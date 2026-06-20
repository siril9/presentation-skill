#!/usr/bin/env python3
"""Fast source-only readiness report for a presentation workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from build_workspace import (
    _artifact_dependency_source_files,
    _canonical_style_preset,
    _deck_style_from_design_brief,
    _style_preset_from_design_brief,
)
from inspect_artifact_manifest import inspect_manifest

QA_WHITESPACE_WARNING_TYPES = {
    "empty_ratio_too_high",
    "content_span_too_short",
    "content_span_too_narrow",
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_if_changed(path: Path, payload: Any) -> bool:
    return _write_text_if_changed(path, json.dumps(payload, indent=2) + "\n")


def _write_text_if_changed(path: Path, text: str) -> bool:
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _workspace_path(workspace: Path, raw: str) -> Path:
    path = Path(str(raw or "")).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


def _display_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace))
    except ValueError:
        return str(path.resolve())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_json(cmd: list[str]) -> tuple[int, dict[str, Any], str]:
    result = subprocess.run(
        cmd,
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
            payload = {
                "issues": [
                    {
                        "severity": "error",
                        "message": "Validator emitted non-JSON output.",
                    }
                ],
                "error_count": 1,
                "warning_count": 0,
                "stdout_tail": result.stdout[-1200:],
            }
    return result.returncode, payload, result.stderr


def _issue_keys(issues: Any, key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    if not isinstance(issues, list):
        return values
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        text = str(issue.get(key) or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def _check_summary(payload: dict[str, Any], *, key_field: str) -> dict[str, Any]:
    issues = payload.get("issues") if isinstance(payload, dict) else []
    return {
        "error_count": int(payload.get("error_count") or 0),
        "warning_count": int(payload.get("warning_count") or 0),
        "info_count": int(payload.get("info_count") or 0),
        "issue_keys": _issue_keys(issues, key_field),
        "issues": issues if isinstance(issues, list) else [],
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compact_qa_whitespace_warnings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    warnings = payload.get("whitespace_warnings")
    if not isinstance(warnings, list):
        geometry = payload.get("geometry_violations")
        if isinstance(geometry, list):
            warnings = [
                item
                for item in geometry
                if isinstance(item, dict)
                and str(item.get("severity") or "").lower() == "warning"
                and str(item.get("type") or "") in QA_WHITESPACE_WARNING_TYPES
            ]
        else:
            warnings = []

    compact: list[dict[str, Any]] = []
    for raw in warnings:
        if not isinstance(raw, dict):
            continue
        warning_type = str(raw.get("type") or "").strip()
        if not warning_type:
            continue
        item: dict[str, Any] = {
            "type": warning_type,
            "severity": str(raw.get("severity") or "warning"),
        }
        slide_index = _safe_int(raw.get("slide_index"))
        if slide_index is not None:
            item["slide_index"] = slide_index
        for key in (
            "slide_type",
            "variant",
            "suggested_fix",
            "content_span_height_ratio",
            "content_span_width_ratio",
            "max_vertical_dead_ratio",
            "max_horizontal_dead_ratio",
            "empty_ratio",
        ):
            if key in raw:
                item[key] = raw.get(key)
        compact.append(item)
    return compact


def _compact_qa_design_warnings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues = payload.get("issues") if isinstance(payload, dict) else []
    compact: list[dict[str, Any]] = []
    if not isinstance(issues, list):
        return compact
    for raw in issues:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("severity") or "").strip().lower() != "warning":
            continue
        warning_type = str(raw.get("type") or "").strip()
        if not warning_type:
            continue
        item: dict[str, Any] = {
            "type": warning_type,
            "severity": "warning",
        }
        slide_index = _safe_int(raw.get("slide_index"))
        if slide_index is not None:
            item["slide_index"] = slide_index
        for key in (
            "shape_id",
            "shape_ids",
            "chart_part",
            "role",
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
            if key in raw:
                item[key] = raw.get(key)
        compact.append(item)
    return compact


def _compact_qa_visual_warnings(payload: Any, *, source: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        issues = payload.get("issues")
    else:
        issues = payload
    compact: list[dict[str, Any]] = []
    if not isinstance(issues, list):
        return compact
    for raw in issues:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("severity") or "").strip().lower() != "warning":
            continue
        warning_type = str(raw.get("type") or "").strip()
        if not warning_type:
            continue
        item: dict[str, Any] = {
            "type": warning_type,
            "severity": "warning",
            "source": source,
        }
        slide_number = _safe_int(raw.get("slide"))
        if slide_number is not None:
            item["slide"] = slide_number
            if slide_number > 0:
                item["slide_index"] = slide_number - 1
        for key in (
            "shape",
            "shape_id",
            "position",
            "message",
            "suggestion",
            "count",
            "variant",
            "family",
            "slides",
            "fill_pct",
            "avg_fill_pct",
            "coverage_pct",
            "gap_in",
            "font_pt",
            "estimated_lines",
        ):
            if key in raw:
                item[key] = raw.get(key)
        compact.append(item)
    return compact


def _last_build_qa_detail(workspace: Path, reports: dict[str, Any]) -> dict[str, Any]:
    qa_summary = reports.get("qa") if isinstance(reports.get("qa"), dict) else {}
    path_text = str(qa_summary.get("path") or "").strip() if isinstance(qa_summary, dict) else ""
    qa_path = _workspace_path(workspace, path_text) if path_text else None
    counts = qa_summary.get("counts") if isinstance(qa_summary, dict) else {}
    detail: dict[str, Any] = {
        "path": _display_path(workspace, qa_path) if qa_path else path_text,
        "exists": bool(qa_path and qa_path.exists()),
        "counts": counts if isinstance(counts, dict) else {},
        "whitespace_warning_count": int(
            (counts or {}).get("whitespace_warning_count") or 0
        )
        if isinstance(counts, dict)
        else 0,
        "design_warning_count": int((counts or {}).get("design_warning_count") or 0)
        if isinstance(counts, dict)
        else 0,
        "visual_warning_count": int((counts or {}).get("visual_warning_count") or 0)
        if isinstance(counts, dict)
        else 0,
        "visual_review_warning_count": int((counts or {}).get("visual_review_warning_count") or 0)
        if isinstance(counts, dict)
        else 0,
        "whitespace_warnings": [],
        "design_report": {
            "path": "",
            "exists": False,
        },
        "design_warnings": [],
        "visual_report": {
            "path": "",
            "exists": False,
        },
        "visual_review_report": {
            "path": "",
            "exists": False,
        },
        "visual_warnings": [],
    }
    payload = _load_json(qa_path, {}) if qa_path else {}
    if isinstance(payload, dict):
        warnings = _compact_qa_whitespace_warnings(payload)
        detail["whitespace_warnings"] = warnings
        detail["whitespace_warning_count"] = max(
            int(detail.get("whitespace_warning_count") or 0),
            len(warnings),
        )
        design_report_text = str(payload.get("design_report") or "").strip()
        design_report_path = _workspace_path(workspace, design_report_text) if design_report_text else None
        design_payload = _load_json(design_report_path, {}) if design_report_path else {}
        design_warnings = (
            _compact_qa_design_warnings(design_payload)
            if isinstance(design_payload, dict)
            else []
        )
        detail["design_report"] = {
            "path": _display_path(workspace, design_report_path)
            if design_report_path
            else design_report_text,
            "exists": bool(design_report_path and design_report_path.exists()),
        }
        detail["design_warnings"] = design_warnings
        detail["design_warning_count"] = max(
            int(detail.get("design_warning_count") or 0),
            len(design_warnings),
        )
        visual_report_text = str(payload.get("visual_report") or "").strip()
        visual_report_path = _workspace_path(workspace, visual_report_text) if visual_report_text else None
        visual_payload = _load_json(visual_report_path, {}) if visual_report_path else []
        visual_warnings = _compact_qa_visual_warnings(
            visual_payload,
            source="visual_qa",
        )
        detail["visual_report"] = {
            "path": _display_path(workspace, visual_report_path)
            if visual_report_path
            else visual_report_text,
            "exists": bool(visual_report_path and visual_report_path.exists()),
        }
        visual_review_report_text = str(payload.get("visual_review_report") or "").strip()
        visual_review_report_path = (
            _workspace_path(workspace, visual_review_report_text)
            if visual_review_report_text
            else None
        )
        visual_review_payload = (
            _load_json(visual_review_report_path, {}) if visual_review_report_path else {}
        )
        visual_review_warnings = _compact_qa_visual_warnings(
            visual_review_payload,
            source="visual_review",
        )
        detail["visual_review_report"] = {
            "path": _display_path(workspace, visual_review_report_path)
            if visual_review_report_path
            else visual_review_report_text,
            "exists": bool(visual_review_report_path and visual_review_report_path.exists()),
        }
        detail["visual_warnings"] = visual_warnings + visual_review_warnings
        detail["visual_warning_count"] = max(
            int(detail.get("visual_warning_count") or 0),
            len(visual_warnings),
        )
        detail["visual_review_warning_count"] = max(
            int(detail.get("visual_review_warning_count") or 0),
            len(visual_review_warnings),
        )
    return detail


def _compact_data_analysis_handoff_payload(payload: dict[str, Any]) -> dict[str, Any]:
    handoff = (
        payload.get("data_analysis_handoff")
        if isinstance(payload.get("data_analysis_handoff"), dict)
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
        if not step:
            continue
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


def _existing_build_report(
    workspace: Path,
    build_dir: Path,
    current_source_files: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = build_dir / "build_workspace_report.json"
    payload = _load_json(path, {})
    summary: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": path.exists(),
    }
    if not isinstance(payload, dict):
        return summary
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), dict) else {}
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}
    run = payload.get("run") if isinstance(payload.get("run"), dict) else {}
    qa_detail = _last_build_qa_detail(workspace, reports)
    summary.update(
        {
            "run": run,
            "run_status": run.get("status"),
            "returncode": run.get("returncode"),
            "failed_step": run.get("failed_step"),
            "style_preset": payload.get("style_preset"),
            "renderer": payload.get("renderer"),
            "source_freshness": _source_freshness(
                workspace,
                payload,
                current_source_files=current_source_files,
            ),
            "pptx_exists": (
                outputs.get("pptx", {}).get("exists")
                if isinstance(outputs.get("pptx"), dict)
                else None
            ),
            "planning_counts": (
                reports.get("planning", {}).get("counts")
                if isinstance(reports.get("planning"), dict)
                else None
            ),
            "qa_counts": (
                reports.get("qa", {}).get("counts")
                if isinstance(reports.get("qa"), dict)
                else None
            ),
            "qa": qa_detail,
            "data_analysis_handoff": _compact_data_analysis_handoff_payload(payload),
            "speed": _compact_build_speed(payload),
        }
    )
    return summary


def _source_freshness(
    workspace: Path,
    build_report: dict[str, Any],
    *,
    current_source_files: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_files = (
        build_report.get("source_files")
        if isinstance(build_report.get("source_files"), dict)
        else {}
    )
    source_files = _merge_current_source_snapshots(workspace, source_files, current_source_files)
    if not source_files:
        return {
            "checked": False,
            "count": 0,
            "stale_count": 0,
            "stale_files": [],
            "files": [],
        }

    files: list[dict[str, Any]] = []
    for name, raw_snapshot in sorted(source_files.items()):
        snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
        path_text = str(snapshot.get("path") or "").strip()
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
            "path": _display_path(workspace, current_path) if current_path else path_text,
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


def _style_mix_matrix(brief: Any) -> dict[str, Any]:
    if not isinstance(brief, dict):
        return {}
    direct = brief.get("style_mix_matrix")
    if isinstance(direct, dict):
        return direct
    style_system = brief.get("style_system")
    if isinstance(style_system, dict) and isinstance(style_system.get("style_mix_matrix"), dict):
        return style_system["style_mix_matrix"]
    return {}


def _style_seed(brief: Any, resolved_style: dict[str, Any]) -> str:
    if isinstance(resolved_style.get("style_seed"), str) and resolved_style["style_seed"].strip():
        return resolved_style["style_seed"].strip()
    if isinstance(brief, dict):
        style_system = brief.get("style_system")
        if isinstance(style_system, dict):
            value = style_system.get("style_seed")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _pool_summary(mix: dict[str, Any]) -> dict[str, Any]:
    pools: dict[str, Any] = {}
    multi_entry_count = 0
    for key in sorted(k for k in mix if str(k).endswith("_pool")):
        value = mix.get(key)
        entries = [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
        unique_entries: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            normalized = entry.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_entries.append(entry)
        if len(unique_entries) >= 2:
            multi_entry_count += 1
        pools[key] = {
            "count": len(entries),
            "unique_count": len(unique_entries),
            "values": unique_entries,
        }
    return {
        "pool_count": len(pools),
        "multi_entry_pool_count": multi_entry_count,
        "pools": pools,
    }


def _style_preview(
    *,
    workspace: Path,
    style_contract_path: Path,
    design_brief_path: Path,
    outline_path: Path,
) -> dict[str, Any]:
    preview: dict[str, Any] = {
        "style_contract": _display_path(workspace, style_contract_path),
        "design_brief": _display_path(workspace, design_brief_path),
        "outline": _display_path(workspace, outline_path),
    }
    contract = _load_json(style_contract_path, {})
    build_cfg = contract.get("build", {}) if isinstance(contract, dict) else {}
    fallback_raw = str(build_cfg.get("style_preset") or "executive-clinical").strip() or "executive-clinical"
    try:
        fallback_preset = _canonical_style_preset(fallback_raw, source="style_contract")
    except ValueError as exc:
        preview["error"] = str(exc)
        fallback_preset = fallback_raw
    preview["fallback_style_preset"] = fallback_preset

    brief = _load_json(design_brief_path, {})
    outline = _load_json(outline_path, {})
    design_preset = ""
    if isinstance(brief, dict):
        try:
            design_preset = _style_preset_from_design_brief(brief)
        except ValueError as exc:
            preview["error"] = str(exc)
    preview["design_brief_style_preset"] = design_preset
    preview["resolved_style_preset"] = design_preset or fallback_preset

    brief_style: dict[str, Any] = {}
    if isinstance(brief, dict):
        try:
            brief_style = _deck_style_from_design_brief(brief)
        except ValueError as exc:
            preview["error"] = str(exc)
            brief_style = {}
    outline_style = outline.get("deck_style") if isinstance(outline, dict) and isinstance(outline.get("deck_style"), dict) else {}
    resolved_style = {**brief_style, **outline_style}
    mix = _style_mix_matrix(brief)
    resolved_outline = _load_json(workspace / "build" / "outline_resolved.json", {})
    resolved_treatment_summary = (
        resolved_outline.get("resolved_treatment_summary")
        if isinstance(resolved_outline, dict)
        and isinstance(resolved_outline.get("resolved_treatment_summary"), dict)
        else {}
    )
    preview.update(
        {
            "style_seed": _style_seed(brief, resolved_style),
            "design_deck_style": brief_style,
            "outline_deck_style_overrides": outline_style,
            "resolved_deck_style": resolved_style,
            "style_mix_matrix": _pool_summary(mix),
            "resolved_treatment_summary": resolved_treatment_summary,
        }
    )
    return preview


def _artifact_manifest_summary(workspace: Path, path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": path.exists(),
        "valid": False,
        "output_count": 0,
        "output_ids": [],
        "aliases": [],
    }
    if not path.exists():
        return summary
    try:
        inspected = inspect_manifest(workspace, path)
    except Exception as exc:
        summary["error"] = str(exc)
        return summary
    alias_plan = inspected.get("alias_plan")
    aliases: list[dict[str, Any]] = []
    output_ids: list[str] = []
    figure_quality_counts: dict[str, int] = {}
    if isinstance(alias_plan, list):
        for item in alias_plan:
            if not isinstance(item, dict):
                continue
            output_id = str(item.get("id") or "").strip()
            if output_id:
                output_ids.append(output_id)
            figure_quality = item.get("figure_quality") if isinstance(item.get("figure_quality"), dict) else {}
            quality_status = str(figure_quality.get("status") or "unknown").strip() or "unknown"
            figure_quality_counts[quality_status] = figure_quality_counts.get(quality_status, 0) + 1
            aliases.append(
                {
                    "id": output_id,
                    "title": str(item.get("title") or ""),
                    "image_alias": str(item.get("image_alias") or ""),
                    "chart_alias": str(item.get("chart_alias") or ""),
                    "table_alias": str(item.get("table_alias") or ""),
                    "source_path": str(item.get("source_path") or ""),
                    "figure_quality": figure_quality,
                }
            )
    summary.update(
        {
            "valid": True,
            "manifest_version": inspected.get("manifest_version"),
            "generated_by": inspected.get("generated_by"),
            "data_specs_sha256": inspected.get("data_specs_sha256"),
            "analysis_summary": inspected.get("analysis_summary"),
            "analysis_summary_markdown": inspected.get("analysis_summary_markdown"),
            "rebuild_context": inspected.get("rebuild_context")
            if isinstance(inspected.get("rebuild_context"), dict)
            else {},
            "output_count": int(inspected.get("output_count") or len(output_ids)),
            "output_ids": output_ids,
            "aliases": aliases,
            "figure_quality_counts": figure_quality_counts,
            "commands": inspected.get("commands") if isinstance(inspected.get("commands"), dict) else {},
            "selection_template_count": len(inspected.get("selection_templates") or [])
            if isinstance(inspected.get("selection_templates"), list)
            else 0,
        }
    )
    return summary


def _artifact_selection_summary(
    workspace: Path,
    path: Path,
    *,
    output_ids: list[str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": path.exists(),
        "binding_count": 0,
        "bound_output_ids": [],
        "unbound_output_ids": output_ids,
        "slide_ids": [],
        "variants": [],
    }
    if not path.exists():
        return summary
    payload = _load_json(path, {})
    bindings = payload.get("bindings") if isinstance(payload, dict) else None
    if not isinstance(bindings, list):
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


def _artifact_context_summary(
    *,
    artifact_manifest_summary: dict[str, Any],
    artifact_selection_summary: dict[str, Any],
    tabular_data: list[str],
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    manifest = artifact_manifest_summary if isinstance(artifact_manifest_summary, dict) else {}
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
    selection = artifact_selection_summary if isinstance(artifact_selection_summary, dict) else {}
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
    tabular_paths = _string_list(tabular_data)
    if tabular_paths:
        context["tabular_data"] = tabular_paths
    return context


def _generated_artifact_paths(workspace: Path) -> set[Path]:
    manifest = _load_json(workspace / "assets" / "artifacts_manifest.json", {})
    paths: set[Path] = {
        (workspace / "assets" / "artifacts_manifest.json").resolve(),
        (workspace / "assets" / "analysis_summary.json").resolve(),
        (workspace / "assets" / "analysis_summary.md").resolve(),
    }
    if not isinstance(manifest, dict):
        return paths
    for key in ("analysis_summary", "analysis_summary_markdown"):
        raw = str(manifest.get(key) or "").strip()
        if raw:
            paths.add(_workspace_path(workspace, raw))
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        return paths
    for output in outputs:
        if not isinstance(output, dict):
            continue
        artifacts = output.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            raw = str(artifact.get("path") or "").strip()
            if raw:
                paths.add(_workspace_path(workspace, raw))
    return paths


def _tabular_data_paths(workspace: Path) -> list[str]:
    roots = [workspace / "data", workspace / "assets" / "data", workspace / "assets" / "tables"]
    suffixes = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".jsonl", ".parquet", ".feather"}
    generated_paths = _generated_artifact_paths(workspace)
    staged_root = (workspace / "assets" / "staged").resolve()
    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.suffix.lower() not in suffixes:
                continue
            resolved = path.resolve()
            if resolved in generated_paths or staged_root in resolved.parents:
                continue
            rel = _display_path(workspace, path)
            if rel in seen:
                continue
            seen.add(rel)
            found.append(rel)
    return found


def _file_snapshot(workspace: Path, path: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": path.exists(),
    }
    if path.exists() and path.is_file():
        try:
            snapshot["sha256"] = _file_sha256(path)
            snapshot["size_bytes"] = path.stat().st_size
        except OSError as exc:
            snapshot["read_error"] = str(exc)
    return snapshot


def _pptx_reference_candidates(workspace: Path, *, build_dir: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(workspace.rglob("*.pptx"), key=lambda item: str(item)):
        try:
            path.relative_to(build_dir)
            continue
        except ValueError:
            pass
        rel = _display_path(workspace, path)
        if rel in seen:
            continue
        seen.add(rel)
        candidates.append(_file_snapshot(workspace, path))
    return candidates


def _style_report_current(
    *,
    workspace: Path,
    report: Any,
    reference_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {
            "checked": False,
            "current": False,
            "matched_inputs": [],
            "stale_inputs": [],
            "missing_inputs": [],
        }
    inputs = report.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {
            "checked": False,
            "current": False,
            "matched_inputs": [],
            "stale_inputs": [],
            "missing_inputs": [],
        }
    current_by_path: dict[str, dict[str, Any]] = {}
    for item in reference_candidates:
        if not isinstance(item, dict):
            continue
        path_text = str(item.get("path") or "").strip()
        if not path_text:
            continue
        current_by_path[path_text] = item
        current_by_path[str((workspace / path_text).resolve())] = item

    matched: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    for raw in inputs:
        if not isinstance(raw, dict):
            continue
        raw_path = str(raw.get("path") or "").strip()
        expected_sha = str(raw.get("sha256") or "").strip()
        current = current_by_path.get(raw_path)
        if current is None:
            path = Path(raw_path).expanduser()
            if not path.is_absolute():
                path = workspace / path
            display = _display_path(workspace, path)
            current = _file_snapshot(workspace, path)
            current_by_path[raw_path] = current
            current_by_path[display] = current
        display_path = str(current.get("path") or raw_path)
        if not current.get("exists"):
            missing.append(display_path)
            continue
        current_sha = str(current.get("sha256") or "").strip()
        if expected_sha and current_sha and expected_sha != current_sha:
            stale.append(display_path)
        else:
            matched.append(display_path)
    checked = bool(matched or stale or missing)
    return {
        "checked": checked,
        "current": checked and not stale and not missing,
        "matched_inputs": matched,
        "stale_inputs": stale,
        "missing_inputs": missing,
    }


def _pptx_style_summary(
    *,
    workspace: Path,
    build_dir: Path,
    design_brief_path: Path,
) -> dict[str, Any]:
    report_path = workspace / "style_extract_report.json"
    fragment_path = workspace / "style_extract_design_brief.json"
    apply_report_path = workspace / "style_fragment_apply_report.json"
    report_payload = _load_json(report_path, {})
    fragment_payload = _load_json(fragment_path, {})
    apply_payload = _load_json(apply_report_path, {})
    design = _load_json(design_brief_path, {})
    style_import = design.get("style_import") if isinstance(design, dict) and isinstance(design.get("style_import"), dict) else {}
    references = _pptx_reference_candidates(workspace, build_dir=build_dir)
    report_current = _style_report_current(
        workspace=workspace,
        report=report_payload,
        reference_candidates=references,
    )
    fragment_snapshot = _file_snapshot(workspace, fragment_path)
    report_snapshot = _file_snapshot(workspace, report_path)
    apply_snapshot = _file_snapshot(workspace, apply_report_path)
    import_fragment = style_import.get("fragment") if isinstance(style_import, dict) and isinstance(style_import.get("fragment"), dict) else {}
    applied_by = str(style_import.get("applied_by") or "") if isinstance(style_import, dict) else ""
    imported_fragment_sha = str(import_fragment.get("sha256") or "").strip()
    current_fragment_sha = str(fragment_snapshot.get("sha256") or "").strip()

    applied = (
        applied_by == "scripts/apply_pptx_style_fragment.py"
        and bool(current_fragment_sha)
        and imported_fragment_sha == current_fragment_sha
    )
    stale_apply = bool(current_fragment_sha and imported_fragment_sha and imported_fragment_sha != current_fragment_sha)
    if not references and not report_path.exists() and not fragment_path.exists() and not style_import:
        status = "none"
    elif references and not report_path.exists() and not fragment_path.exists():
        status = "reference_pptx_unextracted"
    elif report_path.exists() and not bool(report_current.get("current")) and report_current.get("checked"):
        status = "style_extract_stale"
    elif fragment_path.exists() and not style_import:
        status = "fragment_not_applied"
    elif fragment_path.exists() and stale_apply:
        status = "fragment_changed_since_apply"
    elif report_path.exists() and not fragment_path.exists() and not style_import:
        status = "report_not_applied"
    elif applied:
        status = "applied"
    elif style_import and not fragment_path.exists():
        status = "applied_without_local_fragment"
    else:
        status = "needs_review"

    return {
        "status": status,
        "reference_pptx_candidates": references,
        "report": report_snapshot,
        "fragment": fragment_snapshot,
        "apply_report": apply_snapshot,
        "report_current": report_current,
        "applied": applied,
        "stale_apply": stale_apply,
        "style_import": {
            "exists": bool(style_import),
            "applied_by": applied_by,
            "mode": style_import.get("mode") if isinstance(style_import, dict) else "",
            "style_seed": style_import.get("style_seed") if isinstance(style_import, dict) else "",
            "style_preset": style_import.get("style_preset") if isinstance(style_import, dict) else "",
            "fragment_sha256": imported_fragment_sha,
        },
        "report_deck_count": (
            report_payload.get("aggregate", {}).get("deck_count")
            if isinstance(report_payload.get("aggregate"), dict)
            else 0
        ) if isinstance(report_payload, dict) else 0,
        "report_slide_count": (
            report_payload.get("aggregate", {}).get("slide_count")
            if isinstance(report_payload.get("aggregate"), dict)
            else 0
        ) if isinstance(report_payload, dict) else 0,
    }


def _load_json_with_error(path: Path) -> tuple[Any, str]:
    if not path.exists():
        return None, ""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def _string_list(value: Any) -> list[str]:
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


def _contract_acceptance_evidence(
    workspace: Path,
    design: dict[str, Any],
) -> dict[str, Any]:
    qa_contract = (
        design.get("qa_contract")
        if isinstance(design.get("qa_contract"), dict)
        else {}
    )
    items: list[str] = []
    seen: set[str] = set()
    for value in (
        design.get("acceptance_evidence"),
        qa_contract.get("acceptance_evidence") if isinstance(qa_contract, dict) else None,
        qa_contract.get("evidence_files") if isinstance(qa_contract, dict) else None,
        qa_contract.get("verification_evidence") if isinstance(qa_contract, dict) else None,
    ):
        for item in _string_list(value):
            if item in seen:
                continue
            seen.add(item)
            items.append(item)
    files: list[dict[str, Any]] = []
    for item in items:
        path_text = _contract_evidence_path(item)
        if not path_text:
            continue
        files.append(_file_snapshot(workspace, _workspace_path(workspace, path_text)))
    missing_files = [
        str(item.get("path") or "")
        for item in files
        if isinstance(item, dict) and not item.get("exists")
    ]
    return {
        "items": items,
        "item_count": len(items),
        "files": files,
        "file_count": len(files),
        "existing_file_count": len([item for item in files if item.get("exists")]),
        "missing_files": missing_files,
    }


def _contract_execution_plan_summary(design: dict[str, Any]) -> dict[str, Any]:
    plan = (
        design.get("agent_execution_plan")
        if isinstance(design.get("agent_execution_plan"), dict)
        else {}
    )
    phases = (plan.get("phases") or plan.get("steps")) if isinstance(plan, dict) else []
    phase_ids: list[str] = []
    if isinstance(phases, list):
        for item in phases:
            if isinstance(item, dict):
                phase_id = str(item.get("id") or item.get("phase") or item.get("name") or "").strip()
            else:
                phase_id = str(item or "").strip()
            if phase_id:
                phase_ids.append(phase_id)
    commands = _string_list(plan.get("commands")) if isinstance(plan, dict) else []
    return {
        "exists": bool(plan),
        "phase_count": len(phase_ids),
        "phase_ids": phase_ids,
        "command_count": len(commands),
        "commands": commands,
    }


def _phase_proof_default() -> dict[str, Any]:
    return {
        "exists": False,
        "valid": False,
        "ledger_version": "",
        "plan_version": "",
        "phase_count": 0,
        "phase_ids": [],
        "route_required_phase_ids": [],
        "status_sources": [],
        "acceptance_gate_ids": [],
        "acceptance_gate_count": 0,
        "phase_acceptance_gate_ids": {},
        "phase_proof_counts": {},
        "phase_proof_files": {},
        "proof_paths": [],
        "proof_path_count": 0,
        "proof_files": [],
        "proof_file_count": 0,
        "existing_file_count": 0,
        "missing_file_count": 0,
        "missing_files": [],
        "phase_count_matches_execution_plan": False,
    }


def _phase_proof_file_summary(
    workspace: Path,
    proofs: list[str],
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for proof in proofs:
        path_text = _contract_evidence_path(proof)
        if not path_text or path_text in seen:
            continue
        seen.add(path_text)
        files.append(_file_snapshot(workspace, _workspace_path(workspace, path_text)))
    missing_files = [
        str(item.get("path") or "")
        for item in files
        if isinstance(item, dict) and not item.get("exists")
    ]
    return {
        "proof_files": files,
        "proof_file_count": len(files),
        "existing_file_count": len([item for item in files if item.get("exists")]),
        "missing_file_count": len(missing_files),
        "missing_files": missing_files,
    }


def _phase_proof_ledger_summary(
    *,
    workspace: Path,
    packet_payload: Any,
    execution_plan: dict[str, Any],
) -> dict[str, Any]:
    ledger = (
        packet_payload.get("phase_proof_ledger")
        if isinstance(packet_payload, dict) and isinstance(packet_payload.get("phase_proof_ledger"), dict)
        else {}
    )
    if not ledger:
        return _phase_proof_default()

    phases = ledger.get("phases") if isinstance(ledger.get("phases"), list) else []
    phase_ids = _string_list(ledger.get("phase_ids"))
    if not phase_ids:
        phase_ids = [
            str(item.get("id") or "").strip()
            for item in phases
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]

    phase_acceptance_gate_ids: dict[str, list[str]] = {}
    phase_proof_counts: dict[str, int] = {}
    phase_proof_files: dict[str, dict[str, Any]] = {}
    gate_ids: list[str] = []
    proof_paths: list[str] = []
    seen_gates: set[str] = set()
    seen_proofs: set[str] = set()
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_id = str(phase.get("id") or "").strip()
        if not phase_id:
            continue
        gates = _string_list(phase.get("acceptance_gate_ids"))
        proofs = _string_list(phase.get("proof"))
        phase_acceptance_gate_ids[phase_id] = gates
        phase_proof_counts[phase_id] = len(proofs)
        phase_proof_files[phase_id] = _phase_proof_file_summary(workspace, proofs)
        for gate_id in gates:
            if gate_id in seen_gates:
                continue
            seen_gates.add(gate_id)
            gate_ids.append(gate_id)
        for proof in proofs:
            if proof in seen_proofs:
                continue
            seen_proofs.add(proof)
            proof_paths.append(proof)

    execution_phase_ids = _string_list(execution_plan.get("phase_ids"))
    all_file_summary = _phase_proof_file_summary(workspace, proof_paths)
    return {
        "exists": True,
        "valid": str(ledger.get("ledger_version") or "").strip() == "deck_phase_proof_ledger_v1",
        "ledger_version": str(ledger.get("ledger_version") or "").strip(),
        "plan_version": str(ledger.get("plan_version") or "").strip(),
        "phase_count": int(ledger.get("phase_count") or len(phase_ids)),
        "phase_ids": phase_ids,
        "route_required_phase_ids": _string_list(ledger.get("route_required_phase_ids")),
        "status_sources": _string_list(ledger.get("status_sources")),
        "acceptance_gate_ids": gate_ids,
        "acceptance_gate_count": len(gate_ids),
        "phase_acceptance_gate_ids": phase_acceptance_gate_ids,
        "phase_proof_counts": phase_proof_counts,
        "phase_proof_files": phase_proof_files,
        "proof_paths": proof_paths,
        "proof_path_count": len(proof_paths),
        **all_file_summary,
        "phase_count_matches_execution_plan": bool(execution_phase_ids and execution_phase_ids == phase_ids),
    }


def _deck_intake_answers_file(
    workspace: Path,
    packet_payload: Any,
    apply_payload: Any,
) -> Path:
    raw = ""
    if isinstance(apply_payload, dict):
        raw = str(apply_payload.get("answers_path") or "").strip()
    if not raw and isinstance(packet_payload, dict):
        after_answers = packet_payload.get("after_answers")
        if isinstance(after_answers, dict):
            raw = str(after_answers.get("answer_file") or "").strip()
    if not raw:
        raw = "intake_answers.json"
    return _workspace_path(workspace, raw)


def _source_inventory_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "exists": False,
            "data_file_count": 0,
            "data_file_shown_count": 0,
            "reference_pptx_count": 0,
            "reference_pptx_shown_count": 0,
            "artifact_ledger_count": 0,
            "data_paths": [],
            "reference_pptx_paths": [],
            "artifact_ledger_paths": [],
        }

    def paths(key: str) -> list[str]:
        items = value.get(key)
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path:
                out.append(path)
        return out

    return {
        "exists": bool(value),
        "data_file_count": int(value.get("data_file_count") or 0),
        "data_file_shown_count": int(value.get("data_file_shown_count") or 0),
        "reference_pptx_count": int(value.get("reference_pptx_count") or 0),
        "reference_pptx_shown_count": int(value.get("reference_pptx_shown_count") or 0),
        "artifact_ledger_count": int(value.get("artifact_ledger_count") or 0),
        "data_paths": paths("data_files"),
        "reference_pptx_paths": paths("reference_pptx_files"),
        "artifact_ledger_paths": paths("artifact_ledger_files"),
    }


def _deck_intake_summary(
    *,
    workspace: Path,
    design_brief_path: Path,
) -> dict[str, Any]:
    packet_path = workspace / "deck_start_packet.json"
    apply_report_path = workspace / "intake_apply_report.json"
    packet_payload, packet_error = _load_json_with_error(packet_path)
    apply_payload, apply_error = _load_json_with_error(apply_report_path)
    answers_path = _deck_intake_answers_file(workspace, packet_payload, apply_payload)
    answers_payload, answers_error = _load_json_with_error(answers_path)

    packet_snapshot = _file_snapshot(workspace, packet_path)
    answers_snapshot = _file_snapshot(workspace, answers_path)
    apply_snapshot = _file_snapshot(workspace, apply_report_path)
    design = _load_json(design_brief_path, {})
    user_intake = (
        design.get("user_intake")
        if isinstance(design, dict) and isinstance(design.get("user_intake"), dict)
        else {}
    )
    choice_resolution_seed = (
        design.get("choice_resolution_seed")
        if isinstance(design, dict) and isinstance(design.get("choice_resolution_seed"), dict)
        else {}
    )
    packet_source_inventory = _source_inventory_summary(
        packet_payload.get("workspace_source_inventory")
        if isinstance(packet_payload, dict)
        else {}
    )
    seed_source_inventory = _source_inventory_summary(
        choice_resolution_seed.get("workspace_source_inventory")
        if isinstance(choice_resolution_seed, dict)
        else {}
    )
    current_answers_sha = str(answers_snapshot.get("sha256") or "").strip()
    current_packet_sha = str(packet_snapshot.get("sha256") or "").strip()
    applied_answers_sha = str(apply_payload.get("answers_sha256") or "").strip() if isinstance(apply_payload, dict) else ""
    applied_packet_sha = str(apply_payload.get("packet_sha256") or "").strip() if isinstance(apply_payload, dict) else ""
    workflow = str(apply_payload.get("workflow") or "").strip() if isinstance(apply_payload, dict) else ""
    dry_run = bool(apply_payload.get("dry_run")) if isinstance(apply_payload, dict) else False
    valid_packet = (
        isinstance(packet_payload, dict)
        and str(packet_payload.get("workflow") or "").strip() == "deck_start_packet_v1"
    )
    applied = bool(
        user_intake
        and answers_path.exists()
        and workflow == "deck_intake_answers_apply_v1"
        and applied_answers_sha
        and current_answers_sha == applied_answers_sha
        and (not current_packet_sha or not applied_packet_sha or current_packet_sha == applied_packet_sha)
        and not dry_run
    )
    stale_apply = bool(
        answers_path.exists()
        and applied_answers_sha
        and current_answers_sha
        and current_answers_sha != applied_answers_sha
    ) or bool(
        packet_path.exists()
        and applied_packet_sha
        and current_packet_sha
        and current_packet_sha != applied_packet_sha
    )

    if not packet_path.exists() and not answers_path.exists() and not user_intake:
        status = "none"
    elif packet_path.exists() and packet_error:
        status = "deck_start_packet_invalid_json"
    elif packet_path.exists() and not valid_packet:
        status = "deck_start_packet_invalid"
    elif answers_path.exists() and answers_error:
        status = "intake_answers_invalid_json"
    elif apply_report_path.exists() and apply_error:
        status = "intake_apply_report_invalid_json"
    elif packet_path.exists() and not answers_path.exists() and not user_intake:
        status = "intake_answers_missing"
    elif answers_path.exists() and not user_intake:
        status = "intake_answers_not_applied"
    elif answers_path.exists() and dry_run:
        status = "intake_apply_dry_run_only"
    elif answers_path.exists() and user_intake and not apply_payload:
        status = "intake_apply_unstamped"
    elif stale_apply:
        status = "intake_answers_changed_since_apply"
    elif applied:
        status = "applied"
    elif user_intake and not answers_path.exists():
        status = "applied_without_local_answers"
    elif user_intake:
        status = "applied_without_report"
    else:
        status = "needs_review"

    answer_template = {}
    intake_questions: list[dict[str, Any]] = []
    design_contract_prompt_command = ""
    packet_route_ledger: dict[str, Any] = {}
    execution_plan: dict[str, Any] = {
        "valid": False,
        "plan_version": "",
        "phase_count": 0,
        "phase_ids": [],
    }
    phase_proof_ledger: dict[str, Any] = _phase_proof_default()
    if isinstance(packet_payload, dict):
        after_answers = packet_payload.get("after_answers")
        if isinstance(after_answers, dict) and isinstance(after_answers.get("answer_file_template"), dict):
            answer_template = after_answers["answer_file_template"]
        request_user_input = packet_payload.get("request_user_input")
        questions = (
            request_user_input.get("questions")
            if isinstance(request_user_input, dict)
            else []
        )
        if isinstance(questions, list):
            intake_questions = [item for item in questions if isinstance(item, dict)]
        route_ledger = packet_payload.get("route_decision_ledger")
        if isinstance(route_ledger, dict):
            routes = route_ledger.get("routes") if isinstance(route_ledger.get("routes"), list) else []
            route_status = {
                str(item.get("id") or "").strip(): bool(item.get("active"))
                for item in routes
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            }
            packet_route_ledger = {
                "ledger_version": str(route_ledger.get("ledger_version") or ""),
                "route_status": route_status,
                "active_routes": sorted(
                    route_id for route_id, active in route_status.items() if active
                ),
            }
        after_answers = packet_payload.get("after_answers")
        scouts = (
            after_answers.get("optional_scouts")
            if isinstance(after_answers, dict)
            and isinstance(after_answers.get("optional_scouts"), list)
            else []
        )
        for item in scouts:
            if (
                isinstance(item, dict)
                and str(item.get("name") or "").strip() == "design_contract_scout"
            ):
                design_contract_prompt_command = str(item.get("command") or "").strip()
                break
        raw_execution_plan = packet_payload.get("execution_plan")
        if isinstance(raw_execution_plan, dict):
            phases = raw_execution_plan.get("phases")
            phase_ids = [
                str(item.get("id") or "").strip()
                for item in phases
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            ] if isinstance(phases, list) else []
            execution_plan = {
                "valid": str(raw_execution_plan.get("plan_version") or "").strip()
                == "deck_execution_plan_v1",
                "plan_version": str(raw_execution_plan.get("plan_version") or "").strip(),
                "phase_count": len(phase_ids),
                "phase_ids": phase_ids,
                "ordering_rule": str(raw_execution_plan.get("ordering_rule") or "").strip(),
            }
        phase_proof_ledger = _phase_proof_ledger_summary(
            workspace=workspace,
            packet_payload=packet_payload,
            execution_plan=execution_plan,
        )

    seed_choices = (
        choice_resolution_seed.get(
            "resolved_choices",
            choice_resolution_seed.get("choice_ledger"),
        )
        if isinstance(choice_resolution_seed, dict)
        else []
    ) or []
    seed_choice_ids = [
        str(item.get("id") or "").strip()
        for item in seed_choices
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    seed_routes = (
        choice_resolution_seed.get("route_decisions")
        if isinstance(choice_resolution_seed, dict)
        and isinstance(choice_resolution_seed.get("route_decisions"), list)
        else []
    )
    seed_route_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in seed_routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    seed_active_routes = sorted(
        route_id for route_id, active in seed_route_status.items() if active
    )
    seed_route_ledger = (
        choice_resolution_seed.get("route_decision_ledger")
        if isinstance(choice_resolution_seed, dict)
        and isinstance(choice_resolution_seed.get("route_decision_ledger"), dict)
        else {}
    )
    seed_route_ledger_routes = (
        seed_route_ledger.get("routes")
        if isinstance(seed_route_ledger.get("routes"), list)
        else []
    )
    seed_route_ledger_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in seed_route_ledger_routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    seed_route_ledger_active_routes = sorted(
        route_id for route_id, active in seed_route_ledger_status.items() if active
    )

    answer_count = 0
    if isinstance(answers_payload, dict):
        answers = answers_payload.get("answers")
        if isinstance(answers, list):
            answer_count = len([item for item in answers if isinstance(item, dict)])
        else:
            answer_count = len(
                [
                    key
                    for key, value in answers_payload.items()
                    if key != "answered_by" and value not in (None, "", [], {})
                ]
            )

    return {
        "status": status,
        "packet": packet_snapshot,
        "answers": answers_snapshot,
        "apply_report": apply_snapshot,
        "valid_packet": valid_packet,
        "applied": applied,
        "stale_apply": stale_apply,
        "error": packet_error or answers_error,
        "apply_error": apply_error,
        "answer_count": answer_count,
        "answer_template": answer_template,
        "questions": intake_questions,
        "design_contract_prompt_command": design_contract_prompt_command,
        "execution_plan": execution_plan,
        "phase_proof_ledger": phase_proof_ledger,
        "route_decision_ledger": packet_route_ledger,
        "route_ledger_version": packet_route_ledger.get("ledger_version", ""),
        "route_ledger_status": packet_route_ledger.get("route_status", {}),
        "route_ledger_active_routes": packet_route_ledger.get("active_routes", []),
        "workspace_source_inventory": {
            "packet": packet_source_inventory,
            "choice_resolution_seed": seed_source_inventory,
        },
        "choice_resolution_seed": {
            "exists": bool(choice_resolution_seed),
            "contract_version": str(choice_resolution_seed.get("contract_version") or "")
            if isinstance(choice_resolution_seed, dict)
            else "",
            "stable_prompt_id": str(choice_resolution_seed.get("stable_prompt_id") or "")
            if isinstance(choice_resolution_seed, dict)
            else "",
            "choice_ids": seed_choice_ids,
            "choice_count": len(seed_choice_ids),
            "route_status": seed_route_status,
            "active_routes": seed_active_routes,
            "route_ledger_version": str(seed_route_ledger.get("ledger_version") or "")
            if seed_route_ledger
            else "",
            "route_ledger_status": seed_route_ledger_status,
            "route_ledger_active_routes": seed_route_ledger_active_routes,
            "source_inventory": seed_source_inventory,
        },
        "answered_by": str(user_intake.get("answered_by") or "") if isinstance(user_intake, dict) else "",
        "stable_prompt_id": str(user_intake.get("stable_prompt_id") or "") if isinstance(user_intake, dict) else "",
        "unanswered": user_intake.get("unanswered", []) if isinstance(user_intake, dict) else [],
        "user_intake_exists": bool(user_intake),
        "applied_metadata": {
            "workflow": workflow,
            "answers_sha256": applied_answers_sha,
            "packet_sha256": applied_packet_sha,
            "dry_run": dry_run,
        },
    }


def _design_contract_summary(
    *,
    workspace: Path,
    design_brief_path: Path,
) -> dict[str, Any]:
    contract_path = workspace / "design_contract.json"
    apply_report_path = workspace / "design_contract_apply_report.json"
    contract_snapshot = _file_snapshot(workspace, contract_path)
    apply_report_snapshot = _file_snapshot(workspace, apply_report_path)
    design = _load_json(design_brief_path, {})
    applied_meta = (
        design.get("design_contract")
        if isinstance(design, dict) and isinstance(design.get("design_contract"), dict)
        else {}
    )
    contract_payload, contract_error = _load_json_with_error(contract_path)
    current_sha = str(contract_snapshot.get("sha256") or "").strip()
    applied_sha = str(applied_meta.get("contract_sha256") or "").strip() if isinstance(applied_meta, dict) else ""
    current_seed = (
        str(contract_payload.get("stable_prompt_id") or "").strip()
        if isinstance(contract_payload, dict)
        else ""
    )
    applied_seed = str(applied_meta.get("stable_prompt_id") or "").strip() if isinstance(applied_meta, dict) else ""
    applied_by = str(applied_meta.get("applied_by") or "").strip() if isinstance(applied_meta, dict) else ""
    valid_contract = (
        isinstance(contract_payload, dict)
        and str(contract_payload.get("contract_version") or "").strip() == "deck_design_contract_v1"
    )
    qa_contract = (
        design.get("qa_contract")
        if isinstance(design, dict) and isinstance(design.get("qa_contract"), dict)
        else {}
    )
    slide_quality_contract = (
        design.get("slide_quality_contract")
        if isinstance(design, dict) and isinstance(design.get("slide_quality_contract"), dict)
        else {}
    )
    subagent_handoff = (
        design.get("subagent_handoff")
        if isinstance(design, dict) and isinstance(design.get("subagent_handoff"), dict)
        else {}
    )
    required_checks = _string_list(
        qa_contract.get("required_checks") or qa_contract.get("must_run")
    )
    fail_on = _string_list(qa_contract.get("fail_on"))
    visual_risks = _string_list(qa_contract.get("visual_risks_to_check"))
    quality_readability = (
        slide_quality_contract.get("readability_targets")
        if isinstance(slide_quality_contract.get("readability_targets"), dict)
        else {}
    )
    quality_layout = (
        slide_quality_contract.get("layout_targets")
        if isinstance(slide_quality_contract.get("layout_targets"), dict)
        else {}
    )
    quality_artifacts = (
        slide_quality_contract.get("artifact_quality_targets")
        if isinstance(slide_quality_contract.get("artifact_quality_targets"), dict)
        else {}
    )
    quality_qa = (
        slide_quality_contract.get("qa_gates")
        if isinstance(slide_quality_contract.get("qa_gates"), dict)
        else {}
    )
    quality_fail_on = _string_list(quality_qa.get("fail_on"))
    quality_commands = _string_list(quality_qa.get("required_commands"))
    quality_must_record = _string_list(quality_artifacts.get("must_record"))
    acceptance_evidence = (
        _contract_acceptance_evidence(workspace, design)
        if isinstance(design, dict)
        else {
            "items": [],
            "item_count": 0,
            "files": [],
            "file_count": 0,
            "existing_file_count": 0,
            "missing_files": [],
        }
    )
    agent_execution_plan = (
        _contract_execution_plan_summary(design)
        if isinstance(design, dict)
        else {
            "exists": False,
            "phase_count": 0,
            "phase_ids": [],
            "command_count": 0,
            "commands": [],
        }
    )
    reproducibility_contract = (
        design.get("reproducibility_contract")
        if isinstance(design, dict) and isinstance(design.get("reproducibility_contract"), dict)
        else {}
    )
    style_replay = (
        reproducibility_contract.get("style_replay")
        if isinstance(reproducibility_contract.get("style_replay"), dict)
        else {}
    )
    structure_replay = (
        reproducibility_contract.get("structure_replay")
        if isinstance(reproducibility_contract.get("structure_replay"), dict)
        else {}
    )
    artifact_replay = (
        reproducibility_contract.get("artifact_replay")
        if isinstance(reproducibility_contract.get("artifact_replay"), dict)
        else {}
    )
    choice_resolution = (
        applied_meta.get("choice_resolution")
        if isinstance(applied_meta, dict) and isinstance(applied_meta.get("choice_resolution"), dict)
        else {}
    )
    choice_items = (
        choice_resolution.get("resolved_choices", choice_resolution.get("choice_ledger"))
        if isinstance(choice_resolution, dict)
        else []
    ) or []
    choice_ids = [
        str(item.get("id") or "").strip()
        for item in choice_items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    route_items = (
        choice_resolution.get("route_decisions")
        if isinstance(choice_resolution, dict) and isinstance(choice_resolution.get("route_decisions"), list)
        else []
    )
    route_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in route_items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    active_routes = sorted(route_id for route_id, active in route_status.items() if active)
    route_ledger = (
        choice_resolution.get("route_decision_ledger")
        if isinstance(choice_resolution, dict)
        and isinstance(choice_resolution.get("route_decision_ledger"), dict)
        else {}
    )
    route_ledger_items = (
        route_ledger.get("routes")
        if isinstance(route_ledger.get("routes"), list)
        else []
    )
    route_ledger_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in route_ledger_items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    route_ledger_active_routes = sorted(
        route_id for route_id, active in route_ledger_status.items() if active
    )

    applied = (
        valid_contract
        and bool(current_sha)
        and applied_by == "scripts/apply_design_contract.py"
        and applied_sha == current_sha
        and applied_seed == current_seed
    )
    stale_apply = bool(
        valid_contract
        and applied_meta
        and current_sha
        and applied_sha
        and applied_sha != current_sha
    )
    if not contract_path.exists() and not applied_meta:
        status = "none"
    elif not contract_path.exists() and applied_meta:
        status = "applied_without_local_contract"
    elif contract_path.exists() and contract_error:
        status = "contract_invalid_json"
    elif contract_path.exists() and not valid_contract:
        status = "contract_invalid"
    elif valid_contract and not applied_meta:
        status = "contract_not_applied"
    elif valid_contract and applied_by != "scripts/apply_design_contract.py":
        status = "contract_applied_by_unknown_tool"
    elif valid_contract and not applied_sha:
        status = "contract_apply_unstamped"
    elif stale_apply or applied_seed != current_seed:
        status = "contract_changed_since_apply"
    elif applied:
        status = "applied"
    else:
        status = "needs_review"

    return {
        "status": status,
        "contract": contract_snapshot,
        "apply_report": apply_report_snapshot,
        "valid": valid_contract,
        "applied": applied,
        "stale_apply": stale_apply,
        "error": contract_error,
        "contract_version": (
            contract_payload.get("contract_version") if isinstance(contract_payload, dict) else ""
        ),
        "stable_prompt_id": current_seed,
        "qa_contract": {
            "exists": bool(qa_contract),
            "required_checks": required_checks,
            "required_check_count": len(required_checks),
            "fail_on": fail_on,
            "fail_on_count": len(fail_on),
            "visual_risks_to_check": visual_risks,
            "placeholder_checks": bool(qa_contract.get("placeholder_checks"))
            if isinstance(qa_contract, dict)
            else False,
        },
        "slide_quality_contract": {
            "exists": bool(slide_quality_contract),
            "contract_version": str(slide_quality_contract.get("contract_version") or "")
            if isinstance(slide_quality_contract, dict)
            else "",
            "min_title_pt": quality_readability.get("min_title_pt"),
            "min_body_pt": quality_readability.get("min_body_pt"),
            "min_caption_pt": quality_readability.get("min_caption_pt"),
            "chart_label_min_pt": quality_readability.get("chart_label_min_pt"),
            "footer_reserved_inches": quality_readability.get("footer_reserved_inches"),
            "max_title_lines": quality_readability.get("max_title_lines"),
            "max_slide_text_lines": quality_readability.get("max_slide_text_lines"),
            "max_slide_words": quality_readability.get("max_slide_words"),
            "max_slide_chars": quality_readability.get("max_slide_chars"),
            "evidence_anchor_required": bool(quality_layout.get("evidence_anchor_required")),
            "fail_on_awkward_whitespace": bool(quality_layout.get("fail_on_awkward_whitespace")),
            "sparse_slide_allowed_only_when_intentional": bool(
                quality_layout.get("sparse_slide_allowed_only_when_intentional")
            ),
            "source_footer_rule": str(quality_layout.get("source_footer_rule") or ""),
            "artifact_quality_required_when_data_active": bool(
                quality_artifacts.get("required_when_data_artifacts_active")
            ),
            "artifact_must_record": quality_must_record,
            "artifact_must_record_count": len(quality_must_record),
            "fail_on": quality_fail_on,
            "fail_on_count": len(quality_fail_on),
            "required_commands": quality_commands,
            "required_command_count": len(quality_commands),
        },
        "subagent_handoff": {
            "exists": bool(subagent_handoff),
            "ask_user_first": bool(subagent_handoff.get("ask_user_first"))
            if isinstance(subagent_handoff, dict)
            else False,
            "keys": sorted(str(key) for key in subagent_handoff.keys())
            if isinstance(subagent_handoff, dict)
            else [],
        },
        "agent_execution_plan": agent_execution_plan,
        "choice_resolution": {
            "exists": bool(choice_resolution),
            "contract_version": str(choice_resolution.get("contract_version") or "")
            if isinstance(choice_resolution, dict)
            else "",
            "stable_prompt_id": str(choice_resolution.get("stable_prompt_id") or "")
            if isinstance(choice_resolution, dict)
            else "",
            "choice_ids": choice_ids,
            "choice_count": len(choice_ids),
            "route_status": route_status,
            "active_routes": active_routes,
            "route_ledger_version": str(route_ledger.get("ledger_version") or "")
            if route_ledger
            else "",
            "route_ledger_status": route_ledger_status,
            "route_ledger_active_routes": route_ledger_active_routes,
        },
        "reproducibility_contract": {
            "exists": bool(reproducibility_contract),
            "contract_version": str(reproducibility_contract.get("contract_version") or "")
            if isinstance(reproducibility_contract, dict)
            else "",
            "stable_prompt_id": str(reproducibility_contract.get("stable_prompt_id") or "")
            if isinstance(reproducibility_contract, dict)
            else "",
            "style_seed": str(reproducibility_contract.get("style_seed") or "")
            if isinstance(reproducibility_contract, dict)
            else "",
            "renderer": str(reproducibility_contract.get("renderer") or "")
            if isinstance(reproducibility_contract, dict)
            else "",
            "locked_design_fields": _string_list(
                reproducibility_contract.get("locked_design_fields")
            ),
            "locked_design_field_count": len(
                _string_list(reproducibility_contract.get("locked_design_fields"))
            ),
            "replay_commands": _string_list(reproducibility_contract.get("replay_commands")),
            "replay_command_count": len(
                _string_list(reproducibility_contract.get("replay_commands"))
            ),
            "acceptance_evidence": _string_list(
                reproducibility_contract.get("acceptance_evidence")
            ),
            "style_replay": {
                "style_preset": str(style_replay.get("style_preset") or ""),
                "background_system": str(style_replay.get("background_system") or ""),
                "header_variant_pool": _string_list(style_replay.get("header_variant_pool")),
                "footer_pool": _string_list(style_replay.get("footer_pool")),
                "chart_treatment_pool": _string_list(style_replay.get("chart_treatment_pool")),
                "figure_table_treatment_pool": _string_list(
                    style_replay.get("figure_table_treatment_pool")
                ),
                "mix_rule": str(style_replay.get("mix_rule") or ""),
            },
            "structure_replay": {
                "target_slide_count": structure_replay.get("target_slide_count"),
                "slide_variant_mix": _string_list(structure_replay.get("slide_variant_mix")),
            },
            "artifact_replay": {
                "local_data_needed": artifact_replay.get("local_data_needed"),
                "artifact_manifest": str(artifact_replay.get("artifact_manifest") or ""),
                "analysis_summary": str(artifact_replay.get("analysis_summary") or ""),
                "figure_script": str(artifact_replay.get("figure_script") or ""),
                "rebuild_commands": _string_list(artifact_replay.get("rebuild_commands")),
            },
        },
        "acceptance_evidence": acceptance_evidence,
        "applied_metadata": {
            "exists": bool(applied_meta),
            "applied_by": applied_by,
            "stable_prompt_id": applied_seed,
            "contract_sha256": applied_sha,
            "contract_path": str(applied_meta.get("contract_path") or "") if isinstance(applied_meta, dict) else "",
        },
    }


def _data_analysis_handoff_selection_file(
    workspace: Path,
    handoff_payload: Any,
    apply_payload: Any,
) -> Path:
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


def _data_handoff_rebuild_context(handoff_payload: Any) -> dict[str, Any]:
    if not isinstance(handoff_payload, dict):
        return {}
    context = handoff_payload.get("artifact_rebuild_context")
    if isinstance(context, dict):
        return context
    main = handoff_payload.get("main_agent_handoff")
    if isinstance(main, dict) and isinstance(main.get("artifact_rebuild_context"), dict):
        return main["artifact_rebuild_context"]
    return {}


def _rebuild_context_commands(context: dict[str, Any]) -> list[str]:
    commands = context.get("commands") if isinstance(context.get("commands"), dict) else {}
    values = [
        commands.get("rebuild_figures"),
        commands.get("inspect_manifest"),
        commands.get("auto_select_lead"),
        commands.get("auto_select_all"),
        commands.get("validate_planning"),
    ]
    if isinstance(context.get("commands_to_preserve"), list):
        values.extend(context.get("commands_to_preserve", []))
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _data_handoff_rebuild_summary(
    handoff_context: dict[str, Any],
    persisted_context: dict[str, Any],
    *,
    apply_payload: Any,
) -> dict[str, Any]:
    context = handoff_context if handoff_context else persisted_context
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
        "present": bool(handoff_context),
        "persisted": bool(persisted_context),
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


def _data_handoff_scout_analysis_summary(
    handoff_payload: Any,
    persisted_ledger: dict[str, Any],
    *,
    apply_payload: Any,
) -> dict[str, Any]:
    raw = handoff_payload if isinstance(handoff_payload, dict) else {}
    source = persisted_ledger if persisted_ledger else raw
    workflow = source.get("recommended_workflow") if isinstance(source, dict) else {}
    workflow = workflow if isinstance(workflow, dict) else {}

    def object_ids(key: str) -> list[str]:
        if not isinstance(source, dict) or not isinstance(source.get(key), list):
            return []
        return _string_list(
            [
                item.get("id") or item.get("name") or item.get("title")
                for item in source.get(key, [])
                if isinstance(item, dict)
            ]
        )[:8]

    target_slide_ids: list[str] = []
    variants: list[str] = []
    if isinstance(source, dict):
        for key in ("chart_or_table_recommendations", "outline_binding_plan"):
            for item in source.get(key, []) if isinstance(source.get(key), list) else []:
                if not isinstance(item, dict):
                    continue
                slide_id = str(item.get("target_slide") or item.get("slide_id") or "").strip()
                variant = str(item.get("variant") or item.get("target_variant") or item.get("slide_variant") or "").strip()
                if slide_id and slide_id not in target_slide_ids:
                    target_slide_ids.append(slide_id)
                if variant and variant not in variants:
                    variants.append(variant)
    return {
        "present": any(
            isinstance(raw.get(key), list) and raw.get(key)
            for key in (
                "analysis_tasks",
                "computed_findings",
                "chart_or_table_recommendations",
                "outline_binding_plan",
                "quality_flags",
                "open_questions",
            )
        ),
        "persisted": bool(persisted_ledger),
        "applied": bool(apply_payload.get("scout_analysis_applied")) if isinstance(apply_payload, dict) else False,
        "schema": str(source.get("schema") or "") if isinstance(source, dict) else "",
        "analysis_task_count": _count_list(source.get("analysis_tasks")) if isinstance(source, dict) else 0,
        "computed_finding_count": _count_list(source.get("computed_findings")) if isinstance(source, dict) else 0,
        "visual_recommendation_count": _count_list(source.get("chart_or_table_recommendations")) if isinstance(source, dict) else 0,
        "outline_binding_count": _count_list(source.get("outline_binding_plan")) if isinstance(source, dict) else 0,
        "quality_flag_count": _count_list(source.get("quality_flags")) if isinstance(source, dict) else 0,
        "open_question_count": _count_list(source.get("open_questions")) if isinstance(source, dict) else 0,
        "analysis_task_ids": object_ids("analysis_tasks"),
        "computed_finding_ids": object_ids("computed_findings"),
        "visual_recommendation_ids": object_ids("chart_or_table_recommendations"),
        "target_slide_ids": target_slide_ids[:8],
        "variants": variants[:8],
        "quality_flags": _string_list(source.get("quality_flags") if isinstance(source, dict) else [])[:4],
        "open_questions": _string_list(source.get("open_questions") if isinstance(source, dict) else [])[:4],
        "recommended_workflow_mode": str(workflow.get("mode") or "").strip(),
    }


def _data_handoff_storyboard_summary(
    apply_payload: Any,
    persisted_storyboard: dict[str, Any],
) -> dict[str, Any]:
    raw = {}
    if isinstance(apply_payload, dict):
        raw = apply_payload.get("artifact_storyboard") if isinstance(apply_payload.get("artifact_storyboard"), dict) else {}
        if not raw:
            ledger = apply_payload.get("artifact_evidence_ledger")
            if isinstance(ledger, dict) and isinstance(ledger.get("slide_artifact_storyboard"), dict):
                raw = ledger["slide_artifact_storyboard"]
    source = persisted_storyboard if persisted_storyboard else raw
    items = source.get("items") if isinstance(source, dict) and isinstance(source.get("items"), list) else []
    slide_ids: list[str] = []
    variants: list[str] = []
    output_ids: list[str] = []
    roles: list[str] = []
    data_paths: list[str] = []
    script_paths: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for value, target in (
            (item.get("slide_id"), slide_ids),
            (item.get("variant"), variants),
            (item.get("output_id"), output_ids),
        ):
            text = str(value or "").strip()
            if text and text not in target:
                target.append(text)
        for value, target in (
            (item.get("artifact_roles"), roles),
            (item.get("data_source_paths"), data_paths),
            (item.get("script_edit_paths"), script_paths),
        ):
            for text in _string_list(value):
                if text and text not in target:
                    target.append(text)
    return {
        "present": bool(raw),
        "persisted": bool(persisted_storyboard),
        "applied": bool(apply_payload.get("artifact_storyboard_applied")) if isinstance(apply_payload, dict) else False,
        "schema": str(source.get("schema") or "") if isinstance(source, dict) else "",
        "item_count": len([item for item in items if isinstance(item, dict)]),
        "slide_ids": slide_ids[:8],
        "variants": variants[:8],
        "output_ids": output_ids[:8],
        "artifact_roles": roles[:8],
        "data_source_paths": data_paths[:8],
        "script_edit_paths": script_paths[:8],
    }


def _data_analysis_handoff_summary(workspace: Path) -> dict[str, Any]:
    handoff_path = workspace / "data_analysis_handoff.json"
    apply_report_path = workspace / "data_analysis_handoff_apply_report.json"
    legacy_apply_report_path = workspace / "build" / "data_analysis_handoff_apply.json"
    if not apply_report_path.exists() and legacy_apply_report_path.exists():
        apply_report_path = legacy_apply_report_path

    handoff_snapshot = _file_snapshot(workspace, handoff_path)
    apply_snapshot = _file_snapshot(workspace, apply_report_path)
    handoff_payload, handoff_error = _load_json_with_error(handoff_path)
    apply_payload, apply_error = _load_json_with_error(apply_report_path)
    design_payload, _design_error = _load_json_with_error(workspace / "design_brief.json")
    selection_path = _data_analysis_handoff_selection_file(
        workspace,
        handoff_payload,
        apply_payload,
    )
    selection_snapshot = _file_snapshot(workspace, selection_path)
    selection_payload = _load_json(selection_path, {}) if selection_path.exists() else {}
    selection_bindings = (
        selection_payload.get("bindings")
        if isinstance(selection_payload, dict) and isinstance(selection_payload.get("bindings"), list)
        else []
    )
    bound_output_ids = []
    slide_ids = []
    variants = []
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

    bindings = []
    if isinstance(handoff_payload, dict):
        selection_block = handoff_payload.get("artifact_selection_recommendations")
        if isinstance(selection_block, dict) and isinstance(selection_block.get("bindings"), list):
            bindings = selection_block["bindings"]
    current_sha = str(handoff_snapshot.get("sha256") or "").strip()
    applied_sha = str(apply_payload.get("handoff_sha256") or "").strip() if isinstance(apply_payload, dict) else ""
    dry_run = bool(apply_payload.get("dry_run")) if isinstance(apply_payload, dict) else False
    selection_count = int(apply_payload.get("selection_count") or 0) if isinstance(apply_payload, dict) else len(bindings)
    applied_bindings = bool(apply_payload.get("applied_bindings")) if isinstance(apply_payload, dict) else False
    rebuild_context = _data_handoff_rebuild_context(handoff_payload)
    analysis_plan = (
        design_payload.get("analysis_artifact_plan")
        if isinstance(design_payload, dict) and isinstance(design_payload.get("analysis_artifact_plan"), dict)
        else {}
    )
    data_handoff_meta = (
        design_payload.get("data_analysis_handoff")
        if isinstance(design_payload, dict) and isinstance(design_payload.get("data_analysis_handoff"), dict)
        else {}
    )
    persisted_rebuild_context = (
        data_handoff_meta.get("artifact_rebuild_context")
        if isinstance(data_handoff_meta.get("artifact_rebuild_context"), dict)
        else {}
    )
    if not persisted_rebuild_context and isinstance(analysis_plan.get("data_analysis_rebuild_context"), dict):
        persisted_rebuild_context = analysis_plan["data_analysis_rebuild_context"]
    persisted_scout_analysis = (
        data_handoff_meta.get("scout_analysis")
        if isinstance(data_handoff_meta.get("scout_analysis"), dict)
        else {}
    )
    if not persisted_scout_analysis and isinstance(analysis_plan.get("data_analysis_scout"), dict):
        persisted_scout_analysis = analysis_plan["data_analysis_scout"]
    persisted_storyboard = (
        data_handoff_meta.get("artifact_storyboard")
        if isinstance(data_handoff_meta.get("artifact_storyboard"), dict)
        else {}
    )
    if not persisted_storyboard and isinstance(analysis_plan.get("data_artifact_storyboard"), dict):
        persisted_storyboard = analysis_plan["data_artifact_storyboard"]
    if not handoff_path.exists() and not apply_report_path.exists():
        status = "none"
    elif not handoff_path.exists() and apply_report_path.exists():
        status = "applied_without_local_handoff"
    elif handoff_error:
        status = "handoff_invalid_json"
    elif not isinstance(handoff_payload, dict):
        status = "handoff_invalid"
    elif not apply_report_path.exists():
        status = "handoff_not_applied"
    elif apply_error:
        status = "apply_report_invalid_json"
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

    return {
        "status": status,
        "handoff": handoff_snapshot,
        "apply_report": apply_snapshot,
        "selection_file": selection_snapshot,
        "valid": isinstance(handoff_payload, dict) and not handoff_error,
        "error": handoff_error,
        "apply_error": apply_error,
        "applied": status == "applied",
        "stale_apply": status == "handoff_changed_since_apply",
        "selection_count": selection_count,
        "binding_count": len(bindings),
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
        "artifact_rebuild_context": _data_handoff_rebuild_summary(
            rebuild_context,
            persisted_rebuild_context,
            apply_payload=apply_payload,
        ),
        "artifact_contracts": {
            "figure_export_contract_applied": bool(apply_payload.get("figure_export_contract_applied")) if isinstance(apply_payload, dict) else False,
            "figure_export_output_count": int(apply_payload.get("figure_export_output_count") or 0) if isinstance(apply_payload, dict) else 0,
            "artifact_registry_update_count": int(apply_payload.get("artifact_registry_update_count") or 0) if isinstance(apply_payload, dict) else 0,
            "asset_plan_update_counts": apply_payload.get("asset_plan_update_counts") if isinstance(apply_payload, dict) and isinstance(apply_payload.get("asset_plan_update_counts"), dict) else {},
        },
        "scout_analysis": _data_handoff_scout_analysis_summary(
            handoff_payload,
            persisted_scout_analysis,
            apply_payload=apply_payload,
        ),
        "artifact_storyboard": _data_handoff_storyboard_summary(
            apply_payload,
            persisted_storyboard,
        ),
        "recommended_workflow": (
            handoff_payload.get("recommended_workflow") if isinstance(handoff_payload, dict) else {}
        ),
        "applied_metadata": {
            "handoff_sha256": applied_sha,
            "dry_run": dry_run,
            "changed_file_count": apply_payload.get("changed_file_count") if isinstance(apply_payload, dict) else None,
            "artifact_rebuild_context_applied": bool(apply_payload.get("artifact_rebuild_context_applied")) if isinstance(apply_payload, dict) else False,
        },
        "applied_ledger": (
            apply_payload.get("artifact_evidence_ledger")
            if isinstance(apply_payload, dict) and isinstance(apply_payload.get("artifact_evidence_ledger"), dict)
            else {}
        ),
    }


def _outline_authoring_handoff_summary(workspace: Path) -> dict[str, Any]:
    handoff_path = workspace / "outline_authoring_handoff.json"
    apply_report_path = workspace / "outline_authoring_handoff_apply_report.json"
    design_path = workspace / "design_brief.json"
    handoff_snapshot = _file_snapshot(workspace, handoff_path)
    apply_snapshot = _file_snapshot(workspace, apply_report_path)
    handoff_payload, handoff_error = _load_json_with_error(handoff_path)
    apply_payload, apply_error = _load_json_with_error(apply_report_path)
    design_payload, _design_error = _load_json_with_error(design_path)
    valid = (
        isinstance(handoff_payload, dict)
        and str(handoff_payload.get("handoff_version") or "").strip()
        == "outline_authoring_handoff_v1"
        and not handoff_error
    )
    current_sha = str(handoff_snapshot.get("sha256") or "").strip()
    applied_sha = str(apply_payload.get("handoff_sha256") or "").strip() if isinstance(apply_payload, dict) else ""
    dry_run = bool(apply_payload.get("dry_run")) if isinstance(apply_payload, dict) else False
    workflow = str(apply_payload.get("workflow") or "").strip() if isinstance(apply_payload, dict) else ""

    if not handoff_path.exists() and not apply_report_path.exists():
        status = "none"
    elif not handoff_path.exists() and apply_report_path.exists():
        status = "applied_without_local_handoff"
    elif handoff_error:
        status = "handoff_invalid_json"
    elif not isinstance(handoff_payload, dict):
        status = "handoff_invalid"
    elif not valid:
        status = "handoff_invalid"
    elif not apply_report_path.exists():
        status = "handoff_not_applied"
    elif apply_error:
        status = "apply_report_invalid_json"
    elif dry_run:
        status = "handoff_apply_dry_run_only"
    elif workflow != "outline_authoring_handoff_apply_v1":
        status = "handoff_apply_unstamped"
    elif not applied_sha:
        status = "handoff_apply_unstamped"
    elif current_sha and applied_sha and current_sha != applied_sha:
        status = "handoff_changed_since_apply"
    elif current_sha and applied_sha == current_sha:
        status = "applied"
    else:
        status = "needs_review"

    patch = handoff_payload.get("source_patch") if isinstance(handoff_payload, dict) else {}
    patch = patch if isinstance(patch, dict) else {}
    rebuild_plan = (
        handoff_payload.get("artifact_rebuild_plan")
        if isinstance(handoff_payload, dict) and isinstance(handoff_payload.get("artifact_rebuild_plan"), dict)
        else {}
    )
    quality_alignment = (
        handoff_payload.get("quality_alignment")
        if isinstance(handoff_payload, dict) and isinstance(handoff_payload.get("quality_alignment"), dict)
        else {}
    )
    design_outline = (
        design_payload.get("outline_authoring_handoff")
        if isinstance(design_payload, dict) and isinstance(design_payload.get("outline_authoring_handoff"), dict)
        else {}
    )
    persisted_rebuild_plan = (
        design_outline.get("artifact_rebuild_plan")
        if isinstance(design_outline.get("artifact_rebuild_plan"), dict)
        else {}
    )
    persisted_quality_alignment = (
        design_outline.get("quality_alignment")
        if isinstance(design_outline.get("quality_alignment"), dict)
        else {}
    )
    preserved_commands = _string_list(rebuild_plan.get("commands_to_preserve"))
    if not preserved_commands and isinstance(rebuild_plan.get("commands"), dict):
        preserved_commands = [
            str(item).strip()
            for item in rebuild_plan.get("commands", {}).values()
            if str(item).strip()
        ]
    quality_readability = _string_list(quality_alignment.get("readability_targets_used"))
    quality_layout = _string_list(quality_alignment.get("layout_targets_used"))
    quality_artifacts = _string_list(quality_alignment.get("artifact_quality_targets_used"))
    quality_qa = _string_list(quality_alignment.get("qa_gates_used"))
    quality_commands = _string_list(quality_alignment.get("required_commands"))
    return {
        "status": status,
        "handoff": handoff_snapshot,
        "apply_report": apply_snapshot,
        "valid": valid,
        "error": handoff_error,
        "apply_error": apply_error,
        "applied": status == "applied",
        "stale_apply": status == "handoff_changed_since_apply",
        "handoff_version": handoff_payload.get("handoff_version") if isinstance(handoff_payload, dict) else "",
        "patch_fields": sorted([key for key, value in patch.items() if value not in (None, "", [], {})]),
        "artifact_rebuild_plan": {
            "present": bool(rebuild_plan),
            "persisted": bool(persisted_rebuild_plan),
            "context_version": str(rebuild_plan.get("context_version") or ""),
            "producer_path": str(rebuild_plan.get("producer_path") or ""),
            "source_count": len(_string_list(rebuild_plan.get("source_paths"))),
            "output_count": len(_string_list(rebuild_plan.get("output_paths"))),
            "command_count": len(preserved_commands),
            "commands": preserved_commands[:6],
        },
        "quality_alignment": {
            "present": bool(quality_alignment),
            "persisted": bool(persisted_quality_alignment),
            "contract_version": str(quality_alignment.get("contract_version") or ""),
            "readability_target_count": len(quality_readability),
            "readability_targets_used": quality_readability[:8],
            "layout_target_count": len(quality_layout),
            "layout_targets_used": quality_layout[:8],
            "artifact_quality_target_count": len(quality_artifacts),
            "artifact_quality_targets_used": quality_artifacts[:8],
            "qa_gate_count": len(quality_qa),
            "qa_gates_used": quality_qa[:8],
            "required_command_count": len(quality_commands),
            "required_commands": quality_commands[:6],
            "outline_choices": str(quality_alignment.get("outline_choices") or ""),
        },
        "applied_metadata": {
            "workflow": workflow,
            "handoff_sha256": applied_sha,
            "dry_run": dry_run,
            "changed_file_count": apply_payload.get("changed_file_count") if isinstance(apply_payload, dict) else None,
            "artifact_rebuild_plan_applied": bool(apply_payload.get("artifact_rebuild_plan_applied")) if isinstance(apply_payload, dict) else False,
            "quality_alignment_applied": bool(apply_payload.get("quality_alignment_applied")) if isinstance(apply_payload, dict) else False,
        },
    }


def _quality_context_summary(
    *,
    design_contract: dict[str, Any],
    outline_authoring_handoff: dict[str, Any],
) -> dict[str, Any]:
    slide_quality = (
        design_contract.get("slide_quality_contract")
        if isinstance(design_contract.get("slide_quality_contract"), dict)
        else {}
    )
    outline_quality = (
        outline_authoring_handoff.get("quality_alignment")
        if isinstance(outline_authoring_handoff.get("quality_alignment"), dict)
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


def _as_nonempty_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _slide_ref(slide: dict[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "slug"):
        value = str(slide.get(key) or "").strip()
        if value:
            return value
    return f"s{index + 1}"


def _slide_variant(slide: dict[str, Any]) -> str:
    variant = str(slide.get("variant") or "").strip().lower()
    return variant or "standard"


def _visual_anchor_kinds(slide: dict[str, Any]) -> list[str]:
    kinds: list[str] = []
    assets = slide.get("assets")
    if not isinstance(assets, dict):
        assets = {}

    def add(kind: str, present: Any) -> None:
        if present and kind not in kinds:
            kinds.append(kind)

    variant = _slide_variant(slide)
    if variant == "chart":
        add("chart", True)
    if variant in {"table", "lab-run-results"}:
        add("table", True)
    if variant in {"image-sidebar", "scientific-figure"}:
        add("figure", True)
    if variant == "generated-image":
        add("generated_image", True)
    if variant == "flow":
        add("diagram", True)

    add("image", assets.get("hero_image") or assets.get("image"))
    add("generated_image", assets.get("generated_image"))
    add("diagram", assets.get("diagram"))
    add("mermaid", assets.get("mermaid_source") or assets.get("mermaid"))
    add("chart", slide.get("chart") or assets.get("chart_data") or assets.get("chart"))
    add(
        "table",
        slide.get("table")
        or slide.get("table_data")
        or slide.get("tables")
        or assets.get("table_data")
        or assets.get("table")
        or assets.get("tables"),
    )
    add("figure", slide.get("figures") or assets.get("figures"))
    add("icons", assets.get("icons"))
    return kinds


def _structure_anchor_kinds(slide: dict[str, Any]) -> list[str]:
    variant = _slide_variant(slide)
    kinds: list[str] = []
    if variant in {"cards-2", "cards-3", "cards", "timeline", "stats", "matrix", "comparison-2col", "kpi-hero", "flow"}:
        kinds.append(variant)
    if slide.get("cards"):
        kinds.append("cards")
    if slide.get("milestones"):
        kinds.append("timeline")
    if slide.get("facts") or slide.get("stats"):
        kinds.append("stats")
    if slide.get("quadrants"):
        kinds.append("matrix")
    if slide.get("left") or slide.get("right") or slide.get("columns"):
        kinds.append("comparison")
    unique: list[str] = []
    for kind in kinds:
        if kind not in unique:
            unique.append(kind)
    return unique


def _outline_composition(workspace: Path, outline_path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": _display_path(workspace, outline_path),
        "exists": outline_path.exists(),
        "valid": False,
        "slide_count": 0,
        "content_slide_count": 0,
    }
    outline = _load_json(outline_path, {})
    if not isinstance(outline, dict):
        summary["error"] = "outline root is not a JSON object"
        return summary
    slides = outline.get("slides")
    if not isinstance(slides, list):
        summary["error"] = "outline.slides is missing or not a list"
        return summary

    variant_counts: Counter[str] = Counter()
    content_variant_counts: Counter[str] = Counter()
    visual_anchor_counts: Counter[str] = Counter()
    structure_anchor_counts: Counter[str] = Counter()
    slide_summaries: list[dict[str, Any]] = []
    content_refs: list[str] = []
    visual_anchor_refs: list[str] = []
    structure_anchor_refs: list[str] = []
    unanchored_content_refs: list[str] = []
    missing_source_refs: list[str] = []

    for idx, raw_slide in enumerate(slides):
        if not isinstance(raw_slide, dict):
            continue
        slide_type = str(raw_slide.get("type") or "content").strip().lower() or "content"
        variant = _slide_variant(raw_slide)
        slide_ref = _slide_ref(raw_slide, idx)
        title = str(raw_slide.get("title") or "").strip()
        sources = [
            *_as_nonempty_list(raw_slide.get("sources")),
            *_as_nonempty_list(raw_slide.get("refs")),
            *_as_nonempty_list(raw_slide.get("references")),
        ]
        visual_kinds = _visual_anchor_kinds(raw_slide)
        structure_kinds = _structure_anchor_kinds(raw_slide)
        variant_counts[variant] += 1
        for kind in visual_kinds:
            visual_anchor_counts[kind] += 1
        for kind in structure_kinds:
            structure_anchor_counts[kind] += 1
        if slide_type == "content":
            content_refs.append(slide_ref)
            content_variant_counts[variant] += 1
            if visual_kinds:
                visual_anchor_refs.append(slide_ref)
            if structure_kinds:
                structure_anchor_refs.append(slide_ref)
            if not visual_kinds and not structure_kinds:
                unanchored_content_refs.append(slide_ref)
            if not sources:
                missing_source_refs.append(slide_ref)
        slide_summaries.append(
            {
                "index": idx,
                "slide_id": slide_ref,
                "type": slide_type,
                "variant": variant,
                "title": title,
                "visual_anchor_kinds": visual_kinds,
                "structure_anchor_kinds": structure_kinds,
                "has_sources": bool(sources),
            }
        )

    content_count = len(content_refs)
    dominant_variant = ""
    dominant_variant_count = 0
    dominant_variant_ratio = 0.0
    if content_variant_counts:
        dominant_variant, dominant_variant_count = content_variant_counts.most_common(1)[0]
        dominant_variant_ratio = dominant_variant_count / max(1, content_count)

    warning_signals: list[str] = []
    if content_count >= 3 and not visual_anchor_refs:
        warning_signals.append("no_visual_anchors")
    if content_count >= 4 and len(unanchored_content_refs) / max(1, content_count) >= 0.5:
        warning_signals.append("many_unanchored_content_slides")
    if content_count >= 4 and dominant_variant_ratio >= 0.75:
        warning_signals.append("dominant_variant_repetition")
    if content_count >= 3 and len(missing_source_refs) / max(1, content_count) >= 0.5:
        warning_signals.append("low_source_coverage")

    summary.update(
        {
            "valid": True,
            "slide_count": len(slides),
            "content_slide_count": content_count,
            "variant_counts": dict(sorted(variant_counts.items())),
            "content_variant_counts": dict(sorted(content_variant_counts.items())),
            "visual_anchor_counts": dict(sorted(visual_anchor_counts.items())),
            "structure_anchor_counts": dict(sorted(structure_anchor_counts.items())),
            "visual_anchor_slide_ids": visual_anchor_refs,
            "structure_anchor_slide_ids": structure_anchor_refs,
            "unanchored_content_slide_ids": unanchored_content_refs,
            "missing_source_content_slide_ids": missing_source_refs,
            "dominant_content_variant": dominant_variant,
            "dominant_content_variant_count": dominant_variant_count,
            "dominant_content_variant_ratio": round(dominant_variant_ratio, 3),
            "warning_signals": warning_signals,
            "slides": slide_summaries,
        }
    )
    return summary


def _starter_content_slide(slide: dict[str, Any]) -> bool:
    return (
        str(slide.get("slide_id") or "").strip() == "s2"
        and str(slide.get("type") or "").strip().lower() == "content"
        and str(slide.get("variant") or "").strip() == "split"
        and str(slide.get("title") or "").strip() == "Core message"
    )


def _outline_authored_from_contract(outline_composition: dict[str, Any]) -> bool:
    slides = outline_composition.get("slides")
    if not isinstance(slides, list):
        return False
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        if str(slide.get("type") or "").strip().lower() != "content":
            continue
        if not _starter_content_slide(slide):
            return True
    return False


def _delivery_ready(workspace: Path) -> tuple[bool, str]:
    path = workspace / "build" / "delivery_readiness.json"
    payload = _load_json(path, {})
    status = str(payload.get("delivery_status") or "").strip() if isinstance(payload, dict) else ""
    return status == "ready", status


def _summary_route_active(summary: dict[str, Any], route_id: str) -> bool | None:
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
        for key in ("route_ledger_active_routes", "active_routes"):
            active_routes = candidate.get(key)
            if isinstance(active_routes, list) and route_id in {str(item) for item in active_routes}:
                return True
    return None


def _deck_execution_plan_progress(
    *,
    workspace: Path,
    deck_intake: dict[str, Any],
    design_contract: dict[str, Any],
    pptx_style: dict[str, Any],
    data_analysis_handoff: dict[str, Any],
    artifact_manifest_summary: dict[str, Any],
    artifact_selection_summary: dict[str, Any],
    outline_composition: dict[str, Any],
    planning: dict[str, Any],
    preflight: dict[str, Any],
    last_build: dict[str, Any],
    recommendations: list[dict[str, Any]],
    next_action: dict[str, Any],
) -> dict[str, Any]:
    packet_plan = (
        deck_intake.get("execution_plan")
        if isinstance(deck_intake.get("execution_plan"), dict)
        else {}
    )
    phase_proof = (
        deck_intake.get("phase_proof_ledger")
        if isinstance(deck_intake.get("phase_proof_ledger"), dict)
        else {}
    )
    phase_ids = [
        str(item).strip()
        for item in packet_plan.get("phase_ids", [])
        if str(item).strip()
    ] if isinstance(packet_plan.get("phase_ids"), list) else []
    if not phase_ids:
        return {
            "status": "none",
            "valid": False,
            "plan_version": str(packet_plan.get("plan_version") or ""),
            "phase_count": 0,
            "phase_ids": [],
            "current_phase_id": "",
            "phases": [],
            "phase_proof_ledger": phase_proof,
            "required_by_route_ledger": _string_list(phase_proof.get("route_required_phase_ids")),
        }
    route_required_from_proof = [
        phase_id
        for phase_id in _string_list(phase_proof.get("route_required_phase_ids"))
        if phase_id in set(phase_ids)
    ]

    last_build_qa = last_build.get("qa") if isinstance(last_build.get("qa"), dict) else {}
    visual_review_report = (
        last_build_qa.get("visual_review_report")
        if isinstance(last_build_qa.get("visual_review_report"), dict)
        else {}
    )
    delivery_ready, delivery_status = _delivery_ready(workspace)
    source_ready = (
        int(planning.get("error_count") or 0) == 0
        and int(planning.get("warning_count") or 0) == 0
        and int(preflight.get("error_count") or 0) == 0
        and int(preflight.get("warning_count") or 0) == 0
        and not recommendations
    )
    data_bound = bool(
        data_analysis_handoff.get("applied")
        or (
            artifact_manifest_summary.get("valid")
            and int(artifact_selection_summary.get("binding_count") or 0) > 0
        )
    )
    fast_build_checked = bool(
        last_build.get("exists")
        and str(last_build.get("run_status") or "").strip() == "succeeded"
        and isinstance(last_build.get("qa_counts"), dict)
    )
    completed_by_phase = {
        "ask_or_assume_intake": bool(
            deck_intake.get("applied")
            or deck_intake.get("user_intake_exists")
            or deck_intake.get("status") in {"applied_without_local_answers", "applied_without_report"}
        ),
        "lock_design_contract": bool(
            design_contract.get("applied")
            or design_contract.get("status") == "applied_without_local_contract"
        ),
        "extract_reference_style": bool(
            pptx_style.get("applied")
            or pptx_style.get("status") == "applied_without_local_fragment"
        ),
        "route_data_artifacts": data_bound,
        "author_outline_from_contract": bool(
            outline_composition.get("valid")
            and _outline_authored_from_contract(outline_composition)
        ),
        "source_readiness_gate": source_ready,
        "fast_first_pass_build": fast_build_checked,
        "rendered_visual_review": bool(visual_review_report.get("exists")),
        "final_delivery_audit": delivery_ready,
    }
    rendered_visual_review_required = (
        _summary_route_active(deck_intake, "rendered_visual_review") is True
        or _summary_route_active(design_contract, "rendered_visual_review") is True
        or "rendered_visual_review" in route_required_from_proof
    )
    route_required_set = set(route_required_from_proof)
    if rendered_visual_review_required:
        route_required_set.add("rendered_visual_review")
    route_required_phase_ids = [
        phase_id for phase_id in phase_ids if phase_id in route_required_set
    ]
    optional_phase_ids = set() if rendered_visual_review_required else {"rendered_visual_review"}
    phase_reasons = {
        "ask_or_assume_intake": str(deck_intake.get("status") or ""),
        "lock_design_contract": str(design_contract.get("status") or ""),
        "extract_reference_style": str(pptx_style.get("status") or ""),
        "route_data_artifacts": (
            "data_analysis_handoff_applied"
            if data_analysis_handoff.get("applied")
            else f"artifact_bindings={int(artifact_selection_summary.get('binding_count') or 0)}"
        ),
        "author_outline_from_contract": (
            "authored_outline_detected"
            if _outline_authored_from_contract(outline_composition)
            else "only_starter_or_missing_outline"
        ),
        "source_readiness_gate": (
            "ready"
            if source_ready
            else f"next_action={next_action.get('kind', 'none')}"
        ),
        "fast_first_pass_build": str(last_build.get("run_status") or "missing_build_report"),
        "rendered_visual_review": (
            "visual_review_report_exists"
            if visual_review_report.get("exists")
            else (
                "required_by_route_ledger"
                if rendered_visual_review_required
                else "optional_until_final_visual_acceptance"
            )
        ),
        "final_delivery_audit": delivery_status or "missing_delivery_readiness",
    }

    first_required_incomplete = ""
    phases: list[dict[str, Any]] = []
    for index, phase_id in enumerate(phase_ids, start=1):
        required = phase_id not in optional_phase_ids
        complete = bool(completed_by_phase.get(phase_id))
        status = "complete" if complete else "pending"
        phase_file_summary = (
            phase_proof.get("phase_proof_files", {}).get(phase_id, {})
            if isinstance(phase_proof.get("phase_proof_files"), dict)
            else {}
        )
        if required and not complete and not first_required_incomplete:
            first_required_incomplete = phase_id
            status = "current"
        elif not required and not complete:
            status = "available"
        phases.append(
            {
                "id": phase_id,
                "order": index,
                "required": required,
                "required_by_route_ledger": phase_id in route_required_set,
                "status": status,
                "complete": complete,
                "reason": phase_reasons.get(phase_id, ""),
                "acceptance_gate_ids": (
                    phase_proof.get("phase_acceptance_gate_ids", {}).get(phase_id, [])
                    if isinstance(phase_proof.get("phase_acceptance_gate_ids"), dict)
                    else []
                ),
                "proof_count": (
                    phase_proof.get("phase_proof_counts", {}).get(phase_id, 0)
                    if isinstance(phase_proof.get("phase_proof_counts"), dict)
                    else 0
                ),
                "proof_file_count": int(phase_file_summary.get("proof_file_count") or 0),
                "existing_proof_file_count": int(phase_file_summary.get("existing_file_count") or 0),
                "missing_proof_file_count": int(phase_file_summary.get("missing_file_count") or 0),
                "missing_proof_files": phase_file_summary.get("missing_files", []),
            }
        )

    required_phases = [item for item in phases if item.get("required")]
    completed_required = [item for item in required_phases if item.get("complete")]
    return {
        "status": "active" if packet_plan.get("valid") else "invalid",
        "valid": bool(packet_plan.get("valid")),
        "plan_version": str(packet_plan.get("plan_version") or ""),
        "phase_count": len(phases),
        "phase_ids": phase_ids,
        "current_phase_id": first_required_incomplete,
        "current_phase_status": (
            "complete" if not first_required_incomplete else "current"
        ),
        "completed_required_count": len(completed_required),
        "required_phase_count": len(required_phases),
        "rendered_visual_review_required": rendered_visual_review_required,
        "required_by_route_ledger": route_required_phase_ids,
        "phase_proof_ledger": phase_proof,
        "next_action_kind": str(next_action.get("kind") or "none"),
        "phases": phases,
    }


def _attach_execution_phase_command(
    execution_plan: dict[str, Any],
    next_commands: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(execution_plan, dict):
        return {}
    phase_id = str(execution_plan.get("current_phase_id") or "").strip()
    command_candidates = {
        "ask_or_assume_intake": ["intake_answers_apply"],
        "lock_design_contract": ["design_contract_apply", "design_contract_prompt"],
        "extract_reference_style": ["style_extract", "style_apply"],
        "route_data_artifacts": [
            "data_analysis_handoff_apply",
            "data_artifact_build",
        ],
        "author_outline_from_contract": ["outline_authoring_handoff_apply", "outline_authoring_prompt"],
        "source_readiness_gate": ["readiness"],
        "fast_first_pass_build": ["fast_first_pass_build"],
        "final_delivery_audit": ["delivery_audit"],
    }
    enriched = dict(execution_plan)
    enriched["current_phase_command_key"] = ""
    enriched["current_phase_command"] = []
    enriched["current_phase_command_text"] = ""
    for command_key in command_candidates.get(phase_id, []):
        command = next_commands.get(command_key)
        command_text = _command_text(command)
        if command_text:
            enriched["current_phase_command_key"] = command_key
            enriched["current_phase_command"] = command
            enriched["current_phase_command_text"] = command_text
            break
    return enriched


def _execution_phase_recommendations(
    *,
    execution_plan: dict[str, Any],
    outline_composition: dict[str, Any],
    design_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(execution_plan, dict):
        return []
    current_phase = str(execution_plan.get("current_phase_id") or "").strip()
    if current_phase == "lock_design_contract":
        return [
            {
                "kind": "author_design_contract_from_prompt",
                "reason": "The deck-start execution plan has reached design-contract locking, but design_contract.json has not been authored and applied yet.",
                "current_phase_id": current_phase,
                "design_contract_status": str(design_contract.get("status") or ""),
                "design_contract": "design_contract.json",
                "design_contract_apply_report": "design_contract_apply_report.json",
                "suggested_fields": [
                    "design_contract.json",
                    "design_brief.json:design_contract.choice_resolution",
                    "design_brief.json:style_system.style_mix_matrix",
                    "design_brief.json:readability_contract",
                    "evidence_plan.json:source_policy",
                    "asset_plan.json",
                ],
            }
        ]
    if current_phase != "author_outline_from_contract":
        return []
    content_slides = int(outline_composition.get("content_slide_count") or 0)
    return [
        {
            "kind": "author_outline_from_contract",
            "reason": "The deck-start execution plan has reached outline authoring, but outline.json still looks like starter or missing contract-authored content.",
            "current_phase_id": current_phase,
            "design_contract_status": str(design_contract.get("status") or ""),
            "outline_status": "only_starter_or_missing_outline",
            "content_slide_count": content_slides,
            "suggested_fields": [
                "outline.json:slides",
                "content_plan.json:slide_plan",
                "evidence_plan.json:items",
                "asset_plan.json",
                "notes.md:manual design choices",
            ],
            "suggested_variants": [
                "scientific-figure",
                "image-sidebar",
                "chart",
                "lab-run-results",
                "table",
                "comparison-2col",
            ],
        }
    ]


def _enrich_qa_warnings(
    warnings: list[Any],
    *,
    slide_by_index: dict[int, str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    enriched_warnings: list[dict[str, Any]] = []
    slide_ids: list[str] = []
    warning_types: list[str] = []
    for raw in warnings:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        warning_type = str(item.get("type") or "").strip()
        if warning_type and warning_type not in warning_types:
            warning_types.append(warning_type)
        slide_index = _safe_int(item.get("slide_index"))
        slide_id = slide_by_index.get(slide_index) if slide_index is not None else ""
        if slide_id:
            item["slide_id"] = slide_id
            if slide_id not in slide_ids:
                slide_ids.append(slide_id)
        enriched_warnings.append(item)
    return enriched_warnings, slide_ids, warning_types


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


def _qa_design_suggested_fix(warning: dict[str, Any]) -> str:
    warning_type = str(warning.get("type") or "").strip()
    normalized = warning_type.lower()
    role = _qa_design_role(warning_type, warning.get("role"))
    font_pt = warning.get("font_pt")
    min_allowed_pt = warning.get("min_allowed_pt")
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
        return "Shorten or split the affected text, choose a roomier variant, or raise the source font setting."
    if normalized == "footer_reserved_space_intrusion":
        reserved = warning.get("reserved_inches")
        intrusion = warning.get("intrusion_inches")
        if reserved not in (None, "") and intrusion not in (None, ""):
            return (
                f"Footer reserve is {reserved}in and content intrudes by {intrusion}in; "
                "move, shorten, or resize slide content so sources and page number stay below the reserve line."
            )
        return "Move, shorten, or resize slide content so sources and page number stay below the reserved footer line."
    if normalized == "table_density_risk":
        rows = warning.get("rows")
        columns = warning.get("columns")
        if rows not in (None, "") and columns not in (None, ""):
            return f"Table has {rows} rows and {columns} columns; split it, summarize it, or move detail to backup/reference slides."
        return "Split, summarize, or move dense table detail to backup/reference slides before final delivery."
    if normalized == "chart_value_label_headroom_risk":
        max_value = warning.get("max_value")
        axis_max = warning.get("axis_max")
        if max_value not in (None, "") and axis_max not in (None, ""):
            return (
                f"Chart value labels have little headroom: max value {max_value} against axis max {axis_max}; "
                "increase valueAxisMax or reduce label density."
            )
        return "Increase chart value-axis headroom or reduce label density so labels do not crowd the plot edge."
    if normalized == "stack_gap_too_small":
        return "Increase stack spacing or reduce the number/height of stacked blocks so adjacent elements breathe."
    return "Adjust source text, table/chart options, slide variant, or readability contract so the rendered warning clears."


def _enrich_qa_design_warnings(warnings: list[dict[str, Any]]) -> list[str]:
    suggested_fields: list[str] = []
    for warning in warnings:
        warning_type = str(warning.get("type") or "").strip()
        role = _qa_design_role(warning_type, warning.get("role"))
        if role:
            warning["role"] = role
        fields = _qa_design_suggested_fields(warning_type, role)
        warning["suggested_fields"] = fields
        warning["suggested_fix"] = _qa_design_suggested_fix(warning)
        for field in fields:
            if field not in suggested_fields:
                suggested_fields.append(field)
    return suggested_fields


def _slide_by_index(outline_composition: dict[str, Any]) -> dict[int, str]:
    slides = outline_composition.get("slides") if isinstance(outline_composition, dict) else []
    if not isinstance(slides, list):
        return {}
    return {
        int(item.get("index")): str(item.get("slide_id") or "")
        for item in slides
        if isinstance(item, dict) and _safe_int(item.get("index")) is not None
    }


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


def _preflight_recommendation_metadata(
    preflight: dict[str, Any],
    *,
    slide_by_index: dict[int, str],
    severities: set[str],
) -> dict[str, list[str]]:
    slide_ids: list[str] = []
    warning_types: list[str] = []
    suggested_fields: list[str] = []
    for raw in preflight.get("issues", []):
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "").strip().lower()
        if severity not in severities:
            continue
        rule = str(raw.get("rule") or "").strip()
        if rule and rule not in warning_types:
            warning_types.append(rule)
        slide_index = _safe_int(raw.get("slide_index"))
        slide_id = slide_by_index.get(slide_index) if slide_index is not None else ""
        if slide_id and slide_id not in slide_ids:
            slide_ids.append(slide_id)
        for field in _preflight_suggested_fields(rule):
            if field not in suggested_fields:
                suggested_fields.append(field)
    return {
        "slide_ids": slide_ids,
        "warning_types": warning_types,
        "suggested_fields": suggested_fields,
    }


def _planning_rule(path: str, message: str) -> str:
    normalized = f"{path}\n{message}".lower()
    if path.startswith("evidence_plan.") and any(
        token in normalized
        for token in ("artifact_ids", "artifact_aliases", "artifact_paths", "evidence artifact")
    ):
        return "evidence_artifact_context"
    if "image_whitespace" in normalized or "exterior blank area" in normalized or "trim or regenerate" in normalized:
        return "figure_export_whitespace"
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
    if "figure_export_whitespace" in normalized or "image_whitespace" in normalized or "exterior blank area" in normalized:
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


def _planning_recommendation_metadata(
    planning: dict[str, Any],
    *,
    severities: set[str],
) -> dict[str, list[str]]:
    planning_paths: list[str] = []
    warning_types: list[str] = []
    suggested_fields: list[str] = []
    for raw in planning.get("issues", []):
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "").strip().lower()
        if severity not in severities:
            continue
        path = str(raw.get("path") or "").strip()
        message = str(raw.get("message") or "").strip()
        if path and path not in planning_paths:
            planning_paths.append(path)
        rule = _planning_rule(path, message)
        if rule and rule not in warning_types:
            warning_types.append(rule)
        for field in _planning_suggested_fields(rule, path):
            if field not in suggested_fields:
                suggested_fields.append(field)
    return {
        "planning_paths": planning_paths,
        "warning_types": warning_types,
        "suggested_fields": suggested_fields,
    }


def _generated_artifact_staleness(planning: dict[str, Any]) -> dict[str, Any]:
    dependencies: set[str] = set()
    issue_count = 0
    for raw in planning.get("issues", []):
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity") or "").strip().lower()
        if severity not in {"warning", "error"}:
            continue
        path = str(raw.get("path") or "").strip()
        message = str(raw.get("message") or "").strip()
        normalized = f"{path}\n{message}".lower()
        artifact_context = any(
            token in normalized
            for token in (
                "analysis_artifact_plan",
                "artifact_manifest",
                "artifact_registry",
                "chart_json_outputs",
                "table_outputs",
                "data_source_fingerprints",
            )
        )
        stale_context = any(
            token in normalized
            for token in (
                "source_sha256 does not match",
                "source_bytes does not match",
                "source_size_bytes does not match",
                "producer_sha256 does not match",
                "producer_bytes does not match",
                "artifact sha256 does not match",
                "artifact bytes does not match",
                "appears older than source/script",
                "does not match current source file",
                "does not match current producer script",
            )
        )
        if not artifact_context or not stale_context:
            continue
        issue_count += 1
        if (
            "producer_sha256" in normalized
            or "producer_bytes" in normalized
            or "producer script" in normalized
            or "current producer script" in normalized
        ):
            dependencies.add("producer_script")
        if (
            "source_sha256" in normalized
            or "source_bytes" in normalized
            or "source_size_bytes" in normalized
            or "current source file" in normalized
            or "data_source_fingerprints" in normalized
        ):
            dependencies.add("source_data")
        if "artifact sha256" in normalized or "artifact bytes" in normalized:
            dependencies.add("generated_output")
        if "appears older than source/script" in normalized:
            dependencies.add("output_older_than_source")
    return {
        "detected": issue_count > 0,
        "issue_count": issue_count,
        "stale_artifact_dependencies": sorted(dependencies),
    }


def _stale_artifact_data_paths(stale_files: list[Any]) -> list[str]:
    suffixes = {".csv", ".tsv", ".xlsx", ".xls", ".json", ".jsonl", ".parquet", ".feather"}
    paths: list[str] = []
    seen: set[str] = set()
    for item in stale_files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        path = str(item.get("path") or "").strip()
        if not path or "artifact_source" not in name:
            continue
        if Path(path).suffix.lower() not in suffixes:
            continue
        if path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def _artifact_alias_labels(artifact_manifest_summary: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    aliases = artifact_manifest_summary.get("aliases")
    if not isinstance(aliases, list):
        return labels
    for alias in aliases:
        if not isinstance(alias, dict):
            continue
        output_id = str(alias.get("id") or "").strip()
        alias_values = [
            str(alias.get(key) or "").strip()
            for key in ("image_alias", "chart_alias", "table_alias")
            if str(alias.get(key) or "").strip()
        ]
        if output_id and alias_values:
            labels.append(f"{output_id}: {', '.join(alias_values)}")
    return labels


def _recommendations(
    *,
    workspace: Path,
    outline_path: Path,
    design_brief_path: Path,
    planning: dict[str, Any],
    preflight: dict[str, Any],
    artifact_manifest: Path,
    artifact_selection: Path,
    artifact_manifest_summary: dict[str, Any],
    artifact_selection_summary: dict[str, Any],
    outline_composition: dict[str, Any],
    last_build: dict[str, Any],
    tabular_data: list[str],
    pptx_style: dict[str, Any],
    deck_intake: dict[str, Any],
    design_contract: dict[str, Any],
    data_analysis_handoff: dict[str, Any],
    outline_authoring_handoff: dict[str, Any],
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    strict_build_command = [
        "python3",
        "scripts/build_workspace.py",
        "--workspace",
        str(workspace),
        "--qa",
        "--fail-on-planning-warnings",
        "--fail-on-whitespace-warnings",
        "--overwrite",
    ]
    preflight_command = [
        "python3",
        "scripts/preflight.py",
        "--outline",
        str(outline_path),
        "--asset-root",
        str(workspace),
    ]
    if design_brief_path.exists():
        preflight_command.extend(["--design-brief", str(design_brief_path)])
    slide_by_index = _slide_by_index(outline_composition)
    build_freshness = (
        last_build.get("source_freshness")
        if isinstance(last_build.get("source_freshness"), dict)
        else {}
    )
    stale_files = (
        build_freshness.get("stale_files")
        if isinstance(build_freshness.get("stale_files"), list)
        else []
    )
    if planning["error_count"]:
        metadata = _planning_recommendation_metadata(
            planning,
            severities={"error"},
        )
        recs.append(
            {
                "kind": "fix_planning_errors",
                "reason": "Planning validation has blocking errors.",
                "command": [
                    "python3",
                    "scripts/validate_planning.py",
                    "--workspace",
                    str(workspace),
                    "--report",
                    str(workspace / "build" / "planning_validation.json"),
                ],
                **metadata,
            }
        )
    elif planning["warning_count"]:
        metadata = _planning_recommendation_metadata(
            planning,
            severities={"warning"},
        )
        artifact_staleness = _generated_artifact_staleness(planning)
        if artifact_staleness.get("detected"):
            refresh_command = [
                "python3",
                "scripts/build_workspace.py",
                "--workspace",
                str(workspace),
                "--fast-first-pass",
            ]
            data_paths = _stale_artifact_data_paths(stale_files)
            for data_path in data_paths:
                refresh_command.extend(["--data-path", data_path])
            recs.append(
                {
                    "kind": "refresh_generated_artifacts",
                    "reason": "Generated figure/chart/table artifacts are stale relative to local data or producer script fingerprints; rerun the deterministic artifact producer, rebind the manifest, and rebuild the fast first pass.",
                    "command": refresh_command,
                    "data_paths": data_paths,
                    "stale_source_files": [
                        f"{item.get('name', '')}:{item.get('path', '')}:{item.get('status', '')}"
                        for item in stale_files
                        if isinstance(item, dict)
                    ],
                    "artifact_manifest": artifact_manifest_summary.get("path", "assets/artifacts_manifest.json"),
                    "analysis_summary": artifact_manifest_summary.get("analysis_summary", "assets/analysis_summary.json"),
                    "analysis_summary_markdown": artifact_manifest_summary.get("analysis_summary_markdown", "assets/analysis_summary.md"),
                    "artifact_output_ids": [
                        str(item).strip()
                        for item in artifact_manifest_summary.get("output_ids", [])
                        if str(item).strip()
                    ],
                    "artifact_aliases": _artifact_alias_labels(artifact_manifest_summary),
                    **artifact_staleness,
                    **metadata,
                }
            )
        recs.append(
            {
                "kind": "resolve_planning_warnings",
                "reason": "Reusable/report decks should clear source-planning warnings before render.",
                "command": [
                    "python3",
                    "scripts/validate_planning.py",
                    "--workspace",
                    str(workspace),
                    "--report",
                    str(workspace / "build" / "planning_validation.json"),
                ],
                **metadata,
            }
        )
    if preflight["error_count"]:
        metadata = _preflight_recommendation_metadata(
            preflight,
            slide_by_index=slide_by_index,
            severities={"error"},
        )
        recs.append(
            {
                "kind": "fix_preflight_errors",
                "reason": "Static outline preflight has blocking errors.",
                "command": preflight_command,
                **metadata,
            }
        )
    elif preflight["warning_count"]:
        metadata = _preflight_recommendation_metadata(
            preflight,
            slide_by_index=slide_by_index,
            severities={"warning"},
        )
        recs.append(
            {
                "kind": "polish_preflight_warnings",
                "reason": "Static outline preflight found layout, text, or asset warnings.",
                "command": preflight_command,
                **metadata,
            }
        )
    intake_status = str(deck_intake.get("status") or "").strip()
    intake_packet = deck_intake.get("packet") if isinstance(deck_intake.get("packet"), dict) else {}
    intake_answers = deck_intake.get("answers") if isinstance(deck_intake.get("answers"), dict) else {}
    if intake_status in {
        "deck_start_packet_invalid_json",
        "deck_start_packet_invalid",
        "intake_answers_invalid_json",
        "intake_apply_report_invalid_json",
    }:
        recs.append(
            {
                "kind": "fix_deck_intake_json",
                "reason": "The first-turn deck intake packet, answer file, or apply report is invalid; fix the JSON before continuing the reproducible deck workflow.",
                "intake_status": intake_status,
                "deck_start_packet": intake_packet.get("path", "deck_start_packet.json"),
                "intake_answers": intake_answers.get("path", "intake_answers.json"),
                "intake_error": deck_intake.get("error") or deck_intake.get("apply_error") or "",
                "suggested_fields": ["deck_start_packet.json", "intake_answers.json"],
            }
        )
    elif intake_status == "intake_answers_missing":
        recs.append(
            {
                "kind": "record_deck_intake_answers",
                "reason": "deck_start_packet.json exists but intake_answers.json has not been written; record explicit answers or best-judgment assumptions before applying the design contract.",
                "intake_status": intake_status,
                "deck_start_packet": intake_packet.get("path", "deck_start_packet.json"),
                "intake_answers": intake_answers.get("path", "intake_answers.json"),
                "answer_template": deck_intake.get("answer_template", {}),
                "questions": deck_intake.get("questions", []),
                "suggested_fields": ["intake_answers.json", "design_brief.user_intake", "notes.md"],
            }
        )
    elif intake_status in {
        "intake_answers_not_applied",
        "intake_apply_unstamped",
        "intake_apply_dry_run_only",
        "intake_answers_changed_since_apply",
    }:
        command = [
            "python3",
            "scripts/apply_deck_intake_answers.py",
            "--workspace",
            str(workspace),
        ]
        if intake_packet.get("exists"):
            command.extend(["--packet", str(_workspace_path(workspace, str(intake_packet.get("path") or "deck_start_packet.json")))])
        command.extend(
            [
                "--answers",
                str(_workspace_path(workspace, str(intake_answers.get("path") or "intake_answers.json"))),
                "--report",
                str(workspace / "intake_apply_report.json"),
            ]
        )
        recs.append(
            {
                "kind": "apply_deck_intake_answers",
                "reason": "intake_answers.json exists but has not been deterministically applied to design/evidence/asset planning sources, or the answers changed since apply.",
                "intake_status": intake_status,
                "deck_start_packet": intake_packet.get("path", "deck_start_packet.json"),
                "intake_answers": intake_answers.get("path", "intake_answers.json"),
                "intake_apply_report": "intake_apply_report.json",
                "command": command,
            }
        )
    contract_status = str(design_contract.get("status") or "").strip()
    contract = design_contract.get("contract") if isinstance(design_contract.get("contract"), dict) else {}
    if contract_status in {"contract_invalid_json", "contract_invalid"}:
        recs.append(
            {
                "kind": "fix_design_contract_json",
                "reason": "design_contract.json exists but is not valid deck_design_contract_v1 JSON; fix the contract before applying it to planning sources.",
                "design_contract_status": contract_status,
                "design_contract": contract.get("path", "design_contract.json"),
                "design_contract_error": design_contract.get("error", ""),
                "suggested_fields": ["design_contract.json"],
            }
        )
    elif contract_status in {
        "contract_not_applied",
        "contract_changed_since_apply",
        "contract_apply_unstamped",
        "contract_applied_by_unknown_tool",
    }:
        recs.append(
            {
                "kind": "apply_design_contract",
                "reason": "design_contract.json exists but has not been deterministically applied to workspace planning sources, or the applied contract is stale.",
                "design_contract_status": contract_status,
                "design_contract": contract.get("path", "design_contract.json"),
                "design_contract_apply_report": "design_contract_apply_report.json",
                "command": [
                    "python3",
                    "scripts/apply_design_contract.py",
                    "--workspace",
                    str(workspace),
                    "--contract",
                    str(_workspace_path(workspace, str(contract.get("path") or "design_contract.json"))),
                    "--report",
                    str(workspace / "design_contract_apply_report.json"),
                ],
            }
        )
    handoff_status = str(data_analysis_handoff.get("status") or "").strip()
    handoff = data_analysis_handoff.get("handoff") if isinstance(data_analysis_handoff.get("handoff"), dict) else {}
    handoff_pending_binding = False
    if handoff_status in {"handoff_invalid_json", "handoff_invalid", "apply_report_invalid_json"}:
        recs.append(
            {
                "kind": "fix_data_analysis_handoff_json",
                "reason": "data_analysis_handoff.json or its apply report is invalid JSON; fix the scout handoff before applying deterministic artifact/evidence updates.",
                "handoff_status": handoff_status,
                "handoff": handoff.get("path", "data_analysis_handoff.json"),
                "handoff_error": data_analysis_handoff.get("error") or data_analysis_handoff.get("apply_error") or "",
                "suggested_fields": ["data_analysis_handoff.json"],
            }
        )
    elif handoff_status in {
        "handoff_not_applied",
        "handoff_changed_since_apply",
        "handoff_apply_unstamped",
        "handoff_apply_dry_run_only",
        "handoff_selection_missing",
    }:
        handoff_pending_binding = int(data_analysis_handoff.get("binding_count") or 0) > 0
        recs.append(
            {
                "kind": "apply_data_analysis_handoff",
                "reason": "data_analysis_handoff.json exists but its deterministic artifact selection/evidence updates have not been applied, or the handoff changed since apply.",
                "handoff_status": handoff_status,
                "handoff": handoff.get("path", "data_analysis_handoff.json"),
                "apply_report": "data_analysis_handoff_apply_report.json",
                "selection_file": (
                    data_analysis_handoff.get("selection_file", {}).get("path", "artifact_selections.scout.json")
                    if isinstance(data_analysis_handoff.get("selection_file"), dict)
                    else "artifact_selections.scout.json"
                ),
                "command": [
                    "python3",
                    "scripts/apply_data_analysis_handoff.py",
                    "--workspace",
                    str(workspace),
                    "--handoff",
                    str(_workspace_path(workspace, str(handoff.get("path") or "data_analysis_handoff.json"))),
                    "--report",
                    str(workspace / "data_analysis_handoff_apply_report.json"),
                ],
            }
        )
    outline_handoff_status = str(outline_authoring_handoff.get("status") or "").strip()
    outline_handoff = (
        outline_authoring_handoff.get("handoff")
        if isinstance(outline_authoring_handoff.get("handoff"), dict)
        else {}
    )
    if outline_handoff_status in {"handoff_invalid_json", "handoff_invalid", "apply_report_invalid_json"}:
        recs.append(
            {
                "kind": "fix_outline_authoring_handoff_json",
                "reason": "outline_authoring_handoff.json or its apply report is invalid; fix the handoff before applying outline/content/evidence/asset source edits.",
                "outline_handoff_status": outline_handoff_status,
                "outline_handoff": outline_handoff.get("path", "outline_authoring_handoff.json"),
                "outline_handoff_error": outline_authoring_handoff.get("error") or outline_authoring_handoff.get("apply_error") or "",
                "suggested_fields": ["outline_authoring_handoff.json"],
            }
        )
    elif outline_handoff_status in {
        "handoff_not_applied",
        "handoff_changed_since_apply",
        "handoff_apply_unstamped",
        "handoff_apply_dry_run_only",
    }:
        recs.append(
            {
                "kind": "apply_outline_authoring_handoff",
                "reason": "outline_authoring_handoff.json exists but has not been deterministically applied to outline/content/evidence/asset sources, or the handoff changed since apply.",
                "outline_handoff_status": outline_handoff_status,
                "outline_handoff": outline_handoff.get("path", "outline_authoring_handoff.json"),
                "outline_handoff_apply_report": "outline_authoring_handoff_apply_report.json",
                "patch_fields": outline_authoring_handoff.get("patch_fields", []),
                "command": [
                    "python3",
                    "scripts/apply_outline_authoring_handoff.py",
                    "--workspace",
                    str(workspace),
                    "--handoff",
                    str(_workspace_path(workspace, str(outline_handoff.get("path") or "outline_authoring_handoff.json"))),
                    "--report",
                    str(workspace / "outline_authoring_handoff_apply_report.json"),
                ],
            }
        )
    style_status = str(pptx_style.get("status") or "").strip()
    reference_candidates = (
        pptx_style.get("reference_pptx_candidates")
        if isinstance(pptx_style.get("reference_pptx_candidates"), list)
        else []
    )
    extract_input_paths = [
        str(item.get("path") or "").strip()
        for item in reference_candidates
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    if style_status in {"reference_pptx_unextracted", "style_extract_stale"} and extract_input_paths:
        command = [
            "python3",
            "scripts/extract_pptx_style.py",
        ]
        for path_text in extract_input_paths:
            command.extend(["--input", str(_workspace_path(workspace, path_text))])
        command.extend(
            [
                "--report",
                str(workspace / "style_extract_report.json"),
                "--markdown-report",
                str(workspace / "style_extract_report.md"),
                "--design-brief-fragment",
                str(workspace / "style_extract_design_brief.json"),
            ]
        )
        recs.append(
            {
                "kind": "extract_pptx_style",
                "reason": "Reference PPTX style inputs exist but the reusable style extraction report/fragment is missing or stale.",
                "reference_pptx_candidates": extract_input_paths,
                "style_status": style_status,
                "style_report": "style_extract_report.json",
                "style_fragment": "style_extract_design_brief.json",
                "command": command,
            }
        )
    elif style_status in {"fragment_not_applied", "fragment_changed_since_apply", "report_not_applied"}:
        fragment = pptx_style.get("fragment") if isinstance(pptx_style.get("fragment"), dict) else {}
        report = pptx_style.get("report") if isinstance(pptx_style.get("report"), dict) else {}
        command = [
            "python3",
            "scripts/apply_pptx_style_fragment.py",
            "--workspace",
            str(workspace),
        ]
        if fragment.get("exists"):
            command.extend(["--fragment", str(_workspace_path(workspace, str(fragment.get("path") or "")))])
        elif report.get("exists"):
            command.extend(["--style-report", str(_workspace_path(workspace, str(report.get("path") or "")))])
        command.extend(["--report", str(workspace / "style_fragment_apply_report.json")])
        recs.append(
            {
                "kind": "apply_pptx_style_fragment",
                "reason": "A PPTX style extraction fragment/report exists but has not been applied to design_brief.json, or the applied fragment is stale.",
                "style_status": style_status,
                "style_report": report.get("path", ""),
                "style_fragment": fragment.get("path", ""),
                "style_apply_report": "style_fragment_apply_report.json",
                "command": command,
            }
        )
    if last_build.get("exists") and int(build_freshness.get("stale_count") or 0) > 0:
        recs.append(
            {
                "kind": "rebuild_stale_build",
                "reason": "Workspace sources changed after the last build report; rebuild before delivery or visual review.",
                "stale_source_files": [
                    f"{item.get('name', '')}:{item.get('path', '')}:{item.get('status', '')}"
                    for item in stale_files
                    if isinstance(item, dict)
                ],
                "command": strict_build_command,
            }
        )
    source_footer_issues = [
        item
        for item in preflight.get("issues", [])
        if isinstance(item, dict) and str(item.get("rule") or "") == "source_line_footer_over_budget"
    ]
    if source_footer_issues:
        slide_ids: list[str] = []
        for issue in source_footer_issues:
            slide_index = _safe_int(issue.get("slide_index"))
            slide_id = slide_by_index.get(slide_index) if slide_index is not None else ""
            if slide_id and slide_id not in slide_ids:
                slide_ids.append(slide_id)
        recs.append(
            {
                "kind": "compact_source_footers",
                "reason": "Source-line footer provenance is too long for readable small footer text; compact footer IDs and move full references to a final editable References table slide.",
                "slide_ids": slide_ids,
                "warning_types": ["source_line_footer_over_budget"],
                "source_footer_report": "build/source_footer_compaction.json",
                "command": [
                    "python3",
                    "scripts/compact_source_footers.py",
                    "--workspace",
                    str(workspace),
                    "--report",
                    str(workspace / "build" / "source_footer_compaction.json"),
                ],
            }
        )
    qa_detail = last_build.get("qa") if isinstance(last_build.get("qa"), dict) else {}
    qa_warnings = (
        qa_detail.get("whitespace_warnings")
        if isinstance(qa_detail.get("whitespace_warnings"), list)
        else []
    )
    build_current = (
        last_build.get("exists") is True
        and build_freshness.get("checked") is True
        and int(build_freshness.get("stale_count") or 0) == 0
    )
    if build_current and qa_warnings:
        enriched_warnings, slide_ids, warning_types = _enrich_qa_warnings(
            qa_warnings,
            slide_by_index=slide_by_index,
        )
        recs.append(
            {
                "kind": "polish_qa_whitespace_warnings",
                "reason": "The latest current build's QA report found awkward whitespace; patch the outline or design contract before final delivery.",
                "slide_ids": slide_ids,
                "warning_types": warning_types,
                "qa_report": qa_detail.get("path", ""),
                "qa_whitespace_warnings": enriched_warnings,
                "suggested_variants": ["image-sidebar", "chart", "lab-run-results", "table", "comparison-2col"],
                "suggested_fields": ["variant", "assets", "chart", "table", "figures", "summary_callout"],
            }
        )
    qa_design_warnings = (
        qa_detail.get("design_warnings")
        if isinstance(qa_detail.get("design_warnings"), list)
        else []
    )
    if build_current and qa_design_warnings:
        enriched_warnings, slide_ids, warning_types = _enrich_qa_warnings(
            qa_design_warnings,
            slide_by_index=slide_by_index,
        )
        suggested_fields = _enrich_qa_design_warnings(enriched_warnings)
        design_report = qa_detail.get("design_report") if isinstance(qa_detail.get("design_report"), dict) else {}
        recs.append(
            {
                "kind": "polish_qa_design_warnings",
                "reason": "The latest current build's design QA found readability or footer-reserve warnings; patch outline, chart/table specs, or readability contract before delivery.",
                "slide_ids": slide_ids,
                "warning_types": warning_types,
                "qa_report": qa_detail.get("path", ""),
                "design_report": design_report.get("path", ""),
                "qa_design_warnings": enriched_warnings,
                "suggested_variants": ["image-sidebar", "chart", "lab-run-results", "table", "comparison-2col"],
                "suggested_fields": suggested_fields or ["variant", "body", "chart.options", "table", "figures", "readability_contract"],
            }
        )
    qa_visual_warnings = (
        qa_detail.get("visual_warnings")
        if isinstance(qa_detail.get("visual_warnings"), list)
        else []
    )
    if build_current and qa_visual_warnings:
        enriched_warnings, slide_ids, warning_types = _enrich_qa_warnings(
            qa_visual_warnings,
            slide_by_index=slide_by_index,
        )
        visual_report = qa_detail.get("visual_report") if isinstance(qa_detail.get("visual_report"), dict) else {}
        visual_review_report = (
            qa_detail.get("visual_review_report")
            if isinstance(qa_detail.get("visual_review_report"), dict)
            else {}
        )
        recs.append(
            {
                "kind": "polish_qa_visual_warnings",
                "reason": "The latest current build's visual QA or visual-review packet found sparse, underfilled, or repetitive layout warnings; patch outline variants, content density, or visual anchors before delivery.",
                "slide_ids": slide_ids,
                "warning_types": warning_types,
                "qa_report": qa_detail.get("path", ""),
                "visual_report": visual_report.get("path", ""),
                "visual_review_report": visual_review_report.get("path", ""),
                "qa_visual_warnings": enriched_warnings,
                "suggested_variants": ["image-sidebar", "chart", "lab-run-results", "table", "comparison-2col", "kpi-hero"],
                "suggested_fields": ["variant", "body", "assets", "chart", "table", "figures", "stats"],
            }
        )
    build_run = last_build.get("run") if isinstance(last_build.get("run"), dict) else {}
    if build_current and build_run.get("status") == "failed":
        failed_step = str(build_run.get("failed_step") or "unknown").strip() or "unknown"
        qa_counts = last_build.get("qa_counts") if isinstance(last_build.get("qa_counts"), dict) else {}
        recs.append(
            {
                "kind": "inspect_failed_build_report",
                "reason": f"The latest current build report records a failed {failed_step} step; inspect the saved report artifacts and patch sources before delivery.",
                "failed_step": failed_step,
                "returncode": build_run.get("returncode"),
                "qa_counts": qa_counts,
                "qa_report": qa_detail.get("path", ""),
                "suggested_fields": ["variant", "body", "assets", "chart", "table", "figures", "readability_contract"],
                "command": strict_build_command,
            }
        )
    manifest_has_outputs = int(artifact_manifest_summary.get("output_count") or 0) > 0
    manifest_output_ids = [
        str(item).strip()
        for item in artifact_manifest_summary.get("output_ids", [])
        if str(item).strip()
    ]
    unbound_output_ids = artifact_selection_summary.get("unbound_output_ids")
    if not isinstance(unbound_output_ids, list):
        unbound_output_ids = []
    handoff_bound_output_ids = {
        str(item).strip()
        for item in data_analysis_handoff.get("bound_output_ids", [])
        if str(item).strip()
    }
    if handoff_bound_output_ids:
        unbound_output_ids = [
            output_id
            for output_id in (manifest_output_ids or unbound_output_ids)
            if output_id not in handoff_bound_output_ids
        ]
    handoff_selection = (
        data_analysis_handoff.get("selection_file")
        if isinstance(data_analysis_handoff.get("selection_file"), dict)
        else {}
    )
    handoff_selection_covers_manifest = bool(
        manifest_has_outputs
        and manifest_output_ids
        and handoff_bound_output_ids
        and set(manifest_output_ids).issubset(handoff_bound_output_ids)
        and handoff_selection.get("exists")
    )
    if artifact_manifest.exists() and not handoff_pending_binding and (
        (not artifact_selection.exists() and not handoff_selection_covers_manifest)
        or (manifest_has_outputs and unbound_output_ids)
    ):
        recs.append(
            {
                "kind": "bind_generated_artifacts",
                "reason": "Generated artifact manifest outputs are not fully represented in the standard auto-selection file.",
                "command": [
                    "python3",
                    "scripts/apply_artifact_manifest_bindings.py",
                    "--workspace",
                    str(workspace),
                    "--auto-select",
                    "--auto-select-mode",
                    "lead",
                    "--selection-out",
                    str(artifact_selection),
                    "--report",
                    str(workspace / "build" / "artifact_manifest_apply.json"),
                ],
            }
        )
    if tabular_data and not artifact_manifest.exists():
        command = [
            "python3",
            "scripts/build_workspace.py",
            "--workspace",
            str(workspace),
            "--fast-first-pass",
        ]
        for data_path in tabular_data:
            command.extend(["--data-path", str(data_path)])
        recs.append(
            {
                "kind": "scaffold_data_artifacts",
                "reason": "Local tabular data exists but no generated artifact manifest is present.",
                "data_paths": tabular_data,
                "command": command,
            }
        )
    signals = outline_composition.get("warning_signals")
    if not isinstance(signals, list):
        signals = []
    if "no_visual_anchors" in signals or "many_unanchored_content_slides" in signals:
        recs.append(
            {
                "kind": "add_visual_or_evidence_anchors",
                "reason": "Several content slides have no chart, table, figure, image, diagram, icon, or structural visual anchor.",
                "slide_ids": outline_composition.get("unanchored_content_slide_ids", []),
                "suggested_variants": ["image-sidebar", "chart", "lab-run-results", "table", "comparison-2col"],
            }
        )
    if "low_source_coverage" in signals:
        recs.append(
            {
                "kind": "add_source_coverage",
                "reason": "Several content slides have no sources, refs, or references; add compact provenance before final report/scientific delivery.",
                "slide_ids": outline_composition.get("missing_source_content_slide_ids", []),
                "suggested_fields": ["sources", "refs", "references", "footer"],
            }
        )
    if "dominant_variant_repetition" in signals:
        recs.append(
            {
                "kind": "review_variant_rhythm",
                "reason": "One content variant dominates the deck; confirm this is intentional or introduce a focused evidence/table/figure rhythm-breaker.",
                "dominant_variant": outline_composition.get("dominant_content_variant"),
                "dominant_ratio": outline_composition.get("dominant_content_variant_ratio"),
            }
        )
    return recs


_RECOMMENDATION_PRIORITY = {
    "fix_deck_intake_json": 5,
    "record_deck_intake_answers": 6,
    "apply_deck_intake_answers": 7,
    "apply_data_analysis_handoff": 8,
    "fix_planning_errors": 10,
    "fix_design_contract_json": 12,
    "fix_data_analysis_handoff_json": 13,
    "apply_design_contract": 15,
    "author_design_contract_from_prompt": 16,
    "fix_outline_authoring_handoff_json": 16,
    "apply_outline_authoring_handoff": 17,
    "author_outline_from_contract": 18,
    "fix_preflight_errors": 20,
    "extract_pptx_style": 22,
    "apply_pptx_style_fragment": 23,
    "refresh_generated_artifacts": 24,
    "resolve_planning_warnings": 30,
    "compact_source_footers": 35,
    "polish_preflight_warnings": 40,
    "polish_qa_design_warnings": 44,
    "polish_qa_whitespace_warnings": 45,
    "polish_qa_visual_warnings": 46,
    "inspect_failed_build_report": 49,
    "rebuild_stale_build": 50,
    "bind_generated_artifacts": 25,
    "scaffold_data_artifacts": 70,
    "add_source_coverage": 80,
    "add_visual_or_evidence_anchors": 90,
    "review_variant_rhythm": 100,
}


def _next_action(recommendations: list[dict[str, Any]]) -> dict[str, Any]:
    if not recommendations:
        return {
            "kind": "none",
            "priority": 0,
            "action_type": "none",
            "reason": "No source-level action required before build/QA.",
        }
    indexed = [
        (
            _RECOMMENDATION_PRIORITY.get(str(item.get("kind") or ""), 1000),
            index,
            item,
        )
        for index, item in enumerate(recommendations)
        if isinstance(item, dict)
    ]
    if not indexed:
        return {
            "kind": "none",
            "priority": 0,
            "action_type": "none",
            "reason": "No parseable readiness recommendations were emitted.",
        }
    priority, _index, selected = sorted(indexed, key=lambda item: (item[0], item[1]))[0]
    action = dict(selected)
    action["priority"] = priority
    if action.get("kind") in {
        "fix_deck_intake_json",
        "record_deck_intake_answers",
        "author_design_contract_from_prompt",
        "author_outline_from_contract",
        "fix_planning_errors",
        "fix_data_analysis_handoff_json",
        "fix_outline_authoring_handoff_json",
        "resolve_planning_warnings",
        "fix_preflight_errors",
        "polish_preflight_warnings",
        "inspect_failed_build_report",
    }:
        action["action_type"] = "edit_sources"
    else:
        action["action_type"] = "run_command" if _command_text(action.get("command")) else "edit_sources"
    return action


def _source_files(workspace: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    build_dir = workspace / str(manifest.get("build_dir", "build"))
    data_apply_report = workspace / "data_analysis_handoff_apply_report.json"
    legacy_data_apply_report = build_dir / "data_analysis_handoff_apply.json"
    if not data_apply_report.exists() and legacy_data_apply_report.exists():
        data_apply_report = legacy_data_apply_report
    data_handoff_payload = _load_json(workspace / "data_analysis_handoff.json", {})
    data_apply_payload = _load_json(data_apply_report, {}) if data_apply_report.exists() else {}
    data_selection = _data_analysis_handoff_selection_file(
        workspace,
        data_handoff_payload,
        data_apply_payload,
    )
    files = {
        "workspace": workspace / "workspace.json",
        "style_contract": workspace / str(manifest.get("style_contract", "style_contract.json")),
        "deck_start_packet": workspace / "deck_start_packet.json",
        "intake_answers": workspace / "intake_answers.json",
        "intake_apply_report": workspace / "intake_apply_report.json",
        "design_contract": workspace / "design_contract.json",
        "design_contract_apply_report": workspace / "design_contract_apply_report.json",
        "style_extract_report": workspace / "style_extract_report.json",
        "style_extract_design_brief": workspace / "style_extract_design_brief.json",
        "style_fragment_apply_report": workspace / "style_fragment_apply_report.json",
        "data_analysis_handoff": workspace / "data_analysis_handoff.json",
        "data_analysis_handoff_apply_report": data_apply_report,
        "data_analysis_handoff_selection": data_selection,
        "outline_authoring_handoff": workspace / "outline_authoring_handoff.json",
        "outline_authoring_handoff_apply_report": workspace / "outline_authoring_handoff_apply_report.json",
        "artifact_selection": workspace / "artifact_selections.auto.json",
        "artifact_manifest_apply_report": build_dir / "artifact_manifest_apply.json",
        "design_brief": workspace / str(manifest.get("design_brief", "design_brief.json")),
        "content_plan": workspace / str(manifest.get("content_plan", "content_plan.json")),
        "evidence_plan": workspace / str(manifest.get("evidence_plan", "evidence_plan.json")),
        "asset_plan": workspace / str(manifest.get("asset_plan", "asset_plan.json")),
        "outline": workspace / str(manifest.get("outline", "outline.json")),
    }
    snapshots = {
        name: {"path": _display_path(workspace, path), "exists": path.exists()}
        for name, path in files.items()
    }
    snapshots.update(
        _artifact_dependency_source_files(
            workspace,
            workspace / "assets" / "artifacts_manifest.json",
        )
    )
    return snapshots


def _count_pair(section: dict[str, Any]) -> str:
    return f"{section.get('error_count', 0)}/{section.get('warning_count', 0)}"


def _markdown_list(values: Any, *, empty: str = "none") -> str:
    if not isinstance(values, list) or not values:
        return empty
    return ", ".join(str(item) for item in values if str(item).strip()) or empty


def _markdown_code_list(values: Any, *, empty: str = "none") -> str:
    if not isinstance(values, list) or not values:
        return empty
    text_values = [str(item).strip().replace("`", "'") for item in values]
    text_values = [item for item in text_values if item]
    if not text_values:
        return empty
    return ", ".join(f"`{item}`" for item in text_values)


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


def _limited_markdown_list(values: Any, *, limit: int = 6, empty: str = "none") -> str:
    if not isinstance(values, list) or not values:
        return empty
    items = [str(item).strip() for item in values if str(item).strip()]
    if not items:
        return empty
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def _data_handoff_ledger_markdown_lines(data_handoff: Any) -> list[str]:
    if not isinstance(data_handoff, dict):
        return []
    ledger = data_handoff.get("applied_ledger")
    if not isinstance(ledger, dict) or not ledger:
        return []
    lines = [
        "- Data handoff ledger: "
        f"outputs=`{_limited_markdown_list(ledger.get('bound_output_ids'))}` "
        f"slides=`{_limited_markdown_list(ledger.get('slide_ids'))}` "
        f"variants=`{_limited_markdown_list(ledger.get('variants'))}` "
        f"evidence=`{_limited_markdown_list(ledger.get('evidence_ids'))}`"
    ]
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
    storyboard = data_handoff.get("artifact_storyboard")
    if isinstance(storyboard, dict) and int(storyboard.get("item_count") or 0):
        lines.append(
            "- Data handoff storyboard: "
            f"items=`{int(storyboard.get('item_count') or 0)}` "
            f"slides=`{_limited_markdown_list(storyboard.get('slide_ids'))}` "
            f"outputs=`{_limited_markdown_list(storyboard.get('output_ids'))}` "
            f"roles=`{_limited_markdown_list(storyboard.get('artifact_roles'))}` "
            f"sources=`{_limited_markdown_list(storyboard.get('data_source_paths'), limit=3)}`"
        )
    return lines


def _data_handoff_rebuild_markdown_lines(data_handoff: Any) -> list[str]:
    if not isinstance(data_handoff, dict):
        return []
    rebuild = data_handoff.get("artifact_rebuild_context")
    if not isinstance(rebuild, dict):
        return []
    return [
        "- Data artifact rebuild: "
        f"present=`{bool(rebuild.get('present'))}` "
        f"persisted=`{bool(rebuild.get('persisted'))}` "
        f"context=`{rebuild.get('context_version', '')}` "
        f"commands=`{rebuild.get('command_count', 0)}`"
    ]


def _data_handoff_contract_markdown_lines(data_handoff: Any) -> list[str]:
    if not isinstance(data_handoff, dict):
        return []
    contracts = data_handoff.get("artifact_contracts")
    if not isinstance(contracts, dict) or not contracts:
        return []
    asset_counts = contracts.get("asset_plan_update_counts")
    asset_counts = asset_counts if isinstance(asset_counts, dict) else {}
    return [
        "- Data artifact contracts: "
        f"figure_export=`{bool(contracts.get('figure_export_contract_applied'))}` "
        f"figure_outputs=`{int(contracts.get('figure_export_output_count') or 0)}` "
        f"registry_updates=`{int(contracts.get('artifact_registry_update_count') or 0)}` "
        f"asset_updates=`{json.dumps(asset_counts, sort_keys=True)}`"
    ]


def _data_handoff_scout_markdown_lines(data_handoff: Any) -> list[str]:
    if not isinstance(data_handoff, dict):
        return []
    scout = data_handoff.get("scout_analysis")
    if not isinstance(scout, dict) or not scout:
        return []
    return [
        "- Data scout analysis: "
        f"present=`{bool(scout.get('present'))}` "
        f"persisted=`{bool(scout.get('persisted'))}` "
        f"tasks=`{int(scout.get('analysis_task_count') or 0)}` "
        f"findings=`{int(scout.get('computed_finding_count') or 0)}` "
        f"visuals=`{int(scout.get('visual_recommendation_count') or 0)}` "
        f"bindings=`{int(scout.get('outline_binding_count') or 0)}` "
        f"targets=`{_limited_markdown_list(scout.get('target_slide_ids'), limit=4)}` "
        f"variants=`{_limited_markdown_list(scout.get('variants'), limit=4)}` "
        f"open_questions=`{int(scout.get('open_question_count') or 0)}`"
    ]


def _build_data_handoff_ledger_markdown_lines(data_handoff: Any) -> list[str]:
    if not isinstance(data_handoff, dict):
        return []
    ledger = data_handoff.get("applied_ledger")
    if not isinstance(ledger, dict) or not ledger:
        return []
    lines = [
        "- Last build data handoff ledger: "
        f"outputs=`{_limited_markdown_list(ledger.get('bound_output_ids'))}` "
        f"slides=`{_limited_markdown_list(ledger.get('slide_ids'))}` "
        f"variants=`{_limited_markdown_list(ledger.get('variants'))}` "
        f"evidence=`{_limited_markdown_list(ledger.get('evidence_ids'))}`"
    ]
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


def _command_text(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(item) for item in command)
    return str(command or "").strip()


def _recommendation_detail_lines(item: dict[str, Any]) -> list[str]:
    detail_fields = [
        ("slide_ids", "Slide IDs"),
        ("suggested_variants", "Suggested variants"),
        ("suggested_fields", "Suggested fields"),
        ("planning_paths", "Planning paths"),
        ("stale_source_files", "Stale source files"),
        ("warning_types", "Warning types"),
        ("qa_report", "QA report"),
        ("design_report", "Design report"),
        ("visual_report", "Visual report"),
        ("visual_review_report", "Visual review report"),
        ("reference_pptx_candidates", "Reference PPTX"),
        ("data_paths", "Data paths"),
        ("style_status", "PPTX style status"),
        ("style_report", "Style report"),
        ("style_fragment", "Style fragment"),
        ("style_apply_report", "Style apply report"),
        ("intake_status", "Deck intake status"),
        ("deck_start_packet", "Deck start packet"),
        ("intake_answers", "Intake answers"),
        ("intake_apply_report", "Intake apply report"),
        ("intake_error", "Intake error"),
        ("design_contract_status", "Design contract status"),
        ("design_contract", "Design contract"),
        ("design_contract_apply_report", "Design contract apply report"),
        ("design_contract_error", "Design contract error"),
        ("outline_handoff_status", "Outline handoff status"),
        ("outline_handoff", "Outline handoff"),
        ("outline_handoff_apply_report", "Outline handoff apply report"),
        ("outline_handoff_error", "Outline handoff error"),
        ("patch_fields", "Patch fields"),
        ("current_phase_id", "Execution phase"),
        ("outline_status", "Outline status"),
        ("content_slide_count", "Content slide count"),
        ("source_footer_report", "Source-footer report"),
        ("failed_step", "Failed step"),
        ("returncode", "Return code"),
        ("dominant_variant", "Dominant variant"),
        ("dominant_ratio", "Dominant ratio"),
    ]
    lines: list[str] = []
    for key, label in detail_fields:
        value = item.get(key)
        if isinstance(value, list):
            text = _markdown_list(value)
        else:
            text = str(value).strip() if value is not None else ""
        if text and text != "none":
            lines.append(f"  {label}: {text}")
    return lines


def _readiness_markdown(report: dict[str, Any]) -> str:
    style = report.get("style") if isinstance(report.get("style"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    planning = checks.get("planning") if isinstance(checks.get("planning"), dict) else {}
    preflight = checks.get("preflight") if isinstance(checks.get("preflight"), dict) else {}
    composition = (
        report.get("outline_composition")
        if isinstance(report.get("outline_composition"), dict)
        else {}
    )
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    pptx_style = report.get("pptx_style") if isinstance(report.get("pptx_style"), dict) else {}
    deck_intake = (
        report.get("deck_intake")
        if isinstance(report.get("deck_intake"), dict)
        else {}
    )
    intake_choice_seed = (
        deck_intake.get("choice_resolution_seed")
        if isinstance(deck_intake.get("choice_resolution_seed"), dict)
        else {}
    )
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
    contract_quality = (
        design_contract.get("slide_quality_contract")
        if isinstance(design_contract.get("slide_quality_contract"), dict)
        else {}
    )
    contract_choice = (
        design_contract.get("choice_resolution")
        if isinstance(design_contract.get("choice_resolution"), dict)
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
    contract_replay = (
        design_contract.get("reproducibility_contract")
        if isinstance(design_contract.get("reproducibility_contract"), dict)
        else {}
    )
    contract_replay_style = (
        contract_replay.get("style_replay")
        if isinstance(contract_replay.get("style_replay"), dict)
        else {}
    )
    data_handoff = (
        report.get("data_analysis_handoff")
        if isinstance(report.get("data_analysis_handoff"), dict)
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
    execution_plan = (
        report.get("execution_plan")
        if isinstance(report.get("execution_plan"), dict)
        else {}
    )
    phase_proof = (
        execution_plan.get("phase_proof_ledger")
        if isinstance(execution_plan.get("phase_proof_ledger"), dict)
        else {}
    )
    manifest = (
        artifacts.get("artifact_manifest")
        if isinstance(artifacts.get("artifact_manifest"), dict)
        else {}
    )
    manifest_commands = manifest.get("commands") if isinstance(manifest.get("commands"), dict) else {}
    selection = (
        artifacts.get("artifact_selection")
        if isinstance(artifacts.get("artifact_selection"), dict)
        else {}
    )
    last_build = report.get("last_build") if isinstance(report.get("last_build"), dict) else {}
    last_build_qa = last_build.get("qa") if isinstance(last_build.get("qa"), dict) else {}
    last_build_data_handoff = (
        last_build.get("data_analysis_handoff")
        if isinstance(last_build.get("data_analysis_handoff"), dict)
        else {}
    )
    build_freshness = (
        last_build.get("source_freshness")
        if isinstance(last_build.get("source_freshness"), dict)
        else {}
    )
    recommendations = report.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    next_action = report.get("next_action")
    if not isinstance(next_action, dict):
        next_action = {}
    source_files = (
        report.get("source_files") if isinstance(report.get("source_files"), dict) else {}
    )
    missing_source_files = [
        str(item.get("path") or name)
        for name, item in source_files.items()
        if isinstance(item, dict) and not item.get("exists")
    ]
    next_commands = (
        report.get("next_commands") if isinstance(report.get("next_commands"), dict) else {}
    )

    lines = [
        "# Workspace Readiness",
        "",
        f"- Workspace: `{report.get('workspace', '')}`",
        f"- Status: `{report.get('status', '')}`",
        f"- Status reasons: `{_markdown_list(report.get('status_reasons'))}`",
        f"- Planning errors/warnings: `{_count_pair(planning)}`",
        f"- Planning issue keys: {_markdown_code_list(planning.get('issue_keys'))}",
        f"- Preflight errors/warnings: `{_count_pair(preflight)}`",
        f"- Preflight issue keys: {_markdown_code_list(preflight.get('issue_keys'))}",
        f"- Recommendations: `{len(recommendations)}`",
        f"- Next action: `{next_action.get('kind', 'none')}`",
        "",
        "## Style",
        "",
        f"- Resolved preset: `{style.get('resolved_style_preset', '')}`",
        f"- Style seed: `{style.get('style_seed') or 'none'}`",
        f"- Header variant: `{(style.get('resolved_deck_style') or {}).get('header_variant', 'none') if isinstance(style.get('resolved_deck_style'), dict) else 'none'}`",
        f"- Footer mode: `{(style.get('resolved_deck_style') or {}).get('footer_mode', 'none') if isinstance(style.get('resolved_deck_style'), dict) else 'none'}`",
        *_style_mix_markdown_lines(style.get("style_mix_matrix")),
        *_resolved_treatment_markdown_lines(style),
        f"- Deck intake status: `{deck_intake.get('status', 'none')}` applied=`{bool(deck_intake.get('applied'))}`",
        f"- Deck start packet: `{(deck_intake.get('packet') or {}).get('path', '') if isinstance(deck_intake.get('packet'), dict) else ''}` exists=`{bool((deck_intake.get('packet') or {}).get('exists')) if isinstance(deck_intake.get('packet'), dict) else False}`",
        f"- Intake answers: `{(deck_intake.get('answers') or {}).get('path', '') if isinstance(deck_intake.get('answers'), dict) else ''}` exists=`{bool((deck_intake.get('answers') or {}).get('exists')) if isinstance(deck_intake.get('answers'), dict) else False}` answer_count=`{deck_intake.get('answer_count', 0)}` unanswered=`{_markdown_list(deck_intake.get('unanswered'))}`",
        f"- Intake choice seed: exists=`{bool(intake_choice_seed.get('exists'))}` choices=`{_markdown_list(intake_choice_seed.get('choice_ids'))}` active_routes=`{_markdown_list(intake_choice_seed.get('active_routes'))}`",
        *_source_inventory_markdown_lines(deck_intake),
        f"- Execution plan: `{execution_plan.get('plan_version', '') or 'none'}` current=`{execution_plan.get('current_phase_id', '') or execution_plan.get('current_phase_status', 'none')}` required=`{execution_plan.get('completed_required_count', 0)}/{execution_plan.get('required_phase_count', 0)}`",
        f"- Execution route-required phases: `{_markdown_list(execution_plan.get('required_by_route_ledger'))}` visual_review_required=`{bool(execution_plan.get('rendered_visual_review_required'))}`",
        f"- Phase proof ledger: `{phase_proof.get('ledger_version', '') or 'none'}` valid=`{bool(phase_proof.get('valid'))}` gates=`{phase_proof.get('acceptance_gate_count', 0)}` proof_paths=`{phase_proof.get('proof_path_count', 0)}` files=`{phase_proof.get('existing_file_count', 0)}/{phase_proof.get('proof_file_count', 0)}` missing=`{phase_proof.get('missing_file_count', 0)}` route_required=`{_markdown_list(phase_proof.get('route_required_phase_ids'))}`",
        f"- Execution phase command: `{execution_plan.get('current_phase_command_key', '') or 'none'}` `{execution_plan.get('current_phase_command_text', '')}`",
        f"- Design contract status: `{design_contract.get('status', 'none')}` applied=`{bool(design_contract.get('applied'))}`",
        f"- Design contract: `{(design_contract.get('contract') or {}).get('path', '') if isinstance(design_contract.get('contract'), dict) else ''}` exists=`{bool((design_contract.get('contract') or {}).get('exists')) if isinstance(design_contract.get('contract'), dict) else False}`",
        f"- Contract QA checks: `{contract_qa.get('required_check_count', 0)}` fail_on=`{_markdown_list(contract_qa.get('fail_on'))}` placeholders=`{bool(contract_qa.get('placeholder_checks'))}`",
        "- Contract slide quality: "
        f"exists=`{bool(contract_quality.get('exists'))}` "
        f"version=`{contract_quality.get('contract_version', '') or 'none'}` "
        f"title=`{contract_quality.get('min_title_pt', '')}` "
        f"body=`{contract_quality.get('min_body_pt', '')}` "
        f"chart=`{contract_quality.get('chart_label_min_pt', '')}` "
        f"footer=`{contract_quality.get('footer_reserved_inches', '')}` "
        f"whitespace=`{bool(contract_quality.get('fail_on_awkward_whitespace'))}` "
        f"evidence_anchor=`{bool(contract_quality.get('evidence_anchor_required'))}` "
        f"commands=`{contract_quality.get('required_command_count', 0)}`",
        f"- Contract choice resolution: exists=`{bool(contract_choice.get('exists'))}` choices=`{_markdown_list(contract_choice.get('choice_ids'))}` active_routes=`{_markdown_list(contract_choice.get('active_routes'))}`",
        f"- Contract replay: exists=`{bool(contract_replay.get('exists'))}` seed=`{contract_replay.get('style_seed', '')}` renderer=`{contract_replay.get('renderer', '')}` commands=`{contract_replay.get('replay_command_count', 0)}` locked_fields=`{contract_replay.get('locked_design_field_count', 0)}`",
        f"- Contract replay style: preset=`{contract_replay_style.get('style_preset', '')}` background=`{contract_replay_style.get('background_system', '')}` headers=`{_markdown_list(contract_replay_style.get('header_variant_pool'))}` charts=`{_markdown_list(contract_replay_style.get('chart_treatment_pool'))}` figures=`{_markdown_list(contract_replay_style.get('figure_table_treatment_pool'))}`",
        f"- Contract acceptance evidence: `{contract_acceptance.get('existing_file_count', 0)}/{contract_acceptance.get('file_count', 0)}` files exist, missing=`{_markdown_list(contract_acceptance.get('missing_files'))}`",
        f"- Contract agent phases: `{_markdown_list(contract_agent_plan.get('phase_ids'))}` commands=`{contract_agent_plan.get('command_count', 0)}`",
        f"- Data analysis handoff status: `{data_handoff.get('status', 'none')}` applied=`{bool(data_handoff.get('applied'))}`",
        f"- Data analysis handoff: `{(data_handoff.get('handoff') or {}).get('path', '') if isinstance(data_handoff.get('handoff'), dict) else ''}` exists=`{bool((data_handoff.get('handoff') or {}).get('exists')) if isinstance(data_handoff.get('handoff'), dict) else False}` selections=`{data_handoff.get('selection_count', 0)}` script_edits=`{data_handoff.get('script_edit_count', 0)}`",
        *_data_handoff_ledger_markdown_lines(data_handoff),
        *_data_handoff_rebuild_markdown_lines(data_handoff),
        *_data_handoff_contract_markdown_lines(data_handoff),
        *_data_handoff_scout_markdown_lines(data_handoff),
        f"- Outline authoring handoff status: `{outline_handoff.get('status', 'none')}` applied=`{bool(outline_handoff.get('applied'))}`",
        f"- Outline authoring handoff: `{(outline_handoff.get('handoff') or {}).get('path', '') if isinstance(outline_handoff.get('handoff'), dict) else ''}` exists=`{bool((outline_handoff.get('handoff') or {}).get('exists')) if isinstance(outline_handoff.get('handoff'), dict) else False}` patch_fields=`{_markdown_list(outline_handoff.get('patch_fields'))}`",
        f"- Outline artifact rebuild: present=`{bool((outline_handoff.get('artifact_rebuild_plan') or {}).get('present')) if isinstance(outline_handoff.get('artifact_rebuild_plan'), dict) else False}` persisted=`{bool((outline_handoff.get('artifact_rebuild_plan') or {}).get('persisted')) if isinstance(outline_handoff.get('artifact_rebuild_plan'), dict) else False}` context=`{(outline_handoff.get('artifact_rebuild_plan') or {}).get('context_version', '') if isinstance(outline_handoff.get('artifact_rebuild_plan'), dict) else ''}` commands=`{(outline_handoff.get('artifact_rebuild_plan') or {}).get('command_count', 0) if isinstance(outline_handoff.get('artifact_rebuild_plan'), dict) else 0}`",
        "- Outline quality alignment: "
        f"present=`{bool(outline_quality.get('present'))}` "
        f"persisted=`{bool(outline_quality.get('persisted'))}` "
        f"version=`{outline_quality.get('contract_version', '')}` "
        f"readability=`{outline_quality.get('readability_target_count', 0)}` "
        f"layout=`{outline_quality.get('layout_target_count', 0)}` "
        f"qa=`{outline_quality.get('qa_gate_count', 0)}` "
        f"commands=`{outline_quality.get('required_command_count', 0)}`",
        f"- PPTX style status: `{pptx_style.get('status', 'none')}`",
        f"- Reference PPTX candidates: `{len(pptx_style.get('reference_pptx_candidates') or []) if isinstance(pptx_style.get('reference_pptx_candidates'), list) else 0}`",
        f"- Style extraction report: `{(pptx_style.get('report') or {}).get('path', '') if isinstance(pptx_style.get('report'), dict) else ''}` exists=`{bool((pptx_style.get('report') or {}).get('exists')) if isinstance(pptx_style.get('report'), dict) else False}`",
        f"- Style fragment: `{(pptx_style.get('fragment') or {}).get('path', '') if isinstance(pptx_style.get('fragment'), dict) else ''}` exists=`{bool((pptx_style.get('fragment') or {}).get('exists')) if isinstance(pptx_style.get('fragment'), dict) else False}` applied=`{bool(pptx_style.get('applied'))}`",
        "",
        "## Composition",
        "",
        f"- Slides/content slides: `{composition.get('slide_count', 0)}/{composition.get('content_slide_count', 0)}`",
        f"- Content variants: `{json.dumps(composition.get('content_variant_counts', {}), sort_keys=True)}`",
        f"- Visual anchors: `{json.dumps(composition.get('visual_anchor_counts', {}), sort_keys=True)}`",
        f"- Unanchored content slide IDs: `{_markdown_list(composition.get('unanchored_content_slide_ids'))}`",
        f"- Content slides without sources: `{_markdown_list(composition.get('missing_source_content_slide_ids'))}`",
        f"- Warning signals: `{_markdown_list(composition.get('warning_signals'))}`",
        f"- Missing source files: `{_markdown_list(missing_source_files)}`",
        "",
        "## Artifacts",
        "",
        f"- Artifact manifest: `{manifest.get('path', '')}` exists=`{bool(manifest.get('exists'))}` outputs=`{manifest.get('output_count', 0)}`",
        f"- Analysis summary: `{manifest.get('analysis_summary') or ''}` markdown=`{manifest.get('analysis_summary_markdown') or ''}`",
        f"- Output IDs: `{_markdown_list(manifest.get('output_ids'))}`",
        *_artifact_context_markdown_lines(manifest, selection),
        f"- Selection templates: `{manifest.get('selection_template_count', 0)}`",
        f"- Auto-bind command: `{_command_text(manifest_commands.get('auto_select_lead') or manifest_commands.get('auto_select_all'))}`",
        f"- Artifact selection: `{selection.get('path', '')}` exists=`{bool(selection.get('exists'))}` bindings=`{selection.get('binding_count', 0)}`",
        f"- Unbound output IDs: `{_markdown_list(selection.get('unbound_output_ids'))}`",
        f"- Tabular data: `{_markdown_list(artifacts.get('tabular_data'))}`",
        "",
        "## Last Build",
        "",
        f"- Build report: `{last_build.get('path', '')}` exists=`{bool(last_build.get('exists'))}`",
        f"- Build status: `{last_build.get('run_status') or 'unknown'}` returncode=`{last_build.get('returncode')}` failed_step=`{last_build.get('failed_step') or ''}`",
        _build_speed_markdown_line(last_build.get("speed")),
        f"- PPTX exists: `{last_build.get('pptx_exists')}`",
        f"- Source freshness checked: `{bool(build_freshness.get('checked'))}`",
        f"- Stale source files: `{int(build_freshness.get('stale_count') or 0)}`",
        f"- Last build data handoff: status=`{last_build_data_handoff.get('status') or 'none'}` applied=`{bool(last_build_data_handoff.get('applied'))}` selections=`{last_build_data_handoff.get('selection_count') or 0}` outputs=`{_markdown_list(last_build_data_handoff.get('bound_output_ids'))}`",
        *_build_data_handoff_ledger_markdown_lines(last_build_data_handoff),
        f"- QA whitespace warnings: `{int(last_build_qa.get('whitespace_warning_count') or 0)}`",
        f"- QA design warnings: `{int(last_build_qa.get('design_warning_count') or 0)}`",
        f"- QA visual warnings: `{int(last_build_qa.get('visual_warning_count') or 0)}`",
        f"- QA visual-review warnings: `{int(last_build_qa.get('visual_review_warning_count') or 0)}`",
        "",
        "## Next Action",
        "",
        f"- `{next_action.get('kind', 'none')}`: {next_action.get('reason', '')}",
    ]
    stale_files = (
        build_freshness.get("stale_files")
        if isinstance(build_freshness.get("stale_files"), list)
        else []
    )
    if stale_files:
        insert_at = lines.index("## Next Action") - 1
        stale_lines = []
        for item in stale_files:
            if not isinstance(item, dict):
                continue
            stale_lines.append(
                f"- `{item.get('name', '')}` `{item.get('path', '')}`: `{item.get('status', '')}`"
            )
        if stale_lines:
            lines[insert_at:insert_at] = stale_lines + [""]
    if next_action.get("kind") and next_action.get("kind") != "none":
        lines.extend(_recommendation_detail_lines(next_action))
    next_action_command = _command_text(next_action.get("command"))
    if next_action_command:
        lines.append(f"  Command: `{next_action_command}`")
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
        ]
    )
    if recommendations:
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            lines.append(f"- `{item.get('kind', '')}`: {item.get('reason', '')}")
            lines.extend(_recommendation_detail_lines(item))
            command = _command_text(item.get("command"))
            if command:
                lines.append(f"  Command: `{command}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Next Commands", ""])
    if next_commands:
        for name, command in next_commands.items():
            command_text = _command_text(command)
            if command_text:
                lines.append(f"- `{name}`: `{command_text}`")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fast source-only readiness checks for a deck workspace."
    )
    parser.add_argument("--workspace", required=True, help="Workspace created by init_deck_workspace.py")
    parser.add_argument(
        "--report",
        default="build/workspace_readiness.json",
        help="Workspace-relative or absolute path for the combined readiness report.",
    )
    parser.add_argument(
        "--markdown-report",
        default="build/workspace_readiness.md",
        help="Workspace-relative or absolute path for the human-readable readiness summary.",
    )
    parser.add_argument(
        "--skip-markdown",
        action="store_true",
        help="Do not write build/workspace_readiness.md.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print the JSON readiness report but do not write JSON or Markdown reports to disk.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 2

    scripts_dir = Path(__file__).resolve().parent
    py = sys.executable
    manifest = _load_json(workspace / "workspace.json", {})
    if not isinstance(manifest, dict):
        manifest = {}
    build_dir = workspace / str(manifest.get("build_dir", "build"))
    outline_path = workspace / str(manifest.get("outline", "outline.json"))
    design_brief_path = workspace / str(manifest.get("design_brief", "design_brief.json"))
    style_contract_path = workspace / str(manifest.get("style_contract", "style_contract.json"))

    planning_rc, planning_payload, planning_stderr = _run_json(
        [
            py,
            str(scripts_dir / "validate_planning.py"),
            "--workspace",
            str(workspace),
        ]
    )
    preflight_cmd = [
        py,
        str(scripts_dir / "preflight.py"),
        "--outline",
        str(outline_path),
        "--asset-root",
        str(workspace),
    ]
    if design_brief_path.exists():
        preflight_cmd.extend(["--design-brief", str(design_brief_path)])
    preflight_rc, preflight_payload, preflight_stderr = _run_json(preflight_cmd)

    planning_summary = _check_summary(planning_payload, key_field="path")
    preflight_summary = _check_summary(preflight_payload, key_field="rule")
    artifact_manifest = workspace / "assets" / "artifacts_manifest.json"
    artifact_selection = workspace / "artifact_selections.auto.json"
    artifact_manifest_info = _artifact_manifest_summary(workspace, artifact_manifest)
    manifest_output_ids = [
        str(item)
        for item in artifact_manifest_info.get("output_ids", [])
        if str(item).strip()
    ]
    artifact_selection_info = _artifact_selection_summary(
        workspace,
        artifact_selection,
        output_ids=manifest_output_ids,
    )
    outline_composition = _outline_composition(workspace, outline_path)
    tabular_data = _tabular_data_paths(workspace)
    artifact_context = _artifact_context_summary(
        artifact_manifest_summary=artifact_manifest_info,
        artifact_selection_summary=artifact_selection_info,
        tabular_data=tabular_data,
    )
    source_files = _source_files(workspace, manifest)
    last_build = _existing_build_report(
        workspace,
        build_dir,
        current_source_files=source_files,
    )
    pptx_style = _pptx_style_summary(
        workspace=workspace,
        build_dir=build_dir,
        design_brief_path=design_brief_path,
    )
    deck_intake = _deck_intake_summary(
        workspace=workspace,
        design_brief_path=design_brief_path,
    )
    design_contract = _design_contract_summary(
        workspace=workspace,
        design_brief_path=design_brief_path,
    )
    data_analysis_handoff = _data_analysis_handoff_summary(workspace)
    outline_authoring_handoff = _outline_authoring_handoff_summary(workspace)
    quality_context = _quality_context_summary(
        design_contract=design_contract,
        outline_authoring_handoff=outline_authoring_handoff,
    )
    recommendations = _recommendations(
        workspace=workspace,
        outline_path=outline_path,
        design_brief_path=design_brief_path,
        planning=planning_summary,
        preflight=preflight_summary,
        artifact_manifest=artifact_manifest,
        artifact_selection=artifact_selection,
        artifact_manifest_summary=artifact_manifest_info,
        artifact_selection_summary=artifact_selection_info,
        outline_composition=outline_composition,
        last_build=last_build,
        tabular_data=tabular_data,
        pptx_style=pptx_style,
        deck_intake=deck_intake,
        design_contract=design_contract,
        data_analysis_handoff=data_analysis_handoff,
        outline_authoring_handoff=outline_authoring_handoff,
    )
    next_action = _next_action(recommendations)
    execution_plan = _deck_execution_plan_progress(
        workspace=workspace,
        deck_intake=deck_intake,
        design_contract=design_contract,
        pptx_style=pptx_style,
        data_analysis_handoff=data_analysis_handoff,
        artifact_manifest_summary=artifact_manifest_info,
        artifact_selection_summary=artifact_selection_info,
        outline_composition=outline_composition,
        planning=planning_summary,
        preflight=preflight_summary,
        last_build=last_build,
        recommendations=recommendations,
        next_action=next_action,
    )
    phase_recommendations = _execution_phase_recommendations(
        execution_plan=execution_plan,
        outline_composition=outline_composition,
        design_contract=design_contract,
    )
    if phase_recommendations:
        recommendations = [*recommendations, *phase_recommendations]
        next_action = _next_action(recommendations)
        execution_plan = _deck_execution_plan_progress(
            workspace=workspace,
            deck_intake=deck_intake,
            design_contract=design_contract,
            pptx_style=pptx_style,
            data_analysis_handoff=data_analysis_handoff,
            artifact_manifest_summary=artifact_manifest_info,
            artifact_selection_summary=artifact_selection_info,
            outline_composition=outline_composition,
            planning=planning_summary,
            preflight=preflight_summary,
            last_build=last_build,
            recommendations=recommendations,
            next_action=next_action,
        )

    blocking_errors = planning_summary["error_count"] + preflight_summary["error_count"]
    warning_count = planning_summary["warning_count"] + preflight_summary["warning_count"]
    recommendation_count = len(recommendations)
    status_reasons: list[str] = []
    if blocking_errors:
        status = "blocked"
        exit_code = 2
        status_reasons.append("blocking_errors")
    else:
        if warning_count:
            status_reasons.append("validator_warnings")
        if recommendation_count:
            status_reasons.append("open_recommendations")
        if status_reasons:
            status = "needs_attention"
            exit_code = 1
        else:
            status = "ready"
            exit_code = 0
            status_reasons.append("clean")

    data_artifact_build_command = [
        "python3",
        "scripts/build_workspace.py",
        "--workspace",
        str(workspace),
        "--scaffold-data-artifacts",
        "--auto-bind-artifacts",
        "--artifact-bind-mode",
        "lead",
        "--qa",
        "--skip-render",
        "--fail-on-planning-warnings",
        "--fail-on-whitespace-warnings",
        "--overwrite",
    ]
    for data_path in tabular_data:
        data_artifact_build_command.extend(["--data-path", str(data_path)])

    fast_first_pass_build_command = [
        "python3",
        "scripts/build_workspace.py",
        "--workspace",
        str(workspace),
        "--qa",
        "--skip-render",
        "--fail-on-planning-warnings",
        "--fail-on-whitespace-warnings",
        "--overwrite",
    ]

    next_commands = {
        "readiness": [
            "python3",
            "scripts/report_workspace_readiness.py",
            "--workspace",
            str(workspace),
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
        "fast_first_pass_build": fast_first_pass_build_command,
        "data_artifact_build": data_artifact_build_command,
        "delivery_audit": [
            "python3",
            "scripts/report_delivery_readiness.py",
            "--workspace",
            str(workspace),
        ],
    }
    reference_pptx_paths = [
        str(item.get("path") or "").strip()
        for item in pptx_style.get("reference_pptx_candidates", [])
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    if reference_pptx_paths:
        style_extract_command = [
            "python3",
            "scripts/extract_pptx_style.py",
        ]
        for path_text in reference_pptx_paths:
            style_extract_command.extend(["--input", str(_workspace_path(workspace, path_text))])
        style_extract_command.extend(
            [
                "--report",
                str(workspace / "style_extract_report.json"),
                "--markdown-report",
                str(workspace / "style_extract_report.md"),
                "--design-brief-fragment",
                str(workspace / "style_extract_design_brief.json"),
            ]
        )
        next_commands["style_extract"] = style_extract_command

    style_fragment = pptx_style.get("fragment") if isinstance(pptx_style.get("fragment"), dict) else {}
    style_report = pptx_style.get("report") if isinstance(pptx_style.get("report"), dict) else {}
    if style_fragment.get("exists") or style_report.get("exists"):
        style_apply_command = [
            "python3",
            "scripts/apply_pptx_style_fragment.py",
            "--workspace",
            str(workspace),
        ]
        if style_fragment.get("exists"):
            style_apply_command.extend(
                ["--fragment", str(_workspace_path(workspace, str(style_fragment.get("path") or "")))]
            )
        else:
            style_apply_command.extend(
                ["--style-report", str(_workspace_path(workspace, str(style_report.get("path") or "")))]
            )
        style_apply_command.extend(["--report", str(workspace / "style_fragment_apply_report.json")])
        next_commands["style_apply"] = style_apply_command

    intake_packet = deck_intake.get("packet") if isinstance(deck_intake.get("packet"), dict) else {}
    intake_answers = deck_intake.get("answers") if isinstance(deck_intake.get("answers"), dict) else {}
    if intake_answers.get("exists"):
        intake_apply_command = [
            "python3",
            "scripts/apply_deck_intake_answers.py",
            "--workspace",
            str(workspace),
        ]
        if intake_packet.get("exists"):
            intake_apply_command.extend(
                ["--packet", str(_workspace_path(workspace, str(intake_packet.get("path") or "deck_start_packet.json")))]
            )
        intake_apply_command.extend(
            [
                "--answers",
                str(_workspace_path(workspace, str(intake_answers.get("path") or "intake_answers.json"))),
                "--report",
                str(workspace / "intake_apply_report.json"),
            ]
        )
        next_commands["intake_answers_apply"] = intake_apply_command
    design_prompt_command = str(deck_intake.get("design_contract_prompt_command") or "").strip()
    if design_prompt_command:
        next_commands["design_contract_prompt"] = design_prompt_command

    contract = design_contract.get("contract") if isinstance(design_contract.get("contract"), dict) else {}
    if contract.get("exists"):
        next_commands["design_contract_apply"] = [
            "python3",
            "scripts/apply_design_contract.py",
            "--workspace",
            str(workspace),
            "--contract",
            str(_workspace_path(workspace, str(contract.get("path") or "design_contract.json"))),
            "--report",
            str(workspace / "design_contract_apply_report.json"),
        ]
    handoff = data_analysis_handoff.get("handoff") if isinstance(data_analysis_handoff.get("handoff"), dict) else {}
    if handoff.get("exists"):
        next_commands["data_analysis_handoff_apply"] = [
            "python3",
            "scripts/apply_data_analysis_handoff.py",
            "--workspace",
            str(workspace),
            "--handoff",
            str(_workspace_path(workspace, str(handoff.get("path") or "data_analysis_handoff.json"))),
            "--report",
            str(workspace / "data_analysis_handoff_apply_report.json"),
        ]
    outline_handoff = (
        outline_authoring_handoff.get("handoff")
        if isinstance(outline_authoring_handoff.get("handoff"), dict)
        else {}
    )
    if outline_handoff.get("exists"):
        next_commands["outline_authoring_handoff_apply"] = [
            "python3",
            "scripts/apply_outline_authoring_handoff.py",
            "--workspace",
            str(workspace),
            "--handoff",
            str(_workspace_path(workspace, str(outline_handoff.get("path") or "outline_authoring_handoff.json"))),
            "--report",
            str(workspace / "outline_authoring_handoff_apply_report.json"),
        ]
    next_commands["outline_authoring_prompt"] = [
        "python3",
        "scripts/emit_outline_authoring_prompt.py",
        "--workspace",
        str(workspace),
        "--output",
        str(workspace / "build" / "outline_authoring_prompt.md"),
    ]

    execution_plan = _attach_execution_phase_command(execution_plan, next_commands)

    report = {
        "schema_version": 1,
        "workspace": str(workspace),
        "status": status,
        "status_reasons": status_reasons,
        "source_files": source_files,
        "style": _style_preview(
            workspace=workspace,
            style_contract_path=style_contract_path,
            design_brief_path=design_brief_path,
            outline_path=outline_path,
        ),
        "outline_composition": outline_composition,
        "checks": {
            "planning": {
                "returncode": planning_rc,
                **planning_summary,
                "stderr_tail": planning_stderr[-1200:],
            },
            "preflight": {
                "returncode": preflight_rc,
                **preflight_summary,
                "stderr_tail": preflight_stderr[-1200:],
            },
        },
        "artifacts": {
            "artifact_manifest": artifact_manifest_info,
            "artifact_selection": artifact_selection_info,
            "tabular_data": tabular_data,
        },
        "artifact_context": artifact_context,
        "deck_intake": deck_intake,
        "design_contract": design_contract,
        "quality_context": quality_context,
        "data_analysis_handoff": data_analysis_handoff,
        "outline_authoring_handoff": outline_authoring_handoff,
        "pptx_style": pptx_style,
        "execution_plan": execution_plan,
        "last_build": last_build,
        "recommendations": recommendations,
        "next_action": next_action,
        "next_commands": next_commands,
    }

    print(json.dumps(report, indent=2))
    if not args.no_write:
        report_path = _workspace_path(workspace, args.report)
        _write_json_if_changed(report_path, report)
        print(
            f"[workspace_readiness] report: {_display_path(workspace, report_path)}",
            file=sys.stderr,
        )
        if not args.skip_markdown:
            markdown_path = _workspace_path(workspace, args.markdown_report)
            _write_text_if_changed(markdown_path, _readiness_markdown(report))
            print(
                f"[workspace_readiness] markdown: {_display_path(workspace, markdown_path)}",
                file=sys.stderr,
            )
    print(
        "[workspace_readiness] "
        f"status={status} planning={planning_summary['error_count']}/"
        f"{planning_summary['warning_count']} preflight={preflight_summary['error_count']}/"
        f"{preflight_summary['warning_count']} recommendations={len(recommendations)}",
        file=sys.stderr,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
