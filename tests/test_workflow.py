from pathlib import Path
import shutil
import tempfile
import unittest

from ecosystem.config import ROOT, load_channels, write_json, read_json
from ecosystem.cache import file_hash
from ecosystem.corpus import Corpus
from ecosystem.store import Store
from ecosystem.upro_queue import Queue
from ecosystem.workflow import seed_ready_jobs, advance_production


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

    def voice_parent(self):
        brief = self.root / 'production-brief.json'
        write_json(brief, {'kind': 'production_brief_v1', 'channel_id': 'sabias-que',
            'title': 'Fixture only', 'transcript': self.channel['closing']['spoken_text'],
            'sources': [{'locator': 'fixture-page-1'}],
            'scenes': [{'id': f'scene-{i}', 'prompt': f'Fixture visual {i}',
                        'narrative_purpose': f'Fixture beat {i}'} for i in range(4)]})
        request = self.root / 'voice-request.json'
        write_json(request, {'kind': 'voice_generation_v1', 'channel_id': 'sabias-que',
            'brief_path': str(brief), 'brief_sha256': file_hash(brief)})
        parent = self.queue.register({'schema_version': 1, 'job_id': self.job['id'],
            'channel_id': 'sabias-que', 'adapter': 'voice_generate', 'mode': 'production',
            'inputs': [{'path': str(request), 'sha256': file_hash(request)}]})
        self.assertTrue(self.queue.claim(parent))
        audio = self.root / 'audio.test'
        audio.write_bytes(b'Test fixture only, not real audio')
        self.queue.finish(parent, {'status': 'TECHNICAL_PASS', 'path': str(audio),
                                  'sha256': file_hash(audio), 'duration_seconds': 12.0}, 'accepted')
        return parent

    def test_measured_voice_queues_only_needed_scenes_and_restart_is_idempotent(self):
        self.voice_parent()
        self.assertEqual(len(advance_production(self.root, self.queue)), 4)
        scenes = [s for s in self.queue.list() if s['adapter'] == 'visual']
        self.assertEqual(len(scenes), 3)
        self.assertEqual(advance_production(self.root, Queue(self.root)), [])
        requests = [read_json(Path(s['payload']['inputs'][0]['path'])) for s in scenes]
        self.assertEqual({r['scene_id'] for r in requests}, {'scene-0', 'scene-2', 'scene-3'})

    def test_partial_handoff_recovers_missing_scene_requests(self):
        from unittest.mock import patch
        self.voice_parent()
        original = self.queue.register
        calls = 0
        def interrupted(plan):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('Test interrupted handoff')
            return original(plan)
        with patch.object(self.queue, 'register', side_effect=interrupted):
            advance_production(self.root, self.queue)
        self.assertEqual(len([s for s in self.queue.list() if s['adapter'] == 'visual']), 1)
        advance_production(self.root, Queue(self.root))
        self.assertEqual(len([s for s in self.queue.list() if s['adapter'] == 'visual']), 3)
