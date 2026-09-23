#!/usr/bin/env python3
"""Build, render, and hard-gate one source-first quick deck."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from workflow_atom_context import DEFAULT_FAMILY, build_workflow_atom_context  # noqa: E402
from repair_packet import build_repair_packet  # noqa: E402
from office_package_hash import office_package_normalized_sha256  # noqa: E402


QA_BLOCKING_KEYS = (
    "overflow_count",
    "overlap_count",
    "geometry_error_count",
    "geometry_warning_count",
    "whitespace_warning_count",
    "visual_warning_count",
    "visual_review_warning_count",
    "design_error_count",
    "design_warning_count",
    "accessibility_error_count",
    "accessibility_warning_count",
)

QA_FILES = (
    "qa_report.json", "issues.json", "outline.md", "layout_lint.json",
    "visual_qa.json", "design_rules.json", "accessibility.json",
    "repair_packet.json", "finalize_receipt.json",
)
RENDER_FILES = ("render_report.json",)
VISUAL_REVIEW_FILES = (
    "visual_review.json", "visual_review.md", "contact_sheet.jpg",
    "visual_review_receipt.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clear_owned_qa_evidence(qa_dir: Path) -> None:
    for name in QA_FILES:
        (qa_dir / name).unlink(missing_ok=True)
    render_dir = qa_dir / "renders"
    for name in RENDER_FILES:
        (render_dir / name).unlink(missing_ok=True)
    for pattern in ("slide-*.jpg", "slide-*.jpeg", "slide-*.png"):
        for path in render_dir.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
    review_dir = qa_dir / "visual_review"
    for name in VISUAL_REVIEW_FILES:
        (review_dir / name).unlink(missing_ok=True)


def _restore_previous_output_if_equivalent(previous: Path, output: Path) -> bool:
    if not previous.is_file() or not output.is_file():
        return False
    if office_package_normalized_sha256(previous) != office_package_normalized_sha256(output):
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{output.name}-restore-", dir=output.parent)
    try:
        with os.fdopen(handle, "wb") as destination, previous.open("rb") as source:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True


def _load_outline(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("outline root must be a JSON object")
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _completion_status(records: list[dict[str, Any]], qa_dir: Path) -> dict[str, Any]:
    qa_path = qa_dir / "qa_report.json"
    qa = _load_json(qa_path) if any(r.get("stage") == "qa" for r in records) and qa_path.is_file() else {}
    qa_counts = {key: int(qa.get(key, 0) or 0) for key in QA_BLOCKING_KEYS}
    failed_stage = next(
        (str(record.get("stage") or "") for record in records if not bool(record.get("accepted", False))),
        "",
    )
    render_rc = qa.get("render_rc")
    render_failed = render_rc is not None and int(render_rc or 0) != 0
    static_keys = tuple(key for key in QA_BLOCKING_KEYS if key not in {"visual_review_warning_count"})
    static_findings = sum(qa_counts[key] for key in static_keys)
    if not failed_stage:
        category = "passed"
        next_action = "Inspect the rendered slides, repair any visual defects in source, and record the visual judgment before delivery."
    elif failed_stage == "preflight":
        category = "outline_preflight"
        next_action = "Fix the reported outline fields, then rerun the finalizer once."
    elif failed_stage == "build":
        category = "build_failure"
        next_action = "Fix the reported source or asset error; do not patch the generated PPTX."
    elif failed_stage == "qa" and render_failed and static_findings == 0:
        category = "render_environment"
        next_action = (
            "Preserve the built deck and static QA report. Do not probe alternate Office apps, "
            "Python installations, or preview tools; rerun the same finalizer outside the sandbox "
            "to complete rendered visual review."
        )
    else:
        category = "qa_findings"
        next_action = "Read repair_packet.json and the affected slide images, edit outline.json or its renderer, and rerun until clean or report the blocker."
    return {
        "failure_category": category,
        "failed_stage": failed_stage,
        "render_status": "deferred_environment" if category == "render_environment" else (
            "passed" if qa and not render_failed else "not_completed"
        ),
        "qa_counts": qa_counts,
        "visual_inspection_status": "not_recorded",
        "next_action": next_action,
    }


def _thresholds(
    outline: dict[str, Any],
    body_override: float | None,
    support_override: float | None,
    metadata_override: float | None,
) -> tuple[float, float, float]:
    style = outline.get("deck_style") if isinstance(outline.get("deck_style"), dict) else {}
    contract = style.get("readability_contract") if isinstance(style.get("readability_contract"), dict) else {}
    body = body_override if body_override is not None else float(contract.get("min_body_pt", 16))
    support = support_override if support_override is not None else float(contract.get("min_support_pt", 13))
    metadata = metadata_override
    if metadata is None:
        metadata = float(
            contract.get(
                "min_metadata_pt",
                contract.get("min_footer_pt", contract.get("min_caption_pt", 9)),
            )
        )
    return body, support, metadata


def _resolve_style_preset(outline: dict[str, Any], requested: str) -> tuple[str, str]:
    explicit = str(requested or "auto").strip().lower()
    if explicit and explicit != "auto":
        return explicit, "explicit_cli"
    deck_style = outline.get("deck_style") if isinstance(outline.get("deck_style"), dict) else {}
    metadata = outline.get("metadata") if isinstance(outline.get("metadata"), dict) else {}
    for value in (
        outline.get("style_preset"),
        deck_style.get("style_preset"),
        metadata.get("style_preset"),
    ):
        candidate = str(value or "").strip().lower()
        if candidate and candidate != "auto":
            return candidate, "outline_design_choice"
    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    prompt_parts = [str(outline.get("title") or "")]
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        prompt_parts.extend(
            str(slide.get(key) or "")
            for key in ("title", "subtitle", "slide_intent", "role", "variant")
        )
    context = build_workflow_atom_context(
        user_prompt=" ".join(part for part in prompt_parts if part).strip(),
        style_preset="",
        slide_count=max(3, len(slides)),
        include_prompt=False,
    )
    resolved = str(context.get("target_family") or DEFAULT_FAMILY).strip().lower()
    return resolved or DEFAULT_FAMILY, "deterministic_outline_fallback"


def _run(
    stage: str,
    command: list[str],
    records: list[dict[str, Any]],
    *,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> bool:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout or ""
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    records.append(
        {
            "stage": stage,
            "command": command,
            "returncode": completed.returncode,
            "accepted_returncodes": list(accepted_returncodes),
            "accepted": completed.returncode in accepted_returncodes,
            "duration_seconds": round(time.perf_counter() - started, 3),
        }
    )
    return completed.returncode in accepted_returncodes


def _write_receipt(
    path: Path,
    *,
    outline: Path,
    output: Path,
    qa_dir: Path,
    style_preset: str,
    style_resolution_basis: str,
    thresholds: tuple[float, float, float],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = bool(records) and all(bool(record.get("accepted", False)) for record in records)
    completion = _completion_status(records, qa_dir)
    payload = {
        "schema_version": "quick-deck-finalization/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "outline": str(outline),
        "outline_sha256": _sha256(outline),
        "output": str(output),
        "output_exists": output.is_file(),
        "output_sha256": _sha256(output) if output.is_file() else "",
        "style_preset": style_preset,
        "style_resolution_basis": style_resolution_basis,
        "readability": {
            "min_body_pt": thresholds[0],
            "min_support_pt": thresholds[1],
            "min_metadata_pt": thresholds[2],
        },
        "qa_dir": str(qa_dir),
        "qa_report": str(qa_dir / "qa_report.json"),
        "contact_sheet": str(qa_dir / "visual_review" / "contact_sheet.jpg"),
        "total_duration_seconds": round(
            sum(float(record.get("duration_seconds", 0) or 0) for record in records),
            3,
        ),
        **completion,
        "stages": records,
    }
    repair_path = qa_dir / "repair_packet.json"
    if any(record.get("stage") == "qa" for record in records) and (qa_dir / "qa_report.json").is_file():
        try:
            packet = build_repair_packet(outline, qa_dir)
            repair_path.parent.mkdir(parents=True, exist_ok=True)
            repair_path.write_text(json.dumps(packet, separators=(",", ":")) + "\n", encoding="utf-8")
            payload["repair_packet"] = str(repair_path)
        except (OSError, ValueError) as exc:
            payload["repair_packet_error"] = str(exc)
    else:
        repair_path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--style-preset",
        default="auto",
        help="Preset name, or auto to honor outline.deck_style.style_preset and route only as fallback.",
    )
    parser.add_argument("--qa-dir", type=Path)
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--render-cache-dir", type=Path, help="Opt in to verified identical-render reuse.")
    parser.add_argument("--min-body-pt", type=float)
    parser.add_argument("--min-support-pt", type=float)
    parser.add_argument("--min-metadata-pt", type=float)
    parser.add_argument(
        "--strict-preflight-warnings",
        action="store_true",
        help="Treat preflight warnings as blocking. By default they are recorded and the hard QA gate decides.",
    )
    args = parser.parse_args()

    outline = args.outline.resolve()
    output = args.output.resolve()
    qa_dir = (args.qa_dir or output.parent / f"{output.stem}-qa").resolve()
    if outline == output:
        parser.error("--output must not overwrite --outline")
    if qa_dir in {outline, output}:
        parser.error("--qa-dir must not be the outline or output path")
    receipt_path = qa_dir / "finalize_receipt.json"
    records: list[dict[str, Any]] = []
    try:
        outline_payload = _load_outline(outline)
        thresholds = _thresholds(
            outline_payload,
            args.min_body_pt,
            args.min_support_pt,
            args.min_metadata_pt,
        )
        style_preset, style_resolution_basis = _resolve_style_preset(
            outline_payload,
            args.style_preset,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL Could not load outline: {exc}", file=sys.stderr)
        return 2

    node = shutil.which("node")
    if not node:
        print("FAIL Node.js is required", file=sys.stderr)
        return 2

    preflight_returncodes = (0,) if args.strict_preflight_warnings else (0, 1)
    stages = [
        (
            "preflight",
            [sys.executable, str(ROOT / "scripts" / "preflight.py"), "--outline", str(outline)],
            preflight_returncodes,
        ),
        (
            "build",
            [
                node,
                str(ROOT / "scripts" / "build_deck_pptxgenjs.js"),
                "--outline",
                str(outline),
                "--output",
                str(output),
                "--style-preset",
                style_preset,
                *(["--asset-root", str(args.asset_root.resolve())] if args.asset_root else []),
            ],
            (0,),
        ),
        (
            "qa",
            [
                sys.executable,
                str(ROOT / "scripts" / "qa_gate.py"),
                "--input",
                str(output),
                "--outline",
                str(outline),
                "--outdir",
                str(qa_dir),
                "--style-preset",
                style_preset,
                "--strict-geometry",
                "--fail-on-geometry-warnings",
                "--fail-on-whitespace-warnings",
                "--run-visual-review",
                "--fail-on-visual-review-warnings",
                "--fail-on-design-warnings",
                "--accessibility",
                "--strict-accessibility",
                "--accessibility-min-body-pt",
                str(thresholds[0]),
                "--accessibility-min-support-pt",
                str(thresholds[1]),
                "--accessibility-min-metadata-pt",
                str(thresholds[2]),
                "--skip-manual-review",
                *(["--render-cache-dir", str(args.render_cache_dir.resolve())] if args.render_cache_dir else []),
            ],
            (0,),
        ),
    ]

    with tempfile.TemporaryDirectory(prefix="quick-deck-previous-") as temporary:
        previous = Path(temporary) / output.name
        preserve_raw_output = bool(args.render_cache_dir and output.is_file())
        if preserve_raw_output:
            shutil.copyfile(output, previous)
        for stage, command, accepted_returncodes in stages:
            if stage == "qa":
                _clear_owned_qa_evidence(qa_dir)
            if not _run(stage, command, records, accepted_returncodes=accepted_returncodes):
                receipt = _write_receipt(
                    receipt_path,
                    outline=outline,
                    output=output,
                    qa_dir=qa_dir,
                    style_preset=style_preset,
                    style_resolution_basis=style_resolution_basis,
                    thresholds=thresholds,
                    records=records,
                )
                print(json.dumps(receipt, indent=2, sort_keys=True))
                return 1
            if stage == "build" and preserve_raw_output:
                restored = _restore_previous_output_if_equivalent(previous, output)
                records[-1]["previous_output_bytes_restored"] = restored
                records[-1]["output_sha256_after_restore"] = _sha256(output)

    receipt = _write_receipt(
        receipt_path,
        outline=outline,
        output=output,
        qa_dir=qa_dir,
        style_preset=style_preset,
        style_resolution_basis=style_resolution_basis,
        thresholds=thresholds,
        records=records,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
