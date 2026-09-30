# v0.13 Design Studies

Three original GPT-6.1 Sol-authored sources explore different arguments:
enzyme-storage evidence, evening ferry demand, and a microgrid repair decision.
One GPT-6 Luna-authored seed-library source is retained from v0.12 for compatibility.
All scenarios and data are synthetic. These are design studies, not a controlled
comparison against native Codex, Claude Code, or another model.

The source outlines stayed unchanged during shared renderer repairs. After user
review, a Sol authoring pass tightened the operations acceptance wording without
removing its conditions, figures, or safety caveats. Earlier attempts retain their
original source hashes. Source arithmetic checks do not validate real-world
outcomes. Rendered visual judgments and hash-bound receipts are separate from
automated QA.

From the repository root:

```bash
python3 scripts/python_runtime.py decks/v013-first-pass-20260929/build_evidence.py
python3 scripts/python_runtime.py decks/v013-first-pass-20260929/build_evidence.py --warm
```

`manifest.json` preserves every build attempt, source hashes, cache outcomes,
and the final runtime fingerprint. Earlier failures occurred during integration;
they are not hidden or described as successful first passes. Timings cover the
pipeline only, excluding authoring and model/human visual inspection.

The release download contains the four editable decks, their source, three full
contact sheets, and a compact overview. Cached renders are disposable local
outputs, not source or reusable visual approval.

## Pipeline Measurements

Measured locally. The cold builds used up to four concurrent deck jobs;
unchanged rebuilds used two. These are observations, not a controlled benchmark
or latency guarantee; authoring and visual-review time are excluded.

| Source | Slides | Uncached pipeline | Unchanged rebuild |
| --- | --- | --- | --- |
| Lab | 7 | 8.24 s | 3.08 s |
| Editorial | 6 | 7.98 s | 2.54 s |
| Operations | 7 | 6.95 s | 3.27 s |
| Retained Luna | 8 | 7.13 s | 2.56 s |

Recorded pairs are attempts 8/9 for lab and Luna, 14/15 for editorial, and 11/12
for operations. They have identical outline hashes, byte-identical PowerPoints,
and identical render cache keys. All four rebuilds report verified cache hits.
The original authoring notes and failed visual reviews remain historical records;
current judgments and bound receipts live under each case's `qa/` directory.
