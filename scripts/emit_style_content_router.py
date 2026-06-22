#!/usr/bin/env python3
"""Emit a deck-level style/content routing prompt for a subagent.

Use this before finalizing `outline.json` for non-trivial, researched, or
asset-heavy decks. The output prompt asks for structured JSON that constrains
design DNA, preset choice, variants, asset needs, and QA sensitivities.

This is intentionally a prompt emitter, not an automatic picker: deterministic
keyword matching is too brittle for lab/scientific decks and too generic for
brand/editorial decks.

Usage:
    python3 scripts/emit_style_content_router.py --workspace decks/my-deck
    python3 scripts/emit_style_content_router.py --workspace decks/my-deck \\
        --user-prompt "ASCO lab update on LAMP sequencing" --output /tmp/router.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from large_style_corpus import compact_large_style_corpus_context
from style_inspiration_corpus import compact_style_inspiration_context
from style_reference_catalog import rank_style_references, style_reference_mix_plan
from style_treatment_profiles import preset_treatment_profile


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


def _reference_field(match: dict[str, Any], key: str) -> Any:
    reference = match.get("reference") if isinstance(match.get("reference"), dict) else {}
    return reference.get(key)


def _compact_recipe_library(reference: dict[str, Any]) -> dict[str, Any]:
    library = (
        reference.get("content_recipe_library")
        if isinstance(reference.get("content_recipe_library"), dict)
        else {}
    )
    recipes = library.get("recipes") if isinstance(library.get("recipes"), dict) else {}
    compact_recipes: dict[str, Any] = {}
    for treatment_key, recipe in recipes.items():
        if not isinstance(recipe, dict):
            continue
        archetype = (
            recipe.get("treatment_archetype")
            if isinstance(recipe.get("treatment_archetype"), dict)
            else {}
        )
        compact_recipes[str(treatment_key)] = {
            "primary_variants": recipe.get("primary_variants"),
            "required_slots": recipe.get("required_slots"),
            "data_roles": recipe.get("data_roles"),
            "source_posture": recipe.get("source_posture"),
            "recipe_signature": recipe.get("recipe_signature"),
            "treatment_archetype": {
                "archetype_id": archetype.get("archetype_id"),
                "structure": archetype.get("structure"),
                "object_pattern": archetype.get("object_pattern"),
                "required_fields": archetype.get("required_fields")
                if isinstance(archetype.get("required_fields"), list)
                else [],
                "primary_variants": archetype.get("primary_variants")
                if isinstance(archetype.get("primary_variants"), list)
                else [],
            }
            if archetype
            else {},
        }
    return {
        "library_version": library.get("library_version"),
        "recipe_signatures": library.get("recipe_signatures")
        if isinstance(library.get("recipe_signatures"), dict)
        else {},
        "recipes": compact_recipes,
        "authoring_contract": (
            library.get("authoring_contract")
            if isinstance(library.get("authoring_contract"), list)
            else []
        )[:4],
    }


def _compact_source_intake(reference: dict[str, Any]) -> dict[str, Any]:
    intake = (
        reference.get("style_source_intake")
        if isinstance(reference.get("style_source_intake"), dict)
        else {}
    )
    sources: list[dict[str, Any]] = []
    for source in intake.get("sources", []):
        if not isinstance(source, dict):
            continue
        sources.append(
            {
                "source_id": source.get("source_id"),
                "source_name": source.get("source_name"),
                "source_url": source.get("source_url"),
                "source_status": source.get("source_status"),
                "license_summary": source.get("license_summary"),
                "allowed_extractions": (
                    source.get("allowed_extractions")
                    if isinstance(source.get("allowed_extractions"), list)
                    else []
                )[:4],
                "generic_style_observations": (
                    source.get("generic_style_observations")
                    if isinstance(source.get("generic_style_observations"), list)
                    else []
                )[:3],
                "generic_slide_patterns": (
                    source.get("generic_slide_patterns")
                    if isinstance(source.get("generic_slide_patterns"), list)
                    else []
                )[:3],
                "design_constraints": (
                    source.get("design_constraints")
                    if isinstance(source.get("design_constraints"), list)
                    else []
                )[:3],
                "forbidden_materials": (
                    source.get("forbidden_materials")
                    if isinstance(source.get("forbidden_materials"), list)
                    else []
                )[:5],
            }
        )
    return {
        "manifest_version": intake.get("manifest_version"),
        "source_checked_date": intake.get("source_checked_date"),
        "route_id": intake.get("route_id"),
        "derivation_mode": intake.get("derivation_mode"),
        "source_ids": intake.get("source_ids") if isinstance(intake.get("source_ids"), list) else [],
        "use_cases": intake.get("use_cases") if isinstance(intake.get("use_cases"), list) else [],
        "required_synthetic_content": (
            intake.get("required_synthetic_content")
            if isinstance(intake.get("required_synthetic_content"), list)
            else []
        ),
        "content_treatment_scope": (
            intake.get("content_treatment_scope")
            if isinstance(intake.get("content_treatment_scope"), list)
            else []
        ),
        "sources": sources,
        "publish_safety": intake.get("publish_safety") if isinstance(intake.get("publish_safety"), dict) else {},
    }


def _compact_style_metric_profile(reference: dict[str, Any]) -> dict[str, Any]:
    profile = (
        reference.get("style_metric_profile")
        if isinstance(reference.get("style_metric_profile"), dict)
        else {}
    )
    return {
        "metric_profile_version": profile.get("metric_profile_version"),
        "density_level": profile.get("density_level"),
        "whitespace_ratio_target": profile.get("whitespace_ratio_target"),
        "body_words_per_content_slide": (
            profile.get("body_words_per_content_slide")
            if isinstance(profile.get("body_words_per_content_slide"), list)
            else []
        ),
        "max_primary_objects": profile.get("max_primary_objects"),
        "visual_hierarchy": profile.get("visual_hierarchy"),
        "evidence_object_mix": (
            profile.get("evidence_object_mix")
            if isinstance(profile.get("evidence_object_mix"), dict)
            else {}
        ),
        "source_burden": profile.get("source_burden"),
        "footer_posture": profile.get("footer_posture"),
        "artifact_bias": profile.get("artifact_bias") if isinstance(profile.get("artifact_bias"), list) else [],
        "readability_bias": (
            profile.get("readability_bias")
            if isinstance(profile.get("readability_bias"), list)
            else []
        ),
        "metric_signature": profile.get("metric_signature"),
    }


def _compact_footer_reference_contract(
    reference: dict[str, Any], renderer_profile: dict[str, Any]
) -> dict[str, Any]:
    defaults = (
        renderer_profile.get("renderer_treatment_defaults")
        if isinstance(renderer_profile.get("renderer_treatment_defaults"), dict)
        else {}
    )
    mix = (
        renderer_profile.get("style_mix_matrix")
        if isinstance(renderer_profile.get("style_mix_matrix"), dict)
        else {}
    )
    playbook = (
        reference.get("layout_playbook")
        if isinstance(reference.get("layout_playbook"), dict)
        else {}
    )
    library = (
        reference.get("content_recipe_library")
        if isinstance(reference.get("content_recipe_library"), dict)
        else {}
    )
    recipes = library.get("recipes") if isinstance(library.get("recipes"), dict) else {}
    references_recipe = (
        recipes.get("references") if isinstance(recipes.get("references"), dict) else {}
    )
    archetype = (
        references_recipe.get("treatment_archetype")
        if isinstance(references_recipe.get("treatment_archetype"), dict)
        else {}
    )
    footer_pool = mix.get("footer_pool") if isinstance(mix.get("footer_pool"), list) else []
    default_footer = str(defaults.get("footer_mode") or "").strip() or "standard"
    return {
        "contract_version": "style_reference_footer_reference_contract_v1",
        "default_footer_mode": default_footer,
        "footer_pool": footer_pool,
        "source_footer_policy": playbook.get("source_footer_policy"),
        "references_recipe_signature": references_recipe.get("recipe_signature"),
        "references_source_posture": references_recipe.get("source_posture"),
        "references_required_slots": (
            references_recipe.get("required_slots")
            if isinstance(references_recipe.get("required_slots"), list)
            else []
        )[:4],
        "references_data_roles": (
            references_recipe.get("data_roles")
            if isinstance(references_recipe.get("data_roles"), list)
            else []
        )[:4],
        "references_treatment_archetype": {
            "archetype_id": archetype.get("archetype_id"),
            "footer_mode": archetype.get("footer_mode"),
            "structure": archetype.get("structure"),
            "required_fields": (
                archetype.get("required_fields")
                if isinstance(archetype.get("required_fields"), list)
                else []
            ),
        }
        if archetype
        else {},
        "page_number_policy": (
            "Use a bottom-right page number for report/source-line decks; "
            "omit only when the primary reference explicitly supports a no-footer title or poster page."
        ),
        "source_line_policy": (
            "Use short source IDs near the footer rule; move long citations to a final "
            "editable references table or small source notes below the rule when space permits."
        ),
        "readability_policy": (
            "Reserve footer space, keep source IDs readable, and never let footer provenance "
            "collide with dense tables, charts, or figure captions."
        ),
    }


def _compact_large_corpus_router_context(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("available"):
        return payload
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    families: list[dict[str, Any]] = []
    for item in payload.get("selected_family_summaries", [])[:2]:
        if not isinstance(item, dict):
            continue
        descriptor = item.get("descriptor") if isinstance(item.get("descriptor"), dict) else {}
        families.append(
            {
                "style_family": item.get("style_family"),
                "record_count": item.get("record_count"),
                "layout_tags": (descriptor.get("layout_tags") if isinstance(descriptor.get("layout_tags"), list) else [])[:2],
                "content_treatments": (
                    descriptor.get("content_treatments")
                    if isinstance(descriptor.get("content_treatments"), list)
                    else []
                )[:2],
            }
        )
    samples: list[dict[str, Any]] = []
    for record in payload.get("sample_records", [])[:2]:
        if not isinstance(record, dict):
            continue
        samples.append(
            {
                "deck_id": record.get("deck_id"),
                "deck_system": record.get("deck_system"),
                "primary_style_family": record.get("primary_style_family"),
                "descriptor_tags": (
                    record.get("descriptor_tags") if isinstance(record.get("descriptor_tags"), list) else []
                )[:3],
            }
        )
    return {
        "catalog_version": payload.get("catalog_version"),
        "available": True,
        "storage_rule": (
            payload.get("policy", {}).get("storage_rule")
            if isinstance(payload.get("policy"), dict)
            else None
        ),
        "summary": {
            "record_count": summary.get("record_count"),
            "unique_repository_count": summary.get("unique_repository_count"),
            "ai_agent_signal_count": summary.get("ai_agent_signal_count"),
        },
        "selected_family_summaries": families,
        "sample_records": samples,
    }


def _renderer_profile_for_preset(preset: Any) -> dict[str, Any]:
    key = str(preset or "").strip()
    if not key:
        return {}
    try:
        profile = preset_treatment_profile(key)
    except Exception:
        return {}
    mix = profile.get("style_mix_matrix") if isinstance(profile.get("style_mix_matrix"), dict) else {}
    return {
        "renderer_treatment_defaults": profile.get("renderer_treatment_defaults"),
        "renderer_treatment_signature": profile.get("renderer_treatment_signature"),
        "style_mix_matrix": {
            "header_variant_pool": mix.get("header_variant_pool"),
            "title_layout_pool": mix.get("title_layout_pool"),
            "chart_treatment_pool": mix.get("chart_treatment_pool"),
            "table_treatment_pool": mix.get("table_treatment_pool"),
            "figure_table_treatment_pool": mix.get("figure_table_treatment_pool"),
            "stats_mode_pool": mix.get("stats_mode_pool"),
            "matrix_mode_pool": mix.get("matrix_mode_pool"),
            "summary_callout_mode_pool": mix.get("summary_callout_mode_pool"),
            "footer_pool": mix.get("footer_pool"),
            "mix_rule": mix.get("mix_rule"),
            "do_not_mix": mix.get("do_not_mix"),
        },
    }


def _style_reference_match_context(text: str, *, limit: int = 22000) -> str:
    query = str(text or "").strip()
    if not query:
        return "<no prompt or workspace text available for style-reference matching>"
    matches = rank_style_references(query, limit=5)
    mix_plan = style_reference_mix_plan(query, limit=3)
    primary = mix_plan.get("primary") if isinstance(mix_plan.get("primary"), dict) else {}
    secondaries = (
        mix_plan.get("secondary_influences")
        if isinstance(mix_plan.get("secondary_influences"), list)
        else []
    )
    compact_matches: list[dict[str, Any]] = []
    full_reference_by_id: dict[str, dict[str, Any]] = {}
    for match in matches:
        if not isinstance(match, dict):
            continue
        reference = match.get("reference") if isinstance(match.get("reference"), dict) else {}
        renderer_profile = _renderer_profile_for_preset(match.get("style_preset"))
        reference_id = str(_reference_field(match, "reference_id") or "").strip()
        if reference_id:
            full_reference_by_id[reference_id] = reference
        compact_matches.append(
            {
                "style_preset": match.get("style_preset"),
                "score": match.get("score"),
                "reference_id": _reference_field(match, "reference_id"),
                "reference_name": _reference_field(match, "reference_name"),
                "style_dna": _reference_field(match, "style_dna"),
                "structural_motif_library": _reference_field(match, "structural_motif_library"),
                "style_metric_profile": _compact_style_metric_profile(reference),
                "renderer_treatment_defaults": renderer_profile.get("renderer_treatment_defaults"),
                "renderer_treatment_signature": renderer_profile.get("renderer_treatment_signature"),
                "style_source_intake": _compact_source_intake(reference),
                "signature_moves": _reference_field(match, "signature_moves"),
                "content_treatments": _reference_field(match, "content_treatments"),
                "layout_playbook": _reference_field(match, "layout_playbook"),
                "content_recipe_library": _compact_recipe_library(reference),
                "footer_reference_contract": _compact_footer_reference_contract(
                    reference, renderer_profile
                ),
                "example_storyboard": _reference_field(match, "example_storyboard"),
                "publish_safety": _reference_field(match, "publish_safety"),
                "style_mix_matrix": renderer_profile.get("style_mix_matrix"),
            }
        )
    primary_reference_id = str(primary.get("reference_id") or "").strip()
    primary_reference = full_reference_by_id.get(primary_reference_id, {})
    primary_renderer_profile = _renderer_profile_for_preset(primary.get("style_preset"))
    inspiration_context = compact_style_inspiration_context(
        query,
        primary_preset=str(primary.get("style_preset") or ""),
    )
    large_corpus_context = compact_large_style_corpus_context(
        query,
        primary_family=str(primary.get("style_preset") or ""),
        max_records=6,
    )
    large_corpus_context = _compact_large_corpus_router_context(large_corpus_context)
    compact_mix = {
        "mix_plan_version": mix_plan.get("mix_plan_version"),
        "query_summary": _truncate(str(mix_plan.get("query") or ""), 700),
        "primary": {
            "style_preset": primary.get("style_preset"),
            "score": primary.get("score"),
            "reference_id": primary.get("reference_id"),
            "reference_name": primary.get("reference_name"),
            "style_dna": primary.get("style_dna"),
            "structural_motif_library": primary.get("structural_motif_library"),
            "style_metric_profile": _compact_style_metric_profile(primary_reference),
            **primary_renderer_profile,
            "footer_reference_contract": _compact_footer_reference_contract(
                primary_reference, primary_renderer_profile
            ),
        },
        "secondary_influences": [
            {
                "style_preset": item.get("style_preset"),
                "score": item.get("score"),
                "reference_id": item.get("reference_id"),
                "reference_name": item.get("reference_name"),
                "style_dna": item.get("style_dna"),
                "structural_motif_library": item.get("structural_motif_library"),
                "style_metric_profile": _compact_style_metric_profile(
                    full_reference_by_id.get(str(item.get("reference_id") or ""), {})
                ),
                **_renderer_profile_for_preset(item.get("style_preset")),
            }
            for item in secondaries
            if isinstance(item, dict)
        ],
        "treatment_mix": mix_plan.get("treatment_mix"),
        "mixing_rules": mix_plan.get("mixing_rules"),
    }
    return _compact_json(
        {
            "purpose": (
                "Use this publish-safe synthetic style-reference context to pick "
                "design DNA, layout playbook, content recipes, and renderer treatment pools. "
                "Do not copy external/proprietary slide geometry. Use the descriptor-only "
                "style inspiration corpus for broad source matching, then open the selected "
                "preset contact-sheet collection use cases before borrowing any treatment ideas. "
                "When available, use the large_style_corpus block as broad real-world pattern "
                "evidence; it is still descriptor-only and never permits copying source decks."
            ),
            "style_inspiration_corpus": inspiration_context,
            "large_style_corpus": large_corpus_context,
            "preset_contact_collection_contract": {
                "collection_version": "style_reference_preset_contact_collection_v1",
                "required_use_cases": ["overview", "data_evidence", "decision_sources"],
                "browse_rule": (
                    "Open the primary preset's overview sheet first, then data_evidence "
                    "or decision_sources based on the evidence burden. Compare secondary "
                    "preset collections only for named treatment borrow decisions."
                ),
            },
            "matches": compact_matches,
            "mix_plan": compact_mix,
        },
        limit,
    )


def _text_blob(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text_blob(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(v) for v in value)
    return str(value)


def _outline_summary(outline: Any) -> list[str]:
    if not isinstance(outline, dict):
        return ["outline.json: <missing or malformed>"]

    slides = outline.get("slides") or []
    deck_style = outline.get("deck_style") or {}
    lines = [
        f"Deck title: {outline.get('title', '<untitled>')}",
        f"Deck subtitle: {outline.get('subtitle', '')}",
        f"Current deck_style: {json.dumps(deck_style, sort_keys=True)}",
        f"Slide count: {len(slides) if isinstance(slides, list) else '<invalid>'}",
    ]
    if not isinstance(slides, list):
        return lines

    variants: Counter[str] = Counter()
    visual_intents: Counter[str] = Counter()
    asset_keys: Counter[str] = Counter()
    for idx, slide in enumerate(slides):
        if not isinstance(slide, dict):
            continue
        variant = str(slide.get("variant") or "-")
        visual = str(slide.get("visual_intent") or "-")
        variants[variant] += 1
        visual_intents[visual] += 1
        assets = slide.get("assets") or {}
        if isinstance(assets, dict):
            for key, value in assets.items():
                if value:
                    asset_keys[str(key)] += 1
        title = str(slide.get("title") or "").strip()
        role = str(slide.get("slide_intent") or slide.get("role") or "").strip()
        if idx < 18:
            lines.append(
                f"slide {idx:02d}: type={slide.get('type', 'content')} "
                f"variant={variant} visual_intent={visual} "
                f"role={role or '-'} title={title[:90]}"
            )

    lines.append(f"Variant histogram: {dict(variants)}")
    lines.append(f"Visual-intent histogram: {dict(visual_intents)}")
    lines.append(f"Asset-key histogram: {dict(asset_keys)}")
    return lines


def _evidence_summary(evidence_plan: Any, asset_plan: Any) -> list[str]:
    lines: list[str] = []
    if isinstance(evidence_plan, dict):
        items = evidence_plan.get("items") or []
        chart_candidates = evidence_plan.get("chart_candidates") or []
        visual_uses: Counter[str] = Counter()
        units: Counter[str] = Counter()
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                visual_uses[str(item.get("visual_use") or "-")] += 1
                if item.get("unit"):
                    units[str(item.get("unit"))] += 1
        lines.append(f"Evidence items: {len(items) if isinstance(items, list) else '<invalid>'}")
        lines.append(f"Evidence visual_use histogram: {dict(visual_uses)}")
        lines.append(f"Evidence units: {dict(units)}")
        lines.append(
            f"Chart candidates: {len(chart_candidates) if isinstance(chart_candidates, list) else '<invalid>'}"
        )
    else:
        lines.append("Evidence plan: <missing or malformed>")

    if isinstance(asset_plan, dict):
        for key in ("images", "charts", "icons", "backgrounds", "generated_images"):
            value = asset_plan.get(key)
            if isinstance(value, list):
                lines.append(f"Asset plan {key}: {len(value)}")
    else:
        lines.append("Asset plan: <missing or malformed>")
    return lines


def _keyword_priors(text: str) -> list[str]:
    priors = {
        "asco": "conference/scientific meeting",
        "tb": "infectious disease/lab domain",
        "lamp": "assay/workflow domain",
        "clinical": "clinical proof burden",
        "lod": "limit-of-detection result",
        "sequencing": "data-derived figure/table evidence",
        "assay": "methods/readout evidence",
        "sample": "sample/run metadata",
        "resistance": "genotype/clinical interpretation state",
    }
    lower = text.lower()
    found: list[str] = []
    for term, meaning in priors.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower):
            found.append(f"{term}: {meaning}")
    return found


PROMPT = """\
You are the style/content routing scout for a PowerPoint deck. Your job is to
choose the deck's design DNA and slide-level route BEFORE the author finalizes
outline.json.

