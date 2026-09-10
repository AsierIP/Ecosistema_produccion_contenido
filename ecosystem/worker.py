"""Execute a prepared local agent stage once; never equate a receipt with release.

ImageGen is supported for one scene per request. Other remote visual providers
and release still need a qualified platform adapter.
"""
from __future__ import annotations
from contextlib import closing
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from .cache import file_hash
import sqlite3
import subprocess
import time
from .config import ROOT, read_json, write_json
from .dispatch import build_packet, validate_receipt


def subscription_environment():
    """Use the subscription without inheriting another app task's IPC identity.

    Security/sandbox variables and installed tool configuration are preserved.
    The caller's session pipe may disappear or wait forever after that task ends.
    """
    return {key: value for key, value in os.environ.items()
            if key.upper() not in {'OPENAI_API_KEY', 'CODEX_API_KEY',
                                  'CODEX_APP_TOOLS_PIPE_PATH', 'CODEX_THREAD_ID',
                                  'CODEX_SESSION_ID', 'CODEX_INTERNAL_ORIGINATOR_OVERRIDE'}}


def visual_preflight(packet):
    if packet['channel']['visual'].get('generation_provider') != 'imagegen':
        return ['El proveedor requiere otro adaptador; no sustituir Vibes por imágenes estáticas']
    if packet['channel']['visual'].get('approved') is not True:
        return ['Falta estilo aprobado']
    requests = []
    for ref in packet['inputs']:
        path = Path(ref['path'])
        if path.suffix.lower() != '.json' or path.stat().st_size > 100_000:
            continue
        try:
            data = read_json(path)
            if isinstance(data, dict) and data.get('kind') in {'image_generation_request_v1', 'existing_image_review_v1'}:
                requests.append(data)
        except (OSError, ValueError):
            continue
    if len(requests) != 1:
        return ['Falta una petición image_generation_request_v1 única']
    request = requests[0]
    if not isinstance(request.get('scene_id'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', request['scene_id']):
        return ['Falta un scene_id estable para limitar los intentos por escena']
    reviewing_existing = request.get('kind') == 'existing_image_review_v1'
    if request.get('channel_id') != packet['channel']['id'] or request.get('image_count') != (0 if reviewing_existing else 1):
        return ['La petición debe corresponder al canal y a una sola imagen']
    if not isinstance(request.get('prompt'), str) or not 1 <= len(request['prompt']) <= 6000:
        return ['Falta un prompt visual acotado']
    if not request.get('source_basis'):
        return ['Falta la base editorial de la imagen']
    if reviewing_existing:
        ref = request.get('source_image', {})
        if not any(r.get('path') == ref.get('path') and r.get('sha256') == ref.get('sha256') for r in packet['inputs']):
            return ['La imagen existente debe estar declarada y ligada por hash']
        if not ref.get('path') or file_hash(Path(ref['path'])) != ref.get('sha256'):
            return ['La imagen existente cambió antes de su revisión']
    return []

def quality_preflight(packet):
    """Require explicit capability and technical evidence before consuming tokens.

    This gate does not assert that an independent audiovisual review has passed.
    """
    manifests = []
    for ref in packet["inputs"]:
        source = Path(ref["path"])
        try:
            if source.suffix.lower() != ".json" or source.stat().st_size > 512_000:
                continue
            value = read_json(source)
        except (OSError, ValueError, UnicodeError):
            continue
        if isinstance(value, dict) and value.get("kind") == "quality_preflight_v1":
            manifests.append(value)
    if len(manifests) != 1:
        return ["Falta un manifiesto quality_preflight_v1 único"]
    manifest = manifests[0]
    if manifest.get('scope') == 'native_segment':
        from .segment_review import validate_native_preflight
        return validate_native_preflight(packet, manifest)
    errors = []
    capabilities = manifest.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    automatic = manifest.get('automated_evidence')
    if automatic and packet.get('review_policy', {}).get('mode') == 'automatic':
        from .cache import file_hash
        try:
            declared_paths = {str(Path(r['path']).resolve()): r['sha256'] for r in packet['inputs']}
            path = Path(automatic['path'])
            if declared_paths.get(str(path.resolve())) != automatic['sha256'] or file_hash(path) != automatic['sha256']:
                raise ValueError('Automated evidence hash mismatch')
            review = read_json(path)
            if review.get('kind') != 'automated_av_evidence_v1' or review.get('status') != 'EVIDENCE_READY':
                raise ValueError('Automated evidence incomplete')
            master = Path(review['master_path'])
            if declared_paths.get(str(master.resolve())) != review['master_sha256'] or file_hash(master) != review['master_sha256']:
                raise ValueError('Automated review belongs to another master')
            evidence_keys = ['provider_response', 'local_asr'] + (['intro_asr'] if review.get('intro_asr') else [])
            for key in evidence_keys:
                ref = review[key]
                if declared_paths.get(str(Path(ref['path']).resolve())) != ref['sha256'] or file_hash(Path(ref['path'])) != ref['sha256']:
                    raise ValueError('Missing original automated review evidence')
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append(str(exc))
    else:
        for key in ("full_video_playback", "full_audio_playback"):
            if capabilities.get(key) is not True:
                errors.append("Capacidad QA ausente: " + key)
    evidence = manifest.get("technical_evidence", {})
    declared = {ref["sha256"]: ref for ref in packet["inputs"]}
    if not isinstance(evidence, dict) or not isinstance(evidence.get("sha256"), str) or evidence.get("sha256") not in declared:
        errors.append("Falta evidencia técnica declarada y ligada por hash")
    else:
        try:
            report = read_json(Path(declared[evidence["sha256"]]["path"]))
            if report.get("status") != "TECHNICAL_PASS":
                errors.append("La evidencia técnica no tiene TECHNICAL_PASS")
        except (OSError, ValueError, AttributeError):
            errors.append("Evidencia técnica ilegible")
    return errors


def collect_usage(path):
    usage = {"input_tokens": None, "output_tokens": None, "cached_input_tokens": None}
    if path.exists():
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                    for key in usage:
                        value = event["usage"].get(key)
                        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                            usage[key] = (usage[key] or 0) + value
    return usage


def retain_log_tail(path, maximum):
    # Retention cap after process termination; not a token or live disk quota.
    if path.exists() and path.stat().st_size > maximum:
        with path.open("rb") as stream:
            stream.seek(-maximum, 2)
            tail = stream.read()
        path.write_bytes(tail)
        return True
    return False


def run_stage(job_id, role, artifacts=(), *, root=ROOT, execute=False, timeout=None):
    packet = build_packet(job_id, role, artifacts, root)
    if not execute:
        return {k:v for k,v in packet.items() if k != "stdin"}
    if role not in {"creative", "metadata", "quality", "visual", "release"}:
        return {"status": "BLOCKED", "reason": "La generación remota y publicación requieren un adaptador cualificado; la cápsula está preparada"}
    if not artifacts:
        return {"status": "BLOCKED", "reason": "Faltan entradas concretas: ficha de fuentes, guion aprobado o máster con evidencias según la etapa"}
    unit_id = 'stage'
    if role == 'creative':
        from .editorial_history import creative_context_preflight
        try:
            unit_id = creative_context_preflight(read_json(Path(packet['packet_path']))) or unit_id
        except (ValueError, OSError, KeyError) as exc:
            return {'status': 'BLOCKED', 'reason': str(exc), 'agent_started': False}
    if role == 'release':
        from .release_worker import browser_preflight
        try:
            unit_id = browser_preflight(read_json(Path(packet['packet_path'])), root)['action']
        except (ValueError, OSError, KeyError, RuntimeError) as exc:
            return {'status': 'BLOCKED', 'reason': str(exc), 'agent_started': False}
    if role == 'visual':
        errors = visual_preflight(read_json(Path(packet['packet_path'])))
        if errors:
            return {'status': 'BLOCKED', 'reason': 'Visual preflight', 'errors': errors, 'agent_started': False}
        for ref in read_json(Path(packet['packet_path']))['inputs']:
            p = Path(ref['path'])
            if p.suffix.lower() == '.json' and p.stat().st_size <= 100_000:
                try:
                    value = read_json(p)
                    if isinstance(value, dict) and value.get('kind') in {'image_generation_request_v1', 'existing_image_review_v1'}:
                        unit_id = value['scene_id']
                except (OSError, ValueError):
                    continue
    if role == "quality":
        runtime_tools = read_json(Path(packet['packet_path'])).get('runtime_tools',{})
        if set(runtime_tools) != {'ffmpeg','ffprobe'}:
            return {'status':'BLOCKED','reason':'Faltan herramientas audiovisuales locales verificadas','agent_started':False}
        for tool in runtime_tools.values():
            executable = Path(tool['path'])
            if not executable.is_file() or file_hash(executable) != tool['sha256']:
                return {'status':'BLOCKED','reason':'La herramienta audiovisual cambió antes de la revisión','agent_started':False}
        preflight_errors = quality_preflight(read_json(Path(packet["packet_path"])))
        if preflight_errors:
            return {"status": "BLOCKED", "reason": "QA preflight", "errors": preflight_errors, "agent_started": False}
        # Fixed corrected contract: final-master scope plus declared executables.
        # Historical attempts retain their records; this unit has the same bounded limit.
        for artifact in artifacts:
            source = Path(artifact)
            if source.suffix == '.json' and source.stat().st_size < 100000:
                value = read_json(source)
                if isinstance(value,dict) and value.get('kind') == 'quality_preflight_v1' and value.get('scope') == 'final_master':
                    unit_id = 'final-master-tools-v2-runner-routing'
        for artifact in artifacts:
            p = Path(artifact)
            if p.suffix == '.json' and p.stat().st_size < 100000:
                value = read_json(p)
                if isinstance(value, dict) and value.get('kind') == 'quality_preflight_v1' and value.get('scope') == 'native_segment':
                    unit_id = value['unit_id']
    limits = read_json(root / "config/models.json").get("runner_limits", {})
    native_context = None
    if role == 'quality':
        from .native_judge import prepare
        native_context = prepare(packet, root)
    configured_timeout = limits.get("timeout_seconds_by_role", {}).get(role, 300)
    timeout = min(timeout, configured_timeout) if timeout is not None else configured_timeout
    with closing(sqlite3.connect(root / ".runtime/agent-runs.sqlite3", isolation_level=None)) as con:
        con.row_factory = sqlite3.Row
        con.execute("BEGIN IMMEDIATE")
        con.execute("CREATE TABLE IF NOT EXISTS runs(cache_key TEXT PRIMARY KEY, job_id TEXT, role TEXT, state TEXT, model TEXT, started REAL, elapsed REAL, input_tokens INTEGER, output_tokens INTEGER, cached_input_tokens INTEGER, receipt_path TEXT)")
        if 'unit_id' not in {r['name'] for r in con.execute('PRAGMA table_info(runs)')}:
            con.execute("ALTER TABLE runs ADD COLUMN unit_id TEXT NOT NULL DEFAULT 'stage'")
        old = con.execute("SELECT * FROM runs WHERE cache_key=?", (packet["cache_key"],)).fetchone()
        if old:
            con.rollback()
            if old["state"] == "accepted":
                try:
                    prior_errors = validate_receipt(read_json(Path(old["receipt_path"])), read_json(Path(packet["packet_path"])))
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    prior_errors = [str(exc)]
                if prior_errors:
                    return {"status": "BLOCKED", "reason": "El resultado guardado cambió o perdió evidencias", "errors": prior_errors, "agent_started": False}
            return {"status": "ALREADY_RECORDED", "run": dict(old), "reason": "Revisar el recibo anterior; no se vuelve a consumir tokens"}
        unresolved = con.execute("SELECT 1 FROM runs WHERE job_id=? AND role=? AND state IN ('running','uncertain')", (job_id, role)).fetchone()
        if unresolved:
            con.rollback()
            return {"status": "BLOCKED", "reason": "Hay una ejecución anterior activa o incierta; reconciliarla primero"}
        attempts = con.execute("SELECT COUNT(*) FROM runs WHERE job_id=? AND role=? AND unit_id=?", (job_id, role, unit_id)).fetchone()[0]
        maximum = read_json(root / "config/models.json")["max_attempts_per_stage"]
        if attempts >= maximum:
            con.rollback()
            return {"status": "BLOCKED", "reason": "Presupuesto de intentos de esta etapa agotado"}
        started = time.time()
        con.execute("INSERT INTO runs(cache_key,job_id,role,state,model,started,receipt_path,unit_id) VALUES(?,?,?,'running',?,?,?,?)", (packet["cache_key"], job_id, role, packet["model"], started, packet["receipt_path"], unit_id))
        con.commit()
        output = Path(packet["packet_path"]).parent
        events_path = output / "events.jsonl"
        error_path = output / "worker.stderr.txt"
        state = "blocked"
        usage = {"input_tokens": None, "output_tokens": None, "cached_input_tokens": None}
        errors = []
        blockers = []
        try:
            operation = None
            if role == 'release':
                from .release_worker import start_operation
                operation = start_operation(read_json(Path(packet['packet_path'])), root)
            if role == 'visual':
                from .visual_worker import prepare_intent
                prepare_intent(read_json(Path(packet['packet_path'])))
            with events_path.open("w", encoding="utf-8") as events, error_path.open("w", encoding="utf-8") as error:
                completed = subprocess.run(packet["argv"], input=packet["stdin"], stdout=events, stderr=error,
                                           text=True, encoding="utf-8", timeout=timeout, shell=False, check=False,
                                           env=subscription_environment(),
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode:
                errors.append(f"El agente terminó con código {completed.returncode}; revisar el registro local")
            else:
                if native_context:
                    from .native_judge import seal
                    receipt = seal(native_context)
                else:
                    receipt = read_json(Path(packet["receipt_path"]))
                blockers = receipt.get('blockers', [])
                if role == 'visual':
                    from .visual_worker import seal_receipt
                    write_json(output / 'agent-response.json', receipt)
                    receipt = seal_receipt(receipt, read_json(Path(packet['packet_path'])))
                    write_json(Path(packet['receipt_path']), receipt)
                errors.extend(validate_receipt(receipt, read_json(Path(packet["packet_path"]))))
                if role == 'visual' and receipt.get('decision') == 'ACCEPT':
                    pictures = [Path(a['path']) for a in receipt.get('artifacts', []) if Path(a['path']).suffix.lower() == '.png']
                    if len(pictures) != 1 or pictures[0].read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                        errors.append('La etapa visual necesita exactamente una imagen PNG real')
                if not errors:
                    if role == 'release' and receipt['decision'] == 'ACCEPT':
                        from .release_worker import finish_operation
                        expected_result = (output / 'youtube-result.json').resolve()
                        if not any(Path(a['path']).resolve() == expected_result for a in receipt['artifacts']):
                            raise ValueError('Missing declared YouTube operation receipt')
                        finish_operation(read_json(Path(packet['packet_path'])), root, operation)
                    state = "accepted" if receipt["decision"] == "ACCEPT" else "blocked"
        except subprocess.TimeoutExpired:
            state = "uncertain"
            errors.append("Tiempo máximo excedido; reconciliar los artefactos antes de otro intento")
            if role == 'quality' and not native_context:
                try:
                    from .final_qa_receipt import seal_completed_native_report
                    seal_completed_native_report(read_json(Path(packet['packet_path'])))
                    state = 'accepted'
                    errors = []
                    write_json(output / 'timeout-recovery.json', {'kind': 'completed_independent_report',
                        'provider_calls': 0, 'previous_outcome': 'timeout_after_saved_qa',
                        'judgment_changed': False}, exclusive=True)
                except (ValueError, KeyError, OSError, TypeError):
                    pass  # Incomplete or unsupported judgments still require reconciliation.
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            errors.append(str(exc))
        # Parse even partial events on timeout/error before capping retained logs.
        usage = collect_usage(events_path)
        log_cap = limits.get("retained_log_bytes", 2000000)
        truncated_logs = [p.name for p in (events_path, error_path) if retain_log_tail(p, log_cap)]
        elapsed = time.time() - started
        con.execute("UPDATE runs SET state=?,elapsed=?,input_tokens=?,output_tokens=?,cached_input_tokens=? WHERE cache_key=?", (state, elapsed, usage["input_tokens"], usage["output_tokens"], usage["cached_input_tokens"], packet["cache_key"]))
        report = {"status": state.upper(), "job_id": job_id, "role": role, "model": packet["model"], "elapsed_seconds": round(elapsed, 2), "usage": usage, "errors": errors, "receipt_path": packet["receipt_path"], "recorded_at": datetime.now(timezone.utc).isoformat(), "production_complete": False, "truncated_logs": truncated_logs, "usage_coverage": "completed_turn_events_only", "token_cap_enforced": False}
        report['blockers'] = blockers
        write_json(output / "execution.json", report)
        return report

def usage_report(root=ROOT):
    path = root / ".runtime/agent-runs.sqlite3"
    if not path.exists():
        return {"runs": 0, "input_tokens": None, "output_tokens": None, "note": "Sin ejecuciones de agentes registradas"}
    with closing(sqlite3.connect(path)) as con:
        con.row_factory = sqlite3.Row
        return {"by_role": [dict(row) for row in con.execute("SELECT role, model, COUNT(*) runs, SUM(elapsed) elapsed_seconds, SUM(input_tokens) input_tokens, SUM(output_tokens) output_tokens, SUM(cached_input_tokens) cached_input_tokens FROM runs GROUP BY role,model")], "note": "Datos ausentes son null; esta cuenta no incluye el trabajo de desarrollo en Codex"}
