# Skill Development And Update Workflow

This file applies to maintainers and agents changing `presentation-skill`
itself. It is not part of the runtime instructions for ordinary deck creation.

## Major-Change Paired Comparison

For any major skill update, build two decks on the same task before closing the
task:

- Baseline output deck: generated with the published GitHub baseline.
- Updated output deck: generated with the current working tree.

Use the same prompt, same topic, same source data/assets, same requested slide
count, and same output constraints. Change only the skill version. This paired
output is the primary comparison.

Then create a short audit deck only if it helps review the paired outputs. The
audit deck is a summary artifact, not the comparison itself.

Required baseline checks:

```bash
git remote -v
git ls-remote origin HEAD
git rev-parse HEAD
git status --short
```

Required audit deck content:

- Published GitHub baseline commit and branch.
- Paired deck prompt/topic and paths to both output decks.
- Current working-tree scope, including modified and new files.
- Behavioral difference: what users/agents can do after the update that they
  could not do before.
- Rendered side-by-side screenshots or contact sheets from both output decks.
- QA metrics for both output decks.
- Validation commands and results.
- Issues discovered during audit and fixes applied.
- Residual risks or follow-up tests.

Recommended comparison workflow:

```bash
# 1. Build baseline in an isolated checkout/worktree at the published commit.
git worktree add /tmp/presentation-skill-baseline origin/main

# 2. Run the same deck task with baseline sources.
# Output should go under a clearly labeled baseline workspace.

# 3. Run the same deck task with the updated working tree.
# Output should go under a clearly labeled updated workspace.

# 4. Build an optional comparison/audit deck from rendered outputs and QA.
```

Required build and review for each paired deck and for any audit deck:

```bash
python3 scripts/build_workspace.py \
  --workspace decks/<workspace> \
  --qa \
  --overwrite

python3 scripts/visual_review.py \
  --input decks/<workspace>/build/<deck>.pptx \
  --outdir decks/<workspace>/build/qa/visual_review \
  --renders-dir decks/<workspace>/build/qa/renders \
  --outline decks/<workspace>/outline.json
```

Fix source issues found by QA or visual review before reporting completion.

## Best Comparison Method

Use three artifacts when time allows:

1. Baseline deck on the same prompt/topic.
2. Updated deck on the same prompt/topic.
3. Review deck that places rendered slides, contact sheets, QA metrics, and
   verdicts side by side.

The best test prompt is one that exercises the changed behavior. For example,
if the update changes lab routing, use the same ASCO/TB/LAMP assay prompt for
both deck builds. If the update changes editorial imagery, use the same
source-backed public explainer prompt. Avoid comparing unrelated demo decks.

## Scope

Use this workflow for skill-development changes such as:

- New or changed prompt emitters.
- New routing, QA, planning, or validation behavior.
- Major reference updates that change agent behavior.
- Renderer or layout-template changes.

Do not apply this workflow to normal user deck creation unless the user asks
for a comparison/audit deck.
