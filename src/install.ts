import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { request, execute } from "./engine.js";
import { migrate } from "./migrations.js";
import {
  CONFIG_PATH,
  MANIFEST_PATH,
  VERSION,
  JOURNAL_PATH,
  config,
  hasCodex,
  hasCopilot,
  QUALITY,
  selection,
  mergeAgents,
  plan,
  type Selection,
  type Asset,
  type Change,
} from "./core.js";
import { apply, hash, manifest, ownership, read, safe } from "./filesystem.js";
import {
  codexBlock,
  copilotBlock,
  kitAssets,
  stageOpenSpec,
  KIT,
} from "./integrations.js";
export function prepare(
  root: string,
  choices: Partial<Selection> = {},
  dryRun = false,
): Change[] {
  root = path.resolve(root);
  safe(root, CONFIG_PATH);
  if (read(root, JOURNAL_PATH) !== null)
    throw new Error(
      "Pending installation; inspect it and run init --recover before retrying.",
    );
  if (fs.existsSync(safe(root, ".harness/installation.lock")))
    throw new Error(
      "Installation lock exists; confirm no installer is running before removing a stale lock.",
    );
  const current = read(root, CONFIG_PATH);
  const selected = selection({
    ...(current !== null ? config(JSON.parse(current)) : {}),
    ...choices,
  });
  const previous = manifest(root);
  if (previous && previous.packageVersion !== VERSION)
    throw Error(
      "Use upgrade for version changes; init does not migrate an existing installation.",
    );
  for (const rel of [
    ".harness/checks.json",
    ".harness/graph-config.json",
    ".harness/onboarding.json",
    ".harness/state.json",
  ]) {
    const raw = read(root, rel);
    if (raw === null) continue;
    try {
      const value = JSON.parse(raw);
      if (
        !value ||
        typeof value !== "object" ||
        Array.isArray(value) ||
        ("schema_version" in value && value.schema_version !== 1)
      )
        throw Error();
    } catch {
      throw new Error(
        `Existing ${rel} has invalid JSON or an unsupported schema; reconcile it before initialization.`,
      );
    }
  }
  // An override suppresses AGENTS.md discovery. Never claim this adapter is active in that case.
  if (hasCodex(selected.agent) && read(root, "AGENTS.override.md") !== null)
    throw new Error(
      "AGENTS.override.md takes precedence. Merge its rules into AGENTS.md and move the override explicitly before using this Codex integration.",
    );
  const assets: Asset[] = kitAssets();
  assets.push({
    path: ".harness/onboarding.json",
    content: fs.readFileSync(
      path.join(KIT, "templates/onboarding.json"),
      "utf8",
    ),
    owner: "project",
  });
  assets.push({
    path: ".harness/quality.json",
    content: JSON.stringify(QUALITY, null, 2) + "\n",
    owner: "harness",
  });
  assets.push({
    path: CONFIG_PATH,
    content:
      JSON.stringify(
        migrate({ schemaVersion: 1, ...selected }).value,
        null,
        2,
      ) + "\n",
    owner: "harness",
  });
  assets.push({
    path: "AGENTS.md",
    content: mergeAgents(read(root, "AGENTS.md") ?? "", codexBlock),
    owner: "shared",
  });
  if (hasCopilot(selected.agent))
    assets.push({
      path: ".github/copilot-instructions.md",
      content: mergeAgents(
        read(root, ".github/copilot-instructions.md") ?? "",
        copilotBlock,
      ),
      owner: "shared",
    });
  // Dry runs never invoke a generator or alter a target. The CLI separately lists this external step.
  if (!dryRun) assets.push(...stageOpenSpec(root, selected.agent));
  const observed = Object.fromEntries(
    assets.map((a) => [a.path, read(root, a.path)]),
  );
  const changes = plan(assets, observed, previous, hash);
  if (!changes.some((c) => c.action === "conflict")) {
    const content =
      JSON.stringify(ownership(changes, previous, VERSION), null, 2) + "\n";
    const before = read(root, MANIFEST_PATH);
    changes.push({
      path: MANIFEST_PATH,
      content,
      before,
      owner: "harness",
      action:
        before === content ? "keep" : before === null ? "create" : "update",
      reason: "Versioned installation ownership",
    });
  }
  return changes;
}
export function install(root: string, changes: Change[]) {
  root = path.resolve(root);
  if (changes.some((c) => c.action === "conflict"))
    throw Error("Installation conflicts; no files changed.");
  // Run the installed Python engine against staged templates. Python alone creates state/journal.
  if (read(root, ".harness/state.json") === null) {
    const stage = fs.realpathSync(
      fs.mkdtempSync(path.join(os.tmpdir(), "harness-state-")),
    );
    try {
      for (const c of changes) {
        const dest = path.join(stage, c.path);
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.writeFileSync(dest, c.content);
      }
      const result = request(stage, ["init"]);
      if (result.exitCode) throw Error("Python state initialization failed.");
      for (const rel of [".harness/state.json", ".harness/events.jsonl"]) {
        if (read(root, rel) !== null)
          throw Error(
            `Existing ${rel} without state requires manual recovery.`,
          );
        changes.push({
          path: rel,
          before: null,
          content: read(stage, rel)!,
          owner: "project",
          action: "create",
          reason: "Python engine initialization",
        });
      }
    } finally {
      fs.rmSync(stage, { recursive: true, force: true });
    }
  }
  apply(root, changes, undefined, () => {
    if (execute(root, ["validate"]).exitCode)
      throw Error("Installed engine validation failed.");
  });
}
