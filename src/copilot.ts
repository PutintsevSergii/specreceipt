/** Optional process transport. Python owns readiness, transitions and approvals. */
import { executionPreflight, agentEnvironment } from "./doctor.js";
import { spawn } from "node:child_process";
import * as path from "node:path";
import { executable, invoke, type Command } from "./integrations.js";
import { execute } from "./engine.js";
import { read } from "./filesystem.js";

const required = [
  "--prompt",
  "--output-format",
  "--allow-tool",
  "--deny-tool",
  "--no-auto-update",
  "--disallow-temp-dir",
  "--disable-builtin-mcps",
  "--no-bash-env",
];
export function probeCopilot(root: string, command?: Command, env: NodeJS.ProcessEnv = process.env) {
  const binary = executable("copilot", env);
  const cmd =
    command ??
    (binary && !binary.endsWith(".cmd") ? { file: binary, prefix: [] } : null);
  if (!cmd)
    return {
      state: "missing" as const,
      command: null,
      version: null,
      missing: required,
    };
  const version = invoke(cmd, ["--no-auto-update", "--version"], root, env, 5000);
  const help = invoke(cmd, ["--no-auto-update", "--help"], root, env, 5000);
  const missing = required.filter((flag) => !help.stdout?.includes(flag));
  return {
    state:
      version.status === 0 &&
      help.status === 0 &&
      /GitHub Copilot CLI/.test(version.stdout) &&
      !missing.length
        ? ("ready" as const)
        : ("incompatible" as const),
    command: cmd,
    version: version.stdout?.trim().split("\n")[0] ?? null,
    missing,
  };
}
export interface CopilotResult {
  status: "PASS" | "BLOCKED" | "FAIL";
  reason: string;
  exitCode: number | null;
  signal?: string | null;
  events: Record<string, any>[];
  stderr: string;
}
export interface CopilotOptions {
  cwd: string;
  prompt: string;
  allowTools?: string[];
  timeoutMs?: number;
  signal?: AbortSignal;
  command?: Command;
  env?: NodeJS.ProcessEnv;
  taskId?: string;
}
export function copilotArguments(prompt: string, permissions: string[] = []) {
  // Require named commands or explicit files. Never accept an unrestricted tool grant.
  for (const permission of permissions) {
    if (!/^(shell|write)\([^\r\n*]+\)$/.test(permission))
      throw Error(
        "Copilot permissions must name a command or a file; unrestricted grants are rejected.",
      );
  }
  return [
    "--no-auto-update",
    "--no-bash-env",
    "--disallow-temp-dir",
    "--disable-builtin-mcps",
    "--output-format",
    "json",
    ...permissions.map((p) => `--allow-tool=${p}`),
    "--prompt",
    prompt,
  ];
}
export async function runCopilot(
  options: CopilotOptions,
): Promise<CopilotResult> {
  const args = copilotArguments(options.prompt, options.allowTools);
  const timeoutMs = options.timeoutMs ?? 120000;
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1)
    throw Error("Positive timeout required.");
  const blocked = (reason: string): CopilotResult => ({
    status: "BLOCKED",
    reason,
    exitCode: null,
    events: [],
    stderr: "",
  });
  if (options.signal?.aborted) return blocked("cancelled");
  const env = agentEnvironment("copilot", options.env ?? process.env);
  const probe = probeCopilot(options.cwd, options.command, env);
  if (probe.state !== "ready" || !probe.command)
    return blocked(`copilot-${probe.state}`);
  const preflight = executionPreflight({ cwd: options.cwd, agent: "copilot", env,
    command: probe.command, taskId: options.taskId, builtinMcpsDisabled: true });
  if (preflight.status === "FAIL") return blocked("preflight: " + preflight.checks.filter(c => c.status === "FAIL").map(c => c.id + ": " + c.message).join("; "));
  return new Promise((resolve) => {
    const child = spawn(
      probe.command!.file,
      [...probe.command!.prefix, ...args],
      {
        cwd: options.cwd,
        env,
        shell: false,
        detached: process.platform !== "win32",
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "",
      stderr = "",
      stopped = "",
      processError = false;
    let force: ReturnType<typeof setTimeout> | undefined;
    const kill = (signal: NodeJS.Signals) => {
      try {
        if (process.platform !== "win32" && child.pid)
          process.kill(-child.pid, signal);
        else child.kill(signal);
      } catch {}
    };
    const stop = (reason: string) => {
      if (stopped) return;
      stopped = reason;
      kill("SIGTERM");
      force = setTimeout(() => kill("SIGKILL"), 500);
    };
    const abort = () => stop("cancelled");
    options.signal?.addEventListener("abort", abort, { once: true });
    if (options.signal?.aborted) abort();
    const timer = setTimeout(() => stop("timeout"), timeoutMs);
    child.stdout.on("data", (chunk) => {
      if (stopped) return;
      stdout += chunk;
      if (Buffer.byteLength(stdout) > 16 * 1024 * 1024) stop("output-limit");
    });
    child.stderr.on("data", (chunk) => {
      if (stderr.length < 65536)
        stderr += chunk.toString().slice(0, 65536 - stderr.length);
    });
    child.on("error", () => {
      processError = true;
    });
    child.on("close", (exitCode, signal) => {
      if (stopped) kill("SIGKILL");
      clearTimeout(timer);
      if (force) clearTimeout(force);
      options.signal?.removeEventListener("abort", abort);
      const events: Record<string, any>[] = [];
      let malformed = false;
      for (const line of stdout.split(/\r?\n/).filter((l) => l.trim())) {
        try {
          const value = JSON.parse(line);
          if (!value || typeof value.type !== "string") throw Error();
          events.push(value);
        } catch {
          malformed = true;
        }
      }
      const result = events.filter((e) => e.type === "result").at(-1);
      const errors = events.filter(
        (e) =>
          e.type === "session.error" ||
          e.type === "error" ||
          (e.type === "result" && e.error),
      );
      const errorCodes = errors
        .map((e) =>
          String(
            e.data?.errorType ?? e.data?.code ?? e.error?.code ?? e.code ?? "",
          ),
        )
        .join(" ");
      const authentication =
        /auth|unauthorized|login/i.test(errorCodes) ||
        errors.some((e) => e.data?.statusCode === 401);
      const restricted =
        /quota|entitlement|policy|forbidden|rate.limit/i.test(errorCodes) ||
        errors.some((e) => [403, 429].includes(e.data?.statusCode));
      const reason =
        stopped ||
        (processError
          ? "process-unavailable"
          : authentication
            ? "authentication-required: run copilot login"
            : restricted
              ? "account-restricted"
              : malformed
                ? "invalid-jsonl"
                : signal
                  ? "interrupted"
                  : exitCode !== 0
                    ? "process-error: inspect stderr; authenticate with copilot login if requested"
                    : errors.length
                      ? "provider-error"
                      : result?.exitCode !== 0
                        ? "missing-or-failed-result"
                        : "completed");
      resolve({
        status:
          reason === "completed"
            ? "PASS"
            : stopped || authentication || restricted || processError
              ? "BLOCKED"
              : "FAIL",
        reason,
        exitCode,
        signal,
        events,
        stderr,
      });
    });
  });
}
/** Runner context is generated by Python after its authorization gates. */
export async function dispatchCopilot(
  root: string,
  contextFile: string,
  allowTools: string[],
  timeoutMs: number,
  signal?: AbortSignal,
) {
  root = path.resolve(root);
  if (
    path.resolve(contextFile) !==
    path.join(root, ".harness/dispatch/context.json")
  )
    throw Error("Use the Python runner's context path.");
  const context = JSON.parse(
    read(root, ".harness/dispatch/context.json") ?? "null",
  );
  if (
    !context ||
    !["implement", "review"].includes(context.action) ||
    typeof context.task_id !== "string"
  )
    throw Error("Invalid runner context.");
  const readiness = execute(root, ["readiness", context.task_id]);
  if (readiness.exitCode || readiness.data?.result !== "PASS")
    throw Error("Python readiness blocked Copilot dispatch.");
  return runCopilot({
    cwd: root,
    taskId: context.task_id,
    prompt: `Perform only the assigned role. Do not run lifecycle commands or change approval records. Follow this Python engine context:\n${JSON.stringify(context)}`,
    allowTools,
    timeoutMs,
    signal,
  });
}
