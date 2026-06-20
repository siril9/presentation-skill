#!/usr/bin/env python3
"""Emit a contract-aware prompt for authoring outline.json.

This is the deterministic handoff between a locked deck_design_contract_v1 and
the main-agent source edits that create the real deck outline. It does not
modify source files; it packages the current contract, plans, artifact context,
and authoring rules into a prompt that can be answered directly or pasted into
one outline-authoring subagent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_json(path: Path) -> Any | None:
    text = _read_optional(path)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


def _compact_json(payload: Any, limit: int) -> str:
    if payload is None:
        return "<missing or malformed>"
    return _truncate(json.dumps(payload, indent=2, ensure_ascii=False), limit)


def _workspace_context(workspace: Path, limit: int) -> str:
    files = {
        "deck_start_packet.json": _load_json(workspace / "deck_start_packet.json"),
        "intake_answers.json": _load_json(workspace / "intake_answers.json"),
        "intake_apply_report.json": _load_json(workspace / "intake_apply_report.json"),
        "design_contract.json": _load_json(workspace / "design_contract.json"),
        "design_contract_apply_report.json": _load_json(workspace / "design_contract_apply_report.json"),
        "design_brief.json": _load_json(workspace / "design_brief.json"),
        "content_plan.json": _load_json(workspace / "content_plan.json"),
        "evidence_plan.json": _load_json(workspace / "evidence_plan.json"),
        "asset_plan.json": _load_json(workspace / "asset_plan.json"),
        "outline.json": _load_json(workspace / "outline.json"),
        "assets/artifacts_manifest.json": _load_json(workspace / "assets" / "artifacts_manifest.json"),
        "assets/analysis_summary.json": _load_json(workspace / "assets" / "analysis_summary.json"),
    }
    blocks = [f"Workspace: {workspace}"]
    for name, payload in files.items():
        blocks.append(f"\n{name}:\n{_compact_json(payload, limit)}")
    notes = _read_optional(workspace / "notes.md")
    blocks.append(f"\nnotes.md:\n{_truncate(notes or '<missing>', limit)}")
    return "\n".join(blocks)


def _reference_context(limit: int) -> str:
    refs = {
        "DESIGN.md": ROOT / "DESIGN.md",
        "outline_schema.md": ROOT / "references" / "outline_schema.md",
        "planning_schema.md": ROOT / "references" / "planning_schema.md",
    }
    blocks: list[str] = []
    for label, path in refs.items():
        text = _read_optional(path)
        blocks.append(f"{label}:\n{_truncate(text or '<missing>', limit)}")
    return "\n\n".join(blocks)


def _artifact_alias_summary(workspace: Path) -> str:
    manifest = _load_json(workspace / "assets" / "artifacts_manifest.json")
    if not isinstance(manifest, dict):
        return "<no generated artifact manifest found>"
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return "<artifact manifest has no outputs>"
    lines: list[str] = []
    for output in outputs[:40]:
        if not isinstance(output, dict):
            continue
        output_id = str(output.get("id") or "").strip()
        title = str(output.get("title") or output_id or "artifact").strip()
        lines.append(f"- output `{output_id or title}`: {title}")
        artifacts = output.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts[:8]:
                if not isinstance(artifact, dict):
                    continue
                alias = str(artifact.get("alias") or "").strip()
                role = str(artifact.get("role") or "").strip()
                path = str(artifact.get("path") or "").strip()
                if alias or path:
                    lines.append(f"  - {role or 'artifact'} `{alias or path}` from `{path}`")
    return "\n".join(lines) if lines else "<no usable artifact aliases found>"


def _artifact_rebuild_context_summary(workspace: Path, limit: int = 4000) -> str:
    contexts: list[dict[str, Any]] = []
    manifest = _load_json(workspace / "assets" / "artifacts_manifest.json")
    if isinstance(manifest, dict) and isinstance(manifest.get("rebuild_context"), dict):
        contexts.append(
            {
                "source": "assets/artifacts_manifest.json",
                "rebuild_context": manifest.get("rebuild_context"),
            }
        )
    summary = _load_json(workspace / "assets" / "analysis_summary.json")
    if isinstance(summary, dict) and isinstance(summary.get("rebuild_context"), dict):
        summary_context = summary.get("rebuild_context")
        if not contexts or contexts[0].get("rebuild_context") != summary_context:
            contexts.append(
                {
                    "source": "assets/analysis_summary.json",
                    "rebuild_context": summary_context,
                }
            )
    if not contexts:
        return "<no generated artifact rebuild context found>"
    return _compact_json({"contexts": contexts}, limit)


def _slide_quality_context(workspace: Path, limit: int = 4000) -> str:
    for path, key in (
        (workspace / "design_brief.json", "slide_quality_contract"),
        (workspace / "design_contract.json", "slide_quality_contract"),
        (workspace / "deck_start_packet.json", "slide_quality_contract"),
    ):
        payload = _load_json(path)
        if not isinstance(payload, dict):
            continue
        contract = payload.get(key)
        if isinstance(contract, dict):
            return _compact_json(
                {
                    "source": str(path),
                    "slide_quality_contract": contract,
                },
                limit,
            )
    return "<no slide_quality_contract found; derive conservative readability, whitespace, evidence-anchor, artifact, and QA targets from design_brief/readability_contract/qa_contract>"


PROMPT_TEMPLATE = """\
You are authoring the source outline for a reproducible PowerPoint deck.

