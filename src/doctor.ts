import { probeCopilot } from "./copilot.js";
import { execute, request } from "./engine.js";
import * as fs from "node:fs";
import * as path from "node:path";
import { parse as parseYaml } from "yaml";
import { parse as parseToml } from "smol-toml";
import {
  CONFIG_PATH,
  MANIFEST_PATH,
  JOURNAL_PATH,
  OPENSPEC_VERSION,
  config,
  hasCodex,
  hasCopilot,
  needsCopilotCLI,
  QUALITY,
  nodeSupported,
  health,
  managedSection,
  type Diagnostic,
} from "./core.js";
import { hash, manifest, read, safe, walk } from "./filesystem.js";
import {
  KIT,
  PACKAGE_ROOT,
  kitAssets,
  probeOpenSpec,
  installHint,
  executable,
  invoke,
  pythonCommand,
} from "./integrations.js";
class DiagnosticIssue extends Error {}
export function doctor(root: string) {
  root = path.resolve(root);
  const checks: Diagnostic[] = [];
  const add = (
    id: string,
    status: Diagnostic["status"],
    message: string,
    fix?: string,
  ) => checks.push({ id, status, message, ...(fix ? { fix } : {}) });
  const test = (id: string, fn: () => void, fix: string) => {
    try {
      fn();
      add(id, "PASS", "Validated");
    } catch (error) {
      add(
        id,
        "FAIL",
        error instanceof DiagnosticIssue
          ? error.message
          : `${id} is missing, invalid or conflicting; dependent workflows cannot rely on it.`,
        fix,
      );
    }
  };
  add(
    "node",
    nodeSupported(process.versions.node) ? "PASS" : "FAIL",
    "Requires Node >=20.19 and <25.",
    "Use a supported Node runtime.",
  );
  test(
    "package",
    () => {
      const binaries = JSON.parse(
        fs.readFileSync(
          path.join(PACKAGE_ROOT, "assets/cli-integrity.json"),
          "utf8",
        ),
      ) as Record<string, string>;
      for (const [rel, sum] of Object.entries(binaries)) {
        const code = read(PACKAGE_ROOT, rel);
        if (code === null || hash(code) !== sum) throw Error();
      }
      const data = JSON.parse(
        fs.readFileSync(
          path.join(PACKAGE_ROOT, "assets/integrity.json"),
          "utf8",
        ),
      ) as Record<string, string>;
      if (!Object.keys(data).length) throw Error();
      for (const [rel, sum] of Object.entries(data)) {
        const content = read(KIT, rel);
        if (content === null || hash(content) !== sum) throw Error();
      }
    },
    "Reinstall the verified harness package.",
  );
  test(
    "repository",
    () => {
      if (!fs.statSync(root).isDirectory()) throw Error();
      fs.accessSync(root, fs.constants.R_OK);
      safe(root, CONFIG_PATH);
    },
    "Select an accessible directory without symlink ancestors.",
  );
  if (checks.find((c) => c.id === "repository")?.status === "FAIL")
    return { status: health(checks), checks };
  let agent = "";
  test(
    "configuration",
    () => {
      agent = config(JSON.parse(read(root, CONFIG_PATH) ?? "null")).agent;
    },
    "Run init; preserve and reconcile invalid product.json first.",
  );
  test(
    "transaction",
    () => {
      if (
        read(root, JOURNAL_PATH) !== null ||
        fs.existsSync(safe(root, ".harness/installation.lock"))
      )
        throw Error();
    },
    "Inspect pending operations; use init --recover only after confirming no installer is running.",
  );
  test(
    "ownership",
    () => {
      const owned = manifest(root);
      if (!owned || !Object.keys(owned.files).length) throw Error();
      for (const asset of kitAssets().filter((a) => a.owner === "harness"))
        if (!owned.files[asset.path])
          throw new DiagnosticIssue(`Missing ownership entry: ${asset.path}`);
      for (const required of [
        "AGENTS.md",
        CONFIG_PATH,
        ".harness/quality.json",
      ])
        if (!owned.files[required]) throw Error();
      for (const [rel, item] of Object.entries(owned.files)) {
        const content = read(root, rel);
        if (content === null)
          throw new DiagnosticIssue(`Missing managed file: ${rel}`);
        if (item.owner === "project") continue;
        const observed =
          item.owner === "shared" ? managedSection(content) : content;
        if (observed === null || hash(observed) !== item.hash)
          throw new DiagnosticIssue(`Managed content drift: ${rel}`);
        if (
          process.platform !== "win32" &&
          (rel === "harness" || rel.endsWith(".sh")) &&
          !(fs.statSync(safe(root, rel)).mode & 0o111)
        )
          throw Error();
      }
    },
    "A managed file is missing or modified. Compare installation-manifest.json with your changes; restore or merge intentionally before init.",
  );
  if (hasCodex(agent)) {
    test(
      "codex",
      () => {
        if (
          !managedSection(read(root, "AGENTS.md") ?? "") ||
          read(root, "AGENTS.override.md") !== null
        )
          throw Error();
      },
      "Restore the managed AGENTS.md section; reconcile any AGENTS.override.md that suppresses it.",
    );
    test(
      "codex-config",
      () => {
        const content = read(root, ".codex/config.toml");
        if (content !== null) parseToml(content);
      },
      "Repair .codex/config.toml syntax or reconcile symlinks; existing settings were not rewritten.",
    );
    add(
      "codex-authentication",
      "SKIP",
      "File integration checked; authenticated host behavior requires a live Codex session.",
    );
  }
  if (hasCopilot(agent)) {
    test(
      "copilot-instructions",
      () => {
        if (
          !managedSection(
            read(root, ".github/copilot-instructions.md") ?? "",
          ) ||
          !managedSection(read(root, "AGENTS.md") ?? "")
        )
          throw Error();
      },
      "Restore the managed Copilot bridge and shared AGENTS.md instructions using init.",
    );
    test(
      "copilot-openspec",
      () => {
        for (const name of [
          "propose",
          "apply",
          "archive",
          "explore",
          "sync",
          "update",
        ])
          if (!read(root, `.github/prompts/opsx-${name}.prompt.md`))
            throw Error();
      },
      "Run init for the selected Copilot agent; official OpenSpec prompts are required.",
    );
    if (needsCopilotCLI(agent)) {
      const probe = probeCopilot(root);
      add(
        "copilot-cli",
        probe.state === "ready" ? "PASS" : "FAIL",
        `${probe.state}; ${probe.version ?? "CLI unavailable"}`,
        "Install official stable GitHub Copilot CLI, or select copilot-ide for IDE-only use. Required missing capabilities: " +
          probe.missing.join(", "),
      );
    } else
      add("copilot-cli", "SKIP", "IDE-only mode does not require Copilot CLI.");
    test(
      "copilot-skills",
      () => {
        const folder = safe(root, ".github/skills");
        if (fs.existsSync(folder))
          for (const rel of walk(folder).filter((p) =>
            p.endsWith("/SKILL.md"),
          )) {
            const metadata = /^---\r?\n([\s\S]*?)\r?\n---/.exec(
              read(folder, rel) ?? "",
            )?.[1];
            const parsed = metadata
              ? parseYaml(metadata, { maxAliasCount: 10 })
              : null;
            if (
              !parsed ||
              typeof parsed.name !== "string" ||
              typeof parsed.description !== "string" ||
              !parsed.description.trim()
            )
              throw new DiagnosticIssue(
                `Invalid Copilot Skill metadata: ${rel}`,
              );
            if (read(root, `.agents/skills/${rel}`) !== null)
              add(
                "copilot-skill-overlap",
                "WARN",
                `Both Skill directories contain ${rel}. Existing files were preserved.`,
                "Review duplicate Skill variants explicitly; Harness does not delete user-owned OpenSpec files.",
              );
          }
      },
      "Repair Copilot Skill frontmatter and resolve custom integration conflicts.",
    );
    add(
      "copilot-authentication",
      "SKIP",
      "Doctor makes no model calls. CLI users: run copilot login and a permitted prompt; IDE users: sign in through the GitHub Copilot plugin.",
    );
    add(
      "copilot-ide",
      "SKIP",
      "Rider loading requires a live IDE check. Enable repository instructions; open the selected .agents/skills file explicitly if automatic discovery is unavailable.",
    );
  }
  test(
    "skills",
    () => {
      const folder = safe(root, ".agents/skills");
      const names = new Set<string>();
      let count = 0;
      for (const rel of walk(folder).filter((p) => p.endsWith("/SKILL.md"))) {
        const content = read(folder, rel)!;
        const metadata = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content)?.[1];
        if (!metadata)
          throw new DiagnosticIssue(`Missing Skill frontmatter: ${rel}`);
        const parsed = parseYaml(metadata, { maxAliasCount: 10 });
        const name = parsed?.name;
        if (
          typeof name !== "string" ||
          !/^[a-z][a-z0-9-]{0,63}$/.test(name) ||
          typeof parsed?.description !== "string" ||
          !parsed.description.trim() ||
          names.has(name)
        )
          throw new DiagnosticIssue(
            `Invalid or duplicate Skill metadata: ${rel}`,
          );
        names.add(name);
        count++;
        for (const link of content.matchAll(/\]\(([^)]+)\)/g)) {
          const value = link[1]!;
          if (/^(https?:|#|mailto:)/.test(value)) continue;
          const ref = value.split("#")[0]!;
          const dest = path.resolve(folder, path.dirname(rel), ref);
          const relative = path.relative(root, dest).split(path.sep).join("/");
          safe(root, relative);
          if (!fs.existsSync(dest)) throw Error();
        }
      }
      if (count < 18) throw Error();
    },
    "Restore missing Engineering Pack files/references and resolve duplicate or invalid Skill names.",
  );
  test(
    "quality",
    () => {
      const q = JSON.parse(read(root, ".harness/quality.json") ?? "null");
      if (JSON.stringify(q) !== JSON.stringify(QUALITY)) throw Error();
    },
    "Restore the strict engineering baseline; this does not set the task execution-profile minimum. Python enforces task policy in .harness/workflow-policy.json; configure project-specific checks separately in .harness/checks.json.",
  );
  try {
    const probe = probeOpenSpec(root);
    add(
      "openspec-cli",
      probe.state === "ready" ? "PASS" : "FAIL",
      `OpenSpec ${OPENSPEC_VERSION}: ${probe.state}.`,
      probe.state === "ready" ? undefined : installHint,
    );
  } catch {
    add("openspec-cli", "FAIL", "OpenSpec probe failed.", installHint);
  }
  test(
    "openspec-project",
    () => {
      const content = read(root, "openspec/config.yaml");
      if (!content) throw Error();
      const parsed = parseYaml(content, { maxAliasCount: 10 });
      if (
        !parsed ||
        typeof parsed !== "object" ||
        typeof parsed.schema !== "string" ||
        !parsed.schema.trim()
      )
        throw Error();
      const directories = [
        ".agents/skills",
        ...(hasCopilot(agent) ? [".github/skills"] : []),
      ];
      if (
        !directories.some(
          (dir) =>
            fs.existsSync(safe(root, dir)) &&
            walk(safe(root, dir)).some(
              (p) => p.startsWith("openspec-") && p.endsWith("/SKILL.md"),
            ),
        )
      )
        throw Error();
    },
    "Use supported official OpenSpec init for selected agents; preserve and migrate older layouts explicitly.",
  );
  add(
    "mcp",
    "SKIP",
    "This pack requires no MCP server. Existing Codex/MCP settings are preserved.",
  );
  // Installation diagnosis uses the same requirement resolver as paid-launch checks.
  const execution = executionDiagnostics({ cwd: root, agent: hasCodex(agent) ? "codex" : needsCopilotCLI(agent) ? "copilot" : "copilot-ide" }, true);
  checks.push(...execution.checks.filter(c => c.id !== "agent-cli" || !hasCopilot(agent)));
  test(
    "legacy-runtime",
    () => {
      const result = execute(root, ["validate"]);
      if (result.exitCode)
        throw new DiagnosticIssue(
          "Project-installed Python validation failed.",
        );
      add(
        "application-readiness",
        "SKIP",
        "Installation validation does not grant application approval; run readiness TASK-ID.",
      );
    },
    "Install native Python >=3.11 or set HARNESS_PYTHON; restore the installed runtime or run upgrade for legacy/version mismatches.",
  );
  return { status: health(checks), checks };
}

