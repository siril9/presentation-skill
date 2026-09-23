#!/usr/bin/env python3
"""Refresh the Codex plugin skill snapshot from the repo-root skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO / "plugins" / "presentation-skill"
PLUGIN_SKILL_ROOT = PLUGIN_ROOT / "skills" / "presentation-skill"
PLUGIN_ASSETS = PLUGIN_ROOT / "assets"

FILES = [
    "SKILL.md",
    "DESIGN.md",
    "LICENSE",
    "package.json",
    "package-lock.json",
    "examples/outline.json",
    "agents/openai.yaml",
]

DIRECTORIES = [
    "references",
    "schemas",
    "scripts",
    "templates",
]

RUNTIME_EXCLUDES = {
    "large_style_corpus_catalog.json",
    "large_style_corpus_catalog_enriched.json",
    "large_style_corpus_catalog.md",
}

SCRIPT_DEVELOPMENT_ONLY = {
    "atomize_corpus.py",
    "enrich_corpus_structure.py",
    "enrich_corpus_vocabulary.py",
    "large_style_corpus.py",
    "run_focused_workflow_checks.py",
    "sync_plugin_snapshot.py",
    "validate_distribution.py",
}

SCREENSHOTS = {
    "v0.12_narrative_process.jpg": REPO / "examples/v0.12_narrative_process.jpg",
    "v0.12_evidence_decisions.jpg": REPO / "examples/v0.12_evidence_decisions.jpg",
    "v0.12_data_comparisons.jpg": REPO / "examples/v0.12_data_comparisons.jpg",
    "v0.11_monochrome_lab_ab.jpg": REPO / "examples/v0.11_monochrome_lab_ab.jpg",
    "v0.9_narrative_structures.jpg": REPO / "examples/v0.9_narrative_structures.jpg",
    "v0.9_evidence_data_structures.jpg": REPO / "examples/v0.9_evidence_data_structures.jpg",
    "v0.9_decisions_sources.jpg": REPO / "examples/v0.9_decisions_sources.jpg",
    "presentation_skill_variant_proof.png": REPO
    / "decks/native-vs-latest-random-topics-20260623/readme_images/presentation_skill_variant_proof.png",
    "presentation_skill_style_family_proof.png": REPO
    / "decks/native-vs-latest-random-topics-20260623/readme_images/presentation_skill_style_family_proof.png",
    "codex_native_vs_updated_clean_three_topics.png": REPO
    / "decks/native-vs-latest-random-topics-20260623/readme_images/codex_native_vs_updated_clean_three_topics.png",
}


def _ignore(_dir: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    in_scripts = Path(_dir).name == "scripts"
    for name in names:
        if name in {"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules"}:
            ignored.add(name)
        elif name in RUNTIME_EXCLUDES:
            ignored.add(name)
        elif in_scripts and (
            name in SCRIPT_DEVELOPMENT_ONLY
            or (name.startswith("run_") and (name.endswith("_smoke.py") or name.endswith("_smoke.js")))
            or name == "run_pptxgenjs_regression.py"
            or (
                name.startswith("build_")
                and any(token in name for token in ("showcase", "gallery", "comparison", "readme", "native_vs"))
            )
        ):
            ignored.add(name)
        elif name.endswith((".pyc", ".pyo", ".DS_Store")):
            ignored.add(name)
    return ignored


def _copy_file(relative_path: str, skill_root: Path = PLUGIN_SKILL_ROOT) -> None:
    src = REPO / relative_path
    if not src.is_file():
        raise FileNotFoundError(src)
    dst = skill_root / relative_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(relative_path: str, skill_root: Path = PLUGIN_SKILL_ROOT) -> None:
    src = REPO / relative_path
    if not src.is_dir():
        raise FileNotFoundError(src)
    dst = skill_root / relative_path
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore)


def _write_runtime_package_manifest(skill_root: Path = PLUGIN_SKILL_ROOT) -> None:
    package_path = skill_root / "package.json"
    payload = json.loads(package_path.read_text(encoding="utf-8"))
    payload["scripts"] = {
        "setup:python": "python3 scripts/runtime_doctor.py --bootstrap",
        "doctor": "python3 scripts/runtime_doctor.py",
        "check:runtime": "python3 scripts/runtime_doctor.py",
    }
    payload.pop("files", None)
    package_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sync_skill(skill_root: Path) -> None:
    if skill_root.exists():
        shutil.rmtree(skill_root)
    skill_root.mkdir(parents=True, exist_ok=True)

    for relative_path in FILES:
        _copy_file(relative_path, skill_root)
    for relative_path in DIRECTORIES:
        _copy_tree(relative_path, skill_root)
    _write_runtime_package_manifest(skill_root)


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _check_snapshot() -> int:
    with tempfile.TemporaryDirectory(prefix="presentation-skill-plugin-check-") as temporary:
        expected_root = Path(temporary) / "skill"
        _sync_skill(expected_root)
        expected = _tree_hashes(expected_root)
    actual = _tree_hashes(PLUGIN_SKILL_ROOT)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(path for path in set(expected).intersection(actual) if expected[path] != actual[path])
    asset_failures = [
        name
        for name, source in SCREENSHOTS.items()
        if not (PLUGIN_ASSETS / name).is_file()
        or hashlib.sha256(source.read_bytes()).digest()
        != hashlib.sha256((PLUGIN_ASSETS / name).read_bytes()).digest()
    ]
    payload = {
        "passed": not (missing or extra or changed or asset_failures),
        "missing": missing,
        "extra": extra,
        "changed": changed,
        "asset_failures": asset_failures,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify parity without writing the plugin snapshot.")
    args = parser.parse_args()
    if args.check:
        return _check_snapshot()

    _sync_skill(PLUGIN_SKILL_ROOT)

    PLUGIN_ASSETS.mkdir(parents=True, exist_ok=True)
    for name, src in SCREENSHOTS.items():
        if not src.is_file():
            raise FileNotFoundError(src)
        shutil.copy2(src, PLUGIN_ASSETS / name)

    print(f"Synced plugin snapshot: {PLUGIN_SKILL_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
