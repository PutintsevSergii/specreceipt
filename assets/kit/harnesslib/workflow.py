"""Bounded workflow advice and Python-owned policy. Local consent records are attestations only."""
import fnmatch
import hashlib
import json
import re
from .storage import HarnessError, digest, now, read, redact, safe_path
from . import readiness

PROFILES = ('FAST', 'STANDARD', 'STRICT')
# Token families, not substrings: author/productionize are not auth/production.
SENSITIVE_WORDS = set('auth authn authz authenticate authenticates authentication authorize authorizes authorization security privacy payment payments financial migrate migration migrations production integrity credential credentials permission permissions'.split())
RISK_CLASSIFIER_VERSION = 1
ACTIONS = set('add change changes changing modify modifies implement implements enforce require required requires remove removes disable disables bypass allow allows allowed deny denies denied validate validation protect protects access handling checks check'.split())
UNCERTAIN = re.compile(r'\b(unknown|unclear|uncertain|may|might|could|possibly|whether)\b|not (?:sure|known)|\?', re.I)
# Only complete noun-list statements of non-applicability are negatives.
# In particular "no authentication bypass is allowed" is NOT a negative scope fact.
EXCLUDED_NOUNS = {
    'auth', 'authentication', 'authorization', 'security', 'privacy', 'payments',
    'payment', 'financial changes', 'migration', 'migrations', 'credentials',
    'secrets', 'sensitive data', 'permissions', 'production impact',
    'production environment', 'production changes', 'authentication changes',
    'authorization changes', 'security changes', 'roles', 'authorization distinctions',
    'network service', 'network', 'persistence', 'deployment', 'remote repository work',
    'runtime dependency', 'generalized numeric parser', 'state', 'storage',
    'transaction', 'retention', 'data', 'ui', 'integration', 'recovery design',
    'rollback process', 'package metadata', 'additional exports', 'generalized parsing',
    'services', 'third-party dependencies', 'cli', 'browser ui', 'recovery data concerns',
}


def words(text):
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', text)
    return set(re.findall(r'[a-z]+', text.lower()))


def excluded_clause(text):
    value = re.sub(r'^[\s*\-]+', '', text.lower()).strip().rstrip(',').strip()
    value = re.sub(r'^not applicable:\s*', '', value)
    value = re.sub(r'^(?:the (?:pure )?function|the (?:local )?(?:module|library)|this task|the application) has no ', 'no ', value)
    if re.match(r'^(?:there (?:is|are) )?no ', value):
        value = re.sub(r'^(?:there (?:is|are) )?no ', '', value)
        value = re.sub(r' (?:(?:is|are) )?(?:involved|required|in scope|applicable|needed)$| exists?$', '', value)
    elif re.search(r' (?:is|are) (?:excluded|out of scope|not (?:applicable|required|involved|in scope))$', value):
        value = re.sub(r' (?:is|are) (?:excluded|out of scope|not (?:applicable|required|involved|in scope))$', '', value)
    else:
        return False
    value = re.sub(r',\s+(?:and|or)\s+', ', ', value)
    nouns = [re.sub(r'^(?:and|or)\s+', '', part.strip()).strip()
             for part in re.split(r',|\s+(?:and|or)\s+', value)]
    return bool(nouns) and all(noun in EXCLUDED_NOUNS for noun in nouns)


def prose_signals(text):
    """Return applicable and unresolved sensitive clauses; neither is an approval."""
    positive, ambiguous = False, False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#') and words(stripped) <= SENSITIVE_WORDS | {'and', 'scope', 'requirements', 'considerations', 'boundaries'}:
            continue  # A section label alone says nothing about the task.
        for clause in re.split(r'[.;\n]+|\b(?:but|however|whereas)\b|\band\s+(?=(?:add|change|modify|implement|remove|disable|enforce)\b)', stripped, flags=re.I):
            if re.fullmatch(r'\s*this draft does not authorize implementation\s*', clause, re.I):
                continue  # Lifecycle consent statement, not application authorization scope.
            tokens = words(clause)
            if not tokens & SENSITIVE_WORDS or excluded_clause(clause):
                continue
            if UNCERTAIN.search(clause):
                ambiguous = True
            elif re.search(r'\b(?:no|not|never|without)\b', clause, re.I) and not (
                tokens & {'bypass', 'disable', 'remove', 'allowed', 'deny', 'denied'} or re.search(r'\bnot only\b', clause, re.I)
            ):
                ambiguous = True  # Unrecognized negation is not positive evidence.
            elif tokens & ACTIONS or re.search(r'\bnot only\b', clause, re.I):
                positive = True
            else:
                ambiguous = True  # Mention alone is not proof of LOW or HIGH risk.
    return positive, ambiguous


