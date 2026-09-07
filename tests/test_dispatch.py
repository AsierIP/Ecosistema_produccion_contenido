from pathlib import Path
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from ecosystem.config import ROOT
from ecosystem.store import Store
from ecosystem.dispatch import build_packet, validate_receipt
from ecosystem.worker import run_stage

class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for directory in ("channels", "config", "prompts"):
            shutil.copytree(ROOT / directory, self.root / directory)
        with Store(self.root / ".runtime/production.sqlite3") as store:
            self.job = store.enqueue_job("religion", "2026-09-05")["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_prep_is_small_has_explicit_model_and_no_execution(self):
        with patch("ecosystem.worker.subprocess.run") as execute:
            result = run_stage(self.job, "creative", root=self.root)
            execute.assert_not_called()
        self.assertEqual(result["model"], "gpt-5.6-sol")
        self.assertLess(result["input_chars"], 24000)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", result["argv"])

    def test_missing_inputs_and_remote_adapter_do_not_consume_tokens(self):
        with patch("ecosystem.worker.subprocess.run") as execute:
            for role in ("creative", "visual", "release"):
                result = run_stage(self.job, role, root=self.root, execute=True)
                self.assertEqual(result["status"], "BLOCKED")
            execute.assert_not_called()

    def test_receipt_requires_artifacts_not_exit_success(self):
        result = build_packet(self.job, "quality", root=self.root)
        packet = json.loads(Path(result["packet_path"]).read_text(encoding="utf-8"))
        receipt = {"job_id": self.job, "role": "quality", "decision": "ACCEPT", "artifacts": [], "checks": [], "blockers": []}
        self.assertTrue(validate_receipt(receipt, packet))
        self.assertTrue(validate_receipt([], packet))

    def test_failed_process_is_recorded_and_not_retried(self):
        source = self.root / "source-pack.json"
        source.write_text('{}', encoding="utf-8")
        with patch("ecosystem.worker.subprocess.run") as execute:
            execute.return_value.returncode = 1
            result = run_stage(self.job, "creative", [source], root=self.root, execute=True)
            self.assertEqual(result["status"], "BLOCKED")
            retry = run_stage(self.job, "creative", [source], root=self.root, execute=True)
            self.assertEqual(retry["status"], "ALREADY_RECORDED")
            self.assertEqual(execute.call_count, 1)
        self.assertIsNone(result["usage"]["input_tokens"])

    def test_quality_missing_capability_blocks_before_process(self):
        source = self.root / "source.json"
        source.write_text('{}')
        with patch("ecosystem.worker.subprocess.run") as execute:
            result = run_stage(self.job, "quality", [source], root=self.root, execute=True)
        execute.assert_not_called()
        self.assertFalse(result["agent_started"])

    def test_timeout_still_accounts_for_completed_events(self):
        import subprocess
        source = self.root / "source.json"
        source.write_text('{}')
        def expire(*args, **kwargs):
            kwargs["stdout"].write(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 123, "output_tokens": 4, "cached_input_tokens": 100}}) + "\n")
            raise subprocess.TimeoutExpired("test", 1)
        with patch("ecosystem.worker.subprocess.run", side_effect=expire):
            result = run_stage(self.job, "creative", [source], root=self.root, execute=True)
        self.assertEqual(result["status"], "UNCERTAIN")
        self.assertEqual(result["usage"]["input_tokens"], 123)

    def test_reviewed_input_is_allowed_but_not_output(self):
        source = self.root / "source.json"
        source.write_text('{}')
        result = build_packet(self.job, "quality", [source], root=self.root)
        packet = json.loads(Path(result["packet_path"]).read_text())
        receipt = {"job_id": self.job, "role": "quality", "decision": "BLOCK", "artifacts": [], "inputs_reviewed": packet["inputs"], "checks": [], "blockers": ["playback"]}
        self.assertEqual(validate_receipt(receipt, packet), [])
        receipt["artifacts"] = packet["inputs"]
        self.assertIn("artifact outside work order output", validate_receipt(receipt, packet))
        receipt["artifacts"] = []
        source.write_text('{"changed":true}')
        self.assertIn("reviewed input hash or size mismatch", validate_receipt(receipt, packet))

if __name__ == "__main__":
    unittest.main()
