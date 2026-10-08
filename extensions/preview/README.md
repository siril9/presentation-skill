# Slide Review Pilot

Optional local MCP extension for presentation-skill. The GitHub skill and
skills-only plugin still work without this directory or its dependencies.
The model authors content; the existing renderer builds editable PowerPoint.

## Run Locally

From this directory, with Node.js 22+ and the core skill runtime already set up:

```bash
npm ci --ignore-scripts
npm run build
node configure.mjs --root /absolute/path/to/deck-folder
codex plugin marketplace add /absolute/path/to/presentation-skill/extensions/preview
codex plugin add presentation-preview@presentation-preview-local
```

Alternatively, install **presentation-preview** from **Slide Review Pilot** in
the desktop plugin directory. Start a new chat afterward. The generated `.mcp.json` contains
local absolute paths; keep the checkout in place. It is ignored by Git and is
not a portable public submission. Reconfigure and refresh the installed plugin
after moving the checkout or changing the allowed deck folder.

Each deck is a folder containing `outline.json` within the configured root.
The adapter reserves `preview-build` for generated output; it cannot be opened as a source deck.
The adapter never defaults to your home directory. It exposes only that root,
does not upload decks, and does not need an OpenAI API key. The host may send
selected source and QA context to the model as part of the conversation.

For another MCP client, run the same server over stdio:

```bash
node server.mjs --root /absolute/path/to/deck-folder
```

## Workflow

- `presentation_open`: list decks or inspect one, obtaining IDs and revision.
- `presentation_slide`: read selected source and QA; image bytes are app metadata.
- `presentation_update_slide`: bounded source edits with an exact revision precondition.
- `presentation_build`: fixed renderer/finalizer operation, with fresh automated QA.
- `presentation_audition`: optional two/three-style comparison on identical content.
- `presentation_preview`: app-only pixels for current renders.

**Slide Review** opens beside the conversation on compatible hosts. Selecting
a slide shares its ID and source revision with the model. Requesting a revision
sends your explicit request; it does not silently modify source. Unsupported
extension capabilities fall back to standard MCP App methods when available.
The tool workflow also works without an interactive panel.

Source edits invalidate old previews. Automated checks are not independent
visual approval. Inspect the exact rebuilt deck before delivery, using the
normal skill workflow. The adapter does not create approval receipts.

The edit tool supports existing title, subtitle, string body, and role-layout
variant fields. It does not rewrite table data or evidence. Broader changes
remain model-led edits through the ordinary skill workflow. Selecting a style
fills a revision request; sending that request is an explicit user action,
not an automatic source change.

## Boundaries

This is a local stdio pilot, not a public hosted service. It has no arbitrary
command endpoint, cloud storage, accounts, telemetry, or lifecycle hooks.
Source and report strings are untrusted content, not executable instructions.
Paths, symlinks, assets, revision preconditions, and resource limits are checked
before operations. Do not expose a folder writable by hostile processes;
process-local locks are not a filesystem sandbox against concurrent attackers.

Public ChatGPT deployment is a separate step requiring a stable HTTPS MCP
endpoint, per-user isolation, authentication where needed, privacy/retention
decisions, and OpenAI review. File-type handlers and direct binary PPTX editing
are deliberately deferred: this pilot preserves source-first semantics.

## Verify

```bash
npm test
npm run build
```

Tests belong to development, not normal deck generation. Protocol and browser
test evidence is not proof of installation or compatibility with every live host.

The [eight-slide stdio run](evidence/e2e-report.json) exercises source revisions,
fresh QA, and repeatable three-style previews. The [browser run](evidence/browser-report.json)
uses the MCP AppBridge with real tools at desktop and mobile sizes. It is not
a screenshot or compatibility claim from the live Codex host.

Implementation references: [OpenAI Plugin Extensions](https://developers.openai.com/plugins/build/extensions),
[extension SDK](https://github.com/openai/mcp-extensions/blob/main/typescript/README.md),
and [deployment requirements](https://developers.openai.com/plugins/build/mcp-server#deploy-the-endpoint).
