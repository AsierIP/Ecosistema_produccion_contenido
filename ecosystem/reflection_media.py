"""Simple horizontal reflection blocks. Separate from the qualified reel contract."""
from pathlib import Path
import math
import uuid
import json
import subprocess
from .cache import file_hash
from .config import ROOT, read_json, write_json
from .media import discover, probe, decode
from .rife import gpu_lease, _run


def counted_frames(path):
    run = subprocess.run([discover()['ffprobe'], '-v', 'error', '-count_frames',
                          '-select_streams', 'v:0', '-show_entries', 'stream=nb_read_frames',
                          '-of', 'json', str(path)], capture_output=True, check=True)
    return int(json.loads(run.stdout)['streams'][0]['nb_read_frames'])


def slow_block(source, output, frames, *, root=ROOT, multiplier=6):
    """Interpolate one native shot on the GPU, then play its frames at 24 fps."""
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    if not isinstance(frames, int) or not 24 <= frames <= 24 * 40 or multiplier not in (2, 6):
        raise ValueError('Reflection interpolation requires a bounded 2x or legacy 6x operation')
    receipt_path = output.with_suffix('.json')
    binding = {'source_sha256': file_hash(source), 'frames': frames, 'multiplier': multiplier}
    if receipt_path.exists():
        result = read_json(receipt_path)
        if result['binding'] != binding or file_hash(output) != result['sha256']:
            raise ValueError('Existing reflection block changed')
        return result
    if output.exists():
        raise ValueError('Incomplete block requires reconciliation; preserve the prior output')
    tools = discover()
    native = probe(source)
    stream = next(s for s in native['streams'] if s['codec_type'] == 'video')
    if not native['ok'] or stream['width'] <= stream['height'] or stream['avg_frame_rate'] != '24/1':
        raise ValueError('A horizontal native 24 fps source is required')
    count = int(stream['nb_frames'])
    if frames > (count - 1) * multiplier + 1:
        raise ValueError('Native clip is too short for this reflection block')
    work = output.parent / (output.stem + '-work')
    work.mkdir(parents=True, exist_ok=True)
    guarded, raw = work / 'guarded.mkv', work / 'interpolated.mkv'
    recovered = raw.exists()
    if recovered:
        if read_json(work / 'intent.json') != binding or not decode(raw)['ok']:
            raise ValueError('Earlier interpolation cannot be reconciled')
    elif guarded.exists():
        raise ValueError('An incomplete GPU attempt requires reconciliation')
    else:
        write_json(work / 'intent.json', binding, exclusive=True)
    guard = [tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-i', str(source), '-an',
             '-vf', 'tpad=stop_mode=clone:stop=3', '-c:v', 'ffv1', '-pix_fmt', 'yuv420p', str(guarded)]
    if not recovered and _run(guard, work / 'guard.log'):
        raise RuntimeError('Could not prepare interpolation guard frames')
    code = None
    if not recovered:
      with gpu_lease(root, 'reflection-' + str(uuid.uuid4())) as (store, lease):
        code = _run([tools['video2x'], '-i', str(guarded), '-o', str(raw), '-p', 'rife', '-m', str(multiplier),
                     '--rife-model', 'rife-v4.25', '-d', '0', '-c', 'ffv1', '--pix-fmt', 'yuv420p',
                     '--no-copy-streams', '--scene-thresh', '100', '--log-level', 'info'],
                    work / 'rife.log', store=store, lease=lease)
    if (not recovered and code not in (0, -1073741819, 3221225477)) or not decode(raw)['ok']:
        raise RuntimeError('GPU interpolation did not yield a complete decodable stream')
    actual = probe(raw)
    raw_stream = next(s for s in actual['streams'] if s['codec_type'] == 'video')
    if counted_frames(raw) < frames:
        raise RuntimeError('GPU interpolation has too few frames')
    command = [tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-i', str(raw), '-an',
               '-vf', f'trim=end_frame={frames},setpts=N/(24*TB),scale=1920:1080:flags=lanczos',
               '-r', '24', '-frames:v', str(frames), '-c:v', 'h264_nvenc', '-preset', 'p6', '-cq', '19',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output)]
    with gpu_lease(root, 'reflection-encode-' + str(uuid.uuid4())) as (store, lease):
        encoded = _run(command, work / 'delivery.log', store=store, lease=lease)
    if encoded or not decode(output)['ok']:
        raise RuntimeError('Reflection slow-motion delivery failed')
    checked = probe(output)
    video = next(s for s in checked['streams'] if s['codec_type'] == 'video')
    if int(video['nb_frames']) != frames or video['avg_frame_rate'] != '24/1':
        raise RuntimeError('Unexpected reflection frame count or cadence')
    if file_hash(source) != binding['source_sha256']:
        raise RuntimeError('Native source changed')
    result = {'status': 'TECHNICAL_PASS', 'path': str(output), 'sha256': file_hash(output),
              'binding': binding, 'duration_seconds': frames / 24, 'gpu': 'Video2X RIFE v4.25 and NVENC',
              'interpolation_exit_code': code, 'interpolated_across_cuts': False,
              'voice_modified': False, 'editorial_review': 'pending'}
    write_json(receipt_path, result, exclusive=True)
    return result


