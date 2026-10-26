"""Installation contracts, not evidence of authenticated model execution."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from harnesslib.adopt import adopt, ENTRYPOINTS
from harnesslib.core import Harness
from harnesslib.storage import HarnessError
from harnesslib import cli

KIT = Path(__file__).resolve().parents[1]

class AdoptBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'project'

    def test_preview_no_writes_then_initialized_idempotently(self):
        preview = adopt(KIT, self.root)
        self.assertFalse(self.root.exists())
        self.assertEqual(preview['agent_bootstrap']['status'], 'preview')
        for path in ENTRYPOINTS: self.assertIn(path, preview['files'])
        result = adopt(KIT, self.root, False)
        self.assertEqual(result['agent_bootstrap']['status'], 'instructions_installed')
        self.assertEqual(Harness(self.root).state()['phase'], 'SETUP')
        state = (self.root/'.harness/state.json').read_bytes()
        again = adopt(KIT, self.root, False)
        self.assertFalse(again['initialization']['changed'])
        self.assertEqual(state, (self.root/'.harness/state.json').read_bytes())
        self.assertEqual(again['files'], [])
        self.assertNotIn('run ./harness init', again['next_action'])

    def test_corporate_instructions_preserved_and_routed(self):
        originals = {'AGENTS.md':'Company agents', 'CLAUDE.md':'Company Claude',
                     '.github/copilot-instructions.md':'Company Copilot'}
        for name, content in originals.items():
            path=self.root/name; path.parent.mkdir(parents=True, exist_ok=True);path.write_text(content)
        adopt(KIT, self.root, False)
        for name, content in originals.items(): self.assertEqual((self.root/name).read_text(),content)
        bridge=(self.root/'AGENTS.override.md').read_text()
        self.assertIn('explicitly load AGENTS.md',bridge)
        for name in list(ENTRYPOINTS)[:3]: self.assertIn('.harness/BOOTSTRAP.md',(self.root/name).read_text())
        self.assertIn('applyTo: "**"',(self.root/'.github/instructions/harness-bootstrap.instructions.md').read_text())
        self.assertNotIn('paths:',(self.root/'.claude/rules/harness-bootstrap.md').read_text())

    def test_conflict_prevents_partial_install(self):
        self.root.mkdir()
        path=self.root/'AGENTS.override.md';path.write_text('existing corporate override')
        with self.assertRaises(HarnessError): adopt(KIT,self.root,False)
        self.assertFalse((self.root/'harness').exists())
        self.assertFalse((self.root/'.gitignore').exists())
        self.assertEqual(path.read_text(),'existing corporate override')

    def test_each_ignore_layer_covers_bridges(self):
        self.root.mkdir()
        subprocess.run(['git','init',str(self.root)],check=True,capture_output=True)
        result=adopt(KIT,self.root,False)
        exclude=Path(result['ignore_file']); ignore=self.root/'.gitignore'
        for disabled in (exclude,ignore):
            text=disabled.read_text(); disabled.write_text('')
            result=subprocess.run(['git','-C',str(self.root),'check-ignore',*ENTRYPOINTS],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(set(result.stdout.splitlines()),set(ENTRYPOINTS))
            disabled.write_text(text)

    def test_real_adopt_cli_initializes_without_manual_prompt(self):
        with patch.object(sys,'argv',['harness','adopt',str(self.root),'--apply']), \
             patch.object(cli.installation,'complete',return_value={'result':'PASS'}), patch('builtins.print'):
            self.assertEqual(cli.main(),0)
        result=subprocess.run([sys.executable,str(self.root/'harness'),'skills','project-onboarding'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['assessment_status'],'pending_agent')
        self.assertNotEqual(Harness(self.root).validate()['application_ready'],True)
