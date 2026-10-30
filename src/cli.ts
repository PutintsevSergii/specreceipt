#!/usr/bin/env node
import * as path from "node:path";
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { safe } from "./filesystem.js";
import { parseArgs } from "node:util";
import { createInterface } from "node:readline/promises";
import {
  DEFAULTS,
  CONFIG_PATH,
  config,
  AGENTS,
  VERSION,
  nodeSupported,
  type Selection,
} from "./core.js";
import { prepare, install } from "./install.js";
import { recover, read } from "./filesystem.js";
import { checkedAgentLaunch, doctor, executionPreflight } from "./doctor.js";
import { execute } from "./engine.js";
import { dispatchCopilot } from "./copilot.js";
import { prepareUpgrade, upgrade } from "./upgrade.js";
const help = `AI Engineering Harness ${VERSION}
Usage: specreceipt init [--target DIR] [--agent codex|copilot|copilot-ide|codex,copilot --workflow openspec --quality strict --skills engineering-pack] [--yes] [--dry-run]
       specreceipt init --target DIR --recover
       specreceipt doctor [--target DIR] [--json]
       specreceipt doctor --execution --agent codex|copilot|copilot-ide [--task ID] [--target DIR] [--ignore-user-config] [--json]
       specreceipt upgrade [--target DIR] [--dry-run | --recover] [--baseline DIR]
       specreceipt copilot-exec --context FILE [--allow-tool RULE] [--timeout SECONDS]
       specreceipt codex-exec --context FILE [--target DIR]
       specreceipt codex-runner-preview --task ID [--task ID ...] --reference FILE [--target DIR]
       specreceipt <Python operation> [arguments] [--target DIR] [--json]
Operations: workflow, task, run, verify, review, approval-package, status, resume, next, readiness, onboarding, skills, openspec, indexes, graph, codegraph, graphify, tools, validate, self-test, regression, checkpoint, note, recovery, engineering-log, adopt.
Initialization: --workflow openspec selects the specification integration; --quality strict selects the engineering baseline, not a task execution-profile minimum. --workflow adaptive is not an init option.
Adaptive tasks: workflow assess TASK-ID --facts FILE; after actual developer approval, workflow confirm TASK-ID --profile FAST|STANDARD|STRICT --by NAME --reference FILE. Python enforces task policy and OpenSpec requirements.
Compact FAST: workflow propose --file FILE; confirm with --expected PROPOSAL_BINDING; run returns a guarded current-host role; run --submit TOKEN; workflow accept with --expected ACCEPTANCE_BINDING. Legacy opt-in: workflow migrate preview.
Lifecycle arguments and help are owned by Python. No automatic publishing.`;
export function advice(w: any): string {
  if (w.action === "plan-decision") return [
    `${w.task_id} — ${w.brief.outcome}`, `Project: ${w.project}`,
    `Recommended: ${w.recommended} | Minimum permitted: ${w.minimum}`,
    `Scope: ${w.brief.scope.join(", ")}`, `Non-goals: ${w.brief.non_goals.join("; ")}`,
    `Constraints: ${w.brief.constraints.join("; ")}`,
    `Acceptance: ${JSON.stringify(w.brief.acceptance_checks)}`,
    `Context: ${JSON.stringify(w.context)}`, `Environment: ${JSON.stringify(w.environment)}`, `Checks: ${JSON.stringify(w.checks)}`,
    `Risk: ${w.brief.risk}; unknowns: ${JSON.stringify(w.unknowns)}`,
    `Blockers: ${(w.blockers ?? []).join("; ") || "none"}`, w.next_action,
  ].join("\n");
  return ["AI Engineering Harness — Task assessment", `Risk: ${w.risk ?? "unknown"} | Complexity: ${w.complexity ?? "unknown"} | Uncertainty: ${w.uncertainty ?? "unknown"}`,
    `Recommended: ${w.recommended ?? "STRICT"} | Minimum permitted: ${w.minimum ?? "STRICT"} | Execution cost: ${w.execution_cost ?? "unknown"}`,
    ...(w.reasons ?? []).map((r: string) => `- ${r}`), "Plan:", w.plan ?? "Inspect task plan before confirmation.",
    w.deeper_required ? "Next action: Resolve critical unknowns through targeted inspection." : "Next action: Confirm workflow and plan together; recommendation is not authorization."].join("\n");
}
function pythonCanonical(value: unknown): string {
  if (typeof value === "string")
    return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (char) =>
      `\\u${char.charCodeAt(0).toString(16).padStart(4, "0")}`,
    );
  if (Array.isArray(value)) return `[${value.map(pythonCanonical).join(",")}]`;
  if (value && typeof value === "object") {
    const object = value as Record<string, unknown>;
    return `{${Object.keys(object).sort().map((key) => `${pythonCanonical(key)}:${pythonCanonical(object[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}
function runnerPreview(root: string, tasks: string[], reference: string) {
  if (!tasks.length || new Set(tasks).size !== tasks.length || tasks.some((id) => !/^[A-Z][A-Z0-9-]*$/.test(id)))
    throw Error("Provide unique, explicit task IDs.");
  if (path.isAbsolute(reference)) throw Error("Approval reference must be project-relative.");
  const approved = read(root, reference);
  if (!approved || approved.trim().length < 40)
    throw Error("A substantive approval reference must exist before preview.");
  const adapter = [process.execPath, path.resolve(process.argv[1]!), "codex-exec", "--target", root, "--context", "{context}"];
  const configuration = {
    enabled: true, approval_reference: reference, approval_hash: "", task_ids: tasks,
    implement_argv: adapter, review_argv: adapter, timeout_seconds: 900, max_failures: 2,
  };
  configuration.approval_hash = createHash("sha256")
    .update(pythonCanonical({ configuration: Object.fromEntries(Object.entries(configuration).filter(([key]) => key !== "approval_hash")), reference: approved }))
    .digest("hex");
  return configuration;
}
async function dispatchCodex(root: string, contextFile: string) {
  root = path.resolve(root);
  if (path.resolve(contextFile) !== path.join(root, ".harness/dispatch/context.json"))
    throw Error("Use the Python runner's context path.");
  const context = JSON.parse(read(root, ".harness/dispatch/context.json") ?? "null");
  const state = JSON.parse(read(root, ".harness/state.json") ?? "null");
  if (!context || !["implement", "review"].includes(context.action) ||
      typeof context.task_id !== "string" || typeof context.instructions !== "string" ||
      !Array.isArray(context.scope) || !context.scope.length ||
      state?.active_operation?.kind !== "adapter" ||
      state.active_operation.task !== context.task_id ||
      state.active_operation.phase !== context.action ||
      process.env.HARNESS_CHECK_NAME !== `adapter-${context.action}` ||
      process.env.HARNESS_OPERATION_ID !== state.active_operation.id)
    throw Error("Codex dispatch requires a matching active Python runner operation.");
  const status = execute(root, ["status", context.task_id]);
  const task = status.data?.tasks?.[0];
  const expected = context.action === "implement" ? "IN_PROGRESS" : "VERIFIED";
  if (status.exitCode || task?.effective_status !== expected || task?.next_action?.action !== "progress")
    throw Error("Python task readiness blocked Codex dispatch.");
  const prompt = `Perform only the assigned ${context.action} role in this repository. Follow the current AGENTS.md and the exact Python runner context below. Do not run Harness lifecycle or approval commands, change configuration, commit, push or publish. Do not write outside the approved scope; review may write only its review_path. Exit only after the assigned role is complete.\n${JSON.stringify(context)}`;
  const args = ["exec", "--json", "--sandbox", "workspace-write", "--ignore-user-config", "--ephemeral", "--cd", root, prompt];
  const child = checkedAgentLaunch({ cwd: root, agent: "codex", taskId: context.task_id, ignoreUserConfig: true,
    ...(process.platform === "win32" ? {} : { shell: { file: "/bin/sh", login: false } }) },
    (env) => spawn("codex", args, { cwd: root, env, stdio: ["ignore", "inherit", "inherit"] }));
  const stop = () => child.kill("SIGTERM");
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  try {
    const code = await new Promise<number>((resolve, reject) => {
      child.once("error", reject);
      child.once("close", (exitCode, signal) => resolve(signal ? 1 : exitCode ?? 1));
    });
    if (code !== 0) throw Error(`Codex exited with status ${code}.`);
    return { status: "PASS", task_id: context.task_id, action: context.action };
  } finally {
    process.removeListener("SIGINT", stop);
    process.removeListener("SIGTERM", stop);
  }
}
async function main() {
  const raw = process.argv.slice(2);
  if (raw[0] === "codex-runner-preview") {
    const { values } = parseArgs({ args: raw.slice(1), options: {
      target: { type: "string" }, task: { type: "string", multiple: true }, reference: { type: "string" },
    }});
    if (!values.reference) throw Error("codex-runner-preview requires --reference FILE.");
    const root = path.resolve(values.target ?? process.cwd());
    console.log(JSON.stringify(runnerPreview(root, values.task ?? [], values.reference), null, 2));
    return;
  }
  if (raw[0] === "codex-exec") {
    const { values } = parseArgs({ args: raw.slice(1), options: {
      target: { type: "string" }, context: { type: "string" },
    }});
    if (!values.context) throw Error("codex-exec requires --context from the authorized Python runner.");
    console.log(JSON.stringify(await dispatchCodex(values.target ?? process.cwd(), values.context)));
    return;
  }
  if (raw[0] === "doctor" && raw.includes("--execution")) {
    const { values } = parseArgs({ args: raw.slice(1), options: {
      execution: { type: "boolean" }, target: { type: "string" }, agent: { type: "string" },
      task: { type: "string" }, json: { type: "boolean" }, "ignore-user-config": { type: "boolean" },
    }});
    if (!["codex", "copilot", "copilot-ide"].includes(values.agent ?? "")) throw Error("Execution doctor requires --agent codex|copilot|copilot-ide.");
    const result = executionPreflight({ cwd: path.resolve(values.target ?? process.cwd()), agent: values.agent as "codex" | "copilot" | "copilot-ide", taskId: values.task, ignoreUserConfig: values["ignore-user-config"], builtinMcpsDisabled: values.agent === "copilot" });
    console.log(values.json ? JSON.stringify(result) : result.checks.map(c => `${c.status} ${c.requirement} ${c.id}: ${c.message}${c.fix ? " Fix: " + c.fix : ""}`).join("\n"));
    process.exitCode = result.status === "FAIL" ? 1 : 0;
    return;
  }
  if (raw[0] === "copilot-exec") {
    const { values } = parseArgs({
      args: raw.slice(1),
      options: {
        target: { type: "string" },
        context: { type: "string" },
        "allow-tool": { type: "string", multiple: true },
        timeout: { type: "string" },
      },
    });
    if (!values.context)
      throw Error(
        "copilot-exec requires --context from the authorized Python runner.",
      );
    const controller = new AbortController();
    const cancel = () => controller.abort();
    process.once("SIGINT", cancel);
    process.once("SIGTERM", cancel);
    try {
      const result = await dispatchCopilot(
        values.target ?? process.cwd(),
        values.context,
        values["allow-tool"] ?? [],
        Number(values.timeout ?? 120) * 1000,
        controller.signal,
      );
      console.log(JSON.stringify(result));
      process.exitCode = result.status === "PASS" ? 0 : 1;
    } finally {
      process.removeListener("SIGINT", cancel);
      process.removeListener("SIGTERM", cancel);
    }
    return;
  }
  if (
    raw[0] &&
    !["init", "doctor", "upgrade", "--help", "--version"].includes(raw[0])
  ) {
    let target = process.cwd();
    let json = false;
    const argv: string[] = [];
    for (let i = 0; i < raw.length; i++) {
      const a = raw[i]!;
      if (a === "--target") {
        if (!raw[i + 1]) throw Error("--target requires a directory");
        target = raw[++i]!;
      } else if (a.startsWith("--target=")) target = a.slice(9);
      else if (a === "--json") json = true;
      else argv.push(a);
    }
    if (argv[0] === "workflow" && argv[1] === "select") {
      if (!process.stdin.isTTY || !process.stdout.isTTY)
        throw Error("Interactive selection requires a terminal. Use workflow confirm with an actual developer approval reference.");
      const { values, positionals } = parseArgs({ args: argv.slice(2), allowPositionals: true, options: { by: { type: "string" } } });
      if (positionals.length !== 1 || !values.by) throw Error("Usage: workflow select TASK-ID --by NAME");
      const id = positionals[0]!;
      const shown = execute(path.resolve(target), ["workflow", "show", id]);
      if (shown.exitCode) { console.log(JSON.stringify(shown)); process.exitCode = shown.exitCode; return; }
      const w = shown.data;
      console.log(advice(w));
      if (w.deeper_required) throw Error("Resolve critical unknowns through targeted inspection and reassess.");
      const prompt = createInterface({ input: process.stdin, output: process.stdout });
      try {
        const profile = ((await prompt.question(`Select FAST / STANDARD / STRICT / DEEPER [${w.recommended}]: `)).trim() || w.recommended).toUpperCase();
        if (profile === "DEEPER") {
          console.log(`No confirmation recorded. Inspect unresolved facts, then run workflow assess ${id} --facts FILE.`);
          return;
        }
        const answer = await prompt.question(`Confirm ${profile} workflow and the displayed plan together? Type yes: `);
        if (answer.trim().toLowerCase() !== "yes") { console.log("Not confirmed. Implementation remains blocked."); return; }
        const root = path.resolve(target);
        const reference = `.harness/approvals/workflow-${randomUUID()}.txt`;
        const destination = safe(root, reference);
        mkdirSync(path.dirname(destination), { recursive: true });
        writeFileSync(destination, `Developer ${values.by} explicitly confirmed ${profile} workflow and displayed plan in the interactive CLI.\n${advice(w)}\n`, { flag: "wx" });
        const result = execute(root, ["workflow", "confirm", id, "--profile", profile, "--by", values.by, "--reference", reference, ...(w.proposal_binding ? ["--expected", w.proposal_binding] : [])]);
        console.log(JSON.stringify(result.data ?? result.error, null, 2)); process.exitCode = result.exitCode;
      } finally { prompt.close(); }
      return;
    }
    if (argv[0] === "status" && !json && !argv.includes("--format")) argv.push("--format", "terminal");
    const result = execute(path.resolve(target), argv);
    if (!json && result.exitCode === 0 && ["verify", "resume", "task", "review"].includes(argv[0] ?? "")) {
      const id = argv[0] === "task" ? argv[2] : argv[0] === "resume" ? undefined : argv[1];
      if (argv[0] === "resume" || (id && !id.startsWith("-"))) {
        const report = execute(path.resolve(target), ["status", ...(id ? [id] : []), "--format", "terminal"]);
        if (report.exitCode === 0 && report.data?.text) {
          console.log(report.data.text); process.exitCode = result.exitCode; return;
        }
      }
    }
    console.log(
      json
        ? JSON.stringify(result, null, 2)
        : (argv[0] === "workflow" && ["assess", "show", "propose"].includes(argv[1] ?? "") && !result.exitCode ? advice(result.data) : result.data?.text ??
            JSON.stringify(result.data ?? result.error, null, 2)),
    );
    process.exitCode = result.exitCode;
    return;
  }
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    strict: true,
    options: {
      baseline: { type: "string" },
      target: { type: "string" },
      agent: { type: "string" },
      workflow: { type: "string" },
      quality: { type: "string" },
      skills: { type: "string" },
      yes: { type: "boolean" },
      "dry-run": { type: "boolean" },
      recover: { type: "boolean" },
      json: { type: "boolean" },
      help: { type: "boolean" },
      version: { type: "boolean" },
    },
  });
  if (values.help) {
    console.log(help);
    return;
  }
  if (values.version) {
    console.log(VERSION);
    return;
  }
  const command = positionals[0];
  if (
    positionals.length !== 1 ||
    !["init", "doctor", "upgrade"].includes(command ?? "")
  )
    throw Error(help);
  let root = path.resolve(values.target ?? process.cwd());
  if (command === "upgrade") {
    if (values.recover) {
      if (values["dry-run"])
        throw Error("Recovery cannot be combined with dry-run.");
      recover(root);
      console.log("Upgrade rolled back. Inspect the cause before retrying.");
      return;
    }
    const changes = prepareUpgrade(
      root,
      values.baseline ? path.resolve(values.baseline) : undefined,
    );
    for (const c of changes.filter((c) => c.action !== "keep"))
      console.log(`${c.action.toUpperCase()} ${c.path}: ${c.reason}`);
    if (changes.some((c) => c.action === "conflict")) {
      process.exitCode = 1;
      return;
    }
    if (!values["dry-run"]) upgrade(root, changes);
    console.log(
      values["dry-run"]
        ? "Upgrade preview only; target unchanged."
        : "Upgrade validated and committed locally.",
    );
    return;
  }
  if (values.baseline) throw Error("--baseline is only supported by upgrade.");
  if (command === "doctor") {
    if (
      values.recover ||
      values.yes ||
      values["dry-run"] ||
      Object.keys(DEFAULTS).some(
        (k) => values[k as keyof typeof values] !== undefined,
      )
    )
      throw Error("Doctor accepts only --target and --json.");
    const result = doctor(root);
    console.log(
      values.json
        ? JSON.stringify(result, null, 2)
        : "AI Engineering Harness Doctor\n" +
            result.checks
              .map(
                (c) =>
                  `${c.status.padEnd(4)} ${c.id}: ${c.message}${c.fix && c.status !== "PASS" ? " Fix: " + c.fix : ""}`,
              )
              .join("\n") +
            "\nHarness status: " +
            result.status,
    );
    process.exitCode = result.status === "UNHEALTHY" ? 1 : 0;
    return;
  }
  if (!nodeSupported(process.versions.node))
    throw Error("Unsupported Node runtime: use Node >=20.19 and <25.");
  if (values.json) throw Error("--json is supported by doctor.");
  if (values.recover) {
    if (values["dry-run"])
      throw Error("Recovery cannot be combined with --dry-run.");
    recover(root);
    console.log("Installation rolled back. Review the cause, then rerun init.");
    return;
  }
  const saved = read(root, CONFIG_PATH);
  const choices: Partial<Selection> =
    saved === null ? {} : config(JSON.parse(saved));
  for (const key of Object.keys(DEFAULTS) as (keyof Selection)[])
    if (values[key] !== undefined) choices[key] = values[key];
  if (!values.yes && !values["dry-run"]) {
    if (!process.stdin.isTTY || !process.stdout.isTTY)
      throw Error("Non-interactive init requires --yes or --dry-run.");
    const terminal = createInterface({
      input: process.stdin,
      output: process.stdout,
    });
    try {
      console.log("AI Engineering Harness");
      for (const key of Object.keys(DEFAULTS) as (keyof Selection)[]) {
        const options: readonly string[] =
          key === "agent" ? AGENTS : [DEFAULTS[key]];
        const answer = await terminal.question(
          `${key}: ${options.map((v, i) => `[${i + 1}] ${v.replace("codex", "Codex").replace("copilot-ide", "GitHub Copilot IDE only").replace("copilot", "GitHub Copilot CLI")}`).join("; ")} (Enter: ${choices[key] ?? DEFAULTS[key]}): `,
        );
        const chosen = answer
          ? (options[Number(answer) - 1] ?? answer)
          : (choices[key] ?? DEFAULTS[key]);
        if (!options.includes(chosen))
          throw Error(`Unsupported ${key} choice.`);
        choices[key] = chosen;
      }
      const target = await terminal.question(`Target directory [${root}]: `);
      if (target) root = path.resolve(target);
      console.log(
        `Install ${choices.agent} + OpenSpec integration + strict engineering baseline + Engineering Pack in ${root}; task execution profiles are selected through the Python Advisor`,
      );
      const confirm = await terminal.question(
        "Initialize this directory? [y/N] ",
      );
      if (!/^y(es)?$/i.test(confirm)) {
        console.log("Cancelled.");
        return;
      }
    } finally {
      terminal.close();
    }
  }
  const changes = prepare(root, choices, Boolean(values["dry-run"]));
  console.log(`${values["dry-run"] ? "Preview" : "Installation"}: ${root}`);
  for (const c of changes.filter((c) => c.action !== "keep"))
    console.log(
      `${c.action.toUpperCase()} ${c.path}${c.action === "conflict" ? ": " + c.reason : ""}`,
    );
  console.log(
    `${changes.filter((c) => c.action === "keep").length} existing files preserved or already current.`,
  );
  if (changes.some((c) => c.action === "conflict")) {
    process.exitCode = 1;
    return;
  }
  if (values["dry-run"]) {
    console.log(
      "OpenSpec: official init for selected agents will run in isolated staging on apply; generated files will be checked for conflicts. No target changes made.",
    );
    return;
  }
  install(root, changes);
  console.log(
    "Harness initialized. Run specreceipt doctor. Project onboarding remains required before application work.",
  );
}
main().catch((error) => {
  console.error(error instanceof Error ? error.message : "Command failed.");
  process.exitCode = 1;
});
