#!/usr/bin/env python3
"""Reusable preset treatment profiles for reproducible style mixing."""

from __future__ import annotations

import copy
import json
from typing import Any


PROFILE_VERSION = "deck_preset_treatment_profiles_v1"
SUPPORTED_HEADER_VARIANTS = [
    "left-accent",
    "split-rule",
    "title-rule",
    "side-rail",
    "top-bottom-rule",
    "plain",
]
SUPPORTED_TITLE_LAYOUTS = ["split-hero", "lab-plate", "command-center", "poster", "masthead", "light-atlas"]
SUPPORTED_FOOTERS = ["standard", "source-line"]
SUPPORTED_CHART_TREATMENTS = ["standard", "facts-below", "facts-right", "minimal"]
SUPPORTED_FIGURE_TABLE_TREATMENTS = ["figure-first", "table-first", "stats-strip", "image-sidebar"]


BASE_MIX_MATRIX = {
    "header_variant_pool": list(SUPPORTED_HEADER_VARIANTS),
    "title_layout_pool": ["split-hero", "lab-plate", "masthead", "light-atlas"],
    "section_motif_pool": ["rail-dots", "plain", "none"],
    "timeline_mode_pool": ["rail-cards", "staggered", "open-events", "bands", "chapter-spread"],
    "matrix_mode_pool": ["cards", "open-quadrants"],
    "stats_mode_pool": ["tiles", "feature-left", "policy-bands"],
    "cards_mode_pool": ["feature-left", "staggered-row"],
    "chart_treatment_pool": list(SUPPORTED_CHART_TREATMENTS),
    "summary_callout_mode_pool": ["default", "lab-box"],
    "figure_table_treatment_pool": list(SUPPORTED_FIGURE_TABLE_TREATMENTS),
    "footer_pool": list(SUPPORTED_FOOTERS),
    "mix_rule": "Resolve restrained renderer treatments from the stable style_seed; override explicitly when the evidence shape requires it.",
    "do_not_mix": [
        "Do not combine decorative section motifs with dense scientific figure slides unless they support navigation.",
        "Do not use none footer mode for source-heavy research or lab decks.",
    ],
}


