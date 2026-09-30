'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const builder = require('../scripts/build_deck_pptxgenjs.js');
const renderers = require('../templates/pptxgenjs/slides.js');
const { getPreset } = require('../templates/pptxgenjs/presets.js');
const { RECIPES, planReadableRole, textWidth, wrapText } = require('../templates/pptxgenjs/readable_role_layouts.js');

const FACTS = [
  { value: '3', label: 'Primary studies', detail: 'Studies connect validation with diagnosis and local care decisions.' },
  { value: '44', label: 'ICU participants', detail: 'Two cohorts retained separate outcomes because clinical pipelines differed between hospitals.' },
  { value: '3/26', label: 'Methylation findings', detail: 'Family context helped resolve difficult findings while methylation supported interpretation in selected patients.' },
  { value: '16/16', label: 'Structural variants', detail: 'All benchmark events were detected and reviewed independently before results informed the next prospective validation phase.' },
];
const DECISIONS = [
  { title: 'Selection', body: 'Selected intensive care cohorts limit generalizability beyond the enrolled patients.' },
  { title: 'Comparability', body: 'Family structure, referral criteria, pipelines, and turnaround definitions differ; retain separate denominators.' },
  { title: 'Endpoints', body: 'Diagnosis and care changes are reported, but survival and cost require prospective local outcome collection.' },
  { title: 'Operations', body: 'DNA quality, interpretation coverage, confirmation, and governance remain local responsibilities with named owners and documented escalation procedures.' },
];
const LONG_OPERATIONS = [
  { title: 'Release / commissioning', body: 'Require documented site tests and authorized sign-off. No sign-off means no service release.' },
  { title: 'Observe / operations', body: 'Track the next full 720-hour window, including planned downtime; retain every event and missing-data interval.' },
  { title: 'Escalate / maintenance', body: 'Any connector-tagged recurrence triggers qualified reassessment. Never hide it in the aggregate uptime.' },
  { title: 'Evaluate / facilities', body: 'At complete 720-hour coverage, target downtime <=3.6 h. Missing coverage means uptime is unverified.' },
];
const BASE = path.resolve(__dirname, '../decks/v011-monochrome-lab-comparison-20260823');
const plain = (text) => Array.isArray(text) ? text.map((run) => run.text).join('') : String(text);
const normalized = (text) => plain(text).replace(/\s+/g, ' ').trim();

function lineWidths(text, fontSize, fontFace, bold = false) {
  const widths = [0];
  const runs = Array.isArray(text) ? text : [{ text, options: { bold } }];
  for (const run of runs) {
    String(run.text).split('\n').forEach((line, index) => {
      if (index) widths.push(0);
      widths[widths.length - 1] += textWidth(line, fontSize, fontFace, run.options?.bold ?? bold);
    });
  }
  return widths;
}

function presetFor(grammar, font, floor = 15, extra = {}) {
  const preset = builder.applyDeckStyle(getPreset('lab-report'), { deck_style: {
    composition_grammar: grammar, palette_key: 'lab_monochrome_v1',
    style_seed: 'bounded-readable-proof', header_variant: 'plain',
    readability_contract: { min_title_pt: 28, min_body_pt: floor, min_footer_pt: 9 },
    ...extra,
  } }, 'lab-report');
  preset.font_heading = font;
  preset.font_body = font;
  return preset;
}

function slideData(role, variant = 'primary') {
  return role === 'evidence' ? {
    type: 'content', role, variant: 'stats', role_layout_variant: variant,
    title: 'Evidence supports a controlled\nimplementation study', facts: structuredClone(FACTS), sources: ['S1', 'S2'],
  } : {
    type: 'content', role, variant: 'matrix', role_layout_variant: variant,
    title: 'Evidence supports controlled adoption, not broad equivalence', quadrants: structuredClone(DECISIONS), sources: ['S1', 'S2'],
  };
}

function capture(data, preset) {
  const operations = [];
  const slide = {
    addText: (text, options) => operations.push({ text, options }),
    addShape: (shape, options) => operations.push({ shape, options }),
    addNotes() {}, addImage() {},
  };
  renderers[data.variant === 'matrix' ? 'renderMatrix' : 'renderStats']({}, slide, data, preset);
  return operations;
}

