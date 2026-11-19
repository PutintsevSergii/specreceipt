/** Local browser adapter. Python remains the authority for lifecycle decisions. */
import { createServer } from 'node:http';
import { randomBytes, randomUUID, createHash } from 'node:crypto';
import { mkdirSync, writeFileSync, readdirSync, statSync, realpathSync, existsSync } from 'node:fs';
import * as path from 'node:path';
import { execute } from './engine.js';
import { safe, read } from './filesystem.js';
import { loadRepositories, saveRepository, repositoryId } from './ui-repositories.js';
import { setupPlan, runSetup, type SetupPlan } from './ui-setup.js';
import { html, css, script } from './ui-page.js';

type Engine = (root: string, argv: string[]) => { exitCode: number; data: any; error?: any };
const id = (value: unknown) => { if (typeof value !== 'string' || !/^[A-Z][A-Z0-9-]{0,99}$/.test(value)) throw Error('Invalid task ID'); return value; };
const text = (value: unknown, max = 8000) => { if (typeof value !== 'string' || !value.trim() || value.length > max) throw Error('A non-empty, bounded text value is required'); return value.trim(); };
function call(engine: Engine, root: string, argv: string[]) {
  const result = engine(root, argv);
  if (result.exitCode) throw Error(typeof result.data?.error === 'string' ? result.data.error : result.error?.message ?? JSON.stringify(result.data));
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

export async function startUI(root?: string, port = 4317, engine: Engine = execute, registryDirectory?: string) {
  const initialRoot = root ? realpathSync(path.resolve(root)) : undefined;
  const { repositories, warnings } = loadRepositories(registryDirectory);
  if (initialRoot) repositories.set(repositoryId(initialRoot), initialRoot);
  const repositoryList = () => [...repositories].map(([id, path]) => ({ id, path, name: path.split(/[\\/]/).pop() }));
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw Error('Invalid port');
  const token = randomBytes(32).toString('hex');
  // Capabilities exist only in server memory; mutation must refer to material shown by this session.
  const previews = new Map<string, { root: string; task: string; binding: string; compact: boolean; package: any }>();
  const setups = new Map<string, SetupPlan>();
  const jobs = new Map<string, any>();
  let setupRunning = false;
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
      if (req.method === 'GET' && url.pathname === '/api/repositories') return send(200, { repositories: repositoryList(), warnings, initialRepository: initialRoot ? repositoryId(initialRoot) : null });
      if (req.method === 'GET' && url.pathname === '/api/setup/job') {
        const job = jobs.get(url.searchParams.get('id') ?? '');
        return send(job ? 200 : 404, job ?? { error: 'Setup job not found in this session.' });
      }
      const selectedRepository = req.headers['x-specreceipt-repository'];
      const root = selectedRepository === undefined ? initialRoot : typeof selectedRepository === 'string' ? repositories.get(selectedRepository) : undefined;
      if (!root && !['/api/repositories', '/api/setup/preview', '/api/setup/install'].includes(url.pathname)) return send(404, { error: 'Repository is not connected to this session.' });
      if (req.method === 'GET' && url.pathname === '/api/navigation' && root) return send(200, call(engine, root, ['navigation', 'show']));
      if (req.method === 'GET' && url.pathname === '/api/status' && root) {
        return send(200, { ...call(engine, root, ['status', '--detailed']), questions: questions(root) });
      }
      if (req.method === 'GET' && url.pathname === '/api/package' && root) {
        const task = id(url.searchParams.get('task'));
        const result = call(engine, root, ['approval-package', task]);
        if (result.result !== 'PASS') return send(200, result);
        const report = call(engine, root, ['status', task]);
        const preview = randomUUID();
        if (previews.size >= 50) previews.delete(previews.keys().next().value!);
        previews.set(preview, { root, task, binding: result.acceptance_binding, compact: report.tasks[0].documentation === 'compact', package: result });
        return send(200, { ...result, preview });
      }
      if (req.method === 'GET' && url.pathname === '/api/artifact' && root) {
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
      if (req.method !== 'POST' || !['/api/answer', '/api/approve', '/api/repositories', '/api/setup/preview', '/api/setup/install', '/api/navigation'].includes(url.pathname)) return send(404, { error: 'Not found' });
      if (req.headers.origin !== origin || req.headers['content-type'] !== 'application/json') return send(403, { error: 'JSON and same-origin request required' });
      let body = ''; for await (const chunk of req) { body += chunk; if (Buffer.byteLength(body) > 24000) return send(413, { error: 'Request too large' }); }
      const input = JSON.parse(body);
      if (url.pathname === '/api/setup/preview') {
        if (setupRunning) throw Error('Wait for the current setup to finish.');
        const plan = setupPlan(input);
        const preview = randomUUID();
        if (setups.size >= 20) setups.delete(setups.keys().next().value!);
        setups.set(preview, plan);
        return send(200, { ...plan, binding: undefined, preview });
      }
      if (url.pathname === '/api/setup/install') {
        const plan = setups.get(input.preview);
        if (!plan || input.confirm !== true) throw Error('Review a setup preview and explicitly confirm installation.');
        if (plan.conflicts) throw Error('Resolve the displayed conflicts before installing.');
        if (setupRunning) throw Error('Wait for the current setup to finish.');
        if (repositories.size >= 50 && ![...repositories.values()].includes(plan.root)) throw Error('This session supports up to 50 repositories.');
        setups.delete(input.preview);
        setupRunning = true;
        if (jobs.size >= 20) jobs.delete(jobs.keys().next().value!);
        const job = { id: randomUUID(), path: plan.root, status: 'RUNNING', message: 'Starting setup…' } as any;
        jobs.set(job.id, job);
        void runSetup(plan, message => { job.message = message; }).then(diagnostics => {
          call(engine, plan.root, ['status', '--detailed']);
          const repository = saveRepository(registryDirectory, plan.root);
          repositories.set(repository.id, plan.root);
          Object.assign(job, { status: 'SUCCEEDED', message: 'Project installed. Review health checks; onboarding and task approvals remain required.', diagnostics, repository });
        }).catch(error => Object.assign(job, { status: 'FAILED', message: error.message }))
          .finally(() => { setupRunning = false; });
        return send(202, job);
      }
      if (url.pathname === '/api/repositories') {
        const requested = text(input.path, 4096);
        if (!path.isAbsolute(requested)) throw Error('Enter an absolute repository path.');
        const candidate = realpathSync(requested);
        if (!statSync(candidate).isDirectory()) throw Error('Repository path must be a directory.');
        if (repositories.size >= 50 && !repositories.has(repositoryId(candidate))) throw Error('This session supports up to 50 repositories.');
        // Detect a new directory without turning damaged/legacy installations into implicit reinstalls.
        const configured = ['.harness/product.json', '.harness/installation-manifest.json', '.harness/state.json', 'harness', 'harnesslib'].some(rel => existsSync(safe(candidate, rel)));
        if (!configured && engine === execute) {
          const plan = setupPlan({ path: candidate, agent: input.agent ?? 'codex', installOpenSpec: true });
          const preview = randomUUID();
          if (setups.size >= 20) setups.delete(setups.keys().next().value!);
          setups.set(preview, plan);
          return send(200, { setupRequired: true, plan: { ...plan, binding: undefined, preview } });
        }
        call(engine, candidate, ['status', '--detailed']);
        const repository = saveRepository(registryDirectory, candidate);
        repositories.set(repository.id, candidate);
        return send(200, { repository });
      }
      if (!root) return send(404, { error: 'Select a repository first.' });
      if (url.pathname === '/api/navigation') {
        if (!['source', 'auto', 'custom'].includes(input.mode) || !Array.isArray(input.providers) ||
            input.providers.some((name: unknown) => !['codegraph', 'graphify'].includes(name as string)) ||
            new Set(input.providers).size !== input.providers.length ||
            (input.mode === 'source' ? input.providers.length !== 0 : input.providers.length === 0) ||
            typeof input.expected !== 'string' || !/^[a-f0-9]{64}$/.test(input.expected)) throw Error('Invalid navigation settings. Reload and select a mode and providers.');
        const argv = ['navigation', 'set', '--mode', input.mode, '--expected', input.expected];
        if (input.providers.length) argv.push('--providers', ...input.providers);
        return send(200, call(engine, root, argv));
      }
      const by = text(input.by, 120);
      if (url.pathname === '/api/answer') {
        const question = questions(root).find(q => q.id === input.question_id);
        if (!question || question.answer) throw Error('Question missing or already answered');
        const answer = { question_id: question.id, task_id: question.task_id, by, answer: text(input.answer), at: new Date().toISOString() };
        append(root, 'answers', answer, question.id);
        return send(200, { message: 'Ответ сохранён. Агент прочитает его через ui questions.', answer });
      }
      const preview = previews.get(input.preview);
      if (!preview || preview.root !== root || input.confirm !== true) throw Error('Review the current package and explicitly confirm acceptance.');
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
