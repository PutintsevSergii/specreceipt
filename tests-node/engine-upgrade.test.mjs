import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import { prepare, install } from "../dist/install.js";
import { execute, request, resolveEngine, ENGINE_VERSION } from "../dist/engine.js";
import { prepareUpgrade, upgrade, mergeText } from "../dist/upgrade.js";
import { migrate } from "../dist/migrations.js";
import { manifest, read, hash, recover, walk } from "../dist/filesystem.js";
import { CONFIG_PATH, MANIFEST_PATH, DEFAULTS, VERSION } from "../dist/core.js";
import { synchronize, version, registryDecision, publishContext, requirePublishingNpm } from '../scripts/release.mjs';
import YAML from 'yaml';

function releaseFixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'release-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  fs.mkdirSync(path.join(root,'src'));
  fs.mkdirSync(path.join(root,'harnesslib'));
  const pkg = {name:'specreceipt', version:'0.4.1', repository:{url:'git+https://github.com/PutintsevSergii/specreceipt.git'},publishConfig:{registry:'https://registry.npmjs.org/'}};
  fs.writeFileSync(path.join(root,'package.json'),JSON.stringify(pkg));
  fs.writeFileSync(path.join(root,'package-lock.json'),JSON.stringify({name:pkg.name,version:'0.4.0',packages:{'':{name:pkg.name,version:'0.4.0'},'node_modules/fixture':{version:'1.2.3'}}}));
  fs.writeFileSync(path.join(root,'src/core.ts'),'export const VERSION = "0.4.0";\n');
  fs.writeFileSync(path.join(root,'src/engine.ts'),'export const ENGINE_VERSION = "0.4.0";\nexport const PROTOCOL_VERSION = 1;\n');
  fs.writeFileSync(path.join(root,'harnesslib/protocol.py'),"ENGINE_VERSION = '0.4.0'\nPROTOCOL_VERSION = 1\n");
  return {root,pkg};
}

test('release: one configuration value synchronizes consumers and lock metadata idempotently',t=>{
  const {root}=releaseFixture(t);
  assert.throws(()=>synchronize(root,true),/drift/);
  assert.equal(synchronize(root).changed.length,4);
  assert.deepEqual(synchronize(root).changed,[]);
  assert.equal(synchronize(root,true).version,'0.4.1');
  assert.match(fs.readFileSync(path.join(root,'harnesslib/protocol.py'),'utf8'),/PROTOCOL_VERSION = 1/);
  const lock=JSON.parse(fs.readFileSync(path.join(root,'package-lock.json')));
  assert.equal(lock.packages[''].version,'0.4.1');
  assert.equal(lock.packages['node_modules/fixture'].version,'1.2.3');
});

test('release: malformed markers and lock identity fail before any writes',t=>{
  const {root}=releaseFixture(t);
  const before=fs.readFileSync(path.join(root,'src/core.ts'),'utf8');
  fs.appendFileSync(path.join(root,'src/engine.ts'),'export const ENGINE_VERSION = "duplicate";\n');
  assert.throws(()=>synchronize(root),/exactly one/);
  assert.equal(fs.readFileSync(path.join(root,'src/core.ts'),'utf8'),before);
  fs.writeFileSync(path.join(root,'src/engine.ts'),'export const ENGINE_VERSION = "0.4.0";\n');
  fs.writeFileSync(path.join(root,'package-lock.json'),JSON.stringify({name:'another',packages:{}}));
  assert.throws(()=>synchronize(root),/identity/);
  assert.equal(fs.readFileSync(path.join(root,'src/core.ts'),'utf8'),before);
});

test('release: stable version and compatible npm validation rejects invalid inputs',()=>{
  for(const value of ['1.2','v1.2.3','01.2.3','1.2.3-next',null,'1.2.3\ninject','9007199254740992.0.0']) assert.throws(()=>version(value));
  assert.equal(version('0.4.1'),'0.4.1');
  for(const value of ['10.9.9','11.5.0','11.5.1-next']) assert.throws(()=>requirePublishingNpm(value));
  requirePublishingNpm('11.5.1');requirePublishingNpm('12.0.0');
});