def structured_text(ref, value):
    """Project only known record shapes; arbitrary JSON cannot hide behind metadata keys."""
    def strings(item):
        if isinstance(item, str): return item
        if isinstance(item, list): return '\n'.join(strings(x) for x in item)
        return ''
    if ref.startswith('specs/') and ref.endswith('/tasks.json') and isinstance(value, dict) and isinstance(value.get('tasks'), list):
        fields = ('outcome', 'requirements', 'acceptance_criteria', 'failure_scenarios')
        return '\n'.join(strings(task.get(key, '')) for task in value['tasks'] if isinstance(task, dict) for key in fields)
    if ref == '.harness/onboarding.json' and isinstance(value, dict) and isinstance(value.get('coverage'), dict):
        return '\n'.join(str(topic.get('rationale', '')) for topic in value['coverage'].values() if isinstance(topic, dict))
    if ref == '.harness/checks.json' and isinstance(value, dict) and isinstance(value.get('checks'), dict):
        return '\n'.join(strings(check.get(key, '')) for check in value['checks'].values() if isinstance(check, dict) for key in ('purpose', 'argv'))
    return None


def file_signals(ref, text):
    if ref.endswith('.json'):
        try: projected = structured_text(ref, json.loads(text))
        except ValueError: projected = None
        if projected is not None:
            return prose_signals(projected)
    if ref.endswith(('.md', '.txt', '.rst')):
        return prose_signals(text)
    # Source/config identifiers remain conservative, including camel/snake case.
    # A full-line comment is prose; it cannot negate a positive code line elsewhere.
    positive, ambiguous = bool(words(ref) & SENSITIVE_WORDS), False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(('#', '//', '/*', '*')):
            p, a = prose_signals(re.sub(r'^(?:#|//|/\*|\*)\s*', '', stripped))
            positive |= p; ambiguous |= a
        elif words(line) & SENSITIVE_WORDS:
            positive = True
    return positive, ambiguous


def task_signals(task):
    positive, ambiguous = prose_signals('\n'.join([task['outcome'], *task['requirements'], *task.get('acceptance_criteria', []), *task.get('failure_scenarios', [])]))
    for ref in task['scope']:
        if words(ref) & SENSITIVE_WORDS:
            if ref.endswith(('.md', '.txt', '.rst')): ambiguous = True
            else: positive = True
    return positive, ambiguous


def evidence_signals(h, task, refs):
    p, a = task_signals(task)
    positive = ['task scope/requirements'] if p else []
    ambiguous = ['task scope/requirements'] if a else []
    size = 0
    for ref in sorted(set(refs) | {x for x in task['scope'] if not x.endswith('/')}):
        path = safe_path(h.root, ref)
        if not path.is_file():
            if ref in refs: ambiguous.append(ref + ' (missing evidence)')
            continue  # A planned source file may not yet exist.
        length = path.stat().st_size; size += length
        if length > 65536 or size > 131072:
            ambiguous.append(ref + ' (inspection limit)'); continue
        p, a = file_signals(ref, path.read_text(errors='replace'))
        if p: positive.append(ref)
        if a: ambiguous.append(ref)
    return positive, ambiguous


