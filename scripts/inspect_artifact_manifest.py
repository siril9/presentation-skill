#!/usr/bin/env python3
"""Emit slide-ready binding guidance from a generated artifact manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_if_changed(path: Path, payload: Any) -> bool:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _workspace_path(workspace: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (workspace / path).resolve()


def _relative_to_workspace(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _artifact_by_role(artifacts: Any) -> dict[str, dict[str, Any]]:
    roles: dict[str, dict[str, Any]] = {}
    if not isinstance(artifacts, list):
        return roles
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        role = str(artifact.get("role") or "").strip()
        if role and role not in roles:
            roles[role] = artifact
    return roles


def _artifact_binding(artifact: dict[str, Any], *, outline_field: str, role_label: str) -> dict[str, Any]:
    return {
        "artifact_id": str(artifact.get("id") or ""),
        "alias": str(artifact.get("alias") or ""),
        "path": str(artifact.get("path") or ""),
        "role": role_label,
        "outline_field": outline_field,
        "used_on_slides_update": "append the chosen outline slide_id to the matching artifact_registry entry",
    }


def _sources_for_output(output: dict[str, Any], *, generated_by: str) -> list[str]:
    metadata = output.get("analysis_metadata")
    source_path = str(output.get("source_path") or "").strip()
    if isinstance(metadata, dict):
        source_path = source_path or str(metadata.get("source_path") or "").strip()
    sources = [source_path] if source_path else []
    if generated_by and generated_by not in sources:
        sources.append(generated_by)
    return sources


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


def _selected_columns(plan: dict[str, Any]) -> list[str]:
    raw = plan.get("selected_columns")
    if not isinstance(raw, list):
        metadata = plan.get("analysis_metadata")
        raw = metadata.get("selected_columns") if isinstance(metadata, dict) else []
    return [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []


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


def _trim_text(text: str, *, max_chars: int) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_chars:
        return clean
    candidate = clean[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{candidate or clean[: max_chars - 1].rstrip()}..."


def _auto_selection_title(plan: dict[str, Any], variant: str) -> str:
    title = _compact_source_label(str(plan.get("title") or "").strip())
    source = _compact_source_label(
        str(plan.get("source_label") or plan.get("source_path") or "").strip()
    )
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


def _figure_quality_from_metadata(metadata: Any, readability_warnings: list[str]) -> dict[str, Any]:
    quality: dict[str, Any] = {
        "status": "unknown",
        "checked": False,
        "notes": [],
    }
    if not isinstance(metadata, dict):
        quality["notes"].append("Missing analysis_metadata; run or inspect the figure script before binding.")
        return quality
    whitespace = metadata.get("image_whitespace")
    if not isinstance(whitespace, dict):
        quality["notes"].append("Image whitespace was not recorded; rerun the generated figure script.")
        return quality
    checked = whitespace.get("checked") is True
    quality["checked"] = checked
    quality["image_whitespace"] = whitespace
    fraction = whitespace.get("exterior_fraction")
    if isinstance(fraction, (int, float)) and not isinstance(fraction, bool):
        quality["exterior_fraction"] = round(float(fraction), 4)
        quality["exterior_percent"] = round(float(fraction) * 100, 1)
    elif isinstance(whitespace.get("exterior_percent"), (int, float)) and not isinstance(whitespace.get("exterior_percent"), bool):
        quality["exterior_percent"] = round(float(whitespace["exterior_percent"]), 1)
    if isinstance(whitespace.get("content_bbox"), list):
        quality["content_bbox"] = whitespace.get("content_bbox")
    high_whitespace = whitespace.get("high_exterior_whitespace") is True
    if checked and high_whitespace:
        quality["status"] = "needs_trim"
        quality["notes"].append("Figure has high exterior whitespace; trim or regenerate before final binding.")
    elif checked:
        quality["status"] = "ok"
        if "exterior_percent" in quality:
            quality["notes"].append(f"Figure exterior whitespace {quality['exterior_percent']}%.")
    else:
        quality["status"] = "not_checked"
        reason = str(whitespace.get("reason") or "").strip()
        quality["notes"].append(reason or "Image whitespace check did not run.")
    if readability_warnings:
        quality["notes"].extend(readability_warnings[:2])
    return quality


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _layout_recommendation_from_values(
    *,
    available_variants: list[str],
    series_count: Any,
    points: Any,
    readability_warnings: list[str],
) -> dict[str, Any]:
    available = [variant for variant in available_variants if variant]
    if not available:
        return {}
    available_set = set(available)
    series_n = _as_int(series_count)
    point_n = _as_int(points)
    rationale: list[str] = []

    if readability_warnings and "image-sidebar" in available_set:
        lead_variant = "image-sidebar"
        density = "review"
        rationale.append("Readability notes favor the generated figure as the primary evidence view.")
    elif (point_n > 18 or series_n > 3) and "image-sidebar" in available_set:
        lead_variant = "image-sidebar"
        density = "dense"
        rationale.append("Dense data is safer as a generated figure with editable chart/table support.")
    elif point_n <= 8 and series_n <= 3 and "chart" in available_set:
        lead_variant = "chart"
        density = "compact"
        rationale.append("Compact aligned data can lead with an editable native chart.")
    elif "image-sidebar" in available_set:
        lead_variant = "image-sidebar"
        density = "standard"
        rationale.append("Generated figure gives the cleanest first readout for this artifact.")
    elif "chart" in available_set:
        lead_variant = "chart"
        density = "standard"
        rationale.append("Editable native chart is the strongest available evidence view.")
    else:
        lead_variant = available[0]
        density = "standard"
        rationale.append("Use the first available generated evidence view.")

    support_order = {
        "image-sidebar": ["lab-run-results", "chart", "table", "scientific-figure"],
        "chart": ["lab-run-results", "image-sidebar", "table", "scientific-figure"],
        "lab-run-results": ["chart", "image-sidebar", "table", "scientific-figure"],
        "table": ["chart", "image-sidebar", "lab-run-results", "scientific-figure"],
    }.get(lead_variant, ["chart", "image-sidebar", "lab-run-results", "table", "scientific-figure"])
    supporting = [variant for variant in support_order if variant in available_set and variant != lead_variant]
    supporting.extend(variant for variant in available if variant != lead_variant and variant not in supporting)
    priority_variants = [lead_variant, *supporting]
    return {
        "lead_variant": lead_variant,
        "supporting_variants": supporting,
        "priority_variants": priority_variants,
        "density": density,
        "rationale": rationale,
    }


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
    source_label = str(plan.get("source_label") or plan.get("source_path") or plan.get("id") or "").strip()
    primary_readout = _readout_primary(plan)
    readability_notes = _readability_notes(plan)
    layout_extras = _layout_extras(plan, variant)
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
            sidebar_sections.append(
                {"title": "QA", "body": readability_notes[:2]}
            )
        return {
            "subtitle": "Evidence figure with reproducible source metadata",
            "sidebar_body_font_size": 16,
            "interpretation": primary_readout
            or "Use this generated figure as the primary readout; revise the figure script for final analysis choices.",
            "sidebar_sections": sidebar_sections,
            **layout_extras,
        }
    if normalized == "chart":
        return {
            "subtitle": "Editable chart generated from the local artifact manifest",
            **({"interpretation": primary_readout} if primary_readout else {}),
            **layout_extras,
        }
    if normalized in {"lab-run-results", "table"}:
        return {
            "subtitle": "Editable summary table generated from local data",
            "interpretation": primary_readout
            or "Compact generated table keeps the run summary editable in PowerPoint.",
            **layout_extras,
        }
    return {}


def _selection_template(plan: dict[str, Any]) -> dict[str, Any]:
    output_id = str(plan.get("id") or "").strip()
    variants: list[str] = []
    snippets = plan.get("outline_field_snippets")
    if isinstance(snippets, list):
        for snippet in snippets:
            if not isinstance(snippet, dict):
                continue
            variant = str(snippet.get("variant") or "").strip()
            if variant and variant not in variants:
                variants.append(variant)
    recommendation = _layout_recommendation(plan)
    priority_variants = [
        str(item).strip()
        for item in recommendation.get("priority_variants", [])
        if str(item).strip()
    ] if recommendation else []
    if priority_variants:
        variants = [
            *[variant for variant in priority_variants if variant in variants],
            *[variant for variant in variants if variant not in priority_variants],
        ]
    bindings = []
    for variant in variants:
        suffix = _slide_suffix_for_variant(variant)
        bindings.append(
            {
                "output_id": output_id,
                "variant": variant,
                "slide_id": f"{output_id}_{suffix}",
                "title": _auto_selection_title(plan, variant),
                "message": str(plan.get("title") or output_id),
                **_auto_selection_extras(plan, variant),
            }
        )
    return {
        "output_id": output_id,
        "title": str(plan.get("title") or output_id),
        "variants": variants,
        "layout_recommendation": recommendation,
        "bindings": bindings,
    }


def _commands(workspace: Path, manifest_path: Path) -> dict[str, list[str]]:
    manifest_arg = _relative_to_workspace(workspace, manifest_path)
    selection_out = workspace / "artifact_selections.auto.json"
    apply_report = workspace / "build" / "artifact_manifest_apply.json"
    inspect_report = workspace / "build" / "artifact_manifest_inspection.json"
    return {
        "inspect": [
            "python3",
            "scripts/inspect_artifact_manifest.py",
            "--workspace",
            str(workspace),
            "--manifest",
            manifest_arg,
            "--report",
            str(inspect_report),
        ],
        "auto_select_all": [
            "python3",
            "scripts/apply_artifact_manifest_bindings.py",
            "--workspace",
            str(workspace),
            "--manifest",
            manifest_arg,
            "--auto-select",
            "--selection-out",
            str(selection_out),
            "--report",
            str(apply_report),
        ],
        "auto_select_recommended": [
            "python3",
            "scripts/apply_artifact_manifest_bindings.py",
            "--workspace",
            str(workspace),
            "--manifest",
            manifest_arg,
            "--auto-select",
            "--auto-select-mode",
            "recommended",
            "--selection-out",
            str(selection_out),
            "--report",
            str(apply_report),
        ],
        "auto_select_lead": [
            "python3",
            "scripts/apply_artifact_manifest_bindings.py",
            "--workspace",
            str(workspace),
            "--manifest",
            manifest_arg,
            "--auto-select",
            "--auto-select-mode",
            "lead",
            "--selection-out",
            str(selection_out),
            "--report",
            str(apply_report),
        ],
        "validate_planning": [
            "python3",
            "scripts/validate_planning.py",
            "--workspace",
            str(workspace),
        ],
        "strict_build": [
            "python3",
            "scripts/build_workspace.py",
            "--workspace",
            str(workspace),
            "--qa",
            "--fail-on-planning-warnings",
            "--fail-on-whitespace-warnings",
            "--overwrite",
        ],
    }


def _output_alias_plan(output: dict[str, Any], *, manifest_generated_by: str) -> dict[str, Any]:
    output_id = str(output.get("id") or "").strip()
    source_path = str(output.get("source_path") or "").strip()
    source_label = str(output.get("source_label") or source_path or output_id).strip()
    metadata = output.get("analysis_metadata")
    generated_by = manifest_generated_by
    if isinstance(metadata, dict):
        generated_by = str(metadata.get("generated_by") or generated_by).strip()
        source_path = source_path or str(metadata.get("source_path") or "").strip()
        source_label = source_label or str(metadata.get("source_label") or source_path or output_id).strip()
    readout_summary = output.get("readout_summary")
    if not isinstance(readout_summary, dict):
        readout_summary = metadata.get("readout_summary") if isinstance(metadata, dict) else {}
    if not isinstance(readout_summary, dict):
        readout_summary = {}
    readability_warnings = output.get("readability_warnings")
    if not isinstance(readability_warnings, list):
        readability_warnings = metadata.get("readability_warnings") if isinstance(metadata, dict) else []
    if not isinstance(readability_warnings, list):
        readability_warnings = []
    readability_warnings = [str(item).strip() for item in readability_warnings if str(item).strip()]
    figure_quality = _figure_quality_from_metadata(metadata, readability_warnings)
    selected_columns = output.get("selected_columns")
    if not isinstance(selected_columns, list):
        selected_columns = metadata.get("selected_columns") if isinstance(metadata, dict) else []
    selected_columns = [
        str(item).strip()
        for item in selected_columns
        if str(item).strip()
    ] if isinstance(selected_columns, list) else []

    roles = _artifact_by_role(output.get("artifacts"))
    figure = roles.get("figure", {})
    chart = roles.get("chart_json", {})
    table = roles.get("summary_table", {})
    image_alias = str(figure.get("alias") or "").strip()
    chart_alias = str(chart.get("alias") or "").strip()
    table_alias = str(table.get("alias") or "").strip()
    sources = _sources_for_output(output, generated_by=generated_by)

    artifact_bindings: list[dict[str, Any]] = []
    if figure:
        artifact_bindings.append(
            _artifact_binding(figure, outline_field="assets.hero_image", role_label="generated figure")
        )
    if chart:
        artifact_bindings.append(
            _artifact_binding(chart, outline_field="assets.chart_data", role_label="editable native chart JSON")
        )
    if table:
        artifact_bindings.append(
            _artifact_binding(table, outline_field="tables[] or table", role_label="editable summary table JSON")
        )

    outline_field_snippets: list[dict[str, Any]] = []
    if image_alias:
        figure_sources = sources
        outline_field_snippets.append(
            {
                "variant": "image-sidebar",
                "best_for": "dominant generated figure plus a concise interpretation sidebar",
                "fields": {
                    "variant": "image-sidebar",
                    "slide_intent": "evidence",
                    "visual_intent": "generated_figure",
                    "assets": {"hero_image": image_alias},
                    "caption": f"Generated from {source_label} by {generated_by}." if generated_by else f"Generated from {source_label}.",
                    "sources": figure_sources,
                    "evidence_needs": [output_id] if output_id else [],
                    "required_artifact_ids": [str(figure.get("id") or "")] if figure.get("id") else [],
                },
            }
        )
    if chart_alias:
        outline_field_snippets.append(
            {
                "variant": "chart",
                "best_for": "editable native chart when the audience may revise labels or values in PowerPoint",
                "fields": {
                    "variant": "chart",
                    "slide_intent": "evidence",
                    "visual_intent": "data",
                    "assets": {"chart_data": chart_alias},
                    "sources": [source_path] if source_path else sources,
                    "evidence_needs": [output_id] if output_id else [],
                    "required_artifact_ids": [str(chart.get("id") or "")] if chart.get("id") else [],
                },
            }
        )
    if table_alias:
        table_path = str(table.get("path") or "").strip()
        table_sources = [item for item in (table_path, source_path) if item]
        outline_field_snippets.append(
            {
                "variant": "lab-run-results",
                "best_for": "compact report table with summary statistics and source-line provenance",
                "fields": {
                    "variant": "lab-run-results",
                    "slide_intent": "evidence",
                    "visual_intent": "table",
                    "tables": [table_alias],
                    "sources": table_sources or sources,
                    "evidence_needs": [output_id] if output_id else [],
                    "required_artifact_ids": [str(table.get("id") or "")] if table.get("id") else [],
                },
            }
        )
    available_variants = [
        str(item.get("variant") or "").strip()
        for item in outline_field_snippets
        if isinstance(item, dict) and str(item.get("variant") or "").strip()
    ]
    layout_recommendation = _layout_recommendation_from_values(
        available_variants=available_variants,
        series_count=output.get("series_count", 0),
        points=output.get("points", 0),
        readability_warnings=readability_warnings,
    )

    return {
        "id": output_id,
        "title": str(output.get("title") or source_label or output_id),
        "source_path": source_path,
        "source_label": source_label,
        "series_count": output.get("series_count", 0),
        "points": output.get("points", 0),
        "selected_columns": selected_columns,
        "readout_summary": readout_summary,
        "readability_warnings": readability_warnings,
        "figure_quality": figure_quality,
        "layout_recommendation": layout_recommendation,
        "image_alias": image_alias,
        "chart_alias": chart_alias,
        "table_alias": table_alias,
        "artifact_bindings": artifact_bindings,
        "outline_field_snippets": outline_field_snippets,
        "recommended_variants": [
            {
                "variant": item["variant"],
                "use": item["best_for"],
                "layout_role": "lead"
                if layout_recommendation.get("lead_variant") == item["variant"]
                else "support",
                "fields": item["fields"],
            }
            for item in outline_field_snippets
        ],
        "binding_updates": {
            "analysis_artifact_plan": "after choosing slide ids, copy them into artifact_registry[*].used_on_slides for the matching artifact_id",
            "figure_export_contract": "after choosing a figure slide, set outputs[*].target_slide and keep target_variant/target_box aligned with that slide",
            "source_policy": "use compact source-line footers with short IDs; move long references to a final References slide",
        },
    }


def inspect_manifest(workspace: Path, manifest_path: Path) -> dict[str, Any]:
    payload = _read_json(manifest_path)
    if not isinstance(payload, dict):
        raise ValueError("artifact manifest root must be an object")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        raise ValueError("artifact manifest outputs must be a list")

    generated_by = str(payload.get("generated_by") or "").strip()
    alias_plan = [
        _output_alias_plan(output, manifest_generated_by=generated_by)
        for output in outputs
        if isinstance(output, dict)
    ]
    selection_templates = [_selection_template(plan) for plan in alias_plan]
    commands = _commands(workspace, manifest_path)
    return {
        "workspace": str(workspace),
        "manifest": _relative_to_workspace(workspace, manifest_path),
        "manifest_version": payload.get("manifest_version"),
        "generated_by": generated_by,
        "data_specs_sha256": payload.get("data_specs_sha256"),
        "analysis_summary": payload.get("analysis_summary"),
        "analysis_summary_markdown": payload.get("analysis_summary_markdown"),
        "rebuild_context": payload.get("rebuild_context")
        if isinstance(payload.get("rebuild_context"), dict)
        else {},
        "output_count": len(alias_plan),
        "alias_plan": alias_plan,
        "selection_templates": selection_templates,
        "commands": commands,
        "agent_next_steps": [
            "For a clean first pass, run commands.auto_select_lead; for the full figure/chart/table triplet, run commands.auto_select_all.",
            "For layout-guided ordering across all available variants, run commands.auto_select_recommended.",
            "For a custom subset, save one or more selection_templates[*].bindings entries to a selection file and run apply_artifact_manifest_bindings.py --selection.",
            "Revise generated titles, interpretation text, and sidebar notes in outline.json after binding.",
            "Run commands.validate_planning before commands.strict_build.",
        ],
    }


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=".", help="Deck workspace root.")
    parser.add_argument(
        "--manifest",
        default="assets/artifacts_manifest.json",
        help="Artifact manifest path, relative to the workspace by default.",
    )
    parser.add_argument("--report", help="Optional JSON report path.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace).expanduser().resolve()
    manifest_path = _workspace_path(workspace, args.manifest)
    if not manifest_path.exists():
        print(f"Error: artifact manifest not found: {manifest_path}", file=sys.stderr)
        return 1
    try:
        report = inspect_manifest(workspace, manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error: cannot inspect artifact manifest: {exc}", file=sys.stderr)
        return 1
    if args.report:
        _write_json_if_changed(Path(args.report).expanduser().resolve(), report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
