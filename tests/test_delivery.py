from pathlib import Path
from types import SimpleNamespace
from ecosystem.cache import file_hash
from ecosystem.config import write_json, read_json
from ecosystem.delivery import advance_delivery
import unittest
import test_release_worker


class DeliveryTests(unittest.TestCase):
    setUp = test_release_worker.ReleaseWorkerTests.setUp
    def review_step(self):
        folder = self.root / 'review'
        qa_path = folder / 'qa.json'
        self.qa['metadata_sha256'] = file_hash(self.meta)
        write_json(qa_path, self.qa)
        refs = [{'path': str(p), 'sha256': file_hash(p), 'bytes': p.stat().st_size}
                for p in (self.master, self.meta)]
        packet = {**self.packet, 'role': 'quality', 'inputs': refs, 'output_directory': str(folder)}
        write_json(folder / 'packet.json', packet)
        receipt = {'job_id': self.job['id'], 'role': 'quality', 'decision': 'ACCEPT',
                   'inputs_reviewed': refs, 'blockers': [],
                   'checks': [{'passed': True, 'evidence': 'Synthetic test only'}],
                   'artifacts': [{'path': str(qa_path), 'sha256': file_hash(qa_path), 'bytes': qa_path.stat().st_size}]}
        write_json(folder / 'receipt.json', receipt)
        step = {'id': 'review', 'job_id': self.job['id'], 'channel_id': 'sabias-que',
                'adapter': 'quality', 'mode': 'production', 'state': 'accepted',
                'result': {'receipt_path': str(folder / 'receipt.json')}, 'payload': {}}
        steps = [step]
        def register(plan):
            steps.append({'id': 'upload', 'adapter': 'release', 'payload': plan})
            return 'upload'
        return SimpleNamespace(list=lambda: steps, register=register)

    def test_review_handoff_resumes_once_without_uploading(self):
        queue = self.review_step()
        self.assertEqual(advance_delivery(self.root, queue), ['upload'])
        self.assertEqual(advance_delivery(self.root, queue), [])
        plan = queue.list()[-1]['payload']
        request = read_json(Path(plan['inputs'][0]['path']))
        self.assertEqual(request['action'], 'upload')
        self.assertEqual(request['expected_account_id'], self.account)
        self.assertEqual(plan['depends_on'], ['review'])

    def test_changed_description_cannot_be_delivered(self):
        queue = self.review_step()
        write_json(self.meta, {'title': 'Changed', 'description': 'Changed'})
        self.assertEqual(advance_delivery(self.root, queue), [])
        error = self.root / '.runtime/jobs' / self.job['id'] / 'handoffs/error-delivery-review.json'
        self.assertEqual(read_json(error)['status'], 'blocked')

    def test_missing_independent_qa_cannot_be_delivered(self):
        queue = self.review_step()
        self.qa['checks']['independent_review']['passed'] = False
        report = self.root / 'review/qa.json'
        write_json(report, self.qa)
        receipt_path = self.root / 'review/receipt.json'
        receipt = read_json(receipt_path)
        receipt['artifacts'][0].update(sha256=file_hash(report), bytes=report.stat().st_size)
        write_json(receipt_path, receipt)
        self.assertEqual(advance_delivery(self.root, queue), [])
