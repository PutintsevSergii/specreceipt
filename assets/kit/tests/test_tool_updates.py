import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from harnesslib import tool_updates as u
from harnesslib.tool_paths import binary
from harnesslib.storage import HarnessError


class ToolUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_plan_missing_optional_and_no_writes(self):
        with patch.object(u, 'probe', return_value=None):
            result = u.update(self.root)
        self.assertEqual([x['action'] for x in result['tools']], ['install','install','skip_optional'])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_newer_version_blocks_downgrade(self):
        with patch.object(u, 'probe', return_value='999.0.0'):
            result = u.plan(self.root, ['codegraph'])
        self.assertEqual(result['result'], 'BLOCKED')
        self.assertEqual(result['tools'][0]['action'], 'blocked_newer_version')

    def test_latest_does_not_replace_supported_target(self):
        with patch.object(u, 'probe', return_value=None), patch.object(u, 'latest', return_value='999.0.0'):
            entry = u.plan(self.root, ['openspec'], True, True)['tools'][0]
        self.assertTrue(entry['compatibility_review_required'])
        self.assertEqual(entry['target_version'], u.openspec_tool.VERSION)

    def test_local_executable_and_escape_rejected(self):
        path = self.root/'.harness/tools/codegraph/node_modules/.bin/codegraph'
        path.parent.mkdir(parents=True)
        path.write_text('fixture')
        self.assertEqual(binary(self.root,'codegraph'), str(path))
        path.unlink(); path.symlink_to('/bin/sh')
        with self.assertRaises(HarnessError): binary(self.root,'codegraph')

    def test_partial_failure_keeps_other_updates_and_checks(self):
        with patch.object(u,'probe',return_value=None), \
             patch.object(u,'install',side_effect=[HarnessError('fixture failure'),'1.14.3']) as install, \
             patch.object(u,'execute',return_value='PASS'):
            result = u.update(self.root,['codegraph','openspec'],apply=True,include_optional=True)
        self.assertEqual(install.call_count,2)
        self.assertEqual(result['result'],'FAIL')
        self.assertEqual([x['result'] for x in result['tools']],['FAIL','PASS'])
        self.assertEqual(len(result['checks']),2)
        self.assertIsNone(json.loads((self.root/u.REPORT).read_text())['active_tool'])

    def test_interrupted_update_cannot_replay(self):
        path=self.root/u.REPORT; path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'active_tool':'codegraph'}))
        with patch.object(u,'probe',return_value=None), patch.object(u,'install') as install:
            with self.assertRaises(HarnessError): u.update(self.root,apply=True)
        install.assert_not_called()

    def test_install_local_pinned_and_version_verified(self):
        with patch.object(u.shutil,'which',side_effect=lambda name:'/bin/'+name), \
             patch.object(u,'execute',side_effect=['v22.0.0','installed']) as execute, \
             patch.object(u,'probe',return_value=u.openspec_tool.VERSION):
            u.install(self.root,'openspec',u.registry()['openspec'])
        argv=execute.call_args.args[1]
        self.assertIn(str(self.root/'.harness/tools/openspec'),argv)
        self.assertIn('--ignore-scripts',argv)
        self.assertEqual(argv[-1],u.openspec_tool.PACKAGE)

    def test_changed_index_is_refreshed(self):
        with patch.object(u,'probe',return_value=None), patch.object(u,'install',return_value='0.9.27'), \
             patch.object(u.graphify_tool,'ensure',return_value={'freshness':'fresh'}) as ensure, \
             patch.object(u,'execute',return_value='PASS'):
            result=u.update(self.root,['graphify'],apply=True)
        ensure.assert_called_once_with(self.root)
        self.assertEqual(result['result'],'PASS')

    def test_post_install_mismatch_fails(self):
        with patch.object(u.shutil,'which',return_value='/bin/uv'), \
             patch.object(u,'execute',return_value='installed'), \
             patch.object(u,'probe',return_value='0.0.1'):
            with self.assertRaisesRegex(HarnessError,'version mismatch'):
                u.install(self.root,'graphify',u.registry()['graphify'])

    def test_failed_post_check_is_not_success(self):
        with patch.object(u,'probe',return_value=u.openspec_tool.VERSION), \
             patch.object(u,'execute',side_effect=HarnessError('verification failed')):
            report=u.update(self.root,['openspec'],apply=True)
        self.assertEqual(report['result'],'FAIL')
        self.assertTrue(all(c['result']=='FAIL' for c in report['checks']))


class MissingNavigationDependencyTests(unittest.TestCase):
    def test_missing_index_tools_never_install_globally(self):
        for module in (u.codegraph_tool, u.graphify_tool):
            with self.subTest(module=module.__name__), \
                 patch.object(module, 'tool_binary', return_value=None), \
                 patch.object(module.subprocess, 'run') as run:
                with self.assertRaisesRegex(HarnessError, 'Explicitly install'):
                    module.install_binary(Path('/unused-project'))
                run.assert_not_called()
