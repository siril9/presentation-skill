#!/usr/bin/env python3
"""Smoke check for Excel workbook fast-first-pass artifact generation."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Set


WORKBOOK_REL = "data/assay_workbook.xlsx"
EXPECTED_SUBTITLE = "Evidence readout from generated analysis artifacts"
EXPECTED_OUTPUTS: dict[str, dict[str, Any]] = {
    "assay_workbook_run_a_signal": {
        "sheet_name": "Run A",
        "title": "Run A: Signal + Ct",
        "label_col": "Sample",
        "value_cols": ["Signal", "Ct"],
        "selected_columns": ["Sample", "Signal", "Ct"],
    },
    "assay_workbook_dilution_high_copy": {
        "sheet_name": "Dilution",
        "title": "Dilution: High copy + Low copy",
        "label_col": "Cycle",
        "value_cols": ["High copy", "Low copy"],
        "selected_columns": ["Cycle", "High copy", "Low copy"],
    },
}
EXPECTED_OUTPUT_IDS = list(EXPECTED_OUTPUTS)


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
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fixture_workbook(path: Path) -> None:
    try:
        from openpyxl import Workbook  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency failure path
        raise RuntimeError("openpyxl is required for the Excel artifact workflow smoke") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    run_sheet = wb.active
    run_sheet.title = "Run A"
    run_sheet.append(["Sample", "Signal", "Ct"])
    for row in [
        ("A01", 41.2, 18.4),
        ("A02", 38.9, 19.1),
        ("B01", 27.4, 24.8),
        ("B02", 19.6, 28.5),
        ("NTC", 1.8, None),
    ]:
        run_sheet.append(row)

    dilution_sheet = wb.create_sheet("Dilution")
    dilution_sheet.append(["Cycle", "High copy", "Low copy"])
    for row in [
        (1, 5.2, 1.1),
        (2, 9.8, 2.8),
        (3, 14.5, 5.4),
        (4, 18.7, 8.9),
    ]:
        dilution_sheet.append(row)

    wb.save(path)


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _qa_counts(payload: dict[str, Any]) -> dict[str, int]:
    keys = [
        "overflow_count",
        "overlap_count",
        "geometry_error_count",
        "geometry_warning_count",
        "whitespace_warning_count",
        "design_error_count",
        "design_warning_count",
        "visual_warning_count",
        "visual_review_warning_count",
    ]
    counts: dict[str, int] = {}
    for key in keys:
        value = payload.get(key, 0)
        counts[key] = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    return counts


def _assert_report_count(
    failures: list[dict[str, Any]],
    reports: dict[str, Any],
    report_name: str,
    count_name: str,
    expected: int,
) -> None:
    report = reports.get(report_name) if isinstance(reports, dict) else None
    counts = report.get("counts") if isinstance(report, dict) else None
    actual = counts.get(count_name) if isinstance(counts, dict) else None
    if actual != expected:
        failures.append(
            {
                "step": "build_report",
                "reason": "unexpected_report_count",
                "report": report_name,
                "count": count_name,
                "expected": expected,
                "actual": actual,
            }
        )


def _artifact_aliases(output: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for artifact in output.get("artifacts", []):
        if isinstance(artifact, dict) and isinstance(artifact.get("alias"), str):
            aliases.add(artifact["alias"])
    return aliases


def _output_by_id(outputs: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        str(output.get("id")): output
        for output in outputs
        if isinstance(output, dict) and isinstance(output.get("id"), str)
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Excel workbook artifact workflow smoke check."
    )
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
    parser.add_argument(
        "--max-exterior-fraction",
        type=float,
        default=0.45,
        help="Maximum allowed measured exterior whitespace fraction.",
    )
    return parser.parse_args()


def _assert_source_path_exists(
    failures: list[dict[str, Any]],
    source_files: dict[str, Any],
    expected_path: str,
    *,
    dependency_role: str = "",
) -> None:
    for entry in source_files.values():
        if not isinstance(entry, dict):
            continue
        if entry.get("path") != expected_path:
            continue
        if dependency_role and entry.get("dependency_role") != dependency_role:
            continue
        if entry.get("exists") is True:
            return
    failures.append(
        {
            "step": "build_report",
            "reason": "missing_source_freshness_entry",
            "path": expected_path,
            "dependency_role": dependency_role,
        }
    )


def _assert_workbook_outputs(
    failures: list[dict[str, Any]],
    outputs: list[Any],
    *,
    max_exterior_fraction: float,
) -> dict[str, dict[str, Any]]:
    by_id = _output_by_id(outputs)
    if list(by_id) != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "artifact_manifest",
                "reason": "unexpected_output_ids",
                "expected": EXPECTED_OUTPUT_IDS,
                "actual": list(by_id),
            }
        )
    for output_id, expected in EXPECTED_OUTPUTS.items():
        output = by_id.get(output_id, {})
        aliases = _artifact_aliases(output)
        missing_prefixes = sorted(
            prefix
            for prefix in ("image:", "chart:", "table:")
            if not any(alias.startswith(prefix) for alias in aliases)
        )
        if missing_prefixes:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "missing_alias_prefixes",
                    "output_id": output_id,
                    "missing_prefixes": missing_prefixes,
                    "aliases": sorted(aliases),
                }
            )
        if output.get("title") != expected["title"]:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "unexpected_title",
                    "output_id": output_id,
                    "expected": expected["title"],
                    "actual": output.get("title"),
                }
            )
        metadata = output.get("analysis_metadata") if isinstance(output.get("analysis_metadata"), dict) else {}
        if metadata.get("source_path") != WORKBOOK_REL or metadata.get("sheet_name") != expected["sheet_name"]:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "workbook_sheet_provenance_bad",
                    "output_id": output_id,
                    "source_path": metadata.get("source_path"),
                    "sheet_name": metadata.get("sheet_name"),
                }
            )
        whitespace = (
            metadata.get("image_whitespace") if isinstance(metadata.get("image_whitespace"), dict) else {}
        )
        exterior_fraction = whitespace.get("exterior_fraction")
        if whitespace.get("checked") is not True:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "image_whitespace_not_checked",
                    "output_id": output_id,
                }
            )
        if not isinstance(exterior_fraction, (int, float)) or isinstance(exterior_fraction, bool):
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "missing_exterior_fraction",
                    "output_id": output_id,
                    "image_whitespace": whitespace,
                }
            )
        elif float(exterior_fraction) > float(max_exterior_fraction):
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "exterior_fraction_high",
                    "output_id": output_id,
                    "max_exterior_fraction": max_exterior_fraction,
                    "actual_exterior_fraction": exterior_fraction,
                }
            )
    return by_id


def _assert_analysis_summary(
    failures: list[dict[str, Any]],
    analysis_summary: dict[str, Any],
) -> None:
    datasets = analysis_summary.get("datasets") if isinstance(analysis_summary.get("datasets"), list) else []
    by_id = _output_by_id(datasets)
    if analysis_summary.get("output_count") != 2 or list(by_id) != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "analysis_summary",
                "reason": "unexpected_dataset_count_or_ids",
                "output_count": analysis_summary.get("output_count"),
                "dataset_ids": list(by_id),
            }
        )
    if analysis_summary.get("source_paths") != [WORKBOOK_REL]:
        failures.append(
            {
                "step": "analysis_summary",
                "reason": "source_paths_not_workbook_only",
                "source_paths": analysis_summary.get("source_paths"),
            }
        )
    for output_id, expected in EXPECTED_OUTPUTS.items():
        dataset = by_id.get(output_id, {})
        if dataset.get("sheet_name") != expected["sheet_name"]:
            failures.append(
                {
                    "step": "analysis_summary",
                    "reason": "sheet_name_missing",
                    "output_id": output_id,
                    "sheet_name": dataset.get("sheet_name"),
                }
            )
        aliases = dataset.get("aliases") if isinstance(dataset.get("aliases"), dict) else {}
        if not all(aliases.get(key) for key in ("figure", "chart", "table")):
            failures.append(
                {
                    "step": "analysis_summary",
                    "reason": "missing_dataset_aliases",
                    "output_id": output_id,
                    "aliases": aliases,
                }
            )


def _assert_scaffold(
    failures: list[dict[str, Any]],
    scaffold: dict[str, Any],
) -> None:
    specs = scaffold.get("specs") if isinstance(scaffold.get("specs"), list) else []
    by_id = _output_by_id(specs)
    alias_plan = scaffold.get("alias_plan") if isinstance(scaffold.get("alias_plan"), list) else []
    if scaffold.get("run", {}).get("returncode") != 0 or len(alias_plan) != 2:
        failures.append(
            {
                "step": "data_artifact_scaffold",
                "reason": "scaffold_run_or_alias_plan_bad",
                "run": scaffold.get("run"),
                "alias_plan_count": len(alias_plan),
            }
        )
    if scaffold.get("skipped") not in ([], None):
        failures.append(
            {
                "step": "data_artifact_scaffold",
                "reason": "unexpected_skipped_entries",
                "skipped": scaffold.get("skipped"),
            }
        )
    spec_sources = [
        str(spec.get("source_path") or "").strip()
        for spec in specs
        if isinstance(spec, dict)
    ]
    if spec_sources != [WORKBOOK_REL, WORKBOOK_REL]:
        failures.append(
            {
                "step": "data_artifact_scaffold",
                "reason": "generated_artifacts_used_as_source_data",
                "spec_sources": spec_sources,
            }
        )
    if list(by_id) != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "data_artifact_scaffold",
                "reason": "unexpected_spec_ids",
                "expected": EXPECTED_OUTPUT_IDS,
                "actual": list(by_id),
            }
        )
    for output_id, expected in EXPECTED_OUTPUTS.items():
        spec = by_id.get(output_id, {})
        for key in ("source_path", "sheet_name", "label_col", "value_cols", "selected_columns"):
            expected_value = WORKBOOK_REL if key == "source_path" else expected[key]
            if spec.get(key) != expected_value:
                failures.append(
                    {
                        "step": "data_artifact_scaffold",
                        "reason": "unexpected_spec_field",
                        "output_id": output_id,
                        "field": key,
                        "expected": expected_value,
                        "actual": spec.get(key),
                    }
                )


def _assert_selection_and_outline(
    failures: list[dict[str, Any]],
    selection: dict[str, Any],
    outline: dict[str, Any],
) -> None:
    bindings = selection.get("bindings") if isinstance(selection.get("bindings"), list) else []
    by_output = {
        str(binding.get("output_id")): binding
        for binding in bindings
        if isinstance(binding, dict) and isinstance(binding.get("output_id"), str)
    }
    if list(by_output) != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "artifact_selection",
                "reason": "unexpected_binding_ids",
                "expected": EXPECTED_OUTPUT_IDS,
                "actual": list(by_output),
            }
        )
    for output_id in EXPECTED_OUTPUT_IDS:
        binding = by_output.get(output_id, {})
        if binding.get("variant") != "chart" or binding.get("slide_id") != f"{output_id}_chart":
            failures.append(
                {
                    "step": "artifact_selection",
                    "reason": "binding_not_aligned",
                    "output_id": output_id,
                    "binding": binding,
                }
            )
        if binding.get("subtitle") != EXPECTED_SUBTITLE:
            failures.append(
                {
                    "step": "artifact_selection",
                    "reason": "subtitle_not_evidence_readout",
                    "output_id": output_id,
                    "subtitle": binding.get("subtitle"),
                }
            )
    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    slide_by_id = {
        str(slide.get("slide_id") or slide.get("id")): slide
        for slide in slides
        if isinstance(slide, dict)
    }
    for output_id in EXPECTED_OUTPUT_IDS:
        slide_id = f"{output_id}_chart"
        slide = slide_by_id.get(slide_id, {})
        if slide.get("variant") != "chart" or slide.get("subtitle") != EXPECTED_SUBTITLE:
            failures.append(
                {
                    "step": "outline",
                    "reason": "workbook_chart_slide_not_built",
                    "slide_id": slide_id,
                    "variant": slide.get("variant"),
                    "subtitle": slide.get("subtitle"),
                }
            )


def _assert_delivery_artifact_context(
    failures: list[dict[str, Any]],
    *,
    delivery: dict[str, Any],
    delivery_advance: dict[str, Any],
    delivery_markdown: str,
    next_action_markdown: str,
) -> None:
    artifact_context = (
        delivery.get("artifact_context")
        if isinstance(delivery.get("artifact_context"), dict)
        else {}
    )
    manifest = (
        artifact_context.get("artifact_manifest")
        if isinstance(artifact_context.get("artifact_manifest"), dict)
        else {}
    )
    selection = (
        artifact_context.get("artifact_selection")
        if isinstance(artifact_context.get("artifact_selection"), dict)
        else {}
    )
    if manifest.get("output_count") != 2:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_manifest_missing",
                "artifact_context": artifact_context,
            }
        )
    if manifest.get("output_ids") != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_output_ids_bad",
                "expected": EXPECTED_OUTPUT_IDS,
                "actual": manifest.get("output_ids"),
            }
        )
    if manifest.get("analysis_summary") != "assets/analysis_summary.json":
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_analysis_summary_missing",
                "analysis_summary": manifest.get("analysis_summary"),
            }
        )
    if manifest.get("analysis_summary_markdown") != "assets/analysis_summary.md":
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_analysis_markdown_missing",
                "analysis_summary_markdown": manifest.get("analysis_summary_markdown"),
            }
        )
    quality_counts = manifest.get("figure_quality_counts")
    if not isinstance(quality_counts, dict) or quality_counts.get("ok") != 2:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_figure_quality_missing",
                "figure_quality_counts": quality_counts,
            }
        )
    aliases = manifest.get("aliases") if isinstance(manifest.get("aliases"), list) else []
    alias_ids = [
        str(alias.get("id") or "").strip()
        for alias in aliases
        if isinstance(alias, dict)
    ]
    if alias_ids != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_alias_ids_bad",
                "expected": EXPECTED_OUTPUT_IDS,
                "actual": alias_ids,
            }
        )
    if selection.get("binding_count") != 2 or selection.get("bound_output_ids") != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_selection_missing",
                "artifact_selection": selection,
            }
        )
    if selection.get("slide_ids") != [f"{output_id}_chart" for output_id in EXPECTED_OUTPUT_IDS]:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_slide_ids_bad",
                "artifact_selection": selection,
            }
        )
    nested_context = delivery.get("readiness", {}).get("artifact_context")
    if not isinstance(nested_context, dict) or not nested_context.get("artifact_manifest"):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "nested_readiness_artifact_context_missing",
                "readiness": delivery.get("readiness"),
            }
        )
    for needle in (
        "## Artifact Context",
        "Artifact manifest:",
        "assets/analysis_summary.json",
        "Figure quality:",
        "Bound artifact targets:",
        EXPECTED_OUTPUT_IDS[0],
        EXPECTED_OUTPUT_IDS[1],
    ):
        if needle not in delivery_markdown:
            failures.append(
                {
                    "step": "delivery_readiness_markdown",
                    "reason": "missing_artifact_context_text",
                    "needle": needle,
                }
            )

    advance_context = (
        delivery_advance.get("artifact_context")
        if isinstance(delivery_advance.get("artifact_context"), dict)
        else {}
    )
    advance_manifest = (
        advance_context.get("artifact_manifest")
        if isinstance(advance_context.get("artifact_manifest"), dict)
        else {}
    )
    if advance_manifest.get("output_ids") != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "advance_delivery",
                "reason": "artifact_context_not_carried",
                "artifact_context": advance_context,
            }
        )
    advance_steps = (
        delivery_advance.get("steps")
        if isinstance(delivery_advance.get("steps"), list)
        else []
    )
    first_step = advance_steps[0] if advance_steps and isinstance(advance_steps[0], dict) else {}
    first_step_context = (
        first_step.get("artifact_context")
        if isinstance(first_step.get("artifact_context"), dict)
        else {}
    )
    first_step_manifest = (
        first_step_context.get("artifact_manifest")
        if isinstance(first_step_context.get("artifact_manifest"), dict)
        else {}
    )
    if first_step_manifest.get("output_ids") != EXPECTED_OUTPUT_IDS:
        failures.append(
            {
                "step": "advance_delivery",
                "reason": "step_artifact_context_not_carried",
                "steps": advance_steps,
            }
        )
    for needle in (
        "## Artifact Context",
        "Artifact manifest:",
        "assets/analysis_summary.json",
        "Figure quality:",
        "Bound artifact targets:",
        EXPECTED_OUTPUT_IDS[0],
        EXPECTED_OUTPUT_IDS[1],
    ):
        if needle not in next_action_markdown:
            failures.append(
                {
                    "step": "advance_delivery_markdown",
                    "reason": "missing_artifact_context_text",
                    "needle": needle,
                }
            )


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-excel-workflow-"))
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
    build_dir = workspace / "build"
    py = sys.executable
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []

    try:
        commands = [
            [
                py,
                str(repo / "scripts" / "init_deck_workspace.py"),
                "--workspace",
                str(workspace),
                "--title",
                "Excel Artifact Workflow Smoke",
                "--style-preset",
                "lab-report",
            ],
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--fast-first-pass",
            ],
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--fast-first-pass",
            ],
            [
                py,
                str(repo / "scripts" / "report_delivery_readiness.py"),
                "--workspace",
                str(workspace),
                "--allow-skip-render",
            ],
            [
                py,
                str(repo / "scripts" / "advance_delivery.py"),
                "--workspace",
                str(workspace),
                "--allow-skip-render",
            ],
        ]

        result = _run(commands[0], cwd=repo)
        command_results.append(
            {
                "command": commands[0],
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        _write_fixture_workbook(workspace / WORKBOOK_REL)

        result = _run(commands[1], cwd=repo)
        command_results.append(
            {
                "command": commands[1],
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        result = _run(commands[2], cwd=repo)
        command_results.append(
            {
                "command": commands[2],
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        result = _run(commands[3], cwd=repo, allowed_returncodes={0, 1})
        command_results.append(
            {
                "command": commands[3],
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        result = _run(commands[4], cwd=repo, allowed_returncodes={0, 1})
        command_results.append(
            {
                "command": commands[4],
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )

        required_paths = [
            "assets/make_figures.py",
            "assets/artifacts_manifest.json",
            "assets/analysis_summary.json",
            "assets/analysis_summary.md",
            "artifact_selections.auto.json",
            "build/data_artifact_scaffold.json",
            "build/artifact_manifest_apply.json",
            "build/planning_validation.json",
            "build/preflight.json",
            "build/qa/report.json",
            "build/workspace_readiness.json",
            "build/build_workspace_report.json",
            "build/delivery_readiness.json",
            "build/delivery_readiness.md",
            "build/delivery_advance_report.json",
            "build/delivery_next_action.md",
        ]
        for rel in required_paths:
            if not (workspace / rel).exists():
                failures.append({"step": "required_path", "missing": rel})

        manifest = _load_json(workspace / "assets" / "artifacts_manifest.json")
        analysis_summary = _load_json(workspace / "assets" / "analysis_summary.json")
        selection = _load_json(workspace / "artifact_selections.auto.json")
        scaffold = _load_json(workspace / "build" / "data_artifact_scaffold.json")
        artifact_apply = _load_json(workspace / "build" / "artifact_manifest_apply.json")
        planning = _load_json(workspace / "build" / "planning_validation.json")
        preflight = _load_json(workspace / "build" / "preflight.json")
        qa = _load_json(workspace / "build" / "qa" / "report.json")
        readiness = _load_json(workspace / "build" / "workspace_readiness.json")
        build_report = _load_json(workspace / "build" / "build_workspace_report.json")
        delivery = _load_json(workspace / "build" / "delivery_readiness.json")
        delivery_advance = _load_json(workspace / "build" / "delivery_advance_report.json")
        delivery_markdown = (workspace / "build" / "delivery_readiness.md").read_text(
            encoding="utf-8"
        )
        next_action_markdown = (workspace / "build" / "delivery_next_action.md").read_text(
            encoding="utf-8"
        )
        outline = _load_json(workspace / "outline.json")

        outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), list) else []
        if manifest.get("manifest_version") != "presentation_skill_artifact_manifest_v1":
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "unexpected_manifest_version",
                    "version": manifest.get("manifest_version"),
                }
            )
        if manifest.get("output_count") != 2 or len(outputs) != 2:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "unexpected_output_count",
                    "output_count": manifest.get("output_count"),
                    "outputs": len(outputs),
                }
            )
        _assert_workbook_outputs(failures, outputs, max_exterior_fraction=args.max_exterior_fraction)
        _assert_analysis_summary(failures, analysis_summary)
        _assert_scaffold(failures, scaffold)
        _assert_selection_and_outline(failures, selection, outline)

        if artifact_apply.get("applied") is not True or artifact_apply.get("selection_count") != 2:
            failures.append(
                {
                    "step": "artifact_apply",
                    "reason": "apply_not_recorded",
                    "applied": artifact_apply.get("applied"),
                    "selection_count": artifact_apply.get("selection_count"),
                }
            )
        if artifact_apply.get("auto_selected") is not True or artifact_apply.get("auto_select_mode") != "lead":
            failures.append(
                {
                    "step": "artifact_apply",
                    "reason": "unexpected_auto_select_mode",
                    "auto_selected": artifact_apply.get("auto_selected"),
                    "auto_select_mode": artifact_apply.get("auto_select_mode"),
                }
            )

        if planning.get("error_count") != 0 or planning.get("warning_count") != 0:
            failures.append(
                {
                    "step": "validate_planning",
                    "error_count": planning.get("error_count"),
                    "warning_count": planning.get("warning_count"),
                }
            )
        if preflight.get("error_count") != 0 or preflight.get("warning_count") != 0:
            failures.append(
                {
                    "step": "preflight",
                    "error_count": preflight.get("error_count"),
                    "warning_count": preflight.get("warning_count"),
                }
            )
        qa_counts = _qa_counts(qa)
        if any(value != 0 for value in qa_counts.values()):
            failures.append({"step": "qa", "reason": "nonzero_qa_counts", "counts": qa_counts})

        reports = build_report.get("reports") if isinstance(build_report.get("reports"), dict) else {}
        options = build_report.get("options") if isinstance(build_report.get("options"), dict) else {}
        if build_report.get("run", {}).get("status") != "succeeded":
            failures.append(
                {
                    "step": "build_report",
                    "reason": "build_not_succeeded",
                    "run": build_report.get("run"),
                }
            )
        for option in [
            "fast_first_pass",
            "scaffold_data_artifacts",
            "auto_bind_artifacts",
            "qa",
            "skip_render",
            "fail_on_planning_warnings",
            "fail_on_whitespace_warnings",
            "overwrite",
        ]:
            if options.get(option) is not True:
                failures.append(
                    {
                        "step": "build_report",
                        "reason": "required_option_not_true",
                        "option": option,
                        "actual": options.get(option),
                    }
                )
        if options.get("artifact_bind_mode") != "lead":
            failures.append(
                {
                    "step": "build_report",
                    "reason": "artifact_bind_mode_not_lead",
                    "artifact_bind_mode": options.get("artifact_bind_mode"),
                }
            )
        _assert_report_count(failures, reports, "artifact_apply", "selection_count", 2)
        for report_name in ("planning", "preflight"):
            _assert_report_count(failures, reports, report_name, "error_count", 0)
            _assert_report_count(failures, reports, report_name, "warning_count", 0)
        for count_name in qa_counts:
            _assert_report_count(failures, reports, "qa", count_name, 0)

        source_files = build_report.get("source_files") if isinstance(build_report.get("source_files"), dict) else {}
        _assert_source_path_exists(failures, source_files, WORKBOOK_REL, dependency_role="artifact_source")
        for output_id in EXPECTED_OUTPUT_IDS:
            _assert_source_path_exists(
                failures,
                source_files,
                f"assets/figures/{output_id}.png",
                dependency_role="artifact_output",
            )
            _assert_source_path_exists(
                failures,
                source_files,
                f"assets/charts/{output_id}.json",
                dependency_role="artifact_output",
            )
            _assert_source_path_exists(
                failures,
                source_files,
                f"assets/tables/{output_id}_summary.json",
                dependency_role="artifact_output",
            )

        artifact_readiness = (
            readiness.get("artifacts") if isinstance(readiness.get("artifacts"), dict) else {}
        )
        tabular_data = artifact_readiness.get("tabular_data")
        if tabular_data != [WORKBOOK_REL]:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "generated_artifacts_reported_as_tabular_data",
                    "tabular_data": tabular_data,
                }
            )
        manifest_readiness = (
            artifact_readiness.get("artifact_manifest")
            if isinstance(artifact_readiness.get("artifact_manifest"), dict)
            else {}
        )
        selection_readiness = (
            artifact_readiness.get("artifact_selection")
            if isinstance(artifact_readiness.get("artifact_selection"), dict)
            else {}
        )
        if readiness.get("status") != "ready":
            failures.append({"step": "workspace_readiness", "status": readiness.get("status")})
        if manifest_readiness.get("output_count") != 2:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "manifest_output_count_bad",
                    "output_count": manifest_readiness.get("output_count"),
                }
            )
        if manifest_readiness.get("output_ids") != EXPECTED_OUTPUT_IDS:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "manifest_output_ids_bad",
                    "output_ids": manifest_readiness.get("output_ids"),
                }
            )
        if selection_readiness.get("binding_count") != 2 or selection_readiness.get("unbound_output_ids"):
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "artifact_binding_not_clean",
                    "artifact_selection": selection_readiness,
                }
            )
        quality_counts = manifest_readiness.get("figure_quality_counts")
        if not isinstance(quality_counts, dict) or quality_counts.get("ok") != 2:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "figure_quality_not_ok",
                    "figure_quality_counts": quality_counts,
                }
            )

        if delivery.get("delivery_status") != "needs_attention":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_delivery_status",
                    "delivery_status": delivery.get("delivery_status"),
                }
            )
        if delivery.get("blocking_reasons") != []:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_blockers",
                    "blocking_reasons": delivery.get("blocking_reasons"),
                }
            )
        if delivery.get("warning_reasons") != ["fast_first_pass_not_final"]:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_warning_reasons",
                    "warning_reasons": delivery.get("warning_reasons"),
                }
            )
        action = delivery.get("recommended_next_action")
        if not isinstance(action, dict) or action.get("kind") != "run_final_delivery_build":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_recommended_next_action",
                    "recommended_next_action": action,
                }
            )
        gates = delivery.get("gates") if isinstance(delivery.get("gates"), dict) else {}
        expected_gates = {
            "source_readiness_ready": True,
            "source_freshness_current": True,
            "build_report_exists": True,
            "output_pptx_exists": True,
            "build_succeeded": True,
            "qa_run": True,
            "fast_first_pass": True,
            "final_build_mode": False,
            "rendered_qa": False,
            "skip_render_allowed": True,
            "planning_warnings_blocking": True,
            "whitespace_warnings_blocking": True,
        }
        for key, expected in expected_gates.items():
            if gates.get(key) is not expected:
                failures.append(
                    {
                        "step": "delivery_readiness",
                        "reason": "unexpected_gate",
                        "gate": key,
                        "expected": expected,
                        "actual": gates.get(key),
                    }
                )
        _assert_delivery_artifact_context(
            failures,
            delivery=delivery,
            delivery_advance=delivery_advance,
            delivery_markdown=delivery_markdown,
            next_action_markdown=next_action_markdown,
        )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "manifest_output_count": manifest.get("output_count"),
            "output_ids": [output.get("id") for output in outputs if isinstance(output, dict)],
            "selection_count": len(selection.get("bindings") or []),
            "build_status": build_report.get("run", {}).get("status"),
            "qa_counts": qa_counts,
            "readiness_status": readiness.get("status"),
            "tabular_data": tabular_data,
            "delivery_status": delivery.get("delivery_status"),
            "delivery_warnings": delivery.get("warning_reasons"),
            "delivery_artifact_context": delivery.get("artifact_context"),
            "advance_decision": delivery_advance.get("decision"),
            "failures": failures,
            "commands": command_results,
        }
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "excel_artifact_workflow_smoke.json").write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "manifest_output_count",
                        "output_ids",
                        "selection_count",
                        "build_status",
                        "qa_counts",
                        "readiness_status",
                        "tabular_data",
                        "delivery_status",
                        "delivery_warnings",
                        "advance_decision",
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
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "excel_artifact_workflow_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
