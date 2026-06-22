#!/usr/bin/env python3
"""Smoke-test random-topic baseline vs large-corpus-guided deck evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from design_catalog_selector import RELEASE_VERSION
from build_random_topic_comparison_decks import build_random_topic_comparison


EXPECTED_TOPIC_COUNT = 8
EXPECTED_CASE_DECK_COUNT = EXPECTED_TOPIC_COUNT * 2
EXPECTED_MIN_CORPUS_FAMILIES = 8
EXPECTED_MIN_DATA_EXAMPLES = 3


def _assert_file(path_value: str | None, *, label: str) -> Path:
    if not path_value:
        raise AssertionError(f"missing {label} path")
    path = Path(path_value)
    if not path.exists():
        raise AssertionError(f"{label} does not exist: {path}")
    if path.stat().st_size <= 0:
        raise AssertionError(f"{label} is empty: {path}")
    return path


def _assert_nonblank_image(path_value: str | None, *, label: str) -> dict[str, Any]:
    path = _assert_file(path_value, label=label)
    image = Image.open(path).convert("L")
    extrema = ImageStat.Stat(image).extrema[0]
    if extrema[1] - extrema[0] <= 10:
        raise AssertionError(f"{label} appears blank: {path}")
    return {"path": str(path), "size": list(image.size), "luma_extrema": list(extrema)}


def _structural_total_is_zero(summary: dict[str, Any], *, label: str) -> None:
    fields = [
        "overflow_count",
        "overlap_count",
        "placeholder_count",
        "geometry_error_count",
        "whitespace_warning_count",
        "design_error_count",
        "design_warning_count",
    ]
    nonzero = {field: summary.get(field) for field in fields if int(summary.get(field) or 0) != 0}
    if nonzero:
        raise AssertionError(f"{label} has nonzero structural QA counts: {nonzero}")


def _verify_manifest(manifest: dict[str, Any], *, max_visual_warnings: int) -> dict[str, Any]:
    cases = manifest.get("cases") if isinstance(manifest.get("cases"), list) else []
    if manifest.get("release_version") != RELEASE_VERSION:
        raise AssertionError(f"expected release version {RELEASE_VERSION}, saw {manifest.get('release_version')}")
    if manifest.get("topic_count") != EXPECTED_TOPIC_COUNT:
        raise AssertionError(f"expected {EXPECTED_TOPIC_COUNT} topics, saw {manifest.get('topic_count')}")
    if manifest.get("deck_count") != EXPECTED_CASE_DECK_COUNT or len(cases) != EXPECTED_CASE_DECK_COUNT:
        raise AssertionError(
            f"expected {EXPECTED_CASE_DECK_COUNT} case decks, saw manifest={manifest.get('deck_count')} cases={len(cases)}"
        )

    leverage = manifest.get("leverage_evidence") if isinstance(manifest.get("leverage_evidence"), dict) else {}
    if leverage.get("corpus_guided_case_count") != EXPECTED_TOPIC_COUNT:
        raise AssertionError(f"expected {EXPECTED_TOPIC_COUNT} corpus-guided cases, saw {leverage.get('corpus_guided_case_count')}")
    if leverage.get("outlines_with_large_corpus_context") != EXPECTED_TOPIC_COUNT:
        raise AssertionError(f"expected {EXPECTED_TOPIC_COUNT} outlines with large-corpus context")
    if leverage.get("descriptor_only") is not True or leverage.get("no_external_source_decks_rendered_or_copied") is not True:
        raise AssertionError("descriptor-only corpus safety flags are not true")

    baseline_contexts = [case for case in cases if case.get("mode") == "baseline" and case.get("outline_large_corpus_context_present")]
    corpus_contexts = [case for case in cases if case.get("mode") == "corpus" and case.get("outline_large_corpus_record_count") == 2000]
    if baseline_contexts:
        raise AssertionError("baseline cases unexpectedly carry outline large-corpus context")
    if len(corpus_contexts) != EXPECTED_TOPIC_COUNT:
        raise AssertionError(f"expected {EXPECTED_TOPIC_COUNT} corpus cases with 2,000-record context, saw {len(corpus_contexts)}")

    for case in cases:
        _assert_file(case.get("pptx"), label=f"{case.get('topic_slug')} {case.get('mode')} pptx")
        _assert_file(case.get("router_prompt"), label=f"{case.get('topic_slug')} {case.get('mode')} router prompt")
        if int(case.get("slide_count") or 0) <= 0:
            raise AssertionError(f"{case.get('topic_slug')} {case.get('mode')} did not record slide_count")
        if not case.get("content_variant_sequence") or not case.get("content_object_sequence"):
            raise AssertionError(f"{case.get('topic_slug')} {case.get('mode')} missing structural sequences")
        if case.get("mode") == "corpus" and not case.get("design_catalog_selection"):
            raise AssertionError(f"{case.get('topic_slug')} corpus case missing design catalog selection")
        if case.get("data_example"):
            artifacts = case.get("generated_data_artifacts") if isinstance(case.get("generated_data_artifacts"), dict) else {}
            for key in ("data_csv", "chart_json", "table_json", "artifact_manifest", "analysis_summary_json"):
                path_value = artifacts.get(key)
                if not path_value:
                    raise AssertionError(f"{case.get('topic_slug')} data example missing artifact key {key}")
                _assert_file(str(Path(case["workspace"]) / path_value), label=f"{case.get('topic_slug')} {key}")
        _structural_total_is_zero(case.get("qa_summary") or {}, label=f"{case.get('topic_slug')} {case.get('mode')}")

    gallery = manifest.get("gallery_deck") if isinstance(manifest.get("gallery_deck"), dict) else {}
    _assert_file(gallery.get("pptx"), label="gallery pptx")
    _structural_total_is_zero(gallery.get("qa_summary") or {}, label="gallery")

    pair_sheets = manifest.get("pair_contact_sheets") if isinstance(manifest.get("pair_contact_sheets"), list) else []
    if len(pair_sheets) != EXPECTED_TOPIC_COUNT:
        raise AssertionError(f"expected {EXPECTED_TOPIC_COUNT} pair contact sheets, saw {len(pair_sheets)}")
    contact_sheets = [_assert_nonblank_image((manifest.get("overview_contact_sheet") or {}).get("path"), label="overview contact sheet")]
    for sheet in pair_sheets:
        contact_sheets.append(_assert_nonblank_image(sheet.get("path"), label=f"{sheet.get('topic_slug')} pair contact sheet"))

    release_notes = _assert_file(manifest.get("release_notes"), label="release notes")
    notes_text = release_notes.read_text(encoding="utf-8")
    for token in (f"v{RELEASE_VERSION}", "2,000-record", "descriptor-only", "Validation snapshot"):
        if token not in notes_text:
            raise AssertionError(f"release notes missing token: {token}")
    for forbidden in ("QA summary", "Structural QA"):
        if forbidden in notes_text:
            raise AssertionError(f"release notes include raw QA wording: {forbidden}")

    quality = manifest.get("release_quality") if isinstance(manifest.get("release_quality"), dict) else {}
    if quality.get("structural_qa_pass") is not True:
        raise AssertionError(f"structural release gate did not pass: {quality.get('structural_qa_totals')}")
    if int(quality.get("visual_warning_total") or 0) > max_visual_warnings:
        raise AssertionError(
            f"visual warning total {quality.get('visual_warning_total')} exceeds threshold {max_visual_warnings}"
        )
    if int(quality.get("readability_warning_total") or 0) != 0:
        raise AssertionError(f"readability warning total is not zero: {quality.get('readability_warning_total')}")
    if int(quality.get("unique_corpus_family_count") or 0) < EXPECTED_MIN_CORPUS_FAMILIES:
        raise AssertionError(f"too few corpus families: {quality.get('unique_corpus_family_count')}")
    if int(quality.get("data_artifact_example_count") or 0) < EXPECTED_MIN_DATA_EXAMPLES:
        raise AssertionError(f"too few generated data examples: {quality.get('data_artifact_example_count')}")
    if quality.get("pair_structural_delta_pass") is not True:
        raise AssertionError("baseline-vs-corpus pair structural delta gate did not pass")
    if quality.get("contact_sheet_nonblank_pass") is not True:
        raise AssertionError("contact-sheet nonblank gate did not pass")

    return {
        "deck_count": len(cases),
        "visual_warning_total": int(quality.get("visual_warning_total") or 0),
        "readability_warning_total": int(quality.get("readability_warning_total") or 0),
        "unique_corpus_family_count": int(quality.get("unique_corpus_family_count") or 0),
        "data_artifact_example_count": int(quality.get("data_artifact_example_count") or 0),
        "pair_structural_delta_count": int(quality.get("pair_structural_delta_count") or 0),
        "contact_sheet_count": len(contact_sheets),
        "gallery_pptx": gallery.get("pptx"),
        "release_notes": str(release_notes),
    }


def run_smoke(outdir: Path, *, max_visual_warnings: int, overwrite: bool) -> dict[str, Any]:
    manifest = build_random_topic_comparison(outdir, overwrite=overwrite)
    result = _verify_manifest(manifest, max_visual_warnings=max_visual_warnings)
    result.update({"passed": True, "outdir": str(outdir), "manifest_path": manifest.get("manifest_path")})
    return result


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", help="Optional persistent output directory. Defaults to a temporary directory.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary output directory.")
    parser.add_argument("--max-visual-warnings", type=int, default=0, help="Maximum allowed visual-review warnings.")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not remove an existing output directory before building.")
    return parser.parse_args()


def main() -> int:
    args = _args()
    if args.outdir:
        outdir = Path(args.outdir).expanduser().resolve()
        result = run_smoke(outdir, max_visual_warnings=args.max_visual_warnings, overwrite=not args.no_overwrite)
        result["temporary"] = False
        print(json.dumps(result, indent=2))
        return 0

    temp_root = Path(tempfile.mkdtemp(prefix="random-topic-comparison-smoke-"))
    try:
        result = run_smoke(temp_root, max_visual_warnings=args.max_visual_warnings, overwrite=True)
        result["temporary"] = True
        result["kept"] = bool(args.keep)
        print(json.dumps(result, indent=2))
    finally:
        if not args.keep:
            shutil.rmtree(temp_root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
