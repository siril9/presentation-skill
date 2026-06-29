---
name: presentation-skill
description: "Presentation skill for Codex, ChatGPT agents, and OpenAI-style agents that build, edit, verify, or iterate polished PowerPoint `.pptx` presentations, slides, and slide decks from structured `outline.json` or saved workspaces. Use for editable deck generation, lab/clinical/scientific deck assembly, investor or board decks, editorial briefs, presentation design, source-backed assets, optional generated-image slides, alignment QA, overflow/overlap checks, layout validation, and reusable deck workspaces. Aliases: `powerpoint-deck-builder`, `pptx-skill`, PowerPoint skill, PPTX skill, slide-deck generator, slides generator, deck builder, presentation generator."
---

# Presentation Skill

Repo-native PowerPoint skill for editable, aligned, QA-checked `.pptx`
decks. The model plans the story and visual strategy; scripts handle fragile
rendering, staging, and verification.

## When to invoke this skill

Trigger this skill on requests to:

- build a one-off PowerPoint `.pptx`, slide deck, or presentation from a
  single prompt (quick-deck mode, no workspace needed)
- generate a `.pptx` from a structured `outline.json`
- redesign, rebuild, or extend an existing deck
- create a lab, clinical, scientific, board, investor, or editorial deck
- run layout, design, or readability QA on a generated deck
- author or update a reusable deck workspace
- convert CSV/TSV/XLSX/JSON data into slide-ready figures and tables

Quick-deck mode is the right path for one-shot 5-10 slide decks. Workspace
mode is for decks that will be iterated, audited, or rebuilt later. See
`### Quick Deck` and `### Saved Workspace` under Workflow below.

Do not invoke it for text-only brainstorming where no deck artifact is
needed, or for direct edits to a generated `.pptx` when its saved workspace
source files are available (fix the source instead).

Skill name: `presentation-skill`. Compatibility aliases for fuzzy skill
matching: `powerpoint-deck-builder`, `pptx-skill`, PowerPoint skill, PPTX
skill, slide-deck generator, slides generator, deck builder, presentation
generator, presentation maker, PowerPoint generator, Codex presentation
skill, ChatGPT presentation skill, OpenAI agent presentation skill.

## Non-Negotiables

- Do not write ad hoc inline `python-pptx` or `pptxgenjs` deck code. Author
  `outline.json` and run repo scripts.
- Do not reinstall dependencies during deck generation. Missing dependency:
  report it and stop.
- Do not skip QA for a deliverable deck. Use render-free QA when LibreOffice is
  unavailable.
- For reusable/report decks, treat `validate_planning.py` warnings about
  missing artifact registries, stale generated artifacts, figure rebuild
  commands, readability contracts, speed contracts, QA contracts, acceptance
  evidence, or execution phases as source-planning feedback to fix before
  final delivery.
- Fix source files (`outline.json`, plans, assets, renderer code), not mutated
  `.pptx` artifacts.
- For a new topic, scaffold fresh. Do not clone another deck's structure as a
  house style.

## First Files To Read

- `DESIGN.md`: compact design contract, colors, hierarchy, alignment rules,
  generated-image disclosure.
- `references/outline_schema.md`: accepted `outline.json` fields and variants.
- `references/planning_schema.md`: `design_brief.json`,
  `content_plan.json`, and `evidence_plan.json` shape.
- `references/deck_workspace_mode.md`: saved-workspace workflow.
- `references/agent_picker.md`: concise picker guidance for agents and people.
- `references/reference_script_patterns.md`: reusable PPTX/DOCX/figure
  patterns from stronger one-off scripts; read when improving routing,
  scientific decks, or companion document workflows.
- `references/style_reference_catalog.md`: publish-safe style-reference
  policy for using public decks, screenshots, PPTX corpora, and synthetic
  recreations without bundling proprietary material.
- `references/dynamic_design_and_subagents.md`: bounded dynamic design
  modulation plus when to use content, data, routing, critique, and QA
  subagents.
- `references/visual_qa_prompt.md`: visual-review packet and fresh-eyes inspection prompt.
- `scripts/emit_deck_start_packet.py`: preferred first-turn packet for
  reusable decks; bundles a compact user question payload, reproducible design
  contract prompt, and staged subagent handoff commands.
- `scripts/emit_deck_intake_prompt.py`: optional user-facing intake prompt
  for audience, style, palette, density, background, assets, sources, and
  constraints when personalization is underspecified.
- `scripts/apply_deck_intake_answers.py`: deterministic bridge from Codex
  question-card answers to `design_brief.user_intake`, `style_seed`, notes,
  and planning-file source policy/asset posture.
- `scripts/run_deck_start_intake_smoke.py`: focused fast smoke for the
  first-turn deck-start packet, versioned agent kickoff brief, durable intake
  answers, pre-answer readiness `record_deck_intake_answers` trigger,
  deterministic application, idempotence, and readiness `deck_intake` summary.
- `scripts/emit_design_contract_prompt.py`: reproducible style/structure
  contract prompt to run immediately after the user request or intake answers,
  before authoring `outline.json`.
- `scripts/apply_design_contract.py`: deterministic bridge from a returned
  `deck_design_contract_v1` JSON packet to `design_brief.json`,
  `content_plan.json`, `evidence_plan.json`, `asset_plan.json`, and `notes.md`.
- `scripts/run_design_contract_apply_smoke.py`: focused fast smoke for the
  design-contract prompt, intake-seeded choice-resolution enrichment,
  deterministic contract application, idempotence, planning validation, and
  readiness `design_contract` summary.
- `scripts/emit_outline_authoring_prompt.py`: contract-aware handoff prompt
  for replacing starter `outline.json` with authored slides plus aligned
  content/evidence/asset plan edits after `design_contract.json` is applied.
- `scripts/apply_outline_authoring_handoff.py`: deterministic bridge from a
  returned `outline_authoring_handoff_v1` JSON packet to `outline.json`,
  `content_plan.json`, `evidence_plan.json`, `asset_plan.json`, and `notes.md`.
- `scripts/run_outline_authoring_handoff_smoke.py`: focused fast smoke for
  the contract-aware outline prompt, deterministic handoff apply, source-plan
  alignment, readiness summary, PPTX build, and outline-aware render-free QA.
- `scripts/run_reproducible_workflow_smoke.py`: fast end-to-end smoke for the
  deck-start, intake, design-contract, outline-handoff, strict render-free QA,
  and delivery-readiness handoff path.
- `scripts/run_focused_workflow_checks.py`: aggregate fast smoke runner for
  the reproducible workflow, style-mix, layout polish, source-footer, and
  generated-data lanes; can run isolated checks concurrently while writing one
  compact JSON report with per-check durations and failure tails.
- `scripts/extract_pptx_style.py`: source-only PPTX/corpus style extractor
  that emits observed header/footer/color/readability signals plus a reusable
  `design_brief.json` fragment for template-inspired decks.
- `scripts/apply_pptx_style_fragment.py`: deterministic bridge from extracted
  PPTX style fragments to `design_brief.json`, `renderer_treatments`,
  `style_import`, and `notes.md`.
- `scripts/style_reference_catalog.py`: synthetic publish-safe style DNA and
  content-treatment references for each preset, including title, comparison,
  chart, table, figure, dashboard, decision, and references behavior plus the
  `style_reference_mix_plan_v1` prompt matcher and
  `style_reference_layout_playbook_v1` variant map and
  `style_reference_structural_motif_library_v1` motif grammar plus
  `style_reference_metric_profile_v1` density/whitespace/object-bias metrics
  plus `style_reference_content_recipe_library_v1` content-slot recipes used
  by design-contract and outline-authoring prompts.
- `references/style_reference_sources.json` and
  `scripts/style_reference_sources.py`: publish-safe source-intake manifest and
  validator for public decks, screenshots, PPTX corpora, and template-gallery
  inspiration. Use this before adding or citing external style references; it
  records license notes, source-verification evidence, allowed extraction
  modes, forbidden materials, generic style observations, reusable slide
  pattern extracts, attribution posture, and per-preset synthetic
  reconstruction routes.
- `references/style_inspiration_corpus.json` and
  `scripts/style_inspiration_corpus.py`: descriptor-only inspiration corpus for
  public design systems, presentation tooling, template indexes, and slide
  design heuristics. Use it as a scalable source-index layer for prompt-to-style
  routing and subagent scouting; it stores rights posture, extraction limits,
  layout/palette/typography descriptors, per-preset routes, and the safety rule
  that no raw decks, screenshots, logos, proprietary text, or distinctive
  copied geometry are bundled.
- `references/large_style_corpus_sources.json`,
  `references/large_style_corpus_catalog.json`, and
  `scripts/large_style_corpus.py`: descriptor-only large public deck corpus
  layer for real-world style discovery. Use it to index 2,000+ public/open
  deck-like records, balance overlap, prioritize AI-agent/tooling examples,
  emit compact LLM context, and replace redundant-looking preset treatments
  with original synthetic structure. It stores only public URLs, repository/path
  metadata, inferred style families, and descriptors; never raw decks,
  screenshots, copied slide text, logos, or distinctive source geometry.
- `references/style_token_atlas.json`, `references/style_grammar_index.json`,
  `scripts/style_atom_router.py`, `scripts/apply_atom_composition.py`, and
  `scripts/workflow_atom_context.py`: dynamic corpus-atom grammar layer. Use it
  when a deck needs the corpus to influence structure, treatment pools, density,
  and narrative arc while still leaving the current/future LLM free to make
  topic-fit choices. Normal deck-start, design-contract, and style/content
  router prompts now receive a `normal_workflow_atom_context_v1` seed that can
  be accepted, refined through strict JSON, or skipped with a recorded reason.
  Apply only supported renderer fields.
- `scripts/run_large_style_corpus_smoke.py`: focused fast smoke proving the
  large-corpus source manifest, descriptor schema, family coverage, compact
  context, and digest writer stay usable without network access.
- `scripts/run_style_atom_router_smoke.py`: focused fast smoke proving the
  atom atlas, grammar templates, deterministic fallback, topic-aware ranking,
  strict JSON atom prompt, and applier replay ledger stay usable.
- `scripts/build_large_style_corpus_contact_sheets.py`: publish-safe visual
  contact sheets generated from large-corpus descriptors. It draws synthetic
  family and source-record cards from catalog metadata only; it does not fetch,
  render, or screenshot source decks.
- `scripts/run_large_style_corpus_leverage_smoke.py`: focused smoke proving
  the 2,000-record corpus is actually used by router prompts and contact-sheet
  evidence while preserving curated style-reference prompt tokens.
- `scripts/design_catalog_selector.py`: reusable v0.5 design-catalog selection
  layer that maps prompts to topic cases, corpus families, treatment DNA,
  generated data recipes, and reproducible release-evidence scope.
- `scripts/build_random_topic_comparison_decks.py`: release-evidence builder
  for eight random synthetic topics, each built as a baseline deck and a
  descriptor-corpus-guided deck across eight visibly different corpus families,
  plus rendered contact sheets, a gallery deck, generated data/chart/table
  artifacts, manifest metrics, structural-delta signatures, and concise release
  notes.
