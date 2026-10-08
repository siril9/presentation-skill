// Development-only verification against a copied synthetic deck, never a user's original.
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';

const here = path.dirname(fileURLToPath(import.meta.url));
const { values } = parseArgs({ options: { root: { type: 'string' }, deck: { type: 'string' }, outdir: { type: 'string' } }, strict: true });
if (!values.root || !values.deck || !values.outdir) throw new Error('Pass --root, --deck and --outdir for a disposable synthetic copy.');
const root = path.resolve(values.root);
const outdir = path.resolve(values.outdir);
await mkdir(outdir, { recursive: true });
const original = JSON.parse(await readFile(path.join(root, values.deck, 'outline.json'), 'utf8'));
const transport = new StdioClientTransport({ command: process.execPath, args: [path.resolve(here, '../server.mjs'), '--root', root], stderr: 'pipe' });
const client = new Client({ name: 'presentation-preview-e2e', version: '1.0.0' });
const operations = [];
async function call(name, args, allowError = false) {
  const start = performance.now();
  const result = await client.callTool({ name, arguments: args }, undefined, { timeout: 240_000 });
  operations.push({ name, elapsed_ms: Math.round(performance.now() - start), isError: result.isError === true });
  if (!allowError) assert.notEqual(result.isError, true, JSON.stringify(result.content));
  return result;
}
try {
  await client.connect(transport);
  const tools = (await client.listTools()).tools;
  assert.equal(tools.length, 6);
  const catalog = await call('presentation_open', {});
  assert.ok(catalog.structuredContent.decks.some(d => d.deck_id === values.deck));
  const open = await call('presentation_open', { deck_id: values.deck });
  const revision = open.structuredContent.revision;
  const build = await call('presentation_build', { deck_id: values.deck, revision });
  assert.equal(build.structuredContent.qa.state, 'automated_pass');
  assert.equal(build.structuredContent.qa.visual_review, 'pending');
  const selected = open.structuredContent.slides.at(-1).slide_id;
  const revisedTitle = original.slides.at(-1).title === 'Extend only after the pilot earns it'
    ? 'Extend only after measured demand earns it' : 'Extend only after the pilot earns it';
  const updated = await call('presentation_update_slide', {
    deck_id: values.deck, slide_id: selected, revision,
    changes: { title: revisedTitle },
  });
  assert.notEqual(updated.structuredContent.revision, revision);
  const stale = await call('presentation_update_slide', { deck_id: values.deck, slide_id: selected, revision, changes: { title: 'Stale overwrite' } }, true);
  assert.equal(stale.isError, true);
  const fresh = await call('presentation_open', { deck_id: values.deck });
  assert.ok(fresh.structuredContent.slides.every(s => !s.preview_uri));
  const next = fresh.structuredContent.revision;
  const rebuilt = await call('presentation_build', { deck_id: values.deck, revision: next });
  assert.equal(rebuilt.structuredContent.qa.state, 'automated_pass');
  const final = await call('presentation_open', { deck_id: values.deck });
  const source = JSON.parse(await readFile(path.join(root, values.deck, 'outline.json'), 'utf8'));
  assert.deepEqual(source.slides.slice(0, -1), original.slides.slice(0, -1));
  const slideResults = {};
  for (const slide of final.structuredContent.slides) {
    const response = await call('presentation_slide', { deck_id: values.deck, slide_id: slide.slide_id, revision: next });
    assert.equal(response.structuredContent.slide.source.title, slide.title);
    assert.equal(response._meta.preview.mimeType, 'image/jpeg');
    assert.equal(response.structuredContent.image, undefined);
    slideResults[slide.slide_id] = response;
  }
  const audition = await call('presentation_audition', { deck_id: values.deck, revision: next, presets: ['lab-report', 'editorial-minimal', 'warm-terracotta'] });
  assert.equal(audition.structuredContent.status, 'rendered');
  const candidateResults = {};
  for (const candidate of audition.structuredContent.candidates) {
    assert.ok(candidate.preview_uri);
    const slide_id = candidate.preview_slide_id || final.structuredContent.slides[0].slide_id;
    const response = await call('presentation_preview', { deck_id: values.deck, revision: next, slide_id, preset: candidate.preset });
    assert.ok(response._meta.preview.data);
    candidateResults[candidate.preset] = response;
  }
  const repeated = await call('presentation_audition', { deck_id: values.deck, revision: next, presets: ['lab-report', 'editorial-minimal', 'warm-terracotta'] });
  assert.equal(repeated.structuredContent.status, 'rendered', 'Identical deterministic reports must remain usable after a fresh run');
  for (const candidate of repeated.structuredContent.candidates) {
    const response = await call('presentation_preview', { deck_id: values.deck, revision: next, slide_id: candidate.preview_slide_id, preset: candidate.preset });
    assert.equal(response._meta.preview.data, candidateResults[candidate.preset]._meta.preview.data, 'Identical styles must reproduce identical rendered pixels');
  }
  await writeFile(path.join(outdir, 'browser-fixture.json'), JSON.stringify({ initialResult: final, slideResults, audition, candidateResults }));
  const report = { passed: true, transport: 'real MCP stdio', tools: tools.map(t => t.name), operations, slide_count: final.structuredContent.slides.length, visual_review: 'pending', unchanged_other_slides: true, stale_edit_rejected: true, stale_previews_hidden: true, repeated_audition_pixels_identical: true };
  await writeFile(path.join(outdir, 'e2e-report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally { await client.close(); await transport.close(); }
