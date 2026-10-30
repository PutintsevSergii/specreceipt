"""Current reports versus immutable history; isolated fixture approvals only."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_harness
from harnesslib import reporting, runner
from harnesslib.storage import atomic, read, HarnessError


class ReportingTests(unittest.TestCase):
    setUp = test_harness.HarnessTests.setUp
    implemented = test_harness.HarnessTests.implemented
    verified = test_harness.HarnessTests.verified
    review_text = test_harness.HarnessTests.review_text

    def current(self):
        return read(self.root/'.harness/reports/current.json')['tasks'][0]

    def review(self):
        p = self.root/'specs/harness-demo/reviews/review.md'
        p.parent.mkdir(exist_ok=True)
        p.write_text(self.review_text())
        self.h.approve('DEMO-001','review','isolated fixture','specs/harness-demo/reviews/review.md')

    def test_verified_done_refresh_preserves_historical_snapshot(self):
        self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        self.h.transition('DEMO-001','IMPLEMENTED','Implementation complete; verification pending.')
        snapshot = reporting.report(self.h,'DEMO-001',retain=True)
        dest = Path(snapshot['tasks'][0]['paths']['review_package'])
        before = {p.name:p.read_bytes() for p in dest.glob('report.*')}
        self.assertEqual(snapshot['report_kind'],'historical')
        self.assertIn('Historical snapshot:',(dest/'report.md').read_text())
        self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')
        self.h.transition('DEMO-001','VERIFIED','checks pass')
        r = self.current()
        self.assertEqual(r['status'],'VERIFIED')
        self.assertNotIn('pending',r['implementation_summary'])
        self.assertEqual(r['verification']['status'],'PASS')
        self.assertEqual(r['next_action']['action'],'review')
        self.assertEqual(r['implementation_history']['state'],'IMPLEMENTED')
        self.assertTrue(r['implementation_history']['recorded_at'])
        self.assertIn('Historical implementation note [IMPLEMENTED at ',(self.root/'.harness/reports/current.md').read_text())
        self.review()
        self.assertEqual(self.current()['next_action']['action'],'complete')
        self.assertEqual(runner.next_action(self.h)['next_action'],reporting.task_report(self.h,'DEMO-001')['next_action'])
        self.h.transition('DEMO-001','DONE','fixture review complete')
        self.assertEqual(self.current()['next_action']['action'],'finished')
        self.assertTrue(self.h.current_evidence(self.h.task('DEMO-001')[1]))
        self.assertEqual(before,{p.name:p.read_bytes() for p in dest.glob('report.*')})

    def test_final_approval_remains_missing_and_review_can_be_invalid(self):
        f,t=self.h.task('DEMO-001');t['approval_requirements']=['developer'];atomic(self.root/'specs/harness-demo/tasks.json',f)
        self.verified(); self.review()
        self.assertEqual(self.current()['next_action']['action'],'approval')
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','DONE','without developer')
        p=self.root/'specs/harness-demo/reviews/review.md';p.write_text(p.read_text().replace('PASS','CHANGES_REQUESTED'))
        r=reporting.task_report(self.h,'DEMO-001')
        self.assertEqual(r['approvals']['review']['status'],'STALE')
        self.assertEqual(r['next_action']['action'],'review')

    def test_approval_package_links_exact_current_result_without_writes(self):
        f,t=self.h.task('DEMO-001');t['approval_requirements']=['developer'];atomic(self.root/'specs/harness-demo/tasks.json',f)
        self.h.transition('DEMO-001','IN_PROGRESS','fixture start')
        (self.root/'docs/DEMO.md').write_text('Use checkpoint then resume to reconcile. Approved change.\n')
        self.h.transition('DEMO-001','IMPLEMENTED','fixture implemented')
        self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')
        self.h.transition('DEMO-001','VERIFIED','fixture evidence')
        self.review()
        before = {p:p.read_bytes() for p in (self.root/'.harness/state.json',self.root/'.harness/events.jsonl',self.root/'specs/harness-demo/tasks.json')}
        package = reporting.approval_package(self.h,'DEMO-001')
        self.assertEqual(package['result'],'PASS')
        self.assertEqual(package['review_verdict'],'PASS')
        self.assertEqual(package['paths']['spec'],str(self.h.root/'specs/harness-demo/spec.md'))
        self.assertEqual(package['paths']['plan'],str(self.h.root/'specs/harness-demo/plan.md'))
        self.assertTrue(Path(package['paths']['evidence']).exists())
        self.assertTrue(Path(package['paths']['review']).exists())
        self.assertIn('DEMO-001',package['approval_effect'])
        self.assertIn('publication',package['approval_effect'])
        self.assertEqual(package['changed_files'][0]['path'],'docs/DEMO.md')
        markdown=reporting.approval_package(self.h,'DEMO-001','markdown')['text']
        self.assertIn('[Spec](<'+str(self.h.root/'specs/harness-demo/spec.md')+'>)',markdown)
        self.assertIn('[Evidence](<'+package['paths']['evidence']+'>)',markdown)
        self.assertIn('[docs/DEMO.md (modified, task scope)](<'+str(self.h.root/'docs/DEMO.md')+'>)',markdown)
        self.assertIn('Limits:',markdown)
        next_result=runner.next_action(self.h)
        self.assertEqual(next_result['action'],'approval')
        self.assertEqual(next_result['approval_package']['task_id'],'DEMO-001')
        self.assertIn('approval-package DEMO-001',next_result['next_action']['command'])
        cmd=[sys.executable,'-B',str(self.root/'harness'),'--root',str(self.root),'approval-package','DEMO-001','--format','markdown']
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('[Review](<'+package['paths']['review']+'>)',result.stdout)
        terminal=subprocess.run(cmd[:-1]+['terminal'],capture_output=True,text=True)
        self.assertEqual(terminal.returncode,0,terminal.stderr)
        self.assertIn('[Review](<'+package['paths']['review']+'>)',terminal.stdout)
        structured=subprocess.run(cmd[:-2],capture_output=True,text=True)
        self.assertEqual(structured.returncode,0,structured.stderr)
        self.assertEqual(json.loads(structured.stdout)['paths']['review'],package['paths']['review'])
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_approval_package_blocks_missing_review_stale_evidence_and_wrong_phase(self):
        f,t=self.h.task('DEMO-001');t['approval_requirements']=['developer'];atomic(self.root/'specs/harness-demo/tasks.json',f)
        self.assertEqual(reporting.approval_package(self.h,'DEMO-001')['result'],'BLOCKED')
        self.verified()
        self.assertEqual(reporting.approval_package(self.h,'DEMO-001')['result'],'BLOCKED')
        self.review()
        review=self.root/'specs/harness-demo/reviews/review.md'
        review.write_text(review.read_text()+'changed')
        self.assertEqual(reporting.approval_package(self.h,'DEMO-001')['result'],'BLOCKED')
        self.review()
        (self.root/'docs/DEMO.md').write_text('checkpoint and resume changed')
        self.assertEqual(reporting.approval_package(self.h,'DEMO-001')['result'],'BLOCKED')

    def test_done_regression_uses_latest_evidence_without_undoing_completion(self):
        self.verified(); self.review(); self.h.transition('DEMO-001','DONE','fixture')
        (self.root/'docs/DEMO.md').write_text('checkpoint and resume: updated explanation')
        r=reporting.task_report(self.h,'DEMO-001')
        self.assertEqual(r['effective_status'],'DONE')
        self.assertEqual(r['next_action']['action'],'regression')
        ev=self.h.verify('DEMO-001',regression=True)
        r=self.current()
        self.assertEqual(r['verification']['status'],'PASS')
        self.assertTrue(r['paths']['evidence'].endswith(ev['id']+'.json'))
        self.assertEqual(r['approvals']['review']['completion_status'],'ACCEPTED_AT_DONE')

    def test_stale_verified_report_agrees_with_core(self):
        self.verified(); (self.root/'docs/DEMO.md').write_text('checkpoint and resume changed')
        r=reporting.task_report(self.h,'DEMO-001')
        state=self.h.status()
        self.assertEqual(r['effective_status'],'REWORK')
        self.assertEqual(state['tasks'][0]['next_action'],r['next_action']['message'])
        self.assertEqual(state['state']['next_action'],r['next_action']['message'])
        self.h.reconcile()
        self.assertEqual(self.current()['effective_status'],'REWORK')

    def test_refresh_failure_does_not_reverse_committed_transition(self):
        with patch.object(reporting,'report',side_effect=OSError('fixture disk failure')), contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'IN_PROGRESS')
        self.assertIn('lifecycle committed',stderr.getvalue())
        self.assertEqual(read(self.root/'.harness/reports/refresh-error.json')['status'],'STALE')
        reporting.refresh_current(self.h)
        self.assertFalse((self.root/'.harness/reports/refresh-error.json').exists())

    def test_exact_authorized_maintenance_paths_only(self):
        f,t=self.h.task('DEMO-001')
        for p in ['src/copilot.ts','src/core.ts','src/engine.ts','scripts/test-codex-e2e.mjs','scripts/test-copilot-e2e.mjs']:
            self.h.ready(f,{**t,'scope':[p]})
        for p in ['src/','src/application.ts','scripts/unapproved.mjs']:
            with self.assertRaises(HarnessError): self.h.ready(f,{**t,'scope':[p]})

    def test_bounded_assessment_invalidates_cache_without_full_inventory(self):
        from harnesslib import workflow
        self.h.checkpoint()
        atomic(self.root/'.harness/facts.json',{'critical_risk':False,'critical_unknowns':[],'unknowns':[],'public_api':False,'architecture_change':False,'components':1,'inspected':['docs/DEMO.md']})
        with patch.object(self.h,'fingerprints',side_effect=AssertionError('bounded assessment must not inventory')):
            workflow.assess(self.h,'DEMO-001','.harness/facts.json')
        cache=read(self.root/'.harness/reports/current.json')
        self.assertEqual(cache['report_kind'],'stale')
        self.assertEqual(cache['tasks'],[])
        self.assertIn('Stale derived report',(self.root/'.harness/reports/current.md').read_text())

    def test_interrupted_operation_refreshes_recovery_action(self):
        self.implemented()
        state=self.h.state()
        state['active_operation']={'id':'fixture','kind':'verification','task':'DEMO-001','started_at':'2026-01-01T00:00:00+00:00','pid':99999999}
        atomic(self.root/'.harness/state.json',state)
        self.assertEqual(reporting.task_report(self.h,'DEMO-001')['next_action']['action'],'progress')
        self.h.reconcile()
        self.assertEqual(self.current()['next_action']['action'],'recover')
