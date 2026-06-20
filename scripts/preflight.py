#!/usr/bin/env python3
"""Fast pre-build linter for presentation-skill outlines.

Runs static checks on outline.json in <1s to catch common authoring errors
before the slow build+render cycle (~60s) in build_workspace.py --qa.

CLI:
  python3 scripts/preflight.py --outline outline.json [--strict]

Exit codes:
  0 - no issues
  1 - warnings only (non-blocking)
  2 - errors present (blocking when --strict)
  3 - malformed outline JSON (always blocking)

Output: JSON to stdout with {"issues": [...], "error_count": N, "warning_count": N};
human-readable summary to stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageChops
except Exception:  # pragma: no cover - optional dependency error path
    Image = None  # type: ignore[assignment]
    ImageChops = None  # type: ignore[assignment]

# Numeric KPI regex for stats.facts[].value. Mirrors design_rules_qa /
# layout_lint but expressed per the preflight spec. Accepts optional
# leading sign ("-" or unicode "−"), digits/dot/comma/percent, and an
# optional short unit suffix.
_STATS_NUMERIC_VALUE_RE = re.compile(
    r"^[$€£¥\-−]?[\d,./\s%]+[a-zA-Z%°×x$€£¥]{0,4}$"
)

_VALID_FONT_PAIRS = {
    "system_clean_v1",
    "editorial_serif_v1",
    "clean_modern_v1",
}

_STYLE_ENUM_VALUES = {
    "visual_density": {"low", "medium", "high"},
    "header_mode": {"bar", "stack", "eyebrow", "lab-clean", "lab-card"},
    "header_variant": {
        "auto",
        "left-accent",
        "split-rule",
        "title-rule",
        "side-rail",
        "top-bottom-rule",
        "plain",
    },
    "title_layout": {
        "split-hero",
        "lab-plate",
        "command-center",
        "poster",
        "masthead",
        "light-atlas",
    },
    "title_motif": {"orbit", "network", "editorial", "none"},
    "section_motif": {"rail-dots", "numbered-tabs", "plain", "none"},
    "timeline_mode": {"rail-cards", "staggered", "open-events", "bands", "chapter-spread"},
    "matrix_mode": {"cards", "open-quadrants"},
    "stats_mode": {"tiles", "feature-left", "policy-bands"},
    "cards_mode": {"feature-left", "staggered-row"},
    "chart_treatment": {"standard", "facts-below", "facts-right", "minimal"},
    "footer_mode": {"standard", "source-line", "none"},
    "summary_callout_mode": {"default", "lab-box"},
    "figure_table_treatment": {"figure-first", "table-first", "stats-strip", "image-sidebar"},
}

_ROOT_STYLE_ENUM_KEYS = set(_STYLE_ENUM_VALUES)
_SLIDE_STYLE_ENUM_KEYS = {
    "header_mode",
    "header_variant",
    "title_layout",
    "timeline_mode",
    "matrix_mode",
    "stats_mode",
    "cards_mode",
    "chart_treatment",
    "footer_mode",
    "summary_callout_mode",
    "figure_table_treatment",
}

_ASSET_ALIAS_PREFIXES = ("asset:", "image:", "background:", "chart:", "table:", "generated:")
_REACT_ICON_PREFIXES = ("fa6:", "fa:", "bi:", "bs:", "md:", "lu:")

_ASSET_FIELDS_SCALAR = (
    "hero_image",
    "image",
    "generated_image",
    "diagram",
    "mermaid_source",
    "logo",
    "chart_data",
    "table_data",
    "table",
)
_ASSET_FIELDS_ARRAY = ("icons",)
_MERMAID_EDGE_RE = re.compile(
    r"^\s*([A-Za-z0-9_]+)(?:\s*(?:\[[^\]]+\]|\([^)]+\)|\{[^}]+\}))?\s*[-=.]+>\s*"
    r"([A-Za-z0-9_]+)"
)
_MERMAID_NODE_RE = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(?:\[|\(|\{)")

_ALIAS_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("images", ("asset", "image")),
    ("backgrounds", ("asset", "background")),
    ("charts", ("asset", "chart")),
    ("tables", ("asset", "table")),
    ("generated_images", ("asset", "image", "generated")),
)

_PLACEHOLDER_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("xxx", re.compile(r"\bx{3,}\b", re.IGNORECASE)),
    ("lorem/ipsum", re.compile(r"\b(?:lorem|ipsum)\b", re.IGNORECASE)),
    ("todo/tbd", re.compile(r"\b(?:TODO|TBD)\b", re.IGNORECASE)),
    (
        "bracketed placeholder",
        re.compile(r"\[\s*(?:insert|placeholder|todo|tbd)\b[^\]]*\]", re.IGNORECASE),
    ),
    (
        "angle placeholder",
        re.compile(r"<\s*(?:insert|placeholder|todo|tbd)\b[^>]*>", re.IGNORECASE),
    ),
    ("powerpoint prompt", re.compile(r"\bclick\s+to\s+add\b", re.IGNORECASE)),
    (
        "layout prompt",
        re.compile(r"\bthis\s+(?:page|slide)\b.{0,80}\blayout\b", re.IGNORECASE | re.DOTALL),
    ),
)
_PLACEHOLDER_TEXT_SKIP_KEYS = {
    "attribution_file",
    "background_image",
    "chart_data",
    "diagram",
    "generated_image",
    "hero_image",
    "image",
    "logo",
    "mermaid",
    "mermaid_source",
    "path",
    "src",
    "table_data",
    "url",
}
_PLACEHOLDER_TEXT_SKIP_SUBTREES = {"icons"}


def _make_issue(
    slide_index: int | None,
    rule: str,
    severity: str,
    message: str,
    suggested_fix: str = "",
) -> dict[str, Any]:
    return {
        "slide_index": slide_index if slide_index is not None else -1,
        "rule": rule,
        "severity": severity,
        "message": message,
        "suggested_fix": suggested_fix,
    }


class _PreflightContext:
    def __init__(self) -> None:
        self.json_objects: dict[Path, dict[str, Any] | None] = {}
        self.declared_aliases: dict[Path, set[str]] = {}


def _is_numeric_stats_value(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return True  # empty handled upstream
    if not any(ch.isdigit() for ch in stripped):
        return False
    return bool(_STATS_NUMERIC_VALUE_RE.match(stripped))


def _check_asset_path(
    value: str,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> bool:
    """Return True if path resolves locally (or is aliased), False if missing.

    Aliased prefixes are considered OK only when declared in the staged
    manifest or the pre-stage `asset_plan.json`.
    """
    if not value or not isinstance(value, str):
        return True
    for prefix in _ASSET_ALIAS_PREFIXES:
        if value.startswith(prefix):
            return _is_declared_alias(value, outline_parent, context)
    p = Path(value)
    if p.is_absolute():
        return p.exists()
    # relative: try outline_parent, outline_parent/assets, outline_parent/assets/staged
    candidates = [
        outline_parent / p,
        outline_parent / "assets" / p,
        outline_parent / "assets" / "staged" / p,
    ]
    return any(c.exists() for c in candidates)


def _normalize_alias(value: str) -> str:
    return str(value or "").strip().lower()


def _safe_alias_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_")
    return safe.lower()


def _declared_aliases_from_entries(entries: Any, prefixes: tuple[str, ...]) -> set[str]:
    aliases: set[str] = set()
    if not isinstance(entries, list):
        return aliases
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = _safe_alias_name(str(entry.get("name") or ""))
        if not name:
            continue
        aliases.update(f"{prefix}:{name}" for prefix in prefixes)
    return aliases


def _alias_entry_label(section: str, index: int, raw_name: Any, normalized_name: str) -> str:
    explicit = str(raw_name or "").strip()
    if explicit:
        return f"{section}[{index}] name {explicit!r} -> {normalized_name!r}"
    return f"{section}[{index}]"


def _check_declared_alias_conflicts(
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for path in (
        outline_parent / "assets" / "staged" / "staged_manifest.json",
        outline_parent / "asset_plan.json",
    ):
        if not path.exists():
            continue
        payload = _load_json_object(path, context)
        if not payload:
            continue
        seen_aliases: dict[str, str] = {}
        for section, prefixes in _ALIAS_SECTIONS:
            entries = payload.get(section)
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                name = _safe_alias_name(str(entry.get("name") or ""))
                if not name:
                    continue
                label = _alias_entry_label(section, index, entry.get("name"), name)
                for prefix in prefixes:
                    alias = f"{prefix}:{name}"
                    previous = seen_aliases.get(alias)
                    if previous is not None:
                        issues.append(
                            _make_issue(
                                None,
                                "staged_alias_ambiguous",
                                "error",
                                f"{path.name} declares duplicate staged alias {alias!r}: {previous} conflicts with {label}.",
                                (
                                    "Rename one asset in asset_plan.json and rerun asset_stage.py so staged aliases "
                                    "resolve deterministically."
                                ),
                            )
                        )
                    else:
                        seen_aliases[alias] = label
    return issues


def _declared_asset_aliases(
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> set[str]:
    cache_key = outline_parent.resolve()
    if context is not None and cache_key in context.declared_aliases:
        return context.declared_aliases[cache_key]
    aliases: set[str] = set()
    for path in (
        outline_parent / "assets" / "staged" / "staged_manifest.json",
        outline_parent / "asset_plan.json",
    ):
        if not path.exists():
            continue
        payload = _load_json_object(path, context)
        if not payload:
            continue
        for section, prefixes in _ALIAS_SECTIONS:
            aliases.update(_declared_aliases_from_entries(payload.get(section), prefixes))
    if context is not None:
        context.declared_aliases[cache_key] = aliases
    return aliases


def _is_asset_alias(value: Any) -> bool:
    return isinstance(value, str) and _normalize_alias(value).startswith(_ASSET_ALIAS_PREFIXES)


def _is_declared_alias(
    value: str,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> bool:
    normalized = _normalize_alias(value)
    if not normalized.startswith(_ASSET_ALIAS_PREFIXES):
        return True
    return normalized in _declared_asset_aliases(outline_parent, context)


def _check_alias_reference(
    value: Any,
    idx: int,
    field: str,
    outline_parent: Path,
    *,
    severity: str = "warning",
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    if not _is_asset_alias(value):
        return []
    if _is_declared_alias(str(value), outline_parent, context):
        return []
    return [
        _make_issue(
            idx,
            "staged_alias_not_declared",
            severity,
            f"{field} references undeclared staged alias {value!r}.",
            (
                "Add a matching named entry to asset_plan.json and run asset_stage.py, "
                "or fix the alias spelling in outline.json."
            ),
        )
    ]


def _resolve_asset_path(value: str, outline_parent: Path) -> Path | None:
    if not value or not isinstance(value, str):
        return None
    if value.startswith(_ASSET_ALIAS_PREFIXES):
        return None
    p = Path(value)
    if p.is_absolute():
        return p if p.exists() else None
    candidates = [
        outline_parent / p,
        outline_parent / "assets" / p,
        outline_parent / "assets" / "staged" / p,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _count_mermaid_nodes(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    nodes: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        lowered = line.lower()
        if (
            not line
            or line.startswith("%")
            or line.startswith("%%")
            or ":::" in line
            or lowered.startswith(("flowchart", "graph", "sequencediagram", "subgraph", "end"))
            or lowered.startswith(("classdef ", "class ", "style ", "linkstyle "))
        ):
            continue
        edge = _MERMAID_EDGE_RE.match(line)
        if edge:
            nodes.update(edge.groups())
            continue
        node = _MERMAID_NODE_RE.match(line)
        if node:
            nodes.add(node.group(1))
    return len(nodes)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_json_object(
    path: Path,
    context: _PreflightContext | None = None,
) -> dict[str, Any] | None:
    if context is None:
        return _read_json_object(path)
    key = path.resolve()
    if key in context.json_objects:
        return context.json_objects[key]
    result = _read_json_object(key)
    if context is not None:
        context.json_objects[key] = result
    return result


def _chart_alias_name(value: str) -> str:
    normalized = _normalize_alias(value)
    for prefix in ("chart:", "asset:"):
        if normalized.startswith(prefix):
            return normalized.split(":", 1)[1].strip()
    return ""


def _resolve_manifest_entry_path(raw: Any, manifest_path: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path if path.exists() else None
    candidates = [
        manifest_path.parent / path,
        manifest_path.parent / "assets" / path,
        manifest_path.parent / "assets" / "staged" / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _chart_payload_for_ref(
    value: Any,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    direct_path = _resolve_asset_path(value, outline_parent)
    if direct_path is not None:
        return _load_json_object(direct_path, context)

    alias_name = _chart_alias_name(value)
    if not alias_name:
        return None
    for manifest_path in (
        outline_parent / "assets" / "staged" / "staged_manifest.json",
        outline_parent / "asset_plan.json",
    ):
        payload = _load_json_object(manifest_path, context)
        if not payload:
            continue
        charts = payload.get("charts")
        if not isinstance(charts, list):
            continue
        for entry in charts:
            if not isinstance(entry, dict):
                continue
            name = _safe_alias_name(str(entry.get("name") or ""))
            if name != alias_name:
                continue
            chart_path = _resolve_manifest_entry_path(entry.get("path"), manifest_path)
            if chart_path is not None:
                return _load_json_object(chart_path, context)
            if "series" in entry or "values" in entry or "categories" in entry or "labels" in entry:
                return dict(entry)
    return None


def _table_alias_name(value: str) -> str:
    normalized = _normalize_alias(value)
    for prefix in ("table:", "asset:"):
        if normalized.startswith(prefix):
            return normalized.split(":", 1)[1].strip()
    return ""


def _table_payload_for_ref(
    value: Any,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    direct_path = _resolve_asset_path(value, outline_parent)
    if direct_path is not None:
        return _load_json_object(direct_path, context)

    alias_name = _table_alias_name(value)
    if not alias_name:
        return None
    for manifest_path in (
        outline_parent / "assets" / "staged" / "staged_manifest.json",
        outline_parent / "asset_plan.json",
    ):
        payload = _load_json_object(manifest_path, context)
        if not payload:
            continue
        tables = payload.get("tables")
        if not isinstance(tables, list):
            continue
        for entry in tables:
            if not isinstance(entry, dict):
                continue
            name = _safe_alias_name(str(entry.get("name") or ""))
            if name != alias_name:
                continue
            table_path = _resolve_manifest_entry_path(entry.get("path"), manifest_path)
            if table_path is not None:
                return _load_json_object(table_path, context)
            if "headers" in entry or "rows" in entry:
                return dict(entry)
    return None


def _image_alias_parts(value: str) -> tuple[str, tuple[str, ...]]:
    normalized = _normalize_alias(value)
    if normalized.startswith("image:"):
        return normalized.split(":", 1)[1].strip(), ("images", "generated_images")
    if normalized.startswith("generated:"):
        return normalized.split(":", 1)[1].strip(), ("generated_images",)
    if normalized.startswith("asset:"):
        return normalized.split(":", 1)[1].strip(), ("images", "generated_images", "backgrounds")
    if normalized.startswith("background:"):
        return normalized.split(":", 1)[1].strip(), ("backgrounds",)
    return "", ()


def _image_path_for_ref(
    value: Any,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    direct_path = _resolve_asset_path(value, outline_parent)
    if direct_path is not None:
        return direct_path

    alias_name, sections = _image_alias_parts(value)
    if not alias_name:
        return None
    for manifest_path in (
        outline_parent / "assets" / "staged" / "staged_manifest.json",
        outline_parent / "asset_plan.json",
    ):
        payload = _load_json_object(manifest_path, context)
        if not payload:
            continue
        for section in sections:
            entries = payload.get(section)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = _safe_alias_name(str(entry.get("name") or ""))
                if name != alias_name:
                    continue
                image_path = _resolve_manifest_entry_path(entry.get("path"), manifest_path)
                if image_path is not None:
                    return image_path
    return None


def _check_icon_path(value: str, outline_parent: Path) -> bool:
    """Return True if an icon string resolves under the workspace.

    Mirrors `_resolve_icon_path` in build_deck.py:
      - absolute path exists;
      - relative path with extension in assets/icons/ or outline_parent;
      - bare name <name>.{png,svg,jpg,jpeg} under assets/icons/.
    """
    if not value or not isinstance(value, str):
        return True
    raw = value.strip()
    if not raw:
        return True
    if raw.startswith(_REACT_ICON_PREFIXES):
        return True
    icons_dir = outline_parent / "assets" / "icons"
    if raw.startswith("/"):
        return Path(raw).exists()
    p = Path(raw)
    has_ext = p.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg"}
    if has_ext or "/" in raw or "\\" in raw:
        return (icons_dir / p).exists() or (outline_parent / p).exists()
    for ext in (".png", ".svg", ".jpg", ".jpeg"):
        if (icons_dir / f"{raw}{ext}").exists():
            return True
    return False


def _chart_series_items(chart: dict[str, Any]) -> list[dict[str, Any]]:
    series = chart.get("series")
    if isinstance(series, list) and series:
        return [item for item in series if isinstance(item, dict)]
    values = chart.get("values")
    if isinstance(values, list) and values:
        labels = chart.get("categories") if isinstance(chart.get("categories"), list) else chart.get("labels")
        item: dict[str, Any] = {"values": values}
        if isinstance(labels, list):
            item["labels"] = labels
        return [item]
    return []


def _chart_category_labels(chart: dict[str, Any], series_items: list[dict[str, Any]]) -> list[str]:
    categories = chart.get("categories") if isinstance(chart.get("categories"), list) else chart.get("labels")
    if isinstance(categories, list) and categories:
        return [str(item) for item in categories]
    longest: list[str] = []
    for item in series_items:
        labels = item.get("labels")
        if isinstance(labels, list) and len(labels) > len(longest):
            longest = [str(label) for label in labels]
    return longest


def _check_chart_density(chart: dict[str, Any], idx: int, label: str = "chart") -> list[dict[str, Any]]:
    series_items = _chart_series_items(chart)
    if not series_items:
        return []
    category_labels = _chart_category_labels(chart, series_items)
    category_count = len(category_labels)
    series_count = len(series_items)
    point_count = 0
    for item in series_items:
        values = item.get("values")
        if isinstance(values, list):
            point_count += len(values)
    longest_label = max((len(label_text.strip()) for label_text in category_labels), default=0)
    avg_label = (
        sum(len(label_text.strip()) for label_text in category_labels) / category_count
        if category_count
        else 0.0
    )

    issues: list[dict[str, Any]] = []
    if category_count > 10:
        issues.append(
            _make_issue(
                idx,
                "chart_too_many_categories",
                "warning",
                f"{label} has {category_count} categories; native chart axis labels usually become cramped past ~10.",
                "Split into two chart slides, aggregate low-value categories, or export a purpose-built figure.",
            )
        )
    if series_count > 4:
        issues.append(
            _make_issue(
                idx,
                "chart_too_many_series",
                "warning",
                f"{label} has {series_count} series; legends and colors become hard to read past ~4 series.",
                "Show fewer series, facet into multiple slides, or convert the comparison into a small-multiple figure.",
            )
        )
    if point_count > 36 or (category_count and series_count * category_count > 36):
        issues.append(
            _make_issue(
                idx,
                "chart_point_budget_high",
                "warning",
                f"{label} plots {point_count} values across {series_count} series and {category_count} categories.",
                "Keep editable slide charts compact; move dense exploratory results into a generated figure or appendix table.",
            )
        )
    if longest_label > 24 or avg_label > 16:
        issues.append(
            _make_issue(
                idx,
                "chart_category_labels_long",
                "warning",
                f"{label} category labels are long (max {longest_label} chars, average {avg_label:.1f}).",
                "Shorten category labels, rotate to a figure export, or use a table/sidebar for full labels.",
            )
        )
    return issues


def _check_chart(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    chart = slide.get("chart")
    assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
    chart_ref = (
        slide.get("chart")
        if isinstance(slide.get("chart"), str)
        else assets.get("chart_data") or assets.get("chart")
    )
    issues.extend(
        _check_alias_reference(
            chart_ref,
            idx,
            "chart/assets.chart_data",
            outline_parent,
            severity="error",
            context=context,
        )
    )
    if not isinstance(chart, dict):
        if isinstance(chart_ref, str) and chart_ref.strip():
            payload = _chart_payload_for_ref(chart_ref, outline_parent, context)
            if payload is not None:
                issues.extend(_check_chart_density(payload, idx, label=f"staged chart {chart_ref!r}"))
            return issues
        issues.append(
            _make_issue(
                idx,
                "chart_missing",
                "error",
                "Slide has variant: chart but no inline `chart` object or staged chart alias.",
                "Add a `chart` object with series/categories or reference staged chart JSON with `assets.chart_data`.",
            )
        )
        return issues

    series = chart.get("series")
    categories = chart.get("categories") if isinstance(chart.get("categories"), list) else chart.get("labels")
    flat_values = chart.get("values")
    if (
        (not isinstance(series, list) or len(series) < 1)
        and isinstance(categories, list)
        and len(categories) > 0
        and isinstance(flat_values, list)
        and len(flat_values) > 0
    ):
        if len(categories) != len(flat_values):
            issues.append(
                _make_issue(
                    idx,
                    "chart_categories_length_mismatch",
                    "error",
                    f"chart categories length ({len(categories)}) != chart values length ({len(flat_values)}).",
                    "Use one category per value.",
                )
            )
        issues.extend(_check_chart_density(chart, idx))
        return issues
    if not isinstance(series, list) or len(series) < 1:
        issues.append(
            _make_issue(
                idx,
                "chart_series_missing",
                "error",
                "`chart.series` must be a non-empty array.",
                "Add at least one series: [{\"name\": \"...\", \"values\": [...]}].",
            )
        )
        return issues

    categories = chart.get("categories")
    has_top_categories = isinstance(categories, list) and len(categories) > 0

    for s_idx, s in enumerate(series):
        if not isinstance(s, dict):
            issues.append(
                _make_issue(
                    idx,
                    "chart_series_malformed",
                    "error",
                    f"series[{s_idx}] is not an object.",
                    "Each series must be an object with `values`.",
                )
            )
            continue
        values = s.get("values")
        if not isinstance(values, list) or len(values) < 1:
            issues.append(
                _make_issue(
                    idx,
                    "chart_series_values_missing",
                    "error",
                    f"series[{s_idx}] has no `values` array.",
                    "Add a `values` array of numbers to every series.",
                )
            )
            continue

        labels = s.get("labels")
        has_series_labels = isinstance(labels, list) and len(labels) > 0

        if not has_top_categories and not has_series_labels:
            issues.append(
                _make_issue(
                    idx,
                    "chart_categories_missing",
                    "error",
                    f"series[{s_idx}] has no category source: neither chart.categories nor series.labels.",
                    "Add `categories` at the chart level or `labels` inside the series.",
                )
            )
            continue

        if has_top_categories and len(categories) != len(values):
            issues.append(
                _make_issue(
                    idx,
                    "chart_categories_length_mismatch",
                    "error",
                    f"chart.categories length ({len(categories)}) != series[{s_idx}].values length ({len(values)}).",
                    "Make categories and values the same length.",
                )
            )
        if has_series_labels and len(labels) != len(values):
            issues.append(
                _make_issue(
                    idx,
                    "chart_labels_length_mismatch",
                    "error",
                    f"series[{s_idx}].labels length ({len(labels)}) != values length ({len(values)}).",
                    "Make labels and values the same length.",
                )
            )
    issues.extend(_check_chart_density(chart, idx))
    return issues


def _check_stats(slide: dict[str, Any], idx: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    facts = slide.get("facts")
    if not isinstance(facts, list):
        return issues
    for f_idx, fact in enumerate(facts):
        if not isinstance(fact, dict):
            continue
        value = fact.get("value")
        if value is None:
            continue
        value_str = str(value)
        if not _is_numeric_stats_value(value_str):
            issues.append(
                _make_issue(
                    idx,
                    "stats_value_non_numeric",
                    "warning",
                    f"facts[{f_idx}].value = {value_str!r} is not numeric; stats KPIs render badly with adjectives.",
                    "Use a real number + unit (e.g., \"14%\", \"2.1pt\") or switch variant to cards-3.",
                )
            )
    return issues


def _check_style_enum_value(
    *,
    payload: dict[str, Any],
    key: str,
    slide_index: int | None,
    path_label: str,
) -> list[dict[str, Any]]:
    if key not in payload:
        return []
    value = payload.get(key)
    if not isinstance(value, str):
        return [
            _make_issue(
                slide_index,
                "style_treatment_invalid_type",
                "error",
                f"{path_label}.{key} must be a string when present.",
                "Use one of the documented treatment names, or remove the field.",
            )
        ]
    text = value.strip()
    if not text:
        return [
            _make_issue(
                slide_index,
                "style_treatment_empty",
                "warning",
                f"{path_label}.{key} is empty and will be ignored.",
                "Remove the empty treatment field or choose a supported value.",
            )
        ]
    allowed = _STYLE_ENUM_VALUES[key]
    if text.lower() not in allowed:
        return [
            _make_issue(
                slide_index,
                "style_treatment_unsupported",
                "error",
                f"{path_label}.{key} = {text!r} is unsupported.",
                f"Set {path_label}.{key} to one of: {', '.join(sorted(allowed))}.",
            )
        ]
    return []


def _check_header_variants(
    payload: dict[str, Any],
    *,
    slide_index: int | None,
    path_label: str,
) -> list[dict[str, Any]]:
    if "header_variants" not in payload:
        return []
    value = payload.get("header_variants")
    if not isinstance(value, list):
        return [
            _make_issue(
                slide_index,
                "style_treatment_invalid_type",
                "error",
                f"{path_label}.header_variants must be a list when present.",
                "Use an array of supported header variants, or remove the field.",
            )
        ]
    issues: list[dict[str, Any]] = []
    allowed = _STYLE_ENUM_VALUES["header_variant"]
    for item_idx, item in enumerate(value):
        item_path = f"{path_label}.header_variants[{item_idx}]"
        if not isinstance(item, str):
            issues.append(
                _make_issue(
                    slide_index,
                    "style_treatment_invalid_type",
                    "error",
                    f"{item_path} must be a string.",
                    "Use a supported header variant name.",
                )
            )
            continue
        text = item.strip()
        if not text:
            issues.append(
                _make_issue(
                    slide_index,
                    "style_treatment_empty",
                    "warning",
                    f"{item_path} is empty and will be ignored.",
                    "Remove the empty array entry.",
                )
            )
            continue
        if text.lower() not in allowed:
            issues.append(
                _make_issue(
                    slide_index,
                    "style_treatment_unsupported",
                    "error",
                    f"{item_path} = {text!r} is unsupported.",
                    f"Use one of: {', '.join(sorted(allowed))}.",
                )
            )
    return issues


def _check_style_treatments(
    payload: Any,
    *,
    slide_index: int | None,
    path_label: str,
    keys: set[str],
) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return [
            _make_issue(
                slide_index,
                "style_treatment_invalid_type",
                "error",
                f"{path_label} must be an object when present.",
                "Use an object with supported renderer treatment fields.",
            )
        ]
    issues: list[dict[str, Any]] = []
    for key in sorted(keys):
        issues.extend(
            _check_style_enum_value(
                payload=payload,
                key=key,
                slide_index=slide_index,
                path_label=path_label,
            )
        )
    issues.extend(_check_header_variants(payload, slide_index=slide_index, path_label=path_label))
    return issues


def _check_flow_complexity(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
) -> list[dict[str, Any]]:
    variant = (slide.get("variant") or "").strip().lower()
    visual_intent = (slide.get("visual_intent") or "").strip().lower()
    assets = slide.get("assets") or {}
    if not isinstance(assets, dict):
        assets = {}
    mermaid_source = assets.get("mermaid_source") or assets.get("mermaid")
    diagram = assets.get("diagram")
    is_flow = variant == "flow" or visual_intent == "flow" or bool(mermaid_source or diagram)
    if not is_flow:
        return []

    issues: list[dict[str, Any]] = []
    if variant == "flow" and not (mermaid_source or diagram):
        issues.append(
            _make_issue(
                idx,
                "flow_optional_without_diagram",
                "info",
                "variant: flow has no diagram/mermaid asset, so the renderer will fall back to a text slide.",
                "Use flow only when the process itself matters; otherwise switch to split/table/comparison.",
            )
        )
        return issues

    if isinstance(mermaid_source, str):
        mermaid_path = _resolve_asset_path(mermaid_source, outline_parent)
        if mermaid_path:
            node_count = _count_mermaid_nodes(mermaid_path)
            if node_count > 4:
                issues.append(
                    _make_issue(
                        idx,
                        "flow_many_nodes",
                        "info",
                        f"Mermaid flow has {node_count} nodes. The fallback renderer caps rows at four boxes and balances rows.",
                        "Inspect the rendered slide. If the diagram feels generic or crowded, split it, summarize stages, or use a table/timeline.",
                    )
                )
    return issues


def _table_payload(slide: dict[str, Any]) -> dict[str, Any]:
    table = slide.get("table")
    nested = table if isinstance(table, dict) else {}
    return {
        "headers": slide.get("headers", nested.get("headers")),
        "rows": slide.get("rows", nested.get("rows")),
    }


def _is_table_alias(value: Any) -> bool:
    return isinstance(value, str) and value.strip().startswith(("table:", "asset:"))


def _has_table_alias(slide: dict[str, Any]) -> bool:
    assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
    if _is_table_alias(slide.get("table")) or _is_table_alias(slide.get("table_data")):
        return True
    if _is_table_alias(assets.get("table")) or _is_table_alias(assets.get("table_data")):
        return True
    tables = slide.get("tables") or slide.get("table_groups") or assets.get("tables")
    return isinstance(tables, list) and any(_is_table_alias(item) for item in tables)


def _check_table_aliases(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}

    def check_ref(field: str, value: Any) -> None:
        issues.extend(
            _check_alias_reference(
                value,
                idx,
                field,
                outline_parent,
                severity="error",
                context=context,
            )
        )
        payload = _table_payload_for_ref(value, outline_parent, context)
        if payload is not None:
            issues.extend(_check_table_payload(payload, idx, f"staged table {field} {value!r}"))

    for field, value in (
        ("table", slide.get("table")),
        ("table_data", slide.get("table_data")),
        ("assets.table", assets.get("table")),
        ("assets.table_data", assets.get("table_data")),
    ):
        check_ref(field, value)
    tables = slide.get("tables") or slide.get("table_groups") or assets.get("tables")
    if isinstance(tables, list):
        for table_idx, value in enumerate(tables):
            check_ref(f"tables[{table_idx}]", value)
    return issues


def _table_cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("text", "value", "label", "title", "body"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return re.sub(r"\s+", " ", text).strip()
        return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False, sort_keys=True)).strip()
    return re.sub(r"\s+", " ", str(value)).strip()


def _is_source_footer_reference_slide(slide: dict[str, Any]) -> bool:
    metadata = slide.get("source_footer_compaction")
    return (
        isinstance(metadata, dict)
        and str(metadata.get("generated_by") or "") == "scripts/compact_source_footers.py"
    )


def _check_table_text_lengths(
    *,
    headers: list[Any],
    rows: list[Any],
    idx: int,
    label: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    header_texts = [_table_cell_text(header) for header in headers]
    longest_header = max((len(text) for text in header_texts), default=0)
    if longest_header > _TABLE_HEADER_TEXT_MAX_CHARS:
        header_index, header_text = max(
            enumerate(header_texts),
            key=lambda item: len(item[1]),
        )
        issues.append(
            _make_issue(
                idx,
                "table_header_text_long",
                "warning",
                (
                    f"{label} header {header_index} is {len(header_text)} chars; "
                    f"editable table headers are hard to read past ~{_TABLE_HEADER_TEXT_MAX_CHARS} chars."
                ),
                "Shorten the header, abbreviate with a caption/footnote, or split the table.",
            )
        )

    body_cells: list[tuple[int, int, str]] = []
    for row_idx, row in enumerate(rows):
        if not isinstance(row, list):
            continue
        for col_idx, cell in enumerate(row):
            text = _table_cell_text(cell)
            if text:
                body_cells.append((row_idx, col_idx, text))
    if not body_cells:
        return issues

    longest_row, longest_col, longest_text = max(
        body_cells,
        key=lambda item: len(item[2]),
    )
    avg_len = sum(len(text) for _, _, text in body_cells) / len(body_cells)
    long_body_cells = [
        (row_idx, col_idx, text)
        for row_idx, col_idx, text in body_cells
        if len(text) > _TABLE_CELL_TEXT_MAX_CHARS
    ]
    if long_body_cells or avg_len > _TABLE_AVG_CELL_TEXT_MAX_CHARS:
        reasons: list[str] = []
        if long_body_cells:
            reasons.append(
                f"{len(long_body_cells)} body cell(s) exceed {_TABLE_CELL_TEXT_MAX_CHARS} chars"
            )
        if avg_len > _TABLE_AVG_CELL_TEXT_MAX_CHARS:
            reasons.append(
                f"average non-empty body cell is {avg_len:.1f} chars "
                f"(>{_TABLE_AVG_CELL_TEXT_MAX_CHARS})"
            )
        issues.append(
            _make_issue(
                idx,
                "table_cell_text_long",
                "warning",
                (
                    f"{label} has sentence-length editable table text: "
                    + "; ".join(reasons)
                    + f". Longest cell is rows[{longest_row}][{longest_col}] "
                    f"at {len(longest_text)} chars."
                ),
                (
                    "Keep editable table cells to labels, values, and short calls; "
                    "move explanations to caption/footnotes/sidebar or split into a figure-plus-summary table."
                ),
            )
        )
    return issues


def _check_table_payload(
    table: dict[str, Any],
    idx: int,
    label: str = "table",
    *,
    allow_long_text: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    headers = table.get("headers")
    rows = table.get("rows")
    if not isinstance(headers, list) or not headers:
        issues.append(
            _make_issue(
                idx,
                "table_missing_headers",
                "error",
                f"{label} requires a non-empty `headers` array.",
                'Add `"headers": ["Col A", "Col B", "Col C"]`.',
            )
        )
        return issues
    if not isinstance(rows, list) or not rows:
        issues.append(
            _make_issue(
                idx,
                "table_missing_rows",
                "error",
                f"{label} requires a non-empty `rows` array.",
                'Add `"rows": [["cell", "cell", "cell"], ...]`.',
            )
        )
        return issues
    col_count = len(headers)
    for row_idx, row in enumerate(rows):
        if not isinstance(row, list):
            issues.append(
                _make_issue(
                    idx,
                    "table_row_malformed",
                    "error",
                    f"{label} rows[{row_idx}] is not a list.",
                    "Every row must be an array of cell values.",
                )
            )
            continue
        if len(row) != col_count:
            issues.append(
                _make_issue(
                    idx,
                    "table_row_width_mismatch",
                    "error",
                    f"{label} rows[{row_idx}] has {len(row)} cells but headers "
                    f"defines {col_count} columns.",
                    "Pad or trim the row to match the header count.",
                )
            )
    if not allow_long_text:
        issues.extend(_check_table_text_lengths(headers=headers, rows=rows, idx=idx, label=label))
    if len(rows) > 10:
        issues.append(
            _make_issue(
                idx,
                "table_too_many_rows",
                "warning",
                f"{label} has {len(rows)} rows; readability degrades past "
                "~8 rows at typical slide sizes.",
                "Consider splitting across two slides, or promoting the "
                "most-important rows and moving details to an appendix.",
            )
        )
    if col_count > 6:
        issues.append(
            _make_issue(
                idx,
                "table_too_many_columns",
                "warning",
                f"{label} has {col_count} columns; editable tables become hard "
                "to read past ~6 columns on a 16:9 slide.",
                "Split the table, remove low-value columns, or convert the "
                "wide readout into a chart plus compact summary table.",
            )
        )
    cell_count = len(rows) * col_count
    if cell_count > 48 or (col_count >= 6 and len(rows) > 7):
        issues.append(
            _make_issue(
                idx,
                "table_cell_budget_high",
                "warning",
                f"{label} has {len(rows)} rows x {col_count} columns "
                f"({cell_count} editable cells), which is likely to force "
                "small text or cramped gutters.",
                "Summarize to the decision-critical rows, split across slides, "
                "or generate a figure/table pair from the source data.",
            )
        )
    return issues


def _has_caption_or_sources(slide: dict[str, Any]) -> bool:
    if str(slide.get("caption") or slide.get("figure_caption") or slide.get("footer") or "").strip():
        return True
    return _has_footer_provenance_items(slide)


def _has_footer_provenance_items(slide: dict[str, Any]) -> bool:
    for key in ("sources", "refs", "references"):
        values = slide.get(key)
        if isinstance(values, list) and any(_source_text(item) for item in values):
            return True
    return False


def _has_footer_chrome(slide: dict[str, Any]) -> bool:
    if str(slide.get("footer") or "").strip():
        return True
    if _has_footer_provenance_items(slide):
        return True
    if slide.get("page_number") is not None:
        return True
    footer_mode = str(slide.get("footer_mode") or "").strip().lower()
    return footer_mode == "source-line"


_EVIDENCE_ANCHOR_VARIANTS = {
    "chart",
    "table",
    "lab-run-results",
    "image-sidebar",
    "scientific-figure",
    "flow",
    "stats",
    "kpi-hero",
    "comparison-2col",
    "matrix",
    "timeline",
}


def _nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).strip() for item in value)


def _slide_requests_evidence_anchor(slide: dict[str, Any]) -> bool:
    slide_intent = str(slide.get("slide_intent") or "").strip().lower()
    visual_intent = str(slide.get("visual_intent") or "").strip().lower()
    if slide_intent == "evidence":
        return True
    if visual_intent in {"data", "chart", "table", "figure"}:
        return True
    return _nonempty_list(slide.get("evidence_needs")) or _nonempty_list(slide.get("evidence_objects"))


def _slide_has_evidence_anchor(slide: dict[str, Any]) -> bool:
    variant = str(slide.get("variant") or "").strip().lower()
    if variant in _EVIDENCE_ANCHOR_VARIANTS:
        return True
    assets = slide.get("assets")
    if not isinstance(assets, dict):
        assets = {}
    anchor_fields = (
        "hero_image",
        "image",
        "generated_image",
        "diagram",
        "mermaid_source",
        "chart_data",
        "chart",
        "table_data",
        "table",
        "tables",
        "figures",
    )
    if any(assets.get(field) for field in anchor_fields):
        return True
    if any(slide.get(field) for field in ("chart", "table", "tables", "figures", "facts", "stats", "evidence")):
        return True
    return False


def _check_evidence_anchor(slide: dict[str, Any], idx: int) -> list[dict[str, Any]]:
    slide_type = str(slide.get("type") or "content").strip().lower()
    if slide_type not in {"content", "text"}:
        return []
    if not _slide_requests_evidence_anchor(slide):
        return []
    if _slide_has_evidence_anchor(slide):
        return []
    variant = str(slide.get("variant") or "standard").strip() or "standard"
    return [
        _make_issue(
            idx,
            "evidence_slide_missing_anchor",
            "warning",
            (
                "Slide declares evidence/data intent but has no chart, table, figure, "
                f"image, diagram, stats, KPI, or structured comparison anchor (variant={variant!r})."
            ),
            (
                "Use an evidence-first variant such as chart, table, lab-run-results, "
                "image-sidebar, scientific-figure, stats, comparison-2col, or flow; "
                "or add assets.chart_data/table_data/hero_image/figures from the artifact plan."
            ),
        )
    ]


def _check_variant_required(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    variant = (slide.get("variant") or "").strip().lower()

    if variant in ("cards-2", "cards-3"):
        expected = 2 if variant == "cards-2" else 3
        cards = slide.get("cards")
        if not isinstance(cards, list):
            issues.append(
                _make_issue(
                    idx,
                    "cards_missing",
                    "error",
                    f"variant: {variant} requires a `cards` array with {expected} entries.",
                    f"Add a `cards` array of length {expected}.",
                )
            )
        elif len(cards) != expected:
            issues.append(
                _make_issue(
                    idx,
                    "cards_count_wrong",
                    "error",
                    f"variant: {variant} expects {expected} cards, got {len(cards)}.",
                    f"Adjust `cards` length to {expected}.",
                )
            )

    elif variant == "timeline":
        milestones = slide.get("milestones")
        if not isinstance(milestones, list) or len(milestones) < 2:
            issues.append(
                _make_issue(
                    idx,
                    "timeline_milestones_missing",
                    "error",
                    "variant: timeline requires a `milestones` array with >= 2 entries.",
                    "Add at least 2 `milestones` objects.",
                )
            )

    elif variant == "matrix":
        quadrants = slide.get("quadrants")
        if not isinstance(quadrants, list) or len(quadrants) != 4:
            issues.append(
                _make_issue(
                    idx,
                    "matrix_quadrants_wrong",
                    "error",
                    f"variant: matrix requires exactly 4 `quadrants` (got {len(quadrants) if isinstance(quadrants, list) else 'none'}).",
                    "Provide exactly 4 quadrant objects.",
                )
            )

    elif variant == "split":
        highlights = slide.get("highlights")
        body = slide.get("body")
        bullets = slide.get("bullets")
        empty_highlights = not highlights
        empty_body = not body and not bullets
        if empty_highlights and empty_body:
            issues.append(
                _make_issue(
                    idx,
                    "split_empty",
                    "warning",
                    "variant: split has neither `highlights` nor `body`/`bullets`.",
                    "Add content to at least one side (highlights or body/bullets).",
                )
            )

    elif variant == "kpi-hero":
        value = slide.get("value")
        label = slide.get("label")
        if not (isinstance(value, (str, int, float)) and str(value).strip()):
            issues.append(
                _make_issue(
                    idx,
                    "kpi_hero_missing_value",
                    "error",
                    "variant: kpi-hero requires a non-empty `value` string.",
                    'Add `"value": "42%"` or similar numeric+unit headline.',
                )
            )
        elif isinstance(value, str) and len(value.strip()) > 12:
            issues.append(
                _make_issue(
                    idx,
                    "kpi_hero_value_too_long",
                    "warning",
                    f"kpi-hero value {value.strip()!r} is {len(value.strip())} chars; "
                    "the autosize drops font to 60pt at 9+ chars and may still overflow wider slides.",
                    "Shorten the headline (e.g., '$1.2M' instead of '$1,200,000') and move "
                    "precision to `context` or `label`.",
                )
            )
        if not (isinstance(label, str) and label.strip()):
            issues.append(
                _make_issue(
                    idx,
                    "kpi_hero_missing_label",
                    "error",
                    "variant: kpi-hero requires a non-empty `label` string.",
                    "Add `label` naming what the value measures.",
                )
            )

    elif variant == "image-sidebar":
        assets = slide.get("assets") or {}
        has_image = bool(
            isinstance(assets, dict)
            and (assets.get("hero_image") or assets.get("image"))
        )
        if not has_image:
            issues.append(
                _make_issue(
                    idx,
                    "image_sidebar_missing_image",
                    "error",
                    "variant: image-sidebar works best with an image; "
                    "without assets.hero_image it falls back to a "
                    "sidebar-only layout.",
                    'Stage an image and reference it as '
                    '`"assets": {"hero_image": "assets/<name>.png"}`.',
                )
            )
        sections = slide.get("sidebar_sections")
        if not isinstance(sections, list) or not sections:
            issues.append(
                _make_issue(
                    idx,
                    "image_sidebar_missing_sections",
                    "error",
                    "variant: image-sidebar requires sidebar_sections "
                    "(2-4 labeled sections).",
                    'Add `"sidebar_sections": [{"title": "...", "body": "..."}]`.',
                )
            )
        if not _has_caption_or_sources(slide):
            issues.append(
                _make_issue(
                    idx,
                    "image_sidebar_missing_caption_or_sources",
                    "warning",
                    "image-sidebar should include caption, footer, sources, or refs for figure/image provenance.",
                    "Add concise figure provenance, run metadata, or source text so the image-sidebar slide is auditable.",
                )
            )

    elif variant == "scientific-figure":
        assets = slide.get("assets") or {}
        figures = slide.get("figures")
        asset_figures = assets.get("figures") if isinstance(assets, dict) else None
        has_figures = (
            isinstance(figures, list) and bool(figures)
        ) or (
            isinstance(asset_figures, list) and bool(asset_figures)
        )
        if not has_figures:
            issues.append(
                _make_issue(
                    idx,
                    "scientific_figure_missing_figures",
                    "error",
                    "variant: scientific-figure requires figures or assets.figures.",
                    'Add `"figures": [{"path": "assets/panel_a.png", "label": "A"}]`.',
                )
            )
        if not _has_caption_or_sources(slide):
            issues.append(
                _make_issue(
                    idx,
                    "scientific_figure_missing_caption_or_sources",
                    "warning",
                    "scientific-figure should include caption, figure_caption, footer, sources, or refs.",
                    "Add concise provenance/readout text so the figure is auditable.",
                )
            )

    elif variant == "generated-image":
        assets = slide.get("assets") or {}
        image_generation = slide.get("image_generation")
        has_image = bool(
            isinstance(assets, dict)
            and (assets.get("hero_image") or assets.get("generated_image") or assets.get("image"))
        )
        if not has_image:
            issues.append(
                _make_issue(
                    idx,
                    "generated_image_missing_asset",
                    "error",
                    "variant: generated-image requires assets.hero_image or assets.generated_image.",
                    'Reference the generated asset with `"assets": {"hero_image": "generated:<name>"}`.',
                )
            )
        if not isinstance(image_generation, dict):
            issues.append(
                _make_issue(
                    idx,
                    "generated_image_missing_metadata",
                    "warning",
                    "variant: generated-image should include an image_generation object with prompt/model/purpose.",
                    "Add image_generation.prompt, image_generation.model, and image_generation.purpose so the slide is auditable.",
                )
            )
        elif not str(image_generation.get("prompt") or "").strip():
            issues.append(
                _make_issue(
                    idx,
                    "generated_image_prompt_missing",
                    "warning",
                    "image_generation.prompt is empty.",
                    "Store the prompt or a concise prompt summary with the slide.",
                )
            )

    elif variant == "chart":
        if not _has_caption_or_sources(slide):
            issues.append(
                _make_issue(
                    idx,
                    "chart_missing_caption_or_sources",
                    "warning",
                    "Evidence charts should include caption, footer, sources, or refs.",
                    "Add compact chart provenance, source data, or run metadata so the chart is auditable.",
                )
            )

    elif variant == "table":
        issues.extend(_check_table_aliases(slide, idx, outline_parent, context))
        if not _has_table_alias(slide):
            issues.extend(
                _check_table_payload(
                    _table_payload(slide),
                    idx,
                    "variant: table",
                    allow_long_text=_is_source_footer_reference_slide(slide),
                )
            )
        if not _has_caption_or_sources(slide):
            issues.append(
                _make_issue(
                    idx,
                    "table_missing_caption_or_sources",
                    "warning",
                    "Evidence tables should include caption, footer, sources, or refs.",
                    "Add source/run metadata or a caption below the table.",
                )
            )

    elif variant == "lab-run-results":
        issues.extend(_check_table_aliases(slide, idx, outline_parent, context))
        tables = slide.get("tables") or slide.get("table_groups")
        if isinstance(tables, list) and tables:
            if len(tables) > 3:
                issues.append(
                    _make_issue(
                        idx,
                        "lab_run_too_many_tables",
                        "warning",
                        f"lab-run-results renders up to 3 table groups cleanly; got {len(tables)}.",
                        "Split extra tables to a follow-up slide or convert to appendix tables.",
                    )
                )
            for table_idx, table in enumerate(tables):
                if _is_table_alias(table):
                    continue
                if not isinstance(table, dict):
                    issues.append(
                        _make_issue(
                            idx,
                            "lab_run_table_malformed",
                            "error",
                            f"tables[{table_idx}] is not an object.",
                            "Each lab-run-results table must be an object with headers and rows.",
                        )
                    )
                    continue
                issues.extend(
                    _check_table_payload(table, idx, f"lab-run-results tables[{table_idx}]")
                )
        else:
            if not _has_table_alias(slide):
                issues.extend(_check_table_payload(_table_payload(slide), idx, "variant: lab-run-results"))
        if not _has_caption_or_sources(slide):
            issues.append(
                _make_issue(
                    idx,
                    "lab_run_missing_caption_or_sources",
                    "warning",
                    "lab-run-results should include caption, footer, sources, or refs for run/data provenance.",
                    "Add assay/run metadata, data source, or a compact footnote.",
                )
            )

    elif variant == "comparison-2col":
        left = slide.get("left")
        right = slide.get("right")
        if not isinstance(left, dict):
            issues.append(
                _make_issue(
                    idx,
                    "comparison_missing_left",
                    "error",
                    "variant: comparison-2col requires a `left` object with title + body.",
                    'Add `"left": {"title": "...", "body": "..."}`.',
                )
            )
        elif not (isinstance(left.get("title"), str) and left.get("title").strip()):
            issues.append(
                _make_issue(
                    idx,
                    "comparison_left_missing_title",
                    "warning",
                    "comparison-2col `left.title` is empty.",
                    "Add a clear left-column heading (e.g., 'Before', 'Hypothesis').",
                )
            )
        if not isinstance(right, dict):
            issues.append(
                _make_issue(
                    idx,
                    "comparison_missing_right",
                    "error",
                    "variant: comparison-2col requires a `right` object with title + body.",
                    'Add `"right": {"title": "...", "body": "..."}`.',
                )
            )
        elif not (isinstance(right.get("title"), str) and right.get("title").strip()):
            issues.append(
                _make_issue(
                    idx,
                    "comparison_right_missing_title",
                    "warning",
                    "comparison-2col `right.title` is empty.",
                    "Add a clear right-column heading (e.g., 'After', 'Result').",
                )
            )

    return issues


def _figure_specs(slide: dict[str, Any]) -> list[Any]:
    assets = slide.get("assets")
    if isinstance(slide.get("figures"), list):
        return slide.get("figures") or []
    if isinstance(assets, dict) and isinstance(assets.get("figures"), list):
        return assets.get("figures") or []
    return []


def _figure_path(spec: Any) -> str:
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        return str(spec.get("path") or spec.get("image") or "").strip()
    return ""


def _has_figure_caption(spec: Any) -> bool:
    return isinstance(spec, dict) and bool(str(spec.get("caption") or spec.get("note") or "").strip())


def _image_size(path: Path) -> tuple[int, int] | None:
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def _corner_background(img: Any) -> tuple[int, int, int, int]:
    rgba = img.convert("RGBA")
    width, height = rgba.size
    corners = [
        rgba.getpixel((0, 0)),
        rgba.getpixel((max(0, width - 1), 0)),
        rgba.getpixel((0, max(0, height - 1))),
        rgba.getpixel((max(0, width - 1), max(0, height - 1))),
    ]
    return tuple(sorted(values)[len(values) // 2] for values in zip(*corners))  # type: ignore[return-value]


def _image_exterior_whitespace(path: Path, *, tolerance: int = 12) -> dict[str, Any] | None:
    if Image is None or ImageChops is None:
        return None
    try:
        with Image.open(path) as raw:
            img = raw.convert("RGBA")
            if img.width <= 1 or img.height <= 1:
                return None
            bg = Image.new("RGBA", img.size, _corner_background(img))
            diff = ImageChops.difference(img, bg)
            mask = Image.new("L", img.size, 0)
            for channel in diff.split():
                thresholded = channel.point(lambda value: 255 if value > tolerance else 0)
                mask = ImageChops.lighter(mask, thresholded)
            bbox = mask.getbbox()
            if not bbox:
                return None
            left, top, right, bottom = bbox
            content_area = max(1, right - left) * max(1, bottom - top)
            total_area = img.width * img.height
            exterior_fraction = max(0.0, min(1.0, 1.0 - (content_area / total_area)))
            return {
                "size": (img.width, img.height),
                "bbox": bbox,
                "exterior_fraction": exterior_fraction,
            }
    except Exception:
        return None


def _looks_like_generated_figure(raw_path: str, resolved: Path) -> bool:
    text = f"{raw_path} {resolved.as_posix()}".lower()
    figure_terms = ("assets/figures", "/figures/", "figure", "plot", "chart", "graph", "readout", "panel")
    return any(term in text for term in figure_terms)


def _figure_whitespace_issue(
    *,
    raw_path: str,
    resolved: Path | None,
    idx: int,
    context: str,
    require_figure_like: bool = False,
) -> list[dict[str, Any]]:
    if resolved is None:
        return []
    if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return []
    if require_figure_like and not _looks_like_generated_figure(raw_path, resolved):
        return []
    report = _image_exterior_whitespace(resolved)
    if not report:
        return []
    exterior_fraction = float(report.get("exterior_fraction") or 0.0)
    if exterior_fraction < 0.45:
        return []
    bbox = report.get("bbox") or (0, 0, 0, 0)
    size = report.get("size") or (0, 0)
    return [
        _make_issue(
            idx,
            "figure_exterior_whitespace_high",
            "warning",
            (
                f"{context} appears to have {exterior_fraction:.0%} exterior blank area "
                f"(content bbox {bbox[2] - bbox[0]}x{bbox[3] - bbox[1]} px inside {size[0]}x{size[1]} px)."
            ),
            (
                "Export the figure with bbox_inches='tight' and small padding, "
                "or run scripts/trim_image_whitespace.py before inserting it."
            ),
        )
    ]


def _scientific_panel_geometry(slide: dict[str, Any], figure_count: int, has_panel_caption: bool) -> tuple[float, float]:
    """Approximate the pptxgenjs scientific-figure image box in inches."""
    slide_w = 10.0
    slide_h = 5.625
    margin_x = 0.50
    usable_w = slide_w - margin_x * 2
    gap = 0.30
    top_y = 1.08
    bottom_text = bool(slide.get("caption") or slide.get("figure_caption") or slide.get("interpretation") or slide.get("takeaway"))
    has_footer = _has_footer_chrome(slide)
    bottom_reserve = 0.62 if bottom_text else 0.18
    footer_reserve = 0.50 if has_footer else 0.12
    grid_h = slide_h - top_y - bottom_reserve - footer_reserve
    count = max(1, min(figure_count, 4))
    cols = 1 if count == 1 else 2
    rows = 1 if count <= 2 else 2
    panel_w = (usable_w - gap * (cols - 1)) / cols
    panel_h = (grid_h - gap * (rows - 1)) / rows
    title_h = 0.22
    fig_caption_h = 0.22 if has_panel_caption else 0.0
    image_h = max(0.1, panel_h - 0.12 - title_h - fig_caption_h - 0.08)
    image_w = max(0.1, panel_w - 0.12)
    return image_w, image_h


def _scientific_bottom_text_lines(slide: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in ("caption", "figure_caption", "interpretation", "takeaway"):
        _append_text_density_lines(slide.get(key), lines)
    return [line.strip() for line in lines if line.strip()]


def _check_scientific_bottom_text_readability(slide: dict[str, Any], idx: int) -> list[dict[str, Any]]:
    lines = _scientific_bottom_text_lines(slide)
    if not lines:
        return []
    words = sum(len(re.findall(r"\b[\w'-]+\b", line)) for line in lines)
    chars = sum(len(line) for line in lines)
    estimated_lines = sum(
        _estimate_text_lines(line, font_size_pt=8.2, width_in=8.7)
        for line in lines
    )
    if estimated_lines <= 2 and words <= 34 and chars <= 220:
        return []
    exceeded: list[str] = []
    if estimated_lines > 2:
        exceeded.append(f"~{estimated_lines} wrapped lines > 2")
    if words > 34:
        exceeded.append(f"{words} words > 34")
    if chars > 220:
        exceeded.append(f"{chars} chars > 220")
    return [
        _make_issue(
            idx,
            "scientific_figure_bottom_text_long",
            "warning",
            "scientific-figure bottom caption/interpretation is too dense for the fixed synthesis strip "
            f"({', '.join(exceeded)}).",
            (
                "Keep the bottom strip to a compact figure caption plus one interpretation sentence; "
                "move method detail to notes/refs, split the figure, or use image-sidebar for longer explanation."
            ),
        )
    ]


def _check_scientific_figure_readability(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    if (slide.get("variant") or "").strip().lower() != "scientific-figure":
        return []
    figures = _figure_specs(slide)
    if not figures:
        return []

    issues: list[dict[str, Any]] = []
    issues.extend(_check_scientific_bottom_text_readability(slide, idx))
    if len(figures) > 4:
        issues.append(
            _make_issue(
                idx,
                "scientific_figure_panel_count_exceeds_limit",
                "error",
                (
                    f"scientific-figure has {len(figures)} panels, but the renderer "
                    "can place at most 4 and will ignore extras."
                ),
                (
                    "Split the extra panels to a second scientific-figure slide, "
                    "combine them into one slide-ready composite figure, or make "
                    "the dominant plot an image-sidebar hero."
                ),
            )
        )
    if len(figures) >= 3:
        issues.append(
            _make_issue(
                idx,
                "scientific_figure_dense_grid",
                "warning",
                f"scientific-figure has {len(figures)} panels; detailed plots often become tiny in a 2x2 grid.",
                "Use one composite slide-ready figure, split into two slides, or make the primary plot an image-sidebar hero.",
            )
        )

    smallest: tuple[float, float, str] | None = None
    for spec in figures[:4]:
        raw_path = _figure_path(spec)
        resolved = _image_path_for_ref(raw_path, outline_parent, context)
        if resolved is None:
            continue
        issues.extend(
            _figure_whitespace_issue(
                raw_path=raw_path,
                resolved=resolved,
                idx=idx,
                context=f"scientific-figure panel {raw_path!r}",
            )
        )
        size = _image_size(resolved)
        if not size:
            continue
        img_w, img_h = size
        box_w, box_h = _scientific_panel_geometry(slide, len(figures), _has_figure_caption(spec))
        image_ratio = img_w / max(img_h, 1)
        box_ratio = box_w / max(box_h, 0.01)
        if image_ratio >= box_ratio:
            fit_w = box_w
            fit_h = box_w / image_ratio
        else:
            fit_h = box_h
            fit_w = box_h * image_ratio
        if smallest is None or (fit_w * fit_h) < (smallest[0] * smallest[1]):
            smallest = (fit_w, fit_h, raw_path)

    if smallest and (smallest[0] < 2.45 or smallest[1] < 1.35):
        issues.append(
            _make_issue(
                idx,
                "scientific_figure_tiny_plot_risk",
                "warning",
                (
                    "At least one figure is estimated to render at "
                    f"{smallest[0]:.1f}x{smallest[1]:.1f} inches inside its panel."
                ),
                (
                    "Export tighter slide-ready figures from the Python figure script "
                    "(bbox_inches='tight', small padding, or scripts/trim_image_whitespace.py), "
                    "or use image-sidebar for the dominant plot."
                ),
            )
        )
    return issues


def _check_figure_asset_whitespace(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    variant = (slide.get("variant") or "").strip().lower()
    if variant != "image-sidebar":
        return []
    assets = slide.get("assets")
    if not isinstance(assets, dict):
        return []
    raw_path = str(assets.get("hero_image") or assets.get("image") or "").strip()
    if not raw_path:
        return []
    return _figure_whitespace_issue(
        raw_path=raw_path,
        resolved=_image_path_for_ref(raw_path, outline_parent, context),
        idx=idx,
        context=f"image-sidebar hero image {raw_path!r}",
        require_figure_like=True,
    )


def _check_assets(
    slide: dict[str, Any],
    idx: int,
    outline_parent: Path,
    context: _PreflightContext | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    assets = slide.get("assets")
    if not isinstance(assets, dict):
        return issues
    for field in _ASSET_FIELDS_SCALAR:
        value = assets.get(field)
        if isinstance(value, str) and value:
            if _is_asset_alias(value):
                issues.extend(
                    _check_alias_reference(
                        value,
                        idx,
                        f"assets.{field}",
                        outline_parent,
                        context=context,
                    )
                )
                continue
            if not _check_asset_path(value, outline_parent, context):
                issues.append(
                    _make_issue(
                        idx,
                        "asset_not_found",
                        "warning",
                        f"assets.{field} = {value!r} not found at lint time.",
                        "Stage the asset under the workspace's assets/ or assets/staged/ folder, or use an alias prefix.",
                    )
                )
    for field in _ASSET_FIELDS_ARRAY:
        arr = assets.get(field)
        if isinstance(arr, list):
            for i, value in enumerate(arr):
                if isinstance(value, str) and value:
                    # Icons resolve against assets/icons/ with bare-name +
                    # extension fallbacks. Missing icons are a soft warning
                    # (enrichment only), so we check a wider path set here.
                    if field == "icons" and _check_icon_path(value, outline_parent):
                        continue
                    if not _check_asset_path(value, outline_parent, context):
                        issues.append(
                            _make_issue(
                                idx,
                                "asset_not_found",
                                "warning",
                                f"assets.{field}[{i}] = {value!r} not found at lint time.",
                                "Stage the asset or use an alias prefix.",
                            )
                        )
    return issues


# Variants that support `assets.icons`. The renderer draws icons above each
# card/tile/milestone; omitting them is fine but tends to produce text-only
# decks on topics with clear visual metaphors. See Visual Enrichment Defaults
# in SKILL.md.
_ICON_SUPPORTED_VARIANTS = {
    "cards-2": 2,
    "cards-3": 3,
    "timeline": None,  # length = len(milestones)
    "stats": None,     # length = len(facts)
    "matrix": 4,
    "image-sidebar": None,  # length = len(sidebar_sections)
}


# Rhythm-break detection. "Even with different variants, six slides of
# title+bullets/cards/columns on the same light background feel monotonous"
# is the most common Codex failure mode after variant-awareness was added.
#
# A "rhythm-breaker" must break COMPOSITION, not just layout:
#   - kpi-hero (dark by default, one giant number)
#   - any slide with theme: dark
#   - cards-3 with promote_card (asymmetric, breaks the 3-up grid)
# comparison-2col is layout variety but still light-bg text — good to
# have, but not sufficient on its own for a 5+ slide deck.


def _slide_is_rhythm_breaker(slide: dict[str, Any]) -> bool:
    if not isinstance(slide, dict):
        return False
    variant = (slide.get("variant") or "").strip().lower()
    if variant == "kpi-hero":
        return True
    # cards-3 with a promoted card (asymmetric layout) counts.
    if variant == "cards-3" and isinstance(slide.get("promote_card"), int):
        return True
    # Any slide with theme: dark inverts the palette — big rhythm break.
    if str(slide.get("theme", "")).strip().lower() == "dark":
        return True
    return False


# Heuristics for "hedged prose" — bullets that signal un-researched or
# uncommitted claims rather than specific facts. A deck full of these
# reads as generic. The signals are word-boundary regexes so partial
# matches don't fire (e.g., "typically" matches, "atypically" doesn't).
_HEDGE_WORDS = [
    "usually",
    "often",
    "typically",
    "generally",
    "tends? to",
    "can be",
    "may be",
    "might be",
    "could be",
    "largely",
    "mostly",
    "broadly",
    "generally speaking",
    "in most cases",
    "in many cases",
    "relatively",
    "somewhat",
]

# Concrete-claim signals — if a bullet has any of these, it's not hedged:
# specific years, dollar/percent figures, named entities (capitalized
# proper nouns that aren't sentence-starts are hard to detect reliably
# so we focus on numeric anchors).
_CONCRETE_RE = re.compile(
    r"\b("
    r"19\d{2}|20\d{2}"               # 4-digit year
    r"|\d+(?:\.\d+)?\s*%"            # percent
    r"|\$\s?\d"                      # dollar
    r"|\d+(?:,\d{3})+"               # 1,000+ comma-separated numbers
    r"|\d+\s*(?:km|mi|kg|lb|GW|MW|kW|g|m|s|ms|Hz|ppm|mg|x|×)"  # unit
    r")\b"
)
_HEDGE_RE = re.compile(
    r"\b(?:" + "|".join(_HEDGE_WORDS) + r")\b",
    re.IGNORECASE,
)


def _slide_body_lines(slide: dict[str, Any]) -> list[str]:
    """Extract all prose strings from a slide for hedge detection."""
    lines: list[str] = []
    bullets = slide.get("bullets")
    if isinstance(bullets, list):
        for b in bullets:
            if isinstance(b, str):
                lines.append(b)
            elif isinstance(b, dict) and b.get("text"):
                lines.append(str(b["text"]))
    body = slide.get("body")
    if isinstance(body, str) and body.strip():
        lines.append(body)
    elif isinstance(body, list):
        lines.extend(str(x) for x in body if isinstance(x, str))
    for field in ("highlights", "caption", "subtitle"):
        v = slide.get(field)
        if isinstance(v, str) and v.strip():
            lines.append(v)
        elif isinstance(v, list):
            lines.extend(str(x) for x in v if isinstance(x, str))
    for container in ("left", "right"):
        side = slide.get(container)
        if isinstance(side, dict):
            b = side.get("body")
            if isinstance(b, str):
                lines.append(b)
            elif isinstance(b, list):
                lines.extend(str(x) for x in b if isinstance(x, str))
    cards = slide.get("cards")
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict):
                for field in ("body", "text"):
                    v = card.get(field)
                    if isinstance(v, str) and v.strip():
                        lines.append(v)
    return [l.strip() for l in lines if l and l.strip()]


_TEXT_DENSITY_VARIANT_BUDGETS: dict[str, tuple[int, int, int]] = {
    "": (8, 105, 700),
    "standard": (8, 105, 700),
    "split": (10, 130, 850),
    "comparison-2col": (10, 130, 850),
    "cards-2": (9, 120, 780),
    "cards-3": (9, 120, 780),
    "image-sidebar": (8, 105, 700),
}

_TABLE_HEADER_TEXT_MAX_CHARS = 34
_TABLE_CELL_TEXT_MAX_CHARS = 72
_TABLE_AVG_CELL_TEXT_MAX_CHARS = 34


def _readability_contract(design_brief: Any) -> dict[str, Any]:
    if not isinstance(design_brief, dict):
        return {}
    contract = design_brief.get("readability_contract")
    return contract if isinstance(contract, dict) else {}


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return int(value)


def _title_font_for_length(title: str) -> int:
    length = len(title.strip())
    if length > 82:
        return 17
    if length > 64:
        return 16
    if length > 52:
        return 18
    if length > 42:
        return 20
    return 26


def _title_slide_font_for_length(title: str, *, has_hero: bool) -> int:
    length = len(title.strip())
    base_font = 38 if has_hero else 42
    min_font = 29
    return max(min_font, min(base_font, int(base_font - max(0, length - 32) * 0.32)))


def _estimated_chars_per_line(*, font_size_pt: float, width_in: float) -> int:
    avg_char_w = max(0.055, (font_size_pt / 72.0) * 0.56)
    return max(10, int(max(0.2, width_in - 0.08) / avg_char_w))


def _estimate_text_lines(text: str, *, font_size_pt: float, width_in: float) -> int:
    value = str(text or "").strip()
    if not value:
        return 0
    chars_per_line = _estimated_chars_per_line(font_size_pt=font_size_pt, width_in=width_in)
    total = 0
    for paragraph in re.split(r"\n+", value):
        total += max(1, (len(paragraph.strip()) + chars_per_line - 1) // chars_per_line)
    return total


def _estimated_wrapped_lines(text: str, *, font_size_pt: float, width_in: float) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    chars_per_line = _estimated_chars_per_line(font_size_pt=font_size_pt, width_in=width_in)
    lines: list[str] = []
    for paragraph in re.split(r"\n+", value):
        words = re.findall(r"\S+", paragraph.strip())
        if not words:
            continue
        current = ""
        for word in words:
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= chars_per_line:
                current = f"{current} {word}"
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _title_line_estimate(
    slide: dict[str, Any],
    deck_style: dict[str, Any] | None,
) -> tuple[int, int, float]:
    title = str(slide.get("title") or "").strip()
    slide_type = str(slide.get("type") or "content").strip().lower()
    assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
    has_hero = bool(assets.get("hero_image") or assets.get("image"))
    deck_style = deck_style if isinstance(deck_style, dict) else {}
    if slide_type == "title":
        width = 5.3 if has_hero else 7.4
        font = _title_slide_font_for_length(title, has_hero=has_hero)
    elif slide_type == "section":
        width = 8.7
        font = 34
    else:
        header_mode = str(slide.get("header_mode") or deck_style.get("header_mode") or "").strip().lower()
        width = 9.0
        font = _title_font_for_length(title)
        if header_mode in {"lab-clean", "lab-card"}:
            font = min(24, font)
    return _estimate_text_lines(title, font_size_pt=font, width_in=width), font, width


def _check_title_readability(
    slide: dict[str, Any],
    idx: int,
    deck_style: dict[str, Any] | None,
    readability_contract: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    title = slide.get("title")
    if not isinstance(title, str) or not title.strip():
        return []
    contract = readability_contract or {}
    explicit_line_budget = _positive_int(contract.get("max_title_lines"))
    max_lines = explicit_line_budget or 3
    estimated_lines, font_size, width_in = _title_line_estimate(slide, deck_style)
    if estimated_lines > max_lines:
        return [
            _make_issue(
                idx,
                "title_line_budget_high",
                "warning",
                (
                    f"Title is estimated at {estimated_lines} wrapped lines, "
                    f"above the max_title_lines budget of {max_lines} "
                    f"(font ~{font_size}pt across {width_in:.1f} in)."
                ),
                (
                    "Shorten the slide title, move detail to subtitle/body, "
                    "or explicitly relax readability_contract.max_title_lines for this deck."
                ),
            )
        ]
    wrapped_lines = _estimated_wrapped_lines(title, font_size_pt=font_size, width_in=width_in)
    final_line = wrapped_lines[-1] if wrapped_lines else ""
    final_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", final_line)
    title_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'%-]*", title)
    if (
        1 < len(wrapped_lines) <= max_lines
        and len(final_words) == 1
        and len(final_words[0]) <= 12
        and len(title_words) >= 6
    ):
        return [
            _make_issue(
                idx,
                "title_orphan_final_line",
                "warning",
                (
                    f"Title is estimated at {len(wrapped_lines)} wrapped lines with a single short "
                    f"final line ({final_line!r}) at font ~{font_size}pt across {width_in:.1f} in."
                ),
                (
                    "Rebalance the title by shortening it, moving a qualifier to subtitle/body, "
                    "or rephrasing so the final heading line carries more than one short word."
                ),
            )
        ]
    if explicit_line_budget is None and len(title) > 85:
        return [
            _make_issue(
                idx,
                "title_too_long",
                "warning",
                f"Title is {len(title)} chars (> 85); likely to wrap awkwardly or force small header type.",
                "Shorten to <= 60 chars, or set readability_contract.max_title_lines when a report deck deliberately allows longer titles.",
            )
        ]
    return []


def _check_subtitle_readability(
    slide: dict[str, Any],
    idx: int,
    deck_style: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    subtitle = slide.get("subtitle")
    if not isinstance(subtitle, str) or not subtitle.strip():
        return []
    slide_type = str(slide.get("type") or "content").strip().lower()
    if slide_type != "content":
        return []
    deck_style = deck_style if isinstance(deck_style, dict) else {}
    header_mode = str(slide.get("header_mode") or deck_style.get("header_mode") or "").strip().lower()
    width_in = 8.6 if header_mode in {"lab-clean", "lab-card"} else 8.8
    font_size = 12.5
    estimated_lines = _estimate_text_lines(subtitle, font_size_pt=font_size, width_in=width_in)
    if estimated_lines <= 2:
        return []
    return [
        _make_issue(
            idx,
            "subtitle_line_budget_high",
            "warning",
            (
                f"Subtitle is estimated at {estimated_lines} wrapped lines "
                f"(font ~{font_size:g}pt across {width_in:.1f} in), crowding the content header."
            ),
            (
                "Shorten the subtitle to one concise qualifier, move detail to body/notes, "
                "or split the slide when the qualifier is part of the evidence."
            ),
        )
    ]


def _append_text_density_lines(value: Any, lines: list[str]) -> None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            lines.append(text)
    elif isinstance(value, list):
        for item in value:
            _append_text_density_lines(item, lines)
    elif isinstance(value, dict):
        for key in (
            "body",
            "text",
            "caption",
            "note",
            "interpretation",
            "takeaway",
            "summary",
        ):
            if key in value:
                _append_text_density_lines(value.get(key), lines)


def _slide_text_density_lines(slide: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in (
        "subtitle",
        "body",
        "bullets",
        "highlights",
        "caption",
        "figure_caption",
        "interpretation",
        "takeaway",
        "summary_callout",
    ):
        _append_text_density_lines(slide.get(key), lines)
    for key in (
        "left",
        "right",
        "cards",
        "sidebar_sections",
        "quadrants",
        "milestones",
    ):
        _append_text_density_lines(slide.get(key), lines)
    return [line.strip() for line in lines if line.strip()]


def _scaled_text_budget(
    budget: tuple[int, int, int],
    *,
    slide: dict[str, Any],
    deck_style: dict[str, Any] | None,
    readability_contract: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    density = str(
        slide.get("visual_density")
        or (deck_style or {}).get("visual_density")
        or ""
    ).strip().lower()
    factor = 1.2 if density == "high" else 0.9 if density == "low" else 1.0
    line_budget, word_budget, char_budget = budget
    scaled = (
        max(1, int(round(line_budget * factor))),
        max(1, int(round(word_budget * factor))),
        max(1, int(round(char_budget * factor))),
    )
    contract = readability_contract or {}
    return (
        _positive_int(contract.get("max_slide_text_lines")) or scaled[0],
        _positive_int(contract.get("max_slide_words")) or scaled[1],
        _positive_int(contract.get("max_slide_chars")) or scaled[2],
    )


def _check_text_density(
    slide: dict[str, Any],
    idx: int,
    deck_style: dict[str, Any] | None,
    readability_contract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    stype = (slide.get("type") or "content").strip().lower()
    if stype != "content":
        return []
    variant = (slide.get("variant") or "standard").strip().lower()
    if variant not in _TEXT_DENSITY_VARIANT_BUDGETS:
        return []
    lines = _slide_text_density_lines(slide)
    if not lines:
        return []
    words = sum(len(re.findall(r"\b[\w'-]+\b", line)) for line in lines)
    chars = sum(len(line) for line in lines)
    line_budget, word_budget, char_budget = _scaled_text_budget(
        _TEXT_DENSITY_VARIANT_BUDGETS[variant],
        slide=slide,
        deck_style=deck_style,
        readability_contract=readability_contract,
    )
    if len(lines) <= line_budget and words <= word_budget and chars <= char_budget:
        return []
    exceeded: list[str] = []
    if len(lines) > line_budget:
        exceeded.append(f"{len(lines)} text lines > {line_budget}")
    if words > word_budget:
        exceeded.append(f"{words} words > {word_budget}")
    if chars > char_budget:
        exceeded.append(f"{chars} chars > {char_budget}")
    return [
        _make_issue(
            idx,
            "content_text_density_high",
            "warning",
            f"{variant or 'standard'} slide text budget is high ({', '.join(exceeded)}).",
            (
                "Split the slide, shorten bullets, move detail to notes/refs, "
                "or convert dense evidence into a chart, table, sidebar figure, or summary callout."
            ),
        )
    ]


def _check_content_quality(slide: dict[str, Any], idx: int) -> list[dict[str, Any]]:
    """Flag slides whose prose is dominated by hedges and lacks concrete
    anchors (years, percents, quantities, named dollars). Info-level —
    the slide isn't wrong, it just isn't load-bearing.
    """
    stype = (slide.get("type") or "content").strip().lower()
    if stype != "content":
        return []
    lines = _slide_body_lines(slide)
    if len(lines) < 2:
        return []  # tables / kpi-hero / short slides
    hedge_hits = sum(1 for l in lines if _HEDGE_RE.search(l))
    concrete_hits = sum(1 for l in lines if _CONCRETE_RE.search(l))
    # Flag when >= 50% of lines are hedged AND there are 0 concrete anchors.
    if hedge_hits >= max(2, len(lines) // 2) and concrete_hits == 0:
        return [
            _make_issue(
                idx,
                "content_vague_hedged",
                "info",
                (
                    f"{hedge_hits}/{len(lines)} prose lines on this slide use "
                    "hedges (usually/often/can be/typically/tends to) and "
                    "zero lines carry a concrete anchor (year, %, quantity, "
                    "named entity with a number). The slide reads as "
                    "uncommitted."
                ),
                (
                    "Research at least one specific fact per bullet: a year, "
                    "a percentage, a named case, a dollar figure. Replace "
                    "'reactors usually take many years' with '~10-15 years "
                    "median from permit to first criticality (EIA, NRC).' "
                    "If the content genuinely doesn't have specifics, ask "
                    "the user rather than shipping hedged prose."
                ),
            )
        ]
    return []


def _check_rhythm_break(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    content = [
        s for s in slides
        if isinstance(s, dict)
        and (s.get("type") or "content").strip().lower() == "content"
    ]
    if len(content) < 5:
        return []
    if any(_slide_is_rhythm_breaker(s) for s in content):
        return []
    return [
        _make_issue(
            None,
            "rhythm_break_absent",
            "info",
            (
                f"Deck has {len(content)} content slides but no composition "
                "rhythm-breaker (kpi-hero, promote_card on cards-3, or "
                "theme: dark). Varying the variant across cards/split/matrix/"
                "timeline still reads as uniform when every slide is "
                "title+bullets on a light background."
            ),
            (
                "Add at least ONE of: (1) a kpi-hero slide pulling out the "
                "deck's most memorable number (kpi-hero renders dark by "
                "default — the biggest rhythm break); (2) promote_card: N "
                "on one cards-3 slide to break the symmetric 3-up grid; "
                "(3) theme: \"dark\" on one content slide. comparison-2col "
                "is useful but doesn't count on its own — it's still "
                "light-bg text. If the content doesn't naturally offer a "
                "quantitative anchor or a pillar that dominates, ASK THE "
                "USER for one before building rather than shipping a "
                "uniform deck."
            ),
        )
    ]


def _derive_icon_suggestion(title: str) -> str:
    """Derive a reasonable bare-name icon slug from a card/item title.

    Lowercased, spaces/punctuation to hyphens, trimmed to the first 1-2
    meaningful words. Not a lookup — just a starting-point suggestion
    the author can keep or refine when staging actual icons.
    """
    if not title:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", title.lower())
    words = [w for w in cleaned.split() if w and w not in {"the", "a", "an", "and", "or", "of"}]
    if not words:
        return ""
    # Prefer the first 1-2 content words; keep short for filesystem friendliness.
    slug = "-".join(words[:2])
    return slug[:28]


def _collect_icon_candidates(slide: dict[str, Any]) -> list[str]:
    """For a slide that supports icons, return 1 suggested bare name per
    card/milestone/fact, derived from each item's title. Empty list when
    there's nothing to suggest.
    """
    variant = (slide.get("variant") or "").strip().lower()
    if variant not in _ICON_SUPPORTED_VARIANTS:
        return []
    items: list[dict[str, Any]] = []
    if variant in ("cards-2", "cards-3") and isinstance(slide.get("cards"), list):
        items = [c for c in slide["cards"] if isinstance(c, dict)]
    elif variant == "timeline" and isinstance(slide.get("milestones"), list):
        items = [m for m in slide["milestones"] if isinstance(m, dict)]
    elif variant == "matrix" and isinstance(slide.get("quadrants"), list):
        items = [q for q in slide["quadrants"] if isinstance(q, dict)]
    elif variant == "stats" and isinstance(slide.get("facts"), list):
        items = [f for f in slide["facts"] if isinstance(f, dict)]
    elif variant == "image-sidebar" and isinstance(slide.get("sidebar_sections"), list):
        items = [s for s in slide["sidebar_sections"] if isinstance(s, dict)]

    suggestions: list[str] = []
    for item in items:
        title = str(item.get("title") or item.get("label") or "").strip()
        slug = _derive_icon_suggestion(title)
        if slug:
            suggestions.append(slug)
    return suggestions


def _check_variant_overuse(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag when the deck uses the full variant menu instead of picking
    a thoughtful subset. Recent Codex runs cycle through kpi-hero +
    comparison-2col + matrix + timeline + cards-3 + split on nearly
    every deck regardless of topic — the rhythm-break guardrails
    rewarded variant COUNT rather than variant FIT.

    Fires as info-level on decks where distinct_variants / content_slides
    exceeds 0.75 (i.e., almost every slide introduces a new variant).
    Suggestion: commit to 2-3 variants and use them intentionally.
    """
    content = [
        s for s in slides
        if isinstance(s, dict)
        and (s.get("type") or "content").strip().lower() == "content"
    ]
    if len(content) < 5:
        return []
    variants = [
        (s.get("variant") or "").strip().lower()
        for s in content
    ]
    # Treat empty variant as "standard" for counting purposes.
    normalized = [v or "standard" for v in variants]
    distinct = set(normalized)
    ratio = len(distinct) / len(content)
    # "Menu-fitting" threshold: at least 5 distinct variants AND the
    # ratio is ≥ 0.75 (almost every slide is a different variant).
    if len(distinct) < 5 or ratio < 0.75:
        return []
    return [
        _make_issue(
            None,
            "variant_overuse",
            "info",
            (
                f"Deck has {len(content)} content slides using "
                f"{len(distinct)} distinct variants "
                f"({sorted(distinct)}). When nearly every slide is a "
                "different variant, the deck reads as 'menu-fitting the "
                "skill' rather than designed for this topic."
            ),
            (
                "Pick 2-3 variants that fit the topic's voice and use "
                "them intentionally: an editorial primer might use "
                "standard + kpi-hero + image-lead; a research brief "
                "might use cards-3 + table + comparison-2col; a "
                "methodology might use timeline + matrix + standard. "
                "Retire the variants that don't serve the argument. "
                "Don't treat the rhythm-break rule as 'must use every "
                "variant once' — one strong rhythm-breaker plus "
                "consistent supporting variants reads as intentional."
            ),
        )
    ]


