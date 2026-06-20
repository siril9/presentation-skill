# Planning Schema

Use these files before authoring `outline.json` when the deck needs researched
content, sourced numbers, or a reusable narrative and design structure.

## `design_brief.json`

Purpose: lock the design strategy before slide variants are chosen. This is
the taste layer: audience posture, cover concept, grid constants, and the
rules that prevent generic card-heavy decks.

Recommended shape:

```json
{
  "topic": "Deck topic",
  "content_maturity": "silly/playful | casual/explainer | serious/work | technical/educational | premium/brand",
  "audience_posture": "friends/fans | students/learners | coworkers/operators | execs/buyers | public/brand",
  "emotional_register": "fun | warm | curious | urgent | trustworthy | cinematic | premium",
  "format_promise": "What the deck should feel like and what it must avoid",
  "anti_format": ["repeated title + 3 cards", "generic dashboard opener"],
  "user_intake": {
    "audience_context": "Who will use/read the deck and in what setting",
    "target_outcome": "What the audience should believe, decide, or do",
    "style_direction": "Requested feel or reference style",
    "density": "sparse live talk | balanced | dense report/leave-behind",
    "palette": "Brand/lab palette, neutral palette, requested colors, colors to avoid",
    "background_visuals": "White report, gradient, photo-backed, source-backed, generated concept, no imagery",
    "evidence_assets": "User-provided figures, tables, raw data, logos, screenshots, papers, or reference decks",
    "source_policy": "quick draft | cite key claims | source every factual claim | use only provided sources",
    "constraints": "Slide count, talk length, aspect ratio, deadline, accessibility, hard avoids",
    "answered_by": "user | inferred | best_judgment",
    "unanswered": "Skipped questions or assumptions"
  },
  "canvas_and_grid": {
    "aspect": "16:9",
    "margin_x_in": 0.5,
    "footer_reserve_in": 0.32,
    "header_policy": "measured title/subtitle stack; body starts at returned contentTop"
  },
  "title_page_concept": {
    "chosen_archetype": "editorial masthead | typographic poster | full-bleed image | artifact cover | one-number cover",
    "dominant_element": "What owns slide 1",
    "supporting_element": "Optional secondary element",
    "why_this_could_only_be_this_deck": "Why the cover is topic-specific"
  },
  "structure_strategy": {
    "primary_scaffold": "open editorial content slides",
    "repeated_elements": ["shared margins", "consistent footer/source treatment"],
    "allowed_variations": ["standard", "split", "table", "flow", "optional kpi-hero"],
    "container_policy": "When cards/boxes are allowed and when they are not",
    "rhythm_break_plan": "Where the deck breaks the grid on purpose"
  },
  "design_dna": "lab results dashboard | board risk memo | product/investor reveal | editorial report | civic science policy | custom",
  "renderer_treatments": {
    "header_mode": "bar | stack | eyebrow | lab-clean | lab-card",
    "header_variant": "auto | left-accent | split-rule | title-rule | side-rail | top-bottom-rule | plain",
    "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
    "title_motif": "orbit | network | editorial | none",
    "section_motif": "rail-dots | none",
    "timeline_mode": "rail-cards | staggered | open-events | bands | chapter-spread",
    "matrix_mode": "cards | open-quadrants",
    "stats_mode": "tiles | feature-left | policy-bands",
    "chart_treatment": "standard | facts-below | facts-right | minimal",
    "footer_mode": "standard | source-line",
    "footer_source_label": "Sources",
    "footer_refs_label": "Refs",
    "summary_callout_mode": "default | lab-box",
    "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar"
  },
  "style_mix_matrix": {
    "header_variant_pool": ["left-accent", "split-rule", "title-rule", "side-rail", "top-bottom-rule", "plain"],
    "title_layout_pool": ["split-hero", "lab-plate", "command-center", "poster", "masthead", "light-atlas"],
    "section_motif_pool": ["rail-dots", "numbered-tabs", "plain"],
    "timeline_mode_pool": ["rail-cards", "staggered", "open-events", "bands", "chapter-spread"],
    "matrix_mode_pool": ["cards", "open-quadrants"],
    "stats_mode_pool": ["tiles", "feature-left", "policy-bands"],
    "cards_mode_pool": ["feature-left", "staggered-row"],
    "chart_treatment_pool": ["standard", "facts-below", "facts-right", "minimal"],
    "summary_callout_mode_pool": ["default", "lab-box"],
    "figure_table_treatment_pool": ["figure-first", "table-first", "stats-strip", "image-sidebar"],
    "footer_pool": ["source-line", "standard", "none"],
    "mix_rule": "Rotate small treatments only when they reinforce the deck DNA",
    "do_not_mix": ["Conflicting treatments or motifs that make the deck feel random"]
  },
  "reproducibility_contract": {
    "contract_version": "deck_reproducibility_contract_v1",
    "stable_prompt_id": "tb-lamp-report-v1",
    "style_seed": "tb-lamp-report-v1",
    "choice_source": "intake_answers.json | explicit user request | best-judgment assumptions",
    "renderer": "pptxgenjs",
    "locked_design_fields": [
      "style_system.style_preset",
      "style_system.background_system",
      "style_system.style_mix_matrix",
      "structure_blueprint.slide_sequence",
      "evidence_and_assets.analysis_artifact_plan",
      "readability_contract",
      "qa_contract"
    ],
    "replay_inputs": {
      "deck_start_packet": "deck_start_packet.json",
      "intake_answers": "intake_answers.json",
      "design_contract": "design_contract.json",
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json"
    },
    "style_replay": {
      "style_preset": "lab-report",
      "background_system": "white report",
      "header_variant_pool": ["split-rule", "top-bottom-rule", "plain"],
      "footer_pool": ["source-line", "standard"],
      "chart_treatment_pool": ["minimal", "facts-right"],
      "figure_table_treatment_pool": ["figure-first", "image-sidebar"],
      "mix_rule": "Rotate small treatments from style_seed while locking evidence layouts",
      "variation_boundaries": ["What may rotate", "What stays fixed in this deck"]
    },
    "structure_replay": {
      "target_slide_count": 8,
      "slide_variant_mix": ["title", "image-sidebar", "lab-run-results"],
      "evidence_anchor_rule": "Every evidence/data slide gets a visible chart, table, figure, or image anchor",
      "white_space_rule": "Choose variants that match actual evidence shape"
    },
    "artifact_replay": {
      "local_data_needed": true,
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json",
      "figure_script": "assets/make_figures.py",
      "rebuild_commands": ["python3 assets/make_figures.py"]
    },
    "replay_commands": [
      "python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ],
    "acceptance_evidence": [
      "design_contract_apply_report.json",
      "build/workspace_readiness.json",
      "build/build_workspace_report.json",
      "build/delivery_readiness.json"
    ]
  },
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
    "carry_forward_rule": "How title-slide chips/tags continue on content slides",
    "slide_applications": [
      {
        "slide_id": "s2",
        "thread": "EVIDENCE",
        "placement": "subtitle eyebrow | sidebar label | footer tag | section strip"
      }
    ]
  },
  "figure_export_contract": {
    "script": "assets/make_figures.py",
    "outputs": [
      {
        "path": "assets/figures/lod_curve.png",
        "target_slide": "s3",
        "target_variant": "image-sidebar | scientific-figure | lab-run-results",
        "target_box": "approximate rendered size, e.g. 5.0x3.3 in",
        "figure_size_inches": [6.4, 3.6],
        "figure_dpi": 180,
        "axis_label_min_pt": 8,
        "crop_rule": "tight content bbox, <=0.08 in visual padding, no large internal whitespace"
      }
    ],
    "rerun_command": "python3 assets/make_figures.py"
  },
  "analysis_artifact_plan": {
    "candidate_data_files": [],
    "spreadsheet_inputs": [],
    "required_scripts": [],
    "figure_scripts": ["assets/make_figures.py"],
    "artifact_manifest": "assets/artifacts_manifest.json",
    "analysis_summary": "assets/analysis_summary.json",
    "analysis_summary_markdown": "assets/analysis_summary.md",
    "chart_json_outputs": [],
    "table_outputs": [],
    "rebuild_commands": ["python3 assets/make_figures.py"],
    "artifact_registry": [
      {
        "id": "artifact_id",
        "path": "assets/figures/example.png",
        "producer": "assets/make_figures.py",
        "used_on_slides": ["s3"],
        "provenance": "data/source/method note"
      }
    ]
  },
  "readability_contract": {
    "min_title_pt": 24,
    "min_body_pt": 12,
    "min_caption_pt": 7.5,
    "max_title_lines": 2,
    "max_slide_text_lines": 8,
    "max_slide_words": 105,
    "max_slide_chars": 700,
    "footer_reserved_inches": 0.34,
    "chart_label_min_pt": 8,
    "table_density_rule": "split or summarize tables that force unreadable text",
    "whitespace_rule": "avoid awkward empty regions; choose variants that fit actual evidence shape",
    "figure_crop_rule": "tight bounding boxes and trimmed exterior whitespace"
  },
  "speed_contract": {
    "renderer": "pptxgenjs by default; Python fallback only for legacy renderer-specific behavior",
    "first_pass": "render-free schema/preflight/geometry QA before rendering",
    "render_policy": "render only after source files are stable or visual judgment matters",
    "asset_policy": "reuse local/generated artifacts before network assets unless source-backed imagery is needed",
    "conversion_hint": "use persistent LibreOffice/unoserver when available for repeated render QA"
  }
}
```

