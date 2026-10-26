"""Provision the complete harness toolchain after adoption preflight succeeds."""
from pathlib import Path
from . import assessment, codegraph_tool, graphify_tool, openspec_tool, runtime, tool_updates
from .storage import HarnessError, atomic, now, read, redact


def selected_agents(root):
    observed = assessment.inventory(root)
    names = {x['name'] for x in observed['agent_candidates']}
    root=Path(root)
    if (root/'.codex').is_dir(): names.add('codex')
    # Ignore our generated bridges: those exist for every host after adoption.
    if (root/'CLAUDE.md').exists() or (root/'.claude/settings.json').exists(): names.add('claude')
    if (root/'.github/copilot-instructions.md').exists(): names.add('copilot')
    return ','.join(name for name in ('codex','claude','github-copilot')
                    if ('copilot' if name=='github-copilot' else name) in names) or 'none'


def complete(root, openspec=True, agents='auto'):
    root=Path(root).resolve()
    report={'result':'RUNNING','started_at':now(),'steps':[],'active_step':None}
    path=root/'.harness/install.json'
    if path.exists() and read(path).get('result')=='RUNNING':
        raise HarnessError('Previous installation was interrupted. Inspect processes and partial effects before removing .harness/install.json and retrying.')
    def step(name, operation):
        report['active_step']=name;atomic(path,report)
        value=operation()
        report['steps'].append({'name':name,'result':'PASS','details':value})
        report['active_step']=None;atomic(path,report)
        return value
    try:
        step('runtime',lambda:runtime.prepare(root))
        names=['codegraph','graphify']+(['openspec'] if openspec else [])
        configs=tool_updates.registry()
        for name in names:
            config=configs[name]
            def provision(name=name,config=config):
                current=tool_updates.probe(root,name,config)
                if current==config['version']: return {'version':current,'action':'reused'}
                return {'version':tool_updates.install(root,name,config),'action':'installed_locally'}
            step(name,provision)
        if openspec:
            tools=selected_agents(root) if agents=='auto' else agents
            step('openspec-init',lambda:openspec_tool.initialize(root,tools,False))
        for name,module in [('codegraph-index',codegraph_tool),('graphify-index',graphify_tool)]:
            def index(module=module):
                result=module.ensure(root)
                if result.get('freshness')!='fresh': raise HarnessError('Required index is not fresh.')
                return result
            step(name,index)
        step('assessment',lambda:assessment.assess(root))
        from .core import Harness
        step('validate',lambda:Harness(root).validate())
        report['result']='PASS'
    except (HarnessError,OSError,ValueError) as exc:
        report.update(result='BLOCKED',error=redact(str(exc)))
    report['finished_at']=now();atomic(path,report)
    return report
