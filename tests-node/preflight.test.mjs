import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { executionPreflight, checkedAgentLaunch } from '../dist/doctor.js';
import { runCopilot } from '../dist/copilot.js';
const help='--prompt --output-format --allow-tool --deny-tool --no-auto-update --disallow-temp-dir --disable-builtin-mcps --no-bash-env';
function fixture(t) {
  const cwd=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'harness-preflight-')));
  t.after(()=>fs.rmSync(cwd,{recursive:true,force:true}));
  const file=path.join(cwd,'agent.cjs');
  fs.writeFileSync(file,`if(process.argv.includes('--version')) console.log(process.env.AGENT_VERSION || 'codex-cli 1.0'); else if(process.argv.includes('--help')) console.log(${JSON.stringify(help+' --json --sandbox --cd --ignore-user-config')}); else {require('node:fs').writeFileSync('paid-spawn','bad');console.log(JSON.stringify({type:'result',exitCode:0}));}`);
  return {cwd,agent:'codex',command:{file:process.execPath,prefix:[file]},env:{PATH:'',SHELL:'/bin/sh',HOME:cwd},shell:{file:'/bin/sh',login:false},ignoreUserConfig:true};
}
function tool(o,name,version) {
  fs.writeFileSync(path.join(o.cwd,name),`#!${process.execPath}\nconsole.log(${JSON.stringify(version)})`,{mode:0o755});
}
function check(r,id) {return r.checks.find(c=>c.id===id);}
function installed(o) {
  // Use the actual Python engine to resolve existing instruction requirements.
  fs.cpSync('harnesslib',path.join(o.cwd,'harnesslib'),{recursive:true});
  fs.cpSync('schemas',path.join(o.cwd,'schemas'),{recursive:true});
  fs.mkdirSync(path.join(o.cwd,'specs'));
  fs.writeFileSync(path.join(o.cwd,'AGENTS.md'),'Before discovery: ./harness indexes ensure');
  o.env.HARNESS_PYTHON=process.env.HARNESS_PYTHON || spawnSync('python3',['-c','import sys; print(sys.executable)'],{encoding:'utf8'}).stdout.trim();
}
test('child PATH wins over parent; missing optional tools allow repository search fallback',t=>{
  const o=fixture(t);tool(o,'rg','ripgrep 14.0');o.env.PATH=o.cwd;
  const r=executionPreflight(o);
  assert.equal(r.status,'WARN'); assert.equal(check(r,'codegraph-cli').requirement,'OPTIONAL');
  assert.equal(check(r,'codegraph-cli').status,'WARN');assert.equal(check(r,'repository-search').status,'PASS');
  assert.equal(checkedAgentLaunch(o,()=>42),42);
  tool(o,'codegraph','1.6.2'); assert.equal(check(executionPreflight(o),'codegraph-cli').status,'PASS');
  o.env.PATH=''; assert.equal(check(executionPreflight(o),'codegraph-cli').status,'WARN');
});
test('required navigation and version failures prevent paid launch, even with available MCP',t=>{
  const o=fixture(t); installed(o); o.mcpProbe=()=>({server:'codegraph',available:true,tools:['query']});
  const r=executionPreflight(o);assert.equal(check(r,'codegraph-mcp').status,'PASS');
  assert.equal(check(r,'codegraph-cli').requirement,'REQUIRED');assert.equal(r.status,'FAIL');
  let spawns=0; assert.throws(()=>checkedAgentLaunch(o,()=>spawns++),/preflight failed/); assert.equal(spawns,0);
  o.env.PATH=o.cwd;tool(o,'codegraph','0.0.1');tool(o,'graphify','graphify 0.9.27');
  assert.equal(check(executionPreflight(o),'codegraph-cli').status,'FAIL');
  tool(o,'codegraph','1.6.2');assert.equal(check(executionPreflight(o),'codegraph-cli').status,'PASS');
});
test('agent shell PATH transformation is probed rather than assumed',t=>{
  const o=fixture(t);tool(o,'codegraph','1.6.2');o.env.PATH=o.cwd;
  const shell=path.join(o.cwd,'shell');
  fs.writeFileSync(shell,'#!/bin/sh\nPATH=/missing\nexport PATH\nexec /bin/sh "$@"\n',{mode:0o755});
  o.shell={file:shell,login:false};assert.equal(check(executionPreflight(o),'codegraph-cli').status,'WARN');
});
test('MCP configured is not available, disabled wins, required unavailable integration blocks',t=>{
  const o=fixture(t); fs.mkdirSync(path.join(o.cwd,'.codex'));
  const config=path.join(o.cwd,'.codex/config.toml');
  fs.writeFileSync(config,'[mcp_servers.codegraph]\ncommand="not-launched"\nrequired=true\n');
  assert.equal(check(executionPreflight(o),'codegraph-mcp').status,'FAIL');
  o.mcpProbe=()=>({server:'codegraph',available:true,tools:['query']});assert.equal(check(executionPreflight(o),'codegraph-mcp').status,'PASS');
  fs.writeFileSync(config,'[mcp_servers.codegraph]\nenabled=false\n');
  assert.match(check(executionPreflight(o),'codegraph-mcp').message,/disabled/);
});
test('generic required MCP needs an observed read-only host capability',t=>{
  const o=fixture(t);fs.mkdirSync(path.join(o.cwd,'.codex'));
  fs.writeFileSync(path.join(o.cwd,'.codex/config.toml'),'[mcp_servers.contracts]\nrequired=true\ncommand="not-launched"\n');
  assert.equal(check(executionPreflight(o),'required-mcp:contracts').status,'FAIL');
  o.mcpInventory=()=>[{server:'contracts',available:true,readOnlyTools:[]}];
  assert.equal(check(executionPreflight(o),'required-mcp:contracts').status,'FAIL');
  o.mcpInventory=()=>[{server:'contracts',available:true,readOnlyTools:['read_contract']}];
  assert.equal(check(executionPreflight(o),'required-mcp:contracts').status,'PASS');
  o.mcpInventory=()=>[{server:'contracts',available:true,readOnlyTools:['read_contract']},{server:'contracts',available:true,readOnlyTools:['read_contract']}];
  assert.equal(check(executionPreflight(o),'host-mcp-inventory').status,'WARN');
  assert.equal(check(executionPreflight(o),'required-mcp:contracts').status,'FAIL');
});
test('ignore user config and unsupported environment policies are respected',t=>{
  const o=fixture(t);const home=path.join(o.cwd,'user');fs.mkdirSync(path.join(home,'.codex'),{recursive:true});o.env.HOME=home;
  fs.writeFileSync(path.join(home,'.codex/config.toml'),'[shell_environment_policy]\ninherit="none"\n');
  assert.equal(check(executionPreflight(o),'agent-settings').status,'PASS');
  o.ignoreUserConfig=false;assert.equal(check(executionPreflight(o),'agent-settings').status,'FAIL');
});
test('Copilot probes sanitized supplied environment and does not launch on required failure',async t=>{
  const o=fixture(t);o.agent='copilot';o.env.AGENT_VERSION='GitHub Copilot CLI 1.0.test';
  assert.equal((await runCopilot({...o,prompt:'fixture'})).status,'PASS');
  fs.unlinkSync(path.join(o.cwd,'paid-spawn')); installed(o);
  const r=await runCopilot({...o,prompt:'must not launch'});assert.equal(r.status,'BLOCKED');
  assert.equal(fs.existsSync(path.join(o.cwd,'paid-spawn')),false);
});
test('incompatible agent capability fails and IDE-only needs no CLI',t=>{
  const o=fixture(t);o.env.AGENT_VERSION='not an agent';assert.equal(check(executionPreflight(o),'agent-cli').status,'FAIL');
  o.agent='copilot-ide';const r=executionPreflight(o);assert.equal(r.status,'PASS');assert.equal(r.checks[0].requirement,'NOT_APPLICABLE');
  assert.throws(()=>checkedAgentLaunch(o,()=>assert.fail()),/IDE-only/);
});

