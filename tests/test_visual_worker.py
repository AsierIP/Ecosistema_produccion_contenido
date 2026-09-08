from pathlib import Path
import tempfile
import unittest
from ecosystem.cache import file_hash
from ecosystem.visual_worker import prepare_intent, seal_receipt, recover_missing_image_paths
from ecosystem.config import write_json


class VisualBookkeepingTests(unittest.TestCase):
    def test_existing_image_review_has_no_generation_intent_and_cannot_substitute_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / 'existing.png'
            image.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            other = root / 'other.png'
            other.write_bytes(image.read_bytes())
            request = root / 'request.json'
            write_json(request, {'kind': 'existing_image_review_v1',
                'source_image': {'path': str(image), 'sha256': file_hash(image)}})
            output = root / 'review'
            output.mkdir()
            packet = {'job_id': 'fixture', 'cache_key': 'fixture', 'output_directory': str(output),
                'inputs': [{'path': str(request), 'sha256': file_hash(request)}, {'path': str(image), 'sha256': file_hash(image)}]}
            prepare_intent(packet)
            self.assertTrue((output / 'visual-review.intent.json').exists())
            self.assertFalse((output / 'imagegen.intent.json').exists())
            with self.assertRaisesRegex(ValueError, 'substitute'):
                seal_receipt({'decision': 'REJECT', 'artifacts': [{'path': str(other)}]}, packet, generated_root=root)

    def test_recovery_requires_one_png_in_exact_completed_thread_and_is_idempotent(self):
        import json
        class FakeQueue:
            def __init__(self, step): self.step, self.plans = step, []
            def list(self): return [self.step]
            def register(self, plan): self.plans.append(plan); return 'followup'
            def retire(self, key, evidence): self.step['state'] = 'reconciled'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = root / 'source.json'
            write_json(request, {'kind': 'image_generation_request_v1', 'scene_id': 'scene', 'image_count': 1})
            write_json(root / 'packet.json', {'job_id': 'job', 'channel': {'id': 'sabias-que'},
                'inputs': [{'path': str(request), 'sha256': file_hash(request)}]})
            write_json(root / 'agent-response.json', {'decision': 'BLOCK', 'artifacts': [], 'blockers': ['No PNG artifact path returned']})
            thread = '11111111-1111-1111-1111-111111111111'
            (root / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in [
                {'type': 'thread.started', 'thread_id': thread}, {'type': 'turn.completed'}]), encoding='utf-8')
            generated = root / 'generated'
            folder = generated / thread
            folder.mkdir(parents=True)
            (folder / 'exec-one.png').write_bytes(b'PNG fixture one')
            (folder / 'exec-two.png').write_bytes(b'PNG fixture two')
            queue = FakeQueue({'id': 'old', 'adapter': 'visual', 'state': 'blocked', 'job_id': 'job', 'channel_id': 'sabias-que',
                'result': {'receipt_path': str(root / 'receipt.json')}, 'payload': {}})
            self.assertEqual(recover_missing_image_paths(root, queue, generated_root=generated), [])
            (folder / 'exec-two.png').unlink()
            self.assertEqual(recover_missing_image_paths(root, queue, generated_root=generated), ['followup'])
            self.assertEqual(recover_missing_image_paths(root, queue, generated_root=generated), [])
            self.assertEqual(len(queue.plans), 1)

    def test_horizontal_reel_is_rejected_before_import(self):
        import struct
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'output'
            output.mkdir()
            source = root / 'landscape.png'
            source.write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 1920, 1080))
            packet = {'output_directory': str(output), 'channel': {'id': 'sabias-que'}}
            with self.assertRaisesRegex(ValueError, 'vertical'):
                seal_receipt({'decision': 'ACCEPT', 'artifacts': [{'path': str(source)}]}, packet, generated_root=root)
            self.assertFalse((output / 'scene.png').exists())

    def test_intent_is_exclusive_and_checks_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'brief.txt'
            source.write_text('approved')
            packet = {'output_directory': tmp, 'job_id': 'test', 'cache_key': 'cache',
                      'inputs': [{'path': str(source), 'sha256': file_hash(source)}]}
            prepare_intent(packet)
            with self.assertRaises(FileExistsError):
                prepare_intent(packet)
            source.write_text('changed')
            with self.assertRaises(ValueError):
                prepare_intent(packet)

    def test_import_hashes_locally_and_preserves_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / 'generated'
            output = root / 'output'
            generated.mkdir(); output.mkdir()
            source = generated / 'scene.png'
            source.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
            packet = {'output_directory': str(output)}
            raw = {'decision': 'REJECT', 'artifacts': [{'path': str(source), 'sha256': '', 'bytes': 0}]}
            result = seal_receipt(raw, packet, generated_root=generated)
            self.assertEqual(result['decision'], 'REJECT')
            self.assertEqual(result['artifacts'][0]['sha256'], file_hash(source))
            self.assertEqual((output / 'scene.png').read_bytes(), source.read_bytes())
            with self.assertRaises(ValueError):
                seal_receipt(raw, packet, generated_root=generated)
            raw['artifacts'][0]['path'] = str(root / 'private.png')
            (root / 'private.png').write_bytes(source.read_bytes())
            with self.assertRaises(ValueError):
                seal_receipt(raw, packet, generated_root=generated)
