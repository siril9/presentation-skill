#!/usr/bin/env python3
"""End-to-end rendered smoke for a structured lab/data artifact triplet delivery workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageStat
except Exception:  # pragma: no cover - dependency guard
    Image = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]

from pptx import Presentation

from run_design_contract_apply_smoke import USER_PROMPT, _answers_for, _contract_fixture


DATA_REL = "data/assay_readouts.csv"
EXPECTED_TRIPLET_VARIANTS = ["image-sidebar", "chart", "lab-run-results"]
EXPECTED_SIDEBAR_BODY_FONT_SIZE = 16
ZERO_QA_COUNT_KEYS = [
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
    started = time.perf_counter()
    result = _run(cmd, cwd=cwd)
    duration_ms = int(round((time.perf_counter() - started) * 1000))
    command_results.append(
        {
            "command": cmd,
            "returncode": result.returncode,
            "duration_ms": duration_ms,
            "stdout_tail": result.stdout[-1800:],
        }
    )
    if result.returncode not in allowed:
        failures.append(
            {
                "step": Path(cmd[1]).name if len(cmd) > 1 else Path(cmd[0]).name,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1800:],
            }
        )
    return result


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_fixture_csv(workspace: Path) -> Path:
    path = workspace / DATA_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "sample,ct,rfu,state",
                "positive_control,21.4,42.1,pass",
                "limit_check,34.2,12.0,review",
                "assay_a,24.8,36.4,pass",
                "assay_b,28.1,27.8,pass",
                "low_signal,31.7,11.2,review",
                "ntc,0.0,0.2,pass",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _qa_counts(payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in ZERO_QA_COUNT_KEYS:
        value = payload.get(key, 0)
        counts[key] = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
    placeholder_hits = payload.get("placeholder_hits")
    counts["placeholder_hit_count"] = len(placeholder_hits) if isinstance(placeholder_hits, list) else 0
    return counts


def _report_counts(build_report: dict[str, Any], report_name: str) -> dict[str, int]:
    reports = build_report.get("reports") if isinstance(build_report.get("reports"), dict) else {}
    report = reports.get(report_name) if isinstance(reports.get(report_name), dict) else {}
    counts = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    return {
        key: int(value)
        for key, value in counts.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _positive_counts(counts: dict[str, Any]) -> dict[str, Any]:
    positives: dict[str, Any] = {}
    for key, value in counts.items():
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number:
            positives[key] = number
    return positives


def _rendered_paths(render_dir: Path) -> list[Path]:
    paths = (
        list(render_dir.glob("slide-*.jpg"))
        + list(render_dir.glob("slide-*.jpeg"))
        + list(render_dir.glob("slide-*.png"))
    )

    def key(path: Path) -> tuple[int, str]:
        suffix = path.stem.replace("slide-", "")
        try:
            return int(suffix), path.name
        except ValueError:
            return 10**9, path.name

    return sorted(paths, key=key)


def _image_quality(path: Path, *, min_width: int = 640, min_height: int = 360) -> dict[str, Any]:
    if Image is None or ImageStat is None:
        return {
            "path": str(path),
            "exists": path.exists(),
            "valid": False,
            "reason": "pillow_unavailable",
        }
    if not path.exists():
        return {"path": str(path), "exists": False, "valid": False, "reason": "missing"}
    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            stat = ImageStat.Stat(rgb)
            extrema = rgb.getextrema()
            channel_ranges = [high - low for low, high in extrema]
            width, height = rgb.size
    except OSError as exc:
        return {
            "path": str(path),
            "exists": path.exists(),
            "valid": False,
            "reason": f"image_open_failed: {exc}",
        }
    max_channel_range = max(channel_ranges) if channel_ranges else 0
    valid = width >= min_width and height >= min_height and max_channel_range >= 10
    return {
        "path": str(path),
        "exists": True,
        "valid": valid,
        "width": width,
        "height": height,
        "mean_rgb": [round(value, 2) for value in stat.mean],
        "channel_ranges": channel_ranges,
        "max_channel_range": max_channel_range,
        "min_width": min_width,
        "min_height": min_height,
        "reason": "" if valid else "too_small_or_blank",
    }


def _artifact_aliases(output: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for artifact in output.get("artifacts", []):
        if isinstance(artifact, dict) and isinstance(artifact.get("alias"), str):
            aliases.add(artifact["alias"])
    return aliases


def _selection_bindings(selection: dict[str, Any]) -> list[dict[str, str]]:
    bindings = selection.get("bindings") if isinstance(selection.get("bindings"), list) else []
    normalized: list[dict[str, str]] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        normalized.append(
            {
                "output_id": str(binding.get("output_id") or ""),
                "variant": str(binding.get("variant") or ""),
                "slide_id": str(binding.get("slide_id") or ""),
            }
        )
    return normalized


def _command_duration(command_results: list[dict[str, Any]], needle: str) -> int:
    for result in command_results:
        command = " ".join(str(part) for part in result.get("command", []))
        if needle in command:
            return int(result.get("duration_ms") or 0)
    return 0


def _command_durations(command_results: list[dict[str, Any]], needle: str) -> list[int]:
    durations: list[int] = []
    for result in command_results:
        command = " ".join(str(part) for part in result.get("command", []))
        if needle in command:
            durations.append(int(result.get("duration_ms") or 0))
    return durations


def _source_hashes(build_report: dict[str, Any]) -> dict[str, str]:
    source_files = (
        build_report.get("source_files")
        if isinstance(build_report.get("source_files"), dict)
        else {}
    )
    hashes: dict[str, str] = {}
    for key, value in source_files.items():
        if not isinstance(value, dict) or not value.get("exists"):
            continue
        sha = str(value.get("sha256") or "").strip()
        if sha:
            hashes[str(key)] = sha
    return hashes


def _output_pptx_snapshot(build_report: dict[str, Any]) -> dict[str, Any]:
    outputs = build_report.get("outputs") if isinstance(build_report.get("outputs"), dict) else {}
    pptx = outputs.get("pptx") if isinstance(outputs.get("pptx"), dict) else {}
    return pptx


def _output_pptx_hash(build_report: dict[str, Any]) -> str:
    pptx = _output_pptx_snapshot(build_report)
    return str(pptx.get("sha256") or "").strip()


def _output_pptx_normalized_hash(build_report: dict[str, Any]) -> str:
    pptx = _output_pptx_snapshot(build_report)
    return str(pptx.get("normalized_sha256") or "").strip()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _check_required_tools(failures: list[dict[str, Any]]) -> None:
    for name in ("node", "soffice", "pdftoppm"):
        if not shutil.which(name):
            failures.append({"step": "tooling", "reason": "missing_binary", "binary": name})
    if Image is None or ImageStat is None:
        failures.append({"step": "tooling", "reason": "missing_python_dependency", "dependency": "Pillow"})


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an end-to-end structured lab/data deck through rendered final delivery."
    )
    parser.add_argument("--workspace", default="", help="Workspace/output directory. Defaults to a temporary directory.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep artifacts after a passing run.")
    parser.add_argument(
        "--max-exterior-fraction",
        type=float,
        default=0.45,
        help="Maximum allowed generated figure exterior whitespace fraction.",
    )
    parser.add_argument(
        "--max-total-seconds",
        type=float,
        default=180.0,
        help="Maximum total smoke duration. Use <=0 to disable.",
    )
    parser.add_argument(
        "--max-final-build-seconds",
        type=float,
        default=90.0,
        help="Maximum strict rendered final build duration. Use <=0 to disable.",
    )
    parser.add_argument(
        "--max-repeat-build-seconds",
        type=float,
        default=90.0,
        help="Maximum repeated strict rendered build duration. Use <=0 to disable.",
    )
    parser.add_argument(
        "--min-content-density-score",
        type=float,
        default=0.55,
        help="Minimum layout density score for generated content slides. Use <=0 to disable.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-rendered-data-delivery-"))
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
    build_dir = workspace / "build"
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    passed = False
    started = time.perf_counter()
    _check_required_tools(failures)

    try:
        data_path = _write_fixture_csv(workspace)
        packet_path = workspace / "deck_start_packet.json"
        answers_path = workspace / "intake_answers.json"
        design_prompt_path = build_dir / "design_contract_prompt.md"
        contract_path = workspace / "design_contract.json"
        design_apply_report_path = workspace / "design_contract_apply_report.json"

        _run_checked(
            [
                py,
                str(repo / "scripts" / "init_deck_workspace.py"),
                "--workspace",
                str(workspace),
                "--title",
                "Rendered Data Delivery Smoke",
                "--style-preset",
                "lab-report",
                "--overwrite",
                "--user-prompt",
                USER_PROMPT,
                "--start-packet",
                str(packet_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        if failures:
            raise RuntimeError("workspace initialization failed")

        packet = _load_json(packet_path)
        if not isinstance(packet, dict):
            failures.append({"step": "deck_start_packet", "reason": "packet_not_object"})
            packet = {}
        inventory = packet.get("workspace_source_inventory") if isinstance(packet.get("workspace_source_inventory"), dict) else {}
        data_files = inventory.get("data_files") if isinstance(inventory.get("data_files"), list) else []
        if inventory.get("data_file_count", 0) < 1 or not any(
            isinstance(item, dict) and item.get("path") == DATA_REL and item.get("sha256")
            for item in data_files
        ):
            failures.append(
                {
                    "step": "deck_start_packet",
                    "reason": "source_inventory_missing_hashed_fixture",
                    "workspace_source_inventory": inventory,
                }
            )
        route_ledger = packet.get("route_decision_ledger") if isinstance(packet.get("route_decision_ledger"), dict) else {}
        active_routes = [
            str(item.get("id") or "")
            for item in route_ledger.get("routes", [])
            if isinstance(item, dict) and item.get("active")
        ] if isinstance(route_ledger.get("routes"), list) else []
        if "data_artifacts" not in active_routes:
            failures.append({"step": "deck_start_packet", "reason": "data_artifacts_route_not_active", "routes": active_routes})

        answers = _answers_for(packet)
        _write_json(answers_path, answers)
        _run_checked(
            [
                py,
                str(repo / "scripts" / "apply_deck_intake_answers.py"),
                "--workspace",
                str(workspace),
                "--packet",
                str(packet_path),
                "--answers",
                str(answers_path),
                "--answered-by",
                "best_judgment",
                "--report",
                str(workspace / "intake_apply_report.json"),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        intake_report = _load_json(workspace / "intake_apply_report.json")
        if not isinstance(intake_report, dict) or intake_report.get("workflow") != "deck_intake_answers_apply_v1":
            failures.append({"step": "apply_deck_intake_answers", "reason": "bad_apply_report", "report": intake_report})

        _run_checked(
            [
                py,
                str(repo / "scripts" / "emit_design_contract_prompt.py"),
                "--workspace",
                str(workspace),
                "--user-prompt",
                USER_PROMPT,
                "--output",
                str(design_prompt_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        prompt_text = design_prompt_path.read_text(encoding="utf-8") if design_prompt_path.exists() else ""
        for snippet in ("deck_reproducibility_contract_v1", "slide_quality_contract_v1", "deck_preset_treatment_profiles_v1"):
            if snippet not in prompt_text:
                failures.append({"step": "emit_design_contract_prompt", "reason": "missing_prompt_context", "snippet": snippet})

        seed = str(packet.get("recommended_style_seed") or "").strip()
        packet_quality = packet.get("slide_quality_contract") if isinstance(packet.get("slide_quality_contract"), dict) else {}
        _write_json(contract_path, _contract_fixture(seed=seed, slide_quality_contract=packet_quality))
        _run_checked(
            [
                py,
                str(repo / "scripts" / "apply_design_contract.py"),
                "--workspace",
                str(workspace),
                "--contract",
                str(contract_path),
                "--report",
                str(design_apply_report_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        design_apply = _load_json(design_apply_report_path)
        for flag in (
            "choice_resolution_enriched_from_seed",
            "reproducibility_contract_applied",
            "slide_quality_contract_applied",
        ):
            if not isinstance(design_apply, dict) or design_apply.get(flag) is not True:
                failures.append({"step": "apply_design_contract", "reason": f"{flag}_not_true", "report": design_apply})

        _run_checked(
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--fast-first-pass",
                "--artifact-bind-mode",
                "all",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        final_build_cmd = [
            py,
            str(repo / "scripts" / "build_workspace.py"),
            "--workspace",
            str(workspace),
            "--qa",
            "--visual-review",
            "--fail-on-planning-warnings",
            "--fail-on-whitespace-warnings",
            "--fail-on-visual-review-warnings",
            "--overwrite",
        ]
        _run_checked(
            final_build_cmd,
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        first_build_report = _load_json(workspace / "build" / "build_workspace_report.json")
        first_qa = _load_json(workspace / "build" / "qa" / "report.json")
        first_visual_review = _load_json(workspace / "build" / "qa" / "visual_review" / "visual_review.json")
        first_pptx_hash = _output_pptx_hash(first_build_report if isinstance(first_build_report, dict) else {})
        first_pptx_normalized_hash = _output_pptx_normalized_hash(
            first_build_report if isinstance(first_build_report, dict) else {}
        )
        _run_checked(
            final_build_cmd,
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        _run_checked(
            [py, str(repo / "scripts" / "report_workspace_readiness.py"), "--workspace", str(workspace)],
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
                "--require-visual-review",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        _run_checked(
            [
                py,
                str(repo / "scripts" / "advance_delivery.py"),
                "--workspace",
                str(workspace),
                "--require-visual-review",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )

        required_paths = [
            "deck_start_packet.json",
            "intake_answers.json",
            "intake_apply_report.json",
            "design_contract.json",
            "design_contract_apply_report.json",
            "assets/make_figures.py",
            "assets/artifacts_manifest.json",
            "assets/analysis_summary.json",
            "assets/analysis_summary.md",
            "artifact_selections.auto.json",
            "outline.json",
            "build/data_artifact_scaffold.json",
            "build/artifact_manifest_apply.json",
            "build/planning_validation.json",
            "build/preflight.json",
            "build/qa/report.json",
            "build/qa/visual_review/visual_review.json",
            "build/qa/visual_review/contact_sheet.jpg",
            "build/workspace_readiness.json",
            "build/build_workspace_report.json",
            "build/delivery_readiness.json",
            "build/delivery_advance_report.json",
            "build/delivery_next_action.md",
        ]
        for rel in required_paths:
            if not (workspace / rel).exists():
                failures.append({"step": "required_path", "reason": "missing", "path": rel})

        manifest = _load_json(workspace / "assets" / "artifacts_manifest.json")
        analysis_summary = _load_json(workspace / "assets" / "analysis_summary.json")
        selection = _load_json(workspace / "artifact_selections.auto.json")
        outline = _load_json(workspace / "outline.json")
        artifact_apply = _load_json(workspace / "build" / "artifact_manifest_apply.json")
        planning = _load_json(workspace / "build" / "planning_validation.json")
        preflight = _load_json(workspace / "build" / "preflight.json")
        qa = _load_json(workspace / "build" / "qa" / "report.json")
        visual_review = _load_json(workspace / "build" / "qa" / "visual_review" / "visual_review.json")
        readiness = _load_json(workspace / "build" / "workspace_readiness.json")
        build_report = _load_json(workspace / "build" / "build_workspace_report.json")
        delivery = _load_json(workspace / "build" / "delivery_readiness.json")
        delivery_markdown = (
            workspace / "build" / "delivery_readiness.md"
        ).read_text(encoding="utf-8") if (workspace / "build" / "delivery_readiness.md").exists() else ""
        delivery_advance = _load_json(workspace / "build" / "delivery_advance_report.json")

        first_build_report = first_build_report if isinstance(first_build_report, dict) else {}
        first_qa = first_qa if isinstance(first_qa, dict) else {}
        first_visual_review = first_visual_review if isinstance(first_visual_review, dict) else {}
        repeatability = {
            "source_hashes_stable": _source_hashes(first_build_report) == _source_hashes(build_report),
            "artifact_context_stable": _stable_json(first_build_report.get("artifact_context", {})) == _stable_json(build_report.get("artifact_context", {})),
            "quality_context_stable": _stable_json(first_build_report.get("quality_context", {})) == _stable_json(build_report.get("quality_context", {})),
            "options_stable": _stable_json(first_build_report.get("options", {})) == _stable_json(build_report.get("options", {})),
            "qa_counts_stable": _qa_counts(first_qa) == _qa_counts(qa if isinstance(qa, dict) else {}),
            "visual_review_warning_count_stable": first_visual_review.get("warning_count") == visual_review.get("warning_count"),
            "rendered_slide_count_stable": first_visual_review.get("rendered_slide_count") == visual_review.get("rendered_slide_count"),
            "pptx_normalized_sha256_stable": bool(
                first_pptx_normalized_hash
                and first_pptx_normalized_hash == _output_pptx_normalized_hash(build_report)
            ),
            "pptx_sha256_stable": bool(first_pptx_hash and first_pptx_hash == _output_pptx_hash(build_report)),
            "first_pptx_normalized_sha256": first_pptx_normalized_hash,
            "repeat_pptx_normalized_sha256": _output_pptx_normalized_hash(build_report),
            "first_pptx_sha256": first_pptx_hash,
            "repeat_pptx_sha256": _output_pptx_hash(build_report),
        }
        for key in (
            "source_hashes_stable",
            "artifact_context_stable",
            "quality_context_stable",
            "options_stable",
            "qa_counts_stable",
            "visual_review_warning_count_stable",
            "rendered_slide_count_stable",
            "pptx_normalized_sha256_stable",
        ):
            if repeatability.get(key) is not True:
                failures.append(
                    {
                        "step": "repeat_build",
                        "reason": f"{key}_failed",
                        "repeatability": repeatability,
                    }
                )

        outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), list) else []
        if manifest.get("manifest_version") != "presentation_skill_artifact_manifest_v1" or not outputs:
            failures.append({"step": "artifact_manifest", "reason": "missing_outputs_or_bad_version", "manifest": manifest})
        output = outputs[0] if outputs and isinstance(outputs[0], dict) else {}
        aliases = _artifact_aliases(output)
        for prefix in ("image:", "chart:", "table:"):
            if not any(alias.startswith(prefix) for alias in aliases):
                failures.append({"step": "artifact_manifest", "reason": "missing_alias_prefix", "prefix": prefix, "aliases": sorted(aliases)})
        metadata = output.get("analysis_metadata") if isinstance(output.get("analysis_metadata"), dict) else {}
        whitespace = metadata.get("image_whitespace") if isinstance(metadata.get("image_whitespace"), dict) else {}
        exterior_fraction = whitespace.get("exterior_fraction")
        if metadata.get("source_path") != DATA_REL:
            failures.append({"step": "artifact_manifest", "reason": "source_path_not_recorded", "metadata": metadata})
        if whitespace.get("checked") is not True or not isinstance(exterior_fraction, (int, float)) or isinstance(exterior_fraction, bool):
            failures.append({"step": "artifact_manifest", "reason": "whitespace_not_measured", "image_whitespace": whitespace})
        elif float(exterior_fraction) > float(args.max_exterior_fraction):
            failures.append(
                {
                    "step": "artifact_manifest",
                    "reason": "exterior_fraction_high",
                    "max_exterior_fraction": args.max_exterior_fraction,
                    "actual": exterior_fraction,
                }
            )
        if DATA_REL not in (analysis_summary.get("source_paths") or []):
            failures.append({"step": "analysis_summary", "reason": "source_path_missing", "source_paths": analysis_summary.get("source_paths")})
        bindings = selection.get("bindings") if isinstance(selection.get("bindings"), list) else []
        normalized_bindings = _selection_bindings(selection if isinstance(selection, dict) else {})
        binding_variants = [binding["variant"] for binding in normalized_bindings]
        selected_slide_ids = [binding["slide_id"] for binding in normalized_bindings]
        figure_binding = next(
            (
                binding
                for binding in bindings
                if isinstance(binding, dict)
                and str(binding.get("variant") or "") == "image-sidebar"
            ),
            {},
        )
        figure_sidebar_body_font_size = figure_binding.get("sidebar_body_font_size")
        slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
        figure_slide_id = str(figure_binding.get("slide_id") or "")
        figure_slide = next(
            (
                slide
                for slide in slides
                if isinstance(slide, dict)
                and str(slide.get("slide_id") or "") == figure_slide_id
            ),
            {},
        )
        outline_sidebar_body_font_size = figure_slide.get("sidebar_body_font_size")
        if not bindings:
            failures.append({"step": "artifact_selection", "reason": "missing_bindings", "selection": selection})
        if binding_variants != EXPECTED_TRIPLET_VARIANTS:
            failures.append(
                {
                    "step": "artifact_selection",
                    "reason": "triplet_variants_not_bound",
                    "expected": EXPECTED_TRIPLET_VARIANTS,
                    "actual": binding_variants,
                    "bindings": normalized_bindings,
                }
            )
        if figure_sidebar_body_font_size != EXPECTED_SIDEBAR_BODY_FONT_SIZE:
            failures.append(
                {
                    "step": "artifact_selection",
                    "reason": "sidebar_body_font_size_not_preserved",
                    "expected": EXPECTED_SIDEBAR_BODY_FONT_SIZE,
                    "actual": figure_sidebar_body_font_size,
                    "binding": figure_binding,
                }
            )
        if outline_sidebar_body_font_size != EXPECTED_SIDEBAR_BODY_FONT_SIZE:
            failures.append(
                {
                    "step": "outline",
                    "reason": "sidebar_body_font_size_not_applied",
                    "expected": EXPECTED_SIDEBAR_BODY_FONT_SIZE,
                    "actual": outline_sidebar_body_font_size,
                    "slide_id": figure_slide_id,
                    "slide": figure_slide,
                }
            )
        if (
            not isinstance(artifact_apply, dict)
            or artifact_apply.get("applied") is not True
            or artifact_apply.get("selection_count") != len(EXPECTED_TRIPLET_VARIANTS)
            or artifact_apply.get("auto_select_mode") != "all"
        ):
            failures.append(
                {
                    "step": "artifact_apply",
                    "reason": "triplet_apply_not_recorded",
                    "expected_selection_count": len(EXPECTED_TRIPLET_VARIANTS),
                    "report": artifact_apply,
                }
            )

        if planning.get("error_count") != 0 or planning.get("warning_count") != 0:
            failures.append({"step": "planning", "reason": "nonzero_counts", "planning": planning})
        if preflight.get("error_count") != 0 or preflight.get("warning_count") != 0:
            failures.append({"step": "preflight", "reason": "nonzero_counts", "preflight": preflight})
        qa_counts = _qa_counts(qa if isinstance(qa, dict) else {})
        qa_positive = _positive_counts(qa_counts)
        if qa_positive:
            failures.append({"step": "qa", "reason": "nonzero_counts", "counts": qa_positive})
        expected_slide_count = 0
        pptx_path = workspace / "build" / str((workspace / "build").name)
        outputs_payload = build_report.get("outputs") if isinstance(build_report.get("outputs"), dict) else {}
        pptx_payload = outputs_payload.get("pptx") if isinstance(outputs_payload.get("pptx"), dict) else {}
        pptx_rel = str(pptx_payload.get("path") or "")
        if pptx_rel:
            pptx_path = workspace / pptx_rel
        if pptx_path.exists():
            expected_slide_count = len(Presentation(str(pptx_path)).slides)
        if qa.get("render_rc") != 0 or qa.get("rendered_slide_count") != expected_slide_count or expected_slide_count <= 0:
            failures.append(
                {
                    "step": "qa_render",
                    "reason": "render_count_mismatch",
                    "render_rc": qa.get("render_rc"),
                    "rendered_slide_count": qa.get("rendered_slide_count"),
                    "expected_slide_count": expected_slide_count,
                }
            )
        if visual_review.get("warning_count") != 0 or visual_review.get("rendered_slide_count") != expected_slide_count:
            failures.append(
                {
                    "step": "visual_review",
                    "reason": "warnings_or_render_count_bad",
                    "warning_count": visual_review.get("warning_count"),
                    "rendered_slide_count": visual_review.get("rendered_slide_count"),
                    "expected_slide_count": expected_slide_count,
                }
            )

        render_dir = workspace / "build" / "qa" / "renders"
        render_qualities = [_image_quality(path) for path in _rendered_paths(render_dir)]
        invalid_renders = [item for item in render_qualities if not item.get("valid")]
        if len(render_qualities) != expected_slide_count or invalid_renders:
            failures.append(
                {
                    "step": "rendered_images",
                    "reason": "missing_or_blank_render",
                    "expected_slide_count": expected_slide_count,
                    "qualities": render_qualities,
                }
            )
        contact_sheet = Path(str(visual_review.get("contact_sheet") or ""))
        contact_quality = _image_quality(contact_sheet, min_height=240) if str(contact_sheet) else {"valid": False, "reason": "missing"}
        if not contact_quality.get("valid"):
            failures.append({"step": "visual_review", "reason": "contact_sheet_invalid_or_blank", "quality": contact_quality})

        density_score_by_slide = (
            qa.get("density_score_by_slide")
            if isinstance(qa.get("density_score_by_slide"), list)
            else []
        )
        content_density_scores = [
            item
            for item in density_score_by_slide
            if isinstance(item, dict)
            and isinstance(item.get("slide_index"), (int, float))
            and not isinstance(item.get("slide_index"), bool)
            and int(item.get("slide_index")) > 0
        ]
        low_density_scores: list[dict[str, Any]] = []
        if args.min_content_density_score > 0:
            for item in content_density_scores:
                score = item.get("density_score")
                if not isinstance(score, (int, float)) or isinstance(score, bool):
                    low_density_scores.append(
                        {
                            "slide_index": item.get("slide_index"),
                            "reason": "missing_density_score",
                            "actual": score,
                        }
                    )
                elif float(score) < float(args.min_content_density_score):
                    low_density_scores.append(
                        {
                            "slide_index": item.get("slide_index"),
                            "reason": "density_score_below_floor",
                            "actual": score,
                            "minimum": args.min_content_density_score,
                        }
                    )
            if len(content_density_scores) != max(0, expected_slide_count - 1) or low_density_scores:
                failures.append(
                    {
                        "step": "layout_density",
                        "reason": "generated_content_slides_underfilled",
                        "minimum": args.min_content_density_score,
                        "expected_content_slide_count": max(0, expected_slide_count - 1),
                        "actual_content_slide_count": len(content_density_scores),
                        "density_score_by_slide": density_score_by_slide,
                        "low_density_scores": low_density_scores,
                    }
                )

        run = build_report.get("run") if isinstance(build_report.get("run"), dict) else {}
        options = build_report.get("options") if isinstance(build_report.get("options"), dict) else {}
        if run.get("status") != "succeeded":
            failures.append({"step": "build_report", "reason": "build_not_succeeded", "run": run})
        expected_options = {
            "qa": True,
            "skip_render": False,
            "visual_review": True,
            "fail_on_visual_review_warnings": True,
            "fast_first_pass": False,
            "fail_on_whitespace_warnings": True,
            "fail_on_planning_warnings": True,
            "overwrite": True,
        }
        for key, expected in expected_options.items():
            if options.get(key) is not expected:
                failures.append({"step": "build_report", "reason": "option_mismatch", "key": key, "expected": expected, "actual": options.get(key)})
        for label in ("planning", "preflight", "qa"):
            positives = _positive_counts(_report_counts(build_report, label))
            if positives:
                failures.append({"step": "build_report", "reason": f"{label}_nonzero_counts", "counts": positives})
        quality_context = build_report.get("quality_context") if isinstance(build_report.get("quality_context"), dict) else {}
        slide_quality = quality_context.get("slide_quality_contract") if isinstance(quality_context.get("slide_quality_contract"), dict) else {}
        if slide_quality.get("contract_version") != "slide_quality_contract_v1" or slide_quality.get("fail_on_awkward_whitespace") is not True:
            failures.append({"step": "build_report", "reason": "quality_context_missing", "quality_context": quality_context})
        artifact_context = build_report.get("artifact_context") if isinstance(build_report.get("artifact_context"), dict) else {}
        artifact_manifest = artifact_context.get("artifact_manifest") if isinstance(artifact_context.get("artifact_manifest"), dict) else {}
        artifact_selection = artifact_context.get("artifact_selection") if isinstance(artifact_context.get("artifact_selection"), dict) else {}
        artifact_aliases = artifact_manifest.get("aliases") if isinstance(artifact_manifest.get("aliases"), list) else []
        artifact_sources = [
            str(alias.get("source_path") or "")
            for alias in artifact_aliases
            if isinstance(alias, dict)
        ]
        if artifact_manifest.get("output_count", 0) < 1 or DATA_REL not in artifact_sources:
            failures.append({"step": "build_report", "reason": "artifact_context_missing", "artifact_context": artifact_context})
        if (
            artifact_selection.get("binding_count") != len(EXPECTED_TRIPLET_VARIANTS)
            or artifact_selection.get("variants") != EXPECTED_TRIPLET_VARIANTS
            or artifact_selection.get("slide_ids") != selected_slide_ids
        ):
            failures.append(
                {
                    "step": "build_report",
                    "reason": "triplet_artifact_selection_context_missing",
                    "expected_variants": EXPECTED_TRIPLET_VARIANTS,
                    "expected_slide_ids": selected_slide_ids,
                    "artifact_selection": artifact_selection,
                }
            )

        if readiness.get("status") != "ready":
            failures.append({"step": "workspace_readiness", "reason": "not_ready", "status": readiness.get("status")})
        if delivery.get("delivery_status") != "ready" or delivery.get("blocking_reasons") != [] or delivery.get("warning_reasons") != []:
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "not_ready",
                    "status": delivery.get("delivery_status"),
                    "blocking": delivery.get("blocking_reasons"),
                    "warnings": delivery.get("warning_reasons"),
                }
            )
        gates = delivery.get("gates") if isinstance(delivery.get("gates"), dict) else {}
        expected_true_gates = [
            "source_readiness_ready",
            "source_freshness_current",
            "build_report_exists",
            "output_pptx_exists",
            "build_succeeded",
            "qa_run",
            "final_build_mode",
            "rendered_qa",
            "planning_warnings_blocking",
            "whitespace_warnings_blocking",
            "visual_review_required",
            "visual_review_required_by_cli",
            "visual_review_run",
            "acceptance_evidence_files_satisfied",
        ]
        for gate in expected_true_gates:
            if gates.get(gate) is not True:
                failures.append({"step": "delivery_readiness", "reason": "gate_not_true", "gate": gate, "actual": gates.get(gate)})
        if gates.get("fast_first_pass") is not False or gates.get("skip_render_allowed") is not False:
            failures.append({"step": "delivery_readiness", "reason": "unexpected_delivery_gate", "gates": gates})
        visual_requirement = delivery.get("visual_review_requirement") if isinstance(delivery.get("visual_review_requirement"), dict) else {}
        if visual_requirement.get("required") is not True or visual_requirement.get("run") is not True or visual_requirement.get("warning_count") != 0:
            failures.append({"step": "delivery_readiness", "reason": "visual_requirement_bad", "visual_review_requirement": visual_requirement})
        replay = delivery.get("reproducibility_contract") if isinstance(delivery.get("reproducibility_contract"), dict) else {}
        if replay.get("exists") is not True or replay.get("contract_version") != "deck_reproducibility_contract_v1" or replay.get("style_seed") != seed:
            failures.append({"step": "delivery_readiness", "reason": "replay_contract_missing", "reproducibility_contract": replay})
        delivery_quality = delivery.get("quality_context") if isinstance(delivery.get("quality_context"), dict) else {}
        delivery_slide_quality = delivery_quality.get("slide_quality_contract") if isinstance(delivery_quality.get("slide_quality_contract"), dict) else {}
        if delivery_slide_quality.get("contract_version") != "slide_quality_contract_v1":
            failures.append({"step": "delivery_readiness", "reason": "quality_context_missing", "quality_context": delivery_quality})
        delivery_density = delivery.get("layout_density") if isinstance(delivery.get("layout_density"), dict) else {}
        if (
            delivery_density.get("content_slide_count") != len(content_density_scores)
            or delivery_density.get("low_content_density_count") != 0
            or delivery_density.get("density_score_by_slide") != density_score_by_slide
        ):
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "layout_density_context_missing",
                    "expected_density_score_by_slide": density_score_by_slide,
                    "layout_density": delivery_density,
                }
            )
        if "## Layout Density" not in delivery_markdown or "low=`0`" not in delivery_markdown:
            failures.append(
                {
                    "step": "delivery_readiness_markdown",
                    "reason": "layout_density_section_missing",
                    "markdown_tail": delivery_markdown[-1200:],
                }
            )
        delivery_artifacts = delivery.get("artifact_context") if isinstance(delivery.get("artifact_context"), dict) else {}
        delivery_manifest = delivery_artifacts.get("artifact_manifest") if isinstance(delivery_artifacts.get("artifact_manifest"), dict) else {}
        delivery_selection = delivery_artifacts.get("artifact_selection") if isinstance(delivery_artifacts.get("artifact_selection"), dict) else {}
        if delivery_manifest.get("output_count", 0) < 1 or delivery_artifacts.get("tabular_data") != [DATA_REL]:
            failures.append({"step": "delivery_readiness", "reason": "artifact_context_missing", "artifact_context": delivery_artifacts})
        if (
            delivery_selection.get("binding_count") != len(EXPECTED_TRIPLET_VARIANTS)
            or delivery_selection.get("variants") != EXPECTED_TRIPLET_VARIANTS
            or delivery_selection.get("slide_ids") != selected_slide_ids
        ):
            failures.append(
                {
                    "step": "delivery_readiness",
                    "reason": "triplet_artifact_selection_context_missing",
                    "expected_variants": EXPECTED_TRIPLET_VARIANTS,
                    "expected_slide_ids": selected_slide_ids,
                    "artifact_selection": delivery_selection,
                }
            )
        if delivery_advance.get("decision") != "ready" or delivery_advance.get("final_delivery_status") != "ready":
            failures.append({"step": "advance_delivery", "reason": "not_ready", "advance": delivery_advance})

        total_ms = int(round((time.perf_counter() - started) * 1000))
        rendered_build_durations = _command_durations(command_results, " --visual-review ")
        final_build_ms = rendered_build_durations[0] if rendered_build_durations else 0
        repeat_build_ms = rendered_build_durations[1] if len(rendered_build_durations) > 1 else 0
        if args.max_total_seconds > 0 and total_ms > int(args.max_total_seconds * 1000):
            failures.append(
                {
                    "step": "speed",
                    "reason": "total_duration_exceeded",
                    "duration_ms": total_ms,
                    "max_total_seconds": args.max_total_seconds,
                }
            )
        if args.max_final_build_seconds > 0 and final_build_ms > int(args.max_final_build_seconds * 1000):
            failures.append(
                {
                    "step": "speed",
                    "reason": "final_build_duration_exceeded",
                    "duration_ms": final_build_ms,
                    "max_final_build_seconds": args.max_final_build_seconds,
                }
            )
        if args.max_repeat_build_seconds > 0 and repeat_build_ms > int(args.max_repeat_build_seconds * 1000):
            failures.append(
                {
                    "step": "speed",
                    "reason": "repeat_build_duration_exceeded",
                    "duration_ms": repeat_build_ms,
                    "max_repeat_build_seconds": args.max_repeat_build_seconds,
                }
            )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "data_path": DATA_REL,
            "seed": seed,
            "manifest_output_count": manifest.get("output_count") if isinstance(manifest, dict) else None,
            "aliases": sorted(aliases),
            "exterior_fraction": exterior_fraction,
            "selection_count": len(bindings),
            "selected_variants": binding_variants,
            "selected_slide_ids": selected_slide_ids,
            "figure_sidebar_body_font_size": figure_sidebar_body_font_size,
            "outline_sidebar_body_font_size": outline_sidebar_body_font_size,
            "expected_slide_count": expected_slide_count,
            "rendered_slide_count": qa.get("rendered_slide_count") if isinstance(qa, dict) else None,
            "visual_review_warning_count": visual_review.get("warning_count") if isinstance(visual_review, dict) else None,
            "density_score_by_slide": density_score_by_slide,
            "content_density_scores": content_density_scores,
            "min_content_density_score": args.min_content_density_score,
            "low_density_scores": low_density_scores,
            "delivery_layout_density": delivery.get("layout_density") if isinstance(delivery, dict) else {},
            "delivery_status": delivery.get("delivery_status") if isinstance(delivery, dict) else None,
            "advance_decision": delivery_advance.get("decision") if isinstance(delivery_advance, dict) else None,
            "qa_counts": qa_counts,
            "repeatability": repeatability,
            "speed": {
                "total_ms": total_ms,
                "fast_first_pass_ms": _command_duration(command_results, "--fast-first-pass"),
                "final_rendered_build_ms": final_build_ms,
                "repeat_rendered_build_ms": repeat_build_ms,
                "max_total_seconds": args.max_total_seconds,
                "max_final_build_seconds": args.max_final_build_seconds,
                "max_repeat_build_seconds": args.max_repeat_build_seconds,
            },
            "reports": {
                "pptx": str(pptx_path) if pptx_path.exists() else "",
                "qa": str(workspace / "build" / "qa" / "report.json"),
                "visual_review": str(workspace / "build" / "qa" / "visual_review" / "visual_review.json"),
                "contact_sheet": str(contact_sheet) if contact_quality.get("exists") else "",
                "build_report": str(workspace / "build" / "build_workspace_report.json"),
                "delivery": str(workspace / "build" / "delivery_readiness.json"),
            },
            "failures": failures,
            "commands": command_results,
        }
        build_dir.mkdir(parents=True, exist_ok=True)
        _write_json(build_dir / "rendered_data_delivery_smoke.json", summary)
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "manifest_output_count",
                        "selection_count",
                        "selected_variants",
                        "selected_slide_ids",
                        "figure_sidebar_body_font_size",
                        "outline_sidebar_body_font_size",
                        "expected_slide_count",
                        "rendered_slide_count",
                        "visual_review_warning_count",
                        "content_density_scores",
                        "min_content_density_score",
                        "delivery_status",
                        "advance_decision",
                        "qa_counts",
                        "repeatability",
                        "speed",
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
            _write_json(build_dir / "rendered_data_delivery_smoke.json", summary)
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1
    finally:
        _cleanup_workspace(workspace, created_temp=created_temp, keep=args.keep_workspace, passed=passed)


if __name__ == "__main__":
    raise SystemExit(main())
