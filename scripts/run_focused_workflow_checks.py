#!/usr/bin/env python3
"""Run the focused non-regression presentation-skill workflow checks."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CHECKS: dict[str, dict[str, str]] = {
    "deck-start": {
        "script": "run_deck_start_intake_smoke.py",
        "lane": "routing",
        "description": "Deck-start packet, intake answers, deterministic apply, and readiness summary.",
    },
    "design-contract": {
        "script": "run_design_contract_apply_smoke.py",
        "lane": "routing",
        "description": "Design-contract prompt/apply, choice resolution, planning validation, and readiness.",
    },
    "outline-handoff": {
        "script": "run_outline_authoring_handoff_smoke.py",
        "lane": "routing",
        "description": "Contract-aware outline handoff, deterministic apply, build, and render-free QA.",
    },
    "style-mix": {
        "script": "run_style_mix_repro_smoke.py",
        "lane": "style",
        "description": "Deterministic style-mix/header/footer resolution and lab-report header gallery QA.",
    },
    "header-gallery": {
        "script": "run_header_variant_gallery_smoke.py",
        "lane": "style",
        "description": "All-preset header variant gallery decks with clean render-free QA.",
    },
    "rendered-gallery": {
        "script": "run_rendered_header_gallery_smoke.py",
        "lane": "rendered",
        "description": "All-preset header variant gallery decks with real renders, nonblank image checks, and lab visual review.",
    },
    "rendered-data": {
        "script": "run_rendered_data_delivery_smoke.py",
        "lane": "rendered",
        "description": "Structured lab data workflow with rendered figure/chart/table triplet delivery readiness.",
    },
    "layout-polish": {
        "script": "run_layout_polish_handoff_smoke.py",
        "lane": "layout",
        "description": "Saved QA whitespace/readability warnings to exact source-edit handoffs.",
    },
    "readability-contract": {
        "script": "run_readability_contract_smoke.py",
        "lane": "layout",
        "description": "Rendered chart/table readability contracts to exact source-edit handoffs.",
    },
    "source-footers": {
        "script": "run_source_footer_compaction_smoke.py",
        "lane": "layout",
        "description": "Long source-line footer compaction and editable References table slide idempotence.",
    },
    "lab-footer-chrome": {
        "script": "run_lab_footer_chrome_smoke.py",
        "lane": "layout",
        "description": "Lab-report footer rule, source/ref line, page number, and plain/top-bottom header chrome.",
    },
    "artifact-quality": {
        "script": "run_generated_artifact_quality_smoke.py",
        "lane": "data",
        "description": "Generated artifact scaffold/inspect/bind/readiness quality path.",
    },
    "figure-whitespace": {
        "script": "run_figure_whitespace_handoff_smoke.py",
        "lane": "data",
        "description": "High-whitespace generated figures to trim/regenerate source-edit handoffs.",
    },
    "data-workflow": {
        "script": "run_data_artifact_workflow_smoke.py",
        "lane": "data",
        "description": "Local CSV fast-first-pass, artifact binding, render-free QA, and delivery handoff.",
    },
    "excel-workflow": {
        "script": "run_excel_artifact_workflow_smoke.py",
        "lane": "data",
        "description": "Excel workbook sheet scaffolding, artifact binding, provenance, and clean data QA.",
    },
    "artifact-triplet": {
        "script": "run_artifact_triplet_workflow_smoke.py",
        "lane": "data",
        "description": "Full figure/chart/table artifact binding, staged roles, and clean render-free QA.",
    },
    "artifact-freshness": {
        "script": "run_artifact_freshness_smoke.py",
        "lane": "data",
        "description": "Stale local data/source freshness warnings and delivery blocking behavior.",
    },
    "workflow": {
        "script": "run_reproducible_workflow_smoke.py",
        "lane": "workflow",
        "description": "End-to-end start/intake/design-contract/outline/QA/delivery handoff smoke.",
    },
}

PROFILES: dict[str, list[str]] = {
    "routing": ["deck-start", "design-contract", "outline-handoff", "workflow"],
    "style": ["style-mix", "header-gallery", "layout-polish", "readability-contract", "source-footers", "lab-footer-chrome"],
    "data": ["artifact-quality", "figure-whitespace", "data-workflow", "excel-workflow", "artifact-triplet", "artifact-freshness"],
    "rendered": ["rendered-gallery", "rendered-data"],
    "core": [
        "deck-start",
        "design-contract",
        "outline-handoff",
        "style-mix",
        "header-gallery",
        "layout-polish",
        "readability-contract",
        "source-footers",
        "lab-footer-chrome",
        "artifact-quality",
        "figure-whitespace",
        "data-workflow",
        "excel-workflow",
        "artifact-triplet",
        "artifact-freshness",
        "workflow",
    ],
}
PROFILES["all"] = list(PROFILES["core"])


def _split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _default_report_path() -> Path:
    return Path(tempfile.gettempdir()) / f"presentation-skill-focused-checks-{os.getpid()}.json"


def _resolve_checks(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    selected = _split_names(args.checks) if args.checks else list(PROFILES[args.profile])
    skipped = set(_split_names(args.skip))
    names = [name for name in _ordered_unique(selected) if name not in skipped]
    invalid = [name for name in names if name not in CHECKS]
    return names, invalid


def _run_check(
    *,
    repo: Path,
    name: str,
    timeout_seconds: int,
    output_tail_chars: int,
) -> dict[str, Any]:
    meta = CHECKS[name]
    command = [sys.executable, str(repo / "scripts" / meta["script"])]
    started = time.monotonic()
    result: dict[str, Any] = {
        "name": name,
        "lane": meta["lane"],
        "description": meta["description"],
        "command": command,
        "script": meta["script"],
        "timeout_seconds": timeout_seconds,
        "timed_out": False,
    }
    try:
        completed = subprocess.run(
            command,
            cwd=str(repo),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
        stdout = completed.stdout or ""
        result.update(
            {
                "returncode": completed.returncode,
                "passed": completed.returncode == 0,
                "stdout_tail": _tail_text(stdout, output_tail_chars),
            }
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        if isinstance(exc.stderr, str):
            stdout = f"{stdout}\n{exc.stderr}" if stdout else exc.stderr
        result.update(
            {
                "returncode": None,
                "passed": False,
                "timed_out": True,
                "stdout_tail": _tail_text(stdout, output_tail_chars),
            }
        )
    finally:
        result["duration_ms"] = int(round((time.monotonic() - started) * 1000))
    return result


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _print_summary(report: dict[str, Any], *, report_path: Path) -> None:
    status = "PASS" if report["passed"] else "FAIL"
    duration = report.get("duration_ms", 0)
    jobs = report.get("effective_jobs", 1)
    print(f"Focused workflow checks: {status} in {duration} ms (jobs={jobs})")
    for result in report["results"]:
        item_status = "PASS" if result.get("passed") else "FAIL"
        timeout = " timeout" if result.get("timed_out") else ""
        print(f"- {item_status} {result['name']} ({result['duration_ms']} ms){timeout}")
    if report.get("skipped_due_to_fail_fast"):
        skipped = ", ".join(report["skipped_due_to_fail_fast"])
        print(f"Skipped after fail-fast: {skipped}")
    if report.get("first_failed_check"):
        print(f"First failed check: {report['first_failed_check']}")
    print(f"Report: {report_path}")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run focused fast presentation-skill checks and emit one compact JSON report."
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="core",
        help="Named check profile to run when --checks is not supplied.",
    )
    parser.add_argument(
        "--checks",
        default="",
        help="Comma-separated check names to run instead of the selected profile.",
    )
    parser.add_argument(
        "--skip",
        default="",
        help="Comma-separated check names to remove from the selected profile.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing check. Forces serial execution.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of checks to run concurrently. Use 1 for serial execution.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=240,
        help="Per-check timeout.",
    )
    parser.add_argument(
        "--output-tail-chars",
        type=int,
        default=3000,
        help="Maximum stdout tail characters kept per check in the JSON report.",
    )
    parser.add_argument(
        "--report",
        default=str(_default_report_path()),
        help="JSON report path. Relative paths are resolved from the repo root.",
    )
    return parser.parse_args()


def _run_checks(
    *,
    repo: Path,
    checks: list[str],
    jobs: int,
    fail_fast: bool,
    timeout_seconds: int,
    output_tail_chars: int,
) -> tuple[list[dict[str, Any]], list[str], int]:
    effective_jobs = max(1, min(jobs, max(1, len(checks))))
    if fail_fast:
        effective_jobs = 1

    if effective_jobs == 1:
        results: list[dict[str, Any]] = []
        skipped_due_to_fail_fast: list[str] = []
        for index, name in enumerate(checks):
            result = _run_check(
                repo=repo,
                name=name,
                timeout_seconds=timeout_seconds,
                output_tail_chars=output_tail_chars,
            )
            results.append(result)
            if fail_fast and not result.get("passed"):
                skipped_due_to_fail_fast = checks[index + 1 :]
                break
        return results, skipped_due_to_fail_fast, effective_jobs

    result_by_name: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=effective_jobs) as pool:
        future_by_name = {
            pool.submit(
                _run_check,
                repo=repo,
                name=name,
                timeout_seconds=timeout_seconds,
                output_tail_chars=output_tail_chars,
            ): name
            for name in checks
        }
        for future in as_completed(future_by_name):
            name = future_by_name[future]
            result_by_name[name] = future.result()
    ordered_results = [result_by_name[name] for name in checks if name in result_by_name]
    return ordered_results, [], effective_jobs


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    report_path = Path(args.report).expanduser()
    if not report_path.is_absolute():
        report_path = repo / report_path

    checks, invalid = _resolve_checks(args)
    started_wall = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    if invalid:
        report = {
            "schema": "presentation_skill_focused_checks_v1",
            "passed": False,
            "profile": args.profile,
            "checks_requested": checks,
            "invalid_checks": invalid,
            "available_checks": sorted(CHECKS),
            "requested_jobs": args.jobs,
            "effective_jobs": 0,
            "started_at": started_wall,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": int(round((time.monotonic() - started) * 1000)),
            "results": [],
            "first_failed_check": None,
        }
        _write_json(report_path, report)
        _print_summary(report, report_path=report_path)
        return 2

    results, skipped_due_to_fail_fast, effective_jobs = _run_checks(
        repo=repo,
        checks=checks,
        jobs=args.jobs,
        fail_fast=args.fail_fast,
        timeout_seconds=args.timeout_seconds,
        output_tail_chars=args.output_tail_chars,
    )

    first_failed = next((result["name"] for result in results if not result.get("passed")), None)
    report = {
        "schema": "presentation_skill_focused_checks_v1",
        "passed": first_failed is None,
        "profile": args.profile,
        "checks_requested": checks,
        "checks_run": [result["name"] for result in results],
        "skipped_by_request": _split_names(args.skip),
        "skipped_due_to_fail_fast": skipped_due_to_fail_fast,
        "requested_jobs": args.jobs,
        "effective_jobs": effective_jobs,
        "parallel": effective_jobs > 1,
        "started_at": started_wall,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int(round((time.monotonic() - started) * 1000)),
        "first_failed_check": first_failed,
        "failed_count": sum(1 for result in results if not result.get("passed")),
        "results": results,
    }
    _write_json(report_path, report)
    _print_summary(report, report_path=report_path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
