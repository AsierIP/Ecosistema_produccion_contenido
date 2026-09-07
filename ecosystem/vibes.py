"""Bounded Vibes generation, executed by the Upro worker in its own browser."""
from pathlib import Path
import subprocess
from .config import read_json, write_json
from .cache import file_hash


def validate_request(request):
    if (request.get('kind') != 'vibes_native_batch_v1' or request.get('channel_id') != 'religion'
            or request.get('count') != 4 or request.get('batch_number') not in {1, 2, 3}):
        raise ValueError('Invalid bounded native generation request')
    bound = {str(Path(r['path']).resolve()): r['sha256'] for r in request['inputs']}
    for key in ('start_reference', 'prompt'):
        source = request[key]
        if bound.get(str(Path(source['path']).resolve())) != source['sha256']:
            raise ValueError('Unbound Vibes generation source')
    for source in request['inputs']:
        if file_hash(Path(source['path'])) != source['sha256']:
            raise ValueError('Vibes generation source changed')
    if request.get('segment_id', 's01') != 's01':
        previous = request.get('predecessor_selection')
        if not previous or bound.get(str(Path(previous['path']).resolve())) != previous['sha256']:
            raise ValueError('Continuation requires a bound accepted predecessor')
        selection = read_json(Path(previous['path']))
        frame = selection['native_last_frame']
        if (selection.get('decision') != 'ACCEPT' or selection.get('sequence_id') != request['sequence_id']
                or selection['segment_id'] != request['continuity_from']
                or frame['file_sha256'].lower() != request['start_reference']['sha256']
                or file_hash(Path(frame['path'])) != frame['file_sha256'].lower()
                or file_hash(Path(frame['quality_receipt_path'])) != frame['quality_receipt_sha256'].lower()
                or not frame.get('accepted_at')):
            raise ValueError('Native continuation lost its accepted frame binding')


def generate(request_path, output, *, root):
    request = read_json(request_path)
    validate_request(request)
    from .browser import browser_command
    command, env = browser_command('religion', 'check', root=root)
    command = [command[0], str(Path(root) / 'scripts/upro-vibes.cjs'), str(root), str(request_path), str(output)]
    run = subprocess.run(command, env=env, capture_output=True, timeout=780,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if run.returncode:
        message = run.stderr.decode('utf-8', errors='replace')[-2500:]
        write_json(Path(output) / 'provider-error.json', {'message': message})
        raise ValueError('Vibes stage incomplete; inspect durable provider intent before retrying')
    intent = read_json(Path(output) / 'intent.json')
    if intent.get('state') != 'downloaded' or intent.get('request_sha256') != file_hash(request_path):
        raise ValueError('Vibes generation receipt incomplete')
    candidates = intent['candidates']
    if len(candidates) != 4 or len({c['sha256'] for c in candidates}) != 4:
        raise ValueError('Vibes did not deliver four distinct candidates')
    for candidate in candidates:
        if file_hash(Path(candidate['path'])) != candidate['sha256']:
            raise ValueError('Downloaded native candidate changed')
    return {'status': 'ASSETS_READY', 'candidates': candidates, 'intent_path': str(Path(output) / 'intent.json'),
            'production_qa_pass': False}
