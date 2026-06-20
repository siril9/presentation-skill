#!/usr/bin/env python3
"""Fast smoke check for contract-aware outline authoring handoff."""

from __future__ import annotations

import argparse
import json
import re
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

PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|XXX|lorem|ipsum)\b|\[(?:insert|placeholder)[^\]]*\]",
    re.IGNORECASE,
)


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


def _style_seed(workspace: Path) -> str:
    brief = _load_json(workspace / "design_brief.json")
    style = brief.get("style_system") if isinstance(brief.get("style_system"), dict) else {}
    return str(style.get("style_seed") or "").strip()


def _assert_advance_quality_context(
    *,
    advance: dict[str, Any],
    next_action_text: str,
    failures: list[dict[str, Any]],
) -> None:
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
    outline_quality = (
        quality.get("outline_quality_alignment")
        if isinstance(quality.get("outline_quality_alignment"), dict)
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
    ):
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "slide_quality_context_not_summarized",
                "quality_context": quality,
            }
        )
    if (
        outline_quality.get("present") is not True
        or outline_quality.get("persisted") is not True
        or outline_quality.get("contract_version") != "slide_quality_contract_v1"
        or outline_quality.get("readability_target_count") < 4
        or outline_quality.get("layout_target_count") < 4
        or outline_quality.get("artifact_quality_target_count") < 2
        or outline_quality.get("qa_gate_count") < 3
        or outline_quality.get("required_command_count") < 3
    ):
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "outline_quality_context_not_summarized",
                "quality_context": quality,
            }
        )

    steps = advance.get("steps") if isinstance(advance.get("steps"), list) else []
    first_step = steps[0] if steps and isinstance(steps[0], dict) else {}
    step_quality = (
        first_step.get("quality_context")
        if isinstance(first_step.get("quality_context"), dict)
        else {}
    )
    step_outline_quality = (
        step_quality.get("outline_quality_alignment")
        if isinstance(step_quality.get("outline_quality_alignment"), dict)
        else {}
    )
    if step_outline_quality.get("contract_version") != "slide_quality_contract_v1":
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "step_outline_quality_context_missing",
                "step_entry": first_step,
            }
        )

    if (
        "## Quality Context" not in next_action_text
        or "Slide quality contract:" not in next_action_text
        or "Outline quality alignment:" not in next_action_text
        or "slide_quality_contract_v1" not in next_action_text
    ):
        failures.append(
            {
                "step": "advance_workspace",
                "reason": "next_action_markdown_missing_quality_context",
            }
        )


