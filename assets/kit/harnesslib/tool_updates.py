"""One update path for the external tools owned by harness.

Versions come from adapter contracts. New upstream versions are reported for
compatibility review, never silently substituted for a pinned version.
"""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request
from . import codegraph_tool, graphify_tool, openspec_tool
from .storage import HarnessError, atomic, now, read, redact, safe_path
from .tool_paths import binary

REPORT = '.harness/tool-updates.json'


def registry():
    return {
        'codegraph': {'package':codegraph_tool.PACKAGE, 'version':codegraph_tool.PACKAGE.rsplit('@',1)[1],
                      'manager':'npm','version_args':['version'],
                      'latest_url':'https://registry.npmjs.org/@colbymchenry%2fcodegraph/latest'},
        'graphify': {'package':graphify_tool.PACKAGE, 'version':graphify_tool.PACKAGE.split('==')[1],
                    'manager':'uv','version_args':['--version'],
                    'latest_url':'https://pypi.org/pypi/graphifyy/json'},
        'openspec': {'package':openspec_tool.PACKAGE, 'version':openspec_tool.VERSION,
                    'manager':'npm','version_args':['--version'],
                    'latest_url':'https://registry.npmjs.org/@fission-ai%2fopenspec/latest'},
    }


def execute(root, argv, timeout=180):
    env = openspec_tool.environment(root)
    env.update(UV_CACHE_DIR=str(Path(root)/'.harness/uv-cache'), UV_PYTHON_DOWNLOADS='never')
    try:
        with tempfile.TemporaryFile() as output:
            process=subprocess.Popen(argv,cwd=root,env=env,stdout=output,stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL,start_new_session=True)
            try: code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise HarnessError('Tool command timed out; inspect partial effects before retrying.')
            output.seek(0); summary=redact(output.read(65536).decode(errors='replace'))
        if code: raise HarnessError(f'Tool command exited {code}: {summary[-3000:]}')
        return summary
    except OSError as exc:
        raise HarnessError('Tool command unavailable: '+str(exc)) from exc


def version_tuple(value):
    if not re.fullmatch(r'\d+\.\d+\.\d+',value):
        raise HarnessError('Unsupported version format: '+str(value))
    return tuple(map(int,value.split('.')))


def probe(root, name, config):
    executable=binary(root,name)
    if not executable: return None
    output=execute(root,[executable,*config['version_args']],15).strip()
    match=re.fullmatch(r'(?:'+name+r'\s+)?v?(\d+\.\d+\.\d+)',output)
    if not match: raise HarnessError('Unrecognized '+name+' version: '+output[:200])
    return match.group(1)


def latest(config):
    # Fixed public metadata endpoints only; no project content or credentials sent.
    with urllib.request.urlopen(config['latest_url'],timeout=15) as response:
        data=response.read(1024*1024+1)
    if len(data)>1024*1024: raise HarnessError('Registry response is too large.')
    payload=json.loads(data)
    value=payload['info']['version'] if config['manager']=='uv' else payload['version']
    version_tuple(value)
    return value


def plan(root, names=None, check_latest=False, include_optional=False):
    configs=registry(); names=list(configs) if names is None else names
    if not names or len(names)!=len(set(names)) or set(names)-set(configs):
        raise HarnessError('Select unique tools from codegraph, graphify, openspec.')
    entries=[]
    for name in names:
        config=configs[name]
        entry={'tool':name,'target_version':config['version'],'package':config['package']}
        try:
            current=probe(root,name,config); entry['installed_version']=current
            optional=(name=='openspec' and current is None and not (Path(root)/'openspec/config.yaml').exists())
            if optional and not include_optional: entry['action']='skip_optional'
            elif current is None: entry['action']='install'
            elif version_tuple(current)<version_tuple(config['version']): entry['action']='update'
            elif current==config['version']: entry['action']='current'
            else: entry['action']='blocked_newer_version'
        except HarnessError as exc:
            entry.update(action='blocked',error=str(exc))
        if check_latest:
            try:
                entry['latest_version']=latest(config)
                entry['compatibility_review_required']=entry['latest_version']!=config['version']
            except Exception as exc:
                entry['latest_lookup_error']=redact(str(exc))
        entries.append(entry)
    return {'result':'BLOCKED' if any(e['action'].startswith('blocked') or 'latest_lookup_error' in e for e in entries) else 'PASS',
            'mode':'plan','tools':entries,
            'notice':'Targets are adapter-supported versions. Newer upstream releases require adapter review and tests. Host runtimes, agent CLIs and corporate MCP are not managed.'}


