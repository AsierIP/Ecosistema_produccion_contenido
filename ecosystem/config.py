"""Portable configuration; machine-specific paths never enter channel profiles."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def write_json(path: Path, value, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")

def channel_errors(channel: dict) -> list[str]:
    if not isinstance(channel, dict):
        return ["channel must be an object"]
    errors = []
    if channel.get("schema_version") != 1:
        errors.append("unsupported channel schema_version")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(channel.get("id", ""))):
        errors.append("invalid channel id")
    for field in ("name", "theme", "language"):
        if not isinstance(channel.get(field), str) or not channel[field].strip():
            errors.append(f"missing {field}")
    if channel.get("daily_reels") != 1 or isinstance(channel.get("daily_reels"), bool):
        errors.append("this version supports exactly one reel per day")
    if channel.get("lifecycle") not in {"discovery", "migration", "active", "paused"}:
        errors.append("invalid lifecycle")
    for field in ("visual", "voice", "platforms", "release", "migration"):
        if not isinstance(channel.get(field), dict):
            errors.append(f"{field} must be an object")
    if not isinstance(channel.get("sources"), list) or not channel.get("sources"):
        errors.append("at least one source is required")
    return errors

def load_channels(root=ROOT) -> list[dict]:
    channels = []
    for path in sorted((Path(root) / "channels").glob("*.json")):
        channel = read_json(path)
        errors = channel_errors(channel)
        if path.stem != channel.get("id"):
            errors.append("file name does not match channel id")
        if errors:
            raise ValueError(f"{path.name}: {'; '.join(errors)}")
        channels.append(channel)
    return channels

def readiness(channel: dict, local: dict, settings: dict) -> list[str]:
    errors = channel_errors(channel)
    if errors:
        return errors
    blockers = []
    if channel["lifecycle"] == "paused":
        blockers.append("Canal pausado")
    if not channel["visual"].get("approved"):
        blockers.append("Falta aprobar la biblia visual")
    if channel["visual"].get("production_animation_qualified") is False:
        blockers.append("Estilo elegido; falta validar la animación de producción")
    if not channel["voice"].get("approved") or not channel["voice"].get("id"):
        blockers.append("Falta fijar la voz")
    if not channel.get("audience"):
        blockers.append("Falta definir el público y las exclusiones editoriales")
    enabled = [(name, data) for name, data in channel["platforms"].items() if data.get("enabled")]
    if not enabled:
        blockers.append("No hay destinos habilitados")
    for name, data in enabled:
        if name not in {"youtube", "tiktok"} or not data.get("account"):
            blockers.append(f"Falta la cuenta exacta de {name}")
        elif data.get("verification_status") and data["verification_status"] != "verified":
            blockers.append(f"Cuenta de {name} registrada; falta verificar la identidad de la sesión")
    if channel["release"].get("mode") not in {"automatic_after_qa", "manual_review"}:
        blockers.append("Falta fijar la política de publicación")
    if not channel["migration"].get("legacy_writer_reconciled"):
        blockers.append("Falta reconciliar el productor anterior para evitar duplicados")
    if not channel["migration"].get("canary_passed"):
        blockers.append("Falta validar el primer reel completo con el núcleo central")
    machine = local.get("channels", {}).get(channel["id"], {})
    for source in channel["sources"]:
        source_path = machine.get("source_paths", {}).get(source["id"])
        if not source_path or not Path(source_path).exists():
            blockers.append(f"Fuente local no disponible: {source['id']}")
    if not machine.get("provider_profile"):
        blockers.append("Falta vincular el perfil exclusivo del proveedor visual")
    elif machine.get("provider_identity", {}).get("status") not in {None, "verified"}:
        blockers.append("Correo de Vibes asignado; falta verificar la sesión del proveedor")
    if not settings.get("automatic_execution_enabled"):
        blockers.append("Ejecución central pendiente de activación tras la migración")
    return blockers
