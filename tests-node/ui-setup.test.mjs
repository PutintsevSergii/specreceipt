import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, realpathSync, rmSync, readdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, delimiter } from 'node:path';
import { startUI } from '../dist/ui.js';
import { setupPlan, runSetup } from '../dist/ui-setup.js';

function directory(t) {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'sr-ui-setup-')));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}
async function session(t, root, registryDirectory) {
  const ui = await startUI(root, 0, undefined, registryDirectory);
  t.after(() => { ui.server.closeAllConnections(); ui.server.close(); });
  const request = (path, body, extra = {}) => fetch(ui.origin + path, {
    method: body ? 'POST' : 'GET', headers: { Authorization: `Bearer ${ui.token}`, Origin: ui.origin,
      ...(body ? { 'Content-Type': 'application/json' } : {}), ...extra }, ...(body ? { body: JSON.stringify(body) } : {})
  });
  const wait = async id => {
    for (let i = 0; i < 300; i++) {
      const job = await (await request('/api/setup/job?id=' + id)).json();
      if (job.status !== 'RUNNING') return job;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw Error('Setup timed out');
  };
  return { ui, request, wait };
}

test('setup preview is read-only, validates options and detects stale inputs before any writes', async t => {
  const root = directory(t);
  const input = { path: root, agent: 'codex', installOpenSpec: false };
  const plan = setupPlan(input);
  assert.equal(plan.conflicts, false);
  assert.ok(plan.changes.some(c => c.path === 'AGENTS.md'));
  assert.deepEqual(readdirSync(root), []);
  assert.throws(() => setupPlan({ ...input, path: '../relative' }), /absolute/);
  assert.throws(() => setupPlan({ ...input, agent: 'shell-command' }), /supported/);
  assert.throws(() => setupPlan({ ...input, installOpenSpec: 'yes' }), /Choose/);
  writeFileSync(join(root, 'AGENTS.md'), 'User-owned instructions\n');
  await assert.rejects(runSetup(plan, () => {}), /changed since preview/);
  assert.deepEqual(readdirSync(root), ['AGENTS.md']);
  assert.equal(readFileSync(join(root, 'AGENTS.md'), 'utf8'), 'User-owned instructions\n');
});

test('setup HTTP requires authenticated same-origin confirmation and consumes stale previews once', async t => {
  const root = directory(t);
  const { ui, request, wait } = await session(t, root);
  const input = { path: root, agent: 'codex', installOpenSpec: false };
  assert.equal((await fetch(ui.origin + '/api/setup/job?id=x')).status, 401);
  assert.equal((await request('/api/setup/preview', input, { Origin: 'https://evil.test' })).status, 403);
  const preview = await (await request('/api/setup/preview', input)).json();
  assert.equal(preview.binding, undefined);
  assert.equal((await request('/api/setup/install', { preview: preview.preview })).status, 400);
  assert.equal((await request('/api/setup/install', { preview: 'unknown', confirm: true })).status, 400);
  writeFileSync(join(root, 'AGENTS.md'), 'New instructions');
  const response = await request('/api/setup/install', { preview: preview.preview, confirm: true });
  assert.equal(response.status, 202);
  const job = await wait((await response.json()).id);
  assert.equal(job.status, 'FAILED');
  assert.match(job.message, /changed since preview/);
  assert.equal(existsSync(join(root, '.harness')), false);
  assert.equal((await request('/api/setup/install', { preview: preview.preview, confirm: true })).status, 400);
});

test('UI installs a real empty project, reports diagnostics and opens its repository without approvals', { skip: !process.env.HARNESS_REAL_OPENSPEC }, async t => {
  const root = directory(t);
  const previous = process.env.PATH;
  process.env.PATH = dirname(process.env.HARNESS_REAL_OPENSPEC) + delimiter + previous;
  t.after(() => { process.env.PATH = previous; });
  const registry = directory(t);
  const { request, wait } = await session(t, undefined, registry);
  assert.deepEqual((await (await request('/api/repositories')).json()).repositories, []);
  const response = await request('/api/repositories', { path: root, agent: 'codex' });
  assert.equal(response.status, 200);
  const selected = await response.json();
  assert.equal(selected.setupRequired, true);
  const plan = selected.plan;
  const started = await request('/api/setup/install', { preview: plan.preview, confirm: true });
  assert.equal(started.status, 202);
  const job = await wait((await started.json()).id);
  assert.equal(job.status, 'SUCCEEDED', job.message);
  assert.ok(job.diagnostics.checks.some(c => c.id === 'repository' && c.status === 'PASS'));
  const status = await (await request('/api/status', undefined, { 'X-SpecReceipt-Repository': job.repository.id })).json();
  assert.equal(status.project, root);
  assert.ok(existsSync(join(root, '.harness/installation-manifest.json')));
  assert.equal(existsSync(join(root, '.harness/approvals')), false);
  const reopened = await session(t, undefined, registry);
  const saved = (await (await reopened.request('/api/repositories')).json()).repositories;
  assert.equal(saved.length, 1);
  assert.equal(saved[0].path, root);
  assert.equal(saved[0].id, job.repository.id);
  const configured = await (await reopened.request('/api/repositories', { path: root })).json();
  assert.equal(configured.setupRequired, undefined);
  assert.equal(configured.repository.id, saved[0].id);
  const headers = { 'X-SpecReceipt-Repository': job.repository.id };
  const nav = await (await reopened.request('/api/navigation', undefined, headers)).json();
  assert.equal(nav.policy.mode, 'source');
  assert.equal((await reopened.request('/api/navigation', { mode: 'auto', providers: ['graphify'], expected: nav.revision }, { ...headers, Origin: 'https://evil.test' })).status, 403);
  const changed = await reopened.request('/api/navigation', { mode: 'auto', providers: ['graphify'], expected: nav.revision }, headers);
  assert.equal(changed.status, 200, await changed.clone().text());
  assert.deepEqual((await changed.json()).policy, { schema_version: 2, mode: 'auto', providers: ['graphify'] });
  const { request: engineRequest } = await import('../dist/engine.js');
  assert.equal(engineRequest(root, ['navigation', 'show']).data.policy.mode, 'auto');
  assert.equal(engineRequest(root, ['doctor', '--execution-requirements']).data.navigation_cli_required, false);
  assert.equal(engineRequest(root, ['navigation', 'set', '--mode', 'source']).exitCode, 0);
  const stale = await reopened.request('/api/navigation', { mode: 'custom', providers: ['codegraph'], expected: nav.revision }, headers);
  assert.equal(stale.status, 400);
  assert.equal(engineRequest(root, ['navigation', 'show']).data.policy.mode, 'source');
  assert.equal((await reopened.request('/api/navigation', { mode: 'custom', providers: [], expected: nav.revision }, headers)).status, 400);

});


test('target-free UI permits setup without allowing repository-scoped operations', async t => {
  const root = directory(t);
  const { request } = await session(t, undefined, directory(t));
  assert.deepEqual((await (await request('/api/repositories')).json()).repositories, []);
  assert.equal((await request('/api/status')).status, 404);
  assert.equal((await request('/api/answer', { by: 'Developer', answer: 'x' })).status, 404);
  const selection = await (await request('/api/repositories', { path: root })).json();
  assert.equal(selection.setupRequired, true);
  assert.equal(selection.plan.installOpenSpec, true);
  assert.deepEqual(readdirSync(root), []);
  assert.deepEqual((await (await request('/api/repositories')).json()).repositories, []);
});

test('repository bookmarks survive restart, deduplicate paths and never execute projects during discovery', async t => {
  const { saveRepository, loadRepositories } = await import('../dist/ui-repositories.js');
  const root = directory(t), registry = directory(t);
  const first = saveRepository(registry, root);
  assert.equal(saveRepository(registry, root).id, first.id);
  assert.equal(loadRepositories(registry).repositories.size, 1);
  writeFileSync(join(registry, 'repositories', 'a'.repeat(64) + '.json'), 'invalid');
  const stored = loadRepositories(registry);
  assert.equal(stored.repositories.size, 1);
  assert.equal(stored.warnings.length, 1);
  const ui = await startUI(undefined, 0, () => { throw Error('Must not execute on startup'); }, registry);
  t.after(() => { ui.server.closeAllConnections(); ui.server.close(); });
  const list = await (await fetch(ui.origin + '/api/repositories', { headers: { Authorization: `Bearer ${ui.token}` } })).json();
  assert.equal(list.repositories[0].id, first.id);
  assert.equal(list.warnings.length, 1);
});

test('missing Python is prepared through the packaged bootstrap and reused', { skip: process.platform === 'win32' }, async t => {
  const { mkdirSync, symlinkSync } = await import('node:fs');
  const { pythonCommand } = await import('../dist/integrations.js');
  const { ensureSetupPython } = await import('../dist/ui-setup.js');
  const python = pythonCommand();
  assert.ok(python && python.prefix.length === 0);
  const root = directory(t), runtime = join(root, 'runtime'), bin = join(runtime, 'bin');
  mkdirSync(bin, { recursive: true });
  // A pre-existing uv fixture supplies the real interpreter without downloading it.
  writeFileSync(join(bin, 'uv'), '#!/bin/sh\nif [ "$2" = find ]; then printf "%s\\n" "$TEST_UI_PYTHON"; fi\n', { mode: 0o755 });
  for (const [name, source] of [['uname', '/usr/bin/uname'], ['mkdir', '/bin/mkdir'], ['ln', '/bin/ln']]) symlinkSync(source, join(bin, name));
  const keys = ['PATH', 'HARNESS_RUNTIME_DIR', 'HARNESS_PYTHON', 'TEST_UI_PYTHON'];
  const saved = Object.fromEntries(keys.map(k => [k, process.env[k]]));
  t.after(() => { for (const k of keys) { if (saved[k] === undefined) delete process.env[k]; else process.env[k] = saved[k]; } });
  delete process.env.HARNESS_PYTHON;
  process.env.PATH = bin;
  process.env.HARNESS_RUNTIME_DIR = runtime;
  process.env.TEST_UI_PYTHON = python.file;
  const progress = [];
  ensureSetupPython(root, message => progress.push(message));
  assert.ok(progress.some(m => m.includes('Installing')));
  assert.ok(existsSync(join(bin, 'python3')));
  ensureSetupPython(root, () => assert.fail('Prepared Python should be reused'));
});
