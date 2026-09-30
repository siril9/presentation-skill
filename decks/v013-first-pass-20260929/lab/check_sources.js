// Independent source arithmetic and visible-caveat checks; never builds or renders.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');

const root = path.dirname(__dirname);
const read = (folder, name) => JSON.parse(fs.readFileSync(path.join(root, folder, name), 'utf8'));
const sum = (values) => values.reduce((total, value) => total + value, 0);
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);
const visible = (value) => {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(visible).join('\n');
  if (!value || typeof value !== 'object') return '';
  return Object.entries(value)
    .filter(([key]) => !['notes', 'metadata', 'deck_style', 'chart_alt_text'].includes(key))
    .map(([, item]) => visible(item)).join('\n');
};

function checkCommon(folder, slideCount, grammar, variants) {
  const outline = read(folder, 'outline.json');
  const brief = read(folder, 'quick_deck_agent_brief.json');
  const data = read(folder, 'synthetic_data.json');
  assert.equal(outline.slides.length, slideCount);
  assert.equal(outline.deck_style.composition_grammar, grammar);
  const candidate = brief.route_candidates.find((item) => item.grammar_id === grammar);
  assert.ok(candidate);
  assert.equal(outline.deck_style.style_preset, candidate.style_preset);
  assert.deepEqual(outline.deck_style.readability_contract, brief.outline_contract.deck_style.readability_contract);
  assert.equal(data.synthetic, true);
  assert.equal(outline.metadata.synthetic, true);
  assert.equal(outline.metadata.external_assets, false);
  assert.deepEqual(outline.slides.map((slide) => slide.variant), variants);
  assert.equal(new Set(outline.slides.map((slide) => slide.slide_id)).size, slideCount);
  for (const slide of outline.slides) {
    assert.ok(brief.renderer.role_variants[slide.role].includes(slide.variant), `${folder}: unsupported role/variant`);
    assert.ok(slide.sources.length);
    assert.match(visible(slide), /synthetic|invented/i);
    assert.ok(!/https?:\/\//.test(visible(slide)), 'No external references or assets');
    if (slide.variant === 'table') {
      assert.ok(slide.table.caption.length > 60);
      assert.ok(slide.table.rows.every((row) => row.length === slide.table.headers.length));
    }
    if (slide.variant === 'chart') {
      assert.ok(slide.caption.length > 60);
      assert.equal(slide.chart.options.valAxisMinVal, 0);
      assert.ok(slide.chart.series.every((series) => series.values.length === slide.chart.categories.length));
    }
  }
  return { outline, data, text: visible(outline) };
}

function checkLab() {
  const { outline, data, text } = checkCommon('lab', 7, 'scientific-evidence-plate',
    ['title', 'table', 'chart', 'table', 'comparison-2col', 'timeline', 'standard']);
  assert.equal(data.independent_lots.length * data.conditions.length * 2, data.sample_count);
  assert.equal(data.sample_count * data.technical_wells_per_sample, data.well_count);
  const means = [];
  const passCounts = [];
  for (const condition of data.conditions) {
    condition.day14_rate_U_per_mL.forEach((rate, index) => {
      near(100 * rate / data.day0_rate_U_per_mL_by_lot[index], condition.residual_activity_percent[index]);
      near(sum([0.99 * rate, 1.01 * rate]) / 2, rate);
    });
    means.push(sum(condition.residual_activity_percent) / data.independent_lots.length);
    passCounts.push(condition.residual_activity_percent.filter((value) => value >= data.screening_threshold_percent).length);
  }
  assert.deepEqual(means, [62, 91, 84]);
  assert.deepEqual(passCounts, [0, 3, 1]);
  assert.deepEqual(outline.slides[2].chart.series[0].values, means);
  data.independent_lots.forEach((lot, index) => {
    assert.deepEqual(outline.slides[3].table.rows[index], [lot, ...data.conditions.map((condition) => String(condition.residual_activity_percent[index]))]);
  });
  assert.deepEqual(outline.slides[3].table.rows[3], ['Mean', ...means.map(String)]);
  assert.deepEqual(outline.slides[3].table.rows[4], ['Lots >=85%', ...passCounts.map((count) => `${count}/3`)]);
  near(means[1] - means[0], 29);
  for (const warning of ['independent n = 3', 'No error bars', 'significance claim', 'Three lots cannot characterize', 'No temperature excursion test', 'clinical use', 'power calculation', 'no formulation release']) {
    assert.ok(text.includes(warning), `Missing visible lab warning: ${warning}`);
  }
  return {
    checks: ['Matched rate ratios and equal-weight chart means', 'Individual lot table and threshold denominators', '18 samples / 36 wells / independent n=3', '29 percentage-point contrast', 'Visible uncertainty, release, temperature and power boundaries'],
    computed: { means_percent: means, threshold_passes_out_of_3: passCounts, samples: 18, wells: 36, glycerol_minus_buffer_pp: 29 }
  };
}

function queue(arrivals, places) {
  let remaining = 0;
  const queues = [];
  const boardings = [];
  arrivals.forEach((arrivalsThisSlot, index) => {
    const boarded = Math.min(remaining + arrivalsThisSlot, places[index]);
    remaining += arrivalsThisSlot - boarded;
    queues.push(remaining);
    boardings.push(boarded);
  });
  return { queues, boardings };
}

function checkEditorial() {
  const { outline, data, text } = checkCommon('editorial', 6, 'editorial-spread',
    ['title', 'timeline', 'chart', 'comparison-2col', 'table', 'standard']);
  const baseline = queue(data.arrivals_people_per_evening, data.baseline_places_per_evening);
  const moved = queue(data.arrivals_people_per_evening, data.moved_places_per_evening);
  assert.deepEqual(baseline.queues, data.baseline_queue_people);
  assert.deepEqual(moved.queues, data.moved_queue_people);
  assert.deepEqual(baseline.boardings, data.baseline_boardings_per_evening);
  assert.deepEqual(moved.boardings, data.moved_boardings_per_evening);
  assert.equal(sum(data.arrivals_people_per_evening), 540);
  assert.equal(sum(data.baseline_places_per_evening), 480);
  assert.equal(sum(data.moved_places_per_evening), 480);
  assert.equal(sum(baseline.boardings), 425);
  assert.equal(sum(moved.boardings), 480);
  assert.equal(540 - 425, 115);
  assert.equal(540 - 480, 60);
  assert.equal(480 - 425, 55);
  assert.equal(55 * data.evenings, 550);
  assert.equal(540 * data.evenings, 5400);
  near(100 * (110 + 145) / 540, 47.22222222222222);
  assert.deepEqual(outline.slides[2].chart.series[0].values, data.arrivals_people_per_evening);
  assert.deepEqual(outline.slides[2].chart.series[1].values, data.baseline_places_per_evening);
  assert.deepEqual(outline.slides[4].table.rows, data.release_times.map((time, index) =>
    [time, String(data.arrivals_people_per_evening[index]), String(baseline.queues[index]), String(moved.queues[index])]));
  for (const warning of ['not a ridership forecast', 'ten deliberately identical evenings', 'not a sampled estimate', 'early service worsens', 'waiting times are unknown', 'no later service or abandonment', 'not a service-change authorization', 'first queue rises to 40']) {
    assert.ok(text.toLowerCase().includes(warning.toLowerCase()), `Missing visible ferry warning: ${warning}`);
  }
  return {
    checks: ['FIFO queue recurrence and all six ledger rows', 'Chart arrivals and baseline places linked to source', 'Same 540 arrivals / 480 places in each scenario', 'Boardings plus final queues conserve arrivals', 'Middle-hour share and ten-evening totals', 'Visible early-access penalty, waiting-time and forecast boundaries'],
    computed: { arrivals_per_evening: 540, offered_places_per_scenario: 480, baseline_boardings: 425, moved_boardings: 480, baseline_final_queue: 115, moved_final_queue: 60, baseline_peak_sampled_queue: 120, moved_peak_sampled_queue: 65, extra_boardings_per_evening: 55, extra_boardings_10_evenings: 550 }
  };
}

function checkOperations() {
  const { outline, data, text } = checkCommon('operations', 7, 'operations-grid',
    ['title', 'standard', 'chart', 'table', 'timeline', 'comparison-2col', 'matrix']);
  assert.equal(data.window_days * 24, data.window_hours);
  assert.equal(data.coverage_hours, 720);
  const sorted = [...data.events].sort((left, right) => left.start_hour - right.start_hour);
  sorted.forEach((event, index) => {
    near(event.end_hour - event.start_hour, event.downtime_hours);
    assert.ok(event.start_hour >= 0 && event.end_hour <= data.window_hours);
    if (index) assert.ok(event.start_hour >= sorted[index - 1].end_hour);
  });
  const downtime = sum(data.events.map((event) => event.downtime_hours));
  const availability = 100 * (720 - downtime) / 720;
  const allowance = 720 * (1 - data.target_availability_percent / 100);
  const counterfactualDowntime = downtime - data.events[0].downtime_hours + data.options[1].bus_outage_hours;
  near(downtime, 7.5);
  near(availability, 98.95833333333333);
  near(allowance, 3.6);
  near(downtime - allowance, 3.9);
  near(100 * 4.5 / downtime, 60);
  near(counterfactualDowntime, 4.5);
  near(100 * (720 - counterfactualDowntime) / 720, 99.375);
  near(counterfactualDowntime - allowance, 0.9);
  assert.deepEqual(outline.slides[2].chart.series[0].values, data.events.map((event) => event.downtime_hours));
  assert.deepEqual(outline.slides[3].table.rows.map((row) => Number(row[1].replaceAll(',', ''))), data.options.map((option) => option.estimate_USD));
  assert.deepEqual(outline.slides[3].table.rows.map((row) => Number(row[2])), data.options.map((option) => option.bus_outage_hours));
  for (const warning of ['not authorized', 'not a repair instruction', 'safety certification', 'Includes 0.5 h planned', 'not proven causality', 'exclude taxes and contingency', 'not a prediction', 'Incomplete coverage: uptime unverified', 'no actual repair', 'Qualified diagnosis']) {
    assert.ok(text.toLowerCase().includes(warning.toLowerCase()), `Missing visible ops warning: ${warning}`);
  }
  return {
    checks: ['30 days / 720 hours, complete coverage, non-overlapping events', 'Downtime chart linked to event durations', 'Native option table matches USD and bus-outage estimates', 'Inclusive availability, allowance and variance', 'Same-window counterfactual and remaining target gap', 'Visible qualification, authorization, causality and missing-coverage boundaries'],
    computed: { window_hours: 720, downtime_hours: downtime, availability_percent: availability, target_downtime_hours: 3.6, excess_downtime_hours: 3.9, connector_tagged_share_percent: 60, counterfactual_downtime_hours: 4.5, counterfactual_availability_percent: 99.375, counterfactual_excess_hours: 0.9 }
  };
}

const results = { lab: checkLab(), editorial: checkEditorial(), operations: checkOperations() };
for (const [folder, result] of Object.entries(results)) {
  const outlinePath = path.join(root, folder, 'outline.json');
  const sourceBytes = fs.readFileSync(outlinePath);
  const report = {
    status: 'SOURCE_FACTS_PASS_NOT_RENDERED',
    checked_at_utc: new Date().toISOString(),
    outline_sha256: crypto.createHash('sha256').update(sourceBytes).digest('hex'),
    synthetic_data_sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, folder, 'synthetic_data.json'))).digest('hex'),
    common_checks: ['Valid JSON and unique slide IDs', 'Selected brief candidate preset plus grammar', 'Exact brief readability contract', 'Supported role/variant pairs', 'Synthetic provenance visible per slide', 'Native chart zero baseline and matching dimensions', 'Native table dimensions and meaningful captions'],
    ...result,
    not_checked: ['Renderer integration', 'PPTX content preservation', 'Native-object rendering', 'Geometry', 'Readability in rendered output', 'Contact sheet and per-slide visual review'],
    next_owner: 'Main release build/measurement runner; author visual review after main-ready notification'
  };
  fs.writeFileSync(path.join(root, folder, 'factual_check.json'), `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${folder}: ${report.status} (${read(folder, 'outline.json').slides.length} slides)\n`);
}
