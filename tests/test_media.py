"""Integration checks use tiny synthetic clips, never production channel media."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ecosystem.media import build_render_command, build_rife_command, decode, discover, probe


class MediaValidationTests(unittest.TestCase):
    def test_missing_and_empty_media_fail_without_claiming_qa(self):
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing.mp4"
            empty = Path(temporary) / "empty.mp4"
            empty.touch()
            for source in (missing, empty):
                for operation in (probe, decode):
                    self.assertFalse(operation(source)["ok"])

    def test_broken_explicit_tool_override_does_not_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"ECOSYSTEM_FFMPEG": str(Path(temporary) / "missing.exe")}):
                found = discover()
                self.assertIsNone(found["ffmpeg"])
                self.assertIn("ECOSYSTEM_FFMPEG", " ".join(found["errors"]))
                self.assertFalse(found["hardware_qualified"])

    def test_unqualified_rife_cannot_be_used_as_generic_render(self):
        with self.assertRaisesRegex(ValueError, "qualified"):
            build_rife_command("input.mp4", "output.mp4")


class RealMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        found = discover()
        if not found["ffmpeg"] or not found["ffprobe"]:
            raise unittest.SkipTest("Real FFmpeg/FFprobe are required for media integration tests")
        cls.ffmpeg = found["ffmpeg"]
        cls.ffprobe = found["ffprobe"]

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source ; $(literal).mp4"
        completed = subprocess.run([
            self.ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-n",
            "-f", "lavfi", "-i", "testsrc2=size=64x96:rate=12:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-movflags", "+faststart", str(self.source),
        ], capture_output=True, text=True, timeout=30, shell=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_real_video_has_technical_evidence_and_full_decode(self):
        metadata = probe(self.source, self.ffprobe)
        self.assertTrue(metadata["ok"], metadata)
        self.assertAlmostEqual(metadata["duration_seconds"], 1.0, delta=0.15)
        result = decode(self.source, self.ffmpeg)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["editorial_qa_passed"])

    def test_invalid_and_truncated_files_cannot_pass_decode(self):
        invalid = self.root / "invalid.mp4"
        invalid.write_bytes(b"this is not a media container")
        self.assertFalse(probe(invalid, self.ffprobe)["ok"])
        self.assertFalse(decode(invalid, self.ffmpeg)["ok"])
        truncated = self.root / "truncated.mp4"
        payload = self.source.read_bytes()
        truncated.write_bytes(payload[:len(payload) // 2])
        self.assertFalse(decode(truncated, self.ffmpeg)["ok"])

    def test_render_preserves_media_with_literal_special_characters_in_paths(self):
        output = self.root / "render ; $(literal).mp4"
        command = build_render_command(self.source, output, width=64, height=96, ffmpeg=self.ffmpeg)
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, shell=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(decode(output, self.ffmpeg)["ok"])
        before = probe(self.source, self.ffprobe)
        after = probe(output, self.ffprobe)
        self.assertTrue(after["ok"], after)
        self.assertAlmostEqual(before["duration_seconds"], after["duration_seconds"], delta=0.15)

    def test_render_refuses_invalid_dimensions_encoder_and_existing_output(self):
        for values in ({"width": 63}, {"height": True}, {"quality": -1}, {"encoder": "shell injection"}):
            with self.assertRaises(ValueError):
                build_render_command(self.source, self.root / "new.mp4", **values)
        with self.assertRaisesRegex(ValueError, "new file"):
            build_render_command(self.source, self.source)
        with self.assertRaisesRegex(ValueError, "parent"):
            build_render_command(self.source, self.root / "missing" / "new.mp4")

    def test_ass_caption_render_accepts_windows_path_and_apostrophe(self):
        captions = self.root / "captions author's [approved].ass"
        captions.write_text(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 64\nPlayResY: 96\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,12,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,"
            "100,100,0,0,1,1,0,2,2,2,5,1\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,Prueba\n", encoding="utf-8")
        output = self.root / "captioned.mp4"
        command = build_render_command(self.source, output, subtitles=captions,
                                       width=64, height=96, ffmpeg=self.ffmpeg)
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, shell=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(decode(output, self.ffmpeg)["ok"])


if __name__ == "__main__":
    unittest.main()
