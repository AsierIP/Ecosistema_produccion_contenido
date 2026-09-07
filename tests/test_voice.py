import hashlib
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from ecosystem.cache import file_hash
from ecosystem.config import ROOT, write_json
from ecosystem.voice import prepare_voice


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'original.wav'
        with wave.open(str(self.source), 'wb') as audio:
            audio.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\x01\x00' * 24000)
        self.provider = self.folder / 'provider.json'
        self.data = {'provider': 'Google Gemini', 'run_status': 'complete',
                     'comparison': {'language': 'es-CO', 'transcript': 'Texto de prueba.',
                                    'transcript_sha256': hashlib.sha256(b'Texto de prueba.').hexdigest()},
                     'samples': [{'voice': 'Algenib', 'status': 'ok', 'file': self.source.name,
                                  'sha256': file_hash(self.source)}]}
        self.request = self.folder / 'request.json'
        self.output = self.folder / 'output'
        self.save()

    def save(self):
        write_json(self.provider, self.data)
        write_json(self.request, {'kind': 'voice_from_provider_v1', 'channel_id': 'religion',
                                 'transcript': 'Texto de prueba.', 'provider_manifest': str(self.provider),
                                 'provider_manifest_sha256': file_hash(self.provider)})

    @patch('ecosystem.voice.decode', return_value={'ok': True})
    def test_original_natural_voice_and_cache(self, decoder):
        first = prepare_voice(self.request, self.output, root=ROOT)
        self.assertEqual(first['sha256'], file_hash(self.source))
        self.assertEqual(first['provider_calls'], 0)
        self.assertEqual(first['independent_listening'], 'pending')
        self.assertEqual(first, prepare_voice(self.request, self.output, root=ROOT))
        decoder.assert_called_once()

    def test_wrong_accent_or_modified_narration_rejected(self):
        for key, value in [('language', 'es-ES'), ('transcript', 'Otra narración')]:
            original = self.data['comparison'][key]
            self.data['comparison'][key] = value
            self.save()
            with self.assertRaises(ValueError):
                prepare_voice(self.request, self.output, root=ROOT)
            self.data['comparison'][key] = original

    def test_changed_raw_audio_rejected(self):
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            prepare_voice(self.request, self.output, root=ROOT)

    @patch('ecosystem.voice.decode', return_value={'ok': True})
    def test_changed_cached_output_is_not_silently_replaced(self, decoder):
        prepare_voice(self.request, self.output, root=ROOT)
        (self.output / 'narration.wav').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            prepare_voice(self.request, self.output, root=ROOT)
