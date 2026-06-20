#!/usr/bin/env python3
"""Emit the first-turn packet for a reproducible deck build.

This combines the compact Codex question payload, the strict design-contract
prompt, and staged subagent commands into one deterministic JSON object. Use it
immediately after a user's deck request, before writing design_brief.json or
outline.json.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from emit_deck_intake_prompt import render_codex_ui_spec  # noqa: E402
from emit_design_contract_prompt import (  # noqa: E402
    _stable_id,
    _workspace_source_inventory,
    render_contract_prompt,
)
from style_treatment_profiles import preset_treatment_profile  # noqa: E402


DATA_SUFFIXES = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".xlsx",
    ".xls",
    ".parquet",
    ".feather",
}

DATA_HINTS = (
    "data",
    "dataset",
    "spreadsheet",
    "excel",
    "xlsx",
    "csv",
    "table",
    "analysis",
    "chart",
    "figure",
    "plot",
    "assay",
    "lab report",
    "results",
    "readout",
)

RESEARCH_HINTS = (
    "research",
    "sources",
    "citations",
    "refs",
    "reference",
    "public",
    "latest",
    "current",
    "market",
    "clinical",
    "policy",
    "scientific",
)

PPTX_STYLE_HINTS = (
    ".pptx",
    "powerpoint",
    "template",
    "reference deck",
    "example deck",
    "style extraction",
    "extract style",
    "branded deck",
    "brand deck",
    "existing deck",
)

SOURCE_FOOTER_HINTS = (
    "source-line",
    "source",
    "sources",
    "sourced",
    "citation",
    "citations",
    "reference",
    "references",
    "refs",
    "footnote",
    "footer",
    "lab report",
    "report deck",
)


def _shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _workspace_arg(workspace: Path | None) -> str:
    return str(workspace) if workspace is not None else "decks/my-deck"


def _workspace_has_data(workspace: Path | None) -> bool:
    if workspace is None:
        return False
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
            if path.is_file() and path.suffix.lower() in DATA_SUFFIXES:
                return True
    return False


def _workspace_reference_pptx(workspace: Path | None) -> str:
    if workspace is None or not workspace.exists():
        return ""
    for path in sorted(workspace.rglob("*.pptx"), key=lambda item: str(item)):
        rel_parts = path.relative_to(workspace).parts
        if rel_parts and rel_parts[0] == "build":
            continue
        return str(path)
    return ""


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _data_artifacts_likely(*, workspace: Path | None, user_prompt: str) -> bool:
    return _workspace_has_data(workspace) or _contains_any(user_prompt, DATA_HINTS)


def _workspace_style_preset(workspace: Path | None) -> str:
    if workspace is None:
        return "executive-clinical"
    path = workspace / "design_brief.json"
    if not path.exists():
        return "executive-clinical"
    try:
        brief = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "executive-clinical"
    if not isinstance(brief, dict):
        return "executive-clinical"
    for container_key in ("style_system", "visual_system"):
        container = brief.get(container_key)
        if isinstance(container, dict):
            value = str(container.get("style_preset") or "").strip()
            if value:
                return value
    value = str(brief.get("style_preset") or "").strip()
    return value or "executive-clinical"


def _pptx_style_likely(*, workspace: Path | None, user_prompt: str) -> bool:
    return bool(_workspace_reference_pptx(workspace)) or _contains_any(user_prompt, PPTX_STYLE_HINTS)


def _pptx_style_input(workspace: Path | None) -> str:
    return _workspace_reference_pptx(workspace) or "<template-or-reference-folder>"


def _pptx_style_commands(workspace_text: str, *, workspace: Path | None) -> list[str]:
    return [
        _shell_join(
            [
                "python3",
                "scripts/extract_pptx_style.py",
                "--input",
                _pptx_style_input(workspace),
                "--report",
                f"{workspace_text}/style_extract_report.json",
                "--markdown-report",
                f"{workspace_text}/style_extract_report.md",
                "--design-brief-fragment",
                f"{workspace_text}/style_extract_design_brief.json",
            ]
        ),
        _shell_join(
            [
                "python3",
                "scripts/apply_pptx_style_fragment.py",
                "--workspace",
                workspace_text,
                "--fragment",
                f"{workspace_text}/style_extract_design_brief.json",
                "--report",
                f"{workspace_text}/style_fragment_apply_report.json",
            ]
        ),
    ]


def _data_artifact_commands(workspace_text: str) -> list[str]:
    return [
        _shell_join(
            [
                "python3",
                "scripts/apply_data_analysis_handoff.py",
                "--workspace",
                workspace_text,
                "--handoff",
                f"{workspace_text}/data_analysis_handoff.json",
                "--report",
                f"{workspace_text}/data_analysis_handoff_apply_report.json",
            ]
        ),
        _shell_join(
            [
                "python3",
                "scripts/scaffold_figure_artifacts.py",
                "--workspace",
                workspace_text,
                "--run",
                "--bind-outline",
            ]
        ),
        _shell_join(
            [
                "python3",
                "scripts/build_workspace.py",
                "--workspace",
                workspace_text,
                "--fast-first-pass",
            ]
        ),
    ]


def _source_inventory_summary(source_inventory: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(source_inventory, dict):
        return {}

    def shown_paths(key: str) -> list[str]:
        values = source_inventory.get(key)
        if not isinstance(values, list):
            return []
        paths: list[str] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if path:
                paths.append(path)
        return paths

    return {
        "workspace": str(source_inventory.get("workspace") or ""),
        "exists": bool(source_inventory.get("exists")),
        "data_file_count": int(source_inventory.get("data_file_count") or 0),
        "data_file_shown_count": int(source_inventory.get("data_file_shown_count") or 0),
        "reference_pptx_count": int(source_inventory.get("reference_pptx_count") or 0),
        "reference_pptx_shown_count": int(source_inventory.get("reference_pptx_shown_count") or 0),
        "artifact_ledger_count": int(source_inventory.get("artifact_ledger_count") or 0),
        "data_paths": shown_paths("data_files"),
        "reference_pptx_paths": shown_paths("reference_pptx_files"),
        "artifact_ledger_paths": shown_paths("artifact_ledger_files"),
        "inventory_replay_path": "deck_start_packet.json:workspace_source_inventory",
    }


def _visual_review_commands(workspace_text: str) -> list[str]:
    return [
        _shell_join(
            [
                "python3",
                "scripts/build_workspace.py",
                "--workspace",
                workspace_text,
                "--qa",
                "--visual-review",
                "--fail-on-planning-warnings",
                "--fail-on-whitespace-warnings",
                "--overwrite",
            ]
        ),
        _shell_join(
            [
                "python3",
                "scripts/report_delivery_readiness.py",
                "--workspace",
                workspace_text,
                "--require-visual-review",
            ]
        ),
        _shell_join(
            [
                "python3",
                "scripts/advance_delivery.py",
                "--workspace",
                workspace_text,
                "--require-visual-review",
            ]
        ),
    ]


def _intake_apply_command(workspace_text: str) -> str:
    return _shell_join(
        [
            "python3",
            "scripts/apply_deck_intake_answers.py",
            "--workspace",
            workspace_text,
            "--packet",
            f"{workspace_text}/deck_start_packet.json",
            "--answers",
            f"{workspace_text}/intake_answers.json",
            "--report",
            f"{workspace_text}/intake_apply_report.json",
        ]
    )


def _design_contract_apply_command(workspace_text: str) -> str:
    return _shell_join(
        [
            "python3",
            "scripts/apply_design_contract.py",
            "--workspace",
            workspace_text,
            "--contract",
            f"{workspace_text}/design_contract.json",
            "--report",
            f"{workspace_text}/design_contract_apply_report.json",
        ]
    )


def _outline_authoring_prompt_command(workspace_text: str, user_prompt: str = "") -> str:
    parts = [
        "python3",
        "scripts/emit_outline_authoring_prompt.py",
        "--workspace",
        workspace_text,
        "--output",
        f"{workspace_text}/build/outline_authoring_prompt.md",
    ]
    if user_prompt.strip():
        parts.extend(["--user-prompt", user_prompt.strip()])
    return _shell_join(parts)


def _outline_authoring_apply_command(workspace_text: str) -> str:
    return _shell_join(
        [
            "python3",
            "scripts/apply_outline_authoring_handoff.py",
            "--workspace",
            workspace_text,
            "--handoff",
            f"{workspace_text}/outline_authoring_handoff.json",
            "--report",
            f"{workspace_text}/outline_authoring_handoff_apply_report.json",
        ]
    )


def _route_decision_ledger(
    workspace_text: str,
    *,
    workspace: Path | None,
    user_prompt: str,
    source_inventory: dict[str, Any],
    data_artifacts_likely: bool,
    pptx_style_likely: bool,
    data_artifact_commands: list[str],
    pptx_style_commands: list[str],
    visual_review_commands: list[str],
) -> dict[str, Any]:
    data_terms = _matched_terms(user_prompt, DATA_HINTS)
    research_terms = _matched_terms(user_prompt, RESEARCH_HINTS)
    pptx_style_terms = _matched_terms(user_prompt, PPTX_STYLE_HINTS)
    source_footer_terms = _matched_terms(user_prompt, SOURCE_FOOTER_HINTS)
    workspace_data = _workspace_has_data(workspace)
    reference_pptx = _workspace_reference_pptx(workspace)
    research_likely = bool(research_terms)
    source_footer_likely = bool(source_footer_terms)

    def evidence(*items: str) -> list[str]:
        return [item for item in items if item]

    return {
        "ledger_version": "deck_route_decision_ledger_v1",
        "purpose": (
            "Make first-turn workflow routing reproducible before outline "
            "authoring by recording why each deterministic route is active, "
            "inactive, or conditional."
        ),
        "source_fields_to_lock": [
            "design_brief.json:style_system.style_seed",
            "design_brief.json:style_system.style_mix_matrix",
            "design_brief.json:readability_contract",
            "design_brief.json:analysis_artifact_plan",
            "design_brief.json:figure_export_contract",
            "evidence_plan.json:source_policy",
            "asset_plan.json:charts/tables/images/backgrounds",
            "outline.json:slide variants and generated artifact refs",
        ],
        "source_inventory_summary": _source_inventory_summary(source_inventory),
        "routes": [
            {
                "id": "intake_questions",
                "active": True,
                "trigger_evidence": ["first-turn deck request"],
                "decision": "ask compact question card or persist best-judgment assumptions",
                "commands": [_intake_apply_command(workspace_text)],
                "writes": [
                    f"{workspace_text}/intake_answers.json",
                    f"{workspace_text}/intake_apply_report.json",
                    f"{workspace_text}/design_brief.json:user_intake",
                ],
            },
            {
                "id": "design_contract",
                "active": True,
                "trigger_evidence": ["always required before outline authoring"],
                "decision": "lock reproducible style, structure, source, artifact, and QA choices",
                "commands": [_design_contract_apply_command(workspace_text)],
                "writes": [
                    f"{workspace_text}/design_contract.json",
                    f"{workspace_text}/design_contract_apply_report.json",
                    f"{workspace_text}/design_brief.json:design_contract",
                ],
            },
            {
                "id": "data_artifacts",
                "active": data_artifacts_likely,
                "trigger_evidence": evidence(
                    "workspace data files detected" if workspace_data else "",
                    f"prompt terms: {', '.join(data_terms)}" if data_terms else "",
                ),
                "decision": (
                    "run data scout/scaffold before outline binding"
                    if data_artifacts_likely
                    else "skip unless user adds local data, charts, spreadsheets, or analysis outputs"
                ),
                "commands": data_artifact_commands,
                "writes": [
                    f"{workspace_text}/assets/make_figures.py",
                    f"{workspace_text}/assets/artifacts_manifest.json",
                    f"{workspace_text}/assets/analysis_summary.json",
                    f"{workspace_text}/artifact_selections.auto.json",
                    f"{workspace_text}/design_brief.json:analysis_artifact_plan",
                    f"{workspace_text}/outline.json:generated artifact slide refs",
                ],
                "required_when_active": [
                    "source fingerprints, producer fingerprints, selected columns, and rerun commands are recorded",
                    "generated chart/table/figure aliases are bound through artifact selections",
                ],
            },
            {
                "id": "pptx_style_import",
                "active": pptx_style_likely,
                "trigger_evidence": evidence(
                    f"reference PPTX: {reference_pptx}" if reference_pptx else "",
                    f"prompt terms: {', '.join(pptx_style_terms)}" if pptx_style_terms else "",
                ),
                "decision": (
                    "extract and apply bounded style signals before final contract routing"
                    if pptx_style_likely
                    else "skip unless a reference PPTX/template/corpus is provided"
                ),
                "commands": pptx_style_commands,
                "writes": [
                    f"{workspace_text}/style_extract_report.json",
                    f"{workspace_text}/style_extract_design_brief.json",
                    f"{workspace_text}/style_fragment_apply_report.json",
                    f"{workspace_text}/design_brief.json:style_import",
                ],
            },
            {
                "id": "content_research",
                "active": research_likely,
                "trigger_evidence": evidence(
                    f"prompt terms: {', '.join(research_terms)}" if research_terms else "",
                ),
                "decision": (
                    "run content research after draft outline exists"
                    if research_likely
                    else "skip unless factual claims need source-backed anchors"
                ),
                "commands": [
                    _shell_join(
                        [
                            "python3",
                            "scripts/emit_content_research.py",
                            "--outline",
                            f"{workspace_text}/outline.json",
                        ]
                    )
                ] if research_likely else [],
                "writes": [
                    f"{workspace_text}/evidence_plan.json:items",
                    f"{workspace_text}/outline.json:sources/refs",
                ],
            },
            {
                "id": "source_footer_compaction",
                "active": source_footer_likely,
                "trigger_evidence": evidence(
                    f"prompt terms: {', '.join(source_footer_terms)}" if source_footer_terms else "",
                ),
                "decision": (
                    "use compact source-line IDs and move long citations to editable References tables"
                    if source_footer_likely
                    else "run only if preflight reports source_line_footer_over_budget"
                ),
                "commands": [
                    _shell_join(["python3", "scripts/compact_source_footers.py", "--workspace", workspace_text]),
                    _shell_join(["python3", "scripts/advance_workspace.py", "--workspace", workspace_text, "--execute", "--max-steps", "3"]),
                ],
                "writes": [
                    f"{workspace_text}/build/source_footer_compaction.json",
                    f"{workspace_text}/outline.json:short source/ref IDs",
                    f"{workspace_text}/outline.json:editable References table slides",
                ],
                "required_when_active": [
                    "source-line footers stay compact",
                    "full citations remain editable in References table slides",
                ],
            },
            {
                "id": "rendered_visual_review",
                "active": True,
                "trigger_evidence": ["final polished deck workflow"],
                "decision": "run after source text is stable or when final acceptance needs rendered judgment",
                "commands": visual_review_commands,
                "writes": [
                    f"{workspace_text}/build/qa/visual_review/visual_review.md",
                    f"{workspace_text}/build/qa/visual_review/visual_review.json",
                    f"{workspace_text}/build/delivery_readiness.json",
                ],
            },
        ],
        "replay_proof": [
            f"{workspace_text}/deck_start_packet.json:route_decision_ledger",
            f"{workspace_text}/design_contract.json:choice_resolution.route_decisions",
            f"{workspace_text}/design_brief.json:design_contract.choice_resolution",
            f"{workspace_text}/build/workspace_readiness.json:next_action",
        ],
    }


def _acceptance_checklist(
    workspace_text: str,
    *,
    workspace: Path | None,
    data_artifacts_likely: bool,
    pptx_style_likely: bool,
) -> list[dict[str, Any]]:
    checklist: list[dict[str, Any]] = [
        {
            "id": "intake_recorded",
            "phase": "intake",
            "gate": "User answers or best-judgment assumptions are persisted before design routing.",
            "proof": [
                f"{workspace_text}/intake_apply_report.json",
                f"{workspace_text}/design_brief.json:user_intake",
                f"{workspace_text}/notes.md:assumptions",
            ],
            "establish_command": _intake_apply_command(workspace_text),
            "blocks_final_delivery_if_missing": True,
        },
        {
            "id": "design_contract_applied",
            "phase": "contract",
            "gate": "A strict deck_design_contract_v1 has been saved and deterministically applied to planning sources.",
            "proof": [
                f"{workspace_text}/design_contract.json",
                f"{workspace_text}/design_contract_apply_report.json",
                f"{workspace_text}/design_brief.json:design_contract",
                f"{workspace_text}/design_brief.json:style_system.style_seed",
                f"{workspace_text}/content_plan.json",
                f"{workspace_text}/evidence_plan.json",
                f"{workspace_text}/asset_plan.json",
            ],
            "establish_command": _design_contract_apply_command(workspace_text),
            "blocks_final_delivery_if_missing": True,
        },
        {
            "id": "outline_authored_from_contract",
            "phase": "outline",
            "gate": "The starter outline has been replaced through a contract-aware outline_authoring_handoff_v1 source patch.",
            "proof": [
                f"{workspace_text}/build/outline_authoring_prompt.md",
                f"{workspace_text}/outline_authoring_handoff.json",
                f"{workspace_text}/outline_authoring_handoff_apply_report.json",
                f"{workspace_text}/outline.json",
                f"{workspace_text}/content_plan.json",
                f"{workspace_text}/evidence_plan.json",
                f"{workspace_text}/asset_plan.json",
            ],
            "establish_commands": [
                _outline_authoring_prompt_command(workspace_text),
                _outline_authoring_apply_command(workspace_text),
            ],
            "blocks_final_delivery_if_missing": True,
        },
        {
            "id": "source_planning_clean",
            "phase": "planning",
            "gate": "Planning validation and source-only readiness have no blocking warnings before final build.",
            "proof": [
                f"{workspace_text}/build/workspace_readiness.json:status",
                f"{workspace_text}/build/workspace_readiness.md",
            ],
            "verify_commands": [
                _shell_join(["python3", "scripts/validate_planning.py", "--workspace", workspace_text]),
                _shell_join(["python3", "scripts/report_workspace_readiness.py", "--workspace", workspace_text]),
            ],
            "blocks_final_delivery_if_missing": True,
        },
        {
            "id": "fast_first_pass_checked",
            "phase": "build",
            "gate": "The first source build is checked with render-free QA before expensive visual iteration.",
            "proof": [
                f"{workspace_text}/build/build_workspace_report.json",
                f"{workspace_text}/build/qa/report.json",
            ],
            "verify_commands": [
                _shell_join(
                    [
                        "python3",
                        "scripts/build_workspace.py",
                        "--workspace",
                        workspace_text,
                        "--qa",
                        "--skip-render",
                        "--fail-on-planning-warnings",
                        "--fail-on-whitespace-warnings",
                        "--overwrite",
                    ]
                )
            ],
            "blocks_final_delivery_if_missing": False,
        },
        {
            "id": "rendered_visual_review_done",
            "phase": "visual_review",
            "gate": "Rendered slide review has produced a contact-sheet report or has a documented delivery-level waiver.",
            "proof": [
                f"{workspace_text}/build/qa/visual_review/visual_review.md",
                f"{workspace_text}/build/qa/visual_review/visual_review.json",
                f"{workspace_text}/build/delivery_readiness.json:visual_review_requirement",
            ],
            "verify_commands": _visual_review_commands(workspace_text),
            "blocks_final_delivery_if_missing": True,
        },
        {
            "id": "final_delivery_audited",
            "phase": "delivery",
            "gate": "A strict final build and delivery audit prove current sources, QA counts, and PPTX fingerprint.",
            "proof": [
                f"{workspace_text}/build/build_workspace_report.json",
                f"{workspace_text}/build/delivery_readiness.json:delivery_status=ready",
                f"{workspace_text}/build/delivery_readiness.md",
            ],
            "verify_commands": [
                _shell_join(
                    [
                        "python3",
                        "scripts/build_workspace.py",
                        "--workspace",
                        workspace_text,
                        "--qa",
                        "--fail-on-planning-warnings",
                        "--fail-on-whitespace-warnings",
                        "--overwrite",
                    ]
                ),
                _shell_join(["python3", "scripts/report_delivery_readiness.py", "--workspace", workspace_text]),
            ],
            "blocks_final_delivery_if_missing": True,
        },
    ]
    if pptx_style_likely:
        style_commands = _pptx_style_commands(workspace_text, workspace=workspace)
        checklist.insert(
            2,
            {
                "id": "reference_style_imported",
                "phase": "style",
                "gate": "Reference PPTX/corpus style has been extracted, applied, and previewed through supported treatments only.",
                "proof": [
                    f"{workspace_text}/style_extract_report.json",
                    f"{workspace_text}/style_extract_design_brief.json",
                    f"{workspace_text}/style_fragment_apply_report.json",
                    f"{workspace_text}/design_brief.json:style_import",
                ],
                "establish_commands": style_commands,
                "blocks_final_delivery_if_missing": False,
            },
        )
    if data_artifacts_likely:
        checklist.insert(
            2,
            {
                "id": "data_artifacts_bound",
                "phase": "artifacts",
                "gate": "Local tabular data is converted into reproducible figures/chart JSON/tables and bound into outline/planning sources.",
                "proof": [
                    f"{workspace_text}/data_analysis_handoff.json or generated artifact scaffold report",
                    f"{workspace_text}/data_analysis_handoff_apply_report.json when a scout handoff is used",
                    f"{workspace_text}/assets/make_figures.py",
                    f"{workspace_text}/assets/artifacts_manifest.json",
                    f"{workspace_text}/assets/analysis_summary.json",
                    f"{workspace_text}/artifact_selections.auto.json or artifact_selections.scout.json",
                    f"{workspace_text}/design_brief.json:analysis_artifact_plan",
                    f"{workspace_text}/outline.json:generated artifact slide refs",
                ],
                "establish_commands": _data_artifact_commands(workspace_text),
                "blocks_final_delivery_if_missing": True,
            },
        )
    return checklist


def _intake_answers_template() -> dict[str, Any]:
    return {
        "answers": [
            {"id": "audience_context", "answer": "<selected label or free-form answer>"},
            {"id": "style_density", "answer": "<selected label or free-form answer>"},
            {"id": "visual_source_policy", "answer": "<selected label or free-form answer>"},
        ],
        "answered_by": "user | inferred | best_judgment",
    }


def _choice_resolution_contract(
    workspace_text: str,
    *,
    stable_id: str,
    source_inventory: dict[str, Any],
    data_artifacts_likely: bool,
    pptx_style_likely: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "deck_choice_resolution_v1",
        "stable_prompt_id": stable_id,
        "purpose": (
            "Make the first user question card reproducible by turning compact "
            "answers into explicit design, evidence, asset, artifact, and QA "
            "source fields before outline authoring."
        ),
        "question_card": {
            "answer_file": f"{workspace_text}/intake_answers.json",
            "compressed_question_ids": [
                "audience_context",
                "style_density",
                "visual_source_policy",
            ],
            "fallback": (
                "Use best judgment only when the user does not answer; persist "
                "the assumptions and keep them visible in design_brief.user_intake."
            ),
        },
        "workspace_source_inventory": _source_inventory_summary(source_inventory),
        "choice_ledger": [
            {
                "id": "audience_context",
                "locks": [
                    "audience posture",
                    "use context",
                    "target outcome",
                    "technical depth",
                    "readability thresholds",
                ],
                "source_fields": [
                    "design_brief.json:user_intake.audience_context",
                    "design_brief.json:deck_identity or audience_posture",
                    "content_plan.json:audience",
                    "content_plan.json:decision_target",
                    "design_brief.json:readability_contract",
                ],
                "contract_fields": [
                    "deck_identity.audience",
                    "deck_identity.use_context",
                    "deck_identity.target_outcome",
                    "readability_contract.max_slide_text_lines",
                    "readability_contract.max_slide_words",
                    "readability_contract.max_slide_chars",
                ],
            },
            {
                "id": "style_density",
                "locks": [
                    "design DNA",
                    "density",
                    "background system",
                    "title layout pool",
                    "header/footer variant pool",
                    "slide-variant mix",
                    "figure/table treatment",
                    "blank-space policy",
                ],
                "source_fields": [
                    "design_brief.json:design_modulation",
                    "design_brief.json:visual_system",
                    "design_brief.json:deck_style",
                    "design_brief.json:title_page_concept",
                    "design_brief.json:style_system.style_seed",
                    "design_brief.json:style_system.style_mix_matrix",
                    "design_brief.json:renderer_treatments",
                ],
                "contract_fields": [
                    "design_dna",
                    "style_system.style_preset",
                    "style_system.background_system",
                    "style_system.title_slide_system.title_layout",
                    "style_system.header_system.header_variants",
                    "style_system.footer_system",
                    "style_system.style_mix_matrix",
                    "structure_blueprint.slide_variant_mix",
                ],
                "option_resolution": [
                    {
                        "answer_signal": "figure-first report",
                        "default_route": "lab-report preset, clean report background, figure/table evidence slides, compact source-line footer",
                    },
                    {
                        "answer_signal": "conference talk",
                        "default_route": "technical educational DNA, lower prose density, larger figure anchors, fewer footer claims",
                    },
                    {
                        "answer_signal": "premium editorial",
                        "default_route": "editorial report DNA, stronger cover treatment, balanced density, selective evidence tables",
                    },
                ],
            },
            {
                "id": "visual_source_policy",
                "locks": [
                    "source policy",
                    "asset posture",
                    "web/local/generated visual permissions",
                    "citation footer posture",
                    "references slide posture",
                    "analysis artifact burden",
                ],
                "source_fields": [
                    "evidence_plan.json:source_policy",
                    "evidence_plan.json:items",
                    "asset_plan.json:asset_posture",
                    "asset_plan.json:images",
                    "asset_plan.json:charts",
                    "asset_plan.json:tables",
                    "design_brief.json:analysis_artifact_plan",
                    "design_brief.json:figure_export_contract",
                ],
                "contract_fields": [
                    "evidence_plan.source_policy",
                    "source_policy",
                    "asset_posture",
                    "analysis_artifact_plan",
                    "figure_export_contract",
                    "qa_contract.required_checks",
                ],
            },
        ],
        "route_decisions": [
            {
                "id": "data_artifacts",
                "active": data_artifacts_likely,
                "trigger_evidence": (
                    "workspace data files or prompt terms for data, spreadsheet, "
                    "chart, figure, assay, lab report, results, or readout"
                ),
                "must_write_when_active": [
                    f"{workspace_text}/assets/make_figures.py",
                    f"{workspace_text}/assets/artifacts_manifest.json",
                    f"{workspace_text}/assets/analysis_summary.json",
                    f"{workspace_text}/design_brief.json:analysis_artifact_plan",
                    f"{workspace_text}/design_brief.json:figure_export_contract",
                ],
            },
            {
                "id": "pptx_style_import",
                "active": pptx_style_likely,
                "trigger_evidence": (
                    "reference PPTX, template deck, style corpus, or explicit "
                    "request to extract existing deck style"
                ),
                "must_write_when_active": [
                    f"{workspace_text}/style_extract_report.json",
                    f"{workspace_text}/style_extract_design_brief.json",
                    f"{workspace_text}/style_fragment_apply_report.json",
                    f"{workspace_text}/design_brief.json:style_import",
                ],
            },
        ],
        "contract_requirements": {
            "must_echo_resolved_choices": True,
            "design_contract_fields": [
                "choice_resolution",
                "design_brief.design_contract.choice_resolution",
                "design_brief.user_intake",
                "style_system.style_seed",
                "style_system.style_mix_matrix",
                "readability_contract",
                "speed_contract",
                "evidence_plan.source_policy",
                "asset_posture",
                "analysis_artifact_plan",
                "figure_export_contract",
                "qa_contract",
            ],
            "outline_authoring_inputs": [
                "resolved audience/use context",
                "resolved style_density route",
                "resolved visual_source_policy route",
                "header/footer variant pool",
                "slide-variant mix",
                "data_artifact route status",
                "pptx_style_import route status",
                "workspace source inventory snapshot",
            ],
        },
        "replay_proof": [
            f"{workspace_text}/deck_start_packet.json:choice_resolution_contract",
            f"{workspace_text}/deck_start_packet.json:workspace_source_inventory",
            f"{workspace_text}/intake_apply_report.json",
            f"{workspace_text}/design_contract.json:choice_resolution",
            f"{workspace_text}/design_contract_apply_report.json",
            f"{workspace_text}/design_brief.json:design_contract.choice_resolution",
        ],
    }


def _slide_quality_contract(
    workspace_text: str,
    *,
    data_artifacts_likely: bool,
) -> dict[str, Any]:
    return {
        "contract_version": "slide_quality_contract_v1",
        "purpose": (
            "Make readable text, whitespace discipline, evidence anchors, and "
            "artifact QA explicit before the design contract and outline are authored."
        ),
        "source_fields_to_lock": [
            "design_brief.json:readability_contract",
            "design_brief.json:qa_contract.required_checks",
            "design_brief.json:qa_contract.fail_on",
            "design_brief.json:speed_contract",
            "design_brief.json:figure_export_contract",
            "content_plan.json:slide_roles",
            "evidence_plan.json:source_policy",
            "asset_plan.json:charts/tables/images",
            "outline.json:slide variants and evidence anchors",
        ],
        "readability_targets": {
            "min_title_pt": 24,
            "min_body_pt": 12,
            "min_caption_pt": 7.5,
            "chart_label_min_pt": 7,
            "footer_reserved_inches": 0.25,
            "max_title_lines": 2,
            "max_slide_text_lines": 12,
            "max_slide_words": 110,
            "max_slide_chars": 780,
        },
        "layout_targets": {
            "evidence_anchor_required": True,
            "avoid_repeated_card_grids": True,
            "fail_on_awkward_whitespace": True,
            "prefer_source_edit_over_pptx_patch": True,
            "sparse_slide_allowed_only_when_intentional": True,
            "source_footer_rule": "Use compact source/ref IDs in source-line footers; move long references to editable References table slides.",
        },
        "artifact_quality_targets": {
            "required_when_data_artifacts_active": data_artifacts_likely,
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
                "rerun and inspect commands",
            ],
        },
        "qa_gates": {
            "fail_on": [
                "planning_warnings",
                "preflight_errors",
                "overflow",
                "overlap",
                "placeholder_text",
                "whitespace_warnings",
                "design_readability_warnings",
                "visual_review_warnings_for_final_delivery",
            ],
            "required_commands": [
                _shell_join(["python3", "scripts/validate_planning.py", "--workspace", workspace_text]),
                _shell_join(
                    [
                        "python3",
                        "scripts/build_workspace.py",
                        "--workspace",
                        workspace_text,
                        "--qa",
                        "--skip-render",
                        "--fail-on-planning-warnings",
                        "--fail-on-whitespace-warnings",
                        "--overwrite",
                    ]
                ),
                _shell_join(
                    [
                        "python3",
                        "scripts/build_workspace.py",
                        "--workspace",
                        workspace_text,
                        "--qa",
                        "--fail-on-planning-warnings",
                        "--fail-on-whitespace-warnings",
                        "--overwrite",
                    ]
                ),
                _shell_join(["python3", "scripts/report_delivery_readiness.py", "--workspace", workspace_text]),
            ],
        },
        "replay_proof": [
            f"{workspace_text}/deck_start_packet.json:slide_quality_contract",
            f"{workspace_text}/design_contract.json:slide_quality_contract or qa_contract/readability_contract",
            f"{workspace_text}/design_brief.json:readability_contract",
            f"{workspace_text}/build/workspace_readiness.json",
            f"{workspace_text}/build/build_workspace_report.json",
            f"{workspace_text}/build/delivery_readiness.json",
        ],
    }


def _execution_plan(
    workspace_text: str,
    *,
    data_artifacts_likely: bool,
    pptx_style_likely: bool,
    intake_apply_command: str,
    design_contract_apply_command: str,
    outline_authoring_command: str,
    outline_authoring_apply_command: str,
    data_artifact_commands: list[str],
    pptx_style_commands: list[str],
    visual_review_commands: list[str],
) -> dict[str, Any]:
    phases: list[dict[str, Any]] = [
        {
            "id": "ask_or_assume_intake",
            "order": 1,
            "trigger": "always before design routing unless the user already supplied equivalent choices",
            "owner": "main_agent",
            "action": "Ask the compact question packet when useful; otherwise record best-judgment assumptions.",
            "commands": [intake_apply_command],
            "writes": [
                f"{workspace_text}/intake_answers.json",
                f"{workspace_text}/intake_apply_report.json",
                f"{workspace_text}/design_brief.json:user_intake",
                f"{workspace_text}/notes.md:assumptions",
            ],
            "continue_when": [
                "intake answers or assumptions are persisted",
                "style seed is recorded before the design contract is applied",
            ],
        },
        {
            "id": "lock_design_contract",
            "order": 2,
            "trigger": "always before outline authoring",
            "owner": "main_agent_or_design_scout",
            "action": "Return strict deck_design_contract_v1 JSON, save it, and apply it source-first.",
            "commands": [design_contract_apply_command],
            "writes": [
                f"{workspace_text}/design_contract.json",
                f"{workspace_text}/design_contract_apply_report.json",
                f"{workspace_text}/design_brief.json:design_contract",
                f"{workspace_text}/content_plan.json",
                f"{workspace_text}/evidence_plan.json",
                f"{workspace_text}/asset_plan.json",
            ],
            "continue_when": [
                "preset, palette, style seed, header/footer pools, structure, source policy, and QA gates are explicit",
                "unsupported renderer treatments are not introduced",
            ],
        },
    ]
    if pptx_style_likely:
        phases.append(
            {
                "id": "extract_reference_style",
                "order": 3,
                "trigger": "reference PPTX, template, or style corpus detected or requested",
                "owner": "main_agent",
                "action": "Extract measurable style signals and apply only bounded supported treatments.",
                "commands": pptx_style_commands,
                "writes": [
                    f"{workspace_text}/style_extract_report.json",
                    f"{workspace_text}/style_extract_design_brief.json",
                    f"{workspace_text}/style_fragment_apply_report.json",
                    f"{workspace_text}/design_brief.json:style_import",
                ],
                "continue_when": [
                    "style fragment is applied or explicitly skipped with a note",
                    "the contract still owns final preset and style-mix decisions",
                ],
            }
        )
    if data_artifacts_likely:
        phases.append(
            {
                "id": "route_data_artifacts",
                "order": 4,
                "trigger": "local data, spreadsheet, results table, chart, figure, assay, or lab-report signal detected",
                "owner": "main_agent_or_data_scout",
                "action": "Analyze/scaffold local data into reproducible figures, editable chart JSON, summary tables, and binder-ready evidence slides.",
                "commands": data_artifact_commands,
                "writes": [
                    f"{workspace_text}/data_analysis_handoff.json when a scout is used",
                    f"{workspace_text}/data_analysis_handoff_apply_report.json when a scout is used",
                    f"{workspace_text}/assets/make_figures.py",
                    f"{workspace_text}/assets/artifacts_manifest.json",
                    f"{workspace_text}/assets/analysis_summary.json",
                    f"{workspace_text}/artifact_selections.auto.json",
                    f"{workspace_text}/design_brief.json:analysis_artifact_plan",
                    f"{workspace_text}/outline.json:generated evidence slides",
                ],
                "continue_when": [
                    "artifact selections are bound or the artifact step is explicitly out of scope",
                    "source/producers/fingerprints and rerun commands are present for generated outputs",
                ],
            }
        )
    phases.extend(
        [
            {
                "id": "author_outline_from_contract",
                "order": 5,
                "trigger": "after intake and design contract are applied",
                "owner": "main_agent",
                "action": "Emit the contract-aware outline authoring handoff, then write outline.json from the locked structure blueprint and bound evidence objects.",
                "commands": [outline_authoring_command, outline_authoring_apply_command],
                "writes": [
                    f"{workspace_text}/build/outline_authoring_prompt.md",
                    f"{workspace_text}/outline_authoring_handoff.json",
                    f"{workspace_text}/outline_authoring_handoff_apply_report.json",
                    f"{workspace_text}/outline.json",
                    f"{workspace_text}/content_plan.json",
                    f"{workspace_text}/evidence_plan.json",
                    f"{workspace_text}/asset_plan.json",
                    f"{workspace_text}/notes.md:manual design choices",
                ],
                "continue_when": [
                    "every content slide has a visual strategy",
                    "source/citation posture matches evidence_plan.source_policy",
                    "slide variants come from the allowed contract mix",
                ],
            },
            {
                "id": "source_readiness_gate",
                "order": 6,
                "trigger": "before render or when resuming a workspace",
                "owner": "main_agent",
                "action": "Run source-only validation/readiness and patch source files until clean.",
                "commands": [
                    _shell_join(["python3", "scripts/validate_planning.py", "--workspace", workspace_text]),
                    _shell_join(["python3", "scripts/report_workspace_readiness.py", "--workspace", workspace_text]),
                    _shell_join(["python3", "scripts/advance_workspace.py", "--workspace", workspace_text, "--execute", "--max-steps", "3"]),
                ],
                "writes": [
                    f"{workspace_text}/build/planning_validation.json",
                    f"{workspace_text}/build/workspace_readiness.json",
                    f"{workspace_text}/build/workspace_next_action.md",
                ],
                "continue_when": [
                    "planning warnings/errors are resolved or have a source-edit handoff",
                    "readiness status is ready before final report/scientific delivery",
                ],
            },
            {
                "id": "fast_first_pass_build",
                "order": 7,
                "trigger": "first build or quick evidence/data pass",
                "owner": "main_agent",
                "action": "Build with render-free QA to catch planning, overflow, overlap, text density, and whitespace issues quickly.",
                "commands": [
                    _shell_join(
                        [
                            "python3",
                            "scripts/build_workspace.py",
                            "--workspace",
                            workspace_text,
                            "--qa",
                            "--skip-render",
                            "--fail-on-planning-warnings",
                            "--fail-on-whitespace-warnings",
                            "--overwrite",
                        ]
                    )
                ],
                "writes": [
                    f"{workspace_text}/build/build_workspace_report.json",
                    f"{workspace_text}/build/qa/report.json",
                ],
                "continue_when": [
                    "overflow, overlap, design errors, and whitespace warnings are zero",
                    "build report source fingerprints match current sources",
                ],
            },
            {
                "id": "rendered_visual_review",
                "order": 8,
                "trigger": "after source text is stable or final acceptance needs visual inspection",
                "owner": "main_agent_or_visual_qa",
                "action": "Run contact-sheet visual review and convert findings into source edits.",
                "commands": visual_review_commands,
                "writes": [
                    f"{workspace_text}/build/qa/visual_review/visual_review.md",
                    f"{workspace_text}/build/qa/visual_review/visual_review.json",
                    f"{workspace_text}/build/delivery_next_action.md",
                ],
                "continue_when": [
                    "visual issues are patched in source files",
                    "visual-review delivery audit is ready or explicitly waived",
                ],
            },
            {
                "id": "final_delivery_audit",
                "order": 9,
                "trigger": "final handoff",
                "owner": "main_agent",
                "action": "Run strict build and delivery readiness; hand off only when current-source QA and PPTX fingerprint are proven.",
                "commands": [
                    _shell_join(
                        [
                            "python3",
                            "scripts/build_workspace.py",
                            "--workspace",
                            workspace_text,
                            "--qa",
                            "--fail-on-planning-warnings",
                            "--fail-on-whitespace-warnings",
                            "--overwrite",
                        ]
                    ),
                    _shell_join(["python3", "scripts/report_delivery_readiness.py", "--workspace", workspace_text]),
                    _shell_join(["python3", "scripts/advance_delivery.py", "--workspace", workspace_text]),
                ],
                "writes": [
                    f"{workspace_text}/build/build_workspace_report.json",
                    f"{workspace_text}/build/delivery_readiness.json",
                    f"{workspace_text}/build/delivery_readiness.md",
                    f"{workspace_text}/build/delivery_next_action.md",
                ],
                "continue_when": [
                    "delivery_status is ready",
                    "output PPTX fingerprint exists",
                    "strict source-planning and whitespace gates are satisfied",
                ],
            },
        ]
    )
    return {
        "plan_version": "deck_execution_plan_v1",
        "ordering_rule": (
            "Persist intake, apply a design contract, route conditional style/data "
            "work, author outline from the contract, then use readiness, fast QA, "
            "visual review, and delivery audit as explicit gates."
        ),
        "phases": phases,
        "handoff_to_main_agent": (
            "Follow phases in order; skip conditional phases only with a written "
            "reason in notes.md, and fix source files rather than mutating the PPTX."
        ),
    }


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _phase_proof_ledger(
    workspace_text: str,
    *,
    execution_plan: dict[str, Any],
    acceptance_checklist: list[dict[str, Any]],
    route_decision_ledger: dict[str, Any],
) -> dict[str, Any]:
    acceptance_by_phase: dict[str, list[dict[str, Any]]] = {}
    for item in acceptance_checklist:
        if not isinstance(item, dict):
            continue
        phase = str(item.get("phase") or "").strip()
        if not phase:
            continue
        acceptance_by_phase.setdefault(phase, []).append(item)

    phase_to_acceptance = {
        "ask_or_assume_intake": "intake",
        "lock_design_contract": "contract",
        "extract_reference_style": "style",
        "route_data_artifacts": "artifacts",
        "author_outline_from_contract": "outline",
        "source_readiness_gate": "planning",
        "fast_first_pass_build": "build",
        "rendered_visual_review": "visual_review",
        "final_delivery_audit": "delivery",
    }
    route_required = {
        "data_artifacts": "route_data_artifacts",
        "pptx_style_import": "extract_reference_style",
        "rendered_visual_review": "rendered_visual_review",
    }
    route_required_phase_ids = [
        phase_id
        for route in _as_list(route_decision_ledger.get("routes"))
        if isinstance(route, dict)
        and route.get("active") is True
        for phase_id in [route_required.get(str(route.get("id") or ""))]
        if phase_id
    ]

    phases: list[dict[str, Any]] = []
    for phase in _as_list(execution_plan.get("phases")):
        if not isinstance(phase, dict):
            continue
        phase_id = str(phase.get("id") or "").strip()
        acceptance_phase = phase_to_acceptance.get(phase_id, "")
        acceptance_items = acceptance_by_phase.get(acceptance_phase, [])
        establish_commands: list[str] = []
        verify_commands: list[str] = []
        proof: list[str] = []
        gate_ids: list[str] = []
        for item in acceptance_items:
            gate_id = str(item.get("id") or "").strip()
            if gate_id:
                gate_ids.append(gate_id)
            for command in _as_list(item.get("establish_command")) + _as_list(item.get("establish_commands")):
                if isinstance(command, str) and command.strip():
                    establish_commands.append(command)
            for command in _as_list(item.get("verify_commands")):
                if isinstance(command, str) and command.strip():
                    verify_commands.append(command)
            for proof_item in _as_list(item.get("proof")):
                if isinstance(proof_item, str) and proof_item.strip():
                    proof.append(proof_item)
        phases.append(
            {
                "id": phase_id,
                "order": phase.get("order"),
                "owner": phase.get("owner", ""),
                "trigger": phase.get("trigger", ""),
                "required": True,
                "required_by_route": phase_id in route_required_phase_ids,
                "acceptance_gate_ids": gate_ids,
                "commands": _as_list(phase.get("commands")),
                "establish_commands": establish_commands,
                "verify_commands": verify_commands,
                "writes": _as_list(phase.get("writes")),
                "proof": proof,
                "continue_when": _as_list(phase.get("continue_when")),
            }
        )

    return {
        "ledger_version": "deck_phase_proof_ledger_v1",
        "purpose": (
            "Map each execution phase to the exact source files, reports, "
            "commands, and acceptance evidence that prove the phase was handled."
        ),
        "workspace": workspace_text,
        "plan_version": execution_plan.get("plan_version", ""),
        "phase_count": len(phases),
        "phase_ids": [phase["id"] for phase in phases],
        "route_required_phase_ids": route_required_phase_ids,
        "status_sources": [
            f"{workspace_text}/deck_start_packet.json:phase_proof_ledger",
            f"{workspace_text}/build/workspace_readiness.json:execution_plan",
            f"{workspace_text}/build/workspace_advance_report.json:final_execution_plan",
            f"{workspace_text}/build/build_workspace_report.json:source_files",
            f"{workspace_text}/build/delivery_readiness.json:delivery_status",
        ],
        "phases": phases,
    }


def _active_route_ids(route_decision_ledger: dict[str, Any]) -> list[str]:
    routes = route_decision_ledger.get("routes") if isinstance(route_decision_ledger, dict) else []
    if not isinstance(routes, list):
        return []
    return [
        str(route.get("id") or "").strip()
        for route in routes
        if isinstance(route, dict)
        and bool(route.get("active"))
        and str(route.get("id") or "").strip()
    ]


def _phase_command_map(execution_plan: dict[str, Any]) -> dict[str, list[str]]:
    phases = execution_plan.get("phases") if isinstance(execution_plan, dict) else []
    if not isinstance(phases, list):
        return {}
    commands: dict[str, list[str]] = {}
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_id = str(phase.get("id") or "").strip()
        if not phase_id:
            continue
        phase_commands = [
            str(command).strip()
            for command in _as_list(phase.get("commands"))
            if str(command).strip()
        ]
        if phase_commands:
            commands[phase_id] = phase_commands
    return commands


def _acceptance_gate_ids(acceptance_checklist: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("id") or "").strip()
        for item in acceptance_checklist
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]


def _agent_kickoff_brief(
    workspace_text: str,
    *,
    stable_id: str,
    user_prompt: str,
    preset_treatment: dict[str, Any],
    intake: dict[str, Any],
    intake_answers_template: dict[str, Any],
    source_inventory: dict[str, Any],
    route_decision_ledger: dict[str, Any],
    execution_plan: dict[str, Any],
    acceptance_checklist: list[dict[str, Any]],
    slide_quality_contract: dict[str, Any],
    data_artifacts_likely: bool,
    pptx_style_likely: bool,
) -> dict[str, Any]:
    request = intake.get("request_user_input") if isinstance(intake.get("request_user_input"), dict) else {}
    question_ids = [
        str(question.get("id") or "").strip()
        for question in _as_list(request.get("questions"))
        if isinstance(question, dict) and str(question.get("id") or "").strip()
    ]
    phase_commands = _phase_command_map(execution_plan)
    active_routes = _active_route_ids(route_decision_ledger)
    return {
        "contract_version": "deck_agent_kickoff_brief_v1",
        "stable_prompt_id": stable_id,
        "workspace": workspace_text,
        "user_request_summary": user_prompt or "<original user request>",
        "purpose": (
            "Give the main agent a reproducible first-turn operating brief before "
            "source files or slides are authored."
        ),
        "question_trigger": {
            "ask_user_input": bool(question_ids),
            "question_ids": question_ids,
            "auto_resolution_ms": request.get("autoResolutionMs"),
            "answer_file": f"{workspace_text}/intake_answers.json",
            "answer_file_template": intake_answers_template,
            "fallback": "Persist best-judgment assumptions if the user does not answer.",
        },
        "route_snapshot": {
            "active_routes": active_routes,
            "data_artifacts_likely": data_artifacts_likely,
            "pptx_style_likely": pptx_style_likely,
            "source_inventory": _source_inventory_summary(source_inventory),
        },
        "preset_treatment_profile": preset_treatment,
        "slide_quality_contract": slide_quality_contract,
        "locked_replay_fields": [
            "stable_prompt_id",
            "style_system.style_seed",
            "style_system.style_preset",
            "style_system.style_mix_matrix",
            "style_system.background_system",
            "structure_blueprint.slide_sequence",
            "structure_blueprint.slide_variant_mix",
            "slide_quality_contract",
            "readability_contract",
            "speed_contract",
            "qa_contract.fail_on",
            "source_policy",
            "asset_posture",
            "analysis_artifact_plan",
            "figure_export_contract",
        ],
        "required_contracts": [
            {
                "name": "deck_design_contract_v1",
                "save_to": f"{workspace_text}/design_contract.json",
                "must_include": [
                    "choice_resolution",
                    "reproducibility_contract",
                    "style_system.style_mix_matrix",
                    "structure_blueprint",
                    "slide_quality_contract",
                    "readability_contract",
                    "speed_contract",
                    "qa_contract",
                    "acceptance_evidence",
                    "agent_execution_plan",
                ],
            },
            {
                "name": "deck_reproducibility_contract_v1",
                "save_to": f"{workspace_text}/design_brief.json:reproducibility_contract",
                "must_include": [
                    "style_seed",
                    "renderer",
                    "locked_design_fields",
                    "style_replay",
                    "structure_replay",
                    "artifact_replay",
                    "replay_commands",
                    "acceptance_evidence",
                ],
            },
            {
                "name": "outline_authoring_handoff_v1",
                "save_to": f"{workspace_text}/outline_authoring_handoff.json",
                "must_include": [
                    "source_patch",
                    "slide_plan",
                    "evidence_bindings",
                    "artifact_bindings",
                    "qa_notes",
                ],
            },
        ],
        "artifact_obligations": {
            "required_when_active": data_artifacts_likely,
            "must_record": [
                "source fingerprints",
                "producer script fingerprints",
                "chart JSON or editable table outputs",
                "slide-ready figure paths",
                "analysis_summary.json",
                "artifact selection bindings",
                "rerun commands",
                "figure whitespace/readability assumptions",
            ],
        },
        "style_obligations": {
            "required_when_reference_pptx_active": pptx_style_likely,
            "must_record": [
                "loadable base preset",
                "palette key",
                "font pair",
                "header/footer variant pools",
                "page-number/source-footer posture",
                "bounded style fragment path when extracting a reference PPTX",
                "unsupported style signals explicitly skipped",
            ],
        },
        "command_ladder": {
            "intake": phase_commands.get("ask_or_assume_intake", []),
            "design_contract": phase_commands.get("lock_design_contract", []),
            "pptx_style": phase_commands.get("extract_reference_style", []),
            "data_artifacts": phase_commands.get("route_data_artifacts", []),
            "outline_authoring": phase_commands.get("author_outline_from_contract", []),
            "source_readiness": phase_commands.get("source_readiness_gate", []),
            "fast_first_pass": phase_commands.get("fast_first_pass_build", []),
            "rendered_visual_review": phase_commands.get("rendered_visual_review", []),
            "final_delivery": phase_commands.get("final_delivery_audit", []),
        },
        "acceptance_gate_ids": _acceptance_gate_ids(acceptance_checklist),
        "main_agent_next_steps": [
            "Ask the compact question packet or persist best-judgment assumptions.",
            "Apply intake answers before authoring the design contract.",
            "Author/apply deck_design_contract_v1 with reproducibility_contract included.",
            "Run only active style/data routes and record skipped route reasons.",
            "Author outline through outline_authoring_handoff_v1, not by mutating generated PPTX.",
            "Use advance_workspace.py, fast QA, visual review, and delivery readiness as gates.",
        ],
        "no_go_rules": [
            "Do not author outline.json before applying design_contract.json.",
            "Do not leave data-derived figures without scripts, fingerprints, and rerun commands.",
            "Do not patch generated PPTX files as the source of truth.",
            "Do not introduce unsupported renderer treatments or unreadable text sizes.",
            "Do not ignore whitespace/readability warnings before delivery.",
        ],
    }


def _agent_kickoff_prompt(brief: dict[str, Any]) -> str:
    return (
        "AGENT KICKOFF BRIEF\n"
        "Use this deck_agent_kickoff_brief_v1 object as the first-turn "
        "operating brief for the main agent and any scouts. Follow the command "
        "ladder, keep active/skipped route decisions explicit, and preserve the "
        "required replay fields in the design contract.\n"
        + json.dumps(brief, indent=2, sort_keys=True, ensure_ascii=False)
    )


def _scout_commands(*, workspace: Path | None, user_prompt: str) -> list[dict[str, str]]:
    workspace_text = _workspace_arg(workspace)
    prompt_text = user_prompt.strip() or "<original user request>"
    commands: list[dict[str, str]] = [
        {
            "name": "design_contract_scout",
            "when": "Always run or answer directly before outline authoring.",
            "command": _shell_join(
                [
                    "python3",
                    "scripts/emit_design_contract_prompt.py",
                    "--workspace",
                    workspace_text,
                    "--user-prompt",
                    prompt_text,
                ]
            ),
            "expected_output": "Strict deck_design_contract_v1 JSON to save as design_contract.json and apply with scripts/apply_design_contract.py.",
        },
        {
            "name": "outline_authoring_handoff",
            "when": "Use after design_contract.json has been applied and before replacing the starter outline.",
            "command": _outline_authoring_prompt_command(workspace_text, prompt_text),
            "apply_command": _outline_authoring_apply_command(workspace_text),
            "expected_output": "A contract-aware outline authoring prompt that returns outline_authoring_handoff_v1 JSON; save it as outline_authoring_handoff.json and apply with apply_outline_authoring_handoff.py.",
        },
        {
            "name": "style_content_router",
            "when": "Use for non-trivial, scientific, asset-heavy, or visually ambiguous decks.",
            "command": _shell_join(
                [
                    "python3",
                    "scripts/emit_style_content_router.py",
                    "--workspace",
                    workspace_text,
                    "--user-prompt",
                    prompt_text,
                ]
            ),
            "expected_output": "JSON design DNA, variant mix, asset needs, and QA sensitivities.",
        },
    ]

    if _pptx_style_likely(workspace=workspace, user_prompt=user_prompt):
        style_commands = _pptx_style_commands(workspace_text, workspace=workspace)
        commands.append(
            {
                "name": "pptx_style_extraction",
                "when": "Use before design-contract routing when a template, prior deck, or PPTX corpus should inspire a new source-driven deck.",
                "command": style_commands[0],
                "apply_command": style_commands[1],
                "expected_output": "Observed header/footer/page-number/palette/readability signals plus a bounded design_brief fragment; apply the fragment, do not clone slide XML.",
            }
        )

    if _data_artifacts_likely(workspace=workspace, user_prompt=user_prompt):
        commands.append(
            {
                "name": "data_evidence_analysis",
                "when": "Use before claims/figures when local data, spreadsheets, results tables, or chart candidates matter.",
                "command": _shell_join(
                    [
                        "python3",
                        "scripts/emit_data_analysis_prompt.py",
                        "--workspace",
                        workspace_text,
                        "--user-prompt",
                        prompt_text,
                    ]
                ),
                "apply_command": _data_artifact_commands(workspace_text)[0],
                "expected_output": "JSON findings, chart/table recommendations, provenance, binder-ready artifact selections, and figure_export_contract updates. Save as data_analysis_handoff.json and apply deterministic pieces with apply_data_analysis_handoff.py.",
            }
        )
        commands.append(
            {
                "name": "figure_artifact_scaffold",
                "when": "Use after identifying simple local CSV/TSV/XLSX/JSON tables that should become reusable chart/figure artifacts.",
                "command": _shell_join(
                    [
                        "python3",
                        "scripts/scaffold_figure_artifacts.py",
                        "--workspace",
                        workspace_text,
                        "--run",
                        "--bind-outline",
                    ]
                ),
                "expected_output": "assets/make_figures.py, figures, chart JSON, staged table:<name> summary-table aliases, assets/analysis_summary.json, and design_brief/asset_plan artifact updates.",
            }
        )

    if _contains_any(user_prompt, RESEARCH_HINTS):
        commands.append(
            {
                "name": "content_research_after_outline",
                "when": "Use after a draft outline exists if factual claims need concrete sourced anchors.",
                "command": _shell_join(
                    [
                        "python3",
                        "scripts/emit_content_research.py",
                        "--outline",
                        f"{workspace_text}/outline.json",
                    ]
                ),
                "expected_output": "Slide-indexed punch list of concrete facts/source types to verify and fold into the outline.",
            }
        )

    commands.append(
        {
            "name": "outline_critique_before_build",
            "when": "Use after outline.json exists and before the first final build.",
            "command": _shell_join(
                [
                    "python3",
                    "scripts/emit_outline_critique.py",
                    "--outline",
                    f"{workspace_text}/outline.json",
                ]
            ),
            "expected_output": "Punch list for variant monotony, weak visual anchors, density, and source-level composition fixes.",
        }
    )
    visual_review_commands = _visual_review_commands(workspace_text)
    commands.append(
        {
            "name": "rendered_visual_review_after_build",
            "when": "Use after source text and first build are stable, or whenever final acceptance needs a rendered contact sheet.",
            "command": visual_review_commands[0],
            "delivery_audit_command": visual_review_commands[1],
            "advance_command": visual_review_commands[2],
            "expected_output": "build/qa/visual_review contact sheet, visual_review.json, visual_review.md, and delivery/source-edit handoff when rendered visual issues remain.",
        }
    )
    return commands


def build_packet(*, workspace: Path | None, user_prompt: str, mode: str) -> dict[str, Any]:
    user_prompt_clean = user_prompt.strip()
    stable_id = _stable_id(user_prompt_clean or "deck")
    intake = json.loads(
        render_codex_ui_spec(
            workspace=workspace,
            user_prompt=user_prompt_clean,
            mode=mode,
        )
    )
    contract_prompt = render_contract_prompt(
        user_prompt=user_prompt_clean or "<original user request>",
        workspace=workspace,
    )
    workspace_text = _workspace_arg(workspace)
    source_inventory = _workspace_source_inventory(workspace)
    preset_treatment = preset_treatment_profile(_workspace_style_preset(workspace))
    data_artifacts_likely = _data_artifacts_likely(
        workspace=workspace,
        user_prompt=user_prompt_clean,
    )
    pptx_style_likely = _pptx_style_likely(
        workspace=workspace,
        user_prompt=user_prompt_clean,
    )
    data_artifact_commands = _data_artifact_commands(workspace_text) if data_artifacts_likely else []
    pptx_style_commands = _pptx_style_commands(workspace_text, workspace=workspace) if pptx_style_likely else []
    visual_review_commands = _visual_review_commands(workspace_text)
    intake_apply_command = _intake_apply_command(workspace_text)
    design_contract_apply_command = _design_contract_apply_command(workspace_text)
    outline_authoring_command = _outline_authoring_prompt_command(workspace_text, user_prompt_clean)
    outline_authoring_apply_command = _outline_authoring_apply_command(workspace_text)
    intake_answers_template = _intake_answers_template()
    acceptance_checklist = _acceptance_checklist(
        workspace_text,
        workspace=workspace,
        data_artifacts_likely=data_artifacts_likely,
        pptx_style_likely=pptx_style_likely,
    )
    execution_plan = _execution_plan(
        workspace_text,
        data_artifacts_likely=data_artifacts_likely,
        pptx_style_likely=pptx_style_likely,
        intake_apply_command=intake_apply_command,
        design_contract_apply_command=design_contract_apply_command,
        outline_authoring_command=outline_authoring_command,
        outline_authoring_apply_command=outline_authoring_apply_command,
        data_artifact_commands=data_artifact_commands,
        pptx_style_commands=pptx_style_commands,
        visual_review_commands=visual_review_commands,
    )
    choice_resolution_contract = _choice_resolution_contract(
        workspace_text,
        stable_id=stable_id,
        source_inventory=source_inventory,
        data_artifacts_likely=data_artifacts_likely,
        pptx_style_likely=pptx_style_likely,
    )
    slide_quality_contract = _slide_quality_contract(
        workspace_text,
        data_artifacts_likely=data_artifacts_likely,
    )
    route_decision_ledger = _route_decision_ledger(
        workspace_text,
        workspace=workspace,
        user_prompt=user_prompt_clean,
        source_inventory=source_inventory,
        data_artifacts_likely=data_artifacts_likely,
        pptx_style_likely=pptx_style_likely,
        data_artifact_commands=data_artifact_commands,
        pptx_style_commands=pptx_style_commands,
        visual_review_commands=visual_review_commands,
    )
    phase_proof_ledger = _phase_proof_ledger(
        workspace_text,
        execution_plan=execution_plan,
        acceptance_checklist=acceptance_checklist,
        route_decision_ledger=route_decision_ledger,
    )
    agent_kickoff_brief = _agent_kickoff_brief(
        workspace_text,
        stable_id=stable_id,
        user_prompt=user_prompt_clean,
        preset_treatment=preset_treatment,
        intake=intake,
        intake_answers_template=intake_answers_template,
        source_inventory=source_inventory,
        route_decision_ledger=route_decision_ledger,
        execution_plan=execution_plan,
        acceptance_checklist=acceptance_checklist,
        slide_quality_contract=slide_quality_contract,
        data_artifacts_likely=data_artifacts_likely,
        pptx_style_likely=pptx_style_likely,
    )
    agent_kickoff_prompt = _agent_kickoff_prompt(agent_kickoff_brief)
    choice_resolution_prompt = (
        "\n\nCHOICE RESOLUTION CONTRACT\n"
        "Use this `choice_resolution_contract` deck_choice_resolution_v1 ledger "
        "to translate the compact question-card answers into the returned "
        "deck_design_contract_v1 JSON. "
        "Your JSON must include a top-level `choice_resolution` object that "
        "summarizes the resolved choices, the chosen defaults, the active "
        "data/style routes, and the source fields that must be written by the "
        "main agent.\n"
        + json.dumps(choice_resolution_contract, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n\nSLIDE QUALITY CONTRACT\n"
        "Use this `slide_quality_contract` slide_quality_contract_v1 object "
        "as the compact QA target for the design contract and outline. Copy it "
        "or map it into `readability_contract`, `qa_contract`, "
        "`figure_export_contract`, and slide-variant choices. Do not loosen "
        "these targets unless the main agent records the reason.\n"
        + json.dumps(slide_quality_contract, indent=2, sort_keys=True, ensure_ascii=False)
        + "\n\nROUTE DECISION LEDGER\n"
        "Use this `route_decision_ledger` deck_route_decision_ledger_v1 packet "
        "as the audit trail for active, inactive, and conditional workflow "
        "routes. Copy its active route decisions into "
        "`choice_resolution.route_decisions` and record skipped conditional "
        "routes only with an explicit reason.\n"
        + json.dumps(route_decision_ledger, indent=2, sort_keys=True, ensure_ascii=False)
    )

    return {
        "workflow": "deck_start_packet_v1",
        "stable_prompt_id": stable_id,
        "recommended_style_seed": stable_id,
        "usage": (
            "Run immediately after the user's deck request. Ask the compact "
            "question packet if useful, then produce the strict design "
            "contract before writing outline.json."
        ),
        "request_user_input": intake["request_user_input"],
        "if_user_does_not_answer": (
            "Proceed with best judgment, record assumptions under "
            "design_brief.user_intake, and keep the design contract explicit."
        ),
        "after_answers": {
            "answer_file": f"{workspace_text}/intake_answers.json",
            "answer_file_template": intake_answers_template,
            "apply_answers_command": intake_apply_command,
            "apply_answers_report": f"{workspace_text}/intake_apply_report.json",
            "design_contract_file": f"{workspace_text}/design_contract.json",
            "apply_design_contract_command": design_contract_apply_command,
            "apply_design_contract_report": f"{workspace_text}/design_contract_apply_report.json",
            "record_answers_to": [
                f"{workspace_text}/design_brief.json: design_brief.user_intake",
                f"{workspace_text}/design_brief.json: style_system.style_seed = {stable_id}",
                f"{workspace_text}/notes.md: assumptions and unresolved inputs",
            ],
            "translate_answers_to": [
                "design_modulation",
                "visual_system",
                "deck_style",
                "title_page_concept",
                "asset_plan",
                "evidence_plan.source_policy",
                "design_contract.choice_resolution",
            ],
            "then_run_or_answer": "design_contract_scout",
            "optional_scouts": _scout_commands(
                workspace=workspace,
                user_prompt=user_prompt_clean,
            ),
        },
        "workspace_source_inventory": source_inventory,
        "choice_resolution_contract": choice_resolution_contract,
        "route_decision_ledger": route_decision_ledger,
        "slide_quality_contract": slide_quality_contract,
        "phase_proof_ledger": phase_proof_ledger,
        "agent_kickoff_brief": agent_kickoff_brief,
        "application_contract": {
            "data_artifacts_likely": data_artifacts_likely,
            "pptx_style_likely": pptx_style_likely,
            "preset_treatment_profile": preset_treatment,
            "workspace_source_inventory": _source_inventory_summary(source_inventory),
            "choice_resolution_contract": choice_resolution_contract,
            "route_decision_ledger": route_decision_ledger,
            "slide_quality_contract": slide_quality_contract,
            "phase_proof_ledger": phase_proof_ledger,
            "file_write_order": [
                "design_brief.json",
                "content_plan.json",
                "evidence_plan.json",
                "asset_plan.json",
                "outline.json",
                "notes.md",
            ],
            "must_persist": [
                {
                    "input": "explicit user answers or best-judgment defaults",
                    "target": f"{workspace_text}/design_brief.json:user_intake",
                },
                {
                    "input": "recommended deterministic style seed",
                    "target": f"{workspace_text}/design_brief.json:style_system.style_seed={stable_id}",
                },
                {
                    "input": "strict deck_design_contract_v1 JSON from design scout or main agent",
                    "target": f"{workspace_text}/design_contract.json and deterministic apply_design_contract.py source updates",
                },
                {
                    "input": "resolved question-card choices and route decisions",
                    "target": f"{workspace_text}/design_brief.json:design_contract.choice_resolution",
                },
                {
                    "input": "slide_quality_contract_v1 readability, whitespace, artifact, and QA targets",
                    "target": f"{workspace_text}/design_brief.json:readability_contract and qa_contract",
                },
                {
                    "input": "missing inputs and assumptions",
                    "target": f"{workspace_text}/notes.md:assumptions",
                },
                {
                    "input": "source and citation posture",
                    "target": f"{workspace_text}/evidence_plan.json:source_policy",
                },
                {
                    "input": "local, web, generated, chart, table, and background asset posture",
                    "target": f"{workspace_text}/asset_plan.json",
                },
                *(
                    [
                        {
                            "input": "reference PPTX/corpus style extraction report and reusable fragment",
                            "target": f"{workspace_text}/style_extract_report.json, {workspace_text}/style_extract_design_brief.json, and {workspace_text}/design_brief.json:style_import",
                        },
                    ]
                    if pptx_style_likely
                    else []
                ),
                *(
                    [
                        {
                            "input": "data inputs, generated figures/charts/tables, analysis summary, artifact registry, and rebuild commands",
                            "target": f"{workspace_text}/design_brief.json:analysis_artifact_plan and figure_export_contract",
                        },
                        {
                            "input": "generated chart/table/image aliases from scaffold report",
                            "target": f"{workspace_text}/asset_plan.json and {workspace_text}/outline.json asset refs",
                        },
                    ]
                    if data_artifacts_likely
                    else []
                ),
            ],
            "must_translate": [
                {
                    "from": "audience/use context",
                    "to": [
                        "deck_identity or audience_posture",
                        "content_plan.audience",
                        "readability_contract density thresholds",
                    ],
                },
                {
                    "from": "style, palette, density, and background answers",
                    "to": [
                        "design_modulation",
                        "visual_system",
                        "deck_style",
                        "title_page_concept",
                        "style_mix_matrix",
                    ],
                },
                {
                    "from": "evidence/assets/source answers",
                    "to": [
                        "evidence_plan.source_policy",
                        "asset_plan",
                        "analysis_artifact_plan",
                        "figure_export_contract",
                    ],
                },
                {
                    "from": "choice_resolution_contract",
                    "to": [
                        "design_contract.choice_resolution",
                        "design_brief.design_contract.choice_resolution",
                        "route_decision_ledger active routes",
                        "style_system.style_mix_matrix",
                        "readability_contract",
                        "slide_quality_contract",
                        "evidence_plan.source_policy",
                        "analysis_artifact_plan",
                        "figure_export_contract",
                    ],
                },
            ],
            "fast_first_pass_commands": [
                _shell_join(["python3", "scripts/validate_planning.py", "--workspace", workspace_text]),
                _shell_join(
                    [
                        "python3",
                        "scripts/build_workspace.py",
                        "--workspace",
                        workspace_text,
                        "--qa",
                        "--skip-render",
                        "--fail-on-planning-warnings",
                        "--fail-on-whitespace-warnings",
                        "--overwrite",
                    ]
                ),
            ],
            "intake_answer_commands": [
                intake_apply_command,
            ],
            "design_contract_commands": [
                design_contract_apply_command,
            ],
            "outline_authoring_commands": [
                outline_authoring_command,
                outline_authoring_apply_command,
            ],
            "pptx_style_commands": pptx_style_commands,
            "data_artifact_commands": data_artifact_commands,
            "visual_review_commands": visual_review_commands,
            "final_report_commands": [
                _shell_join(
                    [
                        "python3",
                        "scripts/build_workspace.py",
                        "--workspace",
                        workspace_text,
                        "--qa",
                        "--fail-on-planning-warnings",
                        "--fail-on-whitespace-warnings",
                        "--overwrite",
                    ]
                ),
                _shell_join(
                    [
                        "python3",
                        "scripts/report_delivery_readiness.py",
                        "--workspace",
                        workspace_text,
                    ]
                ),
                _shell_join(
                    [
                        "python3",
                        "scripts/advance_delivery.py",
                        "--workspace",
                        workspace_text,
                    ]
                ),
            ],
            "acceptance_checklist": acceptance_checklist,
        },
        "execution_plan": execution_plan,
        "main_agent_handoff_prompt": (
            "Persist question-card answers with apply_deck_intake_answers.py, "
            "use choice_resolution_contract as the decision ledger for mapping "
            "compact answers into source fields, "
            "save the strict deck_design_contract_v1 JSON to design_contract.json, "
            "then run apply_design_contract.py and emit_outline_authoring_prompt.py "
            "before authoring outline.json. Save the returned "
            "outline_authoring_handoff_v1 JSON to outline_authoring_handoff.json "
            "and run apply_outline_authoring_handoff.py to patch source files. "
            "Use slide_quality_contract_v1 as the compact target for readable "
            "text, whitespace, evidence anchors, artifact metadata, and QA gates. "
            "Keep choices reproducible: "
            "preset, palette, style seed, background, title layout, "
            "header/footer variant pool, slide-variant mix, artifact scripts, "
            "source policy, and QA commands must all be explicit. Prefer "
            "deterministic scripts for data-derived figures and record rerun commands."
        ),
        "main_agent_kickoff_prompt": agent_kickoff_prompt,
        "subagent_prompt": agent_kickoff_prompt + "\n\n" + contract_prompt + choice_resolution_prompt,
        "reproducibility_requirements": {
            "style": [
                "base preset",
                "palette key",
                "font pair",
                f"style seed for deterministic treatment rotation: {stable_id}",
                "background system",
                "header/footer pool",
                "allowed slide variants",
                "forbidden treatments",
            ],
            "artifacts": [
                "data inputs",
                "analysis scripts",
                "chart/table outputs",
                "figure exports",
                "artifact registry",
                "rerun commands",
            ],
            "qa": [
                "schema/preflight before rendering",
                "readability_contract prose budgets for static text-density preflight",
                "slide_quality_contract_v1 for text floors, whitespace policy, evidence anchors, artifact QA, and replay commands",
                "strict geometry checks",
                "readability checks for text, charts, captions, and footer",
                "rendered visual review only after source is stable",
                "visual_review_commands for contact-sheet QA plus --require-visual-review delivery audit when final acceptance needs rendered inspection",
                "delivery readiness audit with build report, QA counts, and output fingerprint",
                "delivery next-action handoff for strict final build or source edits",
            ],
        },
        "acceptance_checklist": acceptance_checklist,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a first-turn packet for reproducible deck generation."
    )
    parser.add_argument("--workspace", help="Optional deck workspace directory")
    parser.add_argument("--user-prompt", required=True, help="Original user request")
    parser.add_argument(
        "--mode",
        choices=["concise", "full"],
        default="concise",
        help="Question set size for the embedded intake packet.",
    )
    parser.add_argument("--output", help="Write JSON packet to this file")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None
    packet = build_packet(
        workspace=workspace,
        user_prompt=args.user_prompt,
        mode=args.mode,
    )
    output_text = json.dumps(packet, indent=2, ensure_ascii=False) + "\n"

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
