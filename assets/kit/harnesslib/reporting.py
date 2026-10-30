"""Reports use execution snapshots and evidence; presentation never decides lifecycle."""
from pathlib import Path
import json
import re
import shlex
import shutil
import tempfile
import sys
import os
from dataclasses import dataclass
from types import MappingProxyType
from .storage import is_link, HarnessError, atomic, safe_path, uid, now, digest
from . import compact, acceptance_evidence, check_inputs, workflow, verification


@dataclass(frozen=True)
class ReportSnapshot:
    """One read-only observation; never installed on the lifecycle engine."""
    files: object
    binding: str
    observed_at: str

    @classmethod
    def capture(cls, h):
        files = h.fingerprints()
        binding = digest({'files': files, 'environment': h.environment()})
        return cls(MappingProxyType(files), binding, now())


def report_evidence_current(h, task, snapshot):
    """Presentation freshness; authoritative current_evidence stays uncached."""
    if task.get('execution', {}).get('recognitions'):
        from . import reconciliation
        try:
            if task['execution']['definition'] != h.definition(task): return False
            if reconciliation.classify(h, task, fingerprints=snapshot.files)['unrecognized']: return False
        except (HarnessError, OSError, ValueError): return False
    if not task['evidence']: return False
    refs = task['evidence'] + task.get('regression_evidence', [])
    ev = max((h.evidence(ref) for ref in refs), key=lambda e: e['created_at'])
    return h.successful_evidence(task, ev) and check_inputs.current(h, task, ev, snapshot.files)


