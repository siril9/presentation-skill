#!/usr/bin/env python3
"""Pure, optional deck intake and caller-signaled usage choices. No model calls."""

from __future__ import annotations

import math
import re
from typing import Any


LOW_USAGE_PERCENT = 10
FIELDS = ("audience", "purpose", "evidence", "style")
ANSWER_ALIASES = {
    "audience_context": "audience", "target_outcome": "purpose",
    "evidence_assets": "evidence", "source_policy": "evidence",
    "style_direction": "style", "style_density": "style",
    "visual_source_policy": "evidence",
}
DEFAULTS = {
    "audience": "General professional audience.",
    "purpose": "Explain the topic without inventing a decision or recommendation.",
    "evidence": "Use supplied evidence; label gaps and synthetic examples; invent no facts or citations.",
    "style": "Use a topic-fit route; no extra style audition by default.",
}
QUESTIONS = {
    "audience": "Who will use this deck, and what do they already know?",
    "purpose": "What decision or outcome should this deck support?",
    "evidence": "Which sources or data should support the claims?",
    "style": "Which reference or brand requirements should the deck follow?",
}
# Only explicit signals suppress a question; structured answers take precedence.
ANSWER_SIGNALS = {
    "audience": r"\baudience\s*[:=]|\bfor\s+(?:the\s+)?(?:board|investors?|executives?|students?|patients?|clinicians?|researchers?|engineers?|staff|managers?|beginners?|experts?|children|general public)\b",
    "purpose": r"\b(?:purpose|goal|outcome)\s*[:=]|\b(?:explain|teach|inform|persuade|recommend|approve|train|educate|pitch|decide|compare)\b",
    "evidence": r"\b(?:evidence|sources?|data)\s*[:=]|\b(?:attached|provided|supplied|synthetic|illustrative|no data|no sources|primary sources|official sources)\b|\.(?:csv|xlsx|pdf)\b",
    "style": r"\bstyle\s*[:=]|\b(?:minimalist|editorial|lab-report|monochrome|dark theme|light theme)\b|\b(?:use|match|follow)\s+(?:the\s+)?(?:brand|reference|template|existing|attached)\b",
}


def _usage_choice(remaining_percent: float | None, current_model: str | None,
                  available_models: list[str] | None) -> dict[str, Any] | None:
    if remaining_percent is None:
        return None
    if isinstance(remaining_percent, bool) or not isinstance(remaining_percent, (int, float)) or not math.isfinite(remaining_percent) or not 0 <= remaining_percent <= 100:
        raise ValueError("remaining_percent must be a finite number from 0 to 100, or omitted when unavailable.")
    if available_models is not None and (not isinstance(available_models, list) or not all(isinstance(model, str) for model in available_models)):
        raise ValueError("available_models must be a caller-supplied list of model names.")
    current = str(current_model or "").strip().lower()
    if remaining_percent > LOW_USAGE_PERCENT or current in {"luna", "gpt-6-luna", "gpt-5.6-luna"}:
        return None
    available = {model.strip().lower() for model in (available_models or [])}
    luna = next((name for name in ("gpt-6-luna", "gpt-5.6-luna", "luna") if name in available), None)
    alternative = (
        {"id": "luna", "label": "Use Luna with the same QA", "model": luna, "profile": "fast"}
        if luna else
        {"id": "fast_profile", "label": "Use the fast workflow on the current model", "profile": "fast"}
    )
    return {
        "basis": "caller_supplied_remaining_percent", "remaining_percent": remaining_percent,
        "default": "current", "selection_required_for_change": True, "automatic_switch": False,
        "options": [{"id": "current", "label": "Keep the current model and workflow"}, alternative],
        "qa_target": "unchanged",
        "note": "No usage lookup, model switch, access guarantee, or usage-saving claim. Apply a change only after the user chooses it.",
    }


def normalize_intake_answers(answers: dict[str, str] | None) -> dict[str, str]:
    """Canonicalize actual answers, without filling in inferred answers or defaults."""
    if answers is not None and not isinstance(answers, dict):
        raise ValueError("answers must be a JSON object with audience, purpose, evidence, or style text.")
    resolved = {}
    for key, value in (answers or {}).items():
        field = ANSWER_ALIASES.get(key, key)
        if field not in FIELDS or not isinstance(value, str):
            raise ValueError(f"Unsupported answer {key!r}; use audience, purpose, evidence, or style text.")
        if value.strip():
            resolved[field] = value.strip()
    return resolved


def intake_authoring_prompt(prompt: str, answers: dict[str, str] | None,
                            *, explicit_style: str = "") -> str:
    resolved = normalize_intake_answers(answers)
    if not resolved:
        return str(prompt or "")
    if explicit_style:
        resolved["style"] = explicit_style
    details = "\n".join(f"{field.title()}: {resolved[field]}" for field in FIELDS if field in resolved)
    return (
        f"{prompt}\n\nIntake answers refine the request and supersede earlier answers for these fields:\n{details}"
        + ("\nThe explicit style preset takes precedence over the intake style answer." if explicit_style else "")
    ).strip()


def build_deck_intake(
    prompt: str,
    *,
    answers: dict[str, str] | None = None,
    remaining_percent: float | None = None,
    current_model: str | None = None,
    available_models: list[str] | None = None,
) -> dict[str, Any]:
    """Offer up to three consequential clarifications, never a permission gate."""
    resolved = normalize_intake_answers(answers)
    text = str(prompt or "")
    for field, pattern in ANSWER_SIGNALS.items():
        if field not in resolved and re.search(pattern, text, re.IGNORECASE):
            resolved[field] = "Specified in the request; preserve it."
    consequential = bool(re.search(r"\b(?:decision|board|investor|clinical|regulatory|scientific|publication|external|public release|fundraising|grant|budget|training)\b", text, re.IGNORECASE))
    material = {
        "audience": consequential,
        "purpose": consequential,
        "evidence": consequential or bool(re.search(r"\b(?:evidence|data|chart|statistics|source-backed|claims)\b", text, re.IGNORECASE)),
        "style": bool(re.search(r"\b(?:brand|reference|template|redesign|match)\b", text, re.IGNORECASE)),
    }
    questions = [
        {"id": field, "question": QUESTIONS[field]}
        for field in FIELDS if material[field] and field not in resolved
    ][:3]
    result = {
        "action": "proceed_with_assumptions",
        "questions_optional": True,
        "questions": questions,
        "answered": resolved,
        "assumptions": {field: DEFAULTS[field] for field in FIELDS if field not in resolved},
        "policy": "Ask only if the answer would materially change the deck. Do not repeat answered questions or request routine permission; otherwise proceed with these assumptions.",
    }
    choice = _usage_choice(remaining_percent, current_model, available_models)
    if choice:
        result["usage_choice"] = choice
    return result
