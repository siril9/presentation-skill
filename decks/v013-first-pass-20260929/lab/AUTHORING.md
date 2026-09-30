# Lab Authoring Record

Run-01 follow-up: inspected the failed main build and recorded findings in `RUN01_SOURCE_AUDIT.md`; copied historical QA to `run01_qa_snapshot/`. Shared chart fact retention, caption/comparison allocation, and support-font contract defects were sent to Galileo. Source is unchanged; no render was requested. Hold visual approval until the shared fix and next main build.

Status: full original source ready; main owns the release build and measurements. No rendering or finalization until main is ready. No core files, plugin files, shared docs, or older Luna sample touched.

Requested author model: GPT-6.1 Sol. CLI workflow profile: `sol`; `gpt-6.1-sol` was absent from the observed brief help on 2026-09-29. A workflow profile does not switch the running model.

## Failures To Prevent

- Counting technical wells as independent lots would overstate evidence.
- An invented 85% cutoff must not become a release specification.
- A mean alone can hide failed lots; keep individual ratios and 0/3, 3/3, 1/3.
- Retention can be misread as shelf life or compatibility; preserve the visible exclusions.
- Monochrome must retain legibility and labelled status without relying on red/green.
- New content QA may expose omitted captions; repair geometry, not delete warnings.

## Original Outline And Design

Audience: assay-development scientists. Decision: select a candidate for confirmation, not release it.

Selected brief candidate: `lab-report` + `scientific-evidence-plate`. The brief readability contract is copied verbatim into `outline.json`. Quiet report pages, plain black headings, white evidence fields, a thin source footer, and native editable objects. `lab_monochrome_v1` is selected; chart colors and rules are explicitly black. Its unused secondary risk token must not introduce decorative color during final visual review.

1. Question: enzyme storage, 14-day synthetic screen; report opener.
2. Method: sample-unit table, not a generic methods card grid.
3. Result: native bar chart with zero baseline, 85% criterion, and disclosed spread.
4. Replicate audit: native lot table with numerator/denominator counts.
5. Interpretation: two open columns separate support from missing measurements.
6. Confirmation: three-stage editable study sequence.
7. Decision: advance glycerol, withhold shelf life; rectangular takeaway.

The second table exists because the mean must be auditable, not to fulfill a role sequence. No stock or generated imagery; all geometry and data objects are native.

## Factual Checklist

Source IDs: SYN-L1 = original invented assay case; SYN-L2 = original unperformed confirmation plan. Neither is an external citation.

- Three independent lots; three formulations; two timepoints; two technical wells: 18 samples and 36 wells, independent n = 3 per condition.
- Residual activity = day-14 rate / matched day-0 rate x 100, at 4 C.
- Means 62%, 91%, 84%; ranges 58-66%, 88-94%, 80-88%.
- Threshold counts 0/3, 3/3, 1/3 at >=85%; glycerol-buffer difference = 29 percentage points, not 29% relative growth.
- Glycerol 5% v/v; trehalose 2% w/v; rate U/mL, with assumed unit definition.
- No confidence interval, significance, compatibility, shelf life, clinical-use, or production-release claim.
- Six new lots in the proposed study are not a power calculation; work is unperformed.

## Commands And Handoff

Source factual check passed using `node decks/v013-first-pass-20260929/lab/check_sources.js`. `factual_check.json` binds the result to the outline and synthetic-data SHA-256 hashes. The check independently recalculates ratios, means, lot counts, well counts, and the percentage-point difference; compares native chart/table values to the source; verifies brief/grammar/readability binding and visible caveats. It does not establish rendered fidelity, geometry, or visual approval. The same scoped checker audits all three sibling decks and writes reports only in their permitted folders.

Run from `/Users/sirilarockiam/CascadeProjects/presentation-skill`. The exact brief request is retained in `quick_deck_agent_brief.json`.

```bash
python3 scripts/present.py brief --topic 'Synthetic enzyme-storage screen' --prompt '<request retained in quick_deck_agent_brief.json>' --slides 7 --style-preset lab-report --profile sol --current-model gpt-6.1-sol --output /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/lab/quick_deck_agent_brief.json
python3 scripts/present.py finalize --outline /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/lab/outline.json --output /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/lab/deck.pptx --qa-dir /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/lab/qa
```

The finalize command is documented, not executed; main runs the shared release build once. Refresh the brief with `--profile gpt-6.1-sol` only after notification that the new alias is integrated. Source facts have been checked. After main builds, inspect every rendered slide and the contact sheet. Preserve every warning and caption through repair; shared core agents own renderer changes.
