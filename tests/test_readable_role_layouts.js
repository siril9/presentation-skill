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
            if (grammar === 'operations-grid' && role === 'decision' && floor === 16 && font === 'Georgia') {
              // Georgia's wider copy remains infeasible here. Measured modern
              // headers let the Helvetica fixture fit with the same 16pt floor.
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

test('KPI footer and page number meet 4.5 contrast on their actual dark or light background', () => {
  const luminance = (color) => {
    const channels = [0, 2, 4].map((start) => parseInt(color.slice(start, start + 2), 16) / 255);
    const linear = channels.map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  };
  const preset = builder.applyDeckStyle(getPreset('editorial-minimal'), { deck_style: {
    composition_grammar: 'editorial-spread', footer_mode: 'source-line', footer_page_numbers: true,
    readability_contract: { min_metadata_pt: 9, min_footer_pt: 9 },
  } }, 'editorial-minimal');
  for (const theme of ['dark', 'light']) {
    const data = { variant: 'kpi-hero', title: 'Format preference', value: '127',
      label: 'of 240 prefer drop-in help', theme, __slideIndex: 4, __slideCount: 7,
      footer: 'SYNTHETIC DATA; not a booking forecast', sources: ['Q3; mutually exclusive preferences'] };
    const ops = [];
    const slide = { addText: (text, options) => ops.push({ text, options }),
      addShape: (shape, options) => ops.push({ shape, options }), addNotes() {} };
    renderers.renderKpiHero({}, slide, data, preset);
    const background = slide.background.color;
    assert.equal(background, theme === 'dark' ? preset.bg_dark : preset.bg);
    const footer = ops.filter((op) => op.options.objectName?.startsWith('metadata:footer-'));
    assert.equal(footer.length, 2);
    assert.ok(footer.some((op) => op.text.includes(data.footer) && op.text.includes(data.sources[0])));
    assert.ok(footer.some((op) => op.text === '4/7'));
    for (const { options } of footer) {
      assert.equal(options.fontSize, 9);
      const [a, b] = [luminance(options.color), luminance(background)];
      assert.ok((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05) >= 4.5, `${theme}: ${options.color}`);
      if (theme === 'light') assert.equal(options.color, preset.text_muted, 'preserve passing light footer color');
    }
  }
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

const LAB_FIGURE = path.resolve(__dirname, '../references/assets/visual_references/lab_trend.jpg');

function captureChartRole(data, preset) {
  const ops = [];
  renderers.renderChart({}, {
    addText: (text, options) => ops.push({ text, options }),
    addShape: (shape, options) => ops.push({ shape, options }),
    addChart: (chart, series, options) => ops.push({ chart, series, options }),
    addNotes: (notes) => ops.push({ notes }),
  }, data, preset);
  return ops;
}

function boundedChartData(variant = 'dense') {
  return builder.normalizeSlide({
    type: 'content', role: 'chart', variant: 'chart', role_layout_variant: variant,
    title: 'Modeled heat reduction',
    subtitle: 'Modeled peak surface-temperature reduction', notes: 'Keep the speaker caveat.',
    chart: { type: 'bar', labels: ['Shade', 'Cool roof', 'Combined', 'Target'], values: [1.8, 2.4, 4.1, 4.5],
      options: { valAxisMinVal: -1, valAxisMaxVal: 6, valAxisMajorUnit: 1 },
      facts: [{ value: '4.1 C', label: 'Combined', detail: 'modeled reduction' },
        { value: '91%', label: 'Of target', detail: 'before field correction' }],
      notes: 'Synthetic planning model for release demonstration; editable native chart.' },
  }, path.resolve(__dirname, '..'));
}

test('bounded chart fallbacks retain complete native evidence and distinct family reading systems', () => {
  const layouts = {};
  for (const grammar of Object.keys(RECIPES)) {
    const data = boundedChartData();
    const before = structuredClone(data);
    const ops = captureChartRole(data, presetFor(grammar, 'Arial', 16));
    const chart = ops.find((op) => op.chart);
    assert.deepEqual(chart.series.map((series) => series.values), [[1.8, 2.4, 4.1, 4.5]]);
    assert.deepEqual(chart.series[0].labels.map(normalized), ['Shade', 'Cool roof', 'Combined', 'Target']);
    for (const key of ['valAxisMinVal', 'valAxisMaxVal', 'valAxisMajorUnit'])
      assert.equal(chart.options[key], before.chart.options[key]);
    assert.ok(chart.options.h + 0.20 >= 1.40 - 1e-6, 'reserved plot region stays at least 1.4 inches');
    const texts = ops.filter((op) => /^content:chart-|^support:chart-register$/.test(op.options?.objectName || ''));
    for (const field of [...before.chart.facts.flatMap((fact) => [fact.value, fact.label, fact.detail]), before.chart.notes]) {
      assert.equal(texts.filter((op) => normalized(op.text) === field).length, 1, `${grammar}: ${field}`);
    }
    for (const { text, options } of texts) {
      assert.ok(options.fontSize >= 16);
      assert.notEqual(options.fit, 'shrink');
      assert.ok(wrapText(text, options.w, options.fontSize, options.fontFace, options.bold).h <= options.h + 1e-6);
      assert.ok(options.x >= 0.50 - 1e-6 && options.x + options.w <= 9.50 + 1e-6);
      assert.ok(options.y + options.h <= 5.07 + 1e-6);
    }
    const boxes = [chart, ...texts].map((op) => op.options);
    for (let i = 0; i < boxes.length; i += 1) for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i]; const b = boxes[j];
      assert.ok(!(Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 1e-6
        && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 1e-6), `${grammar}: overlapping chart readout`);
    }
    assert.ok(ops.some((op) => op.notes?.includes(before.notes)));
    assert.deepEqual(data.chart, before.chart);
    layouts[grammar] = { chart: chart.options, texts, adaptation: data.__roleContractExecution.adaptation };
  }
  const clinical = layouts['clinical-care-pathway'];
  assert.equal(clinical.adaptation, 'readable-chart-clinical-outcomes');
  assert.ok(clinical.texts.find((op) => normalized(op.text) === 'Combined').options.y < clinical.chart.y,
    'clinical lead outcome precedes the plot');
  assert.ok(clinical.texts.find((op) => normalized(op.text) === 'Of target').options.x > clinical.chart.x + clinical.chart.w,
    'clinical secondary outcome remains beside the plot');
  const investor = layouts['investor-thesis-stage'];
  assert.equal(investor.adaptation, 'readable-chart-unit-economics');
  assert.ok(investor.texts.find((op) => normalized(op.text) === 'Combined').options.x < investor.chart.x,
    'investor lead remains a full-height rail');
  assert.ok(investor.texts.find((op) => normalized(op.text) === 'Of target').options.y > investor.chart.y + investor.chart.h,
    'investor secondary readout remains below the plot');
  assert.notDeepEqual(clinical.chart, layouts['consulting-answer-pyramid'].chart);
  assert.notDeepEqual(investor.chart, layouts['technical-telemetry-canvas'].chart);
});

test('fitting chart facts retain original family geometry in primary alternate and dense variants', () => {
  for (const grammar of ['consulting-answer-pyramid', 'clinical-care-pathway', 'investor-thesis-stage', 'technical-telemetry-canvas']) {
    for (const variant of ['primary', 'alternate', 'dense']) {
      const preset = presetFor(grammar, 'Arial', 16);
      const easy = boundedChartData(variant);
      easy.chart.facts = [{ value: '1' }, { value: '2' }];
      easy.facts = easy.chart.facts;
      delete easy.chart.notes;
      delete easy.message;
      easy.__chartPayload = builder.normalizeSlide(easy, path.resolve(__dirname, '..')).__chartPayload;
      const empty = structuredClone(easy);
      empty.chart.facts = [];
      empty.facts = [];
      empty.__chartPayload = builder.normalizeSlide(empty, path.resolve(__dirname, '..')).__chartPayload;
      const baseline = captureChartRole(empty, preset).find((op) => op.chart).options;
      const ops = captureChartRole(easy, preset);
      assert.equal(easy.__roleContractExecution.adaptation, undefined, `${grammar} ${variant}`);
      assert.deepEqual(ops.find((op) => op.chart).options, baseline, `${grammar} ${variant}: original plot geometry`);
    }
  }
});

test('clinical and investor chart fallback mirror semantic columns and reject unreadable source', () => {
  for (const grammar of ['clinical-care-pathway', 'investor-thesis-stage']) {
    const preset = presetFor(grammar, 'Arial', 16);
    for (const variant of ['primary', 'alternate', 'dense']) {
      const data = boundedChartData(variant);
      const ops = captureChartRole(data, preset);
      const chart = ops.find((op) => op.chart).options;
      const rail = ops.find((op) => normalized(op.text) === (grammar === 'clinical-care-pathway' ? 'Of target' : 'Combined')).options;
      const railOnLeft = grammar === 'clinical-care-pathway' ? variant === 'alternate' : variant !== 'alternate';
      assert.ok(railOnLeft ? rail.x < chart.x : rail.x > chart.x + chart.w);
      assert.equal(data.__roleContractExecution.adaptation,
        grammar === 'clinical-care-pathway' ? 'readable-chart-clinical-outcomes' : 'readable-chart-unit-economics');
    }
    const impossible = boundedChartData();
    impossible.chart.facts.forEach((fact) => { fact.detail = 'Keep every measurement and limitation. '.repeat(80); });
    impossible.__chartPayload = builder.normalizeSlide(impossible, path.resolve(__dirname, '..')).__chartPayload;
    assert.throws(() => captureChartRole(impossible, preset), /split the source slide/i);
  }
});

function captureFigureRole(renderer, data, preset) {
  const ops = [];
  const slide = {
    addText: (text, options) => ops.push({ text, options }),
    addShape: (shape, options) => ops.push({ shape, options }),
    addImage: (options) => ops.push({ image: true, options }),
    addNotes() {},
  };
  (renderer === 'renderSlide' ? builder.renderSlide : renderers[renderer])({}, slide, data, preset);
  return ops;
}

function checkMeasuredFigureRole(ops) {
  const named = ops.filter((op) => /^(metadata:|support:)?(scientific:|sidebar:|flow:|caption:flow)/.test(op.options.objectName || ''));
  const content = named.filter((op) => op.text || op.image);
  for (const op of content) {
    const box = op.options;
    assert.notEqual(box.fit, 'shrink');
    assert.ok(box.w > 0 && box.h > 0);
    assert.ok(box.x >= 0.49 && box.x + box.w <= 9.51);
    assert.ok(box.y >= 0 && box.y + box.h <= 5.45, JSON.stringify(box));
    if (op.text) {
      const wrapped = wrapText(plain(op.text), box.w, box.fontSize, box.fontFace, box.bold, true);
      assert.ok(wrapped.h <= box.h + 1e-6, `${box.objectName}: measured text exceeds its box`);
      for (const width of lineWidths(wrapped.text, box.fontSize, box.fontFace, box.bold)) {
        assert.ok(width <= box.w - 0.04 + 1e-6);
      }
    }
  }
  for (let i = 0; i < content.length; i += 1) {
    for (let j = i + 1; j < content.length; j += 1) {
      const a = content[i].options; const b = content[j].options;
      assert.ok(!(Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x) > 0.001
        && Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y) > 0.001),
      `${a.objectName} overlaps ${b.objectName}`);
    }
  }
}

