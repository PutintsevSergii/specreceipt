import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  statSync,
  lstatSync,
  rmSync,
  chmodSync,
} from "node:fs";
import { join } from "node:path";
import { createHash } from "node:crypto";
const contracts = await import("../dist/core.js");
const packageVersion = JSON.parse(readFileSync("package.json", "utf8")).version;
if (contracts.VERSION !== packageVersion)
  throw Error("Package and CLI versions disagree");
const engineContract = await import("../dist/engine.js");
const protocolSource = readFileSync("harnesslib/protocol.py", "utf8");
if (
  protocolSource.match(/^ENGINE_VERSION = '([^']+)'/m)?.[1] !==
    engineContract.ENGINE_VERSION ||
  Number(protocolSource.match(/^PROTOCOL_VERSION = (\d+)/m)?.[1]) !==
    engineContract.PROTOCOL_VERSION
)
  throw Error("Python and TypeScript engine contracts disagree");
const pythonOpenSpec = readFileSync(
  "harnesslib/openspec_tool.py",
  "utf8",
).match(/^VERSION = '([^']+)'/m)?.[1];
if (contracts.OPENSPEC_VERSION !== pythonOpenSpec)
  throw Error("Node and Python OpenSpec compatibility pins disagree");
const roots = [
  "AGENTS.md",
  "harness",
  "install.sh",
  "install.ps1",
  "harness.cmd",
  "scripts/python.ps1",
  "scripts/uv.ps1",
  "harnesslib",
  "schemas",
  "templates",
  ".agents/skills",
  "tests",
  "scripts/python.sh",
  "scripts/update-tools.py",
  "docs/HARNESS.md",
  "docs/V02.md",
  "docs/V03.md",
  "docs/COPILOT.md",
  "docs/TECH_SPEC.md",
  "docs/ARCHITECTURE.md",
  "docs/DECISION_QUEUE.md",
  "docs/adr",
];
rmSync("assets", { recursive: true, force: true });
mkdirSync("assets/kit", { recursive: true });
const hashes = {};
function copy(rel) {
  if (lstatSync(rel).isSymbolicLink())
    throw Error("Symlink runtime asset refused");
  const info = statSync(rel);
  if (info.isDirectory()) {
    for (const item of readdirSync(rel).sort())
      if (!["__pycache__", ".DS_Store"].includes(item)) copy(join(rel, item));
    return;
  }
  if (!/\.(py|json|md|sh|ps1|cmd)$/.test(rel) && rel !== "harness")
    throw Error("Unexpected runtime asset " + rel);
  // The asset allowlist contains text only. Keep archives portable even when
  // Git checks source files out as CRLF on Windows (including POSIX shebangs).
  const bytes = Buffer.from(readFileSync(rel, "utf8").replace(/\r\n/g, "\n"), "utf8");
  const out = join("assets/kit", rel);
  mkdirSync(join(out, ".."), { recursive: true });
  writeFileSync(out, bytes);
  if (info.mode & 0o111) chmodSync(out, 0o755);
  hashes[rel.replaceAll("\\", "/")] = createHash("sha256")
    .update(bytes)
    .digest("hex");
}
for (const rel of roots) copy(rel);
// Generic installation seeds, never copy live state/evidence/tool directories.
for (const [rel, value] of Object.entries({
  ".harness/checks.json": {
    schema_version: 1,
    stack_revision: null,
    checks: {
      "harness-validate": {
        kind: "builtin",
        argv: [],
        timeout_seconds: 30,
        approved: true,
        approval_reference: "Selected Strict engineering profile",
        purpose: "Validate harness record structure",
      },
      "harness-tests": {
        kind: "command",
        argv: ["{python}", "-B", "harness", "self-test"],
        timeout_seconds: 1800,
        approved: true,
        approval_reference: "Selected Strict engineering profile",
        purpose: "Run isolated harness regressions",
      },
    },
  },
  ".harness/environment.json": {
    application_runtime: "UNCONFIGURED",
    note: "Declare application versions during onboarding.",
  },
  ".harness/graph-config.json": {
    provider: "local-python-ast",
    version: "1",
    max_bytes: 1048576,
    exclude: [
      "docs/ENGINEERING_LOG.md",
      "specs/*/verification.md",
      "specs/*/tasks.json",
      "*.min.js",
      "coverage/*",
    ],
  },
})) {
  const bytes = JSON.stringify(value, null, 2) + "\n";
  const out = join("assets/kit", rel);
  mkdirSync(join(out, ".."), { recursive: true });
  writeFileSync(out, bytes);
  hashes[rel] = createHash("sha256").update(bytes).digest("hex");
}
const cliHashes = {};
for (const name of readdirSync("dist").sort()) {
  if (name.endsWith(".js"))
    cliHashes["dist/" + name] = createHash("sha256")
      .update(readFileSync("dist/" + name))
      .digest("hex");
}
writeFileSync(
  "assets/cli-integrity.json",
  JSON.stringify(cliHashes, null, 2) + "\n",
);
writeFileSync("assets/integrity.json", JSON.stringify(hashes, null, 2) + "\n");
chmodSync("dist/cli.js", 0o755);