def _check_icon_absence_systemic(
    slides: list[dict[str, Any]],
    prior_issues: list[dict[str, Any]],  # unused; kept for signature stability
) -> list[dict[str, Any]]:
    """Single deck-level icon rule. Fires when ≥2 icon-supporting slides
    (cards-2/cards-3/timeline/stats/matrix) have no `assets.icons` AND
    the deck has zero icons anywhere. Concrete suggestion: bare-name
    slugs derived from each card/milestone/quadrant title.

    Replaces three earlier overlapping rules (`icons_absent_enrichment_hint`
    per slide, `enrichment_missing_pattern` deck-level, plus this one).
    """
    icon_supporting = []
    for idx, s in enumerate(slides):
        if not isinstance(s, dict):
            continue
        variant = (s.get("variant") or "").strip().lower()
        if variant in _ICON_SUPPORTED_VARIANTS:
            icon_supporting.append((idx, s))

    if len(icon_supporting) < 2:
        return []

    # Evidence-first lab/data decks should not be nudged toward decorative
    # icons just because they contain a stats or timeline slide. Clean lab
    # decks use figures, compact tables, semantic fills, and captions as
    # the visual language; icons are optional labels, not a quality gate.
    evidence_first_variants = {"lab-run-results", "scientific-figure", "image-sidebar", "table", "chart"}
    evidence_first_count = sum(
        1
        for s in slides
        if isinstance(s, dict)
        and (s.get("variant") or "").strip().lower() in evidence_first_variants
    )
    if evidence_first_count >= 2:
        return []

    # Any slide already has icons set? Then nothing systemic.
    for s in slides:
        if not isinstance(s, dict):
            continue
        assets = s.get("assets") or {}
        if isinstance(assets, dict) and assets.get("icons"):
            return []

    # Build per-slide suggestion map from card titles.
    suggestions_by_slide: dict[int, list[str]] = {}
    for idx, s in icon_supporting:
        slugs = _collect_icon_candidates(s)
        if slugs:
            suggestions_by_slide[idx] = slugs

    if not suggestions_by_slide:
        return []

    suggestion_lines = [
        f"slide {idx}: {suggestions_by_slide[idx]}"
        for idx in sorted(suggestions_by_slide)
    ]
    suggestion_blob = "; ".join(suggestion_lines)

    return [
        _make_issue(
            None,
            "icons_systemically_absent",
            "warning",
            (
                f"{len(icon_supporting)} icon-supporting slide(s) have "
                "no `assets.icons` and the deck has zero icons anywhere. "
                "Icons often clarify cards that share a visual metaphor."
            ),
            (
                "If icons would help, stage PNGs under "
                "<workspace>/assets/icons/<name>.png and add "
                "`assets.icons` arrays to the flagged slides using these "
                f"derived candidate names: {suggestion_blob}. If the deck "
                "genuinely doesn't benefit from icons (pure prose primer, "
                "minimal aesthetic), ignore this warning."
            ),
        )
    ]


