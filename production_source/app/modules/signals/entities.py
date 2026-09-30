"""Framework-independent signal commands and read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class SignalListMode(StrEnum):
    """Allow-listed public signal collections."""

    LIVE = "live"
    OPEN = "open"
    HISTORY = "history"


class AdminSignalListMode(StrEnum):
    """Allow-listed administrator signal collections."""

    ACTIVE = "active"
    HISTORY = "history"
    DRAFTS = "drafts"


@dataclass(frozen=True, slots=True)
class CreateSignal:
    """Validated by SignalService before persistence."""

    symbol: str
    direction: str
    entry_price: Decimal | str | int
    stop_loss: Decimal | str | int
    leverage: Decimal | str | int
    description: str | None = None
    as_draft: bool = False


@dataclass(frozen=True, slots=True)
class UpdateSignal:
    """Partial signal edit; null fields mean unchanged."""

    symbol: str | None = None
    direction: str | None = None
    entry_price: Decimal | str | int | None = None
    stop_loss: Decimal | str | int | None = None
    leverage: Decimal | str | int | None = None
    description: str | None = None
    clear_description: bool = False


@dataclass(frozen=True, slots=True)
class SignalRecord:
    id: int
    symbol: str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    leverage: Decimal
    status: str
    description: str | None
    profit_loss: Decimal | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True, slots=True)
class SignalTargetRecord:
    id: int
    signal_id: int
    target_number: int
    target_price: Decimal
    status: str
    hit_at: datetime | None
    profit_loss: Decimal | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SignalEventRecord:
    id: int
    signal_id: int
    event_type: str
    metadata: dict[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SignalPage:
    """One database-paginated public signal collection."""

    signals: tuple[SignalRecord, ...]
    mode: str
    page: int
    page_size: int
    total_items: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class SignalDetail:
    """One public signal with one page of ordered targets."""

    signal: SignalRecord
    targets: tuple[SignalTargetRecord, ...]
    target_page: int
    target_page_size: int
    total_targets: int
    total_target_pages: int


@dataclass(frozen=True, slots=True)
class AdminSignalPage:
    """One database-paginated administrator signal collection."""

    signals: tuple[SignalRecord, ...]
    mode: str
    page: int
    page_size: int
    total_items: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class AdminSignalDetail:
    """One administrator-visible signal with a page of targets."""

    signal: SignalRecord
    targets: tuple[SignalTargetRecord, ...]
    target_page: int
    target_page_size: int
    total_targets: int
    total_target_pages: int
