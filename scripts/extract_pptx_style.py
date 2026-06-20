#!/usr/bin/env python3
"""Extract reusable style signals from existing PowerPoint decks.

The report is intentionally source-only. It inspects PPTX XML for geometry,
text sizes, colors, rules, footer/source patterns, charts, tables, and images,
then emits a deterministic design-brief fragment that can seed a workspace
without cloning arbitrary slide XML.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

EMU_PER_IN = 914400

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}

SUPPORTED_HEADER_VARIANTS = [
    "left-accent",
    "split-rule",
    "title-rule",
    "side-rail",
    "top-bottom-rule",
    "plain",
]

SOURCE_RE = re.compile(
    r"\b(source|sources|ref|refs|reference|references|doi|pmid|pmcid|http|www\.)\b",
    re.IGNORECASE,
)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:\d+|[#]|\d+\s*/\s*\d+|slide\s+\d+)\s*$", re.IGNORECASE)


def _write_text_if_changed(path: Path, text: str) -> bool:
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _write_json_if_changed(path: Path, payload: Any) -> bool:
    return _write_text_if_changed(path, json.dumps(payload, indent=2) + "\n")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _emu(value: Any, default: float = 0.0) -> float:
    try:
        return float(value) / EMU_PER_IN
    except (TypeError, ValueError):
        return default


def _round_in(value: float) -> float:
    return round(float(value), 3)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _slide_number(path: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", path)
    return int(match.group(1)) if match else 999999


def _iter_pptx_paths(inputs: list[str], *, recursive: bool, glob_pattern: str) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            iterator = path.rglob(glob_pattern) if recursive else path.glob(glob_pattern)
            paths.extend(item.resolve() for item in iterator if item.suffix.lower() == ".pptx")
        elif path.exists() and path.suffix.lower() == ".pptx":
            paths.append(path.resolve())
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in sorted(paths, key=lambda item: str(item)):
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def _read_xml(zf: zipfile.ZipFile, path: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(path))
    except (KeyError, ET.ParseError):
        return None


def _presentation_size(zf: zipfile.ZipFile) -> dict[str, float]:
    root = _read_xml(zf, "ppt/presentation.xml")
    if root is None:
        return {"width": 13.333, "height": 7.5}
    node = root.find("p:sldSz", NS)
    if node is None:
        return {"width": 13.333, "height": 7.5}
    return {
        "width": _round_in(_emu(node.get("cx"), 13.333)),
        "height": _round_in(_emu(node.get("cy"), 7.5)),
    }


def _shape_geometry(node: ET.Element, shape_kind: str) -> dict[str, float]:
    if shape_kind == "graphic_frame":
        xfrm = node.find("p:xfrm", NS)
    else:
        xfrm = node.find("p:spPr/a:xfrm", NS)
    if xfrm is None:
        return {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    return {
        "x": _round_in(_emu(off.get("x") if off is not None else None)),
        "y": _round_in(_emu(off.get("y") if off is not None else None)),
        "w": _round_in(_emu(ext.get("cx") if ext is not None else None)),
        "h": _round_in(_emu(ext.get("cy") if ext is not None else None)),
    }


def _shape_name(node: ET.Element, shape_kind: str) -> str:
    if shape_kind == "graphic_frame":
        prop = node.find("p:nvGraphicFramePr/p:cNvPr", NS)
    elif shape_kind == "picture":
        prop = node.find("p:nvPicPr/p:cNvPr", NS)
    else:
        prop = node.find("p:nvSpPr/p:cNvPr", NS)
    return str(prop.get("name") or "") if prop is not None else ""


def _placeholder_type(node: ET.Element) -> str:
    ph = node.find("p:nvSpPr/p:nvPr/p:ph", NS)
    return str(ph.get("type") or "") if ph is not None else ""


def _shape_text(node: ET.Element) -> str:
    parts = [str(text_node.text or "").strip() for text_node in node.findall(".//a:t", NS)]
    return " ".join(part for part in parts if part)


def _font_sizes(node: ET.Element) -> list[float]:
    sizes: list[float] = []
    for run in node.findall(".//a:rPr", NS) + node.findall(".//a:defRPr", NS):
        raw = run.get("sz")
        if raw is None:
            continue
        try:
            size = float(raw) / 100.0
        except ValueError:
            continue
        if 1 <= size <= 120:
            sizes.append(round(size, 1))
    return sizes


def _first_color(node: ET.Element | None) -> str:
    if node is None:
        return ""
    srgb = node.find(".//a:srgbClr", NS)
    if srgb is not None and srgb.get("val"):
        return "#" + str(srgb.get("val")).upper()
    scheme = node.find(".//a:schemeClr", NS)
    if scheme is not None and scheme.get("val"):
        return "scheme:" + str(scheme.get("val"))
    return ""


def _fill_color(node: ET.Element) -> str:
    return _first_color(node.find("p:spPr/a:solidFill", NS))


def _line_color(node: ET.Element) -> str:
    return _first_color(node.find("p:spPr/a:ln/a:solidFill", NS))


def _text_colors(node: ET.Element) -> list[str]:
    colors: list[str] = []
    for run in node.findall(".//a:rPr", NS):
        color = _first_color(run.find("a:solidFill", NS))
        if color:
            colors.append(color)
    return colors


def _preset_geometry(node: ET.Element) -> str:
    geom = node.find("p:spPr/a:prstGeom", NS)
    return str(geom.get("prst") or "") if geom is not None else ""


def _has_descendant(node: ET.Element, local_name: str) -> bool:
    return any(_local_name(child.tag) == local_name for child in node.iter())


def _slide_records(root: ET.Element) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for node in root.findall(".//p:sp", NS):
        text = _shape_text(node)
        records.append(
            {
                "kind": "text_shape" if text else "shape",
                "name": _shape_name(node, "shape"),
                "placeholder": _placeholder_type(node),
                "geometry": _shape_geometry(node, "shape"),
                "text": text,
                "font_sizes": _font_sizes(node),
                "fill_color": _fill_color(node),
                "line_color": _line_color(node),
                "text_colors": _text_colors(node),
                "preset_geometry": _preset_geometry(node),
            }
        )
    for node in root.findall(".//p:pic", NS):
        records.append(
            {
                "kind": "picture",
                "name": _shape_name(node, "picture"),
                "geometry": _shape_geometry(node, "picture"),
            }
        )
    for node in root.findall(".//p:graphicFrame", NS):
        kind = "table" if _has_descendant(node, "tbl") else "chart" if _has_descendant(node, "chart") else "graphic_frame"
        records.append(
            {
                "kind": kind,
                "name": _shape_name(node, "graphic_frame"),
                "geometry": _shape_geometry(node, "graphic_frame"),
            }
        )
    return records


def _is_horizontal_rule(record: dict[str, Any], slide_w: float) -> bool:
    geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    w = float(geom.get("w") or 0)
    h = float(geom.get("h") or 0)
    preset = str(record.get("preset_geometry") or "").lower()
    if preset == "line" and w >= slide_w * 0.18 and h <= 0.08:
        return True
    return w >= slide_w * 0.18 and 0 <= h <= 0.08 and (record.get("fill_color") or record.get("line_color"))


def _is_vertical_rail(record: dict[str, Any], slide_h: float) -> bool:
    geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
    return (
        float(geom.get("w") or 0) <= 0.12
        and float(geom.get("h") or 0) >= slide_h * 0.22
        and float(geom.get("x") or 99) <= 0.9
        and bool(record.get("fill_color") or record.get("line_color"))
    )


def _infer_slide_header_variant(
    records: list[dict[str, Any]],
    *,
    slide_w: float,
    slide_h: float,
    title: dict[str, Any] | None,
) -> str:
    top_rules = []
    mid_title_rules = []
    bottom_rules = []
    short_top_rules = []
    left_rails = []
    title_y = float((title or {}).get("geometry", {}).get("y") or 0)
    title_h = float((title or {}).get("geometry", {}).get("h") or 0)
    title_bottom = title_y + title_h
    for record in records:
        geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
        x = float(geom.get("x") or 0)
        y = float(geom.get("y") or 0)
        w = float(geom.get("w") or 0)
        if _is_vertical_rail(record, slide_h):
            left_rails.append(record)
        if not _is_horizontal_rule(record, slide_w):
            continue
        if y < 0.28:
            top_rules.append(record)
        elif y >= slide_h - 0.75:
            bottom_rules.append(record)
        elif title and title_bottom - 0.08 <= y <= title_bottom + 0.38:
            mid_title_rules.append(record)
        if y < 1.4 and x <= 1.2 and w <= slide_w * 0.42:
            short_top_rules.append(record)

    if left_rails:
        return "side-rail"
    if top_rules and bottom_rules:
        return "top-bottom-rule"
    if short_top_rules:
        return "left-accent"
    if mid_title_rules:
        return "title-rule"
    if top_rules:
        return "split-rule" if any(float(item.get("geometry", {}).get("w") or 0) < slide_w * 0.72 for item in top_rules) else "top-bottom-rule"
    return "plain"


def _title_candidate(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for record in records:
        text = str(record.get("text") or "").strip()
        if not text:
            continue
        geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
        y = float(geom.get("y") or 0)
        placeholder = str(record.get("placeholder") or "").lower()
        sizes = [float(size) for size in record.get("font_sizes") or []]
        max_size = max(sizes) if sizes else 0.0
        score = 0.0
        if placeholder in {"title", "ctrtitle", "subTitle".lower()}:
            score += 100
        if y <= 1.6:
            score += 20
        score += max_size
        if len(text) > 160:
            score -= 20
        if score >= 20:
            candidates.append((score, record))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _footer_records(records: list[dict[str, Any]], slide_h: float) -> list[dict[str, Any]]:
    footers: list[dict[str, Any]] = []
    for record in records:
        text = str(record.get("text") or "").strip()
        placeholder = str(record.get("placeholder") or "").lower()
        geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else {}
        y = float(geom.get("y") or 0)
        h = float(geom.get("h") or 0)
        if not text:
            continue
        if placeholder in {"ftr", "dt", "sldnum"} or y + h >= slide_h - 0.72:
            footers.append(record)
    return footers


def _safe_min(values: list[float]) -> float | None:
    return round(min(values), 1) if values else None


def _safe_median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 1)


def _common(counter: Counter[str], limit: int = 8) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def _inspect_deck(path: Path, *, max_slides: int | None = None) -> dict[str, Any]:
    deck: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "sha256": _file_sha256(path),
        "size_bytes": path.stat().st_size,
        "slide_count": 0,
        "slide_size_inches": {"width": 13.333, "height": 7.5},
        "slides": [],
        "summary": {},
    }
    color_counter: Counter[str] = Counter()
    header_counter: Counter[str] = Counter()
    footer_mode_counter: Counter[str] = Counter()
    title_sizes: list[float] = []
    body_sizes: list[float] = []
    footer_sizes: list[float] = []
    image_count = 0
    table_count = 0
    chart_count = 0
    source_footer_count = 0
    page_number_count = 0

    with zipfile.ZipFile(path) as zf:
        deck["slide_size_inches"] = _presentation_size(zf)
        slide_w = float(deck["slide_size_inches"]["width"])
        slide_h = float(deck["slide_size_inches"]["height"])
        slide_paths = sorted(
            [name for name in zf.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name)],
            key=_slide_number,
        )
        if max_slides is not None and max_slides > 0:
            slide_paths = slide_paths[:max_slides]
        for index, slide_path in enumerate(slide_paths, start=1):
            root = _read_xml(zf, slide_path)
            if root is None:
                continue
            records = _slide_records(root)
            title = _title_candidate(records)
            header_variant = _infer_slide_header_variant(
                records,
                slide_w=slide_w,
                slide_h=slide_h,
                title=title,
            )
            header_counter[header_variant] += 1
            footers = _footer_records(records, slide_h)
            footer_text = " ".join(str(item.get("text") or "") for item in footers)
            source_footer = bool(SOURCE_RE.search(footer_text))
            page_number = any(PAGE_NUMBER_RE.match(str(item.get("text") or "")) for item in footers)
            source_footer_count += int(source_footer)
            page_number_count += int(page_number)
            footer_mode_counter["source-line" if source_footer else "standard" if footers else "none"] += 1

            title_text = str(title.get("text") or "") if title else ""
            title_font_sizes = [float(item) for item in (title.get("font_sizes") if title else []) or []]
            title_sizes.extend(title_font_sizes)
            for record in records:
                for color_key in ("fill_color", "line_color"):
                    color = str(record.get(color_key) or "").strip()
                    if color:
                        color_counter[color] += 1
                for color in record.get("text_colors") or []:
                    if color:
                        color_counter[str(color)] += 1
                if record is not title and record.get("text"):
                    body_sizes.extend(float(item) for item in record.get("font_sizes") or [])
            for record in footers:
                footer_sizes.extend(float(item) for item in record.get("font_sizes") or [])
            image_count += sum(1 for record in records if record.get("kind") == "picture")
            table_count += sum(1 for record in records if record.get("kind") == "table")
            chart_count += sum(1 for record in records if record.get("kind") == "chart")
            deck["slides"].append(
                {
                    "index": index,
                    "title": title_text[:180],
                    "title_geometry": title.get("geometry") if title else {},
                    "header_variant_signal": header_variant,
                    "footer_text_present": bool(footers),
                    "source_footer_signal": source_footer,
                    "page_number_signal": page_number,
                    "picture_count": sum(1 for record in records if record.get("kind") == "picture"),
                    "table_count": sum(1 for record in records if record.get("kind") == "table"),
                    "chart_count": sum(1 for record in records if record.get("kind") == "chart"),
                    "text_shape_count": sum(1 for record in records if record.get("text")),
                    "title_font_min_pt": _safe_min(title_font_sizes),
                    "title_font_median_pt": _safe_median(title_font_sizes),
                }
            )

    deck["slide_count"] = len(deck["slides"])
    deck["summary"] = {
        "observed_header_variants": _common(header_counter),
        "footer_modes": _common(footer_mode_counter),
        "dominant_colors": _common(color_counter),
        "source_footer_slide_count": source_footer_count,
        "page_number_slide_count": page_number_count,
        "picture_count": image_count,
        "table_count": table_count,
        "chart_count": chart_count,
        "title_font_median_pt": _safe_median(title_sizes),
        "title_font_min_pt": _safe_min(title_sizes),
        "body_font_median_pt": _safe_median(body_sizes),
        "body_font_min_pt": _safe_min(body_sizes),
        "footer_font_median_pt": _safe_median(footer_sizes),
        "footer_font_min_pt": _safe_min(footer_sizes),
    }
    return deck


def _aggregate_decks(decks: list[dict[str, Any]]) -> dict[str, Any]:
    header_counter: Counter[str] = Counter()
    footer_counter: Counter[str] = Counter()
    color_counter: Counter[str] = Counter()
    title_sizes: list[float] = []
    body_sizes: list[float] = []
    footer_sizes: list[float] = []
    for deck in decks:
        summary = deck.get("summary") if isinstance(deck.get("summary"), dict) else {}
        for item in summary.get("observed_header_variants") or []:
            header_counter[str(item.get("value"))] += int(item.get("count") or 0)
        for item in summary.get("footer_modes") or []:
            footer_counter[str(item.get("value"))] += int(item.get("count") or 0)
        for item in summary.get("dominant_colors") or []:
            color_counter[str(item.get("value"))] += int(item.get("count") or 0)
        for key, target in (
            ("title_font_median_pt", title_sizes),
            ("body_font_median_pt", body_sizes),
            ("footer_font_median_pt", footer_sizes),
        ):
            value = summary.get(key)
            if isinstance(value, (int, float)):
                target.append(float(value))
    slide_count = sum(int(deck.get("slide_count") or 0) for deck in decks)
    return {
        "deck_count": len(decks),
        "slide_count": slide_count,
        "observed_header_variants": _common(header_counter),
        "footer_modes": _common(footer_counter),
        "dominant_colors": _common(color_counter, limit=12),
        "picture_count": sum(int((deck.get("summary") or {}).get("picture_count") or 0) for deck in decks),
        "table_count": sum(int((deck.get("summary") or {}).get("table_count") or 0) for deck in decks),
        "chart_count": sum(int((deck.get("summary") or {}).get("chart_count") or 0) for deck in decks),
        "source_footer_slide_count": sum(int((deck.get("summary") or {}).get("source_footer_slide_count") or 0) for deck in decks),
        "page_number_slide_count": sum(int((deck.get("summary") or {}).get("page_number_slide_count") or 0) for deck in decks),
        "title_font_median_pt": _safe_median(title_sizes),
        "body_font_median_pt": _safe_median(body_sizes),
        "footer_font_median_pt": _safe_median(footer_sizes),
    }


def _pool_from_observed(observed: list[dict[str, Any]]) -> list[str]:
    pool: list[str] = []
    for item in observed:
        value = str(item.get("value") or "").strip()
        if value in SUPPORTED_HEADER_VARIANTS and value not in pool:
            pool.append(value)
    if not pool:
        pool = ["title-rule", "plain"]
    elif len(pool) == 1:
        pool.append("plain" if pool[0] != "plain" else "title-rule")
    return pool[:6]


def _palette_from_aggregate(aggregate: dict[str, Any]) -> dict[str, Any]:
    colors = [
        str(item.get("value") or "").strip()
        for item in aggregate.get("dominant_colors") or []
        if str(item.get("value") or "").startswith("#")
    ]
    return {
        "dominant_colors": colors[:8],
        "accent_candidates": colors[:3],
        "notes": "Extracted from fills, lines, and explicit run colors; theme scheme colors may need manual mapping.",
    }


def _style_preview_plan(
    *,
    style_seed: str,
    style_preset: str,
    header_variants: list[str],
) -> dict[str, Any]:
    variants = [
        variant
        for variant in header_variants
        if variant in SUPPORTED_HEADER_VARIANTS
    ]
    if not variants:
        variants = ["title-rule", "plain"]
    outdir = f"decks/pptx-style-preview-{style_seed}"
    base_command = [
        "python3",
        "scripts/build_header_variant_gallery.py",
        "--outdir",
        outdir,
        "--presets",
        style_preset,
        "--variants",
        *variants,
    ]
    return {
        "kind": "header_variant_gallery",
        "presets": [style_preset],
        "variants": variants,
        "outdir": outdir,
        "commands": {
            "fast": [*base_command, "--build", "--qa"],
            "rendered": [*base_command, "--build", "--qa", "--render"],
        },
    }


def _design_brief_fragment(
    *,
    inputs: list[Path],
    aggregate: dict[str, Any],
    user_label: str,
) -> dict[str, Any]:
    seed_basis = "|".join([user_label] + [f"{path.name}:{_file_sha256(path)[:12]}" for path in inputs])
    style_seed = f"import-{hashlib.sha256(seed_basis.encode('utf-8')).hexdigest()[:10]}"
    slide_count = max(1, int(aggregate.get("slide_count") or 0))
    source_ratio = float(aggregate.get("source_footer_slide_count") or 0) / slide_count
    page_ratio = float(aggregate.get("page_number_slide_count") or 0) / slide_count
    table_count = int(aggregate.get("table_count") or 0)
    chart_count = int(aggregate.get("chart_count") or 0)
    picture_count = int(aggregate.get("picture_count") or 0)
    header_pool = _pool_from_observed(aggregate.get("observed_header_variants") or [])
    footer_pool = ["source-line", "standard"] if source_ratio >= 0.2 else ["standard", "none"]
    style_preset = "lab-report" if source_ratio >= 0.2 or table_count or chart_count else "executive-clinical"
    figure_treatment = "table-first" if table_count > chart_count and table_count >= picture_count else "figure-first" if picture_count or chart_count else "stats-strip"
    body_size = aggregate.get("body_font_median_pt")
    title_size = aggregate.get("title_font_median_pt")
    footer_size = aggregate.get("footer_font_median_pt")
    preview = _style_preview_plan(
        style_seed=style_seed,
        style_preset=style_preset,
        header_variants=header_pool,
    )
    return {
        "style_system": {
            "style_preset": style_preset,
            "style_seed": style_seed,
            "style_mix_matrix": {
                "header_variant_pool": header_pool,
                "title_layout_pool": ["lab-plate", "light-atlas"] if style_preset == "lab-report" else ["split-hero", "masthead"],
                "section_motif_pool": ["plain", "rail-dots"],
                "chart_treatment_pool": ["standard", "facts-below", "facts-right", "minimal"],
                "figure_table_treatment_pool": [figure_treatment, "image-sidebar" if figure_treatment != "image-sidebar" else "figure-first"],
                "footer_pool": footer_pool,
                "mix_rule": "Use extracted template signals as a bounded pool; rotate only small chrome treatments by style_seed.",
                "do_not_mix": ["Do not clone arbitrary template XML or unsupported fonts/colors."],
            },
        },
        "deck_style": {
            "style_seed": style_seed,
            "header_mode": "lab-clean" if style_preset == "lab-report" else "bar",
            "header_variant": "auto",
            "header_variants": header_pool,
            "footer_mode": "source-line" if source_ratio >= 0.2 else "standard",
            "footer_page_numbers": page_ratio >= 0.2 or source_ratio >= 0.2,
            "figure_table_treatment": figure_treatment,
        },
        "design_modulation": {
            "change_intensity": "subtle",
            "base_preset_fit": "preset plus treatment changes",
            "accent_strategy": "Map extracted accent candidates into preset tokens rather than inline per-slide colors.",
            "density_strategy": "Preserve observed report density only when text sizes stay above readability floors.",
            "whitespace_strategy": "Use extracted rules/footers as chrome; do not preserve accidental empty regions.",
            "container_strategy": "Prefer figure/table-first layouts when imported decks contain evidence objects.",
            "figure_table_treatment": figure_treatment,
            "avoid": ["template cloning", "unsupported inline geometry", "footer text below readability floor"],
        },
        "readability_contract": {
            "min_title_pt": max(24, round(float(title_size or 24), 1)),
            "min_body_pt": max(12, round(float(body_size or 12), 1)),
            "min_caption_pt": 7.5,
            "chart_label_min_pt": 7,
            "footer_min_pt": max(7.0, min(8.5, round(float(footer_size or 7.5), 1))),
            "footer_reserved_inches": 0.32,
            "max_title_lines": 2,
            "max_slide_text_lines": 10,
            "max_slide_words": 95,
            "max_slide_chars": 640,
            "whitespace_rule": "Convert extracted sparse areas into deliberate image, table, or callout zones.",
            "figure_crop_rule": "Generated or imported figures should use tight exterior bounds before deck assembly.",
        },
        "speed_contract": {
            "renderer": "pptxgenjs",
            "first_pass": "render-free QA is acceptable while applying extracted style signals",
            "render_policy": "render only after source style and layout choices are stable",
            "asset_policy": "stage assets through asset_plan; do not mutate the imported PPTX",
        },
        "style_observation": {
            "source_decks": [str(path) for path in inputs],
            "observed_header_variants": aggregate.get("observed_header_variants") or [],
            "footer_modes": aggregate.get("footer_modes") or [],
            "palette": _palette_from_aggregate(aggregate),
            "preview": preview,
            "counts": {
                "slides": slide_count,
                "pictures": picture_count,
                "tables": table_count,
                "charts": chart_count,
            },
        },
    }


def _format_count_list(items: Any) -> str:
    if not isinstance(items, list):
        return "none"
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = str(item.get("value") or "").strip()
        count = item.get("count")
        if value:
            parts.append(f"{value}:{count}")
    return ", ".join(parts) if parts else "none"


def _format_command(command: Any) -> str:
    if not isinstance(command, list):
        return ""
    return " ".join(str(part) for part in command if str(part).strip())


def _markdown_report(payload: dict[str, Any]) -> str:
    aggregate = payload.get("aggregate") if isinstance(payload.get("aggregate"), dict) else {}
    fragment = payload.get("design_brief_fragment") if isinstance(payload.get("design_brief_fragment"), dict) else {}
    style_system = fragment.get("style_system") if isinstance(fragment.get("style_system"), dict) else {}
    deck_style = fragment.get("deck_style") if isinstance(fragment.get("deck_style"), dict) else {}
    observation = fragment.get("style_observation") if isinstance(fragment.get("style_observation"), dict) else {}
    preview = observation.get("preview") if isinstance(observation.get("preview"), dict) else {}
    preview_commands = preview.get("commands") if isinstance(preview.get("commands"), dict) else {}
    lines = [
        "# PPTX Style Extraction",
        "",
        f"- Decks: {aggregate.get('deck_count', 0)}",
        f"- Slides inspected: {aggregate.get('slide_count', 0)}",
        f"- Recommended preset: `{style_system.get('style_preset', 'unknown')}`",
        f"- Style seed: `{style_system.get('style_seed', 'none')}`",
        f"- Header mode: `{deck_style.get('header_mode', 'none')}`",
        f"- Header variants: `{', '.join(deck_style.get('header_variants') or []) or 'none'}`",
        f"- Footer mode: `{deck_style.get('footer_mode', 'none')}`",
        f"- Page numbers: `{bool(deck_style.get('footer_page_numbers'))}`",
        "",
        "## Observed Signals",
        "",
        f"- Header variants: `{_format_count_list(aggregate.get('observed_header_variants'))}`",
        f"- Footer modes: `{_format_count_list(aggregate.get('footer_modes'))}`",
        f"- Pictures / tables / charts: `{aggregate.get('picture_count', 0)} / {aggregate.get('table_count', 0)} / {aggregate.get('chart_count', 0)}`",
        f"- Source-footer slides: `{aggregate.get('source_footer_slide_count', 0)}`",
        "",
        "## Preview Commands",
        "",
        f"- Fast gallery: `{_format_command(preview_commands.get('fast')) or 'none'}`",
        f"- Rendered gallery: `{_format_command(preview_commands.get('rendered')) or 'none'}`",
        "",
        "## Palette Candidates",
        "",
    ]
    for item in aggregate.get("dominant_colors") or []:
        lines.append(f"- `{item.get('value')}` ({item.get('count')})")
    lines.extend(
        [
            "",
            "## Decks",
            "",
        ]
    )
    for deck in payload.get("decks") or []:
        summary = deck.get("summary") if isinstance(deck.get("summary"), dict) else {}
        lines.extend(
            [
                f"### {deck.get('name')}",
                "",
                f"- Slides: {deck.get('slide_count', 0)}",
                f"- SHA-256: `{str(deck.get('sha256') or '')[:16]}...`",
                f"- Header signals: `{_format_count_list(summary.get('observed_header_variants'))}`",
                f"- Footer signals: `{_format_count_list(summary.get('footer_modes'))}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="PPTX file or directory; repeat for a corpus")
    parser.add_argument("--recursive", action="store_true", help="Search input directories recursively")
    parser.add_argument("--glob", default="*.pptx", help="Directory glob for PPTX corpus inputs")
    parser.add_argument("--max-slides", type=int, default=0, help="Optional max slides per input deck")
    parser.add_argument("--report", help="Write full JSON report")
    parser.add_argument("--markdown-report", help="Write Markdown summary report")
    parser.add_argument("--design-brief-fragment", help="Write only the reusable design_brief.json fragment")
    parser.add_argument("--label", default="pptx-style-import", help="Stable label included in the generated style seed")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    inputs = _iter_pptx_paths(args.input, recursive=bool(args.recursive), glob_pattern=str(args.glob or "*.pptx"))
    if not inputs:
        print("No PPTX inputs found.", file=sys.stderr)
        return 2
    max_slides = int(args.max_slides or 0) or None
    decks = [_inspect_deck(path, max_slides=max_slides) for path in inputs]
    aggregate = _aggregate_decks(decks)
    fragment = _design_brief_fragment(inputs=inputs, aggregate=aggregate, user_label=str(args.label or "pptx-style-import"))
    observation = fragment.get("style_observation") if isinstance(fragment.get("style_observation"), dict) else {}
    preview = observation.get("preview") if isinstance(observation.get("preview"), dict) else {}
    payload = {
        "schema_version": 1,
        "generated_by": "scripts/extract_pptx_style.py",
        "inputs": [
            {
                "path": str(path),
                "sha256": _file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in inputs
        ],
        "aggregate": aggregate,
        "design_brief_fragment": fragment,
        "preview_commands": preview.get("commands") if isinstance(preview.get("commands"), dict) else {},
        "decks": decks,
    }
    if args.report:
        _write_json_if_changed(Path(args.report).expanduser(), payload)
    if args.markdown_report:
        _write_text_if_changed(Path(args.markdown_report).expanduser(), _markdown_report(payload))
    if args.design_brief_fragment:
        _write_json_if_changed(Path(args.design_brief_fragment).expanduser(), fragment)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
