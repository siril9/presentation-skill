import { realpath, access, writeFile, stat } from 'node:fs/promises';
import { constants } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const { values } = parseArgs({ options: { root: { type: 'string' }, python: { type: 'string', default: 'python3' } }, strict: true });
if (!values.root) throw new Error('Pass --root with the deck folder you want to expose.');
const root = await realpath(values.root);
if (!(await stat(root)).isDirectory()) throw new Error('--root must be a directory.');
await access(path.join(here, 'dist/preview.html'), constants.R_OK);
const manifest = { mcpServers: { 'presentation-preview': {
  command: process.execPath,
  args: [path.join(here, 'server.mjs'), '--root', root, '--skill-root', path.resolve(here, '../..'), '--python', values.python],
} } };
const output = path.join(here, 'plugin/.mcp.json');
await writeFile(output, JSON.stringify(manifest, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify({ configured: true, deck_root: root, marketplace: here, manifest: output }));
