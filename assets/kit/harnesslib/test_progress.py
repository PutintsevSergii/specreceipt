"""Structured self-test progress; raw child output remains private."""
import os
from pathlib import Path
import sys
import time
import unittest
from .storage import HarnessError, atomic, now, read, redact, safe_path

REFERENCE = '.harness/progress/self-test.json'


def observed(root):
    """Last observation, never execution evidence or a liveness claim."""
    try:
        path = safe_path(Path(root), REFERENCE)
        if not path.exists(): return None
        if path.stat().st_size > 65536: return {'status': 'UNAVAILABLE'}
        value = read(path)
        fields = ('status', 'result', 'check', 'operation', 'pid', 'updated_at',
                  'elapsed_seconds', 'total', 'completed', 'failures', 'errors', 'skipped', 'active_test', 'slowest')
        return {key: redact(value[key]) for key in fields if key in value}
    except (OSError, HarnessError, ValueError, TypeError):
        return {'status': 'UNAVAILABLE'}


class Progress:
    def __init__(self, root, total):
        self.root = Path(root); self.total = total
        self.started = time.perf_counter(); self.last_write = -1.0
        self.completed = 0; self.active = None; self.slowest = []
        self.enabled = True

    def publish(self, result=None, status='RUNNING', force=False):
        elapsed = time.perf_counter() - self.started
        if not self.enabled or (not force and elapsed - self.last_write < 1): return
        data = {'status': status, 'result': 'PASS' if result and result.wasSuccessful() else 'FAIL' if result else 'INCOMPLETE',
                'check': redact(os.environ.get('HARNESS_CHECK_NAME', 'self-test'))[:256],
                'operation': redact(os.environ.get('HARNESS_OPERATION_ID', 'direct-self-test'))[:256],
                'pid': os.getpid(), 'updated_at': now(), 'elapsed_seconds': round(elapsed, 3),
                'total': self.total, 'completed': self.completed, 'active_test': self.active,
                'failures': len(result.failures) if result else 0, 'errors': len(result.errors) if result else 0,
                'skipped': len(result.skipped) if result else 0, 'slowest': self.slowest}
        if status != 'COMPLETED': data['result'] = 'INCOMPLETE'
        try:
            atomic(safe_path(self.root, REFERENCE), data)
            self.last_write = elapsed
        except (OSError, HarnessError):
            self.enabled = False
            print('WARNING: self-test progress unavailable; test execution continues.', file=sys.stderr)


class MeasuredResult(unittest.TextTestResult):
    def __init__(self, *args, progress, **kwargs):
        super().__init__(*args, **kwargs)
        self.progress = progress

    def startTest(self, test):
        super().startTest(test)
        self.case_started = time.perf_counter()
        self.progress.active = redact(test.id())[:256]
        self.progress.publish(self, force=True)

    def stopTest(self, test):
        elapsed = time.perf_counter() - self.case_started
        self.progress.completed += 1
        self.progress.slowest = sorted([*self.progress.slowest,
            {'test': redact(test.id())[:256], 'seconds': round(elapsed, 4)}],
            key=lambda entry: entry['seconds'], reverse=True)[:5]
        self.progress.active = None
        self.progress.publish(self)
        super().stopTest(test)


def run(suite, root, stream=None):
    progress = Progress(root, suite.countTestCases())
    progress.publish(force=True)
    runner = unittest.TextTestRunner(verbosity=2, stream=stream,
        resultclass=lambda *args, **kwargs: MeasuredResult(*args, progress=progress, **kwargs))
    try:
        result = runner.run(suite)
    except BaseException:
        progress.publish(status='INTERRUPTED', force=True)
        raise
    progress.publish(result, status='COMPLETED', force=True)
    runner.stream.writeln('Slowest self-tests (seconds):')
    for entry in progress.slowest:
        runner.stream.writeln(f"  {entry['seconds']:.4f}  {entry['test']}")
    return 0 if result.wasSuccessful() else 1
