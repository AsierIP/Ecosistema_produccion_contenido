"""Channel discovery never creates identities or marks a new brand approved."""
from __future__ import annotations
import re
import unicodedata
from .config import ROOT, read_json, write_json, channel_errors

def slug(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if not value:
        raise ValueError("El nombre necesita letras o números")
    return value

def questionnaire(root=ROOT):
    return read_json(root / "config/onboarding.json")

def create_channel(answers: dict, root=ROOT):
    for field in ("name", "theme", "sources", "visual_style"):
        if not answers.get(field):
            raise ValueError(f"Falta {field}")
    if not isinstance(answers["sources"], list) or any(not isinstance(s, dict) or not s.get("id") or not s.get("title") for s in answers["sources"]):
        raise ValueError("sources debe contener objetos con id y title")
    channel_id = slug(answers["name"])
    record = {
        "schema_version": 1, "id": channel_id, "name": answers["name"],
        "theme": answers["theme"], "audience": answers.get("audience"),
        "language": answers.get("language", "es-ES"), "lifecycle": "discovery",
        "sources": answers["sources"], "editorial_policy": answers.get("editorial_policy", "source_grounded_original_adaptation"),
        "visual": {"style": answers["visual_style"], "approved": False, "profile": "natural-variable-v1"},
        "voice": {"provider": answers.get("voice_provider"), "id": answers.get("voice_id"), "approved": False, "retiming": False},
        "branding": {"status": "brief_pending", "brief": answers.get("branding_brief")},
        "platforms": {p: {"enabled": True, "account": answers.get(p + "_account")} for p in ("youtube", "tiktok")},
        "release": {"mode": answers.get("release_mode", read_json(root / 'config/ecosystem.json').get('youtube_release', {}).get('mode', 'awaiting_user_policy')), "ai_disclosure": True},
        "daily_reels": 1, "migration": {"canary_passed": False, "legacy_writer_reconciled": True},
    }
    errors = channel_errors(record)
    if errors:
        raise ValueError("; ".join(errors))
    path = root / "channels" / (channel_id + ".json")
    write_json(path, record, exclusive=True)
    return {"status": "discovery", "path": str(path), "channel": record}