test('modern header measures a long one-line title at its actual font and reserves folded headings before evidence', () => {
  const outline = JSON.parse(fs.readFileSync(path.resolve(__dirname,
    '../examples/v0.14_lab_studies/dark_contrast/outline.json')));
  const name = outline.deck_style.style_preset;
  const preset = builder.applyDeckStyle(getPreset(name), outline, name);
  const source = outline.slides.find((slide) => slide.slide_id === 'con-02');
  const data = { title: source.title, subtitle: source.subtitle, figure_layout: 'panel-grid',
    figures: [{ label: 'A', title: 'Retained evidence', caption: 'Synthetic only.' }], __figurePaths: [LAB_FIGURE] };
  const ops = captureFigureRole('renderScientificFigure', data, preset);
  const title = ops.find((op) => op.text === data.title);
  const subtitle = ops.find((op) => op.options.objectName === 'support:slide-subtitle');
  const body = ops.find((op) => op.options.objectName === 'support:scientific:A:title');
  const measured = wrapText(data.title, title.options.w, title.options.fontSize, title.options.fontFace, true, true);
  assert.equal(measured.text.split('\n').length, 1);
  assert.ok(data.title.length > 42);
  assert.equal(title.options.h, Math.max(0.42, measured.h - 0.07));
  assert.notEqual(title.options.fit, 'shrink');
  assert.ok(subtitle.options.fontSize >= outline.deck_style.readability_contract.min_support_pt);
  assert.ok(subtitle.options.y >= title.options.y + title.options.h + 0.04 - 1e-6);
  assert.ok(body.options.y >= subtitle.options.y + subtitle.options.h + 0.20);
  const legacy = captureFigureRole('renderScientificFigure', structuredClone(data),
    { ...preset, renderer_role_contract_version: 'renderer_role_systems_v1' });
  const oldTitle = legacy.find((op) => op.text === data.title);
  assert.equal(title.options.fontSize, Math.max(oldTitle.options.fontSize, preset.readability_contract.min_title_pt),
    'modern headers respect the declared floor while pinned v1 keeps its original size');
  assert.ok(oldTitle.options.h - title.options.h >= 0.4, 'remove the phantom second line, not actual text');
  const folded = { ...data, title: `${data.title}\nA synthetic extension retains paired denominators` };
  const foldedOps = captureFigureRole('renderScientificFigure', folded, preset);
  const foldedTitle = foldedOps.find((op) => normalized(op.text) === normalized(folded.title));
  const foldedSubtitle = foldedOps.find((op) => op.options.objectName === 'support:slide-subtitle');
  const foldedBody = foldedOps.find((op) => op.options.objectName === 'support:scientific:A:title');
  const measuredFold = wrapText(folded.title, foldedTitle.options.w, foldedTitle.options.fontSize,
    foldedTitle.options.fontFace, true, true);
  assert.ok(measuredFold.text.split('\n').length >= 2);
  assert.ok(foldedTitle.options.fontSize >= preset.readability_contract.min_title_pt);
  assert.equal(foldedTitle.text, measuredFold.text, 'emit the same line breaks used to reserve header height');
  assert.equal(foldedTitle.options.h, measuredFold.h - 0.07);
  assert.ok(foldedBody.options.y > body.options.y);
  assert.ok(foldedSubtitle.options.y >= foldedTitle.options.y + foldedTitle.options.h + 0.04 - 1e-6);
  assert.ok(foldedBody.options.y >= foldedSubtitle.options.y + foldedSubtitle.options.h + 0.20);
  assert.equal(normalized(foldedTitle.text), normalized(folded.title));
  assert.notEqual(foldedTitle.options.fit, 'shrink');
  const orphan = { ...data, title: 'Authorize one dock corridor before citywide scale' };
  const orphanOps = captureFigureRole('renderScientificFigure', orphan, preset);
  const orphanTitle = orphanOps.find((op) => normalized(op.text) === normalized(orphan.title));
  const orphanPlan = wrapText(orphan.title, orphanTitle.options.w, orphanTitle.options.fontSize,
    orphanTitle.options.fontFace, true, true);
  assert.equal(orphanTitle.text, orphanPlan.text);
  assert.equal(normalized(orphanTitle.text), orphan.title);
});

