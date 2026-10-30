"""Versioned compact FAST contract; no second lifecycle or inferred consent."""
import copy
import json
from .report_operation import operation as report_operation
from .storage import HarnessError, read, safe_path, digest, now, uid

FIELDS = ('requirements','outcome','non_goals','constraints','scope','dependencies','acceptance_criteria',
          'failure_scenarios','risk','required_checks','approval_requirements','acceptance_checks','review_contract_version')

def enabled(h):
    from .workflow import policy
    return policy(h).get('experience') == {'version':1,'mode':'compact'}

def is_compact(feature):
    return feature.get('schema_version') == 2

def context(h):
    value = read(safe_path(h.root,'.harness/onboarding.json'))
    h.schema('onboarding',value)
    return value

def material_context(h):
    c = context(h)
    if c['schema_version'] == 2: return {k:v for k,v in c.items() if k != 'approval'}
    from .readiness import fingerprint
    return {'formal_context':fingerprint(h,c)}

def check_definitions(h):
    cfg = read(safe_path(h.root,'.harness/checks.json'))
    h.schema('checks',cfg)
    return {name:{k:v for k,v in check.items() if k not in {'approved','approval_reference'}} for name,check in cfg['checks'].items()}

def substantive(task):
    return {k:task[k] for k in FIELDS if k in task}

def brief(task):
    return json.dumps(substantive(task),ensure_ascii=False,indent=2)

def paths(feature):
    return ['.harness/checks.json','.harness/onboarding.json','.harness/environment.json']

def eligible(h, feature, task):
    from . import workflow, readiness, verification
    if not enabled(h): raise HarnessError('Compact mode is disabled: preview workflow migrate, then record the project decision')
    if feature['kind'] != 'application' or feature.get('spec_source') or feature['revisions']:
        raise HarnessError('Compact tasks cannot replace formal or linked requirements')
    p = workflow.policy(h)
    if p.get('openspec_required') or p.get('separate_plan_approval') or p.get('minimum','FAST') != 'FAST':
        raise HarnessError('Project policy requires formal workflow')
    w=task.get('workflow',{})
    if task['risk'] != 'low' or w.get('selected') not in {None,'FAST'} or w.get('recommended','FAST') != 'FAST':
        raise HarnessError('Compact documentation is eligible only for assessed low-risk FAST work')
    if not task.get('workflow_required'): raise HarnessError('Compact tasks require workflow approval')
    for key in ('outcome','non_goals','constraints','requirements','acceptance_criteria','failure_scenarios'):
        values=task.get(key,[]); values=[values] if isinstance(values,str) else values
        if not values or any(not readiness.substantive(v) for v in values): raise HarnessError('Incomplete compact brief: '+key)
    verification.acceptance(task); verification.validate_scope(h.root,task['scope'])

def project(h, require_approval=True, selected=None):
    from . import readiness, workflow
    c=context(h); blockers=[]
    if selected is not None and not is_compact(h.task(selected['id'])[0]): blockers.append('Formal tasks require the formal project-context contract')
    if c['schema_version'] != 2: return None
    if not enabled(h): blockers.append('Compact project context requires explicit compact policy')
    for key in ('intent','runtime','boundaries','safety_constraints','intent_reference'):
        if not readiness.substantive(c[key]): blockers.append('Missing project context: '+key)
    for key in ('developer_facts','observed_facts'):
        if any(not readiness.substantive(v) for v in c[key]): blockers.append('Unresolved context facts: '+key)
    blockers += ['Unresolved project decision: '+x for x in c['blocking_decisions']]
    cfg=read(h.root/'.harness/checks.json'); h.schema('checks',cfg)
    for name in c['application_checks']:
        check=cfg['checks'].get(name)
        if name in readiness.GENERIC_CHECKS or not check or check['kind']!='command' or not check['argv'] or not readiness.substantive(check.get('purpose','')):
            blockers.append('Application command and purpose required: '+name)
        elif require_approval and (not check['approved'] or not readiness.substantive(check['approval_reference'])):
            blockers.append('Unapproved application check: '+name)
    if require_approval:
        a=c['approval']
        expected=digest({'context':material_context(h),'checks':check_definitions(h),'environment':read(h.root/'.harness/environment.json')})
        if not a or a['fingerprint'] != expected:
            blockers.append('Current combined project-context decision required')
        else:
            try:
                if digest(safe_path(h.root,a['reference']).read_text()) != a['reference_hash']: blockers.append('Context approval reference changed')
            except (OSError,HarnessError): blockers.append('Context approval reference missing')
    return {'result':'BLOCKED' if blockers else 'PASS','application_ready':not blockers,'blockers':blockers,
            'application_checks':c['application_checks'],'next_action':'Review compact context and task together' if blockers else 'Continue approved task',
            'limitations':['Local decision references are attestations, not authenticated identity.']}

