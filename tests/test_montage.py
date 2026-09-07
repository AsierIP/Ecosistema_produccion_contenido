from pathlib import Path
import tempfile
import unittest
import wave
import shutil
from types import SimpleNamespace
from unittest.mock import patch
from ecosystem.cache import file_hash
from ecosystem.config import read_json
from ecosystem.montage import build_manifest


class MontageTests(unittest.TestCase):
    def test_manifest_cache_preserves_inputs_and_rejects_changed_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((1, 2, 48000, 0, 'NONE', 'none'))
                wav.writeframes(b'\x01\x00' * 48000)
            captions, intro, scene = (root / name for name in ('captions.ass', 'intro.test', 'scene.test'))
            for path in (captions, intro, scene):
                path.write_bytes(b'Test fixture only')
            args = dict(title='Título: prueba', transcript='Texto de prueba.', audio=audio, captions=captions,
                        scenes=[{'id': 'scene', 'video': str(scene), 'sha256': file_hash(scene), 'frames': 24}],
                        intro=intro, output_dir=root / 'media', evidence_dir=root / 'evidence', voice={'speed_factor': 1.15})
            def normalize(command, **kwargs):
                self.assertFalse(any('atempo' in str(arg) for arg in command))
                shutil.copyfile(audio, command[-1])
                return SimpleNamespace(returncode=0)
            with patch('ecosystem.montage.discover', return_value={'ffmpeg': 'fixture'}), patch('ecosystem.montage.subprocess.run', side_effect=normalize) as process:
                first = build_manifest(**args)
                self.assertEqual(first, build_manifest(**args))
                process.assert_called_once()
            manifest = read_json(first)
            self.assertEqual(Path(manifest['output']).name, 'Título prueba.mp4')
            self.assertEqual(manifest['end_card_seconds'], 0)
            Path(manifest['narration']).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                build_manifest(**args)
