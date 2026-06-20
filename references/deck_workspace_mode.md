# Deck Workspace Mode

Use deck workspaces when you want a presentation to behave like a real authored project rather than a one-off generated file.

## Why This Mode Exists

Inline heredoc scripts and ad hoc JSON files are fine for a single pass, but they are weak for later extension. A durable deck needs:

- a saved outline or builder source
- a stable style contract
- staged local assets
- notes about data rules, measurements, and QA decisions
- one command that rebuilds the same deck later

`init_deck_workspace.py` and `build_workspace.py` provide that layer.

## Files In A Workspace

- `outline.json`: canonical structured slide source
- `content_plan.json`: thesis, audience, slide roles, and visual strategy
- `design_brief.json`: optional `user_intake`, audience posture, cover concept, grid policy, structure strategy, evidence continuity, and figure export rules
- `design_contract.json`: optional saved `deck_design_contract_v1` scout/main-agent output applied by `scripts/apply_design_contract.py`
- `design_contract_apply_report.json`: deterministic apply report for the saved design contract
- `intake_apply_report.json`: deterministic apply report tying question-card answers to `design_brief.user_intake`
- `style_extract_report.json`, `style_extract_design_brief.json`, `style_fragment_apply_report.json`: bounded PPTX-style extraction and apply evidence when a reference deck/corpus informs the style
- `data_analysis_handoff.json`, `data_analysis_handoff_apply_report.json`, and `artifact_selections.scout.json`: data/evidence scout output, source apply report, and binder-compatible artifact choices
- `outline_authoring_handoff.json`: optional saved `outline_authoring_handoff_v1` source-authoring packet applied by `scripts/apply_outline_authoring_handoff.py`
- `outline_authoring_handoff_apply_report.json`: deterministic apply report tying the handoff SHA-256 to the patched planning sources
- `artifact_selections.auto.json` and `build/artifact_manifest_apply.json`: generated-artifact binding selections and apply evidence from auto-bind/fast-first-pass workflows
- `evidence_plan.json`: sourced claims, metrics, chart candidates, and open questions
- `style_contract.json`: style preset, token contract, reference-deck metadata, and build targets
- `asset_plan.json`: source-backed imagery/background/chart/table staging plan, plus optional generated-image requests
- `notes.md`: sources, data-cleaning rules, coordinate notes, and deck-specific design choices
- `assets/`: local images, diagrams, tables, logos
- `build/`: generated `.pptx`, readiness/advance/delivery reports, next-action prompt, and QA reports

## Commands

Create a workspace:

```bash
python3 scripts/init_deck_workspace.py \
  --workspace decks/my-deck \
  --title "My Deck" \
  --style-preset executive-clinical
```

**New topic = fresh scaffold.** A new deck always scaffolds empty and
gets its outline authored from the topic's own argument arc. Do NOT
clone an existing deck's workspace as a "house style" starting point —
the source's variant mix and structural biases travel with the outline
and every new deck ossifies into the first one's rhythm. The init
script enforces this: if you pass `--source-outline` or
`--reference-pptx` pointing at another deck's workspace under `decks/`,
the script refuses unless you also pass `--followup-edit`.

### When to use `--followup-edit`

