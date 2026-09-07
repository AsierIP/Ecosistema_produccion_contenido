from datetime import datetime, timezone, timedelta
import json
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from ecosystem.config import write_json
from ecosystem.cache import file_hash
from ecosystem.store import Store
from ecosystem.public_check import run_public_check
import test_release_worker
import test_release_recovery


class PublicCheckTests(unittest.TestCase):
    setUp = test_release_worker.ReleaseWorkerTests.setUp

    def prepare(self):
        test_release_recovery.ReconciledReleaseTests.schedule_verified(self)
        write_json(self.root / 'channels/sabias-que.json', self.channel)
        write_json(self.root / 'config/profiles' / (self.channel['visual']['profile'] + '.json'), {})
        with Store(self.root / '.runtime/production.sqlite3') as store:
            upload = next(i for i in store.list_intents() if i['action'] == 'upload')
        write_json(self.request, {**self.data, 'action': 'verify_public', 'upload_intent_id': upload['id']})
        refs = [{'path': str(p), 'sha256': file_hash(p)} for p in (self.request, self.master, self.meta, self.qa_path)]
        return {'id': 'public-test', 'job_id': self.job['id'], 'channel_id': 'sabias-que', 'payload': {'inputs': refs}}

    def invoke(self, step, evidence):
        with patch('ecosystem.public_check.browser_command', return_value=(['node'], {})), \
             patch('ecosystem.public_check.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(evidence))), \
             patch('ecosystem.release_worker.datetime', wraps=datetime) as clock, \
             patch('ecosystem.worker.run_stage') as agent:
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(hours=3)
            result = run_public_check(self.root, step)
            agent.assert_not_called()
        return result

    def test_anonymous_evidence_completes_job_without_agent(self):
        step = self.prepare()
        evidence = {'master_sha256': file_hash(self.master), 'account_id': self.account,
                    'url': 'https://www.youtube.com/shorts/abcdefghijk', 'public_verified': True,
                    'evidence': {'method': 'TEST anonymous fixture'}}
        self.assertEqual(self.invoke(step, evidence)['status'], 'ACCEPTED')
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.assertEqual(store.get_job(self.job['id'])['state'], 'complete')

    def test_wrong_account_never_completes_or_reuploads(self):
        step = self.prepare()
        evidence = {'master_sha256': file_hash(self.master), 'account_id': 'wrong',
                    'url': 'https://www.youtube.com/shorts/abcdefghijk', 'public_verified': True,
                    'evidence': 'TEST wrong account'}
        self.assertEqual(self.invoke(step, evidence)['status'], 'UNCERTAIN')
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.assertNotEqual(store.get_job(self.job['id'])['state'], 'complete')
            self.assertEqual(len([i for i in store.list_intents() if i['action'] == 'upload']), 1)
