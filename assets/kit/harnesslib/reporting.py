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
from . import workflow, verification


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
    return h.successful_evidence(task, ev) and ev['fingerprint'] == snapshot.binding


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
    checks = [{k:r.get(k) for k in ('check','result','exit_code','command','summary','log')} for r in (evidence or {}).get('results',[])]
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
    return {'task_id':task_id,'title':task['outcome'],'agent':task.get('workflow',{}).get('facts',{}).get('agent','unknown'),
            'workflow':selected or ('UNCONFIRMED' if task.get('workflow') else 'STRICT (legacy)'),
            'status':status,'effective_status':effective,'recorded_at':snapshot.observed_at,
            'regression_required':effective == 'DONE' and not current,
            'implementation_summary':f'Current lifecycle: {effective}; verification: '+('PASS' if current else 'FAIL' if evidence and evidence.get('result') != 'PASS' else 'STALE' if evidence else 'MISSING')+'.',
            'implementation_history':next(({'state':x['to'],'recorded_at':x['at'],'text':x['reason']} for x in reversed(task['history']) if x['to']=='IMPLEMENTED'),None),
            'paths':{'project':str(h.root),'engine_source':str(Path(__file__).resolve().parents[1]),'temporary':temporary,
                     'evidence':str(h.root/next(r for r in task['evidence'] + task.get('regression_evidence',[]) if h.evidence(r)['id'] == evidence['id'])) if evidence else None,
                     'review':approvals['review']['reference'],'review_package':None},
            'changed_files':files,'verification':{'status':'PASS' if current else 'FAIL' if evidence and evidence.get('result') != 'PASS' else 'STALE' if evidence else 'MISSING','checks':checks,'check_counts':counts,
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
        for check in t['verification']['checks']:
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
            refs += [str(Path(p).relative_to(h.root)) for k,p in task['paths'].items() if k in {'evidence','review'} and p]
            refs += [c['log'] for c in task['verification']['checks'] if c.get('log')]
            total = 0
            for ref in refs:
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
