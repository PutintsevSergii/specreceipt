"""Repository test selection. No production harness imports or optional dependencies."""
import argparse
import ast
import fnmatch
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name('test_scopes.json')
PYTHON_RUNNER = '''import json, sys, unittest
loader = unittest.TestLoader()
suite = loader.loadTestsFromNames(sys.argv[1:])
if loader.errors or not suite.countTestCases():
    print('Selection must load at least one test without loader errors.', file=sys.stderr)
    for error in loader.errors: print(error, file=sys.stderr)
    raise SystemExit(2)
result = unittest.TextTestRunner(verbosity=2).run(suite)
executed = result.testsRun - len(result.skipped)
print(json.dumps({'discovered': result.testsRun, 'skipped': len(result.skipped), 'executed': executed}), flush=True)
raise SystemExit(0 if result.wasSuccessful() and executed else 1)
'''


class SelectionError(ValueError):
    pass


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode:
        raise SelectionError('Git failed: ' + result.stderr.decode('utf-8', 'replace').strip())
    return result.stdout


def changed_paths(root, base=None):
    """Include both rename endpoints and all dirty/untracked paths, without quoting loss."""
    top = Path(os.fsdecode(git(root, 'rev-parse', '--show-toplevel')).strip()).resolve()
    if top != Path(root).resolve():
        raise SelectionError('Selection requires the Git repository root, not a nested kit')
    paths = set()
    comparisons = [('--cached',), ()]
    if base:
        if base.startswith('-'):
            raise SelectionError('Base must be a revision, not an option')
        commit = git(root, 'rev-parse', '--verify', base + '^{commit}').decode().strip()
        merge = git(root, 'merge-base', commit, 'HEAD').decode().strip()
        comparisons.append((merge, 'HEAD'))
    for comparison in comparisons:
        raw = git(root, 'diff', '--name-only', '-z', '--no-renames', *comparison, '--')
        paths.update(os.fsdecode(item) for item in raw.split(b'\0') if item)
    raw = git(root, 'ls-files', '--others', '--exclude-standard', '-z')
    paths.update(os.fsdecode(item) for item in raw.split(b'\0') if item)
    return sorted(paths)


def load_manifest(root=ROOT, path=MANIFEST):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        if set(value) != {'version', 'python_modules', 'node_files', 'smoke', 'rules', 'prose'} or value['version'] != 1:
            raise SelectionError('Unsupported manifest structure')
        for field in ('python_modules', 'node_files', 'smoke', 'prose'):
            items = value[field]
            if not isinstance(items, list) or not items or any(not isinstance(x, str) or not x for x in items) or len(items) != len(set(items)):
                raise SelectionError('Invalid manifest list: ' + field)
        actual = {p.stem for p in (root/'tests').glob('test_*.py')}
        if actual != set(value['python_modules']):
            raise SelectionError('Python test inventory changed; update manifest: ' + repr(sorted(actual ^ set(value['python_modules']))))
        actual_node = {p.relative_to(root).as_posix() for p in (root/'tests-node').glob('*.test.mjs')}
        # Adopted Python kits deliberately do not ship Node tests.
        if actual_node and actual_node != set(value['node_files']):
            raise SelectionError('Node test inventory changed; update manifest')
        if not isinstance(value['rules'], list) or not value['rules']:
            raise SelectionError('Missing impact rules')
        for rule in value['rules']:
            if set(rule) != {'paths', 'checks', 'reason'} or not isinstance(rule['reason'], str) or not rule['reason'].strip():
                raise SelectionError('Invalid impact rule')
            if not isinstance(rule['paths'], list) or not rule['paths'] or any(not isinstance(p, str) or not p for p in rule['paths']):
                raise SelectionError('Invalid rule paths')
            if not isinstance(rule['checks'], list) or not rule['checks']:
                raise SelectionError('Empty rule checks')
            for check in rule['checks']:
                validate_check(check, value)
        for check in value['smoke']:
            validate_check(check, value)
        return value
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise SelectionError('Invalid test manifest: ' + str(exc)) from exc


def validate_check(check, config):
    if not isinstance(check, str):
        raise SelectionError('Check must be a string')
    if check in {'full', 'typecheck', 'package', 'upgrade', 'wizard', 'validate'}:
        return
    if check.startswith('py:') and re.fullmatch(r'test_[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*', check[3:]) and check[3:].split('.')[0] in config['python_modules']:
        return
    if check.startswith('node:') and check[5:] in config['node_files']:
        return
    raise SelectionError('Unknown check: ' + check)


