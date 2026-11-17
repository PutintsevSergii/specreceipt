/** Actual archived-package upgrade, no source entrypoints or simulated version objects. */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { nativeCommand, executable } from "../dist/integrations.js";
const source = process.cwd();
const currentVersion = JSON.parse(fs.readFileSync(path.join(source, "package.json"), "utf8")).version;
const legacyName = process.env.HARNESS_LEGACY_NAME ?? "my-ai-harness";
const legacyVersion = process.env.HARNESS_LEGACY_VERSION ?? "0.1.0";
if (!["my-ai-harness", "specreceipt"].includes(legacyName) || !/^\d+\.\d+\.\d+$/.test(legacyVersion) || legacyVersion === currentVersion)
  throw Error("Expected a distinct, explicit legacy package identity");
const base = fs.realpathSync(
  fs.mkdtempSync(path.join(os.tmpdir(), "harness-two-versions-")),
);
const report = {
  base,
  kind: "actual packed versions",
  commands: [],
  cases: [],
};
const env = {
  ...process.env,
  PATH: [
    path.dirname(process.env.HARNESS_REAL_OPENSPEC ?? "/missing/openspec"),
    path.join(source, ".harness/tools/codegraph/node_modules/.bin"),
    path.join(source, process.platform === "win32" ? ".harness/tools/graphify/Scripts" : ".harness/tools/graphify/bin"),
    process.env.PATH,
  ].join(path.delimiter),
};
function run(file, args, cwd = base, expected = 0, commandEnv = env) {
  const command = nativeCommand({file: executable(file, commandEnv) ?? file, prefix: []}, commandEnv);
  const r = spawnSync(command.file, [...command.prefix, ...args], {
    cwd,
    env: commandEnv,
    encoding: "utf8",
    timeout: 180000,
    maxBuffer: 8 * 1024 * 1024,
  });
  report.commands.push({ file, args, cwd, exit: r.status });
  assert.equal(r.status, expected, r.stderr + "\n" + r.stdout);
  return r.stdout;
}
function snapshot(root) {
  const out = {};
  function visit(rel = "") {
    for (const name of fs.readdirSync(path.join(root, rel))) {
      const p = path.join(rel, name);
      if (fs.statSync(path.join(root, p)).isDirectory()) visit(p);
      else out[p] = fs.readFileSync(path.join(root, p)).toString("base64");
    }
  }
  visit();
  return out;
}
try {
  if (!process.env.HARNESS_LEGACY_PACKAGE || !process.env.HARNESS_UPGRADE_PACKAGE)
    throw Error("Set HARNESS_LEGACY_PACKAGE and HARNESS_UPGRADE_PACKAGE to reviewed archive paths.");
  for (const version of [legacyVersion, currentVersion]) {
    const consumer = path.join(base, version);
    fs.mkdirSync(consumer);
    fs.writeFileSync(path.join(consumer, "package.json"), "{}");
    run(
      "npm",
      [
        "install",
        "--offline",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--cache",
        process.env.HARNESS_TEST_NPM_CACHE ?? path.join(base, "npm-cache"),
        path.resolve(
          version === currentVersion
            ? process.env.HARNESS_UPGRADE_PACKAGE
            : process.env.HARNESS_LEGACY_PACKAGE,
        ),
        ...(process.env.HARNESS_TEST_LOCAL_DEPS
          ? ["yaml", "smol-toml"].map((name) =>
              path.join(process.env.HARNESS_TEST_LOCAL_DEPS, name),
            )
          : []),
      ],
      consumer,
    );
  }
  const oldPackage = path.join(base, legacyVersion, "node_modules", legacyName);
  const oldMetadata = JSON.parse(fs.readFileSync(path.join(oldPackage, "package.json"), "utf8"));
  assert.equal(oldMetadata.name, legacyName);
  assert.equal(oldMetadata.version, legacyVersion);
  const oldCli = path.join(oldPackage, "dist/cli.js");
  const cli = path.join(base, currentVersion, "node_modules/specreceipt/dist/cli.js");
  for (const scenario of [
    "clean",
    "customized",
    "missing-baseline",
    "conflict",
  ]) {
    const root = path.join(base, scenario);
    // The archived adapter must initialize with its own supported OpenSpec.
    // Only the upgraded adapter sees HARNESS_REAL_OPENSPEC afterward.
    const legacyEnv = process.env.HARNESS_LEGACY_OPENSPEC
      ? { ...env, PATH: path.dirname(process.env.HARNESS_LEGACY_OPENSPEC) + path.delimiter + env.PATH }
      : env;
    run(process.execPath, [oldCli, "init", "--target", root, "--yes"], base, 0, legacyEnv);
    const skill = path.join(root, ".agents/skills/discovery/SKILL.md");
    if (scenario !== "clean")
      fs.appendFileSync(skill, "\nCompany customization retained.\n");
    if (scenario === "customized") {
      fs.appendFileSync(
        path.join(root, "AGENTS.md"),
        "\nOutside company rules.\n",
      );
      const agents = fs
        .readFileSync(path.join(root, "AGENTS.md"), "utf8")
        .replace(
          "Strict policy:",
          "Company extension inside section.\nStrict policy:",
        );
      fs.writeFileSync(path.join(root, "AGENTS.md"), agents);
      fs.mkdirSync(path.join(root, ".agents/skills/custom"));
      fs.writeFileSync(
        path.join(root, ".agents/skills/custom/SKILL.md"),
        "---\nname: custom\ndescription: Company role\n---\n",
      );
      fs.appendFileSync(
        path.join(root, "openspec/config.yaml"),
        "\n# company customization\n",
      );
    }
    if (scenario === "missing-baseline") {
      // Modern archives retain baselines in the manifest. Remove the selected
      // baseline explicitly so this scenario still tests a genuinely missing input.
      const file = path.join(root, ".harness/installation-manifest.json");
      const owned = JSON.parse(fs.readFileSync(file, "utf8"));
      delete owned.files[".agents/skills/discovery/SKILL.md"].baseline;
      delete owned.files[".agents/skills/discovery/SKILL.md"].baselineHash;
      fs.writeFileSync(file, JSON.stringify(owned, null, 2) + "\n");
    }
    if (scenario === "conflict") {
      const file = path.join(root, "harnesslib/cli.py");
      fs.writeFileSync(
        file,
        fs
          .readFileSync(file, "utf8")
          .replace(
            "    g = sub.add_parser('graph')",
            "    g = sub.add_parser('company-graph')",
          ),
      );
    }
    const before = snapshot(root);
    const args = [
      "upgrade",
      "--target",
      root,
      ...(scenario === "missing-baseline" ? [] : ["--baseline", oldPackage]),
    ];
    const blocked = ["missing-baseline", "conflict"].includes(scenario);
    run(process.execPath, [cli, ...args, "--dry-run"], base, blocked ? 1 : 0);
    assert.deepEqual(snapshot(root), before);
    run(process.execPath, [cli, ...args], base, blocked ? 1 : 0);
    if (blocked) {
      assert.deepEqual(snapshot(root), before);
      report.cases.push({
        scenario,
        status: "PASS",
        outcome: "explicit conflict, unchanged",
      });
      continue;
    }
    const m = JSON.parse(
      fs.readFileSync(path.join(root, ".harness/installation-manifest.json")),
    );
    assert.equal(m.packageVersion, currentVersion);
    assert.equal(m.protocolVersion, 1);
    const status = JSON.parse(
      run(process.execPath, [cli, "status", "--target", root, "--json"]),
    );
    assert.equal(status.engineRoot, root);
    if (scenario === "customized") {
      assert.match(
        fs.readFileSync(skill, "utf8"),
        /Company customization retained/,
      );
      assert.match(
        fs.readFileSync(path.join(root, "AGENTS.md"), "utf8"),
        /Company extension inside section/,
      );
      assert.match(
        fs.readFileSync(path.join(root, "openspec/config.yaml"), "utf8"),
        /company customization/,
      );
    }
    const after = snapshot(root);
    run(process.execPath, [cli, ...args]);
    assert.deepEqual(snapshot(root), after);
    const diagnostic = JSON.parse(
      run(process.execPath, [cli, "doctor", "--target", root, "--json"]),
    );
    assert.ok(["HEALTHY", "ATTENTION"].includes(diagnostic.status));
    assert.ok(diagnostic.checks.every((check) => check.status !== "FAIL"));
    report.cases.push({
      scenario,
      status: "PASS",
      outcome: "upgraded, repeated, doctor healthy, installed engine executed",
    });
  }
  report.status = "PASS";
} catch (e) {
  report.status = "FAIL";
  report.error = e.message;
  process.exitCode = 1;
} finally {
  const reportPath =
    process.env.HARNESS_UPGRADE_REPORT ??
    "release-report/packed-upgrade.json";
  fs.mkdirSync(path.dirname(reportPath), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
}
