#!/usr/bin/env python3
"""Deterministic parsePort replay. Consent/navigation are labelled fixtures, never live agents."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

KIT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(KIT),str(KIT/'tests')]
from harnesslib.core import Harness
from harnesslib.adopt import adopt
from harnesslib.storage import atomic, read
from harnesslib import workflow, reporting
from test_onboarding import OnboardingTests

p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--planning-baseline',type=Path,required=True)
a=p.parse_args();baseline=a.baseline.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
started=time.monotonic()
with tempfile.TemporaryDirectory(prefix='harness-fast-parse-port-') as tmp:
 root=Path(tmp).resolve()/'project';adopt(KIT,root,False);h=Harness(root);h.init()
 fixture=OnboardingTests();fixture.root=root;fixture.h=h;fixture.prepare()
 # Reuse only isolated, completed project onboarding scaffolding. Task scope is parsePort.
 f,t=h.task('CALC-001');f['feature_id']='parse-port'
 t.update(id='PORT-001',risk='low',outcome='Parse ASCII port strings in range 1..65535',scope=['parser.mjs','parser.test.mjs'],requirements=['REQ-001'],approval_requirements=[])
 t['acceptance_criteria']=['Accept valid ports; reject non-strings, invalid syntax and range.']
 t['failure_scenarios']=['Invalid port accepted or valid port rejected.'];t['acceptance_checks']=[{'criterion':t['acceptance_criteria'][0],'checks':['application-unit']}]
 old=root/'specs/calculator';dest=root/'specs/parse-port';old.rename(dest)
 atomic(dest/'tasks.json',f)
 for name in ['spec.md','plan.md']:
  (dest/name).write_text('Status: APPROVED\nRevision: 1\nApproval: SIMULATED fixture confirmation of workflow and brief plan\nTech-Spec-Revision: 1\nArchitecture-Revision: 1\n\nREQ-001: Parse ASCII digit strings in range 1..65535; throw TypeError for non-strings and RangeError otherwise.\nPlan: inspect requirements, implement parser and targeted tests, verify, review, request final approval.\n')
 cfg=read(root/'.harness/checks.json');cfg['checks']['application-unit'].update(argv=[shutil.which('node'),'--test','--test-reporter=tap','parser.test.mjs'],purpose='Exercise the original parsePort boundary cases');atomic(root/'.harness/checks.json',cfg)
 for rel in ['docs/TECH_SPEC.md','docs/ARCHITECTURE.md']:
  text=(root/rel).read_text().replace('a local addition function','a local port parser').replace('Add two input numbers accurately.','Parse digit strings in range 1..65535.');(root/rel).write_text(text)
 h.approve_onboarding('SIMULATED fixture','docs/approval.md')
 facts=dict(critical_risk=False,critical_unknowns=[],unknowns=[],public_api=False,architecture_change=False,components=1,inspected=['specs/parse-port/spec.md'],agent='deterministic fixture; no model')
 atomic(root/'.harness/facts.json',facts)
 assessment=workflow.assess(h,'PORT-001','.harness/facts.json');atomic(out/'assessment.json',assessment)
 (root/'.harness/confirmation.txt').write_text('SIMULATED fixture developer confirms FAST workflow and displayed brief plan together.\n')
 workflow.confirm(h,'PORT-001','FAST','SIMULATED fixture','.harness/confirmation.txt')
 # Graph tools are excluded from the deterministic replay; lifecycle and test commands are real.
 with patch('harnesslib.index_context.collect',return_value={'result':'PASS','reference':'SIMULATED navigation fixture'}),patch('harnesslib.index_context.ensure',return_value={'result':'PASS'}):
  h.transition('PORT-001','IN_PROGRESS','Simulated developer confirmed FAST and plan')
  for name in ['parser.mjs','parser.test.mjs']:shutil.copyfile(baseline/name,root/name)
  h.transition('PORT-001','IMPLEMENTED','Implemented parsePort and original targeted boundary tests')
  ev=h.verify('PORT-001');assert ev['result']=='PASS',ev
  h.transition('PORT-001','VERIFIED','Real Node tests passed')
  review={'task_id':'PORT-001','reviewer':'deterministic replay review fixture','evidence':h.task('PORT-001')[1]['evidence'][-1],'verdict':'PASS','summary':'Replay of previously reviewed parser; same test source retained. Not an independent new human review.','findings':[]}
  rev=dest/'reviews/replay.md';rev.parent.mkdir();rev.write_text('```harness-review\n'+json.dumps(review)+'\n```\n')
  h.approve('PORT-001','review','SIMULATED fixture','specs/parse-port/reviews/replay.md')
  data=reporting.report(h,'PORT-001',retain=True,retain_dir=out/'review')
  atomic(out/'verified-report.json',data);(out/'verified-report.md').write_text(reporting.render(data,True));(out/'verified-terminal.txt').write_text(reporting.render(data))
  raw=json.dumps(h.status(),indent=2);compact=reporting.render(data)
  (out/'legacy-status.json').write_text(raw)
  h.approve('PORT-001','developer','SIMULATED final consent','.harness/confirmation.txt')
  h.transition('PORT-001','DONE','SIMULATED final approval; replay only')
  done=reporting.report(h,'PORT-001');atomic(out/'done-report.json',done)
 task_docs=[p for p in dest.glob('*.md') if p.name in {'spec.md','plan.md'}]
 prior_docs=[p for folder in [a.planning_baseline.resolve()/'specs/parse-port',a.planning_baseline.resolve()/'openspec/changes/parse-port'] if folder.exists() for p in folder.rglob('*.md') if '/reviews/' not in str(p) and p.name!='verification.md']
 metrics={'scenario':'parsePort','fixture_seconds':round(time.monotonic()-started,3),'developer_confirmations_simulated':2,
          'task_planning_documents':len(task_docs),'historical_strict_planning_documents_observed':len(prior_docs),
          'historical_document_paths':[str(p.relative_to(a.planning_baseline.resolve())) for p in prior_docs],
          'legacy_status_bytes':len(raw.encode()),'compact_report_bytes':len(compact.encode()),
          'output_reduction_percent':round(100*(1-len(compact.encode())/len(raw.encode())),1),
          'assessment_inspection_bytes':assessment['inspection_bytes'],'assessment_inspected_files':len(assessment['inspected']),
          'verification':data['tasks'][0]['verification'],'model_tokens':None,'cached_tokens':None,'model_calls':0,
          'limitations':['Replay uses simulated developer confirmations and navigation; Node parser tests and Python lifecycle/evidence are real.',
                        'Elapsed time is a local fixture run, not a comparable real-agent speedup.',
                        'Historical provider counters are not normalized; no token-savings claim.',
                        'Historical human interactions/command counts/instruction loads are not reliably comparable.']}
 atomic(out/'metrics.json',metrics)
 (out/'DEMONSTRATION.md').write_text('# FAST parsePort demonstration\n\nDeterministic replay; no real developer approval or model execution is represented.\n\n1. Assessment: FAST; inspect one local requirements file.\n2. Show reasoning and brief plan; one simulated combined confirmation.\n3. Implement parser and original tests; real Node verification passes.\n4. Record replay review; report remains VERIFIED and requests final developer approval.\n5. A second simulated developer confirmation permits DONE.\n\nPersistent source/evidence snapshot: '+data['tasks'][0]['paths']['review_package']+'\n\n'+json.dumps(metrics,indent=2)+'\n')
print(json.dumps({'result':'PASS','metrics':str(out/'metrics.json'),'demonstration':str(out/'DEMONSTRATION.md')}))