def _check_enrichment_pattern(
    slides: list[dict[str, Any]],
    prior_issues: list[dict[str, Any]],
    outline_parent: Path,
) -> list[dict[str, Any]]:
    """Promote scattered icons_absent_enrichment_hint notes to a single
    deck-level warning when the pattern is systemic — ≥3 slides flagged,
    no staged visuals/evidence anchors, and no asset_plan anchor arrays
    populated. This is the "Codex acknowledged the nudges and shipped anyway"
    failure mode.
    """
    icon_hints = [i for i in prior_issues if i.get("rule") == "icons_absent_enrichment_hint"]
    if len(icon_hints) < 3:
        return []

    # Is there any visual/evidence anchor anywhere in the deck?
    has_any_anchor = False
    for s in slides:
        if not isinstance(s, dict):
            continue
        variant = str(s.get("variant") or "").strip().lower()
        assets = s.get("assets") or {}
        if not isinstance(assets, dict):
            assets = {}
        if (
            variant in {"chart", "table", "lab-run-results", "image-sidebar", "scientific-figure", "flow"}
            or s.get("chart")
            or s.get("table")
            or s.get("tables")
            or s.get("figures")
            or assets.get("hero_image")
            or assets.get("image")
            or assets.get("generated_image")
            or assets.get("mermaid_source")
            or assets.get("diagram")
            or assets.get("chart_data")
            or assets.get("chart")
            or assets.get("table_data")
            or assets.get("table")
            or assets.get("tables")
            or assets.get("figures")
        ):
            has_any_anchor = True
            break
    if has_any_anchor:
        return []

    plan_path = outline_parent / "asset_plan.json"
    plan_has_anchors = False
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_has_anchors = bool(
                (plan.get("images") or [])
                or (plan.get("backgrounds") or [])
                or (plan.get("charts") or [])
                or (plan.get("tables") or [])
                or (plan.get("generated_images") or [])
                or (plan.get("icons") or [])
            )
        except (json.JSONDecodeError, OSError):
            plan_has_anchors = False
    if plan_has_anchors:
        return []

    slide_indices = sorted({i.get("slide_index") for i in icon_hints if isinstance(i.get("slide_index"), int)})
    return [
        _make_issue(
            None,
            "enrichment_missing_pattern",
            "warning",
            (
                f"{len(icon_hints)} slides were flagged with "
                "icons_absent_enrichment_hint; the deck also has zero "
                "staged hero images, generated images, charts, tables, figures, "
                "or mermaid diagrams, and an empty asset_plan.json "
                "images/charts/tables/generated_images/icons array. "
                "This is systemic — "
                "the deck will ship as text-only despite multiple nudges."
            ),
            (
                "Take ONE of these three actions before declaring done: "
                f"(1) stage icons for the flagged slides {slide_indices} "
                "under <workspace>/assets/icons/<name>.png and add "
                "`assets.icons` arrays to those slides; (2) populate "
                "asset_plan.json with at least one wikimedia_query for a "
                "photographic hero image, or add a chart/table artifact and "
                "re-run the build; (3) if the "
                "deck genuinely doesn't need visuals (pure-prose primer), "
                "note that decision explicitly in notes.md and accept the "
                "warning. Don't ignore this rule silently — it means the "
                "deck looks uniform and the earlier per-slide nudges "
                "didn't bite."
            ),
        )
    ]