function checkBoxes(ops, data, floor) {
  const role = data.role;
  const texts = ops.filter((op) => op.text && op.options.objectName?.startsWith(`${role}:`));
  const slots = data.__roleContractExecution.executed_slots;
  assert.equal(data.__roleContractExecution.rendered_item_count, 4);
  assert.equal(slots.length, 4);
  for (const { text, options: box } of texts) {
    assert.ok(box.fontSize >= floor);
    assert.notEqual(box.fit, 'shrink');
    assert.ok(box.x >= 0.5 && box.y >= 0 && box.x + box.w <= 9.51 && box.y + box.h <= 5.07, JSON.stringify(box));
    for (const width of lineWidths(text, box.fontSize, box.fontFace, box.bold)) assert.ok(width <= box.w, plain(text));
    const index = Number(box.objectName.split(':')[1]);
    const parent = slots[index];
    assert.ok(box.x >= parent.x - 0.001 && box.x + box.w <= parent.x + parent.w + 0.001);
    assert.ok(box.y >= parent.y - 0.001 && box.y + box.h <= parent.y + parent.h + 0.001);
  }
  for (let i = 0; i < texts.length; i += 1) {
    for (let j = i + 1; j < texts.length; j += 1) {
      const a = texts[i].options; const b = texts[j].options;
      const overlap = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 0.001
        && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 0.001;
      assert.ok(!overlap, `${texts[i].text} overlaps ${texts[j].text}`);
    }
  }
  const items = role === 'evidence' ? data.facts : data.quadrants;
  items.forEach((item, index) => {
    for (const [kind, value] of Object.entries(role === 'evidence'
      ? { value: item.value, label: item.label, caption: item.detail }
      : { value: String(index + 1).padStart(2, '0'), label: item.title, caption: item.body })) {
      const op = texts.find((entry) => entry.options.objectName === `${role}:${index}:${kind}`);
      if (!op) {
        const body = texts.find((entry) => entry.options.objectName === `${role}:${index}:body`);
        assert.ok(body, `${role}:${index}:${kind}`);
        if (kind === 'value') assert.ok(normalized(body.text).startsWith(`${value} `));
        else assert.ok(normalized(body.text).includes(normalized(value)));
      } else {
        assert.ok(op, `${role}:${index}:${kind}`);
        assert.equal(normalized(op.text), normalized(value));
      }
    }
  });
}

for (const grammar of Object.keys(RECIPES)) {
  for (const font of ['Helvetica Neue', 'Georgia']) {
    for (const floor of [15, 16]) {
      for (const variant of ['primary', 'alternate', 'dense']) {
        for (const role of ['evidence', 'decision']) {
          test(`${grammar} ${role} ${font} ${floor}pt ${variant}`, () => {
            const preset = presetFor(grammar, font, floor);
            const data = slideData(role, variant);
            if (grammar === 'operations-grid' && role === 'decision' && floor === 16) {
              // Equal peer widths and safe insets make this long-copy fixture
              // infeasible. The exact authored runtime case below must fit.
              assert.throws(() => capture(data, preset), /Shorten or split this slide; no content was dropped/);
              return;
            }
            const ops = capture(data, preset);
            checkBoxes(ops, data, floor);
            assert.match(data.__roleContractExecution.adaptation, new RegExp(grammar));
            assert.deepEqual(ops, capture(slideData(role, variant), preset), 'fixed inputs must be stable');
          });
        }
      }
    }
  }
}

test('eight grammars keep distinct executed geometry for both roles', () => {
  for (const role of ['evidence', 'decision']) {
    const signatures = Object.keys(RECIPES).map((grammar) => {
      const data = slideData(role);
      capture(data, presetFor(grammar, 'Helvetica Neue'));
      return JSON.stringify(data.__roleContractExecution.executed_slots);
    });
    assert.equal(new Set(signatures).size, 8);
  }
});

test('long tokens never split and impossible content fails explicitly', () => {
  assert.equal(wrapText('Comparability', 2.3, 16, 'Georgia', true).text, 'Comparability');
  assert.throws(() => wrapText('Comparability', 0.4, 16, 'Georgia', true), /wider text box/);
  const items = FACTS.map((item) => ({ ...item, caption: 'Unbounded text '.repeat(150) }));
  assert.throws(() => planReadableRole({ grammar: 'scientific-evidence-plate', role: 'evidence',
    body: { x: 0.5, y: 1.4, w: 9, h: 3.4 }, items, fontSize: 16, fontHeading: 'Georgia', fontBody: 'Georgia' }), /no content was dropped/);
});

