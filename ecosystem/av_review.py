"""Automated video observations plus offline literal-speech checks, never human QA."""
import json
import shutil
import subprocess
from pathlib import Path
from .cache import file_hash
from .config import read_json, write_json
from .captions import normalize, align_number_spans
from .media import discover


def advance_reviews(root, queue):
    root = Path(root)
    steps = queue.list()
    created = []
    from .segment_review import retry_transient_segment_review
    for step in steps:
        if step['adapter'] == 'av_review':
            retry_transient_segment_review(root, step, queue)
    for step in steps:
        if step['state'] != 'accepted' or step['adapter'] not in {'cutout', 'native_master', 'av_review'}:
            continue
        child = 'av_review' if step['adapter'] in {'cutout', 'native_master'} else 'quality'
        if any(s['adapter'] == child and step['id'] in s['payload'].get('depends_on', []) for s in steps):
            continue
        folder = root / '.runtime/jobs' / step['job_id'] / 'handoffs' / step['id']
        error = folder.parent / ('error-review-' + step['id'] + '.json')
        try:
            if step['adapter'] == 'native_master':
                from .native_batch import immutable, ref as artifact_ref
                from .native_master import checked
                source_path = checked(step['payload']['inputs'][0])
                source = read_json(source_path)
                result = step['result']
                if result.get('status') != 'TECHNICAL_PASS':
                    raise ValueError('Native master lacks technical validation')
                master = checked(result)
                voices = [s for s in steps if s['id'] in step['payload']['depends_on']
                          and s['adapter'] == 'voice_generate' and s['state'] == 'accepted']
                if len(voices) != 1:
                    raise ValueError('Native master needs one bound narration')
                voice_request = checked(voices[0]['payload']['inputs'][0])
                voice = read_json(voice_request)
                creative = checked(voice['creative'])
                music_path = checked(source['music_allocation'])
                music = read_json(music_path)
                license_path = checked(music['license'])
                manifest_path = immutable(folder / 'native-review-manifest.json', {
                    'kind':'native_master_review_v1','channel_id':'religion','output':str(master),
                    'caption_transcript':voice['transcript'],'fps':24,'frames':750,
                    'duration_seconds':31.25,'caption_profile':'early-reels-ivory-gold-v01',
                    'voice':voices[0]['result']['binding']['voice'],
                    'native_contract':{'boundary_seconds':[250/24,500/24],
                        'diegetic_gaze':True,'distinct_scenes':3,'no_repeated_action':True}})
                technical = immutable(folder / 'technical-review-input.json',result)
                context = [source_path,manifest_path,technical,voice_request,creative,music_path,
                           license_path,checked(source['captions'])]
                request = {'kind':'automated_av_request_v1','channel_id':'religion',
                    'manifest_path':str(manifest_path),'manifest_sha256':file_hash(manifest_path),
                    'master_sha256':result['sha256'],'technical_path':str(technical),
                    'context':[artifact_ref(p) for p in context]}
                inputs = [immutable(folder / 'av-request.json',request)]
            elif step['adapter'] == 'cutout':
                inspections = [s for s in steps if s['adapter'] == 'media_check' and s['state'] == 'accepted'
                               and step['id'] in s['payload'].get('depends_on', [])]
                metadata = folder / 'metadata.json'
                if not inspections or not metadata.exists():
                    continue
                refs = step['payload']['inputs']
                manifests = [r for r in refs if Path(r['path']).name == 'master-manifest.json']
                if len(manifests) != 1:
                    raise ValueError('Missing assembly for automated review')
                ref = manifests[0]
                result = step['result']
                if result.get('status') != 'TECHNICAL_PASS' or file_hash(Path(result['output_path'])) != result['sha256']:
                    raise ValueError('Rendered master changed')
                technical = folder / 'technical-review-input.json'
                if not technical.exists():
                    write_json(technical, result, exclusive=True)
                request = {'kind': 'automated_av_request_v1', 'channel_id': step['channel_id'],
                           'manifest_path': ref['path'], 'manifest_sha256': ref['sha256'],
                           'master_sha256': result['sha256'], 'technical_path': str(technical.resolve()),
                           'context': [*refs, {'path': str(metadata.resolve()), 'sha256': file_hash(metadata)},
                                       {'path': str(technical.resolve()), 'sha256': file_hash(technical)}]}
                path = folder / 'av-request.json'
                if path.exists() and read_json(path) != request:
                    raise ValueError('Previous review request changed')
                if not path.exists():
                    write_json(path, request, exclusive=True)
                inputs = [path]
            else:
                request = read_json(Path(step['payload']['inputs'][0]['path']))
                result = step['result']
                report = Path(result['path'])
                if file_hash(report) != result['sha256']:
                    raise ValueError('Automated review changed')
                for ref in request['context']:
                    if file_hash(Path(ref['path'])) != ref['sha256']:
                        raise ValueError('Review context changed')
                manifest = read_json(Path(request['manifest_path']))
                preflight = folder / 'quality-preflight.json'
                value = {'kind': 'quality_preflight_v1', 'capabilities': {},
                         'automated_evidence': {'path': str(report), 'sha256': result['sha256']},
                         'technical_evidence': {'sha256': file_hash(Path(request['technical_path']))}}
                if not preflight.exists():
                    write_json(preflight, value, exclusive=True)
                elif read_json(preflight) != value:
                    raise ValueError('QA preflight changed')
                evidence = read_json(report)
                # The final reviewer gets the master plus local evidence, not all source MP4s.
                inputs = [preflight, report, Path(manifest['output'])]
                inputs += [Path(r['path']) for r in request['context'] if Path(r['path']).suffix.lower() != '.mp4']
                if manifest.get('kind') == 'native_master_review_v1':
                    from .metadata import prepare_native_metadata
                    from .native_batch import immutable
                    creative_inputs = [read_json(Path(r['path'])) for r in request['context']
                                       if Path(r['path']).suffix.lower() == '.json']
                    creatives = [c for c in creative_inputs if isinstance(c,dict)
                                 and c.get('canonical_narration_text') == manifest['caption_transcript']
                                 and c.get('editorial_title')]
                    if len(creatives) != 1:
                        raise ValueError('Native publication requires one bound editorial source')
                    inputs.append(immutable(folder / 'metadata.json',
                        prepare_native_metadata(creatives[0],evidence['master_sha256'])))
                inputs += [Path(evidence[k]['path']) for k in ('provider_response', 'local_asr')]
                if evidence.get('intro_asr'):
                    inputs.append(Path(evidence['intro_asr']['path']))
                inputs = list(dict.fromkeys(inputs))
            created.append(queue.register({'schema_version': 1, 'job_id': step['job_id'],
                'channel_id': step['channel_id'], 'adapter': child, 'mode': step['mode'],
                'depends_on': [step['id']],
                'inputs': [{'path': str(p.resolve()), 'sha256': file_hash(p)} for p in inputs]}))
            if error.exists() and read_json(error).get('status') != 'resolved':
                write_json(error, {'status': 'resolved'})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            problem = {'status': 'blocked', 'reason': str(exc)}
            if not error.exists() or read_json(error) != problem:
                write_json(error, problem)
    return created


