from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ecosystem.config import ROOT, load_channels, write_json
from ecosystem.voice_generate import generation_config, free_tier_preflight, generate_voice


class VoiceGenerationTests(unittest.TestCase):
    def setUp(self):
        self.channel = next(c for c in load_channels(ROOT) if c['id'] == 'sabias-que')
        self.request = {'kind': 'voice_generation_v1', 'channel_id': 'sabias-que',
                        'transcript': self.channel['closing']['spoken_text']}

    def test_voice_endpoint_and_direction_are_pinned(self):
        value = generation_config({**self.request, 'voice': 'fake', 'endpoint': 'https://example.com'}, self.channel)
        self.assertEqual(value['google_gemini']['voices'][0]['id'], 'Kore')
        self.assertEqual(value['language'], 'es-ES')
        self.assertTrue(value['direction'].endswith(self.request['transcript']))
        self.assertEqual(len(value['google_gemini']['voices']), 1)

    def test_missing_closing_or_wrong_channel_rejected(self):
        for override in [{'transcript': 'Sin cierre.'}, {'channel_id': 'religion'}]:
            with self.assertRaises(ValueError):
                generation_config({**self.request, **override}, self.channel)

    def test_unbound_free_tier_is_not_sufficient(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / '.runtime/providers/google-tts-free-tier.json', {
                'checked_at': datetime.now(timezone.utc).isoformat(), 'billing_enabled': False,
                'credential_project_verified': False, 'model': 'gemini-3.1-flash-tts-preview',
                'evidence': 'All visible projects are free; credential binding unknown'})
            with self.assertRaises(ValueError):
                free_tier_preflight(root)

    @patch('ecosystem.voice_generate.subprocess.run')
    def test_incomplete_attempt_does_not_send_again(self, process):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            request = root / 'request.json'
            write_json(request, self.request)
            output = root / 'out'
            write_json(output / 'generation-intent.json', {'state': 'sending'})
            with self.assertRaises(ValueError):
                generate_voice(request, output, root=ROOT)
            process.assert_not_called()

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows provider validation')
    def test_actual_provider_validation_reads_no_key_and_makes_no_call(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            request = root / 'request.json'
            write_json(request, self.request)
            result = generate_voice(request, root / 'out', root=ROOT, validate_only=True)
            self.assertEqual(result, {'status': 'CONFIG_VALIDATED', 'provider_calls': 0, 'credentials_read': False})
            self.assertFalse((root / 'out/generation-intent.json').exists())
