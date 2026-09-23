# Model-Adaptive Workflow

Use this reference when choosing how much planning, delegation, and QA a deck
needs. The renderer and source contracts stay the same across model variants;
only the amount of model-side orchestration changes.

A single capable model can own the full deck. Advisor calls are optional and
should answer a concrete unresolved question, not duplicate authoring or create
a mandatory planning phase. Model selection belongs to the caller's harness;
this skill does not require Astra, Sol, or any particular model pairing.

## Core rule

Keep the active prompt small. Store reproducibility detail in workspace files
and reports, then expose only the decisions needed for the current phase.

- Start from `agent_brief.md` or `agent_brief.json`.
- Read `deck_start_packet.json` only for recovery, audit, or a missing command.
- Load one style reference, schema section, or QA report at a time.
- Do not paste the corpus, full preset catalog, or full replay ledger into a
  model prompt.
- Preserve required facts, decisions, caveats, and next actions. Remove
  repeated process language before removing required content.

This follows [OpenAI's Astra skill guidance](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra):
precise discovery, progressive disclosure, and clear completion boundaries,
without turning expert judgment into a rigid itinerary. Profile aliases below
are local workflow policies, not claims about internal model architecture or
an automatic model change. A future model can use any explicit policy.

## Execution profiles

### Quality-first

Aliases include `frontier`, `sol`, `astra`, `gpt-5.6-sol`, `gpt-6-astra`, `pro`.

Use for high-stakes scientific, clinical, board, investor, regulatory, or
public-release decks; difficult source synthesis; or decks with complex data
artifacts.

- Main agent owns the deck and source edits.
- One design/content scout may return bounded decisions.
- One data scout may be used when local data or computed evidence is material.
- Run rendered visual review and inspect slide images at original detail.
- Iterate until source, rendering, readability, and delivery gates pass.

### Balanced

Aliases: `terra`, `standard`.

Use for most professional decks.

- Main agent selects the style route and authors source files.
- Use at most one scout when style, evidence, or asset selection is genuinely
  ambiguous.
- Run deterministic QA plus rendered visual review.
- Prefer one focused repair loop over repeated planning passes.

### Fast

Aliases: `luna`, `draft`.

Use for short drafts, internal working decks, and high-volume generation.

- Use deterministic routing and existing renderer recipes.
- Use a single agent; the brief includes small valid examples for its chosen roles.
- Author once, finalize, and repair from affected-slide feedback when necessary.
- The same model may use a richer workflow when needed. Do not switch providers
  or models without the caller choosing to do so; finished decks still pass all gates.

### Auto

`auto` chooses `quality-first` for high-stakes or evidence-heavy requests,
`fast` for explicit rough/quick drafts, and `balanced` otherwise. The user or
calling harness may always override the profile.

## Phase-sized context

### Plan

Give the model:

- the user request;
- the compact question answers or assumptions;
- one primary style route and at most two secondary influences;
- the evidence/asset burden;
- the required output paths and completion gates.

Do not give it every corpus record, every preset, or the full QA manual.

### Author

Give the model:

- current `outline.json` and the relevant planning-file summaries;
- selected renderer treatments and supported variants;
- generated artifact aliases, if any;
- readable type and density constraints.

The model should write topic-specific slides directly. It should not copy
replay ledgers, recipe signatures, or command ladders into its answer.

### Repair

Give the model:

- the rendered slide image or contact sheet;
- exact slide IDs and measured warnings;
- the source files and fields to edit.

`repair_packet.json` exposes this context without pasting the entire QA folder.
It retains full issue counts and marks any bounded excerpts. The repair pass
changes source and rebuilds; the final full gate remains authoritative.

## Optional User Input

`present.py intake --prompt "..."` returns at most three questions about missing
consequential context. The agent decides whether asking materially improves the
deck; otherwise it proceeds with explicit assumptions. Answers use inline JSON:
`--answers '{"audience":"Lab directors","purpose":"Choose the next experiment"}'`.
Pass them into `present.py brief` to preserve context without repeating questions.

Only caller-provided `--remaining-percent`, `--current-model`, and
`--available-models` can produce a low-usage choice. At 10% or less remaining,
the packet can offer Luna if the caller confirms it is available; otherwise it
offers the fast workflow on the current model. The default is to stay put.
There is no account lookup, automatic switch, or claim that shared account limits
will improve. The caller applies a change only after the user chooses it.

## Optional Previews And Caching

`present.py audition --outline ... --outdir ... --presets ...` compares up to
three candidate styles using the same title, evidence, and dense data slides.
It is useful for an ambiguous design request, not required for the fast route.
Candidate JSON and images remain inspectable; no automatic aesthetic winner is claimed.

`present.py finalize --render-cache-dir ...` opts into content- and
environment-keyed render reuse. It still runs QA and does not cache visual
approval. Measure cold and warm rendering separately from model authoring;
neither is a claim about total user-request latency.

## Stable backbone

All profiles preserve the same backbone:

1. Source files and data/figure scripts are authoritative.
2. The PPTX remains editable.
3. Style routing influences composition, not only palette.
4. Charts, tables, and figures carry source and rebuild metadata.
5. Geometry, visual inspection, placeholder checks, and delivery readiness
   gate final output.

The profile changes model effort and context exposure, not the quality
definition of a finished deck.