- `scripts/run_random_topic_comparison_smoke.py`: reproducibility smoke that
  rebuilds the random-topic comparison evidence in a temporary directory and
  fails if the 16 decks, gallery, manifest, release notes, nonblank contact
  sheets, corpus-context metrics, eight-family coverage, three generated data
  examples, structural QA gates, zero visual/readability warnings, or
  baseline-vs-corpus structural deltas are missing.
- `scripts/build_style_reference_gallery.py`: generated reference-gallery
  decks that turn the synthetic style catalog into actual title, dashboard,
  comparison, chart, table, figure, decision, and references slides without
  bundling external template assets. The gallery summary records per-preset
  variant sequences, structural playbook signatures, structural motif
  signatures, content-recipe signatures, renderer-treatment signatures,
  treatment buckets, rendered contact-sheet paths, per-treatment contact-sheet
  paths, per-preset contact-sheet collections for `overview`, `data_evidence`,
  and `decision_sources`, and QA totals for release evidence.
- `scripts/run_style_reference_gallery_smoke.py`: focused fast smoke proving
  all-preset style-reference gallery decks keep unique content signatures,
  required treatment coverage, publish-safe metadata, and clean render-free QA.
- `scripts/run_style_reference_resolution_smoke.py`: all-preset build-time
  resolver smoke proving identical generic evidence slides resolve into
  preset-specific `build/outline_resolved.json` variants with unique treatment
  signatures.
- `scripts/run_style_content_router_smoke.py`: focused fast smoke proving the
  style/content router prompt includes ranked style-reference matches,
  mix-plan context, layout playbooks, content recipes, renderer treatment pools,
  and the optional first-class atom composition route for prompt-to-reference
  routing.
- `scripts/run_style_reference_release_evidence_smoke.py`: optional rendered
  release-evidence smoke proving the all-preset gallery has clean QA,
  unique content signatures, visual-diversity hashes, fingerprinted contact
  sheets, rendered slide evidence for every required treatment key, and
  per-treatment rendered thumbnail and coarse-layout signatures so
  repeated-looking treatment families are visible and blocked in release
  evidence.
- `scripts/run_style_reference_starter_smoke.py`: all-preset starter smoke
  proving initialized `style_reference_starter_outline_v1` workspaces keep
  distinct scaffold signatures, publish-safe source metadata, starter assets,
  and clean render-free QA.
- `scripts/style_treatment_profiles.py`: reusable preset treatment profiles
  for supported heading/accent, footer, chart, and figure/table pools across
  all loadable presets. Profiles include a `style_reference_catalog_v1`
  reference so agents get more than surface-level chrome variation.
- `scripts/build_header_variant_gallery.py`: visual fixture builder for
  checking clean content-header variants across all presets.
- `scripts/run_header_variant_gallery_smoke.py`: focused fast smoke proving
  all presets build actual header-variant gallery decks with clean render-free
  QA counts.
- `scripts/run_rendered_header_gallery_smoke.py`: optional slower rendered
  smoke proving all presets render the header-variant gallery to nonblank
  slide images, write a contact sheet, and pass lab-report visual review.
- `scripts/run_rendered_data_delivery_smoke.py`: optional slower end-to-end
  smoke proving a lab/data deck carries deck-start intake, a design contract,
  a rendered figure/chart/table artifact triplet, strict rendered QA,
  visual-review contact sheet, generated-slide density floors, speed timings, repeat-build
  source/artifact/quality stability, and final delivery-readiness `ready`
  status.
- `scripts/run_style_mix_repro_smoke.py`: focused fast smoke for deterministic
  style-mix/header/footer treatment resolution.
- `scripts/run_layout_polish_handoff_smoke.py`: focused fast smoke proving
  saved QA whitespace/readability warnings become exact readiness and
  `advance_workspace.py` source-edit handoffs.
- `scripts/run_readability_contract_smoke.py`: focused fast smoke proving
  rendered chart/table readability-contract warnings preserve measurements,
  slide IDs, and exact source-edit handoffs.
- `scripts/trim_image_whitespace.py`: helper for generated plots with large
  exterior whitespace before insertion into figure-first layouts.
- `scripts/compact_source_footers.py`: source-only helper that rewrites
  over-budget `source-line` footer provenance into short IDs and a final
  editable References table slide, splitting reference rows across slides when
  needed.
- `scripts/run_source_footer_compaction_smoke.py`: focused fast smoke for
  preflight footer-budget warnings, readiness/advance compaction, reference
  slide creation, and idempotence.
- `scripts/run_lab_footer_chrome_smoke.py`: focused PPTX-XML smoke for
  lab-report source-line footer rule, compact source/ref text, bottom-right
  page numbers, and top-bottom/plain header chrome.
- `scripts/scaffold_figure_artifacts.py`: deterministic starter for local
  CSV/TSV/XLSX/JSON data; writes `assets/make_figures.py`, chart JSON,
  summary-table JSON, slide-ready PNGs, and artifact-plan updates.
- `scripts/run_generated_artifact_quality_smoke.py`: focused fast smoke for
  the scaffold/inspect/bind/readiness generated-artifact quality path.
- `scripts/run_figure_whitespace_handoff_smoke.py`: focused fast smoke proving
  high-whitespace generated figures become trim/regenerate readiness and
  `advance_workspace.py` source-edit handoffs with measured reasons.
- `scripts/run_data_artifact_workflow_smoke.py`: integrated fast smoke for
  local CSV data through `--fast-first-pass`, auto-binding, render-free QA,
  source freshness, workspace readiness, and delivery-readiness handoff.
- `scripts/run_excel_artifact_workflow_smoke.py`: integrated fast smoke for
  multi-sheet Excel workbook data through `--fast-first-pass`, sheet-level
  artifact provenance, auto-binding, render-free QA, workspace readiness, and
  delivery-readiness handoff.
- `scripts/run_artifact_triplet_workflow_smoke.py`: integrated fast smoke for
  full generated artifact triplets, proving figure, editable chart, and
  summary-table slides bind together with staged roles and clean render-free
  QA counts.
- `scripts/run_artifact_freshness_smoke.py`: focused fast smoke proving stale
  local data changes produce planning warnings, stale build freshness,
  workspace recommendations, and blocked delivery readiness.
- `scripts/inspect_artifact_manifest.py`: re-emits slide-ready aliases,
  outline snippets, and binding updates from `assets/artifacts_manifest.json`
  when only the manifest is available after artifact generation.
- `scripts/apply_artifact_manifest_bindings.py`: applies a small JSON
  selection file, or a deterministic `--auto-select` selection from the
  manifest, to `outline.json`, `content_plan.json`, `evidence_plan.json`,
  artifact `used_on_slides`, figure-export targets, and asset-plan slide-use
  metadata after choosing generated outputs.
- `scripts/apply_data_analysis_handoff.py`: deterministic bridge from a
  returned data/evidence scout JSON packet to artifact selection bindings,
  `evidence_plan.json`, and an idempotent notes handoff for script edits and
  QA evidence.
- `scripts/report_workspace_readiness.py`: fast source-only workspace readiness
  report; run before render when resuming a deck or deciding whether planning,
  preflight, artifact binding, or data scaffolding should happen next. Its
  top-level `quality_context` mirrors the applied slide quality contract and
  outline quality alignment, and its top-level `artifact_context` preserves
  generated artifact output IDs, aliases, figure-quality counts, analysis
  summary paths, binding targets, and tabular-data inputs for later
  build/delivery handoffs.
- `scripts/advance_workspace.py`: readiness-driven next-action loop; use after
  the readiness report when a resumed workspace needs the next command run or a
  written source-edit prompt. Its JSON report and prompt preserve the compact
  slide quality / outline quality context and generated-artifact context from
  readiness so source edits keep readable text floors, whitespace rules, QA
  gates, generated aliases, and bound chart/figure/table targets visible.
- `scripts/report_delivery_readiness.py`: final delivery audit; combines
  source readiness, build-report source fingerprints, QA counts, output
  fingerprints, strict-build options, layout-density evidence, and replay
  commands into one status report.
- `scripts/advance_delivery.py`: delivery-level next-action loop; use after
  the delivery audit when a workspace needs the strict final build command,
  source-edit handoff, or a deterministic delivery prompt written out.
- `references/editing.md`: only when editing an existing deck.
- `references/pptxgenjs.md`: only when editing JS renderer/templates.

## Workflow

### Quick Deck

Use for one-shot 5-10 slide decks.

```bash
node scripts/build_deck_pptxgenjs.js \
  --outline outline.json \
  --output out.pptx \
  --style-preset <preset>

python3 scripts/qa_gate.py \
  --input out.pptx \
  --outdir /tmp/pptx-qa \
  --style-preset <preset> \
  --strict-geometry \
  --skip-render \
  --fail-on-design-warnings
```

### Saved Workspace

Use when the deck will be extended, audited, or rebuilt later.

```bash
python3 scripts/init_deck_workspace.py \
  --workspace decks/my-deck \
  --title "My Deck" \
  --style-preset <preset>
```

When the original user request is available and the deck should be
reproducible, initialize and emit the first-turn packet in one command:

```bash
python3 scripts/init_deck_workspace.py \
  --workspace decks/my-deck \
  --title "My Deck" \
  --style-preset <preset> \
  --user-prompt "Original user request here"
```

This initializes style-reference starter files and a
`normal_workflow_atom_context_v1` seed. Treat the atom seed as optional
first-class grammar: accept it when topic-fit, refine it with the strict JSON
atom prompt when a stronger mix is obvious, or skip it with a reason. When used,
persist the decision in `choice_resolution.atom_composition`,
`style_system.style_atom_composition`, and the slide sequence/variant plan.

That writes `deck_start_packet.json` immediately, records it in
`workspace.json`, and lets the agent ask the compact question card or persist
best-judgment assumptions before design-contract work. Use
`--emit-start-packet` when a packet is useful but only the deck title is known,
and `--start-packet` to choose a non-default packet path.

```bash
# edit design_brief.json, content_plan.json, evidence_plan.json,
# asset_plan.json, notes.md, outline.json
python3 scripts/build_workspace.py --workspace decks/my-deck --qa --overwrite
```

For final reusable/report decks, make planning warnings block before render:

```bash
python3 scripts/build_workspace.py \
  --workspace decks/my-deck \
  --qa \
  --fail-on-planning-warnings \
  --fail-on-whitespace-warnings \
  --overwrite
```

Before spending time on a render, especially after resuming someone else's
workspace, run the fast source-only readiness report:

```bash
python3 scripts/report_workspace_readiness.py \
  --workspace decks/my-deck
```

