import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audition_styles
from audition_styles import candidate_outline, representative_indices


class StyleAuditionTests(unittest.TestCase):
    def test_representative_slides_include_densest_data(self):
        slides = [{"role": "title"}, {"role": "evidence"},
                  {"role": "chart", "data": "small"},
                  {"role": "table", "data": "larger payload" * 20}]
        self.assertEqual(representative_indices(slides), [0, 1, 3])
        self.assertEqual(representative_indices(slides[:1]), [0])
        self.assertEqual(representative_indices([]), [])

    def test_candidates_freeze_content_and_preserve_source(self):
        source = {"title": "Frozen", "slides": [{"role": "title", "title": "Exact"},
                   {"role": "chart", "chart": {"values": [2, 7]}}],
                  "deck_style": {"style_seed": "frozen", "palette_key": "old"},
                  "metadata": {"style_preset": "old", "provenance": "retained"}}
        before = copy.deepcopy(source)
        a = candidate_outline(source, "lab-report", [0, 1])
        b = candidate_outline(source, "midnight-neon", [0, 1])
        self.assertEqual(source, before)
        self.assertEqual(a["slides"], b["slides"])
        self.assertNotEqual(a["deck_style"], b["deck_style"])
        self.assertNotIn("palette_key", a["deck_style"])
        self.assertEqual(a["metadata"], {"provenance": "retained"})
        a["slides"][0]["title"] = "Changed"
        self.assertEqual(source, before)

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            candidate_outline({"slides": []}, "invented", [])

    def test_failed_candidate_cannot_reuse_stale_receipt_or_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.json"
            source.write_text(json.dumps({"slides": [{"role": "title", "title": "Current"}]}))
            work = root / "out/lab-report"
            stale = work / "qa/renders/slide-01.jpg"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"stale preview")
            (work / "qa/finalize_receipt.json").write_text(json.dumps({
                "passed": True, "qa_counts": {"overflow_count": 99},
            }))
            argv = ["audition_styles.py", "--outline", str(source), "--outdir", str(root / "out"),
                    "--presets", "lab-report"]
            failed = type("Result", (), {"returncode": 1, "stdout": "failed", "stderr": ""})()
            with patch.object(sys, "argv", argv), \
                    patch.object(audition_styles.subprocess, "run", return_value=failed), \
                    patch.object(audition_styles, "make_sheet") as make_sheet:
                self.assertEqual(audition_styles.main(), 1)
            report = json.loads((root / "out/report.json").read_text())
            self.assertEqual(report["candidates"][0]["qa_counts"], {})
            self.assertFalse(report["candidates"][0]["automated_checks_passed"])
            self.assertIsNone(report["contact_sheet"])
            self.assertFalse(stale.exists())
            make_sheet.assert_not_called()


if __name__ == "__main__":
    unittest.main()