def task_report(h, task_id, snapshot=None):
    snapshot = snapshot or ReportSnapshot.capture(h)
    feature, task = h.task(task_id)
    warnings = []
    try: current = bool(task['evidence']) and report_evidence_current(h, task, snapshot)
    except (HarnessError,OSError,ValueError) as exc:
        current = False; warnings.append('Evidence unavailable: '+str(exc))
    status = task['status']
    effective = 'REWORK' if status == 'VERIFIED' and not current else status
    if status == 'DONE':
        try:
            if not h.completed(task): effective = 'REWORK'
        except (HarnessError,OSError,ValueError): effective = 'REWORK'
    files = []
    baseline = task.get('execution',{}).get('baseline')
    recognized = set()
    if baseline is not None:
        from . import reconciliation
        try: recognized = set(reconciliation.classify(h, task, fingerprints=snapshot.files)['recognized'])
        except (HarnessError,OSError,ValueError) as exc: warnings.append('Scope reconciliation: '+str(exc))
        after = snapshot.files
        for rel in sorted(set(baseline)|set(after)):
            if baseline.get(rel) != after.get(rel):
                files.append({'path':rel,'absolute_path':str(h.root/rel),
                              'change':'created' if rel not in baseline else 'deleted' if rel not in after else 'modified',
                              'attribution':'recognized_pre_existing' if rel in recognized else 'task_scope' if any(rel == s or (s.endswith('/') and rel.startswith(s)) for s in task['scope']) else 'unrecognized',
                              'in_scope':any(rel == s or (s.endswith('/') and rel.startswith(s)) for s in task['scope'])})
    else: warnings.append('No execution baseline; changed files are unknown.')
    evidence = None
    if task['evidence']:
        try: evidence = max((h.evidence(r) for r in task['evidence'] + task.get('regression_evidence',[])), key=lambda e:e['created_at'])
        except (HarnessError,OSError,ValueError) as exc: warnings.append('Latest evidence unreadable: '+str(exc))
    checks = [{k:r.get(k) for k in ('check','result','exit_code','command','summary','log','input_binding','reused_from')} for r in (evidence or {}).get('results',[])]
    test_counts = {}
    for check in checks:
        text = check.get('summary') or ''
        tap = {k:int(v) for k,v in re.findall(r'^# (pass|fail|skipped) (\d+)\s*$',text,re.M)}
        if set(tap) == {'pass','fail','skipped'}: test_counts[check['check']] = tap
    counts = {state:sum(r['result']==state for r in checks) for state in ('PASS','FAIL','NOT_RUN','BLOCKED')}
    if not evidence: warnings.append('No execution evidence: verification has not been demonstrated.')
    elif not current: warnings.append('Verification evidence is stale; rerun the required checks.')
    selected = task.get('workflow',{}).get('selected')
    approvals = {}
    binding = snapshot.binding
    for kind in sorted(set(task['approval_requirements'])|set(task['approvals'])|{'workflow-plan','plan','implementation','developer','review'}):
        a = task['approvals'].get(kind)
        expected = workflow.decision_binding(h,feature,task) if kind in {'workflow-plan','plan'} and task.get('workflow') else binding
        approvals[kind] = {'status':'CURRENT' if workflow.current_approval(h,task,kind,expected) else 'STALE' if a else 'NOT_RECORDED',
                           'reference':str(h.root/a['reference']) if a else None}
    required = set(task['approval_requirements']) | {'review'}
    if task.get('workflow') or task.get('workflow_required'): required |= {'workflow-plan','developer'}
    if task.get('workflow') and workflow.policy(h).get('separate_plan_approval'): required.add('plan')
    for kind, approval in approvals.items():
        approval['required'] = kind in required
        if approval['status'] == 'NOT_RECORDED' and kind not in required: approval['status'] = 'NOT_REQUIRED'
    if not task.get('workflow') and 'plan' not in task['approvals']:
        rel = f"specs/{feature['feature_id']}/plan.md"
        try:
            meta = h.metadata(rel)
            approvals['plan'].update(document_status=meta['status'],revision=meta['revision'],reference=str(h.root/rel))
            if 'plan' not in required and meta['status'] == 'APPROVED': approvals['plan']['status'] = 'DOCUMENT_APPROVED'
        except (HarnessError,OSError) as exc: warnings.append('Plan metadata unavailable: '+str(exc))
    if selected and not workflow.policy(h).get('separate_plan_approval'):

        approvals['plan'] = {**approvals['workflow-plan'],'combined_with':'workflow-plan'}
    if approvals['review']['status'] == 'CURRENT':
        try: verification.review(h,task,safe_path(h.root,task['approvals']['review']['reference']).read_text(encoding='utf-8'))
        except (HarnessError,OSError,ValueError): approvals['review']['status'] = 'INVALID'
    # DONE eligibility is bound to the original execution evidence, not later regression inputs.
    if effective == 'DONE':
        for kind, approval in approvals.items():
            approval['completion_status'] = 'ACCEPTED_AT_DONE' if kind in (set(task['approval_requirements']) | {'review'} | ({'developer'} if task.get('workflow') else set())) else 'NOT_REQUIRED_FOR_DONE'
    blocked = None
    if effective not in {'DONE','BLOCKED','REWORK'}:
        try: h.ready(feature,task)
        except (HarnessError,OSError,ValueError) as exc: blocked = str(exc); warnings.append(blocked)
    temporary = h.root == Path(tempfile.gettempdir()).resolve() or Path(tempfile.gettempdir()).resolve() in h.root.parents or any(p in {'tmp','private/tmp'} for p in h.root.parts)
    if temporary: warnings.append('Temporary project: files may be deleted. Retain review artifacts before cleanup.')
    next_action = next_step(h, task, effective, current, approvals, blocked)
    git = h.git()
    return {'documentation':'compact' if compact.is_compact(feature) else 'formal','git':git,'task_id':task_id,'title':task['outcome'],'agent':task.get('workflow',{}).get('facts',{}).get('agent','unknown'),
            'workflow':selected or ('UNCONFIRMED' if task.get('workflow') else 'STRICT (legacy)'),
            'status':status,'effective_status':effective,'recorded_at':snapshot.observed_at,
            'regression_required':effective == 'DONE' and not current,
            'implementation_summary':f'Current lifecycle: {effective}; verification: '+('PASS' if current else 'FAIL' if evidence and evidence.get('result') != 'PASS' else 'STALE' if evidence else 'MISSING')+'.',
            'implementation_history':next(({'state':x['to'],'recorded_at':x['at'],'text':x['reason']} for x in reversed(task['history']) if x['to']=='IMPLEMENTED'),None),
            'paths':{'project':str(h.root),'engine_source':str(Path(__file__).resolve().parents[1]),'temporary':temporary,
                     'evidence':str(h.root/next(r for r in task['evidence'] + task.get('regression_evidence',[]) if h.evidence(r)['id'] == evidence['id'])) if evidence else None,
                     'review':approvals['review']['reference'],'review_package':None},
            'changed_files':files,'verification':{'status':'PASS' if current else 'FAIL' if evidence and evidence.get('result') != 'PASS' else 'STALE' if evidence else 'MISSING','checks':checks,'check_counts':counts,
                                               'input_coverage':check_inputs.coverage((evidence or {}).get('results',[])),
                                               'dependency_support':(evidence or {}).get('dependency_support',[]),
                                               'acceptance_support':acceptance_evidence.reported(task, evidence, h),
                                               'test_counts':test_counts or None,'test_counts_note':'Recognized TAP counts are reported per check; otherwise individual test counts remain unknown.'},
            'approvals':approvals,'warnings':warnings,'next_action':next_action,
            'inspect_command':f'git -C {shlex.quote(str(h.root))} diff -- .; git -C {shlex.quote(str(h.root))} status --short' if git.get('head') else None,
            'openspec':'OpenSpec checklist tracks planning progress; Python lifecycle and current evidence determine completion.' if feature.get('spec_source') else None}


