import unittest
from ecosystem.metadata import prepare_native_metadata


class NativeMetadataTests(unittest.TestCase):
    def test_adaptation_label_and_master_binding(self):
        creative = {'editorial_title':'El bien que nadie ve','scripture_reference':'Mateo 6:3-4',
                    'scripture_source':'RV1909','content_classification':{'narration_kind':'editorial_adaptation'}}
        result = prepare_native_metadata(creative,'a'*64)
        self.assertIn('adaptación editorial',result['description'])
        self.assertIn('Mateo 6:3-4',result['description'])
        self.assertEqual(result['master_sha256'],'a'*64)
        self.assertEqual(result['channel_id'],'religion')
        with self.assertRaises(ValueError):
            prepare_native_metadata({**creative,'content_classification':{'narration_kind':'literal_quote'}},'a'*64)
        with self.assertRaises(ValueError):
            prepare_native_metadata(creative,'changed')
