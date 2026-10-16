"""Static contract for the phase 4 signal-delivery migration.

The file paths are resolved relative to the repository root (and fall back to
the frozen ``production_source/`` tree when the materialized release layout is
absent) so that a fresh ``git clone`` can collect and run the corpus without a
manual ``cp -a production_source/app ./app`` step first.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _frozen_text(relative: str) -> str:
    for base in (ROOT, ROOT / "production_source"):
        candidate = base / relative
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise AssertionError(f"frozen migration file not found: {relative}")


text = _frozen_text(
    "migrations/versions/20260902_0013_create_signal_delivery_tracking.py"
)

assert 'revision: str = "20260902_0013"' in text
assert 'down_revision: str | None = "20260902_0012"' in text
assert '"signal_deliveries"' in text
assert "uq_signal_deliveries_signal_destination" in text
assert "'AMBIGUOUS'" in text
assert 'ondelete="CASCADE"' in text
