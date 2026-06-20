#!/usr/bin/env python3
"""Build a visual gallery for clean header variants across presets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional render helper
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

from office_package_hash import OFFICE_PACKAGE_HASH_ALGORITHM, office_package_normalized_sha256
from style_treatment_profiles import SUPPORTED_HEADER_VARIANTS


ROOT = Path(__file__).resolve().parent.parent
SUPPORTED_VARIANTS = list(SUPPORTED_HEADER_VARIANTS)


def _command_text(cmd: list[str]) -> str:
    return " ".join(str(part) for part in cmd)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pptx_fingerprint(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if not path.exists() or not path.is_file():
        return payload
    try:
        payload["size_bytes"] = path.stat().st_size
        payload["sha256"] = _file_sha256(path)
        payload["normalized_sha256"] = office_package_normalized_sha256(path)
        payload["normalized_sha256_algorithm"] = OFFICE_PACKAGE_HASH_ALGORITHM
    except OSError as exc:
        payload["read_error"] = str(exc)
    except Exception as exc:
        payload["normalized_hash_error"] = str(exc)
    return payload


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError("Command failed:\n" + _command_text(cmd) + "\n" + result.stdout)
    if result.stdout.strip():
        print(result.stdout.strip())
    return result.stdout


def _preset_names() -> list[str]:
    script = (
        "const {listPresets}=require('./templates/pptxgenjs/presets.js'); "
        "console.log(JSON.stringify(listPresets()));"
    )
    result = subprocess.run(["node", "-e", script], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    names = json.loads(result.stdout)
    return [str(name) for name in names]


def _slide_for_variant(preset: str, variant: str, index: int) -> dict[str, Any]:
    base = {
        "type": "content",
        "header_mode": "lab-clean",
        "header_variant": variant,
        "footer_mode": "source-line",
        "footer": f"{preset} / {variant}",
        "sources": ["Synthetic gallery fixture"],
        "refs": ["Header variant QA"],
    }
    if index == 0:
        return {
            **base,
            "variant": "standard",
            "title": f"{variant}: measured report heading",
            "subtitle": "Clean header / narrative body / bottom readout",
            "body": (
                "The heading treatment stays visible while the body uses a "
                "full report structure: intro text, concise bullets, and a "
                "bottom synthesis line."
            ),
            "bullets": [
                "Title and subtitle reserve space before evidence content.",
                "Accent treatment changes while the body grid stays stable.",
                "Footer provenance remains compact and separated from content.",
            ],
            "summary_callout": "Preview decks should demonstrate clean usable layouts, not only decorative header states.",
            "summary_callout_mode": "lab-box",
        }
    if index == 1:
        return {
            **base,
            "variant": "table",
            "title": f"{variant}: editable evidence table",
            "subtitle": "Compact table / source-line footer",
            "headers": ["Metric", "Readout", "State"],
            "rows": [
                ["Samples", "96", "Pass"],
                ["Controls", "3", "Pass"],
                ["Borderline", "2", "Review"],
            ],
            "column_weights": [1.15, 0.75, 0.90],
            "caption": "Synthetic fixture values; layout only.",
        }
    if index == 2:
        return {
            **base,
            "variant": "lab-run-results",
            "title": f"{variant}: compact run dashboard",
            "subtitle": "Assay readout / interpretation strip",
            "headers": ["Readout", "Value", "Decision"],
            "rows": [
                ["Median signal", "38.4", "High"],
                ["NTC control", "1.8", "Pass"],
                ["Borderline calls", "2", "Review"],
                ["Replicate CV", "4.2%", "Pass"],
            ],
            "column_weights": [1.05, 0.65, 0.85],
            "interpretation": "The header changes without changing the evidence proof structure.",
        }
    if index == 3:
        return {
            **base,
            "variant": "cards-2",
            "title": f"{variant}: methods and evidence split",
            "subtitle": "Two cards / restrained accent rhythm",
            "cards": [
                {
                    "title": "Method Context",
                    "body": "Sample identifiers, assay conditions, and run metadata stay in structured fields.",
                    "accent": "accent_primary",
                },
                {
                    "title": "Evidence Rule",
                    "body": "Long provenance moves to references while short IDs remain in the footer.",
                    "accent": "accent_secondary",
                },
            ],
        }
    if index == 4:
        return {
            **base,
            "variant": "split",
            "title": f"{variant}: narrative plus checks",
            "subtitle": "Left explanation / right checklist",
            "body": (
                "A split slide provides enough visual structure for report "
                "decks while keeping the header treatment and source-line "
                "footer easy to inspect."
            ),
            "bullets": [
                "Use when a result needs context and review steps.",
                "Keep body text compact enough for a 12 pt floor.",
                "Carry the same source policy across similar slides.",
            ],
            "highlights": [
                "No draft markers",
                "No footer collision",
                "No manual geometry",
            ],
        }
    return {
        **base,
        "variant": "table",
        "title": f"{variant}: source and reference map",
        "subtitle": "Short footer IDs / editable final references",
        "headers": ["Footer ID", "Meaning", "Where detail lives"],
        "rows": [
            ["S1", "Primary run table", "Evidence plan"],
            ["S2", "Control summary", "Asset manifest"],
            ["R1", "Protocol reference", "References slide"],
            ["R2", "Validation memo", "References slide"],
        ],
        "column_weights": [0.60, 1.10, 1.20],
        "caption": "Footer text stays short; long references remain editable.",
    }


def _outline_for_preset(preset: str, variants: list[str]) -> dict[str, Any]:
    return {
        "title": f"{preset} header variant gallery",
        "subtitle": "Six clean heading/accent-rule treatments on actual slides",
        "deck_style": {
            "header_mode": "lab-clean",
            "header_variant": "auto",
            "header_variants": variants,
            "footer_mode": "source-line",
            "footer_page_numbers": True,
            "footer_source_label": "Sources",
            "footer_refs_label": "Refs",
        },
        "slides": [
            {
                "type": "title",
                "title": f"{preset} header variants",
                "subtitle": "Actual pptxgenjs render path / lab-clean header system",
                "chips": ["Heading", "Evidence", "Footer"],
            },
            *[_slide_for_variant(preset, variant, idx) for idx, variant in enumerate(variants)],
        ],
    }


def _write_outline(outline_path: Path, preset: str, variants: list[str]) -> None:
    outline_path.parent.mkdir(parents=True, exist_ok=True)
    outline_path.write_text(json.dumps(_outline_for_preset(preset, variants), indent=2) + "\n", encoding="utf-8")


def _rendered_content_images(preset_dir: Path, preset: str, variant_count: int) -> list[Path]:
    render_dir = preset_dir / "renders"
    paths = []
    for slide_index in range(2, 2 + variant_count):
        for ext in ("jpg", "jpeg", "png"):
            p = render_dir / f"{preset}-{slide_index}.{ext}"
            if p.exists():
                paths.append(p)
                break
            p = render_dir / f"{preset}-{slide_index:02d}.{ext}"
            if p.exists():
                paths.append(p)
                break
            p = render_dir / f"{preset}-{slide_index:03d}.{ext}"
            if p.exists():
                paths.append(p)
                break
    if len(paths) == variant_count:
        return paths
    for pattern in ("*.jpg", "*.jpeg", "*.png"):
        images = sorted(render_dir.glob(pattern))[1:1 + variant_count]
        if images:
            return images
    return []


def _make_contact_sheet(outdir: Path, presets: list[str], variants: list[str]) -> Path | None:
    if Image is None or ImageDraw is None:
        return None
    thumb_w, thumb_h = 320, 180
    label_h = 34
    row_label_w = 178
    gutter = 14
    header_h = 44
    sheet_w = row_label_w + len(variants) * thumb_w + (len(variants) + 1) * gutter
    sheet_h = header_h + len(presets) * (thumb_h + label_h + gutter) + gutter
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#F8FAFC")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default() if ImageFont else None
    for idx, variant in enumerate(variants):
        x = row_label_w + gutter + idx * (thumb_w + gutter)
        draw.text((x, 14), variant, fill="#111827", font=font)

    y = header_h
    for preset in presets:
        preset_dir = outdir / preset
        draw.text((gutter, y + 8), preset, fill="#111827", font=font)
        images = _rendered_content_images(preset_dir, preset, len(variants))
        for idx, image_path in enumerate(images[:len(variants)]):
            x = row_label_w + gutter + idx * (thumb_w + gutter)
            with Image.open(image_path) as img:
                img = img.convert("RGB")
                img.thumbnail((thumb_w, thumb_h))
                canvas = Image.new("RGB", (thumb_w, thumb_h), "#FFFFFF")
                canvas.paste(img, ((thumb_w - img.width) // 2, (thumb_h - img.height) // 2))
                sheet.paste(canvas, (x, y + label_h))
            draw.text((x, y + 8), variants[idx], fill="#334155", font=font)
        y += thumb_h + label_h + gutter

    output = outdir / "header_variant_contact_sheet.jpg"
    sheet.save(output, quality=88)
    return output


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build header variant gallery decks.")
    parser.add_argument("--outdir", default="decks/header-variant-gallery-20260617")
    parser.add_argument("--presets", nargs="*", default=[], help="Optional subset of presets")
    parser.add_argument("--variants", nargs="*", default=[], help="Optional subset of supported header variants")
    parser.add_argument("--build", action="store_true", help="Build PPTX files")
    parser.add_argument("--qa", action="store_true", help="Build missing/current PPTX files and run render-free QA")
    parser.add_argument("--render", action="store_true", help="Build missing/current PPTX files and render them to JPEG")
    parser.add_argument("--dpi", type=int, default=110)
    return parser.parse_args()


def main() -> int:
    args = _args()
    outdir = (ROOT / args.outdir).resolve() if not Path(args.outdir).is_absolute() else Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    presets = args.presets or _preset_names()
    variants: list[str] = []
    for variant in args.variants or []:
        value = str(variant).strip()
        if not value or value in variants:
            continue
        if value not in SUPPORTED_VARIANTS:
            raise SystemExit(f"Unsupported header variant for gallery: {value}")
        variants.append(value)
    if not variants:
        variants = list(SUPPORTED_VARIANTS)

    records: list[dict[str, Any]] = []
    for preset in presets:
        preset_dir = outdir / preset
        outline = preset_dir / "outline.json"
        pptx = preset_dir / f"{preset}.pptx"
        qa_report = preset_dir / "qa" / "report.json"
        render_dir = preset_dir / "renders"
        _write_outline(outline, preset, variants)
        build_cmd = [
            "node",
            "scripts/build_deck_pptxgenjs.js",
            "--outline",
            str(outline),
            "--output",
            str(pptx),
            "--style-preset",
            preset,
        ]
        build_implied = bool((args.qa or args.render) and not args.build)
        build_stdout = ""
        if args.build or args.qa or args.render:
            build_stdout = _run(build_cmd)

        qa_cmd: list[str] = []
        qa_stdout = ""
        if args.qa:
            qa_cmd = [
                sys.executable,
                "scripts/qa_gate.py",
                "--input",
                str(pptx),
                "--outdir",
                str(preset_dir / "qa"),
                "--style-preset",
                preset,
                "--strict-geometry",
                "--skip-manual-review",
                "--skip-render",
                "--fail-on-design-warnings",
                "--outline",
                str(outline),
                "--report",
                str(qa_report),
            ]
            qa_stdout = _run(qa_cmd)

        render_cmd: list[str] = []
        render_stdout = ""
        if args.render:
            render_cmd = [
                sys.executable,
                "scripts/render_slides.py",
                "--input",
                str(pptx),
                "--outdir",
                str(render_dir),
                "--dpi",
                str(args.dpi),
                "--format",
                "jpeg",
            ]
            render_stdout = _run(render_cmd)

        records.append(
            {
                "preset": preset,
                "outline": str(outline),
                "pptx": str(pptx),
                "pptx_fingerprint": _pptx_fingerprint(pptx),
                "qa_report": str(qa_report) if args.qa else "",
                "render_dir": str(render_dir) if args.render else "",
                "rendered_content_images": (
                    [
                        str(path)
                        for path in _rendered_content_images(preset_dir, preset, len(variants))
                    ]
                    if args.render
                    else []
                ),
                "build_requested": bool(args.build),
                "build_implied_by_qa_or_render": build_implied,
                "build_command": build_cmd,
                "qa_command": qa_cmd,
                "render_command": render_cmd,
                "build_stdout_tail": build_stdout[-1200:],
                "qa_stdout_tail": qa_stdout[-1200:],
                "render_stdout_tail": render_stdout[-1200:],
            }
        )

    contact = _make_contact_sheet(outdir, presets, variants) if args.render else None
    summary = {
        "outdir": str(outdir),
        "presets": presets,
        "variants": variants,
        "records": records,
        "contact_sheet": str(contact) if contact else "",
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
