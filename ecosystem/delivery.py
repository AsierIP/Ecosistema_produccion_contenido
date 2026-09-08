"""Resume delivery after independent QA; never infer approval from a render."""
from pathlib import Path
from .cache import file_hash
from .config import read_json, write_json
from .dispatch import validate_receipt
from .quality import validate_qa


def reviewed_master(inputs, qa):
    matches = [r for r in inputs if Path(r['path']).suffix.lower() == '.mp4'
               and r['sha256'] == qa.get('master_sha256')]
    if len(matches) != 1:
        raise ValueError('Independent QA must identify exactly one declared master')
    return matches[0]


def advance_delivery(root, queue):
    root = Path(root)
    steps = queue.list()
    created = []
    for step in steps:
        if step['adapter'] != 'quality' or step['state'] != 'accepted':
            continue
        if any(s['adapter'] == 'release' and step['id'] in s['payload'].get('depends_on', []) for s in steps):
            continue
        error = root / '.runtime/jobs' / step['job_id'] / 'handoffs' / ('error-delivery-' + step['id'] + '.json')
        try:
            result = step['result']
            receipt_path = Path(result.get('receipt_path') or result['run']['receipt_path'])
            packet = read_json(receipt_path.parent / 'packet.json')
            receipt = read_json(receipt_path)
            if (packet.get('job_id') != step['job_id'] or packet.get('role') != 'quality'
                    or packet['channel']['id'] != step['channel_id']
                    or receipt.get('decision') != 'ACCEPT' or validate_receipt(receipt, packet)):
                raise ValueError('Independent review receipt lost integrity')
            metadata = [r for r in packet['inputs'] if Path(r['path']).name == 'metadata.json']
            reports = [a for a in receipt['artifacts'] if Path(a['path']).name == 'qa.json']
            if len(metadata) != 1 or len(reports) != 1:
                raise ValueError('Independent review needs one master, metadata and qa.json')
            qa = read_json(Path(reports[0]['path']))
            masters = [reviewed_master(packet['inputs'],qa)]
            reviewed = {str(Path(r['path']).resolve()): r['sha256'] for r in receipt['inputs_reviewed']}
            for ref in [masters[0], metadata[0]]:
                if (reviewed.get(str(Path(ref['path']).resolve())) != ref['sha256']
                        or file_hash(Path(ref['path'])) != ref['sha256']):
                    raise ValueError('Master or publication text was not reviewed or has changed')
            channel = packet['channel']
            profile = {**packet['profile'], 'voice_speed_factor': channel['voice'].get('speed_factor', 1.0)}
            issues = validate_qa(qa, masters[0]['path'], profile)
            if issues:
                raise ValueError('; '.join(issues))
            if qa.get('metadata_sha256') != metadata[0]['sha256']:
                raise ValueError('Independent QA does not bind the publication text')
            platform = channel['platforms']['youtube']
            if platform.get('enabled') is not True:
                continue
            request = {'kind': 'youtube_operation_v1', 'action': 'upload', 'channel_id': channel['id'],
                       'expected_account_id': platform.get('channel_id', platform.get('account')),
                       'master_path': masters[0]['path'], 'qa_path': reports[0]['path'],
                       'metadata_path': metadata[0]['path']}
            path = error.parent / step['id'] / 'upload-request.json'
            if path.exists():
                if read_json(path) != request:
                    raise ValueError('Upload request changed; preserve the existing operation')
            else:
                write_json(path, request, exclusive=True)
            inputs = [path] + [Path(request[k]) for k in ('master_path', 'qa_path', 'metadata_path')]
            created.append(queue.register({'schema_version': 1, 'job_id': step['job_id'],
                'channel_id': step['channel_id'], 'adapter': 'release', 'mode': step['mode'],
                'depends_on': [step['id']],
                'inputs': [{'path': str(p.resolve()), 'sha256': file_hash(p)} for p in inputs]}))
            if error.exists() and read_json(error).get('status') != 'resolved':
                write_json(error, {'status': 'resolved'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            problem = {'status': 'blocked', 'reason': str(exc)}
            if not error.exists() or read_json(error) != problem:
                write_json(error, problem)
    return created
