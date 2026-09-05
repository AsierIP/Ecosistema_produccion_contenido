"""A silent camera-motion sample from approved artwork, never a production reel.

Call render_style_preview(..., encoder="h264_nvenc", execute=True) to use the
shared GPU lease; choose encoder="libx264" explicitly for CPU rendering. The
default only returns a command plan. No character animation or publication is
performed. Approval is bound to the caller's expected artwork SHA256.
"""
from __future__ import annotations

from contextlib import nullcontext
from fractions import Fraction
import math
from pathlib import Path
import re
import uuid

from .cache import file_hash
from .config import ROOT, write_json
from .media import decode, discover, probe
from .rife import gpu_lease, _run


def render_style_preview(source, output, *, approved_source_sha256: str,
                         encoder: str, root=ROOT, duration_seconds=6.0,
                         execute=False) -> dict:
    """Plan or render a 1080x1920/24fps sample with a centered 1.035x zoom.

    Outputs and their sidecars must be new. A failed render remains available
    for diagnosis and cannot be silently overwritten or retried on the CPU.
    Duration is bounded to 1--30 seconds and must represent whole frames.
    """
    if (isinstance(duration_seconds, bool)
            or not isinstance(duration_seconds, (int, float))
            or not math.isfinite(duration_seconds)
            or not 1 <= duration_seconds <= 30):
        raise ValueError("Duration must be finite and between 1 and 30 seconds")
    frames = round(duration_seconds * 24)
    if abs(frames / 24 - duration_seconds) > 1e-9:
        raise ValueError("Duration must represent whole frames at 24 fps")
    if encoder not in {"h264_nvenc", "libx264"}:
        raise ValueError("Choose h264_nvenc or libx264 explicitly")
    if not isinstance(execute, bool):
        raise ValueError("execute must be a boolean")
    source = Path(source).expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".png":
        raise ValueError("Approved artwork must be a PNG file")
    with source.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Artwork has no valid PNG signature")
    if not isinstance(approved_source_sha256, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", approved_source_sha256):
        raise ValueError("The approved artwork SHA256 is required")
    source_hash = file_hash(source)
    if source_hash != approved_source_sha256.lower():
        raise ValueError("Artwork differs from the approved SHA256")
    output = Path(output).expanduser().resolve()
    receipt_path = output.with_suffix(".preview.json")
    log_path = output.with_suffix(".preview.log")
    artifacts = [output, receipt_path, log_path, log_path.with_suffix(".process.json")]
    if output.suffix.lower() != ".mp4" or not output.parent.is_dir():
        raise ValueError("Output must be an MP4 in an existing directory")
    if any(path.exists() or path == source for path in artifacts):
        raise ValueError("Output and preview sidecars must be new files")
    tools = discover()
    if not tools.get("ffmpeg") or (execute and not tools.get("ffprobe")):
        raise RuntimeError("Installed FFmpeg and, for execution, ffprobe are required")
    # Upscaling before zoompan limits integer-pixel stepping in this small move.
    filters = ("scale=2160:3840:force_original_aspect_ratio=increase,"
               "crop=2160:3840,setsar=1,"
               f"zoompan=z='1+0.035*on/{frames - 1}':"
               f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={frames}:"
               "s=1080x1920:fps=24")
    argv = [tools["ffmpeg"], "-hide_banner", "-nostdin", "-n", "-i", str(source),
            "-map", "0:v:0", "-an", "-vf", filters, "-frames:v", str(frames),
            "-t", str(duration_seconds), "-c:v", encoder]
    argv += (["-preset", "p6", "-rc", "vbr", "-cq", "18", "-b:v", "0"]
             if encoder == "h264_nvenc" else ["-preset", "medium", "-crf", "18"])
    argv += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    record = {"schema_version": 1, "status": "planned", "kind": "style_preview",
              "source_path": str(source), "source_sha256": source_hash,
              "output_path": str(output), "encoder": encoder,
              "duration_seconds": float(duration_seconds), "expected_frames": frames,
              "width": 1080, "height": 1920, "fps": 24, "zoom_final": 1.035,
              "camera_only": True, "not_character_animation": True,
              "production_qa_passed": False, "publication_performed": False,
              "argv": argv, "receipt_path": str(receipt_path)}
    if not execute:
        return record
    reservation = (gpu_lease(Path(root), "style-preview-" + uuid.uuid4().hex)
                   if encoder == "h264_nvenc" else nullcontext((None, None)))
    with reservation as (store, lease):
        code = _run(argv, log_path, store=store, lease=lease, timeout=300)
    if code:
        raise RuntimeError(f"Preview render failed ({code}); inspect {log_path}")
    metadata = probe(output, tools["ffprobe"])
    decoded = decode(output, tools["ffmpeg"])
    videos = [item for item in metadata.get("streams", []) if item.get("codec_type") == "video"]
    audio = [item for item in metadata.get("streams", []) if item.get("codec_type") == "audio"]
    try:
        valid = (metadata.get("ok") and decoded.get("ok") and len(videos) == 1 and not audio
                 and videos[0].get("codec_name") == "h264"
                 and videos[0].get("width") == 1080 and videos[0].get("height") == 1920
                 and Fraction(videos[0].get("avg_frame_rate", "0")) == 24
                 and int(videos[0].get("nb_frames", 0)) == frames
                 and abs(metadata["duration_seconds"] - duration_seconds) <= 1 / 24
                 and file_hash(source) == source_hash)
    except (TypeError, ValueError, ZeroDivisionError):
        valid = False
    if not valid:
        raise RuntimeError("Preview failed dimensions, cadence, duration, decode or source checks")
    record.update(status="technical_sample_verified", sha256=file_hash(output),
                  codec=videos[0]["codec_name"], measured_duration_seconds=metadata["duration_seconds"],
                  measured_frames=int(videos[0]["nb_frames"]), all_packets_decoded=True,
                  gpu_execution=encoder == "h264_nvenc", size_bytes=output.stat().st_size)
    write_json(receipt_path, record, exclusive=True)
    return record
