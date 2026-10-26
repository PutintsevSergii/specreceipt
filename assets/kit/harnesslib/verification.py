"""Verification inputs, scope and structured acceptance; independent of navigation."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from .storage import HarnessError, digest, safe_path

# Build outputs and installed packages are not source inputs. Versions belong in
# environment.json. Configuration, dotfiles and binary assets ARE inputs.
EXCLUDED = {'.git', '.harness', 'graphify-out', '.codegraph', '.codegraph-wsl', '__pycache__', 'node_modules', '.venv', 'venv',
            'dist', 'build', '.next', '.pytest_cache'}

def inventory(root):
    root = Path(root).resolve()
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in list(dirs):
            p = base/name
            if p.is_symlink():
                raise HarnessError('Verification cannot attest symlink directory: '+p.relative_to(root).as_posix())
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in sorted(files):
            if name == '.DS_Store' or name.endswith('.pyc'): continue
            path = base/name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise HarnessError('Verification cannot attest symlink input: '+rel)
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode): raise HarnessError('Unsupported verification input: '+rel)
            hasher = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''): hasher.update(block)
            result[rel] = digest({'content':hasher.hexdigest(), 'executable':bool(mode & 0o111)})
    return result

def validate_scope(root, scope):
    for value in scope:
        if not value or value in {'.','./','/'} or any(c in value for c in '*?['):
            raise HarnessError('Scope needs explicit file paths or directory/ prefixes')
        if any(part in EXCLUDED for part in Path(value).parts):
            raise HarnessError('Scope cannot target excluded verification directories: '+value)
        safe_path(root, value)
        if Path(value).as_posix() != value.rstrip('/'):
            raise HarnessError('Scope path must be normalized: '+value)

def scope_changes(h, task, allow_stale_recognition=False):
    execution = task.get('execution')
    if not execution: raise HarnessError('Missing scope baseline; restart the task before implementation')
    if execution['definition'] != h.definition(task):
        raise HarnessError('Task inputs changed since start; review and restart the task')
    from . import reconciliation
    changes = reconciliation.classify(h, task, allow_stale_recognition)
    if changes['unrecognized']:
        raise HarnessError('Changes outside approved scope: '+', '.join(changes['unrecognized'])+'; propose an exact baseline recognition manifest for developer review')
    return changes['owned']


def acceptance(task):
    criteria = task['acceptance_criteria']
    if len(criteria) != len(set(criteria)): raise HarnessError('Duplicate acceptance criteria')
    mapping = task.get('acceptance_checks', [])
    if len(mapping) != len(criteria) or {m['criterion'] for m in mapping} != set(criteria):
        raise HarnessError('Map every acceptance criterion exactly once in acceptance_checks')
    for row in mapping:
        if not row['checks'] or len(row['checks']) != len(set(row['checks'])) or not set(row['checks']) <= set(task['required_checks']):
            raise HarnessError('Acceptance checks must name distinct required task checks')
    return mapping

def review(h, task, content, require_pass=True):
    blocks = re.findall(r'^```harness-review\s*\n(.*?)^```\s*$', content, re.M|re.S)
    if len(blocks) != 1: raise HarnessError('Review needs exactly one harness-review JSON block')
    try: record = json.loads(blocks[0])
    except ValueError as exc: raise HarnessError('Invalid review JSON') from exc
    h.schema('review', record)
    if record['task_id'] != task['id'] or not task['evidence'] or record['evidence'] != task['evidence'][-1]:
        raise HarnessError('Review must reference this task and its latest execution evidence')
    if require_pass and (record['verdict'] != 'PASS' or any(f['status'] != 'RESOLVED' for f in record['findings'])):
        raise HarnessError('Review has unresolved findings or requests changes')
    if len({f['id'] for f in record['findings']}) != len(record['findings']):
        raise HarnessError('Duplicate review finding IDs')
    from .readiness import substantive
    if not all(substantive(record[k]) for k in ['reviewer','summary']):
        raise HarnessError('Review needs substantive reviewer and summary')
    for finding in record['findings']:
        fields = ['location','behavior','requirement','reproduction'] + (['resolution'] if finding['status'] == 'RESOLVED' else [])
        if not all(substantive(finding[k]) for k in fields):
            raise HarnessError('Resolved findings require location, reproduction and resolution evidence')
    return record
