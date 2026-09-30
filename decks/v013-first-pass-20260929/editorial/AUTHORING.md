# Editorial Authoring Record

Run-01 follow-up: inspected the chapter-spread timeline fit failure (0.93 inches needed, 0.84 available at 22 pt). Sent the source and content-aware row-allocation request to Galileo. All scenes, caveats, typography, and the six-slide sequence remain unchanged. No author build; shared fixes and next main build are pending. Full audit: `../lab/RUN01_SOURCE_AUDIT.md`.

Status: full original source ready; main owns build and measurements. No rendering or finalization until main is ready. After the build, inspect all six slides and repair content without dropping captions, assumptions, or warnings.

Requested author model: GPT-6.1 Sol. Observed CLI alias absent; quick brief uses `--profile sol --current-model gpt-6.1-sol`. Profiles are workflow policy, not model switching.

## Failures To Prevent

- Arrivals are not boardings, offered places are not occupied seats, and records across evenings are not distinct individuals.
- A constructed mean cannot be passed off as a measured forecast or causal service result.
- Re-timing must retain equal demand and 480 places in both scenarios.
- Lower late queues can hide worse early access; keep the initial 40-person queue visible.
- Slot-end queues are not individual waits or continuous-time peaks.
- An editorial story must not turn into invented eyewitness testimony or an asset-led travel pitch.
- Caption removal to fit a layout would erase the model boundary; core owners handle renderer defects.

## Original Outline And Design

Audience: mobility planners who need an approachable account of a constrained service problem. Decision: investigate a bounded seat-release experiment, not authorize a timetable.

Selected brief candidate: `editorial-minimal` + `editorial-spread`; `editorial_serif_v1`; full readability contract copied from the brief. Asymmetric spread geometry and serif hierarchy, with open narrative space followed by dense native proof objects. No external images, logos, invented quotation, or generated art. The arrival chart and queue ledger are the visual subjects.

1. Premise: the evening does not fit the timetable; editorial masthead.
2. Scene: three timestamped queue moments, editable timeline with alternate layout.
3. Pressure: native demand versus offered-place chart; 47% in the middle hour.
4. Turn: asymmetric comparison of identical capacity with different release timing.
5. Consequence: native six-row queue table makes early harm and residual demand explicit.
6. Close: test the wave, protect the early rider, retain the capacity shortfall.

This is premise -> scene -> pressure -> turn -> consequence -> close, not the lab's method/result/replicate audit or the ops decision/control sequence. The diagram-free editorial geometry differs from the other decks beyond palette.

## Factual Checklist

SYN-F1 = original invented route, arrivals, and baseline; SYN-F2 = original invented moved-release model. No external sources.

- Six 30-minute intervals, one-way 17:00-20:00; ten identical evenings.
- Arrivals 40, 65, 110, 145, 105, 75 sum to 540/evening and 5,400 across ten evenings.
- 18:00-19:00 arrivals = 255; 255/540 = 47.2%, shown as 47%.
- Both scenarios offer 480 places/evening, six releases of 80; the moved case has two releases at 19:00 and none at 17:30.
- Baseline 425 boardings + 115 queued = 540; 55 offered places unused.
- Moved case 480 boardings + 60 queued = 540; zero unused places.
- Difference 55 boardings/evening; 550 across ten evenings. Peak slot-end queues: 120 versus 65. Early moved queue: 40.
- FIFO and no abandonment; no continuous-time waiting data, uncertainty interval, operational feasibility, certified capacity, forecast, or field causal claim.

## Commands And Handoff

Source factual check passed using `node decks/v013-first-pass-20260929/lab/check_sources.js`. `factual_check.json` binds the outline and data hashes to the independently recalculated queues, conservation of arrivals, equal capacity, totals, and percentage share. Native chart/table bindings, selected brief grammar, exact readability contract, and visible caveats passed. This is source-only verification, not rendered content fidelity or visual approval.

Run from `/Users/sirilarockiam/CascadeProjects/presentation-skill`. Main should use output `deck.pptx` and keep QA in this folder.

```bash
python3 scripts/present.py finalize --outline /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/editorial/outline.json --output /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/editorial/deck.pptx --qa-dir /Users/sirilarockiam/CascadeProjects/presentation-skill/decks/v013-first-pass-20260929/editorial/qa
```

Command recorded, not executed. The brief JSON preserves the actual request and selected grammar. Main may refresh the brief with the new `gpt-6.1-sol` alias after integration; do not treat profile selection as model provenance. Keep all captions and model limits in visible content during repairs. No core/shared/plugin edits or commit.