It writes `build/workspace_readiness.json` plus the scannable
`build/workspace_readiness.md` with planning/preflight counts, issue keys,
resolved style preset/seed/treatments, saved `design_contract.json` apply
status, style-mix pool names/values and multi-entry counts, contract QA
checks, acceptance-evidence file status, existing
build-report summary, outline composition/variant/anchor
coverage, deck-start `execution_plan` current phase, artifact-manifest output
alias triplets, bound slide/variant targets, unbound generated artifact IDs,
generated figure-quality counts and measured exterior whitespace,
source-coverage recommendations, deck-start source-inventory summaries,
local tabular-data and PPTX-style
extraction/apply status, recommendation details such as slide IDs and
planning paths, suggested fields, warning types, or variants, a prioritized
`next_action`,
recommended next commands, and a
`ready` / `needs_attention` / `blocked` status. The JSON also includes a
top-level `quality_context` so downstream agents can reuse the same compact
text-size, whitespace, evidence-anchor, artifact-metadata, and QA-gate targets.
It also includes a top-level `artifact_context` so resumed agents can reuse the
same compact generated-artifact manifest, analysis-summary paths, alias triplets,
figure-quality counts, selection bindings, unbound output IDs, and tabular-data
inputs without reopening the nested `artifacts` block.
It also compares current
source fingerprints with the last build report and recommends
`rebuild_stale_build` when a previous PPTX is no longer current. When the
last build report is still current, it also surfaces saved QA whitespace and
design/readability warnings as slide-level source-edit recommendations instead
of leaving only counts in the QA report. Use it to
choose the next source edit, artifact command, or rebuild command;
`ready` means no planning/preflight warnings and no open readiness
recommendations; `needs_attention` means warnings or recommendation details
should be addressed before final report/scientific delivery. Still run
`build_workspace.py --qa` for deliverables.

When resuming a workspace and speed matters, use the readiness-driven advancer
to execute command-type next actions or write the exact source-edit prompt for
the main agent:

```bash
python3 scripts/advance_workspace.py \
  --workspace decks/my-deck \
  --execute \
  --max-steps 3
```

Without `--execute`, it only writes `build/workspace_advance_report.json` and
`build/workspace_next_action.md`. With `--execute`, it runs deterministic
command-type actions once, reruns readiness, and stops with a source-edit prompt
when validators or slide-level recommendations require source edits instead of
another command. Planning and preflight warnings/errors stop directly with a
source-edit prompt because readiness has already run the validators and carries
the affected paths or slide IDs, warning types, suggested source fields, and
current deck-start `execution_plan` phase plus the copyable command for that
phase when one is available. When intake answers are missing, the prompt also
includes the compact question list and `intake_answers.json` template. The
advance report includes
`source_edit_plan` entries such as `outline.json` plus `slides[3].sources`, so
the next agent can patch the right source field without re-deriving slide
indexes from the rendered deck. It also carries a `quality_context` summary and
`## Quality Context` prompt section from `slide_quality_contract_v1` and outline
`quality_alignment`, so the next source edit can preserve readable text sizes,
footer reserve, evidence-anchor policy, artifact metadata expectations, and QA
gates without reopening the design or outline handoff JSON. It also carries
`artifact_context` in the final report and each step, and writes a
`## Artifact Context` prompt section with generated output IDs, aliases,
figure-quality counts, auto-bind command, bound slide/variant targets, and
tabular-data paths. When the execution
plan has reached
`author_outline_from_contract` but the outline is still starter-like, readiness
blocks with an explicit source-edit plan for `outline.json`,
`content_plan.json`, `evidence_plan.json`, and `asset_plan.json`, plus a
copyable `scripts/emit_outline_authoring_prompt.py` command that writes
`build/outline_authoring_prompt.md` for a contract-aware main-agent handoff.
When `outline_authoring_handoff.json` exists but has not been applied or has
changed since apply, readiness prioritizes
`scripts/apply_outline_authoring_handoff.py` before generic outline editing.
Planning
warnings map to source fields such as
`design_brief.json` `readability_contract.*`, `speed_contract.*`,
`figure_export_contract.*`, generated-artifact registry entries,
`analysis_artifact_plan.analysis_summary.*`, `evidence_plan.json`
`source_policy`, and stale slide references, so contract cleanup is a source
patch rather than another blind validation run. Generated-artifact fingerprint
or producer-script warnings should carry the artifact manifest path, affected
output IDs, reusable `image:`/`chart:`/`table:` aliases, analysis-summary
files, metadata fields, and available binding
command in the source-edit handoff so stale chart/table/figure artifacts can be
rebuilt or rebound without re-discovering the artifact graph. The
`workspace_next_action.md` artifact context also preserves generated
figure-quality counts and per-alias exterior-whitespace status, so a resumed
agent can decide whether to trim/regenerate a plot before binding or rebuilding.
When local data,
producer scripts, or generated outputs drift, readiness should prefer
`refresh_generated_artifacts`; with `advance_workspace.py --execute`, that
reruns the deterministic fast-first-pass producer, rebinds the artifact
manifest, rebuilds render-free QA, and reruns readiness before handing control
back. If a
generated artifact manifest exists but `artifact_selections.auto.json` is
missing or stale, readiness prioritizes the manifest-binding command before
generic planning-warning cleanup, and `advance_workspace.py --execute` can run
that binding and rerun readiness to reach a clean source state. If scaffold or
artifact-binding commands fail or repeat, the advancer preserves a recovery
source-edit plan with the command, data paths, manifest, selection file,
analysis summaries, aliases, output IDs, and manifest/selection errors so the
next agent can repair source inputs instead of rediscovering the artifact
graph. When local tabular data exists but no generated artifact manifest exists
yet, readiness can choose `scaffold_data_artifacts`; with `--execute`, the
advancer runs the fast scaffold/auto-bind/build/QA path and reruns readiness
before handing control back to the agent. When `deck_start_packet.json` exists
but `intake_answers.json` is missing, readiness writes a source-edit handoff for
recording explicit answers or best-judgment assumptions; when
`intake_answers.json` exists but has not been applied or changed since apply,
readiness can choose `apply_deck_intake_answers`; with `--execute`, the
advancer persists `design_brief.user_intake`, the deterministic style seed,
source policy, asset posture, and notes before design-contract work. When a
deck-start execution plan reaches `lock_design_contract` after intake answers
are applied and no contract exists yet, readiness/advance stops on
`author_design_contract_from_prompt`, includes the packet's
`emit_design_contract_prompt.py` command, and writes a source-edit plan for
`design_contract.json`, choice resolution, source policy, and asset posture.
When a workspace contains `design_contract.json`
that is missing from `design_brief.design_contract`, has changed since apply,
or was applied before fingerprint metadata existed, readiness can choose
`apply_design_contract`; with `--execute`, the advancer runs the deterministic
contract applicator before later planning/build actions. When a workspace
contains a reference PPTX or an unapplied/stale `style_extract_design_brief.json`,
readiness can choose
`extract_pptx_style` or `apply_pptx_style_fragment`; with `--execute`, the
advancer runs the deterministic style extraction/apply command pair and reruns
readiness before later planning/build actions. When a workspace contains a
`data_analysis_handoff.json` scout output that is unapplied or stale, readiness
can choose `apply_data_analysis_handoff`; with `--execute`, the advancer
applies binder-compatible artifact selections and evidence updates before
later planning/build actions. Saved QA
whitespace warnings map to
`slides[n]` operations such as rebalancing content, adding an evidence anchor,
or choosing a deliberate sparse variant, and carry likely source fields plus
measured span/dead-space ratios when available; saved design/readability
warnings map to source edits such as increasing text size, reducing dense
tables, restoring footer reserve, or adjusting chart label options. Saved visual QA and
visual-review warnings map to source edits for underfilled containers,
repetitive composition families, missing visual anchors, or clearance risks.
When changing these saved QA warning mappers, readiness recommendation
priority, or `advance_workspace.py` source-edit prompt formatting, run
`npm run check:layout-polish` before broader workflow/regression suites.
When changing `design_rules_qa.py`, `readability_contract` enforcement,
chart/table rendered text-size checks, or chart/table design-warning source
handoffs, run `npm run check:readability-contract`.
If the latest current build report records a failed strict QA step but no
slide-level warning mapper owns it, the advancer writes a failed-build
inspection source-edit plan with the failed step, return code, QA counts, and
report path instead of blindly rerunning the same strict build.
Preflight chart/table/figure/readability warnings map to source-edit
operations with suggested outline fields and fix text, so dense scientific
evidence slides can be patched from source rather than interpreted from a
generic warning count.

After the strict build, write a final delivery audit before handing off the
PPTX:

```bash
python3 scripts/report_delivery_readiness.py \
  --workspace decks/my-deck
```

It writes `build/delivery_readiness.json` and
`build/delivery_readiness.md`. A `ready` delivery status requires source
readiness, a build report whose source fingerprints still match the current
workspace, an output PPTX fingerprint, QA, zero blocking QA counts, and strict
planning/whitespace warning gates. If `design_brief.json` or `qa_contract`
declares `acceptance_evidence`, the delivery audit also verifies the promised
proof files, treats its own current delivery report as self-generated evidence,
and blocks with `complete_acceptance_evidence` when any other declared proof is
missing. When delivery is blocked or needs attention, the report carries a
delivery-level `recommended_next_action` and a Markdown Next Action section
with the command or `advance_workspace.py` source-edit handoff to run next.
When saved build-report warning counts remain after source readiness is
otherwise clean, delivery readiness inspects the saved planning/preflight/QA
report payloads and carries concrete warning rules and likely source fields in
the recommended action instead of only generic count names. When source
readiness is the blocker, delivery
JSON, Markdown, and `advance_delivery.py` prompts preserve the source action's
slide IDs, planning paths, warning types, and suggested fields so the next
agent can patch the right source fields instead of re-inspecting the whole
workspace. Delivery JSON and Markdown also preserve the source readiness
`phase_proof_ledger` summary, including gate counts, route-required phases,
proof path counts, and proof-file existing/missing counts, so final handoff
keeps the deck-start proof trail visible without reopening the start packet.
They also preserve compact deck-start source inventory counts/paths and the
resolved seeded header-treatment summary from `build/outline_resolved.json`,
so final handoff shows which local data/style routes and lab-report heading
variants drove the current PPTX.
Delivery JSON and Markdown also preserve the applied design-contract replay
ledger (`deck_reproducibility_contract_v1`) with style seed, renderer, locked
field count, replay commands, background/style treatment pools, slide-variant
mix, and artifact manifest/analysis-summary paths, so final handoff keeps the
same reproducibility contract visible without reopening `design_brief.json`.
Delivery JSON and Markdown also preserve a compact generated-artifact context
with artifact manifest/selection paths, output IDs, analysis-summary paths,
figure-quality counts, slide/variant binding targets, and short alias details,
so final report handoffs keep chart/table/figure provenance visible without
dumping the full manifest.
Delivery JSON, Markdown, and `advance_delivery.py` prompts also preserve the
quality context from readiness: the applied `slide_quality_contract_v1` plus
the outline handoff's `quality_alignment`, so final reviewers can see text
floors, whitespace/evidence-anchor policy, artifact metadata expectations, and
QA gates without reopening the design or outline handoff JSON.
They also preserve the latest build's compact speed summary: total duration,
renderer, fast-first-pass/rendered-review flags, longest step, and render/QA
timings, so speed regressions are visible without parsing console logs.
They also preserve compact layout-density evidence from QA, including content
slide counts, min/average/max density, low-density slide references, and the
density-score source report, so clean-page-use checks stay visible in final
delivery handoffs. When the applied slide-quality contract has
`fail_on_awkward_whitespace`, low content-density slides become a
`layout_density_low` delivery warning with source-edit fields and slide
references instead of a passive metric.
`advance_delivery.py` also includes the workspace advancer's
`source_edit_plan` in its JSON report, final edit-sources step, and Markdown
prompt when the delivery blocker comes from source readiness or from saved
build-report planning/preflight/QA warning counts. Missing declared acceptance
evidence gets the same source-edit treatment, with the exact missing proof
files and `design_brief.json` fields to repair. Readability/design QA
handoffs preserve concrete measurements such as role, rendered font size,
minimum allowed font size, footer intrusion, table dimensions, or chart
headroom when those values are present, so delivery prompts point to the source
field and the measured reason to edit. Whitespace QA handoffs preserve
content-span and dead-space ratios in the same prompt, so sparse lab/report
slides can be fixed from source without reopening the QA JSON first. The
source-readiness action is preserved
separately, so a clean fast first pass can still recommend the strict final
build before delivery. Use
`--allow-skip-render` only when LibreOffice/rendering is unavailable and the
deliverable must rely on render-free QA. When the route ledger marks
`rendered_visual_review` active, the delivery audit automatically requires the
latest final build to have run `--visual-review`; use
`--require-visual-review` as an explicit override for workspaces without a
saved route ledger when a rendered contact-sheet review should be part of final
acceptance.

