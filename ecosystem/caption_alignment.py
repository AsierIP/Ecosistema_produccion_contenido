"""Narrow Spanish spelling/word variants, retaining original ASR and script."""
import re
from pathlib import Path
from .cache import file_hash
from .config import read_json


def speech_token(word):
    token = re.sub(r'[^\w]', '', word).casefold()
    # A missing silent h in this ASR spelling is not a spoken-word change.
    return {'úsares': 'húsares'}.get(token, token)


def resolve_alignment(transcript, words, channel_id):
    expected = transcript.split()
    aligned = [dict(w) for w in words]
    changes = []
    if channel_id != 'sabias-que' or len(expected) != len(words):
        return transcript, aligned, changes
    for index, (canonical, observed) in enumerate(zip(expected, words)):
        a = re.sub(r'[^\w]', '', canonical).casefold()
        b = re.sub(r'[^\w]', '', observed['word']).casefold()
        if a == b:
            continue
        if a == 'húsares' and b == 'úsares':
            aligned[index]['word'] = canonical
            changes.append({'index': index, 'kind': 'silent_h_spelling',
                            'original_asr': observed['word'], 'caption': canonical})
        elif {a, b} == {'quizá', 'quizás'}:
            # Caption the form actually transcribed; never discard an audible s.
            replacement = b.capitalize() if canonical[0].isupper() else b
            expected[index] = re.sub(r'\w+', replacement, canonical, count=1)
            changes.append({'index': index, 'kind': 'equivalent_spoken_variant',
                            'original_script': canonical, 'caption': expected[index]})
    return ' '.join(expected), aligned, changes


def verified_caption_transcript(captions, canonical, channel_id):
    """Recompute any adaptation from original bound audio/ASR before montage."""
    if not captions.get('alignment'):
        if captions.get('transcript', canonical) != canonical:
            raise ValueError('Caption transcript changed without alignment evidence')
        return canonical
    ref = captions['alignment']
    path = Path(ref['path'])
    if file_hash(path) != ref['sha256']:
        raise ValueError('Caption alignment evidence changed')
    evidence = read_json(path)
    asr = Path(evidence['asr']['path'])
    if (file_hash(asr) != evidence['asr']['sha256']
            or evidence['audio_sha256'] != captions['binding']['audio_sha256']
            or evidence['canonical_transcript'] != canonical
            or evidence['channel_id'] != channel_id):
        raise ValueError('Caption alignment belongs to other inputs')
    transcript, words, changes = resolve_alignment(canonical, read_json(asr)['words'], channel_id)
    if (evidence['transcript'] != transcript or evidence['changes'] != changes
            or captions['transcript'] != transcript):
        raise ValueError('Unsupported caption adaptation')
    from .captions import validated_words
    validated_words(transcript, words, evidence['duration_seconds'])
    return transcript


def recover_saved_alignments(root, queue):
    """Recover only completed local ASR mismatches; never call a provider again."""
    import json
    import time
    from .captions import prepare_captions
    recovered = []
    for step in queue.list():
        if (step['adapter'] != 'captions' or step['state'] != 'uncertain'
                or step['channel_id'] != 'sabias-que'
                or (step.get('result') or {}).get('error') !=
                'ASR differs from canonical narration; align discrepancies before rendering'):
            continue
        output = Path(root) / '.runtime/upro/results' / step['id']
        if not (output / 'asr.json').is_file() or not (output / 'asr-intent.json').is_file():
            continue
        ref = step['payload']['inputs'][0]
        if file_hash(Path(ref['path'])) != ref['sha256']:
            continue
        try:
            result = prepare_captions(Path(ref['path']), output, root=root)
        except (ValueError, KeyError, OSError):
            continue
        if result.get('status') != 'TECHNICAL_PASS':
            continue
        result['reconciliation'] = {'kind': 'completed_local_asr_alignment',
                                    'previous_result': step['result'], 'provider_calls': 0}
        with queue.connect() as con:
            changed = con.execute("UPDATE steps SET state='accepted',result=?,updated=? WHERE id=? AND state='uncertain' AND result=?",
                (json.dumps(result, ensure_ascii=False), time.time(), step['id'],
                 json.dumps(step['result'], ensure_ascii=False))).rowcount
        if changed:
            recovered.append(step['id'])
    return recovered
