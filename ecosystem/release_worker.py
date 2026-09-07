"""YouTube browser operations bounded by QA and durable local intents."""
from pathlib import Path
import re
from datetime import datetime, timezone

from .config import read_json, write_json
from .quality import validate_qa
from .release import prepare_youtube_schedule
from .store import Store, QualityError


def enqueue_release_followup(root, step, result, queue):
    """Recover the durable handoff without making another remote request."""
    from .cache import file_hash
    from .dispatch import validate_receipt
    receipt_path = Path(result.get('receipt_path') or result['run']['receipt_path'])
    packet = read_json(receipt_path.parent / 'packet.json')
    receipt = read_json(receipt_path)
    if (packet.get('job_id') != step['job_id'] or packet.get('role') != 'release'
            or packet['channel']['id'] != step['channel_id']
            or receipt.get('decision') != 'ACCEPT' or validate_receipt(receipt, packet)):
        raise QualityError('Release receipt lost integrity during recovery')
    if any(file_hash(Path(ref['path'])) != ref['sha256'] for ref in packet['inputs']):
        raise QualityError('Release input changed after the verified operation')
    request = release_request(packet)
    if request['action'] not in {'upload', 'schedule'}:
        return None
    with Store(root / '.runtime/production.sqlite3') as store:
        job = store.get_job(step['job_id'])
        if not job or job['state'] == 'complete':
            return None
        uploads = [i for i in store.list_intents(step['job_id'])
                   if i['platform'] == 'youtube' and i['action'] == 'upload'
                   and i['state'] == 'verified' and i['master_sha256'] == request['master_sha256']]
        if len(uploads) != 1:
            raise QualityError('Cannot resume without a unique verified private upload')
        upload = uploads[0]
        schedule = prepare_youtube_schedule(store, upload['id'], root=root)
        if request['action'] == 'schedule' and schedule['state'] != 'verified':
            raise QualityError('Remote schedule has not been verified')
    next_action = 'verify_public' if schedule['state'] == 'verified' else 'schedule'
    request.pop('metadata', None)
    value = {**request, 'action': next_action, 'upload_intent_id': upload['id']}
    path = root / '.runtime/upro/results' / step['id'] / (next_action + '-request.json')
    if path.exists():
        if read_json(path) != value:
            raise QualityError('Stored release handoff changed; reconcile before continuing')
    else:
        write_json(path, value, exclusive=True)
    inputs = [path] + [Path(request[k]) for k in ('master_path', 'qa_path', 'metadata_path')]
    plan = {**step['payload'], 'inputs': [{'path': str(p.resolve()), 'sha256': file_hash(p)} for p in inputs],
            'depends_on': [step['id']]}
    if next_action == 'verify_public':
        plan['not_before'] = datetime.fromisoformat(schedule['payload']['publishAt'].replace('Z', '+00:00')).timestamp() + 30
    return queue.register(plan)


def release_request(packet):
    refs = {str(Path(r['path']).resolve()): r for r in packet['inputs']}
    requests = []
    for path in refs:
        p = Path(path)
        if p.suffix == '.json' and p.stat().st_size < 100_000:
            value = read_json(p)
            if isinstance(value, dict) and value.get('kind') == 'youtube_operation_v1':
                requests.append(value)
    if len(requests) != 1:
        raise ValueError('Exactly one YouTube operation request is required')
    request = requests[0]
    channel = packet['channel']
    platform = channel['platforms']['youtube']
    account = platform.get('channel_id', platform.get('account'))
    if (channel['lifecycle'] == 'paused' or platform.get('enabled') is not True
            or not isinstance(account, str) or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', account)
            or request.get('channel_id') != channel['id'] or request.get('expected_account_id') != account
            or request.get('action') not in {'upload', 'schedule', 'verify_public'}):
        raise ValueError('Invalid operation, inactive channel or mismatched YouTube identity')
    policy = packet.get('youtube_release', {})
    if policy.get('upload_visibility') != 'private' or policy.get('publish_delay_seconds') != 7200:
        raise ValueError('Unsupported release policy')
    for key in ('master_path', 'qa_path', 'metadata_path'):
        path = str(Path(request[key]).resolve())
        if path not in refs:
            raise ValueError('Release evidence must be declared in the work order')
    master = Path(request['master_path'])
    if master.suffix.lower() != '.mp4':
        raise ValueError('An MP4 master is required')
    profile = {**packet['profile'], 'voice_speed_factor': channel['voice'].get('speed_factor', 1.0)}
    errors = validate_qa(read_json(Path(request['qa_path'])), master, profile)
    if errors:
        raise QualityError('; '.join(errors))
    metadata = read_json(Path(request['metadata_path']))
    if (metadata.get('kind') == 'publication_metadata_v1'
            and read_json(Path(request['qa_path'])).get('metadata_sha256') != refs[str(Path(request['metadata_path']).resolve())]['sha256']):
        raise QualityError('Independent QA does not bind this publication text')
    if not all(isinstance(metadata.get(k), str) and metadata[k].strip() for k in ('title', 'description')):
        raise ValueError('Approved title and description are required')
    if metadata.get('master_sha256') != refs[str(master.resolve())]['sha256']:
        raise ValueError('Metadata does not belong to this master')
    return {**request, 'master_sha256': metadata['master_sha256'], 'metadata': metadata}