def summarize_review(manifest, provider, asr, intro_asr=None):
    provider, asr = Path(provider), Path(asr)
    master = Path(manifest['output'])
    digest = file_hash(master)
    intent = read_json(provider / 'intent.json')
    if intent.get('state') != 'response_saved' or intent.get('master_sha256') != digest:
        raise ValueError('Provider review is incomplete or belongs to another master')
    response = read_json(provider / 'response.json')
    candidate = response['candidates'][0]
    if candidate.get('finishReason') != 'STOP':
        raise ValueError('Provider review was truncated or refused')
    report = json.loads(''.join(p.get('text', '') for p in candidate['content']['parts'] if not p.get('thought')))
    if (report.get('decision') not in {'PASS', 'FAIL', 'UNCERTAIN'}
            or not isinstance(report.get('defects'), list)
            or any(not isinstance(report.get(k), str) or not report[k].strip()
                   for k in ('audio_observation', 'visual_observation', 'caption_observation', 'limitations'))):
        raise ValueError('Incomplete automated observations')
    expected = manifest['caption_transcript'].split()
    if intro_asr is not None:
        expected = [w['word'] for w in read_json(Path(intro_asr))['words']] + expected
    words = align_number_spans(expected, read_json(asr)['words'])
    literal = [normalize(w['word']) for w in words] == [normalize(w) for w in expected]
    return {'kind': 'automated_av_evidence_v1', 'status': 'EVIDENCE_READY',
            'master_sha256': digest, 'master_path': str(master.resolve()),
            'review_method': 'automated-audiovisual-review', 'human_review': False,
            'provider_model': intent['model'], 'provider_observations': report,
            'literal_speech_match': literal, 'local_transcript': ' '.join(w['word'].strip() for w in words),
            'provider_response': {'path': str((provider / 'response.json').resolve()), 'sha256': file_hash(provider / 'response.json')},
            'local_asr': {'path': str(asr.resolve()), 'sha256': file_hash(asr)},
            'intro_asr': {'path': str(Path(intro_asr).resolve()), 'sha256': file_hash(Path(intro_asr)),
                          'source_sha256': file_hash(Path(manifest['intro']))} if intro_asr is not None else None,
            'usage': response.get('usageMetadata', {}), 'production_qa_pass': False}


