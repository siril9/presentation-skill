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

from composition_grammar_catalog import (
    V2_ROLE_VARIANT_CANDIDATES,
    _starter_sequence_for_candidate,
    compact_grammar_route,
    quick_deck_agent_brief,
    route_composition_grammars,
)
from model_adaptive_workflow import (
    PROFILE_ALIASES,
    build_agent_brief,
    minimal_payload_examples,
    normalize_profile,
    render_agent_brief_markdown,
    resolve_profile,
)
from preflight import _check_role_variant_alignment, _check_variant_required
import present


class ModelAdaptiveWorkflowTests(unittest.TestCase):
    def route(self, prompt="Public evidence, options and sources", **kwargs):
        return route_composition_grammars(topic="City cooling", user_prompt=prompt, **kwargs)

    def test_finalize_forwards_opt_in_render_cache(self):
        for cache in (None, Path("cache")):
            args = present._parser().parse_args([
                "finalize", "--outline", "input.json", "--output", "deck.pptx",
                *(["--render-cache-dir", str(cache)] if cache else []),
            ])
            with patch.object(present, "_run", return_value=0) as run:
                self.assertEqual(args.handler(args), 0)
            run.assert_called_once_with("finalize_quick_deck.py", [
                "--outline", str(Path("input.json").resolve()),
                "--output", str(Path("deck.pptx").resolve()),
                "--style-preset", "auto",
                *(["--render-cache-dir", str(cache.resolve())] if cache else []),
            ])

    def test_optional_audition_forwards_without_own_preset_validation(self):
        for presets in (["lab-report", "warm-terracotta"], ["future-preset"]):
            args = present._parser().parse_args([
                "audition", "--outline", "input.json", "--outdir", "previews",
                *(["--presets", *presets] if presets else []),
            ])
            with patch.object(present, "_run", return_value=7) as run:
                self.assertEqual(args.handler(args), 7)
            run.assert_called_once_with("audition_styles.py", [
                "--outline", str(Path("input.json").resolve()),
                "--outdir", str(Path("previews").resolve()),
                *(["--presets", *presets] if presets else []),
            ])
        fast = quick_deck_agent_brief(self.route(), slide_count=7, agent_profile="luna")
        self.assertNotIn("audition", fast["commands"])

    def test_aliases_and_auto_share_one_resolver(self):
        for requested in PROFILE_ALIASES:
            for prompt in ("Quick clinical trial draft", "Quick working draft", "City strategy review"):
                with self.subTest(requested=requested, prompt=prompt):
                    expected, basis = resolve_profile(requested, prompt)
                    quick = quick_deck_agent_brief(self.route(prompt), slide_count=7, agent_profile=requested)
                    workspace = build_agent_brief(packet={}, workspace=ROOT, user_prompt=prompt, requested_profile=requested)
                    self.assertEqual(quick["agent_profile"], expected)
                    self.assertEqual(quick["resolution_basis"], basis)
                    self.assertEqual(workspace["execution_profile"]["resolved"], expected)
                    self.assertEqual(workspace["execution_profile"]["resolution_basis"], basis)
        self.assertEqual(resolve_profile("auto", "Quick clinical trial draft")[0], "quality-first")
        self.assertEqual(resolve_profile("auto", "Quick working draft")[0], "fast")
        self.assertEqual(normalize_profile(" GPT-6-ASTRA "), "quality-first")
        for alias, profile in {"astra": "quality-first", "gpt-6-astra": "quality-first", "gpt-6-sol": "quality-first", "gpt-6-luna": "fast", "gpt-5.6-sol": "quality-first", "gpt-5.6-terra": "balanced", "gpt-5.6-luna": "fast"}.items():
            self.assertEqual(normalize_profile(alias), profile)

    def test_unknown_model_requires_explicit_policy(self):
        for unknown in ("gpt-future", "gpt-5.6-luna-unknown", "typo"):
            with self.assertRaisesRegex(ValueError, "choose an explicit workflow profile"):
                quick_deck_agent_brief(self.route(), slide_count=7, agent_profile=unknown)
            with self.assertRaisesRegex(ValueError, "choose an explicit workflow profile"):
                build_agent_brief(packet={}, workspace=ROOT, user_prompt="", requested_profile=unknown)
        for profile in ("fast", "balanced", "quality-first"):
            self.assertEqual(resolve_profile(profile, "Use unknown-model for a clinical deck")[0], profile)

    def test_compaction_preserves_resolution_context_and_style_lock(self):
        route = compact_grammar_route(self.route("Quick clinical draft", style_preset="lab-report"))
        brief = quick_deck_agent_brief(route, slide_count=7)
        self.assertEqual(brief["agent_profile"], "quality-first")
        self.assertEqual(len(brief["route_candidates"]), 1)
        self.assertEqual(brief["route_candidates"][0]["style_preset"], "lab-report")
        title_only = route_composition_grammars(topic="Clinical trial", user_prompt="  ")
        self.assertEqual(quick_deck_agent_brief(title_only, slide_count=7)["agent_profile"], "quality-first")

    def test_candidates_are_hints_and_capabilities_remain_authoritative(self):
        route = self.route()
        for profile, count in (("terra", 2), ("sol", 3), ("astra", 3)):
            brief = quick_deck_agent_brief(route, slide_count=30, agent_profile=profile)
            self.assertNotIn("story", brief)
            self.assertEqual(len(brief["route_candidates"]), count)
            for candidate, source in zip(brief["route_candidates"], [route["primary"], *route["alternatives"]]):
                self.assertNotIn("starter_sequence", candidate)
                self.assertEqual(candidate["story_shape"]["stages"], source["narrative_arc"]["stages"][:5])
                self.assertEqual(candidate["story_shape"]["role_variants"], source["role_variant_map"])
            self.assertEqual(brief["renderer"]["role_variants"], V2_ROLE_VARIANT_CANDIDATES)
            self.assertEqual(brief["renderer"]["layout_variants"], ["primary", "alternate", "dense"])
            self.assertLess(len(json.dumps(brief, separators=(",", ":"))), 9000)

    def test_starters_are_bounded_and_uniquely_numbered(self):
        route = self.route()
        for count in (0, 1, 2, *range(3, 31), 31, 100):
            expected = max(3, min(30, count))
            brief = quick_deck_agent_brief(route, slide_count=count, agent_profile="luna")
            self.assertEqual(brief["outline_contract"]["content_limits"]["slides"], expected)
            for candidate in (route["primary"], *route["alternatives"]):
                sequence = _starter_sequence_for_candidate(candidate, count)
                self.assertEqual(len(sequence), expected)
                self.assertEqual([slide["slide"] for slide in sequence], list(range(1, expected + 1)))
                self.assertEqual(len({json.dumps(slide, sort_keys=True) for slide in sequence}), expected)
                for slide in sequence:
                    self.assertIn(slide["variant"], V2_ROLE_VARIANT_CANDIDATES[slide["role"]])

    def test_luna_payloads_and_same_completion_target(self):
        quick = quick_deck_agent_brief(self.route(), slide_count=7, agent_profile="gpt-5.6-luna")
        six_luna = quick_deck_agent_brief(self.route(), slide_count=7, agent_profile="gpt-6-luna")
        self.assertEqual(six_luna["agent_profile"], quick["agent_profile"])
        self.assertEqual(six_luna["outline_contract"], quick["outline_contract"])
        self.assertEqual(six_luna["commands"], quick["commands"])
        examples = quick["outline_contract"]["minimal_payload_examples"]
        self.assertEqual(examples, minimal_payload_examples())
        self.assertEqual(set(examples), {v for values in V2_ROLE_VARIANT_CANDIDATES.values() for v in values})
        for role, variants in V2_ROLE_VARIANT_CANDIDATES.items():
            for variant in variants:
                slide = {"type": "title" if role == "title" else "content", "role": role, "variant": variant, "title": "Synthetic illustration", "sources": ["S1: synthetic illustration"], **examples[variant]}
                self.assertFalse(_check_role_variant_alignment(slide, 1))
                self.assertFalse(_check_variant_required(slide, 1, ROOT), (role, variant))
        self.assertEqual(quick["agent_mode"], "single-agent")
        self.assertLess(len(json.dumps(quick, separators=(",", ":"))), 9000)
        briefs = [build_agent_brief(packet={}, workspace=ROOT, user_prompt="Clinical review", requested_profile=p) for p in ("luna", "sol", "astra")]
        self.assertEqual(briefs[0]["completion_rubric"], briefs[1]["completion_rubric"])
        self.assertEqual(briefs[0]["quality_contract"], briefs[2]["quality_contract"])
        self.assertEqual(briefs[0]["execution_profile"]["agent_mode"], "single-agent")
        self.assertEqual(briefs[0]["execution_profile"]["delegation"]["data_scout"], "skip")
        self.assertIn('"cards-2":{"cards":', render_agent_brief_markdown(briefs[0]))

    def test_public_cli_matches_workspace_init(self):
        cases = [
            ("auto", "Clinical trial draft", "", "quality-first"),
            ("auto", "City review", "Quick working draft", "fast"),
            ("auto", "City review", "Strategy review", "balanced"),
            ("astra", "City review", "", "quality-first"),
            ("gpt-6-astra", "City review", "", "quality-first"),
            ("gpt-6-sol", "City review", "", "quality-first"),
            ("gpt-6-luna", "City review", "", "fast"),
            ("gpt-5.6-sol", "City review", "", "quality-first"),
            ("gpt-5.6-terra", "City review", "", "balanced"),
            ("gpt-5.6-luna", "City review", "", "fast"),
        ]
        with tempfile.TemporaryDirectory(prefix="presentation-profile-tests-") as tmp:
            for i, (profile, title, prompt, expected) in enumerate(cases):
                with self.subTest(profile=profile, prompt=prompt):
                    workspace = Path(tmp) / str(i)
                    common = ["--profile", profile, "--prompt", prompt]
                    quick_run = subprocess.run([sys.executable, str(ROOT / "scripts/present.py"), "brief", "--topic", title, *common], capture_output=True, text=True, check=True)
                    subprocess.run([sys.executable, str(ROOT / "scripts/present.py"), "init", "--workspace", str(workspace), "--title", title, *common], capture_output=True, text=True, check=True)
                    quick = json.loads(quick_run.stdout)
                    saved = json.loads((workspace / "agent_brief.json").read_text())["execution_profile"]
                    self.assertEqual(quick["agent_profile"], expected)
                    self.assertEqual(saved["resolved"], expected)
                    self.assertEqual(quick["resolution_basis"], saved["resolution_basis"])
            invalid = Path(tmp) / "unknown"
            failed = subprocess.run([sys.executable, str(ROOT / "scripts/present.py"), "init", "--workspace", str(invalid), "--title", "Demo", "--profile", "gpt-future"], capture_output=True, text=True)
            self.assertEqual(failed.returncode, 2)
            self.assertFalse(invalid.exists())
            self.assertNotIn("Traceback", failed.stderr)


if __name__ == "__main__":
    unittest.main()
