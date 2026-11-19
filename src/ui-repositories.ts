/** User-local repository bookmarks. No task state or approval capabilities live here. */
import { homedir } from 'node:os';
import { mkdirSync, readdirSync, renameSync, writeFileSync, rmSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import * as path from 'node:path';
import { hash, read, safe } from './filesystem.js';
export const repositoryId = (root: string) => hash(root);
export const uiRegistryDirectory = () => path.resolve(process.env.SPECRECEIPT_UI_HOME ?? path.join(homedir(), '.specreceipt', 'ui'));
export function loadRepositories(directory?: string): { repositories: Map<string, string>; warnings: string[] } {
  const repositories = new Map<string, string>();
  const warnings: string[] = [];
  if (!directory) return { repositories, warnings };
  let names: string[];
  try { names = readdirSync(safe(directory, 'repositories')); }
  catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') return { repositories, warnings }; throw error; }
  for (const name of names.sort()) {
    if (!/^[a-f0-9]{64}\.json$/.test(name)) continue;
    try {
      const item = JSON.parse(read(directory, `repositories/${name}`)!);
      if (item.version !== 1 || typeof item.path !== 'string' || !path.isAbsolute(item.path) || item.path.length > 4096 || name !== repositoryId(item.path) + '.json') throw Error('Invalid bookmark');
      if (repositories.size >= 50) { warnings.push('Only the first 50 repository bookmarks are shown.'); break; }
      repositories.set(repositoryId(item.path), item.path);
    } catch { warnings.push(`Could not read repository bookmark ${name}.`); }
  }
  return { repositories, warnings };
}
export function saveRepository(directory: string | undefined, root: string) {
  const id = repositoryId(root);
  if (directory) {
    const file = safe(directory, `repositories/${id}.json`);
    const temporary = safe(directory, `repositories/${id}-${randomUUID()}.tmp`);
    mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    try {
      writeFileSync(temporary, JSON.stringify({ version: 1, path: root }) + '\n', { flag: 'wx', mode: 0o600 });
      renameSync(temporary, file);
    } finally { rmSync(temporary, { force: true }); }
  }
  return { id, path: root, name: path.basename(root) };
}
