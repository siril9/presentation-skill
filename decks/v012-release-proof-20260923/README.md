# v0.12 editable examples

Eight styles use the same synthetic urban-sensor topic, wording, data, and
16-point body-text floor. Each deck contains eight editable slides, a native
chart, and native tables. The separate `luna/` example was authored and repaired
by GPT-6 Luna, with source audit and independent visual review before inclusion.

Rebuild the controlled gallery from the repository root:

```bash
python3 scripts/python_runtime.py scripts/build_readable_style_gallery.py \
  --outdir /absolute/path/to/gallery --verify-rebuild
```

Build any included outline with `scripts/present.py finalize`. Review the new
renders before treating them as approved; the included receipts bind only the
published decks and their reviewed render hashes.

`manifest.json` records the automated build stage before visual approval.
Each deck's `visual_receipt.json` records the subsequent visual sign-off.

The repository keeps contact sheets, source outlines, and compact evidence.
The release ZIP additionally contains the editable PowerPoints. No source
research, imagery, or template assets from third-party slide decks are included.
