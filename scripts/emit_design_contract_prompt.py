#!/usr/bin/env python3
"""Emit a reproducible deck design-contract prompt.

Use immediately after a user's deck request, before outline authoring. The
prompt asks a main agent or subagent to return a strict JSON contract that locks
style, background, structure, evidence policy, and QA expectations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from style_reference_catalog import REQUIRED_CONTENT_TREATMENTS, rank_style_references, style_reference_mix_plan
from style_treatment_profiles import preset_treatment_profile
from workflow_atom_context import build_workflow_atom_context, compact_workflow_atom_context


ROOT = Path(__file__).resolve().parent.parent
SMALL_FILE_HASH_LIMIT = 5 * 1024 * 1024
INVENTORY_LIMIT = 24
TABULAR_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".feather"}
JSON_DATA_EXCLUDED_NAMES = {
    "workspace.json",
    "style_contract.json",
    "design_brief.json",
    "content_plan.json",
    "evidence_plan.json",
    "asset_plan.json",
    "outline.json",
    "design_contract.json",
    "deck_start_packet.json",
    "intake_answers.json",
    "intake_apply_report.json",
    "outline_authoring_handoff.json",
    "outline_authoring_handoff_apply_report.json",
}
ARTIFACT_LEDGER_PATHS = [
    "assets/artifacts_manifest.json",
    "assets/analysis_summary.json",
    "assets/analysis_summary.md",
    "artifact_selections.auto.json",
    "data_analysis_handoff.json",
    "data_analysis_handoff_apply_report.json",
    "style_extract_report.json",
    "style_extract_design_brief.json",
    "style_fragment_apply_report.json",
    "design_contract_apply_report.json",
]


def _read_optional(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _load_json(path: Path) -> Any | None:
    text = _read_optional(path)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _compact_json(value: Any, limit: int = 5000) -> str:
    if value is None:
        return "<missing or malformed>"
    text = json.dumps(value, indent=2, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + f"\n... [truncated at {limit} chars]"


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:54] or "deck"


def _stable_id(user_prompt: str) -> str:
    digest = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()[:12]
    return f"{_slug(user_prompt)}-{digest}"


def _display_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _file_snapshot(workspace: Path, path: Path) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": path.exists(),
    }
    if not path.exists() or not path.is_file():
        return snapshot
    try:
        size = path.stat().st_size
        snapshot["size_bytes"] = size
        if size <= SMALL_FILE_HASH_LIMIT:
            snapshot["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            snapshot["sha256"] = ""
            snapshot["hash_status"] = f"skipped_gt_{SMALL_FILE_HASH_LIMIT}_bytes"
    except OSError as exc:
        snapshot["error"] = str(exc)
    return snapshot


def _iter_candidate_files(workspace: Path) -> list[Path]:
    ignored_parts = {".git", "build", "node_modules", "__pycache__", ".venv", "venv"}
    files: list[Path] = []
    try:
        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(workspace)
            except ValueError:
                rel = path
            if any(part in ignored_parts for part in rel.parts):
                continue
            files.append(path)
    except OSError:
        return []
    return sorted(files, key=lambda item: _display_path(workspace, item))


def _is_data_candidate(workspace: Path, path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TABULAR_EXTENSIONS:
        return True
    if suffix != ".json":
        return False
    name = path.name.lower()
    if name in JSON_DATA_EXCLUDED_NAMES:
        return False
    try:
        rel_parts = path.relative_to(workspace).parts
    except ValueError:
        rel_parts = path.parts
    if rel_parts and rel_parts[0] in {"data", "datasets", "inputs"}:
        return True
    if len(rel_parts) >= 2 and rel_parts[0] == "assets" and rel_parts[1] in {"charts", "tables"}:
        return True
    return any(token in name for token in ("data", "dataset", "table", "chart", "results", "measurements"))


def _workspace_source_inventory(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {
            "workspace": "",
            "data_files": [],
            "reference_pptx_files": [],
            "artifact_ledger_files": [],
        }
    workspace = workspace.expanduser().resolve()
    if not workspace.exists():
        return {
            "workspace": str(workspace),
            "exists": False,
            "data_files": [],
            "reference_pptx_files": [],
            "artifact_ledger_files": [],
        }
    candidates = _iter_candidate_files(workspace)
    data_candidates = [
        path
        for path in candidates
        if _is_data_candidate(workspace, path)
        and not _display_path(workspace, path).startswith("assets/staged/")
    ]
    reference_pptx_candidates = [path for path in candidates if path.suffix.lower() == ".pptx"]
    data_files = [_file_snapshot(workspace, path) for path in data_candidates[:INVENTORY_LIMIT]]
    reference_pptx_files = [
        _file_snapshot(workspace, path)
        for path in reference_pptx_candidates[:INVENTORY_LIMIT]
    ]
    artifact_ledger_files = [
        _file_snapshot(workspace, workspace / rel_path)
        for rel_path in ARTIFACT_LEDGER_PATHS
        if (workspace / rel_path).exists()
    ]
    return {
        "workspace": str(workspace),
        "exists": True,
        "data_file_count": len(data_candidates),
        "data_file_shown_count": len(data_files),
        "reference_pptx_count": len(reference_pptx_candidates),
        "reference_pptx_shown_count": len(reference_pptx_files),
        "artifact_ledger_count": len(artifact_ledger_files),
        "data_files": data_files,
        "reference_pptx_files": reference_pptx_files,
        "artifact_ledger_files": artifact_ledger_files,
        "limits": {
            "max_entries_per_group": INVENTORY_LIMIT,
            "sha256_hashed_when_size_lte_bytes": SMALL_FILE_HASH_LIMIT,
        },
    }


def _choice_resolution_seed_summary(design_brief: Any) -> dict[str, Any]:
    if not isinstance(design_brief, dict):
        return {}
    seed = design_brief.get("choice_resolution_seed")
    if not isinstance(seed, dict):
        return {}
    choices = (
        seed.get("resolved_choices")
        if isinstance(seed.get("resolved_choices"), list)
        else []
    )
    routes = (
        seed.get("route_decisions")
        if isinstance(seed.get("route_decisions"), list)
        else []
    )
    route_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    route_ledger = (
        seed.get("route_decision_ledger")
        if isinstance(seed.get("route_decision_ledger"), dict)
        else {}
    )
    ledger_routes = (
        route_ledger.get("routes")
        if isinstance(route_ledger.get("routes"), list)
        else []
    )
    ledger_route_status = {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in ledger_routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    return {
        "exists": True,
        "contract_version": str(seed.get("contract_version") or ""),
        "seed_kind": str(seed.get("seed_kind") or ""),
        "stable_prompt_id": str(seed.get("stable_prompt_id") or ""),
        "answered_by": str(seed.get("answered_by") or ""),
        "choice_ids": [
            str(item.get("id") or "").strip()
            for item in choices
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ],
        "route_status": route_status,
        "route_ledger_version": str(route_ledger.get("ledger_version") or ""),
        "route_ledger_status": ledger_route_status,
        "route_ledger_active_routes": sorted(
            route_id for route_id, active in ledger_route_status.items() if active
        ),
        "replay_inputs": seed.get("replay_inputs") if isinstance(seed.get("replay_inputs"), dict) else {},
    }


def _design_brief_style_preset(design_brief: Any) -> str:
    if not isinstance(design_brief, dict):
        return "executive-clinical"
    for container_key in ("style_system", "visual_system"):
        container = design_brief.get(container_key)
        if isinstance(container, dict):
            value = str(container.get("style_preset") or "").strip()
            if value:
                return value
    value = str(design_brief.get("style_preset") or "").strip()
    return value or "executive-clinical"


def _workspace_context(workspace: Path | None) -> str:
    if workspace is None:
        return "Workspace: <none yet>"
    workspace = workspace.expanduser().resolve()
    design_brief = _load_json(workspace / "design_brief.json")
    files = {
        "design_brief.json": design_brief,
        "content_plan.json": _load_json(workspace / "content_plan.json"),
        "evidence_plan.json": _load_json(workspace / "evidence_plan.json"),
        "asset_plan.json": _load_json(workspace / "asset_plan.json"),
        "outline.json": _load_json(workspace / "outline.json"),
        "notes.md": _read_optional(workspace / "notes.md")[:3000] or "<missing>",
    }
    blocks = [f"Workspace: {workspace}"]
    choice_seed_summary = _choice_resolution_seed_summary(design_brief)
    if choice_seed_summary:
        blocks.append(
            "\ndesign_brief.choice_resolution_seed summary:\n"
            + _compact_json(choice_seed_summary, limit=2500)
        )
    treatment_profile = preset_treatment_profile(_design_brief_style_preset(design_brief))
    blocks.append(
        "\npreset treatment profile for design contract:\n"
        + _compact_json(treatment_profile, limit=4200)
    )
    for name, value in files.items():
        if name.endswith(".json"):
            blocks.append(f"\n{name}:\n{_compact_json(value)}")
        else:
            blocks.append(f"\n{name}:\n{value}")
    return "\n".join(blocks)


def _renderer_treatment_context_for_preset(preset: Any) -> dict[str, Any]:
    profile = preset_treatment_profile(str(preset or "").strip() or "executive-clinical")
    return {
        "renderer_treatment_signature": profile.get("renderer_treatment_signature"),
        "renderer_treatment_defaults": profile.get("renderer_treatment_defaults"),
        "renderer_treatment_fields": profile.get("renderer_treatment_fields"),
    }


def _style_reference_match_context(user_prompt: str) -> str:
    matches = rank_style_references(user_prompt, limit=5)
    mix_plan = style_reference_mix_plan(user_prompt, limit=3)
    primary = mix_plan.get("primary") if isinstance(mix_plan.get("primary"), dict) else {}
    secondaries = (
        mix_plan.get("secondary_influences")
        if isinstance(mix_plan.get("secondary_influences"), list)
        else []
    )
    reference_by_preset = {
        str(item.get("style_preset") or ""): (
            item.get("reference") if isinstance(item.get("reference"), dict) else {}
        )
        for item in matches
        if isinstance(item, dict)
    }
    primary_reference = reference_by_preset.get(str(primary.get("style_preset") or ""), {})
    concise_mix_plan = {
        "mix_plan_version": mix_plan.get("mix_plan_version"),
        "query_summary": str(mix_plan.get("query") or "")[:700],
        "primary_treatment_archetype_ids": _compact_treatment_archetype_ids(
            primary_reference.get("layout_playbook")
        ),
        "style_source_intake": _compact_source_pattern_intake(primary_reference.get("style_source_intake")),
        "secondary_influences": [
            _compact_secondary_mix_influence(item)
            for item in secondaries
            if isinstance(item, dict)
        ],
        "treatment_mix": _compact_treatment_mix(mix_plan.get("treatment_mix")),
        "primary": {
            "style_preset": primary.get("style_preset"),
            "score": primary.get("score"),
            "reference_id": primary.get("reference_id"),
            "reference_name": primary.get("reference_name"),
            "style_dna": primary.get("style_dna"),
            "structural_motif_library": _compact_structural_motif(primary.get("structural_motif_library")),
            "style_metric_profile": _compact_style_metric_profile(primary_reference.get("style_metric_profile")),
            "layout_playbook": _compact_layout_playbook(primary_reference.get("layout_playbook")),
            "style_source_intake": _compact_source_intake(primary_reference.get("style_source_intake")),
            "content_recipe_library": _compact_recipe_plan(primary_reference.get("content_recipe_library")),
            **_renderer_treatment_context_for_preset(primary.get("style_preset")),
        },
        "mixing_rules": mix_plan.get("mixing_rules"),
    }
    compact = [
        {
            "style_preset": item.get("style_preset"),
            "score": item.get("score"),
            "reference_id": _load_reference_field(item, "reference_id"),
            "reference_name": _load_reference_field(item, "reference_name"),
            **_renderer_treatment_context_for_preset(item.get("style_preset")),
            "style_dna": _load_reference_field(item, "style_dna"),
            "structural_motif_library": _compact_structural_motif(
                _load_reference_field(item, "structural_motif_library")
            ),
            "style_metric_profile": _compact_style_metric_profile(
                _load_reference_field(item, "style_metric_profile")
            ),
            "style_source_intake": _compact_source_intake(
                _load_reference_field(item, "style_source_intake")
            ),
            "signature_moves": _load_reference_field(item, "signature_moves"),
            "content_treatments": _load_reference_field(item, "content_treatments"),
            "content_recipe_library": _compact_content_recipe_library(
                item.get("reference") if isinstance(item.get("reference"), dict) else {}
            ),
            "example_storyboard": _load_reference_field(item, "example_storyboard"),
            "layout_playbook": _compact_layout_playbook(_load_reference_field(item, "layout_playbook")),
            "publish_safety": _load_reference_field(item, "publish_safety"),
        }
        for item in matches
    ]
    return _compact_json(
        {
            "purpose": (
            "Use these synthetic style references as publish-safe design-memory hints. "
            "Do not copy external/proprietary slide geometry; recreate with generic source content."
            ),
            "mix_plan": concise_mix_plan,
            "matches": compact,
        },
        limit=10500,
    )


def _atom_workflow_context(user_prompt: str, workspace: Path | None) -> str:
    context = build_workflow_atom_context(
        user_prompt=user_prompt,
        workspace=workspace,
        style_preset=_design_brief_style_preset(_load_json(workspace / "design_brief.json") if workspace else None),
        slide_count=8,
        include_prompt=True,
    )
    return _compact_json(compact_workflow_atom_context(context, include_prompt=True), limit=16000)


def _load_reference_field(match: dict[str, Any], key: str) -> Any:
    reference = match.get("reference") if isinstance(match.get("reference"), dict) else {}
    return reference.get(key)


def _compact_content_recipe_library(reference: dict[str, Any]) -> dict[str, Any]:
    library = reference.get("content_recipe_library") if isinstance(reference.get("content_recipe_library"), dict) else {}
    recipes = library.get("recipes") if isinstance(library.get("recipes"), dict) else {}
    compact_recipes: dict[str, Any] = {}
    for key, recipe in recipes.items():
        if not isinstance(recipe, dict):
            continue
        compact_recipes[str(key)] = {
            "primary_variants": recipe.get("primary_variants"),
            "required_slots": recipe.get("required_slots"),
            "data_roles": recipe.get("data_roles"),
            "treatment_archetype": _compact_treatment_archetypes(
                {str(key): recipe.get("treatment_archetype")}
            ).get(str(key)),
        }
    return {
        "library_version": library.get("library_version"),
        "recipe_signature_keys": sorted((library.get("recipe_signatures") or {}).keys())
        if isinstance(library.get("recipe_signatures"), dict)
        else [],
        "recipes": compact_recipes,
    }


def _compact_treatment_archetype_ids(value: Any) -> dict[str, str]:
    playbook = value if isinstance(value, dict) else {}
    archetypes = playbook.get("treatment_archetypes") if isinstance(playbook.get("treatment_archetypes"), dict) else {}
    out: dict[str, str] = {}
    for treatment_key in REQUIRED_CONTENT_TREATMENTS:
        item = archetypes.get(treatment_key) if isinstance(archetypes.get(treatment_key), dict) else {}
        archetype_id = str(item.get("archetype_id") or "").strip()
        if archetype_id:
            out[treatment_key] = archetype_id
    return out


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


def _compact_structural_motif(value: Any) -> dict[str, Any]:
    motif = value if isinstance(value, dict) else {}
    return {
        "motif_library_version": motif.get("motif_library_version"),
        "background_structure": motif.get("background_structure"),
        "layout_motifs": motif.get("layout_motifs") if isinstance(motif.get("layout_motifs"), list) else [],
        "content_object_rules": (
            motif.get("content_object_rules")
            if isinstance(motif.get("content_object_rules"), list)
            else []
        ),
        "motif_signature": motif.get("motif_signature"),
    }


def _compact_style_metric_profile(value: Any) -> dict[str, Any]:
    profile = value if isinstance(value, dict) else {}
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


def _compact_layout_playbook(value: Any) -> dict[str, Any]:
    playbook = value if isinstance(value, dict) else {}
    return {
        "playbook_version": playbook.get("playbook_version"),
        "treatment_archetypes": _compact_treatment_archetypes(playbook.get("treatment_archetypes")),
        "preferred_variants": (
            playbook.get("preferred_variants")
            if isinstance(playbook.get("preferred_variants"), list)
            else []
        )[:10],
        "treatment_variant_map": (
            playbook.get("treatment_variant_map")
            if isinstance(playbook.get("treatment_variant_map"), dict)
            else {}
        ),
        "opening_sequence": (
            playbook.get("opening_sequence")
            if isinstance(playbook.get("opening_sequence"), list)
            else []
        )[:6],
        "content_rules": (
            playbook.get("content_rules")
            if isinstance(playbook.get("content_rules"), list)
            else []
        )[:5],
        "avoid_variants": (
            playbook.get("avoid_variants")
            if isinstance(playbook.get("avoid_variants"), list)
            else []
        ),
    }


def _compact_treatment_archetypes(value: Any) -> dict[str, Any]:
    archetypes = value if isinstance(value, dict) else {}
    compact: dict[str, Any] = {}
    for treatment_key in REQUIRED_CONTENT_TREATMENTS:
        item = archetypes.get(treatment_key) if isinstance(archetypes.get(treatment_key), dict) else {}
        if not item:
            continue
        compact[treatment_key] = {
            "archetype_id": item.get("archetype_id"),
            "treatment_key": item.get("treatment_key") or treatment_key,
            "structure": item.get("structure"),
            "object_pattern": item.get("object_pattern"),
            "required_fields": item.get("required_fields") if isinstance(item.get("required_fields"), list) else [],
            "primary_variants": item.get("primary_variants") if isinstance(item.get("primary_variants"), list) else [],
            "title_layout": item.get("title_layout"),
            "footer_mode": item.get("footer_mode"),
            "archetype_signature": item.get("archetype_signature"),
            "semantic_signature": item.get("semantic_signature") or _semantic_archetype_signature(item),
        }
    return compact


def _compact_source_intake(value: Any) -> dict[str, Any]:
    intake = value if isinstance(value, dict) else {}
    compact_sources: list[dict[str, Any]] = []
    for source in intake.get("sources", []):
        if not isinstance(source, dict):
            continue
        compact_sources.append(
            {
                "source_id": source.get("source_id"),
                "source_status": source.get("source_status"),
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
                "forbidden_materials": (
                    source.get("forbidden_materials")
                    if isinstance(source.get("forbidden_materials"), list)
                    else []
                )[:4],
            }
        )
    return {
        "manifest_version": intake.get("manifest_version"),
        "route_id": intake.get("route_id"),
        "derivation_mode": intake.get("derivation_mode"),
        "source_ids": intake.get("source_ids") if isinstance(intake.get("source_ids"), list) else [],
        "required_synthetic_content": (
            intake.get("required_synthetic_content")
            if isinstance(intake.get("required_synthetic_content"), list)
            else []
        ),
        "sources": compact_sources,
    }


def _compact_source_pattern_intake(value: Any) -> dict[str, Any]:
    intake = value if isinstance(value, dict) else {}
    patterns: list[str] = []
    observations: list[str] = []
    for source in intake.get("sources", []):
        if not isinstance(source, dict):
            continue
        for pattern in source.get("generic_slide_patterns", []):
            if isinstance(pattern, str) and pattern not in patterns:
                patterns.append(pattern)
        for observation in source.get("generic_style_observations", []):
            if isinstance(observation, str) and observation not in observations:
                observations.append(observation)
    return {
        "manifest_version": intake.get("manifest_version"),
        "route_id": intake.get("route_id"),
        "source_ids": intake.get("source_ids") if isinstance(intake.get("source_ids"), list) else [],
        "derivation_mode": intake.get("derivation_mode"),
        "generic_slide_patterns": patterns[:8],
        "generic_style_observations": observations[:6],
    }


def _compact_secondary_mix_influence(value: Any) -> dict[str, Any]:
    item = value if isinstance(value, dict) else {}
    motif = _compact_structural_motif(item.get("structural_motif_library"))
    metric = _compact_style_metric_profile(item.get("style_metric_profile"))
    return {
        "style_preset": item.get("style_preset"),
        "score": item.get("score"),
        "reference_id": item.get("reference_id"),
        "reference_name": item.get("reference_name"),
        "style_dna": item.get("style_dna"),
        "background_structure": motif.get("background_structure"),
        "layout_motifs": (motif.get("layout_motifs") or [])[:4],
        "motif_signature": motif.get("motif_signature"),
        "metric_signature": metric.get("metric_signature"),
        "density_level": metric.get("density_level"),
        "body_words_per_content_slide": metric.get("body_words_per_content_slide"),
        "max_primary_objects": metric.get("max_primary_objects"),
        **_renderer_treatment_context_for_preset(item.get("style_preset")),
    }


def _compact_treatment_mix(value: Any) -> dict[str, Any]:
    mix = value if isinstance(value, dict) else {}
    compact: dict[str, Any] = {}
    for treatment, details in mix.items():
        if not isinstance(details, dict):
            continue
        secondary_notes: list[dict[str, Any]] = []
        for item in details.get("optional_secondary_influences", [])[:2]:
            if not isinstance(item, dict):
                continue
            secondary_notes.append(
                {
                    "from_style_preset": item.get("from_style_preset"),
                    "reference_id": item.get("reference_id"),
                    "treatment": item.get("treatment"),
                }
            )
        compact[str(treatment)] = {
            "primary": details.get("primary"),
            "optional_secondary_influences": secondary_notes,
        }
    return compact


def _compact_recipe_plan(value: Any) -> dict[str, Any]:
    library = value if isinstance(value, dict) else {}
    signatures = library.get("recipe_signatures") if isinstance(library.get("recipe_signatures"), dict) else {}
    recipes = library.get("recipes") if isinstance(library.get("recipes"), dict) else {}
    archetype_ids: dict[str, str] = {}
    for treatment_key in REQUIRED_CONTENT_TREATMENTS:
        recipe = recipes.get(treatment_key) if isinstance(recipes.get(treatment_key), dict) else {}
        archetype = (
            recipe.get("treatment_archetype")
            if isinstance(recipe.get("treatment_archetype"), dict)
            else {}
        )
        archetype_id = str(archetype.get("archetype_id") or "").strip()
        if archetype_id:
            archetype_ids[treatment_key] = archetype_id
    return {
        "library_version": library.get("library_version"),
        "recipe_signature_keys": sorted(signatures.keys()),
        "treatment_archetype_ids": archetype_ids,
        "authoring_contract": (library.get("authoring_contract") if isinstance(library.get("authoring_contract"), list) else [])[:2],
    }


def _reference_context() -> str:
    refs = {
        "DESIGN.md": ROOT / "DESIGN.md",
        "planning_schema.md": ROOT / "references" / "planning_schema.md",
        "outline_schema.md": ROOT / "references" / "outline_schema.md",
    }
    blocks = []
    for label, path in refs.items():
        text = _read_optional(path)
        if not text:
            blocks.append(f"{label}: <missing>")
            continue
        blocks.append(f"{label}:\n{text[:6000]}")
    return "\n\n".join(blocks)


PROMPT_TEMPLATE = """\
You are the design-contract scout for a reproducible PowerPoint deck build.
Your job is to convert the user's request into a concrete contract BEFORE
outline.json is written.

