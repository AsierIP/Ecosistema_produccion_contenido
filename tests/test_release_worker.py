from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

from ecosystem.cache import file_hash
from ecosystem.config import ROOT, load_channels, write_json
from ecosystem.release_worker import release_request, start_operation, finish_operation
from ecosystem.store import Store, IntentUncertainError, QualityError
from test_quality import quality_fixture


class ReleaseWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master, self.qa, _, _ = quality_fixture(self.root)
        self.master = self.master.rename(self.root / 'master.mp4')
        self.qa['timeline']['voice_speed_factor'] = 1.15
        self.channel = next(c for c in load_channels(ROOT) if c['id'] == 'sabias-que')
        self.account = self.channel['platforms']['youtube']['channel_id']
        self.qa_path = self.root / 'qa.json'
        write_json(self.qa_path, self.qa)
        self.meta = self.root / 'metadata.json'
        write_json(self.meta, {'title': 'Test', 'description': 'Test description', 'master_sha256': file_hash(self.master)})
        self.request = self.root / 'request.json'
        self.data = {'kind': 'youtube_operation_v1', 'action': 'upload', 'channel_id': 'sabias-que',
                     'expected_account_id': self.account, 'master_path': str(self.master),
                     'qa_path': str(self.qa_path), 'metadata_path': str(self.meta)}
        write_json(self.request, self.data)
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.job = store.enqueue_job('sabias-que', '2026-09-07')
        write_json(self.root / 'config/ecosystem.json', {'youtube_release': {
            'upload_visibility': 'private', 'delay_anchor': 'upload_completed_at', 'publish_delay_seconds': 7200}})
        self.packet = {'job_id': self.job['id'], 'channel': self.channel, 'profile': {},
                       'youtube_release': {'upload_visibility': 'private', 'publish_delay_seconds': 7200},
                       'output_directory': str(self.root / 'out'),
                       'inputs': [{'path': str(p), 'sha256': file_hash(p)} for p in
                                  (self.request, self.master, self.meta, self.qa_path)]}

    def test_failed_qa_cannot_reserve_upload(self):
        self.qa['checks']['independent_review']['passed'] = False
        write_json(self.qa_path, self.qa)
        with self.assertRaises(QualityError):
            start_operation(self.packet, self.root)
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.assertEqual(store.list_intents(), [])

    def test_account_mismatch_rejected(self):
        write_json(self.request, {**self.data, 'expected_account_id': 'another-channel'})
        with self.assertRaises(ValueError):
            release_request(self.packet)

    def test_upload_receipt_prepares_schedule_without_claiming_publication(self):
        intent = start_operation(self.packet, self.root)
        with self.assertRaises(IntentUncertainError):
            start_operation(self.packet, self.root)
        write_json(self.root / 'out/youtube-result.json', {
            'master_sha256': file_hash(self.master), 'account_id': self.account,
            'video_id': 'abcdefghijk', 'privacyStatus': 'private', 'upload_complete': True,
            'never_public': True, 'upload_completed_at': datetime.now(timezone.utc).isoformat(),
            'evidence': 'TEST FIXTURE ONLY; no real upload'})
        verified = finish_operation(self.packet, self.root, intent)
        self.assertEqual(verified['state'], 'verified')
        with Store(self.root / '.runtime/production.sqlite3') as store:
            intents = store.list_intents(self.job['id'])
            self.assertEqual({i['action']: i['state'] for i in intents}, {'upload': 'verified', 'schedule': 'prepared'})
            self.assertNotEqual(store.get_job(self.job['id'])['state'], 'complete')

    def test_public_upload_is_rejected(self):
        intent = start_operation(self.packet, self.root)
        write_json(self.root / 'out/youtube-result.json', {'privacyStatus': 'public',
                   'upload_completed_at': datetime.now(timezone.utc).isoformat()})
        with self.assertRaises(QualityError):
            finish_operation(self.packet, self.root, intent)
