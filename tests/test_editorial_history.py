import tempfile
import unittest
from pathlib import Path

from ecosystem.cache import file_hash
from ecosystem.config import write_json
from ecosystem.editorial_history import creative_context_preflight


class EditorialHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.evidence = self.root / 'observed.txt'
        self.evidence.write_text('Published topic', encoding='utf-8')
        self.pack = self.root / 'pack.json'
        self.value = {
            'kind': 'editorial_source_candidates_v1', 'job_id': 'job',
            'channel_id': 'channel', 'sources': ['book'], 'candidates': ['passage'],
            'editorial_history': {
                'channel_id': 'channel', 'account_id': 'youtube-account',
                'scope': 'complete observed list', 'topics': ['Published topic'],
                'source_evidence': {'path': str(self.evidence), 'sha256': file_hash(self.evidence)},
            },
        }
        self.packet = {'job_id': 'job', 'channel': {'id': 'channel',
            'platforms': {'youtube': {'channel_id': 'youtube-account'}}},
            'inputs': [{'path': str(self.pack)}]}

    def check(self):
        write_json(self.pack, self.value)
        return creative_context_preflight(self.packet)

    def test_complete_context_uses_fixed_bounded_unit(self):
        self.assertEqual(self.check(), 'editorial-context-v1')

    def test_missing_history_rejected_before_worker(self):
        del self.value['editorial_history']
        with self.assertRaises(ValueError):
            self.check()

    def test_other_account_rejected(self):
        self.value['editorial_history']['account_id'] = 'another-account'
        with self.assertRaises(ValueError):
            self.check()

    def test_changed_observation_rejected(self):
        self.evidence.write_text('Changed', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.check()

    def test_empty_topic_rejected(self):
        self.value['editorial_history']['topics'] = [' ']
        with self.assertRaises(ValueError):
            self.check()

    def test_different_job_rejected(self):
        self.value['job_id'] = 'other-job'
        with self.assertRaises(ValueError):
            self.check()
