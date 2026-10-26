import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";
import { portablePath } from "../dist/core.js";
import { apply, recover, read } from "../dist/filesystem.js";
test("portable argument and file operations in spaces and Unicode directories", (t) => {
  const base = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness paths ")),
  );
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  const target = path.join(base, "project ü space");
  const result = spawnSync(
    process.execPath,
    [path.resolve("dist/cli.js"), "init", "--target", target, "--dry-run"],
    { encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(target), false);
  fs.mkdirSync(target);
  const changes = [
    {
      path: "nested/file.txt",
      content: "new",
      before: null,
      owner: "harness",
      action: "create",
      reason: "",
    },
    {
      path: "second.txt",
      content: "second",
      before: null,
      owner: "harness",
      action: "create",
      reason: "",
    },
  ];
  assert.throws(() => apply(target, changes, 1));
  recover(target);
  assert.equal(read(target, "nested/file.txt"), null);
  apply(target, changes);
  assert.equal(read(target, "second.txt"), "second");
  assert.throws(() => portablePath("C:/outside"));
  assert.throws(() => portablePath("..\\outside"));
  assert.throws(() => portablePath("//server/share"));
});
