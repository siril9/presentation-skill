"""Build a bounded, source-first repair context from existing QA reports.

Counts describe diagnostic records, not unique defects across independent audits.
Layout records duplicated in qa_report.json are read only once. This helper does
not run QA, modify source, or certify that an artifact is ready for delivery.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_MAX_BYTES = 12_000
SCHEMA_VERSION = "repair_packet_v1"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON number {value} in {path}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def _pointer_key(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _counts(payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    return {
        key: value for key, value in payload.items()
        if key.endswith("_count") and type(value) is int
    }


def _bounded(value: Any, depth: int = 0) -> tuple[Any, bool]:
    """Keep small measurements structured; flag every elision explicitly."""
    if isinstance(value, str):
        return value[:240], len(value) > 240
    if isinstance(value, (dict, list)):
        if depth >= 4:
            return None, True
        entries = sorted(value.items()) if isinstance(value, dict) else list(enumerate(value))
        limit = 18 if isinstance(value, dict) else 6
        truncated = len(entries) > limit
        result: Any = {} if isinstance(value, dict) else []
        for key, item in entries[:limit]:
            compact, clipped = _bounded(item, depth + 1)
            truncated |= clipped
            if isinstance(result, dict):
                result[key] = compact
            else:
                result.append(compact)
        return result, truncated
    return value, False


def _instruction(issue: dict[str, Any]) -> str:
    for key in ("suggested_fix", "suggestion"):
        if isinstance(issue.get(key), str) and issue[key].strip():
            return issue[key]
    rule = str(issue.get("type") or issue.get("code") or "").lower()
    if "alt_text" in rule:
        return "Add meaningful alt text to the matching source asset; verify the emitted object."
    if "reading_order" in rule:
        return "Correct source reading order so the headline precedes its evidence; rebuild and inspect."
    if "title" in rule and "missing" in rule:
        return "Supply a meaningful slide title in source and verify the rendered title."
    if any(word in rule for word in ("minimum", "font", "readability")):
        return "Meet the reported type threshold; shorten or split content before shrinking text."
    if any(word in rule for word in ("overlap", "overflow", "intrusion", "margin", "gap", "frame")):
        return "Repair source content or its supported layout to resolve measured fit and spacing; rebuild."
    if any(word in rule for word in ("placeholder", "branding")):
        return "Replace residual placeholder or unrelated branding in source with verified content."
    if rule == "audit_failed":
        return "Resolve the reported audit failure and rerun the audit before making a delivery claim."
    return "Inspect the diagnostic and source slide; correct the reported rule, rebuild, and rerun QA."


def build_repair_packet(
    outline: str | Path, qa_dir: str | Path, *, max_bytes: int = DEFAULT_MAX_BYTES
) -> dict[str, Any]:
    """Return JSON-serializable repairs; never infer source fields from shape IDs.

    ``max_bytes`` targets compact ASCII JSON including its trailing newline.
    Full counts, affected-slide identities, and detail paths are never dropped;
    exceptionally large metadata can exceed the budget, explicitly flagged.
    """
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    outline_path = Path(outline).expanduser().resolve()
    directory = Path(qa_dir).expanduser().resolve()
    source = _read(outline_path)
    if not isinstance(source, dict) or not isinstance(source.get("slides"), list):
        raise ValueError("outline must be an object with a slides array")
    slides = source["slides"]
    qa_path = directory / "qa_report.json"
    qa = _read(qa_path) if qa_path.exists() else {}
    if not isinstance(qa, dict):
        raise ValueError(f"Expected a report object: {qa_path}")

    paths: dict[str, Path] = {"qa_report": qa_path}
    payloads: dict[str, Any] = {"qa_report": qa}
    statuses = {"qa_report": "present" if qa_path.exists() else "missing"}
    specs = (
        ("layout", "layout_lint.json", None),
        ("design", "design_rules.json", "design_report"),
        ("accessibility", "accessibility.json", "accessibility_report"),
        ("inventory", "issues.json", None),
        ("visual", "visual_qa.json", "visual_report"),
        ("visual_review", "visual_review/visual_review.json", "visual_review_report"),
    )
    for name, filename, field in specs:
        raw_path = qa.get(field) if field else None
        path = Path(raw_path).expanduser() if raw_path else directory / filename
        if raw_path and not path.is_absolute():
            path = directory / path
        paths[name] = path.resolve()
        disabled = (
            name == "accessibility" and qa.get("accessibility_enabled") is False
        ) or (name == "visual_review" and field in qa and not raw_path)
        statuses[name] = "disabled" if disabled else "present" if path.exists() else "missing"
        if statuses[name] == "present":
            payload = _read(path)
            expected = list if name == "visual" else dict
            if not isinstance(payload, expected):
                raise ValueError(f"Expected {expected.__name__} report: {path}")
            payloads[name] = payload

    # Only source-specific index fields are authoritative. No integer guessing.
    records: list[tuple[str, str, int | None, dict[str, Any]]] = []

    def add(name: str, pointer: str, issue: Any, index: Any) -> None:
        if not isinstance(issue, dict):
            raise ValueError(f"Expected diagnostic object: {paths[name]}#{pointer}")
        index = index if type(index) is int and 0 <= index < len(slides) else None
        records.append((name, pointer, index, issue))

    layout = payloads.get("layout")
    if layout is not None:
        for position, slide in enumerate(layout.get("slides", [])):
            for offset, issue in enumerate(slide.get("violations", [])):
                add("layout", f"/slides/{position}/violations/{offset}", issue, slide.get("slide_index"))
    else:
        for position, issue in enumerate(qa.get("geometry_violations", [])):
            add("qa_report", f"/geometry_violations/{position}", issue, issue.get("slide_index"))

    for name, key, index_key, base in (
        ("design", "issues", "slide_index", 0),
        ("accessibility", "findings", "slide_number", 1),
        ("visual", None, "slide", 1),
        ("visual_review", "issues", "slide", 1),
    ):
        payload = payloads.get(name, [] if key is None else {})
        for position, issue in enumerate(payload if key is None else payload.get(key, [])):
            value = issue.get(index_key)
            index = value - base if type(value) is int else None
            add(name, f"/{key}/{position}" if key else f"/{position}", issue, index)

    for slide_key, shapes in sorted(payloads.get("inventory", {}).items()):
        match = re.fullmatch(r"slide-(\d+)", slide_key)
        index = int(match[1]) - 1 if match else None
        for shape_key, detail in sorted(shapes.items()):
            for rule in ("overflow", "overlap"):
                if rule in detail:
                    add("inventory", f"/{_pointer_key(slide_key)}/{_pointer_key(shape_key)}", {
                        "type": rule, "shape_id": shape_key,
                        "text": detail.get("text", ""), rule: detail[rule],
                    }, index)
    for position, hit in enumerate(qa.get("placeholder_hits", [])):
        add("qa_report", f"/placeholder_hits/{position}", {"type": "placeholder", "text": hit}, None)

    records.sort(key=lambda row: (
        {"error": 0, "warning": 1, "info": 2}.get(row[3].get("severity"), 3),
        row[2] if row[2] is not None else len(slides), row[0], row[1],
    ))
    by_slide = Counter(index for _, _, index, _ in records)
    affected = []
    for index in sorted(i for i in by_slide if i is not None):
        slide = slides[index]
        slide_id = slide.get("slide_id", slide.get("id")) if isinstance(slide, dict) else None
        affected.append({
            "slide_index": index,
            "slide_id": slide_id if slide_id is not None else f"slide-{index + 1:02d}",
            "source_pointer": f"/slides/{index}", "finding_count": by_slide[index],
        })

    images: dict[int, str] = {}
    render_dirs = [directory / "renders"]
    review = payloads.get("visual_review", {})
    if review.get("renders_dir"):
        render_path = Path(review["renders_dir"]).expanduser()
        render_dirs.append(render_path if render_path.is_absolute() else paths["visual_review"].parent / render_path)
    for render_dir in render_dirs:
        for path in sorted(render_dir.glob("slide-*")):
            match = re.fullmatch(r"slide-(\d+)\.(?:jpg|jpeg|png)", path.name)
            if match and path.is_file():
                images.setdefault(int(match[1]) - 1, str(path.resolve()))

    groups: dict[int | None, dict[str, Any]] = {}
    identities = {item["slide_index"]: item for item in affected}
    for name, pointer, index, issue in records:
        if index not in groups:
            excerpt = _json(slides[index]) if index is not None else ""
            groups[index] = {
                **identities.get(index, {"slide_index": None, "slide_id": None, "source_pointer": None}),
                "finding_count": by_slide[index], "image_path": images.get(index),
                "source_excerpt": excerpt[:600], "excerpt_truncated": len(excerpt) > 600,
                "issues": [],
            }
        group = groups[index]
        if len(group["issues"]) >= 6:
            continue
        diagnostic, truncated = _bounded(issue)
        instruction = _instruction(issue)
        group["issues"].append({
            "source": name, "detail_pointer": pointer, "diagnostic": diagnostic,
            "instruction": instruction[:300],
            "details_truncated": truncated or len(instruction) > 300,
        })

    reported = {name: _counts(payload) for name, payload in payloads.items()}
    if layout is not None:
        reported["layout"].update(_counts(layout.get("summary", {})))
    packet = {
        "schema_version": SCHEMA_VERSION,
        "outline_path": str(outline_path), "qa_dir": str(directory),
        "mapping_note": "Source pointers identify slides only; shape IDs are diagnostic references, not source fields. Null pointers require locating the source. This packet is not a QA verdict.",
        "counts": {
            "findings": len(records), "affected_slides": len(affected),
            "unmapped_findings": by_slide.get(None, 0),
            "by_source": dict(sorted(Counter(row[0] for row in records).items())),
            "by_severity": dict(sorted(Counter(str(row[3].get("severity") or "unspecified") for row in records).items())),
        },
        "reported_counts": reported,
        "detail_paths": {name: str(path) for name, path in paths.items()},
        "source_status": statuses, "affected_slides": affected,
        "repairs": list(groups.values()),
        "truncation": {"max_bytes": max_bytes, "budget_exceeded": False},
    }

    def update_truncation() -> None:
        repairs = packet["repairs"]
        emitted = sum(len(item["issues"]) for item in repairs)
        packet["truncation"].update({
            "omitted_findings": len(records) - emitted,
            "omitted_repairs": len(groups) - len(repairs),
            "truncated_excerpts": sum(item["excerpt_truncated"] for item in repairs),
            "truncated_diagnostics": sum(issue["details_truncated"] for item in repairs for issue in item["issues"]),
        })

    update_truncation()
    for repair in reversed(packet["repairs"]):
        if len(_json(packet).encode("utf-8")) + 1 <= max_bytes:
            break
        if repair["source_excerpt"]:
            repair["source_excerpt"] = ""
            repair["excerpt_truncated"] = True
            update_truncation()
    while packet["repairs"] and len(_json(packet).encode("utf-8")) + 1 > max_bytes:
        repair = packet["repairs"][-1]
        repair["issues"].pop()
        if not repair["issues"]:
            packet["repairs"].pop()
        update_truncation()
    packet["truncation"]["budget_exceeded"] = len(_json(packet).encode("utf-8")) + 1 > max_bytes
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outline", required=True, type=Path)
    parser.add_argument("--qa-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        packet = build_repair_packet(args.outline, args.qa_dir)
        output = args.output.expanduser().resolve()
        protected = {packet["outline_path"], *packet["detail_paths"].values()}
        is_image = re.fullmatch(r"slide-\d+\.(?:jpg|jpeg|png)", output.name)
        if str(output) in protected or is_image:
            raise ValueError("output must not overwrite source, QA reports, or slide images")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(_json(packet) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"repair_packet: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
