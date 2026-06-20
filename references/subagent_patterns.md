# Subagent Patterns

When a subagent helps vs. hurts pptx creation. Short rules, curated
patterns, and anti-patterns.

## Decision rule

Use a subagent when **at least one** of these is true:
- The work benefits from **fresh eyes** (main agent has been staring at
  code and will confirm its own assumptions).
- Sub-tasks are **independent** and parallelizable (N slide XML files).
- The task needs **specialized context** that would otherwise dilute the
  main agent's working memory.

Don't use a subagent when:
- A deterministic script can do it (`preflight.py`, `layout_lint.py`,
  `qa_gate.py` — all faster than any agent and don't drift).
- The task is **trivial** (single palette pick, single variant choice).
  Overhead of spawning > value.
- The subagent needs to know **what the main agent is doing mid-task**.
  Spawn overhead and context transfer cost > benefit.

## Instruction-drift prevention

A common failure mode when using multiple agents: each one's system
prompt/instructions drift from the others, so "good palette" means
different things to different agents. Mitigations, in order:

1. **Never define custom plugin-level agent types for pptx work.** Use
   temporary subagent invocations with explicit prompts instead. The
   skill's authoritative refs (`codex_guardrails.md`,
   `design_philosophy.md`, `outline_schema.md`) are the only source of
   truth; every subagent prompt should cite them.
2. **Always pass the relevant ref file paths** to the subagent's prompt
   so it reads from the same canonical docs, not its own priors.
3. **Use the `Explore` subagent type for read/analysis tasks.** It's
   lighter than general-purpose and won't try to edit files.
4. **Don't chain subagents N deep.** Main → subagent → subagent quickly
   loses instruction fidelity. Keep it two-deep max.

## High-value patterns (use these)

### 0. Recommended sequence for complex decks

Use the smallest useful set of subagents, in this order:

1. Deck start packet when the deck needs reproducible setup. Run
   `scripts/emit_deck_start_packet.py`, read `agent_kickoff_brief`, ask or
   auto-resolve the compact question card, and follow its command ladder before
   spawning scouts.
2. Main-agent user intake when only personalization is underspecified. Run
   `scripts/emit_deck_intake_prompt.py` and record answers or assumptions in
   `design_brief.user_intake`; do not spawn a subagent to interview the user.
3. Content research scout when claims are public/researched and still generic.
4. Data/evidence analysis scout when local data, run tables, figures, or chart
   candidates carry the proof burden.
5. Style/content routing scout after evidence shape and user taste are clearer.
6. Outline critique after the main agent drafts `outline.json`.
7. Rendered visual QA after deterministic QA and slide rendering.

The main agent remains the integrator. Subagents return punch lists or JSON
constraint layers; they do not own final deck source edits.

### 1. Visual QA after render

Fresh eyes on rendered JPGs. Automated `qa_gate.py` misses
composition-level issues (ambiguous hierarchy, wrapped-title decorations,
cramped typography).

**Operational**: `render_slides.py --emit-visual-prompt` prints a
ready-to-paste prompt with numbered JPG paths. Spawn an `Explore`
subagent with that prompt. Details in `references/visual_qa_prompt.md`.

### 2. Parallel slide-XML editing (template adaptation)

When adapting a branded template with many content slides, the per-slide
XML edits are independent. Spawn N parallel subagents, one per slide XML
file, with identical prompts pointing at the template analysis and the
new content. Each edits `ppt/slides/slideN.xml` and nothing else.

**When it pays off**: ≥5 slides need text substitution. Below that, the
main agent's single pass is faster than N spawns.

**Prompt pattern**:
```
You are editing one slide of an unpacked PPTX template.

File: /path/to/unpacked/ppt/slides/slide{N}.xml
Original content: <excerpt from markitdown>
New content:
  Title: "..."
  Body: [...]

Rules (from references/editing.md):
- Bold every title and section header (<a:rPr b="1">)
- Never insert unicode bullets; use layout-inherited or <a:buChar>
- Preserve xml:space="preserve" on existing runs
- One <a:p> per list item, do not concatenate
- If the template has more placeholders than your content items,
  delete the entire shape group, not just the text

Edit only slide{N}.xml. Report what you changed.
```

### 3. Outline critique before build

Dedicated agent reads `outline.json` + `references/design_philosophy.md`
and flags editorial issues: monotony (same variant 3 in a row), no
visual elements on content slides, weak or generic palette choice,
text-heavy slides that would fit kpi-hero or comparison-2col. Catches
things the main agent glosses over because it's focused on content.

**Operational**: `scripts/emit_outline_critique.py --outline
outline.json` emits a ready-to-paste prompt. Run before `build_deck.py`.

### 4. Style/content routing scout

