#!/usr/bin/env python3
"""Apply a PPTX style extraction fragment to a deck workspace.

`extract_pptx_style.py` is read-only. This helper is the explicit source edit:
it merges the reusable fragment into `design_brief.json`, maps renderer-visible
treatments into `renderer_treatments`, records style observations, and writes an
idempotent notes section.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


NOTE_START = "<!-- pptx-style-fragment:start -->"
NOTE_END = "<!-- pptx-style-fragment:end -->"

RENDERER_TREATMENT_KEYS = {
    "style_seed",
    "visual_density",
    "header_mode",
    "header_variant",
    "header_variants",
    "title_layout",
    "section_motif",
    "timeline_mode",
    "matrix_mode",
    "stats_mode",
    "cards_mode",
    "chart_treatment",
    "footer_mode",
    "footer_page_numbers",
    "footer_source_label",
    "footer_refs_label",
    "summary_callout_mode",
    "figure_table_treatment",
}

READABILITY_ALIASES = {
    "title_min_pt": "min_title_pt",
    "body_min_pt": "min_body_pt",
    "caption_min_pt": "min_caption_pt",
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def _write_json_if_changed(path: Path, payload: Any, *, dry_run: bool) -> bool:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _write_text_if_changed(path: Path, text: str, *, dry_run: bool) -> bool:
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    if dry_run:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _file_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    snapshot: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
    }
    if path.exists() and path.is_file():
        payload = path.read_bytes()
        snapshot["sha256"] = hashlib.sha256(payload).hexdigest()
        snapshot["size_bytes"] = len(payload)
    return snapshot


def _display_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace.resolve()))
    except ValueError:
        return str(path.resolve())


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _clean_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _clean_value(item)
            for key, item in value.items()
            if not _is_empty(item)
        }
    if isinstance(value, list):
        cleaned = [_clean_value(item) for item in value if not _is_empty(item)]
        return cleaned
    return value


def _merge_unique(existing: list[Any], incoming: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for item in [*existing, *incoming]:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_value(
    target: dict[str, Any],
    key: str,
    value: Any,
    *,
    base_path: str,
    replace: bool,
    touched: list[str],
    skipped: list[str],
) -> None:
    clean = _clean_value(value)
    if _is_empty(clean):
        return
    path = f"{base_path}.{key}" if base_path else key
    existing = target.get(key)
    if isinstance(existing, dict) and isinstance(clean, dict):
        _merge_dict(
            existing,
            clean,
            base_path=path,
            replace=replace,
            touched=touched,
            skipped=skipped,
        )
        return
    if isinstance(existing, list) and isinstance(clean, list) and not replace:
        merged = _merge_unique(existing, clean)
        if merged != existing:
            target[key] = merged
            touched.append(path)
        elif clean and existing != clean:
            skipped.append(path)
        return
    if replace or _is_empty(existing):
        if existing != clean:
            target[key] = clean
            touched.append(path)
        return
    if existing != clean:
        skipped.append(path)


def _merge_dict(
    target: dict[str, Any],
    updates: dict[str, Any],
    *,
    base_path: str,
    replace: bool,
    touched: list[str],
    skipped: list[str],
) -> None:
    for key, value in updates.items():
        _merge_value(
            target,
            str(key),
            value,
            base_path=base_path,
            replace=replace,
            touched=touched,
            skipped=skipped,
        )


def _normalize_readability(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in contract.items():
        normalized[READABILITY_ALIASES.get(str(key), str(key))] = value
    return normalized


def _fragment_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SystemExit("Style fragment/report must contain a JSON object.")
    fragment = payload.get("design_brief_fragment")
    if isinstance(fragment, dict):
        return fragment
    return payload


def _replace_notes_section(existing: str, section: str) -> str:
    if NOTE_START in existing and NOTE_END in existing:
        before = existing.split(NOTE_START, 1)[0].rstrip()
        after = existing.split(NOTE_END, 1)[1].lstrip()
        parts = [part for part in (before, section.rstrip(), after.rstrip()) if part]
        return "\n\n".join(parts) + "\n"
    prefix = existing.rstrip()
    return (prefix + "\n\n" if prefix else "") + section.rstrip() + "\n"


def _format_list(value: Any, *, limit: int = 8) -> str:
    if not isinstance(value, list):
        return "none"
    parts = [str(item).strip() for item in value if str(item).strip()]
    if len(parts) > limit:
        return ", ".join(parts[:limit]) + f", +{len(parts) - limit} more"
    return ", ".join(parts) if parts else "none"


def _format_command(command: Any) -> str:
    if not isinstance(command, list):
        return ""
    return " ".join(str(part) for part in command if str(part).strip())


def _safe_slug(value: Any, default: str = "style-import") -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = default
    chars = [
        char.lower() if char.isalnum() else "-"
        for char in raw
    ]
    slug = "-".join(part for part in "".join(chars).split("-") if part)
    return slug or default


def _style_preview_commands(workspace: Path, fragment: dict[str, Any]) -> dict[str, list[str]]:
    observation = fragment.get("style_observation") if isinstance(fragment.get("style_observation"), dict) else {}
    preview = observation.get("preview") if isinstance(observation.get("preview"), dict) else {}
    style_system = fragment.get("style_system") if isinstance(fragment.get("style_system"), dict) else {}
    deck_style = fragment.get("deck_style") if isinstance(fragment.get("deck_style"), dict) else {}
    presets = preview.get("presets") if isinstance(preview.get("presets"), list) else []
    style_preset = str((presets[0] if presets else style_system.get("style_preset")) or "").strip()
    variants = preview.get("variants") if isinstance(preview.get("variants"), list) else deck_style.get("header_variants")
    header_variants = [
        str(item).strip()
        for item in (variants if isinstance(variants, list) else [])
        if str(item).strip()
    ]
    if not style_preset or not header_variants:
        return {}
    style_seed = style_system.get("style_seed") or deck_style.get("style_seed") or style_preset
    outdir = workspace / "build" / f"pptx_style_preview_{_safe_slug(style_seed)}"
    base_command = [
        "python3",
        "scripts/build_header_variant_gallery.py",
        "--outdir",
        str(outdir),
        "--presets",
        style_preset,
        "--variants",
        *header_variants,
    ]
    return {
        "fast": [*base_command, "--build", "--qa"],
        "rendered": [*base_command, "--build", "--qa", "--render"],
    }


def _observation_summary(fragment: dict[str, Any]) -> dict[str, Any]:
    observation = fragment.get("style_observation")
    if not isinstance(observation, dict):
        return {}
    palette = observation.get("palette") if isinstance(observation.get("palette"), dict) else {}
    counts = observation.get("counts") if isinstance(observation.get("counts"), dict) else {}
    deck_style = fragment.get("deck_style") if isinstance(fragment.get("deck_style"), dict) else {}
    style_system = fragment.get("style_system") if isinstance(fragment.get("style_system"), dict) else {}
    return {
        "source_decks": observation.get("source_decks") if isinstance(observation.get("source_decks"), list) else [],
        "style_seed": style_system.get("style_seed"),
        "style_preset": style_system.get("style_preset"),
        "header_variants": deck_style.get("header_variants"),
        "footer_mode": deck_style.get("footer_mode"),
        "footer_page_numbers": deck_style.get("footer_page_numbers"),
        "accent_candidates": palette.get("accent_candidates") if isinstance(palette, dict) else [],
        "counts": counts,
    }


def _notes_section(
    summary: dict[str, Any],
    *,
    source_label: str,
    mode: str,
    preview_commands: dict[str, list[str]],
) -> str:
    counts = summary.get("counts") if isinstance(summary.get("counts"), dict) else {}
    lines = [
        NOTE_START,
        "## PPTX Style Fragment",
        "",
        f"- Source: `{source_label}`",
        f"- Apply mode: `{mode}`",
    ]
    if summary.get("style_seed"):
        lines.append(f"- Style seed: `{summary['style_seed']}`")
    if summary.get("style_preset"):
        lines.append(f"- Recommended preset: `{summary['style_preset']}`")
    lines.extend(
        [
            f"- Header variants: {_format_list(summary.get('header_variants'))}",
            f"- Footer mode: `{summary.get('footer_mode') or 'none'}`",
            f"- Footer page numbers: `{bool(summary.get('footer_page_numbers'))}`",
            f"- Accent candidates: {_format_list(summary.get('accent_candidates'))}",
            f"- Observed objects: slides={counts.get('slides', 0)}, pictures={counts.get('pictures', 0)}, tables={counts.get('tables', 0)}, charts={counts.get('charts', 0)}",
        ]
    )
    source_decks = summary.get("source_decks")
    if isinstance(source_decks, list) and source_decks:
        lines.extend(["", "### Source Decks"])
        for item in source_decks[:10]:
            lines.append(f"- {item}")
    if preview_commands:
        lines.extend(
            [
                "",
                "### Style Preview",
                f"- Fast gallery: `{_format_command(preview_commands.get('fast'))}`",
                f"- Rendered gallery: `{_format_command(preview_commands.get('rendered'))}`",
            ]
        )
    lines.append(NOTE_END)
    return "\n".join(lines) + "\n"


def _style_import_record(
    *,
    workspace: Path,
    report_path: Path | None,
    fragment_path: Path | None,
    fragment: dict[str, Any],
    source_payload: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    record = {
        "applied_by": "scripts/apply_pptx_style_fragment.py",
        "mode": mode,
        "report": _file_snapshot(report_path),
        "fragment": _file_snapshot(fragment_path),
        "source_decks": [],
        "style_seed": "",
        "style_preset": "",
        "preview_commands": _style_preview_commands(workspace, fragment),
    }
    inputs = source_payload.get("inputs") if isinstance(source_payload, dict) else None
    if isinstance(inputs, list):
        record["source_decks"] = inputs
    observation = _observation_summary(fragment)
    if observation.get("style_seed"):
        record["style_seed"] = observation["style_seed"]
    if observation.get("style_preset"):
        record["style_preset"] = observation["style_preset"]
    return record


def apply_fragment(
    *,
    workspace: Path,
    style_report_path: Path | None,
    fragment_path: Path | None,
    preserve_existing: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if style_report_path is None and fragment_path is None:
        default_fragment = workspace / "style_extract_design_brief.json"
        default_report = workspace / "style_extract_report.json"
        if default_fragment.exists():
            fragment_path = default_fragment
        elif default_report.exists():
            style_report_path = default_report
        else:
            raise SystemExit(
                "Provide --fragment or --style-report, or place style_extract_design_brief.json/style_extract_report.json in the workspace."
            )

    source_path = fragment_path or style_report_path
    assert source_path is not None
    source_payload = _load_json(source_path, {})
    fragment = _fragment_from_payload(source_payload)
    if not fragment:
        raise SystemExit(f"No design brief fragment found in {source_path}.")

    replace = not preserve_existing
    changed_files: list[str] = []
    touched_fields: list[str] = []
    skipped_fields: list[str] = []

    design_path = workspace / "design_brief.json"
    design = _load_json(design_path, {})
    if not isinstance(design, dict):
        raise SystemExit(f"{design_path} must contain a JSON object.")

    style_system = design.get("style_system")
    if not isinstance(style_system, dict):
        style_system = {}
        design["style_system"] = style_system
    _merge_dict(
        style_system,
        fragment.get("style_system") if isinstance(fragment.get("style_system"), dict) else {},
        base_path="design_brief.style_system",
        replace=replace,
        touched=touched_fields,
        skipped=skipped_fields,
    )

    deck_style = fragment.get("deck_style") if isinstance(fragment.get("deck_style"), dict) else {}
    renderer_updates = {
        key: value
        for key, value in deck_style.items()
        if key in RENDERER_TREATMENT_KEYS
    }
    renderer_treatments = design.get("renderer_treatments")
    if not isinstance(renderer_treatments, dict):
        renderer_treatments = {}
        design["renderer_treatments"] = renderer_treatments
    _merge_dict(
        renderer_treatments,
        renderer_updates,
        base_path="design_brief.renderer_treatments",
        replace=replace,
        touched=touched_fields,
        skipped=skipped_fields,
    )

    for key in ("design_modulation", "speed_contract"):
        value = fragment.get(key)
        if not isinstance(value, dict):
            continue
        target = design.get(key)
        if not isinstance(target, dict):
            target = {}
            design[key] = target
        _merge_dict(
            target,
            value,
            base_path=f"design_brief.{key}",
            replace=replace,
            touched=touched_fields,
            skipped=skipped_fields,
        )

    readability = _normalize_readability(fragment.get("readability_contract"))
    if readability:
        target = design.get("readability_contract")
        if not isinstance(target, dict):
            target = {}
            design["readability_contract"] = target
        _merge_dict(
            target,
            readability,
            base_path="design_brief.readability_contract",
            replace=replace,
            touched=touched_fields,
            skipped=skipped_fields,
        )

    observation = fragment.get("style_observation")
    if isinstance(observation, dict):
        if design.get("style_observation") != observation:
            design["style_observation"] = observation
            touched_fields.append("design_brief.style_observation")

    import_record = _style_import_record(
        workspace=workspace,
        report_path=style_report_path,
        fragment_path=fragment_path,
        fragment=fragment,
        source_payload=source_payload if isinstance(source_payload, dict) else {},
        mode="preserve-existing" if preserve_existing else "apply-style",
    )
    if design.get("style_import") != import_record:
        design["style_import"] = import_record
        touched_fields.append("design_brief.style_import")

    if _write_json_if_changed(design_path, design, dry_run=dry_run):
        changed_files.append(_display_path(workspace, design_path))

    notes_path = workspace / "notes.md"
    existing_notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    source_label = _display_path(workspace, source_path)
    summary = _observation_summary(fragment)
    preview_commands = _style_preview_commands(workspace, fragment)
    new_notes = _replace_notes_section(
        existing_notes,
        _notes_section(
            summary,
            source_label=source_label,
            mode="preserve-existing" if preserve_existing else "apply-style",
            preview_commands=preview_commands,
        ),
    )
    if _write_text_if_changed(notes_path, new_notes, dry_run=dry_run):
        changed_files.append(_display_path(workspace, notes_path))

    return {
        "workflow": "pptx_style_fragment_apply_v1",
        "workspace": str(workspace),
        "style_report": str(style_report_path) if style_report_path is not None else None,
        "fragment": str(fragment_path) if fragment_path is not None else None,
        "mode": "preserve-existing" if preserve_existing else "apply-style",
        "changed_files": changed_files,
        "touched_fields": sorted(set(touched_fields)),
        "skipped_fields": sorted(set(skipped_fields)),
        "style_seed": _observation_summary(fragment).get("style_seed") or "",
        "style_preset": _observation_summary(fragment).get("style_preset") or "",
        "preview_commands": preview_commands,
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply extracted PPTX style signals to a deck workspace.")
    parser.add_argument("--workspace", required=True, help="Deck workspace directory")
    parser.add_argument("--style-report", help="Full JSON report from extract_pptx_style.py")
    parser.add_argument("--fragment", help="design_brief fragment JSON from extract_pptx_style.py")
    parser.add_argument(
        "--preserve-existing",
        action="store_true",
        help="Only fill missing fields instead of replacing style-import owned fields.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Emit report without writing files")
    parser.add_argument("--report", help="Optional JSON apply report path")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    style_report_path = Path(args.style_report).expanduser().resolve() if args.style_report else None
    fragment_path = Path(args.fragment).expanduser().resolve() if args.fragment else None

    report = apply_fragment(
        workspace=workspace,
        style_report_path=style_report_path,
        fragment_path=fragment_path,
        preserve_existing=bool(args.preserve_existing),
        dry_run=bool(args.dry_run),
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