Return ONLY valid JSON. Do not write prose outside JSON.

Core rule: preserve creative judgment, but make every decision explicit enough
that another agent can rebuild the same deck family later: preset, palette,
background, header/footer treatment, slide structure, asset posture, evidence
policy, and QA gates.
Also emit a compact reproducibility contract that ties the selected style seed
to the exact background, treatment pools, slide-structure mix, chart/table
posture, artifact ledger paths, replay commands, and QA evidence. This is the
replay layer for mix-and-match styling: it should make the deck varied but not
random, and should let a later agent rebuild the same choices without reopening
the full prompt.

Use the selected synthetic style reference's `structural_motif_library` before
the playbook: its background structure, layout motifs, and content-object
rules should decide whether the deck behaves like a lab run report, command
console, workflow workbench, evidence rail, atlas plate, case-study journey, or
editorial masthead. Copy the motif signature into `style_replay` and the motif
rules into `structure_replay`, so a later outline author can reproduce the same
structure instead of only the same chrome.
Use the selected reference's `style_metric_profile` to set density,
whitespace, body-word budget, maximum primary object count, visual hierarchy,
evidence-object mix, source burden, footer posture, and artifact/readability
bias. Translate it into `readability_contract`, `structure_blueprint`,
`asset_plan`, and `reproducibility_contract.style_replay` so outline authors
know when to split a slide or convert prose into a chart/table/figure.
Then use the selected reference's `layout_playbook` as the primary source for
`structure_blueprint.slide_sequence`, `allowed_variants`, and
`forbidden_variants`. Do not let all presets collapse to the same title,
dashboard, comparison, chart, and table order. The playbook should change the
actual slide variants and content posture, while the renderer still uses only
supported outline variants.
When the style-reference context includes `mix_plan`, keep its primary
reference authoritative for preset, layout playbook, source/footer posture, and
supported variants. Use secondary references only as named influences for
specific content treatments, and record those borrowed influences in
`choice_resolution` and the structure rationale.
Use `renderer_treatment_signature` as the compact replay/audit key for the
title/footer/chart/table/figure/stats/matrix/callout posture. Copy the selected
reference's `renderer_treatment_defaults` into `style_system` and
`reproducibility_contract.style_replay`, then override only with supported
fields when the user's evidence shape requires it.
Use `content_recipe_library` as the content-slot grammar for each treatment:
chart, table, figure, dashboard, comparison, decision, and references slides
should name their treatment key, required slots, data roles, source posture, and
supported variant choices before outline authoring.