@report_operation
def proposal(h, value):
    """Host supplies observed facts and developer intent; engine owns all records."""
    from . import workflow, verification
    if not enabled(h): raise HarnessError('Legacy mode: preview workflow migrate before opting in')
    if set(value)-{'feature_id','task','context','checks','facts'}: raise HarnessError('Unknown proposal fields')
    task=copy.deepcopy(value['task'])
    if set(task)-set(FIELDS)-{'id'}: raise HarnessError('Proposal cannot supply lifecycle or approval records')
    feature={'schema_version':2,'feature_id':value['feature_id'],'kind':'application','revisions':{},'tasks':[task]}
    path=f"specs/{feature['feature_id']}/tasks.json"
    previous = None
    if safe_path(h.root,path).exists():
        old_feature, previous = h.task(task['id'])
        if old_feature['feature_id'] != feature['feature_id'] or not is_compact(old_feature) or len(old_feature['tasks'])!=1:
            raise HarnessError('Cannot replace a different task or formal feature')
        if previous['status']=='DONE': raise HarnessError('Accepted task: explicitly open a new attempt before changing its proposal')
        if previous['status'] in {'IN_PROGRESS','IMPLEMENTED','VERIFIED'}:
            h.transition(task['id'],'REWORK','Material proposal renewal requested; prior plan cannot authorize changes')
            previous=h.task(task['id'])[1]
    elif any(t['id']==task['id'] for f in h.features().values() for t in f['tasks']): raise HarnessError('Task identity already exists')
    task.update(status='TODO',approvals={},evidence=[],history=[],next_action='Await plan/profile decision',workflow_required=True)
    if previous:
        for key in ('status','history','evidence','execution','regression_evidence'):
            if key in previous: task[key]=copy.deepcopy(previous[key])
    h.schema('tasks',feature); eligible(h,feature,task)
    writes={}
    if 'context' in value:
        old=context(h)
        if old.get('approval') or any(f['kind']=='application' for f in h.features().values()):
            raise HarnessError('Existing project context must be reused; context migration needs explicit review')
        c={'schema_version':2,**value['context'],'approval':None}
        if c['schema_version']!=2: raise HarnessError('Unsupported context version')
        h.schema('onboarding',c); writes['.harness/onboarding.json']=c
    cfg=read(h.root/'.harness/checks.json')
    for name,check in value.get('checks',{}).items():
        if name in cfg['checks'] and {k:v for k,v in cfg['checks'][name].items() if k not in {'approved','approval_reference'}} == check: continue
        if name in cfg['checks'] and not previous: raise HarnessError('Existing check definitions must be preserved: '+name)
        cfg['checks'][name]={**check,'approved':False,'approval_reference':''}
    h.schema('checks',cfg)
    if set(task['required_checks'])-set(cfg['checks']): raise HarnessError('Undefined required check')
    writes['.harness/checks.json']=cfg
    facts_ref=f'.harness/proposals/{task["id"]}-facts.json'; writes[facts_ref]=value['facts']
    # Persist draft only. No readiness or approval is asserted by proposal creation.
    h.save(h.state(),h.event('proposal','Compact draft prepared; developer decision required',task['id']),feature,writes)
    workflow.assess(h,task['id'],facts_ref)
    return plan_card(h,task['id'])

