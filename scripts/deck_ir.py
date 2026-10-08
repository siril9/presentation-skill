#!/usr/bin/env python3
"""Versioned, renderer-neutral Deck IR utilities and CLI."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


IR_VERSION = "1.0.0"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "deck_ir.schema.json"

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_STABLE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[-_.][a-z0-9]+)*$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SOURCE_REF_RE = re.compile(r"^(/(?:[^~/]|~[01])*)+$")
_SLIDE_SOURCE_REF_RE = re.compile(r"^/slides/(?:0|[1-9]\d*)(?P<local>/.*)?$")

_INTENT_PURPOSES = {
    "introduce",
    "inform",
    "explain",
    "compare",
    "evidence",
    "persuade",
    "decide",
    "navigate",
    "summarize",
    "process",
}
_VISUAL_INTENTS = {
    "none",
    "hero",
    "timeline",
    "comparison",
    "flow",
    "data",
    "diagram",
    "image",
    "table",
}
_SLIDE_ROLES = {
    "title",
    "section",
    "content",
    "evidence",
    "comparison",
    "data",
    "process",
    "decision",
    "references",
    "closing",
}
_ELEMENT_ROLES = {
    "title",
    "subtitle",
    "heading",
    "body",
    "list",
    "callout",
    "metric",
    "evidence",
    "citation",
    "image",
    "chart",
    "table",
    "diagram",
    "decision",
    "navigation",
    "decoration",
}
_EDITABLE_OBJECT_KINDS = {
    "text",
    "image",
    "chart",
    "table",
    "diagram",
    "shape",
    "group",
    "media",
}
_EVIDENCE_KINDS = {"source", "data", "image", "analysis", "quote"}
_CONSTRAINT_KINDS = {
    "reading_order",
    "keep_together",
    "must_include",
    "must_precede",
    "max_count",
    "min_count",
    "aspect_ratio",
    "content_length",
    "editable",
    "evidence_required",
    "visual_priority",
}
_CONSTRAINT_STRENGTHS = {"required", "preferred"}
_CONSTRAINT_UNITS = {"characters", "items", "ratio", "rank"}

Migration = Callable[[dict[str, Any]], dict[str, Any]]
_MIGRATIONS: dict[tuple[str, str], Migration] = {}


class DeckIRError(ValueError):
    """Base error for Deck IR operations."""


class DeckIRValidationError(DeckIRError):
    """Raised when a Deck IR document violates the current contract."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(errors)
        super().__init__("Deck IR validation failed:\n- " + "\n- ".join(self.errors))


class DeckIRMigrationError(DeckIRError):
    """Raised when no valid, explicit migration path exists."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise DeckIRError(f"Value is not canonical JSON data: {exc}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes with sorted keys and no whitespace."""

    return _canonical_json(value).encode("utf-8")


def canonicalize_deck_ir(document: Mapping[str, Any], *, validate: bool = True) -> str:
    """Return the deterministic canonical JSON form of a Deck IR document."""

    if validate:
        validate_deck_ir(document)
    return _canonical_json(document)


def deck_ir_sha256(document: Mapping[str, Any], *, validate: bool = True) -> str:
    """Hash the canonical Deck IR bytes with SHA-256."""

    return hashlib.sha256(
        canonicalize_deck_ir(document, validate=validate).encode("utf-8")
    ).hexdigest()


def _slug(value: Any, *, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text or not text[0].isalpha():
        text = f"{fallback}-{text}".strip("-")
    return text[:40].rstrip("-") or fallback


def stable_id(kind: str, *identity_parts: Any) -> str:
    """Build a readable ID that is stable for the supplied logical identity."""

    kind_slug = _slug(kind, fallback="object")
    identity = [str(part) if isinstance(part, Path) else part for part in identity_parts]

    def label_text(part: Any) -> str:
        if isinstance(part, (Mapping, list, tuple)):
            return _canonical_json(part)
        return str(part)

    label = next(
        (label_text(part) for part in reversed(identity) if label_text(part).strip()),
        kind_slug,
    )
    label_slug = _slug(label, fallback=kind_slug)
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:12]
    return f"{kind_slug}-{label_slug}-{digest}"


def _json_pointer(base: str, token: str | int) -> str:
    escaped = str(token).replace("~", "~0").replace("/", "~1")
    return f"{base}/{escaped}"


