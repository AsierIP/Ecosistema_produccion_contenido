import tempfile
import unittest
from pathlib import Path

from ecosystem.config import write_json, load_channels, ROOT
from ecosystem.native_batch import ref
from ecosystem.native_narration import selected_voice
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