def _outline_handoff(*, workspace: Path, seed: str) -> dict[str, Any]:
    slides = [
        {
            "slide_id": "s1",
            "type": "title",
            "title": "Design Contract Smoke",
            "subtitle": "Assay readout structure smoke",
            "sources": ["S1: Synthetic outline handoff smoke"],
        },
        {
            "slide_id": "s2",
            "type": "content",
            "variant": "lab-run-results",
            "title": "Assay readouts are structured before rendering",
            "subtitle": "Fixture table / compact source footer",
            "slide_intent": "evidence",
            "visual_intent": "table",
            "headers": ["Readout", "Value", "State"],
            "rows": [
                ["Positive control", "42.1 RFU", "Pass"],
                ["Limit check", "12 copies", "Review"],
                ["NTC", "0.2 RFU", "Pass"],
            ],
            "column_weights": [1.2, 0.9, 0.8],
            "interpretation": (
                "The handoff creates evidence-first report slides with a "
                "readable table anchor before rendering."
            ),
            "sources": ["S1: Synthetic assay fixture"],
        },
        {
            "slide_id": "s3",
            "type": "content",
            "variant": "comparison-2col",
            "title": "Source edits stay replayable",
            "subtitle": "Contract decisions / authored source files",
            "slide_intent": "comparison",
            "visual_intent": "structured comparison",
            "left": {
                "title": "Locked by contract",
                "body": [
                    "Style seed and lab-report preset",
                    "Source-line footer and page numbers",
                    "Readability and QA gates",
                ],
            },
            "right": {
                "title": "Authored by handoff",
                "body": [
                    "Stable slide IDs",
                    "Aligned content and evidence plans",
                    "Compact assumptions in notes",
                ],
            },
            "verdict": (
                "The outline handoff converts the contract into source files "
                "without mutating PPTX artifacts."
            ),
            "sources": ["S2: Outline handoff fixture"],
        },
    ]
    return {
        "handoff_version": "outline_authoring_handoff_v1",
        "workspace": str(workspace),
        "contract_alignment": {
            "style_seed": seed,
            "style_preset": "lab-report",
            "header_footer_plan": (
                "Use lab-clean auto header variants and source-line footer/page "
                "numbers from the contract."
            ),
            "variant_mix_plan": (
                "Use title, lab-run-results, and comparison-2col without random cycling."
            ),
        },
        "artifact_rebuild_plan": {
            "context_version": "presentation_skill_artifact_rebuild_context_v1",
            "producer_path": "none",
            "source_paths": [],
            "output_paths": [],
            "commands_to_preserve": [
                "python3 scripts/report_workspace_readiness.py --workspace <deck>",
                "python3 scripts/validate_planning.py --workspace <deck>",
            ],
            "notes": "No generated artifacts in this fixture; preserve the schema for generated-data decks.",
        },
        "quality_alignment": {
            "contract_version": "slide_quality_contract_v1",
            "readability_targets_used": [
                "min_title_pt=24",
                "min_body_pt=12",
                "chart_label_min_pt=7",
                "footer_reserved_inches=0.25",
            ],
            "layout_targets_used": [
                "evidence_anchor_required",
                "fail_on_awkward_whitespace",
                "avoid_repeated_card_grids",
                "compact_source_footer",
            ],
            "artifact_quality_targets_used": [
                "record generated artifact source fingerprints and producer fingerprints",
                "record image whitespace measurement or trim rule when generated figures are used",
            ],
            "qa_gates_used": [
                "planning_warnings",
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
                "python3 scripts/report_delivery_readiness.py --workspace <deck>",
            ],
            "outline_choices": (
                "Used an evidence-first lab-run-results slide plus a structured "
                "comparison slide so the outline has anchors and avoids stranded prose."
            ),
        },
        "source_patch": {
            "outline_json": {
                "title": "Design Contract Smoke",
                "subtitle": "Assay readout structure smoke",
                "deck_style": {
                    "style_seed": seed,
                    "header_mode": "lab-clean",
                    "header_variant": "auto",
                    "header_variants": ["split-rule", "top-bottom-rule", "plain"],
                    "footer_mode": "source-line",
                    "footer_page_numbers": True,
                },
                "slides": slides,
            },
            "content_plan_updates": {
                "thesis": "A locked design contract can produce a clean, replayable lab-report outline.",
                "audience": "presentation-skill maintainers",
                "slide_plan": [
                    {
                        "slide_id": "s1",
                        "role": "title",
                        "message": "Introduce the outline authoring smoke deck.",
                        "variant": "title",
                        "visual_strategy": "title opener",
                        "evidence_needs": [],
                        "asset_needs": [],
                    },
                    {
                        "slide_id": "s2",
                        "role": "evidence",
                        "message": "Show that report evidence becomes a table-centered slide.",
                        "variant": "lab-run-results",
                        "visual_strategy": "editable lab result table",
                        "evidence_needs": ["S1"],
                        "asset_needs": [],
                    },
                    {
                        "slide_id": "s3",
                        "role": "synthesis",
                        "message": "Show which decisions are locked versus authored.",
                        "variant": "comparison-2col",
                        "visual_strategy": "structured comparison",
                        "evidence_needs": ["S2"],
                        "asset_needs": [],
                    },
                ],
                "narrative_arc": [
                    {
                        "act": "setup",
                        "purpose": "State the deck contract.",
                        "slides": ["s1"],
                    },
                    {
                        "act": "evidence",
                        "purpose": "Demonstrate evidence-first authoring.",
                        "slides": ["s2"],
                    },
                    {
                        "act": "synthesis",
                        "purpose": "Show replayable source edits.",
                        "slides": ["s3"],
                    },
                ],
            },
            "evidence_plan_updates": {
                "source_policy": "cite key claims",
                "items": [
                    {
                        "id": "S1",
                        "claim": "Synthetic assay fixture values exercise readable lab-run-results tables.",
                        "source": "Generated outline-authoring smoke fixture",
                        "used_on_slides": ["s2"],
                    },
                    {
                        "id": "S2",
                        "claim": "The outline handoff applies source edits deterministically.",
                        "source": "apply_outline_authoring_handoff.py report",
                        "used_on_slides": ["s3"],
                    },
                ],
                "chart_candidates": [],
            },
            "asset_plan_updates": {
                "images": [],
                "charts": [],
                "tables": [],
                "generated_images": [],
            },
            "notes_append": "Synthetic fixture only; no factual assay claims are made.",
        },
        "acceptance_checks": [
            "outline has no placeholders",
            "slide IDs resolve",
            "run readiness and render-free QA",
        ],
        "main_agent_handoff": {
            "files_to_patch": [
                str(workspace / "outline.json"),
                str(workspace / "content_plan.json"),
                str(workspace / "evidence_plan.json"),
                str(workspace / "asset_plan.json"),
                str(workspace / "notes.md"),
            ],
            "commands_after_patch": [
                "python3 scripts/apply_outline_authoring_handoff.py --workspace <deck> --handoff <deck>/outline_authoring_handoff.json",
                "python3 scripts/report_workspace_readiness.py --workspace <deck>",
                "python3 scripts/build_workspace.py --workspace <deck> --overwrite",
                "python3 scripts/qa_gate.py --input <deck>/build/deck.pptx --outline <deck>/outline.json --skip-render",
            ],
        },
    }