def plan_card(h, task_id):
    from . import workflow
    f,t=h.task(task_id)
    blockers=[]
    try: eligible(h,f,t)
    except HarnessError as exc: blockers.append(str(exc))
    w=t.get('workflow',{})
    c=context(h)
    context_report=project(h,False)
    if context_report: blockers.extend(context_report['blockers'])
    blockers.extend('Critical unknown: '+v for v in w.get('facts',{}).get('critical_unknowns',[]))
    return {'result':'BLOCKED' if blockers else 'PASS','blockers':blockers,'action':'plan-decision','task_id':task_id,'project':str(h.root),'git':h.git(),
            'brief':substantive(t),'context':material_context(h),'environment':read(h.root/'.harness/environment.json'),'checks':check_definitions(h),
            'policy':workflow.policy(h),'recommended':w.get('recommended'),'minimum':w.get('minimum'),
            'unknowns':w.get('facts',{}).get('critical_unknowns',[])+c.get('blocking_decisions',[]),
            'proposal_binding':digest({'root':str(h.root),'task':task_id,'material':workflow.material(h,f,t),'assessment':assessment_material(w)}),
            'next_action':'Approve displayed plan/context/checks and profile, request changes, or choose a formal stricter profile'}

@report_operation
def confirm(h,task_id,profile,by,reference,expected):
    from . import workflow
    card=plan_card(h,task_id)
    if card['proposal_binding']!=expected: raise HarnessError('Displayed proposal is stale; review current plan')
    if card['blockers']: raise HarnessError('; '.join(card['blockers']))
    if profile!='FAST': raise HarnessError('Stricter selection requires formal requirements; retain the draft and prepare those inputs')
    content=safe_path(h.root,reference).read_text()
    from .readiness import substantive as meaningful
    if not meaningful(by) or not meaningful(content): raise HarnessError('Actual developer answer reference required')
    c=context(h)
    p=project(h,False)
    if p and p['blockers']: raise HarnessError('; '.join(p['blockers']))
    if not set(c['application_checks'])<=set(h.task(task_id)[1]['required_checks']): raise HarnessError('Task omits baseline application checks')
    # Risk/source guard is checked before any check authorization is recorded.
    f,t=h.task(task_id); w=t['workflow']
    if w['material']!=workflow.material(h,f,t): raise HarnessError('Reassess changed material inputs before confirmation')
    sensitive,ambiguous=workflow.evidence_signals(h,t,w['inspected'])
    minimum,_=workflow.floor(h,t,{**w['facts'],'critical_risk':w['facts']['critical_risk'] or bool(sensitive)})
    if minimum!='FAST' or ambiguous or w['deeper_required'] or card['unknowns']: raise HarnessError('Resolve risk/unknowns before compact approval')
    cfg=read(h.root/'.harness/checks.json')
    for name in t['required_checks']:
        check=cfg['checks'][name]
        if not check['approved']: check.update(approved=True,approval_reference=reference)
    writes={'.harness/checks.json':cfg}
    if c['schema_version']==2:
        c['approval']={'by':by,'at':now(),'reference':reference,'reference_hash':digest(content),
                       'fingerprint':digest({'context':material_context(h),'checks':check_definitions(h),'environment':read(h.root/'.harness/environment.json')})}
        writes['.harness/onboarding.json']=c
    state=h.state()
    if c['schema_version']==2:
        state['pending_decisions']=[v for v in state['pending_decisions'] if v not in {'COMPACT-INIT: Review eligible task and project context together.','APP-001: Fill and approve application specification and architecture.'}]
    h.save(state,h.event('compact-decision','Recorded disclosed context/check decision; local attestation',task_id),extra=writes)
    result=workflow.confirm(h,task_id,profile,by,reference)
    f,t=h.task(task_id)
    if t.get('execution') and t['execution']['definition']!=h.definition(t): h.replan(task_id,reference)
    return result


