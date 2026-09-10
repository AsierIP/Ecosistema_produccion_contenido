"""Bounded recovery of terminal local review timeouts; never replay uploads."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from .cache import file_hash
from .config import read_json, write_json


def recover_editorial_context(root, queue):
    from .editorial_history import channel_history
    from .config import load_channels
    root = Path(root)
    channels = {c['id']:c for c in load_channels(root)}
    for step in queue.list():
        result = step.get('result') or {}
        if step['adapter'] != 'creative' or step['state'] != 'blocked' or result.get('agent_started') is not False:
            continue
        if 'historial de temas' not in result.get('reason',''):
            continue
        history = channel_history(root, channels[step['channel_id']])
        if not history:
            continue
        refs = step['payload']['inputs']
        if len(refs)!=1 or file_hash(Path(refs[0]['path']))!=refs[0]['sha256']:
            continue
        pack = read_json(Path(refs[0]['path']))
        pack['editorial_history'] = history
        path = root/'.runtime/upro/recovery'/step['id']/'source-pack.json'
        write_json(path,pack)
        next_id = queue.register({**step['payload'],'inputs':[{'path':str(path.resolve()),'sha256':file_hash(path)}]})
        queue.retire(step['id'],{'checked':True,'reason':'Source candidates preserved; verified editorial history attached before any agent run.','followup_step':next_id})


def recover_missing_runner(root, queue):
    """A failed CreateProcess started no agent; preserve it and repair PATH."""
    from .dispatch import codex_executable
    root = Path(root)
    codex_executable()  # Must now resolve before changing any recorded state.
    restored = []
    for step in queue.list():
        r = step.get('result') or {}
        if step['adapter'] not in {'creative','metadata','quality','segment_quality'} or step['state'] != 'blocked':
            continue
        if r.get('elapsed_seconds', 999) > 1 or not any('[WinError 2]' in e for e in r.get('errors', [])):
            continue
        folder = Path(r['receipt_path']).parent
        if (folder/'receipt.json').exists() or (folder/'launch-failure.json').exists():
            continue
        packet = read_json(folder/'packet.json')
        write_json(folder/'launch-failure.json', r, exclusive=True)
        with sqlite3.connect(root/'.runtime/agent-runs.sqlite3') as db:
            db.execute("DELETE FROM runs WHERE cache_key=? AND state='blocked' AND elapsed<=1", (packet['cache_key'],))
        with queue.connect() as db:
            db.execute("UPDATE steps SET state='queued',result=NULL,updated=? WHERE id=? AND state='blocked'", (time.time(),step['id']))
        restored.append(step['id'])
    return restored


def recover_elapsed_publications(root, queue):
    """Read-only probe of known uploaded videos; never re-upload or reschedule."""
    from datetime import datetime
    from .browser import browser_command
    from .config import load_channels
    from .store import Store
    from .release import validate_schedule_receipt
    root = Path(root)
    recovered = []
    for step in queue.list():
        if step['adapter'] != 'release' or step['state'] not in {'blocked', 'uncertain'}:
            continue
        with Store(root/'.runtime/production.sqlite3') as store:
            pending = [i for i in store.list_intents(step['job_id']) if i['platform']=='youtube' and i['action']=='schedule' and i['state'] in {'sending','uncertain'}]
        if len(pending) != 1:
            continue
        intent = pending[0]
        if datetime.fromisoformat(intent['payload']['publishAt'].replace('Z','+00:00')).timestamp() > time.time():
            continue
        folder = root/'.runtime/upro/recovery'/step['id']
        attempt = folder/'public-probe.json'
        if attempt.exists() and time.time()-attempt.stat().st_mtime < 3600:
            continue
        channel = next(c for c in load_channels(root) if c['id']==step['channel_id'])
        request = {**intent['payload'], 'account_id':intent['payload']['expected_account_id'],
                   'handle':channel['platforms']['youtube']['handle'],'master_sha256':intent['master_sha256']}
        write_json(attempt, request)
        command, env = browser_command(step['channel_id'], 'check', root=root)
        try:
            result = subprocess.run([command[0], str(root/'scripts/upro-public-check.cjs'), str(attempt)],
                                    env=env, capture_output=True, text=True, encoding='utf-8', timeout=125,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode:
                continue
            public = json.loads(result.stdout.strip().splitlines()[-1])
            evidence = {'outcome':'public_observed_after_target','public_receipt':public,
                        'historical_schedule_time_verified':False}
            if validate_schedule_receipt(evidence, intent):
                continue
            write_json(folder/'public-reconciliation.json', evidence)
            with Store(root/'.runtime/production.sqlite3') as store:
                store.reconcile_intent(intent['id'], intent['version'], 'verified', evidence)
            recovered.append(step['id'])
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            continue
    return recovered


def review_process_absent(folder):
    if os.name != 'nt':
        return False
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-Command',
         'Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'],
        capture_output=True, text=True, timeout=20,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        return False
    rows = json.loads(result.stdout)
    if not isinstance(rows, list):
        return False
    return not any(str(folder).lower() in (r.get('CommandLine') or '').lower() for r in rows)


def recover_review_timeouts(root, queue, *, absent=review_process_absent):
    root = Path(root)
    recovered = []
    for step in queue.list():
        # Only local analysis is retryable here. Generation and release need
        # provider-specific reconciliation of their remote side effects.
        if step['adapter'] != 'quality' or step['state'] not in {'blocked', 'uncertain'}:
            continue
        if step['payload'].get('automatic_recovery_of') or time.time()-step['updated'] < 300:
            continue
        result = step.get('result') or {}
        if result.get('status') != 'UNCERTAIN' or not any('Tiempo máximo excedido' in e for e in result.get('errors', [])):
            continue
        receipt = Path(result.get('receipt_path', ''))
        folder = receipt.parent
        if receipt.is_file() or not (folder/'execution.json').is_file() or not absent(folder):
            continue
        packet = read_json(folder/'packet.json')
        if packet.get('job_id') != step['job_id'] or packet.get('role') != 'quality':
            continue
        if any(file_hash(Path(r['path'])) != r['sha256'] for r in step['payload']['inputs']):
            continue
        note = root/'.runtime/upro/recovery'/step['id']/'retry.json'
        value = {'kind':'local_review_timeout_recovery_v1', 'previous_step':step['id'],
                 'reason':'Terminal timeout, no receipt, process absent, inputs unchanged.',
                 'instruction':'Review the existing declared evidence. Do not regenerate media or publish.',
                 'maximum_retries':1}
        if note.exists() and read_json(note) != value:
            continue
        write_json(note, value)
        plan = {**step['payload'], 'automatic_recovery_of':step['id'],
                'inputs':step['payload']['inputs']+[{'path':str(note.resolve()),'sha256':file_hash(note)}]}
        followup = queue.register(plan)
        with sqlite3.connect(root/'.runtime/agent-runs.sqlite3') as db:
            db.execute("UPDATE runs SET state='interrupted' WHERE cache_key=? AND state='uncertain'",
                       (packet['cache_key'],))
        queue.retire(step['id'], {'checked':True,'reason':value['reason'], 'followup_step':followup})
        recovered.append(followup)
    return recovered