Rules:

- Write `design_brief.json` before `outline.json` for any deck that should
  look designed rather than mechanically rendered.
- For reusable or high-stakes decks, prefer
  `scripts/emit_deck_start_packet.py` immediately after the user request. It
  emits the compact `request_user_input` payload, design-contract scout prompt,
  and staged handoff commands for data analysis, style routing, content
  research, outline critique, and visual QA. The packet also emits
  `recommended_style_seed`; copy that value into `style_system.style_seed`
  unless the user explicitly supplied a seed, and record any override. Use the
  emitted `application_contract` as the checklist for persisting answers,
  translating them into planning files, and running fast first-pass/final QA.
- Use `scripts/emit_deck_intake_prompt.py` before planning when the user wants
  a more nuanced/personalized deck and has not supplied audience, style,
  palette, density, background/visual mode, asset, source, or constraint
  preferences. Ask only high-value missing questions. If the user wants speed,
  record assumptions under `user_intake` and proceed.
- If Codex's native `request_user_input` tool is available, run
  `scripts/emit_deck_intake_prompt.py --codex-ui` and use the emitted question
  packet immediately after the user's deck prompt. If the tool is unavailable,
  ask the same questions in chat.
- For reusable decks, persist question-card answers before applying the design
  contract. Write the response to a small JSON file and run
  `scripts/apply_deck_intake_answers.py --workspace <workspace> --packet
  <workspace>/deck_start_packet.json --answers <workspace>/intake_answers.json`.
  This deterministically fills `design_brief.user_intake`, carries the packet
  `recommended_style_seed` into `style_system.style_seed`, translates compressed
  answers such as `style_density` and `visual_source_policy` into density,
  source-policy, visual-system, and asset-posture fields, and replaces a marked
  `notes.md` section without duplicating content on reruns. When using
  `scripts/emit_deck_start_packet.py`, prefer the emitted
  `after_answers.answer_file_template`, `after_answers.apply_answers_command`,
  and `application_contract.intake_answer_commands` so saved packet paths and
  answer/report paths stay aligned.
