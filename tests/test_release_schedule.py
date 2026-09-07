from datetime import datetime
import unittest
from ecosystem.release import youtube_schedule
from ecosystem.config import ROOT, read_json


class ScheduleTests(unittest.TestCase):
    def test_two_elapsed_hours_across_midnight_and_dst(self):
        result = youtube_schedule('2026-10-25T02:30:00+02:00', now=datetime.fromisoformat('2026-10-25T01:00:00+00:00'))
        self.assertEqual(result, {'privacyStatus': 'private', 'publishAt': '2026-10-25T02:30:00Z'})
        result = youtube_schedule('2026-09-07T23:15:00Z', now=datetime.fromisoformat('2026-09-07T23:20:00+00:00'))
        self.assertEqual(result['publishAt'], '2026-09-08T01:15:00Z')

    def test_round_up_for_studio_never_shortens_delay(self):
        result = youtube_schedule('2026-09-07T10:00:43Z', now=datetime.fromisoformat('2026-09-07T10:01:00+00:00'), minute_precision=True)
        self.assertEqual(result['publishAt'], '2026-09-07T12:01:00Z')

    def test_elapsed_or_ambiguous_timestamp_cannot_publish_immediately(self):
        for value in ['2026-09-07T08:00:00Z', '2026-09-07T13:00:00Z', '2026-09-07T10:00:00']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                youtube_schedule(value, now=datetime.fromisoformat('2026-09-07T12:00:00+00:00'))

    def test_global_policy_is_automatic(self):
        policy = read_json(ROOT / 'config/ecosystem.json')['youtube_release']
        self.assertIs(policy['user_approval_required'], False)
        self.assertEqual(policy['scope'], 'all_current_and_future_channels')
