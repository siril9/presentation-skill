#!/usr/bin/env python3
"""Stable content hashes for Office Open XML packages."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path


OFFICE_PACKAGE_SUFFIXES = {".docx", ".pptx", ".potx", ".ppsx", ".xlsx", ".xlsm"}
OFFICE_PACKAGE_HASH_ALGORITHM = "office_package_normalized_v1"
_CORE_TIMESTAMP_RE = re.compile(
    rb"(<dcterms:(created|modified)\b[^>]*>)[^<]*(</dcterms:\2>)"
)
_NORMALIZED_TIMESTAMP = b"1970-01-01T00:00:00Z"


def is_office_package_path(path: Path) -> bool:
    return path.suffix.lower() in OFFICE_PACKAGE_SUFFIXES


def _normalize_core_properties(data: bytes) -> bytes:
    return _CORE_TIMESTAMP_RE.sub(
        lambda match: match.group(1) + _NORMALIZED_TIMESTAMP + match.group(3),
        data,
    )


def _normalized_zip_sha256(data: bytes) -> str:
    digest = hashlib.sha256()
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        for name in sorted(package.namelist()):
            if name.endswith("/"):
                continue
            payload = package.read(name)
            if name == "docProps/core.xml":
                payload = _normalize_core_properties(payload)
            elif Path(name).suffix.lower() in OFFICE_PACKAGE_SUFFIXES:
                payload = _normalized_zip_sha256(payload).encode("ascii")
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(payload)
            digest.update(b"\0")
    return digest.hexdigest()


def office_package_normalized_sha256(path: Path) -> str:
    return _normalized_zip_sha256(path.read_bytes())