test('all four modern scientific layouts retain four plots, captions and the full readout at readable floors', () => {
  const geometries = [];
  for (const layout of ['panel-grid', 'primary-rail', 'ledger-rail', 'strip-readout']) {
    const preset = presetFor('scientific-evidence-plate', 'Arial', 16, {
      readability_contract: { min_title_pt: 28, min_body_pt: 16, min_support_pt: 14, min_metadata_pt: 10 },
    });
    const data = { title: 'Synthetic study views', figure_layout: layout, caption: 'Synthetic values only.',
      interpretation: 'All denominators retained; prospective validation is required.',
      figures: ['A', 'B', 'C', 'D'].map((label) => ({ label, title: `View ${label}`, caption: `Source ${label}.` })),
      __figurePaths: Array(4).fill(LAB_FIGURE) };
    const source = structuredClone(data);
    const ops = captureFigureRole('renderScientificFigure', data, preset);
    checkMeasuredFigureRole(ops);
    const images = ops.filter((op) => op.image);
    assert.equal(images.length, 4);
    const ratio = images[0].options.w / images[0].options.h;
    assert.ok(images.every((op) => Math.abs(op.options.w / op.options.h - ratio) < 1e-6), 'contain preserves plot aspect ratio');
    for (const figure of data.figures) {
      const title = ops.find((op) => op.options.objectName === `support:scientific:${figure.label}:title`);
      const caption = ops.find((op) => op.options.objectName === `metadata:scientific:${figure.label}:caption`);
      assert.equal(normalized(title.text), `${figure.label}. ${figure.title}`);
      assert.equal(normalized(caption.text), figure.caption);
      assert.ok(title.options.fontSize >= 14 && caption.options.fontSize >= 10);
    }
    const readout = ops.find((op) => op.options.objectName === 'scientific:complete-readout');
    assert.equal(normalized(readout.text), `${data.caption} ${data.interpretation}`);
    assert.ok(readout.options.fontSize >= 16);
    assert.deepEqual(data, source);
    assert.deepEqual(ops, captureFigureRole('renderScientificFigure', structuredClone(source), preset));
    geometries.push(JSON.stringify(images.map(({ options: { x, y, w, h } }) => ({ x, y, w, h }))));
  }
  assert.equal(new Set(geometries).size, 4, 'layout diversity changes geometry, not palette');
});

