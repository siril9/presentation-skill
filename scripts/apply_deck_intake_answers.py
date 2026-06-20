#!/usr/bin/env python3
"""Persist first-turn deck intake answers into workspace planning files.

This helper keeps the question-card step reproducible. It accepts a compact
answers JSON payload, optionally paired with the deck-start packet, then writes
the durable planning layer that agents otherwise have to remember to apply by
hand: design_brief.user_intake, a deterministic style seed, light design
translation hints, source policy, asset posture, audience, and notes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from emit_design_contract_prompt import _stable_id  # noqa: E402


INTAKE_FIELDS = (
    "audience_context",
    "target_outcome",
    "style_direction",
    "density",
    "palette",
    "background_visuals",
    "evidence_assets",
    "source_policy",
    "constraints",
)

COMPRESSED_FIELDS = (
    "style_density",
    "visual_source_policy",
)

NOTE_START = "<!-- deck-intake-answers:start -->"
NOTE_END = "<!-- deck-intake-answers:end -->"

PLACEHOLDER_FRAGMENTS = (
    "replace with",
    "topic-specific opener chosen",
    "large topic-specific title",
    "deck author using the presentation-skill workspace scaffold",
    "prefer primary or source-backed facts. do not fabricate citations.",
)


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def _write_json_if_changed(path: Path, payload: Any, *, dry_run: bool) -> bool:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return True


def _write_text_if_changed(path: Path, text: str, *, dry_run: bool) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return True


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(workspace: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _file_snapshot(workspace: Path, path: Path | None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "path": _display_path(workspace, path),
        "exists": bool(path and path.exists()),
    }
    if path and path.exists() and path.is_file():
        payload = path.read_bytes()
        snapshot["size_bytes"] = len(payload)
        snapshot["sha256"] = hashlib.sha256(payload).hexdigest()
    return snapshot


def _answer_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    if isinstance(value, dict):
        for key in ("answer", "value", "label", "text", "selected", "response"):
            text = _answer_text(value.get(key))
            if text:
                return text
        if "option" in value:
            return _answer_text(value.get("option"))
        return "; ".join(
            f"{key}: {_answer_text(item)}"
            for key, item in value.items()
            if _answer_text(item)
        ).strip()
    if isinstance(value, list):
        return "; ".join(text for text in (_answer_text(item) for item in value) if text)
    return ""


def _extract_answer_items(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise SystemExit("Answers JSON must be an object.")

    candidates: list[Any] = [payload]
    for key in ("answers", "responses", "result", "data"):
        value = payload.get(key)
        if isinstance(value, (dict, list)):
            candidates.append(value)

    answers: dict[str, str] = {}
    known = set(INTAKE_FIELDS) | set(COMPRESSED_FIELDS) | {"answered_by", "unanswered"}

    for candidate in candidates:
        if isinstance(candidate, dict):
            for key, value in candidate.items():
                if key in known:
                    text = _answer_text(value)
                    if text:
                        answers[key] = text
        elif isinstance(candidate, list):
            for item in candidate:
                if not isinstance(item, dict):
                    continue
                key = _answer_text(item.get("id") or item.get("question_id") or item.get("name"))
                if key in known:
                    text = _answer_text(
                        item.get("answer")
                        if "answer" in item
                        else item.get("value")
                        if "value" in item
                        else item.get("label")
                    )
                    if text:
                        answers[key] = text

    return answers


def _packet_question_ids(packet: Any) -> list[str]:
    if not isinstance(packet, dict):
        return []
    request = packet.get("request_user_input")
    questions = request.get("questions") if isinstance(request, dict) else None
    if not isinstance(questions, list):
        return []
    ids: list[str] = []
    for item in questions:
        if isinstance(item, dict):
            qid = str(item.get("id") or "").strip()
            if qid:
                ids.append(qid)
    return ids


def _derive_from_style_density(text: str) -> dict[str, str]:
    lower = text.lower()
    updates: dict[str, str] = {"style_density": text}
    if "figure" in lower or "report" in lower or "leave" in lower:
        updates.setdefault("style_direction", text)
        updates.setdefault("density", "dense report/leave-behind")
        updates["design_dna"] = "lab results dashboard"
        updates["figure_table_treatment"] = "figure-first"
    elif "conference" in lower or "talk" in lower:
        updates.setdefault("style_direction", text)
        updates.setdefault("density", "sparse live-talk / presenter-led")
        updates["design_dna"] = "technical educational"
        updates["figure_table_treatment"] = "image-sidebar"
    elif "editorial" in lower or "premium" in lower:
        updates.setdefault("style_direction", text)
        updates.setdefault("density", "balanced editorial report")
        updates["design_dna"] = "editorial report"
        updates["figure_table_treatment"] = "image-sidebar"
    else:
        updates.setdefault("style_direction", text)
    return updates


def _derive_from_visual_source_policy(text: str) -> dict[str, str]:
    lower = text.lower()
    updates: dict[str, str] = {"visual_source_policy": text}
    if "strict" in lower or "every factual" in lower:
        updates.setdefault("source_policy", "source every factual claim")
        updates.setdefault("palette", "restrained neutral/lab palette")
        updates.setdefault("background_visuals", "clean white report with source-backed evidence visuals")
        updates.setdefault("evidence_assets", "prefer provided, local, or source-backed figures and tables")
    elif "custom" in lower or "user-provided" in lower or "provided" in lower:
        updates.setdefault("source_policy", "use only provided sources until approved")
        updates.setdefault("palette", "wait for user-provided palette or reference deck")
        updates.setdefault("background_visuals", "defer to provided assets and reference style")
        updates.setdefault("evidence_assets", "pause for user-provided figures, logos, screenshots, data, or reference decks")
    else:
        updates.setdefault("source_policy", "cite key claims")
        updates.setdefault("palette", "restrained palette chosen by best judgment")
        updates.setdefault("background_visuals", "clean report with source-backed or generated visuals only when useful")
        updates.setdefault("evidence_assets", "use local/generated figures when data exists; otherwise use source-backed visuals selectively")
    return updates


def _is_replaceable_existing(value: Any, *, overwrite: bool) -> bool:
    if overwrite or value in (None, "", [], {}):
        return True
    if isinstance(value, str):
        lower = value.strip().lower()
        return any(fragment in lower for fragment in PLACEHOLDER_FRAGMENTS)
    return False


def _merge_missing(target: dict[str, Any], updates: dict[str, Any], *, overwrite: bool) -> list[str]:
    changed: list[str] = []
    for key, value in updates.items():
        if value in (None, "", [], {}):
            continue
        if _is_replaceable_existing(target.get(key), overwrite=overwrite):
            if target.get(key) != value:
                target[key] = value
                changed.append(key)
    return changed


def _normalize_unanswered(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _answer_text(value)
    if not text:
        return []
    return [part.strip() for part in text.replace("\n", ",").split(",") if part.strip()]


def _build_user_intake(
    *,
    answers: dict[str, str],
    packet: Any,
    answered_by: str,
    stable_prompt_id: str,
) -> dict[str, Any]:
    derived: dict[str, str] = {}
    if answers.get("style_density"):
        derived.update(_derive_from_style_density(answers["style_density"]))
    if answers.get("visual_source_policy"):
        for key, value in _derive_from_visual_source_policy(answers["visual_source_policy"]).items():
            derived.setdefault(key, value)
    for key in INTAKE_FIELDS:
        if answers.get(key):
            derived[key] = answers[key]

    packet_question_ids = _packet_question_ids(packet)
    missing_question_ids = [qid for qid in packet_question_ids if not answers.get(qid)]
    unanswered = _normalize_unanswered(answers.get("unanswered"))
    for qid in missing_question_ids:
        if qid not in unanswered:
            unanswered.append(qid)

    intake: dict[str, Any] = {
        key: derived.get(key, "")
        for key in INTAKE_FIELDS
    }
    intake["answered_by"] = answered_by
    intake["unanswered"] = unanswered
    intake["codex_ui_answers"] = {
        key: answers[key]
        for key in COMPRESSED_FIELDS
        if answers.get(key)
    }
    if stable_prompt_id:
        intake["stable_prompt_id"] = stable_prompt_id
    return intake


def _packet_choice_contract(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    value = packet.get("choice_resolution_contract")
    return value if isinstance(value, dict) else {}


def _packet_route_ledger(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    value = packet.get("route_decision_ledger")
    return value if isinstance(value, dict) else {}


def _packet_source_inventory(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    value = packet.get("workspace_source_inventory")
    return value if isinstance(value, dict) else {}


def _route_ledger_status(route_ledger: dict[str, Any]) -> dict[str, bool]:
    routes = route_ledger.get("routes")
    if not isinstance(routes, list):
        return {}
    return {
        str(item.get("id") or "").strip(): bool(item.get("active"))
        for item in routes
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _choice_ledger_by_id(choice_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ledger = choice_contract.get("choice_ledger")
    if not isinstance(ledger, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for item in ledger:
        if not isinstance(item, dict):
            continue
        choice_id = str(item.get("id") or "").strip()
        if choice_id:
            by_id[choice_id] = item
    return by_id


def _route_decisions_from(packet: Any, choice_contract: dict[str, Any]) -> list[dict[str, Any]]:
    route_items = choice_contract.get("route_decisions")
    if isinstance(route_items, list):
        routes: list[dict[str, Any]] = []
        for item in route_items:
            if not isinstance(item, dict):
                continue
            route_id = str(item.get("id") or "").strip()
            if not route_id:
                continue
            copied = dict(item)
            copied["id"] = route_id
            if "active" in copied:
                copied["active"] = bool(copied.get("active"))
            routes.append(copied)
        if routes:
            return routes

    application_contract = (
        packet.get("application_contract") if isinstance(packet, dict) else {}
    )
    if not isinstance(application_contract, dict):
        return []
    return [
        {
            "id": "data_artifacts",
            "active": bool(application_contract.get("data_artifacts_likely")),
            "trigger_evidence": "copied from deck_start_packet.application_contract.data_artifacts_likely",
        },
        {
            "id": "pptx_style_import",
            "active": bool(application_contract.get("pptx_style_likely")),
            "trigger_evidence": "copied from deck_start_packet.application_contract.pptx_style_likely",
        },
    ]


def _build_choice_resolution_seed(
    *,
    user_intake: dict[str, Any],
    packet: Any,
    stable_prompt_id: str,
) -> dict[str, Any]:
    choice_contract = _packet_choice_contract(packet)
    route_ledger = _packet_route_ledger(packet)
    source_inventory = _packet_source_inventory(packet)
    route_ledger_status = _route_ledger_status(route_ledger)
    ledger_by_id = _choice_ledger_by_id(choice_contract)
    compressed = (
        user_intake.get("codex_ui_answers")
        if isinstance(user_intake.get("codex_ui_answers"), dict)
        else {}
    )
    choice_specs = [
        (
            "audience_context",
            _answer_text(user_intake.get("audience_context")),
            [
                "design_brief.user_intake",
                "content_plan.audience",
                "readability_contract",
            ],
        ),
        (
            "style_density",
            _answer_text(compressed.get("style_density"))
            or _answer_text(user_intake.get("style_direction"))
            or _answer_text(user_intake.get("density")),
            [
                "design_modulation",
                "style_system.style_mix_matrix",
                "structure_blueprint.slide_variant_mix",
            ],
        ),
        (
            "visual_source_policy",
            _answer_text(compressed.get("visual_source_policy"))
            or _answer_text(user_intake.get("source_policy")),
            [
                "evidence_plan.source_policy",
                "asset_posture",
                "analysis_artifact_plan",
                "figure_export_contract",
            ],
        ),
    ]
    resolved_choices: list[dict[str, Any]] = []
    for choice_id, answer, fallback_fields in choice_specs:
        if not answer:
            continue
        ledger = ledger_by_id.get(choice_id, {})
        resolved_choices.append(
            {
                "id": choice_id,
                "answer": answer,
                "locks": ledger.get("locks", []),
                "source_fields": ledger.get("source_fields", fallback_fields),
                "contract_fields": ledger.get("contract_fields", fallback_fields),
            }
        )

    if not resolved_choices and not choice_contract and not route_ledger:
        return {}

    requirements = (
        choice_contract.get("contract_requirements")
        if isinstance(choice_contract.get("contract_requirements"), dict)
        else {}
    )
    seed = {
        "contract_version": "deck_choice_resolution_v1",
        "seed_kind": "resolved_intake_answers",
        "source_contract_version": choice_contract.get("contract_version", ""),
        "stable_prompt_id": stable_prompt_id,
        "answered_by": user_intake.get("answered_by", ""),
        "resolved_choices": resolved_choices,
        "route_decisions": _route_decisions_from(packet, choice_contract),
        "design_fields_locked": requirements.get(
            "design_contract_fields",
            [
                "choice_resolution",
                "style_system.style_mix_matrix",
                "readability_contract",
                "evidence_plan.source_policy",
                "analysis_artifact_plan",
                "figure_export_contract",
            ],
        ),
        "replay_inputs": {
            "answers": "intake_answers.json",
            "packet": "deck_start_packet.json",
            "applied_to": "design_brief.choice_resolution_seed",
        },
    }
    if route_ledger:
        seed["route_decision_ledger"] = route_ledger
        seed["route_ledger_version"] = str(route_ledger.get("ledger_version") or "")
        seed["route_ledger_active_routes"] = sorted(
            route_id for route_id, active in route_ledger_status.items() if active
        )
        seed["replay_inputs"]["route_decision_ledger"] = "deck_start_packet.json:route_decision_ledger"
    if source_inventory:
        seed["workspace_source_inventory"] = source_inventory
        seed["replay_inputs"]["workspace_source_inventory"] = "deck_start_packet.json:workspace_source_inventory"
    return seed


def _style_seed_from(packet: Any, user_prompt: str) -> str:
    if isinstance(packet, dict):
        for key in ("recommended_style_seed", "stable_prompt_id"):
            value = str(packet.get(key) or "").strip()
            if value:
                return value
    if user_prompt.strip():
        return _stable_id(user_prompt.strip())
    return ""


def _replace_notes_section(existing: str, section: str) -> str:
    if NOTE_START in existing and NOTE_END in existing:
        before = existing.split(NOTE_START, 1)[0].rstrip()
        after = existing.split(NOTE_END, 1)[1].lstrip()
        parts = [part for part in (before, section.rstrip(), after.rstrip()) if part]
        return "\n\n".join(parts) + "\n"
    prefix = existing.rstrip()
    return (prefix + "\n\n" if prefix else "") + section.rstrip() + "\n"


def _notes_section(
    user_intake: dict[str, Any],
    *,
    style_seed: str,
    choice_resolution_seed: dict[str, Any],
) -> str:
    lines = [
        NOTE_START,
        "## Deck Intake Answers",
        "",
    ]
    if style_seed:
        lines.append(f"- Stable style seed: `{style_seed}`")
    lines.append(f"- Answered by: {user_intake.get('answered_by', '')}")
    unanswered = user_intake.get("unanswered")
    if unanswered:
        lines.append(f"- Unanswered: {', '.join(str(item) for item in unanswered)}")
    else:
        lines.append("- Unanswered: none")
    lines.extend(["", "### Persisted Answers"])
    for key in INTAKE_FIELDS:
        value = _answer_text(user_intake.get(key))
        if value:
            lines.append(f"- {key}: {value}")
    compressed = user_intake.get("codex_ui_answers")
    if isinstance(compressed, dict) and compressed:
        lines.extend(["", "### Question Card Answers"])
        for key in COMPRESSED_FIELDS:
            value = _answer_text(compressed.get(key))
            if value:
                lines.append(f"- {key}: {value}")
    if choice_resolution_seed:
        lines.extend(["", "### Choice Resolution Seed"])
        version = _answer_text(choice_resolution_seed.get("contract_version"))
        if version:
            lines.append(f"- Choice contract: {version}")
        choices = []
        for item in choice_resolution_seed.get("resolved_choices", []):
            if isinstance(item, dict):
                choice_id = _answer_text(item.get("id"))
                answer = _answer_text(item.get("answer"))
                if choice_id and answer:
                    choices.append(f"{choice_id}: {answer}")
        if choices:
            lines.append(f"- Resolved choices: {', '.join(choices)}")
        routes = []
        for item in choice_resolution_seed.get("route_decisions", []):
            if not isinstance(item, dict):
                continue
            route_id = _answer_text(item.get("id"))
            if not route_id:
                continue
            active = item.get("active")
            if isinstance(active, bool):
                routes.append(f"{route_id}={'active' if active else 'inactive'}")
            else:
                routes.append(route_id)
        if routes:
            lines.append(f"- Route decisions: {', '.join(routes)}")
        route_ledger = choice_resolution_seed.get("route_decision_ledger")
        route_status = _route_ledger_status(route_ledger if isinstance(route_ledger, dict) else {})
        if route_status:
            route_summary = [
                f"{route_id}={'active' if active else 'inactive'}"
                for route_id, active in sorted(route_status.items())
            ]
            lines.append(f"- Route ledger: {', '.join(route_summary)}")
        source_inventory = choice_resolution_seed.get("workspace_source_inventory")
        if isinstance(source_inventory, dict):
            data_count = int(source_inventory.get("data_file_count") or 0)
            pptx_count = int(source_inventory.get("reference_pptx_count") or 0)
            ledger_count = int(source_inventory.get("artifact_ledger_count") or 0)
            lines.append(
                "- Source inventory: "
                f"data_files={data_count}, reference_pptx={pptx_count}, "
                f"artifact_ledgers={ledger_count}"
            )
    lines.append(NOTE_END)
    return "\n".join(lines) + "\n"


def apply_answers(
    *,
    workspace: Path,
    answers_path: Path,
    packet_path: Path | None,
    user_prompt: str,
    answered_by_override: str | None,
    overwrite_translations: bool,
    dry_run: bool,
) -> dict[str, Any]:
    answers_payload = _load_json(answers_path, {})
    answers = _extract_answer_items(answers_payload)
    packet = _load_json(packet_path, {}) if packet_path is not None else {}
    style_seed = _style_seed_from(packet, user_prompt)
    answered_by = (
        answered_by_override
        or answers.get("answered_by")
        or _answer_text(answers_payload.get("answered_by") if isinstance(answers_payload, dict) else None)
        or "user"
    )
    if answered_by not in {"user", "inferred", "best_judgment"}:
        answered_by = "user"

    user_intake = _build_user_intake(
        answers=answers,
        packet=packet,
        answered_by=answered_by,
        stable_prompt_id=style_seed,
    )
    choice_resolution_seed = _build_choice_resolution_seed(
        user_intake=user_intake,
        packet=packet,
        stable_prompt_id=style_seed,
    )

    changed_files: list[str] = []
    touched_fields: dict[str, list[str]] = {}

    design_path = workspace / "design_brief.json"
    design = _load_json(design_path, {})
    if not isinstance(design, dict):
        raise SystemExit(f"{design_path} must contain a JSON object.")
    design["user_intake"] = user_intake
    if choice_resolution_seed:
        design["choice_resolution_seed"] = choice_resolution_seed
        touched_fields.setdefault("design_brief.json", []).append("choice_resolution_seed")
    if style_seed:
        style_system = design.get("style_system")
        if not isinstance(style_system, dict):
            style_system = {}
            design["style_system"] = style_system
        if style_system.get("style_seed") != style_seed:
            style_system["style_seed"] = style_seed
            touched_fields.setdefault("design_brief.json", []).append("style_system.style_seed")

    style_direction = _answer_text(user_intake.get("style_direction"))
    density = _answer_text(user_intake.get("density"))
    palette = _answer_text(user_intake.get("palette"))
    background = _answer_text(user_intake.get("background_visuals"))
    source_policy = _answer_text(user_intake.get("source_policy"))
    evidence_assets = _answer_text(user_intake.get("evidence_assets"))

    design_modulation = design.get("design_modulation")
    if not isinstance(design_modulation, dict):
        design_modulation = {}
        design["design_modulation"] = design_modulation
    modulation_updates = {
        "change_intensity": "subtle",
        "density_strategy": density,
        "accent_strategy": palette,
        "figure_table_treatment": "figure-first"
        if "figure" in style_direction.lower() or "report" in style_direction.lower()
        else "",
        "container_strategy": "evidence-first layouts before generic cards"
        if evidence_assets or "report" in style_direction.lower()
        else "",
    }
    changed = _merge_missing(design_modulation, modulation_updates, overwrite=overwrite_translations)
    if changed:
        touched_fields.setdefault("design_brief.json", []).extend(f"design_modulation.{key}" for key in changed)

    visual_system = design.get("visual_system")
    if not isinstance(visual_system, dict):
        visual_system = {}
        design["visual_system"] = visual_system
    visual_updates = {
        "palette_direction": palette,
        "background_visuals": background,
        "source_policy": source_policy,
        "evidence_assets": evidence_assets,
    }
    changed = _merge_missing(visual_system, visual_updates, overwrite=overwrite_translations)
    if changed:
        touched_fields.setdefault("design_brief.json", []).extend(f"visual_system.{key}" for key in changed)

    title_page = design.get("title_page_concept")
    if not isinstance(title_page, dict):
        title_page = {}
        design["title_page_concept"] = title_page
    title_updates = {
        "chosen_archetype": "lab-plate" if "figure" in style_direction.lower() or "report" in style_direction.lower() else "editorial masthead",
        "dominant_element": style_direction or "topic-specific opening idea",
        "supporting_element": background or evidence_assets or "audience-specific context",
    }
    changed = _merge_missing(title_page, title_updates, overwrite=overwrite_translations)
    if changed:
        touched_fields.setdefault("design_brief.json", []).extend(f"title_page_concept.{key}" for key in changed)

    renderer = design.get("renderer_treatments")
    if not isinstance(renderer, dict):
        renderer = {}
        design["renderer_treatments"] = renderer
    renderer_updates = {
        "header_mode": "lab-clean" if "figure" in style_direction.lower() or "report" in style_direction.lower() else "",
        "header_variant": "auto" if "figure" in style_direction.lower() or "report" in style_direction.lower() else "",
        "footer_mode": "source-line" if source_policy else "",
        "figure_table_treatment": "figure-first" if "figure" in style_direction.lower() or "report" in style_direction.lower() else "",
    }
    changed = _merge_missing(renderer, renderer_updates, overwrite=overwrite_translations)
    if changed:
        touched_fields.setdefault("design_brief.json", []).extend(f"renderer_treatments.{key}" for key in changed)

    if _write_json_if_changed(design_path, design, dry_run=dry_run):
        changed_files.append(str(design_path))

    content_path = workspace / "content_plan.json"
    content = _load_json(content_path, {})
    if not isinstance(content, dict):
        raise SystemExit(f"{content_path} must contain a JSON object.")
    content_updates = {
        "audience": _answer_text(user_intake.get("audience_context")),
        "decision_target": _answer_text(user_intake.get("target_outcome")),
    }
    changed = _merge_missing(content, content_updates, overwrite=overwrite_translations)
    if changed:
        touched_fields["content_plan.json"] = changed
    if _write_json_if_changed(content_path, content, dry_run=dry_run):
        changed_files.append(str(content_path))

    evidence_path = workspace / "evidence_plan.json"
    evidence = _load_json(evidence_path, {})
    if not isinstance(evidence, dict):
        raise SystemExit(f"{evidence_path} must contain a JSON object.")
    changed = _merge_missing(evidence, {"source_policy": source_policy}, overwrite=overwrite_translations)
    if changed:
        touched_fields["evidence_plan.json"] = changed
    if _write_json_if_changed(evidence_path, evidence, dry_run=dry_run):
        changed_files.append(str(evidence_path))

    asset_path = workspace / "asset_plan.json"
    asset = _load_json(asset_path, {})
    if not isinstance(asset, dict):
        raise SystemExit(f"{asset_path} must contain a JSON object.")
    asset_posture = asset.get("asset_posture")
    if not isinstance(asset_posture, dict):
        asset_posture = {}
        asset["asset_posture"] = asset_posture
    asset_updates = {
        "palette": palette,
        "background_visuals": background,
        "evidence_assets": evidence_assets,
        "source_policy": source_policy,
    }
    changed = _merge_missing(asset_posture, asset_updates, overwrite=overwrite_translations)
    if changed:
        touched_fields["asset_plan.json"] = [f"asset_posture.{key}" for key in changed]
    if _write_json_if_changed(asset_path, asset, dry_run=dry_run):
        changed_files.append(str(asset_path))

    notes_path = workspace / "notes.md"
    existing_notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    new_notes = _replace_notes_section(
        existing_notes,
        _notes_section(
            user_intake,
            style_seed=style_seed,
            choice_resolution_seed=choice_resolution_seed,
        ),
    )
    if _write_text_if_changed(notes_path, new_notes, dry_run=dry_run):
        changed_files.append(str(notes_path))

    return {
        "workflow": "deck_intake_answers_apply_v1",
        "workspace": str(workspace),
        "answers_path": str(answers_path),
        "packet_path": str(packet_path) if packet_path is not None else None,
        "answers_sha256": _file_sha256(answers_path) if answers_path.exists() else "",
        "packet_sha256": _file_sha256(packet_path) if packet_path is not None and packet_path.exists() else "",
        "answers_snapshot": _file_snapshot(workspace, answers_path),
        "packet_snapshot": _file_snapshot(workspace, packet_path),
        "stable_prompt_id": style_seed,
        "answered_by": answered_by,
        "user_intake": user_intake,
        "choice_resolution_seed": choice_resolution_seed,
        "choice_resolution_seed_applied": bool(choice_resolution_seed),
        "changed_files": changed_files,
        "changed_file_count": len(changed_files),
        "touched_fields": touched_fields,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Persist deck intake answers into reusable workspace planning files."
    )
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument("--answers", required=True, help="JSON file with question-card answers")
    parser.add_argument("--packet", help="Optional deck_start_packet.json from emit_deck_start_packet.py")
    parser.add_argument("--user-prompt", default="", help="Original user request, used only if no packet seed exists")
    parser.add_argument(
        "--answered-by",
        choices=["user", "inferred", "best_judgment"],
        help="Override answer provenance stored in design_brief.user_intake",
    )
    parser.add_argument(
        "--overwrite-translations",
        action="store_true",
        help="Overwrite existing derived design/evidence/asset fields instead of only filling blanks.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Emit report without writing files")
    parser.add_argument("--report", help="Optional path for JSON report")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    answers_path = Path(args.answers).expanduser().resolve()
    packet_path = Path(args.packet).expanduser().resolve() if args.packet else None

    report = apply_answers(
        workspace=workspace,
        answers_path=answers_path,
        packet_path=packet_path,
        user_prompt=args.user_prompt,
        answered_by_override=args.answered_by,
        overwrite_translations=args.overwrite_translations,
        dry_run=args.dry_run,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
