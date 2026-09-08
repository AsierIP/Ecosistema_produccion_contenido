"""One bounded natural retake when narration exceeds the accepted timeline."""
from pathlib import Path
import wave

from .cache import file_hash
from .config import read_json, write_json
from .native_batch import immutable, ref


def selected_voice(voices):
    if not voices:
        return None
    if len(voices) > 2:
        raise ValueError('Natural narration retake limit exceeded')
    requests = {}
    for step in voices:
        source = step['payload']['inputs'][0]
        if file_hash(Path(source['path'])) != source['sha256']:
            raise ValueError('Narration request changed')
        requests[step['id']] = read_json(Path(source['path']))
    originals = [s for s in voices if not requests[s['id']].get('supersedes_voice_step')]
    if len(originals) != 1:
        raise ValueError('Ambiguous original narration')
    original = originals[0]
    if len(voices) == 1:
        return original
    replacement = next(s for s in voices if s['id'] != original['id'])
    new, old = requests[replacement['id']], requests[original['id']]
    if (original['state'] != 'accepted' or new.get('supersedes_voice_step') != original['id']
            or any(new.get(k) != old.get(k) for k in ('transcript', 'channel_id', 'native_sequence', 'creative'))):
        raise ValueError('Retake must preserve the accepted narration text and storyboard')
    return replacement


def advance_narration_fit(root, queue, *, only_job):
    steps = [s for s in queue.list() if s['job_id'] == only_job]
    voices = [s for s in steps if s['adapter'] == 'voice_generate']
    voice = selected_voice(voices)
    visuals = [s for s in steps if s['adapter'] == 'native_visual' and s['state'] == 'accepted']
    if not voice or voice['state'] != 'accepted' or not visuals:
        return
    if len(visuals) != 1:
        raise ValueError('Ambiguous visual timeline')
    visual = visuals[0]['result']
    if (visual.get('status') != 'TECHNICAL_PASS' or visual.get('frames') != 750
            or visual.get('fps') != 24 or file_hash(Path(visual['path'])) != visual.get('sha256')):
        raise ValueError('Native narration needs the intact accepted timeline')
    audio = voice['result']
    if file_hash(Path(audio['path'])) != audio['sha256']:
        raise ValueError('Narration audio changed')
    with wave.open(audio['path']) as stream:
        duration = stream.getnframes() / stream.getframerate()
    # The native profile is exactly 750 frames at 24 fps.
    target = 750 / 24
    if duration <= target:
        error = Path(root) / '.runtime/jobs' / only_job / 'handoffs/error-narration-fit.json'
        if error.exists() and read_json(error).get('status') != 'resolved':
            write_json(error, {'status': 'resolved', 'job_id': only_job,
                'voice_step': voice['id'], 'duration_seconds': duration,
                'audio_sha256': audio['sha256']})
        return
    if len(voices) == 2:
        raise ValueError('Natural retake still exceeds timeline; preserve both takes for reconciliation')
    source = read_json(Path(voice['payload']['inputs'][0]['path']))
    request = immutable(Path(root) / '.runtime/jobs' / only_job / 'native-voice-retake/request.json',
        {**source, 'target_duration_seconds': target - 0.5, 'supersedes_voice_step': voice['id']})
    return queue.register({'schema_version': 1, 'channel_id': voice['channel_id'], 'job_id': only_job,
        'adapter': 'voice_generate', 'mode': voice['mode'],
        'depends_on': [voice['id'], visuals[0]['id']], 'inputs': [ref(request)]})
