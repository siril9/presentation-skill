#!/usr/bin/env python3
"""Fast smoke check for deck-start packet and intake answer application."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


USER_PROMPT = (
    "Build a clean lab report deck from assay CSV data with figures, "
    "compact source footers, references, and page numbers."
)

ANSWER_FIXTURES = {
    "audience_context": (
        "PI and translational assay team; use as a dense live review and "
        "leave-behind report."
    ),
    "target_outcome": (
        "Show which assay readouts pass, where evidence is still thin, and "
        "what follow-up analysis is needed."
    ),
    "style_direction": (
        "Clean lab-report/figure-first style with restrained header variants, "
        "bottom source rule, and no decorative card grids."
    ),
    "density": "Dense report/leave-behind pages with readable figures and compact captions.",
    "palette": "Restrained neutral lab palette with one high-contrast accent.",
    "background_visuals": "White report body with generated figures and source-backed visuals only when useful.",
    "evidence_assets": "Use local data-derived charts, summary tables, and slide-ready figures.",
    "source_policy": "Use compact source-line footer IDs and move long references to final refs slides.",
    "constraints": "No awkward whitespace, no unreadable table text, no unsupported renderer treatments.",
    "style_density": "Lab-report/figure-first with dense report pages.",
    "visual_source_policy": "Use local data, generated charts, compact source footers, page numbers, and final references.",
}


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _run_checked(
    cmd: list[str],
    *,
    cwd: Path,
    command_results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    allowed_returncodes: set[int] | None = None,
) -> None:
    allowed = allowed_returncodes if allowed_returncodes is not None else {0}
    result = _run(cmd, cwd=cwd)
    command_results.append(
        {
            "command": cmd,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-1200:],
        }
    )
    if result.returncode not in allowed:
        failures.append({"step": Path(cmd[1]).name, "returncode": result.returncode})


def _load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _packet_question_ids(packet: dict[str, Any]) -> list[str]:
    request = packet.get("request_user_input")
    questions = request.get("questions") if isinstance(request, dict) else []
    if not isinstance(questions, list):
        return []
    ids: list[str] = []
    for item in questions:
        if isinstance(item, dict):
            question_id = str(item.get("id") or "").strip()
            if question_id:
                ids.append(question_id)
    return ids


def _answer_ids_from_template(packet: dict[str, Any]) -> list[str]:
    after_answers = packet.get("after_answers")
    template = (
        after_answers.get("answer_file_template")
        if isinstance(after_answers, dict)
        else {}
    )
    answers = template.get("answers") if isinstance(template, dict) else []
    ids: list[str] = []
    if isinstance(answers, list):
        for item in answers:
            if isinstance(item, dict):
                answer_id = str(item.get("id") or "").strip()
                if answer_id:
                    ids.append(answer_id)
    return ids


def _build_answers(packet: dict[str, Any]) -> dict[str, Any]:
    answer_ids = _packet_question_ids(packet) or _answer_ids_from_template(packet)
    answers = [
        {
            "id": answer_id,
            "answer": ANSWER_FIXTURES.get(
                answer_id,
                "Use best judgment; keep the deck structured, reproducible, and readable.",
            ),
        }
        for answer_id in answer_ids
    ]
    return {
        "answers": answers,
        "answered_by": "best_judgment",
    }


def _active_route_ids(route_ledger: dict[str, Any]) -> list[str]:
    routes = route_ledger.get("routes") if isinstance(route_ledger, dict) else []
    if not isinstance(routes, list):
        return []
    return sorted(
        str(item.get("id") or "").strip()
        for item in routes
        if isinstance(item, dict)
        and str(item.get("id") or "").strip()
        and bool(item.get("active"))
    )


def _assert_required_packet(packet: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    required_keys = [
        "workflow",
        "recommended_style_seed",
        "request_user_input",
        "after_answers",
        "choice_resolution_contract",
        "workspace_source_inventory",
        "route_decision_ledger",
        "slide_quality_contract",
        "phase_proof_ledger",
        "agent_kickoff_brief",
        "execution_plan",
        "application_contract",
        "atom_workflow_context",
        "acceptance_checklist",
        "main_agent_kickoff_prompt",
        "subagent_prompt",
    ]
    for key in required_keys:
        if key not in packet:
            failures.append({"step": "deck_start_packet", "reason": "missing_key", "key": key})

    if packet.get("workflow") != "deck_start_packet_v1":
        failures.append({"step": "deck_start_packet", "reason": "wrong_workflow", "workflow": packet.get("workflow")})
    if not str(packet.get("recommended_style_seed") or "").strip():
        failures.append({"step": "deck_start_packet", "reason": "missing_recommended_style_seed"})

    request = packet.get("request_user_input") if isinstance(packet.get("request_user_input"), dict) else {}
    questions = request.get("questions") if isinstance(request, dict) else []
    if not isinstance(questions, list) or not questions:
        failures.append({"step": "deck_start_packet", "reason": "missing_questions"})
    if not isinstance(request.get("autoResolutionMs"), int):
        failures.append({"step": "deck_start_packet", "reason": "missing_auto_resolution_ms"})

    template_ids = _answer_ids_from_template(packet)
    question_ids = _packet_question_ids(packet)
    if question_ids and not set(question_ids).issubset(set(template_ids)):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "answer_template_missing_question_ids",
                "question_ids": question_ids,
                "template_ids": template_ids,
            }
        )

    choice_contract = packet.get("choice_resolution_contract")
    if not isinstance(choice_contract, dict) or choice_contract.get("contract_version") != "deck_choice_resolution_v1":
        failures.append({"step": "deck_start_packet", "reason": "bad_choice_resolution_contract"})
    source_inventory = packet.get("workspace_source_inventory")
    if not isinstance(source_inventory, dict) or source_inventory.get("data_file_count", 0) < 1:
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "source_inventory_missing_data_file",
                "source_inventory": source_inventory,
            }
        )
    else:
        data_files = source_inventory.get("data_files")
        if not isinstance(data_files, list) or not any(
            isinstance(item, dict)
            and item.get("path") == "data/assay_results.csv"
            and item.get("sha256")
            for item in data_files
        ):
            failures.append(
                {
                    "step": "deck_start_packet",
                    "reason": "source_inventory_missing_hashed_fixture",
                    "data_files": data_files,
                }
            )
    route_ledger = packet.get("route_decision_ledger")
    if not isinstance(route_ledger, dict) or route_ledger.get("ledger_version") != "deck_route_decision_ledger_v1":
        failures.append({"step": "deck_start_packet", "reason": "bad_route_decision_ledger"})
    elif route_ledger.get("source_inventory_summary", {}).get("data_file_count", 0) < 1:
        failures.append({"step": "deck_start_packet", "reason": "route_ledger_missing_source_inventory"})
    active_routes = _active_route_ids(route_ledger if isinstance(route_ledger, dict) else {})
    if "atom_composition" not in active_routes:
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "atom_composition_route_not_active",
                "routes": active_routes,
            }
        )
    atom_context = (
        packet.get("atom_workflow_context")
        if isinstance(packet.get("atom_workflow_context"), dict)
        else {}
    )
    if (
        atom_context.get("schema_version") != "normal_workflow_atom_context_v1"
        or atom_context.get("route_id") != "atom_composition"
        or not isinstance(atom_context.get("style_atom_composition"), dict)
        or not atom_context.get("style_atom_composition")
        or not isinstance(atom_context.get("preferred_variants"), list)
        or not atom_context.get("preferred_variants")
    ):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "bad_atom_workflow_context",
                "atom_workflow_context": atom_context,
            }
        )
    strict_prompt = str(atom_context.get("strict_json_prompt") or "")
    strict_instruction = str(atom_context.get("strict_json_instruction") or "")
    if (
        "Use strict JSON only" not in strict_prompt
        and "Use strict JSON only" not in strict_instruction
    ) or not str(atom_context.get("target_family") or "").strip():
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "atom_context_missing_strict_json_prompt",
            }
        )
    quality_contract = packet.get("slide_quality_contract")
    if not isinstance(quality_contract, dict) or quality_contract.get("contract_version") != "slide_quality_contract_v1":
        failures.append({"step": "deck_start_packet", "reason": "bad_slide_quality_contract"})
        quality_contract = {}
    readability = (
        quality_contract.get("readability_targets")
        if isinstance(quality_contract.get("readability_targets"), dict)
        else {}
    )
    if (
        readability.get("min_title_pt") != 24
        or readability.get("min_body_pt") != 12
        or readability.get("chart_label_min_pt") != 7
        or readability.get("footer_reserved_inches") != 0.25
    ):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "slide_quality_readability_targets_bad",
                "readability_targets": readability,
            }
        )
    layout_targets = (
        quality_contract.get("layout_targets")
        if isinstance(quality_contract.get("layout_targets"), dict)
        else {}
    )
    if (
        layout_targets.get("evidence_anchor_required") is not True
        or layout_targets.get("fail_on_awkward_whitespace") is not True
        or "References" not in str(layout_targets.get("source_footer_rule") or "")
    ):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "slide_quality_layout_targets_bad",
                "layout_targets": layout_targets,
            }
        )
    artifact_targets = (
        quality_contract.get("artifact_quality_targets")
        if isinstance(quality_contract.get("artifact_quality_targets"), dict)
        else {}
    )
    must_record = artifact_targets.get("must_record") if isinstance(artifact_targets.get("must_record"), list) else []
    if (
        artifact_targets.get("required_when_data_artifacts_active") is not True
        or "source data fingerprints" not in must_record
        or "image whitespace measurement or trim rule" not in must_record
        or "rerun and inspect commands" not in must_record
    ):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "slide_quality_artifact_targets_bad",
                "artifact_quality_targets": artifact_targets,
            }
        )
    qa_gates = (
        quality_contract.get("qa_gates")
        if isinstance(quality_contract.get("qa_gates"), dict)
        else {}
    )
    fail_on = qa_gates.get("fail_on") if isinstance(qa_gates.get("fail_on"), list) else []
    required_commands = qa_gates.get("required_commands") if isinstance(qa_gates.get("required_commands"), list) else []
    if (
        "whitespace_warnings" not in fail_on
        or "design_readability_warnings" not in fail_on
        or not any("validate_planning.py" in str(command) for command in required_commands)
        or not any("--fail-on-whitespace-warnings" in str(command) for command in required_commands)
        or not any("report_delivery_readiness.py" in str(command) for command in required_commands)
    ):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "slide_quality_qa_gates_bad",
                "qa_gates": qa_gates,
            }
        )
    proof_ledger = packet.get("phase_proof_ledger")
    if not isinstance(proof_ledger, dict) or proof_ledger.get("ledger_version") != "deck_phase_proof_ledger_v1":
        failures.append({"step": "deck_start_packet", "reason": "bad_phase_proof_ledger"})

    execution_plan = packet.get("execution_plan")
    phase_ids = [
        str(item.get("id") or "").strip()
        for item in execution_plan.get("phases", [])
        if isinstance(item, dict)
    ] if isinstance(execution_plan, dict) and isinstance(execution_plan.get("phases"), list) else []
    for phase_id in ("ask_or_assume_intake", "lock_design_contract", "source_readiness_gate", "final_delivery_audit"):
        if phase_id not in phase_ids:
            failures.append({"step": "deck_start_packet", "reason": "missing_execution_phase", "phase_id": phase_id})

    checklist = packet.get("acceptance_checklist")
    if not isinstance(checklist, list) or len(checklist) < 4:
        failures.append({"step": "deck_start_packet", "reason": "acceptance_checklist_too_short"})
    kickoff = packet.get("agent_kickoff_brief")
    if not isinstance(kickoff, dict) or kickoff.get("contract_version") != "deck_agent_kickoff_brief_v1":
        failures.append({"step": "deck_start_packet", "reason": "bad_agent_kickoff_brief"})
        kickoff = {}
    if kickoff.get("stable_prompt_id") != packet.get("recommended_style_seed"):
        failures.append({"step": "deck_start_packet", "reason": "kickoff_seed_mismatch"})
    question_trigger = kickoff.get("question_trigger") if isinstance(kickoff.get("question_trigger"), dict) else {}
    if not isinstance(question_trigger.get("auto_resolution_ms"), int):
        failures.append({"step": "deck_start_packet", "reason": "kickoff_missing_question_trigger"})
    route_snapshot = kickoff.get("route_snapshot") if isinstance(kickoff.get("route_snapshot"), dict) else {}
    kickoff_active_routes = route_snapshot.get("active_routes") if isinstance(route_snapshot.get("active_routes"), list) else []
    if "data_artifacts" not in kickoff_active_routes:
        failures.append({"step": "deck_start_packet", "reason": "kickoff_missing_data_route", "routes": kickoff_active_routes})
    kickoff_quality = (
        kickoff.get("slide_quality_contract")
        if isinstance(kickoff.get("slide_quality_contract"), dict)
        else {}
    )
    if kickoff_quality.get("contract_version") != "slide_quality_contract_v1":
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "kickoff_missing_slide_quality_contract",
                "slide_quality_contract": kickoff_quality,
            }
        )
    preset_profile = (
        kickoff.get("preset_treatment_profile")
        if isinstance(kickoff.get("preset_treatment_profile"), dict)
        else {}
    )
    profile_mix = (
        preset_profile.get("style_mix_matrix")
        if isinstance(preset_profile.get("style_mix_matrix"), dict)
        else {}
    )
    style_reference = (
        preset_profile.get("style_reference")
        if isinstance(preset_profile.get("style_reference"), dict)
        else {}
    )
    content_treatments = (
        style_reference.get("content_treatments")
        if isinstance(style_reference.get("content_treatments"), dict)
        else {}
    )
    layout_playbook = (
        style_reference.get("layout_playbook")
        if isinstance(style_reference.get("layout_playbook"), dict)
        else {}
    )
    if (
        preset_profile.get("profile_version") != "deck_preset_treatment_profiles_v1"
        or preset_profile.get("style_preset") != "lab-report"
        or "top-bottom-rule" not in profile_mix.get("header_variant_pool", [])
        or "source-line" not in profile_mix.get("footer_pool", [])
        or style_reference.get("catalog_version") != "style_reference_catalog_v1"
        or style_reference.get("source_status") != "synthetic_original_publish_safe"
        or layout_playbook.get("playbook_version") != "style_reference_layout_playbook_v1"
        or "lab-run-results" not in layout_playbook.get("preferred_variants", [])
        or not content_treatments.get("figure")
        or not content_treatments.get("table")
        or not content_treatments.get("decision")
    ):
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "kickoff_preset_treatment_profile_missing",
                "preset_profile": preset_profile,
            }
        )
    locked_fields = kickoff.get("locked_replay_fields") if isinstance(kickoff.get("locked_replay_fields"), list) else []
    for required_field in ("style_system.style_mix_matrix", "style_system.style_reference", "slide_quality_contract", "readability_contract", "analysis_artifact_plan"):
        if required_field not in locked_fields:
            failures.append({"step": "deck_start_packet", "reason": "kickoff_missing_locked_field", "field": required_field})
    command_ladder = kickoff.get("command_ladder") if isinstance(kickoff.get("command_ladder"), dict) else {}
    for group in ("intake", "design_contract", "data_artifacts", "outline_authoring", "source_readiness", "fast_first_pass", "final_delivery"):
        if not isinstance(command_ladder.get(group), list) or not command_ladder.get(group):
            failures.append({"step": "deck_start_packet", "reason": "kickoff_missing_command_group", "group": group})
    required_contracts = kickoff.get("required_contracts") if isinstance(kickoff.get("required_contracts"), list) else []
    contract_names = [
        item.get("name")
        for item in required_contracts
        if isinstance(item, dict)
    ]
    for contract_name in ("deck_design_contract_v1", "deck_reproducibility_contract_v1", "outline_authoring_handoff_v1"):
        if contract_name not in contract_names:
            failures.append({"step": "deck_start_packet", "reason": "kickoff_missing_required_contract", "contract": contract_name})
    design_contract_req = next(
        (item for item in required_contracts if isinstance(item, dict) and item.get("name") == "deck_design_contract_v1"),
        {},
    )
    design_must_include = (
        design_contract_req.get("must_include")
        if isinstance(design_contract_req.get("must_include"), list)
        else []
    )
    if "slide_quality_contract" not in design_must_include:
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "design_contract_missing_slide_quality_requirement",
                "must_include": design_must_include,
            }
        )
    artifact_obligations = (
        kickoff.get("artifact_obligations")
        if isinstance(kickoff.get("artifact_obligations"), dict)
        else {}
    )
    if artifact_obligations.get("required_when_active") is not True:
        failures.append({"step": "deck_start_packet", "reason": "kickoff_artifact_route_not_required"})
    prompt_text = str(packet.get("main_agent_kickoff_prompt") or "") + "\n" + str(packet.get("subagent_prompt") or "")
    for needle in (
        "AGENT KICKOFF BRIEF",
        "deck_agent_kickoff_brief_v1",
        "deck_reproducibility_contract_v1",
        "slide_quality_contract_v1",
        "data_artifacts",
        "atom_composition",
        "normal_workflow_atom_context_v1",
        "choice_resolution.atom_composition",
        "style_atom_composition",
        "command_ladder",
    ):
        if needle not in prompt_text:
            failures.append({"step": "deck_start_packet", "reason": "kickoff_prompt_missing", "missing": needle})
    app_contract = (
        packet.get("application_contract")
        if isinstance(packet.get("application_contract"), dict)
        else {}
    )
    app_quality = (
        app_contract.get("slide_quality_contract")
        if isinstance(app_contract.get("slide_quality_contract"), dict)
        else {}
    )
    if app_quality.get("contract_version") != "slide_quality_contract_v1":
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "application_contract_missing_slide_quality_contract",
                "slide_quality_contract": app_quality,
            }
        )
    app_atom = (
        app_contract.get("atom_workflow_context")
        if isinstance(app_contract.get("atom_workflow_context"), dict)
        else {}
    )
    if app_atom.get("schema_version") != "normal_workflow_atom_context_v1":
        failures.append(
            {
                "step": "deck_start_packet",
                "reason": "application_contract_missing_atom_context",
                "atom_workflow_context": app_atom,
            }
        )
    if len(str(packet.get("subagent_prompt") or "")) < 1000:
        failures.append({"step": "deck_start_packet", "reason": "subagent_prompt_too_short"})


def _assert_pre_intake_readiness(
    readiness: dict[str, Any],
    readiness_markdown: str,
    failures: list[dict[str, Any]],
) -> None:
    if readiness.get("status") != "needs_attention":
        failures.append(
            {
                "step": "pre_intake_readiness",
                "reason": "unexpected_status",
                "status": readiness.get("status"),
            }
        )
    deck_intake = readiness.get("deck_intake") if isinstance(readiness.get("deck_intake"), dict) else {}
    if deck_intake.get("status") != "intake_answers_missing" or deck_intake.get("applied") is not False:
        failures.append(
            {
                "step": "pre_intake_readiness",
                "reason": "intake_missing_state_not_reported",
                "deck_intake": deck_intake,
            }
        )
    next_action = readiness.get("next_action") if isinstance(readiness.get("next_action"), dict) else {}
    if next_action.get("kind") != "record_deck_intake_answers":
        failures.append(
            {
                "step": "pre_intake_readiness",
                "reason": "wrong_next_action",
                "next_action": next_action,
            }
        )
    inventory = (
        deck_intake.get("workspace_source_inventory")
        if isinstance(deck_intake.get("workspace_source_inventory"), dict)
        else {}
    )
    packet_inventory = inventory.get("packet") if isinstance(inventory.get("packet"), dict) else {}
    if packet_inventory.get("data_file_count") != 1:
        failures.append(
            {
                "step": "pre_intake_readiness",
                "reason": "packet_source_inventory_not_summarized",
                "workspace_source_inventory": inventory,
            }
        )
    for needle in (
        "Deck intake status: `intake_answers_missing`",
        "Next action: `record_deck_intake_answers`",
        "Source inventory: data=`1`",
        "Source data paths: `data/assay_results.csv`",
    ):
        if needle not in readiness_markdown:
            failures.append(
                {
                    "step": "pre_intake_readiness_markdown",
                    "reason": "missing_pre_intake_context",
                    "missing": needle,
                }
            )


def _assert_style_reference_starter_workspace(workspace: Path, failures: list[dict[str, Any]]) -> None:
    outline = _load_json(workspace / "outline.json")
    content = _load_json(workspace / "content_plan.json")
    design = _load_json(workspace / "design_brief.json")
    style_contract = _load_json(workspace / "style_contract.json")
    notes = (workspace / "notes.md").read_text(encoding="utf-8") if (workspace / "notes.md").exists() else ""

    if not isinstance(outline, dict):
        failures.append({"step": "init_deck_workspace", "reason": "outline_not_object"})
        return
    metadata = outline.get("metadata") if isinstance(outline.get("metadata"), dict) else {}
    style_meta = metadata.get("style_reference") if isinstance(metadata.get("style_reference"), dict) else {}
    outline_atom = (
        metadata.get("style_atom_context")
        if isinstance(metadata.get("style_atom_context"), dict)
        else {}
    )
    if (
        metadata.get("starter_outline_version") != "style_reference_starter_outline_v1"
        or metadata.get("starter_outline_status") != "synthetic_scaffold_replace_before_delivery"
        or style_meta.get("reference_id") != "ref-clean-assay-report"
        or style_meta.get("playbook_version") != "style_reference_layout_playbook_v1"
    ):
        failures.append(
            {
                "step": "init_deck_workspace",
                "reason": "style_reference_starter_metadata_missing",
                "metadata": metadata,
            }
        )
    if (
        outline_atom.get("schema_version") != "normal_workflow_atom_context_v1"
        or outline_atom.get("route_id") != "atom_composition"
        or not outline_atom.get("preferred_variants")
    ):
        failures.append(
            {
                "step": "init_deck_workspace",
                "reason": "outline_atom_context_missing",
                "style_atom_context": outline_atom,
            }
        )

    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    scaffold_slides = [
        slide
        for slide in slides
        if isinstance(slide, dict) and slide.get("starter_kind") == "style_reference"
    ]
    scaffold_variants = {
        str(slide.get("variant") or "").strip()
        for slide in scaffold_slides
        if str(slide.get("variant") or "").strip()
    }
    expected_variants = {"lab-run-results", "scientific-figure", "comparison-2col"}
    if len(scaffold_slides) < 3 or not expected_variants.issubset(scaffold_variants):
        failures.append(
            {
                "step": "init_deck_workspace",
                "reason": "style_reference_starter_variants_missing",
                "variants": sorted(scaffold_variants),
                "slide_count": len(scaffold_slides),
            }
        )
    if any(not slide.get("sources") or not slide.get("refs") for slide in scaffold_slides):
        failures.append(
            {
                "step": "init_deck_workspace",
                "reason": "style_reference_starter_sources_missing",
                "slides": scaffold_slides,
            }
        )

    slide_plan = content.get("slide_plan") if isinstance(content, dict) and isinstance(content.get("slide_plan"), list) else []
    plan_by_id = {
        str(item.get("slide_id") or "").strip(): item
        for item in slide_plan
        if isinstance(item, dict) and str(item.get("slide_id") or "").strip()
    }
    outline_ids = [
        str(slide.get("slide_id") or "").strip()
        for slide in slides
        if isinstance(slide, dict) and str(slide.get("slide_id") or "").strip()
    ]
    if sorted(plan_by_id) != sorted(outline_ids):
        failures.append(
            {
                "step": "content_plan",
                "reason": "starter_slide_plan_not_complete",
                "outline_ids": outline_ids,
                "plan_ids": sorted(plan_by_id),
            }
        )
    for slide in scaffold_slides:
        slide_id = str(slide.get("slide_id") or "").strip()
        plan = plan_by_id.get(slide_id, {})
        evidence_needs = plan.get("evidence_needs") if isinstance(plan.get("evidence_needs"), list) else []
        if (
            plan.get("source_status") != "synthetic_style_reference_scaffold"
            or "replace_synthetic_style_reference_content" not in evidence_needs
        ):
            failures.append(
                {
                    "step": "content_plan",
                    "reason": "style_reference_scaffold_not_flagged",
                    "slide_id": slide_id,
                    "plan": plan,
                }
            )

    style_system = design.get("style_system") if isinstance(design, dict) and isinstance(design.get("style_system"), dict) else {}
    direct_reference = (
        style_system.get("style_reference")
        if isinstance(style_system.get("style_reference"), dict)
        else {}
    )
    structure = design.get("structure_strategy") if isinstance(design, dict) and isinstance(design.get("structure_strategy"), dict) else {}
    structure_playbook = (
        structure.get("style_reference_layout_playbook")
        if isinstance(structure.get("style_reference_layout_playbook"), dict)
        else {}
    )
    design_atom = (
        style_system.get("style_atom_context")
        if isinstance(style_system.get("style_atom_context"), dict)
        else {}
    )
    atom_composition = (
        style_system.get("style_atom_composition")
        if isinstance(style_system.get("style_atom_composition"), dict)
        else {}
    )
    if (
        direct_reference.get("catalog_version") != "style_reference_catalog_v1"
        or direct_reference.get("reference_id") != "ref-clean-assay-report"
        or direct_reference.get("source_status") != "synthetic_original_publish_safe"
        or not isinstance(direct_reference.get("example_storyboard"), dict)
        or structure_playbook.get("playbook_version") != "style_reference_layout_playbook_v1"
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "style_reference_starter_design_context_missing",
                "style_reference": direct_reference,
                "structure_playbook": structure_playbook,
            }
        )
    if (
        design_atom.get("schema_version") != "normal_workflow_atom_context_v1"
        or design_atom.get("route_id") != "atom_composition"
        or not atom_composition
        or not isinstance(style_system.get("style_atom_preferred_variants"), list)
        or not style_system.get("style_atom_preferred_variants")
        or not isinstance(style_system.get("style_atom_narrative_arc"), list)
        or not style_system.get("style_atom_narrative_arc")
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "style_atom_context_missing",
                "style_atom_context": design_atom,
                "style_atom_composition": atom_composition,
            }
        )

    contract_reference = (
        style_contract.get("style_reference")
        if isinstance(style_contract, dict) and isinstance(style_contract.get("style_reference"), dict)
        else {}
    )
    contract_atom = (
        style_contract.get("style_atom_context")
        if isinstance(style_contract, dict) and isinstance(style_contract.get("style_atom_context"), dict)
        else {}
    )
    if (
        contract_reference.get("reference_id") != "ref-clean-assay-report"
        or contract_reference.get("starter_outline_version") != "style_reference_starter_outline_v1"
    ):
        failures.append(
            {
                "step": "style_contract",
                "reason": "style_reference_starter_contract_missing",
                "style_reference": contract_reference,
            }
        )
    if contract_atom.get("schema_version") != "normal_workflow_atom_context_v1":
        failures.append(
            {
                "step": "style_contract",
                "reason": "style_atom_contract_missing",
                "style_atom_context": contract_atom,
            }
        )
    if "Starter scaffold: `style_reference_starter_outline_v1`" not in notes:
        failures.append({"step": "notes", "reason": "style_reference_starter_notes_missing"})


def _assert_application_state(
    *,
    workspace: Path,
    packet: dict[str, Any],
    answers: dict[str, Any],
    apply_report: dict[str, Any],
    repeat_report: dict[str, Any],
    readiness: dict[str, Any],
    readiness_markdown: str,
    next_action_markdown: str,
    failures: list[dict[str, Any]],
) -> None:
    design = _load_json(workspace / "design_brief.json")
    content = _load_json(workspace / "content_plan.json")
    evidence = _load_json(workspace / "evidence_plan.json")
    asset = _load_json(workspace / "asset_plan.json")
    notes = (workspace / "notes.md").read_text(encoding="utf-8") if (workspace / "notes.md").exists() else ""

    expected_seed = str(packet.get("recommended_style_seed") or "").strip()
    style_system = design.get("style_system") if isinstance(design.get("style_system"), dict) else {}
    preset_profile = (
        style_system.get("preset_treatment_profile")
        if isinstance(style_system.get("preset_treatment_profile"), dict)
        else {}
    )
    direct_style_reference = (
        style_system.get("style_reference")
        if isinstance(style_system.get("style_reference"), dict)
        else {}
    )
    user_intake = design.get("user_intake") if isinstance(design.get("user_intake"), dict) else {}
    choice_seed = (
        design.get("choice_resolution_seed")
        if isinstance(design.get("choice_resolution_seed"), dict)
        else {}
    )
    style_atom_context = (
        style_system.get("style_atom_context")
        if isinstance(style_system.get("style_atom_context"), dict)
        else {}
    )
    style_atom_composition = (
        style_system.get("style_atom_composition")
        if isinstance(style_system.get("style_atom_composition"), dict)
        else {}
    )

    if apply_report.get("workflow") != "deck_intake_answers_apply_v1":
        failures.append({"step": "apply_deck_intake_answers", "reason": "wrong_workflow"})
    if apply_report.get("changed_file_count", 0) < 4:
        failures.append(
            {
                "step": "apply_deck_intake_answers",
                "reason": "too_few_changed_files",
                "changed_file_count": apply_report.get("changed_file_count"),
            }
        )
    if repeat_report.get("changed_file_count") != 0:
        failures.append(
            {
                "step": "apply_deck_intake_answers_repeat",
                "reason": "not_idempotent",
                "changed_file_count": repeat_report.get("changed_file_count"),
            }
        )
    if style_system.get("style_seed") != expected_seed:
        failures.append(
            {
                "step": "design_brief",
                "reason": "style_seed_not_applied",
                "expected": expected_seed,
                "actual": style_system.get("style_seed"),
            }
        )
    if (
        preset_profile.get("profile_version") != "deck_preset_treatment_profiles_v1"
        or preset_profile.get("style_preset") != "lab-report"
        or not isinstance(preset_profile.get("style_reference"), dict)
        or preset_profile["style_reference"].get("catalog_version") != "style_reference_catalog_v1"
        or not isinstance(preset_profile["style_reference"].get("layout_playbook"), dict)
        or preset_profile["style_reference"]["layout_playbook"].get("playbook_version") != "style_reference_layout_playbook_v1"
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "preset_treatment_profile_not_preserved",
                "preset_treatment_profile": preset_profile,
            }
        )
    if (
        direct_style_reference.get("catalog_version") != "style_reference_catalog_v1"
        or direct_style_reference.get("reference_id") != "ref-clean-assay-report"
        or not isinstance(direct_style_reference.get("layout_playbook"), dict)
        or direct_style_reference["layout_playbook"].get("playbook_version") != "style_reference_layout_playbook_v1"
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "direct_style_reference_not_preserved",
                "style_reference": direct_style_reference,
            }
        )
    if user_intake.get("answered_by") != "best_judgment":
        failures.append({"step": "design_brief", "reason": "answered_by_not_preserved", "value": user_intake.get("answered_by")})
    if user_intake.get("stable_prompt_id") != expected_seed:
        failures.append({"step": "design_brief", "reason": "stable_prompt_id_not_preserved"})

    codex_answers = user_intake.get("codex_ui_answers")
    answer_count = len(answers.get("answers", [])) if isinstance(answers.get("answers"), list) else 0
    expected_ui_answer_ids = [
        item.get("id")
        for item in answers.get("answers", [])
        if isinstance(item, dict) and item.get("id") in {"style_density", "visual_source_policy"}
    ] if isinstance(answers.get("answers"), list) else []
    if not isinstance(codex_answers, dict) or sorted(codex_answers.keys()) != sorted(expected_ui_answer_ids):
        failures.append(
            {
                "step": "design_brief",
                "reason": "codex_answers_not_persisted",
                "answer_count": answer_count,
                "codex_answers": codex_answers,
            }
        )
    if choice_seed.get("contract_version") != "deck_choice_resolution_v1":
        failures.append({"step": "design_brief", "reason": "choice_resolution_seed_missing"})
    if choice_seed.get("stable_prompt_id") != expected_seed:
        failures.append({"step": "design_brief", "reason": "choice_resolution_seed_wrong_seed"})
    atom_seed = (
        choice_seed.get("atom_composition")
        if isinstance(choice_seed.get("atom_composition"), dict)
        else {}
    )
    if (
        atom_seed.get("route_id") != "atom_composition"
        or not isinstance(atom_seed.get("style_atom_composition"), dict)
        or not atom_seed.get("style_atom_composition")
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "choice_resolution_seed_missing_atom_composition",
                "atom_composition": atom_seed,
            }
        )
    if (
        style_atom_context.get("schema_version") != "normal_workflow_atom_context_v1"
        or style_atom_context.get("route_id") != "atom_composition"
        or not style_atom_composition
        or not isinstance(style_system.get("style_atom_preferred_variants"), list)
        or not style_system.get("style_atom_preferred_variants")
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "style_atom_context_not_preserved_after_intake",
                "style_atom_context": style_atom_context,
                "style_atom_composition": style_atom_composition,
            }
        )
    seed_inventory = (
        choice_seed.get("workspace_source_inventory")
        if isinstance(choice_seed.get("workspace_source_inventory"), dict)
        else {}
    )
    if seed_inventory.get("data_file_count", 0) < 1:
        failures.append(
            {
                "step": "design_brief",
                "reason": "choice_resolution_seed_missing_source_inventory",
                "source_inventory": seed_inventory,
            }
        )

    packet_active_routes = _active_route_ids(packet.get("route_decision_ledger", {}))
    seed_active_routes = choice_seed.get("route_ledger_active_routes")
    if sorted(seed_active_routes or []) != packet_active_routes:
        failures.append(
            {
                "step": "design_brief",
                "reason": "active_routes_not_copied",
                "expected": packet_active_routes,
                "actual": seed_active_routes,
            }
        )

    renderer = design.get("renderer_treatments") if isinstance(design.get("renderer_treatments"), dict) else {}
    if renderer.get("header_mode") != "lab-clean" or renderer.get("header_variant") != "auto":
        failures.append({"step": "design_brief", "reason": "lab_renderer_treatments_not_derived", "renderer": renderer})
    if evidence.get("source_policy") != "cite key claims":
        failures.append({"step": "evidence_plan", "reason": "source_policy_not_applied", "value": evidence.get("source_policy")})

    asset_posture = asset.get("asset_posture") if isinstance(asset.get("asset_posture"), dict) else {}
    expected_assets = "use local/generated figures when data exists; otherwise use source-backed visuals selectively"
    if asset_posture.get("evidence_assets") != expected_assets:
        failures.append({"step": "asset_plan", "reason": "asset_posture_not_derived", "asset_posture": asset_posture})
    answered_ids = {
        item.get("id")
        for item in answers.get("answers", [])
        if isinstance(item, dict)
    } if isinstance(answers.get("answers"), list) else set()
    if "audience_context" in answered_ids and content.get("audience") != ANSWER_FIXTURES["audience_context"]:
        failures.append({"step": "content_plan", "reason": "audience_not_applied", "value": content.get("audience")})
    if (
        "<!-- deck-intake-answers:start -->" not in notes
        or "Stable style seed" not in notes
        or "Source inventory: data_files=1" not in notes
    ):
        failures.append({"step": "notes", "reason": "intake_notes_section_missing"})

    deck_intake = readiness.get("deck_intake") if isinstance(readiness.get("deck_intake"), dict) else {}
    if deck_intake.get("status") != "applied" or deck_intake.get("applied") is not True:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "deck_intake_not_applied",
                "status": deck_intake.get("status"),
                "applied": deck_intake.get("applied"),
            }
        )
    if deck_intake.get("answer_count") != answer_count:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "answer_count_mismatch",
                "expected": answer_count,
                "actual": deck_intake.get("answer_count"),
            }
        )
    if deck_intake.get("stable_prompt_id") != expected_seed:
        failures.append({"step": "workspace_readiness", "reason": "readiness_seed_mismatch"})

    readiness_choice_seed = deck_intake.get("choice_resolution_seed")
    if not isinstance(readiness_choice_seed, dict) or readiness_choice_seed.get("choice_count", 0) < answer_count:
        failures.append({"step": "workspace_readiness", "reason": "choice_seed_not_summarized"})
    readiness_inventory = (
        deck_intake.get("workspace_source_inventory")
        if isinstance(deck_intake.get("workspace_source_inventory"), dict)
        else {}
    )
    packet_inventory = readiness_inventory.get("packet") if isinstance(readiness_inventory.get("packet"), dict) else {}
    seed_readiness_inventory = (
        readiness_inventory.get("choice_resolution_seed")
        if isinstance(readiness_inventory.get("choice_resolution_seed"), dict)
        else {}
    )
    if packet_inventory.get("data_file_count") != 1 or seed_readiness_inventory.get("data_file_count") != 1:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "source_inventory_not_summarized",
                "workspace_source_inventory": readiness_inventory,
            }
        )
    for label, text in (
        ("workspace_readiness_markdown", readiness_markdown),
        ("workspace_next_action_markdown", next_action_markdown),
    ):
        for needle in (
            "Source inventory: data=`1`",
            "Source data paths: `data/assay_results.csv`",
        ):
            if needle not in text:
                failures.append(
                    {
                        "step": label,
                        "reason": "source_inventory_missing_from_markdown",
                        "missing": needle,
                    }
                )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a focused deck-start and intake-answer smoke check."
    )
    parser.add_argument(
        "--workspace",
        default="",
        help="Workspace to create/use. Defaults to a temporary workspace.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the temporary workspace after a passing run.",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-deck-start-"))
    )
    if workspace.exists() and any(workspace.iterdir()):
        print(
            json.dumps(
                {
                    "passed": False,
                    "workspace": str(workspace),
                    "failures": [{"step": "workspace", "reason": "workspace_must_be_empty"}],
                },
                indent=2,
            )
        )
        return 1
    workspace.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    failures: list[dict[str, Any]] = []
    command_results: list[dict[str, Any]] = []
    build_dir = workspace / "build"
    passed = False

    try:
        data_dir = workspace / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "assay_results.csv").write_text(
            "sample,signal,ct\n"
            "A,0.91,23.1\n"
            "B,0.74,27.4\n"
            "C,0.62,31.2\n",
            encoding="utf-8",
        )
        packet_path = workspace / "deck_start_packet.json"
        init_cmd = [
            py,
            str(repo / "scripts" / "init_deck_workspace.py"),
            "--workspace",
            str(workspace),
            "--title",
            "Deck Start Intake Smoke",
            "--style-preset",
            "lab-report",
            "--overwrite",
            "--user-prompt",
            USER_PROMPT,
            "--start-packet",
            str(packet_path),
        ]
        _run_checked(init_cmd, cwd=repo, command_results=command_results, failures=failures)
        if failures:
            raise RuntimeError("workspace initialization failed")

        build_dir.mkdir(parents=True, exist_ok=True)
        answers_path = workspace / "intake_answers.json"
        apply_report_path = workspace / "intake_apply_report.json"
        repeat_report_path = build_dir / "intake_apply_report_repeat.json"
        pre_intake_readiness_report_path = build_dir / "deck_start_pre_intake_readiness.json"
        pre_intake_readiness_markdown_path = build_dir / "deck_start_pre_intake_readiness.md"
        readiness_report_path = build_dir / "deck_start_intake_readiness.json"
        readiness_markdown_path = build_dir / "workspace_readiness.md"
        advance_report_path = build_dir / "deck_start_intake_advance.json"
        next_action_path = build_dir / "deck_start_intake_next_action.md"

        packet = _load_json(packet_path)
        if not isinstance(packet, dict):
            failures.append({"step": "deck_start_packet", "reason": "packet_not_object"})
            packet = {}
        _assert_required_packet(packet, failures)
        manifest = _load_json(workspace / "workspace.json")
        if not isinstance(manifest, dict) or manifest.get("deck_start_packet") != "deck_start_packet.json":
            failures.append(
                {
                    "step": "init_deck_workspace",
                    "reason": "workspace_manifest_missing_start_packet",
                    "workspace_manifest": manifest,
                }
            )
        init_stdout = command_results[0].get("stdout_tail", "") if command_results else ""
        if "Deck start packet:" not in init_stdout:
            failures.append(
                {
                    "step": "init_deck_workspace",
                    "reason": "init_stdout_missing_start_packet",
                    "stdout_tail": init_stdout,
                }
            )
        _assert_style_reference_starter_workspace(workspace, failures)
        pre_intake_readiness_cmd = [
            py,
            str(repo / "scripts" / "report_workspace_readiness.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(pre_intake_readiness_report_path),
            "--markdown-report",
            str(pre_intake_readiness_markdown_path),
        ]
        _run_checked(
            pre_intake_readiness_cmd,
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )
        pre_intake_readiness = _load_json(pre_intake_readiness_report_path)
        pre_intake_markdown = (
            pre_intake_readiness_markdown_path.read_text(encoding="utf-8")
            if pre_intake_readiness_markdown_path.exists()
            else ""
        )
        _assert_pre_intake_readiness(
            pre_intake_readiness if isinstance(pre_intake_readiness, dict) else {},
            pre_intake_markdown,
            failures,
        )
        answers = _build_answers(packet)
        _write_json(answers_path, answers)

        apply_cmd = [
            py,
            str(repo / "scripts" / "apply_deck_intake_answers.py"),
            "--workspace",
            str(workspace),
            "--packet",
            str(packet_path),
            "--answers",
            str(answers_path),
            "--answered-by",
            "best_judgment",
            "--report",
            str(apply_report_path),
        ]
        repeat_apply_cmd = [
            py,
            str(repo / "scripts" / "apply_deck_intake_answers.py"),
            "--workspace",
            str(workspace),
            "--packet",
            str(packet_path),
            "--answers",
            str(answers_path),
            "--answered-by",
            "best_judgment",
            "--report",
            str(repeat_report_path),
        ]
        readiness_cmd = [
            py,
            str(repo / "scripts" / "report_workspace_readiness.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(readiness_report_path),
        ]
        advance_cmd = [
            py,
            str(repo / "scripts" / "advance_workspace.py"),
            "--workspace",
            str(workspace),
            "--report",
            str(advance_report_path),
            "--next-action-markdown",
            str(next_action_path),
        ]
        for cmd in (apply_cmd, repeat_apply_cmd):
            _run_checked(cmd, cwd=repo, command_results=command_results, failures=failures)
        _run_checked(
            readiness_cmd,
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )
        _run_checked(
            advance_cmd,
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )

        apply_report = _load_json(apply_report_path)
        repeat_report = _load_json(repeat_report_path)
        readiness = _load_json(readiness_report_path)
        readiness_markdown = (
            readiness_markdown_path.read_text(encoding="utf-8")
            if readiness_markdown_path.exists()
            else ""
        )
        next_action_markdown = (
            next_action_path.read_text(encoding="utf-8")
            if next_action_path.exists()
            else ""
        )
        _assert_application_state(
            workspace=workspace,
            packet=packet,
            answers=answers,
            apply_report=apply_report if isinstance(apply_report, dict) else {},
            repeat_report=repeat_report if isinstance(repeat_report, dict) else {},
            readiness=readiness if isinstance(readiness, dict) else {},
            readiness_markdown=readiness_markdown,
            next_action_markdown=next_action_markdown,
            failures=failures,
        )

        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "packet_keys": sorted(packet.keys()),
            "question_ids": _packet_question_ids(packet),
            "recommended_style_seed": packet.get("recommended_style_seed"),
            "active_routes": _active_route_ids(packet.get("route_decision_ledger", {})),
            "pre_intake_status": (
                pre_intake_readiness.get("status")
                if isinstance(pre_intake_readiness, dict)
                else None
            ),
            "pre_intake_next_action": (
                pre_intake_readiness.get("next_action", {}).get("kind")
                if isinstance(pre_intake_readiness, dict)
                and isinstance(pre_intake_readiness.get("next_action"), dict)
                else None
            ),
            "apply_changed_file_count": apply_report.get("changed_file_count") if isinstance(apply_report, dict) else None,
            "repeat_changed_file_count": repeat_report.get("changed_file_count") if isinstance(repeat_report, dict) else None,
            "readiness_status": readiness.get("status") if isinstance(readiness, dict) else None,
            "deck_intake_status": (
                readiness.get("deck_intake", {}).get("status")
                if isinstance(readiness, dict) and isinstance(readiness.get("deck_intake"), dict)
                else None
            ),
            "failures": failures,
            "commands": command_results,
        }
        summary_path = build_dir / "deck_start_intake_smoke.json"
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "question_ids",
                        "recommended_style_seed",
                        "active_routes",
                        "pre_intake_status",
                        "pre_intake_next_action",
                        "apply_changed_file_count",
                        "repeat_changed_file_count",
                        "readiness_status",
                        "deck_intake_status",
                        "failures",
                    )
                },
                indent=2,
            )
        )
        _cleanup_workspace(workspace, created_temp=created_temp, keep=args.keep_workspace, passed=passed)
        return 0 if passed else 1
    except Exception as exc:
        failures.append({"step": "smoke", "reason": str(exc)})
        summary = {
            "passed": False,
            "workspace": str(workspace),
            "failures": failures,
            "commands": command_results,
        }
        try:
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "deck_start_intake_smoke.json").write_text(
                json.dumps(summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        print(json.dumps(summary, indent=2))
        return 1
    finally:
        _cleanup_workspace(workspace, created_temp=created_temp, keep=args.keep_workspace, passed=passed)


if __name__ == "__main__":
    raise SystemExit(main())