def policy(h):
    path = safe_path(h.root, '.harness/workflow-policy.json')
    value = read(path) if path.exists() else {}
    allowed = {'minimum', 'strict_paths', 'required_checks', 'approval_requirements', 'openspec_required', 'separate_plan_approval'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise HarnessError('Invalid workflow policy fields')
    if value.get('minimum', 'FAST') not in PROFILES:
        raise HarnessError('Invalid minimum workflow')
    for key in ('strict_paths', 'required_checks', 'approval_requirements'):
        if not isinstance(value.get(key, []), list) or any(not isinstance(x, str) or not x for x in value.get(key, [])):
            raise HarnessError('Invalid workflow policy '+key)
    for key in ('openspec_required', 'separate_plan_approval'):
        if not isinstance(value.get(key, False), bool): raise HarnessError('Invalid workflow policy '+key)
    return value


def material(h, feature, task):
    # No repository inventory, index build, Skill loading or model calls.
    fields = ('requirements', 'outcome', 'scope', 'dependencies', 'acceptance_criteria', 'failure_scenarios', 'risk', 'required_checks', 'approval_requirements')
    paths = ['docs/TECH_SPEC.md', 'docs/ARCHITECTURE.md', 'docs/DECISION_QUEUE.md', '.harness/checks.json',
             f"specs/{feature['feature_id']}/spec.md", f"specs/{feature['feature_id']}/plan.md"]
    return digest({'risk_classifier':RISK_CLASSIFIER_VERSION, 'task':{k:task[k] for k in fields}, 'revisions':feature['revisions'], 'policy':policy(h),
                   'source':feature.get('spec_source'), 'inputs':{p:digest(safe_path(h.root,p).read_text()) for p in paths}})


def floor(h, task, facts):
    p = policy(h)
    rank = PROFILES.index(p.get('minimum', 'FAST'))
    reasons = ['Project policy minimum: '+p['minimum']] if 'minimum' in p else []
    if task['risk'] == 'high' or task_signals(task)[0] or facts.get('critical_risk'):
        rank = 2; reasons.append('High risk or security/production-sensitive scope')
    for scope in task['scope']:
        if any(fnmatch.fnmatch(scope, pattern) or (scope.endswith('/') and (pattern.startswith(scope) or scope.startswith(re.split(r'[*?\[]',pattern,maxsplit=1)[0]))) for pattern in p.get('strict_paths', [])):
            rank = 2; reasons.append('Project strict-path policy')
    if facts.get('public_api') or facts.get('architecture_change'):
        rank = max(rank, 1); reasons.append('Public API or architectural impact')
    return PROFILES[rank], reasons


def assess(h, task_id, facts_ref):
    feature, task = h.task(task_id)
    facts_path = safe_path(h.root,facts_ref)
    if facts_path.stat().st_size > 16384: raise HarnessError('Assessment facts must fit 16 KiB')
    facts = read(facts_path)
    allowed = {'critical_risk', 'critical_unknowns', 'unknowns', 'public_api', 'architecture_change', 'components', 'inspected', 'agent'}
    if not isinstance(facts, dict) or set(facts)-allowed: raise HarnessError('Invalid assessment facts')
    for key in ('critical_risk','public_api','architecture_change'):
        if not isinstance(facts.get(key), bool): raise HarnessError('Explicit boolean fact required: '+key)
    for key in ('critical_unknowns','unknowns','inspected'):
        if not isinstance(facts.get(key), list) or any(not isinstance(x,str) or not x.strip() for x in facts[key]):
            raise HarnessError('Explicit list required: '+key)
    if type(facts.get('components')) is not int or not 1 <= facts['components'] <= 1000:
        raise HarnessError('components must be an integer in 1..1000')
    if 'agent' in facts and (not isinstance(facts['agent'],str) or not facts['agent'].strip()): raise HarnessError('Invalid agent')
    if len(facts['inspected']) > 12: raise HarnessError('Preliminary assessment accepts at most 12 targeted references')
    inspected = {}; size = 0
    for ref in facts['inspected']:
        path = safe_path(h.root, ref)
        if not path.is_file() or path.stat().st_size > 65536: raise HarnessError('Inspect a bounded file (at most 64 KiB): '+ref)
        size += path.stat().st_size
        if size > 131072: raise HarnessError('Assessment inspection exceeds 128 KiB')
        inspected[ref] = digest(path.read_text())
    observed_sensitive, ambiguous = evidence_signals(h, task, inspected)
    policy_facts = {**facts, 'critical_risk':facts['critical_risk'] or bool(observed_sensitive)}
    minimum, reasons = floor(h, task, policy_facts)
    deeper = bool(facts['critical_unknowns'] or not inspected or ambiguous)
    moderate = task['risk'] == 'medium' or facts['components'] > 2 or facts['unknowns'] or facts['public_api'] or facts['architecture_change']
    complex_change = facts['architecture_change'] or facts['components'] > 5 or (facts['public_api'] and facts['components'] >= 3)
    recommendation = PROFILES[max(PROFILES.index(minimum), 2 if complex_change else 1 if moderate or deeper else 0)]
    reasons += (['Targeted inspection has unresolved critical questions'] if deeper else ['Bounded repository references recorded'])
    if moderate: reasons.append('Declared medium risk, multiple components, uncertainty or interface impact warrants structured investigation')
    reasons += ['Applicable sensitive evidence: '+ref for ref in observed_sensitive]
    reasons += ['Investigate ambiguous sensitive evidence: '+ref for ref in ambiguous]
    old = task.get('workflow', {})
    record = {'revision':old.get('revision',0)+1, 'material':material(h,feature,task), 'facts':facts,
              'inspected':inspected, 'inspection_bytes':size, 'sensitive_evidence':observed_sensitive, 'minimum':minimum, 'recommended':recommendation,
              'risk':task['risk'].upper() if minimum != 'STRICT' else 'HIGH',
              'complexity':'HIGH' if complex_change else 'MEDIUM' if moderate else 'LOW', 'uncertainty':'HIGH' if deeper else ('MEDIUM' if facts['unknowns'] else 'LOW'),
              'execution_cost':{'FAST':'targeted','STANDARD':'structured','STRICT':'full'}[recommendation],
              'deeper_required':deeper, 'reasons':reasons, 'selected':None, 'at':now(),
              'plan':safe_path(h.root,f"specs/{feature['feature_id']}/plan.md").read_text()}
    if len(record['plan'].encode()) > 16384: raise HarnessError('Brief assessment plan must fit 16 KiB; link deeper planning artifacts')
    # Identical facts and material keep the existing confirmation stable.
    if old and all(old.get(k) == record[k] for k in ('material','facts','inspected','sensitive_evidence','minimum','deeper_required','reasons')): return old
    if old.get('selected'):
        record['recommended'] = PROFILES[max(PROFILES.index(record['recommended']), PROFILES.index(old['selected']))]
    task['workflow'] = record
    for key in ('workflow-plan','plan'): task['approvals'].pop(key,None)
    h.save(h.state(),h.event('workflow-assessed','Workflow assessment recorded; explicit confirmation required.',task_id,feature['feature_id']),feature)
    return record


def decision_binding(h, feature, task):
    w = task['workflow']
    return digest({'material':material(h,feature,task), 'revision':w['revision'], 'facts':w['facts'],
                   'inspected':w['inspected'], 'selected':w['selected']})


def current_approval(h, task, key, fingerprint):
    a = task['approvals'].get(key)
    try: return bool(a and a['fingerprint'] == fingerprint and a['reference_hash'] == digest(safe_path(h.root,a['reference']).read_text()))
    except (OSError,HarnessError): return False


def deeper_sources(h, feature, task, ambiguous):
    """Map every reviewable finding to a current source; missing sources stay blocked."""
    result = {}
    for finding in ambiguous:
        if finding.endswith(' (missing evidence)'):
            raise HarnessError('Missing evidence cannot be resolved by deeper review: ' + finding)
        task_finding = finding == 'task scope/requirements'
        ref = (f'specs/{feature["feature_id"]}/tasks.json' if task_finding
               else finding.removesuffix(' (inspection limit)'))
        path = safe_path(h.root, ref)
        if not path.is_file(): raise HarnessError('Deeper review source is missing: ' + ref)
        sha = hashlib.sha256()
        if task_finding:
            # The workflow lives in tasks.json; hash the substantive task instead.
            source = {key:task[key] for key in ('outcome','requirements','acceptance_criteria',
                                                'failure_scenarios','scope','risk')}
            sha.update(json.dumps(source, sort_keys=True, separators=(',', ':')).encode())
        else:
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(65536), b''): sha.update(chunk)
        with path.open('rb') as stream:
            lines = sum(1 for _ in stream) or 1
        result[finding] = (sha.hexdigest(), lines)
    return result


