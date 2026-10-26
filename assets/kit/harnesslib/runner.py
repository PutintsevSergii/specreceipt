"""Deterministic local dispatcher. Adapters edit files; only this driver advances state.

No provider is installed or selected. A process exit is not acceptance evidence.
A persisted intent without a result is never automatically replayed.
"""
import time
from .storage import HarnessError, atomic, digest, read, safe_path, now, uid
from . import assessment, openspec_tool, readiness, verification


def next_action(h):
    state = h.state()
    if state['uncertain_outcome'] or state['active_operation'] or state['blockers']:
        return {'result':'BLOCKED','action':'recover','reasons':state['blockers'] or ['Operation active or uncertain']}
    h.validate()
    tasks = [t for f in h.features().values() for t in f['tasks']]
    if not tasks: return {'result':'BLOCKED','action':'onboard','reasons':['No approved tasks are defined']}
    active = next((t for t in tasks if t['id'] == state['active_task'] and t['status'] not in {'DONE','BLOCKED'}),None)
    candidates = [active] if active else sorted((t for t in tasks if t['status'] not in {'DONE','BLOCKED'}),key=lambda t:t['id'])
    blocked = []
    for task in candidates:
        feature,_ = h.task(task['id'])
        try:
            h.ready(feature,task)
            verification.acceptance(task)
            verification.validate_scope(h.root,task['scope'])
        except HarnessError as exc:
            blocked.append(task['id']+': '+str(exc)); continue
        action = {'TODO':'start','REWORK':'start','IN_PROGRESS':'implement','IMPLEMENTED':'verify','VERIFIED':'review'}[task['status']]
        if action == 'review':
            try: h.check_approvals(task); action = 'complete'
            except (HarnessError,OSError):
                if 'review' in task['approvals']:
                    # A valid review may be waiting for a real developer approval.
                    approval = task['approvals']['review']
                    content = safe_path(h.root,approval['reference']).read_text()
                    if approval['fingerprint'] == h.binding() and approval['reference_hash'] == digest(content):
                        verification.review(h,task,content); action='approval'
        from .reporting import task_report
        presentation = task_report(h,task['id'])['next_action']
        return {'result':'PASS','action':action,'next_action':presentation,'task_id':task['id'],'feature_id':feature['feature_id'],
                'scope':task['scope'],'required_checks':sorted({n for t in h.check_closure(task) for n in t['required_checks']}),
                'acceptance_checks':task['acceptance_checks']}
    if all(h.completed(t) for t in tasks):
        stale = [t['id'] for t in tasks if not h.current_evidence(t)]
        if stale: return {'result':'PASS','action':'regression','task_id':stale[0]}
        return {'result':'PASS','action':'finished'}
    return {'result':'BLOCKED','action':'blocked','reasons':blocked or ['Remaining tasks are explicitly BLOCKED']}


def authorization_hash(cfg, reference):
    return digest({'configuration':{k:v for k,v in cfg.items() if k != 'approval_hash'}, 'reference':reference})


def configuration(h):
    path = safe_path(h.root,'.harness/runner.json')
    if not path.exists(): return None
    cfg = read(path); h.schema('runner',cfg)
    if not cfg['enabled']: return None
    reference = safe_path(h.root,cfg['approval_reference']).read_text()
    if not readiness.substantive(reference) or authorization_hash(cfg, reference) != cfg['approval_hash']:
        raise HarnessError('Runner authorization reference is absent or stale')
    return cfg


