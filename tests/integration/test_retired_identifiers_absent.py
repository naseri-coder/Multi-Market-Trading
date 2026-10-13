"""Fail closed if a retired trading-engine name returns to current source."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".ini", ".sh", ".json", ".txt"}
OLD_SHORT_NAME = "".join(("F", "M"))
OLD_CLASS_NAME = "".join(("Dual", "Setup", "Example", "Core"))
OLD_MODULE_NAME = "".join(("example", "_", "dual", "_", "setup", "_core", "_v1"))


def test_retired_engine_names_absent_from_working_tree() -> None:
    bad: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if any(piece.startswith(".") for piece in rel.parts) and ".github" not in rel.parts:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        data = path.read_text(encoding="utf-8")
        if (re.search(r"(?i)(?<![a-z0-9])" + OLD_SHORT_NAME
                      + r"(?=$|[^a-z0-9])", data)
                or OLD_CLASS_NAME in data or OLD_MODULE_NAME in data):
            bad.append(str(rel))
    assert not bad, "Retired engine name detected: " + repr(sorted(bad))
