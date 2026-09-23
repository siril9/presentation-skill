'use strict';

// Slicing recipes retain each grammar's reading structure. Dimensions are
// internal to the renderer; leaves grow to fit text before spare space is shared.
const split = (axis, children, weights) => ({ axis, children, weights });
const row = (children, weights) => split('x', children, weights);
const stack = (children, weights) => split('y', children, weights);
const RECIPES = {
  'consulting-answer-pyramid': {
    evidence: { id: 'proof-stack', tree: row([0, stack([1, 2, 3])], [0.34, 0.66]),
      alternatives: [stack([row([0, 1], [0.36, 0.64]), row([2, 3], [0.36, 0.64])])], frame: 'rail', anchor: 0 },
    decision: { id: 'owner-commitments', tree: stack([row([0, 1], [0.54, 0.46]), row([2, 3], [0.54, 0.46])]), frame: 'rail' },
  },
  'scientific-evidence-plate': {
    evidence: { id: 'paired-evidence-plate', tree: stack([row([0, 1]), row([2, 3], [0.42, 0.58])]), frame: 'rule', anchor: 0 },
    decision: { id: 'validation-gates', tree: stack([row([0, 1], [0.46, 0.54]), row([2, 3], [0.58, 0.42])]), frame: 'rule' },
  },
  'clinical-care-pathway': {
    evidence: { id: 'care-pathway', tree: stack([0, 1, 2, 3]),
      alternatives: [row([stack([0, 1]), stack([2, 3])])], frame: 'path' },
    decision: { id: 'care-gates', tree: stack([0, row([1, 2]), 3]),
      alternatives: [row([stack([0, 1]), stack([2, 3])])], frame: 'path' },
  },
  'editorial-spread': {
    evidence: { id: 'evidence-columns', tree: row([stack([0, 1]), stack([2, 3])], [0.54, 0.46]), frame: 'open', anchor: 0 },
    decision: { id: 'decision-columns', tree: row([stack([0, 1], [2, 1]), stack([2, 3], [1, 2])], [0.52, 0.48]), frame: 'open' },
  },
  'investor-thesis-stage': {
    evidence: { id: 'market-proof-stage', tree: stack([0, row([1, 2, 3])], [1, 2]),
      alternatives: [row([stack([0, 1]), stack([2, 3])], [0.48, 0.52])], frame: 'rule', anchor: 0 },
    decision: { id: 'investment-gates', tree: row([stack([0, 1]), stack([2, 3])], [0.46, 0.54]), frame: 'rail', anchor: 0 },
  },
  'operations-grid': {
    evidence: { id: 'signal-board', tree: row([0, stack([row([1, 2]), 3])], [0.30, 0.70]),
      alternatives: [stack([row([0, 1], [0.44, 0.56]), row([2, 3], [0.56, 0.44])])], frame: 'rail', anchor: 0 },
    decision: { id: 'control-actions', tree: stack([row([0, 1]), row([2, 3], [0.38, 0.62])]), frame: 'rail', anchor: 3 },
  },
  'policy-public-docket': {
    evidence: { id: 'public-record', tree: row([stack([0, 1]), stack([2, 3])], [0.44, 0.56]), frame: 'open', anchor: 0 },
    decision: { id: 'implementation-docket', tree: stack([row([0, 1], [0.58, 0.42]), row([2, 3])]), frame: 'open' },
  },
  'technical-telemetry-canvas': {
    evidence: { id: 'signal-trace', tree: stack([row([0, 1], [0.62, 0.38]), row([2, 3])]), frame: 'rule', anchor: 0 },
    decision: { id: 'remediation-gates', tree: row([0, stack([1, 2, 3])], [0.36, 0.64]),
      alternatives: [stack([row([0, 1], [0.40, 0.60]), row([2, 3], [0.60, 0.40])])], frame: 'rail', anchor: 0 },
  },
};