Read these refs first. They are authoritative:
- {design_philosophy}
- {planning_schema}
- {outline_schema}
- {subagent_patterns}
- {reference_script_patterns}
- {dynamic_design_and_subagents}

Use the prompt-to-style reference matches below as the primary design-memory
context. The `mix_plan.primary` reference owns the base preset, layout
playbook, source/footer posture, renderer treatment defaults, and supported
variant families. Secondary references may influence specific treatment keys,
but record borrowed influence explicitly. Do not let the output collapse to
broad generic categories when a publish-safe synthetic reference provides
concrete `layout_playbook`, `content_recipe_library`, and
`style_metric_profile`, and `renderer_treatment_signature` guidance. Use the
metric profile to set density, whitespace, body-word budget, maximum primary
object count, evidence-object mix, source burden, and artifact/readability
bias before recommending slide variants.

The `style_inspiration_corpus` block is a descriptor-only source index for
dynamic design scouting. It may suggest public design systems, slide tooling,
template indexes, and article heuristics as broad inspiration, but it never
permits copying raw decks, screenshots, logos, proprietary text, or distinctive
slide geometry. Use its selected routes and safety rules to decide which
per-preset contact-sheet collection to browse (`overview`, `data_evidence`,
or `decision_sources`) and where a treatment-specific secondary influence is
worth recording.

