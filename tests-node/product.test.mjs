import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import {
  selection,
  config,
  plan,
  portablePath,
  BEGIN,
  END,
  mergeAgents,
  health,
} from "../dist/core.js";
import {
  apply,
  recover,
  hash,
  read,
  manifest,
  walk,
} from "../dist/filesystem.js";
import { prepare, install } from "../dist/install.js";
import { doctor } from "../dist/doctor.js";
import { stageOpenSpec, probeOpenSpec, codexBlock, copilotBlock } from "../dist/integrations.js";
const cli = path.resolve("dist/cli.js");
test("installed agent rules require a linked decision before final DONE", () => {
  for (const block of [codexBlock, copilotBlock]) {
    assert.match(block, /approval-package TASK-ID --format markdown/);
    assert.match(block, /linked spec, plan, changed files, current evidence and review/);
    assert.match(block, /if the command blocks, do not ask for DONE/);
  }
});
function fixture(t) {
  const base = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-test-")),
  );
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  return base;
}
function fakeTools(t, base) {
  const bin = path.join(base, "bin");
  fs.mkdirSync(bin);
  const old = process.env.PATH;
  for (const [name, output] of [
    ["codegraph", "1.6.2"],
    ["graphify", "graphify 0.9.27"],
  ]) {
    fs.writeFileSync(
      path.join(bin, name),
      `#!${process.execPath}\nconsole.log(${JSON.stringify(output)});\n`,
      { mode: 0o755 },
    );
  }
  const fake = path.join(bin, "openspec");
  fs.writeFileSync(
    fake,
    `#!${process.execPath}
const fs=require('node:fs');
if(process.argv[2]==='--version')console.log('1.14.3');
else if(process.argv[2]==='init'){
 if(process.argv.slice(2).join(' ')!=='init --tools codex')process.exit(5);
 fs.mkdirSync('openspec',{recursive:true});fs.writeFileSync('openspec/config.yaml','schema: spec-driven\\n');
 fs.mkdirSync('.agents/skills/openspec-propose',{recursive:true});fs.writeFileSync('.agents/skills/openspec-propose/SKILL.md','---\\nname: openspec-propose\\ndescription: Official generated test double\\n---\\n');
}else process.exit(2);
`,
    { mode: 0o755 },
  );
  process.env.PATH = bin + path.delimiter + old;
  t.after(() => (process.env.PATH = old));
  return bin;
}
function snapshot(root) {
  return Object.fromEntries(
    walk(root).map((p) => [
      p,
      fs.readFileSync(path.join(root, p)).toString("base64"),
    ]),
  );
}
test("selection, configuration, paths and shared markers reject invalid inputs", () => {
  assert.equal(selection().agent, "codex");
  assert.throws(() => selection({ agent: "other" }));
  assert.throws(() => config({ schemaVersion: 2 }));
  assert.throws(() =>
    config({ schemaVersion: 1, ...selection(), extra: true }),
  );
  for (const p of ["../outside", "/etc/passwd", "C:\\file", "a//b", "a/./b"])
    assert.throws(() => portablePath(p));
  assert.throws(() => mergeAgents(BEGIN, "block"));
  const block = BEGIN + "\nhello\n" + END;
  assert.equal(
    mergeAgents(mergeAgents("user rules", block), block),
    mergeAgents("user rules", block),
  );
  assert.equal(health([{ status: "PASS" }]), "HEALTHY");
  assert.equal(health([{ status: "FAIL" }]), "UNHEALTHY");
});
test("pure plan detects drift, preserves project content, and supports unchanged upgrades", () => {
  const asset = { path: "owned.txt", content: "new", owner: "harness" };
  assert.equal(
    plan([asset], { "owned.txt": "old" }, null, hash)[0].action,
    "conflict",
  );
  const prev = {
    schemaVersion: 1,
    packageVersion: "0",
    files: { "owned.txt": { hash: hash("old"), owner: "harness" } },
  };
  assert.equal(
    plan([asset], { "owned.txt": "old" }, prev, hash)[0].action,
    "update",
  );
  assert.equal(
    plan(
      [{ ...asset, owner: "project" }],
      { "owned.txt": "custom" },
      null,
      hash,
    )[0].content,
    "custom",
  );
});
test("A/B/D/F/G: install preserves existing Codex project and repeats without drift", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  fs.mkdirSync(root);
  fs.writeFileSync(path.join(root, "AGENTS.md"), "Company rules\n");
  fs.mkdirSync(path.join(root, ".codex"));
  fs.writeFileSync(
    path.join(root, ".codex/config.toml"),
    'model = "existing"\n',
  );
  fs.mkdirSync(path.join(root, ".agents/skills/custom"), { recursive: true });
  fs.writeFileSync(
    path.join(root, ".agents/skills/custom/SKILL.md"),
    "---\nname: custom\ndescription: Company skill\n---\n",
  );
  install(root, prepare(root));
  const before = snapshot(root);
  assert.match(read(root, "AGENTS.md"), /^Company rules/);
  assert.equal(read(root, ".codex/config.toml"), 'model = "existing"\n');
  install(root, prepare(root));
  assert.deepEqual(snapshot(root), before);
  assert.ok(manifest(root).files["harnesslib/core.py"]);
  const result = doctor(root);
  assert.equal(result.status, "HEALTHY", JSON.stringify(result));
  assert.deepEqual(snapshot(root), before, "doctor must not write");
  fs.appendFileSync(path.join(root, "harnesslib/core.py"), "\n# damage\n");
  assert.equal(
    doctor(root).checks.find((c) => c.id === "ownership").status,
    "FAIL",
  );
  assert.ok(prepare(root).some((c) => c.action === "conflict"));
});
test("C: existing OpenSpec sources and generated skill customization remain intact", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  fs.mkdirSync(path.join(root, "openspec/changes/private"), {
    recursive: true,
  });
  fs.writeFileSync(path.join(root, "openspec/config.yaml"), "schema: custom\n");
  fs.writeFileSync(
    path.join(root, "openspec/changes/private/proposal.md"),
    "Private requirement",
  );
  fs.mkdirSync(path.join(root, ".agents/skills/openspec-propose"), {
    recursive: true,
  });
  fs.writeFileSync(
    path.join(root, ".agents/skills/openspec-propose/SKILL.md"),
    "---\nname: openspec-propose\ndescription: Customized official skill\n---\n",
  );
  install(root, prepare(root));
  assert.equal(read(root, "openspec/config.yaml"), "schema: custom\n");
  assert.equal(
    read(root, "openspec/changes/private/proposal.md"),
    "Private requirement",
  );
  assert.match(
    read(root, ".agents/skills/openspec-propose/SKILL.md"),
    /Customized/,
  );
});
test("conflict preflight and symlink refusal leave user files untouched", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  fs.mkdirSync(root);
  fs.mkdirSync(path.join(root, "harnesslib"));
  fs.writeFileSync(path.join(root, "harnesslib/core.py"), "custom");
  const before = snapshot(root);
  const changes = prepare(root);
  assert.throws(() => install(root, changes));
  assert.deepEqual(snapshot(root), before);
  fs.symlinkSync(base, path.join(root, ".agents"), "dir");
  assert.throws(() => prepare(root));
});
test("partial write rollback preserves original data; concurrent recovery edits block", (t) => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, "existing"), "original");
  const changes = [
    {
      path: "existing",
      before: "original",
      content: "modified",
      owner: "harness",
      action: "update",
      reason: "",
    },
    {
      path: "new",
      before: null,
      content: "new",
      owner: "harness",
      action: "create",
      reason: "",
    },
  ];
  assert.throws(() => apply(root, changes, 1), /interrupted/);
  assert.equal(read(root, "existing"), "modified");
  recover(root);
  assert.equal(read(root, "existing"), "original");
  assert.equal(read(root, "new"), null);
  assert.throws(() => apply(root, changes, 1));
  fs.writeFileSync(path.join(root, "existing"), "concurrent");
  assert.throws(() => recover(root), /conflict/);
  assert.equal(read(root, "existing"), "concurrent");
});
test("E/H: dry run is read-only and noninteractive init never prompts", (t) => {
  const root = fixture(t);
  const target = path.join(root, "absent");
  const result = spawnSync(
    process.execPath,
    [cli, "init", "--target", target, "--dry-run"],
    { encoding: "utf8", timeout: 15000 },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(target), false);
  const absent = spawnSync(
    process.execPath,
    [cli, "init", "--target", target],
    { encoding: "utf8", timeout: 5000 },
  );
  assert.equal(absent.status, 1);
  assert.match(absent.stderr, /--yes/);
  const missing = spawnSync(
    process.execPath,
    [cli, "init", "--target", target, "--yes"],
    { env: { PATH: "" }, encoding: "utf8", timeout: 5000 },
  );
  assert.equal(missing.status, 1);
  assert.match(missing.stderr, /OpenSpec.*missing/);
  assert.equal(fs.existsSync(target), false);
  const json = spawnSync(
    process.execPath,
    [cli, "doctor", "--target", target, "--json"],
    { encoding: "utf8" },
  );
  assert.equal(json.status, 1);
  assert.equal(JSON.parse(json.stdout).status, "UNHEALTHY");
});
test("duplicate skills and missing references produce actionable diagnostics", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  install(root, prepare(root));
  fs.mkdirSync(path.join(root, ".agents/skills/duplicate"));
  fs.writeFileSync(
    path.join(root, ".agents/skills/duplicate/SKILL.md"),
    "---\nname: discovery\ndescription: Duplicate name\n---\n",
  );
  const finding = doctor(root).checks.find((c) => c.id === "skills");
  assert.equal(finding.status, "FAIL");
  assert.ok(finding.fix);
  fs.rmSync(path.join(root, ".agents/skills/duplicate"), { recursive: true });
  fs.appendFileSync(
    path.join(root, ".agents/skills/discovery/SKILL.md"),
    "\n[missing](missing.md)\n",
  );
  assert.equal(
    doctor(root).checks.find((c) => c.id === "skills").status,
    "FAIL",
  );
});
test(
  "real pinned OpenSpec stages Codex skills when explicitly enabled",
  { skip: !process.env.HARNESS_REAL_OPENSPEC },
  (t) => {
    const base = fixture(t);
    const old = process.env.PATH;
    process.env.PATH =
      path.dirname(process.env.HARNESS_REAL_OPENSPEC) + path.delimiter + old;
    t.after(() => (process.env.PATH = old));
    assert.equal(probeOpenSpec(base).state, "ready");
    const files = stageOpenSpec(base);
    assert.ok(
      files.some((f) => f.path === ".agents/skills/openspec-propose/SKILL.md"),
    );
    assert.ok(files.some((f) => f.path === "openspec/config.yaml"));
    assert.deepEqual(fs.readdirSync(base), []);
  },
);
test("invalid existing config and legacy OpenSpec layout block before mutation", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  fs.mkdirSync(path.join(root, ".harness"), { recursive: true });
  fs.writeFileSync(
    path.join(root, ".harness/checks.json"),
    '{"secret":"not logged",',
  );
  const before = snapshot(root);
  assert.throws(() => prepare(root), /invalid JSON/);
  assert.deepEqual(snapshot(root), before);
  fs.unlinkSync(path.join(root, ".harness/checks.json"));
  fs.mkdirSync(path.join(root, "openspec"));
  fs.writeFileSync(path.join(root, "openspec/project.md"), "old layout");
  assert.throws(() => prepare(root), /Older\/custom/);
  assert.equal(read(root, "openspec/project.md"), "old layout");
});
test("ownership coverage, executable mode and overriding Codex entry point are diagnosed", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  install(root, prepare(root));
  const file = path.join(root, ".harness/installation-manifest.json");
  const original = fs.readFileSync(file, "utf8");
  const data = JSON.parse(original);
  delete data.files["harnesslib/core.py"];
  fs.writeFileSync(file, JSON.stringify(data));
  assert.equal(
    doctor(root).checks.find((c) => c.id === "ownership").status,
    "FAIL",
  );
  fs.writeFileSync(file, original);
  if (process.platform !== "win32") {
    fs.chmodSync(path.join(root, "harness"), 0o644);
    assert.equal(
      doctor(root).checks.find((c) => c.id === "ownership").status,
      "FAIL",
    );
    fs.chmodSync(path.join(root, "harness"), 0o755);
  }
  fs.writeFileSync(path.join(root, "AGENTS.override.md"), "Override");
  assert.throws(() => prepare(root), /takes precedence/);
  assert.equal(
    doctor(root).checks.find((c) => c.id === "codex").status,
    "FAIL",
  );
});
test("OpenSpec version mismatch and failed generator never mutate the target", (t) => {
  const base = fixture(t);
  const bin = fakeTools(t, base);
  const root = path.join(base, "project");
  const executable = path.join(bin, "openspec");
  fs.writeFileSync(
    executable,
    `#!${process.execPath}\nconsole.log('99.0.0');\n`,
  );
  assert.throws(() => prepare(root), /incompatible/);
  assert.equal(fs.existsSync(root), false);
  fs.writeFileSync(
    executable,
    `#!${process.execPath}\nif(process.argv[2]==='--version')console.log('1.14.3');else process.exit(3);\n`,
  );
  assert.throws(() => prepare(root), /staging/);
  assert.equal(fs.existsSync(root), false);
});
test("YAML and TOML diagnostics reject syntax errors without leaking values", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  install(root, prepare(root));
  fs.mkdirSync(path.join(root, ".codex"));
  fs.writeFileSync(
    path.join(root, ".codex/config.toml"),
    'token = "PRIVATE_VALUE\n',
  );
  fs.writeFileSync(
    path.join(root, "openspec/config.yaml"),
    "schema: [PRIVATE_VALUE\n",
  );
  const result = doctor(root);
  assert.equal(
    result.checks.find((c) => c.id === "codex-config").status,
    "FAIL",
  );
  assert.equal(
    result.checks.find((c) => c.id === "openspec-project").status,
    "FAIL",
  );
  assert.ok(!JSON.stringify(result).includes("PRIVATE_VALUE"));
  assert.throws(() => prepare(root), /config is invalid/);
});
test("review regressions: unsupported runtime and stale lock fail closed", async (t) => {
  const { nodeSupported } = await import("../dist/core.js");
  assert.equal(nodeSupported("20.18.9"), false);
  assert.equal(nodeSupported("20.19.0"), true);
  assert.equal(nodeSupported("25.0.0"), false);
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  install(root, prepare(root));
  fs.writeFileSync(path.join(root, ".harness/installation.lock"), "");
  assert.throws(() => prepare(root), /lock exists/);
});
test("doctor returns JSON diagnostics for symlinked Codex configuration", (t) => {
  const base = fixture(t);
  fakeTools(t, base);
  const root = path.join(base, "project");
  install(root, prepare(root));
  fs.mkdirSync(path.join(root, ".codex"));
  fs.writeFileSync(path.join(base, "settings"), 'secret = "private"');
  fs.symlinkSync(
    path.join(base, "settings"),
    path.join(root, ".codex/config.toml"),
  );
  const result = spawnSync(
    process.execPath,
    [cli, "doctor", "--target", root, "--json"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 1);
  assert.equal(
    JSON.parse(result.stdout).checks.find((c) => c.id === "codex-config")
      .status,
    "FAIL",
  );
  assert.ok(!result.stdout.includes("private"));
});
test("a partial low-level write never publishes a torn created file", async (t) => {
  const defaultFs = (await import("node:fs")).default;
  const { syncBuiltinESMExports } = await import("node:module");
  const root = fixture(t);
  const original = defaultFs.writeFileSync;
  try {
    defaultFs.writeFileSync = function (file, data, ...args) {
      if (data === "target-body") {
        original(file, "partial", ...args);
        throw new Error("simulated disk failure");
      }
      return original(file, data, ...args);
    };
    syncBuiltinESMExports();
    assert.throws(
      () =>
        apply(root, [
          {
            path: "new",
            content: "target-body",
            before: null,
            owner: "harness",
            action: "create",
            reason: "",
          },
        ]),
      /interrupted/,
    );
  } finally {
    defaultFs.writeFileSync = original;
    syncBuiltinESMExports();
  }
  assert.equal(read(root, "new"), null);
  recover(root);
  assert.equal(read(root, ".harness/installation-pending.json"), null);
});

test('new project with staged tool directory still defaults to source navigation', t => {
  const base=fixture(t); fakeTools(t,base);
  const root=path.join(base,'new-project');
  fs.mkdirSync(path.join(root,'.harness/tools/cache'),{recursive:true});
  const changes=prepare(root,{},true);
  const policy=changes.find(c=>c.path==='.harness/navigation.json');
  assert.ok(policy);
  assert.equal(JSON.parse(policy.content).mode,'source');
});