def check_deeper_review(h, feature, task, ambiguous):
    w = task['workflow']
    record = w.get('deeper_review')
    if not record or record['material'] != w['material'] or record['revision'] != w['revision']:
        raise HarnessError('Current bounded deeper review required before STRICT confirmation')
    path = safe_path(h.root, record['reference'])
    if not path.is_file() or path.stat().st_size > 32768 or digest(path.read_text()) != record['reference_hash']:
        raise HarnessError('Deeper review reference changed or exceeds 32 KiB')
    review = read(path)
    if not isinstance(review,dict) or set(review) != {'task_id','material','assessment_revision','items'} or review['task_id'] != task['id'] or review['material'] != w['material'] or review['assessment_revision'] != w['revision']:
        raise HarnessError('Deeper review does not match the assessed task')
    sources = deeper_sources(h,feature,task,ambiguous)
    items = review['items']
    if not isinstance(items,list) or len(items) != len(sources):
        raise HarnessError('Deeper review must cover every ambiguous source exactly once')
    seen = set()
    for item in items:
        if not isinstance(item,dict) or set(item) != {'source','sha256','locations','finding','risk'}:
            raise HarnessError('Invalid deeper review item')
        source = item['source']
        if not isinstance(source,str) or source not in sources or source in seen:
            raise HarnessError('Deeper review source is missing, extra or duplicated')
        seen.add(source)
        sha, line_count = sources[source]
        if item['sha256'] != sha: raise HarnessError('Deeper review source changed: ' + source)
        if not isinstance(item['risk'],str) or item['risk'] not in {'HIGH','NOT_APPLICABLE'}:
            raise HarnessError('Deeper review must resolve risk explicitly')
        finding = item['finding']
        if not isinstance(finding,str) or not 40 <= len(finding) <= 1000 or finding != redact(finding):
            raise HarnessError('Deeper review needs a bounded, sanitized finding')
        locations = item['locations']
        if not isinstance(locations,list) or not 1 <= len(locations) <= 8:
            raise HarnessError('Deeper review needs bounded source line locations')
        for location in locations:
            if not isinstance(location,int) or isinstance(location,bool) or not 1 <= location <= line_count:
                raise HarnessError('Deeper review line is outside the source')
    return {'sources': sorted(sources), 'reference': record['reference']}


