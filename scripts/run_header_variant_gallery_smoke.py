#!/usr/bin/env python3
"""Smoke check all-preset header variant gallery decks."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from office_package_hash import OFFICE_PACKAGE_HASH_ALGORITHM, office_package_normalized_sha256
from style_treatment_profiles import SUPPORTED_HEADER_VARIANTS


SUPPORTED_REPORT_HEADER_VARIANTS = list(SUPPORTED_HEADER_VARIANTS)

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


def _cleanup(outdir: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(outdir, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build all-preset header variant gallery decks and verify clean render-free QA."
    )
    parser.add_argument(
        "--outdir",
        default="",
        help="Output directory. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep the temporary gallery artifacts after a passing run.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.outdir).strip())
    outdir = (
        Path(args.outdir).expanduser().resolve()
        if str(args.outdir).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-header-gallery-"))
    )
    outdir.mkdir(parents=True, exist_ok=True)
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []

    try:
        expected_presets = _preset_names(repo)
        cmd = [
            sys.executable,
            str(repo / "scripts" / "build_header_variant_gallery.py"),
            "--outdir",
            str(outdir),
            "--qa",
        ]
        result = _run(cmd, cwd=repo)
        command_results.append(
            {
                "command": cmd,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1800:],
            }
        )
        if result.returncode != 0:
            failures.append({"step": "build_header_variant_gallery", "returncode": result.returncode})

        summary_path = outdir / "summary.json"
        summary = _load_json(summary_path)
        if not isinstance(summary, dict):
            summary = {}
            failures.append({"step": "summary", "reason": "summary_missing_or_invalid"})

        presets = summary.get("presets") if isinstance(summary.get("presets"), list) else []
        variants = summary.get("variants") if isinstance(summary.get("variants"), list) else []
        records = summary.get("records") if isinstance(summary.get("records"), list) else []
        if presets != expected_presets:
            failures.append(
                {
                    "step": "summary",
                    "reason": "preset_list_mismatch",
                    "expected": expected_presets,
                    "actual": presets,
                }
            )
        if variants != SUPPORTED_REPORT_HEADER_VARIANTS:
            failures.append(
                {
                    "step": "summary",
                    "reason": "variant_list_mismatch",
                    "expected": SUPPORTED_REPORT_HEADER_VARIANTS,
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

        records_by_preset = {
            str(record.get("preset")): record
            for record in records
            if isinstance(record, dict) and record.get("preset")
        }
        qa_counts_by_preset: dict[str, dict[str, int]] = {}
        for preset in expected_presets:
            record = records_by_preset.get(preset)
            if not record:
                failures.append({"step": "records", "reason": "missing_preset_record", "preset": preset})
                continue
            outline = Path(str(record.get("outline") or ""))
            pptx = Path(str(record.get("pptx") or ""))
            qa_report = Path(str(record.get("qa_report") or ""))
            for label, path in (("outline", outline), ("pptx", pptx), ("qa_report", qa_report)):
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
            if not isinstance(qa_payload, dict):
                failures.append({"step": "qa_report", "reason": "qa_report_invalid", "preset": preset})
                continue
            counts: dict[str, int] = {}
            for key in ZERO_QA_COUNT_KEYS:
                value = qa_payload.get(key, 0)
                counts[key] = int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0
            placeholder_hits = qa_payload.get("placeholder_hits")
            placeholder_count = len(placeholder_hits) if isinstance(placeholder_hits, list) else 0
            counts["placeholder_hit_count"] = placeholder_count
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

        passed = not failures
        report = {
            "passed": passed,
            "outdir": str(outdir),
            "preset_count": len(expected_presets),
            "variant_count": len(SUPPORTED_REPORT_HEADER_VARIANTS),
            "presets": expected_presets,
            "variants": SUPPORTED_REPORT_HEADER_VARIANTS,
            "qa_counts_by_preset": qa_counts_by_preset,
            "summary_path": str(summary_path),
            "failures": failures,
            "commands": command_results,
        }
        (outdir / "header_variant_gallery_smoke.json").write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "passed": passed,
                    "outdir": str(outdir),
                    "preset_count": len(expected_presets),
                    "variant_count": len(SUPPORTED_REPORT_HEADER_VARIANTS),
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
            "commands": command_results,
        }
        try:
            (outdir / "header_variant_gallery_smoke.json").write_text(
                json.dumps(report, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(report, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
