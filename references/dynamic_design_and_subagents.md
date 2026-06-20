# Dynamic Design And Subagents

Use this reference when a deck needs adaptive style choices, researched
content, local data analysis, or multi-pass QA. The goal is dynamic but
bounded behavior: subtle changes should match the content, not produce a new
visual system on every slide.

## Deck Start Packet

For reusable, sourced, personalized, or lab/scientific decks, start with one
deterministic packet:

```bash
python3 scripts/emit_deck_start_packet.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request"
```

The packet contains:

- `request_user_input`: a compact Codex-native question payload for audience,
  style/density, and visual/source posture.
- `subagent_prompt`: the strict design-contract prompt to answer directly or
  paste into one design scout.
- `after_answers.optional_scouts`: staged commands for style/content routing,
  data/evidence analysis, outline authoring, content research, outline
  critique, and rendered visual QA.
- `application_contract.visual_review_commands`: the contact-sheet QA build,
  `--require-visual-review` delivery audit, and delivery advancer command to
  run once source text is stable.
- `execution_plan`: ordered main-agent phases with triggers, owners, commands,
  files written, and continue conditions from intake through delivery.
- `acceptance_checklist`: proof files/fields plus establish or verify commands
  for intake, design contract, artifact binding, source readiness, first-pass
  QA, and final delivery readiness.
- `reproducibility_requirements`: the style, artifact, and QA decisions that
  must be explicit before `outline.json` is final.

Use the packet instead of separate ad hoc questioning when the deck should be
rebuildable. If the user does not answer within the question timeout, continue
with best judgment and record assumptions under `design_brief.user_intake`.

## User Intake Before Subagents

When the user wants a nuanced or personalized deck but has not specified
audience, style, palette, density, background/visual mode, assets, source
policy, or hard constraints, run:

```bash
python3 scripts/emit_deck_intake_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request" \
  --mapping
```

When Codex's native `request_user_input` tool is available, prefer the compact
question-card packet:

```bash
python3 scripts/emit_deck_intake_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request" \
  --codex-ui
```

Call `request_user_input` with the emitted `questions` immediately after the
user prompt. If the tool is unavailable, ask those questions in chat. Ask only
the useful missing questions and accept "use best judgment" for any item.
Record answers or assumptions under `design_brief.user_intake`, then translate
them into `design_modulation`, `visual_system`, `title_page_concept`,
`deck_style`, `asset_plan`, and `notes.md`.

Do not use a subagent to interview the user. Use subagents after intake when
the deck needs content research, local data analysis, style/content routing,
outline critique, or rendered visual QA.

## Dynamic Design Modulation

Pick a base `style_preset` first, then describe the small design moves that
make it suitable for this deck. Do not hand-roll inline colors or font names
unless you are also adding a validated preset or font pair.
Use `scripts/style_treatment_profiles.py` as the first source for
preset-specific heading/accent, footer, chart, and figure/table treatment
pools. Deck-start packets and design-contract prompts surface the same
`deck_preset_treatment_profiles_v1` profile so scouts can refine supported
pools without drifting into unsupported renderer treatments.

Recommended `design_brief.json` field:

```json
{
  "design_modulation": {
    "change_intensity": "subtle | moderate | bold",
    "base_preset_fit": "base preset is enough | preset plus treatment changes | new preset needed",
    "accent_strategy": "where accent color appears and where it must not",
    "density_strategy": "low live-talk density | medium brief | high report density",
    "whitespace_strategy": "more breathing room | compact report grid | poster-like open field",
    "motif_strategy": "specific motif or none; must relate to topic/evidence",
    "container_strategy": "cards, panels, open grid, table-first, figure-first",
    "figure_table_treatment": "caption/source/table density and semantic highlight rules",
    "avoid": ["visual move that would make this deck generic or misleading"]
  },
  "evidence_continuity": {
    "threads": ["EVIDENCE", "READOUT", "NEXT RUN"],
    "carry_forward_rule": "how cover chips or evidence tags continue after slide 1"
  },
  "figure_export_contract": {
    "script": "assets/make_figures.py",
    "rules": ["export for target slide box", "trim whitespace", "avoid dense multi-panel plots when labels become unreadable"]
  }
}
```

Examples:

- Lab update: subtle intensity, lab-clean header, source-line footer, figure
  frames, compact captions, semantic table fills. Avoid decorative icon grids.
- Board risk memo: moderate intensity, command-center cover, status colors,
  sparse language, owner/risk tables. Avoid playful motifs.
- Editorial explainer: subtle/moderate intensity, masthead cover, warm paper,
  artifact imagery, fewer larger prose blocks. Avoid dashboard cards.
- Product launch: bold intensity only when the content has a true hero moment;
  use one cinematic KPI or product visual, then evidence. Avoid SaaS card walls.

If `motif_strategy` introduces tags, chips, or stages on the title slide, also
define `evidence_continuity`. A motif that appears only on slide 1 is a
template tell, not a design system.

For lab/scientific decks with generated figures, define
`figure_export_contract`. The contract should say which Python script makes the
figures, which slide variant/box each output targets, and how whitespace is
trimmed before rendering. Prefer a larger `image-sidebar` figure when a
3-4-panel `scientific-figure` grid would make axes, labels, gels, or traces too
small. When `scaffold_figure_artifacts.py` creates local analysis outputs, use
the shared `presentation_skill_artifact_rebuild_context_v1` object in the
manifest, analysis summary, scaffold report, `analysis_artifact_plan`, and
`figure_export_contract` as the source of truth for rebuild, inspect,
auto-bind, and validation commands.

## Subagent Pipeline

