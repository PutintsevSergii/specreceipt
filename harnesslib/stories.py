"""Story maps coordinate existing features; they never authorize task implementation.

Definitions are separate from decisions. Block evidence includes common contracts
and ancestor definitions, while later-block planning cannot rewrite earlier receipts.
"""
import re
from .storage import HarnessError, digest, read, safe_path, now, uid


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', value):
        raise HarnessError('Story, block and feature IDs must be lowercase letters, digits and hyphens')
    return value


def path(story_id):
    return '.harness/stories/' + identifier(story_id) + '.json'


def validate(h, definition):
    h.schema('story', definition)
    for values in [definition['requirements'], definition['contracts'], definition['scope'], definition['integration']]:
        if len(values) != len(set(values)) or any(not v.strip() for v in values):
            raise HarnessError('Story lists must contain distinct, nonblank values')
    identifier(definition['id'])
    blocks = {b['id']: b for b in definition['blocks']}
    if len(blocks) != len(definition['blocks']): raise HarnessError('Duplicate story block ID')
    features = [b['feature'] for b in blocks.values()] + [definition['integration_feature']]
    for value in [*blocks, *features]: identifier(value)
    if len(features) != len(set(features)): raise HarnessError('Each block and integration must have a distinct feature')
    requirements = set(definition['requirements'])
    covered = set()
    visited, visiting = set(), set()
    def visit(key):
        if key not in blocks: raise HarnessError('Unknown block dependency: ' + key)
        if key in visiting: raise HarnessError('Story block dependency cycle')
        if key in visited: return
        visiting.add(key)
        for dep in blocks[key]['dependencies']: visit(dep)
        visiting.remove(key); visited.add(key)
    for block in blocks.values():
        for values in (block['requirements'], block['acceptance'], block['dependencies']):
            if len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise HarnessError('Block lists must contain distinct, nonblank values')
        visit(block['id'])
        if not set(block['requirements']) <= requirements: raise HarnessError('Unknown story requirement in block')
        covered.update(block['requirements'])
    if covered != requirements: raise HarnessError('Story requirements must all be assigned to blocks')
    for rel in definition['contracts']:
        if not safe_path(h.root, rel).is_file(): raise HarnessError('Missing shared contract: ' + rel)
    return definition


def records(h):
    result = []
    owners = set()
    for p in sorted((h.root / '.harness/stories').glob('*.json')):
        record = read(safe_path(h.root, p.relative_to(h.root).as_posix()))
        h.schema('story-record', record)
        d = validate(h, record['definition'])
        if p.stem != d['id']: raise HarnessError('Story ID must match its filename')
        features = {b['feature'] for b in d['blocks']} | {d['integration_feature']}
        if owners & features: raise HarnessError('Feature belongs to multiple stories')
        owners.update(features); result.append(record)
    return result


def get(h, story_id):
    identifier(story_id)
    for record in records(h):
        if record['definition']['id'] == story_id: return record
    raise HarnessError('Unknown story: ' + story_id)


def common(h, d):
    return {k: d[k] for k in ('id', 'goal', 'scope', 'requirements')} | {
        'contracts': {rel: digest(safe_path(h.root, rel).read_text(encoding='utf-8')) for rel in d['contracts']}}


def map_binding(h, record):
    return digest({'definition': record['definition'], 'common': common(h, record['definition'])})


def context(h, feature_id):
    for record in records(h):
        d = record['definition']
        blocks = {b['id']: b for b in d['blocks']}
        selected = next((b for b in blocks.values() if b['feature'] == feature_id), None)
        if not selected and d['integration_feature'] != feature_id: continue
        included = {}
        def include(b):
            if b['id'] in included: return
            for dep in b['dependencies']: include(blocks[dep])
            included[b['id']] = b
        if selected: include(selected)
        else:
            for b in blocks.values(): include(b)
        return {'common': common(h, d), 'blocks': included,
                **({'integration': d['integration']} if not selected else {})}
    return None


def check_configuration(h, task):
    """Story receipts pin every executed check; unrelated future checks may be added.

    Full repository fingerprints still govern current verification and review.
    Legacy receipts retain their original whole-configuration binding.
    """
    cfg = read(safe_path(h.root, '.harness/checks.json'))
    feature, _ = h.task(task['id'])
    if context(h, feature['feature_id']) is None: return cfg
    names = {name for t in h.check_closure(task) for name in t['required_checks']}
    return cfg | {'checks': {name: cfg['checks'][name] for name in sorted(names)}}


