# Three Synthetic Lab Studies

Three original eight-slide decks: a white calibration report, a dark signal
seminar, and an editorial sampling report. All numbers and scenarios are
invented and nonclinical. SYN-C, SYN-D and SYN-R identify local synthetic
sources, not papers or empirical findings. No private presentation material,
external slide assets or branding is included.

| Study | Preset / grammar | Argument |
| --- | --- | --- |
| `white_calibration` | lab-report / scientific-evidence-plate | Fit first, compare untouched residuals, then qualify a screening decision |
| `dark_contrast` | midnight-neon / technical-telemetry-canvas | Separate an oracle transformation from an earned explanation |
| `light_river_report` | editorial-minimal / editorial-spread | Separate an unsampled event from a claim of event absence |

The decks use four figure compositions, three editable native methods,
native charts and tables, and measured image sidebars. Figures remain images;
PowerPoint text, methods, charts and tables remain editable. Supported figure,
sidebar and method variants use explicit legacy-route fallbacks, not claimed
v2 role-slot execution. The model can choose these structures independently
of a fixed slide sequence.

## Preview And Evidence

[White](white_calibration_contact_sheet.jpg),
[dark](dark_contrast_contact_sheet.jpg), and
[editorial](light_river_report_contact_sheet.jpg) contact sheets show every
slide. The [release manifest](release_manifest.json) records the exact sources,
PPTX/render hashes, native objects and reviewed release artifacts. Source
validation is not rendered approval or factual verification. These are design
studies, not a comparison of models or evidence of generator superiority.

The [release ZIP](https://github.com/siril9/presentation-skill/releases/download/v0.14.0/presentation-skill-v0.14-lab-studies.zip)
contains all three editable decks and their source. The normal runtime does
not bundle this gallery or its plotting dependencies.

## Reproduce

From the repository root, with the core runtime installed:

```bash
python3 scripts/python_runtime.py examples/v0.14_lab_studies/generate_studies.py --check
python3 scripts/python_runtime.py examples/v0.14_lab_studies/validate_sources.py

python3 scripts/python_runtime.py scripts/present.py finalize \
  --outline examples/v0.14_lab_studies/white_calibration/outline.json \
  --output /tmp/lab-studies/white_calibration/deck.pptx \
  --qa-dir /tmp/lab-studies/white_calibration/qa
```

Repeat finalization for `dark_contrast` and `light_river_report`, then inspect
every full-sized slide. Create exact hash-bound visual receipts only after
that inspection. `build_proof.py --build-root /tmp/lab-studies --zip /tmp/lab-studies.zip`
requires clean finalization and current visual receipts before publishing
contact sheets, the showcase, two curated references and the archive.

`generate_studies.py` writes only data, plot images and their manifest, never
the authored outlines. To regenerate instead of checking, omit `--check`.
Standalone figure dependencies are pinned in `requirements.txt`: NumPy 2.5.1
and Matplotlib 3.11.0. Agg, bundled DejaVu Sans and independent PCG64 seeds
1401/1402/1403 produce repeatable same-runtime bytes. Different libraries,
fonts or platforms can change figure and Office output bytes.

## Interpret Carefully

- Calibration compares three inverse corrections on the same 30 synthetic
  holdout values after fitting 24 training values. One seeded split and invented
  AU thresholds are not physical calibration validation.
- Contrast retains 12 paired traces per condition, each with 11 time points.
  Oracle correction knows the injected drift law. No independent estimator or
  reference-channel experiment has been implemented.
- Sampling retains six values from each of the same 24 pulse realizations.
  Schedule B knows the authored pulse timing. Peak fraction is not sensitivity,
  pollutant load or a field observation.

Raw arrays, fits, residuals, paired changes and per-realization ratios remain
in each `data/synthetic_data.json`. Reproducibility does not validate the
invented conclusions or authorize clinical, environmental or deployment use.
