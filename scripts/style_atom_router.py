"""Compose a deck style from the LEGO atom atlas.

Two entry points:

1. ``emit_composition_prompt(topic, user_prompt, target_family, slide_count)``
   Returns a structured prompt the calling agent (Codex/ChatGPT) reads to
   pick atoms across families. The agent's reply is JSON that goes back
   through ``apply_composition()``. This is how the skill leverages
   improving LLMs without calling APIs itself.

2. ``deterministic_composition(target_family, slide_count, topic, user_prompt)``
   Picks reproducible atoms within the target family, with a light topic
   relevance nudge. Used when no agent is in the loop (CLI builds, smoke
   tests, etc.). Guarantees the skill never breaks if an LLM is unavailable.

The output composition shape (whether agent-picked or deterministic):

    {
        "palette":           "palette:<value>",
        "typography":        "typography:<value>",
        "layout_motifs":     ["layout_motif:<value>", ...],
        "chart_treatment":   "chart_treatment:<value>",
        "table_treatment":   "table_treatment:<value>",
        "header_treatment":  "header_treatment:<value>",
        "footer_treatment":  "footer_treatment:<value>",
        "decorative_motifs": ["decorative_motif:<value>", ...],
        "density":           "density:<value>",
        "arc_beats":         ["arc_beat:<value>", ...],
        "rhythm_signature":  "rhythm_signature:<value>",
        "source_families":   ["data-heavy-boardroom", "arctic-minimal", ...],
        "composition_mode":  "agent-picked" | "deterministic-fallback",
        "target_family":     "lab-report",
        "preferred_variants": ["scientific-figure", "table", ...]
    }

``apply_composition()`` in scripts/apply_atom_composition.py turns this
into design_brief.json overrides + per-slide variant tilts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ATLAS_PATH = REPO_ROOT / "references" / "style_token_atlas.json"
GRAMMAR_PATH = REPO_ROOT / "references" / "style_grammar_index.json"

# How many candidate atoms per type to surface in the agent prompt.
# Trimmed enough to fit a single prompt comfortably; broad enough that the
# agent has cross-family options.
TYPE_CANDIDATE_LIMITS = {
    "palette": 12,
    "typography": 10,
    "layout_motif": 14,
    "chart_treatment": 6,
    "table_treatment": 4,
    "header_treatment": 5,
    "footer_treatment": 3,
    "decorative_motif": 12,
    "density": 3,
    "arc_beat": 18,
    "rhythm_signature": 10,
}

# How many atoms the agent should pick per type for the final composition.
PICK_TARGETS = {
    "palette": 1,
    "typography": 1,
    "layout_motifs": (1, 2),
    "chart_treatment": 1,
    "table_treatment": 1,
    "header_treatment": 1,
    "footer_treatment": 1,
    "decorative_motifs": (2, 3),
    "density": 1,
    "arc_beats": (5, 7),
    "rhythm_signature": 1,
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "the", "to", "with", "without",
}


def _topic_terms(*parts: str) -> set[str]:
    raw = " ".join(part or "" for part in parts).lower()
    out: set[str] = set()
    token: list[str] = []
    for ch in raw:
        if ch.isalnum():
            token.append(ch)
        else:
            if len(token) >= 3:
                value = "".join(token)
                if value not in STOPWORDS:
                    out.add(value)
            token = []
    if len(token) >= 3:
        value = "".join(token)
        if value not in STOPWORDS:
            out.add(value)
    return out


def _atom_topic_score(atom: dict[str, Any], terms: set[str]) -> int:
    if not terms:
        return 0
    text_parts = [
        str(atom.get("atom_id") or ""),
        str(atom.get("value") or ""),
        str(atom.get("atom_type") or ""),
    ]
    text = " ".join(text_parts).lower().replace("-", " ").replace("_", " ")
    compact = text.replace(" ", "")
    return sum(1 for term in terms if term in text or term in compact)


def _load_atlas() -> dict[str, Any]:
    with ATLAS_PATH.open() as fh:
        return json.load(fh)


def _load_grammar() -> dict[str, Any]:
    with GRAMMAR_PATH.open() as fh:
        return json.load(fh)


def _atoms_for_type(atlas: dict[str, Any], atom_type: str) -> list[dict[str, Any]]:
    return atlas.get("atoms", {}).get(atom_type, [])


def _rank_for_family(
    atoms: list[dict[str, Any]],
    primary_family: str,
    related_families: list[str],
    topic_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Re-rank atoms so primary-family atoms surface first, then related, then rest.

    Within each tier preserves the atlas's frequency ordering. Atoms with
    zero presence in the primary family but high overall frequency still
    appear (lower tier) so cross-family mixing is possible.
    """
    primary_set = set([primary_family])
    related_set = set(related_families)
    terms = topic_terms or set()

    def tier(atom: dict[str, Any]) -> int:
        origins = atom.get("family_origins", {})
        if any(origins.get(f, 0) > 0 for f in primary_set):
            return 0
        if any(origins.get(f, 0) > 0 for f in related_set):
            return 1
        return 2

    def family_specific_freq(atom: dict[str, Any], families: set[str]) -> int:
        origins = atom.get("family_origins", {})
        return sum(origins.get(f, 0) for f in families)

    return sorted(
        atoms,
        key=lambda a: (
            tier(a),
            -_atom_topic_score(a, terms),
            -family_specific_freq(a, primary_set) if tier(a) == 0 else 0,
            -family_specific_freq(a, related_set) if tier(a) == 1 else 0,
            -a.get("frequency", 0),
        ),
    )