def definition_inputs(h, feature, task, inputs):
    if context(h, feature['feature_id']) is None: return inputs
    inputs = dict(inputs)
    if '.harness/checks.json' in inputs:
        inputs['.harness/checks.json'] = digest(check_configuration(h, task))
    if '.harness/onboarding.json' in inputs:
        record = read(safe_path(h.root, '.harness/onboarding.json'))
        inputs['.harness/onboarding.json'] = digest({k: v for k, v in record.items() if k != 'approval'})
    return inputs


def decision_current(h, decision, binding):
    if not decision or decision.get('binding') != binding: return False
    try: return decision['reference_hash'] == digest(safe_path(h.root, decision['reference']).read_text(encoding='utf-8'))
    except (OSError, HarnessError, KeyError): return False


def decision(h, binding, by, reference, expected):
    from .readiness import substantive
    if expected != binding: raise HarnessError('Decision package changed; inspect it again before approving')
    text = safe_path(h.root, reference).read_text(encoding='utf-8')
    if not by.strip() or not substantive(text): raise HarnessError('Actual developer approval reference and name required')
    return {'binding': binding, 'by': by, 'reference': reference, 'reference_hash': digest(text), 'at': now()}


def save(h, record, summary, extra=None):
    h.save(h.state(), h.event('story-updated', summary), extra={path(record['definition']['id']): record, **(extra or {})})


def propose(h, definition, apply=False, expected=None):
    validate(h, definition)
    existing = next((r for r in records(h) if r['definition']['id'] == definition['id']), None)
    features = {b['feature'] for b in definition['blocks']} | {definition['integration_feature']}
    for other in records(h):
        if other == existing: continue
        if features & ({b['feature'] for b in other['definition']['blocks']} | {other['definition']['integration_feature']}):
            raise HarnessError('Feature belongs to another story')
    before = map_binding(h, existing) if existing else None
    binding = digest({'before': before, 'definition': definition, 'common': common(h, definition)})
    changed = [b['id'] for b in definition['blocks'] if not existing or b not in existing['definition']['blocks']]
    affected = set(changed)
    if existing:
        old = existing['definition']
        if common(h, old) != common(h, definition): affected.update(b['id'] for b in definition['blocks'])
        old_features = {b['feature'] for b in old['blocks']} | {old['integration_feature']}
        for name in old_features - features:
            feature = h.features().get(name)
            if feature and any(t['history'] or t.get('execution') or t['evidence'] for t in feature['tasks']):
                raise HarnessError('Cannot detach a feature with execution history; preserve it in the story')
    while True:
        expanded = affected | {b['id'] for b in definition['blocks'] if affected.intersection(b['dependencies'])}
        if expanded == affected: break
        affected = expanded
    result = {'result': 'PASS', 'story_id': definition['id'], 'proposal_binding': binding,
              'changed_blocks': changed, 'affected_blocks': sorted(affected), 'definition': definition,
              'effect': 'Save a DRAFT map; no task approvals are granted or transferred.'}
    if not apply: return result
    if expected != binding: raise HarnessError('Preview the current story proposal and supply --expected')
    # Existing tasks may be mapped, but no task metadata, evidence or approvals are copied.
    record = {'definition': definition, 'map_approval': None, 'blocks': {}, 'acceptance': None}
    extra = {}
    if existing:
        record['blocks'] = existing['blocks']
        record['acceptance'] = existing.get('acceptance')
        extra['.harness/story-history/' + uid() + '.json'] = existing
    save(h, record, 'Saved draft story map ' + definition['id'], extra)
    return result | {'saved': True}


def approve_map(h, story_id, by, reference, expected):
    record = get(h, story_id)
    record['map_approval'] = decision(h, map_binding(h, record), by, reference, expected)
    save(h, record, 'Approved story map; individual task approvals remain required')
    return status(h, story_id)


def feature_binding(h, feature_id):
    feature = h.features().get(feature_id)
    if not feature: return None
    return digest([{'id': t['id'], 'definition': h.definition(t), 'evidence': t['evidence'],
                    'approvals': t['approvals'], 'status': t['status']} for t in feature['tasks']])


def location(h, feature_id):
    for record in records(h):
        d = record['definition']
        block = next((b for b in d['blocks'] if b['feature'] == feature_id), None)
        if block or d['integration_feature'] == feature_id:
            return {'story_id': d['id'], 'goal': d['goal'], 'block_id': block['id'] if block else None,
                    'map': str(h.root / path(d['id'])), 'status_command': 'specreceipt story status ' + d['id'],
                    'notice': 'Task acceptance does not accept its block or the integrated story.'}
    return None


