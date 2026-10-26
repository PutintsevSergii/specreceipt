"""Host-mediated MCP investigation records. Tool use is agent-reported, never authenticated here."""
from datetime import datetime, timezone
import hashlib
import re

from .storage import HarnessError, atomic, digest, read, redact, safe_path

POLICY = '.harness/investigation-policy.json'
REPORT_DIR = '.harness/investigations'
TOOL_STATES = {'available', 'configured_only', 'unavailable', 'denied', 'failed', 'irrelevant'}
RESULTS = {'AGREE', 'CODE_ONLY', 'NO_MCP', 'CONFLICT', 'UNVERIFIED'}


def _text(value, label, maximum=1000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or value != redact(value):
        raise HarnessError(label + ' must be bounded, nonempty and sanitized')
    return value


def _sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''): value.update(chunk)
    return value.hexdigest()


def _time(value):
    _text(value, 'Observation time', 60)
    try:
        observed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if observed.tzinfo is None: raise ValueError()
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if not -300 <= age <= 86400: raise ValueError()
        return observed
    except ValueError as exc:
        raise HarnessError('Current MCP observation must be UTC-aware and at most 24 hours old') from exc


def policy(h):
    path = safe_path(h.root, POLICY)
    value = read(path) if path.exists() else {'schema_version': 1, 'required_sources': []}
    h.schema('investigation-policy', value)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'required_sources'} or value['schema_version'] != 1:
        raise HarnessError('Invalid investigation policy')
    entries = value['required_sources']
    if not isinstance(entries, list) or len(entries) > 32: raise HarnessError('Invalid required source list')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'category', 'tasks'}:
            raise HarnessError('Invalid required source entry')
        category = _text(entry['category'], 'Required category', 80)
        tasks = entry['tasks']
        if category in seen or not isinstance(tasks, list) or not 1 <= len(tasks) <= 32 or len(tasks) != len(set(tasks)) or any(not isinstance(t, str) or not re.fullmatch(r'[A-Za-z0-9*_-]{1,80}', t) for t in tasks):
            raise HarnessError('Duplicate category or invalid task selectors')
        seen.add(category)
    return value


def required(h, task_id):
    return {entry['category'] for entry in policy(h)['required_sources'] if task_id in entry['tasks'] or '*' in entry['tasks']}


def report_ref(task_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', task_id): raise HarnessError('Invalid task ID')
    return f'{REPORT_DIR}/{task_id}.json'


def current_ref(task_id):
    return f'{REPORT_DIR}/{task_id}.current.json'


def _check_report(h, task, value):
    h.schema('investigation', value)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'task_id', 'question', 'definition', 'repository_fingerprint', 'policy_hash', 'tools', 'claims', 'host_trace'}:
        raise HarnessError('Invalid investigation report fields')
    if value['schema_version'] != 1 or value['task_id'] != task['id'] or value['question'] != task['outcome']:
        raise HarnessError('Investigation question or task changed')
    _text(value['question'], 'Investigation question', 2000)
    if value['definition'] != h.definition(task) or value['policy_hash'] != digest(policy(h)):
        raise HarnessError('Investigation task definition or source policy changed')
    if value['repository_fingerprint'] != digest(h.fingerprints()):
        raise HarnessError('Investigation repository fingerprint changed')
    if value['host_trace'] is not None: _text(value['host_trace'], 'Host trace reference', 500)
    tools = value['tools']; claims = value['claims']
    if not isinstance(tools, list) or len(tools) > 64 or not isinstance(claims, list) or not 1 <= len(claims) <= 32:
        raise HarnessError('Investigation tools or claims exceed bounds')
    tool_map = {}
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {'name', 'status', 'read_only', 'reason'}:
            raise HarnessError('Invalid MCP tool observation')
        name = _text(tool['name'], 'MCP tool name', 160)
        if name in tool_map or tool['status'] not in TOOL_STATES or type(tool['read_only']) is not bool:
            raise HarnessError('Duplicate or invalid MCP tool observation')
        _text(tool['reason'], 'MCP tool relevance reason', 500)
        tool_map[name] = tool
    claim_ids, used_tools = set(), set()
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != {'id', 'criterion', 'summary', 'category', 'code', 'mcp', 'result'}:
            raise HarnessError('Invalid investigation claim')
        ident = _text(claim['id'], 'Claim ID', 80)
        if ident in claim_ids or claim['criterion'] not in task['acceptance_criteria']:
            raise HarnessError('Claim ID duplicates or criterion is not in the task')
        claim_ids.add(ident)
        _text(claim['summary'], 'Claim summary', 1000)
        category = claim['category']
        if category is not None: _text(category, 'Source category', 80)
        code = claim['code']; mcp = claim['mcp']; result = claim['result']
        if not isinstance(code, list) or len(code) > 8 or not isinstance(mcp, list) or len(mcp) > 8 or result not in RESULTS:
            raise HarnessError('Invalid claim evidence or result')
        for source in code:
            if not isinstance(source, dict) or set(source) != {'path', 'line', 'sha256'}:
                raise HarnessError('Invalid repository source reference')
            path = safe_path(h.root, _text(source['path'], 'Source path', 300))
            if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024 or type(source['line']) is not int or source['line'] < 1 or source['sha256'] != _sha(path):
                raise HarnessError('Repository source changed or location invalid: ' + source['path'])
            with path.open('rb') as stream:
                if source['line'] > (sum(1 for _ in stream) or 1): raise HarnessError('Repository source line is outside the file')
        successes = 0
        for source in mcp:
            if not isinstance(source, dict) or set(source) != {'tool', 'resource', 'revision', 'observed_at', 'summary', 'status'}:
                raise HarnessError('Invalid MCP source reference')
            tool = _text(source['tool'], 'MCP tool', 160)
            if tool not in tool_map: raise HarnessError('MCP source uses an unobserved tool')
            resource = _text(source['resource'], 'MCP resource', 300)
            if source['status'] == 'success': _text(source['revision'], 'MCP revision', 160)
            elif source['revision'] is not None: raise HarnessError('Failed or denied MCP source has no confirmed revision')
            _time(source['observed_at'])
            _text(source['summary'], 'MCP summary', 1000)
            if source['status'] not in {'success', 'denied', 'failed', 'unavailable'}:
                raise HarnessError('Invalid MCP source status')
            if source['status'] == 'success':
                if tool_map[tool]['status'] != 'available' or not tool_map[tool]['read_only']:
                    raise HarnessError('Configured-only or write-capable MCP tool cannot confirm a claim')
                successes += 1
            used_tools.add(tool)
        if result in {'AGREE', 'CONFLICT'} and (not code or not successes):
            raise HarnessError('Agreement or conflict needs code and successful MCP evidence')
        if result in {'CODE_ONLY', 'NO_MCP'} and (not code or successes):
            raise HarnessError('Code-only claim must have code and no successful MCP evidence')
        if result in {'CODE_ONLY', 'NO_MCP'} and mcp:
            raise HarnessError('A failed or denied MCP query is an UNVERIFIED claim, not code-only coverage')
        if result == 'NO_MCP' and any(tool['status'] == 'available' and tool['read_only'] for tool in tools):
            raise HarnessError('NO_MCP contradicts an available read-only MCP tool')
    for name, tool in tool_map.items():
        if tool['status'] == 'available' and tool['read_only'] and name not in used_tools:
            raise HarnessError('Available relevant read-only MCP tool was not queried: ' + name)
    return None


