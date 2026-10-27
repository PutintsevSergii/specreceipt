/** Pure distribution contracts. No filesystem, process or terminal dependencies. */
export const VERSION = "0.4.2";
export const OPENSPEC_VERSION = "1.14.3";
export const DEFAULTS = {
  agent: "codex",
  workflow: "openspec",
  quality: "strict",
  skills: "engineering-pack",
} as const;
export type Selection = {
  agent: string;
  workflow: string;
  quality: string;
  skills: string;
};
export const CONFIG_PATH = ".harness/product.json";
export const MANIFEST_PATH = ".harness/installation-manifest.json";
export const JOURNAL_PATH = ".harness/installation-pending.json";
export const BEGIN = "<!-- my-ai-harness:begin -->";
export const END = "<!-- my-ai-harness:end -->";
export type Owner = "harness" | "project" | "openspec" | "shared";
export interface Asset {
  path: string;
  content: string;
  owner: Owner;
  mode?: number;
}
export interface Change extends Asset {
  before: string | null;
  action: "create" | "update" | "keep" | "conflict";
  reason: string;
}
export interface Manifest {
  schemaVersion: 1 | 2;
  engineVersion?: string;
  protocolVersion?: number;
  configVersion?: number;
  migrations?: string[];
  skills?: Record<string, string>;
  packageVersion: string;
  files: Record<
    string,
    { hash: string; owner: Owner; baseline?: string; baselineHash?: string }
  >;
}
export interface Diagnostic {
  id: string;
  status: "PASS" | "WARN" | "FAIL" | "SKIP";
  message: string;
  fix?: string;
}
export const AGENTS = [
  "codex",
  "copilot",
  "copilot-ide",
  "codex,copilot",
  "codex,copilot-ide",
] as const;
export const hasCodex = (agent: string) => agent.split(",").includes("codex");
export const hasCopilot = (agent: string) => agent.includes("copilot");
export const needsCopilotCLI = (agent: string) =>
  agent.split(",").includes("copilot");
export function selection(input: Partial<Selection> = {}): Selection {
  const result = { ...DEFAULTS, ...input };
  for (const [key, value] of Object.entries(result)) {
    if (
      !(key in DEFAULTS) ||
      (key === "agent"
        ? !AGENTS.includes(value as (typeof AGENTS)[number])
        : value !== DEFAULTS[key as keyof Selection])
    )
      throw new Error(
        `Unsupported ${key}. Supported agents: codex, copilot, copilot-ide, codex,copilot, codex,copilot-ide. Workflow: OpenSpec + Strict + Engineering Pack.`,
      );
  }
  return result;
}
export function config(input: unknown): Selection {
  if (!input || typeof input !== "object" || Array.isArray(input))
    throw new Error("Invalid harness configuration object.");
  const value = input as Record<string, unknown>;
  if (
    ![1, 2].includes(value.schemaVersion as number) ||
    Object.keys(value).some(
      (k) =>
        ![
          "schemaVersion",
          ...(value.schemaVersion === 2 ? ["engine"] : []),
          ...Object.keys(DEFAULTS),
        ].includes(k),
    )
  )
    throw new Error("Unsupported configuration schema or fields.");
  if (Object.keys(DEFAULTS).some((k) => typeof value[k] !== "string"))
    throw new Error("Configuration selections are required.");
  if (
    value.schemaVersion === 2 &&
    JSON.stringify(value.engine) !== JSON.stringify({ protocolVersion: 1 })
  )
    throw new Error("Unsupported engine configuration.");
  return selection(
    Object.fromEntries(Object.keys(DEFAULTS).map((k) => [k, value[k]])),
  );
}
export function portablePath(path: string): string {
  if (
    !path ||
    path.startsWith("/") ||
    path.includes("\\") ||
    path.includes(":") ||
    path.split("/").some((p) => !p || p === "." || p === "..") ||
    /[\x00-\x1f]/.test(path)
  )
    throw new Error("Unsafe managed relative path.");
  return path;
}
export function managedSection(content: string): string | null {
  const starts = content.split(BEGIN).length - 1,
    ends = content.split(END).length - 1;
  if (!starts && !ends) return null;
  if (
    starts !== 1 ||
    ends !== 1 ||
    content.indexOf(END) < content.indexOf(BEGIN)
  )
    throw new Error(
      "Malformed harness markers in AGENTS.md; repair markers manually.",
    );
  return content.slice(
    content.indexOf(BEGIN),
    content.indexOf(END) + END.length,
  );
}
export function mergeAgents(existing: string, block: string): string {
  const old = managedSection(existing);
  return old
    ? existing.replace(old, block)
    : existing +
        (existing.endsWith("\n") || !existing ? "" : "\n") +
        "\n" +
        block +
        "\n";
}
export function plan(
  assets: Asset[],
  observed: Record<string, string | null>,
  previous: Manifest | null,
  hash: (s: string) => string,
): Change[] {
  const seen = new Set<string>();
  return assets.map((asset) => {
    portablePath(asset.path);
    if (seen.has(asset.path)) throw new Error("Duplicate planned path.");
    seen.add(asset.path);
    const before = observed[asset.path] ?? null;
    if (before === null)
      return { ...asset, before, action: "create", reason: "Missing file" };
    if (asset.owner === "project")
      return {
        ...asset,
        before,
        content: before,
        action: "keep",
        reason: "Project-owned configuration preserved",
      };
    if (before === asset.content)
      return { ...asset, before, action: "keep", reason: "Already matches" };
    const prior = previous?.files[asset.path];
    const old = asset.owner === "shared" ? managedSection(before) : before;
    if (asset.owner === "shared" && old === null && !prior)
      return {
        ...asset,
        before,
        action: "update",
        reason: "Append managed section; preserve project text",
      };
    if (
      asset.owner !== "openspec" &&
      prior &&
      old !== null &&
      hash(old) === prior.hash
    )
      return {
        ...asset,
        before,
        action: "update",
        reason: "Unmodified managed content upgrade",
      };
    return {
      ...asset,
      before,
      action: "conflict",
      reason:
        "Existing content differs; manually merge or move it, then rerun. No overwrite performed.",
    };
  });
}
export function health(checks: Diagnostic[]) {
  return checks.some((c) => c.status === "FAIL")
    ? "UNHEALTHY"
    : checks.some((c) => c.status === "WARN")
      ? "ATTENTION"
      : "HEALTHY";
}

export function nodeSupported(version: string): boolean {
  const match = /^(\d+)\.(\d+)\.(\d+)$/.exec(version);
  if (!match) return false;
  const major = Number(match[1]),
    minor = Number(match[2]);
  return major >= 20 && major < 25 && (major !== 20 || minor >= 19);
}

export const QUALITY = {
  schemaVersion: 1,
  profile: "strict",
  instructions: [
    "Investigate source and requirements",
    "Map acceptance criteria to checks",
    "Report assumptions and execution evidence",
  ],
  deterministic: [
    "harness validate",
    "harness readiness TASK-ID",
    "harness verify TASK-ID",
  ],
  human: [
    "Approve requirements and material changes",
    "Review semantic coverage and actual diff",
  ],
  applicationChecks:
    "Configured and approved during project onboarding; never inferred from installation health",
};