def _check_icon_nudge(slide: dict[str, Any], idx: int) -> list[dict[str, Any]]:
    variant = (slide.get("variant") or "").strip().lower()
    if variant not in _ICON_SUPPORTED_VARIANTS:
        return []
    assets = slide.get("assets")
    icons = assets.get("icons") if isinstance(assets, dict) else None
    if isinstance(icons, list) and any(isinstance(i, str) and i.strip() for i in icons):
        return []
    expected = _ICON_SUPPORTED_VARIANTS[variant]
    if expected is None:
        if variant == "timeline":
            expected = len(slide.get("milestones") or []) or 4
        elif variant == "stats":
            expected = len(slide.get("facts") or []) or 3
        elif variant == "image-sidebar":
            expected = len(slide.get("sidebar_sections") or []) or 3
    return [
        _make_issue(
            idx,
            "icons_absent_enrichment_hint",
            "info",
            f"variant: {variant} supports `assets.icons` but none are set; "
            f"icons often clarify cards that share a visual metaphor.",
            f"If the {variant} cards/items have a clear visual anchor, add "
            f"`assets.icons`: [ {expected} bare names ] and stage PNGs under "
            f"`<workspace>/assets/icons/<name>.png`.",
        )
    ]


def _check_section_empty(slide: dict[str, Any], idx: int) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    slide_type = (slide.get("type") or "").strip().lower()
    if slide_type != "section":
        return issues
    has_bullets = bool(slide.get("bullets"))
    has_caption = bool(slide.get("caption"))
    has_body = bool(slide.get("body"))
    hero_image = ""
    assets = slide.get("assets")
    if isinstance(assets, dict):
        hero_image = assets.get("hero_image") or ""
    has_hero = bool(hero_image)
    if not (has_bullets or has_caption or has_body or has_hero):
        issues.append(
            _make_issue(
                idx,
                "section_auto_motif",
                "info",
                "Section divider has no bullets/caption/body/hero_image; renderer will auto-draw a motif.",
                "This is expected. Add `bullets` or `caption` if you want real transition content.",
            )
        )
    return issues


