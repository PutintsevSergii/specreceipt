"""Real compact consumer lifecycle. Every developer answer is simulated fixture input."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from harnesslib.adopt import adopt
from harnesslib.core import Harness
from harnesslib import compact, runner, reporting
from harnesslib.storage import atomic, read, HarnessError

KIT=Path(__file__).resolve().parents[1]

class CompactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()/'consumer'; adopt(KIT,self.root,False); self.h=Harness(self.root)
        self.seed()

    def seed(self):
        (self.root/'calculator.py').write_text('def add(a,b):\n    return a-b\n')
        (self.root/'check_calculator.py').write_text('from calculator import add\nassert add(2,3)==5\nassert add(-2,2)==0\n')
        self.request={'feature_id':'calculator','task':{'id':'CALC-001','requirements':['REQ-1: Arithmetic sums'],
            'outcome':'Return the arithmetic sum','non_goals':['Do not change other operations'],
            'constraints':['Local arithmetic only'], 'scope':['calculator.py'],'dependencies':[],
            'acceptance_criteria':['Positive and signed inputs sum correctly'], 'failure_scenarios':['Subtraction yields wrong results'],
            'risk':'low','required_checks':['application-unit'],'approval_requirements':[],
            'acceptance_checks':[{'criterion':'Positive and signed inputs sum correctly','checks':['application-unit']}]},
            'context':{'intent':'Local arithmetic utility','runtime':'Python standard library','boundaries':'calculator.py exposes add',
                'safety_constraints':'Local computation only','intent_reference':'Fixture developer request for arithmetic',
                'blocking_decisions':[],'observed_facts':['Python function and local assertions inspected'],
                'developer_facts':['Fixture developer wants arithmetic sums'],'application_checks':['application-unit']},
            'checks':{'application-unit':{'kind':'command','argv':['{python}','-B','check_calculator.py'],'timeout_seconds':5,'purpose':'Positive and signed sums'}},
            'facts':{'critical_risk':False,'critical_unknowns':[],'unknowns':[],'public_api':False,'architecture_change':False,'components':1,'inspected':['calculator.py','check_calculator.py']}}

    def propose(self):
        return compact.proposal(self.h,self.request)
    def confirm(self,card=None):
        card=card or self.propose()
        (self.root/'.harness/initial.txt').write_text('Simulated fixture developer approves the displayed plan, context, commands and FAST profile.')
        return compact.confirm(self.h,'CALC-001','FAST','fixture developer','.harness/initial.txt',card['proposal_binding'])
    def advance(self): return runner.run(self.h,20,600)
    def implement(self):
        self.confirm(); role=self.advance()
        self.assertEqual(role['action'],'implement'); self.assertEqual(role['result'],'PASS')
        (self.root/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
        runner.submit(self.h,role['host_role']['request_id'],'fixture host')
        return self.advance()
    def reviewed(self):
        role=self.implement(); self.assertEqual(role['action'],'review')
        ref=role['host_role']['review_path']; p=self.root/ref; p.parent.mkdir(parents=True,exist_ok=True)
        t=self.h.task('CALC-001')[1]
        record={'task_id':t['id'],'reviewer':'fixture same-agent separate pass','evidence':t['evidence'][-1],'verdict':'PASS',
                'summary':'Inspected arithmetic change and the actual positive and signed assertions in a separate pass.','findings':[]}
        p.write_text('```harness-review\n'+json.dumps(record)+'\n```\n')
        runner.submit(self.h,role['host_role']['request_id'],'fixture host',ref)
        return self.advance()
    def test_real_compact_two_decision_lifecycle(self):
        action=self.reviewed(); self.assertEqual(action['action'],'approval')
        card=action['approval_package']; self.assertEqual(card['result'],'PASS')
        (self.root/'.harness/final.txt').write_text('Simulated fixture final acceptance of this displayed current result after review.')
        compact.accept(self.h,'CALC-001','fixture developer','.harness/final.txt',card['acceptance_binding'])
        self.assertEqual(self.h.task('CALC-001')[1]['status'],'DONE')
        self.assertEqual(self.h.validate()['result'],'PASS')
        self.assertFalse((self.root/'specs/calculator/spec.md').exists())
        self.assertFalse((self.root/'specs/calculator/plan.md').exists())
        self.assertEqual(self.h.task('CALC-001')[0]['revisions'],{})
    def test_request_is_not_consent_and_resume_does_not_reapprove(self):
        card=self.propose()
        with self.assertRaises(HarnessError): self.h.transition('CALC-001','IN_PROGRESS','request only')
        self.confirm(card); first=self.advance(); second=self.advance()
        self.assertEqual(first['host_role']['request_id'],second['host_role']['request_id'])
        self.assertEqual(self.h.task('CALC-001')[1]['workflow']['revision'],1)
    def test_material_change_and_wrong_final_token_rejected(self):
        card=self.propose(); f,t=self.h.task('CALC-001'); t['scope'].append('other.py'); atomic(self.root/'specs/calculator/tasks.json',f)
        with self.assertRaisesRegex(HarnessError,'stale'): self.confirm(card)
    def test_strict_unknown_and_legacy_are_not_shortcuts(self):
        atomic(self.root/'.harness/workflow-policy.json',{'minimum':'STRICT','experience':{'version':1,'mode':'compact'}})
        with self.assertRaisesRegex(HarnessError,'formal'): self.propose()
        atomic(self.root/'.harness/workflow-policy.json',{})
        with self.assertRaisesRegex(HarnessError,'Legacy'): self.propose()
        preview=compact.migration(self.h); self.assertEqual(read(self.root/'.harness/workflow-policy.json'),{})
        (self.root/'.harness/migrate.txt').write_text('Simulated fixture project migration approval after preview.')
        compact.migration(self.h,'fixture developer','.harness/migrate.txt',preview['binding'])
        self.request['facts']['critical_unknowns']=['Intent unresolved']; card=self.propose()
        with self.assertRaises(HarnessError): self.confirm(card)
    def test_outside_scope_and_review_mutation_rejected(self):
        self.confirm(); role=self.advance(); (self.root/'other.py').write_text('outside=True\n')
        with self.assertRaisesRegex(HarnessError,'outside'): runner.submit(self.h,role['host_role']['request_id'],'fixture host')
    def test_failed_check_repair_without_new_plan(self):
        self.confirm(); role=self.advance(); runner.submit(self.h,role['host_role']['request_id'],'fixture host')
        role=self.advance(); self.assertEqual(role['action'],'implement'); self.assertEqual(role['run']['failures'],1)
        (self.root/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
        runner.submit(self.h,role['host_role']['request_id'],'fixture host'); self.assertEqual(self.advance()['action'],'review')
    def test_stale_final_acceptance_cannot_finish(self):
        action=self.reviewed(); (self.root/'.harness/final.txt').write_text('Simulated fixture acceptance.')
        (self.root/'calculator.py').write_text('def add(a,b):\n    return a-b\n')
        with self.assertRaisesRegex(HarnessError,'stale'): compact.accept(self.h,'CALC-001','fixture','.harness/final.txt',action['approval_package']['acceptance_binding'])
    def test_reports_do_not_invalidate_evidence(self):
        self.reviewed(); before=self.h.binding(); reporting.report(self.h,'CALC-001',retain=True)
        self.assertEqual(before,self.h.binding()); self.assertTrue(self.h.current_evidence(self.h.task('CALC-001')[1]))
    def test_policy_versions_fail_closed(self):
        atomic(self.root/'.harness/workflow-policy.json',{'experience':{'version':2,'mode':'compact'}})
        with self.assertRaisesRegex(HarnessError,'Unsupported'): self.propose()
    def test_without_any_full_documents(self):
        self.propose()
        for rel in ['docs/TECH_SPEC.md','docs/ARCHITECTURE.md','docs/DECISION_QUEUE.md']: (self.root/rel).unlink()
        self.confirm(compact.plan_card(self.h,'CALC-001'))
        self.assertEqual(self.advance()['action'],'implement')
    def test_renewal_preserves_source_baseline_and_combines_decision(self):
        self.confirm(); self.advance()
        self.request.pop('context'); self.request['task']['scope'].append('extra.py')
        card=self.propose(); self.assertEqual(self.h.task('CALC-001')[1]['status'],'REWORK')
        self.confirm(card); self.assertEqual(self.advance()['action'],'implement')
        self.assertIn('extra.py',self.h.task('CALC-001')[1]['scope'])
    def test_progress_fields_do_not_invalidate_plan_or_evidence(self):
        self.reviewed(); before=self.h.binding(); f,t=self.h.task('CALC-001')
        t['next_action']='Presentation note'; t['workflow']['at']='presentation timestamp'; t['workflow']['plan']='Derived rendering only'
        atomic(self.root/'specs/calculator/tasks.json',f)
        self.assertEqual(before,self.h.binding()); self.assertTrue(self.h.current_evidence(t))
        self.h.ready(f,t)
    def test_new_check_and_instructions_require_renewal(self):
        self.confirm(); self.advance(); f,t=self.h.task('CALC-001')
        cfg=read(self.root/'.harness/checks.json'); cfg['checks']['application-unit']['argv']=['{python}','-c','print(42)']; atomic(self.root/'.harness/checks.json',cfg)
        self.assertEqual(self.advance()['result'],'BLOCKED')
    def test_approval_bound_to_task_attempt_even_via_low_level(self):
        action=self.reviewed()
        with self.assertRaisesRegex(HarnessError,'binding'): self.h.approve('CALC-001','developer','fixture','.harness/initial.txt')
        with self.assertRaisesRegex(HarnessError,'stale'): compact.accept(self.h,'CALC-001','fixture','.harness/initial.txt','other-task-token')
    def test_host_review_cannot_edit_source_or_replay(self):
        role=self.implement(); (self.root/'calculator.py').write_text('def add(a,b):\n    return b+a\n')
        with self.assertRaises(HarnessError): runner.submit(self.h,role['host_role']['request_id'],'fixture host',role['host_role']['review_path'])
    def test_uncertain_command_and_exhausted_budget_block(self):
        self.confirm(); self.advance(); state=self.h.state(); state['active_operation']={'kind':'verification','id':'fixture-interrupted'}; atomic(self.root/'.harness/state.json',state)
        with self.assertRaisesRegex(HarnessError,'interrupted'): self.advance()
        self.assertIsNotNone(self.h.state()['uncertain_outcome'])
    def test_no_full_document_needed_through_done(self):
        self.propose()
        for rel in ['docs/TECH_SPEC.md','docs/ARCHITECTURE.md','docs/DECISION_QUEUE.md']: (self.root/rel).unlink()
        self.confirm(compact.plan_card(self.h,'CALC-001')); role=self.advance()
        (self.root/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
        runner.submit(self.h,role['host_role']['request_id'],'fixture host'); role=self.advance()
        self.assertEqual(role['action'],'review')
        self.assertEqual(self.h.validate()['result'],'PASS')
    def test_missing_case_cannot_become_acceptance(self):
        self.request['task']['acceptance_checks'][0]['required_cases']=[{'check':'application-unit','cases':['missing.case']}]
        self.confirm(); role=self.advance(); (self.root/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
        runner.submit(self.h,role['host_role']['request_id'],'fixture host'); role=self.advance()
        self.assertNotEqual(role['action'],'approval'); t=self.h.task('CALC-001')[1]
        ev=self.h.evidence(t['evidence'][-1]); self.assertEqual(ev['results'][0]['result'],'PASS')
        self.assertFalse(self.h.current_evidence(t))
    def test_budget_limit_blocks_host_submission_and_uncertainty(self):
        self.confirm(); role=runner.run(self.h,2,600)
        # Start used one step; host submission uses the remaining step.
        runner.submit(self.h,role['host_role']['request_id'],'fixture host')
        self.assertEqual(runner.run(self.h,2,600)['action'],'budget-exhausted')
    def test_two_tasks_require_explicit_selection(self):
        self.propose(); request=json.loads(json.dumps(self.request)); request['feature_id']='second'; request['task']['id']='CALC-002'; request.pop('context'); request.pop('checks')
        compact.proposal(self.h,request)
        self.assertEqual(runner.next_action(self.h)['action'],'select-task')
        with self.assertRaises(HarnessError): self.h.transition('CALC-002','IN_PROGRESS','fixture initial request is not approval')
    def test_review_failure_is_repair_not_developer_decision(self):
        role=self.implement(); ref=role['host_role']['review_path']; p=self.root/ref; p.parent.mkdir(parents=True,exist_ok=True)
        t=self.h.task('CALC-001')[1]
        record={'task_id':t['id'],'reviewer':'fixture same-host','evidence':t['evidence'][-1],'verdict':'CHANGES_REQUESTED',
                'summary':'Fixture separate review requests a clearer implementation before acceptance.','findings':[]}
        p.write_text('```harness-review\n'+json.dumps(record)+'\n```\n')
        runner.submit(self.h,role['host_role']['request_id'],'fixture host',ref)
        self.assertEqual(self.advance()['action'],'implement')
    def test_final_cannot_reuse_initial_answer_reference(self):
        card=self.reviewed()['approval_package']
        with self.assertRaisesRegex(HarnessError,'separate current final'):
            compact.accept(self.h,'CALC-001','fixture','.harness/initial.txt',card['acceptance_binding'])
    def test_boolean_policy_version_is_not_version_one(self):
        atomic(self.root/'.harness/workflow-policy.json',{'experience':{'version':True,'mode':'compact'}})
        with self.assertRaisesRegex(HarnessError,'Unsupported'): self.propose()
    def test_new_run_reissues_host_request_without_reapproving(self):
        self.confirm(); first=self.advance(); second=runner.run(self.h,20,600,new_run=True)
        self.assertNotEqual(first['host_role']['request_id'],second['host_role']['request_id'])
        with self.assertRaisesRegex(HarnessError,'stale'): runner.submit(self.h,first['host_role']['request_id'],'fixture host')
        runner.submit(self.h,second['host_role']['request_id'],'fixture host')
