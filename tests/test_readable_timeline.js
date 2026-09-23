'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const builder = require('../scripts/build_deck_pptxgenjs.js');
const { renderTimeline } = require('../templates/pptxgenjs/slides.js');
const { getPreset } = require('../templates/pptxgenjs/presets.js');

function render(mode, count = 4) {
  const preset = builder.applyDeckStyle(getPreset('lab-report'), { deck_style: {
    style_preset: 'lab-report', readability_contract: { min_body_pt: 16 },
  } }, 'lab-report');
  const operations = [];
  const slide = { addText: (text, opts) => operations.push({ text, ...opts }),
    addShape: () => {}, addNotes: () => {} };
  const data = { role: 'evidence', variant: 'timeline', title: 'Pilot gates', timeline_mode: mode,
    milestones: Array.from({ length: count }, (_, i) => ({ label: `Week ${i + 1}`, title: `Gate ${i + 1}`, body: `Review evidence ${i + 1}.` })) };
  renderTimeline({}, slide, data, preset);
  return { data, operations };
}

test('readable timelines retain three distinct bounded compositions', () => {
  const fingerprints = new Set();
  for (const mode of ['bands', 'rail', 'chapter-spread']) {
    const { data, operations } = render(mode);
    const bodies = operations.filter((op) => String(op.text).startsWith('Review evidence'));
    assert.equal(bodies.length, 4);
    assert.ok(bodies.every((op) => op.fontSize >= 16));
    assert.ok(data.__roleContractExecution);
    fingerprints.add(JSON.stringify(bodies.map(({ x, y, w, h }) => [x, y, w, h])));
  }
  assert.equal(fingerprints.size, 3);
});

test('six milestones fail explicitly instead of silently dropping the last', () => {
  assert.throws(() => render('rail', 6), /split the source slide/);
});
