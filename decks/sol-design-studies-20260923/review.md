# Independent Review: Three Sol Design Studies

## Repair Recheck

Subsequent user review rejected the operations bottom-box layering accepted
below. The shared operations-grid timeline and comparison renderers now reserve
separate callout space above the footer, without changing the outline or dropping
content. The main agent inspected rebuilt slides 4 and 6 at full size: the last
timeline row, option cards, callouts, and footer now have visible gaps. The seven-
slide rebuild passed its QA; the pre-existing KPI contract fallback warning
remains. Focused coverage extends the existing renderer test files, including a
non-timeline compatibility case; no extra runtime QA stage was introduced.

The original review below is retained as the defect history. After Sol repaired
the lab source, the main agent independently inspected the new full-size lab
slides 4 and 5. Slide 4 visibly states the six-well basis and screen limits;
slide 5 states that maximum CV is the highest lot CV, not a pooled CV, and gives
six wells per lot / 18 per day. Both readouts are legible and unobstructed.
The native-text assertion now checks these critical phrases. The lab factual
blocker is closed; all three studies pass the scoped design-study review,
with the operations preflight fallback warning retained. This does not validate
the synthetic scenarios as real evidence. The contact sheets were regenerated
after this repair.

## Original Review

Reviewed the current final `qa/renders/slide-*.jpg` at full size (1800 x 1013),
all three `AUTHORING.md` factual checklists, `outline.json`, QA reports, and
receipts; PPTX text was checked for the suspected lab caption omissions. This
is an internal-consistency and visual review of
synthetic examples, not validation of experimental, survey, or operational
outcomes.

| Deck | Visual and geometry | Factual/source fidelity | Decision |
| --- | --- | --- | --- |
| [Clean lab](clean-lab/deck.pptx) | PASS: six renders legible; no visible clipping, unintended overlap, or low-contrast text | FAIL: a decision-relevant table caveat in source is absent from the rendered deck | **FAIL pending caveat restoration** |
| [Editorial](editorial/after_six_library.pptx) | PASS: seven renders legible; no visible clipping or unintended overlap | PASS: Q1 multi-select, Q2 yes/no, Q3 preference, and the pilot assumption remain distinct | **PASS as a synthetic design study** |
| [Operations](operations/deck.pptx) | PASS: seven renders legible; intended callout layering does not hide text | PASS for internal arithmetic and checklist alignment; synthetic forecasts remain unverified | **PASS as a design study, with a preflight warning** |

## Findings

1. **Clean lab, slide 5: FAIL, missing factual qualifier.**
   [`clean-lab/outline.json`](clean-lab/outline.json) supplies the table caption
   “Worst value across three lots per timepoint. Each day has 18 assay wells;
   maxima are not pooled CVs.” Neither [`slide-05.jpg`](clean-lab/qa/renders/slide-05.jpg)
   nor `ppt/slides/slide5.xml` in [`deck.pptx`](clean-lab/deck.pptx) contains it.
   The visible “Maximum CV” column can therefore be read as a pooled result;
   the source's intended denominator and interpretation are lost. The numeric
   values still match the checklist. This source-to-output omission is not
   detected by the passing [QA receipt](clean-lab/qa/finalize_receipt.json).
2. **Clean lab, slide 4: caption also absent.** The source table caption states
   `n=6` technical wells per lot and restates all three screen limits. It is
   absent from [`slide-04.jpg`](clean-lab/qa/renders/slide-04.jpg) and PPTX slide
   text. The six-well basis and limits are visible earlier on slides 2-3, so
   this is a weaker standalone-slide omission than finding 1, not a numerical
   contradiction.
3. **Operations, slide 2: nonblocking preflight contract warning.** Re-running
   `scripts/preflight.py --outline .../operations/outline.json` returned one
   `role_variant_contract_mismatch`: `role='evidence'` plus `variant='kpi-hero'`
   does not share a v2 geometry contract (zero errors, exit 1). The
   [finalize receipt](operations/qa/finalize_receipt.json) accepts preflight
   return codes 0 and 1 and reports the later QA stage as passed. Its zero
   `qa_counts` do **not** mean zero preflight warnings. The rendered
   [`slide-02.jpg`](operations/qa/renders/slide-02.jpg) is legible and shows the
   intended 18-hour KPI; this remains a contract/fallback limitation, not a
   visual failure.
4. **Editorial question separation: PASS.** [`slide-02.jpg`](editorial/qa/renders/slide-02.jpg)
   identifies Q1 as hourly multi-select, shows 92/163/151/68 responses, and
   says overlap is unknown; these selections are not summed. [`slide-03.jpg`](editorial/qa/renders/slide-03.jpg)
   identifies Q2 as a separate service-window yes/no question: purpose groups
   total 72+48+54+66=240, yes counts total 56+39+35+37=167, and displayed
   shares round correctly to 78/81/65/56%. Slides 4-5 identify Q3 as format
   preference: 127+71+42=240, not attendance. Slide 7 correctly attributes
   167 to Q2 and 127 to Q3. No cross-question denominator substitution found.

## Slide Inspection

