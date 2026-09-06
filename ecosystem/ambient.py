"""Local GPU animation of illustration regions; never modifies the source image."""
from __future__ import annotations
import json
import math
from pathlib import Path
import subprocess
import time
import uuid
from .cache import file_hash
from .media import discover, decode, probe
from .rife import gpu_lease


def render(manifest_path, root):
    # These are existing optional GPU-runtime packages, never auto-installed.
    import numpy as np
    import torch
    import torch.nn.functional as F
    from PIL import Image
    cfg = json.loads(Path(manifest_path).read_text(encoding='utf-8-sig'))
    source, output = Path(cfg['image']).resolve(strict=True), Path(cfg['output']).resolve()
    evidence = Path(cfg['evidence']).resolve()
    if output.exists() or evidence.exists():
        raise ValueError('Use new output and evidence paths; previous attempts are immutable')
    if not torch.cuda.is_available():
        raise RuntimeError('Existing CUDA runtime required; no silent CPU substitution')
    width, height, fps, frames = 1080, 1920, 24, int(cfg['frames'])
    if not 1 <= frames <= 24 * 120:
        raise ValueError('Animation must be bounded to 1 frame through 120 seconds')
    tools = discover()
    source_hash = file_hash(source)
    # Resize is only an in-memory delivery transform for the video frame stream.
    with Image.open(source) as im:
        a = np.asarray(im.convert('RGB').resize((width, height), Image.Resampling.LANCZOS)).copy()
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    log_path = output.with_suffix('.encode.log')
    if log_path.exists():
        raise ValueError('Previous encode log already exists')
    command = [tools['ffmpeg'], '-hide_banner', '-nostdin', '-n', '-v', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}', '-r', str(fps), '-i', 'pipe:0',
               '-an', '-frames:v', str(frames), '-c:v', 'h264_nvenc', '-preset', 'p6', '-cq', '18', '-b:v', '0',
               '-pix_fmt', 'yuv420p', '-profile:v', 'high', '-bf', '2', '-video_track_timescale', '12288',
               '-movflags', '+faststart', str(output)]
    started = time.monotonic()
    with gpu_lease(Path(root).resolve(), 'ambient-' + str(uuid.uuid4())) as (store, lease):
        src = torch.from_numpy(a).to('cuda', dtype=torch.float32).permute(2,0,1).unsqueeze(0) / 255
        yy, xx = torch.meshgrid(torch.linspace(0,1,height,device='cuda'), torch.linspace(0,1,width,device='cuda'), indexing='ij')
        base = torch.stack((xx*2-1, yy*2-1), dim=-1)
        regions = []
        for region in cfg['regions']:
            x0,y0,x1,y1 = region['rect']
            feather = float(region.get('feather', .035))
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 and feather > 0):
                raise ValueError('Invalid normalized region rectangle or feather')
            def smooth(v):
                v = torch.clamp(v, 0, 1)
                return v*v*(3-2*v)
            mask = smooth((xx-x0)/feather)*smooth((x1-xx)/feather)*smooth((yy-y0)/feather)*smooth((y1-yy)/feather)
            regions.append((region, mask))
        last_renewal = time.monotonic()
        with log_path.open('x', encoding='utf-8') as log:
            p = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            try:
                with torch.inference_mode():
                    for index in range(frames):
                        t = index/fps
                        grid = base.clone()
                        for region, mask in regions:
                            phase = t*2*math.pi/region.get('period',3) + yy*region.get('spatial_y',0) + xx*region.get('spatial_x',0)
                            grid[:,:,0] += mask*region.get('dx',0)*torch.sin(phase)*2/(width-1)
                            grid[:,:,1] += mask*region.get('dy',0)*torch.sin(phase*1.13+.7)*2/(height-1)
                        frame = F.grid_sample(src, grid.unsqueeze(0), mode='bilinear', padding_mode='border', align_corners=True)
                        encoded = (frame[0].permute(1,2,0)*255).clamp(0,255).to(torch.uint8).cpu().numpy()
                        p.stdin.write(encoded.tobytes())
                        if time.monotonic()-last_renewal > 20:
                            if not store.renew_lease('gpu', lease['owner'], lease['token'], 120):
                                raise RuntimeError('Lost GPU lease during animation')
                            last_renewal = time.monotonic()
                p.stdin.close()
                if p.wait(timeout=120):
                    raise RuntimeError(f'NVENC encoder failed; see {log_path}')
            except BaseException:
                p.kill()
                p.wait()
                raise
        device = torch.cuda.get_device_name(0)
        del src, base, xx, yy, regions
        torch.cuda.empty_cache()
    checked, decoded = probe(output, tools['ffprobe']), decode(output, tools['ffmpeg'])
    stream = next(s for s in checked.get('streams',[]) if s['codec_type']=='video')
    if not checked['ok'] or not decoded['ok'] or int(stream['nb_frames']) != frames or stream['avg_frame_rate'] != '24/1':
        raise RuntimeError('GPU animation failed decode/frame validation')
    if file_hash(source) != source_hash:
        raise RuntimeError('Source changed during video animation')
    receipt = {'status':'TECHNICAL_PASS','gpu':device,'gpu_lease':True,'renderer':'torch CUDA grid_sample + NVENC',
               'source':str(source),'source_sha256':source_hash,'source_modified':False,'output':str(output),
               'sha256':file_hash(output),'frames':frames,'fps':fps,'seconds':frames/fps,
               'render_seconds':time.monotonic()-started,'regions':cfg['regions'],
               'motion_scope':'Illustration only; not applied to documentary photographs',
               'full_decode':decoded,'editorial_qa_passed':False}
    evidence.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt
