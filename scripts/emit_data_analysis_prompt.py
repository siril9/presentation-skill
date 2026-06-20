#!/usr/bin/env python3
"""Emit a subagent prompt for deck data/evidence analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from inspect_artifact_manifest import inspect_manifest
except Exception:  # pragma: no cover - prompt emission can still continue.
    inspect_manifest = None  # type: ignore[assignment]


DATA_SUFFIXES = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".xlsx",
    ".xls",
    ".parquet",
    ".feather",
    ".txt",
}
SMALL_FILE_HASH_LIMIT = 5 * 1024 * 1024
PREVIEW_MAX_BYTES = 512 * 1024
PREVIEW_ROW_LIMIT = 3
DATA_INVENTORY_EXCLUDED_NAMES = {
    "artifacts_manifest.json",
    "analysis_summary.json",
    "artifact_selections.auto.json",
    "artifact_selections.scout.json",
    "data_analysis_handoff.json",
    "data_analysis_handoff_apply_report.json",
}


def _read_optional(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _load_json(path: Path) -> Any | None:
    text = _read_optional(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated at {limit} chars]"


def _compact_json(payload: Any, limit: int) -> str:
    if payload is None:
        return "<missing or malformed>"
    return _truncate(json.dumps(payload, indent=2, ensure_ascii=False), limit)


def _resolve_input_path(workspace: Path, raw: str) -> Path:
    """Resolve explicit inputs without duplicating repo-relative deck paths."""
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()

    cwd_candidate = (Path.cwd() / path).resolve()
    if cwd_candidate.exists():
        return cwd_candidate

    workspace_candidate = (workspace / path).resolve()
    if workspace_candidate.exists():
        return workspace_candidate

    return cwd_candidate


def _candidate_data_files(workspace: Path, explicit_paths: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in explicit_paths:
        paths.append(_resolve_input_path(workspace, raw))

    roots = [
        workspace / "data",
        workspace / "assets" / "data",
        workspace / "assets" / "tables",
        workspace / "assets",
    ]
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and path.suffix.lower() in DATA_SUFFIXES
                and path.name not in DATA_INVENTORY_EXCLUDED_NAMES
            ):
                paths.append(path.resolve())

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique[:80]


def _workspace_relative_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _data_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".tsv":
        return "tsv"
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in {".xlsx", ".xls"}:
        return "xlsx"
    if suffix == ".parquet":
        return "parquet"
    if suffix == ".feather":
        return "feather"
    if suffix == ".txt":
        return "text"
    return "unknown"


def _hash_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"exists": False}
    try:
        size = path.stat().st_size
        snapshot: dict[str, Any] = {"exists": True, "size_bytes": size}
        if size <= SMALL_FILE_HASH_LIMIT:
            snapshot["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            snapshot["sha256"] = ""
            snapshot["hash_status"] = f"skipped_gt_{SMALL_FILE_HASH_LIMIT}_bytes"
        return snapshot
    except OSError as exc:
        return {"exists": True, "error": str(exc)}


def _delimited_preview(path: Path, delimiter: str) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        if path.stat().st_size > PREVIEW_MAX_BYTES:
            return {"preview_status": f"skipped_gt_{PREVIEW_MAX_BYTES}_bytes"}
    except OSError:
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            header = next(reader, [])
            rows: list[list[str]] = []
            for row in reader:
                if len(rows) < PREVIEW_ROW_LIMIT:
                    rows.append(row[:12])
                if len(rows) >= PREVIEW_ROW_LIMIT:
                    break
        return {
            "columns": header[:24],
            "column_count": len(header),
            "sample_rows": rows,
            "sample_row_count": len(rows),
        }
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return {"preview_error": str(exc)}


def _json_preview(path: Path, *, jsonl: bool = False) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        if path.stat().st_size > PREVIEW_MAX_BYTES:
            return {"preview_status": f"skipped_gt_{PREVIEW_MAX_BYTES}_bytes"}
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"preview_error": str(exc)}
    try:
        if jsonl:
            rows = [json.loads(line) for line in text.splitlines()[:PREVIEW_ROW_LIMIT] if line.strip()]
            key_union = sorted(
                {
                    str(key)
                    for row in rows
                    if isinstance(row, dict)
                    for key in row.keys()
                }
            )
            return {
                "top_level_type": "jsonl",
                "sample_record_count": len(rows),
                "sample_keys": key_union[:24],
            }
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"preview_error": str(exc)}
    if isinstance(payload, dict):
        return {
            "top_level_type": "object",
            "top_level_keys": [str(key) for key in list(payload.keys())[:24]],
            "top_level_key_count": len(payload),
        }
    if isinstance(payload, list):
        sample = payload[:PREVIEW_ROW_LIMIT]
        key_union = sorted(
            {
                str(key)
                for row in sample
                if isinstance(row, dict)
                for key in row.keys()
            }
        )
        return {
            "top_level_type": "array",
            "row_count_if_fully_loaded": len(payload),
            "sample_keys": key_union[:24],
        }
    return {"top_level_type": type(payload).__name__}


def _file_preview(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _delimited_preview(path, ",")
    if suffix == ".tsv":
        return _delimited_preview(path, "\t")
    if suffix == ".json":
        return _json_preview(path)
    if suffix == ".jsonl":
        return _json_preview(path, jsonl=True)
    if suffix in {".xlsx", ".xls"}:
        return {"preview_status": "deferred_to_scaffold_excel_sheet_scan"}
    if suffix in {".parquet", ".feather"}:
        return {"preview_status": "deferred_to_pandas_columnar_engine"}
    return {}


def _file_inventory(workspace: Path, paths: list[Path]) -> str:
    if not paths:
        return "<no candidate data files found>"
    items: list[dict[str, Any]] = []
    for path in paths:
        snapshot = _hash_snapshot(path)
        item: dict[str, Any] = {
            "path": str(path),
            "workspace_relative_path": _workspace_relative_path(workspace, path),
            "status": "usable" if snapshot.get("exists") else "missing",
            "data_type": _data_type(path),
        }
        if "size_bytes" in snapshot:
            item["source_size_bytes"] = snapshot["size_bytes"]
        if "sha256" in snapshot:
            item["source_sha256"] = snapshot["sha256"]
        if "hash_status" in snapshot:
            item["hash_status"] = snapshot["hash_status"]
        if "error" in snapshot:
            item["error"] = snapshot["error"]
        preview = _file_preview(path)
        if preview:
            item["preview"] = preview
        items.append(item)
    return _compact_json(
        {
            "inventory_version": "deck_data_source_inventory_v1",
            "file_count": len(items),
            "files": items,
            "limits": {
                "sha256_hashed_when_size_lte_bytes": SMALL_FILE_HASH_LIMIT,
                "previewed_when_size_lte_bytes": PREVIEW_MAX_BYTES,
                "preview_row_limit": PREVIEW_ROW_LIMIT,
            },
        },
        18000,
    )


def _outline_summary(outline: Any) -> str:
    if not isinstance(outline, dict):
        return "outline.json: <missing or malformed>"
    slides = outline.get("slides") or []
    lines = [
        f"Deck title: {outline.get('title', '<untitled>')}",
        f"Deck subtitle: {outline.get('subtitle', '')}",
        f"Slide count: {len(slides) if isinstance(slides, list) else '<invalid>'}",
    ]
    if isinstance(slides, list):
        for idx, slide in enumerate(slides[:24]):
            if not isinstance(slide, dict):
                continue
            lines.append(
                f"slide {idx:02d}: type={slide.get('type', 'content')} "
                f"variant={slide.get('variant', '-')} "
                f"intent={slide.get('slide_intent', '-')} "
                f"title={str(slide.get('title', ''))[:100]}"
            )
    return "\n".join(lines)


def _artifact_manifest_context(workspace: Path, limit: int) -> str:
    manifest_path = workspace / "assets" / "artifacts_manifest.json"
    if not manifest_path.exists():
        return "<no artifact manifest found at assets/artifacts_manifest.json>"
    if inspect_manifest is None:
        return "<artifact manifest exists, but inspect_artifact_manifest.py could not be imported>"
    try:
        report = inspect_manifest(workspace, manifest_path)  # type: ignore[misc]
    except Exception as exc:
        return f"<artifact manifest exists, but inspection failed: {exc}>"
    compact_report = {
        "manifest": report.get("manifest"),
        "manifest_version": report.get("manifest_version"),
        "generated_by": report.get("generated_by"),
        "analysis_summary": report.get("analysis_summary"),
        "analysis_summary_markdown": report.get("analysis_summary_markdown"),
        "rebuild_context": report.get("rebuild_context"),
        "output_count": report.get("output_count"),
        "alias_plan": report.get("alias_plan"),
        "selection_templates": report.get("selection_templates"),
        "commands": report.get("commands"),
        "agent_next_steps": report.get("agent_next_steps"),
    }
    return _compact_json(compact_report, limit)


PROMPT = """\
You are the data/evidence analysis scout for a PowerPoint deck workspace. Your
job is to inspect the available data/evidence and return structured analysis
recommendations before the author finalizes figures, tables, and claims.

Read these refs first. They are authoritative:
- {planning_schema}
- {outline_schema}
- {subagent_patterns}
- {reference_script_patterns}

Rules:
- Do not edit files.
- Do not invent values. If a value is not in the data, leave it as an open
  question or propose the exact analysis needed.
- If you compute a value, include file path, columns/fields used, method, and
  assumptions.
- Use the source inventory fingerprints below. When a file entry includes
  `source_sha256` and `source_size_bytes`, copy those values into computed
  findings and reusable artifact metadata. If a source is too large to hash in
  the prompt, tell the main agent which deterministic script or build report
  should capture the fingerprint before final delivery.
- If a computation or figure will be reused, recommend a deterministic
  workspace script and output paths instead of one-off manual analysis.
- If the available data is a simple CSV/TSV/XLSX/JSON/Parquet/Feather table or
  Excel workbook, say whether the main agent should start with
  `python3 scripts/build_workspace.py --workspace <deck> --fast-first-pass`
  or the separate
  `python3 scripts/scaffold_figure_artifacts.py --workspace <deck> --run --bind-outline`
  path, then edit `assets/make_figures.py` for the real analysis choices.
  The scaffold scans Excel workbooks sheet-by-sheet, reads Parquet/Feather
  through pandas when a compatible engine is available, and emits small
  multi-series chart JSON plus compact summary-table JSON when aligned numeric
  columns exist; after staging, summary tables can be referenced as
  `table:<name>` in `table` or `lab-run-results` slides. If a columnar engine
  is missing, tell the main agent to preserve the skipped-file reason or
  convert the file to CSV/TSV before scaffolding.
  The scaffold also writes `assets/analysis_summary.json` and
  `assets/analysis_summary.md`; tell the main agent to inspect that summary
  before binding generated evidence objects into the outline.
- If `assets/artifacts_manifest.json` already exists, prefer a concrete
  `artifact_selection_recommendations.bindings` block that can be saved as a
  selection JSON and passed directly to
  `scripts/apply_artifact_manifest_bindings.py --selection`. Use only
  `output_id` and variants visible in the artifact manifest context. Include
  slide IDs, slide titles, interpretation/sidebar text, and source notes so the
  main agent can bind artifacts without reconstructing names from scratch.
  If the manifest context includes
  `presentation_skill_artifact_rebuild_context_v1`, treat its
  `commands.rebuild_figures`, `commands.inspect_manifest`,
  `commands.auto_select_lead`, `commands.auto_select_all`, and
  `commands.validate_planning` values as the source of truth for the
  main-agent handoff rather than recreating those commands by memory.
- For generated figures, recommend slide-ready exports: target variant,
  approximate target box, export size, DPI, minimum readable label sizes,
  tight bounding box, and whitespace trimming rule. If a multi-panel figure
  would make plots too small, recommend a larger image-sidebar figure or a
  split slide instead.
- For every reusable chart/table/figure artifact you recommend, include the
  analysis metadata the main agent must persist: source path, selected
  columns/fields, rows used, series count or point count when applicable,
  intended target box, figure size, DPI, and minimum axis-label font size.
  Use this metadata to keep design_brief.analysis_artifact_plan,
  analysis_artifact_plan.artifact_manifest, figure_export_contract, asset_plan
  chart/table entries, and the outline auditable after rebuilds.
- Also include a compact `slide_artifact_storyboard` when a slide structure is
  clear. Each item should bind slide ID, variant, output ID, artifact role,
  data source, script path, and readable layout targets so the main agent can
  reproduce why a figure/chart/table landed on that slide.
- Separate real data from synthetic/illustrative data.
- Prefer chart/table recommendations that map to supported variants:
  `scientific-figure`, `image-sidebar`, `lab-run-results`, `table`, `chart`,
  `stats`, and `comparison-2col`.
- End with a `main_agent_handoff` block that names the immediate next action,
  exact source files to edit, exact commands to run, and verification evidence
  to inspect. The main agent owns all file edits and QA; the scout only returns
  the plan. Include
  `python3 scripts/apply_data_analysis_handoff.py --workspace <deck> --handoff <deck>/data_analysis_handoff.json --report <deck>/data_analysis_handoff_apply_report.json`
  as the preferred command for applying deterministic bindings and evidence
  updates from your returned JSON.

