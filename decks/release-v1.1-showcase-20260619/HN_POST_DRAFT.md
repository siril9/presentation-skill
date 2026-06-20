# HN Post Draft

Title options:

- Show HN: Source-first PowerPoint deck generation for coding agents
- Show HN: A reproducible slide-deck skill with taste constraints and QA
- Show HN: Claude-Code-like workflow for generating PowerPoint decks

Draft first comment:

I have been working on a Codex skill for generating editable PowerPoint decks with a workflow closer to coding agents than one-shot slide generation.

The idea is to treat a deck like a small software artifact: source files, a design brief, content and evidence plans, deterministic build commands, rendered previews, and QA checks for overflow, overlap, placeholders, layout density, and visual issues.

I also tried to encode taste in a practical way: not just prettier templates, but constraints around slide structure, readable text, evidence-first layouts, source footers, figures/tables, and avoiding awkward whitespace.

For this v0.1 release-line candidate I generated the same synthetic topics three ways: the bundled native presentation path, the older GitHub v1 skill, and the updated skill. Then I built a gallery deck comparing actual rendered slides across multiple styles.

I would be interested in feedback on whether this source-first / coding-agent-like workflow is a useful direction for AI-generated slide decks.

Notes before posting:

- Rewrite this in your own voice before posting.
- Link the GitHub repo and the rendered gallery images.
- Say clearly that the release showcase data is synthetic.
