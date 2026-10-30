import * as fs from "node:fs";
import { parse as parseYaml } from "yaml";
import * as path from "node:path";
import * as os from "node:os";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import {
  BEGIN,
  END,
  OPENSPEC_VERSION,
  type Asset,
  hasCodex,
  hasCopilot,
} from "./core.js";
import { read, safe, walk } from "./filesystem.js";
export const PACKAGE_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
export const KIT = path.join(PACKAGE_ROOT, "assets/kit");
const adaptiveInstructions = `For eligible compact FAST tasks, follow docs/HARNESS.md#compact-fast-journey: workflow propose renders the canonical task/context/check bundle; record the actual combined answer with workflow confirm --expected, use run and guarded host-role submissions, then obtain separate workflow accept --expected after current evidence/review. The current IDE host needs no nested agent CLI. Developer lifecycle commands and manual JSON edits are not required. Legacy installations use workflow migrate preview and one explicit project decision; formal and stricter requirements remain authoritative.
The Python Engine owns task workflow policy and OpenSpec requirements. For adaptive tasks, use specreceipt workflow assess TASK-ID --facts FILE; present its actual recommendation, policy minimum and plan, then wait for explicit developer confirmation before workflow confirm. Never treat a recommendation as approval.
FAST/STANDARD use concise specifications and plans without a task OpenSpec change unless linked requirements or project policy require it. STRICT retains required OpenSpec sources and all quality gates. Preserve legacy task requirements. Installing the OpenSpec integration does not select a task execution profile. The strict policy in .harness/quality.json is the engineering baseline, not the task execution-profile minimum; Python enforces .harness/workflow-policy.json and task requirements.
Keep readiness, required checks, substantive review and separate final developer approval after VERIFIED and before DONE. Before asking for final DONE, run specreceipt approval-package TASK-ID --format markdown, show the developer its linked spec, plan, changed files, current evidence and review, and briefly explain the exact result, limitations and what DONE approves. A package is not approval or proof the developer saw it; if the command blocks, do not ask for DONE.`;
const investigationInstructions = `Navigation follows .harness/navigation.json: source uses targeted source search without graph setup; required invokes only selected providers; absent policy retains both legacy providers. Navigation never waives quality gates.
For repository stories, inspect the active host's available MCP tools and use relevant already-connected read-only tools within the user's authorized task. Compare results with exact code and approved requirements; record bounded source/revision references, contradictions and gaps with specreceipt investigation record TASK-ID --file FILE, then run specreceipt investigation check TASK-ID. Configuration alone does not prove access. Optional absence is NO_MCP or CODE_ONLY; project-required missing or stale sources block dependent claims. Never start a server, invoke a write tool or call an agent-reported trace authenticated proof.`;
export const codexBlock = `${BEGIN}
# AI Engineering Harness
Select relevant roles from skill metadata or specreceipt skills; load only those roles. Use [the engineering guide](docs/HARNESS.md#reference-navigation) for the applicable procedure, not a full upfront read.
Before new implementation, present the concrete spec/plan and obtain explicit approval; the initial request, silence and setup success are not approval. Renew approval for material changes.
${adaptiveInstructions}
${investigationInstructions}
At protected work boundaries require current readiness. For compact tasks run performs mechanical progression and unchanged resume; for formal tasks reconcile with specreceipt resume and inspect status/next.
Preserve project instructions and user changes. Never claim checks passed without execution evidence.
Strict policy: [.harness/quality.json](.harness/quality.json). Installation health does not imply application readiness.
${END}`;
export const copilotBlock = `${BEGIN}
# AI Engineering Harness
Read AGENTS.md at the repository root before work; resolve all paths in this paragraph from that root. Discover roles with specreceipt skills and load only relevant .agents/skills/<role>/SKILL.md files. If the IDE does not discover that directory, open the selected Skill file explicitly.
Use the shared workflow guide docs/HARNESS.md#reference-navigation only as needed. All Harness approvals and verification remain required; Copilot tool permission is not developer approval.
${adaptiveInstructions}
${investigationInstructions}
When OpenSpec is required, use official OpenSpec /opsx-* prompts in .github/prompts. Do not infer approval from a request to implement.
${END}`;
export interface Command {
  file: string;
  prefix: string[];
}
export function invoke(
  command: Command,
  args: string[],
  cwd: string,
  env: NodeJS.ProcessEnv = process.env,
  timeout = 60000,
) {
  try { command = nativeCommand(command, env); }
  catch (error) { return { pid: 0, output: [], stdout: "", stderr: String(error), status: null, signal: null, error: error as Error }; }
  return spawnSync(command.file, [...command.prefix, ...args], {
    cwd,
    env,
    encoding: "utf8",
    timeout,
    maxBuffer: 1024 * 1024,
    stdio: ["ignore", "pipe", "pipe"],
    shell: false,
    windowsHide: true,
  });
}
export function nativeCommand(command: Command, env: NodeJS.ProcessEnv = process.env): Command {
  if (process.platform !== "win32" || !/\.(cmd|bat)$/i.test(command.file)) return command;
  const name = path.basename(command.file).replace(/\.(cmd|bat)$/i, "");
  const packages: Record<string, string> = { npm: "npm", npx: "npm", codegraph: "@colbymchenry/codegraph", openspec: "@fission-ai/openspec", codex: "@openai/codex", copilot: "@github/copilot", specreceipt: "specreceipt" };
  if (!packages[name]) throw Error("Use a native executable or explicit interpreter instead of a batch shim: " + name);
  const parent = path.dirname(command.file);
  const base = path.basename(parent) === ".bin" ? path.dirname(parent) : path.join(parent, "node_modules");
  const folder = path.join(base, packages[name]!);
  const bins = JSON.parse(fs.readFileSync(path.join(folder, "package.json"), "utf8")).bin;
  const entry = path.resolve(folder, typeof bins === "string" ? bins : bins[name]);
  if (!entry.startsWith(path.resolve(folder) + path.sep) || !fs.statSync(entry).isFile() || !fs.realpathSync(entry).startsWith(fs.realpathSync(folder) + path.sep)) throw Error("Invalid package entry point");
  const node = executable("node", env);
  if (!node) throw Error("Node is required for " + name);
  return { file: node, prefix: [entry, ...command.prefix] };
}

