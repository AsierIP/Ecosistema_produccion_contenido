"""Small, source-bound topic history supplied before invoking a creative worker."""
from pathlib import Path
from .config import read_json
from .cache import file_hash
from .store import Store


def channel_history(root, channel):
    root = Path(root)
    path = root / '.runtime/editorial-history' / (channel['id'] + '.json')
    if not path.exists():
        return None
    history = read_json(path)
    account = channel['platforms']['youtube'].get('channel_id')
    if history.get('channel_id') != channel['id'] or history.get('account_id') != account:
        raise ValueError('Editorial history belongs to another channel')
    evidence = history['source_evidence']
    if file_hash(Path(evidence['path'])) != evidence['sha256']:
        raise ValueError('Observed channel history changed')
    topics = list(history['topics'])
    if any(not isinstance(t, str) or not t.strip() for t in topics):
        raise ValueError('Invalid topic history')
    with Store(root / '.runtime/production.sqlite3') as store:
        for intent in store.list_intents():
            if intent['platform'] != 'youtube' or intent['action'] != 'upload' or intent['state'] != 'verified':
                continue
            if intent['payload'].get('expected_account_id') != account:
                continue
            title = intent['payload'].get('metadata', {}).get('title')
            if title and title not in topics:
                topics.append(title)
    return {**history, 'topics': topics, 'current_upload_intents_included': True}


def creative_context_preflight(packet):
    """Reject incomplete source packs without spending a model attempt."""
    packs = []
    for source in packet['inputs']:
        path = Path(source['path'])
        if path.suffix == '.json' and path.stat().st_size < 100000:
            value = read_json(path)
            if isinstance(value, dict) and value.get('kind') == 'editorial_source_candidates_v1':
                packs.append(value)
    if not packs:
        return None
    if len(packs) != 1:
        raise ValueError('Exactly one editorial source pack is required')
    pack = packs[0]
    history = pack.get('editorial_history')
    if (pack.get('job_id') != packet['job_id'] or pack.get('channel_id') != packet['channel']['id']
            or not pack.get('candidates') or not pack.get('sources')):
        raise ValueError('Incomplete or mismatched editorial source context')
    if (not isinstance(history, dict) or history.get('channel_id') != packet['channel']['id']
            or not isinstance(history.get('topics'), list) or not history.get('scope')):
        raise ValueError('Falta el historial de temas del canal; preparar contexto antes de ejecutar el guionista')
    account = packet['channel']['platforms']['youtube'].get('channel_id')
    if not account or history.get('account_id') != account:
        raise ValueError('Editorial history belongs to another YouTube account')
    if any(not isinstance(topic, str) or not topic.strip() for topic in history['topics']):
        raise ValueError('Invalid topic history')
    evidence = history.get('source_evidence', {})
    if not evidence.get('path') or file_hash(Path(evidence['path'])) != evidence.get('sha256'):
        raise ValueError('Editorial topic history lacks intact observation evidence')
    return 'editorial-context-v1'
