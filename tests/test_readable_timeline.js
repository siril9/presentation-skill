'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const builder = require('../scripts/build_deck_pptxgenjs.js');
const { renderStandard, renderTimeline, addSummaryCallout, SLIDE_H } = require('../templates/pptxgenjs/slides.js');
const { getPreset } = require('../templates/pptxgenjs/presets.js');
const GRAMMARS = Object.keys(require('../references/renderer_role_contracts_v2.json').grammars);

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

test('v2 timeline captions reserve visible space in every grammar and composition', () => {
  for (const grammar of GRAMMARS) {
    for (const mode of ['bands', 'rail', 'chapter-spread']) {
      const preset = builder.applyDeckStyle(getPreset('lab-report'), { deck_style: {
        composition_grammar: grammar, readability_contract: { min_body_pt: 16, min_caption_pt: 9 },
      } }, 'lab-report');
      const data = { role: 'evidence', variant: 'timeline', title: 'Confirmation gates', timeline_mode: mode,
        caption: 'Proposed design only. Six lots are a planning choice, not a power calculation; no minimum validated shelf life follows from this proposal.',
        takeaway: 'Predeclare the limits before collecting results.',
        milestones: Array.from({ length: 3 }, (_, i) => ({ label: `Gate ${i + 1}`, title: 'Review evidence', body: 'Check blanks and spike recovery before release.' })) };
      const texts = [], shapes = [];
      const slide = { addText: (text, box) => texts.push({ text, ...box }),
        addShape: (shape, box) => shapes.push({ shape, ...box }), addNotes() {} };
      renderTimeline({}, slide, data, preset);
      addSummaryCallout({}, slide, data, preset);
      const caption = texts.find((op) => op.text === data.caption);
      assert.ok(caption, `${grammar}/${mode}: caption retained`);
      assert.ok(caption.fontSize >= 9);
      assert.notEqual(caption.fit, 'shrink');
      const callout = shapes.find((op) => op.objectName === 'content:summary-callout');
      assert.ok(caption.y + caption.h <= callout.y - 0.10);
      for (const op of texts.filter((op) => /Review evidence|Check blanks/.test(op.text))) {
        assert.ok(op.y + op.h <= caption.y - 0.08, `${grammar}/${mode}: caption clears content`);
      }
    }
  }
});

test('v2 editorial heading clears masthead while pinned v1 placement stays unchanged', () => {
  for (const version of ['renderer_role_contracts_v2', 'renderer_role_systems_v1']) {
    const preset = builder.applyDeckStyle(getPreset('editorial-minimal'), { deck_style: {
      renderer_role_contract_version: version, font_pair: 'editorial_serif_v1', readability_contract: { min_body_pt: 16 },
    } }, 'editorial-minimal');
    preset.renderer_role_contract_version = version;
    const texts = [];
    const slide = { addText: (text, box) => texts.push({ text, ...box }), addShape() {}, addNotes() {} };
    const data = { role: 'evidence', variant: 'timeline', title: "A queue becomes the evening's clock",
      subtitle: 'Three moments in the synthetic baseline, not eyewitness reporting', timeline_mode: 'chapter-spread',
      caption: 'Simplified end-of-interval seat release, FIFO queue, empty initial queue. Moments describe one invented representative evening; they do not measure individual waiting times.',
      milestones: [{ label: '17:30', title: 'Seats go unused', body: 'The first release boards 40 of 80 places. Spare seats cannot be carried forward.' },
        { label: '19:00', title: 'The wave arrives', body: 'The 18:30-19:00 interval adds 145 arrivals. After boarding, 95 people remain in the queue.' },
        { label: '20:00', title: 'The count is unfinished', body: '425 people have boarded; 115 remain. The model has no later service or abandonment.' }] };
    renderTimeline({}, slide, data, preset);
    const heading = texts.find((op) => op.text === data.title);
    if (version.endsWith('v2')) {
      assert.ok(heading.y >= 0.26, 'title below masthead accent at y=0.18, h=0.028');
      assert.ok(texts.some((op) => op.text === data.caption));
      assert.equal(data.__roleContractExecution.adaptation, 'readable-timeline-chapter-spread');
      const label = texts.find((op) => op.objectName === 'metadata:timeline-label-0');
      const focusTitle = texts.find((op) => op.text === data.milestones[0].title);
      assert.ok(focusTitle.y - label.y - label.h >= 0.08 - 1e-6, 'focus label/title stack meets the real QA gap');
    } else {
      assert.equal(heading.y, 0.10);
      assert.ok(!texts.some((op) => op.text === data.caption));
    }
  }
});

