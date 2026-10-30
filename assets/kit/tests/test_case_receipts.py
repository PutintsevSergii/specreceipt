"""Fresh structured test observations; text summaries are never receipts."""
import unittest
from pathlib import Path
import tempfile
from harnesslib import case_receipts
from harnesslib.storage import HarnessError

class CaseReceiptTests(unittest.TestCase):
    def xml(self, case='<testcase classname="suite.Case" name="test_owner"/>', operation='op'):
        return (f'<testsuite tests="1"><properties>'
                f'<property name="harness.operation" value="{operation}"/>'
                '<property name="harness.check" value="unit"/>'
                '<property name="harness.invocation" value="inv"/>'
                '</properties>'+case+'</testsuite>').encode()

    def parse(self, content):
        return case_receipts.parse(content, 'op', 'unit', 'inv')

    def test_observed_case_and_skip_are_distinct(self):
        self.assertEqual(self.parse(self.xml())[0]['status'], 'PASS')
        skipped=self.xml('<testcase classname="suite.Case" name="test_owner"><skipped/></testcase>')
        self.assertEqual(self.parse(skipped)[0]['status'], 'SKIPPED')

    def test_stale_duplicate_malformed_and_oversized_reports_reject(self):
        duplicate=self.xml('<testcase classname="suite.Case" name="test_owner"/>'*2).replace(b'tests="1"',b'tests="2"')
        for content in (self.xml(operation='old'), duplicate, b'not xml', b'x'*(1024*1024+1),
                        b'<!DOCTYPE x [<!ENTITY a "b">]>'+self.xml(), self.xml().decode().encode('utf-16'),
                        self.xml().replace(b'tests="1"', b'tests="0"')):
            with self.subTest(content=content[:80]):
                with self.assertRaises(HarnessError): self.parse(content)


