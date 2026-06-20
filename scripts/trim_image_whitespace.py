#!/usr/bin/env python3
"""Trim near-blank borders from slide figures.

Use this from workspace figure scripts before inserting generated plots into
`scientific-figure` or `image-sidebar` slides. It removes exterior whitespace
from PNG/JPG assets while leaving the original deck source workflow intact.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageChops
except Exception as exc:  # pragma: no cover - dependency error path
    print(f"Error: Pillow is required for image trimming: {exc}", file=sys.stderr)
    raise SystemExit(1)


def _corner_background(img: Image.Image) -> tuple[int, int, int, int]:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    corners = [
        rgba.getpixel((0, 0)),
        rgba.getpixel((max(0, w - 1), 0)),
        rgba.getpixel((0, max(0, h - 1))),
        rgba.getpixel((max(0, w - 1), max(0, h - 1))),
    ]
    return tuple(sorted(values)[len(values) // 2] for values in zip(*corners))  # type: ignore[return-value]


def _content_bbox(img: Image.Image, *, tolerance: int) -> tuple[int, int, int, int] | None:
    rgba = img.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, _corner_background(rgba))
    diff = ImageChops.difference(rgba, bg)
    mask = Image.new("L", rgba.size, 0)
    for channel in diff.split():
        thresholded = channel.point(lambda value: 255 if value > tolerance else 0)
        mask = ImageChops.lighter(mask, thresholded)
    return mask.getbbox()


def _pad_bbox(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def trim_image(
    input_path: Path,
    output_path: Path,
    *,
    tolerance: int,
    padding: int,
    overwrite: bool,
) -> dict[str, Any]:
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if output_path.exists() and not overwrite and output_path.resolve() != input_path.resolve():
        raise FileExistsError(f"Output exists: {output_path}")

    with Image.open(input_path) as raw:
        img = raw.convert("RGBA")
        bbox = _content_bbox(img, tolerance=tolerance)
        if not bbox:
            if input_path.resolve() != output_path.resolve():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(input_path, output_path)
            return {
                "input": str(input_path),
                "output": str(output_path),
                "status": "unchanged",
                "original_size": list(img.size),
                "trimmed_size": list(img.size),
            }

        padded = _pad_bbox(bbox, width=img.width, height=img.height, padding=padding)
        cropped = img.crop(padded)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs: dict[str, Any] = {}
        suffix = output_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            cropped = cropped.convert("RGB")
            save_kwargs["quality"] = 95
        cropped.save(output_path, **save_kwargs)
        return {
            "input": str(input_path),
            "output": str(output_path),
            "status": "trimmed" if cropped.size != img.size else "unchanged",
            "original_size": list(img.size),
            "trimmed_size": list(cropped.size),
            "bbox": list(padded),
        }


def _output_path(input_path: Path, args: argparse.Namespace) -> Path:
    if args.in_place:
        return input_path
    name = f"{input_path.stem}{args.suffix}{input_path.suffix}"
    if args.outdir:
        return Path(args.outdir).expanduser().resolve() / name
    return input_path.with_name(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Trim near-blank borders from generated slide figures.")
    parser.add_argument("images", nargs="+", help="Input image paths")
    parser.add_argument("--outdir", help="Optional output directory")
    parser.add_argument("--suffix", default="_tight", help="Suffix for output files when not using --in-place")
    parser.add_argument("--in-place", action="store_true", help="Overwrite each input image")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--tolerance", type=int, default=12, help="Pixel difference threshold from inferred background")
    parser.add_argument("--padding", type=int, default=10, help="Pixels of padding to retain around detected content")
    args = parser.parse_args()

    if args.in_place:
        args.overwrite = True
    if not args.in_place and args.suffix == "":
        parser.error("--suffix cannot be empty unless --in-place is used")

    reports = []
    for raw in args.images:
        input_path = Path(raw).expanduser().resolve()
        output_path = _output_path(input_path, args)
        reports.append(
            trim_image(
                input_path,
                output_path,
                tolerance=max(0, args.tolerance),
                padding=max(0, args.padding),
                overwrite=args.overwrite,
            )
        )
    print(json.dumps({"images": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