- `user_intake` is a bridge, not a final design system. Translate answers into
  `audience_posture`, `format_promise`, `visual_system`,
  `title_page_concept`, `design_modulation`, `renderer_treatments`,
  `asset_plan.json`, `content_plan.json`, and `notes.md` before authoring
  `outline.json`.
- Use `scripts/emit_design_contract_prompt.py` immediately after the user
  request or after intake answers to produce a reproducible JSON contract for
  style, background, structure, source policy, assets, analysis artifacts,
  mix-and-match treatment pools, readability limits, speed policy, continuity,
  replay commands, and QA. The prompt asks for a
  `deck_reproducibility_contract_v1` replay ledger that binds the selected
  seed to the exact background, header/footer treatment pools, chart/table
  posture, slide-variant mix, artifact manifest/summary paths, required
  commands, and acceptance evidence. The main agent can answer it directly for
  simple decks or send it to
  one style scout for high-stakes decks. Save the returned
  `deck_design_contract_v1` JSON as `<workspace>/design_contract.json`, then
  run `scripts/apply_design_contract.py --workspace <workspace> --contract
  <workspace>/design_contract.json --report
  <workspace>/design_contract_apply_report.json` before finalizing
  `outline.json`. Use `--preserve-existing` only when deliberately layering a
  new contract onto already hand-tuned planning files.
- Cards are not a default visual language. Use them only for modular evidence,
  comparisons, dashboards, worksheets, or other content that benefits from
  containment.
- Preserve degrees of freedom. The design brief should constrain what matters
  (readability, alignment, source footer, audience tone) but should not force a
  fixed 8-slide arc, a KPI hero closer, or the full variant menu.
- A cover should have one archetype and one dominant idea. Do not start with
  a generic dashboard, KPI strip, or title-plus-card grid unless the user asks
  for that exact format.
- `design_dna` should limit the variant set. A lab deck should bias toward
  `scientific-figure`, `lab-run-results`, and `image-sidebar`; a product deck
  can use `kpi-hero`, icons, asymmetric cards, and timeline only when the story
  has a real hero metric or image; an editorial deck can use `stack` headers
  and fewer, larger blocks.
- For lab/scientific decks, identify evidence objects before choosing variants.
  Keywords such as ASCO, TB, LAMP, clinical, LOD, sequencing, assay, sample, and
  resistance are priors only. If the evidence shape is figures, plots, assay
  readouts, result tables, run/sample metadata, or validation claims, route to
  lab-report / figure-first layouts. If the same terms appear in a public
  explainer, policy brief, or brand deck, use the corresponding design DNA
  instead.
- `design_modulation` is optional but recommended when the user asks for a
  deck that feels more designed. It should describe bounded micro-design
  choices that the author can apply through supported presets, `deck_style`,
  variants, assets, and captions. It is not permission to invent unchecked
  colors, fonts, or one-off renderer behavior.
- If the cover introduces evidence chips, stage labels, or another motif,
  record it in `evidence_continuity` and carry it through content slides. Do
  not let "Evidence / Readout / Next run" appear only on slide 1; reuse the
  tags as subtitle eyebrows, sidebar labels, footer tags, section strips, or
  table group labels where they clarify the argument.
- Keep `evidence_continuity.slide_applications[*].slide_id` or
  `slide_id_or_index` aligned with `outline.json`, and keep each application
  `thread` within the declared `threads` list. Planning validation warns when
  continuity tags point at deleted slides, omit the slide reference, or use
  undeclared thread labels.
- For generated scientific figures, add `figure_export_contract` before
  rendering. The Python figure script should export assets at the aspect ratio
  the slide will use, trim exterior whitespace, keep legends/captions compact,
  and prefer one large figure plus sidebar when a multi-panel grid would make
  plots unreadable.

## Style/Content Router Output

For non-trivial, researched, asset-heavy, or ambiguous decks, emit one
deck-level scout prompt:

```bash
python3 scripts/emit_style_content_router.py \
  --workspace decks/my-deck \
  --user-prompt "Original user request"
```

The scout returns JSON that the author should apply to `design_brief.json`,
`outline.json`, and asset planning. Recommended shape:

