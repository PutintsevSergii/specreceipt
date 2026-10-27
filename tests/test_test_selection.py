"""Small selector contracts: no adopted kit, models, installed tools or shared mutable fixture."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_scoped as scoped


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'tests').mkdir()
        (self.root/'tests-node').mkdir()
        self.write('tests/test_leaf.py', 'VALUE = 1\n')
        self.write('tests/test_consumer.py', 'import test_leaf\n')
        self.write('tests/test_transitive.py', 'from test_consumer import VALUE\n')
        self.write('tests/test_other.py', 'VALUE = 2\n')
        self.write('tests-node/sample.test.mjs', '// fixture\n')
        self.config = {
            'version':1,
            'python_modules':['test_leaf','test_consumer','test_transitive','test_other'],
            'node_files':['tests-node/sample.test.mjs'],
            'smoke':['py:test_other'],
            'rules':[
                {'paths':['src/leaf.py'], 'checks':['py:test_leaf'], 'reason':'Leaf consumers'},
                {'paths':['src/other.py'], 'checks':['py:test_other'], 'reason':'Independent boundary'},
                {'paths':['core.py'], 'checks':['full'], 'reason':'Foundation'},
                {'paths':['upgrade.py'], 'checks':['full','upgrade'], 'reason':'Archived upgrades'}],
            'prose':['README.md']}
        self.manifest = self.root/'tests/test_scopes.json'
        self.save()

    def write(self, path, text):
        p = self.root/path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def save(self):
        self.manifest.write_text(json.dumps(self.config), encoding='utf-8')

    def select(self, *paths, profile='changed', manual=()):
        return scoped.select(self.root, self.config, profile, paths, manual)

    def git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8','replace'))
        return result.stdout.decode('utf-8').strip()

    def repository(self):
        self.git('init', '--initial-branch=main')
        self.git('add', '.')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')

    def test_narrow_selection_and_transitive_fixture_consumers(self):
        result = self.select('src/leaf.py')
        self.assertEqual(set(result['checks']), {'py:test_leaf','py:test_consumer','py:test_transitive'})
        self.assertIn('fixture', result['checks']['py:test_consumer'][0])
        self.assertFalse(result['full'])

    def test_changed_test_also_selects_consumers(self):
        result = self.select('tests/test_leaf.py')
        self.assertIn('py:test_transitive', result['checks'])
        self.assertNotIn('py:test_other', result['checks'])

    def test_two_boundaries_take_union(self):
        self.assertEqual(len(self.select('src/leaf.py','src/other.py')['checks']), 4)

    def test_unknown_path_expands_and_preserves_reason(self):
        result = self.select('new/code.py')
        self.assertTrue(result['full'])
        self.assertIn('new/code.py', result['checks']['py:test_other'][0])

    def test_foundation_expands_to_package_and_all_modules(self):
        result = self.select('core.py')
        self.assertTrue(result['full'])
        self.assertIn('package', result['checks'])
        self.assertIn('node:tests-node/sample.test.mjs', result['checks'])

    def test_full_does_not_silently_drop_explicit_archive_check(self):
        self.assertIn('upgrade', self.select('upgrade.py')['checks'])

    def test_prose_and_empty_diff_have_distinct_non_pass_labels(self):
        self.assertEqual(self.select()['coverage'], 'EMPTY_DIFF')
        self.assertEqual(self.select('README.md')['coverage'], 'PROSE_ONLY')
        self.assertFalse(self.select('README.md')['checks'])

    def test_smoke_does_not_expand_to_unrelated_integration(self):
        result = self.select(profile='smoke')
        self.assertEqual(set(result['checks']), {'py:test_other'})
        self.assertEqual(result['coverage'], 'SCOPED')

    def test_manual_is_labelled_and_invalid_suite_rejected(self):
        self.assertEqual(self.select(manual=['py:test_other'])['coverage'], 'MANUAL')
        for value in ['py:test_missing', 'node:../../escape', 'py:test_other;bad']:
            with self.assertRaises(scoped.SelectionError): self.select(manual=[value])

    def test_manual_exact_selection_does_not_expand_fixture_consumers(self):
        result = self.select(manual=['py:test_leaf'])
        self.assertEqual(set(result['checks']), {'py:test_leaf'})
        self.config['smoke'] = ['py:test_leaf']
        self.assertEqual(set(self.select(profile='smoke')['checks']), {'py:test_leaf'})

    def test_valid_manifest_and_missing_test_fail_closed(self):
        scoped.load_manifest(self.root, self.manifest)
        (self.root/'tests/test_other.py').unlink()
        with self.assertRaises(scoped.SelectionError): scoped.load_manifest(self.root, self.manifest)

    def test_new_unmapped_test_is_not_silently_ignored(self):
        self.write('tests/test_new.py', 'VALUE=3\n')
        with self.assertRaises(scoped.SelectionError): scoped.load_manifest(self.root, self.manifest)

    def test_malformed_manifest_and_unknown_rule_check_fail(self):
        for value in [{}, {'version':99}, dict(self.config, rules=[{'paths':['x'],'checks':['py:test_absent'],'reason':'bad'}])]:
            self.manifest.write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaises(scoped.SelectionError): scoped.load_manifest(self.root, self.manifest)

    def test_bad_test_syntax_blocks_selection(self):
        self.write('tests/test_leaf.py','def invalid(\n')
        with self.assertRaises(scoped.SelectionError): self.select('src/leaf.py')

    def test_language_filter_keeps_python_checks_out_of_node_job(self):
        plan = scoped.commands(self.root, self.config, self.select('core.py'), 'node')
        self.assertNotIn('python', [p['id'] for p in plan])
        self.assertIn('build-assets', [p['id'] for p in plan])
        plan = scoped.commands(self.root, self.config, self.select('core.py'), 'python')
        self.assertEqual([p['id'] for p in plan], ['python','validate'])
        self.assertEqual(plan[0]['argv'][-1], 'self-test')

    def test_scoped_python_command_uses_exact_modules(self):
        plan = scoped.commands(self.root, self.config, self.select('src/other.py'), 'python')
        self.assertEqual(plan[0]['argv'][-1], 'test_other')
        self.assertNotIn('self-test', plan[0]['argv'])

    def test_no_profile_fails_without_running_tests(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            scoped.main([])
        self.assertEqual(error.exception.code, 2)

    def test_dry_run_does_not_execute_and_writes_json_plan(self):
        output = self.root/'plan.json'
        with patch.object(scoped, 'ROOT', self.root), patch.object(scoped, 'load_manifest', return_value=self.config), \
             patch.object(scoped, 'changed_paths', return_value=['src/other.py']), patch.object(scoped, 'execute') as execute, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scoped.main(['--profile','changed','--dry-run','--output',str(output)]), 0)
        execute.assert_not_called()
        self.assertEqual(json.loads(output.read_text())['coverage'], 'SCOPED')

    def test_manual_cli_does_not_require_git(self):
        with patch.object(scoped, 'ROOT', self.root), patch.object(scoped, 'load_manifest', return_value=self.config), \
             patch.object(scoped, 'changed_paths') as changed, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(scoped.main(['--profile','changed','--suite','py:test_other','--dry-run']), 0)
        changed.assert_not_called()

    def test_missing_class_or_method_fails_before_execution(self):
        selection = self.select(manual=['py:test_other.NoSuchClass.test_case'])
        with self.assertRaises(scoped.SelectionError): scoped.validate_python_names(self.root, selection)

    def test_ci_plan_recomputes_commands_instead_of_trusting_artifact(self):
        saved = self.root/'ci.json'
        saved.write_text(json.dumps({'profile':'changed','changed_paths':['src/other.py'], 'commands':[{'argv':['malicious']}]}))
        with patch.object(scoped, 'ROOT', self.root), patch.object(scoped, 'load_manifest', return_value=self.config), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(scoped.main(['--profile','changed','--plan-file',str(saved),'--dry-run']), 0)
        self.assertNotIn('malicious', output.getvalue())
        self.assertIn('test_other', output.getvalue())

    def test_ci_plan_invalid_paths_or_profile_fail_closed(self):
        saved = self.root/'ci.json'
        for value in [{'profile':'full','changed_paths':[]}, {'profile':'changed','changed_paths':['../escape']}, {'profile':'changed','changed_paths':'not-a-list'}]:
            saved.write_text(json.dumps(value))
            with patch.object(scoped, 'ROOT', self.root), patch.object(scoped, 'load_manifest', return_value=self.config), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(scoped.main(['--profile','changed','--plan-file',str(saved),'--dry-run']), 2)

    def test_command_failure_propagates_and_stops_following_commands(self):
        plan = [{'id':'fixture','argv':[sys.executable,'-c','raise SystemExit(7)']}, {'id':'never','argv':[sys.executable,'-c','raise SystemExit(0)']}]
        with contextlib.redirect_stdout(io.StringIO()): result, code = scoped.execute(self.root, plan)
        self.assertEqual(code, 7)
        self.assertEqual(result['result'], 'FAIL')
        self.assertEqual(len(result['results']), 1)

    def test_empty_execution_does_not_claim_runtime_pass(self):
        result, code = scoped.execute(self.root, [])
        self.assertEqual(code, 0)
        self.assertEqual(result['result'], 'NO_RUNTIME_TESTS')

    def test_empty_python_suite_does_not_return_pass(self):
        plan = scoped.commands(self.root, self.config, self.select('src/other.py'), 'python')
        def quiet(argv, **kwargs):
            return subprocess.run(argv, **kwargs, capture_output=True)
        with contextlib.redirect_stdout(io.StringIO()):
            result, code = scoped.execute(self.root, plan, quiet)
        self.assertNotEqual(code, 0)
        self.assertEqual(result['result'], 'FAIL')

    def test_all_skipped_python_suite_is_not_executed_coverage(self):
        self.write('tests/test_other.py', 'import unittest\n@unittest.skip("fixture")\nclass Cases(unittest.TestCase):\n def test_case(self): pass\n')
        plan = scoped.commands(self.root, self.config, self.select('src/other.py'), 'python')
        def quiet(argv, **kwargs): return subprocess.run(argv, **kwargs, capture_output=True)
        with contextlib.redirect_stdout(io.StringIO()): result, code = scoped.execute(self.root, plan, quiet)
        self.assertNotEqual(code, 0)
        self.assertEqual(result['result'], 'FAIL')

    def test_execution_passes_arrays_and_explicit_python_paths(self):
        calls = []
        def fake(argv, **kwargs):
            calls.append((argv, kwargs)); return subprocess.CompletedProcess(argv, 0)
        with contextlib.redirect_stdout(io.StringIO()):
            result, _ = scoped.execute(self.root, [{'id':'fixture','argv':[sys.executable,'space and & value']}], fake)
        self.assertEqual(result['result'], 'PASS')
        self.assertEqual(calls[0][0][-1], 'space and & value')
        self.assertNotIn('shell', calls[0][1])
        self.assertIn(str(self.root/'tests'), calls[0][1]['env']['PYTHONPATH'])

    def test_upgrade_prerequisites_are_explicit_blocker(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(scoped.SelectionError):
            scoped.execute(self.root, [{'id':'upgrade','argv':['node','script.mjs']}])

    def test_git_collects_staged_unstaged_untracked_unicode_spaces(self):
        self.repository()
        self.write('staged.txt','staged'); self.git('add','staged.txt')
        self.write('tests/test_other.py','CHANGED=1\n')
        self.write('папка с пробелами/new file.txt','untracked')
        paths = scoped.changed_paths(self.root)
        self.assertIn('staged.txt', paths)
        self.assertIn('tests/test_other.py', paths)
        self.assertIn('папка с пробелами/new file.txt', paths)

    def test_git_rename_and_deletion_include_old_paths(self):
        self.repository()
        self.git('mv','tests/test_leaf.py','tests/renamed file.py')
        (self.root/'tests/test_other.py').unlink()
        paths = scoped.changed_paths(self.root)
        self.assertTrue({'tests/test_leaf.py','tests/renamed file.py','tests/test_other.py'} <= set(paths))

    def test_git_base_includes_committed_changes(self):
        self.repository(); base = self.git('rev-parse','HEAD')
        self.write('committed.txt','new'); self.git('add','committed.txt')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','change')
        self.assertEqual(scoped.changed_paths(self.root), [])
        self.assertEqual(scoped.changed_paths(self.root, base), ['committed.txt'])

    def test_git_uses_merge_base_not_target_branch_tip(self):
        self.repository()
        self.git('checkout','-qb','feature'); self.write('feature.txt','f'); self.git('add','feature.txt')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','feature')
        self.git('checkout','main'); self.write('target.txt','t'); self.git('add','target.txt')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','target')
        self.git('checkout','feature')
        self.assertEqual(scoped.changed_paths(self.root,'main'), ['feature.txt'])

    def test_missing_base_option_injection_and_missing_repo_fail(self):
        self.repository()
        for base in ['missing-ref','--all']:
            with self.assertRaises(scoped.SelectionError): scoped.changed_paths(self.root, base)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(scoped.SelectionError):
            scoped.changed_paths(Path(directory))

    def test_real_manifest_maps_every_current_production_boundary(self):
        config = scoped.load_manifest()
        for pattern in ('harnesslib/*.py','src/*.ts'):
            for path in scoped.ROOT.glob(pattern):
                rel = path.relative_to(scoped.ROOT).as_posix()
                self.assertTrue(any(any(scoped.fnmatch.fnmatchcase(rel, p) for p in rule['paths']) for rule in config['rules']), rel)


if __name__ == '__main__':
    unittest.main()
