#!/usr/bin/env python3
"""Build clean README comparison images from rendered native-vs-skill previews."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE_DIR = REPO / "decks/native-vs-latest-random-topics-20260623/contact_sheets"
DEFAULT_OUT_DIR = REPO / "decks/native-vs-latest-random-topics-20260623/readme_images"

CASES = [
    ("night-market-battery-swaps", "Night Market Battery Swaps"),
    ("river-watch-pocket-lab", "Pocket Labs For River Watch"),
    ("microgrid-load-forecast", "Microgrid Load Forecast"),
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
    parser = argparse.ArgumentParser(description="Build clean README-native-vs-updated comparison images.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    outputs = [
        _build_hero(source_dir, out_dir),
        _build_three_case_sheet(source_dir, out_dir),
    ]
    for path in outputs:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