The `large_style_corpus` block, when available, is a larger descriptor-only
index of public/open-source deck-like records. Use it to spot real-world
presentation systems, underused treatment patterns, and style families that
would make the current deck less generic. It is not a template gallery and it
does not grant permission to copy or embed source decks. Borrow only abstract
ideas such as "agent workflow comparison", "risk register table", "journal
figure plate", or "product roadmap bands", then create original synthetic
structure in the design contract and outline.

Treat report structure and source/footer posture as first-class reproducibility
contracts. Bind the selected reference's layout playbook to a concrete section
order, treatment recipes, footer mode, source-line/page-number rule, and final
references behavior. The `footer_reference_contract` in the prompt-to-style
matches is authoritative for page number posture, source IDs, small source
notes, and when long references move to an editable references table.

Important rule: do NOT route by keywords alone. Terms like ASCO, TB, LAMP,
clinical, LOD, sequencing, assay, sample, and resistance are useful priors, but
you must validate them against the objective, audience, evidence objects, and
asset availability. A public-health explainer that mentions TB may need an
editorial deck. A lab update that never says "assay" may still need
figure-first report layouts.

Classify the deck on these axes:
- user objective: talk, report, leave-behind, pitch, poster, lab update
- audience posture: scientific peer, clinician, executive, public, student
- evidence objects: figures, plots, microscopy/images, assay readouts, result
  tables, raw data, workflow, screenshots, citations, metrics
