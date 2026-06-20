#!/usr/bin/env python3
"""Compact over-budget source-line footers into short IDs plus References table slides."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

GENERATED_BY = "scripts/compact_source_footers.py"
NOTE = "Full references moved here from source-line footers by compact_source_footers.py."


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


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


def _workspace_path(workspace: Path | None, raw: str) -> Path:
    path = Path(str(raw or "")).expanduser()
    if path.is_absolute():
        return path.resolve()
    if workspace is not None:
        return (workspace / path).resolve()
    return path.resolve()


def _display_path(base: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def _text_item(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("text", "citation", "source", "title", "label", "name"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
    return ""


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _text_item(item))]
    text = _text_item(value)
    return [text] if text else []


def _slide_ref(slide: dict[str, Any], index: int) -> str:
    for key in ("slide_id", "id", "slug"):
        text = str(slide.get(key) or "").strip()
        if text:
            return text
    title = str(slide.get("title") or "").strip()
    return title or f"s{index + 1}"


def _source_line_enabled(slide: dict[str, Any], deck_style: dict[str, Any]) -> bool:
    slide_mode = str(slide.get("footer_mode") or "").strip().lower()
    deck_mode = str(deck_style.get("footer_mode") or "").strip().lower()
    return (slide_mode or deck_mode) == "source-line"


def _footer_budget(
    slide: dict[str, Any],
    deck_style: dict[str, Any],
    *,
    max_combined_chars: int,
    max_item_chars: int,
    max_items: int,
) -> dict[str, Any]:
    footer = str(slide.get("footer") or "").strip()
    source_label = str(slide.get("source_label") or deck_style.get("footer_source_label") or "Sources").strip()
    refs_label = str(slide.get("refs_label") or deck_style.get("footer_refs_label") or "Refs").strip()
    sources = _text_list(slide.get("sources"))
    refs = _text_list(slide.get("refs")) or _text_list(slide.get("references"))
    parts: list[str] = []
    if footer:
        parts.append(footer)
    if sources:
        parts.append(f"{source_label}: " + "; ".join(sources))
    if refs:
        parts.append(f"{refs_label}: " + "; ".join(refs))
    combined = " · ".join(parts)
    provenance = [*sources, *refs]
    reasons: list[str] = []
    if len(combined) > max_combined_chars:
        reasons.append(f"combined_chars>{max_combined_chars}")
    longest = max((len(item) for item in provenance), default=0)
    if longest > max_item_chars:
        reasons.append(f"item_chars>{max_item_chars}")
    if len(provenance) > max_items:
        reasons.append(f"item_count>{max_items}")
    return {
        "needs_compaction": bool(reasons),
        "combined_chars": len(combined),
        "longest_item_chars": longest,
        "item_count": len(provenance),
        "reasons": reasons,
        "sources": sources,
        "refs": refs,
    }


def _next_id(prefix: str, counters: dict[str, int]) -> str:
    counters[prefix] = counters.get(prefix, 0) + 1
    return f"{prefix}{counters[prefix]}"


def _compact_id_list(ids: list[str]) -> list[str]:
    if len(ids) <= 1:
        return ids
    return [f"{ids[0]}-{ids[-1]}"]


def _generated_reference_slide(slide: Any) -> bool:
    if not isinstance(slide, dict):
        return False
    metadata = slide.get("source_footer_compaction")
    return isinstance(metadata, dict) and metadata.get("generated_by") == GENERATED_BY


def _generated_reference_summary(slides: list[Any], indexes: list[int]) -> dict[str, Any]:
    ids: list[str] = []
    entry_count = 0
    total_entry_count = 0
    for idx in indexes:
        slide = slides[idx] if 0 <= idx < len(slides) else None
        if not isinstance(slide, dict):
            continue
        ids.append(_slide_ref(slide, idx))
        rows = slide.get("rows")
        if isinstance(rows, list):
            entry_count += len(rows)
        metadata = slide.get("source_footer_compaction")
        if isinstance(metadata, dict):
            try:
                total_entry_count = max(total_entry_count, int(metadata.get("total_entry_count") or 0))
            except (TypeError, ValueError):
                pass
    return {
        "existing_references_slide": ids[0] if ids else "",
        "existing_references_slides": ids,
        "existing_reference_slide_count": len(ids),
        "existing_reference_entry_count": entry_count,
        "existing_reference_total_entry_count": total_entry_count or entry_count,
    }


def _unique_slide_id(slides: list[Any], preferred: str) -> str:
    used = {
        str(slide.get(key) or "").strip()
        for slide in slides
        if isinstance(slide, dict)
        for key in ("slide_id", "id", "slug")
        if str(slide.get(key) or "").strip()
    }
    if preferred not in used:
        return preferred
    index = 2
    while f"{preferred}-{index}" in used:
        index += 1
    return f"{preferred}-{index}"


def _unique_slide_ids(slides: list[Any], preferred: str, count: int) -> list[str]:
    used = {
        str(slide.get(key) or "").strip()
        for slide in slides
        if isinstance(slide, dict)
        for key in ("slide_id", "id", "slug")
        if str(slide.get(key) or "").strip()
    }
    ids: list[str] = []
    base = preferred or "references"
    for idx in range(max(1, count)):
        candidate_base = base if idx == 0 else f"{base}-{idx + 1}"
        candidate = candidate_base
        suffix = 2
        while candidate in used:
            candidate = f"{candidate_base}-{suffix}"
            suffix += 1
        used.add(candidate)
        ids.append(candidate)
    return ids


def _chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    chunk_size = max(1, int(size or 1))
    return [values[idx : idx + chunk_size] for idx in range(0, len(values), chunk_size)]


def _reference_table_slide(
    entries: list[dict[str, Any]],
    *,
    slide_id: str,
    references_title: str,
    reference_slide_index: int,
    reference_slide_count: int,
    compacted_slide_count: int,
    total_entry_count: int,
) -> dict[str, Any]:
    title = references_title
    if reference_slide_count > 1:
        title = f"{references_title} ({reference_slide_index}/{reference_slide_count})"
    return {
        "type": "content",
        "variant": "table",
        "slide_id": slide_id,
        "title": title,
        "subtitle": "Full citations for compact source-line footer IDs.",
        "headers": ["ID", "Slide", "Type", "Citation"],
        "rows": [
            [
                item["id"],
                item["slide"],
                "Source" if item["kind"] == "source" else "Ref",
                item["text"],
            ]
            for item in entries
        ],
        "column_weights": [0.10, 0.14, 0.10, 0.66],
        "table_style": "references",
        "caption": "Use compact IDs in slide footers; keep full citation text editable here.",
        "footer_mode": "source-line",
        "footer": "Full references for compact slide footers",
        "sources": ["outline.json"],
        "notes": NOTE,
        "source_footer_compaction": {
            "generated_by": GENERATED_BY,
            "entry_count": len(entries),
            "total_entry_count": total_entry_count,
            "slide_count": compacted_slide_count,
            "reference_slide_index": reference_slide_index,
            "reference_slide_count": reference_slide_count,
            "table_style": "references",
        },
    }


def compact_outline(
    outline: dict[str, Any],
    *,
    max_combined_chars: int,
    max_item_chars: int,
    max_items: int,
    max_reference_rows: int,
    references_slide_id: str,
    references_title: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    slides = outline.get("slides")
    if not isinstance(slides, list):
        return outline, {
            "changed": False,
            "error": "outline.slides is missing or not a list",
            "compacted_slides": [],
            "reference_entries": [],
        }

    deck_style = outline.get("deck_style") if isinstance(outline.get("deck_style"), dict) else {}
    new_slides = [dict(slide) if isinstance(slide, dict) else slide for slide in slides]
    generated_indexes = [idx for idx, slide in enumerate(new_slides) if _generated_reference_slide(slide)]
    existing_reference_summary = _generated_reference_summary(new_slides, generated_indexes)
    reference_entries: list[dict[str, Any]] = []
    compacted_slides: list[dict[str, Any]] = []
    id_by_kind_text: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {"S": 0, "R": 0}

    def ref_id(kind: str, text: str) -> str:
        key = (kind, text)
        if key not in id_by_kind_text:
            prefix = "S" if kind == "source" else "R"
            id_by_kind_text[key] = _next_id(prefix, counters)
        return id_by_kind_text[key]

    for idx, slide in enumerate(new_slides):
        if not isinstance(slide, dict) or _generated_reference_slide(slide):
            continue
        if not _source_line_enabled(slide, deck_style):
            continue
        budget = _footer_budget(
            slide,
            deck_style,
            max_combined_chars=max_combined_chars,
            max_item_chars=max_item_chars,
            max_items=max_items,
        )
        if not budget.get("needs_compaction"):
            continue
        slide_ref = _slide_ref(slide, idx)
        source_ids: list[str] = []
        ref_ids: list[str] = []
        for text in budget.get("sources", []):
            source_id = ref_id("source", text)
            source_ids.append(source_id)
            if not any(item.get("id") == source_id for item in reference_entries):
                reference_entries.append({"id": source_id, "slide": slide_ref, "kind": "source", "text": text})
        for text in budget.get("refs", []):
            reference_id = ref_id("ref", text)
            ref_ids.append(reference_id)
            if not any(item.get("id") == reference_id for item in reference_entries):
                reference_entries.append({"id": reference_id, "slide": slide_ref, "kind": "ref", "text": text})
        footer_source_ids = source_ids
        footer_ref_ids = ref_ids
        if len(source_ids) + len(ref_ids) > max_items:
            footer_source_ids = _compact_id_list(source_ids)
            footer_ref_ids = _compact_id_list(ref_ids)
        if footer_source_ids:
            slide["sources"] = footer_source_ids
        else:
            slide.pop("sources", None)
        if footer_ref_ids:
            slide["refs"] = footer_ref_ids
        else:
            slide.pop("refs", None)
        slide.pop("references", None)
        compacted_slides.append(
            {
                "slide_index": idx,
                "slide_id": slide_ref,
                "source_ids": source_ids,
                "ref_ids": ref_ids,
                "footer_sources": footer_source_ids,
                "footer_refs": footer_ref_ids,
                "reasons": budget.get("reasons", []),
                "combined_chars_before": budget.get("combined_chars", 0),
                "item_count_before": budget.get("item_count", 0),
            }
        )

    if not reference_entries:
        return outline, {
            "changed": False,
            "compacted_slides": compacted_slides,
            "reference_entries": reference_entries,
            "references_slide": existing_reference_summary["existing_references_slide"],
            "references_slides": existing_reference_summary["existing_references_slides"],
            **existing_reference_summary,
        }

    insert_idx = generated_indexes[0] if generated_indexes else len(new_slides)
    preferred_reference_id = references_slide_id
    if generated_indexes and isinstance(new_slides[generated_indexes[0]], dict):
        preferred_reference_id = str(new_slides[generated_indexes[0]].get("slide_id") or references_slide_id)
    generated_index_set = set(generated_indexes)
    body_slides = [slide for idx, slide in enumerate(new_slides) if idx not in generated_index_set]
    insert_idx = min(insert_idx, len(body_slides))
    entry_chunks = _chunks(reference_entries, max_reference_rows)
    reference_ids = _unique_slide_ids(body_slides, preferred_reference_id, len(entry_chunks))
    reference_slides = [
        _reference_table_slide(
            entries,
            slide_id=reference_ids[idx],
            references_title=references_title,
            reference_slide_index=idx + 1,
            reference_slide_count=len(entry_chunks),
            compacted_slide_count=len(compacted_slides),
            total_entry_count=len(reference_entries),
        )
        for idx, entries in enumerate(entry_chunks)
    ]
    new_slides = [*body_slides[:insert_idx], *reference_slides, *body_slides[insert_idx:]]

    new_outline = dict(outline)
    new_outline["slides"] = new_slides
    return new_outline, {
        "changed": new_outline != outline,
        "compacted_slides": compacted_slides,
        "reference_entries": reference_entries,
        "references_slide": reference_ids[0] if reference_ids else "",
        "references_slides": reference_ids,
        **existing_reference_summary,
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Move verbose source-line footer provenance to a final References table slide."
    )
    parser.add_argument("--workspace", help="Deck workspace containing workspace.json and outline.json.")
    parser.add_argument("--outline", help="Outline JSON path. Overrides workspace manifest when provided.")
    parser.add_argument("--report", help="Output report path. Defaults under the workspace/build or outline directory.")
    parser.add_argument("--max-combined-chars", type=int, default=170)
    parser.add_argument("--max-item-chars", type=int, default=95)
    parser.add_argument("--max-items", type=int, default=4)
    parser.add_argument("--max-reference-rows", type=int, default=8)
    parser.add_argument("--references-slide-id", default="references")
    parser.add_argument("--references-title", default="References")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing outline.json.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None
    if workspace is not None and not workspace.exists():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 2
    if args.outline:
        outline_path = _workspace_path(workspace, args.outline)
    elif workspace is not None:
        manifest = _load_json(workspace / "workspace.json", {})
        if not isinstance(manifest, dict):
            manifest = {}
        outline_path = workspace / str(manifest.get("outline", "outline.json"))
    else:
        print("Error: provide --workspace or --outline", file=sys.stderr)
        return 2
    if not outline_path.exists():
        print(f"Error: outline not found: {outline_path}", file=sys.stderr)
        return 2

    base = workspace or outline_path.parent
    report_path = (
        _workspace_path(workspace, args.report)
        if args.report
        else ((workspace / "build" / "source_footer_compaction.json") if workspace else outline_path.with_name("source_footer_compaction.json"))
    )
    outline = _load_json(outline_path, {})
    if not isinstance(outline, dict):
        print(f"Error: outline root is not a JSON object: {outline_path}", file=sys.stderr)
        return 2

    new_outline, summary = compact_outline(
        outline,
        max_combined_chars=max(1, int(args.max_combined_chars or 170)),
        max_item_chars=max(1, int(args.max_item_chars or 95)),
        max_items=max(1, int(args.max_items or 4)),
        max_reference_rows=max(1, int(args.max_reference_rows or 8)),
        references_slide_id=str(args.references_slide_id or "references"),
        references_title=str(args.references_title or "References"),
    )
    outline_changed = bool(summary.get("changed")) and not args.dry_run
    if outline_changed:
        _write_json_if_changed(outline_path, new_outline)

    report = {
        "workflow": "source_footer_compaction_v1",
        "outline": _display_path(base, outline_path),
        "changed": outline_changed,
        "dry_run": bool(args.dry_run),
        "thresholds": {
            "max_combined_chars": max(1, int(args.max_combined_chars or 170)),
            "max_item_chars": max(1, int(args.max_item_chars or 95)),
            "max_items": max(1, int(args.max_items or 4)),
            "max_reference_rows": max(1, int(args.max_reference_rows or 8)),
        },
        **summary,
    }
    if not args.dry_run:
        _write_json_if_changed(report_path, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