PROFILE_OVERRIDES: dict[str, dict[str, Any]] = {
    "lab-report": {
        "family": "scientific-report",
        "background_system": "white report",
        "heading_accent_combo": "lab-clean report heading with compact rules and page/source footer",
        "style_mix_matrix": {
            "header_variant_pool": ["left-accent", "split-rule", "title-rule", "side-rail", "top-bottom-rule", "plain"],
            "title_layout_pool": ["split-hero", "lab-plate", "masthead", "light-atlas"],
            "footer_pool": ["source-line", "standard"],
            "chart_treatment_pool": ["minimal", "facts-right", "facts-below"],
            "figure_table_treatment_pool": ["figure-first", "table-first", "image-sidebar"],
            "summary_callout_mode_pool": ["lab-box", "default"],
        },
        "best_for": ["assay results", "lab reports", "scientific figures", "dense leave-behind reports"],
        "avoid": ["decorative card grids", "dark stage backgrounds for dense data", "footer-free source-heavy slides"],
    },
    "paper-journal": {
        "family": "scientific-report",
        "background_system": "white paper",
        "heading_accent_combo": "journal-style title stack with restrained rules and source-footer posture",
        "style_mix_matrix": {
            "header_variant_pool": ["split-rule", "top-bottom-rule", "plain", "title-rule"],
            "title_layout_pool": ["masthead", "light-atlas", "lab-plate"],
            "footer_pool": ["source-line", "standard"],
            "chart_treatment_pool": ["minimal", "standard", "facts-right"],
            "figure_table_treatment_pool": ["figure-first", "image-sidebar", "table-first"],
        },
        "best_for": ["academic summaries", "journal clubs", "methods/results decks"],
        "avoid": ["high-chroma accent rails", "oversized decorative motifs"],
    },
    "data-heavy-boardroom": {
        "family": "data-report",
        "background_system": "white board report",
        "heading_accent_combo": "executive report heading with split rules and compact source line",
        "style_mix_matrix": {
            "header_variant_pool": ["split-rule", "left-accent", "top-bottom-rule", "plain"],
            "title_layout_pool": ["split-hero", "light-atlas", "masthead"],
            "footer_pool": ["source-line", "standard"],
            "chart_treatment_pool": ["facts-right", "facts-below", "minimal", "standard"],
            "figure_table_treatment_pool": ["table-first", "stats-strip", "figure-first"],
        },
        "best_for": ["dashboards", "board memos", "analytics reviews"],
        "avoid": ["figure-only evidence when editable charts/tables are needed"],
    },
    "executive-clinical": {
        "family": "clinical-executive",
        "background_system": "light clinical report",
        "heading_accent_combo": "quiet clinical heading with left accent or split rule",
        "style_mix_matrix": {
            "header_variant_pool": ["left-accent", "split-rule", "top-bottom-rule", "plain"],
            "title_layout_pool": ["split-hero", "light-atlas", "lab-plate"],
            "footer_pool": ["source-line", "standard"],
            "chart_treatment_pool": ["facts-right", "minimal", "standard"],
            "figure_table_treatment_pool": ["figure-first", "table-first", "image-sidebar"],
        },
        "best_for": ["clinical updates", "translational research", "executive evidence reviews"],
        "avoid": ["startup-style hero exaggeration", "dense cells below readability floors"],
    },
    "forest-research": {
        "family": "research-report",
        "background_system": "light natural report",
        "heading_accent_combo": "research heading with organic accent rail and clean rules",
        "style_mix_matrix": {
            "header_variant_pool": ["left-accent", "split-rule", "plain", "top-bottom-rule"],
            "title_layout_pool": ["light-atlas", "masthead", "split-hero"],
            "footer_pool": ["source-line", "standard"],
            "chart_treatment_pool": ["minimal", "facts-below", "standard"],
            "figure_table_treatment_pool": ["figure-first", "image-sidebar", "table-first"],
        },
        "best_for": ["field research", "environmental science", "observational evidence"],
        "avoid": ["heavy dark sections unless the content needs a section turn"],
    },
    "arctic-minimal": {
        "family": "minimal-report",
        "background_system": "cool light field",
        "heading_accent_combo": "minimal heading with plain, split, or title rule accents",
        "style_mix_matrix": {
            "header_variant_pool": ["plain", "split-rule", "title-rule", "left-accent"],
            "title_layout_pool": ["light-atlas", "masthead", "split-hero"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["minimal", "standard", "facts-right"],
            "figure_table_treatment_pool": ["figure-first", "image-sidebar", "table-first"],
        },
        "best_for": ["clean explainers", "technical summaries", "low-noise analysis"],
        "avoid": ["many simultaneous accent systems"],
    },
    "editorial-minimal": {
        "family": "editorial-report",
        "background_system": "light editorial",
        "heading_accent_combo": "editorial masthead with title rule or plain report body",
        "style_mix_matrix": {
            "header_variant_pool": ["title-rule", "plain", "split-rule", "left-accent"],
            "title_layout_pool": ["masthead", "light-atlas", "poster"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["minimal", "facts-below", "standard"],
            "figure_table_treatment_pool": ["image-sidebar", "figure-first", "table-first"],
        },
        "best_for": ["narrative reports", "public-facing analysis", "portfolio-style explanations"],
        "avoid": ["too many KPI tiles", "busy card grids"],
    },
    "lavender-ops": {
        "family": "ops-report",
        "background_system": "quiet operational report",
        "heading_accent_combo": "operations heading with split rules and restrained labels",
        "style_mix_matrix": {
            "header_variant_pool": ["split-rule", "left-accent", "plain", "top-bottom-rule"],
            "title_layout_pool": ["split-hero", "light-atlas", "masthead"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["facts-right", "standard", "minimal"],
            "figure_table_treatment_pool": ["table-first", "stats-strip", "image-sidebar"],
        },
        "best_for": ["operational reviews", "project status", "team dashboards"],
        "avoid": ["decorative purple gradients as the only visual system"],
    },
    "bold-startup-narrative": {
        "family": "narrative-pitch",
        "background_system": "bold narrative stage",
        "heading_accent_combo": "large narrative heading with left accent, side rail, or title rule",
        "style_mix_matrix": {
            "header_variant_pool": ["left-accent", "title-rule", "side-rail", "split-rule"],
            "title_layout_pool": ["split-hero", "poster", "command-center"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["facts-below", "facts-right", "standard"],
            "figure_table_treatment_pool": ["stats-strip", "image-sidebar", "figure-first"],
        },
        "best_for": ["product stories", "growth narratives", "founder/investor updates"],
        "avoid": ["lab-report density unless the evidence burden requires it"],
    },
    "sunset-investor": {
        "family": "investor-story",
        "background_system": "warm investor narrative",
        "heading_accent_combo": "investor heading with strong title rule or side rail",
        "style_mix_matrix": {
            "header_variant_pool": ["title-rule", "left-accent", "side-rail", "split-rule"],
            "title_layout_pool": ["split-hero", "poster", "command-center"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["facts-below", "facts-right", "standard"],
            "figure_table_treatment_pool": ["stats-strip", "figure-first", "image-sidebar"],
        },
        "best_for": ["fundraising", "market stories", "commercial strategy"],
        "avoid": ["source-heavy tiny footers; move long citations to references"],
    },
    "warm-terracotta": {
        "family": "warm-editorial",
        "background_system": "warm editorial report",
        "heading_accent_combo": "warm report heading with split rule or title accent",
        "style_mix_matrix": {
            "header_variant_pool": ["split-rule", "title-rule", "left-accent", "plain"],
            "title_layout_pool": ["masthead", "split-hero", "light-atlas"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["facts-below", "minimal", "standard"],
            "figure_table_treatment_pool": ["image-sidebar", "figure-first", "table-first"],
        },
        "best_for": ["human-centered reports", "case studies", "strategy narratives"],
        "avoid": ["brown/orange monotone decks without neutral structure"],
    },
    "charcoal-safety": {
        "family": "dark-technical",
        "background_system": "dark safety report",
        "heading_accent_combo": "dark technical heading with side rail, title rule, or split rule",
        "style_mix_matrix": {
            "header_variant_pool": ["side-rail", "title-rule", "split-rule", "plain"],
            "title_layout_pool": ["command-center", "split-hero", "poster"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["facts-right", "standard", "facts-below"],
            "figure_table_treatment_pool": ["stats-strip", "table-first", "figure-first"],
        },
        "best_for": ["risk", "safety", "incident review", "technical operations"],
        "avoid": ["low-contrast muted text on dark backgrounds"],
    },
    "midnight-neon": {
        "family": "dark-technical",
        "background_system": "dark technical stage",
        "heading_accent_combo": "dark stage heading with side rail, split rule, or plain body pages",
        "style_mix_matrix": {
            "header_variant_pool": ["side-rail", "split-rule", "title-rule", "plain"],
            "title_layout_pool": ["command-center", "poster", "split-hero"],
            "footer_pool": ["standard", "source-line"],
            "chart_treatment_pool": ["facts-right", "standard", "facts-below"],
            "figure_table_treatment_pool": ["stats-strip", "image-sidebar", "figure-first"],
        },
        "best_for": ["technical demos", "security/AI narratives", "high-contrast explainers"],
        "avoid": ["neon accents on every object", "small low-contrast footers"],
    },
}


def _merge_mix(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, list):
            merged[key] = list(value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def preset_treatment_profile(preset: str) -> dict[str, Any]:
    """Return a copyable treatment profile for a loadable preset."""
    key = str(preset or "").strip() or "executive-clinical"
    override = PROFILE_OVERRIDES.get(key, {})
    profile = {
        "profile_version": PROFILE_VERSION,
        "style_preset": key,
        "family": override.get("family", "general-report"),
        "background_system": override.get("background_system", "light report"),
        "heading_accent_combo": override.get(
            "heading_accent_combo",
            "general report heading with bounded accent-rule variants",
        ),
        "style_mix_matrix": _merge_mix(
            BASE_MIX_MATRIX,
            override.get("style_mix_matrix", {}) if isinstance(override.get("style_mix_matrix"), dict) else {},
        ),
        "best_for": list(override.get("best_for", ["general presentations", "structured reports"])),
        "avoid": list(override.get("avoid", ["unsupported renderer treatments", "unreadable text"])),
    }
    return copy.deepcopy(profile)


def style_mix_matrix_for_preset(preset: str) -> dict[str, Any]:
    return preset_treatment_profile(preset)["style_mix_matrix"]


def preset_treatment_profiles_for_presets(presets: list[str]) -> list[dict[str, Any]]:
    return [preset_treatment_profile(preset) for preset in presets]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Emit preset treatment profile JSON.")
    parser.add_argument("--preset", default="", help="Optional preset to emit. Defaults to all known profile overrides.")
    args = parser.parse_args()
    payload: Any
    if args.preset:
        payload = preset_treatment_profile(args.preset)
    else:
        payload = {
            "profile_version": PROFILE_VERSION,
            "presets": preset_treatment_profiles_for_presets(sorted(PROFILE_OVERRIDES)),
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
