#!/usr/bin/env python3
"""Build authored examples and record cold/warm pipeline evidence."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageOps, __version__ as pillow_version


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CASES = ("lab", "editorial", "operations", "luna")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(case, warm=False):
    folder = HERE / case
    outline = folder / "outline.json"
    if case == "luna" and not outline.exists():
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "decks/v012-release-proof-20260923/luna/outline.json", outline)
    command = [sys.executable, str(REPO / "scripts/present.py"), "finalize",
               "--outline", str(outline), "--output", str(folder / "deck.pptx"),
               "--qa-dir", str(folder / "qa")]
    history = sorted(folder.glob("run-*.json"))
    number = len(history) + 1
    started = time.perf_counter()
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True)
    wall = time.perf_counter() - started
    (folder / f"run-{number:02d}.log").write_text(result.stdout + result.stderr)
    receipt = read(folder / "qa/finalize_receipt.json")
    render_path = folder / "qa/renders/render_report.json"
    render = read(render_path) if render_path.exists() else {}
    record = {
        "case": case, "attempt": number, "warm_requested": warm,
        "author_model": "gpt-6-luna (retained source)" if case == "luna" else "gpt-6.1-sol",
        "command": command, "returncode": result.returncode,
        "wall_seconds": round(wall, 3), "outline_sha256": digest(outline),
        "receipt": receipt, "render_cache": render.get("cache", {}),
        "timing_scope": "pipeline only; excludes model authoring and visual review",
    }
    (folder / f"run-{number:02d}.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"{case}: attempt {number}, rc={result.returncode}, {wall:.2f}s, cache={record['render_cache'].get('status', 'not rendered')}", flush=True)
    return record


def font(size):
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def contacts():
    width, height, gap = 760, 428, 22
    labels = {"lab": "Enzyme storage", "editorial": "Evening ferry demand", "operations": "Microgrid repair"}
    for case in CASES[:3]:
        renders = sorted((HERE / case / "qa/renders").glob("slide-*.jpg"))
        rows = (len(renders) + 2) // 3
        canvas = Image.new("RGB", (3 * width + 4 * gap, 55 + rows * (height + 28 + gap)), "#f5f6f6")
        draw = ImageDraw.Draw(canvas)
        draw.text((gap, 12), labels[case], font=font(27), fill="#202528")
        for index, path in enumerate(renders):
            x = gap + (index % 3) * (width + gap)
            y = 55 + (index // 3) * (height + 28 + gap)
            with Image.open(path) as original:
                canvas.paste(ImageOps.contain(original.convert("RGB"), (width, height)), (x, y))
            draw.text((x, y + height + 5), str(index + 1), font=font(17), fill="#606a70")
        canvas.save(HERE / f"{case}_contact_sheet.jpg", quality=92, optimize=True)

    overview = Image.new("RGB", (3 * width + 4 * gap, 55 + 3 * (height + gap)), "#f5f6f6")
    draw = ImageDraw.Draw(overview)
    for column, case in enumerate(CASES[:3]):
        x = gap + column * (width + gap)
        draw.text((x, 12), labels[case], font=font(27), fill="#202528")
        slides = read(HERE / case / "outline.json")["slides"]
        chart = next(index for index, slide in enumerate(slides) if slide.get("variant") == "chart")
        for row, index in enumerate((0, chart, len(slides) - 1)):
            path = HERE / case / "qa/renders" / f"slide-{index + 1:02d}.jpg"
            with Image.open(path) as original:
                overview.paste(ImageOps.contain(original.convert("RGB"), (width, height)),
                               (x, 55 + row * (height + gap)))
    overview.save(HERE / "design_studies.jpg", quality=92, optimize=True)


def showcase():
    """Curate whole, currently approved renders without rebuilding any deck."""
    selections = (
        ("lab", 3, "Enzyme storage / evidence", "Native chart with explicit units, screening threshold and descriptive readout."),
        ("editorial", 2, "Evening ferry / sequence", "Featured moment beside two supporting events; asymmetric editorial reading order."),
        ("lab", 4, "Enzyme storage / lot ledger", "Native table exposes individual lots, means and threshold counts instead of repeating a chart."),
        ("library", 4, "Library after six / format", "A dark numerical pause: 127 of 240 prefer drop-in help, explicitly not a booking forecast."),
        ("operations", 5, "Microgrid repair / process", "Owner-labelled gates form a readable operational register, not decorative steps."),
        ("operations", 7, "Microgrid repair / decision", "Four acceptance responsibilities and a bounded release decision close the argument."),
    )
    width, height, margin, gap, label_height = 1800, 1013, 32, 32, 48
    canvas = Image.new("RGB", (2 * width + 2 * margin + gap,
                              3 * (height + label_height) + 2 * margin + 2 * gap), "#eef0f1")
    draw, label_font = ImageDraw.Draw(canvas), font(30)
    case_paths = {"library": REPO / "decks/v013-readme-library-20260930"}
    records = []
    for index, (case, number, label, reason) in enumerate(selections):
        folder = case_paths.get(case, HERE / case)
        outline, deck = folder / "outline.json", folder / "deck.pptx"
        render = folder / "qa/renders" / f"slide-{number:02d}.jpg"
        judgment_path = folder / "qa/visual_judgment.json"
        receipt_path = folder / "qa/visual_review_receipt.json"
        judgment, receipt = read(judgment_path), read(receipt_path)
        approved = {item["name"]: item["sha256"] for item in receipt["renders"]}
        source_hashes = {Path(item["path"]).name: item["sha256"] for item in
                         judgment["review_context"]["artifacts"]["source_files"]}
        if (judgment["verdict"] != "pass" or receipt["verdict"] != "pass"
                or judgment.get("findings") or receipt.get("findings")
                or digest(deck) != receipt["deck"]["sha256"]
                or digest(render) != approved.get(render.name)
                or digest(outline) != source_hashes.get(outline.name)):
            raise ValueError(f"Showcase requires current approved source/deck/render hashes: {case} slide {number}")
        x = margin + index % 2 * (width + gap)
        y = margin + index // 2 * (height + label_height + gap)
        with Image.open(render) as original:
            if original.size != (width, height):
                raise ValueError(f"Unexpected showcase render dimensions: {render}: {original.size}")
            canvas.paste(original.convert("RGB"), (x, y))
        draw.text((x, y + height + 9), label, font=label_font, fill="#42494d")
        slide = read(outline)["slides"][number - 1]
        records.append({
            "row": index // 2 + 1, "column": index % 2 + 1,
            "case": case, "slide": number, "title": slide["title"],
            "variant": slide.get("variant"), "label": label, "selection_reason": reason,
            "artifacts": {name: {"path": str(path.relative_to(REPO)), "sha256": digest(path)}
                          for name, path in (("outline", outline), ("deck", deck), ("render", render),
                                             ("visual_judgment", judgment_path), ("visual_receipt", receipt_path))},
            "review_verdict": judgment["verdict"], "reviewed_at": judgment["reviewed_at"],
        })
    output = REPO / "examples/v0.13_showcase.jpg"
    canvas.save(output, quality=95, subsampling=0, optimize=True)
    selection_manifest = {
        "schema_version": "rendered-showcase/v1", "synthetic_data": True,
        "scope": "Six approved current-runtime renders, including the unchanged 2026-09-23 library source rebuilt with v0.13; not scientific or operational claims.",
        "reproduce": ".venv/bin/python -B decks/v013-first-pass-20260929/build_evidence.py --showcase-only",
        "builder": {"path": str(Path(__file__).resolve().relative_to(REPO)), "sha256": digest(Path(__file__))},
        "output": {"path": str(output.relative_to(REPO)), "sha256": digest(output), "dimensions": list(canvas.size)},
        "layout": {"columns": 2, "rows": 3, "slide_dimensions": [width, height],
                   "margin_px": margin, "gap_px": gap, "label_height_px": label_height,
                   "crop": False, "resample": False, "label_font": label_font.getname(),
                   "label_font_px": 30, "pillow_version": pillow_version},
        "selections": records,
    }
    output.with_name("v0.13_showcase_manifest.json").write_text(json.dumps(selection_manifest, indent=2) + "\n")
    print(f"Curated six approved slides: {output}")


def manifest():
    records = []
    for case in CASES:
        runs = sorted((HERE / case).glob("run-*.json"))
        if runs:
            records.append({"case": case, "runs": [read(path) for path in runs]})
    runtime_files = ["package-lock.json", "scripts/build_deck_pptxgenjs.js",
                     "scripts/finalize_quick_deck.py", "scripts/qa_gate.py",
                     "scripts/design_rules_qa.py", "scripts/source_fidelity.py",
                     "scripts/render_slides.py", "scripts/visual_review.py",
                     "templates/pptxgenjs/slides.js",
                     "templates/pptxgenjs/space_allocation.js",
                     "templates/pptxgenjs/readable_role_layouts.js"]
    (HERE / "manifest.json").write_text(json.dumps({
        "schema_version": "first-pass-evidence/v1", "synthetic_data": True,
        "comparison_scope": "distinct authored examples and one retained Luna source; not a controlled model benchmark",
        "runtime": {
            "version": read(REPO / "package.json")["version"],
            "scope": "Current runtime snapshot only. Earlier failed attempts were recorded during integration; they do not claim this final fingerprint.",
            "files": [{"path": path, "sha256": digest(REPO / path)} for path in runtime_files],
        },
        "cases": records,
    }, indent=2) + "\n")


def package(output):
    paths = [HERE / "README.md", HERE / "build_evidence.py", HERE / "manifest.json"]
    paths.extend(HERE.glob("*.jpg"))
    for case in CASES:
        folder = HERE / case
        paths.extend(folder.glob("*.json"))
        paths.extend(folder.glob("*.md"))
        paths.extend(folder.glob("*.js"))
        paths.append(folder / "deck.pptx")
        paths.extend(folder / "qa" / name for name in (
            "finalize_receipt.json", "qa_report.json", "visual_judgment.json",
            "visual_review_receipt.json",
        ))
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            if path.is_file():
                archive.write(path, Path("v0.13-design-studies") / path.relative_to(HERE))
    print(f"Packaged release evidence: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="*", choices=CASES, default=list(CASES))
    parser.add_argument("--warm", action="store_true")
    parser.add_argument("--contacts-only", action="store_true")
    parser.add_argument("--showcase-only", action="store_true", help="Curate approved renders only; do not build decks or replace contact sheets.")
    parser.add_argument("--package", type=Path, help="Write compact source, deck and review evidence after validation.")
    args = parser.parse_args()
    if args.showcase_only:
        showcase()
        return 0
    if not args.contacts_only:
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(lambda case: build(case, args.warm), args.cases))
        manifest()
        if any(record["returncode"] for record in records):
            return 1
    if all((HERE / case / "qa/renders").exists() for case in CASES[:3]):
        contacts()
    if args.package:
        package(args.package.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
