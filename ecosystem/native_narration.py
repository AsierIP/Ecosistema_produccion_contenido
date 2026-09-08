"""One bounded natural retake when narration exceeds the accepted timeline."""
from pathlib import Path
import wave
import array
import sys

from .cache import file_hash
from .config import read_json, write_json
from .native_batch import immutable, ref


def trim_verified_silent_tail(source, output, *, target, words, transcript):
    """Keep every original PCM sample up to target; trim only proven silent tail."""
    from .captions import validated_words
    source, output = Path(source), Path(output)
    with wave.open(str(source)) as stream:
        params = stream.getparams()
        duration = params.nframes / params.framerate
        if params.sampwidth != 2 or params.comptype != 'NONE':
            raise ValueError('Silent-tail fitting requires PCM16')
        _, aligned = validated_words(transcript, words, duration)
        if not 0 < duration - target <= 0.5 or aligned[-1]['end'] + 0.12 > target:
            raise ValueError('Narration does not leave a safe silent tail')
        cut = round(target * params.framerate)
        pcm = stream.readframes(params.nframes)
    prefix = pcm[:cut * params.nchannels * 2]
    samples = array.array('h', pcm[len(prefix):])
    if sys.byteorder != 'little':
        samples.byteswap()
    peak = max(map(abs, samples), default=32768)
    if peak > 32:
        raise ValueError('Tail contains audible signal; do not cut it')
    if output.exists():
        with wave.open(str(output)) as saved:
            if (saved.getparams() != params._replace(nframes=cut)
                    or saved.readframes(cut) != prefix):
                raise ValueError('Existing fitted narration changed')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as handle:
            with wave.open(handle, 'wb') as saved:
                saved.setparams(params._replace(nframes=cut))
                saved.writeframes(prefix)
    return {**ref(output), 'duration_seconds': cut / params.framerate,
        'source': ref(source), 'last_word_end': aligned[-1]['end'],
        'removed_seconds': duration - target, 'removed_peak_pcm16': peak,
        'retiming': False, 'retained_pcm_identical': True}


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
        captions = [s for s in steps if s['adapter'] == 'captions'
                    and voice['id'] in s['payload'].get('depends_on', [])]
        if not captions or any(s['state'] in ('queued', 'running') for s in captions):
            return  # Obtain literal word timings before diagnosing a short tail overrun.
        if len(captions) == 1 and captions[0]['state'] == 'accepted':
            cap = captions[0]['result']
            asr = Path(cap['path']).parent / 'asr.json'
            if (cap['binding']['audio_sha256'] != audio['sha256']
                    or file_hash(asr) != cap['asr_sha256']):
                raise ValueError('Retake alignment evidence changed')
            fitted = trim_verified_silent_tail(audio['path'],
                Path(root) / '.runtime/jobs' / only_job / 'native-audio-fit/narration.wav',
                target=target, words=read_json(asr)['words'], transcript=cap['binding']['transcript'])
            immutable(Path(root) / '.runtime/jobs' / only_job / 'native-audio-fit/result.json',
                {**fitted, 'voice_step': voice['id'], 'captions_step': captions[0]['id'],
                 'asr': ref(asr), 'status': 'TECHNICAL_PASS'})
            error = Path(root) / '.runtime/jobs' / only_job / 'handoffs/error-narration-fit.json'
            resolved = {'status': 'resolved', 'job_id': only_job, 'voice_step': voice['id'],
                        'fitted_audio_sha256': fitted['sha256']}
            if not error.exists() or read_json(error) != resolved:
                write_json(error, resolved)
            return
        raise ValueError('Natural retake still exceeds timeline; preserve both takes for reconciliation')
    source = read_json(Path(voice['payload']['inputs'][0]['path']))
    request = immutable(Path(root) / '.runtime/jobs' / only_job / 'native-voice-retake/request.json',
        {**source, 'target_duration_seconds': target - 0.5, 'supersedes_voice_step': voice['id']})
    return queue.register({'schema_version': 1, 'channel_id': voice['channel_id'], 'job_id': only_job,
        'adapter': 'voice_generate', 'mode': voice['mode'],
        'depends_on': [voice['id'], visuals[0]['id']], 'inputs': [ref(request)]})
