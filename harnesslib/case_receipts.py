"""Bounded, invocation-stamped JUnit subset. Reports are untrusted observations."""
import hashlib
import xml.etree.ElementTree as ET
from .storage import HarnessError, atomic, digest, read, redact, safe_path, uid

LIMIT = 1024 * 1024


def parse(raw, operation, check, invocation):
    try: text = raw.decode('utf-8')
    except UnicodeDecodeError as exc: raise HarnessError('JUnit must use UTF-8') from exc
    if len(raw) > LIMIT or '\x00' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise HarnessError('JUnit report oversized or contains prohibited declarations')
    try: root = ET.fromstring(raw)
    except ET.ParseError as exc: raise HarnessError('Malformed JUnit report') from exc
    if root.tag not in ('testsuite', 'testsuites'):
        raise HarnessError('Expected JUnit testsuite/testsuites')
    elements = list(root.iter())
    if len(elements) > 10000: raise HarnessError('Too many JUnit elements')
    allowed = {'testsuite','testsuites','testcase','properties','property','failure','error','skipped','system-out','system-err'}
    if any(e.tag not in allowed for e in elements): raise HarnessError('Unsupported JUnit element')
    def structure(e, depth=0):
        if depth > 12: raise HarnessError('JUnit nesting exceeds limit')
        children = {'testsuites': {'testsuite'}, 'testsuite': {'testsuite','testcase','properties','system-out','system-err'},
                    'testcase': {'failure','error','skipped','properties','system-out','system-err'}, 'properties': {'property'}}
        if any(c.tag not in children.get(e.tag, set()) for c in e):
            raise HarnessError('Invalid JUnit nesting')
        for c in e: structure(c, depth+1)
    structure(root)
    stamps = {}
    for e in root.iter('property'):
        name = e.get('name', '')
        if name.startswith('harness.'):
            if name in stamps: raise HarnessError('Duplicate invocation stamp')
            stamps[name] = e.get('value')
    if stamps != {'harness.operation': operation, 'harness.check': check, 'harness.invocation': invocation}:
        raise HarnessError('JUnit invocation/check stamp mismatch; emit a fresh report for this invocation')
    cases, seen = [], set()
    for e in root.iter('testcase'):
        name, group = e.get('name', ''), e.get('classname', '')
        identity = group + '.' + name
        if not name or not group or len(identity) > 500 or identity in seen:
            raise HarnessError('Missing or duplicate stable JUnit case identity')
        seen.add(identity)
        outcomes = [c for c in e if c.tag in ('failure','error','skipped')]
        if len(outcomes) > 1: raise HarnessError('Ambiguous JUnit case result')
        status = {'failure':'FAIL','error':'ERROR','skipped':'SKIPPED'}.get(outcomes[0].tag, 'UNKNOWN') if outcomes else 'PASS'
        if e.get('status', 'run') not in ('run', 'passed', 'failed') or e.get('result', '') in ('xfail', 'xpass'):
            status = 'UNKNOWN'
        detail = outcomes[0] if outcomes else None
        cases.append({'id': identity, 'status': status,
                      'failure_type': detail.get('type', '')[:200] if detail is not None else '',
                      'message': redact(detail.get('message', '')[:1000]) if detail is not None else ''})
    if not cases or len(cases) > 1000: raise HarnessError('JUnit must contain 1..1000 concrete cases')
    for suite in (e for e in elements if e.tag in ('testsuite', 'testsuites')):
        try:
            if int(suite.attrib['tests']) != sum(1 for _ in suite.iter('testcase')): raise ValueError()
        except (ValueError, KeyError): raise HarnessError('JUnit case count mismatch')
    return cases


def prepare(h, name, command, operation, binding):
    invocation = uid()
    ref = f'.harness/evidence/cases/{invocation}/junit.xml'
    path = safe_path(h.root, ref)
    path.parent.mkdir(parents=True, exist_ok=False)
    return {'path': str(path), 'raw_reference': ref, 'invocation': invocation,
            'operation': operation, 'check': name, 'command_hash': digest(command), 'input_binding': binding}


def collect(h, pending):
    path = safe_path(h.root, pending['raw_reference'])
    try:
        if not path.is_file() or path.stat().st_size > LIMIT: raise HarnessError('Fresh bounded JUnit report missing')
        with path.open('rb') as stream: raw = stream.read(LIMIT + 1)
        cases = parse(raw, pending['operation'], pending['check'], pending['invocation'])
        record = {k:v for k,v in pending.items() if k not in ('path','raw_reference')}
        record.update(schema_version=1, raw_hash=hashlib.sha256(raw).hexdigest(), cases=cases)
        record = redact(record)
        ref = pending['raw_reference'].replace('junit.xml','receipt.json')
        atomic(safe_path(h.root, ref), record)
        return {'reference': ref, 'hash': digest(record)}
    finally:
        # Do not retain arbitrary unredacted reporter content, including failures.
        if path.is_file(): path.unlink()


def observed(h, result, operation, binding):
    pointer = result.get('case_observation')
    if not pointer: raise HarnessError(result.get('case_observation_error', 'No structured case receipt; configure report_format and reporter'))
    path = safe_path(h.root, pointer['reference'])
    if not pointer['reference'].startswith('.harness/evidence/cases/') or path.stat().st_size > LIMIT:
        raise HarnessError('Unsafe or oversized case receipt')
    record = read(path)
    fields = {'schema_version','invocation','operation','check','command_hash','input_binding','raw_hash','cases'}
    if not isinstance(record, dict) or set(record) != fields or any(not isinstance(record[k], str) for k in fields - {'schema_version','cases'}):
        raise HarnessError('Invalid case receipt structure')
    if (digest(record) != pointer['hash'] or record.get('schema_version') != 1
            or record.get('operation') != operation or record.get('check') != result['check']
            or record.get('input_binding') != binding or record.get('command_hash') != digest(result['command'])):
        raise HarnessError('Case receipt binding/hash mismatch')
    if pointer['reference'] != f".harness/evidence/cases/{record['invocation']}/receipt.json":
        raise HarnessError('Case invocation identity mismatch')
    cases = record['cases']
    if (not isinstance(cases, list) or not 1 <= len(cases) <= 1000
            or any(not isinstance(c, dict) or set(c) != {'id','status','failure_type','message'}
                   or any(not isinstance(v, str) for v in c.values())
                   or c['status'] not in ('PASS','FAIL','ERROR','SKIPPED','UNKNOWN') for c in cases)
            or len({c['id'] for c in cases}) != len(cases)):
        raise HarnessError('Invalid case receipt identities')
    return record