test('a fifth item is preserved, and an adapter limit is explicit', () => {
  const data = slideData('evidence');
  data.facts = Array.from({ length: 5 }, (_, i) => ({ value: String(i), label: `Signal ${i}`, detail: 'Reviewed locally' }));
  const ops = capture(data, presetFor('scientific-evidence-plate', 'Helvetica Neue'));
  assert.equal(data.__roleContractExecution.rendered_item_count, 5);
  assert.ok(ops.some((op) => op.text === 'Signal 4'));
  data.facts.push({ value: '5', label: 'Do not discard me' });
  assert.throws(() => capture(data, presetFor('scientific-evidence-plate', 'Helvetica Neue')), /must not be dropped/);
});

const V1_HASHES = {
  assay_notebook: ['b86f1e0c889f3ee656f3959abb311ca79e7d05fa17b346e3110aaf1462304505', 'f4938d531d6864ec598db5dd0d4d4e81597b1a09e5a97e8a77620823dd7a4d49', 'd0ff16f929be7da5362e872501568045847b0bda80cd929574efa1a4468b4671'],
  journal_appendix: ['0715c119f433a8a98c7af16d725ee901dbd20ed888a9425e10c40960dcd2aa2e', 'eb22863429de3bb448309f6833b2fc0e04432ec47f7e43a08bd5ce2245e10c87', 'c3c6aaa3cd491103c53df3987df931c9df8fc6024eba1c38648eefced9da00df'],
};
for (const [name, hashes] of Object.entries(V1_HASHES)) {
  for (const [position, index] of [1, 8, 9].entries()) {
    test(`v011 ${name} slide ${index + 1}: v1 operation snapshot unchanged`, () => {
      const outline = JSON.parse(fs.readFileSync(path.join(BASE, `outline_${name}.json`)));
      const preset = builder.applyDeckStyle(getPreset(outline.deck_style.style_preset), outline, outline.deck_style.style_preset);
      preset.renderer_role_contract_version = 'renderer_role_systems_v1';
      const ops = capture(structuredClone(outline.slides[index]), preset);
      assert.equal(crypto.createHash('sha256').update(JSON.stringify(ops)).digest('hex'), hashes[position]);
    });
    test(`v011 ${name} slide ${index + 1}: metric contrast and intact words`, () => {
      const outline = JSON.parse(fs.readFileSync(path.join(BASE, `outline_${name}.json`)));
      const preset = builder.applyDeckStyle(getPreset(outline.deck_style.style_preset), outline, outline.deck_style.style_preset);
      const data = structuredClone(outline.slides[index]);
      const ops = capture(data, preset);
      if (index === 9) {
        assert.ok(ops.some((op) => op.text === 'Comparability'));
      } else {
        const metric = ops.find((op) => op.options.objectName === 'evidence:0:value');
        const dark = ops.find((op) => op.options.objectName === 'role-contract-slot:evidence:0' && op.options.fill);
        assert.ok(metric);
        if (dark) assert.equal(metric.options.color, 'FFFFFF');
        data.facts.forEach((fact, i) => {
          const label = ops.find((op) => op.options.objectName === `evidence:${i}:label`);
          assert.equal(normalized(label.text), fact.label);
        });
      }
    });
  }
}

test('numeric zero remains a visible metric', () => {
  const data = { role: 'evidence', variant: 'stats', title: 'Safety observations',
    facts: [{ value: 0, label: 'Adverse events', detail: 'No events observed.' }] };
  const ops = capture(data, presetFor('scientific-evidence-plate', 'Arial', 16));
  assert.ok(ops.some((op) => op.text === '0'));
});

test('oversized card inputs fail rather than losing the final item', () => {
  const data = { role: 'evidence', variant: 'cards-3', title: 'Review gates',
    cards: Array.from({ length: 6 }, (_, i) => ({ title: `Gate ${i}`, body: `Keep item ${i}.` })) };
  const slide = { addText() {}, addShape() {}, addNotes() {} };
  assert.throws(() => renderers.renderCards({}, slide, data,
    presetFor('scientific-evidence-plate', 'Arial', 16)), /split the source slide/);
});

