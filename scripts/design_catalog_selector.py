#!/usr/bin/env python3
"""Reusable design-catalog selections for corpus-guided release evidence."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from typing import Any


RELEASE_VERSION = "0.5.0"
DESIGN_CATALOG_VERSION = "design_catalog_selection_v1"
RELEASE_EVIDENCE_DIR = "decks/random-topic-corpus-comparison-v0.5.0-20260622"
RANDOM_SEED = "random-topics-v2-20260622"


TOPIC_DESIGN_CASES: list[dict[str, Any]] = [
    {
        "slug": "river-watch-pocket-lab",
        "title": "Pocket Labs For River Watch",
        "subtitle": "A synthetic field-validation brief for community water testing",
        "prompt": "portable water-quality lab report with assay tables, figure panels, run metadata, and compact references",
        "baseline_preset": "lab-report",
        "corpus_preset": "lab-report",
        "corpus_family": "lab-report",
        "topic_type": "lab validation",
        "dna": "lab results dashboard",
        "tags": ["assay tables", "figure-first", "run metadata", "source-footer"],
        "palette": ("#E7F6F7", "#0F6F78", "#F7FCFC"),
        "figure_kind": "river",
        "chart_categories": ["Nitrate", "Phosphate", "Turbidity", "E. coli"],
        "chart_values": [42, 33, 71, 58],
        "table_headers": ["Site", "Nitrate", "Turbidity", "Call"],
        "table_rows": [
            ["North bend", "2.1 mg/L", "8.4 NTU", "Watch"],
            ["Mill bridge", "5.8 mg/L", "19.2 NTU", "Retest"],
            ["Reed flat", "1.4 mg/L", "5.1 NTU", "Pass"],
            ["South intake", "3.9 mg/L", "12.8 NTU", "Watch"],
        ],
        "left_title": "Episodic samples",
        "left_body": ["Few sites sampled weekly", "Paper notes slow follow-up"],
        "right_title": "Pocket lab loop",
        "right_body": ["Readers upload same-day results", "Outliers trigger paired retest"],
        "decision_rows": [
            ["Reader kit", "6 field units", "Calibrate weekly", "Proceed"],
            ["Retest rule", "Two-sigma nitrate jump", "Technician confirm", "Proceed"],
            ["Public note", "Monthly summary", "Avoid raw health claims", "Revise"],
        ],
        "data_example": True,
        "data_recipe": "assay_readout_table_plus_plot",
    },
    {
        "slug": "night-market-battery-swaps",
        "title": "Night Market Battery Swaps",
        "subtitle": "A synthetic launch deck for modular vendor power",
        "prompt": "AI-agent style product deck with neon command center, code-demo energy routing, operating metrics, and launch asks",
        "baseline_preset": "bold-startup-narrative",
        "corpus_preset": "midnight-neon",
        "corpus_family": "midnight-neon",
        "topic_type": "startup launch",
        "dna": "product/investor reveal",
        "tags": ["AI workflow", "command console", "model charts", "growth loops"],
        "palette": ("#EEF3FF", "#233A70", "#C8F7FF"),
        "figure_kind": "battery",
        "chart_categories": ["Setup min", "Swap min", "Peak kW", "Late fees"],
        "chart_values": [18, 4, 12, 3],
        "table_headers": ["Node", "Role", "Metric", "Status"],
        "table_rows": [
            ["Dock A", "Food row", "12 kW peak", "Green"],
            ["Dock B", "Music corner", "8 kW peak", "Green"],
            ["Cart pool", "Roaming", "4 min swap", "Amber"],
            ["Ops desk", "Dispatch", "92% uptime", "Green"],
        ],
        "left_title": "Generator stalls",
        "left_body": ["Noise and fumes mark the edge", "Outages stay hidden"],
        "right_title": "Swappable grid",
        "right_body": ["Docks expose power zones", "Console predicts the next swap"],
        "decision_rows": [
            ["Dock count", "4 launch docks", "Covers 38 vendors", "Proceed"],
            ["Swap crew", "2 runners", "Peak window only", "Proceed"],
            ["Pricing", "$18/night base", "Discount early adoption", "Revise"],
        ],
        "data_example": False,
        "data_recipe": "ops_console_metrics",
    },
    {
        "slug": "pocket-forest-cooling-blocks",
        "title": "Pocket Forest Cooling Blocks",
        "subtitle": "A synthetic civic science brief for heat-resilient streets",
        "prompt": "civic science policy deck with map-like evidence, forest research tone, policy bands, and implementation table",
        "baseline_preset": "arctic-minimal",
        "corpus_preset": "forest-research",
        "corpus_family": "forest-research",
        "topic_type": "civic science",
        "dna": "civic science policy",
        "tags": ["map/data anchor", "policy bands", "implementation table", "source-footer"],
        "palette": ("#EEF6E8", "#497C43", "#DCEED3"),
        "figure_kind": "forest",
        "chart_categories": ["Bare block", "Planters", "Pocket forest", "Canopy + mist"],
        "chart_values": [0, -2.3, -4.8, -5.4],
        "table_headers": ["Block", "Intervention", "Time", "Risk"],
        "table_rows": [
            ["School edge", "Pocket forest", "8 weeks", "Low"],
            ["Bus stop", "Shade + mist", "4 weeks", "Med"],
            ["Alley", "Planter spine", "3 weeks", "Low"],
            ["Market block", "Canopy lane", "6 weeks", "Med"],
        ],
        "left_title": "Reactive calls",
        "left_body": ["Sensor coverage is sparse", "Shade spend follows complaints"],
        "right_title": "Measured blocks",
        "right_body": ["Sensors map daily exposure", "Decision table ranks installs"],
        "decision_rows": [
            ["Sensor kits", "24 blocks", "Two-week baseline", "Proceed"],
            ["Forest crews", "6 blocks", "Tree survival support", "Proceed"],
            ["Mist fixtures", "4 stops", "Water review", "Hold"],
        ],
        "data_example": False,
        "data_recipe": "field_observation_matrix",
    },
    {
        "slug": "clinic-fridge-alarm-triage",
        "title": "Clinic Fridge Alarm Triage",
        "subtitle": "A synthetic risk memo for cold-chain incident response",
        "prompt": "board risk memo with incident timeline, cold-chain dashboard, owner table, and direct triage decisions",
        "baseline_preset": "executive-clinical",
        "corpus_preset": "charcoal-safety",
        "corpus_family": "charcoal-safety",
        "topic_type": "risk operations",
        "dna": "board risk memo",
        "tags": ["incident timeline", "risk matrix", "owner table", "status colors"],
        "palette": ("#F5F6F7", "#202A33", "#FFCC66"),
        "figure_kind": "risk",
        "chart_categories": ["Door", "Probe", "Power", "Courier"],
        "chart_values": [7, 2, 5, 3],
        "table_headers": ["Risk", "Trigger", "Owner", "State"],
        "table_rows": [
            ["Temp drift", "8 C 15m", "Nurse", "Red"],
            ["Probe gap", "No ping", "Biomed", "Amber"],
            ["Courier late", "45 min", "Ops", "Amber"],
            ["Batch hold", "Lot B", "Pharm", "Green"],
        ],
        "left_title": "Alarm stream",
        "left_body": ["Signals arrive as alerts", "Owners infer priority"],
        "right_title": "Triage board",
        "right_body": ["Rules group by risk", "Owners see next action"],
        "decision_rows": [
            ["Hold rule", "Lot B only", "Pharm release", "Proceed"],
            ["Probe swap", "2 sites", "Biomed visit", "Proceed"],
            ["Courier SLA", "Night route", "Cost review", "Revise"],
        ],
        "data_example": False,
        "data_recipe": "risk_status_matrix",
    },
    {
        "slug": "microgrid-load-forecast",
        "title": "Microgrid Load Forecast",
        "subtitle": "A synthetic ops dashboard for neighborhood power planning",
        "prompt": "data-heavy boardroom dashboard with forecast chart, variance table, scenario bands, and operations decision",
        "baseline_preset": "arctic-minimal",
        "corpus_preset": "data-heavy-boardroom",
        "corpus_family": "data-heavy-boardroom",
        "topic_type": "ops dashboard",
        "dna": "data-heavy boardroom",
        "tags": ["forecast chart", "variance table", "scenario bands", "owner action"],
        "palette": ("#F3F7FA", "#155E75", "#9AE6B4"),
        "figure_kind": "dashboard",
        "chart_categories": ["7am", "10am", "1pm", "4pm"],
        "chart_values": [31, 46, 58, 49],
        "table_headers": ["Feeder", "Forecast", "Reserve", "Call"],
        "table_rows": [
            ["North", "46 kW", "12%", "Watch"],
            ["Library", "58 kW", "8%", "Shift"],
            ["Market", "49 kW", "15%", "Pass"],
            ["Depot", "31 kW", "18%", "Pass"],
        ],
        "left_title": "Manual forecast",
        "left_body": ["Peak window set by habit", "Reserve margin checked late"],
        "right_title": "Scenario desk",
        "right_body": ["Bands expose load risk", "Shift calls trigger earlier"],
        "decision_rows": [
            ["Battery dispatch", "Library feeder", "If reserve <10%", "Proceed"],
            ["EV charge hold", "Depot chargers", "2-hour window", "Proceed"],
            ["Diesel backup", "Market loop", "Only if outage", "Hold"],
        ],
        "data_example": True,
        "data_recipe": "forecast_chart_variance_table",
    },
    {
        "slug": "remote-spirometry-follow-up",
        "title": "Remote Spirometry Follow-up",
        "subtitle": "A synthetic clinical exec brief for home lung monitoring",
        "prompt": "clinical executive update with cohort funnel, generated trend figure, safety table, and next-quarter decision",
        "baseline_preset": "lab-report",
        "corpus_preset": "executive-clinical",
        "corpus_family": "executive-clinical",
        "topic_type": "clinical executive",
        "dna": "clinical exec readout",
        "tags": ["cohort funnel", "safety table", "trend figure", "exec decision"],
        "palette": ("#F4F9FB", "#0E7490", "#BEE3F8"),
        "figure_kind": "clinical",
        "chart_categories": ["Enrolled", "Active", "Flagged", "Escalated"],
        "chart_values": [120, 96, 24, 8],
        "table_headers": ["Group", "Adherence", "Flags", "Call"],
        "table_rows": [
            ["COPD", "82%", "12", "Watch"],
            ["Asthma", "88%", "6", "Pass"],
            ["Post-viral", "74%", "9", "Coach"],
            ["Control", "91%", "2", "Pass"],
        ],
        "left_title": "Clinic-only checks",
        "left_body": ["Decline found at visits", "Coaching starts late"],
        "right_title": "Home follow-up",
        "right_body": ["Weekly curves flag drift", "Escalations stay visible"],
        "decision_rows": [
            ["Device pool", "180 kits", "Replace old meters", "Proceed"],
            ["Nurse review", "Twice weekly", "Flagged group", "Proceed"],
            ["Escalation", "FEV1 drop", "Physician review", "Revise"],
        ],
        "data_example": True,
        "data_recipe": "cohort_trend_and_safety_table",
    },
    {
        "slug": "harbor-wave-storage-pitch",
        "title": "Harbor Wave Storage Pitch",
        "subtitle": "A synthetic investor brief for pier-side energy storage",
        "prompt": "investor deck with traction curve, market wedge table, pilot economics, and fundraising ask",
        "baseline_preset": "bold-startup-narrative",
        "corpus_preset": "sunset-investor",
        "corpus_family": "sunset-investor",
        "topic_type": "investor pitch",
        "dna": "product/investor reveal",
        "tags": ["traction curve", "market wedge", "unit economics", "funding ask"],
        "palette": ("#FFF4E8", "#9A4D1E", "#FFD38A"),
        "figure_kind": "investor",
        "chart_categories": ["Pilot", "Port A", "Port B", "Fleet"],
        "chart_values": [3, 9, 17, 28],
        "table_headers": ["Segment", "Buyer", "Need", "Signal"],
        "table_rows": [
            ["Marina", "Harbor ops", "Backup", "Pilot"],
            ["Ferry", "Fleet mgr", "Peak shave", "LOI"],
            ["Cold chain", "Dock ops", "Uptime", "Trial"],
            ["Events", "Venue", "Quiet power", "Repeat"],
        ],
        "left_title": "Prototype story",
        "left_body": ["One pier proves storage", "Sales motion is informal"],
        "right_title": "Repeatable wedge",
        "right_body": ["Ports share use cases", "Pipeline tracks same metrics"],
        "decision_rows": [
            ["Seed ask", "$2.4M", "18-month runway", "Proceed"],
            ["Pilot two", "Port A", "Signed LOI", "Proceed"],
            ["Hardware rev", "Battery rack", "Cost target", "Revise"],
        ],
        "data_example": True,
        "data_recipe": "traction_curve_market_table",
    },
    {
        "slug": "museum-airflow-retrofit",
        "title": "Museum Airflow Retrofit",
        "subtitle": "A synthetic editorial research note for quiet HVAC upgrades",
        "prompt": "paper-journal editorial deck with artifact-first figure, measured airflow table, conservation notes, and references posture",
        "baseline_preset": "editorial-minimal",
        "corpus_preset": "paper-journal",
        "corpus_family": "paper-journal",
        "topic_type": "editorial research",
        "dna": "editorial report",
        "tags": ["artifact figure", "measured table", "conservation note", "references"],
        "palette": ("#F8F4EA", "#6B5A3A", "#D7C39A"),
        "figure_kind": "journal",
        "chart_categories": ["Gallery A", "Archive", "Lobby", "Cafe"],
        "chart_values": [18, 12, 24, 31],
        "table_headers": ["Zone", "Airflow", "Humidity", "Risk"],
        "table_rows": [
            ["Gallery A", "18 ACH", "47%", "Low"],
            ["Archive", "12 ACH", "52%", "Med"],
            ["Lobby", "24 ACH", "43%", "Low"],
            ["Cafe", "31 ACH", "41%", "Med"],
        ],
        "left_title": "Mechanical brief",
        "left_body": ["Upgrade framed as HVAC", "Artifact risk is secondary"],
        "right_title": "Conservation note",
        "right_body": ["Airflow tied to objects", "References stay visible"],
        "decision_rows": [
            ["Archive damper", "Zone B", "Humidity target", "Proceed"],
            ["Gallery diffuser", "North wall", "Noise review", "Proceed"],
            ["Cafe exhaust", "Evening load", "Odor test", "Hold"],
            ["Reference note", "Conservator memo", "Attach appendix", "Proceed"],
        ],
        "data_example": False,
        "data_recipe": "artifact_measurement_table",
    },
]


def _selection_for_topic(topic: dict[str, Any]) -> dict[str, Any]:
    """Return the reusable design-catalog decision for one synthetic topic."""
    return {
        "catalog_version": DESIGN_CATALOG_VERSION,
        "selection_id": f"{topic['slug']}::{topic['corpus_family']}",
        "primary_family": topic["corpus_family"],
        "baseline_preset": topic["baseline_preset"],
        "corpus_preset": topic["corpus_preset"],
        "design_dna": topic["dna"],
        "topic_type": topic["topic_type"],
        "treatment_tags": list(topic["tags"]),
        "data_recipe": topic.get("data_recipe"),
        "data_example": bool(topic.get("data_example")),
        "content_structure": {
            "baseline": ["title", "cards", "chart", "comparison", "figure-sidebar"],
            "corpus": ["title", "figure", "ledger", "chart", "comparison", "decision"],
        },
        "selection_rule": (
            "Match topic evidence burden and tone to one primary corpus family; "
            "translate borrowed treatments into supported renderer variants."
        ),
    }


def comparison_topics() -> list[dict[str, Any]]:
    topics = deepcopy(TOPIC_DESIGN_CASES)
    for topic in topics:
        topic["design_catalog_selection"] = _selection_for_topic(topic)
    return topics


def design_catalog_summary(topics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    selected = topics or comparison_topics()
    families = sorted({topic["corpus_family"] for topic in selected})
    data_examples = [topic["slug"] for topic in selected if topic.get("data_example")]
    return {
        "catalog_version": DESIGN_CATALOG_VERSION,
        "release_version": RELEASE_VERSION,
        "topic_count": len(selected),
        "corpus_family_count": len(families),
        "corpus_families": families,
        "data_example_count": len(data_examples),
        "data_example_slugs": data_examples,
        "selection_rule": (
            "Use topic evidence type, design DNA, source burden, and data/artifact "
            "needs to pick one primary style family plus bounded treatment tags."
        ),
    }


def select_design_case(prompt: str) -> dict[str, Any]:
    """Small deterministic selector for agents and release builders."""
    text = prompt.lower()
    topics = comparison_topics()
    best = topics[0]
    best_score = -1
    for topic in topics:
        tokens = [topic["title"], topic["prompt"], topic["topic_type"], topic["dna"], *topic["tags"]]
        score = sum(1 for token in tokens if str(token).lower() in text)
        if score > best_score:
            best = topic
            best_score = score
    return best


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="Emit catalog summary instead of full topic cases.")
    parser.add_argument("--prompt", help="Select one design case for a prompt.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    if args.prompt:
        payload = select_design_case(args.prompt)
    elif args.summary:
        payload = design_catalog_summary()
    else:
        payload = {
            "catalog_version": DESIGN_CATALOG_VERSION,
            "release_version": RELEASE_VERSION,
            "topics": comparison_topics(),
            "summary": design_catalog_summary(),
        }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
