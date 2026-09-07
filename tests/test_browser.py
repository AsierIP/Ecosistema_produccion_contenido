import tempfile
from pathlib import Path
import unittest
from ecosystem.browser import connection_observation
from ecosystem.config import ROOT, read_json, write_json


class BrowserObservationTests(unittest.TestCase):
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
