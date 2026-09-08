import unittest
from ecosystem.delivery import reviewed_master


class ReviewedMasterTests(unittest.TestCase):
    def test_selects_reviewed_master_among_source_clips(self):
        source = {'path':'source.mp4','sha256':'a'*64}
        master = {'path':'master.mp4','sha256':'b'*64}
        self.assertEqual(reviewed_master([source,master],{'master_sha256':'b'*64}),master)
        with self.assertRaises(ValueError):
            reviewed_master([source],{'master_sha256':'b'*64})
        with self.assertRaises(ValueError):
            reviewed_master([master,{**master,'path':'copy.mp4'}],{'master_sha256':'b'*64})
