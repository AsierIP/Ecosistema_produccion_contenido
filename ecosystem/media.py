"""Local media inspection and non-executing render plans.

Tool discovery does not load models or establish that a GPU encoder works.
All execution uses argument arrays, without a shell. A successful decode is
technical evidence only; editorial, visual, audio and publication QA is separate.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


def discover() -> dict[str, Any]:
    """Find local tools using explicit environment, PATH, then known installs.

    ECOSYSTEM_RELIGION_ROOT may relocate the existing tool installation. Missing
    explicit overrides remain missing rather than silently selecting a fallback.
    Returned paths belong in ignored machine configuration, not channel files.
    """
    root = Path(os.environ.get("ECOSYSTEM_RELIGION_ROOT", Path.home() / "Documents" / "Religion"))
    specs = {
        "ffmpeg": ("ECOSYSTEM_FFMPEG", "ffmpeg", [root / ".tooling/ltx-venv/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe"]),
        "ffprobe": ("ECOSYSTEM_FFPROBE", "ffprobe", [root / ".tooling/ffprobe-6.1-win-64/ffprobe.exe"]),
        "video2x": ("ECOSYSTEM_VIDEO2X", "video2x", [root / "tools/video2x-6.4.0/video2x.exe"]),
        "gpu_python": ("ECOSYSTEM_GPU_PYTHON", None, [root / ".tooling/ltx-venv/Scripts/python.exe"]),
        "asr_python": ("ECOSYSTEM_ASR_PYTHON", None, [root / ".tooling/ep001-asr-venv/Scripts/python.exe"]),
        "comfy_python": ("ECOSYSTEM_COMFY_PYTHON", None, [root / ".tooling/ComfyUI/venv/Scripts/python.exe"]),
        "qwen_tts_python": ("ECOSYSTEM_QWEN_TTS_PYTHON", None, [root / ".tooling/qwen-tts-venv/Scripts/python.exe"]),
    }
    result: dict[str, Any] = {"hardware_qualified": False, "sources": {}, "errors": []}
    for key, (env_name, command, fallbacks) in specs.items():
        override = os.environ.get(env_name)
        if override:
            candidate = Path(override).expanduser()
            result[key] = str(candidate.resolve()) if candidate.is_file() else None
            result["sources"][key] = "environment"
            if result[key] is None:
                result["errors"].append(f"{env_name}: configured executable is missing")
            continue
        located = shutil.which(command) if command else None
        if located:
            result[key] = str(Path(located).resolve())
            result["sources"][key] = "PATH"
            continue
        candidate = next((p for p in fallbacks if p.is_file()), None)
        result[key] = str(candidate.resolve()) if candidate else None
        result["sources"][key] = "existing-installation" if candidate else "missing"
    return result


def _tool(value: str | os.PathLike[str], default: str) -> str:
    value = os.fspath(value)
    if not value or "\x00" in value:
        raise ValueError("Executable must be a nonempty path or command")
    if value == default and not shutil.which(value):
        found = discover().get(default)
        if found:
            return found
    return value


def _input(path: str | os.PathLike[str]) -> Path:
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("Media input must be a regular file")
    if resolved.stat().st_size == 0:
        raise ValueError("Media input is empty")
    return resolved


def _failure(path: Any, error: str, **details: Any) -> dict[str, Any]:
    return {"ok": False, "status": "failed", "path": os.fspath(path), "errors": [error], **details}


def _execute(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          check=False, shell=False)


def probe(path: str | os.PathLike[str], ffprobe: str = "ffprobe") -> dict[str, Any]:
    """Inspect an actual video. Missing, empty and invalid input returns failure."""
    try:
        source = _input(path)
        tool = _tool(ffprobe, "ffprobe")
        completed = _execute([tool, "-v", "error", "-show_error", "-show_format", "-show_streams",
                              "-of", "json", str(source)], 120)
        if completed.returncode:
            return _failure(source, completed.stderr.strip()[:8000] or "ffprobe failed",
                            returncode=completed.returncode, tool=tool)
        data = json.loads(completed.stdout)
        videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")]
        if not videos or any(s.get("width", 0) <= 0 or s.get("height", 0) <= 0 for s in videos):
            return _failure(source, "No valid video stream", tool=tool, data=data)
        duration = float(data.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or duration <= 0:
            return _failure(source, "Video duration is missing or invalid", tool=tool, data=data)
        return {"ok": True, "status": "passed", "path": str(source), "tool": tool,
                "returncode": 0, "errors": [], "size_bytes": source.stat().st_size,
                "duration_seconds": duration, "format": data.get("format", {}),
                "streams": data.get("streams", []), "data": data}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return _failure(path, str(exc))


def decode(path: str | os.PathLike[str], ffmpeg: str = "ffmpeg") -> dict[str, Any]:
    """Decode all video/audio packets to a null sink with strict error handling.

    This produces no media files. It cannot prove that a file contains all frames
    expected by a production manifest; callers must compare duration and frame
    counts with their source plan independently.
    """
    try:
        source = _input(path)
        tool = _tool(ffmpeg, "ffmpeg")
        completed = _execute([tool, "-hide_banner", "-nostdin", "-v", "error", "-xerror",
                              "-err_detect", "explode", "-i", str(source),
                              "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"], 1800)
        if completed.returncode or completed.stderr.strip():
            return _failure(source, completed.stderr.strip()[:8000] or "ffmpeg decode failed",
                            returncode=completed.returncode, tool=tool)
        return {"ok": True, "status": "passed", "path": str(source), "tool": tool,
                "returncode": 0, "errors": [], "all_packets_decoded": True,
                "editorial_qa_passed": False}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return _failure(path, str(exc))


def _output(path: str | os.PathLike[str], inputs: list[Path]) -> Path:
    result = Path(path).expanduser().resolve()
    if result in inputs or result.exists():
        raise ValueError("Output must be a new file and cannot replace an input")
    if not result.parent.is_dir():
        raise ValueError("Output parent directory must already exist")
    if result.suffix.lower() != ".mp4":
        raise ValueError("Render output must use .mp4")
    return result


def _filter_path(path: Path) -> str:
    # Escape the filter option first, then the enclosing filter graph. These
    # are two FFmpeg parser layers; there is no shell layer in our argv.
    value = "".join("\\" + char if char in "\\':" else char for char in path.as_posix())
    return "".join("\\" + char if char in "\\'[],;" else char for char in value)


def build_render_command(
    video: str | os.PathLike[str], output: str | os.PathLike[str], *,
    audio: str | os.PathLike[str] | None = None,
    subtitles: str | os.PathLike[str] | None = None,
    width: int = 1080, height: int = 1920,
    encoder: str = "libx264", quality: int = 18, ffmpeg: str = "ffmpeg",
) -> list[str]:
    """Plan a render; never execute it or claim NVENC qualification.

    Preserves native cadence and durations. No looping, retiming, interpolation,
    audio padding or automatic trimming is added. Serial GPU scheduling and
    independent final QA are the caller's responsibility.
    """
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 16 or n > 7680 or n % 2
           for n in (width, height)):
        raise ValueError("Render dimensions must be even integers from 16 through 7680")
    if isinstance(quality, bool) or not isinstance(quality, int) or not 0 <= quality <= 51:
        raise ValueError("Quality must be an integer from 0 through 51")
    if encoder not in {"libx264", "h264_nvenc"}:
        raise ValueError("Delivery encoder must be libx264 or h264_nvenc")
    source = _input(video)
    soundtrack = _input(audio) if audio is not None else None
    captions = _input(subtitles) if subtitles is not None else None
    if captions and captions.suffix.lower() != ".ass":
        raise ValueError("Captions must use the channel's approved ASS profile")
    target = _output(output, [p for p in (source, soundtrack, captions) if p])
    args = [_tool(ffmpeg, "ffmpeg"), "-hide_banner", "-nostdin", "-n", "-i", str(source)]
    if soundtrack:
        args += ["-i", str(soundtrack)]
    filters = [f"scale={width}:{height}:force_original_aspect_ratio=decrease",
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", "setsar=1"]
    if captions:
        filters.append("ass=filename=" + _filter_path(captions))
    args += ["-map", "0:v:0", "-map", "1:a:0" if soundtrack else "0:a:0?",
             "-vf", ",".join(filters), "-c:v", encoder]
    args += ["-preset", "slow", "-crf", str(quality)] if encoder == "libx264" else [
        "-preset", "p6", "-rc", "vbr", "-cq", str(quality), "-b:v", "0"]
    args += ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(target)]
    return args


def build_rife_command(*args: Any, **kwargs: Any) -> list[str]:
    """Fail closed until a channel-specific, qualified interpolation adapter exists.

    The installed Video2X 6.4.0 integration requires an endpoint/flush protocol
    and verified GPU receipt. A bare command loses that evidence and may lose
    terminal frames. RIFE also changes the native-timeline contract.
    """
    raise ValueError("RIFE requires a separately qualified channel profile, endpoint/flush protocol, "
                     "serial GPU lease and frame-provenance adapter; no generic command is qualified")