- proof burden: concept, sourced report, clinical/lab claim, validation claim
- asset availability: local figures, generated figures, source-backed images,
  editable tables, charts, no assets yet
- density: live talk, readable report, dense leave-behind

Then recommend bounded design modulation. Start from a loadable preset, then
specify subtle/moderate/bold changes that match the audience, evidence, and
deck role: accent use, whitespace, density, motif, container policy, and
figure/table treatment. Do not propose unsupported inline colors or custom
fonts unless the main author should add a validated preset/font pair.

If you introduce title-slide chips, stage tags, or evidence labels, define how
they continue after slide 1. A cover-only motif is a template tell. For
lab/scientific decks with generated figures, also specify the figure export
contract: Python script path, target variant/box, and whitespace/cropping rule.
When local CSV/TSV/XLSX/JSON data, result tables, or chart candidates drive the
deck, return a data artifact workflow that tells the main agent to run the
dedicated analysis scout and deterministic scaffold before outline finalization:
scripts/emit_data_analysis_prompt.py, scripts/scaffold_figure_artifacts.py
--run --bind-outline, scripts/build_workspace.py --fast-first-pass, and
scripts/trim_image_whitespace.py when exported plots have large exterior
whitespace. The workflow must state which slide routes need chart:<name>,
table:<name>, or image:<name> aliases, and which artifacts need reproducibility
metadata.
Also return a concrete readability contract, including
readability_contract.max_slide_text_lines, max_slide_words, max_slide_chars,
max_title_lines, minimum chart/table label sizes, and footer reserve. Flag
content_span_too_short/content_span_too_narrow risk when evidence or text would
leave awkward unused slide space.

