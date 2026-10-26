"""Task lifecycle, checkpoints and evidence gates. Local records are not attestations."""
import copy
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
from . import graph, index_context, openspec_tool, readiness, verification, workflow
from .storage import HarnessError, atomic, digest, events, finish_transaction, now, read, redact, safe_path, transaction, uid, validate_schema

TRANSITIONS = {'TODO':{'IN_PROGRESS','BLOCKED'},'IN_PROGRESS':{'IMPLEMENTED','BLOCKED','REWORK'},
 'IMPLEMENTED':{'VERIFIED','REWORK','BLOCKED'},'VERIFIED':{'DONE','REWORK','BLOCKED'},
 'DONE':{'REWORK'},'BLOCKED':{'IN_PROGRESS','REWORK'},'REWORK':{'IN_PROGRESS','BLOCKED'}}
MUTABLE_TASK = {'status','evidence','next_action','history','approvals','execution','regression_evidence'}

class Harness:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.session = os.environ.get('HARNESS_SESSION_ID',uid())
        self.actor = os.environ.get('HARNESS_ACTOR','local-agent')

    def schema(self, name, value):
        validate_schema(value,read(self.root/f'schemas/{name}.schema.json'))

    def state(self):
        state = read(self.root/'.harness/state.json')
        self.schema('state',state)
        return state

    def features(self):
        result = {}
        for path in sorted((self.root/'specs').glob('*/tasks.json')):
            safe_path(self.root,path.relative_to(self.root).as_posix())
            data = read(path)
            self.schema('tasks',data)
            if data['feature_id'] != path.parent.name:
                raise HarnessError('Feature ID must match its directory')
            result[data['feature_id']] = data
        return result

    def task(self, task_id):
        matches = [(f,t) for f in self.features().values() for t in f['tasks'] if t['id'] == task_id]
        if len(matches) != 1:
            raise HarnessError(f'Task must exist and have a unique ID: {task_id}')
        return matches[0]

    def revisions(self):
        return {'tech_spec':self.metadata('docs/TECH_SPEC.md')['revision'],
                'architecture':self.metadata('docs/ARCHITECTURE.md')['revision']}

    def metadata(self, rel):
        text = safe_path(self.root,rel).read_text()
        values = {}
        for name in ['Status','Revision','Approval']:
            match = re.search(rf'^{name}: (.+)$',text,re.M)
            if not match:
                raise HarnessError(f'{rel}: missing {name}: metadata')
            values[name.lower()] = match.group(1).strip()
        if values['status'] not in {'DRAFT','APPROVED','SUPERSEDED'}:
            raise HarnessError(f'{rel}: invalid approval status')
        if values['status'] == 'APPROVED' and values['approval'] in {'TBD','NONE'}:
            raise HarnessError(f'{rel}: approved document needs approval reference')
        return values

    def fingerprints(self):
        # Conservative repository-wide invalidation. Tasks contribute only their definitions.
        hashes = verification.inventory(self.root)
        hashes.pop('docs/ENGINEERING_LOG.md',None)
        for rel in list(hashes):
            if rel.startswith('specs/') and (rel.endswith('/verification.md') or '/reviews/' in rel):
                del hashes[rel]
            elif rel.startswith('specs/') and rel.endswith('/tasks.json'):
                data = read(self.root/rel)
                data['tasks'] = [{k:v for k,v in t.items() if k not in MUTABLE_TASK} for t in data['tasks']]
                hashes[rel] = digest(data)
        for rel in ['.harness/checks.json','.harness/graph-config.json','.harness/environment.json']:
            hashes[rel] = digest(read(safe_path(self.root,rel)))
        if (self.root/'.harness/onboarding.json').exists():
            hashes['.harness/onboarding.json'] = digest(read(safe_path(self.root,'.harness/onboarding.json')))
        if (self.root/'.harness/runner.json').exists():
            hashes['.harness/runner.json'] = digest(read(safe_path(self.root,'.harness/runner.json')))
        if (self.root/'.harness/workflow-policy.json').exists():
            hashes['.harness/workflow-policy.json'] = digest(workflow.policy(self))
        for feature in self.features().values():
            if feature.get('spec_source'):
                for rel, text in openspec_tool.feature_source(self.root,feature).items():
                    if rel == f"openspec/changes/{feature['spec_source']['change']}/tasks.md":
                        hashes[rel] = digest(text)
        return hashes

    def definition(self, task):
        definitions = {}
        for item in self.check_closure(task):
            feature, _ = self.task(item['id'])
            paths = ['docs/TECH_SPEC.md', 'docs/ARCHITECTURE.md',
                     '.harness/checks.json', '.harness/onboarding.json',
                     f"specs/{feature['feature_id']}/spec.md", f"specs/{feature['feature_id']}/plan.md"]
            definitions[item['id']] = {'task':{k:v for k,v in item.items() if k not in MUTABLE_TASK},
                'kind':feature['kind'], 'revisions':feature['revisions'],
                'inputs':{rel:digest(safe_path(self.root,rel).read_text()) for rel in paths},
                **({'spec_source':feature['spec_source'], 'openspec_inputs':openspec_tool.feature_source(self.root,feature)} if feature.get('spec_source') else {})}
        return digest(definitions)

    def check_closure(self, task):
        ordered, visiting, visited = [], set(), set()
        def visit(t):
            if t['id'] in visiting: raise HarnessError('Task dependency cycle')
            if t['id'] in visited: return
            visiting.add(t['id'])
            for dep in t['dependencies']: visit(self.task(dep)[1])
            visiting.remove(t['id']); visited.add(t['id']); ordered.append(t)
        visit(task)
        return ordered

    def completed(self, task):
        if task['status'] != 'DONE' or not task['evidence']: return False
        ev = self.evidence(task['evidence'][-1])
        try:
            if not self.successful_evidence(task,ev): return False
            self.check_approvals(task, historical=True)
        except (HarnessError, OSError): return False
        return True

    def environment(self):
        return {'python':platform.python_version(),'platform':platform.system(),'machine':platform.machine(),
                'declared':read(safe_path(self.root,'.harness/environment.json'))}

    def binding(self):
        return digest({'files':self.fingerprints(),'environment':self.environment()})

    def git(self):
        def get(*args):
            try:
                p = subprocess.run(['git',*args],cwd=self.root,capture_output=True,text=True,timeout=5)
                return p.stdout.strip() if p.returncode == 0 else None
            except (OSError,subprocess.TimeoutExpired):
                return None
        return {'head':get('rev-parse','HEAD'),'branch':get('symbolic-ref','--short','HEAD')}

    def event(self, kind, summary, task=None, feature=None, **extra):
        return {'id':uid(),'timestamp':now(),'session_id':self.session,'actor':self.actor,
                'feature_id':feature,'task_id':task,'type':kind,'summary':summary,
                'rationale':extra.pop('rationale','Persist observable outcome for safe continuation.'),
                'changed_files':extra.pop('changed_files',[]),'commands':extra.pop('commands',[]),
                'result':extra.pop('result','PASS'),'evidence':extra.pop('evidence',[]),
                'risks':extra.pop('risks',[]),'limitations':extra.pop('limitations',[]),
                'next_action':extra.pop('next_action','Inspect status and continue the approved slice.')}

    def save(self, state, event, feature=None, extra=None):
        state['updated_at'] = now()
        self.schema('state',state)
        self.schema('event',event)
        writes = {'.harness/state.json':state,**(extra or {})}
        if feature:
            self.schema('tasks',feature)
            writes[f"specs/{feature['feature_id']}/tasks.json"] = feature
        transaction(self.root,writes,event)
        if event['type'] == 'workflow-assessed':
            from .reporting import invalidate_current
            invalidate_current(self, 'Workflow assessment changed; query live status after the bounded assessment.')
        if event['type'] in {'interrupted','transition','verification','verification-stale','approval-recorded','workflow-selected','checkpoint','replanned','baseline-recognized','recovery-acknowledged','blocker','resolve'}:
            from .reporting import refresh_current
            refresh_current(self)

    def init(self):
        if (self.root/'.harness/state.json').exists():
            self.state()
            return {'changed':False,'message':'Existing state preserved.'}
        stamp = now()
        state = {'schema_version':1,'created_at':stamp,'updated_at':stamp,'active_feature':None,'active_task':None,
                 'phase':'SETUP','last_checkpoint':None,'active_operation':None,'uncertain_outcome':None,
                 'blockers':[],'pending_decisions':['APP-001: Fill and approve application specification and architecture.'],
                 'next_action':'Fill docs/TECH_SPEC.md and docs/ARCHITECTURE.md before application work.',
                 'revisions':self.revisions(),'git':self.git(),'fingerprints':{},'latest_verification':[],
                 'graph':graph.status(self.root)}
        self.save(state,self.event('setup','Initialized generic harness; application remains unconfigured.'))
        return {'changed':True}

    def validate(self):
        state = self.state()
        for rel,sections in {
            'docs/TECH_SPEC.md':['Goals','Users','Scope','Non-goals','Requirements','Stack','Persistence','Contracts','Security','Performance','Dependencies','Environments','Acceptance','Assumptions','Questions'],
            'docs/ARCHITECTURE.md':['Boundaries','Modules','Dependencies','Data flows','Persistence','Recovery','Integrations','Testing','Observability','ADRs']}.items():
            self.metadata(rel)
            content = (self.root/rel).read_text()
            for section in sections:
                if f'## {section}\n' not in content:
                    raise HarnessError(f'{rel}: missing section {section}')
        checks = read(self.root/'.harness/checks.json')
        self.schema('checks',checks)
        self.schema('graph-config',read(self.root/'.harness/graph-config.json'))
        if (self.root/'.harness/onboarding.json').exists():
            self.schema('onboarding',read(self.root/'.harness/onboarding.json'))
        tasks = {}
        for feature in self.features().values():
            for name in ['spec.md','plan.md','verification.md']:
                path = f"specs/{feature['feature_id']}/{name}"
                text = safe_path(self.root,path).read_text()
                if not text.strip():
                    raise HarnessError(f'Empty feature document: {path}')
                if name != 'verification.md':
                    self.metadata(path)
                    for key,label in [('tech_spec','Tech-Spec-Revision'),('architecture','Architecture-Revision')]:
                        if f"{label}: {feature['revisions'][key]}\n" not in text:
                            raise HarnessError(f'{path}: missing/mismatched revision pin')
            reqtext = (self.root/'docs/TECH_SPEC.md').read_text()+(self.root/f"specs/{feature['feature_id']}/spec.md").read_text()
            if feature.get('spec_source'):
                reqtext = '\n'.join(openspec_tool.feature_source(self.root,feature).values())
            for task in feature['tasks']:
                if task['id'] in tasks:
                    raise HarnessError('Duplicate task ID')
                tasks[task['id']] = task
                for req in task['requirements']:
                    if not re.search(r'(?<![\w-])'+re.escape(req)+r'(?![\w-])',reqtext):
                        raise HarnessError(f'Unknown requirement {req}')
                if set(task['required_checks']) - set(checks['checks']):
                    raise HarnessError(f"{task['id']}: undefined required checks")
                previous = 'TODO'
                for entry in task['history']:
                    if entry['from'] != previous or entry['to'] not in TRANSITIONS[previous]:
                        raise HarnessError(f"{task['id']}: invalid transition history")
                    previous = entry['to']
                if previous != task['status']:
                    raise HarnessError(f"{task['id']}: status/history mismatch")
                for ref in task['evidence'] + task.get('regression_evidence',[]):
                    self.evidence(ref)
        visiting,visited = set(),set()
        def visit(key):
            if key in visiting: raise HarnessError('Task dependency cycle')
            if key in visited: return
            visiting.add(key)
            for dep in tasks[key]['dependencies']:
                if dep not in tasks: raise HarnessError(f'Unknown dependency {dep}')
                visit(dep)
            visiting.remove(key)
            visited.add(key)
        for key in tasks: visit(key)
        if state['active_task'] is not None:
            f,t = self.task(state['active_task'])
            if f['feature_id'] != state['active_feature']:
                raise HarnessError('Active task/feature mismatch')
        journal = events(self.root)
        if len({e['id'] for e in journal}) != len(journal):
            raise HarnessError('Duplicate journal event')
        for event in journal: self.schema('event',event)
        for path in (self.root/'.harness/evidence').glob('*.json'):
            self.schema('evidence',read(path))
        for task in tasks.values():
            if task['status'] == 'DONE':
                if not self.completed(task): raise HarnessError(f"{task['id']}: completion inputs/review changed; run resume")
            elif task['status'] == 'VERIFIED':
                if not self.current_evidence(task):
                    raise HarnessError(f"{task['id']}: verification is stale or missing; run resume")
        return {'result':'PASS','tasks':len(tasks),'application_ready':self.application_ready(),
                'graph':graph.status(self.root),'limitations':['Semantic requirement/architecture conformance requires review.']}

    def application_ready(self):
        return readiness.project(self)['application_ready']

    def approve_onboarding(self, by, reference):
        self.reconcile()
        report = readiness.project(self, require_approval=False)
        if report['blockers']:
            raise HarnessError('Documentation not ready for approval: ' + '; '.join(report['blockers']))
        content = safe_path(self.root,reference).read_text()
        if not readiness.substantive(by) or not readiness.substantive(content):
            raise HarnessError('Developer identity and substantive approval reference required.')
        record = read(self.root/'.harness/onboarding.json')
        record['approval'] = {'by':by,'at':now(),'reference':reference,
                              'reference_hash':digest(content),'fingerprint':readiness.fingerprint(self,record)}
        self.schema('onboarding',record)
        state = self.state()
        state['next_action'] = 'Run readiness TASK-ID for the first approved application slice.'
        self.save(state,self.event('onboarding-approved','Recorded developer documentation approval; identity is not authenticated.'),
                  extra={'.harness/onboarding.json':record})
        self.checkpoint()
        return readiness.project(self)

    def ready(self, feature, task):
        workflow.guard(self, feature, task)
        openspec_tool.ready(self.root, feature)
        if feature['revisions'] != self.revisions():
            raise HarnessError('Canonical revisions changed; replan and approve feature.')
        for name in ['spec.md','plan.md']:
            rel = f"specs/{feature['feature_id']}/{name}"
            if self.metadata(rel)['status'] != 'APPROVED' or 'TBD' in (self.root/rel).read_text():
                raise HarnessError(f'{rel} requires approved, completed inputs')
        if feature['kind'] == 'application':
            self.validate()
            report = readiness.report(self, task['id'])
            if report['blockers']:
                raise HarnessError('Application implementation blocked: ' + '; '.join(report['blockers']))
        if feature['kind'] == 'harness' and any(not p.startswith(('docs/','tests/','harnesslib/','schemas/','templates/','.agents/skills/','tests-node/','assets/')) and p not in {'AGENTS.md','harness','scripts/update-tools.py','scripts/python.sh','install.sh','scripts/build-assets.mjs','scripts/benchmark-workflow.py','scripts/test-package.mjs','src/cli.ts','src/integrations.ts','src/doctor.ts','src/copilot.ts','src/core.ts','src/engine.ts','scripts/test-codex-e2e.mjs','scripts/test-copilot-e2e.mjs'} for p in task['scope']):
            raise HarnessError('Harness task scope must stay within harness files.')
        for dep in task['dependencies']:
            _, other = self.task(dep)
            if not self.completed(other):
                raise HarnessError(f'Dependency {dep} is not currently complete')

    def evidence(self, ref):
        if not re.fullmatch(r'\.harness/evidence/[a-zA-Z0-9-]+\.json',ref):
            raise HarnessError('Invalid evidence reference')
        data = read(safe_path(self.root,ref))
        self.schema('evidence',data)
        return data

    def successful_evidence(self, task, ev):
        closure = self.check_closure(task)
        required = {name for t in closure for name in t['required_checks']}
        results = ev['results']
        passed = {r['check'] for r in results if r['result'] == 'PASS' and r['exit_code'] == 0}
        try:
            expected = [{'criterion':m['criterion'],'checks':m['checks'],'result':'PASS'}
                        for m in verification.acceptance(task)]
        except HarnessError: return False
        logs_valid = all(not r.get('log') or (safe_path(self.root,r['log']).is_file() and r.get('log_hash') == digest(safe_path(self.root,r['log']).read_text())) for r in results)
        return (logs_valid and ev.get('definition_hash') == self.definition(task) and ev['task_id'] == task['id']
                and ev['result'] == 'PASS' and passed == required and len(passed) == len(results)
                and ev.get('checked_tasks') == [t['id'] for t in closure]
                and ev.get('acceptance_results') == expected and ev['revisions'] == self.revisions()
                and ev['check_config_hash'] == digest(read(safe_path(self.root,'.harness/checks.json'))))

    def current_evidence(self, task):
        if task.get('execution', {}).get('recognitions'):
            try: verification.scope_changes(self,task)
            except (HarnessError,OSError,ValueError): return False
        if not task['evidence']: return False
        refs = task['evidence'] + task.get('regression_evidence',[])
        ev = max((self.evidence(ref) for ref in refs), key=lambda e:e['created_at'])
        return self.successful_evidence(task,ev) and ev['fingerprint'] == self.binding()

    def check_approvals(self, task, historical=False):
        required = set(task['approval_requirements']) | {'review'} | ({'developer'} if task.get('workflow') else set())
        fingerprint = self.evidence(task['evidence'][-1])['fingerprint'] if historical and task['evidence'] else self.binding()
        for key in required:
            approval = task['approvals'].get(key)
            expected = workflow.decision_binding(self,self.task(task['id'])[0],task) if task.get('workflow') and key in {'workflow-plan','plan'} else fingerprint
            if not approval or approval['fingerprint'] != expected:
                raise HarnessError(f'Current {key} approval/review required for DONE')
            content = safe_path(self.root,approval['reference']).read_text()
            if approval.get('reference_hash') != digest(content):
                raise HarnessError(f'Current {key} reference changed; repeat review/approval')
            if key == 'review': verification.review(self, task, content)

    def replan(self, task_id, reference):
        self.reconcile()
        feature,task = self.task(task_id)
        if task['status'] not in {'REWORK','BLOCKED'}:
            raise HarnessError('Replan requires REWORK or BLOCKED; record the reason first')
        content = safe_path(self.root,reference).read_text()
        if not readiness.substantive(content): raise HarnessError('Actual replan approval reference required')
        self.ready(feature,task)
        verification.acceptance(task); verification.validate_scope(self.root,task['scope'])
        if not task.get('execution'):
            raise HarnessError('Legacy task has no baseline; create a reviewed replacement task without inventing past scope evidence')
        original_execution = copy.deepcopy(task['execution'])
        baseline = dict(task['execution'].get('policy_baseline', {}))
        current = self.fingerprints()
        # Explicit reviewed replanning may update policy inputs, never absorb source edits.
        policy = {'docs/TECH_SPEC.md','docs/ARCHITECTURE.md','docs/DECISION_QUEUE.md',
                  '.harness/checks.json','.harness/onboarding.json','.harness/graph-config.json','.harness/environment.json',
                  f"specs/{feature['feature_id']}/tasks.json",f"specs/{feature['feature_id']}/spec.md",
                  f"specs/{feature['feature_id']}/plan.md",reference}
        for path in policy:
            if path in current: baseline[path]=current[path]
        task['execution']['policy_baseline'] = baseline
        task['execution']['definition'] = self.definition(task)
        verification.scope_changes(self,task,allow_stale_recognition=True)
        task['approvals']={}
        archive = f'.harness/evidence/reconciliation/execution-before-replan-{uid()}.json'
        self.save(self.state(),self.event('replanned','Recorded explicit reviewed replanning: '+reference,task_id,evidence=[archive]),feature,{archive:original_execution})
        self.checkpoint()
        return {'result':'PASS','task_id':task_id,'next_action':'Restart task; fresh verification and review required'}

    def transition(self, task_id, target, reason):
        self.reconcile()
        feature,task = self.task(task_id)
        old = task['status']
        navigation_context = None
        if target not in TRANSITIONS[old]:
            raise HarnessError(f'Unsupported transition {old} -> {target}')
        state = self.state()
        if target == 'IN_PROGRESS':
            if state['active_task'] not in {None,task_id}:
                _,active = self.task(state['active_task'])
                if active['status'] not in {'DONE','BLOCKED'}:
                    raise HarnessError('Finish or block the active task first')
            self.ready(feature,task)
            verification.validate_scope(self.root, task['scope'])
            verification.acceptance(task)
            if feature['kind'] == 'application':
                navigation_context = index_context.collect(self,feature,task)
            # Preserve baseline across retries; restarting cannot launder extra edits.
            if task.get('execution'):
                verification.scope_changes(self,task)
            else:
                task['execution'] = {'baseline':self.fingerprints(), 'definition':self.definition(task)}
        if target == 'IMPLEMENTED':
            self.ready(feature,task)
            verification.scope_changes(self,task)
            if feature['kind'] == 'application':
                index_context.ensure(self.root)
        if target in {'VERIFIED','DONE'}:
            verification.scope_changes(self,task)
            self.ready(feature,task)
            if not self.current_evidence(task):
                raise HarnessError('Current PASS evidence for every required check is mandatory')
        if target == 'DONE': self.check_approvals(task)
        if old == 'DONE' and target == 'REWORK' and task.get('execution'):
            task.pop('execution')  # a new work attempt, not a reset of an unfinished retry
        task['status'] = target
        task['history'].append({'at':now(),'from':old,'to':target,'reason':reason})
        task['next_action'] = {'IN_PROGRESS':'Implement the approved slice.', 'IMPLEMENTED':'Run required verification.',
                              'VERIFIED':'Perform review and required approvals.', 'DONE':'Choose the next approved task.',
                              'BLOCKED':'Resolve the recorded blocker.', 'REWORK':'Diagnose and rework before verification.'}[target]
        state.update(active_feature=feature['feature_id'],active_task=task_id,phase=target,next_action=task['next_action'])
        self.save(state,self.event('transition',f'{old} -> {target}: {reason}',task_id,feature['feature_id']),feature)
        self.checkpoint()
        result = {'task':task_id,'status':target}
        if navigation_context: result['navigation_context'] = navigation_context
        return result

    def reconcile(self):
        finish_transaction(self.root)
        state = self.state()
        if state['active_operation']:
            operation = state['active_operation']
            state['active_operation'] = None
            state['uncertain_outcome'] = operation
            state['blockers'] = sorted(set(state['blockers']+['Interrupted operation: inspect effects and acknowledge recovery.']))
            state['next_action'] = 'Inspect operation effects/processes, then recovery acknowledge --note ...; do not replay automatically.'
            self.save(state,self.event('interrupted','Operation outcome is uncertain; no automatic replay.',result='BLOCKED'))
        for feature in self.features().values():
            changed = False
            for task in feature['tasks']:
                if (task['status'] == 'VERIFIED' and not self.current_evidence(task)) or (task['status'] == 'DONE' and not self.completed(task)):
                    if task['status'] == 'DONE' and task.get('execution'):
                        task.pop('execution')  # subsequent work gets a new observed baseline
                    task['history'].append({'at':now(),'from':task['status'],'to':'REWORK','reason':'Source, requirements, environment or check configuration changed.'})
                    task['status'] = 'REWORK'
                    task['next_action'] = 'Inspect changes and rerun required verification.'
                    changed = True
            if changed:
                state = self.state()
                if state['active_feature'] == feature['feature_id']:
                    active = next(t for t in feature['tasks'] if t['id'] == state['active_task'])
                    state.update(phase=active['status'],next_action=active['next_action'])
                self.save(state,self.event('verification-stale','Invalidated prior completion because evidence no longer matches.',feature=feature['feature_id']),feature)

    def checkpoint(self):
        self.reconcile()
        state = self.state()
        changed = {k:v for k,v in {'fingerprints':self.fingerprints(),'git':self.git(),'revisions':self.revisions(),'graph':graph.status(self.root)}.items() if state[k] != v}
        signature = digest({k:v for k,v in state.items() if k not in {'updated_at','last_checkpoint'}} | changed)
        if not changed and state['last_checkpoint'] and state['last_checkpoint']['signature'] == signature:
            return {'changed':False,'checkpoint':state['last_checkpoint']}
        files = sorted(k for k in set(state['fingerprints'])|set(changed.get('fingerprints',{})) if state['fingerprints'].get(k) != changed.get('fingerprints',state['fingerprints']).get(k))
        state.update(changed)
        state['last_checkpoint'] = {'at':now(),'signature':signature,'event_id':uid()}
        event = self.event('checkpoint','Confirmed current repository state.',changed_files=files,next_action=state['next_action'])
        state['last_checkpoint']['event_id'] = event['id']
        self.save(state,event)
        return {'changed':True,'checkpoint':state['last_checkpoint']}

    def status(self):
        state = self.state()
        from .reporting import task_report
        tasks = []
        for feature in self.features().values():
            for task in feature['tasks']:
                report = task_report(self,task['id'])
                tasks.append({'id':task['id'],'status':task['status'],'evidence_current':report['verification']['status'] == 'PASS',
                              'regression_required':report['regression_required'],'effective_status':report['effective_status'],
                              'next_action':report['next_action']['message']})
        active = next((t for t in tasks if t['id'] == state['active_task']),None)
        if active: state = {**state,'next_action':active['next_action']}
        return {'state':state,'tasks':tasks,'observed_changes':state['fingerprints'] != self.fingerprints(),
                'pending_transaction':(self.root/'.harness/transaction.json').exists(),'graph':graph.status(self.root),
                'application_ready':self.application_ready(),'notice':'Last confirmed checkpoint, not exact live progress. Run resume to reconcile.'}

    def verify(self, task_id, regression=False):
        self.reconcile()
        self.validate()
        state = self.state()
        if state['uncertain_outcome']: raise HarnessError('Resolve uncertain operation before verification')
        feature,task = self.task(task_id)
        if regression:
            if not self.completed(task): raise HarnessError('Regression requires valid historical DONE completion')
        elif task['status'] != 'IMPLEMENTED': raise HarnessError('Verification requires IMPLEMENTED status')
        self.ready(feature,task)
        if not regression: verification.scope_changes(self,task)
        if feature['kind'] == 'application':
            index_context.ensure(self.root)
        mapping = verification.acceptance(task)
        closure = self.check_closure(task)
        cfg = read(self.root/'.harness/checks.json')
        start_binding = self.binding()
        operation_id = uid()
        state['active_operation'] = {'id':operation_id,'kind':'verification','task':task_id,'started_at':now(),'pid':os.getpid()}
        self.save(state,self.event('operation-start','Starting required verification.',task_id,feature['feature_id']))
        results = []
        for name in sorted({name for t in closure for name in t['required_checks']}):
            check = cfg['checks'][name]
            result = self.run_check(name,check)
            results.append(result)
            state = self.state()
            self.save(state,self.event('check-finished',f'{name}: {result["result"]}',task_id,feature['feature_id'],
                      commands=[{'argv':redact(result['command']),'exit_code':result['exit_code']}],result=result['result']))
        if self.binding() != start_binding:
            results.append({'check':'stable-inputs','result':'FAIL','command':[],'exit_code':None,'summary':'Inputs changed during checks; rerun after inspecting the changes.'})
        passed = {r['check'] for r in results if r['result'] == 'PASS'}
        acceptance_results = [{'criterion':m['criterion'], 'checks':m['checks'],
                               'result':'PASS' if set(m['checks']) <= passed else 'FAIL'} for m in mapping]
        overall = 'PASS' if results and all(r['result']=='PASS' for r in results) else 'FAIL'
        ref = f'.harness/evidence/{operation_id}.json'
        evidence = {'schema_version':1,'id':operation_id,'task_id':task_id,'created_at':now(),'fingerprint':start_binding,
                    'revisions':self.revisions(),'environment':self.environment(),'check_config_hash':digest(cfg),'results':results,'result':overall,
                    'definition_hash':self.definition(task), 'checked_tasks':[t['id'] for t in closure],
                    'acceptance_results':acceptance_results}
        evidence = redact(evidence)
        self.schema('evidence',evidence)
        if regression: task.setdefault('regression_evidence',[]).append(ref)
        else: task['evidence'].append(ref)
        state = self.state()
        state.update(active_operation=None,latest_verification=[ref])
        self.save(state,self.event('verification',f'Required verification: {overall}',task_id,feature['feature_id'],result=overall,evidence=[ref]),feature,{ref:evidence})
        self.checkpoint()
        return evidence

    def run_check(self, name, check):
        result = {'check':name,'result':'NOT_RUN','command':check['argv'],'exit_code':None,'summary':''}
        if not check['approved'] or not check['approval_reference']:
            result['summary'] = 'Execution configuration has no approval; command was not run.'
            return result
        if check['kind'] == 'builtin':
            try:
                if name == 'harness-validate': self.validate()
                elif name == 'graph-freshness':
                    if graph.status(self.root)['freshness'] != 'fresh': raise HarnessError('Graph stale/unavailable; update or explicitly revise the approved check plan.')
                elif name == 'demo-doc':
                    text = (self.root/'docs/DEMO.md').read_text()
                    if 'resume' not in text or 'checkpoint' not in text: raise HarnessError('Demo must explain checkpoint and resume')
                else: raise HarnessError('Unknown builtin check')
                result.update(result='PASS',exit_code=0,summary='Builtin assertions passed.')
            except (HarnessError,OSError) as exc:
                result.update(result='FAIL',exit_code=1,summary=str(exc))
            return result
        if not check['approved'] or not check['approval_reference']:
            result['summary'] = 'Execution configuration has no approval; command was not run.'
            return result
        if not check['argv']:
            result.update(result='BLOCKED',summary='Empty command configuration')
            return result
        # No shell; minimal inherited environment. No secrets or full environment logging.
        env = {k:os.environ[k] for k in ['PATH','HOME','TMPDIR','LANG','SYSTEMROOT'] if k in os.environ}
        env['PYTHONDONTWRITEBYTECODE']='1'
        argv = [sys.executable if v=='{python}' else v for v in check['argv']]
        try:
            with tempfile.TemporaryFile() as output:
                process = subprocess.Popen(argv,cwd=self.root,env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
                timed_out = False
                try: code = process.wait(timeout=check['timeout_seconds'])
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid,signal.SIGKILL)
                    code = process.wait()
                output.seek(0)
                log_ref = f'.harness/evidence/logs/{uid()}.log'
                log_path = safe_path(self.root,log_ref); log_path.parent.mkdir(parents=True,exist_ok=True)
                with log_path.open('w') as log:
                    for line in output:
                        log.write(redact(line.decode(errors='replace')))
                summary = log_path.read_text()[-4096:]
                result['log'] = log_ref
                result['log_hash'] = digest(log_path.read_text())
                result.update(result='BLOCKED' if timed_out else 'PASS' if code==0 else 'FAIL',exit_code=code,
                              summary=('Timeout; process group killed. ' if timed_out else '')+summary)
        except OSError as exc:
            result.update(result='BLOCKED',summary=redact(str(exc)))
        return result

    def approve(self, task_id, kind, by, reference):
        self.reconcile()
        feature,task = self.task(task_id)
        path = safe_path(self.root,reference)
        content = path.read_text()
        if not content.strip(): raise HarnessError('Approval/review reference is empty')
        if kind == 'review':
            if task['status'] != 'VERIFIED' or not self.current_evidence(task):
                raise HarnessError('Review requires VERIFIED with current PASS evidence')
            verification.review(self,task,content)
        if kind in {'workflow-plan','plan'} and task.get('workflow'):
            fingerprint = workflow.decision_binding(self,feature,task)
        else:
            fingerprint = self.binding()
        if task.get('workflow') and kind == 'developer' and (task['status'] != 'VERIFIED' or not self.current_evidence(task)):
            raise HarnessError('Final developer approval requires current VERIFIED evidence')
        if task.get('workflow') and kind == 'developer' and not workflow.current_approval(self,task,'review',self.binding()):
            raise HarnessError('Final developer approval requires current review first')
        task['approvals'][kind] = {'by':by,'at':now(),'reference':reference,'reference_hash':digest(content),'fingerprint':fingerprint}
        self.save(self.state(),self.event('approval-recorded',f'Recorded {kind} by {by}; identity is not authenticated.',task_id,feature['feature_id']),feature)
        return {'recorded':kind,'limitation':'Agent-writable record; not authenticated approval or independent proof.'}

    def note(self, kind, message, next_action=None):
        state = self.state()
        message = redact(message)
        if kind == 'blocker': state['blockers'].append(message)
        if kind == 'decision': state['pending_decisions'].append(message)
        if kind == 'resolve':
            state['blockers'] = [x for x in state['blockers'] if x != message]
            state['pending_decisions'] = [x for x in state['pending_decisions'] if x != message]
        if next_action: state['next_action'] = redact(next_action)
        self.save(state,self.event(kind,message,state['active_task'],state['active_feature'],next_action=state['next_action']))
        self.checkpoint()
        return {'recorded':True}

    def recovery_acknowledge(self, note):
        self.reconcile()
        state = self.state()
        if not state['uncertain_outcome']: raise HarnessError('No uncertain operation to acknowledge')
        state['uncertain_outcome'] = None
        state['blockers'] = [x for x in state['blockers'] if not x.startswith('Interrupted operation:')]
        state['next_action'] = 'Inspect task status and rerun incomplete checks when safe.'
        self.save(state,self.event('recovery-acknowledged',redact(note)))
        self.checkpoint()
        return {'result':'PASS'}

    def engineering_log(self):
        lines = ['# Engineering log','','Generated from observable journal events. No claim of developer understanding or independent attestation.','']
        for event in events(self.root):
            lines += [f"- {event['timestamp']} `{event['type']}`: {event['summary']} Result: {event['result']}. Evidence: {', '.join(event['evidence']) or 'journal event '+event['id']}."]
        target = self.root/'docs/ENGINEERING_LOG.md'
        content = '\n'.join(lines)+'\n'
        if not target.exists() or target.read_text() != content: target.write_text(content)
        return {'path':'docs/ENGINEERING_LOG.md','events':len(events(self.root))}
