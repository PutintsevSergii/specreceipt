"""Bounded reviewer attestations tied to current inputs and actual assertions."""
import ast
import hashlib
from .storage import HarnessError, digest, read, safe_path


def review(h, task, rule, binding):
    ref = rule['review']
    feature, _ = h.task(task['id'])
    if not ref.startswith(f"specs/{feature['feature_id']}/reviews/"):
        raise HarnessError('Semantic review belongs in the feature reviews directory')
    path = safe_path(h.root, ref)
    if path.stat().st_size > 32768: raise HarnessError('Semantic review exceeds 32 KiB')
    data = read(path)
    required = {'schema_version','criterion','check','cases','input_binding','reviewer','reviewer_type','behavior','negative_scenario','gaps','assertions'}
    if (not isinstance(data, dict) or set(data) != required or type(data['schema_version']) is not int
            or data['schema_version'] != 1 or data['input_binding'] != binding
            or data['check'] != rule['check'] or data['cases'] != rule['cases']
            or data['reviewer_type'] not in ('human','agent')
            or any(not isinstance(data[k], str) or not 10 <= len(data[k]) <= 2000
                   for k in ('reviewer','behavior','negative_scenario','gaps'))):
        raise HarnessError('Semantic review needs current binding, concrete behavior/scenario/gaps and reviewer identity/type')
    assertions = data['assertions']
    if not isinstance(assertions, list) or not 1 <= len(assertions) <= 30:
        raise HarnessError('Semantic review needs actual source/assertion mappings')
    for assertion in assertions:
        if not isinstance(assertion, dict) or set(assertion) != {'path','line','text','sha256','case'}:
            raise HarnessError('Assertion needs path, line, exact text and source sha256')
        if any(not isinstance(assertion[k], str) for k in ('case','path','text','sha256')):
            raise HarnessError('Assertion mapping fields must be strings')
        if assertion['case'] not in rule['cases']: raise HarnessError('Assertion must map a required case')
        source = safe_path(h.root, assertion['path'])
        if source.stat().st_size > 1024*1024: raise HarnessError('Assertion source exceeds 1 MiB')
        raw = source.read_bytes()
        lines = raw.decode('utf-8').splitlines()
        line = assertion['line']
        if (type(line) is not int or not 1 <= line <= len(lines) or not assertion['text'].strip()
                or assertion['text'] != lines[line-1] or hashlib.sha256(raw).hexdigest() != assertion['sha256']):
            raise HarnessError('Semantic assertion mapping is missing or stale')
        try:
            tree = ast.parse(raw.decode('utf-8'))
            assertion_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Assert) or
                               (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr.startswith('assert'))]
            module = assertion['path'][:-3].replace('/', '.')
            matching = [method for cls in tree.body if isinstance(cls, ast.ClassDef)
                        for method in cls.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and module+'.'+cls.name+'.'+method.name == assertion['case']
                        and method.lineno <= line <= method.end_lineno]
            if source.suffix != '.py' or not matching or not any(n.lineno == line for n in assertion_nodes):
                raise HarnessError('Version 1 semantic mappings require a concrete Python assertion line')
        except SyntaxError as exc:
            raise HarnessError('Assertion source cannot be parsed') from exc
    if {a['case'] for a in assertions} != set(rule['cases']):
        raise HarnessError('Semantic review must map assertions for every required case')
    return data, {'reference':ref, 'hash':digest(data), 'reviewer':data['reviewer'], 'reviewer_type':data['reviewer_type'],
                  'limitation':'Reviewer attestation; identity is not authenticated and semantic completeness is not proven.'}