Use subagents for independent judgment or specialized analysis. Do not use them
for deterministic checks that scripts already handle.

| Stage | Use When | Prompt Emitter | Expected Output | Main Agent Role |
|---|---|---|---|---|
| Deck start packet | Deck needs reproducible first-turn setup or mixed user/scout handoff | `scripts/emit_deck_start_packet.py` | Question packet, `deck_agent_kickoff_brief_v1`, design-contract prompt, staged scout commands, and application checklist | Ask the useful question card, read the kickoff brief, record assumptions, follow the command ladder, then lock the design contract |
| User intake | Personalization is desired but prompt lacks audience/style/palette/density/background/asset constraints | `scripts/emit_deck_intake_prompt.py` | User answers or best-judgment assumptions in `design_brief.user_intake` | Ask user directly, persist answers, translate to plans |
| PPTX style extraction | User supplies example decks, a branded PPTX, or a style corpus and wants reproducible inspiration | `scripts/extract_pptx_style.py` then `scripts/apply_pptx_style_fragment.py` | JSON/Markdown observations, a `design_brief.json` fragment, and an apply report with changed/skipped fields | Apply only bounded design signals, then run design-contract or style/content routing |
| Content research scout | Public/researched deck has generic or hedged claims | `scripts/emit_content_research.py` | Slide-indexed punch list of concrete facts/source types | Verify, select, and edit plans/outline |
| Data/evidence analysis scout | Workspace has data files, result tables, local figures, or chart candidates | `scripts/emit_data_analysis_prompt.py` | JSON with computed findings, chart/table candidates, binder-ready artifact selections, script edits, and QA handoff | Implement deterministic analysis/figure scripts, apply manifest bindings, or update evidence plan |
| Figure artifact scaffold | Simple local CSV/TSV/XLSX/JSON tables or Excel worksheets should become repeatable charts/figures/tables | `scripts/scaffold_figure_artifacts.py` or `build_workspace.py --scaffold-data-artifacts` | `assets/make_figures.py`, `assets/figures/*.png`, multi-series-capable `assets/charts/*.json`, staged `table:<name>` summary-table aliases, `presentation_skill_artifact_rebuild_context_v1`, and planning updates | Edit the generated starter script for real analysis and rerun it before final outline authoring |
| Outline authoring handoff | Design contract is applied but `outline.json` is still starter-like or missing contract-authored content | `scripts/emit_outline_authoring_prompt.py`, then `scripts/apply_outline_authoring_handoff.py` | Strict `outline_authoring_handoff_v1` JSON shape plus deterministic source apply report | Main agent verifies the handoff, saves it as `outline_authoring_handoff.json`, applies it source-first, and owns final fact/source checks |
| Style/content routing scout | Deck is non-trivial, lab/scientific, asset-heavy, or visually ambiguous | `scripts/emit_style_content_router.py` | JSON with design DNA, `design_modulation`, variants, asset needs, QA sensitivities | Apply constraints to `design_brief.json`, plans, and outline |
| Outline critique | Draft outline exists before rendering | `scripts/emit_outline_critique.py` | Punch list for monotony, weak visual anchors, unsuitable variants | Patch source outline |
| Rendered visual QA | PPTX has rendered JPGs | `render_slides.py --emit-visual-prompt` plus `visual_review.py` | Fresh-eyes composition issues and heuristic findings | Patch source and rebuild |

Recommended order for complex decks:

1. Deck start packet, or user intake if only the question card is needed.
2. Design-contract scout or direct main-agent contract answer.
3. PPTX style extraction when a template, prior deck, or corpus should inform
   bounded style choices.
4. Content research or data/evidence analysis, if needed.
5. Figure artifact scaffold for simple local tables that should become
   repeatable charts/figures.
6. Style/content routing with the improved evidence context.
7. Outline authoring handoff when the locked contract needs a reproducible
   source-edit packet.
8. Main-agent authoring of `design_brief.json`, `content_plan.json`,
   `evidence_plan.json`, `asset_plan.json`, and `outline.json`.
9. Outline critique before first final build.
10. Deterministic QA.
11. Rendered visual review.

## Boundaries

- Subagents may suggest facts, computations, and routes; they do not own final
  deck authorship.
- The main agent must verify externally sourced facts and must decide what
  enters `evidence_plan.json`.
- Data analysis should produce provenance: file path, columns/rows used,
  method, assumptions, and whether values are synthetic or real. If a generated
  artifact manifest already exists, the scout should use its aliases and return
  `artifact_selection_recommendations.bindings` that can be saved directly as a
  selection file for `scripts/apply_artifact_manifest_bindings.py --selection`.
  Prefer `scripts/apply_data_analysis_handoff.py` for the returned scout JSON so
  the selection file, manifest bindings, evidence updates, and notes handoff are
  applied together.
- If analysis is repeatable or used for figures, convert it into a workspace
  script such as `assets/make_figures.py`, record it in `asset_plan.json`, and
  add the output sizing/cropping rules to `figure_export_contract`.
- Use `build_workspace.py --scaffold-data-artifacts` or
  `scripts/scaffold_figure_artifacts.py --workspace <deck> --run` as the first
  deterministic draft for simple local tables. The scaffold scans Excel
  workbooks sheet-by-sheet and emits small multi-series chart JSON plus compact
  summary-table JSON when aligned numeric columns exist. Staged table outputs
  can be referenced as `table:<name>` in `table` and `lab-run-results` slides.
  It is not a substitute for scientific analysis; edit the generated
  `assets/make_figures.py` for real denominators, filters, statistics,
  annotations, and chart/table choices.
- Do not spawn a subagent for a single slide variant choice, JSON syntax, QA
  gate output, or other deterministic script work.
