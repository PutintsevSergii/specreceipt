"""Workflow policy regressions using isolated fixtures and explicit simulated consent."""
import json
from unittest.mock import patch
import test_harness
from harnesslib import workflow, reporting
from harnesslib.storage import HarnessError, atomic


class WorkflowTests(test_harness.HarnessTests):
    # Reuse setup/helpers, not the inherited regression suite.
    def facts(self, **updates):
        value = dict(critical_risk=False, critical_unknowns=[], unknowns=[], public_api=False,
                     architecture_change=False,components=1,inspected=['docs/DEMO.md'],agent='fixture')
        value.update(updates); atomic(self.root/'.harness/facts.json',value)
        return '.harness/facts.json'

    def assess(self, **updates):
        return workflow.assess(self.h,'DEMO-001',self.facts(**updates))

    def confirm(self, profile='FAST'):
        (self.root/'.harness/consent.txt').write_text('Simulated fixture developer confirms workflow and brief plan.\n')
        return workflow.confirm(self.h,'DEMO-001',profile,'fixture','.harness/consent.txt')

    def test_profile_recommendations_and_bounded_assessment(self):
        with patch.object(self.h,'fingerprints',side_effect=AssertionError('full inventory prohibited')):
            self.assertEqual(self.assess()['recommended'],'FAST')
            self.assertEqual(self.assess(components=3)['recommended'],'STANDARD')
            self.assertEqual(self.assess(critical_risk=True)['minimum'],'STRICT')

    def test_contextual_positive_negative_mixed_and_ambiguous_narrative(self):
        cases = [
            ('Implement authentication checks.', 'STRICT', False),
            ('Change production access permissions.', 'STRICT', False),
            ('No authentication. No production impact.', 'FAST', False),
            ('Authentication is not required. No production environment is in scope.', 'FAST', False),
            ('No authentication, authorization, secrets, or sensitive data are involved.', 'FAST', False),
            ('Not applicable: there is no state, storage, migration, transaction, or retention.', 'FAST', False),
            ('No authentication changes; modify payment validation.', 'STRICT', False),
            ('No authentication changes, but modify payment validation.', 'STRICT', False),
            ('No authentication changes and modify payment validation.', 'STRICT', False),
            ('No authentication bypass is allowed.', 'STRICT', False),
            ('Not only authentication changes.', 'STRICT', False),
            ('Authentication impact is unknown.', 'FAST', True),
            ('May affect permissions.', 'FAST', True),
            ('No production impact is expected.', 'FAST', True),
            ('Do not implement authentication.', 'FAST', True),
            ('Authentication.', 'FAST', True),
            ('## Security\nThe author updates documentation.', 'FAST', False),
            ('Pending. This DRAFT does not authorize implementation.', 'FAST', False),
            ('This DRAFT does not authorize implementation; implement authentication checks.', 'STRICT', False),
        ]
        for text, minimum, deeper in cases:
            with self.subTest(text=text):
                (self.root/'docs/DEMO.md').write_text(text)
                result = self.assess()
                self.assertEqual(result['minimum'], minimum)
                self.assertEqual(result['deeper_required'], deeper)
                if deeper:
                    self.assertEqual(result['uncertainty'], 'HIGH')
                    with self.assertRaisesRegex(HarnessError, 'unknown'):
                        self.confirm('STRICT')

    def test_sensitive_task_outcome_uses_same_narrative_classifier(self):
        f, t = self.h.task('DEMO-001')
        t['outcome'] = 'No production impact. Update local documentation.'
        atomic(self.root/'specs/harness-demo/tasks.json', f)
        self.assertEqual(self.assess()['minimum'], 'FAST')
        t['outcome'] = 'May change production permissions.'
        atomic(self.root/'specs/harness-demo/tasks.json', f)
        self.assertTrue(self.assess()['deeper_required'])

    def test_source_identifiers_override_negative_comments_and_match_boundaries(self):
        path = self.root/'sample.py'
        cases = [
            ('# No authentication.\ndef author_name():\n    return "author"\n', 'FAST'),
            ('# No authentication.\ndef authorize_user(user):\n    return True\n', 'STRICT'),
            ('function authenticateUser(user) { return true; }', 'STRICT'),
            ('const authorizationPolicy = true;', 'STRICT'),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                path.write_text(source)
                self.assertEqual(self.assess(inspected=['sample.py'])['minimum'], expected)

    def test_known_metadata_and_previous_advisor_conclusions_do_not_reinforce_risk(self):
        self.assess()
        f, t = self.h.task('DEMO-001')
        t['workflow']['reasons'] = ['High security/production risk']
        t['workflow']['plan'] = 'Implement authentication checks.'
        atomic(self.root/'specs/harness-demo/tasks.json', f)
        result = self.assess(inspected=['specs/harness-demo/tasks.json'])
        self.assertEqual(result['minimum'], 'FAST')
        self.assertFalse(result['deeper_required'])
        self.assertEqual(self.assess(inspected=['specs/harness-demo/tasks.json'])['minimum'], 'FAST')
        atomic(self.root/'.harness/onboarding.json', {
            'sources': [{'authorization': 'Authenticated developer authorizes metadata inspection.'}],
            'approval': {'reference': 'security-review.md'},
            'coverage': {'security': {'rationale': 'No authentication.'}}})
        self.assertEqual(self.assess(inspected=['.harness/onboarding.json'])['minimum'], 'FAST')
        data = json.loads((self.root/'.harness/onboarding.json').read_text())
        data['coverage']['security']['rationale'] = 'Implement authentication checks.'
        atomic(self.root/'.harness/onboarding.json', data)
        self.assertEqual(self.assess(inspected=['.harness/onboarding.json'])['minimum'], 'STRICT')

    def test_arbitrary_json_cannot_hide_sensitive_content_as_generated_metadata(self):
        atomic(self.root/'settings.json', {'workflow': {'authorization': 'enforce permissions'}})
        self.assertEqual(self.assess(inspected=['settings.json'])['minimum'], 'STRICT')

    def test_negative_text_never_overrides_structured_or_project_strict_floors(self):
        (self.root/'docs/DEMO.md').write_text('No authentication. No production impact.')
        self.assertEqual(self.assess(critical_risk=True)['minimum'], 'STRICT')
        atomic(self.root/'.harness/workflow-policy.json', {'minimum': 'STRICT'})
        self.assertEqual(self.assess()['minimum'], 'STRICT')
        atomic(self.root/'.harness/workflow-policy.json', {'strict_paths': ['docs/*']})
        self.assertEqual(self.assess()['minimum'], 'STRICT')
        atomic(self.root/'.harness/workflow-policy.json', {})
        f, t = self.h.task('DEMO-001'); t['risk'] = 'high'
        atomic(self.root/'specs/harness-demo/tasks.json', f)
        self.assertEqual(self.assess()['minimum'], 'STRICT')

    def test_guards_allow_negatives_but_block_new_ambiguity_and_sensitive_code(self):
        (self.root/'docs/DEMO.md').write_text('No authentication. No production impact.')
        self.assess(); self.confirm(); self.h.transition('DEMO-001', 'IN_PROGRESS', 'fixture')
        f, t = self.h.task('DEMO-001'); workflow.guard(self.h, f, t)
        (self.root/'docs/DEMO.md').write_text('Authentication impact is unknown.')
        with self.assertRaisesRegex(HarnessError, 'Deeper'):
            workflow.guard(self.h, f, t)
        (self.root/'docs/DEMO.md').write_text('Implement authentication checks.')
        with self.assertRaisesRegex(HarnessError, 'reassessment'):
            workflow.guard(self.h, f, t)

    def test_confirmation_rechecks_evidence_without_recording_ambiguous_consent(self):
        self.assess()
        (self.root/'docs/DEMO.md').write_text('May affect production permissions.')
        with self.assertRaisesRegex(HarnessError, 'unknown'):
            self.confirm('STRICT')
        self.assertIsNone(self.h.task('DEMO-001')[1]['workflow']['selected'])
        self.assertEqual(self.h.task('DEMO-001')[1]['approvals'], {})

    def test_confirmation_rechecks_new_positive_source_and_scope_before_selection(self):
        f, t = self.h.task('DEMO-001'); t['scope'].append('new_module.py')
        atomic(self.root/'specs/harness-demo/tasks.json', f)
        self.assess()
        (self.root/'new_module.py').write_text('def authenticate_user(user):\n    return True\n')
        with self.assertRaisesRegex(HarnessError, 'minimum'):
            self.confirm('FAST')
        self.assertIsNone(self.h.task('DEMO-001')[1]['workflow']['selected'])

    def test_oversize_guard_evidence_requires_investigation_instead_of_skipping(self):
        self.assess(); self.confirm()
        (self.root/'docs/DEMO.md').write_text('x' * 65537)
        f, t = self.h.task('DEMO-001')
        with self.assertRaisesRegex(HarnessError, 'inspection limit'):
            workflow.guard(self.h, f, t)

    def test_public_exposure_and_medium_risk_are_distinct_from_security_floor(self):
        self.assertEqual(self.assess(public_api=True)['minimum'], 'STANDARD')
        f, t = self.h.task('DEMO-001'); t['risk'] = 'medium'
        atomic(self.root/'specs/harness-demo/tasks.json', f)
        result = self.assess(public_api=False)
        self.assertEqual(result['minimum'], 'FAST')
        self.assertEqual(result['recommended'], 'STANDARD')

    def test_classifier_revision_invalidates_old_decisions(self):
        self.assess(); self.confirm()
        with patch.object(workflow, 'RISK_CLASSIFIER_VERSION', 0):
            f, t = self.h.task('DEMO-001')
            with self.assertRaisesRegex(HarnessError, 'reassessment'):
                workflow.guard(self.h, f, t)

    def test_confirmation_required_and_combines_plan(self):
        self.assess()
        with self.assertRaisesRegex(HarnessError,'confirmation'): self.h.transition('DEMO-001','IN_PROGRESS','unauthorized')
        self.confirm(); self.h.transition('DEMO-001','IN_PROGRESS','confirmed')
        t=self.h.task('DEMO-001')[1]
        self.assertEqual(set(t['approvals']),{'workflow-plan'})
        self.assertEqual(reporting.task_report(self.h,'DEMO-001')['approvals']['plan']['status'],'CURRENT')

    def test_floor_and_stricter_or_simpler_selection(self):
        self.assess(components=3); self.confirm('FAST')
        self.confirm('STRICT')
        self.assess(critical_risk=True)
        with self.assertRaisesRegex(HarnessError,'minimum'): self.confirm('STANDARD')
        self.confirm('STRICT')

    def test_unknowns_require_targeted_inspection_not_automatic_strict(self):
        r=self.assess(unknowns=['Exact formatting convention']); self.assertEqual(r['recommended'],'STANDARD'); self.confirm('FAST')
        r=self.assess(critical_unknowns=['Does this authorize access?'])
        self.assertNotEqual(r['recommended'],'STRICT')
        with self.assertRaisesRegex(HarnessError,'unknown'): self.confirm()

    def test_missing_inspection_blocks_low_risk_confirmation(self):
        self.assess(inspected=[])
        with self.assertRaises(HarnessError): self.confirm()

    def test_material_changes_invalidate_but_implementation_does_not(self):
        self.assess(); self.confirm(); self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        (self.root/'docs/DEMO.md').write_text('Use checkpoint and resume; updated implementation.\n')
        f,t=self.h.task('DEMO-001'); workflow.guard(self.h,f,t)
        (self.root/'specs/harness-demo/plan.md').write_text((self.root/'specs/harness-demo/plan.md').read_text()+'Material requirement change.\n')
        f,t=self.h.task('DEMO-001')
        with self.assertRaisesRegex(HarnessError,'reassessment'): workflow.guard(self.h,f,t)

    def test_identical_assessment_preserves_confirmation(self):
        self.assess(); self.confirm()
        before=self.h.task('DEMO-001')[1]
        self.assess(); after=self.h.task('DEMO-001')[1]
        self.assertEqual(before,after)

    def test_policy_change_invalidates_and_project_checks_cannot_be_omitted(self):
        self.assess();self.confirm()
        atomic(self.root/'.harness/workflow-policy.json',{'minimum':'STRICT','required_checks':['security']})
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','IN_PROGRESS','stale')
        self.assess();self.confirm('STRICT')
        with self.assertRaisesRegex(HarnessError,'mandatory project checks'): self.h.transition('DEMO-001','IN_PROGRESS','omitted')

    def test_fast_keeps_tests_review_and_final_approval(self):
        self.assess();self.confirm(); self.implemented()
        with self.assertRaises(HarnessError): self.h.transition('DEMO-001','VERIFIED','no evidence')
        self.assertEqual(self.h.verify('DEMO-001')['result'],'PASS')
        self.h.transition('DEMO-001','VERIFIED','checks passed')
        (self.root/'specs/harness-demo/reviews').mkdir(exist_ok=True)
        (self.root/'specs/harness-demo/reviews/review.md').write_text(self.review_text())
        self.h.approve('DEMO-001','review','fixture','specs/harness-demo/reviews/review.md')
        with self.assertRaisesRegex(HarnessError,'developer'): self.h.transition('DEMO-001','DONE','no final consent')
        self.h.approve('DEMO-001','developer','fixture','.harness/consent.txt')
        self.h.transition('DEMO-001','DONE','simulated final consent')
        self.assertEqual(reporting.task_report(self.h,'DEMO-001')['status'],'DONE')

    def test_reports_real_files_paths_and_missing_evidence(self):
        self.assess();self.confirm();self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        (self.root/'docs/DEMO.md').write_text('checkpoint and resume; modified\n')
        r=reporting.task_report(self.h,'DEMO-001')
        self.assertTrue(r['paths']['temporary']); self.assertEqual(r['verification']['status'],'MISSING')
        self.assertEqual(r['changed_files'][0]['absolute_path'],str((self.root/'docs/DEMO.md').resolve()))
        data=reporting.report(self.h,'DEMO-001',retain=True)
        from pathlib import Path
        self.assertTrue((Path(data['tasks'][0]['paths']['review_package'])/'report.md').exists())
        self.assertEqual(json.loads(json.dumps(data))['tasks'][0]['status'],'IN_PROGRESS')

    def test_reference_edit_invalidates_combined_consent(self):
        self.assess(); self.confirm(); (self.root/'.harness/consent.txt').write_text('Changed reference')
        with self.assertRaisesRegex(HarnessError,'approval'): self.h.transition('DEMO-001','IN_PROGRESS','stale')

    def test_sensitive_task_metadata_cannot_claim_fast(self):
        f,t=self.h.task('DEMO-001');t['outcome']='Fix authentication validation'
        atomic(self.root/'specs/harness-demo/tasks.json',f)
        self.assertEqual(self.assess()['minimum'],'STRICT')
        with self.assertRaises(HarnessError): self.confirm()

    def test_new_template_requires_assessment_before_start(self):
        f,t=self.h.task('DEMO-001');t['workflow_required']=True
        atomic(self.root/'specs/harness-demo/tasks.json',f)
        with self.assertRaisesRegex(HarnessError,'assessment'): self.h.transition('DEMO-001','IN_PROGRESS','no assessment')
        self.assess();self.confirm();self.h.transition('DEMO-001','IN_PROGRESS','confirmed')

    def test_broad_directory_scope_cannot_avoid_strict_glob(self):
        atomic(self.root/'.harness/workflow-policy.json',{'strict_paths':['**/auth.py']})
        f,t=self.h.task('DEMO-001');t['scope']=['docs/']
        atomic(self.root/'specs/harness-demo/tasks.json',f)
        self.assertEqual(self.assess()['minimum'],'STRICT')

    def test_final_consent_requires_prior_review(self):
        self.assess();self.confirm();self.implemented();self.h.verify('DEMO-001');self.h.transition('DEMO-001','VERIFIED','checks')
        with self.assertRaisesRegex(HarnessError,'review first'): self.h.approve('DEMO-001','developer','fixture','.harness/consent.txt')

    def test_external_review_snapshot_survives_source_deletion(self):
        from pathlib import Path
        import tempfile, shutil
        self.assess();self.confirm();self.h.transition('DEMO-001','IN_PROGRESS','fixture')
        (self.root/'docs/DEMO.md').write_text('checkpoint resume changed')
        with tempfile.TemporaryDirectory() as external:
            data=reporting.report(self.h,'DEMO-001',retain=True,retain_dir=Path(external).resolve())
            dest=Path(data['tasks'][0]['paths']['review_package'])
            shutil.rmtree(self.root)
            self.assertEqual((dest/'files/docs/DEMO.md').read_text(),'checkpoint resume changed')
            self.assertTrue((dest/'report.json').exists())

    def test_report_distinguishes_optional_approvals_and_legacy_plan(self):
        r=reporting.task_report(self.h,'DEMO-001')
        self.assertEqual(r['approvals']['plan']['status'],'DOCUMENT_APPROVED')
        self.assertEqual(r['approvals']['implementation']['status'],'NOT_REQUIRED')
        self.assertEqual(r['approvals']['review']['status'],'NOT_RECORDED')

# Avoid repeating inherited tests while reusing their fixture helpers.
for _name in list(dir(test_harness.HarnessTests)):
    if _name.startswith('test_') and _name not in WorkflowTests.__dict__:
        setattr(WorkflowTests,_name,None)

import test_onboarding

class ApplicationWorkflowTests(test_onboarding.OnboardingTests):
    def adaptive(self, profile='FAST', **facts):
        self.prepare(); self.approve()
        from harnesslib.storage import read
        f,t=self.h.task('CALC-001'); t['risk']='low'
        atomic(self.root/'specs/calculator/tasks.json',f)
        value=dict(critical_risk=False,critical_unknowns=[],unknowns=[],public_api=False,architecture_change=False,components=1,inspected=['calculator.py'],agent='fixture')
        value.update(facts);atomic(self.root/'.harness/facts.json',value)
        workflow.assess(self.h,'CALC-001','.harness/facts.json')
        workflow.confirm(self.h,'CALC-001',profile,'fixture','docs/approval.md')

    def test_fast_application_keeps_onboarding_and_required_checks(self):
        self.adaptive(); self.h.transition('CALC-001','IN_PROGRESS','fixture')
        self.h.transition('CALC-001','IMPLEMENTED','fixture')
        self.assertEqual(self.h.verify('CALC-001')['result'],'PASS')

    def test_strict_application_requires_openspec(self):
        self.adaptive('STRICT')
        with self.assertRaisesRegex(HarnessError,'OpenSpec'): self.h.transition('CALC-001','IN_PROGRESS','fixture')

    def test_policy_separate_plan_approval(self):
        atomic(self.root/'.harness/workflow-policy.json',{'separate_plan_approval':True})
        self.adaptive()
        with self.assertRaisesRegex(HarnessError,'plan approval'): self.h.transition('CALC-001','IN_PROGRESS','fixture')
        self.h.approve('CALC-001','plan','fixture','docs/approval.md')
        self.h.transition('CALC-001','IN_PROGRESS','fixture')

    def test_sensitive_inspected_content_sets_floor_independently(self):
        self.adaptive()
        (self.root/'calculator.py').write_text('def authorize(user):\n    return True\n')
        # Engine examines sensitive code, not just agent-provided critical_risk=false.
        r=workflow.assess(self.h,'CALC-001','.harness/facts.json')
        self.assertEqual(r['minimum'],'STRICT')

    def test_material_sensitive_implementation_blocks_fast(self):
        self.adaptive(); self.h.transition('CALC-001','IN_PROGRESS','fixture')
        (self.root/'calculator.py').write_text('def authenticate(user):\n    return True\n')
        with self.assertRaisesRegex(HarnessError,'reassessment'): self.h.transition('CALC-001','IMPLEMENTED','expanded risk')

    def test_policy_openspec_required_even_for_fast(self):
        atomic(self.root/'.harness/workflow-policy.json',{'openspec_required':True})
        self.adaptive()
        with self.assertRaisesRegex(HarnessError,'OpenSpec'): self.h.transition('CALC-001','IN_PROGRESS','fixture')

    def test_report_missing_evidence_file_stays_readable(self):
        self.adaptive();self.h.transition('CALC-001','IN_PROGRESS','fixture');self.h.transition('CALC-001','IMPLEMENTED','fixture');self.h.verify('CALC-001')
        ref=self.h.task('CALC-001')[1]['evidence'][-1];(self.root/ref).unlink()
        r=reporting.task_report(self.h,'CALC-001')
        self.assertEqual(r['verification']['status'],'MISSING')
        self.assertTrue(any('unavailable' in x for x in r['warnings']))

    def test_log_tampering_invalidates_evidence(self):
        self.adaptive();self.h.transition('CALC-001','IN_PROGRESS','fixture');self.h.transition('CALC-001','IMPLEMENTED','fixture');self.h.verify('CALC-001')
        t=self.h.task('CALC-001')[1];ev=self.h.evidence(t['evidence'][-1])
        (self.root/ev['results'][0]['log']).write_text('altered')
        self.assertFalse(self.h.current_evidence(t))

for _name in list(dir(test_onboarding.OnboardingTests)):
    if _name.startswith('test_') and _name not in ApplicationWorkflowTests.__dict__:
        setattr(ApplicationWorkflowTests,_name,None)
