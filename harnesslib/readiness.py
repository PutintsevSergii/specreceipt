"""Documentation readiness, with an explicit human-review attestation boundary."""
import json
import re
from .storage import HarnessError, digest, read, safe_path

SECTIONS = {
    'docs/TECH_SPEC.md': ['Goals','Users','Scope','Non-goals','Requirements','Stack','Persistence',
                         'Contracts','Security','Performance','Dependencies','Environments','Acceptance','Assumptions','Questions'],
    'docs/ARCHITECTURE.md': ['Boundaries','Modules','Dependencies','Data flows','Persistence',
                           'Recovery','Integrations','Testing','Observability','ADRs'],
}
GENERIC_CHECKS = {'harness-validate','harness-tests','graph-freshness','demo-doc'}
PLACEHOLDER = re.compile(r'\b(?:TBD|TODO|FIXME|UNCONFIGURED)\b|\?\?\?', re.I)


def substantive(value):
    value = re.sub(r'<!--.*?-->', '', value, flags=re.S).strip()
    return bool(value) and not PLACEHOLDER.search(value) and not re.fullmatch(r'(?:N/?A|none|not applicable)[.!]?', value, re.I)


def documents(h, blockers):
    for rel, required in SECTIONS.items():
        try:
            content = safe_path(h.root, rel).read_text()
            if h.metadata(rel)['status'] != 'APPROVED':
                blockers.append(f'{rel}: developer-approved document required.')
            if not substantive(content):
                blockers.append(f'{rel}: unresolved placeholder content.')
            headings = list(re.finditer(r'^## (.+?)\s*$', content, re.M))
            for title in required:
                matches = [i for i, item in enumerate(headings) if item.group(1) == title]
                if len(matches) != 1:
                    blockers.append(f'{rel}: require exactly one {title} section.')
                    continue
                index = matches[0]
                end = headings[index+1].start() if index+1 < len(headings) else len(content)
                if not substantive(content[headings[index].end():end]):
                    blockers.append(f'{rel} / {title}: fill the section or explain non-applicability.')
        except (HarnessError, OSError) as exc:
            blockers.append(str(exc))


def decisions(h, blockers, selected=None):
    """The decision queue remains the single decision source, using its documented table."""
    try:
        content = safe_path(h.root, 'docs/DECISION_QUEUE.md').read_text()
        rows = [[cell.strip() for cell in line.strip().strip('|').split('|')]
                for line in content.splitlines() if line.strip().startswith('|')]
        expected = ['ID','Status','Blocks implementation','Affected work','Decision / why it matters']
        if not rows or rows[0] != expected:
            raise HarnessError('docs/DECISION_QUEUE.md: use the documented decision table with Blocks implementation.')
        seen = set()
        for row in rows[1:]:
            if all(re.fullmatch(r':?-+:?', cell) for cell in row):
                continue
            if len(row) != len(expected):
                raise HarnessError('docs/DECISION_QUEUE.md: malformed decision row.')
            ident, status, blocking, affected, reason = row
            if not ident or ident in seen or status not in {'OPEN','DEFERRED','RESOLVED'} or blocking not in {'yes','no'} or not affected or not substantive(reason):
                raise HarnessError('docs/DECISION_QUEUE.md: invalid or duplicate decision row.')
            seen.add(ident)
            applies = True
            if ':' in affected or affected == '*':
                targets = [v.strip() for v in affected.split(',')]
                all_tasks = [(f,t) for f in h.features().values() for t in f['tasks']]
                known = {'*'} | {'task:'+t['id'] for f,t in all_tasks} | {'feature:'+f['feature_id'] for f,t in all_tasks} | {'requirement:'+r for f,t in all_tasks for r in t['requirements']}
                if any(v not in known for v in targets):
                    raise HarnessError('Decision has unknown affected-work selector: '+affected)
                actual = {'*'}
                if selected:
                    for t in h.check_closure(selected):
                        f,_ = h.task(t['id'])
                        actual |= {'task:'+t['id'], 'feature:'+f['feature_id']} | {'requirement:'+r for r in t['requirements']}
                applies = bool(actual & set(targets))
            # Legacy free text remains conservatively global.
            if applies and status != 'RESOLVED' and blocking == 'yes':
                blockers.append(f'Decision {ident} blocks implementation: {reason}')
    except (HarnessError, OSError) as exc:
        blockers.append(str(exc))


