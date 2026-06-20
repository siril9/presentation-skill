#!/usr/bin/env python3
"""Emit a deck-level style/content routing prompt for a subagent.

Use this before finalizing `outline.json` for non-trivial, researched, or
asset-heavy decks. The output prompt asks for structured JSON that constrains
design DNA, preset choice, variants, asset needs, and QA sensitivities.

This is intentionally a prompt emitter, not an automatic picker: deterministic
keyword matching is too brittle for lab/scientific decks and too generic for
brand/editorial decks.

Usage:
    python3 scripts/emit_style_content_router.py --workspace decks/my-deck
    python3 scripts/emit_style_content_router.py --workspace decks/my-deck \\
        --user-prompt "ASCO lab update on LAMP sequencing" --output /tmp/router.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _read_optional(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _load_json(path: Path) -> Any | None:
    text = _read_optional(path)
    if text is None:
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


def _text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text_blob(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(v) for v in value)
    return str(value)


def _outline_summary(outline: Any) -> list[str]:
    if not isinstance(outline, dict):
        return ["outline.json: <missing or malformed>"]

    slides = outline.get("slides") or []
    deck_style = outline.get("deck_style") or {}
    lines = [
        f"Deck title: {outline.get('title', '<untitled>')}",
        f"Deck subtitle: {outline.get('subtitle', '')}",
        f"Current deck_style: {json.dumps(deck_style, sort_keys=True)}",
        f"Slide count: {len(slides) if isinstance(slides, list) else '<invalid>'}",
    ]
    if not isinstance(slides, list):
        return lines

    variants: Counter[str] = Counter()
    visual_intents: Counter[str] = Counter()
    asset_keys: Counter[str] = Counter()
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        variant = str(slide.get("variant") or "-")
        visual = str(slide.get("visual_intent") or "-")
        variants[variant] += 1
        visual_intents[visual] += 1
        assets = slide.get("assets") or {}
        if isinstance(assets, dict):
            for key, value in assets.items():
                if value:
                    asset_keys[str(key)] += 1
        title = str(slide.get("title") or "").strip()
        role = str(slide.get("slide_intent") or slide.get("role") or "").strip()
        if idx < 18:
            lines.append(
                f"slide {idx:02d}: type={slide.get('type', 'content')} "
                f"variant={variant} visual_intent={visual} "
                f"role={role or '-'} title={title[:90]}"
            )

    lines.append(f"Variant histogram: {dict(variants)}")
    lines.append(f"Visual-intent histogram: {dict(visual_intents)}")
    lines.append(f"Asset-key histogram: {dict(asset_keys)}")
    return lines


def _evidence_summary(evidence_plan: Any, asset_plan: Any) -> list[str]:
    lines: list[str] = []
    if isinstance(evidence_plan, dict):
        items = evidence_plan.get("items") or []
        chart_candidates = evidence_plan.get("chart_candidates") or []
        visual_uses: Counter[str] = Counter()
        units: Counter[str] = Counter()
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                visual_uses[str(item.get("visual_use") or "-")] += 1
                if item.get("unit"):
                    units[str(item.get("unit"))] += 1
        lines.append(f"Evidence items: {len(items) if isinstance(items, list) else '<invalid>'}")
        lines.append(f"Evidence visual_use histogram: {dict(visual_uses)}")
        lines.append(f"Evidence units: {dict(units)}")
        lines.append(
            f"Chart candidates: {len(chart_candidates) if isinstance(chart_candidates, list) else '<invalid>'}"
        )
    else:
        lines.append("Evidence plan: <missing or malformed>")

    if isinstance(asset_plan, dict):
        for key in ("images", "charts", "icons", "backgrounds", "generated_images"):
            value = asset_plan.get(key)
            if isinstance(value, list):
                lines.append(f"Asset plan {key}: {len(value)}")
    else:
        lines.append("Asset plan: <missing or malformed>")
    return lines


def _keyword_priors(text: str) -> list[str]:
    priors = {
        "asco": "conference/scientific meeting",
        "tb": "infectious disease/lab domain",
        "lamp": "assay/workflow domain",
        "clinical": "clinical proof burden",
        "lod": "limit-of-detection result",
        "sequencing": "data-derived figure/table evidence",
        "assay": "methods/readout evidence",
        "sample": "sample/run metadata",
        "resistance": "genotype/clinical interpretation state",
    }
    lower = text.lower()
    found: list[str] = []
    for term, meaning in priors.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower):
            found.append(f"{term}: {meaning}")
    return found


PROMPT = """\
You are the style/content routing scout for a PowerPoint deck. Your job is to
choose the deck's design DNA and slide-level route BEFORE the author finalizes
outline.json.

Read these refs first. They are authoritative:
- {design_philosophy}
- {planning_schema}
- {outline_schema}
- {subagent_patterns}
- {reference_script_patterns}
- {dynamic_design_and_subagents}

