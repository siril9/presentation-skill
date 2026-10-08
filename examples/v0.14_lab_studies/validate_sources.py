#!/usr/bin/env python3
"""Validate source/payload contracts and synthetic denominators, never PPTX QA."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from preflight import lint_outline
from taste_grammar_catalog import PRESET_TO_GRAMMAR


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def assert_close(actual, expected, tolerance=2e-7):
    assert math.isclose(actual, expected, abs_tol=tolerance), (actual, expected)


def validate_data(folder: str, chart: dict):
    data = read(ROOT / folder / "data/synthetic_data.json")
    assert data["synthetic"] is True
    if folder == "white_calibration":
        inputs = data["holdout_input"]
        assert len(data["training_input"]) == 24 and len(inputs) == 30
        assert not set(data["training_input"]) & set(inputs)
        scores = []
        for candidate in data["candidates"].values():
            assert candidate["n"] == len(candidate["residual"]) == len(inputs)
            for estimate, truth, residual in zip(candidate["prediction"], inputs, candidate["residual"]):
                assert_close(estimate - truth, residual)
            assert_close(candidate["rmse"], math.sqrt(sum(x*x for x in candidate["residual"]) / 30))
            assert_close(candidate["max_absolute"], max(abs(x) for x in candidate["residual"]))
            scores.append(round(candidate["rmse"], 3))
        assert chart["series"][0]["values"] == scores
        assert data["candidates"]["Quadratic"]["passes_toy_screen"] is True
        assert scores[2] < scores[1] < scores[0]
        for setting in data["noise_sweep"]:
            assert all(candidate["n"] == 30 for candidate in setting["candidates"].values())
    elif folder == "dark_contrast":
        raw_scores, corrected_scores = [], []
        for name, condition in data["conditions"].items():
            assert len(condition["raw"]) == len(condition["oracle_corrected"]) == 12
            for raw, corrected in zip(condition["raw"], condition["oracle_corrected"]):
                assert len(raw) == len(corrected) == 11
                for time, value, after in zip(data["time"], raw, corrected):
                    assert_close(value - data["design"][f"{name}_drift_per_step"] * time, after)
            for field, traces in (("raw", condition["raw"]), ("corrected", condition["oracle_corrected"])):
                changes = [abs(trace[-1] - trace[0]) for trace in traces]
                mean = sum(changes) / 12
                assert_close(mean, condition[f"mean_endpoint_change_{field}"])
                for actual, expected in zip(condition[f"absolute_endpoint_change_{field}"], changes):
                    assert_close(actual, expected)
                (raw_scores if field == "raw" else corrected_scores).append(round(mean, 4))
        assert chart["series"][0]["values"] == raw_scores
        assert chart["series"][1]["values"] == corrected_scores
    else:
        assert len(data["dense_traces"]) == 24 and len(data["time"]) == 289
        scores = []
        for schedule in data["schedules"].values():
            assert schedule["samples_per_realization"] == len(schedule["times"]) == 6
            assert len(schedule["values"]) == len(schedule["peak_fraction"]) == 24
            for index, (sampled, fraction) in enumerate(zip(schedule["values"], schedule["peak_fraction"])):
                trace = data["dense_traces"][index]
                assert len(trace) == 289 and len(sampled) == 6
                assert all(value == trace[data["time"].index(time)]
                           for time, value in zip(schedule["times"], sampled))
                denominator = max(trace) - data["design"]["baseline"]
                assert_close(denominator, data["dense_peak_above_baseline"][index])
                assert_close((max(sampled) - data["design"]["baseline"]) / denominator, fraction)
                assert 0 <= fraction <= 1
            mean = sum(schedule["peak_fraction"]) / 24
            assert_close(mean, schedule["mean_peak_fraction"])
            scores.append(round(mean, 4))
        assert chart["series"][0]["values"] == scores
        assert scores[1] > scores[0]


def main() -> int:
    capabilities = read(REPO / "schemas/renderer_capabilities_v2.json")
    studies = []
    layouts, frames, flows, step_counts = set(), set(), set(), set()
    for folder in ("white_calibration", "dark_contrast", "light_river_report"):
        path = ROOT / folder / "outline.json"
        outline = read(path)
        assert outline["metadata"]["synthetic"] is True
        style = outline["deck_style"]
        assert PRESET_TO_GRAMMAR[style["style_preset"]] == style["composition_grammar"]
        for key, floor in (("min_title_pt", 28), ("min_body_pt", 16), ("min_support_pt", 13),
                           ("min_caption_pt", 9), ("min_footer_pt", 9), ("min_metadata_pt", 9)):
            assert style["readability_contract"][key] >= floor
        slides = outline["slides"]
        assert 7 <= len(slides) <= 8
        assert len({slide["slide_id"] for slide in slides}) == len(slides)
        routes = []
        chart = None
        for slide in slides:
            role, variant = slide["role"], slide["variant"]
            v2 = variant in capabilities["role_variants"].get(role, [])
            fallback = variant in capabilities["fallback_role_variants"].get(role, [])
            assert v2 or fallback, (folder, role, variant)
            routes.append({"slide_id": slide["slide_id"], "role": role, "variant": variant,
                           "route": "v2-capable pair; render execution unverified" if v2 else "legacy fallback"})
            assert slide["sources"] and all("synthetic" in source.lower() or "invented" in source.lower()
                                            or "illustrative" in source.lower() for source in slide["sources"])
            if variant == "scientific-figure":
                assert 1 <= len(slide["figures"]) <= 4
                layouts.add(slide["figure_layout"])
                frames.add(slide["figure_frame"])
                for figure in slide["figures"]:
                    assert figure["caption"] and (path.parent / figure["path"]).is_file()
            elif variant == "image-sidebar":
                assert 2 <= len(slide["sidebar_sections"]) <= 4
                assert slide["sidebar_body_font_size"] >= 16
                assert (path.parent / slide["assets"]["hero_image"]).is_file()
            elif variant == "flow":
                assert 2 <= len(slide["flow_steps"]) <= 4
                assert all(step["title"].strip() and isinstance(step["detail"], str) and step["detail"].strip()
                           for step in slide["flow_steps"])
                assert not slide.get("assets")
                flows.add(slide["flow_layout"])
                step_counts.add(len(slide["flow_steps"]))
            elif variant == "table":
                table = slide["table"]
                assert all(len(row) == len(table["headers"]) for row in table["rows"])
                assert len(table["headers"]) == len(table["column_weights"])
            elif variant == "chart":
                chart = read(path.parent / slide["chart"])
                assert chart["synthetic"] is True
                assert chart["options"]["valAxisMinVal"] == 0
                for series in chart["series"]:
                    assert len(series["values"]) == len(chart["categories"])
                    assert all(isinstance(value, (int, float)) and math.isfinite(value) for value in series["values"])
        assert chart is not None
        validate_data(folder, chart)
        issues = lint_outline(outline, path.parent, {"readability_contract": style["readability_contract"]})
        blocking = [issue for issue in issues if issue["severity"] in ("error", "warning")]
        assert not blocking, json.dumps({"study": folder, "issues": blocking}, indent=2)
        studies.append({"path": f"{folder}/outline.json", "slides": len(slides),
                        "source_preflight_errors": 0, "source_preflight_warnings": 0,
                        "information": issues, "routes": routes, "data_integrity": "pass"})
    assert layouts == {"panel-grid", "primary-rail", "ledger-rail", "strip-readout"}
    assert frames == {"open", "ruled", "panel"}
    assert flows == {"auto", "strip", "bands"} and step_counts == {2, 3, 4}
    for path in ROOT.rglob("*.json"):
        source = path.read_text(encoding="utf-8")
        read(path)
        assert not re.search(r"https?://|file://|/Users/|/home/|[A-Za-z]:\\\\", source), path.name
    manifest = read(ROOT / "generation_manifest.json")
    for artifact in manifest["artifacts"]:
        assert hashlib.sha256((ROOT / artifact["path"]).read_bytes()).hexdigest() == artifact["sha256"]
    report = {
        "schema_version": "synthetic_source_validation/v1", "source_validation": "pass",
        "command": "python3 scripts/python_runtime.py examples/v0.14_lab_studies/validate_sources.py",
        "core_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "core_state": "Concurrent core work may be dirty; this is a source-only snapshot, not release proof.",
        "core_contract_sha256": {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in (
            "scripts/preflight.py", "schemas/renderer_capabilities_v2.json", "scripts/taste_grammar_catalog.py")},
        "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(ROOT.rglob("outline.json"))},
        "generation_manifest_sha256": hashlib.sha256((ROOT / "generation_manifest.json").read_bytes()).hexdigest(),
        "studies": studies, "figure_layouts": sorted(layouts), "figure_frames": sorted(frames),
        "flow_layouts": sorted(flows), "native_flow_stage_counts": sorted(step_counts),
        "build": "not run", "render": "not run", "visual_review": "not performed",
        "readability_status": "Requested source floors checked; native geometry and embedded label sizes await rendering.",
        "public_proof_status": "Authored candidates only; no final deck acceptance or benchmark claim.",
    }
    (ROOT / "source_validation.json").write_bytes((json.dumps(report, indent=2) + "\n").encode("utf-8"))
    print("PASS: 3 outlines, 24 slides, native/fallback payloads and synthetic data. No decks built or rendered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
