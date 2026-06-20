#!/usr/bin/env python3
"""Smoke check for lab-report source-line footer chrome in generated PPTX."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}
EMU_PER_INCH = 914400
SLIDE_W = 10.0
FOOTER_RULE_Y = 5.265
FOOTER_TEXT_Y = 5.325
FOOTER_RIGHT_EDGE = 9.5


@dataclass
class ShapeRecord:
    text: str
    x: float
    y: float
    w: float
    h: float
    preset: str
    font_sizes: list[float]

    @property
    def bottom(self) -> float:
        return self.y + self.h


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _outline() -> dict[str, Any]:
    return {
        "title": "Lab Footer Chrome Smoke",
        "deck_style": {
            "header_mode": "lab-clean",
            "header_variant": "auto",
            "header_variants": ["top-bottom-rule", "plain"],
            "footer_mode": "source-line",
            "footer_page_numbers": True,
            "footer_source_label": "Sources",
            "footer_refs_label": "Refs",
        },
        "slides": [
            {
                "type": "title",
                "title": "Lab Footer Chrome Smoke",
                "subtitle": "Source-line footer, page number, and clean header variants",
                "chips": ["Footer rule", "Sources/refs", "Page number"],
            },
            {
                "slide_id": "footer-top-bottom",
                "type": "content",
                "variant": "table",
                "header_mode": "lab-clean",
                "header_variant": "top-bottom-rule",
                "footer_mode": "source-line",
                "title": "Top and bottom rules frame the report header",
                "subtitle": "Footer rule / compact provenance / page number",
                "headers": ["Check", "Expected", "State"],
                "rows": [
                    ["Footer rule", "Thin line above provenance", "Pass"],
                    ["Sources", "Small text under rule", "Pass"],
                    ["Page", "Bottom-right counter", "Pass"],
                    ["Body", "Evidence stays above footer", "Pass"],
                ],
                "caption": "Synthetic footer-structure fixture; layout only.",
                "footer": "Run 24A",
                "sources": ["S1 assay run", "S2 calibration"],
                "refs": ["R1 protocol"],
            },
            {
                "slide_id": "footer-plain",
                "type": "content",
                "variant": "table",
                "header_mode": "lab-clean",
                "header_variant": "plain",
                "footer_mode": "source-line",
                "title": "Plain header removes accent rules",
                "subtitle": "No header rule / same footer contract",
                "headers": ["Field", "Value", "QA intent"],
                "rows": [
                    ["Header", "Plain", "No rule shapes"],
                    ["Footer", "Source-line", "Stable rule"],
                    ["Sources", "S3", "Compact provenance"],
                    ["Page", "3/3", "Bottom-right"],
                ],
                "caption": "Plain header fixture keeps the same report footer.",
                "sources": ["S3 secondary run"],
            },
        ],
    }


def _float_attr(node: ET.Element | None, name: str) -> float:
    if node is None:
        return 0.0
    try:
        return int(node.attrib.get(name, "0")) / EMU_PER_INCH
    except ValueError:
        return 0.0


def _shape_records(pptx_path: Path, slide_number: int) -> list[ShapeRecord]:
    slide_name = f"ppt/slides/slide{slide_number}.xml"
    records: list[ShapeRecord] = []
    with zipfile.ZipFile(pptx_path, "r") as archive:
        root = ET.fromstring(archive.read(slide_name))
    for shape in root.findall(".//p:sp", NS):
        text = "".join(node.text or "" for node in shape.findall(".//a:t", NS)).strip()
        off = shape.find(".//a:xfrm/a:off", NS)
        ext = shape.find(".//a:xfrm/a:ext", NS)
        preset_node = shape.find(".//a:prstGeom", NS)
        font_sizes: list[float] = []
        for props in shape.findall(".//a:rPr", NS) + shape.findall(".//a:defRPr", NS):
            raw_size = props.attrib.get("sz")
            if not raw_size:
                continue
            try:
                font_sizes.append(float(raw_size) / 100.0)
            except ValueError:
                continue
        records.append(
            ShapeRecord(
                text=text,
                x=_float_attr(off, "x"),
                y=_float_attr(off, "y"),
                w=_float_attr(ext, "cx"),
                h=_float_attr(ext, "cy"),
                preset=preset_node.attrib.get("prst", "") if preset_node is not None else "",
                font_sizes=font_sizes,
            )
        )
    return records


def _near(value: float, expected: float, tolerance: float = 0.035) -> bool:
    return abs(value - expected) <= tolerance


def _blank_rects(records: list[ShapeRecord]) -> list[ShapeRecord]:
    return [record for record in records if not record.text and record.preset == "rect"]


def _assert_source_footer(
    failures: list[dict[str, Any]],
    records: list[ShapeRecord],
    *,
    slide_number: int,
    slide_count: int,
    required_parts: list[str],
) -> None:
    rule = [
        record
        for record in _blank_rects(records)
        if _near(record.y, FOOTER_RULE_Y)
        and 0.01 <= record.h <= 0.04
        and record.x <= 0.55
        and record.w >= 8.9
    ]
    if not rule:
        failures.append({"step": "footer_chrome", "reason": "missing_footer_rule", "slide": slide_number})

    page_text = f"{slide_number}/{slide_count}"
    page = next((record for record in records if record.text == page_text), None)
    if page is None:
        failures.append({"step": "footer_chrome", "reason": "missing_page_number", "slide": slide_number})
    elif (
        page.x < 8.85
        or not _near(page.y, FOOTER_TEXT_Y)
        or not _near(page.x + page.w, FOOTER_RIGHT_EDGE, 0.06)
        or not page.font_sizes
        or min(page.font_sizes) < 8.0
        or max(page.font_sizes) > 8.8
    ):
        failures.append(
            {
                "step": "footer_chrome",
                "reason": "page_number_not_bottom_right",
                "slide": slide_number,
                "record": page.__dict__,
            }
        )

    provenance = [
        record
        for record in records
        if "Sources:" in record.text or "Refs:" in record.text or record.text.startswith("Run ")
    ]
    matching = next(
        (
            record
            for record in provenance
            if all(part in record.text for part in required_parts)
        ),
        None,
    )
    if matching is None:
        failures.append(
            {
                "step": "footer_chrome",
                "reason": "missing_source_ref_text",
                "slide": slide_number,
                "texts": [record.text for record in provenance],
            }
        )
    elif (
        matching.x > 0.55
        or not _near(matching.y, FOOTER_TEXT_Y)
        or matching.w < 8.0
        or not matching.font_sizes
        or min(matching.font_sizes) > 8.1
    ):
        failures.append(
            {
                "step": "footer_chrome",
                "reason": "source_ref_text_not_small_below_rule",
                "slide": slide_number,
                "record": matching.__dict__,
            }
        )

    footer_texts = {page_text, *(record.text for record in provenance)}
    intrusions = [
        record
        for record in records
        if record.text
        and record.text not in footer_texts
        and record.bottom > FOOTER_RULE_Y - 0.12
    ]
    if intrusions:
        failures.append(
            {
                "step": "footer_chrome",
                "reason": "content_intrudes_into_footer_reserve",
                "slide": slide_number,
                "records": [record.__dict__ for record in intrusions],
            }
        )


def _assert_top_bottom_header(failures: list[dict[str, Any]], records: list[ShapeRecord]) -> None:
    blank_rects = _blank_rects(records)
    top_rule = [record for record in blank_rects if 0.04 <= record.y <= 0.07 and 0.015 <= record.h <= 0.04]
    shade = [record for record in blank_rects if 0.07 <= record.y <= 0.10 and 0.06 <= record.h <= 0.12]
    bottom_rule = [record for record in blank_rects if 1.12 <= record.y <= 1.18 and 0.008 <= record.h <= 0.03]
    if not top_rule or not shade or not bottom_rule:
        failures.append(
            {
                "step": "header_chrome",
                "reason": "missing_top_bottom_rule_treatment",
                "top_rule": [record.__dict__ for record in top_rule],
                "shade": [record.__dict__ for record in shade],
                "bottom_rule": [record.__dict__ for record in bottom_rule],
            }
        )


def _assert_plain_header(failures: list[dict[str, Any]], records: list[ShapeRecord]) -> None:
    header_rules = [
        record
        for record in _blank_rects(records)
        if record.y < 1.30 and record.h <= 0.12 and record.w > SLIDE_W * 0.70
    ]
    if header_rules:
        failures.append(
            {
                "step": "header_chrome",
                "reason": "plain_header_has_rule_shapes",
                "records": [record.__dict__ for record in header_rules],
            }
        )


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the lab footer chrome PPTX smoke check.")
    parser.add_argument("--workspace", default="", help="Workspace/output directory. Defaults to a temporary directory.")
    parser.add_argument("--keep-workspace", action="store_true", help="Keep the temporary workspace after a passing run.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-lab-footer-"))
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
    commands: list[dict[str, Any]] = []
    outline_path = workspace / "outline.json"
    pptx_path = workspace / "lab_footer_chrome.pptx"
    qa_dir = workspace / "qa"

    try:
        _write_json(outline_path, _outline())
        build_cmd = [
            "node",
            str(repo / "scripts" / "build_deck_pptxgenjs.js"),
            "--outline",
            str(outline_path),
            "--output",
            str(pptx_path),
            "--style-preset",
            "lab-report",
        ]
        result = _run(build_cmd, cwd=repo)
        commands.append({"command": build_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1600:]})
        if result.returncode != 0:
            failures.append({"step": "build_deck_pptxgenjs", "returncode": result.returncode})

        qa_cmd = [
            sys.executable,
            str(repo / "scripts" / "qa_gate.py"),
            "--input",
            str(pptx_path),
            "--outdir",
            str(qa_dir),
            "--style-preset",
            "lab-report",
            "--skip-render",
        ]
        result = _run(qa_cmd, cwd=repo)
        commands.append({"command": qa_cmd, "returncode": result.returncode, "stdout_tail": result.stdout[-1600:]})
        if result.returncode != 0:
            failures.append({"step": "qa_gate", "returncode": result.returncode})

        qa_report = {}
        qa_report_path = qa_dir / "qa_report.json"
        if qa_report_path.exists():
            qa_report = json.loads(qa_report_path.read_text(encoding="utf-8"))
            for key in (
                "overflow_count",
                "overlap_count",
                "geometry_error_count",
                "design_error_count",
                "design_warning_count",
            ):
                if qa_report.get(key) != 0:
                    failures.append({"step": "qa_report", "reason": "nonzero_count", "key": key, "value": qa_report.get(key)})
        else:
            failures.append({"step": "qa_report", "reason": "missing_report"})

        slide_count = 3
        top_bottom_records = _shape_records(pptx_path, 2)
        plain_records = _shape_records(pptx_path, 3)
        _assert_top_bottom_header(failures, top_bottom_records)
        _assert_plain_header(failures, plain_records)
        _assert_source_footer(
            failures,
            top_bottom_records,
            slide_number=2,
            slide_count=slide_count,
            required_parts=["Run 24A", "Sources: S1 assay run; S2 calibration", "Refs: R1 protocol"],
        )
        _assert_source_footer(
            failures,
            plain_records,
            slide_number=3,
            slide_count=slide_count,
            required_parts=["Sources: S3 secondary run"],
        )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "pptx": str(pptx_path),
            "qa_counts": {key: qa_report.get(key) for key in sorted(qa_report) if key.endswith("_count")},
            "top_bottom_shape_count": len(top_bottom_records),
            "plain_shape_count": len(plain_records),
            "failures": failures,
            "commands": commands,
        }
        _write_json(workspace / "lab_footer_chrome_smoke.json", summary)
        print(
            json.dumps(
                {
                    "passed": passed,
                    "workspace": str(workspace),
                    "pptx": str(pptx_path),
                    "top_bottom_shape_count": len(top_bottom_records),
                    "plain_shape_count": len(plain_records),
                    "failures": failures,
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
            "commands": commands,
        }
        try:
            _write_json(workspace / "lab_footer_chrome_smoke.json", summary)
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
