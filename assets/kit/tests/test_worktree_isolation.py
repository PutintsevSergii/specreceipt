"""Actual Git worktrees retain global freshness and independent local receipts."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from harnesslib.adopt import adopt
from harnesslib.core import Harness
from harnesslib.storage import HarnessError
from harnesslib.verification import scope_changes
import test_onboarding as onboarding


class WorktreeIsolationTests(unittest.TestCase):
    def test_independent_state_scope_guard_and_integration(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            a, b = base/'a', base/'b'
            a.mkdir()
            def git(root, *args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True, text=True).stdout
            git(a, 'init', '-b', 'main')
            git(a, 'config', 'user.name', 'Isolated fixture')
            git(a, 'config', 'user.email', 'fixture@example.invalid')
            (a/'calculator.py').write_text('def add(a, b):\n    return a + b\n')
            git(a, 'add', 'calculator.py')
            git(a, 'commit', '-m', 'Fixture baseline')
            git(a, 'worktree', 'add', '-b', 'task-b', str(b))
            fixtures = []
            for root in (a, b):
                adopt(onboarding.KIT, root, False)
                f = onboarding.OnboardingTests()
                f.root, f.h = root, Harness(root)
                f.prepare(); f.approve()
                f.h.transition('CALC-001', 'IN_PROGRESS', 'isolated fixture approval')
                f.h.transition('CALC-001', 'IMPLEMENTED', 'isolated fixture implementation')
                self.assertEqual(f.h.verify('CALC-001')['result'], 'PASS')
                fixtures.append(f)
            first, second = fixtures
            binding = first.h.binding()
            state = (a/'.harness/state.json').read_bytes()
            evidence = first.h.task('CALC-001')[1]['evidence'][:]
            self.assertNotEqual(evidence, second.h.task('CALC-001')[1]['evidence'])
            (b/'calculator.py').write_text('def add(a, b):\n    return (a + b) + 0\n')
            second.h.checkpoint()
            self.assertEqual(first.h.binding(), binding)
            self.assertEqual((a/'.harness/state.json').read_bytes(), state)
            self.assertTrue(first.h.current_evidence(first.h.task('CALC-001')[1]))
            (a/'unauthorized.py').write_text('unexpected = True\n')
            with self.assertRaisesRegex(HarnessError, 'outside approved scope'):
                scope_changes(first.h, first.h.task('CALC-001')[1])
            (a/'unauthorized.py').unlink()  # Only this fixture-created file.
            git(b, 'add', 'calculator.py')
            git(b, 'commit', '-m', 'Reviewed fixture integration')
            git(a, 'merge', '--ff-only', 'task-b')
            self.assertNotEqual(first.h.binding(), binding)
            self.assertFalse(first.h.current_evidence(first.h.task('CALC-001')[1]))
            fresh = first.h.verify('CALC-001')
            self.assertEqual(fresh['result'], 'PASS')
            self.assertNotIn('.harness/evidence/'+fresh['id']+'.json', evidence)
