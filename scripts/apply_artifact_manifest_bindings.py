#!/usr/bin/env python3
"""Apply generated artifact manifest selections to outline and planning files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from inspect_artifact_manifest import inspect_manifest


_STARTER_SLIDE_ID = "s2"
_STARTER_TITLE = "Core message"
_STARTER_SUBTITLE = "Start from the decision or takeaway"
_STARTER_BULLETS = [
    "State the main decision, result, or recommendation first.",
    "Use one evidence object per content slide when data is available.",
    "Keep source-backed claims explicit and traceable to the planning files.",
    "Convert dense prose into a chart, table, figure, or short comparison.",
]
_STARTER_HIGHLIGHTS = [
    "Alignment and readability are release gates.",
    "Assets stay source-backed and optional.",
    "QA blocks overlap, overflow, and sparse layouts.",
]


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json_if_changed(path: Path, payload: Any, *, dry_run: bool) -> bool:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _workspace_path(workspace: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


def _merge_unique(existing: Any, additions: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in [*(existing if isinstance(existing, list) else []), *additions]:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        merged.append(text)
    return merged


def _load_selections(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path, None)
    return _normalize_selections(payload)


def _normalize_selections(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        selections = payload
    elif isinstance(payload, dict):
        selections = payload.get("bindings") or payload.get("selections") or payload.get("slides")
    else:
        selections = None
    if not isinstance(selections, list):
        raise ValueError("selection file must be a list or contain bindings/selections/slides list")
    valid = [item for item in selections if isinstance(item, dict)]
    if len(valid) != len(selections):
        raise ValueError("all selections must be objects")
    return valid


def _parse_csv_tokens(raw: str, *, default: list[str]) -> list[str]:
    tokens = [item.strip() for item in raw.split(",") if item.strip()]
    return tokens or default


def _alias_plan_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    alias_plan = report.get("alias_plan")
    if not isinstance(alias_plan, list):
        return {}
    return {
        str(item.get("id") or "").strip(): item
        for item in alias_plan
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _available_variants(plan: dict[str, Any]) -> set[str]:
    snippets = plan.get("outline_field_snippets")
    if not isinstance(snippets, list):
        return set()
    variants: set[str] = set()
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        variant = str(snippet.get("variant") or "").strip()
        if variant:
            variants.add(variant)
    return variants


def _slide_suffix_for_variant(variant: str) -> str:
    normalized = variant.strip().lower()
    if normalized in {"image-sidebar", "scientific-figure"}:
        return "figure"
    if normalized == "chart":
        return "chart"
    if normalized in {"lab-run-results", "table"}:
        return "table"
    return normalized.replace("_", "-").replace(" ", "-") or "artifact"


def _compact_source_label(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return ""
    if "/" in clean or "\\" in clean:
        return Path(clean).name
    return clean


def _value_columns(plan: dict[str, Any]) -> list[str]:
    metadata = plan.get("analysis_metadata")
    raw = metadata.get("value_cols") if isinstance(metadata, dict) else None
    if not isinstance(raw, list):
        raw = plan.get("value_cols")
    return [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []


def _compact_metric_label(plan: dict[str, Any]) -> str:
    values = _value_columns(plan)
    if values:
        shown = values[:2]
        suffix = f" +{len(values) - 2} more" if len(values) > 2 else ""
        return " + ".join(shown) + suffix
    columns = _selected_columns(plan)
    if len(columns) >= 2:
        shown = columns[1:3]
        suffix = f" +{len(columns) - 3} more" if len(columns) > 3 else ""
        return " + ".join(shown) + suffix
    return ""


def _auto_selection_title(plan: dict[str, Any], variant: str) -> str:
    title = _compact_source_label(str(plan.get("title") or "").strip())
    source = _compact_source_label(_source_label(plan))
    metric = _compact_metric_label(plan)
    base = title or source or str(plan.get("id") or "Generated artifact").strip()
    if metric and metric.lower() not in base.lower():
        base = f"{base}: {metric}"
    if base:
        return _trim_text(base, max_chars=56)
    title = str(plan.get("id") or "Generated artifact").strip()
    normalized = variant.strip().lower()
    if normalized in {"image-sidebar", "scientific-figure"}:
        return f"{title} generated figure"
    if normalized == "chart":
        return f"{title} editable chart"
    if normalized in {"lab-run-results", "table"}:
        return f"{title} summary table"
    return title


def _source_label(plan: dict[str, Any]) -> str:
    return str(plan.get("source_label") or plan.get("source_path") or plan.get("id") or "").strip()


def _readout_primary(plan: dict[str, Any]) -> str:
    summary = plan.get("readout_summary")
    if isinstance(summary, dict):
        primary = str(summary.get("primary") or "").strip()
        if primary:
            return primary
    metadata = plan.get("analysis_metadata")
    if isinstance(metadata, dict):
        nested = metadata.get("readout_summary")
        if isinstance(nested, dict):
            primary = str(nested.get("primary") or "").strip()
            if primary:
                return primary
    return ""


def _readability_notes(plan: dict[str, Any]) -> list[str]:
    raw = plan.get("readability_warnings")
    if not isinstance(raw, list):
        metadata = plan.get("analysis_metadata")
        raw = metadata.get("readability_warnings") if isinstance(metadata, dict) else []
    return [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []


def _trim_text(text: str, *, max_chars: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_chars:
        return clean
    candidate = clean[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{candidate or clean[: max_chars - 1].rstrip()}..."


def _selected_columns(plan: dict[str, Any]) -> list[str]:
    raw = plan.get("selected_columns")
    if not isinstance(raw, list):
        metadata = plan.get("analysis_metadata")
        raw = metadata.get("selected_columns") if isinstance(metadata, dict) else []
    return [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []


def _selection_selected_columns(selection: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    raw = selection.get("selected_columns")
    if isinstance(raw, list):
        columns = [str(item).strip() for item in raw if str(item).strip()]
        if columns:
            return columns
    return _selected_columns(plan)


def _column_list_text(columns: list[str], *, max_items: int = 5) -> str:
    clean = [str(item).strip() for item in columns if str(item).strip()]
    if not clean:
        return ""
    shown = clean[:max_items]
    suffix = f" +{len(clean) - max_items} more" if len(clean) > max_items else ""
    return ", ".join(shown) + suffix


def _source_columns_caption(plan: dict[str, Any]) -> str:
    parts: list[str] = []
    source = _source_label(plan)
    if source:
        parts.append(f"Source: {source}")
    columns = _column_list_text(_selected_columns(plan))
    if columns:
        parts.append(f"Columns: {columns}")
    return "; ".join(parts) + "." if parts else ""


def _auto_selection_message(plan: dict[str, Any]) -> str:
    return _readout_primary(plan) or str(plan.get("title") or plan.get("id") or "Generated evidence").strip()


def _layout_recommendation(plan: dict[str, Any]) -> dict[str, Any]:
    recommendation = plan.get("layout_recommendation")
    return recommendation if isinstance(recommendation, dict) else {}


def _layout_extras(plan: dict[str, Any], variant: str) -> dict[str, Any]:
    recommendation = _layout_recommendation(plan)
    if not recommendation:
        return {}
    normalized = variant.strip()
    lead_variant = str(recommendation.get("lead_variant") or "").strip()
    role = "lead" if normalized == lead_variant else "support"
    return {
        "layout_role": role,
        "layout_density": recommendation.get("density"),
        "layout_rationale": recommendation.get("rationale") or [],
    }


def _auto_selection_extras(plan: dict[str, Any], variant: str) -> dict[str, Any]:
    normalized = variant.strip().lower()
    source_label = _source_label(plan)
    primary_readout = _readout_primary(plan)
    readability_notes = _readability_notes(plan)
    layout_extras = _layout_extras(plan, variant)
    caption = _source_columns_caption(plan)
    if normalized in {"image-sidebar", "scientific-figure"}:
        input_text = f"Source: {source_label}." if source_label else "Generated from the artifact manifest."
        sidebar_sections = [
            {"title": "Evidence", "body": [input_text]},
            {
                "title": "Readout",
                "body": [
                    primary_readout
                    or "Generated figure plus editable chart/table artifacts are registered for rebuilds."
                ],
            },
        ]
        if readability_notes:
            sidebar_sections.append({"title": "QA", "body": readability_notes[:2]})
        return {
            "subtitle": "Evidence figure with reproducible source metadata",
            "sidebar_body_font_size": 16,
            "interpretation": primary_readout
            or "Use this generated figure as the primary readout; revise the figure script for final analysis choices.",
            **({"caption": caption} if caption else {}),
            "sidebar_sections": sidebar_sections,
            **layout_extras,
        }
    if normalized == "chart":
        return {
            "subtitle": "Evidence readout from generated analysis artifacts",
            **({"caption": caption} if caption else {}),
            **({"interpretation": primary_readout} if primary_readout else {}),
            **layout_extras,
        }
    if normalized in {"lab-run-results", "table"}:
        return {
            "subtitle": "Evidence readout table from generated analysis artifacts",
            **({"caption": caption} if caption else {}),
            "interpretation": primary_readout
            or "Compact generated table keeps the run summary editable in PowerPoint.",
            **layout_extras,
        }
    return {}


def _variant_order_for_mode(plan: dict[str, Any], requested_variants: list[str], mode: str) -> list[str]:
    normalized_mode = (mode or "all").strip().lower()
    recommendation = _layout_recommendation(plan)
    if normalized_mode == "lead":
        lead = str(recommendation.get("lead_variant") or "").strip()
        if lead and lead in requested_variants:
            return [lead]
        return requested_variants[:1]
    if normalized_mode == "recommended":
        priority = [
            str(item).strip()
            for item in recommendation.get("priority_variants", [])
            if str(item).strip()
        ]
        if priority:
            return [
                *[variant for variant in priority if variant in requested_variants],
                *[variant for variant in requested_variants if variant not in priority],
            ]
    return requested_variants


def generate_auto_selections(
    report: dict[str, Any],
    *,
    output_ids: list[str] | None = None,
    variants: list[str] | None = None,
    mode: str = "all",
) -> list[dict[str, Any]]:
    requested_variants = variants or ["image-sidebar", "chart", "lab-run-results"]
    selected_ids = {item for item in (output_ids or []) if item}
    selections: list[dict[str, Any]] = []
    for plan in report.get("alias_plan") or []:
        if not isinstance(plan, dict):
            continue
        output_id = str(plan.get("id") or "").strip()
        if not output_id or (selected_ids and output_id not in selected_ids):
            continue
        available = _available_variants(plan)
        for variant in _variant_order_for_mode(plan, requested_variants, mode):
            if variant not in available:
                continue
            suffix = _slide_suffix_for_variant(variant)
            selections.append(
                {
                    "output_id": output_id,
                    "variant": variant,
                    "slide_id": f"{output_id}_{suffix}",
                    "title": _auto_selection_title(plan, variant),
                    "message": _auto_selection_message(plan),
                    "selected_columns": _selected_columns(plan),
                    **_auto_selection_extras(plan, variant),
                }
            )
    return selections


def _snippet_fields(plan: dict[str, Any], variant: str) -> dict[str, Any]:
    snippets = plan.get("outline_field_snippets")
    if not isinstance(snippets, list):
        return {}
    for snippet in snippets:
        if not isinstance(snippet, dict):
            continue
        if str(snippet.get("variant") or "").strip() != variant:
            continue
        fields = snippet.get("fields")
        return dict(fields) if isinstance(fields, dict) else {}
    return {}


def _selection_slide(selection: dict[str, Any], plan: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    output_id = str(selection.get("output_id") or selection.get("id") or "").strip()
    variant = str(selection.get("variant") or selection.get("slide_variant") or "image-sidebar").strip()
    slide_id = str(selection.get("slide_id") or selection.get("target_slide") or "").strip()
    if not output_id:
        raise ValueError("selection is missing output_id")
    if not slide_id:
        raise ValueError(f"selection for {output_id!r} is missing slide_id")
    fields = _snippet_fields(plan, variant)
    if not fields:
        raise ValueError(f"selection for {output_id!r} references unavailable variant {variant!r}")
    slide = {
        "type": "content",
        **fields,
        "slide_id": slide_id,
        "title": str(selection.get("title") or plan.get("title") or output_id),
    }
    selected_columns = _selection_selected_columns(selection, plan)
    if selected_columns:
        slide["selected_columns"] = selected_columns
    for key in (
        "subtitle",
        "kicker",
        "interpretation",
        "caption",
        "footer",
        "summary_callout",
        "takeaway",
    ):
        if key in selection:
            slide[key] = selection[key]
    for key in ("sidebar_body_font_size",):
        value = selection.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            slide[key] = value
    layout_role = str(selection.get("layout_role") or "").strip()
    layout_density = str(selection.get("layout_density") or "").strip()
    layout_rationale = [
        str(item).strip()
        for item in selection.get("layout_rationale", [])
        if str(item).strip()
    ] if isinstance(selection.get("layout_rationale"), list) else []
    if layout_role or layout_density or layout_rationale:
        slide["layout_recommendation"] = {
            key: value
            for key, value in {
                "role": layout_role,
                "density": layout_density,
                "rationale": layout_rationale,
            }.items()
            if value
        }
    for key in ("sidebar_sections", "bullets", "notes", "sources"):
        if key in selection and isinstance(selection.get(key), list):
            slide[key] = selection[key]
    required_ids = [str(item).strip() for item in fields.get("required_artifact_ids", []) if str(item).strip()]
    return slide, required_ids


def _selection_content_plan_entry(
    selection: dict[str, Any],
    slide: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    slide_id = str(slide.get("slide_id") or "").strip()
    variant = str(slide.get("variant") or selection.get("variant") or selection.get("slide_variant") or "").strip()
    output_id = str(selection.get("output_id") or selection.get("id") or "").strip()
    title = str(slide.get("title") or output_id or slide_id).strip()
    message = str(selection.get("message") or selection.get("interpretation") or title).strip()
    visual_strategy = str(selection.get("visual_strategy") or slide.get("visual_intent") or variant or "generated evidence").strip()
    entry = {
        "slide_id": slide_id,
        "role": str(selection.get("role") or "evidence").strip(),
        "message": message,
        "variant": variant,
        "visual_strategy": visual_strategy,
        "evidence_needs": [output_id] if output_id else [],
    }
    selected_columns = _selection_selected_columns(selection, plan)
    if selected_columns:
        entry["selected_columns"] = selected_columns
    if "layout_role" in selection:
        entry["layout_role"] = selection["layout_role"]
    if "layout_density" in selection:
        entry["layout_density"] = selection["layout_density"]
    if "notes" in selection:
        entry["notes"] = selection["notes"]
    return entry


def _variant_visual_use(variant: str) -> str:
    normalized = variant.strip().lower()
    if normalized in {"lab-run-results", "table"}:
        return "table"
    if normalized == "chart":
        return "chart"
    if normalized in {"image-sidebar", "scientific-figure"}:
        return "figure"
    return "chart"


_VISUAL_USE_ORDER = ("bullet", "kpi", "figure", "chart", "table", "footer-source")


def _visual_use_tokens(value: Any) -> list[str]:
    raw_tokens: list[str] = []
    if isinstance(value, list):
        raw_tokens = [str(item) for item in value]
    else:
        raw_tokens = str(value or "").replace(",", "|").split("|")
    seen: set[str] = set()
    tokens: list[str] = []
    for token in raw_tokens:
        normalized = token.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens


def _merge_visual_use(existing: Any, incoming: Any) -> str:
    tokens = _visual_use_tokens(existing) + _visual_use_tokens(incoming)
    seen: set[str] = set()
    merged: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        merged.append(token)
    ordered = [token for token in _VISUAL_USE_ORDER if token in seen]
    ordered.extend(token for token in merged if token not in _VISUAL_USE_ORDER)
    return " | ".join(ordered)


def _artifact_context(plan: dict[str, Any]) -> dict[str, Any]:
    bindings = plan.get("artifact_bindings")
    if not isinstance(bindings, list):
        return {}
    artifact_ids: list[str] = []
    aliases: dict[str, str] = {}
    paths: dict[str, str] = {}
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        artifact_id = str(binding.get("artifact_id") or "").strip()
        alias = str(binding.get("alias") or "").strip()
        path = str(binding.get("path") or "").strip()
        if artifact_id:
            artifact_ids.append(artifact_id)
        role = str(binding.get("role") or "").strip().lower()
        outline_field = str(binding.get("outline_field") or "").strip()
        role_key = ""
        if "figure" in role or outline_field == "assets.hero_image":
            role_key = "figure"
        elif "chart" in role or outline_field == "assets.chart_data":
            role_key = "chart"
        elif "table" in role or "table" in outline_field:
            role_key = "table"
        if role_key and alias:
            aliases[role_key] = alias
        if role_key and path:
            paths[role_key] = path
    context: dict[str, Any] = {}
    if artifact_ids:
        context["artifact_ids"] = artifact_ids
    if aliases:
        context["artifact_aliases"] = aliases
    if paths:
        context["artifact_paths"] = paths
    return context


def _selection_evidence_item(
    selection: dict[str, Any],
    slide: dict[str, Any],
    plan: dict[str, Any],
    *,
    generated_by: str,
) -> dict[str, Any]:
    output_id = str(selection.get("evidence_id") or selection.get("output_id") or selection.get("id") or "").strip()
    slide_id = str(slide.get("slide_id") or "").strip()
    variant = str(slide.get("variant") or selection.get("variant") or selection.get("slide_variant") or "").strip()
    title = str(slide.get("title") or plan.get("title") or output_id).strip()
    source_path = str(plan.get("source_path") or "").strip()
    source_label = str(plan.get("source_label") or source_path).strip()
    claim = str(selection.get("claim") or selection.get("message") or selection.get("interpretation") or title).strip()
    source_note = str(selection.get("source_note") or "").strip()
    if not source_note:
        if source_label and generated_by:
            source_note = f"Generated from {source_label} by {generated_by}."
        elif source_label:
            source_note = f"Generated from {source_label}."
        elif generated_by:
            source_note = f"Generated by {generated_by}."
    item = {
        "id": output_id,
        "claim": claim,
        "visual_use": str(selection.get("visual_use") or _variant_visual_use(variant)).strip(),
        "source_note": source_note,
        "used_on_slides": [slide_id] if slide_id else [],
    }
    if source_path:
        item["source_path"] = source_path
    selected_columns = _selection_selected_columns(selection, plan)
    if selected_columns:
        item["selected_columns"] = selected_columns
    item.update(_artifact_context(plan))
    if "metric" in selection:
        item["metric"] = selection["metric"]
    if "value" in selection:
        item["value"] = selection["value"]
    return item


def _slide_key(slide: dict[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "slug"):
        text = str(slide.get(key) or "").strip()
        if text:
            return text
    return f"s{index}"


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _is_default_starter_slide(slide: dict[str, Any]) -> bool:
    return (
        str(slide.get("slide_id") or slide.get("id") or slide.get("slug") or "").strip() == _STARTER_SLIDE_ID
        and str(slide.get("type") or "").strip() == "content"
        and str(slide.get("variant") or "").strip() == "split"
        and str(slide.get("title") or "").strip() == _STARTER_TITLE
        and str(slide.get("subtitle") or "").strip() == _STARTER_SUBTITLE
        and _string_list(slide.get("bullets")) == _STARTER_BULLETS
        and _string_list(slide.get("highlights")) == _STARTER_HIGHLIGHTS
    )


def _remove_default_starter_slides(outline: dict[str, Any]) -> list[str]:
    slides = outline.get("slides")
    if not isinstance(slides, list):
        return []
    kept: list[Any] = []
    removed: list[str] = []
    for slide in slides:
        if isinstance(slide, dict) and _is_default_starter_slide(slide):
            slide_id = str(slide.get("slide_id") or _STARTER_SLIDE_ID).strip()
            if slide_id:
                removed.append(slide_id)
            continue
        kept.append(slide)
    if removed:
        outline["slides"] = kept
    return removed


def _upsert_slides(outline: dict[str, Any], slides: list[dict[str, Any]]) -> list[str]:
    existing = outline.get("slides")
    if not isinstance(existing, list):
        existing = []
        outline["slides"] = existing
    index_by_id = {
        _slide_key(slide, idx): idx - 1
        for idx, slide in enumerate(existing, start=1)
        if isinstance(slide, dict)
    }
    changed_refs: list[str] = []
    for slide in slides:
        slide_id = str(slide.get("slide_id") or "").strip()
        if not slide_id:
            continue
        previous_index = index_by_id.get(slide_id)
        if previous_index is None:
            existing.append(slide)
            index_by_id[slide_id] = len(existing) - 1
        else:
            previous = existing[previous_index]
            if isinstance(previous, dict):
                previous.update(slide)
            else:
                existing[previous_index] = slide
        changed_refs.append(slide_id)
    return changed_refs


def _upsert_evidence_items(evidence_plan: dict[str, Any], entries: list[dict[str, Any]]) -> list[str]:
    items = evidence_plan.get("items")
    if not isinstance(items, list):
        items = []
        evidence_plan["items"] = items
    index_by_id = {
        str(item.get("id") or "").strip(): idx
        for idx, item in enumerate(items)
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    changed_ids: list[str] = []
    changed_seen: set[str] = set()
    for entry in entries:
        evidence_id = str(entry.get("id") or "").strip()
        if not evidence_id:
            continue
        previous_index = index_by_id.get(evidence_id)
        if previous_index is None:
            items.append(entry)
            index_by_id[evidence_id] = len(items) - 1
        else:
            previous = items[previous_index]
            if not isinstance(previous, dict):
                items[previous_index] = entry
            else:
                previous["used_on_slides"] = _merge_unique(
                    previous.get("used_on_slides"),
                    [str(item) for item in entry.get("used_on_slides", [])],
                )
                for key, value in entry.items():
                    if key in {"id", "used_on_slides"}:
                        continue
                    if key == "visual_use":
                        previous[key] = _merge_visual_use(previous.get(key), value)
                        continue
                    if value or not previous.get(key):
                        previous[key] = value
        if evidence_id not in changed_seen:
            changed_seen.add(evidence_id)
            changed_ids.append(evidence_id)
    if items and not str(evidence_plan.get("source_policy") or "").strip():
        evidence_plan["source_policy"] = "Use compact source-line footers with short IDs; move full references to a final References slide."
    return changed_ids


def _upsert_content_plan_entries(content_plan: dict[str, Any], entries: list[dict[str, Any]]) -> list[str]:
    slide_plan = content_plan.get("slide_plan")
    if not isinstance(slide_plan, list):
        slide_plan = []
        content_plan["slide_plan"] = slide_plan
    index_by_id = {
        str(item.get("slide_id") or "").strip(): idx
        for idx, item in enumerate(slide_plan)
        if isinstance(item, dict) and str(item.get("slide_id") or "").strip()
    }
    changed_refs: list[str] = []
    for entry in entries:
        slide_id = str(entry.get("slide_id") or "").strip()
        if not slide_id:
            continue
        previous_index = index_by_id.get(slide_id)
        if previous_index is None:
            slide_plan.append(entry)
            index_by_id[slide_id] = len(slide_plan) - 1
        else:
            previous = slide_plan[previous_index]
            if isinstance(previous, dict):
                previous.update(entry)
            else:
                slide_plan[previous_index] = entry
        changed_refs.append(slide_id)
    return changed_refs


def _remove_content_plan_slide_refs(content_plan: dict[str, Any], slide_ids: list[str]) -> list[str]:
    if not slide_ids:
        return []
    remove_set = {str(item).strip() for item in slide_ids if str(item).strip()}
    if not remove_set:
        return []
    removed: list[str] = []
    removed_seen: set[str] = set()

    def mark_removed(slide_id: str) -> None:
        if slide_id and slide_id not in removed_seen:
            removed_seen.add(slide_id)
            removed.append(slide_id)

    slide_plan = content_plan.get("slide_plan")
    if isinstance(slide_plan, list):
        kept_slide_plan: list[Any] = []
        for entry in slide_plan:
            if isinstance(entry, dict):
                slide_id = str(entry.get("slide_id") or "").strip()
                if slide_id in remove_set:
                    mark_removed(slide_id)
                    continue
            kept_slide_plan.append(entry)
        if len(kept_slide_plan) != len(slide_plan):
            content_plan["slide_plan"] = kept_slide_plan

    narrative_arc = content_plan.get("narrative_arc")
    if isinstance(narrative_arc, list):
        for arc in narrative_arc:
            if not isinstance(arc, dict):
                continue
            arc_slides = arc.get("slides")
            if not isinstance(arc_slides, list):
                continue
            kept_arc_slides: list[Any] = []
            for raw_ref in arc_slides:
                slide_id = str(raw_ref or "").strip()
                if slide_id in remove_set:
                    mark_removed(slide_id)
                    continue
                kept_arc_slides.append(raw_ref)
            if len(kept_arc_slides) != len(arc_slides):
                arc["slides"] = kept_arc_slides
    return removed


def _figure_artifact(plan: dict[str, Any]) -> tuple[str, str]:
    artifacts = plan.get("artifact_bindings")
    if not isinstance(artifacts, list):
        return "", ""
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        role = str(artifact.get("role") or "").strip().lower()
        outline_field = str(artifact.get("outline_field") or "").strip()
        if "figure" in role or outline_field == "assets.hero_image":
            artifact_id = str(artifact.get("artifact_id") or "").strip()
            path = str(artifact.get("path") or "").strip().replace("\\", "/")
            return artifact_id, path
    return "", ""


def _apply_design_brief_updates(
    brief: dict[str, Any],
    selections: list[dict[str, Any]],
    *,
    alias_plan_by_id: dict[str, dict[str, Any]],
    required_by_slide: dict[str, list[str]],
) -> dict[str, Any]:
    plan = brief.get("analysis_artifact_plan")
    if not isinstance(plan, dict):
        plan = {}
    registry = plan.get("artifact_registry")
    if not isinstance(registry, list):
        registry = []
    registry_by_id = {
        str(item.get("id") or "").strip(): item
        for item in registry
        if isinstance(item, dict)
    }
    selected_artifact_ids = {
        artifact_id
        for artifact_ids in required_by_slide.values()
        for artifact_id in artifact_ids
        if artifact_id
    }
    for slide_id, artifact_ids in required_by_slide.items():
        for artifact_id in artifact_ids:
            entry = registry_by_id.get(artifact_id)
            if isinstance(entry, dict):
                entry["used_on_slides"] = _merge_unique(entry.get("used_on_slides"), [slide_id])
                entry["binding_status"] = "selected"
    for selection in selections:
        output_id = str(selection.get("output_id") or selection.get("id") or "").strip()
        selected_plan = alias_plan_by_id.get(output_id, {})
        artifacts = selected_plan.get("artifact_bindings") if isinstance(selected_plan, dict) else []
        if not isinstance(artifacts, list):
            continue
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            artifact_id = str(artifact.get("artifact_id") or "").strip()
            if not artifact_id or artifact_id in selected_artifact_ids:
                continue
            entry = registry_by_id.get(artifact_id)
            if not isinstance(entry, dict):
                continue
            entry["binding_status"] = "deferred_support"
            entry["binding_note"] = (
                "Generated support artifact retained for rebuilds or follow-up editable slides; "
                "not placed by the current manifest selection."
            )
    plan["artifact_registry"] = registry
    brief["analysis_artifact_plan"] = plan

    figure_contract = brief.get("figure_export_contract")
    if not isinstance(figure_contract, dict) or not isinstance(figure_contract.get("outputs"), list):
        return brief
    outputs = figure_contract.get("outputs") or []
    for selection in selections:
        output_id = str(selection.get("output_id") or selection.get("id") or "").strip()
        slide_id = str(selection.get("slide_id") or selection.get("target_slide") or "").strip()
        variant = str(selection.get("variant") or selection.get("slide_variant") or "").strip()
        selected_plan = alias_plan_by_id.get(output_id, {})
        figure_artifact_id, figure_path = _figure_artifact(selected_plan)
        if not figure_path or not slide_id:
            continue
        if figure_artifact_id and figure_artifact_id not in required_by_slide.get(slide_id, []):
            continue
        for output in outputs:
            if not isinstance(output, dict):
                continue
            output_path = str(output.get("path") or "").strip().replace("\\", "/")
            if output_path != figure_path:
                continue
            output["target_slide"] = slide_id
            if variant:
                output["target_variant"] = variant
    return brief


def _apply_asset_plan_updates(asset_plan: dict[str, Any], required_by_slide: dict[str, list[str]]) -> dict[str, Any]:
    artifact_to_name = {}
    for artifact_ids in required_by_slide.values():
        for artifact_id in artifact_ids:
            if artifact_id.endswith("_figure"):
                artifact_to_name[artifact_id] = artifact_id
            elif artifact_id.endswith("_chart_json"):
                artifact_to_name[artifact_id] = artifact_id[: -len("_chart_json")]
            elif artifact_id.endswith("_summary_table"):
                artifact_to_name[artifact_id] = f"{artifact_id[: -len('_summary_table')]}_summary"
    for section in ("images", "charts", "tables"):
        entries = asset_plan.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            slide_refs = [
                slide_id
                for slide_id, artifact_ids in required_by_slide.items()
                for artifact_id in artifact_ids
                if artifact_to_name.get(artifact_id) == name
            ]
            if slide_refs:
                entry["used_on_slides"] = _merge_unique(entry.get("used_on_slides"), slide_refs)
    return asset_plan


def apply_bindings(
    workspace: Path,
    *,
    manifest_path: Path,
    selections_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    report = inspect_manifest(workspace, manifest_path)
    selections = _load_selections(selections_path)
    return apply_selection_payload(
        workspace,
        manifest_path=manifest_path,
        report=report,
        selections=selections,
        selection_label=str(selections_path),
        dry_run=dry_run,
    )


def apply_selection_payload(
    workspace: Path,
    *,
    manifest_path: Path,
    report: dict[str, Any],
    selections: list[dict[str, Any]],
    selection_label: str,
    dry_run: bool = False,
    cleanup_default_starter: bool = False,
) -> dict[str, Any]:
    by_id = _alias_plan_by_id(report)

    slides: list[dict[str, Any]] = []
    content_plan_entries: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = []
    required_by_slide: dict[str, list[str]] = {}
    generated_by = str(report.get("generated_by") or "").strip()
    for selection in selections:
        output_id = str(selection.get("output_id") or selection.get("id") or "").strip()
        plan = by_id.get(output_id)
        if not isinstance(plan, dict):
            raise ValueError(f"selection references unknown manifest output {output_id!r}")
        slide, required_ids = _selection_slide(selection, plan)
        slides.append(slide)
        content_plan_entries.append(_selection_content_plan_entry(selection, slide, plan))
        evidence_entries.append(
            _selection_evidence_item(selection, slide, plan, generated_by=generated_by)
        )
        required_by_slide[str(slide["slide_id"])] = required_ids

    outline_path = workspace / "outline.json"
    outline = _read_json(outline_path, {})
    if not isinstance(outline, dict):
        outline = {}
    removed_starter_slide_refs = (
        _remove_default_starter_slides(outline)
        if cleanup_default_starter and selections
        else []
    )
    changed_slide_refs = _upsert_slides(outline, slides)

    brief_path = workspace / "design_brief.json"
    brief = _read_json(brief_path, {})
    if not isinstance(brief, dict):
        brief = {}
    brief = _apply_design_brief_updates(
        brief,
        selections,
        alias_plan_by_id=by_id,
        required_by_slide=required_by_slide,
    )

    asset_path = workspace / "asset_plan.json"
    asset_plan = _read_json(asset_path, {})
    if not isinstance(asset_plan, dict):
        asset_plan = {}
    asset_plan = _apply_asset_plan_updates(asset_plan, required_by_slide)

    content_path = workspace / "content_plan.json"
    content_plan = _read_json(content_path, {})
    if not isinstance(content_plan, dict):
        content_plan = {}
    removed_content_plan_refs = _remove_content_plan_slide_refs(
        content_plan,
        removed_starter_slide_refs,
    )
    changed_content_refs = _upsert_content_plan_entries(content_plan, content_plan_entries)

    evidence_path = workspace / "evidence_plan.json"
    evidence_plan = _read_json(evidence_path, {})
    if not isinstance(evidence_plan, dict):
        evidence_plan = {}
    changed_evidence_ids = _upsert_evidence_items(evidence_plan, evidence_entries)

    outline_changed = _write_json_if_changed(outline_path, outline, dry_run=dry_run)
    design_changed = _write_json_if_changed(brief_path, brief, dry_run=dry_run)
    asset_changed = _write_json_if_changed(asset_path, asset_plan, dry_run=dry_run)
    content_changed = _write_json_if_changed(content_path, content_plan, dry_run=dry_run)
    evidence_changed = _write_json_if_changed(evidence_path, evidence_plan, dry_run=dry_run)
    return {
        "workspace": str(workspace),
        "manifest": str(manifest_path),
        "selections": selection_label,
        "dry_run": dry_run,
        "applied": not dry_run,
        "selection_count": len(selections),
        "slide_refs": changed_slide_refs,
        "removed_starter_slide_refs": removed_starter_slide_refs,
        "removed_content_plan_refs": removed_content_plan_refs,
        "content_plan_slide_refs": changed_content_refs,
        "evidence_ids": changed_evidence_ids,
        "required_artifact_ids_by_slide": required_by_slide,
        "outline_changed": outline_changed,
        "content_plan_changed": content_changed,
        "evidence_plan_changed": evidence_changed,
        "design_brief_changed": design_changed,
        "asset_plan_changed": asset_changed,
        "next_commands": [
            f"python3 scripts/validate_planning.py --workspace {workspace}",
            f"python3 scripts/build_workspace.py --workspace {workspace} --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
        ],
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Deck workspace root.")
    parser.add_argument(
        "--manifest",
        default="assets/artifacts_manifest.json",
        help="Artifact manifest path, relative to the workspace by default.",
    )
    parser.add_argument("--selection", help="JSON selection file.")
    parser.add_argument(
        "--auto-select",
        action="store_true",
        help="Generate deterministic selections from every manifest output and apply them.",
    )
    parser.add_argument(
        "--selection-out",
        help="Optional path to write generated auto selections before applying them.",
    )
    parser.add_argument(
        "--variants",
        default="image-sidebar,chart,lab-run-results",
        help="Comma-separated variant preference list for --auto-select.",
    )
    parser.add_argument(
        "--auto-select-mode",
        choices=("all", "recommended", "lead"),
        default="all",
        help=(
            "Variant selection mode for --auto-select: all preserves the requested "
            "variant list, recommended orders by manifest layout guidance, and lead "
            "selects only the best lead variant per output."
        ),
    )
    parser.add_argument(
        "--output-id",
        action="append",
        default=[],
        help="Limit --auto-select to one manifest output ID. May be repeated.",
    )
    parser.add_argument("--report", help="Optional JSON report path.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace).expanduser().resolve()
    manifest_path = _workspace_path(workspace, args.manifest)
    if not workspace.exists():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 1
    if not manifest_path.exists():
        print(f"Error: artifact manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    if bool(args.selection) == bool(args.auto_select):
        print("Error: provide exactly one of --selection or --auto-select", file=sys.stderr)
        return 1
    try:
        if args.auto_select:
            manifest_report = inspect_manifest(workspace, manifest_path)
            variants = _parse_csv_tokens(
                str(args.variants or ""),
                default=["image-sidebar", "chart", "lab-run-results"],
            )
            selections = generate_auto_selections(
                manifest_report,
                output_ids=[str(item).strip() for item in args.output_id if str(item).strip()],
                variants=variants,
                mode=args.auto_select_mode,
            )
            if not selections:
                raise ValueError("auto-select did not find any matching manifest outputs and variants")
            selection_label = "auto-select"
            selection_out_changed = False
            if args.selection_out:
                selection_out = Path(args.selection_out).expanduser().resolve()
                selection_out_changed = _write_json_if_changed(
                    selection_out,
                    {"bindings": selections},
                    dry_run=args.dry_run,
                )
                selection_label = str(selection_out)
            report = apply_selection_payload(
                workspace,
                manifest_path=manifest_path,
                report=manifest_report,
                selections=selections,
                selection_label=selection_label,
                dry_run=args.dry_run,
                cleanup_default_starter=True,
            )
            report["auto_selected"] = True
            report["auto_select_mode"] = args.auto_select_mode
            report["selection_out"] = selection_label if args.selection_out else ""
            report["selection_out_changed"] = selection_out_changed
        else:
            selection_path = Path(args.selection).expanduser().resolve()
            if not selection_path.exists():
                print(f"Error: selection file not found: {selection_path}", file=sys.stderr)
                return 1
            report = apply_bindings(
                workspace,
                manifest_path=manifest_path,
                selections_path=selection_path,
                dry_run=args.dry_run,
            )
            report["auto_selected"] = False
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error: cannot apply artifact manifest bindings: {exc}", file=sys.stderr)
        return 1
    if args.report:
        _write_json_if_changed(Path(args.report).expanduser().resolve(), report, dry_run=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
