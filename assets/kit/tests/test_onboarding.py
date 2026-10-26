"""Application work stays gated until the documented intake has current approval."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from harnesslib.adopt import adopt
from harnesslib.core import Harness
from harnesslib import readiness
from harnesslib.storage import HarnessError, atomic, read

KIT = Path(__file__).resolve().parents[1]

class OnboardingTests(unittest.TestCase):
    def setUp(self):
        collect = patch('harnesslib.index_context.collect', return_value={'result':'PASS','reference':'fixture-navigation'})
        ensure = patch('harnesslib.index_context.ensure', return_value={'result':'PASS'})
        self.collect_mock = collect.start(); self.ensure_mock = ensure.start()
        self.addCleanup(collect.stop); self.addCleanup(ensure.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()/'project'
        adopt(KIT,self.root,False)
        self.h = Harness(self.root)
        self.h.init()

    def prepare(self):
        for rel, sections in readiness.SECTIONS.items():
            text='Status: APPROVED\nRevision: 1\nApproval: isolated developer fixture\n'
            for section in sections:
                text+=f'\n## {section}\nFixture decision for {section}: a local addition function with no remote services.\n'
            if rel.endswith('TECH_SPEC.md'): text+='\nREQ-001: Add two input numbers accurately.\n'
            (self.root/rel).write_text(text)
        p=self.root/'docs/DECISION_QUEUE.md'
        p.write_text(p.read_text().replace('| APP-001 | OPEN |','| APP-001 | RESOLVED |'))
        (self.root/'calculator.py').write_text('def add(a, b):\n    return a + b\n')
        (self.root/'check_calculator.py').write_text('from calculator import add\nassert add(2, 3) == 5\nassert add(-2, 2) == 0\n')
        cfg=read(self.root/'.harness/checks.json'); cfg['stack_revision']='1'
        cfg['checks']['application-unit']={'kind':'command','argv':['{python}','-B','check_calculator.py'],
            'timeout_seconds':5,'approved':True,'approval_reference':'Isolated fixture developer authorizes local assertions','purpose':'Check positive and signed addition behavior'}
        atomic(self.root/'.harness/checks.json',cfg)
        atomic(self.root/'.harness/environment.json',{'application_runtime':'Python fixture runtime; no external services'})
        record=read(self.root/'.harness/onboarding.json'); record['mode']='EXISTING'
        record['sources']=[{'id':'human-1','kind':'human','reference':'Fixture developer answer: local arithmetic only','authorization':'Fixture developer provided this answer'},
                           {'id':'code-1','kind':'repository','reference':'calculator.py','authorization':'Fixture developer requested repository inspection'}]
        for topic, value in record['coverage'].items():
            value.update(status='RESOLVED',rationale=f'Reviewed {topic} decision in the canonical fixture documents.',source_ids=['human-1','code-1'])
        record['application_checks']=['application-unit']; atomic(self.root/'.harness/onboarding.json',record)
        dest=self.root/'specs/calculator'; dest.mkdir(parents=True)
        for name in ['spec.md','plan.md']:
            (dest/name).write_text('Status: APPROVED\nRevision: 1\nApproval: isolated developer fixture\nTech-Spec-Revision: 1\nArchitecture-Revision: 1\n\nREQ-001: Addition\nAC-001: Positive and negative inputs produce arithmetic sums.\n')
        (dest/'verification.md').write_text('Verification has not run yet.\n')
        f=read(self.root/'templates/feature/tasks.json'); f.update(feature_id='calculator',revisions={'tech_spec':'1','architecture':'1'})
        t=f['tasks'][0]; t.pop('workflow_required',None)  # Exercise legacy Strict onboarding records.
        t.update(id='CALC-001',requirements=['REQ-001'],outcome='Return the arithmetic sum.',scope=['calculator.py'],
                                 acceptance_criteria=['AC-001: Positive and negative inputs sum correctly.'],failure_scenarios=['Wrong sign produces an incorrect sum.'],
                                 required_checks=['application-unit'],approval_requirements=[])
        t['acceptance_checks']=[{'criterion':c,'checks':['application-unit']} for c in t['acceptance_criteria']]
        atomic(dest/'tasks.json',f)
        (self.root/'docs/approval.md').write_text('Fixture developer reviewed the canonical documents, intake coverage and application checks and approves implementation planning.\n')

    def approve(self):
        return self.h.approve_onboarding('Fixture developer','docs/approval.md')

    def test_fresh_kit_blocks_application_with_actionable_gaps(self):
        report=readiness.report(self.h)
        self.assertEqual(report['result'],'BLOCKED')
        self.assertTrue(any('purpose' in x for x in report['blockers']))
        self.assertFalse(self.h.application_ready())
        self.assertEqual(self.h.validate()['result'],'PASS')

    def test_headers_and_no_placeholders_are_not_enough(self):
        self.prepare()
        self.assertFalse(self.h.application_ready())
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','no review')

    def test_ready_application_lifecycle_uses_real_check(self):
        self.prepare(); self.assertEqual(self.approve()['result'],'PASS')
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'PASS')
        started = self.h.transition('CALC-001','IN_PROGRESS','approved')
        self.assertEqual(started['navigation_context']['reference'],'fixture-navigation')
        self.collect_mock.assert_called_once()
        self.h.transition('CALC-001','IMPLEMENTED','fixture implementation')
        evidence=self.h.verify('CALC-001')
        self.assertEqual(self.ensure_mock.call_count,2)
        self.assertEqual(evidence['result'],'PASS')
        self.h.transition('CALC-001','VERIFIED','current application assertions')

    def test_each_documentation_topic_must_be_resolved(self):
        self.prepare(); original=read(self.root/'.harness/onboarding.json')
        for topic in original['coverage']:
            with self.subTest(topic=topic):
                record=copy.deepcopy(original); record['coverage'][topic]['status']='OPEN'
                atomic(self.root/'.harness/onboarding.json',record)
                with self.assertRaises(HarnessError): self.approve()
        atomic(self.root/'.harness/onboarding.json',original)

    def test_blank_sections_block_even_with_approved_header(self):
        self.prepare(); p=self.root/'docs/ARCHITECTURE.md'; text=p.read_text()
        text=text.replace('Fixture decision for Security: a local addition function with no remote services.','')
        text=text.replace('Fixture decision for Recovery: a local addition function with no remote services.','<!-- fill this later -->')
        p.write_text(text)
        with self.assertRaises(HarnessError): self.approve()
        self.assertTrue(any('Recovery' in x for x in readiness.report(self.h)['blockers']))

    def test_blocking_decision_including_deferred_blocks_approval(self):
        self.prepare(); p=self.root/'docs/DECISION_QUEUE.md'
        p.write_text(p.read_text().replace('| APP-001 | RESOLVED |','| APP-001 | DEFERRED |'))
        with self.assertRaises(HarnessError): self.approve()

    def test_missing_decision_table_is_not_silently_accepted(self):
        self.prepare(); (self.root/'docs/DECISION_QUEUE.md').write_text('No structured decision assessment.')
        with self.assertRaises(HarnessError): self.approve()

    def test_sources_must_include_human_and_resolve_topic_references(self):
        self.prepare(); record=read(self.root/'.harness/onboarding.json')
        record['sources']=record['sources'][1:]
        atomic(self.root/'.harness/onboarding.json',record)
        with self.assertRaises(HarnessError): self.approve()
        self.assertTrue(any('developer-provided intent' in x for x in readiness.report(self.h)['blockers']))

    def test_missing_repository_source_blocks(self):
        self.prepare(); (self.root/'calculator.py').unlink()
        with self.assertRaises(HarnessError): self.approve()

    def test_application_checks_cannot_be_only_harness_checks(self):
        self.prepare(); r=read(self.root/'.harness/onboarding.json'); r['application_checks']=['harness-tests']
        atomic(self.root/'.harness/onboarding.json',r)
        with self.assertRaises(HarnessError): self.approve()

    def test_approved_baseline_cannot_be_omitted_from_task(self):
        self.prepare(); self.approve()
        p=self.root/'specs/calculator/tasks.json'; f=read(p); f['tasks'][0]['required_checks']=['harness-validate']; atomic(p,f)
        self.assertTrue(self.h.application_ready())
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'BLOCKED')
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','omitted baseline')

    def test_task_placeholders_block_start(self):
        self.prepare(); self.approve()
        p=self.root/'specs/calculator/tasks.json'; f=read(p); f['tasks'][0]['outcome']='TODO'; atomic(p,f)
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','incomplete task')

    def test_document_edit_revokes_readiness_without_revision_bump(self):
        self.prepare(); self.approve(); self.h.transition('CALC-001','IN_PROGRESS','approved')
        p=self.root/'docs/TECH_SPEC.md'; p.write_text(p.read_text()+'\nAdditional decision.\n')
        self.assertFalse(self.h.application_ready())
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IMPLEMENTED','stale approval')

    def test_reference_edit_revokes_approval(self):
        self.prepare(); self.approve()
        (self.root/'docs/approval.md').write_text('Developer withdraws approval pending review.')
        self.assertFalse(self.h.application_ready())

    def test_code_edits_do_not_revoke_documentation_approval(self):
        self.prepare(); self.approve()
        (self.root/'calculator.py').write_text('def add(a, b):\n    return sum((a, b))\n')
        self.assertTrue(self.h.application_ready())

    def test_verify_rechecks_documentation_gate(self):
        self.prepare(); self.approve()
        self.h.transition('CALC-001','IN_PROGRESS','approved'); self.h.transition('CALC-001','IMPLEMENTED','implemented')
        r=read(self.root/'.harness/onboarding.json'); r['coverage']['security']['status']='OPEN'; atomic(self.root/'.harness/onboarding.json',r)
        with self.assertRaises(HarnessError): self.h.verify('CALC-001')

    def test_readiness_cli_is_read_only_and_exits_nonzero_when_blocked(self):
        before=(self.root/'.harness/state.json').read_bytes(),(self.root/'.harness/events.jsonl').read_bytes()
        p=subprocess.run([sys.executable,str(self.root/'harness'),'readiness'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout)['result'],'BLOCKED')
        self.assertEqual(before,((self.root/'.harness/state.json').read_bytes(),(self.root/'.harness/events.jsonl').read_bytes()))

    def test_approval_survives_new_session(self):
        self.prepare(); self.approve()
        self.assertTrue(Harness(self.root).application_ready())

    def test_adoption_does_not_inherit_intake_answers_or_approval(self):
        self.prepare(); self.approve()
        target=Path(self.tmp.name).resolve()/'another-project'
        adopt(self.root,target,False)
        intake=read(target/'.harness/onboarding.json')
        self.assertEqual(intake,read(self.root/'templates/onboarding.json'))
        self.assertEqual(intake['sources'],[])
        self.assertIsNone(intake['approval'])

    def test_unapproved_baseline_command_blocks_approval(self):
        self.prepare(); cfg=read(self.root/'.harness/checks.json')
        cfg['checks']['application-unit']['approved']=False
        atomic(self.root/'.harness/checks.json',cfg)
        with self.assertRaises(HarnessError): self.approve()

    def test_missing_onboarding_record_blocks_legacy_project(self):
        self.prepare(); (self.root/'.harness/onboarding.json').unlink()
        self.assertFalse(self.h.application_ready())
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','missing intake')

    def test_approval_record_is_journaled(self):
        self.prepare(); self.approve()
        event_lines=(self.root/'.harness/events.jsonl').read_text().splitlines()
        self.assertTrue(any(json.loads(line)['type']=='onboarding-approved' for line in event_lines))
        self.assertFalse((self.root/'.harness/transaction.json').exists())

    def test_unconfigured_environment_blocks_approval(self):
        self.prepare()
        atomic(self.root/'.harness/environment.json',{'application_runtime':'UNCONFIGURED'})
        with self.assertRaises(HarnessError): self.approve()

    def test_source_removal_after_approval_does_not_revoke_documentation(self):
        self.prepare(); self.approve()
        (self.root/'calculator.py').unlink()
        self.assertTrue(self.h.application_ready())
        # Execution still fails: current documentation approval is not test evidence.
        self.h.transition('CALC-001','IN_PROGRESS','approved refactor')
        self.h.transition('CALC-001','IMPLEMENTED','missing implementation fixture')
        self.assertEqual(self.h.verify('CALC-001')['result'],'FAIL')

    def test_new_project_can_use_human_answers_without_existing_application(self):
        self.prepare()
        r=read(self.root/'.harness/onboarding.json'); r['mode']='NEW'; r['sources']=r['sources'][:1]
        for topic in r['coverage'].values(): topic['source_ids']=['human-1']
        atomic(self.root/'.harness/onboarding.json',r)
        (self.root/'calculator.py').unlink(); (self.root/'check_calculator.py').unlink()
        self.assertEqual(self.approve()['result'],'PASS')
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'PASS')
        self.h.transition('CALC-001','IN_PROGRESS','approved first implementation')
        self.assertFalse((self.root/'calculator.py').exists())

    def test_project_approval_does_not_approve_draft_feature(self):
        self.prepare(); self.approve()
        p=self.root/'specs/calculator/plan.md'; p.write_text(p.read_text().replace('Status: APPROVED','Status: DRAFT'))
        self.assertTrue(self.h.application_ready())
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'BLOCKED')
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','draft feature')

    def test_task_report_handles_invalid_intake_and_check_shapes(self):
        self.prepare()
        r=read(self.root/'.harness/onboarding.json'); r['application_checks']=3
        atomic(self.root/'.harness/onboarding.json',r)
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'BLOCKED')
        cfg=read(self.root/'.harness/checks.json'); cfg['checks']=[]
        atomic(self.root/'.harness/checks.json',cfg)
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'BLOCKED')

    def test_malformed_intake_fails_closed(self):
        atomic(self.root/'.harness/onboarding.json',{'approval':True})
        self.assertEqual(readiness.report(self.h)['result'],'BLOCKED')
        with self.assertRaises(HarnessError): self.h.validate()

if __name__=='__main__': unittest.main()