/** Execution checks share doctor diagnostics; no model calls, installs or MCP activation. */
export type Requirement = "REQUIRED" | "OPTIONAL" | "NOT_APPLICABLE";
export interface ExecutionOptions {
  cwd: string;
  agent: "codex" | "copilot" | "copilot-ide";
  env?: NodeJS.ProcessEnv;
  command?: import("./integrations.js").Command;
  taskId?: string;
  shell?: { file: string; login: boolean };
  ignoreUserConfig?: boolean;
  builtinMcpsDisabled?: boolean;
  // An already-connected host may perform a read-only tools/list, never start a server.
  mcpProbe?: () => { server: "codegraph"; available: boolean; tools: string[] };
  // Host supplied observation; configuration alone is never tool availability.
  mcpInventory?: () => { server: string; available: boolean; readOnlyTools: string[] }[];
}
export function agentEnvironment(agent: string, input: NodeJS.ProcessEnv) {
  const env = { ...input };
  if (agent === "copilot") {
    delete env.COPILOT_ALLOW_ALL;
    delete env.COPILOT_ASSISTED_APPROVAL;
    delete env.BASH_ENV;
  }
  return env;
}
export function executionPreflight(options: ExecutionOptions) {
  return executionDiagnostics(options);
}
function executionDiagnostics(options: ExecutionOptions, installation = false) {
  const started = performance.now();
  const root = path.resolve(options.cwd);
  const env = agentEnvironment(options.agent, options.env ?? process.env);
  let toolEnv = { ...env };
  const checks: (Diagnostic & { requirement: Requirement })[] = [];
  const add = (id: string, requirement: Requirement, ok: boolean, message: string, fix?: string) =>
    checks.push({ id, requirement, status: requirement === "NOT_APPLICABLE" || ok ? "PASS" : requirement === "REQUIRED" ? "FAIL" : "WARN", message, ...(!ok && fix ? { fix } : {}) });
  if (options.agent === "copilot-ide") {
    add("agent-cli", "NOT_APPLICABLE", true, "IDE-only execution; no agent CLI launch.");
    return { status: "PASS" as const, checks, elapsedMs: performance.now() - started };
  }
  let mcpConfigured = false;
  let mcpDisabled = false;
  const requiredMcps = new Set<string>();
  if (!installation && options.agent === "codex") {
    try {
      const configs = [
        ...(!options.ignoreUserConfig && (env.CODEX_HOME || env.HOME) ? [path.join(env.CODEX_HOME ?? path.join(env.HOME!, ".codex"), "config.toml")] : []),
        path.join(root, ".codex/config.toml"),
      ];
      const effectiveServers: Record<string, any> = {};
      for (const file of configs) {
        if (!fs.existsSync(file)) continue;
        const cfg = parseToml(fs.readFileSync(file, "utf8"));
        // Unknown policy transformations cannot be attested as the observed shell environment.
        if (cfg.shell_environment_policy && Object.keys(cfg.shell_environment_policy as object).length)
          throw Error("environment-policy");
        const servers = cfg.mcp_servers as Record<string, any> | undefined;
        for (const [name, server] of Object.entries(servers ?? {})) effectiveServers[name] = { ...effectiveServers[name], ...server };
      }
      for (const [name, server] of Object.entries(effectiveServers)) if (server.required === true && server.enabled !== false) requiredMcps.add(name);
      const entry = effectiveServers.codegraph;
      if (entry) { mcpConfigured = true; mcpDisabled = entry.enabled === false; }
      add("agent-settings", "REQUIRED", true, "Effective Codex config checked; user-config ignore flag respected.");
    } catch {
      add("agent-settings", "REQUIRED", false, "Invalid configuration or unsupported shell environment policy; actual tool environment cannot be attested.", "Use a supported default environment configuration or extend the preflight contract before launching; do not bypass policy.");
    }
  }
  const shell = installation ? undefined : options.shell ?? (options.agent === "codex" && process.platform !== "win32" ? { file: env.SHELL ?? "/bin/sh", login: true } : undefined);
  if (shell) {
    const quote = (s: string) => "'" + s.replaceAll("'", "'\\''") + "'";
    // Capture only inside this process. Environment values never enter diagnostics/evidence.
    const result = invoke({ file: shell.file, prefix: [] }, [shell.login ? "-lc" : "-c", `${quote(process.execPath)} -e 'process.stdout.write(JSON.stringify(process.env))'`], root, env, 5000);
    try {
      if (result.status !== 0) throw Error();
      const observed = JSON.parse(result.stdout);
      if (!observed || typeof observed !== "object" || Object.values(observed).some(v => typeof v !== "string")) throw Error();
      toolEnv = observed;
      add("agent-shell", "REQUIRED", true, "Dependency probes use the observed shell environment.");
    } catch {
      add("agent-shell", "REQUIRED", false, "Selected shell environment probe failed.", "Check shell startup and runtime access in the selected environment.");
    }
  }
  const cmd = options.command ?? (() => { const file = executable(options.agent, env); return file ? { file, prefix: [] } : null; })();
  if (!installation && options.agent === "copilot") {
    const probe = probeCopilot(root, cmd ?? undefined, env);
    add("agent-cli", "REQUIRED", probe.state === "ready", `Copilot CLI ${probe.state}.`, "Provide a compatible Copilot CLI in the launch environment; IDE-only use does not need it.");
  } else if (!installation) {
    const version = cmd && invoke(cmd, ["--version"], root, env, 5000);
    const help = cmd && invoke(cmd, ["exec", "--help"], root, env, 5000);
    const flags = ["--json", "--sandbox", "--cd", ...(options.ignoreUserConfig ? ["--ignore-user-config"] : [])];
    add("agent-cli", "REQUIRED", !!(version && help && version.status === 0 && /codex/i.test(version.stdout) && help.status === 0 && flags.every(f => help.stdout.includes(f))), "Codex CLI version and required execution capabilities checked.", "Provide a compatible Codex CLI in the launch environment.");
  }
  const installed = fs.existsSync(path.join(root, "harnesslib/cli.py"));
  // A failed requirement lookup is not permission to treat dependencies as optional.
  let navigation = installed || !!options.taskId || fs.existsSync(path.join(root, ".harness/product.json"));
  let openspecRequired = navigation;
  if (installed) {
    const python = pythonCommand(toolEnv);
    const version = python && invoke(python, ["--version"], root, toolEnv, 5000);
    const match = version && /Python (\d+)\.(\d+)/.exec(version.stdout || version.stderr);
    add("python", "REQUIRED", !!(version && version.status === 0 && match && Number(match[1]) === 3 && Number(match[2]) >= 11), "Python >=3.11 required by installed engine.", "Expose a compatible Python runtime in the actual tool environment.");
    try {
      const result = request(root, ["doctor", "--execution-requirements", ...(options.taskId ? ["--task", options.taskId] : [])], root, toolEnv);
      if (result.exitCode || result.data?.result !== "PASS") throw Error();
      navigation = result.data.navigation_cli_required;
      openspecRequired = result.data.openspec_required;
      add("execution-requirements", "REQUIRED", true, result.data.reason);
      for (const dependency of result.data.executables ?? []) {
        const name = dependency.executable as string;
        const file = path.isAbsolute(name) ? name : name.includes("/") ? path.resolve(root, name) : executable(name, toolEnv);
        let ok = false;
        try { if (file && fs.statSync(file).isFile()) { fs.accessSync(file, fs.constants.X_OK); ok = true; } } catch {}
        if (ok && ["node","npm","npx","python3","python"].includes(path.basename(name))) {
          // Application runtime versions are project-owned, not Harness's Node/Python pins.
          const version = invoke({ file: file!, prefix: [] }, ["--version"], root, toolEnv, 5000);
          ok = version.status === 0;
        }
        add("check-runtime:" + dependency.check, "REQUIRED", ok, ok ? "Required check executable available." : "Required check executable missing, inaccessible or incompatible.", "Expose the approved check runtime in the agent tool environment before launch.");
      }
    } catch {
      add("execution-requirements", "REQUIRED", false, "Python execution requirements unavailable.", "Restore Python >=3.11 and the selected task/engine in this environment.");
    }
  } else if (options.taskId || fs.existsSync(path.join(root, ".harness/product.json"))) {
    add("execution-requirements", "REQUIRED", false, "Selected Harness engine is missing.", "Restore the installed engine before launching.");
  }
  for (const [name, rel, args, expected, required] of [
    ["codegraph", ".harness/tools/codegraph/node_modules/.bin/codegraph", ["version"], "1.6.2", navigation],
    ["graphify", ".harness/tools/graphify/bin/graphify", ["--version"], "graphify 0.9.27", navigation],
    ["openspec", ".harness/tools/openspec/node_modules/.bin/openspec", ["--version"], OPENSPEC_VERSION, openspecRequired],
  ] as const) {
    const nativeRel = process.platform === "win32" ? (name === "graphify" ? ".harness/tools/graphify/Scripts/graphify.exe" : rel + ".cmd") : rel;
    const local = path.join(root, nativeRel);
    let binary: string | null = null;
    let managed = false;
    let base: string | null = null;
    try { base = safe(root, ".harness/tools/" + name); } catch { managed = true; }
    if (base) {
      try { fs.lstatSync(local); managed = true; } catch (error: any) { if (error.code !== "ENOENT") managed = true; }
      if (managed) {
        try {
          if (fs.statSync(local).isFile() && fs.realpathSync(local).startsWith(fs.realpathSync(base) + path.sep)) binary = local;
        } catch { /* Invalid managed entry blocks PATH fallback, like Python tool_paths.binary. */ }
      } else binary = executable(name, toolEnv);
    }
    let probe;
    try { probe = binary && invoke({ file: binary, prefix: [] }, [...args], root, toolEnv, 5000); } catch { probe = null; }
    const ok = !!probe && probe.status === 0 && probe.stdout.trim() === expected;
    add(name + "-cli", required ? "REQUIRED" : "OPTIONAL", ok,
      ok ? `${name} ${expected} available in tool environment.` : `${name} CLI missing, inaccessible or incompatible (expected ${expected}).`,
      required ? "Expose an approved compatible tool in the agent shell or project-local managed installation; no automatic installation." : "Use repository search when permitted; this does not waive mandatory CLI gates.");
  }
  if (installation) return { status: checks.some(c => c.status === "FAIL") ? "FAIL" as const : checks.some(c => c.status === "WARN") ? "WARN" as const : "PASS" as const, checks, elapsedMs: performance.now() - started };
  const search = executable("rg", toolEnv) ?? executable("git", toolEnv);
  const searchOk = !!search && invoke({ file: search, prefix: [] }, ["--version"], root, toolEnv, 5000).status === 0;
  add("repository-search", "OPTIONAL", searchOk, searchOk ? "Repository search fallback available; required graph gates still apply." : "No rg/git search executable detected; use host file search if available.");
  let mcp = mcpDisabled ? "disabled" : mcpConfigured ? "configured-unverified" : "not-exposed";
  // Copilot disables built-in MCPs, but does not disable explicitly connected custom servers.
  if (!mcpDisabled && options.mcpProbe) {
    try { const r = options.mcpProbe(); mcp = r.server === "codegraph" && r.available && r.tools.some(t => /^(codegraph[._-])?(query|search)$/.test(t)) ? "available-via-host" : "unavailable"; }
    catch { mcp = "unavailable"; }
  }
  add("codegraph-mcp", requiredMcps.has("codegraph") ? "REQUIRED" : "OPTIONAL", mcp === "available-via-host", `CodeGraph MCP: ${mcp}${options.builtinMcpsDisabled ? "; built-in MCPs disabled" : ""}. MCP never replaces a required CLI capability.`, "Connect/verify an authorized host integration if desired; configuration alone is not availability.");
  let observed: { server: string; available: boolean; readOnlyTools: string[] }[] = [];
  if (options.mcpInventory) {
    try {
      const inventory = options.mcpInventory();
      if (!Array.isArray(inventory) || inventory.length > 64 || inventory.some(item =>
        !item || typeof item.server !== "string" || !/^[a-zA-Z0-9_.-]{1,160}$/.test(item.server) ||
        typeof item.available !== "boolean" || !Array.isArray(item.readOnlyTools) ||
        item.readOnlyTools.length > 64 || item.readOnlyTools.some(tool => typeof tool !== "string" || !/^[a-zA-Z0-9_.-]{1,160}$/.test(tool))
      ) || new Set(inventory.map(item => item.server)).size !== inventory.length) throw Error();
      observed = inventory;
      add("host-mcp-inventory", "OPTIONAL", true, "Read-only host MCP inventory observed; relevance and query results still require an investigation report.");
    } catch {
      add("host-mcp-inventory", "OPTIONAL", false, "Host MCP inventory probe failed or returned invalid metadata.");
    }
  } else add("host-mcp-inventory", "OPTIONAL", false, "No host MCP inventory supplied; configured servers remain unverified.");
  for (const name of requiredMcps) if (name !== "codegraph") {
    const entry = observed.find(item => item.server === name);
    const available = !!(entry?.available && entry.readOnlyTools.length);
    add("required-mcp:" + name, "REQUIRED", available,
      available ? `Required MCP ${name} has host-observed read-only tools; task claims still need investigation evidence.` :
      `Required MCP ${name} is configured but no read-only host capability was observed.`,
      "Verify the existing host connection and a relevant read-only tool before paid execution.");
  }
  return { status: checks.some(c => c.status === "FAIL") ? "FAIL" as const : checks.some(c => c.status === "WARN") ? "WARN" as const : "PASS" as const, checks, elapsedMs: performance.now() - started };
}
/** Call immediately at the paid spawn boundary, including resumed runs. */
export function checkedAgentLaunch<T>(options: ExecutionOptions, launch: (env: NodeJS.ProcessEnv) => T): T {
  if (options.agent === "copilot-ide") throw Error("IDE-only mode has no paid CLI launch.");
  const env = agentEnvironment(options.agent, options.env ?? process.env);
  const result = executionPreflight({ ...options, env });
  if (result.status === "FAIL") throw Error("Agent preflight failed: " + result.checks.filter(c => c.status === "FAIL").map(c => c.id + ": " + c.message).join("; "));
  return launch(env);
}
