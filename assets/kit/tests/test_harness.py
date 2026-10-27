from platform_support import symlink
"""Behavioral acceptance tests; every mutation occurs in an isolated fixture."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from harnesslib.core import Harness
from harnesslib import graph
from harnesslib.adopt import adopt
from harnesslib.storage import HarnessError, atomic, events, read, finish_transaction

KIT = Path(__file__).resolve().parents[1]

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'project'
        adopt(KIT, self.root, dry_run=False)
        # Self-contained fixture: adopted projects need not carry the demo check.
        checks = read(self.root/'.harness/checks.json')
        checks['checks']['demo-doc'] = {'kind':'builtin','argv':[], 'timeout_seconds':30,
            'approved':True,'approval_reference':'Isolated test fixture',
            'purpose':'Verify fixture checkpoint and resume documentation'}
        atomic(self.root/'.harness/checks.json', checks)
        revisions = Harness(self.root).revisions()
        dest = self.root/'specs/harness-demo'
        dest.mkdir(parents=True)
        for name in ['spec.md','plan.md','verification.md']:
            shutil.copyfile(KIT/'specs/harness-demo'/name, dest/name) if (KIT/'specs/harness-demo'/name).exists() else None
        # Adoption is tested from projects without demo data, too.
        if not (dest/'spec.md').exists():
            for name in ['spec.md','plan.md']:
                (dest/name).write_text('Status: APPROVED\nRevision: 1\nApproval: isolated fixture\nTech-Spec-Revision: 0\nArchitecture-Revision: 0\nHARNESS-DEMO-001: test\n')
            (dest/'verification.md').write_text('No verification yet.\n')
        # Bind this isolated fixture to its actual canonical inputs, not source-kit revision 0.
        import re
        for name in ['spec.md', 'plan.md']:
            text = (dest/name).read_text()
            text = re.sub(r'(?m)^Tech-Spec-Revision: .*$', 'Tech-Spec-Revision: '+revisions['tech_spec'], text)
            text = re.sub(r'(?m)^Architecture-Revision: .*$', 'Architecture-Revision: '+revisions['architecture'], text)
            (dest/name).write_text(text)
        feature = read(self.root/'templates/feature/tasks.json')
        feature.update(feature_id='harness-demo',kind='harness',revisions=revisions)
        task=feature['tasks'][0]
        task.pop('workflow_required',None)  # Existing Strict records remain backward compatible.
        task.update(id='DEMO-001',requirements=['HARNESS-DEMO-001'],scope=['docs/DEMO.md'],dependencies=[],required_checks=['demo-doc'],approval_requirements=[],approvals={},status='TODO',history=[],evidence=[])
        task['acceptance_checks']=[{'criterion':c,'checks':['demo-doc']} for c in task['acceptance_criteria']]
        atomic(dest/'tasks.json', feature)
        (self.root/'docs/DEMO.md').write_text('Use checkpoint then resume to reconcile.\n')
        self.h=Harness(self.root)
        self.h.init()

    def review_text(self):
        record={'task_id':'DEMO-001','reviewer':'fixture','evidence':self.h.task('DEMO-001')[1]['evidence'][-1],
                'verdict':'PASS','summary':'Separate fixture review found no issues.','findings':[]}
        return '```harness-review\n'+json.dumps(record)+'\n```\n'

    def implemented(self):
        self.h.transition('DEMO-001','IN_PROGRESS','fixture start')
        self.h.transition('DEMO-001','IMPLEMENTED','fixture implemented')

    def verified(self):
        self.implemented()
        self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')
        self.h.transition('DEMO-001','VERIFIED','fixture evidence')

    def test_invalid_state_rejected(self):
        s=self.h.state(); s['schema_version']=False; atomic(self.root/'.harness/state.json',s)
        with self.assertRaises(HarnessError): self.h.validate()

    def test_unsupported_transition_rejected(self):
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','DONE','skip')

    def test_missing_evidence_prevents_verified(self):
        self.implemented()
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','VERIFIED','no checks')

    def test_source_changes_stale_verification(self):
        self.verified(); (self.root/'source.py').write_text('value = 2\n')
        self.assertEqual(self.h.status()['tasks'][0]['effective_status'],'REWORK')
        self.h.reconcile(); self.assertEqual(self.h.task('DEMO-001')[1]['status'],'REWORK')

    def test_required_failure_exits_nonzero(self):
        self.implemented(); (self.root/'docs/DEMO.md').write_text('missing recovery')
        p=subprocess.run([sys.executable,str(self.root/'harness'),'verify','DEMO-001'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)
        self.assertEqual(json.loads(p.stdout)['result'],'FAIL')

    def test_not_run_never_passes(self):
        check={'kind':'command','argv':[sys.executable,'-c','print(42)'],'approved':False,'approval_reference':'','timeout_seconds':1}
        self.assertEqual(self.h.run_check('unapproved',check)['result'],'NOT_RUN')

    def test_no_change_checkpoint_preserves_bytes_and_mtime(self):
        self.h.checkpoint(); p=self.root/'.harness/state.json'; before=(p.read_bytes(),p.stat().st_mtime_ns)
        self.assertFalse(self.h.checkpoint()['changed']); self.assertEqual(before,(p.read_bytes(),p.stat().st_mtime_ns))

    def test_meaningful_change_checkpoints(self):
        self.h.checkpoint(); (self.root/'source.py').write_text('x=1')
        self.assertTrue(self.h.checkpoint()['changed']); self.assertIn('source.py',self.h.state()['fingerprints'])

    def test_interrupted_operation_reconciles_without_replay(self):
        s=self.h.state(); s['active_operation']={'kind':'verification','pid':999999,'id':'fixture'}
        atomic(self.root/'.harness/state.json',s); self.h.reconcile()
        self.assertIsNone(self.h.state()['active_operation']); self.assertIsNotNone(self.h.state()['uncertain_outcome'])
        self.h.recovery_acknowledge('isolated fixture has no process or side effects')
        self.assertIsNone(self.h.state()['uncertain_outcome'])

    def test_transaction_replay_deduplicates_event(self):
        e=self.h.event('observation','fixture transaction'); transaction={'writes':{'.harness/state.json':self.h.state()},'event':e}
        for _ in range(2):
            atomic(self.root/'.harness/transaction.json',transaction); finish_transaction(self.root)
        self.assertEqual(sum(x['id']==e['id'] for x in events(self.root)),1)

    def test_torn_append_recovered(self):
        e=self.h.event('observation','fixture torn append')
        encoded=(json.dumps(e,sort_keys=True)+'\n').encode()
        with (self.root/'.harness/events.jsonl').open('ab') as out: out.write(encoded[:30])
        atomic(self.root/'.harness/transaction.json',{'writes':{},'event':e})
        finish_transaction(self.root); self.assertEqual(events(self.root)[-1]['id'],e['id'])

    def test_fresh_session_recovers_task(self):
        self.implemented(); fresh=Harness(self.root); fresh.reconcile()
        self.assertEqual(fresh.state()['active_task'],'DEMO-001'); self.assertIn('verification',fresh.state()['next_action'])

    def test_graph_incremental_changes_deletions_and_rename(self):
        p=self.root/'example.py'; p.write_text('import os\ndef first(): pass\n')
        graph.update(self.root); self.assertEqual(graph.status(self.root)['freshness'],'fresh')
        self.assertFalse(graph.update(self.root)['changed'])
        p.write_text('import sys\ndef second(): pass\n'); result=graph.update(self.root)
        self.assertEqual(result['reindexed'],['example.py'])
        p.rename(self.root/'renamed.py'); result=graph.update(self.root)
        self.assertIn('example.py',result['deleted']); self.assertEqual(graph.query(self.root,'first')['nodes'],[])
        (self.root/'renamed.py').unlink(); graph.update(self.root)
        self.assertNotIn('renamed.py',read(self.root/'.harness/graph/manifest.json')['files'])

    def test_partial_graph_and_parse_failure_visible(self):
        (self.root/'invalid.py').write_text('def (')
        graph.update(self.root); status=graph.status(self.root)
        self.assertEqual(status['coverage'],'partial'); self.assertIn('invalid.py',status['parse_limitations'])

    def test_graph_failure_allows_source_search_and_checks(self):
        cfg=read(self.root/'.harness/graph-config.json'); cfg['provider']='missing'; atomic(self.root/'.harness/graph-config.json',cfg)
        self.assertEqual(graph.query(self.root,'test')['result'],'BLOCKED')
        self.assertIn('checkpoint',(self.root/'docs/DEMO.md').read_text())
        self.implemented(); self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')

    def test_setup_idempotent_and_conflict_preserved(self):
        p=self.root/'.harness/state.json'; before=p.read_bytes(); self.assertFalse(self.h.init()['changed']); self.assertEqual(before,p.read_bytes())
        self.assertEqual(adopt(KIT,self.root)['files'],[])
        doc=self.root/'docs/HARNESS.md'; doc.write_text('existing user work')
        with self.assertRaises(HarnessError): adopt(KIT,self.root,False)
        self.assertEqual(doc.read_text(),'existing user work')

    def test_adoption_merges_ignores_without_replacing_project_rules(self):
        target = Path(self.tmp.name)/'existing-app'
        target.mkdir()
        ignore = target/'.gitignore'
        ignore.write_text('my-generated/\n')
        preview = adopt(KIT,target)
        self.assertEqual(preview['result'],'PASS')
        self.assertIn('/.codegraph/',preview['gitignore_additions'])
        self.assertIn('/.agents/skills/discovery/SKILL.md',preview['gitignore_additions'])
        self.assertEqual(ignore.read_text(), 'my-generated/\n')
        adopt(KIT,target,False)
        self.assertTrue(ignore.read_text().startswith('my-generated/\n'))
        self.assertEqual(adopt(KIT,target)['gitignore_additions'],[])

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_adoption_is_invisible_to_git_and_preserves_user_files(self):
        target = Path(self.tmp.name)/'git-app'
        target.mkdir()
        def git(*args):
            return subprocess.run(['git','-C',str(target),*args],check=True,
                                  capture_output=True,text=True).stdout
        git('init')
        (target/'.gitignore').write_text('my-generated/\n')
        git('add','.gitignore')
        before = git('status','--porcelain')
        preview = adopt(KIT,target)
        self.assertEqual(Path(preview['ignore_file']).parts[-2:], ('info', 'exclude'))
        self.assertEqual(git('status','--porcelain'),before)
        adopt(KIT,target,False)
        Harness(target).init()
        self.assertTrue((target/'.gitignore').read_text().startswith('my-generated/\n'))
        self.assertIn('/.agents/skills/discovery/SKILL.md', (target/'.gitignore').read_text())
        self.assertIn('/.agents/skills/discovery/SKILL.md', Path(preview['ignore_file']).read_text())
        self.assertEqual(git('status','--porcelain').strip(), 'AM .gitignore')
        for name in ['tests/test_user.py','docs/user.md','.agents/skills/user/SKILL.md']:
            path=target/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('user content')
        git('add','.')
        self.assertEqual(set(git('diff','--cached','--name-only').splitlines()),
                         {'.gitignore','tests/test_user.py','docs/user.md','.agents/skills/user/SKILL.md'})
        self.assertEqual(adopt(KIT,target)['gitignore_additions'],[])

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_adoption_blocks_tracked_harness_files_without_untracking(self):
        target=Path(self.tmp.name)/'tracked-app'; target.mkdir()
        subprocess.run(['git','init',str(target)],check=True,capture_output=True)
        shutil.copyfile(KIT/'AGENTS.md',target/'AGENTS.md')
        subprocess.run(['git','-C',str(target),'add','AGENTS.md'],check=True)
        preview=adopt(KIT,target)
        self.assertEqual(preview['result'],'BLOCKED')
        self.assertEqual(preview['tracked_conflicts'],['AGENTS.md'])
        with self.assertRaises(HarnessError): adopt(KIT,target,False)
        self.assertFalse((target/'harness').exists())

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_each_ignore_layer_protects_kit_independently(self):
        target=Path(self.tmp.name)/'dual-app'; target.mkdir()
        subprocess.run(['git','init',str(target)],check=True,capture_output=True)
        result=adopt(KIT,target,False)
        exclude=Path(result['ignore_file']); ignore=target/'.gitignore'
        exclude_text=exclude.read_text(); ignore_text=ignore.read_text()
        for missing in (exclude, ignore):
            missing.write_text('')
            checked=subprocess.run(['git','-C',str(target),'check-ignore',
                                    '.agents/skills/discovery/SKILL.md','harness','harnesslib/adopt.py',
                                    'scripts/update-tools.py','.agents/skills/tool-updater/SKILL.md'],
                                   check=True,capture_output=True,text=True)
            self.assertEqual(len(checked.stdout.splitlines()),5)
            exclude.write_text(exclude_text); ignore.write_text(ignore_text)
        preview=adopt(KIT,target)
        self.assertEqual(preview['gitignore_additions'],[])
        self.assertEqual(preview['exclude_additions'],[])

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_adoption_before_git_init_stays_invisible(self):
        target=Path(self.tmp.name)/'new-app'
        adopt(KIT,target,False)
        Harness(target).init()
        subprocess.run(['git','init',str(target)],check=True,capture_output=True)
        result=subprocess.run(['git','-C',str(target),'status','--porcelain'],
                              check=True,capture_output=True,text=True)
        self.assertEqual(result.stdout,'')

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_project_negation_cannot_silently_expose_skills(self):
        target=Path(self.tmp.name)/'negation-app'; target.mkdir()
        subprocess.run(['git','init',str(target)],check=True,capture_output=True)
        nested=target/'.agents/skills/discovery'; nested.mkdir(parents=True)
        (nested/'.gitignore').write_text('!SKILL.md\n')
        with self.assertRaisesRegex(HarnessError, 'ignore rules expose'):
            adopt(KIT,target,False)
        self.assertFalse((target/'harness').exists())

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_nested_worktree_adoption_uses_git_resolved_exclude(self):
        repo=Path(self.tmp.name)/'repo'; repo.mkdir()
        def git(*args):
            return subprocess.run(['git','-C',str(repo),*args],check=True,
                                  capture_output=True,text=True).stdout
        git('init')
        git('-c','user.name=Test','-c','user.email=test@example.invalid',
            'commit','--allow-empty','-m','fixture')
        worktree=Path(self.tmp.name)/'worktree'
        git('worktree','add','--detach',str(worktree))
        target=worktree/'nested [app]'
        adopt(KIT,target,False)
        Harness(target).init()
        result=subprocess.run(['git','-C',str(worktree),'status','--porcelain'],
                              check=True,capture_output=True,text=True)
        self.assertEqual(result.stdout,'')

    def test_logs_redact_test_secrets(self):
        self.h.note('observation','token=fixture-sensitive password=fixture-password Bearer fixture-bearer')
        text=(self.root/'.harness/events.jsonl').read_text()
        for secret in ['fixture-sensitive','fixture-password','fixture-bearer']: self.assertNotIn(secret,text)
        self.assertIn('[REDACTED]',text)

    def test_done_requires_separate_review(self):
        self.verified()
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','DONE','no review')
        p=self.root/'specs/harness-demo/verification.md'; p.write_text(self.review_text())
        self.h.approve('DEMO-001','review','fixture','specs/harness-demo/verification.md')
        self.h.transition('DEMO-001','DONE','reviewed'); self.assertEqual(self.h.validate()['result'],'PASS')

    def test_application_blocked_by_draft(self):
        p=self.root/'specs/harness-demo/tasks.json'; f=read(p); f['kind']='application'; atomic(p,f)
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','IN_PROGRESS','not approved')

    def test_timeout_and_missing_command_blocked(self):
        check={'kind':'command','argv':[sys.executable,'-c','import time; time.sleep(5)'],'approved':True,'approval_reference':'fixture','timeout_seconds':0.01}
        self.assertEqual(self.h.run_check('timeout',check)['result'],'BLOCKED')
        check['argv']=['/nonexistent/harness-fixture-command']
        self.assertEqual(self.h.run_check('missing',check)['result'],'BLOCKED')

    def test_empty_self_test_fails(self):
        shutil.rmtree(self.root/'tests'); (self.root/'tests').mkdir()
        p=subprocess.run([sys.executable,str(self.root/'harness'),'self-test'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0)

    def test_changed_review_invalidates_approval(self):
        self.verified()
        p=self.root/'specs/harness-demo/verification.md'
        p.write_text(self.review_text())
        self.h.approve('DEMO-001','review','fixture','specs/harness-demo/verification.md')
        p.write_text('Reviewer: fixture\nFindings: unresolved serious defect\nEvidence: reproduction\n')
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','DONE','changed review')

    def test_command_approval_respected_for_builtins(self):
        check=read(self.root/'.harness/checks.json')['checks']['demo-doc']
        check['approved']=False
        self.assertEqual(self.h.run_check('demo-doc',check)['result'],'NOT_RUN')

    def test_environment_and_configuration_stale_evidence(self):
        self.verified()
        atomic(self.root/'.harness/environment.json',{'database_version':'fixture-change'})
        self.assertFalse(self.h.current_evidence(self.h.task('DEMO-001')[1]))

    def test_required_unapproved_check_fails_verification(self):
        cfg=read(self.root/'.harness/checks.json')
        cfg['checks']['demo-doc']['approved']=False
        atomic(self.root/'.harness/checks.json',cfg)
        self.implemented(); ev=self.h.verify('DEMO-001')
        self.assertEqual(ev['result'],'FAIL'); self.assertEqual(ev['results'][0]['result'],'NOT_RUN')

    def test_skill_links_resolve(self):
        import re
        required = {'adversarial-reviewer','bootstrap-project','checkpoint-and-resume',
            'debugger','discovery','engineering-walkthrough','graph-maintainer',
            'harness-maintainer','implementer','llm-boundary-verifier','planner',
            'project-onboarding','security-reviewer','spec-author','status-reporter',
            'test-designer','tool-updater','verifier'}
        available = {p.parent.name:p for p in (self.root/'.agents/skills').glob('*/SKILL.md')}
        self.assertTrue(required <= set(available))
        skills = [available[name] for name in sorted(required)]
        for p in skills:
            text=p.read_text(encoding='utf-8')
            self.assertTrue(text.startswith('---\nname: '+p.parent.name+'\n'))
            for link in re.findall(r'\]\(([^)]+)\)',text):
                self.assertTrue((p.parent/link).is_file(),str(p)+': '+link)

    def skill_command(self, *args):
        return subprocess.run([sys.executable,str(self.root/'harness'),'skills',*args],capture_output=True,text=True)

    def test_skill_access_before_init_is_read_only(self):
        shutil.rmtree(self.root/'.harness')
        before={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result=self.skill_command()
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual({s['name'] for s in data['skills']},{p.parent.name for p in (self.root/'.agents/skills').glob('*/SKILL.md')})
        result=self.skill_command('planner')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['instructions'],(self.root/'.agents/skills/planner/SKILL.md').read_text())
        after={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_unknown_or_traversing_skill_rejected(self):
        for name in ['missing-role','../../docs/TECH_SPEC.md']:
            result=self.skill_command(name)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(json.loads(result.stderr)['result'],'FAIL')

    def test_missing_skill_inventory_blocked(self):
        shutil.rmtree(self.root/'.agents/skills')
        result=self.skill_command()
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout)['result'],'BLOCKED')

    def test_symlink_skill_rejected(self):
        p=self.root/'.agents/skills/planner/SKILL.md'
        p.unlink(); symlink(p, self.root/'docs/TECH_SPEC.md')
        result=self.skill_command('planner')
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Symlink',result.stderr)

    def test_empty_skill_rejected(self):
        (self.root/'.agents/skills/planner/SKILL.md').write_text('')
        self.assertNotEqual(self.skill_command('planner').returncode,0)

if __name__=='__main__': unittest.main()
