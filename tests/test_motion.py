import unittest
from copy import deepcopy
from ecosystem.motion import validate_motion

class MotionPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'scope_evidence': 'Fixture: smoke above a rigid chimney',
                     'protected_rects': [[.2, .6, .8, 1]],
                     'regions': [{'rect': [.3, .1, .7, .5], 'dx': 3, 'dy': 2, 'period': 3}]}

    def test_bounded_plan(self):
        self.assertEqual(validate_motion(self.plan), self.plan)

    def test_unbounded_or_static_motion_is_rejected(self):
        for changes in ({'dx': float('nan')}, {'dy': 99}, {'period': 0}, {'rect': [-1, 0, 1, 1]}, {'dx': 0, 'dy': 0}):
            plan = deepcopy(self.plan)
            plan['regions'][0].update(changes)
            with self.assertRaises(ValueError):
                validate_motion(plan)
