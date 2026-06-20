#!/usr/bin/env python3
"""Report whether a workspace build is ready for delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from office_package_hash import (
    OFFICE_PACKAGE_HASH_ALGORITHM,
    is_office_package_path,
    office_package_normalized_sha256,
)

DEFAULT_CONTENT_DENSITY_FLOOR = 0.55


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _scout_analysis_markdown_lines(label: str, scout: Any) -> list[str]:
    if not isinstance(scout, dict) or not scout:
        return []

    def count(key: str) -> int:
        try:
            return int(scout.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return [
        f"- {label}: "
        f"present=`{bool(scout.get('present'))}` "
        f"persisted=`{bool(scout.get('persisted'))}` "
        f"applied=`{bool(scout.get('applied'))}` "
        f"tasks=`{count('analysis_task_count')}` "
        f"findings=`{count('computed_finding_count')}` "
        f"visuals=`{count('visual_recommendation_count')}` "
        f"bindings=`{count('outline_binding_count')}` "
        f"targets=`{_limited_markdown_list(scout.get('target_slide_ids'), limit=4)}` "
        f"variants=`{_limited_markdown_list(scout.get('variants'), limit=4)}` "
        f"open_questions=`{count('open_question_count')}`"
    ]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _compact_phase_proof_summary(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    candidates = (
        ("readiness.execution_plan", readiness_payload.get("execution_plan")),
        ("readiness.deck_intake", readiness_payload.get("deck_intake")),
    )
    proof: dict[str, Any] = {}
    source = ""
    for candidate_source, candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw_proof = candidate.get("phase_proof_ledger")
        if isinstance(raw_proof, dict) and raw_proof:
            proof = raw_proof
            source = candidate_source
            break
    if not proof:
        return {
            "exists": False,
            "valid": False,
            "ledger_version": "",
            "plan_version": "",
            "phase_count": 0,
            "phase_ids": [],
            "route_required_phase_ids": [],
            "acceptance_gate_ids": [],
            "acceptance_gate_count": 0,
            "phase_acceptance_gate_ids": {},
            "phase_proof_counts": {},
            "phase_proof_files": {},
            "proof_path_count": 0,
            "proof_file_count": 0,
            "existing_file_count": 0,
            "missing_file_count": 0,
            "missing_files": [],
            "phase_count_matches_execution_plan": False,
            "source": "",
        }

    phase_files: dict[str, Any] = {}
    raw_phase_files = proof.get("phase_proof_files")
    if isinstance(raw_phase_files, dict):
        for phase_id, item in raw_phase_files.items():
            if not isinstance(item, dict):
                continue
            phase_key = str(phase_id).strip()
            if not phase_key:
                continue
            phase_files[phase_key] = {
                "proof_file_count": _int_value(item.get("proof_file_count")),
                "existing_file_count": _int_value(item.get("existing_file_count")),
                "missing_file_count": _int_value(item.get("missing_file_count")),
                "missing_files": _string_list(item.get("missing_files")),
            }

    phase_acceptance_gate_ids: dict[str, list[str]] = {}
    raw_phase_gates = proof.get("phase_acceptance_gate_ids")
    if isinstance(raw_phase_gates, dict):
        for phase_id, gates in raw_phase_gates.items():
            phase_key = str(phase_id).strip()
            if phase_key:
                phase_acceptance_gate_ids[phase_key] = _string_list(gates)

    phase_proof_counts: dict[str, int] = {}
    raw_proof_counts = proof.get("phase_proof_counts")
    if isinstance(raw_proof_counts, dict):
        for phase_id, count in raw_proof_counts.items():
            phase_key = str(phase_id).strip()
            if phase_key:
                phase_proof_counts[phase_key] = _int_value(count)

    return {
        "exists": bool(proof.get("exists")),
        "valid": bool(proof.get("valid")),
        "ledger_version": str(proof.get("ledger_version") or "").strip(),
        "plan_version": str(proof.get("plan_version") or "").strip(),
        "phase_count": _int_value(proof.get("phase_count")),
        "phase_ids": _string_list(proof.get("phase_ids")),
        "route_required_phase_ids": _string_list(proof.get("route_required_phase_ids")),
        "status_sources": _string_list(proof.get("status_sources")),
        "acceptance_gate_ids": _string_list(proof.get("acceptance_gate_ids")),
        "acceptance_gate_count": _int_value(proof.get("acceptance_gate_count")),
        "phase_acceptance_gate_ids": phase_acceptance_gate_ids,
        "phase_proof_counts": phase_proof_counts,
        "phase_proof_files": phase_files,
        "proof_path_count": _int_value(proof.get("proof_path_count")),
        "proof_file_count": _int_value(proof.get("proof_file_count")),
        "existing_file_count": _int_value(proof.get("existing_file_count")),
        "missing_file_count": _int_value(proof.get("missing_file_count")),
        "missing_files": _string_list(proof.get("missing_files")),
        "phase_count_matches_execution_plan": bool(
            proof.get("phase_count_matches_execution_plan")
        ),
        "source": source,
    }


def _compact_data_handoff_summary(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    handoff = (
        readiness_payload.get("data_analysis_handoff")
        if isinstance(readiness_payload.get("data_analysis_handoff"), dict)
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


def _compact_build_speed(payload: dict[str, Any]) -> dict[str, Any]:
    speed = payload.get("speed") if isinstance(payload.get("speed"), dict) else {}
    if not speed:
        return {}
    steps = speed.get("steps") if isinstance(speed.get("steps"), list) else []
    step_durations: dict[str, int] = {}
    for item in steps:
        if not isinstance(item, dict):
            continue
        step = str(item.get("step") or "").strip()
        if step:
            step_durations[step] = _int_value(item.get("duration_ms"))
    longest = speed.get("longest_step") if isinstance(speed.get("longest_step"), dict) else {}
    if not longest and step_durations:
        longest_name, longest_ms = max(step_durations.items(), key=lambda item: item[1])
        longest = {"step": longest_name, "duration_ms": longest_ms}
    return {
        "schema": str(speed.get("schema") or "").strip(),
        "total_duration_ms": _int_value(speed.get("total_duration_ms")),
        "step_count": _int_value(speed.get("step_count"), len(step_durations)),
        "renderer_used": str(speed.get("renderer_used") or "").strip(),
        "fast_first_pass": bool(speed.get("fast_first_pass")),
        "skip_render": bool(speed.get("skip_render")),
        "visual_review": bool(speed.get("visual_review")),
        "longest_step": {
            "step": str(longest.get("step") or "").strip(),
            "duration_ms": _int_value(longest.get("duration_ms")),
        },
        "step_durations_ms": step_durations,
    }


def _build_speed_markdown_line(speed: Any, *, label: str = "Build speed") -> str:
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


def _data_handoff_markdown_lines(readiness: dict[str, Any]) -> list[str]:
    handoff = (
        readiness.get("data_analysis_handoff")
        if isinstance(readiness.get("data_analysis_handoff"), dict)
        else {}
    )
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
    lines.extend(_scout_analysis_markdown_lines("Data scout analysis", handoff.get("scout_analysis")))
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


def _build_data_handoff_markdown_lines(build: dict[str, Any]) -> list[str]:
    handoff = (
        build.get("data_analysis_handoff")
        if isinstance(build.get("data_analysis_handoff"), dict)
        else {}
    )
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
    lines.extend(_scout_analysis_markdown_lines("Build data scout analysis", handoff.get("scout_analysis")))
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


def _compact_artifact_context(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    artifacts = (
        readiness_payload.get("artifacts")
        if isinstance(readiness_payload.get("artifacts"), dict)
        else {}
    )
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
    context: dict[str, Any] = {}
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
        context["artifact_manifest"] = {
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
        context["artifact_selection"] = {
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
        context["tabular_data"] = tabular_data
    return context


def _artifact_context_markdown_lines(context: Any) -> list[str]:
    if not isinstance(context, dict) or not context:
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


def _compact_workspace_source_inventory(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    deck_intake = (
        readiness_payload.get("deck_intake")
        if isinstance(readiness_payload.get("deck_intake"), dict)
        else {}
    )
    inventory = (
        deck_intake.get("workspace_source_inventory")
        if isinstance(deck_intake.get("workspace_source_inventory"), dict)
        else {}
    )
    packet = inventory.get("packet") if isinstance(inventory.get("packet"), dict) else {}
    seed = (
        inventory.get("choice_resolution_seed")
        if isinstance(inventory.get("choice_resolution_seed"), dict)
        else {}
    )
    source = "choice_resolution_seed" if seed.get("exists") else ("packet" if packet.get("exists") else "")
    current = seed if source == "choice_resolution_seed" else packet if source == "packet" else {}
    return {
        "exists": bool(current.get("exists")),
        "source": source,
        "data_file_count": _int_value(current.get("data_file_count")),
        "data_file_shown_count": _int_value(current.get("data_file_shown_count")),
        "reference_pptx_count": _int_value(current.get("reference_pptx_count")),
        "reference_pptx_shown_count": _int_value(current.get("reference_pptx_shown_count")),
        "artifact_ledger_count": _int_value(current.get("artifact_ledger_count")),
        "data_paths": _string_list(current.get("data_paths")),
        "reference_pptx_paths": _string_list(current.get("reference_pptx_paths")),
        "artifact_ledger_paths": _string_list(current.get("artifact_ledger_paths")),
        "packet": packet,
        "choice_resolution_seed": seed,
    }


def _source_inventory_markdown_lines(inventory: Any) -> list[str]:
    if not isinstance(inventory, dict) or not inventory.get("exists"):
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


def _compact_resolved_treatment_summary(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    style = (
        readiness_payload.get("style")
        if isinstance(readiness_payload.get("style"), dict)
        else {}
    )
    summary = (
        style.get("resolved_treatment_summary")
        if isinstance(style.get("resolved_treatment_summary"), dict)
        else {}
    )
    if not summary:
        return {}
    by_slide = (
        summary.get("header_variant_by_slide")
        if isinstance(summary.get("header_variant_by_slide"), list)
        else []
    )
    counts = (
        summary.get("header_variant_counts")
        if isinstance(summary.get("header_variant_counts"), dict)
        else {}
    )
    return {
        "header_variant_by_slide": [item for item in by_slide if isinstance(item, dict)],
        "header_variant_counts": {
            str(key): _int_value(value)
            for key, value in sorted(counts.items())
            if str(key).strip()
        },
        "unique_header_variant_count": _int_value(summary.get("unique_header_variant_count")),
    }


def _resolved_treatment_markdown_lines(summary: Any) -> list[str]:
    if not isinstance(summary, dict) or not summary:
        return ["- Resolved header variants: `none`"]
    counts = summary.get("header_variant_counts")
    counts_text = json.dumps(counts, sort_keys=True) if isinstance(counts, dict) else "{}"
    return [
        "- Resolved header variants: "
        f"unique=`{int(summary.get('unique_header_variant_count') or 0)}` "
        f"counts=`{counts_text}`"
    ]


def _compact_reproducibility_contract(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    design_contract = (
        readiness_payload.get("design_contract")
        if isinstance(readiness_payload.get("design_contract"), dict)
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


def _reproducibility_contract_markdown_lines(replay: Any) -> list[str]:
    if not isinstance(replay, dict) or not replay:
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


def _compact_quality_context(readiness_payload: dict[str, Any]) -> dict[str, Any]:
    design_contract = (
        readiness_payload.get("design_contract")
        if isinstance(readiness_payload.get("design_contract"), dict)
        else {}
    )
    slide_quality = (
        design_contract.get("slide_quality_contract")
        if isinstance(design_contract.get("slide_quality_contract"), dict)
        else {}
    )
    outline_handoff = (
        readiness_payload.get("outline_authoring_handoff")
        if isinstance(readiness_payload.get("outline_authoring_handoff"), dict)
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


def _quality_context_markdown_lines(quality: Any) -> list[str]:
    if not isinstance(quality, dict) or not quality:
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


def _layout_density_markdown_lines(density: Any) -> list[str]:
    if not isinstance(density, dict) or not density.get("exists"):
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


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _run_readiness(
    *,
    repo: Path,
    workspace: Path,
    report_path: Path,
    markdown_path: Path,
) -> tuple[int, dict[str, Any], str]:
    cmd = [
        sys.executable,
        str(repo / "scripts" / "report_workspace_readiness.py"),
        "--workspace",
        str(workspace),
        "--report",
        str(report_path),
        "--markdown-report",
        str(markdown_path),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    payload: dict[str, Any] = {}
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    return result.returncode, payload, result.stderr


def _counts(section: Any) -> dict[str, int]:
    raw = section.get("counts") if isinstance(section, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    return {str(key): int(value or 0) for key, value in raw.items() if isinstance(value, (int, float))}


def _positive_counts(counts: dict[str, int], keys: list[str]) -> dict[str, int]:
    return {key: int(counts.get(key, 0)) for key in keys if int(counts.get(key, 0)) > 0}


def _has_flag(command: Any, flag: str) -> bool:
    return isinstance(command, list) and flag in {str(item) for item in command}


def _dedupe_text(values: Any) -> list[str]:
    items: list[str] = []
    if not isinstance(values, list):
        return items
    for value in values:
        text = str(value or "").strip()
        if text and text not in items:
            items.append(text)
    return items


def _route_active_from_summary(summary: Any, route_id: str) -> bool | None:
    if not isinstance(summary, dict):
        return None
    choice = (
        summary.get("choice_resolution")
        if isinstance(summary.get("choice_resolution"), dict)
        else summary.get("choice_resolution_seed")
    )
    candidates = [choice, summary] if isinstance(choice, dict) else [summary]
    seen: set[int] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        if route_id == "rendered_visual_review":
            required = candidate.get("rendered_visual_review_required")
            if isinstance(required, bool):
                return required
        for key in ("route_ledger_status", "route_status"):
            status = candidate.get(key)
            if isinstance(status, dict) and route_id in status:
                return bool(status.get(route_id))
        route_ledger = candidate.get("route_decision_ledger")
        routes = route_ledger.get("routes") if isinstance(route_ledger, dict) else []
        if isinstance(routes, list):
            for item in routes:
                if isinstance(item, dict) and str(item.get("id") or "").strip() == route_id:
                    return bool(item.get("active"))
        route_decisions = candidate.get("route_decisions")
        if isinstance(route_decisions, list):
            for item in route_decisions:
                if isinstance(item, dict) and str(item.get("id") or "").strip() == route_id:
                    return bool(item.get("active"))
        for key in ("route_ledger_active_routes", "active_routes", "required_by_route_ledger"):
            active_routes = candidate.get(key)
            if isinstance(active_routes, list) and route_id in {str(item) for item in active_routes}:
                return True
    return None


def _route_requirement_from_readiness(
    readiness_payload: dict[str, Any],
    route_id: str,
) -> dict[str, Any]:
    sources: list[str] = []
    inactive_sources: list[str] = []
    candidates = (
        ("readiness.execution_plan", readiness_payload.get("execution_plan")),
        ("readiness.deck_intake", readiness_payload.get("deck_intake")),
        ("readiness.design_contract", readiness_payload.get("design_contract")),
    )
    for source, candidate in candidates:
        active = _route_active_from_summary(candidate, route_id)
        if active is True:
            sources.append(source)
        elif active is False:
            inactive_sources.append(source)
    return {
        "required": bool(sources),
        "route_id": route_id,
        "sources": sources,
        "inactive_sources": inactive_sources,
    }


def _contract_evidence_path(raw: str) -> str:
    text = str(raw or "").strip().strip("`")
    if not text:
        return ""
    token = text.split()[0].strip("`'\",;")
    if token.startswith("<deck>/"):
        token = token[len("<deck>/") :]
    path_part = token.split(":", 1)[0]
    suffix = Path(path_part).suffix.lower()
    if suffix in {".json", ".md", ".pptx", ".csv", ".tsv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg"}:
        return path_part
    return ""


def _acceptance_evidence_summary(
    *,
    workspace: Path,
    design: dict[str, Any],
    self_output_paths: set[Path],
) -> dict[str, Any]:
    qa_contract = (
        design.get("qa_contract")
        if isinstance(design.get("qa_contract"), dict)
        else {}
    )
    raw_lists = (
        design.get("acceptance_evidence"),
        qa_contract.get("acceptance_evidence") if isinstance(qa_contract, dict) else None,
        qa_contract.get("evidence_files") if isinstance(qa_contract, dict) else None,
        qa_contract.get("verification_evidence") if isinstance(qa_contract, dict) else None,
    )
    items: list[str] = []
    for raw in raw_lists:
        for item in _dedupe_text(raw):
            if item not in items:
                items.append(item)

    files: list[dict[str, Any]] = []
    seen_file_paths: set[Path] = set()
    resolved_self_paths = {path.resolve() for path in self_output_paths}
    for item in items:
        path_text = _contract_evidence_path(item)
        if not path_text:
            continue
        path = _workspace_path(workspace, path_text)
        resolved_path = path.resolve()
        if resolved_path in seen_file_paths:
            continue
        seen_file_paths.add(resolved_path)
        is_self_output = resolved_path in resolved_self_paths
        exists = path.exists()
        snapshot: dict[str, Any] = {
            "path": _display_path(workspace, path),
            "exists": exists,
            "self_output": is_self_output,
            "satisfied": exists or is_self_output,
        }
        if exists and path.is_file():
            try:
                snapshot["sha256"] = _file_sha256(path)
                snapshot["size_bytes"] = path.stat().st_size
                if is_office_package_path(path):
                    snapshot["normalized_sha256"] = office_package_normalized_sha256(path)
                    snapshot["normalized_sha256_algorithm"] = OFFICE_PACKAGE_HASH_ALGORITHM
            except OSError as exc:
                snapshot["read_error"] = str(exc)
                snapshot["satisfied"] = False
            except Exception as exc:
                snapshot["normalized_hash_error"] = str(exc)
        files.append(snapshot)

    missing_files = [
        str(item.get("path") or "")
        for item in files
        if isinstance(item, dict) and not item.get("exists")
    ]
    blocking_missing_files = [
        str(item.get("path") or "")
        for item in files
        if isinstance(item, dict) and not item.get("satisfied")
    ]
    return {
        "checked": bool(items),
        "items": items,
        "item_count": len(items),
        "files": files,
        "file_count": len(files),
        "existing_file_count": len([item for item in files if item.get("exists")]),
        "self_output_count": len([item for item in files if item.get("self_output")]),
        "missing_files": missing_files,
        "blocking_missing_files": blocking_missing_files,
        "blocking_missing_file_count": len(blocking_missing_files),
    }


def _report_payload_from_build(
    workspace: Path,
    build_payload: dict[str, Any],
    name: str,
) -> tuple[dict[str, Any], str]:
    reports = build_payload.get("reports") if isinstance(build_payload.get("reports"), dict) else {}
    item = reports.get(name) if isinstance(reports, dict) else {}
    if not isinstance(item, dict):
        return {}, ""
    path_text = str(item.get("path") or "").strip()
    if not path_text:
        return {}, ""
    payload = _load_json(_workspace_path(workspace, path_text), {})
    return (payload if isinstance(payload, dict) else {}), path_text


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _rounded_float(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _compact_layout_density(
    workspace: Path,
    build_payload: dict[str, Any],
    *,
    content_floor: float = DEFAULT_CONTENT_DENSITY_FLOOR,
) -> dict[str, Any]:
    qa_payload, qa_path = _report_payload_from_build(workspace, build_payload, "qa")
    raw_scores = (
        qa_payload.get("density_score_by_slide")
        if isinstance(qa_payload.get("density_score_by_slide"), list)
        else []
    )
    scores: list[dict[str, Any]] = []
    for raw in raw_scores:
        if not isinstance(raw, dict):
            continue
        slide_index_raw = raw.get("slide_index")
        if (
            not isinstance(slide_index_raw, (int, float))
            or isinstance(slide_index_raw, bool)
        ):
            continue
        density_score = _float_value(raw.get("density_score"))
        scores.append(
            {
                "slide_index": int(slide_index_raw),
                "density_score": _rounded_float(density_score),
            }
        )

    content_scores = [
        item
        for item in scores
        if isinstance(item.get("slide_index"), int) and int(item.get("slide_index")) > 0
    ]
    numeric_content_scores = [
        float(item["density_score"])
        for item in content_scores
        if isinstance(item.get("density_score"), (int, float))
        and not isinstance(item.get("density_score"), bool)
    ]
    low_content_scores = [
        item
        for item in content_scores
        if not isinstance(item.get("density_score"), (int, float))
        or isinstance(item.get("density_score"), bool)
        or float(item.get("density_score")) < float(content_floor)
    ]
    return {
        "exists": bool(scores),
        "source": qa_path,
        "slide_count": len(scores),
        "content_slide_count": len(content_scores),
        "content_density_floor": _rounded_float(content_floor),
        "min_content_density_score": _rounded_float(min(numeric_content_scores))
        if numeric_content_scores
        else None,
        "max_content_density_score": _rounded_float(max(numeric_content_scores))
        if numeric_content_scores
        else None,
        "average_content_density_score": _rounded_float(
            sum(numeric_content_scores) / len(numeric_content_scores)
        )
        if numeric_content_scores
        else None,
        "low_content_density_count": len(low_content_scores),
        "low_content_density_slides": low_content_scores,
        "density_score_by_slide": scores,
    }


def _quality_requires_whitespace_polish(quality_context: Any) -> bool:
    if not isinstance(quality_context, dict):
        return False
    slide_quality = (
        quality_context.get("slide_quality_contract")
        if isinstance(quality_context.get("slide_quality_contract"), dict)
        else {}
    )
    return bool(slide_quality.get("fail_on_awkward_whitespace"))


def _layout_density_low_count(layout_density: Any) -> int:
    if not isinstance(layout_density, dict):
        return 0
    return _int_value(layout_density.get("low_content_density_count"))


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
    if "source" in normalized:
        return ["sources", "refs", "references", "footer"]
    if "chart" in normalized:
        return ["variant", "chart", "assets.chart_data", "chart.options"]
    if "table" in normalized:
        return ["variant", "table", "assets.table_data"]
    if "figure" in normalized or "whitespace" in normalized:
        return ["variant", "assets", "figures", "figure_export_contract"]
    return ["outline.json"]


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
        return ["footer", "sources", "refs", "readability_contract.footer_reserved_inches", "variant"]
    if normalized.startswith("table_") or normalized_role == "table":
        return ["table", "tables", "table_groups", "readability_contract.min_body_pt"]
    if normalized.startswith("title_") or normalized_role in {"title", "headline", "heading"}:
        return ["title", "subtitle", "kicker", "readability_contract.min_title_pt"]
    if normalized.startswith("caption_") or normalized_role in {"caption", "source", "sources", "refs"}:
        return ["caption", "figure_caption", "sources", "refs", "readability_contract.min_caption_pt"]
    if normalized.endswith("_font_too_small"):
        return ["body", "bullets", "columns", "cards", "summary_callout", "readability_contract.min_body_pt"]
    return ["variant", "body", "chart.options", "table", "figures", "readability_contract"]


def _qa_whitespace_suggested_fields(warning_type: str) -> list[str]:
    normalized = warning_type.strip().lower()
    if normalized == "content_span_too_short":
        return ["variant", "body", "bullets", "summary_callout", "chart", "table", "figures", "assets"]
    if normalized == "content_span_too_narrow":
        return ["variant", "columns", "body", "chart", "table", "figures", "assets", "sidebar_sections"]
    if normalized == "empty_ratio_too_high":
        return ["variant", "body", "stats", "chart", "table", "figures", "assets", "summary_callout"]
    return ["variant", "body", "assets", "chart", "table", "figures"]


def _qa_geometry_suggested_fields(warning_type: str) -> list[str]:
    normalized = warning_type.strip().lower()
    if normalized == "density_too_high":
        return ["variant", "body", "bullets", "chart", "table", "figures", "assets", "layout_recommendation"]
    return ["variant", "body", "assets", "chart", "table", "figures", "layout_recommendation"]


def _planning_suggested_fields(path: str, message: str = "") -> list[str]:
    normalized = f"{path}\n{message}".lower()
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
    if path:
        parts = [part for part in path.split(".") if part]
        return [".".join(parts[:2])] if len(parts) >= 2 else [path]
    return ["workspace planning sources"]


def _delivery_warning_metadata(
    workspace: Path,
    build_payload: dict[str, Any],
    report_counts: dict[str, dict[str, int]],
    layout_density: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    warning_types: list[str] = []
    suggested_fields: list[str] = []
    planning_paths: list[str] = []
    slide_ids: list[str] = []

    def add_fields(fields: list[str]) -> None:
        for field in fields:
            if field and field not in suggested_fields:
                suggested_fields.append(field)

    planning_counts = report_counts.get("planning", {})
    if int(planning_counts.get("error_count") or 0) > 0 or int(planning_counts.get("warning_count") or 0) > 0:
        planning_payload, _planning_path = _report_payload_from_build(workspace, build_payload, "planning")
        for issue in planning_payload.get("issues", []) if isinstance(planning_payload, dict) else []:
            if not isinstance(issue, dict):
                continue
            path = str(issue.get("path") or "").strip()
            rule = str(issue.get("rule") or "").strip() or (path.split(".", 1)[0] if path else "")
            if rule and rule not in warning_types:
                warning_types.append(rule)
            if path and path not in planning_paths:
                planning_paths.append(path)
            add_fields(_planning_suggested_fields(path, str(issue.get("message") or "")))

    preflight_counts = report_counts.get("preflight", {})
    if int(preflight_counts.get("error_count") or 0) > 0 or int(preflight_counts.get("warning_count") or 0) > 0:
        preflight_payload, _preflight_path = _report_payload_from_build(workspace, build_payload, "preflight")
        for issue in preflight_payload.get("issues", []) if isinstance(preflight_payload, dict) else []:
            if not isinstance(issue, dict):
                continue
            rule = str(issue.get("rule") or "").strip()
            if rule and rule not in warning_types:
                warning_types.append(rule)
            slide_id = str(issue.get("slide_id") or "").strip()
            if slide_id and slide_id not in slide_ids:
                slide_ids.append(slide_id)
            add_fields(_preflight_suggested_fields(rule))

    qa_counts = report_counts.get("qa", {})
    if any(int(qa_counts.get(key) or 0) > 0 for key in ("geometry_warning_count", "whitespace_warning_count", "design_warning_count", "visual_warning_count", "visual_review_warning_count")):
        qa_payload, _qa_path = _report_payload_from_build(workspace, build_payload, "qa")
        geometry = qa_payload.get("geometry_violations") if isinstance(qa_payload.get("geometry_violations"), list) else []
        for issue in geometry:
            if not isinstance(issue, dict):
                continue
            if str(issue.get("severity") or "").strip().lower() != "warning":
                continue
            warning_type = str(issue.get("type") or "").strip()
            if warning_type and warning_type not in warning_types:
                warning_types.append(warning_type)
            slide_index = issue.get("slide_index")
            if isinstance(slide_index, int) and slide_index >= 0:
                slide_label = f"slide_index:{slide_index}"
                if slide_label not in slide_ids:
                    slide_ids.append(slide_label)
            add_fields(_qa_geometry_suggested_fields(warning_type))
        whitespace = qa_payload.get("whitespace_warnings") if isinstance(qa_payload.get("whitespace_warnings"), list) else []
        for issue in whitespace:
            if not isinstance(issue, dict):
                continue
            warning_type = str(issue.get("type") or "").strip()
            if warning_type and warning_type not in warning_types:
                warning_types.append(warning_type)
            slide_id = str(issue.get("slide_id") or issue.get("slide") or "").strip()
            if slide_id and slide_id not in slide_ids:
                slide_ids.append(slide_id)
            add_fields(_qa_whitespace_suggested_fields(warning_type))
        design_report = str(qa_payload.get("design_report") or "").strip()
        if design_report and int(qa_counts.get("design_warning_count") or 0) > 0:
            design_payload = _load_json(_workspace_path(workspace, design_report), {})
            for issue in design_payload.get("issues", []) if isinstance(design_payload, dict) else []:
                if not isinstance(issue, dict):
                    continue
                if str(issue.get("severity") or "").strip().lower() == "error":
                    continue
                warning_type = str(issue.get("type") or "").strip()
                if warning_type and warning_type not in warning_types:
                    warning_types.append(warning_type)
                add_fields(_qa_design_suggested_fields(warning_type, issue.get("role")))
    density = layout_density if isinstance(layout_density, dict) else {}
    low_density = (
        density.get("low_content_density_slides")
        if isinstance(density.get("low_content_density_slides"), list)
        else []
    )
    if low_density:
        if "layout_density_low" not in warning_types:
            warning_types.append("layout_density_low")
        for item in low_density:
            if not isinstance(item, dict):
                continue
            slide_index = item.get("slide_index")
            if isinstance(slide_index, int) and slide_index >= 0:
                slide_label = f"slide_index:{slide_index}"
                if slide_label not in slide_ids:
                    slide_ids.append(slide_label)
        add_fields(_qa_whitespace_suggested_fields("empty_ratio_too_high"))
        add_fields(
            [
                "readability_contract",
                "slide_quality_contract.layout_targets.fail_on_awkward_whitespace",
                "quality_alignment.layout_targets_used",
            ]
        )
    return {
        "warning_types": warning_types,
        "suggested_fields": suggested_fields,
        "planning_paths": planning_paths,
        "slide_ids": slide_ids,
    }


def _recommended_delivery_action(
    *,
    blocking_reasons: list[str],
    warning_reasons: list[str],
    readiness_next_action: Any,
    strict_build_command: list[str],
    visual_review_build_command: list[str] | None = None,
    warning_metadata: dict[str, list[str]] | None = None,
    acceptance_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness_action = dict(readiness_next_action) if isinstance(readiness_next_action, dict) else {}
    readiness_kind = str(readiness_action.get("kind") or "none").strip() or "none"
    if readiness_kind != "none":
        return readiness_action
    if "visual_review_not_run" in warning_reasons or "visual_review_not_run" in blocking_reasons:
        return {
            "kind": "run_visual_review_delivery_build",
            "priority": 62,
            "action_type": "run_command",
            "reason": (
                "Rendered visual review is required for this workspace, but the latest build "
                "did not run it. Run a strict final build with visual review before delivery."
            ),
            "command": visual_review_build_command or strict_build_command,
            "warning_types": ["visual_review_not_run"],
        }
    final_build_reasons = [
        reason
        for reason in (
            "missing_build_report",
            "missing_output_pptx",
            "qa_not_run",
            "fast_first_pass_not_final",
            "render_skipped",
            "planning_warnings_not_blocking",
            "whitespace_warnings_not_blocking",
        )
        if reason in warning_reasons or reason in blocking_reasons
    ]
    if final_build_reasons:
        return {
            "kind": "run_final_delivery_build",
            "priority": 60,
            "action_type": "run_command",
            "reason": (
                "The workspace is missing a strict final delivery build or the latest build is "
                "not a strict final delivery build. Run the strict final build before delivery."
            ),
            "command": strict_build_command,
            "warning_types": final_build_reasons,
        }
    acceptance = acceptance_evidence if isinstance(acceptance_evidence, dict) else {}
    missing_evidence = _dedupe_text(acceptance.get("blocking_missing_files", []))
    if "acceptance_evidence_missing" in blocking_reasons:
        return {
            "kind": "complete_acceptance_evidence",
            "priority": 70,
            "action_type": "edit_sources",
            "reason": (
                "The design or QA contract declares final acceptance evidence files that are "
                "not present. Generate the missing proof files or correct the acceptance "
                "evidence ledger before delivery."
            ),
            "missing_files": missing_evidence,
            "warning_types": ["acceptance_evidence_missing"],
            "suggested_fields": [
                "design_brief.acceptance_evidence",
                "design_brief.qa_contract.acceptance_evidence",
                "design_brief.qa_contract.evidence_files",
                "design_brief.qa_contract.verification_evidence",
            ],
        }
    if warning_reasons:
        metadata = warning_metadata if isinstance(warning_metadata, dict) else {}
        action = {
            "kind": "inspect_delivery_warnings",
            "priority": 75,
            "action_type": "edit_sources",
            "reason": (
                "Delivery is not ready because the latest build report still contains warning "
                "conditions. Inspect the delivery report counts, layout-density evidence, and "
                "the build/preflight/QA report paths, patch workspace sources, then rebuild."
            ),
            "warning_types": _dedupe_text([*warning_reasons, *metadata.get("warning_types", [])]),
            "suggested_fields": _dedupe_text(metadata.get("suggested_fields", [])) or [
                "outline.json",
                "design_brief.json",
                "content_plan.json",
                "evidence_plan.json",
                "asset_plan.json",
            ],
        }
        planning_paths = _dedupe_text(metadata.get("planning_paths", []))
        slide_ids = _dedupe_text(metadata.get("slide_ids", []))
        if planning_paths:
            action["planning_paths"] = planning_paths
        if slide_ids:
            action["slide_ids"] = slide_ids
        return action
    return readiness_action


def _source_path_key(workspace: Path, raw: str) -> str:
    path_text = str(raw or "").strip()
    if not path_text:
        return ""
    return _display_path(workspace, _workspace_path(workspace, path_text))


def _merge_current_source_snapshots(
    workspace: Path,
    build_source_files: dict[str, Any],
    current_source_files: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(build_source_files)
    tracked_paths = {
        key
        for key in (
            _source_path_key(
                workspace,
                str(snapshot.get("path") or "") if isinstance(snapshot, dict) else "",
            )
            for snapshot in build_source_files.values()
        )
        if key
    }
    if not isinstance(current_source_files, dict):
        return merged
    for name, raw_snapshot in sorted(current_source_files.items()):
        snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
        if not snapshot.get("exists"):
            continue
        path_text = str(snapshot.get("path") or "").strip()
        path_key = _source_path_key(workspace, path_text)
        if not path_key or path_key in tracked_paths:
            continue
        merged_name = str(name)
        while merged_name in merged:
            merged_name = f"current_{merged_name}"
        merged[merged_name] = {
            "path": path_text,
            "exists": False,
            "build_snapshot_missing": True,
        }
        tracked_paths.add(path_key)
    return merged


def _source_freshness(
    workspace: Path,
    source_files: Any,
    *,
    current_source_files: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checked_files = source_files if isinstance(source_files, dict) else {}
    checked_files = _merge_current_source_snapshots(
        workspace,
        checked_files,
        current_source_files,
    )
    if not checked_files:
        return {
            "checked": False,
            "count": 0,
            "stale_count": 0,
            "stale_files": [],
            "files": [],
        }

    files: list[dict[str, Any]] = []
    for name, raw_snapshot in sorted(checked_files.items()):
        snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
        path_text = str(snapshot.get("path") or "")
        current_path = _workspace_path(workspace, path_text) if path_text else None
        build_exists = bool(snapshot.get("exists"))
        build_snapshot_missing = bool(snapshot.get("build_snapshot_missing"))
        current_exists = bool(current_path and current_path.exists())
        build_sha = str(snapshot.get("sha256") or "")
        current_sha = ""
        read_error = ""

        if current_path and current_path.exists() and current_path.is_file():
            try:
                current_sha = _file_sha256(current_path)
            except OSError as exc:
                read_error = str(exc)

        stale = False
        if not path_text:
            status = "missing_path"
            stale = True
        elif build_snapshot_missing and current_exists:
            status = "not_fingerprinted_at_build"
            stale = True
        elif build_exists and not current_exists:
            status = "missing_since_build"
            stale = True
        elif not build_exists and current_exists:
            status = "created_since_build"
            stale = True
        elif build_exists and current_exists and read_error:
            status = "unreadable_current_source"
            stale = True
        elif build_exists and current_exists and build_sha and current_sha and build_sha != current_sha:
            status = "changed_since_build"
            stale = True
        elif build_exists and current_exists:
            status = "fresh" if build_sha and current_sha else "present_unhashed"
        else:
            status = "absent_at_build"

        item = {
            "name": str(name),
            "path": _display_path(workspace, current_path),
            "build_exists": build_exists,
            "current_exists": current_exists,
            "build_sha256": build_sha,
            "current_sha256": current_sha,
            "status": status,
            "stale": stale,
        }
        if build_snapshot_missing:
            item["build_snapshot_missing"] = True
        if read_error:
            item["read_error"] = read_error
        files.append(item)

    stale_files = [
        {
            "name": item.get("name"),
            "path": item.get("path"),
            "status": item.get("status"),
        }
        for item in files
        if item.get("stale")
    ]
    return {
        "checked": True,
        "count": len(files),
        "stale_count": len(stale_files),
        "stale_files": stale_files,
        "files": files,
    }


def _delivery_markdown(report: dict[str, Any]) -> str:
    build = report.get("build") if isinstance(report.get("build"), dict) else {}
    outputs = build.get("outputs") if isinstance(build.get("outputs"), dict) else {}
    pptx = outputs.get("pptx") if isinstance(outputs.get("pptx"), dict) else {}
    run = build.get("run") if isinstance(build.get("run"), dict) else {}
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    readiness_next_action = (
        readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    )
    recommended_next_action = (
        report.get("recommended_next_action")
        if isinstance(report.get("recommended_next_action"), dict)
        else {}
    )
    commands = report.get("commands") if isinstance(report.get("commands"), dict) else {}
    source_freshness = (
        report.get("source_freshness") if isinstance(report.get("source_freshness"), dict) else {}
    )
    acceptance_evidence = (
        report.get("acceptance_evidence")
        if isinstance(report.get("acceptance_evidence"), dict)
        else {}
    )
    visual_review = (
        report.get("visual_review_requirement")
        if isinstance(report.get("visual_review_requirement"), dict)
        else {}
    )
    phase_proof = (
        report.get("phase_proof_ledger")
        if isinstance(report.get("phase_proof_ledger"), dict)
        else {}
    )
    source_inventory = (
        report.get("workspace_source_inventory")
        if isinstance(report.get("workspace_source_inventory"), dict)
        else {}
    )
    resolved_treatments = (
        report.get("resolved_treatment_summary")
        if isinstance(report.get("resolved_treatment_summary"), dict)
        else {}
    )
    replay_contract = (
        report.get("reproducibility_contract")
        if isinstance(report.get("reproducibility_contract"), dict)
        else {}
    )
    quality_context = (
        report.get("quality_context")
        if isinstance(report.get("quality_context"), dict)
        else {}
    )
    layout_density = (
        report.get("layout_density")
        if isinstance(report.get("layout_density"), dict)
        else {}
    )
    artifact_context = (
        report.get("artifact_context")
        if isinstance(report.get("artifact_context"), dict)
        else {}
    )
    blocking = report.get("blocking_reasons") if isinstance(report.get("blocking_reasons"), list) else []
    warnings = report.get("warning_reasons") if isinstance(report.get("warning_reasons"), list) else []

    lines = [
        "# Delivery Readiness",
        "",
        f"- Workspace: `{report.get('workspace', '')}`",
        f"- Delivery status: `{report.get('delivery_status', '')}`",
        f"- Blocking reasons: `{', '.join(blocking) if blocking else 'none'}`",
        f"- Warning reasons: `{', '.join(warnings) if warnings else 'none'}`",
        f"- Readiness status: `{readiness.get('status', '')}`",
        "- Phase proof ledger: "
        f"`{phase_proof.get('ledger_version', '') or 'none'}` "
        f"valid=`{bool(phase_proof.get('valid'))}` "
        f"gates=`{phase_proof.get('acceptance_gate_count', 0)}` "
        f"proof_paths=`{phase_proof.get('proof_path_count', 0)}` "
        f"files=`{phase_proof.get('existing_file_count', 0)}/{phase_proof.get('proof_file_count', 0)}` "
        f"missing=`{phase_proof.get('missing_file_count', 0)}` "
        f"route_required=`{_markdown_list(phase_proof.get('route_required_phase_ids'))}` "
        f"source=`{phase_proof.get('source', '') or 'none'}`",
        f"- Build report: `{build.get('path', '')}` exists=`{bool(build.get('exists'))}`",
        f"- Build status: `{run.get('status') or 'unknown'}` returncode=`{run.get('returncode')}` failed_step=`{run.get('failed_step') or ''}`",
        _build_speed_markdown_line(build.get("speed")),
        f"- Output PPTX: `{pptx.get('path', '')}` exists=`{bool(pptx.get('exists'))}` sha256=`{pptx.get('sha256', '')}` normalized_sha256=`{pptx.get('normalized_sha256', '')}`",
        "- Visual review: "
        f"required=`{bool(visual_review.get('required'))}` "
        f"route_ledger=`{bool(visual_review.get('required_by_route_ledger'))}` "
        f"cli=`{bool(visual_review.get('required_by_cli'))}` "
        f"run=`{bool(visual_review.get('run'))}` "
        f"warnings=`{int(visual_review.get('warning_count') or 0)}` "
        f"sources=`{_markdown_list(visual_review.get('sources'))}`",
        f"- Renderer: `{build.get('renderer', {})}`",
        "",
        "## Gates",
        "",
    ]
    gates = report.get("gates") if isinstance(report.get("gates"), dict) else {}
    if gates:
        for key in sorted(gates):
            value = gates.get(key)
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Data Handoff", ""])
    lines.extend(_data_handoff_markdown_lines(readiness))
    lines.extend(["", "## Build Data Handoff", ""])
    lines.extend(_build_data_handoff_markdown_lines(build))
    lines.extend(["", "## Artifact Context", ""])
    lines.extend(_artifact_context_markdown_lines(artifact_context))
    lines.extend(["", "## Reproducibility Context", ""])
    lines.extend(_reproducibility_contract_markdown_lines(replay_contract))
    lines.extend(_source_inventory_markdown_lines(source_inventory))
    lines.extend(_resolved_treatment_markdown_lines(resolved_treatments))
    lines.extend(["", "## Quality Context", ""])
    lines.extend(_quality_context_markdown_lines(quality_context))
    lines.extend(["", "## Layout Density", ""])
    lines.extend(_layout_density_markdown_lines(layout_density))
    lines.extend(["", "## Next Action", ""])
    lines.append(f"- Recommended next action: `{recommended_next_action.get('kind', 'none')}`")
    lines.append(f"- Readiness next action: `{readiness_next_action.get('kind', 'none')}`")
    lines.append(f"- Action type: `{recommended_next_action.get('action_type', 'none')}`")
    lines.append(f"- Reason: {recommended_next_action.get('reason', '')}")
    lines.append(f"- Slide IDs: `{_markdown_list(recommended_next_action.get('slide_ids'))}`")
    lines.append(f"- Planning paths: `{_markdown_list(recommended_next_action.get('planning_paths'))}`")
    lines.append(f"- Warning types: `{_markdown_list(recommended_next_action.get('warning_types'))}`")
    lines.append(f"- Suggested fields: `{_markdown_list(recommended_next_action.get('suggested_fields'))}`")
    action_command = _command_text(recommended_next_action.get("command"))
    if action_command:
        lines.append(f"- Action command: `{action_command}`")
    advance_command = _command_text(commands.get("advance"))
    if advance_command:
        lines.append(f"- Source-edit handoff: `{advance_command}`")
    lines.extend(["", "## Source Freshness", ""])
    lines.append(f"- Checked: `{bool(source_freshness.get('checked'))}`")
    lines.append(f"- Source files: `{int(source_freshness.get('count') or 0)}`")
    lines.append(f"- Stale source files: `{int(source_freshness.get('stale_count') or 0)}`")
    stale_files = (
        source_freshness.get("stale_files")
        if isinstance(source_freshness.get("stale_files"), list)
        else []
    )
    if stale_files:
        for item in stale_files:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- `{item.get('name', '')}` `{item.get('path', '')}`: `{item.get('status', '')}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Acceptance Evidence", ""])
    lines.append(f"- Checked: `{bool(acceptance_evidence.get('checked'))}`")
    lines.append(f"- Evidence items: `{int(acceptance_evidence.get('item_count') or 0)}`")
    lines.append(
        f"- Evidence files: `{int(acceptance_evidence.get('existing_file_count') or 0)}/{int(acceptance_evidence.get('file_count') or 0)}` existing"
    )
    lines.append(f"- Self outputs: `{int(acceptance_evidence.get('self_output_count') or 0)}`")
    lines.append(f"- Missing files: `{_markdown_list(acceptance_evidence.get('missing_files'))}`")
    lines.append(
        f"- Blocking missing files: `{_markdown_list(acceptance_evidence.get('blocking_missing_files'))}`"
    )
    lines.extend(["", "## Report Counts", ""])
    for name, counts in (report.get("report_counts") or {}).items():
        lines.append(f"- `{name}`: `{json.dumps(counts, sort_keys=True)}`")
    lines.extend(["", "## Commands", ""])
    for key in ("readiness", "advance", "strict_build", "visual_review_build", "repeat_build"):
        text = _command_text(commands.get(key))
        if text:
            lines.append(f"- `{key}`: `{text}`")
    lines.append("")
    return "\n".join(lines)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize whether the current workspace build is ready for final delivery."
    )
    parser.add_argument("--workspace", required=True, help="Workspace created by init_deck_workspace.py")
    parser.add_argument(
        "--report",
        default="build/delivery_readiness.json",
        help="Workspace-relative or absolute JSON report path.",
    )
    parser.add_argument(
        "--markdown-report",
        default="build/delivery_readiness.md",
        help="Workspace-relative or absolute Markdown report path.",
    )
    parser.add_argument(
        "--build-report",
        default="build/build_workspace_report.json",
        help="Workspace-relative or absolute build report path.",
    )
    parser.add_argument(
        "--readiness-report",
        default="build/workspace_readiness.json",
        help="Workspace-relative or absolute readiness report path.",
    )
    parser.add_argument(
        "--readiness-markdown",
        default="build/workspace_readiness.md",
        help="Workspace-relative or absolute readiness Markdown path.",
    )
    parser.add_argument(
        "--no-refresh-readiness",
        action="store_true",
        help="Use the existing readiness report instead of rerunning source-only readiness.",
    )
    parser.add_argument(
        "--allow-skip-render",
        action="store_true",
        help="Do not warn when the last QA run used --skip-render.",
    )
    parser.add_argument(
        "--require-visual-review",
        action="store_true",
        help="Warn unless the last build ran rendered visual review with zero warnings.",
    )
    parser.add_argument("--skip-markdown", action="store_true", help="Do not write Markdown report.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = _repo_root()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 2

    report_path = _workspace_path(workspace, args.report)
    markdown_path = _workspace_path(workspace, args.markdown_report)
    build_report_path = _workspace_path(workspace, args.build_report)
    readiness_report_path = _workspace_path(workspace, args.readiness_report)
    readiness_markdown_path = _workspace_path(workspace, args.readiness_markdown)

    readiness_rc: int | None = None
    readiness_stderr = ""
    if not args.no_refresh_readiness:
        readiness_rc, readiness_payload, readiness_stderr = _run_readiness(
            repo=repo,
            workspace=workspace,
            report_path=readiness_report_path,
            markdown_path=readiness_markdown_path,
        )
    else:
        readiness_payload = _load_json(readiness_report_path, {})
    if not isinstance(readiness_payload, dict):
        readiness_payload = {}

    build_payload = _load_json(build_report_path, {})
    if not isinstance(build_payload, dict):
        build_payload = {}
    reports = build_payload.get("reports") if isinstance(build_payload.get("reports"), dict) else {}
    outputs = build_payload.get("outputs") if isinstance(build_payload.get("outputs"), dict) else {}
    options = build_payload.get("options") if isinstance(build_payload.get("options"), dict) else {}
    run = build_payload.get("run") if isinstance(build_payload.get("run"), dict) else {}
    next_commands = (
        build_payload.get("next_commands")
        if isinstance(build_payload.get("next_commands"), dict)
        else {}
    )

    planning_counts = _counts(reports.get("planning"))
    preflight_counts = _counts(reports.get("preflight"))
    qa_counts = _counts(reports.get("qa"))
    report_counts = {
        "planning": planning_counts,
        "preflight": preflight_counts,
        "qa": qa_counts,
    }
    route_visual_review_requirement = _route_requirement_from_readiness(
        readiness_payload,
        "rendered_visual_review",
    )
    visual_review_count = int(qa_counts.get("visual_review_warning_count", 0))
    visual_review_required = bool(
        args.require_visual_review
        or route_visual_review_requirement.get("required")
    )
    source_files = build_payload.get("source_files") if isinstance(build_payload.get("source_files"), dict) else {}
    current_source_files = (
        readiness_payload.get("source_files")
        if isinstance(readiness_payload.get("source_files"), dict)
        else {}
    )
    source_freshness = _source_freshness(
        workspace,
        source_files,
        current_source_files=current_source_files,
    )
    design_brief = _load_json(workspace / "design_brief.json", {})
    if not isinstance(design_brief, dict):
        design_brief = {}
    acceptance_evidence = _acceptance_evidence_summary(
        workspace=workspace,
        design=design_brief,
        self_output_paths={report_path, markdown_path},
    )
    phase_proof_ledger = _compact_phase_proof_summary(readiness_payload)
    workspace_source_inventory = _compact_workspace_source_inventory(readiness_payload)
    resolved_treatment_summary = _compact_resolved_treatment_summary(readiness_payload)
    reproducibility_contract = _compact_reproducibility_contract(readiness_payload)
    quality_context = _compact_quality_context(readiness_payload)
    build_quality_context = (
        build_payload.get("quality_context")
        if isinstance(build_payload.get("quality_context"), dict)
        else {}
    )
    if not quality_context and build_quality_context:
        quality_context = build_quality_context
    layout_density = _compact_layout_density(workspace, build_payload)
    layout_density_contract_required = _quality_requires_whitespace_polish(quality_context)
    layout_density_low = _layout_density_low_count(layout_density) > 0
    artifact_context = _compact_artifact_context(readiness_payload)

    blocking_reasons: list[str] = []
    warning_reasons: list[str] = []
    if not build_report_path.exists():
        blocking_reasons.append("missing_build_report")
    elif not source_freshness.get("checked"):
        blocking_reasons.append("missing_source_fingerprints")
    elif int(source_freshness.get("stale_count", 0)) > 0:
        blocking_reasons.append("source_changed_since_build")
    build_failed = bool(
        run and (run.get("status") == "failed" or _int_value(run.get("returncode")) != 0)
    )
    if build_failed:
        failed_step = str(run.get("failed_step") or "build").strip() or "build"
        blocking_reasons.append(f"{failed_step}_step_failed")
    pptx = outputs.get("pptx") if isinstance(outputs.get("pptx"), dict) else {}
    if not pptx.get("exists"):
        blocking_reasons.append("missing_output_pptx")
    if readiness_payload.get("status") == "blocked":
        blocking_reasons.append("source_readiness_blocked")
    elif readiness_payload.get("status") and readiness_payload.get("status") != "ready":
        warning_reasons.append(f"source_readiness_{readiness_payload.get('status')}")
    elif not readiness_payload:
        warning_reasons.append("missing_readiness_report")

    for prefix, counts in (("planning", planning_counts), ("preflight", preflight_counts)):
        if int(counts.get("error_count", 0)) > 0:
            blocking_reasons.append(f"{prefix}_errors")
        if int(counts.get("warning_count", 0)) > 0:
            warning_reasons.append(f"{prefix}_warnings")
    qa_error_counts = _positive_counts(
        qa_counts,
        [
            "overflow_count",
            "overlap_count",
            "geometry_error_count",
            "design_error_count",
        ],
    )
    if qa_error_counts:
        blocking_reasons.extend(sorted(f"qa_{key}" for key in qa_error_counts))
    qa_warning_counts = _positive_counts(
        qa_counts,
        [
            "geometry_warning_count",
            "whitespace_warning_count",
            "design_warning_count",
            "visual_warning_count",
        ],
    )
    if qa_warning_counts:
        warning_reasons.extend(sorted(f"qa_{key}" for key in qa_warning_counts))

    if not options.get("qa"):
        blocking_reasons.append("qa_not_run")
    if options.get("fast_first_pass"):
        warning_reasons.append("fast_first_pass_not_final")
    if options.get("skip_render") and not args.allow_skip_render:
        warning_reasons.append("render_skipped")
    if not options.get("fail_on_planning_warnings"):
        warning_reasons.append("planning_warnings_not_blocking")
    if not options.get("fail_on_whitespace_warnings"):
        warning_reasons.append("whitespace_warnings_not_blocking")
    if visual_review_required:
        if not options.get("visual_review"):
            warning_reasons.append("visual_review_not_run")
        if visual_review_count:
            warning_reasons.append("visual_review_warnings")
    if layout_density_contract_required and layout_density_low:
        warning_reasons.append("layout_density_low")
    if int(acceptance_evidence.get("blocking_missing_file_count") or 0) > 0:
        blocking_reasons.append("acceptance_evidence_missing")

    blocking_reasons = sorted(dict.fromkeys(blocking_reasons))
    warning_reasons = sorted(dict.fromkeys(warning_reasons))
    if blocking_reasons:
        status = "blocked"
        exit_code = 2
    elif warning_reasons:
        status = "needs_attention"
        exit_code = 1
    else:
        status = "ready"
        exit_code = 0

    gates = {
        "source_readiness_ready": readiness_payload.get("status") == "ready",
        "source_freshness_current": bool(source_freshness.get("checked"))
        and int(source_freshness.get("stale_count", 0)) == 0,
        "build_report_exists": build_report_path.exists(),
        "output_pptx_exists": bool(pptx.get("exists")),
        "build_succeeded": not build_failed,
        "qa_run": bool(options.get("qa")),
        "fast_first_pass": bool(options.get("fast_first_pass")),
        "final_build_mode": not bool(options.get("fast_first_pass")),
        "rendered_qa": not bool(options.get("skip_render")),
        "skip_render_allowed": bool(args.allow_skip_render),
        "planning_warnings_blocking": bool(options.get("fail_on_planning_warnings")),
        "whitespace_warnings_blocking": bool(options.get("fail_on_whitespace_warnings")),
        "visual_review_required": visual_review_required,
        "visual_review_required_by_cli": bool(args.require_visual_review),
        "visual_review_required_by_route_ledger": bool(route_visual_review_requirement.get("required")),
        "visual_review_run": bool(options.get("visual_review")),
        "layout_density_checked": bool(layout_density.get("exists")),
        "layout_density_contract_required": layout_density_contract_required,
        "layout_density_floor_satisfied": not layout_density_low,
        "phase_proof_ledger_declared": bool(phase_proof_ledger.get("exists")),
        "phase_proof_ledger_valid": (
            not bool(phase_proof_ledger.get("exists"))
            or bool(phase_proof_ledger.get("valid"))
        ),
        "acceptance_evidence_files_satisfied": int(
            acceptance_evidence.get("blocking_missing_file_count") or 0
        )
        == 0,
        "acceptance_evidence_declared": bool(acceptance_evidence.get("checked")),
    }
    commands = {
        "readiness": [
            "python3",
            "scripts/report_workspace_readiness.py",
            "--workspace",
            str(workspace),
        ],
        "advance": [
            "python3",
            "scripts/advance_workspace.py",
            "--workspace",
            str(workspace),
            "--execute",
            "--max-steps",
            "3",
        ],
        "strict_build": [
            "python3",
            "scripts/build_workspace.py",
            "--workspace",
            str(workspace),
            "--qa",
            "--fail-on-planning-warnings",
            "--fail-on-whitespace-warnings",
            "--overwrite",
        ],
        "visual_review_build": [
            "python3",
            "scripts/build_workspace.py",
            "--workspace",
            str(workspace),
            "--qa",
            "--visual-review",
            "--fail-on-planning-warnings",
            "--fail-on-whitespace-warnings",
            "--fail-on-visual-review-warnings",
            "--overwrite",
        ],
        "repeat_build": next_commands.get("repeat_build", []),
    }
    warning_metadata = _delivery_warning_metadata(
        workspace,
        build_payload,
        report_counts,
        layout_density=layout_density if layout_density_contract_required else {},
    )
    recommended_next_action = _recommended_delivery_action(
        blocking_reasons=blocking_reasons,
        warning_reasons=warning_reasons,
        readiness_next_action=readiness_payload.get("next_action", {}),
        strict_build_command=commands["strict_build"],
        visual_review_build_command=commands["visual_review_build"],
        warning_metadata=warning_metadata,
        acceptance_evidence=acceptance_evidence,
    )
    report = {
        "schema_version": 1,
        "workspace": str(workspace),
        "delivery_status": status,
        "blocking_reasons": blocking_reasons,
        "warning_reasons": warning_reasons,
        "gates": gates,
        "phase_proof_ledger": phase_proof_ledger,
        "workspace_source_inventory": workspace_source_inventory,
        "resolved_treatment_summary": resolved_treatment_summary,
        "reproducibility_contract": reproducibility_contract,
        "quality_context": quality_context,
        "layout_density": layout_density,
        "artifact_context": artifact_context,
        "visual_review_requirement": {
            "required": visual_review_required,
            "required_by_cli": bool(args.require_visual_review),
            "required_by_route_ledger": bool(route_visual_review_requirement.get("required")),
            "route_id": route_visual_review_requirement.get("route_id", "rendered_visual_review"),
            "sources": route_visual_review_requirement.get("sources", []),
            "inactive_sources": route_visual_review_requirement.get("inactive_sources", []),
            "run": bool(options.get("visual_review")),
            "warning_count": visual_review_count,
        },
        "recommended_next_action": recommended_next_action,
        "readiness": {
            "path": _display_path(workspace, readiness_report_path),
            "exists": readiness_report_path.exists(),
            "returncode": readiness_rc,
            "status": readiness_payload.get("status"),
            "status_reasons": readiness_payload.get("status_reasons", []),
            "next_action": readiness_payload.get("next_action", {}),
            "phase_proof_ledger": phase_proof_ledger,
            "workspace_source_inventory": workspace_source_inventory,
            "resolved_treatment_summary": resolved_treatment_summary,
            "reproducibility_contract": reproducibility_contract,
            "quality_context": quality_context,
            "layout_density": layout_density,
            "artifact_context": artifact_context,
            "data_analysis_handoff": _compact_data_handoff_summary(readiness_payload),
            "stderr_tail": readiness_stderr[-1200:],
        },
        "build": {
            "path": _display_path(workspace, build_report_path),
            "exists": build_report_path.exists(),
            "style_preset": build_payload.get("style_preset"),
            "renderer": build_payload.get("renderer", {}),
            "run": run,
            "options": options,
            "outputs": outputs,
            "data_analysis_handoff": _compact_data_handoff_summary(build_payload),
            "quality_context": build_quality_context,
            "layout_density": layout_density,
            "speed": _compact_build_speed(build_payload),
        },
        "source_freshness": source_freshness,
        "acceptance_evidence": acceptance_evidence,
        "report_counts": report_counts,
        "commands": commands,
    }
    report_changed = _write_json_if_changed(report_path, report)
    markdown_changed = False
    if not args.skip_markdown:
        markdown_changed = _write_text_if_changed(markdown_path, _delivery_markdown(report))
    print(json.dumps(report, indent=2))
    print(
        "[delivery_readiness] "
        f"status={status} blocking={len(blocking_reasons)} warnings={len(warning_reasons)} "
        f"report={_display_path(workspace, report_path)} changed={int(report_changed)} "
        f"markdown={'' if args.skip_markdown else _display_path(workspace, markdown_path)} changed={int(markdown_changed)}",
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
