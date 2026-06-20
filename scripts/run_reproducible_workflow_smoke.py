#!/usr/bin/env python3
"""End-to-end smoke for the reproducible deck workflow."""

from __future__ import annotations

import argparse
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


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _positive_counts(payload: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        try:
            value = int(payload.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            out[key] = value
    return out


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _assert_clean_build(
    *,
    workspace: Path,
    outline_smoke: dict[str, Any],
    build_report: dict[str, Any],
    delivery_report: dict[str, Any],
    advance_report: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    if outline_smoke.get("passed") is not True:
        failures.append({"step": "outline_authoring_handoff_smoke", "reason": "setup_not_passed"})
    if outline_smoke.get("readiness_status") != "ready":
        failures.append(
            {
                "step": "outline_authoring_handoff_smoke",
                "reason": "setup_readiness_not_ready",
                "status": outline_smoke.get("readiness_status"),
            }
        )

    run = build_report.get("run") if isinstance(build_report.get("run"), dict) else {}
    options = build_report.get("options") if isinstance(build_report.get("options"), dict) else {}
    outputs = build_report.get("outputs") if isinstance(build_report.get("outputs"), dict) else {}
    pptx = outputs.get("pptx") if isinstance(outputs.get("pptx"), dict) else {}
    reports = build_report.get("reports") if isinstance(build_report.get("reports"), dict) else {}
    planning = reports.get("planning") if isinstance(reports.get("planning"), dict) else {}
    preflight = reports.get("preflight") if isinstance(reports.get("preflight"), dict) else {}
    qa = reports.get("qa") if isinstance(reports.get("qa"), dict) else {}
    qa_counts = qa.get("counts") if isinstance(qa.get("counts"), dict) else {}
    planning_counts = planning.get("counts") if isinstance(planning.get("counts"), dict) else {}
    preflight_counts = preflight.get("counts") if isinstance(preflight.get("counts"), dict) else {}

    if run.get("status") != "succeeded" or run.get("returncode") not in (0, None):
        failures.append({"step": "build_workspace", "reason": "build_not_succeeded", "run": run})
    expected_options = {
        "qa": True,
        "skip_render": True,
        "fail_on_planning_warnings": True,
        "fail_on_whitespace_warnings": True,
        "fail_on_design_warnings": True,
    }
    for key, expected in expected_options.items():
        if options.get(key) is not expected:
            failures.append({"step": "build_workspace", "reason": "option_mismatch", "key": key, "actual": options.get(key)})
    if not pptx.get("exists"):
        failures.append({"step": "build_workspace", "reason": "missing_output_pptx", "pptx": pptx})

    build_quality = (
        build_report.get("quality_context")
        if isinstance(build_report.get("quality_context"), dict)
        else {}
    )
    build_slide_quality = (
        build_quality.get("slide_quality_contract")
        if isinstance(build_quality.get("slide_quality_contract"), dict)
        else {}
    )
    build_outline_quality = (
        build_quality.get("outline_quality_alignment")
        if isinstance(build_quality.get("outline_quality_alignment"), dict)
        else {}
    )
    if (
        build_slide_quality.get("contract_version") != "slide_quality_contract_v1"
        or build_slide_quality.get("min_title_pt") != 24
        or build_slide_quality.get("fail_on_awkward_whitespace") is not True
        or _int_value(build_slide_quality.get("required_command_count")) < 4
    ):
        failures.append(
            {
                "step": "build_workspace",
                "reason": "slide_quality_contract_not_recorded",
                "quality_context": build_quality,
            }
        )
    if (
        build_outline_quality.get("contract_version") != "slide_quality_contract_v1"
        or build_outline_quality.get("present") is not True
        or _int_value(build_outline_quality.get("readability_target_count")) < 4
        or _int_value(build_outline_quality.get("layout_target_count")) < 4
    ):
        failures.append(
            {
                "step": "build_workspace",
                "reason": "outline_quality_alignment_not_recorded",
                "quality_context": build_quality,
            }
        )

    for label, counts in (("planning", planning_counts), ("preflight", preflight_counts)):
        positives = _positive_counts(counts, ["error_count", "warning_count"])
        if positives:
            failures.append({"step": f"{label}_report", "reason": "nonzero_counts", "counts": positives})
    qa_positive = _positive_counts(
        qa_counts,
        [
            "overflow_count",
            "overlap_count",
            "geometry_error_count",
            "whitespace_warning_count",
            "design_error_count",
            "design_warning_count",
            "visual_warning_count",
            "visual_review_warning_count",
        ],
    )
    if qa_positive:
        failures.append({"step": "qa_report", "reason": "nonzero_counts", "counts": qa_positive})

    if delivery_report.get("delivery_status") != "needs_attention":
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "unexpected_status",
                "status": delivery_report.get("delivery_status"),
            }
        )
    if delivery_report.get("blocking_reasons"):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "unexpected_blockers",
                "blocking_reasons": delivery_report.get("blocking_reasons"),
            }
        )
    warning_reasons = delivery_report.get("warning_reasons")
    if warning_reasons != ["visual_review_not_run"]:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "unexpected_warnings",
                "warning_reasons": warning_reasons,
            }
        )
    gates = delivery_report.get("gates") if isinstance(delivery_report.get("gates"), dict) else {}
    required_true_gates = [
        "source_readiness_ready",
        "source_freshness_current",
        "build_report_exists",
        "output_pptx_exists",
        "build_succeeded",
        "qa_run",
        "final_build_mode",
        "skip_render_allowed",
        "planning_warnings_blocking",
        "whitespace_warnings_blocking",
        "phase_proof_ledger_declared",
        "phase_proof_ledger_valid",
        "acceptance_evidence_files_satisfied",
    ]
    for key in required_true_gates:
        if gates.get(key) is not True:
            failures.append({"step": "delivery_readiness", "reason": "gate_not_true", "gate": key, "actual": gates.get(key)})
    if gates.get("visual_review_run") is not False:
        failures.append({"step": "delivery_readiness", "reason": "visual_review_run_should_be_false"})

    visual_review = (
        delivery_report.get("visual_review_requirement")
        if isinstance(delivery_report.get("visual_review_requirement"), dict)
        else {}
    )
    if visual_review.get("required") is not True or visual_review.get("run") is not False:
        failures.append({"step": "delivery_readiness", "reason": "bad_visual_review_requirement", "visual_review": visual_review})
    next_action = (
        delivery_report.get("recommended_next_action")
        if isinstance(delivery_report.get("recommended_next_action"), dict)
        else {}
    )
    if next_action.get("kind") != "run_visual_review_delivery_build":
        failures.append({"step": "delivery_readiness", "reason": "wrong_next_action", "next_action": next_action})

    if not (workspace / "build" / "delivery_readiness.json").exists():
        failures.append({"step": "delivery_readiness", "reason": "missing_delivery_report_file"})
    if not (workspace / "build" / "delivery_readiness.md").exists():
        failures.append({"step": "delivery_readiness", "reason": "missing_delivery_markdown_file"})
    if not (workspace / "build" / "delivery_advance_report.json").exists():
        failures.append({"step": "advance_delivery", "reason": "missing_advance_report_file"})
    if not (workspace / "build" / "delivery_next_action.md").exists():
        failures.append({"step": "advance_delivery", "reason": "missing_next_action_markdown_file"})

    source_inventory = (
        delivery_report.get("workspace_source_inventory")
        if isinstance(delivery_report.get("workspace_source_inventory"), dict)
        else {}
    )
    data_paths = source_inventory.get("data_paths") if isinstance(source_inventory.get("data_paths"), list) else []
    if source_inventory.get("exists") is not True or _int_value(source_inventory.get("data_file_count")) < 1:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "source_inventory_not_propagated",
                "workspace_source_inventory": source_inventory,
            }
        )
    if "data/assay_readouts.csv" not in data_paths:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "source_inventory_missing_fixture_path",
                "data_paths": data_paths,
            }
        )
    readiness_inventory = (
        delivery_report.get("readiness", {}).get("workspace_source_inventory")
        if isinstance(delivery_report.get("readiness"), dict)
        else {}
    )
    if not isinstance(readiness_inventory, dict) or _int_value(readiness_inventory.get("data_file_count")) < 1:
        failures.append({"step": "delivery_readiness", "reason": "readiness_source_inventory_not_nested"})

    resolved_treatments = (
        delivery_report.get("resolved_treatment_summary")
        if isinstance(delivery_report.get("resolved_treatment_summary"), dict)
        else {}
    )
    if int(resolved_treatments.get("unique_header_variant_count") or 0) < 1:
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "resolved_treatments_not_propagated",
                "resolved_treatment_summary": resolved_treatments,
            }
        )
    replay_contract = (
        delivery_report.get("reproducibility_contract")
        if isinstance(delivery_report.get("reproducibility_contract"), dict)
        else {}
    )
    replay_style = (
        replay_contract.get("style_replay")
        if isinstance(replay_contract.get("style_replay"), dict)
        else {}
    )
    replay_structure = (
        replay_contract.get("structure_replay")
        if isinstance(replay_contract.get("structure_replay"), dict)
        else {}
    )
    if (
        replay_contract.get("exists") is not True
        or replay_contract.get("contract_version") != "deck_reproducibility_contract_v1"
        or not str(replay_contract.get("style_seed") or "").strip()
        or _int_value(replay_contract.get("replay_command_count")) < 3
    ):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "replay_contract_not_propagated",
                "reproducibility_contract": replay_contract,
            }
        )
    if not replay_style.get("style_preset") or not isinstance(replay_style.get("header_variant_pool"), list):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "replay_style_not_propagated",
                "style_replay": replay_style,
            }
        )
    if not isinstance(replay_structure.get("slide_variant_mix"), list) or not replay_structure.get("slide_variant_mix"):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "replay_structure_not_propagated",
                "structure_replay": replay_structure,
            }
        )
    nested_replay = (
        delivery_report.get("readiness", {}).get("reproducibility_contract")
        if isinstance(delivery_report.get("readiness"), dict)
        else {}
    )
    if not isinstance(nested_replay, dict) or nested_replay.get("style_seed") != replay_contract.get("style_seed"):
        failures.append({"step": "delivery_readiness", "reason": "readiness_replay_contract_not_nested"})

    quality_context = (
        delivery_report.get("quality_context")
        if isinstance(delivery_report.get("quality_context"), dict)
        else {}
    )
    slide_quality = (
        quality_context.get("slide_quality_contract")
        if isinstance(quality_context.get("slide_quality_contract"), dict)
        else {}
    )
    outline_quality = (
        quality_context.get("outline_quality_alignment")
        if isinstance(quality_context.get("outline_quality_alignment"), dict)
        else {}
    )
    if (
        slide_quality.get("exists") is not True
        or slide_quality.get("contract_version") != "slide_quality_contract_v1"
        or slide_quality.get("min_title_pt") != 24
        or slide_quality.get("fail_on_awkward_whitespace") is not True
        or _int_value(slide_quality.get("required_command_count")) < 4
    ):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "slide_quality_contract_not_propagated",
                "quality_context": quality_context,
            }
        )
    if (
        outline_quality.get("present") is not True
        or outline_quality.get("persisted") is not True
        or outline_quality.get("contract_version") != "slide_quality_contract_v1"
        or _int_value(outline_quality.get("readability_target_count")) < 4
        or _int_value(outline_quality.get("layout_target_count")) < 4
        or _int_value(outline_quality.get("qa_gate_count")) < 3
    ):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "outline_quality_alignment_not_propagated",
                "quality_context": quality_context,
            }
        )
    nested_quality = (
        delivery_report.get("readiness", {}).get("quality_context")
        if isinstance(delivery_report.get("readiness"), dict)
        else {}
    )
    nested_slide_quality = (
        nested_quality.get("slide_quality_contract")
        if isinstance(nested_quality.get("slide_quality_contract"), dict)
        else {}
    )
    if (
        not isinstance(nested_quality, dict)
        or nested_slide_quality.get("contract_version") != slide_quality.get("contract_version")
    ):
        failures.append({"step": "delivery_readiness", "reason": "readiness_quality_context_not_nested"})

    layout_density = (
        delivery_report.get("layout_density")
        if isinstance(delivery_report.get("layout_density"), dict)
        else {}
    )
    density_scores = (
        layout_density.get("density_score_by_slide")
        if isinstance(layout_density.get("density_score_by_slide"), list)
        else []
    )
    if (
        layout_density.get("exists") is not True
        or _int_value(layout_density.get("slide_count")) < 1
        or _int_value(layout_density.get("content_slide_count")) < 1
        or not density_scores
    ):
        failures.append(
            {
                "step": "delivery_readiness",
                "reason": "layout_density_not_propagated",
                "layout_density": layout_density,
            }
        )
    nested_density = (
        delivery_report.get("readiness", {}).get("layout_density")
        if isinstance(delivery_report.get("readiness"), dict)
        else {}
    )
    if (
        not isinstance(nested_density, dict)
        or nested_density.get("density_score_by_slide") != density_scores
    ):
        failures.append({"step": "delivery_readiness", "reason": "readiness_layout_density_not_nested"})

    delivery_markdown = (
        (workspace / "build" / "delivery_readiness.md").read_text(encoding="utf-8")
        if (workspace / "build" / "delivery_readiness.md").exists()
        else ""
    )
    next_action_markdown = (
        (workspace / "build" / "delivery_next_action.md").read_text(encoding="utf-8")
        if (workspace / "build" / "delivery_next_action.md").exists()
        else ""
    )
    for label, text in (
        ("delivery_readiness_markdown", delivery_markdown),
        ("delivery_next_action_markdown", next_action_markdown),
    ):
        for snippet in (
            "Replay contract",
            "Replay style",
            "Source inventory",
            "data/assay_readouts.csv",
            "Resolved header variants",
            "Slide quality contract",
            "Outline quality alignment",
            "Layout density",
        ):
            if snippet not in text:
                failures.append(
                    {
                        "step": label,
                        "reason": "reproducibility_context_missing",
                        "snippet": snippet,
                    }
                )

    advance_inventory = (
        advance_report.get("workspace_source_inventory")
        if isinstance(advance_report.get("workspace_source_inventory"), dict)
        else {}
    )
    if _int_value(advance_inventory.get("data_file_count")) < 1:
        failures.append({"step": "advance_delivery", "reason": "source_inventory_not_propagated"})
    advance_treatments = (
        advance_report.get("resolved_treatment_summary")
        if isinstance(advance_report.get("resolved_treatment_summary"), dict)
        else {}
    )
    if int(advance_treatments.get("unique_header_variant_count") or 0) < 1:
        failures.append({"step": "advance_delivery", "reason": "resolved_treatments_not_propagated"})
    advance_replay = (
        advance_report.get("reproducibility_contract")
        if isinstance(advance_report.get("reproducibility_contract"), dict)
        else {}
    )
    advance_replay_style = (
        advance_replay.get("style_replay")
        if isinstance(advance_replay.get("style_replay"), dict)
        else {}
    )
    if (
        advance_replay.get("style_seed") != replay_contract.get("style_seed")
        or advance_replay.get("contract_version") != "deck_reproducibility_contract_v1"
        or _int_value(advance_replay.get("replay_command_count")) < 3
        or not advance_replay_style.get("style_preset")
    ):
        failures.append({"step": "advance_delivery", "reason": "replay_contract_not_propagated", "reproducibility_contract": advance_replay})
    advance_quality = (
        advance_report.get("quality_context")
        if isinstance(advance_report.get("quality_context"), dict)
        else {}
    )
    advance_slide_quality = (
        advance_quality.get("slide_quality_contract")
        if isinstance(advance_quality.get("slide_quality_contract"), dict)
        else {}
    )
    advance_outline_quality = (
        advance_quality.get("outline_quality_alignment")
        if isinstance(advance_quality.get("outline_quality_alignment"), dict)
        else {}
    )
    if (
        advance_slide_quality.get("contract_version") != "slide_quality_contract_v1"
        or _int_value(advance_slide_quality.get("required_command_count")) < 4
        or advance_outline_quality.get("contract_version") != "slide_quality_contract_v1"
        or _int_value(advance_outline_quality.get("readability_target_count")) < 4
    ):
        failures.append(
            {
                "step": "advance_delivery",
                "reason": "quality_context_not_propagated",
                "quality_context": advance_quality,
            }
        )
    advance_density = (
        advance_report.get("layout_density")
        if isinstance(advance_report.get("layout_density"), dict)
        else {}
    )
    if (
        advance_density.get("density_score_by_slide") != density_scores
        or _int_value(advance_density.get("content_slide_count"))
        != _int_value(layout_density.get("content_slide_count"))
    ):
        failures.append(
            {
                "step": "advance_delivery",
                "reason": "layout_density_not_propagated",
                "layout_density": advance_density,
            }
        )
    steps = advance_report.get("steps") if isinstance(advance_report.get("steps"), list) else []
    first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
    step_replay = (
        first_step.get("reproducibility_contract")
        if isinstance(first_step.get("reproducibility_contract"), dict)
        else {}
    )
    if step_replay.get("style_seed") != replay_contract.get("style_seed"):
        failures.append({"step": "advance_delivery", "reason": "step_replay_contract_not_propagated"})
    step_quality = (
        first_step.get("quality_context")
        if isinstance(first_step.get("quality_context"), dict)
        else {}
    )
    step_slide_quality = (
        step_quality.get("slide_quality_contract")
        if isinstance(step_quality.get("slide_quality_contract"), dict)
        else {}
    )
    if step_slide_quality.get("contract_version") != "slide_quality_contract_v1":
        failures.append({"step": "advance_delivery", "reason": "step_quality_context_not_propagated"})
    step_density = (
        first_step.get("layout_density")
        if isinstance(first_step.get("layout_density"), dict)
        else {}
    )
    if step_density.get("density_score_by_slide") != density_scores:
        failures.append({"step": "advance_delivery", "reason": "step_layout_density_not_propagated"})


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the fast reproducible deck workflow smoke."
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
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-workflow-"))
    )
    if workspace.exists() and any(workspace.iterdir()):
        print(
            json.dumps(
                {
                    "passed": False,
                    "workspace": str(workspace),
                    "failures": [{"step": "workspace", "reason": "workspace_must_be_empty"}],
                },
                indent=2,
            )
        )
        return 1
    workspace.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    build_dir = workspace / "build"
    summary_path = build_dir / "reproducible_workflow_smoke.json"
    passed = False

    try:
        _run_checked(
            [
                py,
                str(repo / "scripts" / "run_outline_authoring_handoff_smoke.py"),
                "--workspace",
                str(workspace),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        if failures:
            raise RuntimeError("outline handoff setup failed")

        _run_checked(
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--qa",
                "--skip-render",
                "--fail-on-planning-warnings",
                "--fail-on-whitespace-warnings",
                "--overwrite",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        _run_checked(
            [
                py,
                str(repo / "scripts" / "report_delivery_readiness.py"),
                "--workspace",
                str(workspace),
                "--allow-skip-render",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )
        _run_checked(
            [
                py,
                str(repo / "scripts" / "advance_delivery.py"),
                "--workspace",
                str(workspace),
                "--allow-skip-render",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )

        outline_smoke = _load_json(build_dir / "outline_authoring_handoff_smoke.json")
        build_report = _load_json(build_dir / "build_workspace_report.json")
        delivery_report = _load_json(build_dir / "delivery_readiness.json")
        advance_report = _load_json(build_dir / "delivery_advance_report.json")
        _assert_clean_build(
            workspace=workspace,
            outline_smoke=outline_smoke if isinstance(outline_smoke, dict) else {},
            build_report=build_report if isinstance(build_report, dict) else {},
            delivery_report=delivery_report if isinstance(delivery_report, dict) else {},
            advance_report=advance_report if isinstance(advance_report, dict) else {},
            failures=failures,
        )

        passed = not failures
        qa_counts = (
            build_report.get("reports", {}).get("qa", {}).get("counts", {})
            if isinstance(build_report, dict)
            else {}
        )
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "outline_handoff_passed": outline_smoke.get("passed") if isinstance(outline_smoke, dict) else None,
            "build_status": build_report.get("run", {}).get("status") if isinstance(build_report, dict) else None,
            "delivery_status": delivery_report.get("delivery_status") if isinstance(delivery_report, dict) else None,
            "delivery_warning_reasons": delivery_report.get("warning_reasons") if isinstance(delivery_report, dict) else None,
            "delivery_next_action": (
                delivery_report.get("recommended_next_action", {}).get("kind")
                if isinstance(delivery_report, dict)
                else None
            ),
            "delivery_source_inventory": (
                delivery_report.get("workspace_source_inventory")
                if isinstance(delivery_report, dict)
                else None
            ),
            "delivery_resolved_treatments": (
                delivery_report.get("resolved_treatment_summary")
                if isinstance(delivery_report, dict)
                else None
            ),
            "delivery_reproducibility_contract": (
                delivery_report.get("reproducibility_contract")
                if isinstance(delivery_report, dict)
                else None
            ),
            "delivery_layout_density": (
                delivery_report.get("layout_density")
                if isinstance(delivery_report, dict)
                else None
            ),
            "advance_decision": (
                advance_report.get("decision")
                if isinstance(advance_report, dict)
                else None
            ),
            "advance_layout_density": (
                advance_report.get("layout_density")
                if isinstance(advance_report, dict)
                else None
            ),
            "qa_counts": qa_counts,
            "failures": failures,
            "commands": command_results,
        }
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "outline_handoff_passed",
                        "build_status",
                        "delivery_status",
                        "delivery_warning_reasons",
                        "delivery_next_action",
                        "advance_decision",
                        "delivery_layout_density",
                        "advance_layout_density",
                        "qa_counts",
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
            summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1
    finally:
        _cleanup_workspace(workspace, created_temp=created_temp, keep=args.keep_workspace, passed=passed)


if __name__ == "__main__":
    raise SystemExit(main())
