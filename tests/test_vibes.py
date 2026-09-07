from pathlib import Path
import tempfile
import unittest
from ecosystem.vibes import validate_request
from ecosystem.native_batch import ref


class VibesTests(unittest.TestCase):
    def test_existing_religion_profile_can_use_native_adapter(self):
        from ecosystem.config import load_channels, preparation_readiness
        channel = next(c for c in load_channels() if c['id'] == 'religion')
        self.assertEqual(preparation_readiness(channel, {}, 'vibes_generate'), [])
        channel['visual']['generation_provider'] = 'imagegen'
        self.assertTrue(preparation_readiness(channel, {}, 'vibes_generate'))

    def test_bounded_and_hash_bound_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'reference.png'
            source.write_bytes(b'fixture')
            request = {'kind': 'vibes_native_batch_v1', 'channel_id': 'religion', 'count': 4, 'batch_number': 2,
                       'start_reference': ref(source), 'prompt': ref(source), 'inputs': [ref(source)]}
            validate_request(request)
            request['batch_number'] = 4
            with self.assertRaises(ValueError):
                validate_request(request)
            request['batch_number'] = 2
            source.write_bytes(b'replacement')
            with self.assertRaisesRegex(ValueError, 'changed'):
                validate_request(request)
