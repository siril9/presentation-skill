# presentation-skill v0.1.6 Release Notes

This is the public v0.1 release-line package for the updated v1.1 showcase
workflow.

This release focuses on structured, reproducible, taste-constrained slide generation rather than one-shot slide rendering.

## Why this release is worth showing

- Source-first deck workspaces: `outline.json`, `design_brief.json`, `content_plan.json`, `evidence_plan.json`, and `asset_plan.json` travel with the PPTX.
- Reproducible style decisions: stable style seeds, supported treatment pools, and resolved heading/footer variants.
- Cleaner lab/report slides: tuned 15 pt comparison body copy, compact source-line footers, bottom-right page numbers, readable tables, and evidence-first layouts.
- QA-led delivery: rendered slides are checked for overflow, overlap, geometry, placeholder text, visual warnings, and design warnings.
- Data/artifact path: local CSV/Excel/JSON inputs can become reusable figures, chart specs, and summary tables.

## Release evidence

- Gallery deck: `decks/release-v1.1-showcase-20260619/comparison-gallery/build/presentation-skill-v1-1-release-gallery.pptx`
- Contact-sheet PNGs: `decks/release-v1.1-showcase-20260619/comparison-gallery/assets/comparisons`
- Comparison matrix: native bundled skill vs published GitHub v1 vs local v1.1.
- 13 style cases: Lab report, Risk memo, Startup, Editorial, Policy, Ops dashboard, Clinical exec, Arctic minimal, Midnight neon, Investor, Lavender ops, Terracotta, Editorial minimal.
- The build produced 39 comparison decks plus one gallery deck; the repo keeps
  the gallery deck, PNG contact sheets, manifest, and builder script as the
  compact release evidence.
- The comparison data is synthetic and is intended only to show generation
  behavior across styles.

## Verification

- `npm run check:focused` passed for the release commit and the 15 pt body-copy tune.
- `scripts/build_release_showcase.py` generated the 13-style comparison matrix
  and gallery deck.
- Detailed per-deck counts remain available in
  `release_showcase_manifest.json` for audit/debugging without crowding the
  release notes.