def accepted(h, record, block):
    feature = h.features().get(block['feature'])
    approval = record['blocks'].get(block['id'])
    binding = digest({'feature': feature_binding(h, block['feature']), 'snapshot': approval.get('result_snapshot')}) if approval else None
    return bool(feature and all(h.completed(t) for t in feature['tasks']) and
                decision_current(h, approval, binding))


def guard(h, feature, task):
    for record in records(h):
        d = record['definition']
        block = next((b for b in d['blocks'] if b['feature'] == feature['feature_id']), None)
        integration = d['integration_feature'] == feature['feature_id']
        if not block and not integration: continue
        if not decision_current(h, record['map_approval'], map_binding(h, record)):
            raise HarnessError('Story map approval missing or stale: ' + d['id'])
        if feature.get('schema_version') == 2 or not feature.get('spec_source'):
            raise HarnessError('Story blocks require a formal feature with its own OpenSpec change')
        other_sources = [f['spec_source']['change'] for f in h.features().values()
                         if f.get('spec_source') and f['feature_id'] in {b['feature'] for b in d['blocks']} | {d['integration_feature']}]
        if len(other_sources) != len(set(other_sources)): raise HarnessError('Story features must use distinct OpenSpec changes')
        required = set(block['requirements'] if block else d['requirements'])
        criteria = set(block['acceptance'] if block else d['integration'])
        if not required <= {r for t in feature['tasks'] for r in t['requirements']}:
            raise HarnessError('Feature does not cover its story requirements')
        if not criteria <= {c for t in feature['tasks'] for c in t['acceptance_criteria']}:
            raise HarnessError('Feature does not cover its story acceptance scenarios')
        dependencies = block['dependencies'] if block else [b['id'] for b in d['blocks']]
        for dep in dependencies:
            predecessor = next(b for b in d['blocks'] if b['id'] == dep)
            if not accepted(h, record, predecessor): raise HarnessError('Story predecessor is not accepted: ' + dep)
        # Sequential blocks, even when their graph allows independent work.
        for f in h.features().values():
            if f['feature_id'] == feature['feature_id']: continue
            if f['feature_id'] in {b['feature'] for b in d['blocks']} | {d['integration_feature']}:
                if any(t['status'] in {'IN_PROGRESS', 'IMPLEMENTED', 'VERIFIED'} for t in f['tasks']):
                    raise HarnessError('Finish or block the other active story block first')


def package(h, story_id, block_id=None):
    from . import reporting
    record = get(h, story_id); d = record['definition']
    block = next((b for b in d['blocks'] if b['id'] == block_id), None)
    if block_id and not block: raise HarnessError('Unknown story block')
    feature_id = block['feature'] if block else d['integration_feature']
    feature = h.features().get(feature_id)
    gaps = []
    state = h.state()
    if state['uncertain_outcome'] or state['active_operation'] or state['blockers'] or (h.root / '.harness/transaction.json').exists():
        gaps.append('Resolve interrupted operations and project blockers before acceptance')
    if not feature: gaps.append('Detail and import OpenSpec feature: ' + feature_id)
    else:
        try: guard(h, feature, feature['tasks'][0])
        except HarnessError as exc: gaps.append(str(exc))
        for t in feature['tasks']:
            if not h.completed(t): gaps.append('Task not accepted: ' + t['id'])
            if not h.current_evidence(t): gaps.append('Current verification required: ' + t['id'])
    if not block:
        for b in d['blocks']:
            if not accepted(h, record, b): gaps.append('Block not accepted: ' + b['id'])
            f = h.features().get(b['feature'])
            if f:
                for t in f['tasks']:
                    if not h.current_evidence(t): gaps.append('Final regression required: ' + t['id'])
    snapshot = h.binding()
    binding = digest({'map': map_binding(h, record), 'feature': feature_binding(h, feature_id),
                      'blocks': record['blocks'], 'snapshot': snapshot}) if not block else digest({'feature': feature_binding(h, feature_id), 'snapshot': snapshot})
    return {'result': 'BLOCKED' if gaps else 'PASS', 'story_id': story_id, 'block_id': block_id,
            'outcome': block['outcome'] if block else d['goal'], 'verification': block['acceptance'] if block else d['integration'],
            'binding': binding, 'result_snapshot': snapshot, 'blockers': gaps,
            'tasks': [reporting.task_report(h, t['id']) for t in feature['tasks']] if feature else [],
            'effect': 'Accept this block only; later implementation needs its own approvals.' if block else 'Accept the integrated story; no publication authorized.'}


