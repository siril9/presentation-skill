# Local Visual References

Optional composition memory, not templates or a required review stage. Briefs
offer at most three unique local image links across all candidate grammars,
ranked by role, content shape and purpose. Explicit shape/role requests exclude
unrelated examples; unavailable or unmatched references can yield fewer links.
The model chooses whether to inspect them. No image bytes, base64, full decks,
render directories, corpus preload or extra model calls enter the brief.

Keep one coherent base typography, spacing, semantic color and page system.
Borrow at most two compatible composition moves when useful; roles are not a
fixed sequence. These are synthetic design examples, not factual evidence,
quality guarantees or a comparison of models. Renderer capabilities remain
authoritative. In particular, the editorial focal metric is visual pacing
inspiration: use a supported `stats` representation for v2, not an assumed
`evidence/kpi-hero` geometry contract.

## Choose An Example

| Image | Roles / shape | Useful Purpose | Density / composition | Bounded Mixing |
|---|---|---|---|---|
| [Lab cover](assets/visual_references/lab_cover.jpg) | title | restrained scientific opening | sparse; left title and scope, quiet footer | cover hierarchy only |
| [Lab trend](assets/visual_references/lab_trend.jpg) | chart, evidence | drift against a threshold | medium; wide line plot above interpretation | plot/readout allocation; retain units and bounds |
| [Lab endpoints](assets/visual_references/lab_endpoints.jpg) | table, evidence, support | limits and denominators | medium; five-column ledger above caveat | ledger and readout; no second page frame |
| [Lab evidence gate](assets/visual_references/lab_evidence_gate.jpg) | comparison, decision | findings versus required validation | medium; open paired columns | evidence/limits split; not a mandatory close |
| [Editorial chart](assets/visual_references/editorial_chart.jpg) | chart, evidence | survey demand | medium; asymmetric chart and sidecar | chart/rail proportions in the base type |
| [Editorial focal metric](assets/visual_references/editorial_focal_metric.jpg) | evidence, stats | synthesis or a rhythm break | sparse; one metric plus denominator | one optional contrast pause, not a dark theme |
| [Editorial pilot](assets/visual_references/editorial_pilot.jpg) | evidence, support, timeline | bounded implementation | medium; preparation block plus open events | unequal staging with coherent spacing |
| [Editorial decision](assets/visual_references/editorial_decision.jpg) | decision, support | action, trigger, owner, timing | dense; four open fields and a verdict | accountability structure, not an entire frame |
| [Operations queue](assets/visual_references/operations_queue.jpg) | table, evidence, support | auditable ranked dispatch | dense; six-column owner ledger | register with explicit clock and qualifier |
| [Operations handoffs](assets/visual_references/operations_handoffs.jpg) | evidence, support, timeline | timed control handoffs | medium; four rows and separate trigger | rows/callout allocation with footer clearance |
| [Operations tradeoff](assets/visual_references/operations_tradeoff.jpg) | comparison, decision | exposure versus travel cost | medium; paired options and verdict | aligned comparison and separate verdict |
| [Operations owner register](assets/visual_references/operations_owner_register.jpg) | table, decision, support | authorization or appendix support | dense; action, due, trigger and owner | action register wherever needed, not always last |

## Provenance And Retrieval

All 12 images are full-slide snapshots of original repository Sol studies under
`decks/sol-design-studies-20260923`: clean-lab slides 1/3/4/6, editorial slides
2/4/6/7, and operations slides 3/4/6/7. They use original synthetic data and
repository composition, without external slide, photo, logo or brand assets.
Copyright (c) 2026 Siril Sengolraj; [MIT license](../LICENSE).

The source [repair recheck](../decks/sol-design-studies-20260923/review.md)
closes the lab caveat omission and operations bottom-box overlap. The curated
lab endpoint includes the repaired six-well basis, screen limits and no-expiry
caveat; the operations timeline/tradeoff use repaired callout spacing. No
scientific, survey or operational outcome is validated by those reviews.

[Machine-readable catalog](visual_reference_catalog.json) records each use,
density, composition, mixing option, compatible grammar, source slide/outline,
review link, SHA-256 and snapshot size. Images total **875,916 bytes**;
each is 1200 x 675 JPEG, resized without cropping or content changes at quality
82 with 4:4:4 chroma. Original decks/renders are provenance only and need not
be shipped or present for retrieval.

Existing `present.py brief` exposes selected `route_candidates[].visual_references`
as `id`, absolute `path` and `keywords`. Saved workspace briefs expose the same
hints under `routing.composition_grammar` and its `alternatives`, also as
Markdown links. `visual_reference_policy.catalog` leads here only on demand.
Profile aliases such as `gpt-6.1-sol` choose a local workflow policy; they never
select a provider, switch the running model or set its reasoning effort.
