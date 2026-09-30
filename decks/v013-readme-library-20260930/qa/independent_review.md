# Independent Render Review

Reviewer: gpt-6.1-sol (independent of author review).
Reviewed: 2026-09-30T04:50:05Z.
Verdict: **FAIL**. One actionable P2 contrast issue; no other actionable layout findings.

## Finding

- **P2, slide 4, native shape ID 6:** The essential qualifier/source footer is 9 pt `#6B7280` on the actual `#000000` slide background: measured native-color contrast **4.343787999625581:1**. The full-size render visibly subdues "SYNTHETIC DATA", "Format preference, not a booking forecast", and the Q3 mutually-exclusive-format qualifier. These are evidence boundaries, not decoration. Improve the shared dark-slide footer foreground/background contrast, rebuild and reopen the changed artifacts before independent approval. No source shortening is needed.
- Exact source locations: `outline.json#/slides/3/footer` and `outline.json#/slides/3/sources/0`. Actual image: `qa/renders/slide-04.jpg`. Page-number shape 7 uses the same weak color, but is not a separate material finding.
- Review criterion: [W3C normal-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) uses 4.5:1 without rounding up. This is a readability reference, not a claim of full deck WCAG certification.
- Existing finalizer reported zero findings across its QA counts, at 7.18 s. Those counts did not establish this independent visual verdict; no check was suppressed or edited.

## Actual Inspection

Every `qa/renders/slide-01.jpg` through `slide-07.jpg` was independently opened full-size with `view_image(detail=original)`; no slide verdict was copied from author QA.

1. Opening masthead/title/subtitle fit; fictional/synthetic framing is visible. Deliberate opening whitespace.
2. Q1 native chart (shape 8) retains values 92/163/151/68, local-time categories, zero baseline and "Respondents (of 240)" unit. Full "overlap unknown" caption and hourly multi-select source are visible; no inference of distinct summed respondents.
3. Q2 native table (shape 4) has all four rows, counts and rounded shares. 72+48+54+66=240; 56+39+35+37=167. Caption explicitly separates Q2 yes/no from Q1 hourly selections; wrapped 6-8 pm header fits.
4. Native dark KPI retains 127 and "of 240 prefer drop-in help"; headline/value/denominator are clear and unclipped. Footer contrast fails as above; text itself is retained.
5. Drop-in/workshop comparison preserves 127/71 and the separate 42 "either" source, totaling 240. Preference-not-attendance qualifier and complete verdict are visible. Larger left panel provides deliberate hierarchy, not accidental clipping.
6. Prepare/Open/Adjust/Decide timeline is readable; complete first body, four week ranges and pilot-not-authorization/no-real-cost-data qualifier fit.
7. Decision has complete body/bullets/callout. 167 is explicitly Q2 and 127 explicitly Q3; no joint/subset inference is stated. Staffing/safety, observed-use condition and unknown cost/equity impact are retained. Column-first indexed order is explicit.

## Showcase and README

Opened actual `examples/v0.13_showcase.jpg`, then an in-memory 900 px wide preview (no image files written). Six panels represent four topics: enzyme storage, evening ferry, library after six, and microgrid repair. Manifest includes current library slide 4; all six selected render hashes and the board output hash were checked.

Headings, panel labels, table structure and main 127/240 metric are readable at this approximate desktop README width. Small chart labels, captions and footer qualifiers are not reliably readable there; opening the full-size image/deck remains necessary. The library footer weakness also persists at full size. This preview is not a live-browser/mobile layout certification.

Current README's lab/editorial/operations description is consistent with the four topics (ferry and library are both editorial), and it separately links the rebuilt library study. The synthetic-design-study boundary is explicit; this is not a benchmark.

## Exact Hash Scope

Current `outline.json` and old `decks/sol-design-studies-20260923/editorial/outline.json` are byte-identical: `7663bfea44d75cb0bbca53f718fbff2b4d68542d46d4c66afd75502938a742a2`.
Current `deck.pptx`: `96b94a14ad6fd117b65553ecd03b822f945453b7d6fa2216a47c06b6444371b7`.

| Actual file | SHA-256 |
| --- | --- |
| `qa/renders/slide-01.jpg` | `1c6a8806c382ea8cf35a7c0f45d2bd3743121256de9896553dd5bca6542fa357` |
| `qa/renders/slide-02.jpg` | `69df730bcf905d5cc4289dff63563564a97846f68d03fe97cfd321796c4dc74c` |
| `qa/renders/slide-03.jpg` | `87cdd1a0ad658396a88558d9f536533b3ef18b89ce331df75fccd13404d933fe` |
| `qa/renders/slide-04.jpg` | `54051fa072a954606e94732460beac0b4d0fedb8fc928b94f3bb2408e77ab2ea` |
| `qa/renders/slide-05.jpg` | `435d6d0fd58f64320e9118e94bce5dcd0df58c001fcce91c89ab6d6792c93a7b` |
| `qa/renders/slide-06.jpg` | `d0e3d9ced558aa2816200c69416b96cef7bbf764d3a6b3c42acbe5cdb006876c` |
| `qa/renders/slide-07.jpg` | `009b49fa6c59126ed33574defc526c5dbab54dc6282366b05e2a9b954e0e0ad9` |
| `examples/v0.13_showcase.jpg` | `212f6c27f067b99677dfc4d27135249431aeb53979a934fd5a3efff3f55d3fa8` |
| `examples/v0.13_showcase_manifest.json` | `28215e50fe3028ea0e536f6598b41924d5760ec989b9e0f86bd136c37a6287c0` |

Hashes were rechecked after image inspection. Native package inspection confirmed one native chart and one native table matching source; no patch was applied. Only this independent report was authored. Source/deck/renders, author visual judgment and official receipt remain untouched. Any changed artifact requires reopening the affected review; no external factual truth or model-comparison claim is made.
