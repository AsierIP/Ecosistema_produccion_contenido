from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch
from ecosystem.caption_alignment import resolve_alignment, verified_caption_transcript
from ecosystem.captions import prepare_captions, validated_words
from ecosystem.cache import file_hash
from ecosystem.config import read_json, write_json


class CaptionAlignmentTests(unittest.TestCase):
    def test_spoken_variant_preserves_audio_and_captions_actual_s(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / 'voice.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\0\0' * 48000)
            transcript = 'Quizá húsares.'
            output = root / 'captions'
            output.mkdir()
            request = root / 'request.json'
            write_json(request, {'kind': 'comic_captions_v1', 'channel_id': 'sabias-que',
                                'transcript': transcript, 'audio_path': str(audio), 'audio_sha256': file_hash(audio)})
            write_json(output / 'asr-intent.json', {'audio_sha256': file_hash(audio),
                       'transcript': transcript, 'profile': 'sq-bottom-electric-v1'})
            write_json(output / 'asr.json', {'words': [
                {'word': ' Quizás', 'start': 0, 'end': 1},
                {'word': ' úsares.', 'start': 1, 'end': 2}]})
            original = (file_hash(audio), file_hash(output / 'asr.json'))
            with patch('ecosystem.captions.subprocess.run', side_effect=AssertionError('No second ASR/provider run')):
                result = prepare_captions(request, output, root=root)
                self.assertEqual(result['transcript'], 'Quizás húsares.')
                self.assertEqual(verified_caption_transcript(result, transcript, 'sabias-que'), 'Quizás húsares.')
                self.assertEqual(prepare_captions(request, output, root=root), result)
            self.assertEqual(original, (file_hash(audio), file_hash(output / 'asr.json')))
            self.assertIn('Quizás', Path(result['path']).read_text(encoding='utf-8-sig'))
            evidence = Path(result['alignment']['path'])
            changed = read_json(evidence)
            changed['transcript'] = 'Otra historia.'
            write_json(evidence, changed)
            with self.assertRaises(ValueError):
                verified_caption_transcript(result, transcript, 'sabias-que')

    def test_content_changes_and_other_channels_are_not_adapted(self):
        for canonical, heard, channel in [('1795', '1796', 'sabias-que'),
                                          ('quizá', 'quizás', 'religion'),
                                          ('húsares', 'mares', 'sabias-que')]:
            text, words, _ = resolve_alignment(canonical, [{'word': heard, 'start': 0, 'end': 1}], channel)
            with self.assertRaises(ValueError):
                validated_words(text, words, 1)