def start_operation(packet, root):
    request = release_request(packet)
    with Store(root / '.runtime/production.sqlite3') as store:
        if request['action'] == 'upload':
            intent = store.prepare_intent(packet['job_id'], 'youtube', 'upload', request['master_sha256'], {
                'expected_account_id': request['expected_account_id'], 'privacyStatus': 'private',
                'master_path': request['master_path'], 'metadata': request['metadata']})
        else:
            upload = store.get_intent(request['upload_intent_id'])
            if not upload or upload['job_id'] != packet['job_id'] or upload['master_sha256'] != request['master_sha256']:
                raise ValueError('Upload belongs to another job or master')
            intent = prepare_youtube_schedule(store, request['upload_intent_id'], root=root)
            if intent['job_id'] != packet['job_id'] or intent['master_sha256'] != request['master_sha256']:
                raise ValueError('Schedule belongs to another job or master')
            if request['action'] == 'verify_public':
                if intent['state'] != 'verified':
                    raise ValueError('Remote scheduling must be verified first')
                target = datetime.fromisoformat(intent['payload']['publishAt'].replace('Z', '+00:00'))
                if datetime.now(timezone.utc) < target:
                    raise ValueError('Public verification is not due yet')
                intent = store.prepare_intent(packet['job_id'], 'youtube', 'publish', request['master_sha256'], {
                    'expected_account_id': request['expected_account_id'],
                    'video_id': intent['payload']['video_id'], 'read_only_verification': True})
        if intent['state'] == 'verified':
            raise ValueError('Operation already verified; reuse it without starting an agent')
        operation = {**intent, 'only_authorized_action': request['action'],
                     'result_path': str(Path(packet['output_directory']) / 'youtube-result.json')}
        write_json(Path(packet['output_directory']) / 'operation.json', operation)
        return store.start_intent(intent['id'], intent['version'])


def finish_operation(packet, root, intent):
    evidence = read_json(Path(packet['output_directory']) / 'youtube-result.json')
    if intent['action'] == 'upload':
        stamp = datetime.fromisoformat(evidence.get('upload_completed_at', '').replace('Z', '+00:00'))
        if (evidence.get('account_id') != intent['payload']['expected_account_id']
                or evidence.get('privacyStatus') != 'private' or evidence.get('upload_complete') is not True
                or evidence.get('never_public') is not True or stamp.tzinfo is None
                or stamp > datetime.now(timezone.utc)
                or not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(evidence.get('video_id', '')))):
            raise QualityError('Private upload receipt lacks exact identity or completion evidence')
    with Store(root / '.runtime/production.sqlite3') as store:
        if intent['action'] == 'publish' and evidence.get('url') != 'https://www.youtube.com/shorts/' + intent['payload']['video_id']:
            raise QualityError('Public verification belongs to another video')
        verified = store.reconcile_intent(intent['id'], intent['version'], 'verified', evidence)
        if intent['action'] == 'upload':
            prepare_youtube_schedule(store, intent['id'], root=root)
        elif intent['action'] == 'publish':
            request = release_request(packet)
            settings = read_json(root / 'config/ecosystem.json')
            platforms = [p for p in settings['active_platforms'] if packet['channel']['platforms'].get(p, {}).get('enabled')]
            receipts = {i['platform']: i['evidence'] for i in store.list_intents(packet['job_id'])
                        if i['action'] == 'publish' and i['state'] == 'verified'}
            if platforms and all(p in receipts for p in platforms):
                accounts = {p: packet['channel']['platforms'][p].get('channel_id', packet['channel']['platforms'][p]['account']) for p in platforms}
                job = store.get_job(packet['job_id'])
                profile = {**packet['profile'], 'voice_speed_factor': packet['channel']['voice'].get('speed_factor', 1.0)}
                store.complete_job(job['id'], job['version'], read_json(Path(request['qa_path'])), receipts,
                                   request['master_path'], accounts, profile, platforms=platforms)
    return verified