Important rule: do NOT route by keywords alone. Terms like ASCO, TB, LAMP,
clinical, LOD, sequencing, assay, sample, and resistance are useful priors, but
you must validate them against the objective, audience, evidence objects, and
asset availability. A public-health explainer that mentions TB may need an
editorial deck. A lab update that never says "assay" may still need
figure-first report layouts.

Classify the deck on these axes:
- user objective: talk, report, leave-behind, pitch, poster, lab update
- audience posture: scientific peer, clinician, executive, public, student
- evidence objects: figures, plots, microscopy/images, assay readouts, result
  tables, raw data, workflow, screenshots, citations, metrics
- proof burden: concept, sourced report, clinical/lab claim, validation claim
- asset availability: local figures, generated figures, source-backed images,
  editable tables, charts, no assets yet
- density: live talk, readable report, dense leave-behind

Then recommend bounded design modulation. Start from a loadable preset, then
specify subtle/moderate/bold changes that match the audience, evidence, and
deck role: accent use, whitespace, density, motif, container policy, and
figure/table treatment. Do not propose unsupported inline colors or custom
fonts unless the main author should add a validated preset/font pair.

If you introduce title-slide chips, stage tags, or evidence labels, define how
they continue after slide 1. A cover-only motif is a template tell. For
lab/scientific decks with generated figures, also specify the figure export
contract: Python script path, target variant/box, and whitespace/cropping rule.
When local CSV/TSV/XLSX/JSON data, result tables, or chart candidates drive the
deck, return a data artifact workflow that tells the main agent to run the
dedicated analysis scout and deterministic scaffold before outline finalization:
scripts/emit_data_analysis_prompt.py, scripts/scaffold_figure_artifacts.py
--run --bind-outline, scripts/build_workspace.py --fast-first-pass, and
scripts/trim_image_whitespace.py when exported plots have large exterior
whitespace. The workflow must state which slide routes need chart:<name>,
table:<name>, or image:<name> aliases, and which artifacts need reproducibility
metadata.
Also return a concrete readability contract, including
readability_contract.max_slide_text_lines, max_slide_words, max_slide_chars,
max_title_lines, minimum chart/table label sizes, and footer reserve. Flag
content_span_too_short/content_span_too_narrow risk when evidence or text would
leave awkward unused slide space.

For lab/report evidence, prefer:
- style_preset: lab-report or another restrained report preset
- deck_style: header_mode lab-clean, footer_mode source-line,
  summary_callout_mode lab-box, research_visual_mode true
- variants: scientific-figure, image-sidebar, lab-run-results, table,
  comparison-2col, and scoped flow/workflow
- avoid: generic cards-3, decorative icon grids, forced KPI hero slides, and
  process diagrams that do not carry evidence

For non-lab decks, choose the appropriate design DNA and preserve visual
specificity. Do not force lab-report because one keyword appears.

Return ONLY valid JSON with this shape:

