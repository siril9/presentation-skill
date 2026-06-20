#!/usr/bin/env python3
"""Advance a deck workspace by following its readiness next action."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _display_path(workspace: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(workspace))
    except ValueError:
        return str(path.resolve())


def _workspace_path(workspace: Path, raw: str) -> Path:
    path = Path(str(raw or "")).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


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


def _command_text(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(item) for item in command)
    return str(command or "").strip()


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


def _run_readiness(
    *,
    repo: Path,
    workspace: Path,
    report_path: Path,
    markdown_path: Path,
    write_markdown: bool,
) -> tuple[int, dict[str, Any], str]:
    cmd = [
        sys.executable,
        str(repo / "scripts" / "report_workspace_readiness.py"),
        "--workspace",
        str(workspace),
        "--report",
        str(report_path),
    ]
    if write_markdown:
        cmd.extend(["--markdown-report", str(markdown_path)])
    else:
        cmd.append("--skip-markdown")
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


def _markdown_list(value: Any, *, empty: str = "none") -> str:
    if not isinstance(value, list):
        return empty
    items = [str(item).strip() for item in value if str(item).strip()]
    return ", ".join(items) if items else empty


def _limited_markdown_list(value: Any, *, limit: int = 6, empty: str = "none") -> str:
    if not isinstance(value, list):
        return empty
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        return empty
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_speed_line(speed: Any, *, label: str = "Last build speed") -> str:
    if not isinstance(speed, dict) or not speed:
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


def _reproducibility_contract_summary(report: dict[str, Any]) -> dict[str, Any]:
    replay = (
        report.get("reproducibility_contract")
        if isinstance(report.get("reproducibility_contract"), dict)
        else {}
    )
    if not replay:
        design_contract = (
            report.get("design_contract")
            if isinstance(report.get("design_contract"), dict)
            else {}
        )
        replay = (
            design_contract.get("reproducibility_contract")
            if isinstance(design_contract.get("reproducibility_contract"), dict)
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
        "acceptance_evidence": _string_list(replay.get("acceptance_evidence")),
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
            f"footers=`{_limited_markdown_list(style_replay.get('footer_pool'))}` "
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
    if quality:
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
    else:
        design_contract = (
            report.get("design_contract")
            if isinstance(report.get("design_contract"), dict)
            else {}
        )
        slide_quality = (
            design_contract.get("slide_quality_contract")
            if isinstance(design_contract.get("slide_quality_contract"), dict)
            else {}
        )
        outline_handoff = (
            report.get("outline_authoring_handoff")
            if isinstance(report.get("outline_authoring_handoff"), dict)
            else {}
        )
        outline_quality = (
            outline_handoff.get("quality_alignment")
            if isinstance(outline_handoff.get("quality_alignment"), dict)
            else {}
        )
    if not slide_quality and not outline_quality:
        return {}
    return {
        "slide_quality_contract": {
            "exists": bool(slide_quality.get("exists")),
            "contract_version": str(slide_quality.get("contract_version") or "").strip(),
            "min_title_pt": slide_quality.get("min_title_pt"),
            "min_body_pt": slide_quality.get("min_body_pt"),
            "min_caption_pt": slide_quality.get("min_caption_pt"),
            "chart_label_min_pt": slide_quality.get("chart_label_min_pt"),
            "footer_reserved_inches": slide_quality.get("footer_reserved_inches"),
            "max_title_lines": slide_quality.get("max_title_lines"),
            "max_slide_text_lines": slide_quality.get("max_slide_text_lines"),
            "max_slide_words": slide_quality.get("max_slide_words"),
            "max_slide_chars": slide_quality.get("max_slide_chars"),
            "evidence_anchor_required": bool(slide_quality.get("evidence_anchor_required")),
            "fail_on_awkward_whitespace": bool(slide_quality.get("fail_on_awkward_whitespace")),
            "artifact_quality_required_when_data_active": bool(
                slide_quality.get("artifact_quality_required_when_data_active")
            ),
            "artifact_must_record_count": _int_value(slide_quality.get("artifact_must_record_count")),
            "fail_on_count": _int_value(slide_quality.get("fail_on_count")),
            "required_command_count": _int_value(slide_quality.get("required_command_count")),
        },
        "outline_quality_alignment": {
            "present": bool(outline_quality.get("present")),
            "persisted": bool(outline_quality.get("persisted")),
            "contract_version": str(outline_quality.get("contract_version") or "").strip(),
            "readability_target_count": _int_value(outline_quality.get("readability_target_count")),
            "readability_targets_used": _string_list(outline_quality.get("readability_targets_used")),
            "layout_target_count": _int_value(outline_quality.get("layout_target_count")),
            "layout_targets_used": _string_list(outline_quality.get("layout_targets_used")),
            "artifact_quality_target_count": _int_value(
                outline_quality.get("artifact_quality_target_count")
            ),
            "qa_gate_count": _int_value(outline_quality.get("qa_gate_count")),
            "qa_gates_used": _string_list(outline_quality.get("qa_gates_used")),
            "required_command_count": _int_value(outline_quality.get("required_command_count")),
            "outline_choices": str(outline_quality.get("outline_choices") or "").strip(),
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
            f"caption=`{slide_quality.get('min_caption_pt')}` "
            f"chart=`{slide_quality.get('chart_label_min_pt')}` "
            f"footer=`{slide_quality.get('footer_reserved_inches')}` "
            f"whitespace=`{bool(slide_quality.get('fail_on_awkward_whitespace'))}` "
            f"evidence_anchor=`{bool(slide_quality.get('evidence_anchor_required'))}` "
            f"artifact_meta=`{bool(slide_quality.get('artifact_quality_required_when_data_active'))}` "
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
            f"artifact=`{int(outline_quality.get('artifact_quality_target_count') or 0)}` "
            f"qa=`{int(outline_quality.get('qa_gate_count') or 0)}` "
            f"commands=`{int(outline_quality.get('required_command_count') or 0)}`"
        )
    return lines or ["- Quality context: `none`"]


def _data_handoff_summary(report: dict[str, Any]) -> dict[str, Any]:
    handoff = (
        report.get("data_analysis_handoff")
        if isinstance(report.get("data_analysis_handoff"), dict)
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
    last_build = report.get("last_build") if isinstance(report.get("last_build"), dict) else {}
    handoff = (
        last_build.get("data_analysis_handoff")
        if isinstance(last_build.get("data_analysis_handoff"), dict)
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
        return ["- Last build data handoff: `none`"]
    lines = [
        "- Last build data handoff: "
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
            "- Last build data artifact rebuild: "
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
            "- Last build data artifact contracts: "
            f"figure_export=`{bool(contracts.get('figure_export_contract_applied'))}` "
            f"figure_outputs=`{int(contracts.get('figure_export_output_count') or 0)}` "
            f"registry_updates=`{int(contracts.get('artifact_registry_update_count') or 0)}` "
            f"asset_updates=`{json.dumps(asset_counts, sort_keys=True)}`"
        )
    lines.extend(_scout_analysis_lines("Last build data scout analysis", handoff.get("scout_analysis")))
    storyboard = (
        handoff.get("artifact_storyboard")
        if isinstance(handoff.get("artifact_storyboard"), dict)
        else {}
    )
    if int(storyboard.get("item_count") or 0):
        lines.append(
            "- Last build data handoff storyboard: "
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
        "- Last build data handoff ledger: "
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
            "- Last build data handoff scripts/checks: "
            f"scripts=`{scripts}` source_checks=`{source_checks}` build_checks=`{build_checks}`"
        )
    verification = _limited_markdown_list(ledger.get("verification_evidence"), limit=4)
    commands = _limited_markdown_list(ledger.get("commands_to_run"), limit=3)
    if verification != "none" or commands != "none":
        lines.append(
            "- Last build data handoff verification: "
            f"evidence=`{verification}` commands=`{commands}`"
        )
    return lines


def _style_mix_markdown_lines(style_mix: Any) -> list[str]:
    if not isinstance(style_mix, dict):
        return ["- Style mix pools: `0`"]
    pool_count = int(style_mix.get("pool_count") or 0)
    multi_count = int(style_mix.get("multi_entry_pool_count") or 0)
    lines = [f"- Style mix pools: `{pool_count}` multi-entry=`{multi_count}/{pool_count}`"]
    pools = style_mix.get("pools")
    if not isinstance(pools, dict):
        return lines
    for key in sorted(pools):
        item = pools.get(key)
        if not isinstance(item, dict):
            continue
        values = item.get("values") if isinstance(item.get("values"), list) else []
        lines.append(
            f"- Style mix `{key}`: `{int(item.get('unique_count') or 0)}/{int(item.get('count') or 0)}` unique, values=`{_markdown_list(values)}`"
        )
    return lines


def _source_inventory_markdown_lines(deck_intake: Any) -> list[str]:
    if not isinstance(deck_intake, dict):
        return ["- Source inventory: `none`"]
    inventory = deck_intake.get("workspace_source_inventory")
    if not isinstance(inventory, dict):
        return ["- Source inventory: `none`"]
    packet = (
        inventory.get("packet")
        if isinstance(inventory.get("packet"), dict)
        else {}
    )
    seed = (
        inventory.get("choice_resolution_seed")
        if isinstance(inventory.get("choice_resolution_seed"), dict)
        else {}
    )
    current = seed if seed.get("exists") else packet
    if not current.get("exists"):
        return ["- Source inventory: `none`"]
    lines = [
        "- Source inventory: "
        f"data=`{int(current.get('data_file_count') or 0)}` "
        f"reference_pptx=`{int(current.get('reference_pptx_count') or 0)}` "
        f"artifact_ledgers=`{int(current.get('artifact_ledger_count') or 0)}`"
    ]
    for key, label in (
        ("data_paths", "Source data paths"),
        ("reference_pptx_paths", "Reference PPTX paths"),
        ("artifact_ledger_paths", "Artifact ledger paths"),
    ):
        paths = current.get(key)
        if isinstance(paths, list) and paths:
            lines.append(f"- {label}: `{_limited_markdown_list(paths, limit=6)}`")
    return lines


def _resolved_treatment_markdown_lines(style: Any) -> list[str]:
    if not isinstance(style, dict):
        return []
    summary = style.get("resolved_treatment_summary")
    if not isinstance(summary, dict) or not summary:
        return []
    counts = summary.get("header_variant_counts")
    counts_text = json.dumps(counts, sort_keys=True) if isinstance(counts, dict) else "{}"
    return [
        "- Resolved header variants: "
        f"unique=`{int(summary.get('unique_header_variant_count') or 0)}` "
        f"counts=`{counts_text}`"
    ]


def _artifact_context_markdown_lines(manifest: Any, selection: Any) -> list[str]:
    if not isinstance(manifest, dict):
        return ["- Artifact aliases: `none`"]
    aliases = manifest.get("aliases")
    if not isinstance(aliases, list) or not aliases:
        return ["- Artifact aliases: `none`"]
    lines = [f"- Artifact aliases: `{len(aliases)}`"]
    quality_counts = manifest.get("figure_quality_counts")
    if isinstance(quality_counts, dict) and quality_counts:
        quality_text = ", ".join(
            f"{str(key)}={int(value)}"
            for key, value in sorted(quality_counts.items())
            if isinstance(value, int) and not isinstance(value, bool)
        )
        if quality_text:
            lines.append(f"- Figure quality: `{quality_text}`")
    for alias in aliases[:6]:
        if not isinstance(alias, dict):
            continue
        output_id = str(alias.get("id") or "").strip() or "unknown"
        alias_values = [
            str(alias.get(key) or "").strip()
            for key in ("image_alias", "chart_alias", "table_alias")
            if str(alias.get(key) or "").strip()
        ]
        alias_text = _markdown_list(alias_values)
        title = str(alias.get("title") or "").strip()
        source = str(alias.get("source_path") or "").strip()
        detail = []
        if title:
            detail.append(f"title=`{title}`")
        if source:
            detail.append(f"source=`{source}`")
        figure_quality = alias.get("figure_quality") if isinstance(alias.get("figure_quality"), dict) else {}
        quality_status = str(figure_quality.get("status") or "").strip()
        exterior_percent = figure_quality.get("exterior_percent")
        if quality_status:
            if isinstance(exterior_percent, (int, float)) and not isinstance(exterior_percent, bool):
                detail.append(f"figure_quality=`{quality_status}:{float(exterior_percent):.1f}% exterior`")
            else:
                detail.append(f"figure_quality=`{quality_status}`")
        detail_text = f" {' '.join(detail)}" if detail else ""
        lines.append(f"- Artifact `{output_id}` aliases: `{alias_text}`{detail_text}")
    omitted_count = len([item for item in aliases if isinstance(item, dict)]) - 6
    if omitted_count > 0:
        lines.append(f"- Artifact aliases omitted: `{omitted_count}`")
    if isinstance(selection, dict):
        lines.append(
            "- Bound artifact targets: "
            f"outputs=`{_markdown_list(selection.get('bound_output_ids'))}` "
            f"slides=`{_markdown_list(selection.get('slide_ids'))}` "
            f"variants=`{_markdown_list(selection.get('variants'))}`"
        )
    return lines


def _artifact_context_summary(report: dict[str, Any]) -> dict[str, Any]:
    context = (
        report.get("artifact_context")
        if isinstance(report.get("artifact_context"), dict)
        else {}
    )
    if context:
        return context

    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    if not artifacts:
        return {}
    manifest = (
        artifacts.get("artifact_manifest")
        if isinstance(artifacts.get("artifact_manifest"), dict)
        else {}
    )
    selection = (
        artifacts.get("artifact_selection")
        if isinstance(artifacts.get("artifact_selection"), dict)
        else {}
    )
    summary: dict[str, Any] = {}
    if manifest:
        counts = (
            manifest.get("figure_quality_counts")
            if isinstance(manifest.get("figure_quality_counts"), dict)
            else {}
        )
        commands = manifest.get("commands") if isinstance(manifest.get("commands"), dict) else {}
        aliases: list[dict[str, Any]] = []
        raw_aliases = manifest.get("aliases") if isinstance(manifest.get("aliases"), list) else []
        for alias in raw_aliases:
            if not isinstance(alias, dict):
                continue
            alias_compact: dict[str, Any] = {
                "id": str(alias.get("id") or "").strip(),
                "title": str(alias.get("title") or "").strip(),
                "image_alias": str(alias.get("image_alias") or "").strip(),
                "chart_alias": str(alias.get("chart_alias") or "").strip(),
                "table_alias": str(alias.get("table_alias") or "").strip(),
                "source_path": str(alias.get("source_path") or "").strip(),
            }
            figure_quality = (
                alias.get("figure_quality")
                if isinstance(alias.get("figure_quality"), dict)
                else {}
            )
            if figure_quality:
                alias_compact["figure_quality"] = figure_quality
            aliases.append(alias_compact)
        summary["artifact_manifest"] = {
            "path": str(manifest.get("path") or "").strip(),
            "exists": bool(manifest.get("exists")),
            "valid": bool(manifest.get("valid")),
            "manifest_version": str(manifest.get("manifest_version") or "").strip(),
            "output_count": _int_value(manifest.get("output_count")),
            "output_ids": _string_list(manifest.get("output_ids")),
            "analysis_summary": str(manifest.get("analysis_summary") or "").strip(),
            "analysis_summary_markdown": str(
                manifest.get("analysis_summary_markdown") or ""
            ).strip(),
            "figure_quality_counts": {
                str(key): _int_value(value)
                for key, value in sorted(counts.items())
                if str(key).strip()
            },
            "selection_template_count": _int_value(manifest.get("selection_template_count")),
            "aliases": aliases,
            "commands": {
                key: commands.get(key)
                for key in (
                    "auto_select_lead",
                    "auto_select_recommended",
                    "auto_select_all",
                )
                if commands.get(key)
            },
        }
    if selection:
        summary["artifact_selection"] = {
            "path": str(selection.get("path") or "").strip(),
            "exists": bool(selection.get("exists")),
            "binding_count": _int_value(selection.get("binding_count")),
            "bound_output_ids": _string_list(selection.get("bound_output_ids")),
            "unbound_output_ids": _string_list(selection.get("unbound_output_ids")),
            "slide_ids": _string_list(selection.get("slide_ids")),
            "variants": _string_list(selection.get("variants")),
            "error": str(selection.get("error") or "").strip(),
        }
    tabular_data = _string_list(artifacts.get("tabular_data"))
    if tabular_data:
        summary["tabular_data"] = tabular_data
    return summary


def _compact_execution_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    keep = (
        "status",
        "valid",
        "plan_version",
        "phase_count",
        "phase_ids",
        "current_phase_id",
        "current_phase_status",
        "current_phase_command_key",
        "current_phase_command",
        "current_phase_command_text",
        "completed_required_count",
        "required_phase_count",
        "rendered_visual_review_required",
        "required_by_route_ledger",
        "phase_proof_ledger",
        "next_action_kind",
    )
    compact = {key: plan.get(key) for key in keep if key in plan}
    phases = plan.get("phases") if isinstance(plan.get("phases"), list) else []
    compact_phases: list[dict[str, Any]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        compact_phases.append(
            {
                "id": phase.get("id"),
                "status": phase.get("status"),
                "complete": bool(phase.get("complete")),
                "required": bool(phase.get("required")),
                "required_by_route_ledger": bool(phase.get("required_by_route_ledger")),
                "acceptance_gate_ids": phase.get("acceptance_gate_ids", []),
                "proof_count": phase.get("proof_count", 0),
                "proof_file_count": phase.get("proof_file_count", 0),
                "existing_proof_file_count": phase.get("existing_proof_file_count", 0),
                "missing_proof_file_count": phase.get("missing_proof_file_count", 0),
                "missing_proof_files": phase.get("missing_proof_files", []),
                "reason": phase.get("reason"),
            }
        )
    if compact_phases:
        compact["phases"] = compact_phases
    return compact


def _execution_plan_current_reason(plan: dict[str, Any]) -> str:
    current = str(plan.get("current_phase_id") or "").strip()
    phases = plan.get("phases") if isinstance(plan.get("phases"), list) else []
    for phase in phases:
        if isinstance(phase, dict) and str(phase.get("id") or "").strip() == current:
            return str(phase.get("reason") or "").strip()
    return ""


def _intake_question_lines(questions: Any) -> list[str]:
    if not isinstance(questions, list):
        return ["- none"]
    lines: list[str] = []
    for question in questions:
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "").strip()
        prompt = str(question.get("question") or "").strip()
        label = f"`{question_id}`" if question_id else "`question`"
        lines.append(f"- {label}: {prompt or 'Select or record the best available answer.'}")
        options = question.get("options")
        if isinstance(options, list):
            for option in options:
                if not isinstance(option, dict):
                    continue
                option_label = str(option.get("label") or "").strip()
                description = str(option.get("description") or "").strip()
                if option_label and description:
                    lines.append(f"  - `{option_label}`: {description}")
                elif option_label:
                    lines.append(f"  - `{option_label}`")
    return lines if lines else ["- none"]


def _source_file_path(report: dict[str, Any], key: str) -> str:
    source_files = report.get("source_files") if isinstance(report.get("source_files"), dict) else {}
    item = source_files.get(key) if isinstance(source_files, dict) else None
    if isinstance(item, dict):
        path = str(item.get("path") or "").strip()
        if path:
            return path
    return f"{key}.json"


def _report_workspace(report: dict[str, Any]) -> Path | None:
    raw = str(report.get("workspace") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _load_report_source_json(report: dict[str, Any], key: str) -> dict[str, Any]:
    workspace = _report_workspace(report)
    if workspace is None:
        return {}
    path = _workspace_path(workspace, _source_file_path(report, key))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _analysis_artifact_plan_from_brief(brief: dict[str, Any]) -> dict[str, Any]:
    plan = brief.get("analysis_artifact_plan")
    if isinstance(plan, dict):
        return plan
    evidence_and_assets = brief.get("evidence_and_assets")
    if isinstance(evidence_and_assets, dict) and isinstance(evidence_and_assets.get("analysis_artifact_plan"), dict):
        return evidence_and_assets["analysis_artifact_plan"]
    return {}


def _data_source_fingerprint_path(item: dict[str, Any]) -> str:
    for key in ("workspace_relative_path", "relative_path", "source_path", "path"):
        text = str(item.get(key) or "").strip()
        if text:
            return text
    return ""


def _slide_lookup(report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    composition = (
        report.get("outline_composition")
        if isinstance(report.get("outline_composition"), dict)
        else {}
    )
    slides = composition.get("slides") if isinstance(composition, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    by_index: dict[int, dict[str, Any]] = {}
    if not isinstance(slides, list):
        return by_id, by_index
    for item in slides:
        if not isinstance(item, dict):
            continue
        slide_id = str(item.get("slide_id") or "").strip()
        if slide_id:
            by_id[slide_id] = item
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        by_index[index] = item
    return by_id, by_index


def _preflight_operation(rule: str) -> str:
    normalized = rule.strip().lower()
    exact = {
        "placeholder_marker_in_outline": "replace_placeholder_text",
        "content_text_density_high": "reduce_text_or_change_variant",
        "sources_missing_streak": "add_compact_source_entries",
        "chart_too_many_categories": "reduce_chart_categories_or_split_slide",
        "chart_too_many_series": "reduce_chart_series_or_use_small_multiples",
        "chart_point_budget_high": "downsample_chart_or_move_detail_to_table",
        "chart_category_labels_long": "shorten_chart_labels_or_rotate_axis",
        "table_too_many_columns": "split_table_columns_or_summarize",
        "table_too_many_rows": "split_table_rows_or_filter",
        "table_cell_budget_high": "summarize_table_or_split_slide",
        "table_cell_text_long": "shorten_table_cell_text",
        "figure_exterior_whitespace_high": "trim_figure_export_whitespace",
        "image_sidebar_missing_image": "add_image_sidebar_hero_asset",
        "image_sidebar_missing_sections": "add_image_sidebar_sections",
        "scientific_figure_panel_count_exceeds_limit": "split_scientific_figure_panels",
        "scientific_figure_dense_grid": "split_or_composite_scientific_figure_grid",
        "scientific_figure_missing_figures": "add_scientific_figure_assets",
        "scientific_figure_tiny_plot_risk": "enlarge_or_split_scientific_figure",
        "scientific_figure_bottom_text_long": "shorten_scientific_figure_bottom_text",
        "generated_image_missing_asset": "add_generated_image_asset",
        "generated_image_missing_metadata": "add_generated_image_metadata",
        "generated_image_prompt_missing": "add_generated_image_prompt_metadata",
        "table_missing_caption_or_sources": "add_caption_or_sources_to_evidence_table",
        "lab_run_missing_caption_or_sources": "add_caption_or_sources_to_lab_results",
        "chart_missing_caption_or_sources": "add_caption_or_sources_to_chart",
        "lab_run_too_many_tables": "split_lab_run_result_tables",
        "lab_run_table_malformed": "repair_lab_run_table_payload",
        "image_sidebar_missing_caption_or_sources": "add_caption_or_sources_to_figure_slide",
        "scientific_figure_missing_caption_or_sources": "add_caption_or_sources_to_figure_slide",
        "evidence_slide_missing_anchor": "add_evidence_chart_table_or_figure_anchor",
        "title_line_budget_high": "shorten_title_or_move_detail_to_subtitle",
        "title_orphan_final_line": "rebalance_title_wrap",
        "subtitle_line_budget_high": "shorten_subtitle_or_move_detail_to_body",
    }
    if normalized in exact:
        return exact[normalized]
    if "source" in normalized:
        return "add_or_shorten_source_provenance"
    if "table" in normalized:
        return "simplify_table_or_move_detail_to_notes"
    if "chart" in normalized:
        return "simplify_chart_or_split_series"
    if "figure" in normalized or "whitespace" in normalized:
        return "fix_figure_export_or_layout_whitespace"
    return "resolve_preflight_issue"


def _preflight_suggested_fields(rule: str) -> list[str]:
    normalized = rule.strip().lower()
    if normalized == "placeholder_marker_in_outline":
        return ["title", "subtitle", "body", "caption", "notes"]
    if normalized == "content_text_density_high":
        return ["variant", "body", "bullets", "summary_callout", "speaker_notes", "readability_contract"]
    if normalized == "title_line_budget_high":
        return ["title", "subtitle", "kicker", "readability_contract.max_title_lines"]
    if normalized == "title_orphan_final_line":
        return ["title", "subtitle", "kicker"]
    if normalized == "subtitle_line_budget_high":
        return ["subtitle", "body", "speaker_notes", "notes"]
    if normalized == "evidence_motif_not_carried":
        return ["deck_style", "evidence_continuity", "subtitle", "kicker", "footer", "sources"]
    if normalized == "sources_missing_streak":
        return ["sources", "refs", "references", "footer"]
    if normalized == "source_line_footer_over_budget":
        return ["sources", "refs", "references", "footer_mode"]
    if normalized == "chart_missing_caption_or_sources":
        return ["caption", "footer", "sources", "refs", "chart", "assets.chart_data"]
    if normalized.startswith("chart_"):
        return ["variant", "chart", "assets.chart_data", "chart.series", "chart.categories", "chart.options"]
    if normalized.startswith("table_"):
        return ["variant", "table", "assets.table_data", "table.headers", "table.rows", "summary_callout"]
    if normalized == "figure_exterior_whitespace_high":
        return ["assets.hero_image", "assets.figures", "figures", "figure_export_contract", "assets/make_figures.py"]
    if normalized == "image_sidebar_missing_image":
        return ["variant", "assets.hero_image", "assets.image", "asset_plan.images", "assets/staged"]
    if normalized == "image_sidebar_missing_sections":
        return ["sidebar_sections", "caption", "interpretation", "takeaway"]
    if normalized == "scientific_figure_bottom_text_long":
        return ["caption", "figure_caption", "interpretation", "takeaway", "speaker_notes", "refs"]
    if normalized in {
        "scientific_figure_panel_count_exceeds_limit",
        "scientific_figure_dense_grid",
        "scientific_figure_missing_figures",
        "scientific_figure_tiny_plot_risk",
    }:
        return ["variant", "figures", "assets.figures", "figure_export_contract", "assets/make_figures.py"]
    if normalized == "generated_image_missing_asset":
        return ["variant", "assets.generated_image", "assets.hero_image", "assets.image", "asset_plan.generated_images"]
    if normalized in {"generated_image_missing_metadata", "generated_image_prompt_missing"}:
        return ["image_generation.prompt", "image_generation.model", "image_generation.purpose", "asset_plan.generated_images"]
    if normalized == "image_sidebar_missing_caption_or_sources":
        return ["caption", "sources", "refs", "assets.hero_image", "figures"]
    if normalized == "scientific_figure_missing_caption_or_sources":
        return ["caption", "figure_caption", "sources", "refs", "figures"]
    if normalized in {"table_missing_caption_or_sources", "lab_run_missing_caption_or_sources"}:
        return ["caption", "footer", "sources", "refs", "references"]
    if normalized == "lab_run_too_many_tables":
        return ["tables", "table_groups", "variant", "summary_callout"]
    if normalized == "lab_run_table_malformed":
        return ["tables", "table_groups", "tables[].headers", "tables[].rows"]
    if normalized == "evidence_slide_missing_anchor":
        return ["variant", "chart", "table", "figures", "assets", "stats"]
    if "source" in normalized:
        return ["sources", "refs", "references", "footer"]
    if "chart" in normalized:
        return ["variant", "chart", "assets.chart_data", "chart.options"]
    if "table" in normalized:
        return ["variant", "table", "assets.table_data"]
    if "figure" in normalized or "whitespace" in normalized:
        return ["variant", "assets", "figures", "figure_export_contract"]
    return ["outline.json"]


def _preflight_suggested_fix(rule: str, fallback: str = "") -> str:
    if fallback.strip():
        return fallback.strip()
    normalized = rule.strip().lower()
    fixes = {
        "placeholder_marker_in_outline": "Replace placeholder/TODO text in visible slide fields or move unresolved work into notes.md.",
        "content_text_density_high": "Shorten body text, split the slide, or switch to a figure/table/sidebar variant with detail moved to notes.",
        "title_line_budget_high": "Shorten the title and move qualifiers into subtitle, body, or speaker notes.",
        "sources_missing_streak": "Add compact source IDs to the affected slides and move long references to a final editable References table slide.",
        "source_line_footer_over_budget": "Use compact source/ref IDs in the footer and move full citations to an editable References table slide.",
        "chart_too_many_categories": "Reduce categories, group minor categories, or split the chart across multiple evidence slides.",
        "chart_too_many_series": "Reduce visible series, use small multiples, or split series across slides.",
        "chart_point_budget_high": "Downsample points, summarize in a table, or move full-resolution detail to an appendix/source artifact.",
        "chart_category_labels_long": "Shorten category labels, rotate labels deliberately, or replace with grouped labels plus a caption.",
        "table_too_many_columns": "Split wide tables, remove low-value columns, or convert to a chart plus compact summary table.",
        "table_too_many_rows": "Filter to the decision rows, split the table, or move full rows to appendix/source data.",
        "table_cell_budget_high": "Summarize the table, split it across slides, or use a lab-run-results dashboard with fewer cells.",
        "table_cell_text_long": "Rewrite long cell prose as short labels and move detail to notes, caption, or references.",
        "figure_exterior_whitespace_high": "Trim the figure export, fix bbox/padding in the figure script, or run trim_image_whitespace.py.",
        "image_sidebar_missing_image": "Stage or bind the figure/image asset and reference it through assets.hero_image or assets.image.",
        "image_sidebar_missing_sections": "Add 2-4 sidebar_sections with short titled readout or interpretation entries.",
        "scientific_figure_panel_count_exceeds_limit": "Split panels across multiple scientific-figure slides or combine them into one slide-ready composite figure.",
        "scientific_figure_dense_grid": "Split detailed panels, create a slide-ready composite, or use image-sidebar for the dominant plot.",
        "scientific_figure_missing_figures": "Add figures or assets.figures entries pointing to staged figure assets.",
        "scientific_figure_tiny_plot_risk": "Export tighter slide-ready figures, enlarge the dominant figure, split panels, or switch to image-sidebar.",
        "scientific_figure_bottom_text_long": "Shorten the bottom caption/interpretation to a compact figure caption plus one sentence, moving detail to notes or refs.",
        "generated_image_missing_asset": "Reference the generated image through assets.generated_image or assets.hero_image after staging it.",
        "generated_image_missing_metadata": "Add image_generation prompt, model, and purpose metadata so generated imagery is auditable.",
        "generated_image_prompt_missing": "Store the generated-image prompt or a concise prompt summary in image_generation.prompt.",
        "table_missing_caption_or_sources": "Add compact table provenance with caption, footer, sources, refs, or references.",
        "chart_missing_caption_or_sources": "Add compact chart provenance with caption, footer, sources, refs, or references.",
        "lab_run_missing_caption_or_sources": "Add assay/run provenance with caption, footer, sources, refs, or references.",
        "lab_run_too_many_tables": "Split lab-run-results table groups across slides or move lower-priority tables to an appendix/source table.",
        "lab_run_table_malformed": "Repair lab-run-results table objects so each table has headers and rows.",
        "image_sidebar_missing_caption_or_sources": "Add a compact caption and source entry for the figure/image-sidebar evidence object.",
        "scientific_figure_missing_caption_or_sources": "Add compact figure provenance with caption, figure_caption, sources, or refs.",
        "evidence_slide_missing_anchor": "Add a real evidence anchor: chart, table, figure, image, stats, or structured comparison.",
        "title_orphan_final_line": "Rebalance the title so the final wrapped line is not a single short word.",
        "subtitle_line_budget_high": "Shorten the subtitle and move explanatory detail to body text, notes, or a follow-on slide.",
    }
    return fixes.get(normalized, "Patch the affected outline field and rerun readiness/preflight.")


def _preflight_measurements(issue: dict[str, Any]) -> dict[str, Any]:
    rule = str(issue.get("rule") or "").strip().lower()
    message = str(issue.get("message") or "").strip()
    measurements: dict[str, Any] = {}

    def add_int(key: str, pattern: str) -> None:
        match = re.search(pattern, message)
        if match:
            measurements[key] = int(match.group(1))

    def add_float(key: str, pattern: str) -> None:
        match = re.search(pattern, message)
        if match:
            measurements[key] = float(match.group(1))

    if rule == "chart_too_many_categories":
        add_int("category_count", r"has (\d+) categories")
    elif rule == "chart_too_many_series":
        add_int("series_count", r"has (\d+) series")
    elif rule == "chart_point_budget_high":
        match = re.search(r"plots (\d+) values across (\d+) series and (\d+) categories", message)
        if match:
            measurements.update(
                {
                    "point_count": int(match.group(1)),
                    "series_count": int(match.group(2)),
                    "category_count": int(match.group(3)),
                }
            )
    elif rule == "chart_category_labels_long":
        add_int("longest_label_chars", r"max (\d+) chars")
        add_float("avg_label_chars", r"average ([0-9.]+)")
    elif rule == "table_too_many_rows":
        add_int("rows", r"has (\d+) rows")
    elif rule == "table_too_many_columns":
        add_int("columns", r"has (\d+) columns")
    elif rule == "table_cell_budget_high":
        match = re.search(r"has (\d+) rows x (\d+) columns \((\d+) editable cells\)", message)
        if match:
            measurements.update(
                {
                    "rows": int(match.group(1)),
                    "columns": int(match.group(2)),
                    "cell_count": int(match.group(3)),
                }
            )
    elif rule == "table_header_text_long":
        match = re.search(r"header (\d+) is (\d+) chars", message)
        if match:
            measurements.update(
                {
                    "header_index": int(match.group(1)),
                    "longest_header_chars": int(match.group(2)),
                }
            )
    elif rule == "table_cell_text_long":
        add_int("long_cell_count", r"(\d+) body cell\(s\) exceed")
        add_float("avg_cell_chars", r"average non-empty body cell is ([0-9.]+) chars")
        match = re.search(r"Longest cell is rows\[(\d+)\]\[(\d+)\] at (\d+) chars", message)
        if match:
            measurements.update(
                {
                    "longest_cell_row": int(match.group(1)),
                    "longest_cell_column": int(match.group(2)),
                    "longest_cell_chars": int(match.group(3)),
                }
            )
    elif rule == "content_text_density_high":
        for key, pattern in (
            ("text_lines", r"(\d+) text lines >"),
            ("text_line_budget", r"text lines > (\d+)"),
            ("word_count", r"(\d+) words >"),
            ("word_budget", r"words > (\d+)"),
            ("char_count", r"(\d+) chars >"),
            ("char_budget", r"chars > (\d+)"),
        ):
            add_int(key, pattern)
    elif rule == "title_line_budget_high":
        add_int("estimated_title_lines", r"estimated at (\d+) wrapped lines")
        add_int("max_title_lines", r"max_title_lines budget of (\d+)")
        add_float("title_font_pt", r"font ~([0-9.]+)pt")
        add_float("title_width_in", r"across ([0-9.]+) in")
    elif rule == "title_orphan_final_line":
        add_int("estimated_title_lines", r"estimated at (\d+) wrapped lines")
        add_float("title_font_pt", r"font ~([0-9.]+)pt")
        add_float("title_width_in", r"across ([0-9.]+) in")
    elif rule == "subtitle_line_budget_high":
        add_int("estimated_subtitle_lines", r"estimated at (\d+) wrapped lines")
        add_float("subtitle_font_pt", r"font ~([0-9.]+)pt")
        add_float("subtitle_width_in", r"across ([0-9.]+) in")
    elif rule == "title_too_long":
        add_int("title_chars", r"Title is (\d+) chars")
    elif rule == "source_line_footer_over_budget":
        add_int("footer_chars", r"combined footer/source text is (\d+) chars")
        add_int("longest_source_chars", r"one source/ref item is (\d+) chars")
        add_int("source_count", r"(\d+) source/ref items")

    return {key: value for key, value in measurements.items() if value not in (None, "")}


def _qa_whitespace_operation(warning_type: str) -> str:
    normalized = warning_type.strip().lower()
    if normalized in {"content_span_too_short", "content_span_too_narrow"}:
        return "rebalance_content_or_change_variant"
    if normalized == "empty_ratio_too_high":
        return "add_visual_anchor_or_reduce_dead_space"
    return "fix_layout_whitespace"


def _qa_whitespace_suggested_fields(warning_type: str) -> list[str]:
    normalized = warning_type.strip().lower()
    if normalized == "content_span_too_short":
        return ["variant", "body", "bullets", "summary_callout", "chart", "table", "figures", "assets"]
    if normalized == "content_span_too_narrow":
        return ["variant", "columns", "body", "chart", "table", "figures", "assets", "sidebar_sections"]
    if normalized == "empty_ratio_too_high":
        return ["variant", "body", "stats", "chart", "table", "figures", "assets", "summary_callout"]
    return ["variant", "body", "assets", "chart", "table", "figures"]


def _qa_whitespace_suggested_fix(issue: dict[str, Any]) -> str:
    warning_type = str(issue.get("type") or "").strip().lower()
    explicit = str(issue.get("suggested_fix") or "").strip()
    if explicit:
        return explicit
    if warning_type == "content_span_too_short":
        ratio = issue.get("content_span_height_ratio")
        dead = issue.get("max_vertical_dead_ratio")
        if ratio not in (None, "") and dead not in (None, ""):
            return (
                f"Content uses only {ratio} of the safe-area height with {dead} vertical dead-space ratio; "
                "enlarge the evidence object, add a chart/table/sidebar, or choose an intentional sparse variant."
            )
        return "Enlarge the evidence object, add a chart/table/sidebar, or choose an intentional sparse variant."
    if warning_type == "content_span_too_narrow":
        ratio = issue.get("content_span_width_ratio")
        dead = issue.get("max_horizontal_dead_ratio")
        if ratio not in (None, "") and dead not in (None, ""):
            return (
                f"Content uses only {ratio} of the safe-area width with {dead} horizontal dead-space ratio; "
                "widen the primary block, use the opposing column for evidence, or switch variants."
            )
        return "Widen the primary block, use the opposing column for evidence, or switch to a deliberate sparse variant."
    if warning_type == "empty_ratio_too_high":
        density = issue.get("visual_density_score")
        empty = issue.get("empty_ratio")
        if density not in (None, "") or empty not in (None, ""):
            return (
                f"Slide density is low (density={density}, empty_ratio={empty}); "
                "add a visual/evidence anchor, promote a stat/chart/table, or reduce unused container space."
            )
        return "Add a visual/evidence anchor, promote a stat/chart/table, or reduce unused container space."
    return "Adjust slide variant, content density, visual anchors, or layout spacing so the whitespace warning clears."


def _qa_whitespace_measurements(issue: dict[str, Any]) -> dict[str, Any]:
    measurements: dict[str, Any] = {}
    for key in (
        "variant",
        "shape_id",
        "shape_ids",
        "content_span_height_ratio",
        "content_span_width_ratio",
        "max_vertical_dead_ratio",
        "max_horizontal_dead_ratio",
        "visual_density_score",
        "empty_ratio",
        "delta_inches",
    ):
        value = issue.get(key)
        if value not in (None, "", [], {}):
            measurements[key] = value
    return measurements


def _qa_design_operation(warning_type: str) -> str:
    normalized = warning_type.strip().lower()
    if normalized == "chart_label_font_too_small":
        return "increase_chart_label_font_or_simplify_chart"
    if normalized.endswith("_font_too_small"):
        if normalized.startswith("table_"):
            return "increase_table_font_or_reduce_cells"
        return "increase_text_size_or_reduce_text"
    if normalized == "footer_reserved_space_intrusion":
        return "restore_footer_reserved_space"
    if normalized == "table_density_risk":
        return "simplify_table_or_split_slide"
    if normalized == "stack_gap_too_small":
        return "increase_stack_spacing"
    if normalized == "chart_value_label_headroom_risk":
        return "add_chart_value_headroom"
    return "resolve_design_readability_warning"


def _qa_design_role(warning_type: str, role: Any = "") -> str:
    raw_role = str(role or "").strip()
    if raw_role:
        return raw_role
    normalized = warning_type.strip().lower()
    if normalized.endswith("_font_too_small"):
        return normalized.removesuffix("_font_too_small").replace("_", " ")
    if normalized.startswith("chart_"):
        return "chart"
    if normalized.startswith("table_"):
        return "table"
    if normalized.startswith("footer_"):
        return "footer"
    return ""


def _qa_design_suggested_fields(warning_type: str, role: Any = "") -> list[str]:
    normalized = warning_type.strip().lower()
    normalized_role = str(role or "").strip().lower()
    if normalized == "chart_label_font_too_small" or normalized_role.startswith("chart"):
        return [
            "chart.options.labelFontSize",
            "chart.options",
            "assets.chart_data",
            "readability_contract.chart_label_min_pt",
        ]
    if normalized == "footer_reserved_space_intrusion" or normalized_role == "footer":
        return [
            "footer",
            "sources",
            "refs",
            "readability_contract.footer_reserved_inches",
            "variant",
        ]
    if normalized == "table_density_risk":
        return ["table", "tables", "table_groups", "variant", "summary_callout"]
    if normalized == "chart_value_label_headroom_risk":
        return [
            "chart.options.valueAxisMax",
            "chart.options",
            "chart.series",
            "chart.categories",
        ]
    if normalized == "stack_gap_too_small":
        return ["variant", "body", "bullets", "cards", "columns"]
    if normalized.startswith("table_") or normalized_role == "table":
        return ["table", "tables", "table_groups", "readability_contract.min_body_pt"]
    if normalized.startswith("title_") or normalized_role in {"title", "headline", "heading"}:
        return ["title", "subtitle", "kicker", "readability_contract.min_title_pt"]
    if normalized.startswith("caption_") or normalized_role in {"caption", "source", "sources", "refs"}:
        return ["caption", "figure_caption", "sources", "refs", "readability_contract.min_caption_pt"]
    if normalized.endswith("_font_too_small"):
        return ["body", "bullets", "columns", "cards", "summary_callout", "readability_contract.min_body_pt"]
    return ["variant", "body", "chart.options", "table", "figures", "readability_contract"]


def _qa_design_suggested_fix(issue: dict[str, Any]) -> str:
    warning_type = str(issue.get("type") or "").strip()
    normalized = warning_type.lower()
    role = _qa_design_role(warning_type, issue.get("role"))
    font_pt = issue.get("font_pt")
    min_allowed_pt = issue.get("min_allowed_pt")
    if normalized == "chart_label_font_too_small":
        if font_pt not in (None, "") and min_allowed_pt not in (None, ""):
            return (
                f"Rendered chart labels are {font_pt}pt but the readability contract "
                f"requires at least {min_allowed_pt}pt; raise chart label font size, "
                "simplify labels, or split the chart."
            )
        return "Raise chart label font size, simplify labels, or split the chart so labels meet the readability contract."
    if normalized.endswith("_font_too_small"):
        label = role or "text"
        if font_pt not in (None, "") and min_allowed_pt not in (None, ""):
            return (
                f"Rendered {label} text is {font_pt}pt but the readability contract "
                f"requires at least {min_allowed_pt}pt; shorten or split the text, "
                "choose a roomier variant, or raise the source font setting."
            )
        if min_allowed_pt not in (None, ""):
            return (
                f"Rendered {label} text is below the {min_allowed_pt}pt readability floor; "
                "shorten or split the text, choose a roomier variant, or raise the source font setting."
            )
        return "Shorten or split the affected text, choose a roomier variant, or raise the source font setting."
    if normalized == "footer_reserved_space_intrusion":
        reserved = issue.get("reserved_inches")
        intrusion = issue.get("intrusion_inches")
        if reserved not in (None, "") and intrusion not in (None, ""):
            return (
                f"Footer reserve is {reserved}in and content intrudes by {intrusion}in; "
                "move, shorten, or resize slide content so sources and page number stay below the reserve line."
            )
        return "Move, shorten, or resize slide content so sources and page number stay below the reserved footer line."
    if normalized == "table_density_risk":
        rows = issue.get("rows")
        columns = issue.get("columns")
        if rows not in (None, "") and columns not in (None, ""):
            return (
                f"Table has {rows} rows and {columns} columns; split it, summarize it, "
                "or move detail to backup/reference slides before final delivery."
            )
        return "Split, summarize, or move dense table detail to backup/reference slides before final delivery."
    if normalized == "chart_value_label_headroom_risk":
        max_value = issue.get("max_value")
        axis_max = issue.get("axis_max")
        if max_value not in (None, "") and axis_max not in (None, ""):
            return (
                f"Chart value labels have little headroom: max value {max_value} against axis max {axis_max}; "
                "increase valueAxisMax or reduce label density."
            )
        return "Increase chart value-axis headroom or reduce label density so labels do not crowd the plot edge."
    if normalized == "stack_gap_too_small":
        return "Increase stack spacing or reduce the number/height of stacked blocks so adjacent elements breathe."
    return "Adjust source text, table/chart options, slide variant, or readability contract so the rendered warning clears."


def _qa_design_measurements(issue: dict[str, Any]) -> dict[str, Any]:
    warning_type = str(issue.get("type") or "").strip()
    measurements: dict[str, Any] = {}
    role = _qa_design_role(warning_type, issue.get("role"))
    if role:
        measurements["role"] = role
    for key in (
        "shape_id",
        "shape_ids",
        "chart_part",
        "font_pt",
        "min_allowed_pt",
        "reserved_inches",
        "intrusion_inches",
        "rows",
        "columns",
        "axis_max",
        "max_value",
        "text",
    ):
        value = issue.get(key)
        if value not in (None, "", []):
            measurements[key] = value
    return measurements


def _qa_visual_operation(warning_type: str) -> str:
    normalized = warning_type.strip().lower()
    if normalized in {"underfilled_card_row", "underfilled_textbox"}:
        return "densify_or_resize_visual_container"
    if normalized in {"visual_anchor_absent", "research_visual_mode_without_images", "source_image_absent"}:
        return "add_source_backed_visual_anchor"
    if normalized in {"variant_overuse", "variant_run"}:
        return "change_repeated_slide_variant"
    if normalized in {"visual_family_overuse", "composition_family_repetition", "composition_family_run"}:
        return "break_repetitive_composition_family"
    if normalized in {"safe_area_risk", "footer_clearance_risk", "title_clearance_risk"}:
        return "restore_layout_clearance"
    if normalized == "render_unavailable":
        return "rerun_with_rendered_visual_review"
    return "resolve_visual_polish_warning"


def _issue_slide_index(path: str) -> int | None:
    marker = "slides["
    if marker not in path:
        return None
    tail = path.split(marker, 1)[1]
    raw = tail.split("]", 1)[0]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _planning_source_key(path: str, message: str) -> str:
    normalized = f"{path}\n{message}".lower()
    if path.startswith("design_brief."):
        return "design_brief"
    if path.startswith("content_plan."):
        return "content_plan"
    if path.startswith("evidence_plan."):
        return "evidence_plan"
    if path.startswith("asset_plan."):
        return "asset_plan"
    if path.startswith("outline."):
        return "outline"
    if "source_policy" in normalized or "chart candidate" in normalized:
        return "evidence_plan"
    if "asset_plan" in normalized or " asset " in normalized:
        return "asset_plan"
    if "narrative_arc" in normalized or "slide plan" in normalized:
        return "content_plan"
    if (
        "readability_contract" in normalized
        or "speed_contract" in normalized
        or "figure_export_contract" in normalized
        or "analysis_artifact_plan" in normalized
        or "artifact_registry" in normalized
        or "artifact_manifest" in normalized
        or "style_mix_matrix" in normalized
        or "evidence_continuity" in normalized
        or "qa_contract" in normalized
        or "acceptance_evidence" in normalized
        or "agent_execution_plan" in normalized
        or "subagent_handoff" in normalized
    ):
        return "design_brief"
    return "outline"


def _planning_json_path(path: str, source_key: str) -> str:
    prefix = f"{source_key}."
    if path.startswith(prefix):
        return path[len(prefix) :] or source_key
    return path or source_key


def _planning_rule(path: str, message: str) -> str:
    normalized = f"{path}\n{message}".lower()
    if path.startswith("evidence_plan.") and any(
        token in normalized
        for token in ("artifact_ids", "artifact_aliases", "artifact_paths", "evidence artifact")
    ):
        return "evidence_artifact_context"
    for rule in (
        "data_source_fingerprints",
        "readability_contract",
        "speed_contract",
        "figure_export_contract",
        "analysis_summary",
        "analysis_artifact_plan",
        "artifact_manifest",
        "artifact_registry",
        "source_policy",
        "style_mix_matrix",
        "style_seed",
        "qa_contract",
        "acceptance_evidence",
        "agent_execution_plan",
        "subagent_handoff",
        "evidence_continuity",
        "narrative_arc",
        "slide_plan",
    ):
        if rule in normalized:
            return rule
    if path:
        parts = [part.split("[", 1)[0] for part in path.split(".") if part]
        return ".".join(parts[:2]) if len(parts) >= 2 else parts[0]
    return "planning"


def _planning_operation(path: str, message: str) -> str:
    normalized = f"{path}\n{message}".lower()
    if path.startswith("evidence_plan.") and any(
        token in normalized
        for token in ("artifact_ids", "artifact_aliases", "artifact_paths", "evidence artifact")
    ):
        return "repair_evidence_artifact_context"
    if "data_source_fingerprints" in normalized:
        return "repair_data_source_fingerprints"
    if "readability_contract" in normalized:
        return "complete_readability_contract"
    if "speed_contract" in normalized:
        return "complete_speed_contract"
    if "qa_contract" in normalized or "acceptance_evidence" in normalized:
        return "complete_qa_contract"
    if "agent_execution_plan" in normalized or "subagent_handoff" in normalized:
        return "complete_execution_handoff_contract"
    if "source_policy" in normalized:
        return "add_source_policy"
    if "style_mix_matrix" in normalized or "style_seed" in normalized:
        return "fix_style_mix_contract"
    if "evidence_continuity" in normalized:
        return "fix_evidence_continuity"
    if "figure_export_contract" in normalized or "figure output" in normalized:
        if (
            "not referenced in outline" in normalized
            or "target_slide" in normalized
            or "target slide" in normalized
            or "used_on_slides" in normalized
        ):
            return "fix_slide_references"
        return "fix_figure_export_contract"
    if "image_whitespace" in normalized or "exterior blank area" in normalized or "trim or regenerate" in normalized:
        return "trim_figure_export_whitespace"
    if "analysis_summary" in normalized:
        return "repair_or_rebuild_analysis_summary"
    if (
        "appears older than" in normalized
        or "fingerprint" in normalized
        or "source_sha256" in normalized
        or "sha256" in normalized
    ):
        return "rerun_or_rebind_generated_artifacts"
    if (
        "analysis_artifact_plan" in normalized
        or "artifact_manifest" in normalized
        or "artifact_registry" in normalized
    ):
        if "used_on_slides" in normalized or "not referenced in outline" in normalized:
            return "fix_slide_references"
        return "repair_generated_artifact_registry"
    if (
        "slide reference" in normalized
        or "unknown slide" in normalized
        or "used_on_slides" in normalized
        or "target_slide" in normalized
        or "slide_id" in normalized
    ):
        return "fix_slide_references"
    if path.startswith("content_plan.") or "narrative_arc" in normalized:
        return "align_content_plan_with_outline"
    if path.startswith("evidence_plan."):
        return "repair_evidence_plan"
    if path.startswith("asset_plan."):
        return "repair_asset_plan"
    if path.startswith("design_brief."):
        return "complete_design_brief_contract"
    return "resolve_planning_issue"


def _planning_suggested_fix(operation: str) -> str:
    if operation == "complete_readability_contract":
        return "Fill or correct readable text floors, title/prose budgets, footer reserve, table-density, whitespace, and figure-crop rules in design_brief.json."
    if operation == "complete_speed_contract":
        return "Declare renderer, first-pass validation, render policy, asset policy, and conversion guidance so repeat builds are predictable."
    if operation == "complete_qa_contract":
        return "Declare required QA checks, fail-on conditions, placeholder checks, and acceptance-evidence files so final delivery criteria are reproducible."
    if operation == "complete_execution_handoff_contract":
        return "Record agent execution phases and handoff ownership so the next agent can continue the deck workflow without re-deriving the process."
    if operation == "add_source_policy":
        return "Add a compact evidence source policy that decides footer citations, refs, and final reference-slide behavior."
    if operation == "fix_style_mix_contract":
        return "Record a stable style_seed and at least two supported treatment pools so mix-and-match styling is reproducible."
    if operation == "fix_evidence_continuity":
        return "Align continuity threads and slide applications with real outline slide IDs."
    if operation == "fix_figure_export_contract":
        return "Declare the deterministic figure script, rerun command, output paths, target slides, target boxes, DPI, label size, and crop rule."
    if operation == "trim_figure_export_whitespace":
        return "Trim the generated figure export, fix bbox/padding in assets/make_figures.py, or run trim_image_whitespace.py, then rerun the artifact producer and refresh the manifest/analysis summary."
    if operation == "rerun_or_rebind_generated_artifacts":
        return "Rerun the producer script or artifact binding helper so manifests, fingerprints, and slide bindings match current local outputs."
    if operation == "repair_or_rebuild_analysis_summary":
        return "Rerun the figure scaffold/producer script or repair assets/analysis_summary.json and its Markdown companion so schema, manifest path, source paths, aliases, row/point counts, and readability assumptions match generated artifacts."
    if operation == "repair_data_source_fingerprints":
        return "Update analysis_artifact_plan.data_source_fingerprints from the current local data files, or rerun/apply the data analysis handoff that owns those source fingerprints."
    if operation == "repair_generated_artifact_registry":
        return "Repair analysis_artifact_plan registry or manifest metadata so generated figures, charts, tables, producers, and provenance are auditable."
    if operation == "fix_slide_references":
        return "Replace stale slide references with current outline slide IDs or add explicit used_on_slides metadata."
    if operation == "align_content_plan_with_outline":
        return "Align planned slide IDs, roles, variants, and narrative_arc references with outline.json."
    if operation == "repair_evidence_plan":
        return "Align evidence IDs, claims, chart candidates, source IDs, and target slides with the outline and evidence policy."
    if operation == "repair_evidence_artifact_context":
        return "Repair evidence_plan artifact IDs, role-keyed aliases, and local paths so claim provenance matches generated figure/chart/table artifacts."
    if operation == "repair_asset_plan":
        return "Fix asset entries, paths, provenance, generated-image metadata, and used_on_slides references before staging."
    if operation == "complete_design_brief_contract":
        return "Complete the missing design contract field in design_brief.json before final render."
    return "Patch the referenced workspace planning source field, then rerun readiness."


def _planning_suggested_fields(rule: str, path: str) -> list[str]:
    normalized = f"{rule}\n{path}".strip().lower()
    if "data_source_fingerprints" in normalized:
        return [
            "analysis_artifact_plan.data_source_fingerprints",
            "analysis_artifact_plan.candidate_data_files",
            "analysis_artifact_plan.artifact_manifest",
            "assets/artifacts_manifest.json",
            "assets/analysis_summary.json",
            "analysis_metadata.source_path",
            "analysis_metadata.source_sha256",
            "analysis_metadata.source_bytes",
            "source_size_bytes",
            "artifact_selections.auto.json",
        ]
    if any(
        token in normalized
        for token in (
            "source_sha256",
            "source_bytes",
            "source_size_bytes",
            "producer_sha256",
            "producer_bytes",
            "producer script",
            "current source file",
        )
    ):
        return [
            "analysis_artifact_plan.artifact_manifest",
            "assets/artifacts_manifest.json",
            "analysis_metadata.source_path",
            "analysis_metadata.source_sha256",
            "analysis_metadata.source_bytes",
            "analysis_metadata.producer_path",
            "analysis_metadata.producer_sha256",
            "analysis_metadata.producer_bytes",
            "assets/make_figures.py",
            "artifact_selections.auto.json",
        ]
    if "readability_contract" in normalized:
        return [
            "readability_contract",
            "readability_contract.min_title_pt",
            "readability_contract.min_body_pt",
            "readability_contract.footer_reserved_inches",
        ]
    if "speed_contract" in normalized:
        return [
            "speed_contract",
            "speed_contract.renderer",
            "speed_contract.first_pass",
            "speed_contract.conversion_hint",
        ]
    if "qa_contract" in normalized or "acceptance_evidence" in normalized:
        return [
            "qa_contract",
            "qa_contract.required_checks",
            "qa_contract.fail_on",
            "qa_contract.placeholder_checks",
            "acceptance_evidence",
        ]
    if "agent_execution_plan" in normalized or "subagent_handoff" in normalized:
        return [
            "agent_execution_plan",
            "agent_execution_plan.phases",
            "agent_execution_plan.commands",
            "subagent_handoff",
        ]
    if "source_policy" in normalized:
        return ["evidence_plan.source_policy", "sources", "refs", "references"]
    if "evidence_artifact_context" in normalized:
        return [
            "evidence_plan.items[].artifact_ids",
            "evidence_plan.items[].artifact_aliases.figure",
            "evidence_plan.items[].artifact_aliases.chart",
            "evidence_plan.items[].artifact_aliases.table",
            "evidence_plan.items[].artifact_paths.figure",
            "evidence_plan.items[].artifact_paths.chart",
            "evidence_plan.items[].artifact_paths.table",
            "assets/artifacts_manifest.json",
            "artifact_selections.auto.json",
        ]
    if "style_mix_matrix" in normalized or "style_seed" in normalized:
        return ["style_system.style_seed", "style_system.style_mix_matrix", "style_mix_matrix"]
    if "figure_export_contract" in normalized:
        return [
            "figure_export_contract",
            "figure_export_contract.outputs",
            "figure_export_contract.rerun_command",
        ]
    if "image_whitespace" in normalized or "exterior blank area" in normalized or "trim" in normalized:
        return [
            "assets/make_figures.py",
            "scripts/trim_image_whitespace.py",
            "analysis_artifact_plan.artifact_manifest",
            "assets/artifacts_manifest.json",
            "analysis_artifact_plan.analysis_summary",
            "assets/analysis_summary.json",
            "assets/analysis_summary.md",
            "figure_export_contract",
        ]
    if "analysis_summary" in normalized:
        return [
            "analysis_artifact_plan.analysis_summary",
            "assets/analysis_summary.json",
            "assets/analysis_summary.md",
        ]
    if (
        "analysis_artifact_plan" in normalized
        or "artifact_manifest" in normalized
        or "artifact_registry" in normalized
    ):
        return ["analysis_artifact_plan", "assets/artifacts_manifest.json", "artifact_selections.auto.json"]
    if "evidence_continuity" in normalized:
        return ["evidence_continuity", "outline.slide_id", "content_plan.narrative_arc"]
    if "narrative_arc" in normalized or "slide_plan" in normalized:
        return ["content_plan.slide_plan", "content_plan.narrative_arc", "outline.slides"]
    if path:
        parts = [part for part in path.split(".") if part]
        return [".".join(parts[:2])] if len(parts) >= 2 else [path]
    return ["workspace planning sources"]


def _planning_data_source_fingerprint_details(
    report: dict[str, Any],
    planning_path: str,
    message: str,
) -> dict[str, Any]:
    normalized = f"{planning_path}\n{message}".lower()
    if "data_source_fingerprints" not in normalized:
        return {}
    details: dict[str, Any] = {"stale_artifact_dependency": "source_data"}
    match = re.search(r"data_source_fingerprints\[(\d+)\]", planning_path)
    fingerprint_index: int | None = None
    if match:
        try:
            fingerprint_index = int(match.group(1))
        except ValueError:
            fingerprint_index = None
    if fingerprint_index is not None:
        details["data_source_fingerprint_index"] = fingerprint_index
    brief = _load_report_source_json(report, "design_brief")
    plan = _analysis_artifact_plan_from_brief(brief)
    fingerprints = plan.get("data_source_fingerprints") if isinstance(plan, dict) else []
    entry: dict[str, Any] = {}
    if (
        isinstance(fingerprints, list)
        and fingerprint_index is not None
        and 0 <= fingerprint_index < len(fingerprints)
        and isinstance(fingerprints[fingerprint_index], dict)
    ):
        entry = fingerprints[fingerprint_index]
    elif isinstance(fingerprints, list):
        for item in fingerprints:
            if isinstance(item, dict):
                entry = item
                break
    data_path = _data_source_fingerprint_path(entry) if entry else ""
    if data_path:
        details["data_source_path"] = data_path
    recorded_sha = str(entry.get("source_sha256") or "").strip() if entry else ""
    if recorded_sha:
        details["data_source_recorded_sha256"] = recorded_sha
    recorded_size = entry.get("source_size_bytes", entry.get("source_bytes")) if entry else None
    if isinstance(recorded_size, (int, float)) and not isinstance(recorded_size, bool):
        details["data_source_recorded_size_bytes"] = int(recorded_size)
    hash_status = str(entry.get("hash_status") or "").strip() if entry else ""
    if hash_status:
        details["data_source_hash_status"] = hash_status
    workspace = _report_workspace(report)
    if workspace is not None and data_path:
        source_path = _workspace_path(workspace, data_path)
        exists = source_path.exists()
        details["data_source_exists"] = exists
        if exists and source_path.is_file():
            try:
                details["data_source_current_sha256"] = _file_sha256(source_path)
                details["data_source_current_size_bytes"] = source_path.stat().st_size
            except OSError:
                pass
    return details


def _planning_artifact_details(report: dict[str, Any], planning_path: str, message: str, operation: str) -> dict[str, Any]:
    if operation not in {
        "rerun_or_rebind_generated_artifacts",
        "repair_or_rebuild_analysis_summary",
        "repair_generated_artifact_registry",
        "fix_figure_export_contract",
        "trim_figure_export_whitespace",
        "repair_data_source_fingerprints",
    }:
        return {}
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    manifest = (
        artifacts.get("artifact_manifest")
        if isinstance(artifacts.get("artifact_manifest"), dict)
        else {}
    )
    details: dict[str, Any] = {}
    details.update(_planning_data_source_fingerprint_details(report, planning_path, message))
    manifest_path = str(manifest.get("path") or "").strip()
    if manifest_path:
        details["artifact_manifest"] = manifest_path
    analysis_summary = str(manifest.get("analysis_summary") or "").strip()
    if analysis_summary:
        details["analysis_summary"] = analysis_summary
    analysis_summary_markdown = str(manifest.get("analysis_summary_markdown") or "").strip()
    if analysis_summary_markdown:
        details["analysis_summary_markdown"] = analysis_summary_markdown
    output_ids = [
        str(item).strip()
        for item in manifest.get("output_ids", [])
        if str(item).strip()
    ] if isinstance(manifest.get("output_ids"), list) else []
    if output_ids:
        details["artifact_output_ids"] = output_ids[:6]
    aliases = []
    raw_aliases = manifest.get("aliases")
    if isinstance(raw_aliases, list):
        for alias in raw_aliases:
            if not isinstance(alias, dict):
                continue
            output_id = str(alias.get("id") or "").strip()
            alias_values = [
                str(alias.get(key) or "").strip()
                for key in ("image_alias", "chart_alias", "table_alias")
                if str(alias.get(key) or "").strip()
            ]
            if output_id and alias_values:
                aliases.append(f"{output_id}: {', '.join(alias_values)}")
    if aliases:
        details["artifact_aliases"] = aliases[:6]
    commands = manifest.get("commands") if isinstance(manifest.get("commands"), dict) else {}
    for command_key in ("auto_select_lead", "auto_select_recommended", "auto_select_all"):
        command = commands.get(command_key)
        if isinstance(command, list) and command:
            details["artifact_binding_command"] = " ".join(str(item) for item in command)
            break
    normalized = f"{planning_path}\n{message}".lower()
    if "producer_sha256" in normalized or "producer_bytes" in normalized or "producer script" in normalized:
        details["stale_artifact_dependency"] = "producer_script"
    elif "source_sha256" in normalized or "source_bytes" in normalized or "current source file" in normalized:
        details["stale_artifact_dependency"] = "source_data"
    return details


def _artifact_command_details(report: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    manifest = (
        artifacts.get("artifact_manifest")
        if isinstance(artifacts.get("artifact_manifest"), dict)
        else {}
    )
    selection = (
        artifacts.get("artifact_selection")
        if isinstance(artifacts.get("artifact_selection"), dict)
        else {}
    )
    details: dict[str, Any] = {
        "command": _command_text(action.get("command")),
    }
    data_paths = action.get("data_paths")
    if isinstance(data_paths, list) and data_paths:
        details["data_paths"] = [str(item) for item in data_paths if str(item).strip()]
    manifest_path = str(manifest.get("path") or "").strip()
    if manifest_path:
        details["artifact_manifest"] = manifest_path
    selection_path = str(selection.get("path") or "").strip()
    if selection_path:
        details["artifact_selection"] = selection_path
    analysis_summary = str(manifest.get("analysis_summary") or "").strip()
    if analysis_summary:
        details["analysis_summary"] = analysis_summary
    analysis_summary_markdown = str(manifest.get("analysis_summary_markdown") or "").strip()
    if analysis_summary_markdown:
        details["analysis_summary_markdown"] = analysis_summary_markdown
    output_ids = [
        str(item).strip()
        for item in manifest.get("output_ids", [])
        if str(item).strip()
    ] if isinstance(manifest.get("output_ids"), list) else []
    if output_ids:
        details["artifact_output_ids"] = output_ids[:8]
    unbound_ids = [
        str(item).strip()
        for item in selection.get("unbound_output_ids", [])
        if str(item).strip()
    ] if isinstance(selection.get("unbound_output_ids"), list) else []
    if unbound_ids:
        details["unbound_output_ids"] = unbound_ids[:8]
    aliases = []
    raw_aliases = manifest.get("aliases")
    if isinstance(raw_aliases, list):
        for alias in raw_aliases:
            if not isinstance(alias, dict):
                continue
            output_id = str(alias.get("id") or "").strip()
            alias_values = [
                str(alias.get(key) or "").strip()
                for key in ("image_alias", "chart_alias", "table_alias")
                if str(alias.get(key) or "").strip()
            ]
            if output_id and alias_values:
                aliases.append(f"{output_id}: {', '.join(alias_values)}")
    if aliases:
        details["artifact_aliases"] = aliases[:8]
    commands = manifest.get("commands") if isinstance(manifest.get("commands"), dict) else {}
    for command_key in ("auto_select_lead", "auto_select_recommended", "auto_select_all"):
        command = commands.get(command_key)
        if isinstance(command, list) and command:
            details["artifact_binding_command"] = " ".join(str(item) for item in command)
            break
    if str(manifest.get("error") or "").strip():
        details["artifact_manifest_error"] = str(manifest.get("error") or "").strip()
    if str(selection.get("error") or "").strip():
        details["artifact_selection_error"] = str(selection.get("error") or "").strip()
    return {key: value for key, value in details.items() if value not in ("", [], {})}


def _source_edit_plan(report: dict[str, Any], *, decision: str = "") -> list[dict[str, Any]]:
    action = report.get("next_action") if isinstance(report.get("next_action"), dict) else {}
    execution_plan = _compact_execution_plan(report.get("execution_plan"))
    kind = str(action.get("kind") or "")
    outline_file = _source_file_path(report, "outline")
    by_id, by_index = _slide_lookup(report)
    plan: list[dict[str, Any]] = []

    def add_slide_target(
        *,
        slide_id: str,
        operation: str,
        json_path: str,
        reason: str,
        extras: dict[str, Any] | None = None,
    ) -> None:
        slide = by_id.get(slide_id, {})
        target: dict[str, Any] = {
            "file": outline_file,
            "slide_id": slide_id,
            "slide_index": slide.get("index"),
            "slide_title": slide.get("title"),
            "json_path": json_path,
            "operation": operation,
            "reason": reason,
        }
        if extras:
            target.update(extras)
        plan.append(target)

    slide_ids = [str(item).strip() for item in action.get("slide_ids", []) if str(item).strip()] if isinstance(action.get("slide_ids"), list) else []
    if kind == "add_source_coverage":
        for slide_id in slide_ids:
            slide = by_id.get(slide_id)
            index = slide.get("index") if isinstance(slide, dict) else None
            json_path = f"slides[{index}].sources" if isinstance(index, int) else "slides[].sources"
            add_slide_target(
                slide_id=slide_id,
                operation="add_compact_source_entries",
                json_path=json_path,
                reason="Content slide lacks compact provenance.",
                extras={
                    "suggested_fields": action.get("suggested_fields", ["sources"]),
                    "suggested_value_shape": ["S1: short source label or citation ID"],
                },
            )
    elif kind == "add_visual_or_evidence_anchors":
        for slide_id in slide_ids:
            slide = by_id.get(slide_id)
            index = slide.get("index") if isinstance(slide, dict) else None
            json_path = f"slides[{index}]" if isinstance(index, int) else "slides[]"
            add_slide_target(
                slide_id=slide_id,
                operation="add_visual_or_structural_anchor",
                json_path=json_path,
                reason="Content slide lacks a visual, evidence, or structural anchor.",
                extras={
                    "suggested_variants": action.get("suggested_variants", []),
                    "suggested_fields": ["variant", "assets", "chart", "table", "figures", "stats"],
                },
            )
    elif kind == "review_variant_rhythm":
        plan.append(
            {
                "file": outline_file,
                "json_path": "slides",
                "operation": "review_variant_distribution",
                "reason": "One content variant dominates the deck.",
                "dominant_variant": action.get("dominant_variant"),
                "dominant_ratio": action.get("dominant_ratio"),
            }
        )
    elif kind == "record_deck_intake_answers":
        plan.append(
            {
                "file": str(action.get("intake_answers") or "intake_answers.json"),
                "json_path": "answers",
                "operation": "write_intake_answers_or_best_judgment",
                "reason": "deck_start_packet.json exists but durable intake answers have not been recorded.",
                "deck_start_packet": action.get("deck_start_packet", "deck_start_packet.json"),
                "answer_template": action.get("answer_template", {}),
                "suggested_fields": action.get(
                    "suggested_fields",
                    ["intake_answers.json", "design_brief.user_intake", "notes.md"],
                ),
            }
        )
    elif kind == "fix_outline_authoring_handoff_json":
        plan.append(
            {
                "file": str(action.get("outline_handoff") or "outline_authoring_handoff.json"),
                "json_path": "source_patch",
                "operation": "fix_outline_authoring_handoff_json",
                "reason": "outline_authoring_handoff.json or its apply report is invalid and cannot be applied deterministically.",
                "suggested_fields": action.get("suggested_fields", ["outline_authoring_handoff.json"]),
                "error": action.get("outline_handoff_error", ""),
            }
        )
    elif kind == "author_design_contract_from_prompt":
        plan.extend(
            [
                {
                    "file": str(action.get("design_contract") or "design_contract.json"),
                    "json_path": "$",
                    "operation": "author_design_contract_from_prompt",
                    "reason": "The deck-start execution plan reached design-contract locking, but design_contract.json has not been authored and applied yet.",
                    "prompt_command": execution_plan.get("current_phase_command_text", ""),
                    "suggested_fields": action.get("suggested_fields", []),
                },
                {
                    "file": _source_file_path(report, "design_brief"),
                    "json_path": "choice_resolution_seed",
                    "operation": "copy_or_refine_choice_resolution_seed",
                    "reason": "The design contract should preserve the resolved intake choices, route decisions, and locked source fields.",
                    "suggested_fields": [
                        "design_contract.choice_resolution",
                        "style_system.style_mix_matrix",
                        "readability_contract",
                    ],
                },
                {
                    "file": _source_file_path(report, "evidence_plan"),
                    "json_path": "source_policy",
                    "operation": "lock_source_policy_in_design_contract",
                    "reason": "The returned contract should make citation and source-footer policy explicit before outline authoring.",
                    "suggested_fields": ["source_policy", "items", "chart_candidates"],
                },
                {
                    "file": _source_file_path(report, "asset_plan"),
                    "json_path": "asset_posture",
                    "operation": "lock_asset_and_artifact_posture",
                    "reason": "The returned contract should declare local/web/generated/chart/table posture and artifact burden.",
                    "suggested_fields": ["asset_posture", "images", "charts", "tables"],
                },
            ]
        )
    elif kind == "author_outline_from_contract":
        plan.extend(
            [
                {
                    "file": outline_file,
                    "json_path": "slides",
                    "operation": "replace_starter_outline_from_contract",
                    "reason": "The deck-start execution plan reached outline authoring, but the outline still looks like starter or missing authored content.",
                    "prompt_command": execution_plan.get("current_phase_command_text", ""),
                    "suggested_variants": action.get("suggested_variants", []),
                    "suggested_fields": action.get("suggested_fields", []),
                },
                {
                    "file": _source_file_path(report, "content_plan"),
                    "json_path": "slide_plan",
                    "operation": "align_slide_plan_with_authored_outline",
                    "reason": "The content plan should describe the authored slide sequence, roles, variants, and narrative arc before build.",
                    "suggested_fields": ["thesis", "audience", "slide_plan", "narrative_arc"],
                },
                {
                    "file": _source_file_path(report, "evidence_plan"),
                    "json_path": "items",
                    "operation": "bind_claims_and_sources_to_outline",
                    "reason": "Evidence, chart candidates, source IDs, and target slides should match the authored outline.",
                    "suggested_fields": ["source_policy", "items", "chart_candidates", "used_on_slides"],
                },
                {
                    "file": _source_file_path(report, "asset_plan"),
                    "json_path": "images/charts/tables",
                    "operation": "bind_assets_to_authored_outline",
                    "reason": "Asset, chart, table, and generated-artifact entries should resolve to real authored slide IDs.",
                    "suggested_fields": ["images", "charts", "tables", "generated_images", "used_on_slides"],
                },
            ]
        )
    elif kind == "polish_qa_whitespace_warnings":
        issues = (
            action.get("qa_whitespace_warnings")
            if isinstance(action.get("qa_whitespace_warnings"), list)
            else []
        )
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            try:
                slide_index = int(issue.get("slide_index"))
            except (TypeError, ValueError):
                slide_index = -1
            slide = by_index.get(slide_index, {})
            slide_id = str(issue.get("slide_id") or slide.get("slide_id") or "").strip()
            warning_type = str(issue.get("type") or "").strip()
            target = {
                "file": outline_file,
                "slide_id": slide_id or None,
                "slide_index": slide_index if slide_index >= 0 else None,
                "slide_title": slide.get("title"),
                "json_path": f"slides[{slide_index}]" if slide_index >= 0 else "outline.json",
                "operation": _qa_whitespace_operation(warning_type),
                "rule": warning_type,
                "severity": str(issue.get("severity") or "warning"),
                "reason": "Post-build QA found awkward whitespace on this slide.",
                "suggested_fields": _qa_whitespace_suggested_fields(warning_type),
                "suggested_fix": _qa_whitespace_suggested_fix(issue),
                "report_source": "qa_whitespace",
                "qa_report": action.get("qa_report", ""),
            }
            target.update(_qa_whitespace_measurements(issue))
            plan.append(target)
    elif kind == "polish_qa_design_warnings":
        issues = (
            action.get("qa_design_warnings")
            if isinstance(action.get("qa_design_warnings"), list)
            else []
        )
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            try:
                slide_index = int(issue.get("slide_index"))
            except (TypeError, ValueError):
                slide_index = -1
            slide = by_index.get(slide_index, {})
            slide_id = str(issue.get("slide_id") or slide.get("slide_id") or "").strip()
            warning_type = str(issue.get("type") or "").strip()
            target = {
                "file": outline_file,
                "slide_id": slide_id or None,
                "slide_index": slide_index if slide_index >= 0 else None,
                "slide_title": slide.get("title"),
                "json_path": f"slides[{slide_index}]" if slide_index >= 0 else "outline.json",
                "operation": _qa_design_operation(warning_type),
                "rule": warning_type,
                "severity": str(issue.get("severity") or "warning"),
                "reason": "Post-build design QA found a readability or footer-reserve warning.",
                "suggested_fields": _qa_design_suggested_fields(warning_type, issue.get("role")),
                "suggested_fix": _qa_design_suggested_fix(issue),
                "report_source": "qa_design",
                "qa_report": action.get("qa_report", ""),
                "design_report": action.get("design_report", ""),
            }
            target.update(_qa_design_measurements(issue))
            plan.append(target)
    elif kind == "polish_qa_visual_warnings":
        issues = (
            action.get("qa_visual_warnings")
            if isinstance(action.get("qa_visual_warnings"), list)
            else []
        )
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            try:
                slide_index = int(issue.get("slide_index"))
            except (TypeError, ValueError):
                slide_index = -1
            slide = by_index.get(slide_index, {})
            slide_id = str(issue.get("slide_id") or slide.get("slide_id") or "").strip()
            warning_type = str(issue.get("type") or "").strip()
            plan.append(
                {
                    "file": outline_file,
                    "slide_id": slide_id or None,
                    "slide_index": slide_index if slide_index >= 0 else None,
                    "slide_title": slide.get("title"),
                    "json_path": f"slides[{slide_index}]" if slide_index >= 0 else "slides",
                    "operation": _qa_visual_operation(warning_type),
                    "rule": warning_type,
                    "severity": str(issue.get("severity") or "warning"),
                    "reason": "Post-build visual QA or visual-review found a sparse, underfilled, or repetitive layout warning.",
                    "suggested_fix": str(issue.get("suggestion") or issue.get("suggested_fix") or "").strip()
                    or "Adjust slide variant, content density, visual anchors, or layout spacing so the visual warning clears.",
                    "report_source": str(issue.get("source") or "qa_visual"),
                    "qa_report": action.get("qa_report", ""),
                    "visual_report": action.get("visual_report", ""),
                    "visual_review_report": action.get("visual_review_report", ""),
                }
            )
    elif kind == "inspect_failed_build_report":
        qa_counts = action.get("qa_counts") if isinstance(action.get("qa_counts"), dict) else {}
        failed_step = str(action.get("failed_step") or "unknown").strip() or "unknown"
        returncode = action.get("returncode")
        plan.append(
            {
                "file": outline_file,
                "json_path": "slides",
                "operation": "inspect_failed_build_report_and_patch_sources",
                "reason": "The latest current build report records a failed step; inspect saved QA/build artifacts and patch workspace sources before rerunning strict build.",
                "report_source": "failed_build",
                "failed_step": failed_step,
                "returncode": returncode,
                "qa_report": action.get("qa_report", ""),
                "qa_counts": qa_counts,
                "suggested_fields": ["variant", "body", "assets", "chart", "table", "figures", "readability_contract"],
                "suggested_fix": "Use the saved QA report counts and artifacts to identify the failing slides or rules, then patch outline/design/data sources and rerun readiness plus strict build.",
            }
        )
    elif kind == "bind_generated_artifacts" and decision in {
        "dry_run_command_available",
        "command_failed",
        "repeated_command_action",
        "max_steps_reached",
    }:
        target = {
            "file": "artifact_selections.auto.json",
            "json_path": "bindings",
            "operation": "run_or_repair_generated_artifact_binding",
            "reason": "Generated artifact outputs need deterministic slide bindings before clean report/data delivery can continue.",
            "suggested_fields": [
                "bindings[].output_id",
                "bindings[].slide_id",
                "bindings[].variant",
                "outline.json:slides",
                "evidence_plan.json:items",
                "asset_plan.json:images/charts/tables",
            ],
            "suggested_fix": "Run the artifact binding command, or repair the manifest/selection file so generated chart, table, and figure aliases bind to real slide IDs.",
        }
        target.update(_artifact_command_details(report, action))
        plan.append(target)
    elif kind == "scaffold_data_artifacts" and decision in {
        "dry_run_command_available",
        "command_failed",
        "repeated_command_action",
        "max_steps_reached",
    }:
        target = {
            "file": "assets/make_figures.py",
            "json_path": "producer_script",
            "operation": "run_or_repair_data_artifact_scaffold",
            "reason": "Local tabular data needs a deterministic figure/chart/table producer before clean evidence slides can be bound.",
            "suggested_fields": [
                "data_path",
                "assets/make_figures.py",
                "assets/artifacts_manifest.json",
                "assets/analysis_summary.json",
                "artifact_selections.auto.json",
                "outline.json:slides",
            ],
            "suggested_fix": "Run the fast-first-pass scaffold command, or repair the source data/producer script so it emits a manifest, analysis summary, chart JSON, table JSON, and slide-ready figure exports.",
        }
        target.update(_artifact_command_details(report, action))
        plan.append(target)
    elif kind == "refresh_generated_artifacts" and decision in {
        "dry_run_command_available",
        "command_failed",
        "repeated_command_action",
        "max_steps_reached",
    }:
        target = {
            "file": "assets/make_figures.py",
            "json_path": "producer_script",
            "operation": "refresh_stale_generated_artifacts",
            "reason": "Generated figure/chart/table artifacts are stale relative to local data or the producer script.",
            "suggested_fields": [
                "data_path",
                "assets/make_figures.py",
                "assets/artifacts_manifest.json",
                "assets/analysis_summary.json",
                "artifact_selections.auto.json",
                "design_brief.analysis_artifact_plan",
                "build/build_workspace_report.json",
            ],
            "suggested_fix": "Run the refresh command, or repair the source data/producer script so it regenerates the manifest, analysis summary, chart JSON, table JSON, figure exports, and source-freshness fingerprints.",
            "stale_source_files": action.get("stale_source_files", []),
            "stale_artifact_dependencies": action.get("stale_artifact_dependencies", []),
        }
        target.update(_artifact_command_details(report, action))
        plan.append(target)

    if decision == "repeated_command_action" or kind in {"resolve_planning_warnings", "fix_planning_errors"}:
        checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
        planning = checks.get("planning") if isinstance(checks.get("planning"), dict) else {}
        planning_issues = planning.get("issues") if isinstance(planning.get("issues"), list) else []
        for issue in planning_issues:
            if not isinstance(issue, dict):
                continue
            severity = str(issue.get("severity") or "").strip().lower()
            if severity not in {"warning", "error", "info"}:
                continue
            planning_path = str(issue.get("path") or "").strip()
            message = str(issue.get("message") or "").strip()
            source_key = _planning_source_key(planning_path, message)
            slide_index = _issue_slide_index(planning_path) if source_key == "outline" else None
            slide = by_index.get(slide_index, {}) if slide_index is not None else {}
            operation = _planning_operation(planning_path, message)
            rule = _planning_rule(planning_path, message)
            target = {
                "file": _source_file_path(report, source_key),
                "slide_id": slide.get("slide_id"),
                "slide_index": slide_index,
                "slide_title": slide.get("title"),
                "json_path": _planning_json_path(planning_path, source_key),
                "operation": operation,
                "rule": rule,
                "severity": severity,
                "reason": message,
                "suggested_fields": _planning_suggested_fields(rule, planning_path),
                "suggested_fix": _planning_suggested_fix(operation),
                "report_source": "planning",
                "planning_path": planning_path,
            }
            target.update(_planning_artifact_details(report, planning_path, message, operation))
            plan.append(
                target
            )

    if decision == "repeated_command_action" or kind in {"fix_preflight_errors", "polish_preflight_warnings"}:
        checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
        preflight = checks.get("preflight") if isinstance(checks.get("preflight"), dict) else {}
        issues = preflight.get("issues") if isinstance(preflight.get("issues"), list) else []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            severity = str(issue.get("severity") or "").strip().lower()
            if severity not in {"warning", "error", "info"}:
                continue
            try:
                slide_index = int(issue.get("slide_index"))
            except (TypeError, ValueError):
                slide_index = -1
            slide = by_index.get(slide_index, {})
            rule = str(issue.get("rule") or "").strip()
            fallback_fix = str(issue.get("suggested_fix") or "").strip()
            target = {
                "file": outline_file,
                "slide_id": slide.get("slide_id"),
                "slide_index": slide_index if slide_index >= 0 else None,
                "slide_title": slide.get("title"),
                "json_path": f"slides[{slide_index}]" if slide_index >= 0 else "outline.json",
                "operation": _preflight_operation(rule),
                "rule": rule,
                "severity": severity,
                "reason": str(issue.get("message") or "").strip(),
                "suggested_fields": _preflight_suggested_fields(rule),
                "suggested_fix": _preflight_suggested_fix(rule, fallback_fix),
                "report_source": "preflight",
            }
            target.update(_preflight_measurements(issue))
            plan.append(target)
    return plan


def _source_edit_plan_lines(plan: list[dict[str, Any]]) -> list[str]:
    if not plan:
        return ["- none"]
    lines: list[str] = []
    for item in plan:
        slide = str(item.get("slide_id") or "").strip()
        slide_text = f" slide `{slide}`" if slide else ""
        lines.append(
            f"- `{item.get('file', '')}` `{item.get('json_path', '')}`{slide_text}: "
            f"`{item.get('operation', '')}`"
        )
        detail_parts = []
        for key, label in (
            ("suggested_fields", "fields"),
            ("suggested_variants", "variants"),
            ("rule", "rule"),
            ("reason", "reason"),
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
            ("command", "command"),
            ("data_paths", "data paths"),
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
            ("prompt_command", "prompt command"),
            ("suggested_fix", "fix"),
        ):
            value = item.get(key)
            if isinstance(value, list):
                text = _markdown_list(value)
            else:
                text = str(value or "").strip()
            if text and text != "none":
                detail_parts.append(f"{label}: {text}")
        if detail_parts:
            lines.append(f"  {'; '.join(detail_parts)}")
    return lines


def _next_action_prompt(
    report: dict[str, Any],
    *,
    decision: str = "",
    source_edit_plan: list[dict[str, Any]] | None = None,
) -> str:
    action = report.get("next_action") if isinstance(report.get("next_action"), dict) else {}
    execution_plan = _compact_execution_plan(report.get("execution_plan"))
    phase_proof = (
        execution_plan.get("phase_proof_ledger")
        if isinstance(execution_plan.get("phase_proof_ledger"), dict)
        else {}
    )
    phase_command = str(execution_plan.get("current_phase_command_text") or "").strip()
    design_contract = (
        report.get("design_contract")
        if isinstance(report.get("design_contract"), dict)
        else {}
    )
    contract_qa = (
        design_contract.get("qa_contract")
        if isinstance(design_contract.get("qa_contract"), dict)
        else {}
    )
    contract_acceptance = (
        design_contract.get("acceptance_evidence")
        if isinstance(design_contract.get("acceptance_evidence"), dict)
        else {}
    )
    contract_agent_plan = (
        design_contract.get("agent_execution_plan")
        if isinstance(design_contract.get("agent_execution_plan"), dict)
        else {}
    )
    composition = (
        report.get("outline_composition")
        if isinstance(report.get("outline_composition"), dict)
        else {}
    )
    style = report.get("style") if isinstance(report.get("style"), dict) else {}
    resolved_style = (
        style.get("resolved_deck_style")
        if isinstance(style.get("resolved_deck_style"), dict)
        else {}
    )
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    artifact_context = _artifact_context_summary(report)
    manifest = (
        artifact_context.get("artifact_manifest")
        if isinstance(artifact_context.get("artifact_manifest"), dict)
        else artifacts.get("artifact_manifest")
        if isinstance(artifacts.get("artifact_manifest"), dict)
        else {}
    )
    manifest_commands = manifest.get("commands") if isinstance(manifest.get("commands"), dict) else {}
    selection = (
        artifact_context.get("artifact_selection")
        if isinstance(artifact_context.get("artifact_selection"), dict)
        else artifacts.get("artifact_selection")
        if isinstance(artifacts.get("artifact_selection"), dict)
        else {}
    )
    tabular_data = (
        artifact_context.get("tabular_data")
        if isinstance(artifact_context.get("tabular_data"), list)
        else artifacts.get("tabular_data")
    )
    data_handoff = (
        report.get("data_analysis_handoff")
        if isinstance(report.get("data_analysis_handoff"), dict)
        else {}
    )
    deck_intake = (
        report.get("deck_intake")
        if isinstance(report.get("deck_intake"), dict)
        else {}
    )
    last_build = report.get("last_build") if isinstance(report.get("last_build"), dict) else {}
    build_data_handoff = _build_data_handoff_summary(report)
    source_files = report.get("source_files") if isinstance(report.get("source_files"), dict) else {}
    command = _command_text(action.get("command"))
    source_file_lines = []
    for name in (
        "outline",
        "deck_start_packet",
        "intake_answers",
        "intake_apply_report",
        "design_contract",
        "design_contract_apply_report",
        "style_extract_report",
        "style_extract_design_brief",
        "style_fragment_apply_report",
        "data_analysis_handoff",
        "data_analysis_handoff_apply_report",
        "data_analysis_handoff_selection",
        "design_brief",
        "content_plan",
        "evidence_plan",
        "asset_plan",
        "outline_authoring_handoff",
        "outline_authoring_handoff_apply_report",
        "artifact_selection",
        "artifact_manifest_apply_report",
    ):
        item = source_files.get(name) if isinstance(source_files, dict) else None
        if isinstance(item, dict):
            source_file_lines.append(f"- `{name}`: `{item.get('path', '')}` exists=`{bool(item.get('exists'))}`")

    lines = [
        "# Workspace Next Action",
        "",
        f"- Workspace: `{report.get('workspace', '')}`",
        f"- Status: `{report.get('status', '')}`",
        f"- Status reasons: `{_markdown_list(report.get('status_reasons'))}`",
        f"- Next action: `{action.get('kind', 'none')}`",
        f"- Action type: `{action.get('action_type', 'none')}`",
        f"- Reason: {action.get('reason', '')}",
        f"- Execution plan: `{execution_plan.get('plan_version', '') or 'none'}` current=`{execution_plan.get('current_phase_id', '') or execution_plan.get('current_phase_status', 'none')}` required=`{execution_plan.get('completed_required_count', 0)}/{execution_plan.get('required_phase_count', 0)}`",
        f"- Execution phase reason: `{_execution_plan_current_reason(execution_plan)}`",
        f"- Execution route-required phases: `{_markdown_list(execution_plan.get('required_by_route_ledger'))}` visual_review_required=`{bool(execution_plan.get('rendered_visual_review_required'))}`",
        f"- Phase proof ledger: `{phase_proof.get('ledger_version', '') or 'none'}` valid=`{bool(phase_proof.get('valid'))}` gates=`{phase_proof.get('acceptance_gate_count', 0)}` proof_paths=`{phase_proof.get('proof_path_count', 0)}` files=`{phase_proof.get('existing_file_count', 0)}/{phase_proof.get('proof_file_count', 0)}` missing=`{phase_proof.get('missing_file_count', 0)}` route_required=`{_markdown_list(phase_proof.get('route_required_phase_ids'))}`",
        f"- Execution phase command: `{execution_plan.get('current_phase_command_key', '') or 'none'}` `{execution_plan.get('current_phase_command_text', '')}`",
        f"- Slide IDs: `{_markdown_list(action.get('slide_ids'))}`",
        f"- Suggested variants: `{_markdown_list(action.get('suggested_variants'))}`",
        f"- Suggested fields: `{_markdown_list(action.get('suggested_fields'))}`",
        f"- Warning types: `{_markdown_list(action.get('warning_types'))}`",
        f"- Failed step: `{action.get('failed_step', '')}`",
        f"- Return code: `{action.get('returncode', '')}`",
        f"- QA counts: `{json.dumps(action.get('qa_counts', {}), sort_keys=True) if isinstance(action.get('qa_counts'), dict) else '{}'}`",
        f"- QA report: `{action.get('qa_report', '')}`",
        f"- Design report: `{action.get('design_report', '')}`",
        f"- Visual report: `{action.get('visual_report', '')}`",
        f"- Visual review report: `{action.get('visual_review_report', '')}`",
        f"- Reference PPTX: `{_markdown_list(action.get('reference_pptx_candidates'))}`",
        f"- Data paths: `{_markdown_list(action.get('data_paths'))}`",
        f"- PPTX style status: `{action.get('style_status', '')}`",
        f"- Style report: `{action.get('style_report', '')}`",
        f"- Style fragment: `{action.get('style_fragment', '')}`",
        f"- Style apply report: `{action.get('style_apply_report', '')}`",
        f"- Deck intake status: `{action.get('intake_status', '')}`",
        f"- Deck start packet: `{action.get('deck_start_packet', '')}`",
        f"- Intake answers: `{action.get('intake_answers', '')}`",
        f"- Intake apply report: `{action.get('intake_apply_report', '')}`",
        f"- Intake error: `{action.get('intake_error', '')}`",
        f"- Design contract status: `{action.get('design_contract_status', '')}`",
        f"- Design contract: `{action.get('design_contract', '')}`",
        f"- Design contract apply report: `{action.get('design_contract_apply_report', '')}`",
        f"- Design contract error: `{action.get('design_contract_error', '')}`",
        f"- Contract QA checks: `{contract_qa.get('required_check_count', 0)}` fail_on=`{_markdown_list(contract_qa.get('fail_on'))}`",
        f"- Contract acceptance evidence: `{contract_acceptance.get('existing_file_count', 0)}/{contract_acceptance.get('file_count', 0)}` files exist, missing=`{_markdown_list(contract_acceptance.get('missing_files'))}`",
        f"- Contract agent phases: `{_markdown_list(contract_agent_plan.get('phase_ids'))}` commands=`{contract_agent_plan.get('command_count', 0)}`",
        f"- Outline handoff status: `{action.get('outline_handoff_status', '')}`",
        f"- Outline handoff: `{action.get('outline_handoff', '')}`",
        f"- Outline handoff apply report: `{action.get('outline_handoff_apply_report', '')}`",
        f"- Outline handoff error: `{action.get('outline_handoff_error', '')}`",
        f"- Patch fields: `{_markdown_list(action.get('patch_fields'))}`",
        f"- Source-footer report: `{action.get('source_footer_report', '')}`",
        f"- Dominant variant: `{action.get('dominant_variant', '')}`",
        f"- Dominant ratio: `{action.get('dominant_ratio', '')}`",
        "",
        "## Replay Contract",
        "",
        *_reproducibility_contract_lines(report),
        "",
        "## Quality Context",
        "",
        *_quality_context_lines(report),
        "",
        "## Style Context",
        "",
        f"- Resolved preset: `{style.get('resolved_style_preset', '')}`",
        f"- Style seed: `{style.get('style_seed') or 'none'}`",
        f"- Header variant: `{resolved_style.get('header_variant', 'none')}`",
        f"- Footer mode: `{resolved_style.get('footer_mode', 'none')}`",
        *_style_mix_markdown_lines(style.get("style_mix_matrix")),
        *_resolved_treatment_markdown_lines(style),
        "",
        "## Artifact Context",
        "",
        f"- Manifest: `{manifest.get('path', '')}` exists=`{bool(manifest.get('exists'))}` valid=`{bool(manifest.get('valid'))}` outputs=`{manifest.get('output_count', 0)}`",
        f"- Analysis summary: `{manifest.get('analysis_summary') or ''}` markdown=`{manifest.get('analysis_summary_markdown') or ''}`",
        f"- Output IDs: `{_markdown_list(manifest.get('output_ids'))}`",
        *_artifact_context_markdown_lines(manifest, selection),
        f"- Selection templates: `{manifest.get('selection_template_count', 0)}`",
        f"- Auto-bind command: `{_command_text(manifest_commands.get('auto_select_lead') or manifest_commands.get('auto_select_all'))}`",
        f"- Artifact selection: `{selection.get('path', '')}` exists=`{bool(selection.get('exists'))}` bindings=`{selection.get('binding_count', 0)}`",
        f"- Unbound output IDs: `{_markdown_list(selection.get('unbound_output_ids'))}`",
        f"- Tabular data: `{_markdown_list(tabular_data)}`",
        f"- Data handoff status: `{data_handoff.get('status', 'none')}` applied=`{bool(data_handoff.get('applied'))}` bound_outputs=`{_markdown_list(data_handoff.get('bound_output_ids'))}`",
        f"- Last build data handoff status: `{build_data_handoff.get('status', 'none')}` applied=`{bool(build_data_handoff.get('applied'))}` bound_outputs=`{_markdown_list(build_data_handoff.get('bound_output_ids'))}`",
        _build_speed_line(last_build.get("speed")),
        "",
        "## Data Handoff",
        "",
        *_data_handoff_lines(report),
        "",
        "## Last Build Data Handoff",
        "",
        *_build_data_handoff_lines(report),
        "",
        "## Source Context",
        "",
        *_source_inventory_markdown_lines(deck_intake),
        f"- Content slides: `{composition.get('content_slide_count', 0)}`",
        f"- Content variants: `{json.dumps(composition.get('content_variant_counts', {}), sort_keys=True)}`",
        f"- Warning signals: `{_markdown_list(composition.get('warning_signals'))}`",
        f"- Unanchored content slides: `{_markdown_list(composition.get('unanchored_content_slide_ids'))}`",
        f"- Content slides without sources: `{_markdown_list(composition.get('missing_source_content_slide_ids'))}`",
        "",
        "## Source Files",
        "",
        *source_file_lines,
        "",
    ]
    if action.get("kind") == "record_deck_intake_answers":
        answer_template = action.get("answer_template")
        lines.extend(
            [
                "## Intake Questions",
                "",
                *_intake_question_lines(action.get("questions")),
                "",
                "## Intake Answer Template",
                "",
                "```json",
                json.dumps(answer_template if isinstance(answer_template, dict) else {}, indent=2),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Source Edit Plan",
            "",
            *_source_edit_plan_lines(source_edit_plan or []),
            "",
            "## Agent Instructions",
            "",
        ]
    )
    if decision == "repeated_command_action":
        lines.extend(
            [
                "The command-type next action already ran once in this advance run, and readiness still returned the same action.",
                "Inspect the generated reports and patch workspace source files rather than rerunning the same command blindly.",
                "",
                f"```bash\n{command}\n```",
            ]
        )
    elif decision == "command_failed" and command:
        lines.extend(
            [
                "The recommended command failed during this advance run.",
                "Inspect `build/workspace_advance_report.json` for the command stderr/stdout, then patch the listed source files or rerun the command after repairing inputs.",
                "",
                f"```bash\n{command}\n```",
            ]
        )
    elif action.get("action_type") == "run_command" and command:
        lines.extend(
            [
                "Run or inspect the recommended command, then rerun readiness.",
                "",
                f"```bash\n{command}\n```",
            ]
        )
    elif action.get("kind") == "author_design_contract_from_prompt":
        lines.extend(
            [
                "Emit or inspect the reproducible design-contract prompt, then author strict `deck_design_contract_v1` JSON in workspace source.",
                "Save the result as `design_contract.json`; do not proceed to outline authoring until `apply_design_contract.py` has applied it.",
                "",
                f"```bash\n{phase_command}\n```" if phase_command else "",
                "",
                "After saving `design_contract.json`, rerun `scripts/report_workspace_readiness.py` or `scripts/advance_workspace.py --execute` to apply it.",
            ]
        )
    elif action.get("kind") == "author_outline_from_contract":
        lines.extend(
            [
                "Emit or inspect the contract-aware outline authoring prompt, then patch workspace source files only.",
                "The prompt is a handoff aid; the main agent still owns final source edits and fact/source verification.",
                "",
                f"```bash\n{phase_command}\n```" if phase_command else "",
                "",
                "After editing, rerun `scripts/report_workspace_readiness.py` and then the strict workspace build.",
            ]
        )
    elif action.get("kind") and action.get("kind") != "none":
        lines.extend(
            [
                "Patch workspace source files only; do not patch generated PPTX files.",
                "Keep changes scoped to the listed slide IDs when slide IDs are provided.",
                "After editing, rerun `scripts/report_workspace_readiness.py` and then the strict workspace build.",
            ]
        )
    else:
        lines.append("No source-level action is required before build/QA.")
    lines.append("")
    return "\n".join(lines)


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
        "suggested_variants",
        "suggested_fields",
        "dominant_variant",
        "dominant_ratio",
        "warning_types",
        "qa_report",
        "design_report",
        "visual_report",
        "visual_review_report",
        "reference_pptx_candidates",
        "data_paths",
        "stale_source_files",
        "stale_artifact_dependencies",
        "artifact_manifest",
        "analysis_summary",
        "analysis_summary_markdown",
        "artifact_output_ids",
        "artifact_aliases",
        "style_status",
        "style_report",
        "style_fragment",
        "style_apply_report",
        "intake_status",
        "deck_start_packet",
        "intake_answers",
        "intake_apply_report",
        "intake_error",
        "answer_template",
        "questions",
        "design_contract_status",
        "design_contract",
        "design_contract_apply_report",
        "design_contract_error",
        "outline_handoff_status",
        "outline_handoff",
        "outline_handoff_apply_report",
        "outline_handoff_error",
        "patch_fields",
        "source_footer_report",
        "failed_step",
        "returncode",
        "qa_counts",
    )
    return {key: action.get(key) for key in keep if key in action}


def _is_blocking_command_returncode(kind: str, returncode: int) -> bool:
    if kind in {"resolve_planning_warnings", "polish_preflight_warnings"} and returncode in {0, 1}:
        return False
    return returncode != 0


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run workspace readiness, optionally execute command-type next actions, "
            "and write an agent-facing next-action prompt."
        )
    )
    parser.add_argument("--workspace", required=True, help="Workspace created by init_deck_workspace.py")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute command-type next actions. Without this, only reports the next action.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=3,
        help="Maximum readiness/action loops when --execute is set.",
    )
    parser.add_argument(
        "--report",
        default="build/workspace_advance_report.json",
        help="Workspace-relative or absolute path for the advance report.",
    )
    parser.add_argument(
        "--next-action-markdown",
        default="build/workspace_next_action.md",
        help="Workspace-relative or absolute path for the agent-facing next-action prompt.",
    )
    parser.add_argument(
        "--readiness-report",
        default="build/workspace_readiness.json",
        help="Workspace-relative or absolute path for the readiness JSON report.",
    )
    parser.add_argument(
        "--readiness-markdown",
        default="build/workspace_readiness.md",
        help="Workspace-relative or absolute path for the readiness Markdown report.",
    )
    parser.add_argument(
        "--skip-readiness-markdown",
        action="store_true",
        help="Do not write the readiness Markdown report during the loop.",
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
    readiness_report = _workspace_path(workspace, args.readiness_report)
    readiness_markdown = _workspace_path(workspace, args.readiness_markdown)

    steps: list[dict[str, Any]] = []
    executed_signatures: set[str] = set()
    final_report: dict[str, Any] = {}
    final_decision = "not_started"
    exit_code = 1

    for step_number in range(1, max_steps + 1):
        readiness_rc, readiness, readiness_stderr = _run_readiness(
            repo=repo,
            workspace=workspace,
            report_path=readiness_report,
            markdown_path=readiness_markdown,
            write_markdown=not args.skip_readiness_markdown,
        )
        action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
        status = str(readiness.get("status") or "")
        kind = str(action.get("kind") or "none")
        action_type = str(action.get("action_type") or "none")
        final_report = readiness
        artifact_context = _artifact_context_summary(readiness)
        step_entry: dict[str, Any] = {
            "step": step_number,
            "readiness_returncode": readiness_rc,
            "status": status,
            "status_reasons": readiness.get("status_reasons", []),
            "next_action": _compact_action(action),
            "execution_plan": _compact_execution_plan(readiness.get("execution_plan")),
            "reproducibility_contract": _reproducibility_contract_summary(readiness),
            "quality_context": _quality_context_summary(readiness),
            "artifact_context": artifact_context,
            "readiness_stderr_tail": readiness_stderr[-1200:],
        }

        if not readiness:
            step_entry["decision"] = "readiness_json_unavailable"
            steps.append(step_entry)
            final_decision = "readiness_json_unavailable"
            exit_code = 2
            break
        if status == "ready" or kind == "none":
            step_entry["decision"] = "ready"
            steps.append(step_entry)
            final_decision = "ready"
            exit_code = 0
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
        if _is_blocking_command_returncode(kind, command_rc):
            final_decision = "command_failed"
            exit_code = 2
            break
    else:
        final_decision = "max_steps_reached"
        exit_code = 1

    next_prompt_changed = False
    source_edit_plan = _source_edit_plan(final_report, decision=final_decision) if final_report else []
    if final_report:
        next_prompt_changed = _write_text_if_changed(
            next_prompt_path,
            _next_action_prompt(
                final_report,
                decision=final_decision,
                source_edit_plan=source_edit_plan,
            ),
        )
    payload = {
        "schema_version": 1,
        "workspace": str(workspace),
        "execute": bool(args.execute),
        "max_steps": max_steps,
        "decision": final_decision,
        "final_status": final_report.get("status") if isinstance(final_report, dict) else "",
        "final_status_reasons": (
            final_report.get("status_reasons") if isinstance(final_report, dict) else []
        ),
        "final_next_action": _compact_action(
            final_report.get("next_action") if isinstance(final_report, dict) else {}
        ),
        "final_execution_plan": _compact_execution_plan(
            final_report.get("execution_plan") if isinstance(final_report, dict) else {}
        ),
        "reproducibility_contract": (
            _reproducibility_contract_summary(final_report) if isinstance(final_report, dict) else {}
        ),
        "quality_context": (
            _quality_context_summary(final_report) if isinstance(final_report, dict) else {}
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
        "steps": steps,
        "reports": {
            "advance": _display_path(workspace, report_path),
            "readiness": _display_path(workspace, readiness_report),
            "readiness_markdown": (
                "" if args.skip_readiness_markdown else _display_path(workspace, readiness_markdown)
            ),
            "next_action_markdown": _display_path(workspace, next_prompt_path),
        },
    }
    report_changed = _write_json_if_changed(report_path, payload)
    print(json.dumps(payload, indent=2))
    print(
        "[advance_workspace] "
        f"decision={final_decision} status={payload['final_status']} "
        f"next_action={payload['final_next_action'].get('kind', 'none')} "
        f"phase={payload['final_execution_plan'].get('current_phase_id', '') or payload['final_execution_plan'].get('current_phase_status', 'none')} "
        f"report={_display_path(workspace, report_path)} changed={int(report_changed)} "
        f"next_prompt={_display_path(workspace, next_prompt_path)} changed={int(next_prompt_changed)}",
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
