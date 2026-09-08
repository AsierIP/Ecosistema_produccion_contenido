from pathlib import Path
import subprocess
import tempfile
import unittest
from ecosystem.media import discover
from ecosystem.native_timeline import assemble_visual
from ecosystem.rife import frame_hashes


class NativeTimelineTests(unittest.TestCase):
    def test_real_three_scene_assembly_replaces_boundaries_without_extra_frames(self):
        ffmpeg = discover().get('ffmpeg')
        if not ffmpeg:
            self.skipTest('FFmpeg unavailable')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); paths = []
            for i, color in enumerate(('red', 'green', 'blue')):
                p = root / f's{i}.mkv'
                subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                    f'color={color}:s=720x1280:r=24', '-frames:v', '250', '-c:v', 'ffv1', str(p)],
                    capture_output=True, check=True, timeout=60)
                paths.append(p)
            out = root / 'visual.mkv'
            result = assemble_visual(paths, out, root / 'evidence.json')
            hashes = frame_hashes(out, ffmpeg)
            self.assertEqual(len(hashes), 750)
            self.assertEqual(hashes[249], hashes[250])
            self.assertEqual(hashes[499], hashes[500])
            self.assertNotEqual(hashes[250], hashes[251])
            self.assertNotEqual(hashes[500], hashes[501])
            self.assertEqual(result['duration_seconds'], 31.25)
            self.assertEqual(result['independent_visual_review'], 'pending')
            with self.assertRaises(ValueError):
                assemble_visual(paths, out, root / 'evidence.json')
            with self.assertRaises(ValueError):
                assemble_visual([paths[0]] * 3, root / 'duplicate.mkv', root / 'duplicate.json')
