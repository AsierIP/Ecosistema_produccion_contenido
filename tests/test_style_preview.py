"""Preview contract tests; these never start FFmpeg or use the GPU."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ecosystem.cache import file_hash
from ecosystem.style_preview import render_style_preview


class StylePreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "approved ; $(literal).png"
        self.source.write_bytes(b"\x89PNG\r\n\x1a\nplaceholder")
        self.output = self.root / "preview.mp4"
        self.options = {"approved_source_sha256": file_hash(self.source), "encoder": "libx264"}
        self.discovery = patch("ecosystem.style_preview.discover", return_value={
            "ffmpeg": "ffmpeg.exe", "ffprobe": "ffprobe.exe"})
        self.discovery.start()
        self.addCleanup(self.discovery.stop)

    def test_plan_is_silent_finite_and_has_no_execution(self):
        with patch("ecosystem.style_preview._run") as run:
            plan = render_style_preview(self.source, self.output, **self.options)
        run.assert_not_called()
        self.assertEqual(plan["expected_frames"], 144)
        self.assertIn("-an", plan["argv"])
        self.assertIn("-n", plan["argv"])
        self.assertEqual(plan["argv"][plan["argv"].index("-frames:v") + 1], "144")
        self.assertTrue(plan["camera_only"])
        self.assertFalse(plan["production_qa_passed"])
        self.assertFalse(self.output.exists())

    def test_rejects_unbounded_duration_unapproved_source_and_overwrite(self):
        for duration in (float("nan"), float("inf"), 0, 31, True, 6.01):
            with self.assertRaises(ValueError):
                render_style_preview(self.source, self.output, duration_seconds=duration, **self.options)
        with self.assertRaisesRegex(ValueError, "approved SHA256"):
            render_style_preview(self.source, self.output, encoder="libx264", approved_source_sha256="0" * 64)
        with self.assertRaises(FileNotFoundError):
            render_style_preview(self.root / "missing.png", self.output, **self.options)
        with self.assertRaisesRegex(ValueError, "existing directory"):
            render_style_preview(self.source, self.root / "missing" / "out.mp4", **self.options)
        self.output.with_suffix(".preview.json").write_text("existing")
        with self.assertRaisesRegex(ValueError, "new files"):
            render_style_preview(self.source, self.output, **self.options)

    def test_gpu_lease_and_verified_receipt_do_not_claim_production_qa(self):
        state = {"held": False}

        @contextmanager
        def reserve(root, owner):
            self.assertEqual(root, self.root)
            state["held"] = True
            try:
                yield "store", "lease"
            finally:
                state["held"] = False

        def run(*args, **kwargs):
            self.assertTrue(state["held"])
            self.assertEqual(kwargs["lease"], "lease")
            self.output.write_bytes(b"mock encoded data")
            return 0

        metadata = {"ok": True, "duration_seconds": 6.0, "streams": [{
            "codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920,
            "avg_frame_rate": "24/1", "nb_frames": "144"}]}
        with patch("ecosystem.style_preview.gpu_lease", reserve), \
             patch("ecosystem.style_preview._run", side_effect=run), \
             patch("ecosystem.style_preview.probe", return_value=metadata), \
             patch("ecosystem.style_preview.decode", return_value={"ok": True}):
            receipt = render_style_preview(self.source, self.output, encoder="h264_nvenc",
                                           approved_source_sha256=file_hash(self.source),
                                           root=self.root, execute=True)
        self.assertFalse(state["held"])
        self.assertEqual(receipt["sha256"], file_hash(self.output))
        self.assertTrue(receipt["not_character_animation"])
        self.assertFalse(receipt["production_qa_passed"])
        self.assertTrue(self.output.with_suffix(".preview.json").is_file())

    def test_encoder_success_with_wrong_dimensions_cannot_create_receipt(self):
        def run(*args, **kwargs):
            self.output.write_bytes(b"mock encoded data")
            return 0

        metadata = {"ok": True, "duration_seconds": 6.0, "streams": [{
            "codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280,
            "avg_frame_rate": "24/1", "nb_frames": "144"}]}
        with patch("ecosystem.style_preview._run", side_effect=run), \
             patch("ecosystem.style_preview.probe", return_value=metadata), \
             patch("ecosystem.style_preview.decode", return_value={"ok": True}):
            with self.assertRaisesRegex(RuntimeError, "dimensions"):
                render_style_preview(self.source, self.output, execute=True, **self.options)
        self.assertFalse(self.output.with_suffix(".preview.json").exists())


if __name__ == "__main__":
    unittest.main()
