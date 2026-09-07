from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ecosystem.config import write_json
from ecosystem.native_batch import ref
from ecosystem.native_conform import accepted_source, conform, CHECKS


class NativeConformTests(unittest.TestCase):
    def test_rejected_clip_never_reaches_gpu(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            selection = root / 'selection.json'
            write_json(selection, {'decision': 'REJECT'})
            request = root / 'request.json'
            write_json(request, {'kind': 'native_conform_v1', 'channel_id': 'religion', 'selection': ref(selection)})
            with patch('ecosystem.rife.conform_segment') as gpu:
                with self.assertRaisesRegex(ValueError, 'independent native acceptance'):
                    conform(request, root=root)
                gpu.assert_not_called()

    def test_acceptance_requires_every_check_and_unchanged_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'clip.mp4'
            source.write_bytes(b'fixture')
            frame = root / 'last.png'
            frame.write_bytes(b'frame')
            visual = root / 'visual.json'
            report = {'decision': 'PASS', 'candidate_sha256': ref(source)['sha256'],
                      'reviewer': {'role': 'quality', 'model': 'gpt-5.6-sol', 'reasoning_effort': 'medium', 'independent': True},
                      'claims': dict.fromkeys(CHECKS, True)}
            write_json(visual, report)
            selection = root / 'selection.json'
            value = {'decision': 'ACCEPT', 'defects': [], 'candidate': ref(source),
                     'visual_review_receipt_path': str(visual), 'visual_review_receipt_sha256': ref(visual)['sha256'],
                     'native_last_frame': {'path': str(frame), 'file_sha256': ref(frame)['sha256'], 'frame_index': 124,
                      'source_mp4_sha256': ref(source)['sha256'], 'quality_receipt_sha256': ref(visual)['sha256'], 'accepted_at': 'stamp'}}
            write_json(selection, value)
            self.assertEqual(accepted_source(ref(selection))[1], source)
            frame.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'endpoint'):
                accepted_source(ref(selection))
            report['claims']['exit_state_achieved'] = False
            write_json(visual, report)
            value['visual_review_receipt_sha256'] = ref(visual)['sha256']
            write_json(selection, value)
            with self.assertRaisesRegex(ValueError, 'mandatory check'):
                accepted_source(ref(selection))
