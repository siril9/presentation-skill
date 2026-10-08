#!/usr/bin/env python3
"""Validate the lean npm artifact and checked-in Codex plugin snapshot."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "presentation-skill"
MAX_PACKED_BYTES = 2_000_000
MAX_UNPACKED_BYTES = 8_000_000
MAX_PLUGIN_BYTES = 10_000_000
FORBIDDEN_PACKAGE_PARTS = (
    "__pycache__",
    "large_style_corpus_catalog.json",
    "large_style_corpus_catalog_enriched.json",
    "run_pptxgenjs_regression.py",
    "build_native_vs_latest_random_topic_decks.py",
    "build_release_showcase.py",
    "package_plugin.py",
    "sync_plugin_snapshot.py",
    "validate_distribution.py",
)
PRIVATE_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".env", ".ssh"}
HOST_HOME_PATH = re.compile(r"/(?:Users|home)/[\w.-]+/|[A-Za-z]:[\\/]+Users[\\/]+[\w.-]+[\\/]+")
RUNTIME_FILES = (
    "SKILL.md", "DESIGN.md", "scripts/present.py", "scripts/python_runtime.py",
    "scripts/runtime_doctor.py", "scripts/requirements-runtime.txt",
    "scripts/build_deck_pptxgenjs.js", "templates/pptxgenjs/slides.js",
)


def _surface_issues(root: Path, paths: list[str]) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {"development": [], "private": [], "host_specific_scripts": []}
    for name in sorted(paths):
        path = Path(name)
        if any(part in name for part in FORBIDDEN_PACKAGE_PARTS):
            issues["development"].append(name)
        if (any(part.casefold() in PRIVATE_PARTS or part.casefold().startswith(".env.")
                for part in path.parts)
                or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".pyc"}):
            issues["private"].append(name)
        # Historical source docs are evidence, not executable runtime requirements.
        if "scripts" in path.parts and path.suffix.lower() in {".py", ".js", ".mjs", ".sh"}:
            if HOST_HOME_PATH.search((root / path).read_text(encoding="utf-8")):
                issues["host_specific_scripts"].append(name)
    return issues


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def main() -> int:
    version = json.loads((ROOT / "package.json").read_text())["version"]
    discovery = json.loads((ROOT / "agents/discovery.json").read_text())
    completed = subprocess.run(
        ["npm", "pack", "--dry-run", "--json"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    records = json.loads(completed.stdout)
    package = records[0]
    paths = [str(item.get("path") or "") for item in package.get("files") or []]
    npm_issues = _surface_issues(ROOT, paths)
    plugin_paths = [path.relative_to(PLUGIN).as_posix() for path in PLUGIN.rglob("*") if path.is_file()]
    plugin_issues = _surface_issues(PLUGIN, plugin_paths)
    leaked = npm_issues["development"]
    required = [
        PLUGIN / ".codex-plugin" / "plugin.json",
        PLUGIN / "skills" / "presentation-skill" / "SKILL.md",
        PLUGIN / "skills" / "presentation-skill" / "agents" / "discovery.json",
        PLUGIN / "skills" / "presentation-skill" / "DISCOVERY.md",
        PLUGIN / "skills" / "presentation-skill" / "scripts" / "present.py",
        PLUGIN / "skills" / "presentation-skill" / "references" / "style_token_atlas.json",
        PLUGIN / "skills" / "presentation-skill" / "references" / "style_grammar_index.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    plugin_bytes = _tree_bytes(PLUGIN)
    failures = []
    for surface, issues in (("npm artifact", npm_issues), ("plugin snapshot", plugin_issues)):
        for category, found in issues.items():
            if found:
                failures.append(f"{surface} contains {category}: {found}")
    for name in RUNTIME_FILES:
        if name not in paths:
            failures.append(f"npm artifact is missing runtime file: {name}")
        if not (PLUGIN / "skills/presentation-skill" / name).is_file():
            failures.append(f"plugin snapshot is missing runtime file: {name}")
    if discovery.get("version") != version:
        failures.append("agent discovery metadata does not match the package version")
    plugin_manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text())
    if plugin_manifest.get("version") != version:
        failures.append("plugin listing does not match the package version")
    proof_prefix = discovery["repository"].rstrip("/") + "/blob/main/"
    for name, path in discovery.get("proof_assets", {}).items():
        if str(path).startswith(proof_prefix):
            path = path[len(proof_prefix):]
        elif str(path).startswith("https://"):
            continue
        candidate = (ROOT / path).resolve()
        if not candidate.is_relative_to(ROOT) or not candidate.is_file():
            failures.append(f"discovery proof asset is missing or outside the repository: {name}")
    for path in ("DISCOVERY.md", "agents/discovery.json"):
        if path not in paths:
            failures.append(f"npm artifact is missing discovery metadata: {path}")
    if int(package.get("size") or 0) > MAX_PACKED_BYTES:
        failures.append("npm artifact exceeds 2 MB compressed")
    if int(package.get("unpackedSize") or 0) > MAX_UNPACKED_BYTES:
        failures.append("npm artifact exceeds 8 MB unpacked")
    if plugin_bytes > MAX_PLUGIN_BYTES:
        failures.append("plugin snapshot exceeds 10 MB")
    if missing:
        failures.append(f"plugin snapshot is missing runtime files: {missing}")
    payload = {
        "passed": not failures,
        "npm_packed_bytes": package.get("size"),
        "npm_unpacked_bytes": package.get("unpackedSize"),
        "npm_entry_count": package.get("entryCount"),
        "plugin_bytes": plugin_bytes,
        "leaked_paths": leaked,
        "npm_surface_issues": npm_issues,
        "plugin_surface_issues": plugin_issues,
        "missing_plugin_files": missing,
        "failures": failures,
    }
    print(json.dumps(payload, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