Use one deck-level scout before finalizing `outline.json` when the deck is
non-trivial, researched, scientific/lab-heavy, source-backed, or visually
ambiguous. This is the right way to avoid brittle keyword routing such as
"ASCO/TB/LAMP means lab-report" while still catching real lab decks.

**Operational**:
```
python3 scripts/emit_style_content_router.py \
  --workspace decks/my-deck \
  --user-prompt "original user request"
```

Paste the emitted prompt into an `Explore` subagent. The subagent returns JSON
that constrains `design_dna`, `style_preset`, `deck_style`, allowed variants,
`design_modulation`, slide routes, asset requests, subagent plan, and QA
sensitivities. The main agent remains responsible for applying those choices
to the source files.

Use this once per deck, not once per slide. The scout should classify evidence
objects, audience posture, proof burden, density, and asset availability. Terms
such as ASCO, TB, LAMP, clinical, LOD, sequencing, assay, sample, and
resistance are priors only; they do not override the actual evidence shape.

### 5. Content research scout

Use when a researched/public deck has hedged or generic claims. This scout
finds missing concrete anchors and source types; it does not rewrite the deck.

**Operational**:
```
python3 scripts/emit_content_research.py --outline decks/my-deck/outline.json
```

The output should become updates to `content_plan.json`, `evidence_plan.json`,
and selected slide text after the main agent verifies the facts.

### 6. Data/evidence analysis scout

Use when local files, result tables, lab data, chart candidates, or generated
figures carry the proof burden. This scout classifies available files,
recommends analyses, and returns provenance-aware chart/table/evidence updates.
When `assets/artifacts_manifest.json` exists, the emitted prompt includes
manifest aliases, selection templates, and binder commands. The scout should
return `artifact_selection_recommendations.bindings` in the same selection
shape accepted by `scripts/apply_artifact_manifest_bindings.py --selection`,
plus `script_edit_plan`, `outline_binding_plan`, `qa_readiness_plan`, and
`main_agent_handoff` blocks so the main agent can apply source edits without
re-deriving artifact names. Save the scout JSON and run
`scripts/apply_data_analysis_handoff.py` to persist deterministic bindings,
evidence updates, and handoff notes before editing analysis scripts by hand.

**Operational**:
```
python3 scripts/emit_data_analysis_prompt.py \
  --workspace decks/my-deck \
  --user-prompt "original user request"
```

If the analysis is repeatable or supports figures, convert it into a
deterministic workspace script such as `assets/make_figures.py` and record the
outputs in `asset_plan.json`. Do not leave important calculations as invisible
subagent prose.

### 7. Template analysis before reuse

When the user hands you a branded `.pptx` to adapt, spawn an `Explore`
subagent to analyze it. Give it the thumbnail grid path and the
`markitdown` text extraction. Ask it to:
- List each layout's purpose (title, section, content, closing, stats,
  quote).
- Identify the placeholder text patterns that'll need replacement
  (`"XXXX"`, `"Click to add"`, `"Lorem"`).
- Note brand colors (hex values visible in palette usage).
- Flag slides that look like they host charts / tables / icon grids vs.
  plain bullets.

The subagent's output drives the "Plan slide mapping" step in
`references/editing.md`'s template-adaptation workflow.

## Anti-patterns (don't do)

### Custom plugin-defined agent types for pptx

Tempting to define a `pptx-outline-author` or `pptx-palette-picker`
plugin-level agent with its own system prompt. Don't. Each such
definition drifts from the others and from this skill's own
conventions. A "pptx-palette-picker" that picks "Cherry Bold" for a
climate deck because its system prompt says "bold colors" violates
`design_philosophy.md`'s "palette should feel designed for THIS topic"
rule. Use temporary invocations tied to the skill's refs instead.

### Subagent for deterministic work

If `preflight.py` can answer the question in <1s, don't ask a subagent.
Examples where the script is better:
- "Is the outline schema valid?" → `preflight.py`
- "Does any slide have overflow?" → `layout_lint.py`
- "What font pairs are loadable?" → read `design_tokens.py`
- "Are planning JSON files valid?" → `validate_planning.py`
- "Did placeholder text remain?" → `qa_gate.py` or deterministic text extraction

### Subagent to pick a variant

Variant selection for a single slide is trivial (the outline schema
covers the whole decision matrix). Spawning an agent per slide adds
seconds per slide with no quality win over the main agent.

Exception: use the deck-level style/content routing scout above when the
question is the whole deck's design DNA and evidence posture, not one slide's
variant.

### Agent-per-slide on tiny decks

Parallel XML editing is for ≥5 slides. On a 3-slide deck, the main
agent's sequential pass finishes before three subagents finish
spawning.

### Letting a subagent define "good design"

A subagent asked "make this slide look better" without explicit
constraints will drift. Always give specific rules (cite
`design_philosophy.md`, specify allowed variants, pass the palette).
Open-ended authorship from a fresh subagent produces generic output
because it has no context for what's right for THIS deck.