The design contract is already locked. Your job is NOT to redesign the deck
from scratch. Use the contract, planning files, artifact aliases, and rules
below to produce a source patch packet that the main agent can apply to
`outline.json`, `content_plan.json`, `evidence_plan.json`, `asset_plan.json`,
and `notes.md`.

Return ONLY valid JSON. Do not include prose outside JSON.
Save the JSON as `{workspace}/outline_authoring_handoff.json`, then apply it
with `python3 scripts/apply_outline_authoring_handoff.py --workspace {workspace}
--handoff {workspace}/outline_authoring_handoff.json --report
{workspace}/outline_authoring_handoff_apply_report.json`.

Return this JSON shape:

{{
  "handoff_version": "outline_authoring_handoff_v1",
  "workspace": "{workspace}",
  "contract_alignment": {{
    "style_seed": "copied from design_contract/design_brief",
    "style_preset": "copied from contract",
    "header_footer_plan": "how the locked header/footer system is used",
    "variant_mix_plan": "how structure_blueprint.allowed_variants are used without random cycling"
  }},
  "artifact_rebuild_plan": {{
    "context_version": "presentation_skill_artifact_rebuild_context_v1 or none",
    "producer_path": "assets/make_figures.py or none",
    "source_paths": ["data/source.csv"],
    "output_paths": ["assets/figures/example.png"],
    "commands_to_preserve": [
      "copy rebuild_context.commands.rebuild_figures when available",
      "copy rebuild_context.commands.inspect_manifest when available",
      "copy rebuild_context.commands.auto_select_lead or auto_select_all when available",
      "copy rebuild_context.commands.validate_planning when available"
    ],
    "notes": "how generated artifacts should be rebuilt or rebound after outline edits"
  }},
  "quality_alignment": {{
    "contract_version": "slide_quality_contract_v1 or derived",
    "readability_targets_used": [
      "min_title_pt=24",
      "min_body_pt=12",
      "chart_label_min_pt=7",
      "footer_reserved_inches=0.25"
    ],
    "layout_targets_used": [
      "evidence_anchor_required",
      "fail_on_awkward_whitespace",
      "avoid_repeated_card_grids",
      "compact_source_footer"
    ],
    "artifact_quality_targets_used": [
      "record generated artifact source fingerprints and producer fingerprints",
      "record image whitespace measurement or trim rule when generated figures are used"
    ],
    "qa_gates_used": [
      "planning_warnings",
      "whitespace_warnings",
      "design_readability_warnings"
    ],
    "required_commands": [
      "copy the relevant slide_quality_contract.qa_gates.required_commands"
    ],
    "outline_choices": "how the chosen slide variants, evidence anchors, and prose density satisfy the quality contract"
  }},
  "source_patch": {{
    "outline_json": {{
      "title": "final deck title",
      "subtitle": "optional subtitle",
      "deck_style": {{}},
      "slides": [
        {{
          "type": "title | content | section",
          "slide_id": "stable ID from structure_blueprint where possible",
          "title": "specific non-placeholder title",
          "subtitle": "optional",
          "variant": "supported variant",
          "slide_intent": "context | evidence | method | comparison | implication | close",
          "visual_intent": "figure | chart | table | image | structured comparison | concise report body",
          "body": "short body text when useful",
          "bullets": [],
          "sources": ["S1: compact source label or citation ID"]
        }}
      ]
    }},
    "content_plan_updates": {{
      "thesis": "deck-level thesis",
      "audience": "target audience",
      "slide_plan": [],
      "narrative_arc": []
    }},
    "evidence_plan_updates": {{
      "source_policy": "none | cite key claim | source every factual claim",
      "items": [],
      "chart_candidates": []
    }},
    "asset_plan_updates": {{
      "images": [],
      "charts": [],
      "tables": [],
      "generated_images": []
    }},
    "notes_append": "manual assumptions, skipped conditional phases, and unresolved inputs"
  }},
  "acceptance_checks": [
    "outline has no TODO/TBD/lorem/[insert]/[placeholder] visible text",
    "every content slide has a visual or evidence anchor",
    "sources match evidence_plan.source_policy",
    "artifact aliases resolve to asset_plan or assets/artifacts_manifest.json",
    "slide IDs resolve across content_plan, evidence_plan, asset_plan, and figure_export_contract",
    "text density stays inside readability_contract budgets",
    "quality_alignment explicitly references slide_quality_contract_v1 targets",
    "run: python3 scripts/report_workspace_readiness.py --workspace {workspace}"
  ],
  "main_agent_handoff": {{
    "files_to_patch": [
      "{workspace}/outline.json",
      "{workspace}/content_plan.json",
      "{workspace}/evidence_plan.json",
      "{workspace}/asset_plan.json",
      "{workspace}/notes.md"
    ],
    "commands_after_patch": [
      "python3 scripts/apply_outline_authoring_handoff.py --workspace {workspace} --handoff {workspace}/outline_authoring_handoff.json --report {workspace}/outline_authoring_handoff_apply_report.json",
      "python3 scripts/report_workspace_readiness.py --workspace {workspace}",
      "python3 scripts/build_workspace.py --workspace {workspace} --qa --skip-render --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite"
    ]
  }}
}}

