"""Private uploads through Upro's own browser with durable resume checkpoints."""
import json
from pathlib import Path
import subprocess
import re
from .browser import browser_command
from .cache import file_hash
from .config import load_channels, read_json, write_json
from .release_worker import browser_preflight, start_operation, finish_operation
from .store import Store


def resumable_upload(root, step):
    """Permit only the same known draft, never another file selection."""
    if step['adapter'] != 'release':
        return False
    try:
        refs = step['payload']['inputs']
        if any(file_hash(Path(r['path'])) != r['sha256'] for r in refs):
            return False
        requests = [read_json(Path(r['path'])) for r in refs
                    if Path(r['path']).suffix == '.json' and Path(r['path']).stat().st_size < 100000]
        request = next(r for r in requests if isinstance(r, dict) and r.get('kind') == 'youtube_operation_v1')
        with Store(Path(root) / '.runtime/production.sqlite3') as store:
            pending = [i for i in store.list_intents(step['job_id']) if i['state'] in {'sending','uncertain'}]
        if len(pending) != 1 or request['action'] != 'upload':
            return False
        intent = pending[0]
        journal = read_json(Path(root) / '.runtime/jobs' / step['job_id'] / 'release/own-browser-upload/upload-journal.json')
        return (intent['action'] == 'upload' and intent['platform'] == 'youtube'
                and journal['intent_id'] == intent['id']
                and journal['master_sha256'] == intent['master_sha256']
                and journal['account_id'] == request['expected_account_id'] == intent['payload']['expected_account_id']
                and any(r['sha256'] == intent['master_sha256'] and str(Path(r['path']).resolve()) == str(Path(request['master_path']).resolve()) for r in refs)
                and re.fullmatch(r'[\w-]{11}', journal.get('video_id','')) is not None
                and journal['stage'] in {'draft_created','private_save_started','private_saved','private_verified'})
    except (OSError,ValueError,KeyError,StopIteration,TypeError):
        return False


def run_upload(root, step):
    root = Path(root)
    channel = next(c for c in load_channels(root) if c['id'] == step['channel_id'])
    refs = step['payload']['inputs']
    if any(file_hash(Path(r['path'])) != r['sha256'] for r in refs):
        raise ValueError('Upload inputs changed')
    out = root / '.runtime/jobs' / step['job_id'] / 'release/own-browser-upload'
    packet = {'job_id': step['job_id'], 'role': 'release', 'channel': channel,
              'profile': read_json(root / 'config/profiles' / (channel['visual']['profile'] + '.json')),
              'youtube_release': read_json(root / 'config/ecosystem.json')['youtube_release'],
              'inputs': refs, 'output_directory': str(out), 'engine': 'upro-local-browser'}
    request = browser_preflight(packet, root)
    if request['action'] != 'upload':
        raise ValueError('Only private upload is supported')
    write_json(out / 'packet.json', packet)
    with Store(root / '.runtime/production.sqlite3') as store:
        matches = [i for i in store.list_intents(step['job_id']) if i['platform'] == 'youtube'
                   and i['action'] == 'upload' and i['master_sha256'] == request['master_sha256']]
    if matches and matches[0]['state'] in {'sending', 'uncertain', 'verified'}:
        intent = matches[0]
        journal = read_json(out / 'upload-journal.json')
        if journal.get('intent_id') != intent['id'] or not journal.get('video_id'):
            raise ValueError('Uncertain upload needs remote reconciliation; do not select the file again')
    else:
        intent = start_operation(packet, root)
    driver = {**request, 'intent_id': intent['id'], 'journal_path': str(out / 'upload-journal.json'),
              'result_path': str(out / 'youtube-result.json'), 'snapshot_path': str(out / 'browser-snapshot.json')}
    write_json(out / 'driver-request.json', driver)
    command, env = browser_command(channel['id'], 'upload', root=root)
    env['UPRO_UPLOAD_REQUEST'] = str(out / 'driver-request.json')
    try:
        done = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8',
                              timeout=600, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        write_json(out / 'driver-execution.json', {'returncode': done.returncode,
                   'stdout': done.stdout[-4000:], 'stderr': done.stderr[-2000:]})
        if done.returncode or not (out / 'youtube-result.json').is_file():
            raise ValueError('Private upload is not yet confirmed; inspect the saved browser checkpoint')
        if any(file_hash(Path(r['path'])) != r['sha256'] for r in refs):
            raise ValueError('Upload inputs changed during execution')
        if intent['state'] != 'verified':
            finish_operation(packet, root, intent)
        report = out / 'youtube-result.json'
        receipt = {'job_id': step['job_id'], 'role': 'release', 'decision': 'ACCEPT',
                   'inputs_reviewed': refs, 'artifacts': [{'path': str(report), 'sha256': file_hash(report),
                   'bytes': report.stat().st_size}], 'checks': [{'name': 'private_upload', 'passed': True,
                   'evidence': read_json(report)['evidence']}], 'blockers': []}
        write_json(out / 'receipt.json', receipt)
        return {'status': 'ACCEPTED', 'receipt_path': str(out / 'receipt.json'), 'agent_started': False,
                'followup_pending': True}
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        with Store(root / '.runtime/production.sqlite3') as store:
            current = store.get_intent(intent['id'])
            if current['state'] == 'sending':
                store.mark_intent_uncertain(current['id'], current['version'], {'reason': str(exc)})
        return {'status': 'UNCERTAIN', 'reason': str(exc), 'agent_started': False,
                'checkpoint': str(out / 'upload-journal.json')}
