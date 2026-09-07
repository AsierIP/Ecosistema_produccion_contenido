"""Launch a private, per-channel browser without using the desktop chat bridge."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from .config import ROOT, load_channels


def browser_command(channel_id, mode, *, root=ROOT):
    if channel_id not in {c['id'] for c in load_channels(root)}:
        raise ValueError('Unknown channel')
    if mode not in {'check', 'status', 'connect'}:
        raise ValueError('Unknown browser operation')
    node = shutil.which('node')
    if not node:
        raise ValueError('Node runtime unavailable')
    modules = Path(node).resolve().parent.parent / 'node_modules'
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('channel')
    parser.add_argument('--authenticate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(check_browser(args.channel, authenticate=args.authenticate), ensure_ascii=False))
