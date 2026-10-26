"""Native bootstrap failure paths and explicit link capability policy."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from platform_support import require_symlink_capability

KIT = Path(__file__).resolve().parents[1]


class LinkCapabilityTests(unittest.TestCase):
    def test_child_environment_keeps_windows_primitives_without_inheriting_secrets(self):
        from harnesslib import processes
        values = {'SYSTEMDRIVE': 'C:', 'COMSPEC': 'C:/Windows/System32/cmd.exe',
                  'PATHEXT': '.EXE;.CMD', 'PROCESSOR_ARCHITECTURE': 'AMD64',
                  'HARNESS_REQUIRE_SYMLINK_TESTS': '1', 'HARNESS_TEST_SECRET': 'private fixture'}
        with patch.dict(os.environ, values):
            child = processes.environment()
            for key in values:
                if key != 'HARNESS_TEST_SECRET': self.assertEqual(child[key], values[key])
            self.assertNotIn('HARNESS_TEST_SECRET', child)
            self.assertEqual(child['PYTHONUTF8'], '1')

    @unittest.skipUnless(os.name == 'nt', 'Windows privilege contract')
    def test_only_privilege_failure_can_skip_and_strict_mode_fails(self):
        error = OSError('fixture privilege failure'); error.winerror = 1314
        with patch.object(Path, 'symlink_to', side_effect=error):
            with patch.dict(os.environ, {'HARNESS_REQUIRE_SYMLINK_TESTS': '0'}):
                with self.assertRaisesRegex(unittest.SkipTest, '1314'): require_symlink_capability()
            with patch.dict(os.environ, {'HARNESS_REQUIRE_SYMLINK_TESTS': '1'}):
                with self.assertRaisesRegex(AssertionError, 'Strict CI'): require_symlink_capability()
        with patch.object(Path, 'symlink_to', side_effect=OSError('fixture disk failure')):
            with self.assertRaisesRegex(OSError, 'disk failure'): require_symlink_capability()


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell bootstrap')
class WindowsSetupTests(unittest.TestCase):
    def test_no_python_launcher_bootstraps_without_user_bin_or_registry_registration(self):
        import sys
        with tempfile.TemporaryDirectory(prefix='python setup ') as folder:
            root = Path(folder); bins = root/'bins'; bins.mkdir()
            (bins/'uv.cmd').write_text('@echo off\nif "%1 %2" == "python find" (\n  echo '+sys.executable+'\n) else (\n  echo %*>>"'+str(root/'args.txt')+'"\n)\nexit /b 0\n', encoding='utf-8')
            proof = root/'proof.py'
            proof.write_text('import sys; print("bootstrap fixture:", sys.argv[1])', encoding='utf-8')
            runtime = root/'runtime'
            shell = Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(KIT/'scripts/python.ps1'), '-Bootstrap', str(proof), 'argument with spaces'],
                                    env=dict(os.environ, PATH=str(bins), HARNESS_PYTHON='', HARNESS_RUNTIME_DIR=str(runtime)), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('bootstrap fixture: argument with spaces', result.stdout)
            self.assertEqual((root/'args.txt').read_text().strip(), 'python install --no-bin --no-registry 3.12')
            self.assertEqual((runtime/'python-path.txt').read_text(), sys.executable)

    def test_uv_fallback_verifies_archive_before_publishing(self):
        source = (KIT/'scripts/uv.ps1').read_text(encoding='utf-8')
        shell = Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        for mode in ('fallback', 'checksum', 'traversal', 'offline', 'existing'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='uv setup ü ') as folder:
                root = Path(folder)
                archive = root/'fixture.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    z.writestr('../escape.exe' if mode == 'traversal' else 'uv.exe', b'fixture uv')
                    z.writestr('uvx.exe', b'fixture uvx')
                    z.writestr('uvw.exe', b'fixture uvw')
                checksum = '0'*64 if mode == 'checksum' else hashlib.sha256(archive.read_bytes()).hexdigest()
                script = root/'uv.ps1'
                script.write_text(source.replace('a38b8d1902b7cfbc76b423ba1bb456f623f42064cdc72628b6075b89afd1019a', checksum), encoding='utf-8')
                wrapper = root/'invoke.ps1'
                wrapper.write_text('''$ErrorActionPreference = 'Stop'
function Invoke-WebRequest($Uri, $OutFile, [switch]$UseBasicParsing) {
    Add-Content -LiteralPath "$PSScriptRoot/calls.txt" -Value $Uri
    if ($env:UV_TEST_MODE -eq 'offline' -or $Uri.StartsWith('https://github.com/')) { throw 'fixture network refusal' }
    Copy-Item -LiteralPath "$PSScriptRoot/fixture.zip" -Destination $OutFile
}
. "$PSScriptRoot/uv.ps1"
Install-HarnessUv "$PSScriptRoot/bin"
''', encoding='utf-8')
                if mode == 'existing':
                    (root/'bin').mkdir(); (root/'bin/uv.exe').write_bytes(b'keep existing')
                result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper)],
                                        env=dict(os.environ, UV_TEST_MODE=mode), capture_output=True, text=True, timeout=30)
                if mode == 'fallback':
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((root/'bin/uv.exe').read_bytes(), b'fixture uv')
                    self.assertEqual(len((root/'calls.txt').read_text().splitlines()), 2)
                else:
                    self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
                    if mode == 'existing': self.assertEqual((root/'bin/uv.exe').read_bytes(), b'keep existing')
                    else: self.assertFalse((root/'bin/uv.exe').exists())
                self.assertFalse((root/'escape.exe').exists())
                self.assertEqual(list((root/'bin').glob('.uv-stage-*')), [])
