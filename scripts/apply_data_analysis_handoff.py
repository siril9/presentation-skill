#!/usr/bin/env python3
"""Apply a data/evidence scout JSON handoff to deck workspace sources.

`emit_data_analysis_prompt.py` asks a read-only scout to return structured
JSON. This helper applies the deterministic parts of that handoff:

- write `artifact_selection_recommendations.bindings` to a selection JSON file;
- apply those selections through `apply_artifact_manifest_bindings.py`;
- merge `evidence_plan_updates` into `evidence_plan.json`;
- merge structured `figure_export_contract`, `asset_plan_updates`, and
  `artifact_registry_updates` into planning sources;
- persist the scout's analysis tasks, computed findings, visual
  recommendations, outline-binding plan, quality flags, and open questions;
- persist any `artifact_rebuild_context` into `design_brief.json`;
- record script-edit and QA handoff notes idempotently in `notes.md`.

The helper does not edit analysis scripts from prose. The main agent still
owns scientific/statistical decisions and script edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from apply_artifact_manifest_bindings import apply_selection_payload  # noqa: E402
from inspect_artifact_manifest import inspect_manifest  # noqa: E402


NOTE_START = "<!-- data-analysis-handoff:start -->"
NOTE_END = "<!-- data-analysis-handoff:end -->"
SCOUT_ANALYSIS_SCHEMA = "data_analysis_scout_ledger_v1"
ARTIFACT_STORYBOARD_SCHEMA = "data_artifact_storyboard_v1"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _write_json_if_changed(path: Path, payload: Any, *, dry_run: bool) -> bool:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return True


def _write_text_if_changed(path: Path, text: str, *, dry_run: bool) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "sha256": _file_sha256(path),
    }


def _workspace_path(workspace: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _merge_unique(existing: Any, additions: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    source = existing if isinstance(existing, list) else []
    for item in [*source, *additions]:
        if item is None:
            continue
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, dict) else str(item)
        if not key.strip() or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _identity_key(item: Any) -> str:
    if isinstance(item, dict):
        for key in ("id", "name", "alias", "path", "title"):
            value = _text(item.get(key))
            if value:
                return f"{key}:{value.lower().replace(chr(92), '/')}"
        return json.dumps(item, sort_keys=True, ensure_ascii=False)
    return str(item)


def _merge_named_entries(existing: Any, additions: list[dict[str, Any]]) -> list[Any]:
    merged = list(existing) if isinstance(existing, list) else []
    positions: dict[str, int] = {}
    for index, item in enumerate(merged):
        key = _identity_key(item)
        if key:
            positions[key] = index
    for addition in additions:
        key = _identity_key(addition)
        if not key:
            continue
        if key in positions and isinstance(merged[positions[key]], dict):
            previous = merged[positions[key]]
            merged_item = dict(previous)
            previous_slides = previous.get("used_on_slides")
            incoming_slides = addition.get("used_on_slides")
            merged_item.update({field: value for field, value in addition.items() if value not in (None, "", [], {})})
            if previous_slides is not None or incoming_slides is not None:
                merged_item["used_on_slides"] = _merge_unique(
                    previous_slides if isinstance(previous_slides, list) else [],
                    incoming_slides if isinstance(incoming_slides, list) else [],
                )
            merged[positions[key]] = merged_item
            for updated_key in (_identity_key(merged_item),):
                if updated_key:
                    positions[updated_key] = positions[key]
            continue
        positions[key] = len(merged)
        merged.append(addition)
    return merged


def _artifact_registry_keys(item: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    artifact_id = _text(item.get("id"))
    if artifact_id:
        keys.append(f"id:{artifact_id}")
    artifact_path = _text(item.get("path")).replace("\\", "/")
    if artifact_path:
        keys.append(f"path:{artifact_path}")
    return keys


def _merge_artifact_registry_entry(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    merged = dict(previous)
    previous_slides = previous.get("used_on_slides")
    current_slides = current.get("used_on_slides")
    merged.update({field: value for field, value in current.items() if value not in (None, "", [], {})})
    if previous_slides is not None or current_slides is not None:
        merged["used_on_slides"] = _merge_unique(
            previous_slides if isinstance(previous_slides, list) else [],
            current_slides if isinstance(current_slides, list) else [],
        )
    return merged


def _merge_artifact_registry(existing: Any, additions: list[dict[str, Any]]) -> list[Any]:
    merged = list(existing) if isinstance(existing, list) else []
    positions: dict[str, int] = {}
    for index, item in enumerate(merged):
        if not isinstance(item, dict):
            continue
        for key in _artifact_registry_keys(item):
            positions[key] = index
    for addition in additions:
        keys = _artifact_registry_keys(addition)
        if not keys:
            merged.append(addition)
            continue
        position = next((positions[key] for key in keys if key in positions), None)
        if position is None:
            position = len(merged)
            merged.append(addition)
        elif isinstance(merged[position], dict):
            merged[position] = _merge_artifact_registry_entry(merged[position], addition)
        else:
            merged[position] = addition
        if isinstance(merged[position], dict):
            for key in _artifact_registry_keys(merged[position]):
                positions[key] = position
    return merged


_VISUAL_USE_ORDER = ("bullet", "kpi", "figure", "chart", "table", "footer-source")


def _visual_use_tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_tokens = [str(item) for item in value]
    else:
        raw_tokens = str(value or "").replace(",", "|").split("|")
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in raw_tokens:
        token = raw.strip().lower()
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _merge_visual_use(existing: Any, incoming: Any) -> str:
    tokens = _visual_use_tokens(existing) + _visual_use_tokens(incoming)
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    ranked = [token for token in _VISUAL_USE_ORDER if token in seen]
    ranked.extend(token for token in ordered if token not in _VISUAL_USE_ORDER)
    return " | ".join(ranked)


def _selection_block(handoff: dict[str, Any]) -> dict[str, Any]:
    block = handoff.get("artifact_selection_recommendations")
    return block if isinstance(block, dict) else {}


def _selection_file_from_handoff(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    override: str | None,
) -> Path:
    if override:
        return _workspace_path(workspace, override)
    raw = _text(_selection_block(handoff).get("selection_file")) or "artifact_selections.scout.json"
    return _workspace_path(workspace, raw)


def _selection_bindings(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = _selection_block(handoff).get("bindings")
    if bindings is None:
        bindings = handoff.get("bindings")
    if bindings is None:
        return []
    if not isinstance(bindings, list):
        raise ValueError("artifact_selection_recommendations.bindings must be a list")
    valid = [item for item in bindings if isinstance(item, dict)]
    if len(valid) != len(bindings):
        raise ValueError("artifact selection bindings must all be objects")
    return valid


def _artifact_rebuild_context(handoff: dict[str, Any]) -> dict[str, Any]:
    context = handoff.get("artifact_rebuild_context")
    if isinstance(context, dict):
        return context
    main = _as_dict(handoff.get("main_agent_handoff"))
    context = main.get("artifact_rebuild_context")
    return context if isinstance(context, dict) else {}


def _validate_handoff(handoff: Any) -> dict[str, Any]:
    if not isinstance(handoff, dict):
        raise ValueError("handoff JSON root must be an object")
    context = handoff.get("artifact_rebuild_context")
    if context not in (None, "", [], {}) and not isinstance(context, dict):
        raise ValueError("artifact_rebuild_context must be an object when present")
    main = _as_dict(handoff.get("main_agent_handoff"))
    main_context = main.get("artifact_rebuild_context")
    if main_context not in (None, "", [], {}) and not isinstance(main_context, dict):
        raise ValueError("main_agent_handoff.artifact_rebuild_context must be an object when present")
    if "figure_export_contract" in handoff and handoff.get("figure_export_contract") not in (None, "", [], {}) and not isinstance(handoff.get("figure_export_contract"), dict):
        raise ValueError("figure_export_contract must be an object when present")
    for key in ("asset_plan_updates", "artifact_registry_updates"):
        value = handoff.get(key)
        if value in (None, "", [], {}):
            continue
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError(f"{key} must be a list of objects when present")
    for key in (
        "analysis_tasks",
        "computed_findings",
        "chart_or_table_recommendations",
        "outline_binding_plan",
        "slide_artifact_storyboard",
    ):
        value = handoff.get(key)
        if value in (None, "", [], {}):
            continue
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise ValueError(f"{key} must be a list of objects when present")
    for key in ("quality_flags", "open_questions"):
        value = handoff.get(key)
        if value in (None, "", [], {}):
            continue
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list when present")
    workflow = handoff.get("recommended_workflow")
    if workflow not in (None, "", [], {}) and not isinstance(workflow, dict):
        raise ValueError("recommended_workflow must be an object when present")
    return handoff


def _evidence_updates(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    updates = handoff.get("evidence_plan_updates")
    if not isinstance(updates, list):
        return []
    valid = [item for item in updates if isinstance(item, dict)]
    if len(valid) != len(updates):
        raise ValueError("evidence_plan_updates must contain only objects")
    return valid


def _data_inventory_items(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    items = handoff.get("data_inventory")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _data_source_path(item: dict[str, Any]) -> str:
    return (
        _text(item.get("workspace_relative_path"))
        or _text(item.get("relative_path"))
        or _text(item.get("source_path"))
        or _text(item.get("path"))
    )


def _data_source_fingerprint_entry(item: dict[str, Any]) -> dict[str, Any]:
    path = _data_source_path(item)
    entry: dict[str, Any] = {"path": path}
    for source_key, target_key in (
        ("workspace_relative_path", "workspace_relative_path"),
        ("path", "absolute_path"),
        ("status", "status"),
        ("data_type", "data_type"),
        ("source_sha256", "source_sha256"),
        ("source_size_bytes", "source_size_bytes"),
        ("hash_status", "hash_status"),
    ):
        value = item.get(source_key)
        if value not in (None, "", [], {}):
            entry[target_key] = value
    preview = item.get("preview")
    if isinstance(preview, dict):
        preview_summary = {
            key: preview.get(key)
            for key in (
                "columns",
                "column_count",
                "top_level_keys",
                "top_level_key_count",
                "sample_keys",
                "sample_record_count",
                "preview_status",
                "preview_error",
            )
            if preview.get(key) not in (None, "", [], {})
        }
        if preview_summary:
            entry["preview_summary"] = preview_summary
    return {key: value for key, value in entry.items() if value not in (None, "", [], {})}


def _merge_fingerprint_entries(existing: Any, additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    for item in existing if isinstance(existing, list) else []:
        if not isinstance(item, dict):
            continue
        key = _data_source_path(item)
        if not key:
            continue
        positions[key] = len(merged)
        merged.append(dict(item))
    for item in additions:
        key = _data_source_path(item)
        if not key:
            continue
        if key in positions:
            current = merged[positions[key]]
            current.update({field: value for field, value in item.items() if value not in (None, "", [], {})})
        else:
            positions[key] = len(merged)
            merged.append(item)
    return merged


def _apply_data_inventory(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[list[dict[str, Any]], bool]:
    inventory = [_data_source_fingerprint_entry(item) for item in _data_inventory_items(handoff)]
    inventory = [item for item in inventory if _data_source_path(item)]
    if not inventory:
        return [], False
    path = workspace / "design_brief.json"
    brief = _load_json(path, {})
    if not isinstance(brief, dict):
        brief = {}
    plan = brief.get("analysis_artifact_plan")
    if not isinstance(plan, dict):
        plan = {}
        brief["analysis_artifact_plan"] = plan
    source_paths = [_data_source_path(item) for item in inventory if _data_source_path(item)]
    plan["candidate_data_files"] = _merge_unique(plan.get("candidate_data_files"), source_paths)
    plan["data_source_fingerprints"] = _merge_fingerprint_entries(
        plan.get("data_source_fingerprints"),
        inventory,
    )
    changed = _write_json_if_changed(path, brief, dry_run=dry_run)
    return inventory, changed


def _upsert_evidence_items(
    evidence_plan: dict[str, Any],
    updates: list[dict[str, Any]],
    *,
    overwrite: bool,
) -> list[str]:
    items = evidence_plan.get("items")
    if not isinstance(items, list):
        items = []
        evidence_plan["items"] = items
    by_id = {
        _text(item.get("id")): item
        for item in items
        if isinstance(item, dict) and _text(item.get("id"))
    }
    changed_ids: list[str] = []
    for update in updates:
        evidence_id = _text(update.get("id"))
        if not evidence_id:
            continue
        clean = {key: value for key, value in update.items() if value not in (None, "", [], {})}
        clean["id"] = evidence_id
        previous = by_id.get(evidence_id)
        if previous is None:
            items.append(clean)
            by_id[evidence_id] = clean
            changed_ids.append(evidence_id)
            continue
        for key, value in clean.items():
            if key == "id":
                continue
            if key == "used_on_slides":
                previous[key] = _merge_unique(previous.get(key), _as_list(value))
                continue
            if key == "visual_use":
                previous[key] = _merge_visual_use(previous.get(key), value)
                continue
            if overwrite or not previous.get(key):
                previous[key] = value
        changed_ids.append(evidence_id)
    if changed_ids and not _text(evidence_plan.get("source_policy")):
        evidence_plan["source_policy"] = (
            "Use compact source-line footers with short IDs; move full "
            "references to a final References slide."
        )
    return changed_ids


def _apply_evidence_updates(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    overwrite: bool,
    dry_run: bool,
) -> tuple[list[str], bool]:
    updates = _evidence_updates(handoff)
    if not updates:
        return [], False
    path = workspace / "evidence_plan.json"
    plan = _load_json(path, {})
    if not isinstance(plan, dict):
        plan = {}
    changed_ids = _upsert_evidence_items(plan, updates, overwrite=overwrite)
    changed = _write_json_if_changed(path, plan, dry_run=dry_run)
    return changed_ids, changed


def _figure_export_contract(handoff: dict[str, Any]) -> dict[str, Any]:
    contract = handoff.get("figure_export_contract")
    return contract if isinstance(contract, dict) else {}


def _merge_figure_outputs(existing: Any, incoming: Any) -> list[Any]:
    additions = [item for item in incoming if isinstance(item, dict)] if isinstance(incoming, list) else []
    merged = list(existing) if isinstance(existing, list) else []
    positions: dict[str, int] = {}
    for index, item in enumerate(merged):
        if not isinstance(item, dict):
            continue
        key = _text(item.get("path")).replace("\\", "/")
        if key:
            positions[key] = index
    for item in additions:
        key = _text(item.get("path")).replace("\\", "/")
        if key and key in positions and isinstance(merged[positions[key]], dict):
            previous = merged[positions[key]]
            merged_item = dict(previous)
            previous_slides = previous.get("used_on_slides")
            incoming_slides = item.get("used_on_slides")
            merged_item.update({field: value for field, value in item.items() if value not in (None, "", [], {})})
            if previous_slides is not None or incoming_slides is not None:
                merged_item["used_on_slides"] = _merge_unique(
                    previous_slides if isinstance(previous_slides, list) else [],
                    incoming_slides if isinstance(incoming_slides, list) else [],
                )
            merged[positions[key]] = merged_item
            continue
        if key:
            positions[key] = len(merged)
        merged.append(item)
    return merged


def _asset_plan_updates(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    updates = handoff.get("asset_plan_updates")
    return [item for item in updates if isinstance(item, dict)] if isinstance(updates, list) else []


def _artifact_registry_updates(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    updates = handoff.get("artifact_registry_updates")
    return [item for item in updates if isinstance(item, dict)] if isinstance(updates, list) else []


def _path_stem(raw: str) -> str:
    text = _text(raw).replace("\\", "/")
    if not text:
        return ""
    return Path(text).stem


def _asset_section_for_output(update: dict[str, Any], output_path: str) -> str:
    kind = _text(update.get("type")).lower()
    path = output_path.lower().replace("\\", "/")
    if "chart" in kind or "/charts/" in path:
        return "charts"
    if "table" in kind or "/tables/" in path or path.endswith("_summary.json"):
        return "tables"
    return "images"


def _asset_entry(update: dict[str, Any], output_path: str, section: str) -> dict[str, Any]:
    update_id = _text(update.get("id")) or _path_stem(output_path)
    name = update_id
    if len(_as_list(update.get("outputs"))) > 1 and section == "tables" and not name.endswith("_summary"):
        name = f"{name}_summary"
    entry = {
        "name": name,
        "path": output_path,
        "title": _text(update.get("title")) or _text(update.get("caption")) or update_id,
        "caption": _text(update.get("caption")),
        "source_note": _text(update.get("source_note")) or _text(update.get("caption")),
        "provenance": _text(update.get("provenance")) or "data-analysis scout handoff",
        "used_on_slides": _as_list(update.get("used_on_slides")),
        "analysis_metadata": update.get("analysis_metadata") if isinstance(update.get("analysis_metadata"), dict) else {},
    }
    for source_key in (
        "artifact_manifest",
        "analysis_summary",
        "analysis_summary_markdown",
        "script_needed",
    ):
        value = update.get(source_key)
        if value not in (None, "", [], {}):
            entry[source_key] = value
    return {key: value for key, value in entry.items() if value not in (None, "", [], {})}


def _apply_asset_plan_updates(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[dict[str, int], bool]:
    updates = _asset_plan_updates(handoff)
    if not updates:
        return {}, False
    additions: dict[str, list[dict[str, Any]]] = {"images": [], "charts": [], "tables": []}
    for update in updates:
        outputs = _as_list(update.get("outputs"))
        if not outputs and _text(update.get("path")):
            outputs = [_text(update.get("path"))]
        for raw_output in outputs:
            output_path = _text(raw_output)
            if not output_path:
                continue
            section = _asset_section_for_output(update, output_path)
            additions[section].append(_asset_entry(update, output_path, section))
    counts = {section: len(items) for section, items in additions.items() if items}
    if not counts:
        return {}, False
    path = workspace / "asset_plan.json"
    plan = _load_json(path, {})
    if not isinstance(plan, dict):
        plan = {}
    for section, items in additions.items():
        if not items:
            continue
        plan[section] = _merge_named_entries(plan.get(section), items)
    changed = _write_json_if_changed(path, plan, dry_run=dry_run)
    return counts, changed


def _apply_artifact_contracts(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    dry_run: bool,
) -> tuple[dict[str, Any], bool]:
    figure_contract = _figure_export_contract(handoff)
    registry_updates = _artifact_registry_updates(handoff)
    if not figure_contract and not registry_updates:
        return {
            "figure_export_contract_applied": False,
            "artifact_registry_update_count": 0,
            "changed_fields": [],
        }, False

    path = workspace / "design_brief.json"
    brief = _load_json(path, {})
    if not isinstance(brief, dict):
        brief = {}
    changed_fields: list[str] = []

    if figure_contract:
        existing_contract = brief.get("figure_export_contract")
        if not isinstance(existing_contract, dict):
            existing_contract = {}
        merged_contract = dict(existing_contract)
        for key, value in figure_contract.items():
            if key == "outputs":
                continue
            if value not in (None, "", [], {}):
                merged_contract[key] = value
        if isinstance(figure_contract.get("outputs"), list):
            merged_contract["outputs"] = _merge_figure_outputs(
                existing_contract.get("outputs"),
                figure_contract.get("outputs"),
            )
        brief["figure_export_contract"] = merged_contract
        changed_fields.append("figure_export_contract")

    plan = brief.get("analysis_artifact_plan")
    if not isinstance(plan, dict):
        plan = {}
    if registry_updates:
        plan["artifact_registry"] = _merge_artifact_registry(plan.get("artifact_registry"), registry_updates)
        changed_fields.append("analysis_artifact_plan.artifact_registry")

    if figure_contract:
        script = _text(figure_contract.get("script"))
        rerun_command = _text(figure_contract.get("rerun_command"))
        if script and script.lower() != "none":
            plan["figure_scripts"] = _merge_unique(plan.get("figure_scripts"), [script])
            plan["required_scripts"] = _merge_unique(plan.get("required_scripts"), [script])
        if rerun_command:
            plan["rebuild_commands"] = _merge_unique(plan.get("rebuild_commands"), [rerun_command])
        if isinstance(figure_contract.get("rebuild_context"), dict):
            plan["data_analysis_figure_rebuild_context"] = figure_contract["rebuild_context"]
        outputs = [item for item in _as_list(figure_contract.get("outputs")) if isinstance(item, dict)]
        figure_paths = [_text(item.get("path")) for item in outputs if _text(item.get("path"))]
        if figure_paths:
            plan["figure_outputs"] = _merge_unique(plan.get("figure_outputs"), figure_paths)
    brief["analysis_artifact_plan"] = plan

    changed = _write_json_if_changed(path, brief, dry_run=dry_run)
    return {
        "figure_export_contract_applied": bool(figure_contract),
        "figure_export_output_count": len(_as_list(figure_contract.get("outputs"))) if figure_contract else 0,
        "artifact_registry_update_count": len(registry_updates),
        "changed_fields": changed_fields,
    }, changed


def _object_list(handoff: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = handoff.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _scout_analysis_payload(handoff: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "analysis_tasks",
        "computed_findings",
        "chart_or_table_recommendations",
        "outline_binding_plan",
    ):
        items = _object_list(handoff, key)
        if items:
            payload[key] = items
    for key in ("quality_flags", "open_questions"):
        items = _dedupe_text(_as_list(handoff.get(key)))
        if items:
            payload[key] = items
    workflow = handoff.get("recommended_workflow")
    if isinstance(workflow, dict) and workflow:
        payload["recommended_workflow"] = workflow
    return payload


def _merge_scout_analysis(existing: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    current = dict(existing) if isinstance(existing, dict) else {}
    for key in (
        "analysis_tasks",
        "computed_findings",
        "chart_or_table_recommendations",
        "outline_binding_plan",
    ):
        if key in incoming:
            current[key] = _merge_named_entries(current.get(key), incoming[key])
    for key in ("quality_flags", "open_questions"):
        if key in incoming:
            current[key] = _merge_unique(current.get(key), incoming[key])
    if isinstance(incoming.get("recommended_workflow"), dict):
        current["recommended_workflow"] = incoming["recommended_workflow"]
    return current


def _scout_analysis_counts(ledger: dict[str, Any]) -> dict[str, int]:
    return {
        "analysis_task_count": len(_as_list(ledger.get("analysis_tasks"))),
        "computed_finding_count": len(_as_list(ledger.get("computed_findings"))),
        "visual_recommendation_count": len(_as_list(ledger.get("chart_or_table_recommendations"))),
        "outline_binding_count": len(_as_list(ledger.get("outline_binding_plan"))),
        "quality_flag_count": len(_as_list(ledger.get("quality_flags"))),
        "open_question_count": len(_as_list(ledger.get("open_questions"))),
    }


def _apply_scout_analysis_metadata(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    handoff_path: Path,
    handoff_sha: str,
    dry_run: bool,
) -> tuple[dict[str, Any], bool]:
    incoming = _scout_analysis_payload(handoff)
    if not incoming:
        return {
            "schema": SCOUT_ANALYSIS_SCHEMA,
            "applied": False,
            "counts": _scout_analysis_counts({}),
            "changed_fields": [],
        }, False

    design_path = workspace / "design_brief.json"
    brief = _load_json(design_path, {})
    if not isinstance(brief, dict):
        brief = {}

    data_meta = brief.get("data_analysis_handoff")
    if not isinstance(data_meta, dict):
        data_meta = {}
    previous_ledger = data_meta.get("scout_analysis")
    previous_payload = previous_ledger if isinstance(previous_ledger, dict) else {}
    merged_payload = _merge_scout_analysis(previous_payload, incoming)
    ledger = {
        "schema": SCOUT_ANALYSIS_SCHEMA,
        "handoff_path": str(handoff_path),
        "handoff_sha256": handoff_sha,
        **merged_payload,
    }
    data_meta["scout_analysis"] = ledger
    brief["data_analysis_handoff"] = data_meta

    analysis_plan = brief.get("analysis_artifact_plan")
    if not isinstance(analysis_plan, dict):
        analysis_plan = {}
    analysis_plan["data_analysis_scout"] = ledger
    brief["analysis_artifact_plan"] = analysis_plan

    changed = _write_json_if_changed(design_path, brief, dry_run=dry_run)
    return {
        "schema": SCOUT_ANALYSIS_SCHEMA,
        "applied": True,
        "counts": _scout_analysis_counts(ledger),
        "changed_fields": [
            "data_analysis_handoff.scout_analysis",
            "analysis_artifact_plan.data_analysis_scout",
        ],
    }, changed


def _list_lines(items: list[Any], *, key: str | None = None, limit: int = 8) -> list[str]:
    lines: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            text = _text(item.get(key)) if key else ""
            if not text:
                text = _text(item.get("required_change")) or _text(item.get("immediate_next_action"))
            if not text:
                text = json.dumps(item, sort_keys=True, ensure_ascii=False)
        else:
            text = _text(item)
        if text:
            lines.append(f"- {text}")
    return lines


def _dedupe_text(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _compact_join(values: list[Any], *, limit: int = 8) -> str:
    items = _dedupe_text(values)
    if not items:
        return ""
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = _text(value)
        return [text] if text else []
    if not isinstance(value, list):
        return []
    return _dedupe_text(value)


def _rebuild_context_commands(context: dict[str, Any]) -> list[str]:
    commands = _as_dict(context.get("commands"))
    ordered = [
        commands.get("rebuild_figures"),
        commands.get("inspect_manifest"),
        commands.get("auto_select_lead"),
        commands.get("auto_select_all"),
        commands.get("validate_planning"),
    ]
    ordered.extend(_as_list(context.get("commands_to_preserve")))
    return _dedupe_text(ordered)


def _apply_rebuild_context_metadata(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    handoff_path: Path,
    handoff_sha: str,
    dry_run: bool,
) -> tuple[bool, list[str]]:
    context = _artifact_rebuild_context(handoff)
    if not context:
        return False, []

    design_path = workspace / "design_brief.json"
    brief = _load_json(design_path, {})
    if not isinstance(brief, dict):
        brief = {}

    data_meta = brief.get("data_analysis_handoff")
    if not isinstance(data_meta, dict):
        data_meta = {}
    data_meta.update(
        {
            "handoff_path": str(handoff_path),
            "handoff_sha256": handoff_sha,
            "artifact_rebuild_context": context,
        }
    )
    brief["data_analysis_handoff"] = data_meta

    plan = brief.get("analysis_artifact_plan")
    if not isinstance(plan, dict):
        plan = {}
    plan["data_analysis_rebuild_context"] = context
    for source_key, target_key in (
        ("artifact_manifest", "artifact_manifest"),
        ("analysis_summary", "analysis_summary"),
        ("analysis_summary_markdown", "analysis_summary_markdown"),
    ):
        value = _text(context.get(source_key))
        if value and value.lower() != "none":
            plan[target_key] = value

    source_paths = _string_list(context.get("source_paths"))
    if source_paths:
        plan["candidate_data_files"] = _merge_unique(plan.get("candidate_data_files"), source_paths)

    commands = _as_dict(context.get("commands"))
    rebuild_command = _text(commands.get("rebuild_figures"))
    if rebuild_command:
        plan["rebuild_commands"] = _merge_unique(plan.get("rebuild_commands"), [rebuild_command])
    all_commands = _rebuild_context_commands(context)
    if all_commands:
        plan["data_analysis_rebuild_commands"] = _merge_unique(
            plan.get("data_analysis_rebuild_commands"),
            all_commands,
        )

    producer = _text(context.get("producer_path"))
    if producer and producer.lower() != "none":
        plan["figure_scripts"] = _merge_unique(plan.get("figure_scripts"), [producer])

    brief["analysis_artifact_plan"] = plan
    changed = _write_json_if_changed(design_path, brief, dry_run=dry_run)
    return changed, [
        "data_analysis_handoff.artifact_rebuild_context",
        "analysis_artifact_plan.data_analysis_rebuild_context",
    ]


def _artifact_evidence_ledger(
    handoff: dict[str, Any],
    *,
    selection_path: Path | None,
    bindings: list[dict[str, Any]],
    evidence_ids: list[str],
    data_sources: list[dict[str, Any]],
    applied_bindings: bool,
    commands_to_run: list[str],
    artifact_rebuild_context: dict[str, Any],
) -> dict[str, Any]:
    main = _as_dict(handoff.get("main_agent_handoff"))
    qa = _as_dict(handoff.get("qa_readiness_plan"))
    script_edits = [item for item in _as_list(handoff.get("script_edit_plan")) if isinstance(item, dict)]
    output_ids = _dedupe_text(
        [
            binding.get("output_id") or binding.get("id")
            for binding in bindings
        ]
    )
    slide_ids = _dedupe_text(
        [
            binding.get("slide_id") or binding.get("target_slide")
            for binding in bindings
        ]
    )
    variants = _dedupe_text(
        [
            binding.get("variant") or binding.get("slide_variant")
            for binding in bindings
        ]
    )
    titles = _dedupe_text([binding.get("title") for binding in bindings])
    script_paths = _dedupe_text([item.get("path") for item in script_edits])
    data_paths = _dedupe_text([_data_source_path(item) for item in data_sources])
    data_hashes = _dedupe_text([item.get("source_sha256") for item in data_sources])
    return {
        "selection_file": str(selection_path) if selection_path is not None else "",
        "binding_count": len(bindings),
        "applied_bindings": applied_bindings,
        "bound_output_ids": output_ids,
        "slide_ids": slide_ids,
        "variants": variants,
        "slide_titles": titles,
        "evidence_ids": _dedupe_text(evidence_ids),
        "script_edit_paths": script_paths,
        "data_source_paths": data_paths,
        "data_source_sha256": data_hashes,
        "data_sources": data_sources,
        "source_checks": _dedupe_text(_as_list(qa.get("source_checks"))),
        "build_checks": _dedupe_text(_as_list(qa.get("build_checks"))),
        "verification_evidence": _dedupe_text(_as_list(main.get("verification_evidence"))),
        "commands_to_run": _dedupe_text(commands_to_run),
        "artifact_rebuild_context": artifact_rebuild_context,
        "artifact_rebuild_commands": _rebuild_context_commands(artifact_rebuild_context),
    }


def _alias_tokens(value: Any) -> list[str]:
    tokens: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            text = item.strip()
            if text.startswith(("image:", "chart:", "table:", "asset:")):
                tokens.append(text)
            return
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
            return
        if isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return _dedupe_text(tokens)


def _slide_ref(item: dict[str, Any]) -> str:
    return _text(item.get("slide_id")) or _text(item.get("target_slide"))


def _variant_ref(item: dict[str, Any]) -> str:
    return _text(item.get("variant")) or _text(item.get("slide_variant")) or _text(item.get("target_variant"))


def _match_for_slide(items: list[dict[str, Any]], slide_id: str, variant: str = "") -> dict[str, Any]:
    if not slide_id:
        return {}
    fallback: dict[str, Any] = {}
    for item in items:
        if _slide_ref(item) != slide_id:
            continue
        if not fallback:
            fallback = item
        item_variant = _variant_ref(item)
        if variant and item_variant == variant:
            return item
    return fallback


def _figure_output_for_slide(outputs: list[dict[str, Any]], slide_id: str, variant: str = "") -> dict[str, Any]:
    if not slide_id:
        return {}
    fallback: dict[str, Any] = {}
    for output in outputs:
        target_slide = _text(output.get("target_slide"))
        if target_slide != slide_id:
            continue
        if not fallback:
            fallback = output
        target_variant = _text(output.get("target_variant"))
        if variant and target_variant == variant:
            return output
    return fallback


def _artifact_roles(variant: str, aliases: list[str]) -> list[str]:
    roles: list[str] = []
    if variant in {"image-sidebar", "scientific-figure"} or any(alias.startswith("image:") for alias in aliases):
        roles.append("figure")
    if variant in {"chart", "lab-run-results"} or any(alias.startswith("chart:") for alias in aliases):
        roles.append("chart")
    if variant in {"table", "lab-run-results"} or any(alias.startswith("table:") for alias in aliases):
        roles.append("table")
    if not roles:
        roles.append("evidence")
    return _dedupe_text(roles)


def _quality_targets(
    *,
    outline_binding: dict[str, Any],
    visual_recommendation: dict[str, Any],
    figure_output: dict[str, Any],
) -> dict[str, Any]:
    targets: dict[str, Any] = {}
    if _text(outline_binding.get("readability_target")):
        targets["readability_target"] = _text(outline_binding.get("readability_target"))
    for key in ("target_box", "figure_size_inches", "figure_dpi", "axis_label_min_pt", "legend_pt", "x_label_rotation"):
        value = figure_output.get(key)
        if value not in (None, "", [], {}):
            targets[key] = value
    if _text(visual_recommendation.get("data_shape")):
        targets["data_shape"] = _text(visual_recommendation.get("data_shape"))
    columns = visual_recommendation.get("columns_or_series")
    if isinstance(columns, list) and columns:
        targets["columns_or_series"] = _dedupe_text(columns)
    return targets


def _artifact_storyboard(
    handoff: dict[str, Any],
    *,
    bindings: list[dict[str, Any]],
    evidence_ids: list[str],
    data_sources: list[dict[str, Any]],
    artifact_rebuild_context: dict[str, Any],
) -> dict[str, Any]:
    outline_bindings = _object_list(handoff, "outline_binding_plan")
    visual_recommendations = _object_list(handoff, "chart_or_table_recommendations")
    scout_storyboard = _object_list(handoff, "slide_artifact_storyboard")
    figure_outputs = [
        item for item in _as_list(_figure_export_contract(handoff).get("outputs")) if isinstance(item, dict)
    ]
    script_edits = [item for item in _as_list(handoff.get("script_edit_plan")) if isinstance(item, dict)]
    script_paths = _dedupe_text([item.get("path") for item in script_edits])
    if not script_paths:
        producer = _text(artifact_rebuild_context.get("producer_path"))
        if producer and producer.lower() != "none":
            script_paths = [producer]
    source_paths = _dedupe_text([_data_source_path(item) for item in data_sources])
    source_hashes = _dedupe_text([item.get("source_sha256") for item in data_sources])
    items: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_slide_variants: set[str] = set()

    def add_item(base: dict[str, Any]) -> None:
        slide_id = _slide_ref(base)
        variant = _variant_ref(base)
        output_id = _text(base.get("output_id")) or _text(base.get("artifact_output_id"))
        slide_variant_key = f"{slide_id}|{variant}"
        if not output_id and slide_variant_key in seen_slide_variants:
            return
        key = f"{slide_id}|{variant}|{output_id}"
        if not slide_id or key in seen_keys:
            return
        seen_keys.add(key)
        seen_slide_variants.add(slide_variant_key)
        outline_binding = _match_for_slide(outline_bindings, slide_id, variant)
        visual_recommendation = _match_for_slide(visual_recommendations, slide_id, variant)
        figure_output = _figure_output_for_slide(figure_outputs, slide_id, variant)
        fields_to_set = (
            outline_binding.get("fields_to_set")
            if isinstance(outline_binding.get("fields_to_set"), dict)
            else {}
        )
        aliases = _alias_tokens(fields_to_set)
        if not aliases:
            aliases = _alias_tokens(base)
        if isinstance(base.get("artifact_aliases"), list):
            aliases = _dedupe_text(aliases + _as_list(base.get("artifact_aliases")))
        item_evidence_ids = _dedupe_text(
            _as_list(base.get("evidence_ids"))
            or _as_list(outline_binding.get("evidence_ids"))
            or evidence_ids
        )
        base_quality = base.get("quality_targets") if isinstance(base.get("quality_targets"), dict) else {}
        quality_targets = _quality_targets(
            outline_binding=outline_binding,
            visual_recommendation=visual_recommendation,
            figure_output=figure_output,
        )
        if base_quality:
            merged_quality = dict(quality_targets)
            merged_quality.update({key: value for key, value in base_quality.items() if value not in (None, "", [], {})})
            quality_targets = merged_quality
        explicit_roles = _dedupe_text(_as_list(base.get("artifact_roles")))
        item: dict[str, Any] = {
            "slide_id": slide_id,
            "slide_title": _text(base.get("title")) or _text(outline_binding.get("title")),
            "variant": variant,
            "output_id": output_id,
            "artifact_roles": explicit_roles or _artifact_roles(variant, aliases),
            "artifact_aliases": aliases,
            "evidence_ids": item_evidence_ids,
            "message": _text(base.get("message")),
            "interpretation": _text(base.get("interpretation")),
            "source_note": _text(base.get("source_note")),
            "data_source_paths": source_paths,
            "data_source_sha256": source_hashes,
            "script_edit_paths": script_paths,
            "quality_targets": quality_targets,
            "source_fields": [
                "outline.json:slides",
                "evidence_plan.json:items",
                "design_brief.json:analysis_artifact_plan",
                "design_brief.json:figure_export_contract",
                "asset_plan.json",
            ],
        }
        compact = {key: value for key, value in item.items() if value not in (None, "", [], {})}
        items.append(compact)

    for storyboard_item in scout_storyboard:
        add_item(storyboard_item)
    for binding in bindings:
        add_item(binding)
    for outline_binding in outline_bindings:
        add_item(outline_binding)

    return {
        "schema": ARTIFACT_STORYBOARD_SCHEMA,
        "item_count": len(items),
        "items": items,
    }


def _apply_artifact_storyboard_metadata(
    workspace: Path,
    storyboard: dict[str, Any],
    *,
    handoff_path: Path,
    handoff_sha: str,
    dry_run: bool,
) -> tuple[dict[str, Any], bool]:
    items = [item for item in _as_list(storyboard.get("items")) if isinstance(item, dict)]
    if not items:
        return {
            "schema": ARTIFACT_STORYBOARD_SCHEMA,
            "applied": False,
            "item_count": 0,
            "changed_fields": [],
        }, False

    design_path = workspace / "design_brief.json"
    brief = _load_json(design_path, {})
    if not isinstance(brief, dict):
        brief = {}
    persisted = dict(storyboard)
    persisted.update(
        {
            "handoff_path": str(handoff_path),
            "handoff_sha256": handoff_sha,
        }
    )

    data_meta = brief.get("data_analysis_handoff")
    if not isinstance(data_meta, dict):
        data_meta = {}
    data_meta["artifact_storyboard"] = persisted
    brief["data_analysis_handoff"] = data_meta

    analysis_plan = brief.get("analysis_artifact_plan")
    if not isinstance(analysis_plan, dict):
        analysis_plan = {}
    analysis_plan["data_artifact_storyboard"] = persisted
    brief["analysis_artifact_plan"] = analysis_plan

    changed = _write_json_if_changed(design_path, brief, dry_run=dry_run)
    return {
        "schema": ARTIFACT_STORYBOARD_SCHEMA,
        "applied": True,
        "item_count": len(items),
        "changed_fields": [
            "data_analysis_handoff.artifact_storyboard",
            "analysis_artifact_plan.data_artifact_storyboard",
        ],
    }, changed


def _replace_notes_section(existing: str, section: str) -> str:
    if NOTE_START in existing and NOTE_END in existing:
        before = existing.split(NOTE_START, 1)[0].rstrip()
        after = existing.split(NOTE_END, 1)[1].lstrip()
        parts = [part for part in (before, section.rstrip(), after.rstrip()) if part]
        return "\n\n".join(parts) + "\n"
    prefix = existing.rstrip()
    return (prefix + "\n\n" if prefix else "") + section.rstrip() + "\n"


def _notes_section(
    handoff: dict[str, Any],
    *,
    handoff_path: Path,
    selection_path: Path | None,
    selection_count: int,
    artifact_ledger: dict[str, Any] | None = None,
    artifact_storyboard: dict[str, Any] | None = None,
    artifact_contracts: dict[str, Any] | None = None,
    asset_update_counts: dict[str, int] | None = None,
    scout_analysis: dict[str, Any] | None = None,
) -> str:
    workflow = _as_dict(handoff.get("recommended_workflow"))
    main = _as_dict(handoff.get("main_agent_handoff"))
    qa = _as_dict(handoff.get("qa_readiness_plan"))
    rebuild_context = _artifact_rebuild_context(handoff)
    script_edits = [item for item in _as_list(handoff.get("script_edit_plan")) if isinstance(item, dict)]
    lines = [
        NOTE_START,
        "## Data Analysis Handoff",
        "",
        f"- Handoff JSON: `{handoff_path}`",
        f"- Recommended workflow: `{_text(workflow.get('mode')) or 'not specified'}`",
    ]
    if _text(workflow.get("reason")):
        lines.append(f"- Reason: {_text(workflow.get('reason'))}")
    if selection_path is not None:
        lines.append(f"- Artifact selection file: `{selection_path}` ({selection_count} bindings)")
    if _text(main.get("immediate_next_action")):
        lines.append(f"- Immediate next action: {_text(main.get('immediate_next_action'))}")
    ledger = artifact_ledger if isinstance(artifact_ledger, dict) else {}
    if ledger:
        lines.extend(["", "### Artifact Evidence Ledger"])
        if _text(ledger.get("selection_file")):
            lines.append(f"- Selection file: `{_text(ledger.get('selection_file'))}`")
        if _text(ledger.get("binding_count")):
            lines.append(f"- Binding count: {_text(ledger.get('binding_count'))}")
        for key, label in (
            ("bound_output_ids", "Bound outputs"),
            ("slide_ids", "Target slides"),
            ("variants", "Variants"),
            ("slide_titles", "Slide titles"),
            ("evidence_ids", "Evidence IDs"),
            ("script_edit_paths", "Script edit paths"),
            ("data_source_paths", "Data sources"),
        ):
            summary = _compact_join(_as_list(ledger.get(key)))
            if summary:
                lines.append(f"- {label}: {summary}")
        data_sources = [item for item in _as_list(ledger.get("data_sources")) if isinstance(item, dict)]
        if data_sources:
            lines.append("- Data source fingerprints:")
            for item in data_sources[:8]:
                path = _data_source_path(item)
                sha = _text(item.get("source_sha256"))
                size = _text(item.get("source_size_bytes"))
                summary = path
                if sha:
                    summary += f" sha256={sha}"
                if size:
                    summary += f" bytes={size}"
                if summary:
                    lines.append(f"  - {summary}")
    storyboard = artifact_storyboard if isinstance(artifact_storyboard, dict) else {}
    storyboard_items = [item for item in _as_list(storyboard.get("items")) if isinstance(item, dict)]
    if storyboard_items:
        lines.extend(["", "### Slide Artifact Storyboard"])
        lines.append(f"- Storyboard items: {len(storyboard_items)}")
        for item in storyboard_items[:8]:
            slide_id = _text(item.get("slide_id"))
            variant = _text(item.get("variant"))
            output_id = _text(item.get("output_id"))
            roles = _compact_join(_as_list(item.get("artifact_roles")), limit=4)
            sources = _compact_join(_as_list(item.get("data_source_paths")), limit=3)
            quality = item.get("quality_targets") if isinstance(item.get("quality_targets"), dict) else {}
            target_box = _text(quality.get("target_box"))
            detail = []
            if output_id:
                detail.append(f"output={output_id}")
            if roles:
                detail.append(f"roles={roles}")
            if sources:
                detail.append(f"sources={sources}")
            if target_box:
                detail.append(f"target_box={target_box}")
            suffix = " " + "; ".join(detail) if detail else ""
            lines.append(f"- `{slide_id}` variant `{variant}`:{suffix}")
    if rebuild_context:
        lines.extend(["", "### Artifact Rebuild Context"])
        if _text(rebuild_context.get("context_version")):
            lines.append(f"- Context: `{_text(rebuild_context.get('context_version'))}`")
        if _text(rebuild_context.get("source")):
            lines.append(f"- Source: `{_text(rebuild_context.get('source'))}`")
        if _text(rebuild_context.get("producer_path")):
            lines.append(f"- Producer: `{_text(rebuild_context.get('producer_path'))}`")
        if _text(rebuild_context.get("artifact_manifest")):
            lines.append(f"- Manifest: `{_text(rebuild_context.get('artifact_manifest'))}`")
        if _text(rebuild_context.get("analysis_summary")):
            lines.append(f"- Analysis summary: `{_text(rebuild_context.get('analysis_summary'))}`")
        for command in _rebuild_context_commands(rebuild_context)[:6]:
            lines.append(f"- `{command}`")
    contracts = artifact_contracts if isinstance(artifact_contracts, dict) else {}
    asset_counts = asset_update_counts if isinstance(asset_update_counts, dict) else {}
    if contracts or asset_counts:
        lines.extend(["", "### Artifact Contracts Applied"])
        if contracts.get("figure_export_contract_applied"):
            lines.append(f"- Figure export outputs: {int(contracts.get('figure_export_output_count') or 0)}")
        if int(contracts.get("artifact_registry_update_count") or 0):
            lines.append(f"- Artifact registry updates: {int(contracts.get('artifact_registry_update_count') or 0)}")
        for section in ("images", "charts", "tables"):
            count = int(asset_counts.get(section) or 0)
            if count:
                lines.append(f"- Asset plan {section}: {count}")
    analysis = scout_analysis if isinstance(scout_analysis, dict) else {}
    if analysis.get("applied"):
        counts = analysis.get("counts") if isinstance(analysis.get("counts"), dict) else {}
        lines.extend(["", "### Scout Analysis Ledger"])
        for key, label in (
            ("analysis_task_count", "Analysis tasks"),
            ("computed_finding_count", "Computed findings"),
            ("visual_recommendation_count", "Visual recommendations"),
            ("outline_binding_count", "Outline bindings"),
            ("quality_flag_count", "Quality flags"),
            ("open_question_count", "Open questions"),
        ):
            lines.append(f"- {label}: {int(counts.get(key) or 0)}")
    if script_edits:
        lines.extend(["", "Script edits requested:"])
        lines.extend(_list_lines(script_edits, key="required_change"))
    commands = [item for item in _as_list(main.get("commands_to_run")) if _text(item)]
    if commands:
        lines.extend(["", "Commands to run:"])
        lines.extend(_list_lines(commands))
    evidence = [item for item in _as_list(main.get("verification_evidence")) if _text(item)]
    if evidence:
        lines.extend(["", "Verification evidence:"])
        lines.extend(_list_lines(evidence))
    risks = [item for item in _as_list(qa.get("specific_risks")) if _text(item)]
    if risks:
        lines.extend(["", "QA risks to inspect:"])
        lines.extend(_list_lines(risks))
    lines.append(NOTE_END)
    return "\n".join(lines)


def _apply_notes(
    workspace: Path,
    handoff: dict[str, Any],
    *,
    handoff_path: Path,
    selection_path: Path | None,
    selection_count: int,
    artifact_ledger: dict[str, Any] | None,
    artifact_storyboard: dict[str, Any] | None,
    artifact_contracts: dict[str, Any] | None,
    asset_update_counts: dict[str, int] | None,
    scout_analysis: dict[str, Any] | None,
    dry_run: bool,
) -> bool:
    path = workspace / "notes.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    section = _notes_section(
        handoff,
        handoff_path=handoff_path,
        selection_path=selection_path,
        selection_count=selection_count,
        artifact_ledger=artifact_ledger,
        artifact_storyboard=artifact_storyboard,
        artifact_contracts=artifact_contracts,
        asset_update_counts=asset_update_counts,
        scout_analysis=scout_analysis,
    )
    return _write_text_if_changed(path, _replace_notes_section(existing, section), dry_run=dry_run)


def apply_handoff(
    workspace: Path,
    handoff_path: Path,
    *,
    manifest_path: Path,
    selection_out: Path | None,
    apply_bindings: bool,
    overwrite_evidence: bool,
    dry_run: bool,
) -> dict[str, Any]:
    handoff = _validate_handoff(_load_json(handoff_path, {}))
    handoff_sha = _file_sha256(handoff_path)
    bindings = _selection_bindings(handoff)
    selection_path = selection_out
    selection_changed = False
    binding_report: dict[str, Any] = {}
    if bindings:
        selection_path = selection_path or _selection_file_from_handoff(
            workspace,
            handoff,
            override=None,
        )
        selection_changed = _write_json_if_changed(
            selection_path,
            {"bindings": bindings},
            dry_run=dry_run,
        )
        if apply_bindings:
            if not manifest_path.exists():
                raise ValueError(f"artifact manifest not found: {manifest_path}")
            manifest_report = inspect_manifest(workspace, manifest_path)
            binding_report = apply_selection_payload(
                workspace,
                manifest_path=manifest_path,
                report=manifest_report,
                selections=bindings,
                selection_label=str(selection_path),
                dry_run=dry_run,
            )
    evidence_ids, evidence_changed = _apply_evidence_updates(
        workspace,
        handoff,
        overwrite=overwrite_evidence,
        dry_run=dry_run,
    )
    data_sources, data_inventory_changed = _apply_data_inventory(
        workspace,
        handoff,
        dry_run=dry_run,
    )
    rebuild_context = _artifact_rebuild_context(handoff)
    rebuild_context_changed, rebuild_context_fields = _apply_rebuild_context_metadata(
        workspace,
        handoff,
        handoff_path=handoff_path,
        handoff_sha=handoff_sha,
        dry_run=dry_run,
    )
    asset_update_counts, asset_plan_updates_changed = _apply_asset_plan_updates(
        workspace,
        handoff,
        dry_run=dry_run,
    )
    artifact_contracts, artifact_contracts_changed = _apply_artifact_contracts(
        workspace,
        handoff,
        dry_run=dry_run,
    )
    scout_analysis, scout_analysis_changed = _apply_scout_analysis_metadata(
        workspace,
        handoff,
        handoff_path=handoff_path,
        handoff_sha=handoff_sha,
        dry_run=dry_run,
    )
    main = _as_dict(handoff.get("main_agent_handoff"))
    qa = _as_dict(handoff.get("qa_readiness_plan"))
    commands_to_run = [
        _text(item)
        for item in _as_list(main.get("commands_to_run"))
        if _text(item)
    ]
    if not commands_to_run:
        commands_to_run = [
            f"python3 scripts/validate_planning.py --workspace {workspace}",
            (
                "python3 scripts/build_workspace.py "
                f"--workspace {workspace} --qa --fail-on-planning-warnings "
                "--fail-on-whitespace-warnings --overwrite"
            ),
        ]
    artifact_ledger = _artifact_evidence_ledger(
        handoff,
        selection_path=selection_path,
        bindings=bindings,
        evidence_ids=evidence_ids,
        data_sources=data_sources,
        applied_bindings=bool(bindings and apply_bindings),
        commands_to_run=commands_to_run,
        artifact_rebuild_context=rebuild_context,
    )
    artifact_storyboard = _artifact_storyboard(
        handoff,
        bindings=bindings,
        evidence_ids=evidence_ids,
        data_sources=data_sources,
        artifact_rebuild_context=rebuild_context,
    )
    artifact_ledger["slide_artifact_storyboard"] = artifact_storyboard
    artifact_storyboard_report, artifact_storyboard_changed = _apply_artifact_storyboard_metadata(
        workspace,
        artifact_storyboard,
        handoff_path=handoff_path,
        handoff_sha=handoff_sha,
        dry_run=dry_run,
    )
    notes_changed = _apply_notes(
        workspace,
        handoff,
        handoff_path=handoff_path,
        selection_path=selection_path,
        selection_count=len(bindings),
        artifact_ledger=artifact_ledger,
        artifact_storyboard=artifact_storyboard,
        artifact_contracts=artifact_contracts,
        asset_update_counts=asset_update_counts,
        scout_analysis=scout_analysis,
        dry_run=dry_run,
    )
    changed_files = []
    if selection_changed and selection_path is not None:
        changed_files.append(str(selection_path))
    for key, path in (
        ("outline_changed", workspace / "outline.json"),
        ("content_plan_changed", workspace / "content_plan.json"),
        ("evidence_plan_changed", workspace / "evidence_plan.json"),
        ("design_brief_changed", workspace / "design_brief.json"),
        ("asset_plan_changed", workspace / "asset_plan.json"),
    ):
        if binding_report.get(key):
            changed_files.append(str(path))
    if data_inventory_changed and str(workspace / "design_brief.json") not in changed_files:
        changed_files.append(str(workspace / "design_brief.json"))
    if rebuild_context_changed and str(workspace / "design_brief.json") not in changed_files:
        changed_files.append(str(workspace / "design_brief.json"))
    if artifact_contracts_changed and str(workspace / "design_brief.json") not in changed_files:
        changed_files.append(str(workspace / "design_brief.json"))
    if scout_analysis_changed and str(workspace / "design_brief.json") not in changed_files:
        changed_files.append(str(workspace / "design_brief.json"))
    if artifact_storyboard_changed and str(workspace / "design_brief.json") not in changed_files:
        changed_files.append(str(workspace / "design_brief.json"))
    if asset_plan_updates_changed and str(workspace / "asset_plan.json") not in changed_files:
        changed_files.append(str(workspace / "asset_plan.json"))
    if evidence_changed and str(workspace / "evidence_plan.json") not in changed_files:
        changed_files.append(str(workspace / "evidence_plan.json"))
    if notes_changed:
        changed_files.append(str(workspace / "notes.md"))
    return {
        "workspace": str(workspace),
        "workflow": "data_analysis_handoff_apply_v1",
        "handoff": str(handoff_path),
        "handoff_sha256": handoff_sha,
        "handoff_snapshot": _file_snapshot(handoff_path),
        "manifest": str(manifest_path),
        "manifest_snapshot": _file_snapshot(manifest_path),
        "dry_run": dry_run,
        "applied_bindings": bool(bindings and apply_bindings),
        "selection_file": str(selection_path) if selection_path is not None else "",
        "selection_count": len(bindings),
        "selection_file_changed": selection_changed,
        "binding_report": binding_report,
        "artifact_evidence_ledger": artifact_ledger,
        "data_source_count": len(data_sources),
        "data_source_fingerprints": data_sources,
        "data_inventory_changed": data_inventory_changed,
        "design_brief_changed": bool(
            binding_report.get("design_brief_changed")
            or data_inventory_changed
            or rebuild_context_changed
            or artifact_contracts_changed
            or scout_analysis_changed
            or artifact_storyboard_changed
        ),
        "asset_plan_changed": bool(binding_report.get("asset_plan_changed") or asset_plan_updates_changed),
        "artifact_rebuild_context_applied": bool(rebuild_context),
        "artifact_rebuild_context_changed": rebuild_context_changed,
        "artifact_rebuild_context_fields": rebuild_context_fields,
        "figure_export_contract_applied": bool(artifact_contracts.get("figure_export_contract_applied")),
        "figure_export_output_count": int(artifact_contracts.get("figure_export_output_count") or 0),
        "artifact_registry_update_count": int(artifact_contracts.get("artifact_registry_update_count") or 0),
        "artifact_contracts_changed": artifact_contracts_changed,
        "artifact_contract_fields": artifact_contracts.get("changed_fields", []),
        "asset_plan_update_counts": asset_update_counts,
        "asset_plan_updates_changed": asset_plan_updates_changed,
        "scout_analysis_applied": bool(scout_analysis.get("applied")),
        "scout_analysis_changed": scout_analysis_changed,
        "scout_analysis_counts": scout_analysis.get("counts", {}),
        "scout_analysis_fields": scout_analysis.get("changed_fields", []),
        "artifact_storyboard": artifact_storyboard,
        "artifact_storyboard_applied": bool(artifact_storyboard_report.get("applied")),
        "artifact_storyboard_changed": artifact_storyboard_changed,
        "artifact_storyboard_item_count": int(artifact_storyboard_report.get("item_count") or 0),
        "artifact_storyboard_fields": artifact_storyboard_report.get("changed_fields", []),
        "evidence_ids": evidence_ids,
        "evidence_plan_changed": evidence_changed,
        "notes_changed": notes_changed,
        "changed_files": changed_files,
        "changed_file_count": len(changed_files),
        "script_edit_count": len([item for item in _as_list(handoff.get("script_edit_plan")) if isinstance(item, dict)]),
        "qa_source_checks": _as_list(qa.get("source_checks")),
        "qa_build_checks": _as_list(qa.get("build_checks")),
        "next_commands": commands_to_run,
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Deck workspace root.")
    parser.add_argument("--handoff", required=True, help="Data/evidence scout JSON output.")
    parser.add_argument(
        "--manifest",
        default="assets/artifacts_manifest.json",
        help="Artifact manifest path, relative to the workspace by default.",
    )
    parser.add_argument(
        "--selection-out",
        help="Selection JSON output path. Defaults to the scout selection_file or artifact_selections.scout.json.",
    )
    parser.add_argument(
        "--write-selection-only",
        action="store_true",
        help="Write the selection JSON and notes but do not apply manifest bindings.",
    )
    parser.add_argument(
        "--overwrite-evidence",
        action="store_true",
        help="Allow evidence_plan_updates to replace existing non-empty evidence fields.",
    )
    parser.add_argument("--report", help="Optional JSON report path.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace).expanduser().resolve()
    handoff_path = Path(args.handoff).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 1
    if not handoff_path.exists():
        print(f"Error: handoff JSON not found: {handoff_path}", file=sys.stderr)
        return 1
    manifest_path = _workspace_path(workspace, args.manifest)
    selection_out = _workspace_path(workspace, args.selection_out) if args.selection_out else None
    try:
        report = apply_handoff(
            workspace,
            handoff_path,
            manifest_path=manifest_path,
            selection_out=selection_out,
            apply_bindings=not args.write_selection_only,
            overwrite_evidence=args.overwrite_evidence,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: cannot apply data-analysis handoff: {exc}", file=sys.stderr)
        return 1
    if args.report:
        _write_json_if_changed(Path(args.report).expanduser().resolve(), report, dry_run=False)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