class CaseConsumerTests(unittest.TestCase):
    def setUp(self):
        import test_harness as fixtures
        from harnesslib.storage import atomic, read
        self.f=fixtures.HarnessTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.h,self.root=self.f.h,self.f.root
        (self.root/'access.py').write_text('def allowed(owner, viewer):\n    return owner == viewer\n')
        (self.root/'test_access.py').write_text('import unittest\nfrom access import allowed\nclass Access(unittest.TestCase):\n    def test_other(self):\n        self.assertFalse(allowed("owner", "other"), "deny-other-user")\n')
        cfg=read(self.root/'.harness/checks.json')
        cfg['checks']['demo-doc'].update(kind='command',argv=['{python}','-B','-m','harnesslib.junit_unittest','test_access'],report_format='junit-v1')
        atomic(self.root/'.harness/checks.json',cfg)
        path=self.root/'specs/harness-demo/tasks.json';feature=read(path)
        row=feature['tasks'][0]['acceptance_checks'][0]
        row['required_cases']=[{'check':'demo-doc','cases':['test_access.Access.test_other']}]
        atomic(path,feature)

    def test_real_runner_current_case_missing_case_and_tampering(self):
        from harnesslib.storage import atomic, read
        self.f.implemented(); ev=self.h.verify('DEMO-001')
        self.assertEqual(ev['result'],'PASS')
        import subprocess, sys, json
        cli = subprocess.run([sys.executable, '-B', str(self.root/'harness'), 'verify', 'DEMO-001'], capture_output=True, text=True)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertEqual(json.loads(cli.stdout)['acceptance_support']['criteria'][0]['level'], 'CASES_OBSERVED')
        self.assertEqual(ev['acceptance_support']['criteria'][0]['level'],'CASES_OBSERVED')
        self.assertTrue(self.h.current_evidence(self.h.task('DEMO-001')[1]))
        ev=json.loads(cli.stdout)
        pointer=ev['results'][0]['case_observation']; path=self.root/pointer['reference']
        record=read(path);record['operation']='old';atomic(path,record)
        self.assertFalse(self.h.current_evidence(self.h.task('DEMO-001')[1]))

    def test_exit_zero_without_required_case_is_insufficient(self):
        from harnesslib.storage import atomic, read
        path=self.root/'specs/harness-demo/tasks.json';f=read(path)
        f['tasks'][0]['acceptance_checks'][0]['required_cases'][0]['cases']=['test_access.Access.absent']
        atomic(path,f)
        self.f.implemented();ev=self.h.verify('DEMO-001')
        self.assertEqual(ev['results'][0]['result'],'PASS')
        self.assertEqual(ev['acceptance_support']['criteria'][0]['level'],'INSUFFICIENT')
        self.assertEqual(ev['result'],'FAIL')
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','VERIFIED','cannot pass missing cases')

    def test_skipped_and_xfail_never_support_required_case(self):
        for decorator in ('@unittest.skip("fixture")','@unittest.expectedFailure'):
            (self.root/'test_access.py').write_text('import unittest\nclass Access(unittest.TestCase):\n    '+decorator+'\n    def test_other(self):\n        self.fail("fixture")\n')
            result=self.h.run_check('demo-doc',__import__('harnesslib.storage',fromlist=['read']).read(self.root/'.harness/checks.json')['checks']['demo-doc'])
            obs=case_receipts.observed(self.h,result,'direct-check',self.h.binding())
            self.assertEqual(obs['cases'][0]['status'],'SKIPPED')

    def test_semantic_attestation_and_behavioral_fault_are_distinct(self):
        import hashlib
        from harnesslib.storage import atomic, read
        path=self.root/'specs/harness-demo/tasks.json';feature=read(path)
        row=feature['tasks'][0]['acceptance_checks'][0];rule=row['required_cases'][0]
        rule.update(review='specs/harness-demo/reviews/semantic.json',fault_probe={
            'path':'access.py','before':'return owner == viewer','after':'return True',
            'case':rule['cases'][0],'expected_message':'deny-other-user','fixture_paths':['access.py','test_access.py']})
        atomic(path,feature)
        self.f.implemented()
        absent=self.h.verify('DEMO-001')
        self.assertEqual(absent['acceptance_support']['criteria'][0]['level'],'INSUFFICIENT')
        source=(self.root/'test_access.py').read_bytes()
        review={'schema_version':1,'criterion':row['criterion'],'check':rule['check'],'cases':rule['cases'],
                'input_binding':self.h.binding(),'reviewer':'Fixture reviewer agent','reviewer_type':'agent',
                'behavior':'A different viewer must be denied access to the owner record.',
                'negative_scenario':'The viewer identity differs from the owner identity.',
                'gaps':'This narrow fixture does not demonstrate authentication or persistence.',
                'assertions':[{'case':'test_access.Access.test_other','path':'test_access.py','line':5,'text':source.decode().splitlines()[4],
                               'sha256':hashlib.sha256(source).hexdigest()}]}
        atomic(self.root/rule['review'],review)
        good=self.h.verify('DEMO-001')
        self.assertEqual(good['result'],'PASS',good['acceptance_support'])
        support=good['acceptance_support']['criteria'][0]
        self.assertEqual(support['level'],'FAULT_DETECTED')
        self.assertTrue(support['observations'] and support['reviews'] and support['probes'])
        from harnesslib.reporting import report
        retained=report(self.h,'DEMO-001',retain=True,retain_dir=self.root.resolve().parent/'retained')
        folder=Path(retained['tasks'][0]['paths']['review_package'])/'files'
        for artifacts in (support['observations'],support['reviews'],support['probes']):
            for artifact in artifacts: self.assertTrue((folder/artifact['reference']).is_file())
        self.assertEqual((folder/'test_access.py').read_bytes(),source)
        probe=read(self.root/support['probes'][0]['reference'])
        self.assertTrue(probe['baseline_observation']['cases'])
        self.assertTrue(probe['mutant_observation']['cases'])
        self.assertEqual((self.root/'access.py').read_text(),'def allowed(owner, viewer):\n    return owner == viewer\n')
        self.assertTrue(self.h.current_evidence(self.h.task('DEMO-001')[1]))
        from harnesslib import fault_evidence
        import copy
        bad = copy.deepcopy(rule); bad['fault_probe']['after'] = 'return ('
        task = self.h.task('DEMO-001')[1]
        pointer = fault_evidence.run(self.h, task, bad, good['id'], self.h.binding())
        with self.assertRaisesRegex(HarnessError, 'intended mapped assertion'):
            fault_evidence.validate(self.h, task, bad, pointer, good['id'], self.h.binding())
        review['assertions']=[];atomic(self.root/rule['review'],review)
        self.assertFalse(self.h.current_evidence(self.h.task('DEMO-001')[1]))

    def test_dependency_case_contract_is_rechecked_in_downstream_verification(self):
        import copy
        from harnesslib.storage import atomic, read
        cfg=read(self.root/'.harness/checks.json')
        cfg['checks']['child-check']={'kind':'command','argv':['{python}','-c','print("child")'],
            'approved':True,'approval_reference':'Isolated fixture developer','purpose':'Child fixture command','timeout_seconds':5}
        atomic(self.root/'.harness/checks.json',cfg)
        path=self.root/'specs/harness-demo/tasks.json';feature=read(path)
        child=copy.deepcopy(feature['tasks'][0]);child.update(id='CHILD-001',dependencies=['DEMO-001'],required_checks=['child-check'])
        child['acceptance_checks']=[{'criterion':c,'checks':['child-check']} for c in child['acceptance_criteria']]
        feature['tasks'].append(child);atomic(path,feature)
        self.f.verified()
        (self.root/'specs/harness-demo/reviews').mkdir(exist_ok=True)
        ref='specs/harness-demo/reviews/parent.md';(self.root/ref).write_text(self.f.review_text())
        self.h.approve('DEMO-001','review','Fixture reviewer',ref)
        self.h.transition('DEMO-001','DONE','fixture completion')
        (self.root/'test_access.py').write_text('import unittest\nclass Access(unittest.TestCase):\n    @unittest.skip("fixture regression")\n    def test_other(self):\n        pass\n')
        self.h.transition('CHILD-001','IN_PROGRESS','fixture start')
        self.h.transition('CHILD-001','IMPLEMENTED','fixture implementation')
        ev=self.h.verify('CHILD-001')
        self.assertTrue(all(r['result']=='PASS' for r in ev['results']))
        self.assertEqual(ev['result'],'FAIL')
        self.assertEqual(ev['dependency_support'][0]['support']['criteria'][0]['level'],'INSUFFICIENT')
