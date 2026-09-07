from pathlib import Path
import tempfile
import unittest
from ecosystem.captions import build_captions


class CaptionTests(unittest.TestCase):
    def test_year_spelling_preserves_literal_narration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'year.ass'
            result = build_captions('mil ochocientos quince', [{'word': '1815', 'start': 0, 'end': 2}], path, duration=2)
            self.assertTrue(result['literal_text_matches'])
            text = path.read_text(encoding='utf-8-sig')
            self.assertIn('ochocientos', text)
            self.assertNotIn('1815', text)

    def test_literal_bottom_single_block_electric_style_without_black_box(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'captions.ass'
            result = build_captions('Dale like y suscríbete.', [
                {'word': word, 'start': i / 2, 'end': (i + 1) / 2}
                for i, word in enumerate(['Dale', 'like', 'y', 'suscríbete.'])], path, duration=2)
            text = path.read_text(encoding='utf-8-sig')
            self.assertEqual(result['cue_count'], 1)
            self.assertEqual(text.count('Dialogue:'), 1)
            self.assertIn(r'\pos(540,1650)', text)
            self.assertIn('&H0000FFC8', text)
            self.assertIn('&H009D00FF', text)
            # Caption style uses outlined text (BorderStyle 1), not a box (3).
            self.assertIn(',100,100,0,0,1,6,2,5,', text)

    def test_mismatched_words_and_invalid_times_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'captions.ass'
            for words in [[{'word': 'Otro', 'start': 0, 'end': 1}],
                          [{'word': 'Hola', 'start': -1, 'end': 1}],
                          [{'word': 'Hola', 'start': 0, 'end': 0}]]:
                with self.assertRaises(ValueError):
                    build_captions('Hola', words, path, duration=1)