test('operations timeline takeaway clears its last row and footer frame', () => {
  const original = 'If F-04 is not stable by hour 12, transfer its load before the 18-hour limit.';
  const preset = builder.applyDeckStyle(getPreset('charcoal-safety'), { deck_style: {
    style_preset: 'charcoal-safety', composition_grammar: 'operations-grid',
    footer_mode: 'source-line', footer_page_numbers: true,
    readability_contract: { min_body_pt: 16, min_metadata_pt: 9 },
  } }, 'charcoal-safety');
  for (const takeaway of ['', 'Transfer F-04 before hour 18.', original,
    `${original} Quality must confirm a stable temperature before release.`]) {
    const data = { role: 'evidence', variant: 'timeline', title: 'Dispatch is a gated sequence, not a repair list',
      timeline_mode: 'bands', sources: ['S1'], __slideIndex: 4, __slideCount: 7, takeaway,
      milestones: [
        { label: '0-2 h', title: 'Confirm', body: 'Check logger and standby capacity.' },
        { label: '2-6 h', title: 'Dispatch', body: 'Assign crews A-C; stage transfer kits.' },
        { label: '6-18 h', title: 'Repair', body: 'Close jobs; escalate starts delayed 2 h.' },
        { label: '18-24 h', title: 'Verify', body: 'Log stable temperature before release.' },
      ] };
    const shapes = [];
    const texts = [];
    const slide = { addText: (text, box) => texts.push({ text, box }),
      addShape: (shape, box) => shapes.push({ shape, box }), addNotes() {} };
    renderTimeline({}, slide, data, preset);
    addSummaryCallout({}, slide, data, preset);
    const lastRow = shapes.filter(({ box }) => box.objectName === 'role-contract-slot:evidence:timeline-3').at(-1);
    const callout = shapes.find(({ shape }) => shape === 'roundRect');
    assert.ok(lastRow);
    if (!takeaway) {
      assert.equal(callout, undefined);
      continue;
    }
    assert.ok(callout);
    assert.ok(callout.box.y - (lastRow.box.y + lastRow.box.h) >= 0.14);
    assert.ok((SLIDE_H - 0.56) - (callout.box.y + callout.box.h) >= 0.14);
    assert.ok(texts.some(({ text, box }) => text === takeaway && box.fontSize >= 16));
  }
});

test('operations timeline widens complete gate text before rejecting its declared caption', () => {
  const preset = builder.applyDeckStyle(getPreset('lavender-ops'), { deck_style: {
    composition_grammar: 'operations-grid', font_pair: 'clean_modern_v1', footer_mode: 'source-line',
    readability_contract: { min_body_pt: 16, min_support_pt: 13, min_caption_pt: 9, min_metadata_pt: 9 },
  } }, 'lavender-ops');
  const data = { role: 'evidence', variant: 'timeline', title: 'Three gates stand between budget and service',
    subtitle: 'Synthetic process register; owners are proposed roles, not named staff', sources: ['SYN-O2'],
    caption: 'Readiness and commissioning are gates, not a how-to guide. A passed functional check does not certify long-term uptime or eliminate electrical risk.',
    milestones: [
      { label: 'BEFORE / facilities', title: 'Confirm readiness', body: 'Qualified diagnosis, approved permit, correct part, and verified critical-load backup. Stop if any is missing.' },
      { label: 'WORK / qualified crew', title: 'Execute site procedure', body: 'Only authorized personnel perform isolation and repair under approved local procedures. No live-work method is given here.' },
      { label: 'AFTER / commissioning', title: 'Verify before release', body: 'Document site-required tests and authorized sign-off before service release; preserve event logs for follow-up.' },
    ] };
  const texts = [];
  renderTimeline({}, { addText: (text, box) => texts.push({ text, ...box }), addShape() {}, addNotes() {} }, data, preset);
  const visible = texts.map((op) => Array.isArray(op.text) ? op.text.map((run) => run.text).join('') : op.text).join('\n');
  for (const row of data.milestones) {
    assert.ok(visible.includes(row.title));
    assert.ok(visible.includes(row.body));
    assert.ok(visible.toUpperCase().includes(row.label.toUpperCase()));
  }
  const caption = texts.find((op) => op.text === data.caption);
  assert.ok(caption && caption.fontSize >= 9);
  assert.ok(texts.filter((op) => Array.isArray(op.text)).every((op) => op.fontSize >= 16 && op.fit !== 'shrink'
    && op.y + op.h <= caption.y - 0.08));
  const labels = texts.filter((op) => /^metadata:timeline-label-/.test(op.objectName));
  assert.equal(labels.length, data.milestones.length, 'metadata must have its own semantic shapes');
  for (const op of texts.filter((op) => Array.isArray(op.text))) {
    assert.ok(op.text.every((run) => (run.options?.fontSize || op.fontSize) >= 16), 'body shapes contain only readable body runs');
    const label = labels.find((item) => Math.abs(item.y - op.y) < 0.01);
    assert.ok(label && op.x - label.x - label.w >= 0.08 - 1e-6);
  }
});

