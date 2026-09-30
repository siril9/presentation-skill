#!/usr/bin/env node
/*
 * pptxgenjs peer renderer for the presentation-skill outline.json format.
 *
 * Reads the same outline.json as scripts/build_deck.py and emits a .pptx
 * using pptxgenjs directly -- no Playwright and no html2pptx.
 *
 * CLI:
 *   node scripts/build_deck_pptxgenjs.js \
 *     --outline deck.json \
 *     --output  out.pptx \
 *     --style-preset executive-clinical
 *
 * Supported slide types:
 *   - title
 *   - section
 *   - content variants: standard, cards-2/3, split, timeline, stats,
 *     kpi-hero, table, lab-run-results, comparison-2col, matrix, flow,
 *     image-sidebar, scientific-figure, generated-image.
 *
 * Native chart slides are rendered by this path for common bar/line/pie
 * payloads. Use the Python renderer only when a deck needs python-pptx-only
 * behavior.
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');
const Module = require('module');

// ---------------------------------------------------------------------------
// Make pptxgenjs resolvable even when node_modules lives outside the skill.
// ---------------------------------------------------------------------------
function configureNodePath() {
  const sep = path.delimiter;
  const existing = String(process.env.NODE_PATH || '')
    .split(sep)
    .map((s) => s.trim())
    .filter(Boolean);
  const candidates = [
    process.env.PPTX_NODE_MODULES || '',
    path.resolve(__dirname, '..', 'node_modules'),
    path.resolve(process.cwd(), 'node_modules'),
    path.resolve(os.homedir(), 'codex', 'CascadeProjects', 'pptx_ab_comparison', 'node_modules'),
  ].filter(Boolean);
  let changed = false;
  for (const candidate of candidates) {
    if (!candidate || !fs.existsSync(candidate)) continue;
    if (existing.includes(candidate)) continue;
    existing.push(candidate);
    changed = true;
  }
  if (changed) {
    process.env.NODE_PATH = existing.join(sep);
    Module._initPaths();
  }
}
configureNodePath();

let PptxGenJS;
let JSZip;
try {
  PptxGenJS = require('pptxgenjs');
  JSZip = require('jszip');
} catch (err) {
  console.error(
    'Error: missing dependency "pptxgenjs" or "jszip". Run the repository setup before building.\n' +
      'Or set PPTX_NODE_MODULES to a directory that contains it.',
  );
  process.exit(2);
}

const TEMPLATES_DIR = path.resolve(__dirname, '..', 'templates', 'pptxgenjs');
const { getPreset, DEFAULT_PRESET_NAME, listPresets } = require(path.join(TEMPLATES_DIR, 'presets.js'));
const slides = require(path.join(TEMPLATES_DIR, 'slides.js'));
const {
  CONTRACT_VERSION: ROLE_CONTRACT_VERSION,
  contractsForGrammar,
  validateResolvedRoleContracts,
} = require(path.join(TEMPLATES_DIR, 'role_layout_contracts.js'));
const { resolveRenderPlan } = require(path.join(TEMPLATES_DIR, 'render_plan.js'));

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = {
    outline: '',
    output: '',
    stylePreset: DEFAULT_PRESET_NAME,
    assetRoot: '',
    renderPlanDiagnostics: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const tok = argv[i];
    const next = () => {
      const v = argv[i + 1];
      i += 1;
      return v;
    };
    switch (tok) {
      case '-h':
      case '--help':
        printUsage();
        process.exit(0);
        break;
      case '--outline':
        args.outline = next();
        break;
      case '--output':
        args.output = next();
        break;
      case '--style-preset':
        args.stylePreset = next();
        break;
      case '--asset-root':
        args.assetRoot = next();
        break;
      case '--render-plan-diagnostics':
        args.renderPlanDiagnostics = true;
        break;
      default:
        if (tok.startsWith('--outline=')) args.outline = tok.slice('--outline='.length);
        else if (tok.startsWith('--output=')) args.output = tok.slice('--output='.length);
        else if (tok.startsWith('--style-preset=')) args.stylePreset = tok.slice('--style-preset='.length);
        else if (tok.startsWith('--asset-root=')) args.assetRoot = tok.slice('--asset-root='.length);
        else {
          console.error(`Unknown argument: ${tok}`);
          printUsage();
          process.exit(2);
        }
    }
  }
  return args;
}

function printUsage() {
  const usage = [
    'Usage: node scripts/build_deck_pptxgenjs.js \\',
    '         --outline <path/to/outline.json> \\',
    '         --output  <path/to/out.pptx> \\',
    '         [--style-preset executive-clinical] \\',
    '         [--asset-root <workspace>] \\',
    '         [--render-plan-diagnostics]',
    '',
    `Presets: ${listPresets().join(' | ')}`,
  ].join('\n');
  console.log(usage);
}

// ---------------------------------------------------------------------------
// Outline loading
// ---------------------------------------------------------------------------

function loadOutline(outlinePath) {
  const resolved = path.resolve(outlinePath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`outline not found: ${resolved}`);
  }
  const raw = fs.readFileSync(resolved, 'utf8');
  let data;
  try {
    data = JSON.parse(raw);
  } catch (err) {
    throw new Error(`outline is not valid JSON (${resolved}): ${err.message}`);
  }
  if (!data || typeof data !== 'object') {
    throw new Error(`outline root must be an object`);
  }
  const slideList = Array.isArray(data.slides) ? data.slides : [];
  if (!slideList.length) {
    throw new Error(`outline has no slides`);
  }
  return {
    data,
    slideList,
    outlineDir: path.dirname(resolved),
  };
}

const STAGED_LOOKUP_CACHE = new Map();
const JSON_PAYLOAD_CACHE = new Map();
const ASSET_ALIAS_SECTIONS = [
  ['images', ['asset', 'image']],
  ['backgrounds', ['asset', 'background']],
  ['charts', ['asset', 'chart']],
  ['tables', ['asset', 'table']],
  ['generated_images', ['asset', 'image', 'generated']],
];

function normalizedAliasRef(value) {
  const raw = String(value || '').trim();
  const normalized = raw.toLowerCase();
  return /^(asset|image|background|chart|table|generated):/.test(normalized) ? normalized : '';
}

function safeAliasName(value) {
  return String(value || '')
    .replace(/[^A-Za-z0-9_-]/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
}

function addAssetLookupEntries(lookup, payload, baseDir, sourceLabel) {
  if (!payload || typeof payload !== 'object') return;
  for (const [section, prefixes] of ASSET_ALIAS_SECTIONS) {
    const entries = Array.isArray(payload[section]) ? payload[section] : [];
    for (const entry of entries) {
      if (!entry || typeof entry !== 'object') continue;
      const name = safeAliasName(entry.name);
      const rawPath = String(entry.path || entry.file_path || entry.output_path || entry.image_path || '').trim();
      const assetPath = rawPath
        ? (path.isAbsolute(rawPath) ? rawPath : path.resolve(baseDir, rawPath))
        : '';
      if (!name) continue;
      for (const prefix of prefixes) {
        const key = `${prefix}:${name}`;
        if (!lookup.has(key)) {
          lookup.set(key, {
            path: assetPath,
            entry,
            section,
            source: sourceLabel,
          });
        }
      }
    }
  }
}

function stagedAssetLookup(outlineDir) {
  const cacheKey = path.resolve(outlineDir);
  if (STAGED_LOOKUP_CACHE.has(cacheKey)) return STAGED_LOOKUP_CACHE.get(cacheKey);
  const lookup = new Map();
  const sources = [
    {
      sourcePath: path.resolve(outlineDir, 'assets', 'staged', 'staged_manifest.json'),
      baseDir: outlineDir,
      label: 'staged_manifest.json',
    },
    {
      sourcePath: path.resolve(outlineDir, 'asset_plan.json'),
      baseDir: outlineDir,
      label: 'asset_plan.json',
    },
  ];
  for (const source of sources) {
    if (!fs.existsSync(source.sourcePath)) continue;
    try {
      const payload = JSON.parse(fs.readFileSync(source.sourcePath, 'utf8'));
      addAssetLookupEntries(lookup, payload, source.baseDir, source.label);
    } catch (err) {
      console.warn(`[pptxgenjs] failed to read asset lookup ${source.sourcePath}: ${err.message}`);
    }
  }
  STAGED_LOOKUP_CACHE.set(cacheKey, lookup);
  return lookup;
}

function lookupAssetAlias(value, outlineDir) {
  const normalized = normalizedAliasRef(value);
  if (!normalized) return null;
  return stagedAssetLookup(outlineDir).get(normalized) || null;
}

function readJsonPayload(resolved) {
  const cacheKey = path.resolve(resolved);
  if (JSON_PAYLOAD_CACHE.has(cacheKey)) return JSON_PAYLOAD_CACHE.get(cacheKey);
  let result;
  try {
    result = { payload: JSON.parse(fs.readFileSync(cacheKey, 'utf8')), error: '' };
  } catch (err) {
    result = { payload: undefined, error: err.message };
  }
  JSON_PAYLOAD_CACHE.set(cacheKey, result);
  return result;
}

// Resolve an image path or staged alias against the outline directory.
function resolveAssetPath(p, outlineDir) {
  if (!p) return '';
  const raw = String(p).trim();
  const normalized = normalizedAliasRef(raw);
  if (normalized) {
    const staged = lookupAssetAlias(raw, outlineDir);
    if (!staged) {
      console.warn(`[pptxgenjs] staged asset alias not found: ${raw}`);
      return '';
    }
    if (!staged.path) {
      console.warn(`[pptxgenjs] staged asset alias has no file path: ${raw}`);
      return '';
    }
    return staged.path;
  }
  const abs = path.isAbsolute(raw) ? raw : path.resolve(outlineDir, raw);
  return abs;
}

function safeNumber(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim().replace(/,/g, '').replace(/%$/, '');
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}

function normalizeFact(fact) {
  // Model-authored prose is a label, not a numeric statistic.
  return typeof fact === 'string' ? { label: fact.trim() } : fact;
}

function normalizeChartPayload(raw) {
  if (!raw || typeof raw !== 'object') return {};
  const chartType = String(raw.type || 'bar').trim().toLowerCase();
  const options = raw.options && typeof raw.options === 'object' ? raw.options : {};
  const chartLevelCategories = Array.isArray(raw.categories) && raw.categories.length
    ? raw.categories
    : Array.isArray(raw.labels) && raw.labels.length
      ? raw.labels
      : null;
  const invalid = [];
  const normalizedSeries = [];

  const pushSeries = (item, index, fallbackLabels) => {
    if (!item || typeof item !== 'object') {
      invalid.push(`series[${index}] is not an object`);
      return;
    }
    const labels = Array.isArray(item.labels) && item.labels.length ? item.labels : fallbackLabels;
    const values = Array.isArray(item.values) ? item.values : null;
    if (!Array.isArray(labels) || labels.length === 0) {
      invalid.push(`series[${index}] missing labels/categories`);
      return;
    }
    if (!values || values.length === 0) {
      invalid.push(`series[${index}] missing values`);
      return;
    }
    if (labels.length !== values.length) {
      invalid.push(`series[${index}] length mismatch: ${labels.length} labels vs ${values.length} values`);
      return;
    }
    const pairs = [];
    labels.forEach((label, idx) => {
      const parsed = safeNumber(values[idx]);
      const labelText = String(label || '').trim();
      if (labelText && parsed !== null) pairs.push([labelText, parsed]);
    });
    if (!pairs.length) {
      invalid.push(`series[${index}] has no usable label/value pairs`);
      return;
    }
    normalizedSeries.push({
      name: String(item.name || `Series ${index + 1}`),
      labels: pairs.map((item) => item[0]),
      values: pairs.map((item) => item[1]),
    });
  };

  if (Array.isArray(raw.series) && raw.series.length) {
    raw.series.forEach((item, idx) => pushSeries(item, idx, chartLevelCategories));
  } else if (chartLevelCategories && Array.isArray(raw.values)) {
    pushSeries({ name: raw.series_name || 'Series A', labels: chartLevelCategories, values: raw.values }, 0, null);
  } else {
    invalid.push('chart payload has no series and no flat labels/values');
  }

  const base = {
    type: chartType,
    title: String(raw.title || ''),
    subtitle: String(raw.subtitle || ''),
    notes: String(raw.notes || raw.message || raw.caption || ''),
    sources: Array.isArray(raw.sources) ? raw.sources : [],
    facts: Array.isArray(raw.facts) ? raw.facts.map(normalizeFact)
      : Array.isArray(raw.stats) ? raw.stats.map(normalizeFact) : raw.stats,
    options,
    color1: String(raw.color1 || ''),
    color2: String(raw.color2 || ''),
    color3: String(raw.color3 || ''),
    color4: String(raw.color4 || ''),
  };
  if (raw.__error__) {
    return Object.assign(base, {
      __error__: String(raw.__error__),
      series: [],
    });
  }
  if (!normalizedSeries.length) {
    return Object.assign(base, {
      __error__: invalid.join('; ') || 'chart payload present but produced no series',
      series: [],
    });
  }
  return Object.assign(base, { series: normalizedSeries });
}

function loadChartPayload(spec, outlineDir) {
  const assets = spec && spec.assets && typeof spec.assets === 'object' ? spec.assets : {};
  const candidates = [spec.chart, assets.chart_data, assets.chart];
  for (const candidate of candidates) {
    if (!candidate) continue;
    if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
      return normalizeChartPayload(candidate);
    }
    const alias = lookupAssetAlias(candidate, outlineDir);
    if (alias && !alias.path && alias.entry) {
      return normalizeChartPayload(alias.entry);
    }
    const resolved = alias && alias.path ? alias.path : resolveAssetPath(candidate, outlineDir);
    if (!resolved || !fs.existsSync(resolved)) continue;
    const result = readJsonPayload(resolved);
    if (result.error) {
      return normalizeChartPayload({ __error__: `failed to read chart JSON: ${result.error}` });
    }
    if (result.payload && typeof result.payload === 'object' && !Array.isArray(result.payload)) {
      return normalizeChartPayload(result.payload);
    }
    return normalizeChartPayload({ __error__: `chart JSON must be an object: ${resolved}` });
  }
  return {};
}

function normalizeTablePayload(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  return {
    title: String(raw.title || ''),
    headers: Array.isArray(raw.headers) ? raw.headers : [],
    rows: Array.isArray(raw.rows) ? raw.rows : [],
    column_weights: Array.isArray(raw.column_weights) ? raw.column_weights : null,
    caption: String(raw.caption || ''),
    footnotes: Array.isArray(raw.footnotes) ? raw.footnotes : [],
    cell_styles: raw.cell_styles || null,
    row_styles: raw.row_styles || null,
    header_style: raw.header_style || null,
    source_path: String(raw.source_path || ''),
    source_label: String(raw.source_label || ''),
    provenance: String(raw.provenance || ''),
  };
}

function loadTablePayload(candidate, outlineDir) {
  if (!candidate) return {};
  if (candidate && typeof candidate === 'object' && !Array.isArray(candidate)) {
    return normalizeTablePayload(candidate);
  }
  const alias = lookupAssetAlias(candidate, outlineDir);
  if (alias && !alias.path && alias.entry) {
    return normalizeTablePayload(alias.entry);
  }
  const resolved = alias && alias.path ? alias.path : resolveAssetPath(candidate, outlineDir);
  if (!resolved || !fs.existsSync(resolved)) return {};
  const result = readJsonPayload(resolved);
  if (!result.error) return normalizeTablePayload(result.payload);
  try {
    throw new Error(result.error);
  } catch (err) {
    return normalizeTablePayload({
      title: 'Table artifact could not be read',
      headers: ['Error'],
      rows: [[`failed to read table JSON: ${err.message}`]],
      caption: String(candidate),
    });
  }
}

function loadTablePayloads(spec, outlineDir) {
  const assets = (spec && spec.assets && typeof spec.assets === 'object') ? spec.assets : {};
  const rawTables = Array.isArray(spec.tables)
    ? spec.tables
    : Array.isArray(spec.table_groups)
      ? spec.table_groups
      : Array.isArray(assets.tables)
        ? assets.tables
        : [];
  const tables = rawTables
    .map((item) => loadTablePayload(item, outlineDir))
    .filter((item) => Array.isArray(item.headers) && item.headers.length && Array.isArray(item.rows) && item.rows.length);
  if (tables.length) return { tables };

  const candidates = [spec.table, spec.table_data, assets.table_data, assets.table];
  for (const candidate of candidates) {
    const table = loadTablePayload(candidate, outlineDir);
    if (Array.isArray(table.headers) && table.headers.length && Array.isArray(table.rows) && table.rows.length) {
      return { table };
    }
  }
  return {};
}

function parseCsvLine(line) {
  const cells = [];
  let current = '';
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"' && quoted && line[i + 1] === '"') {
      current += '"';
      i += 1;
    } else if (ch === '"') {
      quoted = !quoted;
    } else if (ch === ',' && !quoted) {
      cells.push(current);
      current = '';
    } else {
      current += ch;
    }
  }
  cells.push(current);
  return cells;
}

function readCsv(pathname) {
  if (!pathname || !fs.existsSync(pathname)) return [];
  const lines = fs.readFileSync(pathname, 'utf8').split(/\r?\n/).filter((line) => line.trim());
  if (lines.length < 2) return [];
  const headers = parseCsvLine(lines[0]).map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    const row = {};
    headers.forEach((header, idx) => {
      row[header] = String(values[idx] || '').trim();
    });
    return row;
  });
}

function attributionPath(data, outlineDir) {
  const compliance = (data && data.compliance && typeof data.compliance === 'object')
    ? data.compliance
    : {};
  const raw = String(compliance.attribution_file || 'assets/attribution.csv').trim();
  return path.isAbsolute(raw) ? raw : path.resolve(outlineDir, raw);
}

function isSourceBackedRow(row) {
  const license = String(row.license || '').trim().toLowerCase();
  const sourcePage = String(row.source_page || '').trim();
  const imageUrl = String(row.image_url || '').trim();
  if (!license && !sourcePage && !imageUrl) return false;
  if (license === 'generated asset') return false;
  return /^https?:/i.test(sourcePage) || /^https?:/i.test(imageUrl) || license.startsWith('cc') || license.includes('public');
}

function compactUrl(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  try {
    const u = new URL(raw);
    const tail = u.pathname.split('/').filter(Boolean).pop() || '';
    return `${u.hostname}/${decodeURIComponent(tail).slice(0, 46)}`;
  } catch (_err) {
    return raw.slice(0, 62);
  }
}

function trimCell(value, limit) {
  const raw = String(value || '').replace(/\s+/g, ' ').trim();
  if (raw.length <= limit) return raw;
  return `${raw.slice(0, Math.max(4, limit - 1)).trim()}…`;
}

function hasImageSourcesSlide(slideList) {
  return slideList.some((slide) => {
    if (!slide || typeof slide !== 'object') return false;
    const variant = String(slide.variant || '').trim().toLowerCase();
    const title = String(slide.title || '').trim().toLowerCase();
    return variant === 'image-sources' || title === 'image sources' || title === 'asset sources';
  });
}

function withAutoImageSourcesSlide(slideList, data, outlineDir) {
  const compliance = (data && data.compliance && typeof data.compliance === 'object')
    ? data.compliance
    : {};
  if (compliance.auto_image_sources === false) return slideList;
  if (hasImageSourcesSlide(slideList)) return slideList;

  const rows = readCsv(attributionPath(data, outlineDir)).filter(isSourceBackedRow);
  if (!rows.length) return slideList;

  const visibleRows = rows.slice(0, 8).map((row) => {
    const title = row.title || row.file_name || 'Source-backed image';
    const credit = row.artist || row.credit || 'Wikimedia Commons';
    const license = row.license || 'source-backed';
    const source = row.source_page || row.image_url || '';
    return [
      trimCell(title, 42),
      trimCell(credit, 50),
      trimCell(`${license} · ${compactUrl(source)}`, 72),
    ];
  });
  const caption = rows.length > visibleRows.length
    ? `Showing first ${visibleRows.length} of ${rows.length} source-backed assets. Full attribution: assets/attribution.csv.`
    : 'Full attribution metadata is stored in assets/attribution.csv.';

  return slideList.concat([
    {
      type: 'content',
      variant: 'table',
      title: 'Image Sources',
      subtitle: 'Source-backed assets used in this deck',
      headers: ['Asset', 'Credit', 'License / source'],
      rows: visibleRows,
      column_weights: [1.25, 1.35, 1.70],
      caption,
      footer_mode: 'source-line',
      footer: 'Automatically generated from asset attribution metadata',
      sources: ['assets/attribution.csv'],
    },
  ]);
}

// ---------------------------------------------------------------------------
// Slide dispatch
// ---------------------------------------------------------------------------

const CONTENT_VARIANTS = new Set([
  'standard',
  'cards-2',
  'cards-3',
  'split',
  'timeline',
  'stats',
  'kpi-hero',
  'table',
  'lab-run-results',
  'comparison-2col',
  'matrix',
  'flow',
  'chart',
  'image-sidebar',
  'scientific-figure',
  'generated-image',
]);

// Variants we know we don't handle in v1. Fall back to 'standard' with a warn.
const UNSUPPORTED_VARIANTS = new Set([
  'hero',
  'comparison',
]);

const FONT_PAIRS = {
  system_clean_v1: {
    font_heading: 'Trebuchet MS',
    font_body: 'Calibri',
  },
  editorial_serif_v1: {
    font_heading: 'Georgia',
    font_body: 'Calibri',
  },
  clean_modern_v1: {
    font_heading: 'Helvetica Neue',
    font_body: 'Helvetica Neue',
  },
};

const PALETTE_LIBRARY = {
  climate_coastal_v1: {
    bg: 'ECFEFF',
    bg_dark: '082F49',
    surface: 'FFFFFF',
    text: '0C4A6E',
    text_muted: '155E75',
    accent_primary: '0EA5E9',
    accent_secondary: '14B8A6',
    line: 'BAE6FD',
  },
  energy_sunset_v1: {
    bg: 'F6F8F5',
    bg_dark: '173B3F',
    surface: 'FFFFFF',
    text: '243133',
    text_muted: '5F6F70',
    accent_primary: 'C65D3B',
    accent_secondary: '2F7D76',
    line: 'D9DED8',
  },
  enterprise_graphite_v1: {
    bg: 'F8FAFC',
    bg_dark: '111827',
    surface: 'FFFFFF',
    text: '111827',
    text_muted: '4B5563',
    accent_primary: '2563EB',
    accent_secondary: '0891B2',
    line: 'D1D5DB',
  },
  lab_monochrome_v1: {
    bg: 'FFFFFF',
    bg_dark: '171717',
    surface: 'FFFFFF',
    text: '171717',
    text_muted: '525252',
    accent_primary: '171717',
    accent_secondary: 'B42318',
    line: 'D4D4D4',
    title_subtitle_color: 'E5E5E5',
    section_subtitle_color: 'E5E5E5',
  },
  journal_monochrome_v1: {
    bg: 'FFFFFF',
    bg_dark: '202020',
    surface: 'FFFFFF',
    text: '111111',
    text_muted: '525252',
    accent_primary: '111111',
    accent_secondary: '315A74',
    line: 'D9D9D9',
    title_subtitle_color: 'E8ECEF',
    section_subtitle_color: 'E8ECEF',
  },
};

const PRESET_TREATMENTS = {
  'executive-clinical': {
    page_system: 'clinical-rail',
    structural_motif: 'clinical-stages',
    header_mode: 'bar',
    title_layout: 'split-hero',
    title_motif: 'orbit',
    section_motif: 'rail-dots',
    timeline_mode: 'staggered',
    matrix_mode: 'cards',
    stats_mode: 'feature-left',
    cards_mode: 'feature-left',
    image_sidebar_mode: 'evidence-mosaic',
    comparison_mode: 'scorecard',
    chart_treatment: 'threshold-band',
    table_treatment: 'readout-sidecar',
    figure_table_treatment: 'figure-first',
    summary_callout_mode: 'lab-box',
    footer_mode: 'source-line',
  },
  'data-heavy-boardroom': {
    page_system: 'board-ledger',
    structural_motif: 'board-index',
    header_mode: 'eyebrow',
    title_layout: 'split-hero',
    title_motif: 'network',
    section_motif: 'rail-dots',
    timeline_mode: 'open-events',
    matrix_mode: 'open-quadrants',
    stats_mode: 'policy-bands',
    cards_mode: 'feature-left',
    image_sidebar_mode: 'analysis-rail',
    comparison_mode: 'scorecard',
    chart_treatment: 'facts-right',
    table_treatment: 'compact-ledger',
    figure_table_treatment: 'table-first',
    summary_callout_mode: 'default',
    footer_mode: 'source-line',
  },
  'forest-research': {
    page_system: 'lab-plate',
    structural_motif: 'field-notes',
    header_mode: 'stack',
    title_layout: 'light-atlas',
    title_motif: 'editorial',
    section_motif: 'rail-dots',
    timeline_mode: 'open-events',
    matrix_mode: 'open-quadrants',
    stats_mode: 'policy-bands',
    cards_mode: 'staggered-row',
    image_sidebar_mode: 'editorial-atlas',
    comparison_mode: 'open-columns',
    chart_treatment: 'sparse-wide',
    table_treatment: 'journal-grid',
    figure_table_treatment: 'figure-first',
    summary_callout_mode: 'lab-box',
    footer_mode: 'source-line',
  },
  'sunset-investor': {
    page_system: 'investor-thesis',
    structural_motif: 'thesis-window',
    header_mode: 'bar',
    title_layout: 'poster',
    title_motif: 'orbit',
    section_motif: 'rail-dots',
    timeline_mode: 'chapter-spread',
    matrix_mode: 'open-quadrants',
    stats_mode: 'feature-left',
    cards_mode: 'feature-left',
    image_sidebar_mode: 'evidence-mosaic',
    comparison_mode: 'scorecard',
    chart_treatment: 'hero-stat',
    table_treatment: 'compact-ledger',
    figure_table_treatment: 'stats-strip',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'lavender-ops': {
    page_system: 'command-canvas',
    structural_motif: 'workflow-brackets',
    header_mode: 'eyebrow',
    title_layout: 'command-center',
    title_motif: 'network',
    section_motif: 'rail-dots',
    timeline_mode: 'bands',
    matrix_mode: 'cards',
    stats_mode: 'policy-bands',
    cards_mode: 'staggered-row',
    image_sidebar_mode: 'analysis-rail',
    comparison_mode: 'scorecard',
    chart_treatment: 'facts-right',
    table_treatment: 'readout-sidecar',
    figure_table_treatment: 'table-first',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'warm-terracotta': {
    page_system: 'editorial-field',
    structural_motif: 'case-margin',
    header_mode: 'stack',
    title_layout: 'masthead',
    title_motif: 'editorial',
    section_motif: 'rail-dots',
    timeline_mode: 'bands',
    matrix_mode: 'open-quadrants',
    stats_mode: 'feature-left',
    cards_mode: 'staggered-row',
    image_sidebar_mode: 'editorial-atlas',
    comparison_mode: 'scorecard',
    chart_treatment: 'facts-below',
    table_treatment: 'journal-grid',
    figure_table_treatment: 'image-sidebar',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'paper-journal': {
    page_system: 'editorial-field',
    structural_motif: 'journal-folio',
    header_mode: 'stack',
    title_layout: 'masthead',
    title_motif: 'editorial',
    section_motif: 'rail-dots',
    timeline_mode: 'open-events',
    matrix_mode: 'open-quadrants',
    stats_mode: 'tiles',
    cards_mode: 'staggered-row',
    title_subtitle_color: 'D9CBA8',
    section_subtitle_color: 'EFE5D0',
    image_sidebar_mode: 'editorial-atlas',
    comparison_mode: 'open-columns',
    chart_treatment: 'sparse-wide',
    table_treatment: 'journal-grid',
    figure_table_treatment: 'figure-first',
    summary_callout_mode: 'lab-box',
    footer_mode: 'source-line',
  },
  'editorial-minimal': {
    page_system: 'editorial-field',
    structural_motif: 'editorial-rule',
    header_mode: 'stack',
    title_layout: 'broadsheet',
    title_motif: 'editorial',
    section_motif: 'rail-dots',
    timeline_mode: 'open-events',
    matrix_mode: 'open-quadrants',
    stats_mode: 'feature-left',
    cards_mode: 'staggered-row',
    title_subtitle_color: 'E5E7EB',
    section_subtitle_color: 'E5E7EB',
    image_sidebar_mode: 'editorial-atlas',
    comparison_mode: 'open-columns',
    chart_treatment: 'minimal',
    table_treatment: 'journal-grid',
    figure_table_treatment: 'image-sidebar',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'arctic-minimal': {
    page_system: 'clinical-rail',
    structural_motif: 'open-coordinate',
    header_mode: 'eyebrow',
    title_layout: 'light-atlas',
    title_motif: 'orbit',
    section_motif: 'rail-dots',
    matrix_mode: 'open-quadrants',
    stats_mode: 'tiles',
    cards_mode: 'staggered-row',
    image_sidebar_mode: 'editorial-atlas',
    comparison_mode: 'open-columns',
    chart_treatment: 'minimal',
    table_treatment: 'standard',
    figure_table_treatment: 'image-sidebar',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'bold-startup-narrative': {
    page_system: 'investor-thesis',
    structural_motif: 'proof-stage',
    header_mode: 'eyebrow',
    title_layout: 'poster',
    title_motif: 'orbit',
    section_motif: 'rail-dots',
    timeline_mode: 'chapter-spread',
    cards_mode: 'feature-left',
    image_sidebar_mode: 'evidence-mosaic',
    comparison_mode: 'scorecard',
    chart_treatment: 'hero-stat',
    table_treatment: 'decision-matrix',
    figure_table_treatment: 'stats-strip',
    stats_mode: 'feature-left',
    matrix_mode: 'cards',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'charcoal-safety': {
    page_system: 'board-ledger',
    structural_motif: 'incident-rail',
    header_mode: 'bar',
    title_layout: 'command-center',
    title_motif: 'network',
    section_motif: 'rail-dots',
    stats_mode: 'policy-bands',
    matrix_mode: 'cards',
    cards_mode: 'staggered-row',
    timeline_mode: 'bands',
    title_subtitle_color: 'D1D5DB',
    section_subtitle_color: 'E5E7EB',
    image_sidebar_mode: 'analysis-rail',
    comparison_mode: 'scorecard',
    chart_treatment: 'threshold-band',
    table_treatment: 'decision-matrix',
    figure_table_treatment: 'stats-strip',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'midnight-neon': {
    page_system: 'command-canvas',
    structural_motif: 'signal-grid',
    header_mode: 'bar',
    title_layout: 'command-center',
    title_motif: 'network',
    section_motif: 'rail-dots',
    timeline_mode: 'chapter-spread',
    cards_mode: 'feature-left',
    image_sidebar_mode: 'evidence-mosaic',
    comparison_mode: 'scorecard',
    chart_treatment: 'facts-right',
    table_treatment: 'readout-sidecar',
    figure_table_treatment: 'image-sidebar',
    stats_mode: 'tiles',
    matrix_mode: 'cards',
    summary_callout_mode: 'default',
    footer_mode: 'standard',
  },
  'lab-report': {
    page_system: 'lab-plate',
    structural_motif: 'assay-register',
    header_mode: 'lab-clean',
    header_variant: 'auto',
    header_variants: ['left-accent', 'split-rule', 'title-rule', 'side-rail', 'top-bottom-rule', 'plain'],
    header_rule_color: 'accent_secondary',
    footer_mode: 'source-line',
    footer_page_numbers: true,
    footer_source_label: 'Sources',
    footer_refs_label: 'Refs',
    summary_callout_mode: 'lab-box',
    title_layout: 'lab-plate',
    title_motif: 'none',
    section_motif: 'none',
    title_subtitle_color: 'D6E4F0',
    section_subtitle_color: 'D6E4F0',
    image_sidebar_mode: 'evidence-mosaic',
    comparison_mode: 'scorecard',
    chart_treatment: 'threshold-band',
    table_treatment: 'compact-ledger',
    figure_table_treatment: 'figure-first',
    stats_mode: 'tiles',
    matrix_mode: 'cards',
  },
};

const HEADER_VARIANTS_BY_PRESET = {
  'executive-clinical': ['left-accent', 'split-rule', 'top-bottom-rule', 'plain'],
  'data-heavy-boardroom': ['split-rule', 'left-accent', 'top-bottom-rule', 'plain'],
  'forest-research': ['left-accent', 'split-rule', 'plain', 'top-bottom-rule'],
  'sunset-investor': ['title-rule', 'left-accent', 'side-rail', 'split-rule'],
  'lavender-ops': ['split-rule', 'left-accent', 'plain', 'top-bottom-rule'],
  'warm-terracotta': ['split-rule', 'title-rule', 'left-accent', 'plain'],
  'paper-journal': ['split-rule', 'top-bottom-rule', 'plain', 'title-rule'],
  'editorial-minimal': ['title-rule', 'plain', 'split-rule', 'left-accent'],
  'arctic-minimal': ['plain', 'split-rule', 'title-rule', 'left-accent'],
  'bold-startup-narrative': ['left-accent', 'title-rule', 'side-rail', 'split-rule'],
  'charcoal-safety': ['side-rail', 'title-rule', 'split-rule', 'plain'],
  'midnight-neon': ['side-rail', 'split-rule', 'title-rule', 'plain'],
  'lab-report': ['left-accent', 'split-rule', 'title-rule', 'side-rail', 'top-bottom-rule', 'plain'],
};

// Keep the exported treatment catalog on the same denominator as the Python
// resolver. Consumers that inspect the catalog directly should see the same
// automatic cross-preset header behavior used during rendering.
for (const [presetName, treatment] of Object.entries(PRESET_TREATMENTS)) {
  if (!treatment.header_variant) treatment.header_variant = 'auto';
  treatment.header_variants = HEADER_VARIANTS_BY_PRESET[presetName].slice();
}

const ROLE_SYSTEMS_BY_GRAMMAR = {
  'consulting-answer-pyramid': {
    title: 'title-answer-ledger',
    section: 'section-claim-chapters',
    evidence: 'evidence-proof-stack',
    comparison: 'comparison-option-scorecard',
    data: 'data-executive-exhibit',
    decision: 'decision-owner-commitment',
    references: 'references-executive-notes',
  },
  'scientific-evidence-plate': {
    title: 'title-study-plate',
    section: 'section-method-result',
    evidence: 'evidence-multipanel-plate',
    comparison: 'comparison-control-cohort',
    data: 'data-assay-readout',
    decision: 'decision-evidence-threshold',
    references: 'references-scientific-register',
  },
  'clinical-care-pathway': {
    title: 'title-clinical-status',
    section: 'section-care-stage',
    evidence: 'evidence-clinical-cohort',
    comparison: 'comparison-care-options',
    data: 'data-clinical-outcomes',
    decision: 'decision-care-gate',
    references: 'references-clinical-evidence',
  },
  'editorial-spread': {
    title: 'title-editorial-masthead',
    section: 'section-editorial-folio',
    evidence: 'evidence-captioned-feature',
    comparison: 'comparison-editorial-columns',
    data: 'data-annotated-graphic',
    decision: 'decision-editorial-takeaway',
    references: 'references-editorial-notes',
  },
  'investor-thesis-stage': {
    title: 'title-investor-thesis',
    section: 'section-thesis-stage',
    evidence: 'evidence-market-proof',
    comparison: 'comparison-market-position',
    data: 'data-unit-economics',
    decision: 'decision-investment-ask',
    references: 'references-investor-diligence',
  },
  'operations-grid': {
    title: 'title-operations-state',
    section: 'section-operating-cycle',
    evidence: 'evidence-operations-signal',
    comparison: 'comparison-plan-actual',
    data: 'data-operations-grid',
    decision: 'decision-control-action',
    references: 'references-operations-log',
  },
  'policy-public-docket': {
    title: 'title-public-question',
    section: 'section-policy-docket',
    evidence: 'evidence-public-record',
    comparison: 'comparison-policy-options',
    data: 'data-public-impact',
    decision: 'decision-policy-recommendation',
    references: 'references-public-docket',
  },
  'technical-telemetry-canvas': {
    title: 'title-telemetry-state',
    section: 'section-system-layer',
    evidence: 'evidence-signal-trace',
    comparison: 'comparison-architecture-tradeoff',
    data: 'data-telemetry-canvas',
    decision: 'decision-remediation-gate',
    references: 'references-technical-register',
  },
};

const GRAMMAR_BY_PRESET = {
  'arctic-minimal': 'consulting-answer-pyramid',
  'data-heavy-boardroom': 'consulting-answer-pyramid',
  'lab-report': 'scientific-evidence-plate',
  'forest-research': 'scientific-evidence-plate',
  'executive-clinical': 'clinical-care-pathway',
  'editorial-minimal': 'editorial-spread',
  'paper-journal': 'editorial-spread',
  'bold-startup-narrative': 'investor-thesis-stage',
  'sunset-investor': 'investor-thesis-stage',
  'lavender-ops': 'operations-grid',
  'charcoal-safety': 'operations-grid',
  'warm-terracotta': 'policy-public-docket',
  'midnight-neon': 'technical-telemetry-canvas',
};

for (const [presetName, grammarId] of Object.entries(GRAMMAR_BY_PRESET)) {
  if (!PRESET_TREATMENTS[presetName]) continue;
  PRESET_TREATMENTS[presetName].composition_grammar = grammarId;
  PRESET_TREATMENTS[presetName].role_systems = Object.assign({}, ROLE_SYSTEMS_BY_GRAMMAR[grammarId]);
}

const STYLE_ENUM_VALUES = {
  visual_density: new Set(['low', 'medium', 'high']),
  page_system: new Set(['clinical-rail', 'board-ledger', 'editorial-field', 'command-canvas', 'lab-plate', 'investor-thesis', 'none']),
  structural_motif: new Set([
    'clinical-stages',
    'board-index',
    'field-notes',
    'thesis-window',
    'workflow-brackets',
    'case-margin',
    'journal-folio',
    'editorial-rule',
    'open-coordinate',
    'proof-stage',
    'incident-rail',
    'signal-grid',
    'assay-register',
    'none',
  ]),
  header_mode: new Set(['bar', 'stack', 'eyebrow', 'lab-clean', 'lab-card']),
  header_variant: new Set([
    'auto',
    'left-accent',
    'split-rule',
    'title-rule',
    'side-rail',
    'top-bottom-rule',
    'plain',
  ]),
  title_layout: new Set([
    'split-hero',
    'lab-plate',
    'command-center',
    'poster',
    'masthead',
    'light-atlas',
    'broadsheet',
    'telemetry-board',
  ]),
  title_motif: new Set(['orbit', 'network', 'editorial', 'none']),
  section_motif: new Set(['rail-dots', 'numbered-tabs', 'plain', 'none']),
  timeline_mode: new Set(['rail-cards', 'staggered', 'open-events', 'bands', 'chapter-spread']),
  matrix_mode: new Set(['cards', 'open-quadrants']),
  stats_mode: new Set(['tiles', 'feature-left', 'policy-bands']),
  cards_mode: new Set(['feature-left', 'staggered-row']),
  chart_treatment: new Set([
    'standard',
    'facts-below',
    'facts-right',
    'minimal',
    'hero-stat',
    'threshold-band',
    'sparse-wide',
  ]),
  table_treatment: new Set(['standard', 'compact-ledger', 'readout-sidecar', 'decision-matrix', 'journal-grid']),
  footer_mode: new Set(['standard', 'source-line', 'none']),
  summary_callout_mode: new Set(['default', 'lab-box']),
  figure_table_treatment: new Set(['figure-first', 'table-first', 'stats-strip', 'image-sidebar']),
  image_sidebar_mode: new Set(['analysis-rail', 'evidence-mosaic', 'editorial-atlas']),
  comparison_mode: new Set(['open-columns', 'scorecard']),
  composition_grammar: new Set(Object.keys(ROLE_SYSTEMS_BY_GRAMMAR)),
  role_layout_variant: new Set(['primary', 'alternate', 'dense']),
};

const ROOT_STYLE_ENUM_KEYS = Object.keys(STYLE_ENUM_VALUES).filter((key) => key !== 'role_layout_variant');
const SLIDE_STYLE_ENUM_KEYS = [
  'header_mode',
  'page_system',
  'structural_motif',
  'header_variant',
  'title_layout',
  'timeline_mode',
  'matrix_mode',
  'stats_mode',
  'cards_mode',
  'chart_treatment',
  'table_treatment',
  'footer_mode',
  'summary_callout_mode',
  'figure_table_treatment',
  'image_sidebar_mode',
  'comparison_mode',
  'composition_grammar',
  'role_layout_variant',
];

const ROLE_SYSTEM_KEYS = ['title', 'section', 'evidence', 'comparison', 'data', 'decision', 'references'];

function sortedSetValues(values) {
  return Array.from(values).sort().join(', ');
}

function canonicalStyleValue(payload, key, pathLabel) {
  if (!Object.prototype.hasOwnProperty.call(payload, key)) return '';
  const value = payload[key];
  if (typeof value !== 'string') {
    throw new Error(`${pathLabel}.${key} must be a string when present.`);
  }
  const text = value.trim();
  if (!text) return '';
  const allowed = STYLE_ENUM_VALUES[key];
  if (!allowed) return text;
  const normalized = text.toLowerCase();
  if (!allowed.has(normalized)) {
    throw new Error(
      `Unsupported ${pathLabel}.${key} value '${text}'. Valid values: ${sortedSetValues(allowed)}.`
    );
  }
  return normalized;
}

function canonicalHeaderVariants(payload, pathLabel) {
  if (!Object.prototype.hasOwnProperty.call(payload, 'header_variants')) return [];
  if (!Array.isArray(payload.header_variants)) {
    throw new Error(`${pathLabel}.header_variants must be an array when present.`);
  }
  const allowed = STYLE_ENUM_VALUES.header_variant;
  return payload.header_variants
    .map((item, idx) => {
      if (typeof item !== 'string') {
        throw new Error(`${pathLabel}.header_variants[${idx}] must be a string.`);
      }
      const text = item.trim();
      if (!text) return '';
      const normalized = text.toLowerCase();
      if (!allowed.has(normalized)) {
        throw new Error(
          `Unsupported ${pathLabel}.header_variants[${idx}] value '${text}'. ` +
            `Valid values: ${sortedSetValues(allowed)}.`
        );
      }
      return normalized;
    })
    .filter(Boolean);
}

function validateStyleTreatmentPayload(payload, pathLabel, keys) {
  if (payload === undefined || payload === null) return;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`${pathLabel} must be an object when present.`);
  }
  keys.forEach((key) => {
    canonicalStyleValue(payload, key, pathLabel);
  });
  canonicalHeaderVariants(payload, pathLabel);
  if (Object.prototype.hasOwnProperty.call(payload, 'role_systems')) {
    if (!payload.role_systems || typeof payload.role_systems !== 'object' || Array.isArray(payload.role_systems)) {
      throw new Error(`${pathLabel}.role_systems must be an object when present.`);
    }
    for (const [role, systemId] of Object.entries(payload.role_systems)) {
      if (!ROLE_SYSTEM_KEYS.includes(role)) {
        throw new Error(`${pathLabel}.role_systems has unsupported role '${role}'.`);
      }
      if (typeof systemId !== 'string' || !systemId.trim()) {
        throw new Error(`${pathLabel}.role_systems.${role} must be a non-empty string.`);
      }
    }
  }
}

function validateOutlineStyleTreatments(data) {
  validateStyleTreatmentPayload(data.deck_style, 'deck_style', ROOT_STYLE_ENUM_KEYS);
  const slideList = Array.isArray(data.slides) ? data.slides : [];
  slideList.forEach((slide, idx) => {
    if (!slide || typeof slide !== 'object' || Array.isArray(slide)) return;
    validateStyleTreatmentPayload(slide, `slides[${idx}]`, SLIDE_STYLE_ENUM_KEYS);
  });
}

function applyDeckStyle(basePreset, data, presetName) {
  const preset = Object.assign({}, basePreset);
  preset.style_preset = String(presetName || '').trim().toLowerCase();
  const treatment = PRESET_TREATMENTS[String(presetName || '').trim().toLowerCase()] || {};
  Object.assign(preset, treatment);
  preset.role_systems = Object.assign({}, treatment.role_systems || {});
  if (!preset.header_variant) {
    preset.header_variant = 'auto';
  }
  if (!Array.isArray(preset.header_variants)) {
    preset.header_variants = ['left-accent', 'split-rule', 'title-rule', 'side-rail', 'top-bottom-rule', 'plain'];
  }

  const deckStyle = (data && data.deck_style && typeof data.deck_style === 'object')
    ? data.deck_style
    : {};
  const metadata = data && data.metadata && typeof data.metadata === 'object'
    ? data.metadata
    : {};
  const metadataRoleContracts = metadata.renderer_role_contracts_v2
    && typeof metadata.renderer_role_contracts_v2 === 'object'
    ? metadata.renderer_role_contracts_v2
    : null;
  const deckRoleContracts = deckStyle.renderer_role_contracts_v2
    && typeof deckStyle.renderer_role_contracts_v2 === 'object'
    ? deckStyle.renderer_role_contracts_v2
    : metadataRoleContracts;
  const metadataRoleSystems = data && data.metadata && typeof data.metadata === 'object'
    && data.metadata.renderer_role_systems_v1 && typeof data.metadata.renderer_role_systems_v1 === 'object'
    ? data.metadata.renderer_role_systems_v1
    : {};
  const deckRoleSystems = deckStyle.renderer_role_systems_v1 && typeof deckStyle.renderer_role_systems_v1 === 'object'
    ? deckStyle.renderer_role_systems_v1
    : metadataRoleSystems;
  if (deckRoleSystems.composition_grammar_id) {
    preset.composition_grammar = String(deckRoleSystems.composition_grammar_id).trim().toLowerCase();
  }
  const contractRoles = {};
  for (const role of ROLE_SYSTEM_KEYS) {
    const value = deckRoleSystems[`${role}_system_id`];
    if (typeof value === 'string' && value.trim()) contractRoles[role] = value.trim().toLowerCase();
  }
  if (Object.keys(contractRoles).length) {
    preset.role_systems = Object.assign({}, preset.role_systems, contractRoles);
    preset.renderer_role_systems_v1 = Object.assign({}, deckRoleSystems);
  }
  const paletteKey = String(deckStyle.palette_key || '').trim().toLowerCase();
  const palette = PALETTE_LIBRARY[paletteKey];
  if (palette) {
    Object.assign(preset, palette);
  }

  const fontPairKey = String(deckStyle.font_pair || '').trim();
  const fontPair = FONT_PAIRS[fontPairKey];
  if (fontPair) {
    preset.font_heading = fontPair.font_heading;
    preset.font_body = fontPair.font_body;
    preset.font_title = fontPair.font_heading;
    preset.font_caption = fontPair.font_body;
  }

  const visualDensity = canonicalStyleValue(deckStyle, 'visual_density', 'deck_style') || 'medium';
  if (visualDensity) {
    preset.visual_density = visualDensity;
  }

  for (const key of [
    'header_mode',
    'page_system',
    'structural_motif',
    'header_variant',
    'title_layout',
    'title_motif',
    'section_motif',
    'timeline_mode',
    'matrix_mode',
    'stats_mode',
    'cards_mode',
    'chart_treatment',
    'table_treatment',
    'footer_mode',
    'summary_callout_mode',
    'figure_table_treatment',
    'image_sidebar_mode',
    'comparison_mode',
    'composition_grammar',
  ]) {
    const value = canonicalStyleValue(deckStyle, key, 'deck_style');
    if (value) preset[key] = value;
  }
  if (deckStyle.role_systems && typeof deckStyle.role_systems === 'object' && !Array.isArray(deckStyle.role_systems)) {
    preset.role_systems = Object.assign({}, preset.role_systems, deckStyle.role_systems);
  }
  const headerVariants = canonicalHeaderVariants(deckStyle, 'deck_style');
  if (headerVariants.length) {
    preset.header_variants = headerVariants;
  }
  if (deckStyle.header_rule_color) {
    preset.header_rule_color = String(deckStyle.header_rule_color).trim();
  }
  if (deckStyle.style_seed) {
    preset.style_seed = String(deckStyle.style_seed).trim();
  }
  if (deckStyle.footer_source_label) {
    preset.footer_source_label = String(deckStyle.footer_source_label).trim();
  }
  if (deckStyle.footer_refs_label) {
    preset.footer_refs_label = String(deckStyle.footer_refs_label).trim();
  }
  if (deckStyle.footer_page_numbers !== undefined) {
    preset.footer_page_numbers = Boolean(deckStyle.footer_page_numbers);
  }
  if (deckStyle.readability_contract && typeof deckStyle.readability_contract === 'object') {
    preset.readability_contract = JSON.parse(JSON.stringify(deckStyle.readability_contract));
  }
  if (deckRoleContracts) {
    const failures = validateResolvedRoleContracts(deckRoleContracts);
    if (failures.length) {
      throw new Error(`Invalid renderer_role_contracts_v2: ${failures.join('; ')}`);
    }
    preset.renderer_role_contracts_v2 = JSON.parse(JSON.stringify(deckRoleContracts));
    preset.renderer_role_contract_version = ROLE_CONTRACT_VERSION;
    preset.composition_grammar = String(deckRoleContracts.composition_grammar_id).trim().toLowerCase();
    const contractRoles = deckRoleContracts.roles || {};
    for (const role of ROLE_SYSTEM_KEYS) {
      const contractRole = role === 'data' ? contractRoles.chart : contractRoles[role];
      if (contractRole && typeof contractRole.system_id === 'string' && contractRole.system_id.trim()) {
        preset.role_systems[role] = contractRole.system_id.trim().toLowerCase();
      }
    }
  } else if (deckRoleSystems && Object.keys(deckRoleSystems).length) {
    // A persisted v1-only outline is an explicit compatibility pin. It must
    // not silently adopt new geometry during a rebuild.
    preset.renderer_role_contract_version = 'renderer_role_systems_v1';
  } else {
    preset.renderer_role_contracts_v2 = contractsForGrammar(
      preset.composition_grammar,
      preset.style_preset,
    );
    preset.renderer_role_contract_version = ROLE_CONTRACT_VERSION;
    const contractRoles = preset.renderer_role_contracts_v2 && preset.renderer_role_contracts_v2.roles;
    if (contractRoles) {
      for (const role of ROLE_SYSTEM_KEYS) {
        const contractRole = role === 'data' ? contractRoles.chart : contractRoles[role];
        if (contractRole && typeof contractRole.system_id === 'string' && contractRole.system_id.trim()) {
          preset.role_systems[role] = contractRole.system_id.trim().toLowerCase();
        }
      }
    }
  }
  return preset;
}

// Pre-render a mermaid source file to PNG using the existing Python helper.
// Returns an absolute path to the PNG, or '' on failure.
function preRenderMermaid(sourcePath, outlineDir) {
  const abs = resolveAssetPath(sourcePath, outlineDir);
  if (!abs || !fs.existsSync(abs)) return '';
  const target = abs.replace(/\.(mmd|mermaid)$/i, '.png');
  const script = path.resolve(__dirname, 'render_mermaid.py');
  // Skip re-render if the PNG is already newer than the source.
  try {
    const targetMtime = fs.existsSync(target) ? fs.statSync(target).mtimeMs : 0;
    const sourceMtime = fs.statSync(abs).mtimeMs;
    const scriptMtime = fs.existsSync(script) ? fs.statSync(script).mtimeMs : 0;
    if (fs.existsSync(target) &&
        targetMtime >= sourceMtime &&
        targetMtime >= scriptMtime) {
      return target;
    }
  } catch (_e) {}
  if (!fs.existsSync(script)) {
    console.warn('[pptxgenjs] render_mermaid.py missing; skipping mermaid for', abs);
    return '';
  }
  const python = process.env.PRESENTATION_SKILL_PYTHON || process.env.PYTHON || 'python3';
  const r = spawnSync(python, [script, '--input', abs, '--output', target], {
    stdio: ['ignore', 'pipe', 'pipe'],
    encoding: 'utf8',
  });
  if (r.status === 0 && fs.existsSync(target)) return target;
  console.warn('[pptxgenjs] mermaid render failed for', abs, '-', (r.stderr || r.stdout || '').slice(0, 200));
  return '';
}

function normalizeSlide(spec, outlineDir) {
  const out = Object.assign({}, spec);
  out.type = String(spec.type || 'content').trim().toLowerCase();
  if (out.type === 'text') out.type = 'content';
  out.variant = String(spec.variant || 'standard').trim().toLowerCase();
  if (Array.isArray(out.facts)) out.facts = out.facts.map(normalizeFact);
  if (Array.isArray(out.stats)) out.stats = out.stats.map(normalizeFact);
  if (spec.background_image) {
    out.background_image = resolveAssetPath(spec.background_image, outlineDir);
  }

  // Resolve asset-family paths and pre-render mermaid to PNG.
  const assets = (spec.assets && typeof spec.assets === 'object') ? spec.assets : {};
  if (assets.hero_image || assets.image) {
    out.__heroPath = resolveAssetPath(assets.hero_image || assets.image, outlineDir);
  }
  if (assets.generated_image) {
    out.__generatedImagePath = resolveAssetPath(assets.generated_image, outlineDir);
  }
  const mermaidSrc = assets.mermaid_source || assets.mermaid;
  if (mermaidSrc) {
    const sourcePath = resolveAssetPath(mermaidSrc, outlineDir);
    if (sourcePath && fs.existsSync(sourcePath)) out.__mermaidSourcePath = sourcePath;
    const rendered = preRenderMermaid(mermaidSrc, outlineDir);
    if (rendered) out.__mermaidPath = rendered;
  }
  if (assets.diagram) {
    const p = resolveAssetPath(assets.diagram, outlineDir);
    if (p && fs.existsSync(p)) out.__diagramPath = p;
  }
  const chartPayload = loadChartPayload(spec, outlineDir);
  if (chartPayload && Object.keys(chartPayload).length) {
    out.__chartPayload = chartPayload;
    if (!Array.isArray(out.facts) && !Array.isArray(out.stats) && Array.isArray(chartPayload.facts)) {
      out.facts = chartPayload.facts;
    }
    if (!Array.isArray(out.sources) && Array.isArray(chartPayload.sources)) {
      out.sources = chartPayload.sources;
    }
    if (!out.message && chartPayload.notes) {
      out.message = chartPayload.notes;
    }
  }
  const tablePayloads = loadTablePayloads(spec, outlineDir);
  if (Array.isArray(tablePayloads.tables) && tablePayloads.tables.length) {
    out.tables = tablePayloads.tables;
    if (!Array.isArray(out.sources)) {
      const tableSources = tablePayloads.tables
        .map((table) => table.source_label || table.source_path || table.provenance)
        .filter(Boolean);
      if (tableSources.length) out.sources = tableSources;
    }
  } else if (tablePayloads.table && Object.keys(tablePayloads.table).length) {
    out.table = tablePayloads.table;
    if (!Array.isArray(out.sources)) {
      const tableSource = tablePayloads.table.source_label ||
        tablePayloads.table.source_path ||
        tablePayloads.table.provenance;
      if (tableSource) out.sources = [tableSource];
    }
  }
  const figureSpecs = Array.isArray(spec.figures)
    ? spec.figures
    : Array.isArray(assets.figures)
      ? assets.figures
      : [];
  if (figureSpecs.length) {
    out.__figurePaths = figureSpecs.map((item) => {
      if (!item) return '';
      const raw = typeof item === 'string'
        ? item
        : (item.path || item.image || item.src || item.asset || '');
      const p = resolveAssetPath(raw, outlineDir);
      return p && fs.existsSync(p) ? p : '';
    });
  }

  // If a slide has a flow diagram image (rendered mermaid or supplied
  // diagram), promote it to a synthesized 'flow' variant so renderSlide
  // can dispatch to a diagram-aware renderer. Preserve original variant
  // for downstream metadata in case callers want it.
  const hasFlow = out.__mermaidPath || out.__diagramPath || out.__mermaidSourcePath;
  if (hasFlow && (out.variant === 'standard' || out.variant === 'content' || out.variant === 'flow')) {
    out.variant = 'flow';
  }
  const visualIntent = String(out.visual_intent || '').trim().toLowerCase();
  if (out.type === 'content' && (out.variant === 'standard' || out.variant === 'content')) {
    if (Array.isArray(out.cards) && out.cards.length >= 2) {
      out.variant = out.cards.length >= 3 ? 'cards-3' : 'cards-2';
    } else if (Array.isArray(out.milestones) && out.milestones.length >= 2) {
      out.variant = 'timeline';
    } else if (Array.isArray(out.quadrants) && out.quadrants.length >= 4) {
      out.variant = 'matrix';
    } else if (Array.isArray(out.facts) && out.facts.length >= 2) {
      out.variant = 'stats';
    } else if (
      Array.isArray(out.headers) ||
      (out.table && Array.isArray(out.table.headers)) ||
      (Array.isArray(out.rows) && out.rows.length)
    ) {
      out.variant = 'table';
    } else if (Array.isArray(out.tables) && out.tables.length) {
      out.variant = 'lab-run-results';
    } else if (visualIntent === 'timeline' && Array.isArray(out.milestones) && out.milestones.length >= 2) {
      out.variant = 'timeline';
    } else if (
      visualIntent === 'comparison' &&
      out.left && typeof out.left === 'object' &&
      out.right && typeof out.right === 'object'
    ) {
      out.variant = 'comparison-2col';
    } else if (
      visualIntent === 'data' &&
      (Array.isArray(out.headers) || (out.table && Array.isArray(out.table.headers)))
    ) {
      out.variant = 'table';
    } else if (visualIntent === 'data' && Array.isArray(out.tables) && out.tables.length) {
      out.variant = 'lab-run-results';
    } else if (visualIntent === 'data' && out.__chartPayload) {
      out.variant = 'chart';
    }
  }
  if (
    out.type === 'content' &&
    out.__heroPath &&
    fs.existsSync(out.__heroPath) &&
    out.variant !== 'generated-image' &&
    (
      out.variant === 'image-sidebar' ||
      ['hero', 'image', 'figure'].includes(String(out.visual_intent || '').trim().toLowerCase())
    )
  ) {
    out.variant = 'image-sidebar';
  }
  return out;
}

function renderSlide(pptx, pSlide, slide, preset) {
  const renderPlan = slide.__renderPlan || resolveRenderPlan(slide, preset);
  slide.__renderPlan = renderPlan;

  const finalizeRenderReceipt = (executedVariant) => {
    const execution = slide.__roleContractExecution && typeof slide.__roleContractExecution === 'object'
      ? slide.__roleContractExecution
      : null;
    const plannedV2 = renderPlan.contractSource === 'v2' && String(renderPlan.adapter || '').startsWith('v2:');
    const contractApplied = Boolean(
      execution && execution.applied && execution.adapter === renderPlan.adapter,
    );
    slide.__renderReceipt = {
      schema_version: 'renderer-execution-receipt/v1',
      planned_adapter: renderPlan.adapter,
      planned_contract_source: renderPlan.contractSource,
      executed_adapter: execution ? execution.adapter : `renderer:${executedVariant}`,
      adapter_executed: true,
      contract_applied: contractApplied,
      canonical_role: renderPlan.canonicalRole,
      effective_variant: executedVariant,
      grammar_id: execution ? execution.grammar_id : '',
      system_id: execution ? execution.system_id : '',
      layout_variant: execution ? execution.layout_variant : '',
      consumed_slots: execution ? execution.consumed_slots : [],
      adaptation: execution ? String(execution.adaptation || '') : '',
      source_system_id: execution ? String(execution.source_system_id || '') : '',
      fallback_reason: plannedV2 && !contractApplied
        ? `planned_v2_adapter_not_applied:${renderPlan.adapter}`
        : renderPlan.fallbackReason,
    };
    return slide.__renderReceipt;
  };

  if (renderPlan.effectiveVariant === 'title') {
    slides.renderTitle(pptx, pSlide, slide, preset);
    finalizeRenderReceipt('title');
    return;
  }
  if (renderPlan.effectiveVariant === 'section') {
    slides.renderSection(pptx, pSlide, slide, preset);
    finalizeRenderReceipt('section');
    return;
  }

  // Skip the universal summary callout when the variant already carries
  // its own bottom emphasis (kpi-hero IS the callout; comparison-2col
  // with a verdict already has a strip). Matches the python dispatcher.
  const variantForCallout = renderPlan.effectiveVariant;
  const hasVerdict = !!String(slide.verdict || '').trim();
  const imageSidebarMode = String(slide.image_sidebar_mode || preset.image_sidebar_mode || '').trim().toLowerCase();
  const skipCallout =
    variantForCallout === 'kpi-hero' ||
    variantForCallout === 'generated-image' ||
    (variantForCallout === 'image-sidebar' && ['evidence-mosaic', 'editorial-atlas'].includes(imageSidebarMode)) ||
    (variantForCallout === 'comparison-2col' && hasVerdict);

  // content variants
  let variant = renderPlan.effectiveVariant;
  if (UNSUPPORTED_VARIANTS.has(variant)) {
    if (variant === 'matrix') {
      // Kept for older versions where matrix lived in UNSUPPORTED_VARIANTS.
      // Native matrix rendering is now implemented below.
      console.warn(
        `[pptxgenjs] matrix was unexpectedly marked unsupported; falling back to 'standard'.`,
      );
    } else {
      console.warn(
        `[pptxgenjs] variant '${variant}' is not implemented in v1; ` +
          `falling back to 'standard'. Use build_deck.py for that variant.`,
      );
    }
    variant = 'standard';
  }
  if (!CONTENT_VARIANTS.has(variant)) {
    console.warn(`[pptxgenjs] unknown variant '${variant}'; rendering as 'standard'.`);
    variant = 'standard';
  }

  switch (variant) {
    case 'cards-2':
      slides.renderCards(pptx, pSlide, slide, preset, 2);
      break;
    case 'cards-3':
      slides.renderCards(pptx, pSlide, slide, preset, 3);
      break;
    case 'split':
      slides.renderSplit(pptx, pSlide, slide, preset);
      break;
    case 'timeline':
      slides.renderTimeline(pptx, pSlide, slide, preset);
      break;
    case 'stats':
      slides.renderStats(pptx, pSlide, slide, preset);
      break;
    case 'kpi-hero':
      slides.renderKpiHero(pptx, pSlide, slide, preset);
      break;
    case 'table':
      slides.renderTable(pptx, pSlide, slide, preset);
      break;
    case 'lab-run-results':
      slides.renderLabRunResults(pptx, pSlide, slide, preset);
      break;
    case 'comparison-2col':
      slides.renderComparison2col(pptx, pSlide, slide, preset);
      break;
    case 'matrix':
      slides.renderMatrix(pptx, pSlide, slide, preset);
      break;
    case 'flow':
      slides.renderFlow(pptx, pSlide, slide, preset);
      break;
    case 'chart':
      slides.renderChart(pptx, pSlide, slide, preset);
      break;
    case 'image-sidebar':
      slides.renderImageSidebar(pptx, pSlide, slide, preset);
      break;
    case 'scientific-figure':
      slides.renderScientificFigure(pptx, pSlide, slide, preset);
      break;
    case 'generated-image':
      slides.renderGeneratedImage(pptx, pSlide, slide, preset);
      break;
    case 'standard':
    default:
      slides.renderStandard(pptx, pSlide, slide, preset);
      break;
  }
  if (!skipCallout && !slide.__roleContractConsumesSummary) {
    slides.addSummaryCallout(pptx, pSlide, slide, preset);
  }
  finalizeRenderReceipt(variant);
}

function attachAccessibilityDefaults(pSlide, slideData) {
  const slideTitle = String(slideData.title || slideData.section_title || 'Untitled slide').trim();
  const figure = slideData.figure && typeof slideData.figure === 'object' ? slideData.figure : {};
  const imageGeneration = slideData.image_generation && typeof slideData.image_generation === 'object'
    ? slideData.image_generation
    : {};
  const visualAlt = [
    slideData.image_alt_text,
    slideData.figure_alt_text,
    slideData.alt_text,
    figure.alt_text,
    figure.caption,
    slideData.figure_caption,
    slideData.caption,
    imageGeneration.alt_text,
  ].map((value) => String(value || '').trim()).find(Boolean) || '';

  const originalAddImage = pSlide.addImage.bind(pSlide);
  pSlide.addImage = (options = {}) => {
    const next = { ...options };
    const x = Number(next.x || 0);
    const y = Number(next.y || 0);
    const w = Number(next.w || 0);
    const h = Number(next.h || 0);
    const area = w * h;
    const isBackground = x <= 0.02 && y <= 0.02
      && w >= slides.SLIDE_W * 0.95 && h >= slides.SLIDE_H * 0.95;
    const isDecorative = isBackground || area <= 0.22;
    if (!next.objectName) {
      next.objectName = isDecorative
        ? `decorative-${isBackground ? 'background' : 'icon'}`
        : `Content visual - ${slideTitle}`;
    }
    if (!isDecorative && !next.altText && visualAlt) {
      next.altText = visualAlt;
    }
    return originalAddImage(next);
  };

  const originalAddChart = pSlide.addChart.bind(pSlide);
  pSlide.addChart = (type, series, options = {}) => {
    const next = { ...options };
    const chartSeries = Array.isArray(series) ? series : [];
    const seriesNames = chartSeries
      .map((item) => String((item && item.name) || '').trim())
      .filter(Boolean)
      .slice(0, 4);
    const categories = chartSeries
      .flatMap((item) => Array.isArray(item && item.labels) ? item.labels : [])
      .map((item) => String(item || '').trim())
      .filter(Boolean)
      .filter((item, index, values) => values.indexOf(item) === index)
      .slice(0, 6);
    if (!next.objectName) next.objectName = `Chart - ${slideTitle}`;
    if (!next.altText) {
      const seriesClause = seriesNames.length ? ` Series: ${seriesNames.join(', ')}.` : '';
      const categoryClause = categories.length ? ` Categories: ${categories.join(', ')}.` : '';
      next.altText = String(
        slideData.chart_alt_text
        || slideData.alt_text
        || `Chart supporting ${slideTitle}.${seriesClause}${categoryClause}`,
      ).trim();
    }
    return originalAddChart(type, series, next);
  };
}

// ---------------------------------------------------------------------------
// Icon pre-resolution: rasterize react-icons slugs to PNG before slide render.
// ---------------------------------------------------------------------------

// Shared cache dir — icon PNGs are content-addressable (same slug+color+size
// → same PNG), so sharing across slides and across runs is safe.
const ICON_CACHE_DIR = path.join(os.tmpdir(), 'presentation-skill-icon-cache');

function iconCacheKey(slug, color, size) {
  // Filesystem-safe filename: replace ':' → '__', '#' → '', lowercase.
  const safeSlug = String(slug).replace(/[^\w-]/g, '_');
  const safeColor = String(color || '000000').replace(/[^\w]/g, '').toLowerCase();
  return path.join(ICON_CACHE_DIR, `${safeSlug}_${safeColor}_${size}.png`);
}

async function rasterizeIcon(slug, color, size) {
  const outPath = iconCacheKey(slug, color, size);
  if (fs.existsSync(outPath)) return outPath;
  fs.mkdirSync(ICON_CACHE_DIR, { recursive: true });
  const [pack, exportName] = String(slug).split(':');
  if (!pack || !exportName) {
    throw new Error(`invalid icon slug "${slug}" (expected pack:ExportName)`);
  }
  const packageByPack = {
    fa6: 'react-icons/fa6',
    fa: 'react-icons/fa',
    bi: 'react-icons/bi',
    bs: 'react-icons/bs',
    md: 'react-icons/md',
    lu: 'react-icons/lu',
  };
  const packageName = packageByPack[pack];
  if (!packageName) {
    throw new Error(`unsupported icon pack "${pack}"`);
  }

  let React;
  let ReactDOMServer;
  let sharp;
  let iconModule;
  try {
    React = require('react');
    ReactDOMServer = require('react-dom/server');
    sharp = require('sharp');
    iconModule = require(packageName);
  } catch (err) {
    throw new Error(
      `missing optional icon deps (${err.message}). Run npm install once or use local PNG icons.`,
    );
  }

  const Icon = iconModule[exportName];
  if (!Icon) {
    throw new Error(`icon export "${exportName}" not found in ${packageName}`);
  }
  const cleanColor = String(color || '#000000').startsWith('#') ? String(color) : `#${color}`;
  let svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Icon, { size, color: cleanColor, title: exportName }),
  );
  if (!/\sxmlns=/.test(svg)) {
    svg = svg.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  await sharp(Buffer.from(svg)).png().toFile(outPath);
  return outPath;
}

async function resolveIconsForSlides(slides, outlineDir, preset) {
  // Resolve each slide's assets.icons array in parallel. Slugs with ':' are
  // react-icons; others are filenames and we leave them alone.
  const tasks = [];
  for (const slide of slides) {
    const assets = slide && slide.assets;
    if (!assets || !Array.isArray(assets.icons) || assets.icons.length === 0) continue;
    // Default icon color: accent_primary from preset. Individual slides can
    // override with assets.icons_color. Normalize so we always pass '#rrggbb'.
    const normHex = (v) => '#' + String(v || '').replace(/^#/, '');
    const defaultColor = normHex(preset.accent_primary || '14B8A6');
    const color = assets.icons_color ? normHex(assets.icons_color) : defaultColor;
    const resolved = new Array(assets.icons.length).fill('');
    slide.__iconPaths = resolved;
    for (let i = 0; i < assets.icons.length; i += 1) {
      const s = String(assets.icons[i] || '').trim();
      if (!s) continue;
      if (s.includes(':')) {
        // react-icons slug: pack:ExportName. Bind index in closure so the
        // promise writes to the correct slot.
        const idx = i;
        const paths = resolved;
        tasks.push(
          rasterizeIcon(s, color, 256)
            .then((p) => { paths[idx] = p; })
            .catch((err) => {
              console.warn(`[pptxgenjs] icon '${s}' failed: ${err.message}`);
              paths[idx] = '';
            })
        );
      } else {
        // Plain filename — resolve against outline dir.
        const p = path.isAbsolute(s) ? s : path.resolve(outlineDir, s);
        const withExt = /\.(png|jpg|jpeg|svg)$/i.test(p) ? p : p + '.png';
        resolved[i] = fs.existsSync(withExt) ? withExt : '';
      }
    }
  }
  await Promise.all(tasks);
}

function xmlEscape(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function replaceXmlElement(xml, qualifiedName, value) {
  const escapedName = qualifiedName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const paired = new RegExp(`<${escapedName}(?:\\s[^>]*)?>[\\s\\S]*?<\\/${escapedName}>`, 'i');
  const selfClosing = new RegExp(`<${escapedName}(?:\\s[^>]*)?\\s*\\/>`, 'i');
  const replacement = `<${qualifiedName}>${xmlEscape(value)}</${qualifiedName}>`;
  if (paired.test(xml)) return xml.replace(paired, replacement);
  if (selfClosing.test(xml)) return xml.replace(selfClosing, replacement);
  return xml;
}

async function sanitizeOfficePackageMetadata(packagePath, metadata) {
  const rewriteProperties = async (zip) => {
    const coreEntry = zip.file('docProps/core.xml');
    if (coreEntry) {
      let core = await coreEntry.async('string');
      core = replaceXmlElement(core, 'dc:creator', metadata.author);
      core = replaceXmlElement(core, 'cp:lastModifiedBy', metadata.author);
      zip.file('docProps/core.xml', core);
    }
    const appEntry = zip.file('docProps/app.xml');
    if (appEntry) {
      let app = await appEntry.async('string');
      app = replaceXmlElement(app, 'Company', metadata.company);
      zip.file('docProps/app.xml', app);
    }
  };

  const outer = await JSZip.loadAsync(fs.readFileSync(packagePath));
  await rewriteProperties(outer);
  const embeddedWorkbooks = Object.keys(outer.files)
    .filter((name) => /^ppt\/embeddings\/.*\.xlsx$/i.test(name));
  for (const workbookName of embeddedWorkbooks) {
    const entry = outer.file(workbookName);
    if (!entry) continue;
    const workbook = await JSZip.loadAsync(await entry.async('nodebuffer'));
    await rewriteProperties(workbook);
    outer.file(
      workbookName,
      await workbook.generateAsync({
        type: 'nodebuffer',
        compression: 'DEFLATE',
        compressionOptions: { level: 6 },
      }),
    );
  }
  fs.writeFileSync(
    packagePath,
    await outer.generateAsync({
      type: 'nodebuffer',
      compression: 'DEFLATE',
      compressionOptions: { level: 6 },
    }),
  );
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const args = parseArgs(process.argv);
  if (!args.outline || !args.output) {
    printUsage();
    process.exit(2);
  }

  const { data, slideList, outlineDir } = loadOutline(args.outline);
  const assetRoot = args.assetRoot ? path.resolve(args.assetRoot) : outlineDir;
  validateOutlineStyleTreatments(data);
  const preset = applyDeckStyle(getPreset(args.stylePreset), data, args.stylePreset);

  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: 'PPTX_SKILL_16x9', width: slides.SLIDE_W, height: slides.SLIDE_H });
  pptx.layout = 'PPTX_SKILL_16x9';
  pptx.title = String(data.title || 'Deck');
  pptx.subject = String(data.subtitle || '');
  const documentMetadata = data.document_metadata && typeof data.document_metadata === 'object'
    ? data.document_metadata
    : {};
  const neutralMetadata = {
    author: String(documentMetadata.author || 'Presentation Team').trim() || 'Presentation Team',
    company: String(documentMetadata.company || '').trim(),
  };
  pptx.author = neutralMetadata.author;
  pptx.company = neutralMetadata.company;

  const slidesWithSources = withAutoImageSourcesSlide(slideList, data, assetRoot);
  const normalized = slidesWithSources.map((s) => normalizeSlide(s, assetRoot));
  normalized.forEach((slide, idx) => {
    slide.__slideIndex = idx + 1;
    slide.__slideCount = normalized.length;
    slide.__renderPlan = resolveRenderPlan(slide, preset);
  });

  const renderPlanDiagnostics = args.renderPlanDiagnostics || /^(1|true|yes)$/i.test(
    String(process.env.PRESENTATION_SKILL_RENDER_PLAN_DIAGNOSTICS || ''),
  );
  if (renderPlanDiagnostics) {
    normalized.forEach((slide) => {
      console.log(`[pptxgenjs] render-plan ${JSON.stringify({
        slide: slide.__slideIndex,
        title: String(slide.title || ''),
        ...slide.__renderPlan,
      })}`);
    });
  }

  // Pre-resolve icon slugs to PNG files. Slugs with a colon (e.g.
  // "fa6:FaLightbulb") are react-icons that we rasterize on-the-fly using
  // declared npm dependencies. Plain filenames pass through unchanged — the
  // python path's workspace lookup still works if Codex staged files.
  await resolveIconsForSlides(normalized, assetRoot, preset);

  for (const slide of normalized) {
    const pSlide = pptx.addSlide();
    attachAccessibilityDefaults(pSlide, slide);
    renderSlide(pptx, pSlide, slide, preset);
  }

  const outAbs = path.resolve(args.output);
  fs.mkdirSync(path.dirname(outAbs), { recursive: true });
  await pptx.writeFile({ fileName: outAbs });

  // pptxgenjs sometimes rewrites the path (adds .pptx). Report what's on disk.
  const produced = fs.existsSync(outAbs)
    ? outAbs
    : fs.existsSync(outAbs + '.pptx')
    ? outAbs + '.pptx'
    : outAbs;
  await sanitizeOfficePackageMetadata(produced, neutralMetadata);
  console.log(`Wrote ${produced} (${normalized.length} slides, preset=${args.stylePreset})`);
}

if (require.main === module) {
  main().catch((err) => {
    console.error(`Error: ${err && err.stack ? err.stack : err}`);
    process.exit(1);
  });
}

module.exports = {
  PRESET_TREATMENTS,
  ROLE_SYSTEMS_BY_GRAMMAR,
  GRAMMAR_BY_PRESET,
  STYLE_ENUM_VALUES,
  applyDeckStyle,
  main,
  normalizeSlide,
  renderSlide,
  resolveRenderPlan,
  resolveIconsForSlides,
  sanitizeOfficePackageMetadata,
};
