import { test } from 'node:test';
import { request } from 'node:http';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startUI, askQuestion, questions } from '../dist/ui.js';

test('local UI authenticates, stores answers once, binds explicit approvals and restricts artifacts', async t => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'sr-ui-')));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  let binding = 'current', blocked = false;
  const mutations = [];
  const engine = (_root, argv) => {
    if (argv[0] === 'status') return { exitCode: 0, data: { project: root, tasks: [{ task_id: 'UI-001', documentation: 'formal', paths: {}, verification: { checks: [] } }] } };
    if (argv[0] === 'approval-package') return { exitCode: 0, data: blocked ? { result: 'BLOCKED', reason: 'stale review' } : { result: 'PASS', acceptance_binding: binding, paths: { review: join(root, 'review.md') } } };
    mutations.push(argv); return { exitCode: 0, data: { recorded: 'developer' } };
  };
  const ui = await startUI(root, 0, engine);
  t.after(() => { ui.server.closeAllConnections(); ui.server.close(); });
  const get = (path, headers = {}) => fetch(ui.origin + path, { headers: { Authorization: `Bearer ${ui.token}`, ...headers } });
  const post = (path, data, headers = {}) => fetch(ui.origin + path, { method: 'POST', headers: { Authorization: `Bearer ${ui.token}`, Origin: ui.origin, 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(data) });
  assert.equal((await fetch(ui.origin + '/api/status')).status, 401);
  assert.equal((await get('/api/status', { Origin: 'https://evil.test' })).status, 403);
  const foreignHost = await new Promise((resolve, reject) => {
    const req = request(ui.origin + '/api/status', { headers: { Host: 'evil.test', Authorization: `Bearer ${ui.token}` } }, res => { res.resume(); resolve(res.statusCode); });
    req.on('error', reject); req.end();
  });
  assert.equal(foreignHost, 403);
  const page = await fetch(ui.origin);
  assert.match(page.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  assert.ok(!(await page.text()).includes(ui.token));
  const q = askQuestion(root, 'UI-001', 'Which behaviour should we implement?', engine);
  assert.equal(questions(root)[0].answer, null);
  const answer = { question_id: q.id, by: 'Developer', answer: 'Use the documented behaviour.' };
  assert.equal((await post('/api/answer', answer, { Origin: 'https://evil.test' })).status, 403);
  assert.equal((await post('/api/answer', answer)).status, 200);
  assert.equal((await post('/api/answer', answer)).status, 400);
  assert.equal(questions(root)[0].answer.answer, answer.answer);
  assert.equal((await get('/api/artifact?task=UI-001&path=' + encodeURIComponent('/etc/passwd'))).status, 403);
  writeFileSync(join(root, 'review.md'), '<script>alert(1)</script>');
  assert.equal((await (await get('/api/artifact?task=UI-001&path=' + encodeURIComponent(join(root, 'review.md')))).json()).content, '<script>alert(1)</script>');
  const preview = await (await get('/api/package?task=UI-001')).json();
  assert.equal((await post('/api/approve', { preview: preview.preview, by: 'Developer' })).status, 400);
  binding = 'changed';
  assert.equal((await post('/api/approve', { preview: preview.preview, by: 'Developer', confirm: true })).status, 409);
  assert.equal(mutations.length, 0);
  const current = await (await get('/api/package?task=UI-001')).json();
  assert.equal((await post('/api/approve', { preview: current.preview, by: 'Developer', confirm: true })).status, 200);
  assert.deepEqual(mutations[0].slice(0, 5), ['task', 'approve', 'UI-001', '--kind', 'developer']);
  assert.deepEqual(mutations[0].slice(-2), ['--expected', 'changed']);
  assert.equal((await post('/api/approve', { preview: current.preview, by: 'Developer', confirm: true })).status, 400);
  blocked = true;
  assert.equal((await (await get('/api/package?task=UI-001')).json()).result, 'BLOCKED');
  assert.equal(mutations.length, 1);
});

test('UI rejects malformed queue records and identifiers', async t => {
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'sr-ui-path-')));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  assert.throws(() => askQuestion(root, '../../bad', 'question'), /Invalid task/);
  mkdirSync(join(root, '.harness/ui/questions'), { recursive: true });
  writeFileSync(join(root, '.harness/ui/questions/a.json'), 'invalid');
  assert.throws(() => questions(root), /JSON|Unexpected/);
});

test('HTTP acceptance and questions integrate with the real Python engine in an isolated fixture', async t => {
  const { spawnSync } = await import('node:child_process');
  const { request: engineRequest } = await import('../dist/engine.js');
  const { pythonCommand } = await import('../dist/integrations.js');
  const root = realpathSync(mkdtempSync(join(tmpdir(), 'sr-ui-engine-')));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const python = pythonCommand();
  const setup = spawnSync(python.file, [...python.prefix, '-B', '-c', `
import sys, shutil
sys.path.insert(0, 'tests')
from test_reporting import ReportingTests
from harnesslib.storage import atomic
case = ReportingTests(); case.setUp()
f,t = case.h.task('DEMO-001'); t['approval_requirements'] = ['developer']
atomic(case.root/'specs/harness-demo/tasks.json', f)
shutil.copytree(case.root, sys.argv[1], dirs_exist_ok=True)
from pathlib import Path
from harnesslib.core import Harness
case.root = Path(sys.argv[1]); case.h = Harness(case.root)
case.verified(); case.review()
`, root], { encoding: 'utf8' });
  assert.equal(setup.status, 0, setup.stderr);
  const engine = (r, argv) => engineRequest(r, argv);
  const ui = await startUI(root, 0, engine);
  t.after(() => { ui.server.closeAllConnections(); ui.server.close(); });
  const headers = { Authorization: `Bearer ${ui.token}` };
  const status = await (await fetch(ui.origin + '/api/status', { headers })).json();
  assert.equal(status.tasks[0].task_id, 'DEMO-001');
  const q = askQuestion(root, 'DEMO-001', 'Is the reported behavior expected?', engine);
  const reply = await fetch(ui.origin + '/api/answer', { method: 'POST', headers: { ...headers, Origin: ui.origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ question_id: q.id, by: 'Integration fixture', answer: 'Yes, use the documented behavior.' }) });
  assert.equal(reply.status, 200);
  assert.equal(questions(root)[0].answer.by, 'Integration fixture');
  const packageResponse = await (await fetch(ui.origin + '/api/package?task=DEMO-001', { headers })).json();
  {
    assert.equal(packageResponse.result, 'PASS');
    const approval = await fetch(ui.origin + '/api/approve', { method: 'POST', headers: { ...headers, Origin: ui.origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ preview: packageResponse.preview, by: 'Integration fixture', confirm: true }) });
    assert.equal(approval.status, 200, await approval.text());
    assert.equal(engine(root, ['status', 'DEMO-001']).data.tasks[0].approvals.developer.status, 'CURRENT');
  }
});
