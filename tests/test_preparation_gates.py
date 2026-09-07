import json
from pathlib import Path
import shutil
import tempfile
import unittest
from ecosystem.config import ROOT, load_channels, readiness, preparation_readiness, write_json
from ecosystem.planner import plan_daily
from ecosystem.upro_queue import Queue, canary_authorized


class PreparationGates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for directory in ("config", "channels"):
            shutil.copytree(ROOT / directory, self.root / directory)
        self.sq = next(c for c in load_channels(self.root) if c["id"] == "sabias-que")

    def tearDown(self):
        self.tmp.cleanup()

    def test_youtube_scope_keeps_tiktok_out_but_not_migration(self):
        blockers = readiness(self.sq, {}, {"active_platforms": ["youtube"]})
        self.assertFalse(any("tiktok" in b or "Vibes" in b for b in blockers))
        self.assertTrue(any("reconciliar" in b for b in blockers))
        self.assertTrue(any("primer reel" in b for b in blockers))

    def test_render_canary_not_circular_and_religion_not_comic(self):
        self.assertEqual(preparation_readiness(self.sq, {}, "ambient"), [])
        self.assertEqual(preparation_readiness(self.sq, {}, "cutout"), [])
        religion = next(c for c in load_channels(self.root) if c["id"] == "religion")
        self.assertTrue(preparation_readiness(religion, {}, "cutout"))
        self.assertTrue(preparation_readiness(self.sq, {}, "release"))

    def test_canary_needs_matching_local_grant_and_cannot_publish(self):
        from ecosystem.cache import file_hash
        job = next(c for c in plan_daily(self.root)["channels"] if c["channel_id"] == "sabias-que")
        source = self.root / "source.json"
        write_json(source, {"test": True})
        plan = {"schema_version": 1, "job_id": job["job_id"], "channel_id": "sabias-que",
                "mode": "canary", "adapter": "ambient", "inputs": [{"path": str(source), "sha256": file_hash(source)}]}
        q = Queue(self.root)
        with self.assertRaises(ValueError):
            q.register(plan)
        grant = self.root / ".runtime/authorizations/canary-sabias-que.json"
        write_json(grant, {"authorized": True, "job_id": job["job_id"], "adapters": ["ambient"], "user_instruction": "test explicit canary"})
        self.assertTrue(canary_authorized(self.root, plan))
        self.assertTrue(q.register(plan))
        with self.assertRaises(ValueError):
            q.register({**plan, "adapter": "release"})
        write_json(grant, {"authorized": False})
        self.assertFalse(canary_authorized(self.root, plan))


if __name__ == "__main__":
    unittest.main()
