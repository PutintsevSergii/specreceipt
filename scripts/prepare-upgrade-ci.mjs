/** Supply reproducible inputs for the selected real two-version upgrade check. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const BASELINE = Object.freeze({
  name: 'specreceipt', version: '0.4.4', openspec: '1.14.3',
  integrity: 'sha512-hJRnaDrJkFsuGBiu0EG109U9tRD94wmZ6/sG05HvcF/2rIeuhKRTPXlCWFWYfCUTWcQgOKyORjkv2qUJROCwOg==',
});
export function verifyArchive(record, directory, expected) {
  if (record?.name !== expected.name || record.version !== expected.version ||
      record.filename !== `${expected.name}-${expected.version}.tgz`) throw Error('Unexpected upgrade archive identity');
  const file = path.join(directory, record.filename);
  const integrity = 'sha512-' + createHash('sha512').update(fs.readFileSync(file)).digest('base64');
  if (integrity !== record.integrity || (expected.integrity && integrity !== expected.integrity)) throw Error('Upgrade archive integrity mismatch');
  return file;
}
export function environmentLines(values) {
  return Object.entries(values).map(([key, value]) => {
    if (!/^[A-Z_]+$/.test(key) || typeof value !== 'string' || /[\r\n\0]/.test(value)) throw Error('Invalid upgrade environment entry');
    return `${key}=${value}\n`;
  }).join('');
}
export function prepare() {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const npm = process.env.npm_execpath;
  if (!npm || !fs.existsSync(npm)) throw Error('Run npm run ci:upgrade:prepare');
  if (!process.env.GITHUB_ENV) throw Error('GITHUB_ENV is required for the following selected-check step');
  const output = fs.realpathSync(fs.mkdtempSync(path.join(process.env.RUNNER_TEMP || os.tmpdir(), 'specreceipt-upgrade-inputs-')));
  const cache = path.join(output, 'cache');
  function run(args) {
    const result = spawnSync(process.execPath, [npm, ...args, '--cache', cache], { cwd: root, encoding: 'utf8', timeout: 180000, maxBuffer: 8 * 1024 * 1024 });
    if (result.status !== 0) throw Error(result.error?.message || result.stderr || result.stdout);
    return result.stdout;
  }
  run(['run', 'build']);
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
  const legacy = JSON.parse(run(['pack', `${BASELINE.name}@${BASELINE.version}`, '--ignore-scripts', '--json', '--pack-destination', output]))[0];
  const current = JSON.parse(run(['pack', '--ignore-scripts', '--json', '--pack-destination', output]))[0];
  const legacyFile = verifyArchive(legacy, output, BASELINE);
  const currentFile = verifyArchive(current, output, pkg);
  const legacyTools = path.join(output, 'legacy-tools');
  // Global prefix layout is understood by the old Windows adapter as well.
  run(['install', '--global', '--prefix', legacyTools, '--ignore-scripts', '--no-audit', '--no-fund', `@fission-ai/openspec@${BASELINE.openspec}`]);
  const legacyCLI = process.platform === 'win32' ? path.join(legacyTools, 'openspec.cmd') : path.join(legacyTools, 'bin/openspec');
  if (!fs.existsSync(legacyCLI)) throw Error('Legacy OpenSpec launcher missing');
  const values = {
    HARNESS_LEGACY_PACKAGE: legacyFile, HARNESS_LEGACY_NAME: BASELINE.name, HARNESS_LEGACY_VERSION: BASELINE.version,
    HARNESS_UPGRADE_PACKAGE: currentFile, HARNESS_LEGACY_OPENSPEC: legacyCLI,
    HARNESS_TEST_LOCAL_DEPS: path.join(root, 'node_modules'), HARNESS_TEST_NPM_CACHE: cache,
    HARNESS_UPGRADE_REPORT: path.join(output, 'report.json'),
  };
  fs.appendFileSync(process.env.GITHUB_ENV, environmentLines(values));
  console.log(`Prepared verified ${BASELINE.name}@${BASELINE.version} → ${pkg.name}@${pkg.version} archives in ${output}`);
  return values;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) prepare();
