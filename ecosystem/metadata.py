"""Assemble publication text locally from the editorial brief and used assets.

This is preparation for independent QA, never publication approval.
"""
from pathlib import Path
import re
from .cache import file_hash
from .config import read_json, write_json

CTA = 'Dale like y suscríbete para saber más cosas.'


def prepare_native_metadata(creative, master_sha256):
    """Identify the biblical adaptation without presenting it as a literal quote."""
    title = creative.get('editorial_title')
    reference = creative.get('scripture_reference')
    source = creative.get('scripture_source')
    if (not isinstance(title,str) or not 1 <= len(title.strip()) <= 100
            or any(c in title for c in '<>\r\n')
            or not isinstance(reference,str) or not reference.strip()
            or not isinstance(source,str) or not source.strip()
            or creative.get('content_classification',{}).get('narration_kind') != 'editorial_adaptation'
            or not re.fullmatch('[0-9a-f]{64}',master_sha256)):
        raise ValueError('Native metadata requires the canonical editorial title and scripture context')
    description = (f'{title}. Reflexión inspirada en {reference} ({source}). '
                   'La narración es una adaptación editorial, no una cita literal del texto bíblico.\n\n'
                   'Suscríbete a Las Palabras de Cristo para descubrir nuevas reflexiones.')
    if len(description) > 5000:
        raise ValueError('Native description exceeds the publication limit')
    return {'kind':'publication_metadata_v1','channel_id':'religion','title':title,
            'description':description,'master_sha256':master_sha256,
            'status':'PREPARED_REQUIRES_INDEPENDENT_QA'}


def prepare_metadata(brief, manifest, master_sha256):
    if brief.get('channel_id') != 'sabias-que':
        raise ValueError('No metadata policy configured for this channel')
    title = brief.get('title', '')
    description = brief.get('description', '')
    if not isinstance(description, str) or not description.strip():
        raise ValueError('Editorial brief lacks a description; do not invent a summary')
    paragraph = re.split(r'\n\s*\n', description.strip())[0].strip()
    paragraph = ' '.join(paragraph.split())
    if (not isinstance(title, str) or not 1 <= len(title.strip()) <= 100
            or any(c in title for c in '<>\r\n') or '#' in paragraph or CTA.casefold() in paragraph.casefold()):
        raise ValueError('Invalid title or summary paragraph')
    if manifest.get('title') != title or manifest.get('caption_transcript') != brief.get('transcript'):
        raise ValueError('Editorial brief does not match the rendered story')
    if not re.fullmatch('[0-9a-f]{64}', master_sha256):
        raise ValueError('Missing master hash')
    credits = []
    for scene in manifest['scenes']:
        resource = scene.get('documentary')
        if not resource:
            continue
        if (resource.get('attribution_required') not in (True, False)
                or not isinstance(resource.get('attribution_required'), bool)
                or not resource.get('license_evidence') or not resource.get('source_url')):
            raise ValueError('Used image lacks an explicit attribution decision and license evidence')
        if resource['attribution_required']:
            fields = ('author', 'source_url', 'license_name', 'changes')
            if any(not isinstance(resource.get(k), str) or not resource[k].strip() for k in fields):
                raise ValueError('Required image credit is incomplete')
            credit = ' · '.join(resource[k].strip() for k in fields)
            if credit not in credits:
                credits.append(credit)
    text = '\n\n'.join([paragraph, CTA] + credits)
    if len(text) > 5000:
        raise ValueError('Description exceeds the publication field limit')
    return {'kind': 'publication_metadata_v1', 'channel_id': brief['channel_id'],
            'title': title, 'description': text, 'master_sha256': master_sha256,
            'status': 'PREPARED_REQUIRES_INDEPENDENT_QA'}


def advance_metadata(root, queue):
    """Persist once after rendering; revalidate bindings on restart without a model."""
    root = Path(root)
    created = []
    for step in queue.list():
        if step['channel_id'] != 'sabias-que' or step['adapter'] != 'cutout' or step['state'] != 'accepted':
            continue
        folder = root / '.runtime/jobs' / step['job_id'] / 'handoffs' / step['id']
        error = folder.parent / ('error-metadata-' + step['id'] + '.json')
        try:
            refs = step['payload']['inputs']
            # New automated assemblies declare the brief alongside the manifest.
            briefs = [r for r in refs if Path(r['path']).name == 'production-brief.json']
            if len(briefs) != 1:
                continue  # Older manual canaries need explicit migration.
            manifests = [r for r in refs if Path(r['path']).name == 'master-manifest.json']
            if len(manifests) != 1:
                raise ValueError('Missing unique master manifest')
            for ref in [briefs[0], manifests[0]]:
                if file_hash(Path(ref['path'])) != ref['sha256']:
                    raise ValueError('Metadata input changed after assembly')
            result = step['result']
            manifest = read_json(Path(manifests[0]['path']))
            if (result.get('status') != 'TECHNICAL_PASS'
                    or Path(result['output_path']).resolve() != Path(manifest['output']).resolve()
                    or file_hash(Path(result['output_path'])) != result['sha256']):
                raise ValueError('Master changed after rendering')
            value = prepare_metadata(read_json(Path(briefs[0]['path'])), manifest, result['sha256'])
            output = folder / 'metadata.json'
            if output.exists():
                if read_json(output) != value:
                    raise ValueError('Prepared metadata changed; preserve the previous version')
            else:
                write_json(output, value, exclusive=True)
                created.append(str(output))
            if error.exists() and read_json(error).get('status') != 'resolved':
                write_json(error, {'status': 'resolved'})
        except (ValueError, KeyError, OSError, TypeError) as exc:
            problem = {'status': 'blocked', 'reason': str(exc)}
            if not error.exists() or read_json(error) != problem:
                write_json(error, problem)
    return created