def _check_sources_stretch(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    run_start: int | None = None
    run_len = 0
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        slide_type = (slide.get("type") or "content").strip().lower()
        if slide_type not in ("content", "text"):
            # Reset run at non-content boundaries (title/section).
            if run_len >= 3 and run_start is not None:
                issues.append(
                    _make_issue(
                        run_start,
                        "sources_missing_streak",
                        "info",
                        f"{run_len} consecutive content slides (starting index {run_start}) have no `sources`.",
                        "Add at least one `sources` entry per evidence-bearing slide for citation discipline.",
                    )
                )
            run_start = None
            run_len = 0
            continue
        sources = slide.get("sources")
        if not sources:
            if run_start is None:
                run_start = idx
            run_len += 1
        else:
            if run_len >= 3 and run_start is not None:
                issues.append(
                    _make_issue(
                        run_start,
                        "sources_missing_streak",
                        "info",
                        f"{run_len} consecutive content slides (starting index {run_start}) have no `sources`.",
                        "Add at least one `sources` entry per evidence-bearing slide.",
                    )
                )
            run_start = None
            run_len = 0
    if run_len >= 3 and run_start is not None:
        issues.append(
            _make_issue(
                run_start,
                "sources_missing_streak",
                "info",
                f"{run_len} consecutive content slides (starting index {run_start}) have no `sources`.",
                "Add at least one `sources` entry per evidence-bearing slide.",
            )
        )
    return issues


def _source_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("text", "citation", "source", "title", "label", "name"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        for text in value.values():
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _source_list_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _source_text(item))]