To turn the delivery audit into a reproducible handoff, run:

```bash
python3 scripts/advance_delivery.py \
  --workspace decks/my-deck
```

It writes `build/delivery_advance_report.json` and
`build/delivery_next_action.md`. Without `--execute`, it reports the immediate
delivery-level command or source-edit handoff, such as the strict final build
after a fast first pass or an `inspect_delivery_warnings` source-edit prompt
when only build-report warning counts remain. It also preserves the delivery
audit's visual-review requirement summary, including whether rendered review is
required by the route ledger, by CLI, or both, so a resumed agent can run the
right final build without re-inspecting the packet. It carries the delivery
audit's `phase_proof_ledger`, reproducibility contract, source-inventory,
resolved-treatment, layout-density, and generated-artifact context summaries
into the JSON report, step ledger, and Markdown prompt. Pass
`--no-refresh-readiness` only when intentionally resuming from a known saved
readiness report instead of refreshing source readiness first. With `--execute`,
it runs command-type delivery actions and reruns
delivery readiness; use that only when the environment is ready for final
rendering or when render-free delivery has been explicitly accepted with
`--allow-skip-render`.

If the user wants a nuanced/personalized deck and has not specified audience,
style, palette, density, background/imagery, assets, source policy, or hard
constraints, run the start packet before planning. It is the preferred entry
point for reproducible deck work because it pairs the first question card with
the design-contract scout and subagent handoff instructions:

```bash
python3 scripts/emit_deck_start_packet.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request here"
```

Call `request_user_input` with the packet's `request_user_input` object when
that tool is available, then read `agent_kickoff_brief` before any source
edits. It is the versioned first-turn operating contract: it records the
question trigger, active route snapshot, locked replay fields, required
`deck_design_contract_v1` / `deck_reproducibility_contract_v1` /
`outline_authoring_handoff_v1` outputs, artifact/style obligations, command
ladder, acceptance gates, next steps, and no-go rules. Use
`main_agent_kickoff_prompt` as the concise handoff prompt for the main agent or
for a scout. Use `subagent_prompt` when a design scout should produce the
strict JSON design contract; it includes the kickoff brief plus the full
design-contract and choice-resolution ledgers. If the deck is quick/simple, the
main agent may answer the contract directly. If the deck is high-stakes, paste
the prompt into one style scout and apply the returned JSON before authoring
the outline. Use the packet's `recommended_style_seed` as
`style_system.style_seed` unless the user explicitly supplied a different
seed; record any override in `notes.md`.
Use the packet's top-level `execution_plan` as the ordered main-agent workflow:
each phase names the trigger, owner, commands, files written, and continue
condition from intake through final delivery. Use the packet's
`application_contract` as the main-agent checklist for
persisting intake answers, translating them into design/evidence/asset plans,
and running the fast first-pass, rendered visual-review, and final report QA
commands. Use the packet's top-level `choice_resolution_contract` as the
decision ledger that maps compact question-card answers into source fields,
active data/style routes, style-mix choices, source policy, artifact burden,
and the `design_contract.json` `choice_resolution` object. Use the packet's
top-level `route_decision_ledger` as the replayable routing audit for intake,
design-contract, data-artifact, PPTX-style import, research, source-footer
compaction, and rendered visual-review routes; copy active routes into
`choice_resolution.route_decisions` or record why a conditional route was
skipped. When the ledger marks `rendered_visual_review` active, readiness and
advance reports count the rendered-review phase as required until
`build/qa/visual_review/visual_review.json` exists. Use the packet's top-level
`slide_quality_contract` as the compact QA target for the design contract and
outline: it locks text-size floors, prose budgets, source-footer reserve,
awkward-whitespace policy, evidence-anchor expectations, generated-artifact
metadata, and required QA commands before slide authoring. Map it into
`readability_contract`, `qa_contract`, `figure_export_contract`, and
variant choices instead of relying on prose such as "clean" or "readable".
`scripts/apply_design_contract.py` persists the returned
`slide_quality_contract` into `design_brief.json`, notes, and readiness
summaries, so keep that object intact when a design scout returns it.
Use the packet's top-level
`acceptance_checklist` as the evidence ledger for handoff: each gate names the
source files, reports, and commands that prove intake, design contract,
generated artifacts, readiness, first-pass QA, and final delivery status.
Use the packet's top-level `phase_proof_ledger` when resuming or auditing a
deck-start workflow: it maps every execution phase to the exact commands,
source files, reports, and acceptance gates that prove the phase is complete.
Readiness and advance reports surface a compact `phase_proof_ledger` summary
with route-required phases, acceptance gate IDs, proof counts, and status
sources, plus proof-file existing/missing counts, so a resumed agent can
continue without reopening the start packet.
To keep the question-card step reproducible, persist the returned answers to a
small JSON file and apply them before the design contract:

```bash
python3 scripts/apply_deck_intake_answers.py \
  --workspace decks/my-deck \
  --packet decks/my-deck/deck_start_packet.json \
  --answers decks/my-deck/intake_answers.json \
  --report decks/my-deck/intake_apply_report.json
```

The helper fills `design_brief.user_intake`, carries the packet style seed into
`style_system.style_seed`, writes `design_brief.choice_resolution_seed` from
the actual question-card answers and active packet routes, translates
compressed UI answers into source policy, density, visual-system, and
asset-posture fields, and replaces a marked section in `notes.md`
idempotently. The seed also preserves the packet's `route_decision_ledger` and
fingerprinted `workspace_source_inventory`, so the design scout can replay why
data, style-import, research, source-footer, and visual-review routes were
active or skipped. Continue with the
design-contract scout after this source layer is written, and copy/refine
`choice_resolution_seed` into the returned `design_contract.json`
`choice_resolution`. The start packet also emits
`after_answers.answer_file_template`, `after_answers.apply_answers_command`,
`after_answers.apply_design_contract_command`, and matching
`application_contract.*_commands`, including `visual_review_commands` for a
contact-sheet QA build plus `--require-visual-review` delivery audit; prefer
those emitted paths when the packet was saved somewhere other than the default
workspace path. Readiness and next-action Markdown show the same compact source
inventory, so a resumed agent can see local data, reference PPTX, and
artifact-ledger paths without reopening the long packet JSON. After the design
scout or main agent returns valid `deck_design_contract_v1` JSON, save it to
the emitted `design_contract.json` path and run the emitted
`scripts/apply_design_contract.py` command before authoring `outline.json`.
When changing deck-start packets, compact question-card mapping, intake answer
application, choice-resolution seeding, or readiness `deck_intake` summaries,
run `npm run check:deck-start` before broader renderer/regression suites.
When changing `emit_design_contract_prompt.py`, `apply_design_contract.py`,
choice-resolution enrichment, contract-owned planning fields, or readiness
`design_contract` summaries, run `npm run check:design-contract`.
For a structured source-edit handoff at that point, run:

```bash
python3 scripts/emit_outline_authoring_prompt.py \
  --workspace decks/my-deck \
  --output decks/my-deck/build/outline_authoring_prompt.md
```

Use the returned `outline_authoring_handoff_v1` shape to patch
`outline.json`, `content_plan.json`, `evidence_plan.json`, `asset_plan.json`,
and `notes.md`; do not let a subagent write the final deck without main-agent
verification. When generated artifacts exist, the prompt also includes
`presentation_skill_artifact_rebuild_context_v1` and asks for an
`artifact_rebuild_plan`, so outline authors preserve rebuild, inspect,
auto-bind, and validation commands while choosing slide IDs and variants. Save
that JSON as `outline_authoring_handoff.json` and apply it deterministically;
the applicator records the plan in
`design_brief.outline_authoring_handoff.artifact_rebuild_plan` and mirrors it
under `analysis_artifact_plan.outline_authoring_rebuild_plan` for resumed
workspace handoff. The prompt also exposes `slide_quality_contract_v1` and
requires a `quality_alignment` block. The applicator persists that block under
`design_brief.outline_authoring_handoff.quality_alignment`, notes, and
readiness summaries so outline choices stay tied to concrete text-size,
whitespace, evidence-anchor, artifact-metadata, and QA-gate constraints:

```bash
python3 scripts/apply_outline_authoring_handoff.py \
  --workspace decks/my-deck \
  --handoff decks/my-deck/outline_authoring_handoff.json \
  --report decks/my-deck/outline_authoring_handoff_apply_report.json
```

When changing `emit_outline_authoring_prompt.py`,
`apply_outline_authoring_handoff.py`, outline handoff schema, or readiness
`outline_authoring_handoff` summaries, run `npm run check:outline-handoff`.
When changing the deck-start-to-delivery workflow, strict render-free final
build path, or delivery-readiness handoff expectations, run
`npm run check:workflow`.
When a change touches multiple workflow lanes, or before handing off a broad
skill improvement, run `npm run check:focused` for the aggregate fast suite;
the npm command uses `--jobs 4` because the focused smokes use isolated
temporary workspaces. Use `npm run check:focused -- --jobs 1` for serial
debugging, or `--fail-fast` when the first failure is enough. Choose whether
the heavier `check:pptxgenjs-regression` is needed after the focused report;
its summary records total duration, slowest cases, and per-case normalized
PPTX content fingerprints for renderer-level reproducibility audits.