def fingerprint(h, record):
    files = {}
    for rel in [*SECTIONS, 'docs/DECISION_QUEUE.md', '.harness/checks.json', '.harness/environment.json']:
        files[rel] = safe_path(h.root, rel).read_text()
    return digest({'documents':files, 'onboarding':{k:v for k,v in record.items() if k != 'approval'}})


def project(h, require_approval=True, selected=None):
    blockers = []
    baseline = []
    documents(h, blockers)
    decisions(h, blockers, selected)
    record = None
    try:
        record = read(safe_path(h.root, '.harness/onboarding.json'))
        h.schema('onboarding', record)
        baseline = record['application_checks']
        if record['mode'] == 'UNCONFIRMED': blockers.append('Confirm whether onboarding is for a NEW or EXISTING project.')
        ids = [s['id'] for s in record['sources']]
        if len(ids) != len(set(ids)): blockers.append('Onboarding source IDs must be unique.')
        for source in record['sources']:
            if not all(substantive(source[k]) for k in ['reference','authorization']):
                blockers.append(f'Source {source["id"]}: record an actual reference and authorized scope.')
            # Check that evidence is available for initial/repeated review. Once
            # approved, source refactors affect test evidence, not document sign-off.
            if source['kind'] == 'repository' and (not record['approval'] or not require_approval):
                try:
                    path = safe_path(h.root, source['reference'])
                    if not path.exists(): raise HarnessError('Repository source no longer exists.')
                except (HarnessError, OSError) as exc:
                    blockers.append(f'Source {source["id"]}: {exc}')
        if not any(s['kind'] == 'human' for s in record['sources']):
            blockers.append('Record developer-provided intent; repository content cannot establish product approval.')
        for topic, coverage in record['coverage'].items():
            if coverage['status'] == 'OPEN': blockers.append(f'Onboarding topic {topic} is unresolved.')
            if coverage['status'] == 'NOT_APPLICABLE' and topic not in {'data','contracts'}:
                blockers.append(f'Onboarding topic {topic} needs a resolved project decision.')
            if coverage['status'] != 'OPEN':
                if not substantive(coverage['rationale']): blockers.append(f'Onboarding topic {topic}: record the decision or applicability rationale.')
                if not coverage['source_ids'] or not set(coverage['source_ids']) <= set(ids):
                    blockers.append(f'Onboarding topic {topic}: valid source references required.')
        config = read(safe_path(h.root, '.harness/checks.json'))
        h.schema('checks', config)
        environment = read(safe_path(h.root, '.harness/environment.json'))
        if not isinstance(environment, dict) or not environment or not substantive(json.dumps(environment)):
            blockers.append('Declare the application environment; empty or unconfigured values are not ready.')
        if config['stack_revision'] != h.revisions()['tech_spec']:
            blockers.append('Check configuration must pin the current technical specification revision.')
        if not record['application_checks']:
            blockers.append('Configure at least one application check; harness self-tests do not verify the application.')
        for name in record['application_checks']:
            check = config['checks'].get(name)
            if (name in GENERIC_CHECKS or not check or check['kind'] != 'command' or not check['argv']
                    or not check['approved'] or not substantive(check['approval_reference']) or not substantive(check['purpose'])):
                blockers.append(f'Application check {name}: approved, nonempty application command and purpose required.')
        if require_approval:
            approval = record['approval']
            if not approval:
                blockers.append('Developer documentation approval has not been recorded: use onboarding approve after actual approval.')
            else:
                try:
                    ref = safe_path(h.root, approval['reference']).read_text()
                    if not substantive(ref) or digest(ref) != approval['reference_hash'] or fingerprint(h,record) != approval['fingerprint']:
                        blockers.append('Documentation approval is stale; review changed inputs and obtain approval again.')
                except (HarnessError, OSError) as exc:
                    blockers.append(f'Documentation approval reference unavailable: {exc}')
    except (HarnessError, OSError, ValueError) as exc:
        blockers.append(str(exc))
    return {'result':'BLOCKED' if blockers else 'PASS','application_ready':not blockers,'blockers':blockers,
            'next_action':'Resolve listed gaps through project-onboarding; implementation stays blocked.' if blockers else 'Check readiness for the selected application task before implementation.',
            'limitations':['Structural completeness and a recorded approval do not authenticate the developer or prove semantic quality.'],
            'application_checks':baseline}


