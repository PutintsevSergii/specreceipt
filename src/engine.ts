/** The only process boundary for lifecycle and diagnosis. */
import * as path from "node:path";
import * as fs from "node:fs";
import { spawnSync } from "node:child_process";
import { manifest, read, hash, safe } from "./filesystem.js";
import { pythonCommand, kitAssets } from "./integrations.js";
export const ENGINE_VERSION = "0.4.4";
export const PROTOCOL_VERSION = 1;
export interface Response {
  protocolVersion: number;
  engineVersion: string;
  target: string;
  cwd: string;
  engineRoot: string;
  exitCode: number;
  data: any;
  error: { code: string; message: string } | null;
}
function sameDirectory(actual: unknown, expected: string): boolean {
  if (typeof actual !== "string" || !actual) return false;
  try {
    return fs.realpathSync.native(actual) === fs.realpathSync.native(expected);
  } catch {
    return false;
  }
}
export function request(
  root: string,
  argv: string[],
  engineRoot = root,
  env: NodeJS.ProcessEnv = process.env,
): Response {
  const python = pythonCommand(env);
  if (!python)
    throw Error(
      "Python runtime missing. Install Python >=3.11 or set HARNESS_PYTHON.",
    );
  const code =
    'import sys, importlib.util, pathlib; p=pathlib.Path(sys.argv[1])/"harnesslib"; s=importlib.util.spec_from_file_location("harnesslib", p/"__init__.py", submodule_search_locations=[str(p)]); m=importlib.util.module_from_spec(s); sys.modules["harnesslib"]=m; s.loader.exec_module(m); from harnesslib.protocol import main; sys.exit(main())';
  const r = spawnSync(python.file, [...python.prefix, "-I", "-B", "-X", "utf8", "-c", code, engineRoot], {
    cwd: root,
    input: JSON.stringify({
      protocolVersion: PROTOCOL_VERSION,
      target: root,
      argv,
    }),
    encoding: "utf8",
    timeout: 1800000,
    maxBuffer: 16 * 1024 * 1024,
    env: { ...env, PYTHONDONTWRITEBYTECODE: "1" },
  });
  if (r.error || r.signal || r.status === null)
    throw Error(
      "Python process unavailable or interrupted. Check Python >=3.11 and project recovery state before retrying.",
    );
  let value: Response;
  try {
    value = JSON.parse(r.stdout);
  } catch {
    throw Error(
      "Malformed engine response. Verify installed engine and Python >=3.11.",
    );
  }
  if (
    value.protocolVersion !== PROTOCOL_VERSION ||
    value.engineVersion !== ENGINE_VERSION ||
    !sameDirectory(value.target, root) ||
    !sameDirectory(value.cwd, root) ||
    !sameDirectory(value.engineRoot, engineRoot) ||
    !Number.isInteger(value.exitCode) ||
    value.exitCode !== r.status
  )
    throw Error(
      "Engine/protocol/target mismatch; run upgrade with the matching package.",
    );
  if (r.stderr) process.stderr.write(r.stderr);
  return value;
}
export function resolveEngine(root: string) {
  root = path.resolve(root);
  const owned = manifest(root);
  if (
    !owned ||
    owned.engineVersion !== ENGINE_VERSION ||
    owned.protocolVersion !== PROTOCOL_VERSION
  )
    throw Error(
      "Installed engine is incompatible or legacy. Run upgrade using the matching package and legacy baseline.",
    );
  for (const asset of kitAssets().filter(
    (a) =>
      a.path.startsWith("harnesslib/") ||
      a.path.startsWith("schemas/") ||
      a.path === "harness",
  )) {
    if (
      !owned.files[asset.path] ||
      owned.files[asset.path]!.hash !== hash(asset.content)
    )
      throw Error(
        `Engine inventory/version mismatch: ${asset.path}. Restore the matching release engine.`,
      );
  }
  for (const rel of [
    "harness",
    ...Object.keys(owned.files).filter(
      (p) => p.startsWith("harnesslib/") || p.startsWith("schemas/"),
    ),
  ]) {
    const record = owned.files[rel];
    const content = read(root, rel);
    if (!record || content === null || hash(content) !== record.hash)
      throw Error(
        `Installed engine modified or missing: ${rel}. Restore it before execution.`,
      );
  }
  safe(root, "harnesslib/protocol.py");
  const result = request(root, ["contract"]);
  if (result.exitCode) throw Error("Engine negotiation failed.");
  return result;
}
export function execute(root: string, argv: string[]): Response {
  root = path.resolve(root);
  const contract = resolveEngine(root);
  if (!contract.data.operations.includes(argv[0]) && argv[0] !== "--help")
    throw Error("Unsupported engine operation. Run specreceipt --help.");
  return request(root, argv);
}
