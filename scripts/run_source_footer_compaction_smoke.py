#!/usr/bin/env python3
"""Fast smoke for compact source-line footer provenance."""

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
) -> subprocess.CompletedProcess[str]:
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
    return result


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _long_source(label: str) -> str:
    return (
        f"{label}: Long full citation with authors, instrument metadata, assay "
        "conditions, accession detail, and run provenance that belongs on a "
        "References table slide instead of staying in tiny footer text."
    )


def _patch_workspace_sources(workspace: Path) -> None:
    design_path = workspace / "design_brief.json"
    design = _load_json(design_path)
    if not isinstance(design, dict):
        design = {}
    style_system = design.get("style_system") if isinstance(design.get("style_system"), dict) else {}
    style_system["style_preset"] = "lab-report"
    style_system["style_seed"] = "source-footer-compaction-smoke"
    style_system["style_mix_matrix"] = {
        "header_variant_pool": ["plain", "top-bottom-rule"],
        "footer_pool": ["source-line", "standard"],
        "figure_table_treatment_pool": ["figure-first", "table-first"],
        "mix_rule": "Keep footer compaction fixture reproducible.",
    }
    design["style_system"] = style_system
    renderer = design.get("renderer_treatments") if isinstance(design.get("renderer_treatments"), dict) else {}
    renderer["header_mode"] = "lab-clean"
    renderer["header_variant"] = "auto"
    renderer["footer_mode"] = "source-line"
    renderer["footer_page_numbers"] = True
    design["renderer_treatments"] = renderer
    _write_json(design_path, design)

    outline = {
        "title": "Source Footer Compaction Smoke",
        "deck_style": {
            "header_mode": "lab-clean",
            "header_variant": "auto",
            "footer_mode": "source-line",
            "footer_page_numbers": True,
            "footer_source_label": "Sources",
            "footer_refs_label": "Refs",
        },
        "slides": [
            {
                "slide_id": "s1",
                "type": "title",
                "title": "Source Footer Compaction Smoke",
                "subtitle": "Long footer provenance should move to References",
            },
            {
                "slide_id": "evidence-1",
                "type": "content",
                "variant": "standard",
                "title": "Evidence slide keeps only short source IDs",
                "body": [
                    "The slide keeps a compact source-line footer after the full citations move to an editable table."
                ],
                "footer_mode": "source-line",
                "footer": "Run summary",
                "sources": [
                    _long_source("Sanger confirmation"),
                    _long_source("qPCR calibration"),
                    _long_source("Sequencing panel"),
                ],
                "refs": [
                    _long_source("Protocol reference"),
                    _long_source("Validation memo"),
                ],
            },
        ],
    }
    _write_json(workspace / "outline.json", outline)

    content = _load_json(workspace / "content_plan.json")
    if not isinstance(content, dict):
        content = {}
    content["thesis"] = "Long source-line footer provenance should compact to short IDs."
    content["slide_plan"] = [
        {
            "slide_id": "s1",
            "role": "title",
            "message": "Open the footer compaction fixture.",
            "variant": "title",
            "visual_strategy": "title",
            "evidence_needs": [],
        },
        {
            "slide_id": "evidence-1",
            "role": "evidence",
            "message": "Show a sourced result with long provenance.",
            "variant": "standard",
            "visual_strategy": "clean lab report body with source-line footer",
            "evidence_needs": ["long footer provenance"],
        },
    ]
    content["narrative_arc"] = [
        {
            "label": "Footer provenance",
            "slides": ["evidence-1"],
            "purpose": "Exercise source footer compaction.",
        }
    ]
    _write_json(workspace / "content_plan.json", content)


def _preflight(
    repo: Path,
    workspace: Path,
    *,
    command_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(repo / "scripts" / "preflight.py"),
        "--outline",
        str(workspace / "outline.json"),
        "--design-brief",
        str(workspace / "design_brief.json"),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    command_results.append(
        {
            "command": cmd,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-1600:],
            "stderr_tail": result.stderr[-1600:],
        }
    )
    if result.returncode not in {0, 1}:
        failures.append({"step": "preflight.py", "returncode": result.returncode})
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"parse_error": result.stdout[-800:], "stderr_tail": result.stderr[-800:]}
    return payload if isinstance(payload, dict) else {}


def _issue_rules(payload: dict[str, Any]) -> list[str]:
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    return [
        str(issue.get("rule") or "")
        for issue in issues
        if isinstance(issue, dict) and str(issue.get("rule") or "")
    ]


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a focused source footer compaction smoke check.")
    parser.add_argument("--workspace", default="", help="Workspace to create/use. Defaults to a temporary workspace.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep the temporary workspace after a passing run.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-source-footer-"))
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

    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    passed = False

    try:
        _run_checked(
            [
                sys.executable,
                str(repo / "scripts" / "init_deck_workspace.py"),
                "--workspace",
                str(workspace),
                "--title",
                "Source Footer Compaction Smoke",
                "--style-preset",
                "lab-report",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        _patch_workspace_sources(workspace)

        pre_before = _preflight(repo, workspace, command_results=command_results, failures=failures)
        before_rules = _issue_rules(pre_before)
        if "source_line_footer_over_budget" not in before_rules:
            failures.append(
                {
                    "step": "preflight_before",
                    "reason": "missing_source_line_footer_over_budget",
                    "rules": before_rules,
                }
            )

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
        readiness_before = _load_json(workspace / "build" / "workspace_readiness.json")
        next_before = readiness_before.get("next_action") if isinstance(readiness_before.get("next_action"), dict) else {}
        if next_before.get("kind") != "compact_source_footers":
            failures.append({"step": "readiness_before", "reason": "wrong_next_action", "next_action": next_before})
        if next_before.get("slide_ids") != ["evidence-1"]:
            failures.append({"step": "readiness_before", "reason": "wrong_slide_ids", "slide_ids": next_before.get("slide_ids")})

        _run_checked(
            [
                sys.executable,
                str(repo / "scripts" / "advance_workspace.py"),
                "--workspace",
                str(workspace),
                "--execute",
                "--max-steps",
                "2",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )
        advance = _load_json(workspace / "build" / "workspace_advance_report.json")
        steps = advance.get("steps") if isinstance(advance.get("steps"), list) else []
        first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
        if first_step.get("decision") != "executed_command":
            failures.append({"step": "advance", "reason": "command_not_executed", "first_step": first_step})
        command_text = " ".join(str(part) for part in first_step.get("command", []))
        if "compact_source_footers.py" not in command_text:
            failures.append({"step": "advance", "reason": "wrong_command", "command": command_text})

        compaction_report = _load_json(workspace / "build" / "source_footer_compaction.json")
        if compaction_report.get("changed") is not True:
            failures.append({"step": "compaction_report", "reason": "not_changed", "report": compaction_report})
        if compaction_report.get("references_slides") != ["references"]:
            failures.append(
                {
                    "step": "compaction_report",
                    "reason": "unexpected_reference_slides",
                    "references_slides": compaction_report.get("references_slides"),
                }
            )
        compacted = compaction_report.get("compacted_slides") if isinstance(compaction_report.get("compacted_slides"), list) else []
        compacted_first = compacted[0] if compacted and isinstance(compacted[0], dict) else {}
        if compacted_first.get("slide_id") != "evidence-1":
            failures.append({"step": "compaction_report", "reason": "wrong_compacted_slide", "compacted": compacted})

        outline_after = _load_json(workspace / "outline.json")
        slides = outline_after.get("slides") if isinstance(outline_after.get("slides"), list) else []
        evidence_slide = next((slide for slide in slides if isinstance(slide, dict) and slide.get("slide_id") == "evidence-1"), {})
        refs_slide = next((slide for slide in slides if isinstance(slide, dict) and slide.get("slide_id") == "references"), {})
        if evidence_slide.get("sources") != ["S1-S3"] or evidence_slide.get("refs") != ["R1-R2"]:
            failures.append(
                {
                    "step": "outline_after",
                    "reason": "footer_ids_not_compacted",
                    "sources": evidence_slide.get("sources"),
                    "refs": evidence_slide.get("refs"),
                }
            )
        if not isinstance(refs_slide.get("source_footer_compaction"), dict):
            failures.append({"step": "outline_after", "reason": "missing_reference_slide_metadata", "refs_slide": refs_slide})
        rows = refs_slide.get("rows") if isinstance(refs_slide.get("rows"), list) else []
        if len(rows) != 5:
            failures.append({"step": "outline_after", "reason": "wrong_reference_row_count", "row_count": len(rows)})

        pre_after = _preflight(repo, workspace, command_results=command_results, failures=failures)
        after_rules = _issue_rules(pre_after)
        if "source_line_footer_over_budget" in after_rules:
            failures.append({"step": "preflight_after", "reason": "footer_budget_still_warns", "rules": after_rules})

        _run_checked(
            [
                sys.executable,
                str(repo / "scripts" / "compact_source_footers.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(workspace / "build" / "source_footer_compaction_again.json"),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        again_report = _load_json(workspace / "build" / "source_footer_compaction_again.json")
        if again_report.get("changed") is not False:
            failures.append({"step": "compaction_idempotence", "reason": "second_run_changed", "report": again_report})

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "preflight_before_rules": before_rules,
            "readiness_next_action": next_before,
            "advance_first_decision": first_step.get("decision"),
            "compaction_report": compaction_report,
            "preflight_after_rules": after_rules,
            "second_run_changed": again_report.get("changed"),
            "failures": failures,
            "commands": command_results,
        }
        _write_json(workspace / "build" / "source_footer_compaction_smoke.json", summary)
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "preflight_before_rules",
                        "advance_first_decision",
                        "preflight_after_rules",
                        "second_run_changed",
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
            _write_json(workspace / "build" / "source_footer_compaction_smoke.json", summary)
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
