'use strict';

const assert = require('node:assert/strict');
const { test } = require('node:test');
const builder = require('../scripts/build_deck_pptxgenjs.js');
const renderers = require('../templates/pptxgenjs/slides.js');
const { getPreset } = require('../templates/pptxgenjs/presets.js');

const STYLES = ['midnight-neon', 'editorial-minimal', 'lavender-ops'];
const INTERPRETATION = 'Uptime measures device availability; it does not establish measurement accuracy.';

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
    addNotes() {},
  };
  renderer({ ChartType: { bar: 'bar' } }, slide, data, preset, ...args);
  return operations;
}

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

  test(`${style} ordinary table adapts narrow readout to a body-size band`, () => {
    const data = tableData();
    const operations = capture(renderers.renderTable, data, presetFor(style));
    const readout = operations.find((op) => op.kind === 'text' && op.text === data.interpretation);
    assert.ok(readout, 'ordinary table readout must be rendered in full');
    assert.ok(readout.options.fontSize >= 16);
    assert.ok(readout.options.w >= 7.0);
    assert.equal(data.__roleContractExecution.adaptation, 'readable-table-readout-band');
  });
}

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

test('lab chart renders the supplied fact when its contract has no fact slot', () => {
  const data = chartData();
  const operations = capture(renderers.renderChart, data, presetFor('lab-report', 'scientific-evidence-plate'));
  assert.ok(operations.some((op) => op.kind === 'text' && op.text === '+15 pp'));
  assert.ok(operations.some((op) => op.kind === 'text' && op.text === 'Availability gain'));
  assert.equal(data.__roleContractExecution.adaptation, 'readable-chart-insight-band');
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
  assert.equal(table.rows[0][0].options.fontFace, 'Helvetica Neue');
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
