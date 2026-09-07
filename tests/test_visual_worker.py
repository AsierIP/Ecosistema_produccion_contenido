from pathlib import Path
import tempfile
import unittest
from ecosystem.cache import file_hash
from ecosystem.visual_worker import prepare_intent, seal_receipt


class VisualBookkeepingTests(unittest.TestCase):
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
