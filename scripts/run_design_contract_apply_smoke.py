#!/usr/bin/env python3
"""Fast smoke check for design-contract prompt and deterministic application."""

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
    "style_density": "Lab-report/figure-first with dense report pages.",
    "visual_source_policy": (
        "Use local data, generated charts, compact source footers, page numbers, "
        "and final references."
    ),
    "audience_context": "PI and translational assay team; dense leave-behind review.",
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


def _write_source_data_fixture(workspace: Path) -> Path:
    path = workspace / "data" / "assay_readouts.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "sample,ct,rfu,state",
                "positive_control,21.4,42.1,pass",
                "limit_check,34.2,12.0,review",
                "ntc,0.0,0.2,pass",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _cleanup_workspace(workspace: Path, *, created_temp: bool, keep: bool, passed: bool) -> None:
    if created_temp and not keep and passed:
        shutil.rmtree(workspace, ignore_errors=True)


def _packet_question_ids(packet: dict[str, Any]) -> list[str]:
    request = packet.get("request_user_input")
    questions = request.get("questions") if isinstance(request, dict) else []
    if not isinstance(questions, list):
        return []
    return [
        str(item.get("id") or "").strip()
        for item in questions
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]


def _answers_for(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "answers": [
            {
                "id": question_id,
                "answer": ANSWER_FIXTURES.get(
                    question_id,
                    "Use best judgment and keep choices reproducible.",
                ),
            }
            for question_id in _packet_question_ids(packet)
        ],
        "answered_by": "best_judgment",
    }


def _analysis_artifact_plan() -> dict[str, Any]:
    return {
        "candidate_data_files": [],
        "spreadsheet_inputs": [],
        "required_scripts": [],
        "figure_scripts": [],
        "chart_json_outputs": [],
        "table_outputs": [],
        "rebuild_commands": [],
        "artifact_registry": [],
    }


