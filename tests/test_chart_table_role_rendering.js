'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const builder = require('../scripts/build_deck_pptxgenjs.js');
const renderers = require('../templates/pptxgenjs/slides.js');
const { getPreset } = require('../templates/pptxgenjs/presets.js');
const { wrapText } = require('../templates/pptxgenjs/readable_role_layouts.js');

const GRAMMARS = Object.keys(require('../references/renderer_role_contracts_v2.json').grammars);
// Frozen caption from the clean-lab source; tests do not require local decks.
const LAB_CAPTION = 'Total: 72 assay wells (3 lots x 4 timepoints x 6 wells), excluding blanks. Synthetic values.';

const STYLES = ['midnight-neon', 'editorial-minimal', 'lavender-ops'];
const INTERPRETATION = 'Uptime measures device availability; it does not establish measurement accuracy.';
const normalizedText = (value) => String(value).replace(/\s+/g, ' ').trim();

function presetFor(name, grammar) {
  return builder.applyDeckStyle(getPreset(name), { deck_style: {
    style_preset: name,
    ...(grammar ? { composition_grammar: grammar } : {}),
    readability_contract: {
      min_title_pt: 28,
      min_body_pt: 16,
      min_support_pt: 13,
      min_caption_pt: 9,
      min_metadata_pt: 9,
      min_footer_pt: 9,
    },
  } }, name);
}

function capture(renderer, data, preset, ...args) {
  const operations = [];
  const slide = {
    addText: (text, options) => operations.push({ kind: 'text', text, options }),
    addShape: (shape, options) => operations.push({ kind: 'shape', shape, options }),
    addTable: (rows, options) => operations.push({ kind: 'table', rows, options }),
    addChart: (type, series, options) => operations.push({ kind: 'chart', type, series, options }),
    addImage: (options) => operations.push({ kind: 'image', options }),
    addNotes() {},
  };
  renderer({ ChartType: { bar: 'bar' } }, slide, data, preset, ...args);
  return operations;
}

test('v2 scientific rails retain every declared caption and the complete interpretation', () => {
  const image = path.join(__dirname, '../references/assets/visual_references/lab_trend.jpg');
  for (const layout of ['primary-rail', 'ledger-rail']) {
    const preset = presetFor('lab-report', 'scientific-evidence-plate');
    const data = { type: 'content', variant: 'scientific-figure', title: 'Three views of the same study',
      figure_layout: layout, caption: 'Synthetic operating figure; no customer data.',
      interpretation: 'Enterprise saves offset backlog, but legal owner remains the risk.',
      figures: [
        { label: 'A', title: 'Signal trend', caption: 'Synthetic operating figure; no customer data.' },
        { label: 'B', title: 'Comparison readout', caption: 'Generated fixture.' },
        { label: 'C', title: 'State model', caption: 'No external asset.' },
      ], __figurePaths: [image, image, image] };
    const source = structuredClone(data);
    const ops = capture(renderers.renderScientificFigure, data, preset);
    const texts = ops.filter((op) => op.kind === 'text');
    const visible = texts.map((op) => typeof op.text === 'string' ? op.text : '').join('\n');
    for (const figure of data.figures) {
      assert.ok(visible.includes(`${figure.label}. ${figure.title}`), `${layout}: ${figure.label} title`);
      assert.ok(visible.includes(figure.caption), `${layout}: full ${figure.label} caption`);
    }
    assert.ok(visible.includes(data.interpretation), `${layout}: complete interpretation`);
    assert.equal(ops.filter((op) => op.kind === 'image').length, 3);
    assert.ok(texts.filter((op) => op.options.objectName === 'scientific:complete-readout')
      .every((op) => op.options.fit !== 'shrink' && op.options.fontSize >= 16));
    assert.deepEqual(data.figures, source.figures);
    assert.equal(data.interpretation, source.interpretation);
  }
});

function chartData() {
  return {
    type: 'content', role: 'chart', variant: 'chart', title: 'Availability improved through the pilot',
    chart: {
      type: 'bar',
      series: [{ name: 'Uptime (%)', labels: ['Week 1', 'Week 12'], values: [82, 97] }],
      facts: [{ value: '+15 pp', label: 'Availability gain' }],
    },
    interpretation: INTERPRETATION,
    sources: ['D1'],
  };
}

function tableData() {
  return {
    type: 'content', role: 'table', variant: 'table', title: 'The budget protects coverage and review',
    table: {
      headers: ['Workstream', 'Budget', 'Owner', 'Output'],
      rows: [
        ['Equipment', '$22k', 'Field team', '24 calibrated sensors'],
        ['Analysis', '$10k', 'Research', 'Quality and coverage report'],
      ],
      column_weights: [0.23, 0.14, 0.23, 0.40],
    },
    interpretation: 'Analysis funding is reserved before installation begins.',
    sources: ['D1'],
  };
}

test('native value labels retain fractions and compact bar categories reflow without changing content', () => {
  const data = chartData();
  data.chart.series = [{ name: 'Hours', labels: ['Connector suspected', 'Controller restart', 'Transfer delay', 'Planned inspection'],
    values: [4.5, 1.5, 1, 0.5] }];
  data.chart.options = { showValue: true };
  const before = structuredClone(data);
  const chart = capture(renderers.renderChart, data, presetFor('lavender-ops', 'operations-grid'))
    .find((operation) => operation.kind === 'chart');
  assert.equal(chart.options.dataLabelFormatCode, 'General');
  assert.deepEqual(chart.series[0].values, before.chart.series[0].values);
  assert.deepEqual(chart.series[0].labels.map((label) => label.replace(/\s+/g, ' ')), before.chart.series[0].labels);
  assert.ok(chart.series[0].labels.every((label) => label.includes('\n')));
  assert.deepEqual(data.chart, before.chart);
  data.chart.options.dataLabelFormatCode = '0.00';
  const explicit = capture(renderers.renderChart, data, presetFor('lavender-ops', 'operations-grid'))
    .find((operation) => operation.kind === 'chart');
  assert.equal(explicit.options.dataLabelFormatCode, '0.00');
});

