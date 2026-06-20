# templates/pptxgenjs

Template modules for the default pptxgenjs renderer
(`scripts/build_deck_pptxgenjs.js`). These modules are plain CommonJS, so
`require()` from the builder pulls them in without a bundler.

The renderer is the default path. `scripts/build_deck.py` remains the fallback
only for legacy or python-pptx-specific behavior that the fast editable path
does not cover.

Lab/report decks use `deck_style.header_variant` to vary the clean content
header without changing the evidence-first layout. Supported values are
`auto`, `left-accent`, `split-rule`, `title-rule`, `side-rail`,
`top-bottom-rule`, and `plain`; the `lab-report` preset defaults to `auto`.
Set `deck_style.style_seed` to a short stable deck-specific string when auto
header variation should be reproducible but not identical across similar lab
reports.
Workspace builds record the resulting per-slide `resolved_treatments` and
`resolved_treatment_summary` in `build/outline_resolved.json`, and readiness
Markdown summarizes the selected header-variant counts before render.
The same `header_mode: "lab-clean"` report chrome can be layered over other
presets when a deck needs a boardroom, editorial, research, or journal palette
but still wants restrained heading/accent-rule rhythm.
Chart slides can use `deck_style.chart_treatment` or slide-level
`chart_treatment` to choose `standard`, `facts-below`, `facts-right`, or
`minimal` chart compositions while keeping chart JSON and captions editable.
`footer_mode: source-line` reserves a compact provenance line for `sources`,
`refs`/`references`, and the page number.
The builder validates enum-like `deck_style` and slide-level treatment values
before writing a `.pptx`, so quick-deck calls fail on misspellings instead of
silently falling back to the default renderer treatment.

## Modules

| File         | Responsibility                                                                 |
| ------------ | ------------------------------------------------------------------------------ |
| `presets.js` | Style presets (palette + font pair) keyed by the skill's canonical preset names. Exports `getPreset(name)` / `listPresets()`. |
| `slides.js`  | One function per slide family, plus the shared chrome (dark title bar, footer, notes). Exports `renderTitle`, `renderSection`, `renderStandard`, `renderCards`, `renderSplit`, `renderTimeline`, `renderStats`, `renderTable`, `renderLabRunResults`, and canvas constants (`SLIDE_W`, `SLIDE_H`, `MARGIN_X`, `HEADER_TOP`, `TITLE_BAR_H`, `CONTENT_TOP`). |

## Slide family map

| Outline shape                  | Renderer          | Notes                                                     |
| ------------------------------ | ----------------- | --------------------------------------------------------- |
| `type: title`                  | `renderTitle`     | Full-bleed dark hero; optional `background_image`.        |
| `type: section`                | `renderSection`   | Dark divider slide with oversized title.                  |
| `content / standard`           | `renderStandard`  | Bullets + optional right-side highlights card.            |
| `content / cards-2`            | `renderCards`     | Two square-edged cards with flush top accent rail.        |
| `content / cards-3`            | `renderCards`     | Three equal-width cards.                                  |
| `content / split`              | `renderSplit`     | Bullets left, dark highlights panel right.                |
| `content / timeline`           | `renderTimeline`  | Milestone sequence with rail, staggered, bands, or chapter-spread treatment. |
| `content / stats`              | `renderStats`     | Oversized fact tiles (value + label + caption + source).  |
| `content / kpi-hero`           | `renderKpiHero`   | Single dark KPI emphasis slide.                           |
| `content / table`              | `renderTable`     | Native editable table.                                    |
| `content / lab-run-results`    | `renderLabRunResults` | Compact editable lab/result dashboard with highlighted tables. |
| `content / comparison-2col`    | `renderComparison2col` | Two-column contrast with optional verdict.          |
| `content / matrix`             | `renderMatrix`    | 2x2 quadrant grid.                                        |
| `content / flow`               | `renderFlow`      | Mermaid/diagram image as the body.                        |
| `content / chart`              | `renderChart`     | Native editable bar/line/pie chart from inline or staged chart JSON. |
| `content / scientific-figure`  | `renderScientificFigure` | Multi-panel academic figure slide with labels/captions. |
| `content / generated-image`    | `renderGeneratedImage` | Standalone generated visual with metadata.           |

Use the Python renderer only for legacy or python-pptx-specific chart behavior
outside the fast path's common bar/line/pie payloads.

## Style presets

All four canonical preset names are exported:

- `executive-clinical`
- `bold-startup-narrative`
- `midnight-neon`
- `data-heavy-boardroom`

Each returns `{ bg, bg_dark, surface, text, text_muted, accent_primary,
accent_secondary, line, font_heading, font_body }`. `surface` and `line` are
provided as convenience tokens that several slide families use but are not
part of the required preset shape.

## House rules (worth repeating)

1. pptxgenjs hex colors never carry `#`. Write `"1493A4"`, never `"#1493A4"`.
2. Never reuse an options object across `addShape` / `addText` calls.
   pptxgenjs mutates what you pass in. Use the factory helpers
   (`textOpts()`, `shapeOpts()`, `cardShadow()`) so every call gets a fresh
   object.
3. Every text box sets `margin: 0` so the baseline math matches the layout
   coordinates exactly.
4. Canvas is `10.0" x 5.625"` (16:9). Side margins 0.5". The dark title
   bar is at least 0.90" tall, but folded titles/subtitles are measured and
   the renderer returns `contentTop`; content must start from that value, not
   from a fixed y-coordinate.
5. Sandwich: dark title slide -> light content body -> dark closing /
   section. Don't bounce between light and dark mid-deck.