def resolve(h, task_id, review_ref):
    feature, task = h.task(task_id)
    w = task.get('workflow')
    if not w or w['material'] != material(h,feature,task):
        raise HarnessError('Assess current task inputs before deeper review')
    _, ambiguous = evidence_signals(h,task,w['inspected'])
    if not ambiguous or not w['deeper_required']:
        raise HarnessError('No ambiguous sources require deeper review')
    path = safe_path(h.root,review_ref)
    if not path.is_file() or path.stat().st_size > 32768: raise HarnessError('Deeper review is missing or exceeds 32 KiB')
    previous = w.get('deeper_review')
    w['deeper_review'] = {'reference':review_ref,'reference_hash':digest(path.read_text()),
                          'material':w['material'],'revision':w['revision']}
    try: result = check_deeper_review(h,feature,task,ambiguous)
    except Exception:
        if previous is None: w.pop('deeper_review',None)
        else: w['deeper_review'] = previous
        raise
    h.save(h.state(),h.event('workflow-deeper-reviewed','Bounded source review recorded; explicit STRICT confirmation still required.',task_id,feature['feature_id']),feature)
    return {'result':'PASS',**result}


def guard(h, feature, task):
    w = task.get('workflow')
    p = policy(h)
    if not set(p.get('required_checks',[])) <= set(task['required_checks']): raise HarnessError('Task omits mandatory project checks')
    if not set(p.get('approval_requirements',[])) <= set(task['approval_requirements']): raise HarnessError('Task omits mandatory project approvals')
    if not w:
        if task.get('workflow_required'): raise HarnessError('Workflow assessment and explicit confirmation required before implementation')
        return  # Existing records retain all legacy gates.
    if w['material'] != material(h,feature,task): raise HarnessError('Workflow reassessment required: material task inputs changed')
    sensitive, ambiguous = evidence_signals(h, task, w['inspected'])
    if ambiguous:
        if w.get('selected') != 'STRICT': raise HarnessError('Deeper targeted assessment requires STRICT: ' + ', '.join(ambiguous))
        check_deeper_review(h,feature,task,ambiguous)
    if w.get('selected') in {'FAST','STANDARD'} and sensitive:
        raise HarnessError('Workflow reassessment required: sensitive implementation scope ' + ', '.join(sensitive))
    minimum, _ = floor(h,task,{**w['facts'], 'critical_risk':w['facts']['critical_risk'] or bool(sensitive) or bool(w['sensitive_evidence'])})
    if w['facts']['critical_unknowns'] or not w['inspected'] or (w['deeper_required'] and not ambiguous): raise HarnessError('Deeper targeted assessment required before workflow confirmation')
    if w.get('selected') not in PROFILES: raise HarnessError('Explicit workflow and plan confirmation required')
    if PROFILES.index(w['selected']) < PROFILES.index(minimum): raise HarnessError('Selected workflow is below policy minimum '+minimum)
    binding = decision_binding(h,feature,task)
    for key in ['workflow-plan'] + (['plan'] if policy(h).get('separate_plan_approval') else []):
        if not current_approval(h,task,key,binding): raise HarnessError('Current '+key+' approval required')
    p = policy(h)
    if not set(p.get('required_checks',[])) <= set(task['required_checks']): raise HarnessError('Task omits mandatory project checks')
    if not set(p.get('approval_requirements',[])) <= set(task['approval_requirements']): raise HarnessError('Task omits mandatory project approvals')
    if feature['kind'] == 'application' and (w['selected'] == 'STRICT' or p.get('openspec_required')) and not feature.get('spec_source'):
        raise HarnessError('Selected workflow or project policy requires an OpenSpec source')


