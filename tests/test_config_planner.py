import json
from pathlib import Path
import shutil
import tempfile
import unittest
from ecosystem.config import ROOT, load_channels, readiness
from ecosystem.planner import plan_daily
from ecosystem.onboarding import create_channel
from ecosystem.cache import Cache, cache_key

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "channels", self.root / "channels")
        shutil.copytree(ROOT / "config", self.root / "config")

    def tearDown(self):
        self.tmp.cleanup()

    def test_repeated_days_resume_same_incomplete_job(self):
        first = plan_daily(self.root, "2026-09-05")
        again = plan_daily(self.root, "2026-09-06")
        self.assertEqual([c["job_id"] for c in first["channels"]], [c["job_id"] for c in again["channels"]])
        self.assertTrue(all(c["resuming"] for c in again["channels"]))
        self.assertEqual(first["status"], "BLOCKED")

    def test_source_and_identity_missing_are_not_ready(self):
        channel = next(c for c in load_channels(self.root) if c["id"] == "sabias-que")
        blockers = readiness(channel, {}, {"automatic_execution_enabled": True})
        self.assertTrue(any("youtube" in b for b in blockers))
        self.assertTrue(any("Fuente" in b for b in blockers))
        self.assertFalse(any("fijar la voz" in b for b in blockers))

    def test_onboarding_does_not_overwrite_or_activate(self):
        answers = {"name": "Canal nuevo", "theme": "Historia", "sources": [{"id": "book", "title": "Libro"}], "visual_style": "acuarela", "approved": True}
        channel = create_channel(answers, self.root)["channel"]
        self.assertEqual(channel["lifecycle"], "discovery")
        self.assertFalse(channel["visual"]["approved"])
        with self.assertRaises(FileExistsError):
            create_channel(answers, self.root)

    def test_cache_invalidates_on_artifact_or_policy_change(self):
        cache = Cache(self.root / "cache")
        artifact = self.root / "evidence.txt"
        artifact.write_text("before")
        key = cache_key(channel_id="one", stage="qa", policy=1, inputs=[], model="m")
        other = cache_key(channel_id="one", stage="qa", policy=2, inputs=[], model="m")
        self.assertNotEqual(key, other)
        cache.put(key, {"accepted": True}, [artifact])
        self.assertIsNotNone(cache.get(key))
        artifact.write_text("after")
        self.assertIsNone(cache.get(key))

    def test_invalid_channel_fails_validation(self):
        path = self.root / "channels" / "sabias-que.json"
        content = json.loads(path.read_text(encoding="utf-8"))
        content["daily_reels"] = True
        path.write_text(json.dumps(content), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_channels(self.root)

if __name__ == "__main__":
    unittest.main()
