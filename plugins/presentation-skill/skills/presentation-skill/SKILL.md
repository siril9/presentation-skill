---
name: presentation-skill
description: Build, edit, redesign, render, and verify polished editable PowerPoint `.pptx` decks from a prompt, structured JSON, local data, or a saved workspace. Use for scientific, lab, clinical, consulting, board, investor, editorial, policy, and operational presentations where narrative, visual hierarchy, readability, and reproducibility matter.
---

# Presentation Skill

Create editable PowerPoint decks from source. The model owns the argument,
evidence, and design judgment; the skill owns deterministic rendering and QA.

## Core Contract

- Treat `outline.json`, planning files, data, and figure scripts as source.
- Build with repository commands. Do not write one-off deck generators or patch
  a generated PPTX when source exists.
- Keep text, charts, tables, diagrams, and figures editable where practical.
- Use the selected grammar as a design system, not a fixed slide sequence.
- Fix source and rebuild until geometry, readability, placeholders, and rendered
  visual review pass.
- Do not copy proprietary slides, logos, wording, or distinctive geometry.

Run commands from this skill directory. Use absolute paths for deck files kept
elsewhere. Check the pinned runtime once:

```bash
npm run doctor
```

If required, run `npm run setup:python` once. Do not substitute arbitrary Python
or Office application workflows for the supported runtime.

## Choose A Route

### Clarify Only What Matters

The brief includes optional intake questions. Ask at most three short questions
only when missing audience, decision, evidence, or brand information would change
the deck. Do not ask again when the request or saved answers already cover it.
Otherwise state reasonable assumptions and proceed. Never invent missing results.

Use `present.py intake --prompt "..."` for a standalone intake packet. Pass answers
as inline JSON, for example `--answers '{"audience":"Lab directors"}'`, to the next
brief. Fields are `audience`, `purpose`, `evidence`, and `style`. These are design
questions, not permission requests.

If the caller supplies low remaining usage and confirms Luna is available, offer
the current model or Luna with the same QA. Ask once; do not silently switch.
Without known model availability, offer a leaner workflow on the current model,
not a promise of Luna access or lower quota consumption. Never query account
usage merely because a deck is requested.

### Quick Deck

Use for a one-off 5-10 slide deck.

1. Emit a small model-ready brief:

```bash
python3 scripts/present.py brief \
  --topic "Deck topic" \
  --prompt "Original request" \
  --slides 7 \
  --profile auto \
  --output quick_deck_agent_brief.json
```

2. Read the brief and author `outline.json`. Select one bounded route candidate,
   then adapt its starter sequence to the actual evidence. `role` names the
   editable structure; `slide_intent` names the story job.

3. Build, render, and hard-gate it:

```bash
python3 scripts/present.py finalize \
  --outline /absolute/path/outline.json \
  --output /absolute/path/output.pptx \
  --qa-dir /absolute/path/qa
```

Read `finalize_receipt.json` and inspect the rendered slides. If checks fail,
start from `repair_packet.json`: it contains affected source pointers, measured
issues, and image paths. Repair source and rerun until the artifact passes;
do not stop after an arbitrary number of attempts. Automated checks do not
substitute for actual visual inspection.

When style choice is genuinely uncertain, preview the same representative
content in a few candidate styles before building the full deck:

```bash
python3 scripts/present.py audition \
  --outline /absolute/path/outline.json --outdir /absolute/path/audition \
  --presets lab-report editorial-minimal warm-terracotta
```

This is optional, not an extra step for every deck. Inspect `comparison.jpg`
and select by evidence fit and hierarchy, not decoration. The source is unchanged.

### Saved Workspace

Use for decks that will be rebuilt, audited, or iterated:

```bash
python3 scripts/present.py init \
  --workspace /absolute/path/deck-workspace \
  --title "Deck title" \
  --prompt "Original request" \
  --profile auto \
  --style-preset auto

python3 scripts/present.py build \
  --workspace /absolute/path/deck-workspace \
  --draft

python3 scripts/present.py build \
  --workspace /absolute/path/deck-workspace
```

The default workspace is compact. Add `--audit-packet` to `present.py init` only
when a full intake/multi-agent recovery ledger is useful.

Author or update:

- `design_brief.json`: audience, style, readability, and QA contract
- `content_plan.json`: thesis, narrative arc, and slide roles
- `evidence_plan.json`: claims, sources, and chart candidates
- `asset_plan.json`: figures, tables, charts, images, and icons
- `outline.json`: renderable slide source
- `notes.md`: assumptions and unresolved decisions

The build also writes deterministic `build/deck_ir.json`, a coordinate-free
semantic representation with stable object IDs, evidence links, reading order,
and editability metadata. Renderer scripts continue to own coordinates.

### Existing PPTX

When source exists, edit source. For a standalone PPTX, inspect it first:

```bash
python3 scripts/python_runtime.py scripts/reference_deck.py inspect \
  --input /absolute/path/input.pptx \
  --output /absolute/path/reference_deck_manifest.json
```

Use a typed `reference_deck_patch_v1` for narrow text or alt-text edits. Use
`scripts/extract_pptx_style.py` plus a fresh workspace for a source-first
redesign inspired by an existing deck. Read `references/editing.md` before
editing package internals.

## Model Profiles

Profiles change orchestration, not the final quality definition:

- `fast` / `luna`: one grammar candidate and small valid payload examples;
  single-agent authoring with focused repairs.
- `balanced` / `terra`: two grammar candidates; delegate only when useful.
- `quality-first` / `sol` / `astra`: up to three grammar candidates, optional
  evidence or design scouts, and flexible content-led composition.
