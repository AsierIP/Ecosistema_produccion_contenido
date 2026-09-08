"""Local bookkeeping around a single ImageGen call; never supplies artistic QA."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import json
import struct
from .cache import file_hash
from .config import write_json


def prepare_intent(packet):
    output = Path(packet['output_directory'])
    for ref in packet['inputs']:
        if file_hash(Path(ref['path'])) != ref['sha256']:
            raise ValueError('Visual input changed before execution')
    write_json(output / 'imagegen.intent.json', {
        'job_id': packet['job_id'], 'cache_key': packet['cache_key'],
        'provider': 'imagegen', 'image_count': 1, 'inputs': packet['inputs'],
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
    for name in ('imagegen.intent.json', 'provenance.json', 'motion-plan.json'):
        path = output / name
        if path.exists():
            bound.append({'path': str(path), 'sha256': file_hash(path), 'bytes': path.stat().st_size})
    return {**receipt, 'artifacts': bound}
