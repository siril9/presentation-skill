# After Six: Current Runtime Proof

The original seven-slide Sol editorial design study from 2026-09-23
(v0.12-era authorship) is rebuilt here with the current v0.13.1 runtime.
This is not a newly authored scenario or a reused historical render.

`outline.json` and `AUTHORING.md` are byte-identical copies from
`decks/sol-design-studies-20260923/editorial/`. The copied authoring note describes
the original work and original verification, not this rebuild. No source values,
wording, footer, role, style, or readability requirement was changed.

All counts and operating assumptions are synthetic. Q1 hourly selections overlap
and must not be summed as distinct respondents. Q2 is a separate question:
72 + 48 + 54 + 66 = 240 respondents; 56 + 39 + 35 + 37 = 167 interested.
Q3 format preferences reconcile as 127 + 71 + 42 = 240. Preference is not a
booking forecast. The pilot is an illustration, not authorization or costed advice.
No external images or proprietary assets are used. Repository MIT licensing applies
to this original example; it does not establish real-world factual validity.

## Rebuild

From the repository root:

```bash
.venv/bin/python -B scripts/present.py finalize \
  --outline decks/v013-readme-library-20260930/outline.json \
  --output decks/v013-readme-library-20260930/deck.pptx \
  --qa-dir decks/v013-readme-library-20260930/qa \
  --style-preset editorial-minimal
```

The normal strict finalizer passed with seven rendered slides and zero reported
geometry, overflow, overlap, design, accessibility, or source-fidelity findings.
Its receipt remains untouched: automated finalization is separate from model review.
All seven full-size images were then inspected in this task. The actual judgment
and exact-deck/render binding are `qa/visual_judgment.json` and
`qa/visual_review_receipt.json`; this is one model review, not independent approval.
An independent follow-up found a genuine 4.3438:1 contrast failure in slide 4's
9pt source footer and page number. The original `qa/independent_review.md` remains
unchanged. Before-fix author judgment, official receipt, finalizer receipt, deck,
changed image and independent report are preserved under
`qa/before_footer_contrast_fix/`; the initial author pass missed this issue.
The shared footer now honors the actual KPI background. A source-identical
rebuild retains the six other images byte-for-byte; the changed slide 4 was
reopened full-size. Its footer/page number are now `CBD5E1` on black, 14.1443:1
at the unchanged 9pt size. Current judgment/receipt bind the repaired artifacts;
independent reapproval is still pending. Runtime version remains v0.13.1 with
the revised renderer fingerprint recorded in the current visual judgment.

Native chart data, axis units, table cells, captions, and synthetic footer wording
were also compared with the unchanged outline. Text, chart and table are editable.

The repaired footer has measured 14.1443:1 contrast at its unchanged 9pt size;
the initial footer did not meet 4.5:1. Small source text still requires full-size
viewing. The board is a showcase, not a substitute for reading the full deck.
After any rebuild, re-inspect changed renders and recreate the receipt before
claiming approval. Reproduce the six-slide board with:

```bash
.venv/bin/python -B decks/v013-first-pass-20260929/build_evidence.py --showcase-only
```

`library_current_runtime_proof.zip` contains source, provenance, deck, renders,
and QA/review evidence for separate release packaging. Runtime code is not bundled;
use the matching repository runtime fingerprint in the visual judgment.
