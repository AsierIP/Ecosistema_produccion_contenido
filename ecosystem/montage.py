"""Prepare the comic master from verified local stages; no generation or release."""
import math
import re
import subprocess
import wave
from pathlib import Path
from .cache import file_hash
from .config import read_json, write_json
from .media import discover


def build_manifest(*, title, transcript, audio, captions, scenes, intro, output_dir, evidence_dir, voice):
    audio, captions, intro = Path(audio), Path(captions), Path(intro)
    output_dir, evidence_dir = Path(output_dir), Path(evidence_dir)
    safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title).strip('. ')[:120]
    if not safe_title or safe_title.upper() in {'CON', 'PRN', 'AUX', 'NUL'}:
        raise ValueError('Invalid output title')
    for path in (audio, captions, intro):
        if not path.is_file():
            raise ValueError('Required master input is missing')
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = evidence_dir / 'master-manifest.json'
    normalized = output_dir / 'narration-48000.wav'
    normalized_receipt = evidence_dir / 'normalized-audio.json'
    binding = {'audio_sha256': file_hash(audio), 'captions_sha256': file_hash(captions),
               'intro_sha256': file_hash(intro), 'title': title, 'transcript': transcript, 'voice': voice,
               'scenes': scenes}
    binding_path = evidence_dir / 'assembly-inputs.json'
    if binding_path.exists() and read_json(binding_path) != binding:
        raise ValueError('Assembly inputs changed; preserve the prior attempt')
    if not binding_path.exists():
        write_json(binding_path, binding, exclusive=True)
    with wave.open(str(audio)) as wav:
        duration = wav.getnframes() / wav.getframerate()
    total = math.ceil(duration * 24)
    if sum(s['frames'] for s in scenes) != total:
        raise ValueError('Scene frames must match the complete narration')
    for scene in scenes:
        source = Path(scene.get('video') or scene.get('image', ''))
        if not source.is_file() or file_hash(source) != scene.get('sha256'):
            raise ValueError('Scene media changed before assembly')
    if normalized.exists():
        if not normalized_receipt.exists() or read_json(normalized_receipt) != {'source_sha256': file_hash(audio), 'sha256': file_hash(normalized)}:
            raise ValueError('Normalized audio is unverified or changed')
    else:
        ffmpeg = discover().get('ffmpeg')
        if not ffmpeg:
            raise ValueError('FFmpeg is unavailable')
        run = subprocess.run([ffmpeg, '-nostdin', '-n', '-v', 'error', '-i', str(audio),
                              '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', str(normalized)],
                             capture_output=True, timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            raise ValueError('Narration normalization failed')
        write_json(normalized_receipt, {'source_sha256': file_hash(audio), 'sha256': file_hash(normalized)}, exclusive=True)
    with wave.open(str(normalized)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (48000, 1, 2) or abs(wav.getnframes() / 48000 - duration) > .001:
            raise ValueError('Normalized audio changed timing')
    manifest = {'schema_version': 2, 'title': title, 'fps': 24, 'width': 1080, 'height': 1920,
                'work_dir': str((output_dir / 'render').resolve()), 'evidence_dir': str((evidence_dir / 'render').resolve()),
                'output': str((output_dir / (safe_title + '.mp4')).resolve()), 'intro': str(intro.resolve()),
                'narration': str(normalized.resolve()), 'ass': str(captions.resolve()), 'scenes': scenes,
                'end_card_seconds': 0, 'caption_transcript': transcript, 'voice': voice, 'publication': 'NOT_PUBLISHED'}
    if manifest_path.exists() and read_json(manifest_path) != manifest:
        raise ValueError('Existing master plan differs from current assembly')
    if not manifest_path.exists():
        write_json(manifest_path, manifest, exclusive=True)
    return manifest_path


def advance_montage(root, queue, *, only_job=None):
    root = Path(root)
    steps = queue.list()
    created = []
    if only_job is None:
        for job_id in {s['job_id'] for s in steps if s['channel_id'] == 'sabias-que'}:
            error_path = root / '.runtime/jobs' / job_id / 'handoffs/error-montage.json'
            try:
                created.extend(advance_montage(root, queue, only_job=job_id))
                if error_path.exists() and read_json(error_path).get('status') != 'resolved':
                    write_json(error_path, {'status': 'resolved'})
            except (ValueError, KeyError, OSError, RuntimeError) as exc:
                problem = {'status': 'blocked', 'reason': str(exc)}
                if not error_path.exists() or read_json(error_path) != problem:
                    write_json(error_path, problem)
        return created
    for job_id in {s['job_id'] for s in steps if s['channel_id'] == 'sabias-que'}:
        if job_id != only_job:
            continue
        job_steps = [s for s in steps if s['job_id'] == job_id]
        if any(s['adapter'] == 'cutout' for s in job_steps):
            continue
        voices = [s for s in job_steps if s['adapter'] == 'voice_generate' and s['state'] == 'accepted']
        if len(voices) != 1:
            continue
        parent = voices[0]
        request = read_json(Path(parent['payload']['inputs'][0]['path']))
        if not request.get('brief_path'):
            continue
        brief = read_json(Path(request['brief_path']))
        if file_hash(Path(request['brief_path'])) != request['brief_sha256']:
            raise ValueError('Storyboard changed before final assembly')
        audio_result = parent['result']
        caption_steps = [s for s in job_steps if s['adapter'] == 'captions' and s['state'] == 'accepted'
                         and parent['id'] in s['payload'].get('depends_on', [])]
        visuals = [s for s in job_steps if s['adapter'] == 'visual' and parent['id'] in s['payload'].get('depends_on', [])]
        from .workflow import documentary_index
        total_frames = math.ceil(audio_result['duration_seconds'] * 24)
        count = math.ceil(audio_result['duration_seconds'] / 5)
        documentary_slot = documentary_index(brief, count)
        if len(caption_steps) != 1 or (not visuals and documentary_slot is None) or any(s['state'] != 'accepted' for s in visuals):
            continue
        scenes, dependencies = [], [parent['id'], caption_steps[0]['id']]
        for visual in visuals:
            planned = read_json(Path(visual['payload']['inputs'][0]['path']))
            if planned['timeline_index'] == documentary_slot:
                continue  # Legacy jobs may contain an unused generated documentary slot.
            animations = [s for s in job_steps if s['adapter'] == 'ambient' and s['state'] == 'accepted'
                          and visual['id'] in s['payload'].get('depends_on', [])]
            if len(animations) != 1:
                break
            animation = animations[0]
            scenes.append({'id': planned['scene_id'], 'frames': planned['frames'], 'video': animation['result']['output'],
                           'sha256': animation['result']['sha256'], 'timeline_index': planned['timeline_index']})
            dependencies.append(animation['id'])
        if len(scenes) != count - (1 if documentary_slot is not None else 0):
            continue
        scenes.sort(key=lambda s: s['timeline_index'])
        documentary = brief.get('documentary', {})
        if documentary.get('needed') is True:
            index = documentary.get('scene_index')
            if (not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < count
                    or not documentary.get('source_url') or not documentary.get('license_evidence')):
                raise ValueError('Documentary image requires a valid position, source and license evidence')
            photo = Path(documentary['path']).resolve(strict=True)
            if file_hash(photo) != documentary['sha256']:
                raise ValueError('Documentary image changed')
            scenes.insert(index, {'id': 'documentary-' + str(index), 'frames': min(120, total_frames - index * 120),
                             'timeline_index': index,
                             'image': str(photo), 'sha256': documentary['sha256'], 'documentary': documentary,
                             'background_filter': "scale=1188:2112:force_original_aspect_ratio=decrease,pad=1188:2112:(ow-iw)/2:(oh-ih)/2:color=0x081629,crop=1080:1920:x='54+20*sin(t*0.35)':y=96,eq=contrast=1.12:saturation=1.06"})
        if [s['timeline_index'] for s in scenes] != list(range(count)):
            raise ValueError('Scene timeline has gaps or duplicate indices')
        captions = caption_steps[0]['result']
        if file_hash(Path(audio_result['path'])) != audio_result['sha256'] or file_hash(Path(captions['path'])) != captions['sha256']:
            raise ValueError('Voice or captions changed after validation')
        local = read_json(root / 'local.json')['channels']['sabias-que']
        from .config import load_channels
        channel = next(c for c in load_channels(root) if c['id'] == 'sabias-que')
        from .intro import caption_intro
        intro = caption_intro(local['intro_path'], Path(local['media_root']) / 'shared-intro', root=root)
        from .caption_alignment import verified_caption_transcript
        caption_transcript = verified_caption_transcript(captions, brief['transcript'], 'sabias-que')
        manifest = build_manifest(title=brief['title'], transcript=caption_transcript, audio=audio_result['path'],
            captions=captions['path'], scenes=scenes, intro=intro,
            output_dir=Path(local['media_root']) / job_id / 'master', evidence_dir=root / '.runtime/jobs' / job_id / 'assembly', voice=channel['voice'])
        inputs = [manifest, Path(request['brief_path']), Path(read_json(manifest)['narration']), Path(captions['path']), intro] + [Path(s.get('video') or s['image']) for s in scenes]
        if captions.get('alignment'):
            inputs.append(Path(captions['alignment']['path']))
        if documentary.get('needed') is True:
            inputs.append(Path(documentary['license_evidence']).resolve())
        created.append(queue.register({'schema_version': 1, 'job_id': job_id, 'channel_id': 'sabias-que',
            'adapter': 'cutout', 'mode': parent['mode'], 'depends_on': dependencies,
            'inputs': [{'path': str(p.resolve()), 'sha256': file_hash(p)} for p in inputs]}))
    return created