def render(data, markdown=False):
    lines = ['# AI Engineering Harness' if markdown else 'AI Engineering Harness']
    lines += [('Historical snapshot' if data.get('report_kind') == 'historical' else 'Current report') + ': '+data.get('generated_at','timestamp unavailable')]
    if data.get('progress'):
        p = data['progress']
        lines.append(f"Self-test progress (last observed {p.get('updated_at', 'unknown')}): {p.get('completed', '?')}/{p.get('total', '?')}; {p.get('elapsed_seconds', '?')}s; {p.get('status', 'UNAVAILABLE')}")
        if p.get('active_test'): lines.append('Active test: '+p['active_test'])
    if not data['tasks']:
        lines += ['Project: '+data.get('project','unknown'),'Next action: Complete project readiness and define an approved task.','./harness readiness']
    for t in data['tasks']:
        if t.get('documentation')=='compact':
            lines += compact_card(t)
            continue
        lines += ['',f"{t['task_id']} — {t['title']}",f"Status: {t['status']} | Effective: {t['effective_status']} | Workflow: {t['workflow']} | Agent: {t['agent']}",
                  'Project: '+t['paths']['project'],'Engine: '+t['paths']['engine_source'],
                  f"Files changed: {len(t['changed_files'])}"]
        history = t.get('implementation_history')
        if history: lines.append(f"Historical implementation note [{history['state']} at {history['recorded_at']}]: {history['text']}")
        for f in t['changed_files']:
            label = ' [recognized pre-existing; no write permission]' if f.get('attribution') == 'recognized_pre_existing' else ''
            lines.append(f"  {f['change'].upper()} {f['path']}{label}\n    {f['absolute_path']}")
            if f.get('retained_path'): lines.append('    Retained: '+f['retained_path'])
        lines += ['Verification: '+t['verification']['status']+' | checks '+json.dumps(t['verification']['check_counts']),
                  'Tests: '+(json.dumps(t['verification']['test_counts']) if t['verification']['test_counts'] else 'individual counts unavailable; see evidence logs.'),
                  'Approvals: '+', '.join(k+'='+v['status']+(' (combined)' if v.get('combined_with') else '') for k,v in t['approvals'].items())]
        for support in t['verification'].get('acceptance_support', {}).get('criteria', []):
            lines.append('Criterion support: '+support['criterion']+' | '+support['level']+' | '+support['limitation'])
            for observation in support.get('observations', []):
                lines.append('Observed required cases ('+observation['check']+'): '+', '.join(observation['cases'])+' | '+observation['reference'])
            for review in support.get('reviews', []):
                lines.append('Semantic attestation: '+review['reviewer']+' ('+review['reviewer_type']+') | '+review['reference'])
            for probe in support.get('probes', []):
                lines.append('Targeted fault detected: '+probe['check']+' | '+probe['reference'])
        for dependency in t['verification'].get('dependency_support', []):
            for support in dependency['support']['criteria']:
                lines.append('Dependency criterion support: '+dependency['task_id']+' | '+support['criterion']+' | '+support['level'])
        lines.append('Evidence input coverage: '+t['verification'].get('input_coverage','GLOBAL')+'; scoped evidence is not full-repository verification.')
        for check in t['verification']['checks']:
            if check.get('reused_from'): lines.append('Reused current check receipt: '+check['reused_from'])
            lines.append('Check: '+check['check']+' '+check['result']+' | '+shlex.join(check['command'] or []))
            if check.get('log'): lines.append('Log: '+str(Path(t['paths']['project'])/check['log']))
        for key in ('evidence','review','review_package'):
            if t['paths'][key]: lines.append(key.replace('_',' ').title()+': '+t['paths'][key])
        if t['inspect_command']: lines.append('Inspect: '+t['inspect_command'])
        if t['openspec']: lines.append(t['openspec'])
        lines += ['Warning: '+x for x in t['warnings']]
        lines += ['Next action: '+t['next_action']['message']]
        if t['next_action']['command']: lines.append(t['next_action']['command'])
    return '\n'.join(lines)+'\n'


