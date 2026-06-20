#!/usr/bin/env python3
"""Verify that assets Codex claims to have staged actually exist.

Codex narrates in confident first-person present tense ("adding a small
icon set"). The narration sometimes diverges from actual filesystem
state. This script cross-checks: (a) every outline.slides[].assets.*
path resolves to a real file on disk; (b) every asset_plan.json entry
claiming to be staged has a matching file in assets/staged/.

Runs at the end of build_workspace.py --qa. Fails loudly if any
referenced asset is missing so the agent can't silently declare done
on a deck that's text-only despite its outline claiming otherwise.

Usage:
    python3 verify_narration.py --workspace decks/my-deck
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ALIAS_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("images", ("asset", "image")),
    ("backgrounds", ("asset", "background")),
    ("charts", ("asset", "chart")),
    ("tables", ("asset", "table")),
    ("generated_images", ("asset", "image", "generated")),
)


def _staged_aliases(workspace: Path) -> set[str]:
    manifest_path = workspace / "assets" / "staged" / "staged_manifest.json"
    if not manifest_path.exists():
        return set()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    aliases: set[str] = set()
    if not isinstance(payload, dict):
        return aliases
    for section, prefixes in _ALIAS_SECTIONS:
        entries = payload.get(section)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip().lower()
            if not name:
                continue
            aliases.update(f"{prefix}:{name}" for prefix in prefixes)
    return aliases


def _resolve(workspace: Path, value: str) -> Path | None:
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    # Alias prefixes are always OK (resolved via staged_manifest elsewhere).
    if raw.startswith(("asset:", "image:", "background:", "chart:", "table:", "generated:")):
        return None
    if raw.startswith(("fa6:", "fa:", "bi:", "bs:", "md:", "lu:")):
        return None
    p = Path(raw)
    if p.is_absolute():
        return p if p.exists() else None
    candidates = [
        workspace / p,
        workspace / "assets" / p,
        workspace / "assets" / "staged" / p,
        workspace / "assets" / "icons" / p,
    ]
    # Bare name without extension — probe common icon extensions.
    if not p.suffix:
        for ext in (".png", ".svg", ".jpg", ".jpeg"):
            candidates.append(workspace / "assets" / "icons" / f"{p.name}{ext}")
    for c in candidates:
        if c.exists():
            return c
    return None


def _is_staged_alias(value: str) -> bool:
    raw = value.strip().lower()
    return raw.startswith(("asset:", "image:", "background:", "chart:", "table:", "generated:"))


def _is_runtime_resolved(value: str, workspace: Path) -> bool:
    """Return True for aliases resolved outside this filesystem probe.

    Staged asset aliases and react-icons slugs are valid references even
    though they do not correspond to an immediate local path here. The
    renderer resolves them later from staged_manifest or rasterizes icons
    into a cache.
    """
    raw = value.strip().lower()
    if raw.startswith(("fa6:", "fa:", "bi:", "bs:", "md:", "lu:")):
        return True
    if _is_staged_alias(raw):
        return raw in _staged_aliases(workspace)
    return False


def _alias_issue_if_missing(
    workspace: Path,
    value: str,
    *,
    idx: int | None,
    field: str,
) -> dict[str, Any] | None:
    if not _is_staged_alias(value):
        return None
    if _is_runtime_resolved(value, workspace):
        return None
    return {
        "slide_index": idx,
        "rule": "staged_alias_missing",
        "field": field,
        "value": value,
    }


def _check_slide_assets(
    workspace: Path, slide: dict[str, Any], idx: int
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in ("chart", "table", "table_data"):
        v = slide.get(field)
        if isinstance(v, str) and v.strip():
            alias_issue = _alias_issue_if_missing(workspace, v, idx=idx, field=field)
            if alias_issue:
                issues.append(alias_issue)
    direct_tables = slide.get("tables") or slide.get("table_groups")
    if isinstance(direct_tables, list):
        for i, table in enumerate(direct_tables):
            if isinstance(table, str) and table.strip():
                alias_issue = _alias_issue_if_missing(workspace, table, idx=idx, field=f"tables[{i}]")
                if alias_issue:
                    issues.append(alias_issue)
    assets = slide.get("assets")
    if not isinstance(assets, dict):
        return issues
    scalar_fields = (
        "hero_image",
        "image",
        "generated_image",
        "diagram",
        "mermaid_source",
        "logo",
        "chart_data",
        "table_data",
        "table",
    )
    for field in scalar_fields:
        v = assets.get(field)
        if isinstance(v, str) and v.strip():
            alias_issue = _alias_issue_if_missing(workspace, v, idx=idx, field=f"assets.{field}")
            if alias_issue:
                issues.append(alias_issue)
                continue
            if _is_runtime_resolved(v, workspace):
                continue
            if _resolve(workspace, v) is None:
                issues.append(
                    {
                        "slide_index": idx,
                        "rule": "asset_missing",
                        "field": f"assets.{field}",
                        "value": v,
                    }
                )
    icons = assets.get("icons")
    if isinstance(icons, list):
        for i, icon in enumerate(icons):
            if isinstance(icon, str) and icon.strip():
                alias_issue = _alias_issue_if_missing(workspace, icon, idx=idx, field=f"assets.icons[{i}]")
                if alias_issue:
                    issues.append(alias_issue)
                    continue
                if _is_runtime_resolved(icon, workspace):
                    continue
                if _resolve(workspace, icon) is None:
                    issues.append(
                        {
                            "slide_index": idx,
                            "rule": "asset_missing",
                            "field": f"assets.icons[{i}]",
                            "value": icon,
                        }
                    )
    tables = assets.get("tables")
    if isinstance(tables, list):
        for i, table in enumerate(tables):
            if isinstance(table, str) and table.strip():
                alias_issue = _alias_issue_if_missing(workspace, table, idx=idx, field=f"assets.tables[{i}]")
                if alias_issue:
                    issues.append(alias_issue)
                    continue
                if _is_runtime_resolved(table, workspace):
                    continue
                if _resolve(workspace, table) is None:
                    issues.append(
                        {
                            "slide_index": idx,
                            "rule": "asset_missing",
                            "field": f"assets.tables[{i}]",
                            "value": table,
                        }
                    )
    return issues


def _check_asset_plan(
    workspace: Path, plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Plan entries that reference a `path` should resolve; entries that
    only carry a `wikimedia_query` are intent, not claims of existence.
    """
    issues: list[dict[str, Any]] = []
    for section in ("images", "backgrounds", "icons", "charts", "tables"):
        arr = plan.get(section)
        if not isinstance(arr, list):
            continue
        for i, entry in enumerate(arr):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            if isinstance(path, str) and path.strip():
                if _resolve(workspace, path) is None:
                    issues.append(
                        {
                            "slide_index": None,
                            "rule": "asset_plan_missing",
                            "field": f"{section}[{i}].path",
                            "value": path,
                        }
                    )
    return issues


