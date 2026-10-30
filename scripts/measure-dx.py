"""Deterministic fixture measurements; never live-agent or token telemetry.

Optional baseline runtime must have been checked against the captured starting
hashes. Only that Python package is loaded; current isolated fixture assets are
shared between arms. No source checkout or index is changed.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
import time
p=argparse.ArgumentParser(); p.add_argument('--baseline-runtime'); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[args.baseline_runtime or str(root),str(root/'tests')]
from harnesslib.core import Harness
from harnesslib import workflow,runner,index_context
from harnesslib.storage import atomic,read,HarnessError
from harnesslib.report_operation import scope as reporting_scope
from unittest.mock import patch
baseline=bool(args.baseline_runtime)
if baseline:
    from test_onboarding import OnboardingTests as Fixture
else:
    from test_compact import CompactTests as Fixture
    from harnesslib import compact
counts=Counter(); timing={'application_check_seconds':0.0}
for name in ('save','reconcile','checkpoint','transition','approve','approve_onboarding','verify'):
    original=getattr(Harness,name)
    def wrap(self,*a,_name=name,_original=original,**kw):
        counts[_name]+=1
        return _original(self,*a,**kw)
    setattr(Harness,name,wrap)
original_check=Harness.run_check
def check(self,name,*a,**kw):
    counts['check_executions']+=1; start=time.perf_counter()
    try: return original_check(self,name,*a,**kw)
    finally: timing['application_check_seconds']+=time.perf_counter()-start
Harness.run_check=check
for name,provider in index_context.PROVIDERS.items():
    original=provider.ensure
    def counted(*a,_name=name,_original=original,**kw):
        counts['provider_invocations']+=1
        return _original(*a,**kw)
    provider.ensure=counted

def prepare_baseline(x):
    x.prepare()
    (x.root/'calculator.py').write_text('def add(a,b):\n    return a-b\n')

def facts(x):
    atomic(x.root/'.harness/facts.json',dict(critical_risk=False,critical_unknowns=[],unknowns=[],public_api=False,architecture_change=False,components=1,inspected=['calculator.py']))
    return '.harness/facts.json'
def decision(x):
    return workflow.confirm(x.h,'CALC-001','FAST','simulated fixture developer','docs/approval.md')
def setup_plan(x):
    if baseline:
        prepare_baseline(x); x.approve(); workflow.assess(x.h,'CALC-001',facts(x)); decision(x)
    else: x.confirm()
def initial(x,existing):
    if baseline:
        if not existing: prepare_baseline(x); x.approve()
        workflow.assess(x.h,'CALC-001',facts(x)); decision(x); x.h.transition('CALC-001','IN_PROGRESS','fixture')
    else:
        if existing: x.request.pop('context'); x.request.pop('checks')
        card=x.propose(); x.confirm(card); return x.advance()
def complete(x,role):
    (x.root/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
    if baseline:
        x.h.transition('CALC-001','IMPLEMENTED','fixture'); x.h.verify('CALC-001'); x.h.transition('CALC-001','VERIFIED','fixture')
        ref='specs/calculator/reviews/fixture.md'
    else:
        with reporting_scope(x.h):
            runner.submit(x.h,role['host_role']['request_id'],'simulated host'); role=x.advance()
        assert role['action']=='review',role
        ref=role['host_role']['review_path']
    t=x.h.task('CALC-001')[1]; target=x.root/ref; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('```harness-review\n'+json.dumps({'task_id':t['id'],'reviewer':'simulated same-host separate pass','evidence':t['evidence'][-1],'verdict':'PASS','summary':'Fixture review inspected arithmetic change and positive and signed checks.','findings':[]})+'\n```\n')
    if baseline: x.h.approve('CALC-001','review','fixture',ref)
    else:
        with reporting_scope(x.h):
            runner.submit(x.h,role['host_role']['request_id'],'simulated host',ref); role=x.advance()
        assert role['action']=='approval',role
    (x.root/'.harness/final.txt').write_text('SIMULATED FIXTURE INPUT: separate acceptance of the current result after checks and review.')
    if baseline:
        x.h.approve('CALC-001','developer','fixture','.harness/final.txt'); x.h.transition('CALC-001','DONE','fixture')
    else: compact.accept(x.h,'CALC-001','fixture','.harness/final.txt',role['approval_package']['acceptance_binding'])
    assert x.h.task('CALC-001')[1]['status']=='DONE'

results={}
for scenario in ['new','existing','resume','material','strict']:
    rows=[]
    for sample in range(3):
        x=Fixture(); x.setUp(); patch.stopall()
        if scenario=='existing':
            if baseline: prepare_baseline(x); x.approve()
            else:
                # Reuse a genuinely approved formal context, as an existing project would.
                from test_onboarding import OnboardingTests
                OnboardingTests.prepare(x); x.h.approve_onboarding('fixture developer','docs/approval.md')
                import shutil
                shutil.rmtree(x.root/'specs/calculator')
                x.seed()
                # The existing baseline check name is identical and remains approved.
        elif scenario in {'resume','material'}:
            setup_plan(x)
            if baseline: x.h.transition('CALC-001','IN_PROGRESS','fixture')
            else: x.advance()
        elif scenario=='strict':
            if baseline: prepare_baseline(x); x.approve()
            policy=read(x.root/'.harness/workflow-policy.json') if (x.root/'.harness/workflow-policy.json').exists() else {}
            policy['minimum']='STRICT'; atomic(x.root/'.harness/workflow-policy.json',policy)
        counts.clear(); timing['application_check_seconds']=0; start=time.perf_counter(); result='PASS'
        try:
            if scenario in {'new','existing'}:
                complete(x,initial(x,scenario=='existing'))
                decisions=3 if baseline and scenario=='new' else 2
                calls=(10 if scenario=='new' else 9) if baseline else 6
                artifacts=(14 if scenario=='new' else 7) if baseline else 4
            elif scenario=='resume':
                if baseline: x.h.reconcile(); x.h.status(); action=runner.next_action(x.h)
                else: action=x.advance()
                assert action['action']=='implement',action
                decisions=0; calls=3 if baseline else 1; artifacts=0
            elif scenario=='material':
                if baseline:
                    x.h.transition('CALC-001','REWORK','fixture material expansion')
                    f,t=x.h.task('CALC-001'); t['scope'].append('extra.py'); atomic(x.root/'specs/calculator/tasks.json',f)
                    workflow.assess(x.h,'CALC-001',facts(x)); decision(x); x.h.replan('CALC-001','docs/approval.md'); decision(x)
                    x.h.transition('CALC-001','IN_PROGRESS','fixture renewed scope')
                else:
                    x.request.pop('context'); x.request['task']['scope'].append('extra.py')
                    card=x.propose(); x.confirm(card); assert x.advance()['action']=='implement'
                decisions=1; calls=6 if baseline else 3; artifacts=2 if baseline else 2
            else:
                try:
                    if baseline: workflow.assess(x.h,'CALC-001',facts(x)); decision(x)
                    else: x.propose()
                except HarnessError: result='BLOCKED_AS_REQUIRED'
                else: raise AssertionError('STRICT shortcut accepted')
                decisions=0; calls=2 if baseline else 1; artifacts=1
            elapsed=time.perf_counter()-start
            rows.append({'result':result,'developer_decisions':decisions,'developer_lifecycle_commands':0,'developer_json_edits':0,
                         'host_authored_artifacts':artifacts,'top_level_administrative_operations':calls,
                         'actual_internal_calls':dict(counts),'application_check_seconds':timing['application_check_seconds'],
                         'framework_seconds_excluding_check':elapsed-timing['application_check_seconds'],'total_seconds':elapsed})
        finally: x.doCleanups()
    results[scenario]={'samples':rows,'median_framework_seconds':statistics.median(r['framework_seconds_excluding_check'] for r in rows)}
args.output.write_text(json.dumps({'arm':'baseline' if baseline else 'after','conditions':'same host, interpreter, current fixture assets; baseline exact starting Python modules; no live model; local warm filesystem; three samples','results':results},indent=2)+'\n')
print(json.dumps({k:v['median_framework_seconds'] for k,v in results.items()},indent=2))