test('a failed regular layout still tries a viable compact layout', () => {
  const plan = planReadableRole({ grammar: 'clinical-care-pathway', role: 'evidence',
    body: { x: 0.5, y: 1, w: 9, h: 3.5 }, fontSize: 16, fontHeading: 'Arial', fontBody: 'Arial',
    items: [{ value: '100 patients (95% CI: 90 to 110 patients)', label: 'Complete ascertainment', caption: 'All denominators retained.' }] });
  assert.equal(plan.placements.length, 1);
  assert.ok(plan.placements[0].texts.some((t) => plain(t.text).includes('denominators')));
});

test('advance-based wrapping removes only the extra character cap', () => {
  const args = ['Minimum interval is limited; retain timing.', 2.6, 16, 'Arial', false];
  const ordinary = wrapText(...args);
  assert.equal(ordinary.text, 'Minimum interval is\nlimited; retain\ntiming.');
  const measured = wrapText(...args, true);
  assert.ok(measured.h < ordinary.h);
  assert.equal(normalized(measured.text), args[0]);
  for (const line of measured.text.split('\n')) assert.ok(textWidth(line, 16, 'Arial') <= 2.56);
  assert.throws(() => wrapText('Comparability', 0.4, 16, 'Georgia', true, true), /wider text box/);
});

test('packed fallback measures bold labels and regular captions separately', () => {
  const label = '03 Escalate / maintenance:';
  const text = `${label} Any connector-tagged recurrence triggers qualified reassessment. Never hide it in the aggregate uptime.`;
  const args = [text, 4, 16, 'Arial', true, true];
  const mixed = wrapText(...args, label.length);
  assert.ok(mixed.h < wrapText(...args).h);
  assert.equal(normalized(mixed.text), text);
  let offset = 0;
  for (const line of mixed.text.split('\n')) {
    const prefix = Math.min(line.length, Math.max(0, label.length - offset));
    const width = textWidth(line.slice(0, prefix), 16, 'Arial', true)
      + textWidth(line.slice(prefix), 16, 'Arial', false);
    assert.ok(width <= 3.96);
    offset += line.length + 1;
  }
});

for (const grammar of Object.keys(RECIPES)) {
  test(`${grammar}: measured fallback keeps all four decision fields at 16pt`, () => {
    const items = LONG_OPERATIONS.map((item, index) => ({
      value: String(index + 1).padStart(2, '0'), label: item.title, caption: item.body,
    }));
    const input = { grammar, role: 'decision', body: { x: 0.5, y: 1.5, w: 9, h: grammar === 'operations-grid' ? 3.2 : 2.8 },
      items, fontSize: 16, fontHeading: 'Arial', fontBody: 'Arial' };
    const plan = planReadableRole(input);
    assert.match(plan.recipe, /measured-width$/);
    assert.ok(plan.recipe.startsWith(RECIPES[grammar].decision.id));
    assert.equal(plan.placements.length, 4);
    assert.deepEqual(plan, planReadableRole(input));
    for (const { index, texts, box } of plan.placements) {
      const retained = texts.map((text) => normalized(text.text)).join(' ');
      for (const value of Object.values(items[index])) assert.ok(retained.includes(value), value);
      for (const text of texts) {
        assert.equal(text.fontSize, 16);
        assert.ok(text.x >= box.x && text.y >= box.y);
        assert.ok(text.x + text.w <= box.x + box.w + 1e-6);
        assert.ok(text.y + text.h <= box.y + box.h + 1e-6);
        for (const width of lineWidths(text.text, text.fontSize, text.fontFace, text.bold)) {
          assert.ok(width <= text.w - 0.04 + 1e-6);
        }
      }
    }
    const ordinary = planReadableRole({ ...input, body: { ...input.body, h: 5 } });
    assert.doesNotMatch(ordinary.recipe, /measured-width/);
  });
}

