import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { prepare, install } from "../dist/install.js";
import { prepareUpgrade } from "../dist/upgrade.js";
import { selection, config } from "../dist/core.js";
import {
  probeCopilot,
  runCopilot,
  copilotArguments,
  dispatchCopilot,
} from "../dist/copilot.js";
import { doctor } from "../dist/doctor.js";
const help =
  "--prompt --output-format --allow-tool --deny-tool --no-auto-update --disallow-temp-dir --disable-builtin-mcps --no-bash-env";
function temp(t) {
  const p = fs.realpathSync(
    fs.mkdtempSync(path.join(os.tmpdir(), "harness-copilot-test-")),
  );
  t.after(() => fs.rmSync(p, { recursive: true, force: true }));
  return p;
}
function fake(t, body) {
  const root = temp(t),
    script = path.join(root, "fake.cjs");
  fs.writeFileSync(
    script,
    `if(process.argv.includes('--version'))console.log('GitHub Copilot CLI 1.0.test');else if(process.argv.includes('--help'))console.log(${JSON.stringify(help)});else {${body}}`,
  );
  return {
    cwd: root,
    prompt: "test",
    command: { file: process.execPath, prefix: [script] },
  };
}
test("all supported agents preserve configuration contract", () => {
  for (const agent of [
    "codex",
    "copilot",
    "copilot-ide",
    "codex,copilot",
    "codex,copilot-ide",
  ])
    assert.equal(
      config({
        schemaVersion: 2,
        engine: { protocolVersion: 1 },
        ...selection({ agent }),
      }).agent,
      agent,
    );
  assert.throws(() => selection({ agent: "cloud" }));
});
test("adapter accepts structured result and propagates nonzero or provider failure", async (t) => {
  const o = fake(t, `console.log(JSON.stringify({type:'result',exitCode:0}));`);
  assert.equal((await runCopilot(o)).status, "PASS");
  for (const body of [
    "console.log('human output');",
    "process.exit(4)",
    "console.log(JSON.stringify({type:'result',exitCode:3}));",
    "console.log(JSON.stringify({type:'assistant.message',data:{content:'done'}}));",
  ]) {
    const result = await runCopilot(fake(t, body));
    assert.equal(result.status, "FAIL");
  }
});
test("missing authentication and account restrictions use structured errors", async (t) => {
  for (const code of [
    "authentication_required",
    "quota_exceeded",
    "entitlement_missing",
    "organization_policy",
  ]) {
    const r = await runCopilot(
      fake(
        t,
        `console.log(JSON.stringify({type:'session.error',data:{errorType:'${code}'}}));process.exitCode=1;`,
      ),
    );
    assert.equal(r.status, "BLOCKED");
  }
});
test("timeout, cancellation, missing process and unsupported capability fail closed", async (t) => {
  const slow = fake(t, "setTimeout(()=>{},10000);");
  assert.equal(
    (await runCopilot({ ...slow, timeoutMs: 30 })).reason,
    "timeout",
  );
  const ctrl = new AbortController();
  setTimeout(() => ctrl.abort(), 100);
  assert.equal(
    (await runCopilot({ ...slow, signal: ctrl.signal })).reason,
    "cancelled",
  );
  assert.equal(
    (
      await runCopilot({
        ...slow,
        command: { file: "/missing/copilot", prefix: [] },
      })
    ).reason,
    "copilot-incompatible",
  );
  const cmd = fake(t, "console.log('{}')");
  fs.writeFileSync(
    cmd.command.prefix[0],
    "console.log('unrelated executable')",
  );
  assert.equal(probeCopilot(cmd.cwd, cmd.command).state, "incompatible");
});
test("no unrestricted permissions or inherited allow-all environment", async (t) => {
  for (const p of [
    "shell",
    "write",
    "shell(*)",
    "shell(node:*)",
    "--yolo",
    "url(github.com)",
  ])
    assert.throws(() => copilotArguments("test", [p]));
  const args = copilotArguments("test", [
    "shell(node --test parser.test.mjs)",
    "write(/tmp/project/parser.mjs)",
  ]);
  assert.ok(!args.includes("--allow-all"));
  assert.ok(!args.includes("--allow-all-tools"));
  assert.ok(!args.includes("--trust-folder"));
  const o = fake(
    t,
    `if(process.env.COPILOT_ALLOW_ALL || process.env.COPILOT_ASSISTED_APPROVAL || process.env.BASH_ENV)process.exit(8);console.log(JSON.stringify({type:'result',exitCode:0}));`,
  );
  assert.equal(
    (
      await runCopilot({
        ...o,
        env: {
          ...process.env,
          COPILOT_ALLOW_ALL: "true",
          COPILOT_ASSISTED_APPROVAL: "true",
          BASH_ENV: "unsafe",
        },
      })
    ).status,
    "PASS",
  );
});
test("Python dispatch refuses untrusted context and missing readiness", async (t) => {
  const root = temp(t);
  await assert.rejects(
    dispatchCopilot(root, "/tmp/other.json", [], 100),
    /context path/,
  );
  fs.mkdirSync(path.join(root, ".harness/dispatch"), { recursive: true });
  fs.writeFileSync(
    path.join(root, ".harness/dispatch/context.json"),
    JSON.stringify({ action: "implement", task_id: "FAKE-001" }),
  );
  await assert.rejects(
    dispatchCopilot(
      root,
      path.join(root, ".harness/dispatch/context.json"),
      [],
      100,
    ),
    /engine|legacy/i,
  );
});
test("missing optional CLI is detected without execution", (t) => {
  const root = temp(t),
    old = process.env.PATH;
  process.env.PATH = "";
  try {
    assert.equal(probeCopilot(root).state, "missing");
  } finally {
    process.env.PATH = old;
  }
});
const real = process.env.HARNESS_REAL_OPENSPEC;
test(
  "official OpenSpec: Copilot and coexistence preserve instructions, repeat and upgrade",
  { skip: !real },
  (t) => {
    const old = process.env.PATH;
    process.env.PATH = path.dirname(real) + path.delimiter + old;
    t.after(() => (process.env.PATH = old));
    for (const agent of [
      "copilot",
      "copilot-ide",
      "codex,copilot",
      "codex,copilot-ide",
    ]) {
      const root = temp(t);
      fs.mkdirSync(path.join(root, ".github"));
      fs.writeFileSync(path.join(root, "AGENTS.md"), "Corporate rules\n");
      fs.writeFileSync(
        path.join(root, ".github/copilot-instructions.md"),
        "Custom Copilot rules\n",
      );
      install(root, prepare(root, { agent }));
      assert.ok(
        fs
          .readFileSync(path.join(root, "AGENTS.md"), "utf8")
          .startsWith("Corporate rules"),
      );
      assert.ok(
        fs
          .readFileSync(
            path.join(root, ".github/copilot-instructions.md"),
            "utf8",
          )
          .startsWith("Custom Copilot rules"),
      );
      assert.equal(
        fs.existsSync(
          path.join(root, ".github/workflows/copilot-setup-steps.yml"),
        ),
        false,
      );
      assert.equal(
        fs.existsSync(path.join(root, ".github/skills/implementer")),
        false,
      );
      assert.ok(
        fs.existsSync(path.join(root, ".agents/skills/implementer/SKILL.md")),
      );
      assert.ok(
        fs.existsSync(
          path.join(root, ".github/prompts/opsx-propose.prompt.md"),
        ),
      );
      assert.equal(prepare(root).filter((c) => c.action !== "keep").length, 0);
      assert.ok(!prepareUpgrade(root).some((c) => c.action === "conflict"));
      const checks = doctor(root).checks;
      for (const id of [
        "configuration",
        "copilot-instructions",
        "copilot-openspec",
        "skills",
        "openspec-project",
        "ownership",
      ])
        assert.equal(
          checks.find((c) => c.id === id)?.status,
          "PASS",
          `${agent}: ${id}`,
        );
      if (agent.endsWith("ide"))
        assert.equal(checks.find((c) => c.id === "copilot-cli").status, "SKIP");
      const availablePath = process.env.PATH;
      process.env.PATH = "";
      try {
        const absent = doctor(root).checks.find((c) => c.id === "copilot-cli");
        assert.equal(absent.status, agent.endsWith("ide") ? "SKIP" : "FAIL");
      } finally {
        process.env.PATH = availablePath;
      }
      const prompt = path.join(root, ".github/prompts/opsx-propose.prompt.md");
      fs.appendFileSync(prompt, "\nUser customization\n");
      assert.equal(
        prepare(root).find(
          (c) => c.path === ".github/prompts/opsx-propose.prompt.md",
        ).content,
        fs.readFileSync(prompt, "utf8"),
      );
    }
  },
);

test("HTTP authentication and policy errors stay blocked", async (t) => {
  for (const statusCode of [401, 403, 429]) {
    const o = fake(
      t,
      `console.log(JSON.stringify({type:'session.error',data:{errorType:'http_error',statusCode:${statusCode}}}));process.exitCode=1;`,
    );
    assert.equal((await runCopilot(o)).status, "BLOCKED");
  }
});
test(
  "cancellation terminates a descendant that ignores SIGTERM",
  { skip: process.platform === "win32" },
  async (t) => {
    const o = fake(
      t,
      `const {spawn}=require('node:child_process');spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setTimeout(()=>require('node:fs').writeFileSync('escaped','bad'),900)"],{stdio:'ignore'});setTimeout(()=>{},10000);`,
    );
    const result = await runCopilot({ ...o, timeoutMs: 150 });
    assert.equal(result.reason, "timeout");
    await new Promise((r) => setTimeout(r, 1000));
    assert.equal(fs.existsSync(path.join(o.cwd, "escaped")), false);
  },
);