test('non-timeline callout keeps its legacy size and placement', () => {
  const preset = builder.applyDeckStyle(getPreset('charcoal-safety'), { deck_style: {
    style_preset: 'charcoal-safety', composition_grammar: 'operations-grid',
    footer_mode: 'source-line', footer_page_numbers: true,
    readability_contract: { min_body_pt: 16 },
  } }, 'charcoal-safety');
  const data = { role: 'content', variant: 'standard', title: 'Shift notes',
    bullets: ['Confirm logger state.'], takeaway: 'Retain the standby crew until hour 12.',
    sources: ['S1'], __slideIndex: 3, __slideCount: 7 };
  const shapes = [];
  const texts = [];
  const slide = { addText: (text, box) => texts.push({ text, box }),
    addShape: (shape, box) => shapes.push({ shape, box }), addNotes() {} };
  renderStandard({}, slide, data, preset);
  addSummaryCallout({}, slide, data, preset);
  const callout = shapes.find(({ shape }) => shape === 'roundRect');
  const calloutText = texts.find(({ text }) => text === data.takeaway);
  assert.ok(callout);
  assert.ok(calloutText);
  assert.equal(callout.box.y, SLIDE_H - 0.40 - 0.62);
  assert.equal(callout.box.h, 0.62);
  assert.equal(calloutText.box.fontSize, 14);
});

test('v2 timeline shares the measured callout reservation across grammars and modes', () => {
  for (const grammar of GRAMMARS) {
    for (const mode of ['', 'lab-box']) {
      const preset = builder.applyDeckStyle(getPreset('lab-report'), { deck_style: {
        style_preset: 'lab-report', composition_grammar: grammar,
        footer_mode: 'source-line', footer_page_numbers: true,
        readability_contract: { min_body_pt: 16, min_metadata_pt: 9 },
      } }, 'lab-report');
      const data = { role: 'evidence', variant: 'timeline', title: 'Dispatch gates',
        timeline_mode: 'bands', sources: ['S1'], __slideIndex: 4, __slideCount: 7,
        summary_callout_mode: mode,
        takeaway: 'If F-04 is not stable by hour 12, transfer its load before the 18-hour limit. '.repeat(2),
        milestones: [
          { label: '0-2 h', title: 'Confirm', body: 'Check logger and standby capacity.' },
          { label: '2-6 h', title: 'Dispatch', body: 'Assign crews A-C; stage transfer kits.' },
          { label: '6-18 h', title: 'Repair', body: 'Close jobs; escalate delayed starts.' },
          { label: '18-24 h', title: 'Verify', body: 'Log stable temperature before release.' },
        ] };
      const shapes = [], texts = [];
      const slide = { addText: (text, box) => texts.push({ text, box }),
        addShape: (shape, box) => shapes.push({ shape, box }), addNotes() {} };
      renderTimeline({}, slide, data, preset);
      addSummaryCallout({}, slide, data, preset);
      const callout = shapes.find(({ box }) => box.objectName === 'content:summary-callout');
      assert.ok(callout, `${grammar}/${mode}: shared callout`);
      const lastRow = shapes.filter(({ box }) => box.objectName === 'role-contract-slot:evidence:timeline-3').at(-1);
      assert.ok(callout.box.y - (lastRow.box.y + lastRow.box.h) >= 0.14);
      const text = texts.find((item) => item.text === data.takeaway.trim());
      assert.ok(text && text.box.fontSize >= 16);
      assert.notEqual(text.box.fit, 'shrink');
      assert.ok(callout.box.y + callout.box.h <= SLIDE_H - 0.52);
      data.takeaway = 'This complete caveat must remain visible. '.repeat(500);
      assert.throws(() => renderTimeline({}, slide, data, preset), /summary.*split the source slide/i);
    }
  }
});