test('anonymous decision bullets use neutral labels while explicit recipe slots retain their names', () => {
  const cases = [
    ['lab-report', 'scientific-evidence-plate', [
      'Advance 5% v/v glycerol to a compatibility-first confirmation study.',
      'Keep the evidence unit at the lot; report all failures and raw rates.',
      'Do not authorize production release, clinical use, or a shelf-life label.',
    ]],
    ['editorial-minimal', 'editorial-spread', [
      'Check vessel, berth, crew, and return-leg feasibility before any trial.',
      'Measure arrivals, boardings, and timestamped waits separately; keep early riders in the evaluation.',
      'The remaining 60 people require another answer: more capacity, later service, or a different design.',
    ]],
  ];
  const normalize = (text) => (Array.isArray(text) ? text.map((run) => run.text).join('') : String(text)).replace(/\s+/g, ' ').trim();
  for (const [style, grammar, bullets] of cases) {
    for (const explicit of [false, true]) {
      const titles = explicit ? ['Proposal', 'Evidence Trigger', 'Owner'] : ['Decision', 'Detail 1', 'Detail 2'];
      const data = { role: 'decision', variant: 'standard', title: 'Next decision', bullets: [...bullets],
        ...(grammar === 'editorial-spread' ? { role_layout_variant: 'alternate' } : {}),
        summary_callout: 'This proposed next step is not an authorization.',
        ...(explicit ? { content_recipe: { required_slots: titles } } : {}) };
      const before = structuredClone(data);
      const ops = capture(renderers.renderStandard, data, presetFor(style, grammar));
      const fields = ops.filter((op) => op.kind === 'text' && /^decision:\d+:/.test(op.options.objectName));
      const visible = fields.map((op) => normalize(op.text)).join(' ');
      for (const bullet of bullets) assert.ok(visible.includes(bullet), `${style}: complete source retained`);
      for (const title of titles) {
        const field = fields.find((op) => normalize(op.text).includes(title));
        assert.ok(field && field.options.fontSize >= 16 && field.options.fit !== 'shrink', `${style}: readable ${title}`);
      }
      if (!explicit) assert.doesNotMatch(visible, /Evidence Trigger|Owner|Timing \/ Caveat/);
      assert.deepEqual(data.bullets, before.bullets);
      assert.deepEqual(data.content_recipe, before.content_recipe);
      if (grammar === 'editorial-spread') {
        const slots = ops.filter((op) => op.kind === 'shape' && /^role-contract-slot:decision:\d+$/.test(op.options.objectName));
        const readingOrder = [...slots].sort((a, b) => a.options.x - b.options.x || a.options.y - b.options.y);
        assert.deepEqual(readingOrder.map((op) => op.options.objectName),
          ['role-contract-slot:decision:0', 'role-contract-slot:decision:1', 'role-contract-slot:decision:2']);
        assert.ok(fields.every((op) => op.options.x >= 0.70), 'decision clears the editorial left rail');
      }
    }
  }
});

test('normalizer retains string facts as labels without inventing numeric values', () => {
  const labels = ['Pilot availability measure; not a measure of gardening outcomes.', '72% availability'];
  for (const key of ['facts', 'stats']) {
    const source = { type: 'content', variant: 'stats', [key]: [...labels, { value: 0, label: 'Recorded zero' }] };
    const before = structuredClone(source);
    const normalized = builder.normalizeSlide(source, process.cwd());
    assert.deepEqual(normalized[key].slice(0, 2), labels.map((label) => ({ label })));
    assert.ok(normalized[key].slice(0, 2).every((fact) => !Object.hasOwn(fact, 'value')));
    assert.deepEqual(normalized[key][2], source[key][2]);
    assert.deepEqual(source, before, 'normalization must not mutate the authored source');
  }
  for (const key of ['facts', 'stats']) {
    const source = chartData();
    source.interpretation = '';
    delete source.chart.facts;
    source.chart[key] = labels;
    const before = structuredClone(source);
    const normalized = builder.normalizeSlide(source, process.cwd());
    assert.deepEqual(normalized.__chartPayload.facts, labels.map((label) => ({ label })));
    assert.deepEqual(normalized.facts, normalized.__chartPayload.facts);
    assert.deepEqual(source, before);
    const ops = capture(renderers.renderChart, normalized, presetFor('lab-report'));
    for (const label of labels) assert.ok(ops.some((op) => op.kind === 'text' && op.text === label), label);
  }
});

test('ordinary table retains the lab caption and every footnote alongside a readout', () => {
  for (const grammar of GRAMMARS) {
    for (const readout of ['', 'Retain all lots pending validation.']) {
      const data = tableData();
      data.table.caption = LAB_CAPTION;
      data.interpretation = readout;
      data.table.footnotes = ['Technical wells are not independent lots.', 'Blanks remain excluded from n=72.'];
      const ops = capture(renderers.renderTable, data, presetFor('lab-report', grammar));
      const caption = ops.find((op) => op.options?.objectName === 'metadata:table-caption');
      assert.ok(caption, `${grammar}: caption must stay visible with readout=${Boolean(readout)}`);
      for (const text of [data.table.caption, ...data.table.footnotes]) assert.ok(caption.text.includes(text));
      assert.ok(caption.options.fontSize >= 9);
      assert.notEqual(caption.options.fit, 'shrink');
      const table = ops.find((op) => op.kind === 'table');
      assert.ok(caption.options.y - (table.options.y + table.options.h) >= 0.05);
      assert.ok(caption.options.h >= wrapText(caption.text, caption.options.w,
        caption.options.fontSize, caption.options.fontFace, false, true).h);
      if (readout) assert.ok(ops.some((op) => op.kind === 'text' && normalizedText(op.text) === normalizedText(readout)));
    }
  }
});