def install(root, name, config):
    target=safe_path(root,'.harness/tools/'+name)
    if config['manager']=='npm':
        npm=shutil.which('npm'); node=shutil.which('node')
        if not npm or not node: raise HarnessError('Node and npm are required.')
        node_version=execute(root,[node,'--version'],15).strip().lstrip('v')
        current=version_tuple(node_version)
        if (name=='codegraph' and not 20<=current[0]<25) or (name=='openspec' and current<(20,19,0)):
            raise HarnessError('Node version does not meet '+name+' requirements.')
        target.mkdir(parents=True,exist_ok=True)
        argv=[npm,'install','--prefix',str(target),'--no-audit','--no-fund',
              '--cache',str(safe_path(root,'.harness/npm-cache'))]
        if name=='openspec': argv.append('--ignore-scripts')
        # CodeGraph may need native dependency install scripts, just as its original installer did.
        execute(root,[*argv,config['package']])
    else:
        uv=shutil.which('uv')
        if not uv: raise HarnessError('uv is required for the managed Graphify environment.')
        if not (target/'pyvenv.cfg').is_file():
            execute(root,[uv,'venv','--python',sys.executable,str(target)])
        execute(root,[uv,'pip','install','--python',str(target/'bin/python'),'--upgrade',config['package']])
    observed=probe(root,name,config)
    if observed!=config['version']:
        raise HarnessError(f'{name} post-install version mismatch: {observed}')
    return observed


def update(root, names=None, apply=False, check_latest=False, include_optional=False):
    root=Path(root).resolve()
    report=plan(root,names,check_latest,include_optional)
    if not apply: return report
    previous=safe_path(root,REPORT)
    if previous.exists() and read(previous).get('active_tool'):
        raise HarnessError('Previous update was interrupted. Inspect its process/files and clear active_tool in .harness/tool-updates.json before retrying.')
    report.update(mode='apply',started_at=now(),active_tool=None,checks=[])
    configs=registry()
    atomic(previous,report)
    for entry in report['tools']:
        if entry['action'] not in ('install','update'):
            entry['result']='BLOCKED' if entry['action'].startswith('blocked') else 'SKIPPED'
            continue
        name=entry['tool']
        report['active_tool']=name;atomic(previous,report)
        try:
            entry['installed_after']=install(root,name,configs[name])
            if name in ('codegraph','graphify'):
                module=codegraph_tool if name=='codegraph' else graphify_tool
                safe_path(root,module.STATE).unlink(missing_ok=True)
                entry['index']=module.ensure(root)
                if entry['index'].get('freshness')!='fresh': raise HarnessError('Index refresh did not become fresh.')
            entry['result']='PASS'
        except (HarnessError,OSError,subprocess.SubprocessError) as exc:
            entry.update(result='FAIL',error=redact(str(exc)))
        report['active_tool']=None;atomic(previous,report)
    for command in ('validate','self-test'):
        try:
            summary=execute(root,[sys.executable,'-B',str(root/'harness'),command],180)
            report['checks'].append({'check':command,'result':'PASS','summary':summary[-2000:]})
        except HarnessError as exc:
            report['checks'].append({'check':command,'result':'FAIL','error':str(exc)})
        atomic(previous,report)
    failures=any(e.get('result') in ('FAIL','BLOCKED') or 'latest_lookup_error' in e for e in report['tools'])
    report['result']='FAIL' if failures or any(c['result']!='PASS' for c in report['checks']) else 'PASS'
    report['finished_at']=now();atomic(previous,report)
    return report
