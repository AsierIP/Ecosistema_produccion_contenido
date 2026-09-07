from pathlib import Path
import http.client
import json
import shutil
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from ecosystem.config import ROOT
from ecosystem.cache import file_hash
from ecosystem.store import Store
from ecosystem.upro import Controller, Server, InstanceLock
from ecosystem.upro_queue import Queue


class UproTests(unittest.TestCase):
    def test_browser_connection_requires_csrf_and_reuses_live_window(self):
        with patch('ecosystem.browser.open_connection') as launch:
            launch.return_value.poll.return_value = None
            self.assertEqual(self.request('POST', '/api/browser/religion', {})[0], 403)
            launch.assert_not_called()
            headers = {'X-Upro-Token': self.controller.token}
            for _ in range(2):
                self.assertEqual(self.request('POST', '/api/browser/religion', {}, headers)[0], 200)
            launch.assert_called_once_with('religion', root=self.root)

    def test_delayed_step_survives_restart_without_early_claim(self):
        plan = {'schema_version': 1, 'job_id': self.job, 'channel_id': 'religion',
                'adapter': 'media_check', 'mode': 'validation', 'not_before': 2000,
                'inputs': [{'path': str(self.source), 'sha256': file_hash(self.source)}]}
        step = self.queue.register(plan)
        with patch('ecosystem.upro_queue.time.time', return_value=1999):
            self.assertFalse(Queue(self.root).claim(step))
        with patch('ecosystem.upro_queue.time.time', return_value=2000):
            self.assertTrue(Queue(self.root).claim(step))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('config', 'channels', 'prompts'):
            shutil.copytree(ROOT / name, self.root / name)
        self.source = self.root / 'sample.mp4'
        self.source.write_bytes(b'fixture-only')
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.job = store.enqueue_job('religion', '2026-09-05')['id']
        self.queue = Queue(self.root)
        self.executor = Mock(return_value=({'ok': True}, 'accepted'))
        self.controller = Controller(self.root, executor=self.executor)
        self.server = Server(('127.0.0.1', 0), self.controller)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.controller.close()
        self.thread.join()
        self.tmp.cleanup()

    def plan(self, **changes):
        return {'schema_version': 1, 'job_id': self.job, 'channel_id': 'religion', 'adapter': 'media_check', 'mode': 'validation', 'inputs': [{'path': str(self.source), 'sha256': file_hash(self.source)}], **changes}

    def request(self, method, path, data=None, headers=None):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else None
        merged = {'Content-Type': 'application/json', **(headers or {})}
        con.request(method, path, body=body, headers=merged)
        response = con.getresponse()
        result = response.status, response.read()
        con.close()
        return result

    def test_concurrent_claim_has_one_winner_and_restart_is_uncertain(self):
        key = self.queue.register(self.plan())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.queue.claim(key), range(8)))
        self.assertEqual(sum(results), 1)
        self.queue.recover()
        self.assertEqual(self.queue.list()[0]['state'], 'uncertain')
        self.assertFalse(self.queue.claim(key))

    def test_registration_idempotent_and_dependency_waits(self):
        first = self.queue.register(self.plan())
        self.assertEqual(first, self.queue.register(self.plan()))
        second = self.queue.register(self.plan(depends_on=[first]))
        self.assertFalse(self.queue.claim(second))
        self.assertTrue(self.queue.claim(first))
        self.queue.finish(first, {}, 'accepted')
        self.assertTrue(self.queue.claim(second))

    def test_production_readiness_blocks_executor(self):
        self.queue.register(self.plan(mode='production'))
        self.controller.tick()
        self.executor.assert_not_called()
        self.assertEqual(self.queue.list()[0]['state'], 'queued')

    def test_validation_can_run_without_production_activation(self):
        self.queue.register(self.plan())
        self.controller.tick()
        for active in list(self.controller.active.values()):
            active['future'].result(timeout=3)
        self.executor.assert_called_once()
        self.assertEqual(self.queue.list()[0]['state'], 'accepted')

    def test_controls_persist_without_bypassing_locked_line(self):
        self.controller.set_line('religion', False)
        self.controller.set_paused(True)
        other = Controller(self.root, executor=self.executor)
        try:
            self.assertFalse(other.enabled('religion'))
            self.assertTrue(other.controls['paused'])
            for line in other.settings.get('extra_lines', []):
                if line.get('locked'):
                    with self.assertRaises(ValueError):
                        other.set_line(line['id'], True)
        finally:
            other.close()

    def test_polling_does_not_execute_or_consume_tokens(self):
        self.queue.register(self.plan())
        with patch('ecosystem.worker.run_stage') as agent:
            for _ in range(3):
                self.assertEqual(self.request('GET', '/api/status')[0], 200)
        agent.assert_not_called()
        self.executor.assert_not_called()
        self.assertEqual(self.queue.list()[0]['state'], 'queued')

    def test_http_origin_host_and_csrf(self):
        self.assertEqual(self.request('GET', '/api/status', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/status', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/control', {'paused': True})[0], 403)
        token = {'X-Upro-Token': self.controller.token}
        self.assertEqual(self.request('POST', '/api/control', {'paused': True}, {**token, 'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/control', {'paused': True}, token)[0], 200)
        self.assertTrue(self.controller.controls['paused'])
        self.assertEqual(self.request('POST', '/api/control', {'paused': 'false'}, token)[0], 400)

    def test_media_paths_not_http_inputs_and_changed_media_rejected(self):
        for path in ('/api/media/../../sample.mp4', '/api/media/C:/Windows/win.ini', '/api/media/%2e%2e%2fsample.mp4'):
            self.assertEqual(self.request('GET', path)[0], 404)
        key = self.queue.register(self.plan())
        self.queue.claim(key)
        self.queue.finish(key, {'path': str(self.source), 'master_sha256': file_hash(self.source)}, 'accepted')
        self.assertEqual(self.request('GET', '/api/media/' + key)[0], 200)
        self.source.write_bytes(b'changed')
        self.assertEqual(self.request('GET', '/api/media/' + key)[0], 404)

    def test_uncertain_job_blocks_other_queued_work(self):
        first = self.queue.register(self.plan())
        self.queue.claim(first)
        self.queue.recover()
        self.queue.register(self.plan(marker="second"))
        self.controller.tick()
        self.executor.assert_not_called()
        self.assertEqual([s['state'] for s in self.queue.list()], ['uncertain', 'queued'])

    def test_http_media_range_and_invalid_range(self):
        key = self.queue.register(self.plan())
        self.queue.claim(key)
        self.queue.finish(key, {'path': str(self.source), 'master_sha256': file_hash(self.source)}, 'accepted')
        status, body = self.request('GET', '/api/media/' + key, headers={'Range': 'bytes=0-2'})
        self.assertEqual((status, body), (206, b'fix'))
        self.assertEqual(self.request('GET', '/api/media/' + key, headers={'Range': 'bytes=999-1000'})[0], 416)

    def test_retire_never_replays_old_step_and_allows_new_plan(self):
        for state in ('blocked', 'uncertain'):
            with self.subTest(state=state):
                old_plan = self.plan(marker=state)
                old = self.queue.register(old_plan)
                self.assertTrue(self.queue.claim(old))
                self.queue.finish(old, {'reason': 'fixture'}, state)
                with self.assertRaises(ValueError):
                    self.queue.retire(old, {'checked': False, 'reason': 'inspected'})
                self.queue.retire(old, {'checked': True, 'reason': 'inspected; old operation will not be retried'})
                self.assertEqual(old, self.queue.register(old_plan))
                self.assertFalse(self.queue.claim(old))
                new = self.queue.register(self.plan(marker=state + '-corrected'))
                self.assertNotEqual(old, new)
                self.assertTrue(self.queue.claim(new))
                self.queue.finish(new, {}, 'accepted')

    def test_duplicate_instance_lock_and_release(self):
        first, second = InstanceLock(self.root), InstanceLock(self.root)
        first.acquire()
        try:
            with self.assertRaises(RuntimeError):
                second.acquire()
        finally:
            first.close()
        second.acquire()
        second.close()

    def test_completed_render_handoff_survives_restart_without_rerender(self):
        key = self.queue.register(self.plan(adapter='cutout', mode='production'))
        self.assertTrue(self.queue.claim(key))
        self.queue.finish(key, {'status': 'TECHNICAL_PASS', 'output_path': str(self.source),
                                'sha256': file_hash(self.source)}, 'accepted')
        reopened = Queue(self.root)
        new = reopened.advance_completed_renders()
        self.assertEqual(len(new), 1)
        self.assertEqual(reopened.advance_completed_renders(), [])
        followup = reopened.list()[-1]
        self.assertEqual(followup['adapter'], 'media_check')
        self.assertEqual(followup['mode'], 'validation')
        self.assertEqual(followup['payload']['depends_on'], [key])
        self.assertEqual(reopened.list()[0]['state'], 'accepted')

    def test_changed_render_never_promoted_to_inspection(self):
        key = self.queue.register(self.plan(adapter='cutout', mode='production'))
        self.queue.claim(key)
        self.queue.finish(key, {'status': 'TECHNICAL_PASS', 'output_path': str(self.source),
                                'sha256': file_hash(self.source)}, 'accepted')
        self.source.write_bytes(b'replaced')
        self.assertEqual(self.queue.advance_completed_renders(), [])

    def test_activity_survives_restart_and_partial_last_record(self):
        self.controller.event('Etapa comprobada', line_id='religion')
        with (self.controller.runtime / 'activity.jsonl').open('a') as stream:
            stream.write('{incomplete')
        self.assertEqual(self.controller.load_activity()[-1]['message'], 'Etapa comprobada')


if __name__ == '__main__':
    unittest.main()