```json
{
  "design_dna": "lab results dashboard",
  "style_preset": "lab-report",
  "deck_style": {
    "style_seed": "tb-lamp-report-v1",
    "header_mode": "lab-clean",
    "header_variant": "auto",
    "title_layout": "lab-plate",
    "footer_mode": "source-line",
    "footer_source_label": "Sources",
    "footer_refs_label": "Refs",
    "summary_callout_mode": "lab-box",
    "figure_table_treatment": "figure-first",
    "research_visual_mode": true
  },
  "design_modulation": {
    "change_intensity": "subtle",
    "base_preset_fit": "preset plus treatment changes",
    "accent_strategy": "use accent only for call states and footer rules",
    "density_strategy": "high report density with readable tables",
    "whitespace_strategy": "compact lab grid with protected captions",
    "motif_strategy": "no decorative motif beyond lab header and source rules",
    "container_strategy": "figure-first and table-first; cards only for concepts",
    "figure_table_treatment": "semantic fills for pass/fail/borderline states",
    "avoid": ["decorative icon evidence"]
  },
  "evidence_continuity": {
    "threads": ["EVIDENCE", "READOUT", "NEXT RUN"],
    "carry_forward_rule": "Use one thread tag per content slide in subtitle/sidebar/table labels; do not leave cover chips as a one-off motif.",
    "slide_applications": [
      {
        "slide_id": "s2",
        "thread": "EVIDENCE",
        "placement": "subtitle eyebrow plus figure caption lead-in"
      }
    ]
  },
  "figure_export_contract": {
    "script": "assets/make_figures.py",
    "rerun_command": "python3 assets/make_figures.py",
    "outputs": [
      {
        "path": "assets/figures/lod_curve.png",
        "target_slide": "s2",
        "target_variant": "image-sidebar",
        "target_box": "5.0x3.5 in",
        "crop_rule": "bbox_inches='tight', pad_inches<=0.05, then optional trim_image_whitespace.py"
      }
    ]
  },
  "routing_basis": [
    "local figures and result tables carry the proof burden"
  ],
  "allowed_variants": [
    "scientific-figure",
    "image-sidebar",
    "lab-run-results",
    "table",
    "comparison-2col"
  ],
  "forbidden_variants": [
    "generic cards-3 without evidence"
  ],
  "slide_routes": [
    {
      "slide_id_or_index": "s3",
      "role": "evidence",
      "variant": "scientific-figure",
      "visual_strategy": "source-backed figure with compact caption",
      "asset_needs": ["image:assay_readout"],
      "evidence_objects": ["plot", "run table"],
      "reason": "the figure is the slide evidence",
      "confidence": 0.85
    }
  ],
  "asset_requests": [],
  "subagent_plan": [
    {
      "stage": "data/evidence analysis",
      "use_subagent": true,
      "prompt_emitter": "scripts/emit_data_analysis_prompt.py",
      "reason": "run tables and figures carry the proof burden",
      "expected_output": "computed findings, chart/table recommendations, binder-ready artifact selections, script edits, and QA handoff",
      "must_not_do": "do not edit final outline or bypass validation"
    }
  ],
  "qa_sensitivities": []
}
```

Use this output as a constraint layer, not as an outline rewrite. The main agent
still authors the story and final slide text.

If the scout recommends content research or data/evidence analysis, run that
before final outline authoring so the design route reflects the actual proof
objects, not just prompt terms.
When an artifact manifest already exists, the data/evidence scout prompt
includes manifest aliases and selection templates. The scout output should
include `artifact_selection_recommendations.bindings` using the same selection
shape accepted by `scripts/apply_artifact_manifest_bindings.py --selection`,
plus `slide_artifact_storyboard`, `main_agent_handoff.commands_to_run`, and
`verification_evidence` so the main agent can bind generated
figures/charts/tables reproducibly and preserve why each artifact belongs on
its target slide. Save the scout JSON and run
`scripts/apply_data_analysis_handoff.py` to apply the deterministic
binding/evidence/storyboard portions before manual analysis-script edits.

## `content_plan.json`

Purpose: decide the story and visual strategy before rendering.

Required shape:

```json
{
  "topic": "Deck topic",
  "audience": "Who will read this",
  "objective": "What the deck should accomplish",
  "thesis": "One-sentence main argument",
  "narrative_arc": [
    {
      "act": "setup",
      "purpose": "Why this matters",
      "slides": ["s1", "s2"]
    }
  ],
  "slide_plan": [
    {
      "slide_id": "s1",
      "role": "title | context | evidence | mechanism | comparison | implication",
      "message": "Single slide takeaway",
      "variant": "title | split | cards-3 | timeline | table | chart | generated-image",
      "visual_strategy": "hero_image | icon_system | chart | table | mermaid | generated-image | none",
      "evidence_needs": ["ev1"],
      "asset_needs": ["image:hero_photo"]
    }
  ],
  "design_notes": {
    "style_preset_reason": "",
    "rhythm_break": "",
    "visual_motif": ""
  }
}
```

Rules:

- Every planned content slide should have a specific `message`.
- Every planned content slide should choose a `visual_strategy`; use `none`
  only with an explicit reason in `notes.md`.
- Keep `slide_plan[*].slide_id` aligned with `outline.json`: use the same
  explicit `slide_id`/`id`/`slug` on outline slides, or stable positional IDs
  such as `s1`, `s2`, and `s3`. Planning validation warns when a planned slide
  ID is missing from the outline or when a planned `variant` no longer matches
  the renderable outline slide. It also warns when explicit outline slide
  identifiers are duplicated, because plan/evidence references become
  ambiguous.
- Keep `narrative_arc[*].slides` aligned with `slide_plan[*].slide_id` and the
  renderable outline. Planning validation warns when the story arc references
  a slide that is not planned or no longer exists in `outline.json`.
- `evidence_needs` should reference IDs in `evidence_plan.json` when the slide
  makes factual claims.
- When a renderable outline slide declares `slide_intent: "evidence"`,
  data/figure/table `visual_intent`, `evidence_needs`, or `evidence_objects`,
  preflight expects a concrete evidence anchor: chart, table, figure, image,
  diagram, stats, KPI, flow, or structured comparison. Generic prose/cards
  should be rewritten as an evidence-first variant or given staged assets.
- For public/researched topics, prefer `visual_strategy: "source-backed-image"`
  on 1-2 slides with a clear visual role. The helper
  `scripts/plan_research_assets.py` can convert those opportunities into
  Wikimedia queries, staged `image:<name>` aliases, and an attribution-backed
  Image Sources slide.

## `evidence_plan.json`

Purpose: keep factual substance and citations separate from layout.

Required shape:

