"""Deterministic native master assembly; semantic QA and publication stay separate."""
from pathlib import Path
import subprocess
import shutil
import wave

from .cache import file_hash
from .config import read_json, write_json
from .media import discover, probe, decode
from .native_batch import ref, immutable


def checked(reference):
    path = Path(reference['path'])
    if file_hash(path) != reference['sha256']:
        raise ValueError('Native master input changed')
    return path


def render_master(visual, narration, captions, music, output, evidence, *, music_start):
    """Render exactly 750 native frames, with a quiet music bed and literal ASS."""
    visual, narration, captions, music, output, evidence = map(Path,
        (visual, narration, captions, music, output, evidence))
    if output.exists() or (evidence / 'render-intent.json').exists():
        raise ValueError('Existing master render requires reconciliation')
    info = probe(visual)
    video = next((s for s in info.get('streams', []) if s['codec_type'] == 'video'), {})
    if (not info['ok'] or (video.get('width'), video.get('height'), video.get('avg_frame_rate')) != (720,1280,'24/1')
            or int(video.get('nb_frames', 0)) != 750):
        raise ValueError('Native visual does not meet timeline contract')
    with wave.open(str(narration)) as audio:
        if abs(audio.getnframes() / audio.getframerate() - 31.25) > .001:
            raise ValueError('Native narration must fit the timeline exactly')
    if not isinstance(music_start, (int, float)) or not 0 <= music_start < 100000:
        raise ValueError('Invalid music offset')
    evidence.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    # A fixed local filename avoids quoting an arbitrary Windows path in libass.
    staged = evidence / 'captions.ass'
    if staged.exists() and file_hash(staged) != file_hash(captions):
        raise ValueError('Staged captions changed')
    if not staged.exists():
        shutil.copyfile(captions, staged)
    binding = {k: ref(p) for k,p in [('visual',visual),('narration',narration),('captions',captions),('music',music)]}
    write_json(evidence / 'render-intent.json', {'inputs': binding, 'output':str(output),
        'music_start_seconds':music_start, 'duration_seconds':31.25}, exclusive=True)
    graph = ('[0:v]ass=filename=captions.ass[v];'
        '[1:a]aresample=48000,aformat=channel_layouts=stereo[voice];'
        '[2:a]atrim=duration=31.25,asetpts=PTS-STARTPTS,aresample=48000,'
        'aformat=channel_layouts=stereo,volume=0.07,afade=t=in:d=0.6,'
        'afade=t=out:st=30.25:d=1[music];'
        '[voice][music]amix=inputs=2:duration=first:normalize=0,'
        'alimiter=limit=0.95:level=false:latency=true[a]')
    command = [discover()['ffmpeg'], '-nostdin','-n','-v','error','-i',str(visual.resolve()),
        '-i',str(narration.resolve()),'-ss',str(music_start),'-i',str(music.resolve()),
        '-filter_complex',graph,'-map','[v]','-map','[a]','-t','31.25',
        '-c:v','libx264','-preset','medium','-crf','16','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','192k','-movflags','+faststart',str(output.resolve())]
    with (evidence / 'render.log').open('x', encoding='utf-8') as log:
        run = subprocess.run(command,cwd=evidence,stdout=log,stderr=log,timeout=600,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if run.returncode:
        raise ValueError('Native master render failed; preserve intent and log')
    inspected = probe(output)
    videos = [s for s in inspected.get('streams',[]) if s['codec_type']=='video']
    audios = [s for s in inspected.get('streams',[]) if s['codec_type']=='audio']
    if (not inspected['ok'] or len(videos)!=1 or len(audios)!=1
            or int(videos[0].get('nb_frames',0)) != 750
            or abs(float(videos[0]['duration'])-31.25) > .001
            or abs(float(audios[0]['duration'])-31.25) > .05 or not decode(output)['ok']):
        raise ValueError('Native master failed full decode, frame count or sync validation')
    result = {'status':'TECHNICAL_PASS', **ref(output), 'inputs':binding,
        'frames':750,'duration_seconds':31.25,'full_decode':True,'published':False,
        'independent_audiovisual_review':'pending'}
    write_json(evidence / 'result.json',result,exclusive=True)
    return result


def build_native_master(request_path, evidence, *, root):
    request = read_json(Path(request_path))
    if request.get('kind') != 'native_master_v1' or request.get('channel_id') != 'religion':
        raise ValueError('Unsupported native master')
    output = Path(request['output']).resolve()
    if not output.is_relative_to(Path('E:/Las palabras del señor/reels').resolve()):
        raise ValueError('Religion master must remain in the authorized E: root')
    music = read_json(checked(request['music_allocation']))
    from .music_allocation import reserve
    live_config = read_json(Path(root) / 'local.json')['channels']['religion']['music']
    if reserve(root, request['job_id'], live_config) != music:
        raise ValueError('Music reservation no longer matches its durable record')
    license_record = read_json(checked(music['license']))
    if (music.get('job_id') != request['job_id'] or music.get('duration_ms') != 31250
            or music.get('status') != 'reserved' or license_record.get('status') != 'approved_music_source'
            or 'monetized_youtube' not in license_record.get('license',{}).get('approved_scope',[])
            or music['source']['sha256'].lower() != license_record['source_file']['sha256'].lower()):
        raise ValueError('Music needs an approved source and a job-bound unused allocation')
    start = music.get('start_ms')
    if (isinstance(start, bool) or not isinstance(start, int) or start < 0
            or start + 31250 > license_record['source_file']['duration_seconds'] * 1000):
        raise ValueError('Music allocation exceeds the approved source')
    return render_master(checked(request['visual']),checked(request['narration']),
        checked(request['captions']),checked(music['source']),output,Path(evidence),
        music_start=music['start_ms']/1000)


def advance_native_master(root, queue, *, only_job):
    root = Path(root)
    steps = [s for s in queue.list() if s['job_id'] == only_job]
    if any(s['adapter'] == 'native_master' for s in steps):
        return
    fit_path = root / '.runtime/jobs' / only_job / 'native-audio-fit/result.json'
    if not fit_path.exists():
        return
    fit = read_json(fit_path)
    voices = [s for s in steps if s['id'] == fit['voice_step'] and s['state'] == 'accepted']
    captions = [s for s in steps if s['id'] == fit['captions_step'] and s['state'] == 'accepted']
    visuals = [s for s in steps if s['adapter'] == 'native_visual' and s['state'] == 'accepted']
    if len(voices) != 1 or len(captions) != 1 or len(visuals) != 1:
        raise ValueError('Master requires one accepted voice, caption set and visual timeline')
    audio = checked(fit)
    if fit['source']['sha256'] != voices[0]['result']['sha256']:
        raise ValueError('Fitted audio belongs to a different narration')
    caption = captions[0]['result']
    if caption['binding']['audio_sha256'] != voices[0]['result']['sha256']:
        raise ValueError('Captions belong to a different narration')
    visual = visuals[0]['result']
    for artifact in (caption,visual):
        checked(artifact)
    source = read_json(checked(voices[0]['payload']['inputs'][0]))
    creative = read_json(checked(source['creative']))
    title = creative.get('editorial_title') or creative.get('title')
    if not isinstance(title,str) or not title.strip() or any(c in title for c in '<>:"/\\|?*'):
        raise ValueError('Native master needs an editorial title safe for a filename')
    from .music_allocation import reserve
    config = read_json(root / 'local.json')['channels']['religion'].get('music')
    if not config:
        raise ValueError('Configure the approved music source and historical allocation register')
    folder = root / '.runtime/jobs' / only_job / 'native-master'
    music = immutable(folder / 'music-allocation.json',reserve(root,only_job,config))
    request = immutable(folder / 'request.json',{'kind':'native_master_v1','channel_id':'religion',
        'job_id':only_job,'visual':ref(Path(visual['path'])),'narration':ref(audio),
        'captions':ref(Path(caption['path'])),'music_allocation':ref(music),
        'output':str(Path(visual['path']).parent / (title + '.mp4'))})
    return queue.register({'schema_version':1,'channel_id':'religion','job_id':only_job,
        'adapter':'native_master','mode':voices[0]['mode'],
        'depends_on':[voices[0]['id'],captions[0]['id'],visuals[0]['id']], 'inputs':[ref(request)]})
