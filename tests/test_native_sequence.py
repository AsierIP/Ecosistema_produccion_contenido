from pathlib import Path
import tempfile
import unittest
from ecosystem.config import write_json, read_json
from ecosystem.native_batch import ref
from ecosystem.native_sequence import advance_sequence, retry_prompt
from ecosystem.vibes import validate_request


class QueueFixture:
    def __init__(self):
        self.plans = []
    def list(self):
        return [{'id': 'stage', 'payload': p, **p} for p in self.plans]
    def register(self, plan):
        self.plans.append(plan)
        return 'stage'


class NativeSequenceTests(unittest.TestCase):
    def test_retry_does_not_accumulate_review_instructions(self):
        base = 'Keep the walk, handover, emotional reaction and camera move.'
        result = retry_prompt(base, ['Require an exact 3 cm gap'] * 100)
        self.assertTrue(result.startswith(base))
        self.assertNotIn('3 cm', result)
        self.assertLess(len(result) - len(base), 700)
        self.assertIn('receiver establishes support before the giver releases', result)
        self.assertEqual(retry_prompt(base, []), base)

    def fixture(self, root):
        frame = root / 'start.png'
        frame.write_bytes(b'canonical pixels')
        prompt = root / 'prompt.txt'
        prompt.write_text('Canonical action')
        creative = root / 'creative.json'
        write_json(creative, {'sequence_id': 'sequence', 'canonical_narration_text': 'Narration', 'segments': [
            {'segment_id': s, 'continuity_from': previous, 'state': {}, 'provider_prompt': {
                'provider_prompt_file_path': str(prompt), 'provider_prompt_file_sha256': ref(prompt)['sha256']}}
            for s, previous in [('s01', None), ('s02', 's01'), ('s03', 's02')]]})
        contract = root / 'contract.json'
        write_json(contract, {'source_batch': 's01-b01'})
        spec = root / 'sequence.json'
        write_json(spec, {'kind': 'native_sequence_v1', 'channel_id': 'religion', 'job_id': 'job', 'mode': 'canary',
            'sequence_id': 'sequence', 'creative': ref(creative), 'contract': ref(contract), 'start_reference': ref(frame),
            'inputs': [ref(creative), ref(contract), ref(frame)], 'native_root': str(root / 'media'),
            'project_title': 'Project', 'project_url': 'https://vibes.ai/projects/1234'})
        return spec, frame, contract

    def test_continuation_uses_exact_accepted_frame_and_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec, frame, contract = self.fixture(root)
            quality = root / 'quality.json'
            write_json(quality, {'decision': 'PASS'})
            selection = root / 'selection.json'
            write_json(selection, {'decision': 'ACCEPT', 'job_id': 'job', 'sequence_id': 'sequence', 'segment_id': 's01',
                'native_last_frame': {'path': str(frame), 'file_sha256': ref(frame)['sha256'], 'accepted_at': 'timestamp',
                'quality_receipt_path': str(quality), 'quality_receipt_sha256': ref(quality)['sha256']}})
            batch = root / '.runtime/upro/native-batches/first/batch.json'
            write_json(batch, {'job_id': 'job', 'segment_id': 's01', 'contract': ref(contract)})
            write_json(batch.parent / 'state.json', {'batch_sha256': ref(batch)['sha256'], 'status': 'ACCEPTED', 'selected': ref(selection)})
            queue = QueueFixture()
            advance_sequence(root, queue, spec)
            request = read_json(Path(next(p for p in queue.plans if p['adapter'] == 'vibes_generate')['inputs'][0]['path']))
            self.assertEqual(request['segment_id'], 's02')
            self.assertEqual(Path(request['start_reference']['path']).read_bytes(), frame.read_bytes())
            validate_request(request)
            advance_sequence(root, queue, spec)
            self.assertEqual(len(queue.plans), 2)
            frame.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                validate_request(request)

    def test_exhaustion_does_not_create_a_fourth_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec, _, _ = self.fixture(root)
            for number in range(1, 4):
                base = root / '.runtime/upro/native-batches' / str(number)
                contract = base / 'contract.json'
                write_json(contract, {'source_batch': f's01-b{number:02}'})
                batch = base / 'batch.json'
                write_json(batch, {'job_id': 'job', 'segment_id': 's01', 'contract': ref(contract)})
                write_json(base / 'state.json', {'batch_sha256': ref(batch)['sha256'], 'status': 'EXHAUSTED', 'candidates': {}})
            queue = QueueFixture()
            advance_sequence(root, queue, spec)
            self.assertEqual([p for p in queue.plans if p['adapter'] == 'vibes_generate'], [])
            self.assertEqual(read_json(root / 'status.json')['status'], 'REPLAN_REQUIRED')
