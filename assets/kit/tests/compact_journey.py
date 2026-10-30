"""Deterministic current-host simulation through the actual installed CLI.

Answers below are fixture input, never a real maintainer/developer approval.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_compact import CompactTests
from harnesslib.storage import atomic
from harnesslib.core import Harness


def journey(root, prefix):
    fixture=CompactTests(); fixture.root=root; fixture.h=Harness(root); fixture.seed()
    (root/'unrelated.txt').write_text('Pre-existing developer work\n')
    subprocess.run(['git','init','-q',str(root)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(root),'add','unrelated.txt'],check=True,capture_output=True)
    index=root/'.git/index'; before=hashlib.sha256(index.read_bytes()).hexdigest()
    (root/'unrelated.txt').write_text('Pre-existing unstaged developer work\n')
    atomic(root/'.harness/request.json',fixture.request)
    calls=[]
    def call(*args):
        start=time.monotonic(); result=subprocess.run([*prefix,*args],cwd=root,capture_output=True,text=True)
        if result.returncode: raise AssertionError(f'{args}: {result.stdout}\n{result.stderr}')
        parsed=json.loads(result.stdout); data=parsed.get('data',parsed)
        calls.append({'argv':args,'seconds':time.monotonic()-start,'result':data.get('result'),'action':data.get('action')})
        return data
    start=time.monotonic()
    plan=call('workflow','propose','--file','.harness/request.json')
    assert plan['recommended']=='FAST' and not plan['blockers'],plan
    (root/'.harness/initial.txt').write_text('SIMULATED FIXTURE INPUT: developer approves displayed compact context, exact commands, plan and FAST profile.\n')
    call('workflow','confirm','CALC-001','--profile','FAST','--by','simulated fixture developer','--reference','.harness/initial.txt','--expected',plan['proposal_binding'])
    action=call('run'); assert action['action']=='implement',action
    (root/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
    action=call('run','--submit',action['host_role']['request_id']); assert action['action']=='review',action
    task=json.loads((root/'specs/calculator/tasks.json').read_text())['tasks'][0]
    ref=action['host_role']['review_path']; path=root/ref; path.parent.mkdir(parents=True,exist_ok=True)
    review={'task_id':task['id'],'reviewer':'simulated current-host separate review pass','evidence':task['evidence'][-1],'verdict':'PASS',
            'summary':'Fixture host inspected the arithmetic diff and executed positive and signed assertions; no findings.','findings':[]}
    path.write_text('```harness-review\n'+json.dumps(review)+'\n```\n')
    action=call('run','--submit',action['host_role']['request_id'],'--reference',ref,'--by','simulated current host')
    assert action['action']=='approval',action
    card=action['approval_package']; assert card['state'].endswith('not yet DONE')
    (root/'.harness/final.txt').write_text('SIMULATED FIXTURE INPUT: separate final acceptance after viewing current result, check-only limits and separate review.\n')
    call('workflow','accept','CALC-001','--by','simulated fixture developer','--reference','.harness/final.txt','--expected',card['acceptance_binding'])
    elapsed=time.monotonic()-start
    task=json.loads((root/'specs/calculator/tasks.json').read_text())['tasks'][0]
    assert task['status']=='DONE'
    assert hashlib.sha256(index.read_bytes()).hexdigest()==before
    assert (root/'unrelated.txt').read_text()=='Pre-existing unstaged developer work\n'
    assert not (root/'specs/calculator/spec.md').exists()
    assert not (root/'.harness/runner.json').exists()
    assert not (root/'.harness/graph/task-context-CALC-001.json').exists()
    ev=json.loads((root/task['evidence'][-1]).read_text())
    result={'fixture':'simulated host and explicit fixture developer answers; actual installed CLI/engine/check execution',
            'root':str(root),'decisions':2,'developer_commands':0,'developer_json_edits':0,'administrative_cli_calls':len(calls),
            'host_authored_records':['request','initial-answer-reference','review','final-answer-reference'],
            'check_executions':len(ev['results']),'acceptance_support':ev['acceptance_support'],
            'elapsed_including_cli_and_checks':elapsed,'calls':calls,'staging_preserved':True,'result':'PASS'}
    atomic(root/'.harness/reports/compact-journey.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--project',type=Path,required=True); p.add_argument('--node'); p.add_argument('--cli')
    args=p.parse_args(); root=args.project.resolve()
    prefix=[args.node,args.cli,'--target',str(root),'--json'] if args.cli else [sys.executable,'-B',str(root/'harness')]
    print(json.dumps(journey(root,prefix),indent=2))
