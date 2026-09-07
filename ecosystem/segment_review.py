"""Native segment observations executed and reconciled by the Upro engine."""
from pathlib import Path
import json
import shutil
import subprocess
from .cache import file_hash
from .config import read_json, write_json


def validate_native_preflight(packet, manifest):
    try:
        if packet['channel']['id'] != 'religion' or packet.get('review_policy', {}).get('mode') != 'automatic':
            raise ValueError('Native segment review belongs to Religion automatic QA only')
        refs = {str(Path(r['path']).resolve()): r['sha256'] for r in packet['inputs']}
        def bound(path):
            path = Path(path).resolve()
            if refs.get(str(path)) != file_hash(path):
                raise ValueError('Native QA source missing or changed')
            return path
        video = bound(manifest['master_path'])
        review = read_json(bound(manifest['automated_evidence']['path']))
        if review.get('kind') != 'native_segment_observations_v1' or review['master_sha256'] != file_hash(video):
            raise ValueError('Wrong native observations')
        ref = review['provider_response']
        if file_hash(bound(ref['path'])) != ref['sha256']:
            raise ValueError('Provider response changed')
        technical = read_json(bound(manifest['technical_evidence']['path']))
        if technical.get('status') != 'TECHNICAL_PASS' or technical.get('master_sha256') != file_hash(video):
            raise ValueError('Native technical evidence missing')
        if not isinstance(manifest.get('unit_id'), str) or not manifest['unit_id'].startswith('native:'):
            raise ValueError('Missing native review unit')
    except (KeyError, TypeError, ValueError, OSError) as exc:
        return [str(exc)]
    return []


def run_segment_review(request_path, output, *, root):
    request = read_json(Path(request_path))
    if request.get('kind') != 'segment_review_request_v1' or request.get('channel_id') != 'religion':
        raise ValueError('Expected Religion segment review request')
    for ref in request['inputs']:
        if file_hash(Path(ref['path'])) != ref['sha256']:
            raise ValueError('Segment review input changed')
    refs = {str(Path(r['path']).resolve()): r for r in request['inputs']}
    manifest_path = Path(request['manifest_path']).resolve()
    manifest = read_json(manifest_path)
    video = Path(manifest['output']).resolve()
    if str(manifest_path) not in refs or str(video) not in refs or manifest.get('kind') != 'native_segment_review_v1':
        raise ValueError('Unbound segment or manifest')
    output = Path(output)
    provider = output / 'provider'
    prior = request.get('prior_review')
    if prior:
        # Adopt a completed, hash-bound observation; never pretend Upro made the original call.
        provider = Path(prior).resolve()
        for name in ('intent.json', 'response.json', 'cleanup.json'):
            if str(provider / name) not in refs:
                raise ValueError('Prior provider evidence must be bound')
    elif not (provider / 'response.json').exists():
        runtime = shutil.which('pwsh')
        if not runtime:
            raise ValueError('PowerShell runtime unavailable')
        result = subprocess.run([runtime, '-NoProfile', '-File', str(Path(root) / 'scripts/providers/review-google-video.ps1'),
            '-ManifestPath', str(manifest_path), '-OutputDirectory', str(provider), '-ReviewKind', 'Segment'],
            capture_output=True, timeout=480, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('Segment observation incomplete; reconcile provider intent before retrying')
    intent = read_json(provider / 'intent.json')
    if intent.get('state') != 'response_saved' or intent.get('review_kind') != 'Segment' or intent.get('master_sha256') != file_hash(video):
        raise ValueError('Provider observation belongs to another segment or is incomplete')
    if read_json(provider / 'cleanup.json').get('deleted') is not True:
        raise ValueError('Remote segment cleanup remains pending')
    candidate = read_json(provider / 'response.json')['candidates'][0]
    observation = json.loads(''.join(p.get('text', '') for p in candidate['content']['parts']))
    if candidate.get('finishReason') != 'STOP' or observation.get('decision') not in {'PASS', 'FAIL', 'UNCERTAIN'}:
        raise ValueError('Incomplete structured segment observation')
    if any(file_hash(Path(r['path'])) != r['sha256'] for r in request['inputs']):
        raise ValueError('Segment inputs changed during review')
    path = output / 'segment-observations.json'
    evidence = {'kind': 'native_segment_observations_v1', 'master_sha256': file_hash(video),
                'provider_model': intent['model'], 'observations': observation,
                'adopted_prior_review': bool(prior), 'production_qa_pass': False,
                'provider_response': {'path': str(provider / 'response.json'), 'sha256': file_hash(provider / 'response.json')}}
    if path.exists() and read_json(path) != evidence:
        raise ValueError('Existing segment evidence changed')
    if not path.exists():
        write_json(path, evidence, exclusive=True)
    return {'status': 'EVIDENCE_READY', 'path': str(path), 'sha256': file_hash(path),
            'independent_quality_pending': True, 'adopted_prior_review': bool(prior)}
