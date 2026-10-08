# Promotion Kit

Sharing copy for `presentation-skill` 0.14.0.
Nothing here authorizes posting or claims official marketplace curation.

## Links and Install

- Repository: <https://github.com/siril9/presentation-skill>
- General sharing: <https://github.com/siril9/presentation-skill/releases/latest>
- skills.sh listing: <https://www.skills.sh/siril9/presentation-skill/presentation-skill>
- Public plugin submission: [publication guide](https://github.com/siril9/presentation-skill/blob/main/docs/PLUGIN_PUBLICATION.md).
- Release: <https://github.com/siril9/presentation-skill/releases/tag/v0.14.0>
- Scientific/report showcase: [image](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_showcase.jpg)
  and [release manifest](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/release_manifest.json).
- Eight-slide contact sheets: [white calibration](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/white_calibration_contact_sheet.jpg),
  [dark contrast](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/dark_contrast_contact_sheet.jpg),
  [light sampling report](https://github.com/siril9/presentation-skill/blob/main/examples/v0.14_lab_studies/light_river_report_contact_sheet.jpg).
- Decks and source: [v0.14 lab-studies ZIP](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/presentation-skill-v0.14-lab-studies.zip).
- Individual PowerPoints: [calibration](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/white_calibration.pptx),
  [contrast](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/dark_contrast.pptx),
  [sampling](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/light_river_report.pptx).
- History: [previous proof and downloads](https://github.com/siril9/presentation-skill/releases/tag/v0.13.1).

The three studies contain 24 actual slides with invented synthetic nonclinical
data only. They are not empirical findings or a model/generator benchmark.

For coding agents supported by the [skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add https://github.com/siril9/presentation-skill \
  --skill presentation-skill
```

Add the pinned Codex marketplace:

```bash
codex plugin marketplace add siril9/presentation-skill --ref v0.14.0
```

Then install `presentation-skill` from **Presentation Skill** in `/plugins`.
See the [README](https://github.com/siril9/presentation-skill#install) for local
runtime setup. Installer support does not mean every supported agent has been
tested; ordinary chat without execution tools cannot run the workflow directly.

## Developer Community

```text
presentation-skill is an open-source PowerPoint skill for coding agents:
compact brief -> structured source -> editable deck. Content-led layouts and
style families support lab reports, editorial stories and operations decisions
without a fixed slide sequence. Native text, charts and tables stay editable.
One capable model, including GPT-6.1, can author and refine the deck. Questions,
style previews and saved planning are optional. Source checks and actual
rendered review remain part of delivery.

Install through skills.sh for its supported agents, or use the repository's
Codex plugin marketplace. The v0.14 examples are synthetic nonclinical
studies, not evidence that one model or generator outperforms another.

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

0.14 adds native 2-4-stage method titles/details, four readable scientific-figure
layouts with open/ruled/panel frames, and measured interpretation sidebars.
Fast briefs expose supported evidence fallbacks without pretending they execute
v2 slots. Mapped semantic content-retention checks are not factual verification.

## Sharing Boundaries

Describe the examples as synthetic studies, not validated
findings or superiority evidence. Do not claim all-agent testing
or official/global marketplace inclusion. Use `/releases/latest` for general
sharing, and pinned links for commands and version-specific evidence.
For the official public submission route, follow the
[publication guide](https://github.com/siril9/presentation-skill/blob/main/docs/PLUGIN_PUBLICATION.md);
submission is not acceptance or curation.

The optional [Slide Review extension](../extensions/preview/README.md) is a local
pilot, not a globally hosted service or curated marketplace listing. Core use
does not require it.
