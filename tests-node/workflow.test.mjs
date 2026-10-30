import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { spawnSync } from 'node:child_process';
import { prepare, install } from '../dist/install.js';
import { execute } from '../dist/engine.js';

for (const agent of ['codex','copilot']) test(`${agent}: installed advisor, combined confirmation, compact and JSON reports`, t => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'harness-adaptive-')));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  install(root,prepare(root,{agent},true));
  const dir=path.join(root,'specs','small');fs.mkdirSync(dir,{recursive:true});
  const f=JSON.parse(fs.readFileSync(path.join(root,'templates/feature/tasks.json'),'utf8'));
  f.feature_id='small';f.kind='harness';
  const task=f.tasks[0];
  Object.assign(task,{id:'SMALL-001',outcome:'Improve local formatting',risk:'low',scope:['docs/sample.md'],requirements:['REQ-001'],required_checks:['harness-validate'],approval_requirements:[]});
  task.acceptance_checks=task.acceptance_criteria.map(criterion=>({criterion,checks:task.required_checks}));
  fs.writeFileSync(path.join(dir,'tasks.json'),JSON.stringify(f));
  for (const file of ['spec.md','plan.md']) fs.writeFileSync(path.join(dir,file),'Status: APPROVED\nRevision: 1\nApproval: simulated fixture consent\nTech-Spec-Revision: 0\nArchitecture-Revision: 0\nREQ-001: Improve local formatting and verify it.\n');
  fs.writeFileSync(path.join(root,'docs/sample.md'),'Small local format example.\n');
  fs.writeFileSync(path.join(root,'.harness/facts.json'),JSON.stringify({critical_risk:false,critical_unknowns:[],unknowns:[],public_api:false,architecture_change:false,components:1,inspected:['docs/sample.md'],agent}));
  fs.writeFileSync(path.join(root,'.harness/consent.txt'),'Simulated fixture developer approves FAST and displayed plan.');
  assert.equal(execute(root,['workflow','assess','SMALL-001','--facts','.harness/facts.json']).data.recommended,'FAST');
  assert.notEqual(execute(root,['task','start','SMALL-001']).exitCode,0);
  const cli=path.resolve('dist/cli.js');
  const noninteractive=spawnSync(process.execPath,[cli,'workflow','select','SMALL-001','--by','fixture','--target',root],{encoding:'utf8'});
  assert.notEqual(noninteractive.status,0);assert.match(noninteractive.stderr,/terminal/);
  assert.equal(execute(root,['workflow','confirm','SMALL-001','--profile','FAST','--by','fixture','--reference','.harness/consent.txt']).exitCode,0);
  assert.equal(execute(root,['task','start','SMALL-001']).exitCode,0);
  const report=spawnSync(process.execPath,[cli,'status','SMALL-001','--target',root],{encoding:'utf8'});
  assert.equal(report.status,0,report.stderr);assert.match(report.stdout,/Next action:/);assert.match(report.stdout,/FAST/);assert.ok(report.stdout.includes(root));
  const structured=spawnSync(process.execPath,[cli,'status','SMALL-001','--target',root,'--json'],{encoding:'utf8'});
  assert.equal(JSON.parse(structured.stdout).data.tasks[0].status,'IN_PROGRESS');
  assert.match(execute(root,['status','SMALL-001','--format','markdown']).data.text,/# AI Engineering Harness/);
});

for (const agent of ['codex', 'copilot', 'copilot-ide', 'codex,copilot', 'codex,copilot-ide']) {
  test(`${agent}: generated instructions keep Adaptive separate from installed OpenSpec`, t => {
    const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'harness-routing-')));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    fs.writeFileSync(path.join(root, 'AGENTS.md'), '# Company rules\nRetain local requirements.\n');
    install(root, prepare(root, { agent }, true));
    const instructions = fs.readFileSync(path.join(root, 'AGENTS.md'), 'utf8');
    assert.match(instructions, /Company rules/);
    assert.match(instructions, /Python Engine owns task workflow policy and OpenSpec requirements/);
    assert.match(instructions, /workflow assess TASK-ID --facts FILE/);
    assert.match(instructions, /wait for explicit developer confirmation/);
    assert.match(instructions, /FAST\/STANDARD.*without a task OpenSpec change unless linked requirements or project policy require it/);
    assert.match(instructions, /STRICT retains required OpenSpec sources and all quality gates/);
    assert.match(instructions, /separate final developer approval after VERIFIED and before DONE/);
    assert.doesNotMatch(instructions, /Use OpenSpec as the feature requirements source/);
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(root, '.harness/workflow-policy.json'))), {experience:{version:1,mode:'compact'}});
    const task = JSON.parse(fs.readFileSync(path.join(root, 'templates/feature/tasks.json'))).tasks[0];
    assert.equal(task.workflow_required, true);
    if (agent.includes('copilot')) {
      const copilot = fs.readFileSync(path.join(root, '.github/copilot-instructions.md'), 'utf8');
      const policy = instructions.split('\n').filter(line => /^(The Python Engine|FAST\/STANDARD|Keep readiness)/.test(line));
      for (const line of policy) assert.ok(copilot.includes(line));
      assert.match(copilot, /When OpenSpec is required, use official OpenSpec/);
    }
    install(root, prepare(root, { agent }, true));
    assert.equal(fs.readFileSync(path.join(root, 'AGENTS.md'), 'utf8'), instructions);
    const changed = instructions.replace('Never claim checks passed without execution evidence.', 'Company checks must retain full execution evidence.');
    fs.writeFileSync(path.join(root, 'AGENTS.md'), changed);
    const changes = prepare(root, { agent }, true);
    assert.equal(changes.find(c => c.path === 'AGENTS.md').action, 'conflict');
    assert.equal(fs.readFileSync(path.join(root, 'AGENTS.md'), 'utf8'), changed);
  });
}