```json
{
  "topic": "Deck topic",
  "source_policy": "Prefer primary or source-backed facts.",
  "items": [
    {
      "id": "ev1",
      "claim": "Claim to support",
      "value": "42",
      "unit": "%",
      "date_or_period": "2024",
      "source_title": "Source title",
      "source_url": "https://example.org/report",
      "source_note": "Table 2",
      "used_on_slides": ["s3"],
      "visual_use": "bullet | kpi | figure | chart | table | footer-source"
    }
  ],
  "chart_candidates": [
    {
      "id": "chart1",
      "question": "What should this chart answer?",
      "series_needed": ["series A", "series B"],
      "source_ids": ["ev1"],
      "target_slide": "s4"
    }
  ],
  "open_questions": []
}
```

Rules:

- Do not put unsupported numbers directly into `outline.json`; stage them here
  first.
- Include `source_policy` whenever `items` or `chart_candidates` are present;
  planning validation warns when evidence-backed claims or chart candidates lack
  a deck-level citation/source rule.
- `source_url` or `source_note` is expected for any item used as a KPI, figure,
  chart, table, or source footer. When a generated evidence object appears as
  more than one visual form, use a deterministic pipe-delimited value such as
  `figure | chart | table`.
- `items[*].used_on_slides` and `chart_candidates[*].target_slide` should
  resolve to explicit outline `slide_id`/`id`/`slug` values or stable
  positional IDs such as `s2`; planning validation warns when evidence points
  at deleted or renamed slides.
- `chart_candidates[*].source_ids` should reference evidence `items[*].id`
  values so chart specs remain traceable to sourced claims.
- `chart_candidates` should become either staged chart JSON in `asset_plan.json`
  or a deliberate non-chart decision in `notes.md`.

## Build Integration

`build_workspace.py` runs `scripts/validate_planning.py` when these files exist.
Malformed JSON or broken evidence references should be fixed before the final
deck build.
The optional JSON report is written idempotently: unchanged validation payloads
preserve the existing report file and mtime.

The same validation pass also checks design-contract fields that make
scientific/report decks reproducible:

- `style_mix_matrix`: supported header/title/footer/section/timeline/matrix/
  stats/cards/chart/callout/figure-table treatment pools and a `mix_rule` for
  rotating treatments without random-looking slides.
  Fresh workspaces scaffold a conservative baseline matrix under
  `style_system.style_mix_matrix`; tune or narrow it once the deck DNA and
  evidence shape are known.
  Treatment pool entries should be unique; duplicate values are planning
  warnings because they reduce useful deterministic variation. Header pools
  should retain at least two unique supported variants, and the matrix should
  keep at least two treatment pools with two or more unique supported entries
  so seeded decks can vary rhythm without randomness. If a
  `style_mix_matrix` is present, declare a stable `style_seed` in
  `style_system`, `renderer_treatments`, or `deck_style`; otherwise planning
  validation warns because treatment rotation will rely on fallback text.
  `build_workspace.py` uses `style_system.style_preset` for renderer/QA preset
  selection, accepts scaffolded `visual_system.style_preset` as the compatibility
  source, and translates the remaining defaults into `build/outline_resolved.json`.
  Repeated workspace builds preserve that derived file when the resolved payload
  is unchanged. For lab/report decks, the resolved outline also includes
  generated per-slide `resolved_treatments.header_variant` values and a compact
  `resolved_treatment_summary`; use these as audit evidence for seeded
  mix-and-match header rhythm, not as source fields to hand-edit.
  A short `style_seed` in `style_system`, `renderer_treatments`, or `deck_style`
  locks deterministic treatment-pool resolution so repeated builds match while
  similar report decks can still have different title/footer/section/header
  rhythms. Valid `header_variants` lists in `style_system.header_system`,
  `renderer_treatments`, `deck_style`, or `style_mix_matrix.header_variant_pool`
  become the renderer-visible auto pool.
  Unsupported explicit preset values and conflicting explicit preset
  declarations are validation/build errors. Unsupported direct treatment enum
  values in `style_system`, `renderer_treatments`, or `deck_style` are also
  validation/build errors, including invalid `header_variants` pool entries.
  Explicit `outline.deck_style` values override the design brief for deck-style fields.
- `reproducibility_contract`: compact replay ledger for the design contract.
  New contracts should use `deck_reproducibility_contract_v1` to record the
  stable style seed, renderer, locked source fields, style/background/header/
  footer/chart/figure-table replay choices, slide-variant mix, artifact
  manifest and analysis-summary paths, replay commands, and acceptance
  evidence. `apply_design_contract.py` fills a compatible replay ledger when a
  scout omits it, and readiness reports surface the compact summary so a
  resumed agent can rebuild the same deck family without reopening the long
  prompt.
- `figure_export_contract`: deterministic figure script, slide-ready outputs,
  target variants, crop/whitespace rules, and existing output files once the
  figure script has been run. Optional `outputs[*].target_slide` references
  should resolve to explicit outline slide IDs or stable positional IDs, and
  `target_variant` should match the resolved outline slide variant.
  `target_box` should be a parseable width-by-height inch string such as
  `5.0x3.3 in`; validation warns when a declared box is missing,
  unparseable, or too small for readable figure labels. Generated figure
  outputs should also declare `figure_size_inches`, `figure_dpi`, and
  `axis_label_min_pt`; validation warns when those export/readability fields
  are missing or non-positive. `rerun_command` should include the declared
  figure script path; it may also include follow-on trimming or export-polish
  commands. When `outline.json` exists, declared outputs should also appear in
  the outline, resolve through an asset alias,
  or carry explicit `used_on_slides` metadata.
