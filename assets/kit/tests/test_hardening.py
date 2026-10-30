from platform_support import symlink
"""Counterexamples from the audit and real multi-task/adapter lifecycle regressions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import test_harness
import test_onboarding
from harnesslib import runner, readiness, verification
from harnesslib.storage import HarnessError, atomic, read, digest

class HardeningTests(unittest.TestCase):
    def setUp(self):
        fixture=test_harness.HarnessTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.h,self.root,self.fixture=fixture.h,fixture.root,fixture

    def write_tasks(self,f): atomic(self.root/'specs/harness-demo/tasks.json',f)

    def test_exact_product_maintenance_paths_start_without_broadening_scope(self):
        for scope in ['src/integrations.ts', 'src/doctor.ts', 'scripts/test-package.mjs']:
            with self.subTest(scope=scope):
                fixture = test_harness.HarnessTests()
                fixture.setUp(); self.addCleanup(fixture.doCleanups)
                f, t = fixture.h.task('DEMO-001'); t['scope'] = [scope]
                atomic(fixture.root/'specs/harness-demo/tasks.json', f)
                fixture.h.transition('DEMO-001', 'IN_PROGRESS', 'isolated scope regression')
                self.assertEqual(fixture.h.task('DEMO-001')[1]['status'], 'IN_PROGRESS')

    def test_product_maintenance_scope_rejects_unrelated_paths_and_aliases(self):
        paths = ['src/', 'scripts/', 'src/application.ts', 'scripts/unrelated.mjs',
                 'src/integrations.ts.extra', 'src/doctor.ts/child',
                 'src/integrations.ts/', './src/integrations.ts',
                 'src//integrations.ts', 'src/./integrations.ts',
                 'src/../src/integrations.ts', 'docs/../src/integrations.ts',
                 'docs/../../outside.ts', 'src/Integrations.ts',
                 'src\\integrations.ts', 'src/*', '/src/integrations.ts']
        for scope in paths:
            with self.subTest(scope=scope):
                f, t = self.h.task('DEMO-001'); t['scope'] = [scope]; self.write_tasks(f)
                with self.assertRaises(HarnessError):
                    self.h.transition('DEMO-001', 'IN_PROGRESS', 'isolated rejection regression')
                self.assertEqual(self.h.task('DEMO-001')[1]['status'], 'TODO')

    def test_product_maintenance_scope_rejects_symlink_file_and_directory(self):
        src = self.root/'src'; src.mkdir()
        alias = src/'integrations.ts'; symlink(alias, self.root/'docs/DEMO.md')
        f, t = self.h.task('DEMO-001'); t['scope'] = ['src/integrations.ts']; self.write_tasks(f)
        with self.assertRaisesRegex(HarnessError, 'Symlink'):
            self.h.transition('DEMO-001', 'IN_PROGRESS', 'isolated alias regression')
        alias.unlink(); src.rmdir(); symlink(src, self.root/'docs', target_is_directory=True)
        with self.assertRaisesRegex(HarnessError, 'Symlink'):
            self.h.transition('DEMO-001', 'IN_PROGRESS', 'isolated directory alias regression')

    def pair(self):
        f,a=self.h.task('DEMO-001'); b=copy.deepcopy(a)
        b.update(id='DEMO-002',dependencies=['DEMO-001'])
        f['tasks'].append(b); self.write_tasks(f)

    def review(self, ident='DEMO-001', findings=None, verdict='PASS'):
        t=self.h.task(ident)[1]
        p=self.root/f'specs/harness-demo/reviews/{ident}.md'; p.parent.mkdir(exist_ok=True)
        record={'task_id':ident,'reviewer':'isolated reviewer','evidence':t['evidence'][-1],
                'summary':'Inspected behavior against fixture requirements.','verdict':verdict,'findings':findings or []}
        p.write_text('```harness-review\n'+json.dumps(record)+'\n```\n')
        self.h.approve(ident,'review','isolated reviewer',p.relative_to(self.root).as_posix())

    def finish(self, ident='DEMO-001'):
        self.h.transition(ident,'IN_PROGRESS','fixture')
        self.h.transition(ident,'IMPLEMENTED','fixture')
        self.assertEqual(self.h.verify(ident)['result'],'PASS')
        self.h.transition(ident,'VERIFIED','fixture'); self.review(ident)
        self.h.transition(ident,'DONE','fixture')

    def test_dependency_chain_survives_downstream_edits_and_rechecks_prerequisite(self):
        self.pair(); self.finish()
        self.h.transition('DEMO-002','IN_PROGRESS','fixture')
        (self.root/'docs/DEMO.md').write_text('checkpoint then resume; next task implementation\n')
        self.h.transition('DEMO-002','IMPLEMENTED','fixture')
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'DONE')
        ev=self.h.verify('DEMO-002'); self.assertEqual(ev['result'],'PASS')
        self.assertEqual(ev['checked_tasks'],['DEMO-001','DEMO-002'])
        self.h.transition('DEMO-002','VERIFIED','fixture'); self.review('DEMO-002')
        self.h.transition('DEMO-002','DONE','fixture')
        self.assertEqual(self.h.validate()['result'],'PASS')
        self.assertTrue(self.h.status()['tasks'][0]['regression_required'])
        self.assertEqual(self.h.verify('DEMO-001',regression=True)['result'],'PASS')
        self.assertTrue(self.h.current_evidence(self.h.task('DEMO-001')[1]))
        self.assertEqual(self.h.validate()['result'],'PASS')

    def test_downstream_cannot_hide_broken_prerequisite_check(self):
        self.pair()
        cfg=read(self.root/'.harness/checks.json')
        cfg['checks']['second']={'kind':'command','argv':['{python}','-c','pass'],'approved':True,'approval_reference':'fixture','purpose':'fixture','timeout_seconds':1}
        atomic(self.root/'.harness/checks.json',cfg)
        f,b=self.h.task('DEMO-002'); b['required_checks']=['second'];b['acceptance_checks']=[{'criterion':c,'checks':['second']} for c in b['acceptance_criteria']];self.write_tasks(f)
        self.finish();self.h.transition('DEMO-002','IN_PROGRESS','fixture')
        (self.root/'docs/DEMO.md').write_text('broken prerequisites')
        self.h.transition('DEMO-002','IMPLEMENTED','fixture')
        ev=self.h.verify('DEMO-002');self.assertEqual(ev['result'],'FAIL')
        self.assertEqual({r['check']:r['result'] for r in ev['results']},{'demo-doc':'FAIL','second':'PASS'})

    def test_env_and_executable_bit_invalidate_evidence_without_exposing_values(self):
        self.fixture.verified()
        p=self.root/'.env.test';p.write_text('MODE=fixture-private-value\n')
        self.assertFalse(self.h.current_evidence(self.h.task('DEMO-001')[1]))
        self.h.checkpoint()
        self.assertNotIn('fixture-private-value',(self.root/'.harness/state.json').read_text())
        # Windows chmod controls read-only state, not POSIX executable bits.
        if sys.platform != 'win32':
            before=self.h.binding();(self.root/'docs/DEMO.md').chmod(0o755)
            self.assertNotEqual(before,self.h.binding())

    def test_symlinks_fail_closed_and_os_metadata_is_ignored(self):
        before=self.h.binding();(self.root/'.DS_Store').write_text('os metadata')
        self.assertEqual(before,self.h.binding())
        symlink(self.root/'linked.py', self.root/'docs/DEMO.md')
        with self.assertRaisesRegex(HarnessError,'symlink'):self.h.binding()

    def test_outside_scope_add_delete_and_modify_are_blocked(self):
        p=self.root/'outside.txt';p.write_text('original')
        self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        for operation in ['edit','delete','add']:
            with self.subTest(operation=operation):
                p.write_text('modified') if operation=='edit' else p.unlink() if operation=='delete' else (self.root/'extra.txt').write_text('extra')
                with self.assertRaisesRegex(HarnessError,'outside approved scope'):
                    self.h.transition('DEMO-001','IMPLEMENTED','fixture')
                p.write_text('original');(self.root/'extra.txt').unlink(missing_ok=True)

    def test_preexisting_edits_are_baselined_not_reverted(self):
        (self.root/'outside.txt').write_text('preexisting user work')
        self.fixture.implemented()
        self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')
        self.assertEqual((self.root/'outside.txt').read_text(),'preexisting user work')

    def test_restart_does_not_launder_outside_scope_changes(self):
        self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        (self.root/'extra.txt').write_text('outside scope')
        self.h.transition('DEMO-001','REWORK','fixture')
        with self.assertRaisesRegex(HarnessError,'outside approved scope'):self.h.transition('DEMO-001','IN_PROGRESS','retry')

    def test_acceptance_missing_unknown_and_duplicate_checks_block_start(self):
        f,t=self.h.task('DEMO-001');original=copy.deepcopy(t['acceptance_checks'])
        for rows in [[],[{'criterion':'unknown','checks':['demo-doc']}],[{'criterion':t['acceptance_criteria'][0],'checks':['missing']}],original+original]:
            t['acceptance_checks']=rows;self.write_tasks(f)
            with self.assertRaises(HarnessError):self.h.transition('DEMO-001','IN_PROGRESS','fixture')

    def test_review_rejects_legacy_empty_and_open_findings(self):
        self.fixture.verified()
        p=self.root/'specs/harness-demo/verification.md'
        p.write_text('Reviewer:\nFindings: P1 unresolved critical defect\nEvidence:\n')
        with self.assertRaises(HarnessError):self.h.approve('DEMO-001','review','fixture',p.relative_to(self.root).as_posix())
        finding={'id':'R1','severity':'P1','status':'OPEN','location':'docs/DEMO.md:1','behavior':'Missing action','requirement':'Fixture acceptance','reproduction':'Read fixture','resolution':''}
        with self.assertRaises(HarnessError):self.review(findings=[finding])
        finding.update(status='RESOLVED')
        with self.assertRaises(HarnessError):self.review(findings=[finding])
        with self.assertRaises(HarnessError):self.review(verdict='CHANGES_REQUESTED')

    def test_review_must_reference_latest_task_evidence(self):
        self.fixture.verified();self.review()
        p=self.root/'specs/harness-demo/reviews/DEMO-001.md'
        p.write_text(p.read_text().replace('DEMO-001','DEMO-999'))
        with self.assertRaises(HarnessError):self.h.approve('DEMO-001','review','fixture',p.relative_to(self.root).as_posix())

    def test_opted_in_review_requires_exact_observations_and_current_pass_check(self):
        f,t=self.h.task('DEMO-001')
        t['review_contract_version']=2
        t['required_checks'].append('harness-validate')
        self.write_tasks(f)
        self.fixture.verified()
        t=self.h.task('DEMO-001')[1]
        criterion=t['acceptance_criteria'][0]
        record={'task_id':t['id'],'reviewer':'fixture reviewer',
                'evidence':t['evidence'][-1],'verdict':'PASS',
                'summary':'Compared the required fixture document check with the observed content.',
                'findings':[]}
        row={'criterion':criterion,'check':'demo-doc',
             'observed':'The fixture document contains the required checkpoint and resume text.',
             'assessment':'The successful document check supports this exact acceptance criterion.',
             'limitation':'This check does not assess unrelated application behavior or external systems.'}
        def review_text(): return '```harness-review\n'+json.dumps(record)+'\n```\n'
        with self.assertRaisesRegex(HarnessError,'criterion evidence'):
            verification.review(self.h,t,review_text())
        record['criterion_evidence']=[row]
        self.assertEqual(verification.review(self.h,t,review_text())['verdict'],'PASS')
        for bad in ([row,row], [{**row,'criterion':'unmapped criterion'}],
                    [{**row,'check':'harness-validate'}],
                    [{**row,'observed':'PASS'}],
                    [{**row,'observed':criterion}]):
            record['criterion_evidence']=bad
            with self.assertRaises(HarnessError): verification.review(self.h,t,review_text())
        record['criterion_evidence']=[row]
        record['evidence']='.harness/evidence/stale.json'
        with self.assertRaisesRegex(HarnessError,'latest execution evidence'):
            verification.review(self.h,t,review_text())
        record['evidence']=t['evidence'][-1]
        path=self.root/'specs/harness-demo/reviews/DEMO-001.md'
        path.parent.mkdir(exist_ok=True)
        path.write_text(review_text())
        self.h.approve('DEMO-001','review','fixture reviewer',path.relative_to(self.root).as_posix())

        # Direct runner review validation also rejects a tampered non-PASS check.
        evidence_path=self.root/t['evidence'][-1]
        evidence=read(evidence_path)
        next(item for item in evidence['results'] if item['check']=='demo-doc')['result']='FAIL'
        atomic(evidence_path,evidence)
        with self.assertRaisesRegex(HarnessError,'latest PASS check'):
            verification.review(self.h,t,review_text())

    def test_done_invalidated_by_changed_task_definition_and_review(self):
        self.finish()
        f,t=self.h.task('DEMO-001');t['outcome']='New approved outcome';self.write_tasks(f)
        self.h.reconcile();self.assertEqual(self.h.task('DEMO-001')[1]['status'],'REWORK')

    def test_completed_review_edit_is_not_accepted_historically(self):
        self.finish();(self.root/'specs/harness-demo/reviews/DEMO-001.md').write_text('withdrawn')
        self.h.reconcile();self.assertEqual(self.h.task('DEMO-001')[1]['status'],'REWORK')

    def test_next_and_unconfigured_run_stop_at_real_work(self):
        before=(self.root/'.harness/state.json').read_bytes()
        self.assertEqual(runner.next_action(self.h)['action'],'start')
        self.assertEqual(before,(self.root/'.harness/state.json').read_bytes())
        result=runner.run(self.h,10,60)
        self.assertEqual(result['action'],'implement');self.assertEqual(result['result'],'PASS')
        self.assertEqual(result['host_role']['role'],'implement')
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'IN_PROGRESS')
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'IN_PROGRESS')

    def configure_runner(self, implementation='pass', review_change=False):
        (self.root/'docs/runner-approval.md').write_text('Fixture authorizes these local deterministic adapters for DEMO-001. No external service.')
        impl=self.root/'fixture_implement.py';impl.write_text(implementation+'\n')
        rev=self.root/'fixture_review.py';rev.write_text('''import json,sys
from pathlib import Path
c=json.loads(Path(sys.argv[1]).read_text())
p=Path(c['review_path']);p.parent.mkdir(parents=True,exist_ok=True)
r={'task_id':c['task_id'],'reviewer':'fixture reviewer','evidence':c['evidence'],'verdict':'PASS','summary':'Compared fixture output with approved acceptance.','findings':[]}
p.write_text('```harness-review\\n'+json.dumps(r)+'\\n```\\n')
'''+("Path('docs/DEMO.md').write_text('checkpoint resume unexpected review edit')\n" if review_change else ''))
        cfg={'enabled':True,'approval_reference':'docs/runner-approval.md','approval_hash':digest((self.root/'docs/runner-approval.md').read_text()),'task_ids':['DEMO-001'],
             'implement_argv':['{python}',str(impl),'{context}'],'review_argv':['{python}',str(rev),'{context}'],'timeout_seconds':2,'max_failures':2}
        cfg['approval_hash']=runner.authorization_hash(cfg,(self.root/'docs/runner-approval.md').read_text())
        atomic(self.root/'.harness/runner.json',cfg)

    def test_configured_runner_completes_real_lifecycle(self):
        self.configure_runner("from pathlib import Path; Path('docs/DEMO.md').write_text('checkpoint then resume; adapter implementation')")
        result=runner.run(self.h,10,120)
        self.assertEqual(result['action'],'finished',result)
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'DONE')
        self.assertEqual(self.h.validate()['result'],'PASS')
        events=(self.root/'.harness/events.jsonl').read_text();self.assertIn('adapter-start',events);self.assertIn('adapter-finished',events)

    def test_runner_does_not_invent_developer_approval(self):
        f,t=self.h.task('DEMO-001');t['approval_requirements']=['developer'];self.write_tasks(f)
        self.configure_runner();result=runner.run(self.h,10,120)
        self.assertEqual(result['action'],'approval',result)
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'VERIFIED')
        self.assertNotIn('developer',self.h.task('DEMO-001')[1]['approvals'])

    def test_runner_reviewer_cannot_change_implementation(self):
        self.configure_runner(review_change=True)
        result=runner.run(self.h,10,120)
        self.assertEqual(result['action'],'inspect',result)
        self.assertIn('Reviewer changed',result['reason'])
        self.assertNotEqual(self.h.task('DEMO-001')[1]['status'],'DONE')

    def test_runner_detects_adapter_lifecycle_state_tampering(self):
        self.configure_runner("import json; from pathlib import Path; p=Path('.harness/state.json'); state=json.loads(p.read_text()); state['next_action']='forged'; p.write_text(json.dumps(state))")
        result=runner.run(self.h,10,120)
        self.assertEqual(result['action'],'inspect',result)
        self.assertIn('changed Python lifecycle state',result['reason'])
        self.assertNotEqual(self.h.task('DEMO-001')[1]['status'],'DONE')

    def test_runner_budgets_persist_across_invocations(self):
        self.configure_runner();one=runner.run(self.h,1,120);two=runner.run(self.h,1,120)
        self.assertEqual(one['action'],'budget-exhausted');self.assertEqual(two['run']['steps'],1)
        self.assertEqual(two['action'],'budget-exhausted')

    def test_runner_timeout_records_uncertainty_and_never_replays(self):
        self.configure_runner('import time; time.sleep(4)')
        cfg=read(self.root/'.harness/runner.json');cfg['timeout_seconds']=1;cfg['approval_hash']=runner.authorization_hash(cfg,(self.root/'docs/runner-approval.md').read_text());atomic(self.root/'.harness/runner.json',cfg)
        result=runner.run(self.h,10,120)
        self.assertEqual(result['action'],'recover',result)
        self.assertIsNotNone(self.h.state()['uncertain_outcome'])
        with self.assertRaises(HarnessError):runner.run(self.h,10,120)

    def test_runner_stale_authorization_and_unlisted_task_block(self):
        self.configure_runner();(self.root/'docs/runner-approval.md').write_text('withdrawn')
        with self.assertRaises(HarnessError):runner.run(self.h,10,120)

    def test_replan_preserves_source_boundary_and_accepts_reviewed_scope(self):
        self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        (self.root/'docs/additional.md').write_text('New intended scope')
        self.h.transition('DEMO-001','REWORK','scope change requires review')
        p=self.root/'specs/harness-demo/reviews/replan.md';p.parent.mkdir(exist_ok=True)
        p.write_text('Fixture developer authorizes docs/additional.md and updated task scope.')
        f,t=self.h.task('DEMO-001');t['scope'].append('docs/additional.md');self.write_tasks(f)
        self.h.replan('DEMO-001',p.relative_to(self.root).as_posix())
        self.h.transition('DEMO-001','IN_PROGRESS','approved replan')
        (self.root/'outside.txt').write_text('Unrelated source edit')
        self.h.transition('DEMO-001','REWORK','fixture')
        result=self.h.replan('DEMO-001',p.relative_to(self.root).as_posix())
        self.assertEqual(result['pending_outside_changes'],1)
        with self.assertRaisesRegex(HarnessError,'outside approved scope'):
            self.h.transition('DEMO-001','IN_PROGRESS','unrecognized source still blocks')

    def test_runner_configuration_change_revokes_authorization(self):
        self.configure_runner()
        cfg=read(self.root/'.harness/runner.json');cfg['implement_argv']=['{python}','-c','pass'];atomic(self.root/'.harness/runner.json',cfg)
        with self.assertRaisesRegex(HarnessError,'stale'):runner.run(self.h,10,120)

    def test_environment_config_is_subject_to_scope(self):
        self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        atomic(self.root/'.harness/environment.json',{'runtime':'changed fixture runtime'})
        with self.assertRaisesRegex(HarnessError,'outside approved scope'):
            self.h.transition('DEMO-001','IMPLEMENTED','fixture')

    def test_changed_dependency_definition_invalidates_completion(self):
        self.pair();self.finish();self.finish('DEMO-002')
        f,t=self.h.task('DEMO-001');t['outcome']='Different dependency contract';self.write_tasks(f)
        self.h.reconcile()
        self.assertEqual(self.h.task('DEMO-002')[1]['status'],'REWORK')

    def test_regression_failure_does_not_rewrite_historical_completion(self):
        self.finish();before=self.h.task('DEMO-001')[1]['evidence'][:]
        (self.root/'docs/DEMO.md').write_text('broken regression')
        self.assertEqual(self.h.verify('DEMO-001',regression=True)['result'],'FAIL')
        t=self.h.task('DEMO-001')[1]
        self.assertEqual(t['status'],'DONE');self.assertEqual(t['evidence'],before)
        self.assertFalse(self.h.current_evidence(t))
        self.assertEqual(runner.next_action(self.h)['action'],'regression')

    def test_runner_check_failure_never_completes(self):
        self.configure_runner("from pathlib import Path; Path('docs/DEMO.md').write_text('incorrect implementation')")
        r=runner.run(self.h,10,120)
        self.assertEqual(r['action'],'failure-budget',r)
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'REWORK')

    def test_runner_enforces_task_allowlist(self):
        self.configure_runner();cfg=read(self.root/'.harness/runner.json');cfg['task_ids']=['DEMO-999']
        cfg['approval_hash']=runner.authorization_hash(cfg,(self.root/'docs/runner-approval.md').read_text());atomic(self.root/'.harness/runner.json',cfg)
        r=runner.run(self.h,10,120);self.assertEqual(r['result'],'BLOCKED')
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'TODO')

    def test_runner_refuses_check_bundle_exceeding_time_budget(self):
        self.configure_runner()
        # Test the declared check budget, independently of host fixture IO speed.
        from unittest.mock import patch
        with patch.object(runner.time, 'monotonic', return_value=0):
            r=runner.run(self.h,10,3)
        self.assertEqual(r['action'],'time-budget',r)
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'IMPLEMENTED')

    def test_runner_failure_budget_survives_restart(self):
        self.configure_runner('raise SystemExit(1)')
        cfg=read(self.root/'.harness/runner.json');cfg['max_failures']=1
        cfg['approval_hash']=runner.authorization_hash(cfg,(self.root/'docs/runner-approval.md').read_text());atomic(self.root/'.harness/runner.json',cfg)
        first=runner.run(self.h,10,120);self.assertEqual(first['action'],'adapter-failed')
        self.assertEqual(runner.run(self.h,10,120)['action'],'failure-budget')


    def test_success_status_cannot_hide_failing_results_or_missing_coverage(self):
        self.finish();t=self.h.task('DEMO-001')[1];path=self.root/t['evidence'][-1];original=read(path)
        ev=copy.deepcopy(original);ev['results'][0]['exit_code']=1;atomic(path,ev)
        self.assertFalse(self.h.completed(t));self.assertFalse(self.h.current_evidence(t))
        ev=copy.deepcopy(original);ev['acceptance_results']=[];atomic(path,ev)
        self.assertFalse(self.h.completed(t))

    def test_runner_repairs_failed_check_within_bounded_run(self):
        self.configure_runner("import json,sys; from pathlib import Path; c=json.loads(Path(sys.argv[1]).read_text()); Path('docs/DEMO.md').write_text('checkpoint resume repaired' if c['evidence'] else 'broken first attempt')")
        result=runner.run(self.h,15,180)
        self.assertEqual(result['action'],'finished',result)
        self.assertEqual(result['run']['failures'],1)
        self.assertEqual(self.h.task('DEMO-001')[1]['status'],'DONE')


    def test_runner_repairs_review_feedback_without_fabricating_approval(self):
        self.configure_runner()
        p=self.root/'fixture_review.py'
        script=p.read_text().replace("p.write_text('```harness-review", "r['verdict']='PASS' if p.exists() else 'CHANGES_REQUESTED'\np.write_text('```harness-review")
        p.write_text(script)
        result=runner.run(self.h,15,180)
        self.assertEqual(result['action'],'finished',result)
        self.assertEqual(result['run']['failures'],1)

    def test_missing_legacy_coverage_invalidates_completion_without_crash(self):
        self.finish();f,t=self.h.task('DEMO-001');t.pop('acceptance_checks');self.write_tasks(f)
        self.h.reconcile();self.assertEqual(self.h.task('DEMO-001')[1]['status'],'REWORK')

    def test_excluded_directory_cannot_be_claimed_as_verified_scope(self):
        f,t=self.h.task('DEMO-001');t['scope']=['build/source.py'];self.write_tasks(f)
        with self.assertRaises(HarnessError):self.h.transition('DEMO-001','IN_PROGRESS','fixture')

    def test_control_config_symlink_is_rejected(self):
        p=self.root/'.harness/environment.json';p.unlink();symlink(p, self.root/'templates/onboarding.json')
        with self.assertRaises(HarnessError):self.h.binding()

    def test_legacy_missing_scope_snapshot_requires_reviewed_replacement(self):
        self.fixture.implemented();f,t=self.h.task('DEMO-001');t.pop('execution');self.write_tasks(f)
        with self.assertRaisesRegex(HarnessError,'Missing scope baseline'):self.h.verify('DEMO-001')


    def test_new_attempt_after_done_does_not_absorb_unfinished_retry(self):
        self.finish();(self.root/'later-feature.txt').write_text('Subsequent completed work')
        self.h.transition('DEMO-001','REWORK','Explicit new fix after completed work')
        self.h.transition('DEMO-001','IN_PROGRESS','New attempt snapshot')
        (self.root/'docs/DEMO.md').write_text('checkpoint resume new fix')
        self.h.transition('DEMO-001','IMPLEMENTED','fixture')
        self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')


class ScopedDecisionTests(unittest.TestCase):
    def setUp(self):
        f=test_onboarding.OnboardingTests();f.setUp();f.prepare();self.addCleanup(f.doCleanups)
        self.fixture,self.h,self.root=f,f.h,f.root
        data,t=self.h.task('CALC-001');t2=copy.deepcopy(t);t2['id']='CALC-002';data['tasks'].append(t2)
        atomic(self.root/'specs/calculator/tasks.json',data)

    def decision(self,target):
        p=self.root/'docs/DECISION_QUEUE.md';p.write_text(p.read_text()+f'\n| APP-002 | OPEN | yes | {target} | Resolve fixture business question. |\n')

    def test_scoped_decision_does_not_block_independent_task(self):
        self.decision('task:CALC-002');self.fixture.approve()
        self.assertEqual(readiness.report(self.h,'CALC-001')['result'],'PASS')
        self.assertEqual(readiness.report(self.h,'CALC-002')['result'],'BLOCKED')

    def test_scoped_decision_blocks_dependents(self):
        data,t=self.h.task('CALC-001');t['dependencies']=['CALC-002'];atomic(self.root/'specs/calculator/tasks.json',data)
        self.decision('task:CALC-002');self.fixture.approve()
        r=readiness.report(self.h,'CALC-001');self.assertTrue(any('APP-002' in b for b in r['blockers']))

    def test_unknown_selector_fails_closed(self):
        self.decision('task:CALC-999')
        with self.assertRaises(HarnessError):self.fixture.approve()

if __name__=='__main__':unittest.main()
