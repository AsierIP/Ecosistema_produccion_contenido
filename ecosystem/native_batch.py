"""Resume ordered native candidates through Upro; stop at the first accepted one."""
from pathlib import Path
from .config import read_json, write_json
from .cache import file_hash


def ref(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': file_hash(path)}


def immutable(path, value):
    if path.exists():
        if read_json(path) != value:
            raise ValueError('Native batch artifact changed')
    else:
        write_json(path, value, exclusive=True)
    return path


def advance_batch(root, queue, path):
    batch = read_json(path)
    if batch.get('kind') != 'native_candidate_batch_v1' or batch.get('channel_id') != 'religion':
        raise ValueError('Unsupported native candidate batch')
    candidates = batch['candidates']
    if not 1 <= len(candidates) <= 4 or len({c['path'] for c in candidates}) != len(candidates):
        raise ValueError('A native batch requires up to four distinct candidates')
    for source in [*candidates, batch['contract'], batch['review_manifest'], batch['start_reference']]:
        if file_hash(Path(source['path'])) != source['sha256']:
            raise ValueError('Native batch input changed')
    state_path = path.parent / 'state.json'
    state = read_json(state_path) if state_path.exists() else {'batch_sha256': file_hash(path), 'candidates': {}}
    if state['batch_sha256'] != file_hash(path):
        raise ValueError('Native batch changed after starting')
    if state.get('status') in {'ACCEPTED', 'EXHAUSTED'}:
        return state
    steps = {s['id']: s for s in queue.list()}
    common = {'schema_version': 1, 'channel_id': batch['channel_id'], 'job_id': batch['job_id'], 'mode': batch['mode']}
    def save():
        write_json(state_path, state)
    def register(adapter, inputs, deps=()):
        return queue.register({**common, 'adapter': adapter, 'inputs': inputs, 'depends_on': list(deps)})
    for index, candidate in enumerate(candidates):
        key = str(index)
        progress = state['candidates'].setdefault(key, {})
        quality_id = progress.get('quality') or candidate.get('existing_quality_step')
        if quality_id:
            quality = steps.get(quality_id)
            if not quality or quality['job_id'] != batch['job_id'] or quality['adapter'] != 'segment_quality':
                raise ValueError('Invalid existing candidate quality step')
            if quality['state'] == 'reconciled':
                evidence = quality['result']['reconciliation']
                selection_path = Path(evidence['selection_path'])
                if file_hash(selection_path) != evidence['selection_sha256']:
                    raise ValueError('Native rejection proof changed')
                selection = read_json(selection_path)
                if (selection.get('decision') != 'REJECT' or selection['candidate']['sha256'] != candidate['sha256']
                        or selection['job_id'] != batch['job_id']):
                    raise ValueError('Rejection does not belong to this candidate')
                progress['rejection'] = ref(selection_path)
                continue
            if quality['state'] == 'accepted':
                selection_path = Path(quality['result']['receipt_path']).parent / 'native-selection.json'
                selection = read_json(selection_path)
                if (selection.get('decision') != 'ACCEPT' or selection['candidate']['sha256'] != candidate['sha256']
                        or selection['job_id'] != batch['job_id']):
                    raise ValueError('Acceptance does not belong to this candidate')
                state.update(status='ACCEPTED', selected=ref(selection_path), candidate_index=index)
            save()
            return state
        folder = path.parent / ('candidate-' + str(index + 1))
        if 'technical' not in progress:
            progress['technical'] = register('media_check', [ref(candidate['path'])])
            save()
            return state
        technical = steps[progress['technical']]
        if technical['state'] != 'accepted':
            save()
            return state
        if 'review' not in progress:
            manifest = {**read_json(Path(batch['review_manifest']['path'])), 'output': candidate['path']}
            manifest_path = immutable(folder / 'review-manifest.json', manifest)
            request_path = immutable(folder / 'review-request.json', {
                'kind': 'segment_review_request_v1', 'channel_id': batch['channel_id'],
                'manifest_path': str(manifest_path), 'inputs': [ref(manifest_path), ref(candidate['path'])],
                'extract_endpoints': True, 'sequence_id': batch['sequence_id'], 'segment_id': batch['segment_id']})
            progress['review'] = register('segment_review', [ref(request_path)], [progress['technical']])
            save()
            return state
        review = steps[progress['review']]
        # A bounded provider retry is another durable step, not another candidate.
        seen = set()
        while review['state'] == 'reconciled' and review['id'] not in seen:
            seen.add(review['id'])
            next_id = review['result']['reconciliation'].get('followup_step')
            if not next_id:
                break
            review = steps[next_id]
        if review['state'] != 'accepted':
            save()
            return state
        observations_path = Path(review['result']['path'])
        if file_hash(observations_path) != review['result']['sha256']:
            raise ValueError('Native observation changed after review')
        observation = read_json(observations_path)
        technical_path = immutable(folder / 'technical.json', {**technical['result'], 'status': 'TECHNICAL_PASS'})
        contract = read_json(Path(batch['contract']['path']))
        contract.pop('first_frame_metrics', None)  # Computed from this candidate by the judge.
        contract['candidate'] = Path(candidate['path']).stem
        contract_path = immutable(folder / 'native-contract.json', contract)
        preflight = immutable(folder / 'preflight.json', {
            'kind': 'quality_preflight_v1', 'scope': 'native_segment',
            'unit_id': 'native:' + batch['segment_id'] + ':' + contract['source_batch'] + ':' + contract['candidate']
                       + (':' + batch['storyboard_revision'] if batch.get('storyboard_revision') else ''),
            'master_path': candidate['path'], 'start_reference_path': batch['start_reference']['path'],
            'evidence_context': batch.get('evidence_context', 'Current storyboard observation'),
            'automated_evidence': ref(observations_path), 'technical_evidence': ref(technical_path)})
        inputs = [preflight, contract_path, technical_path, Path(candidate['path']), observations_path,
                  Path(observation['provider_response']['path']), Path(batch['start_reference']['path'])]
        for endpoint in observation['native_endpoints'].values():
            inputs.extend([Path(endpoint['path']), Path(endpoint['extraction_receipt_path'])])
        progress['quality'] = register('segment_quality', [ref(p) for p in inputs], [technical['id'], review['id']])
        save()
        return state
    state['status'] = 'EXHAUSTED'
    save()
    return state


def advance_native_batches(root, queue, *, only_job=None):
    for step in queue.list():
        if only_job is not None and step['job_id'] != only_job:
            continue
        if step['adapter'] != 'vibes_generate' or step['state'] != 'accepted':
            continue
        request = read_json(Path(step['payload']['inputs'][0]['path']))
        template_ref = request.get('selection_template')
        if not template_ref:
            continue
        if (file_hash(Path(step['payload']['inputs'][0]['path'])) != step['payload']['inputs'][0]['sha256']
                or file_hash(Path(template_ref['path'])) != template_ref['sha256']):
            raise ValueError('Native generation handoff changed')
        template = read_json(Path(template_ref['path']))
        if template['job_id'] != step['job_id'] or template['channel_id'] != step['channel_id']:
            raise ValueError('Native handoff belongs to another job')
        immutable(Path(root) / '.runtime/upro/native-batches' / step['id'] / 'batch.json',
                  {**template, 'candidates': step['result']['candidates']})
    for path in (Path(root) / '.runtime/upro/native-batches').glob('*/batch.json'):
        if only_job is not None and read_json(path).get('job_id') != only_job:
            continue
        advance_batch(Path(root), queue, path)
