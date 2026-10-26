"""Native platform boundaries; no WSL, shell-script stubs or network required."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from harnesslib import processes
from harnesslib.storage import atomic, lock, read


class NativePlatformTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows junction boundary')
    def test_junction_does_not_expose_external_navigation_or_verification_inputs(self):
        from harnesslib.graph import inventory
        from harnesslib.verification import inventory as verification_inventory
        from harnesslib.storage import safe_path, HarnessError
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); root = base/'project'; root.mkdir()
            outside = base/'outside'; outside.mkdir()
            (outside/'private.py').write_text('fixture only')
            result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(root/'alias'), str(outside)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('alias/private.py', inventory(root))
            with self.assertRaises(HarnessError): safe_path(root, 'alias/private.py')
            with self.assertRaises(HarnessError): verification_inventory(root)

    @unittest.skipUnless(os.name == 'nt', 'Windows path aliases')
    def test_windows_aliases_cannot_bypass_repository_path_boundary(self):
        from harnesslib.storage import safe_path, HarnessError
        with tempfile.TemporaryDirectory() as folder:
            for name in ('docs/file:stream', 'C:relative', 'docs/plan.md.', 'docs/plan.md ', 'NUL', 'aux.txt'):
                with self.subTest(name=name), self.assertRaises(HarnessError): safe_path(folder, name)

    def test_explicit_empty_child_environment_does_not_inherit_parent_values(self):
        with patch.dict(os.environ, {'HARNESS_TEST_PRIVATE_VALUE': 'not inherited'}):
            result = processes.run([sys.executable, '-c', 'import os; print(os.environ.get("HARNESS_TEST_PRIVATE_VALUE", "absent"))'], env={}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'absent')

    @unittest.skipUnless(os.name == 'nt', 'Windows missing-runtime boundary')
    def test_readonly_launcher_does_not_download_missing_python(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(__file__).resolve().parents[1]/'scripts/python.ps1'
            shell = Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            runtime = Path(folder)/'missing-runtime'
            result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-c', 'print(1)'],
                                    env=dict(os.environ, PATH='', HARNESS_PYTHON='', HARNESS_RUNTIME_DIR=str(runtime)), capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Python 3.11+', result.stderr)
            self.assertFalse(runtime.exists())

    def test_windows_node_zip_checksum_and_paths(self):
        import hashlib
        import io
        import zipfile
        from harnesslib import runtime
        from harnesslib.storage import HarnessError
        prefix = 'node-v22.99.0-win-x64'
        for mode in ('valid', 'checksum', 'traversal'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as archive:
                    archive.writestr('../outside' if mode == 'traversal' else prefix+'/node.exe', b'fixture')
                data = stream.getvalue()
                checksum = '0'*64 if mode == 'checksum' else hashlib.sha256(data).hexdigest()
                def download(url, path, limit):
                    path.write_bytes((checksum+'  '+prefix+'.zip\n').encode() if url.endswith('.txt') else data)
                base = Path(folder)/'runtime'
                with patch.object(runtime, 'directory', return_value=base), patch.object(runtime, 'node_platform', return_value=('win','x64')), patch.object(runtime, 'node_compatible', side_effect=[False, True]), patch.object(runtime, 'download', side_effect=download), patch.object(runtime, 'activate'):
                    if mode == 'valid':
                        runtime.ensure_node()
                        self.assertTrue((base/'node/node.exe').is_file())
                    else:
                        with self.assertRaises(HarnessError): runtime.ensure_node()
                        self.assertFalse((base/'node').exists())
                self.assertFalse((Path(folder)/'outside').exists())

    def test_atomic_replace_failure_preserves_previous_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'
            atomic(path, {'revision': 1})
            with patch('harnesslib.storage.os.replace', side_effect=PermissionError('busy')):
                with self.assertRaises(PermissionError): atomic(path, {'revision': 2})
            self.assertEqual(read(path), {'revision': 1})
            self.assertEqual(list(Path(folder).glob('*.tmp-*')), [])
            atomic(path, {'revision': 3})
            self.assertEqual(read(path), {'revision': 3})

    def test_writer_exclusion_across_processes_and_release(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            code = 'from pathlib import Path; from harnesslib.storage import lock; import sys\nwith lock(Path(sys.argv[1])): print("acquired")'
            with lock(root):
                result = subprocess.run([sys.executable, '-c', code, folder], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Another harness writer', result.stderr)
            result = subprocess.run([sys.executable, '-c', code, folder], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.name == 'nt', 'Windows package command boundary')
    def test_npm_entry_preserves_arguments_without_cmd(self):
        with tempfile.TemporaryDirectory(prefix='native paths ') as folder:
            root = Path(folder)
            package = root/'node_modules/npm'
            package.mkdir(parents=True)
            (package/'package.json').write_text(json.dumps({'bin': {'npm': 'cli.js'}}))
            (package/'cli.js').write_text('console.log(JSON.stringify(process.argv.slice(2)))')
            shim = root/'npm.cmd'; shim.write_text('@exit /b 99')
            result = processes.run([str(shim), 'space value', '& echo injected', '%PATH%', 'quote"value'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ['space value', '& echo injected', '%PATH%', 'quote"value'])

    def test_timeout_cleanup_stops_descendant(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder)/'heartbeat'
            child = 'from pathlib import Path; import sys,time\np=Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.time())); time.sleep(.1)'
            parent = 'import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]])\ntime.sleep(60)'
            process = subprocess.Popen([sys.executable, '-c', parent, child, str(marker)], start_new_session=True)
            try:
                deadline = time.monotonic()+10
                while not marker.exists() and time.monotonic()<deadline: time.sleep(.05)
                self.assertTrue(marker.exists())
                processes.stop(process)
                before = marker.read_bytes()
                time.sleep(.4)
                self.assertEqual(marker.read_bytes(), before)
            finally:
                if process.poll() is None: processes.stop(process)

    def test_bounded_tool_run_cleans_up_descendants_on_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder)/'heartbeat'
            child = 'from pathlib import Path; import sys,time\np=Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.time())); time.sleep(.1)'
            parent = 'import subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]])\ntime.sleep(60)'
            with self.assertRaises(subprocess.TimeoutExpired):
                processes.run([sys.executable, '-c', parent, child, str(marker)], timeout=2, capture_output=True, text=True)
            self.assertTrue(marker.exists())
            before = marker.read_bytes()
            time.sleep(.4)
            self.assertEqual(marker.read_bytes(), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows native launcher')
    def test_powershell_launcher_propagates_exit_code(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, HARNESS_PYTHON=sys.executable)
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(root/'scripts/python.ps1'), str(root/'harness'), 'invalid-command'],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