def task_gaps(h, feature, task):
    gaps = []
    from . import investigation, openspec_tool, workflow
    try: workflow.guard(h,feature,task)
    except (HarnessError,OSError) as exc: gaps.append(str(exc))
    try: openspec_tool.ready(h.root, feature)
    except (HarnessError, OSError) as exc: gaps.append(str(exc))
    try:
        if investigation.required(h, task['id']):
            result = investigation.check(h, task['id'])
            gaps.extend('Investigation: ' + gap for gap in result['gaps'])
    except (HarnessError, OSError) as exc: gaps.append('Investigation: ' + str(exc))
    if feature['revisions'] != h.revisions(): gaps.append('Feature revision pins are stale.')
    for filename in ['spec.md','plan.md']:
        rel = f'specs/{feature["feature_id"]}/{filename}'
        try:
            content = safe_path(h.root,rel).read_text()
            if h.metadata(rel)['status'] != 'APPROVED' or not substantive(content):
                gaps.append(f'{rel}: approved, completed inputs required.')
            for key,label in [('tech_spec','Tech-Spec-Revision'),('architecture','Architecture-Revision')]:
                if f'{label}: {feature["revisions"][key]}\n' not in content:
                    gaps.append(f'{rel}: missing/mismatched revision pin.')
        except (HarnessError,OSError) as exc: gaps.append(str(exc))
    for key in ['outcome','scope','requirements','acceptance_criteria','failure_scenarios']:
        values = task[key] if isinstance(task[key],list) else [task[key]]
        if not values or any(not substantive(value) for value in values): gaps.append(f'{task["id"]}: incomplete {key}.')
    spec = safe_path(h.root, f'specs/{feature["feature_id"]}/spec.md').read_text()
    reqs = spec + safe_path(h.root,'docs/TECH_SPEC.md').read_text()
    if feature.get('spec_source'):
        try: reqs = '\n'.join(openspec_tool.feature_source(h.root,feature).values())
        except (HarnessError,OSError) as exc: gaps.append(str(exc)); reqs = ''
    for req in task['requirements']:
        if not re.search(r'(?<![\w-])'+re.escape(req)+r'(?![\w-])', reqs): gaps.append(f'Unknown requirement {req}.')
    from . import verification
    try:
        verification.acceptance(task)
        verification.validate_scope(h.root,task['scope'])
    except HarnessError as exc: gaps.append(str(exc))
    for path in task['scope']:
        try: safe_path(h.root,path)
        except HarnessError as exc: gaps.append(str(exc))
    config = read(safe_path(h.root,'.harness/checks.json'))
    h.schema('checks',config)
    for name in task['required_checks']:
        check = config['checks'].get(name)
        if not check or not check['approved'] or not substantive(check['approval_reference']):
            gaps.append(f'{task["id"]}: required check {name} is undefined or unapproved.')
    for dep in task['dependencies']:
        _, other = h.task(dep)
        if not h.completed(other): gaps.append(f'Dependency {dep} is not currently complete.')
    state = h.state()
    if state['uncertain_outcome'] or state['active_operation'] or state['blockers']:
        gaps.append('Resolve current operation uncertainty or workflow blockers before application work.')
    return gaps


def report(h, task_id=None):
    selected = h.task(task_id)[1] if task_id is not None else None
    result = project(h, selected=selected)
    if task_id is not None:
        feature, task = h.task(task_id)
        result['task_id'] = task_id
        if feature['kind'] != 'application':
            result['blockers'].append('Select an application task for the onboarding readiness report.')
        else:
            try:
                result['blockers'].extend(task_gaps(h,feature,task))
            except (HarnessError,OSError,ValueError) as exc:
                result['blockers'].append(f'Cannot assess task readiness: {exc}')
            for name in result['application_checks']:
                if name not in task['required_checks']:
                    result['blockers'].append(f'{task_id}: missing baseline application check {name}.')
        result['implementation_ready'] = not result['blockers']
        result['result'] = 'PASS' if result['implementation_ready'] else 'BLOCKED'
        result['next_action'] = 'Start the approved task; keep readiness current before each implementation batch.' if result['implementation_ready'] else 'Resolve listed gaps before implementation.'
    return result
