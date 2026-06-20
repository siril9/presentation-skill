#!/usr/bin/env python3
"""Emit an adaptive user-intake prompt for personalized deck generation.

The prompt is for the main agent to ask the user before authoring a deck when
style, audience, density, palette, or asset expectations are underspecified.
It is intentionally skip-friendly: if the user wants speed, proceed with best
judgment and record assumptions in the workspace.

Usage:
    python3 scripts/emit_deck_intake_prompt.py --user-prompt "Build a deck on TB LAMP"
    python3 scripts/emit_deck_intake_prompt.py --workspace decks/my-deck --mode full
    python3 scripts/emit_deck_intake_prompt.py --user-prompt "Build a technical deck" --codex-ui
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PLACEHOLDER_PATTERNS = (
    "replace with",
    "chosen from the preset",
    "topic-specific opener chosen",
    "clean, editable powerpoint deck",
    "one dominant idea per slide",
    "avoid generic card grids",
    "coworkers/operators",
    "serious/work",
    "trustworthy",
)


QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": "audience_context",
        "title": "Audience and use",
        "question": (
            "Who is the deck for, and how will it be used: live talk, "
            "leave-behind/report, teaching deck, pitch, board update, poster, "
            "or something else?"
        ),
        "why": "Audience and use determine density, citation posture, and slide rhythm.",
        "maps_to": [
            "design_brief.user_intake.audience_context",
            "design_brief.audience_posture",
            "content_plan.audience",
        ],
        "signals": [
            "design_brief.user_intake.audience_context",
            "design_brief.user_intake.audience_detail",
            "design_brief.audience_posture",
            "content_plan.audience",
            "audience_context",
            "audience_detail",
            "audience_posture",
            "presentation_context",
        ],
    },
    {
        "id": "target_outcome",
        "title": "Target outcome",
        "question": (
            "What should the audience believe, decide, or do after the deck?"
        ),
        "why": "A deck with a decision target needs a different structure than a neutral explainer.",
        "maps_to": [
            "design_brief.user_intake.target_outcome",
            "content_plan.thesis",
            "content_plan.decision_target",
        ],
        "signals": [
            "design_brief.user_intake.target_outcome",
            "content_plan.thesis",
            "content_plan.decision_target",
            "target_outcome",
            "decision_target",
            "thesis",
            "objective",
            "goal",
        ],
    },
    {
        "id": "style_direction",
        "title": "Style direction",
        "question": (
            "What visual feel should it have: conservative report, premium "
            "editorial, lab-report/figure-first, bold pitch, teaching "
            "whiteboard, cinematic, playful, or a reference style you like?"
        ),
        "why": "This prevents a generic template from winning by default.",
        "maps_to": [
            "design_brief.user_intake.style_direction",
            "design_brief.design_dna",
            "design_brief.format_promise",
            "outline.deck_style",
        ],
        "signals": [
            "design_brief.user_intake.style_direction",
            "design_brief.design_dna",
            "design_brief.format_promise",
            "outline.deck_style",
            "style_direction",
            "design_dna",
            "format_promise",
            "reference_deck",
            "reference_style",
        ],
    },
    {
        "id": "density",
        "title": "Density",
        "question": (
            "How dense should slides be: sparse live-talk slides, balanced "
            "presenter-led slides, or dense report/leave-behind pages?"
        ),
        "why": "Density changes font sizes, table use, figure placement, and speaker-note reliance.",
        "maps_to": [
            "design_brief.user_intake.density",
            "design_brief.design_modulation.density_strategy",
            "content_plan.visual_strategy",
        ],
        "signals": [
            "design_brief.user_intake.density",
            "design_brief.design_modulation.density_strategy",
            "density",
            "density_strategy",
            "live talk",
            "leave-behind",
            "report density",
        ],
    },
    {
        "id": "palette",
        "title": "Palette",
        "question": (
            "Should I use a brand/lab palette, pick a new palette, stay mostly "
            "neutral, or avoid any specific colors?"
        ),
        "why": "Palette preference is a high-leverage personalization signal and avoids unwanted defaults.",
        "maps_to": [
            "design_brief.user_intake.palette",
            "design_brief.visual_system",
            "design_brief.design_modulation.accent_strategy",
        ],
        "signals": [
            "design_brief.user_intake.palette",
            "design_brief.design_modulation.accent_strategy",
            "palette",
            "brand",
            "color",
            "accent_strategy",
            "avoid_colors",
        ],
    },
    {
        "id": "background_visuals",
        "title": "Background and visuals",
        "question": (
            "What background/visual mode fits: clean white report, subtle "
            "gradient, dark stage, photo-backed, textured/editorial, "
            "source-backed images, generated concept art, or no imagery?"
        ),
        "why": "Background choice affects contrast, asset planning, and whether imagery is evidence or atmosphere.",
        "maps_to": [
            "design_brief.user_intake.background_visuals",
            "design_brief.title_page_concept",
            "asset_plan.images",
            "asset_plan.backgrounds",
            "asset_plan.generated_images",
        ],
        "signals": [
            "design_brief.user_intake.background_visuals",
            "asset_plan.backgrounds",
            "asset_plan.generated_images",
            "background_visuals",
            "background",
            "hero image",
            "source-backed",
            "generated image",
            "photo",
            "imagery",
        ],
    },
    {
        "id": "evidence_assets",
        "title": "Evidence and assets",
        "question": (
            "Do you have figures, screenshots, tables, raw data, logos, papers, "
            "or example decks I should use? If yes, where are they?"
        ),
        "why": "Asset availability should drive figure-first layouts and data-analysis subagents.",
        "maps_to": [
            "design_brief.user_intake.evidence_assets",
            "evidence_plan.items",
            "asset_plan",
            "design_brief.figure_export_contract",
        ],
        "signals": [
            "design_brief.user_intake.evidence_assets",
            "evidence_plan.items",
            "asset_plan.images",
            "asset_plan.charts",
            "asset_plan.icons",
            "design_brief.figure_export_contract",
            "evidence_assets",
            "asset",
            "figure",
            "screenshot",
            "table",
            "raw data",
            "figure_export_contract",
        ],
    },
    {
        "id": "source_policy",
        "title": "Sources and claims",
        "question": (
            "How strict should sourcing be: quick draft, cite key claims, "
            "source every factual claim, or use only files/sources you provide?"
        ),
        "why": "Source policy changes research time, footers, and how aggressively claims are hedged.",
        "maps_to": [
            "design_brief.user_intake.source_policy",
            "evidence_plan.source_policy",
            "outline.slides[].sources",
        ],
        "signals": [
            "design_brief.user_intake.source_policy",
            "evidence_plan.source_policy",
            "source_policy",
            "citation",
            "sources",
            "cite",
            "provenance",
        ],
    },
    {
        "id": "constraints",
        "title": "Constraints",
        "question": (
            "Any hard constraints: slide count, talk length, aspect ratio, "
            "deadline, editable-only elements, font rules, accessibility needs, "
            "or things to avoid?"
        ),
        "why": "Constraints prevent late rework and keep QA targets realistic.",
        "maps_to": [
            "design_brief.user_intake.constraints",
            "design_brief.anti_format",
            "notes.md",
        ],
        "signals": [
            "design_brief.user_intake.constraints",
            "constraints",
            "slide_count",
            "talk_length",
            "deadline",
            "accessibility",
            "must_avoid",
        ],
    },
]


CODEX_UI_QUESTIONS: list[dict[str, Any]] = [
    {
        "header": "Audience",
        "id": "audience_context",
        "question": "Who should this deck primarily serve?",
        "options": [
            {
                "label": "Technical peers (Recommended)",
                "description": "Optimizes for methods, evidence depth, figures, and citations.",
            },
            {
                "label": "Clinical/exec",
                "description": "Keeps mechanisms but foregrounds clinical or strategic implications.",
            },
            {
                "label": "Mixed audience",
                "description": "Balances technical accuracy with more explanatory scaffolding.",
            },
        ],
    },
    {
        "header": "Style",
        "id": "style_density",
        "question": "What style and density should I use?",
        "options": [
            {
                "label": "Figure-first report (Recommended)",
                "description": "Dense, source-backed, and suitable as a technical leave-behind.",
            },
            {
                "label": "Conference talk",
                "description": "Cleaner, more presenter-led, with fewer claims per slide.",
            },
            {
                "label": "Premium editorial",
                "description": "More polished and visual, with less table-heavy density.",
            },
        ],
    },
    {
        "header": "Visuals",
        "id": "visual_source_policy",
        "question": "How should visuals, palette, and sourcing be handled?",
        "options": [
            {
                "label": "Best judgment (Recommended)",
                "description": "Use restrained palette, local schematics/figures, and citations for key claims.",
            },
            {
                "label": "Strict sources",
                "description": "Prefer source-backed figures and cite every factual claim.",
            },
            {
                "label": "Custom assets",
                "description": "Pause for user-provided palette, figures, logo, or reference deck.",
            },
        ],
    },
]


def _read_optional(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _load_json(path: Path) -> Any | None:
    text = _read_optional(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _is_placeholder_text(text: str) -> bool:
    lower = _normalize(text)
    if not lower:
        return True
    return any(pattern in lower for pattern in PLACEHOLDER_PATTERNS)


def _meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return not _is_placeholder_text(value)
    if isinstance(value, dict):
        return any(_meaningful_value(item) for item in value.values())
    if isinstance(value, list):
        return any(_meaningful_value(item) for item in value)
    return True


def _lookup_path(payload: Any, dotted: str) -> Any:
    value = payload
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _workspace_payload(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {}
    return {
        "design_brief": _load_json(workspace / "design_brief.json"),
        "content_plan": _load_json(workspace / "content_plan.json"),
        "evidence_plan": _load_json(workspace / "evidence_plan.json"),
        "asset_plan": _load_json(workspace / "asset_plan.json"),
        "outline": _load_json(workspace / "outline.json"),
        "notes": _read_optional(workspace / "notes.md"),
    }


def _signal_answered(question: dict[str, Any], payloads: dict[str, Any], prompt: str) -> bool:
    user_intake = _lookup_path(payloads, "design_brief.user_intake")
    if isinstance(user_intake, dict) and _meaningful_value(user_intake.get(question["id"])):
        return True

    for signal in question["signals"]:
        if "." in signal:
            if _meaningful_value(_lookup_path(payloads, signal)):
                return True

    lower = _normalize(prompt)

    for signal in question["signals"]:
        token = signal.lower().replace("_", " ")
        if "." not in signal and len(token) >= 4 and token in lower:
            return True

    return False


def _selected_questions(payloads: dict[str, Any], prompt: str, mode: str) -> list[dict[str, Any]]:
    missing = [q for q in QUESTION_BANK if not _signal_answered(q, payloads, prompt)]

    if mode == "full":
        return missing or QUESTION_BANK

    priority = [
        "audience_context",
        "style_direction",
        "density",
        "palette",
        "background_visuals",
        "evidence_assets",
        "constraints",
        "target_outcome",
        "source_policy",
    ]
    by_id = {q["id"]: q for q in missing}
    selected = [by_id[qid] for qid in priority if qid in by_id]
    return selected[:7] or QUESTION_BANK[:5]


def _intake_template() -> dict[str, str]:
    return {
        "audience_context": "",
        "target_outcome": "",
        "style_direction": "",
        "density": "",
        "palette": "",
        "background_visuals": "",
        "evidence_assets": "",
        "source_policy": "",
        "constraints": "",
        "answered_by": "user | inferred | best_judgment",
        "unanswered": "",
    }


def render_prompt(
    *,
    workspace: Path | None,
    user_prompt: str,
    mode: str,
    include_mapping: bool,
) -> str:
    payloads = _workspace_payload(workspace)
    questions = _selected_questions(payloads, user_prompt, mode)

    lines: list[str] = [
        "DECK PERSONALIZATION INTAKE PROMPT",
        "",
        "Use this only when personalization matters or the user has not already specified audience, style, density, palette, or asset constraints. Do not block urgent/simple deck generation.",
        "",
        "Ask the user:",
        "",
        "Before I draft the deck, answer any of these that matter. If you do not care about an item, say `use best judgment` and I will choose a coherent direction.",
        "",
    ]
    for idx, question in enumerate(questions, start=1):
        lines.append(f"{idx}. {question['title']}: {question['question']}")

    lines.extend(
        [
            "",
            "After the user answers:",
            "- Record explicit answers under `design_brief.user_intake`.",
            "- Translate style, palette, density, and background answers into `design_modulation`, `visual_system`, `title_page_concept`, `deck_style`, and `asset_plan`.",
            "- Put unanswered items in `design_brief.user_intake.unanswered` and proceed with best judgment.",
            "- If answers reveal local data, figures, assay results, clinical claims, or strict sourcing, run the content/data/style scouts before finalizing `outline.json`.",
        ]
    )

    if user_prompt:
        lines.extend(["", "Original user request:", user_prompt])

    if workspace is not None:
        lines.extend(["", f"Workspace: {workspace}"])

    if include_mapping:
        lines.extend(
            [
                "",
                "Suggested `design_brief.user_intake` shape:",
                "```json",
                json.dumps(_intake_template(), indent=2),
                "```",
                "",
                "Question-to-field mapping:",
            ]
        )
        for question in questions:
            lines.append(f"- {question['id']}: {', '.join(question['maps_to'])}")

    return "\n".join(lines) + "\n"


def render_codex_ui_spec(*, workspace: Path | None, user_prompt: str, mode: str) -> str:
    """Emit a request_user_input-compatible JSON packet for Codex agents.

    The Codex UI question card only supports up to three short questions, so
    this packet intentionally compresses the full intake into audience, style
    density, and visual/source posture.
    """
    payloads = _workspace_payload(workspace)
    missing_ids = {question["id"] for question in _selected_questions(payloads, user_prompt, mode)}

    selected: list[dict[str, Any]] = []
    if "audience_context" in missing_ids:
        selected.append(CODEX_UI_QUESTIONS[0])
    if {"style_direction", "density"} & missing_ids:
        selected.append(CODEX_UI_QUESTIONS[1])
    if {"palette", "background_visuals", "evidence_assets", "source_policy"} & missing_ids:
        selected.append(CODEX_UI_QUESTIONS[2])

    if not selected:
        selected = CODEX_UI_QUESTIONS[:1]

    packet = {
        "usage": (
            "If the Codex request_user_input tool is available, call it immediately "
            "with this JSON payload before planning the deck. If the tool is not "
            "available in the current mode, ask the same questions in chat."
        ),
        "request_user_input": {
            "autoResolutionMs": 90000,
            "questions": selected[:3],
        },
        "fallback": "If the user does not answer, continue with best judgment and record assumptions in design_brief.user_intake.",
        "maps_to": "design_brief.user_intake, then design_modulation, visual_system, deck_style, asset_plan, notes.md",
    }
    return json.dumps(packet, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit an adaptive deck-personalization intake prompt.")
    parser.add_argument("--workspace", help="Optional deck workspace directory")
    parser.add_argument("--user-prompt", default="", help="Original user request")
    parser.add_argument(
        "--mode",
        choices=["concise", "full"],
        default="concise",
        help="Question set size. Concise asks the highest-value missing questions.",
    )
    parser.add_argument(
        "--mapping",
        action="store_true",
        help="Include the `design_brief.user_intake` template and field mapping.",
    )
    parser.add_argument(
        "--codex-ui",
        action="store_true",
        help="Emit a request_user_input-compatible JSON packet for Codex's native question card.",
    )
    parser.add_argument("--output", help="Optional output path")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else None
    prompt = (
        render_codex_ui_spec(workspace=workspace, user_prompt=args.user_prompt, mode=args.mode)
        if args.codex_ui
        else render_prompt(
            workspace=workspace,
            user_prompt=args.user_prompt,
            mode=args.mode,
            include_mapping=args.mapping,
        )
    )

    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(prompt, encoding="utf-8")
        print(f"Deck intake prompt written to {output}", file=sys.stderr)
    else:
        print(prompt, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
