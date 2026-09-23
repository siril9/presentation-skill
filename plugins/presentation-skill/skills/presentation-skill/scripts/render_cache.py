"""Content-checked, atomically published slide cache (no QA verdicts are cached)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


SCHEMA = "slide_render_cache_v1"


def file_hash(path: Path) -> str:
    """Hash bytes, rejecting files replaced or modified during the read."""
    def signature(stat: os.stat_result) -> tuple[int, ...]:
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before = signature(os.fstat(handle.fileno()))
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        if before != signature(os.fstat(handle.fileno())) or before != signature(path.stat()):
            raise RuntimeError(f"File changed while hashing: {path}")
    return digest.hexdigest()


def cache_key(inputs: dict) -> str:
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore(entry: Path, inputs: dict, destination: Path, extension: str) -> list[Path] | None:
    """Validate copied bytes, never exposing an incomplete hit to the output dir."""
    copied: list[Path] = []
    try:
        if entry.is_symlink():
            return None
        manifest = json.loads((entry / "manifest.json").read_text(encoding="utf-8"))
        if manifest["schema_version"] != SCHEMA or manifest["inputs"] != inputs:
            return None
        files = manifest["files"]
        if not files or len(files) != manifest["page_count"]:
            return None
        expected_names = {f"slide-{i:02d}{extension}" for i in range(1, len(files) + 1)}
        if {p.name for p in entry.iterdir()} != expected_names | {"manifest.json"}:
            return None
        for index, record in enumerate(files, 1):
            name = f"slide-{index:02d}{extension}"
            source = entry / name
            if record["name"] != name or source.is_symlink() or source.stat().st_size != record["size"]:
                return None
            target = destination / name
            copied.append(target)
            shutil.copyfile(source, target)
            if target.stat().st_size <= 0 or file_hash(target) != record["sha256"]:
                return None
        return copied
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return None


def publish(entry: Path, inputs: dict, paths: list[Path]) -> None:
    """Publish a complete generation. Call under the per-key lock."""
    with tempfile.TemporaryDirectory(prefix=".render-stage-", dir=entry.parent) as temporary:
        stage = Path(temporary) / "entry"
        stage.mkdir()
        records = []
        for source in paths:
            target = stage / source.name
            shutil.copyfile(source, target)
            with target.open("rb") as handle:
                os.fsync(handle.fileno())
            records.append({"name": target.name, "size": target.stat().st_size, "sha256": file_hash(target)})
        atomic_json(stage / "manifest.json", {
            "schema_version": SCHEMA, "inputs": inputs, "page_count": len(paths), "files": records,
        })
        # Invalid generations are removed only while holding the same lock as readers.
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.exists():
            shutil.rmtree(entry)
        os.replace(stage, entry)
