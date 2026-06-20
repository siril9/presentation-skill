#!/usr/bin/env python3
"""Rendered smoke for header-variant gallery decks across presets."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageStat
except Exception:  # pragma: no cover - dependency guard
    Image = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]

from pptx import Presentation

from office_package_hash import OFFICE_PACKAGE_HASH_ALGORITHM, office_package_normalized_sha256
from style_treatment_profiles import SUPPORTED_HEADER_VARIANTS


ZERO_QA_COUNT_KEYS = [
    "overflow_count",
    "overlap_count",
    "geometry_error_count",
    "geometry_warning_count",
    "whitespace_warning_count",
    "visual_warning_count",
    "visual_review_warning_count",
    "design_error_count",
    "design_warning_count",
]


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


def _image_quality(path: Path) -> dict[str, Any]:
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
    valid = width >= 640 and height >= 360 and max_channel_range >= 10
    return {
        "path": str(path),
        "exists": True,
        "valid": valid,
        "width": width,
        "height": height,
        "mean_rgb": [round(value, 2) for value in stat.mean],
        "channel_ranges": channel_ranges,
        "max_channel_range": max_channel_range,
        "reason": "" if valid else "too_small_or_blank",
    }


def _check_required_tools(failures: list[dict[str, Any]]) -> None:
    for name in ("node", "soffice", "pdftoppm"):
        if not shutil.which(name):
            failures.append({"step": "tooling", "reason": "missing_binary", "binary": name})
    if Image is None or ImageStat is None:
        failures.append({"step": "tooling", "reason": "missing_python_dependency", "dependency": "Pillow"})


def _cleanup(outdir: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(outdir, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build, render, and inspect header-variant gallery decks. "
            "Defaults to all loadable presets."
        )
    )
    parser.add_argument("--outdir", default="", help="Output directory. Defaults to a temporary directory.")
    parser.add_argument("--presets", nargs="*", default=[], help="Optional preset subset.")
    parser.add_argument("--dpi", type=int, default=90, help="Render DPI passed to render_slides.py.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep artifacts after a passing run.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.outdir).strip())
    outdir = (
        Path(args.outdir).expanduser().resolve()
        if str(args.outdir).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-rendered-header-gallery-"))
    )
    outdir.mkdir(parents=True, exist_ok=True)

    failures: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    _check_required_tools(failures)

    try:
        expected_presets = [str(item) for item in args.presets] if args.presets else _preset_names(repo)
        expected_variants = list(SUPPORTED_HEADER_VARIANTS)
        gallery_cmd = [
            sys.executable,
            str(repo / "scripts" / "build_header_variant_gallery.py"),
            "--outdir",
            str(outdir),
            "--qa",
            "--render",
            "--dpi",
            str(args.dpi),
        ]
        if args.presets:
            gallery_cmd.append("--presets")
            gallery_cmd.extend(expected_presets)
        result = _run(gallery_cmd, cwd=repo)
        commands.append(
            {
                "command": gallery_cmd,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-2400:],
            }
        )
        if result.returncode != 0:
            failures.append(
                {
                    "step": "build_header_variant_gallery",
                    "reason": "command_failed",
                    "returncode": result.returncode,
                }
            )

        summary_path = outdir / "summary.json"
        summary = _load_json(summary_path)
        if not isinstance(summary, dict):
            summary = {}
            failures.append({"step": "summary", "reason": "summary_missing_or_invalid"})

        presets = summary.get("presets") if isinstance(summary.get("presets"), list) else []
        variants = summary.get("variants") if isinstance(summary.get("variants"), list) else []
        records = summary.get("records") if isinstance(summary.get("records"), list) else []
        contact_sheet_raw = str(summary.get("contact_sheet") or "")
        contact_sheet = Path(contact_sheet_raw) if contact_sheet_raw else None

        if presets != expected_presets:
            failures.append(
                {
                    "step": "summary",
                    "reason": "preset_list_mismatch",
                    "expected": expected_presets,
                    "actual": presets,
                }
            )
        if variants != expected_variants:
            failures.append(
                {
                    "step": "summary",
                    "reason": "variant_list_mismatch",
                    "expected": expected_variants,
                    "actual": variants,
                }
            )
        if len(records) != len(expected_presets):
            failures.append(
                {
                    "step": "summary",
                    "reason": "record_count_mismatch",
                    "expected": len(expected_presets),
                    "actual": len(records),
                }
            )

        contact_quality = _image_quality(contact_sheet) if contact_sheet else {"valid": False, "reason": "missing"}
        if not contact_quality.get("valid"):
            failures.append({"step": "contact_sheet", "reason": "invalid_or_blank", "quality": contact_quality})

        records_by_preset = {
            str(record.get("preset")): record
            for record in records
            if isinstance(record, dict) and record.get("preset")
        }
        qa_counts_by_preset: dict[str, dict[str, int]] = {}
        render_counts_by_preset: dict[str, int] = {}
        image_quality_by_preset: dict[str, list[dict[str, Any]]] = {}
        pptx_fingerprints_by_preset: dict[str, dict[str, Any]] = {}

        for preset in expected_presets:
            record = records_by_preset.get(preset)
            if not record:
                failures.append({"step": "records", "reason": "missing_preset_record", "preset": preset})
                continue
            outline = Path(str(record.get("outline") or ""))
            pptx = Path(str(record.get("pptx") or ""))
            qa_report = Path(str(record.get("qa_report") or ""))
            render_dir = Path(str(record.get("render_dir") or ""))
            for label, path in (
                ("outline", outline),
                ("pptx", pptx),
                ("qa_report", qa_report),
                ("render_dir", render_dir),
            ):
                if not path.exists():
                    failures.append(
                        {
                            "step": "records",
                            "reason": f"{label}_missing",
                            "preset": preset,
                            "path": str(path),
                        }
                    )
            fingerprint = (
                record.get("pptx_fingerprint")
                if isinstance(record.get("pptx_fingerprint"), dict)
                else {}
            )
            expected_normalized = office_package_normalized_sha256(pptx) if pptx.exists() else ""
            pptx_fingerprints_by_preset[preset] = fingerprint
            if (
                fingerprint.get("exists") is not True
                or not fingerprint.get("sha256")
                or fingerprint.get("normalized_sha256") != expected_normalized
                or fingerprint.get("normalized_sha256_algorithm") != OFFICE_PACKAGE_HASH_ALGORITHM
            ):
                failures.append(
                    {
                        "step": "records",
                        "reason": "pptx_fingerprint_missing_or_stale",
                        "preset": preset,
                        "fingerprint": fingerprint,
                    }
                )

            qa_payload = _load_json(qa_report)
            counts: dict[str, int] = {}
            if not isinstance(qa_payload, dict):
                failures.append({"step": "qa_report", "reason": "qa_report_invalid", "preset": preset})
            else:
                for key in ZERO_QA_COUNT_KEYS:
                    value = qa_payload.get(key, 0)
                    counts[key] = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
                placeholder_hits = qa_payload.get("placeholder_hits")
                counts["placeholder_hit_count"] = len(placeholder_hits) if isinstance(placeholder_hits, list) else 0
                qa_counts_by_preset[preset] = counts
                positives = {key: value for key, value in counts.items() if value}
                if positives:
                    failures.append(
                        {
                            "step": "qa_report",
                            "reason": "nonzero_qa_counts",
                            "preset": preset,
                            "counts": positives,
                        }
                    )

            rendered = _rendered_paths(render_dir)
            render_counts_by_preset[preset] = len(rendered)
            expected_slide_count = len(expected_variants) + 1
            if pptx.exists():
                expected_slide_count = len(Presentation(str(pptx)).slides)
            if len(rendered) != expected_slide_count:
                failures.append(
                    {
                        "step": "rendered_slides",
                        "reason": "slide_count_mismatch",
                        "preset": preset,
                        "expected": expected_slide_count,
                        "actual": len(rendered),
                    }
                )
            content_images = record.get("rendered_content_images")
            if not isinstance(content_images, list) or len(content_images) != len(expected_variants):
                failures.append(
                    {
                        "step": "rendered_content_images",
                        "reason": "content_variant_count_mismatch",
                        "preset": preset,
                        "expected": len(expected_variants),
                        "actual": len(content_images) if isinstance(content_images, list) else 0,
                    }
                )
            qualities = [_image_quality(path) for path in rendered]
            image_quality_by_preset[preset] = qualities
            invalid = [item for item in qualities if not item.get("valid")]
            if invalid:
                failures.append(
                    {
                        "step": "rendered_images",
                        "reason": "invalid_or_blank_render",
                        "preset": preset,
                        "invalid": invalid,
                    }
                )

        visual_review_summary: dict[str, Any] = {}
        review_preset = "lab-report" if "lab-report" in records_by_preset else (expected_presets[0] if expected_presets else "")
        if review_preset and review_preset in records_by_preset:
            record = records_by_preset[review_preset]
            visual_dir = outdir / str(review_preset) / "visual_review"
            visual_report = visual_dir / "visual_review.json"
            visual_cmd = [
                sys.executable,
                str(repo / "scripts" / "visual_review.py"),
                "--input",
                str(record.get("pptx")),
                "--outdir",
                str(visual_dir),
                "--renders-dir",
                str(record.get("render_dir")),
                "--outline",
                str(record.get("outline")),
                "--report",
                str(visual_report),
                "--markdown",
                str(visual_dir / "visual_review.md"),
                "--fail-on-warnings",
            ]
            result = _run(visual_cmd, cwd=repo)
            commands.append(
                {
                    "command": visual_cmd,
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-1800:],
                }
            )
            visual_payload = _load_json(visual_report)
            visual_review_summary = visual_payload if isinstance(visual_payload, dict) else {}
            if result.returncode != 0:
                failures.append(
                    {
                        "step": "visual_review",
                        "reason": "command_failed",
                        "preset": review_preset,
                        "returncode": result.returncode,
                    }
                )
            if int(visual_review_summary.get("warning_count", 0) or 0) != 0:
                failures.append(
                    {
                        "step": "visual_review",
                        "reason": "warning_count_nonzero",
                        "preset": review_preset,
                        "warning_count": visual_review_summary.get("warning_count"),
                    }
                )
            review_contact_raw = str(visual_review_summary.get("contact_sheet") or "")
            review_contact = Path(review_contact_raw) if review_contact_raw else None
            review_contact_quality = _image_quality(review_contact) if review_contact else {"valid": False, "reason": "missing"}
            if not review_contact_quality.get("valid"):
                failures.append(
                    {
                        "step": "visual_review",
                        "reason": "contact_sheet_invalid_or_blank",
                        "preset": review_preset,
                        "quality": review_contact_quality,
                    }
                )

        passed = not failures
        report = {
            "passed": passed,
            "outdir": str(outdir),
            "preset_count": len(expected_presets),
            "variant_count": len(expected_variants),
            "presets": expected_presets,
            "variants": expected_variants,
            "summary_path": str(summary_path),
            "contact_sheet": str(contact_sheet) if contact_sheet else "",
            "contact_sheet_quality": contact_quality,
            "render_counts_by_preset": render_counts_by_preset,
            "qa_counts_by_preset": qa_counts_by_preset,
            "image_quality_by_preset": image_quality_by_preset,
            "pptx_fingerprints_by_preset": pptx_fingerprints_by_preset,
            "visual_review_preset": review_preset,
            "visual_review": {
                "warning_count": visual_review_summary.get("warning_count"),
                "info_count": visual_review_summary.get("info_count"),
                "rendered_slide_count": visual_review_summary.get("rendered_slide_count"),
                "contact_sheet": visual_review_summary.get("contact_sheet"),
                "report": str(outdir / str(review_preset) / "visual_review" / "visual_review.json") if review_preset else "",
            },
            "failures": failures,
            "commands": commands,
        }
        _write_json(outdir / "rendered_header_gallery_smoke.json", report)
        print(
            json.dumps(
                {
                    "passed": passed,
                    "outdir": str(outdir),
                    "preset_count": len(expected_presets),
                    "variant_count": len(expected_variants),
                    "render_counts_by_preset": render_counts_by_preset,
                    "visual_review_preset": review_preset,
                    "visual_review_warning_count": visual_review_summary.get("warning_count"),
                    "contact_sheet": str(contact_sheet) if contact_sheet else "",
                    "failures": failures,
                },
                indent=2,
            )
        )
        _cleanup(outdir, created_temp=created_temp, keep=args.keep_artifacts, passed=passed)
        return 0 if passed else 1
    except Exception as exc:
        failures.append({"step": "smoke", "reason": str(exc)})
        report = {
            "passed": False,
            "outdir": str(outdir),
            "failures": failures,
            "commands": commands,
        }
        try:
            _write_json(outdir / "rendered_header_gallery_smoke.json", report)
        except OSError:
            pass
        print(json.dumps(report, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