def _candidate_block(
    atoms: list[dict[str, Any]],
    primary_family: str,
    related_families: list[str],
    limit: int,
    topic_terms: set[str] | None = None,
) -> list[dict[str, Any]]:
    ranked = _rank_for_family(atoms, primary_family, related_families, topic_terms)
    return ranked[:limit]


def _format_candidate(atom: dict[str, Any]) -> str:
    origins = atom.get("family_origins", {})
    origin_strs = [f"{fam}={n}" for fam, n in list(origins.items())[:4]]
    return (
        f"  - {atom['atom_id']} (value: \"{atom['value']}\", "
        f"freq={atom['frequency']}, origins: {', '.join(origin_strs)})"
    )


def _related_families(primary_family: str, grammar_index: dict[str, Any]) -> list[str]:
    """Pick related families heuristically by shared narrative-arc beats."""
    templates = grammar_index.get("family_grammar_templates", {})
    primary_arc = set(templates.get(primary_family, {}).get("narrative_arc", []))
    if not primary_arc:
        return []
    scored: list[tuple[float, str]] = []
    for fam, tpl in templates.items():
        if fam == primary_family:
            continue
        arc = set(tpl.get("narrative_arc", []))
        if not arc:
            continue
        overlap = len(primary_arc & arc) / max(1, len(primary_arc | arc))
        scored.append((overlap, fam))
    scored.sort(reverse=True)
    return [fam for _, fam in scored[:3]]


def emit_composition_prompt(
    topic: str,
    user_prompt: str,
    target_family: str,
    slide_count: int,
) -> dict[str, Any]:
    atlas = _load_atlas()
    grammar = _load_grammar()
    related = _related_families(target_family, grammar)
    family_template = grammar.get("family_grammar_templates", {}).get(target_family, {})
    terms = _topic_terms(topic, user_prompt)

    candidates: dict[str, list[dict[str, Any]]] = {}
    for atom_type, limit in TYPE_CANDIDATE_LIMITS.items():
        atoms = _atoms_for_type(atlas, atom_type)
        candidates[atom_type] = _candidate_block(
            atoms,
            target_family,
            related,
            limit,
            topic_terms=terms,
        )

    prompt_lines: list[str] = [
        "You are composing the visual + structural style of a slide deck by",
        "picking LEGO atoms from a 2,000-record style corpus. Mix and match",
        "atoms across families. The goal is a deck that is:",
        "  - coherent (the atoms harmonize visually + structurally)",
        "  - distinctive (this deck does not look template-cycled)",
        "  - content-fit (atoms match the topic + user prompt)",
        "",
        f"Topic: {topic}",
        f"User prompt: {user_prompt}",
        f"Primary style family: {target_family}",
        f"Related families (for cross-family mixing): {', '.join(related) or '(none)'}",
        f"Target slide count: {slide_count}",
        f"Topic terms used for ranking: {', '.join(sorted(terms)) or '(none)'}",
        "",
        "Family baseline (the deterministic fallback if you decline to pick):",
        f"  preferred_variants: {family_template.get('preferred_variants', [])}",
        f"  narrative_arc:      {family_template.get('narrative_arc', [])}",
        f"  artifact_density:   {family_template.get('artifact_density', 0.7)}",
        f"  rhythm_signature:   {family_template.get('rhythm_signature', '')}",
        "",
        "Candidates per atom type (primary-family atoms first, then related,",
        "then cross-family). Higher frequency = more common in corpus.",
        "Pick atoms by atom_id.",
        "",
    ]

    for atom_type, atoms in candidates.items():
        prompt_lines.append(f"### {atom_type.upper()}")
        for atom in atoms:
            prompt_lines.append(_format_candidate(atom))
        prompt_lines.append("")

    prompt_lines.extend(
        [
            "Return JSON with this exact shape:",
            "",
            "{",
            '  "target_family": "primary-family-slug",',
            '  "palette": "palette:<value>",',
            '  "typography": "typography:<value>",',
            '  "layout_motifs": ["layout_motif:<value>"],',
            '  "chart_treatment": "chart_treatment:<value>",',
            '  "table_treatment": "table_treatment:<value>",',
            '  "header_treatment": "header_treatment:<value>",',
            '  "footer_treatment": "footer_treatment:<value>",',
            '  "decorative_motifs": ["decorative_motif:<value>"],',
            '  "density": "density:<value>",',
            '  "arc_beats": ["arc_beat:<value>"],',
            '  "rhythm_signature": "rhythm_signature:<value>",',
            '  "source_families": ["primary-family-slug"],',
            '  "preferred_variants": ["supported-outline-variant"],',
            '  "composition_mode": "agent-picked",',
            '  "reasoning": "1-2 sentences on why this mix fits"',
            "}",
            "",
            "Use strict JSON only: no comments, no trailing commas.",
            "Pick 1-2 layout_motifs, 2-3 decorative_motifs, and 5-7 arc_beats.",
            "Constraint: at least one atom must come from a non-primary family.",
            "Constraint: arc_beats must be ordered as the deck would flow.",
            "Constraint: preferred_variants must use only variants supported by the skill.",
        ]
    )

    return {
        "schema_version": "atom_composition_prompt_v1",
        "topic": topic,
        "user_prompt": user_prompt,
        "target_family": target_family,
        "related_families": related,
        "slide_count": slide_count,
        "prompt": "\n".join(prompt_lines),
        "candidates": candidates,
    }


