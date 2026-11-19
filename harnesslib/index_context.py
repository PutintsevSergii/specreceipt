"""Policy-driven navigation; graph results are leads, never acceptance proof."""
from . import codegraph_tool, graphify_tool
from .storage import HarnessError, atomic, digest, now, read, redact, safe_path

PROVIDERS = {'codegraph': codegraph_tool, 'graphify': graphify_tool}
POLICY_PATH = '.harness/navigation.json'


def policy(root):
    path = safe_path(root, POLICY_PATH)
    if not path.exists():
        return {'schema_version': 1, 'mode': 'required', 'providers': list(PROVIDERS)}
    value = read(path)
    return validate_policy(value)


def validate_policy(value):
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'mode', 'providers'}
            or type(value['schema_version']) is not int or value['schema_version'] not in (1, 2)
            or value['mode'] not in (('source', 'required') if value['schema_version'] == 1 else ('source', 'auto', 'required'))
            or not isinstance(value['providers'], list)
            or any(not isinstance(p, str) or p not in PROVIDERS for p in value['providers'])
            or len(set(value['providers'])) != len(value['providers'])
            or (value['mode'] == 'source' and value['providers'])
            or (value['mode'] in ('required', 'auto') and not value['providers'])):
        raise HarnessError('Invalid navigation policy: source has no providers; auto/required need unique codegraph/graphify providers. Auto requires schema version 2.')
    return value


def show(root):
    selected = policy(root)
    return {'result': 'PASS', 'policy': selected,
            'revision': digest({'present': safe_path(root, POLICY_PATH).exists(), 'policy': selected}),
            'notice': 'Settings apply only to this repository. Changes can invalidate task readiness/evidence. Saving does not install tools or grant approvals.'}


def configure(h, mode, providers=None, expected=None):
    h.reconcile()
    current = show(h.root)
    if expected is not None and expected != current['revision']:
        raise HarnessError('Navigation settings changed. Reload them before saving.')
    mode = 'required' if mode == 'custom' else mode
    selected = validate_policy({'schema_version': 2, 'mode': mode,
                                'providers': ([] if mode == 'source' else list(PROVIDERS)) if providers is None else providers})
    if selected != current['policy']:
        h.save(h.state(), h.event('navigation-configured', 'Repository navigation policy selected: ' + mode,
               changed_files=[POLICY_PATH]), extra={POLICY_PATH: selected})
    return show(h.root)


def decision(root, selected, task=None):
    if selected['mode'] != 'auto':
        return {'providers': selected['providers'], 'reason': 'Explicit repository policy.'}
    if not task:
        return {'providers': [], 'reason': 'Auto waits for task scope; no task-independent indexing.'}
    scope = task.get('scope', [])
    broad = len(scope) > 1 or any(any(c in item for c in '*?[') or safe_path(root, item).is_dir() for item in scope if item != '.') or '.' in scope
    if not broad:
        return {'providers': [], 'reason': 'Bounded single-file task: use targeted source navigation.'}
    available = []
    for name in selected['providers']:
        try:
            status = PROVIDERS[name].status(root)
            if status.get('installed') and status.get('coverage') != 'empty':
                available.append((status.get('freshness') != 'fresh', name))
        except (HarnessError, OSError, ValueError):
            continue
    if not available:
        return {'providers': [], 'reason': 'No enabled graph provider is available; use source navigation.'}
    # Prefer fresh indexes, then deterministic configured order. Query only one provider.
    available.sort(key=lambda item: item[0])
    return {'providers': [available[0][1]], 'reason': 'Multi-file or broad task scope; use one available graph provider.'}


def ensure(root, task=None):
    selected = policy(root)
    chosen = decision(root, selected, task)
    result = {'result': 'PASS', 'mode': selected['mode'], 'decision': chosen}
    for name in chosen['providers']:
        try:
            result[name] = PROVIDERS[name].ensure(root)
            if result[name]['freshness'] != 'fresh':
                raise HarnessError(f'Required {name} index must be fresh; restore the provider and run indexes ensure.')
        except (HarnessError, OSError, ValueError) as exc:
            if selected['mode'] != 'auto': raise
            result['decision'] = {'providers': [], 'reason': 'Optional graph unavailable; use source navigation.', 'error': str(exc)}
    return result


def collect(h, feature, task):
    selected = policy(h.root)
    indexes = ensure(h.root, task)
    question = ' '.join([task['outcome'], *task['scope']])[:500]
    contexts = {}
    for name in indexes['decision']['providers']:
        try:
            contexts[name] = PROVIDERS[name].query(h.root, question, 10 if name == 'codegraph' else 800)
            if contexts[name]['result'] != 'PASS':
                raise HarnessError(f'Required {name} context unavailable before implementation.')
        except (HarnessError, OSError, ValueError) as exc:
            if selected['mode'] != 'auto': raise
            contexts.pop(name, None)
            indexes['decision'] = {'providers': [], 'reason': 'Optional graph query failed; use source navigation.', 'error': str(exc)}
    record = redact({'task_id': task['id'], 'feature_id': feature['feature_id'],
                     'created_at': now(), 'input_fingerprint': h.binding(),
                     'question': question, 'indexes': indexes, 'navigation_policy': selected,
                     **{name + '_context': value for name, value in contexts.items()},
                     'limitations': ['No graph context collected; targeted source inspection is still required.'] if not contexts else
                     ['Graph results are navigation leads; inspect referenced source and requirements before implementation.']})
    ref = f'.harness/graph/task-context-{digest(task["id"])}.json'
    atomic(safe_path(h.root, ref), record)
    return {'result': 'PASS', 'reference': ref, 'mode': selected['mode'], 'decision': indexes['decision'],
            **{name: value['result'] for name, value in contexts.items()}}