def _contract_fixture(
    *,
    seed: str,
    slide_quality_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "contract_version": "deck_design_contract_v1",
        "stable_prompt_id": seed,
        "user_request_summary": "A clean reproducible lab report deck for assay readouts.",
        "missing_inputs": [],
        "assumptions": [
            "Use best-judgment lab-report defaults until the user supplies final assay files."
        ],
        "choice_resolution": {
            "seed_kind": "scout_refined",
        },
        "reproducibility_contract": {
            "contract_version": "deck_reproducibility_contract_v1",
            "stable_prompt_id": seed,
            "style_seed": seed,
            "choice_source": "best-judgment smoke answers",
            "renderer": "pptxgenjs",
            "locked_design_fields": [
                "style_system.style_preset",
                "style_system.background_system",
                "style_system.style_mix_matrix",
                "slide_quality_contract",
                "structure_blueprint.slide_sequence",
                "readability_contract",
                "qa_contract",
            ],
            "replay_inputs": {
                "deck_start_packet": "deck_start_packet.json",
                "intake_answers": "intake_answers.json",
                "design_contract": "design_contract.json",
                "artifact_manifest": "assets/artifacts_manifest.json",
                "analysis_summary": "assets/analysis_summary.json",
            },
            "style_replay": {
                "style_preset": "lab-report",
                "palette_key": "preset-default",
                "background_system": "white report",
                "header_variant_pool": ["split-rule", "top-bottom-rule", "plain"],
                "footer_pool": ["source-line", "standard"],
                "chart_treatment_pool": ["minimal", "facts-right"],
                "figure_table_treatment_pool": ["figure-first", "image-sidebar"],
                "mix_rule": "Rotate only small lab chrome choices from the stable seed.",
                "variation_boundaries": [
                    "Headers and footer treatment may rotate.",
                    "Evidence layout, source policy, and readability thresholds stay locked.",
                ],
            },
            "structure_replay": {
                "target_slide_count": 2,
                "slide_variant_mix": ["title", "split"],
                "evidence_anchor_rule": "Evidence slides need a visible figure, chart, table, or structured comparison.",
                "white_space_rule": "Use split/image-sidebar/table variants rather than leaving empty report regions.",
            },
            "artifact_replay": {
                "local_data_needed": False,
                "artifact_manifest": "assets/artifacts_manifest.json",
                "analysis_summary": "assets/analysis_summary.json",
                "figure_script": "assets/make_figures.py",
                "rebuild_commands": [],
            },
            "replay_commands": [
                "python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json",
                "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
                "python3 scripts/report_delivery_readiness.py --workspace <deck>",
            ],
            "acceptance_evidence": [
                "design_contract_apply_report.json",
                "build/workspace_readiness.json",
                "build/build_workspace_report.json",
                "build/delivery_readiness.json",
            ],
        },
        "slide_quality_contract": slide_quality_contract
        or {
            "contract_version": "slide_quality_contract_v1",
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
                "source_footer_rule": (
                    "Use compact source/ref IDs in source-line footers; move long "
                    "references to editable References table slides."
                ),
            },
            "artifact_quality_targets": {
                "required_when_data_artifacts_active": True,
                "must_record": [
                    "source data fingerprints",
                    "producer script fingerprints",
                    "figure/chart/table output paths",
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
                ],
                "required_commands": [
                    "python3 scripts/validate_planning.py --workspace <deck>",
                    (
                        "python3 scripts/build_workspace.py --workspace <deck> --qa "
                        "--skip-render --fail-on-planning-warnings "
                        "--fail-on-whitespace-warnings --overwrite"
                    ),
                    (
                        "python3 scripts/build_workspace.py --workspace <deck> --qa "
                        "--fail-on-planning-warnings --fail-on-whitespace-warnings "
                        "--overwrite"
                    ),
                    "python3 scripts/report_delivery_readiness.py --workspace <deck>",
                ],
            },
        },
        "deck_identity": {
            "working_title": "Design Contract Smoke",
            "audience": "scientific peer reviewers",
            "use_context": "leave-behind report",
            "target_outcome": "Lock a reproducible lab report structure before outline authoring.",
            "density": "high",
        },
        "design_dna": "lab results dashboard",
        "style_system": {
            "style_preset": "lab-report",
            "palette_key": "preset-default",
            "font_pair": "system_clean_v1",
            "style_seed": seed,
            "background_system": "white report",
            "header_system": {
                "header_mode": "lab-clean",
                "header_variant": "auto",
                "header_variants": ["split-rule", "top-bottom-rule", "plain"],
                "header_rule_color": "accent_primary",
            },
            "footer_system": {
                "footer_mode": "source-line",
                "footer_page_numbers": True,
                "footer_source_label": "Sources",
                "footer_refs_label": "Refs",
            },
            "title_slide_system": {
                "title_layout": "lab-plate",
                "title_motif": "none",
                "cover_chips_or_tags": ["Assay", "Evidence"],
            },
            "section_system": {
                "section_motif": "plain",
                "section_count": 0,
            },
            "figure_table_system": {
                "figure_table_treatment": "figure-first",
            },
            "chart_system": {
                "chart_treatment": "minimal",
            },
            "style_mix_matrix": {
                "header_variant_pool": ["split-rule", "top-bottom-rule", "plain"],
                "title_layout_pool": ["lab-plate", "light-atlas"],
                "chart_treatment_pool": ["minimal", "facts-right"],
                "summary_callout_mode_pool": ["lab-box", "default"],
                "figure_table_treatment_pool": ["figure-first", "image-sidebar"],
                "footer_pool": ["source-line", "standard"],
                "mix_rule": (
                    "Rotate small lab-report treatments from the stable seed without "
                    "changing the evidence layout."
                ),
                "do_not_mix": [
                    "Do not use decorative cards for assay evidence.",
                ],
            },
        },
        "structure_blueprint": {
            "target_slide_count": 2,
            "slide_sequence": [
                {
                    "slide_id": "s1",
                    "role": "title",
                    "variant": "title",
                    "visual_strategy": "title opener",
                    "required_assets": [],
                    "source_policy": "none",
                },
                {
                    "slide_id": "s2",
                    "role": "evidence",
                    "variant": "split",
                    "visual_strategy": "figure/table-ready split with compact readout",
                    "required_assets": [],
                    "source_policy": "cite key claim",
                },
            ],
            "allowed_variants": ["title", "split", "image-sidebar", "lab-run-results", "table"],
            "forbidden_variants": ["generic four-card grid"],
        },
        "evidence_and_assets": {
            "source_policy": "cite key claims",
            "proof_burden": "technical validation",
            "research_needed": False,
            "local_data_needed": False,
            "analysis_artifact_plan": _analysis_artifact_plan(),
            "asset_plan": {
                "images": [],
                "charts": [],
                "tables": [],
                "icons": [],
                "backgrounds": [],
                "generated_images": [],
            },
        },
        "continuity_rules": {
            "recurring_tags": ["Assay", "Evidence"],
            "carry_forward_rule": "Use tags only as compact headers or footers on evidence slides.",
            "source_footer_rule": "Compact source IDs in footer; long references move to final refs slide.",
        },
        "readability_contract": {
            "min_title_pt": 26,
            "min_body_pt": 15,
            "min_caption_pt": 8,
            "max_title_lines": 2,
            "max_slide_text_lines": 8,
            "max_slide_words": 105,
            "max_slide_chars": 700,
            "footer_reserved_inches": 0.34,
            "chart_label_min_pt": 8,
            "table_density_rule": "Split or summarize dense tables.",
            "whitespace_rule": "Avoid awkward empty regions.",
            "figure_crop_rule": "Trim exterior whitespace before insertion.",
        },
        "speed_contract": {
            "renderer": "pptxgenjs by default; Python fallback only for legacy renderer-specific behavior",
            "first_pass": "render-free schema/preflight/geometry QA before slide rendering",
            "render_policy": "render only after source files are stable or visual judgment matters",
            "asset_policy": "reuse local/generated artifacts before network assets",
            "conversion_hint": "use persistent LibreOffice/unoserver when available",
        },
        "subagent_handoff": {
            "ask_user_first": True,
            "question_packet": "scripts/emit_deck_start_packet.py",
            "design_contract_scout": "strict JSON contract",
            "data_analysis_scout": "scripts/emit_data_analysis_prompt.py when data exists",
        },
        "agent_execution_plan": {
            "phases": [
                {
                    "id": "intake",
                    "owner": "main_agent",
                    "trigger": "question card",
                    "commands": [
                        "python3 scripts/apply_deck_intake_answers.py --workspace <deck> --answers <deck>/intake_answers.json"
                    ],
                    "writes": ["design_brief.json:user_intake"],
                    "continue_when": "intake_apply_report.json exists",
                },
                {
                    "id": "design_contract",
                    "owner": "main_agent",
                    "trigger": "before outline authoring",
                    "commands": [
                        "python3 scripts/apply_design_contract.py --workspace <deck> --contract <deck>/design_contract.json --report <deck>/design_contract_apply_report.json"
                    ],
                    "writes": [
                        "design_brief.json",
                        "content_plan.json",
                        "evidence_plan.json",
                        "asset_plan.json",
                        "notes.md",
                    ],
                    "continue_when": "design_contract_apply_report.json records applied",
                },
            ],
            "commands": [
                "python3 scripts/validate_planning.py --workspace <deck>",
                "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
                "python3 scripts/report_delivery_readiness.py --workspace <deck>",
            ],
        },
        "qa_contract": {
            "required_checks": [
                "python3 scripts/validate_planning.py --workspace <deck>",
                "python3 scripts/build_workspace.py --workspace <deck> --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite",
                "python3 scripts/report_delivery_readiness.py --workspace <deck>",
            ],
            "fail_on": ["planning errors", "overflow", "overlap", "awkward whitespace", "undersized text"],
            "visual_risks_to_check": ["footer/source overlap", "blank report regions"],
            "placeholder_checks": True,
            "acceptance_evidence": [
                "build/workspace_readiness.json",
                "build/build_workspace_report.json",
                "build/delivery_readiness.json",
            ],
        },
        "acceptance_evidence": [
            "design_contract_apply_report.json proves the returned contract was applied",
            "build/workspace_readiness.json proves source readiness",
        ],
        "authoring_instructions": [
            "Keep stable seed and source footer policy explicit.",
        ],
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