def block_frame_counts(duration, count=10):
    if not 270 <= duration <= 330 or count != 10:
        raise ValueError('This prototype uses ten blocks covering approximately five minutes')
    total = math.ceil(duration * 24)
    return [total // count + (i < total % count) for i in range(count)]


def build_library_sequence(sources, output, *, root=ROOT):
    """Three native shots slowed once to 10 seconds each; reusable silent 30s."""
    sources, output = list(map(Path,sources)), Path(output)
    if len(sources)!=3:
        raise ValueError('Three native shots are required')
    binding=[{'path':str(p.resolve()),'sha256':file_hash(p)} for p in sources]
    receipt=output.with_suffix('.json')
    if output.exists():
        saved=read_json(receipt)
        if saved['sources']!=binding or file_hash(output)!=saved['sha256']:
            raise ValueError('Sequence changed or is incomplete')
        return saved
    work=output.parent/(output.stem+'-work')
    work.mkdir(parents=True,exist_ok=True)
    clips=[]
    for i,source in enumerate(sources,1):
        clip=work/f'clip-{i}.mp4'
        slow_block(source,clip,240,root=root,multiplier=2)
        clips.append(clip)
    listing=work/'clips.txt'
    listing.write_text(''.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for p in clips),encoding='utf-8')
    code=_run([discover()['ffmpeg'],'-nostdin','-n','-v','error','-f','concat','-safe','0','-i',str(listing),
               '-an','-c:v','copy','-movflags','+faststart',str(output)],work/'concat.log')
    if code or not decode(output)['ok'] or counted_frames(output)!=720:
        raise ValueError('Thirty-second sequence failed complete validation')
    result={'path':str(output.resolve()),'sha256':file_hash(output),'sources':binding,
            'duration_seconds':30,'frames':720,'slowdown_operations':1,'slowdown_multiplier':2,
            'audio':False,'captions':False,'style':'photorealistic','quality_review':'pending'}
    write_json(receipt,result,exclusive=True)
    return result


def reflection_captions(alignment, output, *, duration):
    """Horizontal, literal captions from an explicitly reconciled transcript."""
    from .captions import validated_words
    from .comic_graphics import timestamp
    alignment, output = Path(alignment), Path(output)
    record = read_json(alignment)
    expected, words = validated_words(record['transcript'], record['words'], duration)
    if output.exists():
        raise ValueError('Preserve existing prototype subtitles')
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Reflection,Segoe UI Semibold,54,&H00E8F7FF,&H004EA8D5,&H00201912,&HFF000000,-1,0,0,0,100,100,0,0,1,2.3,1.0,2,140,140,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    rows, cues, index = [], [], 0
    while index < len(words):
        high = index + 1
        while high < len(words) and high-index < 8 and len(' '.join(expected[index:high+1])) <= 56:
            if expected[high-1].endswith(('.', '?', '!', ';', ':')):
                break
            high += 1
        text = ' '.join(expected[index:high])
        start, end = words[index]['start'], words[high-1]['end']
        rows.append(f'Dialogue: 0,{timestamp(start)},{timestamp(end)},Reflection,,0,0,0,,{text}')
        cues.append({'start': start, 'end': end, 'text': text})
        index = high
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header+'\n'.join(rows)+'\n', encoding='utf-8-sig')
    result = {'path': str(output.resolve()), 'sha256': file_hash(output), 'cues': cues,
              'transcript': record['transcript'], 'alignment_sha256': file_hash(alignment),
              'audio_sha256': record['audio_sha256'], 'literal_text_matches': True,
              'profile': 'religion-reflection-horizontal-ivory-v1'}
    write_json(output.with_suffix('.json'), result, exclusive=True)
    return result


