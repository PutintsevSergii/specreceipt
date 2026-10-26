"""Capability gate for real links; strict CI must execute these regressions."""
import os
from pathlib import Path
import tempfile
import unittest


def require_symlink_capability():
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder)/'source'
        source.write_text('capability fixture', encoding='utf-8')
        try:
            (Path(folder)/'link').symlink_to(source)
        except OSError as exc:
            if os.name != 'nt' or getattr(exc, 'winerror', None) != 1314:
                raise
            if os.environ.get('HARNESS_REQUIRE_SYMLINK_TESTS') == '1':
                raise AssertionError('Strict CI requires real symlink capability (WinError 1314).') from exc
            raise unittest.SkipTest('Windows lacks symlink privilege (1314); real symlink coverage is required in strict CI.') from exc


def symlink(path, target, **kwargs):
    require_symlink_capability()
    path.symlink_to(target, **kwargs)
