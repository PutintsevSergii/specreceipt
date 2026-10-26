import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { planningCommands } from "../scripts/copilot-e2e-fixture.mjs";
test("E2E planning executables delegate and reject approval, installs and outside targets", (t) => {
  const root = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-copilot-command-")),
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(
    path.join(root, "package.json"),
    JSON.stringify({ type: "module" }),
  );
  const cli = path.join(root, "cli.cjs");
  fs.writeFileSync(cli, "console.log(JSON.stringify(process.argv.slice(2)))");
  const official = path.join(root, "openspec");
  fs.writeFileSync(
    official,
    `#!${process.execPath}\nconsole.log(JSON.stringify(process.argv.slice(2)))`,
    { mode: 0o755 },
  );
  const fixture = planningCommands(root, cli, official);
  for (const [command, args] of [
    ["harness-e2e-plan", ["resume"]],
    [
      "harness-e2e-plan",
      [
        "openspec",
        "import",
        "parse-port",
        "--mapping",
        ".harness/openspec-mapping.json",
      ],
    ],
    ["openspec-e2e-plan", ["new", "change", "parse-port"]],
    [
      "openspec-e2e-plan",
      ["instructions", "proposal", "--change", "parse-port", "--json"],
    ],
  ]) {
    const r = spawnSync(path.join(fixture.bin, command), args, {
      encoding: "utf8",
    });
    assert.equal(r.status, 0, r.stderr);
    assert.deepEqual(JSON.parse(r.stdout), args);
  }
  for (const [command, args] of [
    ["harness-e2e-plan", ["task", "approve", "TASK-001", "developer"]],
    ["harness-e2e-plan", ["status", "--target", "/outside"]],
    ["harness-e2e-plan", ["tools", "update", "--apply"]],
    ["openspec-e2e-plan", ["init"]],
    ["openspec-e2e-plan", ["new", "change", "other"]],
    ["openspec-e2e-plan", ["instructions", "proposal", "--store", "outside"]],
  ])
    assert.equal(spawnSync(path.join(fixture.bin, command), args).status, 64);
});
