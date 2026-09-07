"""Local bookkeeping around a single ImageGen call; never supplies artistic QA."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
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
            if stream.read(8) != b'\x89PNG\r\n\x1a\n':
                raise ValueError('Output is not a PNG')
        target = output / 'scene.png'
        if source != target:
            if target.exists():
                raise ValueError('Do not overwrite an existing image')
            shutil.copyfile(source, target)
        bound.append({'path': str(target), 'sha256': file_hash(target), 'bytes': target.stat().st_size})
        write_json(output / 'provenance.json', {'generated_path': str(source), 'sha256': file_hash(source)})
    for name in ('imagegen.intent.json', 'provenance.json'):
        path = output / name
        if path.exists():
            bound.append({'path': str(path), 'sha256': file_hash(path), 'bytes': path.stat().st_size})
    return {**receipt, 'artifacts': bound}
