#!/usr/bin/env python3
"""Fast smoke for QA whitespace/readability source-edit handoffs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _run_checked(
    cmd: list[str],
    *,
    cwd: Path,
    command_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    allowed_returncodes: set[int] | None = None,
) -> None:
    allowed = allowed_returncodes if allowed_returncodes is not None else {0}
    result = _run(cmd, cwd=cwd)
    command_results.append(
        {
            "command": cmd,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-1600:],
        }
    )
    if result.returncode not in allowed:
        failures.append({"step": Path(cmd[1]).name, "returncode": result.returncode})


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _file_snapshot(workspace: Path, path: Path) -> dict[str, Any]:
    try:
        display_path = str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        display_path = str(path.resolve())
    snapshot: dict[str, Any] = {
        "path": display_path,
        "exists": path.exists(),
    }
    if path.exists() and path.is_file():
        payload = path.read_bytes()
        snapshot["size_bytes"] = len(payload)
        snapshot["sha256"] = hashlib.sha256(payload).hexdigest()
    return snapshot


def _source_file_snapshots(workspace: Path) -> dict[str, dict[str, Any]]:
    candidates = {
        "workspace": workspace / "workspace.json",
        "style_contract": workspace / "style_contract.json",
        "design_brief": workspace / "design_brief.json",
        "content_plan": workspace / "content_plan.json",
        "evidence_plan": workspace / "evidence_plan.json",
        "asset_plan": workspace / "asset_plan.json",
        "outline": workspace / "outline.json",
    }
    return {
        name: _file_snapshot(workspace, path)
        for name, path in candidates.items()
        if path.exists()
    }


def _patch_design_brief(workspace: Path, *, seed: str) -> None:
    path = workspace / "design_brief.json"
    brief = _load_json(path)
    if not isinstance(brief, dict):
        brief = {}
    style_system = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    style_system["style_preset"] = "lab-report"
    style_system["style_seed"] = seed
    style_system["style_mix_matrix"] = {
        "header_variant_pool": ["plain", "top-bottom-rule"],
        "figure_table_treatment_pool": ["figure-first", "table-first"],
        "footer_pool": ["source-line", "standard"],
        "mix_rule": "Keep QA polish handoff fixtures reproducible.",
    }
    brief["style_system"] = style_system
    renderer_treatments = brief.get("renderer_treatments") if isinstance(brief.get("renderer_treatments"), dict) else {}
    renderer_treatments["header_mode"] = "lab-clean"
    renderer_treatments["header_variant"] = "auto"
    renderer_treatments["footer_mode"] = "source-line"
    renderer_treatments["footer_page_numbers"] = True
    brief["renderer_treatments"] = renderer_treatments
    brief["format_promise"] = "Clean lab-report source-edit handoff fixture."
    _write_json(path, brief)


def _write_fixture_sources(
    workspace: Path,
    *,
    title: str,
    slide_id: str,
    slide_title: str,
    slide_body: str,
    seed: str,
) -> None:
    _patch_design_brief(workspace, seed=seed)
    outline = {
        "title": title,
        "deck_style": {
            "header_mode": "lab-clean",
            "header_variant": "auto",
            "footer_mode": "source-line",
            "footer_page_numbers": True,
        },
        "slides": [
            {
                "slide_id": "s1",
                "type": "title",
                "title": title,
                "subtitle": "Synthetic fixture for saved QA polish warnings",
            },
            {
                "slide_id": slide_id,
                "type": "content",
                "variant": "standard",
                "title": slide_title,
                "body": [slide_body],
                "sources": ["Synthetic QA report"],
            },
        ],
    }
    _write_json(workspace / "outline.json", outline)

    content_plan = _load_json(workspace / "content_plan.json")
    if not isinstance(content_plan, dict):
        content_plan = {}
    content_plan["thesis"] = "Readiness should turn saved QA polish warnings into source edits."
    content_plan["slide_plan"] = [
        {
            "slide_id": "s1",
            "role": "title",
            "message": "Open the QA polish fixture.",
            "variant": "title",
            "visual_strategy": "title",
            "evidence_needs": [],
        },
        {
            "slide_id": slide_id,
            "role": "evidence",
            "message": "Saved QA telemetry marks this slide for source-level polish.",
            "variant": "standard",
            "visual_strategy": "source-backed text summary",
            "evidence_needs": [],
        },
    ]
    content_plan["narrative_arc"] = [
        {
            "label": "QA polish",
            "slides": [slide_id],
            "purpose": "Exercise post-build QA polish readiness.",
        }
    ]
    _write_json(workspace / "content_plan.json", content_plan)


def _write_synthetic_current_build_report(
    workspace: Path,
    *,
    slide_id: str,
    whitespace_warning: bool,
    design_warning: bool,
) -> None:
    qa_dir = workspace / "build" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    whitespace_warnings: list[dict[str, Any]] = []
    if whitespace_warning:
        whitespace_warnings.append(
            {
                "type": "content_span_too_short",
                "severity": "warning",
                "slide_index": 1,
                "slide_id": slide_id,
                "slide_type": "content",
                "variant": "standard",
                "shape_id": "content-block",
                "content_span_height_ratio": 0.22,
                "max_vertical_dead_ratio": 0.58,
                "suggested_fix": (
                    "Enlarge the evidence block, add a visual/table/sidebar, "
                    "or choose an intentional sparse variant."
                ),
            }
        )

    design_warnings: list[dict[str, Any]] = []
    if design_warning:
        design_warnings.append(
            {
                "slide_index": 1,
                "slide_id": slide_id,
                "shape_id": "shape-2",
                "type": "body_font_too_small",
                "severity": "warning",
                "role": "body",
                "font_pt": 8.0,
                "min_allowed_pt": 12.0,
                "text": "Synthetic text is below the readable body threshold.",
            }
        )

    design_report = qa_dir / "design_rules.json"
    _write_json(
        design_report,
        {
            "issue_count": len(design_warnings),
            "error_count": 0,
            "warning_count": len(design_warnings),
            "issues": design_warnings,
            "passed": not design_warnings,
        },
    )
    visual_report = qa_dir / "visual_qa.json"
    _write_json(visual_report, [])

    qa_report = {
        "whitespace_warning_count": len(whitespace_warnings),
        "geometry_warning_count": len(whitespace_warnings),
        "geometry_error_count": 0,
        "overflow_count": 0,
        "overlap_count": 0,
        "design_error_count": 0,
        "design_warning_count": len(design_warnings),
        "design_report": str(design_report),
        "visual_warning_count": 0,
        "visual_report": str(visual_report),
        "visual_review_warning_count": 0,
        "whitespace_warnings": whitespace_warnings,
    }
    _write_json(qa_dir / "report.json", qa_report)

    build_report = {
        "schema_version": 1,
        "workspace": str(workspace),
        "run": {
            "status": "succeeded",
            "returncode": 0,
            "failed_step": "",
            "step_returncodes": {},
        },
        "style_preset": "lab-report",
        "renderer": {"requested": "auto", "used": "pptxgenjs"},
        "source_files": _source_file_snapshots(workspace),
        "outputs": {
            "pptx": {"path": "build/deck.pptx", "exists": False},
            "build_dir": "build",
        },
        "reports": {
            "qa": {
                "path": "build/qa/report.json",
                "exists": True,
                "counts": {
                    "whitespace_warning_count": len(whitespace_warnings),
                    "geometry_warning_count": len(whitespace_warnings),
                    "geometry_error_count": 0,
                    "overflow_count": 0,
                    "overlap_count": 0,
                    "design_error_count": 0,
                    "design_warning_count": len(design_warnings),
                    "visual_warning_count": 0,
                    "visual_review_warning_count": 0,
                },
            }
        },
    }
    _write_json(workspace / "build" / "build_workspace_report.json", build_report)


def _write_synthetic_delivery_density_report(
    workspace: Path,
    *,
    slide_id: str,
) -> None:
    qa_dir = workspace / "build" / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    qa_report = {
        "whitespace_warning_count": 0,
        "geometry_warning_count": 0,
        "geometry_error_count": 0,
        "overflow_count": 0,
        "overlap_count": 0,
        "design_error_count": 0,
        "design_warning_count": 0,
        "visual_warning_count": 0,
        "visual_review_warning_count": 0,
        "whitespace_warnings": [],
        "density_score_by_slide": [
            {"slide_index": 0, "density_score": 0.36},
            {"slide_index": 1, "density_score": 0.32},
        ],
    }
    _write_json(qa_dir / "report.json", qa_report)

    deck_path = workspace / "build" / "deck.pptx"
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_bytes(b"synthetic-pptx-for-delivery-density-smoke\n")

    quality_context = {
        "slide_quality_contract": {
            "exists": True,
            "contract_version": "slide_quality_contract_v1",
            "min_title_pt": 24,
            "min_body_pt": 12,
            "chart_label_min_pt": 7,
            "footer_reserved_inches": 0.25,
            "evidence_anchor_required": True,
            "fail_on_awkward_whitespace": True,
            "required_command_count": 4,
        },
        "outline_quality_alignment": {
            "present": True,
            "persisted": True,
            "contract_version": "slide_quality_contract_v1",
            "readability_target_count": 4,
            "layout_target_count": 4,
            "qa_gate_count": 3,
            "required_command_count": 4,
        },
    }
    source_files = _source_file_snapshots(workspace)
    build_report = {
        "schema_version": 1,
        "workspace": str(workspace),
        "run": {
            "status": "succeeded",
            "returncode": 0,
            "failed_step": "",
            "step_returncodes": {},
        },
        "style_preset": "lab-report",
        "renderer": {"requested": "auto", "used": "pptxgenjs"},
        "source_files": source_files,
        "options": {
            "qa": True,
            "skip_render": True,
            "visual_review": False,
            "fast_first_pass": False,
            "fail_on_planning_warnings": True,
            "fail_on_whitespace_warnings": True,
            "overwrite": True,
        },
        "outputs": {
            "pptx": _file_snapshot(workspace, deck_path),
            "build_dir": "build",
        },
        "reports": {
            "qa": {
                "path": "build/qa/report.json",
                "exists": True,
                "counts": {
                    "whitespace_warning_count": 0,
                    "geometry_warning_count": 0,
                    "geometry_error_count": 0,
                    "overflow_count": 0,
                    "overlap_count": 0,
                    "design_error_count": 0,
                    "design_warning_count": 0,
                    "visual_warning_count": 0,
                    "visual_review_warning_count": 0,
                },
            }
        },
        "quality_context": quality_context,
    }
    _write_json(workspace / "build" / "build_workspace_report.json", build_report)
    _write_json(
        workspace / "build" / "workspace_readiness.json",
        {
            "status": "ready",
            "status_reasons": [],
            "next_action": {},
            "source_files": source_files,
            "quality_context": quality_context,
            "notes": f"Synthetic readiness for {slide_id} low-density delivery handoff.",
        },
    )


def _init_case(repo: Path, workspace: Path, title: str, command_results: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    _run_checked(
        [
            sys.executable,
            str(repo / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            title,
            "--style-preset",
            "lab-report",
        ],
        cwd=repo,
        command_results=command_results,
        failures=failures,
    )


def _run_readiness_and_advance(
    repo: Path,
    workspace: Path,
    command_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    _run_checked(
        [
            sys.executable,
            str(repo / "scripts" / "report_workspace_readiness.py"),
            "--workspace",
            str(workspace),
        ],
        cwd=repo,
        command_results=command_results,
        failures=failures,
        allowed_returncodes={0, 1},
    )
    _run_checked(
        [
            sys.executable,
            str(repo / "scripts" / "advance_workspace.py"),
            "--workspace",
            str(workspace),
            "--max-steps",
            "1",
        ],
        cwd=repo,
        command_results=command_results,
        failures=failures,
        allowed_returncodes={0, 1},
    )
    readiness = _load_json(workspace / "build" / "workspace_readiness.json")
    advance = _load_json(workspace / "build" / "workspace_advance_report.json")
    prompt_path = workspace / "build" / "workspace_next_action.md"
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    return (
        readiness if isinstance(readiness, dict) else {},
        advance if isinstance(advance, dict) else {},
        prompt,
    )


def _run_delivery_and_advance(
    repo: Path,
    workspace: Path,
    command_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    _run_checked(
        [
            sys.executable,
            str(repo / "scripts" / "report_delivery_readiness.py"),
            "--workspace",
            str(workspace),
            "--allow-skip-render",
            "--no-refresh-readiness",
        ],
        cwd=repo,
        command_results=command_results,
        failures=failures,
        allowed_returncodes={0, 1},
    )
    _run_checked(
        [
            sys.executable,
            str(repo / "scripts" / "advance_delivery.py"),
            "--workspace",
            str(workspace),
            "--allow-skip-render",
            "--no-refresh-readiness",
        ],
        cwd=repo,
        command_results=command_results,
        failures=failures,
        allowed_returncodes={0, 1},
    )
    delivery = _load_json(workspace / "build" / "delivery_readiness.json")
    advance = _load_json(workspace / "build" / "delivery_advance_report.json")
    prompt_path = workspace / "build" / "delivery_next_action.md"
    prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    return (
        delivery if isinstance(delivery, dict) else {},
        advance if isinstance(advance, dict) else {},
        prompt,
    )


def _assert_whitespace_case(
    *,
    readiness: dict[str, Any],
    advance: dict[str, Any],
    prompt: str,
    failures: list[dict[str, Any]],
) -> None:
    next_action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    source_edit_plan = advance.get("source_edit_plan") if isinstance(advance.get("source_edit_plan"), list) else []
    first_edit = source_edit_plan[0] if source_edit_plan and isinstance(source_edit_plan[0], dict) else {}
    if readiness.get("status") != "needs_attention":
        failures.append({"case": "whitespace", "step": "readiness", "status": readiness.get("status")})
    if next_action.get("kind") != "polish_qa_whitespace_warnings":
        failures.append({"case": "whitespace", "step": "readiness", "next_action": next_action})
    if next_action.get("slide_ids") != ["q1"] or next_action.get("warning_types") != ["content_span_too_short"]:
        failures.append(
            {
                "case": "whitespace",
                "step": "readiness",
                "slide_ids": next_action.get("slide_ids"),
                "warning_types": next_action.get("warning_types"),
            }
        )
    if advance.get("decision") != "edit_sources_required":
        failures.append({"case": "whitespace", "step": "advance", "decision": advance.get("decision")})
    if first_edit.get("slide_id") != "q1" or first_edit.get("operation") != "rebalance_content_or_change_variant":
        failures.append({"case": "whitespace", "step": "source_edit_plan", "first_edit": first_edit})
    if first_edit.get("report_source") != "qa_whitespace":
        failures.append({"case": "whitespace", "step": "source_edit_plan", "report_source": first_edit.get("report_source")})
    if first_edit.get("content_span_height_ratio") != 0.22 or first_edit.get("max_vertical_dead_ratio") != 0.58:
        failures.append({"case": "whitespace", "step": "source_edit_plan", "measurements": first_edit})
    for field in ("variant", "summary_callout", "chart", "table", "figures"):
        if field not in first_edit.get("suggested_fields", []):
            failures.append({"case": "whitespace", "step": "source_edit_plan", "missing_field": field})
    if "Enlarge the evidence block" not in str(first_edit.get("suggested_fix") or ""):
        failures.append({"case": "whitespace", "step": "source_edit_plan", "reason": "missing_suggested_fix"})
    for needle in (
        "Slide IDs: `q1`",
        "Warning types: `content_span_too_short`",
        "span height ratio: 0.22",
        "vertical dead ratio: 0.58",
        "`outline.json` `slides[1]` slide `q1`: `rebalance_content_or_change_variant`",
    ):
        if needle not in prompt:
            failures.append({"case": "whitespace", "step": "prompt", "missing": needle})


def _assert_design_case(
    *,
    readiness: dict[str, Any],
    advance: dict[str, Any],
    prompt: str,
    failures: list[dict[str, Any]],
) -> None:
    next_action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    source_edit_plan = advance.get("source_edit_plan") if isinstance(advance.get("source_edit_plan"), list) else []
    first_edit = source_edit_plan[0] if source_edit_plan and isinstance(source_edit_plan[0], dict) else {}
    if readiness.get("status") != "needs_attention":
        failures.append({"case": "design", "step": "readiness", "status": readiness.get("status")})
    if next_action.get("kind") != "polish_qa_design_warnings":
        failures.append({"case": "design", "step": "readiness", "next_action": next_action})
    if next_action.get("slide_ids") != ["d1"] or next_action.get("warning_types") != ["body_font_too_small"]:
        failures.append(
            {
                "case": "design",
                "step": "readiness",
                "slide_ids": next_action.get("slide_ids"),
                "warning_types": next_action.get("warning_types"),
            }
        )
    if advance.get("decision") != "edit_sources_required":
        failures.append({"case": "design", "step": "advance", "decision": advance.get("decision")})
    if first_edit.get("slide_id") != "d1" or first_edit.get("operation") != "increase_text_size_or_reduce_text":
        failures.append({"case": "design", "step": "source_edit_plan", "first_edit": first_edit})
    if first_edit.get("report_source") != "qa_design" or first_edit.get("role") != "body":
        failures.append({"case": "design", "step": "source_edit_plan", "first_edit": first_edit})
    if first_edit.get("font_pt") != 8.0 or first_edit.get("min_allowed_pt") != 12.0:
        failures.append({"case": "design", "step": "source_edit_plan", "measurements": first_edit})
    for field in ("body", "readability_contract.min_body_pt"):
        if field not in first_edit.get("suggested_fields", []):
            failures.append({"case": "design", "step": "source_edit_plan", "missing_field": field})
    suggested_fix = str(first_edit.get("suggested_fix") or "")
    if "8.0pt" not in suggested_fix or "12.0pt" not in suggested_fix:
        failures.append({"case": "design", "step": "source_edit_plan", "suggested_fix": suggested_fix})
    for needle in (
        "Slide IDs: `d1`",
        "Warning types: `body_font_too_small`",
        "`outline.json` `slides[1]` slide `d1`: `increase_text_size_or_reduce_text`",
        "font pt: 8.0",
        "min pt: 12.0",
    ):
        if needle not in prompt:
            failures.append({"case": "design", "step": "prompt", "missing": needle})


def _assert_delivery_density_case(
    *,
    delivery: dict[str, Any],
    advance: dict[str, Any],
    prompt: str,
    failures: list[dict[str, Any]],
) -> None:
    next_action = delivery.get("recommended_next_action") if isinstance(delivery.get("recommended_next_action"), dict) else {}
    density = delivery.get("layout_density") if isinstance(delivery.get("layout_density"), dict) else {}
    gates = delivery.get("gates") if isinstance(delivery.get("gates"), dict) else {}
    source_edit_plan = advance.get("source_edit_plan") if isinstance(advance.get("source_edit_plan"), list) else []
    first_edit = source_edit_plan[0] if source_edit_plan and isinstance(source_edit_plan[0], dict) else {}
    if delivery.get("delivery_status") != "needs_attention":
        failures.append({"case": "delivery-density", "step": "delivery", "status": delivery.get("delivery_status")})
    if delivery.get("warning_reasons") != ["layout_density_low"]:
        failures.append({"case": "delivery-density", "step": "delivery", "warning_reasons": delivery.get("warning_reasons")})
    if gates.get("layout_density_contract_required") is not True or gates.get("layout_density_floor_satisfied") is not False:
        failures.append({"case": "delivery-density", "step": "delivery", "gates": gates})
    if density.get("low_content_density_count") != 1 or density.get("low_content_density_slides") != [{"slide_index": 1, "density_score": 0.32}]:
        failures.append({"case": "delivery-density", "step": "delivery", "layout_density": density})
    if next_action.get("kind") != "inspect_delivery_warnings" or "layout_density_low" not in next_action.get("warning_types", []):
        failures.append({"case": "delivery-density", "step": "delivery", "next_action": next_action})
    for field in ("variant", "summary_callout", "chart", "table", "figures", "quality_alignment.layout_targets_used"):
        if field not in next_action.get("suggested_fields", []):
            failures.append({"case": "delivery-density", "step": "delivery", "missing_field": field})
    if next_action.get("slide_ids") != ["slide_index:1"]:
        failures.append({"case": "delivery-density", "step": "delivery", "slide_ids": next_action.get("slide_ids")})
    if advance.get("decision") != "edit_sources_required":
        failures.append({"case": "delivery-density", "step": "advance", "decision": advance.get("decision")})
    if first_edit.get("slide_id") != "ld1" or first_edit.get("operation") != "add_visual_anchor_or_reduce_dead_space":
        failures.append({"case": "delivery-density", "step": "source_edit_plan", "first_edit": first_edit})
    if first_edit.get("report_source") != "qa_whitespace":
        failures.append({"case": "delivery-density", "step": "source_edit_plan", "report_source": first_edit.get("report_source")})
    if first_edit.get("visual_density_score") != 0.32 or first_edit.get("empty_ratio") != 0.68:
        failures.append({"case": "delivery-density", "step": "source_edit_plan", "measurements": first_edit})
    suggested_fix = str(first_edit.get("suggested_fix") or "")
    if "below the floor 0.55" not in suggested_fix or "visual/evidence anchor" not in suggested_fix:
        failures.append({"case": "delivery-density", "step": "source_edit_plan", "suggested_fix": suggested_fix})
    for needle in (
        "Warning types: `layout_density_low`",
        "## Layout Density",
        "low=`1`",
        "`outline.json` `slides[1]` slide `ld1`: `add_visual_anchor_or_reduce_dead_space`",
        "density: 0.32",
        "empty ratio: 0.68",
    ):
        if needle not in prompt:
            failures.append({"case": "delivery-density", "step": "prompt", "missing": needle})


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a focused layout-polish handoff smoke check.")
    parser.add_argument("--workspace", default="", help="Workspace parent to create/use. Defaults to a temporary parent.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep the temporary workspace after a passing run.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    root = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-layout-polish-"))
    )
    if root.exists() and any(root.iterdir()):
        print(
            json.dumps(
                {
                    "passed": False,
                    "workspace": str(root),
                    "failures": [{"step": "workspace", "reason": "workspace_must_be_empty"}],
                },
                indent=2,
            )
        )
        return 1
    root.mkdir(parents=True, exist_ok=True)

    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    summary_path = root / "layout_polish_handoff_smoke.json"
    passed = False

    try:
        whitespace_workspace = root / "qa-whitespace"
        _init_case(repo, whitespace_workspace, "Layout Polish QA Whitespace Smoke", command_results, failures)
        _write_fixture_sources(
            whitespace_workspace,
            title="Layout Polish QA Whitespace Smoke",
            slide_id="q1",
            slide_title="Sparse evidence slide needs layout polish",
            slide_body="Short sourced readout intentionally represented by saved QA telemetry.",
            seed="layout-polish-whitespace",
        )
        _write_synthetic_current_build_report(
            whitespace_workspace,
            slide_id="q1",
            whitespace_warning=True,
            design_warning=False,
        )
        whitespace_readiness, whitespace_advance, whitespace_prompt = _run_readiness_and_advance(
            repo,
            whitespace_workspace,
            command_results,
            failures,
        )
        _assert_whitespace_case(
            readiness=whitespace_readiness,
            advance=whitespace_advance,
            prompt=whitespace_prompt,
            failures=failures,
        )

        design_workspace = root / "qa-design"
        _init_case(repo, design_workspace, "Layout Polish QA Design Smoke", command_results, failures)
        _write_fixture_sources(
            design_workspace,
            title="Layout Polish QA Design Smoke",
            slide_id="d1",
            slide_title="Readable body text warning should become an edit plan",
            slide_body="Saved design QA marks this body text as below the readable threshold.",
            seed="layout-polish-design",
        )
        _write_synthetic_current_build_report(
            design_workspace,
            slide_id="d1",
            whitespace_warning=False,
            design_warning=True,
        )
        design_readiness, design_advance, design_prompt = _run_readiness_and_advance(
            repo,
            design_workspace,
            command_results,
            failures,
        )
        _assert_design_case(
            readiness=design_readiness,
            advance=design_advance,
            prompt=design_prompt,
            failures=failures,
        )

        density_workspace = root / "delivery-density"
        _init_case(repo, density_workspace, "Layout Polish Delivery Density Smoke", command_results, failures)
        _write_fixture_sources(
            density_workspace,
            title="Layout Polish Delivery Density Smoke",
            slide_id="ld1",
            slide_title="Underfilled content slide should block clean delivery",
            slide_body="Short readout intentionally represented by delivery layout-density telemetry.",
            seed="layout-polish-delivery-density",
        )
        _write_synthetic_delivery_density_report(
            density_workspace,
            slide_id="ld1",
        )
        density_delivery, density_advance, density_prompt = _run_delivery_and_advance(
            repo,
            density_workspace,
            command_results,
            failures,
        )
        _assert_delivery_density_case(
            delivery=density_delivery,
            advance=density_advance,
            prompt=density_prompt,
            failures=failures,
        )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(root),
            "whitespace": {
                "workspace": str(whitespace_workspace),
                "status": whitespace_readiness.get("status"),
                "next_action": whitespace_readiness.get("next_action", {}),
                "source_edit_plan_count": len(whitespace_advance.get("source_edit_plan", []))
                if isinstance(whitespace_advance.get("source_edit_plan"), list)
                else 0,
            },
            "design": {
                "workspace": str(design_workspace),
                "status": design_readiness.get("status"),
                "next_action": design_readiness.get("next_action", {}),
                "source_edit_plan_count": len(design_advance.get("source_edit_plan", []))
                if isinstance(design_advance.get("source_edit_plan"), list)
                else 0,
            },
            "delivery_density": {
                "workspace": str(density_workspace),
                "status": density_delivery.get("delivery_status"),
                "warning_reasons": density_delivery.get("warning_reasons"),
                "next_action": density_delivery.get("recommended_next_action", {}),
                "layout_density": density_delivery.get("layout_density", {}),
                "source_edit_plan_count": len(density_advance.get("source_edit_plan", []))
                if isinstance(density_advance.get("source_edit_plan"), list)
                else 0,
            },
            "failures": failures,
            "commands": command_results,
        }
        _write_json(summary_path, summary)
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "whitespace",
                        "design",
                        "delivery_density",
                        "failures",
                    )
                },
                indent=2,
            )
        )
        _cleanup_workspace(root, created_temp=created_temp, keep=args.keep_workspace, passed=passed)
        return 0 if passed else 1
    except Exception as exc:
        failures.append({"step": "smoke", "reason": str(exc)})
        summary = {
            "passed": False,
            "workspace": str(root),
            "failures": failures,
            "commands": command_results,
        }
        try:
            _write_json(summary_path, summary)
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
