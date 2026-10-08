import test from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import { createServer } from '../server.mjs';

const revision = 'a'.repeat(64);
async function connection(overrides = {}) {
  const payload = { deck_id: 'demo', title: 'Synthetic library study', revision, slides: [], qa: { state: 'not_built', visual_review: 'pending' } };
  const backend = {
    list: async () => ({ decks: [{ deck_id: 'demo', title: payload.title }] }),
    inspect: async () => payload,
    slide: async () => ({ ...payload, slide: { source: { title: 'Selected' } }, image: { data: 'cGl4ZWxz', mimeType: 'image/jpeg' } }),
    update: async () => payload, build: async () => payload, audition: async () => ({ ...payload, candidates: [] }),
    resource: async () => ({ deck_id: 'demo', revision, image: { data: 'cGl4ZWxz', mimeType: 'image/jpeg' } }),
    ...overrides,
  };
  const server = createServer(backend, { html: '<!doctype html><title>Slide Review</title>' });
  const [serverTransport, clientTransport] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 'preview-test', version: '1.0.0' });
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  return { client, close: async () => { await client.close(); await server.close(); } };
}

test('MCP advertises a thread panel, bounded operations and correct write hints', async () => {
  const { client, close } = await connection();
  try {
    const { tools } = await client.listTools();
    assert.equal(tools.length, 6);
    const open = tools.find((t) => t.name === 'presentation_open');
    assert.deepEqual(open._meta['openai/ui'].entrypoints, [{ type: 'thread' }]);
    assert.equal(open.inputSchema.additionalProperties, false);
    assert.equal(tools.find((t) => t.name === 'presentation_build').annotations.readOnlyHint, false);
    assert.deepEqual(tools.find((t) => t.name === 'presentation_preview')._meta.ui.visibility, ['app']);
    const opened = await client.callTool({ name: 'presentation_open', arguments: {} });
    assert.equal(opened.structuredContent.decks[0].deck_id, 'demo');
    const resource = await client.readResource({ uri: open._meta.ui.resourceUri });
    assert.match(resource.contents[0].text, /Slide Review/);
    assert.deepEqual(resource.contents[0]._meta.ui.csp.connectDomains, []);
  } finally { await close(); }
});

test('images stay outside structured model content', async () => {
  const { client, close } = await connection();
  try {
    const selected = await client.callTool({ name: 'presentation_slide', arguments: { deck_id: 'demo', slide_id: 'slide-1', revision } });
    assert.equal(selected._meta.preview.data, 'cGl4ZWxz');
    assert.equal(selected.structuredContent.image, undefined);
    assert.doesNotMatch(JSON.stringify(selected.content), /cGl4ZWxz/);
  } finally { await close(); }
});

test('schemas reject extra commands and malformed revisions before calling backend', async () => {
  let called = false;
  const { client, close } = await connection({ build: async () => { called = true; return {}; } });
  try {
    for (const args of [{ deck_id: 'demo', revision, command: 'touch /tmp/injected' }, { deck_id: 'demo', revision: 'stale' }]) {
      const response = await client.callTool({ name: 'presentation_build', arguments: args });
      assert.equal(response.isError, true);
    }
    assert.equal(called, false);
  } finally { await close(); }
});

test('backend errors do not expose host paths or executable output', async () => {
  const { client, close } = await connection({ inspect: async () => { const error = new Error('/private/secret/api-key'); error.code = 'STALE_REVISION'; throw error; } });
  try {
    const response = await client.callTool({ name: 'presentation_open', arguments: { deck_id: 'demo' } });
    assert.equal(response.isError, true);
    assert.equal(response.structuredContent.error, 'STALE_REVISION');
    assert.doesNotMatch(JSON.stringify(response), /secret|api-key/);
  } finally { await close(); }
});
