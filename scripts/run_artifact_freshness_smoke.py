#!/usr/bin/env python3
"""Smoke check that stale local data blocks generated-artifact delivery."""

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


def _append_drift_row(path: Path) -> None:
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write("C01,58.3,17.2\n")


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _issue_messages(payload: dict[str, Any]) -> list[str]:
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    messages: list[str] = []
    for issue in issues:
        if isinstance(issue, dict) and isinstance(issue.get("message"), str):
            messages.append(issue["message"])
    return messages


def _recommendation_kinds(payload: dict[str, Any]) -> set[str]:
    recommendations = (
        payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
    )
    return {
        str(item.get("kind"))
        for item in recommendations
        if isinstance(item, dict) and item.get("kind")
    }


def _stale_paths(freshness: dict[str, Any]) -> list[str]:
    stale = freshness.get("stale_files") if isinstance(freshness.get("stale_files"), list) else []
    paths: list[str] = []
    for item in stale:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            paths.append(item["path"])
    return paths


def _stale_statuses(freshness: dict[str, Any]) -> set[str]:
    stale = freshness.get("stale_files") if isinstance(freshness.get("stale_files"), list) else []
    return {
        str(item.get("status"))
        for item in stale
        if isinstance(item, dict) and item.get("status")
    }


def _assert_delivery_artifact_context(
    failures: list[dict[str, Any]],
    *,
    delivery: dict[str, Any],
    delivery_advance: dict[str, Any],
    next_action_markdown: str,
    label: str,
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
    if manifest.get("output_count") != 1 or manifest.get("output_ids") != ["run_readout_signal"]:
        failures.append(
            {
                "step": label,
                "reason": "artifact_context_manifest_missing",
                "artifact_context": context,
            }
        )
    if manifest.get("analysis_summary") != "assets/analysis_summary.json":
        failures.append(
            {
                "step": label,
                "reason": "artifact_context_analysis_summary_missing",
                "analysis_summary": manifest.get("analysis_summary"),
            }
        )
    quality_counts = manifest.get("figure_quality_counts")
    if not isinstance(quality_counts, dict) or quality_counts.get("ok") != 1:
        failures.append(
            {
                "step": label,
                "reason": "artifact_context_figure_quality_missing",
                "figure_quality_counts": quality_counts,
            }
        )
    if selection.get("binding_count") != 1 or selection.get("bound_output_ids") != ["run_readout_signal"]:
        failures.append(
            {
                "step": label,
                "reason": "artifact_context_selection_missing",
                "artifact_selection": selection,
            }
        )
    nested_context = delivery.get("readiness", {}).get("artifact_context")
    if not isinstance(nested_context, dict) or not nested_context.get("artifact_manifest"):
        failures.append(
            {
                "step": label,
                "reason": "nested_readiness_artifact_context_missing",
                "readiness": delivery.get("readiness"),
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
    if advance_manifest.get("output_ids") != ["run_readout_signal"]:
        failures.append(
            {
                "step": label,
                "reason": "advance_artifact_context_not_carried",
                "artifact_context": advance_context,
            }
        )
    steps = delivery_advance.get("steps") if isinstance(delivery_advance.get("steps"), list) else []
    first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
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
    if first_step_manifest.get("output_ids") != ["run_readout_signal"]:
        failures.append(
            {
                "step": label,
                "reason": "advance_step_artifact_context_not_carried",
                "steps": steps,
            }
        )
    for needle in (
        "## Artifact Context",
        "Artifact manifest:",
        "assets/analysis_summary.json",
        "Figure quality:",
        "Bound artifact targets:",
        "run_readout_signal",
    ):
        if needle not in next_action_markdown:
            failures.append(
                {
                    "step": f"{label}_markdown",
                    "reason": "missing_artifact_context_text",
                    "needle": needle,
                }
            )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the generated-artifact source-freshness smoke check."
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


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-artifact-freshness-"))
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
        init_cmd = [
            py,
            str(repo / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            "Artifact Freshness Smoke",
            "--style-preset",
            "lab-report",
        ]
        build_cmd = [
            py,
            str(repo / "scripts" / "build_workspace.py"),
            "--workspace",
            str(workspace),
            "--fast-first-pass",
        ]
        planning_cmd = [
            py,
            str(repo / "scripts" / "validate_planning.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(build_dir / "artifact_freshness_planning.json"),
        ]
        readiness_cmd = [
            py,
            str(repo / "scripts" / "report_workspace_readiness.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(build_dir / "artifact_freshness_readiness.json"),
        ]
        delivery_cmd = [
            py,
            str(repo / "scripts" / "report_delivery_readiness.py"),
            "--workspace",
            str(workspace),
            "--allow-skip-render",
            "--report",
            str(build_dir / "artifact_freshness_delivery.json"),
            "--markdown-report",
            str(build_dir / "artifact_freshness_delivery.md"),
        ]
        delivery_advance_cmd = [
            py,
            str(repo / "scripts" / "advance_delivery.py"),
            "--workspace",
            str(workspace),
            "--allow-skip-render",
            "--report",
            str(build_dir / "artifact_freshness_delivery_advance.json"),
            "--next-action-markdown",
            str(build_dir / "artifact_freshness_delivery_next_action.md"),
            "--delivery-report",
            str(build_dir / "artifact_freshness_delivery.json"),
            "--delivery-markdown",
            str(build_dir / "artifact_freshness_delivery.md"),
            "--no-refresh-readiness",
        ]
        advance_cmd = [
            py,
            str(repo / "scripts" / "advance_workspace.py"),
            "--workspace",
            str(workspace),
            "--execute",
            "--max-steps",
            "2",
            "--report",
            str(build_dir / "artifact_freshness_advance.json"),
            "--next-action-markdown",
            str(build_dir / "artifact_freshness_next_action.md"),
            "--readiness-report",
            str(build_dir / "artifact_freshness_readiness_after_advance.json"),
        ]
        delivery_after_refresh_cmd = [
            py,
            str(repo / "scripts" / "report_delivery_readiness.py"),
            "--workspace",
            str(workspace),
            "--allow-skip-render",
            "--report",
            str(build_dir / "artifact_freshness_delivery_after_refresh.json"),
            "--markdown-report",
            str(build_dir / "artifact_freshness_delivery_after_refresh.md"),
        ]

        result = _run(init_cmd, cwd=repo)
        command_results.append(
            {"command": init_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]}
        )
        data_path = workspace / "data" / "run_readout.csv"
        _write_fixture_csv(data_path)
        result = _run(build_cmd, cwd=repo)
        command_results.append(
            {"command": build_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]}
        )
        _append_drift_row(data_path)

        for cmd, allowed in [
            (planning_cmd, {0, 1}),
            (readiness_cmd, {0, 1}),
            (delivery_cmd, {0, 1, 2}),
            (delivery_advance_cmd, {0, 1, 2}),
        ]:
            result = _run(cmd, cwd=repo, allowed_returncodes=allowed)
            command_results.append(
                {
                    "command": cmd,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-1200:],
                }
            )

        planning = _load_json(build_dir / "artifact_freshness_planning.json")
        readiness = _load_json(build_dir / "artifact_freshness_readiness.json")
        delivery = _load_json(build_dir / "artifact_freshness_delivery.json")
        delivery_advance = _load_json(build_dir / "artifact_freshness_delivery_advance.json")
        delivery_next_action_markdown = (
            build_dir / "artifact_freshness_delivery_next_action.md"
        ).read_text(encoding="utf-8")
        build_report = _load_json(build_dir / "build_workspace_report.json")

        planning_messages = _issue_messages(planning)
        if planning.get("error_count") != 0:
            failures.append(
                {
                    "step": "validate_planning",
                    "reason": "unexpected_errors",
                    "error_count": planning.get("error_count"),
                }
            )
        if int(planning.get("warning_count") or 0) < 2:
            failures.append(
                {
                    "step": "validate_planning",
                    "reason": "expected_stale_artifact_warnings",
                    "warning_count": planning.get("warning_count"),
                }
            )
        if not any("analysis_metadata.source_sha256 does not match current source file" in msg for msg in planning_messages):
            failures.append(
                {
                    "step": "validate_planning",
                    "reason": "missing_source_hash_warning",
                    "messages": planning_messages,
                }
            )
        if not any("appears older than source/script 'data/run_readout.csv'" in msg for msg in planning_messages):
            failures.append(
                {
                    "step": "validate_planning",
                    "reason": "missing_stale_output_warning",
                    "messages": planning_messages,
                }
            )

        readiness_freshness = (
            readiness.get("last_build", {}).get("source_freshness")
            if isinstance(readiness.get("last_build"), dict)
            else {}
        )
        if not isinstance(readiness_freshness, dict):
            readiness_freshness = {}
        if readiness.get("status") != "needs_attention":
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "unexpected_status",
                    "status": readiness.get("status"),
                }
            )
        status_reasons = readiness.get("status_reasons") if isinstance(readiness.get("status_reasons"), list) else []
        for reason in ("validator_warnings", "open_recommendations"):
            if reason not in status_reasons:
                failures.append(
                    {
                        "step": "workspace_readiness",
                        "reason": "missing_status_reason",
                        "expected": reason,
                        "status_reasons": status_reasons,
                    }
                )
        next_action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
        if next_action.get("kind") != "refresh_generated_artifacts":
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "unexpected_next_action",
                    "next_action": next_action,
                }
            )
        if next_action.get("action_type") != "run_command":
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "refresh_action_not_runnable",
                    "next_action": next_action,
                }
            )
        recommendation_kinds = _recommendation_kinds(readiness)
        for kind in ("refresh_generated_artifacts", "resolve_planning_warnings", "rebuild_stale_build"):
            if kind not in recommendation_kinds:
                failures.append(
                    {
                        "step": "workspace_readiness",
                        "reason": "missing_recommendation",
                        "expected": kind,
                        "recommendation_kinds": sorted(recommendation_kinds),
                    }
                )
        stale_paths = _stale_paths(readiness_freshness)
        stale_statuses = _stale_statuses(readiness_freshness)
        if readiness_freshness.get("checked") is not True or readiness_freshness.get("stale_count") != 1:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "unexpected_source_freshness",
                    "source_freshness": readiness_freshness,
                }
            )
        if stale_paths != ["data/run_readout.csv"] or stale_statuses != {"changed_since_build"}:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "unexpected_stale_source_files",
                    "stale_paths": stale_paths,
                    "stale_statuses": sorted(stale_statuses),
                }
            )

        delivery_freshness = delivery.get("source_freshness") if isinstance(delivery.get("source_freshness"), dict) else {}
        if delivery.get("delivery_status") != "blocked":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_delivery_status",
                    "delivery_status": delivery.get("delivery_status"),
                }
            )
        if delivery.get("blocking_reasons") != ["source_changed_since_build"]:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_blocking_reasons",
                    "blocking_reasons": delivery.get("blocking_reasons"),
                }
            )
        warning_reasons = delivery.get("warning_reasons") if isinstance(delivery.get("warning_reasons"), list) else []
        for reason in ("fast_first_pass_not_final", "source_readiness_needs_attention"):
            if reason not in warning_reasons:
                failures.append(
                    {
                        "step": "delivery_readiness",
                        "reason": "missing_warning_reason",
                        "expected": reason,
                        "warning_reasons": warning_reasons,
                    }
                )
        delivery_action = (
            delivery.get("recommended_next_action")
            if isinstance(delivery.get("recommended_next_action"), dict)
            else {}
        )
        if delivery_action.get("kind") != "refresh_generated_artifacts":
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_recommended_next_action",
                    "recommended_next_action": delivery_action,
                }
            )
        gates = delivery.get("gates") if isinstance(delivery.get("gates"), dict) else {}
        expected_gates = {
            "source_readiness_ready": False,
            "source_freshness_current": False,
            "build_report_exists": True,
            "output_pptx_exists": True,
            "build_succeeded": True,
            "qa_run": True,
            "fast_first_pass": True,
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
        if delivery_freshness.get("checked") is not True or delivery_freshness.get("stale_count") != 1:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "unexpected_delivery_source_freshness",
                    "source_freshness": delivery_freshness,
                }
            )
        if _stale_paths(delivery_freshness) != ["data/run_readout.csv"]:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "delivery_stale_path_missing",
                    "stale_paths": _stale_paths(delivery_freshness),
                }
            )
        if delivery_advance.get("decision") != "dry_run_command_available":
            failures.append(
                {
                    "step": "advance_delivery",
                    "reason": "unexpected_decision",
                    "decision": delivery_advance.get("decision"),
                    "final_delivery_status": delivery_advance.get("final_delivery_status"),
                }
            )
        advance_action = (
            delivery_advance.get("final_recommended_next_action")
            if isinstance(delivery_advance.get("final_recommended_next_action"), dict)
            else {}
        )
        if advance_action.get("kind") != "refresh_generated_artifacts":
            failures.append(
                {
                    "step": "advance_delivery",
                    "reason": "unexpected_recommended_next_action",
                    "final_recommended_next_action": advance_action,
                }
            )
        _assert_delivery_artifact_context(
            failures,
            delivery=delivery,
            delivery_advance=delivery_advance,
            next_action_markdown=delivery_next_action_markdown,
            label="advance_delivery",
        )

        source_files = build_report.get("source_files") if isinstance(build_report.get("source_files"), dict) else {}
        source_snapshot = source_files.get("artifact_source_run_readout_signal_source")
        if not isinstance(source_snapshot, dict) or source_snapshot.get("path") != "data/run_readout.csv":
            failures.append(
                {
                    "step": "build_report",
                    "reason": "missing_artifact_source_snapshot",
                    "source_snapshot": source_snapshot,
                }
            )

        result = _run(advance_cmd, cwd=repo)
        command_results.append(
            {
                "command": advance_cmd,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        result = _run(delivery_after_refresh_cmd, cwd=repo, allowed_returncodes={0, 1})
        command_results.append(
            {
                "command": delivery_after_refresh_cmd,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        readiness_after = _load_json(build_dir / "artifact_freshness_readiness_after_advance.json")
        delivery_after = _load_json(build_dir / "artifact_freshness_delivery_after_refresh.json")
        advance_report = _load_json(build_dir / "artifact_freshness_advance.json")
        if readiness_after.get("status") != "ready":
            failures.append(
                {
                    "step": "advance_workspace",
                    "reason": "readiness_not_ready_after_refresh",
                    "status": readiness_after.get("status"),
                    "next_action": readiness_after.get("next_action"),
                }
            )
        advance_steps = advance_report.get("steps") if isinstance(advance_report.get("steps"), list) else []
        if not any(
            isinstance(step, dict)
            and step.get("next_action", {}).get("kind") == "refresh_generated_artifacts"
            and step.get("command_returncode") == 0
            for step in advance_steps
        ):
            failures.append(
                {
                    "step": "advance_workspace",
                    "reason": "refresh_step_not_recorded",
                    "steps": advance_steps,
                }
            )
        if delivery_after.get("delivery_status") != "needs_attention":
            failures.append(
                {
                    "step": "delivery_after_refresh",
                    "reason": "unexpected_delivery_status",
                    "delivery_status": delivery_after.get("delivery_status"),
                }
            )
        if delivery_after.get("blocking_reasons") != []:
            failures.append(
                {
                    "step": "delivery_after_refresh",
                    "reason": "unexpected_blockers",
                    "blocking_reasons": delivery_after.get("blocking_reasons"),
                }
            )
        if delivery_after.get("warning_reasons") != ["fast_first_pass_not_final"]:
            failures.append(
                {
                    "step": "delivery_after_refresh",
                    "reason": "unexpected_warning_reasons",
                    "warning_reasons": delivery_after.get("warning_reasons"),
                }
            )
        after_freshness = (
            delivery_after.get("source_freshness")
            if isinstance(delivery_after.get("source_freshness"), dict)
            else {}
        )
        if after_freshness.get("checked") is not True or after_freshness.get("stale_count") != 0:
            failures.append(
                {
                    "step": "delivery_after_refresh",
                    "reason": "source_freshness_not_clean",
                    "source_freshness": after_freshness,
                }
            )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "planning_warning_count": planning.get("warning_count"),
            "readiness_status": readiness.get("status"),
            "readiness_recommendations": sorted(recommendation_kinds),
            "readiness_stale_paths": stale_paths,
            "delivery_status": delivery.get("delivery_status"),
            "delivery_blocking_reasons": delivery.get("blocking_reasons"),
            "delivery_warning_reasons": warning_reasons,
            "delivery_stale_paths": _stale_paths(delivery_freshness),
            "delivery_advance_decision": delivery_advance.get("decision"),
            "advance_refresh_executed": any(
                isinstance(step, dict)
                and step.get("next_action", {}).get("kind") == "refresh_generated_artifacts"
                and step.get("command_returncode") == 0
                for step in advance_steps
            ),
            "delivery_after_refresh_status": delivery_after.get("delivery_status"),
            "delivery_after_refresh_warnings": delivery_after.get("warning_reasons"),
            "failures": failures,
            "commands": command_results,
        }
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "artifact_freshness_smoke.json").write_text(
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
                        "planning_warning_count",
                        "readiness_status",
                        "readiness_recommendations",
                        "readiness_stale_paths",
                        "delivery_status",
                        "delivery_blocking_reasons",
                        "delivery_warning_reasons",
                        "delivery_stale_paths",
                        "delivery_advance_decision",
                        "advance_refresh_executed",
                        "delivery_after_refresh_status",
                        "delivery_after_refresh_warnings",
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
            (build_dir / "artifact_freshness_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
