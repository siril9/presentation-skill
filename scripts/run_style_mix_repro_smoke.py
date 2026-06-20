#!/usr/bin/env python3
"""Fast smoke check for reproducible style-mix resolution."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from style_treatment_profiles import SUPPORTED_HEADER_VARIANTS, preset_treatment_profile


STYLE_SEED_A = "style-mix-smoke-a"
STYLE_SEED_B = "style-mix-smoke-b"
SUPPORTED_REPORT_HEADER_VARIANTS = list(SUPPORTED_HEADER_VARIANTS)


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _preset_names(repo: Path) -> list[str]:
    script = (
        "const {listPresets}=require('./templates/pptxgenjs/presets.js'); "
        "console.log(JSON.stringify(listPresets()));"
    )
    result = _run(["node", "-e", script], cwd=repo)
    if result.returncode != 0:
        raise RuntimeError(result.stdout)
    names = json.loads(result.stdout)
    return [str(name) for name in names]


def _preset_profile_summary(repo: Path, failures: list[dict[str, Any]]) -> dict[str, Any]:
    presets = _preset_names(repo)
    records: list[dict[str, Any]] = []
    supported_headers = set(SUPPORTED_REPORT_HEADER_VARIANTS)
    for preset in presets:
        profile = preset_treatment_profile(preset)
        mix = profile.get("style_mix_matrix") if isinstance(profile.get("style_mix_matrix"), dict) else {}
        header_pool = mix.get("header_variant_pool") if isinstance(mix.get("header_variant_pool"), list) else []
        footer_pool = mix.get("footer_pool") if isinstance(mix.get("footer_pool"), list) else []
        chart_pool = mix.get("chart_treatment_pool") if isinstance(mix.get("chart_treatment_pool"), list) else []
        figure_pool = (
            mix.get("figure_table_treatment_pool")
            if isinstance(mix.get("figure_table_treatment_pool"), list)
            else []
        )
        record = {
            "preset": preset,
            "family": profile.get("family"),
            "background_system": profile.get("background_system"),
            "header_variant_count": len(set(header_pool)),
            "footer_count": len(set(footer_pool)),
            "chart_treatment_count": len(set(chart_pool)),
            "figure_table_treatment_count": len(set(figure_pool)),
        }
        records.append(record)
        if profile.get("profile_version") != "deck_preset_treatment_profiles_v1":
            failures.append({"step": "preset_treatment_profile", "reason": "wrong_version", "preset": preset})
        if profile.get("style_preset") != preset:
            failures.append(
                {
                    "step": "preset_treatment_profile",
                    "reason": "preset_mismatch",
                    "preset": preset,
                    "profile_preset": profile.get("style_preset"),
                }
            )
        if len(set(header_pool)) < 3 or not set(header_pool).issubset(supported_headers):
            failures.append(
                {
                    "step": "preset_treatment_profile",
                    "reason": "bad_header_pool",
                    "preset": preset,
                    "header_pool": header_pool,
                }
            )
        if "standard" not in footer_pool or len(set(footer_pool)) < 2:
            failures.append(
                {
                    "step": "preset_treatment_profile",
                    "reason": "bad_footer_pool",
                    "preset": preset,
                    "footer_pool": footer_pool,
                }
            )
        if len(set(chart_pool)) < 2 or len(set(figure_pool)) < 2:
            failures.append(
                {
                    "step": "preset_treatment_profile",
                    "reason": "thin_evidence_treatment_pool",
                    "preset": preset,
                    "chart_pool": chart_pool,
                    "figure_pool": figure_pool,
                }
            )
        if not str(profile.get("heading_accent_combo") or "").strip():
            failures.append({"step": "preset_treatment_profile", "reason": "missing_heading_combo", "preset": preset})
    return {
        "profile_version": "deck_preset_treatment_profiles_v1",
        "preset_count": len(presets),
        "records": records,
    }


def _style_mix_matrix() -> dict[str, Any]:
    return {
        "header_variant_pool": list(SUPPORTED_REPORT_HEADER_VARIANTS),
        "title_layout_pool": ["lab-plate", "light-atlas"],
        "footer_pool": ["source-line", "standard"],
        "chart_treatment_pool": ["minimal", "facts-right"],
        "summary_callout_mode_pool": ["lab-box", "default"],
        "figure_table_treatment_pool": ["image-sidebar", "table-first"],
        "mix_rule": "Rotate small report treatments from a stable seed while preserving lab/report readability.",
        "do_not_mix": [
            "Do not pair decorative card grids with dense evidence tables.",
            "Do not vary the core layout grid across similar evidence slides.",
        ],
    }


def _patch_design_brief(workspace: Path, *, seed: str) -> None:
    path = workspace / "design_brief.json"
    brief = _load_json(path)
    if not isinstance(brief, dict):
        brief = {}
    style_system = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    style_system["style_preset"] = "lab-report"
    style_system["style_seed"] = seed
    style_system["header_system"] = {
        "header_mode": "lab-clean",
        "header_variant": "auto",
    }
    style_system["footer_system"] = {
        "footer_mode": "source-line",
        "footer_page_numbers": True,
    }
    style_system["style_mix_matrix"] = _style_mix_matrix()
    brief["style_system"] = style_system
    renderer_treatments = brief.get("renderer_treatments") if isinstance(brief.get("renderer_treatments"), dict) else {}
    renderer_treatments["header_mode"] = "lab-clean"
    renderer_treatments["header_variant"] = "auto"
    renderer_treatments["footer_mode"] = "source-line"
    renderer_treatments["footer_page_numbers"] = True
    brief["renderer_treatments"] = renderer_treatments
    brief["format_promise"] = "A clean lab-report style mix with reproducible header and footer rhythm."
    _write_json(path, brief)


def _write_outline(workspace: Path) -> None:
    outline = {
        "title": "Style Mix Reproducibility Smoke",
        "slides": [
            {
                "slide_id": "s1",
                "type": "title",
                "title": "Style Mix Reproducibility Smoke",
                "subtitle": "Stable seed / restrained treatment pools",
            },
            {
                "slide_id": "s2",
                "type": "content",
                "variant": "standard",
                "title": "Header rhythm stays bounded",
                "subtitle": "Lab-clean content heading",
                "bullets": [
                    "The style seed resolves a stable header treatment pool.",
                    "Content density and footer reserve stay within report defaults.",
                    "Changing the seed should change treatment choices without changing the outline source.",
                ],
                "sources": ["Synthetic style mix smoke"],
            },
            {
                "slide_id": "s3",
                "type": "content",
                "variant": "lab-run-results",
                "title": "Evidence table remains readable",
                "subtitle": "Compact table / source-line footer",
                "headers": ["Metric", "Readout", "State"],
                "rows": [
                    ["Header variants", "3", "Bounded"],
                    ["Footer modes", "2", "Bounded"],
                    ["Repeat build", "Stable", "Pass"],
                ],
                "column_weights": [1.1, 0.9, 0.8],
                "interpretation": "The treatment mix changes small renderer defaults, not the evidence structure.",
                "sources": ["Synthetic style mix smoke"],
            },
            {
                "slide_id": "s4",
                "type": "content",
                "variant": "comparison-2col",
                "title": "Mixing stays structural, not random",
                "subtitle": "Same source / different seed",
                "left": {
                    "title": "Stable",
                    "body": ["The same seed produces byte-identical resolved outlines.", "Header pool membership stays explicit."],
                },
                "right": {
                    "title": "Variable",
                    "body": ["A different seed can select different footer/chart treatments.", "The available pool remains bounded."],
                },
                "verdict": "Use style_mix_matrix for restrained variation, not per-slide novelty.",
                "sources": ["Synthetic style mix smoke"],
            },
        ],
    }
    _write_json(workspace / "outline.json", outline)


def _write_content_plan(workspace: Path) -> None:
    plan = {
        "thesis": "A stable style seed should resolve restrained report treatments reproducibly.",
        "audience": "presentation-skill maintainers",
        "slide_plan": [
            {
                "slide_id": "s1",
                "role": "title",
                "message": "Open the style-mix smoke deck.",
                "variant": "title",
                "visual_strategy": "title opener",
                "evidence_needs": [],
            },
            {
                "slide_id": "s2",
                "role": "evidence",
                "message": "Show bounded header rhythm.",
                "variant": "standard",
                "visual_strategy": "lab-clean report header with compact body",
                "evidence_needs": [],
            },
            {
                "slide_id": "s3",
                "role": "evidence",
                "message": "Show table readability under the treatment mix.",
                "variant": "lab-run-results",
                "visual_strategy": "editable report table",
                "evidence_needs": [],
            },
            {
                "slide_id": "s4",
                "role": "synthesis",
                "message": "Compare stable versus variable treatment resolution.",
                "variant": "comparison-2col",
                "visual_strategy": "two-column comparison",
                "evidence_needs": [],
            },
        ],
    }
    _write_json(workspace / "content_plan.json", plan)


def _resolved_deck_style(workspace: Path) -> dict[str, Any]:
    payload = _load_json(workspace / "build" / "outline_resolved.json")
    if not isinstance(payload, dict):
        return {}
    style = payload.get("deck_style")
    return style if isinstance(style, dict) else {}


def _resolved_treatment_summary(workspace: Path) -> dict[str, Any]:
    payload = _load_json(workspace / "build" / "outline_resolved.json")
    if not isinstance(payload, dict):
        return {}
    summary = payload.get("resolved_treatment_summary")
    return summary if isinstance(summary, dict) else {}


def _run_checked(
    cmd: list[str],
    *,
    cwd: Path,
    command_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    result = _run(cmd, cwd=cwd)
    command_results.append(
        {
            "command": cmd,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-1200:],
        }
    )
    if result.returncode != 0:
        failures.append({"step": Path(cmd[1]).name, "returncode": result.returncode})


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a focused style-mix reproducibility smoke check.")
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
        else Path(tempfile.mkdtemp(prefix="presentation-skill-style-mix-"))
    )
    workspace.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    preset_profiles = _preset_profile_summary(repo, failures)

    try:
        _run_checked(
            [
                py,
                str(repo / "scripts" / "init_deck_workspace.py"),
                "--workspace",
                str(workspace),
                "--title",
                "Style Mix Reproducibility Smoke",
                "--style-preset",
                "lab-report",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        if failures:
            raise RuntimeError("workspace initialization failed")
        build_dir = workspace / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        _patch_design_brief(workspace, seed=STYLE_SEED_A)
        _write_outline(workspace)
        _write_content_plan(workspace)

        validate_cmd = [
            py,
            str(repo / "scripts" / "validate_planning.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(build_dir / "style_mix_planning.json"),
        ]
        build_cmd = [
            py,
            str(repo / "scripts" / "build_workspace.py"),
            "--workspace",
            str(workspace),
            "--qa",
            "--skip-render",
            "--fail-on-planning-warnings",
            "--overwrite",
            "--build-report",
            str(build_dir / "style_mix_build_a.json"),
        ]
        readiness_cmd = [
            py,
            str(repo / "scripts" / "report_workspace_readiness.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(build_dir / "style_mix_readiness_a.json"),
        ]
        advance_cmd = [
            py,
            str(repo / "scripts" / "advance_workspace.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(build_dir / "style_mix_advance.json"),
            "--next-action-markdown",
            str(build_dir / "style_mix_next_action.md"),
        ]
        for cmd in (validate_cmd, build_cmd, readiness_cmd):
            _run_checked(cmd, cwd=repo, command_results=command_results, failures=failures)

        planning = _load_json(build_dir / "style_mix_planning.json")
        readiness = _load_json(build_dir / "style_mix_readiness_a.json")
        readiness_markdown = (
            (workspace / "build" / "workspace_readiness.md").read_text(encoding="utf-8")
            if (workspace / "build" / "workspace_readiness.md").exists()
            else ""
        )
        resolved_a = _resolved_deck_style(workspace)
        treatment_a = _resolved_treatment_summary(workspace)
        resolved_a_text = (workspace / "build" / "outline_resolved.json").read_text(encoding="utf-8")
        _run_checked(advance_cmd, cwd=repo, command_results=command_results, failures=failures)
        next_action_markdown = (
            (build_dir / "style_mix_next_action.md").read_text(encoding="utf-8")
            if (build_dir / "style_mix_next_action.md").exists()
            else ""
        )

        _run_checked(build_cmd, cwd=repo, command_results=command_results, failures=failures)
        resolved_repeat = _resolved_deck_style(workspace)
        treatment_repeat = _resolved_treatment_summary(workspace)
        resolved_repeat_text = (workspace / "build" / "outline_resolved.json").read_text(encoding="utf-8")

        _patch_design_brief(workspace, seed=STYLE_SEED_B)
        _run_checked(
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--qa",
                "--skip-render",
                "--fail-on-planning-warnings",
                "--overwrite",
                "--build-report",
                str(build_dir / "style_mix_build_b.json"),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        resolved_b = _resolved_deck_style(workspace)
        treatment_b = _resolved_treatment_summary(workspace)

        gallery_dir = build_dir / "header_variant_gallery"
        gallery_cmd = [
            py,
            str(repo / "scripts" / "build_header_variant_gallery.py"),
            "--outdir",
            str(gallery_dir),
            "--presets",
            "lab-report",
            "--variants",
            *SUPPORTED_REPORT_HEADER_VARIANTS,
            "--qa",
        ]
        _run_checked(gallery_cmd, cwd=repo, command_results=command_results, failures=failures)
        gallery_summary = _load_json(gallery_dir / "summary.json")

        header_pool = _style_mix_matrix()["header_variant_pool"]
        expected_multi_pool_count = len(
            [
                value
                for key, value in _style_mix_matrix().items()
                if key.endswith("_pool") and isinstance(value, list) and len(set(value)) >= 2
            ]
        )
        style = readiness.get("style") if isinstance(readiness.get("style"), dict) else {}
        readiness_treatment = (
            style.get("resolved_treatment_summary")
            if isinstance(style.get("resolved_treatment_summary"), dict)
            else {}
        )
        mix_summary = style.get("style_mix_matrix") if isinstance(style.get("style_mix_matrix"), dict) else {}
        pools = mix_summary.get("pools") if isinstance(mix_summary.get("pools"), dict) else {}

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
        if resolved_a_text != resolved_repeat_text or resolved_a != resolved_repeat or treatment_a != treatment_repeat:
            failures.append({"step": "repeat_build", "reason": "resolved_outline_changed_for_same_seed"})
        if resolved_a.get("header_variant") != "auto":
            failures.append({"step": "resolved_style", "reason": "header_variant_not_auto", "value": resolved_a.get("header_variant")})
        if resolved_a.get("header_variants") != header_pool:
            failures.append(
                {
                    "step": "resolved_style",
                    "reason": "header_pool_not_preserved",
                    "expected": header_pool,
                    "actual": resolved_a.get("header_variants"),
                }
            )
        if resolved_a.get("footer_mode") not in _style_mix_matrix()["footer_pool"]:
            failures.append({"step": "resolved_style", "reason": "footer_mode_outside_pool", "value": resolved_a.get("footer_mode")})
        if resolved_b.get("style_seed") != STYLE_SEED_B:
            failures.append({"step": "seed_change", "reason": "style_seed_not_updated", "style_seed": resolved_b.get("style_seed")})
        if resolved_b == resolved_a:
            failures.append({"step": "seed_change", "reason": "resolved_style_did_not_change"})
        header_by_slide = (
            treatment_a.get("header_variant_by_slide")
            if isinstance(treatment_a.get("header_variant_by_slide"), list)
            else []
        )
        header_variants = [
            str(item.get("header_variant") or "").strip()
            for item in header_by_slide
            if isinstance(item, dict) and str(item.get("header_variant") or "").strip()
        ]
        if len(header_by_slide) != 3:
            failures.append(
                {
                    "step": "resolved_treatments",
                    "reason": "content_header_treatment_count_mismatch",
                    "expected": 3,
                    "actual": len(header_by_slide),
                    "header_by_slide": header_by_slide,
                }
            )
        if not set(header_variants).issubset(set(header_pool)):
            failures.append(
                {
                    "step": "resolved_treatments",
                    "reason": "header_variant_outside_pool",
                    "expected_pool": header_pool,
                    "actual": header_variants,
                }
            )
        if int(treatment_a.get("unique_header_variant_count") or 0) < 2:
            failures.append(
                {
                    "step": "resolved_treatments",
                    "reason": "auto_header_variants_not_mixed",
                    "treatment_summary": treatment_a,
                }
            )
        if readiness_treatment != treatment_a:
            failures.append(
                {
                    "step": "workspace_readiness",
                    "reason": "resolved_treatment_summary_not_summarized",
                    "expected": treatment_a,
                    "actual": readiness_treatment,
                }
            )
        for label, text in (
            ("workspace_readiness_markdown", readiness_markdown),
            ("workspace_next_action_markdown", next_action_markdown),
        ):
            if "Resolved header variants: unique=`" not in text:
                failures.append(
                    {
                        "step": label,
                        "reason": "resolved_header_variants_missing_from_markdown",
                    }
                )
        if treatment_b == treatment_a:
            failures.append(
                {
                    "step": "seed_change",
                    "reason": "resolved_treatment_summary_did_not_change",
                }
            )
        if mix_summary.get("multi_entry_pool_count") != expected_multi_pool_count:
            failures.append(
                {
                    "step": "readiness_style_mix",
                    "reason": "multi_pool_count_mismatch",
                    "expected": expected_multi_pool_count,
                    "actual": mix_summary.get("multi_entry_pool_count"),
                }
            )
        header_summary = pools.get("header_variant_pool") if isinstance(pools.get("header_variant_pool"), dict) else {}
        if header_summary.get("values") != header_pool:
            failures.append(
                {
                    "step": "readiness_style_mix",
                    "reason": "header_pool_summary_mismatch",
                    "expected": header_pool,
                    "actual": header_summary.get("values"),
                }
            )
        if gallery_summary.get("variants") != header_pool:
            failures.append(
                {
                    "step": "header_variant_gallery",
                    "reason": "gallery_variants_mismatch",
                    "expected": header_pool,
                    "actual": gallery_summary.get("variants"),
                }
            )
        gallery_records = gallery_summary.get("records") if isinstance(gallery_summary.get("records"), list) else []
        gallery_lab_record = next(
            (
                record
                for record in gallery_records
                if isinstance(record, dict) and record.get("preset") == "lab-report"
            ),
            {},
        )
        gallery_qa_report_value = str(gallery_lab_record.get("qa_report") or "").strip()
        gallery_qa_report = Path(gallery_qa_report_value) if gallery_qa_report_value else None
        if gallery_qa_report is None or not gallery_qa_report.exists():
            failures.append(
                {
                    "step": "header_variant_gallery",
                    "reason": "qa_report_missing",
                    "qa_report": gallery_qa_report_value,
                }
            )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "resolved_style_seed_a": resolved_a,
            "resolved_style_seed_b": resolved_b,
            "resolved_treatment_seed_a": treatment_a,
            "resolved_treatment_seed_b": treatment_b,
            "style_mix_summary": mix_summary,
            "preset_treatment_profiles": preset_profiles,
            "header_variant_gallery": gallery_summary,
            "planning_counts": {
                "errors": planning.get("error_count"),
                "warnings": planning.get("warning_count"),
            },
            "readiness_status": readiness.get("status"),
            "failures": failures,
            "commands": command_results,
        }
        summary_path = build_dir / "style_mix_repro_smoke.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "resolved_style_seed_a",
                        "resolved_style_seed_b",
                        "planning_counts",
                        "readiness_status",
                        "preset_treatment_profiles",
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
            (workspace / "build").mkdir(parents=True, exist_ok=True)
            (workspace / "build" / "style_mix_repro_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
