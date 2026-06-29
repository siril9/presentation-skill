#!/usr/bin/env python3
"""Fast smoke check for style/content router prompt reference context."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_fixture_workspace(workspace: Path) -> None:
    (workspace / "data").mkdir(parents=True, exist_ok=True)
    (workspace / "data" / "readout.csv").write_text(
        "Sample,Condition,Signal,Ct\nA01,case,42.1,18.2\nA02,control,12.4,31.8\n",
        encoding="utf-8",
    )
    _write_json(
        workspace / "design_brief.json",
        {
            "style_system": {
                "style_preset": "lab-report",
                "style_seed": "style-router-smoke-lab",
            },
            "readability_contract": {
                "max_slide_text_lines": 8,
                "max_slide_words": 105,
                "max_slide_chars": 700,
                "max_title_lines": 2,
                "chart_label_min_pt": 8,
                "footer_reserved_inches": 0.34,
            },
            "analysis_artifact_plan": {
                "data_inputs": ["data/readout.csv"],
                "artifact_manifest": "assets/artifacts_manifest.json",
                "analysis_summary": "assets/analysis_summary.json",
                "artifact_registry": [],
            },
        },
    )
    _write_json(
        workspace / "content_plan.json",
        {
            "thesis": "CSV-derived assay readouts need a reproducible lab report route.",
            "slide_plan": [
                {"slide_id": "s2", "role": "evidence", "visual_strategy": "generated figure"},
                {"slide_id": "s3", "role": "result table", "visual_strategy": "summary table"},
            ],
        },
    )
    _write_json(
        workspace / "evidence_plan.json",
        {
            "source_policy": "Use source-line footers with short IDs and final references.",
            "items": [
                {
                    "id": "ev_signal",
                    "claim": "Signal differs between case and control.",
                    "visual_use": "chart",
                    "used_on_slides": ["s2"],
                }
            ],
            "chart_candidates": [
                {
                    "id": "signal_chart",
                    "target_slide": "s2",
                    "source_ids": ["ev_signal"],
                    "data_path": "data/readout.csv",
                }
            ],
        },
    )
    _write_json(
        workspace / "asset_plan.json",
        {
            "charts": [{"name": "signal_chart", "path": "assets/charts/signal_chart.json"}],
            "tables": [{"name": "signal_summary", "path": "assets/tables/signal_summary.json"}],
            "images": [{"name": "signal_figure", "path": "assets/figures/signal_figure.png"}],
        },
    )
    _write_json(
        workspace / "outline.json",
        {
            "title": "Style Router Smoke",
            "deck_style": {"footer_mode": "source-line", "header_mode": "lab-clean"},
            "slides": [
                {"type": "title", "slide_id": "s1", "title": "Style Router Smoke"},
                {
                    "type": "content",
                    "variant": "scientific-figure",
                    "slide_id": "s2",
                    "title": "Assay signal figure",
                    "treatment_key": "figure",
                    "slide_intent": "evidence",
                    "visual_intent": "figure",
                    "evidence_needs": ["signal_chart"],
                    "sources": ["data/readout.csv"],
                },
                {
                    "type": "content",
                    "variant": "lab-run-results",
                    "slide_id": "s3",
                    "title": "Run summary table",
                    "treatment_key": "table",
                    "slide_intent": "evidence",
                    "visual_intent": "table",
                    "evidence_needs": ["signal_chart"],
                    "sources": ["data/readout.csv"],
                },
            ],
        },
    )
    (workspace / "notes.md").write_text(
        "Router should choose the clean assay report reference and preserve CSV artifact reproducibility.\n",
        encoding="utf-8",
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        default="",
        help="Empty workspace path to create/use. Defaults to a temporary workspace.",
    )
    parser.add_argument("--keep-workspace", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    repo = Path(__file__).resolve().parent.parent
    created_temp = not bool(str(args.workspace).strip())
    workspace = (
        Path(args.workspace).expanduser().resolve()
        if str(args.workspace).strip()
        else Path(tempfile.mkdtemp(prefix="presentation-skill-style-router-"))
    )
    failures: list[dict[str, Any]] = []
    if not created_temp and workspace.exists() and any(workspace.iterdir()):
        failures.append({"step": "workspace", "reason": "workspace_must_be_empty_or_absent"})
    workspace.mkdir(parents=True, exist_ok=True)
    prompt_path = workspace / "style_content_router_prompt.txt"
    command_results: list[dict[str, Any]] = []
    if not failures:
        _write_fixture_workspace(workspace)
        cmd = [
            sys.executable,
            str(repo / "scripts" / "emit_style_content_router.py"),
            "--workspace",
            str(workspace),
            "--user-prompt",
            (
                "Build a lab assay validation report deck from CSV data with reusable "
                "figures, editable charts, summary tables, compact source-line footers, "
                "and final refs."
            ),
            "--output",
            str(prompt_path),
        ]
        result = _run(cmd, cwd=repo)
        command_results.append(
            {
                "command": cmd,
                "returncode": result.returncode,
                "stdout_tail": result.stdout[-1200:],
            }
        )
        prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        required_tokens = {
            "Prompt-to-style reference matches",
            "style_reference_selection",
            "style_reference_mix_plan_v1",
            "style_reference_layout_playbook_v1",
            "style_reference_content_recipe_library_v1",
            "style_inspiration_corpus",
            "style_inspiration_corpus_v1",
            "descriptor_only_no_raw_decks",
            "style_inspiration_corpus_used",
            "style_inspiration_subagent_contract_v1",
            "style_reference_preset_contact_collection_v1",
            "preset_contact_collection_contract",
            "preset_contact_collection_use_cases",
            "overview",
            "data_evidence",
            "decision_sources",
            "ref-clean-assay-report",
            "Clean Assay Report",
            "renderer_treatment_signature",
            "renderer_treatment_defaults",
            "structural_motif_library",
            "style_reference_structural_motif_library_v1",
            "style_metric_profile",
            "style_reference_metric_profile_v1",
            "style_metric_signature",
            "whitespace_ratio_target",
            "body_words_per_content_slide",
            "evidence_object_mix",
            "Normal-workflow atom context",
            "normal_workflow_atom_context_v1",
            "atom_composition_route",
            "style_atom_composition",
            "Use strict JSON only",
            "preferred_variants",
            "narrative_arc",
            "footer_reference_contract",
            "style_reference_footer_reference_contract_v1",
            "source_footer_contract",
            "report_structure_contract",
            "style_reference_report_structure_contract_v1",
            "page_number_policy",
            "bottom-right page number",
            "final editable references table",
            "run metadata plate",
            "semantic result table",
            "style_source_intake",
            "generic_style_observations",
            "generic_slide_patterns",
            "cdc_agency_materials_guidance",
            "carbon_charts_design_guidance",
            "cfpb_data_visualization_guidance",
            "section508_accessible_presentations",
            "chart_treatment_pool",
            "table_treatment_pool",
            "figure_table_treatment_pool",
            "layout_playbook",
            "content_recipe_library",
            "treatment_variant_map",
            "treatment_mix_used",
            "scientific-figure",
            "lab-run-results",
            "data_artifact_workflow",
            "assets/artifacts_manifest.json",
            "assets/analysis_summary.json",
        }
        missing_tokens = sorted(token for token in required_tokens if token not in prompt)
        if result.returncode != 0:
            failures.append({"step": "emit_router", "reason": "nonzero_returncode", "returncode": result.returncode})
        if not prompt_path.exists():
            failures.append({"step": "emit_router", "reason": "prompt_not_written"})
        if missing_tokens:
            failures.append({"step": "prompt_contract", "reason": "missing_tokens", "missing": missing_tokens})

    passed = not failures
    summary = {
        "passed": passed,
        "workspace": str(workspace),
        "prompt": str(prompt_path),
        "prompt_chars": len(prompt_path.read_text(encoding="utf-8")) if prompt_path.exists() else 0,
        "failures": failures,
        "commands": command_results,
    }
    (workspace / "style_content_router_smoke.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: summary[key]
                for key in ("passed", "workspace", "prompt", "prompt_chars", "failures")
            },
            indent=2,
        )
    )
    if created_temp and passed and not args.keep_workspace:
        shutil.rmtree(workspace, ignore_errors=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
