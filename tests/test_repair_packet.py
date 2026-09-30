from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from repair_packet import DEFAULT_MAX_BYTES, build_repair_packet  # noqa: E402


class RepairPacketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.qa = self.root / "qa"
        self.qa.mkdir()
        self.outline = self.root / "outline.json"
        self.write(self.outline, {"slides": [
            {"slide_id": "opening", "title": "A"},
            {"id": "evidence", "title": "B", "chart": {"values": [1, 2]}},
            {"title": "C"},
        ]})

    def write(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def report(self, filename: str, payload: object) -> None:
        self.write(self.qa / filename, payload)

    def build(self, **kwargs: object) -> dict:
        return build_repair_packet(self.outline, self.qa, **kwargs)

    def test_mixed_source_indexes_measurements_and_geometry_deduplication(self) -> None:
        geometry = {"type": "margin_left", "severity": "error", "shape_ids": [9],
                    "delta_inches": 0.24, "suggested_fix": "Shift right within the layout."}
        self.report("layout_lint.json", {"summary": {"violation_count": 1}, "slides": [
            {"slide_index": 0, "violations": [geometry]},
            {"slide_index": 1, "violations": []},
        ]})
        self.report("qa_report.json", {
            "geometry_violations": [{**geometry, "slide_index": 0}],
            "geometry_error_count": 1, "overflow_count": 1,
            "whitespace_warnings": [{**geometry, "slide_index": 0}],
        })
        self.report("design_rules.json", {"issue_count": 1, "issues": [
            {"slide_index": 1, "type": "footer_text_overlap", "shape_ids": ["shape-2"],
             "severity": "error", "delta_inches": 0.17},
        ]})
        self.report("accessibility.json", {"finding_count": 1, "findings": [
            {"slide_number": 3, "code": "text_below_minimum", "severity": "warning",
             "details": {"font_size_pt": 7, "minimum_pt": 12}},
        ]})
        self.report("issues.json", {"slide-02": {"shape-003": {
            "text": "B", "overflow": {"overflow_inches": 0.12},
        }}})
        self.report("visual_qa.json", [{"slide": 1, "type": "crowded", "severity": "warning"}])
        self.report("visual_review/visual_review.json", {"issues": [
            {"slide": 2, "type": "text_wrap", "severity": "warning", "suggestion": "Split the text."},
        ]})
        image = self.qa / "renders" / "slide-002.png"
        image.parent.mkdir()
        image.touch()

        packet = self.build()
        repairs = {item["slide_index"]: item for item in packet["repairs"]}
        self.assertEqual(packet["counts"]["findings"], 6)
        self.assertEqual([item["slide_id"] for item in packet["affected_slides"]],
                         ["opening", "evidence", "slide-03"])
        self.assertEqual([item["source_pointer"] for item in packet["affected_slides"]],
                         ["/slides/0", "/slides/1", "/slides/2"])
        self.assertEqual(packet["reported_counts"]["qa_report"]["geometry_error_count"], 1)
        self.assertEqual(packet["reported_counts"]["layout"]["violation_count"], 1)
        self.assertEqual(repairs[1]["image_path"], str(image))
        self.assertIsNone(repairs[0]["image_path"])
        layout_issue = next(i for i in repairs[0]["issues"] if i["source"] == "layout")
        self.assertEqual(layout_issue["diagnostic"]["delta_inches"], 0.24)
        self.assertEqual(layout_issue["instruction"], geometry["suggested_fix"])
        self.assertEqual(layout_issue["detail_pointer"], "/slides/0/violations/0")
        a11y = repairs[2]["issues"][0]
        self.assertEqual(a11y["diagnostic"]["details"]["minimum_pt"], 12)
        self.assertEqual(json.loads(packet["repairs"][0]["source_excerpt"])["title"], "A")
        self.assertEqual(packet, self.build())
        self.assertEqual(json.loads(json.dumps(packet, allow_nan=False)), packet)
        self.assertLessEqual(len(json.dumps(packet, sort_keys=True, separators=(",", ":"))) + 1, DEFAULT_MAX_BYTES)

    def test_no_findings_means_empty_repairs(self) -> None:
        self.report("qa_report.json", {"geometry_violations": [], "geometry_warning_count": 0,
                                      "manual_review_passed": False, "placeholder_hits": []})
        self.report("layout_lint.json", {"slides": [{"slide_index": 0, "violations": []}]})
        self.report("design_rules.json", {"issues": []})
        self.report("accessibility.json", {"findings": []})
        self.report("issues.json", {"slide-01": {"shape-001": {"text": "Not a finding"}}})
        self.report("visual_qa.json", [])
        packet = self.build()
        self.assertEqual(packet["repairs"], [])
        self.assertEqual(packet["affected_slides"], [])
        self.assertEqual(packet["counts"]["findings"], 0)
        self.assertEqual(packet["truncation"]["omitted_findings"], 0)

    def test_content_issue_resolves_only_its_reported_source_field(self) -> None:
        self.write(self.outline, {"slides": [{"title": "Evidence", "caption": "Maximum CV is not pooled CV."}]})
        self.report("design_rules.json", {"issues": [
            {"slide_index": 0, "type": "source_fidelity_text_missing", "severity": "error",
             "source_pointer": "/slides/0/caption"},
            {"slide_index": 0, "type": "source_fidelity_text_missing", "severity": "error",
             "source_pointer": "/slides/1/caption"},
        ]})
        issues = self.build()["repairs"][0]["issues"]
        self.assertEqual(issues[0]["source_pointer"], "/slides/0/caption")
        self.assertEqual(issues[0]["source_field_excerpt"], '"Maximum CV is not pooled CV."')
        self.assertIsNone(issues[1]["source_pointer"])

    def test_missing_details_preserve_counts_without_fabricated_warnings(self) -> None:
        self.report("qa_report.json", {"design_error_count": 4, "render_rc": 1})
        packet = self.build()
        self.assertEqual(packet["reported_counts"]["qa_report"]["design_error_count"], 4)
        self.assertEqual(packet["source_status"]["design"], "missing")
        self.assertEqual(packet["repairs"], [])

    def test_qa_geometry_fallback_is_zero_based(self) -> None:
        self.report("qa_report.json", {"geometry_violations": [
            {"slide_index": 0, "type": "margin_left", "severity": "error"},
            {"slide_index": 2, "type": "margin_right", "severity": "warning"},
        ]})
        packet = self.build()
        self.assertEqual([r["source_pointer"] for r in packet["repairs"]], ["/slides/0", "/slides/2"])
        self.assertEqual(packet["repairs"][0]["issues"][0]["detail_pointer"], "/geometry_violations/0")

    def test_deck_findings_and_invalid_indexes_remain_unmapped(self) -> None:
        self.report("design_rules.json", {"issues": [
            {"type": "chart_headroom", "chart": "ppt/charts/chart1.xml"},
            *[{"slide_index": index, "type": "bad_location"} for index in (-1, 3, True, "1")],
        ]})
        self.report("accessibility.json", {"findings": [
            {"slide_number": 0, "code": "audit_failed"},
            {"slide_number": None, "code": "audit_failed"},
        ]})
        self.report("qa_report.json", {"placeholder_hits": ["lorem ipsum"]})
        packet = self.build()
        self.assertEqual(packet["counts"]["findings"], 8)
        self.assertEqual(packet["counts"]["unmapped_findings"], 8)
        self.assertEqual(packet["affected_slides"], [])
        self.assertIsNone(packet["repairs"][0]["source_pointer"])
        self.assertIsNone(packet["repairs"][0]["slide_id"])
        self.assertEqual(packet["truncation"]["omitted_findings"], 2)

    def test_disabled_reports_do_not_resurrect_stale_findings(self) -> None:
        self.report("qa_report.json", {"accessibility_enabled": False, "visual_review_report": ""})
        self.report("accessibility.json", {"findings": [{"slide_number": 1, "code": "missing_alt_text"}]})
        self.report("visual_review/visual_review.json", {"issues": [{"slide": 1, "type": "text_wrap"}]})
        packet = self.build()
        self.assertEqual(packet["repairs"], [])
        self.assertEqual(packet["source_status"]["accessibility"], "disabled")

    def test_report_paths_are_resolved_relative_to_qa_directory(self) -> None:
        self.report("qa_report.json", {"design_report": "nested/design.json"})
        self.report("nested/design.json", {"issues": [{"slide_index": 0, "type": "footer_text_overlap"}]})
        packet = self.build()
        self.assertEqual(packet["detail_paths"]["design"], str(self.qa / "nested/design.json"))
        self.assertEqual(packet["counts"]["findings"], 1)

    def test_bounded_packet_preserves_all_counts_and_affected_slides(self) -> None:
        self.write(self.outline, {"slides": [
            {"id": f"s-{i}", "title": "Long title " * 100, "bullets": ["\u03b1" * 4000] * 20}
            for i in range(12)
        ]})
        self.report("design_rules.json", {"issue_count": 240, "error_count": 240, "issues": [
            {"slide_index": i, "severity": "error", "type": "text_readability",
             "details": {"minimum_pt": 16, "text": "\u03b1" * 5000, "measurements": list(range(50))}}
            for i in range(12) for _ in range(20)
        ]})
        packet = self.build()
        encoded = json.dumps(packet, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        self.assertLessEqual(len(encoded.encode("utf-8")), DEFAULT_MAX_BYTES)
        self.assertEqual(packet["counts"]["findings"], 240)
        self.assertEqual(packet["reported_counts"]["design"]["issue_count"], 240)
        self.assertEqual(len(packet["affected_slides"]), 12)
        self.assertEqual(sum(item["finding_count"] for item in packet["affected_slides"]), 240)
        emitted = sum(len(item["issues"]) for item in packet["repairs"])
        self.assertEqual(packet["truncation"]["omitted_findings"], 240 - emitted)
        self.assertGreater(packet["truncation"]["truncated_diagnostics"], 0)
        self.assertFalse(packet["truncation"]["budget_exceeded"])
        self.assertEqual(packet["detail_paths"]["design"], str(self.qa / "design_rules.json"))

    def test_metadata_budget_overrun_is_explicit_not_lossy(self) -> None:
        self.report("design_rules.json", {"issues": [{"slide_index": 0, "type": "overlap"}]})
        packet = self.build(max_bytes=100)
        self.assertTrue(packet["truncation"]["budget_exceeded"])
        self.assertEqual(packet["truncation"]["omitted_findings"], 1)
        self.assertEqual(packet["truncation"]["omitted_repairs"], 1)
        self.assertEqual(packet["affected_slides"][0]["source_pointer"], "/slides/0")

    def test_cli_matches_function_and_protects_inputs(self) -> None:
        output = self.root / "out" / "repair.json"
        command = [sys.executable, str(ROOT / "scripts/repair_packet.py"),
                   "--outline", str(self.outline), "--qa-dir", str(self.qa), "--output"]
        run = subprocess.run([*command, str(output)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(output.read_text()), self.build())
        before = self.outline.read_bytes()
        run = subprocess.run([*command, str(self.outline)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(self.outline.read_bytes(), before)

    def test_invalid_json_and_nonfinite_measurements_fail_explicitly(self) -> None:
        self.report("design_rules.json", {"issues": [{"slide_index": 0, "measurement": float("nan")}]})
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            self.build()
        (self.qa / "design_rules.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