function textWidth(text, fontSize, fontFace, bold = false) {
  // Conservative Latin advance estimates, including room for Georgia and bold
  // faces. Explicit word wrapping avoids reliance on Office's mid-word fallback.
  const serif = /georgia|times|cambria|baskerville/i.test(fontFace || '');
  const lower = { a: 0.556, b: 0.556, c: 0.5, d: 0.556, e: 0.556, f: 0.278, g: 0.556, h: 0.556,
    j: 0.222, k: 0.5, l: 0.222, m: 0.833, n: 0.556, o: 0.556, p: 0.556, q: 0.556,
    r: 0.333, s: 0.5, t: 0.278, u: 0.556, v: 0.5, w: 0.722, x: 0.5, y: 0.5, z: 0.5 };
  const units = Array.from(String(text || '')).reduce((sum, char) => {
    if (/\s/.test(char)) return sum + 0.30;
    if (/[ilI.,:;'!|]/.test(char)) return sum + 0.29;
    if (lower[char]) return sum + lower[char];
    if (/[mwMW@%&]/.test(char)) return sum + 0.91;
    if (/[A-Z]/.test(char)) return sum + 0.69;
    if (/[0-9]/.test(char)) return sum + 0.57;
    if (/[-/()[\]]/.test(char)) return sum + 0.37;
    return sum + (char.charCodeAt(0) > 255 ? 1 : 0.55);
  }, 0);
  return units * fontSize / 72 * (serif ? 1.08 : 1.03) * (bold ? 1.06 : 1);
}

function wrapText(text, width, fontSize, fontFace, bold = false) {
  const lines = [];
  const capacity = Math.max(5, Math.floor(Math.max(0.25, width - 0.12) / Math.max(0.055, fontSize / 72 * 0.52)));
  for (const paragraph of String(text || '').split('\n')) {
    const start = lines.length;
    let line = '';
    for (const word of paragraph.trim().split(/\s+/).filter(Boolean)) {
      if (textWidth(word, fontSize, fontFace, bold) > width - 0.04) {
        throw new Error(`Word '${word}' needs a wider text box at ${fontSize}pt`);
      }
      const next = line ? `${line} ${word}` : word;
      if (line && (textWidth(next, fontSize, fontFace, bold) > width - 0.04 || next.length > capacity)) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line && line.length <= 5 && lines.length > start) {
      const previous = lines[lines.length - 1].split(' ');
      if (previous.length > 1) {
        const balanced = `${previous[previous.length - 1]} ${line}`;
        if (balanced.length <= capacity && textWidth(balanced, fontSize, fontFace, bold) <= width - 0.04) {
          previous.pop();
          lines[lines.length - 1] = previous.join(' ');
          line = balanced;
        }
      }
    }
    if (line) lines.push(line);
  }
  // inventory.py reserves 0.08in baseline + 0.06in frame clearance. Retain
  // that space as well as the visual review's 1.28 line-height estimate.
  return { text: lines.join('\n'), h: lines.length ? lines.length * fontSize / 72 * 1.28 + 0.15 : 0 };
}

function cardContent(item, width, typography, pad, compact = false) {
  const { fontSize, fontHeading, fontBody, valueFont } = typography;
  const innerW = width - pad * 2;
  const label = String(item.label || '');
  const value = String(item.value ?? '');
  const caption = String(item.caption || '');
  const gap = 0.10;
  const texts = [];
  let y = pad;
  const valueW = value ? textWidth(value, valueFont, fontHeading, true) + 0.06 : 0;
  const longestLabel = Math.max(0, ...label.split(/\s+/).map((word) => textWidth(word, fontSize, fontHeading, true)));
  const inline = value && valueW < innerW * 0.36 && innerW - valueW - gap >= longestLabel + 0.10;
  const add = (kind, text, x, top, w, size, face, bold) => {
    if (!text) return 0;
    const wrapped = wrapText(text, w, size, face, bold);
    texts.push({ kind, text: wrapped.text, x, y: top, w, h: wrapped.h, fontSize: size, fontFace: face, bold });
    return wrapped.h;
  };
  if (compact && label && caption) {
    const joined = `${label}: ${caption}`;
    const longest = Math.max(...joined.split(/\s+/).map((word) => textWidth(word, fontSize, fontBody, true)));
    const side = value && valueW < innerW * 0.35 && innerW - valueW - gap > longest + 0.10;
    const metricH = add('value', value, pad, y, side ? valueW + 0.04 : innerW, valueFont, fontHeading, true);
    const bodyX = pad + (side ? valueW + gap : 0);
    const bodyW = innerW - (side ? valueW + gap : 0);
    const bodyY = y + (!side && value ? metricH + 0.09 : 0);
    const wrapped = wrapText(joined, bodyW, fontSize, fontBody, true);
    let offset = 0;
    const runs = [];
    wrapped.text.split('\n').forEach((line, index, lines) => {
      const boldLength = Math.min(line.length, Math.max(0, label.length + 1 - offset));
      if (boldLength) runs.push({ text: line.slice(0, boldLength), options: { bold: true } });
      if (boldLength < line.length) runs.push({ text: line.slice(boldLength), options: { bold: false } });
      if (index < lines.length - 1) runs[runs.length - 1].text += '\n';
      offset += line.length + 1;
    });
    texts.push({ kind: 'body', text: runs, x: bodyX, y: bodyY, w: bodyW, h: wrapped.h,
      fontSize, fontFace: fontBody, bold: false });
    return { texts, h: Math.max(y + metricH, bodyY + wrapped.h) + pad };
  }
  if (innerW >= 6.0 && caption) {
    const metricW = value ? valueW + gap : 0;
    const labelW = Math.max(longestLabel + 0.10, Math.min(2.15, innerW * 0.23));
    const captionW = innerW - metricW - labelW - gap;
    const vh = add('value', value, pad, y, valueW + 0.04, valueFont, fontHeading, true);
    const lh = add('label', label, pad + metricW, y, labelW, fontSize, fontHeading, true);
    const ch = add('caption', caption, pad + metricW + labelW + gap, y, captionW, fontSize, fontBody, false);
    return { texts, h: Math.max(vh, lh, ch) + pad * 2 };
  }
  if (inline) {
    const vh = add('value', value, pad, y, valueW + 0.04, valueFont, fontHeading, true);
    const lh = add('label', label, pad + valueW + gap, y, innerW - valueW - gap, fontSize, fontHeading, true);
    y += Math.max(vh, lh);
  } else {
    y += add('value', value, pad, y, innerW, valueFont, fontHeading, true);
    if (value && label) y += 0.09;
    y += add('label', label, pad, y, innerW, fontSize, fontHeading, true);
  }
  if (caption) {
    if (value || label) y += 0.09;
    y += add('caption', caption, pad, y, innerW, fontSize, fontBody, false);
  }
  return { texts, h: y + pad };
}

function pruneTree(node, count) {
  if (typeof node === 'number') {
    if (node >= count) return null;
    // Extra content is retained in the final branch, never sliced away.
    if (node === 3 && count > 4) return stack(Array.from({ length: count - 3 }, (_, i) => i + 3), Array(count - 3).fill(1));
    return node;
  }
  const entries = node.children.map((child, i) => ({ child: pruneTree(child, count), weight: node.weights?.[i] || 1 }))
    .filter(({ child }) => child !== null);
  if (!entries.length) return null;
  if (entries.length === 1) return entries[0].child;
  return split(node.axis, entries.map(({ child }) => child), entries.map(({ weight }) => weight));
}

function planReadableRole({ grammar, role, variant = 'primary', body, items, fontSize, fontHeading, fontBody }) {
  const recipe = RECIPES[grammar]?.[role];
  if (!recipe) throw new Error(`No readable ${role} recipe for '${grammar}'`);
  if (!items.length) return { recipe: recipe.id, frame: recipe.frame, placements: [] };
  let gap = variant === 'dense' ? 0.10 : 0.16;
  let pad = variant === 'dense' ? 0.06 : 0.08;
  const typography = { fontSize, fontHeading, fontBody, valueFont: role === 'decision' ? fontSize : Math.max(20, fontSize) };
  let tree;
  let compact = false;
  const contentFor = (index, width, valueFont = typography.valueFont) => {
    const type = { ...typography, valueFont };
    if (!compact) return cardContent(items[index], width, type, pad);
    const candidates = [];
    let failure;
    for (const packed of [false, true]) {
      try { candidates.push(cardContent(items[index], width, type, pad, packed)); }
      catch (error) { failure = error; }
    }
    if (!candidates.length) throw failure;
    return candidates.reduce((best, value) => value.h < best.h ? value : best);
  };
  let widthCache = new WeakMap();
  const widths = (node, width) => {
    const cached = widthCache.get(node)?.get(width);
    if (cached) return cached;
    const available = width - gap * (node.children.length - 1);
    const total = node.weights.reduce((sum, weight) => sum + weight, 0);
    let best = node.weights.map((weight) => available * weight / total);
    if (node.children.length === 2) {
      const base = node.weights[0] / total;
      let bestHeight = Infinity;
      for (const delta of [0, -0.04, 0.04, -0.08, 0.08, -0.12, 0.12]) {
        const fraction = Math.max(0.24, Math.min(0.76, base + delta));
        const trial = [available * fraction, available * (1 - fraction)];
        try {
          const height = Math.max(...node.children.map((child, i) => minHeight(child, trial[i])));
          if (height < bestHeight - 0.001) { best = trial; bestHeight = height; }
        } catch (_) { /* A narrower trial may not fit its longest word. */ }
      }
    }
    if (!widthCache.has(node)) widthCache.set(node, new Map());
    widthCache.get(node).set(width, best);
    return best;
  };
  const minHeight = (node, width) => {
    if (typeof node === 'number') return contentFor(node, width).h;
    if (node.axis === 'x') {
      const ws = widths(node, width);
      return Math.max(...node.children.map((child, i) => minHeight(child, ws[i])));
    }
    return node.children.reduce((sum, child) => sum + minHeight(child, width), gap * (node.children.length - 1));
  };
  const placements = [];
  const place = (node, box) => {
    if (typeof node === 'number') {
      const mirrored = variant === 'alternate'
        ? { ...box, x: body.x + body.w - (box.x - body.x) - box.w }
        : box;
      let content = contentFor(node, box.w);
      if (role === 'evidence') {
        for (const size of node === 0 ? [32, 30, 28, 26, 24, 22] : [24, 22]) {
          if (size < typography.valueFont) continue;
          try {
            const larger = contentFor(node, box.w, size);
            if (larger.h <= box.h + 0.001) { content = larger; break; }
          } catch (_) { /* Retain the measured font floor for dense content. */ }
        }
      }
      placements.push({ index: node, box: mirrored, anchor: recipe.anchor === node, frame: recipe.frame,
        texts: content.texts.map((text) => ({ ...text, x: mirrored.x + text.x, y: mirrored.y + text.y })) });
      return;
    }
    if (node.axis === 'x') {
      let x = box.x;
      widths(node, box.w).forEach((w, i) => {
        place(node.children[i], { ...box, x, w });
        x += w + gap;
      });
    } else {
      const minimums = node.children.map((child) => minHeight(child, box.w));
      const spare = Math.max(0, box.h - minimums.reduce((sum, h) => sum + h, 0) - gap * (node.children.length - 1));
      const weightSum = node.weights.reduce((sum, weight) => sum + weight, 0);
      let y = box.y;
      minimums.forEach((minimum, i) => {
        const h = minimum + spare * node.weights[i] / weightSum;
        place(node.children[i], { ...box, y, h });
        y += h + gap;
      });
    }
  };
  let failure;
  const candidates = [recipe.tree, ...(recipe.alternatives || [])].flatMap((tree, recipeIndex) => [
    { tree, recipeIndex, compact: false }, { tree, recipeIndex, compact: true }, { tree, recipeIndex, compact: true, tight: true },
  ]);
  for (let candidate = 0; candidate < candidates.length; candidate += 1) {
    placements.length = 0;
    tree = pruneTree(candidates[candidate].tree, items.length);
    compact = candidates[candidate].compact;
    const { recipeIndex, tight } = candidates[candidate];
    gap = tight ? 0.06 : (variant === 'dense' ? 0.10 : 0.16);
    pad = tight ? 0.04 : (variant === 'dense' ? 0.06 : 0.08);
    widthCache = new WeakMap();
    try {
      const minimum = minHeight(tree, body.w);
      if (minimum > body.h + 0.001) throw new Error(`needs ${minimum.toFixed(2)}in height; available ${body.h.toFixed(2)}in`);
      place(tree, body);
      return { recipe: `${recipe.id}${recipeIndex ? `-expanded-${recipeIndex}` : ''}${compact ? '-inline-copy' : ''}${tight ? '-compact-spacing' : ''}`, frame: recipe.frame,
        placements: placements.sort((a, b) => a.index - b.index) };
    } catch (error) {
      failure = error;
    }
  }
  throw new Error(`Readable ${role} '${grammar}' at ${fontSize}pt: ${failure.message}. Shorten or split this slide; no content was dropped.`);
}

module.exports = { RECIPES, planReadableRole, textWidth, wrapText };