def run(h, max_steps, max_seconds, new_run=False):
    if max_steps < 1 or max_seconds < 1: raise HarnessError('Run budgets must be positive')
    h.reconcile()
    if h.state()['uncertain_outcome']: raise HarnessError('Inspect and acknowledge interrupted operation before run')
    cfg = configuration(h)
    path = safe_path(h.root,'.harness/runner-state.json')
    signature = digest({'configuration':cfg,'max_steps':max_steps,'max_seconds':max_seconds})
    if path.exists() and not new_run:
        record = read(path); h.schema('runner-state',record)
        if record['configuration'] != signature: raise HarnessError('Run inputs changed; explicitly start --new-run after review')
    else:
        record = {'id':uid(),'configuration':signature,'steps':0,'elapsed_seconds':0.0,'failures':0,'last_action':None}
    def persist(summary):
        h.save(h.state(), h.event('runner',summary), extra={'.harness/runner-state.json':record})
    persist('Bounded run initialized or resumed; budgets persist across invocations.')
    while record['steps'] < max_steps and record['elapsed_seconds'] < max_seconds:
        if record['failures'] >= (cfg['max_failures'] if cfg else 1):
            return {'result':'BLOCKED','action':'failure-budget','run':record}
        action = next_action(h)
        if action['result'] != 'PASS' or action['action'] in {'finished','approval'}:
            return {**action,'run':record}
        phase = action['action']; task_id = action.get('task_id')
        if phase in {'implement','review'} and cfg is None:
            return {**action,'result':'BLOCKED','reason':'Configure an authorized adapter or perform this role in the current agent session','run':record}
        if cfg and task_id not in cfg['task_ids']:
            return {**action,'result':'BLOCKED','reason':'Task is outside runner authorization','run':record}
        start = time.monotonic()
        record['steps'] += 1; record['last_action'] = action
        persist('Reserved run step before execution: '+phase)
        try:
            if phase == 'start': h.transition(task_id,'IN_PROGRESS','Bounded dispatcher selected ready task')
            elif phase == 'verify':
                # Do not start a check bundle that exceeds the remaining wall-time budget.
                check_cfg = read(h.root/'.harness/checks.json')['checks']
                required = sum(check_cfg[n]['timeout_seconds'] for n in action['required_checks'])
                if required > max_seconds-record['elapsed_seconds']:
                    return {'result':'BLOCKED','action':'time-budget','run':record}
                ev = h.verify(task_id)
                if ev['result'] != 'PASS':
                    h.transition(task_id,'REWORK','Required checks failed'); record['failures'] += 1
                    continue
                h.transition(task_id,'VERIFIED','Dispatcher observed current PASS evidence')
            elif phase == 'complete': h.transition(task_id,'DONE','Current verification and recorded approvals satisfied')
            elif phase == 'regression':
                task=h.task(task_id)[1]; checks=read(h.root/'.harness/checks.json')['checks']
                names={n for t in h.check_closure(task) for n in t['required_checks']}
                if sum(checks[n]['timeout_seconds'] for n in names) > max_seconds-record['elapsed_seconds']:
                    return {'result':'BLOCKED','action':'time-budget','run':record}
                if h.verify(task_id,regression=True)['result'] != 'PASS':
                    record['failures'] += 1
                    return {'result':'BLOCKED','action':'regression-failed','task_id':task_id,'run':record}
            else:
                task = h.task(task_id)[1]
                verification.scope_changes(h,task)
                review_path = f"specs/{action['feature_id']}/reviews/{task_id}.md"
                context = {**action,'environment_assessment':assessment.current(h.root),'review_path':review_path,'evidence':task['evidence'][-1] if task['evidence'] else None,
                           'instructions':'Read AGENTS.md, .harness/AGENTS.md when present, and the relevant role through harness skills. Use current assessed project skills as supplements; preserve required verification and approvals. Edit only approved scope for implement; review must only write review_path. Do not run lifecycle/approval commands. Exit zero only when this role is finished. Do not change approvals, configuration, or task records.'}
                feature = h.task(task_id)[0]
                if feature.get('spec_source'):
                    context['specification'] = openspec_tool.context(h.root,feature['spec_source']['change'])
                context_path = safe_path(h.root,'.harness/dispatch/context.json'); atomic(context_path,context)
                argv = [v.replace('{context}',str(context_path)).replace('{task_id}',task_id) for v in cfg[phase+'_argv']]
                before = h.binding()
                review_inputs = verification.inventory(h.root)
                review_inputs.pop(review_path,None)
                workflow_before = digest(h.features())
                state = h.state(); state['active_operation']={'id':uid(),'kind':'adapter','task':task_id,'phase':phase,'started_at':now()}
                h.save(state,h.event('adapter-start','Persisted adapter intent before execution.',task_id))
                check={'kind':'command','approved':True,'approval_reference':cfg['approval_reference'],'argv':argv,
                       'timeout_seconds':min(cfg['timeout_seconds'],max_seconds-record['elapsed_seconds'])}
                result = h.run_check('adapter-'+phase,check)
                if result['result'] == 'BLOCKED':
                    record['failures'] += 1
                    h.reconcile()  # uncertain effects stay blocked; never auto-retry
                    return {'result':'BLOCKED','action':'recover','run':record}
                state=h.state(); state['active_operation']=None
                h.save(state,h.event('adapter-finished','Adapter process returned; validating effects. '+result['summary'],task_id,result=result['result'],commands=[{'argv':result['command'],'exit_code':result['exit_code']}]))
                if digest(h.features()) != workflow_before: raise HarnessError('Adapter changed task workflow records')
                if phase == 'review':
                    after_review = verification.inventory(h.root); after_review.pop(review_path,None)
                    if h.binding() != before or review_inputs != after_review:
                        raise HarnessError('Reviewer changed implementation inputs or other reviews')
                verification.scope_changes(h,task)
                if result['result'] != 'PASS':
                    record['failures'] += 1
                    return {'result':'BLOCKED','action':'adapter-failed','task_id':task_id,'run':record}
                if phase == 'implement': h.transition(task_id,'IMPLEMENTED','Adapter returned; scope checked; acceptance execution pending')
                else:
                    report = verification.review(h,task,safe_path(h.root,review_path).read_text(),require_pass=False)
                    if report['verdict'] != 'PASS' or any(f['status'] == 'OPEN' for f in report['findings']):
                        h.transition(task_id,'REWORK','Reviewer requested changes; see '+review_path)
                        record['failures'] += 1
                        continue
                    h.approve(task_id,'review','configured-review-adapter',review_path)
        except (HarnessError,OSError) as exc:
            record['failures'] += 1
            h.note('blocker','Runner requires inspection: '+str(exc))
            return {'result':'BLOCKED','action':'inspect','reason':str(exc),'run':record}
        finally:
            record['elapsed_seconds'] += time.monotonic()-start
            persist('Run step ended; budget consumption persisted.')
    return {'result':'BLOCKED','action':'budget-exhausted','run':record}