def _placeholder_path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]" if parent else f"[{key}]"
    return f"{parent}.{key}" if parent else key


def _iter_placeholder_text(value: Any, path: str = "", parent_key: str = "") -> list[tuple[str, str]]:
    key = parent_key.lower()
    if key in _PLACEHOLDER_TEXT_SKIP_SUBTREES:
        return []
    if isinstance(value, str):
        if key in _PLACEHOLDER_TEXT_SKIP_KEYS:
            return []
        return [(path or "$", value)]
    if isinstance(value, (int, float, bool)):
        return []
    if isinstance(value, list):
        chunks: list[tuple[str, str]] = []
        for index, item in enumerate(value):
            chunks.extend(_iter_placeholder_text(item, _placeholder_path(path, index), parent_key))
        return chunks
    if isinstance(value, dict):
        chunks = []
        for raw_key, item in value.items():
            child_key = str(raw_key)
            if child_key.lower() in _PLACEHOLDER_TEXT_SKIP_SUBTREES:
                continue
            chunks.extend(
                _iter_placeholder_text(
                    item,
                    _placeholder_path(path, child_key),
                    child_key,
                )
            )
        return chunks
    return []


def _placeholder_snippet(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 28)
    end = min(len(text), match.end() + 28)
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


def _placeholder_marker_hits(text: str) -> list[str]:
    hits: list[str] = []
    for label, pattern in _PLACEHOLDER_MARKER_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append(f"{label}: {_placeholder_snippet(text, match)!r}")
    return hits


