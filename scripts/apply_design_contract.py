#!/usr/bin/env python3
"""Apply a design-contract JSON packet to deck workspace source files.

`emit_design_contract_prompt.py` asks a main agent or scout to return a strict
JSON contract before outline authoring. This helper turns that contract into
durable workspace state: design_brief.json, content_plan.json,
evidence_plan.json, asset_plan.json, and notes.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from style_reference_catalog import preset_style_reference
from style_treatment_profiles import (
    RENDERER_TREATMENT_FIELDS,
    preset_treatment_profile,
    renderer_treatment_defaults_from_mix,
    renderer_treatment_summary,
)


NOTE_START = "<!-- deck-design-contract:start -->"
NOTE_END = "<!-- deck-design-contract:end -->"

ASSET_SECTIONS = (
    "images",
    "charts",
    "tables",
    "icons",
    "backgrounds",
    "generated_images",
)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _semantic_archetype_signature(item: dict[str, Any]) -> str:
    material = {
        "structure": item.get("structure"),
        "object_pattern": item.get("object_pattern"),
        "required_fields": item.get("required_fields") if isinstance(item.get("required_fields"), list) else [],
        "primary_variants": item.get("primary_variants") if isinstance(item.get("primary_variants"), list) else [],
        "title_layout": item.get("title_layout"),
        "footer_mode": item.get("footer_mode"),
        "content_goal": item.get("content_goal"),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _merge_unique(existing: list[Any], additions: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for item in [*existing, *additions]:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, dict) else str(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_named_entries(existing: list[Any], additions: list[Any]) -> list[Any]:
    merged: list[Any] = []
    positions: dict[str, int] = {}
    raw_seen: set[str] = set()
    for item in existing:
        if isinstance(item, dict) and _text(item.get("name")):
            key = _text(item.get("name")).lower()
            positions[key] = len(merged)
            merged.append(item)
            continue
        raw_key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, dict) else str(item)
        if raw_key in raw_seen:
            continue
        raw_seen.add(raw_key)
        merged.append(item)
    for item in additions:
        if isinstance(item, dict) and _text(item.get("name")):
            key = _text(item.get("name")).lower()
            if key in positions:
                merged[positions[key]] = item
            else:
                positions[key] = len(merged)
                merged.append(item)
            continue
        raw_key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, dict) else str(item)
        if raw_key in raw_seen:
            continue
        raw_seen.add(raw_key)
        merged.append(item)
    return merged


def _set_value(
    target: dict[str, Any],
    key: str,
    value: Any,
    *,
    preserve_existing: bool,
    touched: list[str],
    field_path: str,
) -> None:
    if not _non_empty(value):
        return
    if preserve_existing and _non_empty(target.get(key)):
        return
    if target.get(key) != value:
        target[key] = value
        touched.append(field_path)


def _merge_dict(
    target: dict[str, Any],
    updates: dict[str, Any],
    *,
    preserve_existing: bool,
    touched: list[str],
    base_path: str,
) -> None:
    for key, value in updates.items():
        if not _non_empty(value):
            continue
        path = f"{base_path}.{key}" if base_path else key
        if isinstance(value, dict):
            existing = target.get(key)
            if not isinstance(existing, dict) or (not preserve_existing and existing != value):
                if not isinstance(existing, dict) or not preserve_existing:
                    target[key] = dict(value)
                    touched.append(path)
                    continue
            _merge_dict(existing, value, preserve_existing=preserve_existing, touched=touched, base_path=path)
        else:
            _set_value(target, key, value, preserve_existing=preserve_existing, touched=touched, field_path=path)


def _source_policy_from(contract: dict[str, Any]) -> str:
    evidence = _as_dict(contract.get("evidence_and_assets"))
    explicit = _text(evidence.get("source_policy"))
    if explicit:
        return explicit
    continuity = _as_dict(contract.get("continuity_rules"))
    footer_rule = _text(continuity.get("source_footer_rule"))
    policies = [
        _text(item.get("source_policy"))
        for item in _as_list(_as_dict(contract.get("structure_blueprint")).get("slide_sequence"))
        if isinstance(item, dict) and _text(item.get("source_policy"))
    ]
    lowered = " | ".join([*policies, footer_rule]).lower()
    if "every factual" in lowered or "source every" in lowered:
        return "source every factual claim"
    if "cite key" in lowered:
        return "cite key claims"
    return footer_rule or (policies[0] if policies else "")


def _renderer_treatment_base_defaults(style_system: dict[str, Any]) -> dict[str, str]:
    explicit = _as_dict(style_system.get("renderer_treatment_defaults"))
    if explicit:
        return {
            field: _text(explicit.get(field))
            for field in RENDERER_TREATMENT_FIELDS
            if _text(explicit.get(field))
        }
    mix = _as_dict(style_system.get("style_mix_matrix"))
    if mix:
        return renderer_treatment_defaults_from_mix(
            _text(style_system.get("style_preset")) or "executive-clinical",
            mix,
        )
    profile_defaults = _as_dict(
        _as_dict(style_system.get("preset_treatment_profile")).get("renderer_treatment_defaults")
    )
    return {
        field: _text(profile_defaults.get(field))
        for field in RENDERER_TREATMENT_FIELDS
        if _text(profile_defaults.get(field))
    }


def _renderer_treatment_values(style_system: dict[str, Any]) -> dict[str, str]:
    footer = _as_dict(style_system.get("footer_system"))
    title = _as_dict(style_system.get("title_slide_system"))
    figure_table = _as_dict(style_system.get("figure_table_system"))
    table = _as_dict(style_system.get("table_system"))
    chart = _as_dict(style_system.get("chart_system"))
    stats = _as_dict(style_system.get("stats_system"))
    matrix = _as_dict(style_system.get("matrix_system"))
    summary = _as_dict(style_system.get("summary_callout_system"))
    values = {
        field: _text(value)
        for field, value in _renderer_treatment_base_defaults(style_system).items()
        if _text(value)
    }
    for field, value in {
        "title_layout": title.get("title_layout") or style_system.get("title_layout"),
        "footer_mode": footer.get("footer_mode") or style_system.get("footer_mode"),
        "chart_treatment": chart.get("chart_treatment") or style_system.get("chart_treatment"),
        "table_treatment": table.get("table_treatment")
        or figure_table.get("table_treatment")
        or style_system.get("table_treatment"),
        "figure_table_treatment": figure_table.get("figure_table_treatment")
        or style_system.get("figure_table_treatment"),
        "stats_mode": stats.get("stats_mode") or style_system.get("stats_mode"),
        "matrix_mode": matrix.get("matrix_mode") or style_system.get("matrix_mode"),
        "summary_callout_mode": summary.get("summary_callout_mode")
        or style_system.get("summary_callout_mode"),
    }.items():
        if _text(value):
            values[field] = _text(value)
    return {
        field: _text(values.get(field))
        for field in RENDERER_TREATMENT_FIELDS
        if _text(values.get(field))
    }


def _renderer_treatments(style_system: dict[str, Any]) -> dict[str, Any]:
    header = _as_dict(style_system.get("header_system"))
    footer = _as_dict(style_system.get("footer_system"))
    title = _as_dict(style_system.get("title_slide_system"))
    section = _as_dict(style_system.get("section_system"))
    values = _renderer_treatment_values(style_system)
    defaults = _renderer_treatment_base_defaults(style_system)
    summary = renderer_treatment_summary(values)
    footer_mode = values.get("footer_mode") or footer.get("footer_mode")
    return {
        "style_preset": style_system.get("style_preset"),
        "renderer_treatment_fields": list(RENDERER_TREATMENT_FIELDS),
        "renderer_treatment_defaults": defaults,
        "renderer_treatment_signature": summary["signature"],
        "header_mode": header.get("header_mode"),
        "header_variant": header.get("header_variant"),
        "header_variants": header.get("header_variants"),
        "footer_mode": footer_mode,
        "footer_page_numbers": footer.get("footer_page_numbers")
        if _non_empty(footer.get("footer_page_numbers"))
        else footer_mode == "source-line",
        "footer_source_label": footer.get("footer_source_label"),
        "footer_refs_label": footer.get("footer_refs_label"),
        "title_layout": values.get("title_layout") or title.get("title_layout"),
        "title_motif": title.get("title_motif"),
        "section_motif": section.get("section_motif"),
        "figure_table_treatment": values.get("figure_table_treatment"),
        "table_treatment": values.get("table_treatment"),
        "chart_treatment": values.get("chart_treatment"),
        "stats_mode": values.get("stats_mode"),
        "matrix_mode": values.get("matrix_mode"),
        "summary_callout_mode": values.get("summary_callout_mode"),
    }


def _slide_plan_from(sequence: list[Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for idx, item in enumerate(sequence, start=1):
        if not isinstance(item, dict):
            continue
        slide_id = _text(item.get("slide_id")) or f"s{idx}"
        plan.append(
            {
                "slide_id": slide_id,
                "role": _text(item.get("role")),
                "message": (
                    _text(item.get("message"))
                    or _text(item.get("purpose"))
                    or _text(item.get("visual_strategy"))
                    or _text(item.get("role"))
                ),
                "variant": _text(item.get("variant")),
                "treatment_key": _text(item.get("treatment_key")),
                "visual_strategy": _text(item.get("visual_strategy")),
                "evidence_needs": _as_list(item.get("evidence_needs")),
                "asset_needs": _as_list(item.get("required_assets")),
                "source_policy": _text(item.get("source_policy")),
            }
        )
    return plan


def _narrative_arc_from_slide_plan(slide_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[str]] = {"setup": [], "evidence": [], "implication": []}
    for idx, item in enumerate(slide_plan):
        slide_id = _text(item.get("slide_id")) or f"s{idx + 1}"
        role = _text(item.get("role")).lower()
        variant = _text(item.get("variant")).lower()
        if idx == 0 or role in {"title", "setup", "context", "opening"} or variant == "title":
            buckets["setup"].append(slide_id)
        elif role in {"decision", "recommendation", "implication", "close", "next-step", "next steps"}:
            buckets["implication"].append(slide_id)
        else:
            buckets["evidence"].append(slide_id)
    return [
        {
            "act": "setup",
            "purpose": "Frame the deck and establish the audience context.",
            "slides": buckets["setup"],
        },
        {
            "act": "evidence",
            "purpose": "Present the main proof, analysis, comparison, or figure sequence.",
            "slides": buckets["evidence"],
        },
        {
            "act": "implication",
            "purpose": "Close with the decision, recommendation, or next action.",
            "slides": buckets["implication"],
        },
    ]


def _replace_notes_section(existing: str, section: str) -> str:
    if NOTE_START in existing and NOTE_END in existing:
        before = existing.split(NOTE_START, 1)[0].rstrip()
        after = existing.split(NOTE_END, 1)[1].lstrip()
        parts = [part for part in (before, section.rstrip(), after.rstrip()) if part]
        return "\n\n".join(parts) + "\n"
    prefix = existing.rstrip()
    return (prefix + "\n\n" if prefix else "") + section.rstrip() + "\n"


def _compact_text_list(value: Any, *, limit: int = 6) -> str:
    items: list[str] = []
    for item in _as_list(value):
        text = _text(item)
        if text:
            items.append(text)
    if not items:
        return ""
    shown = items[:limit]
    suffix = f", +{len(items) - limit} more" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def _acceptance_evidence_from(contract: dict[str, Any]) -> list[Any]:
    qa = _as_dict(contract.get("qa_contract"))
    evidence: list[Any] = []
    for value in (
        contract.get("acceptance_evidence"),
        qa.get("acceptance_evidence"),
        qa.get("evidence_files"),
        qa.get("verification_evidence"),
    ):
        evidence = _merge_unique(evidence, _as_list(value))
    return evidence


def _append_style_mix_notes(lines: list[str], style_system: dict[str, Any]) -> None:
    reference = _as_dict(style_system.get("style_reference"))
    mix = _as_dict(style_system.get("style_mix_matrix"))
    if not mix and not reference:
        return
    pool_labels = (
        ("header_variant_pool", "Header variants"),
        ("title_layout_pool", "Title layouts"),
        ("section_motif_pool", "Section motifs"),
        ("timeline_mode_pool", "Timeline modes"),
        ("matrix_mode_pool", "Matrix modes"),
        ("stats_mode_pool", "Stats modes"),
        ("cards_mode_pool", "Card modes"),
        ("chart_treatment_pool", "Chart treatments"),
        ("table_treatment_pool", "Table treatments"),
        ("summary_callout_mode_pool", "Summary callouts"),
        ("footer_pool", "Footers"),
        ("figure_table_treatment_pool", "Figure/table treatments"),
    )
    lines.extend(["", "### Style Mix Ledger"])
    if reference:
        lines.append(f"- Style reference: `{_text(reference.get('reference_id'))}` / {_text(reference.get('reference_name'))}")
        style_dna = _text(reference.get("style_dna"))
        if style_dna:
            lines.append(f"- Reference DNA: {style_dna}")
        content_treatments = _as_dict(reference.get("content_treatments"))
        treatment_keys = [key for key in ("title", "comparison", "chart", "table", "figure", "dashboard", "decision", "references") if _text(content_treatments.get(key))]
        if treatment_keys:
            lines.append(f"- Reference treatment coverage: {', '.join(treatment_keys)}")
        playbook = _as_dict(reference.get("layout_playbook"))
        if playbook:
            playbook_version = _text(playbook.get("playbook_version"))
            preferred = _compact_text_list(playbook.get("preferred_variants"), limit=8)
            avoid = _compact_text_list(playbook.get("avoid_variants"), limit=6)
            treatment_archetypes = _as_dict(playbook.get("treatment_archetypes"))
            if playbook_version:
                lines.append(f"- Reference layout playbook: `{playbook_version}`")
            if preferred:
                lines.append(f"- Preferred variants: {preferred}")
            title_archetype = _as_dict(treatment_archetypes.get("title"))
            refs_archetype = _as_dict(treatment_archetypes.get("references"))
            if title_archetype.get("archetype_id"):
                lines.append(f"- Title archetype: `{_text(title_archetype.get('archetype_id'))}`")
            if refs_archetype.get("archetype_id"):
                lines.append(f"- References archetype: `{_text(refs_archetype.get('archetype_id'))}`")
            body_archetypes = [
                f"{key}=`{_text(_as_dict(value).get('archetype_id'))}`"
                for key, value in treatment_archetypes.items()
                if key not in {"title", "references"} and _text(_as_dict(value).get("archetype_id"))
            ]
            if body_archetypes:
                lines.append(f"- Body treatment archetypes: {', '.join(body_archetypes)}")
            if avoid:
                lines.append(f"- Avoid variants: {avoid}")
        motif = _as_dict(reference.get("structural_motif_library"))
        if motif:
            motif_version = _text(motif.get("motif_library_version"))
            background = _text(motif.get("background_structure"))
            motifs = _compact_text_list(motif.get("layout_motifs"), limit=6)
            if motif_version:
                lines.append(f"- Structural motif library: `{motif_version}`")
            if background:
                lines.append(f"- Background structure: {background}")
            if motifs:
                lines.append(f"- Layout motifs: {motifs}")
    if not mix:
        return
    mix_rule = _text(mix.get("mix_rule"))
    if mix_rule:
        lines.append(f"- Mix rule: {mix_rule}")
    do_not_mix = _compact_text_list(mix.get("do_not_mix"), limit=4)
    if do_not_mix:
        lines.append(f"- Do not mix: {do_not_mix}")
    for key, label in pool_labels:
        summary = _compact_text_list(mix.get(key))
        if summary:
            lines.append(f"- {label}: {summary}")


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list) and value:
            return value
    return []


def _reproducibility_contract_from(
    contract: dict[str, Any],
    *,
    style_system: dict[str, Any],
    structure: dict[str, Any],
    evidence: dict[str, Any],
    choice_resolution: dict[str, Any],
) -> dict[str, Any]:
    explicit = _as_dict(contract.get("reproducibility_contract"))
    replay = dict(explicit) if explicit else {}
    mix = _as_dict(style_system.get("style_mix_matrix"))
    header = _as_dict(style_system.get("header_system"))
    title = _as_dict(style_system.get("title_slide_system"))
    footer = _as_dict(style_system.get("footer_system"))
    figure_table = _as_dict(style_system.get("figure_table_system"))
    chart = _as_dict(style_system.get("chart_system"))
    style_reference = _as_dict(style_system.get("style_reference"))
    style_atom_context = _as_dict(style_system.get("style_atom_context"))
    style_atom_composition = _as_dict(style_system.get("style_atom_composition"))
    artifact_plan = _as_dict(evidence.get("analysis_artifact_plan"))
    figure_contract = _as_dict(evidence.get("figure_export_contract"))
    renderer_defaults = _renderer_treatment_base_defaults(style_system)
    renderer_values = _renderer_treatment_values(style_system)
    renderer_signature = renderer_treatment_summary(renderer_values)["signature"]

    def fill(key: str, value: Any) -> None:
        if _non_empty(value) and not _non_empty(replay.get(key)):
            replay[key] = value

    stable_id = _text(contract.get("stable_prompt_id")) or _text(style_system.get("style_seed"))
    style_seed = _text(style_system.get("style_seed")) or stable_id
    fill("contract_version", "deck_reproducibility_contract_v1")
    fill("stable_prompt_id", stable_id)
    fill("style_seed", style_seed)
    fill("choice_source", _text(choice_resolution.get("answered_by")) or "design_contract")
    fill("renderer", "pptxgenjs")
    fill("renderer_treatment_signature", renderer_signature)
    fill(
        "locked_design_fields",
        [
            "style_system.style_preset",
            "style_system.background_system",
            "style_system.style_mix_matrix",
            "style_system.renderer_treatment_signature",
            "structure_blueprint.slide_sequence",
            "evidence_and_assets.analysis_artifact_plan",
            "slide_quality_contract",
            "readability_contract",
            "qa_contract",
        ],
    )
    replay_inputs = dict(_as_dict(replay.get("replay_inputs")))
    for key, value in {
        "design_contract": "design_contract.json",
        "deck_start_packet": "deck_start_packet.json",
        "intake_answers": "intake_answers.json",
        "artifact_manifest": artifact_plan.get("artifact_manifest"),
        "analysis_summary": artifact_plan.get("analysis_summary"),
        "reference_pptx_style_fragment": "style_extract_design_brief.json",
        "atom_workflow_context": "deck_start_packet.json:atom_workflow_context"
        if style_atom_context
        else "",
    }.items():
        if _non_empty(value) and not _non_empty(replay_inputs.get(key)):
            replay_inputs[key] = value
    if replay_inputs:
        replay["replay_inputs"] = replay_inputs

    structural_motif = _as_dict(style_reference.get("structural_motif_library"))
    style_metric_profile = _as_dict(style_reference.get("style_metric_profile"))
    layout_playbook = _as_dict(style_reference.get("layout_playbook"))
    treatment_archetypes = _as_dict(layout_playbook.get("treatment_archetypes"))
    title_archetype = _as_dict(treatment_archetypes.get("title"))
    refs_archetype = _as_dict(treatment_archetypes.get("references"))
    treatment_archetype_ids = {
        str(key): _text(_as_dict(value).get("archetype_id"))
        for key, value in treatment_archetypes.items()
        if _text(_as_dict(value).get("archetype_id"))
    }
    treatment_archetype_signatures = {
        str(key): _text(_as_dict(value).get("archetype_signature"))
        for key, value in treatment_archetypes.items()
        if _text(_as_dict(value).get("archetype_signature"))
    }
    treatment_archetype_semantic_signatures = {
        str(key): _text(_as_dict(value).get("semantic_signature"))
        or _semantic_archetype_signature(_as_dict(value))
        for key, value in treatment_archetypes.items()
        if _text(_as_dict(value).get("archetype_id"))
    }
    style_replay = dict(_as_dict(replay.get("style_replay")))
    for key, value in {
        "style_preset": style_system.get("style_preset"),
        "palette_key": style_system.get("palette_key"),
        "background_system": style_system.get("background_system"),
        "header_variant": header.get("header_variant"),
        "footer_mode": renderer_values.get("footer_mode") or footer.get("footer_mode"),
        "title_layout": renderer_values.get("title_layout") or title.get("title_layout"),
        "chart_treatment": renderer_values.get("chart_treatment") or chart.get("chart_treatment"),
        "table_treatment": renderer_values.get("table_treatment"),
        "figure_table_treatment": renderer_values.get("figure_table_treatment")
        or figure_table.get("figure_table_treatment"),
        "stats_mode": renderer_values.get("stats_mode"),
        "matrix_mode": renderer_values.get("matrix_mode"),
        "summary_callout_mode": renderer_values.get("summary_callout_mode"),
        "renderer_treatment_fields": list(RENDERER_TREATMENT_FIELDS),
        "renderer_treatment_defaults": renderer_defaults,
        "renderer_treatment_signature": renderer_signature,
        "mix_rule": mix.get("mix_rule"),
        "style_reference_id": style_reference.get("reference_id"),
        "style_reference_name": style_reference.get("reference_name"),
        "style_reference_dna": style_reference.get("style_dna"),
        "structural_motif_library_version": structural_motif.get("motif_library_version"),
        "structural_motif_signature": structural_motif.get("motif_signature"),
        "background_structure": structural_motif.get("background_structure"),
        "layout_motifs": structural_motif.get("layout_motifs"),
        "style_metric_profile_version": style_metric_profile.get("metric_profile_version"),
        "style_metric_signature": style_metric_profile.get("metric_signature"),
        "density_level": style_metric_profile.get("density_level"),
        "whitespace_ratio_target": style_metric_profile.get("whitespace_ratio_target"),
        "body_words_per_content_slide": style_metric_profile.get("body_words_per_content_slide"),
        "max_primary_objects": style_metric_profile.get("max_primary_objects"),
        "visual_hierarchy": style_metric_profile.get("visual_hierarchy"),
        "evidence_object_mix": style_metric_profile.get("evidence_object_mix"),
        "source_burden": style_metric_profile.get("source_burden"),
        "footer_posture": style_metric_profile.get("footer_posture"),
        "style_reference_layout_playbook_version": layout_playbook.get("playbook_version"),
        "style_reference_preferred_variants": layout_playbook.get("preferred_variants"),
        "title_archetype_id": title_archetype.get("archetype_id"),
        "title_archetype_signature": title_archetype.get("archetype_signature"),
        "references_archetype_id": refs_archetype.get("archetype_id"),
        "references_archetype_signature": refs_archetype.get("archetype_signature"),
        "treatment_archetype_ids": treatment_archetype_ids,
        "treatment_archetype_signatures": treatment_archetype_signatures,
        "treatment_archetype_semantic_signatures": treatment_archetype_semantic_signatures,
        "atom_composition": style_atom_composition,
        "atom_target_family": style_atom_context.get("target_family"),
        "atom_selection_basis": style_atom_context.get("selection_basis"),
        "atom_preferred_variants": style_system.get("style_atom_preferred_variants"),
        "atom_narrative_arc": style_system.get("style_atom_narrative_arc"),
    }.items():
        if _non_empty(value) and not _non_empty(style_replay.get(key)):
            style_replay[key] = value
    pool_sources = {
        "header_variant_pool": _first_list(mix.get("header_variant_pool"), header.get("header_variants")),
        "title_layout_pool": _first_list(mix.get("title_layout_pool")),
        "footer_pool": _first_list(mix.get("footer_pool")),
        "chart_treatment_pool": _first_list(mix.get("chart_treatment_pool")),
        "table_treatment_pool": _first_list(mix.get("table_treatment_pool")),
        "figure_table_treatment_pool": _first_list(mix.get("figure_table_treatment_pool")),
    }
    for key, value in pool_sources.items():
        if value and not _non_empty(style_replay.get(key)):
            style_replay[key] = value
    if not _non_empty(style_replay.get("variation_boundaries")):
        style_replay["variation_boundaries"] = [
            "Rotate only supported treatment pools from style_seed.",
            "Keep preset, background system, source/footer policy, and evidence layout locked inside the deck.",
        ]
    if style_replay:
        replay["style_replay"] = style_replay
    if style_reference and not isinstance(replay.get("style_reference"), dict):
        replay["style_reference"] = style_reference

    sequence = _as_list(structure.get("slide_sequence"))
    structure_replay = dict(_as_dict(replay.get("structure_replay")))
    recipe_library = _as_dict(style_reference.get("content_recipe_library"))
    fill_target = structure.get("target_slide_count") or len(sequence)
    for key, value in {
        "target_slide_count": fill_target,
        "slide_variant_mix": [
            _text(item.get("variant"))
            for item in sequence
            if isinstance(item, dict) and _text(item.get("variant"))
        ],
        "content_recipe_library_version": recipe_library.get("library_version"),
        "content_recipe_signatures": recipe_library.get("recipe_signatures"),
        "structural_motif_library_version": structural_motif.get("motif_library_version"),
        "structural_motif_signature": structural_motif.get("motif_signature"),
        "structural_content_object_rules": structural_motif.get("content_object_rules"),
        "evidence_anchor_rule": "Every evidence/data slide needs a visible chart, table, figure, image, or structured comparison anchor.",
        "white_space_rule": "Choose slide variants that fit the actual evidence shape; do not leave awkward sparse regions.",
        "style_reference_opening_sequence": layout_playbook.get("opening_sequence"),
        "style_reference_content_rules": layout_playbook.get("content_rules"),
        "style_reference_treatment_archetypes": treatment_archetypes,
        "treatment_archetype_semantic_signatures": treatment_archetype_semantic_signatures,
    }.items():
        if _non_empty(value) and not _non_empty(structure_replay.get(key)):
            structure_replay[key] = value
    if structure_replay:
        replay["structure_replay"] = structure_replay

    artifact_replay = dict(_as_dict(replay.get("artifact_replay")))
    figure_scripts = _first_list(artifact_plan.get("figure_scripts"))
    fallback_figure_script = _text(figure_contract.get("script")) or (
        _text(figure_scripts[0]) if figure_scripts else ""
    )
    for key, value in {
        "local_data_needed": evidence.get("local_data_needed"),
        "artifact_manifest": artifact_plan.get("artifact_manifest"),
        "analysis_summary": artifact_plan.get("analysis_summary"),
        "analysis_summary_markdown": artifact_plan.get("analysis_summary_markdown"),
        "figure_script": fallback_figure_script,
        "rebuild_commands": _first_list(
            artifact_plan.get("rebuild_commands"),
            [figure_contract.get("rerun_command")] if _text(figure_contract.get("rerun_command")) else [],
        ),
    }.items():
        if _non_empty(value) and not _non_empty(artifact_replay.get(key)):
            artifact_replay[key] = value
    if artifact_replay:
        replay["artifact_replay"] = artifact_replay

    fill(
        "replay_commands",
        [
            "python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json",
            "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
            "python3 scripts/report_delivery_readiness.py --workspace <deck>",
        ],
    )
    fill(
        "acceptance_evidence",
        [
            "design_contract_apply_report.json",
            "build/workspace_readiness.json",
            "build/build_workspace_report.json",
            "build/delivery_readiness.json",
        ],
    )
    return replay


def _slide_quality_contract_from(
    contract: dict[str, Any],
    *,
    evidence: dict[str, Any],
    readability_contract: dict[str, Any],
    qa_contract: dict[str, Any],
) -> dict[str, Any]:
    explicit = _as_dict(contract.get("slide_quality_contract"))
    quality = dict(explicit) if explicit else {}
    if not quality:
        quality = {
            "contract_version": "slide_quality_contract_v1",
            "source": "derived_from_design_contract_fields",
        }
    elif not _text(quality.get("contract_version")):
        quality["contract_version"] = "slide_quality_contract_v1"

    if readability_contract and not isinstance(quality.get("readability_targets"), dict):
        quality["readability_targets"] = {
            key: readability_contract.get(key)
            for key in (
                "min_title_pt",
                "min_body_pt",
                "min_caption_pt",
                "chart_label_min_pt",
                "footer_reserved_inches",
                "max_title_lines",
                "max_slide_text_lines",
                "max_slide_words",
                "max_slide_chars",
            )
            if readability_contract.get(key) not in (None, "", [], {})
        }

    layout_targets = _as_dict(quality.get("layout_targets"))
    if readability_contract and not _non_empty(layout_targets.get("fail_on_awkward_whitespace")):
        layout_targets["fail_on_awkward_whitespace"] = bool(
            _text(readability_contract.get("whitespace_rule"))
        )
    if readability_contract and not _non_empty(layout_targets.get("source_footer_rule")):
        footer_rule = _text(_as_dict(contract.get("continuity_rules")).get("source_footer_rule"))
        if footer_rule:
            layout_targets["source_footer_rule"] = footer_rule
    if layout_targets:
        quality["layout_targets"] = layout_targets

    artifact_targets = _as_dict(quality.get("artifact_quality_targets"))
    if evidence and not _non_empty(artifact_targets.get("required_when_data_artifacts_active")):
        artifact_targets["required_when_data_artifacts_active"] = bool(
            evidence.get("local_data_needed") or _as_dict(evidence.get("analysis_artifact_plan"))
        )
    figure_contract = _as_dict(evidence.get("figure_export_contract"))
    if figure_contract and not _non_empty(artifact_targets.get("must_record")):
        artifact_targets["must_record"] = [
            "source data fingerprints",
            "producer script fingerprints",
            "figure/chart/table output paths",
            "target slide IDs and variants",
            "target figure box",
            "figure size and DPI",
            "axis/chart label font assumptions",
            "image whitespace measurement or trim rule",
            "rerun and inspect commands",
        ]
    if artifact_targets:
        quality["artifact_quality_targets"] = artifact_targets

    qa_gates = _as_dict(quality.get("qa_gates"))
    if qa_contract and not _non_empty(qa_gates.get("fail_on")):
        qa_gates["fail_on"] = _as_list(qa_contract.get("fail_on"))
    if qa_contract and not _non_empty(qa_gates.get("required_commands")):
        qa_gates["required_commands"] = _as_list(
            qa_contract.get("required_checks") or qa_contract.get("must_run")
        )
    if qa_gates:
        quality["qa_gates"] = qa_gates

    return quality


def _append_reproducibility_notes(lines: list[str], replay: dict[str, Any]) -> None:
    if not replay:
        return
    lines.extend(["", "### Reproducibility Replay"])
    for key, label in (
        ("contract_version", "Replay contract"),
        ("stable_prompt_id", "Stable prompt id"),
        ("style_seed", "Style seed"),
        ("renderer", "Renderer"),
    ):
        text = _text(replay.get(key))
        if text:
            lines.append(f"- {label}: `{text}`")
    style_replay = _as_dict(replay.get("style_replay"))
    if style_replay:
        signature = _text(style_replay.get("renderer_treatment_signature"))
        if signature:
            lines.append(f"- Renderer treatment signature: `{signature}`")
        for key, label in (
            ("style_preset", "Style preset"),
            ("background_system", "Background"),
            ("header_variant_pool", "Header pool"),
            ("footer_pool", "Footer pool"),
            ("chart_treatment_pool", "Chart pool"),
            ("table_treatment_pool", "Table pool"),
            ("figure_table_treatment_pool", "Figure/table pool"),
        ):
            value = style_replay.get(key)
            text = _compact_text_list(value) if isinstance(value, list) else _text(value)
            if text:
                lines.append(f"- {label}: {text}")
    commands = _compact_text_list(replay.get("replay_commands"), limit=3)
    if commands:
        lines.append(f"- Replay commands: {commands}")


def _append_slide_quality_notes(lines: list[str], slide_quality: dict[str, Any]) -> None:
    if not slide_quality:
        return
    lines.extend(["", "### Slide Quality Contract"])
    version = _text(slide_quality.get("contract_version"))
    if version:
        lines.append(f"- Quality contract: `{version}`")
    readability = _as_dict(slide_quality.get("readability_targets"))
    if readability:
        targets = []
        for key, label in (
            ("min_title_pt", "title"),
            ("min_body_pt", "body"),
            ("min_caption_pt", "caption"),
            ("chart_label_min_pt", "chart labels"),
            ("footer_reserved_inches", "footer reserve"),
        ):
            value = readability.get(key)
            if value not in (None, "", [], {}):
                targets.append(f"{label}={value}")
        if targets:
            lines.append(f"- Readability targets: {_compact_text_list(targets, limit=8)}")
    layout = _as_dict(slide_quality.get("layout_targets"))
    if layout:
        layout_bits = []
        for key, label in (
            ("evidence_anchor_required", "evidence anchor"),
            ("fail_on_awkward_whitespace", "fail whitespace"),
            ("sparse_slide_allowed_only_when_intentional", "intentional sparse only"),
        ):
            if key in layout:
                layout_bits.append(f"{label}={layout.get(key)}")
        source_rule = _text(layout.get("source_footer_rule"))
        if source_rule:
            layout_bits.append(f"source footer: {source_rule}")
        if layout_bits:
            lines.append(f"- Layout targets: {_compact_text_list(layout_bits, limit=6)}")
    artifacts = _as_dict(slide_quality.get("artifact_quality_targets"))
    if artifacts:
        lines.append(
            "- Artifact quality: "
            f"required_when_data_active={bool(artifacts.get('required_when_data_artifacts_active'))}"
        )
        must_record = _compact_text_list(artifacts.get("must_record"), limit=5)
        if must_record:
            lines.append(f"- Artifact fields to record: {must_record}")
    qa_gates = _as_dict(slide_quality.get("qa_gates"))
    if qa_gates:
        fail_on = _compact_text_list(qa_gates.get("fail_on"), limit=6)
        commands = _compact_text_list(qa_gates.get("required_commands"), limit=3)
        if fail_on:
            lines.append(f"- Quality fail on: {fail_on}")
        if commands:
            lines.append(f"- Quality commands: {commands}")


def _append_artifact_notes(lines: list[str], evidence: dict[str, Any]) -> None:
    plan = _as_dict(evidence.get("analysis_artifact_plan"))
    if not plan and not _non_empty(evidence.get("local_data_needed")):
        return
    lines.extend(["", "### Artifact Ledger"])
    if _non_empty(evidence.get("local_data_needed")):
        lines.append(f"- Local data needed: {evidence.get('local_data_needed')}")
    if _text(plan.get("artifact_manifest")):
        lines.append(f"- Manifest: {_text(plan.get('artifact_manifest'))}")
    if _text(plan.get("analysis_summary")):
        lines.append(f"- Analysis summary: {_text(plan.get('analysis_summary'))}")
    if _text(plan.get("analysis_summary_markdown")):
        lines.append(f"- Analysis summary markdown: {_text(plan.get('analysis_summary_markdown'))}")
    for key, label in (
        ("candidate_data_files", "Candidate data"),
        ("spreadsheet_inputs", "Spreadsheet inputs"),
        ("figure_scripts", "Figure scripts"),
        ("chart_json_outputs", "Chart JSON outputs"),
        ("table_outputs", "Table outputs"),
        ("rebuild_commands", "Rebuild commands"),
    ):
        summary = _compact_text_list(plan.get(key))
        if summary:
            lines.append(f"- {label}: {summary}")
    registry = [
        _text(item.get("id"))
        for item in _as_list(plan.get("artifact_registry"))
        if isinstance(item, dict) and _text(item.get("id"))
    ]
    if registry:
        lines.append(f"- Artifact registry IDs: {_compact_text_list(registry)}")


def _append_qa_execution_notes(lines: list[str], contract: dict[str, Any]) -> None:
    qa = _as_dict(contract.get("qa_contract"))
    subagent = _as_dict(contract.get("subagent_handoff"))
    execution = _as_dict(contract.get("agent_execution_plan"))
    acceptance_evidence = _acceptance_evidence_from(contract)
    if not qa and not subagent and not execution and not acceptance_evidence:
        return
    lines.extend(["", "### QA and Execution Ledger"])
    checks = _compact_text_list(qa.get("required_checks") or qa.get("must_run"))
    if checks:
        lines.append(f"- Required checks: {checks}")
    fail_on = _compact_text_list(qa.get("fail_on"))
    if fail_on:
        lines.append(f"- Fail on: {fail_on}")
    risks = _compact_text_list(qa.get("visual_risks_to_check"))
    if risks:
        lines.append(f"- Visual risks: {risks}")
    if qa.get("placeholder_checks") is True:
        lines.append("- Placeholder checks: true")
    acceptance = _compact_text_list(acceptance_evidence)
    if acceptance:
        lines.append(f"- Acceptance evidence: {acceptance}")
    if subagent:
        handoff_parts = []
        if subagent.get("ask_user_first") is True:
            handoff_parts.append("ask user first")
        for key in (
            "question_packet",
            "design_contract_scout",
            "content_research_scout",
            "data_analysis_scout",
            "style_content_router",
            "outline_critique",
            "visual_qa",
        ):
            text = _text(subagent.get(key))
            if text:
                handoff_parts.append(f"{key}: {text}")
        if handoff_parts:
            lines.append(f"- Subagent handoff: {_compact_text_list(handoff_parts, limit=5)}")
    phases = []
    for item in _as_list(execution.get("phases") or execution.get("steps")):
        if isinstance(item, dict):
            phase = _text(item.get("id")) or _text(item.get("phase")) or _text(item.get("name"))
            if phase:
                phases.append(phase)
        else:
            text = _text(item)
            if text:
                phases.append(text)
    if phases:
        lines.append(f"- Execution phases: {_compact_text_list(phases)}")
    commands = _compact_text_list(execution.get("commands"))
    if commands:
        lines.append(f"- Execution commands: {commands}")


def _append_choice_resolution_notes(lines: list[str], choice_resolution: dict[str, Any]) -> None:
    if not choice_resolution:
        return
    lines.extend(["", "### Choice Resolution Ledger"])
    version = _text(
        choice_resolution.get("contract_version")
        or choice_resolution.get("source_contract_version")
    )
    if version:
        lines.append(f"- Choice contract: {version}")
    answered_by = _text(choice_resolution.get("answered_by"))
    if answered_by:
        lines.append(f"- Answered by: {answered_by}")
    choices = []
    for item in _as_list(
        choice_resolution.get("resolved_choices")
        or choice_resolution.get("choice_ledger")
    ):
        if isinstance(item, dict):
            choice_id = _text(item.get("id"))
            answer = _text(item.get("answer") or item.get("selected") or item.get("route"))
            if choice_id and answer:
                choices.append(f"{choice_id}: {answer}")
            elif choice_id:
                choices.append(choice_id)
        else:
            text = _text(item)
            if text:
                choices.append(text)
    if choices:
        lines.append(f"- Resolved choices: {_compact_text_list(choices)}")
    selected_signature = _text(choice_resolution.get("selected_renderer_treatment_signature"))
    if selected_signature:
        lines.append(f"- Selected renderer treatment signature: `{selected_signature}`")
    routes = []
    for item in _as_list(choice_resolution.get("route_decisions")):
        if not isinstance(item, dict):
            continue
        route_id = _text(item.get("id"))
        if not route_id:
            continue
        active = item.get("active")
        if isinstance(active, bool):
            routes.append(f"{route_id}={'active' if active else 'inactive'}")
        else:
            routes.append(route_id)
    if routes:
        lines.append(f"- Route decisions: {_compact_text_list(routes)}")
    route_ledger = _as_dict(choice_resolution.get("route_decision_ledger"))
    route_ledger_items = _as_list(route_ledger.get("routes"))
    if route_ledger_items:
        route_summary = []
        for item in route_ledger_items:
            if not isinstance(item, dict):
                continue
            route_id = _text(item.get("id"))
            if not route_id:
                continue
            active = item.get("active")
            if isinstance(active, bool):
                route_summary.append(f"{route_id}={'active' if active else 'inactive'}")
            else:
                route_summary.append(route_id)
        if route_summary:
            version = _text(route_ledger.get("ledger_version"))
            version_text = f" ({version})" if version else ""
            lines.append(f"- Route ledger{version_text}: {_compact_text_list(route_summary, limit=8)}")
    locked_fields = _compact_text_list(
        choice_resolution.get("design_fields_locked")
        or choice_resolution.get("source_fields")
        or choice_resolution.get("contract_fields")
    )
    if locked_fields:
        lines.append(f"- Locked fields: {locked_fields}")


def _notes_section(
    contract: dict[str, Any],
    *,
    contract_path: Path,
    choice_resolution_override: dict[str, Any] | None = None,
    reproducibility_contract: dict[str, Any] | None = None,
    slide_quality_contract: dict[str, Any] | None = None,
) -> str:
    deck_identity = _as_dict(contract.get("deck_identity"))
    style_system = _as_dict(contract.get("style_system"))
    evidence = _as_dict(contract.get("evidence_and_assets"))
    slide_quality = (
        slide_quality_contract
        if isinstance(slide_quality_contract, dict)
        else _as_dict(contract.get("slide_quality_contract"))
    )
    choice_resolution = (
        choice_resolution_override
        if isinstance(choice_resolution_override, dict)
        else _as_dict(contract.get("choice_resolution"))
    )
    missing = _as_list(contract.get("missing_inputs"))
    assumptions = _as_list(contract.get("assumptions"))
    authoring = _as_list(contract.get("authoring_instructions"))
    lines = [
        NOTE_START,
        "## Deck Design Contract",
        "",
        f"- Contract file: `{contract_path}`",
        f"- Version: `{_text(contract.get('contract_version'))}`",
        f"- Stable prompt id: `{_text(contract.get('stable_prompt_id'))}`",
        f"- Working title: {_text(deck_identity.get('working_title'))}",
        f"- Design DNA: {_text(contract.get('design_dna'))}",
        f"- Style preset: {_text(style_system.get('style_preset'))}",
        f"- Style seed: `{_text(style_system.get('style_seed'))}`",
        f"- Proof burden: {_text(evidence.get('proof_burden'))}",
    ]
    _append_style_mix_notes(lines, style_system)
    _append_reproducibility_notes(lines, reproducibility_contract or {})
    _append_slide_quality_notes(lines, slide_quality)
    _append_artifact_notes(lines, evidence)
    _append_qa_execution_notes(lines, contract)
    _append_choice_resolution_notes(lines, choice_resolution)
    if missing:
        lines.extend(["", "### Missing Inputs"])
        for item in missing:
            if isinstance(item, dict):
                question = _text(item.get("question"))
                default = _text(item.get("default_if_unanswered"))
                why = _text(item.get("why_it_matters"))
                detail = f" - default: {default}" if default else ""
                why_text = f" ({why})" if why else ""
                lines.append(f"- {question}{why_text}{detail}")
            else:
                lines.append(f"- {item}")
    if assumptions:
        lines.extend(["", "### Assumptions"])
        for item in assumptions:
            lines.append(f"- {item}")
    if authoring:
        lines.extend(["", "### Authoring Instructions"])
        for item in authoring:
            lines.append(f"- {item}")
    lines.append(NOTE_END)
    return "\n".join(lines) + "\n"


def _route_ledger_status(route_ledger: dict[str, Any]) -> dict[str, bool]:
    routes = _as_list(route_ledger.get("routes"))
    return {
        _text(item.get("id")): bool(item.get("active"))
        for item in routes
        if isinstance(item, dict) and _text(item.get("id"))
    }


def _enrich_choice_resolution_from_seed(
    choice_resolution: dict[str, Any],
    design: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    seed = _as_dict(design.get("choice_resolution_seed"))
    if not seed:
        return choice_resolution, False
    enriched = dict(choice_resolution) if choice_resolution else {}
    changed = False
    for key in (
        "contract_version",
        "seed_kind",
        "source_contract_version",
        "stable_prompt_id",
        "answered_by",
        "resolved_choices",
        "route_decisions",
        "atom_composition",
        "design_fields_locked",
        "selected_renderer_treatment_signature",
        "replay_inputs",
    ):
        if key not in enriched and _non_empty(seed.get(key)):
            enriched[key] = seed.get(key)
            changed = True
    seed_route_ledger = _as_dict(seed.get("route_decision_ledger"))
    if seed_route_ledger and not isinstance(enriched.get("route_decision_ledger"), dict):
        enriched["route_decision_ledger"] = seed_route_ledger
        enriched["route_ledger_version"] = _text(seed_route_ledger.get("ledger_version"))
        status = _route_ledger_status(seed_route_ledger)
        enriched["route_ledger_active_routes"] = sorted(
            route_id for route_id, active in status.items() if active
        )
        changed = True
    return enriched, changed


def apply_contract(
    *,
    workspace: Path,
    contract_path: Path,
    preserve_existing: bool,
    dry_run: bool,
) -> dict[str, Any]:
    contract = _load_json(contract_path, {})
    if not isinstance(contract, dict):
        raise SystemExit("Design contract JSON must be an object.")
    if _text(contract.get("contract_version")) != "deck_design_contract_v1":
        raise SystemExit("Design contract must declare contract_version='deck_design_contract_v1'.")

    workspace = workspace.expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise SystemExit(f"Workspace not found: {workspace}")

    changed_files: list[str] = []
    touched_fields: dict[str, list[str]] = {}

    deck_identity = _as_dict(contract.get("deck_identity"))
    style_system = _as_dict(contract.get("style_system"))
    if not isinstance(style_system.get("preset_treatment_profile"), dict):
        style_system["preset_treatment_profile"] = preset_treatment_profile(
            _text(style_system.get("style_preset")) or "executive-clinical"
        )
    if not isinstance(style_system.get("style_reference"), dict):
        profile_reference = _as_dict(_as_dict(style_system.get("preset_treatment_profile")).get("style_reference"))
        style_system["style_reference"] = profile_reference or preset_style_reference(
            _text(style_system.get("style_preset")) or "executive-clinical"
        )
    else:
        reference = _as_dict(style_system.get("style_reference"))
        if not isinstance(reference.get("layout_playbook"), dict):
            fallback_reference = preset_style_reference(_text(style_system.get("style_preset")) or "executive-clinical")
            if isinstance(fallback_reference.get("layout_playbook"), dict):
                reference["layout_playbook"] = fallback_reference["layout_playbook"]
            if not isinstance(reference.get("publish_safety"), dict) and isinstance(fallback_reference.get("publish_safety"), dict):
                reference["publish_safety"] = fallback_reference["publish_safety"]
            if not isinstance(reference.get("style_source_intake"), dict) and isinstance(fallback_reference.get("style_source_intake"), dict):
                reference["style_source_intake"] = fallback_reference["style_source_intake"]
            if not isinstance(reference.get("style_metric_profile"), dict) and isinstance(fallback_reference.get("style_metric_profile"), dict):
                reference["style_metric_profile"] = fallback_reference["style_metric_profile"]
        if not isinstance(reference.get("content_recipe_library"), dict):
            fallback_reference = preset_style_reference(_text(style_system.get("style_preset")) or "executive-clinical")
            if isinstance(fallback_reference.get("content_recipe_library"), dict):
                reference["content_recipe_library"] = fallback_reference["content_recipe_library"]
        if not isinstance(reference.get("structural_motif_library"), dict):
            fallback_reference = preset_style_reference(_text(style_system.get("style_preset")) or "executive-clinical")
            if isinstance(fallback_reference.get("structural_motif_library"), dict):
                reference["structural_motif_library"] = fallback_reference["structural_motif_library"]
        if not isinstance(reference.get("style_metric_profile"), dict):
            fallback_reference = preset_style_reference(_text(style_system.get("style_preset")) or "executive-clinical")
            if isinstance(fallback_reference.get("style_metric_profile"), dict):
                reference["style_metric_profile"] = fallback_reference["style_metric_profile"]
        style_system["style_reference"] = reference
    style_system["renderer_treatment_fields"] = list(RENDERER_TREATMENT_FIELDS)
    style_system["renderer_treatment_defaults"] = _renderer_treatment_base_defaults(style_system)
    style_system["renderer_treatment_signature"] = renderer_treatment_summary(
        _renderer_treatment_values(style_system)
    )["signature"]
    structure = _as_dict(contract.get("structure_blueprint"))
    evidence = _as_dict(contract.get("evidence_and_assets"))
    continuity = _as_dict(contract.get("continuity_rules"))
    qa_contract = _as_dict(contract.get("qa_contract"))
    subagent_handoff = _as_dict(contract.get("subagent_handoff"))
    agent_execution_plan = _as_dict(contract.get("agent_execution_plan"))
    choice_resolution = _as_dict(contract.get("choice_resolution"))
    acceptance_evidence = _acceptance_evidence_from(contract)
    readability_contract = _as_dict(contract.get("readability_contract"))
    slide_quality_contract = _slide_quality_contract_from(
        contract,
        evidence=evidence,
        readability_contract=readability_contract,
        qa_contract=qa_contract,
    )

    design_path = workspace / "design_brief.json"
    design = _load_json(design_path, {})
    if not isinstance(design, dict):
        raise SystemExit(f"{design_path} must contain a JSON object.")
    existing_style_system = _as_dict(design.get("style_system"))
    for key in (
        "style_atom_context",
        "style_atom_composition",
        "style_atom_preferred_variants",
        "style_atom_narrative_arc",
    ):
        if not _non_empty(style_system.get(key)) and _non_empty(existing_style_system.get(key)):
            style_system[key] = existing_style_system.get(key)
    if not _non_empty(style_system.get("style_atom_composition")) and _non_empty(
        design.get("style_atom_composition")
    ):
        style_system["style_atom_composition"] = design.get("style_atom_composition")
    choice_resolution, choice_resolution_enriched = _enrich_choice_resolution_from_seed(
        choice_resolution,
        design,
    )
    if style_system.get("renderer_treatment_signature") and not _non_empty(
        choice_resolution.get("selected_renderer_treatment_signature")
    ):
        choice_resolution["selected_renderer_treatment_signature"] = style_system.get(
            "renderer_treatment_signature"
        )
    reproducibility_contract = _reproducibility_contract_from(
        contract,
        style_system=style_system,
        structure=structure,
        evidence=evidence,
        choice_resolution=choice_resolution,
    )
    design_touched: list[str] = []
    design_contract = {
        "contract_version": contract.get("contract_version"),
        "stable_prompt_id": contract.get("stable_prompt_id"),
        "contract_path": str(contract_path),
        "contract_sha256": _file_sha256(contract_path),
        "contract_bytes": contract_path.stat().st_size,
        "applied_by": "scripts/apply_design_contract.py",
        "user_request_summary": contract.get("user_request_summary"),
        "missing_inputs": contract.get("missing_inputs", []),
        "assumptions": contract.get("assumptions", []),
    }
    if choice_resolution:
        design_contract["choice_resolution"] = choice_resolution
    _merge_dict(
        design,
        {
            "design_contract": design_contract,
            "topic": deck_identity.get("working_title") or contract.get("user_request_summary"),
            "audience_posture": deck_identity.get("audience"),
            "format_promise": deck_identity.get("target_outcome") or contract.get("user_request_summary"),
            "design_dna": contract.get("design_dna"),
            "style_system": style_system,
            "style_atom_composition": style_system.get("style_atom_composition"),
            "renderer_treatments": _renderer_treatments(style_system),
            "style_mix_matrix": style_system.get("style_mix_matrix"),
            "title_page_concept": {
                "chosen_archetype": _as_dict(style_system.get("title_slide_system")).get("title_layout"),
                "dominant_element": deck_identity.get("working_title"),
                "supporting_element": _text(contract.get("user_request_summary")),
                "why_this_could_only_be_this_deck": deck_identity.get("target_outcome"),
            },
            "structure_strategy": {
                "primary_scaffold": f"{deck_identity.get('use_context', '')} / {contract.get('design_dna', '')}".strip(" /"),
                "allowed_variations": structure.get("allowed_variants"),
                "forbidden_variants": structure.get("forbidden_variants"),
                "slide_sequence": structure.get("slide_sequence"),
                "container_policy": "Use containers only when they clarify modular evidence or comparisons.",
                "rhythm_break_plan": "Use deliberate visual rhythm breaks only when the slide role or evidence shape asks for one.",
            },
            "design_modulation": {
                "accent_strategy": style_system.get("palette_key")
                or _as_dict(style_system.get("header_system")).get("header_rule_color"),
                "density_strategy": deck_identity.get("density"),
                "motif_strategy": _as_dict(style_system.get("title_slide_system")).get("title_motif"),
                "container_strategy": "evidence-first layouts before generic cards",
                "figure_table_treatment": _as_dict(style_system.get("figure_table_system")).get("figure_table_treatment"),
                "table_treatment": _as_dict(style_system.get("table_system")).get("table_treatment")
                or _as_dict(style_system.get("figure_table_system")).get("table_treatment"),
                "avoid": structure.get("forbidden_variants"),
            },
            "evidence_continuity": {
                "threads": continuity.get("recurring_tags"),
                "carry_forward_rule": continuity.get("carry_forward_rule"),
                "source_footer_rule": continuity.get("source_footer_rule"),
            },
            "analysis_artifact_plan": evidence.get("analysis_artifact_plan"),
            "figure_export_contract": evidence.get("figure_export_contract"),
            "reproducibility_contract": reproducibility_contract,
            "slide_quality_contract": slide_quality_contract,
            "readability_contract": readability_contract,
            "speed_contract": contract.get("speed_contract"),
            "qa_contract": qa_contract,
            "subagent_handoff": subagent_handoff,
            "agent_execution_plan": agent_execution_plan,
            "acceptance_evidence": acceptance_evidence,
        },
        preserve_existing=preserve_existing,
        touched=design_touched,
        base_path="design_brief",
    )
    if design_touched:
        touched_fields["design_brief.json"] = design_touched
    if _write_json_if_changed(design_path, design, dry_run=dry_run):
        changed_files.append(str(design_path))

    sequence = _as_list(structure.get("slide_sequence"))
    slide_plan = _slide_plan_from(sequence)
    narrative_arc = _narrative_arc_from_slide_plan(slide_plan) if slide_plan else []

    content_path = workspace / "content_plan.json"
    content = _load_json(content_path, {})
    if not isinstance(content, dict):
        raise SystemExit(f"{content_path} must contain a JSON object.")
    content_touched: list[str] = []
    _merge_dict(
        content,
        {
            "topic": deck_identity.get("working_title") or contract.get("user_request_summary"),
            "audience": deck_identity.get("audience"),
            "objective": deck_identity.get("target_outcome"),
            "thesis": contract.get("user_request_summary"),
            "narrative_arc": narrative_arc,
            "target_slide_count": structure.get("target_slide_count"),
            "slide_plan": slide_plan,
            "design_notes": {
                "design_dna": contract.get("design_dna"),
                "style_preset": style_system.get("style_preset"),
                "style_seed": style_system.get("style_seed"),
                "mix_rule": _as_dict(style_system.get("style_mix_matrix")).get("mix_rule"),
            },
        },
        preserve_existing=preserve_existing,
        touched=content_touched,
        base_path="content_plan",
    )
    if content_touched:
        touched_fields["content_plan.json"] = content_touched
    if _write_json_if_changed(content_path, content, dry_run=dry_run):
        changed_files.append(str(content_path))

    evidence_path = workspace / "evidence_plan.json"
    evidence_plan = _load_json(evidence_path, {})
    if not isinstance(evidence_plan, dict):
        raise SystemExit(f"{evidence_path} must contain a JSON object.")
    evidence_touched: list[str] = []
    _merge_dict(
        evidence_plan,
        {
            "topic": deck_identity.get("working_title") or contract.get("user_request_summary"),
            "source_policy": _source_policy_from(contract),
            "proof_burden": evidence.get("proof_burden"),
            "research_needed": evidence.get("research_needed"),
            "local_data_needed": evidence.get("local_data_needed"),
            "open_questions": [
                item.get("question") if isinstance(item, dict) else str(item)
                for item in _as_list(contract.get("missing_inputs"))
            ],
        },
        preserve_existing=preserve_existing,
        touched=evidence_touched,
        base_path="evidence_plan",
    )
    if evidence_touched:
        touched_fields["evidence_plan.json"] = evidence_touched
    if _write_json_if_changed(evidence_path, evidence_plan, dry_run=dry_run):
        changed_files.append(str(evidence_path))

    asset_path = workspace / "asset_plan.json"
    asset_plan = _load_json(asset_path, {})
    if not isinstance(asset_plan, dict):
        raise SystemExit(f"{asset_path} must contain a JSON object.")
    asset_touched: list[str] = []
    contract_asset_plan = _as_dict(evidence.get("asset_plan"))
    for section in ASSET_SECTIONS:
        additions = _as_list(contract_asset_plan.get(section))
        if not additions:
            asset_plan.setdefault(section, [])
            continue
        existing = _as_list(asset_plan.get(section))
        merged = _merge_named_entries(existing, additions)
        if merged != existing:
            asset_plan[section] = merged
            asset_touched.append(f"asset_plan.{section}")
    posture = asset_plan.get("asset_posture")
    if not isinstance(posture, dict):
        posture = {}
        asset_plan["asset_posture"] = posture
    _merge_dict(
        posture,
        {
            "proof_burden": evidence.get("proof_burden"),
            "research_needed": evidence.get("research_needed"),
            "local_data_needed": evidence.get("local_data_needed"),
            "background_system": style_system.get("background_system"),
            "source_policy": _source_policy_from(contract),
        },
        preserve_existing=preserve_existing,
        touched=asset_touched,
        base_path="asset_plan.asset_posture",
    )
    if asset_touched:
        touched_fields["asset_plan.json"] = asset_touched
    if _write_json_if_changed(asset_path, asset_plan, dry_run=dry_run):
        changed_files.append(str(asset_path))

    notes_path = workspace / "notes.md"
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    new_notes = _replace_notes_section(
        notes,
        _notes_section(
            contract,
            contract_path=contract_path,
            choice_resolution_override=choice_resolution,
            reproducibility_contract=reproducibility_contract,
            slide_quality_contract=slide_quality_contract,
        ),
    )
    if _write_text_if_changed(notes_path, new_notes, dry_run=dry_run):
        changed_files.append(str(notes_path))

    return {
        "workflow": "deck_design_contract_apply_v1",
        "workspace": str(workspace),
        "contract_path": str(contract_path),
        "stable_prompt_id": contract.get("stable_prompt_id"),
        "preserve_existing": preserve_existing,
        "dry_run": dry_run,
        "changed_files": changed_files,
        "touched_fields": touched_fields,
        "qa_contract_applied": bool(qa_contract),
        "slide_quality_contract_applied": bool(slide_quality_contract),
        "slide_quality_contract_version": _text(slide_quality_contract.get("contract_version")),
        "subagent_handoff_applied": bool(subagent_handoff),
        "agent_execution_plan_applied": bool(agent_execution_plan),
        "choice_resolution_applied": bool(choice_resolution),
        "choice_resolution_enriched_from_seed": bool(choice_resolution_enriched),
        "choice_resolution_route_ledger_applied": isinstance(
            choice_resolution.get("route_decision_ledger"),
            dict,
        ),
        "style_atom_composition_applied": isinstance(
            _as_dict(style_system.get("style_atom_composition")),
            dict,
        )
        and bool(_as_dict(style_system.get("style_atom_composition"))),
        "reproducibility_contract_applied": bool(reproducibility_contract),
        "acceptance_evidence_count": len(acceptance_evidence),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a deck design-contract JSON packet to workspace sources.")
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument("--contract", required=True, help="Design contract JSON returned by the design scout")
    parser.add_argument(
        "--preserve-existing",
        action="store_true",
        help="Only fill missing fields instead of replacing contract-owned scaffold defaults.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Emit the report without writing source files")
    parser.add_argument("--report", help="Optional path for a JSON apply report")
    args = parser.parse_args()

    report = apply_contract(
        workspace=Path(args.workspace),
        contract_path=Path(args.contract).expanduser().resolve(),
        preserve_existing=args.preserve_existing,
        dry_run=args.dry_run,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
