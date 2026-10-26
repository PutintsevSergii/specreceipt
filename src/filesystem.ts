import * as fs from "node:fs";
import * as path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import {
  JOURNAL_PATH,
  VERSION,
  MANIFEST_PATH,
  portablePath,
  managedSection,
  type Change,
  type Manifest,
} from "./core.js";
export const hash = (s: string) => createHash("sha256").update(s).digest("hex");
export function safe(root: string, rel: string): string {
  portablePath(rel);
  const absolute = path.resolve(root, rel);
  // Check every existing ancestor, including the supplied target itself.
  let cursor = absolute;
  for (;;) {
    try {
      if (fs.lstatSync(cursor).isSymbolicLink())
        throw new Error(`Symlink refused: ${rel}`);
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw e;
    }
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
    cursor = parent;
  }
  return absolute;
}
export function read(root: string, rel: string): string | null {
  const target = safe(root, rel);
  try {
    if (!fs.statSync(target).isFile())
      throw new Error(`Expected regular file: ${rel}`);
    return fs.readFileSync(target, "utf8");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw e;
  }
}
export function manifest(root: string): Manifest | null {
  const raw = read(root, MANIFEST_PATH);
  if (raw === null) return null;
  let data: Manifest;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(
      "Invalid installation manifest JSON. Restore its backup before initializing.",
    );
  }
  if (
    ![1, 2].includes(data.schemaVersion) ||
    typeof data.packageVersion !== "string" ||
    !data.files ||
    Array.isArray(data.files)
  )
    throw new Error("Unsupported installation manifest.");
  for (const [rel, item] of Object.entries(data.files)) {
    portablePath(rel);
    if (
      item.baseline !== undefined &&
      (typeof item.baseline !== "string" ||
        hash(item.baseline) !== item.baselineHash)
    )
      throw Error("Invalid template baseline.");
    if (
      !item ||
      !/^[a-f0-9]{64}$/.test(item.hash) ||
      !["harness", "project", "shared", "openspec"].includes(item.owner)
    )
      throw new Error("Invalid ownership record.");
  }
  return data;
}
export function atomic(
  root: string,
  rel: string,
  content: string,
  mode = 0o600,
) {
  const dest = safe(root, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const temp = dest + ".tmp-" + randomUUID();
  try {
    const fd = fs.openSync(temp, "wx", mode);
    try {
      fs.writeFileSync(fd, content);
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    safe(root, rel);
    fs.renameSync(temp, dest);
  } finally {
    fs.rmSync(temp, { force: true });
  }
}
/** Publish a fully written new file without replacing an existing destination. */
function atomicCreate(
  root: string,
  rel: string,
  content: string,
  mode: number,
) {
  const dest = safe(root, rel);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const temp = dest + ".tmp-" + randomUUID();
  try {
    const fd = fs.openSync(temp, "wx", mode);
    try {
      fs.writeFileSync(fd, content);
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    safe(root, rel);
    fs.linkSync(temp, dest);
  } finally {
    fs.rmSync(temp, { force: true });
  }
}
interface Record {
  path: string;
  before: string | null;
  after: string;
  mode: number;
  oldMode: number | null;
}
interface Journal {
  schemaVersion: 1;
  files: Record[];
}
export function apply(
  root: string,
  changes: Change[],
  failAfter?: number,
  validate?: () => void,
) {
  if (changes.some((c) => c.action === "conflict"))
    throw new Error("Installation conflicts; no files changed.");
  if (read(root, JOURNAL_PATH) !== null)
    throw new Error(
      "Interrupted installation. Inspect the journal, then run init --recover to roll back before retrying.",
    );
  const edits = changes.filter(
    (c) => c.action === "create" || c.action === "update",
  );
  if (!edits.length) {
    if (fs.existsSync(safe(root, ".harness/installation.lock")))
      throw Error("Installation lock exists; inspect active writers.");
    validate?.();
    return;
  }
  fs.mkdirSync(root, { recursive: true });
  const lock = safe(root, ".harness/installation.lock");
  fs.mkdirSync(path.dirname(lock), { recursive: true });
  let fd: number;
  try {
    fd = fs.openSync(lock, "wx", 0o600);
  } catch {
    throw new Error(
      "Installation lock exists. Confirm no installer is running before removing the stale lock.",
    );
  }
  let journalCreated = false;
  try {
    for (const c of changes)
      if (read(root, c.path) !== c.before)
        throw new Error(`Concurrent change detected: ${c.path}`);
    const journal: Journal = {
      schemaVersion: 1,
      files: edits.map((c) => ({
        path: c.path,
        before: c.before,
        after: c.content,
        mode: c.mode ?? 0o644,
        oldMode:
          c.before === null
            ? null
            : fs.statSync(safe(root, c.path)).mode & 0o777,
      })),
    };
    atomic(root, JOURNAL_PATH, JSON.stringify(journal));
    journalCreated = true;
    for (const [i, c] of journal.files.entries()) {
      if (failAfter === i)
        throw new Error("Injected installation interruption");
      if (read(root, c.path) !== c.before)
        throw new Error(`Concurrent change detected: ${c.path}`);
      if (c.before === null) {
        atomicCreate(root, c.path, c.after, c.mode);
      } else atomic(root, c.path, c.after, c.oldMode ?? c.mode);
    }
    validate?.();
    fs.unlinkSync(safe(root, JOURNAL_PATH));
  } catch (e) {
    throw new Error(
      journalCreated
        ? "Installation interrupted; existing data is backed up in the journal. Run init --recover after inspecting changes."
        : (e as Error).message,
    );
  } finally {
    fs.closeSync(fd);
    fs.unlinkSync(lock);
  }
}
export function recover(root: string) {
  const raw = read(root, JOURNAL_PATH);
  if (raw === null) throw new Error("No pending installation to recover.");
  const journal = JSON.parse(raw) as Journal;
  if (journal.schemaVersion !== 1 || !Array.isArray(journal.files))
    throw new Error("Invalid recovery journal.");
  const seen = new Set<string>();
  for (const row of journal.files) {
    portablePath(row.path);
    if (
      seen.has(row.path) ||
      [JOURNAL_PATH, ".harness/installation.lock"].includes(row.path) ||
      typeof row.after !== "string" ||
      (row.before !== null && typeof row.before !== "string")
    )
      throw new Error("Invalid recovery entry.");
    seen.add(row.path);
    const current = read(root, row.path);
    if (current !== row.before && current !== row.after)
      throw new Error(
        `Recovery conflict: ${row.path}; preserve and reconcile the concurrent edit manually.`,
      );
  }
  const lock = safe(root, ".harness/installation.lock");
  const fd = fs.openSync(lock, "wx", 0o600);
  try {
    for (const row of [...journal.files].reverse()) {
      const current = read(root, row.path);
      if (current === row.before) continue;
      if (current !== row.after)
        throw new Error(`Concurrent recovery change: ${row.path}`);
      if (row.before === null) fs.unlinkSync(safe(root, row.path));
      else atomic(root, row.path, row.before, row.oldMode ?? 0o644);
    }
    fs.unlinkSync(safe(root, JOURNAL_PATH));
  } finally {
    fs.closeSync(fd);
    fs.unlinkSync(lock);
  }
}
export function ownership(
  changes: Change[],
  previous: Manifest | null,
  version: string,
): Manifest {
  const files = { ...previous?.files };
  for (const c of changes) {
    if (
      c.owner === "project" ||
      (c.owner === "openspec" && previous?.files[c.path])
    )
      continue;
    const content =
      c.owner === "shared" ? managedSection(c.content) : c.content;
    if (content !== null)
      files[c.path] = {
        hash: hash(content),
        owner: c.owner,
        baseline: previous?.files[c.path]?.baseline ?? content,
        baselineHash: previous?.files[c.path]?.baselineHash ?? hash(content),
      };
  }
  return {
    schemaVersion: 2,
    packageVersion: version,
    engineVersion: VERSION,
    protocolVersion: 1,
    configVersion: 2,
    migrations: previous?.migrations ?? [],
    skills: Object.fromEntries(
      Object.entries(files)
        .filter(([p]) => p.startsWith(".agents/skills/"))
        .map(([p, v]) => [p, v.baselineHash ?? v.hash]),
    ),
    files,
  };
}
export function walk(root: string, relative = ""): string[] {
  if (!fs.existsSync(root)) return [];
  let results: string[] = [];
  for (const name of fs.readdirSync(path.join(root, relative)).sort()) {
    const rel = relative ? relative + "/" + name : name;
    const p = safe(root, rel);
    const s = fs.lstatSync(p);
    if (s.isDirectory()) results.push(...walk(root, rel));
    else if (s.isFile()) results.push(rel);
    else throw new Error("Unsupported filesystem entry.");
  }
  return results;
}