For lab/report evidence, prefer:
- style_preset: lab-report or another restrained report preset
- deck_style: header_mode lab-clean, footer_mode source-line,
  summary_callout_mode lab-box, research_visual_mode true
- variants: scientific-figure, image-sidebar, lab-run-results, table,
  comparison-2col, and scoped flow/workflow
- avoid: generic cards-3, decorative icon grids, forced KPI hero slides, and
  process diagrams that do not carry evidence

For non-lab decks, choose the appropriate design DNA and preserve visual
specificity. Do not force lab-report because one keyword appears.

Return ONLY valid JSON with this shape:

{{
  "design_dna": "lab results dashboard | board risk memo | product/investor reveal | editorial report | civic science policy | custom",
  "style_preset": "loadable preset name",
  "style_reference_selection": {{
    "mix_plan_version": "style_reference_mix_plan_v1",
    "primary_reference_id": "selected reference id from prompt-to-style matches",
    "primary_reference_name": "selected reference name",
    "primary_style_dna": "copied or summarized style_dna",
    "secondary_reference_ids": ["only when a secondary match materially affects a treatment"],
    "layout_playbook_version": "style_reference_layout_playbook_v1",
    "treatment_variant_map_used": {{
      "title": ["title"],
      "chart": ["chart"],
      "table": ["table", "lab-run-results"],
      "figure": ["scientific-figure", "image-sidebar"],
      "dashboard": ["stats", "lab-run-results"],
      "comparison": ["comparison-2col", "matrix", "split"],
      "decision": ["table", "standard"],
      "references": ["table"]
    }},
    "content_recipe_library_version": "style_reference_content_recipe_library_v1",
    "style_metric_profile_version": "style_reference_metric_profile_v1",
    "style_metric_signature": "copy selected reference style_metric_profile.metric_signature",
    "density_level": "copy selected reference density posture",
    "whitespace_ratio_target": "copy selected reference whitespace target",
    "body_words_per_content_slide": "copy selected reference body word budget",
    "max_primary_objects": "copy selected reference object-count limit",
    "visual_hierarchy": "copy selected reference evidence scan path",
    "evidence_object_mix": "copy selected reference chart/table/figure/prose weights",
    "renderer_treatment_signature": "copy selected reference/profile signature or supported override",
    "style_inspiration_corpus_used": {{
      "corpus_version": "style_inspiration_corpus_v1",
      "storage_rule": "descriptor_only_no_raw_decks",
      "primary_source_ids": ["descriptor source ids used for broad inspiration"],
      "borrowed_descriptor_tags": ["descriptor tags that affected the route"],
      "preset_contact_collection_use_cases": ["overview", "data_evidence", "decision_sources"],
      "safety_statement": "descriptor-only use; synthetic reconstruction through local renderer"
    }},
    "treatment_mix_used": {{
      "title": "primary or secondary reference id",
      "chart": "primary or secondary reference id",
      "table": "primary or secondary reference id",
      "figure": "primary or secondary reference id",
      "dashboard": "primary or secondary reference id",
      "comparison": "primary or secondary reference id",
      "decision": "primary or secondary reference id",
      "references": "primary or secondary reference id"
    }},
    "routing_rationale": [
      "specific prompt/evidence signal that matched the selected reference"
    ]
  }},
  "report_structure_contract": {{
    "structure_version": "style_reference_report_structure_contract_v1",
    "primary_layout_playbook_id": "selected reference id",
    "opening_sequence": ["cover/title route", "first evidence or context route"],
    "section_order": ["context", "evidence", "analysis", "decision", "references"],
    "content_recipe_bindings": [
      {{
        "treatment_key": "chart | table | figure | comparison | dashboard | decision | references",
        "recipe_signature": "copy from selected content_recipe_library",
        "required_slots": ["slot that must be present"],
        "target_variants": ["supported variant names"],
        "source_or_artifact_binding": "chart:<name> | table:<name> | image:<name> | source:<id>"
      }}
    ],
    "rebuild_determinism": [
      "store selected reference id, style_seed, treatment map, artifact aliases, and source IDs in outline/design brief"
    ]
  }},
  "source_footer_contract": {{
    "contract_version": "style_reference_footer_reference_contract_v1",
    "footer_mode": "standard | source-line",
    "footer_pool": ["source-line", "standard"],
    "page_number_policy": "bottom-right page number for report/source-line decks unless a no-footer page is intentional",
    "source_line_policy": "short source IDs near or below the footer rule; long refs move to final editable references table",
    "small_source_note_policy": "small but readable source notes only; do not crowd evidence or collide with charts/tables",
    "references_slide_policy": "editable references table or sparse source slide when proof burden requires full citations"
  }},
  "deck_style": {{
    "style_seed": "short stable deck-specific seed",
    "header_mode": "bar | stack | eyebrow | lab-clean | lab-card",
    "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
    "footer_mode": "standard | source-line",
    "summary_callout_mode": "default | lab-box",
    "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar",
    "chart_treatment": "standard | facts-below | facts-right | minimal | hero-stat | threshold-band | sparse-wide",
    "table_treatment": "standard | compact-ledger | readout-sidecar | decision-matrix | journal-grid",
    "research_visual_mode": true
  }},
  "style_mix_matrix": {{
    "header_variant_pool": ["left-accent", "split-rule", "title-rule", "side-rail", "top-bottom-rule", "plain"],
    "title_layout_pool": ["split-hero", "lab-plate", "command-center", "poster", "masthead", "light-atlas"],
    "section_motif_pool": ["rail-dots", "numbered-tabs", "plain"],
    "timeline_mode_pool": ["rail-cards", "staggered", "open-events", "bands", "chapter-spread"],
    "matrix_mode_pool": ["cards", "open-quadrants"],
    "stats_mode_pool": ["tiles", "feature-left", "policy-bands"],
    "cards_mode_pool": ["feature-left", "staggered-row"],
    "chart_treatment_pool": ["standard", "facts-below", "facts-right", "minimal", "hero-stat", "threshold-band", "sparse-wide"],
    "table_treatment_pool": ["standard", "compact-ledger", "readout-sidecar", "decision-matrix", "journal-grid"],
    "summary_callout_mode_pool": ["default", "lab-box"],
    "figure_table_treatment_pool": ["figure-first", "table-first", "stats-strip", "image-sidebar"],
    "footer_pool": ["source-line", "standard", "none"],
    "mix_rule": "rotate only compatible treatments that reinforce the design DNA",
    "do_not_mix": ["specific treatment pairings that would make the deck feel random"]
  }},
  "design_modulation": {{
    "change_intensity": "subtle | moderate | bold",
    "base_preset_fit": "base preset is enough | preset plus treatment changes | new preset needed",
    "accent_strategy": "where accent color appears and where it must not",
    "density_strategy": "low live-talk density | medium brief | high report density",
    "whitespace_strategy": "more breathing room | compact report grid | poster-like open field",
    "motif_strategy": "specific motif or none; must relate to topic/evidence",
    "container_strategy": "cards, panels, open grid, table-first, figure-first",
    "figure_table_treatment": "caption/source/table density and semantic highlight rules",
    "avoid": ["visual move that would make the deck generic or misleading"]
  }},
  "evidence_continuity": {{
    "threads": ["EVIDENCE", "READOUT", "NEXT RUN"],
    "carry_forward_rule": "how cover chips/tags continue on content slides",
    "slide_applications": [
      {{
        "slide_id_or_index": "s2 or 2",
        "thread": "EVIDENCE",
        "placement": "subtitle eyebrow | sidebar label | footer tag | table group label"
      }}
    ]
  }},
  "figure_export_contract": {{
    "script": "assets/make_figures.py or none",
    "rerun_command": "python3 assets/make_figures.py",
    "outputs": [
      {{
        "path": "assets/figures/example.png",
        "target_slide": "s3 or stable slide id",
        "target_variant": "image-sidebar | scientific-figure | lab-run-results | table | chart",
        "target_box": "approximate rendered size in inches",
        "figure_size_inches": [6.4, 3.6],
        "figure_dpi": 180,
        "axis_label_min_pt": 8,
        "legend_pt": 8,
        "x_label_rotation": 0,
        "crop_rule": "tight bbox, <=0.08 in visual padding, avoid large internal whitespace"
      }}
    ]
  }},
  "data_artifact_workflow": {{
    "data_artifacts_likely": true,
    "analysis_prompt": "scripts/emit_data_analysis_prompt.py --workspace <workspace> --user-prompt <brief>",
    "scaffold_command": "python3 scripts/scaffold_figure_artifacts.py --workspace <workspace> --run --bind-outline",
    "integrated_scaffold_command": "python3 scripts/build_workspace.py --workspace <workspace> --fast-first-pass",
    "whitespace_trim_command": "python3 scripts/trim_image_whitespace.py --input assets/figures/example.png --output assets/figures/example.png",
    "analysis_summary": "assets/analysis_summary.json plus assets/analysis_summary.md for fast agent inspection before outline binding",
    "artifact_registry_requirements": [
      "analysis_artifact_plan.artifact_manifest points to assets/artifacts_manifest.json",
      "analysis_artifact_plan.analysis_summary points to assets/analysis_summary.json",
      "analysis_artifact_plan.artifact_registry entries for generated figures/charts/tables",
      "analysis_metadata.source_path",
      "analysis_metadata.source_sha256",
      "analysis_metadata.selected_columns",
      "analysis_metadata.rows_used",
      "analysis_metadata.series_count",
      "analysis_metadata.points",
      "analysis_metadata.target_box",
      "analysis_metadata.figure_size_inches",
      "analysis_metadata.figure_dpi",
      "analysis_metadata.axis_label_min_pt",
      "analysis_metadata.legend_pt",
      "analysis_metadata.x_label_rotation",
      "used_on_slides resolves to outline slide ids",
      "figure_export_contract.outputs[*].target_slide is set when outline aliases already exist"
    ],
    "slide_alias_plan": [
      {{
        "slide_id_or_index": "s3 or 3",
        "required_artifact_ids": ["signal_figure", "signal_chart"],
        "aliases": ["image:signal_figure", "chart:signal_chart", "table:signal_summary"],
        "source_policy": "source-line footer with short IDs; full refs on References slide"
      }}
    ]
  }},
  "readability_contract": {{
    "max_title_lines": 2,
    "max_slide_text_lines": 8,
    "max_slide_words": 105,
    "max_slide_chars": 700,
    "body_min_pt": 14,
    "caption_min_pt": 8,
    "table_body_min_pt": 9,
    "chart_label_min_pt": 8,
    "footer_reserved_inches": 0.34,
    "source_line_footer_rule": "short source IDs only; long references below rule or on final References slide"
  }},
  "routing_basis": [
    "specific evidence/object/audience signal that justifies the route"
  ],
  "keyword_priors_used": [
    "keyword priors that were confirmed or rejected"
  ],
  "allowed_variants": [
    "scientific-figure",
    "image-sidebar"
  ],
  "forbidden_variants": [
    "variant that would make the deck generic or misleading"
  ],
  "slide_routes": [
    {{
      "slide_id_or_index": "s3 or 3",
      "role": "evidence | mechanism | comparison | implication | title",
      "variant": "scientific-figure",
      "visual_strategy": "source-backed figure with interpretation sidebar",
      "asset_needs": ["image:assay_readout"],
      "required_artifact_ids": ["assay_readout"],
      "evidence_objects": ["plot", "result table"],
      "source_policy": "source-line footer | final References slide | inline caption",
      "reason": "why this route fits",
      "confidence": 0.0
    }}
  ],
  "asset_requests": [
    {{
      "id": "fig_or_image_id",
      "type": "local figure | generated figure | source-backed image | editable table | chart",
      "why_needed": "visual/evidence role",
      "provenance_needed": true
    }}
  ],
  "subagent_plan": [
    {{
      "stage": "content research | data/evidence analysis | outline critique | rendered visual QA",
      "use_subagent": true,
      "prompt_emitter": "scripts/emit_content_research.py | scripts/emit_data_analysis_prompt.py | scripts/emit_outline_critique.py | render_slides.py --emit-visual-prompt",
      "reason": "why independent review or analysis is useful",
      "expected_output": "punch list or JSON constraint layer",
      "must_not_do": "do not author final outline or bypass deterministic QA"
    }}
  ],
  "qa_sensitivities": [
    "footers must not collide with dense tables",
    "source-line footer text must not shrink into unreadable provenance",
    "captions must remain legible at 9-11 pt",
    "native chart labels must honor axis_label_min_pt and chart_label_min_pt",
    "watch for content_span_too_short and content_span_too_narrow whitespace warnings",
    "figure/table slides need enough target_box area for readable labels"
  ],
  "open_questions": []
}}

