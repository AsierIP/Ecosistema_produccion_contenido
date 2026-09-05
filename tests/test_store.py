"""Durability, concurrent ownership and fail-closed publication tests."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ecosystem.store import ConflictError, IntentUncertainError, QualityError, Store
from test_quality import quality_fixture


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "state.sqlite3"
        self.store = Store(self.db)
        self.addCleanup(self.store.close)
        self.job = self.store.enqueue_job("religion", "2026-09-05", {"fixture": True})
        self.master, self.qa, self.publications, self.accounts = quality_fixture(self.temp.name)

    def prepare(self, platform="youtube", action="publish"):
        return self.store.prepare_intent(
            self.job["id"], platform, action, self.qa["master_sha256"],
            {"expected_account_id": self.accounts[platform]},
        )

    def verify(self, platform):
        intent = self.prepare(platform)
        intent = self.store.start_intent(intent["id"], intent["version"])
        return self.store.reconcile_intent(intent["id"], intent["version"], "verified", self.publications[platform])

    def test_job_daily_uniqueness_and_stable_id_across_restarts(self):
        again = self.store.enqueue_job("religion", "2026-09-05", {"changed": True})
        self.assertEqual(self.job, again)
        with Store(self.db) as reopened:
            self.assertEqual(self.job["id"], reopened.enqueue_job("religion", "2026-09-05")["id"])
        other = self.store.enqueue_job("sabias-que", "2026-09-05")
        tomorrow = self.store.enqueue_job("religion", "2026-09-06")
        self.assertEqual(3, len({self.job["id"], other["id"], tomorrow["id"]}))
        self.assertEqual(2, len(self.store.list_jobs(channel_id="religion")))

    def test_invalid_dates_and_empty_channel_rejected(self):
        for channel, day in (("", "2026-09-05"), ("a", "2026-02-30"), ("a", "20260905")):
            with self.subTest(channel=channel, day=day), self.assertRaises(ValueError):
                self.store.enqueue_job(channel, day)

    def test_competing_schedulers_only_create_one_job(self):
        def enqueue(_):
            with Store(self.db) as store:
                return store.enqueue_job("new-channel", "2026-09-05")["id"]
        with ThreadPoolExecutor(max_workers=6) as executor:
            ids = list(executor.map(enqueue, range(12)))
        self.assertEqual(1, len(set(ids)))
        self.assertEqual(1, len(self.store.list_events(ids[0])))

    def test_cas_rejects_stale_worker_without_event_or_mutation(self):
        job = self.store.transition_job(self.job["id"], 0, "script", "running")
        event_count = len(self.store.list_events())
        with self.assertRaises(ConflictError):
            self.store.transition_job(self.job["id"], 0, "assets", "running")
        self.assertEqual(job, self.store.get_job(self.job["id"]))
        self.assertEqual(event_count, len(self.store.list_events()))

    def test_explicit_recovery_allows_earlier_stage(self):
        job = self.store.transition_job(self.job["id"], 0, "qa", "blocked")
        with self.assertRaises(ConflictError):
            self.store.transition_job(job["id"], job["version"], "render", "running")
        recovered = self.store.transition_job(job["id"], job["version"], "render", "running", {"reason": "fix failed QA"})
        self.assertEqual("render", recovered["stage"])

    def test_event_ledger_is_append_only(self):
        for sql in ("UPDATE events SET kind='forged'", "DELETE FROM events"):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                self.store.connection.execute(sql)
        self.assertEqual("job_created", self.store.list_events(self.job["id"])[0]["kind"])

    def test_gpu_and_remote_are_independent_singletons(self):
        gpu = self.store.claim_lease("gpu", "worker-a", 60, now=100)
        remote = self.store.claim_lease("remote", "worker-b", 60, now=100)
        self.assertIsNotNone(gpu)
        self.assertIsNotNone(remote)
        with Store(self.db) as second:
            self.assertIsNone(second.claim_lease("gpu", "worker-b", 60, now=120))
            self.assertIsNone(second.claim_lease("remote", "worker-c", 60, now=120))
        self.assertFalse(self.store.release_lease("gpu", "worker-b", gpu["token"]))
        self.assertTrue(self.store.release_lease("gpu", "worker-a", gpu["token"]))
        self.assertIsNotNone(self.store.claim_lease("gpu", "worker-b", 60, now=121))

    def test_expired_lease_token_cannot_release_or_renew_takeover(self):
        old = self.store.claim_lease("gpu", "worker-a", 10, now=100)
        new = self.store.claim_lease("gpu", "worker-a", 10, now=110)
        self.assertNotEqual(old["token"], new["token"])
        self.assertFalse(self.store.release_lease("gpu", "worker-a", old["token"]))
        self.assertFalse(self.store.renew_lease("gpu", "worker-a", old["token"], 30, now=111))
        self.assertTrue(self.store.renew_lease("gpu", "worker-a", new["token"], 30, now=111))
        self.assertFalse(self.store.renew_lease("gpu", "worker-a", new["token"], 30, now=141))

    def test_competing_gpu_claims_have_one_winner(self):
        def claim(index):
            with Store(self.db) as store:
                return store.claim_lease("gpu", f"worker-{index}", 60, now=100)
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(claim, range(12)))
        self.assertEqual(1, sum(result is not None for result in results))

    def test_invalid_lease_values_rejected(self):
        for ttl in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                self.store.claim_lease("gpu", "a", ttl)
        with self.assertRaises(ValueError):
            self.store.claim_lease("gpu-2", "a", 1)

    def test_intent_is_idempotent_and_cannot_change_master_or_payload(self):
        intent = self.prepare()
        self.assertEqual(intent, self.prepare())
        with self.assertRaises(ConflictError):
            self.store.prepare_intent(self.job["id"], "youtube", "publish", "a" * 64)
        with self.assertRaises(ConflictError):
            self.store.prepare_intent(self.job["id"], "youtube", "publish", self.qa["master_sha256"], {"different": True})
        self.assertEqual(1, len(self.store.list_intents(self.job["id"])))

    def test_sending_survives_restart_and_cannot_be_retried(self):
        prepared = self.prepare()
        sending = self.store.start_intent(prepared["id"], prepared["version"])
        with Store(self.db) as reopened:
            self.assertEqual("sending", reopened.get_intent(sending["id"])["state"])
            with self.assertRaises(IntentUncertainError):
                reopened.start_intent(sending["id"], sending["version"])
            with self.assertRaises(IntentUncertainError):
                reopened.prepare_intent(self.job["id"], "youtube", "publish", self.qa["master_sha256"], {"expected_account_id": self.accounts["youtube"]})

    def test_uncertain_requires_authoritative_reconciliation(self):
        intent = self.prepare()
        intent = self.store.start_intent(intent["id"], intent["version"])
        intent = self.store.mark_intent_uncertain(intent["id"], intent["version"], {"error": "timeout after sending"})
        with self.assertRaises(IntentUncertainError):
            self.prepare()
        with self.assertRaises(ValueError):
            self.store.reconcile_intent(intent["id"], intent["version"], "not_found", {"error": "lookup timed out"})
        ready = self.store.reconcile_intent(intent["id"], intent["version"], "not_found", {"checked": True, "evidence": "remote lookup confirmed absence"})
        self.assertEqual("prepared", ready["state"])
        self.assertEqual("sending", self.store.start_intent(ready["id"], ready["version"])["state"])

    def test_stale_intent_cas_cannot_issue_second_attempt(self):
        intent = self.prepare()
        self.store.start_intent(intent["id"], intent["version"])
        with self.assertRaises(ConflictError):
            self.store.start_intent(intent["id"], intent["version"])

    def test_verified_platform_never_republishes_while_other_is_pending(self):
        pending_alt = self.prepare(action="alternative_upload")
        verified = self.verify("youtube")
        self.assertEqual("verified", self.prepare()["state"])
        with self.assertRaises(ConflictError):
            self.store.start_intent(verified["id"], verified["version"])
        with self.assertRaises(ConflictError):
            self.store.start_intent(pending_alt["id"], pending_alt["version"])
        with self.assertRaises(ConflictError):
            self.prepare(action="publish_again")
        self.assertEqual("prepared", self.prepare("tiktok")["state"])

    def test_reconcile_cannot_accept_wrong_account_or_hash(self):
        intent = self.prepare()
        intent = self.store.start_intent(intent["id"], intent["version"])
        for field, value in (("account_id", "wrong-account"), ("master_sha256", "f" * 64), ("public_verified", False)):
            with self.subTest(field=field), self.assertRaises(QualityError):
                self.store.reconcile_intent(intent["id"], intent["version"], "verified", dict(self.publications["youtube"], **{field: value}))
        self.assertEqual("sending", self.store.get_intent(intent["id"])["state"])

    def test_cannot_complete_via_stage_or_exit_code(self):
        for stage, state in (("complete", "running"), ("publish", "complete")):
            with self.subTest(stage=stage), self.assertRaises(QualityError):
                self.store.transition_job(self.job["id"], 0, stage, state, {"exit_code": 0})
        with self.assertRaises(QualityError):
            self.store.complete_job(self.job["id"], 0, {"exit_code": 0}, self.publications, self.master, self.accounts)

    def test_valid_packages_without_durable_receipts_do_not_complete(self):
        with self.assertRaises(QualityError):
            self.store.complete_job(self.job["id"], 0, self.qa, self.publications, self.master, self.accounts)
        self.verify("youtube")
        with self.assertRaises(QualityError):
            self.store.complete_job(self.job["id"], 0, self.qa, self.publications, self.master, self.accounts)

    def test_complete_requires_identical_durable_receipts_and_is_immutable(self):
        self.verify("youtube")
        self.verify("tiktok")
        changed_receipts = deepcopy(self.publications)
        changed_receipts["youtube"]["evidence"] = "different observation"
        with self.assertRaises(QualityError):
            self.store.complete_job(self.job["id"], 0, self.qa, changed_receipts, self.master, self.accounts)
        job = self.store.complete_job(self.job["id"], 0, self.qa, self.publications, self.master, self.accounts)
        self.assertEqual("complete", job["state"])
        self.assertEqual("complete", job["stage"])
        self.assertEqual(self.qa, self.store.list_events(job["id"])[-1]["data"]["details"]["qa"])
        with self.assertRaises(ConflictError):
            self.store.transition_job(job["id"], job["version"], "publish", "running")


if __name__ == "__main__":
    unittest.main()