For only the user-facing questions, run the optional intake prompt:

```bash
python3 scripts/emit_deck_intake_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request here" \
  --mapping
```

If the native Codex `request_user_input` question tool is available in the
current mode, prefer it immediately after the user's deck prompt:

```bash
python3 scripts/emit_deck_intake_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request here" \
  --codex-ui
```

Call `request_user_input` with the emitted JSON packet's `questions` and
`autoResolutionMs`. If that tool is unavailable, ask the same top questions in
chat. Ask only the highest-value missing questions. If the user says "use best
judgment" or does not answer before auto-resolution, do not block the deck;
record explicit answers or assumptions under `design_brief.user_intake`, then
translate them into `design_modulation`, `visual_system`,
`title_page_concept`, `deck_style`, `asset_plan`, and `notes.md` as applicable.

Immediately after the original deck request, or after intake answers if asked,
emit a reproducible design-contract prompt before writing `outline.json`:

```bash
python3 scripts/emit_design_contract_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request here"
```

Use the returned JSON contract as the first lock on preset, palette,
background system, title/header/footer treatments, structure blueprint, source
policy, asset posture, continuity rules, mix-and-match replay choices, and QA
gates. The returned contract should include a
`deck_reproducibility_contract_v1` replay ledger that binds the stable seed to
the selected background, header/footer pools, chart/table/figure treatments,
slide-variant mix, artifact manifest/summary paths, replay commands, and
acceptance evidence. The main agent may answer the prompt directly for simple
decks or paste it into one style scout for high-stakes decks; either way, save
the resulting contract as
`design_contract.json` and run:

```bash
python3 scripts/apply_design_contract.py \
  --workspace decks/my-deck \
  --contract decks/my-deck/design_contract.json \
  --report decks/my-deck/design_contract_apply_report.json
```

Use `--preserve-existing` only when layering a new scout contract onto a
workspace that already has deliberate human edits. The applicator records the
contract metadata and any `choice_resolution` ledger into
`design_brief.design_contract`, maps supported renderer
treatments, style mix pools, readability/speed contracts, structure blueprint,
source policy, artifact contracts, asset posture, QA contracts, subagent
handoffs, execution phases, acceptance evidence, and notes before final
outline authoring. It also writes a compact notes ledger for style treatment
pools, mix rules, source/footer posture, local-data needs, artifact manifests,
analysis summaries, rebuild commands, required checks, fail-on conditions,
acceptance evidence, and handoff phases so the next agent can resume without
re-opening the full contract JSON first. The prompt
includes the recommended deterministic style seed, which should be copied into
`style_system.style_seed` so treatment rotation is reproducible across rebuilds.
The applicator persists the replay ledger into `design_brief.json` and
`notes.md`, filling a compatible ledger from the design contract when a scout
omits it, so a resumed agent can rebuild the same style/background/structure
choices without reopening the full prompt.
It also includes a compact workspace source inventory: local tabular/data files,
reference PPTX candidates, artifact ledgers, file sizes, and SHA-256 hashes for
small files. Use that inventory to lock active data/style routes, artifact
contracts, and source fingerprints instead of asking a scout to infer which
workspace files exist.
During workspace builds, renderer-visible deck style defaults from
`design_brief.json` are written to `build/outline_resolved.json`, and
`style_system.style_preset` becomes the renderer/QA preset, with scaffolded
`visual_system.style_preset` supported as the compatibility source. Explicit
unsupported preset values and conflicting explicit preset declarations are
planning/build errors. Unsupported direct renderer treatments such as
`header_variant`, `title_layout`, `footer_mode`, and `header_variants` are
also preflight errors, direct `pptxgenjs` renderer errors, and block QA/strict
workspace builds. Supported `style_mix_matrix` treatment pools are resolved
deterministically from `style_seed` into title/footer/section/timeline/matrix/
stats/cards/chart/callout/figure-table defaults, while explicit
`outline.deck_style` values still win for deck-style fields. Unchanged resolved
outlines are preserved byte-for-byte so repeat builds do not churn
deterministic workspace artifacts. The resolved outline also records generated
`resolved_treatments.header_variant` entries and a
`resolved_treatment_summary` for lab/report slides, so readiness and advance
Markdown can show which seeded heading/accent-rule variants will render before
spending time on visual review. Planning validation warns when a
`style_mix_matrix` is present but no explicit `style_seed` is recorded, when
the header pool has fewer than two unique supported variants, or when fewer
than two treatment pools contain two or more unique supported entries.
New workspaces also record `style_system.preset_treatment_profile` from
`scripts/style_treatment_profiles.py`; design-contract prompts and deck-start
packets surface the same `deck_preset_treatment_profiles_v1` profile so scouts
can preserve preset-specific heading/accent, footer, chart, and figure/table
pools instead of inventing unsupported treatments. The profile also carries
`renderer_treatment_defaults` and a `renderer_treatment_signature`, a compact
replay/audit key for the selected title, footer, chart, table, figure, stats,
matrix, and summary-callout posture. Design-contract prompts must preserve
that signature in `style_system`, `choice_resolution`, and
`reproducibility_contract.style_replay`; `apply_design_contract.py` will
synthesize it from supported fields when older contracts omit it. That profile
embeds a
`style_reference_catalog_v1` reference from
`scripts/style_reference_catalog.py`, which acts as the preset's publish-safe
style memory: title, comparison, chart, table, figure, dashboard, decision, and
references treatment rules, plus style DNA, signature moves, and anti-patterns.
Each reference also carries `style_reference_example_storyboard_v1`, a
publish-safe synthetic topic with chart labels, dashboard facts, table rows,
figure/sidebar sections, comparison states, decision rows, and source notes, so
gallery decks and design scouts vary actual content grammar rather than only
renderer chrome.
It also carries `style_reference_mix_plan_v1` and
`style_reference_layout_playbook_v1`: the mix plan chooses one primary
reference plus bounded secondary influences for hybrid prompts, while the
playbook defines preferred variants, treatment-to-variant mappings, gallery
showcase variants, treatment-level `treatment_archetypes`, opening sequence,
content rules, and variants to avoid. The `treatment_archetypes` entries name
the opener, comparison, chart, table, figure, dashboard, decision, and
source/provenance posture, so presets differ in body-slide grammar and
footer/reference behavior even when two presets share a renderer variant such
as `chart`, `table`, or `comparison-2col`.
Each reference also carries `style_reference_structural_motif_library_v1`,
with the preset's background structure, layout motifs, content-object rules,
and motif signature. Treat this as the first guard against same-looking
presets: the motif grammar decides whether the deck is an evidence rail,
workflow workbench, atlas plate, command console, lab run report, editorial
masthead, or case-study journey before colors and header chrome are chosen.
Each reference also carries `style_reference_metric_profile_v1`, with the
preset's density level, whitespace target, body-word budget, maximum primary
object count, visual hierarchy, chart/table/figure/prose mix, source burden,
footer posture, artifact bias, readability bias, and replayable metric
signature. Treat this as the guard against applying the same body-slide
density and object count to every preset.
The same reference carries `style_reference_content_recipe_library_v1`, with
one recipe for each treatment key. These recipes name required content slots,
data roles, supported primary variants, source posture, authoring checks, and
a replayable recipe signature so chart/table/figure/dashboard/decision slides
are structurally different for each preset before any renderer chrome is
applied. Every recipe also carries the selected treatment archetype signature.
Outline-authoring handoffs should record selected recipes in
`contract_alignment.content_recipe_library_used.slide_recipe_map` and record
the used archetypes in
`contract_alignment.layout_playbook_used.treatment_archetypes_used`.
Fresh workspaces created by `scripts/init_deck_workspace.py` use
`style_reference_starter_outline_v1`: after the stable title/core-message
starter, the outline includes a few synthetic preset-specific scaffold slides
marked `starter_kind: style_reference`. Treat them as reusable style memory and
replace them with topic-specific sourced content before delivery. The
initializer also writes deterministic local starter assets under
`assets/style_reference/` and `assets/icons/` so image-sidebar,
scientific-figure, flow, matrix, and card scaffolds can render without network
or proprietary media.
Preset profiles also carry chart, table, and figure/table treatment pools;
use `table_treatment` values such as `compact-ledger`, `readout-sidecar`,
`decision-matrix`, and `journal-grid` when an editable table needs a distinct
report, dashboard, decision, or editorial posture.
Treat the profile/reference as the starting point and refine it only inside
supported renderer fields. The design-contract prompt and outline-authoring
prompt must use the primary playbook so presets change actual slide structure,
not only header chrome or color; any secondary borrowed treatment must be
recorded in `choice_resolution`. During `build_workspace.py`, the same
playbook is also applied to `build/outline_resolved.json`: compatible generic
source slides can resolve to preset-specific variants such as
`lab-run-results`, while explicit source variants remain authoritative. The
resolved choices are auditable in
`resolved_treatments.style_reference_layout`, including the selected reference
ID, treatment key, source/resolved variant, content-recipe library version, and
content-recipe signature.
When using web slide decks, public PPTX files, screenshots, or template
galleries as inspiration, follow `references/style_reference_catalog.md`: store
only license-clear assets with attribution or reconstructed synthetic
descriptors/examples with generic content. Do not bundle proprietary source
slides, screenshots, branding, private data, or distinctive copied geometry.
Record any reusable public-source route in
`references/style_reference_sources.json` and validate it with
`python3 scripts/style_reference_sources.py --validate`; each preset route
must name source URLs, rights posture, source-verification evidence, allowed
extraction modes, forbidden materials, generic style observations, reusable
slide pattern extracts, attribution policy, and the synthetic content required
to replace the original deck material. The emitted `style_source_intake` field travels
with `style_reference_catalog_v1` references and gallery metadata, so scouts
can see what may inspire a preset without treating public sources as bundled
templates.
When changing the synthetic reference catalog, prompt-to-reference matching,
or required content-treatment coverage, run `npm run check:style-reference`.
That check covers all loadable presets with prompt-routing score/margin probes
plus hybrid mix-plan secondary-influence probes, not only schema validity.
When changing generated reference-gallery examples, catalog-to-outline mapping,
or the actual synthetic decks used as style memory, run
`npm run check:style-reference-gallery`; it now builds all loadable presets
and verifies per-preset treatment coverage plus unique first-four content
signatures.
When changing rendered gallery release evidence, contact-sheet creation,
visual-diversity hashing, treatment-level layout floors, or release comparison
artifacts, run `npm run check:style-reference-release`.
When changing style-reference starter scaffolds, starter asset creation, or
preset-specific scaffold signatures, run
`npm run check:style-reference-starters`.
When changing build-time style-reference layout resolution, playbook treatment
maps, generic-to-specific variant compatibility, or resolved-outline metadata,
run `npm run check:style-reference-resolution`.
When changing prompt-to-style routing, style/content scout output shape, or
router subagent guidance, run `npm run check:style-router`. When changing the
style atom atlas, atom router, atom applier, deterministic fallback, or
corpus-to-grammar bridge, run `npm run check:style-atoms`.
When changing the large public deck corpus source manifest, descriptor schema,
overlap balancing, compact LLM context, or digest writer, run
`npm run check:large-style-corpus`. When changing corpus contact sheets or
router leverage evidence, run `npm run check:large-style-corpus-leverage`.
When changing design-catalog selection, random-topic corpus comparison decks,
release-evidence manifests, generated data examples, or baseline-vs-corpus
contact sheets, run `npm run check:design-catalog` and
`npm run check:random-topic-comparison`.
When changing style pools, header variants, or seed handling, run
`npm run check:style-mix` for a fast init/validate/build/readiness smoke plus
lab-report header-variant gallery build/QA coverage before the full
`check:pptxgenjs-regression` suite.
When changing header-variant fixture structure, preset portability, or clean
gallery preview copy, run `npm run check:header-gallery`; it builds the same
six heading/accent-rule treatments across every current preset and expects zero
overflow, placeholder, geometry, whitespace, visual, or design QA counts.
When the change could affect the actual rendered look of those variants, run
`npm run check:rendered-gallery` or
`python3 scripts/run_focused_workflow_checks.py --profile rendered`; this
slower lane renders every preset, verifies nonblank slide images/contact sheet,
and runs warning-free lab-report visual review.

