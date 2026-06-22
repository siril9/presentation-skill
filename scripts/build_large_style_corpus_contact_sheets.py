#!/usr/bin/env python3
"""Build publish-safe contact sheets from the large descriptor-only corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont, ImageStat
except Exception:  # pragma: no cover - optional visual helper
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]
    ImageStat = None  # type: ignore[assignment]

from large_style_corpus import DEFAULT_CATALOG, LARGE_STYLE_CORPUS_VERSION, load_large_style_corpus


ROOT = Path(__file__).resolve().parent.parent
CONTACT_SHEET_VERSION = "large_style_corpus_contact_sheets_v1"
DEFAULT_OUTDIR = ROOT / "decks" / f"large-style-corpus-contact-sheets-{datetime.now().strftime('%Y%m%d')}"

FAMILY_COLORS: dict[str, tuple[str, str, str]] = {
    "lab-report": ("#E9F7F8", "#0F6F78", "#C7E7EA"),
    "forest-research": ("#EEF6E8", "#497C43", "#D6E9CE"),
    "paper-journal": ("#F7F3EA", "#5E5143", "#E5DDCB"),
    "executive-clinical": ("#EDF5FF", "#245C9E", "#D4E6FA"),
    "data-heavy-boardroom": ("#EEF2F7", "#354A65", "#D7E0EA"),
    "charcoal-safety": ("#F1F1F1", "#2F3338", "#FFCF66"),
    "bold-startup-narrative": ("#FFF0EA", "#C84630", "#FFD3C7"),
    "sunset-investor": ("#FFF2DD", "#9C5E16", "#F4C06B"),
    "editorial-minimal": ("#F8F8F6", "#1F1F1D", "#DAD8D0"),
    "arctic-minimal": ("#F2F8FB", "#426B80", "#D6EAF2"),
    "midnight-neon": ("#F0F4FF", "#233A70", "#B6F0FF"),
    "lavender-ops": ("#F5F1FF", "#6951A8", "#DDD1FF"),
    "warm-terracotta": ("#FFF4EC", "#9C5A40", "#EFC9B5"),
}


def _font(size: int, *, bold: bool = False) -> Any:
    if ImageFont is None:
        return None
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _shorten(value: Any, limit: int) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _wrap(value: Any, width: int, lines: int) -> list[str]:
    wrapped = textwrap.wrap(_text(value), width=width, break_long_words=False, replace_whitespace=True)
    if len(wrapped) <= lines:
        return wrapped
    out = wrapped[:lines]
    out[-1] = _shorten(out[-1], max(8, width - 1))
    return out


def _draw_wrapped(draw: Any, xy: tuple[int, int], text: Any, *, width: int, lines: int, font: Any, fill: str, line_gap: int = 4) -> int:
    x, y = xy
    line_height = int(getattr(font, "size", 14) * 1.25) if font else 18
    for line in _wrap(text, width, lines):
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height + line_gap
    return y


def _draw_chip(draw: Any, xy: tuple[int, int], label: str, *, fill: str, outline: str, text_fill: str, font: Any) -> int:
    x, y = xy
    text = _shorten(label, 22)
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + 18
    height = bbox[3] - bbox[1] + 10
    draw.rounded_rectangle((x, y, x + width, y + height), radius=6, fill=fill, outline=outline, width=1)
    draw.text((x + 9, y + 5), text, fill=text_fill, font=font)
    return width


def _records_by_family(catalog: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in catalog.get("records", []):
        if isinstance(record, dict):
            out[_text(record.get("primary_style_family"))].append(record)
    return out


def _rank_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            -int(bool((record.get("agent_usage_signal") or {}).get("has_signal"))),
            -int(record.get("distinctiveness_score") or 0),
            _text(record.get("repository")),
            _text(record.get("path")),
        ),
    )


def _select_diverse_records(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_repos: set[str] = set()
    for record in _rank_records(records):
        repo = _text(record.get("repository"))
        if repo in used_repos and len(selected) < max(4, limit // 2):
            continue
        selected.append(record)
        used_repos.add(repo)
        if len(selected) >= limit:
            return selected
    for record in _rank_records(records):
        if record not in selected:
            selected.append(record)
        if len(selected) >= limit:
            break
    return selected


def _draw_title(draw: Any, *, title: str, subtitle: str, width: int) -> None:
    draw.text((72, 48), title, fill="#17191C", font=_font(44, bold=True))
    _draw_wrapped(draw, (72, 108), subtitle, width=120, lines=2, font=_font(20), fill="#4B535C")
    draw.line((72, 166, width - 72, 166), fill="#BCC4CC", width=2)


def _draw_family_card(draw: Any, box: tuple[int, int, int, int], family: str, summary: dict[str, Any]) -> set[str]:
    x0, y0, x1, y1 = box
    bg, accent, tint = FAMILY_COLORS.get(family, ("#F7F7F7", "#333333", "#DDDDDD"))
    draw.rounded_rectangle(box, radius=8, fill=bg, outline="#C7CDD3", width=2)
    draw.rectangle((x0, y0, x0 + 12, y1), fill=accent)
    draw.text((x0 + 28, y0 + 22), family, fill="#15171A", font=_font(24, bold=True))
    draw.text((x0 + 28, y0 + 56), f"{summary.get('record_count', 0)} records", fill=accent, font=_font(18, bold=True))
    systems = summary.get("top_deck_systems") if isinstance(summary.get("top_deck_systems"), dict) else {}
    system_text = ", ".join(f"{key}:{value}" for key, value in list(systems.items())[:3])
    y = _draw_wrapped(draw, (x0 + 28, y0 + 88), f"Systems: {system_text}", width=42, lines=2, font=_font(15), fill="#30363D")
    descriptor = summary.get("descriptor") if isinstance(summary.get("descriptor"), dict) else {}
    treatments = descriptor.get("content_treatments") if isinstance(descriptor.get("content_treatments"), list) else []
    layout_tags = descriptor.get("layout_tags") if isinstance(descriptor.get("layout_tags"), list) else []
    chip_x = x0 + 28
    chip_y = y + 8
    used_labels: set[str] = set()
    for label in [*layout_tags[:2], *treatments[:3]]:
        used_labels.add(str(label))
        chip_w = _draw_chip(draw, (chip_x, chip_y), str(label), fill=tint, outline=accent, text_fill="#1F252B", font=_font(13))
        chip_x += chip_w + 8
        if chip_x > x1 - 135:
            chip_x = x0 + 28
            chip_y += 34
    samples = summary.get("sample_sources") if isinstance(summary.get("sample_sources"), list) else []
    y = chip_y + 44
    for sample in samples[:2]:
        if not isinstance(sample, dict):
            continue
        y = _draw_wrapped(
            draw,
            (x0 + 28, y),
            f"{sample.get('deck_system')} / {sample.get('repository')} / {sample.get('path')}",
            width=48,
            lines=1,
            font=_font(12),
            fill="#59616A",
            line_gap=1,
        )
    return used_labels


def _draw_record_card(draw: Any, box: tuple[int, int, int, int], record: dict[str, Any], *, index: int) -> set[str]:
    x0, y0, x1, y1 = box
    family = _text(record.get("primary_style_family"))
    bg, accent, tint = FAMILY_COLORS.get(family, ("#F7F7F7", "#333333", "#DDDDDD"))
    draw.rounded_rectangle(box, radius=8, fill=bg, outline="#C7CDD3", width=2)
    draw.rectangle((x0, y0, x1, y0 + 10), fill=accent)
    draw.text((x0 + 18, y0 + 24), f"{index:02d}  {family}", fill="#15171A", font=_font(20, bold=True))
    draw.text((x1 - 160, y0 + 27), _text(record.get("deck_system")), fill=accent, font=_font(13, bold=True))
    y = _draw_wrapped(draw, (x0 + 18, y0 + 58), _shorten(record.get("repository"), 70), width=42, lines=1, font=_font(14, bold=True), fill="#28313A")
    y = _draw_wrapped(draw, (x0 + 18, y + 2), record.get("path"), width=52, lines=2, font=_font(12), fill="#4C5560", line_gap=2)
    signal = record.get("agent_usage_signal") if isinstance(record.get("agent_usage_signal"), dict) else {}
    evidence = record.get("deck_like_evidence") if isinstance(record.get("deck_like_evidence"), dict) else {}
    meta = f"id {record.get('deck_id')} | {record.get('deck_format')} | {evidence.get('confidence', 'n/a')}"
    if signal.get("has_signal"):
        meta += " | AI signal"
    y = _draw_wrapped(draw, (x0 + 18, y + 6), meta, width=56, lines=2, font=_font(11), fill="#68717B", line_gap=1)
    chip_x = x0 + 18
    chip_y = y + 8
    labels: set[str] = set()
    for label in (record.get("content_treatments") if isinstance(record.get("content_treatments"), list) else [])[:4]:
        labels.add(str(label))
        chip_w = _draw_chip(draw, (chip_x, chip_y), str(label), fill=tint, outline=accent, text_fill="#1F252B", font=_font(12))
        chip_x += chip_w + 8
        if chip_x > x1 - 120:
            chip_x = x0 + 18
            chip_y += 31
    return labels


def _save_nonblank(image: Any, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    stat = ImageStat.Stat(image.convert("L")) if ImageStat is not None else None
    extrema = stat.extrema[0] if stat else (0, 0)
    return {
        "path": str(path),
        "size": list(image.size),
        "sha256": _sha256(path),
        "luma_extrema": list(extrema),
        "nonblank": bool(extrema[1] - extrema[0] > 10),
    }


def _family_overview_sheet(catalog: dict[str, Any], outdir: Path) -> tuple[dict[str, Any], set[str], set[str]]:
    summaries = catalog.get("family_summaries") if isinstance(catalog.get("family_summaries"), dict) else {}
    families = sorted(summaries)
    card_w, card_h = 520, 255
    margin_x, gap = 72, 28
    columns = 4
    rows = (len(families) + columns - 1) // columns
    width = margin_x * 2 + columns * card_w + (columns - 1) * gap
    height = 210 + rows * card_h + (rows - 1) * gap + 72
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    _draw_title(
        draw,
        title="Large Style Corpus / Family Overview",
        subtitle=f"{catalog.get('summary', {}).get('record_count', 0)} descriptor-only records across {len(families)} style families",
        width=width,
    )
    labels: set[str] = set()
    for idx, family in enumerate(families):
        row, col = divmod(idx, columns)
        x0 = margin_x + col * (card_w + gap)
        y0 = 205 + row * (card_h + gap)
        labels.update(_draw_family_card(draw, (x0, y0, x0 + card_w, y0 + card_h), family, summaries[family]))
    draw.text((72, height - 46), "Descriptor-only: no source deck screenshots, logos, copied text, or raw files.", fill="#59616A", font=_font(15))
    return _save_nonblank(image, outdir / "large_corpus_family_overview.png"), set(), labels


def _record_grid_sheet(title: str, subtitle: str, records: list[dict[str, Any]], outpath: Path, *, columns: int = 4) -> tuple[dict[str, Any], set[str], set[str]]:
    card_w, card_h = 505, 250
    margin_x, gap = 72, 26
    rows = (len(records) + columns - 1) // columns
    width = margin_x * 2 + columns * card_w + (columns - 1) * gap
    height = 210 + rows * card_h + (rows - 1) * gap + 72
    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    _draw_title(draw, title=title, subtitle=subtitle, width=width)
    used_ids: set[str] = set()
    used_labels: set[str] = set()
    for idx, record in enumerate(records):
        row, col = divmod(idx, columns)
        x0 = margin_x + col * (card_w + gap)
        y0 = 205 + row * (card_h + gap)
        used_ids.add(_text(record.get("deck_id")))
        used_labels.update(_draw_record_card(draw, (x0, y0, x0 + card_w, y0 + card_h), record, index=idx + 1))
    draw.text((72, height - 46), "Cards are synthetic descriptors from metadata; source decks were not downloaded or rendered.", fill="#59616A", font=_font(15))
    return _save_nonblank(image, outpath), used_ids, used_labels


def build_contact_sheets(catalog_path: Path = DEFAULT_CATALOG, outdir: Path = DEFAULT_OUTDIR) -> dict[str, Any]:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required to build contact sheets")
    catalog = load_large_style_corpus(catalog_path)
    records = [record for record in catalog.get("records", []) if isinstance(record, dict)]
    by_family = _records_by_family(catalog)
    outdir.mkdir(parents=True, exist_ok=True)
    family_dir = outdir / "families"
    contact_sheets: list[dict[str, Any]] = []
    used_record_ids: set[str] = set()
    used_treatments: set[str] = set()

    sheet, ids, labels = _family_overview_sheet(catalog, outdir)
    sheet.update({"sheet_id": "family_overview", "kind": "family_summary"})
    contact_sheets.append(sheet)
    used_record_ids.update(ids)
    used_treatments.update(labels)

    ai_records = _select_diverse_records(
        [
            record
            for record in records
            if bool((record.get("agent_usage_signal") or {}).get("has_signal"))
            or "ai-agent" in (record.get("descriptor_tags") if isinstance(record.get("descriptor_tags"), list) else [])
        ],
        24,
    )
    sheet, ids, labels = _record_grid_sheet(
        "Large Style Corpus / AI-Agent Slice",
        "Representative AI, agent, LLM, Slidev, and automation signals from the 2,000-record descriptor catalog",
        ai_records,
        outdir / "large_corpus_ai_agent_slice.png",
    )
    sheet.update({"sheet_id": "ai_agent_slice", "kind": "record_grid", "record_count": len(ai_records)})
    contact_sheets.append(sheet)
    used_record_ids.update(ids)
    used_treatments.update(labels)

    system_records: list[dict[str, Any]] = []
    systems: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        systems[_text(record.get("deck_system"))].append(record)
    for system in sorted(systems):
        system_records.extend(_select_diverse_records(systems[system], 3))
    system_records = _select_diverse_records(system_records, 24)
    sheet, ids, labels = _record_grid_sheet(
        "Large Style Corpus / Source-System Mix",
        "PowerPoint, PDF, Slidev, Marp, reveal.js, ODP, and web-slide descriptors selected from the catalog",
        system_records,
        outdir / "large_corpus_system_mix.png",
    )
    sheet.update({"sheet_id": "source_system_mix", "kind": "record_grid", "record_count": len(system_records)})
    contact_sheets.append(sheet)
    used_record_ids.update(ids)
    used_treatments.update(labels)

    family_sheets: list[dict[str, Any]] = []
    for family in sorted(by_family):
        selected = _select_diverse_records(by_family[family], 8)
        sheet, ids, labels = _record_grid_sheet(
            f"{family} / Corpus Records",
            "Top diverse descriptor records for this style family",
            selected,
            family_dir / f"{family}.png",
            columns=4,
        )
        sheet.update({"sheet_id": f"family_{family}", "kind": "family_record_grid", "style_family": family, "record_count": len(selected)})
        family_sheets.append(sheet)
        used_record_ids.update(ids)
        used_treatments.update(labels)

    used_records = [record for record in records if _text(record.get("deck_id")) in used_record_ids]
    used_family_counts = Counter(_text(record.get("primary_style_family")) for record in used_records)
    used_system_counts = Counter(_text(record.get("deck_system")) for record in used_records)
    sheet_count = len(contact_sheets) + len(family_sheets)
    summary = {
        "summary_version": CONTACT_SHEET_VERSION,
        "catalog_version": catalog.get("catalog_version"),
        "catalog_path": str(catalog_path),
        "catalog_sha256": _sha256(catalog_path),
        "catalog_record_count": len(records),
        "catalog_unique_repository_count": catalog.get("summary", {}).get("unique_repository_count"),
        "catalog_ai_agent_signal_count": catalog.get("summary", {}).get("ai_agent_signal_count"),
        "storage_rule": catalog.get("policy", {}).get("storage_rule") if isinstance(catalog.get("policy"), dict) else None,
        "output_dir": str(outdir),
        "descriptor_only": True,
        "no_raw_source_decks_rendered": True,
        "sheet_count": sheet_count,
        "contact_sheets": contact_sheets,
        "family_sheets": family_sheets,
        "records_used_count": len(used_record_ids),
        "records_used_ids": sorted(used_record_ids),
        "records_used_family_counts": dict(sorted(used_family_counts.items())),
        "records_used_system_counts": dict(sorted(used_system_counts.items())),
        "treatment_labels_used_count": len(used_treatments),
        "treatment_labels_used": sorted(used_treatments),
    }
    summary_path = outdir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="Large corpus catalog JSON")
    parser.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="Output directory")
    return parser.parse_args()


def main() -> int:
    args = _args()
    summary = build_contact_sheets(Path(args.catalog).expanduser().resolve(), Path(args.outdir).expanduser().resolve())
    print(json.dumps({"passed": True, "summary_path": summary["summary_path"], "records_used_count": summary["records_used_count"], "sheet_count": summary["sheet_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
