"""Cache a captioned copy of the existing comic intro, preserving its audio."""
from pathlib import Path
import uuid
from .cache import file_hash
from .config import read_json, write_json
from .comic_graphics import Canvas
from .media import discover, probe, decode, _filter_path
from .rife import _run, gpu_lease


def caption_intro(source, output_dir, *, root):
    source, output_dir = Path(source), Path(output_dir)
    digest = file_hash(source)
    folder = output_dir / (digest[:16] + '-captions-v1')
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / 'intro.mp4'
    receipt_path = folder / 'receipt.json'
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt['source_sha256'] != digest or receipt['sha256'] != file_hash(output):
            raise ValueError('Captioned intro cache changed')
        return output
    if output.exists():
        raise ValueError('Incomplete intro attempt requires reconciliation')
    tools = discover()
    info = probe(source, tools['ffprobe'])
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if (video.get('width'), video.get('height'), video.get('nb_frames'), video.get('r_frame_rate')) != (1080,1920,'36','24/1'):
        raise ValueError('Expected existing 36-frame channel intro')
    captions = folder / 'intro.ass'
    canvas = Canvas()
    canvas.text(0, 1.25, '¿Sabías que...?', 540, 1650, size=58, color='#C8FF00', tags=r'\bord3\shad1')
    canvas.save(captions)
    command = [tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-i', str(source),
               '-vf', 'ass=filename=' + _filter_path(captions), '-map', '0:v:0', '-map', '0:a:0',
               '-c:v', 'h264_nvenc', '-preset', 'p6', '-cq', '18', '-b:v', '0',
               '-profile:v', 'high', '-level:v', '5.0', '-bf', '2', '-b_ref_mode', 'disabled',
               '-pix_fmt', 'yuv420p', '-video_track_timescale', '12288', '-c:a', 'copy', str(output)]
    with gpu_lease(root, 'intro-' + str(uuid.uuid4())) as (store, lease):
        if _run(command, folder / 'render.log', store=store, lease=lease):
            raise ValueError('Intro caption render failed')
    result = probe(output, tools['ffprobe'])
    stream = next(s for s in result['streams'] if s['codec_type'] == 'video')
    if stream.get('nb_frames') != '36' or not decode(output, tools['ffmpeg'])['ok']:
        raise ValueError('Captioned intro failed decoding or changed frame count')
    write_json(receipt_path, {'source_sha256': digest, 'sha256': file_hash(output),
        'caption_text': '¿Sabías que...?', 'caption_end_seconds': 1.25,
        'audio_mode': 'stream_copy', 'frames': 36, 'status': 'TECHNICAL_PASS'}, exclusive=True)
    return output
