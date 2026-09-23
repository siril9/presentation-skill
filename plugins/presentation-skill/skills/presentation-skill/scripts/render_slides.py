#!/usr/bin/env python3
"""Render a PPTX using soffice (or unoserver) + pdftoppm.

Caching is opt-in via --cache or --cache-dir; --no-cache wins over both.
The default cache lives under XDG_CACHE_HOME (or ~/.cache), outside QA output.
Successful runs atomically write slide_render_report_v1 to OUTDIR/render_report.json
or --report. Consumers must require exit 0 and status=complete, then use images
(path/size/sha256), page_count, pptx_sha256, dpi, format, elapsed_seconds, and
cache.status (hit/miss/disabled/bypassed). This is render evidence, not a QA pass.
"""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from render_cache import SCHEMA, atomic_json, cache_key, file_hash, publish, restore


def _soffice_env() -> dict[str, str]:
    """Return an env dict for soffice/unoconvert subprocesses.

    Forces the "svp" (Server Virtual Plugin) backend so LibreOffice
    renders headlessly even in sandboxed environments without a display
    server. On macOS the default backend already works; setting this is
    harmless. On Linux sandboxes (CI, containers) the default backend
    can fail to initialize, so pinning to svp avoids silent render
    failures.
    """
    env = os.environ.copy()
    env.setdefault("SAL_USE_VCLPLUGIN", "svp")
    return env


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_soffice_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(command)
            + "\n"
            + (result.stderr.strip() or result.stdout.strip() or "No error output.")
        )


def _render_with_daemon_or_fallback(pptx_path: Path, out_dir: Path, *, isolated: bool = False) -> Path:
    """Convert a .pptx to PDF using unoserver (if available) or soffice.

    Tries ``unoconvert`` first (talks to a persistent LibreOffice daemon via
    ``unoserver``, ~1s per call). Falls back to ``soffice --headless --convert-to``
    (~10-15s per call due to LibreOffice startup cost).

    Returns the path to the resulting PDF inside ``out_dir``.
    Logs the chosen path and timing to stderr.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    expected_pdf = out_dir / f"{pptx_path.stem}.pdf"

    if not isolated and shutil.which("unoconvert"):
        t0 = time.perf_counter()
        result = subprocess.run(
            [
                "unoconvert",
                "--convert-to",
                "pdf",
                str(pptx_path),
                str(expected_pdf),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_soffice_env(),
        )
        elapsed = time.perf_counter() - t0
        if result.returncode == 0 and expected_pdf.exists():
            # Quiet — one-liner with timing only. Daemon path is the
            # expected fast path; no nagging banner.
            print(f"[render] PDF via unoserver in {elapsed:.2f}s", file=sys.stderr)
            return expected_pdf
        # Non-zero exit or missing artifact: log and fall through to soffice.
        err = (result.stderr.strip() or result.stdout.strip() or "no output")
        print(
            f"[render] unoconvert failed ({elapsed:.2f}s): {err}; "
            "falling back to soffice",
            file=sys.stderr,
        )
        # A failed daemon can leave a partial PDF that the fallback must not reuse.
        expected_pdf.unlink(missing_ok=True)

    t0 = time.perf_counter()
    _run(
        [
            "soffice",
            f"-env:UserInstallation={(out_dir / 'lo-profile').resolve().as_uri()}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx_path),
        ]
    )
    elapsed = time.perf_counter() - t0
    # Terse by default. Emit the "install unoserver" hint only on a truly
    # cold start (≥8s) — the usual case on first build after a reboot —
    # so repeated rapid rebuilds don't nag with the same line every run.
    if elapsed >= 8.0:
        print(
            f"[render] PDF via soffice in {elapsed:.2f}s — "
            "install unoserver for ~15x speedup "
            "(`pip install unoserver && unoserver &`)",
            file=sys.stderr,
        )
    else:
        print(f"[render] PDF via soffice in {elapsed:.2f}s", file=sys.stderr)
    if not expected_pdf.exists():
        raise FileNotFoundError(f"Expected converted PDF not found: {expected_pdf}")
    return expected_pdf


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a .pptx to individual slide images.")
    parser.add_argument("--input", required=True, help="Input .pptx path")
    parser.add_argument("--outdir", required=True, help="Directory for rendered slides")
    parser.add_argument("--dpi", type=int, default=150, help="Rendering DPI for pdftoppm")
    parser.add_argument("--format", choices=["jpeg", "png"], default="jpeg", help="Image format")
    parser.add_argument("--cache", action="store_true", help="Opt in to verified reusable slide renders")
    parser.add_argument("--cache-dir", help="Cache root outside the output directory (implies --cache)")
    parser.add_argument("--no-cache", action="store_true", help="Bypass all cache reads and writes")
    parser.add_argument("--report", help="JSON report path (default: OUTDIR/render_report.json)")
    parser.add_argument(
        "--emit-visual-prompt",
        action="store_true",
        help=(
            "After rendering, print the visual-QA subagent prompt with the "
            "rendered image paths substituted. Copy-paste the output into a "
            "fresh Explore agent to run the post-automated-QA inspection "
            "described in references/visual_qa_prompt.md."
        ),
    )
    return parser.parse_args()


_VISUAL_PROMPT_TEMPLATE = """\
Visually inspect these slides. Assume there are issues — find them.

