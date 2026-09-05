"""Opt-in hardware regression: routine core tests never silently consume GPU."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from ecosystem.rife import conform_segment, frame_hashes
from ecosystem.media import discover
from ecosystem.store import Store

@unittest.skipUnless(os.environ.get("ECOSYSTEM_GPU_TEST") == "1", "Set ECOSYSTEM_GPU_TEST=1 to run the real GPU regression")
class RifeHardwareTests(unittest.TestCase):
    def test_native_frames_and_endpoint_survive_real_gpu_interpolation(self):
        tools = discover()
        self.assertIsNotNone(tools["video2x"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.mp4", root / "output.mp4"
            subprocess.run([tools["ffmpeg"], "-n", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=128x224:rate=24",
                            "-frames:v", "125", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", str(source)], check=True, timeout=30)
            result = conform_segment(source, output, root=root)
            self.assertEqual(result["status"], "TECHNICAL_PASS")
            self.assertFalse(result["production_qualified"])
            self.assertEqual(result["native_frames_preserved"], 125)
            self.assertEqual(len(frame_hashes(output, tools["ffmpeg"])), 250)
            self.assertEqual(len(result["model_sha256"]), 2)
            with Store(root / ".runtime/production.sqlite3") as store:
                self.assertEqual(store.connection.execute("SELECT COUNT(*) FROM leases").fetchone()[0], 0)
            with self.assertRaises(ValueError):
                conform_segment(source, output, root=root)

if __name__ == "__main__":
    unittest.main()