| Render | Finding |
| --- | --- |
| [Lab 01](clean-lab/qa/renders/slide-01.jpg) | PASS: title and synthetic-data disclosure have clear hierarchy and contrast; footer visible. |
| [Lab 02](clean-lab/qa/renders/slide-02.jpg) | PASS: protocol ledger is readable; 3 lots x 4 timepoints x 6 wells = 72 matches the checklist. |
| [Lab 03](clean-lab/qa/renders/slide-03.jpg) | PASS: plotted 100/99/97/94, 100/101/98/96, and 100/98/96/93 series match the checklist; 90% limit and 85-105% truncated axis are visibly explained. Chart and interpretation do not collide. |
| [Lab 04](clean-lab/qa/renders/slide-04.jpg) | PASS visually: day-28 values and minimum 93% agree; no clipped cells. Source caption omitted as above. |
| [Lab 05](clean-lab/qa/renders/slide-05.jpg) | PASS visually: day ranges, maximum CVs, and blanks agree; no clipped cells. FAIL factual caveat fidelity as above. |
| [Lab 06](clean-lab/qa/renders/slide-06.jpg) | PASS: decision comparison is structurally distinct from tables; 12/12, 5.4%, and 0.06 AU agree, and no shelf-life claim is made. |
| [Editorial 01](editorial/qa/renders/slide-01.jpg) | PASS: masthead and fictional/synthetic disclosure are clear, with no clipped text. |
| [Editorial 02](editorial/qa/renders/slide-02.jpg) | PASS: readable hourly bar chart; Q1 multi-select and unknown overlap are explicit. |
| [Editorial 03](editorial/qa/renders/slide-03.jpg) | PASS: readable Q2 table; yes counts and rounded within-group shares reconcile; caption explicitly separates Q2 from Q1. |
| [Editorial 04](editorial/qa/renders/slide-04.jpg) | PASS: high-contrast numerical pause; 127/240 is labeled Q3 format preference, not a booking forecast. |
| [Editorial 05](editorial/qa/renders/slide-05.jpg) | PASS: two formats and optional lesson are legible; 127/71/42 reconcile, and verdict layering hides no text. |
| [Editorial 06](editorial/qa/renders/slide-06.jpg) | PASS: W0 preparation and W1-8 pilot sequence are distinct; two 6-8 pm nights weekly is marked an assumption, not authorization. |
| [Editorial 07](editorial/qa/renders/slide-07.jpg) | PASS: Q2 167 and Q3 127 are correctly labeled; continuation depends on observed use, not synthetic survey alone. |
| [Ops 01](operations/qa/renders/slide-01.jpg) | PASS: dark cover has strong contrast and labels the scenario synthetic. |
| [Ops 02](operations/qa/renders/slide-02.jpg) | PASS visually: 18 h is dominant and legible; preflight warning noted above. |
| [Ops 03](operations/qa/renders/slide-03.jpg) | PASS: five queued jobs, held sixth start, first F-04 limit at 18 h, and owners are readable; synthetic-time caption visible. |
| [Ops 04](operations/qa/renders/slide-04.jpg) | PASS: four-phase timeline and hour-12 transfer trigger are readable; dark takeaway overlays only decorative lower chrome, not text. |
| [Ops 05](operations/qa/renders/slide-05.jpg) | PASS: bars show ticket-age 12+26+18+9=65 and risk-first 4+6+9+3=22, so 43 avoided; zero-baseline chart and readout are clear. |
| [Ops 06](operations/qa/renders/slide-06.jpg) | PASS: 5 vs 1 projected excursions, 65 vs 22 pallet-hours, 17 vs 21 travel hours, and 4/7 vs 7/7 loads match the checklist. Four extra travel hours is correct. Bottom verdict overlaps card backgrounds intentionally without covering list text. |
| [Ops 07](operations/qa/renders/slide-07.jpg) | PASS: action register assigns dispatch, held capacity, hour-12 F-04 fallback, and release verification; synthetic-scenario limitation remains visible. |

Geometry differs beyond color. Clean lab moves from a protocol ledger to a
longitudinal chart, endpoint/QC tables, and a scoped evidence-gate comparison.
Editorial uses a masthead, hourly chart, purpose table, dark numerical pause,
format comparison, pilot timeline, and decision grid. Operations uses a
full-field KPI, queue table, staged handoff timeline, grouped bar chart, option
comparison, and action register. Repeated headings and footers are consistent
within each deck, but the evidence layouts are not just recolors.

## Receipt and Evidence Limits

- All three [lab](clean-lab/qa/finalize_receipt.json),
  [editorial](editorial/qa/finalize_receipt.json), and
  [operations](operations/qa/finalize_receipt.json) finalize receipts say
  `passed: true`, `render_status: passed`, and zero recorded geometry,
  overlap, overflow, design, accessibility, and automated visual warnings.
  Their `visual_inspection_status` is `not_recorded`; separate
  [lab](clean-lab/qa/visual_review_receipt.json) and
  [editorial](editorial/qa/visual_receipt.json) and
  [operations](operations/qa/visual_receipt.json) model-review receipts report
  pass. I independently checked all 20 JPGs rather than relying on those
  model judgments.
- Current outline and PPTX SHA-256 values match all three finalize receipts; every
  current render hash matches its separate visual receipt (6 lab, 7 editorial,
  7 operations).
  This binds the reviewed files to the reported artifacts, not the truth of
  the synthetic scenarios.
- The lab checklist supplies summary CV and blank values but no raw well-level
  observations; the editorial survey is fictional with no fielding record; the
  operations checklist supplies invented planning inputs, not telemetry or a
  validated forecast model. This review verifies visible arithmetic, labels,
  and internal consistency only.

## Final Sheets

After this review, the builder regenerated the
[clean-lab](clean-lab_contact_sheet.jpg),
[editorial](editorial_contact_sheet.jpg), and
[operations](operations_contact_sheet.jpg) full sheets and the
[three-row comparison](three_study_comparison.jpg) from the current render files.
Comparison selections are lab 3/4/6, editorial 2/4/6, and operations 2/4/6.
The comparison is a visual index of different-topic authored examples, not a
same-content or model benchmark. The clean-lab finding above remains open.