def _visible_text_values(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in {"notes", "speaker_notes"}:
                continue
            texts.extend(_visible_text_values(nested))
    elif isinstance(value, list):
        for nested in value:
            texts.extend(_visible_text_values(nested))
    elif isinstance(value, str):
        texts.append(value)
    return texts


def _assert_outline_state(
    *,
    workspace: Path,
    apply_report: dict[str, Any],
    repeat_report: dict[str, Any],
    planning: dict[str, Any],
    readiness: dict[str, Any],
    build_report: dict[str, Any],
    qa_report: dict[str, Any],
    failures: list[dict[str, Any]],
) -> None:
    outline = _load_json(workspace / "outline.json")
    content = _load_json(workspace / "content_plan.json")
    evidence = _load_json(workspace / "evidence_plan.json")
    design = _load_json(workspace / "design_brief.json")
    notes = (workspace / "notes.md").read_text(encoding="utf-8") if (workspace / "notes.md").exists() else ""

    if apply_report.get("workflow") != "outline_authoring_handoff_apply_v1":
        failures.append({"step": "apply_outline_authoring_handoff", "reason": "wrong_workflow"})
    if apply_report.get("outline_changed") is not True:
        failures.append({"step": "apply_outline_authoring_handoff", "reason": "outline_not_changed"})
    if apply_report.get("content_plan_changed") is not True or apply_report.get("evidence_plan_changed") is not True:
        failures.append({"step": "apply_outline_authoring_handoff", "reason": "plans_not_changed"})
    if apply_report.get("design_brief_changed") is not True or apply_report.get("artifact_rebuild_plan_applied") is not True:
        failures.append(
            {
                "step": "apply_outline_authoring_handoff",
                "reason": "artifact_rebuild_plan_not_persisted",
                "design_brief_changed": apply_report.get("design_brief_changed"),
                "artifact_rebuild_plan_applied": apply_report.get("artifact_rebuild_plan_applied"),
            }
        )
    if apply_report.get("quality_alignment_applied") is not True:
        failures.append(
            {
                "step": "apply_outline_authoring_handoff",
                "reason": "quality_alignment_not_applied",
                "quality_alignment_applied": apply_report.get("quality_alignment_applied"),
            }
        )
    if apply_report.get("notes_changed") is not True:
        failures.append({"step": "apply_outline_authoring_handoff", "reason": "notes_not_changed"})
    if repeat_report.get("changed_file_count") != 0:
        failures.append(
            {
                "step": "apply_outline_authoring_handoff_repeat",
                "reason": "not_idempotent",
                "changed_file_count": repeat_report.get("changed_file_count"),
            }
        )

    slides = outline.get("slides") if isinstance(outline.get("slides"), list) else []
    slide_ids = [str(slide.get("slide_id") or slide.get("id") or "").strip() for slide in slides if isinstance(slide, dict)]
    if slide_ids != ["s1", "s2", "s3"]:
        failures.append({"step": "outline", "reason": "unexpected_slide_ids", "slide_ids": slide_ids})
    visible_text = "\n".join(_visible_text_values(outline))
    if PLACEHOLDER_RE.search(visible_text):
        failures.append({"step": "outline", "reason": "placeholder_text_found"})
    if not any(isinstance(slide, dict) and slide.get("variant") == "lab-run-results" for slide in slides):
        failures.append({"step": "outline", "reason": "missing_lab_results_slide"})

    plan_ids = [
        str(item.get("slide_id") or "").strip()
        for item in content.get("slide_plan", [])
        if isinstance(item, dict)
    ] if isinstance(content.get("slide_plan"), list) else []
    if plan_ids != slide_ids:
        failures.append({"step": "content_plan", "reason": "slide_plan_not_aligned", "plan_ids": plan_ids, "slide_ids": slide_ids})

    evidence_items = evidence.get("items") if isinstance(evidence.get("items"), list) else []
    evidence_slide_refs = sorted(
        {
            str(ref).strip()
            for item in evidence_items
            if isinstance(item, dict)
            for ref in item.get("used_on_slides", [])
            if str(ref).strip()
        }
    )
    if evidence_slide_refs != ["s2", "s3"]:
        failures.append({"step": "evidence_plan", "reason": "evidence_slide_refs_not_aligned", "refs": evidence_slide_refs})
    if "<!-- outline-authoring-handoff:start -->" not in notes:
        failures.append({"step": "notes", "reason": "outline_handoff_notes_missing"})
    if "### Artifact Rebuild Plan" not in notes or "presentation_skill_artifact_rebuild_context_v1" not in notes:
        failures.append({"step": "notes", "reason": "artifact_rebuild_plan_notes_missing"})
    if "### Quality Alignment" not in notes or "slide_quality_contract_v1" not in notes:
        failures.append({"step": "notes", "reason": "quality_alignment_notes_missing"})

    outline_meta = design.get("outline_authoring_handoff") if isinstance(design.get("outline_authoring_handoff"), dict) else {}
    persisted_plan = (
        outline_meta.get("artifact_rebuild_plan")
        if isinstance(outline_meta.get("artifact_rebuild_plan"), dict)
        else {}
    )
    persisted_quality = (
        outline_meta.get("quality_alignment")
        if isinstance(outline_meta.get("quality_alignment"), dict)
        else {}
    )
    analysis_plan = design.get("analysis_artifact_plan") if isinstance(design.get("analysis_artifact_plan"), dict) else {}
    if persisted_plan.get("context_version") != "presentation_skill_artifact_rebuild_context_v1":
        failures.append(
            {
                "step": "design_brief",
                "reason": "missing_outline_artifact_rebuild_plan",
                "outline_authoring_handoff": outline_meta,
            }
        )
    if not isinstance(analysis_plan.get("outline_authoring_rebuild_plan"), dict):
        failures.append({"step": "design_brief", "reason": "missing_analysis_outline_rebuild_plan"})
    if (
        persisted_quality.get("contract_version") != "slide_quality_contract_v1"
        or "min_title_pt=24" not in persisted_quality.get("readability_targets_used", [])
        or "fail_on_awkward_whitespace" not in persisted_quality.get("layout_targets_used", [])
        or "whitespace_warnings" not in persisted_quality.get("qa_gates_used", [])
        or not any(
            "--fail-on-whitespace-warnings" in str(command)
            for command in persisted_quality.get("required_commands", [])
        )
    ):
        failures.append(
            {
                "step": "design_brief",
                "reason": "missing_outline_quality_alignment",
                "quality_alignment": persisted_quality,
            }
        )

    if planning.get("error_count") != 0 or planning.get("warning_count") != 0:
        failures.append(
            {
                "step": "validate_planning",
                "error_count": planning.get("error_count"),
                "warning_count": planning.get("warning_count"),
                "issues": planning.get("issues", [])[:6],
            }
        )
    if readiness.get("status") != "ready":
        failures.append({"step": "workspace_readiness", "status": readiness.get("status")})
    handoff_summary = (
        readiness.get("outline_authoring_handoff")
        if isinstance(readiness.get("outline_authoring_handoff"), dict)
        else {}
    )
    if handoff_summary.get("status") != "applied" or handoff_summary.get("applied") is not True:
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "outline_handoff_not_applied",
                "status": handoff_summary.get("status"),
            }
        )
    required_patch_fields = {
        "outline_json",
        "content_plan_updates",
        "evidence_plan_updates",
        "asset_plan_updates",
        "notes_append",
    }
    if not required_patch_fields.issubset(set(handoff_summary.get("patch_fields", []))):
        failures.append({"step": "workspace_readiness", "reason": "patch_fields_not_summarized", "patch_fields": handoff_summary.get("patch_fields")})
    readiness_rebuild = (
        handoff_summary.get("artifact_rebuild_plan")
        if isinstance(handoff_summary.get("artifact_rebuild_plan"), dict)
        else {}
    )
    if (
        readiness_rebuild.get("present") is not True
        or readiness_rebuild.get("persisted") is not True
        or readiness_rebuild.get("context_version") != "presentation_skill_artifact_rebuild_context_v1"
        or readiness_rebuild.get("command_count") != 2
    ):
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "artifact_rebuild_plan_not_summarized",
                "artifact_rebuild_plan": readiness_rebuild,
            }
        )
    readiness_quality = (
        handoff_summary.get("quality_alignment")
        if isinstance(handoff_summary.get("quality_alignment"), dict)
        else {}
    )
    if (
        readiness_quality.get("present") is not True
        or readiness_quality.get("persisted") is not True
        or readiness_quality.get("contract_version") != "slide_quality_contract_v1"
        or readiness_quality.get("readability_target_count") < 4
        or readiness_quality.get("layout_target_count") < 4
        or readiness_quality.get("qa_gate_count") < 3
        or readiness_quality.get("required_command_count") < 3
    ):
        failures.append(
            {
                "step": "workspace_readiness",
                "reason": "quality_alignment_not_summarized",
                "quality_alignment": readiness_quality,
            }
        )
    readiness_quality_context = (
        readiness.get("quality_context")
        if isinstance(readiness.get("quality_context"), dict)
        else {}
    )
    readiness_outline_quality = (
        readiness_quality_context.get("outline_quality_alignment")
        if isinstance(readiness_quality_context.get("outline_quality_alignment"), dict)
        else {}
    )
    if (
        readiness_outline_quality.get("present") is not True
        or readiness_outline_quality.get("persisted") is not True
        or readiness_outline_quality.get("contract_version") != "slide_quality_contract_v1"
        or readiness_outline_quality.get("readability_target_count") < 4
        or readiness_outline_quality.get("layout_target_count") < 4
        or readiness_outline_quality.get("artifact_quality_target_count") < 2
        or readiness_outline_quality.get("qa_gate_count") < 3
        or readiness_outline_quality.get("required_command_count") < 3
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
    if "Outline quality alignment:" not in readiness_markdown or "slide_quality_contract_v1" not in readiness_markdown:
        failures.append({"step": "workspace_readiness", "reason": "quality_alignment_markdown_missing"})

    output = build_report.get("outputs", {}).get("pptx") if isinstance(build_report.get("outputs"), dict) else {}
    if build_report.get("run", {}).get("status") != "succeeded" or not output.get("exists"):
        failures.append({"step": "build_workspace", "reason": "pptx_build_not_succeeded", "run": build_report.get("run"), "output": output})

    if qa_report.get("overflow_count") != 0 or qa_report.get("overlap_count") != 0:
        failures.append({"step": "qa_gate", "reason": "overflow_or_overlap", "qa": qa_report})
    if qa_report.get("placeholder_hits"):
        failures.append({"step": "qa_gate", "reason": "placeholder_hits", "hits": qa_report.get("placeholder_hits")})
    if qa_report.get("geometry_error_count") != 0 or qa_report.get("whitespace_warning_count") != 0:
        failures.append(
            {
                "step": "qa_gate",
                "reason": "geometry_or_whitespace",
                "geometry_error_count": qa_report.get("geometry_error_count"),
                "whitespace_warning_count": qa_report.get("whitespace_warning_count"),
            }
        )
    if qa_report.get("visual_warning_count") != 0 or qa_report.get("design_error_count") != 0:
        failures.append(
            {
                "step": "qa_gate",
                "reason": "visual_or_design_errors",
                "visual_warning_count": qa_report.get("visual_warning_count"),
                "design_error_count": qa_report.get("design_error_count"),
            }
        )
    if qa_report.get("design_warning_count") != 0:
        failures.append(
            {
                "step": "qa_gate",
                "reason": "design_warnings",
                "design_warning_count": qa_report.get("design_warning_count"),
            }
        )


def _workspace_output_pptx(workspace: Path, build_report: dict[str, Any]) -> Path:
    output = build_report.get("outputs", {}).get("pptx") if isinstance(build_report.get("outputs"), dict) else {}
    raw = str(output.get("path") or "").strip() if isinstance(output, dict) else ""
    if raw:
        path = Path(raw)
        return path if path.is_absolute() else workspace / path
    return workspace / "build" / "deck.pptx"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a focused outline-authoring handoff smoke check."
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
        else Path(tempfile.mkdtemp(prefix="presentation-skill-outline-handoff-"))
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
                str(repo / "scripts" / "run_design_contract_apply_smoke.py"),
                "--workspace",
                str(workspace),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
        )
        if failures:
            raise RuntimeError("design-contract setup failed")

        build_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = build_dir / "outline_authoring_prompt.md"
        handoff_path = workspace / "outline_authoring_handoff.json"
        apply_report_path = workspace / "outline_authoring_handoff_apply_report.json"
        repeat_report_path = build_dir / "outline_authoring_handoff_apply_repeat.json"
        planning_report_path = build_dir / "outline_handoff_planning.json"
        readiness_report_path = build_dir / "outline_handoff_readiness.json"
        advance_report_path = build_dir / "outline_handoff_advance.json"
        advance_next_action_path = build_dir / "outline_handoff_workspace_next_action.md"
        build_report_path = build_dir / "outline_handoff_build_report.json"
        qa_outdir = build_dir / "outline_handoff_qa"
        qa_report_path = qa_outdir / "report.json"

        _run_checked(
            [
                py,
                str(repo / "scripts" / "emit_outline_authoring_prompt.py"),
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
        seed = _style_seed(workspace)
        if "outline_authoring_handoff_v1" not in prompt_text or seed not in prompt_text:
            failures.append({"step": "emit_outline_authoring_prompt", "reason": "prompt_missing_handoff_or_seed"})
        if (
            "Slide quality contract:" not in prompt_text
            or "slide_quality_contract_v1" not in prompt_text
            or '"quality_alignment"' not in prompt_text
        ):
            failures.append({"step": "emit_outline_authoring_prompt", "reason": "prompt_missing_quality_alignment"})

        _write_json(handoff_path, _outline_handoff(workspace=workspace, seed=seed))
        for cmd in (
            [
                py,
                str(repo / "scripts" / "apply_outline_authoring_handoff.py"),
                "--workspace",
                str(workspace),
                "--handoff",
                str(handoff_path),
                "--report",
                str(apply_report_path),
            ],
            [
                py,
                str(repo / "scripts" / "apply_outline_authoring_handoff.py"),
                "--workspace",
                str(workspace),
                "--handoff",
                str(handoff_path),
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
            [
                py,
                str(repo / "scripts" / "report_workspace_readiness.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(readiness_report_path),
            ],
            [
                py,
                str(repo / "scripts" / "advance_workspace.py"),
                "--workspace",
                str(workspace),
                "--report",
                str(advance_report_path),
                "--readiness-report",
                str(readiness_report_path),
                "--next-action-markdown",
                str(advance_next_action_path),
            ],
            [
                py,
                str(repo / "scripts" / "build_workspace.py"),
                "--workspace",
                str(workspace),
                "--skip-render",
                "--overwrite",
                "--build-report",
                str(build_report_path),
            ],
        ):
            _run_checked(cmd, cwd=repo, command_results=command_results, failures=failures)

        build_report = _load_json(build_report_path)
        pptx_path = _workspace_output_pptx(workspace, build_report if isinstance(build_report, dict) else {})
        _run_checked(
            [
                py,
                str(repo / "scripts" / "qa_gate.py"),
                "--input",
                str(pptx_path),
                "--outdir",
                str(qa_outdir),
                "--style-preset",
                "lab-report",
                "--outline",
                str(workspace / "outline.json"),
                "--design-brief",
                str(workspace / "design_brief.json"),
                "--strict-geometry",
                "--skip-render",
                "--skip-manual-review",
                "--fail-on-whitespace-warnings",
                "--fail-on-design-warnings",
                "--report",
                str(qa_report_path),
            ],
            cwd=repo,
            command_results=command_results,
            failures=failures,
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
        build_report = _load_json(build_report_path)
        qa_report = _load_json(qa_report_path)
        _assert_outline_state(
            workspace=workspace,
            apply_report=apply_report if isinstance(apply_report, dict) else {},
            repeat_report=repeat_report if isinstance(repeat_report, dict) else {},
            planning=planning if isinstance(planning, dict) else {},
            readiness=readiness if isinstance(readiness, dict) else {},
            build_report=build_report if isinstance(build_report, dict) else {},
            qa_report=qa_report if isinstance(qa_report, dict) else {},
            failures=failures,
        )
        _assert_advance_quality_context(
            advance=advance if isinstance(advance, dict) else {},
            next_action_text=advance_next_action_text,
            failures=failures,
        )

        outline = _load_json(workspace / "outline.json")
        handoff_summary = (
            readiness.get("outline_authoring_handoff", {})
            if isinstance(readiness, dict) and isinstance(readiness.get("outline_authoring_handoff"), dict)
            else {}
        )
        readiness_quality_context = (
            readiness.get("quality_context", {})
            if isinstance(readiness, dict) and isinstance(readiness.get("quality_context"), dict)
            else {}
        )
        readiness_outline_quality = (
            readiness_quality_context.get("outline_quality_alignment", {})
            if isinstance(readiness_quality_context.get("outline_quality_alignment"), dict)
            else {}
        )
        advance_quality = (
            advance.get("quality_context", {})
            if isinstance(advance, dict) and isinstance(advance.get("quality_context"), dict)
            else {}
        )
        advance_outline_quality = (
            advance_quality.get("outline_quality_alignment", {})
            if isinstance(advance_quality.get("outline_quality_alignment"), dict)
            else {}
        )
        passed = not failures
        summary = {
            "passed": passed,
            "workspace": str(workspace),
            "style_seed": seed,
            "prompt_contains_handoff_shape": "outline_authoring_handoff_v1" in prompt_text,
            "prompt_contains_quality_alignment": "slide_quality_contract_v1" in prompt_text and '"quality_alignment"' in prompt_text,
            "apply_changed_file_count": apply_report.get("changed_file_count") if isinstance(apply_report, dict) else None,
            "repeat_changed_file_count": repeat_report.get("changed_file_count") if isinstance(repeat_report, dict) else None,
            "quality_alignment_applied": apply_report.get("quality_alignment_applied") if isinstance(apply_report, dict) else None,
            "planning_counts": {
                "errors": planning.get("error_count") if isinstance(planning, dict) else None,
                "warnings": planning.get("warning_count") if isinstance(planning, dict) else None,
            },
            "readiness_status": readiness.get("status") if isinstance(readiness, dict) else None,
            "outline_handoff_status": handoff_summary.get("status"),
            "readiness_outline_quality_contract_version": readiness_outline_quality.get("contract_version"),
            "advance_decision": advance.get("decision") if isinstance(advance, dict) else None,
            "advance_outline_quality_contract_version": advance_outline_quality.get("contract_version"),
            "next_action_contains_quality_context": "## Quality Context" in advance_next_action_text
            and "Outline quality alignment:" in advance_next_action_text,
            "slide_count": len(outline.get("slides", [])) if isinstance(outline, dict) and isinstance(outline.get("slides"), list) else 0,
            "pptx": build_report.get("outputs", {}).get("pptx") if isinstance(build_report.get("outputs"), dict) else {},
            "qa_counts": {
                "overflow": qa_report.get("overflow_count") if isinstance(qa_report, dict) else None,
                "overlap": qa_report.get("overlap_count") if isinstance(qa_report, dict) else None,
                "whitespace_warnings": qa_report.get("whitespace_warning_count") if isinstance(qa_report, dict) else None,
                "design_warnings": qa_report.get("design_warning_count") if isinstance(qa_report, dict) else None,
            },
            "failures": failures,
            "commands": command_results,
        }
        (build_dir / "outline_authoring_handoff_smoke.json").write_text(
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
                        "style_seed",
                        "prompt_contains_handoff_shape",
                        "prompt_contains_quality_alignment",
                        "apply_changed_file_count",
                        "repeat_changed_file_count",
                        "quality_alignment_applied",
                        "planning_counts",
                        "readiness_status",
                        "outline_handoff_status",
                        "readiness_outline_quality_contract_version",
                        "advance_decision",
                        "advance_outline_quality_contract_version",
                        "next_action_contains_quality_context",
                        "slide_count",
                        "qa_counts",
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
            (build_dir / "outline_authoring_handoff_smoke.json").write_text(
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
