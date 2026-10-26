/** Real installed-package consumer planning run. Stops for genuine plan approval. */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { planningCommands } from "./copilot-e2e-fixture.mjs";
const source = process.cwd();
const evidence = path.join(source, ".harness/evidence/copilot");
fs.mkdirSync(evidence, { recursive: true });
const report = {
  status: "BLOCKED",
  commands: [],
  assertions: {},
  reason:
    "Account authorization required before transmitting the disposable project.",
};
if (process.env.HARNESS_COPILOT_E2E_ACCOUNT_APPROVED !== "1") {
  fs.writeFileSync(
    path.join(evidence, "e2e.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = 2;
} else {
  const continuing = process.env.HARNESS_COPILOT_E2E_CONTINUE;
  const base = fs.realpathSync(
    continuing ??
      fs.mkdtempSync(path.join(os.tmpdir(), "harness-copilot-e2e-")),
  );
  if (
    continuing &&
    (!path.basename(base).startsWith("harness-copilot-e2e-") ||
      !fs.existsSync(path.join(base, "project/.git")))
  )
    throw Error("Continuation requires a recorded disposable E2E project.");
  if (continuing)
    for (const name of [
      "trace.jsonl",
      "stderr.log",
      "doctor.json",
      "prompt.txt",
      "final-status.json",
      "openspec-validation.log",
    ]) {
      const file = path.join(base, name);
      if (fs.existsSync(file))
        fs.copyFileSync(file, file + "." + Date.now() + ".previous");
    }
  const root = path.join(base, "project"),
    consumer = path.join(root, ".harness/e2e-consumer");
  Object.assign(report, { base, root });
  if (!continuing) fs.mkdirSync(root);
  if (!fs.existsSync(consumer)) {
    fs.mkdirSync(consumer, { recursive: true });
    fs.writeFileSync(path.join(consumer, "package.json"), "{}");
  }
  const env = {
    ...process.env,
    PATH: [
      path.dirname(process.env.HARNESS_REAL_OPENSPEC ?? "/missing/openspec"),
      path.join(source, ".harness/tools/codegraph/node_modules/.bin"),
      path.join(source, ".harness/tools/graphify/bin"),
      process.env.PATH,
    ].join(path.delimiter),
  };
  const run = (file, args, cwd = root) => {
    const r = spawnSync(file, args, {
      cwd,
      env,
      encoding: "utf8",
      timeout: 180000,
      maxBuffer: 16 * 1024 * 1024,
    });
    report.commands.push({ file, args, cwd, exitCode: r.status });
    return r;
  };
  const checked = (file, args, cwd) => {
    const r = run(file, args, cwd);
    if (r.status !== 0) throw Error(`${file} failed: ${r.stderr}`);
    return r.stdout;
  };
  try {
    const packed = JSON.parse(
      checked(
        "npm",
        [
          "pack",
          "--ignore-scripts",
          "--json",
          "--cache",
          path.join(base, "cache"),
          "--pack-destination",
          base,
        ],
        source,
      ),
    )[0];
    checked(
      "npm",
      [
        "install",
        "--offline",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--cache",
        process.env.HARNESS_TEST_NPM_CACHE ?? path.join(base, "npm-cache"),
        path.join(base, packed.filename),
      ],
      consumer,
    );
    if (!continuing) checked("git", ["init"]);
    const cli = path.join(consumer, "node_modules/specreceipt/dist/cli.js");
    checked(process.execPath, [
      cli,
      "init",
      "--target",
      root,
      "--agent",
      "copilot",
      "--yes",
    ]);
    const diagnostic = run(process.execPath, [
      cli,
      "doctor",
      "--target",
      root,
      "--json",
    ]);
    fs.writeFileSync(path.join(base, "doctor.json"), diagnostic.stdout);
    if (diagnostic.status !== 0)
      throw Error("Consumer doctor failed; inspect doctor.json.");
    checked(process.execPath, [cli, "indexes", "ensure", "--target", root]);
    fs.writeFileSync(
      path.join(root, "package.json"),
      JSON.stringify(
        {
          name: "harness-copilot-parse-port",
          private: true,
          type: "module",
          scripts: { test: "node --test parser.test.mjs" },
        },
        null,
        2,
      ) + "\n",
    );
    if (!process.env.HARNESS_REAL_OPENSPEC)
      throw Error(
        "HARNESS_REAL_OPENSPEC must select the official installed CLI for this fixture.",
      );
    const planning = planningCommands(
      root,
      cli,
      process.env.HARNESS_REAL_OPENSPEC,
    );
    env.PATH = planning.bin + path.delimiter + env.PATH;
    const prompt = `${continuing ? "Continue the existing DRAFT planning artifacts; inspect their current contents and preserve completed work. The previous attempt hit tool denials, not an approval gate. " : ""}Work only in this disposable repository. Use repository-relative file paths; do not copy long absolute temporary paths. Do not commit, push, publish, access credentials, install tools or change global configuration. Read AGENTS.md and .github/copilot-instructions.md. Discover Skills using their metadata; load only relevant Engineering and official OpenSpec Skills. Use harness-e2e-plan for Harness commands; this fixture command delegates only permitted planning operations to the installed npm CLI. Use openspec-e2e-plan for official OpenSpec commands. Prepare the parsePort feature: export parsePort(text) from parser.mjs; accept only ASCII digit strings representing 1..65535 (leading zeros allowed); reject nonstrings with TypeError and empty/whitespace/sign/fraction/non-ASCII/out-of-range strings with RangeError. Use node --test parser.test.mjs for deterministic tests. Create and validate official OpenSpec change parse-port; use capability name port-parser and file openspec/changes/parse-port/specs/port-parser/spec.md. Use openspec-e2e-plan new change parse-port, then openspec-e2e-plan status --change parse-port --json and openspec-e2e-plan instructions proposal --change parse-port --json. The fixture delegates to the official OpenSpec CLI. Prepare concrete canonical project documents, requirements, plan and Harness task mapping at .harness/openspec-mapping.json. Configure the proposed parser check without inventing approval; import the mapping using Harness openspec import (which creates DRAFT wrappers) after OpenSpec validation. Do not precreate wrapper directories before import. This request authorizes planning only. Keep documents DRAFT pending actual user consent. Do not create parser.mjs or parser.test.mjs yet; do not invent approvals or run onboarding approve/task approve. Stop with a reviewable DELIVERY.md listing exact artifacts and decisions requiring operator approval. Report which Skills you actually loaded. No whole-guide upfront read. Run permitted Harness/OpenSpec CLI calls as individual simple commands, without pipes, redirection or chaining. Use native read/search tools for file discovery instead of compound git/ls/find shell commands. A denied unrelated command does not mean the listed Harness/OpenSpec commands are unavailable. If a required CLI command itself is denied, report that exact invocation; do not broaden permissions.`;
    fs.writeFileSync(path.join(base, "prompt.txt"), prompt);
    const writes = [
      "DELIVERY.md",
      "docs/TECH_SPEC.md",
      "docs/ARCHITECTURE.md",
      "docs/DECISION_QUEUE.md",
      ".harness/checks.json",
      ".harness/environment.json",
      ".harness/openspec-mapping.json",
      "specs/parse-port/spec.md",
      "specs/parse-port/plan.md",
      "specs/parse-port/tasks.json",
      "specs/parse-port/verification.md",
      "openspec/changes/parse-port/proposal.md",
      "openspec/changes/parse-port/design.md",
      "openspec/changes/parse-port/tasks.md",
      "openspec/changes/parse-port/specs/port-parser/spec.md",
    ];
    const permissions = [
      ...writes.map((p) => `write(${path.join(root, p)})`),
      ...planning.permissions,
    ];
    const { runCopilot, copilotArguments } = await import(
      pathToFileURL(
        path.join(consumer, "node_modules/specreceipt/dist/copilot.js"),
      )
    );
    report.commands.push({
      file: "copilot",
      args: copilotArguments("<prompt.txt>", permissions),
      cwd: root,
    });
    const controller = new AbortController(),
      cancel = () => controller.abort();
    process.once("SIGINT", cancel);
    process.once("SIGTERM", cancel);
    const result = await runCopilot({
      cwd: root,
      prompt,
      allowTools: permissions,
      timeoutMs: 600000,
      env,
      signal: controller.signal,
    });
    process.removeListener("SIGINT", cancel);
    process.removeListener("SIGTERM", cancel);
    fs.writeFileSync(
      path.join(base, "trace.jsonl"),
      result.events.map((e) => JSON.stringify(e)).join("\n") + "\n",
      { mode: 0o600 },
    );
    fs.writeFileSync(path.join(base, "stderr.log"), result.stderr, {
      mode: 0o600,
    });
    report.transport = {
      status: result.status,
      reason: result.reason,
      exitCode: result.exitCode,
    };
    const toolEvents = result.events.filter(
      (e) => e.type === "tool.execution_start",
    );
    report.assertions.realCopilotTurn = result.status === "PASS";
    const completedTools = new Set(
      result.events
        .filter(
          (e) =>
            e.type === "tool.execution_complete" && e.data?.success === true,
        )
        .map((e) => e.data?.toolCallId),
    );
    report.assertions.observedSkillUse = toolEvents.some(
      (e) =>
        completedTools.has(e.data?.toolCallId) &&
        /SKILL\.md|skills/.test(JSON.stringify(e.data?.arguments ?? {})),
    );
    report.assertions.delivery = fs.existsSync(path.join(root, "DELIVERY.md"));
    report.assertions.planningGatePreserved =
      !fs.existsSync(path.join(root, "parser.mjs")) &&
      !fs.existsSync(path.join(root, "parser.test.mjs"));
    const validation = run(process.execPath, [
      cli,
      "openspec",
      "validate",
      "parse-port",
      "--target",
      root,
    ]);
    fs.writeFileSync(
      path.join(base, "openspec-validation.log"),
      validation.stdout + validation.stderr,
    );
    report.assertions.openspecValid = validation.status === 0;
    const status = run(process.execPath, [
      cli,
      "status",
      "--target",
      root,
      "--json",
    ]);
    fs.writeFileSync(path.join(base, "final-status.json"), status.stdout);
    report.usage = result.events
      .filter((e) => e.type === "session.usage_info" || e.type === "result")
      .map((e) => (e.type === "result" ? e.usage : e.data));
    report.status = report.assertions.planningGatePreserved
      ? "BLOCKED"
      : "FAIL";
    report.reason = Object.values(report.assertions).every(Boolean)
      ? "Planning artifacts ready. Actual developer approval required before implementation; no consent manufactured."
      : `Inspect trace and delivery: transport=${result.reason}; missing planning evidence or approval gate violation.`;
  } catch (error) {
    report.reason = error.message;
  }
  fs.writeFileSync(
    path.join(evidence, "e2e.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.status === "PASS" ? 0 : 2;
}
