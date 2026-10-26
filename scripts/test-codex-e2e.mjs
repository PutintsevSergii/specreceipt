/** Opt-in real Codex run. Never substitutes mocks or manufactures approvals. */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync, spawn } from "node:child_process";
const source = process.cwd();
const continuing = process.env.HARNESS_E2E_CONTINUE;
const base = fs.realpathSync(
  continuing ?? fs.mkdtempSync(path.join(os.tmpdir(), "harness-codex-e2e-")),
);
const consumer = path.join(base, "consumer"),
  root = path.join(base, "project");
if (!continuing) {
  fs.mkdirSync(consumer);
  fs.mkdirSync(root);
  fs.writeFileSync(path.join(consumer, "package.json"), "{}");
} else {
  if (
    base === source ||
    !path.basename(base).startsWith("harness-codex-e2e-") ||
    !fs.existsSync(path.join(root, ".git"))
  )
    throw Error("Continuation requires the recorded disposable E2E directory.");
  for (const name of [
    "trace.jsonl",
    "codex-stderr.log",
    "final-message.txt",
    "doctor.json",
    "final-status.json",
  ]) {
    const file = path.join(base, name);
    if (fs.existsSync(file))
      fs.copyFileSync(file, file + "." + Date.now() + ".previous");
  }
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
const report = {
  base,
  root,
  status: "BLOCKED",
  commands: [],
  assertions: {},
  versions: {
    node: process.version,
    platform: process.platform,
    arch: process.arch,
  },
};
const run = (file, args, cwd = root) => {
  const r = spawnSync(file, args, {
    cwd,
    env,
    encoding: "utf8",
    timeout: 180000,
    maxBuffer: 8 * 1024 * 1024,
  });
  report.commands.push({ file, args, cwd, exit: r.status });
  return r;
};
const checked = (file, args, cwd = root) => {
  const r = run(file, args, cwd);
  if (r.status !== 0)
    throw Error(
      `${path.basename(file)} failed (${r.status}); see command evidence`,
    );
  return r.stdout;
};
try {
  if (!continuing) {
    checked("git", ["init"]);
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
        path.resolve(process.env.HARNESS_E2E_PACKAGE ?? path.join(source, "specreceipt-0.3.0.tgz")),
      ],
      consumer,
    );
  }
  const cli = path.join(consumer, "node_modules/specreceipt/dist/cli.js");
  if (!continuing)
    checked(process.execPath, [cli, "init", "--target", root, "--yes"]);
  const doctor = run(process.execPath, [
    cli,
    "doctor",
    "--target",
    root,
    "--json",
  ]);
  fs.writeFileSync(path.join(base, "doctor.json"), doctor.stdout);
  if (doctor.status !== 0)
    throw Error(
      "Installed project doctor failed; resolve dependencies before live execution.",
    );
  for (const [name, args] of [
    ["python3", ["--version"]],
    ["codex", ["--version"]],
    ["openspec", ["--version"]],
    ["codegraph", ["version"]],
    ["graphify", ["--version"]],
  ])
    report.versions[name] = checked(name, args).trim();
  const auth = run("codex", ["login", "status"]);
  report.authenticated = auth.status === 0;
  if (!report.authenticated) throw Error("Codex authentication unavailable.");
  const help = checked("codex", ["exec", "--help"]);
  fs.writeFileSync(path.join(base, "codex-help.txt"), help);
  for (const flag of [
    "--json",
    "--sandbox",
    "--ignore-user-config",
    "--ephemeral",
  ])
    if (!help.includes(flag)) throw Error(`Installed Codex lacks ${flag}`);
  if (!continuing)
    fs.writeFileSync(
      path.join(root, "package.json"),
      JSON.stringify(
        {
          name: "harness-parser-e2e",
          private: true,
          type: "module",
          scripts: { test: "node --test parser.test.mjs" },
        },
        null,
        2,
      ) + "\n",
    );
  const prompt =
    (continuing
      ? "Continue the existing parse-port plan and mapping, do not recreate or revise approved artifacts. Read docs/approvals/operator.md if present; it must contain actual operator consent and scope, not an agent assertion. Missing genuine approval remains BLOCKED.\n"
      : "") +
    `This is a real isolated Harness integration test. Work only in this disposable repository. Do not commit, push, publish, change global configuration, or access credentials. Read installed AGENTS.md. Select relevant Engineering Pack and generated OpenSpec skills by their metadata, then load the selected instructions. Consult only the needed guide sections and reuse unchanged instructions already in context; all applicable approval, quality and security rules remain mandatory. Use the actual installed public CLI: node ${JSON.stringify(cli)} (with --target ${JSON.stringify(root)} when needed). Preserve all approval and quality gates. Do not invent approval references or claim the test operator approved a later plan.
Feature: implement exported parsePort(text) in parser.mjs. Accept strings consisting only of ASCII decimal digits representing an integer 1..65535; leading zeros allowed. Reject non-strings with TypeError, empty strings, whitespace, signs, fractions, non-ASCII digits and out-of-range values with RangeError. Deterministic tests in parser.test.mjs must cover normal, invalid and boundary inputs; use node --test parser.test.mjs. No external APIs.
Follow onboarding and native OpenSpec workflow: discover instructions, create real OpenSpec change parse-port, prepare canonical project docs, requirements and implementation plan plus Harness execution mapping. Require real operator approval before dependent application implementation. If approval is pending, leave reviewable files and an explicit BLOCKED delivery report in DELIVERY.md; do not fake consent. If legitimately approved in existing repository evidence, implement and test, run Harness lifecycle/checks, review and deliver with evidence. Keep commands via public CLI. Record which Skills you actually used. A final message alone is not success.`;
  fs.writeFileSync(path.join(base, "prompt.txt"), prompt);
  const args = [
    "exec",
    "--json",
    "--sandbox",
    "workspace-write",
    "--ignore-user-config",
    "--ephemeral",
    "--cd",
    root,
    "--output-last-message",
    path.join(base, "final-message.txt"),
    prompt,
  ];
  report.commands.push({
    file: "codex",
    args: args.slice(0, -1).concat(["<prompt.txt>"]),
    cwd: root,
    exit: null,
  });
  const out = fs.openSync(path.join(base, "trace.jsonl"), "w", 0o600),
    err = fs.openSync(path.join(base, "codex-stderr.log"), "w", 0o600);
  const { checkedAgentLaunch } = await import("../dist/doctor.js");
  const child = checkedAgentLaunch({ cwd: root, agent: "codex", env, ignoreUserConfig: true }, (launchEnv) => spawn("codex", args, {
    cwd: root,
    env: launchEnv,
    stdio: ["ignore", out, err],
  }));
  const timeout = setTimeout(() => {
    report.timeout = true;
    child.kill("SIGTERM");
  }, 600000);
  const exit = await new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("close", resolve);
  });
  clearTimeout(timeout);
  fs.closeSync(out);
  fs.closeSync(err);
  report.commands.at(-1).exit = exit;
  const trace = fs.readFileSync(path.join(base, "trace.jsonl"), "utf8");
  const events = trace
    .split("\n")
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return { type: "malformed" };
      }
    });
  const commands = events
    .filter(
      (e) =>
        e.type === "item.completed" && e.item?.type === "command_execution",
    )
    .map((e) => e.item);
  report.assertions.realCodexTurn =
    exit === 0 && events.some((e) => e.type === "turn.completed");
  report.assertions.observedSkillUse = commands.some(
    (c) =>
      c.exit_code === 0 &&
      /SKILL\.md|skills (discovery|planner|spec-author|implementer)/.test(
        c.command ?? "",
      ),
  );
  report.assertions.source = fs.existsSync(path.join(root, "parser.mjs"));
  report.assertions.tests = fs.existsSync(path.join(root, "parser.test.mjs"));
  report.assertions.delivery = fs.existsSync(path.join(root, "DELIVERY.md"));
  report.assertions.openspec = ["proposal.md", "tasks.md"].every((p) =>
    fs.existsSync(path.join(root, "openspec/changes/parse-port", p)),
  );
  if (report.assertions.openspec)
    report.assertions.openspecValid =
      run(process.execPath, [cli, "openspec", "validate", "parse-port"])
        .status === 0;
  if (report.assertions.source && report.assertions.tests) {
    const acceptance = `import assert from 'node:assert/strict'; import {parsePort} from ${JSON.stringify(path.join(root, "parser.mjs"))};
 for (const [text,value] of [['1',1],['65535',65535],['00080',80],['443',443]]) assert.equal(parsePort(text),value);
 for (const text of ['', '0', '65536', ' 80', '80 ', '+80', '-1', '1.0', '1e2', '１２', '9999999999999999999999999']) assert.throws(()=>parsePort(text),RangeError);
 for (const text of [null, undefined, 80, {}, [], true]) assert.throws(()=>parsePort(text),TypeError);`;
    const acceptFile = path.join(base, "independent-acceptance.mjs");
    fs.writeFileSync(acceptFile, acceptance);
    const acceptanceResult = run(process.execPath, [acceptFile]);
    report.assertions.independentAcceptance = acceptanceResult.status === 0;
    fs.writeFileSync(
      path.join(base, "independent-acceptance.log"),
      acceptanceResult.stdout + acceptanceResult.stderr,
    );
    const diff = run("git", [
      "diff",
      "--no-index",
      "--",
      "/dev/null",
      "parser.mjs",
    ]);
    fs.writeFileSync(path.join(base, "source.diff"), diff.stdout);
    const test = run(process.execPath, ["--test", "parser.test.mjs"]);
    fs.writeFileSync(
      path.join(base, "independent-tests.log"),
      test.stdout + test.stderr,
    );
    report.assertions.independentTests = test.status === 0;
  }
  const state = JSON.parse(
    fs.readFileSync(path.join(root, ".harness/state.json"), "utf8"),
  );
  report.assertions.lifecycle =
    state.phase === "DONE" &&
    Boolean(state.active_task) &&
    state.latest_verification.length > 0;
  report.assertions.observedTests = commands.some(
    (c) =>
      c.exit_code === 0 &&
      /node --test|npm test|\bverify\b/.test(c.command ?? ""),
  );
  // A fresh status must confirm evidence, not merely a DONE label.
  const status = run(process.execPath, [cli, "status", "--json"]);
  fs.writeFileSync(path.join(base, "final-status.json"), status.stdout);
  const data = status.status === 0 ? JSON.parse(status.stdout).data : null;
  report.assertions.currentEvidence = Boolean(
    data?.tasks?.some(
      (t) =>
        t.id === state.active_task && t.status === "DONE" && t.evidence_current,
    ),
  );
  report.assertions.approvals = false;
  if (state.active_feature) {
    const f = JSON.parse(
      fs.readFileSync(
        path.join(root, `specs/${state.active_feature}/tasks.json`),
        "utf8",
      ),
    );
    const t = f.tasks.find((t) => t.id === state.active_task);
    report.assertions.approvals = Boolean(
      t?.approvals?.review && t?.approvals?.developer,
    );
  }
  report.status =
    Object.values(report.assertions).every(Boolean) &&
    Object.keys(report.assertions).length >= 12
      ? "PASS"
      : report.assertions.realCodexTurn
        ? "PARTIAL"
        : "BLOCKED";
  report.reason =
    report.status === "PASS"
      ? "All artifact and execution assertions passed."
      : "Missing required artifact/execution/approval assertions; inspect trace and delivery. No approval was synthesized.";
} catch (e) {
  report.reason = e.message;
}
fs.mkdirSync(path.join(source, "release-report"), {
  recursive: true,
});
fs.writeFileSync(
  path.join(source, "release-report/codex-e2e.json"),
  JSON.stringify(report, null, 2) + "\n",
);
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.status === "PASS" ? 0 : 2;