For non-trivial, researched, or asset-heavy decks, especially lab/scientific
decks, run one deck-level style/content scout before finalizing the outline:

```bash
python3 scripts/emit_style_content_router.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request here"
```

Paste the emitted prompt into a fresh Explore subagent. Use the returned JSON
to constrain `design_brief.json`, `deck_style`, slide variants, and asset needs.
Do not spawn one subagent per slide for variant picking.

When a user supplies an existing PPTX, a folder of example decks, or asks to
learn from a deck style without mutating the source deck, extract measurable
style signals before planning:

```bash
python3 scripts/extract_pptx_style.py \
  --input template.pptx \
  --report decks/my-deck/style_extract_report.json \
  --markdown-report decks/my-deck/style_extract_report.md \
  --design-brief-fragment decks/my-deck/style_extract_design_brief.json

python3 scripts/apply_pptx_style_fragment.py \
  --workspace decks/my-deck \
  --fragment decks/my-deck/style_extract_design_brief.json \
  --report decks/my-deck/style_fragment_apply_report.json
```

For a corpus, pass a directory and `--recursive` if needed. The extractor
records slide size, source/footer and page-number patterns, header-rule
signals, palette candidates, text-size observations, chart/table/image counts,
and a deterministic `style_seed`. It also emits fast/rendered
`build_header_variant_gallery.py` preview commands for the extracted preset
and header-variant pool. The applicator writes the bounded fragment into
`design_brief.json`, maps renderer-visible choices into `renderer_treatments`,
records `style_import`/`style_observation`, stores workspace-local preview
commands, and updates `notes.md` idempotently. Use `--preserve-existing` when
applying to a workspace that already has deliberate style choices. Then run the
normal design-contract or style/content scout; do not clone arbitrary template
XML or unsupported per-slide geometry.

For direct style QA, `scripts/build_header_variant_gallery.py --qa` builds the
current gallery decks before running render-free QA, and `--render` builds
before emitting slide JPEGs and a contact sheet. Its `summary.json` records
per-preset outline, PPTX, normalized PPTX content fingerprint, QA, render, and
command paths so a later agent can reproduce and compare the same variant
preview.

When factual substance or local data drives the deck, use the dedicated scouts
before routing: `scripts/emit_content_research.py` for generic/hedged claims
and `scripts/emit_data_analysis_prompt.py` for local datasets, result tables,
chart candidates, or lab run data. Subagents provide punch lists or JSON
constraint layers; the data scout includes a fingerprinted source inventory
with file sizes, SHA-256 hashes for small files, lightweight CSV/TSV/JSON
previews, existing artifact-manifest context when present, binder-compatible
`artifact_selection_recommendations.bindings`, the versioned artifact rebuild
context and exact rebuild/inspect/auto-bind/validate commands when a generated
manifest exists, and a `main_agent_handoff` with source files, commands, and
verification evidence. Save the returned scout JSON
and run
`scripts/apply_data_analysis_handoff.py` to persist the deterministic binding
and evidence-plan pieces before manual script edits. The applicator also copies
scout `data_inventory` paths and fingerprints into
`design_brief.analysis_artifact_plan.candidate_data_files` and
`data_source_fingerprints` so generated figures can be audited against the
exact source file version. The main agent verifies and applies the final source
edits. The apply report and readiness summary carry an
`artifact_evidence_ledger` with bound output IDs, target slide IDs, variants,
evidence IDs, script-edit paths, data source fingerprints, source/build checks,
verification evidence, and next commands, so resumed work can inspect one field
before deciding whether to edit scripts, bind more artifacts, or run QA.
When the scout returns structured `figure_export_contract`,
`asset_plan_updates`, or `artifact_registry_updates`, the applicator merges
those deterministic contract fields into `design_brief.json` and
`asset_plan.json` by stable IDs/paths without editing analysis scripts. Use
this path for scout-confirmed figure export targets, slide-readable crop rules,
editable chart/table asset entries, and artifact-registry provenance that
should survive future rebuilds.
When the scout returns `artifact_rebuild_context`, the applicator also
persists it under `design_brief.data_analysis_handoff.artifact_rebuild_context`
and `design_brief.analysis_artifact_plan.data_analysis_rebuild_context`, then
surfaces the context version, producer, and command count in readiness,
advance, build, and delivery handoffs. Use that persisted context to rerun,
inspect, auto-bind, and validate generated figures without reopening the full
scout response.
The applicator also preserves the scout's analysis ledger under
`design_brief.data_analysis_handoff.scout_analysis` and
`design_brief.analysis_artifact_plan.data_analysis_scout`. It carries
analysis tasks, computed findings, chart/table recommendations, outline
binding intent, quality flags, open questions, and the recommended workflow,
then surfaces compact counts plus target slide and variant previews in
readiness, build, advance, and delivery handoffs. Use that ledger to keep
data-driven slide decisions reproducible across resumes without copying the
whole `data_analysis_handoff.json`.
It also persists a compact `data_artifact_storyboard_v1` under
`design_brief.data_analysis_handoff.artifact_storyboard` and
`design_brief.analysis_artifact_plan.data_artifact_storyboard`, tying slide IDs,
variants, output IDs, artifact roles, data sources, figure scripts, and layout
quality targets together so later agents can reproduce why each
figure/chart/table evidence object belongs on a given slide.
When local tabular data has simple label/value or aligned multi-series columns
and should become a repeatable visual artifact, scaffold the first
deterministic figure script.
For a one-command workspace build, use the integrated path:

```bash
python3 scripts/build_workspace.py \
  --workspace decks/my-deck \
  --fast-first-pass
```

This is the fast first-pass route for converting local data into reproducible
figures, editable chart JSON, summary tables, and source-bound evidence
slides. It expands to scaffold data artifacts, auto-bind the recommended lead
evidence view with deferred support artifacts, run render-free QA, fail on
planning/whitespace warnings, and overwrite the first-pass PPTX. Pass
`--artifact-bind-mode all` when the first pass should place the full
figure/chart/table triplet instead.
`report_delivery_readiness.py` marks this as `fast_first_pass_not_final`; for
final delivery once source text and artifact bindings are stable, its
recommended next action points to the strict build without `--skip-render`.

For a separate scaffold/refine step, run:

```bash
python3 scripts/scaffold_figure_artifacts.py \
  --workspace decks/my-deck \
  --run \
  --bind-outline
```

