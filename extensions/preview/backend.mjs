import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';

const MAX_OUTLINE = 2_000_000;
const MAX_JSON = 500_000;
const MAX_IMAGE = 8_000_000;
const PRESETS = new Set(['executive-clinical', 'editorial-minimal', 'lab-report', 'warm-terracotta', 'arctic-minimal', 'sunset-investor', 'data-heavy-boardroom', 'forest-research', 'paper-journal', 'charcoal-safety', 'lavender-ops', 'midnight-neon', 'bold-startup-narrative']);
const EDITABLE = new Set(['title', 'subtitle', 'role_layout_variant', 'body']);
const ALIAS_SECTIONS = {
  images: ['asset', 'image'], backgrounds: ['asset', 'background'],
  charts: ['asset', 'chart'], tables: ['asset', 'table'],
  generated_images: ['asset', 'image', 'generated'],
};
const ALIAS_REF = /^(asset|image|background|chart|table|generated):([a-z0-9_-]+)$/i;
const ICON_SLUG = /^(fa6|fa|bi|bs|md|lu):[A-Z][A-Za-z0-9]{0,79}$/;
const HASH = /^[a-f0-9]{64}$/;
const LOCKS = new Map();

export class PreviewError extends Error {
  constructor(code, message) { super(message); this.name = 'PreviewError'; this.code = code; }
}
function fail(message) {
  const code = /Stale revision/.test(message) ? 'STALE_REVISION'
    : /Symlink|outside deck|Unsafe asset path|output tree/.test(message) ? 'UNSAFE_PATH'
    : /not found|unavailable|missing/.test(message) ? 'NOT_FOUND'
    : /Unsupported active field/.test(message) ? 'UNSAFE_INPUT'
    : 'INVALID_INPUT';
  throw new PreviewError(code, message);
}
function hash(bytes) { return createHash('sha256').update(bytes).digest('hex'); }
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function within(base, target) { return target === base || target.startsWith(base + path.sep); }
function deckParts(id) {
  if (typeof id !== 'string' || id.length > 160 || !id || id.includes('\\') || id.includes('\0')) fail('Invalid deck_id');
  const parts = id.split('/');
  if (parts.length > 4 || parts.some(p => !p || p === '.' || p === '..' || p === 'preview-build' || !/^[\w. -]{1,80}$/.test(p))) fail('Invalid deck_id');
  return parts;
}
function slideId(slide, index) {
  const id = slide.slide_id ?? slide.id ?? `slide-${index + 1}`;
  if (typeof id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(id)) fail('Invalid slide ID');
  return id;
}
function uri(deckId, revision, kind, name) {
  return `presentation://deck/${encodeURIComponent(deckId)}/${revision}/${kind}/${encodeURIComponent(name)}`;
}
async function noLinks(base, target, { allowMissing = false } = {}) {
  if (!within(base, target)) fail('Path outside deck');
  let cursor = base;
  for (const part of path.relative(base, target).split(path.sep).filter(Boolean)) {
    cursor = path.join(cursor, part);
    try { if ((await fs.lstat(cursor)).isSymbolicLink()) fail('Symlink is forbidden'); }
    catch (error) { if (error.code === 'ENOENT' && allowMissing) continue; throw error; }
  }
}
async function cleanOutputTree(dir, budget = { count: 0 }) {
  let entries;
  try { entries = await fs.readdir(dir, { withFileTypes: true }); }
  catch (error) { if (error.code === 'ENOENT') return; throw error; }
  for (const entry of entries) {
    if (++budget.count > 3000) fail('Preview output tree too large');
    if (entry.isSymbolicLink()) fail('Symlink in preview output tree');
    if (entry.isDirectory()) await cleanOutputTree(path.join(dir, entry.name), budget);
  }
}
async function readLimited(file, limit) {
  const stat = await fs.stat(file);
  if (!stat.isFile() || stat.size > limit) fail('File missing or too large');
  return fs.readFile(file);
}
function parse(bytes) {
  const data = JSON.parse(bytes.toString('utf8'));
  const walk = (value, depth = 0) => {
    if (depth > 40) fail('JSON too deep');
    if (typeof value === 'number' && !Number.isFinite(value)) fail('Nonfinite JSON number');
    if (typeof value === 'string' && value.length > 100_000) fail('JSON string too large');
    if (Array.isArray(value)) { if (value.length > 2000) fail('JSON array too large'); value.forEach(v => walk(v, depth + 1)); }
    else if (object(value)) {
      if (Object.keys(value).length > 500) fail('JSON object too large');
      for (const [key, child] of Object.entries(value)) {
        if (['__proto__', 'prototype', 'constructor'].includes(key)) fail('Unsafe JSON key');
        walk(child, depth + 1);
      }
    }
  };
  walk(data);
  return data;
}
function validateOutline(data) {
  if (!object(data) || !Array.isArray(data.slides) || !data.slides.length || data.slides.length > 100) fail('Invalid outline slides');
  const ids = data.slides.map((s, i) => {
    if (!object(s) || typeof s.title !== 'string') fail('Invalid slide');
    return slideId(s, i);
  });
  if (new Set(ids).size !== ids.length) fail('Duplicate slide ID');
  return ids;
}
async function safeInputs(deck, data) {
  const aliases = new Map();
  const local = async (raw, { icon = false } = {}) => {
    if (typeof raw !== 'string' || !raw.trim() || raw.includes('\0') || raw.includes('\\')) fail('Unsafe asset path');
    if (icon && ICON_SLUG.test(raw.trim())) return;
    const match = ALIAS_REF.exec(raw.trim());
    if (match && !icon) {
      const target = aliases.get(raw.trim().toLowerCase());
      if (!target) fail('Unknown staged asset alias');
      raw = target;
    } else if (/^(?:[a-z]+:|\/\/)/i.test(raw)) fail('Unsafe asset path');
    let target = path.resolve(deck, raw);
    if (icon && !/\.(?:png|jpg|jpeg|svg)$/i.test(target)) target += '.png';
    await noLinks(deck, target);
    if (!within(deck, target) || !(await fs.stat(target)).isFile()) fail('Asset outside deck or missing');
  };
  // Match stagedAssetLookup's source priority and alias normalization in the renderer.
  for (const relative of ['asset_plan.json', 'assets/staged/staged_manifest.json']) {
    const file = path.join(deck, relative);
    await noLinks(deck, file, { allowMissing: true });
    let manifest;
    try { manifest = parse(await readLimited(file, MAX_JSON)); }
    catch (error) { if (error.code === 'ENOENT') continue; throw error; }
    if (!object(manifest)) fail('Invalid asset manifest');
    for (const [section, prefixes] of Object.entries(ALIAS_SECTIONS)) {
      const entries = manifest[section];
      if (entries === undefined) continue;
      if (!Array.isArray(entries) || entries.length > 500) fail('Invalid asset manifest');
      for (const entry of entries) {
        if (!object(entry)) fail('Invalid asset manifest entry');
        const raw = entry.path || entry.file_path || entry.output_path || entry.image_path;
        if (raw !== undefined) await local(raw);
        const name = String(entry.name ?? '').replace(/[^A-Za-z0-9_-]/g, '_').replace(/^_+|_+$/g, '').toLowerCase();
        if (name && raw) for (const prefix of prefixes) aliases.set(`${prefix}:${name}`, raw);
      }
    }
  }
  const checkSpec = async (value, fields) => {
    if (typeof value === 'string') { await local(value); return; }
    if (Array.isArray(value)) fail('Invalid active asset value');
    if (!object(value)) return;
    for (const key of fields) {
      if (value[key] === undefined || value[key] === null || value[key] === '') continue;
      if (typeof value[key] !== 'string') fail('Invalid active asset value');
      await local(value[key]);
    }
  };
  const checkArray = async (values, fields) => {
    if (!Array.isArray(values)) return;
    for (const value of values) await checkSpec(value, fields);
  };
  for (const slide of data.slides) {
    const assets = object(slide.assets) ? slide.assets : {};
    for (const source of [slide, assets]) {
      if (source.mermaid || source.mermaid_source || source.rawdata || source.data_uri) fail('Unsupported active field');
      for (const key of ['script', 'command', 'include']) if (source[key]) fail('Unsupported active field');
    }
    for (const value of [slide.background_image, assets.hero_image, assets.image, assets.generated_image, assets.diagram,
      slide.chart, assets.chart_data, assets.chart, slide.table, slide.table_data, assets.table_data, assets.table]) {
      await checkSpec(value, ['path', 'file_path', 'output_path', 'image_path']);
    }
    for (const values of [slide.tables, slide.table_groups, assets.tables]) await checkArray(values, ['path', 'file_path', 'output_path', 'image_path']);
    for (const values of [slide.figures, assets.figures]) await checkArray(values, ['path', 'image', 'src', 'asset']);
    if (Array.isArray(assets.icons)) for (const icon of assets.icons) await local(icon, { icon: true });
  }
  if (data.compliance?.attribution_file) {
    if (typeof data.compliance.attribution_file !== 'string') fail('Invalid active asset value');
    await local(data.compliance.attribution_file);
  }
  const attribution = path.join(deck, 'assets/attribution.csv');
  await noLinks(deck, attribution, { allowMissing: true });
  // Generated-image rendering reads adjacent metadata JSON when present.
  for (const slide of data.slides) {
    const generated = slide.assets?.generated_image;
    if (typeof generated !== 'string') continue;
    const resolved = ALIAS_REF.test(generated) ? aliases.get(generated.toLowerCase()) : generated;
    if (!resolved) fail('Unknown staged asset alias');
    const metadata = path.resolve(deck, `${resolved}.metadata.json`);
    await noLinks(deck, metadata, { allowMissing: true });
  }
}
function killTree(child) {
  if (!Number.isSafeInteger(child.pid) || child.pid <= 0) return Promise.resolve(false);
  if (process.platform !== 'win32') {
    try { process.kill(-child.pid, 'SIGKILL'); return Promise.resolve(true); }
    catch (error) { return Promise.resolve(error.code === 'ESRCH'); }
  }
  return new Promise(resolve => {
    const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { shell: false, stdio: 'ignore', windowsHide: true });
    const timer = setTimeout(() => { killer.kill('SIGKILL'); resolve(false); }, 5000);
    killer.on('error', () => { clearTimeout(timer); resolve(false); });
    killer.on('close', code => { clearTimeout(timer); resolve(code === 0); });
  });
}
export function runPreviewCommand(argv, cwd, timeout = 180_000) {
  return new Promise((resolve, reject) => {
    const child = spawn(argv[0], argv.slice(1), { cwd, shell: false, detached: process.platform !== 'win32', windowsHide: true, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    let outputBytes = 0;
    let exceeded = false;
    let stopping;
    let watchdog;
    let settled = false;
    const finish = (error, result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(watchdog);
      if (error) reject(error); else resolve(result);
    };
    const stop = () => {
      exceeded = true;
      if (stopping) return;
      stopping = killTree(child);
      stopping.then(ok => {
        if (!ok) {
          child.kill('SIGKILL');
          child.stdout.destroy(); child.stderr.destroy();
          finish(new PreviewError('TERMINATION_FAILED', 'Process tree termination failed'));
        }
      });
      watchdog = setTimeout(() => {
        child.stdout.destroy(); child.stderr.destroy();
        finish(new PreviewError('TERMINATION_FAILED', 'Process tree did not close'));
      }, 6000);
    };
    const timer = setTimeout(stop, timeout);
    for (const stream of [child.stdout, child.stderr]) stream.on('data', bytes => {
      outputBytes += bytes.length;
      output = (output + bytes.toString('utf8')).slice(0, 32_000);
      if (outputBytes > 32_000) stop();
    });
    child.on('error', error => finish(error));
    child.on('close', async code => {
      if (stopping && !await stopping) return finish(new PreviewError('TERMINATION_FAILED', 'Process tree termination failed'));
      finish(null, { code: exceeded ? -1 : code, output });
    });
  });
}

export function createBackend({ root, skillRoot, python = 'python3', runner = runPreviewCommand }) {
  if (!path.isAbsolute(root) || !path.isAbsolute(skillRoot) || typeof python !== 'string' || !python) fail('Absolute root and skillRoot required');
  const base = path.resolve(root);
  const skill = path.resolve(skillRoot);
  const locked = (id, action) => {
    const key = path.join(base, ...deckParts(id));
    const prior = LOCKS.get(key) ?? Promise.resolve();
    const next = prior.catch(() => {}).then(action);
    LOCKS.set(key, next);
    next.finally(() => { if (LOCKS.get(key) === next) LOCKS.delete(key); }).catch(() => {});
    return next;
  };
  async function load(id) {
    const deck = path.join(base, ...deckParts(id));
    await noLinks(base, deck);
    if (!(await fs.stat(deck)).isDirectory()) fail('Deck not found');
    const outline = path.join(deck, 'outline.json');
    await noLinks(deck, outline);
    const bytes = await readLimited(outline, MAX_OUTLINE);
    const data = parse(bytes);
    const ids = validateOutline(data);
    return { deck, outline, bytes, data, ids, revision: hash(bytes) };
  }
  function cas(current, expected) { if (!HASH.test(expected ?? '') || expected !== current) fail('Stale revision'); }
  function select(ctx, id) {
    const index = ctx.ids.indexOf(id);
    if (index < 0) fail('Slide not found');
    return { index, source: ctx.data.slides[index] };
  }
  async function jsonFile(ctx, relative) {
    const file = path.join(ctx.deck, relative);
    await noLinks(ctx.deck, file, { allowMissing: true });
    try { return parse(await readLimited(file, MAX_JSON)); }
    catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  }
  async function saveLog(ctx, name, output) {
    const relative = `preview-build/${name}.log`;
    const file = path.join(ctx.deck, relative);
    await noLinks(ctx.deck, file, { allowMissing: true });
    await fs.writeFile(file, String(output ?? '').slice(0, 32_000), { mode: 0o600 });
    return relative;
  }
  async function priorHash(ctx, relative) {
    const file = path.join(ctx.deck, relative);
    await noLinks(ctx.deck, file, { allowMissing: true });
    try { return hash(await readLimited(file, MAX_JSON)); }
    catch (error) { if (error.code === 'ENOENT') return null; throw error; }
  }
  async function freshBuild(ctx) {
    const dir = path.join(ctx.deck, 'preview-build');
    const output = path.join(dir, 'output.pptx');
    const receipt = await jsonFile(ctx, 'preview-build/qa/finalize_receipt.json');
    if (!receipt || receipt.outline_sha256 !== ctx.revision || receipt.output !== output || receipt.outline !== ctx.outline) return null;
    await noLinks(ctx.deck, output, { allowMissing: true });
    let bytes;
    try { bytes = await readLimited(output, 100_000_000); } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
    if (hash(bytes) !== receipt.output_sha256) return null;
    const render = await jsonFile(ctx, 'preview-build/qa/renders/render_report.json');
    const qa = await jsonFile(ctx, 'preview-build/qa/qa_report.json');
    const rendered = render?.status === 'complete' && render.pptx_sha256 === receipt.output_sha256 && render.page_count === ctx.ids.length && render.images?.length === ctx.ids.length && qa?.render_rc === 0 && qa.expected_slide_count === ctx.ids.length && qa.rendered_slide_count === ctx.ids.length;
    return { receipt, render: rendered ? render : null, qa };
  }
  async function imageAt(ctx, file, expectedHash) {
    await noLinks(ctx.deck, file);
    const bytes = await readLimited(file, MAX_IMAGE);
    if (expectedHash && hash(bytes) !== expectedHash) fail('Image hash mismatch');
    const jpg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes.at(-2) === 0xff && bytes.at(-1) === 0xd9;
    const png = bytes.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
    if (!jpg && !png) fail('Invalid image');
    return { data: bytes.toString('base64'), mimeType: jpg ? 'image/jpeg' : 'image/png' };
  }
  async function buildImage(ctx, slideIdValue, fresh = null) {
    if (!fresh) fresh = await freshBuild(ctx);
    if (!fresh?.render) return null;
    const { index } = select(ctx, slideIdValue);
    const entry = fresh.render.images?.[index];
    const renderDir = path.join(ctx.deck, 'preview-build', 'qa', 'renders');
    const allowed = [`slide-${index + 1}.jpg`, `slide-${String(index + 1).padStart(2, '0')}.jpg`];
    if (!entry || !allowed.some(name => entry.path === path.join(renderDir, name)) || !HASH.test(entry.sha256 ?? '')) return null;
    return { file: entry.path, sha256: entry.sha256 };
  }
  async function slideIssues(ctx, fresh, index) {
    if (!fresh) return [];
    const packet = await jsonFile(ctx, 'preview-build/qa/repair_packet.json');
    if (packet?.outline_path !== ctx.outline || packet?.qa_dir !== path.join(ctx.deck, 'preview-build', 'qa') || !Array.isArray(packet.repairs)) return [];
    const repair = packet.repairs.find(item => item?.source_pointer === `/slides/${index}` && item.slide_index === index);
    if (!Array.isArray(repair?.issues)) return [];
    return repair.issues.slice(0, 20).map(item => ({
      source: String(item?.source ?? '').slice(0, 80),
      severity: String(item?.diagnostic?.severity ?? '').slice(0, 30),
      type: String(item?.diagnostic?.type ?? '').slice(0, 80),
      message: String(item?.diagnostic?.message ?? item?.instruction ?? '').slice(0, 500),
    }));
  }
  async function candidateImage(ctx, preset, report, requestedSlideId) {
    if (report?.source_sha256 !== ctx.revision || !report.candidates?.some(c => c.preset === preset && c.automated_checks_passed === true)) return null;
    const indices = report.source_slide_indices;
    if (!Array.isArray(indices) || !indices.length || indices.length > 3 || indices.some(i => !Number.isInteger(i) || i < 0 || i >= ctx.ids.length) || new Set(indices).size !== indices.length) return null;
    const page = requestedSlideId === undefined ? 0 : indices.indexOf(ctx.ids.indexOf(requestedSlideId));
    if (page < 0) return null;
    const candidate = path.join(ctx.deck, 'preview-build', 'audition', preset);
    const receipt = await jsonFile(ctx, `preview-build/audition/${preset}/qa/finalize_receipt.json`);
    const output = path.join(candidate, 'deck.pptx');
    const outline = path.join(candidate, 'outline.json');
    await noLinks(ctx.deck, output, { allowMissing: true });
    await noLinks(ctx.deck, outline, { allowMissing: true });
    if (!receipt || receipt.passed !== true || receipt.outline !== outline || receipt.output !== output) return null;
    try {
      if (hash(await readLimited(outline, MAX_OUTLINE)) !== receipt.outline_sha256 || hash(await readLimited(output, 100_000_000)) !== receipt.output_sha256) return null;
    } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
    const render = await jsonFile(ctx, `preview-build/audition/${preset}/qa/renders/render_report.json`);
    const qa = await jsonFile(ctx, `preview-build/audition/${preset}/qa/qa_report.json`);
    if (render?.status !== 'complete' || render.pptx_sha256 !== receipt.output_sha256 || render.page_count !== indices.length || render.images?.length !== indices.length || qa?.render_rc !== 0 || qa.expected_slide_count !== indices.length || qa.rendered_slide_count !== indices.length) return null;
    const entry = render.images[page];
    const renderDir = path.join(candidate, 'qa', 'renders');
    if (!entry || ![`slide-${page + 1}.jpg`, `slide-${String(page + 1).padStart(2, '0')}.jpg`].some(name => entry.path === path.join(renderDir, name)) || !HASH.test(entry.sha256 ?? '')) return null;
    return { file: entry.path, sha256: entry.sha256, slide_id: ctx.ids[indices[page]] };
  }
  async function list() {
    const found = [];
    let visited = 0;
    async function visit(dir, parts) {
      if (found.length >= 200 || visited >= 2000 || parts.length > 4) return;
      for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
        if (found.length >= 200 || visited >= 2000) break;
        if (entry.isSymbolicLink() || !entry.isDirectory() || entry.name === 'preview-build' || !/^[\w. -]{1,80}$/.test(entry.name)) continue;
        visited++;
        const next = [...parts, entry.name];
        const sub = path.join(dir, entry.name);
        if (next.length <= 4) {
          try { const ctx = await load(next.join('/')); found.push({ deck_id: next.join('/'), title: ctx.data.title ?? '', revision: ctx.revision }); }
          catch (error) { if (error.code !== 'ENOENT') { /* malformed or inaccessible decks are omitted */ } }
          await visit(sub, next);
        }
      }
    }
    await visit(base, []);
    return { decks: found };
  }
  async function inspect({ deck_id }) {
    const ctx = await load(deck_id);
    const fresh = await freshBuild(ctx);
    const slides = await Promise.all(ctx.data.slides.map(async (s, index) => {
      const id = ctx.ids[index];
      return { slide_id: id, index, title: s.title, variant: s.variant ?? s.type ?? '', preview_uri: await buildImage(ctx, id, fresh) ? uri(deck_id, ctx.revision, 'slides', id) : undefined, issues: await slideIssues(ctx, fresh, index) };
    }));
    return { deck_id, title: ctx.data.title ?? '', revision: ctx.revision, slides, qa: { state: fresh ? (fresh.receipt.passed === true && fresh.render ? 'automated_pass' : 'automated_failed') : 'not_built', visual_review: 'pending', counts: fresh?.receipt.qa_counts ?? {} } };
  }
  async function slide({ deck_id, slide_id, revision }) {
    const ctx = await load(deck_id); cas(ctx.revision, revision);
    const { index, source } = select(ctx, slide_id);
    const fresh = await freshBuild(ctx);
    const ref = await buildImage(ctx, slide_id, fresh);
    return { deck_id, revision, slide: { slide_id, index, title: source.title, variant: source.variant ?? source.type ?? '', source, issues: await slideIssues(ctx, fresh, index), preview_uri: ref ? uri(deck_id, revision, 'slides', slide_id) : undefined }, image: ref ? await imageAt(ctx, ref.file, ref.sha256) : undefined };
  }
  async function update({ deck_id, slide_id, revision, changes }) {
    return locked(deck_id, async () => {
      const ctx = await load(deck_id); cas(ctx.revision, revision);
      if (!object(changes) || !Object.keys(changes).length || Object.keys(changes).some(k => !EDITABLE.has(k))) fail('Unsupported changes');
      const { index, source } = select(ctx, slide_id);
      const next = structuredClone(ctx.data);
      for (const [key, value] of Object.entries(changes)) {
        if (!(key in source)) fail('Only existing slide fields are editable');
        if (key === 'role_layout_variant') {
          if (!['primary', 'alternate', 'dense'].includes(value)) fail('Invalid layout variant');
        } else if (typeof value !== 'string' || value.length > 10_000) fail('Invalid text change');
        next.slides[index][key] = value;
      }
      const bytes = Buffer.from(JSON.stringify(next, null, 2) + '\n');
      if (bytes.length > MAX_OUTLINE) fail('Outline too large');
      validateOutline(parse(bytes));
      const temp = path.join(ctx.deck, `.outline-preview-${process.pid}-${Date.now()}.tmp`);
      await noLinks(ctx.deck, temp, { allowMissing: true });
      const mode = (await fs.stat(ctx.outline)).mode & 0o777;
      try {
        await fs.writeFile(temp, bytes, { flag: 'wx', mode: 0o600 });
        await fs.chmod(temp, mode);
        await noLinks(ctx.deck, ctx.outline);
        cas(hash(await readLimited(ctx.outline, MAX_OUTLINE)), revision);
        await fs.rename(temp, ctx.outline);
      }
      finally { await fs.rm(temp, { force: true }); }
      return { deck_id, slide_id, revision: hash(bytes), qa: { state: 'not_built', visual_review: 'pending' } };
    });
  }
  async function build({ deck_id, revision }) {
    return locked(deck_id, async () => {
      const ctx = await load(deck_id); cas(ctx.revision, revision); await safeInputs(ctx.deck, ctx.data);
      const dir = path.join(ctx.deck, 'preview-build');
      await noLinks(ctx.deck, dir, { allowMissing: true });
      await cleanOutputTree(dir);
      await noLinks(ctx.deck, path.join(dir, 'qa', 'renders'), { allowMissing: true });
      await noLinks(ctx.deck, path.join(dir, 'output.pptx'), { allowMissing: true });
      await fs.mkdir(dir, { recursive: true });
      const receiptPath = 'preview-build/qa/finalize_receipt.json';
      // A failed run must not pair its receipt with evidence from an earlier build.
      for (const relative of [receiptPath, 'preview-build/qa/renders/render_report.json', 'preview-build/qa/qa_report.json', 'preview-build/qa/repair_packet.json']) {
        const file = path.join(ctx.deck, relative);
        await noLinks(ctx.deck, file, { allowMissing: true });
        await fs.rm(file, { force: true });
      }
      const result = await runner([python, path.join(skill, 'scripts/python_runtime.py'), path.join(skill, 'scripts/finalize_quick_deck.py'), '--outline', ctx.outline, '--output', path.join(dir, 'output.pptx'), '--qa-dir', path.join(dir, 'qa'), '--asset-root', ctx.deck], skill, 180_000);
      const log_hint = await saveLog(ctx, 'build', result.output);
      const current = await load(deck_id); cas(current.revision, revision);
      const fresh = await freshBuild(current);
      const details = await inspect({ deck_id }); cas(details.revision, revision);
      const newReceiptHash = await priorHash(current, receiptPath);
      const changed = newReceiptHash !== null;
      const status = changed && fresh ? (fresh.receipt.passed === true && fresh.render && result.code === 0 ? 'automated_pass' : 'automated_failed') : 'unverified';
      return { ...details, qa: { ...details.qa, state: status }, status, exit_code: result.code, log_hint };
    });
  }
  async function audition({ deck_id, revision, presets }) {
    return locked(deck_id, async () => {
      const ctx = await load(deck_id); cas(ctx.revision, revision); await safeInputs(ctx.deck, ctx.data);
      if (!Array.isArray(presets) || presets.length < 2 || presets.length > 3 || new Set(presets).size !== presets.length || presets.some(p => !PRESETS.has(p))) fail('Invalid presets');
      const dir = path.join(ctx.deck, 'preview-build', 'audition');
      await noLinks(ctx.deck, path.join(ctx.deck, 'preview-build'), { allowMissing: true });
      await cleanOutputTree(path.join(ctx.deck, 'preview-build'));
      await noLinks(ctx.deck, dir, { allowMissing: true });
      await fs.mkdir(dir, { recursive: true });
      const reportPath = 'preview-build/audition/report.json';
      await noLinks(ctx.deck, path.join(ctx.deck, reportPath), { allowMissing: true });
      await fs.rm(path.join(ctx.deck, reportPath), { force: true });
      const result = await runner([python, path.join(skill, 'scripts/python_runtime.py'), path.join(skill, 'scripts/audition_styles.py'), '--outline', ctx.outline, '--outdir', dir, '--presets', ...presets], skill, 180_000);
      const log_hint = await saveLog(ctx, 'audition', result.output);
      const current = await load(deck_id); cas(current.revision, revision);
      const report = await jsonFile(current, 'preview-build/audition/report.json');
      const newReportHash = await priorHash(current, reportPath);
      const valid = newReportHash !== null && report?.source_sha256 === revision && Array.isArray(report.candidates);
      const candidates = await Promise.all(presets.map(async preset => {
        const ref = valid ? await candidateImage(current, preset, report) : null;
        return { preset, preview_slide_id: ref?.slide_id, preview_uri: ref ? uri(deck_id, revision, 'audition', `${preset}/${ref.slide_id}`) : undefined };
      }));
      return { deck_id, revision, source_slide_indices: valid ? report.source_slide_indices : [], candidates, status: result.code === 0 && candidates.every(c => c.preview_uri) ? 'rendered' : 'unverified', visual_review: 'pending', log_hint };
    });
  }
  async function resource({ deck_id, revision, kind, slide_id, preset }) {
    const ctx = await load(deck_id); cas(ctx.revision, revision);
    if (kind === 'slide') {
      const ref = await buildImage(ctx, slide_id);
      if (!ref) fail('Preview unavailable');
      return { deck_id, revision, slide_id, uri: uri(deck_id, revision, 'slides', slide_id), image: await imageAt(ctx, ref.file, ref.sha256) };
    }
    if (kind === 'audition' && PRESETS.has(preset)) {
      const report = await jsonFile(ctx, 'preview-build/audition/report.json');
      const ref = await candidateImage(ctx, preset, report, slide_id);
      if (!ref) fail('Audition unavailable');
      return { deck_id, revision, slide_id: ref.slide_id, uri: uri(deck_id, revision, 'audition', `${preset}/${ref.slide_id}`), image: await imageAt(ctx, ref.file, ref.sha256) };
    }
    fail('Unknown resource');
  }
  return { list, inspect, slide, update, build, audition, resource };
}
