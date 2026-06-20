# Reference Script Patterns

Patterns distilled from one-off PPTX, DOCX, and figure-generation scripts that
produced stronger decks than generic slide builders. Treat these as product
requirements for the skill, not as code to copy directly.

## Main Finding

The strongest scripts did not win because they had more decorative layouts.
They won because they modeled the work as a report artifact:

- tokenized design constants before any slide logic
- content stored separately from rendering logic
- evidence objects placed first, with text explaining the evidence
- tables and figures styled semantically, not cosmetically
- repeatable figure generation before deck assembly
- visual QA and geometry checks after rendering

For scientific and lab decks, this means the picker should route by evidence
type and presentation posture, not by a static keyword list.

## Portable PPTX Patterns

### Tokenized Design DNA

Reference scripts define slide size, margins, palette, typography, source-line
treatment, and footer position once, then derive each layout from those tokens.
This keeps alignment disciplined and makes topic-specific visual language
portable.

Port into the skill as:

- stronger `design_brief.json` defaults for design DNA
- preset treatments that constrain headers, footers, title layouts, and card
  policy
- renderer helpers that use named safe areas instead of ad hoc coordinates

### Content/Render Separation

The better JS decks keep thesis, metadata, and slide arrays outside the
renderer. The renderer is a deterministic layout engine; content files carry
the story.

The skill already has this shape through `content_plan.json`, `evidence_plan.json`,
`asset_plan.json`, and `outline.json`. Preserve that separation. Do not regress
to inline deck-building scripts for normal deck generation.

### Evidence-First Lab Composition

Lab decks repeatedly use:

- one large plot/image panel plus a compact interpretation sidebar
- figure grid plus adjacent metric/codon/result table
- full-width bottom interpretation strip
- concise run metadata in subtitles or captions
- semantic red/green/blue/orange states for genotype, resistance, pass/fail,
  concordance, or caveat status

This maps directly to `scientific-figure`, `image-sidebar`,
`lab-run-results`, `table`, and `comparison-2col`. Generic cards should be a
fallback only when the content is truly conceptual or modular.

### Evidence Motif Continuity

Strong lab decks often introduce a small evidence system on the cover: labels
such as Evidence, Readout, Next run; assay stages; or validation checkpoints.
Those labels must not be one-off decoration. If a title slide shows evidence
chips, carry the same system forward as:

- subtitle eyebrows (`EVIDENCE | LOD and concordance`)
- sidebar section labels (`READOUT`, `CAVEAT`, `NEXT RUN`)
- table group titles (`READOUT: Run summary`)
- footer/source prefixes on evidence-bearing slides
- section strips when the deck changes from evidence to action

Encode this in `design_brief.json` as `evidence_continuity` before writing
`outline.json`. Do not create a motif on slide 1 unless the outline has a
clear plan for where it appears again.

### Rich Text Segments

Scientific bullets often need mixed styling inside one line: bold analyte names,
italic gene names, colored result states, units, symbols, and caveats. The
one-off scripts solved this with helper functions that add runs from segment
tuples.

Renderer implication: keep rich text support in helpers and table cells. Do not
force scientific bullets into plain strings when semantic emphasis matters.

### Semantic Tables

The best tables use editable PowerPoint tables, not screenshots, with:

- dark header cells
- alternating row fills
- compact margins
- centered metric values and left-aligned labels
- cell-level highlight styles for calls, mutation rows, borderline states,
  discordance, and footnotes

This validates the existing `cell_styles` field and argues for expanding
documented table presets around lab semantics.

### Data-Derived Figure Manifests

The strongest scientific decks generate figures first from local data scripts,
then insert stable output filenames into the deck. Those figure scripts encode
data inputs, output names, labels, color choices, and annotation logic.

Add or emulate a figure manifest when data provenance matters:

```json
{
  "figures": [
    {
      "id": "fig_assay_kinetics",
      "script": "scripts/make_figures.py",
      "inputs": ["data/run_summary.csv"],
      "outputs": ["assets/fig_assay_kinetics.png"],
      "caption": "Resistance call kinetics by sequencing time",
      "rerun_command": "python3 scripts/make_figures.py"
    }
  ]
}
```

This belongs beside `asset_plan.json`, not buried in speaker notes.

### Slide-Ready Figure Export Contract

Most "tiny image with lots of white space" failures are caused before PPTX
rendering. A renderer can contain-fit an image, but it cannot know which
interior whitespace in a chart is meaningful. When a Python script generates
figures, make it export slide-ready assets:

- choose the plot aspect ratio for the target layout, not for a paper page
- keep legends inside the axes only when they do not shrink the plotted region
- use `bbox_inches="tight"` and small `pad_inches` for Matplotlib exports
- run `scripts/trim_image_whitespace.py` on generated PNG/JPG files when the
  plot still carries exterior borders
- export one dominant plot for `image-sidebar` when a three-panel
  `scientific-figure` grid would make labels or curves unreadable
- store output paths, target variants, target box sizes, and crop rules in
  `design_brief.json` under `figure_export_contract`

Example Matplotlib helper for workspace scripts:

```python
def save_slide_figure(fig, path, *, dpi=180):
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.04, facecolor="white")
    plt.close(fig)
```

Then trim if needed:

```bash
python3 scripts/trim_image_whitespace.py \
  decks/my-deck/assets/figures/*.png \
  --in-place --padding 10 --tolerance 12
```

Use Python for deterministic data analysis, inspection, QA, and safe deck
surgery. Do not write a one-off inline
`python-pptx` deck builder for normal generation; it bypasses the layout
measurement and QA pipeline. The efficient pattern is Python for deterministic
data analysis and figure preparation, then `outline.json` plus the fast
`pptxgenjs` renderer for normal editable PowerPoint assembly. Use the Python
renderer only for legacy or renderer-specific behavior the fast path does not
cover.

### Editable Workflow Strips

The strongest process slides use native editable shapes: equal-width rounded
boxes, explicit gap constants, arrow connectors, grouped-stage brackets,
short detail labels, and a final turnaround/result callout.

This should be treated as an enhanced `flow` mode or future `workflow-strip`
variant. Mermaid is useful for quick diagrams, but editable method workflows
are better for lab decks and handoff decks.

### Safe Incremental Deck Surgery

When editing existing decks, the useful pattern is:

- copy or back up before mutation
- find slides by known text
- remove only selected shapes
- preserve existing image boxes when swapping figures
- reinsert assets at the same geometry
- renumber after slide insertion/reordering
- inspect shape positions before edits

This belongs in editing tooling and references. It should not replace the
workspace rebuild flow when source files are available.

### Deck Inspection Dump

A small inspection script that prints slide size, layout name, shape type,
position, text, and table contents is disproportionately useful before editing
an existing deck. It turns visual guesswork into measurable geometry.

The skill should keep an inspection path available for template adaptation and
incremental edits.

## Portable DOCX Patterns

DOCX scripts showed the same pattern as good decks: define styles once, then
compose structured content. Reusable ideas:

- markdown-ish rich text parsing for `**bold**` spans
- centered title/subtitle handling
- section heading helpers with bottom borders
- bullet style normalization with hanging indents
- compact key-value tables
- highlighted "needs input" fields for forms
- metadata cleanup before delivery
- LibreOffice PDF export for layout inspection

If the presentation skill later adds speaker handouts or companion reports,
reuse these document primitives rather than generating raw paragraphs.

## Dynamic Style/Content Routing

Do not implement lab routing as only:

```text
if prompt contains ASCO/TB/LAMP/clinical/LOD/sequencing/assay/sample/resistance:
    use lab-report
```

Those terms are useful priors, but static token matching fails in both
directions. A public health explainer can mention TB and still need an editorial
policy deck. A lab deck can omit those exact tokens and still require figures,
tables, captions, and source lines.

Use a deck-level style/content scout when the task is non-trivial, researched,
scientific, or asset-heavy. The scout should classify:

- user objective: talk, report, leave-behind, pitch, poster, lab update
- audience posture: scientific peer, clinician, executive, public, student
- evidence objects: plots, microscopy/images, assay readouts, result tables,
  raw data, workflow, screenshots, citations, metrics
- proof burden: exploratory concept, sourced report, clinical/lab claim,
  regulatory or validation claim
- asset availability: local figures, generated figures, source-backed images,
  tables, charts, no assets yet
- density: live talk, readable report, dense leave-behind
- bounded design modulation: subtle/moderate/bold shift, accent role,
  whitespace, density, motif, container policy, and figure/table treatment

Then choose:

- `style_preset`
- `deck_style` treatments such as `header_mode`, `footer_mode`, and
  `research_visual_mode`
- `design_modulation` so agents can make suitable micro-design changes without
  inventing unsupported inline colors or fonts
- allowed and forbidden variants
- slide-level routes from role/evidence to variant
- asset requests and figure/table provenance needs
- QA sensitivities
  and whether content research or data/evidence analysis subagents are needed

For lab/report evidence, the expected route is usually:

- preset: `lab-report` or another restrained report preset
- style: `header_mode: lab-clean`, `footer_mode: source-line`,
  `summary_callout_mode: lab-box`, `research_visual_mode: true`
- variants: `scientific-figure`, `image-sidebar`, `lab-run-results`, `table`,
  `comparison-2col`, and carefully scoped `flow`
- avoid: generic `cards-3`, decorative icon grids, forced KPI hero slides, and
  process diagrams that do not carry evidence

For brand/product/editorial decks, use the same scout but pick a different
design DNA. The scout is not a lab-only feature; it prevents all deck types from
collapsing into generic cards.

## Recommended Implementation Order

1. Keep the pattern report and scout prompt in the repo so agents have a shared
   method to follow.
2. Add a prompt emitter for one deck-level style/content scout before outline
   finalization.
3. Add planning validation that warns when lab DNA uses mostly generic cards or
   when product/editorial DNA forces lab/report layouts without evidence.
4. Keep hardening the figure-manifest convention for data-derived scientific
   figures; `scripts/scaffold_figure_artifacts.py` now creates the first
   deterministic `assets/make_figures.py`, chart JSON, slide-ready figure, and
   artifact-plan draft from simple tabular data.
5. Add or harden editable workflow-strip rendering.
6. Add an inspection command for existing PPTX geometry and tables.
7. Expand regression fixtures around `scientific-figure`, `image-sidebar`,
   `lab-run-results`, and semantic table cell styles.
