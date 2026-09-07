from datetime import datetime
from pathlib import Path
import unittest
import test_release_worker
from ecosystem.cache import file_hash
from ecosystem.config import read_json, write_json
from ecosystem.store import Store
from ecosystem.upro_queue import Queue


class ReleaseResumeTests(unittest.TestCase):
    setUp = test_release_worker.ReleaseWorkerTests.setUp

    def completed_upload(self):
        test_release_worker.ReleaseWorkerTests.test_upload_receipt_prepares_schedule_without_claiming_publication(self)
        packet = {**self.packet, 'role': 'release'}
        packet['inputs'] = [{**r, 'bytes': Path(r['path']).stat().st_size} for r in packet['inputs']]
        folder = self.root / 'out'
        write_json(folder / 'packet.json', packet)
        artifact = folder / 'youtube-result.json'
        write_json(folder / 'receipt.json', {'job_id': self.job['id'], 'role': 'release', 'decision': 'ACCEPT',
            'checks': [{'passed': True, 'evidence': 'Fixture only; no real upload'}], 'blockers': [],
            'inputs_reviewed': packet['inputs'],
            'artifacts': [{'path': str(artifact), 'sha256': file_hash(artifact), 'bytes': artifact.stat().st_size}]})
        queue = Queue(self.root)
        step_id = queue.register({'schema_version': 1, 'job_id': self.job['id'], 'channel_id': 'sabias-que',
            'adapter': 'release', 'mode': 'production', 'inputs': packet['inputs']})
        self.assertTrue(queue.claim(step_id))
        queue.finish(step_id, {'receipt_path': str(folder / 'receipt.json')}, 'accepted')
        return queue

    def test_restart_recovers_schedule_once_and_preserves_time(self):
        queue = self.completed_upload()
        with Store(self.root / '.runtime/production.sqlite3') as store:
            original = next(i for i in store.list_intents() if i['action'] == 'schedule')
        self.assertEqual(len(Queue(self.root).advance_completed_releases()), 1)
        self.assertEqual(Queue(self.root).advance_completed_releases(), [])
        self.assertEqual(len(queue.list()), 2)
        request = read_json(Path(queue.list()[1]['payload']['inputs'][0]['path']))
        self.assertEqual(request['action'], 'schedule')
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.assertEqual(store.get_intent(original['id']), original)
            self.assertEqual(len(store.list_intents()), 2)

    def test_already_scheduled_recovers_only_due_public_check(self):
        queue = self.completed_upload()
        with Store(self.root / '.runtime/production.sqlite3') as store:
            schedule = next(i for i in store.list_intents() if i['action'] == 'schedule')
            schedule = store.start_intent(schedule['id'], schedule['version'])
            store.reconcile_intent(schedule['id'], schedule['version'], 'verified', {
                'master_sha256': file_hash(self.master), 'account_id': self.account, 'video_id': 'abcdefghijk',
                'privacyStatus': 'private', 'publishAt': schedule['payload']['publishAt'],
                'scheduled': True, 'evidence': 'Fixture only'})
        self.assertEqual(len(queue.advance_completed_releases()), 1)
        next_step = queue.list()[1]
        request = read_json(Path(next_step['payload']['inputs'][0]['path']))
        self.assertEqual(request['action'], 'verify_public')
        expected = datetime.fromisoformat(schedule['payload']['publishAt'].replace('Z', '+00:00')).timestamp() + 30
        self.assertEqual(next_step['payload']['not_before'], expected)
        self.assertFalse(queue.claim(next_step['id']))

    def test_uncertain_schedule_never_repeated(self):
        queue = self.completed_upload()
        with Store(self.root / '.runtime/production.sqlite3') as store:
            schedule = next(i for i in store.list_intents() if i['action'] == 'schedule')
            store.start_intent(schedule['id'], schedule['version'])
        self.assertEqual(queue.advance_completed_releases(), [])
        self.assertEqual(len(queue.list()), 1)
        error = self.root / '.runtime/jobs' / self.job['id'] / 'handoffs' / ('error-release-' + queue.list()[0]['id'] + '.json')
        self.assertEqual(read_json(error)['status'], 'blocked')
