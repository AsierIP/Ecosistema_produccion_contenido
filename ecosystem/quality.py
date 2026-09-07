"""Fail-closed checks for a rendered master, its QA evidence and public receipts.

These checks validate evidence contracts; they do not manufacture reviews, run a
decoder or publish anything. Producers must supply the corresponding real results.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED_CHECKS = (
    "decode", "sync", "natural_voice", "literal_captions", "visual_semantics",
    "sources_rights", "independent_review",
)
PLATFORMS = ("youtube", "tiktok")
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def sha256_file(path):
    """Hash an existing, nonempty regular file; never infer success from a path."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or empty artifact: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _evidence(value):
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value) and all(_evidence(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and any(_evidence(item) for item in value.values())
    return False


def _number(value, positive=False):
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and (not positive or value > 0)
    )


def _frames(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _artifact_hash(path, errors, label):
    try:
        return sha256_file(path)
    except (OSError, ValueError, TypeError) as error:
        errors.append(f"{label}: {error}")
        return None


def validate_timeline(timeline, profile=None):
    """Validate native or per-segment RIFE 2x footage and optional exact profile.

    Profile keys: timeline_mode, segment_count, input_frames_per_segment,
    output_frames_per_segment, output_fps, total_output_frames,
    require_provenance_files (defaults to True). Voice remains at natural speed.
    File paths are resolved by the caller, preferably to absolute artifact paths.
    """
    errors = []
    profile = profile or {}
    if not isinstance(profile, dict):
        return ["visual profile must be an object"]
    if not isinstance(timeline, dict):
        return ["timeline is required"]
    mode = timeline.get("mode")
    if mode not in {"native", "rife_2x_por_segmento"}:
        errors.append("timeline.mode must be native or rife_2x_por_segmento")
    if profile.get("timeline_mode") and mode != profile["timeline_mode"]:
        errors.append("timeline mode differs from the configured visual profile")
    voice_speed = timeline.get("voice_speed_factor")
    expected_voice_speed = profile.get('voice_speed_factor', 1.0)
    if not _number(voice_speed, positive=True) or voice_speed != expected_voice_speed:
        errors.append(f"voice must match approved speed (voice_speed_factor={expected_voice_speed})")
    if timeline.get("interpolated_across_cuts") is not False:
        errors.append("interpolation across cuts is forbidden")
    segments = timeline.get("segments")
    if not isinstance(segments, list) or not segments:
        return errors + ["timeline must contain source segments"]
    if "segment_count" in profile and len(segments) != profile["segment_count"]:
        errors.append("segment count differs from the configured visual profile")
    seen_ids, seen_hashes = set(), set()
    total_frames = 0
    for index, segment in enumerate(segments):
        label = f"segment {index + 1}"
        if not isinstance(segment, dict):
            errors.append(f"{label} must be an object")
            continue
        source_id = segment.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            errors.append(f"{label}: source_id is required")
        elif source_id in seen_ids:
            errors.append(f"{label}: source reuse is forbidden")
        else:
            seen_ids.add(source_id)
        source_hash = segment.get("source_sha256")
        if isinstance(source_hash, str) and source_hash in seen_hashes:
            errors.append(f"{label}: duplicate source hash is forbidden")
        if isinstance(source_hash, str):
            seen_hashes.add(source_hash)
        for role in ("source", "output"):
            digest = segment.get(f"{role}_sha256")
            artifact = segment.get(f"{role}_path")
            if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
                errors.append(f"{label}: valid {role}_sha256 is required")
            if not isinstance(artifact, str) or not artifact.strip():
                errors.append(f"{label}: {role}_path provenance is required")
            elif profile.get("require_provenance_files", True):
                actual = _artifact_hash(artifact, errors, f"{label} {role}")
                if actual is not None and actual != digest:
                    errors.append(f"{label}: {role} artifact hash mismatch")
        input_frames, output_frames = segment.get("input_frames"), segment.get("output_frames")
        if not _frames(input_frames) or not _frames(output_frames):
            errors.append(f"{label}: positive integer frame counts are required")
        else:
            total_frames += output_frames
            factor = 2 if mode == "rife_2x_por_segmento" else 1
            if output_frames != input_frames * factor:
                errors.append(f"{label}: frame count does not match {mode}")
        expected_interpolation = "rife_2x" if mode == "rife_2x_por_segmento" else "none"
        if segment.get("interpolation") != expected_interpolation:
            errors.append(f"{label}: invalid interpolation for {mode}")
        speed = segment.get("speed_factor")
        if not _number(speed, positive=True) or speed != 1.0:
            errors.append(f"{label}: timeline speed_factor must be 1.0")
        if segment.get("interpolated_across_cuts", False) is not False:
            errors.append(f"{label}: interpolation across cuts is forbidden")
        if not _number(segment.get("output_fps"), positive=True):
            errors.append(f"{label}: positive output_fps is required")
        for field, config_key in (
            ("input_frames", "input_frames_per_segment"),
            ("output_frames", "output_frames_per_segment"),
            ("output_fps", "output_fps"),
        ):
            if config_key in profile and segment.get(field) != profile[config_key]:
                errors.append(f"{label}: {field} differs from the configured visual profile")
    if "total_output_frames" in profile and total_frames != profile["total_output_frames"]:
        errors.append("total frame count differs from the configured visual profile")
    return errors


def validate_qa(package, master_path, profile=None):
    """Return errors, or [] only for QA bound to the actual nonempty master.

    Each required check contains passed=True, master_sha256 and nonempty evidence.
    independent_review also names a reviewer_id distinct from package.producer_id.
    A truthy exit code, stage label or queue entry is never completion evidence.
    """
    errors = []
    actual = _artifact_hash(master_path, errors, "master")
    if not isinstance(package, dict):
        return errors + ["QA package must be an object"]
    if actual is None or package.get("master_sha256") != actual:
        errors.append("QA master_sha256 does not match the actual master")
    checks = package.get("checks")
    if not isinstance(checks, dict):
        checks = {}
    for name in REQUIRED_CHECKS:
        check = checks.get(name)
        if not isinstance(check, dict):
            errors.append(f"QA check {name} is required")
            continue
        if check.get("passed") is not True:
            errors.append(f"QA check {name} did not pass")
        if actual is None or check.get("master_sha256") != actual:
            errors.append(f"QA check {name} is not bound to this master")
        if not _evidence(check.get("evidence")):
            errors.append(f"QA check {name} requires evidence")
    producer = package.get("producer_id")
    review = checks.get("independent_review", {})
    reviewer = review.get("reviewer_id") if isinstance(review, dict) else None
    if not isinstance(producer, str) or not producer.strip():
        errors.append("QA producer_id is required")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer == producer:
        errors.append("an independent reviewer distinct from the producer is required")
    errors.extend(validate_timeline(package.get("timeline"), profile))
    if isinstance(profile, dict) and profile.get("caption_profile"):
        if package.get("caption_profile") != profile["caption_profile"]:
            errors.append("caption profile differs from the channel configuration")
    return errors


def validate_publication_receipt(receipt, platform, master_sha256, expected_account):
    """Check canonical public URL, configured account, master hash and evidence."""
    if platform not in PLATFORMS:
        return [f"unsupported public platform: {platform}"]
    if not isinstance(receipt, dict):
        return [f"{platform}: public verification receipt is required"]
    errors = []
    if not isinstance(expected_account, str) or not expected_account.strip():
        errors.append(f"{platform}: expected account must be configured")
    if receipt.get("account_id") != expected_account:
        errors.append(f"{platform}: receipt account differs from the configured account")
    if not isinstance(master_sha256, str) or not SHA256_PATTERN.fullmatch(master_sha256):
        errors.append(f"{platform}: valid master SHA-256 is required")
    if receipt.get("master_sha256") != master_sha256:
        errors.append(f"{platform}: published master hash mismatch")
    if receipt.get("public_verified") is not True:
        errors.append(f"{platform}: public reachability was not verified")
    if not _evidence(receipt.get("evidence")):
        errors.append(f"{platform}: public verification evidence is required")
    url = receipt.get("url")
    valid_url = False
    if isinstance(url, str):
        try:
            parsed = urlsplit(url)
            if platform == "youtube":
                path_valid = re.fullmatch(r"/shorts/[A-Za-z0-9_-]{11}", parsed.path)
                host_valid = parsed.netloc == "www.youtube.com"
            else:
                path_valid = re.fullmatch(r"/@[A-Za-z0-9_.]+/video/[0-9]{10,25}", parsed.path)
                host_valid = parsed.netloc == "www.tiktok.com"
                if isinstance(expected_account, str) and expected_account.startswith("@"):
                    host_valid = host_valid and parsed.path.split("/")[1] == expected_account
            valid_url = (
                parsed.scheme == "https" and host_valid and bool(path_valid)
                and not parsed.query and not parsed.fragment
                and not any(character.isspace() for character in url)
            )
        except ValueError:
            pass
    if not valid_url:
        errors.append(f"{platform}: canonical HTTPS public video URL is required")
    return errors


def validate_publications(package, master_path, expected_accounts):
    """Require public verification of YouTube and TikTok for the same master."""
    errors = []
    actual = _artifact_hash(master_path, errors, "master")
    if not isinstance(package, dict):
        return errors + ["publications package must be an object"]
    if not isinstance(expected_accounts, dict):
        return errors + ["expected platform accounts must be configured"]
    for platform in PLATFORMS:
        errors.extend(validate_publication_receipt(
            package.get(platform), platform, actual, expected_accounts.get(platform)
        ))
    return errors
