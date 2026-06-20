#!/usr/bin/env python3
"""Build release evidence decks for native vs v1 vs v1.1 comparisons."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = Path("/private/tmp/presentation-skill-ab-baseline-20260616")
NATIVE_SKILL = Path(
    "/Users/sirilarockiam/.codex/plugins/cache/openai-primary-runtime/"
    "presentations/26.619.11828/skills/presentations"
)
NATIVE_NODE = Path(
    "/Users/sirilarockiam/.cache/codex-runtimes/codex-primary-runtime/"
    "dependencies/node/bin/node"
)


@dataclass(frozen=True)
class Case:
    slug: str
    title: str
    short: str
    preset: str
    dna: str
    topic: str
    key_title: str
    key_subtitle: str
    left_title: str
    left_body: list[str]
    right_title: str
    right_body: list[str]
    verdict: str
    metrics: list[tuple[str, str, str]]
    action_rows: list[list[str]]
    v11_header: str


CASES: list[Case] = [
    Case(
        slug="lab-report-assay",
        title="Assay Readout Triage",
        short="Lab report",
        preset="lab-report",
        dna="lab results dashboard",
        topic="Synthetic assay readout triage for a 96-sample plate",
        key_title="Borderline calls need repeat wells, not a new protocol",
        key_subtitle="Same synthetic run summary; style is the variable under test.",
        left_title="Raw screen",
        left_body=["96 samples loaded", "3 controls pass", "7 borderline wells"],
        right_title="Report-ready readout",
        right_body=["Repeat only borderline wells", "Keep source IDs in footer", "Move full protocol to refs"],
        verdict="Decision: repeat 7 wells and keep the run valid.",
        metrics=[("96", "Samples", "Single synthetic plate"), ("7", "Borderline", "Repeat queue"), ("3/3", "Controls", "Passed")],
        action_rows=[
            ["Repeat wells", "Borderline signal", "Next run"],
            ["Keep plate", "Controls pass", "No rerun"],
            ["Compact refs", "Footer stays readable", "Use IDs"],
        ],
        v11_header="top-bottom-rule",
    ),
    Case(
        slug="board-risk-memo",
        title="Factory Line Risk Memo",
        short="Risk memo",
        preset="charcoal-safety",
        dna="board risk memo",
        topic="Synthetic factory-line risk review",
        key_title="Downtime risk concentrates in one inspection step",
        key_subtitle="The board needs the owner, trigger, and mitigation in one view.",
        left_title="Current exposure",
        left_body=["Inspection queue spikes after shift change", "Manual signoff adds delay", "Escalation path is unclear"],
        right_title="Controlled response",
        right_body=["Assign single owner", "Trigger review at 18 min queue age", "Add daily exception table"],
        verdict="Decision: make inspection queue age the control metric.",
        metrics=[("18m", "Queue trigger", "Escalate"), ("2", "Owner roles", "Named"), ("24h", "Review loop", "Daily")],
        action_rows=[
            ["Queue trigger", "18 minutes", "Line lead"],
            ["Exception log", "Daily", "Ops analyst"],
            ["Board update", "Weekly", "Plant GM"],
        ],
        v11_header="split-rule",
    ),
    Case(
        slug="startup-launch",
        title="Battery Recycling Launch",
        short="Startup",
        preset="bold-startup-narrative",
        dna="product/investor reveal",
        topic="Synthetic launch brief for a battery recycling pilot",
        key_title="Pilot economics improve when intake is sorted upstream",
        key_subtitle="The same business case should feel like a launch story, not a report template.",
        left_title="Unsorted intake",
        left_body=["Wide chemistry mix", "Lower recovery consistency", "More manual triage"],
        right_title="Sorted intake",
        right_body=["Cleaner feedstock", "Higher recovery confidence", "Faster partner onboarding"],
        verdict="Decision: launch with sorted partner intake first.",
        metrics=[("14%", "Yield lift", "Synthetic model"), ("6wk", "Pilot window", "Phase 1"), ("3", "Partners", "Initial lane")],
        action_rows=[
            ["Partner A", "Sorted intake", "Start"],
            ["Partner B", "Chemistry audit", "Prep"],
            ["Partner C", "Volume forecast", "Hold"],
        ],
        v11_header="left-accent",
    ),
    Case(
        slug="editorial-field-note",
        title="Rooftop Field Notes",
        short="Editorial",
        preset="paper-journal",
        dna="editorial report",
        topic="Synthetic urban rooftop field-note summary",
        key_title="Three roof surfaces create three different microclimates",
        key_subtitle="The editorial style should stay warm without becoming a brochure.",
        left_title="Observed pattern",
        left_body=["Black membrane heats fastest", "Gravel roof holds evening warmth", "Planter zone buffers peak heat"],
        right_title="Design implication",
        right_body=["Shade high-heat surfaces", "Stage planters near access paths", "Use simple monitoring tags"],
        verdict="Decision: prioritize planter placement over new hardware.",
        metrics=[("3", "Roof zones", "Compared"), ("11F", "Peak spread", "Synthetic"), ("2", "Low-cost fixes", "Near term")],
        action_rows=[
            ["Planter zone", "Cooler peak", "Expand"],
            ["Black membrane", "Hot peak", "Shade"],
            ["Gravel edge", "Warm evening", "Monitor"],
        ],
        v11_header="plain",
    ),
    Case(
        slug="civic-policy",
        title="Watershed Policy Brief",
        short="Policy",
        preset="forest-research",
        dna="civic science policy",
        topic="Synthetic watershed restoration policy brief",
        key_title="Small upstream fixes reduce downstream intervention load",
        key_subtitle="The policy deck needs plain-language tradeoffs and visible evidence structure.",
        left_title="Reactive plan",
        left_body=["Downstream treatment remains overloaded", "Costs arrive late", "Benefits are harder to attribute"],
        right_title="Preventive plan",
        right_body=["Upstream buffers reduce sediment load", "Monitoring is simpler", "Benefits show earlier"],
        verdict="Decision: fund upstream buffer pilots before plant expansion.",
        metrics=[("22%", "Load cut", "Synthetic estimate"), ("4", "Pilot sites", "Phase 1"), ("9mo", "Signal window", "Review")],
        action_rows=[
            ["Pilot buffers", "4 sites", "Watershed team"],
            ["Sensor check", "Monthly", "Field ops"],
            ["Council memo", "Quarterly", "Policy lead"],
        ],
        v11_header="title-rule",
    ),
    Case(
        slug="ops-dashboard",
        title="Support Queue Ops Review",
        short="Ops dashboard",
        preset="data-heavy-boardroom",
        dna="operational dashboard",
        topic="Synthetic support queue operations review",
        key_title="Backlog drops only when triage rules are explicit",
        key_subtitle="A dense operations deck still needs readable hierarchy and clean whitespace.",
        left_title="Loose triage",
        left_body=["Priority tags drift", "Aging tickets hide in the queue", "Escalations arrive late"],
        right_title="Structured triage",
        right_body=["Priority tags map to SLA", "Aging tickets surface daily", "Escalation has a named owner"],
        verdict="Decision: lock triage rules before hiring more coverage.",
        metrics=[("31%", "Backlog cut", "Synthetic"), ("48h", "Age trigger", "Escalate"), ("5", "SLA bands", "Defined")],
        action_rows=[
            ["SLA tags", "Define", "Ops lead"],
            ["Age trigger", "48 hours", "Queue owner"],
            ["Review table", "Daily", "Support manager"],
        ],
        v11_header="side-rail",
    ),
    Case(
        slug="clinical-pathway",
        title="Care Pathway Review",
        short="Clinical exec",
        preset="executive-clinical",
        dna="executive clinical operating review",
        topic="Synthetic outpatient follow-up pathway review",
        key_title="Missed follow-ups concentrate after discharge handoff",
        key_subtitle="The clinical executive style should feel precise, calm, and operational.",
        left_title="Current handoff",
        left_body=["Discharge tasks split across teams", "Follow-up reminders arrive late", "Owner is unclear after day 3"],
        right_title="Closed-loop handoff",
        right_body=["Assign pathway owner", "Trigger reminder within 48 hours", "Escalate unresolved calls daily"],
        verdict="Decision: make post-discharge ownership explicit.",
        metrics=[("48h", "Reminder trigger", "Synthetic pathway"), ("12%", "Missed follow-up", "Review cohort"), ("3", "Owner roles", "Named")],
        action_rows=[
            ["Owner map", "Handoff gap", "Clinic ops"],
            ["Reminder trigger", "48 hours", "Care team"],
            ["Escalation log", "Daily misses", "Program lead"],
        ],
        v11_header="top-bottom-rule",
    ),
    Case(
        slug="arctic-postmortem",
        title="Incident Postmortem Brief",
        short="Arctic minimal",
        preset="arctic-minimal",
        dna="minimal technical postmortem",
        topic="Synthetic service incident postmortem",
        key_title="Recovery slowed because ownership changed mid-incident",
        key_subtitle="The arctic style should preserve white space while staying concrete.",
        left_title="Unclear response",
        left_body=["Alert context was split", "Triage owner changed twice", "Rollback criteria were implicit"],
        right_title="Clear response",
        right_body=["Single incident owner", "Pinned rollback rule", "Status cadence every 20 minutes"],
        verdict="Decision: publish an owner-first incident checklist.",
        metrics=[("20m", "Status cadence", "Synthetic incident"), ("2", "Owner changes", "Avoid next time"), ("1", "Rollback rule", "Pinned")],
        action_rows=[
            ["Owner handoff", "Avoid drift", "SRE lead"],
            ["Rollback rule", "Reduce debate", "Platform"],
            ["Status cadence", "Every 20 min", "Incident owner"],
        ],
        v11_header="plain",
    ),
    Case(
        slug="midnight-cyber-triage",
        title="Cyber Triage Console",
        short="Midnight neon",
        preset="midnight-neon",
        dna="security operations console",
        topic="Synthetic security alert triage review",
        key_title="Alert volume falls when enrichment happens before escalation",
        key_subtitle="The neon style should feel energetic without hiding operational detail.",
        left_title="Raw alerts",
        left_body=["Rules fire before enrichment", "Analysts chase duplicate hosts", "Escalation notes vary"],
        right_title="Enriched alerts",
        right_body=["Host context is attached", "Duplicates collapse automatically", "Escalation note format is fixed"],
        verdict="Decision: enrich before analyst escalation.",
        metrics=[("37%", "Alert cut", "Synthetic queue"), ("14m", "Triage saved", "Per incident"), ("5", "Fields", "Required")],
        action_rows=[
            ["Enrich hosts", "Reduce duplicates", "SOC engineer"],
            ["Note template", "Faster handoff", "IR lead"],
            ["Queue review", "Daily drift", "Detection owner"],
        ],
        v11_header="side-rail",
    ),
    Case(
        slug="sunset-investor-memo",
        title="Solar Storage Investor Memo",
        short="Investor",
        preset="sunset-investor",
        dna="investor memo",
        topic="Synthetic solar storage expansion memo",
        key_title="Margin expands when storage dispatch is software-led",
        key_subtitle="The investor style should feel confident but still evidence-led.",
        left_title="Hardware-led plan",
        left_body=["Dispatch rules stay static", "Peak pricing capture varies", "Field ops owns too much tuning"],
        right_title="Software-led plan",
        right_body=["Dispatch rules update weekly", "Peak windows are forecasted", "Ops gets exception reports"],
        verdict="Decision: fund software dispatch before adding capacity.",
        metrics=[("19%", "Margin lift", "Synthetic model"), ("8wk", "Pilot length", "Phase 1"), ("4", "Sites", "Initial cohort")],
        action_rows=[
            ["Dispatch model", "Margin lever", "Product"],
            ["Pilot sites", "4 locations", "Ops"],
            ["Investor update", "After 8 weeks", "Finance"],
        ],
        v11_header="title-rule",
    ),
    Case(
        slug="lavender-renewal-ops",
        title="SaaS Renewal Ops Review",
        short="Lavender ops",
        preset="lavender-ops",
        dna="customer operations review",
        topic="Synthetic SaaS renewal operations review",
        key_title="Renewal risk shows up in usage decay before ticket volume",
        key_subtitle="The lavender style should stay polished, calm, and workflow-focused.",
        left_title="Ticket-led view",
        left_body=["Escalations arrive late", "Usage decay hides in dashboards", "CSM notes are inconsistent"],
        right_title="Usage-led view",
        right_body=["Decay flags weekly", "CSM action is triggered early", "Renewal notes follow one schema"],
        verdict="Decision: trigger renewal work from usage decay.",
        metrics=[("16%", "Risk drop", "Synthetic cohort"), ("30d", "Early signal", "Before renewal"), ("6", "Fields", "CSM schema")],
        action_rows=[
            ["Usage flag", "Early signal", "RevOps"],
            ["CSM schema", "Cleaner handoff", "Success lead"],
            ["Renewal review", "Weekly", "Account team"],
        ],
        v11_header="split-rule",
    ),
    Case(
        slug="terracotta-membership",
        title="Museum Membership Plan",
        short="Terracotta",
        preset="warm-terracotta",
        dna="cultural membership planning",
        topic="Synthetic museum membership growth plan",
        key_title="Membership growth improves when visits become return rituals",
        key_subtitle="The terracotta style should feel warm without becoming decorative.",
        left_title="Single-visit push",
        left_body=["Campaigns emphasize discounts", "Return visits are not sequenced", "Member events feel generic"],
        right_title="Return ritual",
        right_body=["Visit two is scheduled", "Member nights match interests", "Renewal copy references attendance"],
        verdict="Decision: build membership around the second visit.",
        metrics=[("24%", "Return lift", "Synthetic cohort"), ("2", "Visit trigger", "Core ritual"), ("5", "Event themes", "Pilot")],
        action_rows=[
            ["Second visit", "Return ritual", "Membership"],
            ["Theme nights", "Interest match", "Programs"],
            ["Renewal copy", "Attendance cue", "Comms"],
        ],
        v11_header="left-accent",
    ),
    Case(
        slug="editorial-minimal-brief",
        title="Magazine Audience Brief",
        short="Editorial minimal",
        preset="editorial-minimal",
        dna="minimal editorial strategy",
        topic="Synthetic magazine audience strategy brief",
        key_title="Reader loyalty rises when recurring columns anchor discovery",
        key_subtitle="The minimal editorial style should feel sharp, spacious, and deliberate.",
        left_title="Loose discovery",
        left_body=["Feature mix changes weekly", "Readers lack a return habit", "Newsletter links are broad"],
        right_title="Column-led discovery",
        right_body=["Recurring columns set cadence", "Newsletter links map to habits", "Editors track repeat reads"],
        verdict="Decision: anchor discovery around recurring columns.",
        metrics=[("28%", "Repeat read lift", "Synthetic audience"), ("4", "Columns", "Weekly anchors"), ("2", "Signals", "Track")],
        action_rows=[
            ["Column slate", "Cadence", "Editorial"],
            ["Newsletter map", "Return path", "Audience"],
            ["Repeat reads", "Loyalty signal", "Analytics"],
        ],
        v11_header="plain",
    ),
]


def run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(cmd), f"(cwd={cwd})", flush=True)
    result = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    if result.stdout.strip():
        print(result.stdout[-6000:], flush=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def showcase_metrics(case: Case) -> list[tuple[str, str, str]]:
    """Use two KPIs so the same fixture stays readable in all generators."""
    return case.metrics[:2]


def metric_number(value: str) -> float:
    cleaned = "".join(ch for ch in value if ch.isdigit() or ch in ".-")
    if not cleaned or cleaned in {".", "-", "-."}:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def ensure_baseline() -> Path:
    if DEFAULT_BASELINE.exists():
        if not (DEFAULT_BASELINE / "scripts" / "build_workspace.py").exists():
            raise RuntimeError(f"baseline path exists but is not a presentation-skill worktree: {DEFAULT_BASELINE}")
    else:
        run(["git", "fetch", "origin", "main"], ROOT)
        run(["git", "worktree", "add", "--detach", str(DEFAULT_BASELINE), "origin/main"], ROOT)
    baseline_node_modules = DEFAULT_BASELINE / "node_modules"
    if not baseline_node_modules.exists():
        baseline_node_modules.symlink_to(ROOT / "node_modules")
    return DEFAULT_BASELINE


def base_outline(case: Case, version: str) -> dict[str, Any]:
    style: dict[str, Any] = {"visual_density": "medium", "emoji_mode": "none"}
    if version == "v1.1":
        style.update(
            {
                "style_seed": f"{case.slug}-v11-release",
                "header_mode": "lab-clean",
                "header_variant": "auto",
                "header_variants": unique([case.v11_header, "split-rule", "plain", "left-accent", "title-rule"]),
                "footer_mode": "source-line",
                "footer_source_label": "Src",
                "footer_refs_label": "Refs",
                "footer_page_numbers": True,
                "chart_treatment": "facts-right",
                "summary_callout_mode": "lab-box",
                "figure_table_treatment": "table-first",
            }
        )
    slides: list[dict[str, Any]] = [
        {
            "slide_id": "s1",
            "type": "title",
            "title": case.title,
            "subtitle": f"{case.short} case generated with {version}",
        },
        {
            "slide_id": "s2",
            "type": "content",
            "variant": "comparison-2col",
            "slide_intent": "evidence",
            "visual_intent": "comparison",
            "header_variant": case.v11_header if version == "v1.1" else None,
            "title": case.key_title,
            "subtitle": case.key_subtitle,
            "left": {"title": case.left_title, "body": case.left_body},
            "right": {"title": case.right_title, "body": case.right_body},
            "verdict": case.verdict,
            "sources": ["S1"] if version == "v1.1" else ["Synthetic release case"],
            "refs": [version],
        },
        {
            "slide_id": "s3",
            "type": "content",
            "variant": "chart" if version == "v1.1" else "stats",
            "slide_intent": "evidence",
            "visual_intent": "data",
            "header_variant": "split-rule" if version == "v1.1" else None,
            "title": "Metrics that should stay readable",
            "subtitle": (
                "The same synthetic readouts exercise editable chart structure."
                if version == "v1.1"
                else "The same synthetic readouts exercise KPI hierarchy and detail text."
            ),
            **(
                {
                    "chart_treatment": "minimal",
                    "chart": {
                        "type": "bar",
                        "title": "Synthetic readout comparison",
                        "categories": [label for _value, label, _detail in showcase_metrics(case)],
                        "series": [
                            {
                                "name": "Fixture value",
                                "values": [metric_number(value) for value, _label, _detail in showcase_metrics(case)],
                            }
                        ],
                        "options": {
                            "catAxisTitle": "Readout",
                            "valAxisTitle": "Value",
                            "showLegend": False,
                        },
                        "facts": [
                            {"value": value, "label": label, "detail": detail, "caption": detail}
                            for value, label, detail in showcase_metrics(case)
                        ],
                    },
                    "caption": "Synthetic values; units remain in slide labels and source notes.",
                }
                if version == "v1.1"
                else {
                    "facts": [
                        {"value": value, "label": label, "detail": detail, "caption": detail}
                        for value, label, detail in showcase_metrics(case)
                    ],
                }
            ),
            "sources": ["S1"] if version == "v1.1" else ["Synthetic release case"],
            "refs": [version],
        },
        {
            "slide_id": "s4",
            "type": "content",
            "variant": "table",
            "slide_intent": "decision",
            "visual_intent": "data",
            "header_variant": "plain" if version == "v1.1" else None,
            "title": "Decision table keeps the next step explicit",
            "subtitle": "A release deck should show useful structure, not just prettier cards.",
            "headers": ["Action", "Reason", "Owner/status"],
            "rows": case.action_rows,
            "column_weights": [0.9, 1.35, 0.95],
            "caption": "Synthetic values and labels for release demonstration.",
            "sources": ["S1"] if version == "v1.1" else ["Synthetic release case"],
            "refs": [version],
        },
    ]
    if version == "v1.1" and case.slug == "editorial-minimal-brief":
        slides[1].update(
            {
                "variant": "split",
                "slide_intent": "comparison",
                "visual_intent": "split",
                "body": "Loose discovery changes the feature mix weekly. Readers lack a reliable return habit. Broad newsletter links dilute the editorial path.",
                "highlights": [
                    "Recurring columns set cadence",
                    "Newsletter links map to habits",
                    "Editors track repeat reads",
                ],
            }
        )
        slides[1].pop("left", None)
        slides[1].pop("right", None)
        slides[1].pop("verdict", None)
    for slide in slides:
        if slide.get("header_variant") is None:
            slide.pop("header_variant", None)
    return {
        "title": case.title,
        "subtitle": f"{case.short} release showcase",
        "deck_style": style,
        "slides": slides,
    }


def design_brief(case: Case, version: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "topic": case.title,
        "content_maturity": "technical/educational" if case.preset == "lab-report" else "serious/work",
        "audience_posture": "coworkers/operators",
        "emotional_register": "trustworthy",
        "design_dna": case.dna,
        "format_promise": f"{case.short} release showcase deck for {version}.",
        "anti_format": [
            "generic repeated card grids",
            "unsupported claims outside the synthetic source case",
            "shrinking text instead of simplifying content",
        ],
        "canvas_and_grid": {
            "aspect": "16:9",
            "margin_x_in": 0.5,
            "footer_reserve_in": 0.34,
            "header_policy": "measured header with body below",
        },
        "visual_system": {
            "style_preset": case.preset,
            "dominant_color": "0B2545",
            "accent_primary": "0B6B78",
            "accent_secondary": "C9302C",
        },
        "title_page_concept": {
            "chosen_archetype": "preset-specific opener",
            "dominant_element": case.title,
            "supporting_element": f"{case.short} version label",
            "why_this_could_only_be_this_deck": case.topic,
        },
        "structure_strategy": {
            "primary_scaffold": "title, comparison, chart, decision table",
            "repeated_elements": ["same synthetic message", "same slide count", "same version label"],
            "allowed_variations": ["title", "comparison-2col", "chart", "table"],
            "container_policy": "Use cards only when the content is truly modular.",
            "rhythm_break_plan": "The chart slide is the primary rhythm break.",
        },
    }
    if version == "v1.1":
        payload.update(
            {
                "style_system": {
                    "style_preset": case.preset,
                    "style_seed": f"{case.slug}-v11-release",
                    "background_system": "preset-specific",
                    "style_mix_matrix": {
                        "header_variant_pool": unique([case.v11_header, "split-rule", "plain", "left-accent", "title-rule"]),
                        "chart_treatment_pool": ["facts-right", "minimal"],
                        "figure_table_treatment_pool": ["table-first", "stats-strip"],
                        "footer_pool": ["source-line", "standard"],
                        "summary_callout_mode_pool": ["lab-box", "default"],
                        "mix_rule": "Use restrained treatment variation while locking story structure.",
                        "do_not_mix": ["Do not turn release evidence into random layout cycling."],
                    },
                },
                "readability_contract": {
                    "min_title_pt": 24,
                    "min_body_pt": 12,
                    "min_caption_pt": 7.5,
                    "max_title_lines": 2,
                    "max_slide_text_lines": 8,
                    "max_slide_words": 105,
                    "max_slide_chars": 700,
                    "footer_reserved_inches": 0.34,
                    "chart_label_min_pt": 8,
                    "table_density_rule": "Keep tables short enough to inspect in screenshots.",
                    "whitespace_rule": "Avoid awkward empty regions; make comparison panels and tables fill the usable space.",
                    "figure_crop_rule": "Not applicable for source-only release fixtures.",
                },
                "analysis_artifact_plan": {
                    "candidate_data_files": [],
                    "spreadsheet_inputs": [],
                    "required_scripts": [],
                    "figure_scripts": [],
                    "artifact_manifest": "",
                    "analysis_summary": "",
                    "analysis_summary_markdown": "",
                    "chart_json_outputs": [],
                    "table_outputs": [],
                    "rebuild_commands": [],
                    "artifact_registry": [],
                },
                "speed_contract": {
                    "renderer": "pptxgenjs by default",
                    "first_pass": "workspace build with QA",
                    "render_policy": "render every showcase deck for screenshot comparison",
                    "asset_policy": "no network assets for reproducible release evidence",
                    "conversion_hint": "use local LibreOffice render path",
                },
            }
        )
    return payload


def content_plan(case: Case, version: str) -> dict[str, Any]:
    comparison_variant = "split" if version == "v1.1" and case.slug == "editorial-minimal-brief" else "comparison-2col"
    return {
        "topic": case.title,
        "audience": "HN/GitHub release reviewers comparing deck generation quality.",
        "objective": f"Show the {version} output for one style case.",
        "thesis": case.verdict,
        "narrative_arc": [
            {"act": "setup", "purpose": "Name the case and version.", "slides": ["s1"]},
            {"act": "evidence", "purpose": "Show the key comparison and metrics.", "slides": ["s2", "s3"]},
            {"act": "decision", "purpose": "Close with next action structure.", "slides": ["s4"]},
        ],
        "slide_plan": [
            {"slide_id": "s1", "role": "title", "message": f"{case.short} {version} output.", "variant": "title", "visual_strategy": "preset opener", "evidence_needs": [], "asset_needs": []},
            {"slide_id": "s2", "role": "evidence", "message": case.verdict, "variant": comparison_variant, "visual_strategy": "two-column contrast", "evidence_needs": ["S1"], "asset_needs": []},
            {"slide_id": "s3", "role": "evidence", "message": "Metrics remain readable.", "variant": "chart", "visual_strategy": "editable chart", "evidence_needs": ["S1"], "asset_needs": []},
            {"slide_id": "s4", "role": "decision", "message": "Next step stays explicit.", "variant": "table", "visual_strategy": "decision table", "evidence_needs": ["S1"], "asset_needs": []},
        ],
    }


def evidence_plan(case: Case, version: str) -> dict[str, Any]:
    return {
        "topic": case.title,
        "source_policy": "Synthetic release fixture. Use only compact IDs in source-line footers.",
        "items": [
            {
                "id": "S1",
                "claim": case.verdict,
                "source_note": f"Synthetic release fixture for {case.short}.",
                "used_on_slides": ["s2", "s3", "s4"],
                "visual_use": "footer-source",
            }
        ],
        "chart_candidates": [],
        "open_questions": [],
    }


def init_workspace(repo: Path, workspace: Path, case: Case, version: str) -> None:
    run(
        [
            "python3",
            "scripts/init_deck_workspace.py",
            "--workspace",
            str(workspace),
            "--title",
            case.title,
            "--style-preset",
            case.preset,
            "--overwrite",
        ],
        repo,
    )
    write_json(workspace / "outline.json", base_outline(case, version))
    write_json(workspace / "design_brief.json", design_brief(case, version))
    write_json(workspace / "content_plan.json", content_plan(case, version))
    write_json(workspace / "evidence_plan.json", evidence_plan(case, version))
    write_json(workspace / "asset_plan.json", {"topic": case.title, "images": [], "backgrounds": [], "charts": [], "tables": [], "generated_images": [], "icons": []})
    write_text(
        workspace / "notes.md",
        f"# {case.title}\n\nSynthetic release showcase case for `{version}`.\n\nDesign DNA: {case.dna}\n",
    )


def build_workspace(repo: Path, workspace: Path) -> None:
    run(["python3", "scripts/build_workspace.py", "--workspace", str(workspace), "--qa", "--overwrite"], repo)


NATIVE_JS = r"""
import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function addText(slide, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = style;
  return shape;
}

