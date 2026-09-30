# Run 01 Source Audit

Disposition: HOLD. Main owns builds; no author re-render, gate weakening, font reduction, source-content deletion, core edits, or Luna edits. Shared allocation and retention repairs are required before the next main build. Existing outlines remain unchanged and match their run-01 recorded hashes.

## Lab

Actual report is `qa/design_rules.json`, not `qa/design_report.json`. The historical QA files have been copied intact into `run01_qa_snapshot/` before any subsequent main build can overwrite the working QA directory.

- Source fidelity: `/slides/2/facts/0/detail` is missing: "Invented criterion, not release specification".
- Source fidelity: `/slides/2/facts/1/detail` is missing: "91% - 62%; descriptive difference".
- The report's actual slide text also lacks the second fact's value `29 pp` and label `Glycerol minus buffer`. Retain every fact's value, label, and detail; do not make an omitted second fact disappear from the gate by moving or deleting source fields.
- `qa/issues.json`: slide 3 chart-register caption has x=0.6, y=3.985, w=3.8, h=1.0 inches and 0.767-inch estimated overflow. The complete caption carries lot ranges and uncertainty caveats. Allocate measured caption space instead of suppressing it.
- `qa/issues.json`: slide 5 comparison's unmeasured-assay column has w=2.69, h=1.941 inches and 0.368-inch estimated overflow. Its three concise bullets are necessary interpretation boundaries; they should receive appropriate width/height.
- `qa/accessibility.json`: six content subtitles are 12.5 pt despite the source's 13 pt support floor. Honor the contract; do not relax accessibility or set a smaller source floor.

Source remains seven slides. No source remediation is justified for genuine chart detail loss or renderer-owned support typography. A bounded chart/comparison alternate can be considered after the allocator owner explains the supported geometry; avoid a deck-specific workaround that leaves the shared defect intact.

## Editorial

`editorial/run-01.log` records the timeline body requiring 0.93 inches at 22 pt, with only 0.84 inches available, at the then-current `renderTimelineComposition` callsite. The failing source is the three-entry evening-scene timeline, plus a meaningful model-boundary caption.

The chapter-spread mode gives the two right-hand entries equal row heights, then subtracts fixed title/label/body gaps. Their bodies contain roughly twenty words each. The first-pass measurement indicates allocation, not excessive narrative or a missing evidence boundary. Request content-aware row heights/title gaps and caption reservation before a fit rejection; keep all three scenes and current typography. Preserve the asymmetric editorial focal structure rather than switching to lab-like bands merely to avoid the problem.

Source remains six slides; no text, caption, role, or variant changed.

## Operations

`operations/run-01.log` records the decision ledger needing 3.08 inches at 16 pt, with 2.65 inches available. The source has three conditional decision bullets and a no-work-authorization takeaway. Each bullet carries a necessary fault-confirmation, readiness, or qualified-personnel boundary.

The inspected `planReadableRole` operations decision recipe uses the same minimum-height tree for primary and alternate; alternate mirrors placement only. Blindly changing to alternate will not create capacity. Ask the shared owner to improve available-body allocation and content-measured rows while retaining the operating grid and commitment strip. If genuine available-space exhaustion remains after shared allocation repairs, redistribute whole clauses across the existing process and acceptance slides without deleting them, keeping seven slides.

There is also a preflight warning for long chart category labels. Full event tags are intentionally retained; an abbreviated label should only be introduced with an explicit visible full-tag mapping, not by erasing suspected-cause wording. No chart labels have been changed.

## Independently Owned Luna Sample

Read-only observation: `luna/run-01.log` fails at timeline row allocation beside summary/footer; preflight also reports long sentence-style table cells. No source, QA, build, or artifact writes were performed in Luna. Main retains ownership of this older sample.

## Coordination

Sent Galileo two successful Codex thread messages with the exact failures, measurements, source pointers, and no-shrink/no-drop boundary. The second message includes the lab overflow/subtitle findings and explains why operations `alternate` alone is not a fix.

Galileo subsequently confirmed active shared-only repairs and requested unchanged source. Planned fixes: variable timeline rows and measured/widened editorial focus; stop duplicating source metadata as a fourth standard-decision content gate; retain all chart facts/details while independently measuring the caption; enforce the v2 support-subtitle floor. These are stated plans, not verified outcomes. Await Galileo's stable-renderer/focused-check report and main's next build. No shared-fix success is asserted.

All render attempts remain main-owned. Run 01 stays a failed attempt, even if a later build passes. No rendered slides exist for these first attempts to visually approve; lab rendering was deferred on source-fidelity findings.

## Historical Hashes

These hashes were read directly after inspection. They are not a claim that the failed attempts passed.

| Case | Original outline SHA-256 | Run-01 JSON SHA-256 | Run-01 log SHA-256 |
|---|---|---|---|
| Lab | `369497f448b6fbbc7dd4c67ff4d93490584cfbba5435003aa7f64df5238ddab0` | `d5880afb156dc6836f025e320832fddfa6907571848ed5f7e28e7217cd987f91` | `df0e6e85ed3fd0f485974211a62b32cf12f43e63bb217700dea04fb7ff4db382` |
| Editorial | `ab247a4e2a3c78f837a77d305b4247457978c42e466f1fd2bceb3cc90c274e22` | `e0b45cd4a98ddb0e755b230a7627280deafed92ba97d7e5a7daa3cc034d414f8` | `95427f2a9b81e3e38030e0c6ad3c94db2d8a86e912cd9fc479de2b79d49df889` |
| Operations | `e853831944e2ce7a63df6b17caea7c7146e13452256faaf528923f8f12691fc2` | `2ba6be65b523401b44166865152fa2215701657f4172fdf347b1dcf545364aca` | `f61b768bd20a8c2432e8650e2ac889a603f581cc8546e041f381c8af9350a611` |
| Luna (read only) | `2080d3fa2d84f8c007f44301300c1801647f16d9dfbb80ae829a89114aece6e2` | `57352e198159f06397dbebe07c41ae17751784101d906733a299cc0c35d22d3e` | `8757ac727bf7775aeae9ea3efeba8faccbb1b8ea98c33e28de1c2914e0e98126` |
