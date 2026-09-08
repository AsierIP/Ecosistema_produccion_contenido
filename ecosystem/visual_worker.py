"""Local bookkeeping around a single ImageGen call; never supplies artistic QA."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import json
import struct
from .cache import file_hash
from .config import read_json, write_json


def existing_source(packet):
    for ref in packet['inputs']:
        p = Path(ref['path'])
        if p.suffix == '.json' and p.stat().st_size < 100000:
            request = read_json(p)
            if isinstance(request, dict) and request.get('kind') == 'existing_image_review_v1':
                return request['source_image']
    return None


def prepare_intent(packet):
    output = Path(packet['output_directory'])
    for ref in packet['inputs']:
        if file_hash(Path(ref['path'])) != ref['sha256']:
            raise ValueError('Visual input changed before execution')
    source = existing_source(packet)
    write_json(output / ('visual-review.intent.json' if source else 'imagegen.intent.json'), {
        'job_id': packet['job_id'], 'cache_key': packet['cache_key'],
        'provider': 'existing_image_review' if source else 'imagegen', 'image_count': 0 if source else 1, 'inputs': packet['inputs'],
        'created_at': datetime.now(timezone.utc).isoformat(),
        'state': 'prepared_by_local_executor',
    }, exclusive=True)


def seal_receipt(receipt, packet, *, generated_root=None):
    """Import only a generated PNG; hash and receipt construction cost no tokens."""
    output = Path(packet['output_directory']).resolve()
    generated_root = (generated_root or Path.home() / '.codex/generated_images').resolve()
    artifacts = receipt.get('artifacts', [])
    if not isinstance(artifacts, list) or len(artifacts) > 1:
        raise ValueError('Visual worker may return at most one generated image')
    bound = []
    if artifacts:
        source = Path(artifacts[0]['path']).resolve(strict=True)
        existing = existing_source(packet) if packet.get('inputs') else None
        if existing and (source != Path(existing['path']).resolve() or file_hash(source) != existing['sha256']):
            raise ValueError('Existing-image review may not substitute or regenerate the image')
        if not source.is_relative_to(generated_root) and not source.is_relative_to(output):
            raise ValueError('Image is outside the tool output directories')
        if source.suffix.lower() != '.png' or source.stat().st_size > 100_000_000:
            raise ValueError('Invalid image output')
        with source.open('rb') as stream:
            header = stream.read(24)
            if header[:8] != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Output is not a PNG')
        if receipt.get('decision') == 'ACCEPT' and packet.get('channel', {}).get('id') == 'sabias-que':
            if len(header) < 24 or header[12:16] != b'IHDR':
                raise ValueError('Image lacks a valid PNG size header')
            width, height = struct.unpack('>II', header[16:24])
            if height <= width or not height or abs(width / height - 9 / 16) > .04:
                raise ValueError('Comic reel image must have a vertical 9:16 composition')
        target = output / 'scene.png'
        if source != target:
            if target.exists():
                raise ValueError('Do not overwrite an existing image')
            shutil.copyfile(source, target)
        bound.append({'path': str(target), 'sha256': file_hash(target), 'bytes': target.stat().st_size})
        write_json(output / 'provenance.json', {'generated_path': str(source), 'sha256': file_hash(source)})
        if receipt.get('decision') == 'ACCEPT':
            from .motion import validate_motion
            plans = [c for c in receipt.get('checks', []) if c.get('name') == 'motion_plan' and c.get('passed') is True]
            if len(plans) != 1:
                raise ValueError('Accepted comic image requires one inspected motion plan')
            plan = validate_motion(json.loads(plans[0]['evidence']))
            write_json(output / 'motion-plan.json', {**plan, 'source_sha256': file_hash(target)}, exclusive=True)
    for name in ('imagegen.intent.json', 'visual-review.intent.json', 'provenance.json', 'motion-plan.json'):
        path = output / name
        if path.exists():
            bound.append({'path': str(path), 'sha256': file_hash(path), 'bytes': path.stat().st_size})
    return {**receipt, 'artifacts': bound}


def recover_missing_image_paths(root, queue, *, generated_root=None):
    """Bind a unique image in the exact completed worker thread to a review-only step."""
    import re
    root = Path(root)
    generated_root = generated_root or Path.home() / '.codex/generated_images'
    created = []
    for step in queue.list():
        if step['adapter'] != 'visual' or step['state'] != 'blocked':
            continue
        result = step.get('result') or {}
        if not result.get('receipt_path'):
            continue
        folder = Path(result['receipt_path']).parent
        try:
            raw = read_json(folder / 'agent-response.json')
            if (raw.get('decision') != 'BLOCK' or raw.get('artifacts')
                    or not any('PNG artifact path' in str(b) for b in raw.get('blockers', []))):
                continue
            events = [json.loads(line) for line in (folder / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            threads = {e['thread_id'] for e in events if e.get('type') == 'thread.started'}
            if len(threads) != 1 or not any(e.get('type') == 'turn.completed' for e in events):
                continue
            thread = next(iter(threads))
            if not re.fullmatch(r'[0-9a-f-]{36}', thread):
                continue
            images = list((generated_root / thread).glob('exec-*.png'))
            if len(images) != 1:
                continue
            image = images[0].resolve()
            packet = read_json(folder / 'packet.json')
            if packet['job_id'] != step['job_id'] or packet['channel']['id'] != step['channel_id']:
                continue
            requests = []
            for r in packet['inputs']:
                p = Path(r['path'])
                if file_hash(p) != r['sha256']:
                    raise ValueError('Original visual input changed')
                if p.suffix == '.json':
                    value = read_json(p)
                    if isinstance(value, dict) and value.get('kind') == 'image_generation_request_v1':
                        requests.append(value)
            if len(requests) != 1:
                continue
            request = requests[0]
            ref = {'path': str(image), 'sha256': file_hash(image)}
            path = folder / 'existing-image-review.json'
            value = {**request, 'kind': 'existing_image_review_v1', 'image_count': 0, 'source_image': ref,
                'recovery': {'original_step': step['id'], 'thread_id': thread, 'new_generation_authorized': False}}
            if path.exists() and read_json(path) != value:
                continue
            if not path.exists():
                write_json(path, value, exclusive=True)
            followup = queue.register({**step['payload'], 'inputs': [
                {'path': str(path.resolve()), 'sha256': file_hash(path)}, ref],
                'recovered_visual_step': step['id']})
            queue.retire(step['id'], {'checked': True, 'reason': 'Unique generated PNG found in the completed worker thread; inspect it without another ImageGen call.',
                                      'image': ref, 'followup_step': followup})
            created.append(followup)
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return created
