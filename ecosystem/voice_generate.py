"""One durable Google narration request, with no retry or provider substitution."""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import subprocess
import wave

from .cache import file_hash
from .config import load_channels, read_json, write_json
from .voice import prepare_voice
from .media import decode


def reconcile_saved_audio(request_path, output, *, root):
    """Recover the observed post-response hashing failure without another API call.

    This is technical recovery only; it does not supply listening or rights QA.
    Other failures and ambiguous/multiple outputs remain blocked.
    """
    output = Path(output)
    request = read_json(Path(request_path))
    channel = next(c for c in load_channels(root) if c['id'] == request['channel_id'])
    config = generation_config(request, channel)
    intent = read_json(output / 'generation-intent.json')
    if intent['request_sha256'] != file_hash(Path(request_path)) or intent['voice'] != channel['voice']:
        raise ValueError('Recovery inputs changed')
    if read_json(output / 'provider-config.json') != config:
        raise ValueError('Provider configuration changed')
    manifests = list((output / 'provider').glob('*/manifest.json'))
    if len(manifests) != 1:
        raise ValueError('Recovery requires one provider manifest')
    manifest_path = manifests[0]
    manifest = read_json(manifest_path)
    if (manifest.get('run_status') != 'failed' or manifest.get('samples')
            or 'Get-FileHash' not in manifest.get('failure', {}).get('message', '')
            or manifest.get('comparison', {}).get('transcript') != config['transcript']):
        raise ValueError('Failure is not the verified post-response hashing error')
    source = manifest_path.parent / 'original.wav'
    checked = decode(source, audio_only=True)
    if not checked['ok']:
        raise ValueError('Saved provider audio is incomplete')
    with wave.open(str(source)) as audio:
        duration = audio.getnframes() / audio.getframerate()
        if duration <= 0:
            raise ValueError('Saved audio is empty')
    archive = manifest_path.with_name('failed-manifest.json')
    write_json(archive, manifest, exclusive=True)
    manifest['run_status'] = 'complete'
    manifest['recovery'] = {'kind': 'post_response_local_hash_failure', 'provider_calls_during_recovery': 0,
                            'original_manifest_sha256': file_hash(archive), 'decode': checked}
    manifest['samples'] = [{'voice': channel['voice']['id'], 'status': 'ok', 'file': 'original.wav',
                            'sha256': file_hash(source), 'bytes': source.stat().st_size, 'duration_seconds': duration}]
    write_json(manifest_path, manifest)
    voice_request = output / 'voice-request.json'
    write_json(voice_request, {'kind': 'voice_from_provider_v1', 'channel_id': channel['id'],
                              'transcript': config['transcript'], 'provider_manifest': str(manifest_path.resolve()),
                              'provider_manifest_sha256': file_hash(manifest_path)})
    result = prepare_voice(voice_request, output / 'processed', root=root)
    binding = {**intent}
    for key in ('state', 'budget_evidence', 'created_at'):
        binding.pop(key, None)
    binding['script_sha256'] = file_hash(root / 'scripts/providers/generate-google-voice.ps1')
    result = {**result, 'binding': binding, 'provider_calls': 0, 'recovered_existing_generation': True}
    write_json(output / 'generation-result.json', result, exclusive=True)
    return result


def generation_config(request, channel):
    voice = channel['voice']
    text = request.get('transcript')
    if (request.get('kind') != 'voice_generation_v1' or request.get('channel_id') != channel['id']
            or channel['lifecycle'] == 'paused' or voice.get('approved') is not True
            or voice['provider'] != 'Google Gemini TTS'
            or not isinstance(text, str) or not 1 <= len(text.strip()) <= 6000):
        raise ValueError('Invalid narration request or unapproved voice')
    closing = channel.get('closing', {})
    if closing.get('required') and not text.rstrip().endswith(closing['spoken_text']):
        raise ValueError('Missing required spoken closing')
    # Delivery comes from the approved channel, never from arbitrary request code.
    direction = (voice.get('delivery', '') + f" Idioma regional {voice['locale']}. "
                 'Ritmo natural. No añadas, repitas, cambies ni omitas palabras. Lee exactamente: ' + text)
    return {'schema_version': 1, 'language': voice['locale'], 'transcript': text, 'direction': direction,
            'google_gemini': {'endpoint': 'https://generativelanguage.googleapis.com/v1beta/interactions',
                             'api_revision': '2026-05-20', 'model': 'gemini-3.1-flash-tts-preview',
                             'provider': 'Google Gemini', 'api': 'Interactions', 'model_lifecycle': 'preview',
                             'sample_rate': 24000, 'channels': 1, 'bits_per_sample': 16,
                             'voices': [{'id': voice['id'], 'order': 1, 'file': 'original.wav',
                                         'descriptor': voice['id'] + ' ' + voice['locale']}]}}