Return ONLY valid JSON with this shape:

{{
  "recommended_workflow": {{
    "mode": "fast_first_pass | scaffold_then_edit | bind_existing_manifest | custom_analysis_script | no_data_work",
    "reason": "why this is the next deterministic path",
    "commands": [
      "python3 scripts/build_workspace.py --workspace <deck> --fast-first-pass"
    ],
    "requires_main_agent_edit": true
  }},
  "artifact_rebuild_context": {{
    "context_version": "presentation_skill_artifact_rebuild_context_v1 or none",
    "source": "existing_manifest | proposed_new_script | none",
    "producer_path": "assets/make_figures.py or none",
    "artifact_manifest": "assets/artifacts_manifest.json",
    "analysis_summary": "assets/analysis_summary.json",
    "commands": {{
      "rebuild_figures": "copy from existing rebuild_context.commands when available",
      "inspect_manifest": "copy from existing rebuild_context.commands when available",
      "auto_select_lead": "copy from existing rebuild_context.commands when available",
      "auto_select_all": "copy from existing rebuild_context.commands when available",
      "validate_planning": "copy from existing rebuild_context.commands when available"
    }},
    "source_paths": ["data/source.csv"],
    "output_paths": [
      "assets/figures/example.png",
      "assets/charts/example.json",
      "assets/tables/example_summary.json"
    ]
  }},
  "data_inventory": [
    {{
      "path": "absolute path",
      "workspace_relative_path": "data/source.csv",
      "status": "usable | missing | unclear",
      "data_type": "csv | tsv | json | jsonl | xlsx | parquet | feather | table | figure | unknown",
      "source_sha256": "sha256 when known",
      "source_size_bytes": 0,
      "notes": "brief"
    }}
  ],
  "analysis_tasks": [
    {{
      "id": "task_id",
      "question": "what the deck needs to know",
      "method": "aggregation/model/filter/check to run",
      "inputs": ["path or evidence id"],
      "output": "metric/table/chart/figure",
      "priority": "high | medium | low"
    }}
  ],
  "computed_findings": [
    {{
      "id": "finding_id",
      "claim": "specific claim supported by the data",
      "value": "42",
      "unit": "%",
      "source_path": "absolute path",
      "source_sha256": "sha256 when known",
      "source_size_bytes": 0,
      "columns_or_fields": ["field_a", "field_b"],
      "rows_used": 0,
      "method": "exact method used",
      "used_on_slides": ["s3"],
      "confidence": 0.0
    }}
  ],
  "chart_or_table_recommendations": [
    {{
      "target_slide": "s3 or 3",
      "variant": "scientific-figure | lab-run-results | table | chart | stats | comparison-2col",
      "data_shape": "one sentence",
      "columns_or_series": ["field_a", "field_b"],
      "why_this_visual": "reason"
    }}
  ],
  "script_edit_plan": [
    {{
      "path": "assets/make_figures.py",
      "edit_target": "DATA_SPECS | transform rows | plot styling | summary table | manifest metadata",
      "required_change": "specific deterministic analysis/filter/statistic/export change",
      "outputs_affected": ["assets/figures/example.png"],
      "why": "reason this cannot stay as the scaffold default"
    }}
  ],
  "artifact_selection_recommendations": {{
    "selection_file": "artifact_selections.scout.json",
    "apply_command": "python3 scripts/apply_artifact_manifest_bindings.py --workspace <deck> --selection <deck>/artifact_selections.scout.json --report <deck>/build/artifact_manifest_apply.json",
    "bindings": [
      {{
        "output_id": "manifest output id",
        "variant": "image-sidebar | chart | lab-run-results | table | scientific-figure",
        "slide_id": "stable_slide_id",
        "title": "slide title",
        "message": "claim or readout the slide should carry",
        "interpretation": "short interpretation text",
        "source_note": "source path, script, and method",
        "sidebar_sections": [
          {{"title": "Evidence", "body": ["source/provenance sentence"]}},
          {{"title": "Readout", "body": ["result sentence"]}}
        ]
      }}
    ]
  }},
  "outline_binding_plan": [
    {{
      "target_slide": "s3 or new stable slide_id",
      "variant": "image-sidebar | scientific-figure | lab-run-results | table | chart",
      "fields_to_set": {{
        "assets.hero_image": "image:<alias>",
        "assets.chart_data": "chart:<alias>",
        "tables": ["table:<alias>"],
        "sources": ["data/source.csv", "assets/make_figures.py"]
      }},
      "artifact_ids": ["artifact_id"],
      "evidence_ids": ["ev_id"],
      "readability_target": "target box, max rows/points, label sizes"
    }}
  ],
  "slide_artifact_storyboard": [
    {{
      "slide_id": "s3 or new stable slide_id",
      "variant": "image-sidebar | scientific-figure | lab-run-results | table | chart",
      "output_id": "manifest output id when known",
      "artifact_roles": ["figure", "chart", "table"],
      "data_source_paths": ["data/source.csv"],
      "script_edit_paths": ["assets/make_figures.py"],
      "quality_targets": {{
        "target_box": "5.0x3.3 in",
        "axis_label_min_pt": 8,
        "max_rows": 8
      }},
      "why_this_slide_structure": "one sentence tying source, artifact role, and readable layout together"
    }}
  ],
  "evidence_plan_updates": [
    {{
      "id": "ev_id",
      "claim": "claim to add or revise",
      "value": "value",
      "unit": "unit",
      "source_note": "file/method/provenance",
      "visual_use": "table | chart | figure | kpi | footer-source"
    }}
  ],
  "asset_plan_updates": [
    {{
      "id": "asset_id",
      "type": "local figure | chart_json | editable_table",
      "script_needed": "assets/make_figures.py or none",
      "outputs": ["assets/figures/fig_name.png", "assets/charts/chart_name.json", "assets/tables/table_name_summary.json"],
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json",
      "analysis_summary_markdown": "assets/analysis_summary.md",
      "caption": "caption/provenance",
      "used_on_slides": ["s3"],
      "analysis_metadata": {{
        "source_path": "absolute path",
        "source_sha256": "sha256 when known",
        "source_size_bytes": 0,
        "selected_columns": ["field_a", "field_b"],
        "rows_used": 0,
        "series_count": 0,
        "points": 0,
        "target_box": "5.0x3.3 in",
        "figure_size_inches": [6.4, 3.6],
        "figure_dpi": 180,
        "axis_label_min_pt": 8,
        "legend_pt": 8,
        "x_label_rotation": 0
      }}
    }}
  ],
  "artifact_registry_updates": [
    {{
      "id": "artifact_id",
      "path": "assets/figures/example.png",
      "producer": "assets/make_figures.py",
      "used_on_slides": ["s3"],
      "provenance": "source path, method, and caveat",
      "analysis_metadata": {{
        "artifact_role": "figure | chart_json | summary_table",
        "source_path": "absolute path",
        "source_sha256": "sha256 when known",
        "source_size_bytes": 0,
        "selected_columns": ["field_a", "field_b"],
        "rows_used": 0,
        "target_box": "5.0x3.3 in",
        "figure_size_inches": [6.4, 3.6],
        "figure_dpi": 180,
        "axis_label_min_pt": 8
      }}
    }}
  ],
  "figure_export_contract": {{
    "script": "assets/make_figures.py or none",
    "rerun_command": "python3 assets/make_figures.py",
    "outputs": [
      {{
        "path": "assets/figures/example.png",
        "target_slide": "s3 or 3",
        "target_variant": "image-sidebar | scientific-figure | lab-run-results | table | chart",
        "target_box": "5.0x3.3 in",
        "figure_size_inches": [6.4, 3.6],
        "figure_dpi": 180,
        "axis_label_min_pt": 8,
        "legend_pt": 8,
        "x_label_rotation": 0,
        "crop_rule": "bbox_inches='tight', small pad, optional trim_image_whitespace.py",
        "readability_note": "why labels/axes remain readable at slide size"
      }}
    ]
  }},
  "qa_readiness_plan": {{
    "source_checks": [
      "python3 scripts/validate_planning.py --workspace <deck>"
    ],
    "build_checks": [
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite"
    ],
    "specific_risks": [
      "figure exterior whitespace, dense chart labels, source-line footer length, stale source or producer fingerprints"
    ],
    "acceptance_evidence": [
      "assets/analysis_summary.json matches artifacts_manifest outputs",
      "build/build_workspace_report.json run.status is success",
      "QA report has zero overflow, overlap, design, and whitespace warnings"
    ]
  }},
  "main_agent_handoff": {{
    "immediate_next_action": "one concrete action for the main agent",
    "source_files_to_edit": [
      "assets/make_figures.py",
      "design_brief.json",
      "evidence_plan.json",
      "asset_plan.json",
      "outline.json"
    ],
    "commands_to_run": [
      "python3 scripts/apply_data_analysis_handoff.py --workspace <deck> --handoff <deck>/data_analysis_handoff.json --report <deck>/data_analysis_handoff_apply_report.json",
      "python3 scripts/build_workspace.py --workspace <deck> --fast-first-pass",
      "python3 scripts/apply_artifact_manifest_bindings.py --workspace <deck> --selection <deck>/artifact_selections.scout.json --report <deck>/build/artifact_manifest_apply.json",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite"
    ],
    "verification_evidence": [
      "assets/artifacts_manifest.json",
      "assets/analysis_summary.md",
      "build/artifact_manifest_apply.json",
      "build/build_workspace_report.json",
      "build/qa/report.json"
    ],
    "open_blocks": ["missing data, denominator, source, or dependency issue"]
  }},
  "quality_flags": [
    "data quality, missing denominator, small-N, synthetic marker, mismatch, or caveat"
  ],
  "open_questions": []
}}

