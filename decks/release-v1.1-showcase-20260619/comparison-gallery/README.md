# Presentation Skill v1.1 Release Gallery

This workspace is the saved authoring source for the `presentation-skill-v1-1-release-gallery` deck.

## Files

- `outline.json`: canonical structured slide source
- `content_plan.json`: thesis, audience, slide roles, and visual strategy
- `design_brief.json`: audience posture, cover concept, structure strategy, and grid policy
- `evidence_plan.json`: sourced claims, metrics, chart candidates, and gaps
- `style_contract.json`: stable style + layout contract for later slide additions
- `asset_plan.json`: source-backed imagery/background/chart staging plan
- `notes.md`: deck-specific data sources, decisions, and manual design notes
- `data/`: local datasets copied or linked for reproducible analysis
- `assets/data/`: smaller data extracts or tables staged with the deck
- `assets/figures/`: generated slide-ready figures
- `assets/charts/`: generated editable chart JSON specs
- `assets/`: local images, diagrams, logos, and tables used by the deck
- `build/`: generated `.pptx` output plus QA reports

## Commands

Emit the first-turn packet during initialization for reproducible intake and
design-contract handoff:

```bash
python3 ../../scripts/init_deck_workspace.py --workspace . --title "Presentation Skill v1.1 Release Gallery" --style-preset <preset> --user-prompt "Original user request"
```

Build the deck:

```bash
python3 ../../scripts/build_workspace.py --workspace . --overwrite
```

Build and run strict QA:

```bash
python3 ../../scripts/build_workspace.py --workspace . --qa --overwrite
```

Final reusable/report build with planning and whitespace gates:

```bash
python3 ../../scripts/build_workspace.py --workspace . --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite
```

Use non-render QA when LibreOffice is unavailable:

```bash
python3 ../../scripts/build_workspace.py --workspace . --qa --skip-render --overwrite
```

Build, scaffold local data artifacts, and run QA:

```bash
python3 ../../scripts/build_workspace.py --workspace . --scaffold-data-artifacts --auto-bind-artifacts --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite
```

Fail final polish on accidental dead whitespace:

```bash
python3 ../../scripts/build_workspace.py --workspace . --qa --fail-on-whitespace-warnings --overwrite
```

Allow Wikimedia Commons fetches while staging assets:

```bash
python3 ../../scripts/build_workspace.py --workspace . --allow-network-assets --overwrite
```

## Iteration Pattern

1. Fill `content_plan.json` with thesis, audience, slide roles, and visual strategy.
2. Fill `design_brief.json` with audience posture, cover concept, and structure strategy.
3. Fill `evidence_plan.json` with sourced claims, metrics, and chart candidates.
4. Update `notes.md` with data rules and unresolved assumptions.
5. Add source-backed image/background/chart requests to `asset_plan.json`.
6. Put local CSV/TSV/XLSX/JSON data in `data/` or `assets/data/`.
7. Run `python3 ../../scripts/build_workspace.py --workspace . --scaffold-data-artifacts --auto-bind-artifacts --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite`
   when a dataset should become a repeatable chart/figure artifact as part of the build, or run
   `python3 ../../scripts/scaffold_figure_artifacts.py --workspace . --run`
   when you want a separate scaffold/refine step.
8. Stage local assets inside `assets/` when needed.
9. Edit `outline.json` to add, replace, or reorder slides.
10. Reference staged assets with aliases such as `asset:hero_name`, `image:crew_portrait`, `chart:result_chart`, or `generated:concept_visual`.
11. Re-run `build_workspace.py`.
12. Before final delivery, run `python3 ../../scripts/build_workspace.py --workspace . --qa --fail-on-planning-warnings --fail-on-whitespace-warnings --overwrite`.
13. Keep the source files. Do not rely on inline heredoc generation if you want to extend the deck later.
