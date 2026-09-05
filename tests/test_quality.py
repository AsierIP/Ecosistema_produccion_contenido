"""Adversarial QA contract tests; fixture bytes never claim production decoding."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from ecosystem.quality import (
    REQUIRED_CHECKS, sha256_file, validate_qa, validate_publications,
    validate_publication_receipt, validate_timeline,
)


def quality_fixture(directory, mode="native"):
    """Create local fixture evidence for exercising validators, not media output."""
    directory = Path(directory)
    master = directory / "master.test"
    master.write_bytes(b"unit test artifact, not a production video")
    digest = sha256_file(master)
    segments = []
    for index in range(3):
        source = directory / f"source-{index}.test"
        output = directory / f"output-{index}.test"
        source.write_bytes(f"unit-test-source-{index}".encode())
        output.write_bytes(f"unit-test-output-{index}".encode())
        segments.append({
            "source_id": str(index), "source_path": str(source),
            "source_sha256": sha256_file(source), "output_path": str(output),
            "output_sha256": sha256_file(output), "input_frames": 125,
            "output_frames": 250 if mode == "rife_2x_por_segmento" else 125,
            "output_fps": 24, "speed_factor": 1.0,
            "interpolation": "rife_2x" if mode == "rife_2x_por_segmento" else "none",
        })
    checks = {name: {
        "passed": True, "master_sha256": digest,
        "evidence": "unit-test-only evidence contract",
    } for name in REQUIRED_CHECKS}
    checks["independent_review"]["reviewer_id"] = "independent-fixture-reviewer"
    qa = {
        "master_sha256": digest, "producer_id": "fixture-producer", "checks": checks,
        "timeline": {"mode": mode, "voice_speed_factor": 1.0,
                     "interpolated_across_cuts": False, "segments": segments},
    }
    accounts = {"youtube": "UC_fixture_account", "tiktok": "@fixture.account"}
    publications = {
        "youtube": {"account_id": accounts["youtube"], "url": "https://www.youtube.com/shorts/abcdefghijk"},
        "tiktok": {"account_id": accounts["tiktok"], "url": "https://www.tiktok.com/@fixture.account/video/1234567890123456789"},
    }
    for receipt in publications.values():
        receipt.update(master_sha256=digest, public_verified=True, evidence="fixture-public-observation")
    return master, qa, publications, accounts


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.master, self.qa, self.publications, self.accounts = quality_fixture(self.temp.name)

    def test_complete_native_contract(self):
        self.assertEqual([], validate_qa(self.qa, self.master))
        self.assertEqual([], validate_publications(self.publications, self.master, self.accounts))

    def test_rife_is_configurable_and_segment_local(self):
        master, qa, _, _ = quality_fixture(self.temp.name, "rife_2x_por_segmento")
        profile = {
            "timeline_mode": "rife_2x_por_segmento", "segment_count": 3,
            "input_frames_per_segment": 125, "output_frames_per_segment": 250,
            "output_fps": 24, "total_output_frames": 750,
        }
        self.assertEqual([], validate_qa(qa, master, profile))
        qa["timeline"]["interpolated_across_cuts"] = True
        self.assertTrue(validate_qa(qa, master, profile))

    def test_modified_master_invalidates_every_bound_check(self):
        self.master.write_bytes(b"changed unit test artifact")
        errors = validate_qa(self.qa, self.master)
        self.assertTrue(any("actual master" in error for error in errors))
        self.assertEqual(len(REQUIRED_CHECKS), sum("not bound" in error for error in errors))
        self.assertTrue(validate_publications(self.publications, self.master, self.accounts))

    def test_exit_status_cannot_replace_qa(self):
        self.assertTrue(validate_qa({"exit_code": 0, "status": "PASS"}, self.master))

    def test_checks_require_boolean_pass_and_evidence(self):
        for value in (1, "true", "PASS", False, None):
            with self.subTest(value=value):
                qa = deepcopy(self.qa)
                qa["checks"]["decode"]["passed"] = value
                self.assertTrue(validate_qa(qa, self.master))
        for value in (None, "", [], {}, {"note": ""}):
            with self.subTest(evidence=value):
                qa = deepcopy(self.qa)
                qa["checks"]["decode"]["evidence"] = value
                self.assertTrue(validate_qa(qa, self.master))

    def test_independent_review_must_be_independent(self):
        self.qa["checks"]["independent_review"]["reviewer_id"] = self.qa["producer_id"]
        self.assertTrue(validate_qa(self.qa, self.master))

    def test_reused_sources_detected_by_id_and_hash(self):
        for key in ("source_id", "source_sha256"):
            with self.subTest(key=key):
                qa = deepcopy(self.qa)
                qa["timeline"]["segments"][1][key] = qa["timeline"]["segments"][0][key]
                self.assertTrue(validate_qa(qa, self.master))

    def test_stretched_voice_and_segment_speed_rejected(self):
        for value in (0.5, 2, True, "1.0", float("nan")):
            with self.subTest(value=value):
                qa = deepcopy(self.qa)
                qa["timeline"]["voice_speed_factor"] = value
                self.assertTrue(validate_qa(qa, self.master))
                qa = deepcopy(self.qa)
                qa["timeline"]["segments"][0]["speed_factor"] = value
                self.assertTrue(validate_qa(qa, self.master))

    def test_source_and_output_files_have_real_provenance(self):
        for role in ("source", "output"):
            with self.subTest(role=role):
                qa = deepcopy(self.qa)
                qa["timeline"]["segments"][0][f"{role}_sha256"] = "a" * 64
                self.assertTrue(validate_qa(qa, self.master))

    def test_empty_or_missing_master_fails(self):
        self.master.write_bytes(b"")
        self.assertTrue(validate_qa(self.qa, self.master))
        self.master.unlink()
        self.assertTrue(validate_publications(self.publications, self.master, self.accounts))

    def test_exact_profile_and_no_native_rife_substitution(self):
        self.assertTrue(validate_qa(self.qa, self.master, {"timeline_mode": "rife_2x_por_segmento"}))
        self.assertTrue(validate_qa(self.qa, self.master, {"segment_count": 4}))
        self.assertTrue(validate_qa(self.qa, self.master, {"total_output_frames": 750}))
        self.assertTrue(validate_qa(self.qa, self.master, {"caption_profile": "ivory-gold"}))

    def test_both_public_platforms_required(self):
        for platform in self.publications:
            partial = deepcopy(self.publications)
            del partial[platform]
            self.assertTrue(validate_publications(partial, self.master, self.accounts))

    def test_publication_requires_exact_account_hash_true_and_evidence(self):
        for field, value in (("account_id", "someone_else"), ("master_sha256", "b" * 64),
                             ("public_verified", 1), ("evidence", "")):
            with self.subTest(field=field):
                publications = deepcopy(self.publications)
                publications["youtube"][field] = value
                self.assertTrue(validate_publications(publications, self.master, self.accounts))

    def test_noncanonical_or_spoofed_youtube_urls_rejected(self):
        bad_urls = (
            "http://www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com.evil.invalid/shorts/abcdefghijk",
            "https://www.youtube.com@evil.invalid/shorts/abcdefghijk",
            "https://evil.invalid@www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com:443/shorts/abcdefghijk",
            "https://www.youtube.com/shorts/abcdefghijk?private=true",
            "https://www.youtube.com/shorts/abcdefghijk#x",
            "https://studio.youtube.com/video/abcdefghijk/edit",
            "https://www.youtube.com/shorts/abcdefghijk\n",
            "https://www.youtube.com/shorts/%61bcdefghijk",
        )
        for url in bad_urls:
            with self.subTest(url=url):
                receipt = dict(self.publications["youtube"], url=url)
                self.assertTrue(validate_publication_receipt(receipt, "youtube", self.qa["master_sha256"], self.accounts["youtube"]))

    def test_tiktok_url_handle_must_match_configured_handle(self):
        self.publications["tiktok"]["url"] = "https://www.tiktok.com/@someoneelse/video/1234567890123456789"
        self.assertTrue(validate_publications(self.publications, self.master, self.accounts))

    def test_malformed_structures_fail_closed(self):
        for value in (None, [], "PASS", 0):
            with self.subTest(value=value):
                self.assertTrue(validate_qa(value, self.master))
                self.assertTrue(validate_publications(value, self.master, self.accounts))
                self.assertTrue(validate_timeline(value))
        qa = deepcopy(self.qa)
        qa["timeline"]["segments"] = [None]
        self.assertTrue(validate_qa(qa, self.master))


if __name__ == "__main__":
    unittest.main()
