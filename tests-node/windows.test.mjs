import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";
import { portablePath } from "../dist/core.js";
import { apply, recover, read } from "../dist/filesystem.js";
import { invoke, nativeCommand, pythonCommand, executable } from "../dist/integrations.js";

test("packaged launchers use portable line endings and include native entry points", () => {
  for (const file of ["harness", "install.sh", "scripts/python.sh", "harness.cmd", "install.ps1", "scripts/python.ps1", "scripts/uv.ps1"]) {
    const content = fs.readFileSync(path.join("assets/kit", file), "utf8");
    assert.equal(content.includes("\r"), false, file);
  }
  assert.equal(fs.readFileSync("assets/kit/harness", "utf8").split("\n")[0], "#!/bin/sh");
});

test("Windows copied environments preserve mixed-case Path discovery", {skip: process.platform !== "win32"}, () => {
  assert.equal(fs.realpathSync(executable("node", {Path:path.dirname(process.execPath)})).toLowerCase(), fs.realpathSync(process.execPath).toLowerCase());
  assert.deepEqual(pythonCommand({harness_python:"explicit-python.exe"}), {file:"explicit-python.exe",prefix:[]});
});

test("Windows npm shims preserve argument boundaries without cmd interpolation", {skip: process.platform !== "win32"}, t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "native command "));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const pkg = path.join(root, "node_modules/npm");
  fs.mkdirSync(pkg, {recursive:true});
  fs.writeFileSync(path.join(pkg, "package.json"), JSON.stringify({bin:{npm:"cli.cjs"}}));
  fs.writeFileSync(path.join(pkg, "cli.cjs"), "console.log(JSON.stringify(process.argv.slice(2)))");
  const shim = path.join(root, "npm.cmd"); fs.writeFileSync(shim, "@exit /b 99");
  const args = ["space ü", "& echo injected", "%PATH%", 'quote"value'];
  const result = invoke({file:shim,prefix:[]}, args, root);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), args);
  assert.throws(() => nativeCommand({file:path.join(root,"unknown.cmd"),prefix:[]}), /explicit interpreter/);
});

test("Windows managed Python is discovered from its runtime pointer", {skip: process.platform !== "win32"}, t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "native python "));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const python = pythonCommand(); assert.ok(python);
  fs.writeFileSync(path.join(root,"python-path.txt"), python.file);
  const env = {...process.env, HARNESS_RUNTIME_DIR:root, PATH:""}; delete env.HARNESS_PYTHON;
  assert.deepEqual(pythonCommand(env), {file:python.file,prefix:[]});
});
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
