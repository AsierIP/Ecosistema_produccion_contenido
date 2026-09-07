"""Upro local control panel and coordinator. Runs without an open Codex chat."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit
import webbrowser

from .config import ROOT, load_channels, read_json, write_json, preparation_readiness
from .planner import plan_daily
from .store import Store
from .upro_queue import Queue, GPU_ADAPTERS, execute_step, canary_authorized
from .worker import usage_report

STATIC = Path(__file__).resolve().parent / "static"
STAGE_LABELS = {"creative": "Preparación del guion", "metadata": "Título y descripción",
                "quality": "Revisión independiente", "media_check": "Inspección del vídeo",
                "cutout": "Montaje del cómic", "ambient": "Animación de escenas",
                "voice": "Preparación de la voz", "voice_generate": "Generación de la narración",
                "captions": "Subtítulos sincronizados",
                "visual": "Creación de imágenes"}


def now():
    return datetime.now(timezone.utc).isoformat()


class InstanceLock:
    """OS lock, released by Windows even after a crash; shared across ports."""
    def __init__(self, root):
        self.path = Path(root) / ".runtime/upro/instance.lock"
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError("Upro ya está abierto para este proyecto") from exc

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


class Controller:
    def __init__(self, root, *, executor=execute_step):
        self.root = Path(root).resolve()
        self.settings = read_json(self.root / "config/upro.json")
        self.runtime = self.root / ".runtime/upro"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.control_path = self.runtime / "controls.json"
        self.controls = read_json(self.control_path) if self.control_path.exists() else {"paused": False, "lines": {}}
        self.guard = threading.RLock()
        self.tick_guard = threading.Lock()
        self.stop = threading.Event()
        self.queue = Queue(self.root)
        self.executor = executor
        self.max_workers = max(1, min(4, int(self.settings.get("max_workers", 2))))
        self.pool = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="upro")
        self.active = {}
        self.plan = {"channels": []}
        self.activity = self.load_activity()
        self.last_error = None
        self.stopping = False
        self.token = secrets.token_urlsafe(32)
        self.thread = None

    def load_activity(self):
        path = self.runtime / 'activity.jsonl'
        if not path.exists():
            return []
        from collections import deque
        result = []
        with path.open(encoding='utf-8', errors='replace') as stream:
            for line in deque(stream, maxlen=60):
                try:
                    item = json.loads(line)
                    if isinstance(item, dict) and isinstance(item.get('message'), str):
                        result.append(item)
                except ValueError:
                    continue
        return result

    def event(self, message, level="info", line_id=None):
        item = {"message": message, "level": level, "line_id": line_id, "created_at": now()}
        with self.guard:
            self.activity = (self.activity + [item])[-60:]
            with (self.runtime / "activity.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(item, ensure_ascii=False) + "\n")

    def save_controls(self):
        temporary = self.control_path.with_suffix(".tmp")
        write_json(temporary, self.controls)
        temporary.replace(self.control_path)

    def set_line(self, line_id, enabled):
        with self.guard:
            ids = {c["id"] for c in load_channels(self.root)}
            extras = {x["id"]: x for x in self.settings.get("extra_lines", [])}
            if line_id not in ids | extras.keys():
                raise KeyError("Línea desconocida")
            if enabled and extras.get(line_id, {}).get("locked"):
                raise ValueError(extras[line_id]["reason"])
            self.controls["lines"][line_id] = enabled
            self.save_controls()
            self.event("Línea activada; se comprobarán sus requisitos." if enabled else "Línea pausada; la etapa en curso terminará antes de detenerse.", line_id=line_id)

    def set_paused(self, paused):
        with self.guard:
            self.controls["paused"] = paused
            self.save_controls()
            self.event("Producción pausada; terminan las etapas en curso." if paused else "Producción reanudada.")

    def start(self):
        self.queue.recover()
        self.event("Upro abierto. Comprobando las líneas activadas.")
        self.tick()
        self.thread = threading.Thread(target=self.loop, name="upro-scheduler", daemon=True)
        self.thread.start()

    def loop(self):
        interval = max(5, int(self.settings.get("poll_seconds", 30)))
        while not self.stop.wait(interval):
            self.tick()

    def enabled(self, line_id):
        return self.controls["lines"].get(line_id, self.settings.get("start_enabled_lines_on_open", True))

    def tick(self):
        if not self.tick_guard.acquire(blocking=False):
            return
        try:
            plan = plan_daily(self.root)
            with self.guard:
                self.plan = plan
                self.last_error = None
                self.active = {k: v for k, v in self.active.items() if not v["future"].done()}
                if self.controls["paused"] or self.stopping:
                    return
                from .workflow import seed_ready_jobs, advance_production
                eligible_plan = {**plan, 'channels': [c for c in plan['channels'] if self.enabled(c['channel_id'])]}
                seed_ready_jobs(self.root, eligible_plan, self.queue)
                advance_production(self.root, self.queue)
                from .montage import advance_montage
                advance_montage(self.root, self.queue)
                self.queue.advance_completed_renders()
                steps = self.queue.list()
                active_channels = {v["channel"] for v in self.active.values()}
                gpu_active = any(v["adapter"] in GPU_ADAPTERS for v in self.active.values())
                with Store(self.root / ".runtime/production.sqlite3") as store:
                    gpu_busy = store.connection.execute("SELECT 1 FROM leases WHERE resource='gpu' AND expires_at>?", (time.time(),)).fetchone() is not None
                    unresolved = {i["job_id"] for i in store.list_intents() if i["state"] in {"sending", "uncertain"}}
                for channel in plan["channels"]:
                    cid = channel["channel_id"]
                    if len(self.active) >= self.max_workers:
                        break
                    if not self.enabled(cid) or cid in active_channels or channel["job_id"] in unresolved:
                        continue
                    # A blocked/uncertain step requires inspection; no automatic retry loop.
                    relevant = [s for s in steps if s["job_id"] == channel["job_id"]]
                    if any(s["state"] in {"blocked", "uncertain"} for s in relevant):
                        continue
                    for step in relevant:
                        if step["state"] != "queued" or (step["mode"] == "production" and not channel["ready"]):
                            continue
                        if step["mode"] == "canary":
                            profile = next(c for c in load_channels(self.root) if c["id"] == cid)
                            local_path = self.root / "local.json"
                            local = read_json(local_path) if local_path.exists() else {}
                            if not canary_authorized(self.root, step["payload"]) or preparation_readiness(profile, local, step["adapter"]):
                                continue
                        if step["adapter"] in GPU_ADAPTERS and (gpu_busy or gpu_active):
                            continue
                        if not self.queue.claim(step["id"]):
                            continue
                        future = self.pool.submit(self.run, step)
                        self.active[step["id"]] = {"future": future, "channel": cid, "adapter": step["adapter"]}
                        active_channels.add(cid)
                        gpu_active |= step["adapter"] in GPU_ADAPTERS
                        break
        except Exception as exc:
            with self.guard:
                message = str(exc)
                if self.last_error != message:
                    self.event("No se pudo actualizar el motor: " + message, "error")
                self.last_error = message
        finally:
            self.tick_guard.release()

    def run(self, step):
        self.event("Etapa iniciada: " + STAGE_LABELS.get(step["adapter"], step["adapter"]), line_id=step["channel_id"])
        try:
            result, state = self.executor(self.root, step)
        except Exception as exc:
            # A render or subprocess may have written partial outputs before failing.
            result, state = {"error": str(exc)}, "uncertain"
        self.queue.finish(step["id"], result, state)
        label = "Etapa terminada; pendiente de las siguientes comprobaciones." if state == "accepted" else "Etapa detenida; revisar sus evidencias antes de continuar."
        self.event(label, "info" if state == "accepted" else "warning", step["channel_id"])

    def status(self):
        with self.guard:
            steps = self.queue.list()
            lines = []
            with Store(self.root / ".runtime/production.sqlite3") as store:
                gpu_busy = store.connection.execute("SELECT 1 FROM leases WHERE resource='gpu' AND expires_at>?", (time.time(),)).fetchone() is not None
                intents = store.list_intents()
                for c in self.plan["channels"]:
                    cid = c["channel_id"]
                    tasks = [s for s in steps if s["job_id"] == c["job_id"]]
                    activation_blockers = list(c["blockers"])
                    blockers = []
                    handoff_dir = self.root / '.runtime/jobs' / c['job_id'] / 'handoffs'
                    for error_file in handoff_dir.glob('error-*.json'):
                        handoff_error = read_json(error_file)
                        if handoff_error.get('status') == 'blocked':
                            blockers.append(handoff_error.get('reason', 'No se pudo preparar la siguiente etapa'))
                    if any(s["state"] == "uncertain" for s in tasks):
                        blockers.append("Una etapa quedó interrumpida o incierta; requiere reconciliación.")
                    if any(s["state"] == "blocked" for s in tasks):
                        blockers.append("Una etapa no superó la validación; revisar antes de repetir.")
                        for step in tasks:
                            if step['state'] == 'blocked':
                                detail = step.get('result') or {}
                                causes = detail.get('blockers') or detail.get('errors') or [detail.get('reason')]
                                if isinstance(causes, list):
                                    blockers.extend(x[:500] for x in causes[:5] if isinstance(x, str) and x)
                    if any(i["job_id"] == c["job_id"] and i["state"] in {"sending", "uncertain"} for i in intents):
                        blockers.append("Publicación incierta pendiente de reconciliar.")
                    running = next((s for s in tasks if s["state"] == "running"), None)
                    queued = next((s for s in tasks if s['state'] == 'queued'), None)
                    inspected = any(s['adapter'] == 'media_check' and s['state'] == 'accepted' for s in tasks)
                    if queued:
                        if queued['mode'] == 'production':
                            blockers.extend(activation_blockers)
                        elif queued['mode'] == 'canary':
                            profile = next(p for p in load_channels(self.root) if p['id'] == cid)
                            local_path = self.root / 'local.json'
                            local = read_json(local_path) if local_path.exists() else {}
                            blockers.extend(preparation_readiness(profile, local, queued['adapter']))
                            if not canary_authorized(self.root, queued['payload']):
                                blockers.append('Falta autorización vigente para esta prueba y etapa.')
                    elif not running and not inspected and c['state'] != 'complete':
                        blockers.append('Falta conectar y validar la siguiente etapa de producción automática.')
                    enabled = self.enabled(cid)
                    state = ("reviewing" if running["adapter"] in {"media_check", "quality"} else "running") if running else "paused" if (not enabled or self.controls["paused"]) else "blocked" if blockers else "queued" if queued else "review_pending" if inspected else "complete" if c['state'] == 'complete' else "ready"
                    if state == 'queued' and queued['payload'].get('not_before', 0) > time.time():
                        state = 'scheduled'
                    if c['state'] == 'complete' and not running and not blockers:
                        state = 'complete'
                    video = self.last_video(cid, steps, intents)
                    lines.append({"id": cid, "name": c["name"], "enabled": enabled,
                                  "state": state, "stage": running["adapter"] if running else state,
                                  "blockers": blockers, "activation_blockers": activation_blockers,
                                  "autonomous_ready": c['ready'], "last_video": video, "progress": None,
                                  "job_id": c["job_id"], "production_date": c["production_date"]})
            for extra in self.settings.get("extra_lines", []):
                lines.append({**extra, "enabled": self.controls["lines"].get(extra["id"], extra["enabled"]),
                              "state": "paused", "stage": "paused", "blockers": [extra["reason"]], "progress": None, "last_video": None})
            raw_usage = usage_report(self.root)
            rows = raw_usage.get("by_role", [])
            usage = {key: sum(r[key] for r in rows if r.get(key) is not None) if any(r.get(key) is not None for r in rows) else None
                     for key in ("input_tokens", "output_tokens", "cached_input_tokens", "runs")}
            usage["note"] = "Entrada incluye caché; datos ausentes no equivalen a cero. No incluye el desarrollo de Upro."
            return {"name": "Upro", "running": not self.stopping, "paused": self.controls["paused"],
                    "lines": lines, "activity": self.activity[-30:][::-1], "updated_at": now(),
                    "resources": {"gpu_busy": gpu_busy, "active_workers": sum(not v["future"].done() for v in self.active.values()), "max_workers": self.max_workers},
                    "csrf_token": self.token, "usage": usage,
                    "execution_notice": self.last_error or "El motor local está disponible. La producción y publicación completas requieren terminar la conexión y validación de las etapas indicadas en cada línea. El panel no consume tokens al actualizarse."}

    def last_video(self, channel, steps, intents):
        candidates = [s for s in steps if s["channel_id"] == channel and s["adapter"] == "media_check" and s["state"] == "accepted"]
        if candidates:
            step = candidates[-1]
            path = Path(step["result"]["path"])
            if path.is_file():
                return {"title": path.stem, "url": "/api/media/" + step["id"], "local_available": True,
                        "status": "Decodificado; revisión editorial y audiovisual pendiente"}
        public = [i for i in intents if i["state"] == "verified" and i["action"] == "publish"]
        with Store(self.root / ".runtime/production.sqlite3") as store:
            public = [i for i in public if store.get_job(i["job_id"])["channel_id"] == channel]
        for intent in reversed(public):
            url = intent["evidence"].get("public_url")
            if url and urlsplit(url).scheme == "https":
                return {"title": "Última publicación verificada", "url": url, "local_available": False}
        return None

    def media(self, step_id):
        for step in self.queue.list():
            if step["id"] == step_id and step["adapter"] == "media_check" and step["state"] == "accepted":
                path = Path(step["result"]["path"])
                if path.is_file() and path.suffix.lower() == ".mp4":
                    # Serving a replacement under an old accepted record is forbidden.
                    from .cache import file_hash
                    if file_hash(path) == step["result"]["master_sha256"]:
                        return path
        raise KeyError("Vídeo no disponible")

    def close(self):
        with self.guard:
            self.stopping = True
            self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.pool.shutdown(wait=True, cancel_futures=False)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, address, controller):
        self.controller = controller
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "Upro"
    def log_message(self, *args):
        pass

    def allowed_origin(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (not origin or origin in {"http://" + h for h in hosts})

    def respond(self, status, data, content_type="application/json; charset=utf-8", extra=None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8") if isinstance(data, (dict, list)) else data
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        if not self.allowed_origin():
            self.respond(403, {"error": "Origen no permitido"})
            return
        path = urlsplit(self.path).path
        controller = self.server.controller
        try:
            if path == "/api/health":
                self.respond(200, {"app": "upro", "root": str(controller.root), "version": "0.2.0"})
            elif path == "/api/status":
                self.respond(200, controller.status())
            elif path.startswith("/api/media/"):
                self.send_media(controller.media(path.removeprefix("/api/media/")))
            elif path in {"/", "/static/app.css", "/static/app.js"}:
                file = STATIC / ("index.html" if path == "/" else path.split("/")[-1])
                self.respond(200, file.read_bytes(), mimetypes.guess_type(file)[0] + "; charset=utf-8")
            else:
                self.respond(404, {"error": "No encontrado"})
        except (KeyError, FileNotFoundError):
            self.respond(404, {"error": "No disponible"})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_media(self, path):
        import re
        size = path.stat().st_size
        first, last = 0, size - 1
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if not match or not any(match.groups()):
                self.respond(416, b"", extra={"Content-Range": f"bytes */{size}"})
                return
            a, b = match.groups()
            first, last = (int(a), min(int(b) if b else size - 1, size - 1)) if a else (max(0, size-int(b)), size-1)
            if first > last or first >= size:
                self.respond(416, b"", extra={"Content-Range": f"bytes */{size}"})
                return
        self.send_response(206 if requested else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(last-first+1))
        self.send_header("Cache-Control", "no-store")
        if requested:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        with path.open("rb") as file:
            file.seek(first)
            remaining = last-first+1
            while remaining:
                chunk = file.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_POST(self):
        c = self.server.controller
        if not self.allowed_origin() or not secrets.compare_digest(self.headers.get("X-Upro-Token", ""), c.token):
            self.respond(403, {"error": "Actualizar el panel antes de cambiar controles"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Petición incorrecta")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Petición incorrecta")
            path = urlsplit(self.path).path
            if path.startswith("/api/lines/"):
                if set(data) != {"enabled"} or not isinstance(data["enabled"], bool):
                    raise ValueError("enabled debe ser verdadero o falso")
                c.set_line(path.removeprefix("/api/lines/"), data["enabled"])
            elif path == "/api/control":
                if set(data) != {"paused"} or not isinstance(data["paused"], bool):
                    raise ValueError("paused debe ser verdadero o falso")
                c.set_paused(data["paused"])
            elif path == "/api/tick" and data == {}:
                pass
            elif path == "/api/shutdown" and data == {}:
                self.respond(200, {"status": "stopping", "message": "El motor terminará las etapas en curso antes de cerrarse."})
                c.stopping = True
                c.stop.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                self.respond(404, {"error": "No encontrado"})
                return
            c.tick()
            self.respond(200, c.status())
        except (ValueError, KeyError, TypeError) as exc:
            self.respond(400, {"error": str(exc)})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Upro: producción local multicanal")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--once", action="store_true", help="Un ciclo local, sin abrir el servidor")
    parser.add_argument("--register", type=Path, help="Registrar una etapa local; no ejecuta el plan")
    parser.add_argument("--reconcile", help="Archivar una etapa bloqueada tras revisar el resultado; no reintenta")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve(strict=True)
    load_channels(root)
    if args.reconcile:
        if not args.evidence:
            raise ValueError("Reconciliar requiere --evidence con el resultado de la inspección")
        Queue(root).retire(args.reconcile, read_json(args.evidence))
        print(json.dumps({"status": "RECONCILED", "replayed": False}))
        return 0
    if args.register:
        key = Queue(root).register(read_json(args.register))
        print(json.dumps({"step_id": key, "status": "REGISTERED", "production_complete": False}))
        return 0
    if args.check:
        read_json(root / "config/upro.json")
        if not (STATIC / "index.html").is_file():
            raise FileNotFoundError("Falta el panel Upro")
        print(json.dumps({"app": "upro", "status": "INSTALLATION_OK", "root": str(root)}))
        return 0
    lock = InstanceLock(root)
    lock.acquire()
    controller = None
    server = None
    try:
        controller = Controller(root)
        if args.once:
            controller.queue.recover()
            controller.tick()
            controller.close()
            print(json.dumps(controller.status(), ensure_ascii=False))
            return 0
        if not 1024 <= args.port <= 65535:
            raise ValueError("Puerto fuera del rango permitido")
        # Bind before starting work: an occupied port must not start a second producer.
        server = Server(("127.0.0.1", args.port), controller)
        controller.start()
        write_json(controller.runtime / "instance.json", {"pid": os.getpid(), "port": args.port, "root": str(root), "started_at": now()})
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{args.port}/")
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        if controller:
            controller.close()
        if server:
            server.server_close()
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
