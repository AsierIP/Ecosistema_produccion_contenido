"""Connect accepted native scenes and bounded replacement batches without an agent."""
from pathlib import Path
import hashlib
import re
import shutil
from .config import read_json, write_json
from .cache import file_hash
from .native_batch import ref, immutable


def retry_prompt(prompt, defects):
    """Keep review prose out of provider instructions; preserve the planned action."""
    if not defects:
        return prompt
    return prompt + ('\n\nCONTINUITY DURING ACTION: Keep the planned movement, emotion and camera progression. '
        'Track each existing prop as the same physical object throughout the shot. '
        'During a transfer, the receiver establishes support before the giver releases; '
        'hands move around that same object along continuous visible paths. '
        'Stage contact, weight transfer and release in that causal order while breathing, '
        'cloth and environmental motion continue naturally. Preserve the established entry and exit story states.\n')


def advance_sequence(root, queue, path):
    spec = read_json(path)
    if spec.get('kind') != 'native_sequence_v1' or spec.get('channel_id') != 'religion':
        raise ValueError('Unsupported native sequence')
    bound = {r['path']: r['sha256'] for r in spec['inputs']}
    if any(bound.get(spec[k]['path']) != spec[k]['sha256'] for k in ('creative', 'contract', 'start_reference')):
        raise ValueError('Native sequence references are not bound')
    for source in spec['inputs']:
        if file_hash(Path(source['path'])) != source['sha256']:
            raise ValueError('Native sequence source changed')
    creative = read_json(Path(spec['creative']['path']))
    contract_template = read_json(Path(spec['contract']['path']))
    if creative['sequence_id'] != spec['sequence_id'] or len(creative['segments']) != 3:
        raise ValueError('Expected the bound three-scene native sequence')
    voices = [s for s in queue.list() if s['job_id'] == spec['job_id'] and s['adapter'] == 'voice_generate']
    if not voices:
        voice_path = immutable(path.parent / 'voice-request.json', {'kind': 'voice_generation_v1',
            'channel_id': spec['channel_id'], 'transcript': creative['canonical_narration_text'],
            'native_sequence': spec['sequence_id'], 'creative': spec['creative']})
        queue.register({'schema_version': 1, 'channel_id': spec['channel_id'], 'job_id': spec['job_id'],
                       'adapter': 'voice_generate', 'mode': spec['mode'], 'inputs': [ref(voice_path)]})
    elif len(voices) != 1 or read_json(Path(voices[0]['payload']['inputs'][0]['path']))['transcript'] != creative['canonical_narration_text']:
        raise ValueError('Native sequence narration requires reconciliation')
    batches = []
    for batch_path in (root / '.runtime/upro/native-batches').glob('*/batch.json'):
        batch = read_json(batch_path)
        if batch['job_id'] != spec['job_id']:
            continue
        if batch.get('storyboard_revision') != spec.get('storyboard_revision'):
            continue
        state_path = batch_path.parent / 'state.json'
        state = read_json(state_path) if state_path.exists() else {}
        if state and state.get('batch_sha256') != file_hash(batch_path):
            raise ValueError('Native sequence batch changed')
        contract = read_json(Path(batch['contract']['path']))
        number = re.fullmatch(r's\d\d-b(\d\d)', contract['source_batch'])
        if not number:
            raise ValueError('Invalid native batch number')
        batches.append((batch, state, int(number[1])))
    selected = []
    for segment in creative['segments']:
        segment_id = segment['segment_id']
        relevant = [row for row in batches if row[0]['segment_id'] == segment_id]
        accepted = [row for row in relevant if row[1].get('status') == 'ACCEPTED']
        if len(accepted) > 1:
            raise ValueError('Multiple accepted candidates require reconciliation')
        if accepted:
            source = accepted[0][1]['selected']
            if file_hash(Path(source['path'])) != source['sha256']:
                raise ValueError('Native selection changed')
            selection = read_json(Path(source['path']))
            if (selection['decision'] != 'ACCEPT' or selection['segment_id'] != segment_id
                    or selection['job_id'] != spec['job_id'] or selection['sequence_id'] != spec['sequence_id']):
                raise ValueError('Wrong native selection')
            selected.append(source)
            continue
        if any(state.get('status') != 'EXHAUSTED' for _, state, _ in relevant):
            return
        if spec.get('generation_enabled', True) is not True:
            write_json(path.parent / 'status.json', {'status': 'GENERATION_PAUSED', 'segment_id': segment_id,
                       'reason': 'Storyboard diagnostic: reuse existing evidence before requesting more media.'})
            return
        next_batch = max((n for _, _, n in relevant), default=0) + 1
        if next_batch > 3:
            write_json(path.parent / 'status.json', {'status': 'REPLAN_REQUIRED', 'segment_id': segment_id,
                       'reason': 'Three native batches exhausted; do not repeat generation or accept a rejected clip.'})
            return
        for step in queue.list():
            if step['job_id'] != spec['job_id'] or step['adapter'] != 'vibes_generate':
                continue
            request = read_json(Path(step['payload']['inputs'][0]['path']))
            if request.get('storyboard_revision') != spec.get('storyboard_revision'):
                continue
            if request.get('segment_id', 's01') == segment_id and request['batch_number'] == next_batch:
                return  # Existing intent/step, including uncertain operations, must be reconciled.
        folder = path.parent / (segment_id + '-b' + str(next_batch).zfill(2))
        folder.mkdir(parents=True, exist_ok=True)
        source = spec['start_reference'] if not selected else ref(read_json(Path(selected[-1]['path']))['native_last_frame']['path'])
        if selected and segment['continuity_from'] != read_json(Path(selected[-1]['path']))['segment_id']:
            raise ValueError('Native scene predecessor mismatch')
        start = folder / (segment_id + '-start-' + source['sha256'][:12] + '.png')
        if not start.exists():
            shutil.copyfile(source['path'], start)
        if file_hash(start) != source['sha256']:
            raise ValueError('Start-frame copy is not byte-identical')
        prompt_source = segment['provider_prompt']
        prompt_path = Path(prompt_source['provider_prompt_file_path'])
        if file_hash(prompt_path) != prompt_source['provider_prompt_file_sha256'].lower():
            raise ValueError('Canonical scene prompt changed')
        prompt = prompt_path.read_text(encoding='utf-8-sig')
        defects = []
        for _, state, _ in relevant:
            for candidate in state['candidates'].values():
                rejection = candidate.get('rejection')
                if rejection:
                    if file_hash(Path(rejection['path'])) != rejection['sha256']:
                        raise ValueError('Prior rejection changed')
                    defects.extend(read_json(Path(rejection['path']))['candidate']['rejection_causes'])
        prompt = retry_prompt(prompt, defects)
        prompt_file = folder / 'prompt.txt'
        if prompt_file.exists() and prompt_file.read_text(encoding='utf-8') != prompt:
            raise ValueError('Native retry prompt changed')
        if not prompt_file.exists():
            prompt_file.write_text(prompt, encoding='utf-8')
        contract = {**contract_template, 'segment': segment, 'source_batch': segment_id + '-b' + str(next_batch).zfill(2)}
        contract.pop('candidate', None)
        contract.pop('first_frame_metrics', None)
        contract_path = immutable(folder / 'contract.json', contract)
        review_path = immutable(folder / 'review.json', {'kind': 'native_segment_review_v1',
                    'caption_transcript': creative['canonical_narration_text'], 'segment': segment['state']})
        template_path = immutable(folder / 'selection-template.json', {'kind': 'native_candidate_batch_v1',
                    'channel_id': spec['channel_id'], 'job_id': spec['job_id'], 'mode': spec['mode'],
                    'sequence_id': spec['sequence_id'], 'segment_id': segment_id, 'contract': ref(contract_path),
                    'review_manifest': ref(review_path), 'start_reference': ref(start),
                    **({'storyboard_revision': spec['storyboard_revision']} if spec.get('storyboard_revision') else {})})
        request = {'kind': 'vibes_native_batch_v1', 'channel_id': spec['channel_id'], 'segment_id': segment_id,
                   'sequence_id': spec['sequence_id'], 'continuity_from': segment['continuity_from'],
                   'batch_number': next_batch, 'count': 4, 'project_url': spec['project_url'], 'project_title': spec['project_title'],
                   'start_reference': ref(start), 'prompt': ref(prompt_file), 'selection_template': ref(template_path),
                   'output_directory': str(Path(spec['native_root']) / ('revision-' + hashlib.sha256(spec['storyboard_revision'].encode()).hexdigest()[:12] if spec.get('storyboard_revision') else 'original') / segment_id / contract['source_batch']),
                   'inputs': [ref(start), ref(prompt_file), ref(template_path), ref(contract_path), ref(review_path)]}
        if spec.get('storyboard_revision'):
            request['storyboard_revision'] = spec['storyboard_revision']
        if selected:
            request['predecessor_selection'] = selected[-1]
            request['inputs'].append(selected[-1])
        request_path = immutable(folder / 'request.json', request)
        step_id = queue.register({'schema_version': 1, 'channel_id': spec['channel_id'], 'job_id': spec['job_id'],
                     'adapter': 'vibes_generate', 'mode': spec['mode'], 'inputs': [ref(request_path)]})
        write_json(path.parent / 'status.json', {'status': 'GENERATING', 'segment_id': segment_id, 'step_id': step_id})
        return
    write_json(path.parent / 'status.json', {'status': 'NATIVE_SEQUENCE_ACCEPTED', 'segments': selected,
               'montage_pending': True})


def advance_native_sequences(root, queue, *, only_job=None):
    for path in (Path(root) / '.runtime/upro/native-sequences').glob('*/sequence.json'):
        if only_job is not None and read_json(path).get('job_id') != only_job:
            continue
        advance_sequence(Path(root), queue, path)
