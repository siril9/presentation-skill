#!/usr/bin/env python3
"""Focused smoke test for dynamic composition-grammar routing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from composition_grammar_catalog import (  # noqa: E402
    quick_deck_agent_brief,
    route_composition_grammars,
    validate_composition_grammar_catalog,
)
from style_reference_catalog import rank_style_references, style_reference_mix_plan  # noqa: E402
from workflow_atom_context import build_workflow_atom_context, compact_workflow_atom_context  # noqa: E402


def _primary_id(route: dict) -> str:
    primary = route.get("primary") if isinstance(route.get("primary"), dict) else {}
    return str(primary.get("grammar_id") or "")


def main() -> int:
    failures: list[str] = []
    summary = validate_composition_grammar_catalog()
    if not summary.get("passed"):
        failures.extend(summary.get("failures") or ["catalog validation failed"])
    if summary.get("grammar_count") != 8:
        failures.append(f"grammar_count={summary.get('grammar_count')} expected=8")
    if summary.get("unique_structural_signature_count") != 8:
        failures.append("composition grammar structural signatures are not unique")
    role_counts = summary.get("role_system_counts") if isinstance(summary.get("role_system_counts"), dict) else {}
    if role_counts.get("title") != 8:
        failures.append("expected exactly eight title systems")
    if int(role_counts.get("section") or 0) < 6:
        failures.append("expected at least six section systems")
    if int(role_counts.get("evidence") or 0) < 8 or int(role_counts.get("data") or 0) < 8:
        failures.append("expected at least eight evidence and eight data systems")
    if int(summary.get("narrative_arc_count") or 0) < 6:
        failures.append("expected at least six narrative arcs")

    cases = [
        (
            "lab",
            route_composition_grammars(
                topic="RT-LAMP validation run",
                user_prompt="scientific evidence figures, assay table, QC decision",
                style_preset="lab-report",
            ),
            "scientific-evidence-plate",
        ),
        (
            "board",
            route_composition_grammars(
                topic="Q3 retention review",
                user_prompt="board decision, variance chart, owner table, risk tradeoff",
                style_preset="data-heavy-boardroom",
            ),
            "consulting-answer-pyramid",
        ),
        (
            "editorial",
            route_composition_grammars(
                topic="Museum membership renewal",
                user_prompt="human-centered editorial case story with evidence and recommendation",
                style_preset="editorial-minimal",
            ),
            "editorial-spread",
        ),
    ]
    for label, route, expected in cases:
        if _primary_id(route) != expected:
            failures.append(f"{label}: primary={_primary_id(route)} expected={expected}")
        alternatives = route.get("alternatives") if isinstance(route.get("alternatives"), list) else []
        if len(alternatives) != 2:
            failures.append(f"{label}: expected two bounded alternatives")

    unlocked = route_composition_grammars(topic="Assay validation", user_prompt="Scientific evidence and sources")
    brief = quick_deck_agent_brief(unlocked, slide_count=7, agent_profile="terra")
    if brief.get("schema_version") != "quick_deck_agent_brief/v3":
        failures.append("quick-deck brief schema is not v3")
    outline_contract = brief.get("outline_contract") if isinstance(brief.get("outline_contract"), dict) else {}
    deck_style = outline_contract.get("deck_style") if isinstance(outline_contract.get("deck_style"), dict) else {}
    readability = deck_style.get("readability_contract") if isinstance(deck_style.get("readability_contract"), dict) else {}
    if readability.get("min_body_pt") != 16 or readability.get("min_metadata_pt") != 9:
        failures.append("quick-deck brief omitted the 16/9 readability contract")
    route_candidates = brief.get("route_candidates") if isinstance(brief.get("route_candidates"), list) else []
    if brief.get("route_mode") != "model-select-from-bounded-candidates" or len(route_candidates) != 2:
        failures.append("Terra brief must expose exactly two bounded grammar candidates")
    fast_brief = quick_deck_agent_brief(unlocked, slide_count=7, agent_profile="luna")
    quality_brief = quick_deck_agent_brief(unlocked, slide_count=7, agent_profile="sol")
    if fast_brief.get("route_mode") != "deterministic" or len(fast_brief.get("route_candidates") or []) != 1:
        failures.append("Luna brief must use one deterministic grammar candidate")
    if len(quality_brief.get("route_candidates") or []) != 3:
        failures.append("Sol brief must expose three bounded grammar candidates")
    if len(json.dumps(brief, ensure_ascii=False)) > 9000:
        failures.append("quick-deck brief exceeded the lightweight 9 KB budget")
    commands = brief.get("commands") if isinstance(brief.get("commands"), dict) else {}
    finalize_command = str(commands.get("finalize") or "")
    if str(ROOT) not in finalize_command or "present.py" not in finalize_command:
        failures.append("quick-deck finalizer command is not self-locating")
    forbidden_command_tokens = ("libreoffice", "keynote", "powerpoint", "set_properties")
    if any(token in finalize_command.lower() for token in forbidden_command_tokens):
        failures.append("quick-deck brief exposes an unsupported application or metadata command")
    if set(commands) != {"finalize", "repair_loop"}:
        failures.append("quick-deck brief must expose only the bounded finalize and repair loop")

    auto_cases = [
        (
            "auto-investor",
            "Seed-stage investor pitch with market sizing and unit economics",
            "sunset-investor",
            "investor-thesis-stage",
        ),
        (
            "auto-lab",
            "Laboratory assay validation with methods, controls, LoD and concordance",
            "lab-report",
            "scientific-evidence-plate",
        ),
        (
            "auto-policy",
            "Public policy brief on urban heat, equity and budget tradeoffs",
            "forest-research",
            "policy-public-docket",
        ),
        (
            "auto-ops",
            "Operations dashboard for backlog, owners, thresholds and weekly actions",
            "data-heavy-boardroom",
            "operations-grid",
        ),
        (
            "auto-technical",
            "Technical architecture review for GPU telemetry, latency and incident response",
            "arctic-minimal",
            "technical-telemetry-canvas",
        ),
    ]
    auto_routes: dict[str, dict[str, str]] = {}
    for label, prompt, expected_family, expected_grammar in auto_cases:
        auto_context = compact_workflow_atom_context(
            build_workflow_atom_context(
                user_prompt=prompt,
                style_preset="",
                include_prompt=False,
            )
        )
        auto_route = auto_context.get("composition_grammar_route") or {}
        auto_primary = auto_route.get("primary") if isinstance(auto_route.get("primary"), dict) else {}
        actual_family = str(auto_context.get("target_family") or "")
        actual_grammar = str(auto_primary.get("grammar_id") or "")
        auto_routes[label] = {"family": actual_family, "grammar": actual_grammar}
        if actual_family != expected_family:
            failures.append(f"{label}: family={actual_family} expected={expected_family}")
        if actual_grammar != expected_grammar:
            failures.append(f"{label}: grammar={actual_grammar} expected={expected_grammar}")
        plan = auto_context.get("style_execution_plan") if isinstance(auto_context.get("style_execution_plan"), dict) else {}
        if plan.get("explicit_style_lock") is not False:
            failures.append(f"{label}: auto route was persisted as an explicit style lock")

    adversarial_lock = route_composition_grammars(
        topic="Investor launch market transformation",
        user_prompt=(
            "founder pitch market launch product story investor narrative transformation "
            "hero metric big number dashboard comparison roadmap"
        ),
        style_preset="lab-report",
    )
    if _primary_id(adversarial_lock) != "scientific-evidence-plate":
        failures.append("adversarial prompt overrode the explicit preset lock")

    context = compact_workflow_atom_context(
        build_workflow_atom_context(
            user_prompt="Investor fundraising unit economics deck with a hero metric",
            style_preset="lab-report",
            slide_count=8,
            include_prompt=False,
        )
    )
    plan = context.get("style_execution_plan") if isinstance(context.get("style_execution_plan"), dict) else {}
    grammar_route = (
        context.get("composition_grammar_route")
        if isinstance(context.get("composition_grammar_route"), dict)
        else {}
    )
    primary = grammar_route.get("primary") if isinstance(grammar_route.get("primary"), dict) else {}
    deck_style = context.get("deck_style_delta") if isinstance(context.get("deck_style_delta"), dict) else {}
    decision = context.get("decision") if isinstance(context.get("decision"), dict) else {}
    if context.get("target_family") != "lab-report":
        failures.append("explicit preset was overridden by prompt routing")
    if plan.get("schema_version") != "style_execution_plan_v1":
        failures.append("missing style_execution_plan_v1")
    if plan.get("explicit_style_lock") is not True:
        failures.append("explicit style lock not preserved")
    if primary.get("grammar_id") != "scientific-evidence-plate":
        failures.append("composition grammar ignored explicit lab-report preset")
    if deck_style.get("page_system") != "lab-plate":
        failures.append("resolved deck style did not carry lab-plate page system")
    if decision.get("status") != "accepted":
        failures.append("normal workflow route lacks an accepted decision state")
    if len(plan.get("treatment_plan") or {}) != 8:
        failures.append("style execution plan does not expose all treatment recipes")
    role_systems = context.get("renderer_role_systems_v1") if isinstance(context.get("renderer_role_systems_v1"), dict) else {}
    if role_systems.get("schema_version") != "renderer_role_systems_v1":
        failures.append("normal workflow omitted renderer_role_systems_v1")
    if role_systems.get("composition_grammar_id") != "scientific-evidence-plate":
        failures.append("normal workflow persisted the wrong role-system grammar")

    zero_matches = rank_style_references("zzqv unmatched vocabulary", limit=3)
    zero_mix = style_reference_mix_plan("zzqv unmatched vocabulary", limit=3)
    if zero_matches:
        failures.append("zero-score style references should not be returned")
    if zero_mix.get("primary"):
        failures.append("zero-score style mix should not promote an arbitrary primary")

    payload = {
        "passed": not failures,
        "catalog": summary,
        "routes": {label: _primary_id(route) for label, route, _expected in cases},
        "auto_routes": auto_routes,
        "explicit_lock": {
            "target_family": context.get("target_family"),
            "grammar_id": primary.get("grammar_id"),
            "page_system": deck_style.get("page_system"),
            "decision": decision,
            "treatment_count": len(plan.get("treatment_plan") or {}),
        },
        "failures": failures,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
