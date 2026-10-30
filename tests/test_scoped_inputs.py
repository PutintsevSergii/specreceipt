"""Per-check freshness never grants write authorization or global coverage."""
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from harnesslib import check_inputs
from harnesslib.storage import atomic, digest, read, HarnessError
import test_onboarding as fixtures
import tempfile
from harnesslib.adopt import adopt
from harnesslib.core import Harness


class ScopedInputTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve()/'project';adopt(fixtures.KIT,self.root,False)
        self.h=Harness(self.root);self.f=fixtures.OnboardingTests()
        self.f.root,self.f.h=self.root,self.h;self.f.prepare()
        for name in ('a','b'):
            folder=self.root/'src'/name;folder.mkdir(parents=True)
            (folder/'value.py').write_text('value = 1\n')
            (self.root/f'test_{name}.py').write_text(
                'from pathlib import Path\nfrom src.'+name+'.value import value\nassert value > 0\n'
                'p=Path(".harness/count-'+name+'")\np.write_text(str(int(p.read_text())+1) if p.exists() else "1")\n')
        (self.root/'src/shared.py').write_text('shared = 1\n')
        (self.root/'global.json').write_text('{}\n')
        (self.root/'lock.json').write_text('{}\n')
        (self.root/'docs/input-approval.md').write_text('Fixture developer reviewed module A independence from module B. No dynamic loading; source, tests, shared modules, policy and runtime are included.\n')
        cfg=read(self.root/'.harness/checks.json');cfg['checks']={}
        for name in ('a','b'):
            cfg['checks']['check-'+name]={'kind':'command','argv':['{python}','-B',f'test_{name}.py'],'approved':True,
                'approval_reference':'Isolated fixture developer approval','purpose':'Run concrete positive-value assertions', 'timeout_seconds':5}
        atomic(self.root/'.harness/checks.json',cfg)
        path=self.root/'specs/calculator/tasks.json';feature=read(path);task=feature['tasks'][0]
        task.update(scope=['src/','global.json','lock.json'],required_checks=['check-a','check-b'],
                    acceptance_criteria=['AC-A: module A positive','AC-B: module B positive'],
                    acceptance_checks=[{'criterion':'AC-A: module A positive','checks':['check-a']},
                                       {'criterion':'AC-B: module B positive','checks':['check-b']}])
        atomic(path,feature)
        self.contract={'schema_version':1,'inputs':['src/a/','src/shared.py','test_a.py','global.json','lock.json'],
                       'independent':['src/b/','test_b.py'],
                       'rationale':'Module A uses no module B code, fixtures, configuration or discovery; every other inventoried path remains an input.',
                       'approval_reference':'docs/input-approval.md',
                       'approval_hash':digest((self.root/'docs/input-approval.md').read_text()),'reviewed_revision':'pending'}
        self.contract['reviewed_revision']=check_inputs.revision(self.h,cfg['checks']['check-a'],self.contract,self.h.fingerprints())
        cfg['checks']['check-a']['input_contract']=self.contract
        atomic(self.root/'.harness/checks.json',cfg)
        onboarding=read(self.root/'.harness/onboarding.json');onboarding['application_checks']=['check-a','check-b']
        atomic(self.root/'.harness/onboarding.json',onboarding)
        self.f.approve()
        # Review the complete prepared fixture, including intake configuration.
        cfg['checks']['check-a']['input_contract']['reviewed_revision']=check_inputs.revision(self.h,cfg['checks']['check-a'],self.contract,self.h.fingerprints())
        atomic(self.root/'.harness/checks.json',cfg)
        self.f.approve()

    def implemented(self):
        self.h.transition('CALC-001','IN_PROGRESS','fixture developer authorization')
        self.h.transition('CALC-001','IMPLEMENTED','fixture implementation')

    def counts(self):
        return tuple(int((self.root/('.harness/count-'+n)).read_text()) for n in ('a','b'))

    def test_known_independent_change_reuses_only_opted_check(self):
        self.implemented();first=self.h.verify('CALC-001');self.assertEqual(first['result'],'PASS')
        self.assertEqual(self.counts(),(1,1))
        (self.root/'src/b/value.py').write_text('value = 2\n')
        second=self.h.verify('CALC-001')
        self.assertEqual(second['result'],'PASS')
        self.assertEqual(self.counts(),(1,2))
        self.assertEqual(second['input_coverage'],'MIXED')
        self.assertIn('reused_from',second['results'][0])
        self.assertNotIn('reused_from',second['results'][1])
        (self.root/'src/shared.py').write_text('shared = 2\n')
        third=self.h.verify('CALC-001');self.assertEqual(third['result'],'PASS')
        self.assertEqual(self.counts(),(2,3))
        self.assertEqual(third['input_coverage'],'GLOBAL')

    def test_unknown_creation_and_environment_changes_fall_back_to_global(self):
        self.implemented();self.h.verify('CALC-001')
        (self.root/'src/new.py').write_text('unknown = 1\n')
        self.assertEqual(self.h.verify('CALC-001')['input_coverage'],'GLOBAL')
        self.assertEqual(self.counts(),(2,2))
        (self.root/'src/new.py').unlink()
        with patch.dict('os.environ',{'LANG':'fixture-changed'}):
            self.assertEqual(self.h.verify('CALC-001')['input_coverage'],'GLOBAL')
        self.assertEqual(self.counts(),(3,3))
        self.assertFalse(self.h.current_evidence(self.h.task('CALC-001')[1]), 'fallback receipts still bind effective environment')

    def test_independent_inputs_never_authorize_outside_scope(self):
        path=self.root/'specs/calculator/tasks.json';feature=read(path)
        feature['tasks'][0]['scope']=['src/a/'];atomic(path,feature)
        self.implemented();self.h.verify('CALC-001')
        (self.root/'src/b/value.py').write_text('value = 2\n')
        with self.assertRaisesRegex(HarnessError,'outside approved scope'): self.h.verify('CALC-001')
        self.assertEqual(self.counts(),(1,1))

    def test_inventory_changes_and_contract_edits_invalidate(self):
        cfg=read(self.root/'.harness/checks.json');check=cfg['checks']['check-a']
        task=self.h.task('CALC-001')[1]
        self.assertEqual(check_inputs.binding(self.h,task,'check-a',check,self.h.fingerprints())['mode'],'SCOPED')
        source=self.root/'src/a/value.py';original=source.read_bytes();mode=source.stat().st_mode
        operations=[lambda:source.write_text('value = 3\n'),lambda:source.unlink(),
                    lambda:source.rename(self.root/'src/a/renamed.py')]
        for operation in operations:
            operation()
            self.assertEqual(check_inputs.binding(self.h,task,'check-a',check,self.h.fingerprints())['mode'],'GLOBAL')
            renamed=self.root/'src/a/renamed.py'
            if renamed.exists(): renamed.unlink()
            source.write_bytes(original)
        if __import__('os').name!='nt':
            source.chmod(mode | 0o111)
            self.assertEqual(check_inputs.binding(self.h,task,'check-a',check,self.h.fingerprints())['mode'],'GLOBAL')
            source.chmod(mode)
        for rel in ('global.json','lock.json','test_a.py'):
            path=self.root/rel;before=path.read_bytes();path.write_bytes(before+b'\n')
            self.assertEqual(check_inputs.binding(self.h,task,'check-a',check,self.h.fingerprints())['mode'],'GLOBAL')
            path.write_bytes(before)
        changed={**check,'argv':['{python}','-B','test_b.py']}
        self.assertEqual(check_inputs.binding(self.h,task,'check-a',changed,self.h.fingerprints())['mode'],'GLOBAL')
        bad={**self.contract,'independent':['src/']}
        with self.assertRaises(HarnessError): check_inputs.validate(self.h,check,bad)
        (self.root/'docs/input-approval.md').write_text('Changed approval document requires genuine renewed developer review.\n')
        with self.assertRaises(HarnessError): check_inputs.binding(self.h,task,'check-a',check,self.h.fingerprints())

    def test_branch_identity_and_missing_original_receipt_reject_reuse(self):
        self.implemented();first=self.h.verify('CALC-001')
        task=self.h.task('CALC-001')[1]
        with patch.object(self.h,'git',return_value={'branch':'different-branch','head':'fixture'}):
            self.assertFalse(self.h.current_evidence(task))
        (self.root/'src/b/value.py').write_text('value = 2\n')
        second=self.h.verify('CALC-001')
        self.assertIn('reused_from',second['results'][0])
        from harnesslib.reporting import report
        retained=report(self.h,'CALC-001',retain=True,retain_dir=self.root.resolve().parent/'retained')
        folder=Path(retained['tasks'][0]['paths']['review_package'])/'files'
        self.assertTrue((folder/second['results'][0]['reused_from']).is_file())
        (self.root/second['results'][0]['reused_from']).unlink()
        self.assertFalse(self.h.successful_evidence(self.h.task('CALC-001')[1],second))

    def test_measured_independent_reruns(self):
        other=ScopedInputTests();other.setUp();self.addCleanup(other.doCleanups)
        cfg=read(other.root/'.harness/checks.json');cfg['checks']['check-a'].pop('input_contract')
        atomic(other.root/'.harness/checks.json',cfg);other.f.approve()
        measurements={}
        for fixture,label in ((other,'global'),(self,'scoped')):
            fixture.implemented();fixture.h.verify('CALC-001')
            overhead=[];scans=[];check_seconds=[]
            original=fixture.h.run_check
            def measured(*args,**kwargs):
                started=time.perf_counter();result=original(*args,**kwargs)
                check_seconds.append(time.perf_counter()-started);return result
            with patch.object(fixture.h,'run_check',side_effect=measured):
                for sample in range(3):
                    (fixture.root/'src/b/value.py').write_text(f'value = {sample+2}\n')
                    started=time.perf_counter();fixture.h.fingerprints();scans.append(time.perf_counter()-started)
                    check_seconds.clear();started=time.perf_counter()
                    self.assertEqual(fixture.h.verify('CALC-001')['result'],'PASS')
                    overhead.append(time.perf_counter()-started-sum(check_seconds))
            measurements[label]={'samples':3,'check_runs_including_baseline':fixture.counts(),
                                 'harness_overhead_excluding_checks_seconds':overhead,'full_scan_seconds':scans}
        self.assertEqual(measurements['global']['check_runs_including_baseline'],(4,4))
        self.assertEqual(measurements['scoped']['check_runs_including_baseline'],(1,4))
        print('SCOPED_MEASUREMENT '+json.dumps(measurements,sort_keys=True))

    def test_all_scoped_evidence_stays_current_only_for_authorized_independent_change(self):
        path=self.root/'specs/calculator/tasks.json';feature=read(path);task=feature['tasks'][0]
        task['required_checks']=['check-a'];task['acceptance_criteria']=task['acceptance_criteria'][:1];task['acceptance_checks']=task['acceptance_checks'][:1]
        atomic(path,feature)
        onboarding=read(self.root/'.harness/onboarding.json');onboarding['application_checks']=['check-a'];atomic(self.root/'.harness/onboarding.json',onboarding)
        cfg=read(self.root/'.harness/checks.json');check=cfg['checks']['check-a']
        check['input_contract']['reviewed_revision']=check_inputs.revision(self.h,check,check['input_contract'],self.h.fingerprints())
        atomic(self.root/'.harness/checks.json',cfg);self.f.approve()
        self.implemented();ev=self.h.verify('CALC-001');self.assertEqual(ev['input_coverage'],'SCOPED')
        self.h.transition('CALC-001','VERIFIED','fixture verification')
        (self.root/'src/b/value.py').write_text('value = 2\n')
        task=self.h.task('CALC-001')[1]
        self.assertTrue(self.h.current_evidence(task))
        from harnesslib.reporting import task_report
        self.assertEqual(task_report(self.h,'CALC-001')['verification']['status'],'PASS')
        self.h.reconcile();self.assertEqual(self.h.task('CALC-001')[1]['status'],'VERIFIED')
        (self.root/'src/unknown.py').write_text('unknown = 1\n')
        self.assertFalse(self.h.current_evidence(self.h.task('CALC-001')[1]))

    def test_invalid_contract_fails_before_operation_start(self):
        cfg=read(self.root/'.harness/checks.json');cfg['checks']['check-a']['input_contract']['approval_hash']='invalid'
        atomic(self.root/'.harness/checks.json',cfg);self.f.approve();self.implemented()
        with self.assertRaisesRegex(HarnessError,'approval is missing or changed'):
            self.h.verify('CALC-001')
        self.assertIsNone(self.h.state()['active_operation'])
