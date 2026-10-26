"""Exact, approved recognition of outside changes; never a write permission."""
import hashlib
from .storage import HarnessError, digest, read, safe_path, uid, now
from . import verification


def baseline(task):
    execution = task.get('execution')
    if not execution:
        raise HarnessError('Missing original task baseline')
    return {**execution['baseline'], **execution.get('policy_baseline', {})}


def protected(h, task):
    paths = {'.harness/checks.json', '.harness/environment.json', '.harness/onboarding.json',
             '.harness/workflow-policy.json', '.harness/graph-config.json', '.harness/runner.json',
             'docs/TECH_SPEC.md', 'docs/ARCHITECTURE.md', 'docs/DECISION_QUEUE.md'}
    for item in h.check_closure(task):
        feature, _ = h.task(item['id'])
        paths.update(f"specs/{feature['feature_id']}/{name}" for name in ('spec.md','plan.md','tasks.json'))
        if feature.get('spec_source'):
            from . import openspec_tool
            paths.update(openspec_tool.feature_source(h.root, feature))
        paths.update(a['reference'] for a in item['approvals'].values())
    return paths


def owned(task, path):
    return any(path == s or (s.endswith('/') and path.startswith(s)) for s in task['scope'])


def entry(h, before, after, path):
    verification.validate_scope(h.root, [path])
    if path.endswith('/') or '\\' in path:
        raise HarnessError('Recognition requires exact file paths')
    file = safe_path(h.root, path)
    if file.exists() and not file.is_file():
        raise HarnessError('Recognition requires regular files')
    return {'path':path, 'change':'CREATED' if path not in before else 'DELETED' if path not in after else 'MODIFIED',
            'before':before.get(path), 'after':after.get(path),
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest() if path in after else None,
            'executable':bool(file.stat().st_mode & 0o111) if path in after else None}


def chain(h, task):
    previous = None
    last = None
    for reference in task.get('execution', {}).get('recognitions', []):
        record = read(safe_path(h.root, reference['reference']))
        if digest(record) != reference['hash']:
            raise HarnessError('Recognition record changed')
        manifest = record['manifest']
        h.schema('reconciliation', manifest)
        if (manifest['previous'] != previous or manifest['task_id'] != task['id'] or
                manifest['baseline'] != digest(task['execution']['baseline'])):
            raise HarnessError('Recognition chain or original baseline changed')
        if digest(safe_path(h.root, record['approval']).read_text()) != record['approval_hash']:
            raise HarnessError('Recognition approval reference changed')
        previous = reference['hash']
        last = manifest
    return previous, last


def propose(h, task):
    before, after = baseline(task), h.fingerprints()
    previous, _ = chain(h, task)
    paths = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p) and not owned(task,p))
    if set(paths) & protected(h,task):
        raise HarnessError('Task policy inputs require approved replan, not recognition')
    return {'schema_version':1, 'task_id':task['id'], 'baseline':digest(task['execution']['baseline']),
            'definition':h.definition(task), 'previous':previous,
            'entries':[entry(h,before,after,p) for p in paths]}


def classify(h, task, allow_stale_definition=False):
    before, after = baseline(task), h.fingerprints()
    _, manifest = chain(h, task)
    recognized = set()
    if manifest:
        if manifest['definition'] != h.definition(task) and not allow_stale_definition:
            raise HarnessError('Recognition approval is stale for task definition; obtain a new manifest approval')
        if len({e['path'] for e in manifest['entries']}) != len(manifest['entries']):
            raise HarnessError('Duplicate recognition paths')
        for item in manifest['entries']:
            path = item['path']
            if owned(task,path) or path in protected(h,task):
                raise HarnessError('Recognition cannot grant task or policy write permissions')
            current = entry(h,before,after,path)
            # tasks.json lifecycle fields are deliberately outside the semantic inventory.
            if path.startswith('specs/') and path.endswith('/tasks.json'):
                current['sha256'] = item['sha256']
            if current != item:
                raise HarnessError('Recognized content changed: '+path)
            recognized.add(path)
    changes = sorted(p for p in set(before)|set(after) if before.get(p) != after.get(p))
    return {'owned':[p for p in changes if owned(task,p)],
            'recognized':sorted(recognized),
            'unrecognized':[p for p in changes if not owned(task,p) and p not in recognized]}


def accept(h, task_id, manifest_path, approval, by):
    feature, task = h.task(task_id)
    if task['status'] not in {'BLOCKED','REWORK','IN_PROGRESS','IMPLEMENTED'}:
        raise HarnessError('Recognition requires an unfinished task before verification')
    content = safe_path(h.root,approval).read_text()
    from .readiness import substantive
    if not substantive(content) or not by.strip():
        raise HarnessError('Explicit substantive developer approval reference required')
    manifest = read(safe_path(h.root,manifest_path)); h.schema('reconciliation',manifest)
    if manifest != propose(h,task) or not manifest['entries']:
        raise HarnessError('Stale or incomplete recognition manifest')
    # Bind the approval to the exact manifest, not just an arbitrary consent document.
    if digest(manifest) not in content:
        raise HarnessError('Approval reference must name the exact manifest digest')
    ref = f'.harness/evidence/reconciliation/recognition-{uid()}.json'
    record = {'manifest':manifest,'approval':approval,'approval_hash':digest(content),'by':by,'at':now()}
    # Recheck immediately before the existing locked transaction commits.
    if manifest != propose(h,task) or digest(safe_path(h.root,approval).read_text()) != record['approval_hash']:
        raise HarnessError('Recognition inputs changed before recording')
    task['execution'].setdefault('recognitions',[]).append({'reference':ref,'hash':digest(record)})
    h.save(h.state(), h.event('baseline-recognized','Recognized exact pre-existing changes; no write scope granted.',task_id,feature['feature_id'],evidence=[ref]), feature, {ref:record})
    return {'result':'PASS','reference':ref,'manifest_hash':digest(manifest),'recognized':len(manifest['entries'])}