- User asks for an update to the SAME deck on the same topic
  (e.g., "add a Q3 slide to the coal deck" or "restyle the energy deck
  with a new palette"). This IS a followup edit. Pass the flag.
- User explicitly asks to start from an existing deck's structure for
  a known reason (e.g., "build a nuclear deck using the coal deck's
  narrative structure because both are energy-source primers"). This
  is a conscious clone decision. Pass the flag, but ALSO plan variant
  substitutions before building — otherwise you'll reproduce the
  source's monotony problems.

### When NOT to use `--followup-edit`

- User asks for a new deck on a new topic. Scaffold fresh.
- Codex would like a "house-style baseline" to write against. No — the
  house style lives in `design_philosophy.md` and the style presets,
  not in any one finished deck.

See `references/codex_guardrails.md` Eighth Trap for the fuller
rationale.

Build from the saved workspace:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck --qa
```

For reproducible first-turn planning, save the JSON returned by
`scripts/emit_design_contract_prompt.py` or the deck-start packet's
design-contract scout as `design_contract.json`, then apply it source-first:

```bash
python3 scripts/apply_design_contract.py \
  --workspace decks/my-deck \
  --contract decks/my-deck/design_contract.json \
  --report decks/my-deck/design_contract_apply_report.json
```

The applicator updates `design_brief.json`, `content_plan.json`,
`evidence_plan.json`, `asset_plan.json`, and a marked section in `notes.md`.
Use `--preserve-existing` only when layering a new contract onto a workspace
that already has deliberate human edits.

When the design contract is applied but `outline.json` is still starter-like,
emit the contract-aware authoring packet before patching sources:

```bash
python3 scripts/emit_outline_authoring_prompt.py \
  --workspace decks/my-deck \
  --output decks/my-deck/build/outline_authoring_prompt.md
```

The returned `outline_authoring_handoff_v1` shape should guide edits to
`outline.json`, `content_plan.json`, `evidence_plan.json`, `asset_plan.json`,
and `notes.md`; the main agent still owns verification and final source edits.
Save the returned JSON as `outline_authoring_handoff.json` and apply it
source-first:

```bash
python3 scripts/apply_outline_authoring_handoff.py \
  --workspace decks/my-deck \
  --handoff decks/my-deck/outline_authoring_handoff.json \
  --report decks/my-deck/outline_authoring_handoff_apply_report.json
```

Readiness will prioritize this apply command when the handoff exists but is
missing, stale, or only dry-run applied.

For final reusable/report decks, block on source-planning and dead-whitespace
warnings before delivery:

```bash
python3 scripts/build_workspace.py \
  --workspace decks/my-deck \
  --qa \
  --fail-on-planning-warnings \
  --fail-on-whitespace-warnings \
  --overwrite
```

The build report fingerprints workflow source-contract files when present:
intake answers/apply reports, design contracts/apply reports, PPTX style
extract fragments/apply reports, data-analysis handoffs/selections/apply
reports, outline-authoring handoffs/apply reports, and generated-artifact
selection/apply reports. If any of those files are changed or newly created
after the latest build, delivery readiness blocks until the affected
contract/handoff/selection is reapplied and the deck is rebuilt.

When picking up an existing workspace, run the source-only readiness check
before rendering:

```bash
python3 scripts/report_workspace_readiness.py \
  --workspace decks/my-deck
```

The machine report is written to `build/workspace_readiness.json`, and the
scannable companion is written to `build/workspace_readiness.md`. Together they
aggregate `validate_planning.py` and `preflight.py`, summarize
planning/preflight counts and issue keys, preview the resolved style preset,
style seed, treatment pools, renderer-visible `deck_style`, and saved
`design_contract.json` apply status, note whether `build/build_workspace_report.json`
exists, compare its source fingerprints with current workspace files,
summarize outline composition, variant rhythm, visual/evidence anchor
coverage, and source coverage, detect local tabular data, summarize generated
artifact output aliases and unbound output IDs, summarize reference-PPTX style
extraction/apply state,
summarize the latest build's compact speed timings,
recommend source/provenance cleanup when coverage is thin, and emit
recommendation details such as slide IDs, suggested fields/variants, a
prioritized `next_action`, and recommended next commands. When the saved build
report is current, readiness also reads the existing QA report and turns
awkward whitespace plus design/readability warnings into slide-level
source-edit recommendations. Use `ready` as a
fast source-level go signal only when there are no planning/preflight warnings
and no open readiness
recommendations, `needs_attention` as a warning/recommendation cleanup queue,
and `blocked` as a required fix before render/QA.

If you want the workspace to take the next deterministic step rather than only
diagnose state, run:

```bash
python3 scripts/advance_workspace.py \
  --workspace decks/my-deck \
  --execute \
  --max-steps 3
```

The advancer writes `build/workspace_advance_report.json` and
`build/workspace_next_action.md`. It executes command-type readiness actions
only when `--execute` is present, reruns readiness after each command, and
stops with a compact agent prompt when the next step is a source edit such as
adding sources, adding visual/evidence anchors, or resolving planning text.
The JSON report carries `source_edit_plan`, mapping slide IDs to concrete
source fields such as `outline.json` `slides[2].sources` or `slides[4]`, plus
the suggested operation and relevant planning, preflight, QA whitespace, or QA
design/readability rule when applicable. Planning warnings are routed to
source fields such as `design_brief.json` `readability_contract.*`,
`speed_contract.*`, `figure_export_contract.*`,
`analysis_artifact_plan.artifact_registry`,
`analysis_artifact_plan.analysis_summary.*`, `evidence_plan.json`
`source_policy`, or stale slide-reference paths instead of leaving only a rerun
command. When `deck_start_packet.json` exists but `intake_answers.json` is
missing, readiness writes a source-edit handoff for recording explicit answers
or best-judgment assumptions. When `intake_answers.json` exists but is
unapplied, stale, or only dry-run applied, readiness treats
`apply_deck_intake_answers` as the next deterministic command before
design-contract work; the advancer can apply the durable intake layer and rerun
readiness. When a `data_analysis_handoff.json` scout output exists but is
unapplied or stale, readiness treats `apply_data_analysis_handoff` as the next
deterministic command before generic artifact binding; the advancer can apply
the scout selection/evidence updates and rerun readiness. When an artifact
manifest exists but neither the standard auto-selection file nor an applied
scout selection covers the outputs, readiness treats `bind_generated_artifacts`
as the next deterministic command before generic planning-warning cleanup; the
advancer can execute that binder and rerun readiness to clear artifact
slide-reference drift. The advancer prompt also preserves generated
figure-quality counts and per-alias exterior-whitespace status, so figure
trimming/regeneration decisions can be made from `build/workspace_next_action.md`
without reopening the manifest inspection report. When local tabular data exists
but no generated artifact
manifest exists yet, readiness can choose `scaffold_data_artifacts`; with
`--execute`, the advancer runs the fast scaffold/auto-bind/build/QA path and
reruns readiness before returning a source edit prompt or ready state. When a
saved `design_contract.json` exists but is not applied to planning sources,
has changed since apply, or predates apply fingerprint metadata, readiness can
choose `apply_design_contract`; with `--execute`, the advancer runs the
deterministic contract applicator and reruns readiness. When a reference PPTX
exists but the style report/fragment is missing or stale, readiness can choose
`extract_pptx_style`; when a style fragment exists but has not been applied to
`design_brief.json`, it can choose `apply_pptx_style_fragment`. With
`--execute`, the advancer runs these deterministic commands and reruns
readiness before later planning/build actions. Saved
visual QA and visual-review
warnings are mapped the same way for underfilled containers, repeated
composition families, missing visual anchors, and clearance risks. When the
latest current build report records a failed strict-QA step without a more
specific saved warning mapper, the advancer emits a failed-build inspection
source-edit plan with the failed step, return code, QA counts, and report path
instead of rerunning the same strict build by default.

After a strict workspace build, create the final delivery audit:

```bash
python3 scripts/report_delivery_readiness.py \
  --workspace decks/my-deck
```

It writes `build/delivery_readiness.json` and
`build/delivery_readiness.md`. The audit combines the current readiness report,
the latest `build/build_workspace_report.json`, QA counts, output PPTX
fingerprints, source-fingerprint freshness, strict-build options, and replay
commands. Office output snapshots include a normalized content hash alongside
the raw package hash, so repeat-build checks can ignore volatile ZIP/core
timestamp metadata. If any source file changed after the build report was written, the
delivery audit blocks until the deck is rebuilt. When the audit blocks or
needs attention, use its delivery-level `recommended_next_action` and Markdown
Next Action section to run the immediate command or hand off to
`advance_workspace.py --execute`. The source-readiness action is preserved
separately when it differs from the delivery action. The audit also carries
the applied design-contract replay ledger, compact deck-start source inventory
counts/paths, the resolved seeded header-treatment summary from
`build/outline_resolved.json`, plus compact generated-artifact
manifest/selection context with output IDs, analysis-summary paths,
figure-quality counts, and bound slide/variant targets, so the final handoff
shows which local data/style inputs, replay seed/treatment pools, lab-report
heading variants, and chart/table/figure artifacts produced the current build.
Use
`--allow-skip-render` only when render-free QA is the accepted fallback for the
environment, and use
`--require-visual-review` when final acceptance requires a rendered contact
sheet.

To turn the audit into a reproducible handoff, run:

```bash
python3 scripts/advance_delivery.py \
  --workspace decks/my-deck
```

It writes `build/delivery_advance_report.json` and
`build/delivery_next_action.md`. Without `--execute`, it records the immediate
delivery-level command or source-edit handoff, including
`inspect_delivery_warnings` when build-report warning counts remain. The
advance report and next-action Markdown preserve the same replay contract,
source-inventory, resolved-treatment summaries, and generated-artifact context
for resumed agents. With `--execute`, it runs
command-type delivery actions and reruns delivery
readiness; use that only when final rendering is available or render-free
delivery has been explicitly accepted with `--allow-skip-render`.

When local CSV/TSV/XLSX/JSON data should become repeatable chart, table, and
figure assets, let the workspace build run the deterministic scaffold before
planning validation and asset staging:

```bash
python3 scripts/build_workspace.py \
  --workspace decks/my-deck \
  --fast-first-pass
```

Use this render-free form for a fast first pass from local data to auditable
figures/charts/tables. It expands to the strict scaffold, auto-bind,
render-free QA, planning-warning, whitespace-warning, and overwrite flags. Run
a rendered strict build for final delivery once sources and artifacts are
stable; delivery readiness reports treat fast-first-pass builds as
`fast_first_pass_not_final` and recommend the strict final build command.

The scaffold writes `assets/make_figures.py`, `assets/figures/*.png`,
`assets/charts/*.json`, `assets/tables/*_summary.json`,
`assets/analysis_summary.json`, `assets/analysis_summary.md`, and updates
`design_brief.json` plus `asset_plan.json` image/chart/table entries. Re-running
the scaffold is idempotent when the generated script and planning JSON are
unchanged. If an existing figure script differs from the newly inferred
scaffold, pass `--overwrite-data-artifacts` deliberately. CSV/TSV/JSON/
Parquet/Feather tables produce one inferred chart each, Excel workbooks are
scanned sheet-by-sheet, and Parquet/Feather inputs report a skipped-file
dependency reason when pandas lacks a compatible columnar engine.
When `--auto-bind-artifacts` is included, the workspace build applies the
generated `assets/artifacts_manifest.json` before planning validation, writes
`artifact_selections.auto.json`, and creates stable figure/chart/table evidence
slides through the same manifest-binding helper used for explicit selections.
Every build that reaches render/QA writes `build/build_workspace_report.json`,
including strict QA failures. Treat it as the resumable run ledger: it records
`run.status`, the failed step/return code when applicable, the resolved
renderer and preset, source/output fingerprints, generated artifact selections,
planning/preflight/QA report paths and counts, and replay commands for the same
workspace build. Office output fingerprints include both raw SHA-256 and a
normalized content SHA-256 for reproducibility checks across repeated builds.
Generated chart/table JSON plus `analysis_artifact_plan.artifact_registry`
entries include `analysis_metadata` with source path, source SHA-256,
producer script path, producer SHA-256, source/producer sizes, selected
columns, rows used, series count, and point count. Planning validation warns
when recorded source or producer fingerprints no longer match the current
local data file or figure script.
If multiple source files or Excel worksheets infer the same base chart ID, the
scaffold appends a deterministic short hash so figure/chart/table paths,
asset-plan aliases, and artifact-registry entries remain unique across rebuilds.
`npm run check:excel-workflow` covers this multi-sheet path and verifies that
the final delivery audit plus `advance_delivery.py` preserve workbook artifact
context, output IDs, analysis-summary paths, and bound slide targets.
The scaffold report includes an `alias_plan` with generated `image:`, `chart:`,
and `table:` aliases plus copy-ready field snippets, deterministic
`selection_templates`, selected-column provenance, and
`commands.auto_select_all` for evidence-first slide variants. For the default
lab/report route, run the emitted
`commands.auto_select_all` or `scripts/apply_artifact_manifest_bindings.py
--auto-select --selection-out <workspace>/artifact_selections.auto.json` to
create stable figure/chart/table evidence slides and update outline, content,
evidence, asset, and artifact registry metadata together. Use the templates,
snippets, or an explicit selection JSON when only some generated outputs belong
in the deck or titles need domain-specific wording; selected columns are copied
into generated slide/content/evidence records during binding. Auto selections
also use the primary analysis readout for capped slide titles and
content/evidence messages, then add compact source-plus-column captions to
generated evidence slides. `npm run check:artifact-triplet` covers the
full figure/chart/table binding mode and verifies final delivery readiness plus
`advance_delivery.py` preserve the same triplet artifact context. Bound
evidence items carry generated artifact IDs,
role-keyed aliases, and paths, so `evidence_plan.json` can be used as a quick
claim-to-figure/chart/table provenance handle. Planning validation warns when
those optional fields are malformed, use the wrong alias prefix, or point at
missing local artifact paths. If only
`assets/artifacts_manifest.json` is available, run
`scripts/inspect_artifact_manifest.py --workspace <deck>` to recover the same
aliases, selection templates, and copyable auto-bind/validate/build commands.
Use `assets/analysis_summary.json` or its Markdown companion as the quick
human/agent readout of source paths, selected columns, aliases, row/point
counts, and readability assumptions before binding outputs into slides.
Planning validation checks the declared summary file for schema version,
matching manifest path, source-path coverage, generated aliases, non-negative
row/point counts, and figure readability assumptions.
If the manifest already exists and the auto-selection file is missing or does
not cover every output, the readiness report's next action is the same binding
command before generic planning-warning cleanup, because it resolves the common
"artifact not referenced in outline" warnings in one deterministic step.
During asset staging, chart JSON must contain numeric values with
labels/categories, and table JSON rows must match the header width. Invalid
chart/table artifacts fail before aliases are added to
`assets/staged/staged_manifest.json`. Unchanged staged JSON outputs and
`assets/attribution.csv` are written idempotently, so repeat workspace builds
preserve mtimes for deterministic chart/table specs, palettes, manifests, and
source rows. Preflight also reads staged chart/table JSON and warns when chart
categories, series, plotted values, axis labels, or editable table row/column
budgets are too dense for a readable slide, or when editable table headers/body
cells carry sentence-length text that should move to captions, footnotes, or a
sidebar. It estimates slide-title wrapping against
`readability_contract.max_title_lines`, and it warns when prose-heavy standard,
split, card, comparison, or image-sidebar slides exceed practical text budgets
before rendering. Image-sidebar figure slides also warn when they lack caption,
footer, or sources. Optional `readability_contract` fields
`max_title_lines`, `max_slide_text_lines`, `max_slide_words`, and
`max_slide_chars` tune those static title/prose limits for the deck. Visible
`outline.json` placeholder markers
such as `TODO`, `TBD`, `XXX`, `lorem/ipsum`, `[insert ...]`, and
`[placeholder ...]` are also flagged before render, so unfinished authoring
tasks stay in `notes.md` rather than leaking into slides.
Fresh workspaces scaffold baseline `readability_contract`, `speed_contract`,
and `style_system.style_mix_matrix` sections; adjust readability thresholds,
renderer/QA policy, and treatment pools for the actual audience, density,
data/artifact load, and review cadence before final delivery.
Planning validation also checks artifact freshness: if a declared figure,
chart JSON, or summary table is older than the newest listed data file or
figure script, rerun the recorded rebuild command before the final render. It
also warns when generated-looking chart/table artifacts or registry entries
lack reproducible `analysis_metadata`.
`npm run check:artifact-freshness` verifies that stale local data blocks final
delivery, that `advance_delivery.py` keeps artifact context in the recovery
prompt, and that the deterministic refresh path clears source freshness.
Unchanged `build/planning_validation.json` reports are preserved in place, so
repeat validation/build cycles do not create noisy derived-artifact churn.

Emit an optional personalization intake prompt before planning when the user
wants nuance but has not supplied audience, style, palette, density,
background/visual mode, asset, source, or constraint preferences:

```bash
python3 scripts/emit_deck_intake_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request" \
  --mapping
```

When Codex's native `request_user_input` tool is available, use the question
card instead of a plain chat questionnaire:

```bash
python3 scripts/emit_deck_intake_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request" \
  --codex-ui
```

Pass the emitted `questions` and `autoResolutionMs` to `request_user_input`
immediately after the user's deck prompt. If that tool is unavailable in the
current mode, ask the same top questions in chat. If the user declines, says
"use best judgment", or does not answer before auto-resolution, write
assumptions under `design_brief.user_intake` and proceed. Translate answers
into `design_modulation`, `visual_system`, `title_page_concept`, `deck_style`,
`asset_plan`, and `notes.md`; do not leave the answers as a disconnected
questionnaire.

Run the rendered polish loop once the outline text is stable:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck --qa --visual-review
```

This writes the normal QA report plus `build/qa/visual_review/`, including a
contact sheet, `visual_review.json`, and `visual_review.md`.

Allow Wikimedia Commons fetches while staging assets:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck --allow-network-assets
```

Allow optional OpenAI-generated images while staging assets:

```bash
OPENAI_API_KEY=... python3 scripts/build_workspace.py \
  --workspace decks/my-deck \
  --allow-generated-images
```

Use this only for deliberate concept visuals. Put each generated image on a
`variant: generated-image` slide so the prompt/model/purpose metadata is
visible and the user can delete the slide without breaking the rest of the deck.

### Renderer selection (`--renderer`)

`build_workspace.py` supports two renderers. Both emit the same `.pptx`
format and both are validated by the same `qa_gate.py` afterwards.

| Value | Behavior |
| --- | --- |
| `auto` (default) | Routes to `pptxgenjs` for the standard editable deck path, including common native charts. The chosen renderer is logged to stderr. This is what you want ~99% of the time. |
| `pptxgenjs` | Forces `node scripts/build_deck_pptxgenjs.js`. Richer typography on timeline/stats/kpi-hero/table/section. Covers `standard`, `cards-2/3`, `split`, `comparison-2col`, `matrix`, `timeline`, `stats`, `kpi-hero`, `table`, `lab-run-results`, `chart`, `image-sidebar`, `scientific-figure`, `flow`, and `generated-image`. Fails loudly if `node` or the `pptxgenjs` module is missing. |
| `python` | Forces `scripts/build_deck.py`. Use for legacy decks or python-pptx-specific chart behavior not covered by the fast path. |

Example:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck --qa
```

Before rendering, workspace builds resolve renderer-facing defaults from
`design_brief.json` into `build/outline_resolved.json`. This lets the design
contract supply the base `style_preset` plus header/footer/title/section/
timeline/matrix/stats/cards/callout treatment pools without mutating the
source `outline.json`; scaffolded
`visual_system.style_preset` remains supported for compatibility, unsupported
or conflicting explicit preset names fail during planning/build, unsupported
design-brief treatment enum values fail before rendering, unsupported
`outline.deck_style` or slide-level treatment overrides are preflight errors,
and explicit `outline.deck_style` values remain the final override for
deck-style fields. The pool choice is stable for the same `style_seed` and
changes only when the contract changes. When the resolved JSON payload is
unchanged, the build keeps the existing file untouched so repeat rebuilds do
not churn derived artifact timestamps.

Applied design contracts also persist a compact
`design_brief.reproducibility_contract` replay ledger. For new contracts this
comes from the `deck_reproducibility_contract_v1` object emitted by
`scripts/emit_design_contract_prompt.py`; if a scout omits it,
`scripts/apply_design_contract.py` fills a compatible ledger from the locked
style system, structure blueprint, artifact plan, commands, and QA evidence.
Readiness Markdown surfaces the replay seed, renderer, locked-field count,
style/background/header/chart/figure-table pools, replay commands, and artifact
summary paths so a resumed agent can rebuild the same deck family without
rediscovering mix-and-match choices from the long prompt.

You almost never need to pass `--renderer` explicitly. The auto-picker
already selects pptxgenjs for normal editable decks, including common chart
slides. Passing `--renderer python` silently downgrades the
typography on timelines, cards, and section dividers — don't do it.

If you are continuing from an existing deck:

```bash
python3 scripts/init_deck_workspace.py \
  --workspace decks/refactor-deck \
  --title "Refactor Deck" \
  --style-preset executive-clinical \
  --reference-pptx /absolute/path/to/reference.pptx
```

## How The Skill Keeps Layouts Clean

The core engine is clean because it is not placing elements blindly.

1. Text is measured before major layout decisions.
   - `_estimate_text_lines()` and `_estimate_text_height()` estimate how much vertical space a given title/body block needs.
   - `_card_body_font()` reduces body size when the available height is tight.
   - `_card_title_layout()` reduces heading size and increases title box height when a card title is likely to wrap.

2. Cards are sized from content, not fixed templates.
   - `_preferred_card_height()` computes target height from rail, title, and body needs.
   - Split layouts share heights for dense side-by-side cards and collapse sparse sidecars instead of leaving empty mirrored boxes.
   - `variant: image-sidebar` / `visual_intent: hero` uses a reliable native figure-plus-sidebar composition when a staged hero image is present.
   - `variant: scientific-figure` uses native multi-panel figure composition for 1-4 staged figure assets.
   - `variant: lab-run-results` uses compact editable tables with semantic cell fills for table-heavy lab/result slides.

3. Content slides reserve header space dynamically.
   - `_content_header()` now returns the bottom of the title/subtitle stack.
   - Content layouts start at `content_top`, which is derived from that stack instead of a fixed `y` coordinate.
   - This prevents wrapped slide titles from colliding with subtitles and with the top of the main content region.

4. The geometry is linted after generation.
   - `layout_lint.py` checks margins, top alignment, height consistency, gutters, density, empty ratio, and rail/card alignment.
   - `layout_lint.py` also flags content stranded in a short or narrow safe-area band as `content_span_too_short` or `content_span_too_narrow`.
   - `inventory.py` catches overflow and overlap from the actual PPTX text boxes.
   - `visual_qa.py` flags underfilled slides.
   - `design_rules_qa.py` catches polish issues that generic geometry misses;
     when `qa_gate.py` receives `--design-brief`, it also checks rendered
     title/body/caption/table text and explicit native-chart label sizes
     against `readability_contract`.
   - `visual_review.py` creates a contact sheet and flags wrap, orphan-word,
     footer-clearance, safe-area, and layout-rhythm risks after render.

5. The final gate combines those checks.
   - `qa_gate.py` runs the inventory, outline extraction, layout lint, render pass, visual QA, and design QA, then fails the build when the configured thresholds are violated.

## Recommended Iteration Pattern

1. Create a workspace once.
2. If personalization is underspecified, ask the optional intake questions and record answers or assumptions in `design_brief.user_intake`.
3. Use `design_brief.json` for audience posture, cover concept, and structure strategy.
4. Translate intake answers into `design_modulation`, `visual_system`, `title_page_concept`, `deck_style`, `asset_plan`, and `notes.md` before writing slides.
5. If the opener uses chips/tags/stages, record `evidence_continuity` so the motif carries into content slides.
6. If local figures are generated, record `figure_export_contract` with script, outputs, target variants, and crop rules.
7. Use `content_plan.json` for the argument arc and visual strategy.
8. Use `evidence_plan.json` for sourced claims, numbers, and chart candidates.
9. Put persistent data rules, measurements, and unresolved assumptions in `notes.md`.
10. Stage source-backed images, backgrounds, charts, tables, and deliberate generated images through `asset_plan.json`.
11. Keep staged asset names unique after normalization, then reference staged assets in `outline.json` with aliases such as `asset:crew_portrait`, `chart:mission_profile`, or `table:run_summary`.
12. For `source-line` footers, keep per-slide source/ref entries compact and move full citations to an editable References/Image Sources table slide. If preflight reports `source_line_footer_over_budget`, run `scripts/compact_source_footers.py --workspace <workspace>` or let `advance_workspace.py --execute` run the readiness command.
13. Keep any local diagrams and logos in `assets/`.
14. Add or replace slides by editing `outline.json`.
15. Rebuild with `build_workspace.py`.
16. Run `build_workspace.py --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --visual-review` before final delivery.
17. Keep the workspace in version control if the deck matters.

This is the path that gets you closest to the clean “later I added two more slides and everything still matched” workflow.
