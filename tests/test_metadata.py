import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from ecosystem.cache import file_hash
from ecosystem.config import read_json, write_json
from ecosystem.metadata import CTA, prepare_metadata, advance_metadata


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.brief = {'channel_id': 'sabias-que', 'title': 'El verano perdido',
                      'transcript': 'Narración de prueba.',
                      'description': 'Un volcán cambió el verano.\n\nTexto que no debe publicarse.'}
        self.manifest = {'title': self.brief['title'], 'caption_transcript': self.brief['transcript'], 'scenes': []}

    def test_first_paragraph_and_exact_single_cta(self):
        value = prepare_metadata(self.brief, self.manifest, 'a' * 64)
        self.assertEqual(value['description'], 'Un volcán cambió el verano.\n\n' + CTA)
        self.assertEqual(value['status'], 'PREPARED_REQUIRES_INDEPENDENT_QA')

    def test_required_credits_survive_brevity_rule(self):
        resource = {'attribution_required': True, 'license_evidence': 'license.txt',
                    'author': 'Autora de prueba', 'source_url': 'https://example.com/photo',
                    'license_name': 'CC BY 4.0', 'changes': 'Contraste y encuadre ajustados'}
        self.manifest['scenes'] = [{'documentary': resource}] * 2
        value = prepare_metadata(self.brief, self.manifest, 'a' * 64)
        self.assertEqual(value['description'].count('Autora de prueba'), 1)
        del resource['author']
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            prepare_metadata(self.brief, self.manifest, 'a' * 64)

    def test_unknown_license_decision_and_wrong_story_fail(self):
        self.manifest['scenes'] = [{'documentary': {'source_url': 'https://example.com/photo'}}]
        with self.assertRaisesRegex(ValueError, 'attribution decision'):
            prepare_metadata(self.brief, self.manifest, 'a' * 64)
        self.manifest['scenes'] = []
        self.manifest['caption_transcript'] = 'Otra historia'
        with self.assertRaisesRegex(ValueError, 'rendered story'):
            prepare_metadata(self.brief, self.manifest, 'a' * 64)

    def test_restart_preserves_metadata_and_detects_changed_master(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            master = root / 'fixture.test'
            master.write_bytes(b'Not actual media; handoff fixture')
            self.manifest['output'] = str(master)
            refs = []
            for name, value in [('production-brief.json', self.brief), ('master-manifest.json', self.manifest)]:
                path = root / name
                write_json(path, value)
                refs.append({'path': str(path), 'sha256': file_hash(path)})
            step = {'id': 'render', 'job_id': 'job', 'channel_id': 'sabias-que', 'adapter': 'cutout',
                    'state': 'accepted', 'payload': {'inputs': refs},
                    'result': {'status': 'TECHNICAL_PASS', 'output_path': str(master), 'sha256': file_hash(master)}}
            queue = SimpleNamespace(list=lambda: [step])
            outputs = advance_metadata(root, queue)
            self.assertEqual(len(outputs), 1)
            old = Path(outputs[0]).read_bytes()
            self.assertEqual(advance_metadata(root, queue), [])
            self.assertEqual(Path(outputs[0]).read_bytes(), old)
            master.write_bytes(b'Changed master')
            self.assertEqual(advance_metadata(root, queue), [])
            error = root / '.runtime/jobs/job/handoffs/error-metadata-render.json'
            self.assertEqual(read_json(error)['status'], 'blocked')
            self.assertEqual(Path(outputs[0]).read_bytes(), old)