test('release: publication requires own push/main and an exact current verified SHA',()=>{
  const sha='a'.repeat(40),repo='PutintsevSergii/specreceipt';
  assert.equal(publishContext('push','refs/heads/main',repo,repo,sha,sha),true);
  for(const args of [
    ['pull_request','refs/heads/main',repo,repo,sha,sha],
    ['workflow_dispatch','refs/heads/main',repo,repo,sha,sha],
    ['push','refs/heads/feature',repo,repo,sha,sha],
    ['push','refs/heads/main','fork/repo',repo,sha,sha],
    ['push','refs/heads/main',repo,repo,sha,'b'.repeat(40)],
    ['push','refs/heads/main',repo,repo,'invalid','invalid']]) assert.equal(publishContext(...args),false);
});

function npmMetadata(current=false) {
  return {name:'specreceipt',versions:{'0.3.1':{name:'specreceipt',version:'0.3.1'},...(current?{'0.4.1':{name:'specreceipt',version:'0.4.1'}}:{})},'dist-tags':{latest:'0.3.1'}};
}

test('release: existing version skips while a greater new version requests publication',async t=>{
  const {pkg}=releaseFixture(t);
  for(const exists of [false,true]) {
    const result=await registryDecision(pkg,async(url,options)=>{
      assert.equal(url,'https://registry.npmjs.org/specreceipt');assert.ok(options.signal);
      return {ok:true,json:async()=>npmMetadata(exists)};
    });
    assert.equal(result.publish,!exists);assert.equal(result.version,'0.4.1');
  }
});

test('release: registry denial, absence, outages and network errors never request publication',async t=>{
  const {pkg}=releaseFixture(t);
  for(const status of [401,403,404,429,500,503]) await assert.rejects(()=>registryDecision(pkg,async()=>({ok:false,status})),/HTTP/);
  await assert.rejects(()=>registryDecision(pkg,async()=>{throw Error('offline')}),/offline/);
  await assert.rejects(()=>registryDecision(pkg,async()=>({ok:true,json:async()=>{throw Error('bad JSON')}})),/bad JSON/);
});

test('release: invalid metadata, downgrade and mismatched package identity fail closed',async t=>{
  const {pkg}=releaseFixture(t);
  for(const data of [{}, {name:'another',versions:{}}, {...npmMetadata(),versions:[]}, {...npmMetadata(),'dist-tags':{latest:'9.0.0'},versions:{'9.0.0':{name:'specreceipt',version:'9.0.0'}}}]) {
    await assert.rejects(()=>registryDecision(pkg,async()=>({ok:true,json:async()=>data})));
  }
  for(const bad of [{...pkg,name:'other'},{...pkg,private:true},{...pkg,publishConfig:{registry:'https://untrusted.example'}},{...pkg,repository:{url:'wrong'}}]) {
    await assert.rejects(()=>registryDecision(bad,async()=>{throw Error('must not fetch')}),/Unexpected/);
  }
});

test('release: workflow connects the verified SHA gate to job-scoped OIDC publication',()=>{
  const workflow=YAML.parse(fs.readFileSync('.github/workflows/verify.yml','utf8'));
  const job=workflow.jobs.publish;
  assert.equal(job.needs,'required');
  assert.equal(job.permissions['id-token'],'write');
  assert.equal(workflow.permissions['id-token'],undefined);
  assert.match(job.if,/github.event_name == 'push'/);
  assert.match(job.if,/refs\/heads\/main/);
  assert.match(job.if,/PutintsevSergii\/specreceipt/);
  assert.equal(job.steps[0].with.ref,'${{ github.sha }}');
  assert.equal(job.steps[0].with['persist-credentials'],false);
  assert.equal(job.concurrency['cancel-in-progress'],false);
  assert.match(job.steps.find(s=>s.name==='Publish through npm Trusted Publishing').run,/\.tgz.*--access public.*--provenance/);
  assert.equal(job.steps.find(s=>s.name==='Publish through npm Trusted Publishing').if,"steps.release.outputs.publish == 'true'");
  assert.ok(workflow.jobs.python.steps.some(s=>s.run==='node scripts/release.mjs sync'));
  assert.ok(workflow.jobs.python.steps.some(s=>s.run==='python -B -X utf8 harness init'));
});

