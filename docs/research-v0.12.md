# v0.12 prior-art research

Read-only inspection on 2026-09-22. Revisions below were resolved from public
repository HEADs; findings use actual source/docs, not search snippets.
No upstream code, prompts, slide assets, or templates were imported. This is
engineering evidence, not a runtime benchmark or legal clearance for reuse.

## Repositories and licensing

1. **anthropics/skills** -- `34040c9c568585f6929bedeaad110ad08f079624`
   - Repo: https://github.com/anthropics/skills
   - Read: https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/pptx/SKILL.md
   - License: https://github.com/anthropics/skills/blob/34040c9c568585f6929bedeaad110ad08f079624/skills/pptx/LICENSE.txt
   - PPTX skill is restrictive/source-available, NOT Apache-2.0. Exclude its materials from reuse. Observed font-substitution cautions and template-relative QA; do not adopt stylistic bans as universal design rules.

2. **openai/skills** -- `49f948faa9258a0c61caceaf225e179651397431`
   - Repo: https://github.com/openai/skills
   - Read: https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.system/skill-creator/SKILL.md
   - License: https://github.com/openai/skills/blob/49f948faa9258a0c61caceaf225e179651397431/skills/.system/skill-creator/LICENSE.txt
   - Apache-2.0 for this skill, not a blanket repo license. Progressive disclosure, executable helpers, and bounded freedom support compact task context. README marks the repository deprecated in favor of openai/plugins.

3. **openai/plugins** -- `1dc195897af4161d039b80d8471ec0a10c9bbc89`
   - Repo: https://github.com/openai/plugins
   - Read: https://github.com/openai/plugins/blob/1dc195897af4161d039b80d8471ec0a10c9bbc89/plugins/google-drive/skills/google-slides/SKILL.md
   - Parser: https://github.com/openai/plugins/blob/1dc195897af4161d039b80d8471ec0a10c9bbc89/plugins/google-drive/skills/google-slides/runtime/design-system.mjs
   - License declaration: https://github.com/openai/plugins/blob/1dc195897af4161d039b80d8471ec0a10c9bbc89/plugins/google-drive/.codex-plugin/plugin.json
   - Google Drive manifest declares MIT; no accompanying root/Google Drive LICENSE file found. Full snapshots stay outside model context; compact catalogs expose inheritance, protected regions, and exemplar roles. Inferred semantics require rendered confirmation.

4. **slidevjs/slidev** -- `30a0a54c8739b4b395d9b336a6304cc8ebcc3947`
   - Repo: https://github.com/slidevjs/slidev
   - Read: https://github.com/slidevjs/slidev/blob/30a0a54c8739b4b395d9b336a6304cc8ebcc3947/docs/guide/exporting.md
   - Source: https://github.com/slidevjs/slidev/blob/30a0a54c8739b4b395d9b336a6304cc8ebcc3947/packages/slidev/node/commands/pptx/normalize.ts
   - License: https://github.com/slidevjs/slidev/blob/30a0a54c8739b4b395d9b336a6304cc8ebcc3947/LICENSE
   - MIT. One theme plus addons separates coherence from extensions. Current source supports pptx-editable with explicit element/slide raster fallback; ordinary PPTX export is image-based. Native-shape conversion is not full semantic editability.

5. **marp-team/marp-cli** -- `ffc4128626cbc64965fe1cc805717c6d4438c384`
   - Repo: https://github.com/marp-team/marp-cli
   - Read: https://github.com/marp-team/marp-cli/blob/ffc4128626cbc64965fe1cc805717c6d4438c384/README.md
   - Source: https://github.com/marp-team/marp-cli/blob/ffc4128626cbc64965fe1cc805717c6d4438c384/src/converter.ts
   - License: https://github.com/marp-team/marp-cli/blob/ffc4128626cbc64965fe1cc805717c6d4438c384/LICENSE
   - MIT. Declarative theme sets and reproducible configuration are useful patterns. Experimental editable PPTX converts PDF through LibreOffice, with documented fidelity loss and no presenter notes.