test('table readout must not consume a distinct takeaway or overflow by shrinking notes', () => {
  const data = tableData();
  data.table.caption = LAB_CAPTION;
  data.caption = 'Generated analysis source: assay_readout.csv; columns Sample, Signal, Ct.';
  data.takeaway = 'Do not expand until independent validation is complete.';
  const preset = presetFor('lab-report', 'scientific-evidence-plate');
  const ops = capture(renderers.renderTable, data, preset);
  assert.notEqual(data.__roleContractConsumesSummary, true);
  assert.ok(ops.some((op) => normalizedText(op.text) === normalizedText(data.interpretation)));
  assert.ok(ops.some((op) => String(op.text).includes(data.caption)));
  const labData = { ...data, variant: 'lab-run-results', tables: [data.table] };
  assert.ok(capture(renderers.renderLabRunResults, labData, preset)
    .some((op) => String(op.text).includes(data.caption)));
  data.table.footnotes = ['A complete source caveat. '.repeat(500)];
  assert.throws(() => capture(renderers.renderTable, data, preset), /table.*split the source slide/i);
});

for (const style of STYLES) {
  test(`${style} chart preserves readable fact and interpretation text`, () => {
    const data = chartData();
    const operations = capture(renderers.renderChart, data, presetFor(style));
    const text = operations.filter((op) => op.kind === 'text');
    const interpretation = text.find((op) => op.text === INTERPRETATION);
    const fact = text.find((op) => String(op.text).includes('Availability gain'));
    assert.ok(interpretation, 'interpretation must be rendered in full');
    assert.ok(fact, 'fact label must be rendered in full');
    assert.ok(interpretation.options.fontSize >= 16);
    assert.ok(fact.options.fontSize >= 16);
    assert.ok(interpretation.options.w >= 2.75);
    assert.notEqual(interpretation.options.align, 'center');
    assert.equal(operations.find((op) => op.kind === 'chart').options.valAxisMinVal, 0);
  });

  test(`${style} ordinary table measures readout within its family geometry`, () => {
    const data = tableData();
    const preset = presetFor(style);
    preset.readability_contract.min_support_pt = 16;
    const operations = capture(renderers.renderTable, data, preset);
    const readout = operations.find((op) => op.kind === 'text' && normalizedText(op.text) === normalizedText(data.interpretation));
    assert.ok(readout, 'ordinary table readout must be rendered in full');
    assert.ok(readout.options.fontSize >= 16);
    assert.ok(readout.options.h >= wrapText(readout.text, readout.options.w,
      readout.options.fontSize, readout.options.fontFace, false, true).h);
    assert.notEqual(readout.options.fit, 'shrink');
    assert.equal(data.__roleContractExecution.adaptation, 'measured-table-contract-geometry');
  });
}

test('all eight ordinary table contracts retain native cells and 13pt support without a universal band', () => {
  const { contractsForGrammar } = require('../templates/pptxgenjs/role_layout_contracts');
  const styles = ['arctic-minimal', 'lab-report', 'executive-clinical', 'editorial-minimal',
    'sunset-investor', 'lavender-ops', 'warm-terracotta', 'midnight-neon'];
  const geometries = new Set();
  GRAMMARS.forEach((grammar, index) => {
    const style = styles[index];
    const preset = builder.applyDeckStyle(getPreset(style), { metadata: {
      renderer_role_contracts_v2: contractsForGrammar(grammar, style),
    } }, style);
    for (const variant of ['primary', 'alternate', 'dense']) {
      const data = tableData();
      data.role_layout_variant = variant;
      data.table.caption = LAB_CAPTION;
      const source = structuredClone(data.table);
      const ops = capture(renderers.renderTable, data, preset);
      const native = ops.find((op) => op.kind === 'table');
      assert.deepEqual(native.rows.map((row) => row.map((cell) => cell.text)), [source.headers, ...source.rows]);
      const readout = ops.find((op) => normalizedText(op.text) === normalizedText(data.interpretation));
      assert.ok(readout.options.fontSize >= 13, `${grammar}/${variant}`);
      assert.notEqual(readout.options.fit, 'shrink');
      const caption = ops.find((op) => op.options?.objectName === 'metadata:table-caption');
      assert.ok(caption.text.includes(source.caption));
      assert.ok(caption.options.y >= native.options.y + native.options.h + 0.05);
      assert.notEqual(caption.options.fit, 'shrink');
      assert.ok(ops.some((op) => String(op.text).includes('D1')));
      if (variant === 'primary') geometries.add(JSON.stringify([
        native.options.x, native.options.y, native.options.w, native.options.h,
        readout.options.x, readout.options.y, readout.options.w, readout.options.h,
      ].map((value) => Math.round(value * 100))));
    }
  });
  assert.equal(geometries.size, 8);
  const outline = JSON.parse(fs.readFileSync(path.resolve(__dirname,
    '../examples/v0.14_lab_studies/white_calibration/outline.json')));
  for (const style of ['lab-report', 'editorial-minimal']) {
    const data = builder.normalizeSlide(outline.slides.find((slide) => slide.variant === 'table'),
      path.resolve(__dirname, '..'));
    const preset = builder.applyDeckStyle(getPreset(style), { ...outline, deck_style: {
      ...outline.deck_style, style_preset: style,
      composition_grammar: style === 'lab-report' ? 'scientific-evidence-plate' : 'editorial-spread',
    } }, style);
    const ops = capture(renderers.renderTable, data, preset);
    const native = ops.find((op) => op.kind === 'table');
    assert.deepEqual(native.rows.map((row) => row.map((cell) => cell.text)), [data.table.headers, ...data.table.rows]);
    assert.ok(native.rows.flat().every((cell) => cell.options.fontSize >= 16));
    const caption = ops.find((op) => op.options?.objectName === 'metadata:table-caption');
    assert.ok(caption.options.y >= native.options.y + native.options.h + 0.05);
  }
});

