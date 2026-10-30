"""Reviewed per-check independence, retaining the complete safe scope inventory."""
import copy
import hashlib
import shutil
import sys
from pathlib import Path
from . import processes, verification
from .storage import HarnessError, digest, read, safe_path


def contains(prefix, path):
    return path == prefix or (prefix.endswith('/') and path.startswith(prefix))


def validate(h, check, contract):
    verification.validate_scope(h.root, contract['inputs'] + contract['independent'])
    if (len(set(contract['inputs'])) != len(contract['inputs']) or len(set(contract['independent'])) != len(contract['independent'])
            or len(contract['rationale'].strip()) < 40):
        raise HarnessError('Input contract needs unique regions and a concrete independence rationale')
    protected = {'package.json','package-lock.json','npm-shrinkwrap.json','pyproject.toml','requirements.txt','uv.lock',
                 'AGENTS.md','AGENTS.override.md','harness','harness.cmd'}
    for region in contract['independent']:
        parts=Path(region).parts
        if (any(p.startswith('.') for p in parts) or parts[0] in ('docs','specs','schemas','harnesslib','scripts','templates')
                or region in protected or Path(region).suffix in ('.json','.yaml','.yml','.toml','.lock')
                or (region.endswith('/') and len(parts)<2)
                or any(contains(region, p.rstrip('/')) or contains(p,region.rstrip('/')) for p in contract['inputs'])):
            raise HarnessError('Independent regions cannot overlap inputs, policies, global configuration or broad roots')
    ref=contract['approval_reference']
    verification.validate_scope(h.root,[ref])
    if any(contains(p,ref) for p in contract['independent']): raise HarnessError('Contract approval cannot be independent')
    text=safe_path(h.root,ref).read_text(encoding='utf-8')
    if len(text.strip())<40 or digest(text)!=contract['approval_hash']:
        raise HarnessError('Input-contract approval is missing or changed; obtain genuine review of the new declaration')


def revision(h, check, contract, files):
    """Approval pins every non-independent path, command and effective environment.

    checks.json is omitted to avoid hashing the declaration into itself; the
    complete selected check definition is separately included without its contract.
    The normal task definition also binds the entire checks configuration.
    """
    filtered={p:v for p,v in files.items() if p!='.harness/checks.json' and not any(contains(r,p) for r in contract['independent'])}
    if '.harness/onboarding.json' in filtered:
        intake=read(safe_path(h.root,'.harness/onboarding.json'))
        filtered['.harness/onboarding.json']=digest({k:v for k,v in intake.items() if k!='approval'})
    executable=sys.executable if check['argv'] and check['argv'][0]=='{python}' else shutil.which(check['argv'][0]) if check['argv'] else None
    runtime_hash=None
    runtime_mode=None
    if executable:
        runtime=Path(executable).resolve()
        if runtime.is_file() and runtime.stat().st_size <= 64*1024*1024:
            runtime_mode=runtime.stat().st_mode & 0o111
            runtime_hash=hashlib.sha256(runtime.read_bytes()).hexdigest()
    return digest({'files':filtered,'check':{k:v for k,v in check.items() if k!='input_contract'},
                   'environment':h.environment(),'process_environment_hash':digest(processes.environment()),
                   'executable':str(Path(executable).resolve()) if executable else None,'runtime_hash':runtime_hash,'runtime_mode':runtime_mode})


def binding(h, task, name, check, files):
    global_hash=digest({'files':dict(files),'environment':h.environment()})
    result={'mode':'GLOBAL','hash':global_hash,'reason':'Legacy/default global inputs'}
    contract=check.get('input_contract')
    if not contract: return result
    validate(h,check,contract)
    current=revision(h,check,contract,files)
    identity={'worktree':str(h.root.resolve()),'branch':h.git()['branch'],'task':task['id'],'check':name}
    # Opted-in checks retain their effective environment/identity binding even
    # while conservative global fallback is active.
    result['hash']=digest({'global':global_hash,'revision':current,'contract':contract,'identity':identity})
    # Case observations remain invocation-specific and always execute fresh.
    if check['kind']!='command' or check.get('report_format'):
        return {**result,'reason':'Builtin and case-report checks retain global execution'}
    if current!=contract['reviewed_revision']:
        return {**result,'reason':'Non-independent inputs/command/environment changed since review; full rerun until reviewed again'}
    return {'mode':'SCOPED','hash':digest({'revision':current,'contract':contract,'identity':identity}),
            'reason':'Reviewed independence; all other inventoried paths remain inputs'}


def reused(h, task, name, current):
    if current['mode']!='SCOPED': return None
    for ref in reversed(task['evidence']):
        try:
            evidence=h.evidence(ref)
            if not h.successful_evidence(task,evidence): continue
            result=next(r for r in evidence['results'] if r['check']==name)
            if result.get('input_binding')!=current or result['result']!='PASS' or result['exit_code']!=0: continue
            value=copy.deepcopy(result)
            value['reused_from']=result.get('reused_from',ref)
            return value
        except (HarnessError,OSError,ValueError,StopIteration): continue
    return None


def valid_reuse(h, task, result):
    ref=result.get('reused_from')
    if not ref: return True
    try:
        original=h.evidence(ref)
        matches=[r for r in original['results'] if r['check']==result['check']]
        return (original['task_id']==task['id'] and original['result']=='PASS'
                and original.get('definition_hash')==h.definition(task)
                and ref==f".harness/evidence/{original['id']}.json"
                and len(matches)==1 and 'reused_from' not in matches[0]
                and matches[0]=={k:v for k,v in result.items() if k!='reused_from'})
    except (HarnessError,OSError,ValueError): return False


def current(h, task, evidence, files=None):
    files = h.fingerprints() if files is None else files
    global_hash=digest({'files':dict(files),'environment':h.environment()})
    try:
        checks=read(safe_path(h.root,'.harness/checks.json'))['checks']
        scoped=[r for r in evidence['results'] if r.get('input_binding',{}).get('mode')=='SCOPED']
        opted=[r for r in evidence['results'] if checks.get(r['check'],{}).get('input_contract')]
        if any(r.get('input_binding')!=binding(h,task,r['check'],checks[r['check']],files) for r in opted): return False
        if evidence['fingerprint']==global_hash: return True
        if not scoped or len(scoped)!=len(evidence['results']): return False
        # Freshness cannot swallow an unauthorized change, even when independent.
        verification.scope_changes(h,task)
        return True
    except (HarnessError,OSError,ValueError,KeyError): return False


def coverage(results):
    modes={r.get('input_binding',{}).get('mode','GLOBAL') for r in results}
    return 'SCOPED' if modes=={'SCOPED'} else 'MIXED' if 'SCOPED' in modes else 'GLOBAL'
