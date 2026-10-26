"""Offline installer acceptance: actual shell bootstrap and fixture package managers."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from harnesslib import installation, runtime
from harnesslib.adopt import adopt
from harnesslib.storage import HarnessError

KIT=Path(__file__).resolve().parents[1]

class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'project'

    @unittest.skipIf(os.name == 'nt', 'POSIX shell bootstrap; Windows launcher covered by test_native_windows')
    def test_shell_bootstraps_when_python_and_uv_are_missing(self):
        bins=self.base/'bins';bins.mkdir();managed=self.base/'runtime'
        for name in ('sh','uname','mkdir','mktemp','rm','ln','cat'):
            (bins/name).symlink_to(shutil.which(name))
        curl=bins/'curl'
        curl.write_text('''#!/bin/sh
for arg do output=$arg; done
cat > "$output" <<'INSTALLER'
#!/bin/sh
cat > "$UV_UNMANAGED_INSTALL/uv" <<'UV'
#!/bin/sh
if [ "$1 $2" = "python find" ]; then
    echo "'''+sys.executable+'''"
fi
UV
/bin/chmod +x "$UV_UNMANAGED_INSTALL/uv"
INSTALLER
''');curl.chmod(0o755)
        env=dict(os.environ,PATH=str(bins),HARNESS_RUNTIME_DIR=str(managed))
        run=subprocess.run(['/bin/sh',str(KIT/'scripts/python.sh'),'--bootstrap','-c','print("bootstrap-ok")'],env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(run.stdout.strip(),'bootstrap-ok')
        self.assertTrue((managed/'bin/python3').is_file())
        self.assertTrue((managed/'bin/uv').is_file())

    @unittest.skipIf(os.name == 'nt', 'POSIX shell bootstrap; Windows missing-runtime test covers this contract')
    def test_no_download_for_readonly_without_python(self):
        run=subprocess.run(['/bin/sh',str(KIT/'scripts/python.sh'),'-c','print(1)'],
                           env=dict(os.environ,PATH=str(self.base),HARNESS_RUNTIME_DIR=str(self.base/'runtime')),
                           capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0)
        self.assertIn('install.sh',run.stderr)
        self.assertFalse((self.base/'runtime').exists())

    def test_complete_installs_tools_openspec_and_indexes(self):
        adopt(KIT,self.root,False)
        with patch.object(runtime,'prepare',return_value={'result':'PASS'}), \
             patch.object(installation.tool_updates,'probe',return_value=None), \
             patch.object(installation.tool_updates,'install',return_value='fixture') as install, \
             patch.object(installation.openspec_tool,'initialize',return_value={'result':'PASS'}) as init, \
             patch.object(installation,'selected_agents',return_value='codex'), \
             patch.object(installation.codegraph_tool,'ensure',return_value={'freshness':'fresh'}), \
             patch.object(installation.graphify_tool,'ensure',return_value={'freshness':'fresh'}):
            result=installation.complete(self.root)
        self.assertEqual(result['result'],'PASS')
        self.assertEqual([c.args[1] for c in install.call_args_list],['codegraph','graphify','openspec'])
        init.assert_called_once_with(self.root,'codex',False)
        self.assertIsNone(json.loads((self.root/'.harness/install.json').read_text())['active_step'])

    def test_failure_stops_and_records_exact_stage(self):
        self.root.mkdir()
        with patch.object(runtime,'prepare',side_effect=HarnessError('offline')), \
             patch.object(installation.tool_updates,'install') as install:
            result=installation.complete(self.root)
        self.assertEqual(result['result'],'BLOCKED')
        self.assertEqual(result['active_step'],'runtime')
        install.assert_not_called()

    def test_agent_detection_ignores_own_generated_bridges(self):
        adopt(KIT,self.root,False)
        with patch('harnesslib.assessment.shutil.which',return_value=None):
            self.assertEqual(installation.selected_agents(self.root),'none')
            (self.root/'CLAUDE.md').write_text('Company instructions')
            self.assertEqual(installation.selected_agents(self.root),'claude')

    def test_node_checksum_and_archive_paths(self):
        prefix='node-v22.99.0-linux-x64'; name=prefix+'.tar.gz'
        def archive_bytes(unsafe=False):
            buffer=io.BytesIO()
            with tarfile.open(fileobj=buffer,mode='w:gz') as tar:
                item=tarfile.TarInfo('../escape' if unsafe else prefix+'/bin/node')
                item.size=4;tar.addfile(item,io.BytesIO(b'node'))
            return buffer.getvalue()
        for mode in ('checksum','path','valid'):
            base=self.base/mode
            data=archive_bytes(mode=='path')
            digest='0'*64 if mode=='checksum' else hashlib.sha256(data).hexdigest()
            def download(url,path,limit):
                path.write_bytes((digest+'  '+name+'\n').encode() if url.endswith('.txt') else data)
            with patch.object(runtime,'directory',return_value=base), \
                 patch.object(runtime,'node_platform',return_value=('linux','x64')), \
                 patch.object(runtime,'node_compatible',side_effect=[False,True]), \
                 patch.object(runtime,'download',side_effect=download),patch.object(runtime,'activate'):
                if mode=='valid':
                    runtime.ensure_node();self.assertTrue((base/'node/bin/node').is_file())
                else:
                    with self.assertRaises(HarnessError): runtime.ensure_node()
                    self.assertFalse((base/'node').exists())
        self.assertFalse((self.base/'escape').exists())

    def test_compatible_node_never_downloads(self):
        with patch.object(runtime,'node_compatible',return_value=True),patch.object(runtime,'download') as download:
            runtime.ensure_node()
        download.assert_not_called()