function addBox(slide, position, fill = "white", line = "slate-200") {
  return slide.shapes.add({
    geometry: "roundRect",
    position,
    fill,
    line: { style: "solid", fill: line, width: 1 },
    borderRadius: "rounded-xl",
    shadow: "shadow-sm",
  });
}

function addFooter(slide, text, pageNo) {
  addText(slide, text, { left: 72, top: 676, width: 700, height: 24 }, { fontSize: 11, color: "slate-500" });
  addText(slide, pageNo, { left: 1130, top: 676, width: 80, height: 24 }, { fontSize: 11, color: "slate-500" });
}

function buildDeck(caseSpec, outDir) {
  const deck = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  const page = { left: 72, top: 58, width: 1136, height: 604 };
  const accent = caseSpec.accent || "teal-600";
  const dark = caseSpec.dark || "slate-950";

  {
    const slide = deck.slides.add();
    slide.background.fill = caseSpec.bg || "slate-50";
    addText(slide, "NATIVE BASELINE", { left: page.left, top: page.top, width: 260, height: 32 }, { fontSize: 13, bold: true, color: "slate-500" });
    addText(slide, caseSpec.title, { left: page.left, top: 176, width: 760, height: 130 }, { fontSize: 54, bold: true, color: dark });
    addText(slide, `${caseSpec.short} case generated with bundled Codex presentations skill`, { left: page.left, top: 322, width: 760, height: 70 }, { fontSize: 22, color: "slate-600" });
    addBox(slide, { left: 860, top: 154, width: 276, height: 276 }, "white", "slate-200");
    addText(slide, "editable objects\nsimple layout\nno repo style contract", { left: 900, top: 230, width: 200, height: 130 }, { fontSize: 24, bold: true, color: accent });
    addFooter(slide, "Native artifact-tool baseline", "1/4");
  }

  {
    const slide = deck.slides.add();
    slide.background.fill = "white";
    addText(slide, caseSpec.key_title, { left: page.left, top: 58, width: 1040, height: 84 }, { fontSize: 35, bold: true, color: dark });
    addText(slide, caseSpec.key_subtitle, { left: page.left, top: 148, width: 1040, height: 42 }, { fontSize: 18, color: "slate-600" });
    addBox(slide, { left: page.left, top: 230, width: 510, height: 250 }, "slate-50", "slate-200");
    addBox(slide, { left: 698, top: 230, width: 510, height: 250 }, "slate-50", "slate-200");
    addText(slide, caseSpec.left_title, { left: 108, top: 262, width: 430, height: 36 }, { fontSize: 25, bold: true, color: dark });
    addText(slide, caseSpec.left_body.map((x) => `• ${x}`).join("\n"), { left: 108, top: 314, width: 420, height: 120 }, { fontSize: 18, color: "slate-700" });
    addText(slide, caseSpec.right_title, { left: 734, top: 262, width: 430, height: 36 }, { fontSize: 25, bold: true, color: accent });
    addText(slide, caseSpec.right_body.map((x) => `• ${x}`).join("\n"), { left: 734, top: 314, width: 420, height: 120 }, { fontSize: 18, color: "slate-700" });
    const verdict = slide.shapes.add({ geometry: "rect", position: { left: 160, top: 536, width: 960, height: 54 }, fill: dark, line: { style: "solid", fill: dark, width: 0 } });
    verdict.text = caseSpec.verdict;
    verdict.text.style = { fontSize: 18, bold: true, color: "white" };
    addFooter(slide, "Synthetic release fixture", "2/4");
  }

    {
    const slide = deck.slides.add();
    slide.background.fill = "white";
    addText(slide, "Metrics that should stay readable", { left: page.left, top: 58, width: 950, height: 70 }, { fontSize: 36, bold: true, color: dark });
    const metricCount = caseSpec.metrics.length;
    const gutter = 56;
    const cardWidth = metricCount <= 2 ? 460 : 320;
    const totalWidth = cardWidth * metricCount + gutter * Math.max(0, metricCount - 1);
    const startX = Math.max(72, (1280 - totalWidth) / 2);
    for (let i = 0; i < caseSpec.metrics.length; i++) {
      const metric = caseSpec.metrics[i];
      const x = startX + i * (cardWidth + gutter);
      addBox(slide, { left: x, top: 188, width: cardWidth, height: 230 }, "slate-50", "slate-200");
      addText(slide, metric[0], { left: x + 28, top: 222, width: cardWidth - 56, height: 70 }, { fontSize: 45, bold: true, color: accent });
      addText(slide, metric[1], { left: x + 28, top: 306, width: cardWidth - 56, height: 38 }, { fontSize: 22, bold: true, color: dark });
      addText(slide, metric[2], { left: x + 28, top: 352, width: cardWidth - 56, height: 46 }, { fontSize: 16, color: "slate-600" });
    }
    addFooter(slide, "Native metric card layout", "3/4");
  }

  {
    const slide = deck.slides.add();
    slide.background.fill = "white";
    addText(slide, "Decision table keeps the next step explicit", { left: page.left, top: 58, width: 1040, height: 66 }, { fontSize: 35, bold: true, color: dark });
    const colX = [82, 430, 820];
    const widths = [300, 340, 300];
    const headers = ["Action", "Reason", "Owner/status"];
    for (let i = 0; i < headers.length; i++) {
      addText(slide, headers[i], { left: colX[i], top: 168, width: widths[i], height: 34 }, { fontSize: 18, bold: true, color: accent });
    }
    for (let r = 0; r < caseSpec.action_rows.length; r++) {
      const y = 226 + r * 88;
      addBox(slide, { left: 72, top: y - 10, width: 1136, height: 68 }, r % 2 === 0 ? "slate-50" : "white", "slate-200");
      for (let c = 0; c < 3; c++) {
        addText(slide, caseSpec.action_rows[r][c], { left: colX[c], top: y, width: widths[c], height: 48 }, { fontSize: 17, color: c === 0 ? dark : "slate-700", bold: c === 0 });
      }
    }
    addFooter(slide, "Native editable table approximation", "4/4");
  }

  return deck;
}

