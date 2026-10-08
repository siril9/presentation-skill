import { build } from 'esbuild';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import path from 'node:path';
import assert from 'node:assert/strict';

const here = path.dirname(fileURLToPath(import.meta.url));
const { values } = parseArgs({ options: { root: { type: 'string' }, deck: { type: 'string' }, outdir: { type: 'string' }, playwright: { type: 'string' }, 'browser-executable': { type: 'string' } }, strict: true });
if (!values.root || !values.deck || !values.outdir || !values.playwright) throw new Error('Pass --root, --deck, --outdir and --playwright (installed module entry).');
const { chromium } = await import(values.playwright);
const outdir = path.resolve(values.outdir);
await mkdir(outdir, { recursive: true });
const html = await readFile(path.resolve(here, '../dist/preview.html'), 'utf8');
const bundle = await build({ entryPoints: [path.join(here, 'browser-host.mjs')], bundle: true, write: false, format: 'esm', platform: 'browser', target: 'es2022' });
const hostHtml = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><script type="module">${bundle.outputFiles[0].text.replace(/<\/script/gi, '<\\/script')}</script></body></html>`;
const transport = new StdioClientTransport({ command: process.execPath, args: [path.resolve(here, '../server.mjs'), '--root', path.resolve(values.root)], stderr: 'pipe' });
const client = new Client({ name: 'preview-browser', version: '1.0.0' });
const errors = [];
let browser;
let currentPage;
const report = { passed: false, transport: 'MCP AppBridge + real stdio tools; not the live Codex host', viewports: [] };
try {
  await client.connect(transport);
  const initial = await client.callTool({ name: 'presentation_open', arguments: { deck_id: values.deck } });
  assert.notEqual(initial.isError, true);
  browser = await chromium.launch({ headless: true, ...(values['browser-executable'] ? { executablePath: values['browser-executable'] } : {}) });
  for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport });
    currentPage = page;
    page.on('pageerror', error => errors.push(error.message));
    await page.exposeFunction('initialPreviewResult', () => initial);
    await page.exposeFunction('callPreviewTool', async args => {
      // Exercise race handling: the earlier selection finishes last.
      if (args.name === 'presentation_slide' && args.arguments.slide_id === initial.structuredContent.slides[1].slide_id) await new Promise(resolve => setTimeout(resolve, 180));
      return client.callTool(args, undefined, { timeout: 240_000 });
    });
    await page.addInitScript(id => { window.previewDeckId = id; }, values.deck);
    await page.route('http://preview.test/**', route => route.fulfill({ contentType: 'text/html', body: new URL(route.request().url()).pathname === '/preview' ? html : hostHtml }));
    await page.goto('http://preview.test/');
    const panel = page.frameLocator('iframe');
    await panel.locator('.slide-item').first().waitFor();
    await panel.locator('.slide-stage img').waitFor({ state: 'visible' });
    assert.equal(await panel.locator('.slide-item').count(), initial.structuredContent.slides.length);
    assert.equal(await page.evaluate(() => window.previewCalls.filter(c => c.name === 'presentation_open').length), 0, 'Initial result must not trigger duplicate open');
    const ids = initial.structuredContent.slides;
    await panel.locator(`.slide-item[data-slide-id="${ids[1].slide_id}"]`).click();
    await panel.locator(`.slide-item[data-slide-id="${ids[3].slide_id}"]`).click();
    await panel.locator('.slide-title').filter({ hasText: ids[3].title }).waitFor();
    await page.waitForTimeout(300);
    assert.equal(await panel.locator('.slide-title').textContent(), ids[3].title);
    const context = await page.evaluate(() => window.previewContexts.at(-1));
    assert.equal(context.structuredContent.slide_id, ids[3].slide_id);
    assert.equal(context.structuredContent.revision, initial.structuredContent.revision);
    assert.ok(!JSON.stringify(context).includes('data:image/'));
    await panel.getByLabel('Revision request').fill('Keep the data unchanged; clarify the headline.');
    await panel.getByRole('button', { name: 'Request revision' }).click();
    await page.waitForFunction(() => window.previewMessages.length === 1);
    const message = await page.evaluate(() => window.previewMessages[0]);
    assert.match(message.content[0].text, /clarify the headline/);
    assert.ok(message.content[0].text.includes(ids[3].slide_id));
    if (viewport.width > 720) {
      await panel.getByRole('button', { name: 'Compare styles', exact: true }).click();
      await panel.locator('.comparison-grid figure img').first().waitFor({ state: 'visible', timeout: 120_000 });
      assert.equal(await panel.locator('.comparison-grid figure img').count(), 3);
      await panel.getByRole('button', { name: 'Select style' }).first().click();
      assert.match(await panel.getByLabel('Revision request').inputValue(), /lab-report/);
      await panel.getByRole('button', { name: 'Request revision', exact: true }).click();
      await page.waitForFunction(() => window.previewMessages.length === 2);
      assert.equal(await page.evaluate(() => window.previewCalls.filter(c => c.name === 'presentation_update_slide').length), 0, 'Style selection must not silently mutate source');
    }
    const metrics = await panel.locator('body').evaluate(body => ({ width: body.scrollWidth, viewport: innerWidth, images: [...document.images].filter(im => im.complete && im.naturalWidth > 0).length }));
    assert.ok(metrics.width <= metrics.viewport, `Horizontal overflow at ${viewport.width}`);
    assert.ok(metrics.images >= 1, 'Rendered slide pixels must load');
    await panel.locator('body').evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(outdir, `slide-review-${viewport.width}.png`) });
    report.viewports.push({ ...viewport, ...metrics, selected_slide: ids[3].slide_id, model_context_synced: true, explicit_request_sent: true, selection_race_pass: true, duplicate_open_count: 0, ...(viewport.width > 720 ? { style_picker_pass: true } : {}) });
    await page.close();
  }
  const limited = await browser.newPage();
  currentPage = limited;
  limited.on('pageerror', error => errors.push(error.message));
  await limited.addInitScript(() => {
    window.__PRESENTATION_PREVIEW_DEV__ = true;
    window.__PRESENTATION_PREVIEW_FIXTURE__ = { structuredContent: {
      deck_id: 'read-only', revision: 'a'.repeat(64), slides: [{ slide_id: 'cover', index: 0, title: 'Cover' }],
      qa: { state: 'not_built', visual_review: 'pending' },
    } };
  });
  await limited.route('http://preview.test/**', route => route.fulfill({ contentType: 'text/html', body: html }));
  await limited.goto('http://preview.test/');
  for (const name of ['Refresh deck', 'Build deck', 'Compare styles', 'Request revision']) {
    assert.equal(await limited.getByRole('button', { name, exact: true }).isDisabled(), true, `${name} needs a host capability`);
  }
  assert.equal(await limited.getByLabel('Deck', { exact: true }).isDisabled(), true);
  assert.equal(await limited.locator('.slide-item').first().isEnabled(), true, 'Supplied deck remains navigable');
  await limited.waitForTimeout(100);
  assert.match(await limited.locator('.status-line').textContent(), /QA: not_built/);
  report.limited_capabilities = 'controls gated; supplied slide remains selectable';
  await limited.close();
  assert.deepEqual(errors, []);
  report.passed = true;
} finally {
  if (!report.passed && currentPage && !currentPage.isClosed()) {
    await currentPage.screenshot({ path: path.join(outdir, 'browser-failure.png'), fullPage: true });
    report.failure_state = await currentPage.evaluate(() => ({ calls: window.previewCalls, contexts: window.previewContexts, frames: document.querySelectorAll('iframe').length }));
    report.frame_text = await currentPage.frames().at(-1)?.locator('body').innerText().catch(() => 'unavailable');
  }
  report.page_errors = errors;
  await writeFile(path.join(outdir, 'browser-report.json'), JSON.stringify(report, null, 2) + '\n');
  await browser?.close(); await client.close(); await transport.close();
}
console.log(JSON.stringify(report, null, 2));
