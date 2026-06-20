#!/usr/bin/env python3
"""Fast smoke check for generated data-artifact quality metadata."""

from __future__ import annotations

import argparse
import csv
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


def _context_failures(
    label: str,
    context: Any,
    *,
    expected_source: str,
    expected_output_count: int,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    if not isinstance(context, dict):
        return [{"step": label, "reason": "missing_rebuild_context"}]
    commands = context.get("commands") if isinstance(context.get("commands"), dict) else {}
    outputs = context.get("outputs") if isinstance(context.get("outputs"), dict) else {}
    if context.get("context_version") != "presentation_skill_artifact_rebuild_context_v1":
        failures.append(
            {
                "step": label,
                "reason": "unexpected_context_version",
                "context_version": context.get("context_version"),
            }
        )
    if context.get("output_count") != expected_output_count:
        failures.append(
            {
                "step": label,
                "reason": "unexpected_output_count",
                "output_count": context.get("output_count"),
            }
        )
    if expected_source not in (context.get("source_paths") or []):
        failures.append(
            {
                "step": label,
                "reason": "missing_source_path",
                "source_paths": context.get("source_paths"),
            }
        )
    if commands.get("rebuild_figures") != "python3 assets/make_figures.py":
        failures.append(
            {
                "step": label,
                "reason": "unexpected_rebuild_command",
                "commands": commands,
            }
        )
    if "inspect_artifact_manifest.py" not in str(commands.get("inspect_manifest") or ""):
        failures.append(
            {
                "step": label,
                "reason": "missing_inspect_command",
                "commands": commands,
            }
        )
    if not isinstance(outputs.get("figures"), list) or not outputs.get("figures"):
        failures.append({"step": label, "reason": "missing_figure_outputs", "outputs": outputs})
    if not isinstance(context.get("producer_sha256"), str) or not context.get("producer_sha256"):
        failures.append({"step": label, "reason": "missing_producer_sha256"})
    if not isinstance(context.get("data_specs_sha256"), str) or not context.get("data_specs_sha256"):
        failures.append({"step": label, "reason": "missing_data_specs_sha256"})
    return failures


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a focused generated-artifact quality smoke check."
    )
    parser.add_argument(
        "--workspace",
        default="",
        help="Workspace to create/use. Defaults to a temporary workspace.",
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
        else Path(tempfile.mkdtemp(prefix="presentation-skill-artifact-quality-"))
    )
    workspace.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    commands = [
        [
            py,
            str(repo / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            "Generated Artifact Quality Smoke",
            "--style-preset",
            "lab-report",
        ],
    ]
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    try:
        for cmd in commands:
            result = _run(cmd, cwd=repo)
            command_results.append(
                {
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-1200:],
                }
            )
            if result.returncode != 0:
                failures.append({"step": Path(cmd[1]).name, "returncode": result.returncode})
                raise RuntimeError(f"{Path(cmd[1]).name} failed")

        _write_fixture_csv(workspace / "data" / "run_readout.csv")

        build_dir = workspace / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        workflow_commands = [
            [
                py,
                str(repo / "scripts" / "scaffold_figure_artifacts.py"),
                "--workspace",
                str(workspace),
                "--data-path",
                "data/run_readout.csv",
                "--run",
                "--overwrite",
                "--report",
                str(build_dir / "artifact_quality_scaffold.json"),
            ],
            [
                py,
                str(repo / "scripts" / "inspect_artifact_manifest.py"),
                "--workspace",
                str(workspace),
                "--manifest",
                "assets/artifacts_manifest.json",
                "--report",
                str(build_dir / "artifact_quality_inspection.json"),
            ],
            [
                py,
                str(repo / "scripts" / "apply_artifact_manifest_bindings.py"),
                "--workspace",
                str(workspace),
                "--auto-select",
                "--auto-select-mode",
                "lead",
                "--selection-out",
                str(workspace / "artifact_selections.auto.json"),
                "--report",
                str(build_dir / "artifact_quality_bindings.json"),
            ],
            [
                py,
                str(repo / "scripts" / "validate_planning.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(build_dir / "artifact_quality_planning.json"),
            ],
            [
                py,
                str(repo / "scripts" / "report_workspace_readiness.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(build_dir / "artifact_quality_readiness.json"),
            ],
            [
                py,
                str(repo / "scripts" / "advance_workspace.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(build_dir / "artifact_quality_advance.json"),
                "--next-action-markdown",
                str(build_dir / "artifact_quality_next_action.md"),
            ],
            [
                py,
                str(repo / "scripts" / "emit_data_analysis_prompt.py"),
                "--workspace",
                str(workspace),
                "--user-prompt",
                "Create a clean lab report deck from local assay data.",
                "--output",
                str(build_dir / "artifact_quality_data_analysis_prompt.md"),
            ],
            [
                py,
                str(repo / "scripts" / "emit_outline_authoring_prompt.py"),
                "--workspace",
                str(workspace),
                "--user-prompt",
                "Create a clean lab report deck from local assay data.",
                "--output",
                str(build_dir / "artifact_quality_outline_authoring_prompt.md"),
            ],
        ]
        for cmd in workflow_commands:
            result = _run(cmd, cwd=repo)
            command_results.append(
                {
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-1200:],
                }
            )
            if result.returncode != 0:
                failures.append({"step": Path(cmd[1]).name, "returncode": result.returncode})

        inspection = _load_json(build_dir / "artifact_quality_inspection.json")
        scaffold_report = _load_json(build_dir / "artifact_quality_scaffold.json")
        manifest = _load_json(workspace / "assets" / "artifacts_manifest.json")
        analysis_summary = _load_json(workspace / "assets" / "analysis_summary.json")
        manifest_outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), list) else []
        first_output = manifest_outputs[0] if manifest_outputs and isinstance(manifest_outputs[0], dict) else {}
        first_metadata = (
            first_output.get("analysis_metadata")
            if isinstance(first_output.get("analysis_metadata"), dict)
            else {}
        )
        output_id = str(first_output.get("id") or "run_readout").strip()
        first_artifacts = first_output.get("artifacts") if isinstance(first_output.get("artifacts"), list) else []
        figure_path = ""
        chart_path = ""
        table_path = ""
        for artifact in first_artifacts:
            if not isinstance(artifact, dict):
                continue
            role = str(artifact.get("role") or "").strip().lower()
            path = str(artifact.get("path") or "").strip()
            if role == "figure":
                figure_path = path
            elif role == "chart_json":
                chart_path = path
            elif role == "summary_table":
                table_path = path
        figure_path = figure_path or f"assets/figures/{output_id}.png"
        chart_path = chart_path or f"assets/charts/{output_id}.json"
        table_path = table_path or f"assets/tables/{output_id}_summary.json"
        data_handoff = {
            "recommended_workflow": {
                "mode": "bind_existing_manifest",
                "reason": "Use the generated manifest and preserve its rebuild commands.",
                "commands": [
                    "python3 scripts/apply_artifact_manifest_bindings.py --workspace <deck> --auto-select --auto-select-mode lead"
                ],
                "requires_main_agent_edit": False,
            },
            "analysis_tasks": [
                {
                    "id": "task_run_readout",
                    "question": "Quantify whether signal and Ct separate assay-positive rows from the NTC.",
                    "data_sources": ["data/run_readout.csv"],
                    "outputs": [figure_path, chart_path, table_path],
                    "recommended_slide_ids": ["s2"],
                }
            ],
            "computed_findings": [
                {
                    "id": "finding_signal_ct_separation",
                    "claim": "Sample rows show stronger signal and lower Ct than the NTC control.",
                    "evidence_source": "data/run_readout.csv",
                    "artifact_paths": [figure_path, table_path],
                    "used_on_slides": ["s2"],
                }
            ],
            "chart_or_table_recommendations": [
                {
                    "id": "visual_signal_ct_sidebar",
                    "target_slide": "s2",
                    "variant": "image-sidebar",
                    "primary_artifact": figure_path,
                    "supporting_artifacts": [chart_path, table_path],
                    "reason": "The generated figure carries the readout while the table provides audit detail.",
                }
            ],
            "outline_binding_plan": [
                {
                    "id": "bind_signal_ct_to_s2",
                    "target_slide": "s2",
                    "variant": "image-sidebar",
                    "message": "Signal and Ct separate assay-positive rows from the NTC.",
                    "fields_to_set": {
                        "visual.path": figure_path,
                        "sidebar.source_note": "data/run_readout.csv via assets/make_figures.py",
                    },
                }
            ],
            "slide_artifact_storyboard": [
                {
                    "slide_id": "s2",
                    "variant": "image-sidebar",
                    "output_id": output_id,
                    "artifact_roles": ["figure", "chart", "table"],
                    "data_source_paths": ["data/run_readout.csv"],
                    "script_edit_paths": ["assets/make_figures.py"],
                    "quality_targets": {
                        "target_box": first_metadata.get("target_box", "5.0x3.4 in"),
                        "axis_label_min_pt": first_metadata.get("axis_label_min_pt", 8),
                    },
                    "why_this_slide_structure": "Use the generated figure as the visual anchor while preserving chart/table artifacts for audit detail.",
                }
            ],
            "quality_flags": [
                "Fixture data is intentionally small; verify the denominator before final delivery."
            ],
            "open_questions": [
                "Confirm NTC handling and assay-positive threshold before final delivery."
            ],
            "artifact_rebuild_context": manifest.get("rebuild_context"),
            "data_inventory": [
                {
                    "workspace_relative_path": "data/run_readout.csv",
                    "status": "usable",
                    "data_type": "csv",
                    "source_sha256": first_metadata.get("source_sha256"),
                    "source_size_bytes": first_metadata.get("source_size_bytes")
                    or first_metadata.get("source_bytes"),
                }
            ],
            "artifact_selection_recommendations": {
                "selection_file": "artifact_selections.scout.json",
                "bindings": [
                    {
                        "output_id": output_id,
                        "variant": "image-sidebar",
                        "slide_id": "s2",
                        "title": "Signal and Ct readout",
                        "message": "Signal and Ct separate assay-positive rows from the NTC.",
                        "interpretation": "Generated figure/table artifacts are already available for binding.",
                        "source_note": "data/run_readout.csv via assets/make_figures.py",
                        "sidebar_sections": [
                            {
                                "title": "Evidence",
                                "body": ["Generated figure from data/run_readout.csv."],
                            },
                            {
                                "title": "Readout",
                                "body": ["Signal and Ct values separate sample rows from NTC."],
                            },
                        ],
                    }
                ],
            },
            "evidence_plan_updates": [
                {
                    "id": "ev_run_readout",
                    "claim": "Signal and Ct readout is available as a generated artifact.",
                    "source_note": "data/run_readout.csv via assets/make_figures.py",
                    "visual_use": "figure | table",
                    "used_on_slides": ["s2"],
                }
            ],
            "asset_plan_updates": [
                {
                    "id": f"{output_id}_figure",
                    "type": "local figure",
                    "outputs": [figure_path],
                    "caption": "Scout-selected signal/Ct figure for the image-sidebar evidence slide.",
                    "used_on_slides": ["s2"],
                    "analysis_metadata": {
                        "source_path": "data/run_readout.csv",
                        "source_sha256": first_metadata.get("source_sha256"),
                        "source_bytes": first_metadata.get("source_bytes"),
                        "source_size_bytes": first_metadata.get("source_bytes"),
                        "selected_columns": first_metadata.get("selected_columns", []),
                        "target_box": first_metadata.get("target_box", "5.0x3.4 in"),
                        "figure_size_inches": first_metadata.get("figure_size_inches", [6.4, 3.6]),
                        "figure_dpi": first_metadata.get("figure_dpi", 180),
                        "axis_label_min_pt": first_metadata.get("axis_label_min_pt", 8),
                    },
                },
                {
                    "id": output_id,
                    "type": "chart_json",
                    "outputs": [chart_path],
                    "caption": "Scout-selected editable chart JSON.",
                    "used_on_slides": ["s2"],
                },
                {
                    "id": f"{output_id}_summary",
                    "type": "editable_table",
                    "outputs": [table_path],
                    "caption": "Scout-selected compact summary table.",
                    "used_on_slides": ["s2"],
                },
            ],
            "artifact_registry_updates": [
                {
                    "id": f"{output_id}_figure",
                    "path": figure_path,
                    "producer": "assets/make_figures.py",
                    "used_on_slides": ["s2"],
                    "provenance": "Scout confirmed figure binding from data/run_readout.csv.",
                    "analysis_metadata": {
                        "artifact_role": "figure",
                        "source_path": "data/run_readout.csv",
                        "source_sha256": first_metadata.get("source_sha256"),
                        "source_bytes": first_metadata.get("source_bytes"),
                        "source_size_bytes": first_metadata.get("source_bytes"),
                        "selected_columns": first_metadata.get("selected_columns", []),
                        "target_box": first_metadata.get("target_box", "5.0x3.4 in"),
                        "figure_size_inches": first_metadata.get("figure_size_inches", [6.4, 3.6]),
                        "figure_dpi": first_metadata.get("figure_dpi", 180),
                        "axis_label_min_pt": first_metadata.get("axis_label_min_pt", 8),
                    },
                }
            ],
            "figure_export_contract": {
                "script": "assets/make_figures.py",
                "rerun_command": "python3 assets/make_figures.py",
                "rebuild_context": manifest.get("rebuild_context"),
                "outputs": [
                    {
                        "path": figure_path,
                        "target_slide": "s2",
                        "target_variant": "image-sidebar",
                        "target_box": first_metadata.get("target_box", "5.0x3.4 in"),
                        "figure_size_inches": first_metadata.get("figure_size_inches", [6.4, 3.6]),
                        "figure_dpi": first_metadata.get("figure_dpi", 180),
                        "axis_label_min_pt": first_metadata.get("axis_label_min_pt", 8),
                        "crop_rule": "bbox_inches='tight', small pad, optional trim_image_whitespace.py",
                        "readability_note": "Scout-applied figure export contract keeps axis labels readable.",
                    }
                ],
            },
            "qa_readiness_plan": {
                "source_checks": ["python3 scripts/validate_planning.py --workspace <deck>"],
                "build_checks": [
                    "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite"
                ],
            },
            "main_agent_handoff": {
                "immediate_next_action": "Apply deterministic artifact bindings and preserve rebuild context.",
                "commands_to_run": [
                    "python3 scripts/apply_data_analysis_handoff.py --workspace <deck> --handoff <deck>/data_analysis_handoff.json --report <deck>/data_analysis_handoff_apply_report.json"
                ],
                "verification_evidence": [
                    "data_analysis_handoff_apply_report.json",
                    "build/artifact_quality_readiness_after_handoff.json",
                ],
            },
        }
        handoff_path = workspace / "data_analysis_handoff.json"
        handoff_path.write_text(json.dumps(data_handoff, indent=2) + "\n", encoding="utf-8")
        post_handoff_commands = [
            [
                py,
                str(repo / "scripts" / "apply_data_analysis_handoff.py"),
                "--workspace",
                str(workspace),
                "--handoff",
                str(handoff_path),
                "--report",
                str(workspace / "data_analysis_handoff_apply_report.json"),
            ],
            [
                py,
                str(repo / "scripts" / "report_workspace_readiness.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(build_dir / "artifact_quality_readiness_after_handoff.json"),
            ],
        ]
        for cmd in post_handoff_commands:
            result = _run(cmd, cwd=repo)
            command_results.append(
                {
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-1200:],
                }
            )
            if result.returncode != 0:
                failures.append({"step": Path(cmd[1]).name, "returncode": result.returncode})

        design_brief = _load_json(workspace / "design_brief.json")
        asset_plan = _load_json(workspace / "asset_plan.json")
        readiness = _load_json(build_dir / "artifact_quality_readiness_after_handoff.json")
        initial_readiness = _load_json(build_dir / "artifact_quality_readiness.json")
        handoff_apply_report = _load_json(workspace / "data_analysis_handoff_apply_report.json")
        planning = _load_json(build_dir / "artifact_quality_planning.json")
        readiness_md_path = build_dir / "workspace_readiness.md"
        readiness_md = readiness_md_path.read_text(encoding="utf-8") if readiness_md_path.exists() else ""
        next_action_md_path = build_dir / "artifact_quality_next_action.md"
        next_action_md = next_action_md_path.read_text(encoding="utf-8") if next_action_md_path.exists() else ""

        alias_plan = inspection.get("alias_plan") if isinstance(inspection.get("alias_plan"), list) else []
        first_plan = alias_plan[0] if alias_plan and isinstance(alias_plan[0], dict) else {}
        quality = first_plan.get("figure_quality") if isinstance(first_plan.get("figure_quality"), dict) else {}
        exterior_fraction = quality.get("exterior_fraction")
        manifest_summary = (
            readiness.get("artifacts", {}).get("artifact_manifest")
            if isinstance(readiness.get("artifacts"), dict)
            else {}
        )
        initial_manifest_summary = (
            initial_readiness.get("artifacts", {}).get("artifact_manifest")
            if isinstance(initial_readiness.get("artifacts"), dict)
            else {}
        )
        figure_quality_counts = (
            manifest_summary.get("figure_quality_counts")
            if isinstance(manifest_summary, dict) and isinstance(manifest_summary.get("figure_quality_counts"), dict)
            else {}
        )

        if quality.get("status") != "ok":
            failures.append({"step": "figure_quality", "reason": "status_not_ok", "quality": quality})
        if quality.get("checked") is not True:
            failures.append({"step": "figure_quality", "reason": "not_checked", "quality": quality})
        if not isinstance(exterior_fraction, (int, float)) or isinstance(exterior_fraction, bool):
            failures.append({"step": "figure_quality", "reason": "missing_exterior_fraction", "quality": quality})
        elif float(exterior_fraction) > float(args.max_exterior_fraction):
            failures.append(
                {
                    "step": "figure_quality",
                    "reason": "exterior_fraction_high",
                    "max_exterior_fraction": args.max_exterior_fraction,
                    "actual_exterior_fraction": exterior_fraction,
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
        if readiness.get("status") != "ready":
            failures.append({"step": "workspace_readiness", "status": readiness.get("status")})
        if figure_quality_counts.get("ok") != 1:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "missing_quality_count",
                    "figure_quality_counts": figure_quality_counts,
                }
            )
        if "Figure quality:" not in readiness_md or "figure_quality=`ok:" not in readiness_md:
            failures.append({"step": "workspace_readiness_markdown", "reason": "missing_quality_lines"})
        if "Figure quality:" not in next_action_md or "figure_quality=`ok:" not in next_action_md:
            failures.append({"step": "advance_workspace_markdown", "reason": "missing_quality_lines"})
        prompt_checks = {
            "data_analysis_prompt": build_dir / "artifact_quality_data_analysis_prompt.md",
            "outline_authoring_prompt": build_dir / "artifact_quality_outline_authoring_prompt.md",
        }
        for label, path in prompt_checks.items():
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            for required in (
                "presentation_skill_artifact_rebuild_context_v1",
                "rebuild_figures",
                "inspect_artifact_manifest.py",
                "auto_select_lead",
                "validate_planning.py",
            ):
                if required not in text:
                    failures.append(
                        {
                            "step": label,
                            "reason": "missing_rebuild_context_prompt_text",
                            "required": required,
                        }
                    )
        data_prompt = (
            build_dir / "artifact_quality_data_analysis_prompt.md"
        ).read_text(encoding="utf-8") if (build_dir / "artifact_quality_data_analysis_prompt.md").exists() else ""
        outline_prompt = (
            build_dir / "artifact_quality_outline_authoring_prompt.md"
        ).read_text(encoding="utf-8") if (build_dir / "artifact_quality_outline_authoring_prompt.md").exists() else ""
        if '"artifact_rebuild_context"' not in data_prompt:
            failures.append({"step": "data_analysis_prompt", "reason": "missing_output_schema_rebuild_context"})
        if '"slide_artifact_storyboard"' not in data_prompt:
            failures.append({"step": "data_analysis_prompt", "reason": "missing_output_schema_artifact_storyboard"})
        if '"artifact_rebuild_plan"' not in outline_prompt:
            failures.append({"step": "outline_authoring_prompt", "reason": "missing_output_schema_rebuild_plan"})

        analysis_plan = (
            design_brief.get("analysis_artifact_plan")
            if isinstance(design_brief.get("analysis_artifact_plan"), dict)
            else {}
        )
        data_handoff_meta = (
            design_brief.get("data_analysis_handoff")
            if isinstance(design_brief.get("data_analysis_handoff"), dict)
            else {}
        )
        scout_meta = (
            data_handoff_meta.get("scout_analysis")
            if isinstance(data_handoff_meta.get("scout_analysis"), dict)
            else {}
        )
        analysis_scout = (
            analysis_plan.get("data_analysis_scout")
            if isinstance(analysis_plan.get("data_analysis_scout"), dict)
            else {}
        )
        figure_contract = (
            design_brief.get("figure_export_contract")
            if isinstance(design_brief.get("figure_export_contract"), dict)
            else {}
        )
        registry = analysis_plan.get("artifact_registry") if isinstance(analysis_plan.get("artifact_registry"), list) else []
        registry_entry = next(
            (
                item
                for item in registry
                if isinstance(item, dict)
                and str(item.get("id") or "") == f"{output_id}_figure"
            ),
            {},
        )
        figure_outputs = figure_contract.get("outputs") if isinstance(figure_contract.get("outputs"), list) else []
        figure_output = next(
            (
                item
                for item in figure_outputs
                if isinstance(item, dict) and str(item.get("path") or "") == figure_path
            ),
            {},
        )
        asset_image = next(
            (
                item
                for item in asset_plan.get("images", [])
                if isinstance(item, dict) and str(item.get("path") or "") == figure_path
            ),
            {},
        ) if isinstance(asset_plan.get("images"), list) else {}
        asset_chart = next(
            (
                item
                for item in asset_plan.get("charts", [])
                if isinstance(item, dict) and str(item.get("path") or "") == chart_path
            ),
            {},
        ) if isinstance(asset_plan.get("charts"), list) else {}
        asset_table = next(
            (
                item
                for item in asset_plan.get("tables", [])
                if isinstance(item, dict) and str(item.get("path") or "") == table_path
            ),
            {},
        ) if isinstance(asset_plan.get("tables"), list) else {}
        readiness_manifest = (
            readiness.get("artifacts", {}).get("artifact_manifest")
            if isinstance(readiness.get("artifacts"), dict)
            else {}
        )
        context_checks = {
            "scaffold_report.rebuild_context": scaffold_report.get("rebuild_context"),
            "artifact_manifest.rebuild_context": manifest.get("rebuild_context"),
            "analysis_summary.rebuild_context": analysis_summary.get("rebuild_context"),
            "design_brief.analysis_artifact_plan.rebuild_context": analysis_plan.get("rebuild_context"),
            "design_brief.figure_export_contract.rebuild_context": figure_contract.get("rebuild_context"),
            "inspection.rebuild_context": inspection.get("rebuild_context"),
            "readiness.artifact_manifest.rebuild_context": readiness_manifest.get("rebuild_context")
            if isinstance(readiness_manifest, dict)
            else None,
        }
        for label, context in context_checks.items():
            failures.extend(
                _context_failures(
                    label,
                    context,
                    expected_source="data/run_readout.csv",
                    expected_output_count=1,
                )
            )
        data_context_checks = {
            "data_handoff_apply_report.artifact_evidence_ledger.artifact_rebuild_context": (
                handoff_apply_report.get("artifact_evidence_ledger", {}).get("artifact_rebuild_context")
                if isinstance(handoff_apply_report.get("artifact_evidence_ledger"), dict)
                else None
            ),
            "design_brief.data_analysis_handoff.artifact_rebuild_context": data_handoff_meta.get("artifact_rebuild_context"),
            "design_brief.analysis_artifact_plan.data_analysis_rebuild_context": analysis_plan.get("data_analysis_rebuild_context"),
            "readiness.data_analysis_handoff.artifact_rebuild_context": (
                readiness.get("data_analysis_handoff", {}).get("artifact_rebuild_context")
                if isinstance(readiness.get("data_analysis_handoff"), dict)
                else None
            ),
        }
        for label, context in data_context_checks.items():
            if label.endswith("readiness.data_analysis_handoff.artifact_rebuild_context"):
                if not isinstance(context, dict) or context.get("context_version") != "presentation_skill_artifact_rebuild_context_v1":
                    failures.append({"step": label, "reason": "missing_readiness_rebuild_context", "context": context})
                continue
            failures.extend(
                _context_failures(
                    label,
                    context,
                    expected_source="data/run_readout.csv",
                    expected_output_count=1,
                )
            )
        data_readiness_rebuild = (
            readiness.get("data_analysis_handoff", {}).get("artifact_rebuild_context")
            if isinstance(readiness.get("data_analysis_handoff"), dict)
            else {}
        )
        if (
            not isinstance(data_readiness_rebuild, dict)
            or data_readiness_rebuild.get("present") is not True
            or data_readiness_rebuild.get("persisted") is not True
            or data_readiness_rebuild.get("command_count", 0) < 3
        ):
            failures.append(
                {
                    "step": "workspace_readiness_data_handoff",
                    "reason": "data_rebuild_context_not_summarized",
                    "artifact_rebuild_context": data_readiness_rebuild,
                }
            )
        if "Data artifact rebuild:" not in readiness_md:
            failures.append({"step": "workspace_readiness_markdown", "reason": "missing_data_rebuild_line"})
        storyboard_sources = {
            "data_analysis_handoff_apply_report.artifact_storyboard": handoff_apply_report.get("artifact_storyboard"),
            "data_analysis_handoff_apply_report.artifact_evidence_ledger.slide_artifact_storyboard": (
                handoff_apply_report.get("artifact_evidence_ledger", {}).get("slide_artifact_storyboard")
                if isinstance(handoff_apply_report.get("artifact_evidence_ledger"), dict)
                else None
            ),
            "design_brief.data_analysis_handoff.artifact_storyboard": data_handoff_meta.get("artifact_storyboard"),
            "design_brief.analysis_artifact_plan.data_artifact_storyboard": analysis_plan.get("data_artifact_storyboard"),
        }
        for label, storyboard in storyboard_sources.items():
            items = storyboard.get("items") if isinstance(storyboard, dict) else []
            item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
            roles = item.get("artifact_roles") if isinstance(item.get("artifact_roles"), list) else []
            quality_targets = item.get("quality_targets") if isinstance(item.get("quality_targets"), dict) else {}
            if (
                not isinstance(storyboard, dict)
                or storyboard.get("schema") != "data_artifact_storyboard_v1"
                or int(storyboard.get("item_count") or 0) != 1
                or item.get("slide_id") != "s2"
                or item.get("variant") != "image-sidebar"
                or item.get("output_id") != output_id
                or not {"figure", "chart", "table"}.issubset(set(roles))
                or "data/run_readout.csv" not in (item.get("data_source_paths") or [])
                or "assets/make_figures.py" not in (item.get("script_edit_paths") or [])
                or not quality_targets.get("target_box")
            ):
                failures.append(
                    {
                        "step": label,
                        "reason": "artifact_storyboard_not_persisted",
                        "storyboard": storyboard,
                    }
                )
        readiness_storyboard = (
            readiness.get("data_analysis_handoff", {}).get("artifact_storyboard")
            if isinstance(readiness.get("data_analysis_handoff"), dict)
            else {}
        )
        if (
            not isinstance(readiness_storyboard, dict)
            or readiness_storyboard.get("persisted") is not True
            or int(readiness_storyboard.get("item_count") or 0) != 1
            or readiness_storyboard.get("slide_ids") != ["s2"]
            or output_id not in (readiness_storyboard.get("output_ids") or [])
            or not {"figure", "chart", "table"}.issubset(set(readiness_storyboard.get("artifact_roles") or []))
            or "data/run_readout.csv" not in (readiness_storyboard.get("data_source_paths") or [])
        ):
            failures.append(
                {
                    "step": "workspace_readiness_data_handoff",
                    "reason": "artifact_storyboard_not_summarized",
                    "artifact_storyboard": readiness_storyboard,
                }
            )
        if "Data handoff storyboard:" not in readiness_md:
            failures.append({"step": "workspace_readiness_markdown", "reason": "missing_data_storyboard_line"})
        if handoff_apply_report.get("artifact_storyboard_applied") is not True:
            failures.append(
                {
                    "step": "data_analysis_handoff_apply",
                    "reason": "artifact_storyboard_not_applied",
                    "artifact_storyboard_applied": handoff_apply_report.get("artifact_storyboard_applied"),
                }
            )
        if handoff_apply_report.get("artifact_rebuild_context_applied") is not True:
            failures.append(
                {
                    "step": "data_analysis_handoff_apply",
                    "reason": "artifact_rebuild_context_not_applied",
                    "artifact_rebuild_context_applied": handoff_apply_report.get("artifact_rebuild_context_applied"),
                }
            )
        if handoff_apply_report.get("figure_export_contract_applied") is not True:
            failures.append(
                {
                    "step": "data_analysis_handoff_apply",
                    "reason": "figure_export_contract_not_applied",
                    "figure_export_contract_applied": handoff_apply_report.get("figure_export_contract_applied"),
                }
            )
        if int(handoff_apply_report.get("artifact_registry_update_count") or 0) < 1:
            failures.append(
                {
                    "step": "data_analysis_handoff_apply",
                    "reason": "artifact_registry_update_count_missing",
                    "artifact_registry_update_count": handoff_apply_report.get("artifact_registry_update_count"),
                }
            )
        asset_counts = (
            handoff_apply_report.get("asset_plan_update_counts")
            if isinstance(handoff_apply_report.get("asset_plan_update_counts"), dict)
            else {}
        )
        if not {"images", "charts", "tables"}.issubset(set(asset_counts)):
            failures.append(
                {
                    "step": "data_analysis_handoff_apply",
                    "reason": "asset_plan_update_counts_incomplete",
                    "asset_plan_update_counts": asset_counts,
                }
            )
        if not isinstance(figure_output, dict) or figure_output.get("readability_note") != "Scout-applied figure export contract keeps axis labels readable.":
            failures.append(
                {
                    "step": "design_brief.figure_export_contract",
                    "reason": "scout_figure_contract_not_persisted",
                    "figure_output": figure_output,
                }
            )
        if not isinstance(registry_entry, dict) or "Scout confirmed" not in str(registry_entry.get("provenance") or ""):
            failures.append(
                {
                    "step": "design_brief.analysis_artifact_plan.artifact_registry",
                    "reason": "scout_registry_update_not_persisted",
                    "registry_entry": registry_entry,
                }
            )
        if not isinstance(asset_image, dict) or "Scout-selected" not in str(asset_image.get("caption") or ""):
            failures.append({"step": "asset_plan.images", "reason": "scout_image_update_not_persisted", "asset_image": asset_image})
        if not isinstance(asset_chart, dict) or "Scout-selected" not in str(asset_chart.get("caption") or ""):
            failures.append({"step": "asset_plan.charts", "reason": "scout_chart_update_not_persisted", "asset_chart": asset_chart})
        if not isinstance(asset_table, dict) or "Scout-selected" not in str(asset_table.get("caption") or ""):
            failures.append({"step": "asset_plan.tables", "reason": "scout_table_update_not_persisted", "asset_table": asset_table})
        readiness_contracts = (
            readiness.get("data_analysis_handoff", {}).get("artifact_contracts")
            if isinstance(readiness.get("data_analysis_handoff"), dict)
            else {}
        )
        if (
            not isinstance(readiness_contracts, dict)
            or readiness_contracts.get("figure_export_contract_applied") is not True
            or int(readiness_contracts.get("artifact_registry_update_count") or 0) < 1
        ):
            failures.append(
                {
                    "step": "workspace_readiness_data_handoff",
                    "reason": "artifact_contracts_not_summarized",
                    "artifact_contracts": readiness_contracts,
                }
            )
        if "Data artifact contracts:" not in readiness_md:
            failures.append({"step": "workspace_readiness_markdown", "reason": "missing_data_contracts_line"})

        for label, ledger in (
            ("design_brief.data_analysis_handoff.scout_analysis", scout_meta),
            ("design_brief.analysis_artifact_plan.data_analysis_scout", analysis_scout),
        ):
            task_ids = [
                str(item.get("id") or "")
                for item in ledger.get("analysis_tasks", [])
                if isinstance(item, dict)
            ] if isinstance(ledger, dict) and isinstance(ledger.get("analysis_tasks"), list) else []
            finding_ids = [
                str(item.get("id") or "")
                for item in ledger.get("computed_findings", [])
                if isinstance(item, dict)
            ] if isinstance(ledger, dict) and isinstance(ledger.get("computed_findings"), list) else []
            if (
                not isinstance(ledger, dict)
                or ledger.get("schema") != "data_analysis_scout_ledger_v1"
                or "task_run_readout" not in task_ids
                or "finding_signal_ct_separation" not in finding_ids
            ):
                failures.append(
                    {
                        "step": label,
                        "reason": "scout_analysis_ledger_not_persisted",
                        "ledger": ledger,
                    }
                )
        scout_counts = (
            handoff_apply_report.get("scout_analysis_counts")
            if isinstance(handoff_apply_report.get("scout_analysis_counts"), dict)
            else {}
        )
        if (
            handoff_apply_report.get("scout_analysis_applied") is not True
            or int(scout_counts.get("analysis_task_count") or 0) < 1
            or int(scout_counts.get("computed_finding_count") or 0) < 1
            or int(scout_counts.get("visual_recommendation_count") or 0) < 1
            or int(scout_counts.get("open_question_count") or 0) < 1
        ):
            failures.append(
                {
                    "step": "data_analysis_handoff_apply",
                    "reason": "scout_analysis_counts_missing",
                    "scout_analysis_applied": handoff_apply_report.get("scout_analysis_applied"),
                    "scout_analysis_counts": scout_counts,
                }
            )
        readiness_scout = (
            readiness.get("data_analysis_handoff", {}).get("scout_analysis")
            if isinstance(readiness.get("data_analysis_handoff"), dict)
            else {}
        )
        if (
            not isinstance(readiness_scout, dict)
            or readiness_scout.get("persisted") is not True
            or int(readiness_scout.get("analysis_task_count") or 0) < 1
            or int(readiness_scout.get("computed_finding_count") or 0) < 1
            or int(readiness_scout.get("visual_recommendation_count") or 0) < 1
            or int(readiness_scout.get("open_question_count") or 0) < 1
            or "s2" not in (readiness_scout.get("target_slide_ids") or [])
            or "image-sidebar" not in (readiness_scout.get("variants") or [])
        ):
            failures.append(
                {
                    "step": "workspace_readiness_data_handoff",
                    "reason": "scout_analysis_not_summarized",
                    "scout_analysis": readiness_scout,
                }
            )
        if "Data scout analysis:" not in readiness_md:
            failures.append({"step": "workspace_readiness_markdown", "reason": "missing_data_scout_analysis_line"})

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "quality": quality,
            "figure_quality_counts": figure_quality_counts,
            "rebuild_context": manifest.get("rebuild_context"),
            "data_handoff_rebuild_context": data_readiness_rebuild,
            "data_handoff_scout_analysis": (
                readiness.get("data_analysis_handoff", {}).get("scout_analysis")
                if isinstance(readiness.get("data_analysis_handoff"), dict)
                else {}
            ),
            "data_handoff_storyboard": (
                readiness.get("data_analysis_handoff", {}).get("artifact_storyboard")
                if isinstance(readiness.get("data_analysis_handoff"), dict)
                else {}
            ),
            "initial_readiness_status": initial_readiness.get("status"),
            "planning_counts": {
                "errors": planning.get("error_count"),
                "warnings": planning.get("warning_count"),
            },
            "readiness_status": readiness.get("status"),
            "failures": failures,
            "commands": command_results,
        }
        summary_path = build_dir / "artifact_quality_smoke.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: summary[key] for key in ("passed", "workspace", "quality", "figure_quality_counts", "planning_counts", "readiness_status", "failures")}, indent=2))
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
            build_dir = workspace / "build"
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "artifact_quality_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
