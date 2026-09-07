"""Native segment observations executed and reconciled by the Upro engine."""
from pathlib import Path
import json
import shutil
import subprocess
import hashlib
from datetime import datetime, timezone
from .cache import file_hash
from .config import read_json, write_json


def extract_native_endpoints(video, output, sequence_id, segment_id):
    from .media import discover, probe
    metadata = probe(video)
    streams = [s for s in metadata.get('streams', []) if s.get('codec_type') == 'video']
    if (not metadata.get('ok') or len(streams) != 1 or streams[0].get('nb_frames') != '125'
            or streams[0].get('avg_frame_rate') != '24/1'
            or (streams[0].get('width'), streams[0].get('height')) != (720, 1280)):
        raise ValueError('Native endpoint extraction requires 125 frames at 720x1280 and 24 fps')
    ffmpeg = discover()['ffmpeg']
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    digest = file_hash(video).upper()
    results = {}
    for key, index in (('native_first_frame', 0), ('native_last_frame', 124)):
        png = output / (key + '.png')
        base = [ffmpeg, '-nostdin', '-v', 'error', '-i', str(video), '-vf', 'select=eq(n\\,' + str(index) + ')', '-frames:v', '1', '-pix_fmt', 'rgb24']
        if not png.exists():
            subprocess.run(base + [str(png)], check=True, capture_output=True, timeout=30)
        raw = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(png), '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             check=True, capture_output=True, timeout=30).stdout
        if len(raw) != 720 * 1280 * 3:
            raise ValueError('Unexpected extracted frame size')
        pixel_hash = hashlib.sha256(b'RGB-RASTER-V1:720x1280x3:' + raw).hexdigest().upper()
        receipt_path = output / (key + '-receipt.json')
        receipt = {'receipt_type': 'frame-extraction-v1', 'source_mp4_path': str(video),
                   'sequence_id': sequence_id, 'segment_id': segment_id,
                   'source_mp4_sha256': digest, 'frame_index': index, 'output_png_path': str(png),
                   'output_png_file_sha256': file_hash(png).upper(), 'output_png_pixel_sha256': pixel_hash,
                   'extractor': 'ffmpeg', 'command': subprocess.list2cmdline(base + [str(png)]), 'completed': True}
        if receipt_path.exists() and read_json(receipt_path) != receipt:
            raise ValueError('Prior extraction changed')
        if not receipt_path.exists():
            write_json(receipt_path, receipt, exclusive=True)
        results[key] = {'path': str(png), 'file_sha256': receipt['output_png_file_sha256'], 'pixel_sha256': pixel_hash,
                        'source_mp4_path': str(video), 'source_mp4_sha256': digest, 'frame_index': index,
                        'extraction_receipt_path': str(receipt_path), 'extraction_receipt_sha256': file_hash(receipt_path).upper(),
                        'extraction_receipt_bytes': receipt_path.stat().st_size,
                        'extracted_at': datetime.fromtimestamp(receipt_path.stat().st_mtime, timezone.utc).isoformat()}
    if file_hash(video).upper() != digest:
        raise ValueError('Native source changed during extraction')
    return results


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
    if request.get('extract_endpoints'):
        evidence['native_endpoints'] = extract_native_endpoints(video, output / 'native-endpoints', request['sequence_id'], request['segment_id'])
    evidence['requested_sample_fps'] = intent.get('requested_sample_fps', 1)
    if path.exists() and read_json(path) != evidence:
        raise ValueError('Existing segment evidence changed')
    if not path.exists():
        write_json(path, evidence, exclusive=True)
    return {'status': 'EVIDENCE_READY', 'path': str(path), 'sha256': file_hash(path),
            'independent_quality_pending': True, 'adopted_prior_review': bool(prior)}
