# Slide Review local readiness, 2026-10-08

Local pilot GO for the tested protocol and browser paths. This is not a hosted
deployment or verification of the live Codex side panel.

Source SHA-256:

- `backend.mjs`: `e8269cd36ece999a2048e8076361154fb87c734da84a8f9dee0fe84e84c98422`
- `app.mjs`: `5ea35d236174a1825c5582d1f7fdafdb07c2b6582c787cf0cb3c53a227b96e8f`
- Core renderer: `0ba4d04d00ba70c6fca5ce11ba32e305a213f950f6d35fb5cb759f8fdc410d65`
- Role catalog: `32a9edd78589c172920faa98470046cae68093f75456c241f551e2c55f6d7c72`

Commands run from `extensions/preview` against a disposable copy of the public
eight-slide synthetic calibration study, never a private or original deck:

- `npm test`: 31/31 passed, including CAS, stale previews, generated-deck
  exclusion, path/symlink containment, command restrictions and MCP contracts.
- `npm run build`: passed.
- `node tests/e2e.mjs --root <temporary-root> --deck calibration --outdir <results>`:
  two automated-pass builds; other slides unchanged; stale edit rejected;
  previews invalidated after source edits; all eight slides selectable;
  three style auditions pass and repeat identical pixels.
  [Exact operation report](e2e-report.json).
- `node tests/browser.mjs --root <temporary-root> --deck calibration --outdir <results> --playwright <module> --browser-executable <executable>`:
  real MCP AppBridge tools at 1280x900 and 390x844, plus limited capabilities.
  No page errors or horizontal overflow. Selection/request races are covered.
  [Browser report](browser-report.json).

An earlier audition exposed insufficient table space in the core renderer; it
was fixed through measured column/row allocation and footer-aware geometry.
No QA threshold was waived. Automated passes remain distinct from visual
approval: the extension does not issue approval receipts.

The generated `plugin/.mcp.json` is Git-ignored and pins local Node, server,
skill-root and deck-root paths. Reconfigure and refresh after moving them.
Core installation has no extension SDK dependency. Host-specific paths are
omitted from this public record; no private deck content is included.