Look for:
- Overlapping elements (text through shapes, lines through words, stacked elements)
- Text overflow or cut off at edges/box boundaries
- Decorative lines positioned for single-line text but the title wrapped to two lines
- Source citations or footers colliding with content above
- Elements too close (< 0.3" gaps) or cards/sections nearly touching
- Uneven gaps (large empty area in one place, cramped in another)
- Insufficient margin from slide edges (< 0.5")
- Columns or similar elements not aligned consistently
- Low-contrast text (e.g., light gray text on cream-colored background)
- Low-contrast icons (e.g., dark icons on dark backgrounds without a contrasting circle)
- Text boxes too narrow causing excessive wrapping
- Leftover placeholder content (Lorem, xxxx, "Prepared deck", etc.)
- AI-slide tells: thin accent rules directly under/over titles, all slides
  using the identical card-3-up layout, every palette key given equal
  weight instead of one dominant color

For each slide, list issues or areas of concern, even if minor.

Read and analyze these images:
{numbered_paths}

Report ALL issues found, including minor ones. Also note any slide that
feels derivative, templatey, or indistinguishable from other slides in the deck.
"""


def _emit_visual_prompt(jpg_paths: list[Path]) -> None:
    numbered = "\n".join(
        f"{i}. {p} (Expected: [fill in per-slide intent])"
        for i, p in enumerate(jpg_paths, start=1)
    )
    print()
    print("=" * 72)
    print("VISUAL QA SUBAGENT PROMPT (copy-paste the block below into an Explore agent)")
    print("=" * 72)
    print(_VISUAL_PROMPT_TEMPLATE.format(numbered_paths=numbered))
    print("=" * 72)


def _require_binary(name: str) -> None:
    if shutil.which(name):
        return
    raise RuntimeError(f"Required binary not found in PATH: {name}")


def _sort_key(path: Path, prefix: str) -> int:
    suffix = path.stem.replace(prefix, "").lstrip("-")
    try:
        return int(suffix)
    except ValueError:
        return 10**9


def _tool_identity(name: str, version_flag: str) -> dict:
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"Cannot identify converter: {name}")
    path = Path(resolved).resolve()
    digest = file_hash(path)
    result = subprocess.run(
        [str(path), version_flag], capture_output=True, text=True,
        env=_soffice_env(), timeout=15,
    )
    version = (result.stdout + result.stderr).strip()
    if result.returncode or not version or file_hash(path) != digest:
        raise RuntimeError(f"Cannot identify converter version: {name}")
    identity = {"path": str(path), "sha256": digest, "version": version}
    if name == "soffice":
        # Common launchers are scripts, not the actual LibreOffice executable.
        engines = [path.with_name("soffice.bin")]
        if sys.platform == "darwin":
            engines.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
        identity["engines"] = {str(p.resolve()): file_hash(p) for p in engines if p.is_file()}
    return identity


def _cache_inputs(input_path: Path, dpi: int, image_format: str) -> dict:
    # The local unoconvert client cannot attest the daemon's engine or font state.
    if shutil.which("unoconvert"):
        raise RuntimeError("unoconvert daemon identity is not verifiable")
    with zipfile.ZipFile(input_path) as package:
        for name in package.namelist():
            if name.endswith(".rels"):
                for relation in ET.fromstring(package.read(name)):
                    if (relation.get("TargetMode") == "External"
                            and not relation.get("Type", "").endswith("/hyperlink")):
                        raise RuntimeError("PPTX has external rendering dependencies")
    # Include installed font metadata, since unchanged converter versions can still
    # produce different output after font installation. Do not memoize across runs.
    font_roots = [Path(p).expanduser() for p in (
        "/System/Library/Fonts", "/Library/Fonts", "~/Library/Fonts",
        "/usr/share/fonts", "/usr/local/share/fonts", "~/.fonts",
        "~/.local/share/fonts", "/etc/fonts", "~/.config/fontconfig",
        "/Applications/LibreOffice.app/Contents/Resources/fonts",
        "/usr/lib/libreoffice/share/fonts", "/usr/lib64/libreoffice/share/fonts",
    )]
    fonts = []
    for root in font_roots:
        if root.exists():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    stat = path.stat()
                    fonts.append([str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns])
    return {
        "schema_version": SCHEMA,
        "pptx_sha256": file_hash(input_path), "dpi": dpi, "format": image_format,
        "tools": {name: _tool_identity(name, flag) for name, flag in (
            ("soffice", "--version"), ("pdftoppm", "-v"), ("pdfinfo", "-v"),
        )},
        "helpers": {name: file_hash(Path(__file__).resolve().with_name(name))
                    for name in ("render_slides.py", "render_cache.py")},
        "environment": {key: value for key, value in sorted(_soffice_env().items())
                        if key.startswith(("SAL_", "LC_", "FONTCONFIG", "XDG_"))
                        or key in ("LANG", "LANGUAGE", "TZ", "HOME")},
        "fonts": fonts,
    }


def _validate_images(pdf: Path, paths: list[Path], image_format: str) -> None:
    from PIL import Image

    result = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True,
        env={**_soffice_env(), "LC_ALL": "C"},
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if result.returncode or not match or len(paths) != int(match[1]) or not paths:
        raise RuntimeError("Incomplete render: image count does not match PDF pages")
    for index, path in enumerate(paths, 1):
        if _sort_key(path, "slide") != index:
            raise RuntimeError("Incomplete render: noncontiguous slide images")
        with Image.open(path) as image:
            if image.format != {"jpeg": "JPEG", "png": "PNG"}[image_format]:
                raise RuntimeError("Unexpected rendered image format")
            image.load()


def _fresh_render(input_path: Path, directory: Path, dpi: int, image_format: str, *, isolated: bool = False) -> list[Path]:
    from pptx import Presentation

    presentation = Presentation(input_path)
    expected_pages = sum(slide._element.get("show", "1") not in ("0", "false")
                         for slide in presentation.slides)
    pdf = _render_with_daemon_or_fallback(input_path, directory, isolated=isolated)
    _run(["pdftoppm", "-png" if image_format == "png" else "-jpeg", "-r", str(dpi),
          str(pdf), str(directory / "slide")])
    extension = ".png" if image_format == "png" else ".jpg"
    generated = sorted(directory.glob(f"slide-*{extension}"), key=lambda p: _sort_key(p, "slide"))
    if len(generated) != expected_pages:
        raise RuntimeError("Incomplete render: image count does not match visible PPTX slides")
    _validate_images(pdf, generated, image_format)
    # Normalize into a separate directory to avoid collisions with Poppler numbering.
    normalized = directory / "normalized"
    normalized.mkdir()
    paths = []
    for index, source in enumerate(generated, 1):
        target = normalized / f"slide-{index:02d}{extension}"
        shutil.move(source, target)
        paths.append(target)
    return paths


def main() -> int:
    started = time.perf_counter()
    args = _args()
    input_path = Path(args.input).expanduser().resolve()
    outdir = Path(args.outdir).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if args.dpi <= 0:
        raise ValueError("DPI must be positive")

    # unoconvert is optional (preferred); soffice is the fallback.
    if not shutil.which("unoconvert"):
        _require_binary("soffice")
    _require_binary("pdftoppm")
    _require_binary("pdfinfo")

    outdir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report).expanduser().resolve() if args.report else outdir / "render_report.json"
    if report_path == input_path or re.fullmatch(r"slide-\d+\.(jpg|jpeg|png)", report_path.name):
        raise ValueError("Report path must not overwrite the input or slide images")
    report_path.unlink(missing_ok=True)
    if report_path != outdir / "render_report.json":
        (outdir / "render_report.json").unlink(missing_ok=True)
    cache_root = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else (
        Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
        / "presentation-skill" / "renders-v1"
    ).resolve()
    enabled = (args.cache or bool(args.cache_dir)) and not args.no_cache
    if enabled and (cache_root == outdir or outdir in cache_root.parents
                    or cache_root in outdir.parents):
        raise ValueError("Cache and output directories must be separate, non-nested locations")
    status, reason, key = "disabled", "not_requested", None
    if args.no_cache:
        reason = "no_cache"
    source_hash = file_hash(input_path)
    extension = ".png" if args.format == "png" else ".jpg"
    with ExitStack() as stack:
        tmp_path = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="pptx-render-")))
        inputs = None
        if enabled:
            try:
                import fcntl

                inputs = _cache_inputs(input_path, args.dpi, args.format)
                if inputs["pptx_sha256"] != source_hash:
                    raise RuntimeError("Input changed before cache lookup")
                key = cache_key(inputs)
                cache_root.mkdir(parents=True, exist_ok=True)
                lock = stack.enter_context((cache_root / f"{key}.lock").open("a"))
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                status, reason = "miss", "absent_or_invalid"
            except (OSError, RuntimeError, ImportError, subprocess.TimeoutExpired, zipfile.BadZipFile, ET.ParseError) as exc:
                inputs = None
                status, reason = "bypassed", str(exc)
        restored = tmp_path / "restored"
        restored.mkdir()
        paths = restore(cache_root / key, inputs, restored, extension) if inputs else None
        if paths:
            status, reason = "hit", "verified"
        else:
            fresh = tmp_path / "fresh"
            fresh.mkdir()
            render_input = input_path
            if inputs:
                render_input = tmp_path / "input.pptx"
                shutil.copyfile(input_path, render_input)
                if file_hash(render_input) != source_hash:
                    raise RuntimeError("Input changed while creating render snapshot")
            paths = _fresh_render(render_input, fresh, args.dpi, args.format, isolated=bool(inputs))
            if file_hash(input_path) != source_hash:
                raise RuntimeError("Input changed during rendering")
            if inputs:
                if _cache_inputs(input_path, args.dpi, args.format) != inputs:
                    raise RuntimeError("Rendering dependencies changed during conversion")
                try:
                    publish(cache_root / key, inputs, paths)
                except OSError as exc:
                    reason = f"cache_write_failed: {exc}"
        if file_hash(input_path) != source_hash:
            raise RuntimeError("Input changed before publishing renders")
        if inputs and status == "hit" and _cache_inputs(input_path, args.dpi, args.format) != inputs:
            raise RuntimeError("Rendering dependencies changed during cache lookup")
        # Stage on the destination filesystem, then replace only managed images.
        # The report is the completion marker; consumers must also require exit 0.
        with tempfile.TemporaryDirectory(prefix=".render-stage-", dir=outdir) as stage:
            staged = []
            for source in paths:
                target = Path(stage) / source.name
                shutil.copyfile(source, target)
                staged.append(target)
            for pattern in ("slide-*.jpg", "slide-*.jpeg", "slide-*.png"):
                for stale in outdir.glob(pattern):
                    stale.unlink()
            final_paths = []
            for source in staged:
                target = outdir / source.name
                os.replace(source, target)
                final_paths.append(target)
        report = {
            "schema_version": "slide_render_report_v1", "status": "complete",
            "input": str(input_path), "pptx_sha256": source_hash,
            "dpi": args.dpi, "format": args.format, "page_count": len(final_paths),
            "cache": {"status": status, "reason": reason, "key": key,
                      "directory": str(cache_root) if enabled else None},
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "images": [{"path": str(p), "size": p.stat().st_size, "sha256": file_hash(p)}
                       for p in final_paths],
        }
        atomic_json(report_path, report)

    print(f"[render] cache {status}: {reason}", file=sys.stderr)
    print(f"Rendered {len(final_paths)} slide image(s) to {outdir}")
    if args.emit_visual_prompt:
        _emit_visual_prompt(final_paths)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Error: {exc}")
        raise SystemExit(1)
