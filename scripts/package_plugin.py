#!/usr/bin/env python3
"""Export the synced, repository-bound skills-only plugin without uploading it."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / "plugins" / "presentation-skill"
MANIFEST = ".codex-plugin/plugin.json"
SKILL = "skills/presentation-skill"
MAX_BYTES = 10_000_000  # Repository budget, below the portal's 512 MiB limit.
MAX_ICON_BYTES = 5 * 1024 * 1024
STAMP = (1980, 1, 1, 0, 0, 0)
PRIVATE_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".env", ".ssh"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def text(value: object, name: str, limit: int, multiline: bool = False) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{name} must be non-empty text")
    require(len(value) <= limit, f"{name} exceeds {limit} characters")
    require(all(unicodedata.category(c) not in {"Cc", "Cf", "Zl", "Zp"}
                or (multiline and c == "\n") for c in value), f"{name} contains unsupported text")
    return value


def local_file(reference: str) -> Path:
    require(isinstance(reference, str) and reference.startswith("./"), "Asset paths must start with ./")
    relative = PurePosixPath(reference[2:])
    require(relative.parts and not relative.is_absolute() and ".." not in relative.parts
            and "\\" not in reference, f"Unsafe asset path: {reference}")
    path = PLUGIN / relative
    require(path.resolve().is_relative_to(PLUGIN.resolve()) and path.is_file(), f"Missing or external asset: {reference}")
    require(not any(parent.is_symlink() for parent in [path, *path.parents] if parent != REPO.parent),
            f"Symlink not allowed: {reference}")
    return path


def validate_icon(reference: str) -> Path:
    path = local_file(reference)
    require(path.is_relative_to(PLUGIN / "assets"), "Listing icons must live under assets/")
    require(path.suffix.lower() == ".svg", "This exporter validates the repository's SVG icons only")
    data = path.read_bytes()
    require(len(data) <= MAX_ICON_BYTES, "Icon exceeds 5 MiB")
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(), "SVG entities are not allowed")
    svg = ET.fromstring(data)
    require(svg.tag == "{http://www.w3.org/2000/svg}svg", "Invalid SVG root")
    if svg.get("width") is not None and svg.get("height") is not None:
        width, height = float(svg.get("width")), float(svg.get("height"))
    else:
        box = [float(v) for v in svg.get("viewBox", "").replace(",", " ").split()]
        require(len(box) == 4, "SVG requires numeric dimensions or viewBox")
        width, height = box[2:]
    require(math.isfinite(width) and math.isfinite(height) and width == height and width >= 48,
            "SVG icon must be square and at least 48 by 48")
    for element in svg.iter():
        require(element.tag.rsplit("}", 1)[-1] in {"svg", "title", "desc", "g", "rect", "path", "circle", "ellipse", "line", "polyline", "polygon"},
                "SVG must be self-contained, with no active or external content")
        require(not any(key.lower().startswith("on") or key.rsplit("}", 1)[-1] in {"href", "style"}
                        for key in element.attrib), "SVG active/external attributes are not allowed")
        require(not any("url(" in value.lower() for value in element.attrib.values()), "SVG external paint references are not allowed")
    return path


def export_manifest() -> tuple[dict, set[Path]]:
    source = local_file(f"./{MANIFEST}")
    manifest = json.loads(source.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "Manifest must be an object")
    require(not any(key in manifest for key in ("mcpServers", "apps", "$schema")),
            "Exporter accepts only the skills-only Codex compatibility manifest")
    name = text(manifest.get("name"), "name", 64)
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is not None, "Invalid package name")
    version = text(manifest.get("version"), "version", 64)
    require(re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version) is not None,
            "Expected an explicit release semantic version")
    text(manifest.get("description"), "description", 1024, multiline=True)
    author = manifest.get("author")
    require(isinstance(author, dict), "author must be an object")
    text(author.get("name"), "author.name", 120)
    require(manifest.get("skills") == "./skills/", "skills must declare ./skills/")
    interface = manifest.get("interface")
    require(isinstance(interface, dict), "interface must be an object")
    for name, limit in (("displayName", 30), ("shortDescription", 30),
                        ("longDescription", 4000), ("developerName", 80)):
        text(interface.get(name), name, limit, multiline=name == "longDescription")
    require(interface.get("category") == "Productivity", "Expected the supported Productivity category")
    capabilities = interface.get("capabilities")
    require(isinstance(capabilities, list) and len(capabilities) <= 20, "At most 20 capabilities required")
    for capability in capabilities:
        text(capability, "capability", 120)
    prompts = interface.get("defaultPrompt", [])
    if isinstance(prompts, str):
        prompts = [prompts]
    require(isinstance(prompts, list) and len(prompts) <= 3, "At most three starter prompts")
    normalized = []
    for prompt in prompts:
        text(prompt, "defaultPrompt", 128)
        require("@" not in prompt, "Starter prompts must not contain @mentions")
        normalized.append(" ".join(unicodedata.normalize("NFKC", prompt).split()))
    require(len(set(normalized)) == len(normalized), "Starter prompts must be unique")
    for obj, fields, limit in ((manifest, ["homepage", "repository"], 2048),
                               (author, ["url"], 2048),
                               (interface, ["websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL"], 1024)):
        for field in fields:
            if field in obj:
                value = text(obj[field], field, limit)
                url = urlsplit(value)
                require(url.scheme == "https" and bool(url.hostname) and url.username is None
                        and url.password is None and not any(c.isspace() for c in value), f"Invalid HTTPS URL: {field}")
    assets = {validate_icon(interface.get(field)) for field in ("logo", "composerIcon")}
    for field in ("logoDark", "composerIconDark"):
        if field in interface:
            assets.add(validate_icon(interface[field]))
    # Portal skills-only rules differ from the repository's local listing.
    interface.pop("screenshots", None)
    return manifest, assets


def checked_entries() -> tuple[dict[str, bytes], dict]:
    require(not PLUGIN.is_symlink(), "Plugin root must not be a symlink")
    manifest, icons = export_manifest()
    parity = subprocess.run([sys.executable, str(REPO / "scripts/sync_plugin_snapshot.py"), "--check"],
                            cwd=REPO, text=True, capture_output=True, check=False)
    require(parity.returncode == 0, "Snapshot parity failed; main must sync after workers freeze.\n" + parity.stdout + parity.stderr)
    skill_root = PLUGIN / SKILL
    require(not skill_root.is_symlink() and not (PLUGIN / "skills").is_symlink(), "Skill directories must not be symlinks")
    require((skill_root / "SKILL.md").is_file(), "At least one packaged skill is required")
    entries = {MANIFEST: (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")}
    files = list(skill_root.rglob("*")) + list(icons)
    seen = {MANIFEST.casefold()}
    for path in sorted(files):
        require(not path.is_symlink() and path.resolve().is_relative_to(PLUGIN.resolve()), f"External/symlink path: {path}")
        if path.is_dir():
            continue
        require(path.is_file(), f"Not a regular file: {path}")
        name = path.relative_to(PLUGIN).as_posix()
        parts = PurePosixPath(name).parts
        require(len(parts) <= 20 and all(p == p.strip() and p not in {".", ".."} for p in parts)
                and "\\" not in name, f"Unsafe archive path: {name}")
        require(not any(p.casefold() in PRIVATE_PARTS or p.casefold().startswith(".env.") for p in parts)
                and path.suffix.lower() not in {".pem", ".key", ".p12", ".pfx", ".pyc"}, f"Private/development file: {name}")
        key = unicodedata.normalize("NFKC", name).casefold()
        require(key not in seen, f"Normalized path collision: {name}")
        seen.add(key)
        require(path.stat().st_size <= MAX_BYTES, f"File exceeds lean budget: {name}")
        entries[name] = path.read_bytes()
    require(len(entries) <= 5000 and sum(map(len, entries.values())) <= MAX_BYTES, "Export exceeds lean 10 MB/5000-entry budget")
    return entries, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a public skills-only ZIP at this path")
    parser.add_argument("--check", action="store_true", help="Validate the export without writing a ZIP")
    args = parser.parse_args()
    if args.check == bool(args.output):
        parser.error("Choose exactly one of --output PATH or --check")
    try:
        entries, manifest = checked_entries()
        report = {"local_validation_passed": True, "scope": "public skills-only export; not portal approval",
                  "name": manifest["name"], "version": manifest["version"], "entry_count": len(entries),
                  "unpacked_bytes": sum(map(len, entries.values())), "omitted_manifest_fields": ["interface.screenshots"],
                  "included_root_assets": sorted(name for name in entries if name.startswith("assets/"))}
        if args.output:
            output = args.output.expanduser().resolve()
            require(not output.is_relative_to(REPO.resolve()), "ZIP output must be outside the repository")
            require(output.suffix.lower() == ".zip", "Output must have .zip extension")
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="plugin-package-", dir=output.parent) as temporary:
                candidate = Path(temporary) / "plugin.zip"
                with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                    for name, data in sorted(entries.items()):
                        info = zipfile.ZipInfo(name, STAMP)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFREG | 0o644) << 16
                        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
                with zipfile.ZipFile(candidate) as archive:
                    require(archive.testzip() is None, "ZIP integrity check failed")
                require(candidate.stat().st_size <= MAX_BYTES, "Compressed ZIP exceeds repository budget")
                report.update(zip_path=str(output), zip_bytes=candidate.stat().st_size,
                              sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
                candidate.replace(output)
        print(json.dumps(report, indent=2))
        return 0
    except (ValueError, OSError, ET.ParseError) as error:
        print(json.dumps({"local_validation_passed": False, "error": str(error)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
