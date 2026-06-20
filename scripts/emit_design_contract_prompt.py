#!/usr/bin/env python3
"""Emit a reproducible deck design-contract prompt.

Use immediately after a user's deck request, before outline authoring. The
prompt asks a main agent or subagent to return a strict JSON contract that locks
style, background, structure, evidence policy, and QA expectations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from style_treatment_profiles import preset_treatment_profile


ROOT = Path(__file__).resolve().parent.parent
SMALL_FILE_HASH_LIMIT = 5 * 1024 * 1024
INVENTORY_LIMIT = 24
TABULAR_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".feather"}
JSON_DATA_EXCLUDED_NAMES = {
    "workspace.json",
    "style_contract.json",
    "design_brief.json",
    "content_plan.json",
    "evidence_plan.json",
    "asset_plan.json",
    "outline.json",
    "design_contract.json",
    "deck_start_packet.json",
    "intake_answers.json",
    "intake_apply_report.json",
    "outline_authoring_handoff.json",
    "outline_authoring_handoff_apply_report.json",
}
ARTIFACT_LEDGER_PATHS = [
    "assets/artifacts_manifest.json",
    "assets/analysis_summary.json",
    "assets/analysis_summary.md",
    "artifact_selections.auto.json",
    "data_analysis_handoff.json",
    "data_analysis_handoff_apply_report.json",
    "style_extract_report.json",
    "style_extract_design_brief.json",
    "style_fragment_apply_report.json",
    "design_contract_apply_report.json",
]


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


def _compact_json(value: Any, limit: int = 5000) -> str:
    if value is None:
        return "<missing or malformed>"
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated at {limit} chars]"


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:54] or "deck"


def _stable_id(user_prompt: str) -> str:
    digest = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()[:12]
    return f"{_slug(user_prompt)}-{digest}"


def _display_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _file_snapshot(workspace: Path, path: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": path.exists(),
    }
    if not path.exists() or not path.is_file():
        return snapshot
    try:
        size = path.stat().st_size
        snapshot["size_bytes"] = size
        if size <= SMALL_FILE_HASH_LIMIT:
            snapshot["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            snapshot["sha256"] = ""
            snapshot["hash_status"] = f"skipped_gt_{SMALL_FILE_HASH_LIMIT}_bytes"
    except OSError as exc:
        snapshot["error"] = str(exc)
    return snapshot


def _iter_candidate_files(workspace: Path) -> list[Path]:
    ignored_parts = {".git", "build", "node_modules", "__pycache__", ".venv", "venv"}
    files: list[Path] = []
    try:
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(workspace)
            except ValueError:
                rel = path
            if any(part in ignored_parts for part in rel.parts):
                continue
            files.append(path)
    except OSError:
        return []
    return sorted(files, key=lambda item: _display_path(workspace, item))


def _is_data_candidate(workspace: Path, path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TABULAR_EXTENSIONS:
        return True
    if suffix != ".json":
        return False
    name = path.name.lower()
    if name in JSON_DATA_EXCLUDED_NAMES:
        return False
    try:
        rel_parts = path.relative_to(workspace).parts
    except ValueError:
        rel_parts = path.parts
    if rel_parts and rel_parts[0] in {"data", "datasets", "inputs"}:
        return True
    if len(rel_parts) >= 2 and rel_parts[0] == "assets" and rel_parts[1] in {"charts", "tables"}:
        return True
    return any(token in name for token in ("data", "dataset", "table", "chart", "results", "measurements"))


def _workspace_source_inventory(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {
            "workspace": "",
            "data_files": [],
            "reference_pptx_files": [],
            "artifact_ledger_files": [],
        }
    workspace = workspace.expanduser().resolve()
    if not workspace.exists():
        return {
            "workspace": str(workspace),
            "exists": False,
            "data_files": [],
            "reference_pptx_files": [],
            "artifact_ledger_files": [],
        }
    candidates = _iter_candidate_files(workspace)
    data_candidates = [
        path
        for path in candidates
        if _is_data_candidate(workspace, path)
        and not _display_path(workspace, path).startswith("assets/staged/")
    ]
    reference_pptx_candidates = [path for path in candidates if path.suffix.lower() == ".pptx"]
    data_files = [_file_snapshot(workspace, path) for path in data_candidates[:INVENTORY_LIMIT]]
    reference_pptx_files = [
        _file_snapshot(workspace, path)
        for path in reference_pptx_candidates[:INVENTORY_LIMIT]
    ]
    artifact_ledger_files = [
        _file_snapshot(workspace, workspace / rel_path)
        for rel_path in ARTIFACT_LEDGER_PATHS
        if (workspace / rel_path).exists()
    ]
    return {
        "workspace": str(workspace),
        "exists": True,
        "data_file_count": len(data_candidates),
        "data_file_shown_count": len(data_files),
        "reference_pptx_count": len(reference_pptx_candidates),
        "reference_pptx_shown_count": len(reference_pptx_files),
        "artifact_ledger_count": len(artifact_ledger_files),
        "data_files": data_files,
        "reference_pptx_files": reference_pptx_files,
        "artifact_ledger_files": artifact_ledger_files,
        "limits": {
            "max_entries_per_group": INVENTORY_LIMIT,
            "sha256_hashed_when_size_lte_bytes": SMALL_FILE_HASH_LIMIT,
        },
    }


def _choice_resolution_seed_summary(design_brief: Any) -> dict[str, Any]:
    if not isinstance(design_brief, dict):
        return {}
    seed = design_brief.get("choice_resolution_seed")
    if not isinstance(seed, dict):
        return {}
    choices = (
        seed.get("resolved_choices")
        if isinstance(seed.get("resolved_choices"), list)
        else []
    )
    routes = (
        seed.get("route_decisions")
        if isinstance(seed.get("route_decisions"), list)
        else []
    )
    route_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    route_ledger = (
        seed.get("route_decision_ledger")
        if isinstance(seed.get("route_decision_ledger"), dict)
        else {}
    )
    ledger_routes = (
        route_ledger.get("routes")
        if isinstance(route_ledger.get("routes"), list)
        else []
    )
    ledger_route_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in ledger_routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    return {
        "exists": True,
        "contract_version": str(seed.get("contract_version") or ""),
        "seed_kind": str(seed.get("seed_kind") or ""),
        "stable_prompt_id": str(seed.get("stable_prompt_id") or ""),
        "answered_by": str(seed.get("answered_by") or ""),
        "choice_ids": [
            str(item.get("id") or "").strip()
            for item in choices
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ],
        "route_status": route_status,
        "route_ledger_version": str(route_ledger.get("ledger_version") or ""),
        "route_ledger_status": ledger_route_status,
        "route_ledger_active_routes": sorted(
            route_id for route_id, active in ledger_route_status.items() if active
        ),
        "replay_inputs": seed.get("replay_inputs") if isinstance(seed.get("replay_inputs"), dict) else {},
    }


def _design_brief_style_preset(design_brief: Any) -> str:
    if not isinstance(design_brief, dict):
        return "executive-clinical"
    for container_key in ("style_system", "visual_system"):
        container = design_brief.get(container_key)
        if isinstance(container, dict):
            value = str(container.get("style_preset") or "").strip()
            if value:
                return value
    value = str(design_brief.get("style_preset") or "").strip()
    return value or "executive-clinical"


def _workspace_context(workspace: Path | None) -> str:
    if workspace is None:
        return "Workspace: <none yet>"
    workspace = workspace.expanduser().resolve()
    design_brief = _load_json(workspace / "design_brief.json")
    files = {
        "design_brief.json": design_brief,
        "content_plan.json": _load_json(workspace / "content_plan.json"),
        "evidence_plan.json": _load_json(workspace / "evidence_plan.json"),
        "asset_plan.json": _load_json(workspace / "asset_plan.json"),
        "outline.json": _load_json(workspace / "outline.json"),
        "notes.md": _read_optional(workspace / "notes.md")[:3000] or "<missing>",
    }
    blocks = [f"Workspace: {workspace}"]
    choice_seed_summary = _choice_resolution_seed_summary(design_brief)
    if choice_seed_summary:
        blocks.append(
            "\ndesign_brief.choice_resolution_seed summary:\n"
            + _compact_json(choice_seed_summary, limit=2500)
        )
    treatment_profile = preset_treatment_profile(_design_brief_style_preset(design_brief))
    blocks.append(
        "\npreset treatment profile for design contract:\n"
        + _compact_json(treatment_profile, limit=4200)
    )
    for name, value in files.items():
        if name.endswith(".json"):
            blocks.append(f"\n{name}:\n{_compact_json(value)}")
        else:
            blocks.append(f"\n{name}:\n{value}")
    return "\n".join(blocks)


def _reference_context() -> str:
    refs = {
        "DESIGN.md": ROOT / "DESIGN.md",
        "planning_schema.md": ROOT / "references" / "planning_schema.md",
        "outline_schema.md": ROOT / "references" / "outline_schema.md",
    }
    blocks = []
    for label, path in refs.items():
        text = _read_optional(path)
        if not text:
            blocks.append(f"{label}: <missing>")
            continue
        blocks.append(f"{label}:\n{text[:6000]}")
    return "\n\n".join(blocks)


PROMPT_TEMPLATE = """\
You are the design-contract scout for a reproducible PowerPoint deck build.
Your job is to convert the user's request into a concrete contract BEFORE
outline.json is written.