- `auto`: quality-first for high-stakes/evidence-heavy work, fast for explicit
  rough drafts, balanced otherwise.

Profiles are workflow policies, not provider/model switches or quality claims.
One capable model can complete the entire workflow. No advisor model or
multi-agent setup is required; use bounded advice only when it resolves a
specific design or evidence uncertainty, then continue authoring and validation.
All models may adapt the suggested sequence and mix supported treatments.
Do not feed them the full corpus or arbitrary coordinates. For an unrecognized
future model, choose a workflow profile explicitly. Use the recorded fallback
when no content-grounded design choice is available.

## Design Decisions

Choose one primary grammar from topic, audience, evidence shape, and density.
The eight structural grammar families own distinct title, section, evidence,
comparison, data, decision, and references systems. Presets contribute palette,
type, and treatment vocabulary; they are not static templates.

Maintain these invariants:

- One dominant idea and a clear reading path per slide.
- Every content slide has a visual or evidence anchor: chart, table, figure,
  image, KPI, timeline, matrix, or structured comparison.
- No centered body copy and no sequence dominated by bullet-only slides.
- Vary composition with the argument; avoid repeating one card grid, border,
  title treatment, or two-column shell.
- Use `header_variant: auto` with a stable seed for reproducible heading,
  top-line, bottom-line, no-line, and compact report treatments.
- Keep source text and page numbers in the reserved footer region; do not let
  footer chrome compete with the evidence.
- Use `role_layout_variant: primary | alternate | dense` for bounded structural
  variation. Do not place arbitrary coordinates in `outline.json`.
- Keep typography, spacing, and semantic colors coherent. Borrow supported
  treatments when the content benefits; the suggested sequence is not mandatory.
- For a visual A/B, freeze one outline and vary only `deck_style`; this exposes
  real grammar differences without letting content changes bias the comparison.
- Treat auxiliary title-stage anchors as content slots, not decoration. Leave
  them absent unless the outline supplies a value or asset.

Readable defaults for ordinary delivery:

- titles at least 28 pt;
- body text at least 16 pt;
- supporting subtitles at least 13 pt;
- captions, sources, and metadata at least 9 pt;
- no more than two title lines;
- shorten, split, or convert prose into evidence objects before shrinking.

Use actual content to balance white space. Sparse slides need a stronger anchor;
dense slides need fewer words or a more suitable structure, not smaller type.

For structural routing details, read
`references/composition_grammar_catalog.md`. For screenshot/template
inspiration, read `references/style_reference_catalog.md`. The descriptor corpus
is retrieval memory; load only the selected record or distilled atoms.

## Data And Figures

For local CSV, TSV, XLSX, or JSON evidence, keep generated artifacts
reproducible:

```bash
python3 scripts/python_runtime.py scripts/scaffold_figure_artifacts.py \
  --workspace /absolute/path/deck-workspace \
  --run \
  --bind-outline
```

Preserve source fingerprints, figure scripts, chart/table JSON, artifact
manifests, slide bindings, and rebuild commands. Solve whitespace and label
readability in the figure script before placing the figure. Stage sourced images
through `asset_plan.json` with attribution. Generated imagery must remain
optional and carry prompt/model/purpose metadata.

Bar charts include zero by default. Set explicit axis bounds only for an
intentional, disclosed comparison; do not exaggerate differences through cropping.

Read `references/reproducible_workflow.md` only when the deck contains computed
evidence or generated figures.

## QA And Delivery

For evidence-led decks, keep a compact source checklist of critical values,
units, denominators, caveats, and source IDs. Compare it with both the outline
and rendered slides before approval. A correctly rendered chart can still
contain swapped counts, missing facts, or an unsupported inference; automated
layout checks do not establish factual fidelity.

A deliverable deck must pass:

1. planning and outline preflight;
2. geometry, overflow, overlap, density, and whitespace checks;
3. rendered contact-sheet and slide-level visual review;
4. placeholder-text checks;
5. readability and accessibility checks;
6. final delivery readiness.

Visual review should search for defects: clipped text, weak contrast, awkward
empty regions, crowded edges, tiny labels, inconsistent alignment, repeated
grammar, and unreadable sources. Fix source and rebuild.

For public proof or audited delivery, bind the actual review to the deck and
render hashes with `scripts/visual_review_receipt.py`. Never invent a review
receipt from automated counts. An optional `--render-cache-dir /absolute/path/cache`
on `present.py finalize` reuses verified identical renders; content and rendering
environment changes invalidate the cache. It never reuses a visual judgment.

If rendering is unavailable in the execution environment, preserve the built
deck and static QA report, record the deferred render stage in the receipt, and
do not probe unrelated Office apps.

## Progressive References

Read only what the current task needs:

- `DESIGN.md`: compact design contract
- `references/model_adaptive_workflow.md`: profile selection and context budgets
- `references/deck_workspace_mode.md`: persistent workspace workflow
- `references/outline_schema.md`: schema or preflight failures
- `references/editing.md`: existing PPTX edits
- `references/reproducible_workflow.md`: data and figure artifacts
- `references/style_reference_catalog.md`: inspiration and screenshot matching
- `references/composition_grammar_catalog.md`: structural grammar routing
- `references/pptxgenjs.md`: renderer development only
- `references/visual_qa_prompt.md`: independent rendered review
- `references/benchmark_protocol.md`: fair comparison or superiority claims

Do not preload all references, presets, or corpus records.

## Development

After changing runtime behavior, run:

```bash
npm run check:python
npm run check:node
npm run check:present
npm run check:focused
```

Visual changes require a rendered proof. Showcase decks alone do not justify a
claim that this skill outperforms another generator; use the frozen benchmark
protocol and report only supported results.
