"""Bind existing provider audio to its exact narration and channel voice.

Local processing only: never generates a substitute voice or calls a paid API.
The output still requires independent listening and literal-caption review.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import wave

from .cache import file_hash
from .config import load_channels, read_json, write_json
from .media import discover, decode


def prepare_voice(request_path, output, *, root):
    request = read_json(Path(request_path))
    if request.get('kind') != 'voice_from_provider_v1':
        raise ValueError('Unsupported voice request')
    channel = next(c for c in load_channels(root) if c['id'] == request['channel_id'])
    voice = channel['voice']
    if channel['lifecycle'] == 'paused' or voice.get('approved') is not True:
        raise ValueError('Voice is unapproved or channel paused')
    if voice['provider'] != 'Google Gemini TTS':
        raise ValueError('Provider needs its own adapter')
    transcript = request.get('transcript')
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError('Canonical narration is missing')
    closing = channel.get('closing', {})
    if closing.get('required') and not transcript.rstrip().endswith(closing['spoken_text']):
        raise ValueError('Missing approved spoken closing')
    provider_path = Path(request['provider_manifest']).resolve(strict=True)
    if file_hash(provider_path) != request['provider_manifest_sha256']:
        raise ValueError('Provider manifest changed')
    provider = read_json(provider_path)
    comparison = provider.get('comparison', {})
    text_hash = hashlib.sha256(transcript.encode('utf-8')).hexdigest()
    if (provider.get('run_status') != 'complete'
            or provider.get('provider') != 'Google Gemini'
            or comparison.get('language') != voice['locale']
            or comparison.get('transcript') != transcript
            or comparison.get('transcript_sha256') != text_hash):
        raise ValueError('Audio provenance does not match narration, provider or accent')
    samples = [s for s in provider.get('samples', []) if s.get('voice') == voice['id'] and s.get('status') == 'ok']
    if len(samples) != 1:
        raise ValueError('Exactly one matching original voice is required')
    sample = samples[0]
    source = (provider_path.parent / sample['file']).resolve(strict=True)
    if not source.is_relative_to(provider_path.parent) or file_hash(source) != sample['sha256']:
        raise ValueError('Original voice audio changed or escaped its provider directory')
    speed = voice.get('speed_factor', 1.0)
    if (not isinstance(speed, (int, float)) or isinstance(speed, bool)
            or not 0.5 <= speed <= 2.0 or voice.get('pitch_shift', False)
            or (speed != 1 and (voice.get('retiming') is not True or voice.get('retiming_method') != 'atempo'))):
        raise ValueError('Unsupported voice timing policy')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / 'voice-result.json'
    target = output / 'narration.wav'
    binding = {'request_sha256': file_hash(Path(request_path)), 'provider_manifest_sha256': file_hash(provider_path),
               'source_sha256': file_hash(source), 'voice': voice, 'transcript_sha256': text_hash}
    if result_path.exists():
        previous = read_json(result_path)
        if previous.get('binding') != binding or file_hash(target) != previous.get('sha256'):
            raise ValueError('Saved voice differs from its current inputs')
        return previous
    if target.exists() or (output / 'voice-intent.json').exists():
        raise ValueError('Interrupted voice processing requires reconciliation')
    write_json(output / 'voice-intent.json', binding, exclusive=True)
    if speed == 1:
        shutil.copyfile(source, target)
    else:
        ffmpeg = discover().get('ffmpeg')
        if not ffmpeg:
            raise ValueError('FFmpeg is unavailable')
        command = [ffmpeg, '-nostdin', '-n', '-v', 'error', '-i', str(source),
                   '-vn', '-af', f'atempo={speed}', '-c:a', 'pcm_s16le', str(target)]
        run = subprocess.run(command, capture_output=True, timeout=120,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if run.returncode:
            raise ValueError('Voice processing failed')
    with wave.open(str(source)) as original, wave.open(str(target)) as rendered:
        duration = rendered.getnframes() / rendered.getframerate()
        expected = original.getnframes() / original.getframerate() / speed
        if rendered.getnframes() <= 0 or abs(duration - expected) > 0.15:
            raise ValueError('Unexpected narration duration')
    decoded = decode(target, audio_only=True)
    if not decoded['ok']:
        raise ValueError('Narration failed complete technical decoding')
    result = {'status': 'TECHNICAL_PASS', 'binding': binding, 'path': str(target),
              'sha256': file_hash(target), 'duration_seconds': duration, 'decode': decoded,
              'provider_calls': 0, 'agent_tokens': 0, 'independent_listening': 'pending',
              'commercial_review': provider.get('commercial_review', {}), 'published': False}
    write_json(result_path, result, exclusive=True)
    return result
