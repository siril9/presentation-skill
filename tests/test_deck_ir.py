from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from deck_ir import (  # noqa: E402
    IR_VERSION,
    SCHEMA_PATH,
    DeckIRMigrationError,
    DeckIRValidationError,
    canonical_json_bytes,
    canonicalize_deck_ir,
    deck_ir_from_outline,
    deck_ir_sha256,
    migrate_deck_ir,
    register_migration,
    registered_migrations,
    stable_id,
    unregister_migration,
    validate_deck_ir,
)


class DeckIRTests(unittest.TestCase):
    def test_native_method_keeps_order_detail_and_stable_semantic_identity(self) -> None:
        outline = {"slides": [{"title": "Prepare the data", "variant": "flow", "flow_steps": [
            {"title": "Collect", "detail": "Retain raw observations."},
            {"title": "Review", "detail": "Log every exclusion."},
        ]}]}
        ir = deck_ir_from_outline(outline)
        method = next(element for element in ir["slides"][0]["elements"] if element["editable_object_kind"] == "diagram")
        self.assertEqual([item["text"] for item in method["content"]["items"]],
                         ["Collect", "Retain raw observations.", "Review", "Log every exclusion."])
        outline["slides"][0]["flow_steps"][1]["detail"] = "Log missingness."
        edited = deck_ir_from_outline(outline)
        new_method = next(element for element in edited["slides"][0]["elements"] if element["editable_object_kind"] == "diagram")
        self.assertEqual(method["id"], new_method["id"])
        validate_deck_ir(ir)

    def _outline(self) -> dict[str, object]:
        return {
            "title": "Quarterly Reliability Review",
            "audience": "Operations leadership",
            "objective": "Approve the recovery plan",
            "slides": [
                {
                    "id": "cover",
                    "type": "title",
                    "title": "Quarterly Reliability Review",
                    "subtitle": "What changed and what happens next",
                },
                {
                    "type": "content",
                    "slide_intent": "evidence",
                    "visual_intent": "data",
                    "title": "Recovery time improved",
                    "bullets": [
                        "Median recovery time fell by 18%.",
                        {"text": "Two regions remain above target.", "level": 1},
                    ],
                    "assets": {"chart_data": "data:recovery_time"},
                    "sources": [
                        "Reliability report, page 4",
                        {
                            "kind": "data",
                            "citation": "Incident warehouse extract",
                            "url": "https://example.test/incidents",
                        },
                    ],
                },
            ],
        }

    def test_from_outline_builds_semantic_linked_ir(self) -> None:
        document = deck_ir_from_outline(self._outline(), source_path="outline.json")

        self.assertEqual(document["ir_version"], IR_VERSION)
        self.assertEqual(document["semantic_role"], "deck")
        self.assertEqual(document["source_outline"]["path"], "outline.json")
        self.assertEqual(document["slides"][0]["source_outline_ref"], "/slides/0")
        self.assertEqual(document["slides"][1]["semantic_role"], "evidence")
        self.assertEqual(document["slides"][1]["intent"]["visual_intent"], "data")

        second_slide = document["slides"][1]
        element_kinds = {
            element["editable_object_kind"] for element in second_slide["elements"]
        }
        self.assertIn("text", element_kinds)
        self.assertIn("chart", element_kinds)
        self.assertEqual(len(document["evidence"]), 2)
        self.assertEqual(
            set(second_slide["evidence_refs"]),
            {record["id"] for record in document["evidence"]},
        )
        citation = next(
            element
            for element in second_slide["elements"]
            if element["semantic_role"] == "citation"
        )
        self.assertEqual(citation["evidence_refs"], second_slide["evidence_refs"])
        self.assertEqual(
            [item["source_outline_ref"] for item in citation["content"]["items"]],
            ["/slides/1/sources/0", "/slides/1/sources/1"],
        )
        self.assertEqual(
            [item["text"] for item in citation["content"]["items"]],
            ["Reliability report, page 4", "Incident warehouse extract"],
        )
        self.assertEqual(
            second_slide["constraints"][0]["kind"], "reading_order"
        )
        validate_deck_ir(document)

    def test_ids_are_stable_across_repeated_conversion_and_text_edits(self) -> None:
        outline = self._outline()
        first = deck_ir_from_outline(outline)
        repeated = deck_ir_from_outline(copy.deepcopy(outline))
        self.assertEqual(first, repeated)

        edited_outline = copy.deepcopy(outline)
        edited_outline["slides"][1]["bullets"][0] = "Median recovery time fell by 21%."
        edited = deck_ir_from_outline(edited_outline)

        self.assertEqual(first["deck_id"], edited["deck_id"])
        self.assertEqual(
            [slide["id"] for slide in first["slides"]],
            [slide["id"] for slide in edited["slides"]],
        )
        self.assertEqual(
            [[element["id"] for element in slide["elements"]] for slide in first["slides"]],
            [[element["id"] for element in slide["elements"]] for slide in edited["slides"]],
        )
        self.assertNotEqual(
            first["source_outline"]["sha256"], edited["source_outline"]["sha256"]
        )

        reordered_outline = copy.deepcopy(outline)
        reordered_outline["slides"].reverse()
        reordered = deck_ir_from_outline(reordered_outline)
        first_by_title = {slide["intent"]["message"]: slide for slide in first["slides"]}
        reordered_by_title = {
            slide["intent"]["message"]: slide for slide in reordered["slides"]
        }
        self.assertEqual(set(first_by_title), set(reordered_by_title))
        for title in first_by_title:
            self.assertEqual(first_by_title[title]["id"], reordered_by_title[title]["id"])
            self.assertEqual(
                [element["id"] for element in first_by_title[title]["elements"]],
                [element["id"] for element in reordered_by_title[title]["elements"]],
            )
        self.assertNotEqual(
            first_by_title["Quarterly Reliability Review"]["source_outline_ref"],
            reordered_by_title["Quarterly Reliability Review"]["source_outline_ref"],
        )

    def test_canonicalization_and_hash_ignore_mapping_order(self) -> None:
        document = deck_ir_from_outline(self._outline())
        reordered = dict(reversed(list(document.items())))

        self.assertEqual(canonicalize_deck_ir(document), canonicalize_deck_ir(reordered))
        self.assertEqual(deck_ir_sha256(document), deck_ir_sha256(reordered))
        self.assertEqual(
            canonical_json_bytes({"b": 2, "a": 1}), b'{"a":1,"b":2}'
        )
        self.assertEqual(
            stable_id("element", {"b": 2, "a": 1}),
            stable_id("element", {"a": 1, "b": 2}),
        )

    def test_validation_rejects_wrong_version_coordinates_and_unknown_refs(self) -> None:
        document = deck_ir_from_outline(self._outline())

        wrong_version = copy.deepcopy(document)
        wrong_version["ir_version"] = "1.0"
        with self.assertRaisesRegex(DeckIRValidationError, "must equal 1.0.0"):
            validate_deck_ir(wrong_version)

        coordinate = copy.deepcopy(document)
        coordinate["slides"][0]["elements"][0]["x"] = 1.25
        with self.assertRaisesRegex(DeckIRValidationError, "unknown fields: x"):
            validate_deck_ir(coordinate)

        unknown_evidence = copy.deepcopy(document)
        unknown_evidence["slides"][0]["evidence_refs"] = ["evidence-missing-123"]
        with self.assertRaisesRegex(DeckIRValidationError, "unknown evidence ID"):
            validate_deck_ir(unknown_evidence)

    def test_schema_is_versioned_closed_and_coordinate_free(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(schema["properties"]["ir_version"]["const"], IR_VERSION)
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["slide"]["additionalProperties"])
        element = schema["$defs"]["element"]
        self.assertFalse(element["additionalProperties"])
        self.assertTrue({"x", "y", "w", "h"}.isdisjoint(element["properties"]))

    def test_explicit_migration_hook_is_required_and_validated(self) -> None:
        current = deck_ir_from_outline(self._outline())
        legacy = copy.deepcopy(current)
        legacy["ir_version"] = "0.9.0"

        with self.assertRaisesRegex(DeckIRMigrationError, "No registered migration"):
            migrate_deck_ir(legacy)

        def migrate_090_to_100(document: dict[str, object]) -> dict[str, object]:
            document["ir_version"] = IR_VERSION
            return document

        register_migration("0.9.0", IR_VERSION, migrate_090_to_100)
        try:
            self.assertIn(("0.9.0", IR_VERSION), registered_migrations())
            migrated = migrate_deck_ir(legacy)
            self.assertEqual(migrated, current)
            self.assertEqual(legacy["ir_version"], "0.9.0")
        finally:
            unregister_migration("0.9.0", IR_VERSION)

    def test_cli_from_outline_validate_and_hash_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            outline_path = temp / "outline.json"
            ir_path = temp / "deck_ir.json"
            outline_path.write_text(json.dumps(self._outline()), encoding="utf-8")

            converted = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "deck_ir.py"),
                    "from-outline",
                    str(outline_path),
                    "--output",
                    str(ir_path),
                ],
                cwd=REPO,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(converted.returncode, 0, converted.stderr)
            document = json.loads(ir_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ir_path.read_text(encoding="utf-8"),
                canonicalize_deck_ir(document) + "\n",
            )

            validated = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "deck_ir.py"),
                    "validate",
                    str(ir_path),
                    "--hash",
                ],
                cwd=REPO,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(
                validated.stdout.strip(), f"valid {deck_ir_sha256(document)}"
            )


if __name__ == "__main__":
    unittest.main()