Both paths create `assets/make_figures.py`, `assets/figures/*.png`,
`assets/charts/*.json`, `assets/tables/*_summary.json`,
`assets/artifacts_manifest.json`, `assets/analysis_summary.json`,
`assets/analysis_summary.md`, a shared
`presentation_skill_artifact_rebuild_context_v1` rebuild context,
`figure_export_contract`,
`analysis_artifact_plan`, and
`asset_plan.images`/`asset_plan.charts`/`asset_plan.tables` entries so slides
can use direct paths or staged aliases such as `image:<chart_id>_figure`,
`chart:<chart_id>`, or `table:<chart_id>_summary`. CSV/TSV/JSON/Parquet/
Feather tables produce one inferred chart each; Excel workbooks are scanned
sheet-by-sheet; aligned numeric columns become small multi-series chart JSON,
grouped/line figures, and compact summary tables usable in `lab-run-results`
or `table` slides. Parquet/Feather inputs require pandas with a compatible
columnar engine; missing engines are reported in the scaffold's `skipped`
entries.
Default data discovery ignores generated artifact outputs, staged assets,
`assets/artifacts_manifest.json`, and generated analysis summaries, so repeated
first-pass builds do not treat their own figure/chart/table outputs as new
source datasets. Pass `--data-path` explicitly only when a generated JSON file
is deliberately being used as a new source input.
Scaffolded slide titles use compact source-plus-metric labels, with Excel
workbooks preferring worksheet names such as `Run A: Signal + Ct` while the
workbook path and sheet provenance stay in captions, sources, manifests, and
artifact IDs.
When `build_workspace.py` also receives `--auto-bind-artifacts`, it applies
the generated manifest before planning validation, writes
`artifact_selections.auto.json`, and creates stable generated evidence slides
without a separate binding command. Its default mode is `all`, while
`--fast-first-pass` defaults to `--artifact-bind-mode lead`; use
`--artifact-bind-mode recommended` for layout-guided ordering across all
available variants.
When the manifest already exists from an earlier scaffold but the selection is
missing or no longer covers all outputs, `report_workspace_readiness.py` and
`advance_workspace.py --execute` choose
`scripts/apply_artifact_manifest_bindings.py --auto-select` before generic
planning-warning cleanup, because that deterministic binding step often clears
artifact slide-reference warnings.
Every workspace build that reaches render/QA also writes
`build/build_workspace_report.json`, even when strict QA fails. The
deterministic run ledger records `run.status`, the failed step/return code,
resolved renderer/preset, source-file fingerprints, artifact selections,
intake/design/style/data/outline handoff and apply-report fingerprints,
planning/preflight/QA report paths and counts, compact generated-artifact
context from the manifest/selection file, compact quality context from
`slide_quality_contract_v1` and outline `quality_alignment`, output PPTX
fingerprints, a `build_workspace_speed_v1` per-step timing ledger, and copyable
follow-up commands. Office-package snapshots include both raw `sha256` and
`office_package_normalized_v1` `normalized_sha256`; use the normalized hash to
verify repeat-build content stability when raw PPTX bytes drift because of
ZIP entry timestamps or Office core-property timestamps. The artifact context preserves
manifest output IDs, aliases, analysis-summary paths, figure-quality counts,
auto-bind commands, selected slide IDs, variants, and unbound output IDs.
Inspect that report first when continuing a deck from a prior run, polishing a
failed strict QA build, or debugging why a generated figure/table landed on a
slide.
For generated data artifacts, the source freshness ledger also fingerprints
declared source data files, producer scripts, generated figure/chart/table
outputs, and analysis-summary files from `assets/artifacts_manifest.json`.
When iterating on this generated-artifact path, including scout handoff
storyboards, run `npm run check:artifact-quality` for a fast
scaffold/inspect/bind/readiness smoke before spending time on the full
`check:pptxgenjs-regression` suite.
When changing generated figure whitespace metadata, trim guidance,
`inspect_artifact_manifest.py` figure-quality summaries, or
readiness/advance handoffs for high-whitespace figures, run
`npm run check:figure-whitespace`.
When changing the integrated `--fast-first-pass` path, generated artifact
source-freshness ledger, build report wiring, render-free data QA, or delivery
readiness behavior for first-pass data builds, run
`npm run check:data-workflow`.
When changing Excel workbook discovery, sheet-by-sheet scaffolding, workbook
provenance metadata, or generated artifact self-ingestion filters, run
`npm run check:excel-workflow`; it also proves multi-sheet generated artifact
context survives final delivery readiness and `advance_delivery.py` handoffs.
When changing full figure/chart/table binding, `--artifact-bind-mode all`,
generated triplet staging, native chart density/layout lint behavior, or final
delivery handoff context for figure/chart/table evidence triplets, run
`npm run check:artifact-triplet`.
When changing generated-artifact fingerprint validation, stale source-data
warnings, source-freshness reports, stale-build recommendations, or delivery
blocking/recovery behavior after local data changes, run
`npm run check:artifact-freshness`; it proves blocked delivery and
`advance_delivery.py` recovery prompts preserve generated-artifact context.
When changing the structured intake/design-contract-to-data path, final
rendered QA behavior, or delivery-readiness requirements for data-backed lab
reports, run `npm run check:rendered-data` or
`python3 scripts/run_focused_workflow_checks.py --profile rendered`; this
slower lane proves the full workflow reaches rendered visual review and
delivery `ready` with figure/chart/table artifact triplet bindings,
generated-slide density floors, delivery layout-density evidence, speed
timings, and repeat-build stability recorded.
The scaffold report includes an `alias_plan` with generated aliases,
copy-ready `outline_field_snippets`, `artifact_bindings`, deterministic
layout recommendations, `selection_templates`, and `commands.auto_select_lead`,
`commands.auto_select_recommended`, and `commands.auto_select_all` for
evidence-first slide variants, so use that report instead of guessing artifact
names, selected columns, or slide IDs. Prefer `auto_select_lead` for a fast
clean first pass and `auto_select_all` when the deck should include the full
figure/chart/table evidence triplet.
After choosing slide IDs, carry those IDs back into generated artifact
`used_on_slides` entries and figure-export `target_slide` fields so the outline
and registry remain auditable. The `--bind-outline` path and
`commands.auto_select_all` path do this automatically when the outline already
contains the generated aliases or when every generated output should become the
standard figure/chart/table evidence triplet.
Generated chart/table JSON and artifact-registry entries include
`analysis_metadata` with source path, source SHA-256, producer script path,
producer SHA-256, source/producer sizes, selected columns, rows used, series
count, point count, target box, figure export size, DPI, and label font
assumptions, plus measured `image_whitespace` for slide-ready PNGs when Pillow
is available, so later rebuilds can be audited without guessing which data and
script produced a figure, whether it was sized for slide-readable labels, or
whether it carries large exterior blank borders. The generated
manifest, `analysis_summary.json`, scaffold report,
`design_brief.analysis_artifact_plan`, and `figure_export_contract` also carry
the same rebuild context with source paths, output paths, producer/data-spec
hashes, and copyable rebuild/inspect/auto-bind/validate commands. The generated
`analysis_summary.md` surfaces that rebuild command and whitespace check next
to the alias list so agents can regenerate or trim a plot before binding it to
a slide.
Planning validation warns when generated artifacts carry basic source metadata
but omit those figure export/readability fields, when their recorded source
fingerprint no longer matches the current local source file, when
`analysis_artifact_plan.data_source_fingerprints` drift from current local data
files, or when a recorded producer fingerprint no longer matches the current
figure script. It also warns when recorded image whitespace crosses the
exterior-blank threshold, making figure cropping a source-planning fix rather
than a late visual-polish surprise, or when chart/table payloads are missing
the whitespace metadata already recorded by the manifest. Readiness and advance handoffs preserve the affected
`data_source_fingerprints` path plus recorded/current source hashes and sizes,
so the next agent can update the source ledger or rerun/apply the data scout
without rediscovering which dataset changed. Delivery readiness/advance prompts
carry the same source-edit details when final delivery is blocked by those
planning warnings. The generated
`assets/artifacts_manifest.json` is the single machine
readable index for scaffold outputs; it records each chart/figure/table alias,
path, artifact fingerprint, selected-column set, and source analysis metadata
so agents can inspect one file before deciding which evidence objects to place
on slides. `scripts/inspect_artifact_manifest.py` converts that manifest into
an alias plan with layout recommendations, binding snippets, selection
templates, and compact `figure_quality` status so whitespace/crop issues are
visible before slide binding. The
generated `assets/analysis_summary.json` and Markdown companion are the
human/agent first-read summary for source paths, selected columns, aliases,
row/point counts, and readability assumptions before outline binding. Planning
validation checks that the declared summary exists, has the expected schema,
and keeps source paths, output counts, dataset IDs, aliases, row/point counts,
and readability assumptions coherent with generated outputs. It also checks
that manifest schema, artifact fingerprints, alias prefixes, and registry
coverage still match the local files.
If the scaffold report is
not at hand, run `scripts/inspect_artifact_manifest.py --workspace <deck>` to
recover the same slide-ready aliases, layout recommendations, outline snippets,
selection templates, copyable auto-bind/validate/build commands, and
binding-update checklist from the manifest. If every generated output should
become the standard figure/chart/table evidence triplet, run the emitted
`commands.auto_select_all` or:
`scripts/apply_artifact_manifest_bindings.py --auto-select --selection-out
decks/my-deck/artifact_selections.auto.json`. For custom titles, slide IDs, or
only some variants, write a small selection file and run the same helper.
Either way, the outline, content plan, evidence plan, and artifact registry are
updated together, and selected-column provenance is copied into the generated
slide/content/evidence records instead of being reconstructed by hand. Auto
selections use compact source/metric titles for slide headings, keep the
primary analysis readout in interpretation, content-plan messages, evidence
claims, and sidebar readout sections, then add compact source-plus-column
captions to generated figure/chart/table slides. Bound evidence items also
carry generated artifact IDs, role-keyed aliases, and paths, so later agents
can trace the figure/chart/table objects behind a claim from
`evidence_plan.json`. Planning validation warns when those optional context
fields are malformed, use the wrong alias prefix, or point at missing local
artifact paths.
Registry-only chart/table JSON artifacts are also payload-validated when their
type or path clearly identifies them as structured chart/table outputs.
`asset_stage.py` validates staged chart/table JSON before aliases are written:
charts need numeric values plus labels/categories, and tables need matching
header/row widths. Planning validation performs the same early check for
existing local `asset_plan.charts`/`asset_plan.tables` paths and inline
chart/table entries so malformed structured assets are found before staging.
Preflight and staging also require staged asset names to stay
unique after normalization across images, backgrounds, charts, tables, and
generated images so aliases such as `asset:<name>` cannot overwrite or resolve
ambiguously. Staging preserves unchanged JSON manifests, chart/table specs,
palette files, and attribution CSVs so repeat builds do not churn deterministic
artifacts. Treat the scaffold as a starter; edit the generated script for real
filters, statistics, annotations, and multi-panel figures. Preflight warns when
local or staged figure assets appear to carry large exterior blank borders; trim
them in the figure script or with `scripts/trim_image_whitespace.py`.
`build_workspace.py --scaffold-data-artifacts` is idempotent when the generated
figure script is unchanged; it preserves the script file and planning JSON
mtimes. If the existing script differs from the newly inferred scaffold, pass
`--overwrite-data-artifacts` deliberately.

Add `--visual-review` once the source text is stable and rendered-slide
judgment matters. It creates `build/qa/visual_review/visual_review.md` plus a
contact sheet for fast source-level iteration.

For public or research topics where credible images should be part of the
deck, use source-backed visual planning:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck \
  --plan-research-assets --allow-network-assets --qa --overwrite