def _nonempty_text(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _first_text(payload: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        text = _nonempty_text(payload.get(key))
        if text:
            return text
    return ""


def _validate_keys(
    value: Any,
    *,
    path: str,
    required: set[str],
    allowed: set[str],
    errors: list[str],
) -> bool:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return False
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        errors.append(f"{path} is missing required fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{path} has unknown fields: {', '.join(unknown)}")
    return not missing and not unknown


def _validate_nonempty_string(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{path} must be a non-empty string")


def _validate_stable_id(value: Any, path: str, errors: list[str]) -> None:
    if (
        not isinstance(value, str)
        or len(value) > 96
        or _STABLE_ID_RE.fullmatch(value) is None
    ):
        errors.append(f"{path} must be a stable lowercase ID")


def _validate_source_ref(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _SOURCE_REF_RE.fullmatch(value) is None:
        errors.append(f"{path} must be a non-root JSON Pointer")


def _validate_intent(value: Any, path: str, errors: list[str]) -> None:
    required = {"purpose"}
    allowed = required | {"message", "audience", "outcome", "visual_intent"}
    if not _validate_keys(
        value, path=path, required=required, allowed=allowed, errors=errors
    ):
        return
    purpose = value.get("purpose")
    if purpose not in _INTENT_PURPOSES:
        errors.append(f"{path}.purpose is not supported in IR {IR_VERSION}")
    for key in ("message", "audience", "outcome"):
        if key in value:
            _validate_nonempty_string(value[key], f"{path}.{key}", errors)
    if "visual_intent" in value and value["visual_intent"] not in _VISUAL_INTENTS:
        errors.append(f"{path}.visual_intent is not supported in IR {IR_VERSION}")


def _validate_evidence_refs(
    value: Any,
    path: str,
    errors: list[str],
    pending_evidence_refs: list[tuple[str, str]],
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return
    if len(value) != len(set(item for item in value if isinstance(item, str))):
        errors.append(f"{path} must not contain duplicate IDs")
    for index, evidence_id in enumerate(value):
        item_path = f"{path}[{index}]"
        _validate_stable_id(evidence_id, item_path, errors)
        if isinstance(evidence_id, str):
            pending_evidence_refs.append((item_path, evidence_id))


def _validate_constraints(
    value: Any,
    path: str,
    errors: list[str],
    pending_object_refs: list[tuple[str, str]],
) -> None:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return
    required = {"kind", "strength"}
    allowed = required | {
        "subject_ids",
        "related_ids",
        "value",
        "unit",
        "description",
    }
    for index, constraint in enumerate(value):
        item_path = f"{path}[{index}]"
        if not _validate_keys(
            constraint,
            path=item_path,
            required=required,
            allowed=allowed,
            errors=errors,
        ):
            continue
        if constraint.get("kind") not in _CONSTRAINT_KINDS:
            errors.append(f"{item_path}.kind is not supported in IR {IR_VERSION}")
        if constraint.get("strength") not in _CONSTRAINT_STRENGTHS:
            errors.append(f"{item_path}.strength must be required or preferred")
        for key in ("subject_ids", "related_ids"):
            if key not in constraint:
                continue
            refs = constraint[key]
            ref_path = f"{item_path}.{key}"
            if not isinstance(refs, list) or not refs:
                errors.append(f"{ref_path} must be a non-empty array")
                continue
            if len(refs) != len(set(ref for ref in refs if isinstance(ref, str))):
                errors.append(f"{ref_path} must not contain duplicate IDs")
            for ref_index, object_id in enumerate(refs):
                object_path = f"{ref_path}[{ref_index}]"
                _validate_stable_id(object_id, object_path, errors)
                if isinstance(object_id, str):
                    pending_object_refs.append((object_path, object_id))
        if "value" in constraint:
            raw_value = constraint["value"]
            if not isinstance(raw_value, (str, int, float, bool)) or isinstance(
                raw_value, (dict, list)
            ):
                errors.append(f"{item_path}.value must be a JSON scalar")
            elif isinstance(raw_value, float) and not math.isfinite(raw_value):
                errors.append(f"{item_path}.value must be finite")
        if "unit" in constraint and constraint["unit"] not in _CONSTRAINT_UNITS:
            errors.append(f"{item_path}.unit is not supported in IR {IR_VERSION}")
        if "description" in constraint:
            _validate_nonempty_string(
                constraint["description"], f"{item_path}.description", errors
            )


def _validate_content(
    value: Any,
    path: str,
    errors: list[str],
    pending_evidence_refs: list[tuple[str, str]],
) -> None:
    allowed = {
        "text",
        "items",
        "asset_ref",
        "data_ref",
        "table_ref",
        "diagram_ref",
        "alt_text",
    }
    if not _validate_keys(
        value, path=path, required=set(), allowed=allowed, errors=errors
    ):
        return
    if not value:
        errors.append(f"{path} must contain editable content")
        return
    if "text" in value and not isinstance(value["text"], str):
        errors.append(f"{path}.text must be a string")
    for key in ("asset_ref", "data_ref", "table_ref", "diagram_ref", "alt_text"):
        if key in value:
            _validate_nonempty_string(value[key], f"{path}.{key}", errors)
    if "items" not in value:
        return
    items = value["items"]
    if not isinstance(items, list) or not items:
        errors.append(f"{path}.items must be a non-empty array")
        return
    required = {"text", "source_outline_ref"}
    allowed = required | {"label", "level", "evidence_refs"}
    for index, item in enumerate(items):
        item_path = f"{path}.items[{index}]"
        if not _validate_keys(
            item,
            path=item_path,
            required=required,
            allowed=allowed,
            errors=errors,
        ):
            continue
        if not isinstance(item.get("text"), str):
            errors.append(f"{item_path}.text must be a string")
        _validate_source_ref(
            item.get("source_outline_ref"),
            f"{item_path}.source_outline_ref",
            errors,
        )
        if "label" in item:
            _validate_nonempty_string(item["label"], f"{item_path}.label", errors)
        if "level" in item and (
            not isinstance(item["level"], int)
            or isinstance(item["level"], bool)
            or not 0 <= item["level"] <= 8
        ):
            errors.append(f"{item_path}.level must be an integer from 0 to 8")
        if "evidence_refs" in item:
            _validate_evidence_refs(
                item["evidence_refs"],
                f"{item_path}.evidence_refs",
                errors,
                pending_evidence_refs,
            )


def collect_validation_errors(document: Mapping[str, Any]) -> list[str]:
    """Return all structural and cross-reference violations for the current IR."""

    errors: list[str] = []
    root_required = {
        "ir_version",
        "deck_id",
        "title",
        "semantic_role",
        "intent",
        "source_outline",
        "evidence",
        "slides",
        "constraints",
    }
    if not _validate_keys(
        document,
        path="$",
        required=root_required,
        allowed=root_required,
        errors=errors,
    ):
        return errors

    if document.get("ir_version") != IR_VERSION:
        errors.append(
            f"$.ir_version must equal {IR_VERSION}; migrate older documents explicitly"
        )
    deck_id = document.get("deck_id")
    _validate_stable_id(deck_id, "$.deck_id", errors)
    _validate_nonempty_string(document.get("title"), "$.title", errors)
    if document.get("semantic_role") != "deck":
        errors.append("$.semantic_role must equal deck")
    _validate_intent(document.get("intent"), "$.intent", errors)

    source = document.get("source_outline")
    source_required = {"format", "sha256", "root_ref"}
    source_allowed = source_required | {"path"}
    if _validate_keys(
        source,
        path="$.source_outline",
        required=source_required,
        allowed=source_allowed,
        errors=errors,
    ):
        if source.get("format") != "presentation-skill-outline":
            errors.append(
                "$.source_outline.format must equal presentation-skill-outline"
            )
        if not isinstance(source.get("sha256"), str) or _SHA256_RE.fullmatch(
            source.get("sha256", "")
        ) is None:
            errors.append("$.source_outline.sha256 must be a lowercase SHA-256 digest")
        if source.get("root_ref") != "":
            errors.append("$.source_outline.root_ref must equal the root JSON Pointer")
        if "path" in source:
            _validate_nonempty_string(source["path"], "$.source_outline.path", errors)

    all_ids: set[str] = set()
    if isinstance(deck_id, str):
        all_ids.add(deck_id)
    evidence_ids: set[str] = set()
    pending_evidence_refs: list[tuple[str, str]] = []
    pending_object_refs: list[tuple[str, str]] = []

    evidence = document.get("evidence")
    if not isinstance(evidence, list):
        errors.append("$.evidence must be an array")
    else:
        evidence_required = {"id", "kind", "citation", "source_outline_refs"}
        evidence_allowed = evidence_required | {"uri", "locator", "sha256"}
        for index, item in enumerate(evidence):
            path = f"$.evidence[{index}]"
            if not _validate_keys(
                item,
                path=path,
                required=evidence_required,
                allowed=evidence_allowed,
                errors=errors,
            ):
                continue
            item_id = item.get("id")
            _validate_stable_id(item_id, f"{path}.id", errors)
            if isinstance(item_id, str):
                if item_id in all_ids:
                    errors.append(f"{path}.id duplicates another Deck IR ID")
                all_ids.add(item_id)
                evidence_ids.add(item_id)
            if item.get("kind") not in _EVIDENCE_KINDS:
                errors.append(f"{path}.kind is not supported in IR {IR_VERSION}")
            _validate_nonempty_string(item.get("citation"), f"{path}.citation", errors)
            for key in ("uri", "locator"):
                if key in item:
                    _validate_nonempty_string(item[key], f"{path}.{key}", errors)
            if "sha256" in item and (
                not isinstance(item["sha256"], str)
                or _SHA256_RE.fullmatch(item["sha256"]) is None
            ):
                errors.append(f"{path}.sha256 must be a lowercase SHA-256 digest")
            refs = item.get("source_outline_refs")
            if not isinstance(refs, list) or not refs:
                errors.append(f"{path}.source_outline_refs must be a non-empty array")
            else:
                if len(refs) != len(set(ref for ref in refs if isinstance(ref, str))):
                    errors.append(
                        f"{path}.source_outline_refs must not contain duplicates"
                    )
                for ref_index, ref in enumerate(refs):
                    _validate_source_ref(
                        ref, f"{path}.source_outline_refs[{ref_index}]", errors
                    )

    slides = document.get("slides")
    if not isinstance(slides, list):
        errors.append("$.slides must be an array")
    else:
        slide_required = {
            "id",
            "source_outline_ref",
            "semantic_role",
            "intent",
            "elements",
            "evidence_refs",
            "constraints",
        }
        for slide_index, slide in enumerate(slides):
            slide_path = f"$.slides[{slide_index}]"
            if not _validate_keys(
                slide,
                path=slide_path,
                required=slide_required,
                allowed=slide_required,
                errors=errors,
            ):
                continue
            slide_id = slide.get("id")
            _validate_stable_id(slide_id, f"{slide_path}.id", errors)
            if isinstance(slide_id, str):
                if slide_id in all_ids:
                    errors.append(f"{slide_path}.id duplicates another Deck IR ID")
                all_ids.add(slide_id)
            _validate_source_ref(
                slide.get("source_outline_ref"),
                f"{slide_path}.source_outline_ref",
                errors,
            )
            if slide.get("semantic_role") not in _SLIDE_ROLES:
                errors.append(
                    f"{slide_path}.semantic_role is not supported in IR {IR_VERSION}"
                )
            _validate_intent(slide.get("intent"), f"{slide_path}.intent", errors)
            _validate_evidence_refs(
                slide.get("evidence_refs"),
                f"{slide_path}.evidence_refs",
                errors,
                pending_evidence_refs,
            )
            elements = slide.get("elements")
            if not isinstance(elements, list):
                errors.append(f"{slide_path}.elements must be an array")
            else:
                element_required = {
                    "id",
                    "source_outline_ref",
                    "semantic_role",
                    "intent",
                    "editable_object_kind",
                    "content",
                    "evidence_refs",
                    "constraints",
                }
                for element_index, element in enumerate(elements):
                    element_path = f"{slide_path}.elements[{element_index}]"
                    if not _validate_keys(
                        element,
                        path=element_path,
                        required=element_required,
                        allowed=element_required,
                        errors=errors,
                    ):
                        continue
                    element_id = element.get("id")
                    _validate_stable_id(element_id, f"{element_path}.id", errors)
                    if isinstance(element_id, str):
                        if element_id in all_ids:
                            errors.append(
                                f"{element_path}.id duplicates another Deck IR ID"
                            )
                        all_ids.add(element_id)
                    _validate_source_ref(
                        element.get("source_outline_ref"),
                        f"{element_path}.source_outline_ref",
                        errors,
                    )
                    if element.get("semantic_role") not in _ELEMENT_ROLES:
                        errors.append(
                            f"{element_path}.semantic_role is not supported in IR {IR_VERSION}"
                        )
                    _validate_intent(
                        element.get("intent"), f"{element_path}.intent", errors
                    )
                    if element.get("editable_object_kind") not in _EDITABLE_OBJECT_KINDS:
                        errors.append(
                            f"{element_path}.editable_object_kind is not supported "
                            f"in IR {IR_VERSION}"
                        )
                    _validate_content(
                        element.get("content"),
                        f"{element_path}.content",
                        errors,
                        pending_evidence_refs,
                    )
                    _validate_evidence_refs(
                        element.get("evidence_refs"),
                        f"{element_path}.evidence_refs",
                        errors,
                        pending_evidence_refs,
                    )
                    _validate_constraints(
                        element.get("constraints"),
                        f"{element_path}.constraints",
                        errors,
                        pending_object_refs,
                    )
            _validate_constraints(
                slide.get("constraints"),
                f"{slide_path}.constraints",
                errors,
                pending_object_refs,
            )

    _validate_constraints(
        document.get("constraints"),
        "$.constraints",
        errors,
        pending_object_refs,
    )
    for path, evidence_id in pending_evidence_refs:
        if evidence_id not in evidence_ids:
            errors.append(f"{path} references unknown evidence ID {evidence_id}")
    for path, object_id in pending_object_refs:
        if object_id not in all_ids:
            errors.append(f"{path} references unknown Deck IR ID {object_id}")
    return errors


def validate_deck_ir(document: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate a current-version Deck IR document or raise with all failures."""

    errors = collect_validation_errors(document)
    if errors:
        raise DeckIRValidationError(errors)
    return document


def register_migration(
    from_version: str,
    to_version: str,
    migrator: Migration,
    *,
    replace: bool = False,
) -> None:
    """Register one explicit directed migration step."""

    for label, version in (("from_version", from_version), ("to_version", to_version)):
        if not isinstance(version, str) or _SEMVER_RE.fullmatch(version) is None:
            raise DeckIRMigrationError(f"{label} must be an exact semantic version")
    if from_version == to_version:
        raise DeckIRMigrationError("Migration versions must differ")
    if not callable(migrator):
        raise DeckIRMigrationError("migrator must be callable")
    key = (from_version, to_version)
    if key in _MIGRATIONS and not replace:
        raise DeckIRMigrationError(
            f"Migration {from_version} -> {to_version} is already registered"
        )
    _MIGRATIONS[key] = migrator


def unregister_migration(from_version: str, to_version: str) -> None:
    """Remove a registered migration, primarily for isolated plugins and tests."""

    _MIGRATIONS.pop((from_version, to_version), None)


def registered_migrations() -> tuple[tuple[str, str], ...]:
    """Return registered migration edges in deterministic order."""

    return tuple(sorted(_MIGRATIONS))


def _migration_path(
    from_version: str, to_version: str
) -> list[tuple[str, str]] | None:
    queue: deque[tuple[str, list[tuple[str, str]]]] = deque([(from_version, [])])
    visited = {from_version}
    while queue:
        version, path = queue.popleft()
        for edge in sorted(edge for edge in _MIGRATIONS if edge[0] == version):
            next_version = edge[1]
            next_path = path + [edge]
            if next_version == to_version:
                return next_path
            if next_version not in visited:
                visited.add(next_version)
                queue.append((next_version, next_path))
    return None


def migrate_deck_ir(
    document: Mapping[str, Any], *, target_version: str = IR_VERSION
) -> dict[str, Any]:
    """Apply registered migration hooks and validate the current-version result."""

    if target_version != IR_VERSION:
        raise DeckIRMigrationError(
            f"This module can only validate migration target {IR_VERSION}"
        )
    source_version = document.get("ir_version") if isinstance(document, Mapping) else None
    if not isinstance(source_version, str) or _SEMVER_RE.fullmatch(source_version) is None:
        raise DeckIRMigrationError("Source document must declare an exact ir_version")
    if source_version == target_version:
        result = copy.deepcopy(dict(document))
        validate_deck_ir(result)
        return result
    path = _migration_path(source_version, target_version)
    if path is None:
        raise DeckIRMigrationError(
            f"No registered migration path from {source_version} to {target_version}"
        )
    result = copy.deepcopy(dict(document))
    for from_version, to_version in path:
        try:
            migrated = _MIGRATIONS[(from_version, to_version)](copy.deepcopy(result))
        except Exception as exc:  # pragma: no cover - preserves plugin failure context
            raise DeckIRMigrationError(
                f"Migration {from_version} -> {to_version} failed: {exc}"
            ) from exc
        if not isinstance(migrated, dict):
            raise DeckIRMigrationError(
                f"Migration {from_version} -> {to_version} must return an object"
            )
        if migrated.get("ir_version") != to_version:
            raise DeckIRMigrationError(
                f"Migration {from_version} -> {to_version} did not set ir_version"
            )
        result = migrated
    validate_deck_ir(result)
    return result


def _evidence_payload(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        citation = value.strip()
        return {"kind": "source", "citation": citation} if citation else None
    if not isinstance(value, Mapping):
        return None
    kind = _nonempty_text(value.get("kind")).lower()
    if kind not in _EVIDENCE_KINDS:
        kind = "source"
    citation = _first_text(value, ("citation", "text", "title", "label", "url", "uri", "path"))
    uri = _first_text(value, ("uri", "url"))
    if not citation:
        citation = uri
    if not citation:
        return None
    result = {"kind": kind, "citation": citation}
    locator = _first_text(value, ("locator", "page", "section"))
    sha256 = _nonempty_text(value.get("sha256")).lower()
    if uri:
        result["uri"] = uri
    if locator:
        result["locator"] = locator
    if _SHA256_RE.fullmatch(sha256):
        result["sha256"] = sha256
    return result


def _iter_source_entries(
    payload: Mapping[str, Any], base_ref: str
) -> Iterable[tuple[Any, str]]:
    for key in ("sources", "refs", "references"):
        if key not in payload:
            continue
        value = payload[key]
        key_ref = _json_pointer(base_ref, key)
        entries = value if isinstance(value, list) else [value]
        for index, entry in enumerate(entries):
            yield entry, _json_pointer(key_ref, index)


def _register_evidence(
    payload: Mapping[str, Any],
    base_ref: str,
    records: list[dict[str, Any]],
    by_signature: dict[str, dict[str, Any]],
) -> list[str]:
    refs: list[str] = []
    for raw_value, source_ref in _iter_source_entries(payload, base_ref):
        normalized = _evidence_payload(raw_value)
        if normalized is None:
            continue
        signature = _canonical_json(normalized)
        record = by_signature.get(signature)
        if record is None:
            record = {
                "id": stable_id("evidence", normalized["citation"], signature),
                **normalized,
                "source_outline_refs": [source_ref],
            }
            by_signature[signature] = record
            records.append(record)
        elif source_ref not in record["source_outline_refs"]:
            record["source_outline_refs"].append(source_ref)
        if record["id"] not in refs:
            refs.append(record["id"])
    return refs


def _evidence_source_records(
    payload: Mapping[str, Any], base_ref: str
) -> dict[str, tuple[str, str]]:
    records: dict[str, tuple[str, str]] = {}
    for raw_value, source_ref in _iter_source_entries(payload, base_ref):
        normalized = _evidence_payload(raw_value)
        if normalized is None:
            continue
        signature = _canonical_json(normalized)
        evidence_id = stable_id("evidence", normalized["citation"], signature)
        records.setdefault(evidence_id, (source_ref, normalized["citation"]))
    return records


def _content_items(value: Any, field_ref: str) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else [value]
    items: list[dict[str, Any]] = []
    for index, raw_item in enumerate(values):
        item_ref = _json_pointer(field_ref, index)
        if isinstance(raw_item, Mapping):
            text = _first_text(raw_item, ("text", "body", "value", "title", "description"))
            label = _first_text(raw_item, ("label", "title", "name"))
            level = raw_item.get("level")
        else:
            text = _nonempty_text(raw_item)
            label = ""
            level = None
        if not text:
            continue
        item: dict[str, Any] = {"text": text, "source_outline_ref": item_ref}
        if label and label != text:
            item["label"] = label
        if isinstance(level, int) and not isinstance(level, bool) and 0 <= level <= 8:
            item["level"] = level
        items.append(item)
    return items


def _ref_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_text(value, ("ref", "path", "data_ref", "asset_ref", "source"))
    return ""


def _slide_semantics(slide: Mapping[str, Any]) -> tuple[str, str, str | None]:
    slide_type = _nonempty_text(slide.get("type")).lower()
    declared_intent = _nonempty_text(slide.get("slide_intent")).lower()
    visual_intent = _nonempty_text(slide.get("visual_intent")).lower()
    variant = _nonempty_text(slide.get("variant")).lower()
    if visual_intent not in _VISUAL_INTENTS:
        if "timeline" in variant:
            visual_intent = "timeline"
        elif "comparison" in variant or "2col" in variant:
            visual_intent = "comparison"
        elif "chart" in variant or "data" in variant:
            visual_intent = "data"
        elif "table" in variant:
            visual_intent = "table"
        else:
            visual_intent = ""

    if slide_type in {"title", "cover"}:
        role, purpose = "title", "introduce"
    elif slide_type == "section" or declared_intent == "section":
        role, purpose = "section", "navigate"
    elif slide_type in {"references", "sources"}:
        role, purpose = "references", "evidence"
    elif slide_type in {"closing", "end"}:
        role, purpose = "closing", "summarize"
    elif declared_intent == "decision":
        role, purpose = "decision", "decide"
    elif declared_intent == "evidence":
        role, purpose = "evidence", "evidence"
    elif declared_intent == "process" or visual_intent in {"timeline", "flow"}:
        role, purpose = "process", "process"
    elif visual_intent == "comparison":
        role, purpose = "comparison", "compare"
    elif visual_intent in {"data", "table"}:
        role, purpose = "data", "evidence"
    else:
        role, purpose = "content", "inform"
    return role, purpose, visual_intent or None


def _append_element(
    elements: list[dict[str, Any]],
    *,
    slide_id: str,
    source_ref: str,
    semantic_role: str,
    purpose: str,
    editable_object_kind: str,
    content: dict[str, Any],
    message: str = "",
    evidence_refs: Sequence[str] = (),
) -> None:
    intent: dict[str, str] = {"purpose": purpose}
    if message:
        intent["message"] = message
    source_match = _SLIDE_SOURCE_REF_RE.fullmatch(source_ref)
    identity_ref = source_match.group("local") if source_match else source_ref
    identity_ref = identity_ref or "/"
    elements.append(
        {
            "id": stable_id("element", slide_id, identity_ref),
            "source_outline_ref": source_ref,
            "semantic_role": semantic_role,
            "intent": intent,
            "editable_object_kind": editable_object_kind,
            "content": content,
            "evidence_refs": list(evidence_refs),
            "constraints": [],
        }
    )


def _elements_from_outline_slide(
    slide: Mapping[str, Any],
    *,
    slide_id: str,
    slide_ref: str,
    slide_purpose: str,
    evidence_refs: Sequence[str],
) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for field, role, purpose in (
        ("title", "title", "introduce"),
        ("subtitle", "subtitle", "explain"),
        ("caption", "body", slide_purpose),
        ("footer", "body", "summarize"),
        ("verdict", "decision", "decide"),
    ):
        text = _nonempty_text(slide.get(field))
        if text:
            _append_element(
                elements,
                slide_id=slide_id,
                source_ref=_json_pointer(slide_ref, field),
                semantic_role=role,
                purpose=purpose,
                editable_object_kind="text",
                content={"text": text},
                message=text,
                evidence_refs=evidence_refs if role not in {"title", "subtitle"} else (),
            )

    for field, role, kind, purpose in (
        ("bullets", "list", "text", slide_purpose),
        ("highlights", "callout", "group", "summarize"),
        ("cards", "body", "group", slide_purpose),
        ("stats", "metric", "group", "evidence"),
        ("milestones", "diagram", "diagram", "process"),
    ):
        if field not in slide:
            continue
        field_ref = _json_pointer(slide_ref, field)
        items = _content_items(slide[field], field_ref)
        if items:
            _append_element(
                elements,
                slide_id=slide_id,
                source_ref=field_ref,
                semantic_role=role,
                purpose=purpose,
                editable_object_kind=kind,
                content={"items": items},
                evidence_refs=evidence_refs,
            )

    if isinstance(slide.get("flow_steps"), list):
        items = []
        for index, step in enumerate(slide["flow_steps"]):
            if not isinstance(step, Mapping):
                continue
            for field in ("title", "detail"):
                value = _nonempty_text(step.get(field))
                if value:
                    items.append({"text": value, "source_outline_ref": f"{slide_ref}/flow_steps/{index}/{field}"})
        if items:
            _append_element(
                elements, slide_id=slide_id, source_ref=_json_pointer(slide_ref, "flow_steps"),
                semantic_role="diagram", purpose="process", editable_object_kind="diagram",
                content={"items": items}, evidence_refs=evidence_refs,
            )

    for field in ("left", "right"):
        value = slide.get(field)
        if not isinstance(value, Mapping):
            continue
        field_ref = _json_pointer(slide_ref, field)
        if "body" in value:
            items = _content_items(
                value["body"], _json_pointer(field_ref, "body")
            )
        else:
            items = _content_items(value, field_ref)
        heading_key = "title" if _nonempty_text(value.get("title")) else "label"
        heading = _nonempty_text(value.get(heading_key))
        if heading:
            items.insert(
                0,
                {
                    "text": heading,
                    "source_outline_ref": _json_pointer(field_ref, heading_key),
                },
            )
        if items:
            _append_element(
                elements,
                slide_id=slide_id,
                source_ref=field_ref,
                semantic_role="body",
                purpose="compare",
                editable_object_kind="group",
                content={"items": items},
                evidence_refs=evidence_refs,
            )

    assets = slide.get("assets")
    asset_entries: list[tuple[str, Any, str, str, str]] = []
    if isinstance(assets, Mapping):
        asset_entries.extend(
            (
                ("hero_image", assets.get("hero_image"), "image", "image", "asset_ref"),
                ("logo", assets.get("logo"), "image", "image", "asset_ref"),
                ("diagram", assets.get("diagram"), "diagram", "diagram", "diagram_ref"),
                (
                    "mermaid_source",
                    assets.get("mermaid_source"),
                    "diagram",
                    "diagram",
                    "diagram_ref",
                ),
                ("chart_data", assets.get("chart_data"), "chart", "chart", "data_ref"),
            )
        )
    for field, value, role, kind, content_key in asset_entries:
        ref = _ref_value(value)
        if not ref:
            continue
        source_ref = _json_pointer(_json_pointer(slide_ref, "assets"), field)
        _append_element(
            elements,
            slide_id=slide_id,
            source_ref=source_ref,
            semantic_role=role,
            purpose="evidence" if role in {"chart", "diagram"} else "inform",
            editable_object_kind=kind,
            content={content_key: ref},
            evidence_refs=evidence_refs,
        )

    for field, role, kind, content_key in (
        ("image", "image", "image", "asset_ref"),
        ("chart", "chart", "chart", "data_ref"),
        ("table", "table", "table", "table_ref"),
        ("diagram", "diagram", "diagram", "diagram_ref"),
    ):
        ref = _ref_value(slide.get(field))
        if ref:
            _append_element(
                elements,
                slide_id=slide_id,
                source_ref=_json_pointer(slide_ref, field),
                semantic_role=role,
                purpose="evidence",
                editable_object_kind=kind,
                content={content_key: ref},
                evidence_refs=evidence_refs,
            )

    if evidence_refs:
        source_records = _evidence_source_records(slide, slide_ref)
        citation_items = [
            {
                "text": source_records[evidence_id][1],
                "source_outline_ref": source_records[evidence_id][0],
                "evidence_refs": [evidence_id],
            }
            for evidence_id in evidence_refs
        ]
        _append_element(
            elements,
            slide_id=slide_id,
            source_ref=source_records[evidence_refs[0]][0],
            semantic_role="citation",
            purpose="evidence",
            editable_object_kind="text",
            content={"items": citation_items},
            evidence_refs=evidence_refs,
        )
    return elements


def deck_ir_from_outline(
    outline: Mapping[str, Any], *, source_path: str | Path | None = None
) -> dict[str, Any]:
    """Convert a presentation-skill outline to the current semantic Deck IR."""

    if not isinstance(outline, Mapping):
        raise DeckIRError("Outline must be a JSON object")
    raw_slides = outline.get("slides", [])
    if not isinstance(raw_slides, list):
        raise DeckIRError("Outline slides must be an array")
    slides_payload = [slide for slide in raw_slides if isinstance(slide, Mapping)]
    first_slide_title = (
        _nonempty_text(slides_payload[0].get("title")) if slides_payload else ""
    )
    title = _first_text(outline, ("title", "name")) or first_slide_title or "Untitled deck"
    source_sha256 = hashlib.sha256(canonical_json_bytes(outline)).hexdigest()
    explicit_identity = _first_text(outline, ("deck_id", "id"))
    deck_identity = explicit_identity or title or source_sha256
    deck_id = stable_id("deck", deck_identity)

    source_outline: dict[str, str] = {
        "format": "presentation-skill-outline",
        "sha256": source_sha256,
        "root_ref": "",
    }
    if source_path is not None:
        source_text = str(source_path).strip()
        if source_text:
            source_outline["path"] = Path(source_text).as_posix()

    deck_intent: dict[str, str] = {"purpose": "inform", "message": title}
    audience = _nonempty_text(outline.get("audience"))
    outcome = _first_text(outline, ("outcome", "objective"))
    if audience:
        deck_intent["audience"] = audience
    if outcome:
        deck_intent["outcome"] = outcome

    evidence: list[dict[str, Any]] = []
    evidence_by_signature: dict[str, dict[str, Any]] = {}
    _register_evidence(outline, "", evidence, evidence_by_signature)
    slides: list[dict[str, Any]] = []
    fallback_slide_occurrences: dict[str, int] = {}
    for source_index, raw_slide in enumerate(raw_slides):
        if not isinstance(raw_slide, Mapping):
            continue
        slide_ref = _json_pointer("", "slides")
        slide_ref = _json_pointer(slide_ref, source_index)
        explicit_slide_id = _first_text(raw_slide, ("slide_id", "id"))
        slide_title = _nonempty_text(raw_slide.get("title"))
        slide_type = _nonempty_text(raw_slide.get("type")) or "content"
        fallback_identity = f"{slide_type}:{slide_title}" if slide_title else str(source_index)
        if explicit_slide_id:
            slide_identity = explicit_slide_id
        else:
            occurrence = fallback_slide_occurrences.get(fallback_identity, 0)
            fallback_slide_occurrences[fallback_identity] = occurrence + 1
            slide_identity = (
                fallback_identity
                if occurrence == 0
                else f"{fallback_identity}#{occurrence + 1}"
            )
        slide_id = stable_id("slide", deck_id, slide_identity)
        role, purpose, visual_intent = _slide_semantics(raw_slide)
        intent: dict[str, str] = {"purpose": purpose}
        if slide_title:
            intent["message"] = slide_title
        if visual_intent:
            intent["visual_intent"] = visual_intent
        evidence_refs = _register_evidence(
            raw_slide, slide_ref, evidence, evidence_by_signature
        )
        elements = _elements_from_outline_slide(
            raw_slide,
            slide_id=slide_id,
            slide_ref=slide_ref,
            slide_purpose=purpose,
            evidence_refs=evidence_refs,
        )
        constraints: list[dict[str, Any]] = []
        if elements:
            constraints.append(
                {
                    "kind": "reading_order",
                    "strength": "required",
                    "subject_ids": [element["id"] for element in elements],
                }
            )
        if evidence_refs:
            constraints.append(
                {
                    "kind": "evidence_required",
                    "strength": "required",
                    "subject_ids": [slide_id],
                    "description": "Preserve the slide's evidence linkage.",
                }
            )
        slides.append(
            {
                "id": slide_id,
                "source_outline_ref": slide_ref,
                "semantic_role": role,
                "intent": intent,
                "elements": elements,
                "evidence_refs": evidence_refs,
                "constraints": constraints,
            }
        )

    deck_constraints: list[dict[str, Any]] = []
    if slides:
        deck_constraints.append(
            {
                "kind": "reading_order",
                "strength": "required",
                "subject_ids": [slide["id"] for slide in slides],
            }
        )
    result: dict[str, Any] = {
        "ir_version": IR_VERSION,
        "deck_id": deck_id,
        "title": title,
        "semantic_role": "deck",
        "intent": deck_intent,
        "source_outline": source_outline,
        "evidence": evidence,
        "slides": slides,
        "constraints": deck_constraints,
    }
    validate_deck_ir(result)
    return result


def load_deck_ir(path: str | Path) -> dict[str, Any]:
    """Load and validate one Deck IR JSON file."""

    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeckIRError(f"Could not read {input_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DeckIRError(f"{input_path} must contain a JSON object")
    validate_deck_ir(payload)
    return payload


def _write_output(text: str, output: str | None) -> None:
    rendered = text + ("" if text.endswith("\n") else "\n")
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate Deck IR")
    validate_parser.add_argument("input")
    validate_parser.add_argument(
        "--hash", action="store_true", help="also print the canonical SHA-256"
    )

    from_outline_parser = subparsers.add_parser(
        "from-outline", help="convert outline.json to semantic Deck IR"
    )
    from_outline_parser.add_argument("input")
    from_outline_parser.add_argument("--output", "-o")
    from_outline_parser.add_argument(
        "--pretty", action="store_true", help="emit indented JSON instead of canonical JSON"
    )

    canonical_parser = subparsers.add_parser(
        "canonicalize", help="validate and emit canonical Deck IR JSON"
    )
    canonical_parser.add_argument("input")
    canonical_parser.add_argument("--output", "-o")

    hash_parser = subparsers.add_parser("hash", help="print canonical Deck IR SHA-256")
    hash_parser.add_argument("input")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            document = load_deck_ir(args.input)
            if args.hash:
                print(f"valid {deck_ir_sha256(document)}")
            else:
                print("valid")
            return 0
        if args.command == "from-outline":
            input_path = Path(args.input)
            outline = json.loads(input_path.read_text(encoding="utf-8"))
            document = deck_ir_from_outline(outline, source_path=input_path)
            if args.pretty:
                rendered = json.dumps(
                    document, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
                )
            else:
                rendered = canonicalize_deck_ir(document)
            _write_output(rendered, args.output)
            return 0
        if args.command == "canonicalize":
            _write_output(canonicalize_deck_ir(load_deck_ir(args.input)), args.output)
            return 0
        if args.command == "hash":
            print(deck_ir_sha256(load_deck_ir(args.input)))
            return 0
    except (DeckIRError, OSError, json.JSONDecodeError) as exc:
        print(f"deck_ir: {exc}", file=sys.stderr)
        return 2
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