def run_review(request_path, output, *, root):
    request = read_json(Path(request_path))
    if request.get('kind') != 'automated_av_request_v1':
        raise ValueError('Expected automated review request')
    manifest_path = Path(request['manifest_path'])
    manifest = read_json(manifest_path)
    for ref in request.get('context', []):
        if file_hash(Path(ref['path'])) != ref['sha256']:
            raise ValueError('Review source context changed')
    if (file_hash(manifest_path) != request['manifest_sha256']
            or file_hash(Path(manifest['output'])) != request['master_sha256']):
        raise ValueError('Master or assembly changed before review')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    binding = output / 'binding.json'
    if binding.exists():
        if read_json(binding) != request:
            raise ValueError('Previous review uses other inputs')
    else:
        write_json(binding, request, exclusive=True)
    provider = output / 'provider'
    if not (provider / 'response.json').exists():
        runtime = shutil.which('pwsh')
        if not runtime:
            raise ValueError('PowerShell 7 is required for the protected provider adapter')
        run = subprocess.run([runtime, '-NoProfile', '-File', str(root / 'scripts/providers/review-google-video.ps1'),
            '-ManifestPath', str(manifest_path), '-OutputDirectory', str(provider)], capture_output=True,
            timeout=480, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            raise ValueError('Automatic video review failed; inspect provider intent and sanitized error')
    asr = output / 'master-asr.json'
    intro_asr = output / 'intro-asr.json' if manifest.get('intro') else None
    targets = [(manifest['output'], asr)]
    if intro_asr:
        targets.append((manifest['intro'], intro_asr))
    for source, destination in targets:
        if destination.exists():
            continue
        runtime = discover().get('asr_python')
        if not runtime:
            raise ValueError('Installed offline ASR unavailable')
        models = list((Path(runtime).parents[2] / 'asr-models').rglob('model.bin'))
        if len(models) != 1:
            raise ValueError('Expected one installed ASR model; no downloads permitted')
        run = subprocess.run([runtime, str(root / 'scripts/transcribe-local.py'), '--audio', source,
            '--model', str(models[0].parent), '--output', str(destination)], capture_output=True,
            timeout=300, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            raise ValueError('Offline master transcription failed')
    result = summarize_review(manifest, provider, asr, intro_asr)
    path = output / 'automated-review.json'
    if path.exists() and read_json(path) != result:
        raise ValueError('Saved automated evidence changed')
    if not path.exists():
        write_json(path, result, exclusive=True)
    return {**result, 'path': str(path.resolve()), 'sha256': file_hash(path)}
