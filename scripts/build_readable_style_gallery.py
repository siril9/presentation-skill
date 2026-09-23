#!/usr/bin/env python3
"""Compare eight styles using identical editable content at delivery type sizes."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
import re
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from office_package_hash import office_package_normalized_sha256
from taste_grammar_catalog import PRESET_TO_GRAMMAR


ROOT = Path(__file__).resolve().parents[1]
STYLES = [
    ("arctic-minimal", "Answer Pyramid"),
    ("lab-report", "Assay Notebook"),
    ("executive-clinical", "Care Pathway"),
    ("editorial-minimal", "Editorial Spread"),
    ("sunset-investor", "Investor Thesis"),
    ("lavender-ops", "Operating Grid"),
    ("warm-terracotta", "Public Docket"),
    ("midnight-neon", "Telemetry Canvas"),
]
GROUPS = {"evidence_decisions": (2, 7), "data_comparisons": (4, 6), "narrative_process": (1, 3)}


def source_fidelity(path: Path, outline: dict) -> dict:
    """Check this controlled fixture's visible content, not arbitrary deck prose."""
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
          "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    normalize = lambda value: re.sub(r"\s+", " ", str(value)).strip().casefold()
    fields = {"title", "subtitle", "kicker", "footer", "value", "label", "detail",
              "body", "interpretation", "verdict", "headers", "rows", "bullets"}
    missing = []

    def expected(node, pointer="", selected=False):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"series", "categories", "deck_style"}:
                    continue
                yield from expected(value, f"{pointer}/{key}", key in fields)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from expected(value, f"{pointer}/{index}", selected)
        elif selected and node is not None:
            yield pointer, normalize(node)

    with zipfile.ZipFile(path) as package:
        for index, source in enumerate(outline["slides"], 1):
            slide = ET.fromstring(package.read(f"ppt/slides/slide{index}.xml"))
            rendered = normalize(" ".join("".join(p.itertext()) for p in slide.findall(".//a:p", ns)))
            for pointer, value in expected(source, f"/slides/{index - 1}"):
                if value and value not in rendered:
                    missing.append({"slide": index, "source_pointer": pointer, "expected": value})
            if "chart" in source:
                chart_node = slide.find(".//c:chart", ns)
                rels = ET.fromstring(package.read(f"ppt/slides/_rels/slide{index}.xml.rels"))
                target = next((rel.attrib["Target"] for rel in rels
                               if chart_node is not None and rel.attrib["Id"] == chart_node.attrib.get(f"{{{ns['r']}}}id")), None)
                if target is None:
                    missing.append({"slide": index, "source_pointer": f"/slides/{index - 1}/chart", "expected": "native editable chart"})
                    continue
                chart_path = posixpath.normpath(posixpath.join("ppt/slides", target)).lstrip("/")
                chart = ET.fromstring(package.read(chart_path))
                series = chart.findall(".//c:ser", ns)
                actual_values = [[float(v.text) for v in s.findall("./c:val//c:pt/c:v", ns)] for s in series]
                expected_values = [[float(v) for v in s["values"]] for s in source["chart"]["series"]]
                if actual_values != expected_values:
                    missing.append({"slide": index, "source_pointer": f"/slides/{index - 1}/chart/series", "expected": expected_values})
                actual_categories = [[normalize(v.text) for v in s.findall("./c:cat//c:pt/c:v", ns)] for s in series]
                expected_categories = [normalize(v) for v in source["chart"]["categories"]]
                if any(values != expected_categories for values in actual_categories):
                    missing.append({"slide": index, "source_pointer": f"/slides/{index - 1}/chart/categories", "expected": expected_categories})
    return {"passed": not missing, "missing": missing}


