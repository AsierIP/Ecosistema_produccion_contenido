"""Local, frame-bounded 2D cutout compositor.

Illustrations stay unmodified. Their placement and motion are described by a
local manifest; code-native ASS drawings and literal captions are composited
at delivery resolution. This adapter provides technical evidence only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess
import time
import uuid
import wave

from .cache import file_hash
from .media import _filter_path, decode, discover, probe
from .rife import _run, frame_hashes, gpu_lease


def render(manifest_path: str | Path, *, root: str | Path) -> dict:
    manifest_path = Path(manifest_path).resolve(strict=True)
    cfg = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    root = Path(root).resolve(strict=True)
    tools = discover()
    if not tools.get("ffmpeg") or not tools.get("ffprobe"):
        raise ValueError("Local FFmpeg and ffprobe are required")
    fps, width, height = cfg.get("fps", 24), cfg.get("width", 1080), cfg.get("height", 1920)
    if fps != 24 or (width, height) != (1080, 1920):
        raise ValueError("This layout supports 1080x1920 at 24 fps")
    work = Path(cfg["work_dir"]).resolve()
    evidence = Path(cfg["evidence_dir"]).resolve()
    output = Path(cfg["output"]).resolve()
    intro, narration, ass = (Path(cfg[name]).resolve(strict=True) for name in ("intro", "narration", "ass"))
    if output.exists() or output.suffix.lower() != ".mp4":
        raise ValueError("The output must be a new MP4")
    # A retry must preserve its previous logs, filter graph and QA receipt.
    # In particular, FFmpeg's -n does not protect files written by Python.
    if work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise ValueError("The work directory must be new or empty; preserve previous attempts")
    receipt_path = evidence / "technical-qa.json"
    if receipt_path.exists():
        raise ValueError("The evidence directory already contains a technical QA receipt")
    if output in {work / name for name in ("body.mp4", "intro-video.mp4")}:
        raise ValueError("The output must differ from intermediate video paths")
    for directory in (work, evidence, output.parent):
        directory.mkdir(parents=True, exist_ok=True)
    with wave.open(str(narration)) as wav:
        wav_params, wav_data = wav.getparams(), wav.readframes(wav.getnframes())
    if (wav_params.nchannels, wav_params.sampwidth, wav_params.framerate) != (1, 2, 48000):
        raise ValueError("Narration must be unretimed mono PCM16 at 48000 Hz")
    duration = wav_params.nframes / wav_params.framerate
    narrated_body_frames = math.ceil(duration * fps)
    end_card_seconds = float(cfg.get('end_card_seconds', 0))
    if not 0 <= end_card_seconds <= 5:
        raise ValueError('End card must be between zero and five seconds')
    end_card_frames = round(end_card_seconds * fps)
    body_frames = narrated_body_frames + end_card_frames
    if sum(scene["frames"] for scene in cfg["scenes"]) != body_frames:
        raise ValueError("Scene frames must equal the narration frames plus the explicit end card")
    intro_probe = probe(intro, tools["ffprobe"])
    if not intro_probe["ok"] or not decode(intro, tools["ffmpeg"])["ok"]:
        raise ValueError("Intro is not fully decodable")
    video = next(s for s in intro_probe["streams"] if s["codec_type"] == "video")
    if (video.get("width"), video.get("height"), video.get("r_frame_rate"), video.get("nb_frames")) != (1080, 1920, "24/1", "36"):
        raise ValueError("Intro must contain exactly 36 frames at 24 fps")
    source_hashes = {str(p): file_hash(p) for p in (intro, narration, ass)}
    argv = [tools["ffmpeg"], "-hide_banner", "-nostdin", "-n", "-filter_complex_threads", "2"]
    graph, scene_labels, input_index = [], [], 0
    for index, scene in enumerate(cfg["scenes"]):
        frames = scene["frames"]
        if not isinstance(frames, int) or frames < 1:
            raise ValueError("Every scene must have a positive integer frame count")
        start_frame = 0
        if scene.get('video'):
            p = Path(scene['video']).resolve(strict=True)
            source_hashes[str(p)] = file_hash(p)
            info = probe(p, tools['ffprobe'])
            streams = [s for s in info.get('streams', []) if s['codec_type']=='video']
            start_frame = scene.get('in_frame', 0)
            if not isinstance(start_frame, int) or start_frame < 0:
                raise ValueError('Video in_frame must be a nonnegative integer')
            if not info['ok'] or not streams or streams[0].get('avg_frame_rate') != '24/1' or int(streams[0].get('nb_frames', 0)) < start_frame + frames:
                raise ValueError('Scene requires enough existing video frames at 24 fps; no looping')
            argv += ['-i', str(p)]
            bg_filter = scene.get('background_filter', f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}')
        elif scene.get("image"):
            p = Path(scene["image"]).resolve(strict=True)
            source_hashes[str(p)] = file_hash(p)
            argv += ["-loop", "1", "-framerate", str(fps), "-i", str(p)]
            bg_filter = scene.get("background_filter", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
        else:
            argv += ["-f", "lavfi", "-i", f"color=c={scene.get('color', '0xFFF1D2')}:s={width}x{height}:r={fps}"]
            bg_filter = "null"
        current = f"scene{index}base"
        graph.append(f"[{input_index}:v]trim=start_frame={start_frame}:end_frame={start_frame+frames},setpts=PTS-STARTPTS,{bg_filter},setsar=1,format=yuv420p[{current}]")
        input_index += 1
        for layer_index, layer in enumerate(scene.get("layers", [])):
            p = Path(layer["image"]).resolve(strict=True)
            source_hashes[str(p)] = file_hash(p)
            argv += ["-loop", "1", "-framerate", str(fps), "-i", str(p)]
            tag = f"scene{index}layer{layer_index}"
            graph.append(f"[{input_index}:v]scale={int(layer['width'])}:-1,format=rgba,trim=end_frame={frames},setpts=PTS-STARTPTS[{tag}]")
            out = f"scene{index}composite{layer_index}"
            graph.append(f"[{current}][{tag}]overlay=x='{layer['x']}':y='{layer['y']}':eval=frame:shortest=1:eof_action=endall[{out}]")
            current = out
            input_index += 1
        scene_labels.append(f"[{current}]")
    graph.append("".join(scene_labels) + f"concat=n={len(scene_labels)}:v=1:a=0,ass=filename={_filter_path(ass)},format=yuv420p[body]")
    filter_file = work / "body-filter.txt"
    filter_file.write_text(";\n".join(graph), encoding="utf-8")
    body = work / "body.mp4"
    argv += ["-filter_complex_script", str(filter_file), "-map", "[body]", "-an", "-frames:v", str(body_frames),
             "-r", str(fps), "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "18", "-b:v", "0",
             "-profile:v", "high", "-level:v", "5.0", "-bf", "2", "-b_ref_mode", "disabled", "-pix_fmt", "yuv420p", "-video_track_timescale", "12288", "-movflags", "+faststart", str(body)]
    started = time.monotonic()
    with gpu_lease(root, "cutout-" + str(uuid.uuid4())) as (store, lease):
        if _run(argv, work / "render.log", store=store, lease=lease):
            raise RuntimeError(f"Cutout render failed; see {work / 'render.log'}")
    render_seconds = time.monotonic() - started
    # PCM composition preserves every original narration sample at offset 1.5s.
    pcm = work / "soundtrack.wav"
    audio_command = [tools["ffmpeg"], "-hide_banner", "-nostdin", "-n", "-v", "error", "-i", str(intro), "-i", str(narration),
                     "-filter_complex", "[0:a]atrim=end_sample=72000,asetpts=PTS-STARTPTS,aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=mono[a0];[1:a]aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=mono[a1];[a0][a1]concat=n=2:v=0:a=1[a]",
                     "-map", "[a]", "-c:a", "pcm_s16le", str(pcm)]
    if _run(audio_command, work / "soundtrack.log"):
        raise RuntimeError("PCM soundtrack composition failed")
    with wave.open(str(pcm)) as wav:
        final_pcm_frames = wav.getnframes()
        wav.setpos(72000)
        if wav.readframes(wav_params.nframes) != wav_data or final_pcm_frames != 72000 + wav_params.nframes:
            raise RuntimeError("Narration PCM samples changed or the intro offset is incorrect")
    # Strip intro audio before video concatenation so AAC encoder priming cannot
    # shift the entire video timeline. Match the intro's two-frame reorder delay.
    intro_video = work / "intro-video.mp4"
    if _run([tools["ffmpeg"], "-hide_banner", "-nostdin", "-n", "-v", "error", "-i", str(intro),
             "-map", "0:v:0", "-an", "-c:v", "copy", "-video_track_timescale", "12288", str(intro_video)], work / "intro-video.log"):
        raise RuntimeError("Cannot isolate the approved intro video")
    concat_list = work / "video-concat.txt"
    def quote_path(p):
        return str(p).replace("\\", "/").replace("'", "'\\''")
    concat_list.write_text(f"file '{quote_path(intro_video)}'\nduration 1.5\nfile '{quote_path(body)}'\n", encoding="utf-8")
    final_command = [tools["ffmpeg"], "-hide_banner", "-nostdin", "-n", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                     "-i", str(pcm), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                     "-video_track_timescale", "12288", "-movflags", "+faststart", str(output)]
    if _run(final_command, work / "mux.log"):
        raise RuntimeError("Final mux failed")
    result_probe, result_decode = probe(output, tools["ffprobe"]), decode(output, tools["ffmpeg"])
    if not result_probe["ok"] or not result_decode["ok"]:
        raise RuntimeError("Final master failed full probe/decode")
    result_video = next(s for s in result_probe["streams"] if s["codec_type"] == "video")
    if result_video.get("avg_frame_rate") != "24/1" or float(result_video.get("start_time", -1)) != 0 or abs(float(result_video.get("duration", 0)) - (36 + body_frames) / fps) > 0.00001:
        raise RuntimeError("Final video start, cadence, or duration differs from the frame plan")
    pts_result = subprocess.run([tools["ffprobe"], "-v", "error", "-select_streams", "v:0", "-show_frames",
                                 "-show_entries", "frame=best_effort_timestamp", "-of", "json", str(output)],
                                capture_output=True, text=True, check=True, timeout=120)
    pts = [f["best_effort_timestamp"] for f in json.loads(pts_result.stdout)["frames"]]
    if pts != [512 * i for i in range(36 + body_frames)]:
        raise RuntimeError("Every decoded frame must occur at its exact 24 fps timestamp")
    final_hashes, intro_hashes = frame_hashes(output, tools["ffmpeg"]), frame_hashes(intro, tools["ffmpeg"])
    if len(final_hashes) != 36 + body_frames or final_hashes[:36] != intro_hashes:
        raise RuntimeError("Intro pixels changed or final frame count is wrong")
    if any(file_hash(Path(p)) != value for p, value in source_hashes.items()):
        raise RuntimeError("A source changed during render")
    receipt = {"status": "TECHNICAL_PASS", "publication": "NOT_PUBLISHED", "output_path": str(output), "sha256": file_hash(output),
               "size_bytes": output.stat().st_size, "fps": fps, "frames": len(final_hashes), "duration_seconds": result_probe["duration_seconds"],
               "body_frames": body_frames, "intro_frames": 36, "intro_pixels_preserved": True, "narration_pcm_samples_preserved": True,
               "every_frame_pts_checked": True, "video_start_seconds": 0,
               "narration_offset_samples": 72000, "narration_samples": wav_params.nframes, "narration_duration_seconds": duration,
               "audio_speed_factor": 1.0, "pitch_shift": False, "audio_delivery_codec": "aac", "end_visual_rounding_seconds": narrated_body_frames / fps - duration,
               "end_card_frames": end_card_frames, "end_card_audio_policy": "no additional speech or voice retiming",
               "render_seconds": render_seconds, "encoder": "h264_nvenc", "gpu_lease": True, "source_sha256": source_hashes,
               "full_decode": result_decode, "probe": result_probe, "independent_editorial_qa": "PENDING", "independent_audiovisual_qa": "PENDING",
               "manifest": str(manifest_path), "production_qualified": False}
    with receipt_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt
