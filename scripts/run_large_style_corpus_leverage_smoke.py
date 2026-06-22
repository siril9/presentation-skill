#!/usr/bin/env python3
"""Prove the large corpus is used by prompts and contact-sheet evidence."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageStat

from build_large_style_corpus_contact_sheets import build_contact_sheets
from large_style_corpus import (
    DEFAULT_CATALOG,
    STYLE_FAMILY_DESCRIPTORS,
    load_large_style_corpus,
    validate_large_style_corpus,
)


ROOT = Path(__file__).resolve().parent.parent


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _prompt_contains_large_corpus() -> dict:
    with tempfile.TemporaryDirectory(prefix="large-corpus-router-smoke-") as tmp_name:
        tmp = Path(tmp_name)
        _write_json(tmp / "outline.json", {"title": "Corpus leverage", "slides": []})
        for name in ("design_brief.json", "evidence_plan.json", "asset_plan.json", "content_plan.json"):
            _write_json(tmp / name, {})
        prompt_path = tmp / "router.txt"
        cmd = [
            "python3",
            str(ROOT / "scripts" / "emit_style_content_router.py"),
            "--workspace",
            str(tmp),
            "--user-prompt",
            "AI agent generated deck with code demos, product metrics, and clean source references",
            "--output",
            str(prompt_path),
        ]
        subprocess.run(cmd, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        text = prompt_path.read_text(encoding="utf-8")
    required_tokens = [
        '"large_style_corpus"',
        '"catalog_version": "large_style_corpus_v1"',
        '"record_count": 2000',
        "style_reference_structural_motif_library_v1",
        "style_source_intake",
    ]
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise AssertionError(f"router prompt missing expected corpus/reference tokens: {missing}")
    return {
        "prompt_chars": len(text),
        "large_corpus_offset": text.index('"large_style_corpus"'),
        "record_count_offset": text.index('"record_count": 2000'),
    }


def _assert_nonblank(path: Path) -> dict:
    image = Image.open(path).convert("L")
    extrema = ImageStat.Stat(image).extrema[0]
    if extrema[1] - extrema[0] <= 10:
        raise AssertionError(f"contact sheet appears blank: {path}")
    return {"path": str(path), "size": list(image.size), "luma_extrema": list(extrema)}


def main() -> int:
    catalog = load_large_style_corpus(DEFAULT_CATALOG)
    failures = validate_large_style_corpus(catalog, min_records=2000, min_family_records=10)
    if failures:
        raise AssertionError(json.dumps(failures[:8], indent=2))
    records = catalog.get("records") if isinstance(catalog.get("records"), list) else []
    catalog_record_ids = {str(record.get("deck_id")) for record in records if isinstance(record, dict)}
    if len(catalog_record_ids) < 2000:
        raise AssertionError("catalog does not expose 2,000 unique deck IDs")

    router_evidence = _prompt_contains_large_corpus()
    with tempfile.TemporaryDirectory(prefix="large-corpus-contact-smoke-") as tmp_name:
        summary = build_contact_sheets(DEFAULT_CATALOG, Path(tmp_name))
        if summary.get("catalog_record_count") != 2000:
            raise AssertionError("contact-sheet summary did not read the 2,000-record catalog")
        if summary.get("catalog_version") != "large_style_corpus_v1":
            raise AssertionError("contact-sheet summary did not carry large corpus version")
        if summary.get("storage_rule") != "descriptor_only_no_raw_decks":
            raise AssertionError("contact-sheet summary did not preserve descriptor-only storage rule")
        if int(summary.get("records_used_count") or 0) < 80:
            raise AssertionError(f"too few records used in contact sheets: {summary.get('records_used_count')}")
        family_counts = summary.get("records_used_family_counts") if isinstance(summary.get("records_used_family_counts"), dict) else {}
        missing_families = sorted(set(STYLE_FAMILY_DESCRIPTORS) - set(family_counts))
        if missing_families:
            raise AssertionError(f"contact sheets missed style families: {missing_families}")
        sheet_count = len(summary.get("contact_sheets", [])) + len(summary.get("family_sheets", []))
        if summary.get("sheet_count") != sheet_count:
            raise AssertionError(f"summary sheet_count mismatch: {summary.get('sheet_count')} != {sheet_count}")
        if sheet_count < 16:
            raise AssertionError(f"expected at least 16 sheets, saw {sheet_count}")
        used_ids = set(summary.get("records_used_ids") if isinstance(summary.get("records_used_ids"), list) else [])
        unknown_ids = sorted(used_ids - catalog_record_ids)
        if unknown_ids:
            raise AssertionError(f"contact sheets used IDs not in catalog: {unknown_ids[:5]}")
        for sheet in [*summary.get("contact_sheets", [])[:3], *summary.get("family_sheets", [])[:2]]:
            _assert_nonblank(Path(sheet["path"]))

    print(
        json.dumps(
            {
                "passed": True,
                "catalog_records": len(records),
                "router_evidence": router_evidence,
                "contact_sheet_records_used": summary.get("records_used_count"),
                "contact_sheet_count": sheet_count,
                "families_used": len(family_counts),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
