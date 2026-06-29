"""Shared atom-composition context for normal deck workflow prompts.

This module keeps the corpus atom layer available to deck-start,
design-contract, and style/content routing without making it a rigid template.
The returned packet is a reproducible seed: agents may accept it, refine it
through the strict JSON atom prompt, or skip it with a recorded reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apply_atom_composition import apply_composition
from style_atom_router import deterministic_composition, emit_composition_prompt
from style_reference_catalog import style_reference_mix_plan


DEFAULT_FAMILY = "executive-clinical"
DEFAULT_SLIDE_COUNT = 8


def _load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return str(value)


def _style_preset_from_workspace(workspace: Path | None, fallback: str = "") -> str:
    if workspace is None:
        return fallback or DEFAULT_FAMILY
    design_brief = _load_json(workspace / "design_brief.json")
    if isinstance(design_brief, dict):
        for container_key in ("style_system", "visual_system"):
            container = design_brief.get(container_key)
            if isinstance(container, dict):
                value = str(container.get("style_preset") or "").strip()
                if value:
                    return value
        value = str(design_brief.get("style_preset") or "").strip()
        if value:
            return value
    return fallback or DEFAULT_FAMILY


def _workspace_text(workspace: Path | None, limit: int = 5000) -> str:
    if workspace is None:
        return ""
    parts: list[str] = []
    for name in ("design_brief.json", "content_plan.json", "evidence_plan.json", "asset_plan.json", "outline.json"):
        value = _load_json(workspace / name)
        if value is not None:
            parts.append(_text_blob(value))
    notes = workspace / "notes.md"
    try:
        parts.append(notes.read_text(encoding="utf-8"))
    except OSError:
        pass
    text = " ".join(parts)
    return text[:limit]


def _infer_family(user_prompt: str, *, workspace: Path | None, style_preset: str = "") -> tuple[str, str]:
    workspace_preset = _style_preset_from_workspace(workspace, fallback=style_preset)
    prompt = str(user_prompt or "").strip()
    if prompt:
        mix = style_reference_mix_plan(prompt, limit=3)
        primary = mix.get("primary") if isinstance(mix.get("primary"), dict) else {}
        primary_preset = str(primary.get("style_preset") or "").strip()
        if primary_preset:
            return primary_preset, "style_reference_mix_plan.primary"
    return workspace_preset or DEFAULT_FAMILY, "workspace_or_requested_style_preset"


def build_workflow_atom_context(
    *,
    user_prompt: str,
    workspace: Path | None = None,
    style_preset: str = "",
    slide_count: int = DEFAULT_SLIDE_COUNT,
    include_prompt: bool = True,
) -> dict[str, Any]:
    """Return a compact atom seed plus optional strict JSON scout prompt."""

    workspace = workspace.expanduser().resolve() if workspace is not None else None
    family, basis = _infer_family(user_prompt, workspace=workspace, style_preset=style_preset)
    topic = str(user_prompt or "").strip() or "presentation deck"
    workspace_context = _workspace_text(workspace)
    prompt_context = " ".join(part for part in (topic, workspace_context) if part).strip()
    composition = deterministic_composition(
        target_family=family,
        slide_count=slide_count,
        topic=topic,
        user_prompt=prompt_context,
    )
    applied = apply_composition(composition)
    atom_prompt = (
        emit_composition_prompt(topic=topic, user_prompt=prompt_context[:4000], target_family=family, slide_count=slide_count)
        if include_prompt
        else {}
    )
    brief = applied.get("design_brief") if isinstance(applied.get("design_brief"), dict) else {}
    ledger = brief.get("style_atom_composition") if isinstance(brief.get("style_atom_composition"), dict) else {}
    strict_prompt = str(atom_prompt.get("prompt") or "")
    if strict_prompt:
        strict_prompt = (
            "Use strict JSON only. Return no markdown, comments, or prose.\n\n"
            + strict_prompt
        )
    return {
        "schema_version": "normal_workflow_atom_context_v1",
        "route_id": "atom_composition",
        "status": "seeded_optional",
        "target_family": family,
        "selection_basis": basis,
        "slide_count": slide_count,
        "topic": topic,
        "topic_terms": composition.get("topic_terms") if isinstance(composition.get("topic_terms"), list) else [],
        "preferred_variants": applied.get("preferred_variants") if isinstance(applied.get("preferred_variants"), list) else [],
        "narrative_arc": applied.get("narrative_arc") if isinstance(applied.get("narrative_arc"), list) else [],
        "deck_style_delta": applied.get("deck_style") if isinstance(applied.get("deck_style"), dict) else {},
        "design_brief_delta": {
            key: brief.get(key)
            for key in ("palette_signals", "typography_signals", "layout_signals", "rhythm_signature", "style_atom_composition")
            if key in brief
        },
        "style_atom_composition": ledger,
        "deterministic_composition": composition,
        "strict_json_prompt": strict_prompt if include_prompt else "",
        "prompt_packet_summary": {
            "schema_version": atom_prompt.get("schema_version"),
            "target_family": atom_prompt.get("target_family"),
            "related_families": atom_prompt.get("related_families"),
            "candidate_type_count": len(atom_prompt.get("candidates") or {}) if include_prompt else 0,
        },
        "normal_workflow_contract": {
            "decision_rule": (
                "Treat this as a first-class optional route. Accept it when the atom choices fit the "
                "topic, refine it by returning the strict JSON atom shape, or skip it with a recorded reason."
            ),
            "persist_when_used": [
                "design_contract.json:choice_resolution.atom_composition",
                "design_contract.json:style_system.style_atom_composition",
                "design_brief.json:style_atom_composition",
                "design_brief.json:style_system.style_atom_preferred_variants",
                "design_brief.json:style_system.style_atom_narrative_arc",
                "outline.json:deck_style supported fields from deck_style_delta",
                "content_plan.json:narrative_arc or slide_plan variants where topic-fit",
            ],
            "do_not_force": [
                "Do not use every preferred variant just because it appears in the atom packet.",
                "Do not override explicit user style, brand, source, or accessibility constraints.",
                "Do not copy external slide geometry; atoms are descriptor-only grammar signals.",
            ],
        },
    }


def compact_workflow_atom_context(context: dict[str, Any], *, include_prompt: bool = False) -> dict[str, Any]:
    """Shrink a workflow atom context for embedding inside larger prompts."""

    topic_terms = context.get("topic_terms")
    if isinstance(topic_terms, list):
        topic_terms = topic_terms[:50]
    compact = {
        "schema_version": context.get("schema_version"),
        "route_id": context.get("route_id"),
        "status": context.get("status"),
        "strict_json_instruction": "Use strict JSON only. Return no markdown, comments, or prose.",
        "target_family": context.get("target_family"),
        "selection_basis": context.get("selection_basis"),
        "slide_count": context.get("slide_count"),
        "topic_terms": topic_terms,
        "preferred_variants": context.get("preferred_variants"),
        "narrative_arc": context.get("narrative_arc"),
        "deck_style_delta": context.get("deck_style_delta"),
        "design_brief_delta": context.get("design_brief_delta"),
        "style_atom_composition": context.get("style_atom_composition"),
        "normal_workflow_contract": context.get("normal_workflow_contract"),
        "prompt_packet_summary": context.get("prompt_packet_summary"),
    }
    if include_prompt:
        compact["strict_json_prompt"] = str(context.get("strict_json_prompt", "") or "")[:6000]
    return compact
