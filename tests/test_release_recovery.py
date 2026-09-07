from pathlib import Path
import unittest
from ecosystem.cache import file_hash
from ecosystem.config import write_json, read_json
from ecosystem.store import Store
from ecosystem.upro_queue import Queue
import test_release_worker


class ReconciledReleaseTests(unittest.TestCase):
    setUp = test_release_worker.ReleaseWorkerTests.setUp

    def failed_step(self):
        self.queue = Queue(self.root)
        refs = [{**r, 'bytes': Path(r['path']).stat().st_size} for r in self.packet['inputs']]
        packet = {**self.packet, 'role': 'release', 'inputs': refs}
        folder = self.root / 'out'
        write_json(folder / 'packet.json', packet)
        write_json(folder / 'receipt.json', {
            'job_id': self.job['id'], 'role': 'release', 'decision': 'BLOCK',
            'artifacts': [], 'checks': [], 'inputs_reviewed': refs,
            'blockers': ['TEST: browser unavailable']})
        step = self.queue.register({'schema_version': 1, 'job_id': self.job['id'],
            'channel_id': 'sabias-que', 'adapter': 'release', 'mode': 'production', 'inputs': refs})
        self.assertTrue(self.queue.claim(step))
        self.queue.finish(step, {'receipt_path': str(folder / 'receipt.json')}, 'blocked')
        return step

    def schedule_verified(self):
        test_release_worker.ReleaseWorkerTests.test_upload_receipt_prepares_schedule_without_claiming_publication(self)
        with Store(self.root / '.runtime/production.sqlite3') as store:
            schedule = next(i for i in store.list_intents() if i['action'] == 'schedule')
            schedule = store.start_intent(schedule['id'], schedule['version'])
            store.reconcile_intent(schedule['id'], schedule['version'], 'verified', {
                'master_sha256': file_hash(self.master), 'account_id': self.account,
                'video_id': 'abcdefghijk', 'privacyStatus': 'private',
                'publishAt': schedule['payload']['publishAt'], 'scheduled': True,
                'evidence': 'TEST remote schedule fixture'})
        return schedule

    def test_recovery_only_queues_due_public_check_and_preserves_failed_receipt(self):
        schedule = self.schedule_verified()
        old = self.failed_step()
        receipt_hash = file_hash(self.root / 'out/receipt.json')
        created = self.queue.advance_completed_releases()
        self.assertEqual(len(created), 1)
        self.assertEqual(self.queue.advance_completed_releases(), [])
        steps = self.queue.list()
        self.assertEqual(next(s for s in steps if s['id'] == old)['state'], 'reconciled')
        followup = next(s for s in steps if s['id'] == created[0])
        request = read_json(Path(followup['payload']['inputs'][0]['path']))
        self.assertEqual(request['action'], 'verify_public')
        self.assertFalse(self.queue.claim(created[0]))
        self.assertEqual(file_hash(self.root / 'out/receipt.json'), receipt_hash)
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.assertEqual(len(store.list_intents()), 2)
            self.assertEqual(store.get_intent(schedule['id'])['payload']['publishAt'], schedule['payload']['publishAt'])

    def test_no_recovery_without_verified_remote_schedule(self):
        test_release_worker.ReleaseWorkerTests.test_upload_receipt_prepares_schedule_without_claiming_publication(self)
        self.failed_step()
        self.assertEqual(self.queue.advance_completed_releases(), [])
        self.assertEqual(self.queue.list()[0]['state'], 'blocked')

    def test_changed_master_stays_blocked(self):
        self.schedule_verified()
        self.failed_step()
        self.master.write_bytes(b'changed fixture')
        self.assertEqual(self.queue.advance_completed_releases(), [])
        self.assertEqual(self.queue.list()[0]['state'], 'blocked')
