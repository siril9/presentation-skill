# Promotion Kit

Concise drafts for sharing `presentation-skill` 0.13.1. Nothing here is a
posting authorization or a claim of official marketplace curation.

## Links and Install

- Repository: <https://github.com/siril9/presentation-skill>
- General sharing: <https://github.com/siril9/presentation-skill/releases/latest>
- skills.sh listing: <https://www.skills.sh/siril9/presentation-skill/presentation-skill>
- Public plugin submission: [publication guide](https://github.com/siril9/presentation-skill/blob/main/docs/PLUGIN_PUBLICATION.md).
- Current distribution: <https://github.com/siril9/presentation-skill/releases/tag/v0.13.1>
- Original design-study evidence: <https://github.com/siril9/presentation-skill/releases/tag/v0.13.0>
- Six-slide showcase: [image](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_showcase.jpg)
  and [manifest](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_showcase_manifest.json).
- Full contact sheets: [lab](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_lab_contact_sheet.jpg),
  [editorial](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_editorial_contact_sheet.jpg),
  [operations](https://github.com/siril9/presentation-skill/blob/main/examples/v0.13_operations_contact_sheet.jpg).
- Original editable decks and source: [v0.13 design-studies ZIP](https://github.com/siril9/presentation-skill/releases/download/v0.13.0/presentation-skill-v0.13-design-studies.zip).

0.13.1 updates distribution and the showcase; `v0.13` image filenames and the
original 0.13.0 design-study ZIP remain unchanged.

For coding agents supported by the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add https://github.com/siril9/presentation-skill \
  --skill presentation-skill
```

For the pinned Codex plugin:

```bash
codex plugin marketplace add siril9/presentation-skill --ref v0.13.1
```

Then install `presentation-skill` from **Presentation Skill** in `/plugins`.
See the [README](https://github.com/siril9/presentation-skill#install) for local
runtime setup. Installer support does not mean every supported agent has been
tested; ordinary chat without execution tools cannot run the workflow directly.

## Hacker News

Title: `Show HN: Editable PowerPoint decks that rebuild from source`

```text
I built presentation-skill, an MIT-licensed skill for coding agents that makes
editable PowerPoint decks from structured source. Change outline.json and
rebuild, rather than starting over or hand-patching generated slides.

The layouts follow the argument: a lab report can lead with a native chart and
limitations, an editorial story with a timeline, an operations memo with a
decision matrix, or a KPI readout when one number carries the story.
Style families give them a coherent visual language without
forcing the same card grid onto every slide. Text, charts and tables remain
editable in PowerPoint, with source and rendered checks before delivery.

One capable model can use this single skill to author and refine a deck; no
required multi-agent setup. The examples are synthetic design studies, not
benchmarks. I'd value real workflows and design misses: a layout that repeats,
a chart that is hard to read, or a deck that does not fit its audience.

https://github.com/siril9/presentation-skill
https://github.com/siril9/presentation-skill/releases/latest
```

## Developer Community

```text
presentation-skill is an open-source PowerPoint skill for coding agents:
compact brief -> structured source -> editable deck. Content-led layouts and
style families support lab reports, editorial stories and operations decisions
without a fixed slide sequence. Native text, charts and tables stay editable.
One capable model can author and refine the deck; questions, style previews and
saved planning are optional. Source checks and actual rendered review remain
part of delivery.

Install through skills.sh for its supported agents, or use the repository's
Codex plugin marketplace. The v0.13 examples are synthetic design studies,
not evidence that one model or generator outperforms another.

Feedback requested: real presentation workflows and design misses. Include the
prompt and a slide image showing what did not fit the audience or evidence.
https://github.com/siril9/presentation-skill/releases/latest
```

## Directory Description

MIT-licensed skill for source-first, editable PowerPoint generation. Coding
agents with local tool access author structured JSON, choose content-led
layouts, build native text, charts and tables, and check mapped source retention,
layout and readability. Actual rendered review remains required. Supports lean
one-off authoring and rebuildable workspaces; no required multi-agent or
model-specific workflow.

## Before Sharing

Confirm the linked showcase, manifest and release ZIP are published. Describe
the current examples as synthetic design studies, not benchmarks. Any
[v0.7.0 Codex-native comparison](https://github.com/siril9/presentation-skill/releases/tag/v0.7.0)
is historical, not current superiority evidence. Do not claim all-agent testing
or official/global marketplace inclusion. Use `/releases/latest` for general
sharing, and pinned links for commands and version-specific evidence.
For the official public submission route, follow the
[publication guide](https://github.com/siril9/presentation-skill/blob/main/docs/PLUGIN_PUBLICATION.md);
submission is not acceptance or curation.