def _check_placeholder_markers(
    payload: Any,
    slide_index: int | None,
    path_label: str,
) -> list[dict[str, Any]]:
    hits: list[str] = []
    for path, text in _iter_placeholder_text(payload, path_label):
        marker_hits = _placeholder_marker_hits(text)
        if marker_hits:
            hits.append(f"{path} ({'; '.join(marker_hits)})")
    if not hits:
        return []

    visible_hits = hits[:4]
    remainder = len(hits) - len(visible_hits)
    if remainder > 0:
        visible_hits.append(f"{remainder} more field(s)")
    return [
        _make_issue(
            slide_index,
            "placeholder_marker_in_outline",
            "warning",
            "Outline text contains placeholder marker(s): " + "; ".join(visible_hits) + ".",
            (
                "Replace TODO/TBD/lorem/XXX/bracketed insert prompts with final slide text, "
                "or move unresolved work into notes.md before building the deck."
            ),
        )
    ]


def _source_line_footer_text(slide: dict[str, Any], deck_style: dict[str, Any] | None) -> tuple[str, list[str]]:
    deck_style = deck_style if isinstance(deck_style, dict) else {}
    footer = str(slide.get("footer") or "").strip()
    source_label = str(slide.get("source_label") or deck_style.get("footer_source_label") or "Sources").strip()
    refs_label = str(slide.get("refs_label") or deck_style.get("footer_refs_label") or "Refs").strip()
    sources = _source_list_texts(slide.get("sources"))
    refs = _source_list_texts(slide.get("refs")) or _source_list_texts(slide.get("references"))

    parts: list[str] = []
    if footer:
        parts.append(footer)
    if sources:
        parts.append(f"{source_label}: " + "; ".join(sources))
    if refs:
        parts.append(f"{refs_label}: " + "; ".join(refs))
    return " · ".join(parts), [*sources, *refs]


