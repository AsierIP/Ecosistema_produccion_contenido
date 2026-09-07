import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ecosystem.config import write_json
from ecosystem.cache import file_hash
from ecosystem.segment_review import run_segment_review, validate_native_preflight


class SegmentReviewTests(unittest.TestCase):
    def test_reconciles_bound_review_without_resending(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / 'segment.mp4'
            video.write_bytes(b'fixture only')
            manifest = root / 'manifest.json'
            write_json(manifest, {'kind': 'native_segment_review_v1', 'output': str(video)})
            provider = root / 'prior'
            write_json(provider / 'intent.json', {'state': 'response_saved', 'review_kind': 'Segment',
                       'master_sha256': file_hash(video), 'model': 'fixture'})
            write_json(provider / 'cleanup.json', {'deleted': True})
            write_json(provider / 'response.json', {'candidates': [{'finishReason': 'STOP',
                       'content': {'parts': [{'text': json.dumps({'decision': 'PASS'})}]}}]})
            request = root / 'request.json'
            refs = [manifest, video, *(provider / n for n in ('intent.json', 'cleanup.json', 'response.json'))]
            write_json(request, {'kind': 'segment_review_request_v1', 'channel_id': 'religion',
                       'manifest_path': str(manifest), 'prior_review': str(provider),
                       'inputs': [{'path': str(p), 'sha256': file_hash(p)} for p in refs]})
            with patch('ecosystem.segment_review.subprocess.run') as remote:
                result = run_segment_review(request, root / 'out', root=root)
                self.assertEqual(result['status'], 'EVIDENCE_READY')
                self.assertTrue(result['independent_quality_pending'])
                remote.assert_not_called()
                technical = root / 'technical.json'
                write_json(technical, {'status': 'TECHNICAL_PASS', 'master_sha256': file_hash(video)})
                quality_paths = [video, Path(result['path']), provider / 'response.json', technical]
                packet = {'channel': {'id': 'religion'}, 'review_policy': {'mode': 'automatic'},
                          'inputs': [{'path': str(p), 'sha256': file_hash(p)} for p in quality_paths]}
                preflight = {'master_path': str(video), 'unit_id': 'native:s01:c01',
                             'automated_evidence': {'path': result['path']}, 'technical_evidence': {'path': str(technical)}}
                self.assertEqual(validate_native_preflight(packet, preflight), [])
                packet['channel']['id'] = 'sabias-que'
                self.assertTrue(validate_native_preflight(packet, preflight))
                video.write_bytes(b'replacement')
                with self.assertRaisesRegex(ValueError, 'input changed'):
                    run_segment_review(request, root / 'out', root=root)
                remote.assert_not_called()