Return ONLY valid JSON. Do not write prose outside JSON.

Core rule: preserve creative judgment, but make every decision explicit enough
that another agent can rebuild the same deck family later: preset, palette,
background, header/footer treatment, slide structure, asset posture, evidence
policy, and QA gates.
Also emit a compact reproducibility contract that ties the selected style seed
to the exact background, treatment pools, slide-structure mix, chart/table
posture, artifact ledger paths, replay commands, and QA evidence. This is the
replay layer for mix-and-match styling: it should make the deck varied but not
random, and should let a later agent rebuild the same choices without reopening
the full prompt.

For data-derived figures, editable chart JSON, or summary tables, make the
artifact contract auditable before outline authoring: include source path,
source fingerprint fields, selected columns/fields, rows used, point/series
counts, target slide box, figure export size, DPI, and readable label-size
assumptions. The main agent should be able to copy these decisions into
design_brief.analysis_artifact_plan, figure_export_contract, asset_plan, and
outline asset refs without guessing. If scaffolded data artifacts are likely,
include `assets/analysis_summary.json` as the first-read handoff before
outline binding.

If workspace context includes `design_brief.choice_resolution_seed`, copy that
object into the returned top-level `choice_resolution` field and refine only
when the final contract makes a more specific choice. Keep the compact intake
answers, route decisions, active data/style paths, and locked source fields
visible so the deck can be rebuilt from the same first-turn decisions.
If the seed includes `route_decision_ledger`, carry active route evidence into
`choice_resolution.route_decisions` and record any skipped conditional route
with an explicit reason.