def record(h, task_id, source_ref):
    _, task = h.task(task_id)
    path = safe_path(h.root, source_ref)
    if not path.is_file() or path.stat().st_size > 65536: raise HarnessError('Investigation candidate missing or over 64 KiB')
    value = read(path)
    _check_report(h, task, value)
    target = report_ref(task_id)
    atomic(safe_path(h.root, target), value)
    return {'result': 'PASS', 'report': target, 'attestation': 'agent-reported; no generic MCP call authentication'}


def _current(h, task_id, explicit=None):
    path = safe_path(h.root, explicit or current_ref(task_id))
    if not path.exists(): return None
    if path.stat().st_size > 16384: raise HarnessError('Current MCP observations exceed 16 KiB')
    value = read(path)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'task_id', 'observed_at', 'sources'} or value['schema_version'] != 1 or value['task_id'] != task_id:
        raise HarnessError('Invalid current MCP observation')
    observed_at = _time(value['observed_at'])
    sources = value['sources']
    if not isinstance(sources, list) or len(sources) > 64: raise HarnessError('Invalid current MCP sources')
    result = {}
    for source in sources:
        if not isinstance(source, dict) or set(source) != {'resource', 'revision'}:
            raise HarnessError('Invalid current MCP source entry')
        resource = _text(source['resource'], 'MCP resource', 300)
        if resource in result: raise HarnessError('Duplicate current MCP resource')
        result[resource] = _text(source['revision'], 'MCP revision', 160)
    return {'observed_at': observed_at, 'revisions': result}


def check(h, task_id, current=None):
    _, task = h.task(task_id)
    needed = required(h, task_id)
    path = safe_path(h.root, report_ref(task_id))
    if not path.is_file():
        return {'result': 'BLOCKED', 'coverage': 'NO_REPORT', 'gaps': ['Task investigation report is missing'], 'required_sources': sorted(needed)}
    if path.stat().st_size > 65536: raise HarnessError('Investigation report exceeds 64 KiB')
    value = read(path)
    _check_report(h, task, value)
    observed = _current(h, task_id, current)
    gaps = []
    categories = {claim['category'] for claim in value['claims'] if claim['category'] is not None}
    for category in sorted(needed-categories): gaps.append('Required source category has no claim: ' + category)
    successful = 0
    for claim in value['claims']:
        if claim['result'] in {'CONFLICT', 'UNVERIFIED'}:
            gaps.append('Claim ' + claim['id'] + ' is ' + claim['result'])
        if claim['category'] in needed and claim['result'] != 'AGREE':
            gaps.append('Required source did not confirm claim ' + claim['id'])
        for source in claim['mcp']:
            if source['status'] != 'success': continue
            successful += 1
            if observed is None:
                gaps.append('Current MCP revision unavailable for ' + source['resource'])
            elif observed['revisions'].get(source['resource']) != source['revision']:
                gaps.append('MCP revision missing or changed: ' + source['resource'])
            elif observed['observed_at'] < datetime.fromisoformat(source['observed_at'].replace('Z', '+00:00')):
                gaps.append('Current MCP observation predates claim: ' + source['resource'])
    return {'result': 'BLOCKED' if gaps else 'PASS',
            'coverage': 'CONFLICT' if any(c['result'] == 'CONFLICT' for c in value['claims']) else
                        'MCP_SUPPORTED' if successful else 'NO_MCP' if any(c['result'] == 'NO_MCP' for c in value['claims']) else 'CODE_ONLY',
            'gaps': gaps, 'required_sources': sorted(needed),
            'attestation': 'agent-reported tool use; current source revisions ' + ('supplied' if observed is not None else 'not rechecked')}