def editable_inventory(path: Path) -> dict:
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(path) as package:
        slide_names = [n for n in package.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        slides = [ET.fromstring(package.read(n)) for n in slide_names]
        return {"slides": len(slides), "native_tables": sum(len(s.findall(".//a:tbl", ns)) for s in slides),
                "editable_text_runs": sum(len(s.findall(".//a:t", ns)) for s in slides),
                "native_charts": sum(n.startswith("ppt/charts/chart") and n.endswith(".xml") for n in package.namelist())}


def content() -> dict:
    def slide(role: str, variant: str, title: str, **fields) -> dict:
        return {"type": "title" if role == "title" else "content", "role": role,
                "variant": variant, "title": title, "sources": ["D1"], **fields}

    return {
        "title": "The Urban Observatory",
        "slides": [
            slide("title", "title", "The Urban\nObservatory", kicker="FIELD PROGRAM / 2026",
                  subtitle="A 90-day sensor pilot with a clear scale-up decision",
                  footer="Illustrative planning data"),
            slide("evidence", "stats", "A small network can answer a focused question", facts=[
                {"value": "24", "label": "Field sensors", "detail": "Six devices in each of four contrasting zones."},
                {"value": "90 days", "label": "Observation window", "detail": "Repeat measurements through changing weather and daily activity."},
                {"value": "97%", "label": "Final-week uptime", "detail": "Device availability improved after the first maintenance cycle."},
                {"value": "$48k", "label": "Pilot ceiling", "detail": "Equipment, deployment, review, and contingency share one cap."},
            ]),
            slide("evidence", "timeline", "Four gates turn measurements into a decision", milestones=[
                {"label": "Days 1-14", "title": "Calibrate", "body": "Test all devices together before field placement."},
                {"label": "Days 15-30", "title": "Deploy", "body": "Install matched sensors across the four zones."},
                {"label": "Days 31-75", "title": "Observe", "body": "Review uptime and investigate unusual readings weekly."},
                {"label": "Days 76-90", "title": "Decide", "body": "Publish coverage gaps and the scale-up recommendation."},
            ]),
            slide("chart", "chart", "Availability improved through the pilot", chart={
                "type": "bar", "categories": ["Week 1", "Week 4", "Week 8", "Week 12"],
                "series": [{"name": "Uptime (%)", "values": [82, 89, 94, 97]}],
                "facts": [{"value": "+15 pp", "label": "Availability gain"}],
            }, interpretation="Uptime measures device availability; it does not establish measurement accuracy."),
            slide("table", "table", "The budget protects both coverage and review", table={
                "headers": ["Workstream", "Budget", "Owner", "Output"],
                "rows": [["Equipment", "$22k", "Field team", "24 calibrated sensors"],
                         ["Deployment", "$12k", "Operations", "Four matched zones"],
                         ["Analysis", "$10k", "Research", "Quality and coverage report"],
                         ["Reserve", "$4k", "Program lead", "Repairs and replacements"]],
                "column_weights": [0.23, 0.14, 0.23, 0.40],
            }, interpretation="Analysis funding is reserved before installation begins."),
            slide("comparison", "comparison-2col", "Depth now or breadth before the evidence is ready?",
                  left={"title": "Focused pilot", "bullets": ["24 sensors across four zones", "$48k budget with review funded", "Comparable measurements before expansion"]},
                  right={"title": "Immediate expansion", "bullets": ["60 sensors across ten zones", "$110k indicative budget", "More coverage; greater maintenance burden"]},
                  verdict="Run the focused pilot; expand only after the coverage and quality review."),
            slide("decision", "matrix", "Scale only when four conditions hold", quadrants=[
                {"title": "Data quality", "body": "Calibration checks remain inside the agreed tolerance across all zones."},
                {"title": "Coverage", "body": "Every zone has enough valid observations to support a fair comparison."},
                {"title": "Operations", "body": "A named team can maintain sensors and resolve recurring faults."},
                {"title": "Evidence", "body": "The final report separates measured results from assumptions and uncertainty."},
            ]),
            slide("references", "table", "The evidence remains inspectable", table={
                "table_style": "references", "headers": ["ID", "Record", "Use"],
                "rows": [["D1", "Illustrative program dataset", "All numbers are synthetic design-test inputs"],
                         ["D2", "Frozen outline.json", "Identical wording and data across eight styles"],
                         ["D3", "Build and review records", "Reproducibility and visual inspection"]],
                "column_weights": [0.08, 0.34, 0.58],
            }),
        ],
    }


def font(size: int, bold: bool = False):
    paths = [Path("/System/Library/Fonts/Supplemental") / ("Arial Bold.ttf" if bold else "Arial.ttf"),
             Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")]
    return next((ImageFont.truetype(str(p), size) for p in paths if p.exists()), ImageFont.load_default())


def contact_sheet(root: Path, name: str, numbers: tuple[int, int]) -> Path:
    width, height, gap, label = 400, 225, 18, 34
    canvas = Image.new("RGB", (4 * width + 5 * gap, 4 * (height + label) + 5 * gap), "white")
    draw = ImageDraw.Draw(canvas)
    for index, (preset, title) in enumerate(STYLES):
        x = gap + (index % 2) * (2 * width + 2 * gap)
        y = gap + (index // 2) * (height + label + gap)
        draw.text((x, y), title, font=font(21, True), fill="#202020")
        for col, number in enumerate(numbers):
            with Image.open(root / preset / "qa" / "renders" / f"slide-{number:02d}.jpg") as im:
                canvas.paste(ImageOps.fit(im.convert("RGB"), (width, height)), (x + col * (width + gap), y + label))
    path = root / f"{name}.jpg"
    canvas.save(path, quality=94, optimize=True)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--styles", nargs="*", choices=[x[0] for x in STYLES])
    parser.add_argument("--verify-rebuild", action="store_true")
    args = parser.parse_args()
    root = args.outdir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    base = content()
    (root / "content.json").write_text(json.dumps(base, indent=2) + "\n")
    evidence = {"schema_version": "readable_style_gallery/v1", "synthetic_data": True,
                "content_sha256": hashlib.sha256(json.dumps(base, sort_keys=True).encode()).hexdigest(), "decks": []}
    for preset, _title in STYLES:
        if args.styles and preset not in args.styles:
            continue
        work = root / preset
        work.mkdir(exist_ok=True)
        outline = copy.deepcopy(base)
        outline["deck_style"] = {
            "style_preset": preset, "composition_grammar": PRESET_TO_GRAMMAR[preset],
            "style_seed": "urban-observatory-v012", "header_variant": "auto",
            "footer_mode": "source-line", "footer_page_numbers": True,
            "readability_contract": {"min_title_pt": 28, "min_body_pt": 16, "min_support_pt": 13,
                                     "min_caption_pt": 9, "min_metadata_pt": 9, "min_footer_pt": 9},
        }
        if preset == "lab-report":
            outline["deck_style"]["palette_key"] = "lab_monochrome_v1"
        path = work / "outline.json"
        path.write_text(json.dumps(outline, indent=2) + "\n")
        pptx = work / "deck.pptx"
        result = subprocess.run([sys.executable, str(ROOT / "scripts/present.py"), "finalize",
                                 "--outline", str(path), "--output", str(pptx), "--qa-dir", str(work / "qa")],
                                cwd=ROOT, text=True, capture_output=True)
        (work / "build.log").write_text(result.stdout + result.stderr)
        receipt = json.loads((work / "qa/finalize_receipt.json").read_text())
        record = {"preset": preset, "passed": result.returncode == 0, "qa_counts": receipt["qa_counts"],
                  "visual_inspection_status": receipt.get("visual_inspection_status", "not_recorded"),
                  "duration_seconds": receipt["total_duration_seconds"],
                  "normalized_sha256": office_package_normalized_sha256(pptx) if pptx.exists() else None}
        if pptx.exists():
            record["editability"] = editable_inventory(pptx)
            record["source_fidelity"] = source_fidelity(pptx, outline)
            record["passed"] = record["passed"] and record["source_fidelity"]["passed"]
        if args.verify_rebuild and record["passed"]:
            rebuild = work / "rebuild.pptx"
            rerun = subprocess.run(["node", str(ROOT / "scripts/build_deck_pptxgenjs.js"),
                                    "--outline", str(path), "--output", str(rebuild), "--style-preset", preset],
                                   cwd=ROOT, text=True, capture_output=True)
            record["reproducible"] = rerun.returncode == 0 and office_package_normalized_sha256(rebuild) == record["normalized_sha256"]
            record["passed"] = record["passed"] and record["reproducible"]
            if rebuild.exists():
                rebuild.unlink()
        evidence["decks"].append(record)
        print(json.dumps(record), flush=True)
    if all((root / p / "qa/renders/slide-08.jpg").exists() for p, _ in STYLES):
        evidence["contact_sheets"] = [contact_sheet(root, name, numbers).name for name, numbers in GROUPS.items()]
    (root / "manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return 0 if all(x["passed"] for x in evidence["decks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