test('measured evidence fallback retains separate metrics and captions', () => {
  const items = LONG_OPERATIONS.map((item, index) => ({
    value: String(index + 1).padStart(2, '0'), label: item.title, caption: item.body,
  }));
  const plan = planReadableRole({ grammar: 'operations-grid', role: 'evidence',
    body: { x: 0.5, y: 1.5, w: 9, h: 3.15 }, items,
    fontSize: 16, fontHeading: 'Arial', fontBody: 'Arial' });
  assert.match(plan.recipe, /measured-width$/);
  assert.equal(plan.placements.length, 4);
  for (const { index, texts, box } of plan.placements) {
    const metric = texts.find((text) => text.kind === 'value');
    assert.equal(metric.text, items[index].value);
    assert.ok(metric.fontSize >= 20);
    const retained = texts.map((text) => normalized(text.text)).join(' ');
    assert.ok(retained.includes(items[index].label));
    assert.ok(retained.includes(items[index].caption));
    for (const text of texts) {
      assert.ok(text.fontSize >= 16);
      assert.ok(text.y + text.h <= box.y + box.h + 1e-6);
    }
  }
});

test('operations repair gates fit the exact lavender runtime without losing safety fields', () => {
  const outline = JSON.parse(fs.readFileSync(path.resolve(__dirname,
    '../decks/v013-first-pass-20260929/operations/outline.json')));
  const data = { ...structuredClone(outline.slides[6]), __slideIndex: 6, __slideCount: outline.slides.length };
  const preset = builder.applyDeckStyle(getPreset('lavender-ops'), outline, 'lavender-ops');
  const ops = capture(data, preset);
  const visible = ops.filter((op) => op.text).map((op) => normalized(op.text)).join(' ');
  for (const item of data.quadrants) {
    assert.ok(visible.includes(item.title));
    assert.ok(visible.includes(item.body));
  }
  assert.ok(visible.includes(data.summary_callout));
  assert.equal(data.__roleContractExecution.rendered_item_count, 4);
  for (const [index, slot] of data.__roleContractExecution.executed_slots.entries()) {
    const field = ops.find((op) => op.options.objectName === `decision:${index}:body`);
    assert.ok(normalized(field.text).startsWith(String(index + 1).padStart(2, '0')));
    assert.equal(field.options.fontSize, 16);
    assert.notEqual(field.options.fit, 'shrink');
    assert.ok(field.options.x - slot.x >= 0.12 - 1e-6);
    assert.ok(slot.x + slot.w - field.options.x - field.options.w >= 0.12 - 1e-6);
    assert.ok(field.options.y - slot.y >= 0.12 - 1e-6);
    assert.ok(slot.y + slot.h - field.options.y - field.options.h >= 0.12 - 1e-6);
    for (const width of lineWidths(field.text, 16, field.options.fontFace, field.options.bold)) {
      assert.ok(width <= field.options.w - 0.04 + 1e-6);
    }
  }
});

