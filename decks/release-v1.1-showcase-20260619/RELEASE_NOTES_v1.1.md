# presentation-skill v0.1.6 Release Notes

This is the public v0.1 release-line package for the updated v1.1 showcase
workflow.

This release focuses on structured, reproducible, taste-constrained slide generation rather than one-shot slide rendering.

## Why this release is worth showing

- Source-first deck workspaces: `outline.json`, `design_brief.json`, `content_plan.json`, `evidence_plan.json`, and `asset_plan.json` travel with the PPTX.
- Reproducible style decisions: stable style seeds, supported treatment pools, and resolved heading/footer variants.
- Cleaner lab/report slides: compact source-line footers, bottom-right page numbers, readable tables, and evidence-first layouts.
- QA-led delivery: rendered slides are checked for overflow, overlap, geometry, placeholder text, visual warnings, and design warnings.
- Data/artifact path: local CSV/Excel/JSON inputs can become reusable figures, chart specs, and summary tables.

## Release evidence

- Gallery deck: `decks/release-v1.1-showcase-20260619/comparison-gallery/build/presentation-skill-v1-1-release-gallery.pptx`
- Contact-sheet PNGs: `decks/release-v1.1-showcase-20260619/comparison-gallery/assets/comparisons`
- Comparison matrix: native bundled skill vs published GitHub v1 vs local v1.1.
- Native rows are render/inspection baselines; repo QA counts are marked `n/a` because that generator uses a different tool path.
- 13 style cases: Lab report, Risk memo, Startup, Editorial, Policy, Ops dashboard, Clinical exec, Arctic minimal, Midnight neon, Investor, Lavender ops, Terracotta, Editorial minimal.
- The build produced 39 comparison decks plus one gallery deck; the repo keeps
  the gallery deck, PNG contact sheets, manifest, and builder script as the
  compact release evidence.
- Suggested release attachments: gallery deck plus 6-8 PNG contact sheets. The lab, startup, neon, investor, clinical, and ops sheets make the improvement easiest to see quickly.

## QA summary

| Case | Version | Rendered slides | Overflow | Overlap | Geometry warnings | Geometry errors | Visual warnings | Design warnings |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| lab-report-assay | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| lab-report-assay | v1 | 4 | 0 | 0 | 1 | 0 | 0 | 0 |
| lab-report-assay | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| board-risk-memo | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| board-risk-memo | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| board-risk-memo | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| startup-launch | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| startup-launch | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| startup-launch | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| editorial-field-note | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| editorial-field-note | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| editorial-field-note | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| civic-policy | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| civic-policy | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| civic-policy | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| ops-dashboard | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| ops-dashboard | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| ops-dashboard | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| clinical-pathway | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| clinical-pathway | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| clinical-pathway | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| arctic-postmortem | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| arctic-postmortem | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| arctic-postmortem | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| midnight-cyber-triage | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| midnight-cyber-triage | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| midnight-cyber-triage | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| sunset-investor-memo | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| sunset-investor-memo | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| sunset-investor-memo | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| lavender-renewal-ops | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| lavender-renewal-ops | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| lavender-renewal-ops | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| terracotta-membership | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| terracotta-membership | v1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| terracotta-membership | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| editorial-minimal-brief | native | 4 | n/a | n/a | n/a | n/a | n/a | n/a |
| editorial-minimal-brief | v1 | 4 | 0 | 0 | 1 | 0 | 0 | 0 |
| editorial-minimal-brief | v1.1 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |

## HN framing

The strongest honest framing is: a Claude-Code-like workflow for decks. Treat the deck as a software artifact with source files, deterministic builds, visual taste constraints, and QA loops.

Suggested title:

> Show HN: Source-first PowerPoint deck generation for coding agents

Suggested one-sentence hook:

> I built a Codex presentation skill that treats slide decks like software artifacts: source files, style contracts, deterministic builds, rendered previews, and QA for overflow/overlap/layout issues.

## Release checklist before publishing

- Update `package.json` version and changelog if this is being tagged.
- Run `npm run check:focused` before release.
- Include the gallery deck and 2-3 rendered screenshots in the GitHub release.
- Make clear that release-showcase data is synthetic.