- `analysis_artifact_plan`: data/spreadsheet inputs, figure scripts, a
  deterministic `artifact_manifest` path, rebuild commands, chart/table
  outputs, and an `artifact_registry` that maps produced files to slides and
  provenance. The manifest JSON is schema-checked when present; validation
  warns when its output count, alias prefixes, local file fingerprints, or
  registry coverage no longer match the generated artifacts. Registry ids and
  normalized paths should be unique; duplicates are planning warnings because
  they make artifact
  provenance and slide-use mapping ambiguous. Registry paths should point at
  existing local artifacts once the figure/data scripts have run. `producer`
  can be a human-readable source label, but path-like script/source producers
  should resolve to local files. Repeated input/script/output path entries and
  repeated rebuild commands are also planning warnings; keep the contract
  concise enough that rebuild order and freshness checks are obvious.
  Registry `used_on_slides` entries should resolve to explicit outline slide
  IDs or stable positional IDs; validation warns when generated artifacts point
  at deleted or renamed slides. Declared chart/table output paths should also
  be referenced in `outline.json` through the path or an `asset_plan` alias, or
  carry non-empty registry `used_on_slides` metadata, so generated structured
  artifacts do not drift away from the slides that consume them.
  Validation warns when declared figure, chart, or table outputs are older than
  their newest listed input or script;
  rerun a listed `rebuild_commands` entry before the final build. Declared
  chart JSON outputs may use either non-empty `series[].values` with
  labels/categories or compact top-level `categories`/`values`, matching
  `asset_stage.py` and the fast renderer. Registry-only chart/table JSON
  paths are also payload-validated when the entry type or normalized path
  clearly identifies the artifact as a structured chart/table output.
  Scaffold-generated chart/table JSON and registry entries carry
  `analysis_metadata` with source path, source SHA-256, producer script path,
  producer SHA-256, source/producer sizes, selected columns, rows used, series
  count, and point count; validation warns when generated-looking artifacts
  lack that metadata or when recorded source/producer fingerprints no longer
  match local files.
- `asset_plan.json`: source-backed images, backgrounds, charts, tables, and
  generated images may declare `used_on_slides`; those slide references should
  resolve to explicit outline IDs or stable positional IDs so staged assets do
  not drift away from the slides that consume them. Non-URL local `path`
  entries should exist by final planning, or be created by the listed artifact
  scripts, so image/chart/table staging does not fail late. Existing local
  chart/table JSON paths and inline chart/table entries should pass the same
  payload-shape checks used by staging: charts need numeric values with
  labels/categories, and tables need non-empty headers plus matching row widths.
  Local image/background entries should include at least one provenance field
  (`source_note`, `source_url`, `source_page`, `license`, or `provenance`) so
  strict provenance staging and image-source slides remain auditable.
  Generated image entries should include `prompt`, `model`, and `purpose` even
  when a local `path` is supplied, so disclosure and regeneration metadata can
  be carried into staged sidecars and source slides.
- `readability_contract`: numeric minimums for title/body/caption/chart labels,
  optional static prose budgets (`max_slide_text_lines`, `max_slide_words`,
  `max_slide_chars`), footer reserve, table-density rule, whitespace rule, and
  figure crop rule.
  Planning validation warns when numeric thresholds are missing, boolean,
  non-numeric, or below the safe floors: title 24 pt, body 12 pt, caption
  7.5 pt, chart labels 7 pt, and footer reserve 0.25 in. It also warns when
  `max_title_lines` is below 1 or above 3 and when optional prose budgets are
  non-positive.
  Design QA warns when non-footer text enters the declared
  `footer_reserved_inches` band. Preflight also warns when editable table
  row/column shape or long cell text violates the table-density intent, when
  estimated slide-title wrapping exceeds `max_title_lines`, when the estimated
  final title line is a single short orphan word, and when standard, split,
  card, comparison, or image-sidebar prose exceeds readable text budgets before
  rendering, including single long paragraphs that are only one outline field.
  It also warns when content-slide subtitles are estimated to exceed two
  header lines, when evidence chart slides lack caption/footer/source
  provenance, and when image-sidebar figure slides lack caption, footer, or
  sources. Workspace builds pass `design_brief.json` into preflight so those
  optional title/prose budgets can tighten or relax the defaults.
  Preflight also flags visible `outline.json` placeholder markers (`TODO`,
  `TBD`, `XXX`, `lorem/ipsum`, `[insert ...]`, `[placeholder ...]`) before
  render; keep unresolved tasks in `notes.md`, not slide copy.
- `speed_contract`: renderer choice, fast first-pass QA, render policy, asset
  policy, and a conversion hint for repeated render QA. Planning validation
  warns when `renderer`, `first_pass`, `render_policy`, `asset_policy`, or
  `conversion_hint` is missing so reusable/report decks keep a fast QA path.

When `qa_gate.py` is run with the outline, `layout_lint.py` reports
`content_span_too_short` and `content_span_too_narrow` warnings for slides
whose content is stranded in a small safe-area band. The usual fix is to
enlarge the evidence object, add a table, sidebar, or visual anchor, or switch
to a deliberate sparse variant instead of leaving accidental dead whitespace.
Use `qa_gate.py --fail-on-whitespace-warnings` when final polish should block
on those dead-space findings without failing unrelated density or alignment
warnings.

Warnings are guidance for the main agent unless the JSON shape is malformed.
Blocking errors remain malformed JSON, invalid required list/object shapes, and
broken core planning references.