test('default scientific rendering measures multiline captions and honors slide or preset figure_frame', () => {
  const preset = getPreset('lab-report');
  preset.figure_frame = 'panel';
  const data = { title: 'Synthetic trend', figure_layout: 'primary-rail',
    figures: [{ label: 'A', title: 'Observed response over the entire collection period',
      caption: 'All observations are synthetic. Every collection interval, exclusion and denominator remains visible in this deliberately multiline caption.' }],
    __figurePaths: [LAB_FIGURE], interpretation: 'No clinical claim is established. All collection intervals and exclusions remain visible; this synthetic trend is exploratory and does not establish clinical validity, cohort comparability or causal treatment benefit.' };
  for (const frame of [undefined, 'open', 'ruled', 'panel']) {
    const ops = captureFigureRole('renderScientificFigure', { ...data, figure_frame: frame }, preset);
    checkMeasuredFigureRole(ops);
    const effective = frame || 'panel';
    assert.equal(ops.filter((op) => op.options.objectName === 'scientific:A:frame').length, effective === 'panel' ? 1 : 0);
    assert.equal(ops.filter((op) => op.options.objectName === 'scientific:A:rule').length, effective === 'ruled' ? 1 : 0);
    const caption = ops.find((op) => op.options.objectName === 'metadata:scientific:A:caption');
    assert.equal(normalized(caption.text), data.figures[0].caption);
    assert.ok(caption.options.h > 0.3 && caption.options.fontSize >= 9);
    assert.ok(ops.find((op) => op.options.objectName === 'support:scientific:A:title').options.fontSize >= 13);
    assert.equal(ops.find((op) => op.options.objectName === 'support:scientific:A:title').options.w, 8.84,
      'one primary panel uses the full content width rather than an empty 38 percent rail');
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'scientific:complete-readout').text), data.interpretation);
  }
});

