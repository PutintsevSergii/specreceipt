"""Story coordination with real lifecycle/check execution in isolated projects."""
import copy
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import test_openspec
from harnesslib import stories, openspec_tool, runner, readiness
from harnesslib.storage import HarnessError, atomic, read


class StoryTests(unittest.TestCase):
    def setUp(self):
        fixture = test_openspec.OpenSpecTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        if os.environ.get('HARNESS_TEST_OPENSPEC'):
            env = patch.dict(os.environ, {'PATH': str(Path(os.environ['HARNESS_TEST_OPENSPEC']).absolute().parent) + os.pathsep + os.environ['PATH']})
            env.start(); self.addCleanup(env.stop)
        self.root, self.h = fixture.root, fixture.h
        self.criterion = fixture.mapping['tasks'][0]['acceptance_criteria'][0]
        self.definition = {'schema_version': 1, 'id': 'arithmetic', 'goal': 'Reliable arithmetic in two reviewed slices.',
                           'scope': ['Integer arithmetic only'], 'requirements': ['REQ-001'],
                           'contracts': ['docs/ARCHITECTURE.md'],
                           'blocks': [{'id': 'first', 'feature': 'calculator', 'outcome': 'First arithmetic slice works.',
                                       'requirements': ['REQ-001'], 'acceptance': [self.criterion], 'dependencies': []},
                                      {'id': 'second', 'feature': 'calculator-second', 'outcome': 'Second arithmetic slice works.',
                                       'requirements': ['REQ-001'], 'acceptance': [self.criterion], 'dependencies': ['first']}],
                           'integration_feature': 'calculator-integration', 'integration': [self.criterion]}
        # References are test-only human decisions, created before task execution.
        self.reference = '.harness/story-decision.md'
        (self.root/self.reference).write_text('Isolated fixture developer reviewed this exact decision package and explicitly approves its stated scope.\n')

    def propose(self, definition=None):
        definition = definition or self.definition
        preview = stories.propose(self.h, definition)
        return stories.propose(self.h, definition, True, preview['proposal_binding'])

    def approve(self):
        card = stories.status(self.h, 'arithmetic')
        stories.approve_map(self.h, 'arithmetic', 'fixture developer', self.reference, card['map_binding'])

    def import_feature(self, number):
        if number == 1:
            self.fixture.imported(True)
            return 'CALC-001'
        feature_id = 'calculator-second' if number == 2 else 'calculator-integration'
        change = 'second-calculator' if number == 2 else 'integrated-calculator'
        shutil.copytree(self.root/'openspec/changes/add-calculator', self.root/'openspec/changes'/change)
        mapping = copy.deepcopy(self.fixture.mapping)
        mapping['feature_id'] = feature_id
        mapping['tasks'][0]['id'] = 'CALC-00' + str(number)
        atomic(self.root/'.harness/next-mapping.json', mapping)
        openspec_tool.import_change(self.h, change, '.harness/next-mapping.json')
        for name in ('spec.md', 'plan.md'):
            p = self.root/'specs'/feature_id/name
            p.write_text(p.read_text().replace('Status: DRAFT', 'Status: APPROVED').replace('Approval: TBD', 'Approval: isolated fixture developer approval'))
        self.fixture.fixture.approve()
        return mapping['tasks'][0]['id']

    def complete(self, task_id):
        self.h.transition(task_id, 'IN_PROGRESS', 'isolated approved fixture')
        self.h.transition(task_id, 'IMPLEMENTED', 'fixture result ready')
        evidence = self.h.verify(task_id)
        self.assertEqual(evidence['result'], 'PASS', evidence['results'])
        self.h.transition(task_id, 'VERIFIED', 'fixture checks passed')
        feature, task = self.h.task(task_id)
        ref = 'specs/' + feature['feature_id'] + '/reviews/review.md'
        p = self.root/ref; p.parent.mkdir(exist_ok=True)
        p.write_text('```harness-review\n' + json.dumps({'task_id': task_id, 'reviewer': 'isolated reviewer',
            'evidence': task['evidence'][-1], 'verdict': 'PASS', 'summary': 'Reviewed arithmetic behavior and actual assertion results.', 'findings': []}) + '\n```\n')
        self.h.approve(task_id, 'review', 'fixture reviewer', ref)
        self.h.transition(task_id, 'DONE', 'fixture review passed')

    def accept_block(self, block):
        card = stories.package(self.h, 'arithmetic', block)
        self.assertEqual(card['blockers'], [])
        return stories.accept(self.h, 'arithmetic', block, 'fixture developer', self.reference, card['binding'])

    def test_preview_validation_and_stale_confirmation(self):
        preview = stories.propose(self.h, self.definition)
        self.assertFalse((self.root/'.harness/stories').exists())
        with self.assertRaisesRegex(HarnessError, 'Preview'):
            stories.propose(self.h, self.definition, True, 'wrong')
        self.propose(); self.approve()
        for mutate in ('cycle', 'missing', 'duplicate', 'coverage', 'path'):
            d = copy.deepcopy(self.definition)
            if mutate == 'cycle': d['blocks'][0]['dependencies'] = ['second']
            if mutate == 'missing': d['blocks'][0]['dependencies'] = ['unknown']
            if mutate == 'duplicate': d['blocks'][1]['feature'] = 'calculator'
            if mutate == 'coverage': d['requirements'].append('REQ-002')
            if mutate == 'path': d['id'] = '../../escape'
            with self.assertRaises(HarnessError): stories.propose(self.h, d)
        changed = copy.deepcopy(self.definition); changed['goal'] += ' Updated.'
        self.propose(changed)
        with self.assertRaises(HarnessError):
            stories.approve_map(self.h, 'arithmetic', 'fixture', self.reference, preview['proposal_binding'])
        self.assertEqual(stories.status(self.h, 'arithmetic')['status'], 'DRAFT')
        self.assertEqual(len(list((self.root/'.harness/story-history').glob('*.json'))), 1)

    def test_draft_dependencies_and_mapping_gates(self):
        self.propose(); first = self.import_feature(1)
        with self.assertRaisesRegex(HarnessError, 'map approval'):
            self.h.transition(first, 'IN_PROGRESS', 'cannot bypass map')
        self.approve(); second = self.import_feature(2)
        with self.assertRaisesRegex(HarnessError, 'predecessor'):
            self.h.transition(second, 'IN_PROGRESS', 'cannot bypass predecessor')
        self.assertTrue(any('predecessor' in gap for gap in readiness.task_gaps(self.h, *self.h.task(second))))
        self.assertEqual(stories.package(self.h, 'arithmetic', 'first')['result'], 'BLOCKED')
        with self.assertRaises(HarnessError): self.accept_block_without_assert('first')

    def accept_block_without_assert(self, block):
        return stories.accept(self.h, 'arithmetic', block, 'fixture', self.reference, 'unverified')

    def test_progressive_import_acceptance_and_final_regression(self):
        self.propose(); self.approve()
        first = self.import_feature(1); self.complete(first); self.accept_block('first')
        first_definition = self.h.definition(self.h.task(first)[1])
        # Importing the next detailed OpenSpec adds a structural check and renews onboarding.
        second = self.import_feature(2)
        self.assertEqual(first_definition, self.h.definition(self.h.task(first)[1]))
        self.assertTrue(self.h.completed(self.h.task(first)[1]))
        self.assertEqual(stories.status(self.h, 'arithmetic')['blocks'][0]['status'], 'ACCEPTED')
        self.complete(second); self.accept_block('second')
        integration = self.import_feature(3); self.complete(integration)
        self.assertEqual(stories.status(self.h, 'arithmetic')['status'], 'ACTIVE')
        self.assertEqual(stories.package(self.h, 'arithmetic')['result'], 'BLOCKED')
        for task_id in (first, second, integration):
            self.assertEqual(self.h.verify(task_id, regression=True)['result'], 'PASS')
        card = stories.package(self.h, 'arithmetic')
        self.assertEqual(card['blockers'], [])
        stories.accept(self.h, 'arithmetic', None, 'fixture developer', self.reference, card['binding'])
        self.assertEqual(stories.status(self.h, 'arithmetic')['status'], 'DONE')
        self.assertEqual(runner.next_action(self.h)['action'], 'finished')
        (self.root/'calculator.py').write_text('def add(a,b):\n    return a-b\n')
        self.assertEqual(stories.status(self.h, 'arithmetic')['status'], 'ACTIVE')
        self.assertEqual(stories.package(self.h, 'arithmetic')['result'], 'BLOCKED')

    def test_common_contract_change_invalidates_definition_and_map(self):
        self.propose(); self.approve(); first = self.import_feature(1)
        self.complete(first); self.accept_block('first')
        original = self.h.definition(self.h.task(first)[1])
        p = self.root/'docs/ARCHITECTURE.md'; p.write_text(p.read_text() + '\nShared contract changed.\n')
        self.assertNotEqual(original, self.h.definition(self.h.task(first)[1]))
        self.assertFalse(self.h.completed(self.h.task(first)[1]))
        self.assertEqual(stories.status(self.h, 'arithmetic')['status'], 'DRAFT')

    def test_future_block_map_edit_preserves_prior_definition(self):
        self.propose(); self.approve(); first = self.import_feature(1)
        self.complete(first); self.accept_block('first')
        original = self.h.definition(self.h.task(first)[1])
        d = copy.deepcopy(self.definition); d['blocks'][1]['outcome'] += ' With clearer diagnostics.'
        self.propose(d)
        self.assertEqual(original, self.h.definition(self.h.task(first)[1]))
        self.approve()
        self.assertEqual(stories.status(self.h, 'arithmetic')['blocks'][0]['status'], 'ACCEPTED')

    def test_selected_check_change_invalidates_prior_completion(self):
        self.propose(); self.approve(); first = self.import_feature(1)
        self.complete(first); self.accept_block('first')
        cfg = read(self.root/'.harness/checks.json')
        cfg['checks']['application-unit']['argv'] += ['changed']
        atomic(self.root/'.harness/checks.json', cfg)
        self.assertFalse(self.h.completed(self.h.task(first)[1]))
        self.assertNotEqual(stories.status(self.h, 'arithmetic')['blocks'][0]['status'], 'ACCEPTED')

    def test_decision_reference_and_result_binding_cannot_be_reused(self):
        self.propose(); self.approve(); first = self.import_feature(1)
        self.complete(first)
        old = stories.package(self.h, 'arithmetic', 'first')
        (self.root/'calculator.py').write_text('def add(a,b):\n    return sum((a,b))\n')
        self.assertEqual(self.h.verify(first, regression=True)['result'], 'PASS')
        with self.assertRaisesRegex(HarnessError, 'package changed'):
            stories.accept(self.h, 'arithmetic', 'first', 'fixture', self.reference, old['binding'])
        self.accept_block('first')
        (self.root/self.reference).write_text('Changed reference; the original recorded developer answer is no longer available.')
        self.assertEqual(stories.status(self.h, 'arithmetic')['status'], 'DRAFT')
        self.assertNotEqual(stories.status(self.h, 'arithmetic')['blocks'][0]['status'], 'ACCEPTED')

    def test_executed_feature_cannot_be_detached_and_ownership_is_unique(self):
        self.propose(); self.approve(); first = self.import_feature(1); self.complete(first)
        d = copy.deepcopy(self.definition); d['blocks'][0]['feature'] = 'replacement'
        with self.assertRaisesRegex(HarnessError, 'detach'):
            self.propose(d)
        d = copy.deepcopy(self.definition); d['id'] = 'other-story'
        with self.assertRaisesRegex(HarnessError, 'another story'):
            stories.propose(self.h, d)
        record = read(self.root/'.harness/stories/arithmetic.json')
        record['map_approval']['binding'] = False
        atomic(self.root/'.harness/stories/arithmetic.json', record)
        with self.assertRaises(HarnessError): self.h.validate()

    def test_map_change_during_check_is_not_pass_evidence(self):
        self.propose(); self.approve(); first = self.import_feature(1)
        self.h.transition(first, 'IN_PROGRESS', 'fixture approved')
        self.h.transition(first, 'IMPLEMENTED', 'fixture implemented')
        original = self.h.run_check
        def change_map(name, config):
            result = original(name, config)
            record = read(self.root/'.harness/stories/arithmetic.json')
            record['definition']['goal'] += ' Changed during execution.'
            atomic(self.root/'.harness/stories/arithmetic.json', record)
            return result
        with patch.object(self.h, 'run_check', side_effect=change_map):
            evidence = self.h.verify(first)
        self.assertEqual(evidence['result'], 'FAIL')
        self.assertTrue(any(r['check'] == 'stable-inputs' for r in evidence['results']))

    def test_interrupted_state_blocks_acceptance_and_recovery_preserves_map(self):
        from harnesslib.storage import finish_transaction
        self.propose(); self.approve(); first = self.import_feature(1); self.complete(first)
        record = read(self.root/'.harness/stories/arithmetic.json')
        atomic(self.root/'.harness/transaction.json', {'writes': {'.harness/stories/arithmetic.json': record},
            'event': self.h.event('story-updated', 'Isolated interrupted story transaction')})
        card = stories.package(self.h, 'arithmetic', 'first')
        self.assertTrue(any('interrupted' in gap for gap in card['blockers']))
        self.assertTrue(finish_transaction(self.root))
        self.assertEqual(record, read(self.root/'.harness/stories/arithmetic.json'))
        self.accept_block('first')

    def test_cli_resume_readonly_and_next_story(self):
        self.propose()
        before = {p: p.read_bytes() for p in (self.root/'.harness/stories/arithmetic.json', self.root/'.harness/state.json')}
        command = [sys.executable, '-B', str(self.root/'harness'), '--root', str(self.root), 'story', 'status', 'arithmetic', '--format', 'markdown']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('approve-map', result.stdout)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(runner.next_action(self.h)['action'], 'story-decision')


if __name__ == '__main__': unittest.main()
