# Authoring record

- Model: GPT-6 Sol.
- Status: synthetic content for a design study, not real assay evidence.
- Source: `outline.json`; S1 is the constructed dataset embedded in that file.
- Design: monochrome lab-report system with a small red rule/limit accent; a protocol ledger, editable longitudinal line chart, two distinct native result tables, and a scoped decision comparison. Heading rules are named deliberately rather than randomized.
- Grammar and readability: explicit supported `scientific-evidence-plate` composition grammar (resolved by the renderer to v2 role contracts); `deck_style.readability_contract` is title 28, body 16, support 13, caption/metadata/footer 9 pt.

## Factual checklist

- Material: three independent reagent lots (A-C), one vial per lot/timepoint, stored at 2-8 C protected from light.
- Timepoints: days 0, 7, 14, 28. Six technical assay wells per lot/timepoint, or 72 assay wells total, excluding blanks. The wells are not independent lot replicates.
- Endpoint: blank-corrected A450, normalized to the corresponding lot's day-0 six-well mean. Day-0 lot means are 100% by definition.
- Predeclared screen: each lot/timepoint mean 90-110% of baseline, condition-level CV <=8%, and blank A450 <=0.10 AU.
- Lot means by day: A = 100/99/97/94%; B = 100/101/98/96%; C = 100/98/96/93%.
- Day-28 CV: A 4.7%, B 5.4%, C 5.1%. Day-28 blanks: A 0.04, B 0.05, C 0.06 AU.
- Maximum CV by day: 3.6/4.1/4.8/5.4%. Maximum blank by day: 0.04/0.05/0.05/0.06 AU.
- Slide 5 maximum CV is the highest lot-level six-well CV at each day, not a CV pooled across lots; each day has 18 assay wells.
- Chart y-axis is 85-105% to show drift; it is not a zero-baseline effect-size comparison. The 90% line is the lower screen limit.
- All 12 lot/timepoint conditions satisfy the synthetic screen. This does not establish shelf life or real-world assay performance.

## Build and QA

Run from the repository root:

```bash
python3 scripts/python_runtime.py scripts/present.py finalize \
  --outline /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/sol-design-studies-20260923/clean-lab/outline.json \
  --output /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/sol-design-studies-20260923/clean-lab/deck.pptx \
  --qa-dir /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/sol-design-studies-20260923/clean-lab/qa

python3 scripts/python_runtime.py \
  decks/sol-design-studies-20260923/clean-lab/assert_native_text.py
```

Results: six slides rendered and visually inspected. Finalize passed with zero
preflight warnings, zero geometry/overflow/overlap findings, zero visual-review
warnings, and zero accessibility findings. The retained QA folder includes
all six slide renders, the contact sheet, machine reports, and a hash-bound
visual judgment receipt. The PPTX package contains one native chart with an
embedded workbook and three native OOXML tables; text remains editable.

Independent-review repair: the native table renderer omitted slide 4 and 5
`table.caption` text even though both captions were present in the outline.
Moved the day-28 denominator/limits and the non-pooled CV qualifier to visible
`interpretation` readouts. `assert_native_text.py` now extracts native slide
text and asserts seven required phrases on slides 4-5; it passes on the rebuilt
PPTX. Both affected full-size renders and all six slides in the contact sheet
were re-inspected after the repair.

Renderer limitations encountered: slide-level subtitles rendered at 12.5 pt,
below the declared 13 pt support-text floor, so the final source omits them.
The line chart did not emit the requested `catAxisTitle` and `valAxisTitle`
options into chart XML; units and normalization are stated in visible slide
text instead. Table `caption` is likewise not emitted by this native-table
path, so decision-relevant notes use rendered readouts. No shared renderer
files were changed.
