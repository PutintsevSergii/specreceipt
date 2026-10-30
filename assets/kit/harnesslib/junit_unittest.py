"""Run real stdlib unittest cases and emit the supported stamped JUnit subset.

Usage: python -B -m harnesslib.junit_unittest test_module
The approved Harness runner supplies HARNESS_TEST_REPORT and invocation stamps.
Subtests are deliberately unsupported for case-level acceptance in version 1.
"""
import os
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observations = []
        self.subtested = set()

    def record(self, test, status, error=None, message=''):
        identity = test.id()
        self.observations.append((identity, status, error[0].__name__ if error else '',
                                  str(error[1]) if error else message))

    def addSuccess(self, test):
        super().addSuccess(test)
        if test.id() not in self.subtested: self.record(test, 'PASS')

    def addFailure(self, test, err):
        super().addFailure(test, err); self.record(test, 'FAIL', err)

    def addError(self, test, err):
        super().addError(test, err); self.record(test, 'ERROR', err)

    def addSkip(self, test, reason):
        super().addSkip(test, reason); self.record(test, 'SKIPPED', message=reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err); self.record(test, 'SKIPPED', err)

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test); self.record(test, 'ERROR', message='Unexpected success (xpass)')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if test.id() not in self.subtested:
            self.subtested.add(test.id())
            self.record(test, 'ERROR', message='Subtests need a supported stable identity adapter')


class Runner(unittest.TextTestRunner):
    resultclass = Result

    def run(self, test):
        result = super().run(test)
        suite = ET.Element('testsuite', tests=str(len(result.observations)))
        props = ET.SubElement(suite, 'properties')
        for key, env in [('operation','HARNESS_OPERATION_ID'),('check','HARNESS_CHECK_NAME'),('invocation','HARNESS_TEST_INVOCATION')]:
            ET.SubElement(props,'property', name='harness.'+key, value=os.environ[env])
        for identity, status, kind, message in result.observations:
            group, _, name = identity.rpartition('.')
            case = ET.SubElement(suite,'testcase', classname=group, name=name)
            if status != 'PASS':
                ET.SubElement(case, {'FAIL':'failure','ERROR':'error','SKIPPED':'skipped'}[status], type=kind, message=message)
        Path(os.environ['HARNESS_TEST_REPORT']).write_bytes(ET.tostring(suite, encoding='utf-8'))
        return result


if __name__ == '__main__':
    unittest.main(module=None, testRunner=Runner)
