#!/usr/bin/env python3
"""Focused smoke for corpus atom routing and composition application."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from apply_atom_composition import apply_composition
from style_atom_router import deterministic_composition, emit_composition_prompt


ROOT = Path(__file__).resolve().parent.parent
ATLAS_PATH = ROOT / "references" / "style_token_atlas.json"
GRAMMAR_PATH = ROOT / "references" / "style_grammar_index.json"
MIN_ATOM_COUNT = 250


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    atlas = _load(ATLAS_PATH)
    grammar = _load(GRAMMAR_PATH)
    atom_counts = atlas.get("atom_type_counts") or {}
    total_atoms = sum(int(value or 0) for value in atom_counts.values())
    _assert(total_atoms >= MIN_ATOM_COUNT, f"expected >= {MIN_ATOM_COUNT} atoms, saw {total_atoms}")
    for atom_type in (
        "palette",
        "typography",
        "layout_motif",
        "chart_treatment",
        "table_treatment",
        "header_treatment",
        "footer_treatment",
        "decorative_motif",
        "density",
        "arc_beat",
        "rhythm_signature",
        "content_treatment",
    ):
        _assert(int(atom_counts.get(atom_type) or 0) > 0, f"missing atoms for {atom_type}")

    templates = grammar.get("family_grammar_templates") or {}
    _assert(len(templates) >= 13, f"expected at least 13 family templates, saw {len(templates)}")

    families_checked = []
    for family in sorted(templates):
        composition = deterministic_composition(
            family,
            10,
            topic=f"{family} workflow evidence dashboard",
            user_prompt="clean editable deck with chart table figure and decision evidence",
        )
        _assert(composition.get("target_family") == family, f"{family} target_family drift")
        _assert(composition.get("preferred_variants"), f"{family} missing preferred variants")
        _assert(composition.get("topic_terms"), f"{family} missing topic terms")
        applied = apply_composition(composition)
        deck_style = applied.get("deck_style") or {}
        brief = applied.get("design_brief") or {}
        ledger = brief.get("style_atom_composition") or {}
        _assert(deck_style.get("composition_mode") == "deterministic-fallback", f"{family} composition mode missing")
        _assert(deck_style.get("style_seed_families") == [family], f"{family} source family not preserved")
        _assert(ledger.get("target_family") == family, f"{family} atom ledger target missing")
        _assert(ledger.get("preferred_variants"), f"{family} atom ledger variants missing")
        families_checked.append(family)

    clinical = deterministic_composition(
        "midnight-neon",
        10,
        topic="Remote spirometry cohort endpoints",
        user_prompt="clinical cohort table safety endpoints",
    )
    console = deterministic_composition(
        "midnight-neon",
        10,
        topic="Night market battery swap console",
        user_prompt="AI workflow command console growth loops",
    )
    _assert(clinical.get("topic_terms") != console.get("topic_terms"), "topic terms did not change")
    _assert(
        clinical.get("layout_motifs") != console.get("layout_motifs")
        or clinical.get("palette") != console.get("palette"),
        "topic-aware deterministic composition did not affect visible atom choices",
    )

    prompt_packet = emit_composition_prompt(
        topic="hospital discharge bottleneck",
        user_prompt="operations deck with metrics, tradeoffs, and next actions",
        target_family="lavender-ops",
        slide_count=9,
    )
    prompt = str(prompt_packet.get("prompt") or "")
    for token in ("target_family", "source_families", "preferred_variants", "Use strict JSON only"):
        _assert(token in prompt, f"composition prompt missing {token}")
    _assert("//" not in prompt, "composition prompt contains comment-style JSON")

    print(
        json.dumps(
            {
                "passed": True,
                "total_atoms": total_atoms,
                "atom_type_counts": atom_counts,
                "families_checked": len(families_checked),
                "prompt_chars": len(prompt),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