def evidence_artifacts(h, reference):
    """Retain the bounded observation/review/reuse chain, not just its hashes."""
    from .storage import read
    pending=[reference]; seen=set(); refs=set()
    while pending:
        ref=pending.pop()
        if ref in seen: continue
        seen.add(ref)
        if len(seen)>128: raise HarnessError('Evidence retention chain exceeds 128 receipts')
        ev=h.evidence(ref); refs.add(ref)
        for result in ev['results']:
            if result.get('log'): refs.add(result['log'])
            if result.get('case_observation'): refs.add(result['case_observation']['reference'])
            if result.get('reused_from'): pending.append(result['reused_from'])
        sections=[ev.get('acceptance_support',{}), *[d['support'] for d in ev.get('dependency_support',[])]]
        for section in sections:
            for row in section.get('criteria',[]):
                for key in ('observations','reviews','probes'):
                    for artifact in row.get(key,[]): refs.add(artifact['reference'])
                for review in row.get('reviews',[]):
                    path=safe_path(h.root,review['reference'])
                    if path.stat().st_size>32768: raise HarnessError('Semantic retention artifact exceeds limit')
                    data=read(path)
                    if not isinstance(data,dict) or not isinstance(data.get('assertions'),list): raise HarnessError('Invalid semantic retention artifact')
                    for assertion in data['assertions']:
                        if not isinstance(assertion,dict) or not isinstance(assertion.get('path'),str): raise HarnessError('Invalid retained assertion path')
                        refs.add(assertion['path'])
    return refs


