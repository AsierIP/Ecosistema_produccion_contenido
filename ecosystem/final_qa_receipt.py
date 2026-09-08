"""Seal a completed independent QA report; never infer missing QA decisions."""
import json
from pathlib import Path
from .cache import file_hash
from .config import read_json, write_json
from .quality import REQUIRED_CHECKS, validate_qa


def seal_completed_native_report(packet):
    if packet.get('role') != 'quality' or packet['channel']['id'] != 'religion':
        raise ValueError('Only final native QA reports support this recovery')
    folder = Path(packet['output_directory'])
    path = folder / 'qa.json'
    if (folder / 'receipt.json').exists():
        raise ValueError('Existing receipt must be reconciled without overwriting it')
    original = folder / 'qa-original.json'
    source = original if original.exists() else path
    original_bytes = source.read_bytes()
    report = read_json(source)
    if (report.get('kind') != 'final_master_qa_v1' or report.get('decision') != 'ACCEPT'
            or report.get('job_id') != packet['job_id'] or report.get('channel_id') != packet['channel']['id']
            or report.get('defects') != [] or report.get('human_review') is not False
            or report.get('review_method') != 'automated-audiovisual-review'):
        raise ValueError('No completed independent acceptance to recover')
    original_hash = file_hash(source)
    events = [json.loads(line) for line in (folder / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    authored = any(e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'file_change'
        and e['item'].get('status') == 'completed'
        and any(Path(c['path']).resolve() == path.resolve() for c in e['item'].get('changes', [])) for e in events)
    hash_checked = any(e.get('type') == 'item.completed' and e.get('item', {}).get('type') == 'command_execution'
        and e['item'].get('exit_code') == 0 and original_hash in e['item'].get('aggregated_output', '') for e in events)
    if not authored or not hash_checked:
        raise ValueError('Independent report completion is not evidenced by worker events')
    refs = packet['inputs']
    for ref in refs:
        if file_hash(Path(ref['path'])) != ref['sha256']:
            raise ValueError('QA input changed before receipt recovery')
    masters = [r for r in refs if Path(r['path']).suffix.lower() == '.mp4' and r['sha256'] == report['master_sha256']]
    metadata = [r for r in refs if Path(r['path']).name == 'metadata.json' and r['sha256'] == report['metadata_sha256']]
    timelines = []
    for ref in refs:
        p = Path(ref['path'])
        if p.suffix == '.json' and p.stat().st_size < 100_000:
            value = read_json(p)
            if isinstance(value, dict) and value.get('kind') == 'native_master_timeline_evidence_v1':
                timelines.append((ref, value))
    if len(masters) != 1 or len(metadata) != 1 or len(timelines) != 1:
        raise ValueError('Final QA needs unique bound master, metadata and timeline')
    timeline_ref, evidence = timelines[0]
    if evidence['master']['sha256'] != report['master_sha256']:
        raise ValueError('Timeline belongs to another master')
    timeline = evidence['timeline']
    summary = report['timeline']
    if isinstance(summary.get('segments'), int):
        segments = timeline['segments']
        if (summary['segments'] != len(segments)
                or summary.get('total_output_frames') != sum(s['output_frames'] for s in segments)
                or summary.get('output_fps') != packet['profile']['output_fps']
                or summary.get('mode') != timeline['mode']
                or summary.get('voice_speed_factor') != timeline['voice_speed_factor']
                or summary.get('interpolated_across_cuts') != timeline['interpolated_across_cuts']
                or any(summary.get('input_frames_per_segment') != s['input_frames']
                       or summary.get('output_frames_per_segment') != s['output_frames'] for s in segments)):
            raise ValueError('Independent timeline summary contradicts its detailed evidence')
        report = {**report, 'timeline_summary': summary, 'timeline': timeline}
    checks = report.get('checks')
    if isinstance(checks, list):
        if len(checks) != len(REQUIRED_CHECKS) or {c.get('name') for c in checks} != set(REQUIRED_CHECKS):
            raise ValueError('Missing or duplicated independent QA check')
        report = {**report, 'checks': {c['name']: c for c in checks}}
    errors = validate_qa(report, masters[0]['path'], packet['profile'])
    if errors:
        raise ValueError('; '.join(errors))
    report['format_normalization'] = {'original_report_sha256': original_hash,
        'timeline_evidence_sha256': timeline_ref['sha256'],
        'judgment_changed': False, 'provider_calls': 0}
    if original.exists():
        if read_json(path) not in (read_json(original), report):
            raise ValueError('Interrupted QA normalization contains unexpected changes')
    else:
        with original.open('xb') as stream:
            stream.write(original_bytes)
    write_json(path, report)
    def ref(p):
        return {'path': str(p.resolve()), 'sha256': file_hash(p), 'bytes': p.stat().st_size}
    receipt = {'job_id': packet['job_id'], 'role': 'quality', 'decision': 'ACCEPT',
        'artifacts': [ref(path), ref(original)],
        'checks': [{'name': name, 'passed': True, 'evidence': report['checks'][name]['evidence']} for name in REQUIRED_CHECKS],
        'blockers': [], 'inputs_reviewed': [masters[0], metadata[0], timeline_ref]}
    from .dispatch import validate_receipt
    if validate_receipt(receipt, packet):
        raise ValueError('Recovered final receipt is invalid')
    write_json(folder / 'receipt.json', receipt, exclusive=True)
    return receipt
