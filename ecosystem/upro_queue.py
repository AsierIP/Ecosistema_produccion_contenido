"""Durable, bounded local steps. HTTP never accepts commands or file paths.

Plans are prepared locally by the production code, then consumed by Upro.
Read-only validation may run before migration; production never bypasses readiness.
Remote visuals, TTS and publication have no qualified unattended adapter yet.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

from .cache import file_hash
from .config import read_json, write_json

ADAPTERS = {"creative", "metadata", "quality", "media_check", "cutout", "ambient"}
GPU_ADAPTERS = {"cutout", "ambient"}


class Queue:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / ".runtime/upro/steps.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS steps (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL, channel_id TEXT NOT NULL,
                adapter TEXT NOT NULL, mode TEXT NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL, result TEXT, created REAL NOT NULL, updated REAL NOT NULL)""")

    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        return closing_transaction(con)

    def register(self, plan):
        if plan.get("schema_version") != 1 or plan.get("adapter") not in ADAPTERS:
            raise ValueError("Adaptador no disponible o formato de etapa incorrecto")
        from .store import Store
        with Store(self.root / ".runtime/production.sqlite3") as store:
            job = store.get_job(plan.get("job_id"))
        if not job or job["state"] == "complete" or job["channel_id"] != plan.get("channel_id"):
            raise ValueError("Trabajo inexistente, terminado o de otro canal")
        mode = plan.get("mode", "production")
        if mode not in {"production", "validation"} or (mode == "validation" and plan["adapter"] != "media_check"):
            raise ValueError("Antes de la migración solo se admite inspección de medios sin efectos externos")
        inputs = plan.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            raise ValueError("La etapa necesita entradas explícitas y sus hashes")
        for ref in inputs:
            path = Path(ref["path"])
            if not path.is_absolute() or not path.is_file() or file_hash(path) != ref.get("sha256"):
                raise ValueError("Entrada ausente, no absoluta o modificada")
        dependencies = plan.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise ValueError("Dependencias incorrectas")
        plan = {**plan, "mode": mode, "depends_on": dependencies}
        encoded = json.dumps(plan, sort_keys=True, ensure_ascii=False)
        if len(encoded) > 32768:
            raise ValueError("Plan demasiado grande; usar referencias a artefactos")
        key = hashlib.sha256(encoded.encode()).hexdigest()
        with self.connect() as con:
            for dep in dependencies:
                row = con.execute("SELECT job_id FROM steps WHERE id=?", (dep,)).fetchone()
                if not row or row["job_id"] != plan["job_id"]:
                    raise ValueError("Dependencia inexistente o de otro trabajo")
            con.execute("INSERT OR IGNORE INTO steps VALUES(?,?,?,?,?,?,'queued',NULL,?,?)",
                        (key, plan["job_id"], plan["channel_id"], plan["adapter"], mode, encoded, time.time(), time.time()))
        return key

    def recover(self):
        # No blind retries after app/PC interruption, even for local render outputs.
        with self.connect() as con:
            con.execute("UPDATE steps SET state='uncertain',updated=? WHERE state='running'", (time.time(),))

    def list(self, channel=None):
        with self.connect() as con:
            sql = "SELECT * FROM steps" + (" WHERE channel_id=?" if channel else "") + " ORDER BY created,id"
            rows = con.execute(sql, (channel,) if channel else ()).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"]),
                 "result": json.loads(row["result"]) if row["result"] else None} for row in rows]

    def claim(self, step_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT * FROM steps WHERE id=?", (step_id,)).fetchone()
            if not row or row["state"] != "queued":
                return False
            plan = json.loads(row["payload"])
            if con.execute("SELECT 1 FROM steps WHERE channel_id=? AND state IN ('running','uncertain')", (row["channel_id"],)).fetchone():
                return False
            for dep in plan["depends_on"]:
                found = con.execute("SELECT state FROM steps WHERE id=?", (dep,)).fetchone()
                if not found or found[0] != "accepted":
                    return False
            return bool(con.execute("UPDATE steps SET state='running',updated=? WHERE id=? AND state='queued'", (time.time(), step_id)).rowcount)

    def finish(self, step_id, result, state):
        if state not in {"accepted", "blocked", "uncertain"}:
            raise ValueError("Invalid outcome")
        with self.connect() as con:
            con.execute("UPDATE steps SET state=?,result=?,updated=? WHERE id=? AND state='running'",
                        (state, json.dumps(result, ensure_ascii=False), time.time(), step_id))

    def retire(self, step_id, evidence):
        """Archive an inspected failure; never reset or replay the old operation."""
        if not isinstance(evidence, dict) or evidence.get("checked") is not True or not evidence.get("reason"):
            raise ValueError("La reconciliación necesita checked=true y motivo documentado")
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT state FROM steps WHERE id=?", (step_id,)).fetchone()
            if not row or row["state"] not in {"blocked", "uncertain"}:
                raise ValueError("Solo se pueden reconciliar etapas bloqueadas o inciertas")
            con.execute("UPDATE steps SET state='reconciled',result=?,updated=? WHERE id=?",
                        (json.dumps({"reconciliation": evidence}, ensure_ascii=False), time.time(), step_id))


class closing_transaction:
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        return self.connection
    def __exit__(self, kind, value, tb):
        try:
            self.connection.rollback() if kind else self.connection.commit()
        finally:
            self.connection.close()


def execute_step(root, step):
    """Only statically registered adapters, no shell or arbitrary executable."""
    root = Path(root)
    plan = step["payload"]
    paths = []
    for ref in plan["inputs"]:
        path = Path(ref["path"])
        if file_hash(path) != ref["sha256"]:
            raise ValueError("Una entrada cambió; preparar una nueva etapa")
        paths.append(path)
    out = root / ".runtime/upro/results" / step["id"]
    out.mkdir(parents=True, exist_ok=True)
    adapter = plan["adapter"]
    if adapter in {"creative", "metadata", "quality"}:
        from .worker import run_stage
        result = run_stage(plan["job_id"], adapter, paths, root=root, execute=True)
        accepted = result.get("status") == "ACCEPTED" or (result.get("status") == "ALREADY_RECORDED" and result.get("run", {}).get("state") == "accepted")
    elif adapter == "media_check":
        from .media import probe, decode
        if len(paths) != 1:
            raise ValueError("La inspección requiere un solo máster")
        result = {"probe": probe(paths[0]), "decode": decode(paths[0]),
                  "master_sha256": file_hash(paths[0]), "path": str(paths[0]),
                  "editorial_qa": "pending", "audiovisual_qa": "pending", "published": False}
        accepted = result["probe"]["ok"] and result["decode"]["ok"]
    elif adapter == "cutout":
        from .cutout import render
        result = render(paths[0], root=root)
        accepted = result.get("status") == "TECHNICAL_PASS"
    elif adapter == "ambient":
        from .media import discover
        runtime = discover().get("gpu_python")
        if not runtime:
            raise ValueError("Falta el intérprete CUDA instalado")
        # Existing renderer owns and renews the global GPU lease itself.
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        with (out / "render.log").open("w", encoding="utf-8") as log:
            run = subprocess.run([runtime, str(root / "scripts/render-ambient.py"), str(paths[0])],
                                 stdout=log, stderr=log, stdin=subprocess.DEVNULL, shell=False,
                                 timeout=1800, creationflags=flags)
        if run.returncode:
            raise RuntimeError("La animación falló; revisar el registro local")
        result = read_json(Path(read_json(paths[0])["evidence"]))
        accepted = result.get("status") == "TECHNICAL_PASS"
    else:
        raise ValueError("Adaptador no cualificado")
    # Verify that data supplied to the stage were not edited while it ran.
    if any(file_hash(Path(ref["path"])) != ref["sha256"] for ref in plan["inputs"]):
        raise ValueError("Entrada alterada durante la ejecución")
    write_json(out / "result.json", result)
    return result, "accepted" if accepted else "blocked"