For data-derived figures, editable chart JSON, or summary tables, make the
artifact contract auditable before outline authoring: include source path,
source fingerprint fields, selected columns/fields, rows used, point/series
counts, target slide box, figure export size, DPI, and readable label-size
assumptions. The main agent should be able to copy these decisions into
design_brief.analysis_artifact_plan, figure_export_contract, asset_plan, and
outline asset refs without guessing. If scaffolded data artifacts are likely,
include `assets/analysis_summary.json` as the first-read handoff before
outline binding.

If workspace context includes `design_brief.choice_resolution_seed`, copy that
object into the returned top-level `choice_resolution` field and refine only
when the final contract makes a more specific choice. Keep the compact intake
answers, route decisions, active data/style paths, and locked source fields
visible so the deck can be rebuilt from the same first-turn decisions.
If the seed includes `route_decision_ledger`, carry active route evidence into
`choice_resolution.route_decisions` and record any skipped conditional route
with an explicit reason.

Use these repository constraints:
{reference_context}

User request:
{user_prompt}

Stable prompt id:
{stable_id}

Recommended deterministic style seed:
{style_seed}

Available workspace context:
{workspace_context}

Workspace source inventory:
{workspace_source_inventory}

Prompt-to-style reference matches:
{style_reference_matches}

Normal-workflow atom composition context:
{atom_workflow_context}

