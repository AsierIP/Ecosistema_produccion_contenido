from pathlib import Path
import tempfile
import unittest
from ecosystem.religion_captions import build_religion_captions
from ecosystem.config import read_json


class ReligionCaptionTests(unittest.TestCase):
    def test_literal_text_uses_frozen_ivory_gold_style_and_local_word_times(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'captions.ass'
            text = 'Una persona comparte pan sin anunciar su gesto.'
            words = [{'word': word, 'start': .2 + i / 2, 'end': .6 + i / 2}
                     for i, word in enumerate(text.split())]
            result = build_religion_captions(text, words, path, duration=5)
            ass = path.read_text(encoding='utf-8-sig')
            cues = read_json(path.with_suffix('.json'))['cues']
            self.assertEqual(' '.join(c['text'] for c in cues), text)
            self.assertEqual(cues[0]['start'], .2)
            self.assertEqual(cues[-1]['end'], words[-1]['end'])
            self.assertEqual(ass.count('Dialogue:'), 2 * len(cues))
            self.assertIn('Segoe UI Semibold,39,&H00E8F7FF', ass)
            self.assertIn(',1,7.2,0.0,2,54,54,336,1', ass)
            self.assertIn(r'\pos(360,944)', ass)
            self.assertNotIn(r'\kf', ass)
            self.assertEqual(result['caption_profile'], 'early-reels-ivory-gold-v01')

    def test_wrong_transcript_cannot_be_hidden_by_caption_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'captions.ass'
            with self.assertRaises(ValueError):
                build_religion_captions('Comparte pan.', [{'word': 'Otro', 'start': 0, 'end': 1}], path, duration=2)
            self.assertFalse(path.exists())
