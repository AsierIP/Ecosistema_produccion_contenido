from pathlib import Path
import shutil
import tempfile
import unittest

from ecosystem.config import ROOT, load_channels, write_json
from ecosystem.corpus import Corpus
from ecosystem.store import Store
from ecosystem.upro_queue import Queue
from ecosystem.workflow import seed_ready_jobs


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'channels', self.root / 'channels')
        self.channel = next(c for c in load_channels(self.root) if c['id'] == 'sabias-que')
        self.source = self.root / 'fixture-book.txt'
        self.source.write_text('\n'.join(f'Pasaje de prueba número {i}. ' + ('Contenido de prueba. ' * 10) for i in range(9)), encoding='utf-8')
        self.source_id = self.channel['sources'][0]['id']
        write_json(self.root / 'local.json', {'channels': {'sabias-que': {'source_paths': {self.source_id: str(self.source)}}}})
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.job = store.enqueue_job('sabias-que', '2026-09-07')
        self.plan = {'channels': [{'channel_id': 'sabias-que', 'job_id': self.job['id'], 'ready': True}]}
        self.queue = Queue(self.root)

    def test_startup_seeds_once_and_restart_keeps_selection(self):
        self.assertEqual(len(seed_ready_jobs(self.root, self.plan, self.queue)), 1)
        original = self.queue.list()
        self.assertEqual(original[0]['adapter'], 'creative')
        self.assertEqual(seed_ready_jobs(self.root, self.plan, Queue(self.root)), [])
        self.assertEqual(original, Queue(self.root).list())

    def test_unready_job_is_not_started(self):
        self.plan['channels'][0]['ready'] = False
        self.assertEqual(seed_ready_jobs(self.root, self.plan, self.queue), [])
        self.assertEqual(self.queue.list(), [])

    def test_distinct_jobs_reserve_distinct_candidates(self):
        corpus = Corpus(self.root / '.runtime/corpus.sqlite3')
        corpus.index(self.source_id, self.source)
        first = corpus.reserve(self.source_id, 'sabias-que', 'first')
        second = corpus.reserve(self.source_id, 'sabias-que', 'second')
        self.assertFalse({p['locator'] for p in first} & {p['locator'] for p in second})
        self.assertEqual(first, Corpus(corpus.database).reserve(self.source_id, 'sabias-que', 'first'))
        self.source.write_text('Source changed. ' * 100, encoding='utf-8')
        corpus.index(self.source_id, self.source)
        with self.assertRaises(ValueError):
            corpus.reserve(self.source_id, 'sabias-que', 'first')
