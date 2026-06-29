#!/usr/bin/env python3
"""Build clean README evidence images from rendered presentation-skill previews."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = REPO / "decks/native-vs-latest-random-topics-20260623/contact_sheets"
DEFAULT_OUT_DIR = REPO / "decks/native-vs-latest-random-topics-20260623/readme_images"
DEFAULT_GALLERY_SUMMARY = REPO / "decks/style-reference-gallery-20260620-corpus-v1/summary.json"

CASES = [
    ("night-market-battery-swaps", "Night Market Battery Swaps"),
    ("river-watch-pocket-lab", "Pocket Labs For River Watch"),
    ("microgrid-load-forecast", "Microgrid Load Forecast"),
]

VARIANT_TILE_SOURCES = [
    ("title", "Title", "bold-startup-narrative", "title"),
    ("section", "Section", "_section", "section"),
    ("cards-3", "Cards 3", "bold-startup-narrative", "cards-3"),
    ("split", "Split", "editorial-minimal", "split"),
    ("timeline", "Timeline", "charcoal-safety", "timeline"),
    ("stats", "Stats", "arctic-minimal", "stats"),
    ("kpi-hero", "KPI Hero", "bold-startup-narrative", "kpi-hero"),
    ("comparison-2col", "Comparison", "lab-report", "comparison-2col"),
    ("matrix", "Matrix", "lavender-ops", "matrix"),
    ("chart", "Chart", "data-heavy-boardroom", "chart"),
    ("lab-run-results", "Lab Results", "lab-report", "lab-run-results"),
    ("scientific-figure", "Scientific Figure", "paper-journal", "scientific-figure"),
    ("flow", "Mermaid Flow", "midnight-neon", "flow"),
]

STYLE_TILE_SOURCES = [
    ("arctic-minimal", "Arctic Minimal", "image-sidebar"),
    ("bold-startup-narrative", "Startup Narrative", "kpi-hero"),
    ("charcoal-safety", "Risk Memo", "timeline"),
    ("data-heavy-boardroom", "Board Dashboard", "chart"),
    ("editorial-minimal", "Editorial Report", "split"),
    ("executive-clinical", "Executive Clinical", "lab-run-results"),
    ("forest-research", "Forest Research", "scientific-figure"),
    ("lab-report", "Lab Report", "lab-run-results"),
    ("lavender-ops", "Lavender Ops", "flow"),
    ("midnight-neon", "Midnight Neon", "flow"),
    ("paper-journal", "Paper Journal", "scientific-figure"),
    ("sunset-investor", "Investor Reveal", "chart"),
    ("warm-terracotta", "Terracotta Case", "timeline"),
]

INK = "#111827"
MUTED = "#4b5563"
RULE = "#d8dee8"
BG = "#ffffff"


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, size: int, fill: str = INK, bold: bool = False) -> None:
    draw.text(xy, text, font=_font(size, bold=bold), fill=fill)


def _crop_pair(path: Path) -> tuple[Image.Image, Image.Image]:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    y1 = int(height * 0.278)
    y2 = int(height * 0.728)
    native = image.crop((int(width * 0.060), y1, int(width * 0.479), y2))
    updated = image.crop((int(width * 0.521), y1, int(width * 0.940), y2))
    return native, updated


def _fit(image: Image.Image, width: int) -> Image.Image:
    ratio = width / image.width
    height = round(image.height * ratio)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _paste_with_border(canvas: Image.Image, image: Image.Image, xy: tuple[int, int]) -> None:
    draw = ImageDraw.Draw(canvas)
    x, y = xy
    draw.rectangle((x - 1, y - 1, x + image.width, y + image.height), outline=RULE, width=1)
    canvas.paste(image, xy)


def _load_gallery_records(summary_path: Path) -> dict[str, dict]:
    if not summary_path.exists():
        return {}
    payload = json.loads(summary_path.read_text())
    records: dict[str, dict] = {}
    for record in payload.get("records", []):
        preset = record.get("preset")
        if preset:
            records[preset] = record
    return records


def _repo_relative_render_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.exists():
        return path
    parts = path.parts
    if "decks" in parts:
        decks_index = parts.index("decks")
        candidate = REPO.joinpath(*parts[decks_index:])
        if candidate.exists():
            return candidate
    return path


def _record_variant_image(records: dict[str, dict], preset: str, variant: str) -> Path | None:
    record = records.get(preset)
    if not record:
        return None
    variants = record.get("variant_sequence", [])
    images = record.get("rendered_slide_images", [])
    for index, current_variant in enumerate(variants):
        if current_variant == variant and index < len(images):
            path = _repo_relative_render_path(str(images[index]))
            if path.exists():
                return path
    return None


def _run_section_render(out_dir: Path) -> Path | None:
    if not shutil.which("node") or not shutil.which("soffice"):
        return None
    section_image = out_dir / "readme_section_example.jpg"
    with tempfile.TemporaryDirectory(prefix="presentation-skill-section-") as tmp:
        tmp_path = Path(tmp)
        pptx_path = tmp_path / "section_example.pptx"
        render_dir = tmp_path / "renders"
        build_cmd = [
            "node",
            str(REPO / "scripts/build_deck_pptxgenjs.js"),
            "--outline",
            str(REPO / "examples/outline.json"),
            "--output",
            str(pptx_path),
            "--style-preset",
            "lab-report",
        ]
        render_cmd = [
            "python3",
            str(REPO / "scripts/render_slides.py"),
            "--input",
            str(pptx_path),
            "--outdir",
            str(render_dir),
            "--format",
            "jpeg",
        ]
        subprocess.run(build_cmd, cwd=REPO, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(render_cmd, cwd=REPO, check=True, stdout=subprocess.DEVNULL)
        rendered = render_dir / "slide-02.jpg"
        if rendered.exists():
            section_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(rendered, section_image)
            return section_image
    return None


def _section_image(out_dir: Path, *, render_section: bool) -> Path | None:
    path = out_dir / "readme_section_example.jpg"
    if render_section or not path.exists():
        try:
            rendered = _run_section_render(out_dir)
            if rendered:
                return rendered
        except (OSError, subprocess.CalledProcessError):
            pass
    return path if path.exists() else None


def _tile_from_path(path: Path | None, size: tuple[int, int], label: str) -> Image.Image:
    if path and path.exists():
        image = Image.open(path).convert("RGB")
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    width, height = size
    tile = Image.new("RGB", size, "#eef2f7")
    draw = ImageDraw.Draw(tile)
    draw.rectangle((0, 0, width - 1, height - 1), outline="#cbd5e1", width=2)
    draw.rectangle((24, 24, width - 24, 38), fill="#0f172a")
    draw.rectangle((24, 64, width // 2, 78), fill="#94a3b8")
    draw.rectangle((24, 100, width - 44, 110), fill="#cbd5e1")
    draw.rectangle((24, 128, width - 88, 138), fill="#cbd5e1")
    _text(draw, (24, height - 34), label, size=18, fill="#475569", bold=True)
    return tile


def _captioned_tile(
    canvas: Image.Image,
    image: Image.Image,
    xy: tuple[int, int],
    *,
    title: str,
    subtitle: str,
    tile_w: int,
    tile_h: int,
) -> None:
    draw = ImageDraw.Draw(canvas)
    x, y = xy
    _text(draw, (x, y), title, size=15, bold=True)
    _text(draw, (x, y + 19), subtitle, size=11, fill=MUTED)
    image_y = y + 42
    draw.rectangle((x - 1, image_y - 1, x + tile_w, image_y + tile_h), outline=RULE, width=1)
    canvas.paste(image, (x, image_y))


def _build_tile_board(
    *,
    title: str,
    subtitle: str,
    tiles: list[tuple[str, str, Image.Image]],
    out_path: Path,
    columns: int = 5,
) -> Path:
    tile_w = 280
    tile_h = 158
    left = 48
    top = 34
    header_h = 84
    gap_x = 24
    gap_y = 30
    label_h = 40
    rows = (len(tiles) + columns - 1) // columns
    content_w = columns * tile_w + (columns - 1) * gap_x
    width = left * 2 + content_w
    height = top + header_h + rows * (label_h + tile_h) + (rows - 1) * gap_y + 44
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    _text(draw, (left, top), title, size=30, bold=True)
    _text(draw, (left, top + 40), subtitle, size=16, fill=MUTED)

    y = top + header_h
    for index, (label, source, image) in enumerate(tiles):
        row = index // columns
        col = index % columns
        row_start = row * columns
        row_count = min(columns, len(tiles) - row_start)
        row_w = row_count * tile_w + max(0, row_count - 1) * gap_x
        row_left = left + (content_w - row_w) // 2
        x = row_left + col * (tile_w + gap_x)
        yy = y + row * (label_h + tile_h + gap_y)
        _captioned_tile(canvas, image, (x, yy), title=label, subtitle=source, tile_w=tile_w, tile_h=tile_h)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)
    return out_path


def _build_variant_proof(summary_path: Path, out_dir: Path, *, render_section: bool) -> Path:
    out_path = out_dir / "presentation_skill_variant_proof.png"
    if not summary_path.exists() and out_path.exists():
        return out_path
    records = _load_gallery_records(summary_path)
    section = _section_image(out_dir, render_section=render_section)
    tiles: list[tuple[str, str, Image.Image]] = []
    for variant, label, preset, source_variant in VARIANT_TILE_SOURCES:
        path = section if preset == "_section" else _record_variant_image(records, preset, source_variant)
        source = "rendered example" if preset == "_section" else preset.replace("-", " ")
        tiles.append((label, source, _tile_from_path(path, (280, 158), variant)))
    return _build_tile_board(
        title="13 variants, not one bullet-list template",
        subtitle="Rendered samples across title, section, data, figure, flow, KPI, matrix, and comparison layouts.",
        tiles=tiles,
        out_path=out_path,
    )


def _build_style_family_proof(summary_path: Path, out_dir: Path) -> Path:
    out_path = out_dir / "presentation_skill_style_family_proof.png"
    if not summary_path.exists() and out_path.exists():
        return out_path
    records = _load_gallery_records(summary_path)
    tiles: list[tuple[str, str, Image.Image]] = []
    for preset, label, variant in STYLE_TILE_SOURCES:
        path = _record_variant_image(records, preset, variant)
        tiles.append((label, variant, _tile_from_path(path, (280, 158), preset)))
    return _build_tile_board(
        title="Presets change structure, not only color",
        subtitle="One rendered sample per style family, selected from the style-reference gallery.",
        tiles=tiles,
        out_path=out_path,
    )


def _build_three_case_sheet(source_dir: Path, out_dir: Path) -> Path:
    slide_w = 520
    gutter = 44
    left = 56
    top = 34
    title_h = 128
    row_gap = 58
    label_h = 32

    pairs: list[tuple[str, Image.Image, Image.Image]] = []
    for slug, title in CASES:
        src = source_dir / f"{slug}_codex_native_vs_latest_preview.png"
        native, updated = _crop_pair(src)
        pairs.append((title, _fit(native, slide_w), _fit(updated, slide_w)))

    row_h = max(native.height for _, native, _ in pairs) + label_h + 34
    width = left * 2 + slide_w * 2 + gutter
    height = top + title_h + len(pairs) * row_h + (len(pairs) - 1) * row_gap + 36
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    _text(draw, (left, top), "Codex Native vs Updated presentation-skill", size=31, bold=True)
    _text(draw, (left, top + 43), "Same topics, generated two ways.", size=18, fill=MUTED)
    col_y = top + title_h
    _text(draw, (left, col_y), "Codex native", size=21, bold=True)
    _text(draw, (left + slide_w + gutter, col_y), "Updated skill", size=21, bold=True)

    y = col_y + label_h + 32
    for title, native, updated in pairs:
        _text(draw, (left, y - 24), title, size=16, fill=MUTED, bold=True)
        _paste_with_border(canvas, native, (left, y))
        _paste_with_border(canvas, updated, (left + slide_w + gutter, y))
        y += row_h + row_gap

    out = out_dir / "codex_native_vs_updated_clean_three_topics.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def _build_hero(source_dir: Path, out_dir: Path) -> Path:
    slug, title = CASES[0]
    src = source_dir / f"{slug}_codex_native_vs_latest_preview.png"
    native, updated = _crop_pair(src)
    slide_w = 560
    native = _fit(native, slide_w)
    updated = _fit(updated, slide_w)
    left = 56
    gutter = 44
    top = 34
    width = left * 2 + slide_w * 2 + gutter
    height = top + 124 + native.height + 56
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    _text(draw, (left, top), title, size=30, bold=True)
    _text(draw, (left, top + 42), "Same topic. Left: Codex native. Right: updated presentation-skill.", size=18, fill=MUTED)
    y = top + 92
    _text(draw, (left, y), "Codex native", size=21, bold=True)
    _text(draw, (left + slide_w + gutter, y), "Updated skill", size=21, bold=True)
    _paste_with_border(canvas, native, (left, y + 32))
    _paste_with_border(canvas, updated, (left + slide_w + gutter, y + 32))

    out = out_dir / "codex_native_vs_updated_clean_hero.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build clean README evidence images.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--gallery-summary", default=str(DEFAULT_GALLERY_SUMMARY))
    parser.add_argument(
        "--render-section",
        action="store_true",
        help="Refresh the section-divider thumbnail from examples/outline.json.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    gallery_summary = Path(args.gallery_summary).expanduser().resolve()
    outputs = [
        _build_hero(source_dir, out_dir),
        _build_three_case_sheet(source_dir, out_dir),
        _build_variant_proof(gallery_summary, out_dir, render_section=args.render_section),
        _build_style_family_proof(gallery_summary, out_dir),
    ]
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