test('bar axes include zero by default while honoring explicit limits', () => {
  for (const [values, options, expected] of [
    [[-90, -70], {}, { valAxisMaxVal: 0 }],
    [[-10, 90], {}, {}],
    [[82, 97], { valAxisMinVal: 70, valAxisMaxVal: 100 }, { valAxisMinVal: 70, valAxisMaxVal: 100 }],
  ]) {
    const data = chartData();
    data.chart.series[0].values = values;
    data.chart.options = options;
    const chart = capture(renderers.renderChart, data, presetFor('lab-report')).find((op) => op.kind === 'chart');
    for (const key of ['valAxisMinVal', 'valAxisMaxVal']) assert.equal(chart.options[key], expected[key]);
  }
});

test('native charts show supplied axis titles unless explicitly hidden', async () => {
  const PptxGenJS = require('pptxgenjs');
  const JSZip = require('jszip');
  const preset = presetFor('lab-report', 'scientific-evidence-plate');
  for (const hidden of [false, true]) {
    const data = chartData();
    data.chart.options = { catAxisTitle: 'Storage day', valAxisTitle: '% of day-0 mean', showValue: true,
      ...(hidden ? { dataLabelFontSize: 11 } : {}),
      ...(hidden ? { showCatAxisTitle: false, showValAxisTitle: false } : {}) };
    const chart = capture(renderers.renderChart, data, preset).find((op) => op.kind === 'chart');
    assert.equal(chart.options.showCatAxisTitle, !hidden);
    assert.equal(chart.options.showValAxisTitle, !hidden);
    assert.equal(chart.options.dataLabelFontSize, hidden ? 11 : 10);
    const pptx = new PptxGenJS();
    pptx.layout = 'LAYOUT_16x9';
    renderers.renderChart(pptx, pptx.addSlide(), data, preset);
    const zip = await JSZip.loadAsync(await pptx.write({ outputType: 'nodebuffer' }));
    const xml = await zip.file(/^ppt\/charts\/chart\d+\.xml$/)[0].async('string');
    assert.equal(xml.includes('Storage day'), !hidden);
    assert.equal(xml.includes('% of day-0 mean'), !hidden);
    const labels = xml.match(/<c:dLbls>[\s\S]*?<\/c:dLbls>/)?.[0];
    assert.ok(labels?.includes(`sz="${hidden ? 1100 : 1000}"`), 'native data labels use the explicit readable size');
  }
  const chart = capture(renderers.renderChart, chartData(), preset).find((op) => op.kind === 'chart');
  assert.equal(chart.options.showCatAxisTitle, false);
  assert.equal(chart.options.showValAxisTitle, false);
});

test('dense lab chart recovers inter-band whitespace without shrinking facts or the plot', () => {
  const data = builder.normalizeSlide({
    type: 'content', role: 'chart', variant: 'chart', role_layout_variant: 'dense',
    title: 'The combined intervention is expected to close most of the heat gap',
    subtitle: 'Modeled peak surface-temperature reduction',
    chart: { type: 'bar', labels: ['Shade', 'Cool roof', 'Combined', 'Target'], values: [1.8, 2.4, 4.1, 4.5],
      facts: [{ value: '4.1 C', label: 'Combined', detail: 'modeled reduction' },
        { value: '91%', label: 'Of target', detail: 'before field correction' }] },
    caption: 'Illustrative model values; not a public performance claim.',
    footer: 'Urban heat resilience pilot | Evidence Plate',
  }, path.resolve(__dirname, '..'));
  const ops = capture(renderers.renderChart, data, presetFor('lab-report', 'scientific-evidence-plate'));
  const chart = ops.find((op) => op.kind === 'chart').options;
  assert.ok(chart.h >= 1.20 - 1e-6, 'preserve 1.40in plot region before internal padding');
  for (const fact of data.chart.facts) {
    for (const text of [fact.value, fact.label, fact.detail]) {
      const box = ops.find((op) => op.text === text)?.options;
      assert.ok(box && box.fontSize >= 16 && box.fit !== 'shrink', text);
      assert.ok(box.y >= chart.y + chart.h + 0.09 - 1e-6, text);
    }
  }
  const caption = ops.find((op) => op.text === data.caption).options;
  const factBottom = Math.max(...ops.filter((op) => op.options.objectName?.startsWith('content:chart-fact-'))
    .map((op) => op.options.y + op.options.h));
  assert.ok(caption.y >= factBottom + 0.09 - 1e-6, 'retain visible fact/caption separation');
});

