# Discovery and Adoption

`presentation-skill` 0.13.1 is an MIT-licensed, source-first PowerPoint skill
for coding agents with local tool access. Write `outline.json`, build an
editable `.pptx`, check retained source content and layout, then inspect the
actual rendered slides.

## Why Use It

- Source JSON, local data, and figure scripts remain rebuildable; repair source
  rather than patching a generated deck when its source exists.
- Native PowerPoint text, charts, and tables stay editable where supported.
  Imported images and rendered figures are not editable data objects.
- Content-led layouts vary with the argument, not just the palette. Scientific,
  lab, clinical, board, investor, editorial, and operational decks share a
  deterministic renderer without a mandatory slide sequence.
- Normal QA checks geometry, readability, placeholders, accessibility, and
  mapped visible source fields, including captions, caveats, units, and native
  chart values. Source retention is not factual verification or exhaustive
  coverage of every field; actual rendered review remains necessary.
- One capable model can use a compact brief, source authoring, and finalization.
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
codex plugin marketplace add siril9/presentation-skill --ref v0.13.1
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

## Current Evidence

The [0.13.1 distribution/showcase update](https://github.com/siril9/presentation-skill/releases/tag/v0.13.1)
keeps the original `v0.13` proof filenames. The original design-study release
and ZIP below remain pinned to 0.13.0; they are not republished patch artifacts.

- [Six selected actual slides](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_showcase.jpg)
  and their [selection/provenance manifest](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_showcase_manifest.json).
- Full current contact sheets: [lab](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_lab_contact_sheet.jpg),
  [editorial](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_editorial_contact_sheet.jpg),
  and [operations](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_operations_contact_sheet.jpg).
- [Original v0.13.0 design-study evidence](https://github.com/siril9/presentation-skill/releases/tag/v0.13.0)
  and [design-studies ZIP](https://github.com/siril9/presentation-skill/releases/download/v0.13.0/presentation-skill-v0.13-design-studies.zip)
  with that release's editable decks and sources, including a retained example
  rebuilt for 0.13.0.

These are synthetic design studies, not real-world findings, model-quality
benchmarks, or evidence of superiority over another generator. The
[June 2026 Codex-native comparison](https://github.com/siril9/presentation-skill/blob/main/decks/native-vs-latest-random-topics-20260623/readme_images/codex_native_vs_updated_clean_three_topics.png)
belongs to [v0.7.0](https://github.com/siril9/presentation-skill/releases/tag/v0.7.0)
and is explicitly historical, not a comparison of the current release.

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
