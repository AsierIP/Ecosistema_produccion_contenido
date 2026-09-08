import tempfile
import unittest
import wave
import struct
from pathlib import Path

from ecosystem.config import write_json, load_channels, ROOT
from ecosystem.native_batch import ref
from ecosystem.native_narration import selected_voice, trim_verified_silent_tail
from ecosystem.voice_generate import generation_config


class NativeNarrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.request = {'kind': 'voice_generation_v1', 'channel_id': 'religion',
            'native_sequence': 'sequence', 'creative': {'sha256': 'creative'},
            'transcript': 'Una narración que conserva todas sus palabras.'}

    def step(self, name, request, state='accepted'):
        path = self.root / (name + '.json')
        write_json(path, request)
        return {'id': name, 'state': state, 'payload': {'inputs': [ref(path)]}}

    def test_pending_retake_prevents_reusing_previous_audio(self):
        original = self.step('original', self.request)
        new = self.step('new', {**self.request, 'supersedes_voice_step': 'original'}, 'queued')
        self.assertEqual(selected_voice([new, original]), new)

    def test_retake_cannot_change_text(self):
        original = self.step('original', self.request)
        new = self.step('new', {**self.request, 'supersedes_voice_step': 'original', 'transcript': 'Changed'})
        with self.assertRaises(ValueError):
            selected_voice([original, new])

    def test_third_take_is_rejected(self):
        original = self.step('original', self.request)
        with self.assertRaises(ValueError):
            selected_voice([original, original, original])

    def test_silent_tail_preserves_samples_and_rejects_speech(self):
        source, output = self.root / 'audio.wav', self.root / 'fitted.wav'
        def audio(tail):
            with wave.open(str(source), 'wb') as stream:
                stream.setparams((1, 2, 1000, 0, 'NONE', 'not compressed'))
                stream.writeframes(struct.pack('<1200h', *([500] * 700 + [0] * 300 + [tail] * 200)))
        audio(0)
        words = [{'word': 'Hola', 'start': 0, 'end': 0.7}]
        result = trim_verified_silent_tail(source, output, target=1, words=words, transcript='Hola')
        self.assertTrue(result['retained_pcm_identical'])
        with wave.open(str(output)) as stream:
            self.assertEqual(stream.getnframes(), 1000)
        self.assertEqual(result, trim_verified_silent_tail(source, output, target=1, words=words, transcript='Hola'))
        audio(100)
        with self.assertRaises(ValueError):
            trim_verified_silent_tail(source, self.root / 'bad.wav', target=1, words=words, transcript='Hola')
        self.assertFalse((self.root / 'bad.wav').exists())
        audio(0)
        with self.assertRaises(ValueError):
            trim_verified_silent_tail(source, self.root / 'spoken.wav', target=1,
                words=[{'word': 'Hola', 'start': 0, 'end': 1.05}], transcript='Hola')

    def test_natural_duration_keeps_voice_and_transcript(self):
        channel = next(c for c in load_channels(ROOT) if c['id'] == 'religion')
        original = generation_config(self.request, channel)
        revised = generation_config({**self.request, 'target_duration_seconds': 30.75}, channel)
        self.assertEqual(original['google_gemini'], revised['google_gemini'])
        self.assertEqual(original['transcript'], revised['transcript'])
        self.assertIn('30.75 segundos', revised['direction'])
        for invalid in [True, 0, 40, float('nan')]:
            with self.assertRaises(ValueError):
                generation_config({**self.request, 'target_duration_seconds': invalid}, channel)