def free_tier_preflight(root, now=None):
    """Account/credential binding must be evidenced; a price table is insufficient."""
    proof = read_json(root / '.runtime/providers/google-tts-free-tier.json')
    current = now or datetime.now(timezone.utc)
    checked = datetime.fromisoformat(proof['checked_at'].replace('Z', '+00:00'))
    if (checked.tzinfo is None or not 0 <= (current - checked).total_seconds() <= 86400
            or proof.get('billing_enabled') is not False
            or proof.get('credential_project_verified') is not True
            or proof.get('model') != 'gemini-3.1-flash-tts-preview' or not proof.get('evidence')):
        raise ValueError('A current free-tier check bound to the configured credential is required')
    secret_record = Path(proof['credential_record_path'])
    expected_record = Path(os.environ['LOCALAPPDATA']) / 'LUMEN/secrets/gemini-api-key.v1.dpapi.json'
    if secret_record.resolve() != expected_record.resolve():
        raise ValueError('Budget evidence is for another credential store')
    if file_hash(secret_record) != proof.get('credential_record_sha256'):
        raise ValueError('Configured credential changed after free-tier verification')
    return proof


def generate_voice(request_path, output, *, root, validate_only=False):
    root, output = Path(root), Path(output)
    request = read_json(Path(request_path))
    channel = next(c for c in load_channels(root) if c['id'] == request['channel_id'])
    config = generation_config(request, channel)
    script = root / 'scripts/providers/generate-google-voice.ps1'
    binding = {'request_sha256': file_hash(Path(request_path)), 'voice': channel['voice'],
               'transcript_sha256': hashlib.sha256(config['transcript'].encode()).hexdigest(),
               'script_sha256': file_hash(script)}
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output / 'generation-result.json'
    if receipt_path.exists():
        receipt = read_json(receipt_path)
        if receipt.get('binding') != binding:
            raise ValueError('Previous narration belongs to different inputs')
        prepare_voice(output / 'voice-request.json', output / 'processed', root=root)
        return {**receipt, 'provider_calls': 0, 'cache_hit': True}
    config_path = output / 'provider-config.json'
    intent_path = output / 'generation-intent.json'
    if intent_path.exists() and not validate_only:
        raise ValueError('Prior generation must be reconciled; never send it again')
    write_json(config_path, config)
    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script.resolve()),
               '-ConfigPath', str(config_path.resolve()), '-OutputRoot', str((output / 'provider').resolve()),
               '-MaxAttempts', '1', '-TimeoutSeconds', '180']
    if validate_only:
        command.append('-ValidateOnly')
    else:
        proof = free_tier_preflight(root)
        write_json(intent_path, {**binding, 'state': 'sending', 'budget_evidence': proof,
                                 'created_at': datetime.now(timezone.utc).isoformat()}, exclusive=True)
    with (output / ('validation.log' if validate_only else 'provider.log')).open('w', encoding='utf-8') as log:
        run = subprocess.run(command, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                             timeout=240, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if run.returncode:
        raise ValueError('Provider failed; inspect evidence before any further attempt')
    if validate_only:
        return {'status': 'CONFIG_VALIDATED', 'provider_calls': 0, 'credentials_read': False}
    manifests = list((output / 'provider').glob('*/manifest.json'))
    if len(manifests) != 1:
        raise ValueError('A single provider result is required')
    manifest = manifests[0]
    voice_request = output / 'voice-request.json'
    write_json(voice_request, {'kind': 'voice_from_provider_v1', 'channel_id': channel['id'],
                              'transcript': config['transcript'], 'provider_manifest': str(manifest.resolve()),
                              'provider_manifest_sha256': file_hash(manifest)})
    result = prepare_voice(voice_request, output / 'processed', root=root)
    result = {**result, 'provider_calls': 1, 'binding': binding}
    write_json(receipt_path, result, exclusive=True)
    return result
