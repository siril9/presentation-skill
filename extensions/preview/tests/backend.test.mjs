import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createBackend, runPreviewCommand } from '../backend.mjs';

const sha = data => createHash('sha256').update(data).digest('hex');
const jpg = Buffer.from([0xff, 0xd8, 0x11, 0xff, 0xd9]);
async function fixture(t, outline = { title: 'Test', slides: [{ id: 'cover', title: 'Cover', subtitle: 'Old', role_layout_variant: 'primary', body: 'Text' }, { title: 'Second' }] }) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'preview-backend-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const deck = path.join(root, 'group', 'deck');
  await fs.mkdir(deck, { recursive: true });
  const outlinePath = path.join(deck, 'outline.json');
  await fs.writeFile(outlinePath, JSON.stringify(outline) + '\n');
  const backend = createBackend({ root, skillRoot: path.resolve('..', '..', '..'), runner: async () => ({ code: 0, output: '' }) });
  const { revision } = await backend.inspect({ deck_id: 'group/deck' });
  return { root, deck, outlinePath, backend, revision };
}
async function receipt(f, { outlineHash = f.revision, outputHash, reportPath, passed = true, padded = false, malicious = false } = {}) {
  const dir = path.join(f.deck, 'preview-build');
  const qa = path.join(dir, 'qa');
  const renders = path.join(qa, 'renders');
  await fs.mkdir(renders, { recursive: true });
  const output = path.join(dir, 'output.pptx');
  await fs.writeFile(output, 'pptx-test');
  const file = path.join(renders, padded ? 'slide-01.jpg' : 'slide-1.jpg');
  await fs.writeFile(file, jpg);
  await fs.writeFile(path.join(renders, padded ? 'slide-02.jpg' : 'slide-2.jpg'), jpg);
  await fs.writeFile(path.join(qa, 'finalize_receipt.json'), JSON.stringify({ outline: f.outlinePath, output, outline_sha256: outlineHash, output_sha256: outputHash ?? sha('pptx-test'), passed, qa_counts: { warning_count: 0 } }));
  await fs.writeFile(path.join(qa, 'qa_report.json'), JSON.stringify({ render_rc: 0, expected_slide_count: 2, rendered_slide_count: 2 }));
  await fs.writeFile(path.join(renders, 'render_report.json'), JSON.stringify({ status: 'complete', pptx_sha256: sha('pptx-test'), page_count: 2, images: [{ path: reportPath ?? file, sha256: sha(jpg) }, { path: path.join(renders, padded ? 'slide-02.jpg' : 'slide-2.jpg'), sha256: sha(jpg) }], ...(malicious ? { extra: '/etc/passwd' } : {}) }));
  return { output, file, renders };
}

