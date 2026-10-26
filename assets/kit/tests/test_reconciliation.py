from platform_support import symlink
"""Adversarial exact-recognition fixtures. Consent here is simulated, never production consent."""
import copy
import json
import os
from unittest.mock import patch
import unittest
import test_harness
from harnesslib import reconciliation as rec, verification, reporting
from harnesslib.storage import atomic, digest, HarnessError, read


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_harness.HarnessTests(); self.fixture.setUp()
        self.root=self.fixture.root; self.h=self.fixture.h
    def tearDown(self): self.fixture.doCleanups()
    def start(self): self.h.transition('DEMO-001','IN_PROGRESS','fixture')
    def task(self): return self.h.task('DEMO-001')[1]
    def manifest(self): return rec.propose(self.h,self.task())
    def accept(self, manifest=None):
        manifest=manifest or self.manifest()
        atomic(self.root/'.harness/proposal.json',manifest)
        approval='.harness/approval-'+digest(manifest)+'.md'
        (self.root/approval).write_text('Simulated developer approves exact fixture manifest '+digest(manifest))
        return rec.accept(self.h,'DEMO-001','.harness/proposal.json',approval,'fixture developer')
    def test_risk_scheduling_release_and_other_feature_not_writable(self):
        self.fixture.verified(); old=copy.deepcopy(self.task()); evidence=(self.root/old['evidence'][-1]).read_bytes()
        self.h.transition('DEMO-001','BLOCKED','schedule other task')
        (self.root/'release').mkdir(); (self.root/'release/fixture.zip').write_bytes(b'archive')
        (self.root/'specs/other').mkdir(); (self.root/'specs/other/plan.md').write_text('Other approved work')
        with self.assertRaisesRegex(HarnessError,'outside approved scope'): self.h.transition('DEMO-001','IN_PROGRESS','restart')
        self.accept(); self.h.transition('DEMO-001','IN_PROGRESS','recognized')
        self.assertEqual(self.task()['execution']['baseline'],old['execution']['baseline'])
        self.assertEqual(self.task()['scope'],old['scope'])
        self.assertEqual((self.root/old['evidence'][-1]).read_bytes(),evidence)
        self.h.transition('DEMO-001','IMPLEMENTED','unchanged'); self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')
        self.h.transition('DEMO-001','VERIFIED','checks'); self.assertTrue(self.h.current_evidence(self.task()))
        report=reporting.task_report(self.h,'DEMO-001')
        self.assertIn('recognized_pre_existing',json.dumps(report))
        (self.root/'release/fixture.zip').write_bytes(b'unauthorized')
        self.assertFalse(self.h.current_evidence(self.task()))
        with self.assertRaisesRegex(HarnessError,'Recognized content changed'): verification.scope_changes(self.h,self.task())
    def test_two_task_concurrency_preserves_history_and_lifecycle_projection(self):
        f=read(self.root/'specs/harness-demo/tasks.json'); second=copy.deepcopy(f['tasks'][0]);second.update(id='DEMO-002',scope=['docs/second.md']);f['tasks'].append(second);atomic(self.root/'specs/harness-demo/tasks.json',f)
        self.start(); before=copy.deepcopy(self.task()['execution']['baseline']);self.h.transition('DEMO-001','BLOCKED','schedule')
        self.h.transition('DEMO-002','IN_PROGRESS','independent');(self.root/'docs/second.md').write_text('Other task implementation')
        self.h.transition('DEMO-002','IMPLEMENTED','done');self.assertEqual(self.h.verify('DEMO-002')['result'],'PASS');self.h.transition('DEMO-002','BLOCKED','await review')
        self.accept();self.h.transition('DEMO-001','IN_PROGRESS','resume')
        self.assertEqual(self.task()['execution']['baseline'],before)
        self.assertEqual(verification.scope_changes(self.h,self.task()),[])
        (self.root/'docs/third.md').write_text('Unauthorized')
        with self.assertRaisesRegex(HarnessError,'outside approved scope'): verification.scope_changes(self.h,self.task())
    def test_created_modified_deleted_modes_and_extra_files(self):
        (self.root/'existing.txt').write_text('old');(self.root/'deleted.txt').write_text('old');self.start()
        (self.root/'existing.txt').write_text('new');(self.root/'deleted.txt').unlink();(self.root/'created.txt').write_text('new')
        self.assertEqual({e['change'] for e in self.manifest()['entries']},{'CREATED','MODIFIED','DELETED'})
        self.accept();verification.scope_changes(self.h,self.task())
        if os.name == 'nt':
            # Windows does not expose a POSIX execute bit for a text file.
            (self.root/'existing.txt').write_text('changed after recognition')
        else:
            (self.root/'existing.txt').chmod(0o755)
        with self.assertRaises(HarnessError):verification.scope_changes(self.h,self.task())
    def test_stale_manifest_reference_replay_and_hash(self):
        self.start();(self.root/'outside.txt').write_text('first');m=self.manifest();(self.root/'outside.txt').write_text('second')
        with self.assertRaisesRegex(HarnessError,'Stale'):self.accept(m)
        self.accept();m=self.manifest();self.accept(m)
        with self.assertRaisesRegex(HarnessError,'Stale'):self.accept(m)
        reference=self.task()['execution']['recognitions'][-1]['reference'];record=read(self.root/reference);(self.root/record['approval']).write_text('Changed consent')
        with self.assertRaises(HarnessError):verification.scope_changes(self.h,self.task())
    def test_invalid_manifests_and_symlinks(self):
        self.start();(self.root/'outside.txt').write_text('outside');m=self.manifest()
        for path in ['../escape','/absolute','./outside.txt','outside.txt/','*.txt','docs/../outside.txt','docs\\x']:
            broken=copy.deepcopy(m);broken['entries'][0]['path']=path
            with self.subTest(path=path), self.assertRaises(HarnessError):self.accept(broken)
        broken=copy.deepcopy(m);broken['entries']*=2
        with self.assertRaises(HarnessError):self.accept(broken)
        (self.root/'outside.txt').unlink();symlink(self.root/'outside.txt', self.root/'docs/DEMO.md')
        with self.assertRaises(HarnessError):self.accept(m)
    def test_definition_replan_preserves_original_and_requires_new_consent(self):
        self.start();(self.root/'outside.txt').write_text('outside');self.accept();old=copy.deepcopy(self.task()['execution']['baseline'])
        self.h.transition('DEMO-001','REWORK','approved new requirement')
        f,t=self.h.task('DEMO-001');t['outcome']='Approved revised task outcome';atomic(self.root/'specs/harness-demo/tasks.json',f)
        (self.root/'.harness/replan.md').write_text('Simulated developer approves revised task outcome.')
        self.h.replan('DEMO-001','.harness/replan.md')
        self.assertEqual(self.task()['execution']['baseline'],old)
        with self.assertRaisesRegex(HarnessError,'stale'):self.h.transition('DEMO-001','IN_PROGRESS','stale')
        self.accept();self.h.transition('DEMO-001','IN_PROGRESS','fresh approval')
    def test_policy_and_in_scope_cannot_be_recognized(self):
        self.start();(self.root/'docs/TECH_SPEC.md').write_text('changed policy')
        with self.assertRaisesRegex(HarnessError,'policy'):self.manifest()
    def test_accept_revalidates_before_commit(self):
        self.start();(self.root/'outside.txt').write_text('outside');m=self.manifest();real=rec.propose; calls=[]
        def changed(h,t):
            calls.append(1)
            if len(calls)==2:(self.root/'outside.txt').write_text('concurrent mutation')
            return real(h,t)
        with patch.object(rec,'propose',side_effect=changed), self.assertRaises(HarnessError):self.accept(m)
        self.assertFalse(self.task()['execution'].get('recognitions'))
