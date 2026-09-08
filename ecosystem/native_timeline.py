"""Assemble the three accepted native scenes; never interpolate across boundaries."""
from pathlib import Path
import subprocess
from .cache import file_hash
from .config import read_json, write_json
from .media import discover, probe, decode
from .rife import frame_hashes
from .native_batch import ref, immutable
from .native_conform import accepted_source


def assemble_visual(paths, output, evidence):
    paths, output, evidence = list(map(Path, paths)), Path(output), Path(evidence)
    if len(paths) != 3 or len({file_hash(p) for p in paths}) != 3:
        raise ValueError('Three distinct conformed scenes are required')
    if output.exists() or evidence.exists():
        raise ValueError('Existing visual assembly requires reconciliation')
    tools = discover(); ffmpeg = tools['ffmpeg']
    source_refs = [ref(p) for p in paths]
    source_frames = []
    for path in paths:
        inspection = probe(path)
        stream = next(s for s in inspection['streams'] if s['codec_type'] == 'video')
        hashes = frame_hashes(path, ffmpeg)
        if (not inspection['ok'] or not decode(path)['ok'] or len(hashes) != 250
                or (stream['width'], stream['height'], stream['avg_frame_rate']) != (720, 1280, '24/1')):
            raise ValueError('A conformed scene does not meet its frame/raster/cadence contract')
        source_frames.append(hashes)
    # Replace each continuation's first frame, preserving exactly 250 frames per scene.
    graph = ('[0:v]split=2[a][ae];[1:v]split=2[b][be];'
        '[ae]trim=start_frame=249:end_frame=250,setpts=PTS-STARTPTS[x];'
        '[b]trim=start_frame=1:end_frame=250,setpts=PTS-STARTPTS[y];'
        '[be]trim=start_frame=249:end_frame=250,setpts=PTS-STARTPTS[z];'
        '[2:v]trim=start_frame=1:end_frame=250,setpts=PTS-STARTPTS[c];'
        '[a]setpts=PTS-STARTPTS[aa];[aa][x][y][z][c]concat=n=5:v=1:a=0,setpts=N/(24*TB)[out]')
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [ffmpeg, '-nostdin', '-n', '-v', 'error']
    for path in paths:
        command += ['-i', str(path)]
    command += ['-filter_complex', graph, '-map', '[out]', '-an', '-frames:v', '750', '-r', '24',
                '-c:v', 'libx264', '-preset', 'fast', '-qp', '0', '-pix_fmt', 'yuv420p',
                '-video_track_timescale', '24000', '-movflags', '+faststart', str(output)]
    run = subprocess.run(command, capture_output=True, timeout=300,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if run.returncode:
        raise ValueError('Visual assembly failed: ' + run.stderr.decode('utf-8', errors='replace')[-1000:])
    actual = frame_hashes(output, ffmpeg)
    expected = source_frames[0] + [source_frames[0][-1]] + source_frames[1][1:] + [source_frames[1][-1]] + source_frames[2][1:]
    if actual != expected or not decode(output)['ok']:
        raise ValueError('Assembly altered or lost timeline frames')
    if any(file_hash(Path(s['path'])) != s['sha256'] for s in source_refs):
        raise ValueError('Conformed source changed during assembly')
    result = {'status': 'TECHNICAL_PASS', 'path': str(output), 'sha256': file_hash(output),
              'frames': 750, 'fps': 24, 'duration_seconds': 31.25, 'sources': source_refs,
              'boundary_normalization_replaces_not_appends': True,
              'boundary_pairs': [{'indices': [a, b], 'identical_decoded_yuv': actual[a] == actual[b]}
                                 for a, b in ((249, 250), (499, 500))],
              'all_timeline_frame_hashes_verified': True, 'independent_visual_review': 'pending'}
    write_json(evidence, result, exclusive=True)
    return result


def build_native_visual(request_path, output_dir, *, root):
    request = read_json(Path(request_path))
    if request.get('kind') != 'native_visual_v1' or request.get('channel_id') != 'religion':
        raise ValueError('Unsupported native visual assembly')
    output = Path(request['output']).resolve()
    allowed = Path('E:/Las palabras del señor/reels/.temp').resolve()
    if not output.is_relative_to(allowed):
        raise ValueError('Religion visual media must remain in the authorized E: root')
    scenes = request['scenes']
    if [s['segment_id'] for s in scenes] != ['s01', 's02', 's03']:
        raise ValueError('Native timeline order must be s01, s02, s03')
    paths = []
    for scene in scenes:
        selection, source = accepted_source(scene['selection'])
        if selection['segment_id'] != scene['segment_id'] or selection['sequence_id'] != request['sequence_id']:
            raise ValueError('Selection belongs to another native scene')
        conform_ref = scene['conform_receipt']
        if file_hash(Path(conform_ref['path'])) != conform_ref['sha256']:
            raise ValueError('Native conform receipt changed')
        conform = read_json(Path(conform_ref['path']))
        if (conform['status'] != 'TECHNICAL_PASS' or conform['source_sha256'] != file_hash(source)
                or conform['gpu_execution'] is not True or conform['native_frames_preserved'] != 125
                or conform['output_sha256'] != file_hash(Path(conform['output_path']))):
            raise ValueError('Conformed scene lost GPU/source integrity')
        paths.append(Path(conform['output_path']))
    return assemble_visual(paths, output, Path(output_dir) / 'visual-result.json')


def advance_native_visual(root, queue, *, only_job):
    root = Path(root); steps = queue.list()
    for sequence_path in (root / '.runtime/upro/native-sequences').glob('*/sequence.json'):
        spec = read_json(sequence_path)
        if spec['job_id'] != only_job:
            continue
        status_path = sequence_path.parent / 'status.json'
        if not status_path.exists():
            continue
        status = read_json(status_path)
        if status.get('status') != 'NATIVE_SEQUENCE_ACCEPTED':
            continue
        scenes, dependencies = [], []
        for selection_ref in status['segments']:
            selection, source = accepted_source(selection_ref)
            matches = [s for s in steps if s['job_id'] == only_job and s['adapter'] == 'native_conform'
                       and s['state'] == 'accepted' and s['result'].get('source_sha256') == file_hash(source)]
            if len(matches) != 1:
                break
            conform = matches[0]
            receipt = Path(conform['result']['output_path']).with_suffix('.rife.json')
            scenes.append({'segment_id': selection['segment_id'], 'selection': selection_ref, 'conform_receipt': ref(receipt)})
            dependencies.append(conform['id'])
        if len(scenes) != 3:
            continue
        path = immutable(sequence_path.parent / 'visual-request.json', {'kind': 'native_visual_v1',
            'channel_id': 'religion', 'sequence_id': spec['sequence_id'], 'scenes': scenes,
            'output': str(Path(spec['native_root']).parent / 'visual-master.mp4')})
        queue.register({'schema_version': 1, 'channel_id': 'religion', 'job_id': only_job,
                        'adapter': 'native_visual', 'mode': spec['mode'], 'depends_on': dependencies, 'inputs': [ref(path)]})


def native_voice_ready(step, queue):
    """A queued native voice waits for the assembled visual, without calling TTS."""
    if step['adapter'] != 'voice_generate' or step['channel_id'] != 'religion':
        return True
    request_ref = step['payload']['inputs'][0]
    if file_hash(Path(request_ref['path'])) != request_ref['sha256']:
        raise ValueError('Native narration request changed')
    request = read_json(Path(request_ref['path']))
    if not request.get('native_sequence'):
        return True
    for candidate in queue.list():
        if (candidate['job_id'] != step['job_id'] or candidate['adapter'] != 'native_visual'
                or candidate['state'] != 'accepted'):
            continue
        visual_ref = candidate['payload']['inputs'][0]
        if file_hash(Path(visual_ref['path'])) != visual_ref['sha256']:
            raise ValueError('Native visual request changed')
        visual = read_json(Path(visual_ref['path']))
        if visual['sequence_id'] != request['native_sequence']:
            continue
        result = candidate['result']
        if (result.get('status') != 'TECHNICAL_PASS' or result.get('frames') != 750
                or result.get('all_timeline_frame_hashes_verified') is not True
                or file_hash(Path(result['path'])) != result['sha256']):
            raise ValueError('Native visual lost integrity before voice generation')
        return True
    return False
