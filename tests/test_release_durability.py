from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from ecosystem.release import prepare_youtube_schedule
from ecosystem.store import Store, QualityError, IntentUncertainError


class DurableScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'state.sqlite3'
        self.store = Store(self.db)
        self.addCleanup(self.store.close)
        self.job = self.store.enqueue_job('sabias-que', '2026-09-07')
        self.upload = self.store.prepare_intent(self.job['id'], 'youtube', 'upload', 'a' * 64,
                                               {'expected_account_id': 'channel-test'})
        self.upload = self.store.start_intent(self.upload['id'], self.upload['version'])
        self.evidence = {'account_id': 'channel-test', 'video_id': 'abcdefghijk',
                         'master_sha256': 'a' * 64, 'privacyStatus': 'private',
                         'upload_complete': True, 'never_public': True,
                         'upload_completed_at': '2026-09-07T10:00:43Z',
                         'evidence': 'test fixture: completed private upload'}
        self.now = datetime.fromisoformat('2026-09-07T10:01:00+00:00')

    def verify_upload(self):
        return self.store.reconcile_intent(self.upload['id'], self.upload['version'],
                                           'verified', self.evidence)

    def prepare(self, store=None, now=None):
        return prepare_youtube_schedule(store or self.store, self.upload['id'], now=now or self.now)

    def test_restart_preserves_original_target_and_rejects_elapsed(self):
        self.verify_upload()
        first = self.prepare()
        self.assertEqual(first['payload']['publishAt'], '2026-09-07T12:01:00Z')
        with Store(self.db) as reopened:
            self.assertEqual(first, self.prepare(reopened, datetime.fromisoformat('2026-09-07T11:30:00+00:00')))
            with self.assertRaises(IntentUncertainError):
                self.prepare(reopened, datetime.fromisoformat('2026-09-07T12:02:00+00:00'))
        self.assertEqual(len(self.store.list_intents(self.job['id'])), 2)

    def test_uncertain_upload_never_starts_schedule(self):
        with self.assertRaises(IntentUncertainError):
            self.prepare()
        self.assertEqual(len(self.store.list_intents(self.job['id'])), 1)

    def test_wrong_account_or_incomplete_upload_cannot_schedule(self):
        self.evidence['account_id'] = 'another-channel'
        self.verify_upload()
        with self.assertRaises(QualityError):
            self.prepare()

    def test_uncertain_remote_schedule_is_not_repeated(self):
        self.verify_upload()
        intent = self.prepare()
        self.store.start_intent(intent['id'], intent['version'])
        with self.assertRaises(IntentUncertainError):
            self.prepare()

    def test_schedule_receipt_must_match_and_never_completes_job(self):
        self.verify_upload()
        intent = self.prepare()
        intent = self.store.start_intent(intent['id'], intent['version'])
        evidence = {**self.evidence, 'publishAt': '2026-09-07T12:00:00Z', 'scheduled': True}
        with self.assertRaises(QualityError):
            self.store.reconcile_intent(intent['id'], intent['version'], 'verified', evidence)
        evidence['publishAt'] = intent['payload']['publishAt']
        verified = self.store.reconcile_intent(intent['id'], intent['version'], 'verified', evidence)
        self.assertEqual(verified['state'], 'verified')
        self.assertEqual(self.prepare(now=datetime.fromisoformat('2026-09-08T12:00:00+00:00')), verified)
        self.assertNotEqual(self.store.get_job(self.job['id'])['state'], 'complete')
