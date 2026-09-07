"""Build compact, hash-bound work orders. This module never invokes a model."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from .cache import cache_key, file_hash
from .config import ROOT, load_channels, read_json, write_json
from .store import Store

ROLE_STAGES = {"creative": "script", "visual": "assets", "quality": "qa", "release": "publish", "metadata": "script"}

def build_packet(job_id, role, artifacts=(), root=ROOT):
    if role not in ROLE_STAGES:
        raise ValueError("Unknown agent role")
    with Store(root / ".runtime/production.sqlite3") as store:
        job = store.get_job(job_id)
        if not job:
            raise ValueError("Unknown job")
        intents = store.list_intents(job_id)
    channel = next(c for c in load_channels(root) if c["id"] == job["channel_id"])
    models = read_json(root / "config/models.json")
    routing = dict(models["roles"][role])
    routing.update(models.get("channel_role_overrides", {}).get(channel["id"], {}).get(role, {}))
    refs = []
    for artifact in artifacts:
        path = Path(artifact).resolve(strict=True)
        if not path.is_file():
            raise ValueError("Artifact must be a file")
        refs.append({"path": str(path), "sha256": file_hash(path), "bytes": path.stat().st_size})
    if job["state"] == "complete":
        raise ValueError("El trabajo ya está completo; no se prepara otra ejecución")
    prompt_path = root / "prompts" / (role + ".md")
    prompt = prompt_path.read_text(encoding="utf-8")
    profile_path = root / "config/profiles" / (channel["visual"]["profile"] + ".json")
    profile = read_json(profile_path)
    # Channel-approved narration speed overrides the shared profile's default.
    # Keep the same effective profile in review and release validation.
    profile = {**profile, 'voice_speed_factor': channel['voice'].get('speed_factor', 1.0)}
    release_policy = read_json(root / 'config/ecosystem.json').get('youtube_release', {})
    review_path = root / 'config/review.json'
    review_policy = read_json(review_path) if review_path.exists() else {}
    prompt += '\nPolítica vigente de revisión: ' + json.dumps(review_policy, ensure_ascii=False)
    fingerprint = cache_key(channel_id=channel["id"], stage=role, policy={"channel": channel, "visual": profile, "prompt": prompt, "youtube_release": release_policy, "receipt_schema": read_json(root / "config/receipt.schema.json"), "runner_limits": models.get("runner_limits", {}), "validator_version": 2}, inputs=refs, model=routing)
    output = root / ".runtime/jobs" / job_id / role / fingerprint[:16]
    packet = {
        "schema_version": 1, "job_id": job_id, "job_version": job["version"],
        "channel": channel, "role": role, "stage": ROLE_STAGES[role], "model": routing,
        "profile": profile, "instructions": prompt, "inputs": refs,
        "youtube_release": release_policy,
        "review_policy": review_policy,
        "unresolved_intents": [i for i in intents if i["state"] != "verified"],
        "output_directory": str(output), "cache_key": fingerprint,
        "receipt_schema": str(root / "config/receipt.schema.json"),
        "constraints": {"only_write_output_directory": True, "no_secrets": True, "target_output_tokens": routing["target_output_tokens"], "no_nested_agents": True},
    }
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True)
    if len(encoded) > routing["max_input_chars"]:
        raise ValueError("La cápsula supera el presupuesto de contexto; reduce las entradas")
    output.mkdir(parents=True, exist_ok=True)
    packet_path = output / "packet.json"
    write_json(packet_path, packet)
    receipt = output / "receipt.json"
    command = [shutil.which("codex") or "codex", "exec", "--model", routing["model"],
               "-c", 'forced_login_method="chatgpt"',
               "-c", f'model_reasoning_effort="{routing["effort"]}"',
               "--sandbox", "workspace-write", "--cd", str(root),
               "--output-schema", str(root / "config/receipt.schema.json"),
               "--output-last-message", str(receipt), "--json", "-"]
    return {"packet_path": str(packet_path), "receipt_path": str(receipt), "argv": command,
            "stdin": "Ejecuta exclusivamente esta cápsula y devuelve su recibo JSON.\n" + encoded,
            "input_chars": len(encoded), "status": "PREPARED", "model": routing["model"], "cache_key": fingerprint}

def validate_receipt(receipt, packet):
    if not isinstance(receipt, dict) or not isinstance(packet, dict):
        return ["receipt and packet must be objects"]
    errors = []
    for field in ("job_id", "role"):
        if receipt.get(field) != packet.get(field):
            errors.append(f"receipt {field} mismatch")
    if receipt.get("decision") not in {"ACCEPT", "REJECT", "BLOCK"}:
        errors.append("invalid receipt decision")
    output = Path(packet["output_directory"]).resolve()
    artifacts = receipt.get("artifacts")
    checks = receipt.get("checks")
    if not isinstance(artifacts, list) or not isinstance(checks, list):
        return errors + ["artifacts and checks must be lists"]
    for artifact in artifacts:
        try:
            path = Path(artifact["path"]).resolve(strict=True)
            if not path.is_relative_to(output):
                errors.append("artifact outside work order output")
            if file_hash(path) != artifact.get("sha256") or path.stat().st_size != artifact.get("bytes"):
                errors.append("artifact hash or size mismatch")
        except (ValueError, OSError, KeyError, TypeError):
            errors.append("invalid artifact")
    allowed_inputs = {str(Path(ref["path"]).resolve()): ref for ref in packet.get("inputs", [])}
    reviewed = receipt.get("inputs_reviewed", [])
    if not isinstance(reviewed, list):
        errors.append("inputs_reviewed must be a list")
    else:
        for ref in reviewed:
            try:
                path = Path(ref["path"]).resolve(strict=True)
                expected = allowed_inputs.get(str(path))
                if expected is None or ref.get("sha256") != expected["sha256"] or ref.get("bytes") != expected["bytes"]:
                    errors.append("reviewed input not bound to work order")
                elif file_hash(path) != ref["sha256"] or path.stat().st_size != ref["bytes"]:
                    errors.append("reviewed input hash or size mismatch")
            except (ValueError, OSError, KeyError, TypeError):
                errors.append("invalid reviewed input")
    if receipt.get("decision") == "ACCEPT":
        if not artifacts or not checks:
            errors.append("ACCEPT requires artifacts and checks")
        if any(not isinstance(c, dict) or c.get("passed") is not True or not c.get("evidence") for c in checks):
            errors.append("ACCEPT contains missing or failed checks")
        if receipt.get("blockers"):
            errors.append("ACCEPT contains blockers")
    return errors