def _assert_contract_state(
    *,
    workspace: Path,
    packet: dict[str, Any],
    apply_report: dict[str, Any],
    repeat_report: dict[str, Any],
    planning: dict[str, Any],
    readiness: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    design = _load_json(workspace / "design_brief.json")
    content = _load_json(workspace / "content_plan.json")
    evidence = _load_json(workspace / "evidence_plan.json")
    notes = (workspace / "notes.md").read_text(encoding="utf-8") if (workspace / "notes.md").exists() else ""

    expected_seed = str(packet.get("recommended_style_seed") or "").strip()
    changed_files = apply_report.get("changed_files") if isinstance(apply_report.get("changed_files"), list) else []
    repeat_changed_files = repeat_report.get("changed_files") if isinstance(repeat_report.get("changed_files"), list) else []

    if apply_report.get("workflow") != "deck_design_contract_apply_v1":
        failures.append({"step": "apply_design_contract", "reason": "wrong_workflow"})
    if len(changed_files) < 4:
        failures.append({"step": "apply_design_contract", "reason": "too_few_changed_files", "changed_files": changed_files})
    if repeat_changed_files:
        failures.append({"step": "apply_design_contract_repeat", "reason": "not_idempotent", "changed_files": repeat_changed_files})
    for flag in (
        "qa_contract_applied",
        "subagent_handoff_applied",
        "agent_execution_plan_applied",
        "choice_resolution_applied",
        "choice_resolution_enriched_from_seed",
        "choice_resolution_route_ledger_applied",
        "reproducibility_contract_applied",
        "slide_quality_contract_applied",
    ):
        if apply_report.get(flag) is not True:
            failures.append({"step": "apply_design_contract", "reason": f"{flag}_not_true", "value": apply_report.get(flag)})
    if apply_report.get("slide_quality_contract_version") != "slide_quality_contract_v1":
        failures.append(
            {
                "step": "apply_design_contract",
                "reason": "slide_quality_contract_version_mismatch",
                "value": apply_report.get("slide_quality_contract_version"),
            }
        )
    if apply_report.get("acceptance_evidence_count", 0) < 3:
        failures.append({"step": "apply_design_contract", "reason": "acceptance_evidence_not_applied"})

    style_system = design.get("style_system") if isinstance(design.get("style_system"), dict) else {}
    preset_profile = (
        style_system.get("preset_treatment_profile")
        if isinstance(style_system.get("preset_treatment_profile"), dict)
        else {}
    )
    if style_system.get("style_seed") != expected_seed:
        failures.append({"step": "design_brief", "reason": "style_seed_not_applied", "value": style_system.get("style_seed")})
    if style_system.get("style_preset") != "lab-report":
        failures.append({"step": "design_brief", "reason": "style_preset_not_applied", "value": style_system.get("style_preset")})
    if (
        preset_profile.get("profile_version") != "deck_preset_treatment_profiles_v1"
        or preset_profile.get("style_preset") != "lab-report"
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "preset_treatment_profile_not_applied",
                "preset_treatment_profile": preset_profile,
            }
        )

    design_contract = design.get("design_contract") if isinstance(design.get("design_contract"), dict) else {}
    choice_resolution = (
        design_contract.get("choice_resolution")
        if isinstance(design_contract.get("choice_resolution"), dict)
        else {}
    )
    if design_contract.get("stable_prompt_id") != expected_seed:
        failures.append({"step": "design_brief", "reason": "design_contract_seed_mismatch"})
    if choice_resolution.get("stable_prompt_id") != expected_seed:
        failures.append({"step": "design_brief", "reason": "choice_resolution_not_enriched"})
    if sorted(choice_resolution.get("route_ledger_active_routes", [])) != _active_route_ids(packet.get("route_decision_ledger", {})):
        failures.append(
            {
                "step": "design_brief",
                "reason": "route_ledger_not_enriched",
                "expected": _active_route_ids(packet.get("route_decision_ledger", {})),
                "actual": choice_resolution.get("route_ledger_active_routes"),
            }
        )
    replay = design.get("reproducibility_contract") if isinstance(design.get("reproducibility_contract"), dict) else {}
    replay_style = replay.get("style_replay") if isinstance(replay.get("style_replay"), dict) else {}
    replay_structure = replay.get("structure_replay") if isinstance(replay.get("structure_replay"), dict) else {}
    replay_artifact = replay.get("artifact_replay") if isinstance(replay.get("artifact_replay"), dict) else {}
    if replay.get("contract_version") != "deck_reproducibility_contract_v1":
        failures.append({"step": "design_brief", "reason": "replay_contract_missing", "replay": replay})
    if replay.get("style_seed") != expected_seed or replay.get("renderer") != "pptxgenjs":
        failures.append({"step": "design_brief", "reason": "replay_contract_seed_or_renderer_mismatch", "replay": replay})
    if replay_style.get("background_system") != "white report":
        failures.append({"step": "design_brief", "reason": "replay_background_not_persisted", "style_replay": replay_style})
    if replay_style.get("header_variant_pool") != ["split-rule", "top-bottom-rule", "plain"]:
        failures.append({"step": "design_brief", "reason": "replay_header_pool_not_persisted", "style_replay": replay_style})
    if replay_style.get("chart_treatment_pool") != ["minimal", "facts-right"]:
        failures.append({"step": "design_brief", "reason": "replay_chart_pool_not_persisted", "style_replay": replay_style})
    if replay_structure.get("slide_variant_mix") != ["title", "split"]:
        failures.append({"step": "design_brief", "reason": "replay_structure_not_persisted", "structure_replay": replay_structure})
    if replay_artifact.get("analysis_summary") != "assets/analysis_summary.json":
        failures.append({"step": "design_brief", "reason": "replay_artifact_summary_missing", "artifact_replay": replay_artifact})

    renderer = design.get("renderer_treatments") if isinstance(design.get("renderer_treatments"), dict) else {}
    if renderer.get("header_mode") != "lab-clean" or renderer.get("footer_mode") != "source-line":
        failures.append({"step": "design_brief", "reason": "renderer_treatments_not_mapped", "renderer": renderer})
    if not isinstance(design.get("analysis_artifact_plan"), dict):
        failures.append({"step": "design_brief", "reason": "analysis_artifact_plan_missing"})
    if not isinstance(design.get("readability_contract"), dict) or not isinstance(design.get("speed_contract"), dict):
        failures.append({"step": "design_brief", "reason": "contracts_not_persisted"})
    slide_quality = (
        design.get("slide_quality_contract")
        if isinstance(design.get("slide_quality_contract"), dict)
        else {}
    )
    quality_readability = (
        slide_quality.get("readability_targets")
        if isinstance(slide_quality.get("readability_targets"), dict)
        else {}
    )
    quality_layout = (
        slide_quality.get("layout_targets")
        if isinstance(slide_quality.get("layout_targets"), dict)
        else {}
    )
    quality_artifacts = (
        slide_quality.get("artifact_quality_targets")
        if isinstance(slide_quality.get("artifact_quality_targets"), dict)
        else {}
    )
    quality_qa = (
        slide_quality.get("qa_gates")
        if isinstance(slide_quality.get("qa_gates"), dict)
        else {}
    )
    quality_must_record = (
        quality_artifacts.get("must_record")
        if isinstance(quality_artifacts.get("must_record"), list)
        else []
    )
    quality_fail_on = quality_qa.get("fail_on") if isinstance(quality_qa.get("fail_on"), list) else []
    quality_commands = (
        quality_qa.get("required_commands")
        if isinstance(quality_qa.get("required_commands"), list)
        else []
    )
    if slide_quality.get("contract_version") != "slide_quality_contract_v1":
        failures.append({"step": "design_brief", "reason": "slide_quality_contract_not_persisted", "slide_quality": slide_quality})
    expected_readability = {
        "min_title_pt": 24,
        "min_body_pt": 12,
        "min_caption_pt": 7.5,
        "chart_label_min_pt": 7,
        "footer_reserved_inches": 0.25,
        "max_title_lines": 2,
        "max_slide_text_lines": 12,
        "max_slide_words": 110,
        "max_slide_chars": 780,
    }
    for key, expected_value in expected_readability.items():
        if quality_readability.get(key) != expected_value:
            failures.append(
                {
                    "step": "design_brief",
                    "reason": "slide_quality_readability_mismatch",
                    "key": key,
                    "expected": expected_value,
                    "actual": quality_readability.get(key),
                }
            )
    if (
        quality_layout.get("fail_on_awkward_whitespace") is not True
        or quality_layout.get("evidence_anchor_required") is not True
        or quality_layout.get("avoid_repeated_card_grids") is not True
        or "compact source/ref IDs" not in str(quality_layout.get("source_footer_rule") or "")
    ):
        failures.append({"step": "design_brief", "reason": "slide_quality_layout_not_persisted", "layout_targets": quality_layout})
    if (
        quality_artifacts.get("required_when_data_artifacts_active") is not True
        or "source data fingerprints" not in quality_must_record
        or "image whitespace measurement or trim rule" not in quality_must_record
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "slide_quality_artifact_targets_not_persisted",
                "artifact_quality_targets": quality_artifacts,
            }
        )
    if (
        "whitespace_warnings" not in quality_fail_on
        or "design_readability_warnings" not in quality_fail_on
        or len(quality_commands) < 4
        or not any("--fail-on-whitespace-warnings" in str(command) for command in quality_commands)
        or not any("--skip-render" in str(command) for command in quality_commands)
        or not any("report_delivery_readiness.py" in str(command) for command in quality_commands)
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "slide_quality_qa_gates_not_persisted",
                "qa_gates": quality_qa,
            }
        )
    if not isinstance(content.get("slide_plan"), list) or len(content.get("slide_plan")) != 2:
        failures.append({"step": "content_plan", "reason": "slide_plan_not_mapped", "slide_plan": content.get("slide_plan")})
    if evidence.get("source_policy") != "cite key claims":
        failures.append({"step": "evidence_plan", "reason": "source_policy_not_mapped", "value": evidence.get("source_policy")})
    if (
        "<!-- deck-design-contract:start -->" not in notes
        or "Choice Resolution" not in notes
        or "Reproducibility Replay" not in notes
        or "Slide Quality Contract" not in notes
    ):
        failures.append({"step": "notes", "reason": "contract_notes_missing"})

    if planning.get("error_count") != 0 or planning.get("warning_count") != 0:
        failures.append(
            {
                "step": "validate_planning",
                "error_count": planning.get("error_count"),
                "warning_count": planning.get("warning_count"),
                "issues": planning.get("issues", [])[:6],
            }
        )

    summary = readiness.get("design_contract") if isinstance(readiness.get("design_contract"), dict) else {}
    if summary.get("status") != "applied" or summary.get("applied") is not True:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "design_contract_not_applied",
                "status": summary.get("status"),
                "applied": summary.get("applied"),
            }
        )
    readiness_choice = summary.get("choice_resolution") if isinstance(summary.get("choice_resolution"), dict) else {}
    if readiness_choice.get("stable_prompt_id") != expected_seed or readiness_choice.get("choice_count", 0) < 2:
        failures.append({"step": "workspace_readiness", "reason": "choice_resolution_not_summarized"})
    qa_summary = summary.get("qa_contract") if isinstance(summary.get("qa_contract"), dict) else {}
    if qa_summary.get("required_check_count", 0) < 3 or qa_summary.get("placeholder_checks") is not True:
        failures.append({"step": "workspace_readiness", "reason": "qa_contract_not_summarized"})
    quality_summary = summary.get("slide_quality_contract") if isinstance(summary.get("slide_quality_contract"), dict) else {}
    if (
        quality_summary.get("contract_version") != "slide_quality_contract_v1"
        or quality_summary.get("min_title_pt") != 24
        or quality_summary.get("min_body_pt") != 12
        or quality_summary.get("chart_label_min_pt") != 7
        or quality_summary.get("footer_reserved_inches") != 0.25
        or quality_summary.get("fail_on_awkward_whitespace") is not True
        or quality_summary.get("evidence_anchor_required") is not True
        or quality_summary.get("artifact_quality_required_when_data_active") is not True
        or quality_summary.get("required_command_count", 0) < 4
    ):
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "slide_quality_contract_not_summarized",
                "slide_quality_contract": quality_summary,
            }
        )
    readiness_quality_context = (
        readiness.get("quality_context")
        if isinstance(readiness.get("quality_context"), dict)
        else {}
    )
    readiness_quality = (
        readiness_quality_context.get("slide_quality_contract")
        if isinstance(readiness_quality_context.get("slide_quality_contract"), dict)
        else {}
    )
    if (
        readiness_quality.get("contract_version") != "slide_quality_contract_v1"
        or readiness_quality.get("min_title_pt") != 24
        or readiness_quality.get("min_body_pt") != 12
        or readiness_quality.get("chart_label_min_pt") != 7
        or readiness_quality.get("footer_reserved_inches") != 0.25
        or readiness_quality.get("fail_on_awkward_whitespace") is not True
        or readiness_quality.get("evidence_anchor_required") is not True
        or readiness_quality.get("required_command_count", 0) < 4
    ):
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "top_level_quality_context_not_summarized",
                "quality_context": readiness_quality_context,
            }
        )
    readiness_markdown = (
        (workspace / "build" / "workspace_readiness.md").read_text(encoding="utf-8")
        if (workspace / "build" / "workspace_readiness.md").exists()
        else ""
    )
    if "Contract slide quality:" not in readiness_markdown or "slide_quality_contract_v1" not in readiness_markdown:
        failures.append({"step": "workspace_readiness", "reason": "slide_quality_contract_markdown_missing"})
    readiness_replay = summary.get("reproducibility_contract") if isinstance(summary.get("reproducibility_contract"), dict) else {}
    readiness_replay_style = (
        readiness_replay.get("style_replay")
        if isinstance(readiness_replay.get("style_replay"), dict)
        else {}
    )
    if (
        readiness_replay.get("style_seed") != expected_seed
        or readiness_replay.get("replay_command_count", 0) < 3
        or readiness_replay_style.get("header_variant_pool") != ["split-rule", "top-bottom-rule", "plain"]
    ):
        failures.append({"step": "workspace_readiness", "reason": "replay_contract_not_summarized", "replay": readiness_replay})


