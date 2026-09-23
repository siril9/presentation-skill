#!/usr/bin/env python3
"""Render the same representative source slides in up to three candidate styles."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from taste_grammar_catalog import PRESET_TO_GRAMMAR


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clear_candidate_outputs(work: Path) -> None:
    for name in ("outline.json", "deck.pptx", "build.log"):
        (work / name).unlink(missing_ok=True)
    qa = work / "qa"
    for name in (
        "qa_report.json", "issues.json", "outline.md", "layout_lint.json",
        "visual_qa.json", "design_rules.json", "accessibility.json",
        "repair_packet.json", "finalize_receipt.json",
    ):
        (qa / name).unlink(missing_ok=True)
    for pattern in ("slide-*.jpg", "slide-*.jpeg", "slide-*.png"):
        for path in (qa / "renders").glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
    (qa / "renders" / "render_report.json").unlink(missing_ok=True)
    for name in ("visual_review.json", "visual_review.md", "contact_sheet.jpg", "visual_review_receipt.json"):
        (qa / "visual_review" / name).unlink(missing_ok=True)


def _validated_candidate_artifacts(work: Path, outline_sha256: str, expected_slides: int, returncode: int) -> tuple[dict, list[Path]]:
    if returncode != 0:
        return {}, []
    receipt_path = work / "qa" / "finalize_receipt.json"
    qa_path = work / "qa" / "qa_report.json"
    render_path = work / "qa" / "renders" / "render_report.json"
    try:
        receipt = json.loads(receipt_path.read_text())
        qa = json.loads(qa_path.read_text())
        render = json.loads(render_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}, []
    outline = (work / "outline.json").resolve()
    deck = (work / "deck.pptx").resolve()
    images = sorted((work / "qa" / "renders").glob("slide-*.jpg"))
    valid = (
        receipt.get("passed") is True
        and Path(str(receipt.get("outline", ""))).resolve() == outline
        and receipt.get("outline_sha256") == outline_sha256
        and Path(str(receipt.get("output", ""))).resolve() == deck
        and deck.is_file()
        and receipt.get("output_sha256") == _sha256(deck)
        and qa.get("render_rc") == 0
        and qa.get("expected_slide_count") == expected_slides
        and qa.get("rendered_slide_count") == expected_slides
        and render.get("status") == "complete"
        and render.get("pptx_sha256") == _sha256(deck)
        and render.get("page_count") == expected_slides
        and len(images) == expected_slides
    )
    return (receipt, images) if valid else ({}, [])


def representative_indices(slides: list[dict]) -> list[int]:
    selected = []
    for roles in ({"title"}, {"evidence", "comparison", "decision"}, {"table", "chart"}):
        candidates = [(i, s) for i, s in enumerate(slides)
                      if i not in selected and str(s.get("role") or s.get("variant") or s.get("type")) in roles]
        if candidates:
            # For data slides, preview the densest candidate rather than an easy example.
            index = max(candidates, key=lambda item: len(json.dumps(item[1])))[0] if "table" in roles else candidates[0][0]
            selected.append(index)
    selected.extend(i for i in range(len(slides)) if i not in selected)
    return sorted(selected[:3])


def candidate_outline(source: dict, preset: str, indices: list[int]) -> dict:
    if preset not in PRESET_TO_GRAMMAR:
        raise ValueError(f"Unknown preset: {preset}")
    result = copy.deepcopy(source)
    result["slides"] = [copy.deepcopy(source["slides"][i]) for i in indices]
    old = source.get("deck_style") or {}
    result["deck_style"] = {
        "style_preset": preset, "composition_grammar": PRESET_TO_GRAMMAR[preset],
        "style_seed": old.get("style_seed", "content-style-audition"),
        "footer_mode": old.get("footer_mode", "source-line"), "footer_page_numbers": True,
        "readability_contract": copy.deepcopy(old.get("readability_contract") or {
            "min_title_pt": 28, "min_body_pt": 16, "min_support_pt": 13, "min_metadata_pt": 9}),
    }
    # Source payloads stay frozen; only deck-level renderer selections are replaced.
    for key in ("renderer_role_contracts_v2", "renderer_role_systems_v1", "style_preset"):
        result.pop(key, None)
        if isinstance(result.get("metadata"), dict):
            result["metadata"].pop(key, None)
    return result


def make_sheet(paths: list[tuple[str, list[Path]]], output: Path) -> None:
    tile_w, tile_h, gap, label_h = 440, 248, 18, 34
    canvas = Image.new("RGB", (3 * tile_w + 4 * gap, len(paths) * (tile_h + label_h + gap) + gap), "white")
    draw = ImageDraw.Draw(canvas)
    font_paths = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    font = next((ImageFont.truetype(p, 21) for p in font_paths if Path(p).exists()), ImageFont.load_default())
    for row, (preset, images) in enumerate(paths):
        y = gap + row * (tile_h + label_h + gap)
        draw.text((gap, y), preset, fill="#202020", font=font)
        for col, path in enumerate(images):
            with Image.open(path) as im:
                canvas.paste(ImageOps.fit(im.convert("RGB"), (tile_w, tile_h)), (gap + col * (tile_w + gap), y + label_h))
    canvas.save(output, quality=93, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outline", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--presets", nargs="+", choices=sorted(PRESET_TO_GRAMMAR), required=True)
    args = parser.parse_args()
    presets = list(dict.fromkeys(args.presets))
    if len(presets) > 3:
        parser.error("Choose at most three candidates per audition.")
    source_path = args.outline.resolve()
    source = json.loads(source_path.read_text())
    if not isinstance(source.get("slides"), list) or not source["slides"]:
        parser.error("The outline must contain slides.")
    indices = representative_indices(source["slides"])
    root = args.outdir.resolve()
    if root == source_path:
        parser.error("--outdir must not overwrite --outline")
    root.mkdir(parents=True, exist_ok=True)
    (root / "comparison.jpg").unlink(missing_ok=True)
    (root / "report.json").unlink(missing_ok=True)
    results, renders = [], []
    for preset in presets:
        work = root / preset
        work.mkdir(exist_ok=True)
        path = work / "outline.json"
        deck_path = work / "deck.pptx"
        if source_path in {path.resolve(), deck_path.resolve()}:
            parser.error("Audition output must not overwrite the source outline.")
        _clear_candidate_outputs(work)
        path.write_text(json.dumps(candidate_outline(source, preset, indices), indent=2) + "\n")
        candidate_hash = _sha256(path)
        run = subprocess.run([sys.executable, str(ROOT / "scripts/finalize_quick_deck.py"),
                              "--outline", str(path), "--output", str(deck_path),
                              "--asset-root", str(source_path.parent), "--qa-dir", str(work / "qa")],
                             cwd=ROOT, text=True, capture_output=True)
        (work / "build.log").write_text(run.stdout + run.stderr)
        receipt, images = _validated_candidate_artifacts(work, candidate_hash, len(indices), run.returncode)
        passed = bool(receipt)
        results.append({"preset": preset, "automated_checks_passed": passed,
                        "qa_counts": receipt.get("qa_counts", {}), "log": f"{preset}/build.log"})
        if images:
            renders.append((preset, images))
    if renders:
        make_sheet(renders, root / "comparison.jpg")
    report = {"schema_version": "style_audition/v1", "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
              "source_slide_indices": indices, "source_pointers": [f"/slides/{i}" for i in indices],
              "candidates": results, "visual_selection": "pending", "contact_sheet": "comparison.jpg" if renders else None,
              "next_action": "Inspect the previews and select a style using evidence fit, readability, and visual hierarchy."}
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if all(r["automated_checks_passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
