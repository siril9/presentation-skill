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

from PIL import Image, ImageDraw, ImageFont, ImageOps


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
    parser.add_argument("--package", type=Path, help="Write compact source, deck and review evidence after validation.")
    args = parser.parse_args()
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
