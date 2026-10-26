import json
from pathlib import Path
import subprocess
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]

class ProtocolTests(unittest.TestCase):
    def call(self, request):
        return subprocess.run([sys.executable, '-B', '-m', 'harnesslib.protocol'], cwd=ROOT,
                              input=json.dumps(request), text=True, capture_output=True)

    def test_contract_and_legacy_command_registry(self):
        result = self.call({'protocolVersion': 1, 'target': str(ROOT), 'argv': ['contract']})
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn('task', data['data']['operations'])
        self.assertIn('review', data['data']['operations'])
        self.assertEqual(data['engineRoot'], str(ROOT))

    def test_wrong_protocol_and_invalid_input_are_structured(self):
        for request in [None, {}, {'protocolVersion': 99, 'target': str(ROOT), 'argv': ['status']},
                        {'protocolVersion': 1, 'target': str(ROOT), 'argv': ['--root=/tmp', 'status']}]:
            result = self.call(request)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['error']['code'], 'INVALID_REQUEST')

    def test_help_and_argparse_errors_have_envelopes(self):
        for argv, code in [(['task','--help'],0), (['task','invalid'],2)]:
            result=self.call({'protocolVersion':1,'target':str(ROOT),'argv':argv})
            self.assertEqual(result.returncode,code)
            self.assertEqual(json.loads(result.stdout)['exitCode'],code)
