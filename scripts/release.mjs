/** Release configuration tooling. package.json.version is the only editable version. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const stable = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

export function version(value) {
  if (typeof value !== 'string' || !stable.test(value) || !value.split('.').every(v=>Number.isSafeInteger(Number(v)))) throw Error('Expected a stable major.minor.patch version');
  return value;
}

export function synchronize(directory = root, check = false) {
  const pkg = JSON.parse(fs.readFileSync(path.join(directory, 'package.json'), 'utf8'));
  const target = version(pkg.version);
  const changes = [];
  const markers = [
    ['src/core.ts', /^export const VERSION = "[^"]*";/gm, `export const VERSION = "${target}";`],
    ['src/engine.ts', /^export const ENGINE_VERSION = "[^"]*";/gm, `export const ENGINE_VERSION = "${target}";`],
    ['harnesslib/protocol.py', /^ENGINE_VERSION = '[^']*'/gm, `ENGINE_VERSION = '${target}'`],
  ];
  // Validate every input before writing any derived file.
  for (const [relative, pattern, replacement] of markers) {
    const file = path.join(directory, relative);
    const before = fs.readFileSync(file, 'utf8');
    if ([...before.matchAll(pattern)].length !== 1) throw Error(`Expected exactly one version marker in ${relative}`);
    const after = before.replace(pattern, replacement);
    if (before !== after) changes.push({file, after});
  }
  const lockFile = path.join(directory, 'package-lock.json');
  const lockBefore = fs.readFileSync(lockFile, 'utf8');
  const lock = JSON.parse(lockBefore);
  if (lock.name !== pkg.name || lock.packages?.['']?.name !== pkg.name) throw Error('Lockfile package identity mismatch');
  if (lock.version !== target || lock.packages[''].version !== target) {
    lock.version = target;
    lock.packages[''].version = target;
    changes.push({file:lockFile, after:JSON.stringify(lock, null, 2)+'\n'});
  }
  if (check && changes.length) throw Error('Version drift: '+changes.map(c => path.relative(directory,c.file)).join(', '));
  if (!check) for (const change of changes) fs.writeFileSync(change.file, change.after);
  return {version:target, changed:changes.map(c => path.relative(directory,c.file))};
}

export function publishContext(event, ref, repository, expectedRepository, sourceSha, mainSha) {
  return event === 'push' && ref === 'refs/heads/main' && repository === expectedRepository &&
    /^[a-f0-9]{40}$/.test(sourceSha) && sourceSha === mainSha;
}

function compare(a, b) {
  const left = version(a).split('.').map(BigInt), right = version(b).split('.').map(BigInt);
  for (let i=0; i<3; i++) if (left[i] !== right[i]) return left[i] > right[i] ? 1 : -1;
  return 0;
}

export function requirePublishingNpm(value) {
  if (compare(value, '11.5.1') < 0) throw Error('npm >=11.5.1 is required for trusted publishing');
}

export async function registryDecision(pkg, request = fetch) {
  const current = version(pkg.version);
  if (pkg.name !== 'specreceipt' || pkg.private === true || pkg.publishConfig?.registry !== 'https://registry.npmjs.org/' ||
      pkg.repository?.url !== 'git+https://github.com/PutintsevSergii/specreceipt.git') throw Error('Unexpected release package identity, privacy or registry');
  const response = await request('https://registry.npmjs.org/'+encodeURIComponent(pkg.name), {signal:AbortSignal.timeout(15000)});
  if (!response.ok) throw Error(`Cannot inspect existing npm package: HTTP ${response.status}`);
  const metadata = await response.json();
  if (metadata.name !== pkg.name || !metadata.versions || typeof metadata.versions !== 'object' || Array.isArray(metadata.versions)) throw Error('Invalid npm package metadata');
  if (Object.hasOwn(metadata.versions, current)) {
    if (metadata.versions[current]?.version !== current || metadata.versions[current]?.name !== pkg.name) throw Error('Invalid existing version metadata');
    return {version:current, publish:false, reason:'Version already published'};
  }
  const latest = metadata['dist-tags']?.latest;
  if (!latest || metadata.versions[latest]?.name !== pkg.name || metadata.versions[latest]?.version !== latest) throw Error('Invalid npm latest metadata');
  if (!latest || compare(current, latest) <= 0) throw Error('New stable version must be greater than npm latest');
  return {version:current, publish:true, reason:'New version from package.json'};
}

async function main() {
  const [command, ...extra] = process.argv.slice(2);
  if (extra.length) throw Error('Unexpected release arguments');
  if (command === 'sync' || command === 'check') return console.log(JSON.stringify(synchronize(root,command === 'check')));
  if (command === 'registry-check') {
    synchronize(root, true);
    const result = await registryDecision(JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8')));
    if (process.env.GITHUB_OUTPUT) fs.appendFileSync(process.env.GITHUB_OUTPUT, `publish=${result.publish}\nversion=${result.version}\n`);
    return console.log(JSON.stringify(result));
  }
  throw Error('Usage: node scripts/release.mjs sync|check|registry-check');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode=1; });
}
