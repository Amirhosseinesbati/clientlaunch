/** Repair moved pnpm junctions using only this project's existing package files. No installs or downloads. */
import { existsSync, lstatSync, readdirSync, readlinkSync, rmdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { join, relative, resolve, sep } from 'node:path';

const root = resolve(import.meta.dirname, '../apps/web/node_modules');
const apply = process.argv.includes('--apply');
const repairs = [];
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    const stat = lstatSync(path);
    if (stat.isSymbolicLink()) {
      if (existsSync(path)) continue;
      const before = readlinkSync(path);
      const marker = `${sep}node_modules${sep}`;
      const index = before.indexOf(marker);
      if (index < 0) continue;
      const after = resolve(root, before.slice(index + marker.length));
      if (!after.startsWith(root + sep) || !existsSync(after)) continue;
      repairs.push({ path: relative(root, path), before, after });
      // rmdir removes the junction itself on Windows. No recursive deletion is used.
      if (apply) { rmdirSync(path); symlinkSync(after, path, 'junction'); }
    } else if (stat.isDirectory()) walk(path);
  }
}
walk(root);
if (apply && repairs.length) writeFileSync(resolve(import.meta.dirname, '../.runtime/dependency-link-repairs.json'), JSON.stringify(repairs, null, 2));
console.log(`${apply ? 'Repaired' : 'Repairable'} ${repairs.length} project-local dependency junctions. No package data changed.`);