def report(h, task_id=None, format='json', retain=False, retain_dir=None):
    snapshot = ReportSnapshot.capture(h)
    ids = [task_id] if task_id else [t['id'] for f in h.features().values() for t in f['tasks']]
    from .test_progress import observed
    data = {'project':str(h.root),'report_kind':'historical' if retain else 'current','generated_at':snapshot.observed_at,'state_updated_at':h.state()['updated_at'],'tasks':[task_report(h,i,snapshot) for i in ids], 'progress':observed(h.root)}
    if retain:
        # Opt-in bounded artifact snapshot, not a full project copy or automatic archive.
        for task in data['tasks']:
            if retain_dir is not None:
                base = Path(retain_dir).absolute()
                if any(is_link(p) for p in [base,*base.parents]): raise HarnessError('Symlink export directory refused')
                if base.resolve() == h.root or h.root in base.resolve().parents: raise HarnessError('External retention must be outside project; use --retain for local evidence')
                dest = base/(task['task_id']+'-'+uid())
            else:
                dest = safe_path(h.root,'.harness/evidence/reports/'+task['task_id']+'-'+uid())
            dest.mkdir(parents=True,exist_ok=True)
            refs = [f['path'] for f in task['changed_files'] if f['change'] != 'deleted']
            refs += [Path(p).relative_to(h.root).as_posix() for k,p in task['paths'].items() if k in {'evidence','review'} and p]
            refs += [c['log'] for c in task['verification']['checks'] if c.get('log')]
            if task['paths']['evidence']:
                refs += list(evidence_artifacts(h,Path(task['paths']['evidence']).relative_to(h.root).as_posix()))
            total = 0
            for ref in sorted(set(refs)):
                source = safe_path(h.root,ref)
                total += source.stat().st_size
                if total > 8*1024*1024: raise HarnessError('Review retention exceeds 8 MiB; select artifacts manually')
                target = safe_path(dest,'files/'+ref)
                target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
                for changed in task['changed_files']:
                    if changed['path'] == ref: changed['retained_path'] = str(target)
            task['paths']['review_package'] = str(dest)
        for task in data['tasks']:
            dest = Path(task['paths']['review_package'])
            snapshot = {**data,'tasks':[task]}
            atomic(dest/'report.json',snapshot); atomic_text(dest/'report.md',render(snapshot,True))
    return data if format == 'json' else {'text':render(data,format=='markdown')}


def approval_package(h, task_id, format='json', snapshot=None):
    """Read-only, current decision material; never records or implies approval."""
    def brief(value, limit=360):
        normalized = ' '.join(value.split())
        return normalized if len(normalized) <= limit else normalized[:limit-1].rstrip()+'… (full text in linked review)'
    snapshot = snapshot or ReportSnapshot.capture(h)
    feature, task = h.task(task_id)
    report = task_report(h, task_id, snapshot)
    if task['status'] != 'VERIFIED' or report['effective_status'] != 'VERIFIED':
        return {'result':'BLOCKED','task_id':task_id,'reason':'Task is not currently VERIFIED with fresh passing evidence.'}
    if report['verification']['status'] != 'PASS' or report['approvals']['review']['status'] != 'CURRENT':
        return {'result':'BLOCKED','task_id':task_id,'reason':'Current PASS evidence and a valid current review are required.'}
    if report['approvals']['developer']['status'] != 'NOT_RECORDED':
        return {'result':'BLOCKED','task_id':task_id,'reason':'Final developer approval is not pending; inspect task status.'}
    if not report['approvals']['developer']['required']:
        return {'result':'BLOCKED','task_id':task_id,'reason':'This task does not require final developer approval.'}
    if any(a['required'] and kind not in {'developer'} and a['status'] != 'CURRENT'
           for kind,a in report['approvals'].items()):
        return {'result':'BLOCKED','task_id':task_id,'reason':'Other required approvals are missing or stale.'}
    if report['next_action']['action'] != 'approval':
        return {'result':'BLOCKED','task_id':task_id,'reason':'Task is not at the final developer decision step.'}
    review_path = Path(report['paths']['review'])
    review = verification.review(h, task, review_path.read_text(encoding='utf-8'))
    limitations = [brief(row['limitation']) for row in review.get('criterion_evidence', [])]
    package = {
        'result':'PASS', 'task_id':task_id, 'outcome':task['outcome'],
        'acceptance_binding':compact.result_binding(h,task),
        'state':'Ready for your acceptance — not yet DONE',
        'review_summary':brief(review['summary']), 'review_verdict':review['verdict'],
        'recorded_at':snapshot.observed_at,
        'paths':{'spec':str(h.root/f"specs/{feature['feature_id']}/spec.md"),
                 'plan':str(h.root/f"specs/{feature['feature_id']}/plan.md"),
                 'evidence':report['paths']['evidence'], 'review':str(review_path)},
        'changed_files':report['changed_files'],
        'checks':[{k:c.get(k) for k in ('check','result','summary','log','input_binding','reused_from')} for c in report['verification']['checks']],
        'acceptance_support':report['verification']['acceptance_support'],
        'dependency_support':report['verification']['dependency_support'],
        'input_coverage':report['verification']['input_coverage'],
        'limitations':limitations or ['The review has no structured criterion limitations; inspect the linked review and evidence.'],
        'approval_effect':f'DONE accepts only the verified result of {task_id}. It does not approve a commit, push, publication, deployment or any other task.',
        'approval_command':f'./harness task approve {task_id} --kind developer --by NAME --reference FILE',
    }
    if compact.is_compact(feature):
        package['paths']['spec'] = package['paths']['plan'] = str(h.root/f"specs/{feature['feature_id']}/tasks.json")
        package['approval_command'] = f'./harness workflow accept {task_id} --by NAME --reference FILE --expected '+package['acceptance_binding']
    return package if format == 'json' else {'result':'PASS','text':render_approval_package(package)}