test('editorial chart fills its sidecar with complete measured fact heads and details', () => {
  const data = chartData();
  data.role_layout_variant = 'alternate';
  delete data.interpretation;
  data.facts = [
    { value: '540', label: 'Arrivals per evening', detail: '5,400 across 10 identical synthetic evenings' },
    { value: '47%', label: '18:00-19:00 share', detail: '255 / 540 = 47.2%, rounded' },
  ];
  delete data.chart.facts;
  data.chart.series = [
    { name: 'Arrivals (people)', labels: ['17:00-17:30', '17:30-18:00', '18:00-18:30', '18:30-19:00', '19:00-19:30', '19:30-20:00'], values: [40, 65, 110, 145, 105, 75] },
    { name: 'Baseline offered places', labels: ['17:00-17:30', '17:30-18:00', '18:00-18:30', '18:30-19:00', '19:00-19:30', '19:30-20:00'], values: [80, 80, 80, 80, 80, 80] },
  ];
  data.chart.options = { showValue: true };
  const chartSource = structuredClone(data.chart);
  data.caption = 'Ten deliberately identical evenings are a constructed case, not a sampled estimate. Six 80-place releases offer 480 places per evening. No day-to-day variability or uncertainty interval is implied.';
  const ops = capture(renderers.renderChart, data, presetFor('editorial-minimal', 'editorial-spread'));
  const plot = ops.find((op) => op.kind === 'chart').options;
  assert.equal(data.__roleContractExecution.adaptation, 'readable-chart-sidecar');
  for (const fact of data.facts) {
    const value = ops.find((op) => op.text === fact.value).options;
    const label = ops.find((op) => op.text === fact.label).options;
    const detail = ops.find((op) => op.text === fact.detail).options;
    assert.equal(value.y, label.y, 'compact fact head');
    assert.ok(value.x >= 0.70 && detail.x >= 0.70, 'sidecar clears the editorial left rail');
    assert.ok(label.x - value.x - value.w >= 0.18 - 1e-6, 'value and heading have a real gutter');
    assert.ok(detail.y >= label.y + label.h + 0.09);
    assert.ok(detail.x + detail.w <= plot.x - 0.10, 'vacant plot-side region becomes visible readout');
  }
  assert.equal(plot.dataLabelFontSize, 10);
  assert.equal(plot.barOverlapPct, -60, 'native clustered bars separate adjacent value labels');
  assert.equal(plot.barGapWidthPct, 100, 'retain readable bar widths while separating series');
  const rendered = ops.find((op) => op.kind === 'chart');
  assert.deepEqual(rendered.series, chartSource.series);
  assert.deepEqual(data.chart, chartSource);
  const preset = presetFor('editorial-minimal', 'editorial-spread');
  data.chart.options = { showValue: true, barOverlapPct: 0, barGapWidthPct: 150 };
  const explicit = capture(renderers.renderChart, data, preset).find((op) => op.kind === 'chart').options;
  assert.equal(explicit.barOverlapPct, 0);
  assert.equal(explicit.barGapWidthPct, 150);
  data.chart.options = { showValue: true, barGrouping: 'stacked' };
  const stacked = capture(renderers.renderChart, data, preset).find((op) => op.kind === 'chart').options;
  assert.equal(stacked.barGrouping, 'stacked');
  assert.equal(stacked.barOverlapPct, undefined, 'do not separate a declared stacked chart');
  const legacy = capture(renderers.renderChart, data, { ...preset, renderer_role_contract_version: 'renderer_role_systems_v1' })
    .find((op) => op.kind === 'chart').options;
  assert.equal(legacy.barOverlapPct, undefined, 'archived v1 spacing untouched');
});

test('v2 editorial comparison and table keep complete source clear of the left page spine', () => {
  const preset = presetFor('editorial-minimal', 'editorial-spread');
  const data = { type: 'content', role: 'comparison', variant: 'comparison-2col', role_layout_variant: 'alternate',
    title: 'Move one release, not the whole promise', subtitle: 'The same 480 places, distributed differently',
    left: { title: 'Even spacing', bullets: ['Six releases of 80 places; one after every interval.', '425 boardings; 55 places unused early.', '115 people remain at 20:00.'] },
    right: { title: 'One release moved to 19:00', bullets: ['Omit 17:30; offer two 80-place releases at 19:00.', '480 boardings; no unused places in this model.', '60 people remain; the first queue rises to 40.'] },
    verdict: '55 more boardings per evening, but no added places and no elimination of the queue.',
  };
  const before = structuredClone(data);
  const ops = capture(renderers.renderComparison2col, data, preset);
  const panels = ops.filter((op) => /^role-contract-slot:comparison:option-/.test(op.options.objectName));
  assert.ok(Math.min(...panels.map((op) => op.options.x)) >= 0.70);
  for (const option of [data.left, data.right]) {
    for (const text of [option.title, option.bullets.join('\n')]) {
      const field = ops.find((op) => op.kind === 'text' && normalizedText(op.text) === normalizedText(text));
      assert.ok(field && field.options.x >= 0.74 && field.options.fontSize >= 16);
      assert.notEqual(field.options.fit, 'shrink');
    }
  }
  assert.deepEqual(data.left, before.left);
  assert.deepEqual(data.right, before.right);
  const table = tableData();
  table.role_layout_variant = 'alternate';
  table.table.caption = LAB_CAPTION;
  const tableOps = capture(renderers.renderTable, table, preset);
  assert.ok(tableOps.find((op) => op.kind === 'table').options.x >= 0.70);
  assert.ok(tableOps.find((op) => op.options.objectName === 'metadata:table-caption').options.x >= 0.70);
});

