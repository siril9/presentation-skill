"""Apply a LEGO atom composition to a deck.

Reads a composition dict produced by:
- scripts/style_atom_router.py deterministic, OR
- an agent's JSON reply to the prompt emitted by emit_composition_prompt(),

and translates it into the existing skill vocabulary the renderer
already understands: deck_style fields + design_brief overrides +
variant preferences. The applier never invents fields — every atom
maps to an existing skill knob.

Mapping summary
---------------
- palette / typography           → design_brief.palette_signals, typography_signals
- chart_treatment atom value     → outline.deck_style.chart_treatment
- table_treatment atom value     → outline.deck_style.table_treatment
- header_treatment atom value    → outline.deck_style.header_mode
- footer_treatment atom value    → outline.deck_style.footer_mode
- density atom value             → outline.deck_style.visual_density
- decorative_motifs              → outline.deck_style.decorative_signals (list)
- layout_motifs / rhythm         → design_brief.rhythm_signals (guidance)
- arc_beats                      → outline.deck_style.arc_beats (sequence guidance)
- source_families                → outline.deck_style.style_seed_families

Variant preferences (used by the outline generator if it consults
the composition) come from the family grammar template via Layer 1
(style_grammar_index.json), tilted by the composed atoms.

Robust by design: missing atom types fall back to skill defaults.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = REPO_ROOT / "references" / "style_grammar_index.json"


# Map density atom values to the existing visual_density vocabulary.
DENSITY_TO_VISUAL_DENSITY = {
    "low": "low",
    "medium": "medium",
    "high": "high",
}

VALID_CHART_TREATMENTS = {
    "standard", "facts-below", "facts-right", "minimal",
    "hero-stat", "threshold-band", "sparse-wide",
}
VALID_TABLE_TREATMENTS = {
    "standard", "compact-ledger", "readout-sidecar",
    "decision-matrix", "journal-grid",
}
VALID_HEADER_MODES = {
    "bar", "eyebrow", "lab-card", "lab-clean", "stack",
}
VALID_FOOTER_MODES = {
    "standard", "source-line", "none",
}


def _strip_prefix(atom_id: str) -> str:
    """Convert 'chart_treatment:facts-right' → 'facts-right'."""
    if ":" in atom_id:
        return atom_id.split(":", 1)[1]
    return atom_id


def _validate(value: str, valid: set[str], fallback: str) -> str:
    return value if value in valid else fallback


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def apply_composition(
    composition: dict[str, Any],
    base_design_brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate a composition into design_brief + deck_style overrides.

    Returns a dict shaped like:
        {
            "design_brief": {...overrides for design_brief.json...},
            "deck_style":   {...overrides for outline.json's deck_style block...},
            "preferred_variants": [...],
            "narrative_arc": [...]
        }
    """
    brief = dict(base_design_brief or {})
    deck_style: dict[str, Any] = {}
    source_families = _as_text_list(composition.get("source_families"))
    target_family = str(composition.get("target_family") or "").strip()
    if not target_family and source_families:
        target_family = source_families[0]

    if composition.get("palette"):
        brief.setdefault("palette_signals", []).append(_strip_prefix(composition["palette"]))
    if composition.get("typography"):
        brief.setdefault("typography_signals", []).append(_strip_prefix(composition["typography"]))

    for motif_atom in composition.get("layout_motifs", []) or []:
        brief.setdefault("layout_signals", []).append(_strip_prefix(motif_atom))

    if composition.get("rhythm_signature"):
        brief["rhythm_signature"] = _strip_prefix(composition["rhythm_signature"])

    chart = _strip_prefix(composition.get("chart_treatment") or "")
    if chart:
        deck_style["chart_treatment"] = _validate(chart, VALID_CHART_TREATMENTS, "standard")

    table = _strip_prefix(composition.get("table_treatment") or "")
    if table:
        deck_style["table_treatment"] = _validate(table, VALID_TABLE_TREATMENTS, "standard")

    header = _strip_prefix(composition.get("header_treatment") or "")
    if header:
        deck_style["header_mode"] = _validate(header, VALID_HEADER_MODES, "bar")

    footer = _strip_prefix(composition.get("footer_treatment") or "")
    if footer:
        deck_style["footer_mode"] = _validate(footer, VALID_FOOTER_MODES, "standard")

    density_value = _strip_prefix(composition.get("density") or "")
    if density_value:
        deck_style["visual_density"] = DENSITY_TO_VISUAL_DENSITY.get(density_value, "medium")

    decorative = [_strip_prefix(atom) for atom in composition.get("decorative_motifs", []) or []]
    if decorative:
        deck_style["decorative_signals"] = decorative

    arc = [_strip_prefix(atom) for atom in composition.get("arc_beats", []) or []]
    if arc:
        deck_style["arc_beats"] = arc

    if not source_families and target_family:
        source_families = [target_family]
    if source_families:
        deck_style["style_seed_families"] = source_families

    grammar_template = _load_family_template(target_family)
    preferred_variants = list(grammar_template.get("preferred_variants", []))
    narrative_arc = list(grammar_template.get("narrative_arc", []))

    record_tilt = _as_text_list(composition.get("preferred_variants"))
    if record_tilt:
        preferred_variants = record_tilt

    deck_style["composition_mode"] = composition.get("composition_mode", "agent-picked")
    brief["style_atom_composition"] = {
        "schema_version": "style_atom_composition_v1",
        "target_family": target_family,
        "source_families": source_families,
        "composition_mode": deck_style["composition_mode"],
        "topic_terms": _as_text_list(composition.get("topic_terms")),
        "palette": composition.get("palette"),
        "typography": composition.get("typography"),
        "layout_motifs": _as_text_list(composition.get("layout_motifs")),
        "chart_treatment": composition.get("chart_treatment"),
        "table_treatment": composition.get("table_treatment"),
        "header_treatment": composition.get("header_treatment"),
        "footer_treatment": composition.get("footer_treatment"),
        "decorative_motifs": _as_text_list(composition.get("decorative_motifs")),
        "density": composition.get("density"),
        "arc_beats": _as_text_list(composition.get("arc_beats")),
        "rhythm_signature": composition.get("rhythm_signature"),
        "preferred_variants": preferred_variants,
        "artifact_density": composition.get("artifact_density", grammar_template.get("artifact_density")),
    }

    return {
        "design_brief": brief,
        "deck_style": deck_style,
        "preferred_variants": preferred_variants,
        "narrative_arc": arc or narrative_arc,
    }


def _load_family_template(family: str) -> dict[str, Any]:
    if not family:
        return {}
    try:
        grammar = json.loads(GRAMMAR_PATH.read_text())
    except FileNotFoundError:
        return {}
    return grammar.get("family_grammar_templates", {}).get(family, {})


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--composition", required=True, help="Path to composition JSON")
    parser.add_argument("--base-design-brief", help="Optional path to existing design_brief.json to merge into")
    parser.add_argument("--output", help="Write to file (default: stdout JSON)")
    args = parser.parse_args()

    composition = json.loads(Path(args.composition).read_text())
    base_brief = json.loads(Path(args.base_design_brief).read_text()) if args.base_design_brief else None

    result = apply_composition(composition, base_brief)
    text = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(text)
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    _cli()
