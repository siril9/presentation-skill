from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deck_intake import build_deck_intake
from composition_grammar_catalog import quick_deck_agent_brief, route_composition_grammars
from model_adaptive_workflow import write_agent_brief


class DeckIntakeTests(unittest.TestCase):
    def test_simple_request_proceeds_without_routine_questions(self):
        result = build_deck_intake("Explain how rainbows form")
        self.assertEqual(result["action"], "proceed_with_assumptions")
        self.assertTrue(result["questions_optional"])
        self.assertEqual(result["questions"], [])
        self.assertIn("audience", result["assumptions"])
        self.assertNotIn("usage_choice", result)

    def test_only_missing_consequential_fields_up_to_three(self):
        prompt = "Prepare a regulatory decision deck with brand requirements"
        first = build_deck_intake(prompt)
        self.assertEqual([q["id"] for q in first["questions"]], ["audience", "purpose", "evidence"])
        second = build_deck_intake(prompt, answers={"audience": "Regulators", "purpose": "Review an application"})
        self.assertEqual([q["id"] for q in second["questions"]], ["evidence", "style"])
        complete = build_deck_intake(prompt, answers={"audience": "Regulators", "purpose": "Review", "evidence": "Provided data", "style": "No preference"})
        self.assertEqual(complete["questions"], [])
        self.assertEqual(complete["assumptions"], {})

    def test_prompt_answers_are_not_repeated(self):
        result = build_deck_intake("Recommend an option for executives using supplied data. Style: monochrome. This is a board decision.")
        self.assertEqual(result["questions"], [])
        self.assertEqual(set(result["answered"]), {"audience", "purpose", "evidence", "style"})
        explicit = build_deck_intake("Audience: board", answers={"audience": "Clinicians"})
        self.assertEqual(explicit["answered"]["audience"], "Clinicians")

    def test_model_choice_requires_caller_usage_signal(self):
        for prompt in ("Context budget 2%", "Usage is low", "Only 3% remaining", "Use Luna"):
            self.assertNotIn("usage_choice", build_deck_intake(prompt, available_models=["gpt-5.6-luna"]))
        self.assertNotIn("usage_choice", build_deck_intake("", remaining_percent=11, available_models=["gpt-5.6-luna"]))
        with patch("builtins.open", side_effect=AssertionError("No filesystem lookup allowed")):
            result = build_deck_intake("", remaining_percent=10, current_model="gpt-6-astra", available_models=["gpt-5.6-luna"])
        choice = result["usage_choice"]
        self.assertEqual(choice["default"], "current")
        self.assertFalse(choice["automatic_switch"])
        self.assertTrue(choice["selection_required_for_change"])
        self.assertEqual([option["id"] for option in choice["options"]], ["current", "luna"])
        self.assertEqual(choice["options"][1]["model"], "gpt-5.6-luna")
        self.assertEqual(choice["qa_target"], "unchanged")

    def test_unknown_availability_offers_profile_not_a_model(self):
        for models in (None, [], ["gpt-6-astra"], ["gpt-5.6-luna-unknown"]):
            choice = build_deck_intake("", remaining_percent=0, available_models=models)["usage_choice"]
            self.assertEqual(choice["options"][1]["id"], "fast_profile")
            self.assertEqual(choice["options"][1]["profile"], "fast")
            self.assertNotIn("model", choice["options"][1])
        self.assertNotIn("usage_choice", build_deck_intake("", remaining_percent=0, current_model="gpt-5.6-luna", available_models=["gpt-5.6-luna"]))

    def test_low_usage_prefers_confirmed_six_luna_without_switching(self):
        choice = build_deck_intake(
            "", remaining_percent=10, current_model="gpt-6-sol",
            available_models=["gpt-5.6-luna", " GPT-6-LUNA "],
        )["usage_choice"]
        self.assertEqual(choice["default"], "current")
        self.assertTrue(choice["selection_required_for_change"])
        self.assertFalse(choice["automatic_switch"])
        self.assertEqual(choice["options"][1]["model"], "gpt-6-luna")
        self.assertEqual(choice["options"][1]["profile"], "fast")
        self.assertEqual(choice["qa_target"], "unchanged")
        self.assertNotIn("usage_choice", build_deck_intake(
            "", remaining_percent=10, current_model=" GPT-6-LUNA ",
            available_models=["gpt-6-luna", "gpt-5.6-luna"],
        ))
        fallback = build_deck_intake(
            "", remaining_percent=5, current_model="gpt-6-sol",
            available_models=["gpt-5.6-luna"],
        )["usage_choice"]
        self.assertEqual(fallback["options"][1]["model"], "gpt-5.6-luna")

    def test_invalid_signals_and_answers_have_clear_errors(self):
        for value in (-1, 101, float("nan"), float("inf"), True, "5"):
            with self.assertRaisesRegex(ValueError, "finite number"):
                build_deck_intake("", remaining_percent=value)
        for answers in ([], {"unknown": "value"}, {"audience": ["board"]}):
            with self.assertRaises(ValueError):
                build_deck_intake("", answers=answers)
        with self.assertRaisesRegex(ValueError, "list of model names"):
            build_deck_intake("", remaining_percent=5, available_models="gpt-5.6-luna")

    def test_brief_offer_does_not_change_profile_or_qa(self):
        route = route_composition_grammars(topic="Clinical decision", user_prompt="Recommend an option", style_preset="lab-report")
        normal = quick_deck_agent_brief(route, slide_count=7, agent_profile="astra")
        offered = quick_deck_agent_brief(route, slide_count=7, agent_profile="astra", intake_answers={"audience": "Clinicians"}, remaining_percent=5, current_model="gpt-6-astra", available_models=["gpt-5.6-luna"])
        self.assertEqual(offered["agent_profile"], "quality-first")
        self.assertEqual(offered["outline_contract"], normal["outline_contract"])
        self.assertEqual(offered["commands"], normal["commands"])
        self.assertNotIn("style", [q["id"] for q in offered["intake"]["questions"]])
        self.assertNotIn("audience", [q["id"] for q in offered["intake"]["questions"]])

    def test_workspace_reuses_saved_answers(self):
        with tempfile.TemporaryDirectory(prefix="presentation-intake-") as tmp:
            workspace = Path(tmp)
            (workspace / "design_brief.json").write_text(json.dumps({"user_intake": {"audience_context": "Board", "target_outcome": "Approve funding", "evidence_assets": "Supplied CSV", "style_direction": "Existing brand", "answered_by": "user"}}))
            _, md, brief = write_agent_brief(packet={}, workspace=workspace, user_prompt="Regulatory decision with brand requirements")
            self.assertEqual(brief["intake"]["questions"], [])
            self.assertIn("Do not repeat answered questions", md.read_text())

    def test_public_intake_and_brief_cli(self):
        arguments = ["--answers", '{"audience":"Board","evidence":"Supplied CSV"}', "--remaining-percent", "5", "--current-model", "gpt-6-astra", "--available-models", "gpt-6-astra", "gpt-5.6-luna"]
        for command in (["intake", "--prompt", "Board decision"], ["brief", "--topic", "Board decision", "--profile", "astra"]):
            run = subprocess.run([sys.executable, str(ROOT / "scripts/present.py"), *command, *arguments], capture_output=True, text=True, check=True)
            payload = json.loads(run.stdout)
            intake = payload.get("intake", payload)
            self.assertEqual(intake["usage_choice"]["default"], "current")
            self.assertEqual([q["id"] for q in intake["questions"]], ["purpose"])
        for extra in (["--remaining-percent", "nan"], ["--answers", "[]"], ["--answers", "invalid"]):
            run = subprocess.run([sys.executable, str(ROOT / "scripts/present.py"), "intake", "--prompt", "Demo", *extra], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()
