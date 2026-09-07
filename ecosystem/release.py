"""Deterministic YouTube schedule calculation; no remote calls or paid services."""
from datetime import datetime, timedelta, timezone
from .config import ROOT, read_json


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
