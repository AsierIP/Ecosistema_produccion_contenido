import unittest
from unittest.mock import Mock
from ecosystem.recovery import recover_review_timeouts
from ecosystem.release import validate_schedule_receipt


class RecoveryTests(unittest.TestCase):
    def test_remote_side_effects_never_enter_review_retry(self):
        queue = Mock()
        queue.list.return_value = [{'adapter':a,'state':'uncertain'} for a in ('release','visual','vibes_generate','voice_generate')]
        self.assertEqual(recover_review_timeouts('.',queue), [])
        queue.register.assert_not_called()

    def test_retry_cannot_repeat_itself(self):
        queue = Mock()
        queue.list.return_value = [{'adapter':'quality','state':'blocked','payload':{'automatic_recovery_of':'old'}}]
        self.assertEqual(recover_review_timeouts('.',queue), [])
        queue.register.assert_not_called()

    def test_public_outcome_does_not_invent_schedule_time(self):
        intent = {'master_sha256':'a'*64,'payload':{'expected_account_id':'channel',
                  'video_id':'abcdefghijk','publishAt':'2026-09-08T11:00:00Z'}}
        public = {'master_sha256':'a'*64,'account_id':'channel','public_verified':True,
                  'url':'https://www.youtube.com/shorts/abcdefghijk',
                  'evidence':{'verified_at':'2026-09-10T11:00:00Z','method':'anonymous-playback'}}
        receipt = {'outcome':'public_observed_after_target','public_receipt':public}
        self.assertEqual(validate_schedule_receipt(receipt,intent), [])
        public['url']='https://www.youtube.com/shorts/otherVideo1'
        self.assertTrue(validate_schedule_receipt(receipt,intent))
        public['url']='https://www.youtube.com/shorts/abcdefghijk'
        public['evidence']['verified_at']='2026-09-07T11:00:00Z'
        self.assertTrue(validate_schedule_receipt(receipt,intent))