test('v2 editorial timeline gives its focus label, heading and body equal safe insets', () => {
  const data = { type: 'content', role: 'evidence', variant: 'timeline', role_layout_variant: 'alternate',
    title: "A queue becomes the evening's clock",
    subtitle: 'Three moments in the synthetic baseline, not eyewitness reporting',
    milestones: [
      { label: '17:30', title: 'Seats go unused', body: 'The first release boards 40 of 80 places. Spare seats cannot be carried forward.' },
      { label: '19:00', title: 'The wave arrives', body: 'The 18:30-19:00 interval adds 145 arrivals. After boarding, 95 people remain in the queue.' },
      { label: '20:00', title: 'The count is unfinished', body: '425 people have boarded; 115 remain. The model has no later service or abandonment.' },
    ],
    caption: 'SYN-F1. Simplified end-of-interval seat release, FIFO queue, empty initial queue. Moments describe one invented representative evening; they do not measure individual waiting times.',
  };
  const before = structuredClone(data);
  const preset = presetFor('editorial-minimal', 'editorial-spread');
  preset.font_heading = 'Georgia';
  const ops = capture(renderers.renderTimeline, data, preset);
  const focus = ops.find((op) => op.kind === 'shape' && op.options.objectName === 'role-contract-slot:evidence:timeline-0').options;
  const texts = [data.milestones[0].label, data.milestones[0].title, data.milestones[0].body]
    .map((text) => ops.find((op) => op.kind === 'text' && op.text === text).options);
  assert.ok(focus.x >= 0.70, 'focus panel clears the editorial rail');
  for (const text of texts) {
    assert.ok(text.x - focus.x >= 0.32 - 1e-6);
    assert.ok(focus.x + focus.w - text.x - text.w >= 0.32 - 1e-6);
    assert.notEqual(text.fit, 'shrink');
  }
  assert.ok(texts.slice(1).every((text) => text.fontSize >= 16));
  assert.ok(texts[2].y - texts[1].y - texts[1].h >= 0.12);
  assert.ok(ops.some((op) => op.text === data.caption));
  for (const item of data.milestones.slice(1)) {
    const detail = ops.find((op) => op.text === item.body).options;
    assert.ok(detail.h >= 3 * detail.fontSize / 72 * 1.28 - 1e-6,
      'supporting row reserves the complete three-line 16pt body, not only advance-estimated lines');
  }
  assert.equal(data.__roleContractExecution.adaptation, 'readable-timeline-chapter-spread');
  assert.deepEqual(data.milestones, before.milestones);
  assert.equal(data.caption, before.caption);
});

test('lab chart renders the supplied fact when its contract has no fact slot', () => {
  const data = chartData();
  const operations = capture(renderers.renderChart, data, presetFor('lab-report', 'scientific-evidence-plate'));
  assert.ok(operations.some((op) => op.kind === 'text' && op.text === '+15 pp'));
  assert.ok(operations.some((op) => op.kind === 'text' && op.text === 'Availability gain'));
  assert.equal(data.__roleContractExecution.adaptation, 'readable-chart-insight-band');
  data.chart.facts = [
    { value: '85%', label: 'Screening threshold', detail: 'Invented criterion, not release specification' },
    { value: '29 pp', label: 'Glycerol minus buffer', detail: '91% - 62%; descriptive difference' },
  ];
  data.caption = 'Equal-weight lot means; no confidence interval or significance claim.';
  data.interpretation = '';
  data.chart.notes = 'Technical replicates are not independent lots.';
  for (const grammar of GRAMMARS) {
    const ops = capture(renderers.renderChart, data, presetFor('lab-report', grammar));
    for (const field of [...data.chart.facts.flatMap((fact) => [fact.value, fact.label, fact.detail]),
      data.caption]) {
      const text = ops.find((op) => op.kind === 'text' && String(op.text).includes(field));
      assert.ok(text, `${grammar}: missing ${field}`);
      assert.notEqual(text.options.fit, 'shrink');
      assert.ok(wrapText(text.text, text.options.w, text.options.fontSize,
        text.options.fontFace, text.options.bold).h <= text.options.h + 1e-6);
    }
    assert.ok(!ops.some((op) => String(op.text).includes(data.chart.notes)), 'fallback notes must not duplicate an explicit caption');
    const notesOnly = structuredClone(data);
    delete notesOnly.caption;
    assert.ok(capture(renderers.renderChart, notesOnly, presetFor('lab-report', grammar))
      .some((op) => String(op.text).includes(data.chart.notes)), `${grammar}: retain declared fallback notes`);
  }
});

test('chart colors do not turn absent options into a dark first bar', () => {
  const chart = capture(renderers.renderChart, chartData(), presetFor('midnight-neon', 'technical-telemetry-canvas'))
    .find((op) => op.kind === 'chart');
  assert.equal(chart.options.chartColors[0], '22D3EE');
  assert.ok(!chart.options.chartColors.includes('030712'));
});

