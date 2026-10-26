from platform_support import symlink
"""Real subprocess assessment and corporate skill coexistence without a live provider."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from harnesslib import cli
from harnesslib.adopt import adopt
from harnesslib.assessment import assess, current, inventory
from harnesslib.skills import catalog
from harnesslib.storage import HarnessError, atomic, read

KIT = Path(__file__).resolve().parents[1]

class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'project'
        self.root.mkdir()
        (self.root/'AGENTS.md').write_text('Corporate rules: preserve our review process.\n')
        skill=self.root/'.github/skills/company-tests/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('Use existing company tests for verification.\n')
        (self.root/'package.json').write_text(json.dumps({'scripts':{'test':'touch MUST_NOT_RUN'}}))
        (self.root/'.mcp.json').write_text('{"mcpServers":{"corp":{"token":"sensitive-fixture-value"}}}')
        adopt(KIT,self.root,False)

    def response(self):
        context=read(self.root/'.harness/assessment-context.json')
        return {'inventory_hash':context['inventory_hash'],
                'role_skills':{'verifier':['.github/skills/company-tests/SKILL.md']},
                'capabilities':[{'name':'corporate-mcp','status':'unverified','evidence':'Only a config file was observed.'}],
                'summary':'Use the company testing skill as a verifier supplement.'}

    def test_inventory_preserves_instructions_and_does_not_execute(self):
        self.assertEqual((self.root/'AGENTS.md').read_text(),'Corporate rules: preserve our review process.\n')
        self.assertTrue((self.root/'.harness/AGENTS.md').is_file())
        report=current(self.root)
        self.assertEqual(report['status'],'pending_agent')
        self.assertEqual(report['inventory']['mcp_configs'][0]['status'],'configured_unverified')
        self.assertNotIn('sensitive-fixture-value',json.dumps(report))
        self.assertFalse((self.root/'MUST_NOT_RUN').exists())

    def test_import_activates_supplement_and_change_invalidates(self):
        atomic(self.root/'.harness/response.json',self.response())
        result=assess(self.root,response_file='.harness/response.json')
        self.assertEqual(result['assessment_status'],'assessed')
        selected=catalog(self.root,'verifier')
        self.assertEqual(len(selected['project_skills']),1)
        self.assertIn('required check',selected['instructions'])
        (self.root/'.github/skills/company-tests/SKILL.md').write_text('Changed skill')
        self.assertEqual(catalog(self.root,'verifier')['assessment_status'],'stale')
        self.assertEqual(catalog(self.root,'verifier')['project_skills'],[])

    def test_unobserved_skill_and_stale_response_are_rejected(self):
        response=self.response(); response['role_skills']['verifier']=['../../outside/SKILL.md']
        atomic(self.root/'.harness/response.json',response)
        with self.assertRaises(HarnessError): assess(self.root,response_file='.harness/response.json')
        response=self.response(); response['inventory_hash']='old'
        atomic(self.root/'.harness/response.json',response)
        with self.assertRaises(HarnessError): assess(self.root,response_file='.harness/response.json')
        self.assertEqual(current(self.root)['status'],'pending_agent')

    def test_explicit_agent_subprocess_and_cli_integration(self):
        agent=Path(self.tmp.name)/'agent.py'
        agent.write_text('''import json,sys
from pathlib import Path
context=json.loads(Path(sys.argv[1]).read_text())
assert Path.cwd()==Path(context['project_root'])
print(json.dumps({'inventory_hash':context['inventory_hash'],
'role_skills':{'verifier':['.github/skills/company-tests/SKILL.md']},
'capabilities':[], 'summary':'Deterministic fixture examined project context.'}))
''')
        result=subprocess.run([sys.executable,str(self.root/'harness'),'assess','--agent-command',
                               json.dumps([sys.executable,str(agent),'{context}'])],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertEqual(json.loads(result.stdout)['assessment_status'],'assessed')
        self.assertEqual(len(catalog(self.root,'verifier')['project_skills']),1)

    def test_colliding_corporate_role_is_preserved(self):
        target=Path(self.tmp.name)/'collision'; target.mkdir()
        skill=target/'.agents/skills/verifier/SKILL.md'; skill.parent.mkdir(parents=True)
        skill.write_text('Corporate verifier remains authoritative for company procedures.')
        result=adopt(KIT,target,False)
        self.assertIn('.agents/skills/verifier/SKILL.md',result['preserved_project_files'])
        self.assertEqual(skill.read_text(),'Corporate verifier remains authoritative for company procedures.')
        self.assertEqual(catalog(target,'verifier')['path'],'.harness/skills/verifier/SKILL.md')

    def test_symlink_skills_are_not_discovered(self):
        outside=Path(self.tmp.name)/'outside.md'; outside.write_text('do not inventory')
        linked=self.root/'.github/skills/linked'; linked.mkdir()
        symlink(linked/'SKILL.md', outside)
        self.assertNotIn('.github/skills/linked/SKILL.md',[s['path'] for s in inventory(self.root)['skills']])

    def test_agent_failure_keeps_assessment_pending(self):
        with self.assertRaises(HarnessError):
            assess(self.root, [sys.executable, '-c', 'raise SystemExit(7)'])
        self.assertEqual(current(self.root)['status'],'pending_agent')

    def test_agent_source_mutation_is_detected(self):
        with self.assertRaisesRegex(HarnessError, 'modified project inputs'):
            assess(self.root, [sys.executable, '-c',
                   "from pathlib import Path; Path('unexpected.txt').write_text('change'); print('{}')"])
        self.assertEqual(current(self.root)['status'],'pending_agent')

    def test_repeat_adoption_keeps_current_assessment(self):
        atomic(self.root/'.harness/response.json',self.response())
        assess(self.root,response_file='.harness/response.json')
        adopt(KIT,self.root,False)
        self.assertEqual(current(self.root)['status'],'assessed')

    def test_installation_runs_explicit_assessor_before_index_failure(self):
        target=Path(self.tmp.name)/'install'
        agent=Path(self.tmp.name)/'assessor.py'
        agent.write_text("import json,sys; from pathlib import Path; c=json.loads(Path(sys.argv[1]).read_text()); print(json.dumps({'inventory_hash':c['inventory_hash'],'role_skills':{},'capabilities':[],'summary':'Installation assessment executed.'}))")
        argv=['harness','adopt',str(target),'--apply','--agent-command',
              json.dumps([sys.executable,str(agent),'{context}'])]
        with patch.object(sys,'argv',argv), patch('harnesslib.cli.installation.complete',return_value={'result':'BLOCKED','error':'fixture index unavailable'}), patch('builtins.print'):
            self.assertEqual(cli.main(),1)
        self.assertEqual(current(target)['status'],'assessed')
        self.assertEqual(current(target)['summary'],'Installation assessment executed.')
