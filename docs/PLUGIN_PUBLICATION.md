# Public Plugin Publication

Verified against official OpenAI documentation on 2026-10-08. This repository's
local/repo marketplace is not the public directory. No public approval,
curation, completed portal scans, or verified publishing identity is claimed.

## Package And Listing

The [package guide](https://developers.openai.com/plugins/build/plugins)
supports the existing `.codex-plugin/plugin.json` compatibility layout.
The ZIP has `.codex-plugin/`, `skills/`, and `assets/` at its root, without a
repository wrapper. No duplicate portable manifest is needed.

[Submission requirements](https://developers.openai.com/plugins/deploy/submission):

- Display name and short description: required, single-line, <=30 characters.
- Long description <=4000; developer name <=80; capabilities <=20, each <=120.
- Starter prompts: <=3, each <=128, unique, single-line, without @mentions.
- Logo and composer icon: `./`-prefixed included files; square, >=48 px,
  <=5 MiB. PNG/JPEG/WebP/SVG accepted; raster dimensions <=4096 px.
  SVG needs square numeric dimensions or a square numeric viewBox.
- Skills-only does not require all four MCP listing URLs. Support is provided
  through GitHub issues; no privacy policy or legal acceptance is fabricated.

The [error reference](https://developers.openai.com/plugins/deploy/submission-errors)
specifically prohibits `interface.screenshots`, MCP configuration, and app
configuration in skills-only uploads. It limits ZIPs to 100 MB compressed,
512 MiB extracted, 5000 entries, 100 MiB per file and 20 path segments.
These archive rules are stricter than local-listing screenshot support.

## Export

For 0.14.0, run from repo root with the core and plugin snapshot synchronized:

```bash
python3 scripts/sync_plugin_snapshot.py --check
python3 scripts/validate_distribution.py
python3 scripts/package_plugin.py --output /tmp/presentation-skill-v0.14.0-plugin.zip
```

The packager does not sync. It checks parity, validates listing limits, paths
and the original SVG, and exports the existing skill runtime with fixed ZIP
timestamps/permissions and sorted entries. Only the exported manifest loses
`interface.screenshots`; source listing and local screenshots remain unchanged.
Unreferenced root assets are omitted; curated skill reference images remain.
The 10 MB extracted cap is this project's lean budget, not a portal limit.
Its JSON report includes the ZIP hash and byte counts. These local checks are
not portal safety/security scans or proof of public acceptance.

The [release proof](../examples/v0.14_lab_studies/release_manifest.json)
is separate from this skills-only plugin ZIP. Three synthetic studies, 24 actual
slides, and their deck/source assets do not establish plugin approval
or a model benchmark. One capable model, including GPT-6.1, can use the core;
no model-specific or multi-agent dependency is required.

The optional [Slide Review extension](../extensions/preview/README.md) remains
a local pilot. It is not this skills-only export, a globally hosted service,
or a curated listing; its extra dependencies are not required for core use.

## Human Publication

In the [official portal](https://developers.openai.com/plugins/deploy/submission),
an owner or member with Apps Management Write selects the owning organization
and project, completes individual/business verification, then uploads via
Skills only. Resolve findings and wait for every bundled skill's safety/security
scans. A human reviews the [plugin guidelines](https://developers.openai.com/plugins/plugin-guidelines),
completes required attestations, submits for review, and publishes only after
approval. Uploading a ZIP alone does not publish it. Never package credentials,
private datasets or unsupported claims; recheck official rules before submission.
