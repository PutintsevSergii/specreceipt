import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { spawnSync } from "node:child_process";
import { kitAssets, codexBlock, copilotBlock } from "./integrations.js";
import {
  VERSION,
  hasCopilot,
  CONFIG_PATH,
  MANIFEST_PATH,
  JOURNAL_PATH,
  QUALITY,
  managedSection,
  mergeAgents,
  type Change,
  type Asset,
} from "./core.js";
import { read, manifest, hash, apply, ownership, safe } from "./filesystem.js";
import { execute, request } from "./engine.js";
import { migrate } from "./migrations.js";

export function mergeText(
  base: string,
  local: string,
  remote: string,
): string | null {
  if (local === base) return remote;
  if (remote === base || local === remote) return local;
  const temp = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-merge-")),
  );
  try {
    for (const [name, data] of [
      ["base", base],
      ["local", local],
      ["remote", remote],
    ])
      fs.writeFileSync(path.join(temp, name!), data!);
    const r = spawnSync(
      "git",
      ["merge-file", "-p", "--", "local", "base", "remote"],
      {
        cwd: temp,
        encoding: "utf8",
        timeout: 30000,
        maxBuffer: 16 * 1024 * 1024,
      },
    );
    if (r.error || r.status === null || r.status < 0 || r.status > 127)
      throw Error(
        "Git merge-file unavailable or failed; install Git or merge manually.",
      );
    return r.status === 0 ? r.stdout : null;
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
}
function legacyBase(
  baseline: string | undefined,
  rel: string,
  expected: string,
  version: string,
): string | null {
  if (!baseline) return null;
  const info = JSON.parse(read(baseline, "package.json") ?? "null");
  if (info?.name !== "my-ai-harness" || info?.version !== version)
    throw Error("Legacy baseline package identity mismatch.");
  let value = read(baseline, "assets/kit/" + rel);
  if (rel === "AGENTS.md") {
    // Recover only the literal managed block from the archived adapter, never execute old JS.
    const source = read(baseline, "dist/integrations.js") ?? "";
    const literal = /export const codexBlock = `([^`]+)`;/.exec(source)?.[1];
    value =
      literal
        ?.replace("${BEGIN}", "<!-- my-ai-harness:begin -->")
        .replace("${END}", "<!-- my-ai-harness:end -->") ?? null;
  }
  return value !== null && hash(value) === expected ? value : null;
}
export function prepareUpgrade(root: string, baseline?: string): Change[] {
  root = path.resolve(root);
  if (
    read(root, JOURNAL_PATH) !== null ||
    fs.existsSync(safe(root, ".harness/installation.lock"))
  )
    throw Error(
      "Pending installation or lock; inspect and recover before upgrade.",
    );
  const previous = manifest(root);
  const supported = ["0.1.0", "0.2.0", "0.3.0", "0.3.1", VERSION];
  if (!previous || !supported.includes(previous.packageVersion))
    throw Error(
      "Unsupported or absent installation version. Supported source: " + supported.join(", ") + ".",
    );
  const migration = migrate(JSON.parse(read(root, CONFIG_PATH) ?? "null"));
  const assets: Asset[] = [
    ...kitAssets(),
    {
      path: ".harness/quality.json",
      content: JSON.stringify(QUALITY, null, 2) + "\n",
      owner: "harness",
    },
    {
      path: CONFIG_PATH,
      content: JSON.stringify(migration.value, null, 2) + "\n",
      owner: "harness",
    },
    { path: "AGENTS.md", content: codexBlock, owner: "shared" },
  ];
  if (hasCopilot(migration.value.agent as string))
    assets.push({
      path: ".github/copilot-instructions.md",
      content: copilotBlock,
      owner: "shared",
    });
  const baselines = new Map<string, string>();
  const changes: Change[] = assets.map((a) => {
    const before = read(root, a.path),
      prior = previous.files[a.path];
    const local =
      a.owner === "shared" && before !== null ? managedSection(before) : before;
    const remote = a.content;
    baselines.set(a.path, remote);
    const change = (
      content: string,
      action: Change["action"],
      reason: string,
    ): Change => ({ ...a, content, before, action, reason });
    if (a.owner === "project")
      return change(
        before ?? remote,
        before === null ? "create" : "keep",
        "Project-owned; preserve",
      );
    if (!prior)
      return before === null
        ? change(remote, "create", "New managed file")
        : change(before, "conflict", "Unowned path collision");
    if (before === null || local === null)
      return change(
        remote,
        "conflict",
        "Managed content locally deleted; resolve intentionally",
      );
    if (a.path === CONFIG_PATH)
      return change(
        remote,
        before === remote ? "keep" : "update",
        "Validated configuration schema migration",
      );
    let base =
      prior.baseline ??
      (hash(local) === prior.hash
        ? local
        : legacyBase(baseline, a.path, prior.hash, previous.packageVersion));
    if (base === null)
      return change(
        before,
        "conflict",
        "Missing trustworthy legacy baseline; provide --baseline extracted-package-directory",
      );
    if (
      (a.path.startsWith("harnesslib/") ||
        a.path.startsWith("schemas/") ||
        a.path === "harness") &&
      local !== base &&
      local !== remote
    )
      return change(
        before,
        "conflict",
        "Custom engine/schema cannot claim upstream version; preserve and migrate fork explicitly",
      );
    const merged = mergeText(base, local, remote);
    if (merged === null)
      return change(
        before,
        "conflict",
        "Overlapping changes; manually reconcile LOCAL with BASE and REMOTE, then retry",
      );
    const content = a.owner === "shared" ? mergeAgents(before, merged) : merged;
    return change(
      content,
      content === before ? "keep" : "update",
      "Three-way merge preserves local changes",
    );
  });
  const desired = new Set(assets.map((a) => a.path));
  for (const [rel, prior] of Object.entries(previous.files)) {
    if (
      desired.has(rel) ||
      prior.owner === "openspec" ||
      prior.owner === "project"
    )
      continue;
    const before = read(root, rel);
    changes.push({
      path: rel,
      content: before ?? "",
      before,
      owner: prior.owner,
      action: "conflict",
      reason:
        "Removed or renamed managed path; manual ownership migration required, content preserved",
    });
  }
  if (!changes.some((c) => c.action === "conflict")) {
    const owned = ownership(changes, previous, VERSION);
    owned.migrations = [
      ...new Set([...(previous.migrations ?? []), ...migration.applied]),
    ];
    for (const [rel, base] of baselines)
      if (owned.files[rel]) {
        owned.files[rel]!.baseline = base;
        owned.files[rel]!.baselineHash = hash(base);
      }
    owned.skills = Object.fromEntries(
      Object.entries(owned.files)
        .filter(([p]) => p.startsWith(".agents/skills/"))
        .map(([p, v]) => [p, v.baselineHash ?? v.hash]),
    );
    const content = JSON.stringify(owned, null, 2) + "\n",
      before = read(root, MANIFEST_PATH);
    changes.push({
      path: MANIFEST_PATH,
      before,
      content,
      owner: "harness",
      action: before === content ? "keep" : "update",
      reason: "Commit versioned ownership and migration history",
    });
  }
  return changes;
}
export function upgrade(root: string, changes: Change[], failAfter?: number) {
  root = path.resolve(root);
  if (changes.some((c) => c.action === "conflict"))
    throw Error("Upgrade conflicts; no files changed.");
  // Stage and validate planned engine/config against a complete copy of runtime documents.
  const stage = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-upgrade-")),
  );
  try {
    for (const c of changes) {
      const dest = path.join(stage, c.path);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.writeFileSync(dest, c.content);
    }
    if (request(stage, ["contract"]).exitCode)
      throw Error("Staged engine incompatible.");
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
  }
  apply(root, changes, failAfter, () => {
    if (execute(root, ["validate"]).exitCode)
      throw Error("Post-upgrade validation failed; recover the transaction.");
  });
}
