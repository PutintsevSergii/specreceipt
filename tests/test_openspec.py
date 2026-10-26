"""OpenSpec contract and harness lifecycle. Set HARNESS_TEST_OPENSPEC for real CLI runs.

Only navigation index calls use the existing onboarding fixture's mocks.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import test_onboarding as onboarding_fixture
from harnesslib import openspec_tool as adapter
from harnesslib.storage import HarnessError, atomic, read


class OpenSpecTests(unittest.TestCase):
    def setUp(self):
        fixture=onboarding_fixture.OnboardingTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.prepare()
        self.fixture=fixture; self.root=fixture.root; self.h=fixture.h
        self.mapping=read(self.root/'specs/calculator/tasks.json')
        shutil.rmtree(self.root/'specs/calculator')
        self.mapping['tasks'][0]['approval_requirements']=[]
        atomic(self.root/'.harness/mapping.json',self.mapping)
        bin_dir=Path(fixture.tmp.name)/'bin'; bin_dir.mkdir()
        real=os.environ.get('HARNESS_TEST_OPENSPEC')
        if real:
            (bin_dir/'openspec').symlink_to(Path(real).resolve())
        else:
            executable=bin_dir/'openspec'
            executable.write_text('#!'+sys.executable+'''\nimport sys,json
from pathlib import Path
if '--version' in sys.argv: print('1.14.3')
elif sys.argv[1]=='init':
    p=Path('openspec/config.yaml');p.parent.mkdir(exist_ok=True);p.write_text('schema: spec-driven\\n')
elif sys.argv[1]=='validate':
    p=Path('openspec/changes')/sys.argv[2]/'specs/calculator/spec.md'
    good='#### Scenario:' in p.read_text()
    print(json.dumps({'valid':good}));sys.exit(0 if good else 1)
else: sys.exit(2)
''')
            executable.chmod(0o755)
        env=patch.dict(os.environ,{'PATH':str(bin_dir)+os.pathsep+os.environ['PATH']})
        env.start();self.addCleanup(env.stop)
        adapter.initialize(self.root)
        change=self.root/'openspec/changes/add-calculator'
        (change/'specs/calculator').mkdir(parents=True)
        (change/'proposal.md').write_text('# Calculator\n\n## Why\nUsers need addition.\n\n## What Changes\n- Add arithmetic.\n\n## Impact\n- calculator.py\n')
        (change/'design.md').write_text('# Design\nUse a pure addition function.\n')
        (change/'tasks.md').write_text('## 1. Implementation\n- [ ] 1.1 Implement addition and verify positive and negative inputs.\n')
        self.spec=change/'specs/calculator/spec.md'
        self.spec.write_text('## ADDED Requirements\n\n### Requirement: REQ-001 Addition\nThe system SHALL add integers correctly.\n\n#### Scenario: Positive inputs\n- **WHEN** adding 2 and 3\n- **THEN** return 5\n')

    def imported(self, approved=False):
        result=adapter.import_change(self.h,'add-calculator','.harness/mapping.json')
        if approved:
            for filename in ('spec.md','plan.md'):
                path=self.root/'specs/calculator'/filename
                path.write_text(path.read_text().replace('Status: DRAFT','Status: APPROVED').replace('Approval: TBD','Approval: isolated fixture developer reviewed the OpenSpec requirements and execution mapping'))
            self.fixture.approve()
        return result

    def test_import_keeps_single_source_and_draft_gates(self):
        self.imported()
        wrapper=(self.root/'specs/calculator/spec.md').read_text()
        self.assertNotIn('The system SHALL',wrapper)
        self.assertIn('Status: DRAFT',wrapper)
        self.assertEqual(self.h.validate()['result'],'PASS')
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','not approved')
        task=self.h.task('CALC-001')[1]
        self.assertIn('openspec-add-calculator',task['required_checks'])
        with self.assertRaises(HarnessError): self.imported()

    def test_real_execution_and_review_completion(self):
        self.imported(True)
        self.h.transition('CALC-001','IN_PROGRESS','fixture approval')
        self.h.transition('CALC-001','IMPLEMENTED','fixture implementation ready')
        evidence=self.h.verify('CALC-001')
        self.assertEqual(evidence['result'],'PASS')
        self.assertEqual({r['check'] for r in evidence['results']},{'application-unit','openspec-add-calculator'})
        self.h.transition('CALC-001','VERIFIED','both checks passed')
        review={'task_id':'CALC-001','reviewer':'isolated fixture reviewer',
                'evidence':self.h.task('CALC-001')[1]['evidence'][-1], 'verdict':'PASS',
                'summary':'Inspected arithmetic assertions and the bound OpenSpec requirements.', 'findings':[]}
        path=self.root/'specs/calculator/reviews/review.md';path.parent.mkdir()
        path.write_text('```harness-review\n'+json.dumps(review)+'\n```\n')
        self.h.approve('CALC-001','review','fixture reviewer','specs/calculator/reviews/review.md')
        self.h.transition('CALC-001','DONE','current execution and review passed')
        self.assertTrue(self.h.completed(self.h.task('CALC-001')[1]))
        self.spec.write_text(self.spec.read_text().replace('return 5','return 6'))
        self.assertFalse(self.h.completed(self.h.task('CALC-001')[1]))

    def test_source_change_blocks_until_refresh_and_new_approval(self):
        self.imported(True)
        self.spec.write_text(self.spec.read_text().replace('integers correctly','signed integers correctly'))
        with self.assertRaisesRegex(HarnessError,'sources changed'):
            self.h.ready(*self.h.task('CALC-001'))
        adapter.refresh(self.h,'calculator')
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','still draft')
        self.assertIn('Status: DRAFT',(self.root/'specs/calculator/spec.md').read_text())

    def test_validation_failure_and_unsafe_paths(self):
        self.spec.write_text('## ADDED Requirements\n### Requirement: REQ-001 Addition\nThe system SHALL add integers.\n')
        self.assertEqual(adapter.validate(self.root,'add-calculator')['result'],'FAIL')
        with self.assertRaises(HarnessError): self.imported()
        with self.assertRaises(HarnessError): adapter.context(self.root,'../../escape')
        self.spec.unlink();self.spec.symlink_to(self.root/'docs/TECH_SPEC.md')
        with self.assertRaises(HarnessError): adapter.context(self.root,'add-calculator')

    def test_validation_check_cannot_be_removed_or_replaced(self):
        self.imported(True)
        feature,task=self.h.task('CALC-001')
        task['required_checks'].remove('openspec-add-calculator')
        with self.assertRaises(HarnessError): adapter.ready(self.root,feature)
        feature,task=self.h.task('CALC-001')
        checks=read(self.root/'.harness/checks.json')
        checks['checks']['openspec-add-calculator']['argv']=['true']
        atomic(self.root/'.harness/checks.json',checks)
        with self.assertRaises(HarnessError): adapter.ready(self.root,feature)

    def test_generated_files_are_ignored_in_both_layers(self):
        subprocess.run(['git','init',str(self.root)],check=True,capture_output=True)
        adapter.ignores(self.root,['openspec/'])
        self.imported()
        result=subprocess.run(['git','-C',str(self.root),'check-ignore','openspec/config.yaml',
                               'specs/calculator/tasks.json'],check=True,capture_output=True,text=True)
        self.assertEqual(len(result.stdout.splitlines()),2)
        gitignore=(self.root/'.gitignore').read_text()
        exclude=(self.root/'.git/info/exclude').read_text()
        self.assertIn('/openspec/',gitignore);self.assertIn('/openspec/',exclude)

    def test_existing_config_is_preserved(self):
        config=self.root/'openspec/config.yaml'
        config.write_text('schema: spec-driven\n# corporate settings stay here\n')
        before=config.read_bytes()
        adapter.initialize(self.root)
        self.assertEqual(config.read_bytes(),before)

    def test_checkboxes_are_progress_not_acceptance_evidence(self):
        self.imported(True)
        before=self.h.binding()
        path=self.root/'openspec/changes/add-calculator/tasks.md'
        path.write_text(path.read_text().replace('[ ]','[x]'))
        self.assertEqual(self.h.binding(),before)
        self.assertEqual(self.h.task('CALC-001')[1]['status'],'TODO')
        self.assertFalse(self.h.current_evidence(self.h.task('CALC-001')[1]))
        self.h.ready(*self.h.task('CALC-001'))
