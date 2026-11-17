/** Local browser adapter. Python remains the authority for lifecycle decisions. */
import { createServer } from 'node:http';
import { randomBytes, randomUUID, createHash } from 'node:crypto';
import { mkdirSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import * as path from 'node:path';
import { execute } from './engine.js';
import { safe, read } from './filesystem.js';
import { html, css, script } from './ui-page.js';

type Engine = (root: string, argv: string[]) => { exitCode: number; data: any; error?: any };
const id = (value: unknown) => { if (typeof value !== 'string' || !/^[A-Z][A-Z0-9-]{0,99}$/.test(value)) throw Error('Invalid task ID'); return value; };
const text = (value: unknown, max = 8000) => { if (typeof value !== 'string' || !value.trim() || value.length > max) throw Error('A non-empty, bounded text value is required'); return value.trim(); };
function call(engine: Engine, root: string, argv: string[]) {
  const result = engine(root, argv);
  if (result.exitCode) throw Error(result.error?.message ?? JSON.stringify(result.data));
  return result.data;
}
function entries(root: string, kind: string) {
  const dir = safe(root, `.harness/ui/${kind}`);
  try { return readdirSync(dir).filter(n => /^[a-f0-9-]+\.json$/.test(n)).map(n => JSON.parse(read(root, `.harness/ui/${kind}/${n}`)!)); }
  catch (e) { if ((e as NodeJS.ErrnoException).code === 'ENOENT') return []; throw e; }
}
function append(root: string, kind: string, value: any, name = randomUUID()) {
  const file = safe(root, `.harness/ui/${kind}/${name}.json`);
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(value, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
}
export function questions(root: string) {
  const answers = entries(root, 'answers');
  return entries(root, 'questions').map(q => ({ ...q, answer: answers.find(a => a.question_id === q.id) ?? null }));
}
export function askQuestion(root: string, task: string, question: string, engine: Engine = execute) {
  task = id(task); question = text(question);
  call(engine, root, ['status', task]);
  const item = { id: randomUUID(), task_id: task, question, created_at: new Date().toISOString() };
  append(root, 'questions', item, item.id);
  return item;
}

export async function startUI(root: string, port = 4317, engine: Engine = execute) {
  root = path.resolve(root);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw Error('Invalid port');
  const token = randomBytes(32).toString('hex');
  // Capabilities exist only in server memory; mutation must refer to material shown by this session.
  const previews = new Map<string, { task: string; binding: string; compact: boolean; package: any }>();
  let origin = '';
  const server = createServer(async (req, res) => {
    const send = (status: number, value: any, type = 'application/json') => {
      res.writeHead(status, { 'Content-Type': type + '; charset=utf-8', 'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer',
        'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'" });
      res.end(type === 'application/json' ? JSON.stringify(value) : value);
    };
    try {
      if (req.headers.host !== new URL(origin).host || (req.headers.origin && req.headers.origin !== origin)) return send(403, { error: 'Local origin required' });
      const url = new URL(req.url!, origin);
      if (req.method === 'GET' && ['/', '/app.css', '/app.js'].includes(url.pathname)) {
        return send(200, url.pathname === '/' ? html : url.pathname === '/app.css' ? css : script, url.pathname === '/' ? 'text/html' : url.pathname === '/app.css' ? 'text/css' : 'text/javascript');
      }
      if (req.headers.authorization !== `Bearer ${token}`) return send(401, { error: 'Open the session URL printed by the CLI.' });
      if (req.method === 'GET' && url.pathname === '/api/status') {
        return send(200, { ...call(engine, root, ['status', '--detailed']), questions: questions(root) });
      }
      if (req.method === 'GET' && url.pathname === '/api/package') {
        const task = id(url.searchParams.get('task'));
        const result = call(engine, root, ['approval-package', task]);
        if (result.result !== 'PASS') return send(200, result);
        const report = call(engine, root, ['status', task]);
        const preview = randomUUID();
        if (previews.size >= 50) previews.delete(previews.keys().next().value!);
        previews.set(preview, { task, binding: result.acceptance_binding, compact: report.tasks[0].documentation === 'compact', package: result });
        return send(200, { ...result, preview });
      }
      if (req.method === 'GET' && url.pathname === '/api/artifact') {
        // Only documents explicitly offered by the engine's current report/package may be read.
        const task = id(url.searchParams.get('task'));
        const report = call(engine, root, ['status', task]).tasks[0];
        const pack = call(engine, root, ['approval-package', task]);
        const requested = url.searchParams.get('path');
        const allowed = [...Object.values(pack.paths ?? {}), report.paths?.review, report.paths?.evidence,
          ...report.verification.checks.map((c: any) => c.log && path.resolve(root, c.log))].filter(v => typeof v === 'string');
        if (!requested || !allowed.includes(path.normalize(requested))) return send(403, { error: 'Artifact is not part of this task review.' });
        const relative = path.relative(root, requested).split(path.sep).join('/');
        const file = safe(root, relative);
        if (statSync(file).size > 512 * 1024) throw Error('Artifact exceeds 512 KB; inspect locally.');
        return send(200, { path: relative, content: read(root, relative) });
      }
      if (req.method !== 'POST' || !['/api/answer', '/api/approve'].includes(url.pathname)) return send(404, { error: 'Not found' });
      if (req.headers.origin !== origin || req.headers['content-type'] !== 'application/json') return send(403, { error: 'JSON and same-origin request required' });
      let body = ''; for await (const chunk of req) { body += chunk; if (Buffer.byteLength(body) > 24000) return send(413, { error: 'Request too large' }); }
      const input = JSON.parse(body);
      const by = text(input.by, 120);
      if (url.pathname === '/api/answer') {
        const question = questions(root).find(q => q.id === input.question_id);
        if (!question || question.answer) throw Error('Question missing or already answered');
        const answer = { question_id: question.id, task_id: question.task_id, by, answer: text(input.answer), at: new Date().toISOString() };
        append(root, 'answers', answer, question.id);
        return send(200, { message: 'Ответ сохранён. Агент прочитает его через ui questions.', answer });
      }
      const preview = previews.get(input.preview);
      if (!preview || input.confirm !== true) throw Error('Review the current package and explicitly confirm acceptance.');
      const current = call(engine, root, ['approval-package', preview.task]);
      if (current.result !== 'PASS' || current.acceptance_binding !== preview.binding) { previews.delete(input.preview); return send(409, { error: 'Результат изменился. Откройте актуальный пакет ещё раз.' }); }
      const reference = `.harness/approvals/ui-${randomUUID()}.txt`;
      const file = safe(root, reference); mkdirSync(path.dirname(file), { recursive: true });
      writeFileSync(file, `Explicit developer acceptance from the local UI\nBy: ${by}\nTask: ${preview.task}\nBinding: ${preview.binding}\nAt: ${new Date().toISOString()}\nDecision: Approve the displayed verified result.\nPackage SHA256: ${createHash('sha256').update(JSON.stringify(preview.package)).digest('hex')}\n${JSON.stringify(preview.package, null, 2)}\n`, { flag: 'wx', mode: 0o600 });
      previews.delete(input.preview);
      const argv = preview.compact ? ['workflow', 'accept', preview.task] : ['task', 'approve', preview.task, '--kind', 'developer'];
      const result = call(engine, root, [...argv, '--by', by, '--reference', reference, '--expected', preview.binding]);
      return send(200, { message: preview.compact ? 'Результат принят. Задача завершена.' : 'Approval записан. Финальный переход выполняется обычным workflow.', result });
    } catch (e) { send(400, { error: (e as Error).message }); }
  });
  server.requestTimeout = 15000;
  await new Promise<void>((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', () => resolve()); });
  const address = server.address();
  origin = `http://127.0.0.1:${typeof address === 'object' && address ? address.port : port}`;
  return { server, url: `${origin}/#token=${token}`, origin, token };
}