{{
  "design_dna": "lab results dashboard | board risk memo | product/investor reveal | editorial report | civic science policy | custom",
  "style_preset": "loadable preset name",
  "deck_style": {{
    "style_seed": "short stable deck-specific seed",
    "header_mode": "bar | stack | eyebrow | lab-clean | lab-card",
    "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
    "footer_mode": "standard | source-line",
    "summary_callout_mode": "default | lab-box",
    "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar",
    "chart_treatment": "standard | facts-below | facts-right | minimal",
    "research_visual_mode": true
  }},
  "style_mix_matrix": {{
    "header_variant_pool": ["left-accent", "split-rule", "title-rule", "side-rail", "top-bottom-rule", "plain"],
    "title_layout_pool": ["split-hero", "lab-plate", "command-center", "poster", "masthead", "light-atlas"],
    "section_motif_pool": ["rail-dots", "numbered-tabs", "plain"],
    "timeline_mode_pool": ["rail-cards", "staggered", "open-events", "bands", "chapter-spread"],
    "matrix_mode_pool": ["cards", "open-quadrants"],
    "stats_mode_pool": ["tiles", "feature-left", "policy-bands"],
    "cards_mode_pool": ["feature-left", "staggered-row"],
    "chart_treatment_pool": ["standard", "facts-below", "facts-right", "minimal"],
    "summary_callout_mode_pool": ["default", "lab-box"],
    "figure_table_treatment_pool": ["figure-first", "table-first", "stats-strip", "image-sidebar"],
    "footer_pool": ["source-line", "standard", "none"],
    "mix_rule": "rotate only compatible treatments that reinforce the design DNA",
    "do_not_mix": ["specific treatment pairings that would make the deck feel random"]
  }},
  "design_modulation": {{
    "change_intensity": "subtle | moderate | bold",
    "base_preset_fit": "base preset is enough | preset plus treatment changes | new preset needed",
    "accent_strategy": "where accent color appears and where it must not",
    "density_strategy": "low live-talk density | medium brief | high report density",
    "whitespace_strategy": "more breathing room | compact report grid | poster-like open field",
    "motif_strategy": "specific motif or none; must relate to topic/evidence",
    "container_strategy": "cards, panels, open grid, table-first, figure-first",
    "figure_table_treatment": "caption/source/table density and semantic highlight rules",
    "avoid": ["visual move that would make the deck generic or misleading"]
  }},
  "evidence_continuity": {{
    "threads": ["EVIDENCE", "READOUT", "NEXT RUN"],
    "carry_forward_rule": "how cover chips/tags continue on content slides",
    "slide_applications": [
      {{
        "slide_id_or_index": "s2 or 2",
        "thread": "EVIDENCE",
        "placement": "subtitle eyebrow | sidebar label | footer tag | table group label"
      }}
    ]
  }},
  "figure_export_contract": {{
    "script": "assets/make_figures.py or none",
    "rerun_command": "python3 assets/make_figures.py",
    "outputs": [
      {{
        "path": "assets/figures/example.png",
        "target_slide": "s3 or stable slide id",
        "target_variant": "image-sidebar | scientific-figure | lab-run-results | table | chart",
        "target_box": "approximate rendered size in inches",
        "figure_size_inches": [6.4, 3.6],
        "figure_dpi": 180,
        "axis_label_min_pt": 8,
        "legend_pt": 8,
        "x_label_rotation": 0,
        "crop_rule": "tight bbox, <=0.08 in visual padding, avoid large internal whitespace"
      }}
    ]
  }},
  "data_artifact_workflow": {{
    "data_artifacts_likely": true,
    "analysis_prompt": "scripts/emit_data_analysis_prompt.py --workspace <workspace> --user-prompt <brief>",
    "scaffold_command": "python3 scripts/scaffold_figure_artifacts.py --workspace <workspace> --run --bind-outline",
    "integrated_scaffold_command": "python3 scripts/build_workspace.py --workspace <workspace> --fast-first-pass",
    "whitespace_trim_command": "python3 scripts/trim_image_whitespace.py --input assets/figures/example.png --output assets/figures/example.png",
    "analysis_summary": "assets/analysis_summary.json plus assets/analysis_summary.md for fast agent inspection before outline binding",
    "artifact_registry_requirements": [
      "analysis_artifact_plan.artifact_manifest points to assets/artifacts_manifest.json",
      "analysis_artifact_plan.analysis_summary points to assets/analysis_summary.json",
      "analysis_artifact_plan.artifact_registry entries for generated figures/charts/tables",
      "analysis_metadata.source_path",
      "analysis_metadata.source_sha256",
      "analysis_metadata.selected_columns",
      "analysis_metadata.rows_used",
      "analysis_metadata.series_count",
      "analysis_metadata.points",
      "analysis_metadata.target_box",
      "analysis_metadata.figure_size_inches",
      "analysis_metadata.figure_dpi",
      "analysis_metadata.axis_label_min_pt",
      "analysis_metadata.legend_pt",
      "analysis_metadata.x_label_rotation",
      "used_on_slides resolves to outline slide ids",
      "figure_export_contract.outputs[*].target_slide is set when outline aliases already exist"
    ],
    "slide_alias_plan": [
      {{
        "slide_id_or_index": "s3 or 3",
        "required_artifact_ids": ["signal_figure", "signal_chart"],
        "aliases": ["image:signal_figure", "chart:signal_chart", "table:signal_summary"],
        "source_policy": "source-line footer with short IDs; full refs on References slide"
      }}
    ]
  }},
  "readability_contract": {{
    "max_title_lines": 2,
    "max_slide_text_lines": 8,
    "max_slide_words": 105,
    "max_slide_chars": 700,
    "body_min_pt": 14,
    "caption_min_pt": 8,
    "table_body_min_pt": 9,
    "chart_label_min_pt": 8,
    "footer_reserved_inches": 0.34,
    "source_line_footer_rule": "short source IDs only; long references below rule or on final References slide"
  }},
  "routing_basis": [
    "specific evidence/object/audience signal that justifies the route"
  ],
  "keyword_priors_used": [
    "keyword priors that were confirmed or rejected"
  ],
  "allowed_variants": [
    "scientific-figure",
    "image-sidebar"
  ],
  "forbidden_variants": [
    "variant that would make the deck generic or misleading"
  ],
  "slide_routes": [
    {{
      "slide_id_or_index": "s3 or 3",
      "role": "evidence | mechanism | comparison | implication | title",
      "variant": "scientific-figure",
      "visual_strategy": "source-backed figure with interpretation sidebar",
      "asset_needs": ["image:assay_readout"],
      "required_artifact_ids": ["assay_readout"],
      "evidence_objects": ["plot", "result table"],
      "source_policy": "source-line footer | final References slide | inline caption",
      "reason": "why this route fits",
      "confidence": 0.0
    }}
  ],
  "asset_requests": [
    {{
      "id": "fig_or_image_id",
      "type": "local figure | generated figure | source-backed image | editable table | chart",
      "why_needed": "visual/evidence role",
      "provenance_needed": true
    }}
  ],
  "subagent_plan": [
    {{
      "stage": "content research | data/evidence analysis | outline critique | rendered visual QA",
      "use_subagent": true,
      "prompt_emitter": "scripts/emit_content_research.py | scripts/emit_data_analysis_prompt.py | scripts/emit_outline_critique.py | render_slides.py --emit-visual-prompt",
      "reason": "why independent review or analysis is useful",
      "expected_output": "punch list or JSON constraint layer",
      "must_not_do": "do not author final outline or bypass deterministic QA"
    }}
  ],
  "qa_sensitivities": [
    "footers must not collide with dense tables",
    "source-line footer text must not shrink into unreadable provenance",
    "captions must remain legible at 9-11 pt",
    "native chart labels must honor axis_label_min_pt and chart_label_min_pt",
    "watch for content_span_too_short and content_span_too_narrow whitespace warnings",
    "figure/table slides need enough target_box area for readable labels"
  ],
  "open_questions": []
}}