test('lists nested decks with stable ids and raw-byte revision', async t => {
  const f = await fixture(t);
  const { decks: rows } = await f.backend.list();
  assert.equal(rows.length, 1);
  assert.equal(rows[0].deck_id, 'group/deck');
  assert.equal(rows[0].revision, sha(await fs.readFile(f.outlinePath)));
  assert.deepEqual((await f.backend.inspect({ deck_id: 'group/deck' })).slides.map(s => s.slide_id), ['cover', 'slide-2']);
});
test('catalog omits adapter-owned audition outlines while keeping nested source decks', async t => {
  const f = await fixture(t);
  const candidate = path.join(f.deck, 'preview-build', 'audition', 'lab-report');
  const nested = path.join(f.deck, 'real-source');
  await fs.mkdir(candidate, { recursive: true });
  await fs.mkdir(nested);
  await fs.copyFile(f.outlinePath, path.join(f.deck, 'preview-build', 'outline.json'));
  await fs.copyFile(f.outlinePath, path.join(candidate, 'outline.json'));
  await fs.copyFile(f.outlinePath, path.join(nested, 'outline.json'));
  assert.deepEqual((await f.backend.list()).decks.map(d => d.deck_id), ['group/deck', 'group/deck/real-source']);
  await assert.rejects(f.backend.inspect({ deck_id: 'group/deck/preview-build' }), { code: 'INVALID_INPUT' });
});
test('explicit slide_id takes priority over legacy id', async t => {
  const f = await fixture(t, { title: 'X', slides: [{ id: 'legacy', slide_id: 'source-id', title: 'One' }] });
  assert.equal((await f.backend.inspect({ deck_id: 'group/deck' })).slides[0].slide_id, 'source-id');
});
test('rejects traversal and absolute deck ids', async t => {
  const f = await fixture(t);
  for (const deck_id of ['../deck', '/tmp/a', 'group//deck', 'group/../deck', 'group\\deck']) await assert.rejects(f.backend.inspect({ deck_id }));
});
test('does not follow deck symlinks', async t => {
  const f = await fixture(t);
  await fs.symlink(f.deck, path.join(f.root, 'link'));
  assert.equal((await f.backend.list()).decks.length, 1);
  await assert.rejects(f.backend.inspect({ deck_id: 'link' }), /Symlink/);
});
test('CAS rejects stale update, slide and build', async t => {
  const f = await fixture(t);
  for (const call of [() => f.backend.update({ deck_id: 'group/deck', slide_id: 'cover', revision: '0'.repeat(64), changes: { title: 'X' } }), () => f.backend.slide({ deck_id: 'group/deck', slide_id: 'cover', revision: '0'.repeat(64) }), () => f.backend.build({ deck_id: 'group/deck', revision: '0'.repeat(64) })]) await assert.rejects(call(), /Stale revision/);
  await assert.rejects(f.backend.slide({ deck_id: 'group/deck', slide_id: 'cover', revision: '0'.repeat(64) }), { code: 'STALE_REVISION' });
});
test('update preserves unrelated content and invalidates old previews', async t => {
  const f = await fixture(t);
  await fs.chmod(f.outlinePath, 0o640);
  await receipt(f);
  const result = await f.backend.update({ deck_id: 'group/deck', slide_id: 'cover', revision: f.revision, changes: { title: 'New' } });
  const outline = JSON.parse(await fs.readFile(f.outlinePath));
  assert.equal(outline.slides[1].title, 'Second');
  assert.equal(outline.slides[0].subtitle, 'Old');
  assert.equal((await fs.stat(f.outlinePath)).mode & 0o777, 0o640);
  assert.equal((await f.backend.inspect({ deck_id: 'group/deck' })).slides[0].preview_uri, undefined);
  assert.notEqual(result.revision, f.revision);
});
test('update rejects injected fields and nonstring text', async t => {
  const f = await fixture(t);
  for (const changes of [{ id: 'other' }, { assets: { image: '/etc/passwd' } }, { title: { __proto__: null } }, { role_layout_variant: 'evil' }, { body: ['x'] }]) await assert.rejects(f.backend.update({ deck_id: 'group/deck', slide_id: 'cover', revision: f.revision, changes }));
});
test('same-process CAS serializes updates across backend instances', async t => {
  const f = await fixture(t);
  const other = createBackend({ root: f.root, skillRoot: '/skill' });
  const calls = [f.backend, other].map(backend => backend.update({ deck_id: 'group/deck', slide_id: 'cover', revision: f.revision, changes: { title: 'Changed' } }));
  const results = await Promise.allSettled(calls);
  assert.equal(results.filter(r => r.status === 'fulfilled').length, 1);
  assert.equal(results.filter(r => r.status === 'rejected').length, 1);
});
test('fresh receipt exposes image separately and never approves visual review', async t => {
  const f = await fixture(t);
  await receipt(f, { padded: true });
  await fs.writeFile(path.join(f.deck, 'preview-build/qa/repair_packet.json'), JSON.stringify({ outline_path: f.outlinePath, qa_dir: path.join(f.deck, 'preview-build/qa'), repairs: [{ source_pointer: '/slides/0', slide_index: 0, issues: [{ source: 'layout', diagnostic: { severity: 'warning', type: 'overlap', message: 'Check overlap' } }] }] }));
  const info = await f.backend.inspect({ deck_id: 'group/deck' });
  assert.equal(info.qa.state, 'automated_pass');
  assert.equal(info.qa.visual_review, 'pending');
  assert.match(info.slides[0].preview_uri, /^presentation:\/\/deck\//);
  assert.equal(info.slides[0].issues[0].message, 'Check overlap');
  const slide = await f.backend.slide({ deck_id: 'group/deck', slide_id: 'cover', revision: f.revision });
  assert.equal(slide.slide.source.title, 'Cover');
  assert.equal(slide.slide.slide_id, 'cover');
  assert.equal(slide.slide.issues[0].type, 'overlap');
  assert.equal(slide.image.mimeType, 'image/jpeg');
  assert.equal((await f.backend.resource({ deck_id: 'group/deck', revision: f.revision, kind: 'slide', slide_id: 'cover' })).image.data, jpg.toString('base64'));
});
test('stale outline and output hashes suppress previews', async t => {
  const f = await fixture(t);
  await receipt(f, { outlineHash: '0'.repeat(64) });
  assert.equal((await f.backend.inspect({ deck_id: 'group/deck' })).slides[0].preview_uri, undefined);
  await receipt(f, { outputHash: '0'.repeat(64) });
  assert.equal((await f.backend.inspect({ deck_id: 'group/deck' })).qa.state, 'not_built');
});
test('receipt without a complete render never claims automated pass', async t => {
  const f = await fixture(t);
  const { renders } = await receipt(f);
  await fs.rm(path.join(renders, 'render_report.json'));
  const info = await f.backend.inspect({ deck_id: 'group/deck' });
  assert.equal(info.qa.state, 'automated_failed');
  assert.equal(info.slides[0].preview_uri, undefined);
});
test('render report cannot redirect image paths outside fixed render names', async t => {
  const f = await fixture(t);
  await receipt(f, { reportPath: '/etc/passwd' });
  assert.equal((await f.backend.inspect({ deck_id: 'group/deck' })).slides[0].preview_uri, undefined);
  await assert.rejects(f.backend.resource({ deck_id: 'group/deck', revision: f.revision, kind: 'slide', slide_id: 'cover' }));
});
test('build uses fixed argv and contained output', async t => {
  const f = await fixture(t);
  let command;
  const backend = createBackend({ root: f.root, skillRoot: '/skill', python: 'python3', runner: async argv => { command = argv; return { code: 1, output: 'failed' }; } });
  const result = await backend.build({ deck_id: 'group/deck', revision: f.revision });
  assert.deepEqual(command, ['python3', '/skill/scripts/python_runtime.py', '/skill/scripts/finalize_quick_deck.py', '--outline', f.outlinePath, '--output', path.join(f.deck, 'preview-build/output.pptx'), '--qa-dir', path.join(f.deck, 'preview-build/qa'), '--asset-root', f.deck]);
  assert.equal(result.status, 'unverified');
  assert.equal(result.log_hint, 'preview-build/build.log');
  assert.equal(result.log, undefined);
  assert.deepEqual(result.slides.map(s => s.slide_id), ['cover', 'slide-2']);
});
test('no-op build cannot recycle an old passing receipt', async t => {
  const f = await fixture(t);
  await receipt(f);
  const result = await f.backend.build({ deck_id: 'group/deck', revision: f.revision });
  assert.equal(result.status, 'unverified');
  assert.equal(result.qa.state, 'unverified');
});
test('failed rebuild cannot attach earlier render evidence to a fresh receipt', async t => {
  const f = await fixture(t);
  await receipt(f);
  const backend = createBackend({ root: f.root, skillRoot: '/skill', runner: async () => {
    await fs.writeFile(path.join(f.deck, 'preview-build/qa/finalize_receipt.json'), JSON.stringify({
      outline: f.outlinePath, output: path.join(f.deck, 'preview-build/output.pptx'),
      outline_sha256: f.revision, output_sha256: sha('pptx-test'), passed: false,
    }));
    return { code: 1, output: 'Failed before rendering' };
  } });
  const result = await backend.build({ deck_id: 'group/deck', revision: f.revision });
  assert.equal(result.status, 'automated_failed');
  assert.ok(result.slides.every(s => !s.preview_uri && s.issues.length === 0));
  await assert.rejects(backend.resource({ deck_id: 'group/deck', revision: f.revision, kind: 'slide', slide_id: 'cover' }));
});
test('build rejects external and symlinked nested assets before runner', async t => {
  const f = await fixture(t, { title: 'X', slides: [{ title: 'One', assets: { image: '../outside.jpg' } }] });
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: f.revision }));
  await fs.writeFile(path.join(f.deck, 'outside.jpg'), jpg);
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', assets: { image: 'outside.jpg' } }] }));
  const r = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await fs.rm(path.join(f.deck, 'outside.jpg'));
  await fs.symlink('/etc/passwd', path.join(f.deck, 'outside.jpg'));
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: r }), /Symlink/);
});
test('build rejects active Mermaid and linked output tree', async t => {
  const f = await fixture(t, { title: 'X', slides: [{ title: 'One', assets: { mermaid_source: 'flow.mmd' } }] });
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: f.revision }), /Unsupported active field/);
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One' }] }));
  const r = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await fs.mkdir(path.join(f.deck, 'preview-build'), { recursive: true });
  await fs.symlink('/tmp', path.join(f.deck, 'preview-build', 'qa'));
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: r }), /Symlink/);
  await fs.rm(path.join(f.deck, 'preview-build', 'qa'));
  await fs.rm(path.join(f.deck, 'preview-build'), { recursive: true });
  await fs.symlink('/tmp', path.join(f.deck, 'preview-build'));
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: r }), { code: 'UNSAFE_PATH' });
});
test('build audits automatically loaded manifest paths', async t => {
  const f = await fixture(t);
  const staged = path.join(f.deck, 'assets', 'staged');
  await fs.mkdir(staged, { recursive: true });
  await fs.writeFile(path.join(staged, 'staged_manifest.json'), JSON.stringify({ images: [{ path: '/etc/passwd' }] }));
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: f.revision }), /Path outside deck/);
});
test('renderer-active icon, table, background and figure paths never reach runner outside deck', async t => {
  const f = await fixture(t);
  let calls = 0;
  const backend = createBackend({ root: f.root, skillRoot: '/skill', runner: async () => { calls++; return { code: 0, output: '' }; } });
  const vectors = [
    { assets: { icons: ['/etc/hosts'] } },
    { tables: ['/etc/hosts'] },
    { table_groups: ['/etc/hosts'] },
    { assets: { tables: ['/etc/hosts'] } },
    { background_image: '/etc/hosts' },
    { figures: [{ path: '/etc/hosts' }] },
    { assets: { figures: [{ src: '/etc/hosts' }] } },
    { assets: { generated_image: '/etc/hosts' } },
  ];
  for (const active of vectors) {
    await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', ...active }] }));
    const revision = (await backend.inspect({ deck_id: 'group/deck' })).revision;
    await assert.rejects(backend.build({ deck_id: 'group/deck', revision }), { code: 'UNSAFE_PATH' });
  }
  assert.equal(calls, 0);
});
test('local staged aliases, icon slugs and citation URLs remain usable', async t => {
  const f = await fixture(t);
  await fs.mkdir(path.join(f.deck, 'assets'), { recursive: true });
  await fs.writeFile(path.join(f.deck, 'assets/panel.png'), jpg);
  await fs.writeFile(path.join(f.deck, 'assets/icon.png'), jpg);
  await fs.writeFile(path.join(f.deck, 'asset_plan.json'), JSON.stringify({ images: [{ name: 'panel', path: 'assets/panel.png', source_url: 'https://example.org/citation' }] }));
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', source_url: 'https://example.org/study', slides: [{ title: 'One', sources: ['https://example.org/study'], background_image: 'image:panel', assets: { hero_image: 'image:panel', generated_image: 'assets/panel.png', icons: ['fa6:FaMicroscope', 'assets/icon.png'] }, tables: [{ headers: ['A'], rows: [['B']], source_url: 'https://example.org/table' }] }] }));
  const revision = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  assert.equal((await f.backend.build({ deck_id: 'group/deck', revision })).status, 'unverified');
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', assets: { image: 'image:missing' } }] }));
  const missing = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision: missing }), /Unknown staged asset alias/);
});
test('a staged alias cannot resolve to an outside or symlinked file', async t => {
  const f = await fixture(t);
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', assets: { image: 'image:panel' } }] }));
  const revision = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await fs.writeFile(path.join(f.deck, 'asset_plan.json'), JSON.stringify({ images: [{ name: 'panel', path: '/etc/hosts' }] }));
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision }), { code: 'UNSAFE_PATH' });
  await fs.symlink('/etc/hosts', path.join(f.deck, 'linked.png'));
  await fs.writeFile(path.join(f.deck, 'asset_plan.json'), JSON.stringify({ images: [{ name: 'panel', path: 'linked.png' }] }));
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision }), { code: 'UNSAFE_PATH' });
});
test('coerced candidate arrays and generated-image metadata symlinks are rejected', async t => {
  const f = await fixture(t);
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', tables: [['/etc/hosts']] }] }));
  let revision = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision }), /Invalid active asset value/);
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', figures: [{ path: ['/etc/hosts'] }] }] }));
  revision = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision }), /Invalid active asset value/);
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', compliance: { attribution_file: ['/etc/hosts'] }, slides: [{ title: 'One' }] }));
  revision = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision }), /Invalid active asset value/);
  await fs.mkdir(path.join(f.deck, 'assets'), { recursive: true });
  await fs.writeFile(path.join(f.deck, 'assets/generated.png'), jpg);
  await fs.symlink('/etc/hosts', path.join(f.deck, 'assets/generated.png.metadata.json'));
  await fs.writeFile(path.join(f.deck, 'asset_plan.json'), JSON.stringify({ generated_images: [{ name: 'generated', path: 'assets/generated.png' }] }));
  await fs.writeFile(f.outlinePath, JSON.stringify({ title: 'X', slides: [{ title: 'One', assets: { generated_image: 'generated:generated' } }] }));
  revision = (await f.backend.inspect({ deck_id: 'group/deck' })).revision;
  await assert.rejects(f.backend.build({ deck_id: 'group/deck', revision }), { code: 'UNSAFE_PATH' });
});
test('timeout terminates a real descendant process tree', { skip: process.platform === 'win32' }, async t => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'preview-tree-'));
  const heartbeat = path.join(dir, 'heartbeat');
  const pidfile = path.join(dir, 'pid');
  t.after(async () => {
    try { process.kill(Number(await fs.readFile(pidfile, 'utf8')), 'SIGKILL'); } catch {}
    await fs.rm(dir, { recursive: true, force: true });
  });
  const childCode = `const fs=require('fs');fs.writeFileSync(${JSON.stringify(pidfile)},String(process.pid));setInterval(()=>fs.writeFileSync(${JSON.stringify(heartbeat)},String(Date.now())),20)`;
  const parentCode = `require('child_process').spawn(process.execPath,['-e',${JSON.stringify(childCode)}],{stdio:'ignore'});setInterval(()=>{},1000)`;
  const result = await runPreviewCommand([process.execPath, '-e', parentCode], dir, 800);
  assert.equal(result.code, -1);
  const first = await fs.readFile(heartbeat, 'utf8');
  await new Promise(resolve => setTimeout(resolve, 160));
  assert.equal(await fs.readFile(heartbeat, 'utf8'), first);
});
test('audition enforces bounded presets and fixed command', async t => {
  const f = await fixture(t);
  await assert.rejects(f.backend.audition({ deck_id: 'group/deck', revision: f.revision, presets: ['lab-report', '--help'] }), /Invalid presets/);
  let command;
  const backend = createBackend({ root: f.root, skillRoot: '/skill', runner: async argv => { command = argv; return { code: 1, output: '' }; } });
  const result = await backend.audition({ deck_id: 'group/deck', revision: f.revision, presets: ['lab-report', 'editorial-minimal'] });
  assert.deepEqual(command.slice(-3), ['--presets', 'lab-report', 'editorial-minimal']);
  assert.equal(result.candidates[0].preview_uri, undefined);
});
test('forged audition report does not expose candidate URI', async t => {
  const f = await fixture(t);
  const dir = path.join(f.deck, 'preview-build', 'audition');
  const backend = createBackend({ root: f.root, skillRoot: '/skill', runner: async () => {
    await fs.writeFile(path.join(dir, 'report.json'), JSON.stringify({ source_sha256: f.revision, candidates: [{ preset: 'lab-report', automated_checks_passed: true }] }));
    return { code: 0, output: '' };
  } });
  const result = await backend.audition({ deck_id: 'group/deck', revision: f.revision, presets: ['lab-report', 'editorial-minimal'] });
  assert.equal(result.status, 'unverified');
  assert.equal(result.candidates[0].preview_uri, undefined);
});
test('audition resource maps source slide ID to the candidate page', async t => {
  const f = await fixture(t);
  const dir = path.join(f.deck, 'preview-build', 'audition');
  const candidate = path.join(dir, 'lab-report');
  const renders = path.join(candidate, 'qa', 'renders');
  await fs.mkdir(renders, { recursive: true });
  const outline = path.join(candidate, 'outline.json');
  const output = path.join(candidate, 'deck.pptx');
  const second = Buffer.from([0xff, 0xd8, 0x22, 0xff, 0xd9]);
  await fs.writeFile(outline, '{"slides":[{},{}]}');
  await fs.writeFile(output, 'candidate-pptx');
  await fs.writeFile(path.join(renders, 'slide-1.jpg'), jpg);
  await fs.writeFile(path.join(renders, 'slide-2.jpg'), second);
  await fs.writeFile(path.join(dir, 'report.json'), JSON.stringify({ source_sha256: f.revision, source_slide_indices: [0, 1], candidates: [{ preset: 'lab-report', automated_checks_passed: true }] }));
  await fs.writeFile(path.join(candidate, 'qa', 'finalize_receipt.json'), JSON.stringify({ passed: true, outline, output, outline_sha256: sha(await fs.readFile(outline)), output_sha256: sha('candidate-pptx') }));
  await fs.writeFile(path.join(candidate, 'qa', 'qa_report.json'), JSON.stringify({ render_rc: 0, expected_slide_count: 2, rendered_slide_count: 2 }));
  await fs.writeFile(path.join(renders, 'render_report.json'), JSON.stringify({ status: 'complete', pptx_sha256: sha('candidate-pptx'), page_count: 2, images: [{ path: path.join(renders, 'slide-1.jpg'), sha256: sha(jpg) }, { path: path.join(renders, 'slide-2.jpg'), sha256: sha(second) }] }));
  const resource = await f.backend.resource({ deck_id: 'group/deck', revision: f.revision, kind: 'audition', preset: 'lab-report', slide_id: 'slide-2' });
  assert.equal(resource.slide_id, 'slide-2');
  assert.equal(resource.image.data, second.toString('base64'));
  await assert.rejects(f.backend.resource({ deck_id: 'group/deck', revision: f.revision, kind: 'audition', preset: 'lab-report', slide_id: 'not-in-audition' }));
  const backend = createBackend({ root: f.root, skillRoot: '/skill', runner: async () => {
    await fs.writeFile(path.join(dir, 'report.json'), JSON.stringify({ source_sha256: f.revision, source_slide_indices: [0, 1], candidates: [{ preset: 'lab-report', automated_checks_passed: true }] }));
    return { code: 0, output: '' };
  } });
  const result = await backend.audition({ deck_id: 'group/deck', revision: f.revision, presets: ['lab-report', 'editorial-minimal'] });
  assert.equal(result.candidates[0].preview_slide_id, 'cover');
  assert.deepEqual(result.source_slide_indices, [0, 1]);
});