def render_approval_package(package, markdown=True):
    def link(label, path):
        if not markdown: return f'{label}: {path}'
        escaped = str(path).replace('>', '%3E')
        return f'[{label}](<{escaped}>)'
    lines = [f"# Decision on {package['task_id']}" if markdown else f"Decision on {package['task_id']}",
             '', 'Result: '+package['outcome'], 'Review: '+package['review_summary'],
             'Verification: '+str(len(package['checks']))+' current checks; '+', '.join(c['check']+' '+c['result'] for c in package['checks']),
             '', 'Inspect:']
    lines.insert(-1,'Evidence input coverage: '+package.get('input_coverage','GLOBAL')+'; scoped evidence is not full-repository verification.')
    for support in package.get('acceptance_support',{}).get('criteria',[]):
        lines.insert(-1,'Criterion support: '+support['criterion']+' | '+support['level']+' | '+support['limitation'])
    for dependency in package.get('dependency_support',[]):
        for support in dependency['support']['criteria']:
            lines.insert(-1,'Dependency support: '+dependency['task_id']+' | '+support['criterion']+' | '+support['level'])
    for check in package['checks']:
        if check.get('reused_from'): lines.insert(-1,'Reused check: '+check['check']+' | '+check['reused_from'])
    lines.extend('- '+link(k.title(),v) for k,v in package['paths'].items())
    lines += ['', 'Changed files:']
    for item in package['changed_files']:
        label = item['path']+' ('+item['change']+', '+item['attribution'].replace('_',' ')+')'
        lines.append('- '+(label+' [deleted; inspect diff]' if item['change']=='deleted' else link(label,item['absolute_path'])))
    if not package['changed_files']: lines.append('- No changed files in the execution baseline.')
    lines += ['', 'Limits:'] + ['- '+x for x in package['limitations']]
    lines += ['', 'What approval means: '+package['approval_effect'],
              'If you accept this exact result, record a separate final developer approval before DONE.']
    return '\n'.join(lines)+'\n'


def next_step(h, task, effective, current, approvals, blocked=None):
    """Presentation only: eligibility still belongs to ready/check_approvals/transition."""
    tid = task['id']; cmd = './harness'
    state = h.state()
    def result(action, message, command=None):
        return {'action':action,'message':message,'command':command}
    if state['uncertain_outcome'] or state['blockers']:
        return result('recover','Resolve the active operation or recorded blockers before continuing.',f'{cmd} resume')
    if state['active_operation']:
        return result('progress','An operation is recorded as active. Inspect last-observed progress; recover only after confirming interruption.',f'{cmd} status {tid} --format terminal')
    if effective == 'DONE':
        if not current: return result('regression','Task completed historically; rerun required regression checks.',f'{cmd} regression {tid}')
        return result('finished','Finished. Task status: DONE.')
    if effective == 'BLOCKED': return result('blocked','Resolve the recorded task blocker.',f'{cmd} status {tid} --format terminal')
    if blocked: return result('blocked',blocked,f'{cmd} readiness {tid}')
    if effective == 'REWORK': return result('start','Inspect changes, restart approved work and rerun verification.',f'{cmd} task start {tid}')
    if effective == 'VERIFIED':
        order = ['review', *task['approval_requirements'], *(['developer'] if task.get('workflow') else [])]
        missing = next((k for k in order if approvals[k]['status'] != 'CURRENT'),None)
        if missing:
            action = 'review' if missing == 'review' else 'approval'
            if missing == 'developer':
                return result('approval','Present the current linked decision package and explain the exact result before asking for final developer approval.',
                              f'{cmd} approval-package {tid} --format markdown')
            sub = f'review {tid}' if action == 'review' else f'task approve {tid} --kind {missing}'
            return result(action,f'Inspect changed files and provide {missing} approval.',f'{cmd} {sub} --by NAME --reference FILE')
        # Approval hashes and structured review were checked above against the
        # report snapshot. Actual DONE still runs fresh core.check_approvals.
        return result('complete','All required approvals current; finish task.',f'{cmd} task transition {tid} DONE --reason "Verified and approved"')
    if effective == 'IMPLEMENTED':
        return result('verify','Advance using current passing evidence.' if current else 'Run required verification.',
                      f'{cmd} task transition {tid} VERIFIED --reason "Current checks passed"' if current else f'{cmd} verify {tid}')
    if effective == 'TODO': return result('start','Review approved inputs, then start task.',f'{cmd} task start {tid}')
    return result('implement','Implement the approved slice.',f'{cmd} next')


