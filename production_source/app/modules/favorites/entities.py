"""Framework-independent favorites commands and read models."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.signals.entities import SignalRecord


@dataclass(frozen=True, slots=True)
class FavoriteMutation:
    """Idempotent favorite state returned after add or remove."""

    signal_id: int
    is_favorite: bool
    changed: bool


@dataclass(frozen=True, slots=True)
class FavoritePage:
    """One database-paginated user favorites collection."""

    signals: tuple[SignalRecord, ...]
    page: int
    page_size: int
    total_items: int
    total_pages: int
