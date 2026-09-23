/*
 * Slide-family renderers for the pptxgenjs peer path.
 *
 * Canvas: LAYOUT_16x9 = 10.00" x 5.625".
 *   Side margins: 0.50"
 *   Title bar:    minimum 0.90" tall at y=0, full-bleed, dark fill
 *   Content rail: starts at the measured header bottom, not a fixed y
 *
 * Each exported function has the shape:
 *   renderXxx(pptx, slide, slideData, preset)
 *
 * Important pptxgenjs rules respected here:
 *   - Hex colors NEVER carry a '#'. "1493A4" not "#1493A4".
 *   - Option objects are NEVER shared across addShape / addText calls.
 *     Use the factory helpers (txt(), shape(), card()) which return fresh
 *     objects each time. pptxgenjs mutates what you pass in, so reuse
 *     across slides produces silently broken output.
 *   - All text boxes set margin: 0 for precise alignment.
 */

'use strict';

const fs = require('fs');
const {
  absoluteSlot,
} = require('./role_layout_contracts.js');
const {
  contractForResolvedPlan,
  resolveRenderPlan,
} = require('./render_plan.js');

// Canvas constants -- keep in sync with pptx.layout = 'LAYOUT_16x9'.
const SLIDE_W = 10.0;
const SLIDE_H = 5.625;
const MARGIN_X = 0.5;
// The dark title bar sits at y=0 (full-bleed) and is 0.90" tall. HEADER_TOP is
// kept for backwards compatibility with callers that reference it, but the bar
// itself now starts at y=0.
const HEADER_TOP = 0.0;
const TITLE_BAR_H = 0.9;
const CONTENT_TOP = HEADER_TOP + TITLE_BAR_H; // 0.90
const FOOTER_H = 0.32;

// ---------------------------------------------------------------------------
// Factory helpers. These exist because pptxgenjs mutates option objects in
// place during rendering. Reusing one object across shapes = silent bugs.
// ---------------------------------------------------------------------------

function textOpts(extra) {
  return Object.assign(
    {
      margin: 0,
      fontFace: 'Helvetica Neue',
      fontSize: 14,
      color: '0F172A',
      valign: 'top',
      align: 'left',
      isTextBox: true,
    },
    extra || {},
  );
}

function shapeOpts(extra) {
  return Object.assign(
    {
      line: { color: 'FFFFFF', width: 0 },
    },
    extra || {},
  );
}

function cardShadow() {
  // Fresh shadow descriptor every call. pptxgenjs will attach and mutate it.
  return {
    type: 'outer',
    color: '0F172A',
    opacity: 0.12,
    blur: 8,
    offset: 2,
    angle: 90,
  };
}

function cleanHex(value, fallback) {
  const raw = String(value || fallback || '').replace(/^#/, '').trim();
  return /^[0-9a-fA-F]{6}$/.test(raw) ? raw.toUpperCase() : String(fallback || '0F172A');
}

function colorLuminance(value) {
  const hex = cleanHex(value, '0F172A');
  const channels = [0, 2, 4].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
  const linear = channels.map((channel) => (
    channel <= 0.03928
      ? channel / 12.92
      : Math.pow((channel + 0.055) / 1.055, 2.4)
  ));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(foreground, background) {
  const a = colorLuminance(foreground);
  const b = colorLuminance(background);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function firstReadableColor(background, candidates, minimumRatio = 4.5) {
  const colors = candidates
    .map((value) => String(value || '').replace(/^#/, '').trim())
    .filter((value) => /^[0-9a-fA-F]{6}$/.test(value))
    .map((value) => value.toUpperCase());
  const passing = colors.find((color) => contrastRatio(color, background) >= minimumRatio);
  if (passing) return passing;
  return colors.sort((left, right) => contrastRatio(right, background) - contrastRatio(left, background))[0] || 'FFFFFF';
}

function darkSlideSubtitleColor(preset) {
  const background = cleanHex(preset.bg_dark, '0F172A');
  return firstReadableColor(
    background,
    [
      preset.title_subtitle_color,
      preset.accent_secondary,
      preset.accent_primary,
      preset.text_muted,
      'CBD5E1',
      'FFFFFF',
    ],
    4.5,
  );
}

function addTitleMotif(slide, preset, hasHero) {
  const motif = String(preset.title_motif || 'orbit').trim().toLowerCase();
  if (motif === 'none') return;
  const accent = cleanHex(preset.accent_primary, '14B8A6');
  const secondary = cleanHex(preset.accent_secondary, accent);
  const ink = cleanHex(preset.bg_dark, '0F172A');

  if (motif === 'network') {
    const pts = [
      [6.4, 1.2], [7.5, 0.85], [8.7, 1.45], [6.9, 2.45],
      [8.2, 2.65], [7.4, 3.55], [9.1, 3.8],
    ];
    for (let i = 0; i < pts.length - 1; i += 1) {
      slide.addShape('line', shapeOpts({
        x: pts[i][0], y: pts[i][1], w: pts[i + 1][0] - pts[i][0], h: pts[i + 1][1] - pts[i][1],
        line: { color: accent, transparency: 74, width: 1.2 },
      }));
    }
    pts.forEach(([x, y], idx) => {
      slide.addShape('ellipse', shapeOpts({
        x: x - 0.055, y: y - 0.055, w: 0.11, h: 0.11,
        fill: { color: idx % 2 ? secondary : accent, transparency: 18 },
        line: { color: 'FFFFFF', transparency: 85, width: 0.4 },
      }));
    });
    return;
  }

  if (motif === 'editorial') {
    slide.addShape('rect', shapeOpts({
      x: hasHero ? 5.35 : 7.15,
      y: 0,
      w: hasHero ? 0.18 : 1.85,
      h: SLIDE_H,
      fill: { color: accent, transparency: 78 },
      line: { color: accent, transparency: 100, width: 0 },
    }));
    slide.addShape('rect', shapeOpts({
      x: hasHero ? 5.62 : 7.55,
      y: 0.72,
      w: hasHero ? 3.35 : 1.2,
      h: 0.05,
      fill: { color: secondary, transparency: 18 },
    }));
    return;
  }

  // Default orbit motif: a few quiet rings make the cover feel authored
  // without depending on external imagery.
  const cx = hasHero ? 7.55 : 7.35;
  const cy = hasHero ? 2.70 : 2.35;
  [1.05, 1.55, 2.10].forEach((r, idx) => {
    slide.addShape('ellipse', shapeOpts({
      x: cx - r,
      y: cy - r,
      w: r * 2,
      h: r * 2,
      fill: { color: ink, transparency: 100 },
      line: { color: idx % 2 ? secondary : accent, transparency: 70, width: 1.0 },
    }));
  });
  slide.addShape('ellipse', shapeOpts({
    x: cx + 1.12,
    y: cy - 0.68,
    w: 0.16,
    h: 0.16,
    fill: { color: accent, transparency: 8 },
    line: { color: 'FFFFFF', transparency: 100, width: 0 },
  }));
}

function addSectionMotif(slide, preset) {
  const motif = String(preset.section_motif || 'rail-dots').trim().toLowerCase();
  if (motif === 'none') return;
  const accent = cleanHex(preset.accent_primary, '14B8A6');
  const secondary = cleanHex(preset.accent_secondary, accent);

  // The right-side wash intentionally fills dead space on divider slides so
  // section breaks read like designed pauses, not sparse placeholders.
  slide.addShape('rect', shapeOpts({
    x: SLIDE_W - 2.25,
    y: 0,
    w: 2.25,
    h: SLIDE_H,
    fill: { color: accent, transparency: 84 },
    line: { color: accent, transparency: 100, width: 0 },
  }));
  [0.72, 1.05, 1.42].forEach((r, idx) => {
    slide.addShape('ellipse', shapeOpts({
      x: SLIDE_W - 1.55 - r,
      y: 2.80 - r,
      w: r * 2,
      h: r * 2,
      fill: { color: accent, transparency: 100 },
      line: { color: idx % 2 ? secondary : 'FFFFFF', transparency: 72, width: 1.0 },
    }));
  });
  for (let i = 0; i < 5; i += 1) {
    slide.addShape('ellipse', shapeOpts({
      x: SLIDE_W - 0.82,
      y: 1.05 + i * 0.46,
      w: 0.10,
      h: 0.10,
      fill: { color: i % 2 ? secondary : accent, transparency: 12 },
      line: { color: 'FFFFFF', transparency: 100, width: 0 },
    }));
  }
}

function safeText(value, fallback) {
  if (value === null || value === undefined) return fallback || '';
  const s = String(value).trim();
  return s.length ? s : fallback || '';
}

function truncate(s, max) {
  if (!s) return '';
  return s.length > max ? s.slice(0, Math.max(1, max - 1)) + '…' : s;
}

function estimateTextLines(text, fontSize, boxW) {
  const value = safeText(text);
  if (!value) return 0;
  const avgCharW = Math.max(0.055, (fontSize / 72) * 0.56);
  const charsPerLine = Math.max(10, Math.floor(Math.max(0.2, boxW - 0.08) / avgCharW));
  return value.split(/\n+/).reduce((sum, paragraph) => {
    const len = paragraph.trim().length;
    return sum + Math.max(1, Math.ceil(len / charsPerLine));
  }, 0);
}

function estimateTextHeight(text, fontSize, boxW, lineHeight) {
  const lines = estimateTextLines(text, fontSize, boxW);
  if (!lines) return 0;
  return lines * (fontSize / 72) * (lineHeight || 1.18);
}

function fitFontToBox(text, preferredFont, minFont, boxW, boxH, lineHeight) {
  let fontSize = preferredFont;
  const safeHeight = Math.max(0.2, boxH - 0.08);
  while (
    fontSize > minFont
    && estimateTextHeight(text, fontSize, boxW, lineHeight || 1.18) > safeHeight
  ) {
    fontSize -= 1;
  }
  return Math.max(minFont, fontSize);
}

function titleFontForLength(title) {
  const len = safeText(title).length;
  if (len > 42) return 24;
  return 26;
}

function headerMetrics(title, subtitle, options) {
  const opts = options || {};
  const titleText = safeText(title, 'Untitled');
  const subtitleText = safeText(subtitle);
  const textW = opts.textW || (SLIDE_W - MARGIN_X * 2);
  const titleFont = opts.titleFont || titleFontForLength(titleText);
  const subtitleFont = opts.subtitleFont || 13;
  const titleH = Math.max(0.42, estimateTextHeight(titleText, titleFont, textW, 1.50));
  const subtitleH = subtitleText
    ? Math.max(0.32, estimateTextHeight(subtitleText, subtitleFont, textW, 1.30))
    : 0;
  const topPad = opts.topPad === undefined ? 0.10 : opts.topPad;
  const titleSubtitleGap = subtitleText ? 0.05 : 0;
  const bottomPad = opts.bottomPad === undefined ? 0.12 : opts.bottomPad;
  const barH = Math.max(
    TITLE_BAR_H,
    topPad + titleH + titleSubtitleGap + subtitleH + bottomPad,
  );
  const titleY = subtitleText ? topPad : Math.max(topPad, (barH - titleH) / 2);
  const subtitleY = topPad + titleH + titleSubtitleGap;
  return {
    barH,
    stripeY: barH,
    contentTop: barH + 0.04,
    textW,
    titleText,
    subtitleText,
    titleFont,
    subtitleFont,
    titleY,
    titleH,
    subtitleY,
    subtitleH,
  };
}

const LAB_HEADER_VARIANTS = [
  'left-accent',
  'split-rule',
  'title-rule',
  'side-rail',
  'top-bottom-rule',
  'plain',
];

function hashString(value) {
  const s = String(value || '');
  let hash = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    hash ^= s.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function normalizeLabHeaderVariant(value) {
  const raw = String(value || '').trim().toLowerCase();
  const aliases = {
    auto: 'auto',
    default: 'left-accent',
    left: 'left-accent',
    'left-rule': 'left-accent',
    'left-accent': 'left-accent',
    split: 'split-rule',
    'split-rule': 'split-rule',
    full: 'split-rule',
    title: 'title-rule',
    'title-rule': 'title-rule',
    underline: 'title-rule',
    rail: 'side-rail',
    'side-rail': 'side-rail',
    bracket: 'side-rail',
    frame: 'top-bottom-rule',
    'frame-rule': 'top-bottom-rule',
    'top-bottom': 'top-bottom-rule',
    'top-bottom-rule': 'top-bottom-rule',
    top: 'top-bottom-rule',
    plain: 'plain',
    minimal: 'plain',
    none: 'plain',
    'no-line': 'plain',
    'no-lines': 'plain',
    'no-rule': 'plain',
    'no-rules': 'plain',
  };
  return aliases[raw] || raw;
}

function pickLabHeaderVariant(slideData, preset) {
  const requested = normalizeLabHeaderVariant(slideData.header_variant || preset.header_variant || 'left-accent');
  const rawPool = Array.isArray(slideData.header_variants)
    ? slideData.header_variants
    : Array.isArray(preset.header_variants)
      ? preset.header_variants
      : LAB_HEADER_VARIANTS;
  const pool = rawPool
    .map(normalizeLabHeaderVariant)
    .filter((item) => LAB_HEADER_VARIANTS.includes(item));
  if (requested && requested !== 'auto' && LAB_HEADER_VARIANTS.includes(requested)) return requested;
  const variants = pool.length ? pool : LAB_HEADER_VARIANTS;
  const seed = [
    safeText(slideData.style_seed || preset.style_seed),
    slideData.__slideIndex || '',
    safeText(slideData.title),
    safeText(slideData.subtitle),
  ].join('|');
  return variants[hashString(seed) % variants.length];
}

function presetColor(preset, value, fallback) {
  const raw = String(value || '').trim();
  if (raw && Object.prototype.hasOwnProperty.call(preset, raw)) {
    return cleanHex(preset[raw], fallback);
  }
  return cleanHex(raw || fallback, fallback);
}

function addLabHeaderRule(slide, options) {
  const variant = options.variant;
  const x = options.x;
  const y = options.y;
  const w = options.w;
  const lineColor = options.lineColor;
  const accent = options.accent;
  const titleText = options.titleText;

  const addLine = (lineX, lineY, lineW, lineH, color) => {
    if (lineW <= 0 || lineH <= 0) return;
    slide.addShape('rect', shapeOpts({
      x: lineX,
      y: lineY,
      w: lineW,
      h: lineH,
      fill: { color },
      line: { color, width: 0 },
    }));
  };

  if (variant === 'plain') {
    return;
  }

  if (variant === 'top-bottom-rule') {
    addLine(x, 0.055, w, 0.022, accent);
    slide.addShape('rect', shapeOpts({
      x,
      y: 0.077,
      w,
      h: 0.090,
      fill: { color: lineColor, transparency: 74 },
      line: { color: lineColor, transparency: 100, width: 0 },
    }));
    addLine(x, y, w, 0.014, lineColor);
    return;
  }

  if (variant === 'split-rule') {
    const accentW = Math.min(2.60, Math.max(1.45, w * 0.30));
    addLine(x, y - 0.012, accentW, 0.034, accent);
    addLine(x + accentW + 0.12, y, w - accentW - 0.12, 0.014, lineColor);
    return;
  }

  if (variant === 'title-rule') {
    const titleRuleW = Math.min(4.90, Math.max(1.20, safeText(titleText).length * 0.075));
    addLine(x, y - 0.010, titleRuleW, 0.030, accent);
    addLine(x + titleRuleW + 0.14, y, w - titleRuleW - 0.14, 0.014, lineColor);
    return;
  }

  if (variant === 'side-rail') {
    addLine(x, y, w, 0.014, lineColor);
    addLine(x, y + 0.034, Math.min(1.20, w * 0.16), 0.026, accent);
    return;
  }

  addLine(x, y, w, 0.018, lineColor);
  addLine(x, y - 0.035, 0.85, 0.035, accent);
}

function imageDimensions(imagePath) {
  try {
    const buf = fs.readFileSync(imagePath);
    if (buf.length >= 24 && buf.toString('ascii', 1, 4) === 'PNG') {
      return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
    }
    if (buf.length >= 4 && buf[0] === 0xff && buf[1] === 0xd8) {
      let offset = 2;
      while (offset + 9 < buf.length) {
        if (buf[offset] !== 0xff) { offset += 1; continue; }
        const marker = buf[offset + 1];
        const len = buf.readUInt16BE(offset + 2);
        if (marker >= 0xc0 && marker <= 0xc3) {
          return { w: buf.readUInt16BE(offset + 7), h: buf.readUInt16BE(offset + 5) };
        }
        offset += 2 + len;
      }
    }
  } catch (_e) {}
  return null;
}

function imageSizingContainLocal(imagePath, x, y, w, h) {
  const size = imageDimensions(imagePath);
  if (!size || !size.w || !size.h) return { x, y, w, h };
  const boxRatio = w / Math.max(h, 0.01);
  const imageRatio = size.w / size.h;
  let fitW;
  let fitH;
  if (imageRatio >= boxRatio) {
    fitW = w;
    fitH = w / imageRatio;
  } else {
    fitH = h;
    fitW = h * imageRatio;
  }
  return { x: x + (w - fitW) / 2, y: y + (h - fitH) / 2, w: fitW, h: fitH };
}

function generatedImageMeta(imagePath, slideData) {
  const meta = {};
  if (imagePath) {
    const metaPath = `${imagePath}.metadata.json`;
    if (fs.existsSync(metaPath)) {
      try {
        Object.assign(meta, JSON.parse(fs.readFileSync(metaPath, 'utf8')));
      } catch (_e) {}
    }
  }
  if (slideData.image_generation && typeof slideData.image_generation === 'object') {
    Object.assign(meta, slideData.image_generation);
  }
  return meta;
}

// ---------------------------------------------------------------------------
// Shared chrome: background, title bar, footer, optional background image.
// ---------------------------------------------------------------------------

function paintBackground(slide, color) {
  slide.background = { color: color };
}

function addBackgroundImage(slide, imagePath, preset) {
  if (!imagePath) return;
  if (!fs.existsSync(imagePath)) {
    console.warn(`[pptxgenjs] background_image not found, skipping: ${imagePath}`);
    return;
  }
  slide.addImage({
    path: imagePath,
    x: 0,
    y: 0,
    w: SLIDE_W,
    h: SLIDE_H,
    sizing: { type: 'cover', w: SLIDE_W, h: SLIDE_H },
    transparency: 15,
  });
  // Dim overlay so text stays readable.
  slide.addShape('rect', shapeOpts({
    x: 0, y: 0, w: SLIDE_W, h: SLIDE_H,
    fill: { color: preset.bg_dark, transparency: 55 },
  }));
}

function compositionGrammar(preset, slideData = {}) {
  return String(slideData.composition_grammar || preset.composition_grammar || '').trim().toLowerCase();
}

function roleSystem(preset, slideData, role) {
  const local = slideData.role_systems && typeof slideData.role_systems === 'object'
    ? slideData.role_systems
    : {};
  const deck = preset.role_systems && typeof preset.role_systems === 'object'
    ? preset.role_systems
    : {};
  return String(local[role] || deck[role] || slideData.render_system_id || '').trim().toLowerCase();
}

function roleContract(preset, slideData, role) {
  return contractForResolvedPlan(slideData, preset, role);
}

function resolvedRenderPlan(preset, slideData) {
  return slideData && slideData.__renderPlan && typeof slideData.__renderPlan === 'object'
    ? slideData.__renderPlan
    : resolveRenderPlan(slideData, preset);
}

function markRoleContractExecution(slideData, preset, role, consumedSlots = []) {
  if (!slideData || typeof slideData !== 'object') return;
  const plan = resolvedRenderPlan(preset, slideData);
  if (!plan || plan.contractSource !== 'v2' || plan.canonicalRole !== role) return;
  const contract = plan.contract && typeof plan.contract === 'object' ? plan.contract : {};
  slideData.__roleContractExecution = {
    schema_version: 'renderer-role-contract-execution/v1',
    applied: true,
    role,
    adapter: plan.adapter,
    grammar_id: String(contract.grammar_id || ''),
    system_id: String(contract.system_id || ''),
    layout_variant: String(contract.variant || 'primary'),
    consumed_slots: Array.from(new Set(consumedSlots.map((slot) => String(slot || '')).filter(Boolean))),
  };
}

function roleBodyFont(preset, fallback) {
  const contract = preset && preset.readability_contract && typeof preset.readability_contract === 'object'
    ? preset.readability_contract
    : {};
  const minimum = Number(contract.min_body_pt);
  return Number.isFinite(minimum) && minimum > 0
    ? Math.max(Number(fallback) || 0, minimum)
    : fallback;
}

function roleMetadataFont(preset, fallback) {
  const contract = preset && preset.readability_contract && typeof preset.readability_contract === 'object'
    ? preset.readability_contract
    : {};
  const minimum = Number(contract.min_metadata_pt || contract.min_footer_pt || contract.min_caption_pt);
  return Number.isFinite(minimum) && minimum > 0
    ? Math.max(Number(fallback) || 0, minimum)
    : fallback;
}

function roleSupportFont(preset, fallback) {
  const contract = preset && preset.readability_contract && typeof preset.readability_contract === 'object'
    ? preset.readability_contract
    : {};
  const minimum = Number(contract.min_support_pt || 13);
  return Number.isFinite(minimum) && minimum > 0
    ? Math.max(Number(fallback) || 0, minimum)
    : fallback;
}

function roleBodyBox(header, slideData, preset, opts = {}) {
  const hasSummary = Boolean(safeText(
    slideData.summary_callout || slideData.key_summary || slideData.takeaway,
  ));
  const topGap = Number(opts.topGap ?? 0.22);
  const footerReserve = Number(opts.footerReserve ?? (hasFooterChrome(slideData, preset) ? 0.62 : 0.24));
  const summaryReserve = hasSummary && !opts.consumeSummary ? Number(opts.summaryReserve ?? 0.74) : 0;
  const y = header.contentTop + topGap;
  return {
    x: MARGIN_X,
    y,
    w: SLIDE_W - MARGIN_X * 2,
    h: Math.max(1.0, SLIDE_H - y - footerReserve - summaryReserve),
  };
}

function roleSlot(contract, slotName, bodyBox) {
  return absoluteSlot(contract, slotName, bodyBox);
}

function roleSlotNames(contract, prefix) {
  return Object.keys((contract && contract.slots) || {})
    .filter((name) => name.startsWith(prefix))
    .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
}

function grammarFrameContract(preset, slideData = {}) {
  const grammar = compositionGrammar(preset, slideData);
  const contracts = {
    'consulting-answer-pyramid': { left: 0.42, right: 0.42, top: 0.20, bottom: 0.30, grid: 12 },
    'scientific-evidence-plate': { left: 0.50, right: 0.50, top: 0.30, bottom: 0.46, grid: 10 },
    'clinical-care-pathway': { left: 0.72, right: 0.60, top: 0.22, bottom: 0.32, grid: 10 },
    'editorial-spread': { left: 0.54, right: 0.54, top: 0.24, bottom: 0.34, grid: 6 },
    'investor-thesis-stage': { left: 0.42, right: 0.56, top: 0.18, bottom: 0.34, grid: 12 },
    'operations-grid': { left: 0.36, right: 0.36, top: 0.34, bottom: 0.48, grid: 12 },
    'policy-public-docket': { left: 0.78, right: 0.46, top: 0.22, bottom: 0.38, grid: 10 },
    'technical-telemetry-canvas': { left: 0.34, right: 0.78, top: 0.36, bottom: 0.38, grid: 16 },
  };
  return Object.assign({ grammar, left: MARGIN_X, right: MARGIN_X, top: 0.20, bottom: 0.30, grid: 12 }, contracts[grammar] || {});
}

function isPolicyPublicDocket(preset, slideData = {}) {
  return compositionGrammar(preset, slideData) === 'policy-public-docket';
}

function canonicalSlideRole(slideData = {}) {
  const role = safeText(slideData.role || slideData.type).trim().toLowerCase();
  if (role === 'content') return safeText(slideData.slide_intent).trim().toLowerCase();
  return role;
}

function policyDecisionMetric(slideData = {}) {
  const explicit = safeText(
    slideData.hero_metric || slideData.decision_metric || slideData.amount || slideData.primary_metric,
  );
  if (explicit) return explicit;
  const title = safeText(slideData.title);
  const match = title.match(/(?:[$€£]\s?[\d,.]+(?:\.\d+)?\s?[KMB]?|[\d,.]+(?:\.\d+)?\s?(?:%|°C|days?|weeks?))/i);
  return match ? safeText(match[0]).replace(/\s+/g, '') : '';
}

function addGrammarFrame(slide, preset, slideData = {}) {
  const frame = grammarFrameContract(preset, slideData);
  if (!frame.grammar) return false;
  const accent = cleanHex(preset.accent_primary, '1493A4');
  const secondary = cleanHex(preset.accent_secondary, accent);
  const line = cleanHex(preset.line, 'CBD5E1');
  const muted = cleanHex(preset.text_muted, '64748B');
  const addRule = (x, y, w, h, color, transparency = 0) => {
    slide.addShape('rect', shapeOpts({
      x, y, w, h,
      fill: { color, transparency },
      line: { color, transparency: 100, width: 0 },
    }));
  };

  if (frame.grammar === 'consulting-answer-pyramid') {
    addRule(0.42, 0.08, 2.10, 0.035, accent);
    addRule(2.62, 0.08, SLIDE_W - 3.04, 0.012, line);
    addRule(0.42, SLIDE_H - 0.48, SLIDE_W - 0.84, 0.018, line);
    return true;
  }
  if (frame.grammar === 'scientific-evidence-plate') {
    ['QUESTION', 'METHOD', 'RESULT', 'INTERPRET'].forEach((_label, idx) => {
      const x = 0.50 + idx * 1.10;
      addRule(x, 0.08, 0.92, 0.055, idx === 2 ? accent : line, idx === 2 ? 0 : 18);
    });
    addRule(0.50, SLIDE_H - 0.52, SLIDE_W - 1.00, 0.018, line);
    addRule(0.50, SLIDE_H - 0.47, 1.62, 0.035, secondary);
    return true;
  }
  if (frame.grammar === 'clinical-care-pathway') {
    addRule(0.18, 0.82, 0.035, 5.78, accent);
    [1.36, 2.84, 4.32, 5.80].forEach((y, idx) => {
      slide.addShape('ellipse', shapeOpts({
        x: 0.115, y, w: 0.16, h: 0.16,
        fill: { color: idx === 2 ? secondary : preset.bg || 'FFFFFF' },
        line: { color: idx === 2 ? secondary : accent, width: 0.85 },
      }));
    });
    addRule(SLIDE_W - 0.24, 1.06, 0.035, 5.24, secondary, 8);
    return true;
  }
  if (frame.grammar === 'editorial-spread') {
    addRule(0.48, 0.12, SLIDE_W - 0.96, 0.014, line);
    addRule(0.48, 0.18, 1.34, 0.028, accent);
    addRule(0.48, 1.04, 0.018, 5.72, line);
    addRule(SLIDE_W - 0.78, SLIDE_H - 0.46, 0.30, 0.018, accent);
    return true;
  }
  if (frame.grammar === 'investor-thesis-stage') {
    const progress = Number(slideData.progress_index || 3);
    for (let idx = 0; idx < 6; idx += 1) {
      addRule(0.42 + idx * 0.62, SLIDE_H - 0.48, 0.48, 0.045, idx < progress ? accent : line, idx < progress ? 0 : 20);
    }
    addRule(SLIDE_W - 0.18, 1.06, 0.18, 5.74, secondary);
    return true;
  }
  if (frame.grammar === 'operations-grid') {
    const widths = [1.72, 1.42, 1.42, 1.72];
    let x = 0.36;
    widths.forEach((w, idx) => {
      addRule(x, 0.08, w, 0.11, idx === 1 ? accent : (idx === 2 ? secondary : line), idx > 1 ? 12 : 0);
      x += w + 0.12;
    });
    addRule(0.36, SLIDE_H - 0.56, SLIDE_W - 0.72, 0.16, preset.surface || 'FFFFFF');
    addRule(0.36, SLIDE_H - 0.56, 1.58, 0.16, accent, 6);
    return true;
  }
  if (frame.grammar === 'policy-public-docket') {
    const role = canonicalSlideRole(slideData);
    const stageLike = role === 'title' || role === 'section';
    const topX = stageLike ? 0.62 : MARGIN_X;
    addRule(topX, 0.09, stageLike ? 0.82 : 0.68, stageLike ? 0.055 : 0.035, accent);
    addRule(
      topX + (stageLike ? 0.96 : 0.82),
      0.09,
      SLIDE_W - topX - (stageLike ? 1.38 : 1.24),
      0.014,
      stageLike ? secondary : line,
      stageLike ? 4 : 20,
    );
    addRule(MARGIN_X, SLIDE_H - 0.48, SLIDE_W - MARGIN_X * 2, 0.018, line);
    return true;
  }
  if (frame.grammar === 'technical-telemetry-canvas') {
    [0.34, 2.10, 3.86, 5.62, 7.38].forEach((x, idx) => {
      addRule(x, 0.07, 1.48, 0.12, idx === 2 ? accent : line, idx === 2 ? 0 : 16);
    });
    addRule(SLIDE_W - 0.52, 0.44, 0.32, 5.30, preset.surface || '111827', 12);
    [1.10, 2.08, 3.06, 4.04, 5.02, 6.00].forEach((y, idx) => {
      addRule(SLIDE_W - 0.46, y, 0.20, 0.018, idx === 3 ? secondary : line, idx === 3 ? 0 : 24);
    });
    return true;
  }
  return false;
}

function addPageSystemChrome(slide, preset, slideData) {
  if (addGrammarFrame(slide, preset, slideData)) return;
  const system = String(slideData.page_system || preset.page_system || '').trim().toLowerCase();
  const motif = String(slideData.structural_motif || preset.structural_motif || '').trim().toLowerCase();
  if (!system || system === 'none') return;
  const accent = cleanHex(preset.accent_primary, '1493A4');
  const secondary = cleanHex(preset.accent_secondary, accent);
  const line = cleanHex(preset.line, 'CBD5E1');

  const addRule = (x, y, w, h, color, transparency = 0) => {
    slide.addShape('rect', shapeOpts({
      x, y, w, h,
      fill: { color, transparency },
      line: { color, transparency: 100, width: 0 },
    }));
  };

  // Preset-level structural motifs keep related page systems coherent without
  // making every family share the same rails, rules, or corner furniture.
  if (motif && motif !== 'none') {
    if (motif === 'clinical-stages') {
      addRule(0.16, 1.24, 0.025, 5.12, accent);
      [1.56, 3.54, 5.52].forEach((y, idx) => {
        slide.addShape('ellipse', shapeOpts({
          x: 0.105, y, w: 0.135, h: 0.135,
          fill: { color: idx === 1 ? secondary : preset.bg || 'FFFFFF' },
          line: { color: idx === 1 ? secondary : accent, width: 0.8 },
        }));
        addRule(0.25, y + 0.055, 0.12 + idx * 0.04, 0.012, line, 12);
      });
      return;
    }
    if (motif === 'board-index') {
      [0.88, 0.62, 0.36].forEach((w, idx) => {
        addRule(SLIDE_W - 0.46 - w, 0.06 + idx * 0.09, w, 0.035, idx === 0 ? accent : line, idx * 10);
      });
      addRule(0.42, SLIDE_H - 0.16, SLIDE_W - 0.84, 0.018, line);
      addRule(SLIDE_W - 3.32, SLIDE_H - 0.12, 2.90, 0.035, secondary);
      return;
    }
    if (motif === 'field-notes') {
      [1.48, 2.72, 3.96, 5.20].forEach((y, idx) => {
        addRule(0.18, y, 0.12 + (idx % 2) * 0.09, 0.018, idx === 2 ? secondary : line);
      });
      addRule(0.18, 1.48, 0.018, 3.76, accent, 8);
      addRule(0.42, SLIDE_H - 0.16, 1.70, 0.024, accent);
      addRule(2.20, SLIDE_H - 0.16, 0.50, 0.024, secondary, 12);
      return;
    }
    if (motif === 'thesis-window') {
      addRule(SLIDE_W - 0.16, 1.02, 0.16, 5.96, accent);
      addRule(SLIDE_W - 1.54, 1.02, 1.38, 0.055, secondary);
      addRule(SLIDE_W - 1.54, 1.02, 0.025, 0.52, secondary);
      addRule(SLIDE_W - 0.74, 1.30, 0.58, 0.018, line);
      return;
    }
    if (motif === 'workflow-brackets') {
      const corner = (x, y, flipX, flipY) => {
        addRule(x + (flipX ? -0.38 : 0), y, 0.38, 0.025, accent, 10);
        addRule(x, y + (flipY ? -0.38 : 0), 0.025, 0.38, accent, 10);
      };
      corner(0.22, 1.12, false, false);
      corner(SLIDE_W - 0.22, 1.12, true, false);
      corner(0.22, SLIDE_H - 0.30, false, true);
      corner(SLIDE_W - 0.22, SLIDE_H - 0.30, true, true);
      addRule(SLIDE_W / 2 - 0.72, SLIDE_H - 0.18, 1.44, 0.035, secondary);
      return;
    }
    if (motif === 'case-margin') {
      addRule(SLIDE_W - 0.32, 1.10, 0.025, 5.58, accent, 8);
      [1.10, 3.64, 6.66].forEach((y, idx) => {
        addRule(SLIDE_W - 0.72 - idx * 0.12, y, 0.42 + idx * 0.12, 0.022, idx === 1 ? secondary : line);
      });
      addRule(0.42, SLIDE_H - 0.20, 1.12, 0.045, secondary);
      return;
    }
    if (motif === 'journal-folio') {
      addRule(0.42, 0.13, SLIDE_W - 0.84, 0.016, line);
      addRule(0.42, 0.19, 2.08, 0.024, accent);
      addRule(SLIDE_W - 2.14, 0.19, 1.72, 0.024, secondary, 10);
      addRule(SLIDE_W / 2 - 0.38, SLIDE_H - 0.14, 0.76, 0.016, line);
      return;
    }
    if (motif === 'editorial-rule') {
      addRule(0.34, 1.10, 0.018, 5.72, line);
      addRule(0.30, 1.10, 0.10, 0.82, accent);
      addRule(0.30, 6.42, 0.10, 0.40, secondary);
      return;
    }
    if (motif === 'open-coordinate') {
      addRule(0.22, 1.12, 0.54, 0.018, accent, 16);
      addRule(0.22, 1.12, 0.018, 0.44, accent, 16);
      addRule(SLIDE_W - 0.78, SLIDE_H - 0.30, 0.56, 0.018, line);
      addRule(SLIDE_W - 0.24, SLIDE_H - 0.74, 0.018, 0.44, line);
      return;
    }
    if (motif === 'proof-stage') {
      addRule(0.42, 1.12, 0.92, 0.055, secondary);
      addRule(0.42, 1.19, 0.34, 0.018, accent);
      addRule(0, SLIDE_H - 0.16, SLIDE_W, 0.07, preset.bg_dark || '0B1220');
      addRule(0, SLIDE_H - 0.16, 3.24, 0.07, accent);
      return;
    }
    if (motif === 'incident-rail') {
      addRule(0.16, 1.08, 0.085, 5.82, secondary);
      addRule(0.16, 1.08, 0.62, 0.055, secondary);
      [0.00, 0.28, 0.56].forEach((offset, idx) => {
        addRule(SLIDE_W - 1.28 + offset, SLIDE_H - 0.18, 0.18, 0.035, idx === 1 ? secondary : line);
      });
      return;
    }
    if (motif === 'signal-grid') {
      [0.00, 0.22, 0.44, 0.66].forEach((offset) => {
        addRule(SLIDE_W - 0.88 + offset, 1.18, 0.012, 5.28, line, 56);
      });
      [1.18, 2.50, 3.82, 5.14, 6.46].forEach((y, idx) => {
        addRule(SLIDE_W - 0.88, y, 0.68, 0.012, idx === 2 ? accent : line, idx === 2 ? 18 : 56);
      });
      addRule(0.22, SLIDE_H - 0.18, 1.36, 0.03, secondary);
      return;
    }
    if (motif === 'assay-register') {
      [0.72, 1.02, 1.32].forEach((x, idx) => addRule(x, 0.07, 0.18, 0.025, idx === 1 ? secondary : line));
      addRule(MARGIN_X, SLIDE_H - 0.28, SLIDE_W - MARGIN_X * 2, 0.014, line);
      [0.00, 0.08, 0.18, 0.31, 0.39, 0.55, 0.67].forEach((offset, idx) => {
        addRule(MARGIN_X + offset, SLIDE_H - 0.25, 0.025, idx % 2 ? 0.07 : 0.11, idx === 3 ? secondary : accent);
      });
      return;
    }
  }

  if (system === 'clinical-rail') {
    addRule(0.15, 0.28, 0.035, 6.58, accent);
    [1.48, 3.72, 5.96].forEach((y, idx) => {
      slide.addShape('ellipse', shapeOpts({
        x: 0.10,
        y,
        w: 0.13,
        h: 0.13,
        fill: { color: idx === 1 ? secondary : preset.bg || 'FFFFFF' },
        line: { color: idx === 1 ? secondary : accent, width: 0.8 },
      }));
    });
    return;
  }

  if (system === 'board-ledger') {
    addRule(SLIDE_W - 1.82, 0.0, 1.82, 0.16, accent);
    [SLIDE_W - 1.60, SLIDE_W - 1.30, SLIDE_W - 1.00].forEach((x) => {
      addRule(x, 0.16, 0.012, 0.34, line, 18);
    });
    addRule(0, SLIDE_H - 0.10, SLIDE_W, 0.025, line);
    addRule(SLIDE_W - 3.15, SLIDE_H - 0.10, 3.15, 0.025, secondary);
    return;
  }

  if (system === 'editorial-field') {
    addRule(0.34, 1.10, 0.018, 5.72, line);
    addRule(0.30, 1.10, 0.10, 0.82, accent);
    addRule(0.30, 6.42, 0.10, 0.40, accent);
    return;
  }

  if (system === 'command-canvas') {
    const corner = (x, y, flipX, flipY) => {
      addRule(x + (flipX ? -0.36 : 0), y, 0.36, 0.025, accent, 12);
      addRule(x, y + (flipY ? -0.36 : 0), 0.025, 0.36, accent, 12);
    };
    corner(0.22, 1.08, false, false);
    corner(SLIDE_W - 0.22, 1.08, true, false);
    corner(0.22, SLIDE_H - 0.30, false, true);
    corner(SLIDE_W - 0.22, SLIDE_H - 0.30, true, true);
    addRule(SLIDE_W - 0.56, 1.42, 0.012, 4.90, line, 48);
    return;
  }

  if (system === 'lab-plate') {
    [0.72, 1.02, 1.32].forEach((x, idx) => addRule(x, 0.07, 0.18, 0.025, idx === 1 ? secondary : line));
    addRule(MARGIN_X, SLIDE_H - 0.28, SLIDE_W - MARGIN_X * 2, 0.014, line);
    addRule(MARGIN_X, SLIDE_H - 0.24, 1.45, 0.026, secondary);
    return;
  }

  if (system === 'investor-thesis') {
    addRule(SLIDE_W - 0.14, 1.04, 0.14, 5.98, accent);
    addRule(SLIDE_W - 1.42, 1.04, 1.28, 0.06, secondary);
    addRule(SLIDE_W - 0.62, 1.28, 0.48, 0.018, line);
  }
}

function addDarkTitleBar(slide, preset, title, subtitle, slideData = {}) {
  // Full-bleed dark bar at the top of every content slide. The bar height is
  // measured from the title/subtitle stack so folded titles reserve real space
  // before the body layout starts.
  addPageSystemChrome(slide, preset, slideData);
  const grammarHeaderInset = 0;
  const headerMode = String(slideData.header_mode || preset.header_mode || 'bar').trim().toLowerCase();
  const isLabHeader = headerMode === 'lab-clean' || headerMode === 'lab-card';
  const headerVariant = headerMode === 'lab-card'
    ? 'left-accent'
    : pickLabHeaderVariant(slideData, preset);
  const metrics = isLabHeader
    ? headerMetrics(title, subtitle, {
      titleFont: isPolicyPublicDocket(preset, slideData)
        ? Math.max(24, Math.min(28, titleFontForLength(title)))
        : Math.max(26, Math.min(28, titleFontForLength(title))),
      subtitleFont: 12.5,
      topPad: 0.20,
      bottomPad: 0.10,
    })
    : headerMetrics(title, subtitle);

  if (isLabHeader) {
    const titleColor = preset.text || preset.text_primary || '0F172A';
    const subtitleColor = preset.text_muted || '64748B';
    const accent = cleanHex(slideData.header_fill || preset.accent_primary, '0B2545');
    const ruleAccent = presetColor(
      preset,
      slideData.header_rule_color || preset.header_rule_color ||
        (preset.header_accent_stripe ? 'accent_secondary' : 'accent_primary'),
      accent,
    );
    const lineColor = cleanHex(preset.line, 'D1D5DB');
    const railInset = headerVariant === 'side-rail' ? 0.20 : 0;
    const titleX = MARGIN_X + railInset + grammarHeaderInset;
    const titleW = metrics.textW - railInset - grammarHeaderInset;
    const titleH = metrics.titleH;
    const subtitleH = metrics.subtitleH;
    const titleY = 0.19;
    let contentTop = 0.80;

    if (headerVariant === 'side-rail' && headerMode === 'lab-clean') {
      slide.addShape('rect', shapeOpts({
        x: MARGIN_X,
        y: titleY + 0.02,
        w: 0.055,
        h: Math.max(0.42, titleH + (metrics.subtitleText ? subtitleH + 0.09 : 0)),
        fill: { color: ruleAccent },
        line: { color: ruleAccent, width: 0 },
      }));
    }

    if (headerMode === 'lab-card') {
      const estimatedTitleW = Math.max(
        2.40,
        Math.min(6.80, metrics.titleText.length * 0.115 + 0.70),
      );
      const cardH = Math.max(0.94, titleH + 0.30);
      slide.addShape('rect', shapeOpts({
        x: MARGIN_X,
        y: titleY,
        w: estimatedTitleW,
        h: cardH,
        fill: { color: accent },
        line: { color: accent, width: 0 },
      }));
      slide.addText(metrics.titleText, textOpts({
        x: MARGIN_X + 0.16,
        y: titleY + 0.08,
        w: estimatedTitleW - 0.32,
        h: cardH - 0.16,
        fontFace: preset.font_heading,
        fontSize: metrics.titleFont,
        bold: true,
        color: 'FFFFFF',
        fit: 'shrink',
      }));
      if (metrics.subtitleText) {
        slide.addText(metrics.subtitleText, textOpts({
          x: MARGIN_X,
          y: titleY + cardH + 0.08,
          w: titleW,
          h: subtitleH,
          fontFace: preset.font_body,
          fontSize: metrics.subtitleFont,
          color: subtitleColor,
          fit: 'shrink',
          objectName: 'support:slide-subtitle',
        }));
      }
      contentTop = titleY + cardH + (metrics.subtitleText ? subtitleH + 0.24 : 0.22);
    } else {
      slide.addText(metrics.titleText, textOpts({
        x: titleX,
        y: titleY,
        w: titleW,
        h: titleH,
        fontFace: preset.font_heading,
        fontSize: metrics.titleFont,
        bold: true,
        color: titleColor,
        fit: 'shrink',
      }));
      if (metrics.subtitleText) {
        slide.addText(metrics.subtitleText, textOpts({
          x: titleX,
          y: titleY + titleH + 0.04,
          w: titleW,
          h: subtitleH,
          fontFace: preset.font_body,
          fontSize: metrics.subtitleFont,
          color: subtitleColor,
          fit: 'shrink',
          objectName: 'support:slide-subtitle',
        }));
      }
      contentTop = titleY + titleH + (metrics.subtitleText ? subtitleH + 0.20 : 0.16);
    }

    const ruleY = Math.max(0.62, contentTop - 0.10);
    if (headerMode === 'lab-clean') {
      addLabHeaderRule(slide, {
        variant: headerVariant,
        x: MARGIN_X,
        y: ruleY,
        w: SLIDE_W - MARGIN_X * 2,
        lineColor,
        accent: ruleAccent,
        titleText: metrics.titleText,
      });
    } else {
      slide.addShape('rect', shapeOpts({
        x: MARGIN_X,
        y: ruleY,
        w: SLIDE_W - MARGIN_X * 2,
        h: 0.018,
        fill: { color: lineColor },
        line: { color: lineColor, width: 0 },
      }));
      slide.addShape('rect', shapeOpts({
        x: MARGIN_X,
        y: ruleY - 0.035,
        w: 0.85,
        h: 0.035,
        fill: { color: accent },
        line: { color: accent, width: 0 },
      }));
    }
    return Object.assign({}, metrics, {
      barH: ruleY + 0.02,
      stripeY: ruleY,
      contentTop: Math.max(contentTop, ruleY + 0.14),
      titleY,
    });
  }

  if (headerMode === 'stack' || headerMode === 'eyebrow') {
    const titleColor = preset.text || preset.text_primary || '0F172A';
    const subtitleColor = preset.text_muted || '64748B';
    const railInset = headerVariant === 'side-rail' ? 0.20 : 0;
    const titleX = MARGIN_X + grammarHeaderInset + railInset;
    const titleW = metrics.textW - grammarHeaderInset - railInset;
    if (headerVariant === 'side-rail') {
      slide.addShape('rect', shapeOpts({
        x: MARGIN_X + grammarHeaderInset,
        y: metrics.titleY + 0.02,
        w: 0.055,
        h: Math.max(0.42, metrics.titleH + (metrics.subtitleText ? metrics.subtitleH + 0.09 : 0)),
        fill: { color: preset.accent_primary },
        line: { color: preset.accent_primary, width: 0 },
      }));
    }
    slide.addText(metrics.titleText, textOpts({
      x: titleX,
      y: metrics.titleY,
      w: titleW,
      h: metrics.titleH,
      fontFace: preset.font_heading,
      fontSize: metrics.titleFont,
      bold: true,
      color: titleColor,
    }));
    if (metrics.subtitleText) {
      slide.addText(metrics.subtitleText, textOpts({
        x: titleX,
        y: metrics.subtitleY,
        w: titleW,
        h: metrics.subtitleH,
        fontFace: preset.font_body,
        fontSize: metrics.subtitleFont,
        color: subtitleColor,
        objectName: 'support:slide-subtitle',
      }));
    }
    addLabHeaderRule(slide, {
      variant: headerVariant,
      x: MARGIN_X + grammarHeaderInset,
      y: metrics.contentTop - 0.10,
      w: SLIDE_W - MARGIN_X * 2 - grammarHeaderInset,
      lineColor: cleanHex(preset.line, 'D1D5DB'),
      accent: presetColor(
        preset,
        slideData.header_rule_color || preset.header_rule_color || 'accent_primary',
        preset.accent_primary,
      ),
      titleText: metrics.titleText,
    });
    return Object.assign({}, metrics, {
      headerVariant,
      contentTop: Math.max(metrics.contentTop, metrics.contentTop + (headerVariant === 'side-rail' ? 0.03 : 0)),
    });
  }

  slide.addShape('rect', shapeOpts({
    x: 0, y: 0, w: SLIDE_W, h: metrics.barH,
    fill: { color: preset.bg_dark },
  }));
  const stripeColor = preset.header_accent_stripe
    ? (preset.accent_secondary || preset.accent_primary)
    : preset.accent_primary;
  const lineColor = cleanHex(preset.line, 'D1D5DB');
  const addBarRule = (x, y, w, h, color, transparency = 0) => {
    if (w <= 0 || h <= 0) return;
    slide.addShape('rect', shapeOpts({
      x, y, w, h,
      fill: { color, transparency },
      line: { color, transparency: 100, width: 0 },
    }));
  };
  if (headerVariant === 'split-rule') {
    addBarRule(0, metrics.stripeY, SLIDE_W * 0.34, 0.04, stripeColor);
    addBarRule(SLIDE_W * 0.34, metrics.stripeY, SLIDE_W * 0.66, 0.018, lineColor, 35);
  } else if (headerVariant === 'title-rule') {
    const titleRuleW = Math.min(5.1, Math.max(1.35, metrics.titleText.length * 0.078));
    addBarRule(MARGIN_X + grammarHeaderInset, metrics.stripeY, titleRuleW, 0.04, stripeColor);
    addBarRule(MARGIN_X + grammarHeaderInset + titleRuleW + 0.14, metrics.stripeY, SLIDE_W - MARGIN_X * 2 - grammarHeaderInset - titleRuleW - 0.14, 0.018, lineColor, 40);
  } else if (headerVariant === 'side-rail') {
    addBarRule(0, 0, 0.085, metrics.barH + 0.04, stripeColor);
    addBarRule(0.085, metrics.stripeY, SLIDE_W - 0.085, 0.018, lineColor, 42);
  } else if (headerVariant === 'top-bottom-rule') {
    addBarRule(0, 0, SLIDE_W, 0.035, stripeColor);
    addBarRule(0, metrics.stripeY, SLIDE_W, 0.018, lineColor, 28);
  } else if (headerVariant === 'left-accent') {
    addBarRule(0, metrics.stripeY, SLIDE_W, 0.025, lineColor, 24);
    addBarRule(0, metrics.stripeY, Math.min(1.75, SLIDE_W * 0.16), 0.05, stripeColor);
  }

  slide.addText(metrics.titleText, textOpts({
    x: MARGIN_X + grammarHeaderInset,
    y: metrics.titleY,
    w: metrics.textW - grammarHeaderInset,
    h: metrics.titleH,
    fontFace: preset.font_heading,
    fontSize: metrics.titleFont,
    bold: true,
    color: 'FFFFFF',
    valign: 'top',
  }));

  if (metrics.subtitleText) {
    slide.addText(metrics.subtitleText, textOpts({
      x: MARGIN_X + grammarHeaderInset,
      y: metrics.subtitleY,
      w: metrics.textW - grammarHeaderInset,
      h: metrics.subtitleH,
      fontFace: preset.font_body,
      fontSize: metrics.subtitleFont,
      color: darkSlideSubtitleColor(preset),
      bold: false,
      objectName: 'support:slide-subtitle',
    }));
  }
  return metrics;
}

function extractSourceText(src) {
  if (src === null || src === undefined) return '';
  if (typeof src === 'string') return src.trim();
  if (typeof src === 'number' || typeof src === 'boolean') return String(src);
  if (typeof src === 'object') {
    // Prefer explicit text-bearing fields, in priority order.
    const keys = ['text', 'citation', 'source', 'title', 'label', 'name'];
    for (const k of keys) {
      const v = src[k];
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
    // Last-ditch: first string-valued property.
    for (const k of Object.keys(src)) {
      const v = src[k];
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
  }
  return '';
}

function footerTextList(value) {
  return Array.isArray(value)
    ? value.map(extractSourceText).filter(Boolean)
    : [];
}

function footerChromeModel(slideData, preset) {
  const footer = safeText(slideData.footer);
  const sources = footerTextList(slideData.sources);
  const refs = footerTextList(slideData.refs).length
    ? footerTextList(slideData.refs)
    : footerTextList(slideData.references);
  const sourceLabel = safeText(slideData.source_label || preset.footer_source_label, 'Sources');
  const refsLabel = safeText(slideData.refs_label || preset.footer_refs_label, 'Refs');
  const provenanceParts = [];
  if (sources.length) provenanceParts.push(`${sourceLabel}: ` + sources.join('; '));
  if (refs.length) provenanceParts.push(`${refsLabel}: ` + refs.join('; '));
  const footerMode = String(slideData.footer_mode || preset.footer_mode || '').trim().toLowerCase();
  const pageNumber = slideData.__slideIndex && slideData.__slideCount
    ? `${slideData.__slideIndex}/${slideData.__slideCount}`
    : '';
  const showPageNumber = slideData.show_page_number === false
    ? false
    : Boolean(slideData.page_number || preset.footer_page_numbers || footerMode === 'source-line');
  return { footer, sources, refs, provenanceParts, footerMode, pageNumber, showPageNumber };
}

function hasFooterChrome(slideData, preset) {
  const model = footerChromeModel(slideData, preset);
  return Boolean(model.footer || model.provenanceParts.length || model.showPageNumber);
}

function addFooter(slide, preset, slideData) {
  const { footer, provenanceParts, footerMode, pageNumber, showPageNumber } = footerChromeModel(slideData, preset);
  if (!footer && provenanceParts.length === 0 && !showPageNumber) return;

  const y = SLIDE_H - FOOTER_H;
  const darkCover = (slideData.role === 'title' || slideData.type === 'title')
    && ['lavender-ops', 'sunset-investor', 'midnight-neon'].includes(preset.style_preset);
  const footerInk = darkCover
    ? firstReadableColor(preset.bg_dark, [preset.title_footer_color, preset.text_muted, 'CBD5E1', 'FFFFFF'], 4.5)
    : preset.text_muted;
  // Thin accent line above footer.
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X, y: y - 0.04, w: SLIDE_W - MARGIN_X * 2, h: 0.02,
    fill: { color: preset.line },
  }));

  if (footerMode === 'source-line') {
    const leftParts = [];
    if (footer) leftParts.push(footer);
    leftParts.push(...provenanceParts);
    const leftText = leftParts.join(' · ');
    const pageW = showPageNumber && pageNumber ? 0.55 : 0;
    const textW = SLIDE_W - MARGIN_X * 2 - pageW - (pageW ? 0.16 : 0);
    const fontSize = roleMetadataFont(preset, leftText.length > 170 ? 6.4 : leftText.length > 115 ? 7.2 : 8.0);
    if (leftText) {
      slide.addText(leftText, textOpts({
        x: MARGIN_X,
        y: y + 0.02,
        w: textW,
        h: FOOTER_H - 0.02,
        fontFace: preset.font_body,
        fontSize,
        color: footerInk,
        valign: 'middle',
        fit: 'shrink',
        objectName: 'metadata:footer-sources',
      }));
    }
    if (showPageNumber && pageNumber) {
      slide.addText(pageNumber, textOpts({
        x: SLIDE_W - MARGIN_X - pageW,
        y: y + 0.02,
        w: pageW,
        h: FOOTER_H - 0.02,
        fontFace: preset.font_body,
        fontSize: roleMetadataFont(preset, 8.4),
        color: footerInk,
        align: 'right',
        valign: 'middle',
        objectName: 'metadata:footer-page-number',
      }));
    }
    return;
  }

  if (footer) {
    const pageW = showPageNumber && pageNumber ? 0.55 : 0;
    const totalW = SLIDE_W - MARGIN_X * 2 - pageW - (pageW ? 0.16 : 0);
    const hasSources = provenanceParts.length > 0;
    const footerFont = roleMetadataFont(preset, hasSources
      ? (footer.length > 75 ? 7.2 : footer.length > 55 ? 8.0 : 9.0)
      : (footer.length > 105 ? 8.0 : footer.length > 75 ? 9.0 : 10));
    slide.addText(footer, textOpts({
      x: MARGIN_X,
      y: y,
      w: hasSources ? totalW * 0.48 : totalW * 0.55,
      h: FOOTER_H,
      fontFace: preset.font_body,
      fontSize: footerFont,
      color: footerInk,
      valign: 'middle',
      fit: 'shrink',
      objectName: 'metadata:footer-text',
    }));
  }
  if (provenanceParts.length) {
    const sourceText = provenanceParts.join(' · ');
    const pageW = showPageNumber && pageNumber ? 0.55 : 0;
    const totalW = SLIDE_W - MARGIN_X * 2 - pageW - (pageW ? 0.16 : 0);
    const sourceOnly = !footer;
    const sourceX = sourceOnly ? MARGIN_X : MARGIN_X + totalW * 0.52;
    const sourceW = sourceOnly ? totalW : totalW * 0.48;
    const sourceFont = roleMetadataFont(preset, sourceText.length > 170 ? 7.2 : sourceText.length > 115 ? 8.0 : 9.0);
    slide.addText(sourceText, textOpts({
      x: sourceX,
      y: y,
      w: sourceW,
      h: FOOTER_H,
      fontFace: preset.font_body,
      fontSize: sourceFont,
      color: footerInk,
      italic: true,
      align: sourceOnly ? 'left' : 'right',
      valign: 'middle',
      fit: 'shrink',
      objectName: 'metadata:footer-sources',
    }));
  }
  if (showPageNumber && pageNumber) {
    slide.addText(pageNumber, textOpts({
      x: SLIDE_W - MARGIN_X - 0.50,
      y,
      w: 0.50,
      h: FOOTER_H,
      fontFace: preset.font_body,
      fontSize: roleMetadataFont(preset, 9),
      color: footerInk,
      align: 'right',
      valign: 'middle',
      objectName: 'metadata:footer-page-number',
    }));
  }
}

function attachNotes(slide, slideData) {
  const notes = safeText(slideData.notes);
  if (notes) slide.addNotes(notes);
}

// ---------------------------------------------------------------------------
// Title slide: big hero title, centered, no dark header bar.
// ---------------------------------------------------------------------------

function addTitleFooter(slide, preset, slideData, colorOverride) {
  const footer = safeText(slideData.footer);
  if (!footer) return;
  const footerColor = colorOverride || firstReadableColor(
    cleanHex(preset.bg_dark, '0F172A'),
    [preset.title_footer_color, preset.text_muted, '94A3B8', 'CBD5E1', 'FFFFFF'],
    4.5,
  );
  slide.addText(footer, textOpts({
    x: MARGIN_X,
    y: SLIDE_H - 0.40,
    w: SLIDE_W - MARGIN_X * 2,
    h: 0.25,
    fontFace: preset.font_body,
    fontSize: 10,
    color: footerColor,
    valign: 'middle',
  }));
}

function addTitleKicker(slide, preset, text, box) {
  const label = safeText(text, 'PRESENTATION');
  slide.addText(label.toUpperCase(), textOpts({
    x: box.x,
    y: box.y,
    w: box.w,
    h: box.h,
    fontFace: preset.font_heading,
    fontSize: box.fontSize || 9,
    bold: true,
    color: box.color || preset.accent_primary,
    charSpacing: box.charSpacing === undefined ? 1.8 : box.charSpacing,
  }));
}

function addHeroFrame(slide, heroPath, preset, box, options) {
  if (!heroPath || !fs.existsSync(heroPath)) return false;
  const opts = options || {};
  const pad = opts.pad === undefined ? 0.08 : opts.pad;
  if (opts.surface !== false) {
    slide.addShape('rect', shapeOpts({
      x: box.x,
      y: box.y,
      w: box.w,
      h: box.h,
      fill: { color: opts.fill || preset.surface || 'FFFFFF', transparency: opts.fillTransparency || 0 },
      line: { color: opts.line || preset.line || 'CBD5E1', width: opts.lineWidth || 0.75 },
    }));
  }
  try {
    const sized = imageSizingContainLocal(
      heroPath,
      box.x + pad,
      box.y + pad,
      box.w - pad * 2,
      box.h - pad * 2,
    );
    slide.addImage(Object.assign({ path: heroPath }, sized));
    return true;
  } catch (e) {
    console.warn('[pptxgenjs] hero_image failed:', e.message);
    return false;
  }
}

function titleTextSizing(titleText, boxW, baseFont, minFont) {
  const titleFont = Math.max(minFont || 27, Math.min(baseFont, Math.floor(baseFont - Math.max(0, titleText.length - 32) * 0.32)));
  // Cover titles use display fonts and tend to wrap taller than body-text
  // estimates, especially with serif pairs. Over-reserve slightly so a
  // folded title cannot collide with subtitle or hero metadata.
  const titleH = Math.min(2.28, Math.max(0.96, estimateTextHeight(titleText, titleFont, boxW, 1.32) + 0.22));
  return { titleFont, titleH };
}

function renderTitleSplit(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg_dark);
  addBackgroundImage(slide, slideData.background_image, preset);

  // When a hero image is staged, place it on the right half and narrow the
  // text column to the left half. Otherwise use the standard full-width layout.
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const textRight = hasHero ? 5.3 : SLIDE_W - MARGIN_X;
  const textW = textRight - MARGIN_X;

  addTitleMotif(slide, preset, hasHero);

  if (hasHero) {
    try {
      const imgX = 5.6;
      const imgY = 0.85;
      const imgW = SLIDE_W - imgX - MARGIN_X;
      const imgH = SLIDE_H - imgY - 0.85;
      const sized = imageSizingContainLocal(heroPath, imgX, imgY, imgW, imgH);
      slide.addImage(Object.assign({ path: heroPath }, sized));
    } catch (e) {
      console.warn('[pptxgenjs] hero_image failed:', e.message);
    }
  }

  // Accent stripe, left-aligned, as an editorial touch.
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 1.85,
    w: 0.6,
    h: 0.08,
    fill: { color: preset.accent_primary },
  }));

  const titleText = safeText(slideData.title, 'Untitled Deck');
  const titleFont = hasHero
    ? (titleText.length > 30 ? 32 : 36)
    : (titleText.length > 28 ? 40 : 44);
  const titleH = hasHero
    ? (titleText.length > 30 ? 1.72 : 1.35)
    : (titleText.length > 24 ? 1.85 : 1.45);
  const titleY = 2.00;

  slide.addText(titleText, textOpts({
    x: MARGIN_X,
    y: titleY,
    w: textW,
    h: titleH,
    fontFace: preset.font_heading,
    fontSize: titleFont,
    bold: true,
    color: 'FFFFFF',
    valign: 'top',
  }));

  const subtitle = safeText(slideData.subtitle);
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: MARGIN_X,
      y: titleY + titleH + 0.10,
      w: textW,
      h: subtitle.length > 70 ? 1.12 : 0.9,
      fontFace: preset.font_body,
      fontSize: hasHero ? 13 : 20,
      color: darkSlideSubtitleColor(preset),
      valign: 'top',
    }));
  }

  addTitleFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderTitleLabPlate(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg || 'FFFFFF');
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const titleText = safeText(slideData.title, 'Untitled Deck');
  const subtitle = safeText(slideData.subtitle);
  const dark = cleanHex(preset.bg_dark, '0B2545');
  const red = cleanHex(preset.accent_secondary, 'C9302C');

  slide.addShape('rect', shapeOpts({
    x: 0, y: 0, w: SLIDE_W, h: 0.72,
    fill: { color: dark },
    line: { color: dark, width: 0 },
  }));
  slide.addShape('rect', shapeOpts({
    x: 0, y: 0.72, w: SLIDE_W, h: 0.06,
    fill: { color: red },
    line: { color: red, width: 0 },
  }));
  addTitleKicker(slide, preset, slideData.kicker || 'LAB PRESENTATION', {
    x: MARGIN_X,
    y: 0.28,
    w: 3.0,
    h: 0.20,
    color: 'FFFFFF',
    fontSize: 8.5,
  });

  const textW = hasHero ? 5.05 : SLIDE_W - MARGIN_X * 2;
  const sizing = titleTextSizing(titleText, textW, hasHero ? 32 : 36, 25);
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 1.22,
    w: 0.10,
    h: Math.max(1.35, sizing.titleH + (subtitle ? 0.75 : 0.15)),
    fill: { color: red },
    line: { color: red, width: 0 },
  }));
  slide.addText(titleText, textOpts({
    x: MARGIN_X + 0.25,
    y: 1.16,
    w: textW - 0.25,
    h: sizing.titleH,
    fontFace: preset.font_heading,
    fontSize: sizing.titleFont,
    bold: true,
    color: dark,
    fit: 'shrink',
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: MARGIN_X + 0.25,
      y: 1.16 + sizing.titleH + 0.18,
      w: textW - 0.25,
      h: 0.82,
      fontFace: preset.font_body,
      fontSize: hasHero ? 13.5 : 16,
      color: preset.text_muted,
      fit: 'shrink',
    }));
  }

  if (hasHero) {
    addHeroFrame(slide, heroPath, preset, { x: 6.25, y: 1.10, w: 3.05, h: 3.10 }, {
      pad: 0.07,
      line: preset.line,
    });
  }

  const labelY = 4.58;
  const rawChips = Array.isArray(slideData.chips)
    ? slideData.chips
    : (Array.isArray(slideData.evidence_chips) ? slideData.evidence_chips : ['Evidence', 'Readout', 'Next run']);
  const micro = rawChips.map((label) => safeText(label)).filter(Boolean).slice(0, 5);
  const chipGap = 0.13;
  const chipRight = hasHero ? 5.58 : SLIDE_W - MARGIN_X;
  const chipW = Math.min(1.82, (chipRight - MARGIN_X - chipGap * Math.max(0, micro.length - 1)) / Math.max(1, micro.length));
  micro.forEach((label, idx) => {
    const x = MARGIN_X + idx * (chipW + chipGap);
    slide.addShape('rect', shapeOpts({
      x,
      y: labelY,
      w: chipW,
      h: 0.34,
      fill: { color: idx === 0 ? dark : 'F8FAFC' },
      line: { color: idx === 0 ? dark : preset.line, width: 0.75 },
    }));
    slide.addText(label.toUpperCase(), textOpts({
      x: x + 0.10,
      y: labelY + 0.06,
      w: Math.max(0.4, chipW - 0.20),
      h: 0.22,
      fontFace: preset.font_heading,
      fontSize: 8.0,
      bold: true,
      color: idx === 0 ? 'FFFFFF' : dark,
      charSpacing: 1.2,
      fit: 'shrink',
    }));
  });

  addTitleFooter(slide, preset, slideData, preset.text_muted);
  attachNotes(slide, slideData);
}

function renderTitleCommandCenter(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg_dark);
  addBackgroundImage(slide, slideData.background_image, preset);
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const accent = cleanHex(preset.accent_secondary || preset.accent_primary, 'DC2626');
  const titleText = safeText(slideData.title, 'Untitled Deck');
  const subtitle = safeText(slideData.subtitle);
  const textW = hasHero ? 5.55 : SLIDE_W - 1.30;

  addTitleMotif(slide, Object.assign({}, preset, { title_motif: preset.title_motif || 'network' }), hasHero);
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 0.62,
    w: SLIDE_W - MARGIN_X * 2,
    h: 0.02,
    fill: { color: 'FFFFFF', transparency: 76 },
  }));
  addTitleKicker(slide, preset, slideData.kicker || 'BOARD BRIEF', {
    x: MARGIN_X,
    y: 0.34,
    w: 2.6,
    h: 0.18,
    color: accent,
    fontSize: 8.2,
  });

  if (hasHero) {
    addHeroFrame(slide, heroPath, preset, { x: 6.45, y: 1.05, w: 3.0, h: 3.30 }, {
      pad: 0.05,
      fill: preset.bg_dark,
      fillTransparency: 15,
      line: accent,
      lineWidth: 1.0,
    });
  }

  const sizing = titleTextSizing(titleText, textW, 36, 27);
  slide.addText(titleText, textOpts({
    x: MARGIN_X,
    y: 1.12,
    w: textW,
    h: sizing.titleH,
    fontFace: preset.font_heading,
    fontSize: sizing.titleFont,
    bold: true,
    color: 'FFFFFF',
    fit: 'shrink',
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: MARGIN_X,
      y: 1.12 + sizing.titleH + 0.18,
      w: textW,
      h: 0.86,
      fontFace: preset.font_body,
      fontSize: 13,
      color: darkSlideSubtitleColor(preset),
      fit: 'shrink',
    }));
  }

  const stripY = 4.55;
  const stripW = (SLIDE_W - MARGIN_X * 2 - 0.16 * 2) / 3;
  ['Risk', 'Control', 'Action'].forEach((label, idx) => {
    const x = MARGIN_X + idx * (stripW + 0.16);
    slide.addShape('rect', shapeOpts({
      x, y: stripY, w: stripW, h: 0.34,
      fill: { color: idx === 0 ? accent : 'FFFFFF', transparency: idx === 0 ? 8 : 88 },
      line: { color: idx === 0 ? accent : 'FFFFFF', transparency: idx === 0 ? 0 : 82, width: 0.6 },
    }));
    slide.addText(label.toUpperCase(), textOpts({
      x: x + 0.10,
      y: stripY + 0.09,
      w: stripW - 0.20,
      h: 0.16,
      fontFace: preset.font_heading,
      fontSize: 7.8,
      bold: true,
      color: 'FFFFFF',
      charSpacing: 1.3,
      align: 'center',
    }));
  });

  addTitleFooter(slide, preset, slideData, '94A3B8');
  attachNotes(slide, slideData);
}

function renderTitlePoster(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg_dark);
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const titleText = safeText(slideData.title, 'Untitled Deck');
  const subtitle = safeText(slideData.subtitle);
  const accent = cleanHex(preset.accent_primary, 'FF6B35');
  const secondary = cleanHex(preset.accent_secondary, '22C55E');

  slide.addShape('ellipse', shapeOpts({
    x: -1.1, y: -1.0, w: 3.6, h: 3.6,
    fill: { color: accent, transparency: 78 },
    line: { color: accent, transparency: 100, width: 0 },
  }));
  slide.addShape('rect', shapeOpts({
    x: 0, y: 4.48, w: SLIDE_W, h: 0.56,
    fill: { color: secondary, transparency: 18 },
    line: { color: secondary, transparency: 100, width: 0 },
  }));

  if (hasHero) {
    try {
      slide.addImage({
        path: heroPath,
        x: 5.15,
        y: 0.0,
        w: SLIDE_W - 5.15,
        h: SLIDE_H,
        sizing: { type: 'cover', w: SLIDE_W - 5.15, h: SLIDE_H },
        transparency: 8,
      });
      slide.addShape('rect', shapeOpts({
        x: 4.65, y: 0, w: 5.35, h: SLIDE_H,
        fill: { color: preset.bg_dark, transparency: 42 },
        line: { color: preset.bg_dark, transparency: 100, width: 0 },
      }));
    } catch (e) {
      console.warn('[pptxgenjs] hero_image failed:', e.message);
    }
  }

  addTitleKicker(slide, preset, slideData.kicker || 'LAUNCH STORY', {
    x: MARGIN_X,
    y: 0.72,
    w: 2.8,
    h: 0.20,
    color: accent,
    fontSize: 8.8,
  });
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 1.02,
    w: 0.72,
    h: 0.08,
    fill: { color: accent },
    line: { color: accent, width: 0 },
  }));

  const textW = hasHero ? 4.65 : 8.6;
  const x = hasHero ? MARGIN_X : 0.70;
  const align = hasHero ? 'left' : 'center';
  const sizing = titleTextSizing(titleText, textW, hasHero ? 39 : 46, 30);
  slide.addText(titleText, textOpts({
    x,
    y: hasHero ? 1.34 : 1.55,
    w: textW,
    h: sizing.titleH,
    fontFace: preset.font_heading,
    fontSize: sizing.titleFont,
    bold: true,
    color: 'FFFFFF',
    align,
    fit: 'shrink',
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x,
      y: (hasHero ? 1.34 : 1.55) + sizing.titleH + 0.18,
      w: textW,
      h: 0.85,
      fontFace: preset.font_body,
      fontSize: hasHero ? 13.5 : 16,
      color: darkSlideSubtitleColor(preset),
      align,
      fit: 'shrink',
    }));
  }

  addTitleFooter(slide, preset, slideData, 'CBD5E1');
  attachNotes(slide, slideData);
}

function renderTitleMasthead(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg || 'FAF6EC');
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const titleText = safeText(slideData.title, 'Untitled Deck');
  const subtitle = safeText(slideData.subtitle);
  const textColor = cleanHex(preset.text || preset.text_primary, '2A2118');
  const muted = cleanHex(preset.text_muted, '6B5B42');
  const accent = cleanHex(preset.accent_primary, '8B4513');
  const secondary = cleanHex(preset.accent_secondary, accent);

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 0.55,
    w: SLIDE_W - MARGIN_X * 2,
    h: 0.02,
    fill: { color: accent },
    line: { color: accent, width: 0 },
  }));
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 0.66,
    w: SLIDE_W - MARGIN_X * 2,
    h: 0.01,
    fill: { color: preset.line || 'D9CBA8' },
    line: { color: preset.line || 'D9CBA8', width: 0 },
  }));
  addTitleKicker(slide, preset, slideData.kicker || 'EDITORIAL REPORT', {
    x: MARGIN_X,
    y: 0.28,
    w: 3.2,
    h: 0.18,
    color: accent,
    fontSize: 8.2,
  });

  const textW = hasHero ? 5.05 : 8.65;
  const sizing = titleTextSizing(titleText, textW, hasHero ? 31 : 41, 24);
  if (hasHero) {
    sizing.titleH = Math.max(sizing.titleH, 1.82);
  }
  slide.addText(titleText, textOpts({
    x: MARGIN_X,
    y: 1.18,
    w: textW,
    h: sizing.titleH,
    fontFace: preset.font_heading,
    fontSize: sizing.titleFont,
    bold: true,
    color: textColor,
    fit: 'shrink',
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: MARGIN_X,
      y: 1.18 + sizing.titleH + 0.18,
      w: textW,
      h: 0.82,
      fontFace: preset.font_body,
      fontSize: 13.5,
      color: muted,
      fit: 'shrink',
    }));
  }

  if (hasHero) {
    slide.addShape('rect', shapeOpts({
      x: 5.92,
      y: 1.00,
      w: 0.02,
      h: 3.72,
      fill: { color: preset.line || 'D9CBA8' },
      line: { color: preset.line || 'D9CBA8', width: 0 },
    }));
    addHeroFrame(slide, heroPath, preset, { x: 6.25, y: 1.00, w: 3.05, h: 3.72 }, {
      pad: 0.06,
      fill: 'FFFFFF',
      line: preset.line,
    });
  }

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 4.62,
    w: 1.35,
    h: 0.06,
    fill: { color: secondary },
    line: { color: secondary, width: 0 },
  }));
  addTitleFooter(slide, preset, slideData, muted);
  attachNotes(slide, slideData);
}

function renderTitleBroadsheet(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg || 'FFFFFF');
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const titleText = safeText(slideData.title, 'Untitled Deck');
  const subtitle = safeText(slideData.subtitle);
  const textColor = cleanHex(preset.text || preset.text_primary, '0A0A0A');
  const muted = cleanHex(preset.text_muted, '6B7280');
  const accent = cleanHex(preset.accent_primary, 'D4461E');
  const line = cleanHex(preset.line, 'E5E7EB');
  const dividerX = 7.08;

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X, y: 0.42, w: SLIDE_W - MARGIN_X * 2, h: 0.018,
    fill: { color: textColor }, line: { color: textColor, width: 0 },
  }));
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X, y: 0.50, w: 1.05, h: 0.055,
    fill: { color: accent }, line: { color: accent, width: 0 },
  }));
  addTitleKicker(slide, preset, slideData.kicker || 'EDITORIAL FIELD NOTE', {
    x: MARGIN_X, y: 0.20, w: 3.4, h: 0.18, color: accent, fontSize: 8.2,
  });

  const sizing = titleTextSizing(titleText, 6.08, 43, 29);
  slide.addText(titleText, textOpts({
    x: MARGIN_X,
    y: 1.14,
    w: 6.08,
    h: Math.max(1.72, sizing.titleH),
    fontFace: preset.font_heading,
    fontSize: sizing.titleFont,
    bold: true,
    color: textColor,
    fit: 'shrink',
  }));
  slide.addShape('rect', shapeOpts({
    x: dividerX, y: 1.10, w: 0.018, h: 4.72,
    fill: { color: line }, line: { color: line, width: 0 },
  }));
  slide.addShape('rect', shapeOpts({
    x: dividerX - 0.035, y: 1.10, w: 0.088, h: 0.82,
    fill: { color: accent }, line: { color: accent, width: 0 },
  }));

  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: 7.42,
      y: hasHero ? 1.18 : 3.02,
      w: 2.08,
      h: hasHero ? 0.92 : 1.38,
      fontFace: preset.font_body,
      fontSize: hasHero ? 13.5 : 12.5,
      color: muted,
      fit: 'shrink',
    }));
  }
  if (hasHero) {
    addHeroFrame(slide, heroPath, preset, { x: 7.42, y: 2.30, w: 2.08, h: 2.82 }, {
      pad: 0.04,
      fill: 'FFFFFF',
      line,
      lineWidth: 0.8,
    });
  } else {
    [4.46, 4.88, 5.30].forEach((y, idx) => {
      slide.addShape('rect', shapeOpts({
        x: 7.42,
        y,
        w: 2.08 - idx * 0.28,
        h: 0.018,
        fill: { color: idx === 0 ? textColor : line },
        line: { color: idx === 0 ? textColor : line, width: 0 },
      }));
    });
  }
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X, y: 5.82, w: 6.12, h: 0.018,
    fill: { color: textColor }, line: { color: textColor, width: 0 },
  }));
  addTitleFooter(slide, preset, slideData, muted);
  attachNotes(slide, slideData);
}

function renderTitleLightAtlas(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg || 'F8FAFC');
  const heroPath = slideData.__heroPath;
  const hasHero = heroPath && fs.existsSync(heroPath);
  const titleText = safeText(slideData.title, 'Untitled Deck');
  const subtitle = safeText(slideData.subtitle);
  const accent = cleanHex(preset.accent_primary, '0EA5E9');
  const textColor = cleanHex(preset.text || preset.text_primary, '0F172A');
  const muted = cleanHex(preset.text_muted, '64748B');

  for (let i = 0; i < 7; i += 1) {
    slide.addShape('line', shapeOpts({
      x: 6.05 + i * 0.42,
      y: 0.52,
      w: 0,
      h: 4.38,
      line: { color: preset.line || 'E2E8F0', transparency: 12, width: 0.5 },
    }));
  }
  [0.42, 0.76, 1.12].forEach((r, idx) => {
    slide.addShape('ellipse', shapeOpts({
      x: 7.65 - r,
      y: 2.70 - r,
      w: r * 2,
      h: r * 2,
      fill: { color: accent, transparency: 100 },
      line: { color: idx % 2 ? preset.accent_secondary : accent, transparency: 68, width: 0.9 },
    }));
  });

  addTitleKicker(slide, preset, slideData.kicker || 'POLICY BRIEF', {
    x: MARGIN_X,
    y: 0.72,
    w: 2.6,
    h: 0.18,
    color: accent,
    fontSize: 8.4,
  });
  const textW = hasHero ? 5.30 : 7.4;
  const sizing = titleTextSizing(titleText, textW, hasHero ? 38 : 42, 29);
  slide.addText(titleText, textOpts({
    x: MARGIN_X,
    y: 1.10,
    w: textW,
    h: sizing.titleH,
    fontFace: preset.font_heading,
    fontSize: sizing.titleFont,
    bold: true,
    color: textColor,
    fit: 'shrink',
  }));
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 1.10 + sizing.titleH + 0.10,
    w: 0.95,
    h: 0.06,
    fill: { color: accent },
    line: { color: accent, width: 0 },
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: MARGIN_X,
      y: 1.10 + sizing.titleH + 0.30,
      w: textW,
      h: 0.86,
      fontFace: preset.font_body,
      fontSize: 14,
      color: muted,
      fit: 'shrink',
    }));
  }

  if (hasHero) {
    addHeroFrame(slide, heroPath, preset, { x: 6.28, y: 1.00, w: 3.10, h: 3.65 }, {
      pad: 0.07,
      line: preset.line,
    });
  }
  addTitleFooter(slide, preset, slideData, muted);
  attachNotes(slide, slideData);
}

function renderTitleTelemetryBoard(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg_dark || '07111F');
  addGrammarFrame(slide, preset, slideData);
  const title = safeText(slideData.title, 'System review');
  const subtitle = safeText(slideData.subtitle);
  const accent = cleanHex(preset.accent_primary, '22D3EE');
  const secondary = cleanHex(preset.accent_secondary, 'F43F5E');
  const surface = cleanHex(preset.surface, '111827');
  const muted = darkSlideSubtitleColor(preset);

  slide.addShape('rect', shapeOpts({
    x: 0.42, y: 1.02, w: 1.72, h: 4.30,
    fill: { color: surface, transparency: 4 },
    line: { color: preset.line || '334155', width: 0.65 },
  }));
  slide.addText(safeText(slideData.kicker, 'SYSTEM STATUS'), textOpts({
    x: 0.62, y: 1.28, w: 1.32, h: 0.24,
    fontFace: preset.font_body, fontSize: 8, bold: true, color: accent,
    charSpacing: 1.2, fit: 'shrink',
  }));
  const statusText = safeText(slideData.status, 'OBSERVE');
  slide.addText(statusText, textOpts({
    x: 0.62, y: 1.78, w: 1.32, h: 0.72,
    fontFace: preset.font_heading, fontSize: statusText.length > 6 ? 15 : 24,
    bold: true, color: 'FFFFFF', align: 'center', fit: 'shrink',
  }));
  const telemetry = [
    ['ENV', safeText(slideData.environment, 'PROD')],
    ['WINDOW', safeText(slideData.window, '24H')],
    ['STATE', safeText(slideData.severity, 'WATCH')],
  ];
  telemetry.forEach(([label, value], idx) => {
    const y = 3.02 + idx * 0.66;
    slide.addText(label, textOpts({
      x: 0.62, y, w: 0.52, h: 0.16, fontFace: preset.font_body,
      fontSize: 7.8, bold: true, color: muted, fit: 'shrink',
    }));
    slide.addText(value, textOpts({
      x: 1.18, y: y - 0.02, w: 0.76, h: 0.20, fontFace: preset.font_body,
      fontSize: 8.5, bold: true, color: idx === 2 ? secondary : 'FFFFFF', align: 'right', fit: 'shrink',
    }));
    slide.addShape('line', shapeOpts({
      x: 0.62, y: y + 0.26, w: 1.32, h: 0,
      line: { color: preset.line || '334155', width: 0.45, transparency: 20 },
    }));
  });

  slide.addText(title, textOpts({
    x: 2.58, y: 1.36, w: 6.72, h: 1.56,
    fontFace: preset.font_heading, fontSize: 38, bold: true, color: 'FFFFFF', fit: 'shrink',
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: 2.58, y: 3.18, w: 5.92, h: 0.72,
      fontFace: preset.font_body, fontSize: 14, color: muted, fit: 'shrink',
    }));
  }
  slide.addShape('rect', shapeOpts({
    x: 2.58, y: 4.54, w: 6.48, h: 0.62,
    fill: { color: surface, transparency: 2 },
    line: { color: preset.line || '334155', width: 0.55 },
  }));
  ['SIGNAL', 'DEPENDENCY', 'ACTION'].forEach((label, idx) => {
    slide.addText(label, textOpts({
      x: 2.78 + idx * 2.02, y: 4.74, w: 1.62, h: 0.18,
      fontFace: preset.font_body, fontSize: 7.8, bold: true,
      color: idx === 1 ? secondary : accent, align: 'center', fit: 'shrink',
    }));
  });
  addTitleFooter(slide, preset, slideData, muted);
  attachNotes(slide, slideData);
}

function contractStageUsesDarkBackground(contract) {
  return new Set([
    'investor-thesis-stage',
    'operations-grid',
    'technical-telemetry-canvas',
  ]).has(String(contract && contract.composition_grammar_id || '').trim().toLowerCase());
}

function contractStageExplicitValue(slideData, slotName) {
  return [
    slideData[slotName],
    slotName === 'status' ? slideData.status : '',
    slotName === 'index' ? slideData.section_number : '',
    slotName === 'folio' ? slideData.section_number : '',
    slotName === 'stage' ? slideData.kicker : '',
    slotName === 'study_id' ? slideData.study_id : '',
    slotName === 'docket' ? slideData.docket_id : '',
    slotName === 'layer' ? slideData.layer : '',
  ].map((value) => safeText(value)).find(Boolean) || '';
}

function contractStageValue(slideData, slotName, index, kind) {
  const explicit = contractStageExplicitValue(slideData, slotName);
  if (explicit) return explicit;
  if (kind === 'section' && ['index', 'folio', 'stage', 'cycle', 'docket', 'layer'].includes(slotName)) {
    return String(index + 1).padStart(2, '0');
  }
  const defaults = {
    anchor: 'ANSWER',
    method: 'METHOD',
    pathway: 'PATHWAY',
    signal: 'SIGNAL',
    controls: 'CONTROL',
    control: 'CONTROL',
    stakeholders: 'PUBLIC',
    accountability: 'OWNER',
    verification: 'VERIFY',
    signals: 'LIVE',
    thesis: 'THESIS',
    masthead: 'REPORT',
    study_id: 'STUDY',
    status: 'ACTIVE',
    stage: 'PHASE',
    cycle: 'CYCLE',
    docket: 'DOCKET',
    layer: 'LAYER',
    folio: 'SECTION',
    index: 'SECTION',
  };
  return defaults[slotName] || slotName.replace(/_/g, ' ').toUpperCase();
}

function renderPolicyContractStage(slide, slideData, preset, contract, kind) {
  if (!isPolicyPublicDocket(preset, slideData)) return false;
  if (!['title-public-question', 'section-policy-docket'].includes(safeText(contract.system_id))) return false;

  const background = cleanHex(preset.bg, 'F6F8F5');
  const text = cleanHex(preset.text || preset.text_primary, '243133');
  const muted = cleanHex(preset.text_muted, '5F6F70');
  const accent = cleanHex(preset.accent_primary, 'C65D3B');
  const secondary = cleanHex(preset.accent_secondary, '2F7D76');
  const line = cleanHex(preset.line, 'D8E1DD');
  const title = safeText(slideData.title, kind === 'title' ? 'Public decision' : 'Policy section');
  const subtitle = safeText(slideData.subtitle);
  const subtitleLines = subtitle.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  const metric = kind === 'title' ? policyDecisionMetric(slideData) : '';
  let headline = metric ? title.replace(metric, '').replace(/\s{2,}/g, ' ').trim() : title;
  const lead = subtitleLines[0] || '';
  if (metric && headline.length <= 18 && lead) {
    const fundingLead = lead.match(/^(?:fund|authorize)\s+(?:option\s+[A-Z0-9]+:\s*)?(?:a|an|the)?\s*(.+)$/i);
    headline = /^approve$/i.test(headline) && fundingLead
      ? `Approve the ${fundingLead[1]}`
      : `${headline}: ${lead}`;
  }
  const supportLines = metric && lead ? subtitleLines.slice(1) : subtitleLines;
  const support = supportLines.join('\n');

  paintBackground(slide, background);
  addBackgroundImage(slide, slideData.background_image, preset);
  addGrammarFrame(slide, preset, slideData);

  const kicker = safeText(slideData.kicker, kind === 'title' ? 'PUBLIC DECISION' : 'PUBLIC DOCKET').toUpperCase();
  slide.addText(kicker, textOpts({
    x: 0.68, y: 0.44, w: 3.8, h: 0.28,
    fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
    bold: true, color: secondary, charSpacing: 1.0, fit: 'shrink',
    objectName: `metadata:${kind}-kicker`,
  }));

  if (kind === 'title') {
    const hasMetric = Boolean(metric);
    const headlineW = hasMetric ? 6.18 : 8.55;
    const headlineFont = headline.length > 54 ? 29 : (headline.length > 34 ? 30 : 41);
    slide.addText(headline, textOpts({
      x: 0.68, y: 1.16, w: headlineW, h: 1.70,
      fontFace: preset.font_heading, fontSize: headlineFont,
      bold: true, color: text, fit: 'shrink', valign: 'middle',
      objectName: 'slide-title:title',
    }));
    slide.addShape('line', shapeOpts({
      x: 0.68, y: 3.12, w: hasMetric ? 5.28 : 6.90, h: 0,
      line: { color: line, width: 0.8 },
      objectName: 'decorative:policy-title-divider',
    }));
    if (support) {
      slide.addText(support, textOpts({
        x: 0.68, y: 3.36, w: hasMetric ? 5.48 : 7.30, h: 1.02,
        fontFace: preset.font_body, fontSize: roleBodyFont(preset, 15),
        color: muted, fit: 'shrink', valign: 'top',
      }));
    }
    if (hasMetric) {
      const panelX = 7.10;
      const panelY = 0.62;
      const panelW = 2.45;
      const panelH = 4.48;
      slide.addShape('rect', shapeOpts({
        x: panelX, y: panelY, w: panelW, h: panelH,
        fill: { color: accent }, line: { color: accent, width: 0 },
        objectName: 'role-contract-slot:title:decision-metric',
      }));
      slide.addText(metric, textOpts({
        x: panelX + 0.28, y: panelY + 0.52, w: panelW - 0.56, h: 0.82,
        fontFace: preset.font_heading, fontSize: metric.length > 7 ? 27 : 34,
        bold: true, color: 'FFFFFF', fit: 'shrink',
      }));
      slide.addText(safeText(slideData.hero_metric_label, 'APPROPRIATION'), textOpts({
        x: panelX + 0.28, y: panelY + 1.40, w: panelW - 0.56, h: 0.28,
        fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
        bold: true, color: 'FFFFFF', charSpacing: 0.8, fit: 'shrink',
        objectName: 'metadata:title-metric-label',
      }));
      slide.addShape('line', shapeOpts({
        x: panelX + 0.28, y: panelY + 1.98, w: panelW - 0.56, h: 0,
        line: { color: 'FFFFFF', transparency: 36, width: 0.75 },
      }));
      const detailItems = subtitleLines.slice(1).flatMap((lineText) => lineText.split(/\s*[•|]\s*/)).filter(Boolean).slice(0, 4);
      if (detailItems.length) {
        const itemH = Math.min(0.70, 2.20 / detailItems.length);
        detailItems.forEach((item, index) => {
          slide.addText(item, textOpts({
            x: panelX + 0.28, y: panelY + 2.22 + index * itemH,
            w: panelW - 0.56, h: itemH - 0.06,
            fontFace: preset.font_body, fontSize: roleBodyFont(preset, 13.5),
            bold: index === 0, color: 'FFFFFF', fit: 'shrink', valign: 'middle',
          }));
        });
      }
    }
  } else {
    slide.addText(title, textOpts({
      x: 0.68, y: 1.72, w: 6.20, h: 1.52,
      fontFace: preset.font_heading, fontSize: title.length > 52 ? 33 : 39,
      bold: true, color: text, fit: 'shrink', valign: 'middle',
      objectName: 'slide-title:section',
    }));
    if (subtitle) {
      slide.addText(subtitle, textOpts({
        x: 7.42, y: 1.78, w: 2.02, h: 1.76,
        fontFace: preset.font_body, fontSize: roleBodyFont(preset, 14),
        color: muted, fit: 'shrink', valign: 'middle',
      }));
      slide.addShape('rect', shapeOpts({
        x: 7.18, y: 1.78, w: 0.06, h: 1.76,
        fill: { color: secondary }, line: { color: secondary, width: 0 },
      }));
    }
  }

  if (hasFooterChrome(slideData, preset)) addFooter(slide, preset, slideData);
  else addTitleFooter(slide, preset, slideData, muted);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, kind, ['headline', ...(subtitle ? ['support'] : []), ...(metric ? ['stakeholders'] : [])]);
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = `policy-${kind}-stage`;
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderContractStage(slide, slideData, preset, contract, kind) {
  if (renderPolicyContractStage(slide, slideData, preset, contract, kind)) return true;
  const dark = contractStageUsesDarkBackground(contract);
  const background = dark ? cleanHex(preset.bg_dark, '0B1220') : cleanHex(preset.bg, 'FFFFFF');
  const text = dark ? 'FFFFFF' : cleanHex(preset.text || preset.text_primary, '0F172A');
  const muted = dark
    ? firstReadableColor(background, [preset.text_muted, 'CBD5E1', 'FFFFFF'], 3.0)
    : cleanHex(preset.text_muted, '64748B');
  const accent = cleanHex(preset.accent_primary, '1493A4');
  const secondary = cleanHex(preset.accent_secondary, accent);
  const line = dark
    ? firstReadableColor(background, [preset.line, '475569', 'CBD5E1'], 2.0)
    : cleanHex(preset.line, 'CBD5E1');
  const canvas = { x: 0, y: 0, w: SLIDE_W, h: SLIDE_H };
  const headline = roleSlot(contract, 'headline', canvas);
  if (!headline) return false;
  const support = roleSlot(contract, 'support', canvas);
  const heroPath = slideData.__heroPath;
  const reserved = new Set(['headline', 'support']);
  const anchorNames = Object.keys(contract.slots || {}).filter((name) => {
    if (reserved.has(name)) return false;
    if (kind === 'title' && name === 'stakeholders') return false;
    if (
      kind === 'title'
      && !heroPath
      && slideData.show_stage_anchors !== true
      && !contractStageExplicitValue(slideData, name)
    ) return false;
    return true;
  });
  const title = safeText(slideData.title, kind === 'title' ? 'Untitled Deck' : 'Section');
  const subtitle = safeText(slideData.subtitle);
  const dense = contract.variant === 'dense';

  paintBackground(slide, background);
  addBackgroundImage(slide, slideData.background_image, preset);
  addGrammarFrame(slide, preset, slideData);

  const kicker = safeText(
    slideData.kicker,
    kind === 'title' ? 'PRESENTATION' : 'SECTION',
  );
  const kickerY = Math.max(0.18, headline.y - 0.36);
  slide.addText(kicker.toUpperCase(), textOpts({
    x: headline.x,
    y: kickerY,
    w: Math.min(Math.max(2.4, headline.w * 0.78), 4.8),
    h: 0.24,
    fontFace: preset.font_body,
    fontSize: roleMetadataFont(preset, dense ? 8.0 : 8.2),
    bold: true,
    color: accent,
    charSpacing: 1.1,
    fit: 'shrink',
    objectName: `metadata:${kind}-kicker`,
  }));
  slide.addShape('rect', shapeOpts({
    x: headline.x,
    y: kickerY + 0.24,
    w: Math.min(1.15, Math.max(0.42, headline.w * 0.18)),
    h: 0.045,
    fill: { color: accent },
    line: { color: accent, width: 0 },
    objectName: `decorative:role-contract-accent:${kind}:heading`,
  }));

  const baseTitleFont = kind === 'title' ? 45 : 39;
  const widthPenalty = Math.max(0, 5.2 - headline.w) * 3.1;
  const heightPenalty = Math.max(0, 1.45 - headline.h) * 6.0;
  const minTitleFont = kind === 'title' ? 25 : 23;
  const preferredTitleFont = Math.max(
    minTitleFont,
    baseTitleFont - widthPenalty - heightPenalty - (dense ? 4 : 0),
  );
  const titleFont = fitFontToBox(
    title,
    preferredTitleFont,
    minTitleFont,
    headline.w,
    headline.h,
    1.18,
  );
  slide.addText(title, textOpts({
    x: headline.x,
    y: headline.y,
    w: headline.w,
    h: headline.h,
    fontFace: preset.font_heading,
    fontSize: titleFont,
    bold: true,
    color: text,
    fit: 'shrink',
    valign: 'middle',
    objectName: `slide-title:${kind}`,
  }));

  if (subtitle) {
    const box = support || {
      x: headline.x,
      y: Math.min(SLIDE_H - 0.88, headline.y + headline.h + 0.24),
      w: Math.min(headline.w, SLIDE_W - headline.x - 0.42),
      h: 0.62,
    };
    const subtitleFont = roleBodyFont(preset, dense ? 11.5 : (kind === 'title' ? 14.5 : 13.5));
    const availableSubtitleH = Math.max(0.28, SLIDE_H - box.y - 0.62);
    const subtitleH = Math.min(
      availableSubtitleH,
      Math.max(box.h, estimateTextHeight(subtitle, subtitleFont, box.w, 1.18) + 0.22),
    );
    slide.addText(subtitle, textOpts({
      x: box.x,
      y: box.y,
      w: box.w,
      h: subtitleH,
      fontFace: preset.font_body,
      fontSize: subtitleFont,
      color: muted,
      fit: 'shrink',
      valign: 'top',
    }));
  }

  const largestAnchor = anchorNames
    .map((name) => ({ name, box: roleSlot(contract, name, canvas) }))
    .filter((item) => item.box)
    .sort((left, right) => right.box.w * right.box.h - left.box.w * left.box.h)[0];
  const heroRendered = Boolean(
    largestAnchor && heroPath && fs.existsSync(heroPath) &&
    addHeroFrame(slide, heroPath, preset, largestAnchor.box, {
      pad: 0.04,
      fill: background,
      fillTransparency: 0,
      line,
      lineWidth: 0.75,
    })
  );

  anchorNames.forEach((name, index) => {
    const box = roleSlot(contract, name, canvas);
    if (!box || (heroRendered && largestAnchor && name === largestAnchor.name)) return;
    const horizontal = box.w >= box.h * 2.2;
    const compact = box.w < 1.35 || box.h < 0.72;
    slide.addShape('rect', shapeOpts({
      x: box.x,
      y: box.y,
      w: box.w,
      h: box.h,
      objectName: `role-contract-slot:${kind}:${name}`,
      fill: { color: background, transparency: 100 },
      line: { color: index % 2 ? secondary : line, width: index === 0 ? 0.85 : 0.55 },
    }));
    slide.addShape('rect', shapeOpts({
      x: box.x,
      y: box.y,
      w: horizontal ? Math.min(box.w, 0.72) : Math.min(0.055, box.w * 0.08),
      h: horizontal ? Math.min(0.055, box.h * 0.14) : box.h,
      fill: { color: index % 2 ? secondary : accent },
      line: { color: index % 2 ? secondary : accent, width: 0 },
      objectName: `decorative:role-contract-accent:${kind}:${name}`,
    }));
    const label = name.replace(/_/g, ' ').toUpperCase();
    const value = contractStageValue(slideData, name, index, kind);
    const pad = compact ? 0.08 : 0.14;
    if (horizontal && box.h < 0.80) {
      slide.addText(`${label}  /  ${value}`, textOpts({
        x: box.x + pad,
        y: box.y + pad,
        w: Math.max(0.28, box.w - pad * 2),
        h: Math.max(0.28, box.h - pad * 2),
        fontFace: preset.font_body,
        fontSize: roleMetadataFont(preset, 9.0),
        bold: true,
        color: muted,
        charSpacing: 0.8,
        fit: 'shrink',
        valign: 'middle',
        objectName: `metadata:${kind}-${name}-label`,
      }));
      return;
    }
    const labelH = compact
      ? Math.max(0.16, Math.min(0.24, box.h * 0.26))
      : 0.20;
    const valueY = box.y + pad + labelH + 0.10;
    slide.addText(label, textOpts({
      x: box.x + pad,
      y: box.y + pad,
      w: Math.max(0.28, box.w - pad * 2),
      h: labelH,
      fontFace: preset.font_body,
      fontSize: roleMetadataFont(preset, compact ? 8.0 : 8.2),
      bold: true,
      color: muted,
      charSpacing: compact ? 0.4 : 0.8,
      fit: 'shrink',
      align: horizontal ? 'left' : 'center',
      objectName: `metadata:${kind}-${name}-label`,
    }));
    const valueFont = compact ? 10 : Math.min(20, 10 + box.w * 2.2);
    const valueW = Math.max(0.28, box.w - pad * 2);
    const availableValueH = Math.max(0.20, box.y + box.h - valueY - pad);
    const valueH = Math.min(
      availableValueH,
      Math.max(0.24, estimateTextHeight(value, valueFont, valueW, 1.12) + 0.12),
    );
    slide.addText(value, textOpts({
      x: box.x + pad,
      y: valueY + Math.max(0, (availableValueH - valueH) / 2),
      w: valueW,
      h: valueH,
      fontFace: preset.font_heading,
      fontSize: valueFont,
      bold: true,
      color: index % 2 ? secondary : accent,
      fit: 'shrink',
      align: horizontal ? 'left' : 'center',
      valign: 'middle',
      objectName: `metadata:${kind}-${name}-value`,
    }));
  });

  if (hasFooterChrome(slideData, preset)) {
    addFooter(slide, preset, slideData);
  } else {
    addTitleFooter(slide, preset, slideData, muted);
  }
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    kind,
    [
      'headline',
      ...(subtitle && support ? ['support'] : []),
      ...anchorNames,
    ],
  );
  return true;
}

function renderTitle(pptx, slide, slideData, preset) {
  const titleContract = roleContract(preset, slideData, 'title');
  if (titleContract) {
    renderContractStage(slide, slideData, preset, titleContract, 'title');
    return;
  }
  const titleSystem = roleSystem(preset, slideData, 'title');
  const roleLayout = {
    'answer-cover': 'split-hero',
    'title-answer-ledger': 'split-hero',
    'evidence-cover': 'lab-plate',
    'title-study-plate': 'lab-plate',
    'care-dossier': 'light-atlas',
    'title-clinical-status': 'light-atlas',
    'editorial-cover': 'broadsheet',
    'title-editorial-masthead': 'broadsheet',
    'thesis-cover': 'poster',
    'title-investor-thesis': 'poster',
    'operating-cover': 'command-center',
    'title-operations-state': 'command-center',
    'docket-cover': 'masthead',
    'title-public-question': 'masthead',
    'telemetry-cover': 'telemetry-board',
    'title-telemetry-state': 'telemetry-board',
  }[titleSystem];
  const layout = String(slideData.title_layout || roleLayout || preset.title_layout || 'split-hero')
    .trim()
    .toLowerCase();
  if (layout === 'lab-plate') {
    renderTitleLabPlate(pptx, slide, slideData, preset);
  } else if (layout === 'command-center') {
    renderTitleCommandCenter(pptx, slide, slideData, preset);
  } else if (layout === 'poster') {
    renderTitlePoster(pptx, slide, slideData, preset);
  } else if (layout === 'masthead') {
    renderTitleMasthead(pptx, slide, slideData, preset);
  } else if (layout === 'broadsheet') {
    renderTitleBroadsheet(pptx, slide, slideData, preset);
  } else if (layout === 'light-atlas') {
    renderTitleLightAtlas(pptx, slide, slideData, preset);
  } else if (layout === 'telemetry-board') {
    renderTitleTelemetryBoard(pptx, slide, slideData, preset);
  } else {
    renderTitleSplit(pptx, slide, slideData, preset);
  }
}

// ---------------------------------------------------------------------------
// Section divider: full-bleed dark slide, oversized title, optional subtitle.
// ---------------------------------------------------------------------------

function renderRoleSection(slide, slideData, preset) {
  const sectionContract = roleContract(preset, slideData, 'section');
  if (sectionContract) {
    return renderContractStage(slide, slideData, preset, sectionContract, 'section');
  }
  const system = roleSystem(preset, slideData, 'section');
  if (!system) return false;
  const title = safeText(slideData.title, 'Section');
  const subtitle = safeText(slideData.subtitle);
  const accent = cleanHex(preset.accent_primary, '1493A4');
  const secondary = cleanHex(preset.accent_secondary, accent);
  const text = cleanHex(preset.text || preset.text_primary, '0F172A');
  const muted = cleanHex(preset.text_muted, '64748B');
  const dark = cleanHex(preset.bg_dark, '0B1220');
  const surface = cleanHex(preset.surface, 'FFFFFF');

  if (['answer-chapter', 'section-claim-chapters'].includes(system)) {
    paintBackground(slide, preset.bg || 'FFFFFF');
    addGrammarFrame(slide, preset, slideData);
    slide.addText(safeText(slideData.section_number, '01'), textOpts({
      x: 0.52, y: 1.34, w: 1.40, h: 0.72, fontFace: preset.font_heading,
      fontSize: 18, bold: true, color: accent, fit: 'shrink',
    }));
    slide.addShape('line', shapeOpts({ x: 2.14, y: 1.10, w: 0, h: 4.92, line: { color: preset.line || 'CBD5E1', width: 0.8 } }));
    slide.addText('GOVERNING QUESTION', textOpts({
      x: 2.54, y: 1.12, w: 2.42, h: 0.20, fontFace: preset.font_body,
      fontSize: 8, bold: true, color: muted, charSpacing: 1.1, fit: 'shrink',
    }));
    slide.addText(title, textOpts({
      x: 2.54, y: 1.62, w: 6.72, h: 1.54, fontFace: preset.font_heading,
      fontSize: 38, bold: true, color: text, fit: 'shrink',
    }));
    if (subtitle) {
      slide.addShape('rect', shapeOpts({
        x: 2.54, y: 4.18, w: 6.36, h: 1.00,
        fill: { color: surface }, line: { color: preset.line || 'CBD5E1', width: 0.7 },
      }));
      slide.addShape('rect', shapeOpts({ x: 2.54, y: 4.18, w: 0.08, h: 1.00, fill: { color: accent }, line: { color: accent, width: 0 } }));
      slide.addText(subtitle, textOpts({
        x: 2.82, y: 4.40, w: 5.74, h: 0.54, fontFace: preset.font_body,
        fontSize: 14, bold: true, color: text, fit: 'shrink',
      }));
    }
    attachNotes(slide, slideData);
    return true;
  }

  if (['method-tabs', 'section-method-result'].includes(system)) {
    paintBackground(slide, preset.bg || 'FFFFFF');
    addGrammarFrame(slide, preset, slideData);
    slide.addText(safeText(slideData.kicker, 'STUDY PHASE'), textOpts({
      x: 0.54, y: 0.72, w: 1.82, h: 0.18, fontFace: preset.font_body,
      fontSize: 7.5, bold: true, color: accent, charSpacing: 1.0, fit: 'shrink',
    }));
    slide.addText(title, textOpts({
      x: 0.54, y: 1.54, w: 8.36, h: 1.18, fontFace: preset.font_heading,
      fontSize: 34, bold: true, color: text, fit: 'shrink',
    }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 0.54, y: 2.94, w: 7.82, h: 0.62, fontFace: preset.font_body,
      fontSize: 14, color: muted, fit: 'shrink',
    }));
    ['DESIGN', 'CONTROL', 'READOUT', 'LIMIT'].forEach((label, idx) => {
      const x = 0.54 + idx * 2.18;
      slide.addShape('rect', shapeOpts({
        x, y: 4.54, w: 1.92, h: 0.62,
        fill: { color: idx === 2 ? accent : surface, transparency: idx === 2 ? 0 : 8 },
        line: { color: idx === 2 ? accent : preset.line || 'CBD5E1', width: 0.6 },
      }));
      slide.addText(label, textOpts({
        x: x + 0.12, y: 4.75, w: 1.68, h: 0.18, fontFace: preset.font_body,
        fontSize: 8, bold: true, color: idx === 2 ? 'FFFFFF' : muted, align: 'center', fit: 'shrink',
      }));
    });
    attachNotes(slide, slideData);
    return true;
  }

  if (['care-stage', 'section-care-stage'].includes(system)) {
    paintBackground(slide, preset.bg || 'FFFFFF');
    addGrammarFrame(slide, preset, slideData);
    slide.addText(safeText(slideData.kicker, 'CARE PATHWAY'), textOpts({
      x: 0.86, y: 0.82, w: 1.72, h: 0.18, fontFace: preset.font_body,
      fontSize: 7.5, bold: true, color: secondary, charSpacing: 1.0, fit: 'shrink',
    }));
    slide.addText(title, textOpts({
      x: 0.86, y: 1.50, w: 6.20, h: 1.34, fontFace: preset.font_heading,
      fontSize: 36, bold: true, color: text, fit: 'shrink',
    }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 0.86, y: 3.18, w: 5.92, h: 0.78, fontFace: preset.font_body,
      fontSize: 14, color: muted, fit: 'shrink',
    }));
    slide.addShape('rect', shapeOpts({
      x: 7.42, y: 1.30, w: 1.86, h: 3.58,
      fill: { color: surface }, line: { color: preset.line || 'CBD5E1', width: 0.65 },
    }));
    slide.addText('DECISION WINDOW', textOpts({
      x: 7.66, y: 1.62, w: 1.38, h: 0.22, fontFace: preset.font_body,
      fontSize: 7.2, bold: true, color: muted, align: 'center', fit: 'shrink',
    }));
    slide.addText(safeText(slideData.status, 'REVIEW'), textOpts({
      x: 7.66, y: 2.18, w: 1.38, h: 0.58, fontFace: preset.font_heading,
      fontSize: 22, bold: true, color: accent, align: 'center', fit: 'shrink',
    }));
    slide.addText('benefit  |  risk  |  owner', textOpts({
      x: 7.62, y: 3.46, w: 1.46, h: 0.48, fontFace: preset.font_body,
      fontSize: 8, color: muted, align: 'center', fit: 'shrink',
    }));
    attachNotes(slide, slideData);
    return true;
  }

  if (['article-spread', 'section-editorial-folio'].includes(system)) {
    paintBackground(slide, preset.bg || 'FFFFFF');
    addGrammarFrame(slide, preset, slideData);
    slide.addText(safeText(slideData.kicker, 'CHAPTER'), textOpts({
      x: 0.62, y: 0.72, w: 1.42, h: 0.18, fontFace: preset.font_body,
      fontSize: 7.4, bold: true, color: accent, charSpacing: 1.1, fit: 'shrink',
    }));
    slide.addText(title, textOpts({
      x: 0.62, y: 1.50, w: 5.82, h: 2.34, fontFace: preset.font_heading,
      fontSize: 44, bold: true, color: text, fit: 'shrink',
    }));
    slide.addShape('line', shapeOpts({ x: 6.84, y: 1.30, w: 0, h: 4.72, line: { color: preset.line || 'CBD5E1', width: 0.7 } }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 7.04, y: 1.58, w: 1.82, h: 2.18, fontFace: preset.font_body,
      fontSize: 14, color: muted, valign: 'top', fit: 'shrink',
    }));
    slide.addText('Scene, context, counterpoint, interpretation.', textOpts({
      x: 6.84, y: 4.48, w: 1.65, h: 0.54, fontFace: preset.font_body,
      fontSize: 9, italic: true, color: muted, fit: 'shrink',
    }));
    attachNotes(slide, slideData);
    return true;
  }

  if (['thesis-reset', 'section-thesis-stage'].includes(system)) {
    paintBackground(slide, dark);
    addGrammarFrame(slide, preset, slideData);
    slide.addShape('rect', shapeOpts({
      x: 7.62, y: 1.30, w: 1.62, h: 3.96,
      fill: { color: surface, transparency: 78 },
      line: { color: preset.line || '334155', width: 0.55 },
    }));
    [1.82, 2.72, 3.62, 4.52].forEach((y, idx) => {
      slide.addShape('rect', shapeOpts({
        x: 7.90, y, w: idx === 1 ? 1.02 : 0.72, h: 0.055,
        fill: { color: idx === 1 ? secondary : preset.line || '475569', transparency: idx === 1 ? 0 : 18 },
        line: { color: idx === 1 ? secondary : preset.line || '475569', width: 0 },
      }));
    });
    slide.addShape('rect', shapeOpts({
      x: 0.54, y: 5.14, w: 8.70, h: 0.36,
      fill: { color: surface, transparency: 84 },
      line: { color: preset.line || '334155', width: 0.45 },
    }));
    slide.addText(safeText(slideData.kicker, 'THESIS'), textOpts({
      x: 0.54, y: 0.72, w: 1.82, h: 0.20, fontFace: preset.font_body,
      fontSize: 8, bold: true, color: accent, charSpacing: 1.2, fit: 'shrink',
    }));
    slide.addText(title, textOpts({
      x: 0.54, y: 1.82, w: 6.62, h: 1.82, fontFace: preset.font_heading,
      fontSize: 46, bold: true, color: 'FFFFFF', fit: 'shrink',
    }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 0.54, y: 4.22, w: 6.70, h: 0.70, fontFace: preset.font_body,
      fontSize: 15, color: darkSlideSubtitleColor(preset), fit: 'shrink',
    }));
    attachNotes(slide, slideData);
    return true;
  }

  if (['workstream-band', 'section-operating-cycle'].includes(system)) {
    paintBackground(slide, dark);
    addGrammarFrame(slide, preset, slideData);
    ['STATE', 'VARIANCE', 'OWNER', 'DUE'].forEach((label, idx) => {
      slide.addText(label, textOpts({
        x: 0.56 + idx * 2.22, y: 0.66, w: 1.80, h: 0.18,
        fontFace: preset.font_body, fontSize: 7.2, bold: true,
        color: idx === 1 ? secondary : darkSlideSubtitleColor(preset), align: 'center', fit: 'shrink',
      }));
    });
    slide.addText(title, textOpts({
      x: 0.56, y: 2.12, w: 8.86, h: 1.18, fontFace: preset.font_heading,
      fontSize: 38, bold: true, color: 'FFFFFF', fit: 'shrink',
    }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 0.56, y: 3.58, w: 7.94, h: 0.62, fontFace: preset.font_body,
      fontSize: 14, color: darkSlideSubtitleColor(preset), fit: 'shrink',
    }));
    slide.addShape('rect', shapeOpts({
      x: 0.56, y: 4.72, w: 8.74, h: 0.62,
      fill: { color: surface, transparency: 82 }, line: { color: preset.line || '475569', width: 0.55 },
    }));
    attachNotes(slide, slideData);
    return true;
  }

  if (['docket-tab', 'section-policy-docket'].includes(system)) {
    paintBackground(slide, preset.bg || 'FFFFFF');
    addGrammarFrame(slide, preset, slideData);
    slide.addShape('rect', shapeOpts({
      x: 0.22, y: 1.04, w: 0.22, h: 0.08,
      fill: { color: 'FFFFFF' }, line: { color: 'FFFFFF', width: 0 },
    }));
    slide.addText(safeText(slideData.kicker, 'PUBLIC QUESTION'), textOpts({
      x: 0.84, y: 0.90, w: 2.14, h: 0.20, fontFace: preset.font_body,
      fontSize: 8, bold: true, color: accent, charSpacing: 1.0, fit: 'shrink',
    }));
    slide.addText(title, textOpts({
      x: 0.84, y: 1.58, w: 8.08, h: 1.42, fontFace: preset.font_heading,
      fontSize: 38, bold: true, color: text, fit: 'shrink',
    }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 0.84, y: 3.44, w: 7.14, h: 0.84, fontFace: preset.font_body,
      fontSize: 15, color: muted, fit: 'shrink',
    }));
    slide.addShape('rect', shapeOpts({
      x: 0.84, y: 4.86, w: 8.12, h: 0.54,
      fill: { color: surface }, line: { color: preset.line || 'CBD5E1', width: 0.65 },
    }));
    slide.addText('population  |  geography  |  evidence  |  options  |  accountability', textOpts({
      x: 1.20, y: 4.98, w: 7.40, h: 0.18, fontFace: preset.font_body,
      fontSize: 8.2, color: muted, align: 'center', fit: 'shrink',
    }));
    attachNotes(slide, slideData);
    return true;
  }

  if (['incident-mode', 'section-system-layer'].includes(system)) {
    paintBackground(slide, dark);
    addGrammarFrame(slide, preset, slideData);
    slide.addShape('rect', shapeOpts({
      x: 0.42, y: 1.16, w: 1.72, h: 4.48,
      fill: { color: surface, transparency: 6 }, line: { color: preset.line || '334155', width: 0.6 },
    }));
    slide.addText(safeText(slideData.kicker, 'INCIDENT MODE'), textOpts({
      x: 0.62, y: 1.46, w: 1.32, h: 0.20, fontFace: preset.font_body,
      fontSize: 7.2, bold: true, color: accent, align: 'center', fit: 'shrink',
    }));
    const statusText = safeText(slideData.status, 'DIAGNOSE');
    slide.addText(statusText, textOpts({
      x: 0.62, y: 2.10, w: 1.32, h: 0.68, fontFace: preset.font_heading,
      fontSize: statusText.length > 6 ? 14 : 22,
      bold: true, color: 'FFFFFF', align: 'center', fit: 'shrink',
    }));
    ['OBSERVE', 'DIAGNOSE', 'RESPOND', 'RECOVER'].forEach((label, idx) => {
      slide.addText(label, textOpts({
        x: 0.64, y: 3.20 + idx * 0.46, w: 1.28, h: 0.16,
        fontFace: preset.font_body, fontSize: 7, bold: idx === 1,
        color: idx === 1 ? secondary : darkSlideSubtitleColor(preset), align: 'center', fit: 'shrink',
      }));
    });
    slide.addText(title, textOpts({
      x: 2.58, y: 1.70, w: 6.64, h: 1.48, fontFace: preset.font_heading,
      fontSize: 38, bold: true, color: 'FFFFFF', fit: 'shrink',
    }));
    if (subtitle) slide.addText(subtitle, textOpts({
      x: 2.58, y: 3.60, w: 5.78, h: 0.72, fontFace: preset.font_body,
      fontSize: 14, color: darkSlideSubtitleColor(preset), fit: 'shrink',
    }));
    attachNotes(slide, slideData);
    return true;
  }

  return false;
}

function renderSection(pptx, slide, slideData, preset) {
  if (renderRoleSection(slide, slideData, preset)) return;
  const motif = String(slideData.structural_motif || preset.structural_motif || '').trim().toLowerCase();
  const title = safeText(slideData.title, 'Section');
  const subtitle = safeText(slideData.subtitle);
  const lightEditorial = new Set([
    'editorial-rule',
    'journal-folio',
    'case-margin',
    'field-notes',
    'open-coordinate',
  ]);
  const technicalStage = new Set(['workflow-brackets', 'signal-grid', 'incident-rail']);
  const investorStage = new Set(['proof-stage', 'thesis-window']);

  if (lightEditorial.has(motif)) {
    paintBackground(slide, preset.bg || 'FFFFFF');
    addPageSystemChrome(slide, preset, slideData);
    const textColor = cleanHex(preset.text || preset.text_primary, '0F172A');
    const muted = cleanHex(preset.text_muted, '64748B');
    const accent = cleanHex(preset.accent_primary, 'D4461E');
    addTitleKicker(slide, preset, slideData.kicker || 'SECTION', {
      x: MARGIN_X, y: 0.54, w: 2.4, h: 0.18, color: accent, fontSize: 8.2,
    });
    slide.addText(title, textOpts({
      x: MARGIN_X,
      y: 1.36,
      w: 6.08,
      h: 1.82,
      fontFace: preset.font_heading,
      fontSize: 42,
      bold: true,
      color: textColor,
      fit: 'shrink',
    }));
    slide.addShape('rect', shapeOpts({
      x: 7.08, y: 1.30, w: 0.018, h: 4.48,
      fill: { color: preset.line || 'E5E7EB' }, line: { color: preset.line || 'E5E7EB', width: 0 },
    }));
    slide.addShape('rect', shapeOpts({
      x: 7.045, y: 1.30, w: 0.088, h: 0.76,
      fill: { color: accent }, line: { color: accent, width: 0 },
    }));
    if (subtitle) {
      slide.addText(subtitle, textOpts({
        x: 7.42,
        y: 1.42,
        w: 2.08,
        h: 1.42,
        fontFace: preset.font_body,
        fontSize: 12.5,
        color: muted,
        fit: 'shrink',
      }));
    }
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X, y: 5.76, w: 6.12, h: 0.02,
      fill: { color: textColor }, line: { color: textColor, width: 0 },
    }));
    attachNotes(slide, slideData);
    return;
  }

  if (technicalStage.has(motif)) {
    paintBackground(slide, preset.bg_dark);
    addPageSystemChrome(slide, preset, slideData);
    addTitleKicker(slide, preset, slideData.kicker || 'SYSTEM PHASE', {
      x: MARGIN_X, y: 0.58, w: 2.8, h: 0.18, color: preset.accent_secondary, fontSize: 8.2,
    });
    slide.addText(title, textOpts({
      x: MARGIN_X, y: 1.38, w: 8.20, h: 1.48,
      fontFace: preset.font_heading, fontSize: 40, bold: true, color: 'FFFFFF', fit: 'shrink',
    }));
    if (subtitle) {
      slide.addText(subtitle, textOpts({
        x: MARGIN_X, y: 3.06, w: 7.40, h: 0.82,
        fontFace: preset.font_body, fontSize: 15, color: darkSlideSubtitleColor(preset), fit: 'shrink',
      }));
    }
    const stripW = 0.42;
    [0, 1, 2].forEach((idx) => {
      slide.addShape('rect', shapeOpts({
        x: 8.12 + idx * (stripW + 0.12), y: 4.76, w: stripW, h: 0.08,
        fill: { color: idx === 1 ? preset.accent_secondary : preset.accent_primary, transparency: idx === 1 ? 0 : 42 },
        line: { color: preset.accent_primary, transparency: 100, width: 0 },
      }));
    });
    attachNotes(slide, slideData);
    return;
  }

  if (investorStage.has(motif)) {
    paintBackground(slide, preset.bg_dark);
    addPageSystemChrome(slide, preset, slideData);
    addTitleKicker(slide, preset, slideData.kicker || 'THESIS TURN', {
      x: MARGIN_X, y: 0.64, w: 2.8, h: 0.18, color: preset.accent_primary, fontSize: 8.4,
    });
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X, y: 1.02, w: 1.12, h: 0.065,
      fill: { color: preset.accent_primary }, line: { color: preset.accent_primary, width: 0 },
    }));
    slide.addText(title, textOpts({
      x: MARGIN_X, y: 2.06, w: 9.10, h: 1.62,
      fontFace: preset.font_heading, fontSize: 44, bold: true, color: 'FFFFFF', fit: 'shrink',
    }));
    if (subtitle) {
      slide.addText(subtitle, textOpts({
        x: MARGIN_X, y: 4.02, w: 8.40, h: 0.78,
        fontFace: preset.font_body, fontSize: 15, color: darkSlideSubtitleColor(preset), fit: 'shrink',
      }));
    }
    attachNotes(slide, slideData);
    return;
  }

  paintBackground(slide, preset.bg_dark);
  addBackgroundImage(slide, slideData.background_image, preset);
  if (!motif) addSectionMotif(slide, preset);
  addPageSystemChrome(slide, preset, slideData);

  // Large accent block as divider motif.
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: 2.55,
    w: 1.2,
    h: 0.10,
    fill: { color: preset.accent_primary },
  }));

  slide.addText(title, textOpts({
    x: MARGIN_X,
    y: 1.40,
    w: SLIDE_W - MARGIN_X * 2,
    h: 1.10,
    fontFace: preset.font_heading,
    fontSize: 40,
    bold: true,
    color: 'FFFFFF',
  }));

  if (subtitle) {
    const subtitleH = Math.min(
      1.20,
      Math.max(0.45, estimateTextHeight(subtitle, 16, SLIDE_W - MARGIN_X * 2, 1.22) + 0.18),
    );
    slide.addText(subtitle, textOpts({
      x: MARGIN_X,
      y: 2.80,
      w: SLIDE_W - MARGIN_X * 2,
      h: subtitleH,
      fontFace: preset.font_body,
      fontSize: 16,
      color: cleanHex(preset.section_subtitle_color, 'E5E7EB'),
    }));
  }
  attachNotes(slide, slideData);
}

// ---------------------------------------------------------------------------
// Bullet helpers: shared by standard + split variants.
// ---------------------------------------------------------------------------

function normalizeBullets(items) {
  if (!Array.isArray(items)) return [];
  const out = [];
  for (const item of items) {
    if (item === null || item === undefined) continue;
    if (typeof item === 'string') {
      const t = item.trim();
      if (t) out.push({ text: t, level: 0 });
    } else if (typeof item === 'object') {
      const t = safeText(item.text);
      if (t) {
        let level = Number(item.level);
        if (!Number.isFinite(level) || level < 0) level = 0;
        if (level > 2) level = 2;
        out.push({ text: t, level });
      }
    }
  }
  return out;
}

function bulletTextArray(bullets, preset) {
  // pptxgenjs accepts an array of { text, options } for mixed bullet levels.
  // Two invariants from references/pptxgenjs.md:
  //   - `bullet: { code: '2022' }` (unicode bullet code) renders reliably
  //     in LibreOffice; `{ type: 'bullet' }` sometimes doesn't.
  //   - Every item except the last must carry `breakLine: true` or
  //     pptxgenjs concatenates them into a single paragraph.
  const n = bullets.length;
  return bullets.map((b, i) => ({
    text: b.text,
    options: {
      bullet: { code: '2022' },
      fontFace: preset.font_body,
      fontSize: b.level === 0 ? 16 : 14,
      color: b.level === 0 ? preset.text : preset.text_muted,
      paraSpaceAfter: 6,
      indentLevel: b.level,
      breakLine: i < n - 1,
    },
  }));
}

// ---------------------------------------------------------------------------
// Standard content: title + bullets column, optional pull-quote on right.
// ---------------------------------------------------------------------------

function renderStandard(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const decisionContract = roleContract(preset, slideData, 'decision');
  if (decisionContract) {
    const recipe = slideData.content_recipe && typeof slideData.content_recipe === 'object'
      ? slideData.content_recipe
      : {};
    const recipeSlots = Array.isArray(recipe.required_slots) ? recipe.required_slots : [];
    const rawBullets = (Array.isArray(slideData.bullets) ? slideData.bullets : [])
      .map((item) => safeText(item && typeof item === 'object' ? item.text : item))
      .filter(Boolean);
    const decisionBodies = [
      safeText(slideData.body),
      ...rawBullets,
      safeText((slideData.sources || [])[0] || (slideData.refs || [])[0]),
    ].filter(Boolean);
    const fallbackTitles = ['Decision', 'Evidence trigger', 'Owner', 'Timing / caveat'];
    const quadrants = fallbackTitles.map((fallbackTitle, index) => ({
      title: safeText(recipeSlots[index], fallbackTitle)
        .replace(/(^|[\s/_-])\w/g, (match) => match.toUpperCase()),
      body: decisionBodies[index] || decisionBodies[decisionBodies.length - 1] || 'Record before delivery.',
    }));
    const decisionSlideData = {
      ...slideData,
      summary_callout: safeText(
        slideData.summary_callout || slideData.takeaway || rawBullets[0] || slideData.body,
      ),
    };
    renderDecisionContract(
      slide,
      decisionSlideData,
      preset,
      header,
      decisionContract,
      quadrants,
    );
    slideData.__roleContractConsumesSummary = true;
    return;
  }
  const referencesContract = roleContract(preset, slideData, 'references');
  if (referencesContract) {
    const sourceItems = [
      ...(Array.isArray(slideData.bullets) ? slideData.bullets : []),
      ...(Array.isArray(slideData.sources) ? slideData.sources : []),
      ...(Array.isArray(slideData.refs) ? slideData.refs : []),
    ].map((item) => safeText(item)).filter(Boolean);
    const seen = new Set();
    const rows = sourceItems.filter((item) => {
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }).slice(0, 10).map((item, index) => {
      const match = item.match(/^([A-Za-z]\d+)\s*:\s*(.+)$/);
      return [
        match ? match[1] : `S${index + 1}`,
        match ? match[2] : item,
        safeText(slideData.body, 'Supporting evidence'),
      ];
    });
    if (rows.length) {
      renderTableContract(
        slide,
        slideData,
        preset,
        header,
        {
          title: safeText(slideData.title, 'Sources'),
          headers: ['ID', 'Source', 'Use'],
          rows,
          caption: safeText(slideData.body),
          footnotes: [],
          table_style: 'references',
        },
        true,
        referencesContract,
      );
      return;
    }
  }

  let bullets = normalizeBullets(slideData.bullets);
  const highlights = Array.isArray(slideData.highlights)
    ? slideData.highlights.map((h) => safeText(h)).filter(Boolean)
    : [];

  // Compatibility fallback: old outlines sometimes omitted `variant: matrix`
  // but still supplied quadrants. Preserve that content as bullets instead of
  // rendering an empty slide.
  if (bullets.length === 0
      && !safeText(slideData.body)
      && !(Array.isArray(slideData.paragraphs) && slideData.paragraphs.length)
      && Array.isArray(slideData.quadrants) && slideData.quadrants.length) {
    console.warn(
      '[pptxgenjs] quadrants supplied without variant: matrix; ' +
      'synthesizing bullets so content is preserved.',
    );
    bullets = slideData.quadrants.slice(0, 4).map((q) => {
      const title = safeText(q && q.title);
      const body = safeText(q && q.body);
      const text = title && body ? `${title}: ${body}` : (title || body);
      return text;
    }).filter(Boolean).map((t) => ({ text: t, level: 0 }));
  }

  const contentY = header.contentTop + 0.25;
  const hasBottomSummary = !!safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway);
  const summaryReserve = hasBottomSummary ? 0.66 : 0;
  const contentH = SLIDE_H - contentY - 0.55 - summaryReserve;

  const hasHighlights = highlights.length > 0;
  const leftW = hasHighlights ? 5.6 : SLIDE_W - MARGIN_X * 2;

  if (bullets.length) {
    // Mirror python renderer's "body + bullets" composition: if the
    // outline has both `body` (prose) AND bullets, render body as an
    // intro paragraph above the bullets. Matches _add_standard_content.
    const introText = safeText(slideData.body);
    let currentY = contentY;
    if (introText) {
      const introH = Math.min(1.0, Math.max(0.48, 0.20 + introText.length / 180));
      slide.addText(introText, textOpts({
        x: MARGIN_X,
        y: currentY,
        w: leftW,
        h: introH,
        fontFace: preset.font_body,
        fontSize: 16,
        color: preset.text,
        valign: 'top',
        paraSpaceAfter: 8,
      }));
      currentY += introH + 0.12;
    }
    const bulletText = bullets.map((b) => b.text).join('\n');
    const bulletH = Math.min(
      Math.max(0.5, contentH - (currentY - contentY)),
      Math.max(0.95, estimateTextHeight(bulletText, 16, leftW, 1.24) + 0.32),
    );
    slide.addText(bulletTextArray(bullets, preset), textOpts({
      x: MARGIN_X,
      y: currentY,
      w: leftW,
      h: bulletH,
      fontFace: preset.font_body,
      fontSize: 16,
      color: preset.text,
      valign: 'top',
      paraSpaceAfter: 6,
    }));
  } else {
    // Fall back to `paragraphs` (array of strings) or `body` (single string).
    // Schema lists both as Common Text Fields; without this, schema-valid
    // slides authored with only `body` would render empty below the title.
    let paragraphs = [];
    if (Array.isArray(slideData.paragraphs) && slideData.paragraphs.length) {
      paragraphs = slideData.paragraphs
        .map((p) => safeText(p))
        .filter(Boolean);
    } else {
      const body = safeText(slideData.body);
      if (body) paragraphs = [body];
    }
    if (paragraphs.length) {
      const items = paragraphs.map((p, i) => ({
        text: p,
        options: {
          fontFace: preset.font_body,
          fontSize: 16,
          color: preset.text,
          paraSpaceAfter: i < paragraphs.length - 1 ? 10 : 0,
          breakLine: i < paragraphs.length - 1,
        },
      }));
      const paragraphText = paragraphs.join('\n');
      const paragraphH = Math.min(
        contentH,
        Math.max(0.75, estimateTextHeight(paragraphText, 16, leftW, 1.24) + 0.25),
      );
      slide.addText(items, textOpts({
        x: MARGIN_X,
        y: contentY,
        w: leftW,
        h: paragraphH,
        fontFace: preset.font_body,
        fontSize: 16,
        color: preset.text,
        valign: 'top',
      }));
    }
  }

  if (hasHighlights) {
    const cardX = MARGIN_X + leftW + 0.2;
    const cardW = SLIDE_W - cardX - MARGIN_X;
    slide.addShape('roundRect', shapeOpts({
      x: cardX, y: contentY, w: cardW, h: contentH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.75 },
      rectRadius: 0.08,
      shadow: cardShadow(),
    }));
    slide.addText('Key takeaways', textOpts({
      x: cardX + 0.2, y: contentY + 0.15, w: cardW - 0.4, h: 0.3,
      fontFace: preset.font_heading,
      fontSize: 11,
      bold: true,
      color: preset.accent_primary,
    }));
    const hiItems = highlights.map((h) => ({
      text: h,
      options: {
        bullet: { type: 'bullet', indent: 12 },
        fontFace: preset.font_body,
        fontSize: 13,
        color: preset.text,
        paraSpaceAfter: 5,
      },
    }));
    slide.addText(hiItems, textOpts({
      x: cardX + 0.2,
      y: contentY + 0.56,
      w: cardW - 0.4,
      h: contentH - 0.71,
      fontFace: preset.font_body,
      fontSize: 13,
      color: preset.text,
      valign: 'top',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

// ---------------------------------------------------------------------------
// Cards grid: 2- or 3-column card layout.
// ---------------------------------------------------------------------------

function renderCards(pptx, slide, slideData, preset, columns) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const rawCards = Array.isArray(slideData.cards) ? slideData.cards : [];
  const evidenceContract = roleContract(preset, slideData, 'evidence');
  if (evidenceContract && rawCards.length) {
    const maxItems = Math.max(1, Number(evidenceContract.density && evidenceContract.density.max_items) || 4);
    if (rawCards.length > maxItems) {
      throw new Error(`Evidence layout supports at most ${maxItems} cards; split the source slide instead of dropping content.`);
    }
    const facts = normalizeFacts(rawCards.slice(0, maxItems).map((card, index) => ({
      value: safeText(card && (card.value ?? card.number)),
      label: safeText(card && card.title, `Evidence ${index + 1}`),
      caption: safeText(card && (card.body || card.text || card.caption)),
      source: safeText(card && card.source),
      accent: card && card.accent,
    })));
    renderEvidenceContract(slide, slideData, preset, header, evidenceContract, facts);
    return;
  }
  const cols = columns === 2 ? 2 : 3;
  const cards = rawCards.slice(0, cols);
  while (cards.length < cols) {
    cards.push({ title: '', body: '', accent: 'accent_primary' });
  }

  const gutter = 0.24;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const avgBodyLen = cards.reduce((sum, card) => sum + safeText(card.body || card.text).length, 0) /
    Math.max(1, cards.length);
  const compactCardRow = cols === 2 && avgBodyLen > 0 && avgBodyLen < 170;
  const cardY = header.contentTop + (compactCardRow ? 0.78 : 0.35);
  const maxCardH = SLIDE_H - cardY - 0.65;
  const cardH = compactCardRow ? Math.min(maxCardH, 2.30) : maxCardH;

  // cards_mode gives presets an anti-sameness lever without creating more
  // variants. feature-left promotes the first/selected card; staggered-row
  // keeps equal width but varies the vertical silhouette.
  const cardsMode = String(slideData.cards_mode || preset.cards_mode || '').trim().toLowerCase();
  const explicitPromote = Number.isInteger(slideData.promote_card) ? slideData.promote_card : null;
  const promote = explicitPromote !== null
    ? explicitPromote
    : (cols === 3 && cardsMode === 'feature-left' ? 0 : null);
  const useAsymmetric =
    cols === 3 &&
    Number.isInteger(promote) &&
    promote >= 0 &&
    promote < cards.length;

  // Per-card positions: each entry is {x, y, w, h, accentKey, maxLines}
  let placements;
  if (useAsymmetric) {
    const leftW = usableW * 0.60 - gutter / 2;
    const rightW = usableW - leftW - gutter;
    const smallH = (cardH - gutter) / 2;
    const others = [0, 1, 2].filter((i) => i !== promote);
    placements = [null, null, null];
    placements[promote] = { x: MARGIN_X, y: cardY, w: leftW, h: cardH, big: true };
    placements[others[0]] = {
      x: MARGIN_X + leftW + gutter, y: cardY, w: rightW, h: smallH, big: false,
    };
    placements[others[1]] = {
      x: MARGIN_X + leftW + gutter, y: cardY + smallH + gutter, w: rightW, h: smallH, big: false,
    };
  } else if (cols === 3 && cardsMode === 'staggered-row') {
    const cardW = (usableW - gutter * (cols - 1)) / cols;
    const offsets = [0.00, 0.18, 0.36];
    placements = cards.map((_, idx) => ({
      x: MARGIN_X + idx * (cardW + gutter),
      y: cardY + offsets[idx],
      w: cardW,
      h: Math.max(1.4, cardH - offsets[idx]),
      big: false,
    }));
  } else {
    const cardW = (usableW - gutter * (cols - 1)) / cols;
    placements = cards.map((_, idx) => ({
      x: MARGIN_X + idx * (cardW + gutter),
      y: cardY,
      w: cardW,
      h: cardH,
      big: false,
    }));
  }

  const iconPaths = Array.isArray(slideData.__iconPaths) ? slideData.__iconPaths : [];

  cards.forEach((card, idx) => {
    const pos = placements[idx];
    const cx = pos.x;
    const cy = pos.y;
    const cw = pos.w;
    const ch = pos.h;
    const accentKey = card.accent === 'accent_secondary' ? 'accent_secondary' : 'accent_primary';
    const accentColor = preset[accentKey] || preset.accent_primary;
    const padX = 0.25;

    // Card surface. Use a square body so the top accent rail sits flush.
    slide.addShape('rect', shapeOpts({
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.75 },
      shadow: cardShadow(),
    }));
    // Top accent rail.
    slide.addShape('rect', shapeOpts({
      x: cx, y: cy, w: cw, h: 0.10,
      fill: { color: accentColor },
    }));

    // Optional icon above card title. Icons are pre-resolved to PNG paths by
    // the build script (react-icons slugs like 'fa6:FaLightbulb' get
    // rasterized; bare filenames resolve against the outline dir).
    const iconPath = iconPaths[idx];
    const iconSize = pos.big ? 0.52 : 0.34;
    const hasIcon = iconPath && fs.existsSync(iconPath);
    let titleX = cx + padX;
    let titleY = cy + 0.28;
    let titleW = cw - padX * 2;
    let bodyY = cy + 0.92;
    const compactStackCard = useAsymmetric && !pos.big;
    if (compactStackCard) {
      titleY = cy + 0.18;
      bodyY = cy + 0.64;
    }
    if (hasIcon && pos.big) {
      slide.addImage({
        path: iconPath,
        x: cx + (cw - iconSize) / 2,
        y: cy + 0.22,
        w: iconSize,
        h: iconSize,
      });
      titleY = cy + 0.84;
      bodyY = cy + 1.48;
    } else if (hasIcon) {
      slide.addImage({
        path: iconPath,
        x: cx + 0.20,
        y: cy + 0.23,
        w: iconSize,
        h: iconSize,
      });
      titleX = cx + 0.62;
      titleY = cy + 0.20;
      titleW = cw - 0.82;
      bodyY = cy + 0.72;
    }

    slide.addText(safeText(card.title, ''), textOpts({
      x: titleX,
      y: titleY,
      w: titleW,
      h: pos.big ? 0.55 : (compactStackCard ? 0.34 : 0.42),
      fontFace: preset.font_heading,
      fontSize: pos.big ? 22 : (compactStackCard ? 12.4 : 13.5),
      bold: true,
      color: preset.text,
      fit: 'shrink',
    }));
    const bodyText = safeText(card.body, '');
    const bodyBoxMaxH = Math.max(0.38, ch - (bodyY - cy) - 0.22);
    const bodyFontSize = pos.big ? 14 : (compactStackCard ? 9.4 : 10.6);
    const estimatedBodyH = estimateTextHeight(bodyText, bodyFontSize, cw - padX * 2, 1.20);
    const bodyBoxH = Math.min(
      bodyBoxMaxH,
      Math.max(compactStackCard ? 0.46 : 0.55, estimatedBodyH + 0.18),
    );
    slide.addText(bodyText, textOpts({
      x: cx + padX,
      y: bodyY,
      w: cw - padX * 2,
      h: bodyBoxH,
      fontFace: preset.font_body,
      fontSize: bodyFontSize,
      color: preset.text_muted,
      valign: 'top',
      paraSpaceAfter: 4,
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

// ---------------------------------------------------------------------------
// Split layout: bullets on the left, highlight panel on the right.
// ---------------------------------------------------------------------------

function renderSplit(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const contentY = header.contentTop + 0.30;
  const contentH = SLIDE_H - contentY - 0.60;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const leftW = usableW * 0.58;
  const gutter = 0.25;
  const rightW = usableW - leftW - gutter;
  const rightX = MARGIN_X + leftW + gutter;

  const bullets = normalizeBullets(slideData.bullets);
  if (bullets.length) {
    slide.addText(bulletTextArray(bullets, preset), textOpts({
      x: MARGIN_X,
      y: contentY,
      w: leftW,
      h: contentH,
      fontFace: preset.font_body,
      fontSize: 16,
      color: preset.text,
      valign: 'top',
      paraSpaceAfter: 6,
    }));
  }

  // Right panel -- dark card with highlights or subtitle-style text.
  // The accent stripe needs a square body to align cleanly at the edge.
  slide.addShape('rect', shapeOpts({
    x: rightX, y: contentY, w: rightW, h: contentH,
    fill: { color: preset.bg_dark },
    line: { color: preset.bg_dark, width: 0 },
    shadow: cardShadow(),
  }));
  // Accent stripe on the right panel.
  slide.addShape('rect', shapeOpts({
    x: rightX, y: contentY, w: 0.10, h: contentH,
    fill: { color: preset.accent_primary },
  }));

  const highlights = Array.isArray(slideData.highlights)
    ? slideData.highlights.map((h) => safeText(h)).filter(Boolean)
    : [];
  const label = safeText(slideData.highlights_label, 'Focus');
  slide.addText(label.toUpperCase(), textOpts({
    x: rightX + 0.3,
    y: contentY + 0.25,
    w: rightW - 0.5,
    h: 0.30,
    fontFace: preset.font_heading,
    fontSize: 11,
    bold: true,
    color: preset.accent_primary,
    charSpacing: 2,
  }));

  if (highlights.length) {
    const n = Math.min(highlights.length, 5);
    const items = highlights.slice(0, n).map((h, i) => ({
      text: h,
      options: {
        bullet: { code: '2022' },
        fontFace: preset.font_body,
        fontSize: 14,
        color: 'FFFFFF',
        paraSpaceAfter: 6,
        breakLine: i < n - 1,
      },
    }));
    const highlightText = highlights.slice(0, n).join('\n');
    const highlightH = Math.min(
      contentH - 0.98,
      Math.max(0.75, estimateTextHeight(highlightText, 14, rightW - 0.5, 1.22) + 0.25),
    );
    slide.addText(items, textOpts({
      x: rightX + 0.3,
      y: contentY + 0.78,
      w: rightW - 0.5,
      h: highlightH,
      fontFace: preset.font_body,
      fontSize: 14,
      color: 'FFFFFF',
      valign: 'top',
    }));
  } else {
    // Fall back to subtitle / footer as the right-panel narrative.
    const narrative = safeText(slideData.subtitle) || safeText(slideData.footer);
    if (narrative) {
      const narrativeH = Math.min(
        contentH - 0.98,
        Math.max(0.75, estimateTextHeight(narrative, 14, rightW - 0.5, 1.22) + 0.25),
      );
      slide.addText(narrative, textOpts({
        x: rightX + 0.3,
        y: contentY + 0.78,
        w: rightW - 0.5,
        h: narrativeH,
        fontFace: preset.font_body,
        fontSize: 14,
        color: 'FFFFFF',
        valign: 'top',
      }));
    }
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

// ---------------------------------------------------------------------------
// Timeline: milestone sequence renderers. Prefer non-card modes when a rail
// would make the slide feel templated.
// ---------------------------------------------------------------------------

function normalizeTimelineItems(slideData) {
  const defaults = [
    { label: 'Q1', title: 'Discover', body: 'Define baseline' },
    { label: 'Q2', title: 'Build', body: 'Pilot delivery' },
    { label: 'Q3', title: 'Scale', body: 'Expand coverage' },
    { label: 'Q4', title: 'Optimize', body: 'Harden operations' },
  ];
  return Array.isArray(slideData.milestones) && slideData.milestones.length
    ? slideData.milestones.slice(0, 5)
    : defaults;
}

function renderTimelineOpenEvents(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const rawItems = normalizeTimelineItems(slideData);
  const count = rawItems.length;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.18;
  const eventW = Math.max(1.24, (usableW - gutter * (count - 1)) / count);
  const totalW = eventW * count + gutter * (count - 1);
  const startX = MARGIN_X + (usableW - totalW) / 2;
  const railY = header.contentTop + 0.86;
  const accent = cleanHex(preset.accent_primary, '8B4513');
  const secondary = cleanHex(preset.accent_secondary, accent);

  slide.addShape('rect', shapeOpts({
    x: startX,
    y: railY,
    w: totalW,
    h: 0.025,
    fill: { color: preset.line || 'D9CBA8' },
    line: { color: preset.line || 'D9CBA8', width: 0 },
  }));

  rawItems.forEach((item, idx) => {
    const x = startX + idx * (eventW + gutter);
    const cx = x + eventW / 2;
    const color = idx % 2 ? secondary : accent;
    slide.addShape('line', shapeOpts({
      x: cx,
      y: railY - 0.38,
      w: 0,
      h: 2.70,
      line: { color: preset.line || 'D9CBA8', transparency: 12, width: 0.6 },
    }));
    slide.addShape('ellipse', shapeOpts({
      x: cx - 0.09,
      y: railY - 0.09,
      w: 0.18,
      h: 0.18,
      fill: { color },
      line: { color: preset.bg || 'FAF6EC', width: 1.1 },
    }));
    slide.addText(safeText(item.label, `Phase ${idx + 1}`).toUpperCase(), textOpts({
      x,
      y: railY - 0.58,
      w: eventW,
      h: 0.20,
      fontFace: preset.font_heading,
      fontSize: 8.2,
      bold: true,
      color,
      align: 'center',
      charSpacing: 1.1,
    }));
    slide.addText(safeText(item.title, item.label || `Step ${idx + 1}`), textOpts({
      x,
      y: railY + 0.32,
      w: eventW,
      h: 0.42,
      fontFace: preset.font_heading,
      fontSize: count >= 5 ? 10.4 : 11.2,
      bold: true,
      color: preset.text || preset.text_primary,
      align: 'center',
      fit: 'shrink',
    }));
    const bodyText = safeText(item.body || item.text, '');
    slide.addText(bodyText, textOpts({
      x,
      y: railY + 0.82,
      w: eventW,
      h: 0.72,
      fontFace: preset.font_body,
      fontSize: count >= 5 ? 7.6 : 8.4,
      color: preset.text_muted,
      align: 'center',
      valign: 'top',
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderTimelineStaggered(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const rawItems = normalizeTimelineItems(slideData);
  const count = rawItems.length;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.18;
  const cardW = Math.max(1.34, (usableW - gutter * (count - 1)) / count);
  const totalW = cardW * count + gutter * (count - 1);
  const startX = MARGIN_X + (usableW - totalW) / 2;
  const railY = Math.min(2.90, header.contentTop + 1.88);
  const topCardY = header.contentTop + 0.18;
  const topCardH = Math.max(1.18, railY - topCardY - 0.34);
  const bottomCardY = railY + 0.36;
  const bottomCardH = Math.max(1.00, SLIDE_H - bottomCardY - 0.72);
  const iconPaths = Array.isArray(slideData.__iconPaths) ? slideData.__iconPaths : [];

  slide.addShape('rect', shapeOpts({
    x: startX,
    y: railY - 0.025,
    w: totalW,
    h: 0.05,
    fill: { color: preset.line || 'CBD5E1' },
    line: { color: preset.line || 'CBD5E1', width: 0 },
  }));

  rawItems.forEach((item, idx) => {
    const x = startX + idx * (cardW + gutter);
    const above = idx % 2 === 0;
    const y = above ? topCardY : bottomCardY;
    const h = above ? topCardH : bottomCardH;
    const cx = x + cardW / 2;
    const accentKey = idx % 2 === 0 ? 'accent_primary' : 'accent_secondary';
    const accentColor = preset[accentKey] || preset.accent_primary;
    const connectorY = above ? y + h : railY;
    const connectorH = above ? railY - (y + h) : y - railY;

    slide.addShape('line', shapeOpts({
      x: cx,
      y: connectorY,
      w: 0,
      h: connectorH,
      line: { color: accentColor, transparency: 32, width: 1.0 },
    }));
    slide.addShape('ellipse', shapeOpts({
      x: cx - 0.12,
      y: railY - 0.12,
      w: 0.24,
      h: 0.24,
      fill: { color: accentColor },
      line: { color: preset.bg, width: 1.2 },
    }));

    slide.addShape('rect', shapeOpts({
      x,
      y,
      w: cardW,
      h,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.75 },
      shadow: cardShadow(),
    }));
    slide.addShape('rect', shapeOpts({
      x,
      y,
      w: 0.08,
      h,
      fill: { color: accentColor },
      line: { color: accentColor, width: 0 },
    }));

    const iconPath = iconPaths[idx];
    const hasIcon = iconPath && fs.existsSync(iconPath);
    if (hasIcon) {
      slide.addImage({ path: iconPath, x: x + cardW - 0.34, y: y + 0.12, w: 0.22, h: 0.22 });
    }

    slide.addText(safeText(item.label, `Phase ${idx + 1}`).toUpperCase(), textOpts({
      x: x + 0.18,
      y: y + 0.12,
      w: cardW - 0.36,
      h: 0.16,
      fontFace: preset.font_heading,
      fontSize: 7.4,
      bold: true,
      color: accentColor,
      charSpacing: 1.2,
    }));
    slide.addText(safeText(item.title, item.label || `Step ${idx + 1}`), textOpts({
      x: x + 0.18,
      y: y + 0.36,
      w: cardW - 0.36,
      h: above ? 0.34 : 0.42,
      fontFace: preset.font_heading,
      fontSize: count >= 5 ? 10.0 : 10.8,
      bold: true,
      color: preset.text,
      fit: 'shrink',
    }));
    slide.addText(safeText(item.body || item.text, ''), textOpts({
      x: x + 0.18,
      y: y + (above ? 0.84 : 0.92),
      w: cardW - 0.36,
      h: Math.max(above ? 0.46 : 0.34, h - (above ? 0.96 : 1.06)),
      fontFace: preset.font_body,
      fontSize: above ? 7.2 : 8.0,
      color: preset.text_muted,
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderTimelineBands(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const items = normalizeTimelineItems(slideData).slice(0, 5);
  const contentY = header.contentTop + 0.34;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const rowGap = 0.16;
  const rowH = Math.min(
    0.70,
    (SLIDE_H - contentY - 0.72 - rowGap * (items.length - 1)) / Math.max(1, items.length),
  );
  const accent = cleanHex(preset.accent_primary, '0EA5E9');
  const secondary = cleanHex(preset.accent_secondary, accent);

  items.forEach((item, idx) => {
    const y = contentY + idx * (rowH + rowGap);
    const color = idx % 2 ? secondary : accent;
    const fillColor = idx % 2 ? (preset.surface || 'FFFFFF') : (preset.bg || 'F8FAFC');
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: usableW,
      h: rowH,
      fill: { color: fillColor },
      line: { color: preset.line || 'E2E8F0', width: 0.75 },
    }));
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: 0.08,
      h: rowH,
      fill: { color },
      line: { color, width: 0 },
    }));
    slide.addText(safeText(item.label, `Step ${idx + 1}`).toUpperCase(), textOpts({
      x: MARGIN_X + 0.22,
      y: y + 0.16,
      w: 1.05,
      h: 0.20,
      fontFace: preset.font_heading,
      fontSize: 8.0,
      bold: true,
      color,
      charSpacing: 1.0,
      fit: 'shrink',
    }));
    slide.addText(safeText(item.title, item.label || `Step ${idx + 1}`), textOpts({
      x: MARGIN_X + 1.42,
      y: y + 0.10,
      w: 2.20,
      h: 0.28,
      fontFace: preset.font_heading,
      fontSize: 11.4,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
    slide.addText(safeText(item.body || item.text, ''), textOpts({
      x: MARGIN_X + 3.82,
      y: y + 0.12,
      w: usableW - 3.98,
      h: Math.max(0.26, rowH - 0.22),
      fontFace: preset.font_body,
      fontSize: 8.8,
      color: preset.text_muted,
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderTimelineChapterSpread(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const items = normalizeTimelineItems(slideData).slice(0, 4);
  const contentY = header.contentTop + 0.34;
  const contentH = SLIDE_H - contentY - 0.70;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const leftW = Math.min(3.25, usableW * 0.38);
  const rightX = MARGIN_X + leftW + 0.44;
  const rightW = usableW - leftW - 0.44;
  const focus = items[0] || { label: '01', title: 'Start', body: '' };
  const accent = cleanHex(preset.accent_primary, 'FF6B35');
  const secondary = cleanHex(preset.accent_secondary, accent);

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: contentY,
    w: leftW,
    h: contentH,
    fill: { color: preset.bg_dark || '0F172A' },
    line: { color: preset.bg_dark || '0F172A', width: 0 },
    shadow: cardShadow(),
  }));
  slide.addText('01', textOpts({
    x: MARGIN_X + 0.22,
    y: contentY + 0.08,
    w: leftW - 0.44,
    h: 0.68,
    fontFace: preset.font_heading,
    fontSize: 34,
    bold: true,
    color: accent,
    transparency: 14,
  }));
  slide.addText(safeText(focus.label, 'Start').toUpperCase(), textOpts({
    x: MARGIN_X + 0.28,
    y: contentY + 1.00,
    w: leftW - 0.56,
    h: 0.20,
    fontFace: preset.font_heading,
    fontSize: 8.2,
    bold: true,
    color: secondary,
    charSpacing: 1.3,
    fit: 'shrink',
  }));
  slide.addText(safeText(focus.title, focus.label || 'Milestone'), textOpts({
    x: MARGIN_X + 0.28,
    y: contentY + 1.38,
    w: leftW - 0.56,
    h: 0.62,
    fontFace: preset.font_heading,
    fontSize: 20,
    bold: true,
    color: 'FFFFFF',
    fit: 'shrink',
  }));
  const focusBody = safeText(focus.body || focus.text, '');
  const focusBodyH = Math.min(
    Math.max(0.48, estimateTextHeight(focusBody, 10.2, leftW - 0.56, 1.20) + 0.18),
    Math.max(0.48, contentH - 2.48),
  );
  slide.addText(focusBody, textOpts({
    x: MARGIN_X + 0.28,
    y: contentY + 2.20,
    w: leftW - 0.56,
    h: focusBodyH,
    fontFace: preset.font_body,
    fontSize: 10.2,
    color: 'CBD5E1',
    fit: 'shrink',
  }));
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: contentY + contentH - 0.10,
    w: leftW,
    h: 0.10,
    fill: { color: secondary },
    line: { color: secondary, width: 0 },
  }));

  const rest = items.slice(1);
  const rowGap = 0.22;
  const rowH = (contentH - rowGap * Math.max(0, rest.length - 1)) / Math.max(1, rest.length);
  rest.forEach((item, idx) => {
    const y = contentY + idx * (rowH + rowGap);
    const number = String(idx + 2).padStart(2, '0');
    const color = idx % 2 ? secondary : accent;
    const compactRow = rowH < 0.96;
    const titleY = y + (compactRow ? 0.30 : 0.38);
    const titleH = compactRow ? 0.24 : 0.30;
    const bodyY = y + (compactRow ? 0.60 : 0.82);
    const bodyH = compactRow
      ? Math.max(0.18, rowH - 0.64)
      : Math.max(0.35, rowH - 0.92);
    slide.addShape('line', shapeOpts({
      x: rightX,
      y: y + rowH - 0.02,
      w: rightW,
      h: 0,
      line: { color: preset.line || 'E2E8F0', width: 0.85 },
    }));
    slide.addText(number, textOpts({
      x: rightX,
      y: y + 0.04,
      w: 0.62,
      h: 0.36,
      fontFace: preset.font_heading,
      fontSize: 18,
      bold: true,
      color,
      fit: 'shrink',
    }));
    slide.addText(safeText(item.label, `Step ${idx + 2}`).toUpperCase(), textOpts({
      x: rightX + 0.82,
      y: y + 0.10,
      w: rightW - 0.82,
      h: 0.16,
      fontFace: preset.font_heading,
      fontSize: 7.4,
      bold: true,
      color,
      charSpacing: 1.0,
      fit: 'shrink',
    }));
    slide.addText(safeText(item.title, item.label || `Milestone ${idx + 2}`), textOpts({
      x: rightX + 0.82,
      y: titleY,
      w: rightW - 0.82,
      h: titleH,
      fontFace: preset.font_heading,
      fontSize: compactRow ? 10.8 : 12.2,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
    slide.addText(safeText(item.body || item.text, ''), textOpts({
      x: rightX + 0.82,
      y: bodyY,
      w: rightW - 0.82,
      h: bodyH,
      fontFace: preset.font_body,
      fontSize: compactRow ? 7.8 : 8.7,
      color: preset.text_muted,
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderReadableTimelineContract(slide, slideData, preset, header, contract, items) {
  const body = roleBodyBox(header, slideData, preset, { summaryReserve: 0.76 });
  const rows = items.slice(0, 5);
  const rowGap = 0.10;
  const rowH = (body.h - rowGap * Math.max(0, rows.length - 1)) / Math.max(1, rows.length);
  const labelW = Math.min(1.34, body.w * 0.13);
  const titleW = Math.min(2.40, body.w * 0.23);
  const bodyX = body.x + labelW + titleW + 0.38;
  const bodyW = Math.max(1.8, body.x + body.w - bodyX - 0.18);
  const metadataFont = roleMetadataFont(preset, 9.0);
  const bodyFont = roleBodyFont(preset, 16.0);
  const accent = cleanHex(preset.accent_primary, '1493A4');
  const secondary = cleanHex(preset.accent_secondary, accent);

  rows.forEach((item, index) => {
    const y = body.y + index * (rowH + rowGap);
    const color = index % 2 ? secondary : accent;
    const label = safeText(item.label || item.date, `Step ${index + 1}`).toUpperCase();
    const labelH = Math.min(
      rowH - 0.16,
      Math.max(0.28, estimateTextHeight(label, metadataFont, labelW - 0.20, 1.18) + 0.14),
    );
    slide.addShape('line', shapeOpts({
      x: body.x,
      y: y + rowH,
      w: body.w,
      h: 0,
      line: { color: preset.line || 'CBD5E1', width: 0.7 },
      objectName: `role-contract-slot:evidence:timeline-${index}`,
    }));
    slide.addShape('ellipse', shapeOpts({
      x: body.x,
      y: y + Math.max(0.06, (rowH - 0.18) / 2),
      w: 0.18,
      h: 0.18,
      fill: { color },
      line: { color: preset.bg || 'FFFFFF', width: 0.8 },
      objectName: `decorative:timeline-marker:${index}`,
    }));
    slide.addText(label, textOpts({
      x: body.x + 0.30,
      y: y + (rowH - labelH) / 2,
      w: labelW - 0.20,
      h: labelH,
      fontFace: preset.font_heading,
      fontSize: metadataFont,
      bold: true,
      color,
      valign: 'middle',
      fit: 'shrink',
      objectName: `metadata:timeline-label-${index}`,
    }));
    slide.addText(safeText(item.title || item.name, `Milestone ${index + 1}`), textOpts({
      x: body.x + labelW + 0.18,
      y: y + 0.06,
      w: titleW - 0.16,
      h: Math.max(0.28, rowH - 0.12),
      fontFace: preset.font_heading,
      fontSize: bodyFont,
      bold: true,
      color: preset.text || preset.text_primary,
      valign: 'middle',
      fit: 'shrink',
    }));
    slide.addText(safeText(item.body || item.text || item.caption), textOpts({
      x: bodyX,
      y: y + 0.06,
      w: bodyW,
      h: Math.max(0.28, rowH - 0.12),
      fontFace: preset.font_body,
      fontSize: bodyFont,
      color: preset.text_muted,
      valign: 'middle',
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'evidence',
    rows.map((_item, index) => `timeline_${index}`),
  );
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'readable-timeline-rows';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderTimelineComposition(slide, slideData, preset, header, contract, items) {
  const grammar = safeText(contract.composition_grammar_id || preset.composition_grammar);
  const defaultMode = /editorial|investor/.test(grammar) ? 'chapter-spread'
    : /scientific|operational|policy/.test(grammar) ? 'bands' : 'rail';
  const requested = safeText(slideData.timeline_mode || preset.timeline_mode).toLowerCase();
  const mode = ['bands', 'report-bands'].includes(requested) ? 'bands'
    : requested === 'chapter-spread' ? 'chapter-spread'
      : ['rail', 'rail-cards'].includes(requested) ? 'rail' : defaultMode;
  if (mode === 'bands') {
    return renderReadableTimelineContract(slide, slideData, preset, header, contract, items);
  }
  const rows = items.slice(0, 5);
  if (!rows.length) return false;
  const body = roleBodyBox(header, slideData, preset, { summaryReserve: 0.76 });
  const bodyFont = roleBodyFont(preset, 16);
  const labelFont = roleMetadataFont(preset, 10);
  const accent = cleanHex(preset.accent_primary, '1493A4');
  const ink = firstReadableColor(preset.bg, [preset.text, preset.text_primary, '171717', 'FFFFFF']);
  const muted = firstReadableColor(preset.bg, [preset.text_muted, ink], 4.5);
  const addText = (text, box, options = {}) => slide.addText(safeText(text), textOpts({
    ...box, fontFace: preset.font_body, fontSize: bodyFont, color: ink,
    fit: 'shrink', ...options,
  }));
  const addRule = (x, y, w, color = preset.line) => slide.addShape('line', shapeOpts({
    x, y, w, h: 0, line: { color: cleanHex(color, 'CBD5E1'), width: 0.8 },
  }));
  if (mode === 'rail' || rows.length === 1) {
    const gap = 0.24;
    const width = (body.w - gap * (rows.length - 1)) / rows.length;
    const railY = body.y + 0.62;
    addRule(body.x + 0.09, railY, body.w - width + 0.01, accent);
    rows.forEach((item, index) => {
      const x = body.x + index * (width + gap);
      const color = firstReadableColor(preset.bg, [index % 2 ? preset.accent_secondary : accent, ink]);
      addText(item.label || item.date || String(index + 1).padStart(2, '0'), {
        x, y: body.y + 0.05, w: width, h: 0.40,
      }, { fontSize: labelFont, color, bold: true, objectName: `metadata:timeline-label-${index}` });
      slide.addShape('ellipse', shapeOpts({
        x, y: railY - 0.08, w: 0.16, h: 0.16,
        fill: { color }, line: { color, width: 0 },
        objectName: `role-contract-slot:evidence:timeline-${index}`,
      }));
      const title = safeText(item.title || item.name);
      const titleH = Math.max(0.48, estimateTextHeight(title, bodyFont, width, 1.18) + 0.12);
      const titleY = railY + 0.26;
      addText(title, { x, y: titleY, w: width, h: titleH }, { bold: true, fontFace: preset.font_heading });
      const detailY = titleY + titleH + 0.16;
      addText(item.body || item.text || item.caption, {
        x, y: detailY, w: width, h: Math.max(0.32, body.y + body.h - detailY - 0.08),
      }, { color: muted });
    });
  } else {
    const focusW = body.w * 0.32;
    const gap = 0.42;
    const focus = rows[0];
    const dark = cleanHex(preset.bg_dark, '171717');
    const focusInk = firstReadableColor(dark, ['FFFFFF', '171717']);
    slide.addShape('rect', shapeOpts({
      x: body.x, y: body.y, w: focusW, h: body.h,
      fill: { color: dark }, line: { color: dark, width: 0 },
      objectName: 'role-contract-slot:evidence:timeline-0',
    }));
    const x = body.x + 0.26;
    const width = focusW - 0.52;
    addText(focus.label || focus.date || '01', {
      x, y: body.y + 0.28, w: width, h: 0.46,
    }, { fontSize: labelFont, bold: true, color: focusInk, objectName: 'metadata:timeline-label-0' });
    const titleFont = Math.max(bodyFont, 22);
    const titleH = Math.max(0.60, estimateTextHeight(safeText(focus.title), titleFont, width, 1.18) + 0.12);
    addText(focus.title || focus.name, {
      x, y: body.y + 0.92, w: width, h: titleH,
    }, { fontSize: titleFont, color: focusInk, bold: true, fontFace: preset.font_heading });
    const detailY = body.y + 0.92 + titleH + 0.24;
    addText(focus.body || focus.text || focus.caption, {
      x, y: detailY, w: width, h: Math.max(0.38, body.y + body.h - detailY - 0.24),
    }, { color: focusInk });
    const rest = rows.slice(1);
    const rowH = body.h / rest.length;
    const rightX = body.x + focusW + gap;
    const rightW = body.w - focusW - gap;
    rest.forEach((item, index) => {
      const y = body.y + index * rowH;
      const labelW = Math.min(1.08, rightW * 0.22);
      const textX = rightX + labelW + 0.15;
      const textW = rightW - labelW - 0.15;
      addRule(rightX, y + rowH - 0.02, rightW);
      addText(item.label || item.date || String(index + 2).padStart(2, '0'), {
        x: rightX, y: y + 0.12, w: labelW, h: Math.min(0.48, rowH - 0.22),
      }, { fontSize: labelFont, color: muted, bold: true, objectName: `metadata:timeline-label-${index + 1}` });
      const titleH = Math.max(0.30, estimateTextHeight(safeText(item.title), bodyFont, textW, 1.12) + 0.08);
      addText(item.title || item.name, { x: textX, y: y + 0.08, w: textW, h: titleH }, {
        bold: true, objectName: `role-contract-slot:evidence:timeline-${index + 1}`,
      });
      addText(item.body || item.text || item.caption, {
        x: textX, y: y + 0.08 + titleH + 0.08, w: textW,
        h: Math.max(0.30, rowH - titleH - 0.28),
      }, { color: muted });
    });
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, 'evidence', rows.map((_item, index) => `timeline_${index}`));
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = `readable-timeline-${mode}`;
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderTimeline(pptx, slide, slideData, preset) {
  const evidenceContract = roleContract(preset, slideData, 'evidence');
  if (evidenceContract) {
    if (Array.isArray(slideData.milestones) && slideData.milestones.length > 5) {
      throw new Error('Timeline supports at most five milestones; split the source slide instead of dropping steps.');
    }
    paintBackground(slide, preset.bg);
    const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
    const timelineItems = normalizeTimelineItems(slideData);
    const minBody = Number(
      preset && preset.readability_contract && preset.readability_contract.min_body_pt,
    );
    if ((Number.isFinite(minBody) && minBody >= 15) || slideData.timeline_mode) {
      renderTimelineComposition(
        slide,
        slideData,
        preset,
        header,
        evidenceContract,
        timelineItems,
      );
      return;
    }
    const maxItems = Math.max(1, Number(evidenceContract.density && evidenceContract.density.max_items) || 4);
    const facts = normalizeFacts(timelineItems.slice(0, maxItems).map((item, index) => ({
      value: safeText(item && (item.label || item.date), String(index + 1).padStart(2, '0')),
      label: safeText(item && (item.title || item.name), `Milestone ${index + 1}`),
      caption: safeText(item && (item.body || item.text || item.caption)),
      source: safeText(item && item.source),
    })));
    renderEvidenceContract(slide, slideData, preset, header, evidenceContract, facts);
    return;
  }
  const mode = String(slideData.timeline_mode || preset.timeline_mode || 'rail-cards')
    .trim()
    .toLowerCase();
  if (mode === 'bands' || mode === 'report-bands') {
    renderTimelineBands(pptx, slide, slideData, preset);
    return;
  }
  if (mode === 'chapter-spread' || mode === 'focus-stack') {
    renderTimelineChapterSpread(pptx, slide, slideData, preset);
    return;
  }
  if (mode === 'open-events') {
    renderTimelineOpenEvents(pptx, slide, slideData, preset);
    return;
  }
  if (mode === 'staggered') {
    renderTimelineStaggered(pptx, slide, slideData, preset);
    return;
  }

  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const rawItems = normalizeTimelineItems(slideData);
  const count = rawItems.length;

  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.30;
  const cardW = Math.max(1.5, (usableW - gutter * (count - 1)) / count);
  const totalW = cardW * count + gutter * (count - 1);
  const startX = MARGIN_X + (usableW - totalW) / 2;

  const railY = header.contentTop + 0.85;
  const markerR = 0.22;

  // Horizontal rail.
  slide.addShape('rect', shapeOpts({
    x: startX, y: railY - 0.03, w: totalW, h: 0.06,
    fill: { color: preset.line },
  }));

  const iconPaths = Array.isArray(slideData.__iconPaths) ? slideData.__iconPaths : [];

  // Markers + cards.
  rawItems.forEach((item, idx) => {
    const cardX = startX + idx * (cardW + gutter);
    const cx = cardX + cardW / 2;
    const accentKey = idx % 2 === 0 ? 'accent_primary' : 'accent_secondary';
    const accentColor = preset[accentKey] || preset.accent_primary;

    // Marker circle.
    slide.addShape('ellipse', shapeOpts({
      x: cx - markerR,
      y: railY - markerR,
      w: markerR * 2,
      h: markerR * 2,
      fill: { color: accentColor },
      line: { color: preset.bg, width: 1.5 },
    }));

    // Label text above the rail.
    slide.addText(safeText(item.label, `Phase ${idx + 1}`), textOpts({
      x: cardX,
      y: railY - 0.80,
      w: cardW,
      h: 0.30,
      fontFace: preset.font_heading,
      fontSize: 12,
      bold: true,
      color: accentColor,
      align: 'center',
      charSpacing: 2,
    }));

    // Card below the rail.
    const cardY = railY + 0.35;
    const cardH = SLIDE_H - cardY - 0.65;
    slide.addShape('rect', shapeOpts({
      x: cardX, y: cardY, w: cardW, h: cardH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.75 },
      shadow: cardShadow(),
    }));
    // Top accent rail on the card.
    slide.addShape('rect', shapeOpts({
      x: cardX, y: cardY, w: cardW, h: 0.08,
      fill: { color: accentColor },
    }));

    // Optional icon above the card title.
    const iconPath = iconPaths[idx];
    const iconSize = 0.35;
    const hasIcon = iconPath && fs.existsSync(iconPath);
    const cardShift = hasIcon ? (iconSize + 0.04) : 0;
    if (hasIcon) {
      slide.addImage({
        path: iconPath,
        x: cardX + (cardW - iconSize) / 2,
        y: cardY + 0.18,
        w: iconSize,
        h: iconSize,
      });
    }

    slide.addText(safeText(item.title, item.label || `Step ${idx + 1}`), textOpts({
      x: cardX + 0.15,
      y: cardY + 0.22 + cardShift,
      w: cardW - 0.30,
      h: 0.50,
      fontFace: preset.font_heading,
      fontSize: 15,
      bold: true,
      color: preset.text,
    }));
    const bodyText = safeText(item.body || item.text, '');
    const bodyFont = count >= 5 ? 9.2 : 10.0;
    const bodyY = cardY + 0.82 + cardShift;
    const bodyMaxH = Math.max(0.40, cardH - (bodyY - cardY) - 0.16);
    const bodyH = Math.min(
      bodyMaxH,
      Math.max(0.48, estimateTextHeight(bodyText, bodyFont, cardW - 0.30, 1.22) + 0.26),
    );
    slide.addText(bodyText, textOpts({
      x: cardX + 0.15,
      y: bodyY,
      w: cardW - 0.30,
      h: bodyH,
      fontFace: preset.font_body,
      fontSize: bodyFont,
      color: preset.text_muted,
      valign: 'top',
      paraSpaceAfter: 4,
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

// ---------------------------------------------------------------------------
// Stats: oversized fact tiles (value + label + optional caption/source).
// ---------------------------------------------------------------------------

function normalizeFacts(facts) {
  if (!Array.isArray(facts)) return [];
  return facts
    .map((f) => {
      if (!f || typeof f !== 'object') return null;
      const accentRaw = typeof f.accent === 'string' ? f.accent.trim() : '';
      let accent = null;
      if (accentRaw === 'accent_primary' || accentRaw === 'accent_secondary') {
        accent = accentRaw;
      }
      return {
        value: safeText(f.value ?? f.stat ?? f.number),
        label: safeText(f.label || f.title),
        caption: safeText(f.detail || f.caption || f.body || f.text),
        source: safeText(f.source),
        accent: accent,
      };
    })
    .filter((f) => f && (f.value || f.label));
}

function renderRoleFactCard(slide, preset, fact, box, index, isAnchor, dense, readable = null) {
  const accentKey = fact.accent || (index % 2 ? 'accent_secondary' : 'accent_primary');
  const accent = preset[accentKey] || preset.accent_primary;
  const darkAnchor = isAnchor && box.w >= 2.2 && box.h >= 1.5;
  const fill = darkAnchor ? (preset.bg_dark || '0F172A') : (preset.surface || 'FFFFFF');
  const valueColor = firstReadableColor(fill, [accent, preset.text, 'FFFFFF', '111111'], 4.5);
  if (readable) {
    const role = readable.role || 'evidence';
    const slotName = `role-contract-slot:${role}:${index}`;
    if (darkAnchor || readable.frame === 'rail') {
      slide.addShape('rect', shapeOpts({
        ...box, fill: { color: fill },
        line: { color: darkAnchor ? fill : (preset.line || 'CBD5E1'), width: 0.6 },
        objectName: slotName,
      }));
    } else {
      slide.addShape('line', shapeOpts({
        x: box.x, y: readable.frame === 'rule' ? box.y : box.y + box.h,
        w: box.w, h: 0,
        line: { color: readable.frame === 'rule' ? accent : (preset.line || 'CBD5E1'), width: 0.7 },
        objectName: slotName,
      }));
    }
    if (readable.frame === 'rail') {
      slide.addShape('rect', shapeOpts({
        x: box.x, y: box.y, w: 0.045, h: box.h,
        fill: { color: accent }, line: { color: accent, width: 0 },
      }));
    }
    const background = darkAnchor || readable.frame === 'rail' ? fill : (preset.bg || 'FFFFFF');
    for (const text of readable.texts) {
      const candidates = text.kind === 'value'
        ? [accent, preset.text, 'FFFFFF', '111111']
        : text.kind === 'caption'
          ? [preset.text_muted, 'CBD5E1', 'FFFFFF', '111111']
          : [darkAnchor ? 'FFFFFF' : preset.text, 'FFFFFF', '111111'];
      const { kind, text: content, ...options } = text;
      slide.addText(content, textOpts({
        ...options, color: firstReadableColor(background, candidates, 4.5),
        wrap: true, valign: 'top',
        objectName: `${role}:${index}:${kind}`,
      }));
    }
    return;
  }
  const titleColor = darkAnchor ? 'FFFFFF' : (preset.text || preset.text_primary || '0F172A');
  const mutedColor = darkAnchor
    ? firstReadableColor(fill, [preset.text_muted, 'CBD5E1', 'FFFFFF'], 3.0)
    : (preset.text_muted || '64748B');
  slide.addShape('rect', shapeOpts({
    x: box.x, y: box.y, w: box.w, h: box.h,
    objectName: `role-contract-slot:evidence:${index}`,
    fill: { color: fill },
    line: { color: darkAnchor ? fill : (preset.line || 'CBD5E1'), width: 0.6 },
  }));
  const horizontal = box.w >= box.h * 2.0;
  const hasValue = Boolean(safeText(fact.value));
  if (horizontal) {
    const longValue = safeText(fact.value).length >= 5;
    const valueW = hasValue ? Math.min(box.w * (longValue ? 0.30 : 0.25), longValue ? 1.45 : 1.35) : 0;
    slide.addShape('rect', shapeOpts({
      x: box.x, y: box.y, w: 0.06, h: box.h,
      fill: { color: accent }, line: { color: accent, width: 0 },
    }));
    if (hasValue) {
      slide.addText(truncate(fact.value, 10), textOpts({
        x: box.x + 0.18, y: box.y + 0.12, w: valueW, h: Math.max(0.34, box.h - 0.24),
        fontFace: preset.font_heading, fontSize: dense ? 18 : 22, bold: true,
        color: valueColor, valign: 'middle', fit: 'shrink',
      }));
    }
    const minBody = Number(
      preset && preset.readability_contract && preset.readability_contract.min_body_pt,
    );
    const compactCaption = Boolean(fact.caption) && box.h < (
      Number.isFinite(minBody) && minBody >= 15
        ? (hasValue ? 1.58 : 1.10)
        : Number.isFinite(minBody) && minBody >= 12
          ? (hasValue ? 1.34 : 0.94)
          : (hasValue ? 0.95 : 0.72)
    );
    const labelText = compactCaption
      ? [fact.label, fact.caption].map((item) => safeText(item)).filter(Boolean).join(' · ')
      : fact.label || '';
    const labelY = box.y + 0.12;
    const labelFont = roleBodyFont(preset, dense ? 9.5 : 11.5);
    const labelX = box.x + (hasValue ? valueW + 0.28 : 0.18);
    const labelW = Math.max(0.55, box.x + box.w - labelX - 0.18);
    const readableSideBySide = Number.isFinite(minBody)
      && minBody >= 15
      && Boolean(fact.caption)
      && box.h >= 1.50
      && labelW >= 2.20;
    if (readableSideBySide) {
      const splitGap = 0.18;
      const labelColumnW = Math.max(0.90, labelW * 0.45);
      const captionColumnW = Math.max(0.78, labelW - labelColumnW - splitGap);
      const textBoxMaxH = Math.max(0.40, box.h - 0.24);
      const labelBoxH = Math.min(
        textBoxMaxH,
        Math.max(0.42, estimateTextHeight(fact.label, labelFont, labelColumnW, 1.16) + 0.20),
      );
      const captionFont = roleBodyFont(preset, dense ? 8.0 : 9.2);
      const captionBoxH = Math.min(
        textBoxMaxH,
        Math.max(0.42, estimateTextHeight(fact.caption, captionFont, captionColumnW, 1.18) + 0.20),
      );
      slide.addText(fact.label || '', textOpts({
        x: labelX,
        y: box.y + (box.h - labelBoxH) / 2,
        w: labelColumnW,
        h: labelBoxH,
        fontFace: preset.font_heading,
        fontSize: labelFont,
        bold: true,
        color: titleColor,
        fit: 'shrink',
        valign: 'middle',
      }));
      slide.addText(fact.caption, textOpts({
        x: labelX + labelColumnW + splitGap,
        y: box.y + (box.h - captionBoxH) / 2,
        w: captionColumnW,
        h: captionBoxH,
        fontFace: preset.font_body,
        fontSize: captionFont,
        color: mutedColor,
        fit: 'shrink',
        valign: 'middle',
      }));
      return;
    }
    const minLabelH = hasValue ? 0.32 : 0.24;
    const labelH = Math.min(
      Math.max(minLabelH, box.h - 0.24),
      Math.max(minLabelH, estimateTextHeight(labelText, labelFont, labelW, 1.15) + (hasValue ? 0.16 : 0.08)),
    );
    slide.addText(labelText, textOpts({
      x: labelX, y: labelY,
      w: labelW, h: labelH,
      fontFace: preset.font_heading, fontSize: labelFont, bold: true,
      color: titleColor, fit: 'shrink',
    }));
    if (fact.caption && !compactCaption) {
      const captionY = labelY + labelH + (hasValue ? 0.12 : 0.08);
      const captionFont = roleBodyFont(preset, dense ? 8.0 : 9.2);
      const availableCaptionH = Math.max(0.16, box.y + box.h - captionY - (hasValue ? 0.10 : 0.04));
      const minCaptionH = Number.isFinite(minBody) && minBody >= 15 ? 0.62 : 0.30;
      const captionH = Math.min(
        Math.max(minCaptionH, estimateTextHeight(fact.caption, captionFont, labelW, 1.18) + 0.18),
        availableCaptionH,
      );
      slide.addText(fact.caption, textOpts({
        x: labelX, y: captionY,
        w: labelW,
        h: captionH,
        fontFace: preset.font_body,
        fontSize: captionFont,
        color: mutedColor, fit: 'shrink',
      }));
    }
    return;
  }
  slide.addShape('rect', shapeOpts({
    x: box.x, y: box.y, w: Math.min(0.075, box.w * 0.08), h: box.h,
    fill: { color: accent }, line: { color: accent, width: 0 },
  }));
  const pad = Math.min(0.24, Math.max(0.10, box.w * 0.08));
  const valueH = hasValue ? Math.min(Math.max(0.38, box.h * 0.28), 0.90) : 0;
  if (hasValue) {
    slide.addText(truncate(fact.value, 10), textOpts({
      x: box.x + pad, y: box.y + pad, w: Math.max(0.38, box.w - pad * 2), h: valueH,
      fontFace: preset.font_heading,
      fontSize: dense ? (isAnchor ? 25 : 18) : (isAnchor ? 34 : 23),
      bold: true, color: valueColor, fit: 'shrink',
    }));
  }
  const labelY = box.y + pad + (hasValue ? valueH + 0.12 : 0);
  const labelFont = roleBodyFont(preset, dense ? 9.5 : 11.5);
  const labelW = Math.max(0.38, box.w - pad * 2);
  const minBody = Number(
    preset && preset.readability_contract && preset.readability_contract.min_body_pt,
  );
  const compactCaption = Boolean(fact.caption) && box.h < (
      Number.isFinite(minBody) && minBody >= 15
        ? (hasValue ? 1.72 : 1.12)
      : Number.isFinite(minBody) && minBody >= 12
        ? (hasValue ? 2.00 : 1.12)
        : (hasValue ? 1.05 : 0.78)
  );
  const labelText = compactCaption
    ? [fact.label, fact.caption].map((item) => safeText(item)).filter(Boolean).join(' · ')
    : fact.label || '';
  const labelH = Math.min(
    Math.max(0.34, box.y + box.h - labelY - pad),
    Math.max(0.34, estimateTextHeight(labelText, labelFont, labelW, 1.15) + 0.16),
  );
  slide.addText(labelText, textOpts({
    x: box.x + pad, y: labelY, w: labelW,
    h: labelH,
    fontFace: preset.font_heading, fontSize: labelFont,
    bold: true, color: titleColor, fit: 'shrink',
  }));
  if (fact.caption && !compactCaption) {
    const captionY = labelY + labelH + 0.12;
    const captionFont = roleBodyFont(preset, dense ? 8.0 : 9.2);
    const availableCaptionH = Math.max(0.22, box.y + box.h - captionY - pad);
    const captionH = Math.min(
      Math.max(0.32, estimateTextHeight(fact.caption, captionFont, labelW, 1.18) + 0.18),
      availableCaptionH,
    );
    slide.addText(fact.caption, textOpts({
      x: box.x + pad, y: captionY, w: labelW,
      h: captionH,
      fontFace: preset.font_body,
      fontSize: captionFont,
      color: mutedColor, fit: 'shrink',
    }));
  }
}

function renderReadableEvidenceGrid(slide, slideData, preset, header, contract, facts) {
  const { planReadableRole } = require('./readable_role_layouts.js');
  const body = roleBodyBox(header, slideData, preset, { topGap: 0.12, summaryReserve: 0.76 });
  const grammar = safeText(contract.grammar_id || contract.composition_grammar_id || preset.composition_grammar);
  const layout = planReadableRole({
    grammar, role: 'evidence', variant: contract.variant, body, items: facts,
    fontSize: roleBodyFont(preset, 15), fontHeading: preset.font_heading, fontBody: preset.font_body,
  });
  layout.placements.forEach((placement) => {
    const { index, box, anchor } = placement;
    renderRoleFactCard(
      slide, preset, facts[index], box, index, anchor, false, placement,
    );
  });
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'evidence',
    facts.map((_fact, index) => `evidence_${index}`),
  );
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = `readable-evidence:${grammar}:${layout.recipe}`;
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
    slideData.__roleContractExecution.executed_slots = layout.placements.map(({ index, box }) => ({ slot: `evidence_${index}`, ...box }));
    slideData.__roleContractExecution.rendered_item_count = facts.length;
  }
  return true;
}

function renderPolicyEvidenceRecord(slide, slideData, preset, header, contract, facts) {
  if (!isPolicyPublicDocket(preset, slideData) || safeText(contract.system_id) !== 'evidence-public-record') {
    return false;
  }
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const items = facts.slice(0, 4);
  if (!items.length) return false;
  const accent = cleanHex(preset.accent_primary, 'C65D3B');
  const secondary = cleanHex(preset.accent_secondary, '2F7D76');
  const text = cleanHex(preset.text || preset.text_primary, '243133');
  const muted = cleanHex(preset.text_muted, '5F6F70');
  const line = cleanHex(preset.line, 'D8E1DD');
  const anchorW = Math.min(4.55, body.w * 0.38);
  const gap = 0.42;
  const rightX = body.x + anchorW + gap;
  const rightW = body.w - anchorW - gap;
  const anchor = items[0];

  slide.addShape('rect', shapeOpts({
    x: body.x, y: body.y, w: anchorW, h: body.h,
    fill: { color: preset.bg_dark || '173B3F' },
    line: { color: preset.bg_dark || '173B3F', width: 0 },
    objectName: 'role-contract-slot:evidence:primary-record',
  }));
  slide.addShape('rect', shapeOpts({
    x: body.x, y: body.y, w: 0.10, h: body.h,
    fill: { color: accent }, line: { color: accent, width: 0 },
  }));
  slide.addText(safeText(anchor.value, '01'), textOpts({
    x: body.x + 0.38, y: body.y + 0.54, w: anchorW - 0.72, h: 1.02,
    fontFace: preset.font_heading, fontSize: safeText(anchor.value).length > 8 ? 36 : 48,
    bold: true, color: 'FFFFFF', fit: 'shrink',
  }));
  slide.addText(safeText(anchor.label, 'Primary evidence'), textOpts({
    x: body.x + 0.38, y: body.y + 1.70, w: anchorW - 0.72, h: 0.72,
    fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 17),
    bold: true, color: 'FFFFFF', fit: 'shrink',
  }));
  const anchorDetail = safeText(anchor.caption || anchor.detail || anchor.source);
  if (anchorDetail) {
    const detailBottom = body.y + body.h - 0.18;
    const anchorLabelBottom = body.y + 2.42;
    const detailFont = roleBodyFont(preset, 15);
    const detailW = anchorW - 0.72;
    const availableDetailH = Math.max(0.34, detailBottom - anchorLabelBottom - 0.08);
    const detailH = Math.min(
      availableDetailH,
      Math.max(0.34, estimateTextHeight(anchorDetail, detailFont, detailW, 1.18) + 0.16),
    );
    const detailY = detailBottom - detailH;
    slide.addShape('line', shapeOpts({
      x: body.x + 0.38, y: detailY - 0.16, w: anchorW - 0.78, h: 0,
      line: { color: 'FFFFFF', transparency: 52, width: 0.65 },
    }));
    slide.addText(anchorDetail, textOpts({
      x: body.x + 0.38, y: detailY, w: detailW, h: detailH,
      fontFace: preset.font_body, fontSize: detailFont,
      color: 'FFFFFF', fit: 'shrink', valign: 'top',
    }));
  }

  const supporting = items.slice(1);
  const rowGap = 0.08;
  const rowH = (body.h - rowGap * Math.max(0, supporting.length - 1)) / Math.max(1, supporting.length);
  supporting.forEach((fact, index) => {
    const y = body.y + index * (rowH + rowGap);
    const rowAccent = index % 2 ? secondary : accent;
    if (index > 0) {
      slide.addShape('line', shapeOpts({
        x: rightX, y: y - rowGap / 2, w: rightW, h: 0,
        line: { color: line, width: 0.65 },
      }));
    }
    const valueW = Math.min(2.10, rightW * 0.30);
    slide.addText(safeText(fact.value, String(index + 2).padStart(2, '0')), textOpts({
      x: rightX, y: y + 0.12, w: valueW, h: Math.max(0.50, rowH - 0.24),
      fontFace: preset.font_heading, fontSize: safeText(fact.value).length > 8 ? 22 : 29,
      bold: true, color: rowAccent, fit: 'shrink', valign: 'middle',
    }));
    const labelX = rightX + valueW + 0.24;
    const labelW = rightW - valueW - 0.24;
    slide.addText(safeText(fact.label, `Evidence ${index + 2}`), textOpts({
      x: labelX, y: y + 0.10, w: labelW, h: Math.min(0.54, rowH * 0.42),
      fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 16),
      bold: true, color: text, fit: 'shrink', valign: 'middle',
    }));
    const detail = safeText(fact.caption || fact.detail || fact.source);
    if (detail) {
      const detailFont = roleBodyFont(preset, 15);
      const detailY = y + 0.10 + Math.min(0.54, rowH * 0.42) + 0.10;
      const availableDetailH = Math.max(0.30, y + rowH - detailY - 0.10);
      const detailH = Math.min(
        availableDetailH,
        Math.max(0.34, estimateTextHeight(detail, detailFont, labelW, 1.18) + 0.16),
      );
      slide.addText(detail, textOpts({
        x: labelX, y: detailY, w: labelW, h: detailH,
        fontFace: preset.font_body, fontSize: detailFont,
        color: muted, fit: 'shrink', valign: 'top',
      }));
    }
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, 'evidence', items.map((_fact, index) => `evidence_${index}`));
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'policy-public-record-open';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderEvidenceContract(slide, slideData, preset, header, contract, facts) {
  const minBody = Number(
    preset && preset.readability_contract && preset.readability_contract.min_body_pt,
  );
  if (Number.isFinite(minBody) && minBody >= 15) {
    if (Array.isArray(slideData.facts) && normalizeFacts(slideData.facts).length > facts.length) {
      throw new Error('Evidence exceeds the adapter item limit. Split this slide; content must not be dropped.');
    }
    return renderReadableEvidenceGrid(slide, slideData, preset, header, contract, facts);
  }
  if (renderPolicyEvidenceRecord(slide, slideData, preset, header, contract, facts)) return true;
  const body = roleBodyBox(header, slideData, preset, { summaryReserve: 0.76 });
  const slots = roleSlotNames(contract, 'evidence_');
  const dense = contract.variant === 'dense' || facts.length > slots.length;
  slots.forEach((slotName, index) => {
    if (!facts[index]) return;
    const box = roleSlot(contract, slotName, body);
    if (!box) return;
    const isFinalSlot = index === slots.length - 1;
    const overflowFacts = isFinalSlot ? facts.slice(index) : [facts[index]];
    if (overflowFacts.length === 1) {
      renderRoleFactCard(slide, preset, overflowFacts[0], box, index, slotName === contract.anchor_slot, dense);
      return;
    }
    const gap = 0.10;
    const horizontalSplit = box.w >= box.h * 2.2;
    overflowFacts.forEach((fact, overflowIndex) => {
      const count = overflowFacts.length;
      const splitBox = horizontalSplit
        ? {
          x: box.x + overflowIndex * ((box.w - gap * (count - 1)) / count + gap),
          y: box.y,
          w: (box.w - gap * (count - 1)) / count,
          h: box.h,
        }
        : {
          x: box.x,
          y: box.y + overflowIndex * ((box.h - gap * (count - 1)) / count + gap),
          w: box.w,
          h: (box.h - gap * (count - 1)) / count,
        };
      renderRoleFactCard(slide, preset, fact, splitBox, index + overflowIndex, false, true);
    });
  });
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'evidence',
    slots.filter((_slotName, index) => Boolean(facts[index])),
  );
}

function renderStatsFeatureLeft(slide, slideData, preset, header, facts, iconPaths) {
  const contentY = header.contentTop + 0.30;
  const contentH = SLIDE_H - contentY - 0.72;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.32;
  const leftW = Math.min(3.75, usableW * 0.42);
  const rightX = MARGIN_X + leftW + gutter;
  const rightW = usableW - leftW - gutter;
  const primary = facts[0];
  const primaryAccent = preset[primary.accent || 'accent_secondary'] || preset.accent_secondary || preset.accent_primary;

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: contentY,
    w: leftW,
    h: contentH,
    fill: { color: preset.bg_dark || '0F172A' },
    line: { color: preset.bg_dark || '0F172A', width: 0 },
    shadow: cardShadow(),
  }));
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: contentY,
    w: 0.10,
    h: contentH,
    fill: { color: primaryAccent },
    line: { color: primaryAccent, width: 0 },
  }));
  const primaryIcon = iconPaths[0];
  if (primaryIcon && fs.existsSync(primaryIcon)) {
    slide.addImage({ path: primaryIcon, x: MARGIN_X + leftW - 0.60, y: contentY + 0.28, w: 0.36, h: 0.36 });
  }
  slide.addText(truncate(primary.value || '-', 10), textOpts({
    x: MARGIN_X + 0.34,
    y: contentY + 0.48,
    w: leftW - 0.58,
    h: 0.95,
    fontFace: preset.font_heading,
    fontSize: String(primary.value || '').length > 5 ? 42 : 50,
    bold: true,
    color: primaryAccent,
    fit: 'shrink',
  }));
  slide.addText(primary.label || '', textOpts({
    x: MARGIN_X + 0.34,
    y: contentY + 1.58,
    w: leftW - 0.58,
    h: 0.68,
    fontFace: preset.font_heading,
    fontSize: 14,
    bold: true,
    color: 'FFFFFF',
    fit: 'shrink',
  }));
  if (primary.caption) {
    slide.addText(primary.caption, textOpts({
      x: MARGIN_X + 0.34,
      y: contentY + 2.42,
      w: leftW - 0.58,
      h: Math.max(0.56, contentH - 2.70),
      fontFace: preset.font_body,
      fontSize: 12,
      color: 'CBD5E1',
      fit: 'shrink',
    }));
  }

  const rest = facts.slice(1, 4);
  const rowGap = 0.16;
  const rowH = (contentH - rowGap * (rest.length - 1)) / Math.max(1, rest.length);
  rest.forEach((fact, idx) => {
    const y = contentY + idx * (rowH + rowGap);
    const accentKey = fact.accent || (idx % 2 ? 'accent_primary' : 'accent_secondary');
    const accentColor = preset[accentKey] || preset.accent_primary;
    slide.addShape('rect', shapeOpts({
      x: rightX,
      y,
      w: rightW,
      h: rowH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'D1D5DB', width: 0.75 },
    }));
    slide.addShape('rect', shapeOpts({
      x: rightX,
      y,
      w: 0.07,
      h: rowH,
      fill: { color: accentColor },
      line: { color: accentColor, width: 0 },
    }));
    const iconPath = iconPaths[idx + 1];
    if (iconPath && fs.existsSync(iconPath)) {
      slide.addImage({ path: iconPath, x: rightX + rightW - 0.42, y: y + 0.13, w: 0.24, h: 0.24 });
    }
    slide.addText(truncate(fact.value || '-', 8), textOpts({
      x: rightX + 0.20,
      y: y + 0.10,
      w: 1.20,
      h: 0.42,
      fontFace: preset.font_heading,
      fontSize: 16,
      bold: true,
      color: accentColor,
      fit: 'shrink',
    }));
    slide.addText(fact.label || '', textOpts({
      x: rightX + 0.20,
      y: y + 0.60,
      w: rightW - 0.48,
      h: 0.34,
      fontFace: preset.font_heading,
      fontSize: 12,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
    if (fact.caption) {
      const captionH = Math.min(
        Math.max(0.34, estimateTextHeight(fact.caption, 12, rightW - 0.40, 1.15) + 0.10),
        Math.max(0.22, rowH - 1.18),
      );
      slide.addText(fact.caption, textOpts({
        x: rightX + 0.20,
        y: y + 1.08,
        w: rightW - 0.40,
        h: captionH,
        fontFace: preset.font_body,
        fontSize: 12,
        color: preset.text_muted,
        fit: 'shrink',
      }));
    }
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderStatsPolicyBands(slide, slideData, preset, header, facts, iconPaths) {
  const contentY = header.contentTop + 0.35;
  const contentH = SLIDE_H - contentY - 0.72;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const leftW = 3.20;
  const rightX = MARGIN_X + leftW + 0.44;
  const rightW = usableW - leftW - 0.44;
  const primary = facts[0];
  const accent = preset[primary.accent || 'accent_primary'] || preset.accent_primary;
  const circleX = MARGIN_X - 0.20;
  const circleY = contentY + 0.18;
  const circleW = 2.65;
  const circlePad = 0.26;

  slide.addShape('ellipse', shapeOpts({
    x: circleX,
    y: circleY,
    w: circleW,
    h: circleW,
    fill: { color: accent, transparency: 88 },
    line: { color: accent, transparency: 100, width: 0 },
  }));
  const primaryIcon = iconPaths[0];
  if (primaryIcon && fs.existsSync(primaryIcon)) {
    slide.addImage({ path: primaryIcon, x: MARGIN_X + 2.55, y: contentY + 0.20, w: 0.34, h: 0.34 });
  }
  slide.addText(truncate(primary.value || '-', 10), textOpts({
    x: circleX + circlePad,
    y: circleY + 0.50,
    w: circleW - circlePad * 2,
    h: 0.92,
    fontFace: preset.font_heading,
    fontSize: String(primary.value || '').length > 5 ? 42 : 50,
    bold: true,
    color: accent,
    align: 'center',
    fit: 'shrink',
  }));
  slide.addText(primary.label || '', textOpts({
    x: circleX + circlePad,
    y: circleY + 1.48,
    w: circleW - circlePad * 2,
    h: 0.54,
    fontFace: preset.font_heading,
    fontSize: 13.5,
    bold: true,
    color: preset.text || preset.text_primary,
    align: 'center',
    fit: 'shrink',
  }));
  if (primary.caption) {
    slide.addText(primary.caption, textOpts({
      x: circleX + circlePad,
      y: circleY + 2.08,
      w: circleW - circlePad * 2,
      h: Math.min(0.72, Math.max(0.44, estimateTextHeight(primary.caption, 12, circleW - circlePad * 2, 1.20) + 0.18)),
      fontFace: preset.font_body,
      fontSize: 12,
      color: preset.text_muted,
      align: 'center',
      fit: 'shrink',
    }));
  }

  slide.addShape('line', shapeOpts({
    x: rightX - 0.22,
    y: contentY + 0.02,
    w: 0,
    h: contentH - 0.04,
    line: { color: preset.line || 'E2E8F0', width: 1.1 },
  }));

  const rest = facts.slice(1, 4);
  const rowH = contentH / Math.max(1, rest.length);
  rest.forEach((fact, idx) => {
    const y = contentY + idx * rowH;
    const factAccent = preset[fact.accent || (idx % 2 ? 'accent_secondary' : 'accent_primary')] || preset.accent_primary;
    if (idx > 0) {
      slide.addShape('line', shapeOpts({
        x: rightX,
        y,
        w: rightW,
        h: 0,
        line: { color: preset.line || 'E2E8F0', width: 0.8 },
      }));
    }
    const iconPath = iconPaths[idx + 1];
    if (iconPath && fs.existsSync(iconPath)) {
      slide.addImage({ path: iconPath, x: rightX, y: y + 0.22, w: 0.24, h: 0.24 });
    }
    slide.addText(truncate(fact.value || '-', 9), textOpts({
      x: rightX + 0.36,
      y: y + 0.18,
      w: 1.05,
      h: 0.34,
      fontFace: preset.font_heading,
      fontSize: 18,
      bold: true,
      color: factAccent,
      fit: 'shrink',
    }));
    slide.addText(fact.label || '', textOpts({
      x: rightX + 1.50,
      y: y + 0.18,
      w: rightW - 1.50,
      h: 0.34,
      fontFace: preset.font_heading,
      fontSize: 12,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
    if (fact.caption) {
      const captionH = Math.min(
        Math.max(0.34, estimateTextHeight(fact.caption, 12, rightW - 1.50, 1.15) + 0.10),
        Math.max(0.28, rowH - 0.78),
      );
      slide.addText(fact.caption, textOpts({
        x: rightX + 1.50,
        y: y + 0.70,
        w: rightW - 1.50,
        h: captionH,
        fontFace: preset.font_body,
        fontSize: 12,
        color: preset.text_muted,
        fit: 'shrink',
      }));
    }
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderStats(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const evidenceContract = roleContract(preset, slideData, 'evidence');
  const facts = normalizeFacts(slideData.facts).slice(
    0,
    evidenceContract ? Math.max(1, Number(evidenceContract.density && evidenceContract.density.max_items) || 4) : 4,
  );
  if (facts.length === 0) {
    slide.addText('No facts provided.', textOpts({
      x: MARGIN_X,
      y: header.contentTop + 1.0,
      w: SLIDE_W - MARGIN_X * 2,
      h: 0.5,
      fontFace: preset.font_body,
      fontSize: 14,
      color: preset.text_muted,
      align: 'center',
    }));
    addFooter(slide, preset, slideData);
    attachNotes(slide, slideData);
    return;
  }

  if (evidenceContract) {
    renderEvidenceContract(slide, slideData, preset, header, evidenceContract, facts);
    return;
  }

  const cols = facts.length;
  const gutter = 0.28;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const tileW = (usableW - gutter * (cols - 1)) / cols;
  const tileY = header.contentTop + 0.45;
  const tileH = SLIDE_H - tileY - 0.75;

  const iconPaths = Array.isArray(slideData.__iconPaths) ? slideData.__iconPaths : [];
  const statsMode = String(slideData.stats_mode || preset.stats_mode || 'tiles')
    .trim()
    .toLowerCase();
  if (statsMode === 'feature-left' && facts.length >= 3) {
    renderStatsFeatureLeft(slide, slideData, preset, header, facts, iconPaths);
    return;
  }
  if (statsMode === 'policy-bands' && facts.length >= 3) {
    renderStatsPolicyBands(slide, slideData, preset, header, facts, iconPaths);
    return;
  }

  facts.forEach((fact, idx) => {
    const tx = MARGIN_X + idx * (tileW + gutter);
    // Per-fact accent when explicitly set on the fact; otherwise alternate.
    const accentKey = fact.accent
      ? fact.accent
      : (idx % 2 === 0 ? 'accent_primary' : 'accent_secondary');
    const accentColor = preset[accentKey] || preset.accent_primary;

    slide.addShape('rect', shapeOpts({
      x: tx, y: tileY, w: tileW, h: tileH,
      fill: { color: preset.bg_dark },
      line: { color: preset.bg_dark, width: 0 },
      shadow: cardShadow(),
    }));
    // Left accent rail.
    slide.addShape('rect', shapeOpts({
      x: tx, y: tileY, w: 0.08, h: tileH,
      fill: { color: accentColor },
    }));

    // Optional icon above the stat value (smaller than cards — value stays
    // the dominant element).
    const iconPath = iconPaths[idx];
    const iconSize = 0.34;
    const hasIcon = iconPath && fs.existsSync(iconPath);
    if (hasIcon) {
      slide.addImage({
        path: iconPath,
        x: tx + tileW - iconSize - 0.22,
        y: tileY + 0.22,
        w: iconSize,
        h: iconSize,
      });
    }

    // Large stat value.
    const valueFont = String(fact.value || '').length > 5 ? 36 : 40;
    const valueY = tileY + 0.34;
    const valueH = Math.min(0.86, tileH * 0.28);
    const labelY = valueY + valueH + 0.13;
    const labelH = 0.74;
    const captionY = labelY + labelH + 0.12;
    slide.addText(truncate(fact.value || '-', 10), textOpts({
      x: tx + 0.25,
      y: valueY,
      w: tileW - 0.4,
      h: valueH,
      fontFace: preset.font_heading,
      fontSize: valueFont,
      bold: true,
      color: accentColor,
      valign: 'middle',
    }));
    slide.addText(fact.label || '', textOpts({
      x: tx + 0.25,
      y: labelY,
      w: tileW - 0.4,
      h: labelH,
      fontFace: preset.font_heading,
      fontSize: 12.5,
      bold: true,
      color: 'FFFFFF',
      valign: 'top',
    }));
    if (fact.caption) {
      slide.addText(fact.caption, textOpts({
        x: tx + 0.25,
        y: captionY,
        w: tileW - 0.4,
        h: Math.min(0.70, Math.max(0.44, 0.16 + estimateTextLines(fact.caption, 12, tileW - 0.4) * 0.20)),
        fontFace: preset.font_body,
        fontSize: 12,
        color: preset.text_muted,
        valign: 'top',
        paraSpaceAfter: 3,
      }));
    }
    if (fact.source) {
      slide.addText('Source: ' + fact.source, textOpts({
        x: tx + 0.25,
        y: tileY + tileH - 0.30,
        w: tileW - 0.4,
        h: 0.22,
        fontFace: preset.font_body,
        fontSize: 9,
        color: preset.text_muted,
        italic: true,
      }));
    }
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// kpi-hero variant — single giant number on a dark bg. The rhythm-break
// moment of the deck. Mirrors the python renderer (build_deck.py) closely
// so switching renderers produces the same composition.
// ---------------------------------------------------------------------------

function kpiValueFontSize(valueText) {
  const n = (valueText || '').trim().length;
  if (n <= 4) return 120;
  if (n <= 6) return 96;
  if (n <= 8) return 72;
  return 60;
}

function kpiValueBoxHeight(fontSize) {
  // Match the inventory line-height heuristic with a little internal padding
  // so oversized KPI values do not depend on PowerPoint text autofit.
  return Math.max(1.28, (fontSize / 72) * 1.22 + 0.14);
}

function renderKpiHero(pptx, slide, slideData, preset) {
  const dark = slideData.theme !== 'light';
  const bgColor = dark ? (preset.bg_dark || '0F172A') : preset.bg;
  paintBackground(slide, bgColor);

  // Title + subtitle on the top of the slide in light text for dark mode.
  const titleColor = dark ? 'FFFFFF' : preset.text_primary;
  const subtitleColor = dark ? 'CBD5E1' : preset.text_muted;
  const title = String(slideData.title || '').trim();
  const subtitle = String(slideData.subtitle || '').trim();
  const header = headerMetrics(title, subtitle, {
    topPad: 0.28,
    bottomPad: 0.10,
    titleFont: titleFontForLength(title) + 2,
    subtitleFont: 14,
  });
  slide.addText(title, textOpts({
    x: MARGIN_X,
    y: header.titleY,
    w: header.textW,
    h: header.titleH,
    fontFace: preset.font_title,
    fontSize: header.titleFont,
    color: titleColor,
    bold: true,
  }));
  if (subtitle) {
    slide.addText(subtitle, textOpts({
      x: MARGIN_X,
      y: header.subtitleY,
      w: header.textW,
      h: header.subtitleH,
      fontFace: preset.font_caption,
      fontSize: header.subtitleFont,
      color: subtitleColor,
    }));
  }

  const value = String(slideData.value || '?').trim();
  const label = String(slideData.label || '').trim();
  const context = String(slideData.context || '').trim();
  let valueFont = kpiValueFontSize(value);

  const valueColor = dark
    ? firstReadableColor(
      bgColor,
      [preset.accent_secondary, preset.accent_primary, 'FFFFFF', preset.text],
      4.5,
    )
    : firstReadableColor(
      bgColor,
      [preset.accent_primary, preset.accent_secondary, preset.text, '0F172A'],
      4.5,
    );

  // Center value vertically in the content zone, but reserve space for the
  // subtitle. Without this reservation, the big value shape overlaps the
  // subtitle (subtitle bottom = 0.96 + 0.42 = 1.38).
  const effectiveContentTop = Math.max(subtitle ? 1.50 : CONTENT_TOP, header.contentTop + 0.16);
  const contentH = SLIDE_H - effectiveContentTop - 0.85;
  let valueH = kpiValueBoxHeight(valueFont);
  const labelH = label ? 0.5 : 0;
  // Context box: scale height with line count. 13pt font across a ~7.4"-wide
  // box fits ~80 chars per line. Short strings get 0.42"; longer ones get
  // 0.42" per estimated line up to 3 lines. Previous flat 0.42" overflowed.
  let contextH = 0;
  if (context) {
    contextH = Math.min(
      0.78,
      Math.max(
        0.46,
        estimateTextHeight(context, 12, SLIDE_W - (MARGIN_X + 0.8) * 2, 1.22) + 0.12,
      ),
    );
  }
  const maxStack = Math.max(1.5, SLIDE_H - FOOTER_H - 0.16 - effectiveContentTop);
  const labelGap = label ? 0.15 : 0;
  const contextGap = context ? 0.10 : 0;
  let totalStack = valueH + labelGap + labelH + contextGap + contextH;
  if (totalStack > maxStack && context) {
    const overflow = totalStack - maxStack;
    contextH = Math.max(0.42, contextH - overflow);
    totalStack = valueH + labelGap + labelH + contextGap + contextH;
  }
  if (totalStack > maxStack) {
    const fixedStack = labelGap + labelH + contextGap + contextH;
    const availableForValue = Math.max(1.28, maxStack - fixedStack);
    while (valueFont > 60 && kpiValueBoxHeight(valueFont) > availableForValue) {
      valueFont -= 4;
    }
    valueH = Math.min(kpiValueBoxHeight(valueFont), availableForValue);
    totalStack = valueH + (label ? 0.15 : 0) + labelH +
                 (context ? 0.10 : 0) + contextH;
  }
  const idealStartY = effectiveContentTop + Math.max(0.2, (contentH - totalStack) / 2);
  const bottomLimit = SLIDE_H - 0.78;
  const startY = Math.max(
    effectiveContentTop + 0.05,
    Math.min(idealStartY, bottomLimit - totalStack),
  );

  slide.addText(value, textOpts({
    x: MARGIN_X,
    y: startY,
    w: SLIDE_W - MARGIN_X * 2,
    h: valueH,
    fontFace: preset.font_title,
    fontSize: valueFont,
    color: valueColor,
    bold: true,
    align: 'center',
    fit: 'shrink',
  }));
  if (label) {
    slide.addText(label, textOpts({
      x: MARGIN_X,
      y: startY + valueH + 0.22,
      w: SLIDE_W - MARGIN_X * 2,
      h: labelH,
      fontFace: preset.font_title,
      fontSize: 24,
      color: titleColor,
      bold: true,
      align: 'center',
    }));
  }
  if (context) {
    const contextY = startY + valueH + (label ? 0.22 + labelH + 0.10 : 0.15);
    slide.addText(context, textOpts({
      x: MARGIN_X + 0.8,
      y: contextY,
      w: SLIDE_W - (MARGIN_X + 0.8) * 2,
      h: contextH,
      fontFace: preset.font_caption,
      fontSize: 12,
      color: subtitleColor,
      align: 'center',
      fit: 'shrink',
    }));
  }

  addFooter(slide, preset, slideData, { dark });
  attachNotes(slide, slideData);
}


// ---------------------------------------------------------------------------
// table variant — native pptxgenjs addTable. Cleaner typography than the
// python renderer's add_table; this is the reason the HTML path exists.
// ---------------------------------------------------------------------------

function normalizeTableSpec(slideData) {
  const nested = (slideData.table && typeof slideData.table === 'object') ? slideData.table : {};
  const get = (key, fallback) => (
    slideData[key] !== undefined ? slideData[key] :
      nested[key] !== undefined ? nested[key] :
        fallback
  );
  return {
    title: String(get('title', '') || '').trim(),
    headers: Array.isArray(get('headers', [])) ? get('headers', []) : [],
    rows: Array.isArray(get('rows', [])) ? get('rows', []) : [],
    column_weights: Array.isArray(get('column_weights', null)) ? get('column_weights', null) : null,
    caption: String(get('caption', '') || '').trim(),
    footnotes: Array.isArray(get('footnotes', [])) ? get('footnotes', []) : [],
    cell_styles: get('cell_styles', null),
    cell_highlights: get('cell_highlights', null),
    row_styles: get('row_styles', null),
    header_style: get('header_style', null),
    table_style: String(get('table_style', '') || '').trim(),
    table_treatment: String(get('table_treatment', '') || '').trim().toLowerCase(),
  };
}

function normalizeTables(slideData) {
  const rawTables = Array.isArray(slideData.tables)
    ? slideData.tables
    : Array.isArray(slideData.table_groups)
      ? slideData.table_groups
      : [];
  if (rawTables.length) {
    return rawTables
      .filter((item) => item && typeof item === 'object')
      .map((item) => normalizeTableSpec({ table: item }));
  }
  return [normalizeTableSpec(slideData)].filter((item) => item.headers.length && item.rows.length);
}

function stripHashColor(value, fallback) {
  const raw = String(value || fallback || '').trim().replace(/^#/, '');
  return /^[0-9a-fA-F]{6}$/.test(raw) ? raw.toUpperCase() : String(fallback || 'FFFFFF');
}

function tableStyle(base, override) {
  const extra = (override && typeof override === 'object') ? override : {};
  const merged = Object.assign({}, base);
  const fillColor = extra.fill || extra.fill_color || (base.fill && base.fill.color);
  if (fillColor) merged.fill = { color: stripHashColor(fillColor, base.fill && base.fill.color) };
  const textColor = extra.color || extra.text_color || base.color;
  if (textColor) merged.color = stripHashColor(textColor, base.color);
  if (extra.bold !== undefined) merged.bold = !!extra.bold;
  if (extra.italic !== undefined) merged.italic = !!extra.italic;
  if (extra.align) merged.align = String(extra.align);
  if (extra.valign) merged.valign = String(extra.valign);
  if (extra.fontSize || extra.font_size) merged.fontSize = Number(extra.fontSize || extra.font_size);
  if (extra.margin !== undefined) merged.margin = Number(extra.margin);
  if (extra.border_color) merged.border = { color: stripHashColor(extra.border_color, 'CBD5E1'), pt: 0.5 };
  return merged;
}

function tableCellOverride(table, rowIdx, colIdx) {
  const cellStyles = table.cell_styles;
  if (Array.isArray(cellStyles)) {
    const row = cellStyles[rowIdx];
    if (Array.isArray(row) && row[colIdx] && typeof row[colIdx] === 'object') return row[colIdx];
  } else if (cellStyles && typeof cellStyles === 'object') {
    const direct = cellStyles[`${rowIdx},${colIdx}`] || cellStyles[`${rowIdx}:${colIdx}`];
    if (direct && typeof direct === 'object') return direct;
  }
  const highlights = Array.isArray(table.cell_highlights) ? table.cell_highlights : [];
  for (const item of highlights) {
    if (!item || typeof item !== 'object') continue;
    if (Number(item.row) === rowIdx && Number(item.col) === colIdx) return item;
  }
  return null;
}

function tableRowOverride(table, rowIdx) {
  const rowStyles = table.row_styles;
  if (Array.isArray(rowStyles) && rowStyles[rowIdx] && typeof rowStyles[rowIdx] === 'object') {
    return rowStyles[rowIdx];
  }
  if (rowStyles && typeof rowStyles === 'object') {
    const direct = rowStyles[String(rowIdx)];
    if (direct && typeof direct === 'object') return direct;
  }
  return null;
}

function buildTableRows(table, preset, opts) {
  const options = opts || {};
  const headerFill = stripHashColor(
    options.headerFill || (table.header_style && table.header_style.fill) || preset.accent_primary,
    '1F4E79',
  );
  const headerTextColor = stripHashColor(options.headerTextColor || 'FFFFFF', 'FFFFFF');
  const headerFont = options.headerFontSize || 11;
  const bodyFont = options.bodyFontSize || 9.5;
  const headerCellStyle = {
    fill: { color: headerFill },
    color: headerTextColor,
    bold: true,
    fontFace: preset.font_title,
    fontSize: headerFont,
    align: 'left',
    valign: 'middle',
    margin: 0.04,
  };
  const bodyCellStyleA = {
    fill: { color: stripHashColor(options.bodyFill || preset.surface || 'FFFFFF', 'FFFFFF') },
    color: preset.text_primary || preset.text || '0F172A',
    fontFace: preset.font_body,
    fontSize: bodyFont,
    align: 'left',
    valign: 'middle',
    margin: 0.04,
  };
  const bodyCellStyleB = tableStyle(bodyCellStyleA, {
    fill: options.zebraFill || preset.bg || 'F8FAFC',
  });

  const headerStyle = tableStyle(headerCellStyle, table.header_style);
  const tableRows = [
    table.headers.map((h) => ({ text: String(h || ''), options: tableStyle(headerStyle, {}) })),
  ];
  table.rows.forEach((row, idx) => {
    const rowBase = idx % 2 === 0 ? bodyCellStyleA : bodyCellStyleB;
    const rowExtra = tableRowOverride(table, idx);
    const cells = [];
    for (let c = 0; c < table.headers.length; c++) {
      const v = Array.isArray(row) && row[c] !== undefined ? row[c] : '';
      const override = tableCellOverride(table, idx, c);
      let cellStyle = tableStyle(tableStyle(rowBase, rowExtra), override);
      if (c === 0 && options.firstColumnFill) {
        cellStyle = tableStyle(cellStyle, {
          fill: options.firstColumnFill,
          color: options.firstColumnColor || 'FFFFFF',
          bold: options.firstColumnBold !== false,
        });
      } else if (c === table.headers.length - 1 && options.lastColumnFill) {
        cellStyle = tableStyle(cellStyle, {
          fill: options.lastColumnFill,
          color: options.lastColumnColor || preset.text_primary || preset.text,
          bold: options.lastColumnBold !== false,
        });
      }
      cells.push({ text: String(v), options: cellStyle });
    }
    tableRows.push(cells);
  });
  return tableRows;
}

function tableColumnWidths(headers, weights, usableW) {
  if (weights && weights.length === headers.length) {
    const total = weights.reduce((a, b) => a + Number(b || 0), 0);
    if (total > 0) return weights.map((w) => (usableW * Number(w || 0)) / total);
  }
  return Array(headers.length).fill(usableW / headers.length);
}

function normalizeTableTreatment(value, fallback) {
  const raw = String(value || fallback || 'standard').trim().toLowerCase();
  const allowed = new Set(['standard', 'compact-ledger', 'readout-sidecar', 'decision-matrix', 'journal-grid']);
  return allowed.has(raw) ? raw : 'standard';
}

function tableTreatmentOptions(treatment, preset, referenceTable) {
  if (referenceTable) {
    return {
      headerFontSize: 8.8,
      bodyFontSize: 7.8,
      rowH: null,
      headerFill: preset.bg_dark || preset.accent_primary,
    };
  }
  if (treatment === 'compact-ledger') {
    return {
      headerFontSize: 10.2,
      bodyFontSize: 8.9,
      rowH: 0.34,
      headerFill: preset.bg_dark || preset.accent_primary,
      zebraFill: preset.bg || 'F8FAFC',
    };
  }
  if (treatment === 'readout-sidecar') {
    return {
      headerFontSize: 10.6,
      bodyFontSize: 9.3,
      rowH: 0.39,
      headerFill: preset.accent_primary,
      zebraFill: preset.bg || 'F8FAFC',
      firstColumnFill: preset.bg_dark || preset.accent_primary,
      firstColumnColor: 'FFFFFF',
    };
  }
  if (treatment === 'decision-matrix') {
    return {
      headerFontSize: 10.8,
      bodyFontSize: 9.4,
      rowH: 0.40,
      headerFill: preset.bg_dark || preset.accent_primary,
      zebraFill: preset.surface_alt || preset.bg || 'F8FAFC',
      lastColumnFill: preset.accent_secondary || preset.accent_primary,
      lastColumnColor: 'FFFFFF',
    };
  }
  if (treatment === 'journal-grid') {
    return {
      headerFontSize: 9.8,
      bodyFontSize: 8.9,
      rowH: 0.36,
      headerFill: preset.line || 'CBD5E1',
      headerTextColor: preset.text_primary || preset.text || '0F172A',
      bodyFill: preset.surface || 'FFFFFF',
      zebraFill: preset.surface || 'FFFFFF',
    };
  }
  return {
    headerFontSize: 12,
    bodyFontSize: 10,
    rowH: 0.42,
    headerFill: preset.accent_primary,
  };
}

function tableReadoutText(slideData, table) {
  return safeText(
    slideData.interpretation
      || slideData.takeaway
      || slideData.summary_callout
      || slideData.key_summary,
  );
}

function addTableReadoutPanel(slide, preset, text, x, y, w, h, treatment) {
  if (!text || w <= 0 || h <= 0) return;
  const fill = treatment === 'decision-matrix' ? (preset.bg_dark || '0F172A') : (preset.surface || 'FFFFFF');
  const dark = treatment === 'decision-matrix';
  const bodyColor = firstReadableColor(fill, [dark ? 'FFFFFF' : preset.text, preset.text_primary, '111111', 'FFFFFF']);
  const accentColor = firstReadableColor(fill, [preset.accent_secondary, preset.accent_primary, bodyColor], 4.5);
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w,
    h,
    fill: { color: fill },
    line: { color: preset.line || preset.accent_primary || 'CBD5E1', width: dark ? 0 : 0.65 },
  }));
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w: 0.07,
    h,
    fill: { color: accentColor },
    line: { color: accentColor, width: 0 },
  }));
  if (w < 1.35) {
    const labelH = Math.min(0.34, Math.max(0.30, h * 0.16));
    const bodyFont = roleBodyFont(preset, 8.0);
    slide.addText(treatment === 'decision-matrix' ? 'DECISION' : 'READOUT', textOpts({
      x: x + 0.12, y: y + 0.12, w: Math.max(0.24, w - 0.24),
      h: labelH, fontFace: preset.font_heading,
      fontSize: roleMetadataFont(preset, 8.0), bold: true,
      color: accentColor,
      align: 'center', fit: 'shrink',
      objectName: 'metadata:table-readout-label',
    }));
    const bodyY = y + 0.12 + labelH + 0.10;
    const bodyW = Math.max(0.24, w - 0.24);
    const availableBodyH = Math.max(0.22, y + h - bodyY - 0.12);
    const bodyH = Math.min(
      Math.max(0.34, estimateTextHeight(text, bodyFont, bodyW, 1.18) + 0.12),
      availableBodyH,
    );
    slide.addText(text, textOpts({
      x: x + 0.12, y: bodyY, w: bodyW,
      h: bodyH,
      fontFace: preset.font_body, fontSize: bodyFont,
      color: bodyColor,
      align: 'center', valign: 'middle', fit: 'shrink',
    }));
    return;
  }
  if (h < 0.85) {
    const labelW = Math.min(1.18, Math.max(0.86, w * 0.18));
    const compactText = safeText(text).replace(/\s*\n\s*/g, '  |  ');
    const labelH = Math.min(0.34, Math.max(0.26, h - 0.16));
    slide.addText(treatment === 'decision-matrix' ? 'DECISION' : 'READOUT', textOpts({
      x: x + 0.18,
      y: y + Math.max(0.08, (h - labelH) / 2),
      w: labelW,
      h: labelH,
      fontFace: preset.font_heading,
      fontSize: roleMetadataFont(preset, 8.2),
      bold: true,
      color: accentColor,
      charSpacing: 1.1,
      fit: 'shrink',
      valign: 'middle',
      objectName: 'metadata:table-readout-label',
    }));
    slide.addText(compactText, textOpts({
      x: x + 0.24 + labelW,
      y: y + 0.06,
      w: Math.max(0.5, w - labelW - 0.44),
      h: Math.max(0.32, h - 0.12),
      fontFace: preset.font_body,
      fontSize: roleBodyFont(preset, 8.0),
      color: bodyColor,
      fit: 'shrink',
      valign: 'middle',
    }));
    return;
  }
  slide.addText(treatment === 'decision-matrix' ? 'DECISION' : 'READOUT', textOpts({
    x: x + 0.18,
    y: y + 0.16,
    w: w - 0.34,
    h: 0.34,
    fontFace: preset.font_heading,
    fontSize: roleMetadataFont(preset, 8.6),
    bold: true,
    color: accentColor,
    charSpacing: 1.2,
    fit: 'shrink',
    objectName: 'metadata:table-readout-label',
  }));
  const tallBodyFont = roleBodyFont(preset, 12);
  const tallBodyW = w - 0.34;
  const tallBodyH = Math.min(
    Math.max(0.50, estimateTextHeight(text, tallBodyFont, tallBodyW, 1.18) + 0.16),
    Math.max(0.50, h - 0.66),
  );
  slide.addText(text, textOpts({
    x: x + 0.18,
    y: y + 0.60,
    w: w - 0.34,
    h: tallBodyH,
    fontFace: preset.font_body,
    fontSize: tallBodyFont,
    color: bodyColor,
    fit: 'shrink',
    valign: 'top',
  }));
}

function addTableCaptionAndFootnotes(slide, preset, table, x, y, w, maxH, opts) {
  const lines = [];
  if (table.caption) lines.push(table.caption);
  for (const note of table.footnotes || []) {
    const text = String(note || '').trim();
    if (text) lines.push(text);
  }
  if (!lines.length || maxH <= 0.08) return;
  slide.addText(lines.join('\n'), textOpts({
    x,
    y,
    w,
    h: maxH,
    fontFace: preset.font_caption || preset.font_body,
      fontSize: (opts && opts.fontSize) || 8.2,
    color: preset.text_muted,
    italic: true,
    breakLine: false,
    fit: 'shrink',
    objectName: 'metadata:table-caption',
  }));
}

function addCompactTable(slide, preset, table, box, opts) {
  const options = opts || {};
  const title = String(table.title || '').trim();
  const titleH = title ? (options.titleH || 0.24) : 0;
  const gap = title ? 0.07 : 0;
  if (title) {
    slide.addText(title, textOpts({
      x: box.x,
      y: box.y,
      w: box.w,
      h: titleH,
      fontFace: preset.font_heading,
      fontSize: options.titleFont || 10.5,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
  }
  const noteLines = (table.caption ? 1 : 0) + (Array.isArray(table.footnotes) ? table.footnotes.length : 0);
  const notesH = Math.min(options.maxNotesH || 0.42, noteLines ? 0.14 + noteLines * 0.13 : 0);
  const tableY = box.y + titleH + gap;
  const tableH = Math.max(0.55, box.h - titleH - gap - notesH - (noteLines ? 0.08 : 0));
  const tableRows = buildTableRows(table, preset, {
    headerFontSize: options.headerFontSize || 9,
    bodyFontSize: options.bodyFontSize || 8,
    headerFill: options.headerFill,
  });
  const colW = tableColumnWidths(table.headers, table.column_weights, box.w);
  const rowH = Math.min(options.rowH || 0.30, Math.max(0.18, tableH / Math.max(1, tableRows.length)));
  slide.addTable(tableRows, {
    x: box.x,
    y: tableY,
    w: box.w,
    h: tableH,
    colW,
    fontSize: options.bodyFontSize || 8,
    rowH,
  });
  if (noteLines) {
    addTableCaptionAndFootnotes(slide, preset, table, box.x, tableY + tableH + 0.06, box.w, notesH, {
      fontSize: options.notesFontSize || 8.0,
    });
  }
}

function addRoleIndexPanel(slide, preset, table, box, referenceTable) {
  if (!box) return;
  const label = referenceTable ? 'SOURCE INDEX' : safeText(table.title, 'OPERATING INDEX').toUpperCase();
  const detail = [
    `${table.rows.length} ${referenceTable ? 'sources' : 'rows'}`,
    table.headers.slice(0, 3).map((item) => safeText(item)).filter(Boolean).join(' · '),
  ].filter(Boolean).join('\n');
  slide.addShape('rect', shapeOpts({
    x: box.x, y: box.y, w: box.w, h: box.h,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line || 'CBD5E1', width: 0.55 },
  }));
  const shallow = box.h < 0.80 || box.w >= box.h * 4.0;
  if (shallow) {
    const compactLabel = referenceTable ? 'SOURCE INDEX' : 'TABLE INDEX';
    const compactDetail = detail.replace(/\s*\n\s*/g, '  |  ');
    const labelW = Math.min(Math.max(0.92, box.w * 0.34), 2.35);
    const labelH = Math.min(0.34, Math.max(0.24, box.h - 0.16));
    slide.addText(compactLabel, textOpts({
      x: box.x + 0.12, y: box.y + Math.max(0.08, (box.h - labelH) / 2), w: Math.max(0.30, labelW - 0.12),
      h: labelH, fontFace: preset.font_heading,
      fontSize: roleMetadataFont(preset, 8.0), bold: true, color: preset.accent_primary,
      valign: 'middle', fit: 'shrink',
      objectName: 'metadata:table-index-label',
    }));
    slide.addText(compactDetail, textOpts({
      x: box.x + labelW + 0.10, y: box.y + 0.10,
      w: Math.max(0.30, box.w - labelW - 0.22), h: Math.max(0.20, box.h - 0.20),
      fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 8.0),
      color: preset.text || preset.text_primary || '0F172A', valign: 'middle', fit: 'shrink',
      objectName: 'metadata:table-index-detail',
    }));
    return;
  }
  const labelH = Math.min(0.26, Math.max(0.18, box.h * 0.14));
  const verticalLabel = box.w <= 2.00
    ? (referenceTable ? 'SOURCE INDEX' : 'TABLE INDEX')
    : label;
  slide.addText(verticalLabel, textOpts({
    x: box.x + 0.12, y: box.y + 0.10, w: Math.max(0.30, box.w - 0.24),
    h: labelH, fontFace: preset.font_heading,
    fontSize: roleMetadataFont(preset, box.w < 1.5 ? 8.0 : 9.2),
    bold: true, color: preset.accent_primary, fit: 'shrink',
    objectName: 'metadata:table-index-label',
  }));
  const detailY = box.y + 0.10 + labelH + 0.10;
  const detailFont = roleBodyFont(preset, 8.0);
  const detailW = Math.max(0.30, box.w - 0.24);
  const detailH = Math.min(
    Math.max(0.62, estimateTextHeight(detail, detailFont, detailW, 1.18) + 0.24),
    Math.max(0.22, box.y + box.h - detailY - 0.10),
  );
  slide.addText(detail, textOpts({
    x: box.x + 0.12, y: detailY,
    w: detailW, h: detailH,
    fontFace: preset.font_body, fontSize: detailFont,
    color: preset.text || preset.text_primary || '0F172A', fit: 'shrink',
  }));
}

function renderReadableReferenceRegister(slide, slideData, preset, header, table, contract) {
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const contentY = body.y;
  const sourceNoteText = (table.footnotes || [])
    .map((item) => safeText(item))
    .filter(Boolean)
    .join('  |  ');
  const sourceNoteH = sourceNoteText ? 0.54 : 0;
  const sourceNoteGap = sourceNoteText ? 0.10 : 0;
  const contentH = Math.max(1.0, body.h - sourceNoteH - sourceNoteGap);
  const columnGap = 0.28;
  const columnW = (body.w - columnGap) / 2;
  const splitAt = Math.ceil(table.rows.length / 2);
  const columns = [table.rows.slice(0, splitAt), table.rows.slice(splitAt)];
  const maxRows = Math.max(1, ...columns.map((rows) => rows.length));
  const rowGap = 0.08;
  const rowH = (contentH - rowGap * Math.max(0, maxRows - 1)) / maxRows;
  const metadataFont = roleMetadataFont(preset, 12.5);

  columns.forEach((rows, columnIndex) => {
    const x = body.x + columnIndex * (columnW + columnGap);
    rows.forEach((row, rowIndex) => {
      const y = contentY + rowIndex * (rowH + rowGap);
      const globalIndex = columnIndex === 0 ? rowIndex : splitAt + rowIndex;
      const accent = globalIndex % 2 === 0 ? preset.accent_primary : preset.accent_secondary;
      const title = safeText(Array.isArray(row) ? row[0] : '', `Source ${globalIndex + 1}`);
      const detail = Array.isArray(row)
        ? row.slice(1).map((item) => safeText(item)).filter(Boolean).join(' · ')
        : '';
      const longTitle = title.length > 18;
      const titleW = Math.min(longTitle ? 1.82 : 1.52, columnW * (longTitle ? 0.34 : 0.28));
      const titleFont = roleMetadataFont(preset, longTitle ? 10.0 : 12.5);
      const titleTextW = titleW - 0.14;
      const detailW = Math.max(0.50, columnW - titleW - 0.32);
      const titleH = Math.min(rowH - 0.08, Math.max(0.30,
        estimateTextHeight(title, titleFont, titleTextW, 1.18) + 0.16));
      const detailH = Math.min(rowH - 0.08, Math.max(0.30,
        estimateTextHeight(detail, metadataFont, detailW, 1.18) + 0.16));
      slide.addShape('rect', shapeOpts({
        x,
        y,
        w: columnW,
        h: rowH,
        fill: { color: preset.surface || 'FFFFFF' },
        line: { color: preset.line || 'CBD5E1', width: 0.6 },
        objectName: `role-contract-slot:references:register-${globalIndex}`,
      }));
      slide.addShape('rect', shapeOpts({
        x,
        y,
        w: 0.07,
        h: rowH,
        fill: { color: accent },
        line: { color: accent, width: 0 },
      }));
      slide.addText(title, textOpts({
        x: x + 0.18,
        y: y + (rowH - titleH) / 2,
        w: titleTextW,
        h: titleH,
        fontFace: preset.font_heading,
        fontSize: titleFont,
        bold: true,
        color: accent,
        valign: 'middle',
        fit: 'shrink',
        objectName: `metadata:reference-title-${globalIndex}`,
      }));
      slide.addText(detail, textOpts({
        x: x + titleW + 0.16,
        y: y + (rowH - detailH) / 2,
        w: detailW,
        h: detailH,
        fontFace: preset.font_body,
        fontSize: metadataFont,
        color: preset.text || preset.text_primary || '0F172A',
        valign: 'middle',
        fit: 'shrink',
        objectName: `metadata:reference-detail-${globalIndex}`,
      }));
    });
  });

  if (sourceNoteText) {
    const noteY = contentY + contentH + sourceNoteGap;
    slide.addShape('line', shapeOpts({
      x: body.x,
      y: noteY - 0.04,
      w: body.w,
      h: 0,
      line: { color: preset.line || 'CBD5E1', width: 0.65 },
    }));
    slide.addText(sourceNoteText, textOpts({
      x: body.x,
      y: noteY,
      w: body.w,
      h: sourceNoteH,
      fontFace: preset.font_body,
      fontSize: roleMetadataFont(preset, 9.0),
      color: preset.text_muted || '64748B',
      fit: 'shrink',
      valign: 'middle',
      objectName: 'metadata:reference-source-register',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'references',
    ['register'],
  );
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'readable-reference-register';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderPolicyOptionTable(slide, slideData, preset, header, table, contract) {
  if (!isPolicyPublicDocket(preset, slideData) || safeText(contract.system_id) !== 'table-public-record') {
    return false;
  }
  if (!table.headers.length || !table.rows.length) return false;
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const accent = cleanHex(preset.accent_primary, 'C65D3B');
  const secondary = cleanHex(preset.accent_secondary, '2F7D76');
  const summary = safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway);
  const interpretation = safeText(slideData.interpretation);
  const hasTableNotes = !!(table.caption || (table.footnotes || []).length);
  const captionH = hasTableNotes ? 0.20 : 0;
  const captionGap = hasTableNotes ? 0.06 : 0;
  const summaryLines = summary ? summary.split(/\r?\n/).filter(Boolean).length : 0;
  const summaryH = summary
    ? (summaryLines > 1 ? 0.82 : (summary.length > 84 ? 0.74 : 0.64))
    : 0;
  const summaryGap = summary ? 0.10 : 0;
  const interpretationH = interpretation ? 0.66 : 0;
  const interpretationGap = interpretation ? 0.10 : 0;
  const tableY = body.y;
  const tableH = Math.max(1.20, body.h - captionGap - captionH - summaryGap - summaryH - interpretationGap - interpretationH);
  const treatmentOpts = tableTreatmentOptions('standard', preset, false);
  treatmentOpts.headerFontSize = Math.max(12.5, roleBodyFont(preset, 13));
  treatmentOpts.bodyFontSize = Math.max(12.5, roleBodyFont(preset, 13));
  treatmentOpts.headerFill = preset.bg_dark || '173B3F';
  const tableRows = buildTableRows(table, preset, treatmentOpts);

  slide.addTable(tableRows, {
    x: body.x, y: tableY, w: body.w, h: tableH,
    colW: tableColumnWidths(table.headers, table.column_weights, body.w),
    fontSize: treatmentOpts.bodyFontSize,
    rowH: tableH / Math.max(1, tableRows.length),
    objectName: 'Editable table: public option register',
  });
  if (summary) {
    const summaryY = body.y + body.h - interpretationH - interpretationGap - summaryH;
    slide.addShape('rect', shapeOpts({
      x: body.x, y: summaryY, w: body.w, h: summaryH,
      fill: { color: secondary }, line: { color: secondary, width: 0 },
      objectName: 'role-contract-slot:table:readout',
    }));
    slide.addShape('rect', shapeOpts({
      x: body.x, y: summaryY, w: 0.12, h: summaryH,
      fill: { color: accent }, line: { color: accent, width: 0 },
    }));
    slide.addText(summary, textOpts({
      x: body.x + 0.28, y: summaryY + 0.06, w: body.w - 0.52, h: summaryH - 0.12,
      fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 16),
      bold: true, color: 'FFFFFF', fit: 'shrink', valign: 'middle',
    }));
    slideData.__roleContractConsumesSummary = true;
  }
  if (hasTableNotes) {
    addTableCaptionAndFootnotes(slide, preset, table, body.x, tableY + tableH + captionGap, body.w, captionH, {
      fontSize: roleMetadataFont(preset, 9),
    });
  }
  if (interpretation) {
    addTableReadoutPanel(
      slide, preset, interpretation,
      body.x, body.y + body.h - interpretationH, body.w, interpretationH, 'standard',
    );
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, 'table', ['table', ...(summary || interpretation ? ['readout'] : [])]);
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'policy-option-table-open';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderPolicyReferenceRegister(slide, slideData, preset, header, table, contract) {
  if (!isPolicyPublicDocket(preset, slideData) || safeText(contract.system_id) !== 'references-public-docket') {
    return false;
  }
  if (!table.rows.length) return false;
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const accent = cleanHex(preset.accent_primary, 'C65D3B');
  const secondary = cleanHex(preset.accent_secondary, '2F7D76');
  const text = cleanHex(preset.text || preset.text_primary, '243133');
  const muted = cleanHex(preset.text_muted, '5F6F70');
  const line = cleanHex(preset.line, 'D8E1DD');
  const indexed = table.rows.map((row, index) => ({ row, index }));
  let sourceRows = indexed.filter(({ row }) => {
    const label = safeText(row && row[0]);
    const detailLead = safeText(row && row[1]);
    return /(?:evidence|operating|source)\s+register/i.test(label)
      || /(?:source|evidence|dataset|reference)\b/i.test(label)
      || /^S\d+\b/i.test(detailLead);
  });
  let riskRows = indexed.filter((item) => !sourceRows.includes(item));
  if (!sourceRows.length && indexed.length > 5) {
    sourceRows = indexed.slice(-2);
    riskRows = indexed.slice(0, -2);
  }
  const gap = 0.32;
  const sourceW = sourceRows.length ? Math.min(3.30, body.w * 0.30) : 0;
  const riskW = body.w - sourceW - (sourceRows.length ? gap : 0);
  const labelH = 0.70;
  const rowsY = body.y + labelH + 0.10;
  const rowsH = body.h - labelH - 0.10;

  slide.addText('ACCOUNTABILITY REGISTER', textOpts({
    x: body.x, y: body.y, w: riskW, h: 0.30,
    fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
    bold: true, color: secondary, charSpacing: 0.8, fit: 'shrink',
    objectName: 'metadata:policy-accountability-register',
  }));
  const riskRowH = rowsH / Math.max(1, riskRows.length);
  const indexW = 0.42;
  const titleW = Math.min(1.70, Math.max(1.52, riskW * 0.27));
  const ownerW = Math.min(1.76, Math.max(1.62, riskW * 0.285));
  const controlW = Math.max(0.90, riskW - indexW - titleW - ownerW);
  const headerLabels = table.headers.slice(0, 3);
  [
    [body.x + indexW + 0.04, titleW - 0.08],
    [body.x + indexW + titleW + 0.04, ownerW - 0.08],
    [body.x + indexW + titleW + ownerW + 0.04, controlW - 0.08],
  ].forEach(([x, w], index) => {
    if (!safeText(headerLabels[index])) return;
    slide.addText(headerLabels[index], textOpts({
      x, y: body.y + 0.40, w, h: 0.22,
      fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
      bold: true, color: secondary, fit: 'shrink',
      objectName: `metadata:policy-register-header-${index}`,
    }));
  });
  const registerRows = riskRows.map(({ row }, rowIndex) => {
    const rowFill = cleanHex(preset.bg, 'F6F8F5');
    const cellBorder = { type: 'solid', color: rowFill, pt: 0.1 };
    return [
      {
        text: String(rowIndex + 1).padStart(2, '0'),
        options: {
          fill: { color: rowFill }, border: cellBorder,
          fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 14),
          bold: true, color: rowIndex % 2 ? secondary : accent, valign: 'middle', margin: 0.04,
        },
      },
      {
        text: safeText(row && row[0], `Risk ${rowIndex + 1}`),
        options: {
          fill: { color: rowFill }, border: cellBorder,
          fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 14),
          bold: true, color: text, valign: 'middle', margin: 0.04,
        },
      },
      {
        text: safeText(row && row[1]),
        options: {
          fill: { color: rowFill }, border: cellBorder,
          fontFace: preset.font_body, fontSize: roleBodyFont(preset, 13.5),
          color: secondary, valign: 'middle', margin: 0.04,
        },
      },
      {
        text: safeText(row && row[2]),
        options: {
          fill: { color: rowFill }, border: cellBorder,
          fontFace: preset.font_body, fontSize: roleBodyFont(preset, 13.5),
          color: muted, valign: 'middle', margin: 0.04,
        },
      },
    ];
  });
  if (registerRows.length) {
    riskRows.forEach((_item, rowIndex) => {
      if (rowIndex === 0) return;
      const y = rowsY + rowIndex * riskRowH;
      slide.addShape('line', shapeOpts({
        x: body.x, y, w: riskW, h: 0,
        line: { color: line, width: 0.65 },
      }));
    });
    slide.addTable(registerRows, {
      x: body.x, y: rowsY, w: riskW, h: rowsH,
      colW: [indexW, titleW, ownerW, controlW],
      rowH: riskRowH,
      objectName: 'Editable table: public accountability register',
    });
  }

  if (sourceRows.length) {
    const sourceX = body.x + riskW + gap;
    slide.addShape('rect', shapeOpts({
      x: sourceX, y: body.y, w: sourceW, h: body.h,
      fill: { color: preset.bg_dark || '173B3F' }, line: { color: preset.bg_dark || '173B3F', width: 0 },
      objectName: 'role-contract-slot:references:source-register',
    }));
    slide.addText('SOURCE REGISTER', textOpts({
      x: sourceX + 0.28, y: body.y + 0.26, w: sourceW - 0.56, h: 0.34,
      fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
      bold: true, color: 'FFFFFF', charSpacing: 0.8, fit: 'shrink',
      objectName: 'metadata:policy-source-register',
    }));
    const sourceTop = body.y + 0.62;
    const sourceRowH = (body.h - 0.72) / sourceRows.length;
    sourceRows.forEach(({ row }, index) => {
      const y = sourceTop + index * sourceRowH;
      if (index > 0) {
        slide.addShape('line', shapeOpts({
          x: sourceX + 0.28, y, w: sourceW - 0.56, h: 0,
          line: { color: 'FFFFFF', transparency: 64, width: 0.6 },
        }));
      }
      const sourceTitle = safeText(row && row[0], `Source ${index + 1}`);
      const sourceTitleW = sourceW - 0.56;
      const sourceTitleFont = roleMetadataFont(preset, sourceRows.length >= 3 ? 10 : 12.5);
      const sourceTitleH = Math.min(
        Math.max(0.26, sourceRowH - 0.46),
        Math.max(0.26, estimateTextHeight(sourceTitle, sourceTitleFont, sourceTitleW, 1.14) + 0.06),
      );
      slide.addText(sourceTitle, textOpts({
        x: sourceX + 0.28, y: y + 0.06, w: sourceTitleW, h: sourceTitleH,
        fontFace: preset.font_heading, fontSize: sourceTitleFont,
        bold: true, color: firstReadableColor(preset.bg_dark, [index % 2 ? secondary : accent, 'FFFFFF']), fit: 'shrink',
        objectName: `metadata:policy-source-title-${index}`,
      }));
      const sourceDetailCells = (row || []).slice(1).map((item) => safeText(item)).filter(Boolean);
      if (sourceDetailCells.length > 1 && /^S\d+(?:\s*,\s*S\d+)*$/i.test(sourceDetailCells[sourceDetailCells.length - 1])) {
        sourceDetailCells.pop();
      }
      const sourceDetail = sourceDetailCells.join(' · ');
      const sourceDetailFont = roleMetadataFont(preset, sourceRows.length >= 3 ? 9 : 12.5);
      const sourceDetailW = sourceW - 0.56;
      const sourceDetailY = y + 0.06 + sourceTitleH + 0.09;
      const sourceDetailAvailableH = Math.max(0.30, y + sourceRowH - sourceDetailY - 0.06);
      const sourceDetailH = Math.min(
        sourceDetailAvailableH,
        Math.max(0.30, estimateTextHeight(sourceDetail, sourceDetailFont, sourceDetailW, 1.18) + 0.14),
      );
      slide.addText(sourceDetail, textOpts({
        x: sourceX + 0.28, y: sourceDetailY, w: sourceDetailW, h: sourceDetailH,
        fontFace: preset.font_body, fontSize: sourceDetailFont,
        color: 'FFFFFF', fit: 'shrink', valign: 'top',
        objectName: `metadata:policy-source-detail-${index}`,
      }));
    });
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, 'references', ['register', ...(sourceRows.length ? ['notes'] : [])]);
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'policy-accountability-register-open';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderTableContract(slide, slideData, preset, header, table, referenceTable, contract) {
  if (referenceTable && renderPolicyReferenceRegister(slide, slideData, preset, header, table, contract)) return true;
  if (!referenceTable && renderPolicyOptionTable(slide, slideData, preset, header, table, contract)) return true;
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  let tableBox = roleSlot(contract, referenceTable ? 'register' : 'table', body);
  if (!tableBox) return false;
  let indexBox = roleSlot(contract, 'index', body);
  let readoutBox = roleSlot(contract, 'readout', body);
  let notesBox = roleSlot(contract, 'notes', body);
  const minBody = Number(
    preset && preset.readability_contract && preset.readability_contract.min_body_pt,
  );
  const readableWideTable = !referenceTable
    && Number.isFinite(minBody)
    && minBody >= 15
    && (table.headers.length >= 5 || table.rows.length >= 5);
  const readableReferenceRegister = referenceTable
    && Number.isFinite(minBody)
    && minBody >= 15
    && table.rows.length >= 5;
  if (readableReferenceRegister) {
    return renderReadableReferenceRegister(slide, slideData, preset, header, table, contract);
  }
  let readableAdaptation = readableWideTable
    ? 'readable-wide-table'
    : '';
  if (readableWideTable) {
    const stripH = Math.min(0.86, Math.max(0.78, body.h * 0.19));
    const stripGap = 0.28;
    const indexW = Math.min(3.20, body.w * 0.28);
    readoutBox = {
      x: body.x,
      y: body.y,
      w: body.w - indexW - stripGap,
      h: stripH,
    };
    indexBox = {
      x: body.x + body.w - indexW,
      y: body.y,
      w: indexW,
      h: stripH,
    };
    tableBox = {
      x: body.x,
      y: body.y + stripH + stripGap,
      w: body.w,
      h: Math.max(0.80, body.h - stripH - stripGap),
    };
    notesBox = null;
  }
  const explicitReadout = tableReadoutText(slideData, table);
  const narrowOrdinaryReadout = !referenceTable
    && explicitReadout
    && Number.isFinite(minBody)
    && minBody >= 15
    && readoutBox
    && (readoutBox.w < 2.75 || estimateTextHeight(explicitReadout, minBody, Math.max(0.30, readoutBox.w - 0.34), 1.18) > readoutBox.h - 0.60);
  if (narrowOrdinaryReadout) {
    const bandH = Math.min(1.02, Math.max(0.82, estimateTextHeight(explicitReadout, minBody, body.w - 1.70, 1.18) + 0.24));
    const bandGap = 0.24;
    tableBox = { x: body.x, y: body.y, w: body.w, h: Math.max(0.80, body.h - bandH - bandGap) };
    readoutBox = { x: body.x, y: body.y + body.h - bandH, w: body.w, h: bandH };
    indexBox = null;
    notesBox = null;
    readableAdaptation = 'readable-table-readout-band';
  }
  if (!referenceTable && !explicitReadout) {
    tableBox = body;
    indexBox = null;
    readoutBox = null;
    notesBox = null;
  }
  const treatment = normalizeTableTreatment(slideData.table_treatment || table.table_treatment, preset.table_treatment);
  const treatmentOpts = tableTreatmentOptions(treatment, preset, referenceTable);
  treatmentOpts.bodyFontSize = Math.max(8.0, roleBodyFont(preset, treatmentOpts.bodyFontSize || 8.0));
  treatmentOpts.headerFontSize = Math.max(8.4, roleBodyFont(preset, treatmentOpts.headerFontSize || 8.4));
  const tableRows = buildTableRows(table, preset, treatmentOpts);
  const captionText = [table.caption, ...(table.footnotes || [])].map((item) => safeText(item)).filter(Boolean).join('\n');
  const embeddedCaption = captionText && !notesBox && !readoutBox;
  const captionH = embeddedCaption ? Math.min(0.42, Math.max(0.22, tableBox.h * 0.12)) : 0;
  const tableH = Math.max(0.55, tableBox.h - captionH - (captionH ? 0.06 : 0));
  const rowH = readableAdaptation
    ? Math.max(0.36, tableH / Math.max(1, tableRows.length))
    : Math.max(0.18, Math.min(treatmentOpts.rowH || 0.36, tableH / Math.max(1, tableRows.length)));
  slide.addTable(tableRows, {
    x: tableBox.x,
    y: tableBox.y,
    w: tableBox.w,
    h: tableH,
    colW: tableColumnWidths(table.headers, table.column_weights, tableBox.w),
    fontSize: treatmentOpts.bodyFontSize || (contract.variant === 'dense' ? 7.5 : 8.3),
    rowH,
    objectName: `Editable ${referenceTable ? 'source register' : 'table'}: ${safeText(slideData.title)}`,
  });
  if (referenceTable && preset.style_preset === 'midnight-neon') {
    slide.addText('SOURCE REGISTER', textOpts({
      x: tableBox.x, y: tableBox.y - 0.28, w: tableBox.w, h: 0.22,
      fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
      bold: true, color: firstReadableColor(preset.bg, [preset.accent_primary, preset.text, 'FFFFFF']),
      objectName: 'metadata:reference-table-label',
    }));
  }
  if (embeddedCaption) {
    slide.addText(captionText, textOpts({
      x: tableBox.x, y: tableBox.y + tableH + 0.06, w: tableBox.w, h: captionH,
      fontFace: preset.font_caption || preset.font_body, fontSize: roleMetadataFont(preset, 9.0),
      italic: true, color: preset.text_muted || '64748B', fit: 'shrink',
      objectName: 'metadata:table-caption',
    }));
  }
  addRoleIndexPanel(slide, preset, table, indexBox, referenceTable);
  if (readoutBox) {
    addTableReadoutPanel(
      slide,
      preset,
      explicitReadout,
      readoutBox.x,
      readoutBox.y,
      readoutBox.w,
      readoutBox.h,
      treatment,
    );
    if (safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway)) {
      slideData.__roleContractConsumesSummary = true;
    }
  }
  if (notesBox && (captionText || explicitReadout)) {
    const notes = captionText || explicitReadout;
    slide.addShape('rect', shapeOpts({
      x: notesBox.x, y: notesBox.y, w: notesBox.w, h: notesBox.h,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.55 },
    }));
    const noteLabelText = referenceTable ? 'EVIDENCE NOTES' : 'READOUT';
    const shallowNotes = notesBox.h < 0.80 || notesBox.w >= notesBox.h * 4.0;
    if (shallowNotes) {
      const labelW = Math.min(Math.max(1.12, notesBox.w * 0.22), 2.45);
      slide.addText(noteLabelText, textOpts({
        x: notesBox.x + 0.12, y: notesBox.y + 0.08,
        w: Math.max(0.30, labelW - 0.12), h: Math.max(0.20, notesBox.h - 0.16),
        fontFace: preset.font_heading, fontSize: roleMetadataFont(preset, 8.0),
        bold: true, color: preset.accent_primary, valign: 'middle', fit: 'shrink',
        objectName: 'metadata:table-notes-label',
      }));
      slide.addText(notes.replace(/\s*\n\s*/g, '  |  '), textOpts({
        x: notesBox.x + labelW + 0.10, y: notesBox.y + 0.08,
        w: Math.max(0.30, notesBox.w - labelW - 0.22), h: Math.max(0.20, notesBox.h - 0.16),
        fontFace: preset.font_body, fontSize: referenceTable ? roleMetadataFont(preset, 9) : roleBodyFont(preset, 8.0),
        color: preset.text || preset.text_primary || '0F172A', valign: 'middle', fit: 'shrink',
        objectName: referenceTable ? 'metadata:reference-notes' : 'support:table-readout',
      }));
      addFooter(slide, preset, slideData);
      attachNotes(slide, slideData);
      markRoleContractExecution(
        slideData,
        preset,
        referenceTable ? 'references' : 'table',
        [referenceTable ? 'register' : 'table', 'notes'],
      );
      if (readableAdaptation && slideData.__roleContractExecution) {
        slideData.__roleContractExecution.adaptation = readableAdaptation;
        slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
      }
      return true;
    }
    const noteLabelFont = roleMetadataFont(preset, notesBox.w < 1.4 ? 8.0 : 8.5);
    const noteLabelW = Math.max(0.26, notesBox.w - 0.20);
    const noteLabelH = Math.min(
      Math.max(0.30, notesBox.h - 0.20),
      Math.max(0.32, estimateTextHeight(noteLabelText, noteLabelFont, noteLabelW, 1.12) + 0.14),
    );
    slide.addText(noteLabelText, textOpts({
      x: notesBox.x + 0.10, y: notesBox.y + 0.10, w: noteLabelW,
      h: noteLabelH, fontFace: preset.font_heading,
      fontSize: noteLabelFont,
      bold: true, color: preset.accent_primary, fit: 'shrink',
      objectName: 'metadata:table-notes-label',
    }));
    const notesY = notesBox.y + 0.10 + noteLabelH + 0.10;
    const notesFont = referenceTable ? roleMetadataFont(preset, 9) : roleBodyFont(preset, 8.0);
    const notesW = Math.max(0.26, notesBox.w - 0.20);
    const availableNotesH = Math.max(0.20, notesBox.y + notesBox.h - notesY - 0.10);
    const notesH = Math.min(
      Math.max(0.36, estimateTextHeight(notes, notesFont, notesW, 1.18) + 0.12),
      availableNotesH,
    );
    slide.addText(notes, textOpts({
      x: notesBox.x + 0.10, y: notesY,
      w: notesW, h: notesH,
      fontFace: preset.font_body, fontSize: notesFont,
      color: preset.text || preset.text_primary || '0F172A', fit: 'shrink',
      objectName: referenceTable ? 'metadata:reference-notes' : 'support:table-readout',
    }));
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    referenceTable ? 'references' : 'table',
    [
      referenceTable ? 'register' : 'table',
      ...(indexBox ? ['index'] : []),
      ...(readoutBox ? ['readout'] : []),
      ...(notesBox ? ['notes'] : []),
    ],
  );
  if (readableAdaptation && slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = readableAdaptation;
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderTable(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const table = normalizeTableSpec(slideData);
  const inferredReferenceTable = table.table_style === 'references' ||
    (
      slideData.source_footer_compaction &&
      slideData.source_footer_compaction.generated_by === 'scripts/compact_source_footers.py'
    );
  const renderPlan = resolvedRenderPlan(preset, slideData);
  const contractRole = renderPlan.canonicalRole === 'references' ? 'references' : 'table';
  const contractReferenceTable = contractRole === 'references';
  const referenceTable = contractReferenceTable || inferredReferenceTable;
  const referenceSystem = referenceTable ? roleSystem(preset, slideData, 'references') : '';
  const tableTreatment = referenceTable
    ? 'references'
    : normalizeTableTreatment(slideData.table_treatment || table.table_treatment, preset.table_treatment);
  const headers = table.headers;
  const rows = table.rows;
  if (headers.length === 0 || rows.length === 0) {
    slide.addText('table variant requires `headers` + `rows`.', textOpts({
      x: MARGIN_X,
      y: header.contentTop + 0.4,
      w: SLIDE_W - MARGIN_X * 2,
      h: 0.5,
      fontFace: preset.font_body,
      fontSize: 14,
      color: preset.text_muted,
    }));
    addFooter(slide, preset, slideData);
    attachNotes(slide, slideData);
    return;
  }

  const contract = roleContract(preset, slideData, contractRole);
  if (contract && renderTableContract(
    slide,
    slideData,
    preset,
    header,
    table,
    contractReferenceTable,
    contract,
  )) {
    return;
  }

  const usableW = SLIDE_W - MARGIN_X * 2;
  const captionLines = (table.caption ? 1 : 0) + table.footnotes.length;
  const captionGap = captionLines ? 0.12 : 0;
  const captionH = captionLines ? Math.min(referenceTable ? 0.38 : 0.54, 0.18 + captionLines * 0.14) : 0;
  const operationsReference = ['references-operations-log', 'references-technical-register'].includes(referenceSystem);
  const availableH = SLIDE_H - header.contentTop - 0.56 - captionH - captionGap - (operationsReference ? 0.42 : 0);
  const treatmentOpts = tableTreatmentOptions(tableTreatment, preset, referenceTable);
  const tableRows = buildTableRows(table, preset, treatmentOpts);
  let tableY = header.contentTop + (tableTreatment === 'journal-grid' ? 0.34 : 0.2) + (operationsReference ? 0.42 : 0);
  const sidecar = tableTreatment === 'readout-sidecar';
  const decisionStrip = tableTreatment === 'decision-matrix';
  const journalGrid = tableTreatment === 'journal-grid';
  const gap = sidecar ? 0.30 : 0;
  const sidecarW = sidecar ? Math.min(2.05, usableW * 0.24) : 0;
  let tableX = journalGrid ? MARGIN_X + usableW * 0.06 : MARGIN_X;
  let tableW = journalGrid ? usableW * 0.88 : usableW - sidecarW - gap;
  const editorialReference = referenceSystem === 'references-editorial-notes';
  const docketReference = referenceSystem === 'references-public-docket';
  const executiveReference = ['references-executive-notes', 'references-investor-diligence'].includes(referenceSystem);
  if (editorialReference) {
    tableX += 1.62;
    tableW -= 1.62;
  } else if (docketReference) {
    tableX += 1.08;
    tableW -= 1.08;
  } else if (executiveReference) {
    tableW *= 0.73;
  }
  const colW = tableColumnWidths(headers, table.column_weights, tableW);
  const stripH = decisionStrip ? 1.10 : 0;
  const tableAvailableH = Math.max(0.75, availableH - stripH - (decisionStrip ? 0.14 : 0));
  const rowH = treatmentOpts.rowH || (referenceTable ? Math.max(0.24, Math.min(0.42, tableAvailableH / Math.max(1, tableRows.length))) : 0.42);
  const tableH = referenceTable
    ? Math.max(0.75, Math.min(tableAvailableH, 0.52 + tableRows.length * rowH))
    : Math.min(tableAvailableH, 0.52 + tableRows.length * rowH);

  if (referenceTable && editorialReference) {
    slide.addShape('line', shapeOpts({
      x: MARGIN_X + 1.28, y: tableY, w: 0, h: tableH,
      line: { color: preset.line || 'CBD5E1', width: 0.75 },
    }));
    slide.addText('NOTES', textOpts({
      x: MARGIN_X, y: tableY, w: 1.08, h: 0.22, fontFace: preset.font_body,
      fontSize: 8.0, bold: true, color: preset.accent_primary, charSpacing: 1.2, fit: 'shrink',
    }));
    slide.addText('Sources are read as a closing editorial apparatus, not as a dashboard.', textOpts({
      x: MARGIN_X, y: tableY + 0.54, w: 1.08, h: Math.max(0.72, tableH - 0.70),
      fontFace: preset.font_heading, fontSize: 11, color: preset.text || preset.text_primary,
      valign: 'top', fit: 'shrink',
    }));
  }
  if (referenceTable && docketReference) {
    ['01', '02', '03'].forEach((label, idx) => {
      slide.addText(label, textOpts({
        x: MARGIN_X, y: tableY + idx * 0.74, w: 0.72, h: 0.28,
        fontFace: preset.font_heading, fontSize: 12, bold: true,
        color: idx === 0 ? preset.accent_primary : preset.text_muted, align: 'center', fit: 'shrink',
      }));
      slide.addShape('line', shapeOpts({
        x: MARGIN_X + 0.16, y: tableY + 0.38 + idx * 0.74, w: 0.40, h: 0,
        line: { color: idx === 0 ? preset.accent_primary : preset.line || 'CBD5E1', width: 0.65 },
      }));
    });
  }
  if (referenceTable && executiveReference) {
    const panelX = tableX + tableW + 0.28;
    const panelW = MARGIN_X + usableW - panelX;
    slide.addShape('rect', shapeOpts({
      x: panelX, y: tableY, w: panelW, h: tableH,
      fill: { color: preset.surface || 'FFFFFF' }, line: { color: preset.line || 'CBD5E1', width: 0.65 },
    }));
    slide.addShape('rect', shapeOpts({
      x: panelX, y: tableY, w: panelW, h: 0.10,
      fill: { color: preset.accent_primary }, line: { color: preset.accent_primary, width: 0 },
    }));
    slide.addText(referenceSystem === 'references-investor-diligence' ? 'DILIGENCE' : 'SOURCE POSTURE', textOpts({
      x: panelX + 0.18, y: tableY + 0.32, w: panelW - 0.36, h: 0.24,
      fontFace: preset.font_body, fontSize: 7.5, bold: true, color: preset.accent_primary, fit: 'shrink',
    }));
    slide.addText(`${rows.length} source records\nClaims remain linked to editable evidence objects.`, textOpts({
      x: panelX + 0.18, y: tableY + 0.70, w: panelW - 0.36, h: Math.max(0.90, tableH - 0.90),
      fontFace: preset.font_heading, fontSize: 11, color: preset.text || preset.text_primary, fit: 'shrink',
    }));
  }
  if (referenceTable && operationsReference) {
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X, y: tableY - 0.36, w: usableW, h: 0.24,
      fill: { color: preset.surface || 'FFFFFF' }, line: { color: preset.line || 'CBD5E1', width: 0.45 },
    }));
    slide.addText(referenceSystem === 'references-technical-register'
      ? 'TIME  |  SIGNAL  |  COMPONENT  |  PROVENANCE'
      : 'PERIOD  |  OWNER  |  FRESHNESS  |  SOURCE', textOpts({
      x: MARGIN_X + 0.14, y: tableY - 0.31, w: usableW - 0.28, h: 0.14,
      fontFace: preset.font_body, fontSize: 7.2, bold: true,
      color: preset.accent_primary, align: 'center', fit: 'shrink',
    }));
  }

  if (journalGrid) {
    slide.addShape('line', shapeOpts({
      x: tableX,
      y: tableY - 0.12,
      w: tableW,
      h: 0,
      line: { color: preset.line || preset.accent_primary || 'CBD5E1', width: 0.75 },
    }));
  }
  slide.addTable(tableRows, {
    x: tableX,
    y: tableY,
    w: tableW,
    h: tableH,
    colW,
    fontSize: referenceTable ? 7.8 : 11,
    rowH,
  });

  if (sidecar) {
    addTableReadoutPanel(
      slide,
      preset,
      tableReadoutText(slideData, table),
      tableX + tableW + gap,
      tableY,
      sidecarW,
      tableH,
      tableTreatment,
    );
  }

  if (decisionStrip) {
    addTableReadoutPanel(
      slide,
      preset,
      tableReadoutText(slideData, table),
      tableX,
      tableY + tableH + 0.14,
      tableW,
      stripH,
      tableTreatment,
    );
  }

  if (captionLines) {
    // Caption sits immediately below the table, not at a fixed bottom
    // offset — that caused overlap when the table ran long.
    addTableCaptionAndFootnotes(
      slide,
      preset,
      table,
      tableX,
      tableY + tableH + stripH + (decisionStrip ? 0.14 : 0) + captionGap,
      tableW,
      captionH,
      { fontSize: referenceTable ? 8.0 : 9 },
    );
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderLabRunResults(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const tables = normalizeTables(slideData);
  if (!tables.length) {
    slide.addText('lab-run-results requires `tables` or table `headers` + `rows`.', textOpts({
      x: MARGIN_X,
      y: header.contentTop + 0.4,
      w: SLIDE_W - MARGIN_X * 2,
      h: 0.5,
      fontFace: preset.font_body,
      fontSize: 13,
      color: preset.text_muted,
    }));
    addFooter(slide, preset, slideData);
    attachNotes(slide, slideData);
    return;
  }

  const usableW = SLIDE_W - MARGIN_X * 2;
  const callout = String(slideData.interpretation || slideData.takeaway || '').trim();
  const calloutReserve = callout ? 0.68 : 0;
  const usableH = SLIDE_H - header.contentTop - FOOTER_H - 0.34 - calloutReserve;
  const topY = header.contentTop + 0.18;
  const gutter = 0.24;

  if (tables.length === 1) {
    addCompactTable(slide, preset, tables[0], { x: MARGIN_X, y: topY, w: usableW, h: usableH }, {
      headerFontSize: 10,
      bodyFontSize: 8.6,
      rowH: 0.30,
      maxNotesH: 0.50,
    });
  } else if (tables.length === 2) {
    const colW = (usableW - gutter) / 2;
    addCompactTable(slide, preset, tables[0], { x: MARGIN_X, y: topY, w: colW, h: usableH }, {
      headerFontSize: 9.5,
      bodyFontSize: 8,
      rowH: 0.28,
      maxNotesH: 0.46,
    });
    addCompactTable(slide, preset, tables[1], { x: MARGIN_X + colW + gutter, y: topY, w: colW, h: usableH }, {
      headerFontSize: 9.5,
      bodyFontSize: 8,
      rowH: 0.28,
      maxNotesH: 0.46,
    });
  } else {
    const leftW = usableW * 0.58;
    const rightW = usableW - leftW - gutter;
    addCompactTable(slide, preset, tables[0], { x: MARGIN_X, y: topY, w: leftW, h: usableH }, {
      headerFontSize: 9,
      bodyFontSize: 8.2,
      rowH: 0.26,
      maxNotesH: 0.44,
    });
    const stackCount = Math.min(2, tables.length - 1);
    const stackH = (usableH - gutter * (stackCount - 1)) / stackCount;
    for (let i = 0; i < stackCount; i += 1) {
      addCompactTable(
        slide,
        preset,
        tables[i + 1],
        {
          x: MARGIN_X + leftW + gutter,
          y: topY + i * (stackH + gutter),
          w: rightW,
          h: stackH,
        },
        {
          headerFontSize: 8.8,
          bodyFontSize: 8.0,
          rowH: 0.24,
          titleFont: 9.2,
          maxNotesH: 0.34,
        },
      );
    }
  }

  if (callout) {
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y: SLIDE_H - FOOTER_H - 0.52,
      w: usableW,
      h: 0.42,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.5 },
    }));
    slide.addText(callout, textOpts({
      x: MARGIN_X + 0.12,
      y: SLIDE_H - FOOTER_H - 0.43,
      w: usableW - 0.24,
      h: 0.32,
      fontFace: preset.font_body,
      fontSize: 12,
      color: preset.text || preset.text_primary,
      bold: true,
      fit: 'shrink',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}


// ---------------------------------------------------------------------------
// comparison-2col — two-column A-vs-B layout with a dark verdict strip.
// Mirrors build_deck.py's _add_comparison_content composition.
// ---------------------------------------------------------------------------

function comparisonMetricRows(spec) {
  if (Array.isArray(spec.metrics)) {
    return spec.metrics.slice(0, 4).map((item) => ({
      label: safeText(item && (item.label || item.name || item.title)),
      value: safeText(item && (item.value || item.score || item.status)),
      note: safeText(item && (item.note || item.context)),
    })).filter((item) => item.label || item.value || item.note);
  }
  const body = Array.isArray(spec.body)
    ? spec.body.map((item) => safeText(item)).filter(Boolean)
    : safeText(spec.body).split(/\n|(?<=\.)\s+/).map((item) => item.trim()).filter(Boolean);
  return body.slice(0, 4).map((item) => ({ label: item, value: '', note: '' }));
}

function renderComparisonScorecard(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const left = (slideData.left && typeof slideData.left === 'object') ? slideData.left : {};
  const right = (slideData.right && typeof slideData.right === 'object') ? slideData.right : {};
  const verdict = safeText(slideData.verdict || slideData.takeaway);
  const hasFooter = hasFooterChrome(slideData, preset);
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.34;
  const colW = (usableW - gutter) / 2;
  const top = header.contentTop + 0.18;
  const footerReserve = hasFooter ? 0.52 : 0.18;
  const verdictH = verdict ? 0.54 : 0;
  const verdictGap = verdict ? 0.10 : 0;
  const bottom = SLIDE_H - footerReserve - verdictH - verdictGap;
  const scoreH = 0.78;
  const rowTop = top + scoreH + 0.06;
  const rowH = Math.max(0.68, bottom - rowTop);
  const requestedBodyFont = Number(slideData.comparison_body_font_size || 15);
  const bodyFontSize = Number.isFinite(requestedBodyFont) && requestedBodyFont >= 12
    ? requestedBodyFont
    : 15;

  const renderHead = (spec, x, accent) => {
    const title = safeText(spec.title, 'Option');
    const score = safeText(spec.score || spec.value || spec.primary_metric);
    const hasScore = Boolean(score);
    const scoreLabel = safeText(spec.score_label || spec.label || spec.subtitle);
    slide.addShape('rect', shapeOpts({
      x,
      y: top,
      w: colW,
      h: scoreH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.6 },
    }));
    slide.addShape('rect', shapeOpts({
      x,
      y: top,
      w: 0.07,
      h: scoreH,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    slide.addText(title, textOpts({
      x: x + 0.20,
      y: top + 0.10,
      w: hasScore ? colW * 0.55 : colW - 0.40,
      h: 0.32,
      fontFace: preset.font_heading,
      fontSize: 14,
      bold: true,
      color: accent,
      fit: 'shrink',
    }));
    if (hasScore) {
      slide.addText(score, textOpts({
        x: x + colW * 0.62,
        y: top + 0.04,
        w: colW * 0.32,
        h: 0.52,
        fontFace: preset.font_title,
        fontSize: score.length > 8 ? 21 : 25,
        bold: true,
        color: preset.text,
        align: 'right',
        fit: 'shrink',
      }));
    }
    if (scoreLabel) {
      slide.addText(scoreLabel, textOpts({
        x: x + 0.20,
        y: top + 0.54,
        w: colW - 0.40,
        h: 0.20,
        fontFace: preset.font_body,
        fontSize: 9.5,
        color: preset.text_muted,
        fit: 'shrink',
      }));
    }
  };

  const renderRows = (spec, x, accent) => {
    const rows = comparisonMetricRows(spec);
    const gap = 0.10;
    const eachH = (rowH - gap * Math.max(0, rows.length - 1)) / Math.max(1, rows.length);
    rows.forEach((row, idx) => {
      const y = rowTop + idx * (eachH + gap);
      slide.addShape('rect', shapeOpts({
        x,
        y,
        w: colW,
        h: eachH,
        fill: { color: idx % 2 === 0 ? (preset.surface || 'FFFFFF') : preset.bg },
        line: { color: preset.line, width: 0.45 },
      }));
      slide.addText([
        {
          text: row.label,
          options: {
            fontFace: preset.font_body,
            fontSize: bodyFontSize,
            bold: true,
            color: accent,
            breakLine: Boolean(row.note),
            paraSpaceAfter: 3,
          },
        },
        {
          text: row.note,
          options: {
            fontFace: preset.font_body,
            fontSize: bodyFontSize,
            color: preset.text,
          },
        },
      ], textOpts({
        x: x + 0.14,
        y: y + 0.04,
        w: colW * 0.70,
        h: Math.max(0.40, eachH - 0.08),
        fontFace: preset.font_body,
        fontSize: bodyFontSize,
        color: preset.text,
        valign: 'top',
        fit: 'shrink',
      }));
      if (row.value) {
        slide.addText(row.value, textOpts({
          x: x + colW * 0.74,
          y: y + 0.04,
          w: colW * 0.22 - 0.08,
          h: Math.max(0.40, eachH - 0.08),
          fontFace: preset.font_heading,
          fontSize: 12,
          bold: true,
          color: preset.text,
          align: 'right',
          valign: 'top',
          fit: 'shrink',
        }));
      }
    });
  };

  renderHead(left, MARGIN_X, preset.accent_primary);
  renderHead(right, MARGIN_X + colW + gutter, preset.accent_secondary);
  renderRows(left, MARGIN_X, preset.accent_primary);
  renderRows(right, MARGIN_X + colW + gutter, preset.accent_secondary);

  slide.addText('VS', textOpts({
    x: MARGIN_X + colW + gutter / 2 - 0.18,
    y: top + 0.41,
    w: 0.36,
    h: 0.24,
    fontFace: preset.font_heading,
    fontSize: 9,
    bold: true,
    color: preset.text_muted,
    align: 'center',
  }));

  if (verdict) {
    const y = bottom + verdictGap;
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: usableW,
      h: verdictH,
      fill: { color: preset.bg_dark },
      line: { color: preset.bg_dark, width: 0 },
    }));
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: 0.10,
      h: verdictH,
      fill: { color: preset.accent_secondary },
      line: { color: preset.accent_secondary, width: 0 },
    }));
    slide.addText(verdict, textOpts({
      x: MARGIN_X + 0.24,
      y: y + 0.07,
      w: usableW - 0.40,
      h: verdictH - 0.14,
      fontFace: preset.font_body,
      fontSize: 15,
      bold: true,
      color: 'FFFFFF',
      valign: 'middle',
      fit: 'shrink',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderPolicyOptionDocket(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const options = [
    (slideData.left && typeof slideData.left === 'object') ? slideData.left : {},
    (slideData.right && typeof slideData.right === 'object') ? slideData.right : {},
  ];
  const verdict = safeText(slideData.verdict || slideData.takeaway);
  const top = header.contentTop + 0.22;
  const usableH = SLIDE_H - top - 0.84;
  const docketW = 0.72;
  const verdictW = verdict ? 2.02 : 0;
  const gap = 0.22;
  const bandX = MARGIN_X + docketW + gap;
  const bandW = SLIDE_W - MARGIN_X * 2 - docketW - gap - verdictW - (verdict ? gap : 0);
  const bandH = (usableH - gap) / 2;
  options.forEach((spec, idx) => {
    const y = top + idx * (bandH + gap);
    const accent = idx === 0 ? preset.accent_primary : preset.accent_secondary;
    const lines = Array.isArray(spec.bullets)
      ? spec.bullets.map((item) => safeText(item)).filter(Boolean)
      : comparisonMetricRows(spec).map((item) => item.label || item.note).filter(Boolean);
    slide.addText(`0${idx + 1}`, textOpts({
      x: MARGIN_X, y: y + 0.10, w: docketW, h: 0.34,
      fontFace: preset.font_heading, fontSize: 14, bold: true, color: accent, align: 'center', fit: 'shrink',
    }));
    slide.addShape('line', shapeOpts({
      x: MARGIN_X + 0.16, y: y + 0.56, w: docketW - 0.32, h: 0,
      line: { color: accent, width: 0.75 },
    }));
    slide.addShape('rect', shapeOpts({
      x: bandX, y, w: bandW, h: bandH,
      fill: { color: preset.surface || 'FFFFFF' }, line: { color: preset.line || 'CBD5E1', width: 0.65 },
    }));
    slide.addShape('rect', shapeOpts({
      x: bandX, y, w: 0.08, h: bandH,
      fill: { color: accent }, line: { color: accent, width: 0 },
    }));
    slide.addText(safeText(spec.title, `Option ${idx + 1}`), textOpts({
      x: bandX + 0.28, y: y + 0.18, w: bandW * 0.34, h: bandH - 0.36,
      fontFace: preset.font_heading, fontSize: 18, bold: true, color: accent,
      valign: 'middle', fit: 'shrink',
    }));
    slide.addText(lines.slice(0, 3).join('\n'), textOpts({
      x: bandX + bandW * 0.40, y: y + 0.18, w: bandW * 0.55, h: bandH - 0.36,
      fontFace: preset.font_body, fontSize: 12, color: preset.text || preset.text_primary,
      valign: 'middle', fit: 'shrink',
    }));
  });
  if (verdict) {
    const x = bandX + bandW + gap;
    slide.addShape('rect', shapeOpts({
      x, y: top, w: verdictW, h: usableH,
      fill: { color: preset.bg_dark || '0F172A' }, line: { color: preset.bg_dark || '0F172A', width: 0 },
    }));
    slide.addText('PUBLIC DECISION', textOpts({
      x: x + 0.20, y: top + 0.30, w: verdictW - 0.40, h: 0.24,
      fontFace: preset.font_body, fontSize: 7.5, bold: true,
      color: preset.accent_secondary || 'FFFFFF', align: 'center', fit: 'shrink',
    }));
    slide.addText(verdict, textOpts({
      x: x + 0.22, y: top + 1.02, w: verdictW - 0.44, h: usableH - 1.34,
      fontFace: preset.font_heading, fontSize: 15, bold: true, color: 'FFFFFF',
      valign: 'middle', align: 'center', fit: 'shrink',
    }));
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function comparisonBodyLines(spec) {
  if (!spec || typeof spec !== 'object') return [];
  if (Array.isArray(spec.bullets)) return spec.bullets.map((item) => safeText(item)).filter(Boolean).slice(0, 5);
  if (Array.isArray(spec.body)) return spec.body.map((item) => safeText(item)).filter(Boolean).slice(0, 5);
  const metricRows = comparisonMetricRows(spec);
  if (metricRows.length) {
    return metricRows.map((row) => [row.label, row.value, row.note].filter(Boolean).join('  ')).slice(0, 5);
  }
  return safeText(spec.body || spec.text)
    .split(/\n|(?<=\.)\s+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 5);
}

function renderContractComparisonOption(slide, preset, spec, box, index, dense) {
  const accent = index === 0 ? preset.accent_primary : preset.accent_secondary;
  const title = safeText(spec.title, `Option ${index + 1}`);
  const body = comparisonBodyLines(spec);
  const narrow = box.w < 1.45;
  const horizontal = box.w >= box.h * 1.85;
  slide.addShape('rect', shapeOpts({
    x: box.x, y: box.y, w: box.w, h: box.h,
    objectName: `role-contract-slot:comparison:option-${index}`,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line || 'CBD5E1', width: 0.65 },
  }));
  slide.addShape('rect', shapeOpts({
    x: box.x, y: box.y, w: horizontal ? 0.07 : box.w, h: horizontal ? box.h : 0.07,
    fill: { color: accent }, line: { color: accent, width: 0 },
  }));
  if (horizontal) {
    const pad = 0.16;
    const titleW = Math.min(2.45, Math.max(1.35, box.w * 0.28));
    const titleFont = roleBodyFont(preset, dense ? 12 : 15);
    const titleTextW = Math.max(0.50, titleW - pad);
    const titleH = Math.min(
      Math.max(0.34, box.h - pad * 2),
      // Keep a full line-height safety margin for bold labels. PowerPoint's
      // rendered metrics are taller than the compact planning estimate for
      // short two-word labels such as "Design gap".
      Math.max(0.52, estimateTextHeight(title, titleFont, titleTextW, 1.16) + 0.30),
    );
    slide.addText(title, textOpts({
      x: box.x + pad, y: box.y + Math.max(pad, (box.h - titleH) / 2),
      w: titleTextW, h: titleH,
      fontFace: preset.font_heading, fontSize: titleFont,
      bold: true, color: accent, valign: 'middle', fit: 'shrink',
    }));
    if (body.length) {
      const text = body.map((item) => `• ${item}`).join('\n');
      const bodyFont = roleBodyFont(preset, dense ? 8.8 : 10.2);
      const bodyW = Math.max(0.50, box.w - titleW - pad - 0.12);
      const bodyH = Math.min(
        Math.max(0.34, box.h - pad * 2),
        Math.max(0.40, estimateTextHeight(text, bodyFont, bodyW, 1.20) + 0.22),
      );
      slide.addText(text, textOpts({
        x: box.x + titleW + 0.12,
        y: box.y + Math.max(pad, (box.h - bodyH) / 2),
        w: bodyW, h: bodyH,
        fontFace: preset.font_body,
        fontSize: bodyFont,
        color: preset.text || preset.text_primary || '0F172A',
        valign: 'middle', fit: 'shrink',
      }));
    }
    return;
  }
  const pad = narrow ? 0.10 : 0.18;
  const optionTitleFont = roleBodyFont(preset, narrow ? 10 : (dense ? 12 : 15));
  const titleH = Math.min(0.62, Math.max(0.34,
    estimateTextHeight(title, optionTitleFont, Math.max(0.30, box.w - pad * 2), 1.10) + 0.08));
  const titleX = box.x + pad;
  const titleY = box.y + pad;
  slide.addText(title, textOpts({
    x: titleX, y: titleY, w: Math.max(0.30, box.w - pad * 2), h: titleH,
    fontFace: preset.font_heading, fontSize: optionTitleFont,
    bold: true, color: accent, fit: 'shrink',
  }));
  if (body.length) {
    const bodyY = titleY + titleH + 0.10;
    const text = narrow ? body.join('\n') : body.map((item) => `• ${item}`).join('\n');
    const bodyFont = roleBodyFont(preset, narrow ? 7.6 : (dense ? 8.8 : 10.2));
    const bodyW = Math.max(0.30, box.w - pad * 2);
    const availableBodyH = Math.max(0.24, box.y + box.h - bodyY - pad);
    const bodyH = Math.min(
      Math.max(0.40, estimateTextHeight(text, bodyFont, bodyW, 1.20) + 0.26),
      availableBodyH,
    );
    slide.addText(text, textOpts({
      x: titleX, y: bodyY, w: bodyW,
      h: bodyH,
      fontFace: preset.font_body,
      fontSize: bodyFont,
      color: preset.text || preset.text_primary || '0F172A', fit: 'shrink',
    }));
  }
}

function renderPolicyComparisonDocket(slide, slideData, preset, contract) {
  if (!isPolicyPublicDocket(preset, slideData) || safeText(contract.system_id) !== 'comparison-policy-options') {
    return false;
  }
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const options = [
    (slideData.left && typeof slideData.left === 'object') ? slideData.left : {},
    (slideData.right && typeof slideData.right === 'object') ? slideData.right : {},
  ];
  const verdict = safeText(slideData.verdict || slideData.takeaway || slideData.summary_callout);
  const accent = cleanHex(preset.accent_primary, 'C65D3B');
  const secondary = cleanHex(preset.accent_secondary, '2F7D76');
  const text = cleanHex(preset.text || preset.text_primary, '243133');
  const muted = cleanHex(preset.text_muted, '5F6F70');
  const line = cleanHex(preset.line, 'D8E1DD');
  const verdictH = verdict ? 0.78 : 0;
  const verdictGap = verdict ? 0.18 : 0;
  const optionsH = body.h - verdictH - verdictGap;
  const rowH = optionsH / options.length;

  options.forEach((spec, index) => {
    const y = body.y + index * rowH;
    const rowAccent = index % 2 ? secondary : accent;
    const optionNumber = String(index + 1).padStart(2, '0');
    const optionTitle = safeText(spec.title, `Option ${index + 1}`);
    const bodyText = comparisonBodyLines(spec).map((item) => `• ${item}`).join('\n');
    const titleW = Math.min(3.0, body.w * 0.25);
    const bodyW = Math.max(1.0, body.w - titleW - 1.02);
    const numberFont = roleBodyFont(preset, 22);
    const titleFont = roleBodyFont(preset, 18);
    const optionBodyFont = roleBodyFont(preset, 15.5);
    const compactH = (value, font, width) => Math.min(rowH - 0.28, Math.max(
      0.40, estimateTextHeight(value, font, width, 1.18) + 0.18,
    ));
    const numberH = compactH(optionNumber, numberFont, 0.72);
    const titleH = compactH(optionTitle, titleFont, titleW);
    const bodyH = compactH(bodyText, optionBodyFont, bodyW);
    if (index > 0) {
      slide.addShape('line', shapeOpts({
        x: body.x, y, w: body.w, h: 0,
        line: { color: line, width: 0.75 },
      }));
    }
    slide.addText(optionNumber, textOpts({
      x: body.x, y: y + (rowH - numberH) / 2, w: 0.72, h: numberH,
      fontFace: preset.font_heading, fontSize: numberFont,
      bold: true, color: rowAccent, valign: 'middle', fit: 'shrink',
      objectName: `metadata:policy-option-${index + 1}`,
    }));
    slide.addText(optionTitle, textOpts({
      x: body.x + 0.88, y: y + (rowH - titleH) / 2, w: titleW, h: titleH,
      fontFace: preset.font_heading, fontSize: titleFont,
      bold: true, color: text, valign: 'middle', fit: 'shrink',
    }));
    slide.addText(bodyText, textOpts({
      x: body.x + 1.02 + titleW, y: y + (rowH - bodyH) / 2,
      w: bodyW, h: bodyH,
      fontFace: preset.font_body, fontSize: optionBodyFont,
      color: muted, valign: 'middle', fit: 'shrink',
    }));
  });

  if (verdict) {
    const y = body.y + optionsH + verdictGap;
    slide.addShape('rect', shapeOpts({
      x: body.x, y, w: body.w, h: verdictH,
      fill: { color: secondary }, line: { color: secondary, width: 0 },
      objectName: 'role-contract-slot:comparison:verdict',
    }));
    slide.addShape('rect', shapeOpts({
      x: body.x, y, w: 0.12, h: verdictH,
      fill: { color: accent }, line: { color: accent, width: 0 },
    }));
    slide.addText(verdict, textOpts({
      x: body.x + 0.30, y: y + 0.05, w: body.w - 0.56, h: verdictH - 0.10,
      fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 16),
      bold: true, color: 'FFFFFF', fit: 'shrink', valign: 'middle',
    }));
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, 'comparison', ['option_0', 'option_1', ...(verdict ? ['verdict'] : [])]);
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'policy-option-docket-open';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderComparisonContract(slide, slideData, preset, contract) {
  if (renderPolicyComparisonDocket(slide, slideData, preset, contract)) return true;
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const options = [
    (slideData.left && typeof slideData.left === 'object') ? slideData.left : {},
    (slideData.right && typeof slideData.right === 'object') ? slideData.right : {},
  ];
  const dense = contract.variant === 'dense';
  let optionBoxes = options.map((_spec, index) => roleSlot(contract, `option_${index}`, body));
  const verdict = safeText(slideData.verdict || slideData.takeaway);
  const verdictBox = roleSlot(contract, 'verdict', body);
  let verdictRenderBox = verdictBox;
  if (verdict && verdictBox) {
    // Some grammars intentionally use a compact verdict anchor between two
    // comparison fields. Preserve that reading order, but widen the top-row
    // anchor for sentence-length conclusions so the readability floor does
    // not force overflow inside a narrow semantic slot.
    verdictRenderBox = verdict.length > 52
      && verdictBox.w < body.w * 0.48
      && verdictBox.h <= body.h * 0.36
      ? {
        x: body.x + body.w * 0.20,
        y: verdictBox.y,
        w: body.w * 0.60,
        h: verdictBox.h,
      }
      : verdictBox;
    if (verdict.length > 70 && verdictRenderBox.h < 1.08) {
      const bottom = verdictRenderBox.y + verdictRenderBox.h;
      verdictRenderBox = {
        ...verdictRenderBox,
        y: bottom - 1.08,
        h: 1.08,
      };
    }
    const textRects = [];
    const measuringSlide = {
      addShape() {},
      addText(_text, opts) { textRects.push(opts); },
    };
    options.forEach((spec, index) => {
      if (optionBoxes[index]) {
        renderContractComparisonOption(measuringSlide, preset, spec, optionBoxes[index], index, dense);
      }
    });
    const intersectsText = (rect) => textRects.some((textRect) => (
      rect.x < textRect.x + textRect.w - 0.02
      && textRect.x < rect.x + rect.w - 0.02
      && rect.y < textRect.y + textRect.h - 0.02
      && textRect.y < rect.y + rect.h - 0.02
    ));
    if (intersectsText(verdictRenderBox)) {
      const verdictFont = roleBodyFont(preset, 12);
      const verdictH = Math.min(1.02, Math.max(
        0.72,
        estimateTextHeight(verdict, verdictFont, body.w - 0.24, 1.18) + 0.24,
      ));
      verdictRenderBox = {
        x: body.x,
        y: body.y + body.h - verdictH,
        w: body.w,
        h: verdictH,
      };
      if (intersectsText(verdictRenderBox)) {
        const bottom = Math.max(...optionBoxes.filter(Boolean).map((box) => box.y + box.h));
        const scale = Math.max(0.1, (verdictRenderBox.y - 0.10 - body.y) / (bottom - body.y));
        optionBoxes = optionBoxes.map((box) => box && ({
          ...box,
          y: body.y + (box.y - body.y) * scale,
          h: box.h * scale,
        }));
      }
    }
  }
  options.forEach((spec, index) => {
    if (optionBoxes[index]) {
      renderContractComparisonOption(slide, preset, spec, optionBoxes[index], index, dense);
    }
  });
  if (verdict && verdictRenderBox) {
    const accent = preset.accent_secondary || preset.accent_primary;
    slide.addShape('rect', shapeOpts({
      x: verdictRenderBox.x, y: verdictRenderBox.y, w: verdictRenderBox.w, h: verdictRenderBox.h,
      objectName: 'role-contract-slot:comparison:verdict',
      fill: { color: preset.bg_dark || '0F172A' },
      line: { color: accent, width: 0.65 },
    }));
    const verdictFont = roleBodyFont(
      preset,
      verdictRenderBox.w < 1.4 ? 8.0 : (verdictRenderBox.h < 0.75 ? 9.5 : 12),
    );
    const verdictW = Math.max(0.28, verdictRenderBox.w - 0.20);
    const availableVerdictH = Math.max(0.22, verdictRenderBox.h - 0.16);
    const verdictH = Math.min(
      Math.max(0.30, estimateTextHeight(verdict, verdictFont, verdictW, 1.18) + 0.12),
      availableVerdictH,
    );
    slide.addText(verdict, textOpts({
      x: verdictRenderBox.x + 0.10,
      y: verdictRenderBox.y + Math.max(0.08, (verdictRenderBox.h - verdictH) / 2),
      w: verdictW, h: verdictH,
      fontFace: preset.font_heading,
      fontSize: verdictFont,
      bold: true, color: 'FFFFFF', align: 'center', valign: 'middle', fit: 'shrink',
    }));
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'comparison',
    [
      ...options.map((_option, index) => `option_${index}`),
      ...(verdict && verdictBox ? ['verdict'] : []),
    ],
  );
}

function renderComparison2col(pptx, slide, slideData, preset) {
  const contract = roleContract(preset, slideData, 'comparison');
  if (contract) {
    renderComparisonContract(slide, slideData, preset, contract);
    return;
  }
  const comparisonSystem = roleSystem(preset, slideData, 'comparison');
  if (comparisonSystem === 'comparison-policy-options') {
    renderPolicyOptionDocket(pptx, slide, slideData, preset);
    return;
  }
  const mode = String(slideData.comparison_mode || preset.comparison_mode || 'open-columns').trim().toLowerCase();
  if (mode === 'scorecard') {
    renderComparisonScorecard(pptx, slide, slideData, preset);
    return;
  }
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const left = (slideData.left && typeof slideData.left === 'object') ? slideData.left : {};
  const right = (slideData.right && typeof slideData.right === 'object') ? slideData.right : {};
  const verdict = String(slideData.verdict || '').trim();

  const gutter = 0.35;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const colW = (usableW - gutter) / 2;
  const hasVerdict = verdict.length > 0;
  const verdictH = hasVerdict ? (verdict.length > 80 ? 0.86 : 0.70) : 0;
  const verdictGap = hasVerdict ? 0.20 : 0;

  const colTop = header.contentTop + 0.20;
  const colBottom = SLIDE_H - 0.65 - verdictH - verdictGap;
  const colH = Math.max(2.0, colBottom - colTop);

  const renderColumn = (spec, x, accentKey) => {
    const title = String(spec.title || '—').trim();
    let bodyLines;
    if (Array.isArray(spec.body)) {
      bodyLines = spec.body.map(String).filter((s) => s.trim());
    } else {
      bodyLines = String(spec.body || '')
        .split(/[.\n]/)
        .map((s) => s.trim())
        .filter((s) => s);
    }
    // Oversized colored title — the column's identity is the color + size,
    // not a thin accent rail (mirrors the python renderer's AI-tell fix).
    slide.addText(title, textOpts({
      x, y: colTop,
      w: colW, h: 0.72,
      fontFace: preset.font_title,
      fontSize: 24,
      bold: true,
      color: preset[accentKey] || preset.accent_primary,
    }));
    // Body bullets.
    const bodyY = colTop + 0.86;
    const bodyH = Math.max(0.8, colH - (bodyY - colTop) - 0.08);
    if (bodyLines.length) {
      slide.addText(
        bodyLines.map((line, i) => ({
          text: line,
          options: {
            bullet: { code: '2022' },
            breakLine: i < bodyLines.length - 1,
          },
        })),
        textOpts({
          x, y: bodyY, w: colW, h: bodyH,
          fontFace: preset.font_body,
          fontSize: 15,
          color: preset.text_primary,
          valign: 'top',
          paraSpaceAfter: 5,
        }),
      );
    }
  };

  renderColumn(left, MARGIN_X, 'accent_primary');
  renderColumn(right, MARGIN_X + colW + gutter, 'accent_secondary');

  // Vertical divider between the columns.
  const dividerX = MARGIN_X + colW + gutter / 2 - 0.02;
  slide.addShape('rect', shapeOpts({
    x: dividerX, y: colTop + 0.06,
    w: 0.04, h: colH - 0.12,
    fill: { color: preset.line || 'CBD5E1' },
    line: { color: preset.line || 'CBD5E1', width: 0 },
  }));

  if (hasVerdict) {
    const verdictY = colBottom + verdictGap;
    const verdictX = MARGIN_X + 0.5;
    const verdictW = usableW - 1.0;
    slide.addShape('rect', shapeOpts({
      x: verdictX, y: verdictY,
      w: verdictW, h: verdictH,
      fill: { color: preset.bg_dark || '0F172A' },
      line: { color: preset.bg_dark || '0F172A', width: 0 },
    }));
    // Left accent stripe inside the verdict strip.
    slide.addShape('rect', shapeOpts({
      x: verdictX, y: verdictY,
      w: 0.08, h: verdictH,
      fill: { color: preset.accent_primary || '14B8A6' },
      line: { color: preset.accent_primary || '14B8A6', width: 0 },
    }));
    slide.addText(verdict, textOpts({
      x: verdictX + 0.22, y: verdictY + 0.04,
      w: verdictW - 0.38, h: verdictH - 0.08,
      fontFace: preset.font_body,
      fontSize: 16,
      bold: true,
      color: 'FFFFFF',
      align: 'center',
      valign: 'middle',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}


// ---------------------------------------------------------------------------
// matrix — 2×2 quadrant grid. Mirrors _add_matrix_content.
// ---------------------------------------------------------------------------

function renderMatrixOpenQuadrants(slide, slideData, preset, header, quadrants, iconPaths) {
  const usableW = SLIDE_W - MARGIN_X * 2;
  const topY = header.contentTop + 0.25;
  const hasSummary = Boolean(safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway));
  const usableH = SLIDE_H - topY - 0.70 - (hasSummary ? 0.72 : 0);
  const centerX = MARGIN_X + usableW / 2;
  const centerY = topY + usableH / 2;
  const gutter = 0.34;
  const zoneW = (usableW - gutter) / 2;
  const zoneH = (usableH - gutter) / 2;

  slide.addShape('line', shapeOpts({
    x: centerX,
    y: topY,
    w: 0,
    h: usableH,
    line: { color: preset.line || 'E2E8F0', width: 1.0 },
  }));
  slide.addShape('line', shapeOpts({
    x: MARGIN_X,
    y: centerY,
    w: usableW,
    h: 0,
    line: { color: preset.line || 'E2E8F0', width: 1.0 },
  }));

  quadrants.forEach((q, idx) => {
    const row = Math.floor(idx / 2);
    const col = idx % 2;
    const x = MARGIN_X + col * (zoneW + gutter);
    const y = topY + row * (zoneH + gutter);
    const accentKey = idx % 2 === 0 ? 'accent_primary' : 'accent_secondary';
    const accentColor = preset[accentKey] || preset.accent_primary;
    const title = safeText(q.title, `Quadrant ${idx + 1}`);
    const body = safeText(q.body || q.text);
    const iconPath = iconPaths[idx];
    const hasIcon = iconPath && fs.existsSync(iconPath);

    slide.addShape('ellipse', shapeOpts({
      x: x + zoneW - 0.54,
      y: y + 0.04,
      w: 0.44,
      h: 0.44,
      fill: { color: accentColor, transparency: 86 },
      line: { color: accentColor, transparency: 100, width: 0 },
    }));
    slide.addText(String(idx + 1).padStart(2, '0'), textOpts({
      x: x,
      y: y + 0.02,
      w: 0.58,
      h: 0.30,
      fontFace: preset.font_heading,
      fontSize: 11,
      bold: true,
      color: accentColor,
      charSpacing: 1.2,
    }));
    if (hasIcon) {
      slide.addImage({
        path: iconPath,
        x: x + zoneW - 0.44,
        y: y + 0.14,
        w: 0.24,
        h: 0.24,
      });
    }
    slide.addText(title, textOpts({
      x,
      y: y + 0.42,
      w: zoneW - 0.18,
      h: 0.42,
      fontFace: preset.font_heading,
      fontSize: 15,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
    if (body) {
      const bodyLines = body.split(/\n|(?<=\.)\s+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 4);
      slide.addText(bodyLines.map((line, i) => ({
        text: line,
        options: { breakLine: i < bodyLines.length - 1 },
      })), textOpts({
        x,
        y: y + 0.96,
        w: zoneW - 0.18,
        h: Math.max(0.45, zoneH - 1.04),
        fontFace: preset.font_body,
        fontSize: 12,
        color: preset.text_muted || preset.text,
        fit: 'shrink',
        paraSpaceAfter: 3,
      }));
    }
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderReadableDecisionLedger(slide, slideData, preset, header, contract, quadrants) {
  const { planReadableRole, wrapText } = require('./readable_role_layouts.js');
  const body = roleBodyBox(header, slideData, preset, { topGap: 0.12, consumeSummary: true, footerReserve: 0.58 });
  const items = quadrants.map((item, index) => ({
    value: String(index + 1).padStart(2, '0'),
    label: safeText(item.title, `Gate ${index + 1}`),
    caption: safeText(item.body || item.text),
  }));
  const commitment = safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway);
  const bodyFont = roleBodyFont(preset, 15);
  const commitmentText = wrapText(commitment, body.w - 0.44, bodyFont, preset.font_heading, true);
  const commitmentGap = commitment ? 0.16 : 0;
  const commitmentH = commitment ? commitmentText.h + 0.20 : 0;
  const rowsH = body.h - commitmentGap - commitmentH;
  const grammar = safeText(contract.grammar_id || contract.composition_grammar_id || preset.composition_grammar);
  const layout = planReadableRole({
    grammar, role: 'decision', variant: contract.variant, body: { ...body, h: rowsH }, items,
    fontSize: bodyFont, fontHeading: preset.font_heading, fontBody: preset.font_body,
  });
  layout.placements.forEach((placement) => {
    const { index, box, anchor } = placement;
    renderRoleFactCard(slide, preset, items[index], box, index, anchor, false, { ...placement, role: 'decision' });
  });

  if (commitment) {
    const y = body.y + rowsH + commitmentGap;
    slide.addShape('rect', shapeOpts({
      x: body.x,
      y,
      w: body.w,
      h: commitmentH,
      fill: { color: preset.bg_dark || '0F172A' },
      line: { color: preset.accent_primary || '14B8A6', width: 0.65 },
      objectName: 'role-contract-slot:decision:commitment',
    }));
    slide.addText(commitmentText.text, textOpts({
      x: body.x + 0.22,
      y: y + 0.10,
      w: body.w - 0.44,
      h: commitmentText.h,
      fontFace: preset.font_heading,
      fontSize: bodyFont,
      bold: true,
      color: firstReadableColor(preset.bg_dark || '0F172A', ['FFFFFF', '111111'], 4.5),
      wrap: true,
      objectName: 'decision:commitment',
    }));
    slideData.__roleContractConsumesSummary = true;
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'decision',
    [
      ...items.map((_item, index) => `decision_${index}`),
      ...(commitment ? ['commitment'] : []),
    ],
  );
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = `readable-decision:${grammar}:${layout.recipe}`;
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
    slideData.__roleContractExecution.executed_slots = layout.placements.map(({ index, box }) => ({ slot: `decision_${index}`, ...box }));
    slideData.__roleContractExecution.rendered_item_count = items.length;
  }
  return true;
}

function renderPolicyDecisionBoard(slide, slideData, preset, header, contract, quadrants) {
  if (!isPolicyPublicDocket(preset, slideData) || safeText(contract.system_id) !== 'decision-policy-recommendation') {
    return false;
  }
  const items = quadrants.slice(0, 4);
  if (!items.length) return false;
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.46 });
  const accent = cleanHex(preset.accent_primary, 'C65D3B');
  const secondary = cleanHex(preset.accent_secondary, '2F7D76');
  const text = cleanHex(preset.text || preset.text_primary, '243133');
  const muted = cleanHex(preset.text_muted, '5F6F70');
  const line = cleanHex(preset.line, 'D8E1DD');
  const commitment = safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway);
  const commitmentH = commitment ? 0.58 : 0;
  const commitmentGap = commitment ? 0.06 : 0;
  const boardH = body.h - commitmentH - commitmentGap;
  const scopeW = Math.min(4.10, body.w * 0.35);
  const gap = 0.34;
  const rightX = body.x + scopeW + gap;
  const rightW = body.w - scopeW - gap;
  const scope = items[0];

  slide.addShape('rect', shapeOpts({
    x: body.x, y: body.y, w: scopeW, h: boardH,
    fill: { color: preset.bg_dark || '173B3F' }, line: { color: preset.bg_dark || '173B3F', width: 0 },
    objectName: 'role-contract-slot:decision:scope',
  }));
  slide.addText('PILOT SCOPE', textOpts({
    x: body.x + 0.34, y: body.y + 0.16, w: scopeW - 0.68, h: 0.24,
    fontFace: preset.font_body, fontSize: roleMetadataFont(preset, 9),
    bold: true, color: accent, charSpacing: 0.8, fit: 'shrink',
    objectName: 'metadata:policy-decision-scope',
  }));
  slide.addText(safeText(scope.title, 'Scope'), textOpts({
    x: body.x + 0.34, y: body.y + 0.52, w: scopeW - 0.68, h: 0.42,
    fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 23),
    bold: true, color: 'FFFFFF', fit: 'shrink',
  }));
  slide.addShape('line', shapeOpts({
    x: body.x + 0.34, y: body.y + 1.06, w: scopeW - 0.68, h: 0,
    line: { color: 'FFFFFF', transparency: 55, width: 0.65 },
  }));
  const scopeBody = safeText(scope.body || scope.text);
  const scopeBodyW = scopeW - 0.68;
  const scopeBodyFont = roleBodyFont(preset, 16);
  const scopeBodyY = body.y + 1.20;
  const scopeBodyAvailableH = Math.max(0.38, body.y + boardH - scopeBodyY - 0.18);
  const scopeBodyH = Math.min(
    scopeBodyAvailableH,
    Math.max(0.38, estimateTextHeight(scopeBody, scopeBodyFont, scopeBodyW, 1.18) + 0.18),
  );
  slide.addText(scopeBody, textOpts({
    x: body.x + 0.34, y: scopeBodyY, w: scopeBodyW, h: scopeBodyH,
    fontFace: preset.font_body, fontSize: scopeBodyFont,
    color: 'FFFFFF', fit: 'shrink', valign: 'top',
  }));

  const supporting = items.slice(1);
  if (supporting.length) {
    const rowGap = 0.02;
    const availableRowsH = boardH - rowGap * Math.max(0, supporting.length - 1);
    const rowWeights = supporting.map((item) => {
      const length = safeText(item.body || item.text).length;
      return length > 84 ? 1.45 : (length > 64 ? 1.35 : 1.0);
    });
    const totalWeight = rowWeights.reduce((sum, value) => sum + value, 0);
    let rowY = body.y;
    supporting.forEach((item, index) => {
      const rowH = availableRowsH * rowWeights[index] / totalWeight;
      const y = rowY;
      const itemAccent = index % 2 ? secondary : accent;
      if (index > 0) {
        slide.addShape('line', shapeOpts({
          x: rightX, y: y - rowGap / 2, w: rightW, h: 0,
          line: { color: line, width: 0.7 },
        }));
      }
      const titleText = safeText(item.title, `Gate ${index + 1}`);
      const bodyText = safeText(item.body || item.text);
      const titleW = Math.min(bodyText.length > 58 ? 1.14 : 1.44, rightW * 0.24);
      const titleFont = roleBodyFont(preset, 17);
      const bodyFont = roleBodyFont(preset, 15.5);
      const availableTextH = Math.max(0.30, rowH - 0.08);
      const titleH = Math.min(
        availableTextH,
        Math.max(0.34, estimateTextHeight(titleText, titleFont, titleW, 1.14) + 0.14),
      );
      const bodyW = rightW - titleW - 0.20;
      const bodyTextH = Math.min(
        availableTextH,
        Math.max(0.34, estimateTextHeight(bodyText, bodyFont, bodyW, 1.18) + 0.16),
      );
      slide.addText(titleText, textOpts({
        x: rightX, y: y + 0.04 + (availableTextH - titleH) / 2, w: titleW, h: titleH,
        fontFace: preset.font_heading, fontSize: titleFont,
        bold: true, color: itemAccent, fit: 'shrink', valign: 'middle',
      }));
      slide.addText(bodyText, textOpts({
        x: rightX + titleW + 0.20, y: y + 0.04 + (availableTextH - bodyTextH) / 2,
        w: bodyW, h: bodyTextH,
        fontFace: preset.font_body, fontSize: bodyFont,
        color: index === supporting.length - 1 ? muted : text,
        fit: 'shrink', valign: 'middle',
      }));
      rowY += rowH + rowGap;
    });
  }

  if (commitment) {
    const y = body.y + boardH + commitmentGap;
    slide.addShape('rect', shapeOpts({
      x: body.x, y, w: body.w, h: commitmentH,
      fill: { color: secondary }, line: { color: secondary, width: 0 },
      objectName: 'role-contract-slot:decision:commitment',
    }));
    slide.addText(commitment, textOpts({
      x: body.x + 0.28, y: y + 0.05, w: body.w - 0.56, h: commitmentH - 0.10,
      fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 16),
      bold: true, color: 'FFFFFF', fit: 'shrink', valign: 'middle', align: 'center',
    }));
    slideData.__roleContractConsumesSummary = true;
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(slideData, preset, 'decision', [
    ...items.map((_item, index) => `decision_${index}`),
    ...(commitment ? ['commitment'] : []),
  ]);
  if (slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = 'policy-decision-board-open';
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderDecisionContract(slide, slideData, preset, header, contract, quadrants) {
  const minBody = Number(
    preset && preset.readability_contract && preset.readability_contract.min_body_pt,
  );
  if (Number.isFinite(minBody) && minBody >= 15) {
    const items = Array.isArray(slideData.quadrants) ? slideData.quadrants : quadrants;
    return renderReadableDecisionLedger(slide, slideData, preset, header, contract, items);
  }
  if (renderPolicyDecisionBoard(slide, slideData, preset, header, contract, quadrants)) return true;
  const body = roleBodyBox(header, slideData, preset, { consumeSummary: true, footerReserve: 0.58 });
  const dense = contract.variant === 'dense';
  quadrants.slice(0, 4).forEach((item, index) => {
    const box = roleSlot(contract, `decision_${index}`, body);
    if (!box) return;
    const accent = index % 2 === 0 ? preset.accent_primary : preset.accent_secondary;
    const narrow = box.w < 1.55;
    slide.addShape('rect', shapeOpts({
      x: box.x, y: box.y, w: box.w, h: box.h,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.65 },
    }));
    slide.addShape('rect', shapeOpts({
      x: box.x, y: box.y, w: Math.min(0.07, box.w * 0.10), h: box.h,
      fill: { color: accent }, line: { color: accent, width: 0 },
    }));
    const pad = narrow ? 0.10 : 0.17;
    const shallow = box.h < 1.30 || box.w >= box.h * 4.0;
    if (shallow) {
      const titleText = safeText(item.title, `Gate ${index + 1}`);
      const bodyText = safeText(item.body || item.text);
      const titleFont = roleBodyFont(preset, narrow ? 8.0 : 9.5);
      const titleW = Math.min(Math.max(box.w * 0.31, 1.08), Math.min(box.w * 0.50, 1.65));
      const bodyFont = roleBodyFont(preset, narrow ? 7.1 : 8.5);
      const titleTextW = Math.max(0.30, titleW - pad);
      const bodyTextW = Math.max(0.30, box.w - titleW - pad - 0.08);
      const titleTextH = Math.min(
        Math.max(0.26, box.h - 0.08),
        Math.max(0.32, estimateTextHeight(titleText, titleFont, titleTextW, 1.16) + 0.16),
      );
      const bodyTextH = Math.min(
        Math.max(0.26, box.h - 0.08),
        Math.max(0.32, estimateTextHeight(bodyText, bodyFont, bodyTextW, 1.18) + 0.16),
      );
      slide.addText(titleText, textOpts({
        x: box.x + pad, y: box.y + Math.max(0.04, (box.h - titleTextH) / 2),
        w: titleTextW, h: titleTextH,
        fontFace: preset.font_heading, fontSize: titleFont,
        bold: true, color: accent, valign: 'middle', fit: 'shrink',
      }));
      slide.addText(bodyText, textOpts({
        x: box.x + titleW + 0.08,
        y: box.y + Math.max(0.04, (box.h - bodyTextH) / 2),
        w: bodyTextW, h: bodyTextH,
        fontFace: preset.font_body,
        fontSize: bodyFont,
        color: preset.text || preset.text_primary || '0F172A', valign: 'middle', fit: 'shrink',
      }));
    } else {
      const titleH = Math.min(0.48, Math.max(0.32, box.h * 0.26));
      const titleFont = roleBodyFont(preset, narrow ? 8.8 : (dense ? 10.5 : 12.5));
      const sequenceW = Math.min(0.38, Math.max(0.28, box.w * 0.16));
      slide.addText(String(index + 1).padStart(2, '0'), textOpts({
        x: box.x + box.w - pad - sequenceW, y: box.y + pad,
        w: sequenceW, h: Math.max(0.30, titleH),
        fontFace: preset.font_heading, fontSize: titleFont,
        bold: true, color: accent, align: 'right', fit: 'shrink',
      }));
      slide.addText(safeText(item.title, `Gate ${index + 1}`), textOpts({
        x: box.x + pad, y: box.y + pad,
        w: Math.max(0.30, box.w - pad * 2 - sequenceW - 0.08),
        h: titleH,
        fontFace: preset.font_heading, fontSize: titleFont,
        bold: true, color: accent, fit: 'shrink',
      }));
      const bodyY = box.y + pad + titleH + 0.10;
      const bodyText = safeText(item.body || item.text);
      const bodyFont = roleBodyFont(preset, narrow ? 7.3 : (dense ? 8.3 : 9.5));
      const bodyW = Math.max(0.30, box.w - pad * 2);
      const availableBodyH = Math.max(0.18, box.y + box.h - bodyY - pad);
      const bodyH = Math.min(
        Math.max(0.28, estimateTextHeight(bodyText, bodyFont, bodyW, 1.18) + 0.10),
        availableBodyH,
      );
      slide.addText(bodyText, textOpts({
        x: box.x + pad, y: bodyY, w: bodyW,
        h: bodyH,
        fontFace: preset.font_body,
        fontSize: bodyFont,
        color: preset.text || preset.text_primary || '0F172A', fit: 'shrink',
      }));
    }
  });
  const commitment = safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway);
  const commitmentBox = roleSlot(contract, 'commitment', body);
  if (commitment && commitmentBox) {
    slide.addShape('rect', shapeOpts({
      x: commitmentBox.x, y: commitmentBox.y, w: commitmentBox.w, h: commitmentBox.h,
      fill: { color: preset.bg_dark || '0F172A' },
      line: { color: preset.accent_primary, width: 0.65 },
    }));
    const commitmentFont = roleBodyFont(
      preset,
      commitmentBox.w < 1.5 ? 7.6 : (commitmentBox.h < 0.7 ? 9.0 : 11.2),
    );
    const commitmentW = Math.max(0.28, commitmentBox.w - 0.24);
    const commitmentH = Math.min(
      Math.max(0.28, commitmentBox.h - 0.12),
      Math.max(0.34, estimateTextHeight(commitment, commitmentFont, commitmentW, 1.18) + 0.18),
    );
    slide.addText(commitment, textOpts({
      x: commitmentBox.x + 0.12,
      y: commitmentBox.y + Math.max(0.06, (commitmentBox.h - commitmentH) / 2),
      w: commitmentW, h: commitmentH,
      fontFace: preset.font_heading,
      fontSize: commitmentFont,
      bold: true, color: 'FFFFFF', valign: 'middle', align: 'center', fit: 'shrink',
    }));
    slideData.__roleContractConsumesSummary = true;
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'decision',
    [
      ...quadrants.slice(0, 4).map((_item, index) => `decision_${index}`),
      ...(commitment && commitmentBox ? ['commitment'] : []),
    ],
  );
}

function renderMatrix(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const quadrants = Array.isArray(slideData.quadrants) ? slideData.quadrants.slice(0, 4) : [];
  while (quadrants.length < 4) {
    quadrants.push({ title: `Quadrant ${quadrants.length + 1}`, body: '' });
  }

  const referencesContract = roleContract(preset, slideData, 'references');
  if (referencesContract) {
    const sourceRecords = quadrants
      .map((item, index) => ({
        id: `S${index + 1}`,
        source: safeText(item.title),
        note: safeText(item.body || item.text),
      }))
      .filter((item) => item.source && item.note);
    for (const item of [
      ...(Array.isArray(slideData.sources) ? slideData.sources : []),
      ...(Array.isArray(slideData.refs) ? slideData.refs : []),
    ]) {
      const text = safeText(item);
      if (text && !sourceRecords.some((entry) => entry.source.toLowerCase() === text.toLowerCase())) {
        sourceRecords.push({ id: `S${sourceRecords.length + 1}`, source: text, note: 'Supporting evidence' });
      }
    }
    renderTableContract(
      slide,
      slideData,
      preset,
      header,
      {
        title: safeText(slideData.title, 'Sources'),
        headers: ['ID', 'Source / basis', 'Use in deck'],
        rows: sourceRecords.slice(0, 10).map((item) => [item.id, item.source, item.note]),
        caption: safeText(slideData.summary_callout || slideData.subtitle),
        footnotes: [],
        table_style: 'references',
      },
      true,
      referencesContract,
    );
    return;
  }

  const decisionContract = roleContract(preset, slideData, 'decision');
  if (decisionContract) {
    renderDecisionContract(slide, slideData, preset, header, decisionContract, quadrants);
    return;
  }

  const gutter = 0.30;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const cardW = (usableW - gutter) / 2;
  const topY = header.contentTop + 0.20;
  const hasSummary = Boolean(safeText(slideData.summary_callout || slideData.key_summary || slideData.takeaway));
  const usableH = SLIDE_H - topY - 0.65 - (hasSummary ? 0.72 : 0);
  const cardH = (usableH - gutter) / 2;
  const iconPaths = Array.isArray(slideData.__iconPaths) ? slideData.__iconPaths : [];

  const matrixMode = String(slideData.matrix_mode || preset.matrix_mode || 'cards')
    .trim()
    .toLowerCase();
  if (matrixMode === 'open-quadrants') {
    renderMatrixOpenQuadrants(slide, slideData, preset, header, quadrants, iconPaths);
    return;
  }

  quadrants.forEach((q, idx) => {
    const row = Math.floor(idx / 2);
    const col = idx % 2;
    const accentKey = idx % 2 === 0 ? 'accent_primary' : 'accent_secondary';
    const accentColor = preset[accentKey] || preset.accent_primary;
    const cx = MARGIN_X + col * (cardW + gutter);
    const cy = topY + row * (cardH + gutter);
    const railH = 0.08;

    // Card body
    slide.addShape('rect', shapeOpts({
      x: cx, y: cy,
      w: cardW, h: cardH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'E5E7EB', width: 1 },
    }));
    // Top rail
    slide.addShape('rect', shapeOpts({
      x: cx, y: cy,
      w: cardW, h: railH,
      fill: { color: accentColor },
      line: { color: accentColor, width: 0 },
    }));

    // Optional icon in top-right corner of the quadrant.
    const iconPath = iconPaths[idx];
    const iconSize = 0.40;
    const hasIcon = iconPath && fs.existsSync(iconPath);
    if (hasIcon) {
      slide.addImage({
        path: iconPath,
        x: cx + cardW - iconSize - 0.20,
        y: cy + railH + 0.14,
        w: iconSize,
        h: iconSize,
      });
    }

    const title = String(q.title || '').trim() || `Quadrant ${idx + 1}`;
    const body = String(q.body || q.text || '').trim();

    slide.addText(title, textOpts({
      x: cx + 0.18, y: cy + railH + 0.10,
      w: cardW - 0.36, h: 0.44,
      fontFace: preset.font_title,
      fontSize: 18,
      bold: true,
      color: preset.text_primary,
    }));
    if (body) {
      const bodyLines = body.split(/\n|(?<=\.)\s+/)
        .map((s) => s.trim())
        .filter((s) => s)
        .slice(0, 4);
      const bodyY = cy + railH + 0.68;
      const availableBodyH = Math.max(0.4, cardH - (bodyY - cy) - 0.18);
      const bodyBoxH = Math.min(
        availableBodyH,
        Math.max(0.48, 0.16 + bodyLines.length * 0.22),
      );
      slide.addText(
        bodyLines.map((line, i) => ({
          text: line,
          options: { breakLine: i < bodyLines.length - 1 },
        })),
        textOpts({
          x: cx + 0.18, y: bodyY,
          w: cardW - 0.36, h: bodyBoxH,
          fontFace: preset.font_body,
          fontSize: 12,
          color: preset.text_primary,
          valign: 'top',
          paraSpaceAfter: 4,
        }),
      );
    }
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}


// ---------------------------------------------------------------------------
// Universal summary callout (the rounded "oval" box at the bottom).
// Called by the build_deck_pptxgenjs dispatcher for any variant that
// doesn't already carry its own bottom emphasis.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Flow: slide with title + subtitle on top, diagram image filling the body.
// Triggered when assets.mermaid_source or assets.diagram is present.
// The build script pre-renders .mmd to PNG before calling this.
// ---------------------------------------------------------------------------
function parseEditableMermaidFlow(sourcePath) {
  if (!sourcePath || !fs.existsSync(sourcePath)) return [];
  const source = fs.readFileSync(sourcePath, 'utf8');
  const nodes = [];
  const labels = new Map();
  const addNode = (id, label) => {
    if (!id || labels.has(id)) return;
    const cleaned = safeText(label || id).replace(/^['"]|['"]$/g, '');
    labels.set(id, cleaned || id);
    nodes.push(id);
  };
  const nodePattern = /([A-Za-z0-9_]+)\s*(?:\[([^\]]+)\]|\(([^)]+)\)|\{([^}]+)\})?/g;
  source.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line || /^(?:%%|flowchart\b|graph\b|classDef\b|class\b|style\b|linkStyle\b|subgraph\b|end\b)/i.test(line)) return;
    let match;
    while ((match = nodePattern.exec(line)) !== null) {
      const id = match[1];
      if (/^(?:LR|RL|TB|BT|TD)$/i.test(id)) continue;
      addNode(id, match[2] || match[3] || match[4]);
    }
  });
  return nodes.slice(0, 6).map((id) => labels.get(id));
}

function renderEditableFlowFallback(slide, slideData, preset, header, body) {
  const labels = parseEditableMermaidFlow(slideData.__mermaidSourcePath);
  const stages = labels.length >= 2 ? labels : ['Input', 'Check', 'Route', 'Output'];
  const panelX = MARGIN_X;
  const panelY = body.top;
  const panelW = body.diagramW;
  const panelH = body.height;
  slide.addShape('rect', shapeOpts({
    x: panelX,
    y: panelY,
    w: panelW,
    h: panelH,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line || 'D1D5DB', width: 0.75 },
  }));

  const gap = 0.22;
  const maxNodeW = 1.72;
  const nodeW = Math.min(maxNodeW, (panelW - 0.52 - gap * (stages.length - 1)) / stages.length);
  const usedW = nodeW * stages.length + gap * (stages.length - 1);
  const startX = panelX + Math.max(0.26, (panelW - usedW) / 2);
  const nodeH = 1.22;
  const nodeY = panelY + Math.max(0.52, (panelH - nodeH) / 2);
  stages.forEach((label, idx) => {
    const x = startX + idx * (nodeW + gap);
    const accent = idx % 2 === 0 ? preset.accent_primary : preset.accent_secondary;
    slide.addShape('roundRect', shapeOpts({
      x,
      y: nodeY,
      w: nodeW,
      h: nodeH,
      rectRadius: 0.06,
      fill: { color: preset.bg || 'FFFFFF' },
      line: { color: accent, width: 1.25 },
    }));
    slide.addShape('rect', shapeOpts({
      x,
      y: nodeY,
      w: nodeW,
      h: 0.08,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    slide.addText(String(idx + 1).padStart(2, '0'), textOpts({
      x: x + 0.13,
      y: nodeY + 0.18,
      w: nodeW - 0.26,
      h: 0.20,
      fontFace: preset.font_heading,
      fontSize: 9.5,
      bold: true,
      color: accent,
    }));
    slide.addText(label, textOpts({
      x: x + 0.13,
      y: nodeY + 0.48,
      w: nodeW - 0.26,
      h: 0.46,
      fontFace: preset.font_heading,
      fontSize: 13,
      bold: true,
      color: preset.text || preset.text_primary,
      align: 'center',
      valign: 'mid',
      fit: 'shrink',
    }));
    if (idx < stages.length - 1) {
      slide.addShape('chevron', shapeOpts({
        x: x + nodeW + 0.05,
        y: nodeY + 0.48,
        w: Math.max(0.11, gap - 0.10),
        h: 0.25,
        fill: { color: preset.line || accent },
        line: { color: preset.line || accent, width: 0 },
      }));
    }
  });

  slide.addText('EDITABLE PROCESS MAP', textOpts({
    x: panelX + 0.26,
    y: panelY + 0.22,
    w: panelW - 0.52,
    h: 0.22,
    fontFace: preset.font_heading,
    fontSize: 9.5,
    bold: true,
    color: preset.text_muted,
  }));
}

function renderFlow(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const diagramPath = slideData.__mermaidPath || slideData.__diagramPath;
  // Body region: below header, leaving space for footer/callout.
  const bodyTop = header.contentTop + 0.15;
  const hasFooter = hasFooterChrome(slideData, preset);
  const hasCallout = !!(String(slideData.summary_callout || '').trim());
  const bottomReserve = (hasFooter ? 0.40 : 0.20) + (hasCallout ? 0.75 : 0.0);
  const bodyH = SLIDE_H - bodyTop - bottomReserve;
  const bodyW = SLIDE_W - MARGIN_X * 2;
  const hasRailContent = (
    (Array.isArray(slideData.sidebar_sections) && slideData.sidebar_sections.length > 0) ||
    !!safeText(slideData.body) ||
    normalizeBullets(slideData.bullets).length > 0 ||
    (Array.isArray(slideData.highlights) && slideData.highlights.some((h) => safeText(h)))
  );
  const railGap = 0.28;
  const railW = hasRailContent ? 2.25 : 0;
  const diagramW = hasRailContent ? Math.max(5.4, bodyW - railW - railGap) : bodyW;

  if (diagramPath && fs.existsSync(diagramPath)) {
    try {
      const sized = imageSizingContainLocal(diagramPath, MARGIN_X, bodyTop, diagramW, bodyH);
      slide.addImage(Object.assign({ path: diagramPath }, sized));
    } catch (e) {
      console.warn('[pptxgenjs] flow diagram embed failed; using editable fallback:', e.message);
      renderEditableFlowFallback(slide, slideData, preset, header, {
        top: bodyTop,
        height: bodyH,
        diagramW,
      });
    }
  } else {
    renderEditableFlowFallback(slide, slideData, preset, header, {
      top: bodyTop,
      height: bodyH,
      diagramW,
    });
  }

  if (hasRailContent) {
    const railX = MARGIN_X + diagramW + railGap;
    const sections = normalizeSidebarSections(slideData).slice(0, 3);
    const sectionGap = 0.12;
    const sectionModels = sections.map((section, idx) => {
      const title = safeText(section.title || section.label, idx === 0 ? 'Readout' : `Note ${idx + 1}`);
      const rawLines = sectionBodyLines(section);
      const lines = rawLines.slice(0, rawLines.length <= 2 ? 2 : 3);
      const bodyText = lines.join('\n');
      const estimatedBodyH = estimateTextHeight(bodyText, 12, railW - 0.14, 1.25);
      const desiredH = Math.min(1.45, Math.max(0.74, 0.44 + estimatedBodyH + 0.16));
      return { section, title, lines, desiredH };
    });
    const totalGap = sectionGap * Math.max(0, sectionModels.length - 1);
    const desiredTotal = sectionModels.reduce((sum, model) => sum + model.desiredH, 0);
    const heightScale = desiredTotal + totalGap > bodyH
      ? Math.max(0.72, (bodyH - totalGap) / Math.max(0.01, desiredTotal))
      : 1;
    let y = bodyTop;
    sectionModels.forEach((model, idx) => {
      const sectionH = Math.max(0.54, model.desiredH * heightScale);
      const accent = idx % 2 === 0 ? preset.accent_primary : preset.accent_secondary;
      slide.addShape('rect', shapeOpts({
        x: railX,
        y,
        w: 0.04,
        h: sectionH,
        fill: { color: accent },
        line: { color: accent, width: 0 },
      }));
      slide.addText(model.title, textOpts({
        x: railX + 0.14,
        y,
        w: railW - 0.14,
        h: 0.25,
        fontFace: preset.font_heading,
        fontSize: 11,
        bold: true,
        color: accent,
      }));
      if (model.lines.length) {
        slide.addText(model.lines.join('\n'), textOpts({
          x: railX + 0.14,
          y: y + 0.31,
          w: railW - 0.14,
          h: Math.max(0.35, sectionH - 0.34),
          fontFace: preset.font_body,
          fontSize: 12,
          color: preset.text,
          breakLine: false,
          fit: 'shrink',
          valign: 'top',
        }));
      }
      y += sectionH + sectionGap;
    });
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function normalizeSidebarSections(slideData) {
  const sections = Array.isArray(slideData.sidebar_sections)
    ? slideData.sidebar_sections.filter((s) => s && typeof s === 'object')
    : [];
  if (sections.length) return sections.slice(0, 4);

  const fallback = [];
  const body = safeText(slideData.body);
  const bullets = normalizeBullets(slideData.bullets).map((b) => b.text);
  const highlights = Array.isArray(slideData.highlights)
    ? slideData.highlights.map((h) => safeText(h)).filter(Boolean)
    : [];
  if (body) fallback.push({ title: 'Readout', body });
  if (bullets.length) fallback.push({ title: 'Key results', body: bullets.slice(0, 4) });
  if (highlights.length) fallback.push({ title: 'Interpretation', body: highlights.slice(0, 4) });
  if (!fallback.length) {
    fallback.push({ title: 'Figure note', body: 'Add sidebar_sections to explain the visual.' });
  }
  return fallback.slice(0, 4);
}

function sectionBodyLines(section) {
  const raw = section && section.body;
  if (Array.isArray(raw)) return raw.map((v) => safeText(v)).filter(Boolean);
  const text = safeText(raw || (section && section.text));
  if (!text) return [];
  return text
    .split(/\n|(?<=\.)\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 4);
}

function sidebarPrimaryMetric(slideData) {
  const candidates = [];
  if (slideData.value || slideData.label) {
    candidates.push({ value: slideData.value, label: slideData.label, context: slideData.context });
  }
  ['facts', 'stats', 'evidence'].forEach((key) => {
    if (Array.isArray(slideData[key])) candidates.push(...slideData[key]);
  });
  const first = candidates.find((item) => item && (item.value || item.number || item.metric));
  if (!first) return null;
  return {
    value: safeText(first.value || first.number || first.metric),
    label: safeText(first.label || first.title || first.name, 'Primary readout'),
    context: safeText(first.context || first.note || first.detail),
  };
}

function renderImageSidebarEvidenceMosaic(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const imagePath = slideData.__heroPath || slideData.__generatedImagePath;
  const hasImage = imagePath && fs.existsSync(imagePath);
  const metric = sidebarPrimaryMetric(slideData);
  const sections = normalizeSidebarSections(slideData).slice(0, 2);
  const takeaway = safeText(slideData.takeaway || slideData.interpretation || slideData.summary_callout);
  const caption = safeText(slideData.caption);
  const hasFooter = hasFooterChrome(slideData, preset);
  const contentY = header.contentTop + 0.18;
  const footerReserve = hasFooter ? 0.56 : 0.20;
  const takeawayH = takeaway ? 0.62 : 0;
  const takeawayGap = takeaway ? 0.10 : 0;
  const contentH = SLIDE_H - contentY - footerReserve - takeawayH - takeawayGap;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.34;
  const imageW = usableW * 0.63;
  const railX = MARGIN_X + imageW + gutter;
  const railW = usableW - imageW - gutter;

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: contentY,
    w: imageW,
    h: contentH,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line, width: 0.65 },
  }));
  if (hasImage) {
    const captionReserve = caption ? 0.32 : 0;
    const sized = imageSizingContainLocal(
      imagePath,
      MARGIN_X + 0.06,
      contentY + 0.06,
      imageW - 0.12,
      contentH - 0.12 - captionReserve,
    );
    slide.addImage(Object.assign({ path: imagePath }, sized));
    if (caption) {
      slide.addText(caption, textOpts({
        x: MARGIN_X + 0.12,
        y: contentY + contentH - 0.30,
        w: imageW - 0.24,
        h: 0.22,
        fontFace: preset.font_body,
        fontSize: 8,
        italic: true,
        color: preset.text_muted,
        fit: 'shrink',
      }));
    }
  }

  let railY = contentY;
  if (metric) {
    const metricH = 1.10;
    slide.addShape('rect', shapeOpts({
      x: railX,
      y: railY,
      w: railW,
      h: metricH,
      fill: { color: preset.bg_dark },
      line: { color: preset.bg_dark, width: 0 },
    }));
    slide.addShape('rect', shapeOpts({
      x: railX,
      y: railY,
      w: 0.07,
      h: metricH,
      fill: { color: preset.accent_secondary || preset.accent_primary },
      line: { color: preset.accent_secondary || preset.accent_primary, width: 0 },
    }));
    slide.addText(metric.value, textOpts({
      x: railX + 0.20,
      y: railY + 0.08,
      w: railW - 0.38,
      h: 0.56,
      fontFace: preset.font_title,
      fontSize: metric.value.length > 10 ? 23 : 28,
      bold: true,
      color: 'FFFFFF',
      valign: 'top',
      fit: 'shrink',
    }));
    slide.addText(metric.label, textOpts({
      x: railX + 0.20,
      y: railY + 0.72,
      w: railW - 0.38,
      h: 0.24,
      fontFace: preset.font_body,
      fontSize: 12,
      color: preset.accent_primary,
      valign: 'top',
      fit: 'shrink',
    }));
    railY += metricH + 0.10;
  }

  const sectionGap = 0.08;
  const availableH = Math.max(0.8, contentY + contentH - railY);
  const sectionH = (availableH - sectionGap * Math.max(0, sections.length - 1)) / Math.max(1, sections.length);
  sections.forEach((section, idx) => {
    const y = railY + idx * (sectionH + sectionGap);
    const accent = idx % 2 === 0 ? preset.accent_primary : preset.accent_secondary;
    slide.addShape('rect', shapeOpts({
      x: railX,
      y,
      w: railW,
      h: sectionH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.6 },
    }));
    slide.addShape('rect', shapeOpts({
      x: railX,
      y,
      w: railW,
      h: 0.045,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    const title = safeText(section.title || section.label, `Evidence ${idx + 1}`);
    const lines = sectionBodyLines(section);
    slide.addText([
      {
        text: title,
        options: {
          fontFace: preset.font_heading,
          fontSize: 12,
          bold: true,
          color: accent,
          breakLine: Boolean(lines.length),
          paraSpaceAfter: 5,
        },
      },
      {
        text: lines.join(' '),
        options: {
          fontFace: preset.font_body,
          fontSize: 12,
          color: preset.text,
        },
      },
    ], textOpts({
      x: railX + 0.14,
      y: y + 0.04,
      w: railW - 0.28,
      h: Math.max(0.70, sectionH - 0.08),
      fontFace: preset.font_body,
      fontSize: 12,
      color: preset.text,
      valign: 'top',
      fit: 'shrink',
    }));
  });

  if (takeaway) {
    const y = contentY + contentH + takeawayGap;
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: usableW,
      h: takeawayH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.6 },
    }));
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: 0.08,
      h: takeawayH,
      fill: { color: preset.accent_primary },
      line: { color: preset.accent_primary, width: 0 },
    }));
    slide.addText(takeaway, textOpts({
      x: MARGIN_X + 0.22,
      y: y + 0.08,
      w: usableW - 0.38,
      h: takeawayH - 0.16,
      fontFace: preset.font_body,
      fontSize: 12.5,
      bold: true,
      color: preset.text,
      valign: 'middle',
      fit: 'shrink',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderImageSidebarEditorialAtlas(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const imagePath = slideData.__heroPath || slideData.__generatedImagePath;
  const hasImage = imagePath && fs.existsSync(imagePath);
  const sections = normalizeSidebarSections(slideData).slice(0, 3);
  const caption = safeText(slideData.caption);
  const hasFooter = hasFooterChrome(slideData, preset);
  const contentY = header.contentTop + 0.16;
  const footerReserve = hasFooter ? 0.54 : 0.18;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const totalH = SLIDE_H - contentY - footerReserve;
  const noteH = Math.max(1.05, totalH * 0.28);
  const imageH = totalH - noteH - 0.18;

  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: contentY,
    w: usableW,
    h: imageH,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line, width: 0.6 },
  }));
  if (hasImage) {
    const sized = imageSizingContainLocal(imagePath, MARGIN_X + 0.05, contentY + 0.05, usableW - 0.10, imageH - 0.10);
    slide.addImage(Object.assign({ path: imagePath }, sized));
  }
  if (caption) {
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y: contentY + imageH - 0.34,
      w: usableW,
      h: 0.34,
      fill: { color: preset.bg_dark, transparency: 12 },
      line: { color: preset.bg_dark, transparency: 100, width: 0 },
    }));
    slide.addText(caption, textOpts({
      x: MARGIN_X + 0.14,
      y: contentY + imageH - 0.29,
      w: usableW - 0.28,
      h: 0.22,
      fontFace: preset.font_body,
      fontSize: 8.5,
      color: 'FFFFFF',
      italic: true,
      fit: 'shrink',
    }));
  }

  const noteY = contentY + imageH + 0.18;
  const gap = 0.24;
  const colW = (usableW - gap * 2) / 3;
  sections.forEach((section, idx) => {
    const x = MARGIN_X + idx * (colW + gap);
    const accent = idx === 1 ? preset.accent_secondary : preset.accent_primary;
    slide.addShape('rect', shapeOpts({
      x,
      y: noteY,
      w: colW,
      h: 0.04,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    slide.addText(safeText(section.title || section.label, `View ${idx + 1}`), textOpts({
      x,
      y: noteY + 0.11,
      w: colW,
      h: 0.23,
      fontFace: preset.font_heading,
      fontSize: 11,
      bold: true,
      color: accent,
    }));
    slide.addText(sectionBodyLines(section).join('\n'), textOpts({
      x,
      y: noteY + 0.40,
      w: colW,
      h: Math.max(0.30, noteH - 0.40),
      fontFace: preset.font_body,
      fontSize: 12,
      color: preset.text,
      valign: 'top',
      fit: 'shrink',
    }));
  });

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderImageSidebar(pptx, slide, slideData, preset) {
  const mode = String(slideData.image_sidebar_mode || preset.image_sidebar_mode || 'analysis-rail').trim().toLowerCase();
  if (mode === 'evidence-mosaic') {
    renderImageSidebarEvidenceMosaic(pptx, slide, slideData, preset);
    return;
  }
  if (mode === 'editorial-atlas') {
    renderImageSidebarEditorialAtlas(pptx, slide, slideData, preset);
    return;
  }
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const imagePath = slideData.__heroPath || slideData.__generatedImagePath;
  const hasImage = imagePath && fs.existsSync(imagePath);
  const sections = normalizeSidebarSections(slideData);
  const imageSide = String(slideData.image_side || 'left').trim().toLowerCase() === 'right'
    ? 'right'
    : 'left';

  const contentY = header.contentTop + 0.18;
  const hasFooter = hasFooterChrome(slideData, preset);
  const caption = safeText(slideData.caption);
  const captionH = caption ? (caption.length > 95 ? 0.28 : 0.22) : 0;
  const footerReserve = hasFooter ? 0.55 : 0.18;
  const contentH = SLIDE_H - contentY - footerReserve - captionH - (caption ? 0.10 : 0);
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gutter = 0.30;
  const imageW = hasImage ? usableW * 0.56 : 0;
  const sidebarW = hasImage ? usableW - imageW - gutter : usableW;
  const imageX = imageSide === 'left' ? MARGIN_X : MARGIN_X + sidebarW + gutter;
  const sidebarX = imageSide === 'left' ? MARGIN_X + imageW + gutter : MARGIN_X;

  if (hasImage) {
    slide.addShape('rect', shapeOpts({
      x: imageX,
      y: contentY,
      w: imageW,
      h: contentH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line, width: 0.75 },
    }));
    const sized = imageSizingContainLocal(imagePath, imageX + 0.06, contentY + 0.06, imageW - 0.12, contentH - 0.12);
    slide.addImage(Object.assign({ path: imagePath }, sized));
  }

  const sectionGap = 0.10;
  const sectionCount = Math.max(1, sections.length);
  const sectionH = (contentH - sectionGap * (sectionCount - 1)) / sectionCount;
  const iconPaths = Array.isArray(slideData.__iconPaths) ? slideData.__iconPaths : [];
  sections.forEach((section, idx) => {
    const y = contentY + idx * (sectionH + sectionGap);
    const title = safeText(section.title || section.label, idx === 0 ? 'Figure note' : `Note ${idx + 1}`);
    const lines = sectionBodyLines(section);
    const accent = idx % 2 === 0 ? preset.accent_primary : preset.accent_secondary;

    slide.addShape('rect', shapeOpts({
      x: sidebarX,
      y,
      w: 0.04,
      h: sectionH,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    const iconPath = iconPaths[idx];
    const sectionIconSize = 0.18;
    const hasSectionIcon = iconPath && fs.existsSync(iconPath);
    if (hasSectionIcon) {
      slide.addImage({
        path: iconPath,
        x: sidebarX + 0.14,
        y: y + 0.02,
        w: sectionIconSize,
        h: sectionIconSize,
      });
    }
    slide.addText(title, textOpts({
      x: sidebarX + (hasSectionIcon ? 0.38 : 0.14),
      y,
      w: sidebarW - (hasSectionIcon ? 0.38 : 0.14),
      h: 0.24,
      fontFace: preset.font_heading,
      fontSize: 12,
      bold: true,
      color: accent,
    }));
    if (lines.length) {
      const bodyText = lines.join('\n');
      const requestedBodyFont = Number(slideData.sidebar_body_font_size || 12);
      const bodyFontSize = Number.isFinite(requestedBodyFont) && requestedBodyFont > 0
        ? requestedBodyFont
        : 12;
      const bodyBoxH = Math.min(
        Math.max(0.50, sectionH - 0.32),
        Math.max(0.50, estimateTextHeight(bodyText, bodyFontSize, sidebarW - 0.14, 1.25) + 0.18),
      );
      slide.addText(lines.map((line, i) => ({
        text: line,
        options: {
          bullet: { code: '2022' },
          breakLine: i < lines.length - 1,
        },
      })), textOpts({
        x: sidebarX + 0.14,
        y: y + 0.30,
        w: sidebarW - 0.14,
        h: bodyBoxH,
        fontFace: preset.font_body,
        fontSize: bodyFontSize,
        color: preset.text,
        valign: 'top',
        paraSpaceAfter: 3,
        fit: 'shrink',
      }));
    }
  });

  if (caption) {
    const captionY = hasFooter
      ? Math.min(contentY + contentH + 0.10, SLIDE_H - 0.84)
      : contentY + contentH + 0.10;
    slide.addText(caption, textOpts({
      x: MARGIN_X,
      y: captionY,
      w: usableW,
      h: captionH,
      fontFace: preset.font_body,
      fontSize: 8.5,
      color: preset.text_muted,
      italic: true,
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function normalizeFigures(slideData) {
  const raw = Array.isArray(slideData.figures)
    ? slideData.figures
    : (slideData.assets && Array.isArray(slideData.assets.figures))
      ? slideData.assets.figures
      : [];
  const paths = Array.isArray(slideData.__figurePaths) ? slideData.__figurePaths : [];
  return raw.slice(0, 4).map((item, idx) => {
    const spec = typeof item === 'string' ? { path: item } : (item || {});
    return {
      path: paths[idx] || '',
      label: safeText(spec.label, String.fromCharCode(65 + idx)),
      title: safeText(spec.title || spec.heading),
      caption: safeText(spec.caption || spec.note),
    };
  }).filter((item) => item.path && fs.existsSync(item.path));
}

function normalizeScientificFigureLayout(slideData, preset) {
  const raw = String(
    slideData.figure_layout
      || slideData.scientific_figure_layout
      || slideData.figure_treatment
      || preset.figure_layout
      || '',
  ).trim().toLowerCase();
  const treatment = String(
    slideData.figure_table_treatment
      || preset.figure_table_treatment
      || '',
  ).trim().toLowerCase();
  const value = raw || treatment;
  if (['primary-rail', 'primary_rail', 'figure-rail', 'figure-first-rail'].includes(value)) return 'primary-rail';
  if (['ledger-rail', 'ledger_rail', 'table-first', 'table-first-rail'].includes(value)) return 'ledger-rail';
  if (['strip-readout', 'strip_readout', 'stats-strip', 'metric-strip'].includes(value)) return 'strip-readout';
  return 'panel-grid';
}

function scientificBottomText(slideData) {
  return [
    safeText(slideData.caption || slideData.figure_caption),
    safeText(slideData.interpretation || slideData.takeaway),
  ].filter(Boolean).join('\n');
}

function addScientificFigureBottomText(slide, preset, bottomText, bottomY, bottomH) {
  if (!bottomText || bottomH <= 0) return;
  const usableW = SLIDE_W - MARGIN_X * 2;
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: bottomY,
    w: usableW,
    h: bottomH,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line || 'CBD5E1', width: 0.5 },
  }));
  slide.addText(bottomText, textOpts({
    x: MARGIN_X + 0.14,
    y: bottomY + 0.08,
    w: usableW - 0.28,
    h: Math.max(0.12, bottomH - 0.14),
    fontFace: preset.font_body,
    fontSize: 8.2,
    color: preset.text || preset.text_primary,
    fit: 'shrink',
  }));
}

function renderFigurePanel(slide, preset, figure, x, y, w, h, opts) {
  const options = opts || {};
  const ruleColor = cleanHex(options.ruleColor || preset.bg_dark || preset.accent_primary, '0F172A');
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w,
    h,
    fill: { color: options.fill || preset.surface || 'FFFFFF' },
    line: { color: options.line || preset.line || 'CBD5E1', width: options.lineWidth || 0.75 },
  }));
  if (options.rule !== false) {
    slide.addShape('rect', shapeOpts({
      x,
      y,
      w,
      h: options.ruleH || 0.05,
      fill: { color: ruleColor },
      line: { color: ruleColor, width: 0 },
    }));
  }
  const heading = figure.title ? `${figure.label}. ${figure.title}` : figure.label;
  const titleH = heading ? (options.titleH || 0.22) : 0;
  if (heading) {
    slide.addText(heading, textOpts({
      x: x + 0.08,
      y: y + 0.09,
      w: w - 0.16,
      h: titleH,
      fontFace: preset.font_heading,
      fontSize: options.titleFontSize || 8.5,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
  }
  const showCaption = options.caption !== false && figure.caption;
  const figCaptionH = showCaption ? (figure.caption.length > 90 ? 0.28 : 0.22) : 0;
  const imageY = y + 0.12 + titleH;
  const imageH = Math.max(0.1, h - (imageY - y) - figCaptionH - 0.08);
  const sized = imageSizingContainLocal(figure.path, x + 0.06, imageY, w - 0.12, imageH);
  slide.addImage(Object.assign({ path: figure.path }, sized));
  if (showCaption) {
    slide.addText(figure.caption, textOpts({
      x: x + 0.08,
      y: y + h - figCaptionH - 0.04,
      w: w - 0.16,
      h: figCaptionH,
      fontFace: preset.font_caption || preset.font_body,
      fontSize: 8.2,
      color: preset.text_muted,
      italic: true,
      fit: 'shrink',
    }));
  }
}

function renderScientificPrimaryRail(slide, slideData, preset, figures, metrics) {
  const topY = metrics.topY;
  const usableW = metrics.usableW;
  const gridH = metrics.gridH;
  const bottomText = metrics.bottomText;
  const primaryW = usableW * 0.66;
  const railW = usableW - primaryW - 0.28;
  renderFigurePanel(slide, preset, figures[0], MARGIN_X, topY, primaryW, gridH, {
    titleFontSize: 9.2,
    ruleColor: preset.accent_primary,
  });
  const railX = MARGIN_X + primaryW + 0.28;
  const thumbCount = Math.min(Math.max(0, figures.length - 1), 1);
  const thumbH = thumbCount ? Math.min(0.82, (gridH - 0.24) / 3) : 0;
  for (let idx = 0; idx < thumbCount; idx += 1) {
    renderFigurePanel(slide, preset, figures[idx + 1], railX, topY + idx * (thumbH + 0.12), railW, thumbH, {
      titleFontSize: 8.2,
      ruleColor: idx % 2 ? preset.accent_secondary : preset.accent_primary,
      lineWidth: 0.55,
    });
  }
  const noteY = topY + thumbCount * (thumbH + 0.12);
  const noteH = Math.max(0.96, gridH - (noteY - topY));
  slide.addShape('rect', shapeOpts({
    x: railX,
    y: noteY,
    w: railW,
    h: noteH,
    fill: { color: preset.bg || preset.surface || 'FFFFFF' },
    line: { color: preset.accent_primary || preset.line || 'CBD5E1', width: 0.7 },
  }));
  slide.addText('Interpretation', textOpts({
    x: railX + 0.16,
    y: noteY + 0.14,
    w: railW - 0.32,
    h: 0.28,
    fontFace: preset.font_heading,
    fontSize: 11.2,
    bold: true,
    color: preset.accent_primary || preset.text,
  }));
  slide.addText(truncate(bottomText || figures[0].caption || 'Figure carries the primary proof object.', 165), textOpts({
    x: railX + 0.16,
    y: noteY + 0.56,
    w: railW - 0.32,
    h: Math.max(0.28, noteH - 0.70),
    fontFace: preset.font_body,
    fontSize: 11.2,
    color: preset.text || preset.text_primary,
    fit: 'shrink',
    breakLine: false,
  }));
}

function renderScientificLedgerRail(slide, slideData, preset, figures, metrics) {
  const topY = metrics.topY;
  const usableW = metrics.usableW;
  const gridH = metrics.gridH;
  const ledgerW = Math.min(2.45, usableW * 0.28);
  const figureX = MARGIN_X + ledgerW + 0.28;
  const figureW = usableW - ledgerW - 0.28;
  const rows = figures.slice(0, 3);
  const rowGap = 0.10;
  const rowH = Math.min(0.88, (gridH - rowGap * Math.max(0, rows.length - 1)) / Math.max(1, rows.length));
  rows.forEach((figure, idx) => {
    const y = topY + idx * (rowH + rowGap);
    const accent = idx % 2 ? preset.accent_secondary : preset.accent_primary;
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: ledgerW,
      h: rowH,
      fill: { color: idx % 2 ? preset.bg || 'F8FAFC' : preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.45 },
    }));
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: 0.05,
      h: rowH,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    slide.addText(`${figure.label}. ${truncate(figure.title || 'Evidence panel', 28)}`, textOpts({
      x: MARGIN_X + 0.16,
      y: y + 0.12,
      w: ledgerW - 0.28,
      h: 0.28,
      fontFace: preset.font_heading,
      fontSize: 11.2,
      bold: true,
      color: preset.text || preset.text_primary,
      fit: 'shrink',
    }));
    slide.addText(truncate(figure.caption || 'Generated panel; source stays in caption.', 34), textOpts({
      x: MARGIN_X + 0.16,
      y: y + 0.52,
      w: ledgerW - 0.28,
      h: Math.max(0.20, rowH - 0.52),
      fontFace: preset.font_body,
      fontSize: 8.5,
      color: preset.text_muted,
      fit: 'shrink',
    }));
  });
  renderFigurePanel(slide, preset, figures[0], figureX, topY, figureW, gridH, {
    titleFontSize: 9.0,
    ruleColor: preset.bg_dark || preset.accent_primary,
    caption: false,
  });
}

function renderScientificStripReadout(slide, slideData, preset, figures, metrics) {
  const topY = metrics.topY;
  const usableW = metrics.usableW;
  const gridH = metrics.gridH;
  const bottomText = metrics.bottomText;
  const bandH = Math.min(0.86, Math.max(0.72, gridH * 0.22));
  const mainH = gridH - bandH - 0.16;
  renderFigurePanel(slide, preset, figures[0], MARGIN_X, topY, usableW, mainH, {
    titleFontSize: 9.2,
    ruleColor: preset.accent_primary,
  });
  const bandY = topY + mainH + 0.16;
  const fill = preset.bg_dark || preset.accent_primary || '0F172A';
  slide.addShape('rect', shapeOpts({
    x: MARGIN_X,
    y: bandY,
    w: usableW,
    h: bandH,
    fill: { color: fill },
    line: { color: preset.accent_secondary || preset.accent_primary || '38BDF8', width: 0.65 },
  }));
  slide.addText('FIGURE TRACE', textOpts({
    x: MARGIN_X + 0.18,
    y: bandY + 0.12,
    w: 1.28,
    h: 0.28,
    fontFace: preset.font_heading,
    fontSize: 8.8,
    bold: true,
    color: preset.accent_secondary || preset.accent_primary || '38BDF8',
  }));
  slide.addText(truncate(bottomText || figures[0].caption || 'Primary proof object with source-aware interpretation.', 120), textOpts({
    x: MARGIN_X + 1.58,
    y: bandY + 0.12,
    w: usableW - 3.36,
    h: bandH - 0.24,
    fontFace: preset.font_heading,
    fontSize: 12.2,
    bold: true,
    color: 'FFFFFF',
    valign: 'middle',
    fit: 'shrink',
  }));
  const thumbW = 0.74;
  figures.slice(1, 3).forEach((figure, idx) => {
    const x = MARGIN_X + usableW - (2 - idx) * (thumbW + 0.10);
    const sized = imageSizingContainLocal(figure.path, x, bandY + 0.12, thumbW, bandH - 0.24);
    slide.addImage(Object.assign({ path: figure.path }, sized));
  });
}

function renderScientificFigure(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);
  const figures = normalizeFigures(slideData);
  if (!figures.length) {
    renderImageSidebar(pptx, slide, slideData, preset);
    return;
  }

  const hasFooter = hasFooterChrome(slideData, preset);
  const bottomText = scientificBottomText(slideData);
  const layout = normalizeScientificFigureLayout(slideData, preset);
  const bottomReserve = bottomText && layout === 'panel-grid' ? 0.62 : 0.18;
  const footerReserve = hasFooter ? 0.50 : 0.12;
  const topY = header.contentTop + 0.16;
  const gridH = SLIDE_H - topY - bottomReserve - footerReserve;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const gap = 0.30;
  const count = Math.min(figures.length, 4);

  const metrics = { topY, gridH, usableW, bottomText };
  if (layout === 'primary-rail') {
    renderScientificPrimaryRail(slide, slideData, preset, figures.slice(0, count), metrics);
    addFooter(slide, preset, slideData);
    attachNotes(slide, slideData);
    return;
  }
  if (layout === 'ledger-rail') {
    renderScientificLedgerRail(slide, slideData, preset, figures.slice(0, count), metrics);
    addFooter(slide, preset, slideData);
    attachNotes(slide, slideData);
    return;
  }
  if (layout === 'strip-readout') {
    renderScientificStripReadout(slide, slideData, preset, figures.slice(0, count), metrics);
    addFooter(slide, preset, slideData);
    attachNotes(slide, slideData);
    return;
  }

  const cols = count === 1 ? 1 : 2;
  const rows = count <= 2 ? 1 : 2;
  const panelW = (usableW - gap * (cols - 1)) / cols;
  const panelH = (gridH - gap * (rows - 1)) / rows;

  figures.slice(0, count).forEach((figure, idx) => {
    const row = Math.floor(idx / cols);
    const col = idx % cols;
    const x = MARGIN_X + col * (panelW + gap);
    const y = topY + row * (panelH + gap);
    renderFigurePanel(slide, preset, figure, x, y, panelW, panelH, {
      ruleColor: preset.bg_dark || '0F172A',
    });
  });

  if (bottomText) {
    const bottomY = topY + gridH + 0.12;
    addScientificFigureBottomText(slide, preset, bottomText, bottomY, bottomReserve - 0.16);
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function chartTypeForPayload(pptx, payload) {
  const types = (pptx && pptx.ChartType) || {};
  const raw = String((payload && payload.type) || 'bar').trim().toLowerCase();
  if (raw === 'line') return types.line || 'line';
  if (raw === 'pie' || raw === 'doughnut') return types.pie || 'pie';
  return types.bar || 'bar';
}

function chartColors(payload, preset) {
  const colors = [];
  const addColor = (value) => {
    const raw = String(value || '').replace(/^#/, '').trim();
    if (!/^[0-9a-fA-F]{6}$/.test(raw)) return;
    const color = raw.toUpperCase();
    if (!colors.includes(color)) colors.push(color);
  };
  const options = payload && payload.options && typeof payload.options === 'object'
    ? payload.options
    : {};
  if (Array.isArray(options.chartColors)) {
    options.chartColors.forEach(addColor);
  }
  ['color1', 'color2', 'color3', 'color4'].forEach((key) => addColor(payload && payload[key]));
  [preset.accent_primary, preset.accent_secondary, preset.text_muted, preset.bg_dark]
    .filter((value) => contrastRatio(value, preset.surface || preset.bg || 'FFFFFF') >= 3.0)
    .forEach(addColor);
  return colors.length ? colors : ['0B6B78', '1493A4', '64748B'];
}

function renderChartError(slide, preset, message, x, y, w, h) {
  const bannerH = Math.min(0.68, Math.max(0.46, h * 0.22));
  const bannerY = y + Math.max(0.10, (h - bannerH) / 2);
  slide.addShape('rect', shapeOpts({
    x: x + 0.20,
    y: bannerY,
    w: Math.max(1.0, w - 0.40),
    h: bannerH,
    fill: { color: 'B91C1C' },
    line: { color: '7F1D1D', width: 1 },
  }));
  slide.addText(truncate(message || 'Chart data malformed - see QA report', 110), textOpts({
    x: x + 0.32,
    y: bannerY + 0.08,
    w: Math.max(0.8, w - 0.64),
    h: bannerH - 0.16,
    fontFace: preset.font_heading,
    fontSize: 12.5,
    bold: true,
    color: 'FFFFFF',
    align: 'center',
    valign: 'middle',
    fit: 'shrink',
  }));
}

function renderChartFactCards(slide, preset, facts, x, y, w, h) {
  if (!facts.length) return;
  const gap = 0.30;
  const cols = Math.min(3, facts.length);
  const cardW = (w - gap * (cols - 1)) / cols;
  facts.slice(0, cols).forEach((fact, idx) => {
    const cardX = x + idx * (cardW + gap);
    const accent = preset[fact.accent || (idx % 2 ? 'accent_secondary' : 'accent_primary')] || preset.accent_primary;
    slide.addShape('rect', shapeOpts({
      x: cardX,
      y,
      w: cardW,
      h,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.55 },
    }));
    slide.addShape('rect', shapeOpts({
      x: cardX,
      y,
      w: 0.055,
      h,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    if (fact.value) {
      slide.addText(safeText(fact.value), textOpts({
      x: cardX + 0.15,
      y: y + 0.08,
      w: cardW - 0.28,
      h: 0.32,
      fontFace: preset.font_heading,
      fontSize: 16,
        bold: true,
        color: accent,
        fit: 'shrink',
      }));
    }
    slide.addText(safeText(fact.label || fact.caption), textOpts({
      x: cardX + 0.15,
      y: y + (fact.value ? 0.52 : 0.12),
      w: cardW - 0.28,
      h: Math.max(0.32, fact.caption && fact.value ? 0.42 : h - (fact.value ? 0.62 : 0.22)),
      fontFace: preset.font_heading,
      fontSize: roleBodyFont(preset, 8.6),
      bold: true,
      color: preset.text || preset.text_primary || '0F172A',
      fit: 'shrink',
    }));
    if (fact.caption && fact.value) {
      slide.addText(safeText(fact.caption), textOpts({
        x: cardX + 0.15,
        y: y + 0.85,
        w: cardW - 0.28,
        h: Math.max(0.16, h - 0.91),
        fontFace: preset.font_body,
        fontSize: roleBodyFont(preset, 7.4),
        color: preset.text_muted || '64748B',
        fit: 'shrink',
      }));
    }
  });
}

function renderChartFactRail(slide, preset, facts, x, y, w, h) {
  if (!facts.length) return;
  const gap = 0.16;
  const rows = Math.min(3, facts.length);
  const availableCardH = (h - gap * (rows - 1)) / rows;
  const cardH = Math.min(1.24, Math.max(0.46, availableCardH));
  facts.slice(0, rows).forEach((fact, idx) => {
    const cardY = y + idx * (cardH + gap);
    const accent = preset[fact.accent || (idx % 2 ? 'accent_secondary' : 'accent_primary')] || preset.accent_primary;
    slide.addShape('rect', shapeOpts({
      x,
      y: cardY,
      w,
      h: cardH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.55 },
    }));
    slide.addShape('rect', shapeOpts({
      x,
      y: cardY,
      w: 0.055,
      h: cardH,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    const compact = cardH < 0.88;
    if (fact.value && compact) {
      const valueW = Math.min(Math.max(0.42, w * 0.32), 1.05);
      const compactLabel = [fact.label, fact.caption].map((item) => safeText(item)).filter(Boolean).join(' · ');
      slide.addText(safeText(fact.value), textOpts({
        x: x + 0.16, y: cardY + 0.10, w: valueW, h: Math.max(0.22, cardH - 0.20),
        fontFace: preset.font_heading, fontSize: fact.value.length > 8 ? 10 : 13,
        bold: true, color: accent, valign: 'middle', fit: 'shrink',
      }));
      slide.addText(compactLabel, textOpts({
        x: x + valueW + 0.26, y: cardY + 0.10,
        w: Math.max(0.28, w - valueW - 0.42), h: Math.max(0.32, cardH - 0.20),
        fontFace: preset.font_body, fontSize: roleBodyFont(preset, 8.0), bold: true,
        color: preset.text || preset.text_primary || '0F172A', fit: 'shrink',
      }));
      return;
    }
    if (fact.value) {
      slide.addText(safeText(fact.value), textOpts({
        x: x + 0.16,
        y: cardY + 0.11,
        w: w - 0.32,
        h: 0.30,
        fontFace: preset.font_heading,
        fontSize: roleBodyFont(preset, fact.value.length > 8 ? 13 : 15),
        bold: true,
        color: accent,
        fit: 'shrink',
      }));
    }
    const compactDetail = Boolean(fact.caption);
    const factLabel = compactDetail
      ? [fact.label, fact.caption].map((item) => safeText(item)).filter(Boolean).join(' · ')
      : fact.label || fact.caption || '';
    const labelY = cardY + (fact.value ? 0.52 : 0.14);
    const labelFont = roleBodyFont(preset, 8.2);
    const labelW = w - 0.32;
    const labelH = Math.min(
      Math.max(0.32, cardY + cardH - labelY - 0.08),
      Math.max(0.34, estimateTextHeight(factLabel, labelFont, labelW, 1.18) + 0.16),
    );
    slide.addText(factLabel, textOpts({
      x: x + 0.16,
      y: labelY,
      w: labelW,
      h: labelH,
      fontFace: preset.font_heading,
      fontSize: labelFont,
      bold: true,
      color: preset.text || preset.text_primary || '0F172A',
      fit: 'shrink',
    }));
    if (fact.caption && fact.value && !compactDetail) {
      const captionY = labelY + labelH + 0.08;
      const captionFont = roleBodyFont(preset, 8.0);
      const captionH = Math.max(0.22, cardY + cardH - captionY - 0.08);
      slide.addText(safeText(fact.caption), textOpts({
        x: x + 0.16,
        y: captionY,
        w: w - 0.32,
        h: captionH,
        fontFace: preset.font_body,
        fontSize: captionFont,
        color: preset.text_muted || '64748B',
        fit: 'shrink',
      }));
    }
  });
}

function renderChartHeroStat(slide, preset, fact, note, x, y, w, h) {
  if (!fact || w <= 0 || h <= 0) return;
  const accent = preset[fact.accent || 'accent_primary'] || preset.accent_primary;
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w,
    h,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line || 'CBD5E1', width: 0.55 },
  }));
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w: 0.075,
    h,
    fill: { color: accent },
    line: { color: accent, width: 0 },
  }));
  slide.addText('READOUT', textOpts({
    x: x + 0.22,
    y: y + 0.22,
    w: w - 0.44,
    h: 0.22,
    fontFace: preset.font_heading,
    fontSize: 8.2,
    bold: true,
    color: accent,
    charSpacing: 1.2,
    fit: 'shrink',
  }));
  slide.addText(truncate(fact.value || '', 16), textOpts({
    x: x + 0.22,
    y: y + 0.58,
    w: w - 0.44,
    h: 0.74,
    fontFace: preset.font_heading,
    fontSize: 29,
    bold: true,
    color: preset.text || preset.text_primary || '0F172A',
    fit: 'shrink',
  }));
  slide.addText(truncate(fact.label || fact.caption || '', 72), textOpts({
    x: x + 0.22,
    y: y + 1.50,
    w: w - 0.44,
    h: 0.36,
    fontFace: preset.font_heading,
    fontSize: 9.0,
    bold: true,
    color: preset.text || preset.text_primary || '0F172A',
    fit: 'shrink',
  }));
  const supporting = safeText(fact.caption && fact.caption !== fact.label ? fact.caption : note);
  if (supporting) {
    const supportingH = Math.min(0.72, Math.max(0.30, h - 2.16));
    slide.addText(truncate(supporting, 130), textOpts({
      x: x + 0.22,
      y: y + 2.06,
      w: w - 0.44,
      h: supportingH,
      fontFace: preset.font_body,
      fontSize: 8.0,
      color: preset.text_muted || '64748B',
      fit: 'shrink',
    }));
  }
}

function renderChartThresholdBand(slide, preset, facts, note, x, y, w, h) {
  if (w <= 0 || h <= 0) return;
  const primary = facts && facts.length ? facts[0] : {};
  const secondary = facts && facts.length > 1 ? facts[1] : {};
  const accent = preset[primary.accent || 'accent_primary'] || preset.accent_primary;
  const fill = preset.bg_dark || preset.surface || '0F172A';
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w,
    h,
    fill: { color: fill },
    line: { color: accent, width: 0.65 },
  }));
  slide.addShape('rect', shapeOpts({
    x,
    y,
    w: Math.min(1.8, Math.max(0.9, w * 0.16)),
    h: 0.07,
    fill: { color: accent },
    line: { color: accent, width: 0 },
  }));
  slide.addText('STATUS READOUT', textOpts({
    x: x + 0.22,
    y: y + 0.10,
    w: 1.46,
    h: 0.30,
    fontFace: preset.font_heading,
    fontSize: 8.8,
    bold: true,
    color: accent,
    charSpacing: 0,
    valign: 'middle',
    fit: 'shrink',
  }));
  const noteText = safeText(note);
  const hasPrimaryFact = Boolean(primary.value);
  const hasSecondaryFact = Boolean(secondary.value);
  const noteIsSource = /^source[:\s]/i.test(noteText);
  const primaryLine = primary.value
    ? `${primary.value} ${primary.label || ''}`.trim()
    : noteIsSource
      ? 'Source-linked chart'
      : safeText(noteText, 'Threshold check');
  const secondaryLine = secondary.value
    ? `${secondary.value} ${secondary.label || secondary.caption || ''}`.trim()
    : noteIsSource
      ? noteText
      : hasPrimaryFact
        ? noteText
        : 'QA trace recorded';
  slide.addText(truncate(primaryLine, 64), textOpts({
    x: x + 1.82,
    y: y + 0.12,
    w: Math.max(1.45, w * 0.34),
    h: h - 0.24,
    fontFace: preset.font_heading,
    fontSize: 14.5,
    bold: true,
    color: 'FFFFFF',
    valign: 'middle',
    fit: 'shrink',
  }));
  slide.addText(truncate(secondaryLine, hasSecondaryFact ? 68 : 64), textOpts({
    x: x + Math.max(3.3, w * 0.54),
    y: y + 0.38,
    w: Math.max(1.6, w - Math.max(3.5, w * 0.56) - 0.20),
    h: 0.30,
    fontFace: preset.font_body,
    fontSize: 8.8,
    color: 'E5E7EB',
    valign: 'middle',
    fit: 'shrink',
  }));
}

function renderContractChartInsight(slide, preset, fact, note, box) {
  if (!box) return;
  const surface = preset.surface || 'FFFFFF';
  const bodyColor = firstReadableColor(surface, [preset.text, preset.text_primary, '111111', 'FFFFFF']);
  const mutedColor = firstReadableColor(surface, [preset.text_muted, bodyColor, '111111', 'FFFFFF']);
  const accent = firstReadableColor(surface, [preset[(fact && fact.accent) || 'accent_primary'], preset.accent_primary, preset.accent_secondary, bodyColor], 4.5);
  const value = safeText(fact && fact.value);
  const label = safeText((fact && (fact.label || fact.caption)) || note, 'Key readout');
  slide.addShape('rect', shapeOpts({
    x: box.x, y: box.y, w: box.w, h: box.h,
    fill: { color: surface },
    line: { color: preset.line || 'CBD5E1', width: 0.55 },
  }));
  const horizontalBand = box.w >= 2.20 && box.h < 1.30;
  if (horizontalBand) {
    const bandH = Math.max(0.24, box.h - 0.20);
    const metaH = Math.min(0.34, bandH);
    const metaY = box.y + Math.max(0.10, (box.h - metaH) / 2);
    slide.addText('READOUT', textOpts({
      x: box.x + 0.12, y: metaY, w: 0.70, h: metaH,
      fontFace: preset.font_heading, fontSize: roleMetadataFont(preset, 8.0), bold: true,
      color: accent, valign: 'middle', fit: 'shrink',
      objectName: 'metadata:chart-readout-label',
    }));
    const valueX = box.x + 0.84;
    const valueW = value ? Math.min(0.78, Math.max(0.54, box.w * 0.24)) : 0;
    const labelX = value ? valueX + valueW + 0.10 : box.x + 0.92;
    const labelW = Math.max(0.34, box.x + box.w - labelX - 0.12);
    if (value) {
      const valueH = Math.min(0.52, bandH);
      slide.addText(value, textOpts({
        x: valueX, y: box.y + Math.max(0.10, (box.h - valueH) / 2),
        w: valueW, h: valueH,
        fontFace: preset.font_heading, fontSize: 18, bold: true,
        color: bodyColor, valign: 'middle', fit: 'shrink',
      }));
    }
    const labelFont = roleBodyFont(preset, 8.6);
    const labelH = Math.min(
      bandH,
      Math.max(0.34, estimateTextHeight(label, labelFont, labelW, 1.16) + 0.16),
    );
    slide.addText(label, textOpts({
      x: labelX, y: box.y + Math.max(0.10, (box.h - labelH) / 2), w: labelW, h: labelH,
      fontFace: preset.font_body, fontSize: labelFont,
      color: mutedColor, valign: 'middle', fit: 'shrink',
    }));
    return;
  }
  const readoutH = Math.min(0.34, Math.max(0.30, box.h * 0.18));
  slide.addText('READOUT', textOpts({
    x: box.x + 0.10, y: box.y + 0.10, w: Math.max(0.28, box.w - 0.20),
    h: readoutH, fontFace: preset.font_heading,
    fontSize: roleMetadataFont(preset, box.w < 1.45 ? 8.0 : 8.6),
    bold: true, color: accent, fit: 'shrink',
    objectName: 'metadata:chart-readout-label',
  }));
  const valueY = box.y + 0.10 + readoutH + 0.10;
  const valueH = Math.min(0.70, Math.max(0.52, box.h * 0.24));
  if (value) {
    slide.addText(value, textOpts({
      x: box.x + 0.10, y: valueY,
      w: Math.max(0.28, box.w - 0.20), h: valueH,
      fontFace: preset.font_heading, fontSize: box.w < 1.45 ? 16 : 25,
      bold: true, color: bodyColor, fit: 'shrink',
    }));
  }
  const labelY = value ? valueY + valueH + 0.10 : box.y + 0.10 + readoutH + 0.10;
  const labelFont = roleBodyFont(preset, box.w < 1.45 ? 8.0 : 8.6);
  const labelW = Math.max(0.28, box.w - 0.20);
  const availableLabelH = Math.max(0.22, box.y + box.h - labelY - 0.10);
  const labelH = Math.min(
    Math.max(0.34, estimateTextHeight(label, labelFont, labelW, 1.18) + 0.22),
    availableLabelH,
  );
  slide.addText(label, textOpts({
    x: box.x + 0.10, y: labelY, w: labelW,
    h: labelH,
    fontFace: preset.font_body,
    fontSize: labelFont,
    color: mutedColor, fit: 'shrink',
  }));
}

function renderContractChartFacts(slide, preset, facts, box) {
  if (!box || !facts.length) return;
  const horizontal = box.w >= box.h * 2.2;
  if (!horizontal) {
    renderChartFactRail(slide, preset, facts, box.x, box.y, box.w, box.h);
    return;
  }
  const count = Math.min(3, facts.length);
  const gap = 0.12;
  const width = (box.w - gap * (count - 1)) / count;
  facts.slice(0, count).forEach((fact, index) => {
    const x = box.x + index * (width + gap);
    const accent = preset[fact.accent || (index % 2 ? 'accent_secondary' : 'accent_primary')] || preset.accent_primary;
    slide.addText(`${fact.value || ''} ${fact.label || ''}`.trim(), textOpts({
      x, y: box.y, w: width, h: box.h,
      fontFace: preset.font_heading, fontSize: roleBodyFont(preset, box.h < 0.65 ? 8.0 : 10.5),
      bold: true, color: accent, valign: 'middle', align: 'center', fit: 'shrink',
    }));
  });
}

function chartLeadFact(payload, facts = []) {
  const explicit = facts.find((fact) => (
    safeText(fact && fact.value) || safeText(fact && (fact.label || fact.caption))
  ));
  if (explicit) return explicit;
  let best = null;
  for (const series of (Array.isArray(payload && payload.series) ? payload.series : [])) {
    const labels = Array.isArray(series && series.labels) ? series.labels : [];
    const values = Array.isArray(series && series.values) ? series.values : [];
    values.forEach((rawValue, index) => {
      const value = Number(rawValue);
      if (!Number.isFinite(value)) return;
      if (!best || Math.abs(value) > Math.abs(best.value)) {
        best = {
          value,
          label: safeText(labels[index], safeText(series && series.name, 'Peak value')),
          series: safeText(series && series.name),
        };
      }
    });
  }
  if (!best) {
    return {
      value: '',
      label: safeText(payload && payload.title, 'Priority evidence'),
    };
  }
  const suffix = safeText(
    payload && (payload.unit || payload.value_suffix || (payload.options && payload.options.valueSuffix)),
  );
  const formatted = Number.isInteger(best.value)
    ? best.value.toLocaleString('en-US')
    : best.value.toLocaleString('en-US', { maximumFractionDigits: 2 });
  return {
    value: `${formatted}${suffix}`,
    label: best.series && best.series.toLowerCase() !== best.label.toLowerCase()
      ? `${best.label} · ${best.series}`
      : best.label,
  };
}

function chartAxisBounds(payload, series) {
  const options = payload.options || {};
  const bounds = {};
  for (const key of ['valAxisMinVal', 'valAxisMaxVal', 'valAxisMajorUnit']) {
    if (typeof options[key] === 'number' && Number.isFinite(options[key])) bounds[key] = options[key];
  }
  if (String(payload.type).toLowerCase() === 'bar') {
    const values = series.flatMap((item) => item.values).filter(Number.isFinite);
    if (values.length && values.every((value) => value >= 0) && bounds.valAxisMinVal === undefined) {
      bounds.valAxisMinVal = 0;
    }
    if (values.length && values.every((value) => value <= 0) && bounds.valAxisMaxVal === undefined) {
      bounds.valAxisMaxVal = 0;
    }
  }
  return bounds;
}

function renderChartContract(pptx, slide, slideData, preset, payload, facts, note, contract) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title || payload.title, slideData.subtitle || payload.subtitle, slideData);
  const body = roleBodyBox(header, slideData, preset, { footerReserve: 0.58 });
  const policyLayout = isPolicyPublicDocket(preset, slideData) && safeText(contract.system_id) === 'data-public-impact';
  let chartBox = roleSlot(contract, 'chart', body);
  if (!chartBox) return false;
  let insightBox = roleSlot(contract, 'insight', body);
  let factsBox = roleSlot(contract, 'facts', body);
  let registerBox = roleSlot(contract, 'register', body);
  let readableAdaptation = '';
  const minBody = Number(
    preset && preset.readability_contract && preset.readability_contract.min_body_pt,
  );
  const insightText = `${safeText(facts[0] && facts[0].label)} ${safeText(facts[0] && facts[0].caption)}`.trim();
  const narrowTextSlot = [insightBox, factsBox, registerBox].some((box) => (
    box && (box.w < 2.75 || (box.h < 0.72 && box.w < 4.0))
  ));
  const readableInsightBand = Number.isFinite(minBody)
    && minBody >= 15
    && facts.length > 0
    && ((insightBox || factsBox)
      ? (narrowTextSlot || insightText.length > 24 || (note && !registerBox))
      : true);
  if (policyLayout) {
    const bandH = safeText(note).length > 84 ? 0.98 : 0.82;
    const bandGap = 0.24;
    const insightW = Math.min(3.86, Math.max(3.42, body.w * 0.36));
    chartBox = {
      x: body.x,
      y: body.y,
      w: body.w,
      h: Math.max(1.80, body.h - bandH - bandGap),
    };
    insightBox = {
      x: body.x,
      y: body.y + body.h - bandH,
      w: insightW,
      h: bandH,
    };
    registerBox = {
      x: body.x + insightW + 0.30,
      y: body.y + body.h - bandH,
      w: body.w - insightW - 0.30,
      h: bandH,
    };
    factsBox = null;
    readableAdaptation = 'policy-public-impact-open';
  } else if (readableInsightBand) {
    const bandH = safeText(note).length > 64 ? 1.12 : 0.90;
    const bandGap = 0.30;
    const insightW = Math.min(5.25, Math.max(4.70, body.w * 0.44));
    chartBox = {
      x: body.x,
      y: body.y,
      w: body.w,
      h: Math.max(1.5, body.h - bandH - bandGap),
    };
    insightBox = {
      x: body.x + body.w - insightW,
      y: body.y + body.h - bandH,
      w: insightW,
      h: bandH,
    };
    registerBox = {
      x: body.x,
      y: body.y + body.h - bandH,
      w: Math.max(1.0, body.w - insightW - bandGap),
      h: bandH,
    };
    factsBox = null;
    readableAdaptation = 'readable-chart-insight-band';
  }
  slide.addShape('rect', shapeOpts({
    x: chartBox.x, y: chartBox.y, w: chartBox.w, h: chartBox.h,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line || 'CBD5E1', width: policyLayout ? 0 : 0.6 },
    objectName: policyLayout ? 'role-contract-slot:chart:public-impact-canvas' : undefined,
  }));
  if (payload.__error__ || !Array.isArray(payload.series) || !payload.series.length) {
    renderChartError(slide, preset, payload.__error__ || 'Chart data is unavailable.', chartBox.x, chartBox.y, chartBox.w, chartBox.h);
  } else {
    const series = payload.series.map((item, index) => ({
      name: safeText(item.name, `Series ${index + 1}`),
      labels: Array.isArray(item.labels) ? item.labels.map((label) => safeText(label)) : [],
      values: Array.isArray(item.values) ? item.values.map((value) => Number(value)) : [],
    }));
    const options = payload.options && typeof payload.options === 'object' ? payload.options : {};
    const chartSurface = cleanHex(preset.surface, 'FFFFFF');
    const darkChartSurface = colorLuminance(chartSurface) < 0.24;
    const axisColor = darkChartSurface
      ? firstReadableColor(chartSurface, [preset.text_muted, preset.text, 'CBD5E1', 'FFFFFF'], 4.5)
      : cleanHex(preset.text_muted, '64748B');
    const gridColor = darkChartSurface
      ? firstReadableColor(chartSurface, [preset.line, '64748B', '94A3B8'], 2.0)
      : cleanHex(preset.line, 'CBD5E1');
    const chartOptions = {
      ...chartAxisBounds(payload, series),
      x: chartBox.x + 0.12,
      y: chartBox.y + 0.10,
      w: Math.max(0.50, chartBox.w - 0.24),
      h: Math.max(0.50, chartBox.h - 0.20),
      showLegend: Boolean(options.showLegend ?? (series.length > 1 || String(payload.type).toLowerCase() === 'pie')),
      legendPos: safeText(options.legendPos, 'r'),
      chartColors: chartColors(payload, preset),
      catAxisTitle: safeText(options.catAxisTitle),
      valAxisTitle: safeText(options.valAxisTitle),
      catAxisLabelFontFace: preset.font_body,
      valAxisLabelFontFace: preset.font_body,
      catAxisLabelFontSize: Number(options.catAxisLabelFontSize || roleMetadataFont(preset, 9)),
      valAxisLabelFontSize: Number(options.valAxisLabelFontSize || roleMetadataFont(preset, 9)),
      catAxisLabelColor: axisColor,
      valAxisLabelColor: axisColor,
      catAxisTitleColor: axisColor,
      valAxisTitleColor: axisColor,
      legendColor: axisColor,
      dataLabelColor: axisColor,
      catAxisLineColor: axisColor,
      valAxisLineColor: axisColor,
      valGridLine: { color: gridColor, transparency: 40, size: 0.5 },
      catGridLine: { style: 'none' },
      showValue: Boolean(options.showValue),
      showTitle: false,
      showCatName: false,
      showSerName: false,
      objectName: `Editable chart: ${safeText(slideData.title || payload.title, 'data evidence')}`,
      altText: safeText(
        payload.alt_text || slideData.alt_text,
        `Editable ${safeText(payload.type, 'data')} chart for ${safeText(slideData.title || payload.title, 'the slide')}.`,
      ),
    };
    if (String(payload.type || '').toLowerCase() === 'bar') {
      const categoryCount = Math.max(0, ...series.map((item) => item.labels.length));
      chartOptions.barDir = safeText(options.barDir, policyLayout && categoryCount >= 4 ? 'bar' : 'col');
    }
    slide.addChart(chartTypeForPayload(pptx, payload), series, chartOptions);
  }
  if (policyLayout) {
    const accent = cleanHex(preset.accent_primary, 'C65D3B');
    const secondary = cleanHex(preset.accent_secondary, '2F7D76');
    const text = cleanHex(preset.text || preset.text_primary, '243133');
    const muted = cleanHex(preset.text_muted, '5F6F70');
    const line = cleanHex(preset.line, 'D8E1DD');
    const fact = chartLeadFact(payload, facts);
    const bandY = insightBox ? insightBox.y : body.y + body.h - 0.84;
    slide.addShape('line', shapeOpts({
      x: body.x, y: bandY - 0.08, w: body.w, h: 0,
      line: { color: line, width: 0.75 },
    }));
    if (insightBox) {
      const valueText = safeText(fact.value);
      const valueW = Math.min(
        1.58,
        Math.max(0.94, Math.min(insightBox.w * 0.48, 0.68 + valueText.length * 0.12)),
      );
      slide.addText(valueText, textOpts({
        x: insightBox.x, y: insightBox.y + 0.04, w: valueW, h: insightBox.h - 0.08,
        fontFace: preset.font_heading, fontSize: valueText.length > 8 ? 20 : 26,
        bold: true, color: accent, fit: 'shrink', valign: 'middle',
      }));
      slide.addText(safeText(fact.label || fact.caption, 'Priority evidence'), textOpts({
        x: insightBox.x + valueW + 0.14, y: insightBox.y + 0.04,
        w: Math.max(0.42, insightBox.w - valueW - 0.14), h: insightBox.h - 0.08,
        fontFace: preset.font_heading, fontSize: roleBodyFont(preset, 15.5),
        bold: true, color: text, fit: 'shrink', valign: 'middle',
      }));
    }
    if (registerBox) {
      slide.addShape('rect', shapeOpts({
        x: registerBox.x, y: registerBox.y + 0.08, w: 0.055, h: registerBox.h - 0.16,
        fill: { color: secondary }, line: { color: secondary, width: 0 },
      }));
      slide.addText(note || 'Method, denominator, uncertainty, and interpretation stay visible.', textOpts({
        x: registerBox.x + 0.22, y: registerBox.y + 0.04, w: registerBox.w - 0.22, h: registerBox.h - 0.08,
        fontFace: preset.font_body, fontSize: roleBodyFont(preset, 14.5),
        color: muted, fit: 'shrink', valign: 'middle',
      }));
    }
  } else {
    renderContractChartInsight(slide, preset, facts[0], note, insightBox);
    renderContractChartFacts(slide, preset, facts, factsBox);
  }
  if (registerBox && !policyLayout && note) {
    const registerText = note;
    slide.addShape('rect', shapeOpts({
      x: registerBox.x, y: registerBox.y, w: registerBox.w, h: registerBox.h,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.5 },
    }));
    const registerFont = roleBodyFont(preset, registerBox.h < 0.60 ? 11.0 : 12.0);
    const registerW = Math.max(0.30, registerBox.w - 0.20);
    const availableRegisterH = Math.max(0.18, registerBox.h - 0.12);
    const registerH = Math.min(
      Math.max(0.34, estimateTextHeight(registerText, registerFont, registerW, 1.18) + 0.24),
      availableRegisterH,
    );
    slide.addText(registerText, textOpts({
      x: registerBox.x + 0.10,
      y: registerBox.y + Math.max(0.06, (registerBox.h - registerH) / 2),
      w: registerW, h: registerH,
      fontFace: preset.font_body,
      fontSize: registerFont,
      color: firstReadableColor(preset.surface || 'FFFFFF', [preset.text_muted, preset.text, preset.text_primary, '111111', 'FFFFFF']),
      align: 'left', valign: 'middle', fit: 'shrink',
      objectName: 'support:chart-register',
    }));
  }
  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
  markRoleContractExecution(
    slideData,
    preset,
    'chart',
    [
      'chart',
      ...(insightBox ? ['insight'] : []),
      ...(factsBox ? ['facts'] : []),
      ...(registerBox && note ? ['register'] : []),
    ],
  );
  if (readableAdaptation && slideData.__roleContractExecution) {
    slideData.__roleContractExecution.adaptation = readableAdaptation;
    slideData.__roleContractExecution.source_system_id = safeText(contract.system_id);
  }
  return true;
}

function renderChart(pptx, slide, slideData, preset) {
  const payload = slideData.__chartPayload || (slideData.chart && typeof slideData.chart === 'object' ? slideData.chart : {});
  const facts = normalizeFacts(slideData.facts || slideData.stats || payload.facts).slice(0, 3);
  const note = safeText(slideData.interpretation || slideData.message || slideData.caption || payload.notes);
  const contract = roleContract(preset, slideData, 'chart');
  if (contract && renderChartContract(pptx, slide, slideData, preset, payload, facts, note, contract)) {
    return;
  }
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title || payload.title, slideData.subtitle || payload.subtitle, slideData);
  const dataSystem = roleSystem(preset, slideData, 'data');
  const rawTreatment = String(slideData.chart_treatment || preset.chart_treatment || 'standard').trim().toLowerCase();
  let chartTreatment = [
    'standard',
    'facts-below',
    'facts-right',
    'minimal',
    'hero-stat',
    'threshold-band',
    'sparse-wide',
  ].includes(rawTreatment)
    ? rawTreatment
    : 'standard';
  const roleTreatment = {
    'benchmark-exhibit': 'facts-right',
    'data-executive-exhibit': 'facts-right',
    'assay-readout': 'sparse-wide',
    'data-assay-readout': 'sparse-wide',
    'endpoint-threshold': 'threshold-band',
    'data-clinical-outcomes': 'threshold-band',
    'annotated-evidence': 'minimal',
    'data-annotated-graphic': 'minimal',
    'growth-proof': 'hero-stat',
    'data-unit-economics': 'hero-stat',
    'operating-grid': 'facts-below',
    'data-operations-grid': 'facts-below',
    'distribution-lens': 'minimal',
    'data-public-impact': 'threshold-band',
    'telemetry-canvas': 'facts-right',
    'data-telemetry-canvas': 'facts-right',
  }[dataSystem];
  if (!slideData.chart_treatment && roleTreatment) chartTreatment = roleTreatment;
  const hasFooter = hasFooterChrome(slideData, preset);
  const contentY = header.contentTop + 0.22;
  const usableW = SLIDE_W - MARGIN_X * 2;
  const footerReserve = hasFooter ? 0.68 : 0.20;
  const factsRight = chartTreatment === 'facts-right' && facts.length > 0;
  const heroStat = chartTreatment === 'hero-stat' && facts.length > 0;
  const thresholdBand = chartTreatment === 'threshold-band' && (facts.length > 0 || note);
  const sparseWide = chartTreatment === 'sparse-wide';
  const contextRail = ['annotated-evidence', 'data-annotated-graphic', 'distribution-lens'].includes(dataSystem);
  const showFactCards = facts.length > 0 && !['minimal', 'hero-stat', 'threshold-band', 'sparse-wide'].includes(chartTreatment);
  const noteH = note && !contextRail && (!facts.length || chartTreatment === 'minimal' || sparseWide) ? 0.30 : 0;
  const factH = showFactCards && !factsRight ? 1.15 : 0;
  const bandH = thresholdBand ? 0.74 : 0;
  const roleBandH = ['assay-readout', 'data-assay-readout'].includes(dataSystem) ? 0.46 : 0;
  const gap = factsRight || heroStat ? 0.32 : 0.20;
  const chartH = Math.max(
    chartTreatment === 'facts-below' ? 1.82 : 2.05,
    SLIDE_H - contentY - footerReserve - noteH - factH - bandH - roleBandH
      - (showFactCards && !factsRight ? gap : 0)
      - (thresholdBand ? 0.18 : 0)
      - (note ? 0.10 : 0),
  );
  const chartY = contentY + (sparseWide ? 0.12 : 0);
  const heroW = heroStat ? Math.min(2.45, usableW * 0.28) : 0;
  const railW = factsRight ? (['telemetry-canvas', 'data-telemetry-canvas'].includes(dataSystem) ? 2.32 : 2.15) : 0;
  const sparseInset = sparseWide ? usableW * 0.08 : 0;
  let chartX = heroStat
    ? MARGIN_X + heroW + gap
    : MARGIN_X + sparseInset;
  let chartW = factsRight
    ? usableW - railW - gap
    : usableW - heroW - (heroStat ? gap : 0) - sparseInset * 2;
  const leftContextW = ['annotated-evidence', 'data-annotated-graphic'].includes(dataSystem)
    ? 2.04
    : (dataSystem === 'distribution-lens' ? 1.58 : 0);
  if (leftContextW) {
    chartX += leftContextW + 0.24;
    chartW -= leftContextW + 0.24;
  }

  if (['annotated-evidence', 'data-annotated-graphic', 'distribution-lens'].includes(dataSystem)) {
    const panelX = MARGIN_X;
    const editorialData = ['annotated-evidence', 'data-annotated-graphic'].includes(dataSystem);
    const panelTitle = editorialData ? 'WHAT THE EVIDENCE SAYS' : 'WHO IS AFFECTED';
    const panelBody = note || (editorialData
      ? 'Lead with the observation, then show the exhibit.'
      : 'Read the result by population, place, and baseline.');
    slide.addShape('rect', shapeOpts({
      x: panelX, y: chartY, w: leftContextW, h: chartH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.55 },
    }));
    slide.addShape('rect', shapeOpts({
      x: panelX, y: chartY, w: 0.07, h: chartH,
      fill: { color: preset.accent_primary }, line: { color: preset.accent_primary, width: 0 },
    }));
    slide.addText(panelTitle, textOpts({
      x: panelX + 0.22, y: chartY + 0.24, w: leftContextW - 0.40, h: 0.52,
      fontFace: preset.font_body, fontSize: 12, bold: true,
      color: preset.accent_primary, fit: 'shrink',
    }));
    slide.addText(panelBody, textOpts({
      x: panelX + 0.22, y: chartY + 0.94, w: leftContextW - 0.40, h: Math.max(0.76, chartH - 1.30),
      fontFace: preset.font_heading, fontSize: editorialData ? 13.5 : 12,
      bold: editorialData, color: preset.text || preset.text_primary || '0F172A',
      valign: 'top', fit: 'shrink',
    }));
  }

  if (heroStat) {
    renderChartHeroStat(slide, preset, facts[0], note, MARGIN_X, chartY, heroW, chartH);
  }
  if (sparseWide) {
    slide.addShape('line', shapeOpts({
      x: chartX,
      y: chartY - 0.10,
      w: chartW,
      h: 0,
      line: { color: preset.line || preset.accent_primary || 'CBD5E1', width: 0.65, transparency: 25 },
    }));
  } else {
    slide.addShape('rect', shapeOpts({
      x: chartX,
      y: chartY,
      w: chartW,
      h: chartH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: {
        color: preset.line || 'CBD5E1',
        width: chartTreatment === 'minimal' ? 0.35 : 0.65,
        transparency: chartTreatment === 'minimal' ? 45 : 0,
      },
    }));
  }

  if (payload.__error__ || !Array.isArray(payload.series) || !payload.series.length) {
    renderChartError(
      slide,
      preset,
      payload.__error__ || 'Provide chart data as inline chart JSON or a staged chart:<alias> file.',
      chartX,
      chartY,
      chartW,
      chartH,
    );
  } else {
    const series = payload.series.map((item, idx) => ({
      name: safeText(item.name, `Series ${idx + 1}`),
      labels: Array.isArray(item.labels) ? item.labels.map((label) => safeText(label)) : [],
      values: Array.isArray(item.values) ? item.values.map((value) => Number(value)) : [],
    }));
    const options = payload.options && typeof payload.options === 'object' ? payload.options : {};
    const type = chartTypeForPayload(pptx, payload);
    const chartOptions = {
      ...chartAxisBounds(payload, series),
      x: chartX + (sparseWide ? 0.04 : 0.18),
      y: chartY + 0.14,
      w: chartW - (sparseWide ? 0.08 : 0.36),
      h: chartH - 0.28,
      showLegend: Boolean(options.showLegend ?? (series.length > 1 || String(payload.type).toLowerCase() === 'pie')),
      legendPos: safeText(options.legendPos, 'r'),
      chartColors: chartColors(payload, preset),
      catAxisTitle: safeText(options.catAxisTitle),
      valAxisTitle: safeText(options.valAxisTitle),
      catAxisLabelFontFace: preset.font_body,
      valAxisLabelFontFace: preset.font_body,
      catAxisLabelFontSize: Number(options.catAxisLabelFontSize || 8),
      valAxisLabelFontSize: Number(options.valAxisLabelFontSize || 8),
      valGridLine: { color: cleanHex(preset.line, 'CBD5E1'), transparency: 40, size: 0.5 },
      catGridLine: { style: 'none' },
      showValue: Boolean(options.showValue),
      showTitle: false,
      showCatName: false,
      showSerName: false,
      objectName: `Editable chart: ${safeText(slideData.title || payload.title, 'data evidence')}`,
      altText: safeText(
        payload.alt_text || slideData.alt_text,
        `Editable ${safeText(payload.type, 'data')} chart for ${safeText(slideData.title || payload.title, 'the slide')}.`,
      ),
    };
    if (String(payload.type || '').toLowerCase() === 'bar' && safeText(options.barDir)) {
      chartOptions.barDir = safeText(options.barDir);
    } else if (String(payload.type || '').toLowerCase() === 'bar') {
      chartOptions.barDir = 'col';
    }
    slide.addChart(type, series, chartOptions);
  }

  let cursorY = chartY + chartH + gap;
  if (showFactCards && factsRight) {
    renderChartFactRail(slide, preset, facts, chartX + chartW + gap, chartY, railW, chartH);
  } else if (showFactCards) {
    renderChartFactCards(slide, preset, facts, MARGIN_X, cursorY, usableW, factH);
    cursorY += factH + 0.10;
  }
  if (thresholdBand) {
    renderChartThresholdBand(slide, preset, facts, note, MARGIN_X, cursorY, usableW, bandH);
    cursorY += bandH + 0.10;
  }
  if (note && !contextRail && (!facts.length || chartTreatment === 'minimal' || sparseWide)) {
    slide.addText(note, textOpts({
      x: MARGIN_X,
      y: Math.min(cursorY, SLIDE_H - footerReserve - noteH),
      w: usableW,
      h: noteH,
      fontFace: preset.font_body,
      fontSize: 8.4,
      italic: true,
      color: preset.text_muted || '64748B',
      fit: 'shrink',
    }));
  }

  if (['assay-readout', 'data-assay-readout'].includes(dataSystem)) {
    const y = cursorY + noteH + 0.08;
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X, y, w: usableW, h: 0.32,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'CBD5E1', width: 0.45 },
    }));
    slide.addText('METHOD  |  CONTROL  |  n  |  UNCERTAINTY  |  INTERPRETATION', textOpts({
      x: MARGIN_X + 0.16, y: y + 0.08, w: usableW - 0.32, h: 0.16,
      fontFace: preset.font_body, fontSize: 8.2, bold: true,
      color: preset.text_muted || '64748B', align: 'center', fit: 'shrink',
    }));
  }

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function renderGeneratedImage(pptx, slide, slideData, preset) {
  paintBackground(slide, preset.bg);
  const header = addDarkTitleBar(slide, preset, slideData.title, slideData.subtitle, slideData);

  const imagePath = slideData.__generatedImagePath || slideData.__heroPath;
  const contentY = header.contentTop + 0.24;
  const contentH = SLIDE_H - contentY - 0.56;
  const panelW = 3.05;
  const gutter = 0.28;
  const imageX = MARGIN_X;
  const imageW = SLIDE_W - MARGIN_X * 2 - panelW - gutter;
  const panelX = imageX + imageW + gutter;

  slide.addShape('rect', shapeOpts({
    x: imageX, y: contentY, w: imageW, h: contentH,
    fill: { color: preset.surface || 'FFFFFF' },
    line: { color: preset.line, width: 0.75 },
  }));

  if (imagePath && fs.existsSync(imagePath)) {
    const sized = imageSizingContainLocal(imagePath, imageX + 0.08, contentY + 0.08, imageW - 0.16, contentH - 0.16);
    slide.addImage(Object.assign({ path: imagePath }, sized));
  } else {
    slide.addText('Generated image asset missing. Rebuild with --allow-generated-images or replace this slide.', textOpts({
      x: imageX + 0.35,
      y: contentY + contentH / 2 - 0.25,
      w: imageW - 0.70,
      h: 0.55,
      fontFace: preset.font_body,
      fontSize: 13,
      color: preset.text_muted,
      align: 'center',
      valign: 'middle',
    }));
  }

  slide.addShape('rect', shapeOpts({
    x: panelX, y: contentY, w: panelW, h: contentH,
    fill: { color: preset.bg_dark },
    line: { color: preset.bg_dark, width: 0 },
  }));

  const meta = generatedImageMeta(imagePath, slideData);
  slide.addText('GENERATED VISUAL', textOpts({
    x: panelX + 0.20,
    y: contentY + 0.22,
    w: panelW - 0.40,
    h: 0.28,
    fontFace: preset.font_heading,
    fontSize: 11,
    bold: true,
    color: preset.accent_primary,
  }));

  const details = [
    `Model: ${truncate(safeText(meta.model, 'OpenAI image model'), 56)}`,
    `Purpose: ${truncate(safeText(meta.purpose, 'Concept visual'), 76)}`,
    'Standalone disclosure slide. Delete if source imagery is preferred.',
  ];
  const prompt = safeText(meta.prompt) || safeText(meta.revised_prompt);
  if (prompt) details.push(`Prompt: ${truncate(prompt, 120)}`);

  slide.addText(details.map((line, i) => ({
    text: line,
    options: {
      fontFace: preset.font_body,
      fontSize: i === 0 ? 9 : 8.5,
      color: 'FFFFFF',
      breakLine: i < details.length - 1,
      paraSpaceAfter: 4,
    },
  })), textOpts({
    x: panelX + 0.20,
    y: contentY + 0.62,
    w: panelW - 0.40,
    h: contentH - 0.74,
    fontFace: preset.font_body,
    fontSize: 8.5,
    color: 'FFFFFF',
    valign: 'top',
    fit: 'shrink',
  }));

  addFooter(slide, preset, slideData);
  attachNotes(slide, slideData);
}

function addSummaryCallout(pptx, slide, slideData, preset) {
  const text = String(slideData.summary_callout || slideData.key_summary || slideData.takeaway || '').trim();
  if (!text) return;
  const hasFooter = hasFooterChrome(slideData, preset);
  const mode = String(slideData.summary_callout_mode || preset.summary_callout_mode || '').trim().toLowerCase();
  const labBox = mode === 'lab-box';
  const footerReserve = hasFooter ? 0.40 : 0.36;
  const calloutH = labBox ? 0.44 : 0.62;
  const calloutY = SLIDE_H - footerReserve - calloutH;
  const calloutW = SLIDE_W - MARGIN_X * 2.2;
  const calloutX = MARGIN_X * 1.1;
  const accent = preset.accent_primary || '14B8A6';
  if (labBox) {
    const y = SLIDE_H - FOOTER_H - calloutH - 0.12;
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: SLIDE_W - MARGIN_X * 2,
      h: calloutH,
      fill: { color: preset.surface || 'FFFFFF' },
      line: { color: preset.line || 'D1D5DB', width: 0.55 },
    }));
    slide.addShape('rect', shapeOpts({
      x: MARGIN_X,
      y,
      w: 0.055,
      h: calloutH,
      fill: { color: accent },
      line: { color: accent, width: 0 },
    }));
    slide.addText(text, textOpts({
      x: MARGIN_X + 0.14,
      y: y + 0.06,
      w: SLIDE_W - MARGIN_X * 2 - 0.28,
      h: calloutH - 0.12,
      fontFace: preset.font_body,
      fontSize: text.length > 150 ? 8.2 : 9.2,
      bold: true,
      color: preset.text || preset.text_primary || '0F172A',
      valign: 'middle',
      fit: 'shrink',
    }));
    return;
  }
  slide.addShape('roundRect', shapeOpts({
    x: calloutX, y: calloutY, w: calloutW, h: calloutH,
    fill: { color: accent },
    line: { color: accent, width: 0 },
    rectRadius: 0.22,
  }));
  slide.addText(text, textOpts({
    x: calloutX + 0.25, y: calloutY + 0.06,
    w: calloutW - 0.50, h: calloutH - 0.12,
    fontFace: preset.font_body,
    fontSize: 14,
    bold: true,
    color: 'FFFFFF',
    align: 'center',
    valign: 'middle',
  }));
}


// Exports
// ---------------------------------------------------------------------------

function withReadableDisplayFont(renderer) {
  return (pptx, slide, slideData, preset, ...rest) => {
    const minBody = Number(preset && preset.readability_contract && preset.readability_contract.min_body_pt);
    const defaultMidnightDisplay = preset && preset.style_preset === 'midnight-neon'
      && preset.renderer_role_contract_version === 'renderer_role_contracts_v2'
      && preset.font_heading === 'Inter' && preset.font_title === 'Inter'
      && preset.font_body === 'Inter'
      && Number.isFinite(minBody) && minBody >= 15;
    const resolvedPreset = defaultMidnightDisplay
      ? { ...preset, font_heading: 'Helvetica Neue', font_title: 'Helvetica Neue' }
      : preset;
    return renderer(pptx, slide, slideData, resolvedPreset, ...rest);
  };
}

module.exports = {
  // Canvas constants, exposed so the builder can assert the same layout math.
  SLIDE_W,
  SLIDE_H,
  MARGIN_X,
  HEADER_TOP,
  TITLE_BAR_H,
  CONTENT_TOP,

  renderTitle: withReadableDisplayFont(renderTitle),
  renderSection: withReadableDisplayFont(renderSection),
  renderStandard: withReadableDisplayFont(renderStandard),
  renderCards: withReadableDisplayFont(renderCards),
  renderSplit: withReadableDisplayFont(renderSplit),
  renderTimeline: withReadableDisplayFont(renderTimeline),
  renderStats: withReadableDisplayFont(renderStats),
  renderKpiHero: withReadableDisplayFont(renderKpiHero),
  renderTable: withReadableDisplayFont(renderTable),
  renderLabRunResults: withReadableDisplayFont(renderLabRunResults),
  renderComparison2col: withReadableDisplayFont(renderComparison2col),
  renderMatrix: withReadableDisplayFont(renderMatrix),
  renderFlow: withReadableDisplayFont(renderFlow),
  renderChart: withReadableDisplayFont(renderChart),
  renderImageSidebar: withReadableDisplayFont(renderImageSidebar),
  renderScientificFigure: withReadableDisplayFont(renderScientificFigure),
  renderGeneratedImage: withReadableDisplayFont(renderGeneratedImage),
  addSummaryCallout: withReadableDisplayFont(addSummaryCallout),
};
