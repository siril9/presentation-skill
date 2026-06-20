#!/usr/bin/env python3
"""Stage source-backed deck assets into a local manifest."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

from fetch_wikimedia_cc import search_and_download
from generate_openai_image import DEFAULT_FORMAT, DEFAULT_MODEL, DEFAULT_QUALITY, DEFAULT_SIZE, generate_image
from palette_from_topic import choose_palette_for_topic


ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_STAGE_ALIAS_SECTIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("images", "images", ("asset", "image")),
    ("backgrounds", "backgrounds", ("asset", "background")),
    ("charts", "chart", ("asset", "chart")),
    ("tables", "table", ("asset", "table")),
    ("generated_images", "generated", ("asset", "image", "generated")),
)


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_")


def _stage_name(spec: dict[str, Any], *, default_base: str, index: int) -> str:
    fallback = f"{default_base}_{index + 1}"
    return _safe_name(str(spec.get("name") or fallback)) or fallback


def _entry_label(section: str, index: int, raw_name: Any, name: str) -> str:
    explicit = str(raw_name or "").strip()
    if explicit:
        return f"{section}[{index}] name {explicit!r} -> {name!r}"
    return f"{section}[{index}] default name {name!r}"


def _manifest_entries(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    entries_by_section: dict[str, list[dict[str, Any]]] = {}
    for section, _default_base, _prefixes in _STAGE_ALIAS_SECTIONS:
        raw_entries = manifest.get(section, [])
        if raw_entries is None:
            raw_entries = []
        if not isinstance(raw_entries, list):
            raise RuntimeError(f"asset_plan.{section} must be a list")
        entries: list[dict[str, Any]] = []
        for index, entry in enumerate(raw_entries):
            if not isinstance(entry, dict):
                raise RuntimeError(f"asset_plan.{section}[{index}] must be an object")
            entries.append(entry)
        entries_by_section[section] = entries
    return entries_by_section


def _validate_unique_stage_aliases(entries_by_section: dict[str, list[dict[str, Any]]]) -> None:
    seen_aliases: dict[str, str] = {}
    for section, default_base, prefixes in _STAGE_ALIAS_SECTIONS:
        entries = entries_by_section.get(section, [])
        for index, spec in enumerate(entries):
            name = _stage_name(spec, default_base=default_base, index=index)
            key = name.strip().lower()
            label = _entry_label(section, index, spec.get("name"), name)
            for prefix in prefixes:
                alias = f"{prefix}:{key}"
                previous = seen_aliases.get(alias)
                if previous is not None:
                    raise RuntimeError(
                        f"Duplicate staged asset alias '{alias}' after name normalization: "
                        f"{previous} conflicts with {label}. "
                        "Use distinct asset_plan names so aliases and staged outputs stay reproducible."
                    )
                seen_aliases[alias] = label


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def _copy_local_asset(src: Path, target_dir: Path, name: str) -> Path:
    suffix = src.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise RuntimeError(
            f"Unsupported local asset format for {src.name}. "
            "Use PNG or JPG/JPEG for the open-source-safe staging path."
        )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{name}{suffix}"
    shutil.copy2(src, target)
    return target


def _metadata_payload(spec: dict[str, Any], *, provider: str, source: str | None = None) -> dict[str, Any]:
    return {
        "provider": provider,
        "source": source,
        "source_note": spec.get("source_note"),
        "source_url": spec.get("source_url"),
        "source_page": spec.get("source_page"),
        "license": spec.get("license"),
        "license_url": spec.get("license_url"),
        "artist": spec.get("artist"),
        "credit": spec.get("credit"),
        "provenance": spec.get("provenance") or provider,
        "generated": bool(spec.get("generated")),
    }


def _write_metadata(target: Path, metadata: dict[str, Any]) -> Path:
    metadata_path = Path(f"{target}.metadata.json")
    _write_json(metadata_path, metadata)
    return metadata_path


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _cached_json_payload(path: Path, cache: dict[Path, Any] | None = None) -> Any:
    if cache is None:
        return _read_json_payload(path)
    key = path.resolve()
    if key not in cache:
        cache[key] = _read_json_payload(key)
    return cache[key]


def _resolve_manifest_path(raw: str, manifest_dir: Path) -> Path:
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (manifest_dir / path).resolve()


def _is_number_like(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _validate_values(values: Any, *, base: str) -> None:
    if not isinstance(values, list) or not values:
        raise RuntimeError(f"{base} must be a non-empty list")
    bad = [idx for idx, value in enumerate(values) if not _is_number_like(value)]
    if bad:
        raise RuntimeError(f"{base} contains non-numeric values at index(es): {', '.join(map(str, bad))}")


def _validate_chart_payload(payload: dict[str, Any], *, name: str) -> None:
    series = payload.get("series")
    categories = payload.get("categories") if isinstance(payload.get("categories"), list) else payload.get("labels")
    flat_values = payload.get("values")

    if isinstance(series, list) and series:
        top_categories = categories if isinstance(categories, list) and categories else None
        for idx, item in enumerate(series):
            base = f"Chart JSON for '{name}' series[{idx}]"
            if not isinstance(item, dict):
                raise RuntimeError(f"{base} must be an object")
            values = item.get("values")
            _validate_values(values, base=f"{base}.values")
            labels = item.get("labels")
            if top_categories is not None and len(top_categories) != len(values):
                raise RuntimeError(
                    f"{base}.values length ({len(values)}) does not match chart categories length ({len(top_categories)})"
                )
            if isinstance(labels, list) and labels and len(labels) != len(values):
                raise RuntimeError(
                    f"{base}.labels length ({len(labels)}) does not match values length ({len(values)})"
                )
            if top_categories is None and not (isinstance(labels, list) and labels):
                raise RuntimeError(f"{base} needs labels or top-level categories")
        return

    if isinstance(categories, list) and categories and isinstance(flat_values, list) and flat_values:
        _validate_values(flat_values, base=f"Chart JSON for '{name}' values")
        if len(categories) != len(flat_values):
            raise RuntimeError(
                f"Chart JSON for '{name}' categories length ({len(categories)}) does not match values length ({len(flat_values)})"
            )
        return

    raise RuntimeError(
        f"Chart JSON for '{name}' must include either non-empty series[].values "
        "with labels/categories or top-level categories+values"
    )


def _validate_table_payload(payload: dict[str, Any], *, name: str) -> None:
    headers = payload.get("headers")
    rows = payload.get("rows")
    if not isinstance(headers, list) or not headers:
        raise RuntimeError(f"Table JSON for '{name}' must include a non-empty headers list")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"Table JSON for '{name}' must include a non-empty rows list")
    width = len(headers)
    for idx, row in enumerate(rows):
        if not isinstance(row, list):
            raise RuntimeError(f"Table JSON for '{name}' rows[{idx}] must be a list")
        if len(row) != width:
            raise RuntimeError(
                f"Table JSON for '{name}' rows[{idx}] has {len(row)} cells but headers define {width} columns"
            )
    column_weights = payload.get("column_weights")
    if column_weights is not None:
        if not isinstance(column_weights, list):
            raise RuntimeError(f"Table JSON for '{name}' column_weights must be a list when present")
        if len(column_weights) != width:
            raise RuntimeError(
                f"Table JSON for '{name}' column_weights length ({len(column_weights)}) does not match header count ({width})"
            )
        if any(not _is_number_like(value) for value in column_weights):
            raise RuntimeError(f"Table JSON for '{name}' column_weights must contain only numeric values")


def _ensure_provenance(spec: dict[str, Any], *, name: str) -> None:
    if bool(spec.get("generated")):
        raise RuntimeError(f"Asset '{name}' is marked generated. Use source-backed or licensed assets instead.")
    required = ("source_note", "source_url", "source_page", "license", "provenance")
    if not any(spec.get(key) for key in required):
        raise RuntimeError(
            f"Asset '{name}' is missing provenance metadata. "
            "Provide at least one of source_note, source_url, source_page, license, or provenance."
        )


def _row_for_asset(
    *,
    target: Path,
    title: str,
    query: str = "",
    source_page: str = "",
    source_url: str = "",
    license_name: str = "",
    license_url: str = "",
    artist: str = "",
    credit: str = "",
) -> dict[str, str]:
    return {
        "file_name": target.name,
        "file_path": str(target),
        "title": title,
        "source_page": source_page,
        "image_url": source_url,
        "license": license_name,
        "license_url": license_url,
        "artist": artist,
        "credit": credit,
        "query": query,
    }


def _write_attribution_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "file_name",
        "file_path",
        "title",
        "source_page",
        "image_url",
        "license",
        "license_url",
        "artist",
        "credit",
        "query",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return
    path.write_bytes(data)


def _stage_local_or_remote(
    entries: list[dict[str, Any]],
    *,
    kind: str,
    output_dir: Path,
    manifest_dir: Path,
    attribution_rows: list[dict[str, str]],
    allow_network: bool,
    strict_provenance: bool,
) -> list[dict[str, Any]]:
    staged: list[dict[str, Any]] = []
    kind_dir = output_dir / kind
    kind_dir.mkdir(parents=True, exist_ok=True)

    for index, spec in enumerate(entries):
        name = _stage_name(spec, default_base=kind, index=index)
        if spec.get("path"):
            if strict_provenance:
                _ensure_provenance(spec, name=name)
            src = _resolve_manifest_path(str(spec["path"]), manifest_dir)
            if not src.exists():
                raise FileNotFoundError(f"Asset path not found for '{name}': {src}")
            target = _copy_local_asset(src, kind_dir, name)
            metadata_path = _write_metadata(target, _metadata_payload(spec, provider="local_file", source=str(src)))
            attribution_rows.append(
                _row_for_asset(
                    target=target,
                    title=str(spec.get("title") or name),
                    source_page=str(spec.get("source_page") or ""),
                    source_url=str(spec.get("source_url") or src),
                    license_name=str(spec.get("license") or ""),
                    license_url=str(spec.get("license_url") or ""),
                    artist=str(spec.get("artist") or ""),
                    credit=str(spec.get("credit") or ""),
                )
            )
            staged.append(
                {
                    "kind": kind,
                    "name": name,
                    "path": str(target),
                    "metadata_path": str(metadata_path),
                    "source": str(src),
                }
            )
            continue

        if spec.get("wikimedia_query"):
            if not allow_network:
                raise RuntimeError(
                    f"Asset '{name}' requests Wikimedia fetches. Re-run with --allow-network."
                )
            result = search_and_download(
                str(spec["wikimedia_query"]),
                kind_dir,
                limit=int(spec.get("limit", 12)),
                allow_sharealike=bool(spec.get("allow_sharealike", True)),
                name=name,
            )
            target = Path(result["image_path"]).resolve()
            metadata_path = Path(result["metadata_path"]).resolve()
            attribution_rows.append(
                _row_for_asset(
                    target=target,
                    title=result["title"],
                    query=str(spec["wikimedia_query"]),
                    source_page=result["source_page"],
                    source_url=result["image_url"],
                    license_name=result["license"],
                    license_url=result["license_url"],
                    artist=result["artist"],
                    credit=result["credit"],
                )
            )
            staged.append(
                {
                    "kind": kind,
                    "name": name,
                    "path": str(target),
                    "metadata_path": str(metadata_path),
                    "source_query": str(spec["wikimedia_query"]),
                    "source_page": result["source_page"],
                    "license": result["license"],
                }
            )
            continue

        raise RuntimeError(f"Asset '{name}' must specify either 'path' or 'wikimedia_query'.")

    return staged


def _stage_json_assets(
    entries: list[dict[str, Any]],
    output_dir: Path,
    *,
    manifest_dir: Path,
    kind: str,
    required_keys: tuple[str, ...],
    json_payload_cache: dict[Path, Any] | None = None,
) -> list[dict[str, Any]]:
    asset_dir = output_dir / kind
    asset_dir.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, Any]] = []
    singular = kind[:-1] if kind.endswith("s") else kind
    for index, spec in enumerate(entries):
        name = _stage_name(spec, default_base=singular, index=index)
        target = asset_dir / f"{name}.json"
        if spec.get("path"):
            src = _resolve_manifest_path(str(spec["path"]), manifest_dir)
            if not src.exists():
                raise FileNotFoundError(f"{singular.title()} path not found for '{name}': {src}")
            loaded_payload = _cached_json_payload(src, json_payload_cache)
            if not isinstance(loaded_payload, dict):
                raise RuntimeError(f"{singular.title()} JSON must decode to an object: {src}")
            payload = dict(loaded_payload)
        else:
            payload = dict(spec)
        missing = [key for key in required_keys if key not in payload]
        if missing:
            raise RuntimeError(f"{singular.title()} JSON for '{name}' missing required keys: {', '.join(missing)}")
        if kind == "charts":
            _validate_chart_payload(payload, name=name)
        elif kind == "tables":
            _validate_table_payload(payload, name=name)
        payload["name"] = name
        payload.pop("path", None)
        _write_json(target, payload)
        staged.append({"kind": singular, "name": name, "path": str(target)})
    return staged


def _stage_charts(
    charts: list[dict[str, Any]],
    output_dir: Path,
    *,
    manifest_dir: Path,
    json_payload_cache: dict[Path, Any] | None = None,
) -> list[dict[str, Any]]:
    return _stage_json_assets(
        charts,
        output_dir,
        manifest_dir=manifest_dir,
        kind="charts",
        required_keys=(),
        json_payload_cache=json_payload_cache,
    )


def _stage_tables(
    tables: list[dict[str, Any]],
    output_dir: Path,
    *,
    manifest_dir: Path,
    json_payload_cache: dict[Path, Any] | None = None,
) -> list[dict[str, Any]]:
    return _stage_json_assets(
        tables,
        output_dir,
        manifest_dir=manifest_dir,
        kind="tables",
        required_keys=("headers", "rows"),
        json_payload_cache=json_payload_cache,
    )


def _stage_generated_images(
    entries: list[dict[str, Any]],
    *,
    output_dir: Path,
    manifest_dir: Path,
    allow_generation: bool,
    attribution_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    generated_dir = output_dir / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, Any]] = []
    for index, spec in enumerate(entries):
        name = _stage_name(spec, default_base="generated", index=index)
        output_format = str(spec.get("output_format") or DEFAULT_FORMAT).strip().lower().lstrip(".")
        if output_format not in {"png", "webp", "jpg", "jpeg"}:
            raise RuntimeError(f"Generated image '{name}' has unsupported output_format: {output_format}")
        target = generated_dir / f"{name}.{output_format}"

        if spec.get("path"):
            src = _resolve_manifest_path(str(spec["path"]), manifest_dir)
            if not src.exists():
                raise FileNotFoundError(f"Generated image path not found for '{name}': {src}")
            target = _copy_local_asset(src, generated_dir, name)
            metadata_path = _write_metadata(
                target,
                _metadata_payload(spec, provider="generated_openai_image", source=str(src))
                | {
                    "generated": True,
                    "prompt": spec.get("prompt"),
                    "model": spec.get("model"),
                    "purpose": spec.get("purpose"),
                    "edit_note": spec.get("edit_note"),
                },
            )
        else:
            prompt = str(spec.get("prompt") or "").strip()
            if not prompt:
                raise RuntimeError(f"Generated image '{name}' must specify either 'path' or 'prompt'.")
            if not allow_generation:
                raise RuntimeError(
                    f"Generated image '{name}' requires an OpenAI API call. "
                    "Re-run with --allow-generated-images."
                )
            result = generate_image(
                prompt=prompt,
                output=target,
                metadata_path=Path(f"{target}.metadata.json"),
                model=str(spec.get("model") or DEFAULT_MODEL),
                size=str(spec.get("size") or DEFAULT_SIZE),
                quality=str(spec.get("quality") or DEFAULT_QUALITY),
                output_format=output_format,
                background=str(spec.get("background") or "auto"),
                purpose=str(spec.get("purpose") or ""),
                edit_note=str(spec.get("edit_note") or ""),
            )
            metadata_path = Path(result["metadata_path"]).resolve()

        attribution_rows.append(
            _row_for_asset(
                target=target,
                title=str(spec.get("title") or name),
                source_page=str(spec.get("source_page") or "OpenAI Images API"),
                source_url=str(spec.get("source_url") or ""),
                license_name=str(spec.get("license") or "Generated asset"),
                license_url=str(spec.get("license_url") or ""),
                artist=str(spec.get("artist") or "OpenAI image model"),
                credit=str(spec.get("credit") or "Generated image"),
                query=str(spec.get("prompt") or ""),
            )
        )
        staged.append(
            {
                "kind": "generated_image",
                "name": name,
                "path": str(target.resolve()),
                "metadata_path": str(metadata_path),
                "generated": True,
                "model": str(spec.get("model") or DEFAULT_MODEL),
                "purpose": str(spec.get("purpose") or ""),
            }
        )
    return staged


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage source-backed deck assets into a reusable manifest.")
    parser.add_argument("--manifest", required=True, help="JSON manifest describing images/backgrounds/charts/tables")
    parser.add_argument("--output-dir", required=True, help="Directory for staged assets")
    parser.add_argument("--attribution-csv", help="CSV file to write attribution rows")
    parser.add_argument("--allow-network", action="store_true", help="Allow Wikimedia Commons fetches")
    parser.add_argument(
        "--allow-generated-images",
        action="store_true",
        help="Allow OpenAI Images API calls for manifest.generated_images entries",
    )
    parser.add_argument(
        "--strict-provenance",
        action="store_true",
        help="Reject local assets that lack source/provenance metadata",
    )
    return parser.parse_args()


def main() -> int:
    args = _args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest = _load_manifest(manifest_path)
    if not isinstance(manifest, dict):
        raise RuntimeError("Asset manifest must decode to an object")
    entries_by_section = _manifest_entries(manifest)
    _validate_unique_stage_aliases(entries_by_section)
    output_dir.mkdir(parents=True, exist_ok=True)

    topic = str(manifest.get("topic") or manifest.get("palette_topic") or "general presentation").strip()
    palette_payload = choose_palette_for_topic(topic)
    palette_path = output_dir / "palette.json"
    _write_json(palette_path, palette_payload)

    attribution_rows: list[dict[str, str]] = []
    images = _stage_local_or_remote(
        entries_by_section["images"],
        kind="images",
        output_dir=output_dir,
        manifest_dir=manifest_path.parent,
        attribution_rows=attribution_rows,
        allow_network=args.allow_network,
        strict_provenance=args.strict_provenance,
    )
    backgrounds = _stage_local_or_remote(
        entries_by_section["backgrounds"],
        kind="backgrounds",
        output_dir=output_dir,
        manifest_dir=manifest_path.parent,
        attribution_rows=attribution_rows,
        allow_network=args.allow_network,
        strict_provenance=args.strict_provenance,
    )
    json_payload_cache: dict[Path, Any] = {}
    charts = _stage_charts(
        entries_by_section["charts"],
        output_dir,
        manifest_dir=manifest_path.parent,
        json_payload_cache=json_payload_cache,
    )
    tables = _stage_tables(
        entries_by_section["tables"],
        output_dir,
        manifest_dir=manifest_path.parent,
        json_payload_cache=json_payload_cache,
    )
    generated_images = _stage_generated_images(
        entries_by_section["generated_images"],
        output_dir=output_dir,
        manifest_dir=manifest_path.parent,
        allow_generation=args.allow_generated_images,
        attribution_rows=attribution_rows,
    )

    attribution_csv = (
        Path(args.attribution_csv).expanduser().resolve()
        if args.attribution_csv
        else output_dir.parent / "attribution.csv"
    )
    _write_attribution_csv(attribution_csv, attribution_rows)

    staged_manifest = {
        "workspace_assets_version": 1,
        "topic": topic,
        "palette_path": str(palette_path),
        "palette": palette_payload,
        "images": images,
        "backgrounds": backgrounds,
        "charts": charts,
        "tables": tables,
        "generated_images": generated_images,
        "attribution_csv": str(attribution_csv),
    }
    staged_manifest_path = output_dir / "staged_manifest.json"
    _write_json(staged_manifest_path, staged_manifest)
    print(json.dumps({"staged_manifest": str(staged_manifest_path), **staged_manifest}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