def deterministic_composition(
    target_family: str,
    slide_count: int,
    topic: str = "",
    user_prompt: str = "",
) -> dict[str, Any]:
    atlas = _load_atlas()
    grammar = _load_grammar()
    related = _related_families(target_family, grammar)
    template = grammar.get("family_grammar_templates", {}).get(target_family, {})
    terms = _topic_terms(topic, user_prompt)

    def pick_one(atom_type: str) -> str | None:
        atoms = _atoms_for_type(atlas, atom_type)
        ranked = _rank_for_family(atoms, target_family, related, terms)
        return ranked[0]["atom_id"] if ranked else None

    def pick_n(atom_type: str, n: int) -> list[str]:
        atoms = _atoms_for_type(atlas, atom_type)
        ranked = _rank_for_family(atoms, target_family, related, terms)
        return [a["atom_id"] for a in ranked[:n]]

    arc = template.get("narrative_arc", [])
    arc_beats = [f"arc_beat:{beat}" for beat in arc[:7]]

    composition: dict[str, Any] = {
        "palette": pick_one("palette"),
        "typography": pick_one("typography"),
        "layout_motifs": pick_n("layout_motif", 2),
        "chart_treatment": pick_one("chart_treatment"),
        "table_treatment": pick_one("table_treatment"),
        "header_treatment": pick_one("header_treatment"),
        "footer_treatment": pick_one("footer_treatment"),
        "decorative_motifs": pick_n("decorative_motif", 3),
        "density": pick_one("density"),
        "arc_beats": arc_beats,
        "rhythm_signature": pick_one("rhythm_signature"),
        "source_families": [target_family],
        "composition_mode": "deterministic-fallback",
        "target_family": target_family,
        "slide_count": slide_count,
        "topic_terms": sorted(terms),
        "preferred_variants": list(template.get("preferred_variants", [])),
        "artifact_density": template.get("artifact_density"),
    }
    return composition


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_prompt = sub.add_parser("emit-prompt", help="Emit composition prompt for an agent.")
    p_prompt.add_argument("--topic", required=True)
    p_prompt.add_argument("--user-prompt", default="")
    p_prompt.add_argument("--family", required=True)
    p_prompt.add_argument("--slide-count", type=int, default=10)
    p_prompt.add_argument("--output", help="Write to file (default: stdout JSON)")

    p_det = sub.add_parser("deterministic", help="Emit deterministic composition.")
    p_det.add_argument("--family", required=True)
    p_det.add_argument("--slide-count", type=int, default=10)
    p_det.add_argument("--topic", default="")
    p_det.add_argument("--user-prompt", default="")
    p_det.add_argument("--output", help="Write to file (default: stdout JSON)")

    args = parser.parse_args()

    if args.cmd == "emit-prompt":
        result = emit_composition_prompt(
            args.topic, args.user_prompt, args.family, args.slide_count
        )
    else:
        result = deterministic_composition(
            args.family,
            args.slide_count,
            topic=args.topic,
            user_prompt=args.user_prompt,
        )

    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    _cli()
