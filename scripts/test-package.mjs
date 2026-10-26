import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
const root = process.cwd();
const temp = fs.realpathSync(
  fs.mkdtempSync(path.join(os.tmpdir(), "harness-packed-")),
);
function run(cmd, args, cwd = root, env = process.env, timeoutMs = 120000) {
  const r = spawnSync(cmd, args, {
    cwd,
    env,
    encoding: "utf8",
    timeout: timeoutMs,
  });
  assert.equal(
    r.status,
    0,
    `${cmd} ${args.join(" ")}\n${r.error?.message ?? ""}\n${r.stderr}\n${r.stdout}`,
  );
  return r.stdout;
}
function assertAdaptiveInstallation(project, agent) {
  assert.equal(fs.existsSync(path.join(project, "harnesslib/reconciliation.py")), true);
  assert.equal(fs.existsSync(path.join(project, "schemas/reconciliation.schema.json")), true);
  assert.match(run("python3", ["-B", "harness", "task", "baseline", "--help"], project), /propose.*accept/s);
  const instructions = fs.readFileSync(path.join(project, "AGENTS.md"), "utf8");
  assert.match(instructions, /Python Engine owns task workflow policy and OpenSpec requirements/);
  assert.match(instructions, /workflow assess TASK-ID --facts FILE/);
  assert.match(instructions, /wait for explicit developer confirmation/);
  assert.match(instructions, /FAST\/STANDARD.*without a task OpenSpec change unless linked requirements or project policy require it/);
  assert.match(instructions, /STRICT retains required OpenSpec sources and all quality gates/);
  assert.match(instructions, /separate final developer approval after VERIFIED and before DONE/);
  assert.doesNotMatch(instructions, /Use OpenSpec as the feature requirements source/);
  assert.equal(fs.existsSync(path.join(project, ".harness/workflow-policy.json")), false);
  const template = JSON.parse(fs.readFileSync(path.join(project, "templates/feature/tasks.json")));
  assert.equal(template.tasks[0].workflow_required, true);
  const product = JSON.parse(fs.readFileSync(path.join(project, ".harness/product.json")));
  assert.equal(product.workflow, "openspec");
  assert.equal(product.quality, "strict");
  assert.deepEqual(fs.readdirSync(path.join(project, "openspec/changes")).filter(name => name !== "archive" && name !== ".gitkeep"), []);
  if (agent.includes("copilot")) {
    const copilot = fs.readFileSync(path.join(project, ".github/copilot-instructions.md"), "utf8");
    for (const line of instructions.split("\n").filter(line => /^(The Python Engine|FAST\/STANDARD|Keep readiness)/.test(line)))
      assert.ok(copilot.includes(line));
    assert.match(copilot, /When OpenSpec is required, use official OpenSpec/);
  }
}
try {
  const packed = JSON.parse(
    run("npm", [
      "pack",
      "--ignore-scripts",
      "--json",
      "--cache",
      path.join(temp, "cache"),
      "--pack-destination",
      temp,
    ]),
  )[0];
  assert.ok(packed.files.some((f) => f.path === "dist/cli.js"));
  assert.ok(
    packed.files.some(
      (f) => f.path === "assets/kit/.agents/skills/implementer/SKILL.md",
    ),
  );
  for (const item of packed.files) {
    assert.ok(
      /^(dist\/|assets\/|README.md$|LICENSE$|CHANGELOG.md$|CONTRIBUTING.md$|SECURITY.md$|THIRD_PARTY_NOTICES.md$|package.json$)/.test(item.path),
      item.path,
    );
    assert.ok(
      !/(\.env|state.json|events.jsonl|evidence\/|node_modules\/|\.DS_Store)/.test(
        item.path,
      ),
      item.path,
    );
  }
  const consumer = path.join(temp, "consumer");
  fs.mkdirSync(consumer);
  fs.writeFileSync(path.join(consumer, "package.json"), "{}");
  run(
    "npm",
    [
      "install",
      ...(process.env.HARNESS_TEST_NPM_CACHE ? ["--offline"] : []),
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      "--cache",
      process.env.HARNESS_TEST_NPM_CACHE ?? path.join(temp, "cache"),
      path.join(temp, packed.filename),
      ...(process.env.HARNESS_TEST_LOCAL_DEPS
        ? ["yaml", "smol-toml"].map((name) =>
            path.join(process.env.HARNESS_TEST_LOCAL_DEPS, name),
          )
        : []),
    ],
    consumer,
  );
  const cli = path.join(consumer, "node_modules/specreceipt/dist/cli.js");
  assert.match(run(process.execPath, [cli, "--version"], consumer), /0.3.0/);
  const { executionPreflight, checkedAgentLaunch } = await import(pathToFileURL(path.join(consumer, "node_modules/specreceipt/dist/doctor.js")));
  const { executable } = await import(pathToFileURL(path.join(consumer, "node_modules/specreceipt/dist/integrations.js")));
  function assertPackagedPreflight(project, agent) {
    const mode = agent.includes("codex") ? "codex" : agent === "copilot-ide" ? "copilot-ide" : "copilot";
    const fake = path.join(temp, "preflight-agent.cjs");
    fs.writeFileSync(fake, `if(process.argv.includes('--version')) console.log(${JSON.stringify(mode === "codex" ? "codex-cli 1.0" : "GitHub Copilot CLI 1.0")}); else if(process.argv.includes('--help')) console.log('--json --sandbox --cd --ignore-user-config --prompt --output-format --allow-tool --deny-tool --no-auto-update --disallow-temp-dir --disable-builtin-mcps --no-bash-env'); else process.exit(99);`);
    const options = {cwd: project, agent: mode, command: {file:process.execPath,prefix:[fake]}, env: {PATH:"", HOME:temp,HARNESS_PYTHON:executable("python3")}, shell:{file:"/bin/sh",login:false},ignoreUserConfig:true};
    const featureDir = path.join(project,"specs/preflight-fixture");
    fs.mkdirSync(featureDir,{recursive:true});
    const feature = JSON.parse(fs.readFileSync(path.join(project,"templates/feature/tasks.json")));
    feature.feature_id="preflight-fixture";
    fs.writeFileSync(path.join(featureDir,"tasks.json"),JSON.stringify(feature));
    const result = executionPreflight(options);
    if (mode === "copilot-ide") assert.equal(result.status,"PASS");
    else {
      assert.equal(result.checks.find(c=>c.id === "codegraph-cli").requirement,"REQUIRED");
      assert.equal(result.status,"FAIL");
      let launches=0;
      assert.throws(()=>checkedAgentLaunch(options,()=>launches++),/preflight failed/);
      assert.equal(launches,0);
    }
    fs.rmSync(featureDir,{recursive:true});
  }
  const target = path.join(temp, "target");
  run(
    process.execPath,
    [cli, "init", "--target", target, "--dry-run"],
    consumer,
  );
  assert.equal(fs.existsSync(target), false);
  if (process.env.HARNESS_REAL_OPENSPEC) {
    const env = {
      ...process.env,
      PATH:
        path.dirname(process.env.HARNESS_REAL_OPENSPEC) +
        path.delimiter +
        process.env.PATH,
    };
    run(
      process.execPath,
      [cli, "init", "--target", target, "--yes"],
      consumer,
      env,
    );
    assertAdaptiveInstallation(target, "codex");
    assertPackagedPreflight(target, "codex");
    assert.match(run(process.execPath, [cli, "workflow", "--help", "--target", target], consumer, env), /assess,show,confirm/);
    const first = fs.readFileSync(
      path.join(target, ".harness/installation-manifest.json"),
      "utf8",
    );
    run(
      process.execPath,
      [cli, "init", "--target", target, "--yes"],
      consumer,
      env,
    );
    assert.equal(
      fs.readFileSync(
        path.join(target, ".harness/installation-manifest.json"),
        "utf8",
      ),
      first,
    );
    const result = spawnSync(
      process.execPath,
      [cli, "doctor", "--target", target, "--json"],
      { cwd: consumer, env, encoding: "utf8" },
    );
    const report = JSON.parse(result.stdout);
    assert.equal(
      report.checks.find((c) => c.id === "openspec-cli").status,
      "PASS",
    );
    assert.equal(
      report.checks.find((c) => c.id === "ownership").status,
      "PASS",
    );
    assert.equal(
      report.checks.find((c) => c.id === "legacy-runtime").status,
      "PASS",
    );
    for (const agent of [
      "copilot",
      "copilot-ide",
      "codex,copilot",
      "codex,copilot-ide",
    ]) {
      const project = path.join(temp, agent.replaceAll(",", "-"));
      run(
        process.execPath,
        [cli, "init", "--target", project, "--agent", agent, "--yes"],
        consumer,
        env,
      );
      assertAdaptiveInstallation(project, agent);
      assertPackagedPreflight(project, agent);
      const before = fs.readFileSync(
        path.join(project, ".harness/installation-manifest.json"),
        "utf8",
      );
      run(
        process.execPath,
        [cli, "init", "--target", project, "--yes"],
        consumer,
        env,
      );
      assert.equal(
        fs.readFileSync(
          path.join(project, ".harness/installation-manifest.json"),
          "utf8",
        ),
        before,
      );
      const diagnostic = spawnSync(
        process.execPath,
        [cli, "doctor", "--target", project, "--json"],
        { cwd: consumer, env, encoding: "utf8" },
      );
      const checks = JSON.parse(diagnostic.stdout).checks;
      for (const id of [
        "configuration",
        "ownership",
        "copilot-instructions",
        "copilot-openspec",
        "skills",
        "openspec-project",
        "legacy-runtime",
      ])
        assert.equal(
          checks.find((c) => c.id === id)?.status,
          "PASS",
          `${agent}: ${id}`,
        );
      if (agent.endsWith("ide"))
        assert.equal(checks.find((c) => c.id === "copilot-cli").status, "SKIP");
      run(
        process.execPath,
        [cli, "upgrade", "--target", project, "--dry-run"],
        consumer,
        env,
      );
      assert.equal(
        fs.existsSync(
          path.join(project, ".github/workflows/copilot-setup-steps.yml"),
        ),
        false,
      );
    }
    console.log(
      "Packed Copilot CLI/IDE/coexistence initialization, idempotence and upgrade checks passed.",
    );
    const agentsPath = path.join(target, "AGENTS.md");
    const customized = "# Company policy preserved\n" + fs.readFileSync(agentsPath, "utf8");
    fs.writeFileSync(agentsPath, customized);
    run(process.execPath, [cli, "init", "--target", target, "--yes"], consumer, env);
    assert.equal(fs.readFileSync(agentsPath, "utf8"), customized);
    const conflicting = customized.replace("Never claim checks passed without execution evidence.", "Company verification customization.");
    fs.writeFileSync(agentsPath, conflicting);
    const refused = spawnSync(process.execPath, [cli, "init", "--target", target, "--yes"], { cwd: consumer, env, encoding: "utf8" });
    assert.notEqual(refused.status, 0);
    assert.equal(fs.readFileSync(agentsPath, "utf8"), conflicting);
    fs.writeFileSync(agentsPath, customized);
    run("python3", ["-B", "harness", "self-test"], target, env, 300000);
    // Regression from real Codex onboarding: consumer revisions need not be zero.
    for (const name of ["TECH_SPEC.md", "ARCHITECTURE.md"]) {
      const file = path.join(target, "docs", name);
      fs.writeFileSync(
        file,
        fs.readFileSync(file, "utf8").replace(/^Revision: .*$/m, "Revision: 7"),
      );
    }
    run(
      process.execPath,
      [cli, "self-test", "--target", target, "--json"],
      consumer,
      env,
      300000,
    );

    console.log(
      "Packed CLI: actual init, repeat init, OpenSpec and legacy validation passed. Missing navigation dependencies remain reported by doctor.",
    );
  } else
    console.log(
      "Packed CLI entry and dry-run passed; real init requires HARNESS_REAL_OPENSPEC.",
    );
  console.log(
    `Package verified: ${packed.files.length} files, ${packed.size} bytes.`,
  );
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}
