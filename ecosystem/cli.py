"""Small local command surface, designed for scheduled calls and human review."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .config import ROOT, load_channels, read_json, readiness, write_json

def main(argv=None):
    parser = argparse.ArgumentParser(description="Ecosistema central de reels")
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("status", "readiness", "questionnaire", "doctor", "dashboard", "usage"):
        sub.add_parser(command)
    daily = sub.add_parser("daily", help="Preparar o reanudar un trabajo por canal; no publica")
    daily.add_argument("--date")
    onboard = sub.add_parser("onboard", help="Registrar una ficha de canal nuevo")
    onboard.add_argument("--answers", type=Path, required=True)
    dispatch = sub.add_parser("dispatch-packet", help="Preparar cápsula con modelo y entradas mínimas")
    dispatch.add_argument("--job", required=True)
    dispatch.add_argument("--role", choices=["creative", "visual", "quality", "release", "metadata"], required=True)
    dispatch.add_argument("--artifact", action="append", default=[])
    worker = sub.add_parser("run-stage", help="Ejecutar una etapa local con su modelo; por defecto solo prepara")
    worker.add_argument("--job", required=True)
    worker.add_argument("--role", choices=["creative", "visual", "quality", "release", "metadata"], required=True)
    worker.add_argument("--artifact", action="append", default=[])
    worker.add_argument("--execute", action="store_true")
    inspect = sub.add_parser("media-probe")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--decode", action="store_true")
    receipt = sub.add_parser("validate-receipt")
    receipt.add_argument("--packet", type=Path, required=True)
    receipt.add_argument("--receipt", type=Path, required=True)
    index = sub.add_parser("index-source", help="Indexar una fuente local una sola vez")
    index.add_argument("--source-id", required=True)
    index.add_argument("--path", type=Path, required=True)
    search = sub.add_parser("search-source", help="Recuperar solo pasajes relevantes")
    search.add_argument("--source-id", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=5)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command == "questionnaire":
            from .onboarding import questionnaire
            result = questionnaire(root)
        elif args.command == "onboard":
            from .onboarding import create_channel
            result = create_channel(read_json(args.answers), root)
        elif args.command in {"daily", "dashboard"}:
            from .planner import plan_daily
            result = plan_daily(root, getattr(args, "date", None))
            write_json(root / ".runtime/latest-plan.json", result)
            if args.command == "dashboard":
                from .dashboard import build_dashboard
                target = root / ".runtime/dashboard.html"
                build_dashboard(load_channels(root), result, target)
                result = {"status": result["status"], "path": str(target)}
        elif args.command == "readiness":
            local_path = root / "local.json"
            local = read_json(local_path) if local_path.exists() else {}
            settings = read_json(root / "config/ecosystem.json")
            result = {c["id"]: readiness(c, local, settings) for c in load_channels(root)}
        elif args.command == "status":
            from .store import Store
            with Store(root / ".runtime/production.sqlite3") as store:
                result = {"channels": [{"id": c["id"], "name": c["name"], "lifecycle": c["lifecycle"]} for c in load_channels(root)], "jobs": store.list_jobs()}
        elif args.command == "doctor":
            from .media import discover
            result = discover()
        elif args.command == "media-probe":
            from .media import probe, decode
            result = {"probe": probe(args.path)}
            if args.decode:
                result["decode"] = decode(args.path)
        elif args.command == "dispatch-packet":
            from .dispatch import build_packet
            result = build_packet(args.job, args.role, args.artifact, root)
            result.pop("stdin")  # Stored packet supplies it without repeating it in every log.
        elif args.command == "run-stage":
            from .worker import run_stage
            result = run_stage(args.job, args.role, args.artifact, root=root, execute=args.execute)
        elif args.command == "usage":
            from .worker import usage_report
            result = usage_report(root)
        elif args.command == "validate-receipt":
            from .dispatch import validate_receipt
            errors = validate_receipt(read_json(args.receipt), read_json(args.packet))
            result = {"status": "FAIL" if errors else "PASS", "errors": errors}
        elif args.command in {"index-source", "search-source"}:
            from .corpus import Corpus
            corpus = Corpus(root / ".runtime/corpus.sqlite3")
            result = corpus.index(args.source_id, args.path) if args.command == "index-source" else corpus.search(args.source_id, args.query, args.limit)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 1 if isinstance(result, dict) and result.get("status") == "FAIL" else 0
    except (ValueError, OSError, KeyError, RuntimeError, StopIteration) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