test('scientific overflow and missing or excessive panels fail without silently dropping source', () => {
  const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
  const data = { title: 'Synthetic views', figures: [{ label: 'A', title: 'Trend', caption: 'Full caption.' }],
    __figurePaths: [LAB_FIGURE] };
  for (const layout of ['panel-grid', 'primary-rail', 'ledger-rail', 'strip-readout']) {
    assert.throws(() => captureFigureRole('renderScientificFigure', { ...data, figure_layout: layout,
      interpretation: 'Retain the complete scientific interpretation. '.repeat(90) }, preset), /split the source slide/i);
    assert.throws(() => captureFigureRole('renderScientificFigure', { ...data, figure_layout: layout,
      figures: [{ ...data.figures[0], caption: 'Complete caption with all exclusions. '.repeat(100) }] }, preset), /split the source slide/i);
  }
  assert.throws(() => captureFigureRole('renderScientificFigure', { ...data, __figurePaths: [] }, preset), /missing.*image/);
  assert.throws(() => captureFigureRole('renderScientificFigure', { ...data,
    figures: Array(5).fill(data.figures[0]), __figurePaths: Array(5).fill(LAB_FIGURE) }, preset), /four panels/);
});

test('modern analysis sidebar measures headings and retains every declared sentence, section and reserved note', () => {
  const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
  const data = { title: 'Synthetic assay readout', image_sidebar_mode: 'analysis-rail', __heroPath: LAB_FIGURE, sidebar_body_font_size: 8,
    sidebar_sections: [{ title: 'Collection and exclusion criteria remain explicit',
      body: 'First result. Second result. Third result. Fourth result. Fifth result. Sixth result.' }],
    caption: 'Synthetic fixture caption with the complete collection denominator and all excluded observations. '.repeat(2).trim(),
    interpretation: 'Exploratory only. Retain the complete readout and all cautions.' };
  for (const imageSide of ['left', 'right']) {
    const ops = captureFigureRole('renderImageSidebar', { ...data, image_side: imageSide }, preset);
    checkMeasuredFigureRole(ops);
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'support:sidebar:0:title').text), data.sidebar_sections[0].title);
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'sidebar:0:body').text), data.sidebar_sections[0].body);
    assert.ok(ops.find((op) => op.options.objectName === 'sidebar:0:body').options.fontSize >= 16);
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'metadata:sidebar:caption').text), data.caption);
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'sidebar:complete-readout').text), data.interpretation);
    const image = ops.find((op) => op.image).options;
    const title = ops.find((op) => op.options.objectName === 'support:sidebar:0:title').options;
    assert.equal(image.x < title.x, imageSide === 'left');
  }
  const sparse = { title: 'All declared notes', image_sidebar_mode: 'analysis-rail', sidebar_sections: Array.from({ length: 5 }, (_, i) => ({ title: `Note ${i}`, body: `Keep ${i}.` })) };
  const ops = captureFigureRole('renderImageSidebar', sparse, preset);
  assert.equal(ops.filter((op) => /sidebar:\d+:body/.test(op.options.objectName || '')).length, 5);
  checkMeasuredFigureRole(ops);
  const fallback = captureFigureRole('renderImageSidebar', { title: 'All declared bullets', image_sidebar_mode: 'analysis-rail',
    bullets: Array.from({ length: 6 }, (_, i) => `Result ${i}.`), highlights: ['All cautions retained.'] }, preset);
  assert.ok(normalized(fallback.find((op) => op.options.objectName === 'sidebar:0:body').text).includes('Result 5.'));
  assert.throws(() => captureFigureRole('renderImageSidebar', { ...data,
    sidebar_sections: [{ title: 'All results', body: 'Retain every declared sentence. '.repeat(50) }] }, preset), /split the source slide/i);
});

