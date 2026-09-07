"""Launch a private, per-channel browser without using the desktop chat bridge."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from .config import ROOT, load_channels, read_json


def connection_observation(channel_id, *, root=ROOT):
    """Display the last observation; never authorize a release from this cache."""
    channel = next((c for c in load_channels(root) if c['id'] == channel_id), None)
    if channel is None:
        raise ValueError('Unknown channel')
    try:
        value = json.loads((Path(root) / '.runtime/upro/browser-connections' / (channel_id + '.json')).read_text(encoding='utf-8'))
        platform = channel['platforms']['youtube']
        if (value.get('channel_id') != channel_id or value.get('expected_account_id') != platform.get('channel_id', platform.get('account'))
                or value.get('status') not in {'CHANNEL_READY', 'AUTH_REQUIRED'}):
            return None
        return {k: value[k] for k in ('status', 'observed_at')}
    except (OSError, ValueError, KeyError):
        return None


def browser_command(channel_id, mode, *, root=ROOT):
    if channel_id not in {c['id'] for c in load_channels(root)}:
        raise ValueError('Unknown channel')
    if mode not in {'check', 'status', 'connect'}:
        raise ValueError('Unknown browser operation')
    local_path = Path(root) / 'local.json'
    runtime = read_json(local_path).get('browser_runtime', {}) if local_path.exists() else {}
    node = runtime.get('node') or shutil.which('node')
    if not node:
        raise ValueError('Node runtime unavailable')
    if not Path(node).is_file():
        raise ValueError('Configured Node runtime unavailable')
    modules = Path(runtime['modules']) if runtime.get('modules') else Path(node).resolve().parent.parent / 'node_modules'
    if not (modules / 'playwright/package.json').is_file():
        raise ValueError('Local Playwright runtime unavailable')
    env = dict(os.environ, NODE_PATH=str(modules))
    command = [node, str(root / 'scripts/upro-browser.cjs'), str(root), channel_id, mode]
    return command, env


def check_browser(channel_id, *, root=ROOT, authenticate=False):
    command, env = browser_command(channel_id, 'status' if authenticate else 'check', root=root)
    result = subprocess.run(command, env=env, capture_output=True, text=True, encoding='utf-8',
                            timeout=80, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('No se pudo iniciar el navegador propio de Upro')
    return json.loads(result.stdout.strip().splitlines()[-1])


def open_connection(channel_id, *, root=ROOT):
    command, env = browser_command(channel_id, 'connect', root=root)
    return subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def open_provider_connection(channel_id, *, root=ROOT):
    channel = next((c for c in load_channels(root) if c['id'] == channel_id), None)
    if not channel or channel['visual'].get('generation_provider', 'vibes') != 'vibes':
        raise ValueError('This channel does not use Vibes')
    local = read_json(Path(root) / 'local.json')
    chrome = Path(local.get('browser_runtime', {}).get('chrome', ''))
    if not chrome.is_file():
        raise ValueError('Chrome runtime unavailable')
    profile = Path(root).resolve() / '.runtime/browser-profiles' / channel_id
    # Normal manual sign-in browser: no credential automation or copied sessions.
    return subprocess.Popen([str(chrome), '--user-data-dir=' + str(profile), '--disable-background-mode',
                             '--new-window', 'https://vibes.ai/'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('channel')
    parser.add_argument('--authenticate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check_browser(args.channel, authenticate=args.authenticate), ensure_ascii=False))
