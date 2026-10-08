import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.dirname(fileURLToPath(import.meta.url));
const output = await build({
  entryPoints: [path.join(root, 'app.mjs')],
  bundle: true,
  write: false,
  format: 'iife',
  platform: 'browser',
  loader: { '.css': 'empty' },
  target: ['es2022'],
  minify: true,
});
const css = await readFile(path.join(root, 'app.css'), 'utf8');
const script = output.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
await mkdir(path.join(root, 'dist'), { recursive: true });
await writeFile(path.join(root, 'dist', 'preview.html'), `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Slide Review</title><style>${css}</style></head><body><main id="app"></main><script>${script}</script></body></html>\n`);
