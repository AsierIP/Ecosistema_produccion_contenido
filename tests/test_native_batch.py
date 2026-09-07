from pathlib import Path
import tempfile
import unittest
from ecosystem.config import write_json, read_json
from ecosystem.native_batch import advance_batch, ref


class FakeQueue:
    def __init__(self):
        self.steps = []

    def list(self):
        return self.steps

    def register(self, plan):
        for step in self.steps:
            if step.get('payload') == plan:
                return step['id']
        key = str(len(self.steps))
        self.steps.append({'id': key, 'payload': plan, 'state': 'queued', **plan})
        return key


class NativeBatchTests(unittest.TestCase):
    def fixture(self, root):
        paths = []
        for name in ('one.mp4', 'two.mp4', 'contract.json', 'manifest.json', 'start.png'):
            path = root / name
            path.write_text('{}')
            paths.append(path)
        batch = {'kind': 'native_candidate_batch_v1', 'channel_id': 'religion', 'job_id': 'job', 'mode': 'canary',
                 'candidates': [ref(p) for p in paths[:2]], 'contract': ref(paths[2]),
                 'review_manifest': ref(paths[3]), 'start_reference': ref(paths[4])}
        path = root / 'batch.json'
        write_json(path, batch)
        return path, batch

    def test_waits_for_first_candidate_and_does_not_duplicate_on_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, batch = self.fixture(root)
            queue = FakeQueue()
            advance_batch(root, queue, path)
            advance_batch(root, queue, path)
            self.assertEqual(len(queue.steps), 1)
            self.assertEqual(queue.steps[0]['inputs'][0], batch['candidates'][0])
            Path(batch['candidates'][1]['path']).write_text('changed')
            with self.assertRaisesRegex(ValueError, 'input changed'):
                advance_batch(root, queue, path)

    def test_only_bound_rejection_advances_and_acceptance_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path, batch = self.fixture(root)
            batch['candidates'][0]['existing_quality_step'] = 'prior'
            write_json(path, batch)
            selection_path = root / 'native-selection.json'
            selection = {'decision': 'REJECT', 'job_id': 'job', 'candidate': {'sha256': batch['candidates'][0]['sha256']}}
            write_json(selection_path, selection)
            queue = FakeQueue()
            queue.steps.append({'id': 'prior', 'job_id': 'job', 'adapter': 'segment_quality', 'state': 'reconciled',
                'result': {'reconciliation': {'selection_path': str(selection_path), 'selection_sha256': ref(selection_path)['sha256']}}})
            advance_batch(root, queue, path)
            self.assertEqual(queue.steps[-1]['inputs'][0], batch['candidates'][1])
            # Start a new batch with the same accepted first candidate: no second inspection.
            (root / 'state.json').unlink()
            queue.steps = queue.steps[:1]
            selection['decision'] = 'ACCEPT'
            write_json(selection_path, selection)
            queue.steps[0].update(state='accepted', result={'receipt_path': str(root / 'receipt.json')})
            state = advance_batch(root, queue, path)
            self.assertEqual(state['status'], 'ACCEPTED')
            self.assertEqual(len(queue.steps), 1)


if __name__ == '__main__':
    unittest.main()