def verify(workspace: Path) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    outline_path = workspace / "outline.json"
    if outline_path.exists():
        try:
            outline = json.loads(outline_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return issues
        for idx, slide in enumerate(outline.get("slides") or []):
            if isinstance(slide, dict):
                issues.extend(_check_slide_assets(workspace, slide, idx))

    plan_path = workspace / "asset_plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            plan = {}
        issues.extend(_check_asset_plan(workspace, plan))

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that assets claimed in outline.json / asset_plan.json exist."
    )
    parser.add_argument("--workspace", required=True, help="Workspace directory")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 if any asset is missing (default exit 0 with warnings).",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        print(f"Error: workspace is not a directory: {workspace}", file=sys.stderr)
        return 1

    issues = verify(workspace)
    if not issues:
        print("[verify_narration] all referenced assets resolved.")
        return 0

    print(
        f"[verify_narration] {len(issues)} asset reference(s) point at "
        "missing files. Codex may have narrated staging that didn't happen.",
        file=sys.stderr,
    )
    for issue in issues:
        slide = issue.get("slide_index")
        loc = f"slide {slide}" if isinstance(slide, int) else "asset_plan"
        print(
            f"  {loc} :: {issue['rule']} :: {issue['field']} = "
            f"{issue['value']!r}",
            file=sys.stderr,
        )
    return 2 if args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
