import json
from pathlib import Path
import tempfile
import unittest
from ecosystem.cache import file_hash
from ecosystem.config import ROOT, read_json, write_json
from ecosystem.final_qa_receipt import seal_completed_native_report
from ecosystem.quality import validate_qa
from test_quality import quality_fixture


class FinalReceiptRecoveryTests(unittest.TestCase):
    def fixture(self, mutate=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        master, qa, _, _ = quality_fixture(root, 'rife_2x_por_segmento')
        video = master.with_suffix('.mp4')
        master.rename(video)
        def ref(p):
            return {'path': str(p), 'sha256': file_hash(p), 'bytes': p.stat().st_size}
        metadata = root / 'metadata.json'
        write_json(metadata, {'title': 'Unit-test fixture'})
        timeline = root / 'timeline.json'
        write_json(timeline, {'kind': 'native_master_timeline_evidence_v1', 'master': ref(video), 'timeline': qa['timeline']})
        qa.update(kind='final_master_qa_v1', decision='ACCEPT', job_id='fixture', channel_id='religion',
                  defects=[], human_review=False, review_method='automated-audiovisual-review',
                  metadata_sha256=file_hash(metadata), caption_profile='early-reels-ivory-gold-v01')
        qa['checks'] = [dict(c, name=name) for name, c in qa['checks'].items()]
        qa['timeline'] = {'mode': 'rife_2x_por_segmento', 'segments': 3, 'input_frames_per_segment': 125,
            'output_frames_per_segment': 250, 'total_output_frames': 750, 'output_fps': 24,
            'voice_speed_factor': 1, 'interpolated_across_cuts': False}
        if mutate:
            mutate(qa)
        report = root / 'qa.json'
        write_json(report, qa)
        events = [
            {'type': 'item.completed', 'item': {'type': 'file_change', 'status': 'completed', 'changes': [{'path': str(report)}]}},
            {'type': 'item.completed', 'item': {'type': 'command_execution', 'exit_code': 0, 'aggregated_output': file_hash(report)}}]
        (root / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events), encoding='utf-8')
        packet = {'role': 'quality', 'channel': {'id': 'religion'}, 'job_id': 'fixture',
            'output_directory': str(root), 'inputs': [ref(video), ref(metadata), ref(timeline)],
            'profile': read_json(ROOT / 'config/profiles/religion-rife-2x-v1.json')}
        return root, packet

    def test_completed_judgment_is_preserved_and_only_format_is_normalized(self):
        root, packet = self.fixture()
        original = (root / 'qa.json').read_bytes()
        receipt = seal_completed_native_report(packet)
        self.assertEqual(receipt['decision'], 'ACCEPT')
        self.assertEqual((root / 'qa-original.json').read_bytes(), original)
        self.assertEqual(validate_qa(read_json(root / 'qa.json'), root / 'master.mp4', packet['profile']), [])
        self.assertEqual(read_json(root / 'qa.json')['checks']['decode']['evidence'], 'unit-test-only evidence contract')
        with self.assertRaises(ValueError):
            seal_completed_native_report(packet)

    def test_missing_failed_or_contradictory_judgment_is_not_recovered(self):
        for mutate in [lambda q: q['checks'][0].update(passed=False),
                       lambda q: q.update(decision='BLOCK'),
                       lambda q: q['timeline'].update(total_output_frames=749)]:
            root, packet = self.fixture(mutate)
            with self.assertRaises(ValueError):
                seal_completed_native_report(packet)
            self.assertFalse((root / 'receipt.json').exists())

    def test_changed_inputs_and_unproven_worker_authorship_are_rejected(self):
        for filename in ['metadata.json', 'events.jsonl']:
            root, packet = self.fixture()
            (root / filename).write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                seal_completed_native_report(packet)
            self.assertFalse((root / 'qa-original.json').exists())