def assemble(blocks, narration, music, subtitles, output, *, root=ROOT, sequence_plan=None):
    """Concatenate ten distinct blocks with one continuous, unretimed narration."""
    import wave
    paths = list(map(Path, blocks))
    narration, music, subtitles, output = map(Path, (narration, music, subtitles, output))
    if sequence_plan is None and (len(paths) != 10 or len({file_hash(p) for p in paths}) != 10):
        raise ValueError('Ten distinct processed visual blocks are required')
    if output.exists():
        raise ValueError('Preserve an existing prototype master')
    with wave.open(str(narration)) as wav:
        duration = wav.getnframes() / wav.getframerate()
    if sequence_plan is None:
        expected = block_frame_counts(duration)
        for p, count in zip(paths, expected):
            receipt = read_json(p.with_suffix('.json'))
            if receipt['sha256'] != file_hash(p) or receipt['binding']['frames'] != count:
                raise ValueError('Block is not bound to this narration timeline')
    else:
        from .sequence_library import SequenceLibrary
        library = SequenceLibrary(root)
        items = sequence_plan['items']
        if len(items) != len(paths) or len(items) != math.ceil(duration/30) or abs(sequence_plan['duration_seconds']-duration)>.001:
            raise ValueError('Library plan does not cover this narration')
        previous = None
        for i, (p, item) in enumerate(zip(paths, items)):
            row = library.get(item['sequence_id'])
            library.verify(row)
            if (Path(row['path']).resolve()!=p.resolve() or row['sha256']!=item['sha256']
                    or row['environment']==previous or item['start_seconds']!=i*30):
                raise ValueError('Library timeline changed or repeats an adjacent environment')
            previous=row['environment']
        expected = [math.ceil(duration*24)]
    tools = discover()
    work = output.parent / (output.stem + '-assembly')
    work.mkdir(parents=True, exist_ok=True)
    listing = work / 'blocks.txt'
    listing.write_text(''.join("file '" + str(p.resolve()).replace('\\','/').replace("'", "'\\''") + "'\n" for p in paths), encoding='utf-8')
    refs = [{'path': str(p.resolve()), 'sha256': file_hash(p)} for p in paths + [narration, music, subtitles]]
    write_json(work / 'inputs.json', refs, exclusive=True)
    ass = str(subtitles.resolve()).replace('\\','/').replace(':', '\\:').replace("'", "\\'")
    graph = (f"[0:v]ass=filename='{ass}'[v];[1:a]aresample=48000[voice];"
             f"[2:a]aresample=48000,volume=0.10,apad,atrim=0:{duration:.6f},afade=t=out:st={duration-4:.6f}:d=4[bed];"
             "[voice][bed]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    command = [tools['ffmpeg'], '-nostdin', '-n', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing),
               '-i', str(narration), '-i', str(music), '-filter_complex', graph, '-map', '[v]', '-map', '[a]',
               '-c:v', 'h264_nvenc', '-preset', 'p6', '-cq', '19', '-pix_fmt', 'yuv420p', '-r', '24',
               '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', '-t', f'{sum(expected)/24:.6f}', str(output)]
    with gpu_lease(root, 'reflection-master-' + str(uuid.uuid4())) as (store, lease):
        code = _run(command, work / 'render.log', store=store, lease=lease)
    if code or not decode(output)['ok']:
        raise RuntimeError('Prototype master failed full decoding')
    video = next(s for s in probe(output)['streams'] if s['codec_type'] == 'video')
    if (video['width'], video['height'], int(video['nb_frames'])) != (1920, 1080, sum(expected)):
        raise RuntimeError('Prototype master has an unexpected raster or duration')
    if any(file_hash(Path(r['path'])) != r['sha256'] for r in refs):
        raise RuntimeError('An assembly input changed')
    result = {'status':'TECHNICAL_PASS','path':str(output.resolve()),'sha256':file_hash(output),
              'duration_seconds':sum(expected)/24,'frames':sum(expected),'visual_blocks':len(paths),'voice_speed_factor':1.0,
              'library_plan_id':sequence_plan['plan_id'] if sequence_plan else None,
              'inputs':refs,'independent_audiovisual_review':'pending','publication':'not_uploaded'}
    write_json(output.with_suffix('.json'), result, exclusive=True)
    return result
