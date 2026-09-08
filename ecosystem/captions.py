"""Literal bottom captions from local ASR evidence; no listening QA claims."""
import math
import re
import subprocess
import wave
from pathlib import Path
from .comic_graphics import Canvas
from .config import read_json, write_json
from .cache import file_hash
from .media import discover


def prepare_captions(request_path, output, *, root):
    request = read_json(Path(request_path))
    profiles = {('comic_captions_v1', 'sabias-que'): 'sq-bottom-electric-v1',
                ('religion_captions_v1', 'religion'): 'early-reels-ivory-gold-v01'}
    profile = profiles.get((request.get('kind'), request.get('channel_id')))
    if not profile:
        raise ValueError('Caption request does not match an approved channel profile')
    source = Path(request['audio_path']).resolve(strict=True)
    if file_hash(source) != request['audio_sha256']:
        raise ValueError('Narration changed before transcription')
    with wave.open(str(source)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / 'captions-result.json'
    binding = {'audio_sha256': file_hash(source), 'transcript': request['transcript'], 'profile': profile}
    if receipt_path.exists():
        previous = read_json(receipt_path)
        if (previous['binding'] != binding or file_hash(Path(previous['path'])) != previous['sha256']
                or file_hash(output / 'asr.json') != previous['asr_sha256']):
            raise ValueError('Saved captions differ from the current narration')
        return previous
    asr_path = output / 'asr.json'
    intent_path = output / 'asr-intent.json'
    if asr_path.exists():
        if read_json(intent_path) != binding:
            raise ValueError('Transcription belongs to another narration')
    else:
        if intent_path.exists():
            raise ValueError('Interrupted transcription requires reconciliation')
        runtime = discover().get('asr_python')
        if not runtime:
            raise ValueError('The existing local ASR runtime is unavailable')
        models = list((Path(runtime).parents[2] / 'asr-models/models--Systran--faster-whisper-large-v3/snapshots').glob('*/model.bin'))
        if len(models) != 1:
            raise ValueError('Exactly one installed ASR model is required; no automatic download')
        write_json(intent_path, binding, exclusive=True)
        with (output / 'asr.log').open('x', encoding='utf-8') as log:
            completed = subprocess.run([runtime, str(Path(root) / 'scripts/transcribe-local.py'),
                '--audio', str(source), '--model', str(models[0].parent), '--output', str(asr_path.resolve())],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=600,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode:
            raise ValueError('Local transcription failed; inspect the saved result')
    builder = build_captions
    if profile == 'early-reels-ivory-gold-v01':
        from .religion_captions import build_religion_captions
        builder = build_religion_captions
    from .caption_alignment import resolve_alignment
    transcript, aligned_words, changes = resolve_alignment(request['transcript'], read_json(asr_path)['words'], request['channel_id'])
    result = builder(transcript, aligned_words, output / 'captions.ass', duration=duration)
    alignment_path = output / 'alignment.json'
    alignment = {'kind': 'caption_alignment_v1', 'channel_id': request['channel_id'],
                 'canonical_transcript': request['transcript'], 'transcript': transcript,
                 'changes': changes, 'audio_sha256': binding['audio_sha256'],
                 'duration_seconds': duration,
                 'asr': {'path': str(asr_path.resolve()), 'sha256': file_hash(asr_path)}}
    write_json(alignment_path, alignment, exclusive=True)
    result.update(transcript=transcript, alignment={'path': str(alignment_path.resolve()), 'sha256': file_hash(alignment_path)})
    result.update(status='TECHNICAL_PASS', binding=binding, sha256=file_hash(Path(result['path'])),
                  asr_sha256=file_hash(asr_path), provider_calls=0, agent_tokens=0, independent_listening='pending')
    write_json(receipt_path, result, exclusive=True)
    return result


def normalize(word):
    return re.sub(r'[^\w]', '', word).casefold()


def spanish_integer(n):
    small = ('cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince '
             'dieciséis diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés veinticuatro '
             'veinticinco veintiséis veintisiete veintiocho veintinueve').split()
    if not 0 <= n <= 9999:
        raise ValueError('Number needs explicit alignment')
    if n < 30:
        return small[n]
    if n < 100:
        tens = {3: 'treinta', 4: 'cuarenta', 5: 'cincuenta', 6: 'sesenta', 7: 'setenta', 8: 'ochenta', 9: 'noventa'}
        return tens[n // 10] + (' y ' + small[n % 10] if n % 10 else '')
    if n == 100:
        return 'cien'
    if n < 1000:
        prefix = {1: 'ciento', 2: 'doscientos', 3: 'trescientos', 4: 'cuatrocientos', 5: 'quinientos',
                  6: 'seiscientos', 7: 'setecientos', 8: 'ochocientos', 9: 'novecientos'}[n // 100]
        return prefix + (' ' + spanish_integer(n % 100) if n % 100 else '')
    return ('mil' if n // 1000 == 1 else small[n // 1000] + ' mil') + (' ' + spanish_integer(n % 1000) if n % 1000 else '')


def align_number_spans(expected, words):
    expanded = []
    for word in words:
        token = word['word'].strip().strip('.,;:!?¿¡')
        if token.isascii() and token.isdigit() and len(token) <= 4 and not any(normalize(w) == token for w in expected):
            spoken = spanish_integer(int(token)).split()
            span = word['end'] - word['start']
            total = sum(map(len, spoken))
            offset = 0
            for part in spoken:
                expanded.append({**word, 'word': part, 'start': word['start'] + span * offset / total,
                                 'end': word['start'] + span * (offset + len(part)) / total,
                                 'timing_note': 'Approximate subdivision of ASR numeric span'})
                offset += len(part)
        else:
            expanded.append(word)
    return expanded


def validated_words(transcript, words, duration):
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Invalid narration duration')
    if any(c in transcript for c in '\\{}\r\n'):
        raise ValueError('Narration contains subtitle control characters')
    expected = transcript.split()
    words = align_number_spans(expected, words)
    if not expected or len(expected) != len(words) or any(normalize(a) != normalize(b['word']) for a, b in zip(expected, words)):
        raise ValueError('ASR differs from canonical narration; align discrepancies before rendering')
    previous = 0.0
    for word in words:
        start, end = word['start'], word['end']
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (start, end))
                or not previous <= start < end <= duration + .05):
            raise ValueError('Invalid or overlapping ASR word timing')
        previous = end
    return expected, words


def build_captions(transcript, words, output, *, duration):
    expected, words = validated_words(transcript, words, duration)
    output = Path(output)
    if output.exists() or output.with_suffix('.json').exists():
        raise ValueError('Existing captions must not be overwritten')
    canvas = Canvas()
    cues = []
    index = 0
    while index < len(expected):
        high = index + 1
        while high < len(expected) and high - index < 5 and len(' '.join(expected[index:high + 1])) <= 28:
            high += 1
        chunk = words[index:high]
        start, end = chunk[0]['start'], min(duration, chunk[-1]['end'])
        text = ''
        for n, word in enumerate(chunk):
            until = chunk[n + 1]['start'] if n + 1 < len(chunk) else end
            text += (' ' if n else '') + r'{\kf' + str(max(1, round((until - word['start']) * 100))) + '}' + expected[index + n]
        canvas.event(start, end, r'{\pos(540,1650)\fs58}' + text, 'Caption', 9)
        cues.append({'start': start, 'end': end, 'text': ' '.join(expected[index:high])})
        index = high
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output)
    write_json(output.with_suffix('.json'), {'cues': cues, 'transcript': transcript,
               'timing_source': 'local_asr', 'number_spans_subdivided': any(w.get('timing_note') for w in words),
               'independent_listening': 'pending'}, exclusive=True)
    return {'path': str(output), 'cue_count': len(cues), 'literal_text_matches': True}