```

This fills a stub `asset_plan.json` with Wikimedia Commons queries, updates
selected slides to use staged `image:<name>` aliases, writes
`assets/attribution.csv`, and lets the renderer append an Image Sources slide.

Workspace source files:

- `design_brief.json`: audience posture, cover concept, structure strategy,
  grid policy, card/container rules, `readability_contract`,
  `speed_contract`, `evidence_continuity`, and optional
  `figure_export_contract`. Evidence-continuity slide applications should
  resolve to outline slide IDs and declared continuity threads.
  `figure_export_contract.outputs[*].target_slide` should resolve to outline
  slide IDs, and each output's `target_variant` should match the target
  slide's outline variant. Figure outputs should include a parseable
  `target_box` such as `5.0x3.3 in`, plus `figure_size_inches`,
  `figure_dpi`, and `axis_label_min_pt`, so plot label readability can be
  checked before render. The contract's `rerun_command` should include the
  declared figure script path, with optional follow-on steps such as whitespace
  trimming. Generated artifact registry `used_on_slides` entries should also
  resolve, registry paths should exist, declared chart/table outputs should
  appear in the outline through paths or asset aliases or carry
  `used_on_slides`, and script-like `producer` values should resolve so charts,
  tables, and figures remain auditable after slide edits.
- `content_plan.json`: thesis, audience, slide roles, visual strategy.
  Planned `slide_id` values should align with explicit outline slide
  `slide_id`/`id`/`slug` fields or stable positional IDs such as `s1`; planning
  validation warns on missing planned slides, duplicate explicit outline IDs,
  plan/outline variant drift, and `narrative_arc` slide references that no
  longer resolve.
- `evidence_plan.json`: sourced facts, metrics, claims, chart candidates.
  Include `source_policy` whenever evidence `items` or `chart_candidates` are
  present so source-line footers, refs, and final reference slides follow an
  explicit citation rule.
  Evidence `used_on_slides`, chart `target_slide`, and chart `source_ids`
  should resolve to outline slide IDs and evidence IDs so final decks do not
  carry orphaned claims or chart plans.
- `asset_plan.json`: source-backed images, backgrounds, charts, tables, icons, optional generated images.
  Asset entries with `used_on_slides` should resolve to outline slide IDs so
  staging plans do not keep orphaned visuals. Declared local `path` entries
  should exist by final planning, or be created by the listed artifact scripts,
  so staging does not fail late. Existing local chart/table JSON paths and
  inline chart/table entries should pass the same payload-shape checks used by
  staging. Local image/background entries should include source/provenance
  metadata, especially before strict provenance staging. Generated-image
  entries should include `prompt`, `model`, and `purpose` metadata for
  disclosure, staged sidecars, and later regeneration.
- `assets/make_figures.py`: optional deterministic figure-generation script
  created manually or by `scripts/scaffold_figure_artifacts.py`.
- `assets/figures/` and `assets/charts/`: slide-ready figure exports and
  editable chart JSON specs.
- `assets/tables/`: compact generated summary-table JSON for editable table
  slides.
- `outline.json`: final renderable deck structure.
- `notes.md`: data rules, manual design choices, unresolved assumptions.

## Renderer Policy

- Default renderer: `scripts/build_deck_pptxgenjs.js`.
- Python fallback: `scripts/build_deck.py`, selected only for legacy or
  python-pptx-specific behavior not covered by the fast editable path.
- Mermaid diagrams are optional. Use them only when the process itself is the
  slide's evidence; otherwise use a table, split comparison, figure, or concise
  bullets. `scripts/render_mermaid.py` uses `mmdc` when installed and a
  repo-native fallback otherwise; the fallback caps rows at four boxes and
  balances long flows, but agents should still keep process diagrams short.
- Generated imagery is optional and API-key gated. It must be staged through
  `asset_plan.json` and placed on `variant: "generated-image"` slides unless
  the user explicitly asks otherwise.
- Online source-backed images are also optional and network-gated. For public
  topics where credible images would improve the deck, populate
  `asset_plan.json` with Wikimedia Commons queries and run
  `build_workspace.py --allow-network-assets`; cite those assets through the
  generated `assets/attribution.csv`, slide `sources`, or a final image-source
  slide. If `asset_plan.json` is still a stub, prefer
  `build_workspace.py --plan-research-assets --allow-network-assets`.

## Design Rules

- Alignment and readability outrank decoration.
- Decide the design brief before the outline: audience posture, cover concept,
  structure strategy, and what the deck must not look like.
- Choose one design DNA before rendering: lab results dashboard, board risk
  memo, product/investor reveal, editorial report, civic science policy, or a
  custom DNA. Let that DNA constrain preset, cover archetype, structural
  treatments, motifs, variants, icons, and density.
- Use bounded `design_modulation` for subtle or suitable visual shifts:
  accent role, whitespace, density, motif, container style, and figure/table
  treatment. Start from a loadable preset and avoid unsupported inline colors
  or custom fonts unless adding validated design tokens.
- If the title slide introduces evidence chips, stages, or tags, carry that
  system through the deck with `evidence_continuity`. Reuse the tags as
  subtitle eyebrows, sidebar labels, table group titles, footer/source
  prefixes, or section strips; do not leave the motif only on slide 1.
- Every content slide needs a visual strategy: image, chart, icon system,
  table, clean report body, bottom takeaway box, strong two-column composition,
  or an optional diagram when the content genuinely needs one. Oversized KPI
  slides and process diagrams are optional rhythm breaks, not defaults.
- Do not pair rounded card bodies with edge-attached accent rails or header
  strips. Use rectangular card bodies when an accent needs to sit flush at the
  top or side edge.
- Do not default to repeated four-card grids. Prefer feature stats, open
  quadrants, staggered timelines, or evidence-first layouts when those better
  match the argument.
- Treat timelines as a last-mile storytelling choice, not a default shape.
  If milestones feel like a template, use `timeline_mode: "bands"` or
  `"chapter-spread"`, or replace the timeline with a figure, table, split
  comparison, or standard evidence slide.
- Preserve model freedom: choose the smallest set of layouts that fit the
  user's content. Do not force a `kpi-hero`, dark section divider, card grid,
  flow diagram, or icon system just because the renderer supports it.
- For academic, lab, and data presentations, prefer evidence-first slides:
  `scientific-figure` for 2-4 panel figure slides, `image-sidebar` for
  one figure plus interpretation, `lab-run-results` for compact result table
  dashboards, then `table`, `flow`, `stats`, and `comparison-2col` before
  generic card grids. Use captions, footnotes, sidebars, and semantic cell
  highlights for readout, interpretation, caveats, assay/run metadata, and
  concordance/pass-fail state. Preflight warns when inline or staged editable
  tables exceed clean slide-readable row/column/cell-budget limits or contain
  sentence-length cell text, and when native chart JSON has too many
  categories, series, points, or long axis labels for a readable slide.
  Chart, `image-sidebar`, `scientific-figure`, table, and lab-run-result slides
  should carry compact captions, footers, or sources so the evidence remains
  auditable.
  Preflight errors when a `scientific-figure` slide contains more than 4 panels,
  because the renderer intentionally lays out only the first 4; split the
  evidence across slides or use a composite figure instead.
  Preflight warns when a `scientific-figure` slide uses a long bottom caption
  plus interpretation that would shrink inside the fixed synthesis strip.
  Preflight also warns when a slide declares
  `slide_intent: "evidence"`, data/figure/table `visual_intent`, or
  `evidence_needs` but lacks a chart, table, figure, image, diagram, stats,
  KPI, flow, or structured comparison anchor. Split, summarize, or convert
  dense data into chart-plus-summary-table evidence or a generated figure.
- For generated scientific figures, solve whitespace and readability in the
  Python figure script before rendering the deck. Export at the target slide
  aspect ratio, use tight bounding boxes and small padding, run
  `scripts/trim_image_whitespace.py` when needed, and switch from
  `scientific-figure` to `image-sidebar` when a dense panel grid would make
  plots, gels, labels, or axes too small.
- Route lab/report decks by evidence objects and proof burden, not by a static
  keyword list. Terms such as ASCO, TB, LAMP, clinical, LOD, sequencing, assay,
  sample, and resistance are priors; confirm that the deck actually has lab
  evidence, figures, tables, readouts, run metadata, or clinical validation
  claims before forcing `lab-report`.
- For simple lab or academic summaries, `lab-report` can use `header_mode:
  "lab-clean"` or slide-level `header_mode: "lab-card"` with a white body,
  `header_variant: "auto"` for restrained heading/accent-rule variation,
  including top/bottom page-rule and plain no-rule treatments,
  footer rule, sources/refs, page number, and optional `summary_callout`
  bottom box.
  Keep `source-line` footer provenance compact: use short citation IDs or
  abbreviated source labels in the footer, and move long references to a final
  editable References/Image Sources table slide. When preflight reports
  `source_line_footer_over_budget`, run
  `scripts/compact_source_footers.py --workspace <deck>` or let
  `advance_workspace.py --execute` run the readiness command to compact footer
  IDs and append/update the References table slide. Preflight warns when
  source-line footer text is likely to shrink into unreadable provenance.
  When changing source-footer budget rules, compaction behavior, or References
  table slide generation, run `npm run check:source-footers`.
  When changing source-line footer rendering, bottom footer rules, page
  numbers, source/ref label placement, or `top-bottom-rule`/`plain`
  lab-report header chrome, run `npm run check:lab-footer-chrome`.
  Use a short deck-level `style_seed` when similar lab reports should preserve
  reproducible builds but avoid identical auto header rhythms.
  This is preferred when the user wants a clean editable research deck more
  than a dramatic design system.
- Wrapped titles must reserve vertical space before subtitles/body content.
- Preflight estimates title wrapping before render and warns when a slide title
  exceeds `readability_contract.max_title_lines`; shorten the title, move
  qualifiers to subtitle/body, or deliberately relax the contract for dense
  report decks. It also warns when a title stays within the line budget but
  leaves a single short orphan word on the final estimated heading line, and
  when standard, split, card, comparison, or image-sidebar slides exceed
  practical prose budgets, including one long paragraph that would otherwise
  look like a single outline line. Treat
  `content_text_density_high` as a signal to split the slide, shorten bullets,
  move detail to notes/refs, or convert dense evidence into a chart, table,
  figure, or summary callout.
  Content-slide subtitles should stay compact; preflight warns when a subtitle
  is estimated to occupy more than two header lines because it will crowd the
  body region before render.
  Workspace builds pass `design_brief.json` into preflight, so
  `readability_contract.max_title_lines`, `max_slide_text_lines`,
  `max_slide_words`, and `max_slide_chars` can make the static title/prose
  budget stricter or more permissive for the deck's audience and density.
  Planning validation warns when readability thresholds are missing, boolean,
  non-numeric, or below safe deck floors: title 24 pt, body 12 pt, caption
  7.5 pt, chart labels 7 pt, footer reserve 0.25 in, title lines below 1 or
  above 3, and non-positive prose budgets.
  It also warns when the speed contract is missing renderer, first-pass,
  render-policy, asset-policy, or repeated-render conversion guidance, and
  when an applied design contract lacks required QA checks, fail-on conditions,
  placeholder checks, acceptance-evidence entries, or agent execution phases.
- Preflight also warns when visible outline text still contains placeholder
  markers such as `TODO`, `TBD`, `XXX`, `lorem/ipsum`, `[insert ...]`,
  `[placeholder ...]`, or PowerPoint prompt text. Resolve those in
  `outline.json` or move unresolved work into `notes.md` before rendering.
- Treat `content_span_too_short` and `content_span_too_narrow` QA warnings as
  layout-polish feedback: enlarge the evidence object, add a table, sidebar,
  or visual anchor, or intentionally choose a sparse variant instead of leaving
  a stranded text band and dead whitespace.
- Generated visuals must be labeled with prompt/model/purpose metadata and be
  removable without damaging the narrative.
- Prefer source-backed imagery/facts; use generated imagery for concept visuals
  when source-backed assets are weak or unavailable.
- Visual review now flags layout sameness and research decks that claim source
  visuals but do not include image/figure anchors. Treat those findings as
  planning feedback, not a reason to add decorative components.

## QA Gate

For final deliverables, run:

```bash
python3 scripts/qa_gate.py \
  --input out.pptx \
  --outdir /tmp/pptx-qa \
  --style-preset <preset> \
  --design-brief design_brief.json \
  --strict-geometry \
  --fail-on-whitespace-warnings \
  --fail-on-visual-warnings \
  --fail-on-design-warnings
```

When `--design-brief` is supplied, targeted design QA checks rendered
title/body/caption/table text plus explicit native-chart label sizes against
`readability_contract` and reports undersized text before delivery.
It also warns when title/body text intrudes into the declared
`footer_reserved_inches` band, so source-line footers and page numbers stay
clear.
Whitespace warnings include empty-slide balance checks and content clustered
into a narrow or short band inside the safe content area.

Then render and inspect visually:

```bash
python3 scripts/render_slides.py --input out.pptx --outdir renders/ \
  --emit-visual-prompt
python3 scripts/visual_review.py --input out.pptx --outdir review/ \
  --renders-dir renders/ --outline outline.json
```

Finally check placeholders:

```bash
python -m markitdown out.pptx | grep -iE "\bx{3,}\b|lorem|ipsum|\bTODO|\[insert|\[placeholder"
```

Preflight catches the same class of placeholder leaks in visible
`outline.json` text before render, but keep this final extracted-content check
because template/master text and renderer-introduced content can still appear
only after PPTX generation. If any check fails, fix source, rebuild, and rerun
the affected checks.