test('analysis sidebar tries balanced columns only when three complete sections exceed the preferred rail', () => {
  const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
  const data = { title: 'Synthetic three-section readout', image_sidebar_mode: 'analysis-rail', __heroPath: LAB_FIGURE,
    sidebar_sections: [
      { title: 'Collection', body: 'Every interval and excluded observation remains available.' },
      { title: 'Denominator', body: 'All values retain denominators and exclusions for review.' },
      { title: 'Readout', body: 'Keep every observation and excluded interval in the readout.' },
    ] };
  const source = structuredClone(data);
  for (const imageSide of ['left', 'right']) {
    const ops = captureFigureRole('renderImageSidebar', { ...data, image_side: imageSide }, preset);
    checkMeasuredFigureRole(ops);
    data.sidebar_sections.forEach((section, index) => {
      const text = ops.find((op) => op.options.objectName === `sidebar:${index}:body`);
      assert.equal(normalized(text.text), section.body);
      assert.equal(text.options.fontSize, 16);
      assert.ok(Math.abs(text.options.w - (9 * 0.50 - 0.30 - 0.14)) < 1e-6);
      const preferred = wrapText(section.body, 9 * 0.44 - 0.30 - 0.14, 16, preset.font_body);
      assert.ok(preferred.h > text.options.h, 'balanced columns reduce measured height without reducing type');
    });
    const image = ops.find((op) => op.options.objectName === 'sidebar:figure').options;
    assert.ok(image.w <= 4.5 + 1e-6 && image.h > 0, 'full image is contained in the half-width region');
  }
  assert.deepEqual(data, source);
  const easy = { ...data, sidebar_sections: data.sidebar_sections.map((section) => ({ ...section, body: 'Complete result.' })) };
  const ops = captureFigureRole('renderImageSidebar', easy, preset);
  assert.ok(Math.abs(ops.find((op) => op.options.objectName === 'sidebar:0:body').options.w - (9 * 0.44 - 0.30 - 0.14)) < 1e-6,
    'fitting content keeps the preferred 56 percent figure allocation');
  assert.throws(() => captureFigureRole('renderImageSidebar', { ...data,
    sidebar_sections: data.sidebar_sections.map((section) => ({ ...section, body: section.body.repeat(10) })) }, preset), /Split the source slide; no content was dropped/);
});

test('packed analysis sidebar retains the actual three-section study readouts at 16pt without source edits', () => {
  for (const [study, slideIds] of [['dark_contrast', ['con-06']], ['light_river_report', ['riv-02', 'riv-06']]]) {
    const dir = path.resolve(__dirname, '../examples/v0.14_lab_studies', study);
    const file = path.join(dir, 'outline.json');
    const bytes = fs.readFileSync(file);
    const outline = JSON.parse(bytes);
    const name = outline.deck_style.style_preset;
    const preset = builder.applyDeckStyle(getPreset(name), outline, name);
    for (const slideId of slideIds) {
      const index = outline.slides.findIndex((slide) => slide.slide_id === slideId);
      assert.ok(index >= 0);
      const source = outline.slides[index];
      assert.equal(source.sidebar_sections.length, 3);
      const data = builder.normalizeSlide(structuredClone(source), dir);
      Object.assign(data, { __slideIndex: index + 1, __slideCount: outline.slides.length });
      const ops = captureFigureRole('renderSlide', data, preset);
      checkMeasuredFigureRole(ops);
      const paragraphs = ops.filter((op) => /^sidebar:\d+:body$/.test(op.options.objectName || ''));
      assert.equal(paragraphs.length, 3);
      paragraphs.forEach(({ text, options }, i) => {
        const section = source.sidebar_sections[i];
        assert.equal(normalized(text), `${section.title}: ${section.body}`);
        assert.ok(Array.isArray(text));
        assert.equal(text[0].options.bold, true);
        assert.equal(text[0].text, `${section.title}:`);
        assert.ok(text.some((run) => run.options.bold === false));
        assert.equal(options.fontSize, 16);
        assert.notEqual(options.fit, 'shrink');
        assert.ok([0.44, 0.50].some((ratio) => Math.abs(options.w - (9 * ratio - 0.30 - 0.14)) < 1e-6),
          'packed delivery stays within the two bounded column choices');
        const capacity = Math.max(5, Math.floor(Math.max(0.25, options.w - 0.12)
          / Math.max(0.055, options.fontSize / 72 * 0.52)));
        for (const line of plain(text).split('\n')) assert.ok(line.length <= capacity,
          'explicit mixed-weight wraps also retain the conservative delivery capacity');
        for (const width of lineWidths(text, options.fontSize, options.fontFace)) {
          assert.ok(width <= options.w - 0.04 + 1e-6, 'bold prefix is included in line-width measurement');
        }
        if (i) assert.ok(options.y > paragraphs[i - 1].options.y, 'section order is unchanged');
      });
      const caption = ops.find((op) => op.options.objectName === 'metadata:sidebar:caption');
      assert.equal(normalized(caption.text), source.caption);
      const last = paragraphs.at(-1).options;
      assert.ok(caption.options.y - last.y - last.h >= 0.18 - 1e-6, 'caption and footer band has measured clearance');
      const available = caption.options.y - 0.18 - paragraphs[0].options.y;
      for (const ratio of [0.44, 0.50]) {
        const width = 9 * ratio - 0.30 - 0.14;
        const normalHeight = source.sidebar_sections.reduce((sum, section) => sum
          + wrapText(section.title, width, 13, preset.font_heading, true).h
          + wrapText(section.body, width, 16, preset.font_body).h + 0.08, 0) + 0.28;
        assert.ok(normalHeight > available, 'packing is used only after both normal column choices fail');
      }
      assert.equal(ops.filter((op) => op.options.objectName === 'sidebar:figure').length, 1);
      assert.deepEqual(data.sidebar_sections, source.sidebar_sections);
      assert.throws(() => captureFigureRole('renderSlide', { ...data,
        sidebar_sections: source.sidebar_sections.map((section) => ({ ...section, body: `${section.body} `.repeat(30) })) }, preset), /Split the source slide; no content was dropped/);
    }
    assert.ok(bytes.equals(fs.readFileSync(file)), 'example source bytes remain unchanged');
  }
});