for (const variant of ['primary', 'alternate', 'dense']) {
  test(`operations decision ${variant}: aligned pairs preserve source order and spacing`, () => {
    const outline = JSON.parse(fs.readFileSync(path.resolve(__dirname,
      '../decks/v013-first-pass-20260929/operations/outline.json')));
    const items = outline.slides[6].quadrants.map((item, index) => ({
      value: String(index + 1).padStart(2, '0'), label: item.title, caption: item.body,
    }));
    const input = { grammar: 'operations-grid', role: 'decision', variant,
      body: { x: 0.5, y: 1.3, w: 9, h: 3.2 }, items,
      fontSize: 16, fontHeading: 'Helvetica Neue', fontBody: 'Helvetica Neue' };
    const placements = planReadableRole(input).placements;
    const boxes = placements.map(({ box }) => box);
    assert.deepEqual([...placements].sort((a, b) => a.box.y - b.box.y || a.box.x - b.box.x)
      .map(({ index }) => index), [0, 1, 2, 3]);
    for (const [left, right] of [[boxes[0], boxes[1]], [boxes[2], boxes[3]]]) {
      assert.equal(left.y, right.y);
      assert.equal(left.h, right.h);
      assert.equal(left.w, right.w);
      assert.ok(right.x - left.x - left.w >= 0.12 - 1e-6);
    }
    assert.equal(boxes[0].x, boxes[2].x);
    assert.equal(boxes[1].x, boxes[3].x);
    assert.ok(boxes[2].y - boxes[0].y - boxes[0].h >= 0.12 - 1e-6);
    for (const { index, box, texts } of placements) {
      const retained = texts.map((text) => normalized(text.text)).join(' ');
      for (const value of Object.values(items[index])) assert.ok(retained.includes(value));
      for (const text of texts) {
        assert.equal(text.fontSize, 16);
        assert.ok(text.x - box.x >= 0.12 - 1e-6);
        assert.ok(box.x + box.w - text.x - text.w >= 0.12 - 1e-6);
        assert.ok(text.y - box.y >= 0.12 - 1e-6);
        assert.ok(box.y + box.h - text.y - text.h >= 0.12 - 1e-6);
        for (const width of lineWidths(text.text, 16, text.fontFace, text.bold)) assert.ok(width <= text.w - 0.04 + 1e-6);
      }
    }
    assert.throws(() => planReadableRole({ ...input, body: { ...input.body, h: 1.8 } }),
      /needs .*in height; available 1\.80in/);
  });
  test(`editorial decision ${variant}: first source item remains the feature on the left`, () => {
    const items = [
      { value: '01', label: 'Feature', caption: 'First authored decision.' },
      { value: '02', label: 'Detail 1', caption: 'Next authored decision.' },
      { value: '03', label: 'Detail 2', caption: 'Last authored decision.' },
    ];
    const input = { grammar: 'editorial-spread', role: 'decision', variant,
      body: { x: 0.5, y: 1.3, w: 9, h: 4 }, items,
      fontSize: 16, fontHeading: 'Georgia', fontBody: 'Georgia' };
    const { placements } = planReadableRole(input);
    const [feature, first, last] = placements.map(({ box }) => box);
    assert.ok(feature.x < first.x);
    assert.equal(first.x, last.x);
    assert.ok(first.y < last.y);
    assert.equal(feature.y, first.y);
    assert.ok(feature.h > first.h && feature.h > last.h);
    assert.notEqual(feature.w, first.w);
    placements.forEach(({ index, texts }) => {
      const retained = texts.map((text) => normalized(text.text)).join(' ');
      for (const value of Object.values(items[index])) assert.ok(retained.includes(value));
    });
    assert.deepEqual(planReadableRole(input), planReadableRole(input));
  });
}

async function proof(outdir) {
  const PptxGenJS = require('pptxgenjs');
  const deck = new PptxGenJS();
  deck.layout = 'LAYOUT_16x9';
  const manifest = [];
  for (const grammar of Object.keys(RECIPES)) {
    for (const role of ['evidence', 'decision']) {
      const data = slideData(role);
      const preset = presetFor(grammar, 'Georgia', 16);
      builder.renderSlide(deck, deck.addSlide(), data, preset);
      manifest.push({ slide: manifest.length + 1, grammar, role, execution: data.__roleContractExecution });
    }
  }
  for (const name of Object.keys(V1_HASHES)) {
    const outline = JSON.parse(fs.readFileSync(path.join(BASE, `outline_${name}.json`)));
    const preset = builder.applyDeckStyle(getPreset(outline.deck_style.style_preset), outline, outline.deck_style.style_preset);
    for (const index of [1, 8, 9]) {
      const data = structuredClone(outline.slides[index]);
      builder.renderSlide(deck, deck.addSlide(), data, preset);
      manifest.push({ slide: manifest.length + 1, source: name, source_slide: index + 1, execution: data.__roleContractExecution });
    }
  }
  for (let i = 0; i < process.argv.length; i += 1) {
    if (process.argv[i] !== '--source') continue;
    const file = path.resolve(process.argv[++i]);
    const outline = JSON.parse(fs.readFileSync(file));
    const name = outline.deck_style?.style_preset || 'warm-terracotta';
    const preset = builder.applyDeckStyle(getPreset(name), outline, name);
    outline.slides.forEach((data, index) => {
      if (!['stats', 'matrix'].includes(data.variant)) return;
      builder.renderSlide(deck, deck.addSlide(), data, preset);
      manifest.push({ slide: manifest.length + 1, source: file, source_slide: index + 1, execution: data.__roleContractExecution });
    });
  }
  fs.mkdirSync(outdir, { recursive: true });
  await deck.writeFile({ fileName: path.join(outdir, 'readable_roles.pptx') });
  fs.writeFileSync(path.join(outdir, 'manifest.json'), JSON.stringify(manifest, null, 2));
}

const proofIndex = process.argv.indexOf('--proof');
if (proofIndex !== -1) proof(path.resolve(process.argv[proofIndex + 1])).catch((error) => { console.error(error); process.exitCode = 1; });
