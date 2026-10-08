# Discovery and Adoption

`presentation-skill` 0.14.0 is an MIT-licensed, source-first PowerPoint skill
for coding agents with local tool access. Write `outline.json`, build an
editable `.pptx`, check retained source content and layout, then inspect the
actual rendered slides.

## Why Use It

- Source JSON, local data, and figure scripts remain rebuildable; repair source
  rather than patching a generated deck when its source exists.
- Native PowerPoint text, charts, and tables stay editable where supported.
  Native ordered methods carry 2-4 editable stages with titles/details.
  Scientific figures offer `panel-grid`, `primary-rail`, `ledger-rail`, and
  `strip-readout` layouts with `open`, `ruled`, or `panel` frames; sidebars
  measure the declared interpretation at readable type. Imported images and
  rendered figures are not editable data objects.
- Content-led layouts vary with the argument, not just the palette. Scientific,
  lab, clinical, board, investor, editorial, and operational decks share a
  deterministic renderer without a mandatory slide sequence.
- Normal QA checks geometry, readability, placeholders, accessibility, and
  mapped visible source fields, including captions, caveats, units, and native
  chart values. Source retention is not factual verification or exhaustive
  coverage of every field; actual rendered review remains necessary.
- One capable model, including GPT-6.1, can use a compact brief, source authoring,
  and finalization. Fast briefs expose actual evidence fallback variants;
  those routes do not claim v2 slot execution.
  Questions, style auditions, and saved workspaces are optional. Focused repair
  packets and verified render caching reduce repeated work without reusing
  stale visual approval. Exact PPTX/render hashes can bind a human/model review.

## Install

For a coding agent supported by the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add https://github.com/siril9/presentation-skill \
  --skill presentation-skill
```

Installer support is not a claim that this skill has been tested in every agent.
For the pinned Codex plugin release:

```bash
codex plugin marketplace add siril9/presentation-skill --ref v0.14.0
```

Then open `/plugins` in Codex and install `presentation-skill` from the
repository's **Presentation Skill** marketplace. This is a repository-provided
marketplace, not a claim of official or globally curated marketplace inclusion.
Follow the [README setup instructions](https://github.com/siril9/presentation-skill#install)
for runtime dependencies. Run commands from the installed skill directory.
Ordinary chat without local execution tools cannot run this workflow directly.

## Try It

```text
Use presentation-skill to build a 7-slide editable lab-report PowerPoint from
this CSV. Treat outline.json as source. Retain units, denominators, captions,
and limitations; choose layouts from the evidence, run QA, and inspect the
actual rendered slides before delivery.
```

Read [SKILL.md](SKILL.md) for the compact brief -> source -> finalize route.
Use workspace mode only when the deck needs saved planning or repeated rebuilds.
Generation does not require LibreOffice; full rendered verification requires
the supported LibreOffice/Poppler tools. A deferred render is not approval.

## Release Evidence

Three eight-slide public studies provide 24 actual slides: a white calibration
decision, a dark contrast seminar, and a light sampling report. Source outlines,
seeded data and figure scripts make the examples reproducible.

- [Scientific/report showcase](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_showcase.jpg)
  and [release manifest](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/release_manifest.json).
- Full contact sheets: [white calibration](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/white_calibration_contact_sheet.jpg),
  [dark contrast](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/dark_contrast_contact_sheet.jpg),
  and [light sampling report](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/light_river_report_contact_sheet.jpg).
- [v0.14.0 release](https://github.com/siril9/presentation-skill/releases/tag/v0.14.0)
  and [three decks plus source ZIP](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/presentation-skill-v0.14-lab-studies.zip).
- Individual editable decks: [calibration](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/white_calibration.pptx),
  [contrast](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/dark_contrast.pptx),
  and [sampling](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/light_river_report.pptx).

Only invented synthetic nonclinical data are used. The studies are not real-world
findings, model-quality benchmarks, or evidence of superiority over another
generator. History: [previous proof and downloads](https://github.com/siril9/presentation-skill/releases/tag/v0.13.1).

The optional [Slide Review extension](extensions/preview/README.md) is a local
pilot. Core use does not require it; no globally hosted or curated listing is claimed.

## Agent and Directory Routing

Trigger requests include PowerPoint, PPTX, slide deck, presentation, deck
redesign, scientific figures, CSV/Excel-to-slides, and layout/readability QA.
Search terms: source-first PPTX generator, editable PowerPoint skill, Codex
presentation skill, scientific slide deck, agent presentation QA.

`SKILL.md` frontmatter supplies the skill name and a description with trigger
phrases. Search aliases are separate metadata in
[agents/discovery.json](agents/discovery.json), not an `aliases` frontmatter
field or a guarantee of fuzzy matching. [agents/openai.yaml](agents/openai.yaml)
provides the agent-facing prompt. Skip pure text brainstorming when no deck
artifact is needed.

## Share

General links: [repository](https://github.com/siril9/presentation-skill),
[latest release](https://github.com/siril9/presentation-skill/releases/latest),
[skills.sh listing](https://www.skills.sh/siril9/presentation-skill/presentation-skill).
Use pinned release links only for version-specific installation and evidence.
[Promotion copy](https://github.com/siril9/presentation-skill/blob/main/docs/PROMOTION.md)
is short and ready to adapt. Useful feedback includes the prompt, source,
affected slide, and rendered image for a concrete content or design miss.
For the official public plugin submission route, see the
[publication guide](https://github.com/siril9/presentation-skill/blob/main/docs/PLUGIN_PUBLICATION.md).
Submission is not a claim of acceptance or marketplace curation.