test('scientific and sidebar readouts consume summary aliases once; support ink remains readable', () => {
  for (const variant of ['scientific-figure', 'image-sidebar']) {
    for (const alias of ['summary_callout', 'key_summary', 'takeaway']) {
      const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
      const data = { type: 'content', variant, title: 'Synthetic readout', figure_layout: 'primary-rail',
        image_sidebar_mode: 'analysis-rail', [alias]: 'Keep this complete conclusion.', interpretation: 'Independent caveat retained.',
        ...(variant === 'scientific-figure' ? { figures: [{ label: 'A', title: 'Response', caption: 'Synthetic only.' }],
          __figurePaths: [LAB_FIGURE] } : { sidebar_sections: [{ title: 'Result', body: 'Complete result.' }] }) };
      const ops = captureFigureRole('renderSlide', data, preset);
      assert.equal(data.__roleContractConsumesSummary, true);
      const readout = ops.find((op) => op.options.objectName === `${variant === 'scientific-figure' ? 'scientific' : 'sidebar'}:complete-readout`);
      assert.ok(normalized(readout.text).includes(data[alias]));
      assert.ok(normalized(readout.text).includes(data.interpretation));
      assert.equal(ops.filter((op) => op.text && normalized(op.text).includes(data[alias])).length, 1);
      checkMeasuredFigureRole(ops);
    }
  }
  for (const [background, accent, readable] of [['FFFFFF', 'EEEEEE', '111111'], ['111111', '333333', 'FFFFFF']]) {
    const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
    Object.assign(preset, { bg: background, accent_primary: accent, text: readable });
    const ops = captureFigureRole('renderImageSidebar', { title: 'Synthetic readout', image_sidebar_mode: 'analysis-rail',
      sidebar_sections: [{ title: 'Result', body: 'Complete result.' }] }, preset);
    assert.equal(ops.find((op) => op.options.objectName === 'support:sidebar:0:title').options.color, readable);
  }
});

test('explicit v1 scientific layouts and analysis sidebar keep their legacy operations unchanged', () => {
  const preset = getPreset('lab-report');
  preset.renderer_role_contract_version = 'renderer_role_systems_v1';
  const base = { title: 'Synthetic trend', figures: [
    { label: 'A', title: 'Trend', caption: 'Complete caption.' },
    { label: 'B', title: 'Control', caption: 'Control caption.' },
  ], __figurePaths: [LAB_FIGURE, LAB_FIGURE], caption: 'Synthetic only.', interpretation: 'Exploratory pattern.' };
  const hashes = {
    'panel-grid': '817e3b6c5f16937a4a385b779f3f23fd18f00dd063c05935f3a191af4841934a',
    'primary-rail': '5b6e25cc01d002a5cf90adef6d19485a4713591ef548c36e2fd04e41cd3dab6f',
    'ledger-rail': '41faf06fa65ef25d9783dd950dd9813818ec16e7a51c8773cae92da871e045b6',
    'strip-readout': '42d6ca88d4e25a55ac37758db72990dabf2abda787115b1c3724ea3aa7a18644',
  };
  // Image filenames are normalized so the frozen operations travel with the repo.
  const hash = (ops) => crypto.createHash('sha256').update(JSON.stringify(ops).replaceAll(LAB_FIGURE, 'lab_trend.jpg')).digest('hex');
  for (const [layout, expected] of Object.entries(hashes)) {
    assert.equal(hash(captureFigureRole('renderScientificFigure', { ...base, figure_layout: layout }, preset)), expected);
  }
  assert.equal(hash(captureFigureRole('renderImageSidebar', { title: 'Synthetic trend', image_sidebar_mode: 'analysis-rail',
    __heroPath: LAB_FIGURE, sidebar_sections: [{ title: 'Results', body: 'First result. Second result.' }],
    caption: 'Synthetic only.' }, preset)), '9c734135f949a5b0d06a5a5c7d9326a98b62d5ba36127b42c0bd88f266c04891');
});

