"""Explicit CLI; mutating commands hold one advisory lock for their lifetime."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import unittest
from .core import Harness
from .report_operation import scope as reporting_scope
from . import compact, assessment, index_context, installation, codegraph_tool, graph, graphify_tool, investigation, openspec_tool, readiness, runner, tool_updates, workflow, reporting
from .skills import catalog
from .storage import HarnessError, lock, redact

def parser():
    p = argparse.ArgumentParser(prog='./harness')
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    sub = p.add_subparsers(dest='command',required=True)
    for name in ['doctor','validate','status','resume','init','self-test','engineering-log']:
        command = sub.add_parser(name)
        if name == 'doctor':
            command.add_argument('--execution-requirements',action='store_true'); command.add_argument('--task')
        if name == 'status':
            command.add_argument('id',nargs='?'); command.add_argument('--format',choices=['json','markdown','terminal'],default='json'); command.add_argument('--retain',action='store_true'); command.add_argument('--retain-dir',type=Path)
    wf = sub.add_parser('workflow').add_subparsers(dest='action',required=True)
    wp = wf.add_parser('propose'); wp.add_argument('--file',required=True)
    wm = wf.add_parser('migrate'); wm.add_argument('--by'); wm.add_argument('--reference'); wm.add_argument('--expected')
    wp = wf.add_parser('accept'); wp.add_argument('id'); wp.add_argument('--by',required=True); wp.add_argument('--reference',required=True); wp.add_argument('--expected',required=True)
    wa = wf.add_parser('assess'); wa.add_argument('id'); wa.add_argument('--facts',required=True)
    ws = wf.add_parser('show'); ws.add_argument('id')
    wc = wf.add_parser('confirm'); wc.add_argument('id'); wc.add_argument('--profile',choices=workflow.PROFILES,required=True); wc.add_argument('--by',required=True); wc.add_argument('--reference',required=True)
    wc.add_argument('--expected')
    wr = wf.add_parser('resolve'); wr.add_argument('id'); wr.add_argument('--review',required=True)
    inv = sub.add_parser('investigation').add_subparsers(dest='action',required=True)
    ir = inv.add_parser('record'); ir.add_argument('id'); ir.add_argument('--file',required=True)
    ic = inv.add_parser('check'); ic.add_argument('id'); ic.add_argument('--current')
    sub.add_parser('next')
    decision = sub.add_parser('approval-package')
    decision.add_argument('id'); decision.add_argument('--format',choices=['json','markdown','terminal'],default='json')
    tools = sub.add_parser('tools').add_subparsers(dest='action',required=True)
    updater = tools.add_parser('update')
    updater.add_argument('--apply',action='store_true')
    updater.add_argument('--check-latest',action='store_true')
    updater.add_argument('--include-optional',action='store_true')
    updater.add_argument('--only',nargs='+',choices=['codegraph','graphify','openspec'])
    ospec = sub.add_parser('openspec').add_subparsers(dest='action',required=True)
    ospec.add_parser('status')
    ospec.add_parser('list')
    ospec.add_parser('new').add_argument('change')
    os_instructions = ospec.add_parser('instructions')
    os_instructions.add_argument('artifact'); os_instructions.add_argument('--change',required=True)
    ospec.add_parser('install')
    os_init = ospec.add_parser('init')
    os_init.add_argument('--tools',default='none')
    os_init.add_argument('--install',action='store_true')
    for action in ('validate','context'):
        ospec.add_parser(action).add_argument('change')
    os_import = ospec.add_parser('import')
    os_import.add_argument('change'); os_import.add_argument('--mapping',required=True)
    ospec.add_parser('refresh').add_argument('feature')

    assess = sub.add_parser('assess')
    assessment_input = assess.add_mutually_exclusive_group()
    assessment_input.add_argument('--agent-command', type=json.loads)
    assessment_input.add_argument('--response')
    run = sub.add_parser('run')
    run.add_argument('--max-steps',type=int,default=20)
    run.add_argument('--max-seconds',type=int,default=600)
    run.add_argument('--new-run',action='store_true')
    run.add_argument('--submit'); run.add_argument('--by',default='current IDE host'); run.add_argument('--reference')
    sub.add_parser('regression').add_argument('id')
    sub.add_parser('skills').add_argument('name', nargs='?')
    sub.add_parser('readiness').add_argument('id', nargs='?')
    onboarding = sub.add_parser('onboarding').add_subparsers(dest='action',required=True)
    onboard_approval = onboarding.add_parser('approve')
    onboard_approval.add_argument('--by',required=True)
    onboard_approval.add_argument('--reference',required=True)
    checkpoint = sub.add_parser('checkpoint')
    checkpoint.add_argument('--if-needed',action='store_true')
    adoption = sub.add_parser('adopt'); adoption.add_argument('destination',type=Path); adoption.add_argument('--apply',action='store_true')
    adoption.add_argument('--agent-command', type=json.loads, help='Explicit assessment adapter argv; {context} is replaced with its input path')
    adoption.add_argument('--openspec', action=argparse.BooleanOptionalAction, default=True, help='Install/init OpenSpec by default; --no-openspec opts out')
    adoption.add_argument('--openspec-tools',default='auto')
    verify = sub.add_parser('verify'); verify.add_argument('id')
    task = sub.add_parser('task').add_subparsers(dest='action',required=True)
    baseline = task.add_parser('baseline').add_subparsers(dest='baseline_action',required=True)
    proposal = baseline.add_parser('propose'); proposal.add_argument('id')
    acceptance = baseline.add_parser('accept'); acceptance.add_argument('id'); acceptance.add_argument('--manifest',required=True); acceptance.add_argument('--reference',required=True); acceptance.add_argument('--by',required=True)
    replan = task.add_parser('replan'); replan.add_argument('id'); replan.add_argument('--reference',required=True)
    start = task.add_parser('start'); start.add_argument('id')
    trans = task.add_parser('transition'); trans.add_argument('id'); trans.add_argument('status'); trans.add_argument('--reason',required=True)
    approve = task.add_parser('approve'); approve.add_argument('id'); approve.add_argument('--kind',required=True); approve.add_argument('--by',required=True); approve.add_argument('--reference',required=True)
    review = sub.add_parser('review')
    review.add_argument('id'); review.add_argument('--by',required=True); review.add_argument('--reference',required=True)
    g = sub.add_parser('graph').add_subparsers(dest='action',required=True)
    g.add_parser('status')
    g.add_parser('update').add_argument('--if-needed',action='store_true')
    q = g.add_parser('query'); q.add_argument('query'); q.add_argument('--limit',type=int,default=30)
    gf = sub.add_parser('graphify').add_subparsers(dest='action',required=True)
    gf.add_parser('status')
    gf.add_parser('ensure')
    gfq = gf.add_parser('query'); gfq.add_argument('question'); gfq.add_argument('--budget',type=int,default=800)
    cg = sub.add_parser('codegraph').add_subparsers(dest='action',required=True)
    cg.add_parser('status')
    cg.add_parser('ensure')
    cgq = cg.add_parser('query'); cgq.add_argument('term'); cgq.add_argument('--limit',type=int,default=10)
    indexes = sub.add_parser('indexes').add_subparsers(dest='action',required=True)
    indexes.add_parser('status')
    indexes.add_parser('ensure')
    note = sub.add_parser('note'); note.add_argument('kind',choices=['decision','blocker','resolve','observation','correction']); note.add_argument('message'); note.add_argument('--next-action')
    recovery = sub.add_parser('recovery').add_subparsers(dest='action',required=True)
    recovery.add_parser('acknowledge').add_argument('--note',required=True)
    return p

def run(args,h):
    cmd = args.command
    if cmd == 'workflow':
        if args.action == 'propose':
            from .storage import read, safe_path
            return compact.proposal(h,read(safe_path(h.root,args.file)))
        if args.action == 'migrate': return compact.migration(h,args.by,args.reference,args.expected)
        if args.action == 'accept': return compact.accept(h,args.id,args.by,args.reference,args.expected)
        if args.action == 'confirm' and compact.is_compact(h.task(args.id)[0]): return compact.confirm(h,args.id,args.profile,args.by,args.reference,args.expected)
        if args.action == 'assess': return workflow.assess(h,args.id,args.facts)
        if args.action == 'show' and compact.is_compact(h.task(args.id)[0]): return compact.plan_card(h,args.id)
        if args.action == 'show': return h.task(args.id)[1].get('workflow',{'selected':'STRICT','notice':'Legacy task; existing gates apply'})
        if args.action == 'resolve': return workflow.resolve(h,args.id,args.review)
        return workflow.confirm(h,args.id,args.profile,args.by,args.reference)
    if cmd == 'investigation':
        if args.action == 'record': return investigation.record(h,args.id,args.file)
        return investigation.check(h,args.id,args.current)
    if cmd == 'tools': return tool_updates.update(h.root,args.only,args.apply,args.check_latest,args.include_optional)
    if cmd == 'openspec':
        if args.action == 'status': return openspec_tool.status(h.root)
        if args.action == 'list': return openspec_tool.list_changes(h.root)
        if args.action == 'new': return openspec_tool.new_change(h.root,args.change)
        if args.action == 'instructions': return openspec_tool.instructions(h.root,args.change,args.artifact)
        if args.action == 'install': return openspec_tool.install(h.root)
        if args.action == 'init': return openspec_tool.initialize(h.root,args.tools,args.install)
        if args.action == 'validate': return openspec_tool.validate(h.root,args.change)
        if args.action == 'context': return openspec_tool.context(h.root,args.change)
        if args.action == 'import': return openspec_tool.import_change(h,args.change,args.mapping)
        if args.action == 'refresh': return openspec_tool.refresh(h,args.feature)
    if cmd == 'assess': return assessment.assess(h.root, args.agent_command, args.response)
    if cmd == 'next': return runner.next_action(h)
    if cmd == 'approval-package': return reporting.approval_package(h,args.id,args.format)
    if cmd == 'run':
        if args.submit: runner.submit(h,args.submit,args.by,args.reference)
        return runner.run(h,args.max_steps,args.max_seconds,args.new_run)
    if cmd == 'regression': return h.verify(args.id,regression=True)
    if cmd == 'skills': return catalog(h.root, args.name)
    if cmd == 'readiness': return readiness.report(h, args.id)
    if cmd == 'onboarding': return h.approve_onboarding(args.by,args.reference)
    if cmd == 'init': return h.init()
    if cmd == 'validate': return h.validate()
    if cmd == 'doctor':
        if args.execution_requirements:
            from .index_context import policy
            features = [h.task(args.task)[0]] if args.task else list(h.features().values())
            providers = policy(h.root)['providers']
            navigation = bool(providers)
            product = h.root/'.harness/product.json'
            configured = json.loads(product.read_text(encoding='utf-8')) if product.exists() else {}
            openspec = configured.get('workflow') == 'openspec' or any(f.get('spec_source') for f in features)
            checks_path = h.root/'.harness/checks.json'
            checks = json.loads(checks_path.read_text(encoding='utf-8'))['checks'] if checks_path.exists() else {}
            tasks = [h.task(args.task)[1]] if args.task else [t for f in features for t in f['tasks'] if t['status'] not in {'DONE','BLOCKED'}]
            names = sorted({n for t in tasks for dependency in h.check_closure(t) for n in dependency['required_checks']})
            executables = []
            for name in names:
                check = checks.get(name)
                if check is None: raise HarnessError('Required check is missing: '+name)
                if check['kind'] == 'command' and check['argv']:
                    executable = check['argv'][0].replace('{python}',sys.executable)
                    executables.append({'check':name,'executable':executable})
            return {'result':'PASS','navigation_cli_required':navigation,'navigation_providers':providers,'openspec_required':openspec,'executables':executables,
                    'experience':workflow.policy(h).get('experience',{'version':1,'mode':'legacy'}),
                    'experience_next_action':'Use workflow propose for eligible FAST tasks' if compact.enabled(h) else 'Use workflow migrate to preview explicit compact opt-in; legacy rules remain active',
                    'reason':'Required navigation providers: '+', '.join(providers) if navigation else 'Source navigation; no graph CLI required.'}
        return {'result':'PASS','python':sys.version.split()[0],'runtime':('Python standard library; native Windows locking/process trees' if sys.platform == 'win32' else 'Python standard library; POSIX flock/process groups'),
                'git':h.git(),'validation':h.validate(),'skills':len(list((h.root/'.agents/skills').glob('*/SKILL.md'))),
                'permissions':'Runtime-managed; no hooks, merge protection, credentials or permission overrides installed.'}
    if cmd == 'status':
        if args.id or args.format != 'json' or args.retain or args.retain_dir:
            return reporting.report(h,args.id,args.format,args.retain or bool(args.retain_dir),args.retain_dir)
        return h.status()
    if cmd == 'resume':
        h.reconcile(); h.checkpoint(); return h.status()
    if cmd == 'checkpoint': return h.checkpoint()
    if cmd == 'verify': return h.verify(args.id)
    if cmd == 'engineering-log': return h.engineering_log()
    if cmd == 'note': return h.note(args.kind,args.message,args.next_action)
    if cmd == 'recovery': return h.recovery_acknowledge(args.note)
    if cmd == 'review': return h.approve(args.id,'review',args.by,args.reference)
    if cmd == 'task':
        if args.action == 'baseline':
            from . import reconciliation
            if args.baseline_action == 'propose': return reconciliation.propose(h,h.task(args.id)[1])
            return reconciliation.accept(h,args.id,args.manifest,args.reference,args.by)
        if args.action == 'replan': return h.replan(args.id,args.reference)
        if args.action == 'start': return h.transition(args.id,'IN_PROGRESS','Started approved task')
        if args.action == 'transition': return h.transition(args.id,args.status,args.reason)
        return h.approve(args.id,args.kind,args.by,args.reference)
    if cmd == 'graph':
        if args.action == 'status': return graph.status(h.root)
        if args.action == 'update': return graph.update(h.root)
        if not 1 <= args.limit <= 100: raise HarnessError('Query limit must be 1..100')
        return graph.query(h.root,args.query,args.limit)
    if cmd == 'graphify':
        if args.action == 'status': return graphify_tool.status(h.root)
        if args.action == 'ensure': return graphify_tool.ensure(h.root)
        return graphify_tool.query(h.root,args.question,args.budget)
    if cmd == 'codegraph':
        if args.action == 'status': return codegraph_tool.status(h.root)
        if args.action == 'ensure': return codegraph_tool.ensure(h.root)
        return codegraph_tool.query(h.root,args.term,args.limit)
    if cmd == 'indexes':
        if args.action == 'status': return {'codegraph':codegraph_tool.status(h.root),'graphify':graphify_tool.status(h.root)}
        return index_context.ensure(h.root)
    raise HarnessError('Unsupported command')

def main():
    args = parser().parse_args()
    if args.command == 'self-test':
        try:
            suite = unittest.defaultTestLoader.discover(str(args.root/'tests'))
        except (ImportError, OSError) as exc:
            print(f'Self-test discovery failed: {exc}', file=sys.stderr)
            return 1
        if not suite.countTestCases():
            print('Self-test requires at least one discovered test.', file=sys.stderr)
            return 1
        from .test_progress import run as run_self_tests
        return run_self_tests(suite, args.root)
    if args.command == 'adopt':
        from .adopt import adopt
        try:
            if args.apply:
                preview = adopt(args.root,args.destination,True)
                if preview['conflicts']:
                    print(json.dumps(preview,indent=2))
                    return 1
            result = adopt(args.root,args.destination,not args.apply)
            if args.apply and not result['conflicts']:
                result['installation'] = installation.complete(args.destination,args.openspec,args.openspec_tools)
                if result['installation']['result'] != 'PASS':
                    result['result'] = 'BLOCKED'
                if args.agent_command is not None:
                    result['assessment'] = assessment.assess(args.destination, args.agent_command)
            print(json.dumps(result,indent=2))
            return 1 if result['result'] == 'BLOCKED' or result['conflicts'] else 0
        except (HarnessError,OSError,ValueError) as exc:
            print(str(exc),file=sys.stderr); return 1
    h = Harness(args.root)
    try:
        readonly = (args.command=='workflow' and args.action=='migrate' and not args.by) or (args.command=='tools' and not args.apply) or (args.command=='openspec' and args.action in {'status','context','validate','list','instructions'}) or (args.command=='investigation' and args.action=='check') or args.command in {'status','validate','doctor','skills','readiness','next','approval-package'} or args.command=='graph' and args.action=='status' or args.command=='graphify' and args.action in {'status','query'} or args.command=='codegraph' and args.action in {'status','query'} or args.command=='indexes' and args.action=='status'
        if args.command == 'status' and (args.retain or args.retain_dir): readonly = False
        if readonly: result = run(args,h)
        else:
            with lock(h.root), reporting_scope(h): result = run(args,h)
        if args.command in {'status','approval-package'} and args.format in {'terminal','markdown'} and result.get('result') != 'BLOCKED':
            print(redact(result['text']),end='')
        else:
            print(json.dumps(redact(result),indent=2,sort_keys=True))
        return 1 if result.get('result') in {'FAIL','BLOCKED','NOT_RUN'} else 0
    except (HarnessError,OSError,ValueError,KeyError) as exc:
        print(json.dumps({'result':'FAIL','error':redact(str(exc))}),file=sys.stderr)
        return 1