test('comparison verdict clears all rendered option text extents', () => {
  const grammars = {
    'executive-clinical': 'clinical-care-pathway',
    'lab-report': 'scientific-evidence-plate',
    'midnight-neon': 'technical-telemetry-canvas',
    'lavender-ops': 'operations-grid',
    'sunset-investor': 'investor-thesis-stage',
  };
  for (const [style, grammar] of Object.entries(grammars)) {
    const data = {
      type: 'content', role: 'comparison', variant: 'comparison-2col', title: 'Depth now or breadth before the evidence is ready?',
      left: { title: 'Focused pilot', bullets: ['24 sensors across four zones', '$48k budget with review funded', 'Comparable measurements before expansion'] },
      right: { title: 'Immediate expansion', bullets: ['60 sensors across ten zones', '$110k indicative budget', 'More coverage; greater maintenance burden'] },
      verdict: 'Run the focused pilot; expand only after the coverage and quality review.',
    };
    const operations = capture(renderers.renderComparison2col, data, presetFor(style, grammar));
    const verdict = operations.find((op) => op.options?.objectName === 'role-contract-slot:comparison:verdict');
    assert.ok(verdict, `${style}: verdict slot`);
    const optionText = operations.filter((op) => op.kind === 'text' && (
      String(op.text).includes('More coverage') || String(op.text).includes('Comparable measurements')
    ));
    for (const { options: box } of optionText) {
      const callout = verdict.options;
      const overlap = Math.min(box.x + box.w, callout.x + callout.w) - Math.max(box.x, callout.x) > 0.02
        && Math.min(box.y + box.h, callout.y + callout.h) - Math.max(box.y, callout.y) > 0.02;
      assert.ok(!overlap, `${style}: verdict overlaps option body`);
    }
  }

  const original = 'Choose risk-first for this shift; accept four extra crew travel hours to reduce modeled exposure.';
  for (const verdictText of ['', 'Choose risk-first for this shift.', original,
    `${original} Recheck the queue if telemetry or crew capacity changes.`]) {
    const data = {
      type: 'content', role: 'comparison', variant: 'comparison-2col',
      title: 'Risk-first protects product; it costs more travel',
      left: { title: 'Ticket-age order', body: [
        '5 projected threshold excursions', '65 unprotected pallet-hours',
        '17 crew travel hours', '4 of 7 critical loads restored',
      ] },
      right: { title: 'Risk-first order', body: [
        '1 projected threshold excursion', '22 unprotected pallet-hours',
        '21 crew travel hours', '7 of 7 critical loads restored',
      ] },
      verdict: verdictText, sources: ['S1'], __slideIndex: 6, __slideCount: 7,
    };
    const operations = capture(renderers.renderComparison2col, data, presetFor('charcoal-safety', 'operations-grid'));
    const verdictBox = operations.find((op) => op.options?.objectName === 'role-contract-slot:comparison:verdict');
    const cards = operations.filter((op) => /^role-contract-slot:comparison:option-\d$/.test(op.options?.objectName || ''));
    assert.equal(cards.length, 2);
    if (!verdictText) {
      assert.equal(verdictBox, undefined);
      continue;
    }
    assert.ok(verdictBox);
    assert.ok(cards.every(({ options: box }) => verdictBox.options.y - (box.y + box.h) >= 0.14));
    assert.ok((renderers.SLIDE_H - 0.56) - (verdictBox.options.y + verdictBox.options.h) >= 0.14);
    assert.ok(operations.some((op) => op.kind === 'text' && op.text === verdictText && op.options.fontSize >= 16));
    assert.ok(operations.filter((op) => op.kind === 'text' && String(op.text).includes('critical loads restored'))
      .every((op) => op.options.fontSize >= 16));
  }
});

test('v2 verdict reservation clears whole option containers without hiding long conclusions', () => {
  for (const grammar of GRAMMARS) {
    const data = { role: 'comparison', variant: 'comparison-2col', title: 'Dispatch tradeoff',
      left: { title: 'Ticket-age order', body: ['Five excursions', 'Seventeen travel hours'] },
      right: { title: 'Risk-first order', body: ['One excursion', 'Twenty-one travel hours'] },
      verdict: 'Choose risk-first for this shift; accept four extra crew travel hours to reduce modeled exposure.', sources: ['S1'] };
    const preset = presetFor('charcoal-safety', grammar);
    const ops = capture(renderers.renderComparison2col, data, preset);
    const verdict = ops.find((op) => op.options?.objectName === 'role-contract-slot:comparison:verdict').options;
    for (const option of ops.filter((op) => /^role-contract-slot:comparison:option-\d$/.test(op.options?.objectName || ''))) {
      const box = option.options;
      const overlap = Math.min(box.x + box.w, verdict.x + verdict.w) - Math.max(box.x, verdict.x) > 0.01
        && Math.min(box.y + box.h, verdict.y + verdict.h) - Math.max(box.y, verdict.y) > 0.01;
      assert.ok(!overlap, `${grammar}: verdict overlaps option container`);
    }
    const text = ops.find((op) => op.text === data.verdict);
    assert.notEqual(text.options.fit, 'shrink');
    assert.ok(text.options.h >= wrapText(text.text, text.options.w, text.options.fontSize, text.options.fontFace, true).h);
    data.verdict = 'Retain this complete conclusion and its caveats. '.repeat(500);
    assert.throws(() => capture(renderers.renderComparison2col, data, preset), /comparison.*split the source slide/i);
  }
});

test('dark cover footer uses readable provenance and page ink', () => {
  for (const style of ['lavender-ops', 'sunset-investor']) {
    const data = { type: 'title', role: 'title', variant: 'title', title: 'The Urban Observatory', footer: 'Illustrative planning data', sources: ['D1'], page_number: true, __slideIndex: 1, __slideCount: 8 };
    const preset = presetFor(style);
    const operations = capture(renderers.renderTitle, data, preset);
    for (const name of ['metadata:footer-sources', 'metadata:footer-page-number']) {
      const item = operations.find((op) => op.options?.objectName === name);
      assert.ok(item, `${style}: ${name}`);
      assert.notEqual(item.options.color, preset.text_muted, `${style}: footer remains low contrast`);
    }
  }
});

test('policy table keeps interpretation and reference register keeps source headers', () => {
  const preset = presetFor('warm-terracotta', 'policy-public-docket');
  const table = tableData();
  const tableOps = capture(renderers.renderTable, table, preset);
  assert.ok(tableOps.some((op) => op.kind === 'text' && op.text === table.interpretation));

  const references = {
    type: 'content', role: 'references', title: 'The evidence remains inspectable',
    table: { table_style: 'references', headers: ['ID', 'Record', 'Use'], rows: [
      ['D1', 'Illustrative program dataset', 'Synthetic inputs'],
      ['D2', 'Frozen outline.json', 'Identical wording'],
      ['D3', 'Build and review records', 'Visual inspection'],
    ] },
  };
  const referenceOps = capture(renderers.renderTable, references, preset);
  for (const header of references.table.headers) {
    assert.ok(referenceOps.some((op) => op.kind === 'text' && op.text === header), `${header} header`);
  }
});

