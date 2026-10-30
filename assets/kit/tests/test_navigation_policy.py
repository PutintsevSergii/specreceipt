"""Navigation policy is separate from workflow quality and fails closed."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from harnesslib import index_context
from harnesslib.storage import atomic, HarnessError


class NavigationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def policy(self, mode, providers):
        atomic(self.root / '.harness/navigation.json',
               {'schema_version': 1, 'mode': mode, 'providers': providers})

    def test_source_never_invokes_providers(self):
        self.policy('source', [])
        with patch.object(index_context.codegraph_tool, 'ensure') as code, \
             patch.object(index_context.graphify_tool, 'ensure') as graph:
            self.assertEqual(index_context.ensure(self.root)['result'], 'PASS')
        code.assert_not_called()
        graph.assert_not_called()

    def test_required_provider_is_individual(self):
        for name in ('codegraph', 'graphify'):
            self.policy('required', [name])
            with patch.object(index_context.codegraph_tool, 'ensure', return_value={'freshness': 'fresh'}) as code, \
                 patch.object(index_context.graphify_tool, 'ensure', return_value={'freshness': 'fresh'}) as graph:
                index_context.ensure(self.root)
                self.assertEqual(code.call_count, int(name == 'codegraph'))
                self.assertEqual(graph.call_count, int(name == 'graphify'))

    def test_legacy_requires_both(self):
        with patch.object(index_context.codegraph_tool, 'ensure', return_value={'freshness': 'fresh'}) as code, \
             patch.object(index_context.graphify_tool, 'ensure', return_value={'freshness': 'fresh'}) as graph:
            index_context.ensure(self.root)
            self.assertEqual((code.call_count, graph.call_count), (1, 1))

    def test_invalid_policy_blocks(self):
        for mode, providers in [('source', ['codegraph']), ('required', []),
                                ('required', ['other']), ('auto', []),
                                ('required', ['codegraph', 'codegraph'])]:
            self.policy(mode, providers)
            with self.assertRaises(HarnessError):
                index_context.ensure(self.root)

    def test_required_missing_blocks(self):
        self.policy('required', ['codegraph'])
        with patch.object(index_context.codegraph_tool, 'ensure', side_effect=HarnessError('missing')):
            with self.assertRaises(HarnessError):
                index_context.ensure(self.root)

    def test_real_adoption_and_application_lifecycle_without_graph_tools(self):
        from harnesslib.adopt import adopt
        from harnesslib.core import Harness
        from test_onboarding import OnboardingTests, KIT
        project = self.root / 'consumer'
        adopt(KIT, project, False)
        import subprocess, sys, json
        run = subprocess.run([sys.executable, '-B', str(project / 'harness'), 'indexes', 'ensure'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['mode'], 'source')
        fixture = OnboardingTests()
        fixture.root = project
        fixture.h = Harness(project)
        fixture.prepare()
        fixture.approve()
        with patch.object(index_context.codegraph_tool, 'ensure', side_effect=AssertionError('unexpected graph')), \
             patch.object(index_context.graphify_tool, 'ensure', side_effect=AssertionError('unexpected graph')):
            result = fixture.h.transition('CALC-001', 'IN_PROGRESS', 'fixture approval')
            self.assertEqual(result['navigation_context']['mode'], 'source')
            fixture.h.transition('CALC-001', 'IMPLEMENTED', 'fixture implementation')
            self.assertEqual(fixture.h.verify('CALC-001')['result'], 'PASS')
        from harnesslib import workflow
        feature, task = fixture.h.task('CALC-001')
        material = workflow.material(fixture.h, feature, task)
        atomic(project / '.harness/navigation.json',
               {'schema_version': 1, 'mode': 'required', 'providers': ['codegraph']})
        self.assertNotEqual(material, workflow.material(fixture.h, feature, task))
        with self.assertRaises(HarnessError):
            fixture.h.transition('CALC-001', 'VERIFIED', 'changed policy')

    def test_existing_adoption_never_adds_source_policy(self):
        from harnesslib.adopt import adopt
        from test_onboarding import KIT
        adopt(KIT, self.root, False)
        (self.root / '.harness/navigation.json').unlink()
        adopt(KIT, self.root, False)
        self.assertFalse((self.root / '.harness/navigation.json').exists())
        self.assertEqual(index_context.policy(self.root)['providers'], ['codegraph', 'graphify'])

    def test_measure_source_lifecycle_without_graph_setup(self):
        import json, time
        from harnesslib.adopt import adopt
        from harnesslib.core import Harness
        from test_onboarding import OnboardingTests, KIT
        samples=[]
        with patch.object(index_context.codegraph_tool,'ensure',side_effect=AssertionError('unexpected indexer')) as code, \
             patch.object(index_context.graphify_tool,'ensure',side_effect=AssertionError('unexpected indexer')) as graph:
            for sample in range(3):
                project=self.root/str(sample);started=time.perf_counter();adopt(KIT,project,False)
                adoption=time.perf_counter()-started
                fixture=OnboardingTests();fixture.root=project;fixture.h=Harness(project)
                fixture.prepare();fixture.approve()
                checks=[];original=fixture.h.run_check
                def measured(*args,**kwargs):
                    started=time.perf_counter();result=original(*args,**kwargs)
                    checks.append(time.perf_counter()-started);return result
                started=time.perf_counter()
                with patch.object(fixture.h,'run_check',side_effect=measured):
                    fixture.h.transition('CALC-001','IN_PROGRESS','fixture approval')
                    fixture.h.transition('CALC-001','IMPLEMENTED','fixture implementation')
                    self.assertEqual(fixture.h.verify('CALC-001')['result'],'PASS')
                samples.append({'adoption_seconds':adoption,'lifecycle_excluding_checks_seconds':time.perf_counter()-started-sum(checks)})
        self.assertEqual((code.call_count,graph.call_count),(0,0))
        print('SOURCE_MEASUREMENT '+json.dumps({'samples':samples,'indexer_calls':0,'extra_graph_commands':0},sort_keys=True))

    def test_tool_bootstrap_directory_is_not_a_legacy_engine(self):
        from harnesslib.adopt import adopt
        from test_onboarding import KIT
        (self.root/'.harness/tools/openspec').mkdir(parents=True)
        adopt(KIT,self.root,False)
        self.assertEqual(index_context.policy(self.root)['mode'],'source')
