"""Segment-local Video2X 6.4/RIFE adapter with verified endpoint provenance.

The three processing guard frames never enter the result. Delivery contains the
249-frame native/intermediate sequence followed by exactly one native endpoint,
as in the observed Religion adapter. This is technical evidence, not visual QA.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from .cache import file_hash
from .config import ROOT, write_json
from .media import discover, decode, probe
from .store import Store

@contextmanager
def gpu_lease(root, owner):
    with Store(root / ".runtime/production.sqlite3") as store:
        lease = store.claim_lease("gpu", owner, 120)
        if not lease:
            raise RuntimeError("GPU ocupada por otra tarea del ecosistema")
        try:
            yield store, lease
        finally:
            store.release_lease("gpu", owner, lease["token"])

def _run(argv, log_path, *, store=None, lease=None, timeout=1800):
    started = time.monotonic()
    with Path(log_path).open("w", encoding="utf-8") as log:
        previous_mode = None
        if os.name == "nt":
            import ctypes
            previous_mode = ctypes.windll.kernel32.SetErrorMode(0x0003)
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                       shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        finally:
            if previous_mode is not None:
                ctypes.windll.kernel32.SetErrorMode(previous_mode)
        write_json(Path(log_path).with_suffix(".process.json"), {"pid": process.pid, "argv": argv, "started_at": time.time()})
        try:
            while True:
                try:
                    return process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started > timeout:
                        raise RuntimeError("Tiempo máximo del proceso GPU excedido")
                    if store and not store.renew_lease("gpu", lease["owner"], lease["token"], 120):
                        raise RuntimeError("Se perdió la reserva de GPU")
        except BaseException:
            process.kill()
            process.wait()
            raise

def frame_hashes(path, ffmpeg):
    result = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0",
                             "-an", "-pix_fmt", "yuv420p", "-f", "framemd5", "-"],
                            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900, check=True)
    return [line.rsplit(",", 1)[-1].strip() for line in result.stdout.splitlines() if line and not line.startswith("#")]

def conform_segment(source, output, *, root=ROOT, device=0):
    tools = discover()
    if any(not tools.get(name) for name in ("ffmpeg", "ffprobe", "video2x")):
        raise RuntimeError("Se requieren FFmpeg, ffprobe y Video2X instalados")
    source = Path(source).resolve(strict=True)
    output = Path(output).resolve()
    if output.suffix.lower() != ".mp4" or output.exists() or output == source:
        raise ValueError("La salida debe ser un MP4 nuevo")
    if not isinstance(device, int) or isinstance(device, bool) or device < 0:
        raise ValueError("Invalid GPU device")
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.with_suffix(".rife-work")
    work.mkdir(exist_ok=False)
    source_hash = file_hash(source)
    input_probe = probe(source, tools["ffprobe"])
    input_decode = decode(source, tools["ffmpeg"])
    if not input_probe["ok"] or not input_decode["ok"]:
        raise ValueError("La fuente no supera la inspección y decodificación")
    stream = next(s for s in input_probe["streams"] if s["codec_type"] == "video")
    if stream.get("r_frame_rate") != "24/1" or stream.get("avg_frame_rate") != "24/1":
        raise ValueError("RIFE Religion requiere entrada CFR de 24 fps")
    native = frame_hashes(source, tools["ffmpeg"])
    if len(native) != 125:
        raise ValueError("RIFE Religion requiere exactamente 125 fotogramas nativos")
    version = subprocess.run([tools["video2x"], "--version"], capture_output=True, text=True, timeout=20, check=True)
    if "Video2X version 6.4.0" not in version.stdout + version.stderr:
        raise ValueError("Este protocolo solo se ha diseñado para Video2X 6.4.0")
    model_dir = Path(tools["video2x"]).parent / "models/rife/rife-v4.25"
    model_hashes = {name: file_hash(model_dir / name) for name in ("flownet.bin", "flownet.param")}
    guarded, raw = work / "flush.mkv", work / "raw.mkv"
    guard_filter = '[0:v]split=4[b][g1][g2][g3];[b]trim=end_frame=125,setpts=PTS-STARTPTS,format=yuv420p[base];' + ''.join(f'[g{i}]trim=start_frame=124:end_frame=125,setpts=PTS-STARTPTS,format=yuv420p[guard{i}];' for i in (1,2,3)) + '[base][guard1][guard2][guard3]concat=n=4:v=1:a=0,setpts=N/(24*TB)[out]'
    guard_cmd = [tools["ffmpeg"], "-n", "-nostdin", "-v", "error", "-i", str(source), "-filter_complex", guard_filter,
                 "-map", "[out]", "-frames:v", "128", "-r", "24", "-c:v", "ffv1", "-level", "3", "-pix_fmt", "yuv420p", "-an", str(guarded)]
    if _run(guard_cmd, work / "guard.log"):
        raise RuntimeError("No se pudo preparar la entrada de vaciado")
    guarded_hashes = frame_hashes(guarded, tools["ffmpeg"])
    if guarded_hashes != native + [native[-1]] * 3:
        raise RuntimeError("Las guardas no conservan exactamente la fuente")
    owner = "rife-" + str(uuid.uuid4())
    with gpu_lease(root, owner) as (store, lease):
        cmd = [tools["video2x"], "-i", str(guarded), "-o", str(raw), "-p", "rife", "-m", "2", "--rife-model", "rife-v4.25",
               "-d", str(device), "-c", "ffv1", "--pix-fmt", "yuv420p", "--no-copy-streams", "--scene-thresh", "100", "--log-level", "info"]
        code = _run(cmd, work / "video2x.log", store=store, lease=lease)
    # A known encoder shutdown crash may leave a complete lossless artifact.
    # Its exit code is retained and never suffices: every native frame is checked.
    if code not in (0, -1073741819, 3221225477):
        raise RuntimeError(f"Video2X falló ({code}); revisar {work / 'video2x.log'}")
    if not decode(raw, tools["ffmpeg"])["ok"]:
        raise RuntimeError("La salida RIFE no se decodifica completamente")
    raw_hashes = frame_hashes(raw, tools["ffmpeg"])
    if len(raw_hashes) < 250 or raw_hashes[:249:2] != native:
        raise RuntimeError("La salida RIFE perdió o modificó fotogramas nativos")
    conform = '[0:v]trim=end_frame=249,setpts=PTS-STARTPTS,format=yuv420p[m];[1:v]trim=start_frame=124:end_frame=125,setpts=PTS-STARTPTS,format=yuv420p[e];[m][e]concat=n=2:v=1:a=0,setpts=N/(24*TB)[out]'
    cmd = [tools["ffmpeg"], "-n", "-nostdin", "-v", "error", "-i", str(raw), "-i", str(source), "-filter_complex", conform,
           "-map", "[out]", "-frames:v", "250", "-r", "24", "-c:v", "libx264", "-preset", "slow", "-qp", "0", "-pix_fmt", "yuv420p",
           "-video_track_timescale", "24000", "-movflags", "+faststart", "-an", str(output)]
    if _run(cmd, work / "conform.log"):
        raise RuntimeError("No se pudo conformar el segmento")
    final_hashes = frame_hashes(output, tools["ffmpeg"])
    final_probe = probe(output, tools["ffprobe"])
    if len(final_hashes) != 250 or final_hashes[:249:2] != native or final_hashes[-1] != native[-1]:
        raise RuntimeError("El segmento final no conserva los 125 fotogramas y su extremo")
    if not final_probe["ok"] or not decode(output, tools["ffmpeg"])["ok"]:
        raise RuntimeError("El segmento final no supera QA técnica")
    final_stream = next(s for s in final_probe["streams"] if s["codec_type"] == "video")
    if any(final_stream.get(field) != stream.get(field) for field in ("width", "height")) or any(final_stream.get(field) != "24/1" for field in ("r_frame_rate", "avg_frame_rate")):
        raise RuntimeError("Las dimensiones o la cadencia cambiaron durante la conformación")
    if file_hash(source) != source_hash:
        raise RuntimeError("La fuente cambió durante el proceso")
    receipt = {"status": "TECHNICAL_PASS", "source_path": str(source), "source_sha256": source_hash,
               "output_path": str(output), "output_sha256": file_hash(output), "input_frames": 125, "output_frames": 250,
               "output_fps": 24, "interpolation": "rife_2x", "speed_factor": 1.0, "interpolated_across_cuts": False,
               "native_frames_preserved": 125, "generated_intermediate_frames": 124, "endpoint_hold_frames": 1,
               "processing_guard_frames_excluded": 3, "video2x_exit_code": code, "gpu_device": device,
               "gpu_execution": True, "tool_sha256": file_hash(Path(tools["video2x"])),
               "model_sha256": model_hashes,
               "provenance": [{"input_frame": i, "output_frame": 2*i, "pixel_md5": value} for i,value in enumerate(native)],
               "editorial_qa_passed": False, "production_qualified": False}
    write_json(output.with_suffix(".rife.json"), receipt, exclusive=True)
    return {k:v for k,v in receipt.items() if k != "provenance"}
