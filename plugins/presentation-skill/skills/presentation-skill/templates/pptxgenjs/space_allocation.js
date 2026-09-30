'use strict';
const { wrapText } = require('./readable_role_layouts.js');

// Bands are in reading order. The parent and the painted children share these
// exact rectangles; a minimum is a gate, never permission to grow over a band.
function reserveBottom(parent, bands, minimum = 1, context = 'Content') {
  const active = bands.filter((band) => band && band.h > 0);
  let bottom = parent.y + parent.h;
  const placed = {};
  for (const band of [...active].reverse()) {
    bottom -= band.h;
    placed[band.id] = { ...parent, y: bottom, h: band.h };
    bottom -= band.gap ?? 0.16;
  }
  const h = bottom - parent.y;
  if (!Number.isFinite(h) || h < minimum - 1e-6) {
    throw new Error(`${context} needs more vertical space (${h.toFixed(2)}in available, ${minimum.toFixed(2)}in required); split the source slide or choose a wider supported layout.`);
  }
  return { content: { ...parent, h }, bands: placed };
}

function requireTextFit(text, box, context) {
  let measured;
  try { measured = wrapText(text, box.w, box.fontSize, box.fontFace, box.bold); }
  catch (error) { throw new Error(`${context}: ${error.message}; choose a wider supported layout or split the source slide.`); }
  if (measured.h > box.h + 1e-6) {
    measured = wrapText(text, box.w, box.fontSize, box.fontFace, box.bold, true);
  }
  if (measured.h > box.h + 1e-6) {
    throw new Error(`${context} needs ${measured.h.toFixed(2)}in at ${box.fontSize}pt; ${box.h.toFixed(2)}in available. Choose a wider supported layout or split the source slide.`);
  }
}

module.exports = { reserveBottom, requireTextFit };