test('broken managed tool must not fall back to compatible PATH executable',t=>{
  const o=fixture(t);installed(o);o.env.PATH=o.cwd;tool(o,'codegraph','1.6.2');
  const local=path.join(o.cwd,'.harness/tools/codegraph/node_modules/.bin');fs.mkdirSync(local,{recursive:true});
  fs.symlinkSync('/missing/codegraph',path.join(local,'codegraph'));
  assert.equal(check(executionPreflight(o),'codegraph-cli').status,'FAIL');
});
test('MCP effective disabled override and unrelated host tools are not treated as available',t=>{
  const o=fixture(t);o.ignoreUserConfig=false;const user=path.join(o.cwd,'home');o.env.HOME=user;
  fs.mkdirSync(path.join(user,'.codex'),{recursive:true});fs.mkdirSync(path.join(o.cwd,'.codex'));
  fs.writeFileSync(path.join(user,'.codex/config.toml'),'[mcp_servers.codegraph]\nrequired=true\n');
  fs.writeFileSync(path.join(o.cwd,'.codex/config.toml'),'[mcp_servers.codegraph]\nenabled=false\n');
  assert.equal(check(executionPreflight(o),'codegraph-mcp').requirement,'OPTIONAL');
  fs.writeFileSync(path.join(o.cwd,'.codex/config.toml'),'');
  o.mcpProbe=()=>({server:'unrelated',available:true,tools:['query']});
  assert.equal(check(executionPreflight(o),'codegraph-mcp').status,'FAIL');
});

