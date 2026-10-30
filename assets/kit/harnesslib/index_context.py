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
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'mode', 'providers'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['mode'] not in ('source', 'required')
            or not isinstance(value['providers'], list)
            or any(not isinstance(p, str) or p not in PROVIDERS for p in value['providers'])
            or len(set(value['providers'])) != len(value['providers'])
            or (value['mode'] == 'source' and value['providers'])
            or (value['mode'] == 'required' and not value['providers'])):
        raise HarnessError('Invalid .harness/navigation.json: use version 1 source with no providers or required with unique codegraph/graphify providers.')
    return value


def ensure(root):
    selected = policy(root)
    result = {'result': 'PASS', 'mode': selected['mode']}
    for name in selected['providers']:
        result[name] = PROVIDERS[name].ensure(root)
        if result[name]['freshness'] != 'fresh':
            raise HarnessError(f'Required {name} index must be fresh; restore the provider and run indexes ensure.')
    return result


def collect(h, feature, task):
    selected = policy(h.root)
    indexes = ensure(h.root)
    question = ' '.join([task['outcome'], *task['scope']])[:500]
    contexts = {}
    for name in selected['providers']:
        contexts[name] = PROVIDERS[name].query(h.root, question, 10 if name == 'codegraph' else 800)
        if contexts[name]['result'] != 'PASS':
            raise HarnessError(f'Required {name} context unavailable before implementation.')
    record = redact({'task_id': task['id'], 'feature_id': feature['feature_id'],
                     'created_at': now(), 'input_fingerprint': h.binding(),
                     'question': question, 'indexes': indexes, 'navigation_policy': selected,
                     **{name + '_context': value for name, value in contexts.items()},
                     'limitations': ['Source mode records policy only, not inspected source or graph evidence.'] if not contexts else
                     ['Graph results are navigation leads; inspect referenced source and requirements before implementation.']})
    ref = f'.harness/graph/task-context-{digest(task["id"])}.json'
    atomic(safe_path(h.root, ref), record)
    return {'result': 'PASS', 'reference': ref, 'mode': selected['mode'],
            **{name: value['result'] for name, value in contexts.items()}}