async function main() {
  const specPath = process.argv[2];
  const cases = JSON.parse(await fs.readFile(specPath, "utf8"));
  for (const caseSpec of cases) {
    const outDir = caseSpec.native_dir;
    await fs.mkdir(outDir, { recursive: true });
    const deck = buildDeck(caseSpec, outDir);
    for (const [index, slide] of deck.slides.items.entries()) {
      const stem = `slide-${String(index + 1).padStart(2, "0")}`;
      const png = await deck.export({ slide, format: "png", scale: 1 });
      await writeBlob(path.join(outDir, "renders", `${stem}.png`), png);
      const layout = await slide.export({ format: "layout" });
      await fs.writeFile(path.join(outDir, "renders", `${stem}.layout.json`), await layout.text());
    }
    const pptx = await PresentationFile.exportPptx(deck);
    await pptx.save(path.join(outDir, `${caseSpec.slug}-native.pptx`));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
"""


def build_native(cases: list[Case], release_dir: Path, scratch: Path) -> None:
    setup = NATIVE_SKILL / "container_tools" / "setup_artifact_tool_workspace.mjs"
    run([str(NATIVE_NODE if NATIVE_NODE.exists() else "node"), str(setup), "--workspace", str(scratch)], ROOT)
    specs = []
    palette = [
        ("#0B6B78", "#0F172A", "slate-50"),
        ("#F97316", "#111827", "slate-50"),
        ("#7C3AED", "#111827", "slate-50"),
        ("#A16207", "#1F2937", "amber-50"),
        ("#15803D", "#14532D", "green-50"),
        ("#2563EB", "#111827", "slate-50"),
    ]
    for idx, case in enumerate(cases):
        accent, dark, bg = palette[idx % len(palette)]
        specs.append(
            {
                "slug": case.slug,
                "title": case.title,
                "short": case.short,
                "key_title": case.key_title,
                "key_subtitle": case.key_subtitle,
                "left_title": case.left_title,
                "left_body": case.left_body,
                "right_title": case.right_title,
                "right_body": case.right_body,
                "verdict": case.verdict,
                "metrics": showcase_metrics(case),
                "action_rows": case.action_rows,
                "accent": accent,
                "dark": dark,
                "bg": bg,
                "native_dir": str(release_dir / "cases" / case.slug / "native"),
            }
        )
    spec_path = scratch / "native_cases.json"
    script_path = scratch / "native_release_showcase.mjs"
    write_json(spec_path, specs)
    write_text(script_path, NATIVE_JS)
    run([str(NATIVE_NODE if NATIVE_NODE.exists() else "node"), str(script_path), str(spec_path)], scratch)


def build_case_decks(release_dir: Path, baseline: Path) -> None:
    for index, case in enumerate(CASES, start=1):
        print(f"\n=== Case {index}/{len(CASES)}: {case.slug} ===", flush=True)
        v1 = release_dir / "cases" / case.slug / "v1"
        v11 = release_dir / "cases" / case.slug / "v1.1"
        init_workspace(baseline, v1, case, "v1")
        init_workspace(ROOT, v11, case, "v1.1")
        build_workspace(baseline, v1)
        build_workspace(ROOT, v11)


def screenshot_path(release_dir: Path, case: Case, version: str) -> str:
    base = release_dir / "cases" / case.slug
    if version == "native":
        return str(base / "native" / "renders" / "slide-02.png")
    if version == "v1":
        return str(base / "v1" / "build" / "qa" / "renders" / "slide-02.jpg")
    return str(base / "v1.1" / "build" / "qa" / "renders" / "slide-02.jpg")


def build_case_contact_sheet(release_dir: Path, workspace: Path, case: Case) -> str:
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    out_rel = Path("assets") / "comparisons" / f"{case.slug}-native-v1-v11.png"
    out_path = workspace / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    labels = [("Native", "Bundled baseline"), ("v1", "GitHub baseline"), ("v1.1", "Updated skill")]
    paths = [screenshot_path(release_dir, case, version) for version in ("native", "v1", "v1.1")]
    thumb_w, thumb_h = 560, 315
    label_h, pad, gutter = 56, 28, 24
    out_w = pad * 2 + thumb_w * 3 + gutter * 2
    out_h = pad * 2 + label_h + thumb_h
    sheet = Image.new("RGB", (out_w, out_h), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        title_font = ImageFont.truetype("Arial Bold.ttf", 24)
        sub_font = ImageFont.truetype("Arial.ttf", 17)
    except OSError:
        title_font = ImageFont.load_default()
        sub_font = ImageFont.load_default()
    for idx, ((label, caption), image_path) in enumerate(zip(labels, paths)):
        x = pad + idx * (thumb_w + gutter)
        draw.rounded_rectangle((x, pad, x + thumb_w, pad + label_h - 6), radius=8, fill=(248, 250, 252), outline=(203, 213, 225), width=1)
        draw.text((x + 16, pad + 8), label, fill=(15, 23, 42), font=title_font)
        draw.text((x + 150, pad + 13), caption, fill=(71, 85, 105), font=sub_font)
        img = Image.open(image_path).convert("RGB")
        img = ImageOps.contain(img, (thumb_w, thumb_h), Image.Resampling.LANCZOS)
        frame_y = pad + label_h
        draw.rectangle((x - 1, frame_y - 1, x + thumb_w + 1, frame_y + thumb_h + 1), outline=(148, 163, 184), width=2)
        paste_x = x + (thumb_w - img.width) // 2
        paste_y = frame_y + (thumb_h - img.height) // 2
        sheet.paste(img, (paste_x, paste_y))
    sheet.save(out_path, quality=95)
    return str(out_rel)


def build_comparison_deck(release_dir: Path) -> Path:
    workspace = release_dir / "comparison-gallery"
    style_count = len(CASES)
    deck_count = style_count * 3
    style_summary = "Report, clinical, ops, investor, editorial, policy, security, cultural"
    run(
        [
            "python3",
            "scripts/init_deck_workspace.py",
            "--workspace",
            str(workspace),
            "--title",
            "Presentation Skill v1.1 Release Gallery",
            "--style-preset",
            "lab-report",
            "--overwrite",
        ],
        ROOT,
    )
    slides: list[dict[str, Any]] = [
        {
            "slide_id": "s1",
            "type": "title",
            "title": "Presentation Skill v1.1 Release Gallery",
            "subtitle": f"Native vs v1 vs v1.1 across {style_count} deck styles",
        },
        {
            "slide_id": "s2",
            "type": "content",
            "variant": "table",
            "title": "Release claim: structured taste, reproducible builds, cleaner slides",
            "subtitle": "This evidence packet compares the same content across three generators.",
            "headers": ["Signal", "Value", "Release meaning"],
            "rows": [
                ["Styles", str(style_count), style_summary],
                ["Decks", str(deck_count), "Native, v1, and v1.1 for every case"],
                ["Evidence", "Rendered", "Actual slide images, not mockups"],
            ],
            "column_weights": [0.75, 0.55, 1.8],
            "caption": "Synthetic topics; local generated PPTX and render outputs.",
            "sources": ["local release fixtures"],
            "refs": ["synthetic cases"],
        },
    ]
    for idx, case in enumerate(CASES, start=3):
        contact_sheet = build_case_contact_sheet(release_dir, workspace, case)
        slides.append(
            {
                "slide_id": f"s{idx}",
                "type": "content",
                "variant": "scientific-figure",
                "header_mode": "lab-clean",
                "header_variant": case.v11_header,
                "title": f"{case.short}: native vs v1 vs v1.1",
                "subtitle": case.key_title,
                "figures": [
                    {
                        "path": contact_sheet,
                        "label": "A",
                        "title": "Rendered slide comparison",
                        "caption": "Slide 2 from the native, v1, and v1.1 generated decks.",
                    },
                ],
                "interpretation": "Look for hierarchy, content fit, footer/source handling, and whether the slide feels intentionally designed.",
                "sources": ["native", "v1", "v1.1"],
                "refs": [case.slug],
            }
        )
    outline = {
        "title": "Presentation Skill v1.1 Release Gallery",
        "subtitle": "Native vs v1 vs v1.1",
        "deck_style": {
            "style_seed": "release-v11-gallery-20260619",
            "header_mode": "lab-clean",
            "header_variant": "auto",
            "header_variants": ["top-bottom-rule", "split-rule", "left-accent", "plain"],
            "footer_mode": "source-line",
            "footer_page_numbers": True,
            "footer_source_label": "Src",
            "footer_refs_label": "Refs",
        },
        "slides": slides,
    }
    write_json(workspace / "outline.json", outline)
    write_json(
        workspace / "design_brief.json",
        {
            "topic": "Presentation Skill v1.1 Release Gallery",
            "content_maturity": "serious/work",
            "audience_posture": "execs/buyers",
            "emotional_register": "trustworthy",
            "design_dna": "custom release evidence gallery",
            "format_promise": "A compact gallery showing actual slide outputs instead of abstract release claims.",
            "anti_format": ["unsupported marketing claims", "tiny unreadable screenshots"],
            "canvas_and_grid": {"aspect": "16:9", "margin_x_in": 0.5, "footer_reserve_in": 0.34, "header_policy": "compact lab-clean header"},
            "visual_system": {"style_preset": "lab-report"},
            "style_system": {
                "style_preset": "lab-report",
                "style_seed": "release-v11-gallery-20260619",
                "style_mix_matrix": {
                    "header_variant_pool": ["top-bottom-rule", "split-rule", "left-accent", "plain"],
                    "chart_treatment_pool": ["minimal", "facts-right"],
                    "figure_table_treatment_pool": ["figure-first", "image-sidebar"],
                    "footer_pool": ["source-line", "standard"],
                    "summary_callout_mode_pool": ["lab-box", "default"],
                    "mix_rule": "Keep the comparison frame restrained; let screenshots be the evidence.",
                    "do_not_mix": ["Do not restyle screenshot panels."],
                },
            },
            "title_page_concept": {
                "chosen_archetype": "release evidence opener",
                "dominant_element": "v1.1 release gallery",
                "supporting_element": "native vs v1 vs v1.1 comparison",
                "why_this_could_only_be_this_deck": "It shows real generated outputs from this release candidate.",
            },
            "structure_strategy": {
                "primary_scaffold": "title, summary table, six comparison-image slides",
                "repeated_elements": ["native panel", "v1 panel", "v1.1 panel"],
                "allowed_variations": ["title", "table", "scientific-figure"],
                "container_policy": "Composite screenshots are the evidence containers.",
                "rhythm_break_plan": "Use only one summary table; keep comparisons consistent.",
            },
            "readability_contract": {
                "min_title_pt": 24,
                "min_body_pt": 12,
                "min_caption_pt": 7.5,
                "max_title_lines": 2,
                "max_slide_text_lines": 7,
                "max_slide_words": 95,
                "max_slide_chars": 640,
                "footer_reserved_inches": 0.34,
                "chart_label_min_pt": 8,
                "table_density_rule": "No dense tables in gallery.",
                "whitespace_rule": "Three screenshot panels should fill the body.",
                "figure_crop_rule": "Use rendered slide images as-is.",
            },
        },
    )
    write_json(
        workspace / "content_plan.json",
        {
            "topic": "Presentation Skill v1.1 Release Gallery",
            "audience": "HN and GitHub release readers",
            "objective": "Show actual before/after slide improvements across multiple styles.",
            "thesis": "v1.1 adds structure, taste constraints, reproducible style variation, and QA-visible cleanliness.",
            "slide_plan": [{"slide_id": f"s{i+1}", "role": "evidence", "variant": slide.get("variant", "title"), "message": slide["title"], "visual_strategy": "rendered composite slide screenshots", "evidence_needs": [], "asset_needs": []} for i, slide in enumerate(slides)],
        },
    )
    write_json(
        workspace / "evidence_plan.json",
        {
            "topic": "Presentation Skill v1.1 Release Gallery",
            "source_policy": "All evidence is generated locally from release showcase decks.",
            "items": [],
            "chart_candidates": [],
            "open_questions": [],
        },
    )
    write_json(
        workspace / "asset_plan.json",
        {"topic": "Presentation Skill v1.1 Release Gallery", "images": [], "backgrounds": [], "charts": [], "tables": [], "generated_images": [], "icons": []},
    )
    write_text(
        workspace / "notes.md",
        "# Presentation Skill v1.1 Release Gallery\n\nAll screenshots are local rendered outputs from native, v1, and v1.1 decks.\n",
    )
    build_workspace(ROOT, workspace)
    return workspace


def collect_counts(release_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in CASES:
        for version in ("native", "v1", "v1.1"):
            base = release_dir / "cases" / case.slug / version
            pptx = base / f"{case.slug}-native.pptx" if version == "native" else next((base / "build").glob("*.pptx"), None)
            rendered = len(list((base / "renders").glob("slide-*.png"))) if version == "native" else len(list((base / "build" / "qa" / "renders").glob("slide-*.jpg")))
            qa = None
            report = base / "build" / "qa" / "report.json"
            if report.exists():
                qa = json.loads(report.read_text(encoding="utf-8"))
            rows.append(
                {
                    "case": case.slug,
                    "style": case.short,
                    "version": version,
                    "pptx": str(pptx) if pptx else "",
                    "rendered_slides": rendered,
                    "overflow_count": None if version == "native" else qa.get("overflow_count", 0) if qa else None,
                    "overlap_count": None if version == "native" else qa.get("overlap_count", 0) if qa else None,
                    "geometry_warning_count": None if version == "native" else qa.get("geometry_warning_count", 0) if qa else None,
                    "geometry_error_count": None if version == "native" else qa.get("geometry_error_count", 0) if qa else None,
                    "visual_warning_count": None if version == "native" else qa.get("visual_warning_count", 0) if qa else None,
                    "design_error_count": None if version == "native" else qa.get("design_error_count", 0) if qa else None,
                    "design_warning_count": None if version == "native" else qa.get("design_warning_count", 0) if qa else None,
                }
            )
    return rows


def write_release_notes(release_dir: Path, gallery_workspace: Path) -> None:
    rows = collect_counts(release_dir)
    write_json(release_dir / "release_showcase_manifest.json", {"cases": [case.__dict__ for case in CASES], "outputs": rows})
    gallery_pptx = gallery_workspace / "build" / "presentation-skill-v1-1-release-gallery.pptx"
    if not gallery_pptx.exists():
        gallery_pptx = next((gallery_workspace / "build").glob("*.pptx"))
    style_count = len(CASES)
    deck_count = style_count * 3
    style_summary = ", ".join(case.short for case in CASES)
    notes = [
        "# presentation-skill v1.1 Release Notes",
        "",
        "This release focuses on structured, reproducible, taste-constrained slide generation rather than one-shot slide rendering.",
        "",
        "## Why this release is worth showing",
        "",
        "- Source-first deck workspaces: `outline.json`, `design_brief.json`, `content_plan.json`, `evidence_plan.json`, and `asset_plan.json` travel with the PPTX.",
        "- Reproducible style decisions: stable style seeds, supported treatment pools, and resolved heading/footer variants.",
        "- Cleaner lab/report slides: compact source-line footers, bottom-right page numbers, readable tables, and evidence-first layouts.",
        "- QA-led delivery: rendered slides are checked for overflow, overlap, geometry, placeholder text, visual warnings, and design warnings.",
        "- Data/artifact path: local CSV/Excel/JSON inputs can become reusable figures, chart specs, and summary tables.",
        "",
        "## Release evidence",
        "",
        f"- Gallery deck: `{gallery_pptx}`",
        f"- Contact-sheet PNGs: `{gallery_workspace / 'assets' / 'comparisons'}`",
        "- Comparison matrix: native bundled skill vs published GitHub v1 vs local v1.1.",
        "- Native rows are render/inspection baselines; repo QA counts are marked `n/a` because that generator uses a different tool path.",
        f"- {style_count} style cases: {style_summary}.",
        f"- {deck_count} comparison decks plus one gallery deck.",
        "- Suggested release attachments: gallery deck plus 6-8 PNG contact sheets. The lab, startup, neon, investor, clinical, and ops sheets make the improvement easiest to see quickly.",
        "",
        "## QA summary",
        "",
        "| Case | Version | Rendered slides | Overflow | Overlap | Geometry warnings | Geometry errors | Visual warnings | Design warnings |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value: Any) -> str:
        return "n/a" if value is None else str(value)

    for row in rows:
        notes.append(
            f"| {row['case']} | {row['version']} | {row['rendered_slides']} | "
            f"{fmt(row['overflow_count'])} | {fmt(row['overlap_count'])} | {fmt(row['geometry_warning_count'])} | "
            f"{fmt(row['geometry_error_count'])} | {fmt(row['visual_warning_count'])} | {fmt(row['design_warning_count'])} |"
        )
    notes.extend(
        [
            "",
            "## HN framing",
            "",
            "The strongest honest framing is: a Claude-Code-like workflow for decks. Treat the deck as a software artifact with source files, deterministic builds, visual taste constraints, and QA loops.",
            "",
            "Suggested title:",
            "",
            "> Show HN: Source-first PowerPoint deck generation for coding agents",
            "",
            "Suggested one-sentence hook:",
            "",
            "> I built a Codex presentation skill that treats slide decks like software artifacts: source files, style contracts, deterministic builds, rendered previews, and QA for overflow/overlap/layout issues.",
            "",
            "## Release checklist before publishing",
            "",
            "- Update `package.json` version and changelog if this is being tagged.",
            "- Run `npm run check:focused` before release.",
            "- Include the gallery deck and 2-3 rendered screenshots in the GitHub release.",
            "- Make clear that release-showcase data is synthetic.",
        ]
    )
    write_text(release_dir / "RELEASE_NOTES_v1.1.md", "\n".join(notes) + "\n")
    hn = """# HN Post Draft

Title options:

- Show HN: Source-first PowerPoint deck generation for coding agents
- Show HN: A reproducible slide-deck skill with taste constraints and QA
- Show HN: Claude-Code-like workflow for generating PowerPoint decks

Draft first comment:

I have been working on a Codex skill for generating editable PowerPoint decks with a workflow closer to coding agents than one-shot slide generation.

The idea is to treat a deck like a small software artifact: source files, a design brief, content and evidence plans, deterministic build commands, rendered previews, and QA checks for overflow, overlap, placeholders, layout density, and visual issues.

I also tried to encode taste in a practical way: not just prettier templates, but constraints around slide structure, readable text, evidence-first layouts, source footers, figures/tables, and avoiding awkward whitespace.

For this release candidate I generated the same synthetic topics three ways: the bundled native presentation path, the older GitHub v1 skill, and the updated local v1.1 skill. Then I built a gallery deck comparing actual rendered slides across multiple styles.

I would be interested in feedback on whether this source-first / coding-agent-like workflow is a useful direction for AI-generated slide decks.

Notes before posting:

- Rewrite this in your own voice before posting.
- Link the GitHub repo and the rendered gallery images.
- Say clearly that the release showcase data is synthetic.
"""
    write_text(release_dir / "HN_POST_DRAFT.md", hn)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="decks/release-v1.1-showcase-20260619")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    release_dir = (ROOT / args.outdir).resolve()
    if args.clean and release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)
    baseline = ensure_baseline()
    scratch = Path(tempfile.gettempdir()) / "presentation-skill-native-release-showcase"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    build_native(CASES, release_dir, scratch)
    build_case_decks(release_dir, baseline)
    gallery = build_comparison_deck(release_dir)
    write_release_notes(release_dir, gallery)
    print(f"\nRelease showcase written to {release_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
