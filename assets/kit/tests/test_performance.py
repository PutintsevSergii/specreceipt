"""Bounded reporting work without cached lifecycle decisions."""
import copy
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_harness
from harnesslib import reporting
from harnesslib.storage import atomic, read, HarnessError


class ReportingPerformanceTests(unittest.TestCase):
    setUp = test_harness.HarnessTests.setUp
    implemented = test_harness.HarnessTests.implemented
    verified = test_harness.HarnessTests.verified

    def test_multi_task_report_and_status_each_inventory_once(self):
        feature, task = self.h.task('DEMO-001')
        other = copy.deepcopy(task); other['id'] = 'DEMO-002'
        feature['tasks'].append(other)
        atomic(self.root/'specs/harness-demo/tasks.json', feature)
        self.verified()
        for action in (lambda: reporting.report(self.h), self.h.status):
            with patch.object(self.h, 'fingerprints', wraps=self.h.fingerprints) as scans:
                result = action()
            self.assertEqual(scans.call_count, 1)
            self.assertEqual(len(result['tasks']), 2)

    def test_transition_refreshes_once_and_keeps_fresh_gate_scans(self):
        for state in ('IN_PROGRESS', 'IMPLEMENTED'):
            with patch.object(reporting, 'refresh_current', wraps=reporting.refresh_current) as refresh, \
                 patch.object(self.h, 'fingerprints', wraps=self.h.fingerprints) as scans:
                self.h.transition('DEMO-001', state, 'bounded reporting regression')
            self.assertEqual(refresh.call_count, 1)
            self.assertGreaterEqual(scans.call_count, 2)
            self.assertLessEqual(scans.call_count, 4)
            self.assertEqual(read(self.root/'.harness/reports/current.json')['tasks'][0]['status'], state)

    def test_outer_operation_batches_nested_library_calls_but_state_is_durable(self):
        from harnesslib.report_operation import scope
        with patch.object(reporting, 'refresh_current', wraps=reporting.refresh_current) as refresh:
            with scope(self.h):
                self.h.transition('DEMO-001', 'IN_PROGRESS', 'nested operation fixture')
                self.h.transition('DEMO-001', 'IMPLEMENTED', 'nested operation fixture')
                self.assertEqual(refresh.call_count, 0)
                self.assertEqual(self.h.task('DEMO-001')[1]['status'], 'IMPLEMENTED')
                self.assertEqual(read(self.root/'.harness/reports/current.json')['report_kind'], 'stale')
                self.assertEqual(reporting.report(self.h)['tasks'][0]['status'], 'IMPLEMENTED')
            self.assertEqual(refresh.call_count, 1)
        self.assertEqual(read(self.root/'.harness/reports/current.json')['tasks'][0]['status'], 'IMPLEMENTED')

    def test_same_timestamp_edit_invalidates_next_report_and_real_gate(self):
        self.verified()
        before = reporting.report(self.h)['tasks'][0]
        self.assertEqual(before['verification']['status'], 'PASS')
        path = self.root/'docs/DEMO.md'; stamp = path.stat()
        text = path.read_text(encoding='utf-8')
        path.write_text(('u' if text[0] != 'u' else 'U') + text[1:], encoding='utf-8')
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        after = reporting.report(self.h)['tasks'][0]
        self.assertEqual(after['effective_status'], 'REWORK')
        self.assertFalse(self.h.current_evidence(self.h.task('DEMO-001')[1]))
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001', 'DONE', 'must reject stale content')
        self.assertEqual(self.h.task('DEMO-001')[1]['status'], 'REWORK')

    def test_check_source_mutation_still_fails_stable_inputs(self):
        config = read(self.root/'.harness/checks.json')
        config['checks']['demo-doc'].update(kind='command', argv=['{python}', '-c',
            "from pathlib import Path; Path('docs/DEMO.md').write_text('checkpoint resume mutated by check')"])
        atomic(self.root/'.harness/checks.json', config)
        self.implemented()
        evidence = self.h.verify('DEMO-001')
        self.assertEqual(evidence['result'], 'FAIL')
        self.assertTrue(any(r['check'] == 'stable-inputs' and r['result'] == 'FAIL' for r in evidence['results']))

    def test_process_exit_after_commit_leaves_stale_derived_report(self):
        kit = Path(__file__).resolve().parents[1]
        code = ('import sys,os; sys.path.insert(0,sys.argv[1]); from harnesslib.core import Harness; '
                'h=Harness(sys.argv[2]); h.checkpoint=lambda:os._exit(77); '
                'h.transition("DEMO-001","IN_PROGRESS","simulated interruption after durable commit")')
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', code, str(kit), str(self.root)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertEqual(self.h.task('DEMO-001')[1]['status'], 'IN_PROGRESS')
        self.assertEqual(read(self.root/'.harness/reports/current.json')['report_kind'], 'stale')
        self.h.checkpoint()
        self.assertEqual(read(self.root/'.harness/reports/current.json')['tasks'][0]['status'], 'IN_PROGRESS')


class ProgressTests(unittest.TestCase):
    def test_active_test_is_published_even_inside_throttle_interval(self):
        from harnesslib import test_progress
        with tempfile.TemporaryDirectory() as folder:
            class Cases(unittest.TestCase):
                def test_active(self):
                    data = test_progress.observed(folder)
                    self.assertEqual(data['active_test'], self.id())
                    self.assertEqual(data['result'], 'INCOMPLETE')
            result = test_progress.run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases), folder, stream=io.StringIO())
            self.assertEqual(result, 0)

    def test_progress_is_bounded_redacted_and_preserves_failure_result(self):
        from harnesslib import test_progress
        class Cases(unittest.TestCase):
            def test_pass(self): pass
            def test_fail(self): self.fail('private failure text')
            def id(self): return 'token=fixture-private'
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'HARNESS_CHECK_NAME': 'password=fixture-private'}):
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(Cases)
            self.assertEqual(test_progress.run(suite, folder, stream=io.StringIO()), 1)
            data = test_progress.observed(folder)
            self.assertEqual((data['status'], data['result'], data['completed'], data['failures']), ('COMPLETED', 'FAIL', 2, 1))
            self.assertLessEqual(len(data['slowest']), 5)
            self.assertNotIn('fixture-private', json.dumps(data))
            self.assertNotIn('private failure text', json.dumps(data))

    def test_interrupted_progress_cannot_claim_pass(self):
        from harnesslib import test_progress
        class Cases(unittest.TestCase):
            def test_interrupt(self): raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(KeyboardInterrupt):
                test_progress.run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases), folder, stream=io.StringIO())
            data = test_progress.observed(folder)
            self.assertEqual((data['status'], data['result']), ('INTERRUPTED', 'INCOMPLETE'))

    def test_running_progress_is_observation_not_passing_evidence(self):
        from harnesslib import test_progress
        with tempfile.TemporaryDirectory() as folder:
            progress = test_progress.Progress(folder, 10)
            progress.publish(force=True)
            data = test_progress.observed(folder)
            self.assertEqual((data['status'], data['result'], data['completed']), ('RUNNING', 'INCOMPLETE', 0))
