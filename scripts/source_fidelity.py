"""Cheap source-retention checks, not fact checking or rendered visibility proof.

Only renderer-declared visible fields are mapped. Speaker notes, style metadata,
optional reference headers and chart formatting are deliberately not searched.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import unicodedata


NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}
SCOPE = "Retained mapped source content only; not factual truth or rendered visibility."


def _text(value):
    if isinstance(value, dict):
        return _text(value.get("text", value.get("runs", "")))
    if isinstance(value, list):
        # Rich runs are adjacent, not separate words. Formatting is not content.
        return "".join(_text(item) + (" " if isinstance(item, dict) and
                       item.get("options", {}).get("breakLine") else "") for item in value)
    return "" if value is None else str(value)


def canonical_text(value):
    text = unicodedata.normalize("NFKC", _text(value)).casefold()
    # Table readouts and reference registers reflow newlines with separators.
    text = text.translate(str.maketrans({"\u00b7": " ", "|": " ", "\u2022": " "}))
    return re.sub(r"\s+", " ", text).strip()


def _shapes(shapes):
    for shape in shapes:
        if hasattr(shape, "shapes"):
            yield from _shapes(shape.shapes)
        else:
            yield shape


def _paragraphs(root):
    return [canonical_text("".join(
        " " if child.tag == f"{{{NS['a']}}}br" else (child.text or "")
        for child in paragraph.iter()
        if child.tag in {f"{{{NS['a']}}}t", f"{{{NS['a']}}}br"}
    )) for paragraph in root.findall(".//a:p", NS)]


def _native_content(slide):
    text, charts = [], []
    for shape in _shapes(slide.shapes):
        text.extend(_paragraphs(shape._element))
        if getattr(shape, "has_chart", False):
            chart = shape.chart._chartSpace
            charts.append(chart)
            # Axis titles/labels are visible text; c:v caches are data, not prose.
            text.extend(_paragraphs(chart))
    return " ".join(item for item in text if item), charts


def _first(node, keys):
    return next((key for key in keys if node.get(key)), None)


def _resolve(candidate, pointer, outline_path, *, asset_root=None, path_only=False):
    """Return payload and provenance without replacing the original pointer."""
    if isinstance(candidate, dict):
        return None if path_only else (candidate, str(outline_path), pointer)
    if not isinstance(candidate, str):
        raise ValueError("source payload must be an object or JSON reference")
    root = asset_root if asset_root is not None else outline_path.parent
    if re.match(r"^(asset|image|background|chart|table|generated):", candidate, re.I):
        for manifest in (root / "assets/staged/staged_manifest.json",
                         root / "asset_plan.json"):
            if not manifest.exists():
                continue
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            for section, prefixes in (("images", ("asset", "image")),
                                      ("backgrounds", ("asset", "background")),
                                      ("charts", ("asset", "chart")),
                                      ("tables", ("asset", "table")),
                                      ("generated_images", ("asset", "image", "generated"))):
                for index, entry in enumerate(payload.get(section, [])):
                    name = re.sub(r"[^A-Za-z0-9_-]", "_", str(entry.get("name", ""))).strip("_").lower()
                    if candidate.lower().split(":", 1)[1] != name:
                        continue
                    if candidate.lower().split(":", 1)[0] not in prefixes:
                        continue
                    path_key = _first(entry, ("path", "file_path", "output_path", "image_path"))
                    if not path_key:
                        return None if path_only else (entry, str(manifest), f"/{section}/{index}")
                    candidate = entry[path_key]
                    break
                else:
                    continue
                break
            else:
                continue
            break
        else:
            raise ValueError(f"unresolved source alias: {candidate}")
    path = Path(candidate).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if path_only:
        return path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"source payload must be an object: {path}")
    return payload, str(path), ""


def _effective_variant(spec, resolve, outline_path, base, asset_root=None):
    """Mirror normalizeSlide + resolveVariant routing without rendering assets."""
    slide_type = str(spec.get("type") or "content").strip().lower()
    if slide_type in {"title", "section"}:
        return slide_type
    assets = spec.get("assets") if isinstance(spec.get("assets"), dict) else {}
    variant = str(spec.get("variant") or "standard").strip().lower()

    def existing_asset(candidate):
        try:
            path = _resolve(candidate, "", outline_path, asset_root=asset_root, path_only=True)
            return path is not None and path.exists()
        except (OSError, ValueError, TypeError):
            return False

    def source(container, keys, prefix):
        for key in keys:
            if container.get(key):
                try:
                    return resolve(container[key], prefix + "/" + key)[0]
                except (OSError, ValueError, TypeError):
                    continue
        return {}

    def count(key):
        return len(spec[key]) if isinstance(spec.get(key), list) else 0

    if variant in {"standard", "content", "flow"} and any(
        existing_asset(assets.get(key)) for key in ("diagram", "mermaid_source", "mermaid") if assets.get(key)
    ):
        variant = "flow"
    if slide_type in {"content", "text"} and variant in {"standard", "content"}:
        chart = source(spec, ("chart",), base) or source(assets, ("chart_data", "chart"), base + "/assets")
        facts = spec.get("facts", [])
        if not isinstance(facts, list) or not facts:
            if not any(isinstance(spec.get(key), list) for key in ("facts", "stats")):
                facts = chart.get("facts", chart.get("stats", []))
        table = source(spec, ("table", "table_data"), base) or source(assets, ("table_data", "table"), base + "/assets")
        valid_table = isinstance(table.get("headers"), list) and bool(table["headers"]) and bool(table.get("rows"))
        groups = next((container[key] for container, key in ((spec, "tables"), (spec, "table_groups"), (assets, "tables"))
                       if isinstance(container.get(key), list)), [])
        if count("cards") >= 2:
            variant = "cards-3" if count("cards") >= 3 else "cards-2"
        elif count("milestones") >= 2:
            variant = "timeline"
        elif count("quadrants") >= 4:
            variant = "matrix"
        elif isinstance(facts, list) and len(facts) >= 2:
            variant = "stats"
        elif isinstance(spec.get("headers"), list) or count("rows") or valid_table:
            variant = "table"
        elif groups:
            variant = "lab-run-results"
        elif str(spec.get("visual_intent", "")).strip().lower() == "comparison" and isinstance(spec.get("left"), dict) and isinstance(spec.get("right"), dict):
            variant = "comparison-2col"
        elif str(spec.get("visual_intent", "")).strip().lower() == "data" and chart:
            variant = "chart"
    if slide_type in {"content", "text"} and variant != "generated-image" and (
        variant == "image-sidebar" or str(spec.get("visual_intent", "")).strip().lower() in {"hero", "image", "figure"}
    ) and existing_asset(assets.get("hero_image") or assets.get("image")):
        variant = "image-sidebar"
    if variant in {"content", "standard"}:
        return "standard"
    if variant == "comparison":
        return "comparison-2col"
    return variant if variant in {"cards-2", "cards-3", "split", "timeline", "stats", "kpi-hero", "table",
                                  "lab-run-results", "comparison-2col", "matrix", "flow", "chart", "image-sidebar",
                                  "scientific-figure", "generated-image"} else "standard"


def _number(value):
    # Same supported normalization as the JS chart renderer: commas and %.
    text = str(value).strip().replace(",", "").removesuffix("%")
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("non-finite chart value")
    return number


def _points(series, kind):
    nodes = series.findall(f"./c:{kind}//c:pt", NS)
    return [node.findtext("c:v", default="", namespaces=NS)
            for node in sorted(nodes, key=lambda node: int(node.get("idx", "0")))]


def _chart_uses_v2(outline, spec, known_roles):
    """Only the chart:v2 adapter declares default-visible axis titles.

    Keep this to the persisted version pin and chart role boundary; geometry
    and the general render plan remain owned by the JS renderer.
    """
    style = outline.get("deck_style") if isinstance(outline.get("deck_style"), dict) else {}
    metadata = outline.get("metadata") if isinstance(outline.get("metadata"), dict) else {}
    v2 = style.get("renderer_role_contracts_v2")
    if not isinstance(v2, dict):
        v2 = metadata.get("renderer_role_contracts_v2")
    v1 = style.get("renderer_role_systems_v1")
    if not isinstance(v1, dict):
        v1 = metadata.get("renderer_role_systems_v1")
    if not isinstance(v2, dict) and isinstance(v1, dict) and v1:
        return False
    role = str(spec.get("role", "")).strip().lower()
    if role in known_roles and role not in {"chart", "graph", "plot", "data"}:
        return False
    if isinstance(v2, dict):
        chart = v2.get("roles", {}).get("chart", {})
        return bool(chart.get("slots", {}).get("chart"))
    # applyDeckStyle auto-resolves v2 when no persisted v1 pin exists.
    return True


def check_source_fidelity(prs, outline_path, asset_root=None):
    """Return issues compatible with design QA and its bounded repair packet."""
    if outline_path is None:
        return {"enabled": False, "scope": SCOPE, "checked_count": 0,
                "error_count": 0, "warning_count": 0, "issues": []}
    outline_path = Path(outline_path).expanduser().resolve()
    issues, checked, references = [], 0, []

    def issue(index, pointer, role, expected, actual, *, kind="text_missing",
              file=None, data_pointer=None, severity="error"):
        if file and file != str(outline_path):
            pointer = next((original for original, resolved in references
                            if resolved == file and (pointer == original or pointer.startswith(original + "/"))), pointer)
        issues.append({
            "type": f"source_fidelity_{kind}", "severity": severity,
            "slide_index": index, "source_pointer": pointer,
            "source_file": str(outline_path), "field_role": role,
            "source_data_file": file or str(outline_path),
            "source_data_pointer": data_pointer if data_pointer is not None else pointer,
            "expected_canonical": expected, "actual_canonical": actual,
            "suggested_fix": "Restore the declared visible source field or repair its renderer; rebuild and rerun QA. This checks retention, not factual truth.",
        })

    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
        if not isinstance(outline, dict) or not isinstance(outline.get("slides"), list):
            raise ValueError("outline must contain a slides array")
        resolved_outline = outline
        root = Path(asset_root).expanduser().resolve() if asset_root is not None else None
        # build_workspace writes this documented intermediate beside its build
        # outputs; renderer asset-root and repair pointers still use the source.
        manifest_path = outline_path.parent.parent / "workspace.json"
        if outline_path.name == "outline_resolved.json" and manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_path = (manifest_path.parent / manifest.get("outline", "outline.json")).resolve()
            source = json.loads(source_path.read_text(encoding="utf-8"))
            if not isinstance(source, dict) or not isinstance(source.get("slides"), list):
                raise ValueError("workspace source outline must contain a slides array")
            if len(source["slides"]) != len(resolved_outline["slides"]):
                raise ValueError("source and resolved outlines have different slide counts")
            outline_path, outline = source_path, source
        if root is None:
            root = outline_path.parent
    except (OSError, ValueError) as exc:
        issue(None, "", "outline", "readable source outline", str(exc), kind="audit_failed")
        return {"enabled": True, "scope": SCOPE, "checked_count": 0,
                "error_count": 1, "warning_count": 0, "issues": issues}

    for index, spec in enumerate(outline["slides"]):
        base = f"/slides/{index}"
        if not isinstance(spec, dict):
            issue(index, base, "slide", "source slide object", spec, kind="audit_failed")
            continue
        source_cache = {}

        def resolve(candidate, pointer):
            if isinstance(candidate, dict):
                return _resolve(candidate, pointer, outline_path, asset_root=root)
            if pointer not in source_cache:
                source_cache[pointer] = _resolve(candidate, pointer, outline_path, asset_root=root)
                if source_cache[pointer][1] != str(outline_path):
                    references.append((pointer, source_cache[pointer][1]))
            return source_cache[pointer]

        rendered, charts = _native_content(prs.slides[index]) if index < len(prs.slides) else ("", [])
        effective_spec = resolved_outline["slides"][index]
        variant = _effective_variant(effective_spec, resolve, outline_path, base, root)
        role = str(spec.get("role", "")).strip().lower()
        reference_aliases = {"references", "reference", "source", "sources", "citation", "citations"}
        known_roles = reference_aliases | {"title", "section", "evidence", "comparison", "chart", "table", "decision", "data",
                                          "cover", "opener", "chapter", "divider", "message", "content", "figure", "image",
                                          "stats", "metric", "metrics", "process", "flow", "dashboard", "compare", "options",
                                          "graph", "plot", "ledger", "register", "recommendation", "recommend", "action", "actions", "conclusion"}
        reference_role = role in reference_aliases
        if role not in known_roles and variant in {"standard", "table", "matrix"}:
            intent = str(spec.get("slide_intent", "")).strip().lower()
            treatment = str(spec.get("treatment_key", "")).strip().lower()
            reference_role = intent in reference_aliases or treatment in reference_aliases

        def text(value, pointer, field_role, file=None, data_pointer=None):
            nonlocal checked
            expected = canonical_text(value)
            if not expected:
                return
            checked += 1
            # Word boundaries avoid treating 2 mg as retained inside 12 mg.
            left = r"(?<![\w.,+-])" if expected[0].isdigit() else r"(?<!\w)"
            right = r"(?![\w.,]\d|\w)" if expected[-1].isdigit() else r"(?!\w)"
            if not re.search(left + re.escape(expected) + right, rendered):
                issue(index, pointer, field_role, expected, rendered,
                      file=file, data_pointer=data_pointer)

        def fields(node, pointer, keys, field_role, file=None, data_base=None):
            for key in keys:
                if key in node:
                    text(node[key], f"{pointer}/{key}", field_role, file,
                         f"{data_base}/{key}" if data_base is not None else None)

        # Not a recursive exact-string crawl: slots have explicit role mappings.
        fields(spec, base, ("title", "subtitle"), "heading")
        is_chart = variant == "chart"
        is_table = variant in {"table", "lab-run-results"} or (variant == "standard" and reference_role)
        is_figure = variant in {"scientific-figure", "image-sidebar"}
        if variant == "standard" and not reference_role:
            bullets = spec.get("bullets", [])
            if isinstance(bullets, list) and bullets:
                fields(spec, base, ("body",), "body")
                for offset, bullet in enumerate(bullets):
                    text(bullet, f"{base}/bullets/{offset}", "body")
            elif isinstance(spec.get("paragraphs"), list) and spec["paragraphs"]:
                for offset, paragraph in enumerate(spec["paragraphs"]):
                    text(paragraph, f"{base}/paragraphs/{offset}", "body")
            else:
                fields(spec, base, ("body",), "body")
            key = _first(spec, ("summary_callout", "key_summary", "takeaway"))
            if key:
                fields(spec, base, (key,), "caveat_readout")
        if is_figure:
            key = _first(spec, ("caption", "figure_caption"))
            if key:
                fields(spec, base, (key,), "caption")
            key = _first(spec, ("interpretation", "takeaway"))
            if key:
                fields(spec, base, (key,), "caveat_readout")
            figures = spec.get("figures", spec.get("assets", {}).get("figures", []))
            figure_base = base + ("/figures" if "figures" in spec else "/assets/figures")
            # Sidebar renderers consume the slide caption, not a figure array.
            # Scientific strip-readout captions its primary panel only; its
            # secondary images are bare thumbnails, unlike captioned panels.
            style = resolved_outline.get("deck_style")
            style = style if isinstance(style, dict) else {}
            layout = str(effective_spec.get("figure_layout") or effective_spec.get("scientific_figure_layout")
                         or effective_spec.get("figure_treatment") or style.get("figure_layout")
                         or effective_spec.get("figure_table_treatment") or style.get("figure_table_treatment")
                         or "").strip().lower()
            if variant == "image-sidebar":
                figures = []
            elif layout in {"strip-readout", "strip_readout", "stats-strip", "metric-strip"}:
                figures = figures[:1]
            for offset, figure in enumerate(figures):
                if isinstance(figure, dict):
                    key = _first(figure, ("caption", "note"))
                    if key:
                        fields(figure, f"{figure_base}/{offset}", (key,), "figure_caption")
        if variant == "timeline":
            fields(spec, base, ("caption",), "caption")

        # Stats/detail is a visible evidence slot, not optional speaker notes.
        if variant in {"stats", "chart", "scientific-figure", "kpi-hero"}:
            fact_key = next((key for key in ("facts", "stats") if isinstance(spec.get(key), list)), None)
            if fact_key:
                for offset, fact in enumerate(spec[fact_key]):
                    if isinstance(fact, dict):
                        key = _first(fact, ("detail", "caption", "body", "text"))
                        if key:
                            fields(fact, f"{base}/{fact_key}/{offset}", (key,), "fact_caveat")
                    elif isinstance(fact, str):
                        text(fact, f"{base}/{fact_key}/{offset}", "fact_label")

        def payload(candidate, pointer):
            try:
                return resolve(candidate, pointer)
            except (OSError, ValueError, TypeError) as exc:
                issue(index, pointer, "source_payload", "resolvable JSON source", str(exc), kind="audit_failed")
                return {}, str(outline_path), pointer

        if is_table:
            group_key = _first(spec, ("tables", "table_groups"))
            if group_key:
                tables = [(item, f"{base}/{group_key}/{offset}")
                          for offset, item in enumerate(spec[group_key])]
            elif isinstance(spec.get("assets", {}).get("tables"), list):
                tables = [(item, f"{base}/assets/tables/{offset}")
                          for offset, item in enumerate(spec["assets"]["tables"])]
            else:
                tables = [(spec, base)]
                for container, prefix, keys in ((spec, base, ("table", "table_data")),
                                                (spec.get("assets", {}), base + "/assets", ("table_data", "table"))):
                    key = _first(container, keys)
                    if key:
                        tables = [(container[key], f"{prefix}/{key}")]
                        break
            for candidate, pointer in tables:
                table, file, data_base = payload(candidate, pointer)
                compaction = spec.get("source_footer_compaction") or {}
                reference_table = reference_role or spec.get("table_style", table.get("table_style")) == "references" or (isinstance(compaction, dict) and compaction.get("generated_by") == "scripts/compact_source_footers.py")
                # This adapter declares its source-note panel from table rows,
                # not the optional footnote/register-label metadata. The native
                # marker identifies the executed route without redoing routing.
                policy_register = reference_table and index < len(prs.slides) and any(
                    shape.name == "metadata:policy-accountability-register"
                    for shape in _shapes(prs.slides[index].shapes)
                )
                for key in ("caption", "footnotes", "headers", "rows"):
                    # A references register intentionally omits column headings.
                    # Its reformatted rows are outside this critical-field check.
                    if reference_table and key in {"headers", "rows"}:
                        continue
                    if policy_register and key == "footnotes":
                        continue
                    value, ptr, data_ptr = table.get(key), pointer + "/" + key, data_base + "/" + key
                    selected_file = file
                    if len(tables) == 1 and candidate is not spec and key in spec:
                        value, ptr, selected_file, data_ptr = spec[key], base + "/" + key, str(outline_path), base + "/" + key
                    # Preserve individual cell/footnote pointers, rich runs intact.
                    if key == "footnotes" and isinstance(value, list):
                        for offset, note in enumerate(value):
                            text(note, f"{ptr}/{offset}", "caveat", selected_file, f"{data_ptr}/{offset}")
                    elif key in {"headers", "rows"} and isinstance(value, list):
                        for row, item in enumerate(value):
                            cells = item if key == "rows" and isinstance(item, list) else [item]
                            for col, cell in enumerate(cells):
                                suffix = f"/{row}/{col}" if key == "rows" else f"/{row}"
                                text(cell, ptr + suffix, "table_cell", selected_file, data_ptr + suffix)
                    else:
                        text(value, ptr, "caption", selected_file, data_ptr)

        if is_chart:
            chart, pointer, file, data_base = {}, base + "/chart", str(outline_path), base + "/chart"
            for container, prefix, keys in ((spec, base, ("chart",)),
                                            (spec.get("assets", {}), base + "/assets", ("chart_data", "chart"))):
                key = _first(container, keys)
                if key:
                    pointer = f"{prefix}/{key}"
                    chart, file, data_base = payload(container[key], pointer)
                    break
            for key in ("title", "subtitle"):
                if not spec.get(key):
                    fields(chart, pointer, (key,), "heading", file, data_base)
            # Slide notes are speaker notes; chart notes are a visible readout
            # only if not replaced by an explicit slide readout.
            key = _first(spec, ("interpretation", "message", "caption"))
            if key:
                fields(spec, base, (key,), "caveat_readout")
            else:
                key = _first(chart, ("notes", "message", "caption"))
                if key:
                    fields(chart, pointer, (key,), "caveat_readout", file, data_base)
            options = chart.get("options") if isinstance(chart.get("options"), dict) else {}
            if _chart_uses_v2(resolved_outline, effective_spec, known_roles) and str(chart.get("type", "")).strip().lower() not in {"pie", "doughnut"}:
                for key, flag in (("catAxisTitle", "showCatAxisTitle"), ("valAxisTitle", "showValAxisTitle")):
                    if options.get(flag) is None or bool(options[flag]):
                        fields(options, pointer + "/options", (key,), "axis_unit", file, data_base + "/options")
            fact_key = next((key for key in ("facts", "stats") if isinstance(chart.get(key), list)), None)
            if not any(isinstance(spec.get(key), list) for key in ("facts", "stats")) and fact_key:
                for offset, fact in enumerate(chart[fact_key]):
                    if isinstance(fact, dict):
                        key = _first(fact, ("detail", "caption", "body", "text"))
                        if key:
                            fields(fact, f"{pointer}/{fact_key}/{offset}", (key,), "fact_caveat",
                                   file, f"{data_base}/{fact_key}/{offset}")
                    elif isinstance(fact, str):
                        text(fact, f"{pointer}/{fact_key}/{offset}", "fact_label",
                             file, f"{data_base}/{fact_key}/{offset}")
            series = chart.get("series")
            flat = not isinstance(series, list) or not series
            series = [{"values": chart.get("values", [])}] if flat else series
            actual = charts[0].findall(".//c:ser", NS) if charts else []
            checked += 1
            if not charts or len(actual) != len(series):
                issue(index, pointer, "native_chart", len(series), len(actual), kind="chart_series_mismatch",
                      file=file, data_pointer=data_base + ("/values" if flat else "/series"))
            for offset, source_series in enumerate(series):
                series_pointer = pointer if flat else f"{pointer}/series/{offset}"
                series_data = data_base if flat else f"{data_base}/series/{offset}"
                labels_key = _first(source_series, ("labels",))
                category_key = _first(chart, ("categories", "labels"))
                labels = source_series.get(labels_key) if labels_key else chart.get(category_key, [])
                for kind, values, ptr, data_ptr in (
                    ("values", source_series.get("values", []), series_pointer + "/values", series_data + "/values"),
                    ("categories", labels, series_pointer + "/labels" if labels_key else pointer + "/" + (category_key or "categories"),
                     series_data + "/labels" if labels_key else data_base + "/" + (category_key or "categories")),
                ):
                    checked += 1
                    node = actual[offset] if offset < len(actual) else None
                    try:
                        normalize = _number if kind == "values" else canonical_text
                        expected = [normalize(value) for value in values]
                        observed = [normalize(value) for value in _points(node, "val" if kind == "values" else "cat")] if node is not None else []
                        matches = len(expected) == len(observed) and all(
                            math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12) if kind == "values" else a == b
                            for a, b in zip(expected, observed))
                    except (ValueError, TypeError) as exc:
                        issue(index, ptr, "chart_" + kind, values, str(exc), kind="audit_failed", file=file, data_pointer=data_ptr)
                        continue
                    if not matches:
                        issue(index, ptr, "chart_" + kind, expected, observed,
                              kind="chart_" + kind + "_mismatch", file=file, data_pointer=data_ptr)

    return {"enabled": True, "scope": SCOPE, "checked_count": checked,
            "error_count": sum(item["severity"] == "error" for item in issues),
            "warning_count": sum(item["severity"] == "warning" for item in issues),
            "issues": issues}
