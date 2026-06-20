#!/usr/bin/env python3
"""Validate workspace planning files before rendering a deck."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

from design_tokens import available_presets


SUPPORTED_STYLE_PRESET_NAMES = {str(name).strip().lower(): str(name).strip() for name in available_presets()}
SUPPORTED_STYLE_PRESETS = set(SUPPORTED_STYLE_PRESET_NAMES)
SUPPORTED_HEADER_VARIANTS = {
    "auto",
    "left-accent",
    "split-rule",
    "title-rule",
    "side-rail",
    "top-bottom-rule",
    "plain",
}
SUPPORTED_TITLE_LAYOUTS = {
    "split-hero",
    "lab-plate",
    "command-center",
    "poster",
    "masthead",
    "light-atlas",
}
SUPPORTED_HEADER_MODES = {"bar", "stack", "eyebrow", "lab-clean", "lab-card"}
SUPPORTED_VISUAL_DENSITIES = {"low", "medium", "high"}
SUPPORTED_TITLE_MOTIFS = {"orbit", "network", "editorial", "none"}
SUPPORTED_SECTION_MOTIFS = {"rail-dots", "numbered-tabs", "plain", "none"}
SUPPORTED_TIMELINE_MODES = {"rail-cards", "staggered", "open-events", "bands", "chapter-spread"}
SUPPORTED_MATRIX_MODES = {"cards", "open-quadrants"}
SUPPORTED_STATS_MODES = {"tiles", "feature-left", "policy-bands"}
SUPPORTED_CARDS_MODES = {"feature-left", "staggered-row"}
SUPPORTED_CHART_TREATMENTS = {"standard", "facts-below", "facts-right", "minimal"}
SUPPORTED_FOOTERS = {"standard", "source-line", "none"}
SUPPORTED_SUMMARY_CALLOUT_MODES = {"default", "lab-box"}
SUPPORTED_FIGURE_TREATMENTS = {
    "figure-first",
    "table-first",
    "stats-strip",
    "image-sidebar",
}
STYLE_MIX_POOL_SPECS = (
    ("header_variant_pool", SUPPORTED_HEADER_VARIANTS, True),
    ("title_layout_pool", SUPPORTED_TITLE_LAYOUTS, False),
    ("section_motif_pool", SUPPORTED_SECTION_MOTIFS, False),
    ("timeline_mode_pool", SUPPORTED_TIMELINE_MODES, False),
    ("matrix_mode_pool", SUPPORTED_MATRIX_MODES, False),
    ("stats_mode_pool", SUPPORTED_STATS_MODES, False),
    ("cards_mode_pool", SUPPORTED_CARDS_MODES, False),
    ("chart_treatment_pool", SUPPORTED_CHART_TREATMENTS, False),
    ("summary_callout_mode_pool", SUPPORTED_SUMMARY_CALLOUT_MODES, False),
    ("summary_callout_pool", SUPPORTED_SUMMARY_CALLOUT_MODES | {"kpi-hero", "promote-card", "thin-rule-callout", "none"}, False),
    ("footer_pool", SUPPORTED_FOOTERS, False),
    ("figure_table_treatment_pool", SUPPORTED_FIGURE_TREATMENTS, False),
)
TARGET_BOX_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:x|by)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
MIN_FIGURE_TARGET_BOX_WIDTH = 3.0
MIN_FIGURE_TARGET_BOX_HEIGHT = 2.0


def _issue(path: str, severity: str, message: str) -> dict[str, str]:
    return {"path": path, "severity": severity, "message": message}


def _load_json(path: Path) -> tuple[Any | None, list[dict[str, str]]]:
    if not path.exists():
        return None, []
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [_issue(str(path), "error", f"malformed JSON: {exc}")]


def _read_json_payload(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def _cached_json_payload(
    path: Path,
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] | None,
) -> tuple[Any | None, str | None]:
    if json_payload_cache is None:
        return _read_json_payload(path)
    key = path.resolve()
    if key not in json_payload_cache:
        json_payload_cache[key] = _read_json_payload(key)
    return json_payload_cache[key]


def _write_json_if_changed(path: Path, payload: Any) -> bool:
    """Write JSON only when bytes changed; return True when the file changed."""
    text = json.dumps(payload, indent=2) + "\n"
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _nested_dict(payload: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, dict) else None


def _first_dict(payload: dict[str, Any], paths: list[tuple[str, ...]]) -> dict[str, Any] | None:
    for path in paths:
        value = _nested_dict(payload, *path)
        if value is not None:
            return value
    return None


def _list_value(payload: dict[str, Any], key: str) -> list[Any] | None:
    value = payload.get(key)
    return value if isinstance(value, list) else None


def _normalize_ref(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _looks_like_local_path(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text.startswith(("http://", "https://")):
        return False
    if any(char.isspace() for char in text):
        return False
    suffix = Path(text).suffix.lower()
    return "/" in text or "\\" in text or text.startswith(".") or suffix in {
        ".py",
        ".ipynb",
        ".r",
        ".rmd",
        ".jl",
        ".sh",
        ".js",
        ".ts",
        ".csv",
        ".tsv",
        ".xlsx",
        ".xls",
        ".json",
    }


def _target_box_dimensions(value: Any) -> tuple[float, float] | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = TARGET_BOX_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1)), float(match.group(2))
    except ValueError:
        return None


def _collect_outline_refs(payload: Any) -> set[str]:
    refs: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            text = _normalize_ref(value)
            if text:
                refs.add(text)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)

    visit(payload)
    return refs


def _asset_aliases_by_path(asset_plan: Any) -> dict[str, set[str]]:
    if not isinstance(asset_plan, dict):
        return {}
    sections = {
        "images": ("asset", "image"),
        "backgrounds": ("asset", "background"),
        "charts": ("asset", "chart"),
        "tables": ("asset", "table"),
        "generated_images": ("asset", "image", "generated"),
    }
    aliases: dict[str, set[str]] = {}
    for section, prefixes in sections.items():
        entries = asset_plan.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            raw_path = str(entry.get("path") or "").strip()
            if not name or not raw_path:
                continue
            path = _normalize_ref(raw_path)
            aliases.setdefault(path, set()).update(f"{prefix}:{name.lower()}" for prefix in prefixes)
            aliases[path].update(f"{prefix}:{name}" for prefix in prefixes)
    return aliases


def _path_used_in_outline(path: str, outline_refs: set[str] | None, alias_refs: set[str] | None = None) -> bool:
    if outline_refs is None:
        return True
    normalized = _normalize_ref(path)
    candidates = {
        normalized,
        normalized.lstrip("/"),
        Path(normalized).name if normalized else "",
    }
    if normalized.startswith("assets/"):
        candidates.add(normalized[len("assets/") :])
    if alias_refs:
        candidates.update(alias_refs)
    return any(candidate and candidate in outline_refs for candidate in candidates)


def _validate_string_list(
    issues: list[dict[str, str]],
    *,
    base: str,
    payload: dict[str, Any],
    key: str,
    required: bool = False,
    allowed: set[str] | None = None,
    unsupported_severity: str = "warning",
) -> list[str]:
    value = payload.get(key)
    if value is None:
        if required:
            issues.append(_issue(f"{base}.{key}", "warning", "missing list"))
        return []
    if not isinstance(value, list):
        issues.append(_issue(f"{base}.{key}", "error", "must be a list"))
        return []
    strings = [str(item).strip() for item in value if str(item).strip()]
    if required and not strings:
        issues.append(_issue(f"{base}.{key}", "warning", "list should not be empty"))
    seen_values: dict[str, int] = {}
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        duplicate_key = text.lower() if allowed else text
        previous_idx = seen_values.get(duplicate_key)
        if previous_idx is not None:
            issues.append(
                _issue(
                    f"{base}.{key}[{idx}]",
                    "warning",
                    f"duplicate value {text!r}; already listed at {base}.{key}[{previous_idx}]",
                )
            )
        else:
            seen_values[duplicate_key] = idx
    if allowed:
        unknown = [item for item in strings if item not in allowed]
        if unknown:
            issues.append(
                _issue(
                    f"{base}.{key}",
                    unsupported_severity,
                    f"unsupported values: {', '.join(sorted(set(unknown)))}",
                )
            )
    return strings


def _unique_supported_strings(values: Any, *, allowed: set[str] | None = None) -> set[str]:
    if not isinstance(values, list):
        return set()
    unique: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        if allowed is not None and text not in allowed:
            continue
        unique.add(text.lower() if allowed else text)
    return unique


def _warn_duplicate_string_entries(
    issues: list[dict[str, str]],
    *,
    base: str,
    values: Any,
    normalizer: Callable[[str], str] | None = None,
) -> None:
    if not isinstance(values, list):
        return
    normalize = normalizer or (lambda item: item)
    seen: dict[str, int] = {}
    for idx, item in enumerate(values):
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = normalize(text)
        previous_idx = seen.get(key)
        if previous_idx is not None:
            issues.append(
                _issue(
                    f"{base}[{idx}]",
                    "warning",
                    f"duplicate entry {text!r}; already listed at {base}[{previous_idx}]",
                )
            )
        else:
            seen[key] = idx


def _resolve_workspace_path(workspace: Path | None, raw: str) -> Path | None:
    if not workspace or not raw.strip() or raw.strip().lower() == "none":
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    return (workspace / path).resolve()


def _warn_missing_path(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    raw: str,
    kind: str,
) -> None:
    resolved = _resolve_workspace_path(workspace, raw)
    if resolved is not None and not resolved.exists():
        issues.append(
            _issue(
                base,
                "warning",
                f"{kind} path is listed but does not exist yet: {raw}",
            )
        )


def _file_fingerprint(path: Path) -> dict[str, Any] | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"source_sha256": digest.hexdigest(), "source_bytes": path.stat().st_size}
    except OSError:
        return None


def _cached_file_fingerprint(
    path: Path,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None,
) -> dict[str, Any] | None:
    if fingerprint_cache is None:
        return _file_fingerprint(path)
    key = path.resolve()
    if key not in fingerprint_cache:
        fingerprint_cache[key] = _file_fingerprint(key)
    return fingerprint_cache[key]


def _is_number_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    if not text:
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


def _is_positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _image_whitespace_issues(payload: Any, *, base: str) -> list[dict[str, str]]:
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return [_issue(base, "warning", "expected image whitespace metadata object")]
    issues: list[dict[str, str]] = []
    fraction = payload.get("exterior_fraction")
    numeric_fraction: float | None = None
    if fraction is not None:
        if not isinstance(fraction, (int, float)) or isinstance(fraction, bool) or fraction < 0 or fraction > 1:
            issues.append(_issue(f"{base}.exterior_fraction", "warning", "expected a number between 0 and 1"))
        else:
            numeric_fraction = float(fraction)
    high_whitespace = payload.get("high_exterior_whitespace") is True
    if numeric_fraction is not None and numeric_fraction >= 0.45:
        high_whitespace = True
    if high_whitespace:
        percent = payload.get("exterior_percent")
        if isinstance(percent, (int, float)) and not isinstance(percent, bool):
            percent_text = f"{float(percent):.1f}%"
        elif numeric_fraction is not None:
            percent_text = f"{numeric_fraction * 100:.1f}%"
        else:
            percent_text = "high"
        issues.append(
            _issue(
                base,
                "warning",
                f"generated figure appears to have {percent_text} exterior blank area; trim or regenerate before binding",
            )
        )
    return issues


def _numeric_values_issue(values: Any, *, base: str) -> str | None:
    if not isinstance(values, list) or not values:
        return f"{base} must be a non-empty list"
    bad = [idx for idx, value in enumerate(values) if not _is_number_like(value)]
    if bad:
        return f"{base} contains non-numeric values at index(es): {', '.join(map(str, bad))}"
    return None


def _chart_payload_issue(payload: dict[str, Any], *, name: str) -> str | None:
    series = payload.get("series")
    categories = payload.get("categories") if isinstance(payload.get("categories"), list) else payload.get("labels")
    flat_values = payload.get("values")

    if isinstance(series, list) and series:
        top_categories = categories if isinstance(categories, list) and categories else None
        for idx, item in enumerate(series):
            base = f"chart JSON output '{name}' series[{idx}]"
            if not isinstance(item, dict):
                return f"{base} must be an object"
            values = item.get("values")
            issue = _numeric_values_issue(values, base=f"{base}.values")
            if issue:
                return issue
            labels = item.get("labels")
            if top_categories is not None and len(top_categories) != len(values):
                return (
                    f"{base}.values length ({len(values)}) does not match "
                    f"chart categories length ({len(top_categories)})"
                )
            if isinstance(labels, list) and labels and len(labels) != len(values):
                return (
                    f"{base}.labels length ({len(labels)}) does not match "
                    f"values length ({len(values)})"
                )
            if top_categories is None and not (isinstance(labels, list) and labels):
                return f"{base} needs labels or top-level categories"
        return None

    if isinstance(categories, list) and categories and isinstance(flat_values, list) and flat_values:
        issue = _numeric_values_issue(flat_values, base=f"chart JSON output '{name}' values")
        if issue:
            return issue
        if len(categories) != len(flat_values):
            return (
                f"chart JSON output '{name}' categories length ({len(categories)}) "
                f"does not match values length ({len(flat_values)})"
            )
        return None

    return (
        f"chart JSON output '{name}' should include either non-empty series[].values "
        "with labels/categories or top-level categories+values"
    )


def _table_payload_issue(payload: dict[str, Any], *, name: str) -> str | None:
    headers = payload.get("headers")
    rows = payload.get("rows")
    if not isinstance(headers, list) or not headers:
        return f"table output '{name}' must include a non-empty headers list"
    if not isinstance(rows, list) or not rows:
        return f"table output '{name}' must include a non-empty rows list"
    width = len(headers)
    for idx, row in enumerate(rows):
        if not isinstance(row, list):
            return f"table output '{name}' rows[{idx}] must be a list"
        if len(row) != width:
            return (
                f"table output '{name}' rows[{idx}] has {len(row)} cells "
                f"but headers define {width} columns"
            )
    column_weights = payload.get("column_weights")
    if column_weights is not None:
        if not isinstance(column_weights, list):
            return f"table output '{name}' column_weights must be a list when present"
        if len(column_weights) != width:
            return (
                f"table output '{name}' column_weights length ({len(column_weights)}) "
                f"does not match header count ({width})"
            )
        if any(not _is_number_like(value) for value in column_weights):
            return f"table output '{name}' column_weights must contain only numeric values"
    return None


def _looks_like_generated_artifact(payload: dict[str, Any], *, producer: str = "") -> bool:
    provenance = str(payload.get("provenance") or "").lower()
    generated_by = ""
    metadata = payload.get("analysis_metadata")
    if isinstance(metadata, dict):
        generated_by = str(metadata.get("generated_by") or "").lower()
    return any(
        marker in text
        for text in (provenance, generated_by)
        for marker in ("assets/make_figures.py", "scaffold_figure_artifacts", "generated from", "summary table generated")
    )


def _analysis_metadata_fingerprint_issue(
    metadata: dict[str, Any],
    *,
    workspace: Path | None,
    item_name: str,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None = None,
) -> str | None:
    source_path = str(metadata.get("source_path") or "").strip()
    if not source_path:
        return None
    resolved = _resolve_workspace_path(workspace, source_path)
    if resolved is None or not resolved.exists():
        return None
    fingerprint = _cached_file_fingerprint(resolved, fingerprint_cache)
    if fingerprint is None:
        return None
    expected_sha = str(metadata.get("source_sha256") or "").strip()
    if expected_sha and expected_sha != fingerprint["source_sha256"]:
        return f"{item_name} analysis_metadata.source_sha256 does not match current source file"
    expected_bytes = metadata.get("source_bytes")
    if isinstance(expected_bytes, (int, float)) and not isinstance(expected_bytes, bool):
        if int(expected_bytes) != int(fingerprint["source_bytes"]):
            return f"{item_name} analysis_metadata.source_bytes does not match current source file"
    return None


def _analysis_metadata_producer_issue(
    metadata: dict[str, Any],
    *,
    workspace: Path | None,
    item_name: str,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None = None,
) -> str | None:
    producer_path = str(metadata.get("producer_path") or metadata.get("generated_by") or "").strip()
    expected_sha = str(metadata.get("producer_sha256") or "").strip()
    expected_bytes = metadata.get("producer_bytes")
    if not producer_path or (not expected_sha and expected_bytes is None):
        return None
    resolved = _resolve_workspace_path(workspace, producer_path)
    if resolved is None or not resolved.exists():
        return None
    fingerprint = _cached_file_fingerprint(resolved, fingerprint_cache)
    if fingerprint is None:
        return None
    if expected_sha and expected_sha != fingerprint["source_sha256"]:
        return f"{item_name} analysis_metadata.producer_sha256 does not match current producer script"
    if isinstance(expected_bytes, (int, float)) and not isinstance(expected_bytes, bool):
        if int(expected_bytes) != int(fingerprint["source_bytes"]):
            return f"{item_name} analysis_metadata.producer_bytes does not match current producer script"
    return None


def _selected_columns_issue(payload: dict[str, Any], *, item_name: str) -> str | None:
    selected_columns = payload.get("selected_columns")
    if selected_columns is None:
        return None
    if not (
        isinstance(selected_columns, list)
        and selected_columns
        and all(isinstance(item, str) and item.strip() for item in selected_columns)
    ):
        return f"{item_name}.selected_columns should be a non-empty list of column names"
    expected_columns: list[str] = []
    label_col = payload.get("label_col")
    if isinstance(label_col, str) and label_col.strip():
        expected_columns.append(label_col)
    value_cols = payload.get("value_cols")
    if isinstance(value_cols, list):
        expected_columns.extend(
            item
            for item in value_cols
            if isinstance(item, str) and item.strip()
        )
    if expected_columns and not set(expected_columns).issubset(set(selected_columns)):
        return f"{item_name}.selected_columns should include label_col and value_cols"
    return None


def _analysis_metadata_issue(
    payload: dict[str, Any],
    *,
    name: str,
    kind: str,
    workspace: Path | None = None,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None = None,
) -> str | None:
    if not _looks_like_generated_artifact(payload):
        return None
    metadata = payload.get("analysis_metadata")
    if not isinstance(metadata, dict):
        return f"{kind} '{name}' is generated but missing analysis_metadata"
    required_strings = ("source_path", "source_sha256", "generated_by")
    for key in required_strings:
        if not str(metadata.get(key) or "").strip():
            return f"{kind} '{name}' analysis_metadata.{key} is missing"
    for key in ("source_bytes", "rows_used", "series_count"):
        value = metadata.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            return f"{kind} '{name}' analysis_metadata.{key} should be a non-negative number"
    if kind == "chart JSON output":
        value = metadata.get("points")
        if not isinstance(value, (int, float)) or value < 0:
            return f"{kind} '{name}' analysis_metadata.points should be a non-negative number"
    fingerprint_issue = _analysis_metadata_fingerprint_issue(
        metadata,
        workspace=workspace,
        item_name=f"{kind} '{name}'",
        fingerprint_cache=fingerprint_cache,
    )
    if fingerprint_issue:
        return fingerprint_issue
    producer_issue = _analysis_metadata_producer_issue(
        metadata,
        workspace=workspace,
        item_name=f"{kind} '{name}'",
        fingerprint_cache=fingerprint_cache,
    )
    if producer_issue:
        return producer_issue
    selected_columns_issue = _selected_columns_issue(
        metadata,
        item_name=f"{kind} '{name}' analysis_metadata",
    )
    if selected_columns_issue:
        return selected_columns_issue
    export_issue = _figure_export_metadata_issue(
        metadata,
        item_name=f"{kind} '{name}'",
    )
    if export_issue:
        return export_issue
    return None


def _figure_export_metadata_issue(metadata: dict[str, Any], *, item_name: str) -> str | None:
    target_box = str(metadata.get("target_box") or "").strip()
    if not target_box:
        return f"{item_name} analysis_metadata.target_box is missing"
    if _target_box_dimensions(target_box) is None:
        return f"{item_name} analysis_metadata.target_box should include width x height in inches"
    figure_size = metadata.get("figure_size_inches")
    if not isinstance(figure_size, list) or len(figure_size) != 2 or not all(
        _is_positive_number(item) for item in figure_size
    ):
        return f"{item_name} analysis_metadata.figure_size_inches should be [width, height] positive inches"
    for key in ("figure_dpi", "axis_label_min_pt"):
        if not _is_positive_number(metadata.get(key)):
            return f"{item_name} analysis_metadata.{key} should be a positive number"
    return None


def _figure_output_export_metadata_issue(output: dict[str, Any], *, item_name: str) -> str | None:
    figure_size = output.get("figure_size_inches")
    if not isinstance(figure_size, list) or len(figure_size) != 2 or not all(
        _is_positive_number(item) for item in figure_size
    ):
        return f"{item_name}.figure_size_inches should be [width, height] positive inches"
    for key in ("figure_dpi", "axis_label_min_pt"):
        if not _is_positive_number(output.get(key)):
            return f"{item_name}.{key} should be a positive number"
    return None


def _registry_analysis_metadata_issue(
    item: dict[str, Any],
    *,
    item_name: str,
    workspace: Path | None = None,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None = None,
) -> str | None:
    if not _looks_like_generated_artifact(item, producer=str(item.get("producer") or "")):
        return None
    metadata = item.get("analysis_metadata")
    if not isinstance(metadata, dict):
        return f"{item_name} is generated but missing analysis_metadata"
    for key in ("source_path", "source_sha256", "generated_by"):
        if not str(metadata.get(key) or "").strip():
            return f"{item_name} analysis_metadata.{key} is missing"
    value = metadata.get("source_bytes")
    if not isinstance(value, (int, float)) or value < 0:
        return f"{item_name} analysis_metadata.source_bytes should be a non-negative number"
    fingerprint_issue = _analysis_metadata_fingerprint_issue(
        metadata,
        workspace=workspace,
        item_name=item_name,
        fingerprint_cache=fingerprint_cache,
    )
    if fingerprint_issue:
        return fingerprint_issue
    producer_issue = _analysis_metadata_producer_issue(
        metadata,
        workspace=workspace,
        item_name=item_name,
        fingerprint_cache=fingerprint_cache,
    )
    if producer_issue:
        return producer_issue
    selected_columns_issue = _selected_columns_issue(
        metadata,
        item_name=f"{item_name} analysis_metadata",
    )
    if selected_columns_issue:
        return selected_columns_issue
    export_issue = _figure_export_metadata_issue(metadata, item_name=item_name)
    if export_issue:
        return export_issue
    return None


def _validate_declared_output_payload(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    raw: str,
    kind: str,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None = None,
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] | None = None,
) -> None:
    resolved = _resolve_workspace_path(workspace, raw)
    if resolved is None or not resolved.exists():
        return
    if kind == "table output":
        payload, error = _cached_json_payload(resolved, json_payload_cache)
        if error:
            issues.append(_issue(base, "warning", f"table output is not valid JSON: {error}"))
            return
        if not isinstance(payload, dict):
            issues.append(_issue(base, "warning", "table output JSON root should be an object"))
            return
        issue = _table_payload_issue(payload, name=raw)
        if issue:
            issues.append(_issue(base, "warning", issue))
        metadata_issue = _analysis_metadata_issue(
            payload,
            name=raw,
            kind=kind,
            workspace=workspace,
            fingerprint_cache=fingerprint_cache,
        )
        if metadata_issue:
            issues.append(_issue(base, "warning", metadata_issue))
    elif kind == "chart JSON output":
        payload, error = _cached_json_payload(resolved, json_payload_cache)
        if error:
            issues.append(_issue(base, "warning", f"chart JSON output is not valid JSON: {error}"))
            return
        if not isinstance(payload, dict):
            issues.append(_issue(base, "warning", "chart JSON output root should be an object"))
            return
        issue = _chart_payload_issue(payload, name=raw)
        if issue:
            issues.append(_issue(base, "warning", issue))
        metadata_issue = _analysis_metadata_issue(
            payload,
            name=raw,
            kind=kind,
            workspace=workspace,
            fingerprint_cache=fingerprint_cache,
        )
        if metadata_issue:
            issues.append(_issue(base, "warning", metadata_issue))


def _validate_asset_plan_payload(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    entry: dict[str, Any],
    section: str,
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] | None = None,
) -> None:
    if section not in {"charts", "tables"}:
        return
    raw_path = str(entry.get("path") or "").strip()
    label = "chart JSON" if section == "charts" else "table JSON"
    name = str(entry.get("name") or raw_path or base).strip()
    payload: dict[str, Any] | None = None
    issue_path = base

    if raw_path:
        if raw_path.startswith(("http://", "https://")):
            return
        resolved = _resolve_workspace_path(workspace, raw_path)
        if resolved is None or not resolved.exists():
            return
        issue_path = f"{base}.path"
        parsed, error = _cached_json_payload(resolved, json_payload_cache)
        if error:
            issues.append(_issue(issue_path, "warning", f"asset_plan {label} is not valid JSON: {error}"))
            return
        if not isinstance(parsed, dict):
            issues.append(_issue(issue_path, "warning", f"asset_plan {label} root should be an object"))
            return
        payload = parsed
    else:
        payload = entry

    if section == "charts":
        issue = _chart_payload_issue(payload, name=name)
    else:
        issue = _table_payload_issue(payload, name=name)
    if issue:
        issues.append(_issue(issue_path, "warning", issue))


def _validate_generated_image_metadata(
    issues: list[dict[str, str]],
    *,
    base: str,
    entry: dict[str, Any],
) -> None:
    for key in ("prompt", "model", "purpose"):
        if not str(entry.get(key) or "").strip():
            issues.append(
                _issue(
                    f"{base}.{key}",
                    "warning",
                    f"generated image should include {key} metadata for disclosure and reproducibility",
                )
            )


def _validate_local_visual_asset_provenance(
    issues: list[dict[str, str]],
    *,
    base: str,
    entry: dict[str, Any],
    section: str,
) -> None:
    raw_path = str(entry.get("path") or "").strip()
    if section not in {"images", "backgrounds"} or not raw_path or raw_path.startswith(("http://", "https://")):
        return
    provenance_fields = ("source_note", "source_url", "source_page", "license", "provenance")
    if any(str(entry.get(key) or "").strip() for key in provenance_fields):
        return
    issues.append(
        _issue(
            base,
            "warning",
            (
                f"local asset_plan {section[:-1]} should include source_note, source_url, "
                "source_page, license, or provenance for attribution audit"
            ),
        )
    )


def _registry_structured_payload_kind(item: dict[str, Any], path: str) -> str | None:
    candidates: list[str] = []
    for key in ("kind", "type", "artifact_type", "role"):
        value = str(item.get(key) or "").strip().lower()
        if value:
            candidates.append(value)
    metadata = item.get("analysis_metadata")
    if isinstance(metadata, dict):
        value = str(metadata.get("artifact_role") or "").strip().lower()
        if value:
            candidates.append(value)

    normalized_candidates = [value.replace("-", "_").replace(" ", "_") for value in candidates]
    if any("chart" in value for value in normalized_candidates):
        return "chart JSON output"
    if any("table" in value for value in normalized_candidates):
        return "table output"

    normalized_path = _normalize_ref(path).lower()
    if normalized_path.endswith(".json"):
        parts = set(normalized_path.split("/"))
        if "charts" in parts:
            return "chart JSON output"
        if "tables" in parts:
            return "table output"
    return None


def _mtime_for_path(workspace: Path | None, raw: str) -> float | None:
    resolved = _resolve_workspace_path(workspace, raw)
    if resolved is None or not resolved.exists():
        return None
    try:
        return resolved.stat().st_mtime
    except OSError:
        return None


def _newest_artifact_source(
    plan: dict[str, Any],
    figure_contract: dict[str, Any] | None,
    *,
    workspace: Path | None,
) -> tuple[str, float] | None:
    candidates: list[tuple[str, float]] = []
    for key in ("candidate_data_files", "spreadsheet_inputs", "required_scripts", "figure_scripts"):
        for raw in _list_value(plan, key) or []:
            if not isinstance(raw, str):
                continue
            mtime = _mtime_for_path(workspace, raw)
            if mtime is not None:
                candidates.append((raw, mtime))
    if isinstance(figure_contract, dict):
        script = str(figure_contract.get("script") or "").strip()
        if script and script.lower() != "none":
            mtime = _mtime_for_path(workspace, script)
            if mtime is not None:
                candidates.append((script, mtime))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[1])


def _warn_if_output_stale(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    raw: str,
    kind: str,
    newest_source: tuple[str, float] | None,
    rebuild_commands: list[str],
) -> None:
    if newest_source is None:
        return
    output_mtime = _mtime_for_path(workspace, raw)
    if output_mtime is None:
        return
    source_path, source_mtime = newest_source
    # Give the filesystem a little rounding tolerance for outputs generated in
    # the same second as the script rewrite.
    if output_mtime + 1.0 >= source_mtime:
        return
    command_hint = rebuild_commands[0] if rebuild_commands else "the declared rebuild command"
    issues.append(
        _issue(
            base,
            "warning",
            f"{kind} appears older than source/script {source_path!r}; rerun `{command_hint}` before final build",
        )
    )


def _validate_artifact_rebuild_context(
    issues: list[dict[str, str]],
    *,
    base: str,
    context: Any,
    expected_manifest: str = "",
    expected_analysis_summary: str = "",
    expected_output_count: int | None = None,
    expected_data_specs_sha256: str = "",
    expected_producer_path: str = "",
) -> None:
    if context is None:
        return
    if not isinstance(context, dict):
        issues.append(_issue(base, "warning", "artifact rebuild context should be an object"))
        return
    if context.get("context_version") != "presentation_skill_artifact_rebuild_context_v1":
        issues.append(
            _issue(
                f"{base}.context_version",
                "warning",
                "expected presentation_skill_artifact_rebuild_context_v1",
            )
        )
    for key in ("producer_path", "producer_sha256", "data_specs_sha256"):
        if not str(context.get(key) or "").strip():
            issues.append(_issue(f"{base}.{key}", "warning", f"missing {key}"))
    producer_path = str(context.get("producer_path") or "").strip()
    if expected_producer_path and producer_path and _normalize_ref(producer_path) != _normalize_ref(expected_producer_path):
        issues.append(
            _issue(
                f"{base}.producer_path",
                "warning",
                "rebuild context producer_path should match the declared figure producer",
            )
        )
    data_specs_sha256 = str(context.get("data_specs_sha256") or "").strip()
    if (
        expected_data_specs_sha256
        and data_specs_sha256
        and data_specs_sha256 != expected_data_specs_sha256
    ):
        issues.append(
            _issue(
                f"{base}.data_specs_sha256",
                "warning",
                "rebuild context data_specs_sha256 should match artifact metadata",
            )
        )
    for key, expected in (
        ("artifact_manifest", expected_manifest),
        ("analysis_summary", expected_analysis_summary),
    ):
        value = str(context.get(key) or "").strip()
        if expected and value and _normalize_ref(value) != _normalize_ref(expected):
            issues.append(
                _issue(
                    f"{base}.{key}",
                    "warning",
                    f"rebuild context {key} should match declared artifact paths",
                )
            )
    output_count = context.get("output_count")
    if output_count is not None and (
        not isinstance(output_count, int) or isinstance(output_count, bool) or output_count < 0
    ):
        issues.append(_issue(f"{base}.output_count", "warning", "expected a non-negative integer output count"))
    elif expected_output_count is not None and output_count is not None and output_count != expected_output_count:
        issues.append(
            _issue(
                f"{base}.output_count",
                "warning",
                f"output_count {output_count} does not match expected {expected_output_count}",
            )
        )
    for key in ("source_paths", "artifact_paths"):
        value = context.get(key)
        if value is not None and not (
            isinstance(value, list)
            and all(isinstance(item, str) and item.strip() for item in value)
        ):
            issues.append(_issue(f"{base}.{key}", "warning", "expected a list of non-empty path strings"))
    outputs = context.get("outputs")
    if outputs is not None:
        if not isinstance(outputs, dict):
            issues.append(_issue(f"{base}.outputs", "warning", "expected an object of generated output path lists"))
        else:
            for key in ("figures", "chart_json", "summary_tables"):
                value = outputs.get(key)
                if value is not None and not (
                    isinstance(value, list)
                    and all(isinstance(item, str) and item.strip() for item in value)
                ):
                    issues.append(_issue(f"{base}.outputs.{key}", "warning", "expected a list of output path strings"))
    commands = context.get("commands")
    if commands is not None:
        if not isinstance(commands, dict):
            issues.append(_issue(f"{base}.commands", "warning", "expected an object of rebuild command strings"))
        else:
            rebuild = str(commands.get("rebuild_figures") or "").strip()
            inspect = str(commands.get("inspect_manifest") or "").strip()
            validate = str(commands.get("validate_planning") or "").strip()
            if expected_producer_path and rebuild and expected_producer_path not in rebuild:
                issues.append(
                    _issue(
                        f"{base}.commands.rebuild_figures",
                        "warning",
                        "rebuild_figures command should include the figure script path",
                    )
                )
            if inspect and "inspect_artifact_manifest.py" not in inspect:
                issues.append(
                    _issue(
                        f"{base}.commands.inspect_manifest",
                        "warning",
                        "inspect_manifest command should call inspect_artifact_manifest.py",
                    )
                )
            if validate and "validate_planning.py" not in validate:
                issues.append(
                    _issue(
                        f"{base}.commands.validate_planning",
                        "warning",
                        "validate_planning command should call validate_planning.py",
                    )
                )


def _validate_artifact_manifest_payload(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    raw: str,
    registered_paths: set[str],
    registry_present: bool,
    fingerprint_cache: dict[Path, dict[str, Any] | None] | None = None,
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] | None = None,
) -> None:
    resolved = _resolve_workspace_path(workspace, raw)
    if resolved is None or not resolved.exists():
        return
    payload, error = _cached_json_payload(resolved, json_payload_cache)
    if error:
        issues.append(_issue(base, "warning", f"artifact manifest is not valid JSON: {error}"))
        return
    if not isinstance(payload, dict):
        issues.append(_issue(base, "warning", "artifact manifest JSON root should be an object"))
        return

    if payload.get("manifest_version") != "presentation_skill_artifact_manifest_v1":
        issues.append(
            _issue(
                f"{base}.manifest_version",
                "warning",
                "expected presentation_skill_artifact_manifest_v1",
            )
        )
    if not str(payload.get("generated_by") or "").strip():
        issues.append(_issue(f"{base}.generated_by", "warning", "missing manifest producer"))
    if not str(payload.get("data_specs_sha256") or "").strip():
        issues.append(_issue(f"{base}.data_specs_sha256", "warning", "missing data spec fingerprint"))
    manifest_producer_metadata = {
        "producer_path": payload.get("producer_path") or payload.get("generated_by"),
        "producer_sha256": payload.get("producer_sha256"),
        "producer_bytes": payload.get("producer_bytes"),
    }
    manifest_producer_issue = _analysis_metadata_producer_issue(
        manifest_producer_metadata,
        workspace=workspace,
        item_name="artifact manifest",
        fingerprint_cache=fingerprint_cache,
    )
    if manifest_producer_issue:
        issues.append(_issue(f"{base}.producer_sha256", "warning", manifest_producer_issue))

    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        issues.append(_issue(f"{base}.outputs", "warning", "must be a list"))
        return

    output_count = payload.get("output_count")
    if not isinstance(output_count, int) or isinstance(output_count, bool):
        issues.append(_issue(f"{base}.output_count", "warning", "expected an integer output count"))
    elif output_count != len(outputs):
        issues.append(
            _issue(
                f"{base}.output_count",
                "warning",
                f"output_count {output_count} does not match outputs length {len(outputs)}",
            )
        )
    _validate_artifact_rebuild_context(
        issues,
        base=f"{base}.rebuild_context",
        context=payload.get("rebuild_context") if "rebuild_context" in payload else None,
        expected_manifest=raw,
        expected_analysis_summary=str(payload.get("analysis_summary") or ""),
        expected_output_count=len(outputs),
        expected_data_specs_sha256=str(payload.get("data_specs_sha256") or ""),
        expected_producer_path=str(payload.get("producer_path") or payload.get("generated_by") or ""),
    )

    seen_output_ids: dict[str, int] = {}
    seen_artifact_ids: dict[str, str] = {}
    seen_artifact_paths: dict[str, str] = {}
    role_alias_prefix = {
        "figure": "image:",
        "chart_json": "chart:",
        "summary_table": "table:",
    }
    allowed_roles = set(role_alias_prefix)

    for output_idx, output in enumerate(outputs):
        output_base = f"{base}.outputs[{output_idx}]"
        if not isinstance(output, dict):
            issues.append(_issue(output_base, "warning", "manifest output entry must be an object"))
            continue
        output_id = str(output.get("id") or "").strip()
        if not output_id:
            issues.append(_issue(f"{output_base}.id", "warning", "missing output id"))
        else:
            output_key = output_id.lower()
            previous_idx = seen_output_ids.get(output_key)
            if previous_idx is not None:
                issues.append(
                    _issue(
                        f"{output_base}.id",
                        "warning",
                        f"duplicate manifest output id {output_id!r}; already used by outputs[{previous_idx}]",
                    )
                )
            else:
                seen_output_ids[output_key] = output_idx

        for key in ("source_path", "source_label"):
            if key in output and not str(output.get(key) or "").strip():
                issues.append(_issue(f"{output_base}.{key}", "warning", f"empty {key}"))
        output_selected_issue = _selected_columns_issue(output, item_name=output_base)
        if output_selected_issue:
            issues.append(_issue(f"{output_base}.selected_columns", "warning", output_selected_issue))

        metadata = output.get("analysis_metadata")
        if not isinstance(metadata, dict):
            issues.append(_issue(f"{output_base}.analysis_metadata", "warning", "missing source analysis metadata"))
        else:
            for key in ("source_path", "source_sha256", "generated_by"):
                if not str(metadata.get(key) or "").strip():
                    issues.append(_issue(f"{output_base}.analysis_metadata.{key}", "warning", f"missing {key}"))
            source_bytes = metadata.get("source_bytes")
            if source_bytes is not None and (
                not isinstance(source_bytes, (int, float))
                or isinstance(source_bytes, bool)
                or source_bytes < 0
            ):
                issues.append(
                    _issue(
                        f"{output_base}.analysis_metadata.source_bytes",
                        "warning",
                        "expected a non-negative source byte count",
                    )
                )
            for key in ("series_count", "points", "rows_used"):
                value = metadata.get(key)
                if value is not None and (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or value < 0
                ):
                    issues.append(
                        _issue(
                            f"{output_base}.analysis_metadata.{key}",
                            "warning",
                            "expected a non-negative number",
                        )
                    )
            fingerprint_issue = _analysis_metadata_fingerprint_issue(
                metadata,
                workspace=workspace,
                item_name=f"artifact manifest output {output_idx}",
                fingerprint_cache=fingerprint_cache,
            )
            if fingerprint_issue:
                issues.append(_issue(f"{output_base}.analysis_metadata", "warning", fingerprint_issue))
            producer_issue = _analysis_metadata_producer_issue(
                metadata,
                workspace=workspace,
                item_name=f"artifact manifest output {output_idx}",
                fingerprint_cache=fingerprint_cache,
            )
            if producer_issue:
                issues.append(_issue(f"{output_base}.analysis_metadata", "warning", producer_issue))
            selected_columns_issue = _selected_columns_issue(
                metadata,
                item_name=f"{output_base}.analysis_metadata",
            )
            if selected_columns_issue:
                issues.append(_issue(f"{output_base}.analysis_metadata.selected_columns", "warning", selected_columns_issue))
            issues.extend(
                _image_whitespace_issues(
                    metadata.get("image_whitespace"),
                    base=f"{output_base}.analysis_metadata.image_whitespace",
                )
            )

        artifacts = output.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            issues.append(_issue(f"{output_base}.artifacts", "warning", "must be a non-empty list"))
            continue

        for artifact_idx, artifact in enumerate(artifacts):
            artifact_base = f"{output_base}.artifacts[{artifact_idx}]"
            if not isinstance(artifact, dict):
                issues.append(_issue(artifact_base, "warning", "manifest artifact entry must be an object"))
                continue

            artifact_id = str(artifact.get("id") or "").strip()
            if not artifact_id:
                issues.append(_issue(f"{artifact_base}.id", "warning", "missing artifact id"))
            else:
                artifact_id_key = artifact_id.lower()
                previous_path = seen_artifact_ids.get(artifact_id_key)
                if previous_path is not None:
                    issues.append(
                        _issue(
                            f"{artifact_base}.id",
                            "warning",
                            f"duplicate manifest artifact id {artifact_id!r}; already used at {previous_path}",
                        )
                    )
                else:
                    seen_artifact_ids[artifact_id_key] = f"outputs[{output_idx}].artifacts[{artifact_idx}]"

            role = str(artifact.get("role") or "").strip()
            if not role:
                issues.append(_issue(f"{artifact_base}.role", "warning", "missing artifact role"))
            elif role not in allowed_roles:
                issues.append(
                    _issue(
                        f"{artifact_base}.role",
                        "warning",
                        f"unsupported artifact role {role!r}; expected one of {', '.join(sorted(allowed_roles))}",
                    )
                )

            alias = str(artifact.get("alias") or "").strip()
            if not alias:
                issues.append(_issue(f"{artifact_base}.alias", "warning", "missing staged alias"))
            else:
                prefix = role_alias_prefix.get(role)
                if prefix and not alias.startswith(prefix):
                    issues.append(
                        _issue(
                            f"{artifact_base}.alias",
                            "warning",
                            f"{role} artifacts should use a {prefix!r} alias",
                        )
                    )

            path = str(artifact.get("path") or "").strip()
            if not path:
                issues.append(_issue(f"{artifact_base}.path", "warning", "missing artifact path"))
                continue
            _warn_missing_path(
                issues,
                workspace=workspace,
                base=f"{artifact_base}.path",
                raw=path,
                kind="artifact manifest",
            )
            normalized_path = _normalize_ref(path)
            previous_path = seen_artifact_paths.get(normalized_path)
            if previous_path is not None:
                issues.append(
                    _issue(
                        f"{artifact_base}.path",
                        "warning",
                        f"duplicate manifest artifact path {path!r}; already used at {previous_path}",
                    )
                )
            else:
                seen_artifact_paths[normalized_path] = f"outputs[{output_idx}].artifacts[{artifact_idx}]"
            if registry_present and normalized_path not in registered_paths:
                issues.append(
                    _issue(
                        f"{artifact_base}.path",
                        "warning",
                        f"manifest artifact {path!r} is not listed in artifact_registry",
                    )
                )

            fingerprint = artifact.get("fingerprint")
            if not isinstance(fingerprint, dict):
                issues.append(_issue(f"{artifact_base}.fingerprint", "warning", "missing artifact fingerprint"))
                continue
            expected_sha = str(fingerprint.get("sha256") or "").strip()
            expected_bytes = fingerprint.get("bytes")
            if not expected_sha:
                issues.append(_issue(f"{artifact_base}.fingerprint.sha256", "warning", "missing artifact sha256"))
            if (
                not isinstance(expected_bytes, int)
                or isinstance(expected_bytes, bool)
                or expected_bytes <= 0
            ):
                issues.append(
                    _issue(
                        f"{artifact_base}.fingerprint.bytes",
                        "warning",
                        "expected a positive artifact byte count",
                    )
                )

            artifact_path = _resolve_workspace_path(workspace, path)
            if artifact_path is None or not artifact_path.exists():
                continue
            actual_fingerprint = _cached_file_fingerprint(artifact_path, fingerprint_cache)
            if actual_fingerprint is None:
                continue
            if expected_sha and expected_sha != actual_fingerprint["source_sha256"]:
                issues.append(
                    _issue(
                        f"{artifact_base}.fingerprint.sha256",
                        "warning",
                        "artifact sha256 does not match current artifact file",
                    )
                )
            if isinstance(expected_bytes, int) and not isinstance(expected_bytes, bool):
                if expected_bytes != int(actual_fingerprint["source_bytes"]):
                    issues.append(
                        _issue(
                            f"{artifact_base}.fingerprint.bytes",
                            "warning",
                            "artifact byte count does not match current artifact file",
                        )
                    )
            if role in {"chart_json", "summary_table"}:
                payload, error = _cached_json_payload(artifact_path, json_payload_cache)
                if error:
                    issues.append(
                        _issue(
                            f"{artifact_base}.path",
                            "warning",
                            f"manifest artifact structured payload is not valid JSON: {error}",
                        )
                    )
                    continue
                if not isinstance(payload, dict):
                    issues.append(
                        _issue(
                            f"{artifact_base}.path",
                            "warning",
                            "manifest artifact structured payload root should be an object",
                        )
                    )
                    continue
                payload_issue = (
                    _chart_payload_issue(payload, name=path)
                    if role == "chart_json"
                    else _table_payload_issue(payload, name=path)
                )
                if payload_issue:
                    issues.append(_issue(f"{artifact_base}.path", "warning", payload_issue))
                payload_metadata = payload.get("analysis_metadata")
                expected_whitespace = metadata.get("image_whitespace") if isinstance(metadata, dict) else None
                if isinstance(payload_metadata, dict):
                    payload_whitespace = payload_metadata.get("image_whitespace")
                    if expected_whitespace is not None and payload_whitespace is None:
                        issues.append(
                            _issue(
                                f"{artifact_base}.analysis_metadata.image_whitespace",
                                "warning",
                                "structured artifact metadata is missing manifest image_whitespace; rerun figure generation",
                            )
                        )
                    issues.extend(
                        _image_whitespace_issues(
                            payload_whitespace,
                            base=f"{artifact_base}.analysis_metadata.image_whitespace",
                        )
                    )
                else:
                    issues.append(
                        _issue(
                            f"{artifact_base}.analysis_metadata",
                            "warning",
                            "generated structured artifact is missing analysis_metadata",
                        )
                    )


def _validate_analysis_summary_payload(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    raw: str,
    artifact_manifest_path: str,
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] | None = None,
) -> None:
    resolved = _resolve_workspace_path(workspace, raw)
    if resolved is None or not resolved.exists():
        return
    payload, error = _cached_json_payload(resolved, json_payload_cache)
    if error:
        issues.append(_issue(base, "warning", f"analysis summary is not valid JSON: {error}"))
        return
    if not isinstance(payload, dict):
        issues.append(_issue(base, "warning", "analysis summary JSON root should be an object"))
        return

    if payload.get("summary_version") != "presentation_skill_analysis_summary_v1":
        issues.append(
            _issue(
                f"{base}.summary_version",
                "warning",
                "expected presentation_skill_analysis_summary_v1",
            )
        )
    summary_manifest = str(payload.get("artifact_manifest") or "").strip()
    if artifact_manifest_path and summary_manifest and _normalize_ref(summary_manifest) != _normalize_ref(artifact_manifest_path):
        issues.append(
            _issue(
                f"{base}.artifact_manifest",
                "warning",
                "analysis summary artifact_manifest should match analysis_artifact_plan.artifact_manifest",
            )
        )
    if not str(payload.get("data_specs_sha256") or "").strip():
        issues.append(_issue(f"{base}.data_specs_sha256", "warning", "missing data spec fingerprint"))

    manifest_output_count: int | None = None
    manifest_output_ids: set[str] = set()
    manifest_total_points: float | None = None
    if artifact_manifest_path:
        manifest_resolved = _resolve_workspace_path(workspace, artifact_manifest_path)
        if manifest_resolved is not None and manifest_resolved.exists():
            manifest_payload, manifest_error = _cached_json_payload(manifest_resolved, json_payload_cache)
            if manifest_error is None and isinstance(manifest_payload, dict):
                manifest_outputs = manifest_payload.get("outputs")
                if isinstance(manifest_outputs, list):
                    manifest_output_count = len(manifest_outputs)
                    total = 0.0
                    has_points = False
                    points_complete = True
                    for manifest_output in manifest_outputs:
                        if not isinstance(manifest_output, dict):
                            points_complete = False
                            continue
                        output_id = str(manifest_output.get("id") or "").strip()
                        if output_id:
                            manifest_output_ids.add(output_id.lower())
                        raw_points = manifest_output.get("points")
                        metadata = (
                            manifest_output.get("analysis_metadata")
                            if isinstance(manifest_output.get("analysis_metadata"), dict)
                            else {}
                        )
                        if raw_points is None:
                            raw_points = metadata.get("points")
                        if raw_points is None:
                            points_complete = False
                            continue
                        if (
                            isinstance(raw_points, (int, float))
                            and not isinstance(raw_points, bool)
                            and raw_points >= 0
                        ):
                            total += float(raw_points)
                            has_points = True
                        else:
                            points_complete = False
                    if has_points and points_complete:
                        manifest_total_points = total

    source_paths = payload.get("source_paths")
    if source_paths is not None and not isinstance(source_paths, list):
        issues.append(_issue(f"{base}.source_paths", "warning", "expected a list of source paths"))
        source_path_set: set[str] = set()
    else:
        source_path_set = {
            _normalize_ref(str(item))
            for item in (source_paths or [])
            if isinstance(item, str) and str(item).strip()
        }
        for idx, item in enumerate(source_paths or []):
            if not isinstance(item, str):
                issues.append(_issue(f"{base}.source_paths[{idx}]", "warning", "expected a source path string"))
                continue
            _warn_missing_path(
                issues,
                workspace=workspace,
                base=f"{base}.source_paths[{idx}]",
                raw=item,
                kind="analysis summary source",
            )

    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        issues.append(_issue(f"{base}.datasets", "warning", "must be a list"))
        return
    output_count = payload.get("output_count")
    if not isinstance(output_count, int) or isinstance(output_count, bool):
        issues.append(_issue(f"{base}.output_count", "warning", "expected an integer output count"))
    elif output_count != len(datasets):
        issues.append(
            _issue(
                f"{base}.output_count",
                "warning",
                f"output_count {output_count} does not match datasets length {len(datasets)}",
            )
        )
    if manifest_output_count is not None:
        if isinstance(output_count, int) and not isinstance(output_count, bool) and output_count != manifest_output_count:
            issues.append(
                _issue(
                    f"{base}.output_count",
                    "warning",
                    (
                        f"output_count {output_count} does not match artifact manifest "
                        f"outputs length {manifest_output_count}"
                    ),
                )
            )
        if len(datasets) != manifest_output_count:
            issues.append(
                _issue(
                    f"{base}.datasets",
                    "warning",
                    (
                        f"datasets length {len(datasets)} does not match artifact manifest "
                        f"outputs length {manifest_output_count}"
                    ),
                )
            )
    expected_summary_output_count: int | None = None
    if manifest_output_count is not None:
        expected_summary_output_count = manifest_output_count
    elif isinstance(output_count, int) and not isinstance(output_count, bool):
        expected_summary_output_count = output_count
    _validate_artifact_rebuild_context(
        issues,
        base=f"{base}.rebuild_context",
        context=payload.get("rebuild_context") if "rebuild_context" in payload else None,
        expected_manifest=artifact_manifest_path or summary_manifest,
        expected_analysis_summary=raw,
        expected_output_count=expected_summary_output_count,
        expected_data_specs_sha256=str(payload.get("data_specs_sha256") or ""),
        expected_producer_path=str(payload.get("producer_path") or payload.get("generated_by") or ""),
    )

    total_points = payload.get("total_points")
    if total_points is not None and (
        not isinstance(total_points, (int, float))
        or isinstance(total_points, bool)
        or total_points < 0
    ):
        issues.append(_issue(f"{base}.total_points", "warning", "expected a non-negative point count"))
    elif manifest_total_points is not None and total_points is not None and float(total_points) != manifest_total_points:
        manifest_points_text = (
            str(int(manifest_total_points))
            if manifest_total_points.is_integer()
            else f"{manifest_total_points:g}"
        )
        issues.append(
            _issue(
                f"{base}.total_points",
                "warning",
                f"total_points {total_points} does not match artifact manifest output points {manifest_points_text}",
            )
        )

    seen_dataset_ids: dict[str, int] = {}
    alias_prefixes = {"figure": "image:", "chart": "chart:", "table": "table:"}
    for dataset_idx, dataset in enumerate(datasets):
        dataset_base = f"{base}.datasets[{dataset_idx}]"
        if not isinstance(dataset, dict):
            issues.append(_issue(dataset_base, "warning", "analysis summary dataset entry must be an object"))
            continue

        dataset_id = str(dataset.get("id") or "").strip()
        if not dataset_id:
            issues.append(_issue(f"{dataset_base}.id", "warning", "missing dataset id"))
        else:
            dataset_key = dataset_id.lower()
            previous_idx = seen_dataset_ids.get(dataset_key)
            if previous_idx is not None:
                issues.append(
                    _issue(
                        f"{dataset_base}.id",
                        "warning",
                        f"duplicate dataset id {dataset_id!r}; already used by datasets[{previous_idx}]",
                    )
                )
            else:
                seen_dataset_ids[dataset_key] = dataset_idx

        source_path = str(dataset.get("source_path") or "").strip()
        if not source_path:
            issues.append(_issue(f"{dataset_base}.source_path", "warning", "missing source path"))
        else:
            if source_path_set and _normalize_ref(source_path) not in source_path_set:
                issues.append(
                    _issue(
                        f"{dataset_base}.source_path",
                        "warning",
                        "dataset source_path is not listed in analysis summary source_paths",
                    )
                )
            _warn_missing_path(
                issues,
                workspace=workspace,
                base=f"{dataset_base}.source_path",
                raw=source_path,
                kind="analysis summary source",
            )

        value_cols = dataset.get("value_cols")
        if value_cols is not None and not (
            isinstance(value_cols, list) and all(isinstance(item, str) and item.strip() for item in value_cols)
        ):
            issues.append(_issue(f"{dataset_base}.value_cols", "warning", "expected a non-empty list of value column names"))
        selected_columns_issue = _selected_columns_issue(dataset, item_name=dataset_base)
        if selected_columns_issue:
            issues.append(_issue(f"{dataset_base}.selected_columns", "warning", selected_columns_issue))

        for key in ("rows_scanned", "rows_used", "series_count", "points"):
            value = dataset.get(key)
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                issues.append(_issue(f"{dataset_base}.{key}", "warning", "expected a non-negative number"))
        rows_scanned = dataset.get("rows_scanned")
        rows_used = dataset.get("rows_used")
        if (
            isinstance(rows_scanned, (int, float))
            and not isinstance(rows_scanned, bool)
            and isinstance(rows_used, (int, float))
            and not isinstance(rows_used, bool)
            and rows_used > rows_scanned
        ):
            issues.append(_issue(f"{dataset_base}.rows_used", "warning", "rows_used exceeds rows_scanned"))

        for key, kind in (
            ("figure_path", "analysis summary figure"),
            ("chart_json", "analysis summary chart JSON"),
            ("table_json", "analysis summary table JSON"),
        ):
            path = str(dataset.get(key) or "").strip()
            if path:
                _warn_missing_path(
                    issues,
                    workspace=workspace,
                    base=f"{dataset_base}.{key}",
                    raw=path,
                    kind=kind,
                )

        aliases = dataset.get("aliases")
        if not isinstance(aliases, dict):
            issues.append(_issue(f"{dataset_base}.aliases", "warning", "missing generated alias map"))
        else:
            for key, prefix in alias_prefixes.items():
                alias = str(aliases.get(key) or "").strip()
                if not alias:
                    issues.append(_issue(f"{dataset_base}.aliases.{key}", "warning", f"missing {key} alias"))
                elif not alias.startswith(prefix):
                    issues.append(
                        _issue(
                            f"{dataset_base}.aliases.{key}",
                            "warning",
                            f"{key} alias should use a {prefix!r} prefix",
                        )
                    )

        readability = dataset.get("readability")
        if not isinstance(readability, dict):
            issues.append(_issue(f"{dataset_base}.readability", "warning", "missing readability assumptions"))
            continue
        target_box = str(readability.get("target_box") or "").strip()
        if not target_box:
            issues.append(_issue(f"{dataset_base}.readability.target_box", "warning", "missing target box"))
        elif _target_box_dimensions(target_box) is None:
            issues.append(
                _issue(
                    f"{dataset_base}.readability.target_box",
                    "warning",
                    "target box should include width x height in inches",
                )
            )
        figure_size = readability.get("figure_size_inches")
        if not isinstance(figure_size, list) or len(figure_size) != 2 or not all(
            _is_positive_number(item) for item in figure_size
        ):
            issues.append(
                _issue(
                    f"{dataset_base}.readability.figure_size_inches",
                    "warning",
                    "figure_size_inches should be [width, height] positive inches",
                )
            )
        for key in ("figure_dpi", "axis_label_min_pt"):
            if not _is_positive_number(readability.get(key)):
                issues.append(
                    _issue(
                        f"{dataset_base}.readability.{key}",
                        "warning",
                        "expected a positive number",
                    )
                )
        issues.extend(
            _image_whitespace_issues(
                readability.get("image_whitespace"),
                base=f"{dataset_base}.readability.image_whitespace",
            )
        )
    if manifest_output_ids:
        summary_dataset_ids = set(seen_dataset_ids)
        missing_from_summary = sorted(manifest_output_ids - summary_dataset_ids)
        extra_in_summary = sorted(summary_dataset_ids - manifest_output_ids)
        if missing_from_summary:
            issues.append(
                _issue(
                    f"{base}.datasets",
                    "warning",
                    "analysis summary missing manifest output dataset ids: "
                    + ", ".join(missing_from_summary),
                )
            )
        if extra_in_summary:
            issues.append(
                _issue(
                    f"{base}.datasets",
                    "warning",
                    "analysis summary has dataset ids not present in artifact manifest outputs: "
                    + ", ".join(extra_in_summary),
                )
            )


def _validate_content_plan(plan: Any, evidence_ids: set[str], outline: Any | None = None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if plan is None:
        return issues
    if not isinstance(plan, dict):
        return [_issue("content_plan.json", "error", "root must be an object")]

    thesis = str(plan.get("thesis") or "").strip()
    if not thesis:
        issues.append(_issue("content_plan.thesis", "warning", "missing thesis"))

    slide_plan = plan.get("slide_plan")
    if not isinstance(slide_plan, list):
        issues.append(_issue("content_plan.slide_plan", "error", "must be a list"))
        return issues

    seen_slide_ids: set[str] = set()
    normalized_slide_ids: set[str] = set()
    for idx, slide in enumerate(slide_plan):
        base = f"content_plan.slide_plan[{idx}]"
        if not isinstance(slide, dict):
            issues.append(_issue(base, "error", "slide plan item must be an object"))
            continue
        slide_id = str(slide.get("slide_id") or "").strip()
        if not slide_id:
            issues.append(_issue(f"{base}.slide_id", "error", "missing slide_id"))
        elif slide_id in seen_slide_ids:
            issues.append(_issue(f"{base}.slide_id", "error", f"duplicate slide_id {slide_id!r}"))
        else:
            seen_slide_ids.add(slide_id)
            normalized_slide_ids.add(_normalize_slide_identifier(slide_id))
        if not str(slide.get("message") or "").strip() and str(slide.get("role") or "") != "title":
            issues.append(_issue(f"{base}.message", "warning", "content slide has no message"))
        if not str(slide.get("visual_strategy") or "").strip():
            issues.append(_issue(f"{base}.visual_strategy", "warning", "missing visual strategy"))
        needs = slide.get("evidence_needs") or []
        if not isinstance(needs, list):
            issues.append(_issue(f"{base}.evidence_needs", "error", "must be a list"))
            continue
        for ev_id in needs:
            ev = str(ev_id)
            if evidence_ids and ev not in evidence_ids:
                issues.append(_issue(f"{base}.evidence_needs", "warning", f"unknown evidence id {ev!r}"))

    narrative_arc = plan.get("narrative_arc")
    if narrative_arc is not None:
        if not isinstance(narrative_arc, list):
            issues.append(_issue("content_plan.narrative_arc", "warning", "expected a list"))
        else:
            for arc_idx, arc in enumerate(narrative_arc):
                base = f"content_plan.narrative_arc[{arc_idx}]"
                if not isinstance(arc, dict):
                    issues.append(_issue(base, "warning", "narrative arc item should be an object"))
                    continue
                slides = arc.get("slides")
                if slides is None:
                    continue
                if not isinstance(slides, list):
                    issues.append(_issue(f"{base}.slides", "warning", "expected a list"))
                    continue
                for slide_idx, raw_slide_ref in enumerate(slides):
                    slide_ref = str(raw_slide_ref or "").strip()
                    ref_path = f"{base}.slides[{slide_idx}]"
                    if not slide_ref:
                        issues.append(_issue(ref_path, "warning", "empty slide reference will be ignored"))
                        continue
                    normalized_ref = _normalize_slide_identifier(slide_ref)
                    if normalized_slide_ids and normalized_ref not in normalized_slide_ids:
                        issues.append(
                            _issue(
                                ref_path,
                                "warning",
                                f"narrative arc slide {slide_ref!r} is not listed in content_plan.slide_plan",
                            )
                        )
                    if _outline_has_slides(outline) and not _outline_slide_reference_exists(slide_ref, outline):
                        issues.append(
                            _issue(
                                ref_path,
                                "warning",
                                f"narrative arc slide {slide_ref!r} was not found in outline.json",
                            )
                        )
    return issues


def _normalize_slide_identifier(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_slide_variant(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _outline_slide_variant(slide: dict[str, Any]) -> str:
    variant = _normalize_slide_variant(slide.get("variant"))
    if variant:
        return variant
    slide_type = _normalize_slide_variant(slide.get("type"))
    if slide_type and slide_type != "content":
        return slide_type
    return ""


def _outline_slide_lookups(outline: Any) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    explicit: dict[str, dict[str, Any]] = {}
    positional: dict[str, dict[str, Any]] = {}
    if not isinstance(outline, dict):
        return explicit, positional
    slides = outline.get("slides")
    if not isinstance(slides, list):
        return explicit, positional
    for idx, slide in enumerate(slides, start=1):
        if not isinstance(slide, dict):
            continue
        for key in ("slide_id", "id", "slug"):
            slide_id = _normalize_slide_identifier(slide.get(key))
            if slide_id and slide_id not in explicit:
                explicit[slide_id] = slide
        positional.setdefault(str(idx), slide)
        positional.setdefault(f"s{idx}", slide)
    return explicit, positional


def _outline_has_slides(outline: Any) -> bool:
    return isinstance(outline, dict) and isinstance(outline.get("slides"), list) and bool(outline.get("slides"))


def _outline_slide_reference_exists(value: Any, outline: Any) -> bool:
    return _outline_slide_for_reference(value, outline) is not None


def _outline_slide_for_reference(value: Any, outline: Any) -> dict[str, Any] | None:
    slide_id = _normalize_slide_identifier(value)
    if not slide_id:
        return None
    explicit_lookup, positional_lookup = _outline_slide_lookups(outline)
    return explicit_lookup.get(slide_id) or positional_lookup.get(slide_id)


def _validate_outline_slide_identifiers(outline: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(outline, dict):
        return issues
    slides = outline.get("slides")
    if not isinstance(slides, list):
        return issues
    seen: dict[str, str] = {}
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        seen_on_slide: set[str] = set()
        for key in ("slide_id", "id", "slug"):
            if key not in slide:
                continue
            raw = str(slide.get(key) or "").strip()
            path = f"outline.slides[{idx}].{key}"
            if not raw:
                issues.append(_issue(path, "warning", "empty outline slide identifier will be ignored"))
                continue
            normalized = _normalize_slide_identifier(raw)
            if normalized in seen_on_slide:
                continue
            previous_path = seen.get(normalized)
            if previous_path is not None:
                issues.append(
                    _issue(
                        path,
                        "warning",
                        f"duplicate outline slide identifier {raw!r}; already listed at {previous_path}",
                    )
                )
            else:
                seen[normalized] = path
            seen_on_slide.add(normalized)
    return issues


def _validate_content_plan_outline_alignment(content_plan: Any, outline: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(content_plan, dict) or not isinstance(outline, dict):
        return issues
    slide_plan = content_plan.get("slide_plan")
    outline_slides = outline.get("slides")
    if not isinstance(slide_plan, list) or not isinstance(outline_slides, list) or not outline_slides:
        return issues

    explicit_lookup, positional_lookup = _outline_slide_lookups(outline)
    for idx, planned_slide in enumerate(slide_plan):
        if not isinstance(planned_slide, dict):
            continue
        base = f"content_plan.slide_plan[{idx}]"
        raw_slide_id = str(planned_slide.get("slide_id") or "").strip()
        slide_id = _normalize_slide_identifier(raw_slide_id)
        if not slide_id:
            continue
        outline_slide = explicit_lookup.get(slide_id) or positional_lookup.get(slide_id)
        if outline_slide is None:
            issues.append(
                _issue(
                    f"{base}.slide_id",
                    "warning",
                    f"planned slide id {raw_slide_id!r} was not found in outline.json",
                )
            )
            continue
        planned_variant = _normalize_slide_variant(planned_slide.get("variant"))
        outline_variant = _outline_slide_variant(outline_slide)
        if planned_variant and outline_variant and planned_variant != outline_variant:
            issues.append(
                _issue(
                    f"{base}.variant",
                    "warning",
                    (
                        f"planned variant {planned_variant!r} does not match outline "
                        f"variant {outline_variant!r} for slide id {raw_slide_id!r}"
                    ),
                )
            )
    return issues


_EVIDENCE_ARTIFACT_ALIAS_PREFIXES = {
    "figure": "image:",
    "chart": "chart:",
    "table": "table:",
}


def _validate_evidence_artifact_context(
    item: dict[str, Any],
    *,
    base: str,
    workspace: Path | None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    artifact_ids = item.get("artifact_ids")
    if artifact_ids is not None:
        if not (
            isinstance(artifact_ids, list)
            and artifact_ids
            and all(isinstance(artifact_id, str) and artifact_id.strip() for artifact_id in artifact_ids)
        ):
            issues.append(
                _issue(
                    f"{base}.artifact_ids",
                    "warning",
                    "expected a non-empty list of artifact ids",
                )
            )

    artifact_aliases = item.get("artifact_aliases")
    alias_roles: set[str] = set()
    if artifact_aliases is not None:
        if not isinstance(artifact_aliases, dict):
            issues.append(_issue(f"{base}.artifact_aliases", "warning", "expected an object"))
        else:
            for role, raw_alias in artifact_aliases.items():
                role_text = str(role or "").strip()
                role_path = role_text or str(role)
                alias_base = f"{base}.artifact_aliases.{role_path}"
                expected_prefix = _EVIDENCE_ARTIFACT_ALIAS_PREFIXES.get(role_text)
                if expected_prefix is None:
                    issues.append(
                        _issue(
                            alias_base,
                            "warning",
                            f"unsupported artifact alias role {role_text!r}; expected one of "
                            f"{', '.join(sorted(_EVIDENCE_ARTIFACT_ALIAS_PREFIXES))}",
                        )
                    )
                    continue
                alias_roles.add(role_text)
                alias = str(raw_alias or "").strip()
                if not alias:
                    issues.append(_issue(alias_base, "warning", "empty artifact alias will be ignored"))
                elif not alias.startswith(expected_prefix):
                    issues.append(
                        _issue(
                            alias_base,
                            "warning",
                            f"expected alias to start with {expected_prefix!r}",
                        )
                    )

    artifact_paths = item.get("artifact_paths")
    if artifact_paths is not None:
        if not isinstance(artifact_paths, dict):
            issues.append(_issue(f"{base}.artifact_paths", "warning", "expected an object"))
        else:
            path_roles: set[str] = set()
            for role, raw_path in artifact_paths.items():
                role_text = str(role or "").strip()
                role_path = role_text or str(role)
                path_base = f"{base}.artifact_paths.{role_path}"
                if role_text not in _EVIDENCE_ARTIFACT_ALIAS_PREFIXES:
                    issues.append(
                        _issue(
                            path_base,
                            "warning",
                            f"unsupported artifact path role {role_text!r}; expected one of "
                            f"{', '.join(sorted(_EVIDENCE_ARTIFACT_ALIAS_PREFIXES))}",
                        )
                    )
                    continue
                path_roles.add(role_text)
                path = str(raw_path or "").strip()
                if not path:
                    issues.append(_issue(path_base, "warning", "empty artifact path will be ignored"))
                elif not path.startswith(("http://", "https://")):
                    _warn_missing_path(
                        issues,
                        workspace=workspace,
                        base=path_base,
                        raw=path,
                        kind="evidence artifact",
                    )
            if artifact_aliases is not None and isinstance(artifact_aliases, dict):
                missing_paths = sorted(role for role in alias_roles - path_roles if role)
                extra_paths = sorted(role for role in path_roles - alias_roles if role)
                if missing_paths:
                    issues.append(
                        _issue(
                            f"{base}.artifact_paths",
                            "warning",
                            f"missing paths for artifact alias role(s): {', '.join(missing_paths)}",
                        )
                    )
                if extra_paths:
                    issues.append(
                        _issue(
                            f"{base}.artifact_aliases",
                            "warning",
                            f"missing aliases for artifact path role(s): {', '.join(extra_paths)}",
                        )
                    )

    return issues


def _validate_evidence_plan(
    plan: Any,
    outline: Any | None = None,
    *,
    workspace: Path | None = None,
) -> tuple[set[str], list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    ids: set[str] = set()
    if plan is None:
        return ids, issues
    if not isinstance(plan, dict):
        return ids, [_issue("evidence_plan.json", "error", "root must be an object")]

    items = plan.get("items")
    if not isinstance(items, list):
        return ids, [_issue("evidence_plan.items", "error", "must be a list")]
    chart_candidates = plan.get("chart_candidates")
    source_policy = str(plan.get("source_policy") or "").strip()
    if (items or chart_candidates) and not source_policy:
        issues.append(
            _issue(
                "evidence_plan.source_policy",
                "warning",
                "missing source policy for evidence-backed claims or chart candidates",
            )
        )

    for idx, item in enumerate(items):
        base = f"evidence_plan.items[{idx}]"
        if not isinstance(item, dict):
            issues.append(_issue(base, "error", "evidence item must be an object"))
            continue
        ev_id = str(item.get("id") or "").strip()
        if not ev_id:
            issues.append(_issue(f"{base}.id", "error", "missing id"))
        elif ev_id in ids:
            issues.append(_issue(f"{base}.id", "error", f"duplicate id {ev_id!r}"))
        else:
            ids.add(ev_id)
        if not str(item.get("claim") or "").strip():
            issues.append(_issue(f"{base}.claim", "warning", "missing claim"))
        visual_use = str(item.get("visual_use") or "").strip()
        visual_use_tokens = {
            token.strip()
            for token in visual_use.replace(",", "|").split("|")
            if token.strip()
        }
        source_url = str(item.get("source_url") or "").strip()
        source_note = str(item.get("source_note") or "").strip()
        if visual_use_tokens & {"kpi", "figure", "chart", "table", "footer-source"} and not (source_url or source_note):
            issues.append(
                _issue(
                    f"{base}.source_url",
                    "warning",
                    f"{visual_use} evidence should include source_url or source_note",
                )
            )
        used_on_slides = item.get("used_on_slides")
        if used_on_slides is not None:
            if not isinstance(used_on_slides, list):
                issues.append(_issue(f"{base}.used_on_slides", "warning", "expected a list"))
            else:
                for slide_idx, raw_slide_ref in enumerate(used_on_slides):
                    slide_ref = str(raw_slide_ref or "").strip()
                    ref_path = f"{base}.used_on_slides[{slide_idx}]"
                    if not slide_ref:
                        issues.append(_issue(ref_path, "warning", "empty slide reference will be ignored"))
                    elif _outline_has_slides(outline) and not _outline_slide_reference_exists(slide_ref, outline):
                        issues.append(
                            _issue(
                                ref_path,
                                "warning",
                                f"slide reference {slide_ref!r} was not found in outline.json",
                            )
                        )
        issues.extend(_validate_evidence_artifact_context(item, base=base, workspace=workspace))

    if chart_candidates is not None:
        if not isinstance(chart_candidates, list):
            issues.append(_issue("evidence_plan.chart_candidates", "warning", "expected a list"))
        else:
            for idx, candidate in enumerate(chart_candidates):
                base = f"evidence_plan.chart_candidates[{idx}]"
                if not isinstance(candidate, dict):
                    issues.append(_issue(base, "warning", "chart candidate should be an object"))
                    continue
                target_slide = str(candidate.get("target_slide") or "").strip()
                if "target_slide" in candidate:
                    if not target_slide:
                        issues.append(_issue(f"{base}.target_slide", "warning", "empty target slide will be ignored"))
                    elif _outline_has_slides(outline) and not _outline_slide_reference_exists(target_slide, outline):
                        issues.append(
                            _issue(
                                f"{base}.target_slide",
                                "warning",
                                f"target slide {target_slide!r} was not found in outline.json",
                            )
                        )
                source_ids = candidate.get("source_ids")
                if source_ids is not None:
                    if not isinstance(source_ids, list):
                        issues.append(_issue(f"{base}.source_ids", "warning", "expected a list"))
                    else:
                        for source_idx, raw_source_id in enumerate(source_ids):
                            source_id = str(raw_source_id or "").strip()
                            if not source_id:
                                issues.append(
                                    _issue(
                                        f"{base}.source_ids[{source_idx}]",
                                        "warning",
                                        "empty evidence source id will be ignored",
                                    )
                                )
                            elif source_id not in ids:
                                issues.append(
                                    _issue(
                                        f"{base}.source_ids[{source_idx}]",
                                        "warning",
                                        f"unknown evidence id {source_id!r}",
                                    )
                                )
    return ids, issues


def _validate_asset_plan_references(
    asset_plan: Any,
    outline: Any | None = None,
    *,
    workspace: Path | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if asset_plan is None:
        return issues
    if not isinstance(asset_plan, dict):
        return [_issue("asset_plan.json", "warning", "root should be an object")]
    sections = ("images", "backgrounds", "charts", "tables", "generated_images")
    section_labels = {
        "images": "image",
        "backgrounds": "background",
        "charts": "chart",
        "tables": "table",
        "generated_images": "generated image",
    }
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] = {}
    for section in sections:
        entries = asset_plan.get(section)
        if entries is None:
            continue
        if not isinstance(entries, list):
            issues.append(_issue(f"asset_plan.{section}", "warning", "expected a list"))
            continue
        for idx, entry in enumerate(entries):
            base = f"asset_plan.{section}[{idx}]"
            if not isinstance(entry, dict):
                issues.append(_issue(base, "warning", "asset entry should be an object"))
                continue
            raw_path = str(entry.get("path") or "").strip()
            if raw_path and not raw_path.startswith(("http://", "https://")):
                _warn_missing_path(
                    issues,
                    workspace=workspace,
                    base=f"{base}.path",
                    raw=raw_path,
                    kind=f"asset_plan {section_labels.get(section, section)}",
                )
            _validate_local_visual_asset_provenance(issues, base=base, entry=entry, section=section)
            _validate_asset_plan_payload(
                issues,
                workspace=workspace,
                base=base,
                entry=entry,
                section=section,
                json_payload_cache=json_payload_cache,
            )
            if section == "generated_images":
                _validate_generated_image_metadata(issues, base=base, entry=entry)
            used_on_slides = entry.get("used_on_slides")
            if used_on_slides is None:
                continue
            if not isinstance(used_on_slides, list):
                issues.append(_issue(f"{base}.used_on_slides", "warning", "expected a list"))
                continue
            for slide_idx, raw_slide_ref in enumerate(used_on_slides):
                slide_ref = str(raw_slide_ref or "").strip()
                ref_path = f"{base}.used_on_slides[{slide_idx}]"
                if not slide_ref:
                    issues.append(_issue(ref_path, "warning", "empty slide reference will be ignored"))
                elif _outline_has_slides(outline) and not _outline_slide_reference_exists(slide_ref, outline):
                    issues.append(
                        _issue(
                            ref_path,
                            "warning",
                            f"slide reference {slide_ref!r} was not found in outline.json",
                        )
                    )
    return issues


def _validate_style_mix_matrix(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    style_system = brief.get("style_system")
    has_malformed_candidate = (
        ("style_mix_matrix" in brief and not isinstance(brief.get("style_mix_matrix"), dict))
        or (
            isinstance(style_system, dict)
            and "style_mix_matrix" in style_system
            and not isinstance(style_system.get("style_mix_matrix"), dict)
        )
    )
    mix = _first_dict(
        brief,
        [
            ("style_mix_matrix",),
            ("style_system", "style_mix_matrix"),
        ],
    )
    style_system_has_treatments = isinstance(style_system, dict) and any(
        key in style_system
        for key in (
            "header_system",
            "footer_system",
            "title_slide_system",
            "section_system",
            "figure_table_system",
        )
    )
    has_style_contract = (
        any(
            key in brief
            for key in (
                "renderer_treatments",
                "design_modulation",
                "deck_style",
            )
        )
        or style_system_has_treatments
    )
    if mix is None:
        if has_malformed_candidate:
            return issues
        if has_style_contract:
            issues.append(
                _issue(
                    "design_brief.style_mix_matrix",
                    "warning",
                    "missing mix-and-match treatment pool for reproducible style variation",
                )
            )
        return issues

    base = (
        "design_brief.style_system.style_mix_matrix"
        if _nested_dict(brief, "style_system", "style_mix_matrix") is mix
        else "design_brief.style_mix_matrix"
    )
    explicit_seed_candidates = [brief.get("style_seed")]
    for field in ("style_system", "renderer_treatments", "deck_style"):
        value = brief.get(field)
        if isinstance(value, dict):
            explicit_seed_candidates.append(value.get("style_seed"))
    if not any(isinstance(value, str) and value.strip() for value in explicit_seed_candidates):
        seed_path = (
            "design_brief.style_system.style_seed"
            if isinstance(style_system, dict)
            else "design_brief.style_seed"
        )
        issues.append(
            _issue(
                seed_path,
                "warning",
                "style_mix_matrix should declare a stable style_seed so treatment rotation is reproducible",
            )
        )
    multi_option_pools: list[str] = []
    header_unique_count = 0
    for key, allowed, required in STYLE_MIX_POOL_SPECS:
        _validate_string_list(
            issues,
            base=base,
            payload=mix,
            key=key,
            required=required,
            allowed=allowed,
            unsupported_severity="error",
        )
        unique_supported_values = _unique_supported_strings(mix.get(key), allowed=allowed)
        if key == "header_variant_pool":
            header_unique_count = len(unique_supported_values)
        if len(unique_supported_values) >= 2:
            multi_option_pools.append(key)
    if "header_variant_pool" in mix and header_unique_count < 2:
        issues.append(
            _issue(
                f"{base}.header_variant_pool",
                "warning",
                "include at least 2 unique supported header variants so auto headers can vary",
            )
        )
    if len(multi_option_pools) < 2:
        issues.append(
            _issue(
                base,
                "warning",
                "style_mix_matrix should include at least two treatment pools with 2+ unique supported entries",
            )
        )
    do_not_mix = mix.get("do_not_mix")
    if do_not_mix is not None and not isinstance(do_not_mix, list):
        issues.append(_issue(f"{base}.do_not_mix", "warning", "expected a list"))
    if not str(mix.get("mix_rule") or "").strip():
        issues.append(
            _issue(
                f"{base}.mix_rule",
                "warning",
                "missing rule for rotating treatments without making the deck feel random",
            )
        )
    return issues


def _style_preset_candidates(brief: dict[str, Any]) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = [("design_brief.style_preset", brief.get("style_preset"))]
    for field in ("style_system", "visual_system", "deck_style", "renderer_treatments"):
        value = brief.get(field)
        if isinstance(value, dict):
            candidates.append((f"design_brief.{field}.style_preset", value.get("style_preset")))
    return candidates


def _validate_style_preset(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    valid_text = ", ".join(SUPPORTED_STYLE_PRESET_NAMES[name] for name in sorted(SUPPORTED_STYLE_PRESET_NAMES))
    resolved: list[tuple[str, str]] = []
    for path, value in _style_preset_candidates(brief):
        if value is None:
            continue
        if not isinstance(value, str):
            issues.append(_issue(path, "error", "must be a string when present"))
            continue
        text = value.strip()
        if not text:
            issues.append(_issue(path, "warning", "empty style preset will fall back to the workspace style contract"))
            continue
        if text.lower() not in SUPPORTED_STYLE_PRESETS:
            issues.append(_issue(path, "error", f"unsupported style preset {text!r}; valid presets: {valid_text}"))
            continue
        resolved.append((path, SUPPORTED_STYLE_PRESET_NAMES[text.lower()]))
    unique_presets = {preset.lower(): preset for _, preset in resolved}
    if len(unique_presets) > 1:
        detail = ", ".join(f"{path}={preset!r}" for path, preset in resolved)
        issues.append(
            _issue(
                "design_brief.style_preset",
                "error",
                (
                    "conflicting style preset declarations: "
                    f"{detail}; keep one preset source or make all preset fields match"
                ),
            )
        )
    return issues


STYLE_TREATMENT_ENUMS = {
    "visual_density": SUPPORTED_VISUAL_DENSITIES,
    "header_mode": SUPPORTED_HEADER_MODES,
    "header_variant": SUPPORTED_HEADER_VARIANTS,
    "title_layout": SUPPORTED_TITLE_LAYOUTS,
    "title_motif": SUPPORTED_TITLE_MOTIFS,
    "section_motif": SUPPORTED_SECTION_MOTIFS,
    "timeline_mode": SUPPORTED_TIMELINE_MODES,
    "matrix_mode": SUPPORTED_MATRIX_MODES,
    "stats_mode": SUPPORTED_STATS_MODES,
    "cards_mode": SUPPORTED_CARDS_MODES,
    "chart_treatment": SUPPORTED_CHART_TREATMENTS,
    "footer_mode": SUPPORTED_FOOTERS,
    "summary_callout_mode": SUPPORTED_SUMMARY_CALLOUT_MODES,
    "figure_table_treatment": SUPPORTED_FIGURE_TREATMENTS,
}


def _validate_treatment_enum(
    issues: list[dict[str, str]],
    *,
    payload: dict[str, Any],
    base: str,
    key: str,
) -> None:
    if key not in payload:
        return
    value = payload.get(key)
    if not isinstance(value, str):
        issues.append(_issue(f"{base}.{key}", "error", "must be a string when present"))
        return
    text = value.strip()
    if not text:
        issues.append(_issue(f"{base}.{key}", "warning", "empty treatment value will be ignored"))
        return
    allowed = STYLE_TREATMENT_ENUMS[key]
    if text.lower() not in allowed:
        issues.append(
            _issue(
                f"{base}.{key}",
                "error",
                f"unsupported value {text!r}; valid values: {', '.join(sorted(allowed))}",
            )
        )


def _validate_header_variants(
    issues: list[dict[str, str]],
    *,
    payload: dict[str, Any],
    base: str,
) -> None:
    if "header_variants" not in payload:
        return
    value = payload.get("header_variants")
    if not isinstance(value, list):
        issues.append(_issue(f"{base}.header_variants", "error", "must be a list when present"))
        return
    for idx, item in enumerate(value):
        path = f"{base}.header_variants[{idx}]"
        if not isinstance(item, str):
            issues.append(_issue(path, "error", "must be a string"))
            continue
        text = item.strip()
        if not text:
            issues.append(_issue(path, "warning", "empty header variant will be ignored"))
            continue
        if text.lower() not in SUPPORTED_HEADER_VARIANTS:
            issues.append(
                _issue(
                    path,
                    "error",
                    f"unsupported value {text!r}; valid values: {', '.join(sorted(SUPPORTED_HEADER_VARIANTS))}",
                )
            )


def _validate_treatment_payload(
    issues: list[dict[str, str]],
    *,
    payload: Any,
    base: str,
    keys: set[str],
    include_header_variants: bool = False,
) -> None:
    if payload is None:
        return
    if not isinstance(payload, dict):
        issues.append(_issue(base, "error", "must be an object when present"))
        return
    for key in sorted(keys):
        _validate_treatment_enum(issues, payload=payload, base=base, key=key)
    if include_header_variants:
        _validate_header_variants(issues, payload=payload, base=base)


def _validate_style_treatments(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    style_system = brief.get("style_system")
    if isinstance(style_system, dict):
        _validate_treatment_payload(
            issues,
            payload=style_system,
            base="design_brief.style_system",
            keys={"visual_density"},
        )
        _validate_treatment_payload(
            issues,
            payload=style_system.get("header_system"),
            base="design_brief.style_system.header_system",
            keys={"header_mode", "header_variant"},
            include_header_variants=True,
        )
        _validate_treatment_payload(
            issues,
            payload=style_system.get("footer_system"),
            base="design_brief.style_system.footer_system",
            keys={"footer_mode"},
        )
        _validate_treatment_payload(
            issues,
            payload=style_system.get("title_slide_system"),
            base="design_brief.style_system.title_slide_system",
            keys={"title_layout", "title_motif"},
        )
        _validate_treatment_payload(
            issues,
            payload=style_system.get("section_system"),
            base="design_brief.style_system.section_system",
            keys={"section_motif"},
        )
        _validate_treatment_payload(
            issues,
            payload=style_system.get("figure_table_system"),
            base="design_brief.style_system.figure_table_system",
            keys={"figure_table_treatment"},
        )
        _validate_treatment_payload(
            issues,
            payload=style_system.get("chart_system"),
            base="design_brief.style_system.chart_system",
            keys={"chart_treatment"},
        )
    for field in ("renderer_treatments", "deck_style"):
        _validate_treatment_payload(
            issues,
            payload=brief.get(field),
            base=f"design_brief.{field}",
            keys=set(STYLE_TREATMENT_ENUMS),
            include_header_variants=True,
        )
    return issues


def _figure_contract_from_brief(brief: dict[str, Any]) -> dict[str, Any] | None:
    return _first_dict(
        brief,
        [
            ("figure_export_contract",),
            ("evidence_and_assets", "figure_export_contract"),
        ],
    )


def _analysis_artifact_plan_from_brief(brief: dict[str, Any]) -> dict[str, Any] | None:
    return _first_dict(
        brief,
        [
            ("analysis_artifact_plan",),
            ("evidence_and_assets", "analysis_artifact_plan"),
        ],
    )


def _data_source_fingerprint_path(item: dict[str, Any]) -> str:
    for key in ("workspace_relative_path", "relative_path", "source_path", "path"):
        text = str(item.get(key) or "").strip()
        if text:
            return text
    return ""


def _validate_data_source_fingerprints(
    issues: list[dict[str, str]],
    *,
    workspace: Path | None,
    base: str,
    fingerprints: Any,
    candidate_data_files: set[str],
    fingerprint_cache: dict[Path, dict[str, Any] | None],
) -> None:
    if fingerprints is None:
        return
    if not isinstance(fingerprints, list):
        issues.append(_issue(base, "error", "must be a list when present"))
        return
    seen: dict[str, int] = {}
    for idx, item in enumerate(fingerprints):
        item_base = f"{base}[{idx}]"
        if not isinstance(item, dict):
            issues.append(_issue(item_base, "error", "data source fingerprint entry must be an object"))
            continue
        path = _data_source_fingerprint_path(item)
        if not path:
            issues.append(_issue(f"{item_base}.path", "warning", "missing data source path"))
            continue
        normalized_path = _normalize_ref(path)
        previous_idx = seen.get(normalized_path)
        if previous_idx is not None:
            issues.append(
                _issue(
                    f"{item_base}.path",
                    "warning",
                    f"duplicate data source path {path!r}; already listed at {base}[{previous_idx}]",
                )
            )
        else:
            seen[normalized_path] = idx
        if candidate_data_files and normalized_path not in candidate_data_files:
            issues.append(
                _issue(
                    f"{item_base}.path",
                    "warning",
                    "data source fingerprint path should also appear in candidate_data_files",
                )
            )
        _warn_missing_path(
            issues,
            workspace=workspace,
            base=f"{item_base}.path",
            raw=path,
            kind="data source fingerprint",
        )
        resolved = _resolve_workspace_path(workspace, path)
        if resolved is None or not resolved.exists():
            continue
        fingerprint = _cached_file_fingerprint(resolved, fingerprint_cache)
        if fingerprint is None:
            continue
        expected_sha = str(item.get("source_sha256") or "").strip()
        hash_status = str(item.get("hash_status") or "").strip()
        if expected_sha:
            if expected_sha != fingerprint["source_sha256"]:
                issues.append(
                    _issue(
                        f"{item_base}.source_sha256",
                        "warning",
                        "data source fingerprint source_sha256 does not match current source file",
                    )
                )
        elif not hash_status:
            issues.append(
                _issue(
                    f"{item_base}.source_sha256",
                    "warning",
                    "missing source_sha256 or hash_status for data source fingerprint",
                )
            )
        expected_bytes = item.get("source_size_bytes", item.get("source_bytes"))
        if isinstance(expected_bytes, (int, float)) and not isinstance(expected_bytes, bool):
            if int(expected_bytes) != int(fingerprint["source_bytes"]):
                issues.append(
                    _issue(
                        f"{item_base}.source_size_bytes",
                        "warning",
                        "data source fingerprint source_size_bytes does not match current source file",
                    )
                )


def _validate_analysis_artifact_plan(
    brief: dict[str, Any],
    *,
    workspace: Path | None,
    outline: Any | None = None,
    outline_refs: set[str] | None = None,
    asset_aliases: dict[str, set[str]] | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    evidence_and_assets = brief.get("evidence_and_assets")
    has_malformed_candidate = (
        (
            "analysis_artifact_plan" in brief
            and not isinstance(brief.get("analysis_artifact_plan"), dict)
        )
        or (
            isinstance(evidence_and_assets, dict)
            and "analysis_artifact_plan" in evidence_and_assets
            and not isinstance(evidence_and_assets.get("analysis_artifact_plan"), dict)
        )
    )
    plan = _analysis_artifact_plan_from_brief(brief)
    figure_contract = _figure_contract_from_brief(brief)
    design_dna = str(brief.get("design_dna") or "").lower()
    likely_data_deck = any(term in design_dna for term in ("lab", "data", "scientific"))
    if plan is None:
        if has_malformed_candidate:
            return issues
        if figure_contract is not None or likely_data_deck:
            issues.append(
                _issue(
                    "design_brief.analysis_artifact_plan",
                    "warning",
                    "missing analysis artifact plan for data/figure-driven deck",
                )
            )
        return issues

    base = (
        "design_brief.evidence_and_assets.analysis_artifact_plan"
        if _nested_dict(brief, "evidence_and_assets", "analysis_artifact_plan") is plan
        else "design_brief.analysis_artifact_plan"
    )
    list_fields = (
        "candidate_data_files",
        "spreadsheet_inputs",
        "required_scripts",
        "figure_scripts",
        "chart_json_outputs",
        "table_outputs",
        "rebuild_commands",
    )
    for key in list_fields:
        value = plan.get(key)
        if value is not None and not isinstance(value, list):
            issues.append(_issue(f"{base}.{key}", "error", "must be a list when present"))
        elif isinstance(value, list):
            normalizer = (
                (lambda item: " ".join(item.split()))
                if key == "rebuild_commands"
                else _normalize_ref
            )
            _warn_duplicate_string_entries(
                issues,
                base=f"{base}.{key}",
                values=value,
                normalizer=normalizer,
            )

    artifact_manifest = plan.get("artifact_manifest")
    artifact_manifest_path = ""
    if artifact_manifest is not None:
        if not isinstance(artifact_manifest, str):
            issues.append(_issue(f"{base}.artifact_manifest", "warning", "expected a path string"))
        else:
            artifact_manifest_path = artifact_manifest.strip()
    analysis_summary = plan.get("analysis_summary")
    analysis_summary_path = ""
    if analysis_summary is not None:
        if not isinstance(analysis_summary, str):
            issues.append(_issue(f"{base}.analysis_summary", "warning", "expected a path string"))
        else:
            analysis_summary_path = analysis_summary.strip()
    analysis_summary_markdown = plan.get("analysis_summary_markdown")
    analysis_summary_markdown_path = ""
    if analysis_summary_markdown is not None:
        if not isinstance(analysis_summary_markdown, str):
            issues.append(_issue(f"{base}.analysis_summary_markdown", "warning", "expected a path string"))
        else:
            analysis_summary_markdown_path = analysis_summary_markdown.strip()

    for key, kind in (
        ("candidate_data_files", "data input"),
        ("spreadsheet_inputs", "spreadsheet input"),
        ("required_scripts", "required script"),
        ("figure_scripts", "figure script"),
    ):
        for idx, raw in enumerate(_list_value(plan, key) or []):
            if not isinstance(raw, str):
                issues.append(_issue(f"{base}.{key}[{idx}]", "warning", "expected a path string"))
                continue
            _warn_missing_path(
                issues,
                workspace=workspace,
                base=f"{base}.{key}[{idx}]",
                raw=raw,
                kind=kind,
            )

    newest_source = _newest_artifact_source(plan, figure_contract, workspace=workspace)
    rebuild_commands = [str(item).strip() for item in (_list_value(plan, "rebuild_commands") or []) if str(item).strip()]
    figure_script = str(figure_contract.get("script") or "").strip() if isinstance(figure_contract, dict) else ""
    figure_outputs = figure_contract.get("outputs") if isinstance(figure_contract, dict) else None
    _validate_artifact_rebuild_context(
        issues,
        base=f"{base}.rebuild_context",
        context=plan.get("rebuild_context") if "rebuild_context" in plan else None,
        expected_manifest=artifact_manifest_path,
        expected_analysis_summary=analysis_summary_path,
        expected_output_count=len(figure_outputs) if isinstance(figure_outputs, list) else None,
        expected_producer_path=figure_script,
    )
    declared_structured_output_paths = {
        _normalize_ref(raw)
        for key in ("chart_json_outputs", "table_outputs")
        for raw in (_list_value(plan, key) or [])
        if isinstance(raw, str) and raw.strip()
    }
    fingerprint_cache: dict[Path, dict[str, Any] | None] = {}
    json_payload_cache: dict[Path, tuple[Any | None, str | None]] = {}
    candidate_data_file_refs = {
        _normalize_ref(raw)
        for raw in (_list_value(plan, "candidate_data_files") or [])
        if isinstance(raw, str) and raw.strip()
    }
    _validate_data_source_fingerprints(
        issues,
        workspace=workspace,
        base=f"{base}.data_source_fingerprints",
        fingerprints=plan.get("data_source_fingerprints"),
        candidate_data_files=candidate_data_file_refs,
        fingerprint_cache=fingerprint_cache,
    )

    registry = plan.get("artifact_registry")
    registered_paths: set[str] = set()
    registry_has_slide_use: dict[str, bool] = {}
    seen_registry_ids: dict[str, int] = {}
    seen_registry_paths: dict[str, int] = {}
    registry_present = False
    if registry is None:
        issues.append(
            _issue(
                f"{base}.artifact_registry",
                "warning",
                "missing artifact registry for data, chart, table, and figure outputs",
            )
        )
    elif not isinstance(registry, list):
        issues.append(_issue(f"{base}.artifact_registry", "error", "must be a list"))
    else:
        registry_present = True
        for idx, item in enumerate(registry):
            item_base = f"{base}.artifact_registry[{idx}]"
            if not isinstance(item, dict):
                issues.append(_issue(item_base, "error", "artifact registry entry must be an object"))
                continue
            art_id = str(item.get("id") or "").strip()
            path = str(item.get("path") or "").strip()
            producer = str(item.get("producer") or "").strip()
            if not art_id:
                issues.append(_issue(f"{item_base}.id", "warning", "missing artifact id"))
            else:
                id_key = art_id.lower()
                previous_idx = seen_registry_ids.get(id_key)
                if previous_idx is not None:
                    issues.append(
                        _issue(
                            f"{item_base}.id",
                            "warning",
                            f"duplicate artifact id {art_id!r}; already used by artifact_registry[{previous_idx}]",
                        )
                    )
                else:
                    seen_registry_ids[id_key] = idx
            if not path:
                issues.append(_issue(f"{item_base}.path", "warning", "missing artifact path"))
            else:
                _warn_missing_path(
                    issues,
                    workspace=workspace,
                    base=f"{item_base}.path",
                    raw=path,
                    kind="artifact registry",
                )
                normalized_path = _normalize_ref(path)
                previous_idx = seen_registry_paths.get(normalized_path)
                if previous_idx is not None:
                    issues.append(
                        _issue(
                            f"{item_base}.path",
                            "warning",
                            f"duplicate artifact path {path!r}; already used by artifact_registry[{previous_idx}]",
                        )
                    )
                else:
                    seen_registry_paths[normalized_path] = idx
                registered_paths.add(normalized_path)
                if normalized_path not in declared_structured_output_paths:
                    structured_kind = _registry_structured_payload_kind(item, path)
                    if structured_kind:
                        _validate_declared_output_payload(
                            issues,
                            workspace=workspace,
                            base=f"{item_base}.path",
                            raw=path,
                            kind=structured_kind,
                            fingerprint_cache=fingerprint_cache,
                            json_payload_cache=json_payload_cache,
                        )
            if not producer:
                issues.append(_issue(f"{item_base}.producer", "warning", "missing artifact producer/source"))
            elif _looks_like_local_path(producer):
                _warn_missing_path(
                    issues,
                    workspace=workspace,
                    base=f"{item_base}.producer",
                    raw=producer,
                    kind="artifact producer",
                )
            used_on = item.get("used_on_slides")
            if used_on is not None and not isinstance(used_on, list):
                issues.append(_issue(f"{item_base}.used_on_slides", "warning", "expected a list"))
            elif isinstance(used_on, list) and _outline_has_slides(outline):
                for slide_idx, slide_ref in enumerate(used_on):
                    normalized_slide_ref = str(slide_ref or "").strip()
                    if not normalized_slide_ref:
                        continue
                    if not _outline_slide_reference_exists(normalized_slide_ref, outline):
                        issues.append(
                            _issue(
                                f"{item_base}.used_on_slides[{slide_idx}]",
                                "warning",
                                f"slide reference {normalized_slide_ref!r} was not found in outline.json",
                            )
                        )
            binding_status = str(item.get("binding_status") or "").strip()
            if binding_status and binding_status not in {"selected", "deferred_support"}:
                issues.append(
                    _issue(
                        f"{item_base}.binding_status",
                        "warning",
                        "expected 'selected' or 'deferred_support'",
                    )
                )
            normalized_path = _normalize_ref(path)
            if normalized_path:
                registry_has_slide_use[normalized_path] = registry_has_slide_use.get(
                    normalized_path,
                    False,
                ) or (isinstance(used_on, list) and any(str(item).strip() for item in used_on)) or (
                    binding_status == "deferred_support"
                )
            if not str(item.get("provenance") or "").strip():
                issues.append(_issue(f"{item_base}.provenance", "warning", "missing provenance note"))
            metadata_issue = _registry_analysis_metadata_issue(
                item,
                item_name=f"artifact registry entry {idx}",
                workspace=workspace,
                fingerprint_cache=fingerprint_cache,
            )
            if metadata_issue:
                issues.append(_issue(f"{item_base}.analysis_metadata", "warning", metadata_issue))

    if artifact_manifest_path:
        _warn_missing_path(
            issues,
            workspace=workspace,
            base=f"{base}.artifact_manifest",
            raw=artifact_manifest_path,
            kind="artifact manifest",
        )
        _validate_artifact_manifest_payload(
            issues,
            workspace=workspace,
            base=f"{base}.artifact_manifest",
            raw=artifact_manifest_path,
            registered_paths=registered_paths,
            registry_present=registry_present,
            fingerprint_cache=fingerprint_cache,
            json_payload_cache=json_payload_cache,
        )
    if analysis_summary_path:
        _warn_missing_path(
            issues,
            workspace=workspace,
            base=f"{base}.analysis_summary",
            raw=analysis_summary_path,
            kind="analysis summary",
        )
        _validate_analysis_summary_payload(
            issues,
            workspace=workspace,
            base=f"{base}.analysis_summary",
            raw=analysis_summary_path,
            artifact_manifest_path=artifact_manifest_path,
            json_payload_cache=json_payload_cache,
        )
    if analysis_summary_markdown_path:
        _warn_missing_path(
            issues,
            workspace=workspace,
            base=f"{base}.analysis_summary_markdown",
            raw=analysis_summary_markdown_path,
            kind="analysis summary markdown",
        )

    for key, kind in (
        ("chart_json_outputs", "chart JSON output"),
        ("table_outputs", "table output"),
    ):
        for idx, raw in enumerate(_list_value(plan, key) or []):
            if not isinstance(raw, str):
                issues.append(_issue(f"{base}.{key}[{idx}]", "warning", "expected a path string"))
                continue
            normalized_path = _normalize_ref(raw)
            _warn_missing_path(
                issues,
                workspace=workspace,
                base=f"{base}.{key}[{idx}]",
                raw=raw,
                kind=kind,
            )
            _validate_declared_output_payload(
                issues,
                workspace=workspace,
                base=f"{base}.{key}[{idx}]",
                raw=raw,
                kind=kind,
                fingerprint_cache=fingerprint_cache,
                json_payload_cache=json_payload_cache,
            )
            _warn_if_output_stale(
                issues,
                workspace=workspace,
                base=f"{base}.{key}[{idx}]",
                raw=raw,
                kind=kind,
                newest_source=newest_source,
                rebuild_commands=rebuild_commands,
            )
            if raw.strip() and registry_present and normalized_path not in registered_paths:
                issues.append(
                    _issue(
                        f"{base}.artifact_registry",
                        "warning",
                        f"{kind} {raw!r} is not listed in artifact_registry",
                    )
                )
            if raw.strip() and outline_refs is not None:
                alias_refs = (asset_aliases or {}).get(normalized_path, set())
                if not registry_has_slide_use.get(normalized_path, False) and not _path_used_in_outline(
                    raw,
                    outline_refs,
                    alias_refs,
                ):
                    issues.append(
                        _issue(
                            f"{base}.artifact_registry",
                            "warning",
                            f"{kind} {raw!r} is not referenced in outline.json and has no used_on_slides metadata",
                        )
                    )

    if figure_contract is not None:
        script = str(figure_contract.get("script") or "").strip()
        figure_scripts = {str(item).strip() for item in (_list_value(plan, "figure_scripts") or [])}
        if script and script.lower() != "none" and script not in figure_scripts:
            issues.append(
                _issue(
                    f"{base}.figure_scripts",
                    "warning",
                    "figure_export_contract.script should also appear in analysis_artifact_plan.figure_scripts",
                )
            )
        if script and script.lower() != "none" and not any(script in command for command in rebuild_commands):
            issues.append(
                _issue(
                    f"{base}.rebuild_commands",
                    "warning",
                    "missing rebuild command for deterministic figure script",
                )
            )
        for idx, output in enumerate(figure_contract.get("outputs") or []):
            if not isinstance(output, dict):
                continue
            path = str(output.get("path") or "").strip()
            normalized_path = _normalize_ref(path)
            if path:
                _warn_if_output_stale(
                    issues,
                    workspace=workspace,
                    base=f"{base}.artifact_registry",
                    raw=path,
                    kind="figure output",
                    newest_source=newest_source,
                    rebuild_commands=rebuild_commands,
                )
            if path and registry_present and normalized_path not in registered_paths:
                issues.append(
                    _issue(
                        f"{base}.artifact_registry",
                        "warning",
                        f"figure output {path!r} is not listed in artifact_registry",
                    )
                )
            if path and outline_refs is not None:
                alias_refs = (asset_aliases or {}).get(normalized_path, set())
                if not registry_has_slide_use.get(normalized_path, False) and not _path_used_in_outline(path, outline_refs, alias_refs):
                    issues.append(
                        _issue(
                            f"{base}.artifact_registry",
                            "warning",
                            f"figure output {path!r} is not referenced in outline.json and has no used_on_slides metadata",
                        )
                    )
    return issues


def _validate_readability_contract(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if "readability_contract" in brief and not isinstance(brief.get("readability_contract"), dict):
        return issues
    contract = _first_dict(brief, [("readability_contract",)])
    has_dense_contract = any(
        key in brief
        for key in ("analysis_artifact_plan", "figure_export_contract", "evidence_and_assets")
    )
    if contract is None:
        if has_dense_contract:
            issues.append(
                _issue(
                    "design_brief.readability_contract",
                    "warning",
                    "missing readability contract for data/figure/report deck",
                )
            )
        return issues

    numeric_minima = {
        "min_title_pt": 24.0,
        "min_body_pt": 12.0,
        "min_caption_pt": 7.5,
        "chart_label_min_pt": 7.0,
        "footer_reserved_inches": 0.25,
    }
    for key, floor in numeric_minima.items():
        value = contract.get(key)
        if value is None:
            issues.append(_issue(f"design_brief.readability_contract.{key}", "warning", "missing numeric threshold"))
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(_issue(f"design_brief.readability_contract.{key}", "warning", "expected a number"))
            continue
        if float(value) < floor:
            issues.append(
                _issue(
                    f"design_brief.readability_contract.{key}",
                    "warning",
                    f"value {value} is below recommended minimum {floor:g}",
                )
            )
    max_title_lines = contract.get("max_title_lines")
    if max_title_lines is not None:
        if isinstance(max_title_lines, bool) or not isinstance(max_title_lines, int):
            issues.append(_issue("design_brief.readability_contract.max_title_lines", "warning", "expected an integer"))
        elif max_title_lines < 1:
            issues.append(
                _issue(
                    "design_brief.readability_contract.max_title_lines",
                    "warning",
                    "expected at least 1 title line",
                )
            )
        elif max_title_lines > 3:
            issues.append(
                _issue(
                    "design_brief.readability_contract.max_title_lines",
                    "warning",
                    "more than 3 title lines risks crowding the content region",
                )
            )
    for key in ("max_slide_text_lines", "max_slide_words", "max_slide_chars"):
        value = contract.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(_issue(f"design_brief.readability_contract.{key}", "warning", "expected a positive number"))
            continue
        if value <= 0:
            issues.append(_issue(f"design_brief.readability_contract.{key}", "warning", "expected a positive number"))
    for key in ("table_density_rule", "whitespace_rule", "figure_crop_rule"):
        if not str(contract.get(key) or "").strip():
            issues.append(_issue(f"design_brief.readability_contract.{key}", "warning", "missing rule"))
    return issues


def _validate_speed_contract(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if "speed_contract" in brief and not isinstance(brief.get("speed_contract"), dict):
        return issues
    contract = _first_dict(brief, [("speed_contract",)])
    if contract is None:
        if _analysis_artifact_plan_from_brief(brief) is not None:
            issues.append(
                _issue(
                    "design_brief.speed_contract",
                    "warning",
                    "missing speed contract for artifact-heavy deck",
                )
            )
        return issues

    renderer = str(contract.get("renderer") or "").strip().lower()
    if not renderer:
        issues.append(_issue("design_brief.speed_contract.renderer", "warning", "missing renderer policy"))
    elif "pptxgenjs" not in renderer and "python" not in renderer:
        issues.append(
            _issue(
                "design_brief.speed_contract.renderer",
                "warning",
                "renderer policy should name pptxgenjs or the Python fallback",
            )
        )
    for key in ("first_pass", "render_policy", "asset_policy", "conversion_hint"):
        if not str(contract.get(key) or "").strip():
            issues.append(_issue(f"design_brief.speed_contract.{key}", "warning", "missing policy"))
    return issues


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_qa_execution_contract(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    has_applied_contract = isinstance(brief.get("design_contract"), dict)
    has_qa_fields = any(
        key in brief
        for key in (
            "qa_contract",
            "acceptance_evidence",
            "agent_execution_plan",
            "subagent_handoff",
        )
    )
    if not has_applied_contract and not has_qa_fields:
        return issues

    contract = brief.get("qa_contract") if isinstance(brief.get("qa_contract"), dict) else None
    if contract is None:
        issues.append(
            _issue(
                "design_brief.qa_contract",
                "warning",
                "missing QA contract for applied design contract",
            )
        )
    else:
        checks = contract.get("required_checks", contract.get("must_run"))
        if not isinstance(checks, list):
            issues.append(_issue("design_brief.qa_contract.required_checks", "warning", "missing required checks list"))
        else:
            check_text = " | ".join(_string_list(checks)).lower()
            if not check_text:
                issues.append(_issue("design_brief.qa_contract.required_checks", "warning", "required checks list should not be empty"))
            if "validate_planning.py" not in check_text:
                issues.append(_issue("design_brief.qa_contract.required_checks", "warning", "required checks should include validate_planning.py"))
            if "build_workspace.py" not in check_text and "qa_gate.py" not in check_text:
                issues.append(_issue("design_brief.qa_contract.required_checks", "warning", "required checks should include build_workspace.py or qa_gate.py"))
            if "report_delivery_readiness.py" not in check_text:
                issues.append(_issue("design_brief.qa_contract.required_checks", "warning", "required checks should include report_delivery_readiness.py"))

        fail_on = contract.get("fail_on")
        if not isinstance(fail_on, list) or not _string_list(fail_on):
            issues.append(_issue("design_brief.qa_contract.fail_on", "warning", "missing fail-on conditions"))
        else:
            fail_text = " | ".join(_string_list(fail_on)).lower()
            for token in ("planning", "overflow", "overlap", "whitespace"):
                if token not in fail_text:
                    issues.append(_issue("design_brief.qa_contract.fail_on", "warning", f"fail-on conditions should mention {token}"))
                    break
        if contract.get("placeholder_checks") is not True:
            issues.append(_issue("design_brief.qa_contract.placeholder_checks", "warning", "placeholder checks should be true"))

    acceptance = brief.get("acceptance_evidence")
    qa_acceptance = contract.get("acceptance_evidence") if isinstance(contract, dict) else None
    if acceptance is not None and not isinstance(acceptance, list):
        issues.append(_issue("design_brief.acceptance_evidence", "error", "must be a list when present"))
    elif not _string_list(acceptance) and not _string_list(qa_acceptance):
        issues.append(_issue("design_brief.acceptance_evidence", "warning", "missing acceptance evidence ledger"))

    execution_plan = brief.get("agent_execution_plan")
    if execution_plan is None:
        issues.append(_issue("design_brief.agent_execution_plan", "warning", "missing agent execution plan"))
    elif not isinstance(execution_plan, dict):
        issues.append(_issue("design_brief.agent_execution_plan", "error", "must be an object when present"))
    else:
        phases = execution_plan.get("phases", execution_plan.get("steps"))
        phase_ids = []
        if isinstance(phases, list):
            for item in phases:
                if isinstance(item, dict):
                    text = str(item.get("id") or item.get("phase") or item.get("name") or "").strip()
                else:
                    text = str(item or "").strip()
                if text:
                    phase_ids.append(text)
        if not phase_ids:
            issues.append(_issue("design_brief.agent_execution_plan.phases", "warning", "missing execution phases"))

    subagent_handoff = brief.get("subagent_handoff")
    if subagent_handoff is not None and not isinstance(subagent_handoff, dict):
        issues.append(_issue("design_brief.subagent_handoff", "error", "must be an object when present"))
    return issues


def _validate_contract_object_shapes(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    direct_fields = (
        "style_mix_matrix",
        "analysis_artifact_plan",
        "readability_contract",
        "speed_contract",
        "figure_export_contract",
        "qa_contract",
        "agent_execution_plan",
        "subagent_handoff",
        "reproducibility_contract",
    )
    for field in direct_fields:
        value = brief.get(field)
        if value is not None and not isinstance(value, dict):
            issues.append(_issue(f"design_brief.{field}", "error", "must be an object when present"))

    nested_specs = (
        ("style_system", "style_mix_matrix"),
        ("evidence_and_assets", "analysis_artifact_plan"),
        ("evidence_and_assets", "figure_export_contract"),
    )
    for parent, child in nested_specs:
        container = brief.get(parent)
        if container is None:
            continue
        if not isinstance(container, dict):
            issues.append(_issue(f"design_brief.{parent}", "error", "must be an object when present"))
            continue
        value = container.get(child)
        if value is not None and not isinstance(value, dict):
            issues.append(_issue(f"design_brief.{parent}.{child}", "error", "must be an object when present"))
    return issues


def _validate_reproducibility_contract(brief: dict[str, Any]) -> list[dict[str, str]]:
    replay = brief.get("reproducibility_contract")
    if replay is None:
        return []
    if not isinstance(replay, dict):
        return [_issue("design_brief.reproducibility_contract", "error", "must be an object when present")]

    issues: list[dict[str, str]] = []
    version = str(replay.get("contract_version") or "").strip()
    if version and version != "deck_reproducibility_contract_v1":
        issues.append(
            _issue(
                "design_brief.reproducibility_contract.contract_version",
                "warning",
                "unexpected reproducibility contract version",
            )
        )
    style_seed = str(replay.get("style_seed") or "").strip()
    style_system = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    expected_seed = str(style_system.get("style_seed") or "").strip() if isinstance(style_system, dict) else ""
    if expected_seed and style_seed and style_seed != expected_seed:
        issues.append(
            _issue(
                "design_brief.reproducibility_contract.style_seed",
                "warning",
                "replay contract style_seed differs from style_system.style_seed",
            )
        )
    for key in ("locked_design_fields", "replay_commands", "acceptance_evidence"):
        value = replay.get(key)
        if value is not None and not isinstance(value, list):
            issues.append(
                _issue(
                    f"design_brief.reproducibility_contract.{key}",
                    "error",
                    "must be a list when present",
                )
            )
    for key in ("style_replay", "structure_replay", "artifact_replay", "replay_inputs"):
        value = replay.get(key)
        if value is not None and not isinstance(value, dict):
            issues.append(
                _issue(
                    f"design_brief.reproducibility_contract.{key}",
                    "error",
                    "must be an object when present",
                )
            )
    return issues


def _validate_choice_resolution_payload(
    choice_resolution: Any,
    *,
    base_path: str,
    expected_seed: str = "",
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not isinstance(choice_resolution, dict):
        return [
            _issue(
                base_path,
                "error",
                "must be an object when present",
            )
        ]

    choices = choice_resolution.get("resolved_choices", choice_resolution.get("choice_ledger"))
    if choices is not None and not isinstance(choices, list):
        issues.append(
            _issue(
                f"{base_path}.resolved_choices",
                "error",
                "must be a list when present",
            )
        )
    elif not _string_list(choices):
        issues.append(
            _issue(
                f"{base_path}.resolved_choices",
                "warning",
                "missing resolved question-card choices",
            )
        )

    routes = choice_resolution.get("route_decisions")
    if routes is not None and not isinstance(routes, list):
        issues.append(
            _issue(
                f"{base_path}.route_decisions",
                "error",
                "must be a list when present",
            )
        )
    elif isinstance(routes, list):
        for index, item in enumerate(routes):
            if not isinstance(item, dict):
                issues.append(
                    _issue(
                        f"{base_path}.route_decisions[{index}]",
                        "error",
                        "must be an object",
                    )
                )
                continue
            if not str(item.get("id") or "").strip():
                issues.append(
                    _issue(
                        f"{base_path}.route_decisions[{index}].id",
                        "warning",
                        "missing route id",
                    )
                )
            if "active" in item and not isinstance(item.get("active"), bool):
                issues.append(
                    _issue(
                        f"{base_path}.route_decisions[{index}].active",
                        "warning",
                        "active should be boolean when present",
                    )
                )

    choice_seed = str(choice_resolution.get("stable_prompt_id") or "").strip()
    if choice_seed and expected_seed and choice_seed != expected_seed:
        issues.append(
            _issue(
                f"{base_path}.stable_prompt_id",
                "warning",
                "choice-resolution seed differs from expected style or design-contract seed",
            )
        )
    return issues


def _validate_choice_resolution_contract(brief: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    style_system = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    style_seed = str(style_system.get("style_seed") or "").strip() if isinstance(style_system, dict) else ""

    seed = brief.get("choice_resolution_seed")
    if seed is not None:
        issues.extend(
            _validate_choice_resolution_payload(
                seed,
                base_path="design_brief.choice_resolution_seed",
                expected_seed=style_seed,
            )
        )

    design_contract = brief.get("design_contract")
    if not isinstance(design_contract, dict):
        return issues
    choice_resolution = design_contract.get("choice_resolution")
    if choice_resolution is None:
        return issues
    applied_seed = str(design_contract.get("stable_prompt_id") or "").strip()
    issues.extend(
        _validate_choice_resolution_payload(
            choice_resolution,
            base_path="design_brief.design_contract.choice_resolution",
            expected_seed=applied_seed,
        )
    )
    return issues


def _validate_design_brief(
    brief: Any,
    *,
    workspace: Path | None = None,
    outline: Any | None = None,
    outline_refs: set[str] | None = None,
    asset_aliases: dict[str, set[str]] | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if brief is None:
        return issues
    if not isinstance(brief, dict):
        return [_issue("design_brief.json", "error", "root must be an object")]
    issues.extend(_validate_contract_object_shapes(brief))
    issues.extend(_validate_reproducibility_contract(brief))
    issues.extend(_validate_choice_resolution_contract(brief))
    issues.extend(_validate_style_preset(brief))
    issues.extend(_validate_style_treatments(brief))

    if not str(brief.get("format_promise") or "").strip():
        issues.append(_issue("design_brief.format_promise", "warning", "missing format promise"))

    structure = brief.get("structure_strategy")
    if not isinstance(structure, dict):
        issues.append(_issue("design_brief.structure_strategy", "warning", "missing structure strategy object"))
    elif not str(structure.get("container_policy") or "").strip():
        issues.append(_issue("design_brief.structure_strategy.container_policy", "warning", "missing container/card policy"))

    title_page = brief.get("title_page_concept")
    if not isinstance(title_page, dict):
        issues.append(_issue("design_brief.title_page_concept", "warning", "missing title page concept object"))
    elif not str(title_page.get("chosen_archetype") or "").strip():
        issues.append(_issue("design_brief.title_page_concept.chosen_archetype", "warning", "missing cover archetype"))

    user_intake = brief.get("user_intake")
    if user_intake is not None:
        if not isinstance(user_intake, dict):
            issues.append(_issue("design_brief.user_intake", "error", "must be an object when present"))
        else:
            answered_by = str(user_intake.get("answered_by") or "").strip()
            if answered_by and answered_by not in {"user", "inferred", "best_judgment"}:
                issues.append(
                    _issue(
                        "design_brief.user_intake.answered_by",
                        "warning",
                        "expected user, inferred, or best_judgment",
                    )
                )
            unanswered = user_intake.get("unanswered")
            if unanswered is not None and not isinstance(unanswered, (str, list)):
                issues.append(
                    _issue(
                        "design_brief.user_intake.unanswered",
                        "warning",
                        "expected a string or list of skipped intake questions",
                    )
                )

    modulation = brief.get("design_modulation")
    if modulation is not None:
        if not isinstance(modulation, dict):
            issues.append(_issue("design_brief.design_modulation", "error", "must be an object when present"))
        else:
            intensity = str(modulation.get("change_intensity") or "").strip()
            if intensity and intensity not in {"subtle", "moderate", "bold"}:
                issues.append(
                    _issue(
                        "design_brief.design_modulation.change_intensity",
                        "warning",
                        "expected subtle, moderate, or bold",
                    )
                )
            if not str(modulation.get("accent_strategy") or "").strip():
                issues.append(
                    _issue(
                        "design_brief.design_modulation.accent_strategy",
                        "warning",
                        "missing accent strategy",
                    )
                )
            if not str(modulation.get("container_strategy") or "").strip():
                issues.append(
                    _issue(
                        "design_brief.design_modulation.container_strategy",
                        "warning",
                        "missing container strategy",
                    )
                )

    continuity = brief.get("evidence_continuity")
    if continuity is not None:
        if not isinstance(continuity, dict):
            issues.append(_issue("design_brief.evidence_continuity", "error", "must be an object when present"))
        else:
            threads = continuity.get("threads") or continuity.get("primary_threads")
            if not isinstance(threads, list) or not any(str(item).strip() for item in threads):
                issues.append(
                    _issue(
                        "design_brief.evidence_continuity.threads",
                        "warning",
                        "missing evidence/readout threads to carry across slides",
                    )
                )
                thread_names: set[str] = set()
            else:
                thread_names = {str(item).strip() for item in threads if str(item).strip()}
            if not str(continuity.get("carry_forward_rule") or "").strip():
                issues.append(
                    _issue(
                        "design_brief.evidence_continuity.carry_forward_rule",
                        "warning",
                        "missing rule for how title-slide motifs continue on content slides",
                    )
                )
            applications = continuity.get("slide_applications")
            if applications is not None and not isinstance(applications, list):
                issues.append(
                    _issue(
                        "design_brief.evidence_continuity.slide_applications",
                        "error",
                        "must be a list when present",
                    )
                )
            elif isinstance(applications, list):
                for idx, application in enumerate(applications):
                    base = f"design_brief.evidence_continuity.slide_applications[{idx}]"
                    if not isinstance(application, dict):
                        issues.append(_issue(base, "warning", "slide application should be an object"))
                        continue
                    slide_ref = ""
                    slide_key = ""
                    for key in ("slide_id", "slide_id_or_index", "slide"):
                        if key in application:
                            slide_ref = str(application.get(key) or "").strip()
                            slide_key = key
                            break
                    if not slide_key:
                        issues.append(_issue(base, "warning", "missing slide reference"))
                    elif not slide_ref:
                        issues.append(_issue(f"{base}.{slide_key}", "warning", "empty slide reference will be ignored"))
                    elif _outline_has_slides(outline) and not _outline_slide_reference_exists(slide_ref, outline):
                        issues.append(
                            _issue(
                                f"{base}.{slide_key}",
                                "warning",
                                f"slide reference {slide_ref!r} was not found in outline.json",
                            )
                        )
                    thread = str(application.get("thread") or "").strip()
                    if thread_names and thread and thread not in thread_names:
                        issues.append(
                            _issue(
                                f"{base}.thread",
                                "warning",
                                f"thread {thread!r} is not listed in evidence_continuity.threads",
                            )
                        )

    figure_contract = _figure_contract_from_brief(brief)
    if figure_contract is not None:
        if not isinstance(figure_contract, dict):
            issues.append(_issue("design_brief.figure_export_contract", "error", "must be an object when present"))
        else:
            base_path = (
                "design_brief.evidence_and_assets.figure_export_contract"
                if _nested_dict(brief, "evidence_and_assets", "figure_export_contract") is figure_contract
                else "design_brief.figure_export_contract"
            )
            script = str(figure_contract.get("script") or "").strip()
            rerun_command = str(figure_contract.get("rerun_command") or "").strip()
            outputs = figure_contract.get("outputs")
            _validate_artifact_rebuild_context(
                issues,
                base=f"{base_path}.rebuild_context",
                context=figure_contract.get("rebuild_context")
                if "rebuild_context" in figure_contract
                else None,
                expected_output_count=len(outputs) if isinstance(outputs, list) else None,
                expected_producer_path=script,
            )
            if not script:
                issues.append(
                    _issue(
                        f"{base_path}.script",
                        "warning",
                        "missing deterministic figure-generation script path",
                    )
                )
            else:
                _warn_missing_path(
                    issues,
                    workspace=workspace,
                    base=f"{base_path}.script",
                    raw=script,
                    kind="figure script",
                )
                if script.lower() != "none":
                    if not rerun_command:
                        issues.append(
                            _issue(
                                f"{base_path}.rerun_command",
                                "warning",
                                "missing rerun command for deterministic figure script",
                            )
                        )
                    elif script not in rerun_command:
                        issues.append(
                            _issue(
                                f"{base_path}.rerun_command",
                                "warning",
                                f"rerun_command should include figure script path {script!r}",
                            )
                        )
            if not isinstance(outputs, list) or not outputs:
                issues.append(
                    _issue(
                        f"{base_path}.outputs",
                        "warning",
                        "missing slide-ready figure outputs and target layouts",
                    )
                )
            else:
                seen_output_paths: dict[str, int] = {}
                for idx, output in enumerate(outputs):
                    base = f"{base_path}.outputs[{idx}]"
                    if not isinstance(output, dict):
                        issues.append(_issue(base, "error", "figure output entry must be an object"))
                        continue
                    figure_path = str(output.get("path") or "").strip()
                    if not figure_path:
                        issues.append(_issue(f"{base}.path", "warning", "missing figure output path"))
                    else:
                        _warn_missing_path(
                            issues,
                            workspace=workspace,
                            base=f"{base}.path",
                            raw=figure_path,
                            kind="figure output",
                        )
                        normalized_figure_path = _normalize_ref(figure_path)
                        previous_idx = seen_output_paths.get(normalized_figure_path)
                        if previous_idx is not None:
                            issues.append(
                                _issue(
                                    f"{base}.path",
                                    "warning",
                                    (
                                        f"duplicate figure output path {figure_path!r}; "
                                        f"already listed at {base_path}.outputs[{previous_idx}]"
                                    ),
                                )
                            )
                        else:
                            seen_output_paths[normalized_figure_path] = idx
                    if not str(output.get("target_variant") or "").strip():
                        issues.append(_issue(f"{base}.target_variant", "warning", "missing target slide variant"))
                    target_box = str(output.get("target_box") or "").strip()
                    if not target_box:
                        issues.append(_issue(f"{base}.target_box", "warning", "missing rendered target box size"))
                    else:
                        target_box_dims = _target_box_dimensions(target_box)
                        if target_box_dims is None:
                            issues.append(
                                _issue(
                                    f"{base}.target_box",
                                    "warning",
                                    "target_box should include width x height in inches, e.g. 5.0x3.3 in",
                                )
                            )
                        else:
                            width, height = target_box_dims
                            if width < MIN_FIGURE_TARGET_BOX_WIDTH or height < MIN_FIGURE_TARGET_BOX_HEIGHT:
                                issues.append(
                                    _issue(
                                        f"{base}.target_box",
                                        "warning",
                                        (
                                            f"target_box {target_box!r} may be too small for readable figure labels; "
                                            f"use at least {MIN_FIGURE_TARGET_BOX_WIDTH:g}x"
                                            f"{MIN_FIGURE_TARGET_BOX_HEIGHT:g} in or switch layouts"
                                        ),
                                    )
                                )
                    if not str(output.get("crop_rule") or "").strip():
                        issues.append(_issue(f"{base}.crop_rule", "warning", "missing crop/whitespace rule"))
                    if script and script.lower() != "none":
                        export_metadata_issue = _figure_output_export_metadata_issue(output, item_name=base)
                        if export_metadata_issue:
                            issues.append(_issue(base, "warning", export_metadata_issue))
                    slide_ref = ""
                    slide_key = ""
                    for key in ("target_slide", "target_slide_id", "slide_id", "slide"):
                        if key in output:
                            slide_ref = str(output.get(key) or "").strip()
                            slide_key = key
                            break
                    if slide_key:
                        if not slide_ref:
                            issues.append(_issue(f"{base}.{slide_key}", "warning", "empty target slide will be ignored"))
                        elif _outline_has_slides(outline):
                            target_slide = _outline_slide_for_reference(slide_ref, outline)
                            if target_slide is None:
                                issues.append(
                                    _issue(
                                        f"{base}.{slide_key}",
                                        "warning",
                                        f"target slide {slide_ref!r} was not found in outline.json",
                                    )
                                )
                            else:
                                raw_target_variant = str(output.get("target_variant") or "").strip()
                                target_variant = _normalize_slide_variant(raw_target_variant)
                                outline_variant = _outline_slide_variant(target_slide)
                                if (
                                    target_variant
                                    and outline_variant
                                    and "|" not in raw_target_variant
                                    and target_variant != outline_variant
                                ):
                                    issues.append(
                                        _issue(
                                            f"{base}.target_variant",
                                            "warning",
                                            (
                                                f"target variant {raw_target_variant!r} does not match "
                                                f"outline slide {slide_ref!r} variant {outline_variant!r}"
                                            ),
                                        )
                                    )
    issues.extend(_validate_style_mix_matrix(brief))
    issues.extend(
        _validate_analysis_artifact_plan(
            brief,
            workspace=workspace,
            outline=outline,
            outline_refs=outline_refs,
            asset_aliases=asset_aliases,
        )
    )
    issues.extend(_validate_readability_contract(brief))
    issues.extend(_validate_speed_contract(brief))
    issues.extend(_validate_qa_execution_contract(brief))
    return issues


def validate(workspace: Path) -> dict[str, Any]:
    content_plan, content_load_issues = _load_json(workspace / "content_plan.json")
    design_brief, design_load_issues = _load_json(workspace / "design_brief.json")
    evidence_plan, evidence_load_issues = _load_json(workspace / "evidence_plan.json")
    outline, outline_load_issues = _load_json(workspace / "outline.json")
    asset_plan, asset_load_issues = _load_json(workspace / "asset_plan.json")
    outline_refs = _collect_outline_refs(outline) if isinstance(outline, dict) else None
    asset_aliases = _asset_aliases_by_path(asset_plan)
    evidence_ids, evidence_issues = _validate_evidence_plan(evidence_plan, outline, workspace=workspace)
    asset_plan_issues = _validate_asset_plan_references(asset_plan, outline, workspace=workspace)
    content_issues = _validate_content_plan(content_plan, evidence_ids, outline)
    outline_id_issues = _validate_outline_slide_identifiers(outline)
    alignment_issues = _validate_content_plan_outline_alignment(content_plan, outline)
    design_issues = _validate_design_brief(
        design_brief,
        workspace=workspace,
        outline=outline,
        outline_refs=outline_refs,
        asset_aliases=asset_aliases,
    )
    issues = [
        *content_load_issues,
        *design_load_issues,
        *evidence_load_issues,
        *outline_load_issues,
        *asset_load_issues,
        *evidence_issues,
        *asset_plan_issues,
        *content_issues,
        *outline_id_issues,
        *alignment_issues,
        *design_issues,
    ]
    return {
        "issues": issues,
        "error_count": sum(1 for issue in issues if issue["severity"] == "error"),
        "warning_count": sum(1 for issue in issues if issue["severity"] == "warning"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate content_plan.json, design_brief.json, and evidence_plan.json.")
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument("--report", help="Optional JSON report path")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    payload = validate(workspace)
    if args.report:
        report = Path(args.report).expanduser().resolve()
        _write_json_if_changed(report, payload)
    print(json.dumps(payload, indent=2))
    if payload["error_count"]:
        return 2
    if payload["warning_count"]:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
