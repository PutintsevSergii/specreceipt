"""Criterion support is distinct from command exit status and code coverage."""

LIMITATION = 'Command execution only; no individual test execution or semantic correctness is established.'


def check_support(mapping, results):
    passed = {r['check'] for r in results if r['result'] == 'PASS' and r['exit_code'] == 0}
    return {'schema_version': 1, 'criteria': [
        {'criterion': row['criterion'],
         'level': 'CHECK_ONLY' if set(row['checks']) <= passed else 'FAILED',
         'limitation': LIMITATION}
        for row in mapping]}


def reported(task, evidence, h=None):
    if not evidence:
        return {'schema_version': 1, 'criteria': [
            {'criterion': row['criterion'], 'level': 'INSUFFICIENT', 'limitation': 'No execution receipt.'}
            for row in task.get('acceptance_checks', [])]}
    if h is not None and 'acceptance_support' in evidence:
        return evaluate(h, task, evidence['results'], evidence['id'], evidence['fingerprint'], existing=evidence['acceptance_support'])
    # Reading a historical receipt never upgrades or rewrites its claims.
    return evidence.get('acceptance_support') or check_support(task.get('acceptance_checks', []), evidence['results'])


def evaluate(h, task, results, operation, binding, existing=None, run_probes=False):
    from . import case_receipts, semantic_evidence, fault_evidence
    from .storage import HarnessError, redact
    support = check_support(task.get('acceptance_checks', []), results)
    by_name = {r['check']: r for r in results}
    for mapping, row in zip(task.get('acceptance_checks', []), support['criteria']):
        rules = mapping.get('required_cases', [])
        if not rules or row['level'] == 'FAILED': continue
        row.update(level='CASES_OBSERVED', limitation='Only the named current cases were observed; this is not proof of complete correctness.',
                   observations=[], reviews=[], probes=[])
        try:
            for rule in rules:
                result = by_name[rule['check']]
                record = case_receipts.observed(h, result, operation, binding)
                cases = {c['id']:c for c in record['cases']}
                if any(c not in cases or cases[c]['status'] != 'PASS' for c in rule['cases']):
                    raise HarnessError('Required case missing, skipped, unknown or failed: '+', '.join(rule['cases']))
                row['observations'].append({'check':rule['check'], 'cases':rule['cases'], **result['case_observation']})
                if rule.get('review'):
                    data, review = semantic_evidence.review(h, task, rule, binding)
                    if data['criterion'] != mapping['criterion']: raise HarnessError('Review criterion mismatch')
                    row['reviews'].append(review)
                    if row['level'] != 'FAULT_DETECTED': row['level']='REVIEW_ATTESTED'
                if rule.get('fault_probe'):
                    if run_probes:
                        pointer = fault_evidence.run(h, task, rule, operation, binding)
                    else:
                        old = next(r for r in (existing or {}).get('criteria', []) if r['criterion']==mapping['criterion'])
                        pointer = next(p for p in old.get('probes', []) if p['check']==rule['check'])
                        pointer = {k:v for k,v in pointer.items() if k!='check'}
                    fault_evidence.validate(h,task,rule,pointer,operation,binding)
                    row['probes'].append({'check':rule['check'], **pointer})
                    row['level']='FAULT_DETECTED'
            if row['reviews']:
                row['limitation']='Observed cases plus reviewer attestation; reviewer identity is not authenticated. Fault evidence, when present, covers only the specified mutation, not complete correctness.'
        except (HarnessError, OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
            row.update(level='INSUFFICIENT', limitation=redact(str(exc))[:1500] or 'Required evidence unavailable')
    return support