def test_imports(root, modules):
    """Only test-to-test imports: explicit manifest edges cover dynamic product calls."""
    result = {}
    for name in modules:
        try:
            tree = ast.parse((root/'tests'/(name+'.py')).read_text(encoding='utf-8'))
        except (OSError, SyntaxError) as exc:
            raise SelectionError('Cannot inspect test imports: ' + name) from exc
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split('.')[0])
        result[name] = imports & set(modules)
    return result


def select(root, config, profile, paths=(), manual=()):
    reasons = {}
    def add(check, reason):
        reasons.setdefault(check, []).append(reason)
    if manual:
        for check in manual:
            validate_check(check, config)
            add(check, 'Explicit manual selection; not automatic impact coverage')
        label = 'MANUAL'
    elif profile == 'full':
        add('full', 'Explicit complete regression profile')
        label = 'FULL'
    elif profile == 'smoke':
        for check in config['smoke']:
            add(check, 'Explicit short contract profile; not complete acceptance')
        label = 'SCOPED'
    else:
        label = 'SCOPED'
        for path in paths:
            matched = False
            if path.startswith('tests/') and Path(path).stem in config['python_modules'] and path == 'tests/'+Path(path).name:
                add('py:'+Path(path).stem, 'Changed test module: '+path)
                matched = True
            for rule in config['rules']:
                if any(fnmatch.fnmatchcase(path, pattern) for pattern in rule['paths']):
                    matched = True
                    for check in rule['checks']:
                        add(check, path+': '+rule['reason'])
            if not matched and not any(fnmatch.fnmatchcase(path, pattern) for pattern in config['prose']):
                add('full', 'Unmapped path; conservative fallback: '+path)
        if not paths:
            label = 'EMPTY_DIFF'
        elif not reasons:
            label = 'PROSE_ONLY'
    full = 'full' in reasons
    if full:
        # Keep the cause even when expanding the complete set.
        why = '; '.join(reasons.pop('full'))
        expanded = [*('py:'+m for m in config['python_modules']), *('node:'+p for p in config['node_files']), 'typecheck', 'package', 'wizard', 'validate']
        reasons = {check: [why] for check in dict.fromkeys([*reasons, *expanded])}
    elif not manual and profile == 'changed':
        imports = test_imports(root, config['python_modules'])
        changed = True
        while changed:
            changed = False
            selected = {c[3:].split('.')[0] for c in reasons if c.startswith('py:')}
            for module, dependencies in imports.items():
                if dependencies & selected and 'py:'+module not in reasons:
                    add('py:'+module, 'Imports shared test fixture(s): '+', '.join(sorted(dependencies & selected)))
                    changed = True
    return {'profile': profile, 'coverage': label, 'full': full, 'changed_paths': list(paths), 'checks': reasons}


def commands(root, config, selection, language='all'):
    checks = selection['checks']
    planned = []
    python = [c[3:] for c in checks if c.startswith('py:')]
    if language != 'node':
        if python:
            planned.append({'id': 'python', 'argv': [sys.executable, '-B', '-X', 'utf8', str(root/'harness'), 'self-test'] if selection['full'] else [sys.executable, '-B', '-X', 'utf8', '-c', PYTHON_RUNNER, *sorted(python)]})
        if 'validate' in checks:
            planned.append({'id': 'validate', 'argv': [sys.executable, '-B', '-X', 'utf8', str(root/'harness'), 'validate']})
    if language != 'python':
        node = [c[5:] for c in checks if c.startswith('node:')]
        # Keep the existing Windows compatibility set; POSIX-only fixtures stay on POSIX.
        if os.name == 'nt':
            node = [p for p in node if p in {'tests-node/windows.test.mjs', 'tests-node/engine-upgrade.test.mjs', 'tests-node/copilot.test.mjs'}]
        node_checks = bool(node or set(checks) & {'typecheck', 'package', 'upgrade', 'wizard'})
        if node_checks:
            # Direct Node entry points avoid npm .cmd shell interpolation on Windows.
            planned.extend([{'id':'version-sync', 'argv':['node', 'scripts/release.mjs', 'sync']},
                            {'id':'typecheck', 'argv':['node', 'node_modules/typescript/bin/tsc', '--noEmit']},
                            {'id':'build-types', 'argv':['node', 'node_modules/typescript/bin/tsc']},
                            {'id':'build-assets', 'argv':['node', 'scripts/build-assets.mjs']}])
        if node:
            planned.append({'id':'node', 'argv':['node', '--test', *sorted(node)]})
        for check, script in [('package','scripts/test-package.mjs'), ('upgrade','scripts/test-upgrade.mjs')]:
            if check in checks:
                planned.append({'id':check, 'argv':['node', script]})
        if 'wizard' in checks and os.name != 'nt':
            planned.append({'id':'wizard', 'argv':[sys.executable, '-B', 'scripts/test-wizard.py']})
    return planned


