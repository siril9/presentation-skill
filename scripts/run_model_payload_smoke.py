#!/usr/bin/env python3
"""Render the brief's exact example payloads through every advertised v2 pair."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from itertools import zip_longest
from pathlib import Path

from composition_grammar_catalog import quick_deck_agent_brief, route_composition_grammars
from preflight import _check_role_variant_alignment, _check_variant_required


ROOT = Path(__file__).resolve().parents[1]
COUNT_KEYS = (
    "overflow_count", "overlap_count", "geometry_error_count", "geometry_warning_count",
    "whitespace_warning_count", "visual_warning_count", "design_error_count", "design_warning_count",
)


def _run(*args: str, allow_findings: bool = False) -> int:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode and not (allow_findings and result.returncode == 1):
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stdout}\n{result.stderr}")
    return result.returncode


def run(outdir: Path, preset: str) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    renderer = ROOT / "templates/pptxgenjs/slides.js"
    renderer_sha = hashlib.sha256(renderer.read_bytes()).hexdigest()
    brief = quick_deck_agent_brief(
        route_composition_grammars(topic="Synthetic pilot", user_prompt="", style_preset=preset),
        slide_count=14,
        agent_profile="gpt-5.6-luna",
    )
    examples = brief["outline_contract"]["minimal_payload_examples"]
    candidate = brief["route_candidates"][0]
    slides = []
    pairs = []
    for role, variants in brief["renderer"]["role_variants"].items():
        for variant in variants:
            slide = {
                "type": "title" if role == "title" else "section" if role == "section" else "content",
                "role": role,
                "variant": variant,
                "title": f"Synthetic pilot: {role} / {variant}",
                "sources": ["S1: synthetic illustration"],
                **copy.deepcopy(examples[variant]),
            }
            assert not _check_role_variant_alignment(slide, len(slides) + 1)
            assert not _check_variant_required(slide, len(slides) + 1, outdir)
            slides.append(slide)
            pairs.append(f"{role}/{variant}")
    # Exercise every pair without making the fixture itself a run of card slides.
    groups = {
        role: [slide for slide in slides if slide["role"] == role]
        for role in brief["renderer"]["role_variants"]
    }
    middle = [items for role, items in groups.items() if role not in {"title", "section", "references"}]
    slides = [
        *groups["title"], *groups["section"],
        *(slide for batch in zip_longest(*middle) for slide in batch if slide is not None),
        *groups["references"],
    ]
    pairs = [f"{slide['role']}/{slide['variant']}" for slide in slides]
    outline = {
        "title": "Synthetic payload contract",
        "deck_style": {
            **brief["outline_contract"]["deck_style"],
            "style_preset": candidate["style_preset"],
            "composition_grammar": candidate["grammar_id"],
            "style_seed": "model-payload-smoke",
        },
        "slides": slides,
    }
    outline_path = outdir / "outline.json"
    output = outdir / "deck.pptx"
    qa_dir = outdir / "qa"
    outline_path.write_text(json.dumps(outline, indent=2) + "\n", encoding="utf-8")
    _run("node", str(ROOT / "scripts/build_deck_pptxgenjs.js"), "--outline", str(outline_path), "--output", str(output), "--style-preset", preset)
    qa_rc = _run(sys.executable, str(ROOT / "scripts/qa_gate.py"), "--input", str(output), "--outline", str(outline_path), "--outdir", str(qa_dir), "--style-preset", preset, "--allow-issues", allow_findings=True)
    access_rc = _run(sys.executable, str(ROOT / "scripts/accessibility_qa.py"), "--input", str(output), "--report", str(qa_dir / "accessibility.json"), "--min-body-pt", "16", "--min-metadata-pt", "9", "--strict", allow_findings=True)
    qa = json.loads((qa_dir / "qa_report.json").read_text())
    access = json.loads((qa_dir / "accessibility.json").read_text())
    rendered = int(qa["rendered_slide_count"]) == len(slides) and qa["render_rc"] == 0
    visual_rc = 1
    visual = {}
    if rendered:
        visual_rc = _run(sys.executable, str(ROOT / "scripts/visual_review.py"), "--input", str(output), "--outline", str(outline_path), "--renders-dir", str(qa_dir / "renders"), "--outdir", str(outdir / "visual"), "--fail-on-warnings", allow_findings=True)
        visual = json.loads((outdir / "visual/visual_review.json").read_text())
    counts = {key: int(qa[key]) for key in COUNT_KEYS}
    renderer_unchanged = renderer_sha == hashlib.sha256(renderer.read_bytes()).hexdigest()
    passed = (
        rendered and not any(counts.values()) and not int(access["finding_count"])
        and not int(visual["warning_count"]) and not qa_rc and not access_rc and not visual_rc
        and renderer_unchanged
    )
    summary = {
        "passed": passed, "style_preset": preset, "pairs": pairs,
        "slide_count": len(slides), "min_body_pt": 16, "counts": counts,
        "accessibility_findings": int(access["finding_count"]),
        "visual_review_warnings": visual.get("warning_count"),
        "rendered_slide_count": int(qa["rendered_slide_count"]),
        "render_error": qa.get("render_stdout_tail") if not rendered else None,
        "renderer_sha256": renderer_sha, "renderer_unchanged_during_run": renderer_unchanged,
        "contact_sheet": str(outdir / "visual/contact_sheet.jpg") if rendered else None,
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path)
    parser.add_argument("--style-preset", action="append")
    args = parser.parse_args()
    presets = args.style_preset or ["lab-report", "warm-terracotta"]
    if args.outdir:
        results = [run(args.outdir.resolve() / preset, preset) for preset in presets]
    else:
        with tempfile.TemporaryDirectory(prefix="presentation-model-payload-") as tmp:
            results = [run(Path(tmp) / preset, preset) for preset in presets]
    passed = all(result["passed"] for result in results)
    print(json.dumps({"passed": passed, "results": results}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
