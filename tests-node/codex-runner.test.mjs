import { test } from "node:test";
import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { spawnSync } from "node:child_process";
import { pythonCommand } from "../dist/integrations.js";

const cli = path.resolve("dist/cli.js");

test("Codex runner preview binds exact commands and Unicode approval to Python hash", (t) => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "harness-codex-preview-")));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const reference = "Developer approves Codex for DEMO-001 with bounded local scope. Принято.\n";
  fs.writeFileSync(path.join(root, "runner-approval.md"), reference);
  const output = spawnSync(process.execPath, [cli, "codex-runner-preview", "--target", root,
    "--task", "DEMO-001", "--reference", "runner-approval.md"], { encoding: "utf8" });
  assert.equal(output.status, 0, output.stderr);
  const config = JSON.parse(output.stdout);
  assert.equal(config.enabled, true);
  assert.deepEqual(config.task_ids, ["DEMO-001"]);
  assert.deepEqual(config.implement_argv, config.review_argv);
  assert.ok(config.implement_argv.includes("codex-exec"));
  assert.ok(config.implement_argv.includes("{context}"));
  const py = pythonCommand(process.env);
  assert.ok(py, "Python must be available for the engine contract test");
  const check = spawnSync(py.file, [...py.prefix, "-c", "import hashlib,json,sys; d=json.load(sys.stdin); c=d['config']; c.pop('approval_hash'); print(hashlib.sha256(json.dumps({'configuration':c,'reference':d['reference']},sort_keys=True,separators=(',',':')).encode()).hexdigest())"],
    { input: JSON.stringify({ config, reference }), encoding: "utf8" });
  assert.equal(check.status, 0, check.stderr);
  assert.equal(config.approval_hash, check.stdout.trim());
  const duplicate = spawnSync(process.execPath, [cli, "codex-runner-preview", "--target", root,
    "--task", "DEMO-001", "--task", "DEMO-001", "--reference", "runner-approval.md"], { encoding: "utf8" });
  assert.notEqual(duplicate.status, 0);
});

test("Codex adapter refuses a direct launch without active Python intent", (t) => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "harness-codex-direct-")));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, ".harness/dispatch"), { recursive: true });
  fs.writeFileSync(path.join(root, ".harness/dispatch/context.json"), JSON.stringify({
    action: "implement", task_id: "DEMO-001", instructions: "Implement approved task", scope: ["app.py"],
  }));
  fs.writeFileSync(path.join(root, ".harness/state.json"), JSON.stringify({ active_operation: null }));
  const args = [cli, "codex-exec", "--target", root, "--context", path.join(root, ".harness/dispatch/context.json")];
  const direct = spawnSync(process.execPath, args, { encoding: "utf8" });
  assert.notEqual(direct.status, 0);
  assert.match(direct.stderr, /matching active Python runner operation/);
  fs.writeFileSync(path.join(root, ".harness/state.json"), JSON.stringify({
    active_operation: { id: "intent-1", kind: "adapter", task: "DEMO-001", phase: "implement" },
  }));
  const forged = spawnSync(process.execPath, args, { encoding: "utf8" });
  assert.notEqual(forged.status, 0);
  assert.match(forged.stderr, /matching active Python runner operation/);
});
