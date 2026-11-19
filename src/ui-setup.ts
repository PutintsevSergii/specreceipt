/** Repository setup adapter: reuse the installer; never grant lifecycle approvals. */
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { realpathSync, statSync } from 'node:fs';
import * as path from 'node:path';
import { homedir } from 'node:os';
import { prepare, install } from './install.js';
import { hash, safe } from './filesystem.js';
import { AGENTS, OPENSPEC_VERSION, nodeSupported, type Selection } from './core.js';
import { executable, invoke, probeOpenSpec, pythonCommand, KIT } from './integrations.js';
import { doctor } from './doctor.js';

export function prepareUIRuntime() {
  const runtime = process.env.HARNESS_RUNTIME_DIR ?? (process.platform === 'win32'
    ? path.join(process.env.LOCALAPPDATA ?? path.join(homedir(), 'AppData', 'Local'), 'harness', 'runtime')
    : path.join(process.env.XDG_DATA_HOME ?? path.join(homedir(), '.local', 'share'), 'harness', 'runtime'));
  process.env.HARNESS_RUNTIME_DIR = runtime;
  process.env.PATH = path.join(runtime, 'bin') + path.delimiter + (process.env.PATH ?? '');
}
export function ensureSetupPython(root: string, progress: (message: string) => void) {
  prepareUIRuntime();
  const check = () => { const python = pythonCommand(); return python && invoke(python, ['-c', 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'], root).status === 0; };
  if (check()) return;
  // An explicit runtime override is never silently replaced.
  if (process.env.HARNESS_PYTHON) throw Error('HARNESS_PYTHON does not identify Python >=3.11. Correct this override and retry.');
  progress('Installing the managed Python runtime (network required)…');
  const script = path.join(KIT, 'scripts', process.platform === 'win32' ? 'python.ps1' : 'python.sh');
  const command = process.platform === 'win32' ? executable('powershell') : '/bin/sh';
  if (!command) throw Error('PowerShell is required to prepare Python on Windows.');
  const args = process.platform === 'win32'
    ? ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', "& $env:SPECRECEIPT_BOOTSTRAP_SCRIPT -Bootstrap -CommandArgs @('--version'); exit $LASTEXITCODE"]
    : [script, '--bootstrap', '--version'];
  const result = invoke({ file: command, prefix: [] }, args, root, { ...process.env, SPECRECEIPT_BOOTSTRAP_SCRIPT: script }, 600000);
  if (result.status !== 0 || !check()) throw Error('Python bootstrap failed. Check network access and the managed runtime, then retry setup.');
}

export type SetupPlan = { root: string; agent: string; installOpenSpec: boolean; binding: string; changes: { path: string; action: string; reason: string }[]; conflicts: boolean };
export function setupPlan(input: { path: unknown; agent: unknown; installOpenSpec: unknown }): SetupPlan {
  if (!nodeSupported(process.versions.node)) throw Error('Setup requires Node >=22.20 and <25. Restart the UI with a supported Node runtime.');
  if (typeof input.path !== 'string' || input.path.length > 4096 || !path.isAbsolute(input.path.trim())) throw Error('Enter an absolute repository path.');
  if (typeof input.agent !== 'string' || !(AGENTS as readonly string[]).includes(input.agent)) throw Error('Select a supported agent integration.');
  if (typeof input.installOpenSpec !== 'boolean') throw Error('Choose whether to install OpenSpec.');
  const root = realpathSync(input.path.trim());
  if (!statSync(root).isDirectory()) throw Error('Select an existing project directory.');
  const changes = prepare(root, { agent: input.agent } as Partial<Selection>, true);
  return { root, agent: input.agent, installOpenSpec: input.installOpenSpec,
    binding: hash(JSON.stringify(changes)), conflicts: changes.some(c => c.action === 'conflict'),
    changes: changes.map(({ path, action, reason }) => ({ path, action, reason })) };
}
export function runSetup(plan: SetupPlan, progress: (message: string) => void): Promise<any> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('./ui-setup.js', import.meta.url), { workerData: plan });
    let result: any;
    worker.on('message', message => {
      if (message.progress) progress(message.progress);
      else result = message;
    });
    worker.once('error', reject);
    worker.once('exit', code => {
      if (code || !result?.ok) reject(Error(result?.error ?? 'Setup stopped unexpectedly. Inspect the installation before retrying.'));
      else resolve(result.diagnostics);
    });
  });
}
if (!isMainThread) {
  try {
    const plan = workerData as SetupPlan;
    const fresh = setupPlan({ path: plan.root, agent: plan.agent, installOpenSpec: plan.installOpenSpec });
    if (fresh.root !== plan.root || fresh.binding !== plan.binding || fresh.conflicts) throw Error('Project changed since preview. Review a new setup preview.');
    parentPort!.postMessage({ progress: 'Checking Python and OpenSpec…' });
    ensureSetupPython(plan.root, progress => parentPort!.postMessage({ progress }));
    if (probeOpenSpec(plan.root).state !== 'ready') {
      if (!plan.installOpenSpec) throw Error(`OpenSpec ${OPENSPEC_VERSION} is required. Enable its installation in a new preview or provide a compatible CLI.`);
      const npm = executable('npm');
      if (!npm) throw Error('npm is required to install OpenSpec.');
      const target = safe(plan.root, '.harness/tools/openspec');
      parentPort!.postMessage({ progress: `Installing OpenSpec ${OPENSPEC_VERSION} in the project (network required)…` });
      const result = invoke({ file: npm, prefix: [] }, ['install', '--prefix', target, '--ignore-scripts', '--no-audit', '--no-fund', `@fission-ai/openspec@${OPENSPEC_VERSION}`], plan.root, process.env, 180000);
      if (result.status !== 0) throw Error('OpenSpec download/install failed. Check network access and npm configuration, then preview and retry. Project-local dependency files may remain.');
    }
    parentPort!.postMessage({ progress: 'Staging agent integration and checking file conflicts…' });
    const changes = prepare(plan.root, { agent: plan.agent } as Partial<Selection>);
    // Recheck all previewed inputs after external tooling and before writing project files.
    const current = setupPlan({ path: plan.root, agent: plan.agent, installOpenSpec: plan.installOpenSpec });
    if (current.binding !== plan.binding) throw Error('Project changed during setup. Review a new preview; downloaded dependencies may remain.');
    parentPort!.postMessage({ progress: 'Installing and validating the project…' });
    install(plan.root, changes);
    parentPort!.postMessage({ progress: 'Checking installation health…' });
    parentPort!.postMessage({ ok: true, diagnostics: doctor(plan.root) });
  } catch (error) {
    parentPort!.postMessage({ ok: false, error: (error as Error).message });
  }
}