def refresh_current(h):
    """Derived cache, excluded from fingerprints; never rewrite immutable evidence."""
    target = '.harness/reports/current.json'
    try:
        data = report(h)
        atomic(safe_path(h.root,target), data)
        atomic_text(safe_path(h.root,'.harness/reports/current.md'), render(data,True))
        marker = safe_path(h.root,'.harness/reports/refresh-error.json')
        if marker.exists(): marker.unlink()
    except Exception as exc:
        # The lifecycle transaction already committed. Do not report its operation as failed.
        print('WARNING: lifecycle committed but current report refresh failed; run status for live state ('+type(exc).__name__+').',file=sys.stderr)
        try:
            atomic(safe_path(h.root,'.harness/reports/refresh-error.json'), {'status':'STALE','at':now(),'error_type':type(exc).__name__})
        except Exception: pass


def atomic_text(path, content):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists(): temporary.unlink()


def invalidate_current(h, reason):
    """Keep bounded assessment cheap: invalidate the cache without a source inventory."""
    try:
        data = {'report_kind':'stale','generated_at':now(),'state_updated_at':h.state()['updated_at'],
                'project':str(h.root),'reason':reason,'tasks':[]}
        atomic(safe_path(h.root,'.harness/reports/current.json'),data)
        atomic_text(safe_path(h.root,'.harness/reports/current.md'),'# Stale derived report\n\n'+reason+'\nRun ./harness status --format terminal for live state.\n')
    except Exception as exc:
        print('WARNING: current report cache invalidation failed ('+type(exc).__name__+'); use live status.',file=sys.stderr)


def compact_card(t):
    v=t['verification']; review=t['approvals']['review']
    phase=('Ready for your acceptance — not yet DONE' if t['next_action']['action']=='approval' else
           'Historically DONE; current regression '+v['status'] if t['effective_status']=='DONE' else t['effective_status'])
    checks=[c['check']+': '+c['result']+(' (reused from '+str(c['reused_from'])+')' if c.get('reused_from') else ' (executed)') for c in v['checks']]
    return ['',t['task_id']+' — '+t['title'],
            'Project: '+t['paths']['project']+' | Branch: '+str(t['git'].get('branch')),
            'Profile: '+t['workflow']+' | '+phase,
            'Changed: '+(', '.join(f['path'] for f in t['changed_files']) or 'No changes recorded'),
            'Checks: '+('; '.join(checks) or 'Not run'),
            'Acceptance support: '+'; '.join(row['criterion']+': '+row['level'] for row in v['acceptance_support']['criteria']),
            'Review: '+review['status']+'; inspect linked record for reviewer identity and limitations',
            'Limitations: '+('; '.join(t['warnings']) or 'Only the declared checks and recorded review are established; no release/platform claim'),
            'Next: '+t['next_action']['message']]