Authoring rules:

- Use the locked `deck_design_contract_v1` and applied `design_brief.json`
  decisions. Preserve style_preset, style_seed, palette, background system,
  header/footer treatments, source-line/footer/page-number posture,
  readability_contract, speed_contract, slide_quality_contract, and
  style_mix_matrix.
- Use `structure_blueprint.slide_sequence` as the primary slide order. If a
  slide must be merged, split, or skipped, explain it in `notes_append`.
- Fill `quality_alignment` from the Slide quality contract block below. It
  should name the concrete readability floors, whitespace/evidence-anchor
  rules, generated-artifact metadata expectations, and QA gates that changed
  the slide variant or prose-density choices.
- Use only supported outline variants. If the contract names an unsupported
  variant, map to the nearest supported variant and record the mapping.
- Every content/evidence slide must have a real visual or evidence anchor:
  chart, table, figure, image, diagram, stats, KPI, flow, or structured
  comparison. Do not leave report slides as stranded prose bands.
- For lab/report decks, prefer evidence-first variants: `scientific-figure`,
  `image-sidebar`, `lab-run-results`, `table`, `chart`, then
  `comparison-2col` or concise standard report slides.
- Use existing generated artifact aliases when available. Do not invent local
  file paths, chart JSON, table JSON, or image paths. If the needed artifact is
  absent, add the need to `asset_plan_updates` and `notes_append` instead.
- When a `presentation_skill_artifact_rebuild_context_v1` block is available,
  preserve its rebuild, inspect, auto-bind, and validation commands in
  `artifact_rebuild_plan` and `main_agent_handoff.commands_after_patch` when
  generated evidence must be rerun or rebound.
- Keep footer/source provenance compact. Use short source IDs in slide
  footers/sources and move long citations to a References/Image Sources slide
  when needed.
- Do not use placeholders, TODO/TBD, lorem/ipsum, or PowerPoint prompt text in
  visible fields. If information is missing, write a concise assumption or
  skip note in `notes_append`.
- Keep text readable: short titles, compact bullets, no dense sentence-length
  table cells, and no overpacked charts. Respect footer_reserved_inches and
  chart_label_min_pt.
- Patch source files only. Do not mutate generated PPTX files.

Original user request or summary:
{user_prompt}

Slide quality contract:
{slide_quality_context}

Generated artifact aliases:
{artifact_aliases}

Generated artifact rebuild context:
{artifact_rebuild_context}

Repository rules:
{reference_context}

Workspace context:
{workspace_context}
"""


def render_outline_authoring_prompt(
    *,
    workspace: Path,
    user_prompt: str = "",
    context_limit: int = 5000,
    reference_limit: int = 5000,
) -> str:
    resolved_workspace = workspace.expanduser().resolve()
    return PROMPT_TEMPLATE.format(
        workspace=str(resolved_workspace),
        user_prompt=user_prompt.strip() or "<infer from design_contract.json and planning files>",
        slide_quality_context=_slide_quality_context(resolved_workspace),
        artifact_aliases=_artifact_alias_summary(resolved_workspace),
        artifact_rebuild_context=_artifact_rebuild_context_summary(resolved_workspace),
        reference_context=_reference_context(reference_limit),
        workspace_context=_workspace_context(resolved_workspace, context_limit),
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit a contract-aware outline authoring prompt.")
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument("--user-prompt", default="", help="Original user deck request or concise summary")
    parser.add_argument("--output", default="", help="Optional path to write the prompt")
    parser.add_argument("--context-limit", type=int, default=5000, help="Per-file workspace context character limit")
    parser.add_argument("--reference-limit", type=int, default=5000, help="Per-reference character limit")
    return parser.parse_args()


def main() -> int:
    args = _args()
    prompt = render_outline_authoring_prompt(
        workspace=Path(args.workspace),
        user_prompt=args.user_prompt,
        context_limit=max(1000, args.context_limit),
        reference_limit=max(1000, args.reference_limit),
    )
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt, encoding="utf-8")
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
