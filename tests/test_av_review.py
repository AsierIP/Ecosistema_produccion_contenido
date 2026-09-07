import json
import tempfile
import unittest
from pathlib import Path
from ecosystem.av_review import summarize_review
from ecosystem.cache import file_hash
from ecosystem.config import write_json


class AutomatedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master = self.root / 'fixture.test'
        self.master.write_bytes(b'Synthetic fixture, not an actual video')
        self.manifest = {'output': str(self.master), 'caption_transcript': 'Dale like y suscríbete para saber más cosas.'}
        write_json(self.root / 'intent.json', {'state': 'response_saved', 'master_sha256': file_hash(self.master), 'model': 'fixture'})
        report = {'decision': 'PASS', 'audio_observation': 'Fixture audio', 'visual_observation': 'Fixture visual',
                  'caption_observation': 'Fixture captions', 'limitations': 'Fixture sampling', 'defects': []}
        write_json(self.root / 'response.json', {'candidates': [{'finishReason': 'STOP',
                   'content': {'parts': [{'text': json.dumps(report)}]}}]})
        self.asr = self.root / 'asr.json'
        self.words = [{'word': w, 'start': i, 'end': i+1} for i,w in enumerate(self.manifest['caption_transcript'].split())]
        write_json(self.asr, {'words': self.words})

    def test_model_pass_does_not_approve_video_or_hide_missing_speech(self):
        result = summarize_review(self.manifest, self.root, self.asr)
        self.assertTrue(result['literal_speech_match'])
        self.assertFalse(result['production_qa_pass'])
        self.assertFalse(result['human_review'])
        write_json(self.asr, {'words': self.words[:-1]})
        self.assertFalse(summarize_review(self.manifest, self.root, self.asr)['literal_speech_match'])

    def test_changed_master_cannot_reuse_review(self):
        self.master.write_bytes(b'Changed')
        with self.assertRaisesRegex(ValueError, 'another master'):
            summarize_review(self.manifest, self.root, self.asr)

    def test_intro_speech_is_compared_and_does_not_hide_body_omission(self):
        intro = self.root / 'intro.test'
        intro.write_bytes(b'Intro fixture')
        self.manifest['intro'] = str(intro)
        intro_asr = self.root / 'intro-asr.json'
        intro_words = [{'word': w, 'start': 0, 'end': 1} for w in ('Sabías', 'que')]
        write_json(intro_asr, {'words': intro_words})
        write_json(self.asr, {'words': intro_words + self.words})
        self.assertTrue(summarize_review(self.manifest, self.root, self.asr, intro_asr)['literal_speech_match'])
        write_json(self.asr, {'words': intro_words + self.words[:-1]})
        self.assertFalse(summarize_review(self.manifest, self.root, self.asr, intro_asr)['literal_speech_match'])

    def test_truncated_provider_answer_is_not_evidence_ready(self):
        write_json(self.root / 'response.json', {'candidates': [{'finishReason': 'MAX_TOKENS'}]})
        with self.assertRaisesRegex(ValueError, 'truncated'):
            summarize_review(self.manifest, self.root, self.asr)

    def test_text_reviewer_requires_original_automated_evidence(self):
        from ecosystem.worker import quality_preflight
        report = self.root / 'automated-review.json'
        write_json(report, summarize_review(self.manifest, self.root, self.asr))
        technical = self.root / 'technical.json'
        write_json(technical, {'status': 'TECHNICAL_PASS'})
        preflight = self.root / 'preflight.json'
        write_json(preflight, {'kind': 'quality_preflight_v1', 'capabilities': {},
            'automated_evidence': {'path': str(report), 'sha256': file_hash(report)},
            'technical_evidence': {'sha256': file_hash(technical)}})
        paths = [report, technical, preflight, self.master, self.asr, self.root / 'response.json']
        packet = {'review_policy': {'mode': 'automatic'},
                  'inputs': [{'path': str(p), 'sha256': file_hash(p)} for p in paths]}
        self.assertEqual(quality_preflight(packet), [])
        packet['inputs'] = packet['inputs'][:-1]
        self.assertTrue(quality_preflight(packet))