Before rendering, `scripts/report_workspace_readiness.py --workspace
decks/my-deck` can produce `build/workspace_readiness.json` and
`build/workspace_readiness.md` without mutating deck sources or building a
PPTX. Use them to see combined planning/preflight counts and issue keys,
resolved style preset/seed/treatments, outline composition and visual-anchor
coverage, artifact-manifest output aliases, unbound generated artifact IDs,
source-coverage recommendations, local tabular-data detection, last-build
source-fingerprint freshness, compact build-speed timings, and recommended
next commands with a prioritized `next_action`, slide IDs, and suggested
fields/variants before deciding whether to record/apply intake answers,
scaffold data artifacts, bind a manifest, fix warnings, rebuild a stale PPTX,
or run the full build. Treat `ready` as clean only when there are no
planning/preflight warnings and no open readiness recommendations. If a
`deck_start_packet.json` exists but `intake_answers.json` is missing,
readiness produces a source-edit handoff for `intake_answers.json`. If
`intake_answers.json` exists but is unapplied or stale,
`apply_deck_intake_answers` is prioritized before design-contract application.
If a
`data_analysis_handoff.json` scout output exists but is unapplied or stale,
`apply_data_analysis_handoff` is prioritized before generic artifact binding.
If an artifact manifest exists but neither `artifact_selections.auto.json` nor
an applied scout selection covers every output, `bind_generated_artifacts` is
prioritized before generic planning-warning cleanup because the binding command
can resolve generated-artifact slide-reference warnings directly.

When the next step should be reproducible from that readiness state, run:

```bash
python3 scripts/advance_workspace.py --workspace decks/my-deck --execute --max-steps 3
```

It records `build/workspace_advance_report.json` and
`build/workspace_next_action.md`. The advancer executes command-type
`next_action` entries only with `--execute`, reruns readiness after each
command, and stops with an agent-facing prompt when the remaining work is a
source edit. This keeps resume loops deterministic without asking the model to
guess which command or slide IDs mattered. The advance report's
`source_edit_plan` turns slide-level recommendations and repeated preflight
warnings into concrete edit targets: workspace-relative file, slide ID, slide
index, JSON path, suggested operation, and any relevant rule/fix text.
Planning warnings from `analysis_artifact_plan.analysis_summary.*` map to a
specific summary repair/rebuild operation so stale schema, source-path, alias,
row/point-count, and readability assumptions are not hidden inside generic
artifact-registry cleanup.
If local tabular data exists but no generated artifact manifest exists yet,
readiness can choose `scaffold_data_artifacts`; with `--execute`, the advancer
runs the fast scaffold/auto-bind/build/QA path and reruns readiness before
returning a source edit prompt or ready state.

After the strict build, run the delivery audit:

```bash
python3 scripts/report_delivery_readiness.py --workspace decks/my-deck
```

The audit writes `build/delivery_readiness.json` and
`build/delivery_readiness.md`, combining current source readiness, the latest
build report, source-fingerprint freshness, output PPTX fingerprints, QA counts,
strict warning-gate options, and replay commands. `ready` means the deck has
source readiness, source files that still match the latest build report, a
built PPTX, QA evidence, no blocking QA counts, and strict
planning/whitespace gates. Office output snapshots carry raw SHA-256 plus an
`office_package_normalized_v1` content hash so repeat-build reproducibility can
be verified despite volatile Office package timestamps. Blocked and needs-attention reports include a
delivery-level `recommended_next_action` plus a Markdown Next Action section
with the command or `advance_workspace.py` handoff. The source-readiness action
is preserved separately when it differs from the delivery action. Use
`--allow-skip-render` only for accepted render-free delivery, and
`--require-visual-review` when a rendered contact-sheet review is part of final
acceptance.

For the deterministic handoff after the audit, run:

```bash
python3 scripts/advance_delivery.py --workspace decks/my-deck
```

It writes `build/delivery_advance_report.json` and
`build/delivery_next_action.md` with the immediate delivery command or
source-edit handoff, including `inspect_delivery_warnings` when build-report
warning counts remain. Use `--execute` only when the environment is ready for
the recommended command, especially strict final builds that require rendering.

For simple local CSV/TSV/XLSX/JSON tables, use the deterministic artifact
scaffold before hand-authoring chart specs. The integrated workspace path runs
before planning validation and asset staging:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck --fast-first-pass
```

Use this render-free command for the fast first pass from data to reusable
artifacts and bound evidence slides. It expands to the strict scaffold,
auto-bind, render-free QA, planning-warning, whitespace-warning, and overwrite
flags; run a rendered strict build for final delivery. Delivery readiness keeps
fast-first-pass builds in `needs_attention` with `fast_first_pass_not_final`
and recommends the strict final build command.

With `--auto-bind-artifacts`, the integrated path writes
`artifact_selections.auto.json`, applies `assets/artifacts_manifest.json`, and
creates stable figure/chart/table evidence slides before planning validation
and asset staging.
The same successful build writes `build/build_workspace_report.json`, which
summarizes renderer/preset resolution, source and output fingerprints,
artifact bindings, planning/preflight/QA counts, and replay commands. For
Office outputs, use `normalized_sha256` to compare repeat-build content
stability and raw `sha256` for byte-level package diagnostics. Use that
report as the first audit surface before opening individual scaffold, staging,
or QA JSON files.

For a separate scaffold/refine step, run:

```bash
python3 scripts/scaffold_figure_artifacts.py \
  --workspace decks/my-deck \
  --run \
  --bind-outline
