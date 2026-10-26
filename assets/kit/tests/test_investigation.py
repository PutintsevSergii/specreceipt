"""Investigation evidence is bounded, stale on changed inputs, and honest about host MCP use."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import unittest

from harnesslib import investigation
from harnesslib import readiness
from harnesslib.storage import HarnessError, atomic, digest, read
import test_harness


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        fixture = test_harness.HarnessTests('runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root, self.h = fixture.root, fixture.h
        self.task = self.h.task('DEMO-001')[1]
        self.now = datetime.now(timezone.utc).isoformat()

    def report(self, result='NO_MCP'):
        rel = 'docs/DEMO.md'
        source = self.root / rel
        return {'schema_version': 1, 'task_id': 'DEMO-001', 'question': self.task['outcome'],
                'definition': self.h.definition(self.task), 'repository_fingerprint': digest(self.h.fingerprints()),
                'policy_hash': digest(investigation.policy(self.h)),
                'host_trace': None, 'tools': [], 'claims': [{
                    'id': 'C-1', 'criterion': self.task['acceptance_criteria'][0],
                    'summary': 'The fixture documents checkpoint and resume.', 'category': None,
                    'result': result, 'code': [{'path': rel, 'line': 1,
                        'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}], 'mcp': []}]}

    def save(self, report):
        atomic(self.root/'.harness/candidate-investigation.json', report)
        return investigation.record(self.h, 'DEMO-001', '.harness/candidate-investigation.json')

    def mcp(self, report, status='available', source_status='success'):
        report['tools'] = [{'name': 'contracts.read', 'status': status, 'read_only': True,
                            'reason': 'Relevant contract source for this claim'}]
        report['claims'][0]['category'] = 'api-contract'
        report['claims'][0]['result'] = 'AGREE' if source_status == 'success' else 'UNVERIFIED'
        report['claims'][0]['mcp'] = [{'tool': 'contracts.read', 'resource': 'contract://demo',
                                      'revision': 'r1' if source_status == 'success' else None, 'observed_at': self.now,
                                      'summary': 'Contract matches the repository statement.',
                                      'status': source_status}]
        return report

    def policy(self):
        atomic(self.root/'.harness/investigation-policy.json',
               {'schema_version': 1, 'required_sources': [{'category': 'api-contract', 'tasks': ['DEMO-001']}]})

    def current(self, revision='r1'):
        atomic(self.root/'.harness/investigations/DEMO-001.current.json',
               {'schema_version': 1, 'task_id': 'DEMO-001', 'observed_at': self.now,
                'sources': [{'resource': 'contract://demo', 'revision': revision}]})

    def test_optional_no_mcp_is_explicit_and_code_changes_stale_report(self):
        self.save(self.report())
        result = investigation.check(self.h, 'DEMO-001')
        self.assertEqual((result['result'], result['coverage']), ('PASS', 'NO_MCP'))
        (self.root/'docs/DEMO.md').write_text('Changed behavior.\n')
        with self.assertRaisesRegex(HarnessError, 'repository fingerprint changed'):
            investigation.check(self.h, 'DEMO-001')

    def test_required_source_must_be_current_and_agree(self):
        self.policy()
        report = self.mcp(self.report())
        report['policy_hash'] = digest(investigation.policy(self.h))
        self.save(report)
        self.assertEqual(investigation.check(self.h, 'DEMO-001')['result'], 'BLOCKED')
        self.current()
        self.assertEqual(investigation.check(self.h, 'DEMO-001')['result'], 'PASS')
        self.current('r2')
        self.assertIn('revision', ' '.join(investigation.check(self.h, 'DEMO-001')['gaps']))

    def test_optional_success_also_needs_current_revision(self):
        self.save(self.mcp(self.report()))
        self.assertIn('Current MCP revision unavailable', ' '.join(investigation.check(self.h, 'DEMO-001')['gaps']))
        self.current()
        self.assertEqual(investigation.check(self.h, 'DEMO-001')['result'], 'PASS')
        current = read(self.root/'.harness/investigations/DEMO-001.current.json')
        current['observed_at'] = (datetime.fromisoformat(self.now) - timedelta(seconds=1)).isoformat()
        atomic(self.root/'.harness/investigations/DEMO-001.current.json', current)
        self.assertIn('predates claim', ' '.join(investigation.check(self.h, 'DEMO-001')['gaps']))

    def test_denied_and_conflict_block_required_claim(self):
        self.policy()
        denied = self.mcp(self.report(), status='denied', source_status='denied')
        denied['policy_hash'] = digest(investigation.policy(self.h))
        self.save(denied)
        self.assertEqual(investigation.check(self.h, 'DEMO-001')['result'], 'BLOCKED')
        conflict = self.mcp(self.report())
        conflict['policy_hash'] = digest(investigation.policy(self.h))
        conflict['claims'][0]['result'] = 'CONFLICT'
        self.save(conflict)
        self.current()
        self.assertEqual(investigation.check(self.h, 'DEMO-001')['coverage'], 'CONFLICT')
        self.assertEqual(investigation.check(self.h, 'DEMO-001')['result'], 'BLOCKED')

    def test_configured_only_and_secret_candidate_preserve_previous_report(self):
        self.save(self.report())
        original = read(self.root/investigation.report_ref('DEMO-001'))
        configured = self.mcp(self.report(), status='configured_only')
        with self.assertRaisesRegex(HarnessError, 'Configured-only'):
            self.save(configured)
        secret = copy.deepcopy(self.report())
        secret['claims'][0]['summary'] = 'Bearer secret-token-value'
        with self.assertRaisesRegex(HarnessError, 'sanitized'):
            self.save(secret)
        self.assertEqual(read(self.root/investigation.report_ref('DEMO-001')), original)

    def test_policy_or_question_change_stales_report(self):
        self.save(self.report())
        self.policy()
        with self.assertRaisesRegex(HarnessError, 'source policy changed'):
            investigation.check(self.h, 'DEMO-001')

    def test_required_source_gap_reaches_readiness(self):
        self.policy()
        feature, task = self.h.task('DEMO-001')
        self.assertIn('Investigation: Task investigation report is missing', readiness.task_gaps(self.h, feature, task))

    def test_irrelevant_tool_is_not_mcp_confirmation(self):
        report = self.report()
        report['tools'] = [{'name': 'tickets.read', 'status': 'irrelevant', 'read_only': True,
                            'reason': 'Ticket data does not define this repository behavior'}]
        self.save(report)
        result = investigation.check(self.h, 'DEMO-001')
        self.assertEqual((result['result'], result['coverage']), ('PASS', 'NO_MCP'))

    def test_stale_host_observation_cannot_confirm_required_source(self):
        self.policy()
        report = self.mcp(self.report())
        report['policy_hash'] = digest(investigation.policy(self.h))
        self.save(report)
        self.current()
        current = read(self.root/'.harness/investigations/DEMO-001.current.json')
        current['observed_at'] = '2000-01-01T00:00:00+00:00'
        atomic(self.root/'.harness/investigations/DEMO-001.current.json', current)
        with self.assertRaisesRegex(HarnessError, 'at most 24 hours'):
            investigation.check(self.h, 'DEMO-001')


if __name__ == '__main__':
    unittest.main()
