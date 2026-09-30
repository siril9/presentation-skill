# After six, the library changes

- Author: GPT-6 Sol, 2026-09-23.
- Purpose: original, seven-slide editorial narrative for a fictional library leadership team. Every datum and operating parameter is synthetic; no real public-library demand is asserted.
- Source: `outline.json`. Output: `after_six_library.pptx`. Built only with the repository outline renderer and `scripts/python_runtime.py scripts/present.py finalize`.

## Design choices

The sequence follows the argument: hourly-demand chart, separate service-window evidence table, isolated format-preference number, format comparison, pilot cadence, then a conditional decision. The source selects `editorial-spread` with the current Sol quick-brief readability contract and supported v2 role variants; the isolated KPI is the permitted fallback. Georgia/Calibri typography, an asymmetrical masthead, a single dark numerical pause, and restrained orange/charcoal accents supply the editorial rhythm. The chart, table, and text remain editable. No external images or proprietary assets are used.

## Factual checklist

- Survey scenario denominator: 240 fictional respondents; no real fielding or source exists.
- Q1 asks which one-hour slots could be used, with multiple selections allowed: 5–6 pm 92, 6–7 pm 163, 7–8 pm 151, 8–9 pm 68. Overlap between slots is unknown; selections should not be summed or treated as Q2 answers.
- Q2 separately asks whether 6–8 pm service would be useful. Primary-purpose groups are mutually exclusive: 72 + 48 + 54 + 66 = 240. Yes counts are 56 + 39 + 35 + 37 = 167. Displayed within-group shares round to 78%, 81%, 65%, and 56%.
- Q3 format preference is mutually exclusive: 127 drop-in + 71 workshop + 42 either = 240. Preference is not an attendance forecast.
- One branch, two nights weekly, 6–8 pm, for eight weeks is an illustrative planning assumption, not an authorized program or costed proposal.

## Verification

Command from repository root:

```bash
python3 scripts/python_runtime.py scripts/present.py finalize --outline /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/sol-design-studies-20260923/editorial/outline.json --output /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/sol-design-studies-20260923/editorial/after_six_library.pptx --qa-dir /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/sol-design-studies-20260923/editorial/qa --style-preset editorial-minimal
```

Preflight: 0 errors, 0 warnings. Render: 7/7 slides. I inspected each full-size render after source repairs. Finalize passes: accessibility, geometry, overflow, overlap, placeholders, design, and automated visual review all have 0 findings. PPTX inspection confirms a native chart and a native table. Evidence is retained under `qa/`, including `finalize_receipt.json`, `qa_report.json`, `accessibility.json`, `repair_packet.json`, renders, `visual_review/contact_sheet.jpg`, and the hash-bound visual receipt.

## Blockers

None after applying the source readability contract and v2 editorial grammar. No shared renderer edits were needed.
