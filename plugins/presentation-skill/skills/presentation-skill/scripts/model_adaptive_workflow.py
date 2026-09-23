#!/usr/bin/env python3
"""Compact model-adaptive operating briefs for presentation workspaces."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from deck_intake import ANSWER_ALIASES, FIELDS, build_deck_intake

BRIEF_VERSION = "model_adaptive_deck_brief_v1"
PROFILE_ALIASES = {
    "auto": "auto",
    "quality-first": "quality-first",
    "quality_first": "quality-first",
    "frontier": "quality-first",
    "astra": "quality-first",
    "gpt-6-astra": "quality-first",
    "sol": "quality-first",
    "gpt-6-sol": "quality-first",
    "gpt-5.6-sol": "quality-first",
    "pro": "quality-first",
    "balanced": "balanced",
    "standard": "balanced",
    "terra": "balanced",
    "gpt-5.6-terra": "balanced",
    "fast": "fast",
    "draft": "fast",
    "luna": "fast",
    "gpt-6-luna": "fast",
    "gpt-5.6-luna": "fast",
}

PROFILE_HELP = (
    "Workflow policy: auto, fast (luna), balanced (terra), quality-first (sol/astra); "
    "full gpt-5.6-sol/terra/luna and gpt-6-astra/sol/luna aliases accepted. For other models choose an "
    "explicit workflow profile. Aliases are local defaults, not performance claims."
)

PROFILE_CONTRACTS: dict[str, dict[str, Any]] = {
    "quality-first": {
        "intent": "Maximize narrative, evidence, and visual quality for difficult or high-stakes work.",
        "delegation": {
            "design_scout": "only_when_independent_work_is_useful",
            "data_scout": "when_local_data_or_computed_evidence_is_material",
            "visual_critic": "self_review_or_independent_review_when_useful",
        },
        "workflow_order": "suggested_not_required",
        "workflow": [
            "choose a topic-fit story and visual route from the evidence",
            "author editable source and reproducible artifacts",
            "meet the completion rubric; repair and rerun affected checks until clean or report a blocker",
        ],
        "render_policy": "rendered_visual_review_required",
    },
    "balanced": {
        "intent": "Produce a polished professional deck with focused planning and repair.",
        "delegation": {
            "design_scout": "only_when_style_or_evidence_is_ambiguous",
            "data_scout": "only_when_local_data_needs_analysis",
            "visual_critic": "self_review_or_independent_review_when_useful",
        },
        "workflow": [
            "resolve intake or record best-judgment assumptions",
            "select one primary style route",
            "author source files and required artifacts",
            "run render-free QA",
            "render, inspect, and repair until clean or report a blocker",
            "run final delivery readiness",
        ],
        "render_policy": "render_final_candidate_and_review",
    },
    "fast": {
        "intent": "Use a compact single-agent route with the same editable-source and delivery QA target.",
        "agent_mode": "single-agent",
        "delegation": {
            "design_scout": "skip",
            "data_scout": "skip",
            "visual_critic": "self_review_final_render",
        },
        "workflow": [
            "use deterministic style routing",
            "author source files directly",
            "run render-free QA",
            "render and inspect the final candidate",
            "repair source and rerun affected checks until clean or report a blocker",
            "run final delivery readiness",
        ],
        "render_policy": "render_final_candidate_and_review",
    },
}

HIGH_STAKES_RE = re.compile(
    r"\b(clinical|patient|regulatory|board|investor|fundrais|scientific|lab|assay|"
    r"publication|public release|executive decision|risk memo|source-backed|"
    r"data-backed|experiment|trial)\b",
    re.IGNORECASE,
)
FAST_RE = re.compile(
    r"\b(quick|fast|rough|draft|working deck|internal draft|three slides|3 slides|"
    r"four slides|4 slides|five slides|5 slides)\b",
    re.IGNORECASE,
)

CONTENT_SHAPE_HINTS = (
    (re.compile(r"\b(chart|plot|graph)\b", re.IGNORECASE), "chart"),
    (re.compile(r"\b(table|tabular)\b", re.IGNORECASE), "table"),
    (re.compile(r"\b(compare|comparison|versus|vs\.?|trade-?off)\b", re.IGNORECASE), "comparison-2col"),
    (re.compile(r"\b(timeline|roadmap|milestones?)\b", re.IGNORECASE), "timeline"),
    (re.compile(r"\b(matrix|quadrant)\b", re.IGNORECASE), "matrix"),
    (re.compile(r"\b(scientific figure|multi-?panel figure|figure)\b", re.IGNORECASE), "scientific-figure"),
    (re.compile(r"\b(flow|workflow|process diagram)\b", re.IGNORECASE), "flow"),
    (re.compile(r"\b(kpi|hero metric|single metric)\b", re.IGNORECASE), "kpi-hero"),
    (re.compile(r"\b(stats?|metrics?)\b", re.IGNORECASE), "stats"),
    (re.compile(r"\b(lab results?|run results?|assay results?)\b", re.IGNORECASE), "lab-run-results"),
)


def normalize_profile(value: str) -> str:
    key = str(value or "auto").strip().lower()
    if key not in PROFILE_ALIASES:
        valid = ", ".join(sorted(PROFILE_ALIASES))
        raise ValueError(
            f"Unsupported agent profile {value!r}. For an unknown model, choose an explicit "
            f"workflow profile: fast, balanced, or quality-first. Valid values: {valid}"
        )
    return PROFILE_ALIASES[key]


def resolve_profile(requested: str, user_prompt: str) -> tuple[str, str]:
    normalized = normalize_profile(requested)
    if normalized != "auto":
        return normalized, "explicit"
    prompt = str(user_prompt or "")
    if HIGH_STAKES_RE.search(prompt):
        return "quality-first", "auto_high_stakes_or_evidence_heavy"
    if FAST_RE.search(prompt):
        return "fast", "auto_explicit_draft_or_latency_signal"
    return "balanced", "auto_default_professional"


def minimal_payload_examples() -> dict[str, Any]:
    """Variant payloads only; merge into a slide with a valid role and title."""
    return {
        "title": {"subtitle": "Synthetic illustration", "kicker": "DEMO"},
        "section": {"subtitle": "Options and next steps"},
        "stats": {"facts": [
            {"value": "12", "label": "Sites", "detail": "Synthetic pilot"},
            {"value": "8", "label": "Ready", "detail": "Synthetic subset"},
        ]},
        "cards-2": {"cards": [
            {"title": "Scope", "body": "Start with two sites."},
            {"title": "Gate", "body": "Review before expansion."},
        ]},
        "cards-3": {"cards": [
            {"title": "Scope", "body": "Start small."},
            {"title": "Owner", "body": "Assign one lead."},
            {"title": "Gate", "body": "Review results."},
        ]},
        "chart": {"chart": {"type": "bar", "categories": ["A", "B"],
                             "series": [{"name": "Synthetic count", "values": [12, 8]}]}},
        "table": {"table": {"headers": ["Source", "Basis"],
                             "rows": [["S1", "Synthetic illustration"]]}},
        "comparison-2col": {"left": {"title": "Pilot", "bullets": ["Two sites"]},
                            "right": {"title": "Expansion", "bullets": ["After review"]}},
        "matrix": {"quadrants": [
            {"title": "Scope", "body": "Two sites."},
            {"title": "Owner", "body": "Operations lead."},
            {"title": "Gate", "body": "Review readiness."},
            {"title": "Stop", "body": "Pause on missing evidence."},
        ]},
        "standard": {"bullets": ["Approve the bounded pilot.", "Review before expansion."]},
        "timeline": {"milestones": [
            {"label": "Week 1", "title": "Scope", "body": "Select sites."},
            {"label": "Week 2", "title": "Pilot", "body": "Collect observations."},
            {"label": "Week 3", "title": "Review", "body": "Decide next steps."},
        ]},
    }


def compact_authoring_diagnostics() -> list[str]:
    return [
        "Examples are payloads, not slides: add type, role, variant, title, and real sources; sample values are synthetic.",
        "A role describes renderer structure, not story intent. Use a supported role/variant pair; layout variants remain optional suggestions.",
        "stats values must be numeric; chart values must match categories; table rows must match headers; matrix needs exactly four quadrants.",
        "Read the reported slide, rule, and suggested_fix; repair source and rerun. Unresolved QA means not ready, regardless of profile.",
    ]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _requested_variants(user_prompt: str) -> list[str]:
    return [variant for pattern, variant in CONTENT_SHAPE_HINTS if pattern.search(user_prompt)]


def _compact_routes(packet: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
    kickoff = _as_dict(packet.get("agent_kickoff_brief"))
    snapshot = _as_dict(kickoff.get("route_snapshot"))
    atom = _as_dict(kickoff.get("atom_workflow_context"))
    preset = _as_dict(kickoff.get("preset_treatment_profile"))
    style_reference = _as_dict(preset.get("style_reference"))
    mix = _as_dict(style_reference.get("mix_plan"))
    primary = _as_dict(mix.get("primary"))
    grammar_route = _as_dict(atom.get("composition_grammar_route"))
    primary_grammar = _as_dict(grammar_route.get("primary"))
    execution_plan = _as_dict(atom.get("style_execution_plan"))
    treatment_plan = _as_dict(execution_plan.get("treatment_plan"))
    requested_variants = _requested_variants(user_prompt)
    preferred_variants = []
    for variant in [*_as_list(atom.get("preferred_variants")), *requested_variants]:
        if variant not in preferred_variants:
            preferred_variants.append(variant)
    return {
        "active_routes": _as_list(snapshot.get("active_routes")),
        "primary_style": {
            "preset": preset.get("style_preset") or preset.get("preset"),
            "family": preset.get("family"),
            "background_system": preset.get("background_system"),
            "reference_id": primary.get("reference_id") or style_reference.get("reference_id"),
        },
        "atom_seed": {
            "target_family": atom.get("target_family"),
            "decision": atom.get("decision"),
            "preferred_variants": preferred_variants[:10],
            "requested_content_shapes": requested_variants,
            "narrative_arc": _as_list(atom.get("narrative_arc"))[:10],
            "deck_style_delta": _as_dict(atom.get("deck_style_delta")),
        },
        "composition_grammar": {
            "grammar_id": primary_grammar.get("grammar_id"),
            "lane": primary_grammar.get("lane"),
            "rhythm_pattern": _as_list(primary_grammar.get("rhythm_pattern"))[:10],
            "role_variant_map": _as_dict(primary_grammar.get("role_variant_map")),
            "renderer_bias": _as_dict(primary_grammar.get("renderer_bias")),
            "distinctive_moves": _as_list(primary_grammar.get("distinctive_moves"))[:7],
            "max_consecutive_same_variant": primary_grammar.get("max_consecutive_same_variant", 2),
            "alternatives": [
                {
                    "grammar_id": item.get("grammar_id"),
                    "lane": item.get("lane"),
                    "style_preset": item.get("style_preset"),
                }
                for item in _as_list(grammar_route.get("alternatives"))[:2]
                if isinstance(item, dict)
            ],
        },
        "style_execution_plan": {
            "schema_version": execution_plan.get("schema_version"),
            "resolved_primary_preset": execution_plan.get("resolved_primary_preset"),
            "explicit_style_lock": execution_plan.get("explicit_style_lock"),
            "selection_basis": execution_plan.get("selection_basis"),
            "decision": _as_dict(execution_plan.get("decision")),
            "deck_style": _as_dict(execution_plan.get("deck_style")),
            "treatment_keys": list(treatment_plan)[:8],
            "full_plan_location": "design_brief.json:style_system.style_execution_plan",
        },
        "source_inventory": snapshot.get("source_inventory"),
    }


def _compact_commands(packet: dict[str, Any]) -> dict[str, Any]:
    kickoff = _as_dict(packet.get("agent_kickoff_brief"))
    ladder = _as_dict(kickoff.get("command_ladder"))
    preferred_keys = (
        "intake",
        "design_contract",
        "data_artifacts",
        "outline_authoring",
        "source_readiness",
        "fast_first_pass",
        "rendered_visual_review",
        "final_delivery",
    )
    return {key: _as_list(ladder.get(key))[:2] for key in preferred_keys if ladder.get(key)}


def build_agent_brief(
    *,
    packet: dict[str, Any],
    workspace: Path,
    user_prompt: str,
    requested_profile: str = "auto",
    intake_answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    profile, basis = resolve_profile(requested_profile, user_prompt)
    kickoff = _as_dict(packet.get("agent_kickoff_brief"))
    quality = _as_dict(kickoff.get("slide_quality_contract"))
    brief = {
        "brief_version": BRIEF_VERSION,
        "workspace": str(workspace.expanduser().resolve()),
        "stable_prompt_id": packet.get("stable_prompt_id"),
        "user_request": str(user_prompt or "").strip(),
        "execution_profile": {
            "requested": requested_profile,
            "resolved": profile,
            "resolution_basis": basis,
            "policy_basis": "Local workflow defaults, not model performance guarantees; explicit profiles work with any model.",
            **PROFILE_CONTRACTS[profile],
        },
        "autonomy": {
            "local_actions": "Read and edit in-scope source files, run non-destructive builds and QA, and iterate without asking again.",
            "confirmation_required": "External writes, destructive actions, purchases, or material scope expansion.",
        },
        "intake": build_deck_intake(user_prompt, answers=intake_answers),
        "routing": _compact_routes(packet, user_prompt=user_prompt),
        "authoring_contract": {
            "source_of_truth": [
                "outline.json",
                "design_brief.json",
                "content_plan.json",
                "evidence_plan.json",
                "asset_plan.json",
                "notes.md",
                "data and figure scripts when present",
            ],
            "decide": [
                "one primary visual grammar and bounded secondary influences",
                "topic-specific slide sequence and composition rhythm",
                "which claims need charts, tables, figures, or citations",
                "which generated artifacts must stay editable and reproducible",
            ],
            "evidence_guardrails": [
                "Do not invent factual values or citations when source data is missing.",
                "Ask once when missing evidence changes the decision; otherwise label assumptions or synthetic illustrations explicitly.",
                "Run PPTX style extraction only when an actual reference deck path exists.",
            ],
            "do_not_copy": [
                "full corpus records",
                "full preset catalog",
                "recipe signatures that do not change the slide",
                "command ladders or replay ledgers into model answers",
            ],
        },
        "quality_contract": quality,
        "commands": _compact_commands(packet),
        "completion_rubric": [
            "Every content slide has a clear visual or evidence anchor.",
            "Slide compositions vary with the argument; the deck is not a repeated card or bullet template.",
            "Text is readable and no source/footer content intrudes into the body.",
            "Charts, tables, figures, and images have source or rebuild metadata when required.",
            "Geometry, rendered visual review, and placeholder checks pass.",
            "The final PPTX is editable and reproducible from workspace source.",
        ],
        "context_policy": {
            "start_here": "Read this brief first.",
            "load_on_demand": [
                "references/outline_schema.md for fields and variants",
                "DESIGN.md for the compact design contract",
                "one selected style reference or artifact manifest",
                "the specific QA report for a repair pass",
            ],
            "audit_only": "Open deck_start_packet.json only for recovery, audit, or a missing command.",
        },
    }
    if profile == "fast":
        brief["authoring_contract"]["minimal_payload_examples"] = minimal_payload_examples()
        brief["authoring_contract"]["diagnostics"] = compact_authoring_diagnostics()
    encoded = json.dumps(brief, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    brief["prompt_budget"] = {
        "compact_json_chars": len(encoded),
        "target_max_chars": 20000,
        "within_budget": len(encoded) <= 20000,
    }
    return brief


def render_agent_brief_markdown(brief: dict[str, Any]) -> str:
    profile = _as_dict(brief.get("execution_profile"))
    routing = _as_dict(brief.get("routing"))
    primary = _as_dict(routing.get("primary_style"))
    lines = [
        "# Agent Deck Brief",
        "",
        f"Request: {brief.get('user_request') or '<not provided>'}",
        f"Profile: {profile.get('resolved')} ({profile.get('resolution_basis')})",
        f"Style route: {primary.get('preset') or 'auto'} / {primary.get('family') or 'custom'}",
        "",
        "## Outcome",
        "",
        str(profile.get("intent") or "Create a polished editable deck."),
        "",
        "## Workflow",
        "",
    ]
    lines.extend(f"- {item}" for item in _as_list(profile.get("workflow")))
    if profile.get("workflow_order") == "suggested_not_required":
        lines.append("These are suggested actions, not a fixed sequence.")
    if profile.get("agent_mode") == "single-agent":
        lines.append("Use one agent, including final visual review; the delivery QA target is unchanged.")
    intake = _as_dict(brief.get("intake"))
    lines.extend(["", "## Optional Intake", "", str(intake.get("policy") or "")])
    lines.extend(f"- {item['question']}" for item in _as_list(intake.get("questions")))
    lines.extend(f"- Assumption ({key}): {value}" for key, value in _as_dict(intake.get("assumptions")).items())
    lines.extend(["", "## Design Route", ""])
    atom = _as_dict(routing.get("atom_seed"))
    grammar = _as_dict(routing.get("composition_grammar"))
    variants = ", ".join(str(item) for item in _as_list(atom.get("preferred_variants"))) or "choose from the evidence shape"
    rhythm = " > ".join(str(item) for item in _as_list(grammar.get("rhythm_pattern"))) or "derive from the argument"
    lines.extend(
        [
            f"Primary preset: {primary.get('preset') or 'auto'}",
            f"Background system: {primary.get('background_system') or 'topic-fit'}",
            f"Composition grammar: {grammar.get('grammar_id') or 'topic-fit'}",
            f"Rhythm candidates: {rhythm}",
            f"Preferred variants: {variants}",
            "Use the grammar as a coherent starting point, not a mandatory sequence. Keep one page system and borrow at most two bounded secondary moves.",
            "",
            "## Completion Rubric",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in _as_list(brief.get("completion_rubric")))
    authoring = _as_dict(brief.get("authoring_contract"))
    if authoring.get("minimal_payload_examples"):
        lines.extend(["", "## Payload Help", ""])
        lines.extend(f"- {item}" for item in authoring["diagnostics"])
        lines.extend(["```json", json.dumps(authoring["minimal_payload_examples"], separators=(",", ":")), "```"])
    lines.extend(
        [
            "",
            "## Context Policy",
            "",
            "Start with this brief. Load only the schema, selected style reference, artifact manifest, or QA report needed for the current phase.",
            "Keep the full deck-start packet on disk for audit and recovery; do not paste it into the active prompt.",
            "",
        ]
    )
    return "\n".join(lines)


def write_agent_brief(
    *,
    packet: dict[str, Any],
    workspace: Path,
    user_prompt: str,
    requested_profile: str = "auto",
    json_path: Path | None = None,
    markdown_path: Path | None = None,
    intake_answers: dict[str, str] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    resolved_workspace = workspace.expanduser().resolve()
    design_path = resolved_workspace / "design_brief.json"
    if intake_answers is None and design_path.is_file():
        design = _as_dict(json.loads(design_path.read_text(encoding="utf-8")))
        saved = _as_dict(design.get("user_intake"))
        intake_answers = {
            key: value for key, value in saved.items()
            if (key in FIELDS or key in ANSWER_ALIASES) and isinstance(value, str) and value.strip()
        }
    brief = build_agent_brief(
        packet=packet,
        workspace=resolved_workspace,
        user_prompt=user_prompt,
        requested_profile=requested_profile,
        intake_answers=intake_answers,
    )
    json_out = (json_path or (resolved_workspace / "agent_brief.json")).expanduser().resolve()
    md_out = (markdown_path or (resolved_workspace / "agent_brief.md")).expanduser().resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_out.write_text(render_agent_brief_markdown(brief), encoding="utf-8")
    return json_out, md_out, brief


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Emit a compact model-adaptive deck brief.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--packet", default="deck_start_packet.json")
    parser.add_argument("--user-prompt", default="")
    parser.add_argument("--agent-profile", default="auto", choices=sorted(PROFILE_ALIASES), help=PROFILE_HELP)
    parser.add_argument("--json-output", default="")
    parser.add_argument("--markdown-output", default="")
    return parser.parse_args()


def main() -> int:
    args = _args()
    workspace = Path(args.workspace).expanduser().resolve()
    packet_path = Path(args.packet)
    if not packet_path.is_absolute():
        packet_path = workspace / packet_path
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    json_path, markdown_path, brief = write_agent_brief(
        packet=packet,
        workspace=workspace,
        user_prompt=args.user_prompt or str(_as_dict(packet.get("agent_kickoff_brief")).get("user_request_summary") or ""),
        requested_profile=args.agent_profile,
        json_path=Path(args.json_output) if args.json_output else None,
        markdown_path=Path(args.markdown_output) if args.markdown_output else None,
    )
    print(json.dumps({
        "brief_version": brief.get("brief_version"),
        "execution_profile": _as_dict(brief.get("execution_profile")).get("resolved"),
        "json_output": str(json_path),
        "markdown_output": str(markdown_path),
        "prompt_budget": brief.get("prompt_budget"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
