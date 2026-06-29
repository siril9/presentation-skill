#!/usr/bin/env python3
"""Build random-topic baseline vs large-corpus-guided comparison decks."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont, ImageStat
except Exception:  # pragma: no cover - visual artifact dependency
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]

from design_catalog_selector import (
    DESIGN_CATALOG_VERSION,
    RELEASE_EVIDENCE_DIR,
    RELEASE_VERSION,
    RANDOM_SEED,
    comparison_topics,
    design_catalog_summary,
)
from large_style_corpus import compact_large_style_corpus_context
from style_atom_router import deterministic_composition
from apply_atom_composition import apply_composition


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTDIR = ROOT / RELEASE_EVIDENCE_DIR
TOPICS: list[dict[str, Any]] = comparison_topics()
CORPUS_BUILDER_VARIANTS = {
    "image-sidebar",
    "lab-run-results",
    "table",
    "chart",
    "comparison-2col",
    "stats",
    "kpi-hero",
}


def _slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-")


def _font(size: int, *, bold: bool = False) -> Any:
    if ImageFont is None:
        return None
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fingerprint(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def _source_fingerprint(path: Path) -> dict[str, Any]:
    fingerprint = _fingerprint(path)
    return {"source_sha256": fingerprint["sha256"], "source_bytes": fingerprint["bytes"]}


def _run(cmd: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        print(result.stdout, end="")
    return {
        "command": cmd,
        "returncode": result.returncode,
        "stdout_tail": (result.stdout or "")[-2400:],
    }


def _run_checked(cmd: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    entry = _run(cmd, cwd=cwd)
    if entry["returncode"] != 0:
        raise RuntimeError(f"command failed ({entry['returncode']}): {' '.join(cmd)}")
    return entry


def _draw_topic_figure(topic: dict[str, Any], outpath: Path, *, mode: str) -> None:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required to generate comparison figures")
    outpath.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 720
    bg, accent, tint = topic["palette"]
    image = Image.new("RGB", (width, height), bg if mode == "corpus" else "#F7FAFC")
    draw = ImageDraw.Draw(image)
    draw.rectangle((42, 42, width - 42, height - 42), fill="#FFFFFF", outline="#BFC9D4", width=3)
    draw.text((76, 72), f"{topic['title']} / synthetic evidence panel", fill="#17202A", font=_font(38, bold=True))
    draw.text((78, 122), f"{mode} deck asset · deterministic local figure", fill="#53616F", font=_font(20))

    kind = topic["figure_kind"]
    if kind == "river":
        cells = [
            [0.20, 0.42, 0.58, 0.35, 0.22],
            [0.28, 0.51, 0.72, 0.48, 0.30],
            [0.15, 0.33, 0.44, 0.40, 0.19],
            [0.10, 0.24, 0.38, 0.31, 0.16],
        ]
        x0, y0 = 92, 190
        cw, ch = 116, 82
        for r, row in enumerate(cells):
            for c, val in enumerate(row):
                intensity = int(245 - val * 120)
                color = (intensity, 245, 247)
                draw.rectangle((x0 + c * cw, y0 + r * ch, x0 + (c + 1) * cw - 6, y0 + (r + 1) * ch - 6), fill=color, outline=accent, width=2)
                draw.text((x0 + c * cw + 36, y0 + r * ch + 25), f"{val:.2f}", fill="#12343B", font=_font(18, bold=True))
        draw.text((92, 540), "Panel A: field readout heatmap", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 500), (805, 438), (890, 460), (975, 312), (1060, 358)]
    elif kind == "battery":
        x0, y0 = 100, 210
        for i, level in enumerate([0.85, 0.62, 0.38, 0.78]):
            x = x0 + i * 142
            draw.rounded_rectangle((x, y0, x + 82, y0 + 245), radius=18, outline=accent, width=5, fill="#F8FBFF")
            draw.rectangle((x + 18, y0 + 225 - int(190 * level), x + 64, y0 + 225), fill=tint, outline=accent)
            draw.text((x + 12, y0 + 265), f"Dock {i+1}", fill="#24313D", font=_font(18, bold=True))
        draw.text((98, 540), "Panel A: dock charge state", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 485), (805, 402), (890, 360), (975, 288), (1060, 254)]
    elif kind == "forest":
        x0, y0 = 95, 190
        for i, canopy in enumerate([0.18, 0.35, 0.62, 0.75]):
            x = x0 + i * 138
            draw.rectangle((x, y0 + 210, x + 86, y0 + 244), fill="#8C6B4A")
            radius = 34 + int(canopy * 48)
            center_x = x + 43
            center_y = y0 + 180 - int(canopy * 70)
            draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=tint, outline=accent, width=4)
            draw.text((x - 2, y0 + 270), f"B{i+1}", fill="#24313D", font=_font(18, bold=True))
        draw.text((95, 540), "Panel A: canopy density bands", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 480), (805, 430), (890, 365), (975, 320), (1060, 292)]
    elif kind == "risk":
        labels = ["TEMP", "POWER", "PROBE", "COURIER"]
        fills = ["#FCA5A5", "#FCD34D", "#93C5FD", "#D1D5DB"]
        x0, y0 = 92, 205
        for i, label in enumerate(labels):
            x = x0 + (i % 2) * 245
            y = y0 + (i // 2) * 132
            draw.rectangle((x, y, x + 190, y + 92), fill=fills[i], outline=accent, width=4)
            draw.text((x + 22, y + 22), label, fill="#111827", font=_font(24, bold=True))
            draw.text((x + 22, y + 56), "owner + next action", fill="#374151", font=_font(16))
        draw.text((92, 540), "Panel A: incident risk board", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 472), (805, 380), (890, 430), (975, 292), (1060, 320)]
    elif kind == "dashboard":
        x0, y0 = 92, 205
        for i, value in enumerate([31, 46, 58, 49]):
            x = x0 + i * 122
            draw.rectangle((x, y0 + 230 - value * 3, x + 70, y0 + 230), fill=tint, outline=accent, width=3)
            draw.text((x, y0 + 248), f"{value}kW", fill="#24313D", font=_font(17, bold=True))
        draw.line((90, y0 + 230, 585, y0 + 230), fill="#8995A1", width=2)
        draw.text((92, 540), "Panel A: forecast load bars", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 470), (805, 398), (890, 335), (975, 362), (1060, 285)]
    elif kind == "clinical":
        x0, y0 = 92, 205
        for i, value in enumerate([120, 96, 24, 8]):
            x = x0 + i * 115
            w = max(42, int(value * 3.4))
            draw.rounded_rectangle((x, y0 + i * 26, x + w, y0 + 52 + i * 26), radius=8, fill=tint, outline=accent, width=3)
            draw.text((x + 16, y0 + 14 + i * 26), str(value), fill="#24313D", font=_font(20, bold=True))
        draw.text((92, 540), "Panel A: cohort funnel", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 450), (805, 408), (890, 376), (975, 352), (1060, 330)]
    elif kind == "investor":
        draw.text((95, 210), "Pilot traction", fill="#24313D", font=_font(25, bold=True))
        bars = [3, 9, 17, 28]
        for i, value in enumerate(bars):
            x = 115 + i * 118
            draw.rectangle((x, 480 - value * 8, x + 70, 480), fill=tint, outline=accent, width=3)
            draw.text((x + 8, 500), f"{value}", fill="#24313D", font=_font(18, bold=True))
        draw.text((92, 540), "Panel A: port expansion path", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 482), (805, 430), (890, 352), (975, 308), (1060, 245)]
    else:
        draw.rectangle((92, 205, 590, 470), fill="#FBF7ED", outline=accent, width=4)
        draw.line((125, 260, 550, 260), fill="#D7C39A", width=4)
        draw.line((125, 325, 550, 325), fill="#D7C39A", width=4)
        draw.line((125, 390, 550, 390), fill="#D7C39A", width=4)
        draw.text((122, 220), "Object note", fill="#24313D", font=_font(25, bold=True))
        draw.text((122, 282), "measurement", fill="#24313D", font=_font(19))
        draw.text((122, 347), "conservation", fill="#24313D", font=_font(19))
        draw.text((92, 540), "Panel A: artifact measurement note", fill="#24313D", font=_font(20, bold=True))
        points = [(720, 450), (805, 430), (890, 405), (975, 380), (1060, 360)]

    draw.line((690, 180, 690, 560), fill="#CED6DE", width=3)
    draw.text((720, 205), "Panel B: pilot signal trend", fill="#24313D", font=_font(24, bold=True))
    draw.line((720, 500, 1085, 500), fill="#8995A1", width=2)
    draw.line((720, 245, 720, 500), fill="#8995A1", width=2)
    for p0, p1 in zip(points, points[1:]):
        draw.line((*p0, *p1), fill=accent, width=8)
    for x, y in points:
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=tint, outline=accent, width=3)
    draw.text((720, 535), "Synthetic data for visual QA only", fill="#596574", font=_font(18))
    image.save(outpath)


def _topic_atom_prompt(topic: dict[str, Any]) -> str:
    return " ".join(
        [
            str(topic.get("prompt") or ""),
            str(topic.get("topic_type") or ""),
            " ".join(str(item) for item in topic.get("tags", [])),
            " ".join(str(item) for item in topic.get("chart_categories", [])),
        ]
    )


def _corpus_atom_application(topic: dict[str, Any]) -> dict[str, Any]:
    composition = deterministic_composition(
        target_family=topic["corpus_family"],
        slide_count=topic.get("slide_count_target", 10),
        topic=topic["title"],
        user_prompt=_topic_atom_prompt(topic),
    )
    applied = apply_composition(composition)
    applied["composition"] = composition
    return applied


def _corpus_variant_plan(topic: dict[str, Any], applied: dict[str, Any]) -> dict[str, str]:
    preferred = [
        str(item)
        for item in applied.get("preferred_variants", [])
        if str(item) in CORPUS_BUILDER_VARIANTS
    ]
    family = topic["corpus_family"]
    dashboard_variant = (
        "kpi-hero"
        if "kpi-hero" in preferred
        and family in {"bold-startup-narrative", "midnight-neon", "sunset-investor"}
        else "stats" if "stats" in preferred else "chart"
    )
    return {
        "s2": "image-sidebar",
        "s3": "lab-run-results" if "lab-run-results" in preferred else "table",
        "s4": "chart" if "chart" in preferred else dashboard_variant,
        "s5": "comparison-2col",
        "s6": dashboard_variant if dashboard_variant in {"kpi-hero", "stats"} else "table",
    }


def _base_deck_style(
    topic: dict[str, Any],
    *,
    mode: str,
    applied: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if mode == "baseline":
        return {
            "visual_density": "medium",
            "style_seed": f"{topic['slug']}-baseline",
            "footer_page_numbers": True,
        }

    # Corpus arm: pull the deck_style from the LEGO atom composer rather
    # than a hardcoded per-family map. The composer queries the token atlas
    # built from all 2,183 enriched records and returns atoms ranked by
    # family-specific frequency. This is what makes "corpus changes slide
    # grammar" a real claim instead of scaffolding.
    if applied is None:
        applied = _corpus_atom_application(topic)
    deck_style = dict(applied["deck_style"])
    deck_style.update(
        {
            "style_seed": f"{topic['slug']}-large-corpus",
            "header_variant": "auto",
            "footer_page_numbers": True,
            "figure_table_treatment": "figure-first",
            "summary_callout_mode": (
                "lab-box" if topic["corpus_family"] == "lab-report" else "default"
            ),
        }
    )
    deck_style.setdefault("visual_density", "medium")
    return deck_style


def _baseline_outline(topic: dict[str, Any], figure_path: str) -> dict[str, Any]:
    return {
        "title": topic["title"],
        "subtitle": topic["subtitle"],
        "deck_style": _base_deck_style(topic, mode="baseline"),
        "slides": [
            {
                "slide_id": "s1",
                "type": "title",
                "title": topic["title"],
                "subtitle": topic["subtitle"],
            },
            {
                "slide_id": "s2",
                "type": "content",
                "variant": "comparison-2col",
                "title": "Baseline framing",
                "subtitle": "Useful, but mostly generic structure",
                "left": {
                    "title": "Current readout",
                    "body": [
                        f"{topic['topic_type'].title()} needs a clearer repeatable evidence view.",
                        "Operators need a short path from observation to next action.",
                    ],
                },
                "right": {
                    "title": "Design gap",
                    "body": [
                        "Status, caveat, and follow-up should stay visible together.",
                        "The corpus-guided deck tests a more specific content grammar.",
                    ],
                },
                "verdict": "Baseline remains useful but intentionally generic.",
                "sources": ["Synthetic scenario for comparison"],
            },
            {
                "slide_id": "s3",
                "type": "content",
                "variant": "chart",
                "slide_intent": "evidence",
                "visual_intent": "data",
                "title": "Simple pilot readout",
                "subtitle": "Single chart plus compact facts",
                "chart": {
                    "type": "bar",
                    "title": "Illustrative pilot metrics",
                    "categories": topic["chart_categories"],
                    "series": [{"name": "Index", "values": topic["chart_values"]}],
                    "options": {"catAxisLabelFontSize": 9, "valAxisLabelFontSize": 9},
                    "facts": [
                        {"value": str(max(topic["chart_values"])), "label": "highest index"},
                        {"value": str(min(topic["chart_values"])), "label": "lowest index"},
                    ],
                },
                "sources": ["Synthetic pilot table"],
            },
            {
                "slide_id": "s4",
                "type": "content",
                "variant": "comparison-2col",
                "title": "Before and after model",
                "left": {"title": topic["left_title"], "body": topic["left_body"]},
                "right": {"title": topic["right_title"], "body": topic["right_body"]},
                "verdict": "Move from reactive monitoring to a visible operating loop.",
                "sources": ["Synthetic comparison brief"],
            },
            {
                "slide_id": "s5",
                "type": "content",
                "variant": "image-sidebar",
                "title": "One visual anchor improves the baseline",
                "assets": {"hero_image": figure_path},
                "caption": "Locally generated synthetic evidence panel.",
                "sidebar_sections": [
                    {"title": "Readout", "body": "Show the main signal as a figure, not only as prose."},
                    {"title": "Caveat", "body": "Numbers are illustrative; deck exists for design comparison."},
                    {"title": "Next", "body": "Use the corpus-guided version to vary content grammar."},
                ],
                "sources": ["Generated locally from deterministic synthetic data"],
            },
        ],
    }


def _metric_facts(topic: dict[str, Any]) -> list[dict[str, str]]:
    values = [int(v) for v in topic.get("chart_values", [])]
    labels = [str(v) for v in topic.get("chart_categories", [])]
    if not values or not labels:
        return []
    high_i = max(range(len(values)), key=lambda idx: values[idx])
    low_i = min(range(len(values)), key=lambda idx: values[idx])
    return [
        {"value": str(values[high_i]), "label": labels[high_i], "detail": "Highest synthetic readout", "accent": "accent_primary"},
        {"value": str(values[low_i]), "label": labels[low_i], "detail": "Lowest synthetic readout", "accent": "accent_secondary"},
        {"value": str(len(values)), "label": "tracked nodes", "detail": "Compact comparison set", "accent": "accent_primary"},
    ]


def _dashboard_slide(topic: dict[str, Any], *, variant: str, slide_id: str = "s6") -> dict[str, Any]:
    facts = _metric_facts(topic)
    if variant == "table":
        return {
            "slide_id": slide_id,
            "type": "content",
            "variant": "table",
            "treatment_key": "decision",
            "slide_intent": "decision",
            "title": "Decision row",
            "subtitle": "Close with action, owner, and caveat instead of a generic recap",
            "headers": ["Choice", "Scope", "Condition", "Call"],
            "rows": topic["decision_rows"],
            "caption": "Synthetic decision ledger for reproducible deck comparison.",
            "sources": ["Synthetic decision ledger"],
            "refs": ["LC-v1"],
        }
    if variant == "kpi-hero" and facts:
        return {
            "slide_id": slide_id,
            "type": "content",
            "variant": "kpi-hero",
            "treatment_key": "decision",
            "slide_intent": "decision",
            "title": "One number to carry forward",
            "subtitle": "Use the strongest signal as the close, not another table",
            "value": facts[0]["value"],
            "label": facts[0]["label"],
            "context": "Synthetic comparison metric; used to test whether corpus grammar can end on a focused decision moment.",
            "sources": ["Synthetic decision metric"],
            "refs": ["LC-v1"],
        }
    return {
        "slide_id": slide_id,
        "type": "content",
        "variant": "stats",
        "treatment_key": "decision",
        "slide_intent": "decision",
        "title": "Decision readout",
        "subtitle": "Close with a compact metric strip and a next action",
        "facts": facts,
        "bullets": [
            "Promote the strongest signal into the next pilot gate.",
            "Keep caveats beside the metric instead of burying them in prose.",
        ],
        "sources": ["Synthetic decision ledger"],
        "refs": ["LC-v1"],
    }


def _corpus_outline(
    topic: dict[str, Any],
    figure_path: str,
    corpus_context: dict[str, Any],
    applied: dict[str, Any],
) -> dict[str, Any]:
    variant_plan = _corpus_variant_plan(topic, applied)
    return {
        "title": topic["title"],
        "subtitle": f"Corpus-guided treatment: {topic['corpus_family']}",
        "deck_style": _base_deck_style(topic, mode="corpus", applied=applied),
        "large_corpus_context": {
            "catalog_version": corpus_context.get("catalog_version"),
            "selected_family": topic["corpus_family"],
            "record_count": (corpus_context.get("summary") or {}).get("record_count"),
            "borrowed_treatments": topic["tags"],
            "safety": "Descriptor-only; no source deck screenshots, logos, copied text, or geometry.",
        },
        "slides": [
            {
                "slide_id": "s1",
                "type": "title",
                "title": topic["title"],
                "subtitle": f"{topic['corpus_family']} corpus-guided grammar",
            },
            {
                "slide_id": "s2",
                "type": "content",
                "variant": variant_plan["s2"],
                "treatment_key": "figure",
                "slide_intent": "evidence",
                "visual_intent": "hero",
                "title": "Evidence object owns the slide",
                "subtitle": "Large-corpus cue: " + ", ".join(topic["tags"][:3]),
                "assets": {"hero_image": figure_path},
                "caption": "Synthetic local figure; included to test figure-first slide grammar.",
                "sidebar_sections": [
                    {"title": "Pattern", "body": f"Borrowed treatment labels: {', '.join(topic['tags'][:2])}."},
                    {"title": "Readout", "body": "Primary visual evidence stays larger than the explanation rail."},
                    {"title": "Trace", "body": "Caption and source footer remain visible for auditability."},
                ],
                "sources": ["Large corpus descriptor route", "Generated synthetic figure"],
                "refs": ["LC-v1"],
            },
            {
                "slide_id": "s3",
                "type": "content",
                "variant": variant_plan["s3"],
                "treatment_key": "table",
                "slide_intent": "evidence",
                "visual_intent": "data",
                "title": "Structured result ledger",
                "subtitle": "A table-first slide changes the body grammar",
                "tables": [
                    {
                        "title": "Pilot rows",
                        "headers": topic["table_headers"],
                        "rows": topic["table_rows"],
                        "caption": "Synthetic rows for slide-layout comparison.",
                    }
                ],
                "headers": topic["table_headers"],
                "rows": topic["table_rows"],
                "caption": "Synthetic rows for slide-layout comparison.",
                "interpretation": "Status and caveat scan as evidence, not decoration.",
                "sources": ["Synthetic pilot ledger"],
                "refs": ["LC-v1"],
            },
            {
                "slide_id": "s4",
                "type": "content",
                "variant": variant_plan["s4"],
                "treatment_key": "chart",
                "slide_intent": "evidence",
                "visual_intent": "data",
                "title": "Metric story with a larger plot",
                "subtitle": "Same metrics, less label clutter",
                "chart": {
                    "type": "bar",
                    "title": "Illustrative pilot metrics",
                    "categories": topic["chart_categories"],
                    "series": [{"name": "Index", "values": topic["chart_values"]}],
                    "options": {"catAxisLabelFontSize": 9, "valAxisLabelFontSize": 9},
                },
                "sources": ["Synthetic pilot metrics"],
                "refs": ["LC-v1"],
            } if variant_plan["s4"] == "chart" else _dashboard_slide(topic, variant=variant_plan["s4"], slide_id="s4"),
            {
                "slide_id": "s5",
                "type": "content",
                "variant": "comparison-2col",
                "treatment_key": "comparison",
                "title": "Operating model comparison",
                "left": {"title": topic["left_title"], "body": topic["left_body"]},
                "right": {"title": topic["right_title"], "body": topic["right_body"]},
                "verdict": "Corpus-guided layout keeps the decision logic attached to the evidence.",
                "sources": ["Synthetic comparison brief"],
                "refs": ["LC-v1"],
            },
            _dashboard_slide(topic, variant=variant_plan["s6"]),
        ],
    }


def _design_brief(
    topic: dict[str, Any],
    *,
    mode: str,
    preset: str,
    corpus_context: dict[str, Any] | None,
    generated_data: dict[str, Any] | None = None,
    atom_application: dict[str, Any] | None = None,
) -> dict[str, Any]:
    builder_script = str((ROOT / "scripts" / "build_random_topic_comparison_decks.py").resolve())
    generated_data = generated_data or {}
    brief: dict[str, Any] = {
        "topic": topic["title"],
        "content_maturity": "technical/educational",
        "audience_posture": "coworkers/operators",
        "emotional_register": "trustworthy",
        "format_promise": f"{mode} comparison deck for judging slide grammar and style distinctiveness.",
        "anti_format": ["text-only content slides", "repeated title plus three identical cards", "thin decorative title rules"],
        "design_dna": topic["dna"],
        "user_intake": {
            "audience_context": "Internal skill-quality review",
            "target_outcome": "Compare baseline vs large-corpus-guided deck structure on the same random topic",
            "style_direction": "Use best judgment; keep sources synthetic and publish-safe",
            "density": "balanced",
            "source_policy": "synthetic evidence only; cite as local/generated",
            "answered_by": "best_judgment",
        },
        "style_system": {
            "style_preset": preset,
            "style_seed": f"{topic['slug']}-{mode}",
            "design_catalog_selection": topic.get("design_catalog_selection"),
        },
        "readability_contract": {
            "min_title_pt": 24,
            "min_body_pt": 12.0,
            "min_caption_pt": 7.5,
            "chart_label_min_pt": 7.0,
            "min_chart_label_pt": 7.0,
            "footer_reserved_inches": 0.28,
            "max_title_lines": 2,
            "max_slide_text_lines": 8,
            "max_slide_words": 92,
            "max_slide_chars": 650,
            "table_density_rule": "Keep editable tables compact; split rows or move explanation to captions.",
            "whitespace_rule": "Use variants that fit the evidence object and avoid stranded empty regions.",
            "figure_crop_rule": "Use generated slide-ready figures with tight exterior whitespace.",
        },
        "title_page_concept": {
            "chosen_archetype": "topic-specific opener",
            "dominant_element": topic["title"],
            "supporting_element": f"{mode} comparison label",
            "why_this_could_only_be_this_deck": f"It names the {topic['topic_type']} scenario and comparison mode.",
        },
        "structure_strategy": {
            "primary_scaffold": "short comparison deck",
            "repeated_elements": ["stable slide IDs", "compact source footer", "evidence-first body slides"],
            "allowed_variations": ["chart", "table", "image-sidebar", "comparison-2col"],
            "container_policy": "Use containers for evidence grouping only.",
            "rhythm_break_plan": "Corpus mode gives the primary visual more space and ends with a decision row.",
        },
        "analysis_artifact_plan": {
            "candidate_data_files": [generated_data["data_csv"]] if generated_data.get("data_csv") else [],
            "required_scripts": [builder_script],
            "figure_scripts": [builder_script],
            "artifact_manifest": generated_data.get("artifact_manifest", ""),
            "analysis_summary": generated_data.get("analysis_summary_json", ""),
            "chart_json_outputs": [generated_data["chart_json"]] if generated_data.get("chart_json") else [],
            "table_outputs": [generated_data["table_json"]] if generated_data.get("table_json") else [],
            "rebuild_commands": [f"python3 {builder_script} --outdir {RELEASE_EVIDENCE_DIR} --overwrite"],
            "artifact_registry": [
                {
                    "id": f"{topic['slug']}_{mode}_synthetic_evidence_panel",
                    "path": "assets/figures/synthetic_evidence_panel.png",
                    "producer": builder_script,
                    "used_on_slides": ["s2", "s5"],
                    "provenance": "Deterministic synthetic figure generated locally for comparison.",
                }
            ]
            + (
                [
                    {
                        "id": f"{topic['slug']}_{mode}_generated_chart",
                        "path": generated_data["chart_json"],
                        "producer": builder_script,
                        "used_on_slides": ["s3", "s4"],
                        "provenance": "Generated chart JSON from deterministic synthetic data.",
                    },
                    {
                        "id": f"{topic['slug']}_{mode}_generated_table",
                        "path": generated_data["table_json"],
                        "producer": builder_script,
                        "used_on_slides": generated_data.get("table_slide_targets", ["s3"]),
                        "provenance": "Generated table JSON from deterministic synthetic data.",
                    },
                ]
                if generated_data.get("chart_json") and generated_data.get("table_json")
                else []
            ),
        },
        "figure_export_contract": {
            "script": builder_script,
            "rerun_command": f"python3 {builder_script} --outdir {RELEASE_EVIDENCE_DIR} --overwrite",
            "outputs": [
                {
                    "path": "assets/figures/synthetic_evidence_panel.png",
                    "target_slide": "s2" if mode == "corpus" else "s5",
                    "target_variant": "image-sidebar",
                    "target_box": "approx 7.2x4.3 in",
                    "figure_size_inches": [6.67, 4.0],
                    "figure_dpi": 180,
                    "axis_label_min_pt": 8,
                    "crop_rule": "Generated at slide-ready aspect ratio with no large exterior whitespace.",
                }
            ],
        },
        "speed_contract": {
            "renderer": "pptxgenjs",
            "first_pass": "Render-free QA before rendered contact-sheet review.",
            "render_policy": "Render after source files are authored for visual comparison.",
            "asset_policy": "Use local synthetic figures only.",
            "conversion_hint": "Use render_slides.py for contact-sheet evidence.",
        },
        "qa_contract": {
            "required_checks": [
                "python3 scripts/validate_planning.py --workspace <deck>",
                "python3 scripts/build_workspace.py --workspace <deck> --qa --skip-render --overwrite",
                "python3 scripts/report_delivery_readiness.py --workspace <deck> --allow-skip-render",
            ],
            "fail_on": ["planning_errors", "overflow", "overlap", "whitespace", "placeholder_text"],
            "placeholder_checks": True,
        },
        "acceptance_evidence": [
            "build/planning_validation.json",
            "build/build_workspace_report.json",
            "build/renders",
        ],
        "agent_execution_plan": {
            "phases": [
                {"id": "author_sources", "owner": "main_agent", "status": "complete"},
                {"id": "build_render_free_qa", "owner": "script", "status": "complete_after_build"},
                {"id": "render_contact_sheets", "owner": "script", "status": "complete_after_render"},
            ]
        },
    }
    if mode == "corpus":
        atom_brief = (atom_application or {}).get("design_brief") or {}
        for key in ("palette_signals", "typography_signals", "layout_signals", "rhythm_signature"):
            if key in atom_brief:
                brief[key] = atom_brief[key]
        if atom_brief.get("style_atom_composition"):
            brief["style_atom_composition"] = atom_brief["style_atom_composition"]
        brief["large_style_corpus_used"] = {
            "catalog_version": corpus_context.get("catalog_version") if corpus_context else None,
            "selected_family": topic["corpus_family"],
            "summary_record_count": ((corpus_context or {}).get("summary") or {}).get("record_count"),
            "borrowed_treatment_labels": topic["tags"],
            "safety_statement": "Descriptor-only source records; no source deck assets copied or rendered.",
        }
        brief["design_catalog_selection"] = topic.get("design_catalog_selection")
        brief["style_system"]["style_atom_preferred_variants"] = (atom_application or {}).get("preferred_variants", [])
        brief["style_system"]["style_atom_narrative_arc"] = (atom_application or {}).get("narrative_arc", [])
        brief["style_system"]["style_mix_matrix"] = {
            "header_variant_pool": ["left-accent", "split-rule", "top-bottom-rule", "plain"],
            "chart_treatment_pool": ["facts-right", "minimal", "sparse-wide"],
            "table_treatment_pool": ["compact-ledger", "decision-matrix", "readout-sidecar"],
            "figure_table_treatment_pool": ["figure-first", "image-sidebar"],
            "footer_pool": ["source-line", "standard"],
            "mix_rule": "Rotate only treatments that reinforce the selected corpus family.",
        }
    return brief


def _content_plan(topic: dict[str, Any], *, mode: str, atom_application: dict[str, Any] | None = None) -> dict[str, Any]:
    s3_variant = "chart"
    s4_variant = "comparison-2col"
    s5_variant = "image-sidebar"
    s6_variant = ""
    if mode == "corpus":
        variant_plan = _corpus_variant_plan(topic, atom_application or _corpus_atom_application(topic))
        s3_variant = variant_plan["s3"]
        s4_variant = variant_plan["s4"]
        s5_variant = variant_plan["s5"]
        s6_variant = variant_plan["s6"]
    return {
        "thesis": f"{topic['title']} can be explained through a concise evidence loop.",
        "audience": "Skill-quality reviewers",
        "visual_strategy": "Baseline uses ordinary variants; corpus deck uses descriptor-guided evidence/table/decision grammar.",
        "slide_plan": [
            {"slide_id": "s1", "role": "opener", "message": "Set the topic and comparison mode.", "variant": "title", "visual_strategy": "topic-specific title opener"},
            {"slide_id": "s2", "role": "evidence", "message": "Give the primary visual object enough area.", "variant": "image-sidebar" if mode == "corpus" else "comparison-2col", "visual_strategy": "evidence object or modular framing"},
            {"slide_id": "s3", "role": "evidence", "message": "Expose a compact data readout.", "variant": s3_variant, "visual_strategy": "chart or table-first evidence"},
            {"slide_id": "s4", "role": "evidence", "message": "Compare operating states.", "variant": s4_variant if mode == "corpus" else "comparison-2col", "visual_strategy": "sidecar chart, stats strip, or before-after comparison"},
            {"slide_id": "s5", "role": "decision", "message": "Show implications and next action.", "variant": s5_variant if mode == "corpus" else "image-sidebar", "visual_strategy": "decision comparison or figure sidebar"},
            *(
                [{"slide_id": "s6", "role": "decision", "message": "Close with the strongest action signal.", "variant": s6_variant, "visual_strategy": "atom-selected dashboard or decision readout"}]
                if mode == "corpus"
                else []
            ),
        ],
        "narrative_arc": [
            {"phase": "frame", "slides": ["s1", "s2"]},
            {"phase": "evidence", "slides": ["s3", "s4"]},
            {"phase": "decision", "slides": ["s5", *(['s6'] if mode == "corpus" else [])]},
        ],
    }


def _evidence_plan(topic: dict[str, Any], *, mode: str) -> dict[str, Any]:
    return {
        "source_policy": "synthetic_comparison_only",
        "items": [
            {
                "id": "synthetic_metrics",
                "claim": "Pilot metrics are illustrative and generated only for deck-style comparison.",
                "source": "Local deterministic script",
                "used_on_slides": ["s3", "s4"],
            },
            {
                "id": "large_corpus_descriptor" if mode == "corpus" else "baseline_renderer",
                "claim": "Deck structure was selected for comparison of style grammar.",
                "source": "presentation-skill local builder",
                "used_on_slides": ["s1", "s2", "s5"],
            },
        ],
    }


def _write_data_artifacts(topic: dict[str, Any], workspace: Path, *, mode: str) -> dict[str, Any]:
    if not topic.get("data_example"):
        return {}
    builder_script = str((ROOT / "scripts" / "build_random_topic_comparison_decks.py").resolve())
    figure_rel = "assets/figures/synthetic_evidence_panel.png"
    chart_rel = "assets/charts/synthetic_metrics_chart.json"
    table_rel = "assets/tables/synthetic_summary_table.json"
    data_rel = "assets/data/synthetic_metrics.csv"
    artifact_manifest_rel = "assets/artifacts_manifest.json"
    analysis_summary_rel = "assets/analysis_summary.json"
    analysis_summary_md_rel = "assets/analysis_summary.md"
    table_slide_targets = ["s3", "s6"] if mode == "corpus" else ["s3"]
    data_dir = workspace / "assets" / "data"
    chart_dir = workspace / "assets" / "charts"
    table_dir = workspace / "assets" / "tables"
    for directory in (data_dir, chart_dir, table_dir):
        directory.mkdir(parents=True, exist_ok=True)

    rows = [["metric", "value", "unit", "group"]]
    for label, value in zip(topic["chart_categories"], topic["chart_values"]):
        rows.append([str(label), str(value), "index", mode])
    data_csv = workspace / data_rel
    data_csv.write_text("\n".join(",".join(row) for row in rows) + "\n", encoding="utf-8")
    source_fp = _source_fingerprint(data_csv)
    producer_fp = _source_fingerprint(Path(builder_script))
    data_specs_hash = hashlib.sha256(
        json.dumps(
            {
                "topic_slug": topic["slug"],
                "mode": mode,
                "data_recipe": topic.get("data_recipe"),
                "categories": topic["chart_categories"],
                "values": topic["chart_values"],
                "headers": topic["table_headers"],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    common_metadata = {
        "source_path": data_rel,
        "source_sha256": source_fp["source_sha256"],
        "source_bytes": source_fp["source_bytes"],
        "generated_by": builder_script,
        "producer_path": builder_script,
        "producer_sha256": producer_fp["source_sha256"],
        "producer_bytes": producer_fp["source_bytes"],
        "data_recipe": topic.get("data_recipe"),
        "rows_scanned": len(topic["chart_categories"]),
        "rows_used": len(topic["chart_categories"]),
        "series_count": 1,
        "points": len(topic["chart_categories"]),
        "label_col": "metric",
        "value_cols": ["value"],
        "selected_columns": ["metric", "value"],
        "chart_type": "bar",
        "target_box": "approx 7.2x3.8 in",
        "axis_label_min_pt": 8,
    }

    chart_json = workspace / chart_rel
    chart_payload = {
        "type": "bar",
        "title": f"{topic['title']} metrics",
        "categories": topic["chart_categories"],
        "series": [{"name": "Index", "values": topic["chart_values"]}],
        "analysis_metadata": common_metadata,
    }
    _write_json(chart_json, chart_payload)

    table_json = workspace / table_rel
    table_payload = {
        "title": f"{topic['title']} generated summary",
        "headers": topic["table_headers"],
        "rows": topic["table_rows"],
        "analysis_metadata": {
            **common_metadata,
            "rows_scanned": len(topic["table_rows"]),
            "rows_used": len(topic["table_rows"]),
            "points": len(topic["table_rows"]) * len(topic["table_headers"]),
            "selected_columns": topic["table_headers"],
            "target_box": "approx 7.2x3.0 in",
        },
    }
    _write_json(table_json, table_payload)

    chart_fp = _fingerprint(chart_json)
    table_fp = _fingerprint(table_json)
    figure_fp = _fingerprint(workspace / figure_rel)
    rebuild_context = {
        "context_version": "presentation_skill_artifact_rebuild_context_v1",
        "producer_path": builder_script,
        "producer_sha256": producer_fp["source_sha256"],
        "producer_bytes": producer_fp["source_bytes"],
        "data_specs_sha256": data_specs_hash,
        "artifact_manifest": artifact_manifest_rel,
        "analysis_summary": analysis_summary_rel,
        "output_count": 1,
        "source_paths": [data_rel],
        "artifact_paths": [figure_rel, chart_rel, table_rel],
        "outputs": {
            "figures": [figure_rel],
            "chart_json": [chart_rel],
            "summary_tables": [table_rel],
        },
        "commands": {
            "rebuild_figures": f"python3 {builder_script} --outdir {RELEASE_EVIDENCE_DIR} --overwrite",
            "inspect_manifest": "python3 scripts/inspect_artifact_manifest.py --workspace <workspace> --manifest assets/artifacts_manifest.json",
            "validate_planning": "python3 scripts/validate_planning.py --workspace <workspace>",
        },
    }
    output_id = f"{topic['slug']}_{mode}_metrics"
    manifest_payload = {
        "manifest_version": "presentation_skill_artifact_manifest_v1",
        "generated_by": builder_script,
        "producer_path": builder_script,
        "producer_sha256": producer_fp["source_sha256"],
        "producer_bytes": producer_fp["source_bytes"],
        "data_specs_sha256": data_specs_hash,
        "analysis_summary": analysis_summary_rel,
        "analysis_summary_markdown": analysis_summary_md_rel,
        "output_count": 1,
        "rebuild_context": rebuild_context,
        "outputs": [
            {
                "id": output_id,
                "title": f"{topic['title']} generated metrics",
                "source_path": data_rel,
                "source_label": "synthetic_metrics.csv",
                "selected_columns": ["metric", "value"],
                "series_count": 1,
                "points": len(topic["chart_categories"]),
                "analysis_metadata": common_metadata,
                "artifacts": [
                    {
                        "id": f"{output_id}_figure",
                        "role": "figure",
                        "alias": f"image:{output_id}_figure",
                        "path": figure_rel,
                        "fingerprint": figure_fp,
                    },
                    {
                        "id": f"{output_id}_chart",
                        "role": "chart_json",
                        "alias": f"chart:{output_id}",
                        "path": chart_rel,
                        "fingerprint": chart_fp,
                    },
                    {
                        "id": f"{output_id}_table",
                        "role": "summary_table",
                        "alias": f"table:{output_id}_summary",
                        "path": table_rel,
                        "fingerprint": table_fp,
                    },
                ],
            }
        ],
    }
    artifact_manifest = workspace / artifact_manifest_rel
    _write_json(artifact_manifest, manifest_payload)

    analysis_summary_json = workspace / analysis_summary_rel
    analysis_summary_md = workspace / analysis_summary_md_rel
    summary_payload = {
        "summary_version": "presentation_skill_analysis_summary_v1",
        "generated_by": builder_script,
        "producer_path": builder_script,
        "producer_sha256": producer_fp["source_sha256"],
        "producer_bytes": producer_fp["source_bytes"],
        "artifact_manifest": artifact_manifest_rel,
        "data_specs_sha256": data_specs_hash,
        "rebuild_context": rebuild_context,
        "output_count": 1,
        "source_paths": [data_rel],
        "total_points": len(topic["chart_categories"]),
        "datasets": [
            {
                "id": output_id,
                "title": f"{topic['title']} generated metrics",
                "source_path": data_rel,
                "source_label": "synthetic_metrics.csv",
                "sheet_name": "",
                "label_col": "metric",
                "value_cols": ["value"],
                "selected_columns": ["metric", "value"],
                "chart_type": "bar",
                "rows_scanned": len(topic["chart_categories"]),
                "rows_used": len(topic["chart_categories"]),
                "series_count": 1,
                "points": len(topic["chart_categories"]),
                "readout_summary": {
                    "high": max(topic["chart_values"]),
                    "low": min(topic["chart_values"]),
                },
                "readability_warnings": [],
                "figure_path": figure_rel,
                "chart_json": chart_rel,
                "table_json": table_rel,
                "aliases": {
                    "figure": f"image:{output_id}_figure",
                    "chart": f"chart:{output_id}",
                    "table": f"table:{output_id}_summary",
                },
                "readability": {
                    "target_box": "approx 7.2x3.8 in",
                    "figure_size_inches": [6.67, 4.0],
                    "figure_dpi": 180,
                    "axis_label_min_pt": 8,
                },
            }
        ],
        "recommended_next_steps": [
            "Use chart alias for editable chart slides and table alias for compact evidence tables.",
            "Keep source footer and artifact registry slide targets aligned after outline edits.",
        ],
    }
    _write_json(analysis_summary_json, summary_payload)
    analysis_summary_md.write_text(
        f"# Generated data artifacts\n\n"
        f"- Topic: {topic['title']}\n"
        f"- Mode: {mode}\n"
        f"- Recipe: {topic.get('data_recipe')}\n"
        "- Outputs: CSV, editable chart JSON, editable table JSON.\n",
        encoding="utf-8",
    )
    return {
        "data_csv": data_rel,
        "chart_json": chart_rel,
        "table_json": table_rel,
        "artifact_manifest": artifact_manifest_rel,
        "analysis_summary_json": analysis_summary_rel,
        "analysis_summary_md": analysis_summary_md_rel,
        "data_recipe": topic.get("data_recipe"),
        "table_slide_targets": table_slide_targets,
        "output_id": output_id,
    }


def _asset_plan(topic: dict[str, Any], figure_rel: str, generated_data: dict[str, Any] | None = None) -> dict[str, Any]:
    generated_data = generated_data or {}
    return {
        "images": [
            {
                "name": "synthetic_evidence_panel",
                "path": figure_rel,
                "purpose": "Local synthetic visual anchor for comparison deck",
                "used_on_slides": ["s2", "s5"],
                "source": "Generated by scripts/build_random_topic_comparison_decks.py",
                "source_note": "Deterministic synthetic figure generated locally for comparison; no external asset.",
                "license": "Original synthetic artifact for this repository",
                "provenance": "scripts/build_random_topic_comparison_decks.py",
            }
        ],
        "charts": [
            {
                "name": "synthetic_metrics_chart",
                "path": generated_data["chart_json"],
                "purpose": "Editable generated chart JSON for data-driven release evidence",
                "used_on_slides": ["s4"],
                "source": generated_data.get("data_csv", ""),
                "provenance": "Generated by scripts/build_random_topic_comparison_decks.py",
            }
        ]
        if generated_data.get("chart_json")
        else [],
        "tables": [
            {
                "name": "synthetic_summary_table",
                "path": generated_data["table_json"],
                "purpose": "Editable generated table JSON for data-driven release evidence",
                "used_on_slides": generated_data.get("table_slide_targets", ["s3"]),
                "source": generated_data.get("data_csv", ""),
                "provenance": "Generated by scripts/build_random_topic_comparison_decks.py",
            }
        ]
        if generated_data.get("table_json")
        else [],
        "backgrounds": [],
        "generated_images": [],
        "icons": [],
    }


def _slide_sequences(outline: dict[str, Any]) -> dict[str, Any]:
    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    variant_sequence: list[str] = []
    treatment_sequence: list[str] = []
    object_sequence: list[str] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        variant_sequence.append(str(slide.get("variant") or slide.get("type") or "unknown"))
        treatment_sequence.append(str(slide.get("treatment_key") or "none"))
        objects = []
        if slide.get("chart"):
            objects.append("chart")
        if slide.get("tables") or slide.get("headers") or slide.get("rows"):
            objects.append("table")
        assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
        if assets.get("hero_image") or assets.get("image"):
            objects.append("image")
        if slide.get("cards"):
            objects.append("cards")
        if slide.get("left") or slide.get("right"):
            objects.append("comparison")
        object_sequence.append("+".join(objects) if objects else "text")
    return {
        "slide_count": len(slides),
        "content_variant_sequence": variant_sequence,
        "treatment_key_sequence": treatment_sequence,
        "content_object_sequence": object_sequence,
    }


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _qa_summary(workspace: Path) -> dict[str, Any]:
    qa = _read_json_if_exists(workspace / "build" / "qa" / "report.json")
    planning = _read_json_if_exists(workspace / "build" / "planning_validation.json")
    preflight = _read_json_if_exists(workspace / "build" / "preflight.json")
    placeholder_hits = qa.get("placeholder_hits")
    if not isinstance(placeholder_hits, list):
        placeholder_hits = []
    return {
        "report": str(workspace / "build" / "qa" / "report.json"),
        "planning_report": str(workspace / "build" / "planning_validation.json"),
        "planning_error_count": int(planning.get("error_count") or 0),
        "planning_warning_count": int(planning.get("warning_count") or 0),
        "preflight_report": str(workspace / "build" / "preflight.json"),
        "preflight_error_count": int(preflight.get("error_count") or 0),
        "preflight_warning_count": int(preflight.get("warning_count") or 0),
        "overflow_count": int(qa.get("overflow_count") or 0),
        "overlap_count": int(qa.get("overlap_count") or 0),
        "placeholder_count": len(placeholder_hits),
        "geometry_error_count": int(qa.get("geometry_error_count") or 0),
        "geometry_warning_count": int(qa.get("geometry_warning_count") or 0),
        "whitespace_warning_count": int(qa.get("whitespace_warning_count") or 0),
        "design_error_count": int(qa.get("design_error_count") or 0),
        "design_warning_count": int(qa.get("design_warning_count") or 0),
        "visual_warning_count": int(qa.get("visual_warning_count") or 0),
        "visual_review_warning_count": int(qa.get("visual_review_warning_count") or 0),
        "rendered_slide_count": int(qa.get("rendered_slide_count") or 0),
        "expected_slide_count": int(qa.get("expected_slide_count") or 0),
    }


def _visual_review_summary(review_dir: Path) -> dict[str, Any]:
    report_path = review_dir / "visual_review.json"
    review = _read_json_if_exists(report_path)
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    warnings = [
        {
            "slide": issue.get("slide"),
            "type": issue.get("type"),
            "severity": issue.get("severity"),
            "message": issue.get("message"),
        }
        for issue in issues
        if isinstance(issue, dict) and issue.get("severity") == "warning"
    ]
    return {
        "report": str(report_path),
        "contact_sheet": str(review_dir / "contact_sheet.jpg"),
        "warning_count": int(review.get("warning_count") or len(warnings)),
        "info_count": int(review.get("info_count") or 0),
        "issue_count": int(review.get("issue_count") or len(issues)),
        "warnings": warnings,
        "passed": bool(review.get("passed")) if "passed" in review else False,
    }


def _structural_blocking_counts(summary: dict[str, Any]) -> dict[str, int]:
    keys = [
        "overflow_count",
        "overlap_count",
        "placeholder_count",
        "planning_error_count",
        "planning_warning_count",
        "preflight_error_count",
        "preflight_warning_count",
        "geometry_error_count",
        "whitespace_warning_count",
        "design_error_count",
        "design_warning_count",
    ]
    return {key: int(summary.get(key) or 0) for key in keys}


def _build_workspace(topic: dict[str, Any], *, mode: str, outdir: Path) -> dict[str, Any]:
    preset = topic["baseline_preset"] if mode == "baseline" else topic["corpus_preset"]
    workspace = outdir / "cases" / topic["slug"] / mode
    title = f"{topic['title']} ({mode})"
    prompt = f"{topic['prompt']} [{mode}]"
    init = _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            title,
            "--style-preset",
            preset,
            "--overwrite",
            "--user-prompt",
            prompt,
        ]
    )
    figure_rel = "assets/figures/synthetic_evidence_panel.png"
    _draw_topic_figure(topic, workspace / figure_rel, mode=mode)
    generated_data = _write_data_artifacts(topic, workspace, mode=mode)
    corpus_context = None
    atom_application = None
    if mode == "corpus":
        corpus_context = compact_large_style_corpus_context(
            topic["prompt"],
            primary_family=topic["corpus_family"],
            max_records=6,
        )
        atom_application = _corpus_atom_application(topic)
    outline = (
        _corpus_outline(topic, figure_rel, corpus_context or {}, atom_application or {})
        if mode == "corpus"
        else _baseline_outline(topic, figure_rel)
    )
    _write_json(workspace / "outline.json", outline)
    _write_json(
        workspace / "design_brief.json",
        _design_brief(
            topic,
            mode=mode,
            preset=preset,
            corpus_context=corpus_context,
            generated_data=generated_data,
            atom_application=atom_application,
        ),
    )
    _write_json(workspace / "content_plan.json", _content_plan(topic, mode=mode, atom_application=atom_application))
    _write_json(workspace / "evidence_plan.json", _evidence_plan(topic, mode=mode))
    _write_json(workspace / "asset_plan.json", _asset_plan(topic, figure_rel, generated_data))
    notes = [
        f"# {topic['title']} ({mode})",
        "",
        f"- Comparison mode: {mode}",
        f"- Style preset: {preset}",
        f"- Random seed: {RANDOM_SEED}",
        "- Source posture: synthetic local data only; no external source decks copied or rendered.",
    ]
    if corpus_context:
        notes.extend(
            [
                f"- Large corpus version: {corpus_context.get('catalog_version')}",
                f"- Large corpus selected family: {topic['corpus_family']}",
                f"- Borrowed descriptor labels: {', '.join(topic['tags'])}",
            ]
        )
    if generated_data:
        notes.extend(
            [
                f"- Generated data recipe: {generated_data.get('data_recipe')}",
                f"- Generated chart JSON: {generated_data.get('chart_json')}",
                f"- Generated table JSON: {generated_data.get('table_json')}",
            ]
        )
    (workspace / "notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    router_prompt = workspace / "build" / "style_content_router_prompt.txt"
    router = _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "emit_style_content_router.py"),
            "--workspace",
            str(workspace),
            "--user-prompt",
            prompt,
            "--output",
            str(router_prompt),
        ]
    )
    build = _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_workspace.py"),
            "--workspace",
            str(workspace),
            "--qa",
            "--skip-render",
            "--overwrite",
            "--renderer",
            "pptxgenjs",
        ]
    )
    workspace_manifest = json.loads((workspace / "workspace.json").read_text(encoding="utf-8"))
    style_contract = json.loads((workspace / "style_contract.json").read_text(encoding="utf-8"))
    pptx_path = workspace / style_contract["build"]["output_pptx"]
    render_dir = workspace / "build" / "renders"
    render = _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "render_slides.py"),
            "--input",
            str(pptx_path),
            "--outdir",
            str(render_dir),
            "--format",
            "png",
        ]
    )
    review_dir = workspace / "build" / "visual_review"
    visual_review = _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "visual_review.py"),
            "--input",
            str(pptx_path),
            "--outdir",
            str(review_dir),
            "--renders-dir",
            str(render_dir),
            "--outline",
            str(workspace / "outline.json"),
        ]
    )
    prompt_text = router_prompt.read_text(encoding="utf-8")
    render_paths = sorted(render_dir.glob("slide-*.png"))
    sequences = _slide_sequences(outline)
    treatment_signature = "|".join(
        [
            preset,
            "/".join(sequences["content_variant_sequence"]),
            "/".join(sequences["treatment_key_sequence"]),
            "/".join(sequences["content_object_sequence"]),
        ]
    )
    return {
        "topic_slug": topic["slug"],
        "topic_title": topic["title"],
        "mode": mode,
        "preset": preset,
        "workspace": str(workspace),
        "pptx": str(pptx_path),
        "renders_dir": str(render_dir),
        "render_count": len(render_paths),
        "render_paths": [str(path) for path in render_paths],
        "visual_review_dir": str(review_dir),
        "visual_review_contact_sheet": str(review_dir / "contact_sheet.jpg"),
        "router_prompt": str(router_prompt),
        "router_prompt_chars": len(prompt_text),
        "router_large_corpus_present": '"large_style_corpus"' in prompt_text and '"record_count": 2000' in prompt_text,
        "outline_large_corpus_context_present": bool(outline.get("large_corpus_context")),
        "outline_large_corpus_record_count": (outline.get("large_corpus_context") or {}).get("record_count"),
        "corpus_context": corpus_context,
        "design_catalog_selection": topic.get("design_catalog_selection"),
        "data_example": bool(topic.get("data_example")),
        "generated_data_artifacts": generated_data,
        **sequences,
        "style_delta_signature": treatment_signature,
        "qa_summary": _qa_summary(workspace),
        "visual_review_summary": _visual_review_summary(review_dir),
        "commands": {
            "init": init,
            "router": router,
            "build": build,
            "render": render,
            "visual_review": visual_review,
        },
        "workspace_manifest": workspace_manifest,
    }


def _thumb(path: Path, size: tuple[int, int]) -> Image.Image:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGB", size, "#FFFFFF")
    x = (size[0] - image.size[0]) // 2
    y = (size[1] - image.size[1]) // 2
    canvas.paste(image, (x, y))
    return canvas


def _draw_label(draw: Any, xy: tuple[int, int], text: str, *, width: int, font: Any, fill: str) -> int:
    x, y = xy
    words = text.split()
    line = ""
    line_height = int(getattr(font, "size", 14) * 1.25)
    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > width and line:
            draw.text((x, y), line, fill=fill, font=font)
            y += line_height
            line = word
        else:
            line = test
    if line:
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height
    return y


def _build_pair_contact_sheet(topic: dict[str, Any], baseline: dict[str, Any], corpus: dict[str, Any], outdir: Path) -> dict[str, Any]:
    if Image is None or ImageDraw is None or ImageStat is None:
        raise RuntimeError("Pillow is required to build comparison contact sheets")
    thumb_size = (300, 169)
    slide_count = min(6, max(len(baseline["render_paths"]), len(corpus["render_paths"])))
    width = 120 + slide_count * (thumb_size[0] + 22)
    height = 560
    image = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    draw.text((48, 34), f"{topic['title']} / baseline vs corpus-guided", fill="#111827", font=_font(30, bold=True))
    draw.text((48, 78), "Same random topic, rebuilt as ordinary baseline and descriptor-corpus-guided deck.", fill="#4B5563", font=_font(17))
    draw.text((48, 145), "Baseline", fill="#111827", font=_font(20, bold=True))
    draw.text((48, 338), "Corpus", fill="#111827", font=_font(20, bold=True))
    for idx in range(slide_count):
        x = 145 + idx * (thumb_size[0] + 22)
        for row_y, record in ((125, baseline), (318, corpus)):
            paths = record["render_paths"]
            if idx >= len(paths):
                continue
            thumb = _thumb(Path(paths[idx]), thumb_size)
            image.paste(thumb, (x, row_y))
            draw.rectangle((x, row_y, x + thumb_size[0], row_y + thumb_size[1]), outline="#CBD5E1", width=2)
            draw.text((x, row_y + thumb_size[1] + 8), f"Slide {idx + 1}", fill="#4B5563", font=_font(12))
    draw.text((48, height - 52), "Corpus decks record descriptor-only large-corpus context; no external source slides were copied or rendered.", fill="#6B7280", font=_font(14))
    path = outdir / "contact_sheets" / f"{topic['slug']}_baseline_vs_corpus.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    stat = ImageStat.Stat(image.convert("L"))
    return {
        "topic_slug": topic["slug"],
        "path": str(path),
        "size": list(image.size),
        "luma_extrema": list(stat.extrema[0]),
        "nonblank": bool(stat.extrema[0][1] - stat.extrema[0][0] > 10),
    }


def _build_overview_contact_sheet(topics: list[dict[str, Any]], case_records: list[dict[str, Any]], pair_sheets: list[dict[str, Any]], outdir: Path) -> dict[str, Any]:
    if Image is None or ImageDraw is None or ImageStat is None:
        raise RuntimeError("Pillow is required to build comparison contact sheets")
    columns = 2
    thumb_size = (960, 262)
    row_height = 355
    header_height = 150
    metrics_height = 330
    rows = (len(pair_sheets) + columns - 1) // columns
    width = 80 + columns * thumb_size[0] + (columns - 1) * 80
    height = header_height + rows * row_height + metrics_height
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    draw.text((58, 44), "Random Topic Deck Comparison", fill="#111827", font=_font(40, bold=True))
    draw.text(
        (60, 98),
        f"Baseline vs descriptor-corpus-guided decks across {len(topics)} fresh synthetic topics",
        fill="#4B5563",
        font=_font(20),
    )
    for idx, sheet in enumerate(pair_sheets):
        topic = topics[idx]
        thumb = _thumb(Path(sheet["path"]), thumb_size)
        col = idx % columns
        row = idx // columns
        x = 58 + col * (thumb_size[0] + 80)
        y = header_height + row * row_height
        image.paste(thumb, (x, y))
        draw.rectangle((x, y, x + thumb_size[0], y + thumb_size[1]), outline="#CBD5E1", width=2)
        _draw_label(draw, (x, y + thumb_size[1] + 18), topic["title"], width=thumb_size[0], font=_font(22, bold=True), fill="#111827")
        draw.text((x, y + thumb_size[1] + 76), f"{topic['baseline_preset']} → {topic['corpus_preset']}", fill="#4B5563", font=_font(16))
    y2 = header_height + rows * row_height + 24
    draw.text((58, y2), "Corpus leverage evidence", fill="#111827", font=_font(28, bold=True))
    lines = [
        f"Decks built: {len(case_records)} plus one gallery deck",
        f"Corpus-guided cases: {sum(1 for item in case_records if item['mode'] == 'corpus')}",
        f"Outlines carrying corpus context: {sum(1 for item in case_records if item['outline_large_corpus_context_present'])}/{len(case_records)}",
        f"Router prompts exposing catalog context: {sum(1 for item in case_records if item['router_large_corpus_present'])}/{len(case_records)}",
        f"Generated data examples: {sum(1 for item in case_records if item.get('mode') == 'corpus' and item.get('data_example'))}",
        f"Random seed: {RANDOM_SEED}",
        "All slide content is synthetic; corpus sources are descriptor-only metadata.",
    ]
    yy = y2 + 45
    for line in lines:
        draw.text((72, yy), f"• {line}", fill="#374151", font=_font(19))
        yy += 33
    presets = Counter(item["preset"] for item in case_records)
    right_x = width // 2 + 40
    draw.text((right_x, y2), "Presets used", fill="#111827", font=_font(28, bold=True))
    yy = y2 + 45
    for preset, count in sorted(presets.items()):
        draw.text((right_x + 14, yy), f"{preset}: {count}", fill="#374151", font=_font(19))
        yy += 33
    path = outdir / "contact_sheets" / "all_topics_baseline_vs_corpus.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    stat = ImageStat.Stat(image.convert("L"))
    return {
        "path": str(path),
        "size": list(image.size),
        "luma_extrema": list(stat.extrema[0]),
        "nonblank": bool(stat.extrema[0][1] - stat.extrema[0][0] > 10),
    }


def _build_gallery_deck(outdir: Path, overview_sheet: dict[str, Any], pair_sheets: list[dict[str, Any]]) -> dict[str, Any]:
    workspace = outdir / "comparison-gallery"
    builder_script = str((ROOT / "scripts" / "build_random_topic_comparison_decks.py").resolve())
    _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            "Random Topic Corpus Comparison Gallery",
            "--style-preset",
            "editorial-minimal",
            "--overwrite",
            "--user-prompt",
            "gallery deck comparing baseline and corpus-guided random topic slide decks",
        ]
    )
    asset_dir = workspace / "assets" / "comparisons"
    asset_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    for source in [overview_sheet["path"], *[item["path"] for item in pair_sheets]]:
        src = Path(source)
        dest = asset_dir / src.name
        shutil.copy2(src, dest)
        copied.append({"source": str(src), "relative": str(dest.relative_to(workspace))})
    slides: list[dict[str, Any]] = [
        {
            "slide_id": "s1",
            "type": "title",
            "title": "Random Topic Corpus Comparison",
            "subtitle": f"v{RELEASE_VERSION} baseline vs descriptor-corpus-guided decks built from source JSON",
        },
        {
            "slide_id": "s2",
            "type": "content",
            "variant": "image-sidebar",
            "title": "All topics at a glance",
            "assets": {"hero_image": copied[0]["relative"]},
            "caption": "Rendered comparison contact sheet generated locally.",
            "sidebar_sections": [
                {"title": "Purpose", "body": "Check whether deck structure changes when the large corpus informs design choices."},
                {"title": "Scope", "body": f"{len(pair_sheets)} synthetic topics, each with baseline and corpus-guided decks."},
                {"title": "Safety", "body": "Descriptor-only corpus references; no external slides copied."},
            ],
            "sources": ["Local comparison builder"],
        },
    ]
    for idx, item in enumerate(copied[1:], start=3):
        title = Path(item["relative"]).stem.replace("_baseline_vs_corpus", "").replace("-", " ").replace("_", " ").title()
        slides.append(
            {
                "slide_id": f"s{idx}",
                "type": "content",
                "variant": "image-sidebar",
                "title": title,
                "assets": {"hero_image": item["relative"]},
                "caption": "Baseline row above, corpus-guided row below.",
                "sidebar_sections": [
                    {"title": "Compare", "body": "Look for evidence-object size, table/decision treatment, and source/footer handling."},
                    {"title": "Corpus signal", "body": "The corpus-guided version records selected family and treatment labels in source files."},
                ],
                "sources": ["Local comparison builder"],
            }
        )
    outline = {
        "title": "Random Topic Corpus Comparison Gallery",
        "subtitle": "Rendered deck evidence",
        "deck_style": {
            "visual_density": "medium",
            "style_seed": "random-topic-comparison-gallery",
            "footer_page_numbers": True,
        },
        "slides": slides,
    }
    _write_json(workspace / "outline.json", outline)
    _write_json(
        workspace / "design_brief.json",
        {
            "topic": "Random Topic Corpus Comparison Gallery",
            "content_maturity": "technical/educational",
            "audience_posture": "coworkers/operators",
            "format_promise": "Compact gallery deck that embeds rendered comparison sheets.",
            "design_dna": "editorial report",
            "style_system": {"style_preset": "editorial-minimal", "style_seed": "random-topic-comparison-gallery"},
            "readability_contract": {
                "min_title_pt": 26,
                "min_body_pt": 12,
                "min_caption_pt": 7.5,
                "chart_label_min_pt": 7,
                "min_chart_label_pt": 7,
                "footer_reserved_inches": 0.28,
                "max_title_lines": 2,
                "max_slide_words": 90,
                "max_slide_chars": 620,
                "table_density_rule": "No dense tables in the gallery; use rendered contact sheets as the evidence object.",
                "whitespace_rule": "Keep contact sheets large and use sidebars only for short inspection notes.",
                "figure_crop_rule": "Use generated contact sheets without exterior whitespace or decorative cropping.",
            },
            "title_page_concept": {
                "chosen_archetype": "comparison gallery opener",
                "dominant_element": "Random Topic Corpus Comparison",
                "supporting_element": "Baseline versus corpus-guided rendered sheets",
                "why_this_could_only_be_this_deck": "It names the exact evidence gallery generated by this builder.",
            },
            "structure_strategy": {
                "primary_scaffold": "title, overview sheet, one pair sheet per topic",
                "repeated_elements": ["image-sidebar contact sheet slides", "short inspection sidebar", "local source footer"],
                "allowed_variations": ["image-sidebar"],
                "container_policy": "Let the rendered sheet be the primary object; keep text secondary.",
                "rhythm_break_plan": "The overview sheet starts broad; each following slide zooms into one topic pair.",
            },
            "analysis_artifact_plan": {
                "candidate_data_files": [],
                "required_scripts": [builder_script],
                "figure_scripts": [builder_script],
                "artifact_registry": [
                    {
                        "id": Path(item["relative"]).stem,
                        "path": item["relative"],
                        "producer": builder_script,
                        "used_on_slides": [f"s{idx + 2}"],
                        "provenance": "Generated locally from rendered deck JPGs.",
                    }
                    for idx, item in enumerate(copied)
                ],
                "rebuild_commands": [
                    f"python3 {builder_script} --outdir {RELEASE_EVIDENCE_DIR} --overwrite"
                ],
            },
            "figure_export_contract": {
                "script": builder_script,
                "rerun_command": f"python3 {builder_script} --outdir {RELEASE_EVIDENCE_DIR} --overwrite",
                "outputs": [
                    {
                        "path": item["relative"],
                        "target_slide": f"s{idx + 2}",
                        "target_variant": "image-sidebar",
                        "target_box": "approx 7.2x4.4 in",
                        "figure_size_inches": [8.0, 4.5],
                        "figure_dpi": 150,
                        "axis_label_min_pt": 7,
                        "crop_rule": "Contact sheet should remain readable without being cropped.",
                    }
                    for idx, item in enumerate(copied)
                ],
            },
            "speed_contract": {
                "renderer": "pptxgenjs",
                "first_pass": "Build gallery from existing rendered sheets.",
                "render_policy": "Render after the gallery deck is built for final inspection.",
                "asset_policy": "Use local generated contact sheets only.",
                "conversion_hint": "Use scripts/render_slides.py after build_workspace.py finishes.",
            },
            "qa_contract": {
                "required_checks": [
                    "python3 scripts/validate_planning.py --workspace <deck>",
                    "python3 scripts/build_workspace.py --workspace <deck> --qa --skip-render --overwrite",
                    "python3 scripts/report_delivery_readiness.py --workspace <deck> --allow-skip-render",
                    "python3 scripts/render_slides.py --pptx <deck>",
                ],
                "fail_on": ["planning_errors", "overflow", "overlap", "whitespace", "placeholder_text"],
                "placeholder_checks": True,
            },
            "acceptance_evidence": ["build/qa/report.json", "build/renders"],
            "agent_execution_plan": {
                "phases": [
                    {"id": "copy_contact_sheets", "owner": "script", "status": "complete"},
                    {"id": "build_gallery", "owner": "script", "status": "complete_after_build"},
                    {"id": "render_gallery", "owner": "script", "status": "complete_after_render"},
                ]
            },
        },
    )
    _write_json(
        workspace / "content_plan.json",
        {
            "thesis": "Rendered sheets make corpus-guided differences inspectable.",
            "audience": "Skill-quality reviewers",
            "visual_strategy": "Use contact sheets as the evidence object and keep explanatory text brief.",
            "slide_plan": [
                {
                    "slide_id": "s1",
                    "role": "opener",
                    "message": "Name the comparison evidence artifact.",
                    "variant": "title",
                    "visual_strategy": "plain editorial opener",
                },
                {
                    "slide_id": "s2",
                    "role": "overview",
                    "message": "Show all random topic comparisons at a glance.",
                    "variant": "image-sidebar",
                    "visual_strategy": "overview contact sheet",
                },
                *[
                    {
                        "slide_id": f"s{idx + 3}",
                        "role": "comparison",
                        "message": "Inspect one baseline/corpus topic pair.",
                        "variant": "image-sidebar",
                        "visual_strategy": "topic pair contact sheet",
                    }
                    for idx, _item in enumerate(pair_sheets)
                ],
            ],
            "narrative_arc": [
                {"phase": "frame", "slides": ["s1", "s2"]},
                {"phase": "inspect", "slides": [f"s{idx + 3}" for idx, _item in enumerate(pair_sheets)]},
            ],
        },
    )
    _write_json(workspace / "evidence_plan.json", {"source_policy": "local_generated_evidence", "items": []})
    _write_json(
        workspace / "asset_plan.json",
        {
            "images": [
                {
                    "name": Path(item["relative"]).stem,
                    "path": item["relative"],
                    "purpose": "Rendered comparison evidence sheet for gallery deck",
                    "used_on_slides": [f"s{idx + 2}"],
                    "source": "Generated by scripts/build_random_topic_comparison_decks.py",
                    "source_note": "Local generated contact sheet from rendered deck images; no external asset.",
                    "license": "Original synthetic artifact for this repository",
                    "provenance": "scripts/build_random_topic_comparison_decks.py",
                }
                for idx, item in enumerate(copied)
            ],
            "charts": [],
            "tables": [],
            "backgrounds": [],
            "generated_images": [],
            "icons": [],
        },
    )
    (workspace / "notes.md").write_text(
        "# Random Topic Corpus Comparison Gallery\n\n"
        "Generated from local rendered sheets. External corpus sources are descriptor-only metadata.\n",
        encoding="utf-8",
    )
    _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "build_workspace.py"),
            "--workspace",
            str(workspace),
            "--qa",
            "--skip-render",
            "--overwrite",
            "--renderer",
            "pptxgenjs",
        ]
    )
    style_contract = json.loads((workspace / "style_contract.json").read_text(encoding="utf-8"))
    pptx_path = workspace / style_contract["build"]["output_pptx"]
    render_dir = workspace / "build" / "renders"
    _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "render_slides.py"),
            "--input",
            str(pptx_path),
            "--outdir",
            str(render_dir),
            "--format",
            "png",
        ]
    )
    return {
        "workspace": str(workspace),
        "pptx": str(pptx_path),
        "renders_dir": str(render_dir),
        "render_count": len(list(render_dir.glob("slide-*.png"))),
        "qa_summary": _qa_summary(workspace),
    }


def _pair_structural_deltas(case_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    by_topic: dict[str, dict[str, dict[str, Any]]] = {}
    for record in case_records:
        by_topic.setdefault(record["topic_slug"], {})[record["mode"]] = record
    for topic_slug, modes in sorted(by_topic.items()):
        baseline = modes.get("baseline")
        corpus = modes.get("corpus")
        if not baseline or not corpus:
            continue
        variant_delta = baseline.get("content_variant_sequence") != corpus.get("content_variant_sequence")
        treatment_delta = baseline.get("treatment_key_sequence") != corpus.get("treatment_key_sequence")
        object_delta = baseline.get("content_object_sequence") != corpus.get("content_object_sequence")
        pairs.append(
            {
                "topic_slug": topic_slug,
                "variant_sequence_delta": bool(variant_delta),
                "treatment_sequence_delta": bool(treatment_delta),
                "object_sequence_delta": bool(object_delta),
                "passes_structural_delta_gate": bool(variant_delta or treatment_delta or object_delta),
                "baseline_signature": baseline.get("style_delta_signature"),
                "corpus_signature": corpus.get("style_delta_signature"),
            }
        )
    return pairs


def _release_quality(
    case_records: list[dict[str, Any]],
    gallery: dict[str, Any],
    pair_sheets: list[dict[str, Any]],
    overview_sheet: dict[str, Any],
) -> dict[str, Any]:
    structural_totals = Counter()
    for record in case_records:
        structural_totals.update(_structural_blocking_counts(record.get("qa_summary") or {}))
    structural_totals.update(_structural_blocking_counts(gallery.get("qa_summary") or {}))
    visual_warning_total = sum(
        int((record.get("visual_review_summary") or {}).get("warning_count") or 0)
        for record in case_records
    )
    readability_warning_total = sum(
        int((record.get("qa_summary") or {}).get("planning_warning_count") or 0)
        + int((record.get("qa_summary") or {}).get("design_warning_count") or 0)
        for record in case_records
    ) + int((gallery.get("qa_summary") or {}).get("planning_warning_count") or 0)
    pair_deltas = _pair_structural_deltas(case_records)
    contact_sheets = [overview_sheet, *pair_sheets]
    corpus_families = sorted({str(record.get("preset")) for record in case_records if record.get("mode") == "corpus"})
    data_artifact_examples = [
        record["topic_slug"]
        for record in case_records
        if record.get("mode") == "corpus" and record.get("data_example") and record.get("generated_data_artifacts")
    ]
    return {
        "structural_qa_totals": dict(structural_totals),
        "structural_qa_pass": all(value == 0 for value in structural_totals.values()),
        "visual_warning_total": visual_warning_total,
        "visual_warning_target": 0,
        "visual_warning_target_pass": visual_warning_total == 0,
        "readability_warning_total": readability_warning_total,
        "readability_warning_target": 0,
        "readability_warning_target_pass": readability_warning_total == 0,
        "unique_corpus_family_count": len(corpus_families),
        "unique_corpus_family_target": 8,
        "unique_corpus_family_pass": len(corpus_families) >= 8,
        "corpus_families": corpus_families,
        "data_artifact_example_count": len(data_artifact_examples),
        "data_artifact_example_target": 3,
        "data_artifact_example_pass": len(data_artifact_examples) >= 3,
        "data_artifact_example_slugs": data_artifact_examples,
        "pair_structural_deltas": pair_deltas,
        "pair_structural_delta_count": sum(1 for pair in pair_deltas if pair["passes_structural_delta_gate"]),
        "pair_structural_delta_target": len(TOPICS),
        "pair_structural_delta_pass": bool(pair_deltas) and all(pair["passes_structural_delta_gate"] for pair in pair_deltas),
        "contact_sheet_count": len(contact_sheets),
        "contact_sheet_nonblank_count": sum(1 for sheet in contact_sheets if sheet.get("nonblank")),
        "contact_sheet_nonblank_pass": all(bool(sheet.get("nonblank")) for sheet in contact_sheets),
        "gallery_render_count": int(gallery.get("render_count") or 0),
    }


def _write_release_notes(path: Path, manifest: dict[str, Any]) -> None:
    quality = manifest.get("release_quality") or {}
    def display_path(path_value: Any) -> str:
        if not path_value:
            return ""
        try:
            return str(Path(str(path_value)).resolve().relative_to(ROOT))
        except ValueError:
            return str(path_value)

    warning_budget_status = "pass" if (
        quality.get("structural_qa_pass")
        and quality.get("visual_warning_target_pass")
        and quality.get("readability_warning_target_pass")
    ) else "fail"
    lines = [
        f"# presentation-skill v{RELEASE_VERSION}",
        "",
        "This release turns the 2,000-record descriptor-only public deck corpus into reproducible deck evidence, not only a catalog.",
        "",
        "## What changed",
        "",
        f"- Expanded the random-topic baseline-vs-corpus comparison builder to {manifest.get('topic_count')} synthetic topics and {manifest.get('deck_count')} case decks.",
        "- Added a reusable design-catalog selection layer that records primary family, treatment tags, data recipe, and structure intent.",
        "- Added manifest fields that prove corpus-guided outlines carry large-corpus context while baseline outlines do not.",
        "- Added structural sequence signatures so corpus leverage can be checked as slide grammar, not only color/header chrome.",
        "- Added generated data-artifact examples with CSV, editable chart JSON, editable table JSON, artifact manifest, and analysis summary files.",
        "- Added compact rendered contact sheets and a gallery deck for quick visual inspection.",
        "- Kept all evidence publish-safe: synthetic slide content plus descriptor-only corpus metadata; no external decks, screenshots, logos, copied text, or copied geometry.",
        "",
        "## Evidence",
        "",
        f"- Manifest: `{display_path(manifest.get('manifest_path'))}`",
        f"- Gallery deck: `{display_path((manifest.get('gallery_deck') or {}).get('pptx'))}`",
        f"- Overview contact sheet: `{display_path((manifest.get('overview_contact_sheet') or {}).get('path'))}`",
        "- Pair contact sheets: `contact_sheets/*_baseline_vs_corpus.png`",
        "- Builder: `scripts/build_random_topic_comparison_decks.py`",
        "- Smoke gate: `python3 scripts/run_random_topic_comparison_smoke.py`",
        "",
        "## Validation snapshot",
        "",
        f"- Automated smoke gate: `{warning_budget_status}`",
        f"- Decks generated: `{manifest.get('deck_count')}`",
        f"- Topics generated: `{manifest.get('topic_count')}`",
        f"- Unique corpus families: `{quality.get('unique_corpus_family_count')}` / `{quality.get('unique_corpus_family_target')}`",
        f"- Generated data examples: `{quality.get('data_artifact_example_count')}` / `{quality.get('data_artifact_example_target')}`",
        f"- Corpus-guided cases: `{(manifest.get('leverage_evidence') or {}).get('corpus_guided_case_count')}`",
        f"- Outlines with corpus context: `{(manifest.get('leverage_evidence') or {}).get('outlines_with_large_corpus_context')}`",
        f"- Warning budget: `{quality.get('visual_warning_total')}` visual, `{quality.get('readability_warning_total')}` readability, zero layout blockers",
        f"- Pair structural deltas: `{quality.get('pair_structural_delta_count')}` / `{quality.get('pair_structural_delta_target')}`",
        f"- Nonblank contact sheets: `{quality.get('contact_sheet_nonblank_count')}` / `{quality.get('contact_sheet_count')}`",
        "",
        "## Residual risk",
        "",
        "This is corpus-leverage release evidence. It is not a full published-GitHub-baseline audit; that broader comparison remains covered by earlier release evidence galleries.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def build_random_topic_comparison(outdir: Path, *, overwrite: bool = False) -> dict[str, Any]:
    outdir = outdir.expanduser().resolve()
    if outdir.exists() and overwrite:
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    case_records: list[dict[str, Any]] = []
    pair_sheets: list[dict[str, Any]] = []
    for topic in TOPICS:
        baseline = _build_workspace(topic, mode="baseline", outdir=outdir)
        corpus = _build_workspace(topic, mode="corpus", outdir=outdir)
        case_records.extend([baseline, corpus])
        pair_sheets.append(_build_pair_contact_sheet(topic, baseline, corpus, outdir))
    overview_sheet = _build_overview_contact_sheet(TOPICS, case_records, pair_sheets, outdir)
    gallery = _build_gallery_deck(outdir, overview_sheet, pair_sheets)
    release_notes_path = outdir / f"RELEASE_NOTES_v{RELEASE_VERSION}.md"
    catalog_summary = design_catalog_summary(TOPICS)
    manifest = {
        "manifest_version": "random_topic_corpus_comparison_v2",
        "release_version": RELEASE_VERSION,
        "random_seed": RANDOM_SEED,
        "output_dir": str(outdir),
        "comparison_model": "baseline_vs_large_corpus_guided",
        "design_catalog_version": DESIGN_CATALOG_VERSION,
        "design_catalog_summary": catalog_summary,
        "topic_count": len(TOPICS),
        "deck_count": len(case_records),
        "gallery_deck": gallery,
        "topics": [
            {
                "slug": topic["slug"],
                "title": topic["title"],
                "baseline_preset": topic["baseline_preset"],
                "corpus_preset": topic["corpus_preset"],
                "corpus_family": topic["corpus_family"],
                "borrowed_treatment_labels": topic["tags"],
                "data_example": bool(topic.get("data_example")),
                "data_recipe": topic.get("data_recipe"),
                "design_catalog_selection": topic.get("design_catalog_selection"),
            }
            for topic in TOPICS
        ],
        "cases": case_records,
        "pair_contact_sheets": pair_sheets,
        "overview_contact_sheet": overview_sheet,
        "release_notes": str(release_notes_path),
        "leverage_evidence": {
            "router_prompts_with_large_corpus": sum(1 for item in case_records if item["router_large_corpus_present"]),
            "router_prompt_count": len(case_records),
            "outlines_with_large_corpus_context": sum(
                1 for item in case_records if item["outline_large_corpus_context_present"]
            ),
            "corpus_guided_case_count": sum(1 for item in case_records if item["mode"] == "corpus"),
            "corpus_guided_topic_count": len(TOPICS),
            "descriptor_only": True,
            "no_external_source_decks_rendered_or_copied": True,
        },
    }
    manifest["release_quality"] = _release_quality(case_records, gallery, pair_sheets, overview_sheet)
    manifest_path = outdir / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    _write_release_notes(release_notes_path, manifest)
    _write_json(manifest_path, manifest)
    return manifest


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Output directory for comparison run")
    parser.add_argument("--overwrite", action="store_true", help="Replace the output directory before building")
    return parser.parse_args()


def main() -> int:
    args = _args()
    manifest = build_random_topic_comparison(Path(args.outdir), overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "passed": True,
                "manifest_path": manifest["manifest_path"],
                "deck_count": manifest["deck_count"],
                "gallery_pptx": manifest["gallery_deck"]["pptx"],
                "overview_contact_sheet": manifest["overview_contact_sheet"]["path"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