--- User prompt ---

{user_prompt}

--- Keyword priors detected ---

{keyword_priors}

--- Prompt-to-style reference matches ---

{style_reference_matches}

--- Workspace summary ---

{workspace_summary}

--- Evidence/assets summary ---

{evidence_summary}

--- design_brief.json ---

{design_brief}

--- content_plan.json ---

{content_plan}

--- evidence_plan.json ---

{evidence_plan}

--- asset_plan.json ---

{asset_plan}

--- outline.json ---

{outline}

--- notes.md ---

{notes}
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a subagent prompt for deck-level style/content routing."
    )
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument(
        "--user-prompt",
        default="",
        help="Original user request or brief to include as routing context.",
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
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        print(f"Error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    design_brief = _load_json(workspace / "design_brief.json")
    content_plan = _load_json(workspace / "content_plan.json")
    evidence_plan = _load_json(workspace / "evidence_plan.json")
    asset_plan = _load_json(workspace / "asset_plan.json")
    outline = _load_json(workspace / "outline.json")
    notes = _read_optional(workspace / "notes.md") or "<missing>"

    combined_text = " ".join(
        [
            args.user_prompt,
            _text_blob(design_brief),
            _text_blob(content_plan),
            _text_blob(evidence_plan),
            _text_blob(asset_plan),
            _text_blob(outline),
            notes,
        ]
    )
    priors = _keyword_priors(combined_text)

    repo_root = Path(__file__).resolve().parent.parent
    refs = {
        "design_philosophy": str(repo_root / "references" / "design_philosophy.md"),
        "planning_schema": str(repo_root / "references" / "planning_schema.md"),
        "outline_schema": str(repo_root / "references" / "outline_schema.md"),
        "subagent_patterns": str(repo_root / "references" / "subagent_patterns.md"),
        "reference_script_patterns": str(
            repo_root / "references" / "reference_script_patterns.md"
        ),
        "dynamic_design_and_subagents": str(
            repo_root / "references" / "dynamic_design_and_subagents.md"
        ),
    }

    prompt = PROMPT.format(
        user_prompt=args.user_prompt or "<not provided>",
        keyword_priors="\n".join(f"- {item}" for item in priors) or "<none>",
        style_reference_matches=_style_reference_match_context(combined_text),
        workspace_summary="\n".join(_outline_summary(outline)),
        evidence_summary="\n".join(_evidence_summary(evidence_plan, asset_plan)),
        design_brief=_compact_json(design_brief, args.truncate_json),
        content_plan=_compact_json(content_plan, args.truncate_json),
        evidence_plan=_compact_json(evidence_plan, args.truncate_json),
        asset_plan=_compact_json(asset_plan, args.truncate_json),
        outline=_compact_json(outline, args.truncate_json),
        notes=_truncate(notes, args.truncate_notes),
        **refs,
    )

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(prompt, encoding="utf-8")
        print(f"Style/content router prompt written to {output}", file=sys.stderr)
    else:
        print("=" * 72)
        print("STYLE/CONTENT ROUTER SUBAGENT PROMPT (paste into an Explore agent)")
        print("=" * 72)
        print(prompt)
        print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
