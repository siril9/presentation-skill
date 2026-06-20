#!/usr/bin/env python3
"""Advance a deck workspace from delivery readiness to the next handoff."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _workspace_path(workspace: Path, raw: str) -> Path:
    path = Path(str(raw or "")).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


def _display_path(workspace: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(workspace))
    except ValueError:
        return str(path.resolve())


def _write_text_if_changed(path: Path, text: str) -> bool:
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _write_json_if_changed(path: Path, payload: Any) -> bool:
    return _write_text_if_changed(path, json.dumps(payload, indent=2) + "\n")


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _command_text(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(item) for item in command)
    return str(command or "").strip()


def _markdown_list(value: Any, *, empty: str = "none") -> str:
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(items) if items else empty
    text = str(value or "").strip()
    return text or empty


def _limited_markdown_list(value: Any, *, limit: int = 6, empty: str = "none") -> str:
    if not isinstance(value, list):
        return empty
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        return empty
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_speed_summary(report: dict[str, Any]) -> dict[str, Any]:
    build = report.get("build") if isinstance(report.get("build"), dict) else {}
    speed = build.get("speed") if isinstance(build.get("speed"), dict) else {}
    if not speed:
        return {}
    return {
        "schema": str(speed.get("schema") or "").strip(),
        "total_duration_ms": _int_value(speed.get("total_duration_ms")),
        "step_count": _int_value(speed.get("step_count")),
        "renderer_used": str(speed.get("renderer_used") or "").strip(),
        "fast_first_pass": bool(speed.get("fast_first_pass")),
        "skip_render": bool(speed.get("skip_render")),
        "visual_review": bool(speed.get("visual_review")),
        "longest_step": speed.get("longest_step") if isinstance(speed.get("longest_step"), dict) else {},
        "step_durations_ms": (
            speed.get("step_durations_ms")
            if isinstance(speed.get("step_durations_ms"), dict)
            else {}
        ),
    }


def _build_speed_line(report: dict[str, Any], *, label: str = "Build speed") -> str:
    speed = _build_speed_summary(report)
    if not speed:
        return f"- {label}: `none`"
    longest = speed.get("longest_step") if isinstance(speed.get("longest_step"), dict) else {}
    steps = speed.get("step_durations_ms") if isinstance(speed.get("step_durations_ms"), dict) else {}
    return (
        f"- {label}: "
        f"total_ms=`{_int_value(speed.get('total_duration_ms'))}` "
        f"steps=`{_int_value(speed.get('step_count'))}` "
        f"renderer=`{speed.get('renderer_used') or 'none'}` "
        f"fast_first_pass=`{bool(speed.get('fast_first_pass'))}` "
        f"skip_render=`{bool(speed.get('skip_render'))}` "
        f"visual_review=`{bool(speed.get('visual_review'))}` "
        f"longest=`{longest.get('step') or 'none'}:{_int_value(longest.get('duration_ms'))}` "
        f"render_ms=`{_int_value(steps.get('render_deck'))}` "
        f"qa_ms=`{_int_value(steps.get('qa'))}`"
    )


def _scout_analysis_lines(label: str, scout: Any) -> list[str]:
    if not isinstance(scout, dict) or not scout:
        return []
    return [
        f"- {label}: "
        f"present=`{bool(scout.get('present'))}` "
        f"persisted=`{bool(scout.get('persisted'))}` "
        f"applied=`{bool(scout.get('applied'))}` "
        f"tasks=`{_int_value(scout.get('analysis_task_count'))}` "
        f"findings=`{_int_value(scout.get('computed_finding_count'))}` "
        f"visuals=`{_int_value(scout.get('visual_recommendation_count'))}` "
        f"bindings=`{_int_value(scout.get('outline_binding_count'))}` "
        f"targets=`{_limited_markdown_list(scout.get('target_slide_ids'), limit=4)}` "
        f"variants=`{_limited_markdown_list(scout.get('variants'), limit=4)}` "
        f"open_questions=`{_int_value(scout.get('open_question_count'))}`"
    ]


def _phase_proof_summary(report: dict[str, Any]) -> dict[str, Any]:
    proof = (
        report.get("phase_proof_ledger")
        if isinstance(report.get("phase_proof_ledger"), dict)
        else {}
    )
    if not proof:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        proof = (
            readiness.get("phase_proof_ledger")
            if isinstance(readiness.get("phase_proof_ledger"), dict)
            else {}
        )
    if not proof:
        return {}
    return {
        "exists": bool(proof.get("exists")),
        "valid": bool(proof.get("valid")),
        "ledger_version": str(proof.get("ledger_version") or "").strip(),
        "plan_version": str(proof.get("plan_version") or "").strip(),
        "phase_count": _int_value(proof.get("phase_count")),
        "phase_ids": proof.get("phase_ids", []) if isinstance(proof.get("phase_ids"), list) else [],
        "route_required_phase_ids": (
            proof.get("route_required_phase_ids", [])
            if isinstance(proof.get("route_required_phase_ids"), list)
            else []
        ),
        "acceptance_gate_ids": (
            proof.get("acceptance_gate_ids", [])
            if isinstance(proof.get("acceptance_gate_ids"), list)
            else []
        ),
        "acceptance_gate_count": _int_value(proof.get("acceptance_gate_count")),
        "proof_path_count": _int_value(proof.get("proof_path_count")),
        "proof_file_count": _int_value(proof.get("proof_file_count")),
        "existing_file_count": _int_value(proof.get("existing_file_count")),
        "missing_file_count": _int_value(proof.get("missing_file_count")),
        "missing_files": (
            proof.get("missing_files", [])
            if isinstance(proof.get("missing_files"), list)
            else []
        ),
        "phase_count_matches_execution_plan": bool(
            proof.get("phase_count_matches_execution_plan")
        ),
        "source": str(proof.get("source") or "").strip(),
    }


def _phase_proof_line(report: dict[str, Any]) -> str:
    proof = _phase_proof_summary(report)
    if not proof:
        return "- Phase proof ledger: `none`"
    return (
        "- Phase proof ledger: "
        f"`{proof.get('ledger_version', '') or 'none'}` "
        f"valid=`{bool(proof.get('valid'))}` "
        f"gates=`{proof.get('acceptance_gate_count', 0)}` "
        f"proof_paths=`{proof.get('proof_path_count', 0)}` "
        f"files=`{proof.get('existing_file_count', 0)}/{proof.get('proof_file_count', 0)}` "
        f"missing=`{proof.get('missing_file_count', 0)}` "
        f"route_required=`{_markdown_list(proof.get('route_required_phase_ids'))}` "
        f"source=`{proof.get('source', '') or 'none'}`"
    )


def _workspace_source_inventory_summary(report: dict[str, Any]) -> dict[str, Any]:
    inventory = (
        report.get("workspace_source_inventory")
        if isinstance(report.get("workspace_source_inventory"), dict)
        else {}
    )
    if not inventory:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        inventory = (
            readiness.get("workspace_source_inventory")
            if isinstance(readiness.get("workspace_source_inventory"), dict)
            else {}
        )
    if not inventory:
        return {}
    return {
        "exists": bool(inventory.get("exists")),
        "source": str(inventory.get("source") or "").strip(),
        "data_file_count": _int_value(inventory.get("data_file_count")),
        "data_file_shown_count": _int_value(inventory.get("data_file_shown_count")),
        "reference_pptx_count": _int_value(inventory.get("reference_pptx_count")),
        "reference_pptx_shown_count": _int_value(inventory.get("reference_pptx_shown_count")),
        "artifact_ledger_count": _int_value(inventory.get("artifact_ledger_count")),
        "data_paths": (
            inventory.get("data_paths", [])
            if isinstance(inventory.get("data_paths"), list)
            else []
        ),
        "reference_pptx_paths": (
            inventory.get("reference_pptx_paths", [])
            if isinstance(inventory.get("reference_pptx_paths"), list)
            else []
        ),
        "artifact_ledger_paths": (
            inventory.get("artifact_ledger_paths", [])
            if isinstance(inventory.get("artifact_ledger_paths"), list)
            else []
        ),
    }


def _source_inventory_lines(report: dict[str, Any]) -> list[str]:
    inventory = _workspace_source_inventory_summary(report)
    if not inventory or not inventory.get("exists"):
        return ["- Source inventory: `none`"]
    lines = [
        "- Source inventory: "
        f"data=`{int(inventory.get('data_file_count') or 0)}` "
        f"reference_pptx=`{int(inventory.get('reference_pptx_count') or 0)}` "
        f"artifact_ledgers=`{int(inventory.get('artifact_ledger_count') or 0)}` "
        f"source=`{inventory.get('source') or 'none'}`"
    ]
    for key, label in (
        ("data_paths", "Source data paths"),
        ("reference_pptx_paths", "Reference PPTX paths"),
        ("artifact_ledger_paths", "Artifact ledger paths"),
    ):
        paths = inventory.get(key)
        if isinstance(paths, list) and paths:
            lines.append(f"- {label}: `{_limited_markdown_list(paths, limit=6)}`")
    return lines


def _resolved_treatment_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = (
        report.get("resolved_treatment_summary")
        if isinstance(report.get("resolved_treatment_summary"), dict)
        else {}
    )
    if not summary:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        summary = (
            readiness.get("resolved_treatment_summary")
            if isinstance(readiness.get("resolved_treatment_summary"), dict)
            else {}
        )
    if not summary:
        return {}
    return {
        "header_variant_by_slide": (
            summary.get("header_variant_by_slide", [])
            if isinstance(summary.get("header_variant_by_slide"), list)
            else []
        ),
        "header_variant_counts": (
            summary.get("header_variant_counts", {})
            if isinstance(summary.get("header_variant_counts"), dict)
            else {}
        ),
        "unique_header_variant_count": _int_value(summary.get("unique_header_variant_count")),
    }


def _resolved_treatment_lines(report: dict[str, Any]) -> list[str]:
    summary = _resolved_treatment_summary(report)
    if not summary:
        return ["- Resolved header variants: `none`"]
    counts = summary.get("header_variant_counts")
    counts_text = json.dumps(counts, sort_keys=True) if isinstance(counts, dict) else "{}"
    return [
        "- Resolved header variants: "
        f"unique=`{int(summary.get('unique_header_variant_count') or 0)}` "
        f"counts=`{counts_text}`"
    ]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _reproducibility_contract_summary(report: dict[str, Any]) -> dict[str, Any]:
    replay = (
        report.get("reproducibility_contract")
        if isinstance(report.get("reproducibility_contract"), dict)
        else {}
    )
    if not replay:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        replay = (
            readiness.get("reproducibility_contract")
            if isinstance(readiness.get("reproducibility_contract"), dict)
            else {}
        )
    if not replay:
        return {}
    style_replay = replay.get("style_replay") if isinstance(replay.get("style_replay"), dict) else {}
    structure_replay = (
        replay.get("structure_replay") if isinstance(replay.get("structure_replay"), dict) else {}
    )
    artifact_replay = (
        replay.get("artifact_replay") if isinstance(replay.get("artifact_replay"), dict) else {}
    )
    return {
        "exists": bool(replay.get("exists")),
        "contract_version": str(replay.get("contract_version") or "").strip(),
        "stable_prompt_id": str(replay.get("stable_prompt_id") or "").strip(),
        "style_seed": str(replay.get("style_seed") or "").strip(),
        "renderer": str(replay.get("renderer") or "").strip(),
        "locked_design_field_count": _int_value(replay.get("locked_design_field_count")),
        "locked_design_fields": _string_list(replay.get("locked_design_fields")),
        "replay_command_count": _int_value(replay.get("replay_command_count")),
        "replay_commands": _string_list(replay.get("replay_commands")),
        "style_replay": {
            "style_preset": str(style_replay.get("style_preset") or "").strip(),
            "background_system": str(style_replay.get("background_system") or "").strip(),
            "header_variant_pool": _string_list(style_replay.get("header_variant_pool")),
            "footer_pool": _string_list(style_replay.get("footer_pool")),
            "chart_treatment_pool": _string_list(style_replay.get("chart_treatment_pool")),
            "figure_table_treatment_pool": _string_list(
                style_replay.get("figure_table_treatment_pool")
            ),
            "mix_rule": str(style_replay.get("mix_rule") or "").strip(),
        },
        "structure_replay": {
            "target_slide_count": structure_replay.get("target_slide_count"),
            "slide_variant_mix": _string_list(structure_replay.get("slide_variant_mix")),
        },
        "artifact_replay": {
            "local_data_needed": artifact_replay.get("local_data_needed"),
            "artifact_manifest": str(artifact_replay.get("artifact_manifest") or "").strip(),
            "analysis_summary": str(artifact_replay.get("analysis_summary") or "").strip(),
            "figure_script": str(artifact_replay.get("figure_script") or "").strip(),
            "rebuild_commands": _string_list(artifact_replay.get("rebuild_commands")),
        },
    }


def _reproducibility_contract_lines(report: dict[str, Any]) -> list[str]:
    replay = _reproducibility_contract_summary(report)
    if not replay:
        return ["- Replay contract: `none`"]
    style_replay = replay.get("style_replay") if isinstance(replay.get("style_replay"), dict) else {}
    structure_replay = (
        replay.get("structure_replay") if isinstance(replay.get("structure_replay"), dict) else {}
    )
    artifact_replay = (
        replay.get("artifact_replay") if isinstance(replay.get("artifact_replay"), dict) else {}
    )
    lines = [
        "- Replay contract: "
        f"`{replay.get('contract_version') or 'none'}` "
        f"exists=`{bool(replay.get('exists'))}` "
        f"seed=`{replay.get('style_seed') or 'none'}` "
        f"renderer=`{replay.get('renderer') or 'none'}` "
        f"commands=`{int(replay.get('replay_command_count') or 0)}` "
        f"locked_fields=`{int(replay.get('locked_design_field_count') or 0)}`",
    ]
    if style_replay:
        lines.append(
            "- Replay style: "
            f"preset=`{style_replay.get('style_preset') or 'none'}` "
            f"background=`{style_replay.get('background_system') or 'none'}` "
            f"headers=`{_limited_markdown_list(style_replay.get('header_variant_pool'))}` "
            f"charts=`{_limited_markdown_list(style_replay.get('chart_treatment_pool'))}` "
            f"figures=`{_limited_markdown_list(style_replay.get('figure_table_treatment_pool'))}`"
        )
    if structure_replay:
        lines.append(
            "- Replay structure: "
            f"slides=`{structure_replay.get('target_slide_count') or 0}` "
            f"variants=`{_limited_markdown_list(structure_replay.get('slide_variant_mix'))}`"
        )
    if artifact_replay:
        lines.append(
            "- Replay artifacts: "
            f"manifest=`{artifact_replay.get('artifact_manifest') or 'none'}` "
            f"summary=`{artifact_replay.get('analysis_summary') or 'none'}` "
            f"script=`{artifact_replay.get('figure_script') or 'none'}`"
        )
    return lines


def _quality_context_summary(report: dict[str, Any]) -> dict[str, Any]:
    quality = (
        report.get("quality_context")
        if isinstance(report.get("quality_context"), dict)
        else {}
    )
    if not quality:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        quality = (
            readiness.get("quality_context")
            if isinstance(readiness.get("quality_context"), dict)
            else {}
        )
    if not quality:
        return {}
    slide_quality = (
        quality.get("slide_quality_contract")
        if isinstance(quality.get("slide_quality_contract"), dict)
        else {}
    )
    outline_quality = (
        quality.get("outline_quality_alignment")
        if isinstance(quality.get("outline_quality_alignment"), dict)
        else {}
    )
    return {
        "slide_quality_contract": {
            "exists": bool(slide_quality.get("exists")),
            "contract_version": str(slide_quality.get("contract_version") or "").strip(),
            "min_title_pt": slide_quality.get("min_title_pt"),
            "min_body_pt": slide_quality.get("min_body_pt"),
            "chart_label_min_pt": slide_quality.get("chart_label_min_pt"),
            "footer_reserved_inches": slide_quality.get("footer_reserved_inches"),
            "evidence_anchor_required": bool(slide_quality.get("evidence_anchor_required")),
            "fail_on_awkward_whitespace": bool(slide_quality.get("fail_on_awkward_whitespace")),
            "required_command_count": _int_value(slide_quality.get("required_command_count")),
        },
        "outline_quality_alignment": {
            "present": bool(outline_quality.get("present")),
            "persisted": bool(outline_quality.get("persisted")),
            "contract_version": str(outline_quality.get("contract_version") or "").strip(),
            "readability_target_count": _int_value(outline_quality.get("readability_target_count")),
            "layout_target_count": _int_value(outline_quality.get("layout_target_count")),
            "qa_gate_count": _int_value(outline_quality.get("qa_gate_count")),
            "required_command_count": _int_value(outline_quality.get("required_command_count")),
            "readability_targets_used": _string_list(outline_quality.get("readability_targets_used")),
            "layout_targets_used": _string_list(outline_quality.get("layout_targets_used")),
            "qa_gates_used": _string_list(outline_quality.get("qa_gates_used")),
        },
    }


def _quality_context_lines(report: dict[str, Any]) -> list[str]:
    quality = _quality_context_summary(report)
    if not quality:
        return ["- Quality context: `none`"]
    slide_quality = (
        quality.get("slide_quality_contract")
        if isinstance(quality.get("slide_quality_contract"), dict)
        else {}
    )
    outline_quality = (
        quality.get("outline_quality_alignment")
        if isinstance(quality.get("outline_quality_alignment"), dict)
        else {}
    )
    lines: list[str] = []
    if slide_quality:
        lines.append(
            "- Slide quality contract: "
            f"`{slide_quality.get('contract_version') or 'none'}` "
            f"exists=`{bool(slide_quality.get('exists'))}` "
            f"title=`{slide_quality.get('min_title_pt')}` "
            f"body=`{slide_quality.get('min_body_pt')}` "
            f"chart=`{slide_quality.get('chart_label_min_pt')}` "
            f"footer=`{slide_quality.get('footer_reserved_inches')}` "
            f"whitespace=`{bool(slide_quality.get('fail_on_awkward_whitespace'))}` "
            f"evidence_anchor=`{bool(slide_quality.get('evidence_anchor_required'))}` "
            f"commands=`{int(slide_quality.get('required_command_count') or 0)}`"
        )
    if outline_quality:
        lines.append(
            "- Outline quality alignment: "
            f"`{outline_quality.get('contract_version') or 'none'}` "
            f"present=`{bool(outline_quality.get('present'))}` "
            f"persisted=`{bool(outline_quality.get('persisted'))}` "
            f"readability=`{int(outline_quality.get('readability_target_count') or 0)}` "
            f"layout=`{int(outline_quality.get('layout_target_count') or 0)}` "
            f"qa=`{int(outline_quality.get('qa_gate_count') or 0)}` "
            f"commands=`{int(outline_quality.get('required_command_count') or 0)}`"
        )
    return lines or ["- Quality context: `none`"]


def _layout_density_summary(report: dict[str, Any]) -> dict[str, Any]:
    density = (
        report.get("layout_density")
        if isinstance(report.get("layout_density"), dict)
        else {}
    )
    if not density:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        density = (
            readiness.get("layout_density")
            if isinstance(readiness.get("layout_density"), dict)
            else {}
        )
    if not density:
        build = report.get("build") if isinstance(report.get("build"), dict) else {}
        density = (
            build.get("layout_density")
            if isinstance(build.get("layout_density"), dict)
            else {}
        )
    if not density:
        return {}
    low_slides = (
        density.get("low_content_density_slides")
        if isinstance(density.get("low_content_density_slides"), list)
        else []
    )
    score_by_slide = (
        density.get("density_score_by_slide")
        if isinstance(density.get("density_score_by_slide"), list)
        else []
    )
    return {
        "exists": bool(density.get("exists")),
        "source": str(density.get("source") or "").strip(),
        "slide_count": _int_value(density.get("slide_count")),
        "content_slide_count": _int_value(density.get("content_slide_count")),
        "content_density_floor": density.get("content_density_floor"),
        "min_content_density_score": density.get("min_content_density_score"),
        "average_content_density_score": density.get("average_content_density_score"),
        "max_content_density_score": density.get("max_content_density_score"),
        "low_content_density_count": _int_value(density.get("low_content_density_count")),
        "low_content_density_slides": [item for item in low_slides if isinstance(item, dict)],
        "density_score_by_slide": [item for item in score_by_slide if isinstance(item, dict)],
    }


def _layout_density_lines(report: dict[str, Any]) -> list[str]:
    density = _layout_density_summary(report)
    if not density or not density.get("exists"):
        return ["- Layout density: `none`"]
    lines = [
        "- Layout density: "
        f"slides=`{int(density.get('slide_count') or 0)}` "
        f"content=`{int(density.get('content_slide_count') or 0)}` "
        f"min=`{density.get('min_content_density_score')}` "
        f"avg=`{density.get('average_content_density_score')}` "
        f"max=`{density.get('max_content_density_score')}` "
        f"floor=`{density.get('content_density_floor')}` "
        f"low=`{int(density.get('low_content_density_count') or 0)}` "
        f"source=`{density.get('source') or 'none'}`"
    ]
    low = (
        density.get("low_content_density_slides")
        if isinstance(density.get("low_content_density_slides"), list)
        else []
    )
    if low:
        low_text = ", ".join(
            f"{int(item.get('slide_index'))}:{item.get('density_score')}"
            for item in low[:8]
            if isinstance(item, dict) and isinstance(item.get("slide_index"), int)
        )
        suffix = f", +{len(low) - 8} more" if len(low) > 8 else ""
        lines.append(f"- Low-density content slides: `{low_text}{suffix}`")
    return lines


def _data_handoff_summary(report: dict[str, Any]) -> dict[str, Any]:
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    handoff = (
        readiness.get("data_analysis_handoff")
        if isinstance(readiness.get("data_analysis_handoff"), dict)
        else {}
    )
    if not handoff:
        return {}
    ledger = (
        handoff.get("applied_ledger")
        if isinstance(handoff.get("applied_ledger"), dict)
        else {}
    )
    compact: dict[str, Any] = {
        "status": handoff.get("status"),
        "applied": bool(handoff.get("applied")),
        "selection_count": handoff.get("selection_count"),
        "selection_binding_count": handoff.get("selection_binding_count"),
        "binding_count": handoff.get("binding_count"),
        "bound_output_ids": handoff.get("bound_output_ids", []),
        "slide_ids": handoff.get("slide_ids", []),
        "variants": handoff.get("variants", []),
        "script_edit_count": handoff.get("script_edit_count"),
        "artifact_rebuild_context": handoff.get("artifact_rebuild_context", {}),
        "artifact_contracts": handoff.get("artifact_contracts", {}),
        "scout_analysis": handoff.get("scout_analysis", {}),
        "artifact_storyboard": handoff.get("artifact_storyboard", {}),
    }
    if ledger:
        compact["applied_ledger"] = {
            key: ledger.get(key, [])
            for key in (
                "bound_output_ids",
                "slide_ids",
                "variants",
                "evidence_ids",
                "script_edit_paths",
                "source_checks",
                "build_checks",
                "verification_evidence",
                "commands_to_run",
            )
        }
    return compact


def _build_data_handoff_summary(report: dict[str, Any]) -> dict[str, Any]:
    build = report.get("build") if isinstance(report.get("build"), dict) else {}
    handoff = (
        build.get("data_analysis_handoff")
        if isinstance(build.get("data_analysis_handoff"), dict)
        else {}
    )
    if not handoff:
        return {}
    ledger = (
        handoff.get("applied_ledger")
        if isinstance(handoff.get("applied_ledger"), dict)
        else {}
    )
    compact: dict[str, Any] = {
        "status": handoff.get("status"),
        "applied": bool(handoff.get("applied")),
        "selection_count": handoff.get("selection_count"),
        "selection_binding_count": handoff.get("selection_binding_count"),
        "binding_count": handoff.get("binding_count"),
        "bound_output_ids": handoff.get("bound_output_ids", []),
        "slide_ids": handoff.get("slide_ids", []),
        "variants": handoff.get("variants", []),
        "script_edit_count": handoff.get("script_edit_count"),
        "artifact_rebuild_context": handoff.get("artifact_rebuild_context", {}),
        "artifact_contracts": handoff.get("artifact_contracts", {}),
        "scout_analysis": handoff.get("scout_analysis", {}),
        "artifact_storyboard": handoff.get("artifact_storyboard", {}),
    }
    if ledger:
        compact["applied_ledger"] = {
            key: ledger.get(key, [])
            for key in (
                "bound_output_ids",
                "slide_ids",
                "variants",
                "evidence_ids",
                "script_edit_paths",
                "source_checks",
                "build_checks",
                "verification_evidence",
                "commands_to_run",
            )
        }
    return compact


def _data_handoff_lines(report: dict[str, Any]) -> list[str]:
    handoff = _data_handoff_summary(report)
    if not handoff:
        return ["- Data handoff: `none`"]
    lines = [
        "- Data handoff: "
        f"status=`{handoff.get('status') or 'none'}` "
        f"applied=`{bool(handoff.get('applied'))}` "
        f"selections=`{handoff.get('selection_count') or 0}`"
    ]
    rebuild = (
        handoff.get("artifact_rebuild_context")
        if isinstance(handoff.get("artifact_rebuild_context"), dict)
        else {}
    )
    if rebuild:
        lines.append(
            "- Data artifact rebuild: "
            f"present=`{bool(rebuild.get('present'))}` "
            f"persisted=`{bool(rebuild.get('persisted'))}` "
            f"context=`{rebuild.get('context_version', '')}` "
            f"commands=`{rebuild.get('command_count', 0)}`"
        )
    contracts = (
        handoff.get("artifact_contracts")
        if isinstance(handoff.get("artifact_contracts"), dict)
        else {}
    )
    if contracts:
        asset_counts = contracts.get("asset_plan_update_counts")
        asset_counts = asset_counts if isinstance(asset_counts, dict) else {}
        lines.append(
            "- Data artifact contracts: "
            f"figure_export=`{bool(contracts.get('figure_export_contract_applied'))}` "
            f"figure_outputs=`{int(contracts.get('figure_export_output_count') or 0)}` "
            f"registry_updates=`{int(contracts.get('artifact_registry_update_count') or 0)}` "
            f"asset_updates=`{json.dumps(asset_counts, sort_keys=True)}`"
        )
    lines.extend(_scout_analysis_lines("Data scout analysis", handoff.get("scout_analysis")))
    storyboard = (
        handoff.get("artifact_storyboard")
        if isinstance(handoff.get("artifact_storyboard"), dict)
        else {}
    )
    if int(storyboard.get("item_count") or 0):
        lines.append(
            "- Data handoff storyboard: "
            f"items=`{int(storyboard.get('item_count') or 0)}` "
            f"slides=`{_limited_markdown_list(storyboard.get('slide_ids'))}` "
            f"outputs=`{_limited_markdown_list(storyboard.get('output_ids'))}` "
            f"roles=`{_limited_markdown_list(storyboard.get('artifact_roles'))}` "
            f"sources=`{_limited_markdown_list(storyboard.get('data_source_paths'), limit=3)}`"
        )
    ledger = (
        handoff.get("applied_ledger")
        if isinstance(handoff.get("applied_ledger"), dict)
        else {}
    )
    if not ledger:
        return lines
    lines.append(
        "- Data handoff ledger: "
        f"outputs=`{_limited_markdown_list(ledger.get('bound_output_ids'))}` "
        f"slides=`{_limited_markdown_list(ledger.get('slide_ids'))}` "
        f"variants=`{_limited_markdown_list(ledger.get('variants'))}` "
        f"evidence=`{_limited_markdown_list(ledger.get('evidence_ids'))}`"
    )
    scripts = _limited_markdown_list(ledger.get("script_edit_paths"))
    source_checks = _limited_markdown_list(ledger.get("source_checks"), limit=3)
    build_checks = _limited_markdown_list(ledger.get("build_checks"), limit=3)
    if scripts != "none" or source_checks != "none" or build_checks != "none":
        lines.append(
            "- Data handoff scripts/checks: "
            f"scripts=`{scripts}` source_checks=`{source_checks}` build_checks=`{build_checks}`"
        )
    verification = _limited_markdown_list(ledger.get("verification_evidence"), limit=4)
    commands = _limited_markdown_list(ledger.get("commands_to_run"), limit=3)
    if verification != "none" or commands != "none":
        lines.append(
            "- Data handoff verification: "
            f"evidence=`{verification}` commands=`{commands}`"
        )
    return lines


def _build_data_handoff_lines(report: dict[str, Any]) -> list[str]:
    handoff = _build_data_handoff_summary(report)
    if not handoff:
        return ["- Build data handoff: `none`"]
    lines = [
        "- Build data handoff: "
        f"status=`{handoff.get('status') or 'none'}` "
        f"applied=`{bool(handoff.get('applied'))}` "
        f"selections=`{handoff.get('selection_count') or 0}`"
    ]
    rebuild = (
        handoff.get("artifact_rebuild_context")
        if isinstance(handoff.get("artifact_rebuild_context"), dict)
        else {}
    )
    if rebuild:
        lines.append(
            "- Build data artifact rebuild: "
            f"present=`{bool(rebuild.get('present'))}` "
            f"context=`{rebuild.get('context_version', '')}` "
            f"commands=`{rebuild.get('command_count', 0)}`"
        )
    contracts = (
        handoff.get("artifact_contracts")
        if isinstance(handoff.get("artifact_contracts"), dict)
        else {}
    )
    if contracts:
        asset_counts = contracts.get("asset_plan_update_counts")
        asset_counts = asset_counts if isinstance(asset_counts, dict) else {}
        lines.append(
            "- Build data artifact contracts: "
            f"figure_export=`{bool(contracts.get('figure_export_contract_applied'))}` "
            f"figure_outputs=`{int(contracts.get('figure_export_output_count') or 0)}` "
            f"registry_updates=`{int(contracts.get('artifact_registry_update_count') or 0)}` "
            f"asset_updates=`{json.dumps(asset_counts, sort_keys=True)}`"
        )
    lines.extend(_scout_analysis_lines("Build data scout analysis", handoff.get("scout_analysis")))
    storyboard = (
        handoff.get("artifact_storyboard")
        if isinstance(handoff.get("artifact_storyboard"), dict)
        else {}
    )
    if int(storyboard.get("item_count") or 0):
        lines.append(
            "- Build data handoff storyboard: "
            f"items=`{int(storyboard.get('item_count') or 0)}` "
            f"slides=`{_limited_markdown_list(storyboard.get('slide_ids'))}` "
            f"outputs=`{_limited_markdown_list(storyboard.get('output_ids'))}` "
            f"roles=`{_limited_markdown_list(storyboard.get('artifact_roles'))}` "
            f"sources=`{_limited_markdown_list(storyboard.get('data_source_paths'), limit=3)}`"
        )
    ledger = (
        handoff.get("applied_ledger")
        if isinstance(handoff.get("applied_ledger"), dict)
        else {}
    )
    if not ledger:
        return lines
    lines.append(
        "- Build data handoff ledger: "
        f"outputs=`{_limited_markdown_list(ledger.get('bound_output_ids'))}` "
        f"slides=`{_limited_markdown_list(ledger.get('slide_ids'))}` "
        f"variants=`{_limited_markdown_list(ledger.get('variants'))}` "
        f"evidence=`{_limited_markdown_list(ledger.get('evidence_ids'))}`"
    )
    scripts = _limited_markdown_list(ledger.get("script_edit_paths"))
    source_checks = _limited_markdown_list(ledger.get("source_checks"), limit=3)
    build_checks = _limited_markdown_list(ledger.get("build_checks"), limit=3)
    if scripts != "none" or source_checks != "none" or build_checks != "none":
        lines.append(
            "- Build data handoff scripts/checks: "
            f"scripts=`{scripts}` source_checks=`{source_checks}` build_checks=`{build_checks}`"
        )
    verification = _limited_markdown_list(ledger.get("verification_evidence"), limit=4)
    commands = _limited_markdown_list(ledger.get("commands_to_run"), limit=3)
    if verification != "none" or commands != "none":
        lines.append(
            "- Build data handoff verification: "
            f"evidence=`{verification}` commands=`{commands}`"
        )
    return lines


def _artifact_context_summary(report: dict[str, Any]) -> dict[str, Any]:
    context = (
        report.get("artifact_context")
        if isinstance(report.get("artifact_context"), dict)
        else {}
    )
    if not context:
        readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
        context = (
            readiness.get("artifact_context")
            if isinstance(readiness.get("artifact_context"), dict)
            else {}
        )
    return context if isinstance(context, dict) else {}


def _artifact_context_lines(report: dict[str, Any]) -> list[str]:
    context = _artifact_context_summary(report)
    if not context:
        return ["- Artifact manifest: `none`"]
    manifest = (
        context.get("artifact_manifest")
        if isinstance(context.get("artifact_manifest"), dict)
        else {}
    )
    selection = (
        context.get("artifact_selection")
        if isinstance(context.get("artifact_selection"), dict)
        else {}
    )
    lines: list[str] = []
    if manifest:
        lines.append(
            "- Artifact manifest: "
            f"`{manifest.get('path') or 'none'}` "
            f"exists=`{bool(manifest.get('exists'))}` "
            f"valid=`{bool(manifest.get('valid'))}` "
            f"outputs=`{int(manifest.get('output_count') or 0)}` "
            f"templates=`{int(manifest.get('selection_template_count') or 0)}`"
        )
        analysis_summary = str(manifest.get("analysis_summary") or "").strip()
        analysis_markdown = str(manifest.get("analysis_summary_markdown") or "").strip()
        if analysis_summary or analysis_markdown:
            lines.append(
                "- Analysis summary: "
                f"json=`{analysis_summary or 'none'}` md=`{analysis_markdown or 'none'}`"
            )
        output_ids = manifest.get("output_ids")
        if isinstance(output_ids, list) and output_ids:
            lines.append(f"- Artifact outputs: `{_limited_markdown_list(output_ids, limit=8)}`")
        quality_counts = manifest.get("figure_quality_counts")
        if isinstance(quality_counts, dict) and quality_counts:
            quality_text = ", ".join(
                f"{str(key)}={int(value)}"
                for key, value in sorted(quality_counts.items())
                if isinstance(value, int) and not isinstance(value, bool)
            )
            if quality_text:
                lines.append(f"- Figure quality: `{quality_text}`")
        aliases = manifest.get("aliases") if isinstance(manifest.get("aliases"), list) else []
        if aliases:
            lines.append(f"- Artifact aliases: `{len(aliases)}`")
            for alias in aliases[:6]:
                if not isinstance(alias, dict):
                    continue
                output_id = str(alias.get("id") or "").strip() or "unknown"
                alias_values = [
                    str(alias.get(key) or "").strip()
                    for key in ("image_alias", "chart_alias", "table_alias")
                    if str(alias.get(key) or "").strip()
                ]
                detail: list[str] = []
                title = str(alias.get("title") or "").strip()
                source = str(alias.get("source_path") or "").strip()
                if title:
                    detail.append(f"title=`{title}`")
                if source:
                    detail.append(f"source=`{source}`")
                figure_quality = (
                    alias.get("figure_quality")
                    if isinstance(alias.get("figure_quality"), dict)
                    else {}
                )
                quality_status = str(figure_quality.get("status") or "").strip()
                exterior_percent = figure_quality.get("exterior_percent")
                if quality_status:
                    if isinstance(exterior_percent, (int, float)) and not isinstance(exterior_percent, bool):
                        detail.append(
                            f"figure_quality=`{quality_status}:{float(exterior_percent):.1f}% exterior`"
                        )
                    else:
                        detail.append(f"figure_quality=`{quality_status}`")
                detail_text = f" {' '.join(detail)}" if detail else ""
                lines.append(
                    f"- Artifact `{output_id}` aliases: "
                    f"`{_markdown_list(alias_values)}`{detail_text}"
                )
            omitted_count = len([item for item in aliases if isinstance(item, dict)]) - 6
            if omitted_count > 0:
                lines.append(f"- Artifact aliases omitted: `{omitted_count}`")
    else:
        lines.append("- Artifact manifest: `none`")
    if selection:
        lines.append(
            "- Bound artifact targets: "
            f"outputs=`{_markdown_list(selection.get('bound_output_ids'))}` "
            f"slides=`{_markdown_list(selection.get('slide_ids'))}` "
            f"variants=`{_markdown_list(selection.get('variants'))}` "
            f"unbound=`{_markdown_list(selection.get('unbound_output_ids'))}`"
        )
    tabular_data = context.get("tabular_data")
    if isinstance(tabular_data, list) and tabular_data:
        lines.append(f"- Tabular data: `{_limited_markdown_list(tabular_data, limit=6)}`")
    return lines or ["- Artifact manifest: `none`"]


def _visual_review_requirement_summary(report: dict[str, Any]) -> dict[str, Any]:
    requirement = (
        report.get("visual_review_requirement")
        if isinstance(report.get("visual_review_requirement"), dict)
        else {}
    )
    if not requirement:
        return {}
    return {
        "required": bool(requirement.get("required")),
        "required_by_cli": bool(requirement.get("required_by_cli")),
        "required_by_route_ledger": bool(requirement.get("required_by_route_ledger")),
        "route_id": str(requirement.get("route_id") or ""),
        "sources": [
            str(item).strip()
            for item in requirement.get("sources", [])
            if str(item).strip()
        ] if isinstance(requirement.get("sources"), list) else [],
        "inactive_sources": [
            str(item).strip()
            for item in requirement.get("inactive_sources", [])
            if str(item).strip()
        ] if isinstance(requirement.get("inactive_sources"), list) else [],
        "run": bool(requirement.get("run")),
        "warning_count": int(requirement.get("warning_count") or 0),
    }


def _visual_review_requirement_line(report: dict[str, Any]) -> str:
    requirement = _visual_review_requirement_summary(report)
    if not requirement:
        return "- Visual review requirement: `none`"
    return (
        "- Visual review requirement: "
        f"required=`{bool(requirement.get('required'))}` "
        f"route_ledger=`{bool(requirement.get('required_by_route_ledger'))}` "
        f"cli=`{bool(requirement.get('required_by_cli'))}` "
        f"run=`{bool(requirement.get('run'))}` "
        f"warnings=`{int(requirement.get('warning_count') or 0)}` "
        f"sources=`{_markdown_list(requirement.get('sources'))}`"
    )


def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    return result.returncode, result.stdout, result.stderr


def _normalize_command(command: Any) -> list[str]:
    if not isinstance(command, list):
        return []
    normalized = [str(item) for item in command]
    if normalized and normalized[0] in {"python", "python3"}:
        normalized[0] = sys.executable
    return normalized


def _run_delivery(
    *,
    repo: Path,
    workspace: Path,
    report_path: Path,
    markdown_path: Path,
    allow_skip_render: bool,
    require_visual_review: bool,
    no_refresh_readiness: bool,
    write_markdown: bool,
) -> tuple[int, dict[str, Any], str]:
    cmd = [
        sys.executable,
        str(repo / "scripts" / "report_delivery_readiness.py"),
        "--workspace",
        str(workspace),
        "--report",
        str(report_path),
    ]
    if write_markdown:
        cmd.extend(["--markdown-report", str(markdown_path)])
    else:
        cmd.append("--skip-markdown")
    if allow_skip_render:
        cmd.append("--allow-skip-render")
    if require_visual_review:
        cmd.append("--require-visual-review")
    if no_refresh_readiness:
        cmd.append("--no-refresh-readiness")
    rc, stdout, stderr = _run(cmd, cwd=repo)
    payload: dict[str, Any] = {}
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    return rc, payload, stderr


def _compact_action(action: Any) -> dict[str, Any]:
    if not isinstance(action, dict):
        return {}
    keep = (
        "kind",
        "priority",
        "action_type",
        "reason",
        "command",
        "slide_ids",
        "planning_paths",
        "suggested_fields",
        "suggested_variants",
        "warning_types",
        "failed_step",
        "returncode",
        "qa_counts",
        "qa_report",
        "design_report",
        "visual_report",
        "visual_review_report",
        "missing_files",
    )
    return {key: action.get(key) for key in keep if key in action}


def _source_edit_plan_lines(plan: list[dict[str, Any]]) -> list[str]:
    if not plan:
        return ["- none"]
    lines: list[str] = []
    for item in plan:
        if not isinstance(item, dict):
            continue
        slide = str(item.get("slide_id") or "").strip()
        slide_text = f" slide `{slide}`" if slide else ""
        lines.append(
            f"- `{item.get('file', '')}` `{item.get('json_path', '')}`{slide_text}: "
            f"`{item.get('operation', '')}`"
        )
        detail_parts: list[str] = []
        for key, label in (
            ("suggested_fields", "fields"),
            ("suggested_variants", "variants"),
            ("rule", "rule"),
            ("role", "role"),
            ("font_pt", "font pt"),
            ("min_allowed_pt", "min pt"),
            ("reserved_inches", "footer reserve in"),
            ("intrusion_inches", "footer intrusion in"),
            ("rows", "rows"),
            ("columns", "columns"),
            ("cell_count", "cells"),
            ("category_count", "categories"),
            ("series_count", "series"),
            ("point_count", "points"),
            ("longest_label_chars", "longest label chars"),
            ("avg_label_chars", "avg label chars"),
            ("header_index", "header index"),
            ("longest_header_chars", "longest header chars"),
            ("long_cell_count", "long cell count"),
            ("avg_cell_chars", "avg cell chars"),
            ("longest_cell_row", "longest cell row"),
            ("longest_cell_column", "longest cell column"),
            ("longest_cell_chars", "longest cell chars"),
            ("text_lines", "text lines"),
            ("text_line_budget", "line budget"),
            ("word_count", "words"),
            ("word_budget", "word budget"),
            ("char_count", "chars"),
            ("char_budget", "char budget"),
            ("estimated_title_lines", "estimated title lines"),
            ("max_title_lines", "max title lines"),
            ("title_font_pt", "title font pt"),
            ("title_width_in", "title width in"),
            ("title_chars", "title chars"),
            ("footer_chars", "footer chars"),
            ("longest_source_chars", "longest source chars"),
            ("source_count", "source count"),
            ("axis_max", "axis max"),
            ("max_value", "max value"),
            ("content_span_height_ratio", "span height ratio"),
            ("content_span_width_ratio", "span width ratio"),
            ("max_vertical_dead_ratio", "vertical dead ratio"),
            ("max_horizontal_dead_ratio", "horizontal dead ratio"),
            ("visual_density_score", "density"),
            ("empty_ratio", "empty ratio"),
            ("delta_inches", "delta in"),
            ("chart_part", "chart part"),
            ("shape_id", "shape"),
            ("planning_path", "planning path"),
            ("artifact_manifest", "artifact manifest"),
            ("artifact_selection", "artifact selection"),
            ("analysis_summary", "analysis summary"),
            ("analysis_summary_markdown", "analysis summary md"),
            ("artifact_output_ids", "artifact outputs"),
            ("unbound_output_ids", "unbound outputs"),
            ("artifact_aliases", "artifact aliases"),
            ("artifact_binding_command", "artifact bind command"),
            ("artifact_manifest_error", "manifest error"),
            ("artifact_selection_error", "selection error"),
            ("stale_artifact_dependency", "stale dependency"),
            ("data_source_fingerprint_index", "data source index"),
            ("data_source_path", "data source"),
            ("data_source_exists", "data source exists"),
            ("data_source_recorded_sha256", "recorded source sha256"),
            ("data_source_current_sha256", "current source sha256"),
            ("data_source_recorded_size_bytes", "recorded source bytes"),
            ("data_source_current_size_bytes", "current source bytes"),
            ("data_source_hash_status", "data source hash status"),
            ("failed_step", "failed step"),
            ("returncode", "return code"),
            ("qa_report", "QA report"),
            ("visual_report", "visual report"),
            ("visual_review_report", "visual review report"),
            ("missing_files", "missing files"),
            ("suggested_fix", "fix"),
        ):
            value = item.get(key)
            text = _markdown_list(value) if isinstance(value, list) else str(value or "").strip()
            if text and text != "none":
                detail_parts.append(f"{label}: {text}")
        if detail_parts:
            lines.append(f"  {'; '.join(detail_parts)}")
    return lines or ["- none"]


def _workspace_source_edit_plan(
    *,
    repo: Path,
    workspace: Path,
    delivery_report: dict[str, Any],
    decision: str,
) -> tuple[list[dict[str, Any]], str]:
    action = (
        delivery_report.get("recommended_next_action")
        if isinstance(delivery_report.get("recommended_next_action"), dict)
        else {}
    )
    if action.get("action_type") == "run_command" or action.get("kind") in {"", "none", None}:
        return [], ""
    if action.get("kind") == "complete_acceptance_evidence":
        return _acceptance_evidence_source_edit_plan(delivery_report), ""
    readiness = (
        delivery_report.get("readiness")
        if isinstance(delivery_report.get("readiness"), dict)
        else {}
    )
    readiness_action = (
        readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    )
    readiness_path_text = str(readiness.get("path") or "").strip()
    if not readiness_path_text:
        return [], "readiness report path unavailable"
    readiness_payload = _load_json(_workspace_path(workspace, readiness_path_text), {})
    if not isinstance(readiness_payload, dict):
        return [], "readiness report JSON unavailable"
    build_report = (
        delivery_report.get("build") if isinstance(delivery_report.get("build"), dict) else {}
    )
    build_path_text = str(build_report.get("path") or "").strip()
    build_payload = _load_json(_workspace_path(workspace, build_path_text), {}) if build_path_text else {}
    if not isinstance(build_payload, dict):
        build_payload = {}
    scripts_dir = str(repo / "scripts")
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    try:
        import advance_workspace  # type: ignore[import-not-found]

        if action.get("kind") == readiness_action.get("kind"):
            plan = advance_workspace._source_edit_plan(readiness_payload, decision=decision)  # noqa: SLF001
        elif action.get("kind") == "inspect_delivery_warnings":
            plan = _delivery_warning_source_edit_plan(
                advance_workspace=advance_workspace,
                workspace=workspace,
                delivery_report=delivery_report,
                readiness_payload=readiness_payload,
                build_payload=build_payload,
                decision=decision,
            )
        else:
            plan = []
    except Exception as exc:  # pragma: no cover - defensive handoff path
        return [], f"{type(exc).__name__}: {exc}"
    finally:
        if inserted:
            try:
                sys.path.remove(scripts_dir)
            except ValueError:
                pass
    if not isinstance(plan, list):
        return [], "workspace source edit plan builder returned non-list payload"
    return [item for item in plan if isinstance(item, dict)], ""


def _acceptance_evidence_source_edit_plan(delivery_report: dict[str, Any]) -> list[dict[str, Any]]:
    action = (
        delivery_report.get("recommended_next_action")
        if isinstance(delivery_report.get("recommended_next_action"), dict)
        else {}
    )
    evidence = (
        delivery_report.get("acceptance_evidence")
        if isinstance(delivery_report.get("acceptance_evidence"), dict)
        else {}
    )
    missing_files = action.get("missing_files")
    if not isinstance(missing_files, list) or not missing_files:
        missing_files = evidence.get("blocking_missing_files")
    if not isinstance(missing_files, list):
        missing_files = []
    fields = action.get("suggested_fields")
    if not isinstance(fields, list) or not fields:
        fields = [
            "design_brief.acceptance_evidence",
            "design_brief.qa_contract.acceptance_evidence",
            "design_brief.qa_contract.evidence_files",
            "design_brief.qa_contract.verification_evidence",
        ]

    plans: list[dict[str, Any]] = []
    for raw_path in missing_files:
        path_text = str(raw_path or "").strip()
        if not path_text:
            continue
        plans.append(
            {
                "file": "design_brief.json",
                "json_path": "acceptance_evidence",
                "operation": "complete_acceptance_evidence",
                "rule": "acceptance_evidence_missing",
                "missing_files": [path_text],
                "suggested_fields": [str(field) for field in fields if str(field).strip()],
                "suggested_fix": (
                    "Generate the missing proof file if it is a real delivery gate, or correct "
                    "the acceptance evidence ledger if the declared path is stale or optional."
                ),
            }
        )
    if plans:
        return plans
    return [
        {
            "file": "design_brief.json",
            "json_path": "acceptance_evidence",
            "operation": "complete_acceptance_evidence",
            "rule": "acceptance_evidence_missing",
            "suggested_fields": [str(field) for field in fields if str(field).strip()],
            "suggested_fix": (
                "Inspect delivery_readiness.json acceptance_evidence, then generate missing "
                "proof files or correct the ledger."
            ),
        }
    ]


def _report_payload_from_build(workspace: Path, build_payload: dict[str, Any], name: str) -> tuple[dict[str, Any], str]:
    reports = build_payload.get("reports") if isinstance(build_payload.get("reports"), dict) else {}
    item = reports.get(name) if isinstance(reports, dict) else {}
    if not isinstance(item, dict):
        return {}, ""
    path_text = str(item.get("path") or "").strip()
    if not path_text:
        return {}, ""
    payload = _load_json(_workspace_path(workspace, path_text), {})
    return (payload if isinstance(payload, dict) else {}), path_text


def _qa_design_issues(workspace: Path, qa_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    path_text = str(qa_payload.get("design_report") or "").strip()
    if not path_text:
        return [], ""
    payload = _load_json(_workspace_path(workspace, path_text), {})
    issues = payload.get("issues") if isinstance(payload, dict) else []
    if not isinstance(issues, list):
        issues = []
    return [item for item in issues if isinstance(item, dict)], path_text


def _qa_visual_issues(workspace: Path, qa_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    issues: list[dict[str, Any]] = []
    path_text = str(qa_payload.get("visual_report") or "").strip()
    if path_text:
        payload = _load_json(_workspace_path(workspace, path_text), [])
        if isinstance(payload, list):
            issues.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            raw_issues = payload.get("issues") or payload.get("warnings") or payload.get("items")
            if isinstance(raw_issues, list):
                issues.extend(item for item in raw_issues if isinstance(item, dict))
    review_path = str(qa_payload.get("visual_review_report") or "").strip()
    if review_path:
        payload = _load_json(_workspace_path(workspace, review_path), {})
        raw_issues = payload.get("issues") if isinstance(payload, dict) else []
        if isinstance(raw_issues, list):
            for item in raw_issues:
                if isinstance(item, dict):
                    issue = dict(item)
                    issue.setdefault("source", "visual_review")
                    issues.append(issue)
    return issues, path_text


def _delivery_warning_source_edit_plan(
    *,
    advance_workspace: Any,
    workspace: Path,
    delivery_report: dict[str, Any],
    readiness_payload: dict[str, Any],
    build_payload: dict[str, Any],
    decision: str,
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    reports = build_payload.get("reports") if isinstance(build_payload.get("reports"), dict) else {}
    action = (
        delivery_report.get("recommended_next_action")
        if isinstance(delivery_report.get("recommended_next_action"), dict)
        else {}
    )

    def add_plan(action: dict[str, Any], checks_patch: dict[str, Any] | None = None) -> None:
        synthetic = dict(readiness_payload)
        synthetic["next_action"] = action
        if checks_patch:
            checks = dict(synthetic.get("checks") if isinstance(synthetic.get("checks"), dict) else {})
            checks.update(checks_patch)
            synthetic["checks"] = checks
        plan = advance_workspace._source_edit_plan(synthetic, decision=decision)  # noqa: SLF001
        if isinstance(plan, list):
            plans.extend(item for item in plan if isinstance(item, dict))

    planning_payload, planning_path = _report_payload_from_build(workspace, build_payload, "planning")
    planning_counts = (
        reports.get("planning", {}).get("counts", {})
        if isinstance(reports.get("planning"), dict)
        else {}
    )
    if isinstance(planning_payload, dict) and (
        int(planning_counts.get("error_count") or 0) > 0
        or int(planning_counts.get("warning_count") or 0) > 0
    ):
        kind = "fix_planning_errors" if int(planning_counts.get("error_count") or 0) > 0 else "resolve_planning_warnings"
        add_plan(
            {
                "kind": kind,
                "action_type": "edit_sources",
                "planning_report": planning_path,
            },
            {"planning": planning_payload},
        )

    preflight_payload, preflight_path = _report_payload_from_build(workspace, build_payload, "preflight")
    preflight_counts = (
        reports.get("preflight", {}).get("counts", {})
        if isinstance(reports.get("preflight"), dict)
        else {}
    )
    if isinstance(preflight_payload, dict) and (
        int(preflight_counts.get("error_count") or 0) > 0
        or int(preflight_counts.get("warning_count") or 0) > 0
    ):
        kind = "fix_preflight_errors" if int(preflight_counts.get("error_count") or 0) > 0 else "polish_preflight_warnings"
        add_plan(
            {
                "kind": kind,
                "action_type": "edit_sources",
                "preflight_report": preflight_path,
            },
            {"preflight": preflight_payload},
        )

    qa_payload, qa_path = _report_payload_from_build(workspace, build_payload, "qa")
    qa_counts = reports.get("qa", {}).get("counts", {}) if isinstance(reports.get("qa"), dict) else {}
    whitespace_warnings = (
        qa_payload.get("whitespace_warnings")
        if isinstance(qa_payload.get("whitespace_warnings"), list)
        else []
    )
    if int(qa_counts.get("whitespace_warning_count") or 0) > 0 and whitespace_warnings:
        add_plan(
            {
                "kind": "polish_qa_whitespace_warnings",
                "action_type": "edit_sources",
                "qa_whitespace_warnings": whitespace_warnings,
                "qa_report": qa_path,
            }
        )
    action_warning_types = {
        str(item).strip()
        for item in action.get("warning_types", [])
        if str(item).strip()
    } if isinstance(action.get("warning_types"), list) else set()
    layout_density = (
        delivery_report.get("layout_density")
        if isinstance(delivery_report.get("layout_density"), dict)
        else {}
    )
    low_density = (
        layout_density.get("low_content_density_slides")
        if isinstance(layout_density.get("low_content_density_slides"), list)
        else []
    )
    if "layout_density_low" in action_warning_types and low_density:
        floor = layout_density.get("content_density_floor")
        outline_payload = _load_json(workspace / "outline.json", {})
        outline_slides = (
            outline_payload.get("slides")
            if isinstance(outline_payload, dict) and isinstance(outline_payload.get("slides"), list)
            else []
        )
        synthetic_warnings: list[dict[str, Any]] = []
        for item in low_density:
            if not isinstance(item, dict):
                continue
            score = item.get("density_score")
            slide_index = item.get("slide_index")
            slide_id = ""
            if (
                isinstance(slide_index, int)
                and 0 <= slide_index < len(outline_slides)
                and isinstance(outline_slides[slide_index], dict)
            ):
                slide_id = str(
                    outline_slides[slide_index].get("slide_id")
                    or outline_slides[slide_index].get("id")
                    or ""
                ).strip()
            warning: dict[str, Any] = {
                "type": "empty_ratio_too_high",
                "severity": "warning",
                "slide_index": slide_index,
                "visual_density_score": score,
                "suggested_fix": (
                    f"Content density {score} is below the floor {floor}; add a "
                    "visual/evidence anchor, expand the figure/chart/table/body area, "
                    "or deliberately change the slide variant."
                ),
            }
            if slide_id:
                warning["slide_id"] = slide_id
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                warning["empty_ratio"] = round(max(0.0, 1.0 - float(score)), 4)
            synthetic_warnings.append(warning)
        if synthetic_warnings:
            add_plan(
                {
                    "kind": "polish_qa_whitespace_warnings",
                    "action_type": "edit_sources",
                    "qa_whitespace_warnings": synthetic_warnings,
                    "qa_report": layout_density.get("source") or qa_path,
                }
            )

    design_issues, design_path = _qa_design_issues(workspace, qa_payload)
    if int(qa_counts.get("design_warning_count") or 0) > 0 and design_issues:
        add_plan(
            {
                "kind": "polish_qa_design_warnings",
                "action_type": "edit_sources",
                "qa_design_warnings": design_issues,
                "qa_report": qa_path,
                "design_report": design_path,
            }
        )

    visual_issues, visual_path = _qa_visual_issues(workspace, qa_payload)
    visual_warning_count = int(qa_counts.get("visual_warning_count") or 0)
    visual_review_warning_count = int(qa_counts.get("visual_review_warning_count") or 0)
    if (visual_warning_count > 0 or visual_review_warning_count > 0) and visual_issues:
        add_plan(
            {
                "kind": "polish_qa_visual_warnings",
                "action_type": "edit_sources",
                "qa_visual_warnings": visual_issues,
                "qa_report": qa_path,
                "visual_report": visual_path,
                "visual_review_report": str(qa_payload.get("visual_review_report") or ""),
            }
        )

    return plans


def _delivery_next_action_prompt(
    report: dict[str, Any],
    *,
    decision: str,
    execute: bool,
    steps: list[dict[str, Any]],
    source_edit_plan: list[dict[str, Any]] | None = None,
    source_edit_plan_error: str = "",
) -> str:
    action = (
        report.get("recommended_next_action")
        if isinstance(report.get("recommended_next_action"), dict)
        else {}
    )
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    readiness_action = (
        readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    )
    commands = report.get("commands") if isinstance(report.get("commands"), dict) else {}
    command = _command_text(action.get("command"))
    advance_command = _command_text(commands.get("advance"))
    executed_steps = [
        step for step in steps if isinstance(step, dict) and step.get("command_returncode") is not None
    ]

    lines = [
        "# Delivery Next Action",
        "",
        f"- Workspace: `{report.get('workspace', '')}`",
        f"- Delivery status: `{report.get('delivery_status', '')}`",
        f"- Decision: `{decision}`",
        f"- Blocking reasons: `{_markdown_list(report.get('blocking_reasons'))}`",
        f"- Warning reasons: `{_markdown_list(report.get('warning_reasons'))}`",
        _visual_review_requirement_line(report),
        _phase_proof_line(report),
        _build_speed_line(report),
        f"- Recommended next action: `{action.get('kind', 'none')}`",
        f"- Readiness next action: `{readiness_action.get('kind', 'none')}`",
        f"- Action type: `{action.get('action_type', 'none')}`",
        f"- Reason: {action.get('reason', '')}",
        f"- Slide IDs: `{_markdown_list(action.get('slide_ids'))}`",
        f"- Planning paths: `{_markdown_list(action.get('planning_paths'))}`",
        f"- Warning types: `{_markdown_list(action.get('warning_types'))}`",
        f"- Suggested fields: `{_markdown_list(action.get('suggested_fields'))}`",
        f"- Missing files: `{_markdown_list(action.get('missing_files'))}`",
        f"- Execute mode: `{bool(execute)}`",
        "",
        "## Command",
        "",
    ]
    if command:
        lines.extend([f"```bash\n{command}\n```", ""])
    else:
        lines.extend(["No delivery command is currently recommended.", ""])
    if advance_command:
        lines.extend(["## Source-Edit Handoff", "", f"```bash\n{advance_command}\n```", ""])
    lines.extend(["## Reproducibility Context", ""])
    lines.extend(_reproducibility_contract_lines(report))
    lines.extend(_source_inventory_lines(report))
    lines.extend(_resolved_treatment_lines(report))
    lines.append("")
    lines.extend(["## Quality Context", ""])
    lines.extend(_quality_context_lines(report))
    lines.append("")
    lines.extend(["## Layout Density", ""])
    lines.extend(_layout_density_lines(report))
    lines.append("")
    lines.extend(["## Data Handoff", ""])
    lines.extend(_data_handoff_lines(report))
    lines.append("")
    lines.extend(["## Build Data Handoff", ""])
    lines.extend(_build_data_handoff_lines(report))
    lines.append("")
    lines.extend(["## Artifact Context", ""])
    lines.extend(_artifact_context_lines(report))
    lines.append("")
    lines.extend(["## Source Edit Plan", ""])
    if source_edit_plan_error:
        lines.append(f"- unavailable: `{source_edit_plan_error}`")
    else:
        lines.extend(_source_edit_plan_lines(source_edit_plan or []))
    lines.append("")
    lines.extend(["## Execution", ""])
    if executed_steps:
        for step in executed_steps:
            lines.append(
                f"- Step `{step.get('step')}` returned `{step.get('command_returncode')}` "
                f"for `{step.get('next_action', {}).get('kind', '')}`."
            )
    else:
        lines.append("- No command was executed in this run.")
    lines.extend(["", "## Agent Instructions", ""])
    if decision == "ready":
        lines.append("Delivery readiness is ready; hand off the current PPTX and reports.")
    elif decision == "dry_run_command_available" and command:
        lines.extend(
            [
                "Run the recommended delivery command when the environment is ready for it, then rerun delivery readiness.",
                "If the command is a strict final build, do not add `--skip-render` unless render-free delivery is explicitly accepted.",
            ]
        )
    elif decision == "command_failed":
        lines.append("Inspect the command stderr/stdout tails in the JSON report and patch workspace sources or environment issues before rerunning.")
    elif decision == "repeated_command_action":
        lines.append("The same command action repeated after execution; inspect the generated reports instead of rerunning blindly.")
    elif decision == "attention_without_command":
        lines.append("Delivery is not ready, but no command-type action was emitted. Inspect the delivery and build reports, then patch workspace sources or QA settings before rerunning.")
    elif action.get("action_type") != "run_command" and action.get("kind") not in {"", "none"}:
        lines.append("Patch workspace source files or use the source-edit handoff; do not patch generated PPTX files.")
    else:
        lines.append("No delivery-level action is required.")
    lines.append("")
    return "\n".join(lines)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run delivery readiness, optionally execute command-type delivery actions, "
            "and write an agent-facing delivery next-action prompt."
        )
    )
    parser.add_argument("--workspace", required=True, help="Workspace created by init_deck_workspace.py")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute command-type delivery actions. Without this, only reports the next action.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=2,
        help="Maximum delivery/action loops when --execute is set.",
    )
    parser.add_argument(
        "--report",
        default="build/delivery_advance_report.json",
        help="Workspace-relative or absolute path for the delivery advance report.",
    )
    parser.add_argument(
        "--next-action-markdown",
        default="build/delivery_next_action.md",
        help="Workspace-relative or absolute path for the agent-facing delivery prompt.",
    )
    parser.add_argument(
        "--delivery-report",
        default="build/delivery_readiness.json",
        help="Workspace-relative or absolute path for the delivery readiness JSON report.",
    )
    parser.add_argument(
        "--delivery-markdown",
        default="build/delivery_readiness.md",
        help="Workspace-relative or absolute path for the delivery readiness Markdown report.",
    )
    parser.add_argument(
        "--skip-delivery-markdown",
        action="store_true",
        help="Do not write the delivery readiness Markdown report during the loop.",
    )
    parser.add_argument(
        "--allow-skip-render",
        action="store_true",
        help="Pass through to report_delivery_readiness.py for accepted render-free delivery.",
    )
    parser.add_argument(
        "--require-visual-review",
        action="store_true",
        help="Pass through to report_delivery_readiness.py when visual review is required.",
    )
    parser.add_argument(
        "--no-refresh-readiness",
        action="store_true",
        help="Pass through to report_delivery_readiness.py to reuse an existing readiness report.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = _repo_root()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 2

    max_steps = max(1, int(args.max_steps or 1))
    report_path = _workspace_path(workspace, args.report)
    next_prompt_path = _workspace_path(workspace, args.next_action_markdown)
    delivery_report_path = _workspace_path(workspace, args.delivery_report)
    delivery_markdown_path = _workspace_path(workspace, args.delivery_markdown)

    steps: list[dict[str, Any]] = []
    executed_signatures: set[str] = set()
    final_report: dict[str, Any] = {}
    final_decision = "not_started"
    exit_code = 1

    for step_number in range(1, max_steps + 1):
        delivery_rc, delivery, delivery_stderr = _run_delivery(
            repo=repo,
            workspace=workspace,
            report_path=delivery_report_path,
            markdown_path=delivery_markdown_path,
            allow_skip_render=bool(args.allow_skip_render),
            require_visual_review=bool(args.require_visual_review),
            no_refresh_readiness=bool(args.no_refresh_readiness),
            write_markdown=not args.skip_delivery_markdown,
        )
        final_report = delivery
        action = (
            delivery.get("recommended_next_action")
            if isinstance(delivery.get("recommended_next_action"), dict)
            else {}
        )
        status = str(delivery.get("delivery_status") or "")
        kind = str(action.get("kind") or "none")
        action_type = str(action.get("action_type") or "none")
        step_entry: dict[str, Any] = {
            "step": step_number,
            "delivery_returncode": delivery_rc,
            "delivery_status": status,
            "blocking_reasons": delivery.get("blocking_reasons", []),
            "warning_reasons": delivery.get("warning_reasons", []),
            "visual_review_requirement": _visual_review_requirement_summary(delivery),
            "phase_proof_ledger": _phase_proof_summary(delivery),
            "workspace_source_inventory": _workspace_source_inventory_summary(delivery),
            "resolved_treatment_summary": _resolved_treatment_summary(delivery),
            "reproducibility_contract": _reproducibility_contract_summary(delivery),
            "quality_context": _quality_context_summary(delivery),
            "layout_density": _layout_density_summary(delivery),
            "build_speed": _build_speed_summary(delivery),
            "artifact_context": _artifact_context_summary(delivery),
            "next_action": _compact_action(action),
            "delivery_stderr_tail": delivery_stderr[-1200:],
        }

        if not delivery:
            step_entry["decision"] = "delivery_json_unavailable"
            steps.append(step_entry)
            final_decision = "delivery_json_unavailable"
            exit_code = 2
            break
        if status == "ready":
            step_entry["decision"] = "ready"
            steps.append(step_entry)
            final_decision = "ready"
            exit_code = 0
            break
        if kind == "none":
            step_entry["decision"] = "attention_without_command"
            steps.append(step_entry)
            final_decision = "attention_without_command"
            exit_code = 1
            break
        if action_type != "run_command":
            step_entry["decision"] = "edit_sources_required"
            steps.append(step_entry)
            final_decision = "edit_sources_required"
            exit_code = 1
            break

        command = _normalize_command(action.get("command"))
        signature = f"{kind}\n{_command_text(command)}"
        if not command:
            step_entry["decision"] = "missing_command"
            steps.append(step_entry)
            final_decision = "missing_command"
            exit_code = 2
            break
        if not args.execute:
            step_entry["decision"] = "dry_run_command_available"
            steps.append(step_entry)
            final_decision = "dry_run_command_available"
            exit_code = 1
            break
        if signature in executed_signatures:
            step_entry["decision"] = "repeated_command_action"
            steps.append(step_entry)
            final_decision = "repeated_command_action"
            exit_code = 1
            break

        executed_signatures.add(signature)
        command_rc, command_stdout, command_stderr = _run(command, cwd=repo)
        step_entry.update(
            {
                "decision": "executed_command",
                "command": command,
                "command_returncode": command_rc,
                "command_stdout_tail": command_stdout[-2000:],
                "command_stderr_tail": command_stderr[-2000:],
            }
        )
        steps.append(step_entry)
        if command_rc != 0:
            final_decision = "command_failed"
            exit_code = 2
            break
    else:
        final_decision = "max_steps_reached"
        exit_code = 1

    source_edit_plan: list[dict[str, Any]] = []
    source_edit_plan_error = ""
    if final_report and final_decision == "edit_sources_required":
        source_edit_plan, source_edit_plan_error = _workspace_source_edit_plan(
            repo=repo,
            workspace=workspace,
            delivery_report=final_report,
            decision=final_decision,
        )
        if steps and source_edit_plan:
            steps[-1]["source_edit_plan"] = source_edit_plan
        if steps and source_edit_plan_error:
            steps[-1]["source_edit_plan_error"] = source_edit_plan_error

    next_prompt_changed = False
    if final_report:
        next_prompt_changed = _write_text_if_changed(
            next_prompt_path,
            _delivery_next_action_prompt(
                final_report,
                decision=final_decision,
                execute=bool(args.execute),
                steps=steps,
                source_edit_plan=source_edit_plan,
                source_edit_plan_error=source_edit_plan_error,
            ),
        )
    payload = {
        "schema_version": 1,
        "workspace": str(workspace),
        "execute": bool(args.execute),
        "max_steps": max_steps,
        "decision": final_decision,
        "final_delivery_status": (
            final_report.get("delivery_status") if isinstance(final_report, dict) else ""
        ),
        "final_blocking_reasons": (
            final_report.get("blocking_reasons") if isinstance(final_report, dict) else []
        ),
        "final_warning_reasons": (
            final_report.get("warning_reasons") if isinstance(final_report, dict) else []
        ),
        "final_recommended_next_action": _compact_action(
            final_report.get("recommended_next_action") if isinstance(final_report, dict) else {}
        ),
        "visual_review_requirement": (
            _visual_review_requirement_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "phase_proof_ledger": (
            _phase_proof_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "workspace_source_inventory": (
            _workspace_source_inventory_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "resolved_treatment_summary": (
            _resolved_treatment_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "reproducibility_contract": (
            _reproducibility_contract_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "quality_context": (
            _quality_context_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "layout_density": (
            _layout_density_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "build_speed": (
            _build_speed_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "artifact_context": (
            _artifact_context_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "data_analysis_handoff": (
            _data_handoff_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "build_data_analysis_handoff": (
            _build_data_handoff_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "source_edit_plan": source_edit_plan,
        "source_edit_plan_error": source_edit_plan_error,
        "steps": steps,
        "reports": {
            "advance": _display_path(workspace, report_path),
            "delivery": _display_path(workspace, delivery_report_path),
            "delivery_markdown": (
                "" if args.skip_delivery_markdown else _display_path(workspace, delivery_markdown_path)
            ),
            "next_action_markdown": _display_path(workspace, next_prompt_path),
        },
    }
    report_changed = _write_json_if_changed(report_path, payload)
    print(json.dumps(payload, indent=2))
    print(
        "[advance_delivery] "
        f"decision={final_decision} status={payload['final_delivery_status']} "
        f"next_action={payload['final_recommended_next_action'].get('kind', 'none')} "
        f"report={_display_path(workspace, report_path)} changed={int(report_changed)} "
        f"next_prompt={_display_path(workspace, next_prompt_path)} changed={int(next_prompt_changed)}",
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