def _check_source_line_footer_budget(
    slide: dict[str, Any],
    idx: int,
    deck_style: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    slide_mode = str(slide.get("footer_mode") or "").strip().lower()
    deck_mode = ""
    if isinstance(deck_style, dict):
        deck_mode = str(deck_style.get("footer_mode") or "").strip().lower()
    footer_mode = slide_mode or deck_mode
    if footer_mode != "source-line":
        return []

    left_text, provenance_items = _source_line_footer_text(slide, deck_style)
    if not left_text:
        return []

    text_len = len(left_text)
    longest_item = max((len(item) for item in provenance_items), default=0)
    item_count = len(provenance_items)
    reasons: list[str] = []
    if text_len > 170:
        reasons.append(f"combined footer/source text is {text_len} chars (>170)")
    if longest_item > 95:
        reasons.append(f"one source/ref item is {longest_item} chars (>95)")
    if item_count > 4:
        reasons.append(f"{item_count} source/ref items are packed into one footer (>4)")
    if not reasons:
        return []

    return [
        _make_issue(
            idx,
            "source_line_footer_over_budget",
            "warning",
            "source-line footer is likely to shrink into unreadable provenance text: "
            + "; ".join(reasons)
            + ".",
            (
                "Keep slide footer provenance compact with short citation IDs, "
                "or run scripts/compact_source_footers.py to move full references "
                "to a References/Image Sources table slide and cite short IDs."
            ),
        )
    ]


def _collect_slide_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            chunks.extend(_collect_slide_text(item))
        return chunks
    if isinstance(value, dict):
        chunks = []
        for item in value.values():
            chunks.extend(_collect_slide_text(item))
        return chunks
    return []


def _check_evidence_motif_continuity(slides: list[dict[str, Any]], deck_style: Any) -> list[dict[str, Any]]:
    if not isinstance(deck_style, dict):
        return []
    title_layout = str(deck_style.get("title_layout") or "").strip().lower()
    if title_layout != "lab-plate":
        return []

    content_text = []
    for slide in slides[1:]:
        if not isinstance(slide, dict):
            continue
        if str(slide.get("type") or "content").strip().lower() not in {"content", "text", "section"}:
            continue
        content_text.extend(_collect_slide_text(slide))
    normalized = re.sub(r"[^a-z0-9]+", " ", " ".join(content_text).lower())
    threads = {
        "evidence": "evidence" in normalized,
        "readout": "readout" in normalized,
        "next run": "next run" in normalized or "next step" in normalized or "next steps" in normalized,
    }
    carried = [thread for thread, present in threads.items() if present]
    if len(carried) >= 2:
        return []
    return [
        _make_issue(
            None,
            "evidence_motif_not_carried",
            "warning",
            (
                "deck_style.title_layout='lab-plate' creates Evidence/Readout/Next run chips on the cover, "
                f"but only {len(carried)}/3 thread(s) appear in later slide text."
            ),
            (
                "Carry the chips forward with subtitle prefixes, sidebar labels, table group titles, "
                "or a final NEXT RUN strip; otherwise choose a title layout without those chips."
            ),
        )
    ]


def lint_outline(
    outline: dict[str, Any],
    outline_parent: Path,
    design_brief: Any | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    context = _PreflightContext()
    issues.extend(_check_declared_alias_conflicts(outline_parent, context))
    readability_contract = _readability_contract(design_brief)
    deck_level_payload = {key: value for key, value in outline.items() if key != "slides"}
    issues.extend(_check_placeholder_markers(deck_level_payload, None, "outline"))

    # Deck-level font_pair check.
    deck_style = outline.get("deck_style")
    if isinstance(deck_style, dict):
        font_pair = deck_style.get("font_pair")
        if font_pair is not None and font_pair not in _VALID_FONT_PAIRS:
            issues.append(
                _make_issue(
                    None,
                    "invalid_font_pair",
                    "error",
                    f"deck_style.font_pair = {font_pair!r} is not one of {sorted(_VALID_FONT_PAIRS)}.",
                    f"Set font_pair to one of: {', '.join(sorted(_VALID_FONT_PAIRS))}.",
                )
            )
        issues.extend(
            _check_style_treatments(
                deck_style,
                slide_index=None,
                path_label="deck_style",
                keys=_ROOT_STYLE_ENUM_KEYS,
            )
        )
    elif deck_style is not None:
        issues.extend(
            _check_style_treatments(
                deck_style,
                slide_index=None,
                path_label="deck_style",
                keys=_ROOT_STYLE_ENUM_KEYS,
            )
        )

    slides = outline.get("slides")
    if not isinstance(slides, list):
        issues.append(
            _make_issue(
                None,
                "slides_missing",
                "error",
                "Top-level `slides` array is missing or not a list.",
                "Add a `slides` array to the outline.",
            )
        )
        return issues

    # Slide 1 must be title.
    if slides:
        first = slides[0]
        if isinstance(first, dict):
            first_type = (first.get("type") or "content").strip().lower()
            if first_type != "title":
                issues.append(
                    _make_issue(
                        0,
                        "slide1_not_title",
                        "warning",
                        f"Slide 1 has type={first_type!r}; the title-slide motif only fires on type: title.",
                        "Set slide 0 to type: title, or accept that the opener will use the content motif.",
                    )
                )

    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            issues.append(
                _make_issue(
                    idx,
                    "slide_malformed",
                    "error",
                    "Slide entry is not an object.",
                    "Replace the entry with a slide object.",
                )
            )
            continue

        issues.extend(_check_placeholder_markers(slide, idx, f"slides[{idx}]"))

        issues.extend(
            _check_title_readability(
                slide,
                idx,
                deck_style if isinstance(deck_style, dict) else None,
                readability_contract,
            )
        )
        issues.extend(
            _check_subtitle_readability(
                slide,
                idx,
                deck_style if isinstance(deck_style, dict) else None,
            )
        )

        variant = (slide.get("variant") or "").strip().lower()
        if slide.get("render_mode") is not None:
            issues.append(
                _make_issue(
                    idx,
                    "legacy_render_mode",
                    "warning",
                    "`render_mode` is a legacy field and should not be used in new outlines.",
                    "Remove render_mode and let build_workspace.py --renderer auto choose the renderer.",
                )
            )
        if variant == "chart":
            issues.extend(_check_chart(slide, idx, outline_parent, context))
        if variant == "stats":
            issues.extend(_check_stats(slide, idx))

        issues.extend(
            _check_style_treatments(
                slide,
                slide_index=idx,
                path_label=f"slides[{idx}]",
                keys=_SLIDE_STYLE_ENUM_KEYS,
            )
        )
        issues.extend(_check_variant_required(slide, idx, outline_parent, context))
        issues.extend(_check_evidence_anchor(slide, idx))
        issues.extend(_check_assets(slide, idx, outline_parent, context))
        issues.extend(
            _check_text_density(
                slide,
                idx,
                deck_style if isinstance(deck_style, dict) else None,
                readability_contract,
            )
        )
        issues.extend(_check_scientific_figure_readability(slide, idx, outline_parent, context))
        issues.extend(_check_figure_asset_whitespace(slide, idx, outline_parent, context))
        issues.extend(_check_flow_complexity(slide, idx, outline_parent))
        issues.extend(_check_section_empty(slide, idx))
        issues.extend(
            _check_source_line_footer_budget(
                slide,
                idx,
                deck_style if isinstance(deck_style, dict) else None,
            )
        )
        # Removed: _check_icon_nudge per-slide info. icons_systemically_absent
        # now fires at the deck level with concrete suggestions.
        # Removed: _check_content_quality (hedged-prose linter was firing on
        # decent prose too often). See SKILL.md "Visual Enrichment Defaults"
        # for the soft guidance on specific-vs-hedged claims.

    issues.extend(_check_sources_stretch(slides))
    # Removed: _check_rhythm_break (turned a taste call into a rule that
    # fired on every ≥5-slide deck). Rhythm is a design judgement, not
    # a schema invariant. SKILL.md covers when to reach for a
    # rhythm-break.
    # Removed: _check_enrichment_pattern (overlapped with the rule below).
    issues.extend(_check_icon_absence_systemic(slides, issues))
    issues.extend(_check_variant_overuse(slides))
    issues.extend(_check_evidence_motif_continuity(slides, deck_style))

    return issues


def _summary_to_stderr(issues: list[dict[str, Any]], error_count: int, warning_count: int, info_count: int) -> None:
    if not issues:
        print("[preflight] OK - no issues.", file=sys.stderr)
        return
    print(
        f"[preflight] {error_count} error(s), {warning_count} warning(s), {info_count} info note(s).",
        file=sys.stderr,
    )
    for it in issues:
        slide = it["slide_index"]
        loc = f"slide {slide}" if slide is not None and slide >= 0 else "deck"
        sev = it["severity"].upper()
        print(f"  [{sev}] {loc} :: {it['rule']} :: {it['message']}", file=sys.stderr)
        if it.get("suggested_fix"):
            print(f"        fix: {it['suggested_fix']}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Static preflight linter for presentation-skill outlines.")
    parser.add_argument("--outline", required=True, help="Path to outline.json.")
    parser.add_argument(
        "--design-brief",
        help="Optional design_brief.json with readability_contract title/prose budgets.",
    )
    parser.add_argument(
        "--asset-root",
        help=(
            "Directory for resolving local asset paths, asset_plan.json, and "
            "assets/staged/staged_manifest.json. Defaults to the outline file's parent."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 2 if any errors are found (default: warnings-only exit 1).",
    )
    args = parser.parse_args()

    outline_path = Path(args.outline).expanduser().resolve()
    if not outline_path.exists():
        print(
            json.dumps(
                {
                    "issues": [
                        {
                            "slide_index": -1,
                            "rule": "outline_missing",
                            "severity": "error",
                            "message": f"Outline file not found: {outline_path}",
                            "suggested_fix": "Pass the correct --outline path.",
                        }
                    ],
                    "error_count": 1,
                    "warning_count": 0,
                }
            )
        )
        print(f"[preflight] outline not found: {outline_path}", file=sys.stderr)
        return 3

    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {
                    "issues": [
                        {
                            "slide_index": -1,
                            "rule": "outline_malformed",
                            "severity": "error",
                            "message": f"Outline JSON is malformed: {exc}",
                            "suggested_fix": "Fix the JSON syntax before running preflight.",
                        }
                    ],
                    "error_count": 1,
                    "warning_count": 0,
                }
            )
        )
        print(f"[preflight] malformed JSON: {exc}", file=sys.stderr)
        return 3

    if not isinstance(outline, dict):
        print(
            json.dumps(
                {
                    "issues": [
                        {
                            "slide_index": -1,
                            "rule": "outline_malformed",
                            "severity": "error",
                            "message": "Outline root is not a JSON object.",
                            "suggested_fix": "Wrap the outline in a top-level object.",
                        }
                    ],
                    "error_count": 1,
                    "warning_count": 0,
                }
            )
        )
        print("[preflight] outline root is not an object", file=sys.stderr)
        return 3

    design_brief: Any | None = None
    design_brief_issues: list[dict[str, Any]] = []
    if args.design_brief:
        design_brief_path = Path(args.design_brief).expanduser().resolve()
        if not design_brief_path.exists():
            design_brief_issues.append(
                _make_issue(
                    None,
                    "design_brief_missing",
                    "warning",
                    f"Design brief not found: {design_brief_path}",
                    "Pass the correct design_brief.json path or omit --design-brief.",
                )
            )
        else:
            try:
                design_brief = json.loads(design_brief_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                design_brief_issues.append(
                    _make_issue(
                        None,
                        "design_brief_malformed",
                        "warning",
                        f"Design brief JSON is malformed: {exc}",
                        "Fix design_brief.json so readability_contract can be applied.",
                    )
                )
            if design_brief is not None and not isinstance(design_brief, dict):
                design_brief_issues.append(
                    _make_issue(
                        None,
                        "design_brief_malformed",
                        "warning",
                        "Design brief root is not a JSON object.",
                        "Wrap design_brief.json in a top-level object.",
                    )
                )
                design_brief = None

    asset_root = (
        Path(args.asset_root).expanduser().resolve()
        if args.asset_root
        else outline_path.parent
    )
    issues = [*design_brief_issues, *lint_outline(outline, asset_root, design_brief)]

    error_count = sum(1 for it in issues if it["severity"] == "error")
    warning_count = sum(1 for it in issues if it["severity"] == "warning")
    info_count = sum(1 for it in issues if it["severity"] == "info")

    print(
        json.dumps(
            {
                "issues": issues,
                "error_count": error_count,
                "warning_count": warning_count,
                "info_count": info_count,
            },
            indent=2,
        )
    )

    _summary_to_stderr(issues, error_count, warning_count, info_count)

    # Exit code semantics:
    #   0 -> no issues
    #   1 -> warnings only
    #   2 -> errors present (caller decides blocking via --strict-preflight / --qa)
    #   3 -> malformed JSON (handled above)
    # --strict is a CLI convenience that forces non-zero on errors; today
    # any error already yields 2, so --strict is a no-op at this layer and
    # exists for parity with the integration flag name.
    if error_count > 0:
        return 2
    if warning_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