test('Windows engine identity accepts native drive and directory casing', {skip:process.platform!=='win32'},()=>{
  const root=fs.realpathSync.native(process.cwd());
  for(const alias of [root[0].toLowerCase()+root.slice(1),root.toUpperCase()]) {
    const result=request(alias,['contract'],alias);
    assert.equal(fs.realpathSync.native(result.target),root);
    assert.equal(fs.realpathSync.native(result.cwd),root);
    assert.equal(fs.realpathSync.native(result.engineRoot),root);
  }
});
const cli = path.resolve("dist/cli.js");
function fixture(t) {
  const root = fs.realpathSync.native(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-contract-")),
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  // No OpenSpec mock is used: omit generation in this engine-only fixture explicitly.
  install(root, prepare(root, {}, true));
  return root;
}
const snapshot = (root) =>
  Object.fromEntries(walk(root).map((p) => [p, read(root, p)]));
test("Python owns initial state and setup event; installed CLI delegates help, errors and gates", (t) => {
  const root = fixture(t);
  const state = JSON.parse(read(root, ".harness/state.json"));
  assert.equal(state.phase, "SETUP");
  assert.match(
    read(root, ".harness/events.jsonl"),
    /Initialized generic harness/,
  );
  assert.equal(resolveEngine(root).engineRoot, root);
  const before = snapshot(root);
  assert.equal(execute(root, ["validate"]).exitCode, 0);
  assert.match(execute(root, ["task", "--help"]).data.text, /transition/);
  assert.equal(execute(root, ["task", "start", "ABSENT"]).exitCode, 1);
  assert.equal(execute(root, ["run"]).exitCode, 1);
  const p = spawnSync(
    process.execPath,
    [cli, "task", "--help", "--target", root, "--json"],
    { encoding: "utf8" },
  );
  assert.equal(p.status, 0);
  assert.equal(fs.realpathSync.native(JSON.parse(p.stdout).engineRoot), fs.realpathSync.native(root));
  assert.equal(JSON.parse(read(root, ".harness/state.json")).phase, "SETUP");
  // Read-only calls do not modify target files.
  const after = snapshot(root);
  execute(root, ["status"]);
  assert.deepEqual(snapshot(root), after);
});
test("installed engine drift, wrong protocol, missing Python and root injection fail closed", (t) => {
  const root = fixture(t);
  assert.throws(() => request(root, ["--root", "/tmp", "status"]), /mismatch/);
  const prior = process.env.HARNESS_PYTHON;
  process.env.HARNESS_PYTHON = "/missing/python";
  try {
    assert.throws(() => execute(root, ["status"]), /unavailable/);
  } finally {
    if (prior === undefined) delete process.env.HARNESS_PYTHON;
    else process.env.HARNESS_PYTHON = prior;
  }
  const file = path.join(root, MANIFEST_PATH);
  const data = manifest(root);
  data.protocolVersion = 99;
  fs.writeFileSync(file, JSON.stringify(data));
  assert.throws(() => execute(root, ["status"]), /incompatible/);
  data.protocolVersion = 1;
  fs.writeFileSync(file, JSON.stringify(data));
  fs.appendFileSync(path.join(root, "harnesslib/core.py"), "\n# tamper\n");
  assert.throws(() => execute(root, ["status"]), /modified/);
});
test("three-way Git merge covers local-only, remote-only, disjoint, overlap and missing Git", () => {
  const base = "one\ntwo\nthree\nfour\nfive\n";
  assert.equal(mergeText(base, base, "new"), "new");
  assert.equal(mergeText(base, "custom", base), "custom");
  assert.equal(
    mergeText(
      base,
      "ONE\ntwo\nthree\nfour\nfive\n",
      "one\ntwo\nthree\nfour\nFIVE\n",
    ),
    "ONE\ntwo\nthree\nfour\nFIVE\n",
  );
  assert.equal(mergeText(base, "local", "remote"), null);
  const old = process.env.PATH;
  process.env.PATH = "";
  try {
    assert.throws(() => mergeText(base, "local", "remote"), /Git/);
  } finally {
    process.env.PATH = old;
  }
});
test("migration validates both versions, adds defaults, is ordered and idempotent", () => {
  const input = { schemaVersion: 1, ...DEFAULTS };
  const first = migrate(input);
  assert.deepEqual(first.applied, ["product-1-to-2"]);
  assert.equal(first.value.engine.protocolVersion, 1);
  assert.deepEqual(migrate(first.value), { value: first.value, applied: [] });
  assert.throws(() => migrate({ ...input, schemaVersion: 9 }));
  assert.throws(() => migrate({ ...input, secret: "no" }));
});
test("upgrade preserves local Skills, shared rules, OpenSpec and custom files; dry-run and repeat unchanged", (t) => {
  const root = fixture(t);
  const rel = ".agents/skills/discovery/SKILL.md";
  fs.appendFileSync(path.join(root, rel), "\nCompany customization\n");
  fs.appendFileSync(path.join(root, "AGENTS.md"), "\nOutside section\n");
  fs.mkdirSync(path.join(root, "openspec"), { recursive: true });
  fs.writeFileSync(
    path.join(root, "openspec/config.yaml"),
    "schema: customized\n",
  );
  fs.mkdirSync(path.join(root, ".agents/skills/custom"), { recursive: true });
  fs.writeFileSync(
    path.join(root, ".agents/skills/custom/SKILL.md"),
    "private skill",
  );
  const before = snapshot(root),
    changes = prepareUpgrade(root);
  assert.deepEqual(snapshot(root), before);
  assert.ok(!changes.some((c) => c.action === "conflict"));
  upgrade(root, changes);
  assert.match(read(root, rel), /Company customization/);
  assert.match(read(root, "AGENTS.md"), /Outside section/);
  assert.equal(read(root, "openspec/config.yaml"), "schema: customized\n");
  const after = snapshot(root);
  upgrade(root, prepareUpgrade(root));
  assert.deepEqual(snapshot(root), after);
});
for (const previousVersion of ["0.3.0", "0.3.1"]) test(`${previousVersion} installation manifest can upgrade to the current release`, (t) => {
  const root = fixture(t);
  const old = manifest(root);
  old.packageVersion = previousVersion;
  old.engineVersion = previousVersion;
  fs.writeFileSync(path.join(root, MANIFEST_PATH), JSON.stringify(old));
  const changes = prepareUpgrade(root);
  assert.ok(!changes.some((change) => change.action === "conflict"));
  upgrade(root, changes);
  assert.equal(manifest(root).packageVersion, VERSION);
  assert.equal(manifest(root).engineVersion, ENGINE_VERSION);
});
test("legacy missing baseline, local deletion, removed ownership and collisions explicitly conflict", (t) => {
  const root = fixture(t);
  const rel = ".agents/skills/discovery/SKILL.md";
  const data = manifest(root);
  data.schemaVersion = 1;
  data.packageVersion = "0.1.0";
  for (const v of Object.values(data.files)) {
    delete v.baseline;
    delete v.baselineHash;
  }
  fs.writeFileSync(path.join(root, MANIFEST_PATH), JSON.stringify(data));
  fs.appendFileSync(path.join(root, rel), "\ncustom\n");
  assert.equal(
    prepareUpgrade(root).find((c) => c.path === rel).action,
    "conflict",
  );
  fs.unlinkSync(path.join(root, rel));
  assert.match(
    prepareUpgrade(root).find((c) => c.path === rel).reason,
    /deleted/,
  );
  data.files["old-name.md"] = { hash: hash("x"), owner: "harness" };
  fs.writeFileSync(path.join(root, MANIFEST_PATH), JSON.stringify(data));
  assert.match(
    prepareUpgrade(root).find((c) => c.path === "old-name.md").reason,
    /renamed/,
  );
});
test("interrupted upgrade retains backup, recovery restores bytes and retry works", (t) => {
  const root = fixture(t);
  fs.appendFileSync(
    path.join(root, ".agents/skills/discovery/SKILL.md"),
    "\ncustom\n",
  );
  const before = snapshot(root);
  const changes = prepareUpgrade(root);
  assert.throws(() => upgrade(root, changes, 0), /interrupted/);
  recover(root);
  assert.deepEqual(snapshot(root), before);
  upgrade(root, prepareUpgrade(root));
  assert.equal(execute(root, ["validate"]).exitCode, 0);
});
test("postvalidation failure retains journal and protects concurrent edits during recovery", (t) => {
  const root = fixture(t);
  const changes = prepareUpgrade(root);
  const c = changes.find((c) => c.path === "docs/TECH_SPEC.md");
  c.content = "invalid";
  c.action = "update";
  assert.throws(() => upgrade(root, changes), /interrupted/);
  fs.writeFileSync(path.join(root, "docs/TECH_SPEC.md"), "concurrent");
  assert.throws(() => recover(root), /conflict/);
  fs.writeFileSync(path.join(root, "docs/TECH_SPEC.md"), "invalid");
  recover(root);
  assert.equal(execute(root, ["validate"]).exitCode, 0);
});
test("doctor engine cannot import project shadow modules; missing inventory entry is rejected", (t) => {
  const root = fixture(t);
  fs.writeFileSync(
    path.join(root, "subprocess.py"),
    "raise RuntimeError('PROJECT MODULE EXECUTED')\n",
  );
  assert.equal(execute(root, ["validate"]).exitCode, 0);
  const data = manifest(root);
  delete data.files["harnesslib/core.py"];
  fs.writeFileSync(path.join(root, MANIFEST_PATH), JSON.stringify(data));
  assert.throws(() => execute(root, ["validate"]), /inventory/);
});
test("lifecycle writes refuse installer lock and pending recovery, reads still work", (t) => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, ".harness/installation.lock"), "");
  assert.equal(execute(root, ["checkpoint"]).exitCode, 1);
  assert.equal(execute(root, ["validate"]).exitCode, 0);
  fs.unlinkSync(path.join(root, ".harness/installation.lock"));
  fs.writeFileSync(path.join(root, ".harness/installation-pending.json"), "{}");
  assert.equal(execute(root, ["checkpoint"]).exitCode, 1);
});
test("custom runtime upgrade cannot silently claim upstream engine version", (t) => {
  const root = fixture(t);
  fs.appendFileSync(path.join(root, "harnesslib/core.py"), "\n# local fork\n");
  assert.equal(
    prepareUpgrade(root).find((c) => c.path === "harnesslib/core.py").action,
    "conflict",
  );
});
test("interruption after configuration write restores pre-upgrade config and manifest", (t) => {
  const root = fixture(t);
  fs.writeFileSync(
    path.join(root, CONFIG_PATH),
    JSON.stringify({ schemaVersion: 1, ...DEFAULTS }) + "\n",
  );
  const before = snapshot(root);
  assert.throws(() => upgrade(root, prepareUpgrade(root), 1), /interrupted/);
  assert.equal(JSON.parse(read(root, CONFIG_PATH)).schemaVersion, 2);
  recover(root);
  assert.deepEqual(snapshot(root), before);
  upgrade(root, prepareUpgrade(root));
  assert.equal(JSON.parse(read(root, CONFIG_PATH)).schemaVersion, 2);
});

test('legacy upgrade without navigation policy retains dual-provider requirements', t => {
  const root=fixture(t);
  fs.unlinkSync(path.join(root,'.harness/navigation.json'));
  const old=manifest(root);
  delete old.files['.harness/navigation.json'];
  old.packageVersion='0.3.1';old.engineVersion='0.3.1';
  fs.writeFileSync(path.join(root,MANIFEST_PATH),JSON.stringify(old));
  upgrade(root,prepareUpgrade(root));
  assert.equal(fs.existsSync(path.join(root,'.harness/navigation.json')),false);
  const requirements=request(root,['doctor','--execution-requirements']);
  assert.equal(requirements.exitCode,0);
  assert.deepEqual(requirements.data.navigation_providers,['codegraph','graphify']);
});
