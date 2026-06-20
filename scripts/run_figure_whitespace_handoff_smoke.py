#!/usr/bin/env python3
"""Smoke check high-whitespace generated figure handoff."""

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


OUTPUT_ID = "run_signal"
WHITESPACE_PAYLOAD = {
    "checked": True,
    "exterior_fraction": 0.62,
    "exterior_percent": 62.0,
    "high_exterior_whitespace": True,
    "content_bbox": [120, 80, 320, 220],
}


def _run(cmd: list[str], *, cwd: Path, allowed_returncodes: set[int] | None = None) -> subprocess.CompletedProcess[str]:
    allowed = allowed_returncodes if allowed_returncodes is not None else {0}
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


def _inject_high_whitespace(workspace: Path) -> None:
    manifest_path = workspace / "assets" / "artifacts_manifest.json"
    manifest = _load_json(manifest_path)
    for output in manifest.get("outputs", []):
        if not isinstance(output, dict):
            continue
        metadata = output.get("analysis_metadata") if isinstance(output.get("analysis_metadata"), dict) else {}
        metadata["image_whitespace"] = dict(WHITESPACE_PAYLOAD)
        output["analysis_metadata"] = metadata
    _write_json(manifest_path, manifest)

    summary_path = workspace / "assets" / "analysis_summary.json"
    summary = _load_json(summary_path)
    datasets = summary.get("datasets") if isinstance(summary.get("datasets"), list) else []
    for dataset in datasets:
        if not isinstance(dataset, dict):
            continue
        readability = dataset.get("readability") if isinstance(dataset.get("readability"), dict) else {}
        readability["image_whitespace"] = dict(WHITESPACE_PAYLOAD)
        dataset["readability"] = readability
    _write_json(summary_path, summary)


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run generated figure whitespace handoff smoke.")
    parser.add_argument("--workspace", default="", help="Workspace to create/use. Defaults to a temporary workspace.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep the temporary workspace after a passing run.")
    return parser.parse_args()


def _assert_planning(failures: list[dict[str, Any]], planning: dict[str, Any]) -> None:
    issues = planning.get("issues") if isinstance(planning.get("issues"), list) else []
    paths = [str(item.get("path") or "") for item in issues if isinstance(item, dict)]
    messages = [str(item.get("message") or "") for item in issues if isinstance(item, dict)]
    if planning.get("error_count") != 0 or planning.get("warning_count") != 2:
        failures.append(
            {
                "step": "planning",
                "error_count": planning.get("error_count"),
                "warning_count": planning.get("warning_count"),
                "paths": paths,
            }
        )
    expected_paths = [
        "design_brief.analysis_artifact_plan.artifact_manifest.outputs[0].analysis_metadata.image_whitespace",
        "design_brief.analysis_artifact_plan.analysis_summary.datasets[0].readability.image_whitespace",
    ]
    if paths != expected_paths:
        failures.append({"step": "planning", "reason": "unexpected_paths", "paths": paths})
    if any("62.0% exterior blank area" not in message for message in messages):
        failures.append({"step": "planning", "reason": "missing_exterior_percent", "messages": messages})


def _assert_readiness(failures: list[dict[str, Any]], readiness: dict[str, Any]) -> None:
    next_action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    manifest = (
        readiness.get("artifacts", {}).get("artifact_manifest")
        if isinstance(readiness.get("artifacts"), dict)
        else {}
    )
    quality_counts = manifest.get("figure_quality_counts") if isinstance(manifest, dict) else {}
    if readiness.get("status") != "needs_attention":
        failures.append({"step": "readiness", "status": readiness.get("status")})
    if next_action.get("kind") != "resolve_planning_warnings":
        failures.append({"step": "readiness", "reason": "wrong_next_action", "next_action": next_action})
    if next_action.get("warning_types") != ["figure_export_whitespace"]:
        failures.append({"step": "readiness", "reason": "wrong_warning_types", "warning_types": next_action.get("warning_types")})
    for field in (
        "assets/make_figures.py",
        "scripts/trim_image_whitespace.py",
        "assets/artifacts_manifest.json",
        "assets/analysis_summary.json",
        "figure_export_contract",
    ):
        if field not in next_action.get("suggested_fields", []):
            failures.append({"step": "readiness", "reason": "missing_suggested_field", "field": field})
    if quality_counts.get("needs_trim") != 1:
        failures.append({"step": "readiness", "reason": "quality_count_missing", "figure_quality_counts": quality_counts})


def _assert_advance(failures: list[dict[str, Any]], advance: dict[str, Any], prompt: str) -> None:
    if advance.get("decision") != "edit_sources_required":
        failures.append({"step": "advance", "decision": advance.get("decision")})
    plan = advance.get("source_edit_plan") if isinstance(advance.get("source_edit_plan"), list) else []
    if len(plan) != 2:
        failures.append({"step": "advance", "reason": "source_edit_count_bad", "source_edit_plan": plan})
        return
    for edit in plan:
        if edit.get("operation") != "trim_figure_export_whitespace":
            failures.append({"step": "advance", "reason": "wrong_operation", "edit": edit})
        for field in ("assets/make_figures.py", "scripts/trim_image_whitespace.py", "assets/artifacts_manifest.json"):
            if field not in edit.get("suggested_fields", []):
                failures.append({"step": "advance", "reason": "missing_field", "field": field, "edit": edit})
        if edit.get("artifact_output_ids") != [OUTPUT_ID]:
            failures.append({"step": "advance", "reason": "missing_output_id", "edit": edit})
        aliases = edit.get("artifact_aliases") if isinstance(edit.get("artifact_aliases"), list) else []
        if not aliases or "image:run_signal_figure" not in aliases[0]:
            failures.append({"step": "advance", "reason": "missing_aliases", "edit": edit})
        fix = str(edit.get("suggested_fix") or "")
        if "Trim the generated figure export" not in fix or "assets/make_figures.py" not in fix:
            failures.append({"step": "advance", "reason": "fix_not_specific", "edit": edit})
    for needle in (
        "Warning types: `figure_export_whitespace`",
        "`trim_figure_export_whitespace`",
        "scripts/trim_image_whitespace.py",
        "assets/make_figures.py",
        "62.0% exterior blank area",
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
        else Path(tempfile.mkdtemp(prefix="presentation-skill-figure-whitespace-"))
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
    try:
        setup_commands = [
            [
                py,
                str(repo / "scripts" / "init_deck_workspace.py"),
                "--workspace",
                str(workspace),
                "--title",
                "Figure Whitespace Handoff Smoke",
                "--style-preset",
                "lab-report",
            ],
        ]
        for cmd in setup_commands:
            result = _run(cmd, cwd=repo)
            command_results.append({"command": cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]})

        _write_fixture_csv(workspace / "data" / "run.csv")
        build_dir = workspace / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        workflow_commands = [
            [
                py,
                str(repo / "scripts" / "scaffold_figure_artifacts.py"),
                "--workspace",
                str(workspace),
                "--data-path",
                "data/run.csv",
                "--run",
                "--overwrite",
                "--report",
                str(build_dir / "figure_whitespace_scaffold.json"),
            ],
            [
                py,
                str(repo / "scripts" / "apply_artifact_manifest_bindings.py"),
                "--workspace",
                str(workspace),
                "--manifest",
                "assets/artifacts_manifest.json",
                "--auto-select",
                "--auto-select-mode",
                "lead",
                "--selection-out",
                str(workspace / "artifact_selections.auto.json"),
                "--report",
                str(build_dir / "figure_whitespace_bindings.json"),
            ],
        ]
        for cmd in workflow_commands:
            result = _run(cmd, cwd=repo)
            command_results.append({"command": cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]})

        _inject_high_whitespace(workspace)

        validation_commands = [
            [
                py,
                str(repo / "scripts" / "validate_planning.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(build_dir / "figure_whitespace_planning.json"),
            ],
            [
                py,
                str(repo / "scripts" / "report_workspace_readiness.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(build_dir / "figure_whitespace_readiness.json"),
            ],
            [
                py,
                str(repo / "scripts" / "advance_workspace.py"),
                "--workspace",
                str(workspace),
                "--max-steps",
                "1",
            ],
        ]
        for cmd in validation_commands:
            result = _run(cmd, cwd=repo, allowed_returncodes={0, 1})
            command_results.append({"command": cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1200:]})

        planning = _load_json(build_dir / "figure_whitespace_planning.json")
        readiness = _load_json(build_dir / "figure_whitespace_readiness.json")
        advance = _load_json(build_dir / "workspace_advance_report.json")
        prompt_path = build_dir / "workspace_next_action.md"
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""

        _assert_planning(failures, planning)
        _assert_readiness(failures, readiness)
        _assert_advance(failures, advance, prompt)

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "planning_counts": {
                "errors": planning.get("error_count"),
                "warnings": planning.get("warning_count"),
            },
            "readiness_status": readiness.get("status"),
            "next_action": readiness.get("next_action", {}),
            "source_edit_plan_count": len(advance.get("source_edit_plan", []))
            if isinstance(advance.get("source_edit_plan"), list)
            else 0,
            "failures": failures,
            "commands": command_results,
        }
        _write_json(build_dir / "figure_whitespace_handoff_smoke.json", summary)
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "planning_counts",
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
            _write_json(workspace / "build" / "figure_whitespace_handoff_smoke.json", summary)
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
