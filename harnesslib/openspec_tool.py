"""Optional, pinned OpenSpec adapter. Source documents stay in OpenSpec.

Harness owns execution metadata, approvals and evidence; OpenSpec structural
validation is an additional required check, never application test evidence.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .storage import HarnessError, atomic, digest, read, redact, safe_path

VERSION = '1.14.3'
PACKAGE = '@fission-ai/openspec@' + VERSION
LOCAL = '.harness/tools/openspec/node_modules/.bin/openspec'
TOOLS = {'none', 'codex', 'claude', 'github-copilot'}


def identifier(value):
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value):
        raise HarnessError('OpenSpec IDs must use lowercase letters, digits and hyphens.')
    return value


def environment(root):
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'SYSTEMROOT', 'HARNESS_RUNTIME_DIR') if k in os.environ}
    env.update(OPENSPEC_TELEMETRY='0', DO_NOT_TRACK='1', OPENSPEC_NO_UPDATE_CHECK='1',
               XDG_CONFIG_HOME=str(Path(root) / '.harness/openspec-config'))
    return env


def binary(root):
    # npm's bin entry is a symlink within the isolated install; do not use safe_path on it.
    local = Path(root) / LOCAL
    if local.is_file():
        resolved = local.resolve()
        if not resolved.is_relative_to((Path(root) / '.harness/tools/openspec').resolve()):
            raise HarnessError('OpenSpec executable escapes its local installation.')
        return str(local)
    found = shutil.which('openspec')
    if not found:
        raise HarnessError('OpenSpec is not installed. Run ./harness openspec install.')
    return found


def invoke(root, args, cwd=None, timeout=60):
    executable = binary(root)
    try:
        result = subprocess.run([executable, *args], cwd=cwd or root, env=environment(root),
                                capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f'OpenSpec execution unavailable: {exc}') from exc
    return {'result':'PASS' if result.returncode == 0 else 'FAIL', 'exit_code':result.returncode,
            'command':['openspec', *args], 'summary':redact((result.stdout + result.stderr)[-65536:])}


def status(root):
    try:
        result = invoke(root, ['--version'])
        version = result['summary'].strip()
        return {'result':'PASS' if result['exit_code'] == 0 and version == VERSION else 'BLOCKED',
                'installed':True, 'version':version, 'supported_version':VERSION,
                'initialized':(Path(root)/'openspec/config.yaml').is_file()}
    except HarnessError as exc:
        return {'result':'BLOCKED', 'installed':False, 'supported_version':VERSION, 'error':str(exc)}


def require(root):
    result = status(root)
    if result['result'] != 'PASS':
        raise HarnessError(f'OpenSpec {VERSION} required: {result}')


def install(root):
    target = safe_path(root, '.harness/tools/openspec')
    npm = shutil.which('npm')
    if not npm:
        raise HarnessError('npm and Node >=20.19 are required to install OpenSpec.')
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([npm, 'install', '--prefix', str(target), '--ignore-scripts', '--no-audit',
                             '--no-fund', '--cache', str(safe_path(root,'.harness/npm-cache')), PACKAGE],
                            cwd=root, env=environment(root), capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise HarnessError('OpenSpec installation failed: ' + redact(result.stderr[-3000:]))
    require(root)
    return status(root)


def ignores(root, paths):
    """Ignore only newly owned paths; preserve existing corporate OpenSpec files."""
    from .adopt import git_context, ignore_pattern
    root = Path(root).resolve()
    context = git_context(root)
    prefix = root.relative_to(context[0]).as_posix() if context else '.'
    prefix = '' if prefix == '.' else prefix + '/'
    targets = {safe_path(root,'.gitignore'):[ignore_pattern(p) for p in paths]}
    if context:
        targets[context[1]] = [ignore_pattern(prefix + p) for p in paths]
    for path in targets:
        if any(p.is_symlink() for p in [path,*path.parents]):
            raise HarnessError('Symlink ignore file refused.')
    for path, rules in targets.items():
        previous = path.read_text() if path.exists() else ''
        missing = [r for r in rules if r not in previous.splitlines()]
        if missing:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('a') as stream:
                stream.write(('\n' if previous and not previous.endswith('\n') else '') + '\n'.join(missing)+'\n')
    if context and paths:
        probes=[prefix+p+('harness-ignore-probe' if p.endswith('/') else '') for p in paths]
        result=subprocess.run(['git','-C',str(context[0]),'check-ignore','--no-index','-z','-v',
                               '--non-matching','--stdin'],input='\0'.join(probes)+'\0',capture_output=True,text=True)
        fields=result.stdout.split('\0')[:-1]
        if result.returncode not in (0,1) or len(fields)!=4*len(probes) or any(
                not fields[i+2] or fields[i+2].startswith('!') for i in range(0,len(fields),4)):
            raise HarnessError('Project rules expose generated OpenSpec files; no files copied.')


def initialize(root, tools='none', install_missing=False):
    root = Path(root).resolve()
    selected = tools.split(',')
    if not selected or set(selected)-TOOLS or ('none' in selected and len(selected)>1):
        raise HarnessError('Supported tool selections: none, codex, claude, github-copilot.')
    if install_missing and status(root)['result'] != 'PASS':
        install(root)
    require(root)
    # Generate into staging first: never overwrite corporate instructions or skill files.
    with tempfile.TemporaryDirectory(prefix='harness-openspec-init-') as directory:
        stage=Path(directory)
        result=invoke(root,['init','--tools',tools],cwd=stage)
        if result['result']!='PASS':
            raise HarnessError('OpenSpec init failed: '+result['summary'])
        additions=[]; conflicts=[]
        for path in sorted(stage.rglob('*')):
            if path.is_symlink(): raise HarnessError('OpenSpec generated an unexpected symlink.')
            if not path.is_file(): continue
            rel=path.relative_to(stage).as_posix()
            if rel != '.agents/skills/.openspec-target' and not rel.startswith(('openspec/','.agents/skills/openspec-', '.claude/skills/openspec-',
                                   '.claude/commands/', '.github/skills/openspec-', '.github/prompts/')):
                raise HarnessError('Unexpected OpenSpec generated path: '+rel)
            target=safe_path(root,rel)
            if target.exists():
                if rel=='openspec/config.yaml': continue
                if not target.is_file() or target.read_bytes()!=path.read_bytes(): conflicts.append(rel)
            else: additions.append(rel)
        if conflicts: raise HarnessError('OpenSpec files conflict; existing files preserved: '+', '.join(conflicts))
        paths=list(additions)
        if not (root/'openspec').exists(): paths.append('openspec/')
        ignores(root,paths)
        for rel in additions:
            target=safe_path(root,rel); target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output: output.write((stage/rel).read_bytes())
    return {'result':'PASS','files':additions,'version':VERSION,
            'next_action':'Create an OpenSpec change, then import its execution mapping into harness.'}


def source(root, change):
    identifier(change)
    base=safe_path(root,'openspec/changes/'+change)
    if not base.is_dir(): raise HarnessError('Active OpenSpec change missing: '+change)
    paths=[p for p in base.rglob('*') if p.is_file() or p.is_symlink()]
    main=safe_path(root,'openspec/specs')
    if main.exists(): paths += [p for p in main.rglob('*') if p.is_file() or p.is_symlink()]
    config=safe_path(root,'openspec/config.yaml')
    if config.exists(): paths.append(config)
    result={}
    for p in sorted(paths):
        rel=p.relative_to(root).as_posix(); p=safe_path(root,rel)
        if p.stat().st_size>1024*1024: raise HarnessError('Oversized OpenSpec input: '+rel)
        text=p.read_text()
        if rel == f'openspec/changes/{change}/tasks.md':
            # Progress markers belong to OpenSpec UI, not requirement approval or proof.
            text=re.sub(r'(?m)^([ \t]*[-*] +)\[[ xX]\](?= )',r'\1[ ]',text)
        result[rel]=text
    if not any('/specs/' in p and p.endswith('.md') for p in result if p.startswith('openspec/changes/')):
        raise HarnessError('OpenSpec change needs specification deltas.')
    return result


def feature_source(root, feature):
    config=feature.get('spec_source')
    return source(Path(root).resolve(),config['change']) if config else {}


def context(root, change):
    inputs=source(Path(root).resolve(),change)
    return {'result':'PASS','provider':'openspec','change':change,
            'fingerprint':digest(inputs),'paths':list(inputs),
            'instructions':'Read these OpenSpec sources as the feature requirements. Harness owns task execution, approvals and evidence. OpenSpec checkboxes do not prove completion.'}


def validate(root, change):
    source(Path(root).resolve(),change)
    require(root)
    return invoke(root,['validate',identifier(change),'--type','change','--strict','--json','--no-interactive'])


def ready(root, feature):
    config=feature.get('spec_source')
    if not config: return
    if digest(feature_source(root,feature)) != config['fingerprint']:
        raise HarnessError('OpenSpec sources changed; refresh the feature binding and obtain approval again.')
    check='openspec-'+config['change']
    if any(check not in t['required_checks'] for t in feature['tasks']):
        raise HarnessError('Every OpenSpec task must require its structural validation check.')
    configured=read(safe_path(root,'.harness/checks.json'))['checks'].get(check)
    expected=['{python}','harness','openspec','validate',config['change']]
    if not configured or configured['kind']!='command' or configured['argv']!=expected or not configured['approved']:
        raise HarnessError('OpenSpec structural validation check is absent or changed.')


def import_change(h, change, mapping_file):
    """Explicit task mapping supplies scope/checks; imported documents remain DRAFT."""
    identifier(change)
    result=validate(h.root,change)
    if result['result']!='PASS': raise HarnessError('OpenSpec validation failed: '+result['summary'])
    feature=read(safe_path(h.root,mapping_file)); h.schema('tasks',feature)
    if feature['kind']!='application': raise HarnessError('OpenSpec imports are application features.')
    feature_id=identifier(feature['feature_id'])
    dest=safe_path(h.root,'specs/'+feature_id)
    if dest.exists(): raise HarnessError('Feature already exists; import never replaces task history.')
    existing={t['id'] for f in h.features().values() for t in f['tasks']}
    checks=read(safe_path(h.root,'.harness/checks.json'))
    name='openspec-'+change
    definition={'kind':'command','argv':['{python}','harness','openspec','validate',change],
                'timeout_seconds':90,'approved':True,'approval_reference':'Explicit OpenSpec feature import command',
                'purpose':'Validate OpenSpec structure; application behavior requires separate checks.'}
    if name in checks['checks'] and checks['checks'][name]!=definition:
        raise HarnessError('Existing check name conflicts: '+name)
    from . import verification
    inputs=source(h.root,change)
    requirement_text='\n'.join(inputs.values())
    for task in feature['tasks']:
        if task['id'] in existing or task['status']!='TODO' or any(task[k] for k in ('history','evidence','approvals')) or 'execution' in task:
            raise HarnessError('Import requires unique new TODO tasks without execution records.')
        existing.add(task['id'])
        verification.validate_scope(h.root,task['scope']); verification.acceptance(task)
        if any(not re.search(r'(?<![\w-])'+re.escape(req)+r'(?![\w-])',requirement_text) for req in task['requirements']):
            raise HarnessError('Task requirements must reference the OpenSpec source text.')
        if not task['required_checks'] or any(c not in checks['checks'] for c in task['required_checks']):
            raise HarnessError('Configure the application checks before importing the mapping.')
        if name not in task['required_checks']: task['required_checks'].append(name)
    feature['spec_source']={'provider':'openspec','change':change,'fingerprint':digest(inputs)}
    h.schema('tasks',feature)
    ignores(h.root,['specs/'+feature_id+'/'])
    dest.mkdir(parents=True)
    for filename in ('spec.md','plan.md'):
        (dest/filename).write_text(wrapper(feature))
    (dest/'verification.md').write_text('Verification has not run.\n')
    checks['checks'][name]=definition
    atomic(h.root/'.harness/checks.json',checks)
    atomic(dest/'tasks.json',feature)
    return {'result':'PASS','feature':feature_id,'source':context(h.root,change),
            'next_action':'Review the execution mapping and approve the DRAFT wrappers and project readiness. Import is not implementation approval.'}


def wrapper(feature):
    return ('Status: DRAFT\nRevision: 1\nApproval: TBD\n'
            f"Tech-Spec-Revision: {feature['revisions']['tech_spec']}\nArchitecture-Revision: {feature['revisions']['architecture']}\n\n"
            f"Authoritative feature source: openspec/changes/{feature['spec_source']['change']}/\n"
            'This file records harness approval only. Read the OpenSpec sources; do not duplicate requirements here.\n'
            'Execution scope, checks and acceptance mapping are in tasks.json.\n')


def refresh(h, feature_id):
    feature=h.features().get(feature_id)
    if not feature or 'spec_source' not in feature: raise HarnessError('Unknown OpenSpec feature.')
    if any(t['status'] not in ('TODO','REWORK','BLOCKED') for t in feature['tasks']):
        raise HarnessError('Move affected tasks to REWORK/BLOCKED before refreshing; completed history is not replaced.')
    change=feature['spec_source']['change']
    result=validate(h.root,change)
    if result['result']!='PASS': raise HarnessError('OpenSpec validation failed: '+result['summary'])
    feature['spec_source']['fingerprint']=digest(feature_source(h.root,feature))
    for task in feature['tasks']: task['approvals']={}
    for filename in ('spec.md','plan.md'):
        safe_path(h.root,f'specs/{feature_id}/{filename}').write_text(wrapper(feature))
    atomic(h.root/f'specs/{feature_id}/tasks.json',feature)
    return {'result':'PASS','next_action':'Wrappers are DRAFT. Review changed requirements and mapping, obtain approval, and replan unfinished tasks before restarting.'}


def new_change(root, change):
    identifier(change); require(root)
    path=safe_path(root,'openspec/changes/'+change)
    if path.exists(): raise HarnessError('OpenSpec change already exists.')
    ignores(root,['openspec/changes/'+change+'/'])
    return invoke(root,['new','change',change])


def instructions(root, change, artifact):
    identifier(change); identifier(artifact); require(root)
    safe_path(root,'openspec/changes/'+change)
    return invoke(root,['instructions',artifact,'--change',change,'--json'])


def list_changes(root):
    require(root)
    return invoke(root,['list','--json'])