@report_operation
def migration(h, by=None, reference=None, expected=None):
    from . import workflow, readiness
    p=workflow.policy(h)
    preview={'result':'PASS','effective_mode':p.get('experience',{'version':1,'mode':'legacy'}),
             'changes':'Enable compact documentation for newly proposed eligible FAST tasks. Existing tasks, required checks, formal policy, scope, review and final acceptance remain mandatory. The policy change invalidates policy-bound task approvals; renew affected plans before continuation.',
             'policy':p,'binding':digest({'root':str(h.root),'policy':p}),
             'next_action':'Record one actual project decision with workflow migrate --by NAME --reference FILE --expected BINDING'}
    if by is None: return preview
    if expected!=preview['binding']: raise HarnessError('Migration preview changed')
    content=safe_path(h.root,reference).read_text()
    if not readiness.substantive(by) or not readiness.substantive(content): raise HarnessError('Actual project decision required')
    p['experience']={'version':1,'mode':'compact'}
    receipt=f'.harness/evidence/decisions/migration-{uid()}.json'
    h.save(h.state(),h.event('compact-migration','Explicit project opt-in by '+by+'; reference '+reference,evidence=[receipt]),
           extra={'.harness/workflow-policy.json':p,receipt:{'by':by,'at':now(),'reference':reference,'reference_hash':digest(content),'preview':preview}})
    return {**preview,'effective_mode':p['experience']}


def result_binding(h,task,binding=None):
    return digest({'project':str(h.root),'task':task['id'],'history':[x for x in task['history'] if x['to']!='DONE'],'evidence':task['evidence'],
                   'binding':binding or h.binding(),'review':task['approvals'].get('review')})


@report_operation
def accept(h,task_id,by,reference,expected):
    from .reporting import approval_package
    h.reconcile()
    f,t=h.task(task_id)
    if not is_compact(f): raise HarnessError('Use the existing final approval path for formal tasks')
    if result_binding(h,t)!=expected: raise HarnessError('Final acceptance is stale or belongs to another task/attempt')
    if reference in {a['reference'] for key,a in t['approvals'].items() if key in {'workflow-plan','plan','developer'}}:
        raise HarnessError('A separate current final answer reference is required; earlier consent cannot be reused')
    package=approval_package(h,task_id)
    if package['result']!='PASS': raise HarnessError(package['reason'])
    from .readiness import substantive as meaningful
    if not meaningful(by) or not meaningful(safe_path(h.root,reference).read_text()): raise HarnessError('Actual final developer answer required')
    h.approve(task_id,'developer',by,reference,expected_result=expected)
    return h.transition(task_id,'DONE','Developer accepted this exact verified result; final gates rechecked')


def instructions(h,task):
    from pathlib import PurePosixPath
    refs={'AGENTS.md','AGENTS.override.md','.harness/AGENTS.md'}
    for scope in task['scope']:
        for parent in PurePosixPath(scope).parents:
            refs.add((parent/'AGENTS.md').as_posix())
    return {ref:digest(safe_path(h.root,ref).read_text()) for ref in sorted(refs) if safe_path(h.root,ref).is_file()}


def assessment_material(w):
    return {k:w[k] for k in ('revision','material','facts','inspected','selected','minimum','recommended','deeper_required','sensitive_evidence') if k in w}


def definition_task(task):
    from .core import MUTABLE_TASK
    value={k:v for k,v in task.items() if k not in MUTABLE_TASK}
    if 'workflow' in value: value['workflow']=assessment_material(value['workflow'])
    return value