def validate_python_names(root, selection):
    """Validate explicit class/method selectors without importing tests or running setup."""
    for check in selection['checks']:
        if not check.startswith('py:') or '.' not in check[3:]:
            continue
        module, *parts = check[3:].split('.')
        tree = ast.parse((root/'tests'/(module+'.py')).read_text(encoding='utf-8'))
        nodes = tree.body
        for part in parts:
            node = next((n for n in nodes if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == part), None)
            if node is None:
                raise SelectionError('Mapped test no longer exists: '+check)
            nodes = node.body


def execute(root, plan, run=subprocess.run):
    """No shell; prerequisites are checked by actual commands, never silently skipped."""
    started = time.monotonic()
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([str(root), str(root/'tests'), env.get('PYTHONPATH', '')])
    env['HARNESS_PYTHON'] = sys.executable
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    results = []
    for command in plan:
        argv = command['argv']
        if command['id'] == 'upgrade' and not all(env.get(k) for k in ('HARNESS_LEGACY_PACKAGE', 'HARNESS_UPGRADE_PACKAGE')):
            raise SelectionError('Upgrade check requires reviewed HARNESS_LEGACY_PACKAGE and HARNESS_UPGRADE_PACKAGE archives; it was not run')
        if argv[0] == 'node' and not shutil.which('node'):
            raise SelectionError('Node required by selected checks; install/choose the existing supported runtime explicitly')
        print('RUN '+command['id']+': '+json.dumps(argv), flush=True)
        before = time.monotonic()
        result = run(argv, cwd=root, env=env, check=False)
        results.append({'check':command['id'], 'exit_code':result.returncode, 'seconds':round(time.monotonic()-before, 3)})
        if result.returncode:
            return {'result':'FAIL', 'results':results, 'seconds':round(time.monotonic()-started, 3)}, result.returncode if result.returncode > 0 else 1
    return {'result':'PASS' if plan else 'NO_RUNTIME_TESTS', 'results':results, 'seconds':round(time.monotonic()-started, 3)}, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, choices=['smoke','changed','full'])
    parser.add_argument('--base', help='Compare HEAD with merge-base(REF, HEAD), plus local changes')
    parser.add_argument('--language', choices=['all','python','node'], default='all')
    parser.add_argument('--suite', action='append', default=[], help='Explicit py:MODULE[.CLASS.METHOD] or node:FILE; manual coverage')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--output', type=Path, help='Write JSON plan (useful for CI planning)')
    parser.add_argument('--plan-file', type=Path, help='Reuse CI changed paths; commands are always recomputed locally')
    args = parser.parse_args(argv)
    try:
        config = load_manifest()
        if args.plan_file:
            if args.base or args.suite:
                raise SelectionError('CI plan cannot be combined with a base or manual suites')
            saved = json.loads(args.plan_file.read_text(encoding='utf-8'))
            if not isinstance(saved, dict) or saved.get('profile') != args.profile:
                raise SelectionError('CI plan profile does not match')
            paths = saved.get('changed_paths')
            if not isinstance(paths, list) or any(not isinstance(p, str) or not p or p.startswith(('/', '-')) or '..' in Path(p).parts for p in paths):
                raise SelectionError('Invalid CI changed paths')
        else:
            paths = changed_paths(ROOT, args.base) if args.profile == 'changed' and not args.suite else []
        selection = select(ROOT, config, args.profile, paths, args.suite)
        validate_python_names(ROOT, selection)
        selection['commands'] = commands(ROOT, config, selection, args.language)
        selection['language'] = args.language
        selection['not_applicable'] = []
        if os.name == 'nt' and args.language != 'python':
            selection['not_applicable'] = [c for c in selection['checks'] if (c.startswith('node:') and c[5:] not in {'tests-node/windows.test.mjs', 'tests-node/engine-upgrade.test.mjs', 'tests-node/copilot.test.mjs'}) or c == 'wizard']
        selection['limitations'] = ['Conservative maintained impact map, not complete dynamic coverage.', 'Scoped PASS is not final acceptance. Read runner summaries for skips and actual test counts.', 'Windows Node and wizard selection preserves the existing platform applicability.']
        output = json.dumps(selection, ensure_ascii=True, indent=2)
        if args.output:
            args.output.write_text(output+'\n', encoding='utf-8')
        print(output, flush=True)
        if args.dry_run:
            return 0
        result, code = execute(ROOT, selection['commands'])
        result.update(coverage=selection['coverage'], language=args.language)
        print(json.dumps(result, indent=2), flush=True)
        return code
    except (SelectionError, OSError, json.JSONDecodeError) as exc:
        print('TEST_SELECTION_ERROR: '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