def accept(h, story_id, block_id, by, reference, expected):
    p = package(h, story_id, block_id)
    if p['blockers']: raise HarnessError('; '.join(p['blockers']))
    record = get(h, story_id)
    approval = decision(h, p['binding'], by, reference, expected)
    if block_id:
        approval['result_snapshot'] = p['result_snapshot']
        record['blocks'][block_id] = approval
    else: record['acceptance'] = approval
    save(h, record, 'Accepted ' + (('block ' + block_id) if block_id else ('story ' + story_id)))
    return {'result': 'PASS', 'story_id': story_id, 'block_id': block_id, 'effect': p['effect']}


def status(h, story_id):
    record = get(h, story_id); d = record['definition']
    approved = decision_current(h, record['map_approval'], map_binding(h, record))
    rows = []
    for b in d['blocks']:
        f = h.features().get(b['feature'])
        state = 'ACCEPTED' if accepted(h, record, b) else 'PLANNED'
        blockers = []
        if state != 'ACCEPTED' and f:
            try: guard(h, f, f['tasks'][0])
            except HarnessError as exc: blockers.append(str(exc))
            state = 'BLOCKED' if blockers else ('AWAITING_ACCEPTANCE' if all(h.completed(t) for t in f['tasks']) else 'IN_PROGRESS' if any(t['status'] != 'TODO' for t in f['tasks']) else 'READY_FOR_TASK_APPROVAL')
        rows.append({'id': b['id'], 'outcome': b['outcome'], 'feature': b['feature'], 'status': state, 'dependencies': b['dependencies'], 'blockers': blockers})
    finished = False
    if approved and record.get('acceptance'):
        p = package(h, story_id)
        finished = not p['blockers'] and decision_current(h, record['acceptance'], p['binding'])
    pending = next((r for r in rows if r['status'] != 'ACCEPTED' and all(next(x for x in rows if x['id'] == dep)['status'] == 'ACCEPTED' for dep in r['dependencies'])), None)
    action = 'finished' if finished else 'approve-map' if not approved else 'block' if pending else 'integration'
    return {'result': 'PASS', 'story_id': story_id, 'goal': d['goal'], 'status': 'DONE' if finished else 'ACTIVE' if approved else 'DRAFT',
            'map_binding': map_binding(h, record), 'blocks': rows, 'next_action': action,
            'next_block': pending['id'] if pending else None, 'integration_feature': d['integration_feature'],
            'definition': d, 'approval_effect': 'Approve the map only; detailed block/task approvals remain required.'}


def next_story(h):
    for record in records(h):
        result = status(h, record['definition']['id'])
        if result['status'] != 'DONE':
            return {'result': 'BLOCKED', 'action': 'story-decision', 'story': result,
                    'reasons': ['Inspect story status and the next block; no automatic story approval.']}
    return None


def render(result):
    lines = [f"Story: {result['story_id']}"]
    if 'blocks' in result:
        lines += [result['goal'], 'Status: ' + result['status'], '']
        lines += [f"- {b['id']}: {b['status']} — {b['outcome']}" for b in result['blocks']]
        lines += ['', 'Next: ' + result['next_action'] + (' ' + result['next_block'] if result['next_block'] else ''),
                  'Map binding: ' + result['map_binding'], result['approval_effect']]
    else:
        lines += [result['outcome'], 'Result: ' + result['result'], 'Binding: ' + str(result['binding']), '', 'How to verify:']
        lines += ['- ' + c for c in result['verification']]
        lines += ['- ' + gap for gap in result['blockers']]
        for task in result['tasks']:
            lines += ['', 'Task: ' + task['task_id'] + ' — ' + task['title'],
                      'Verification: ' + task['verification']['status']]
            for check in task['verification']['checks']:
                lines.append('- ' + check['check'] + ': ' + check['result'])
            for name in ('evidence', 'review'):
                if task['paths'].get(name): lines.append(f"[{name.title()}](<{task['paths'][name]}>)")
            lines += ['- ' + warning for warning in task['warnings']]
        lines += ['', result['effect']]
    return '\n'.join(lines) + '\n'