def confirm(h, task_id, profile, by, reference):
    feature, task = h.task(task_id)
    w = task.get('workflow')
    if not w: raise HarnessError('Assess task before confirmation')
    if profile not in PROFILES: raise HarnessError('Unknown workflow profile')
    if w['material'] != material(h,feature,task): raise HarnessError('Reassess changed material inputs')
    if w['facts']['critical_unknowns'] or not w['inspected'] or (w['deeper_required'] and not w.get('deeper_review')): raise HarnessError('Resolve critical unknowns with targeted assessment first')
    sensitive, ambiguous = evidence_signals(h, task, w['inspected'])
    if ambiguous:
        if profile != 'STRICT': raise HarnessError('Deeper review requires STRICT selection')
        check_deeper_review(h,feature,task,ambiguous)
    minimum,_ = floor(h,task,{**w['facts'], 'critical_risk':w['facts']['critical_risk'] or bool(sensitive) or bool(w['sensitive_evidence'])})
    if PROFILES.index(profile) < PROFILES.index(minimum): raise HarnessError('Below policy minimum '+minimum)
    if not readiness.substantive(by) or not readiness.substantive(safe_path(h.root,reference).read_text()):
        raise HarnessError('Actual developer confirmation reference and identity required')
    w['selected'] = profile
    # Use the official approval path; selection and plan share one attestation.
    h.save(h.state(),h.event('workflow-selected','Explicit selection '+profile,task_id,feature['feature_id']),feature)
    return h.approve(task_id,'workflow-plan',by,reference)