--- User prompt ---

{user_prompt}

--- Candidate data files ---

{data_files}

--- Existing artifact manifest context ---

{artifact_manifest}

--- Workspace summary ---

{workspace_summary}

--- design_brief.json ---

{design_brief}

--- evidence_plan.json ---

{evidence_plan}

--- asset_plan.json ---

{asset_plan}

--- content_plan.json ---

{content_plan}

--- notes.md ---

{notes}
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a subagent prompt for deck data/evidence analysis."
    )
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument(
        "--user-prompt",
        default="",
        help="Original user request or brief to include as analysis context.",
    )
    parser.add_argument(
        "--data-path",
        action="append",
        default=[],
        help="Explicit data file or directory path. May be passed multiple times.",
    )
    parser.add_argument("--output", help="Write prompt to this file instead of stdout")
    parser.add_argument(
        "--truncate-json",
        type=int,
        default=12000,
        help="Max chars per JSON planning file included in the prompt.",
    )
    parser.add_argument(
        "--truncate-notes",
        type=int,
        default=4000,
        help="Max chars of notes.md included in the prompt.",
    )
    parser.add_argument(
        "--truncate-manifest",
        type=int,
        default=14000,
        help="Max chars of inspected artifact manifest context included in the prompt.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    explicit_files: list[str] = []
    for raw in args.data_path:
        path = _resolve_input_path(workspace, raw)
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix.lower() in DATA_SUFFIXES:
                    explicit_files.append(str(child))
        else:
            explicit_files.append(str(path))

    outline = _load_json(workspace / "outline.json")
    design_brief = _load_json(workspace / "design_brief.json")
    evidence_plan = _load_json(workspace / "evidence_plan.json")
    asset_plan = _load_json(workspace / "asset_plan.json")
    content_plan = _load_json(workspace / "content_plan.json")
    notes = _read_optional(workspace / "notes.md") or "<missing>"
    data_files = _candidate_data_files(workspace, explicit_files)

    repo_root = Path(__file__).resolve().parent.parent
    refs = {
        "planning_schema": str(repo_root / "references" / "planning_schema.md"),
        "outline_schema": str(repo_root / "references" / "outline_schema.md"),
        "subagent_patterns": str(repo_root / "references" / "subagent_patterns.md"),
        "reference_script_patterns": str(
            repo_root / "references" / "reference_script_patterns.md"
        ),
    }

    prompt = PROMPT.format(
        user_prompt=args.user_prompt or "<not provided>",
        data_files=_file_inventory(workspace, data_files),
        artifact_manifest=_artifact_manifest_context(workspace, args.truncate_manifest),
        workspace_summary=_outline_summary(outline),
        design_brief=_compact_json(design_brief, args.truncate_json),
        evidence_plan=_compact_json(evidence_plan, args.truncate_json),
        asset_plan=_compact_json(asset_plan, args.truncate_json),
        content_plan=_compact_json(content_plan, args.truncate_json),
        notes=_truncate(notes, args.truncate_notes),
        **refs,
    )

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(prompt, encoding="utf-8")
        print(f"Data-analysis prompt written to {output}", file=sys.stderr)
    else:
        print("=" * 72)
        print("DATA/EVIDENCE ANALYSIS SUBAGENT PROMPT (paste into an Explore agent)")
        print("=" * 72)
        print(prompt)
        print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
