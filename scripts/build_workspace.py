#!/usr/bin/env python3
"""Build a deck from a persistent workspace scaffold."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from design_tokens import available_presets
from inspect_artifact_manifest import inspect_manifest
from office_package_hash import (
    OFFICE_PACKAGE_HASH_ALGORITHM,
    is_office_package_path,
    office_package_normalized_sha256,
)


_FAST_FIRST_PASS_ATTRS = {
    "qa",
    "skip_render",
    "scaffold_data_artifacts",
    "auto_bind_artifacts",
    "fail_on_planning_warnings",
    "fail_on_whitespace_warnings",
    "overwrite",
}


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def _run_capture_echo(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        print(result.stdout, end="")
    return result.returncode, result.stdout or ""


def _record_step_timing(
    timings: list[dict[str, Any]],
    *,
    step: str,
    started: float,
    returncode: int | None = None,
    command: list[str] | None = None,
    status: str | None = None,
) -> None:
    duration_ms = int(round((time.perf_counter() - started) * 1000))
    inferred_status = status
    if inferred_status is None and returncode is not None:
        inferred_status = "succeeded" if returncode == 0 else "failed"
    entry: dict[str, Any] = {
        "step": step,
        "duration_ms": duration_ms,
        "status": inferred_status or "completed",
    }
    if returncode is not None:
        entry["returncode"] = int(returncode)
    if command is not None:
        entry["command"] = [str(item) for item in command]
    timings.append(entry)


def _run_timed(
    cmd: list[str],
    *,
    timings: list[dict[str, Any]],
    step: str,
) -> None:
    started = time.perf_counter()
    try:
        _run(cmd)
    except Exception:
        _record_step_timing(timings, step=step, started=started, command=cmd, status="failed")
        raise
    _record_step_timing(timings, step=step, started=started, returncode=0, command=cmd)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text_if_changed(path: Path, text: str) -> bool:
    """Write text only when bytes changed; return True when the file changed."""
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


def _load_json_if_exists(path: Path | None) -> Any:
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_snapshot(workspace: Path, path: Path | None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": bool(path and path.exists()),
    }
    if not path or not path.exists() or not path.is_file():
        return snapshot
    try:
        stat = path.stat()
        snapshot["size_bytes"] = stat.st_size
        snapshot["sha256"] = _file_sha256(path)
        if is_office_package_path(path):
            snapshot["normalized_sha256"] = office_package_normalized_sha256(path)
            snapshot["normalized_sha256_algorithm"] = OFFICE_PACKAGE_HASH_ALGORITHM
    except OSError as exc:
        snapshot["read_error"] = str(exc)
    except Exception as exc:
        snapshot["normalized_hash_error"] = str(exc)
    return snapshot


def _json_report_summary(
    workspace: Path,
    path: Path | None,
    *,
    count_keys: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": bool(path and path.exists()),
    }
    payload = _load_json_if_exists(path)
    if not isinstance(payload, dict):
        return summary
    counts: dict[str, Any] = {}
    for key in count_keys:
        if key in payload:
            counts[key] = payload.get(key)
    for key, list_key in (("error_count", "errors"), ("warning_count", "warnings")):
        if key not in counts and isinstance(payload.get(list_key), list):
            counts[key] = len(payload[list_key])
    if counts:
        summary["counts"] = counts
    return summary


def _artifact_selection_summary(workspace: Path, path: Path | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": bool(path and path.exists()),
    }
    payload = _load_json_if_exists(path)
    bindings = payload.get("bindings") if isinstance(payload, dict) else None
    if not isinstance(bindings, list):
        return summary
    compact_bindings: list[dict[str, str]] = []
    for item in bindings:
        if not isinstance(item, dict):
            continue
        compact_bindings.append(
            {
                "slide_id": str(item.get("slide_id") or item.get("target_slide") or ""),
                "output_id": str(item.get("output_id") or item.get("id") or ""),
                "variant": str(item.get("variant") or item.get("slide_variant") or ""),
                "title": str(item.get("title") or ""),
            }
        )
    summary["binding_count"] = len(compact_bindings)
    summary["bindings"] = compact_bindings
    return summary


def _artifact_selection_context(
    workspace: Path,
    path: Path | None,
    *,
    output_ids: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": bool(path and path.exists()),
        "binding_count": 0,
        "bound_output_ids": [],
        "unbound_output_ids": output_ids,
        "slide_ids": [],
        "variants": [],
        "error": "",
    }
    payload = _load_json_if_exists(path)
    bindings = payload.get("bindings") if isinstance(payload, dict) else None
    if not isinstance(bindings, list):
        if path and path.exists():
            summary["error"] = "selection file must contain a bindings list"
        return summary
    bound_output_ids: list[str] = []
    slide_ids: list[str] = []
    variants: list[str] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        output_id = str(binding.get("output_id") or binding.get("id") or "").strip()
        slide_id = str(binding.get("slide_id") or binding.get("target_slide") or "").strip()
        variant = str(binding.get("variant") or binding.get("slide_variant") or "").strip()
        if output_id and output_id not in bound_output_ids:
            bound_output_ids.append(output_id)
        if slide_id and slide_id not in slide_ids:
            slide_ids.append(slide_id)
        if variant and variant not in variants:
            variants.append(variant)
    summary.update(
        {
            "binding_count": len([item for item in bindings if isinstance(item, dict)]),
            "bound_output_ids": bound_output_ids,
            "unbound_output_ids": [item for item in output_ids if item not in bound_output_ids],
            "slide_ids": slide_ids,
            "variants": variants,
        }
    )
    return summary


def _build_artifact_context(
    workspace: Path,
    *,
    artifact_manifest_path: Path,
    artifact_selection_path: Path | None,
) -> dict[str, Any]:
    selection_exists = bool(artifact_selection_path and artifact_selection_path.exists())
    if not artifact_manifest_path.exists() and not selection_exists:
        return {}

    manifest_summary: dict[str, Any] = {
        "path": _display_path(workspace, artifact_manifest_path),
        "exists": artifact_manifest_path.exists(),
        "valid": False,
        "manifest_version": "",
        "output_count": 0,
        "output_ids": [],
        "analysis_summary": "",
        "analysis_summary_markdown": "",
        "figure_quality_counts": {},
        "selection_template_count": 0,
        "aliases": [],
        "commands": {},
    }
    output_ids: list[str] = []
    if artifact_manifest_path.exists():
        try:
            inspected = inspect_manifest(workspace, artifact_manifest_path)
        except Exception as exc:
            manifest_summary["error"] = str(exc)
        else:
            aliases: list[dict[str, Any]] = []
            figure_quality_counts: dict[str, int] = {}
            alias_plan = inspected.get("alias_plan") if isinstance(inspected.get("alias_plan"), list) else []
            for item in alias_plan:
                if not isinstance(item, dict):
                    continue
                output_id = str(item.get("id") or "").strip()
                if output_id:
                    output_ids.append(output_id)
                figure_quality = (
                    item.get("figure_quality")
                    if isinstance(item.get("figure_quality"), dict)
                    else {}
                )
                quality_status = str(figure_quality.get("status") or "unknown").strip() or "unknown"
                figure_quality_counts[quality_status] = figure_quality_counts.get(quality_status, 0) + 1
                aliases.append(
                    {
                        "id": output_id,
                        "title": str(item.get("title") or "").strip(),
                        "image_alias": str(item.get("image_alias") or "").strip(),
                        "chart_alias": str(item.get("chart_alias") or "").strip(),
                        "table_alias": str(item.get("table_alias") or "").strip(),
                        "source_path": str(item.get("source_path") or "").strip(),
                        "figure_quality": figure_quality,
                    }
                )
            commands = inspected.get("commands") if isinstance(inspected.get("commands"), dict) else {}
            manifest_summary.update(
                {
                    "valid": True,
                    "manifest_version": str(inspected.get("manifest_version") or "").strip(),
                    "output_count": _int_value(inspected.get("output_count")),
                    "output_ids": output_ids,
                    "analysis_summary": str(inspected.get("analysis_summary") or "").strip(),
                    "analysis_summary_markdown": str(
                        inspected.get("analysis_summary_markdown") or ""
                    ).strip(),
                    "figure_quality_counts": figure_quality_counts,
                    "selection_template_count": len(inspected.get("selection_templates") or [])
                    if isinstance(inspected.get("selection_templates"), list)
                    else 0,
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
            )

    return {
        "artifact_manifest": manifest_summary,
        "artifact_selection": _artifact_selection_context(
            workspace,
            artifact_selection_path,
            output_ids=output_ids,
        ),
    }


def _data_analysis_handoff_apply_report_path(workspace: Path, build_dir: Path) -> Path:
    canonical = workspace / "data_analysis_handoff_apply_report.json"
    legacy = build_dir / "data_analysis_handoff_apply.json"
    if canonical.exists() or not legacy.exists():
        return canonical
    return legacy


def _data_analysis_handoff_selection_path(workspace: Path, build_dir: Path) -> Path:
    handoff_payload = _load_json_if_exists(workspace / "data_analysis_handoff.json")
    apply_payload = _load_json_if_exists(
        _data_analysis_handoff_apply_report_path(workspace, build_dir)
    )
    raw = ""
    if isinstance(apply_payload, dict):
        raw = str(apply_payload.get("selection_file") or "").strip()
    if not raw and isinstance(handoff_payload, dict):
        selection_block = handoff_payload.get("artifact_selection_recommendations")
        if isinstance(selection_block, dict):
            raw = str(selection_block.get("selection_file") or "").strip()
    if not raw:
        raw = "artifact_selections.scout.json"
    return _workspace_path(workspace, raw)


def _data_handoff_rebuild_context(handoff_payload: Any, apply_payload: Any) -> dict[str, Any]:
    if isinstance(handoff_payload, dict):
        context = handoff_payload.get("artifact_rebuild_context")
        if isinstance(context, dict):
            return context
        main = handoff_payload.get("main_agent_handoff")
        if isinstance(main, dict) and isinstance(main.get("artifact_rebuild_context"), dict):
            return main["artifact_rebuild_context"]
    ledger = (
        apply_payload.get("artifact_evidence_ledger")
        if isinstance(apply_payload, dict) and isinstance(apply_payload.get("artifact_evidence_ledger"), dict)
        else {}
    )
    context = ledger.get("artifact_rebuild_context") if isinstance(ledger, dict) else {}
    return context if isinstance(context, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_quality_context(design_brief_path: Path) -> dict[str, Any]:
    design = _load_json_if_exists(design_brief_path)
    if not isinstance(design, dict):
        return {}
    slide_quality = (
        design.get("slide_quality_contract")
        if isinstance(design.get("slide_quality_contract"), dict)
        else {}
    )
    readability = (
        slide_quality.get("readability_targets")
        if isinstance(slide_quality.get("readability_targets"), dict)
        else {}
    )
    layout = (
        slide_quality.get("layout_targets")
        if isinstance(slide_quality.get("layout_targets"), dict)
        else {}
    )
    artifact_quality = (
        slide_quality.get("artifact_quality_targets")
        if isinstance(slide_quality.get("artifact_quality_targets"), dict)
        else {}
    )
    qa_gates = (
        slide_quality.get("qa_gates")
        if isinstance(slide_quality.get("qa_gates"), dict)
        else {}
    )
    outline_meta = (
        design.get("outline_authoring_handoff")
        if isinstance(design.get("outline_authoring_handoff"), dict)
        else {}
    )
    outline_quality = (
        outline_meta.get("quality_alignment")
        if isinstance(outline_meta.get("quality_alignment"), dict)
        else {}
    )
    if not slide_quality and not outline_quality:
        return {}
    return {
        "slide_quality_contract": {
            "exists": bool(slide_quality),
            "contract_version": str(slide_quality.get("contract_version") or "").strip(),
            "min_title_pt": readability.get("min_title_pt"),
            "min_body_pt": readability.get("min_body_pt"),
            "min_caption_pt": readability.get("min_caption_pt"),
            "chart_label_min_pt": readability.get("chart_label_min_pt"),
            "footer_reserved_inches": readability.get("footer_reserved_inches"),
            "max_title_lines": readability.get("max_title_lines"),
            "max_slide_text_lines": readability.get("max_slide_text_lines"),
            "max_slide_words": readability.get("max_slide_words"),
            "max_slide_chars": readability.get("max_slide_chars"),
            "evidence_anchor_required": bool(layout.get("evidence_anchor_required")),
            "fail_on_awkward_whitespace": bool(layout.get("fail_on_awkward_whitespace")),
            "artifact_quality_required_when_data_active": bool(
                artifact_quality.get("required_when_data_artifacts_active")
            ),
            "artifact_must_record_count": len(_string_list(artifact_quality.get("must_record"))),
            "fail_on_count": len(_string_list(qa_gates.get("fail_on"))),
            "required_command_count": len(_string_list(qa_gates.get("required_commands"))),
        },
        "outline_quality_alignment": {
            "present": bool(outline_quality),
            "persisted": bool(outline_quality),
            "contract_version": str(outline_quality.get("contract_version") or "").strip(),
            "readability_target_count": len(_string_list(outline_quality.get("readability_targets_used"))),
            "readability_targets_used": _string_list(outline_quality.get("readability_targets_used")),
            "layout_target_count": len(_string_list(outline_quality.get("layout_targets_used"))),
            "layout_targets_used": _string_list(outline_quality.get("layout_targets_used")),
            "artifact_quality_target_count": len(
                _string_list(outline_quality.get("artifact_quality_targets_used"))
            ),
            "qa_gate_count": len(_string_list(outline_quality.get("qa_gates_used"))),
            "qa_gates_used": _string_list(outline_quality.get("qa_gates_used")),
            "required_command_count": len(_string_list(outline_quality.get("required_commands"))),
            "outline_choices": str(outline_quality.get("outline_choices") or "").strip(),
        },
    }


def _rebuild_context_commands(context: dict[str, Any]) -> list[str]:
    commands = context.get("commands") if isinstance(context.get("commands"), dict) else {}
    values = [
        commands.get("rebuild_figures"),
        commands.get("inspect_manifest"),
        commands.get("auto_select_lead"),
        commands.get("auto_select_all"),
        commands.get("validate_planning"),
    ]
    values.extend(_string_list(context.get("commands_to_preserve")))
    return _string_list(values)


def _data_handoff_rebuild_summary(
    context: dict[str, Any],
    *,
    apply_payload: Any,
) -> dict[str, Any]:
    commands = _rebuild_context_commands(context) if context else []
    source_count = len(_string_list(context.get("source_paths"))) if context else 0
    if not source_count and context:
        try:
            source_count = int(context.get("source_count") or 0)
        except (TypeError, ValueError):
            source_count = 0
    output_count = len(_string_list(context.get("output_paths"))) if context else 0
    if not output_count and context:
        output_count = len(_string_list(context.get("artifact_paths")))
    if not output_count and context:
        try:
            output_count = int(context.get("output_count") or 0)
        except (TypeError, ValueError):
            output_count = 0
    return {
        "present": bool(context),
        "applied": (
            bool(apply_payload.get("artifact_rebuild_context_applied"))
            if isinstance(apply_payload, dict)
            else False
        ),
        "context_version": str(context.get("context_version") or "") if context else "",
        "source": str(context.get("source") or "") if context else "",
        "producer_path": str(context.get("producer_path") or "") if context else "",
        "artifact_manifest": str(context.get("artifact_manifest") or "") if context else "",
        "analysis_summary": str(context.get("analysis_summary") or "") if context else "",
        "source_count": source_count,
        "output_count": output_count,
        "command_count": len(commands),
        "commands": commands[:6],
    }


def _count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _data_handoff_scout_summary(handoff_payload: Any, apply_payload: Any) -> dict[str, Any]:
    raw = handoff_payload if isinstance(handoff_payload, dict) else {}
    applied_counts = (
        apply_payload.get("scout_analysis_counts")
        if isinstance(apply_payload, dict)
        and isinstance(apply_payload.get("scout_analysis_counts"), dict)
        else {}
    )

    def count(key: str, count_key: str) -> int:
        try:
            value = int(applied_counts.get(count_key) or 0)
        except (TypeError, ValueError):
            value = 0
        return value or _count_list(raw.get(key))

    counts = {
        "analysis_task_count": count("analysis_tasks", "analysis_task_count"),
        "computed_finding_count": count("computed_findings", "computed_finding_count"),
        "visual_recommendation_count": count(
            "chart_or_table_recommendations",
            "visual_recommendation_count",
        ),
        "outline_binding_count": count("outline_binding_plan", "outline_binding_count"),
        "quality_flag_count": count("quality_flags", "quality_flag_count"),
        "open_question_count": count("open_questions", "open_question_count"),
    }
    present = any(
        _count_list(raw.get(key))
        for key in (
            "analysis_tasks",
            "computed_findings",
            "chart_or_table_recommendations",
            "outline_binding_plan",
            "quality_flags",
            "open_questions",
        )
    )
    workflow = raw.get("recommended_workflow") if isinstance(raw.get("recommended_workflow"), dict) else {}

    def object_ids(key: str) -> list[str]:
        if not isinstance(raw.get(key), list):
            return []
        return _string_list(
            [
                item.get("id") or item.get("name") or item.get("title")
                for item in raw.get(key, [])
                if isinstance(item, dict)
            ]
        )[:8]

    target_slide_ids: list[str] = []
    variants: list[str] = []
    for key in ("chart_or_table_recommendations", "outline_binding_plan"):
        for item in raw.get(key, []) if isinstance(raw.get(key), list) else []:
            if not isinstance(item, dict):
                continue
            slide_id = str(item.get("target_slide") or item.get("slide_id") or "").strip()
            variant = str(item.get("variant") or item.get("target_variant") or item.get("slide_variant") or "").strip()
            if slide_id and slide_id not in target_slide_ids:
                target_slide_ids.append(slide_id)
            if variant and variant not in variants:
                variants.append(variant)
    applied = (
        bool(apply_payload.get("scout_analysis_applied"))
        if isinstance(apply_payload, dict)
        else False
    )
    return {
        "present": bool(present or any(counts.values())),
        "applied": applied,
        "persisted": applied,
        "schema": "data_analysis_scout_ledger_v1" if (present or applied or any(counts.values())) else "",
        "analysis_task_ids": object_ids("analysis_tasks"),
        "computed_finding_ids": object_ids("computed_findings"),
        "visual_recommendation_ids": object_ids("chart_or_table_recommendations"),
        "target_slide_ids": target_slide_ids[:8],
        "variants": variants[:8],
        "quality_flags": _string_list(raw.get("quality_flags"))[:4],
        "open_questions": _string_list(raw.get("open_questions"))[:4],
        "recommended_workflow_mode": str(workflow.get("mode") or "").strip(),
        **counts,
    }


def _data_analysis_handoff_summary(workspace: Path, build_dir: Path) -> dict[str, Any]:
    handoff_path = workspace / "data_analysis_handoff.json"
    apply_report_path = _data_analysis_handoff_apply_report_path(workspace, build_dir)
    selection_path = _data_analysis_handoff_selection_path(workspace, build_dir)
    handoff_payload = _load_json_if_exists(handoff_path)
    apply_payload = _load_json_if_exists(apply_report_path)
    selection_payload = _load_json_if_exists(selection_path)

    selection_bindings = (
        selection_payload.get("bindings")
        if isinstance(selection_payload, dict) and isinstance(selection_payload.get("bindings"), list)
        else []
    )
    bound_output_ids: list[str] = []
    slide_ids: list[str] = []
    variants: list[str] = []
    for binding in selection_bindings:
        if not isinstance(binding, dict):
            continue
        output_id = str(binding.get("output_id") or binding.get("id") or "").strip()
        slide_id = str(binding.get("slide_id") or binding.get("target_slide") or "").strip()
        variant = str(binding.get("variant") or binding.get("slide_variant") or "").strip()
        if output_id and output_id not in bound_output_ids:
            bound_output_ids.append(output_id)
        if slide_id and slide_id not in slide_ids:
            slide_ids.append(slide_id)
        if variant and variant not in variants:
            variants.append(variant)

    recommended_bindings = []
    if isinstance(handoff_payload, dict):
        selection_block = handoff_payload.get("artifact_selection_recommendations")
        if isinstance(selection_block, dict) and isinstance(selection_block.get("bindings"), list):
            recommended_bindings = selection_block["bindings"]

    current_sha = _file_sha256(handoff_path) if handoff_path.exists() and handoff_path.is_file() else ""
    applied_sha = (
        str(apply_payload.get("handoff_sha256") or "").strip()
        if isinstance(apply_payload, dict)
        else ""
    )
    dry_run = bool(apply_payload.get("dry_run")) if isinstance(apply_payload, dict) else False
    selection_count = (
        int(apply_payload.get("selection_count") or 0)
        if isinstance(apply_payload, dict)
        else len(recommended_bindings)
    )
    applied_bindings = (
        bool(apply_payload.get("applied_bindings")) if isinstance(apply_payload, dict) else False
    )

    if not handoff_path.exists() and not apply_report_path.exists():
        status = "none"
    elif not handoff_path.exists() and apply_report_path.exists():
        status = "applied_without_local_handoff"
    elif not isinstance(handoff_payload, dict):
        status = "handoff_invalid"
    elif not apply_report_path.exists():
        status = "handoff_not_applied"
    elif not isinstance(apply_payload, dict):
        status = "apply_report_invalid"
    elif dry_run:
        status = "handoff_apply_dry_run_only"
    elif not applied_sha:
        status = "handoff_apply_unstamped"
    elif current_sha and applied_sha and current_sha != applied_sha:
        status = "handoff_changed_since_apply"
    elif selection_count > 0 and applied_bindings and not selection_path.exists():
        status = "handoff_selection_missing"
    elif current_sha and applied_sha == current_sha:
        status = "applied"
    else:
        status = "needs_review"

    ledger = (
        apply_payload.get("artifact_evidence_ledger")
        if isinstance(apply_payload, dict)
        and isinstance(apply_payload.get("artifact_evidence_ledger"), dict)
        else {}
    )
    summary: dict[str, Any] = {
        "status": status,
        "applied": status == "applied",
        "stale_apply": status == "handoff_changed_since_apply",
        "selection_count": selection_count,
        "binding_count": len(recommended_bindings),
        "selection_binding_count": len(selection_bindings),
        "bound_output_ids": bound_output_ids,
        "slide_ids": slide_ids,
        "variants": variants,
        "applied_bindings": applied_bindings,
        "script_edit_count": (
            len([item for item in handoff_payload.get("script_edit_plan", []) if isinstance(item, dict)])
            if isinstance(handoff_payload, dict) and isinstance(handoff_payload.get("script_edit_plan"), list)
            else 0
        ),
    }
    if ledger:
        summary["applied_ledger"] = {
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
    rebuild_context = _data_handoff_rebuild_context(handoff_payload, apply_payload)
    summary["artifact_rebuild_context"] = _data_handoff_rebuild_summary(
        rebuild_context,
        apply_payload=apply_payload,
    )
    summary["artifact_contracts"] = {
        "figure_export_contract_applied": bool(apply_payload.get("figure_export_contract_applied")) if isinstance(apply_payload, dict) else False,
        "figure_export_output_count": int(apply_payload.get("figure_export_output_count") or 0) if isinstance(apply_payload, dict) else 0,
        "artifact_registry_update_count": int(apply_payload.get("artifact_registry_update_count") or 0) if isinstance(apply_payload, dict) else 0,
        "asset_plan_update_counts": apply_payload.get("asset_plan_update_counts") if isinstance(apply_payload, dict) and isinstance(apply_payload.get("asset_plan_update_counts"), dict) else {},
    }
    summary["scout_analysis"] = _data_handoff_scout_summary(handoff_payload, apply_payload)
    return summary


def _artifact_source_key(prefix: str, label: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(label or ""))
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return f"{prefix}_{cleaned}" if cleaned else prefix


def _looks_like_local_artifact_path(raw: str) -> bool:
    text = str(raw or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered.startswith(("http://", "https://", "s3://", "gs://", "doi:", "pmid:")):
        return False
    if ":" in text and not Path(text).drive:
        prefix = text.split(":", 1)[0].lower()
        if prefix in {"asset", "image", "chart", "table", "icon"}:
            return False
    return True


def _artifact_dependency_source_files(
    workspace: Path,
    artifact_manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    payload = _load_json_if_exists(artifact_manifest_path)
    if not isinstance(payload, dict):
        return {}

    snapshots: dict[str, dict[str, Any]] = {}
    seen_paths: set[str] = set()

    def add(prefix: str, raw_path: Any, label: str = "") -> None:
        path_text = str(raw_path or "").strip()
        if not _looks_like_local_artifact_path(path_text):
            return
        path = _workspace_path(workspace, path_text)
        display_path = _display_path(workspace, path)
        if display_path in seen_paths:
            return
        key = _artifact_source_key(prefix, label or display_path)
        base_key = key
        index = 2
        while key in snapshots:
            key = f"{base_key}_{index}"
            index += 1
        snapshot = _file_snapshot(workspace, path)
        snapshot["dependency_role"] = prefix
        snapshots[key] = snapshot
        seen_paths.add(display_path)

    add(
        "artifact_producer",
        payload.get("producer_path") or payload.get("generated_by"),
        "manifest_producer",
    )
    add("artifact_summary", payload.get("analysis_summary"), "analysis_summary")
    add(
        "artifact_summary",
        payload.get("analysis_summary_markdown"),
        "analysis_summary_markdown",
    )
    source_paths = payload.get("source_paths")
    if isinstance(source_paths, list):
        for idx, source_path in enumerate(source_paths):
            add("artifact_source", source_path, f"source_path_{idx + 1}")

    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        return snapshots
    for output_idx, output in enumerate(outputs):
        if not isinstance(output, dict):
            continue
        output_id = str(output.get("id") or f"output_{output_idx + 1}")
        metadata = output.get("analysis_metadata") if isinstance(output.get("analysis_metadata"), dict) else {}
        add(
            "artifact_source",
            output.get("source_path") or metadata.get("source_path"),
            f"{output_id}_source",
        )
        add(
            "artifact_producer",
            metadata.get("producer_path") or metadata.get("generated_by") or output.get("producer"),
            f"{output_id}_producer",
        )
        for field in ("figure_path", "chart_json", "table_json", "path"):
            add("artifact_output", output.get(field), f"{output_id}_{field}")
        artifacts = output.get("artifacts")
        if isinstance(artifacts, list):
            for artifact_idx, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    continue
                artifact_id = str(
                    artifact.get("id")
                    or artifact.get("role")
                    or f"artifact_{artifact_idx + 1}"
                )
                add("artifact_output", artifact.get("path"), f"{output_id}_{artifact_id}")
    return snapshots


def _build_workspace_command(args: argparse.Namespace, workspace: Path) -> list[str]:
    command = ["python3", "scripts/build_workspace.py", "--workspace", str(workspace)]
    if getattr(args, "fast_first_pass", False):
        command.append("--fast-first-pass")
    bool_flags = (
        ("qa", "--qa"),
        ("skip_render", "--skip-render"),
        ("visual_review", "--visual-review"),
        ("fail_on_visual_review_warnings", "--fail-on-visual-review-warnings"),
        ("fail_on_whitespace_warnings", "--fail-on-whitespace-warnings"),
        ("fail_on_planning_warnings", "--fail-on-planning-warnings"),
        ("skip_preflight", "--skip-preflight"),
        ("strict_preflight", "--strict-preflight"),
        ("skip_asset_staging", "--skip-asset-staging"),
        ("allow_network_assets", "--allow-network-assets"),
        ("allow_generated_images", "--allow-generated-images"),
        ("plan_research_assets", "--plan-research-assets"),
        ("scaffold_data_artifacts", "--scaffold-data-artifacts"),
        ("skip_data_artifact_run", "--skip-data-artifact-run"),
        ("overwrite_data_artifacts", "--overwrite-data-artifacts"),
        ("auto_bind_artifacts", "--auto-bind-artifacts"),
        ("strict_provenance", "--strict-provenance"),
        ("overwrite", "--overwrite"),
    )
    for attr, flag in bool_flags:
        if getattr(args, "fast_first_pass", False) and attr in _FAST_FIRST_PASS_ATTRS:
            continue
        if getattr(args, attr, False):
            command.append(flag)
    for data_path in getattr(args, "data_path", []) or []:
        command.extend(["--data-path", str(data_path)])
    if args.renderer != "auto":
        command.extend(["--renderer", str(args.renderer)])
    if args.artifact_selection_out != "artifact_selections.auto.json":
        command.extend(["--artifact-selection-out", str(args.artifact_selection_out)])
    if args.artifact_bind_variants != "image-sidebar,chart,lab-run-results":
        command.extend(["--artifact-bind-variants", str(args.artifact_bind_variants)])
    if getattr(args, "artifact_bind_mode", "all") != ("lead" if getattr(args, "fast_first_pass", False) else "all"):
        command.extend(["--artifact-bind-mode", str(args.artifact_bind_mode)])
    if args.build_report != "build/build_workspace_report.json":
        command.extend(["--build-report", str(args.build_report)])
    return command


def _build_report_payload(
    *,
    workspace: Path,
    workspace_manifest_path: Path,
    manifest: dict[str, Any],
    style_contract_path: Path,
    deck_start_packet_path: Path,
    intake_answers_path: Path,
    design_contract_path: Path,
    data_analysis_handoff_path: Path,
    outline_authoring_handoff_path: Path,
    outline_authoring_handoff_apply_report_path: Path,
    outline_source_path: Path,
    outline_used_path: Path,
    design_brief_path: Path,
    content_plan_path: Path,
    evidence_plan_path: Path,
    asset_plan_path: Path,
    build_dir: Path,
    output_pptx: Path,
    resolved_style_preset: str,
    renderer_requested: str,
    renderer_used: str,
    args: argparse.Namespace,
    research_asset_report: Path | None,
    scaffold_report: Path | None,
    artifact_manifest_path: Path,
    artifact_selection_out: Path | None,
    artifact_apply_report: Path | None,
    planning_report: Path | None,
    preflight_report: Path | None,
    qa_report: Path,
    staged_manifest: Path,
    attribution_csv: Path,
    verify_log_path: Path | None,
    run_status: str,
    returncode: int,
    failed_step: str = "",
    step_returncodes: dict[str, int] | None = None,
    step_timings: list[dict[str, Any]] | None = None,
    total_duration_ms: int | None = None,
) -> dict[str, Any]:
    planning_summary = _json_report_summary(
        workspace,
        planning_report,
        count_keys=["error_count", "warning_count"],
    )
    preflight_summary = _json_report_summary(
        workspace,
        preflight_report,
        count_keys=["error_count", "warning_count"],
    )
    qa_summary = _json_report_summary(
        workspace,
        qa_report,
        count_keys=[
            "overflow_count",
            "overlap_count",
            "geometry_error_count",
            "geometry_warning_count",
            "whitespace_warning_count",
            "design_error_count",
            "design_warning_count",
            "visual_warning_count",
            "visual_review_warning_count",
        ],
    )
    artifact_apply_summary = _json_report_summary(
        workspace,
        artifact_apply_report,
        count_keys=["selection_count"],
    )
    artifact_apply_payload = _load_json_if_exists(artifact_apply_report)
    if isinstance(artifact_apply_payload, dict):
        artifact_apply_summary["auto_selected"] = artifact_apply_payload.get("auto_selected")
        artifact_apply_summary["auto_select_mode"] = artifact_apply_payload.get("auto_select_mode")
        artifact_apply_summary["changed"] = {
            "outline": artifact_apply_payload.get("outline_changed"),
            "content_plan": artifact_apply_payload.get("content_plan_changed"),
            "evidence_plan": artifact_apply_payload.get("evidence_plan_changed"),
            "design_brief": artifact_apply_payload.get("design_brief_changed"),
            "asset_plan": artifact_apply_payload.get("asset_plan_changed"),
        }

    options = {
        "qa": args.qa,
        "skip_render": args.skip_render,
        "visual_review": args.visual_review,
        "fail_on_visual_review_warnings": args.fail_on_visual_review_warnings,
        "fail_on_visual_warnings": True,
        "fail_on_design_warnings": True,
        "strict_geometry": True,
        "fast_first_pass": args.fast_first_pass,
        "fail_on_whitespace_warnings": args.fail_on_whitespace_warnings,
        "fail_on_planning_warnings": args.fail_on_planning_warnings,
        "skip_preflight": args.skip_preflight,
        "strict_preflight": args.strict_preflight,
        "skip_asset_staging": args.skip_asset_staging,
        "allow_network_assets": args.allow_network_assets,
        "allow_generated_images": args.allow_generated_images,
        "plan_research_assets": args.plan_research_assets,
        "scaffold_data_artifacts": args.scaffold_data_artifacts,
        "data_paths": [str(item) for item in args.data_path],
        "skip_data_artifact_run": args.skip_data_artifact_run,
        "overwrite_data_artifacts": args.overwrite_data_artifacts,
        "auto_bind_artifacts": args.auto_bind_artifacts,
        "artifact_bind_variants": args.artifact_bind_variants,
        "artifact_bind_mode": args.artifact_bind_mode,
        "strict_provenance": args.strict_provenance,
        "overwrite": args.overwrite,
    }

    source_files = {
        "workspace_manifest": _file_snapshot(workspace, workspace_manifest_path),
        "style_contract": _file_snapshot(workspace, style_contract_path),
        "deck_start_packet": _file_snapshot(workspace, deck_start_packet_path),
        "intake_answers": _file_snapshot(workspace, intake_answers_path),
        "intake_apply_report": _file_snapshot(workspace, workspace / "intake_apply_report.json"),
        "design_contract": _file_snapshot(workspace, design_contract_path),
        "design_contract_apply_report": _file_snapshot(
            workspace,
            workspace / "design_contract_apply_report.json",
        ),
        "style_extract_report": _file_snapshot(workspace, workspace / "style_extract_report.json"),
        "style_extract_design_brief": _file_snapshot(
            workspace,
            workspace / "style_extract_design_brief.json",
        ),
        "style_fragment_apply_report": _file_snapshot(
            workspace,
            workspace / "style_fragment_apply_report.json",
        ),
        "data_analysis_handoff": _file_snapshot(workspace, data_analysis_handoff_path),
        "data_analysis_handoff_apply_report": _file_snapshot(
            workspace,
            _data_analysis_handoff_apply_report_path(workspace, build_dir),
        ),
        "data_analysis_handoff_selection": _file_snapshot(
            workspace,
            _data_analysis_handoff_selection_path(workspace, build_dir),
        ),
        "outline_authoring_handoff": _file_snapshot(workspace, outline_authoring_handoff_path),
        "outline_authoring_handoff_apply_report": _file_snapshot(
            workspace,
            outline_authoring_handoff_apply_report_path,
        ),
        "design_brief": _file_snapshot(workspace, design_brief_path),
        "content_plan": _file_snapshot(workspace, content_plan_path),
        "evidence_plan": _file_snapshot(workspace, evidence_plan_path),
        "asset_plan": _file_snapshot(workspace, asset_plan_path),
        "outline_source": _file_snapshot(workspace, outline_source_path),
        "outline_used": _file_snapshot(workspace, outline_used_path),
        "artifact_manifest": _file_snapshot(workspace, artifact_manifest_path),
        "artifact_selection": _file_snapshot(
            workspace,
            artifact_selection_out or _workspace_path(workspace, args.artifact_selection_out),
        ),
        "artifact_manifest_apply_report": _file_snapshot(
            workspace,
            artifact_apply_report or (build_dir / "artifact_manifest_apply.json"),
        ),
    }
    source_files.update(_artifact_dependency_source_files(workspace, artifact_manifest_path))
    outputs = {
        "pptx": _file_snapshot(workspace, output_pptx),
        "build_dir": _display_path(workspace, build_dir),
        "staged_manifest": _file_snapshot(workspace, staged_manifest),
        "attribution_csv": _file_snapshot(workspace, attribution_csv),
        "build_report": _display_path(workspace, _workspace_path(workspace, args.build_report)),
    }
    reports = {
        "research_assets": _json_report_summary(workspace, research_asset_report, count_keys=[]),
        "data_artifact_scaffold": _json_report_summary(workspace, scaffold_report, count_keys=[]),
        "artifact_apply": artifact_apply_summary,
        "planning": planning_summary,
        "preflight": preflight_summary,
        "qa": qa_summary,
        "verify_narration_log": _file_snapshot(workspace, verify_log_path),
    }
    artifact_selection_path = artifact_selection_out or _workspace_path(
        workspace,
        args.artifact_selection_out,
    )
    timings = [item for item in (step_timings or []) if isinstance(item, dict)]
    longest_step = max(timings, key=lambda item: int(item.get("duration_ms") or 0), default={})
    speed = {
        "schema": "build_workspace_speed_v1",
        "total_duration_ms": int(total_duration_ms or 0),
        "step_count": len(timings),
        "steps": timings,
        "longest_step": {
            "step": str(longest_step.get("step") or ""),
            "duration_ms": int(longest_step.get("duration_ms") or 0),
        },
        "renderer_used": renderer_used,
        "fast_first_pass": bool(args.fast_first_pass),
        "skip_render": bool(args.skip_render),
        "visual_review": bool(args.visual_review),
    }
    return {
        "schema_version": 1,
        "workspace": str(workspace),
        "run": {
            "status": run_status,
            "returncode": int(returncode),
            "failed_step": failed_step,
            "step_returncodes": step_returncodes or {},
        },
        "style_preset": resolved_style_preset,
        "renderer": {
            "requested": renderer_requested,
            "used": renderer_used,
        },
        "options": options,
        "manifest": {
            "build_dir": manifest.get("build_dir", "build"),
            "outline": manifest.get("outline", "outline.json"),
            "style_contract": manifest.get("style_contract", "style_contract.json"),
        },
        "source_files": source_files,
        "artifact_selection": _artifact_selection_summary(workspace, artifact_selection_path),
        "artifact_context": _build_artifact_context(
            workspace,
            artifact_manifest_path=artifact_manifest_path,
            artifact_selection_path=artifact_selection_path,
        ),
        "data_analysis_handoff": _data_analysis_handoff_summary(workspace, build_dir),
        "quality_context": _build_quality_context(design_brief_path),
        "speed": speed,
        "outputs": outputs,
        "reports": reports,
        "next_commands": {
            "repeat_build": _build_workspace_command(args, workspace),
            "planning_only": [
                "python3",
                "scripts/validate_planning.py",
                "--workspace",
                str(workspace),
                "--report",
                str(planning_report or (build_dir / "planning_validation.json")),
            ],
            "qa_only": [
                "python3",
                "scripts/qa_gate.py",
                "--input",
                str(output_pptx),
                "--outdir",
                str(qa_report.parent),
                "--style-preset",
                resolved_style_preset,
                "--strict-geometry",
                "--skip-render",
                "--outline",
                str(outline_used_path),
                "--design-brief",
                str(design_brief_path),
                "--report",
                str(qa_report),
            ],
        },
    }


_DECK_STYLE_SCALAR_KEYS = {
    "palette_key",
    "font_pair",
    "style_seed",
    "visual_density",
    "header_mode",
    "header_variant",
    "header_rule_color",
    "title_layout",
    "title_motif",
    "section_motif",
    "timeline_mode",
    "matrix_mode",
    "stats_mode",
    "cards_mode",
    "chart_treatment",
    "footer_mode",
    "footer_source_label",
    "footer_refs_label",
    "summary_callout_mode",
    "figure_table_treatment",
}

_STYLE_ENUM_VALUES = {
    "visual_density": {"low", "medium", "high"},
    "header_mode": {"bar", "stack", "eyebrow", "lab-clean", "lab-card"},
    "header_variant": {
        "auto",
        "left-accent",
        "split-rule",
        "title-rule",
        "side-rail",
        "top-bottom-rule",
        "plain",
    },
    "title_layout": {
        "split-hero",
        "lab-plate",
        "command-center",
        "poster",
        "masthead",
        "light-atlas",
    },
    "title_motif": {"orbit", "network", "editorial", "none"},
    "section_motif": {"rail-dots", "numbered-tabs", "plain", "none"},
    "timeline_mode": {"rail-cards", "staggered", "open-events", "bands", "chapter-spread"},
    "matrix_mode": {"cards", "open-quadrants"},
    "stats_mode": {"tiles", "feature-left", "policy-bands"},
    "cards_mode": {"feature-left", "staggered-row"},
    "chart_treatment": {"standard", "facts-below", "facts-right", "minimal"},
    "footer_mode": {"standard", "source-line", "none"},
    "summary_callout_mode": {"default", "lab-box"},
    "figure_table_treatment": {"figure-first", "table-first", "stats-strip", "image-sidebar"},
}

_LAB_HEADER_VARIANTS = (
    "left-accent",
    "split-rule",
    "title-rule",
    "side-rail",
    "top-bottom-rule",
    "plain",
)

_LAB_HEADER_VARIANT_ALIASES = {
    "auto": "auto",
    "default": "left-accent",
    "left": "left-accent",
    "left-rule": "left-accent",
    "left-accent": "left-accent",
    "split": "split-rule",
    "split-rule": "split-rule",
    "full": "split-rule",
    "title": "title-rule",
    "title-rule": "title-rule",
    "underline": "title-rule",
    "rail": "side-rail",
    "side-rail": "side-rail",
    "bracket": "side-rail",
    "frame": "top-bottom-rule",
    "frame-rule": "top-bottom-rule",
    "top-bottom": "top-bottom-rule",
    "top-bottom-rule": "top-bottom-rule",
    "top": "top-bottom-rule",
    "plain": "plain",
    "minimal": "plain",
    "none": "plain",
    "no-line": "plain",
    "no-lines": "plain",
    "no-rule": "plain",
    "no-rules": "plain",
}


def _canonical_style_value(key: str, value: str, *, path: str) -> str:
    text = str(value or "").strip()
    allowed = _STYLE_ENUM_VALUES.get(key)
    if allowed is None:
        return text
    normalized = text.lower()
    if normalized not in allowed:
        valid_text = ", ".join(sorted(allowed))
        raise ValueError(f"Unsupported {path} value {text!r}. Valid values: {valid_text}")
    return normalized


def _normalize_lab_header_variant(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return _LAB_HEADER_VARIANT_ALIASES.get(raw, raw)


def _hash_string_fnv32(value: str) -> int:
    result = 2166136261
    for char in str(value or ""):
        result ^= ord(char)
        result = (result * 16777619) & 0xFFFFFFFF
    return result


def _style_string_list(
    source: Any,
    key: str,
    *,
    path: str,
    allowed: set[str] | None = None,
) -> list[str]:
    if not isinstance(source, dict) or key not in source:
        return []
    value = source.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Invalid {path}: expected a list")
    items: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"Invalid {path}[{idx}]: expected a string")
        text = item.strip()
        if not text:
            continue
        normalized = text.lower()
        if allowed is not None and normalized not in allowed:
            valid_text = ", ".join(sorted(allowed))
            raise ValueError(f"Unsupported {path}[{idx}] value {text!r}. Valid values: {valid_text}")
        items.append(normalized if allowed is not None else text)
    return items


def _merge_style_values(target: dict[str, Any], source: Any, keys: set[str], *, base_path: str) -> None:
    if not isinstance(source, dict):
        return
    for key in sorted(keys):
        value = source.get(key)
        if isinstance(value, str) and value.strip() and key not in target:
            target[key] = _canonical_style_value(key, value, path=f"{base_path}.{key}")
        elif isinstance(value, bool) and key not in target:
            target[key] = value


def _merge_header_variants(target: dict[str, Any], source: Any, *, path: str) -> None:
    if "header_variants" in target:
        return
    pool = _style_string_list(
        source,
        "header_variants",
        path=path,
        allowed=_STYLE_ENUM_VALUES["header_variant"],
    )
    if pool:
        target["header_variants"] = pool


def _first_nonempty(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _style_mix_matrix(brief: dict[str, Any]) -> dict[str, Any]:
    direct = brief.get("style_mix_matrix")
    if isinstance(direct, dict):
        return direct
    style_system = brief.get("style_system")
    if isinstance(style_system, dict) and isinstance(style_system.get("style_mix_matrix"), dict):
        return style_system["style_mix_matrix"]
    return {}


def _style_mix_matrix_path(brief: dict[str, Any]) -> str:
    if isinstance(brief.get("style_mix_matrix"), dict):
        return "design_brief.style_mix_matrix"
    style_system = brief.get("style_system")
    if isinstance(style_system, dict) and isinstance(style_system.get("style_mix_matrix"), dict):
        return "design_brief.style_system.style_mix_matrix"
    return "design_brief.style_mix_matrix"


def _style_mix_seed(brief: dict[str, Any], style: dict[str, Any]) -> str:
    if isinstance(style.get("style_seed"), str) and style["style_seed"].strip():
        return style["style_seed"].strip()
    style_system = brief.get("style_system")
    if isinstance(style_system, dict):
        value = style_system.get("style_seed")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("topic", "design_dna", "format_promise"):
        value = brief.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    deck_identity = brief.get("deck_identity")
    if isinstance(deck_identity, dict):
        value = deck_identity.get("working_title")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "presentation-skill-style-mix"


def _seeded_pool_choice(pool: list[str], *, seed: str, key: str) -> str:
    if not pool:
        return ""
    digest = hashlib.sha256(f"{seed}\n{key}\n{'|'.join(pool)}".encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], byteorder="big") % len(pool)
    return pool[index]


def _apply_seeded_style_pool(
    style: dict[str, Any],
    mix: dict[str, Any],
    *,
    style_key: str,
    pool_key: str,
    seed: str,
    base_path: str,
) -> None:
    if style_key in style:
        return
    pool = _style_string_list(
        mix,
        pool_key,
        path=f"{base_path}.{pool_key}",
        allowed=_STYLE_ENUM_VALUES[style_key],
    )
    choice = _seeded_pool_choice(pool, seed=seed, key=style_key)
    if choice:
        style[style_key] = choice


def _deck_style_from_design_brief(brief: Any) -> dict[str, Any]:
    """Translate the reusable design contract into renderer-visible defaults."""
    if not isinstance(brief, dict):
        return {}
    style: dict[str, Any] = {}
    style_system = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    if isinstance(style_system, dict):
        _merge_style_values(
            style,
            style_system,
            {"palette_key", "font_pair", "style_seed", "visual_density"},
            base_path="design_brief.style_system",
        )
        _merge_style_values(
            style,
            style_system.get("header_system"),
            _DECK_STYLE_SCALAR_KEYS,
            base_path="design_brief.style_system.header_system",
        )
        _merge_style_values(
            style,
            style_system.get("footer_system"),
            _DECK_STYLE_SCALAR_KEYS | {"footer_page_numbers"},
            base_path="design_brief.style_system.footer_system",
        )
        _merge_style_values(
            style,
            style_system.get("title_slide_system"),
            _DECK_STYLE_SCALAR_KEYS,
            base_path="design_brief.style_system.title_slide_system",
        )
        _merge_style_values(
            style,
            style_system.get("section_system"),
            _DECK_STYLE_SCALAR_KEYS,
            base_path="design_brief.style_system.section_system",
        )
        _merge_style_values(
            style,
            style_system.get("figure_table_system"),
            _DECK_STYLE_SCALAR_KEYS,
            base_path="design_brief.style_system.figure_table_system",
        )
        _merge_style_values(
            style,
            style_system.get("chart_system"),
            _DECK_STYLE_SCALAR_KEYS,
            base_path="design_brief.style_system.chart_system",
        )
        header_system = style_system.get("header_system")
        pool = _style_string_list(
            header_system,
            "header_variants",
            path="design_brief.style_system.header_system.header_variants",
            allowed=_STYLE_ENUM_VALUES["header_variant"],
        )
        if pool and "header_variants" not in style:
            style["header_variants"] = pool

    renderer_treatments = brief.get("renderer_treatments")
    _merge_style_values(
        style,
        renderer_treatments,
        _DECK_STYLE_SCALAR_KEYS | {"footer_page_numbers"},
        base_path="design_brief.renderer_treatments",
    )
    _merge_header_variants(
        style,
        renderer_treatments,
        path="design_brief.renderer_treatments.header_variants",
    )
    design_deck_style = brief.get("deck_style")
    _merge_style_values(
        style,
        design_deck_style,
        _DECK_STYLE_SCALAR_KEYS | {"footer_page_numbers"},
        base_path="design_brief.deck_style",
    )
    _merge_header_variants(
        style,
        design_deck_style,
        path="design_brief.deck_style.header_variants",
    )

    mix = _style_mix_matrix(brief)
    mix_path = _style_mix_matrix_path(brief)
    mix_seed = _style_mix_seed(brief, style)
    header_pool = _style_string_list(
        mix,
        "header_variant_pool",
        path=f"{mix_path}.header_variant_pool",
        allowed=_STYLE_ENUM_VALUES["header_variant"],
    )
    if header_pool and "header_variants" not in style:
        style["header_variants"] = header_pool
    if header_pool and "header_variant" not in style:
        style["header_variant"] = "auto"
    for style_key, pool_key in (
        ("title_layout", "title_layout_pool"),
        ("section_motif", "section_motif_pool"),
        ("timeline_mode", "timeline_mode_pool"),
        ("matrix_mode", "matrix_mode_pool"),
        ("stats_mode", "stats_mode_pool"),
        ("cards_mode", "cards_mode_pool"),
        ("chart_treatment", "chart_treatment_pool"),
        ("summary_callout_mode", "summary_callout_mode_pool"),
        ("figure_table_treatment", "figure_table_treatment_pool"),
        ("footer_mode", "footer_pool"),
    ):
        _apply_seeded_style_pool(
            style,
            mix,
            style_key=style_key,
            pool_key=pool_key,
            seed=mix_seed,
            base_path=mix_path,
        )
    return style


def _style_preset_candidates(brief: Any) -> list[tuple[str, Any]]:
    if not isinstance(brief, dict):
        return []
    visual_system = brief.get("visual_system") if isinstance(brief.get("visual_system"), dict) else {}
    style_system = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    candidates: list[tuple[str, Any]] = [
        ("design_brief.style_preset", brief.get("style_preset")),
        (
            "design_brief.style_system.style_preset",
            style_system.get("style_preset") if isinstance(style_system, dict) else None,
        ),
        (
            "design_brief.visual_system.style_preset",
            visual_system.get("style_preset") if isinstance(visual_system, dict) else None,
        ),
    ]
    deck_style = brief.get("deck_style")
    if isinstance(deck_style, dict):
        candidates.append(("design_brief.deck_style.style_preset", deck_style.get("style_preset")))
    renderer_treatments = brief.get("renderer_treatments")
    if isinstance(renderer_treatments, dict):
        candidates.append(
            (
                "design_brief.renderer_treatments.style_preset",
                renderer_treatments.get("style_preset"),
            )
        )
    return candidates


def _style_preset_from_design_brief(brief: Any) -> str:
    resolved: list[tuple[str, str]] = []
    for path, value in _style_preset_candidates(brief):
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"Invalid design_brief style_preset at {path}: expected string")
        text = value.strip()
        if text:
            resolved.append((path, _canonical_style_preset(text, source="design_brief")))
    unique_presets = {preset.lower(): preset for _, preset in resolved}
    if len(unique_presets) > 1:
        detail = ", ".join(f"{path}={preset!r}" for path, preset in resolved)
        raise ValueError(
            "Conflicting design_brief style_preset values: "
            f"{detail}. Keep one preset source or make all preset fields match."
        )
    if resolved:
        return resolved[0][1]
    return ""


def _valid_style_presets() -> dict[str, str]:
    return {str(name).strip().lower(): str(name).strip() for name in available_presets()}


def _canonical_style_preset(value: str, *, source: str) -> str:
    preset = str(value or "").strip()
    valid = _valid_style_presets()
    key = preset.lower()
    if key not in valid:
        valid_text = ", ".join(valid[name] for name in sorted(valid))
        raise ValueError(
            f"Unsupported {source} style_preset {preset!r}. Valid presets: {valid_text}"
        )
    return valid[key]


def _resolved_style_preset(
    *,
    workspace: Path,
    design_brief_path: Path,
    build_cfg: dict[str, Any],
) -> str:
    fallback = _canonical_style_preset(
        str(build_cfg.get("style_preset") or "executive-clinical").strip() or "executive-clinical",
        source="style_contract",
    )
    if not design_brief_path.exists():
        return fallback
    try:
        brief = _load_json(design_brief_path)
    except (OSError, json.JSONDecodeError):
        return fallback
    preset = _style_preset_from_design_brief(brief)
    if not preset:
        return fallback
    preset = _canonical_style_preset(preset, source="design_brief")
    if preset != fallback:
        try:
            display_path = design_brief_path.relative_to(workspace)
        except ValueError:
            display_path = design_brief_path
        print(
            f"[build_workspace] using style_preset={preset!r} from {display_path} "
            f"(style_contract fallback was {fallback!r})",
            file=sys.stderr,
        )
    return preset


def _resolved_slide_header_variant(
    slide: dict[str, Any],
    deck_style: dict[str, Any],
    *,
    slide_index: int,
) -> dict[str, Any]:
    slide_type = str(slide.get("type") or "content").strip().lower()
    if slide_type in {"title", "section"}:
        return {}
    header_mode = str(slide.get("header_mode") or deck_style.get("header_mode") or "bar").strip().lower()
    if header_mode not in {"lab-clean", "lab-card"}:
        return {}
    if header_mode == "lab-card":
        return {
            "header_mode": header_mode,
            "header_variant": "left-accent",
            "header_variant_source": "lab-card-default",
            "header_variant_pool": ["left-accent"],
        }

    requested = _normalize_lab_header_variant(
        slide.get("header_variant") or deck_style.get("header_variant") or "left-accent"
    )
    raw_pool = (
        slide.get("header_variants")
        if isinstance(slide.get("header_variants"), list)
        else deck_style.get("header_variants")
        if isinstance(deck_style.get("header_variants"), list)
        else list(_LAB_HEADER_VARIANTS)
    )
    pool = [
        item
        for item in (_normalize_lab_header_variant(value) for value in raw_pool)
        if item in _LAB_HEADER_VARIANTS
    ] or list(_LAB_HEADER_VARIANTS)

    if requested and requested != "auto" and requested in _LAB_HEADER_VARIANTS:
        variant = requested
        source = "explicit"
    else:
        seed = "|".join(
            [
                str(slide.get("style_seed") or deck_style.get("style_seed") or ""),
                str(slide_index),
                str(slide.get("title") or ""),
                str(slide.get("subtitle") or ""),
            ]
        )
        variant = pool[_hash_string_fnv32(seed) % len(pool)]
        source = "auto"

    return {
        "header_mode": header_mode,
        "header_variant": variant,
        "header_variant_source": source,
        "header_variant_pool": pool,
    }


def _annotate_resolved_slide_treatments(
    resolved_outline: dict[str, Any],
    resolved_style: dict[str, Any],
) -> dict[str, Any]:
    slides = resolved_outline.get("slides")
    if not isinstance(slides, list):
        return {}
    header_by_slide: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for slide_index, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        treatment = _resolved_slide_header_variant(
            slide,
            resolved_style,
            slide_index=slide_index,
        )
        if not treatment:
            continue
        existing = slide.get("resolved_treatments")
        resolved_treatments = dict(existing) if isinstance(existing, dict) else {}
        resolved_treatments.update(treatment)
        slide["resolved_treatments"] = resolved_treatments
        slide_id = str(
            slide.get("slide_id")
            or slide.get("id")
            or slide.get("slug")
            or f"s{slide_index}"
        )
        variant = str(treatment.get("header_variant") or "")
        if variant:
            counts[variant] = counts.get(variant, 0) + 1
        header_by_slide.append(
            {
                "slide_id": slide_id,
                "slide_index": slide_index,
                "title": str(slide.get("title") or ""),
                "header_mode": treatment.get("header_mode"),
                "header_variant": variant,
                "header_variant_source": treatment.get("header_variant_source"),
            }
        )
    if not header_by_slide:
        return {}
    return {
        "header_variant_by_slide": header_by_slide,
        "header_variant_counts": dict(sorted(counts.items())),
        "unique_header_variant_count": len(counts),
    }


def _resolved_outline_path(
    *,
    workspace: Path,
    outline_path: Path,
    design_brief_path: Path,
    build_dir: Path,
) -> Path:
    if not design_brief_path.exists():
        return outline_path
    try:
        outline = _load_json(outline_path)
        brief = _load_json(design_brief_path)
    except (OSError, json.JSONDecodeError):
        return outline_path
    if not isinstance(outline, dict):
        return outline_path
    brief_style = _deck_style_from_design_brief(brief)
    if not brief_style:
        return outline_path
    outline_style = outline.get("deck_style") if isinstance(outline.get("deck_style"), dict) else {}
    resolved_style = {**brief_style, **outline_style}
    resolved_outline = copy.deepcopy(outline)
    resolved_outline["deck_style"] = resolved_style
    treatment_summary = _annotate_resolved_slide_treatments(resolved_outline, resolved_style)
    if treatment_summary:
        resolved_outline["resolved_treatment_summary"] = treatment_summary
    if resolved_style == outline_style and not treatment_summary:
        return outline_path
    out_path = build_dir / "outline_resolved.json"
    _write_json_if_changed(out_path, resolved_outline)
    try:
        display_path = out_path.relative_to(workspace)
    except ValueError:
        display_path = out_path
    print(
        f"[build_workspace] resolved deck_style defaults from design_brief.json -> {display_path}",
        file=sys.stderr,
    )
    return out_path


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and optionally QA a persistent deck workspace.")
    parser.add_argument("--workspace", required=True, help="Workspace directory created by init_deck_workspace.py")
    parser.add_argument(
        "--fast-first-pass",
        action="store_true",
        help=(
            "Shortcut for the strict render-free data-to-evidence first pass: "
            "--scaffold-data-artifacts --auto-bind-artifacts --artifact-bind-mode lead --qa --skip-render "
            "--fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite."
        ),
    )
    parser.add_argument("--qa", action="store_true", help="Run qa_gate.py after building")
    parser.add_argument("--skip-render", action="store_true", help="Pass --skip-render through to qa_gate.py")
    parser.add_argument(
        "--visual-review",
        action="store_true",
        help=(
            "When --qa is set, also create a visual-review packet with contact "
            "sheet, wrap heuristics, and layout-rhythm findings."
        ),
    )
    parser.add_argument(
        "--fail-on-visual-review-warnings",
        action="store_true",
        help="When --visual-review is set, fail QA on warning-level visual-review findings.",
    )
    parser.add_argument(
        "--fail-on-whitespace-warnings",
        action="store_true",
        help=(
            "When --qa is set, fail on layout_lint dead-space warnings "
            "(empty_ratio_too_high, content_span_too_short, content_span_too_narrow)."
        ),
    )
    parser.add_argument(
        "--fail-on-planning-warnings",
        action="store_true",
        help=(
            "Abort before build when validate_planning.py reports warning-only "
            "source-planning issues. Use for final reusable/report decks."
        ),
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the static outline preflight linter that normally runs before build.",
    )
    parser.add_argument(
        "--strict-preflight",
        action="store_true",
        help="Abort the build if preflight finds blocking errors (exit code 2).",
    )
    parser.add_argument(
        "--skip-asset-staging",
        action="store_true",
        help="Do not run asset_stage.py even when asset_plan.json exists",
    )
    parser.add_argument(
        "--allow-network-assets",
        action="store_true",
        help="Allow Wikimedia Commons downloads during asset staging",
    )
    parser.add_argument(
        "--allow-generated-images",
        action="store_true",
        help="Allow OpenAI Images API calls for generated_images entries in asset_plan.json",
    )
    parser.add_argument(
        "--plan-research-assets",
        action="store_true",
        help=(
            "Before staging, populate a stub asset_plan.json with Wikimedia "
            "queries and update selected slides to use staged image aliases. "
            "Requires --allow-network-assets for a full image-backed build."
        ),
    )
    parser.add_argument(
        "--scaffold-data-artifacts",
        action="store_true",
        help=(
            "Before validation/staging, infer simple charts and summary tables "
            "from local CSV/TSV/XLSX/JSON data, write assets/make_figures.py, "
            "update design_brief.json and asset_plan.json, and run the generated "
            "script unless --skip-data-artifact-run is set."
        ),
    )
    parser.add_argument(
        "--data-path",
        action="append",
        default=[],
        help=(
            "Data file or directory to pass to scaffold_figure_artifacts.py. "
            "May be supplied multiple times. Defaults to workspace data/ and assets/."
        ),
    )
    parser.add_argument(
        "--skip-data-artifact-run",
        action="store_true",
        help="Write/update the data artifact scaffold but do not run assets/make_figures.py.",
    )
    parser.add_argument(
        "--overwrite-data-artifacts",
        action="store_true",
        help="Allow scaffold_figure_artifacts.py to overwrite an existing figure script.",
    )
    parser.add_argument(
        "--auto-bind-artifacts",
        action="store_true",
        help=(
            "Before planning validation, apply assets/artifacts_manifest.json "
            "with deterministic figure/chart/table selections so generated "
            "data artifacts become editable evidence slides."
        ),
    )
    parser.add_argument(
        "--artifact-selection-out",
        default="artifact_selections.auto.json",
        help=(
            "Workspace-relative or absolute path for the generated selection "
            "JSON written by --auto-bind-artifacts."
        ),
    )
    parser.add_argument(
        "--artifact-bind-variants",
        default="image-sidebar,chart,lab-run-results",
        help="Comma-separated variant preference list for --auto-bind-artifacts.",
    )
    parser.add_argument(
        "--artifact-bind-mode",
        choices=("all", "recommended", "lead"),
        default=None,
        help=(
            "Selection mode for --auto-bind-artifacts. Defaults to 'lead' with "
            "--fast-first-pass and 'all' otherwise."
        ),
    )
    parser.add_argument(
        "--build-report",
        default="build/build_workspace_report.json",
        help=(
            "Workspace-relative or absolute path for the deterministic build "
            "ledger written after render/QA, including strict QA failures."
        ),
    )
    parser.add_argument(
        "--skip-build-report",
        action="store_true",
        help="Do not write build/build_workspace_report.json after render/QA.",
    )
    parser.add_argument(
        "--strict-provenance",
        action="store_true",
        help="Require local staged assets to include provenance metadata",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite the built .pptx output")
    parser.add_argument(
        "--renderer",
        choices=("python", "pptxgenjs", "auto"),
        default="auto",
        help=(
            "Which renderer to invoke for the .pptx. 'auto' (default) routes to pptxgenjs "
            "unless the outline has a python-only variant. "
            "'python' forces build_deck.py. 'pptxgenjs' forces build_deck_pptxgenjs.js via node."
        ),
    )
    args = parser.parse_args()
    explicit_artifact_bind_mode = args.artifact_bind_mode
    if args.fast_first_pass:
        for attr in _FAST_FIRST_PASS_ATTRS:
            setattr(args, attr, True)
    if explicit_artifact_bind_mode is None:
        args.artifact_bind_mode = "lead" if args.fast_first_pass else "all"
    return args


def _pick_auto_renderer(outline_path: Path) -> str:
    """Return 'pptxgenjs' if the outline looks like it benefits from it, else 'python'.

    Route to pptxgenjs (HTML-typography path) when ANY slide:
    - is a `section` divider, OR
    - has visual_intent in {timeline, hero, comparison}, OR
    - uses the `timeline`, `stats`, `kpi-hero`, or `table` variant
      (pptxgenjs renders these with richer typography than python-pptx,
      especially tables where the HTML path uses native addTable).
    Route to python only when the outline has variants pptxgenjs still
    shouldn't own. The default path handles the common designed layouts
    (matrix, comparison-2col, table, stats, timeline, flow, generated-image)
    because it has better typography and faster iteration.
    """
    try:
        data = json.loads(outline_path.read_text(encoding="utf-8"))
    except Exception:
        return "python"
    slides = data.get("slides") if isinstance(data, dict) else None
    if not isinstance(slides, list):
        return "python"

    # Variants that only render correctly under python-pptx because the
    # pptxgenjs path hasn't implemented them yet. Keep this list deliberately
    # small; chart, mermaid_source, hero_image/image-sidebar, diagram, and
    # visual_intent:flow are now handled natively by the pptxgenjs path.
    python_only_variants: set[str] = set()
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        variant = str(slide.get("variant", "") or "").strip().lower()
        if variant in python_only_variants:
            return "python"

    # Default: pptxgenjs. It's the richer-typography path with native mermaid
    # and hero support.
    return "pptxgenjs"


def main() -> int:
    args = _args()
    workflow_started = time.perf_counter()
    step_timings: list[dict[str, Any]] = []
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists():
        raise FileNotFoundError(f"Workspace not found: {workspace}")

    workspace_manifest_path = workspace / "workspace.json"
    manifest = _load_json(workspace_manifest_path)
    style_contract_path = workspace / manifest["style_contract"]
    deck_start_packet_path = workspace / "deck_start_packet.json"
    intake_answers_path = workspace / "intake_answers.json"
    design_contract_path = workspace / "design_contract.json"
    data_analysis_handoff_path = workspace / "data_analysis_handoff.json"
    outline_authoring_handoff_path = workspace / "outline_authoring_handoff.json"
    outline_authoring_handoff_apply_report_path = (
        workspace / "outline_authoring_handoff_apply_report.json"
    )
    contract = _load_json(style_contract_path)

    outline_source_path = workspace / manifest["outline"]
    outline_path = outline_source_path
    design_brief_path = workspace / manifest.get("design_brief", "design_brief.json")
    content_plan_path = workspace / manifest.get("content_plan", "content_plan.json")
    evidence_plan_path = workspace / manifest.get("evidence_plan", "evidence_plan.json")
    build_cfg = contract.get("build", {})
    build_dir = workspace / manifest.get("build_dir", "build")
    build_dir.mkdir(parents=True, exist_ok=True)
    try:
        resolved_style_preset = _resolved_style_preset(
            workspace=workspace,
            design_brief_path=design_brief_path,
            build_cfg=build_cfg,
        )
    except ValueError as exc:
        print(f"[build_workspace] {exc}", file=sys.stderr)
        return 2

    output_pptx = workspace / build_cfg.get("output_pptx", "build/deck.pptx")
    qa_dir = workspace / build_cfg.get("qa_dir", "build/qa")
    qa_report = workspace / build_cfg.get("qa_report", "build/qa/report.json")
    qa_dir.mkdir(parents=True, exist_ok=True)

    if output_pptx.exists() and not args.overwrite:
        raise FileExistsError(
            f"Output already exists: {output_pptx}. Pass --overwrite to replace it."
        )

    scripts_dir = Path(__file__).resolve().parent
    py = sys.executable

    asset_plan = workspace / manifest.get("asset_plan", "asset_plan.json")
    staged_assets_dir = workspace / manifest.get("staged_assets_dir", "assets/staged")
    staged_manifest = staged_assets_dir / "staged_manifest.json"
    attribution_csv = workspace / "assets" / "attribution.csv"
    research_asset_report: Path | None = None
    scaffold_report: Path | None = None
    artifact_manifest = workspace / "assets" / "artifacts_manifest.json"
    artifact_selection_out: Path | None = None
    artifact_apply_report: Path | None = None
    planning_report: Path | None = None

    if args.plan_research_assets:
        if not args.allow_network_assets:
            print(
                "[build_workspace] --plan-research-assets creates Wikimedia "
                "queries and outline aliases, so it requires "
                "--allow-network-assets for the build to contain images.",
                file=sys.stderr,
            )
            return 2
        planner = scripts_dir / "plan_research_assets.py"
        if not planner.exists():
            raise FileNotFoundError(f"Research asset planner not found: {planner}")
        research_asset_report = build_dir / "research_asset_plan.json"
        _run_timed(
            [
                py,
                str(planner),
                "--workspace",
                str(workspace),
                "--apply-to-outline",
                "--report",
                str(research_asset_report),
            ],
            timings=step_timings,
            step="plan_research_assets",
        )

    if args.scaffold_data_artifacts:
        scaffold_script = scripts_dir / "scaffold_figure_artifacts.py"
        if not scaffold_script.exists():
            raise FileNotFoundError(f"Data artifact scaffold script not found: {scaffold_script}")
        scaffold_report = build_dir / "data_artifact_scaffold.json"
        scaffold_cmd = [
            py,
            str(scaffold_script),
            "--workspace",
            str(workspace),
            "--report",
            str(scaffold_report),
            "--bind-outline",
        ]
        for data_path in args.data_path:
            scaffold_cmd.extend(["--data-path", str(data_path)])
        if not args.skip_data_artifact_run:
            scaffold_cmd.append("--run")
        if args.overwrite_data_artifacts:
            scaffold_cmd.append("--overwrite")
        _run_timed(scaffold_cmd, timings=step_timings, step="scaffold_data_artifacts")

    if args.auto_bind_artifacts:
        bind_script = scripts_dir / "apply_artifact_manifest_bindings.py"
        if not bind_script.exists():
            raise FileNotFoundError(f"Artifact manifest binding script not found: {bind_script}")
        if not artifact_manifest.exists():
            print(
                "[build_workspace] --auto-bind-artifacts requires "
                "assets/artifacts_manifest.json. Run with --scaffold-data-artifacts "
                "or create the manifest first.",
                file=sys.stderr,
            )
            return 2
        artifact_selection_out = _workspace_path(workspace, args.artifact_selection_out)
        artifact_apply_report = build_dir / "artifact_manifest_apply.json"
        _run_timed(
            [
                py,
                str(bind_script),
                "--workspace",
                str(workspace),
                "--auto-select",
                "--selection-out",
                str(artifact_selection_out),
                "--variants",
                str(args.artifact_bind_variants),
                "--auto-select-mode",
                str(args.artifact_bind_mode),
                "--report",
                str(artifact_apply_report),
            ],
            timings=step_timings,
            step="auto_bind_artifacts",
        )

    try:
        outline_path = _resolved_outline_path(
            workspace=workspace,
            outline_path=outline_path,
            design_brief_path=design_brief_path,
            build_dir=build_dir,
        )
    except ValueError as exc:
        print(f"[build_workspace] {exc}", file=sys.stderr)
        return 2

    planning_script = scripts_dir / "validate_planning.py"
    if planning_script.exists():
        planning_report = build_dir / "planning_validation.json"
        planning_cmd = [
            py,
            str(planning_script),
            "--workspace",
            str(workspace),
            "--report",
            str(planning_report),
        ]
        step_started = time.perf_counter()
        planning = subprocess.run(
            planning_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _record_step_timing(
            step_timings,
            step="planning_validation",
            started=step_started,
            returncode=planning.returncode,
            command=planning_cmd,
        )
        if planning.stdout:
            print(planning.stdout, end="")
        if planning.stderr:
            print(planning.stderr, end="", file=sys.stderr)
        if planning.returncode == 2 and (args.qa or args.fail_on_planning_warnings):
            print(
                "[build_workspace] Planning validation found blocking errors. "
                "Fix content_plan.json / evidence_plan.json or run without the strict planning gate.",
                file=sys.stderr,
            )
            return 2
        if planning.returncode == 1 and args.fail_on_planning_warnings:
            print(
                "[build_workspace] Planning validation found warnings. "
                "Fix the source-planning issues above or run without --fail-on-planning-warnings.",
                file=sys.stderr,
            )
            return 1

    # Preflight: fast static outline linter. Runs before build so we can
    # catch common authoring errors in <1s instead of failing during a
    # ~60s LibreOffice render. Safe-by-default: warnings are printed but
    # the build proceeds; errors only block when --strict-preflight or
    # --qa are set (QA will fail on these downstream regardless).
    preflight_stdout_capture = None  # path used for telemetry logging
    if not args.skip_preflight:
        preflight_script = scripts_dir / "preflight.py"
        if preflight_script.exists():
            preflight_cmd = [py, str(preflight_script), "--outline", str(outline_path)]
            preflight_cmd.extend(["--asset-root", str(workspace)])
            if design_brief_path.exists():
                preflight_cmd.extend(["--design-brief", str(design_brief_path)])
            step_started = time.perf_counter()
            pf = subprocess.run(
                preflight_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            _record_step_timing(
                step_timings,
                step="preflight",
                started=step_started,
                returncode=pf.returncode,
                command=preflight_cmd,
            )
            # Surface the human-readable summary (stderr) to the user.
            if pf.stderr:
                print(pf.stderr, end="", file=sys.stderr)
            # pf.stdout is the JSON payload; keep it available for tooling.
            if pf.stdout:
                print(pf.stdout, end="")
                # Capture for skill-level telemetry aggregation.
                preflight_stdout_capture = workspace / "build" / "preflight.json"
                try:
                    preflight_stdout_capture.parent.mkdir(parents=True, exist_ok=True)
                    _write_text_if_changed(preflight_stdout_capture, pf.stdout)
                except OSError:
                    preflight_stdout_capture = None
            if pf.returncode == 3:
                print(
                    "[build_workspace] Preflight aborted: outline JSON is malformed. Fix it and retry.",
                    file=sys.stderr,
                )
                return 3
            if pf.returncode == 2:
                if args.strict_preflight or args.qa:
                    print(
                        "[build_workspace] Preflight found blocking errors. Aborting build "
                        "(run with --skip-preflight to bypass, or fix the issues above).",
                        file=sys.stderr,
                    )
                    return 2
                else:
                    print(
                        "[build_workspace] Preflight found errors; proceeding anyway (no --strict-preflight / --qa). "
                        "These will likely surface as QA failures downstream.",
                        file=sys.stderr,
                    )

    # Nudge: if asset_plan is still the init stub (has __readme__ and
    # all arrays empty) AND the outline references no staged visuals,
    # the deck will render text-only. Warn loudly — this is the #1
    # "Codex skipped visual enrichment" failure mode.
    _warn_if_stub_and_text_only(asset_plan, outline_path)

    if asset_plan.exists() and not args.skip_asset_staging:
        stage_cmd = [
            py,
            str(scripts_dir / "asset_stage.py"),
            "--manifest",
            str(asset_plan),
            "--output-dir",
            str(staged_assets_dir),
            "--attribution-csv",
            str(attribution_csv),
        ]
        if args.allow_network_assets:
            stage_cmd.append("--allow-network")
        if args.allow_generated_images:
            stage_cmd.append("--allow-generated-images")
        if args.strict_provenance:
            stage_cmd.append("--strict-provenance")
        _run_timed(stage_cmd, timings=step_timings, step="asset_staging")

    renderer_requested = args.renderer
    renderer = args.renderer
    if renderer == "auto":
        renderer = _pick_auto_renderer(outline_path)
        print(f"[build_workspace] --renderer auto picked '{renderer}'", file=sys.stderr)

    # `pptxgenjs` generates the same .pptx container format, so QA downstream
    # runs identically. If node or the module is missing we surface the error
    # rather than silently falling back to Python -- honoring the explicit
    # renderer request (per Fix 4).
    if output_pptx.exists() and args.overwrite:
        try:
            output_pptx.unlink()
        except OSError:
            pass

    if renderer == "pptxgenjs":
        js_script = scripts_dir / "build_deck_pptxgenjs.js"
        if not js_script.exists():
            raise FileNotFoundError(f"pptxgenjs renderer not found: {js_script}")
        build_cmd = [
            "node",
            str(js_script),
            "--outline",
            str(outline_path),
            "--output",
            str(output_pptx),
            "--style-preset",
            resolved_style_preset,
            "--asset-root",
            str(workspace),
        ]
        try:
            step_started = time.perf_counter()
            result = subprocess.run(
                build_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
            )
        except FileNotFoundError as exc:
            _record_step_timing(
                step_timings,
                step="render_deck",
                started=step_started,
                command=build_cmd,
                status="failed",
            )
            print(
                f"[build_workspace] pptxgenjs renderer failed: node not found on PATH ({exc})",
                file=sys.stderr,
            )
            return 1
        _record_step_timing(
            step_timings,
            step="render_deck",
            started=step_started,
            returncode=result.returncode,
            command=build_cmd,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            print(
                "[build_workspace] pptxgenjs renderer failed. "
                "Ensure node is on PATH and the 'pptxgenjs' module is installed "
                "(see scripts/build_deck_pptxgenjs.js NODE_PATH hints).",
                file=sys.stderr,
            )
            return result.returncode
        if result.stderr:
            # pptxgenjs can print benign warnings; surface them.
            print(result.stderr, end="", file=sys.stderr)
    else:
        build_cmd = [
            py,
            str(scripts_dir / "build_deck.py"),
            "--outline",
            str(outline_path),
            "--output",
            str(output_pptx),
            "--style-preset",
            resolved_style_preset,
        ]
        if build_cfg.get("font_pair"):
            build_cmd.extend(["--font-pair", str(build_cfg["font_pair"])])
        if build_cfg.get("palette_key"):
            build_cmd.extend(["--palette-key", str(build_cfg["palette_key"])])
        if args.overwrite:
            build_cmd.append("--overwrite")
        _run_timed(build_cmd, timings=step_timings, step="render_deck")

    step_returncodes: dict[str, int] = {}
    qa_returncode = 0
    failed_step = ""
    if args.qa:
        qa_cmd = [
            py,
            str(scripts_dir / "qa_gate.py"),
            "--input",
            str(output_pptx),
            "--outdir",
            str(qa_dir),
            "--style-preset",
            resolved_style_preset,
            "--strict-geometry",
            "--skip-manual-review",
            "--fail-on-visual-warnings",
            "--fail-on-design-warnings",
            "--outline",
            str(outline_path),
            "--design-brief",
            str(design_brief_path),
            "--report",
            str(qa_report),
        ]
        if args.skip_render:
            qa_cmd.append("--skip-render")
        if args.fail_on_whitespace_warnings:
            qa_cmd.append("--fail-on-whitespace-warnings")
        if args.visual_review:
            qa_cmd.append("--run-visual-review")
        if args.fail_on_visual_review_warnings:
            qa_cmd.append("--fail-on-visual-review-warnings")
        step_started = time.perf_counter()
        qa_returncode, _qa_stdout = _run_capture_echo(qa_cmd)
        _record_step_timing(
            step_timings,
            step="qa",
            started=step_started,
            returncode=qa_returncode,
            command=qa_cmd,
        )
        step_returncodes["qa"] = qa_returncode
        if qa_returncode != 0:
            failed_step = "qa"
            print(
                "[build_workspace] QA gate failed; writing build report before returning failure.",
                file=sys.stderr,
            )

    # Narration check: fail loudly when the outline references assets
    # that don't exist on disk. Catches the "Codex narrated 'adding
    # icons' but assets/icons/ was never created" failure mode.
    verify_script = scripts_dir / "verify_narration.py"
    verify_log_path = None
    if verify_script.exists():
        step_started = time.perf_counter()
        vn = subprocess.run(
            [py, str(verify_script), "--workspace", str(workspace)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _record_step_timing(
            step_timings,
            step="verify_narration",
            started=step_started,
            returncode=vn.returncode,
            command=[py, str(verify_script), "--workspace", str(workspace)],
        )
        # Echo to user-visible channels the same way the script would
        # when run standalone.
        if vn.stdout:
            print(vn.stdout, end="")
        if vn.stderr:
            print(vn.stderr, end="", file=sys.stderr)
        # Persist stderr for telemetry (that's where asset-missing lines go).
        if vn.stderr:
            verify_log_path = workspace / "build" / "verify_narration.log"
            try:
                verify_log_path.write_text(vn.stderr, encoding="utf-8")
            except OSError:
                verify_log_path = None

    # Skill-level telemetry. Non-blocking — harvests preflight + QA +
    # narration results into a JSONL log we can mine for patterns with
    # `summarize_skill_log.py`. Safe to skip on any error.
    telemetry_script = scripts_dir / "log_skill_telemetry.py"
    if telemetry_script.exists() and args.qa:
        telem_cmd = [py, str(telemetry_script), "--workspace", str(workspace)]
        if preflight_stdout_capture and preflight_stdout_capture.exists():
            telem_cmd.extend(["--preflight-json", str(preflight_stdout_capture)])
        if qa_report.exists():
            telem_cmd.extend(["--qa-report", str(qa_report)])
        if verify_log_path and verify_log_path.exists():
            telem_cmd.extend(["--verify-narration-log", str(verify_log_path)])
        subprocess.run(telem_cmd, check=False)

    if not args.skip_build_report:
        build_report_path = _workspace_path(workspace, args.build_report)
        build_report = _build_report_payload(
            workspace=workspace,
            workspace_manifest_path=workspace_manifest_path,
            manifest=manifest,
            style_contract_path=style_contract_path,
            deck_start_packet_path=deck_start_packet_path,
            intake_answers_path=intake_answers_path,
            design_contract_path=design_contract_path,
            data_analysis_handoff_path=data_analysis_handoff_path,
            outline_authoring_handoff_path=outline_authoring_handoff_path,
            outline_authoring_handoff_apply_report_path=outline_authoring_handoff_apply_report_path,
            outline_source_path=outline_source_path,
            outline_used_path=outline_path,
            design_brief_path=design_brief_path,
            content_plan_path=content_plan_path,
            evidence_plan_path=evidence_plan_path,
            asset_plan_path=asset_plan,
            build_dir=build_dir,
            output_pptx=output_pptx,
            resolved_style_preset=resolved_style_preset,
            renderer_requested=renderer_requested,
            renderer_used=renderer,
            args=args,
            research_asset_report=research_asset_report,
            scaffold_report=scaffold_report,
            artifact_manifest_path=artifact_manifest,
            artifact_selection_out=artifact_selection_out,
            artifact_apply_report=artifact_apply_report,
            planning_report=planning_report,
            preflight_report=preflight_stdout_capture,
            qa_report=qa_report,
            staged_manifest=staged_manifest,
            attribution_csv=attribution_csv,
            verify_log_path=verify_log_path,
            run_status="failed" if qa_returncode else "succeeded",
            returncode=qa_returncode,
            failed_step=failed_step,
            step_returncodes=step_returncodes,
            step_timings=step_timings,
            total_duration_ms=int(round((time.perf_counter() - workflow_started) * 1000)),
        )
        _write_json_if_changed(build_report_path, build_report)
        print(
            f"[build_workspace] build report: {_display_path(workspace, build_report_path)}",
            file=sys.stderr,
        )

    if qa_returncode != 0:
        return qa_returncode

    # After a successful build, surface the outline-critique subagent
    # prompt for any deck with >=5 content slides. Automated preflight
    # catches schema-level issues; the subagent critique catches
    # editorial ones (monotony, weak palette, text-only bias) that a
    # deterministic linter can't see. Non-blocking — just printed so the
    # agent sees it and can paste it into an Explore subagent.
    _maybe_emit_critique_prompt(
        outline_path=outline_path,
        scripts_dir=scripts_dir,
        py=py,
    )

    return 0


def _warn_if_stub_and_text_only(asset_plan_path: Path, outline_path: Path) -> None:
    """Emit a warning when the deck is about to render with no evidence anchor
    AND the asset_plan is still the init stub.

    This is the failure mode Codex falls into: it scaffolds a workspace,
    never populates asset_plan.json, and the outline has no hero/icons/
    mermaid/chart/table — so the deck renders text-only despite the skill having
    every tool needed for visual enrichment.
    """
    if not asset_plan_path.exists():
        return
    try:
        plan = json.loads(asset_plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    # Stub signature: __readme__ present, and every asset array is empty.
    is_stub = "__readme__" in plan and all(
        not plan.get(k)
        for k in ("images", "backgrounds", "charts", "tables", "generated_images", "icons")
    )
    if not is_stub:
        return

    # Inspect outline for any visual/evidence anchors.
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    slides = outline.get("slides") or []
    has_anchor = False
    for s in slides:
        if not isinstance(s, dict):
            continue
        variant = str(s.get("variant") or "").strip().lower()
        assets = s.get("assets") or {}
        if not isinstance(assets, dict):
            assets = {}
        if (
            variant in {"chart", "table", "lab-run-results", "image-sidebar", "scientific-figure", "flow"}
            or s.get("chart")
            or s.get("table")
            or s.get("tables")
            or s.get("figures")
            or assets.get("hero_image")
            or assets.get("image")
            or assets.get("generated_image")
            or assets.get("icons")
            or assets.get("mermaid_source")
            or assets.get("diagram")
            or assets.get("chart_data")
            or assets.get("chart")
            or assets.get("table_data")
            or assets.get("table")
            or assets.get("tables")
            or assets.get("figures")
        ):
            has_anchor = True
            break
    if has_anchor:
        return

    print(
        "",
        file=sys.stderr,
    )
    print(
        "[build_workspace] WARNING: asset_plan.json is still the init "
        "stub AND the outline references no visual/evidence anchors (no "
        "assets.hero_image, no assets.generated_image, no assets.icons, "
        "no assets.mermaid_source, no assets.diagram, no chart/table/figure "
        "payloads). The deck will render TEXT-ONLY.",
        file=sys.stderr,
    )
    print(
        "[build_workspace] If that's intentional (qualitative primer, "
        "no natural visual anchor), continue. Otherwise: populate "
        f"{asset_plan_path.name} with topic-specific images/icons/charts/tables, or "
        "reference assets inline via `assets.hero_image` / "
        "`assets.generated_image` / `assets.icons` / `assets.mermaid_source` "
        "/ `assets.chart_data` / `assets.table_data` on individual slides. "
        "See references/outline_schema.md #Visual Enrichment Defaults.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)


def _maybe_emit_critique_prompt(*, outline_path: Path, scripts_dir: Path, py: str) -> None:
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    slides = outline.get("slides") or []
    content_count = sum(
        1 for s in slides
        if isinstance(s, dict)
        and (s.get("type") or "content").strip().lower() == "content"
    )
    if content_count < 5:
        return

    emitter = scripts_dir / "emit_outline_critique.py"
    if not emitter.exists():
        return

    result = subprocess.run(
        [py, str(emitter), "--outline", str(outline_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        return

    # Write to stderr so pipelines that capture stdout aren't polluted.
    print("", file=sys.stderr)
    print(
        "[build_workspace] Deck has "
        f"{content_count} content slides. "
        "Editorial critique recommended — paste the prompt below into a "
        "fresh Explore subagent to catch monotony, weak palette, and "
        "missing rhythm-breakers that preflight can't see. Re-run the "
        "build after addressing the findings.",
        file=sys.stderr,
    )
    print(result.stdout, file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Error: {exc}")
        raise SystemExit(1)
