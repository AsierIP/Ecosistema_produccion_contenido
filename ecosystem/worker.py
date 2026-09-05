"""Execute a prepared local agent stage once; never equate a receipt with release.

Remote visual generation and release need a qualified platform adapter. This
runner intentionally exposes only editorial, metadata and independent QA stages.
"""
from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from .config import ROOT, read_json, write_json
from .dispatch import build_packet, validate_receipt

def run_stage(job_id, role, artifacts=(), *, root=ROOT, execute=False, timeout=1800):
    packet = build_packet(job_id, role, artifacts, root)
    if not execute:
        return {k:v for k,v in packet.items() if k != "stdin"}
    if role not in {"creative", "metadata", "quality"}:
        return {"status": "BLOCKED", "reason": "La generación remota y publicación requieren un adaptador cualificado; la cápsula está preparada"}
    if not artifacts:
        return {"status": "BLOCKED", "reason": "Faltan entradas concretas: ficha de fuentes, guion aprobado o máster con evidencias según la etapa"}
    with closing(sqlite3.connect(root / ".runtime/agent-runs.sqlite3", isolation_level=None)) as con:
        con.row_factory = sqlite3.Row
        con.execute("CREATE TABLE IF NOT EXISTS runs(cache_key TEXT PRIMARY KEY, job_id TEXT, role TEXT, state TEXT, model TEXT, started REAL, elapsed REAL, input_tokens INTEGER, output_tokens INTEGER, cached_input_tokens INTEGER, receipt_path TEXT)")
        con.execute("BEGIN IMMEDIATE")
        old = con.execute("SELECT * FROM runs WHERE cache_key=?", (packet["cache_key"],)).fetchone()
        if old:
            con.rollback()
            return {"status": "ALREADY_RECORDED", "run": dict(old), "reason": "Revisar el recibo anterior; no se vuelve a consumir tokens"}
        unresolved = con.execute("SELECT 1 FROM runs WHERE job_id=? AND role=? AND state IN ('running','uncertain')", (job_id, role)).fetchone()
        if unresolved:
            con.rollback()
            return {"status": "BLOCKED", "reason": "Hay una ejecución anterior activa o incierta; reconciliarla primero"}
        attempts = con.execute("SELECT COUNT(*) FROM runs WHERE job_id=? AND role=?", (job_id, role)).fetchone()[0]
        maximum = read_json(root / "config/models.json")["max_attempts_per_stage"]
        if attempts >= maximum:
            con.rollback()
            return {"status": "BLOCKED", "reason": "Presupuesto de intentos de esta etapa agotado"}
        started = time.time()
        con.execute("INSERT INTO runs(cache_key,job_id,role,state,model,started,receipt_path) VALUES(?,?,?,'running',?,?,?)", (packet["cache_key"], job_id, role, packet["model"], started, packet["receipt_path"]))
        con.commit()
        output = Path(packet["packet_path"]).parent
        events_path = output / "events.jsonl"
        error_path = output / "worker.stderr.txt"
        state = "blocked"
        usage = {"input_tokens": None, "output_tokens": None, "cached_input_tokens": None}
        errors = []
        try:
            with events_path.open("w", encoding="utf-8") as events, error_path.open("w", encoding="utf-8") as error:
                completed = subprocess.run(packet["argv"], input=packet["stdin"], stdout=events, stderr=error,
                                           text=True, encoding="utf-8", timeout=timeout, shell=False, check=False)
            for line in events_path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                    for key in usage:
                        value = event["usage"].get(key)
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                            usage[key] = (usage[key] or 0) + value
            if completed.returncode:
                errors.append(f"El agente terminó con código {completed.returncode}; revisar el registro local")
            else:
                receipt = read_json(Path(packet["receipt_path"]))
                errors.extend(validate_receipt(receipt, read_json(Path(packet["packet_path"]))))
                if not errors:
                    state = "accepted" if receipt["decision"] == "ACCEPT" else "blocked"
        except subprocess.TimeoutExpired:
            state = "uncertain"
            errors.append("Tiempo máximo excedido; reconciliar los artefactos antes de otro intento")
        except (OSError, ValueError, KeyError) as exc:
            errors.append(str(exc))
        elapsed = time.time() - started
        con.execute("UPDATE runs SET state=?,elapsed=?,input_tokens=?,output_tokens=?,cached_input_tokens=? WHERE cache_key=?", (state, elapsed, usage["input_tokens"], usage["output_tokens"], usage["cached_input_tokens"], packet["cache_key"]))
        report = {"status": state.upper(), "job_id": job_id, "role": role, "model": packet["model"], "elapsed_seconds": round(elapsed, 2), "usage": usage, "errors": errors, "receipt_path": packet["receipt_path"], "recorded_at": datetime.now(timezone.utc).isoformat(), "production_complete": False}
        write_json(output / "execution.json", report)
        return report

def usage_report(root=ROOT):
    path = root / ".runtime/agent-runs.sqlite3"
    if not path.exists():
        return {"runs": 0, "input_tokens": None, "output_tokens": None, "note": "Sin ejecuciones de agentes registradas"}
    with closing(sqlite3.connect(path)) as con:
        con.row_factory = sqlite3.Row
        return {"by_role": [dict(row) for row in con.execute("SELECT role, model, COUNT(*) runs, SUM(elapsed) elapsed_seconds, SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens, SUM(cached_input_tokens) cached_input_tokens FROM runs GROUP BY role,model")], "note": "Datos ausentes son null; esta cuenta no incluye el trabajo de desarrollo en Codex"}
