#!/usr/bin/env python3
"""Smoke check for the integrated local-data fast-first-pass workflow."""

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


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the integrated local-data artifact workflow smoke check."
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


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-data-workflow-"))
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
                "Data Artifact Workflow Smoke",
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
                str(repo / "scripts" / "advance_workspace.py"),
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
        _write_fixture_csv(workspace / "data" / "run_readout.csv")

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
        result = _run(commands[5], cwd=repo, allowed_returncodes={0, 1})
        command_results.append(
            {
                "command": commands[5],
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
            "build/workspace_readiness.md",
            "build/workspace_advance_report.json",
            "build/workspace_next_action.md",
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
        workspace_advance = _load_json(workspace / "build" / "workspace_advance_report.json")
        delivery = _load_json(workspace / "build" / "delivery_readiness.json")
        delivery_advance = _load_json(workspace / "build" / "delivery_advance_report.json")
        workspace_next_action_markdown = (workspace / "build" / "workspace_next_action.md").read_text(
            encoding="utf-8"
        )
        delivery_markdown = (workspace / "build" / "delivery_readiness.md").read_text(
            encoding="utf-8"
        )
        next_action_markdown = (workspace / "build" / "delivery_next_action.md").read_text(
            encoding="utf-8"
        )

        outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), list) else []
        if manifest.get("manifest_version") != "presentation_skill_artifact_manifest_v1":
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "unexpected_manifest_version",
                    "version": manifest.get("manifest_version"),
                }
            )
        if manifest.get("output_count") != 1 or len(outputs) != 1:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "unexpected_output_count",
                    "output_count": manifest.get("output_count"),
                    "outputs": len(outputs),
                }
            )
        output = outputs[0] if outputs and isinstance(outputs[0], dict) else {}
        aliases = _artifact_aliases(output)
        expected_alias_prefixes = {"image:", "chart:", "table:"}
        missing_prefixes = sorted(
            prefix for prefix in expected_alias_prefixes if not any(alias.startswith(prefix) for alias in aliases)
        )
        if missing_prefixes:
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "missing_alias_prefixes",
                    "missing_prefixes": missing_prefixes,
                    "aliases": sorted(aliases),
                }
            )
        metadata = output.get("analysis_metadata") if isinstance(output.get("analysis_metadata"), dict) else {}
        whitespace = (
            metadata.get("image_whitespace") if isinstance(metadata.get("image_whitespace"), dict) else {}
        )
        exterior_fraction = whitespace.get("exterior_fraction")
        if metadata.get("source_path") != "data/run_readout.csv":
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "source_path_not_recorded",
                    "source_path": metadata.get("source_path"),
                }
            )
        if whitespace.get("checked") is not True:
            failures.append({"step": "artifact_manifest", "reason": "image_whitespace_not_checked"})
        if not isinstance(exterior_fraction, (int, float)) or isinstance(exterior_fraction, bool):
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "missing_exterior_fraction",
                    "image_whitespace": whitespace,
                }
            )
        elif float(exterior_fraction) > float(args.max_exterior_fraction):
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "exterior_fraction_high",
                    "max_exterior_fraction": args.max_exterior_fraction,
                    "actual_exterior_fraction": exterior_fraction,
                }
            )

        datasets = analysis_summary.get("datasets") if isinstance(analysis_summary.get("datasets"), list) else []
        if analysis_summary.get("output_count") != 1 or len(datasets) != 1:
            failures.append(
                {
                    "step": "analysis_summary",
                    "reason": "unexpected_dataset_count",
                    "output_count": analysis_summary.get("output_count"),
                    "datasets": len(datasets),
                }
            )
        if "data/run_readout.csv" not in (analysis_summary.get("source_paths") or []):
            failures.append(
                {
                    "step": "analysis_summary",
                    "reason": "source_path_missing",
                    "source_paths": analysis_summary.get("source_paths"),
                }
            )
        dataset = datasets[0] if datasets and isinstance(datasets[0], dict) else {}
        dataset_aliases = dataset.get("aliases") if isinstance(dataset.get("aliases"), dict) else {}
        if not all(dataset_aliases.get(key) for key in ("figure", "chart", "table")):
            failures.append(
                {
                    "step": "analysis_summary",
                    "reason": "missing_dataset_aliases",
                    "aliases": dataset_aliases,
                }
            )

        bindings = selection.get("bindings") if isinstance(selection.get("bindings"), list) else []
        if len(bindings) != 1:
            failures.append(
                {"step": "artifact_selection", "reason": "unexpected_binding_count", "bindings": len(bindings)}
            )
        binding = bindings[0] if bindings and isinstance(bindings[0], dict) else {}
        if binding.get("output_id") != output.get("id") or not binding.get("slide_id"):
            failures.append(
                {
                    "step": "artifact_selection",
                    "reason": "binding_not_aligned",
                    "binding": binding,
                    "output_id": output.get("id"),
                }
            )

        alias_plan = scaffold.get("alias_plan") if isinstance(scaffold.get("alias_plan"), list) else []
        if scaffold.get("run", {}).get("returncode") != 0 or len(alias_plan) != 1:
            failures.append(
                {
                    "step": "data_artifact_scaffold",
                    "reason": "scaffold_run_or_alias_plan_bad",
                    "run": scaffold.get("run"),
                    "alias_plan_count": len(alias_plan),
                }
            )
        specs = scaffold.get("specs") if isinstance(scaffold.get("specs"), list) else []
        spec_sources = [
            str(spec.get("source_path") or "").strip()
            for spec in specs
            if isinstance(spec, dict)
        ]
        if spec_sources != ["data/run_readout.csv"]:
            failures.append(
                {
                    "step": "data_artifact_scaffold",
                    "reason": "generated_artifacts_used_as_source_data",
                    "spec_sources": spec_sources,
                }
            )
        if artifact_apply.get("applied") is not True or artifact_apply.get("selection_count") != 1:
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
        build_speed = build_report.get("speed") if isinstance(build_report.get("speed"), dict) else {}
        build_speed_steps = build_speed.get("steps") if isinstance(build_speed.get("steps"), list) else []
        build_speed_step_names = {
            str(item.get("step") or "")
            for item in build_speed_steps
            if isinstance(item, dict)
        }
        if (
            build_speed.get("schema") != "build_workspace_speed_v1"
            or int(build_speed.get("total_duration_ms") or 0) <= 0
            or not {"scaffold_data_artifacts", "auto_bind_artifacts", "planning_validation", "preflight", "render_deck", "qa"}.issubset(build_speed_step_names)
            or build_speed.get("renderer_used") != "pptxgenjs"
            or build_speed.get("fast_first_pass") is not True
            or build_speed.get("skip_render") is not True
        ):
            failures.append(
                {
                    "step": "build_report",
                    "reason": "speed_ledger_missing_or_incomplete",
                    "speed": build_speed,
                }
            )
        _assert_report_count(failures, reports, "artifact_apply", "selection_count", 1)
        for report_name in ("planning", "preflight"):
            _assert_report_count(failures, reports, report_name, "error_count", 0)
            _assert_report_count(failures, reports, report_name, "warning_count", 0)
        for count_name in qa_counts:
            _assert_report_count(failures, reports, "qa", count_name, 0)
        source_files = build_report.get("source_files") if isinstance(build_report.get("source_files"), dict) else {}
        for key in [
            "artifact_manifest",
            "artifact_selection",
            "artifact_source_run_readout_signal_source",
            "artifact_output_run_readout_signal_run_readout_signal_figure",
            "artifact_output_run_readout_signal_run_readout_signal_chart_json",
            "artifact_output_run_readout_signal_run_readout_signal_summary_table",
        ]:
            if key not in source_files or not source_files.get(key, {}).get("exists"):
                failures.append(
                    {
                        "step": "build_report",
                        "reason": "missing_source_freshness_entry",
                        "key": key,
                    }
                )

        build_artifact_context = (
            build_report.get("artifact_context")
            if isinstance(build_report.get("artifact_context"), dict)
            else {}
        )
        build_context_manifest = (
            build_artifact_context.get("artifact_manifest")
            if isinstance(build_artifact_context.get("artifact_manifest"), dict)
            else {}
        )
        build_context_selection = (
            build_artifact_context.get("artifact_selection")
            if isinstance(build_artifact_context.get("artifact_selection"), dict)
            else {}
        )
        build_context_aliases = (
            build_context_manifest.get("aliases")
            if isinstance(build_context_manifest.get("aliases"), list)
            else []
        )
        build_context_commands = (
            build_context_manifest.get("commands")
            if isinstance(build_context_manifest.get("commands"), dict)
            else {}
        )
        build_context_quality_counts = build_context_manifest.get("figure_quality_counts")
        if (
            build_context_manifest.get("manifest_version") != "presentation_skill_artifact_manifest_v1"
            or build_context_manifest.get("output_count") != 1
            or "run_readout_signal" not in build_context_manifest.get("output_ids", [])
            or build_context_manifest.get("analysis_summary") != "assets/analysis_summary.json"
            or build_context_manifest.get("analysis_summary_markdown") != "assets/analysis_summary.md"
            or not isinstance(build_context_quality_counts, dict)
            or build_context_quality_counts.get("ok") != 1
            or not build_context_commands.get("auto_select_lead")
        ):
            failures.append(
                {
                    "step": "build_report",
                    "reason": "artifact_context_manifest_not_summarized",
                    "artifact_context": build_artifact_context,
                }
            )
        if not any(
            isinstance(alias, dict)
            and alias.get("id") == "run_readout_signal"
            and alias.get("image_alias") == "image:run_readout_signal_figure"
            and alias.get("chart_alias") == "chart:run_readout_signal"
            and alias.get("table_alias") == "table:run_readout_signal_summary"
            for alias in build_context_aliases
        ):
            failures.append(
                {
                    "step": "build_report",
                    "reason": "artifact_context_alias_missing",
                    "aliases": build_context_aliases,
                }
            )
        if (
            build_context_selection.get("binding_count") != 1
            or build_context_selection.get("bound_output_ids") != ["run_readout_signal"]
            or build_context_selection.get("unbound_output_ids") != []
            or build_context_selection.get("slide_ids") != ["run_readout_signal_chart"]
            or build_context_selection.get("variants") != ["chart"]
        ):
            failures.append(
                {
                    "step": "build_report",
                    "reason": "artifact_context_selection_not_summarized",
                    "artifact_selection": build_context_selection,
                }
            )

        artifact_readiness = (
            readiness.get("artifacts") if isinstance(readiness.get("artifacts"), dict) else {}
        )
        tabular_data = artifact_readiness.get("tabular_data")
        if tabular_data != ["data/run_readout.csv"]:
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
        if manifest_readiness.get("output_count") != 1:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "manifest_output_count_bad",
                    "output_count": manifest_readiness.get("output_count"),
                }
            )
        if selection_readiness.get("binding_count") != 1 or selection_readiness.get("unbound_output_ids"):
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "artifact_binding_not_clean",
                    "artifact_selection": selection_readiness,
                }
            )
        quality_counts = manifest_readiness.get("figure_quality_counts")
        if not isinstance(quality_counts, dict) or quality_counts.get("ok") != 1:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "figure_quality_not_ok",
                    "figure_quality_counts": quality_counts,
                }
            )
        readiness_artifact_context = (
            readiness.get("artifact_context")
            if isinstance(readiness.get("artifact_context"), dict)
            else {}
        )
        readiness_context_manifest = (
            readiness_artifact_context.get("artifact_manifest")
            if isinstance(readiness_artifact_context.get("artifact_manifest"), dict)
            else {}
        )
        readiness_context_selection = (
            readiness_artifact_context.get("artifact_selection")
            if isinstance(readiness_artifact_context.get("artifact_selection"), dict)
            else {}
        )
        readiness_context_commands = (
            readiness_context_manifest.get("commands")
            if isinstance(readiness_context_manifest.get("commands"), dict)
            else {}
        )
        readiness_context_quality_counts = readiness_context_manifest.get("figure_quality_counts")
        if (
            readiness_context_manifest.get("output_count") != 1
            or readiness_context_manifest.get("analysis_summary") != "assets/analysis_summary.json"
            or readiness_context_manifest.get("analysis_summary_markdown") != "assets/analysis_summary.md"
            or "run_readout_signal" not in (readiness_context_manifest.get("output_ids") or [])
            or not isinstance(readiness_context_quality_counts, dict)
            or readiness_context_quality_counts.get("ok") != 1
            or not readiness_context_commands.get("auto_select_lead")
            or readiness_artifact_context.get("tabular_data") != ["data/run_readout.csv"]
        ):
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "artifact_context_manifest_not_summarized",
                    "artifact_context": readiness_artifact_context,
                }
            )
        if (
            readiness_context_selection.get("binding_count") != 1
            or readiness_context_selection.get("bound_output_ids") != ["run_readout_signal"]
            or readiness_context_selection.get("unbound_output_ids") != []
            or readiness_context_selection.get("slide_ids") != ["run_readout_signal_chart"]
            or readiness_context_selection.get("variants") != ["chart"]
        ):
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "artifact_context_selection_not_summarized",
                    "artifact_selection": readiness_context_selection,
                }
            )

        if workspace_advance.get("decision") != "ready":
            failures.append(
                {
                    "step": "advance_workspace",
                    "reason": "unexpected_decision",
                    "decision": workspace_advance.get("decision"),
                }
            )
        readiness_speed = (
            readiness.get("last_build", {}).get("speed")
            if isinstance(readiness.get("last_build"), dict)
            else {}
        )
        readiness_steps = (
            readiness_speed.get("step_durations_ms")
            if isinstance(readiness_speed, dict) and isinstance(readiness_speed.get("step_durations_ms"), dict)
            else {}
        )
        if (
            not isinstance(readiness_speed, dict)
            or readiness_speed.get("schema") != "build_workspace_speed_v1"
            or int(readiness_speed.get("total_duration_ms") or 0) <= 0
            or int(readiness_steps.get("render_deck") or 0) <= 0
            or int(readiness_steps.get("qa") or 0) <= 0
            or readiness_speed.get("fast_first_pass") is not True
        ):
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "build_speed_not_summarized",
                    "speed": readiness_speed,
                }
            )
        if "Build speed:" not in (workspace / "build" / "workspace_readiness.md").read_text(encoding="utf-8"):
            failures.append({"step": "workspace_readiness_markdown", "reason": "missing_build_speed_line"})
        workspace_advance_context = (
            workspace_advance.get("artifact_context")
            if isinstance(workspace_advance.get("artifact_context"), dict)
            else {}
        )
        workspace_advance_manifest = (
            workspace_advance_context.get("artifact_manifest")
            if isinstance(workspace_advance_context.get("artifact_manifest"), dict)
            else {}
        )
        workspace_advance_selection = (
            workspace_advance_context.get("artifact_selection")
            if isinstance(workspace_advance_context.get("artifact_selection"), dict)
            else {}
        )
        workspace_advance_quality_counts = workspace_advance_manifest.get("figure_quality_counts")
        if (
            workspace_advance_manifest.get("output_count") != 1
            or not isinstance(workspace_advance_quality_counts, dict)
            or workspace_advance_quality_counts.get("ok") != 1
            or "run_readout_signal" not in (workspace_advance_manifest.get("output_ids") or [])
            or workspace_advance_context.get("tabular_data") != ["data/run_readout.csv"]
        ):
            failures.append(
                {
                    "step": "advance_workspace",
                    "reason": "artifact_context_not_carried",
                    "artifact_context": workspace_advance_context,
                }
            )
        if (
            workspace_advance_selection.get("binding_count") != 1
            or workspace_advance_selection.get("bound_output_ids") != ["run_readout_signal"]
            or workspace_advance_selection.get("slide_ids") != ["run_readout_signal_chart"]
            or workspace_advance_selection.get("variants") != ["chart"]
        ):
            failures.append(
                {
                    "step": "advance_workspace",
                    "reason": "artifact_context_selection_not_carried",
                    "artifact_selection": workspace_advance_selection,
                }
            )
        workspace_steps = (
            workspace_advance.get("steps")
            if isinstance(workspace_advance.get("steps"), list)
            else []
        )
        workspace_first_step = (
            workspace_steps[0] if workspace_steps and isinstance(workspace_steps[0], dict) else {}
        )
        workspace_first_step_context = (
            workspace_first_step.get("artifact_context")
            if isinstance(workspace_first_step.get("artifact_context"), dict)
            else {}
        )
        workspace_first_step_manifest = (
            workspace_first_step_context.get("artifact_manifest")
            if isinstance(workspace_first_step_context.get("artifact_manifest"), dict)
            else {}
        )
        if workspace_first_step_manifest.get("output_count") != 1:
            failures.append(
                {
                    "step": "advance_workspace",
                    "reason": "step_artifact_context_not_carried",
                    "steps": workspace_steps,
                }
            )
        for needle in (
            "## Artifact Context",
            "Manifest:",
            "assets/analysis_summary.json",
            "Figure quality:",
            "Bound artifact targets:",
            "Last build speed:",
        ):
            if needle not in workspace_next_action_markdown:
                failures.append(
                    {
                        "step": "advance_workspace_markdown",
                        "reason": "missing_artifact_context_text",
                        "needle": needle,
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

        delivery_artifact_context = (
            delivery.get("artifact_context")
            if isinstance(delivery.get("artifact_context"), dict)
            else {}
        )
        delivery_manifest = (
            delivery_artifact_context.get("artifact_manifest")
            if isinstance(delivery_artifact_context.get("artifact_manifest"), dict)
            else {}
        )
        delivery_selection = (
            delivery_artifact_context.get("artifact_selection")
            if isinstance(delivery_artifact_context.get("artifact_selection"), dict)
            else {}
        )
        if delivery_manifest.get("output_count") != 1:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_manifest_missing",
                    "artifact_context": delivery_artifact_context,
                }
            )
        delivery_speed = (
            delivery.get("build", {}).get("speed")
            if isinstance(delivery.get("build"), dict)
            else {}
        )
        delivery_steps = (
            delivery_speed.get("step_durations_ms")
            if isinstance(delivery_speed, dict) and isinstance(delivery_speed.get("step_durations_ms"), dict)
            else {}
        )
        if (
            not isinstance(delivery_speed, dict)
            or delivery_speed.get("schema") != "build_workspace_speed_v1"
            or int(delivery_speed.get("total_duration_ms") or 0) <= 0
            or int(delivery_steps.get("render_deck") or 0) <= 0
            or int(delivery_steps.get("qa") or 0) <= 0
            or delivery_speed.get("fast_first_pass") is not True
        ):
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "build_speed_not_carried",
                    "speed": delivery_speed,
                }
            )
        if delivery_manifest.get("analysis_summary") != "assets/analysis_summary.json":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_analysis_summary_missing",
                    "analysis_summary": delivery_manifest.get("analysis_summary"),
                }
            )
        if delivery_manifest.get("analysis_summary_markdown") != "assets/analysis_summary.md":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_analysis_markdown_missing",
                    "analysis_summary_markdown": delivery_manifest.get("analysis_summary_markdown"),
                }
            )
        delivery_quality_counts = delivery_manifest.get("figure_quality_counts")
        if not isinstance(delivery_quality_counts, dict) or delivery_quality_counts.get("ok") != 1:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_figure_quality_missing",
                    "figure_quality_counts": delivery_quality_counts,
                }
            )
        if output.get("id") not in (delivery_manifest.get("output_ids") or []):
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_output_id_missing",
                    "output_ids": delivery_manifest.get("output_ids"),
                    "expected_output_id": output.get("id"),
                }
            )
        if delivery_selection.get("binding_count") != 1 or output.get("id") not in (
            delivery_selection.get("bound_output_ids") or []
        ):
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "artifact_context_selection_missing",
                    "artifact_selection": delivery_selection,
                }
            )
        nested_artifact_context = delivery.get("readiness", {}).get("artifact_context")
        if not isinstance(nested_artifact_context, dict) or not nested_artifact_context.get(
            "artifact_manifest"
        ):
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
            "Build speed:",
        ):
            if needle not in delivery_markdown:
                failures.append(
                    {
                        "step": "delivery_readiness_markdown",
                        "reason": "missing_artifact_context_text",
                        "needle": needle,
                    }
                )

        advance_artifact_context = (
            delivery_advance.get("artifact_context")
            if isinstance(delivery_advance.get("artifact_context"), dict)
            else {}
        )
        advance_manifest = (
            advance_artifact_context.get("artifact_manifest")
            if isinstance(advance_artifact_context.get("artifact_manifest"), dict)
            else {}
        )
        if advance_manifest.get("output_count") != 1:
            failures.append(
                {
                    "step": "advance_delivery",
                    "reason": "artifact_context_not_carried",
                    "artifact_context": advance_artifact_context,
                }
            )
        advance_speed = (
            delivery_advance.get("build_speed")
            if isinstance(delivery_advance.get("build_speed"), dict)
            else {}
        )
        if (
            advance_speed.get("schema") != "build_workspace_speed_v1"
            or int(advance_speed.get("total_duration_ms") or 0) <= 0
            or advance_speed.get("fast_first_pass") is not True
        ):
            failures.append(
                {
                    "step": "advance_delivery",
                    "reason": "build_speed_not_carried",
                    "build_speed": advance_speed,
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
        if first_step_manifest.get("output_count") != 1:
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
            "Build speed:",
        ):
            if needle not in next_action_markdown:
                failures.append(
                    {
                        "step": "advance_delivery_markdown",
                        "reason": "missing_artifact_context_text",
                        "needle": needle,
                    }
                )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "manifest_output_count": manifest.get("output_count"),
            "aliases": sorted(aliases),
            "exterior_fraction": exterior_fraction,
            "selection_count": len(bindings),
            "build_status": build_report.get("run", {}).get("status"),
            "build_speed": build_speed,
            "build_artifact_context": build_artifact_context,
            "qa_counts": qa_counts,
            "readiness_status": readiness.get("status"),
            "tabular_data": tabular_data,
            "workspace_advance_decision": workspace_advance.get("decision"),
            "workspace_advance_artifact_context": workspace_advance_context,
            "delivery_status": delivery.get("delivery_status"),
            "delivery_speed": delivery_speed,
            "delivery_warnings": delivery.get("warning_reasons"),
            "delivery_artifact_context": delivery_artifact_context,
            "advance_decision": delivery_advance.get("decision"),
            "failures": failures,
            "commands": command_results,
        }
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "data_artifact_workflow_smoke.json").write_text(
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
                        "aliases",
                        "exterior_fraction",
                        "selection_count",
                        "build_status",
                        "qa_counts",
                        "readiness_status",
                        "tabular_data",
                        "workspace_advance_decision",
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
            (build_dir / "data_artifact_workflow_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
