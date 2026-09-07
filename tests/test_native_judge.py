from pathlib import Path
import tempfile
import unittest
from ecosystem.config import write_json
from ecosystem.native_judge import seal


class NativeJudgeTests(unittest.TestCase):
    def test_acceptance_cannot_hide_a_failed_check(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            write_json(output/'native-judgment.json', {'decision':'ACCEPT','checks':{'exit_state_achieved':False},'defects':[]})
            context={'saved':{'output_directory':str(output)},
                     'contract':{'schema':{'segment_qa':{'required_passes':['exit_state_achieved']}}}}
            with self.assertRaisesRegex(ValueError,'contradicts'):
                seal(context)
            self.assertFalse((output/'receipt.json').exists())

    def test_native_checks_must_be_boolean_not_truthy_strings(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            write_json(output/'native-judgment.json', {'decision':'ACCEPT','checks':{'exit_state_achieved':'false'},'defects':[]})
            context={'saved':{'output_directory':str(output)},
                     'contract':{'schema':{'segment_qa':{'required_passes':['exit_state_achieved']}}}}
            with self.assertRaisesRegex(ValueError,'check set'):
                seal(context)
