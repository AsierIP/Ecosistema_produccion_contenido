"""Retry regressions: preserve previous evidence without running a renderer."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ecosystem.cutout import render


class CutoutRetryTests(unittest.TestCase):
    def test_retry_cannot_overwrite_work_files_or_previous_receipt(self):
        for existing in ("work/body-filter.txt", "work/render.log", "evidence/technical-qa.json"):
            with self.subTest(existing=existing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name in ("intro.mp4", "narration.wav", "captions.ass"):
                    (root / name).write_bytes(b"source must remain unchanged")
                previous = root / existing
                previous.parent.mkdir(parents=True)
                previous.write_bytes(b"previous attempt evidence")
                manifest = root / "manifest.json"
                manifest.write_text(json.dumps({
                    "work_dir": str(root / "work"), "evidence_dir": str(root / "evidence"),
                    "output": str(root / "new.mp4"), "intro": str(root / "intro.mp4"),
                    "narration": str(root / "narration.wav"), "ass": str(root / "captions.ass"),
                }), encoding="utf-8")
                with patch("ecosystem.cutout.discover", return_value={"ffmpeg": "unused", "ffprobe": "unused"}), \
                     patch("ecosystem.cutout.wave.open") as open_audio, \
                     patch("ecosystem.cutout._run") as run_process:
                    with self.assertRaisesRegex(ValueError, "previous attempts|already contains"):
                        render(manifest, root=root)
                open_audio.assert_not_called()
                run_process.assert_not_called()
                self.assertEqual(previous.read_bytes(), b"previous attempt evidence")
                self.assertFalse((root / "new.mp4").exists())

    def test_final_output_cannot_claim_an_intermediate_video_path(self):
        for name in ("body.mp4", "intro-video.mp4"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.write_bytes(b"input")
                manifest = root / "manifest.json"
                manifest.write_text(json.dumps({
                    "work_dir": str(root / "work"), "evidence_dir": str(root / "evidence"),
                    "output": str(root / "work" / name),
                    "intro": str(source), "narration": str(source), "ass": str(source),
                }), encoding="utf-8")
                with patch("ecosystem.cutout.discover", return_value={"ffmpeg": "unused", "ffprobe": "unused"}), \
                     patch("ecosystem.cutout._run") as run_process:
                    with self.assertRaisesRegex(ValueError, "intermediate video paths"):
                        render(manifest, root=root)
                run_process.assert_not_called()
                self.assertFalse((root / "work").exists())


if __name__ == "__main__":
    unittest.main()