test('native flow retains two and four ordered strip stages with equal rectangles and measured text', () => {
  const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
  for (const count of [2, 4]) {
    const steps = Array.from({ length: count }, (_, i) => ({ title: `Stage ${i + 1}`, detail: `Retain result ${i + 1}.` }));
    const data = { title: 'Synthetic method', flow_steps: steps, flow_layout: 'strip',
      caption: 'Synthetic workflow only.', summary_callout: 'No clinical validation is implied.' };
    const ops = captureFigureRole('renderFlow', data, preset);
    checkMeasuredFigureRole(ops);
    assert.equal(ops.filter((op) => op.image).length, 0, 'native flow remains editable');
    const titles = ops.filter((op) => /^flow:\d+:title$/.test(op.options.objectName || ''));
    assert.deepEqual(titles.map((op) => normalized(op.text)), steps.map((step) => step.title));
    const boxes = titles.map(({ options: title }) => ops.find((op) => op.shape === 'rect'
      && Math.abs(op.options.x + 0.14 - title.x) < 1e-6 && Math.abs(op.options.y + 0.40 - title.y) < 1e-6).options);
    for (const box of boxes) assert.deepEqual([box.y, box.w, box.h], [boxes[0].y, boxes[0].w, boxes[0].h]);
    assert.ok(boxes.every((box, i) => !i || box.x > boxes[i - 1].x + boxes[i - 1].w));
    steps.forEach((step, i) => assert.equal(normalized(ops.find((op) => op.options.objectName === `flow:${i}:detail`).text), step.detail));
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'flow:readout').text), data.summary_callout);
    assert.equal(normalized(ops.find((op) => op.options.objectName === 'caption:flow').text), data.caption);
    assert.deepEqual(data.flow_steps, steps);
  }
});

test('native flow explicit bands and auto long-token fallback preserve source order and complete detail', () => {
  const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
  const steps = ['Collect', 'Measure', 'Review', 'Release'].map((title) => ({ title,
    detail: 'Electrochemiluminescence readout retained.' }));
  for (const layout of ['bands', 'auto']) {
    const ops = captureFigureRole('renderFlow', { title: 'Synthetic method bands', flow_steps: steps, flow_layout: layout }, preset);
    checkMeasuredFigureRole(ops);
    const titles = ops.filter((op) => /^flow:\d+:title$/.test(op.options.objectName || ''));
    assert.deepEqual(titles.map((op) => normalized(op.text)), steps.map((step, i) => `${i + 1}. ${step.title}`));
    assert.ok(titles.every((op, i) => !i || op.options.y > titles[i - 1].options.y));
    assert.ok(titles.every((op) => op.options.x === titles[0].options.x));
    assert.equal(ops.filter((op) => op.image).length, 0);
    steps.forEach((step, i) => assert.equal(normalized(ops.find((op) => op.options.objectName === `flow:${i}:detail`).text), step.detail));
  }
});

test('native flow invalid counts and impossible strip or bands throw instead of losing steps', () => {
  const preset = presetFor('scientific-evidence-plate', 'Arial', 16);
  const data = { title: 'Impossible method' };
  for (const count of [1, 5]) assert.throws(() => captureFigureRole('renderFlow', { ...data,
    flow_steps: Array(count).fill({ title: 'Collect' }) }, preset), /2-4 ordered stages/);
  for (const layout of ['strip', 'bands', 'auto']) {
    assert.throws(() => captureFigureRole('renderFlow', { ...data, flow_layout: layout,
      flow_steps: Array(4).fill({ title: 'Complete stage', detail: 'Retain every measurement. '.repeat(60) }) }, preset), /split; no steps were dropped/);
  }
  assert.throws(() => captureFigureRole('renderFlow', { ...data, flow_layout: 'strip',
    flow_steps: Array(4).fill({ title: 'Measure', detail: 'Electrochemiluminescence' }) }, preset), /wider text box/);
});

test('default v2 policy content preserves narrow labels and value-free evidence without shrinking', () => {
  const name = 'warm-terracotta';
  const outline = { deck_style: {} };
  const preset = builder.applyDeckStyle(getPreset(name), outline, name);
  const data = { type: 'content', variant: 'matrix', title: 'Museum membership renewal',
    quadrants: ['High empathy', 'High effort', 'Caveat/Date', 'Low burden'].map((title) => ({ title, body: 'Guide cue.' })) };
  const ops = capture(data, preset);
  for (const item of data.quadrants.slice(1)) {
    const heading = ops.find((op) => op.text && normalized(op.text) === item.title);
    assert.ok(heading, item.title);
    const { options } = heading;
    const measured = wrapText(item.title, options.w, options.fontSize, options.fontFace, true, true);
    assert.ok(options.h >= measured.h, item.title);
    assert.notEqual(options.fit, 'shrink');
    for (const width of lineWidths(heading.text, options.fontSize, options.fontFace, true)) assert.ok(width <= options.w);
  }
  const cards = { type: 'content', role: 'evidence', variant: 'cards-2', title: 'Methods and evidence split',
    cards: [{ title: 'Method Context', body: 'Sample identifiers, assay conditions, and run metadata stay in structured fields.' },
      { title: 'Evidence Rule', body: 'Long provenance moves to references while short IDs remain in the footer.' }] };
  const evidence = captureFigureRole('renderSlide', cards, preset).filter((op) => op.text);
  const visible = evidence.map((op) => normalized(op.text));
  assert.ok(!visible.includes('01'), 'value-free source must not acquire a numeric evidence anchor');
  for (const card of cards.cards) {
    assert.ok(visible.some((text) => text.includes(card.title)));
    assert.ok(visible.some((text) => text.includes(card.body)));
  }
});

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