function environmentValue(env: NodeJS.ProcessEnv, name: string): string | undefined {
  if (env[name] !== undefined || process.platform !== "win32") return env[name];
  const key = Object.keys(env).find(key => key.toLowerCase() === name.toLowerCase());
  return key === undefined ? undefined : env[key];
}

export function pythonCommand(env: NodeJS.ProcessEnv = process.env): Command | null {
  const override = environmentValue(env, "HARNESS_PYTHON");
  if (override) return { file: override, prefix: [] };
  if (process.platform === "win32") {
    const runtime = environmentValue(env, "HARNESS_RUNTIME_DIR") ?? path.join(environmentValue(env, "LOCALAPPDATA") ?? path.join(os.homedir(), "AppData", "Local"), "harness", "runtime");
    try {
      const file = fs.readFileSync(path.join(runtime, "python-path.txt"), "utf8").trim();
      if (path.isAbsolute(file) && fs.statSync(file).isFile()) return { file, prefix: [] };
    } catch { /* Continue to existing native installations. */ }
  }
  const file = executable("python3", env) ?? executable("python", env);
  if (file) return { file, prefix: [] };
  const launcher = process.platform === "win32" && executable("py", env);
  return launcher ? { file: launcher, prefix: ["-3"] } : null;
}
export function executable(name: string, env: NodeJS.ProcessEnv = process.env): string | null {
  for (const folder of (environmentValue(env, "PATH") ?? "").split(path.delimiter)) {
    if (!path.isAbsolute(folder)) continue;
    for (const ext of process.platform === "win32"
      ? [".exe", ".cmd", ""]
      : [""]) {
      const candidate = path.join(folder, name + ext);
      if (process.platform === "win32" && /^(python3?|py)$/.test(name) && /[\\/]Microsoft[\\/]WindowsApps[\\/]/i.test(candidate)) continue;
      try {
        if (fs.statSync(candidate).isFile()) {
          fs.accessSync(candidate, fs.constants.X_OK);
          return candidate;
        }
      } catch {}
    }
  }
  return null;
}
export function openspec(root: string): Command | null {
  // Resolve known npm JS entry directly; never use cmd.exe/shell interpolation on Windows.
  for (const folder of [
    ".harness/tools/openspec/node_modules/@fission-ai/openspec",
    "node_modules/@fission-ai/openspec",
  ]) {
    const entry = path.join(root, folder, "bin/openspec.js");
    if (fs.existsSync(entry))
      return { file: process.execPath, prefix: [entry] };
  }
  const binary = executable("openspec");
  if (!binary) return null;
  try { return nativeCommand({ file: binary, prefix: [] }); }
  catch { return null; }
}
export function probeOpenSpec(root: string): {
  command: Command | null;
  state: "missing" | "incompatible" | "ready";
  version?: string;
} {
  const command = openspec(root);
  if (!command) return { command: null, state: "missing" };
  let cwd = root;
  while (!fs.existsSync(cwd)) cwd = path.dirname(cwd);
  const r = invoke(command, ["--version"], cwd, {
    ...process.env,
    OPENSPEC_TELEMETRY: "0",
    DO_NOT_TRACK: "1",
    OPENSPEC_NO_UPDATE_CHECK: "1",
  });
  const version = r.stdout?.trim();
  return {
    command,
    state:
      r.status === 0 && version === OPENSPEC_VERSION ? "ready" : "incompatible",
    version: version && /^\d+\.\d+\.\d+$/.test(version) ? version : "unknown",
  };
}
export const installHint = `Install locally with: npm install --prefix .harness/tools/openspec --ignore-scripts --no-audit --no-fund @fission-ai/openspec@${OPENSPEC_VERSION}`;
export function stageOpenSpec(root: string, agent = "codex"): Asset[] {
  const check = probeOpenSpec(root);
  if (check.state !== "ready" || !check.command)
    throw new Error(
      `OpenSpec ${OPENSPEC_VERSION} is ${check.state}. ${installHint}`,
    );
  const stage = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-openspec-")),
  );
  try {
    const home = path.join(stage, "home");
    const project = path.join(stage, "project");
    fs.mkdirSync(home);
    fs.mkdirSync(project);
    const env = {
      ...process.env,
      HOME: home,
      USERPROFILE: home,
      XDG_CONFIG_HOME: path.join(home, ".config"),
      OPENSPEC_TELEMETRY: "0",
      DO_NOT_TRACK: "1",
      OPENSPEC_NO_UPDATE_CHECK: "1",
    };
    const result = invoke(
      check.command,
      [
        "init",
        "--tools",
        [
          hasCodex(agent) ? "codex" : "",
          hasCopilot(agent) ? "github-copilot" : "",
        ]
          .filter(Boolean)
          .join(","),
        ...(hasCopilot(agent) ? ["--no-copilot-cloud"] : []),
      ],
      project,
      env,
    );
    if (result.status !== 0)
      throw new Error(
        "Official OpenSpec init failed in staging. Check supported CLI/runtime; target was not changed.",
      );
    const existingConfig = read(root, "openspec/config.yaml");
    const existing = existingConfig !== null;
    if (existing) {
      try {
        const value = parseYaml(existingConfig, { maxAliasCount: 10 });
        if (!value || typeof value.schema !== "string" || !value.schema.trim())
          throw Error();
      } catch {
        throw new Error(
          "Existing OpenSpec config is invalid; repair its YAML/schema before initialization.",
        );
      }
    }

    if (!existing && fs.existsSync(safe(root, "openspec")))
      throw new Error(
        "Older/custom OpenSpec layout detected. Migrate it with the official OpenSpec CLI before init; existing sources were preserved.",
      );
    return walk(project)
      .filter(
        (rel) =>
          !(hasCodex(agent) && rel.startsWith(".github/skills/openspec-")),
      )
      .map((rel) => {
        if (
          ![
            "openspec/config.yaml",
            "openspec/changes/archive/.gitkeep",
            "openspec/specs/.gitkeep",
          ].includes(rel) &&
          rel !== ".agents/skills/.openspec-target" &&
          !rel.startsWith(".agents/skills/openspec-") &&
          !(
            hasCopilot(agent) &&
            /^\.github\/(skills\/openspec-[a-z-]+\/SKILL\.md|prompts\/opsx-[a-z-]+\.prompt\.md)$/.test(
              rel,
            )
          )
        )
          throw new Error(
            "Unexpected official OpenSpec output; adapter compatibility review required.",
          );
        const content = fs.readFileSync(path.join(project, rel), "utf8");
        // Existing OpenSpec project owns all customization. Add only missing artifacts.
        return {
          path: rel,
          content: existing ? (read(root, rel) ?? content) : content,
          owner: rel === "openspec/config.yaml" ? "project" : "openspec",
        } as Asset;
      });
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
  }
}
export function kitAssets(): Asset[] {
  return walk(KIT)
    .filter((rel) => rel !== "AGENTS.md")
    .map((rel) => ({
      path: rel,
      content: fs.readFileSync(path.join(KIT, rel), "utf8"),
      owner:
        rel.startsWith(".harness/") ||
        [
          "docs/TECH_SPEC.md",
          "docs/ARCHITECTURE.md",
          "docs/DECISION_QUEUE.md",
        ].includes(rel)
          ? "project"
          : "harness",
      mode: rel === "harness" || rel.endsWith(".sh") ? 0o755 : 0o644,
    }));
}