def _assert_advance_replay_state(
    *,
    expected_seed: str,
    advance: dict[str, Any],
    next_action_text: str,
    failures: list[dict[str, Any]],
) -> None:
    replay = (
        advance.get("reproducibility_contract")
        if isinstance(advance.get("reproducibility_contract"), dict)
        else {}
    )
    style_replay = replay.get("style_replay") if isinstance(replay.get("style_replay"), dict) else {}
    if (
        replay.get("style_seed") != expected_seed
        or replay.get("replay_command_count", 0) < 3
        or style_replay.get("header_variant_pool") != ["split-rule", "top-bottom-rule", "plain"]
    ):
        failures.append({"step": "advance_workspace", "reason": "replay_contract_not_summarized", "replay": replay})

    steps = advance.get("steps") if isinstance(advance.get("steps"), list) else []
    first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
    step_replay = (
        first_step.get("reproducibility_contract")
        if isinstance(first_step.get("reproducibility_contract"), dict)
        else {}
    )
    if step_replay.get("style_seed") != expected_seed:
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "step_replay_contract_missing",
                "step_entry": first_step,
            }
        )

    quality = (
        advance.get("quality_context")
        if isinstance(advance.get("quality_context"), dict)
        else {}
    )
    slide_quality = (
        quality.get("slide_quality_contract")
        if isinstance(quality.get("slide_quality_contract"), dict)
        else {}
    )
    step_quality = (
        first_step.get("quality_context")
        if isinstance(first_step.get("quality_context"), dict)
        else {}
    )
    step_slide_quality = (
        step_quality.get("slide_quality_contract")
        if isinstance(step_quality.get("slide_quality_contract"), dict)
        else {}
    )
    if (
        slide_quality.get("contract_version") != "slide_quality_contract_v1"
        or slide_quality.get("min_title_pt") != 24
        or slide_quality.get("min_body_pt") != 12
        or slide_quality.get("chart_label_min_pt") != 7
        or slide_quality.get("footer_reserved_inches") != 0.25
        or slide_quality.get("fail_on_awkward_whitespace") is not True
        or slide_quality.get("evidence_anchor_required") is not True
        or slide_quality.get("required_command_count", 0) < 4
    ):
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "quality_context_not_summarized",
                "quality_context": quality,
            }
        )
    if step_slide_quality.get("contract_version") != "slide_quality_contract_v1":
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "step_quality_context_missing",
                "step_entry": first_step,
            }
        )

    if (
        "## Replay Contract" not in next_action_text
        or "deck_reproducibility_contract_v1" not in next_action_text
        or expected_seed not in next_action_text
        or "split-rule" not in next_action_text
    ):
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "next_action_markdown_missing_replay_contract",
            }
        )
    if (
        "## Quality Context" not in next_action_text
        or "Slide quality contract:" not in next_action_text
        or "slide_quality_contract_v1" not in next_action_text
        or "whitespace=`True`" not in next_action_text
        or "evidence_anchor=`True`" not in next_action_text
    ):
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "next_action_markdown_missing_quality_context",
            }
        )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a focused design-contract prompt/apply smoke check."
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
        else Path(tempfile.mkdtemp(prefix="presentation-skill-design-contract-"))
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
        _run_checked(
            [
                py,
                str(repo / "scripts" / "init_deck_workspace.py"),
                "--workspace",
                str(workspace),
                "--title",
                "Design Contract Smoke",
                "--style-preset",
                "lab-report",
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        if failures:
            raise RuntimeError("workspace initialization failed")

        source_fixture_path = _write_source_data_fixture(workspace)
        build_dir.mkdir(parents=True, exist_ok=True)
        packet_path = workspace / "deck_start_packet.json"
        answers_path = workspace / "intake_answers.json"
        prompt_path = build_dir / "design_contract_prompt.md"
        contract_path = workspace / "design_contract.json"
        apply_report_path = workspace / "design_contract_apply_report.json"
        repeat_report_path = build_dir / "design_contract_apply_report_repeat.json"
        planning_report_path = build_dir / "design_contract_planning.json"
        readiness_report_path = build_dir / "design_contract_readiness.json"
        advance_report_path = build_dir / "design_contract_workspace_advance.json"
        advance_readiness_report_path = build_dir / "design_contract_advance_readiness.json"
        advance_next_action_path = build_dir / "design_contract_workspace_next_action.md"

        _run_checked(
            [
                py,
                str(repo / "scripts" / "emit_deck_start_packet.py"),
                "--workspace",
                str(workspace),
                "--user-prompt",
                USER_PROMPT,
                "--output",
                str(packet_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        packet = _load_json(packet_path)
        if not isinstance(packet, dict):
            failures.append({"step": "deck_start_packet", "reason": "packet_not_object"})
            packet = {}
        answers = _answers_for(packet)
        _write_json(answers_path, answers)
        _run_checked(
            [
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
                str(workspace / "intake_apply_report.json"),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        source_fixture_path.unlink(missing_ok=True)

        _run_checked(
            [
                py,
                str(repo / "scripts" / "emit_design_contract_prompt.py"),
                "--workspace",
                str(workspace),
                "--user-prompt",
                USER_PROMPT,
                "--output",
                str(prompt_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        seed = str(packet.get("recommended_style_seed") or "").strip()
        if "design_brief.choice_resolution_seed summary" not in prompt_text or seed not in prompt_text:
            failures.append({"step": "emit_design_contract_prompt", "reason": "prompt_missing_choice_seed_context"})
        if '"reproducibility_contract"' not in prompt_text or "deck_reproducibility_contract_v1" not in prompt_text:
            failures.append({"step": "emit_design_contract_prompt", "reason": "prompt_missing_reproducibility_contract"})
        if '"slide_quality_contract"' not in prompt_text or "slide_quality_contract_v1" not in prompt_text:
            failures.append({"step": "emit_design_contract_prompt", "reason": "prompt_missing_slide_quality_contract"})
        if "preset treatment profile for design contract" not in prompt_text or "deck_preset_treatment_profiles_v1" not in prompt_text:
            failures.append({"step": "emit_design_contract_prompt", "reason": "prompt_missing_preset_treatment_profile"})

        packet_quality = (
            packet.get("slide_quality_contract")
            if isinstance(packet.get("slide_quality_contract"), dict)
            else {}
        )
        _write_json(
            contract_path,
            _contract_fixture(seed=seed, slide_quality_contract=packet_quality),
        )
        for cmd in (
            [
                py,
                str(repo / "scripts" / "apply_design_contract.py"),
                "--workspace",
                str(workspace),
                "--contract",
                str(contract_path),
                "--report",
                str(apply_report_path),
            ],
            [
                py,
                str(repo / "scripts" / "apply_design_contract.py"),
                "--workspace",
                str(workspace),
                "--contract",
                str(contract_path),
                "--report",
                str(repeat_report_path),
            ],
            [
                py,
                str(repo / "scripts" / "validate_planning.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(planning_report_path),
            ],
        ):
            _run_checked(cmd, cwd=repo, command_results=command_results, failures=failures)
        _run_checked(
            [
                py,
                str(repo / "scripts" / "report_workspace_readiness.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(readiness_report_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )
        _run_checked(
            [
                py,
                str(repo / "scripts" / "advance_workspace.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(advance_report_path),
                "--readiness-report",
                str(advance_readiness_report_path),
                "--next-action-markdown",
                str(advance_next_action_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
            allowed_returncodes={0, 1},
        )

        apply_report = _load_json(apply_report_path)
        repeat_report = _load_json(repeat_report_path)
        planning = _load_json(planning_report_path)
        readiness = _load_json(readiness_report_path)
        advance = _load_json(advance_report_path)
        advance_next_action_text = (
            advance_next_action_path.read_text(encoding="utf-8")
            if advance_next_action_path.exists()
            else ""
        )
        _assert_contract_state(
            workspace=workspace,
            packet=packet,
            apply_report=apply_report if isinstance(apply_report, dict) else {},
            repeat_report=repeat_report if isinstance(repeat_report, dict) else {},
            planning=planning if isinstance(planning, dict) else {},
            readiness=readiness if isinstance(readiness, dict) else {},
            failures=failures,
        )
        _assert_advance_replay_state(
            expected_seed=seed,
            advance=advance if isinstance(advance, dict) else {},
            next_action_text=advance_next_action_text,
            failures=failures,
        )

        design_summary = (
            readiness.get("design_contract", {})
            if isinstance(readiness, dict) and isinstance(readiness.get("design_contract"), dict)
            else {}
        )
        readiness_quality_context = (
            readiness.get("quality_context", {})
            if isinstance(readiness, dict) and isinstance(readiness.get("quality_context"), dict)
            else {}
        )
        readiness_slide_quality = (
            readiness_quality_context.get("slide_quality_contract", {})
            if isinstance(readiness_quality_context.get("slide_quality_contract"), dict)
            else {}
        )
        advance_quality = (
            advance.get("quality_context", {})
            if isinstance(advance, dict) and isinstance(advance.get("quality_context"), dict)
            else {}
        )
        advance_slide_quality = (
            advance_quality.get("slide_quality_contract", {})
            if isinstance(advance_quality.get("slide_quality_contract"), dict)
            else {}
        )
        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "recommended_style_seed": seed,
            "prompt_contains_choice_seed": "design_brief.choice_resolution_seed summary" in prompt_text and seed in prompt_text,
            "prompt_contains_reproducibility_contract": '"reproducibility_contract"' in prompt_text and "deck_reproducibility_contract_v1" in prompt_text,
            "prompt_contains_slide_quality_contract": '"slide_quality_contract"' in prompt_text and "slide_quality_contract_v1" in prompt_text,
            "apply_changed_file_count": len(apply_report.get("changed_files", [])) if isinstance(apply_report, dict) else None,
            "repeat_changed_file_count": len(repeat_report.get("changed_files", [])) if isinstance(repeat_report, dict) else None,
            "choice_resolution_enriched_from_seed": apply_report.get("choice_resolution_enriched_from_seed") if isinstance(apply_report, dict) else None,
            "reproducibility_contract_applied": apply_report.get("reproducibility_contract_applied") if isinstance(apply_report, dict) else None,
            "slide_quality_contract_applied": apply_report.get("slide_quality_contract_applied") if isinstance(apply_report, dict) else None,
            "slide_quality_contract_version": apply_report.get("slide_quality_contract_version") if isinstance(apply_report, dict) else None,
            "planning_counts": {
                "errors": planning.get("error_count") if isinstance(planning, dict) else None,
                "warnings": planning.get("warning_count") if isinstance(planning, dict) else None,
            },
            "readiness_status": readiness.get("status") if isinstance(readiness, dict) else None,
            "design_contract_status": design_summary.get("status"),
            "readiness_quality_contract_version": readiness_slide_quality.get("contract_version"),
            "advance_decision": advance.get("decision") if isinstance(advance, dict) else None,
            "advance_reproducibility_contract": (
                advance.get("reproducibility_contract") if isinstance(advance, dict) else None
            ),
            "advance_quality_contract_version": advance_slide_quality.get("contract_version"),
            "next_action_contains_replay_contract": "## Replay Contract" in advance_next_action_text
            and "deck_reproducibility_contract_v1" in advance_next_action_text
            and seed in advance_next_action_text,
            "next_action_contains_quality_context": "## Quality Context" in advance_next_action_text
            and "slide_quality_contract_v1" in advance_next_action_text,
            "failures": failures,
            "commands": command_results,
        }
        (build_dir / "design_contract_apply_smoke.json").write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    key: summary[key]
                    for key in (
                        "passed",
                        "workspace",
                        "recommended_style_seed",
                        "prompt_contains_choice_seed",
                        "prompt_contains_reproducibility_contract",
                        "prompt_contains_slide_quality_contract",
                        "apply_changed_file_count",
                        "repeat_changed_file_count",
                        "choice_resolution_enriched_from_seed",
                        "reproducibility_contract_applied",
                        "slide_quality_contract_applied",
                        "planning_counts",
                        "readiness_status",
                        "design_contract_status",
                        "readiness_quality_contract_version",
                        "advance_decision",
                        "advance_quality_contract_version",
                        "next_action_contains_replay_contract",
                        "next_action_contains_quality_context",
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
            (build_dir / "design_contract_apply_smoke.json").write_text(
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