6. **gitbrent/PptxGenJS** -- `3c9ec1b687c174952166f6a34b5e87ebf69fa469`
   - Repo: https://github.com/gitbrent/PptxGenJS
   - Read: https://github.com/gitbrent/PptxGenJS/blob/3c9ec1b687c174952166f6a34b5e87ebf69fa469/src/pptxgen.ts
   - Tables: https://github.com/gitbrent/PptxGenJS/blob/3c9ec1b687c174952166f6a34b5e87ebf69fa469/src/gen-tables.ts
   - License: https://github.com/gitbrent/PptxGenJS/blob/3c9ec1b687c174952166f6a34b5e87ebf69fa469/LICENSE
   - MIT. Native masters, named placeholders, editable tables, and repeated headers can improve consistency and recipient-side editing. Pagination is heuristic and still needs fit QA.

7. **zarazhangrui/frontend-slides** -- `9906a34d640d2111f724544cbc50f7f130569ae1`
   - Repo: https://github.com/zarazhangrui/frontend-slides
   - Read: https://github.com/zarazhangrui/frontend-slides/blob/9906a34d640d2111f724544cbc50f7f130569ae1/SKILL.md
   - License: https://github.com/zarazhangrui/frontend-slides/blob/9906a34d640d2111f724544cbc50f7f130569ae1/LICENSE
   - MIT. Contrasting visual previews, compact indexes before full specifications, and reading/speaking density distinctions. HTML success is not evidence of editable PPTX success; do not import template assets.

8. **singerla/pptx-automizer** -- `3a08689441ba3d353793bbb2fccd1c37782557dc`
   - Repo: https://github.com/singerla/pptx-automizer
   - Read: https://github.com/singerla/pptx-automizer/blob/3a08689441ba3d353793bbb2fccd1c37782557dc/docs/selectors.md
   - Masters: https://github.com/singerla/pptx-automizer/blob/3a08689441ba3d353793bbb2fccd1c37782557dc/docs/masters-layouts.md
   - License: https://github.com/singerla/pptx-automizer/blob/3a08689441ba3d353793bbb2fccd1c37782557dc/LICENSE
   - MIT. Stable creation IDs and selective native-object reuse support reference editing. Imported layouts containing images/charts have documented limitations.

## Ranked implementation hypotheses

1. Content-matched style auditions: compare title, evidence, and dense-data slides on frozen content, not title treatments or palettes alone.
2. Machine-generated repair packets: expose affected slides, source pointers, measured diagnostics, relevant instructions, and images; preserve full counts and explicit truncation with detail paths. Measure tokens, repair rounds, render calls, and final pass rate.
3. Compile shared styling into native masters: retain slide-local evidence and verify propagation/inheritance in the delivered PPTX.
4. Compare actual emitted editability against Deck IR: record fallbacks and font substitutions; never count source availability as native object editability.
5. Semantic reference-deck catalogs: record role, density, protected regions, stable IDs, and explicit keep/replace/delete media mappings.

Retain the native source-first renderer. Pilot improvements rather than claiming
unmeasured savings or a superior backend. Final QA must remain authoritative;
repair budgets trigger escalation, not acceptance. Repository licenses do not
automatically cover external fonts, imagery, trademarks, or linked templates.

## Development evidence (2026-09-23)

- An eight-slide GPT-6 Luna authoring trial produced valid editable source but
  initially swapped survey and outcome counts and omitted a supplied staffing
  figure. Luna corrected those errors after a source audit and repaired a long
  title. This supports a compact fact checklist, not an unattended-accuracy claim.
- On this machine, the corrected deck's build/render/automated-QA pipeline took
  5.403 seconds cold and 2.408 seconds with a verified render-cache hit. Both runs
  rebuilt the PPTX and reran QA. These are single local observations, excluding
  model authoring, factual audit, and visual inspection; not a model speed ranking.
- The controlled eight-style gallery gained a source-to-PPTX check for visible
  text and native chart data. It exposed missing chart facts and a missing table
  interpretation despite zero geometry warnings. XML presence does not prove
  visibility, so rendered inspection remains required.