test('midnight reference table has a visible nearby context label', () => {
  const data = {
    type: 'content', role: 'references', title: 'The evidence remains inspectable',
    table: { table_style: 'references', headers: ['ID', 'Record', 'Use'], rows: [['D1', 'Dataset', 'Synthetic inputs']] },
  };
  const operations = capture(renderers.renderTable, data, presetFor('midnight-neon', 'technical-telemetry-canvas'));
  const table = operations.find((op) => op.kind === 'table');
  const label = operations.find((op) => op.kind === 'text' && op.options?.objectName === 'metadata:reference-table-label');
  assert.ok(table && label);
  assert.equal(label.text, 'SOURCE REGISTER');
  assert.ok(table.options.y - label.options.y - label.options.h <= 0.75);
  assert.equal(table.rows[0][0].options.fontFace, 'Arial');
});

test('midnight display adjustment preserves explicit and legacy fonts', () => {
  const data = { type: 'title', role: 'title', variant: 'title', title: 'The Urban Observatory' };
  const base = presetFor('midnight-neon', 'technical-telemetry-canvas');
  const custom = { ...base, font_heading: 'Georgia', font_title: 'Georgia' };
  const legacy = { ...base, renderer_role_contract_version: 'renderer_role_systems_v1' };
  for (const [preset, expected] of [[custom, 'Georgia'], [legacy, 'Inter']]) {
    const operations = capture(renderers.renderTitle, { ...data }, preset);
    const title = operations.find((op) => op.kind === 'text' && op.text === data.title);
    assert.ok(title);
    assert.equal(title.options.fontFace, expected);
  }
});

test('midnight renderer forwards the cards column argument', () => {
  const data = { type: 'content', title: 'Three options', cards: [
    { title: 'One', body: 'First option' },
    { title: 'Two', body: 'Second option' },
    { title: 'Three', body: 'Third option' },
  ] };
  const preset = presetFor('midnight-neon');
  const two = capture(renderers.renderCards, data, preset, 2);
  const three = capture(renderers.renderCards, data, preset, 3);
  assert.ok(!two.some((op) => op.kind === 'text' && op.text === 'Three'));
  assert.ok(three.some((op) => op.kind === 'text' && op.text === 'Three'));
});

test('three readable timeline labels use compact centered boxes', () => {
  const data = { type: 'content', role: 'evidence', variant: 'timeline', title: 'Pilot timeline',
    milestones: [
      { label: 'Week 1', title: 'Scope', body: 'Select sites.' },
      { label: 'Week 2', title: 'Pilot', body: 'Collect observations.' },
      { label: 'Week 3', title: 'Review', body: 'Decide next steps.' },
    ],
  };
  for (const [style, grammar] of [
    ['lab-report', 'scientific-evidence-plate'],
    ['warm-terracotta', 'policy-public-docket'],
  ]) {
    const operations = capture(renderers.renderTimeline, { ...data }, presetFor(style, grammar));
    const labels = operations.filter((op) => op.kind === 'text'
      && String(op.options?.objectName || '').startsWith('metadata:timeline-label-'));
    assert.equal(labels.length, 3);
    assert.ok(labels.every((op) => op.options.h < 0.8), `${style}: label box too tall`);
    assert.deepEqual(labels.map((op) => op.text), ['WEEK 1', 'WEEK 2', 'WEEK 3']);
  }
});

test('sparse reference cards fit their real text inside retained card rows', () => {
  const data = { type: 'content', role: 'references', variant: 'table', title: 'References', table: {
    table_style: 'references', headers: ['ID', 'Record', 'Use'], rows: [
      ['S1', 'Scope', 'Two sites.'],
      ['S2', 'Owner', 'Operations lead.'],
      ['S3', 'Gate', 'Review readiness.'],
      ['S4', 'Stop', 'Pause on missing evidence.'],
      ['S5', 'S1: synthetic illustration', 'Supporting evidence'],
    ],
  } };
  const operations = capture(renderers.renderTable, data, presetFor('lab-report', 'scientific-evidence-plate'));
  const cardTexts = operations.filter((op) => op.kind === 'text'
    && /^metadata:reference-(title|detail)-/.test(String(op.options?.objectName || '')));
  assert.equal(cardTexts.length, 10);
  assert.ok(cardTexts.every((op) => op.options.h < 0.8));
  for (const row of data.table.rows) {
    assert.ok(cardTexts.some((op) => op.text === row[0]));
    assert.ok(cardTexts.some((op) => op.text.includes(row[1])));
  }
});

test('sparse policy comparison rows keep complete text in compact boxes', () => {
  const data = { type: 'content', role: 'comparison', variant: 'comparison-2col', title: 'Options',
    left: { title: 'Pilot', bullets: ['Two sites'] },
    right: { title: 'Expansion', bullets: ['After review'] },
  };
  const operations = capture(renderers.renderComparison2col, data, presetFor('warm-terracotta', 'policy-public-docket'));
  const numbers = operations.filter((op) => op.kind === 'text'
    && /^metadata:policy-option-/.test(String(op.options?.objectName || '')));
  assert.equal(numbers.length, 2);
  assert.ok(numbers.every((op) => op.options.h < 0.8));
  for (const value of ['Pilot', 'Expansion', '• Two sites', '• After review']) {
    const text = operations.find((op) => op.kind === 'text' && op.text === value);
    assert.ok(text, `${value} omitted`);
    assert.ok(text.options.h < 0.8, `${value} box too tall`);
  }
});
