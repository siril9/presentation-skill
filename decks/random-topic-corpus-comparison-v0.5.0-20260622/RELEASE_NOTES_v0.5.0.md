# presentation-skill v0.5.0

This release turns the 2,000-record descriptor-only public deck corpus into reproducible deck evidence, not only a catalog.

## What changed

- Expanded the random-topic baseline-vs-corpus comparison builder to 8 synthetic topics and 16 case decks.
- Added a reusable design-catalog selection layer that records primary family, treatment tags, data recipe, and structure intent.
- Added manifest fields that prove corpus-guided outlines carry large-corpus context while baseline outlines do not.
- Added structural sequence signatures so corpus leverage can be checked as slide grammar, not only color/header chrome.
- Added generated data-artifact examples with CSV, editable chart JSON, editable table JSON, artifact manifest, and analysis summary files.
- Added compact rendered contact sheets and a gallery deck for quick visual inspection.
- Kept all evidence publish-safe: synthetic slide content plus descriptor-only corpus metadata; no external decks, screenshots, logos, copied text, or copied geometry.

## Evidence

- Manifest: `decks/random-topic-corpus-comparison-v0.5.0-20260622/manifest.json`
- Gallery deck: `decks/random-topic-corpus-comparison-v0.5.0-20260622/comparison-gallery/build/random-topic-corpus-comparison-gallery.pptx`
- Overview contact sheet: `decks/random-topic-corpus-comparison-v0.5.0-20260622/contact_sheets/all_topics_baseline_vs_corpus.png`
- Pair contact sheets: `contact_sheets/*_baseline_vs_corpus.png`
- Builder: `scripts/build_random_topic_comparison_decks.py`
- Smoke gate: `python3 scripts/run_random_topic_comparison_smoke.py`

## Validation snapshot

- Automated smoke gate: `pass`
- Decks generated: `16`
- Topics generated: `8`
- Unique corpus families: `8` / `8`
- Generated data examples: `4` / `3`
- Corpus-guided cases: `8`
- Outlines with corpus context: `8`
- Warning budget: `0` visual, `0` readability, zero layout blockers
- Pair structural deltas: `8` / `8`
- Nonblank contact sheets: `9` / `9`

## Residual risk

This is corpus-leverage release evidence. It is not a full published-GitHub-baseline audit; that broader comparison remains covered by earlier release evidence galleries.
