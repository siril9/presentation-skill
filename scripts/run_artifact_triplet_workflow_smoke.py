#!/usr/bin/env python3
"""Smoke check for full figure/chart/table artifact triplet binding."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional, Set


DATA_REL = "data/run_readout.csv"
OUTPUT_ID = "run_readout_signal"
EXPECTED_BINDINGS = [
    (OUTPUT_ID, "image-sidebar", f"{OUTPUT_ID}_figure"),
    (OUTPUT_ID, "chart", f"{OUTPUT_ID}_chart"),
    (OUTPUT_ID, "lab-run-results", f"{OUTPUT_ID}_table"),
]
EXPECTED_SIDEBAR_BODY_FONT_SIZE = 16
EXPECTED_REQUIRED_ARTIFACTS = {
    f"{OUTPUT_ID}_figure": [f"{OUTPUT_ID}_figure"],
    f"{OUTPUT_ID}_chart": [f"{OUTPUT_ID}_chart_json"],
    f"{OUTPUT_ID}_table": [f"{OUTPUT_ID}_summary_table"],
}


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


def _write_fixture_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Sample", "Signal", "Ct"])
        writer.writeheader()
        writer.writerows(
            [
                {"Sample": "A01", "Signal": "41.2", "Ct": "18.4"},
                {"Sample": "A02", "Signal": "38.9", "Ct": "19.1"},
                {"Sample": "B01", "Signal": "27.4", "Ct": "24.8"},
                {"Sample": "B02", "Signal": "19.6", "Ct": "28.5"},
                {"Sample": "NTC", "Signal": "1.8", "Ct": ""},
            ]
        )


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


def _artifact_aliases(output: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for artifact in output.get("artifacts", []):
        if isinstance(artifact, dict) and isinstance(artifact.get("alias"), str):
            aliases.add(artifact["alias"])
    return aliases


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


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full generated-artifact triplet workflow smoke check."
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
    return parser.parse_args()


def _assert_manifest(failures: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), list) else []
    output = outputs[0] if outputs and isinstance(outputs[0], dict) else {}
    if manifest.get("manifest_version") != "presentation_skill_artifact_manifest_v1":
        failures.append(
            {
                "step": "artifact_manifest",
                "reason": "unexpected_manifest_version",
                "version": manifest.get("manifest_version"),
            }
        )
    if manifest.get("output_count") != 1 or output.get("id") != OUTPUT_ID:
        failures.append(
            {
                "step": "artifact_manifest",
                "reason": "unexpected_output",
                "output_count": manifest.get("output_count"),
                "output_id": output.get("id"),
            }
        )
    aliases = _artifact_aliases(output)
    for alias in (
        f"image:{OUTPUT_ID}_figure",
        f"chart:{OUTPUT_ID}",
        f"table:{OUTPUT_ID}_summary",
    ):
        if alias not in aliases:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "missing_alias",
                    "alias": alias,
                    "aliases": sorted(aliases),
                }
            )
    metadata = output.get("analysis_metadata") if isinstance(output.get("analysis_metadata"), dict) else {}
    if metadata.get("source_path") != DATA_REL:
        failures.append(
            {
                "step": "artifact_manifest",
                "reason": "source_path_not_recorded",
                "source_path": metadata.get("source_path"),
            }
        )
    whitespace = metadata.get("image_whitespace") if isinstance(metadata.get("image_whitespace"), dict) else {}
    if whitespace.get("checked") is not True or whitespace.get("high_exterior_whitespace") is True:
        failures.append(
            {
                "step": "artifact_manifest",
                "reason": "figure_whitespace_not_clean",
                "image_whitespace": whitespace,
            }
        )


def _assert_triplet_bindings(
    failures: list[dict[str, Any]],
    selection: dict[str, Any],
    artifact_apply: dict[str, Any],
    outline: dict[str, Any],
) -> None:
    bindings = selection.get("bindings") if isinstance(selection.get("bindings"), list) else []
    actual_bindings = [
        (
            str(binding.get("output_id") or ""),
            str(binding.get("variant") or ""),
            str(binding.get("slide_id") or ""),
        )
        for binding in bindings
        if isinstance(binding, dict)
    ]
    if actual_bindings != EXPECTED_BINDINGS:
        failures.append(
            {
                "step": "artifact_selection",
                "reason": "unexpected_triplet_bindings",
                "expected": EXPECTED_BINDINGS,
                "actual": actual_bindings,
            }
        )
    figure_binding = next(
        (
            binding
            for binding in bindings
            if isinstance(binding, dict)
            and str(binding.get("variant") or "") == "image-sidebar"
        ),
        {},
    )
    if figure_binding.get("sidebar_body_font_size") != EXPECTED_SIDEBAR_BODY_FONT_SIZE:
        failures.append(
            {
                "step": "artifact_selection",
                "reason": "sidebar_body_font_size_not_preserved",
                "expected": EXPECTED_SIDEBAR_BODY_FONT_SIZE,
                "actual": figure_binding.get("sidebar_body_font_size"),
                "binding": figure_binding,
            }
        )
    if artifact_apply.get("applied") is not True or artifact_apply.get("selection_count") != 3:
        failures.append(
            {
                "step": "artifact_apply",
                "reason": "apply_not_recorded",
                "applied": artifact_apply.get("applied"),
                "selection_count": artifact_apply.get("selection_count"),
            }
        )
    if artifact_apply.get("auto_selected") is not True or artifact_apply.get("auto_select_mode") != "all":
        failures.append(
            {
                "step": "artifact_apply",
                "reason": "unexpected_auto_select_mode",
                "auto_selected": artifact_apply.get("auto_selected"),
                "auto_select_mode": artifact_apply.get("auto_select_mode"),
            }
        )
    required = artifact_apply.get("required_artifact_ids_by_slide")
    if required != EXPECTED_REQUIRED_ARTIFACTS:
        failures.append(
            {
                "step": "artifact_apply",
                "reason": "required_artifact_mapping_bad",
                "expected": EXPECTED_REQUIRED_ARTIFACTS,
                "actual": required,
            }
        )
    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    actual_slides = [
        (str(slide.get("slide_id") or ""), str(slide.get("variant") or ""))
        for slide in slides[1:]
        if isinstance(slide, dict)
    ]
    expected_slides = [(slide_id, variant) for _, variant, slide_id in EXPECTED_BINDINGS]
    if actual_slides != expected_slides:
        failures.append(
            {
                "step": "outline",
                "reason": "triplet_slides_not_built",
                "expected": expected_slides,
                "actual": actual_slides,
            }
        )
    slides_by_id = {
        str(slide.get("slide_id") or ""): slide
        for slide in slides
        if isinstance(slide, dict)
    }
    figure_slide = slides_by_id.get(f"{OUTPUT_ID}_figure", {})
    if figure_slide.get("sidebar_body_font_size") != EXPECTED_SIDEBAR_BODY_FONT_SIZE:
        failures.append(
            {
                "step": "outline",
                "reason": "sidebar_body_font_size_not_applied",
                "expected": EXPECTED_SIDEBAR_BODY_FONT_SIZE,
                "actual": figure_slide.get("sidebar_body_font_size"),
                "slide": figure_slide,
            }
        )


def _assert_readiness(failures: list[dict[str, Any]], readiness: dict[str, Any]) -> None:
    artifacts = readiness.get("artifacts") if isinstance(readiness.get("artifacts"), dict) else {}
    manifest = artifacts.get("artifact_manifest") if isinstance(artifacts.get("artifact_manifest"), dict) else {}
    selection = artifacts.get("artifact_selection") if isinstance(artifacts.get("artifact_selection"), dict) else {}
    if readiness.get("status") != "ready":
        failures.append({"step": "workspace_readiness", "status": readiness.get("status")})
    if artifacts.get("tabular_data") != [DATA_REL]:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "generated_artifacts_reported_as_tabular_data",
                "tabular_data": artifacts.get("tabular_data"),
            }
        )
    if manifest.get("output_count") != 1 or manifest.get("figure_quality_counts", {}).get("ok") != 1:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "manifest_summary_bad",
                "artifact_manifest": manifest,
            }
        )
    if (
        selection.get("binding_count") != 3
        or selection.get("bound_output_ids") != [OUTPUT_ID]
        or selection.get("unbound_output_ids")
        or selection.get("variants") != ["image-sidebar", "chart", "lab-run-results"]
    ):
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "artifact_selection_not_clean",
                "artifact_selection": selection,
            }
        )


def _assert_build_report(
    failures: list[dict[str, Any]],
    build_report: dict[str, Any],
    qa_counts: dict[str, int],
) -> None:
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
    expected_true = [
        "scaffold_data_artifacts",
        "auto_bind_artifacts",
        "qa",
        "skip_render",
        "fail_on_planning_warnings",
        "fail_on_whitespace_warnings",
        "overwrite",
    ]
    for option in expected_true:
        if options.get(option) is not True:
            failures.append(
                {
                    "step": "build_report",
                    "reason": "required_option_not_true",
                    "option": option,
                    "actual": options.get(option),
                }
            )
    if options.get("fast_first_pass") is not False or options.get("artifact_bind_mode") != "all":
        failures.append(
            {
                "step": "build_report",
                "reason": "unexpected_build_mode",
                "fast_first_pass": options.get("fast_first_pass"),
                "artifact_bind_mode": options.get("artifact_bind_mode"),
            }
        )
    _assert_report_count(failures, reports, "artifact_apply", "selection_count", 3)
    for report_name in ("planning", "preflight"):
        _assert_report_count(failures, reports, report_name, "error_count", 0)
        _assert_report_count(failures, reports, report_name, "warning_count", 0)
    for count_name in qa_counts:
        _assert_report_count(failures, reports, "qa", count_name, 0)

    artifact_context = (
        build_report.get("artifact_context")
        if isinstance(build_report.get("artifact_context"), dict)
        else {}
    )
    context_manifest = (
        artifact_context.get("artifact_manifest")
        if isinstance(artifact_context.get("artifact_manifest"), dict)
        else {}
    )
    context_selection = (
        artifact_context.get("artifact_selection")
        if isinstance(artifact_context.get("artifact_selection"), dict)
        else {}
    )
    context_aliases = (
        context_manifest.get("aliases")
        if isinstance(context_manifest.get("aliases"), list)
        else []
    )
    if (
        context_manifest.get("manifest_version") != "presentation_skill_artifact_manifest_v1"
        or context_manifest.get("output_ids") != [OUTPUT_ID]
        or context_manifest.get("output_count") != 1
        or context_manifest.get("analysis_summary") != "assets/analysis_summary.json"
        or context_manifest.get("analysis_summary_markdown") != "assets/analysis_summary.md"
        or not isinstance(context_manifest.get("figure_quality_counts"), dict)
        or context_manifest.get("figure_quality_counts", {}).get("ok") != 1
        or not isinstance(context_manifest.get("commands"), dict)
        or not context_manifest.get("commands", {}).get("auto_select_all")
    ):
        failures.append(
            {
                "step": "build_report",
                "reason": "artifact_context_manifest_not_summarized",
                "artifact_context": artifact_context,
            }
        )
    if not any(
        isinstance(alias, dict)
        and alias.get("id") == OUTPUT_ID
        and alias.get("image_alias") == f"image:{OUTPUT_ID}_figure"
        and alias.get("chart_alias") == f"chart:{OUTPUT_ID}"
        and alias.get("table_alias") == f"table:{OUTPUT_ID}_summary"
        for alias in context_aliases
    ):
        failures.append(
            {
                "step": "build_report",
                "reason": "artifact_context_alias_missing",
                "aliases": context_aliases,
            }
        )
    if (
        context_selection.get("binding_count") != len(EXPECTED_BINDINGS)
        or context_selection.get("bound_output_ids") != [OUTPUT_ID]
        or context_selection.get("unbound_output_ids") != []
        or [
            (OUTPUT_ID, variant, slide_id)
            for variant, slide_id in zip(
                context_selection.get("variants", []),
                context_selection.get("slide_ids", []),
            )
        ]
        != EXPECTED_BINDINGS
    ):
        failures.append(
            {
                "step": "build_report",
                "reason": "artifact_context_selection_not_summarized",
                "artifact_selection": context_selection,
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
    context = (
        delivery.get("artifact_context")
        if isinstance(delivery.get("artifact_context"), dict)
        else {}
    )
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
    expected_slide_ids = [slide_id for _, _, slide_id in EXPECTED_BINDINGS]
    expected_variants = [variant for _, variant, _ in EXPECTED_BINDINGS]
    if manifest.get("output_count") != 1 or manifest.get("output_ids") != [OUTPUT_ID]:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_manifest_missing",
                "artifact_context": context,
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
    if not isinstance(quality_counts, dict) or quality_counts.get("ok") != 1:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_figure_quality_missing",
                "figure_quality_counts": quality_counts,
            }
        )
    aliases = manifest.get("aliases") if isinstance(manifest.get("aliases"), list) else []
    alias = aliases[0] if aliases and isinstance(aliases[0], dict) else {}
    expected_aliases = {
        "image_alias": f"image:{OUTPUT_ID}_figure",
        "chart_alias": f"chart:{OUTPUT_ID}",
        "table_alias": f"table:{OUTPUT_ID}_summary",
    }
    for key, expected in expected_aliases.items():
        if alias.get(key) != expected:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_alias_missing",
                    "field": key,
                    "expected": expected,
                    "actual": alias.get(key),
                    "aliases": aliases,
                }
            )
    if (
        selection.get("binding_count") != 3
        or selection.get("bound_output_ids") != [OUTPUT_ID]
        or selection.get("slide_ids") != expected_slide_ids
        or selection.get("variants") != expected_variants
    ):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "artifact_context_selection_missing",
                "artifact_selection": selection,
                "expected_slide_ids": expected_slide_ids,
                "expected_variants": expected_variants,
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
        f"image:{OUTPUT_ID}_figure",
        f"chart:{OUTPUT_ID}",
        f"table:{OUTPUT_ID}_summary",
        f"{OUTPUT_ID}_figure",
        f"{OUTPUT_ID}_chart",
        f"{OUTPUT_ID}_table",
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
    if advance_manifest.get("output_ids") != [OUTPUT_ID]:
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
    if first_step_manifest.get("output_ids") != [OUTPUT_ID]:
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
        f"image:{OUTPUT_ID}_figure",
        f"chart:{OUTPUT_ID}",
        f"table:{OUTPUT_ID}_summary",
        f"{OUTPUT_ID}_figure",
        f"{OUTPUT_ID}_chart",
        f"{OUTPUT_ID}_table",
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
        else Path(tempfile.mkdtemp(prefix="presentation-skill-artifact-triplet-"))
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
                "Artifact Triplet Workflow Smoke",
                "--style-preset",
                "lab-report",
            ],
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--scaffold-data-artifacts",
                "--auto-bind-artifacts",
                "--artifact-bind-mode",
                "all",
                "--qa",
                "--skip-render",
                "--fail-on-planning-warnings",
                "--fail-on-whitespace-warnings",
                "--overwrite",
            ],
            [
                py,
                str(repo / "scripts" / "report_workspace_readiness.py"),
                "--workspace",
                str(workspace),
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
        _write_fixture_csv(workspace / DATA_REL)

        for index, cmd in enumerate(commands[1:], start=1):
            allowed_returncodes = {0, 1} if index in {3, 4} else None
            result = _run(cmd, cwd=repo, allowed_returncodes=allowed_returncodes)
            command_results.append(
                {
                    "command": cmd,
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
        selection = _load_json(workspace / "artifact_selections.auto.json")
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

        _assert_manifest(failures, manifest)
        _assert_triplet_bindings(failures, selection, artifact_apply, outline)
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
        _assert_readiness(failures, readiness)
        _assert_build_report(failures, build_report, qa_counts)
        if delivery.get("delivery_status") != "ready":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_delivery_status",
                    "delivery_status": delivery.get("delivery_status"),
                    "blocking_reasons": delivery.get("blocking_reasons"),
                    "warning_reasons": delivery.get("warning_reasons"),
                }
            )
        if delivery.get("blocking_reasons") != [] or delivery.get("warning_reasons") != []:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_delivery_reasons",
                    "blocking_reasons": delivery.get("blocking_reasons"),
                    "warning_reasons": delivery.get("warning_reasons"),
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
            "fast_first_pass": False,
            "final_build_mode": True,
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
        if delivery_advance.get("decision") != "ready":
            failures.append(
                {
                    "step": "advance_delivery",
                    "reason": "unexpected_decision",
                    "decision": delivery_advance.get("decision"),
                    "final_delivery_status": delivery_advance.get("final_delivery_status"),
                }
            )
        _assert_delivery_artifact_context(
            failures,
            delivery=delivery,
            delivery_advance=delivery_advance,
            delivery_markdown=delivery_markdown,
            next_action_markdown=next_action_markdown,
        )

        outline_slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
        figure_slide = next(
            (
                slide
                for slide in outline_slides
                if isinstance(slide, dict)
                and str(slide.get("slide_id") or "") == f"{OUTPUT_ID}_figure"
            ),
            {},
        )
        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "manifest_output_count": manifest.get("output_count"),
            "selection_count": len(selection.get("bindings") or []),
            "bindings": [
                (binding.get("output_id"), binding.get("variant"), binding.get("slide_id"))
                for binding in selection.get("bindings", [])
                if isinstance(binding, dict)
            ],
            "figure_sidebar_body_font_size": figure_slide.get("sidebar_body_font_size"),
            "build_status": build_report.get("run", {}).get("status"),
            "qa_counts": qa_counts,
            "readiness_status": readiness.get("status"),
            "delivery_status": delivery.get("delivery_status"),
            "advance_decision": delivery_advance.get("decision"),
            "failures": failures,
            "commands": command_results,
        }
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "artifact_triplet_workflow_smoke.json").write_text(
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
                        "selection_count",
                        "bindings",
                        "figure_sidebar_body_font_size",
                        "build_status",
                        "qa_counts",
                        "readiness_status",
                        "delivery_status",
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
            (build_dir / "artifact_triplet_workflow_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
