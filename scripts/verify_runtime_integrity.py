#!/usr/bin/env python3
"""Fail-closed source inventory for the legacy v0.3.2 Python runtime.

The frozen 359-file SHA256SUMS identity is immutable. Three historical public
cold-start modules have independent SHA-256 pins, not a rewritten manifest.
This is a CI/installation integrity check, NOT a signature or trusted boot.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SHA256 = "1a15f9d4b40b07c05186d27f694f9ce71cd007dd5047a35b25b6811f9bc67335"
FROZEN_ENTRIES = 359
PUBLIC_EXTRAS = {
    "app/modules/signal_intelligence/cold_start_integration.py":
        "0be746a515737316621742eda8142528f3c0d57fd6c7e29798323530cf4524be",
    "app/modules/signal_intelligence/cold_start_policy.py":
        "fa9425234f3bb654f536c842097b5190f73c92e350b00209af744debf3998038",
    "app/modules/signal_intelligence/cold_start_reporting.py":
        "2f373d1f68f708adb907f5b5b4497565cf8449b78eed0b73c9e4daf54d8b8bb3",
}
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class InventoryRefused(ValueError):
    """A source file is absent, unexpected, unsafe, or modified."""


def _canonical(name: str) -> bool:
    path = PurePosixPath(name)
    return (bool(name) and "\\" not in name and ":" not in name
            and path.as_posix() == name and not path.is_absolute()
            and all(part not in (".", "..") for part in name.split("/"))
            and not any(ord(ch) < 32 or ord(ch) == 127 for ch in name))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_runtime_integrity(source_root: Path) -> tuple[int, int]:
    root = Path(source_root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise InventoryRefused("INTEGRITY_SOURCE_ROOT_UNSAFE")
    manifest = root / "SHA256SUMS"
    if not manifest.is_file() or manifest.is_symlink():
        raise InventoryRefused("INTEGRITY_MANIFEST_MISSING")
    if _sha256(manifest) != MANIFEST_SHA256:
        raise InventoryRefused("INTEGRITY_FROZEN_MANIFEST_CHANGED")
    lines = manifest.read_text(encoding="utf-8").splitlines()
    if len(lines) != FROZEN_ENTRIES:
        raise InventoryRefused("INTEGRITY_MANIFEST_COUNT")
    names: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ", 1)
        if (len(parts) != 2 or not DIGEST.fullmatch(parts[0])
                or not _canonical(parts[1]) or parts[1] in names):
            raise InventoryRefused("INTEGRITY_MANIFEST_ENTRY_INVALID")
        names[parts[1]] = parts[0]

    overlap = set(names).intersection(PUBLIC_EXTRAS)
    if overlap:
        raise InventoryRefused("INTEGRITY_EXTRA_OVERLAPS_FROZEN")

    actual_python: set[str] = set()
    for directory, dirs, files in os.walk(root, topdown=True, followlinks=False):
        folder = Path(directory)
        for child in dirs + files:
            item = folder / child
            if item.is_symlink():
                raise InventoryRefused("INTEGRITY_SYMLINK_DENIED")
            if child in files and item.suffix == ".py":
                actual_python.add(item.relative_to(root).as_posix())
    approved_python = {name for name in names if name.endswith(".py")} | set(PUBLIC_EXTRAS)
    if actual_python != approved_python:
        raise InventoryRefused("INTEGRITY_PYTHON_INVENTORY_MISMATCH")

    for name, expected in names.items():
        file = root / name
        if not file.is_file() or file.is_symlink() or _sha256(file) != expected:
            raise InventoryRefused("INTEGRITY_FROZEN_FILE_CHANGED")
    for name, expected in PUBLIC_EXTRAS.items():
        file = root / name
        if not file.is_file() or file.is_symlink() or _sha256(file) != expected:
            raise InventoryRefused("INTEGRITY_PUBLIC_EXTRA_CHANGED")
    return len(names), len(PUBLIC_EXTRAS)


def main() -> int:
    try:
        frozen, extra = verify_runtime_integrity(ROOT / "production_source")
    except (InventoryRefused, OSError, UnicodeError, ValueError) as exc:
        print(f"RUNTIME_SOURCE_INTEGRITY_FAIL: {type(exc).__name__}: {exc}")
        return 1
    print(f"RUNTIME_SOURCE_INTEGRITY_PASS frozen={frozen} pinned_extras={extra} "
          f"python_inventory={frozen - 3 + extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
