import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from ecosystem.cache import file_hash
from ecosystem.config import ROOT
from ecosystem.store import Store
from ecosystem.worker import collect_usage, run_stage, subscription_environment, visual_preflight


class WorkerBoundaryTests(unittest.TestCase):
    def test_subscription_workers_strip_api_key_overrides(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'fixture', 'CODEX_API_KEY': 'fixture', 'UPRO_TEST': 'kept'}):
            env = subscription_environment()
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('CODEX_API_KEY', env)
        self.assertEqual(env['UPRO_TEST'], 'kept')

    def test_visual_preflight_rejects_cross_channel_and_unbounded_work(self):
        request = self.root / 'image-request.json'
        packet = {'channel': {'id': 'sabias-que', 'visual': {'generation_provider': 'imagegen', 'approved': True}},
                  'inputs': [{'path': str(request)}]}
        valid = {'kind': 'image_generation_request_v1', 'channel_id': 'sabias-que', 'scene_id': 'scene-01', 'image_count': 1,
                 'prompt': 'Approved visual brief', 'source_basis': 'Source pack'}
        for change in ({'channel_id': 'religion'}, {'image_count': 4}, {'source_basis': ''}):
            request.write_text(json.dumps({**valid, **change}), encoding='utf-8')
            self.assertTrue(visual_preflight(packet))
        request.write_text(json.dumps(valid), encoding='utf-8')
        self.assertEqual(visual_preflight(packet), [])
        packet['channel']['visual']['generation_provider'] = 'vibes'
        self.assertTrue(visual_preflight(packet))

    def test_visual_attempt_limit_is_per_scene_not_entire_reel(self):
        with Store(self.root / '.runtime/production.sqlite3') as store:
            job = store.enqueue_job('sabias-que', '2026-09-07')['id']
        request = self.root / 'image-request.json'
        def run(scene, prompt):
            request.write_text(json.dumps({'kind': 'image_generation_request_v1',
                'channel_id': 'sabias-que', 'scene_id': scene, 'image_count': 1,
                'prompt': prompt, 'source_basis': 'approved source'}), encoding='utf-8')
            return run_stage(job, 'visual', [request], root=self.root, execute=True)
        with patch('ecosystem.worker.subprocess.run') as process:
            process.return_value.returncode = 1
            run('scene-01', 'first')
            run('scene-01', 'corrected')
            exhausted = run('scene-01', 'third')
            self.assertIn('agotado', exhausted['reason'])
            run('scene-02', 'different scene')
            self.assertEqual(process.call_count, 3)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('channels', 'config', 'prompts'):
            shutil.copytree(ROOT / name, self.root / name)
        with Store(self.root / '.runtime/production.sqlite3') as store:
            self.job = store.enqueue_job('religion', '2026-09-07')['id']

    def tearDown(self):
        self.temp.cleanup()

    def quality_inputs(self, capabilities, report=None, hash_value=None):
        technical = self.root / 'technical.json'
        technical.write_text(json.dumps(report), encoding='utf-8')
        manifest = self.root / 'preflight.json'
        manifest.write_text(json.dumps({'kind': 'quality_preflight_v1', 'capabilities': capabilities, 'technical_evidence': {'sha256': file_hash(technical) if hash_value is None else hash_value}}), encoding='utf-8')
        return [manifest, technical]

    def test_malformed_capabilities_block_without_agent(self):
        for capabilities in (None, [], 'yes', False):
            with self.subTest(capabilities=capabilities), patch('ecosystem.worker.subprocess.run') as process:
                result = run_stage(self.job, 'quality', self.quality_inputs(capabilities), root=self.root, execute=True)
                self.assertEqual(result['status'], 'BLOCKED')
                process.assert_not_called()

    def test_malformed_report_or_hash_block_without_agent(self):
        caps = {'full_video_playback': True, 'full_audio_playback': True}
        for report, sha in ((None, None), ([], None), ({'status': 'TECHNICAL_PASS'}, [])):
            with self.subTest(report=report, sha=sha), patch('ecosystem.worker.subprocess.run') as process:
                result = run_stage(self.job, 'quality', self.quality_inputs(caps, report, sha), root=self.root, execute=True)
                self.assertEqual(result['status'], 'BLOCKED')
                process.assert_not_called()

    def test_usage_ignores_nonobjects_partial_and_invalid_counts(self):
        events = self.root / 'events.jsonl'
        rows = [None, [], {'type': 'turn.completed', 'usage': {'input_tokens': 12, 'cached_input_tokens': 5, 'output_tokens': True}}, {'type': 'turn.completed', 'usage': {'input_tokens': 3, 'output_tokens': 2, 'cached_input_tokens': -1}}]
        events.write_text('\n'.join(json.dumps(row) for row in rows) + '\n{partial', encoding='utf-8')
        self.assertEqual(collect_usage(events), {'input_tokens': 15, 'output_tokens': 2, 'cached_input_tokens': 5})

    def test_timeout_accounts_usage_and_is_not_retried(self):
        source = self.root / 'source.json'
        source.write_text('{}')
        def timeout(*args, **kwargs):
            kwargs['stdout'].write(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 10, 'output_tokens': 2, 'cached_input_tokens': 3}}) + '\n')
            raise subprocess.TimeoutExpired('fixture', 1)
        with patch('ecosystem.worker.subprocess.run', side_effect=timeout) as process:
            result = run_stage(self.job, 'creative', [source], root=self.root, execute=True)
            retry = run_stage(self.job, 'creative', [source], root=self.root, execute=True)
        self.assertEqual(result['status'], 'UNCERTAIN')
        self.assertEqual(result['usage']['input_tokens'], 10)
        self.assertEqual(retry['status'], 'ALREADY_RECORDED')
        self.assertEqual(process.call_count, 1)

    def test_accepted_cache_revalidates_changed_output_without_agent(self):
        from ecosystem.dispatch import build_packet
        source = self.root / 'source.json'
        source.write_text('{}')
        packet = build_packet(self.job, 'creative', [source], root=self.root)
        output = Path(packet['receipt_path']).parent / 'script.txt'
        output.write_text('approved content', encoding='utf-8')
        receipt = {'job_id': self.job, 'role': 'creative', 'decision': 'ACCEPT',
                   'artifacts': [{'path': str(output), 'sha256': file_hash(output), 'bytes': output.stat().st_size}],
                   'checks': [{'name': 'source', 'passed': True, 'evidence': 'fixture reviewed'}], 'blockers': []}
        def accept(*args, **kwargs):
            Path(packet['receipt_path']).write_text(json.dumps(receipt), encoding='utf-8')
            return subprocess.CompletedProcess(args[0], 0)
        with patch('ecosystem.worker.subprocess.run', side_effect=accept) as process:
            first = run_stage(self.job, 'creative', [source], root=self.root, execute=True)
            intact = run_stage(self.job, 'creative', [source], root=self.root, execute=True)
            output.write_text('tampered content', encoding='utf-8')
            changed = run_stage(self.job, 'creative', [source], root=self.root, execute=True)
        self.assertEqual(first['status'], 'ACCEPTED')
        self.assertEqual(intact['status'], 'ALREADY_RECORDED')
        self.assertEqual(changed['status'], 'BLOCKED')
        self.assertFalse(changed['agent_started'])
        self.assertIn('artifact hash or size mismatch', changed['errors'])
        self.assertEqual(process.call_count, 1)


if __name__ == '__main__':
    unittest.main()
