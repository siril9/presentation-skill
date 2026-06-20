#!/usr/bin/env python3
"""Smoke check for rendered chart/table readability-contract handoffs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Set


EXPECTED_WARNING_TYPES = ["table_font_too_small", "chart_label_font_too_small"]
EXPECTED_SLIDE_IDS = ["table_probe", "chart_probe"]


def _run(
    cmd: list[str],
    *,
    cwd: Path,
    allowed_returncodes: Optional[Set[int]] = None,
) -> subprocess.CompletedProcess[str]:
    allowed = {0} if allowed_returncodes is None else allowed_returncodes
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode not in allowed:
        raise RuntimeError(f"{Path(cmd[1]).name} failed with return code {result.returncode}")
    return result


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _patch_readability_contract(workspace: Path) -> None:
    path = workspace / "design_brief.json"
    brief = _load_json(path)
    deck_style = brief.get("deck_style") if isinstance(brief.get("deck_style"), dict) else {}
    deck_style["title_layout"] = "light-atlas"
    brief["deck_style"] = deck_style
    brief["readability_contract"] = {
        "min_title_pt": 24,
        "min_body_pt": 12,
        "min_caption_pt": 8,
        "chart_label_min_pt": 8,
        "footer_reserved_inches": 0.3,
        "table_density_rule": "Keep table text at or above caption floor; split dense tables.",
        "whitespace_rule": "Fill evidence regions without crowding.",
        "figure_crop_rule": "Trim figure exterior whitespace.",
    }
    _write_json(path, brief)


def _write_fixture_sources(workspace: Path) -> None:
    _patch_readability_contract(workspace)
    outline = {
        "title": "Readability Contract Smoke",
        "slides": [
            {
                "slide_id": "s1",
                "type": "title",
                "title": "Readability Contract Smoke",
                "subtitle": "Rendered chart and table text must meet the contract",
            },
            {
                "slide_id": "chart_probe",
                "type": "content",
                "variant": "chart",
                "title": "Tiny chart axis labels trigger QA",
                "caption": "Synthetic chart fixture with intentionally undersized axis labels.",
                "sources": ["Synthetic CSV"],
                "chart": {
                    "type": "bar",
                    "series": [
                        {
                            "name": "Signal",
                            "labels": ["Alpha long label", "Beta long label", "Gamma long label"],
                            "values": [12, 18, 9],
                        }
                    ],
                    "options": {
                        "catAxisLabelFontSize": 6,
                        "valAxisLabelFontSize": 6,
                        "showLegend": False,
                    },
                },
            },
            {
                "slide_id": "table_probe",
                "type": "content",
                "variant": "table",
                "title": "Tiny table cells trigger QA",
                "headers": ["Sample", "Signal", "Ct"],
                "rows": [
                    ["A01", "41.2", "18.4"],
                    ["A02", "38.9", "19.1"],
                    ["B01", "27.4", "24.8"],
                ],
                "sources": ["Synthetic CSV"],
                "row_styles": {
                    "0": {"fontSize": 6},
                    "1": {"fontSize": 6},
                    "2": {"fontSize": 6},
                },
                "header_style": {"fontSize": 6},
                "caption": "Synthetic table readability fixture.",
            },
        ],
    }
    _write_json(workspace / "outline.json", outline)

    content_plan = {
        "thesis": "Readable chart and table text are delivery gates.",
        "audience": "QA smoke",
        "slide_plan": [
            {
                "slide_id": "s1",
                "role": "title",
                "message": "Open the readability fixture.",
                "variant": "title",
                "visual_strategy": "title",
                "evidence_needs": [],
            },
            {
                "slide_id": "chart_probe",
                "role": "evidence",
                "message": "Chart labels are too small.",
                "variant": "chart",
                "visual_strategy": "native chart",
                "evidence_needs": ["chart"],
            },
            {
                "slide_id": "table_probe",
                "role": "evidence",
                "message": "Table cells are too small.",
                "variant": "table",
                "visual_strategy": "native table",
                "evidence_needs": ["table"],
            },
        ],
        "narrative_arc": [
            {
                "label": "readability",
                "slides": ["chart_probe", "table_probe"],
                "purpose": "Verify rendered readability source-edit handoff.",
            }
        ],
    }
    _write_json(workspace / "content_plan.json", content_plan)

    evidence_plan = {
        "source_policy": {"footer_mode": "source-line", "citation_style": "short-id"},
        "items": [
            {
                "id": "chart",
                "claim": "Chart label fixture",
                "source": "Synthetic CSV",
                "used_on_slides": ["chart_probe"],
            },
            {
                "id": "table",
                "claim": "Table font fixture",
                "source": "Synthetic CSV",
                "used_on_slides": ["table_probe"],
            },
        ],
        "chart_candidates": [
            {
                "id": "chart_candidate",
                "target_slide": "chart_probe",
                "source_ids": ["chart"],
            }
        ],
    }
    _write_json(workspace / "evidence_plan.json", evidence_plan)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the rendered readability-contract smoke check.")
    parser.add_argument(
        "--workspace",
        default="",
        help="Empty workspace path to create/use. Defaults to a temporary workspace.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the temporary workspace after a passing run.",
    )
    return parser.parse_args()


def _assert_design_report(failures: list[dict[str, Any]], design: dict[str, Any]) -> None:
    issues = design.get("issues") if isinstance(design.get("issues"), list) else []
    issue_types = [str(item.get("type") or "") for item in issues if isinstance(item, dict)]
    if design.get("warning_count") != 2 or issue_types != EXPECTED_WARNING_TYPES:
        failures.append(
            {
                "step": "design_rules_qa",
                "reason": "unexpected_warning_types",
                "warning_count": design.get("warning_count"),
                "warning_types": issue_types,
            }
        )
    by_type = {
        str(item.get("type") or ""): item
        for item in issues
        if isinstance(item, dict)
    }
    table = by_type.get("table_font_too_small", {})
    chart = by_type.get("chart_label_font_too_small", {})
    if table.get("slide_index") != 2 or table.get("font_pt") != 6.0 or table.get("min_allowed_pt") != 8.0:
        failures.append({"step": "design_rules_qa", "reason": "table_warning_not_measured", "warning": table})
    if (
        chart.get("slide_index") != 1
        or chart.get("font_pt") != 6.0
        or chart.get("min_allowed_pt") != 8.0
        or not str(chart.get("chart_part") or "").startswith("ppt/charts/chart")
    ):
        failures.append({"step": "design_rules_qa", "reason": "chart_warning_not_mapped", "warning": chart})


def _assert_build_reports(
    failures: list[dict[str, Any]],
    build_report: dict[str, Any],
    qa_report: dict[str, Any],
) -> None:
    run = build_report.get("run") if isinstance(build_report.get("run"), dict) else {}
    if run.get("status") != "failed" or run.get("failed_step") != "qa" or run.get("returncode") != 1:
        failures.append({"step": "build_report", "reason": "qa_failure_not_recorded", "run": run})
    reports = build_report.get("reports") if isinstance(build_report.get("reports"), dict) else {}
    qa_counts = reports.get("qa", {}).get("counts") if isinstance(reports.get("qa"), dict) else {}
    for key, expected in {
        "overflow_count": 0,
        "overlap_count": 0,
        "geometry_error_count": 0,
        "geometry_warning_count": 0,
        "whitespace_warning_count": 0,
        "design_error_count": 0,
        "design_warning_count": 2,
        "visual_warning_count": 0,
        "visual_review_warning_count": 0,
    }.items():
        if qa_report.get(key) != expected or qa_counts.get(key) != expected:
            failures.append(
                {
                    "step": "qa_report",
                    "reason": "unexpected_count",
                    "count": key,
                    "qa_report": qa_report.get(key),
                    "build_report": qa_counts.get(key),
                    "expected": expected,
                }
            )


def _assert_readiness_and_advance(
    failures: list[dict[str, Any]],
    readiness: dict[str, Any],
    advance: dict[str, Any],
    prompt: str,
) -> None:
    next_action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    if readiness.get("status") != "needs_attention":
        failures.append({"step": "workspace_readiness", "status": readiness.get("status")})
    if next_action.get("kind") != "polish_qa_design_warnings":
        failures.append({"step": "workspace_readiness", "next_action": next_action})
    if next_action.get("slide_ids") != EXPECTED_SLIDE_IDS or next_action.get("warning_types") != EXPECTED_WARNING_TYPES:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "warning_handoff_not_specific",
                "slide_ids": next_action.get("slide_ids"),
                "warning_types": next_action.get("warning_types"),
            }
        )
    if advance.get("decision") != "edit_sources_required":
        failures.append({"step": "advance_workspace", "decision": advance.get("decision")})
    source_edit_plan = advance.get("source_edit_plan") if isinstance(advance.get("source_edit_plan"), list) else []
    if len(source_edit_plan) != 2:
        failures.append({"step": "advance_workspace", "reason": "source_edit_count_bad", "source_edit_plan": source_edit_plan})
        return
    table_edit, chart_edit = source_edit_plan
    if (
        table_edit.get("slide_id") != "table_probe"
        or table_edit.get("operation") != "increase_table_font_or_reduce_cells"
        or table_edit.get("font_pt") != 6.0
        or table_edit.get("min_allowed_pt") != 8.0
    ):
        failures.append({"step": "advance_workspace", "reason": "table_edit_bad", "edit": table_edit})
    if (
        chart_edit.get("slide_id") != "chart_probe"
        or chart_edit.get("operation") != "increase_chart_label_font_or_simplify_chart"
        or chart_edit.get("font_pt") != 6.0
        or chart_edit.get("min_allowed_pt") != 8.0
    ):
        failures.append({"step": "advance_workspace", "reason": "chart_edit_bad", "edit": chart_edit})
    for field in ("table", "tables", "readability_contract.min_body_pt"):
        if field not in table_edit.get("suggested_fields", []):
            failures.append({"step": "advance_workspace", "reason": "table_missing_field", "field": field})
    for field in ("chart.options.labelFontSize", "assets.chart_data", "readability_contract.chart_label_min_pt"):
        if field not in chart_edit.get("suggested_fields", []):
            failures.append({"step": "advance_workspace", "reason": "chart_missing_field", "field": field})
    for needle in (
        "Slide IDs: `table_probe, chart_probe`",
        "Warning types: `table_font_too_small, chart_label_font_too_small`",
        "`outline.json` `slides[2]` slide `table_probe`: `increase_table_font_or_reduce_cells`",
        "`outline.json` `slides[1]` slide `chart_probe`: `increase_chart_label_font_or_simplify_chart`",
        "font pt: 6.0",
        "min pt: 8.0",
    ):
        if needle not in prompt:
            failures.append({"step": "advance_prompt", "missing": needle})


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-readability-contract-"))
    )
    if not created_temp and workspace.exists() and any(workspace.iterdir()):
        print(
            json.dumps(
                {
                    "passed": False,
                    "workspace": str(workspace),
                    "failures": [
                        {
                            "step": "workspace",
                            "reason": "workspace_must_be_empty_or_absent",
                        }
                    ],
                },
                indent=2,
            )
        )
        return 1
    workspace.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    try:
        init_cmd = [
            py,
            str(repo / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            "Readability Contract Smoke",
            "--style-preset",
            "lab-report",
        ]
        result = _run(init_cmd, cwd=repo)
        command_results.append({"command": init_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]})
        _write_fixture_sources(workspace)

        build_cmd = [
            py,
            str(repo / "scripts" / "build_workspace.py"),
            "--workspace",
            str(workspace),
            "--qa",
            "--skip-render",
            "--overwrite",
        ]
        result = _run(build_cmd, cwd=repo, allowed_returncodes={1})
        command_results.append({"command": build_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-2000:]})

        readiness_cmd = [py, str(repo / "scripts" / "report_workspace_readiness.py"), "--workspace", str(workspace)]
        result = _run(readiness_cmd, cwd=repo, allowed_returncodes={0, 1})
        command_results.append({"command": readiness_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]})

        advance_cmd = [py, str(repo / "scripts" / "advance_workspace.py"), "--workspace", str(workspace), "--max-steps", "1"]
        result = _run(advance_cmd, cwd=repo, allowed_returncodes={0, 1})
        command_results.append({"command": advance_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]})

        planning = _load_json(workspace / "build" / "planning_validation.json")
        preflight = _load_json(workspace / "build" / "preflight.json")
        qa_report = _load_json(workspace / "build" / "qa" / "report.json")
        design_report = _load_json(workspace / "build" / "qa" / "design_rules.json")
        build_report = _load_json(workspace / "build" / "build_workspace_report.json")
        readiness = _load_json(workspace / "build" / "workspace_readiness.json")
        advance = _load_json(workspace / "build" / "workspace_advance_report.json")
        prompt_path = workspace / "build" / "workspace_next_action.md"
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

        if planning.get("error_count") != 0 or planning.get("warning_count") != 0:
            failures.append({"step": "planning", "error_count": planning.get("error_count"), "warning_count": planning.get("warning_count")})
        if preflight.get("error_count") != 0 or preflight.get("warning_count") != 0:
            failures.append({"step": "preflight", "error_count": preflight.get("error_count"), "warning_count": preflight.get("warning_count")})
        _assert_design_report(failures, design_report)
        _assert_build_reports(failures, build_report, qa_report)
        _assert_readiness_and_advance(failures, readiness, advance, prompt)

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "design_warning_types": [
                item.get("type")
                for item in design_report.get("issues", [])
                if isinstance(item, dict)
            ],
            "readiness_status": readiness.get("status"),
            "next_action": readiness.get("next_action", {}),
            "source_edit_plan_count": len(advance.get("source_edit_plan", []))
            if isinstance(advance.get("source_edit_plan"), list)
            else 0,
            "failures": failures,
            "commands": command_results,
        }
        summary_path = workspace / "build" / "readability_contract_smoke.json"
        _write_json(summary_path, summary)
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "design_warning_types",
                        "readiness_status",
                        "source_edit_plan_count",
                        "failures",
                    )
                },
                indent=2,
            )
        )
        _cleanup_workspace(workspace, created_temp=created_temp, keep=args.keep_workspace, passed=passed)
        return 0 if passed else 1
    except Exception as exc:
        failures.append({"step": "smoke", "reason": str(exc)})
        summary = {
            "passed": False,
            "workspace": str(workspace),
            "failures": failures,
            "commands": command_results,
        }
        try:
            _write_json(workspace / "build" / "readability_contract_smoke.json", summary)
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