```

The scaffold infers one chart per usable CSV/TSV/JSON/Parquet/Feather table or
Excel worksheet, writes `assets/make_figures.py`, exports
`assets/figures/*.png`, `assets/charts/*.json`,
`assets/tables/*_summary.json`, `assets/artifacts_manifest.json`,
`assets/analysis_summary.json`, and `assets/analysis_summary.md`, then
updates
`figure_export_contract`, `analysis_artifact_plan`, `asset_plan.images`,
`asset_plan.charts`, and `asset_plan.tables`. When aligned numeric columns are
present, the generated chart JSON and figure can carry a small multi-series
grouped/line chart, and the generated summary-table JSON can render as an
editable `lab-run-results` or `table` slide. Parquet/Feather inputs require
pandas with a compatible columnar engine; missing engines appear in the
scaffold report's `skipped` list with a dependency reason.
The chart/table JSON and `analysis_artifact_plan.artifact_registry` entries
also include `analysis_metadata` for source and producer-script
fingerprinting, selected columns, rows used, target box, figure export size,
DPI, and label font assumptions for later audit. Planning validation treats
missing generated-artifact export metadata as a warning so report decks can
fix figure readability assumptions before final render, and it warns when a
recorded source or producer SHA-256/byte count does not match the current
local source file or figure script.
Treat generated aliases such as `image:<chart_id>_figure`,
`chart:<chart_id>`, and `table:<chart_id>_summary` as reusable slide inputs.
Use `assets/analysis_summary.json` or its Markdown companion as the quick
human/agent readout of source paths, selected columns, aliases, row/point
counts, and readability assumptions before binding outputs into slides.
Planning validation checks the declared summary file for schema version,
matching manifest path, source-path coverage, generated aliases, non-negative
row/point counts, and figure readability assumptions.
The scaffold report also includes an `alias_plan` with those aliases plus
copy-ready `outline_field_snippets` for `image-sidebar`, `chart`, and
`lab-run-results` slides, selected-column provenance, plus
`artifact_bindings` that name the matching artifact-registry IDs and expected
outline fields. After choosing slide IDs, copy those IDs into
`analysis_artifact_plan.artifact_registry[*].used_on_slides`
for the matching generated figure/chart/table and set
`figure_export_contract.outputs[*].target_slide` for any figure slide. This
keeps the final outline, artifact registry, selected-column provenance, and
figure-export contract aligned without reconstructing aliases by hand. Auto
bindings use the primary analysis readout for capped slide titles and
content/evidence messages, then write compact source-plus-column captions onto
generated evidence slides. Bound evidence items carry generated artifact IDs,
role-keyed aliases, and paths so claim-to-figure/chart/table provenance can be
audited from `evidence_plan.json`. Planning validation warns when those optional
fields are malformed, use the wrong alias prefix, or point at missing local
artifact paths. If the data/evidence scout is involved, its
`slide_artifact_storyboard` should also record slide IDs, variants, output IDs,
artifact roles, source data paths, figure scripts, and layout quality targets;
the applicator persists that storyboard under
`design_brief.data_analysis_handoff.artifact_storyboard` and
`analysis_artifact_plan.data_artifact_storyboard` for readiness and delivery
handoffs. If the
outline already references the
generated aliases or artifact paths, `--bind-outline` applies those bindings
automatically; the integrated `build_workspace.py --scaffold-data-artifacts`
path requests this binding before planning validation.
If only `assets/artifacts_manifest.json` remains available later, run:

```bash
python3 scripts/inspect_artifact_manifest.py --workspace decks/my-deck \
  --report decks/my-deck/artifact_binding_report.json
```

The report reconstructs the same slide-ready alias plan, recommended
`image-sidebar`/`chart`/`lab-run-results` fields, required artifact IDs, and
post-selection binding updates from the manifest.
To apply all generated outputs as a standard editable evidence triplet, let the
helper write a deterministic selection file:

```bash
python3 scripts/apply_artifact_manifest_bindings.py \
  --workspace decks/my-deck \
  --auto-select \
  --selection-out decks/my-deck/artifact_selections.auto.json \
  --report decks/my-deck/artifact_apply_report.json
```

Auto-selection creates one `image-sidebar`, one `chart`, and one
`lab-run-results` slide for each manifest output when those artifact forms are
available, using stable slide IDs such as `<output_id>_figure`,
`<output_id>_chart`, and `<output_id>_table`. Readiness promotes this same
auto-selection command when an existing manifest is unbound or only partially
bound, so the advancer can run the binder before asking the main agent to patch
planning warnings manually. Use this for fast, reproducible first-pass
lab/report decks; switch to an explicit selection file when only a subset of
outputs should appear or the titles/slide IDs need domain-specific wording.

For custom choices, write a selection file:

```json
{
  "bindings": [
    {
      "output_id": "run_workbook_run_a_signal",
      "variant": "image-sidebar",
      "slide_id": "run_a_figure",
      "title": "Run A generated figure",
      "interpretation": "Short readout for the slide."
    }
  ]
}
```

Then run:

```bash
python3 scripts/apply_artifact_manifest_bindings.py \
  --workspace decks/my-deck \
  --selection decks/my-deck/artifact_selections.json \
  --report decks/my-deck/artifact_apply_report.json
```

The apply report lists changed slide IDs and required artifact IDs; rerun
`validate_planning.py` before the strict workspace build. The helper also
upserts matching `content_plan.slide_plan` entries, so generated evidence
slides stay visible in the planning map rather than existing only in
`outline.json`. It also creates or merges `evidence_plan.items` for the
manifest output IDs used in `content_plan.evidence_needs`, including compact
source policy, source notes, and `used_on_slides` links.
When multiple files or worksheets infer the same base chart ID, the scaffold
adds a deterministic short hash suffix so generated figure, chart, table,
asset-plan, and artifact-registry IDs stay unique without random churn.
Treat the generated script as a starting point for real filtering, statistics,
annotations, and multi-panel figures. The integrated build path will not
overwrite an existing figure script unless
`--overwrite-data-artifacts` is passed.

For a source-backed visual pass, run:

```bash
python3 scripts/build_workspace.py --workspace decks/my-deck \
  --plan-research-assets --allow-network-assets --qa --overwrite
```

Use this only when online image sourcing is appropriate for the deck. Private
lab data, proprietary screenshots, or source-free internal readouts should use
local assets instead.
