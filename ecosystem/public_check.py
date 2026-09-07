"""Verify a scheduled YouTube video with a local anonymous browser, without tokens."""
import json
from pathlib import Path
import subprocess
from .browser import browser_command
from .cache import file_hash
from .config import load_channels, read_json, write_json
from .release_worker import release_request, start_operation, finish_operation
from .store import Store


def run_public_check(root, step):
    root = Path(root)
    channel = next(c for c in load_channels(root) if c['id'] == step['channel_id'])
    refs = [{**ref, 'bytes': Path(ref['path']).stat().st_size} for ref in step['payload']['inputs']]
    if any(file_hash(Path(r['path'])) != r['sha256'] for r in refs):
        raise ValueError('Public verification inputs changed')
    policy = read_json(root / 'config/ecosystem.json')['youtube_release']
    profile = read_json(root / 'config/profiles' / (channel['visual']['profile'] + '.json'))
    out = root / '.runtime/upro/results' / step['id'] / 'public-check'
    packet = {'job_id': step['job_id'], 'role': 'release', 'channel': channel,
              'profile': profile, 'youtube_release': policy, 'inputs': refs,
              'output_directory': str(out), 'engine': 'local-anonymous-browser'}
    request = release_request(packet)
    if request['action'] != 'verify_public':
        raise ValueError('Only public verification is supported')
    # Prepare tools before reserving the durable read-only operation.
    command, env = browser_command(channel['id'], 'check', root=root)
    with Store(root / '.runtime/production.sqlite3') as store:
        schedule = next(i for i in store.list_intents(step['job_id'])
                        if i['action'] == 'schedule' and i['platform'] == 'youtube' and i['state'] == 'verified')
    write_json(out / 'packet.json', packet)
    intent = start_operation(packet, root)
    probe = {'video_id': intent['payload']['video_id'], 'account_id': request['expected_account_id'],
             'handle': channel['platforms']['youtube']['handle'], 'master_sha256': request['master_sha256'],
             'publishAt': schedule['payload']['publishAt']}
    write_json(out / 'request.json', probe)
    try:
        result = subprocess.run([command[0], str(root / 'scripts/upro-public-check.cjs'), str(out / 'request.json')],
                                env=env, capture_output=True, text=True, encoding='utf-8', timeout=125,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('YouTube aún no ofrece una reproducción pública verificable')
        if any(file_hash(Path(r['path'])) != r['sha256'] for r in refs):
            raise ValueError('Public verification inputs changed during playback')
        evidence = json.loads(result.stdout.strip().splitlines()[-1])
        write_json(out / 'youtube-result.json', evidence, exclusive=True)
        finish_operation(packet, root, intent)
        report = out / 'youtube-result.json'
        receipt = {'job_id': step['job_id'], 'role': 'release', 'decision': 'ACCEPT', 'inputs_reviewed': refs,
                   'artifacts': [{'path': str(report), 'sha256': file_hash(report), 'bytes': report.stat().st_size}],
                   'checks': [{'name': 'anonymous_public_playback', 'passed': True, 'evidence': evidence['evidence']}],
                   'blockers': []}
        write_json(out / 'receipt.json', receipt, exclusive=True)
        return {'status': 'ACCEPTED', 'receipt_path': str(out / 'receipt.json'), 'agent_started': False}
    except (ValueError, OSError, subprocess.TimeoutExpired, KeyError, RuntimeError) as exc:
        with Store(root / '.runtime/production.sqlite3') as store:
            current = store.get_intent(intent['id'])
            if current['state'] == 'sending':
                store.mark_intent_uncertain(current['id'], current['version'], {'reason': str(exc), 'read_only': True})
        return {'status': 'UNCERTAIN', 'reason': str(exc), 'agent_started': False}