Use `normal_workflow_atom_context_v1` as an optional first-class style-grammar
route, not as a hard template. The deterministic packet gives a reproducible
seed from the descriptor-only atom atlas. Accept it when it fits the topic,
refine it by returning the strict JSON atom shape, or skip it with a recorded
reason. When accepted or refined, persist the atom replay ledger under
`choice_resolution.atom_composition`, `style_system.style_atom_composition`,
`reproducibility_contract.style_replay.atom_composition`, and the relevant
`structure_blueprint` variant/narrative fields. Use only supported renderer
fields from `deck_style_delta`; never copy external slide geometry.

Return this JSON shape:

{{
  "contract_version": "deck_design_contract_v1",
  "stable_prompt_id": "{stable_id}",
  "user_request_summary": "one concise sentence",
  "missing_inputs": [
    {{
      "question": "high-leverage missing question",
      "why_it_matters": "impact on deck design",
      "default_if_unanswered": "best-judgment assumption"
    }}
  ],
  "assumptions": [
    "explicit assumption to record in notes.md if user does not answer"
  ],
  "choice_resolution": {{
    "contract_version": "deck_choice_resolution_v1",
    "seed_kind": "resolved_intake_answers | scout_refined",
    "stable_prompt_id": "{stable_id}",
    "answered_by": "user | inferred | best_judgment",
    "resolved_choices": [
      {{
        "id": "audience_context | style_density | visual_source_policy",
        "answer": "selected answer or explicit assumption",
        "source_fields": ["design_brief.user_intake"],
        "contract_fields": ["deck_identity.audience"]
      }}
    ],
    "route_decisions": [
      {{
        "id": "data_artifacts | pptx_style_import",
        "active": true,
        "trigger_evidence": "why this route is active or inactive"
      }}
    ],
    "route_decision_ledger": {{
      "ledger_version": "deck_route_decision_ledger_v1",
      "routes": [
        {{
          "id": "intake_questions | design_contract | data_artifacts | pptx_style_import | content_research | source_footer_compaction | rendered_visual_review",
          "active": true,
          "trigger_evidence": ["why this route is active or skipped"]
        }}
      ]
    }},
    "route_ledger_version": "deck_route_decision_ledger_v1",
    "route_ledger_active_routes": [
      "intake_questions",
      "design_contract"
    ],
    "atom_composition": {{
      "schema_version": "normal_workflow_atom_context_v1",
      "decision": "accept_seed | refine_with_agent_atoms | skip",
      "target_family": "copy from atom context or refined strict JSON",
      "source": "deterministic_seed | agent_refined | skipped",
      "skip_reason": "required only when decision is skip",
      "preferred_variants": ["supported variants selected for this deck"],
      "narrative_arc": ["ordered story beats selected for this deck"],
      "deck_style_delta": {{"supported_renderer_field": "supported value"}},
      "style_atom_composition": {{"schema_version": "style_atom_composition_v1"}}
    }},
    "selected_renderer_treatment_signature": "copy from the selected preset defaults, or the recomputed supported override signature",
    "replay_inputs": {{
      "answers": "intake_answers.json or explicit assumptions",
      "packet": "deck_start_packet.json",
      "route_decision_ledger": "deck_start_packet.json:route_decision_ledger",
      "atom_workflow_context": "deck_start_packet.json:atom_workflow_context or this prompt's normal_workflow_atom_context_v1 block"
    }},
    "design_fields_locked": [
      "style_system.style_mix_matrix",
      "readability_contract",
      "evidence_plan.source_policy",
      "analysis_artifact_plan",
      "figure_export_contract"
    ]
  }},
  "reproducibility_contract": {{
    "contract_version": "deck_reproducibility_contract_v1",
    "stable_prompt_id": "{stable_id}",
    "style_seed": "{style_seed}",
    "choice_source": "intake_answers.json | explicit user request | best-judgment assumptions",
    "renderer": "pptxgenjs",
    "locked_design_fields": [
      "style_system.style_preset",
      "style_system.background_system",
      "style_system.style_mix_matrix",
      "style_system.renderer_treatment_signature",
      "structure_blueprint.slide_sequence",
      "evidence_and_assets.analysis_artifact_plan",
      "readability_contract",
      "qa_contract"
    ],
    "replay_inputs": {{
      "user_prompt_hash_source": "original user request",
      "deck_start_packet": "deck_start_packet.json if present",
      "intake_answers": "intake_answers.json or explicit assumptions",
      "design_contract": "design_contract.json",
      "artifact_manifest": "assets/artifacts_manifest.json when generated artifacts exist",
      "analysis_summary": "assets/analysis_summary.json when generated artifacts exist",
      "reference_pptx_style_fragment": "style_extract_design_brief.json when style import is active"
    }},
    "style_replay": {{
      "style_preset": "same as style_system.style_preset",
      "palette_key": "same as style_system.palette_key",
      "background_system": "same as style_system.background_system",
      "structural_motif_library_version": "style_reference_structural_motif_library_v1",
      "structural_motif_signature": "copy selected reference structural_motif_library.motif_signature",
      "background_structure": "copy selected reference structural_motif_library.background_structure",
      "layout_motifs": ["copy selected reference structural_motif_library.layout_motifs used by the contract"],
      "style_metric_profile_version": "style_reference_metric_profile_v1",
      "style_metric_signature": "copy selected reference style_metric_profile.metric_signature",
      "density_level": "copy selected reference style_metric_profile.density_level",
      "whitespace_ratio_target": "copy selected reference style_metric_profile.whitespace_ratio_target",
      "body_words_per_content_slide": "copy selected reference style_metric_profile.body_words_per_content_slide",
      "header_variant_pool": ["same supported entries as style_mix_matrix.header_variant_pool"],
      "title_layout_pool": ["same supported entries as style_mix_matrix.title_layout_pool"],
      "footer_pool": ["same supported entries as style_mix_matrix.footer_pool"],
      "chart_treatment_pool": ["same supported entries as style_mix_matrix.chart_treatment_pool"],
      "table_treatment_pool": ["same supported entries as style_mix_matrix.table_treatment_pool"],
      "figure_table_treatment_pool": ["same supported entries as style_mix_matrix.figure_table_treatment_pool"],
      "renderer_treatment_signature": "title_layout:...|footer_mode:...|chart_treatment:...|table_treatment:...|figure_table_treatment:...|stats_mode:...|matrix_mode:...|summary_callout_mode:...",
      "atom_composition": {{
        "schema_version": "style_atom_composition_v1",
        "target_family": "accepted/refined atom target family",
        "source_families": ["families that contributed atoms"],
        "preferred_variants": ["variants that influenced structure"],
        "narrative_arc": ["beats that influenced structure"],
        "deck_style_delta": {{"supported renderer fields used": "values"}}
      }},
      "renderer_treatment_defaults": {{
        "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
        "footer_mode": "standard | source-line",
        "chart_treatment": "standard | facts-below | facts-right | minimal | hero-stat | threshold-band | sparse-wide",
        "table_treatment": "standard | compact-ledger | readout-sidecar | decision-matrix | journal-grid",
        "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar",
        "stats_mode": "tiles | feature-left | policy-bands",
        "matrix_mode": "cards | open-quadrants",
        "summary_callout_mode": "default | lab-box"
      }},
      "mix_rule": "one sentence describing deterministic treatment rotation from style_seed",
      "variation_boundaries": ["what may vary between sibling decks", "what must stay locked inside this deck"]
    }},
    "structure_replay": {{
      "target_slide_count": 0,
      "slide_variant_mix": ["ordered variants from structure_blueprint.slide_sequence"],
      "content_recipe_library_version": "style_reference_content_recipe_library_v1",
      "content_recipe_signatures": "copy selected reference content_recipe_library.recipe_signatures",
      "treatment_archetype_semantic_signatures": "copy selected reference layout_playbook.treatment_archetypes semantic_signature values",
      "structural_motif_library_version": "style_reference_structural_motif_library_v1",
      "structural_motif_signature": "copy selected reference structural_motif_library.motif_signature",
      "structural_content_object_rules": ["copy rules that changed chart/table/figure/source placement"],
      "evidence_anchor_rule": "how each evidence/data slide gets a visible chart, table, figure, or image anchor",
      "white_space_rule": "how to avoid awkward sparse or overfilled regions"
    }},
    "artifact_replay": {{
      "local_data_needed": false,
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json",
      "figure_script": "assets/make_figures.py or none",
      "rebuild_commands": []
    }},
    "replay_commands": [
      "python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ],
    "acceptance_evidence": [
      "design_contract_apply_report.json",
      "build/workspace_readiness.json",
      "build/build_workspace_report.json",
      "build/delivery_readiness.json"
    ]
  }},
  "deck_identity": {{
    "working_title": "deck title",
    "audience": "scientific peer | executive | public | student | custom",
    "use_context": "live talk | leave-behind | report | pitch | teaching | poster",
    "target_outcome": "what the audience should believe, decide, or do",
    "density": "low | medium | high"
  }},
  "design_dna": "lab results dashboard | board risk memo | product/investor reveal | editorial report | civic science policy | custom",
  "style_system": {{
    "style_preset": "loadable preset name",
    "palette_key": "preset-default or palette key",
    "font_pair": "system_clean_v1 | editorial_serif_v1 | clean_modern_v1",
    "style_seed": "{style_seed}",
    "background_system": "white report | dark stage | light editorial | source-backed visual | generated concept | custom",
    "preset_treatment_profile": "copy/refine the workspace preset treatment profile so preset-specific heading/footer/chart/figure pools are reproducible",
    "renderer_treatment_signature": "compact replay key for selected title/footer/chart/table/figure/stats/matrix/callout posture",
    "style_atom_composition": {{
      "schema_version": "style_atom_composition_v1",
      "target_family": "accepted/refined atom target family",
      "source_families": ["families that contributed atoms"],
      "preferred_variants": ["variants selected for outline authoring"],
      "narrative_arc": ["story beats selected for outline authoring"]
    }},
    "style_atom_preferred_variants": ["ordered supported variants from accepted/refined atom route"],
    "style_atom_narrative_arc": ["ordered story beats from accepted/refined atom route"],
    "renderer_treatment_defaults": {{
      "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
      "footer_mode": "standard | source-line",
      "chart_treatment": "standard | facts-below | facts-right | minimal | hero-stat | threshold-band | sparse-wide",
      "table_treatment": "standard | compact-ledger | readout-sidecar | decision-matrix | journal-grid",
      "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar",
      "stats_mode": "tiles | feature-left | policy-bands",
      "matrix_mode": "cards | open-quadrants",
      "summary_callout_mode": "default | lab-box"
    }},
    "style_reference": {{
      "catalog_version": "style_reference_catalog_v1",
      "reference_id": "copy from the selected synthetic reference",
      "reference_name": "copy from the selected synthetic reference",
      "source_status": "synthetic_original_publish_safe | license_clear_public_source | reconstructed_generic",
      "style_dna": "the selected reference's reusable visual grammar",
      "structural_motif_library": {{
        "motif_library_version": "style_reference_structural_motif_library_v1",
        "background_structure": "the selected reference page system",
        "layout_motifs": ["named structure moves such as run metadata plate or workflow lanes"],
        "content_object_rules": ["rules that place charts, tables, figures, decisions, caveats, and sources"],
        "motif_signature": "copy from selected reference"
      }},
      "style_metric_profile": {{
        "metric_profile_version": "style_reference_metric_profile_v1",
        "density_level": "copy selected preset density posture",
        "whitespace_ratio_target": 0.25,
        "body_words_per_content_slide": [24, 48],
        "max_primary_objects": 2,
        "visual_hierarchy": "copy selected preset evidence scan path",
        "evidence_object_mix": {{"chart": 0.25, "table": 0.25, "figure": 0.25, "prose": 0.25}},
        "source_burden": "copy selected source burden",
        "footer_posture": "copy selected footer/source posture",
        "artifact_bias": ["copy selected artifact preferences"],
        "readability_bias": ["copy selected text and density constraints"],
        "metric_signature": "copy selected metric signature"
      }},
      "signature_moves": ["2-4 moves that make this deck family distinct"],
      "example_storyboard": {{
        "storyboard_version": "style_reference_example_storyboard_v1",
        "topic": "synthetic example topic used only as style-memory evidence",
        "title": "publish-safe synthetic title",
        "chart": "chart vocabulary, labels, and readout pattern",
        "table": "table headers/rows pattern",
        "figure": "figure/sidebar/panel vocabulary",
        "decision": "decision headers/rows pattern"
      }},
      "content_treatments": {{
        "title": "how this reference presents title slides",
        "comparison": "how this reference presents comparisons",
        "chart": "how this reference presents charts",
        "table": "how this reference presents tables",
        "figure": "how this reference presents figures/images",
        "dashboard": "how this reference presents dashboards",
        "decision": "how this reference presents decisions",
        "references": "how this reference presents sources/refs"
      }},
      "content_recipe_library": {{
        "library_version": "style_reference_content_recipe_library_v1",
        "recipe_signatures": "copy from selected reference",
        "authoring_contract": ["how treatment-key recipes must be used before outline authoring"]
      }},
      "publish_safety": {{
        "status": "publish_safe",
        "basis": "synthetic reference or license-clear public source notes"
      }},
      "style_source_intake": {{
        "manifest_version": "style_reference_source_manifest_v1",
        "route_id": "copy from selected reference",
        "source_ids": ["license/public-guidance source ids"],
        "derivation_mode": "metadata_only | synthetic_reconstruction | linked_attribution",
        "publish_safety": {{
          "status": "publish_safe_descriptor",
          "basis": "source URLs and license notes are recorded; bundled deck material is not copied"
        }}
      }},
      "layout_playbook": {{
        "playbook_version": "style_reference_layout_playbook_v1",
        "preferred_variants": ["ordered supported outline variants for this preset"],
        "treatment_variant_map": {{
          "title": ["title"],
          "comparison": ["comparison-2col", "split", "matrix"],
          "chart": ["chart"],
          "table": ["table", "lab-run-results"],
          "figure": ["image-sidebar", "scientific-figure", "flow"],
          "dashboard": ["stats", "lab-run-results"],
          "decision": ["standard", "table"],
          "references": ["table"]
        }},
        "treatment_archetypes": {{
          "title": {{
            "archetype_id": "selected title archetype such as lab-run-metadata-plate-opener",
            "structure": "how the opener is organized beyond the title variant",
            "required_fields": ["scope", "evidence promise", "decision context"],
            "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
            "archetype_signature": "copy selected reference archetype signature",
            "semantic_signature": "copy selected semantic signature that excludes preset/id naming"
          }},
          "chart": {{
            "archetype_id": "selected body archetype such as clean-assay-report-chart-readout",
            "structure": "how this treatment presents evidence beyond the renderer variant",
            "object_pattern": "chart/table/figure/dashboard/decision object grammar",
            "required_fields": ["evidence object", "readout", "caveat", "source"],
            "primary_variants": ["supported outline variants for the treatment"],
            "archetype_signature": "copy selected reference archetype signature",
            "semantic_signature": "copy selected semantic signature that excludes preset/id naming"
          }},
          "references": {{
            "archetype_id": "selected source/provenance archetype such as lab-source-id-refs-table",
            "structure": "how footers, page numbers, source IDs, and references tables work",
            "required_fields": ["source id", "claim link", "usage note"],
            "footer_mode": "standard | source-line",
            "archetype_signature": "copy selected reference archetype signature",
            "semantic_signature": "copy selected semantic signature that excludes preset/id naming"
          }}
        }},
        "slide_archetypes": [
          {{
            "role": "evidence",
            "variant": "chart",
            "treatment_key": "chart",
            "layout_note": "reference-specific composition note"
          }}
        ],
        "opening_sequence": [],
        "content_rules": ["rules that make this preset structurally distinct"],
        "avoid_variants": ["variants to avoid for this reference"]
      }}
    }},
    "header_system": {{
      "header_mode": "bar | stack | eyebrow | lab-clean | lab-card",
      "header_variant": "auto | left-accent | split-rule | title-rule | side-rail | top-bottom-rule | plain",
      "header_variants": ["left-accent", "split-rule", "title-rule", "side-rail", "top-bottom-rule", "plain"],
      "header_rule_color": "accent_primary | accent_secondary | hex"
    }},
    "footer_system": {{
      "footer_mode": "standard | source-line",
      "footer_page_numbers": true,
      "footer_source_label": "Sources",
      "footer_refs_label": "Refs"
    }},
    "title_slide_system": {{
      "title_layout": "split-hero | lab-plate | command-center | poster | masthead | light-atlas",
      "title_motif": "orbit | network | editorial | none",
      "cover_chips_or_tags": ["optional recurring chips"]
    }},
    "section_system": {{
      "section_motif": "rail-dots | none",
      "section_count": 0
    }},
    "figure_table_system": {{
      "figure_table_treatment": "figure-first | table-first | stats-strip | image-sidebar",
      "table_treatment": "standard | compact-ledger | readout-sidecar | decision-matrix | journal-grid"
    }},
    "chart_system": {{
      "chart_treatment": "standard | facts-below | facts-right | minimal | hero-stat | threshold-band | sparse-wide"
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
      "mix_rule": "how to rotate treatments across slides without making the deck feel random",
      "do_not_mix": ["specific pairings that would break the design DNA"]
    }}
  }},
  "structure_blueprint": {{
    "target_slide_count": 0,
    "slide_sequence": [
      {{
        "slide_id": "s1",
        "role": "title | context | evidence | method | comparison | implication | close",
        "variant": "supported outline variant",
        "treatment_key": "title | comparison | chart | table | figure | dashboard | decision | references",
        "visual_strategy": "figure | table | image-sidebar | cards | flow | narrative",
        "required_assets": [],
        "source_policy": "none | cite key claim | source every factual claim"
      }}
    ],
    "allowed_variants": [],
    "forbidden_variants": []
  }},
  "evidence_and_assets": {{
    "proof_burden": "concept | sourced report | technical validation | clinical/lab claim",
    "research_needed": true,
    "local_data_needed": false,
    "analysis_artifact_plan": {{
      "candidate_data_files": [],
      "spreadsheet_inputs": [],
      "required_scripts": [],
      "figure_scripts": [],
      "artifact_manifest": "assets/artifacts_manifest.json",
      "analysis_summary": "assets/analysis_summary.json",
      "analysis_summary_markdown": "assets/analysis_summary.md",
      "chart_json_outputs": [],
      "table_outputs": [],
      "rebuild_commands": [],
      "artifact_registry": [
        {{
          "id": "artifact_id",
          "path": "relative or absolute path",
          "producer": "script or source file",
          "used_on_slides": [],
          "provenance": "data/source/method note",
          "analysis_metadata": {{
            "artifact_role": "figure | chart_json | summary_table",
            "source_path": "relative or absolute source data path",
            "source_sha256": "sha256 or pending until generated",
            "source_bytes": 0,
            "selected_columns": ["field_a", "field_b"],
            "rows_used": 0,
            "series_count": 0,
            "points": 0,
            "target_box": "5.0x3.3 in",
            "figure_size_inches": [6.4, 3.6],
            "figure_dpi": 180,
            "axis_label_min_pt": 8
          }}
        }}
      ]
    }},
    "asset_plan": {{
      "images": [],
      "charts": [],
      "tables": [],
      "icons": [],
      "backgrounds": [],
      "generated_images": []
    }},
    "figure_export_contract": {{
      "script": "assets/make_figures.py or none",
      "rerun_command": "python3 assets/make_figures.py",
      "outputs": [
        {{
          "path": "assets/figures/example.png",
          "target_slide": "s3",
          "target_variant": "image-sidebar | scientific-figure | lab-run-results",
          "target_box": "5.0x3.3 in",
          "figure_size_inches": [6.4, 3.6],
          "figure_dpi": 180,
          "axis_label_min_pt": 8,
          "legend_pt": 8,
          "x_label_rotation": 0,
          "crop_rule": "tight content bbox, <=0.08 in visual padding, no large internal whitespace"
        }}
      ]
    }}
  }},
  "continuity_rules": {{
    "recurring_tags": [],
    "carry_forward_rule": "how cover/title motifs recur intentionally",
    "source_footer_rule": "what appears in footer/sources/refs"
  }},
  "slide_quality_contract": {{
    "contract_version": "slide_quality_contract_v1",
    "readability_targets": {{
      "min_title_pt": 24,
      "min_body_pt": 12,
      "min_caption_pt": 7.5,
      "chart_label_min_pt": 7,
      "footer_reserved_inches": 0.25,
      "max_title_lines": 2,
      "max_slide_text_lines": 12,
      "max_slide_words": 110,
      "max_slide_chars": 780
    }},
    "layout_targets": {{
      "evidence_anchor_required": true,
      "avoid_repeated_card_grids": true,
      "fail_on_awkward_whitespace": true,
      "prefer_source_edit_over_pptx_patch": true,
      "sparse_slide_allowed_only_when_intentional": true,
      "source_footer_rule": "compact source/ref IDs in footers; full references in editable References table slides"
    }},
    "artifact_quality_targets": {{
      "required_when_data_artifacts_active": false,
      "must_record": [
        "source data fingerprints",
        "producer script fingerprints",
        "selected columns or data slices",
        "figure/chart/table output paths",
        "target slide IDs and variants",
        "target figure box",
        "figure size and DPI",
        "axis/chart label font assumptions",
        "image whitespace measurement or trim rule",
        "rerun and inspect commands"
      ]
    }},
    "qa_gates": {{
      "fail_on": ["planning_warnings", "overflow", "overlap", "placeholder_text", "whitespace_warnings", "design_readability_warnings"],
      "required_commands": [
        "python3 scripts/validate_planning.py --workspace <deck>",
        "python3 scripts/build_workspace.py --workspace <deck> --qa --skip-render --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
        "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
        "python3 scripts/report_delivery_readiness.py --workspace <deck>"
      ]
    }}
  }},
  "readability_contract": {{
    "min_title_pt": 26,
    "min_body_pt": 15,
    "min_caption_pt": 8,
    "max_title_lines": 2,
    "max_slide_text_lines": 8,
    "max_slide_words": 105,
    "max_slide_chars": 700,
    "footer_reserved_inches": 0.34,
    "chart_label_min_pt": 8,
    "table_density_rule": "split or summarize tables that force unreadable text",
    "whitespace_rule": "avoid awkward empty regions; use figure/sidebar/table variants when content is sparse",
    "figure_crop_rule": "export tight bounding boxes and trim exterior whitespace before insertion"
  }},
  "speed_contract": {{
    "renderer": "pptxgenjs by default; Python fallback only for legacy renderer-specific behavior",
    "first_pass": "render-free schema/preflight/geometry QA before slide rendering",
    "render_policy": "render only after source files are stable or when visual judgment matters",
    "asset_policy": "reuse local/generated artifacts before network assets unless the deck needs source-backed imagery",
    "conversion_hint": "use persistent LibreOffice/unoserver when available for repeated render QA"
  }},
  "subagent_handoff": {{
    "ask_user_first": true,
    "question_packet": "scripts/emit_deck_start_packet.py or scripts/emit_deck_intake_prompt.py --codex-ui",
    "design_contract_scout": "this prompt; return strict JSON",
    "content_research_scout": "scripts/emit_content_research.py when claims need sourced anchors",
    "data_analysis_scout": "scripts/emit_data_analysis_prompt.py when local data, spreadsheets, or figures drive claims",
    "style_content_router": "scripts/emit_style_content_router.py for non-trivial or visually ambiguous decks",
    "outline_critique": "scripts/emit_outline_critique.py before final build",
    "visual_qa": "render_slides.py --emit-visual-prompt or build_workspace.py --visual-review after render"
  }},
  "agent_execution_plan": {{
    "phases": [
      {{
        "id": "intake",
        "owner": "main_agent",
        "trigger": "missing high-leverage personalization choices",
        "commands": ["python3 scripts/emit_deck_start_packet.py --workspace <deck> --user-prompt '<request>'"],
        "writes": ["intake_answers.json", "design_brief.json:user_intake"],
        "continue_when": "answers or explicit assumptions are persisted"
      }},
      {{
        "id": "design_contract",
        "owner": "style_scout_or_main_agent",
        "trigger": "before outline authoring",
        "commands": ["python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json"],
        "writes": ["design_contract.json", "design_brief.json", "content_plan.json", "evidence_plan.json", "asset_plan.json", "notes.md"],
        "continue_when": "design_contract_apply_report.json records the contract as applied"
      }},
      {{
        "id": "outline_authoring",
        "owner": "main_agent",
        "trigger": "contract is applied and starter outline remains",
        "commands": ["python3 scripts/emit_outline_authoring_prompt.py --workspace <deck> --output <deck>/build/outline_authoring_prompt.md"],
        "writes": ["outline.json", "content_plan.json", "evidence_plan.json", "asset_plan.json"],
        "continue_when": "planning validation has no blocking errors"
      }}
    ],
    "commands": [
      "python3 scripts/report_workspace_readiness.py --workspace <deck>",
      "python3 scripts/advance_workspace.py --workspace <deck>",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ]
  }},
  "qa_contract": {{
    "required_checks": [
      "python3 scripts/validate_planning.py --workspace <deck>",
      "python3 scripts/preflight.py --outline <deck>/outline.json --design-brief <deck>/design_brief.json",
      "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
      "python3 scripts/report_delivery_readiness.py --workspace <deck>"
    ],
    "fail_on": ["planning errors", "overflow", "overlap", "undersized text", "awkward whitespace", "visual review blockers"],
    "visual_risks_to_check": [],
    "placeholder_checks": true,
    "acceptance_evidence": [
      "build/workspace_readiness.json",
      "build/build_workspace_report.json",
      "build/qa/report.json",
      "build/delivery_readiness.json"
    ]
  }},
  "acceptance_evidence": [
    "design_contract_apply_report.json proves the returned contract was applied",
    "build/workspace_readiness.json proves source planning is clean or names the next source edit",
    "build/build_workspace_report.json fingerprints sources, artifacts, QA reports, and output PPTX",
    "build/delivery_readiness.json records final delivery status and blocking reasons"
  ],
  "authoring_instructions": [
    "Use style_system.style_seed={style_seed!r} unless the user explicitly supplied a different seed, and record any override in notes.md.",
    "specific instruction the main agent must follow when writing design_brief.json and outline.json"
  ]
}}
"""


def render_contract_prompt(*, user_prompt: str, workspace: Path | None) -> str:
    stable_id = _stable_id(user_prompt)
    return PROMPT_TEMPLATE.format(
        user_prompt=user_prompt.strip(),
        stable_id=stable_id,
        style_seed=stable_id,
        workspace_context=_workspace_context(workspace),
        workspace_source_inventory=_compact_json(_workspace_source_inventory(workspace), limit=3500),
        style_reference_matches=_style_reference_match_context(user_prompt),
        atom_workflow_context=_atom_workflow_context(user_prompt, workspace),
        reference_context=_reference_context(),
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit a reproducible deck design-contract prompt.")
    parser.add_argument("--user-prompt", required=True, help="Original user deck request")
    parser.add_argument("--workspace", default="", help="Optional deck workspace directory")
    parser.add_argument("--output", default="", help="Optional path to write the prompt")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace) if args.workspace else None
    prompt = render_contract_prompt(user_prompt=args.user_prompt, workspace=workspace)
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(prompt, encoding="utf-8")
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
