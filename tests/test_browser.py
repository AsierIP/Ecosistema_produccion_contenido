import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from ecosystem.browser import connection_observation, browser_command, open_connection
from ecosystem.config import ROOT, read_json, write_json


class BrowserObservationTests(unittest.TestCase):
    def test_connection_uses_private_shared_identifier_without_changing_channel(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / 'local.json', {'youtube_login': {'email': 'owner@example.com'}})
            with patch('ecosystem.browser.browser_command', return_value=(['node', 'religion', 'connect'], {})), \
                    patch('ecosystem.browser.subprocess.Popen') as launch:
                open_connection('religion', root=root)
                self.assertEqual(launch.call_args.args[0], ['node', 'religion', 'connect'])
                self.assertEqual(launch.call_args.kwargs['env']['UPRO_LOGIN_EMAIL'], 'owner@example.com')
                with self.assertRaises(ValueError):
                    open_connection('religion', root=root, login_email='invalid')
                self.assertEqual(launch.call_count, 1)

    def test_explicit_runtime_works_without_codex_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / 'channels/sabias-que.json', read_json(ROOT / 'channels/sabias-que.json'))
            node = root / 'installed-node.exe'
            node.write_bytes(b'test fixture, not executed')
            modules = root / 'modules'
            write_json(modules / 'playwright/package.json', {})
            write_json(root / 'local.json', {'browser_runtime': {'node': str(node), 'modules': str(modules)}})
            with patch('ecosystem.browser.shutil.which', return_value=None):
                command, env = browser_command('sabias-que', 'status', root=root)
            self.assertEqual(command[0], str(node))
            self.assertEqual(env['NODE_PATH'], str(modules))

    def test_wrong_identity_and_private_fields_are_not_displayed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            channel = read_json(ROOT / 'channels/sabias-que.json')
            channel['id'] = 'example'
            channel['platforms']['youtube']['channel_id'] = 'expected'
            write_json(root / 'channels/example.json', channel)
            path = root / '.runtime/upro/browser-connections/example.json'
            value = {'channel_id': 'example', 'expected_account_id': 'wrong', 'status': 'CHANNEL_READY',
                     'observed_at': '2026-09-07T00:00:00Z', 'private_data': 'must not appear'}
            write_json(path, value)
            self.assertIsNone(connection_observation('example', root=root))
            write_json(path, {**value, 'expected_account_id': 'expected'})
            self.assertEqual(connection_observation('example', root=root),
                             {'status': 'CHANNEL_READY', 'observed_at': value['observed_at']})
            path.write_text('{interrupted', encoding='utf-8')
            self.assertIsNone(connection_observation('example', root=root))
