import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import { prepare, install } from "../dist/install.js";
import { execute, request, resolveEngine } from "../dist/engine.js";
import { prepareUpgrade, upgrade, mergeText } from "../dist/upgrade.js";
import { migrate } from "../dist/migrations.js";
import { manifest, read, hash, recover, walk } from "../dist/filesystem.js";
import { CONFIG_PATH, MANIFEST_PATH, DEFAULTS } from "../dist/core.js";
const cli = path.resolve("dist/cli.js");
function fixture(t) {
  const root = fs.realpathSync(
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
  assert.equal(JSON.parse(p.stdout).engineRoot, root);
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