Use these repository constraints:
{reference_context}

User request:
{user_prompt}

Stable prompt id:
{stable_id}

Recommended deterministic style seed:
{style_seed}

Available workspace context:
{workspace_context}

Workspace source inventory:
{workspace_source_inventory}

Return this JSON shape:

{{
  "contract_version": "deck_design_contract_v1",
  "stable_prompt_id": "{stable_id}",
  "user_request_summary": "one concise sentence",
  "missing_inputs": [
    {{
      "question": "high-leverage missing question",
      "why_it_matters": "impact on deck design",
      "default_if_unanswered": "best-judgment assumption"
    }}
  ],
  "assumptions": [
    "explicit assumption to record in notes.md if user does not answer"
  ],
  "choice_resolution": {{
    "contract_version": "deck_choice_resolution_v1",
    "seed_kind": "resolved_intake_answers | scout_refined",
    "stable_prompt_id": "{stable_id}",
    "answered_by": "user | inferred | best_judgment",
    "resolved_choices": [
      {{
        "id": "audience_context | style_density | visual_source_policy",
        "answer": "selected answer or explicit assumption",
        "source_fields": ["design_brief.user_intake"],
        "contract_fields": ["deck_identity.audience"]
      }}
    ],
    "route_decisions": [
      {{
        "id": "data_artifacts | pptx_style_import",
        "active": true,
        "trigger_evidence": "why this route is active or inactive"
      }}
    ],
    "route_decision_ledger": {{
      "ledger_version": "deck_route_decision_ledger_v1",
      "routes": [
        {{
          "id": "intake_questions | design_contract | data_artifacts | pptx_style_import | content_research | source_footer_compaction | rendered_visual_review",
          "active": true,
          "trigger_evidence": ["why this route is active or skipped"]
        }}
      ]
    }},
    "route_ledger_version": "deck_route_decision_ledger_v1",
    "route_ledger_active_routes": [
      "intake_questions",
      "design_contract"
    ],
    "replay_inputs": {{
      "answers": "intake_answers.json or explicit assumptions",
      "packet": "deck_start_packet.json",
      "route_decision_ledger": "deck_start_packet.json:route_decision_ledger"
    }},
    "design_fields_locked": [
      "style_system.style_mix_matrix",
      "readability_contract",
      "evidence_plan.source_policy",
      "analysis_artifact_plan",
      "figure_export_contract"
    ]
  }},
  "reproducibility_contract": {{
    "contract_version": "deck_reproducibility_contract_v1",
    "stable_prompt_id": "{stable_id}",
    "style_seed": "{style_seed}",
    "choice_source": "intake_answers.json | explicit user request | best-judgment assumptions",
    "renderer": "pptxgenjs",
    "locked_design_fields": [
      "style_system.style_preset",
      "style_system.background_system",
      "style_system.style_mix_matrix",
      "structure_blueprint.slide_sequence",
      "evidence_and_assets.analysis_artifact_plan",
      "readability_contract",
      "qa_contract"
    ],
    "replay_inputs": {{
      "user_prompt_hash_source": "original user request",
      "deck_start_packet": "deck_start_packet.json if present",
      "intake_answers": "intake_answers.json or explicit assumptions",
      "design_contract": "design_contract.json",
      "artifact_manifest": "assets/artifacts_manifest.json when generated artifacts exist",
      "analysis_summary": "assets/analysis_summary.json when generated artifacts exist",
      "reference_pptx_style_fragment": "style_extract_design_brief.json when style import is active"
    }},
    "style_replay": {{
      "style_preset": "same as style_system.style_preset",
      "palette_key": "same as style_system.palette_key",
      "background_system": "same as style_system.background_system",
      "header_variant_pool": ["same supported entries as style_mix_matrix.header_variant_pool"],
      "title_layout_pool": ["same supported entries as style_mix_matrix.title_layout_pool"],
      "footer_pool": ["same supported entries as style_mix_matrix.footer_pool"],
      "chart_treatment_pool": ["same supported entries as style_mix_matrix.chart_treatment_pool"],
      "figure_table_treatment_pool": ["same supported entries as style_mix_matrix.figure_table_treatment_pool"],
      "mix_rule": "one sentence describing deterministic treatment rotation from style_seed",
      "variation_boundaries": ["what may vary between sibling decks", "what must stay locked inside this deck"]
    }},
    "structure_replay": {{
      "target_slide_count": 0,
      "slide_variant_mix": ["ordered variants from structure_blueprint.slide_sequence"],
      "evidence_anchor_rule": "how each evidence/data slide gets a visible chart, table, figure, or image anchor",
      "white_space_rule": "how to avoid awkward sparse or overfilled regions"
    }},
    "artifact_replay": {{
      "local_data_needed": false,
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json",
      "figure_script": "assets/make_figures.py or none",
      "rebuild_commands": []
    }},
    "replay_commands": [
      "python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ],
    "acceptance_evidence": [
      "design_contract_apply_report.json",
      "build/workspace_readiness.json",
      "build/build_workspace_report.json",
      "build/delivery_readiness.json"
    ]
  }},
  "deck_identity": {{
    "working_title": "deck title",
    "audience": "scientific peer | executive | public | student | custom",
    "use_context": "live talk | leave-behind | report | pitch | teaching | poster",
    "target_outcome": "what the audience should believe, decide, or do",
    "density": "low | medium | high"
  }},
  "design_dna": "lab results dashboard | board risk memo | product/investor reveal | editorial report | civic science policy | custom",
  "style_system": {{
    "style_preset": "loadable preset name",
    "palette_key": "preset-default or palette key",
    "font_pair": "system_clean_v1 | editorial_serif_v1 | clean_modern_v1",
    "style_seed": "{style_seed}",
    "background_system": "white report | dark stage | light editorial | source-backed visual | generated concept | custom",
    "preset_treatment_profile": "copy/refine the workspace preset treatment profile so preset-specific heading/footer/chart/figure pools are reproducible",
    "header_system": {{
      "header_mode": "bar | stack | eyebrow | lab-clean | lab-card",
      "header_variant": "auto | left-accent | split-rule | title-rule | side-rail | top-bottom-rule | plain",
      "header_variants": ["left-accent", "split-rule", "title-rule", "side-rail", "top-bottom-rule", "plain"],
      "header_rule_color": "accent_primary | accent_secondary | hex"
    }},
    "footer_system": {{
      "footer_mode": "standard | source-line",
      "footer_page_numbers": true,
      "footer_source_label": "Sources",
      "footer_refs_label": "Refs"
    }},
    "title_slide_system": {{
      "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
      "title_motif": "orbit | network | editorial | none",
      "cover_chips_or_tags": ["optional recurring chips"]
    }},
    "section_system": {{
      "section_motif": "rail-dots | none",
      "section_count": 0
    }},
    "figure_table_system": {{
      "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar"
    }},
    "chart_system": {{
      "chart_treatment": "standard | facts-below | facts-right | minimal"
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
      "mix_rule": "how to rotate treatments across slides without making the deck feel random",
      "do_not_mix": ["specific pairings that would break the design DNA"]
    }}
  }},
  "structure_blueprint": {{
    "target_slide_count": 0,
    "slide_sequence": [
      {{
        "slide_id": "s1",
        "role": "title | context | evidence | method | comparison | implication | close",
        "variant": "supported outline variant",
        "visual_strategy": "figure | table | image-sidebar | cards | flow | narrative",
        "required_assets": [],
        "source_policy": "none | cite key claim | source every factual claim"
      }}
    ],
    "allowed_variants": [],
    "forbidden_variants": []
  }},
  "evidence_and_assets": {{
    "proof_burden": "concept | sourced report | technical validation | clinical/lab claim",
    "research_needed": true,
    "local_data_needed": false,
    "analysis_artifact_plan": {{
      "candidate_data_files": [],
      "spreadsheet_inputs": [],
      "required_scripts": [],
      "figure_scripts": [],
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json",
      "analysis_summary_markdown": "assets/analysis_summary.md",
      "chart_json_outputs": [],
      "table_outputs": [],
      "rebuild_commands": [],
      "artifact_registry": [
        {{
          "id": "artifact_id",
          "path": "relative or absolute path",
          "producer": "script or source file",
          "used_on_slides": [],
          "provenance": "data/source/method note",
          "analysis_metadata": {{
            "artifact_role": "figure | chart_json | summary_table",
            "source_path": "relative or absolute source data path",
            "source_sha256": "sha256 or pending until generated",
            "source_bytes": 0,
            "selected_columns": ["field_a", "field_b"],
            "rows_used": 0,
            "series_count": 0,
            "points": 0,
            "target_box": "5.0x3.3 in",
            "figure_size_inches": [6.4, 3.6],
            "figure_dpi": 180,
            "axis_label_min_pt": 8
          }}
        }}
      ]
    }},
    "asset_plan": {{
      "images": [],
      "charts": [],
      "tables": [],
      "icons": [],
      "backgrounds": [],
      "generated_images": []
    }},
    "figure_export_contract": {{
      "script": "assets/make_figures.py or none",
      "rerun_command": "python3 assets/make_figures.py",
      "outputs": [
        {{
          "path": "assets/figures/example.png",
          "target_slide": "s3",
          "target_variant": "image-sidebar | scientific-figure | lab-run-results",
          "target_box": "5.0x3.3 in",
          "figure_size_inches": [6.4, 3.6],
          "figure_dpi": 180,
          "axis_label_min_pt": 8,
          "legend_pt": 8,
          "x_label_rotation": 0,
          "crop_rule": "tight content bbox, <=0.08 in visual padding, no large internal whitespace"
        }}
      ]
    }}
  }},
  "continuity_rules": {{
    "recurring_tags": [],
    "carry_forward_rule": "how cover/title motifs recur intentionally",
    "source_footer_rule": "what appears in footer/sources/refs"
  }},
  "slide_quality_contract": {{
    "contract_version": "slide_quality_contract_v1",
    "readability_targets": {{
      "min_title_pt": 24,
      "min_body_pt": 12,
      "min_caption_pt": 7.5,
      "chart_label_min_pt": 7,
      "footer_reserved_inches": 0.25,
      "max_title_lines": 2,
      "max_slide_text_lines": 12,
      "max_slide_words": 110,
      "max_slide_chars": 780
    }},
    "layout_targets": {{
      "evidence_anchor_required": true,
      "avoid_repeated_card_grids": true,
      "fail_on_awkward_whitespace": true,
      "prefer_source_edit_over_pptx_patch": true,
      "sparse_slide_allowed_only_when_intentional": true,
      "source_footer_rule": "compact source/ref IDs in footers; full references in editable References table slides"
    }},
    "artifact_quality_targets": {{
      "required_when_data_artifacts_active": false,
      "must_record": [
        "source data fingerprints",
        "producer script fingerprints",
        "selected columns or data slices",
        "figure/chart/table output paths",
        "target slide IDs and variants",
        "target figure box",
        "figure size and DPI",
        "axis/chart label font assumptions",
        "image whitespace measurement or trim rule",
        "rerun and inspect commands"
      ]
    }},
    "qa_gates": {{
      "fail_on": ["planning_warnings", "overflow", "overlap", "placeholder_text", "whitespace_warnings", "design_readability_warnings"],
      "required_commands": [
        "python3 scripts/validate_planning.py --workspace <deck>",
        "python3 scripts/build_workspace.py --workspace <deck> --qa --skip-render --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
        "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
        "python3 scripts/report_delivery_readiness.py --workspace <deck>"
      ]
    }}
  }},
  "readability_contract": {{
    "min_title_pt": 26,
    "min_body_pt": 15,
    "min_caption_pt": 8,
    "max_title_lines": 2,
    "max_slide_text_lines": 8,
    "max_slide_words": 105,
    "max_slide_chars": 700,
    "footer_reserved_inches": 0.34,
    "chart_label_min_pt": 8,
    "table_density_rule": "split or summarize tables that force unreadable text",
    "whitespace_rule": "avoid awkward empty regions; use figure/sidebar/table variants when content is sparse",
    "figure_crop_rule": "export tight bounding boxes and trim exterior whitespace before insertion"
  }},
  "speed_contract": {{
    "renderer": "pptxgenjs by default; Python fallback only for legacy renderer-specific behavior",
    "first_pass": "render-free schema/preflight/geometry QA before slide rendering",
    "render_policy": "render only after source files are stable or when visual judgment matters",
    "asset_policy": "reuse local/generated artifacts before network assets unless the deck needs source-backed imagery",
    "conversion_hint": "use persistent LibreOffice/unoserver when available for repeated render QA"
  }},
  "subagent_handoff": {{
    "ask_user_first": true,
    "question_packet": "scripts/emit_deck_start_packet.py or scripts/emit_deck_intake_prompt.py --codex-ui",
    "design_contract_scout": "this prompt; return strict JSON",
    "content_research_scout": "scripts/emit_content_research.py when claims need sourced anchors",
    "data_analysis_scout": "scripts/emit_data_analysis_prompt.py when local data, spreadsheets, or figures drive claims",
    "style_content_router": "scripts/emit_style_content_router.py for non-trivial or visually ambiguous decks",
    "outline_critique": "scripts/emit_outline_critique.py before final build",
    "visual_qa": "render_slides.py --emit-visual-prompt or build_workspace.py --visual-review after render"
  }},
  "agent_execution_plan": {{
    "phases": [
      {{
        "id": "intake",
        "owner": "main_agent",
        "trigger": "missing high-leverage personalization choices",
        "commands": ["python3 scripts/emit_deck_start_packet.py --workspace <deck> --user-prompt '<request>'"],
        "writes": ["intake_answers.json", "design_brief.json:user_intake"],
        "continue_when": "answers or explicit assumptions are persisted"
      }},
      {{
        "id": "design_contract",
        "owner": "style_scout_or_main_agent",
        "trigger": "before outline authoring",
        "commands": ["python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json"],
        "writes": ["design_contract.json", "design_brief.json", "content_plan.json", "evidence_plan.json", "asset_plan.json", "notes.md"],
        "continue_when": "design_contract_apply_report.json records the contract as applied"
      }},
      {{
        "id": "outline_authoring",
        "owner": "main_agent",
        "trigger": "contract is applied and starter outline remains",
        "commands": ["python3 scripts/emit_outline_authoring_prompt.py --workspace <deck> --output <deck>/build/outline_authoring_prompt.md"],
        "writes": ["outline.json", "content_plan.json", "evidence_plan.json", "asset_plan.json"],
        "continue_when": "planning validation has no blocking errors"
      }}
    ],
    "commands": [
      "python3 scripts/report_workspace_readiness.py --workspace <deck>",
      "python3 scripts/advance_workspace.py --workspace <deck>",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ]
  }},
  "qa_contract": {{
    "required_checks": [
      "python3 scripts/validate_planning.py --workspace <deck>",
      "python3 scripts/preflight.py --outline <deck>/outline.json --design-brief <deck>/design_brief.json",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ],
    "fail_on": ["planning errors", "overflow", "overlap", "undersized text", "awkward whitespace", "visual review blockers"],
    "visual_risks_to_check": [],
    "placeholder_checks": true,
    "acceptance_evidence": [
      "build/workspace_readiness.json",
      "build/build_workspace_report.json",
      "build/qa/report.json",
      "build/delivery_readiness.json"
    ]
  }},
  "acceptance_evidence": [
    "design_contract_apply_report.json proves the returned contract was applied",
    "build/workspace_readiness.json proves source planning is clean or names the next source edit",
    "build/build_workspace_report.json fingerprints sources, artifacts, QA reports, and output PPTX",
    "build/delivery_readiness.json records final delivery status and blocking reasons"
  ],
  "authoring_instructions": [
    "Use style_system.style_seed={style_seed!r} unless the user explicitly supplied a different seed, and record any override in notes.md.",
    "specific instruction the main agent must follow when writing design_brief.json and outline.json"
  ]
}}
"""


def render_contract_prompt(*, user_prompt: str, workspace: Path | None) -> str:
    stable_id = _stable_id(user_prompt)
    return PROMPT_TEMPLATE.format(
        user_prompt=user_prompt.strip(),
        stable_id=stable_id,
        style_seed=stable_id,
        workspace_context=_workspace_context(workspace),
        workspace_source_inventory=_compact_json(_workspace_source_inventory(workspace), limit=3500),
        reference_context=_reference_context(),
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit a reproducible deck design-contract prompt.")
    parser.add_argument("--user-prompt", required=True, help="Original user deck request")
    parser.add_argument("--workspace", default="", help="Optional deck workspace directory")
    parser.add_argument("--output", default="", help="Optional path to write the prompt")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace) if args.workspace else None
    prompt = render_contract_prompt(user_prompt=args.user_prompt, workspace=workspace)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt, encoding="utf-8")
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
