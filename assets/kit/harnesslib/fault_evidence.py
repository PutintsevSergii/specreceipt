"""Opt-in exact replacement probe in a disposable stdlib-unittest fixture."""
from pathlib import Path
import json
import re
import shutil
import tempfile
from . import case_receipts, verification
from .storage import HarnessError, atomic, digest, read, safe_path, uid


def run(h, task, rule, operation, binding):
    spec = rule['fault_probe']
    config = read(safe_path(h.root, '.harness/checks.json'))['checks'][rule['check']]
    argv = config['argv']
    if (config.get('report_format') != 'junit-v1' or argv[:4] != ['{python}','-B','-m','harnesslib.junit_unittest']
            or len(argv) != 5 or not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', argv[4])):
        raise HarnessError('Fault probe supports only the bundled unittest reporter with one explicit test module')
    if not 10 <= len(spec['expected_message']) <= 1000: raise HarnessError('Fault expectation needs a specific assertion message')
    if spec['case'] not in rule['cases'] or not spec['before'] or spec['before'] == spec['after']:
        raise HarnessError('Fault mutation must target an explicitly required case and change behavior')
    verification.validate_scope(h.root, spec['fixture_paths'] + [spec['path']])
    if any(p.startswith(('harnesslib/','schemas/','specs/','docs/','.')) for p in spec['fixture_paths']):
        raise HarnessError('Fault fixture paths must be explicit application/test files, not engine, policy or hidden directories')
    inventory = verification.inventory(h.root)  # Retain unsafe-link protections even outside the fixture.
    paths = [p for p in inventory if any(p == s or (s.endswith('/') and p.startswith(s)) for s in spec['fixture_paths'])]
    if spec['path'] not in paths or len(paths) > 100 or sum(safe_path(h.root,p).stat().st_size for p in paths) > 4*1024*1024:
        raise HarnessError('Fault fixture must include the mutation target and stay within 100 files / 4 MiB')
    original = safe_path(h.root,spec['path']).read_text(encoding='utf-8')
    if original.count(spec['before']) != 1: raise HarnessError('Fault mutation must match exactly once')
    record = {'schema_version':1,'operation':operation,'input_binding':binding,'task_id':task['id'],
              'check':rule['check'],'spec_hash':digest(spec),'original_hash':digest(original),'detected':False}
    with tempfile.TemporaryDirectory(prefix='harness-fault-') as directory:
        root = Path(directory).resolve()
        for p in paths:
            target=safe_path(root,p); target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(safe_path(h.root,p),target)
        shutil.copytree(Path(__file__).parent,root/'harnesslib',ignore=shutil.ignore_patterns('__pycache__'))
        # Only operation metadata exists here; no task state, approvals or receipts are copied.
        class Fixture:
            def state(self): return {'active_operation':{'id':operation}}
            def binding(self): return binding
        fixture=Fixture(); fixture.root=root
        from .core import Harness
        baseline=Harness.run_check(fixture,rule['check'],config)
        before=case_receipts.observed(fixture,baseline,operation,binding)
        expected=set(rule['cases'])
        if baseline['result'] != 'PASS' or not expected <= {c['id'] for c in before['cases'] if c['status']=='PASS'}:
            raise HarnessError('Fault probe baseline must execute and pass all mapped cases')
        safe_path(root,spec['path']).write_text(original.replace(spec['before'],spec['after']),encoding='utf-8')
        mutant=Harness.run_check(fixture,rule['check'],config)
        try:
            after=case_receipts.observed(fixture,mutant,operation,binding)
        except (HarnessError, OSError, ValueError) as exc:
            after={'cases':[]}
            record['rejection']=str(exc)[:1500]
        failures=[c for c in after['cases'] if c['status']!='PASS']
        record.update(baseline_observation=before, mutant_observation=after if 'rejection' not in record else None,
                      baseline_report_hash=digest(before),mutant_report_hash=digest(after) if 'rejection' not in record else None,
                      failures=failures,
                      detected=(mutant['result']=='FAIL' and mutant['exit_code']==1 and len(failures)==1
                                and failures[0]['id']==spec['case'] and failures[0]['status']=='FAIL'
                                and failures[0]['failure_type']=='AssertionError'
                                and spec['expected_message'] in failures[0]['message']))
    if len(json.dumps(record).encode('utf-8'))>32768: raise HarnessError('Fault receipt exceeds 32 KiB; narrow the fixture module')
    ref=f'.harness/evidence/faults/{uid()}.json'
    atomic(safe_path(h.root,ref),record)
    return {'reference':ref,'hash':digest(record)}


def validate(h, task, rule, pointer, operation, binding):
    ref=pointer['reference']; path=safe_path(h.root,ref)
    if not ref.startswith('.harness/evidence/faults/') or path.stat().st_size>32768:
        raise HarnessError('Invalid fault receipt')
    data=read(path)
    if (digest(data)!=pointer['hash'] or data.get('schema_version')!=1 or data.get('operation')!=operation
            or data.get('input_binding')!=binding or data.get('task_id')!=task['id']
            or data.get('check')!=rule['check'] or data.get('spec_hash')!=digest(rule['fault_probe'])
            or data.get('detected') is not True
            or digest(data.get('baseline_observation'))!=data.get('baseline_report_hash')
            or digest(data.get('mutant_observation'))!=data.get('mutant_report_hash')):
        raise HarnessError('Fault was not detected by the intended mapped assertion')
    return pointer
