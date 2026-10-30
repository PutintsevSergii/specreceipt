"""Command success must never imply observed cases or semantic proof."""
import unittest
from harnesslib import reporting
from harnesslib.storage import atomic, read, HarnessError
import test_harness as fixtures


class AcceptanceSupportTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.HarnessTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.h, self.root = self.f.h, self.f.root

    def test_exit_zero_is_check_only_in_receipt_and_reports(self):
        cfg = read(self.root/'.harness/checks.json')
        cfg['checks']['demo-doc'].update(kind='command', argv=['{python}', '-c', 'print("all good")'])
        atomic(self.root/'.harness/checks.json', cfg)
        self.f.implemented()
        ev = self.h.verify('DEMO-001')
        self.assertEqual(ev['results'][0]['result'], 'PASS')
        self.assertEqual(ev['acceptance_support']['criteria'][0]['level'], 'CHECK_ONLY')
        report = reporting.task_report(self.h, 'DEMO-001')
        self.assertEqual(report['verification']['acceptance_support'], ev['acceptance_support'])
        for markdown in (False, True):
            self.assertIn('CHECK_ONLY', reporting.render({'tasks':[report]}, markdown))

    def test_legacy_receipt_read_does_not_rewrite_or_strengthen(self):
        self.f.implemented()
        ev = self.h.verify('DEMO-001')
        ev.pop('acceptance_support', None)
        ref = self.h.task('DEMO-001')[1]['evidence'][-1]
        atomic(self.root/ref, ev)
        before = (self.root/ref).read_bytes()
        self.h.evidence(ref)
        report = reporting.task_report(self.h, 'DEMO-001')
        self.assertEqual(report['verification']['acceptance_support']['criteria'][0]['level'], 'CHECK_ONLY')
        self.assertEqual(before, (self.root/ref).read_bytes())

    def test_unsupported_support_schema_or_claim_is_rejected(self):
        self.f.implemented()
        ev = self.h.verify('DEMO-001')
        ev['acceptance_support'] = {'schema_version': 99, 'criteria': []}
        with self.assertRaises(HarnessError): self.h.schema('evidence', ev)