--- User prompt ---

{user_prompt}

--- Keyword priors detected ---

{keyword_priors}

--- Workspace summary ---

{workspace_summary}

--- Evidence/assets summary ---

{evidence_summary}

--- design_brief.json ---

{design_brief}

--- content_plan.json ---

{content_plan}

--- evidence_plan.json ---

{evidence_plan}

--- asset_plan.json ---

{asset_plan}

--- outline.json ---

{outline}

--- notes.md ---

{notes}
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a subagent prompt for deck-level style/content routing."
    )
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument(
        "--user-prompt",
        default="",
        help="Original user request or brief to include as routing context.",
    )
    parser.add_argument("--output", help="Write prompt to this file instead of stdout")
    parser.add_argument(
        "--truncate-json",
        type=int,
        default=12000,
        help="Max chars per JSON planning file included in the prompt.",
    )
    parser.add_argument(
        "--truncate-notes",
        type=int,
        default=4000,
        help="Max chars of notes.md included in the prompt.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    design_brief = _load_json(workspace / "design_brief.json")
    content_plan = _load_json(workspace / "content_plan.json")
    evidence_plan = _load_json(workspace / "evidence_plan.json")
    asset_plan = _load_json(workspace / "asset_plan.json")
    outline = _load_json(workspace / "outline.json")
    notes = _read_optional(workspace / "notes.md") or "<missing>"

    combined_text = " ".join(
        [
            args.user_prompt,
            _text_blob(design_brief),
            _text_blob(content_plan),
            _text_blob(evidence_plan),
            _text_blob(asset_plan),
            _text_blob(outline),
            notes,
        ]
    )
    priors = _keyword_priors(combined_text)

    repo_root = Path(__file__).resolve().parent.parent
    refs = {
        "design_philosophy": str(repo_root / "references" / "design_philosophy.md"),
        "planning_schema": str(repo_root / "references" / "planning_schema.md"),
        "outline_schema": str(repo_root / "references" / "outline_schema.md"),
        "subagent_patterns": str(repo_root / "references" / "subagent_patterns.md"),
        "reference_script_patterns": str(
            repo_root / "references" / "reference_script_patterns.md"
        ),
        "dynamic_design_and_subagents": str(
            repo_root / "references" / "dynamic_design_and_subagents.md"
        ),
    }

    prompt = PROMPT.format(
        user_prompt=args.user_prompt or "<not provided>",
        keyword_priors="\n".join(f"- {item}" for item in priors) or "<none>",
        workspace_summary="\n".join(_outline_summary(outline)),
        evidence_summary="\n".join(_evidence_summary(evidence_plan, asset_plan)),
        design_brief=_compact_json(design_brief, args.truncate_json),
        content_plan=_compact_json(content_plan, args.truncate_json),
        evidence_plan=_compact_json(evidence_plan, args.truncate_json),
        asset_plan=_compact_json(asset_plan, args.truncate_json),
        outline=_compact_json(outline, args.truncate_json),
        notes=_truncate(notes, args.truncate_notes),
        **refs,
    )

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(prompt, encoding="utf-8")
        print(f"Style/content router prompt written to {output}", file=sys.stderr)
    else:
        print("=" * 72)
        print("STYLE/CONTENT ROUTER SUBAGENT PROMPT (paste into an Explore agent)")
        print("=" * 72)
        print(prompt)
        print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
