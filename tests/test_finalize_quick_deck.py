from __future__ import annotations

import subprocess
import json
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.finalize_quick_deck import (
    _clear_owned_qa_evidence,
    _completion_status,
    _restore_previous_output_if_equivalent,
    _run,
    _thresholds,
    main,
)


def office_bytes(payload: str, timestamp: str) -> bytes:
    buffer = io.BytesIO()
    core = (
        '<cp:coreProperties xmlns:cp="x" xmlns:dcterms="y">'
        f'<dcterms:created>{timestamp}</dcterms:created>'
        f'<dcterms:modified>{timestamp}</dcterms:modified>'
        '</cp:coreProperties>'
    )
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("docProps/core.xml", core)
        package.writestr("ppt/slides/slide1.xml", payload)
    return buffer.getvalue()


class FinalizeQuickDeckTests(unittest.TestCase):
    def test_warning_only_preflight_is_accepted(self) -> None:
        records: list[dict[str, object]] = []
        completed = subprocess.CompletedProcess(["preflight"], 1, stdout="warning\n")
        with patch("scripts.finalize_quick_deck.subprocess.run", return_value=completed):
            accepted = _run(
                "preflight",
                ["preflight"],
                records,
                accepted_returncodes=(0, 1),
            )
        self.assertTrue(accepted)
        self.assertTrue(records[0]["accepted"])
        self.assertGreaterEqual(float(records[0]["duration_seconds"]), 0.0)
        with tempfile.TemporaryDirectory() as tmp:
            status = _completion_status(records, Path(tmp))
        self.assertEqual(status["failure_category"], "passed")

    def test_preflight_error_remains_blocking(self) -> None:
        records: list[dict[str, object]] = []
        completed = subprocess.CompletedProcess(["preflight"], 2, stdout="error\n")
        with patch("scripts.finalize_quick_deck.subprocess.run", return_value=completed):
            accepted = _run(
                "preflight",
                ["preflight"],
                records,
                accepted_returncodes=(0, 1),
            )
        self.assertFalse(accepted)
        with tempfile.TemporaryDirectory() as tmp:
            status = _completion_status(records, Path(tmp))
        self.assertEqual(status["failure_category"], "outline_preflight")

    def test_quick_defaults_preserve_readability(self) -> None:
        self.assertEqual(_thresholds({}, None, None, None), (16.0, 13.0, 9.0))

    def test_preflight_failure_does_not_reuse_previous_qa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "qa_report.json").write_text(json.dumps({"overflow_count": 99, "render_rc": 0}))
            status = _completion_status([{"stage": "preflight", "accepted": False}], path)
        self.assertEqual(status["qa_counts"]["overflow_count"], 0)
        self.assertEqual(status["render_status"], "not_completed")
        self.assertEqual(status["visual_inspection_status"], "not_recorded")

    def test_missing_source_content_defers_render_as_a_content_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "qa_report.json").write_text(json.dumps({
                "source_fidelity_error_count": 1,
                "render_status": "deferred_source_fidelity", "render_rc": 0,
            }))
            status = _completion_status([{"stage": "qa", "accepted": False}], path)
        self.assertEqual(status["qa_counts"]["source_fidelity_error_count"], 1)
        self.assertEqual(status["failure_category"], "qa_findings")
        self.assertEqual(status["render_status"], "deferred_source_fidelity")

    def test_qa_cleanup_removes_only_owned_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            qa = Path(tmp)
            for path in (
                qa / "qa_report.json", qa / "repair_packet.json",
                qa / "renders/slide-01.jpg", qa / "renders/render_report.json",
                qa / "visual_review/contact_sheet.jpg",
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("generated")
            unrelated = qa / "user-notes.txt"
            nested = qa / "renders/keep-me.bin"
            cache = qa / ".render-cache/verified/manifest.json"
            cache.parent.mkdir(parents=True)
            cache.write_text("keep")
            unrelated.write_text("keep")
            nested.write_text("keep")
            _clear_owned_qa_evidence(qa)
            self.assertEqual(unrelated.read_text(), "keep")
            self.assertEqual(nested.read_text(), "keep")
            self.assertEqual(cache.read_text(), "keep")
            self.assertFalse((qa / "qa_report.json").exists())
            self.assertFalse((qa / "renders/slide-01.jpg").exists())

    def test_equivalent_package_restores_previous_raw_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = root / "previous.pptx"
            output = root / "deck.pptx"
            previous.write_bytes(office_bytes("same", "2026-01-01T00:00:00Z"))
            output.write_bytes(office_bytes("same", "2026-02-01T00:00:00Z"))
            self.assertNotEqual(previous.read_bytes(), output.read_bytes())
            self.assertTrue(_restore_previous_output_if_equivalent(previous, output))
            self.assertEqual(output.read_bytes(), previous.read_bytes())

    def test_payload_change_keeps_new_output_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = root / "previous.pptx"
            output = root / "deck.pptx"
            previous.write_bytes(office_bytes("old", "2026-01-01T00:00:00Z"))
            fresh = office_bytes("new", "2026-02-01T00:00:00Z")
            output.write_bytes(fresh)
            self.assertFalse(_restore_previous_output_if_equivalent(previous, output))
            self.assertEqual(output.read_bytes(), fresh)

    def test_render_reuse_defaults_to_local_cache_with_cold_render_option(self) -> None:
        for flags, custom in (([], False), (["--no-render-cache"], False), (["--render-cache-dir"], True)):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                outline = root / "outline.json"
                output = root / "deck.pptx"
                qa = root / "qa"
                outline.write_text(json.dumps({"slides": [{"type": "title", "title": "Deck"}]}))
                commands = {}

                def fake_run(stage, command, records, *, accepted_returncodes=(0,)):
                    commands[stage] = command
                    if stage == "build":
                        output.write_bytes(office_bytes("same", "2026-01-01T00:00:00Z"))
                    records.append({"stage": stage, "accepted": True, "duration_seconds": 0})
                    return True

                option_flags = flags + ([str(root / "custom-cache")] if custom else [])
                argv = ["finalize_quick_deck.py", "--outline", str(outline), "--output", str(output),
                        "--qa-dir", str(qa), *option_flags]
                with patch.object(sys, "argv", argv), \
                        patch("scripts.finalize_quick_deck.shutil.which", return_value="node"), \
                        patch("scripts.finalize_quick_deck._run", side_effect=fake_run), \
                        patch("sys.stdout", new=io.StringIO()):
                    self.assertEqual(main(), 0)
                command = commands["qa"]
                if "--no-render-cache" in flags:
                    self.assertNotIn("--render-cache-dir", command)
                else:
                    cache = root / "custom-cache" if custom else qa / ".render-cache"
                    self.assertEqual(command[command.index("--render-cache-dir") + 1], str(cache.resolve()))

    def test_failed_build_does_not_restore_previous_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outline = root / "outline.json"
            output = root / "deck.pptx"
            qa = root / "qa"
            outline.write_text(json.dumps({"slides": [{"role": "title", "title": "Deck"}]}))
            old = office_bytes("old", "2026-01-01T00:00:00Z")
            output.write_bytes(old)
            partial = b"current failed build bytes"

            def fake_run(stage, command, records, *, accepted_returncodes=(0,)):
                accepted = stage == "preflight"
                if stage == "build":
                    output.write_bytes(partial)
                records.append({"stage": stage, "accepted": accepted, "duration_seconds": 0})
                return accepted

            argv = ["finalize_quick_deck.py", "--outline", str(outline), "--output", str(output),
                    "--qa-dir", str(qa), "--render-cache-dir", str(root / "cache")]
            with patch.object(sys, "argv", argv), \
                    patch("scripts.finalize_quick_deck.shutil.which", return_value="node"), \
                    patch("scripts.finalize_quick_deck._run", side_effect=fake_run), \
                    patch("scripts.finalize_quick_deck._restore_previous_output_if_equivalent") as restore:
                self.assertEqual(main(), 1)
            restore.assert_not_called()
            self.assertEqual(output.read_bytes(), partial)


if __name__ == "__main__":
    unittest.main()
