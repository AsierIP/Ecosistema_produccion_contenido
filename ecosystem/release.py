"""Deterministic YouTube schedule calculation; no remote calls or paid services."""
from datetime import datetime, timedelta, timezone
from .config import ROOT, read_json
from .store import ConflictError, IntentUncertainError, QualityError


def youtube_schedule(upload_completed_at, *, root=ROOT, now=None, minute_precision=False):
    policy = read_json(root / 'config/ecosystem.json')['youtube_release']
    if policy['upload_visibility'] != 'private' or policy['delay_anchor'] != 'upload_completed_at':
        raise ValueError('Unsupported YouTube release policy')
    completed = datetime.fromisoformat(upload_completed_at.replace('Z', '+00:00'))
    if completed.tzinfo is None:
        raise ValueError('Upload timestamp requires an explicit timezone')
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError('Current time requires an explicit timezone')
    completed = completed.astimezone(timezone.utc)
    if completed > current:
        raise ValueError('Upload completion cannot be in the future')
    delay = policy['publish_delay_seconds']
    if not isinstance(delay, int) or isinstance(delay, bool) or delay <= 0:
        raise ValueError('Invalid publication delay')
    target = completed + timedelta(seconds=delay)
    if minute_precision and (target.second or target.microsecond):
        target = target.replace(second=0, microsecond=0) + timedelta(minutes=1)
    if target <= current:
        raise ValueError('Schedule has elapsed: reconcile YouTube before any action')
    return {'privacyStatus': 'private', 'publishAt': target.isoformat().replace('+00:00', 'Z')}


def prepare_youtube_schedule(store, upload_intent_id, *, root=ROOT, now=None):
    """Persist a schedule from verified upload evidence, never from a retry clock.

    The browser/API adapter must have verified the completed private upload first.
    This function does not upload, schedule remotely, or assert public visibility.
    """
    upload = store.get_intent(upload_intent_id)
    if not upload or upload['platform'] != 'youtube' or upload['action'] != 'upload':
        raise QualityError('A YouTube upload intent is required')
    if upload['state'] != 'verified':
        raise IntentUncertainError('Reconcile the private upload before scheduling')
    receipt = upload['evidence']
    account = upload['payload'].get('expected_account_id')
    import re
    video = receipt.get('video_id')
    if (not account or receipt.get('account_id') != account
            or receipt.get('master_sha256') != upload['master_sha256']
            or receipt.get('privacyStatus') != 'private'
            or receipt.get('upload_complete') is not True
            or receipt.get('never_public') is not True
            or not isinstance(video, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video)
            or not isinstance(receipt.get('upload_completed_at'), str)):
        raise QualityError('Missing identity, private upload completion or never-public evidence')
    previous = next((i for i in store.list_intents(upload['job_id'])
                     if i['platform'] == 'youtube' and i['action'] == 'schedule'), None)
    if previous:
        payload = previous['payload']
        if (previous['master_sha256'] != upload['master_sha256']
                or payload.get('upload_intent_id') != upload['id']
                or payload.get('video_id') != video
                or payload.get('expected_account_id') != account
                or payload.get('upload_completed_at') != receipt['upload_completed_at']):
            raise ConflictError('Existing schedule belongs to another upload')
        if previous['state'] in {'sending', 'uncertain'}:
            raise IntentUncertainError('Reconcile the remote schedule before repeating')
        if previous['state'] == 'verified':
            return previous
        target = datetime.fromisoformat(payload['publishAt'].replace('Z', '+00:00'))
        if target <= (now or datetime.now(timezone.utc)):
            raise IntentUncertainError('Stored schedule elapsed; reconcile YouTube')
        return previous
    schedule = youtube_schedule(receipt['upload_completed_at'], root=root, now=now, minute_precision=True)
    return store.prepare_intent(upload['job_id'], 'youtube', 'schedule', upload['master_sha256'], {
        **schedule, 'expected_account_id': account, 'video_id': video,
        'upload_intent_id': upload['id'], 'upload_completed_at': receipt['upload_completed_at'],
    })


def validate_schedule_receipt(receipt, intent):
    """Match remote scheduling evidence exactly; scheduled is not public."""
    payload = intent['payload']
    checks = {
        'master_sha256': intent['master_sha256'],
        'account_id': payload.get('expected_account_id'),
        'video_id': payload.get('video_id'),
        'privacyStatus': 'private',
        'publishAt': payload.get('publishAt'),
        'scheduled': True,
    }
    errors = [f'Schedule receipt mismatch: {key}' for key, expected in checks.items()
              if expected is None or receipt.get(key) != expected]
    if not receipt.get('evidence'):
        errors.append('Missing remote scheduling evidence')
    return errors