test('selected required check executable missing in child environment fails before spawn',t=>{
  const o=fixture(t);installed(o);
  fs.writeFileSync(path.join(o.cwd,'AGENTS.md'),'No navigation CLI requirement for this fixture.');
  const feature=JSON.parse(fs.readFileSync('templates/feature/tasks.json'));
  feature.feature_id='preflight';feature.kind='harness';feature.tasks[0].required_checks=['node-test'];
  fs.mkdirSync(path.join(o.cwd,'specs/preflight'));fs.mkdirSync(path.join(o.cwd,'.harness'),{recursive:true});
  fs.writeFileSync(path.join(o.cwd,'specs/preflight/tasks.json'),JSON.stringify(feature));
  fs.writeFileSync(path.join(o.cwd,'.harness/checks.json'),JSON.stringify({checks:{'node-test':{kind:'command',argv:['node','--test']}}}));
  const r=executionPreflight(o);
  assert.equal(check(r,'check-runtime:node-test').status,'FAIL');
  let spawns=0;assert.throws(()=>checkedAgentLaunch(o,()=>spawns++));assert.equal(spawns,0);
});
test('symlinked managed tool directory is rejected instead of passing PATH fallback',t=>{
  const o=fixture(t);installed(o);tool(o,'codegraph','1.6.2');o.env.PATH=o.cwd;
  const external=path.join(o.cwd,'external');fs.mkdirSync(path.join(external,'node_modules/.bin'),{recursive:true});
  fs.copyFileSync(path.join(o.cwd,'codegraph'),path.join(external,'node_modules/.bin/codegraph'));
  fs.mkdirSync(path.join(o.cwd,'.harness/tools'),{recursive:true});fs.symlinkSync(external,path.join(o.cwd,'.harness/tools/codegraph'));
  assert.equal(check(executionPreflight(o),'codegraph-cli').status,'FAIL');
});

test('empty symlinked managed directory cannot fall through to PATH',t=>{
  const o=fixture(t);installed(o);tool(o,'codegraph','1.6.2');o.env.PATH=o.cwd;
  const external=path.join(o.cwd,'empty');fs.mkdirSync(external);
  fs.mkdirSync(path.join(o.cwd,'.harness/tools'),{recursive:true});fs.symlinkSync(external,path.join(o.cwd,'.harness/tools/codegraph'));
  assert.equal(check(executionPreflight(o),'codegraph-cli').status,'FAIL');
});
test('application runtime versions are not replaced by Harness runtime pins',t=>{
  const o=fixture(t);installed(o);fs.writeFileSync(path.join(o.cwd,'AGENTS.md'),'No graph requirement.');
  const feature=JSON.parse(fs.readFileSync('templates/feature/tasks.json'));feature.feature_id='preflight';feature.kind='harness';feature.tasks[0].required_checks=['app-python'];
  fs.mkdirSync(path.join(o.cwd,'specs/preflight'));fs.mkdirSync(path.join(o.cwd,'.harness'),{recursive:true});
  fs.writeFileSync(path.join(o.cwd,'specs/preflight/tasks.json'),JSON.stringify(feature));
  fs.writeFileSync(path.join(o.cwd,'.harness/checks.json'),JSON.stringify({checks:{'app-python':{kind:'command',argv:['python3','-m','unittest']}}}));
  tool(o,'python3','Python 3.10.0');o.env.PATH=o.cwd;
  assert.equal(check(executionPreflight(o),'check-runtime:app-python').status,'PASS');
});

test('unknown engine requirements never downgrade navigation to optional',t=>{
  const o=fixture(t);installed(o);o.env.HARNESS_PYTHON='/missing/python';
  const r=executionPreflight(o);
  assert.equal(check(r,'execution-requirements').status,'FAIL');
  assert.equal(check(r,'codegraph-cli').requirement,'REQUIRED');
  assert.equal(check(r,'graphify-cli').requirement,'REQUIRED');
  let spawns=0;assert.throws(()=>checkedAgentLaunch(o,()=>spawns++));assert.equal(spawns,0);
});
