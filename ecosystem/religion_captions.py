"""Canonical ivory/gold captions using shared literal ASR alignment."""
from pathlib import Path
from .captions import validated_words
from .comic_graphics import timestamp
from .config import write_json
from .config import read_json
from .cache import file_hash
from .native_batch import ref, immutable

PROFILE = 'early-reels-ivory-gold-v01'
# Extracted from the historical approved visual profile and caption builder.
HEADER = '''[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: SubtitleGlow,Segoe UI Semibold,39,&H404EA8D5,&H404EA8D5,&H304EA8D5,&HFF000000,-1,0,0,0,100,100,0.1,0,1,7.2,0.0,2,54,54,336,1
Style: Subtitle,Segoe UI Semibold,39,&H00E8F7FF,&H00E8F7FF,&H00100E0C,&H78000000,-1,0,0,0,100,100,0.1,0,1,3.0,1.4,2,54,54,336,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''


def build_religion_captions(transcript, words, output, *, duration):
    expected, words = validated_words(transcript, words, duration)
    output = Path(output)
    if output.exists() or output.with_suffix('.json').exists():
        raise ValueError('Existing captions must not be overwritten')
    rows, cues, index = [], [], 0
    while index < len(expected):
        end = index + 1
        while end < len(expected) and end - index < 6 and len(' '.join(expected[index:end + 1])) <= 32:
            end += 1
        text = ' '.join(expected[index:end])
        if len(text) > 32:
            raise ValueError('A caption word needs an explicit readable line plan')
        start_time, end_time = words[index]['start'], min(duration, words[end - 1]['end'])
        cues.append({'start': start_time, 'end': end_time, 'text': text})
        fade_out = 140 if end == len(expected) else 90
        for layer, style in ((0, 'SubtitleGlow'), (1, 'Subtitle')):
            rows.append(f'Dialogue: {layer},{timestamp(start_time)},{timestamp(end_time)},{style},,0,0,0,,{{\\an2\\pos(360,944)\\fad(70,{fade_out})}}{text}')
        index = end
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(HEADER + '\n'.join(rows) + '\n', encoding='utf-8-sig')
    write_json(output.with_suffix('.json'), {'cues': cues, 'transcript': transcript,
               'profile': PROFILE, 'timing_source': 'local_asr', 'independent_listening': 'pending',
               'rendered_rgb_review': 'pending'}, exclusive=True)
    return {'path': str(output), 'cue_count': len(cues), 'literal_text_matches': True, 'caption_profile': PROFILE}


def advance_native_captions(root, queue, *, only_job):
    root = Path(root)
    steps = [s for s in queue.list() if s['job_id'] == only_job and s['channel_id'] == 'religion']
    voices = [s for s in steps if s['adapter'] == 'voice_generate' and s['state'] == 'accepted']
    if not voices:
        return
    if len(voices) != 1:
        raise ValueError('Multiple accepted narrations require reconciliation')
    voice = voices[0]
    source_ref = voice['payload']['inputs'][0]
    if file_hash(Path(source_ref['path'])) != source_ref['sha256']:
        raise ValueError('Narration request changed before caption handoff')
    source = read_json(Path(source_ref['path']))
    if not source.get('native_sequence') or not source.get('creative'):
        raise ValueError('Religion captions require the bound native storyboard')
    creative_ref = source['creative']
    if file_hash(Path(creative_ref['path'])) != creative_ref['sha256']:
        raise ValueError('Narration storyboard changed')
    creative = read_json(Path(creative_ref['path']))
    if (creative['sequence_id'] != source['native_sequence']
            or creative['canonical_narration_text'] != source['transcript']):
        raise ValueError('Captions must use the exact native canonical narration')
    audio = voice['result']
    if audio.get('status') != 'TECHNICAL_PASS' or file_hash(Path(audio['path'])) != audio.get('sha256'):
        raise ValueError('Validated narration changed before captions')
    existing = [s for s in steps if s['adapter'] == 'captions' and voice['id'] in s['payload'].get('depends_on', [])]
    if existing:
        return
    request = immutable(root / '.runtime/jobs' / only_job / 'native-captions/request.json',
        {'kind': 'religion_captions_v1', 'channel_id': 'religion', 'transcript': source['transcript'],
         'audio_path': audio['path'], 'audio_sha256': audio['sha256']})
    return queue.register({'schema_version': 1, 'channel_id': 'religion', 'job_id': only_job,
        'adapter': 'captions', 'mode': voice['mode'], 'depends_on': [voice['id']], 'inputs': [ref(request)]})
