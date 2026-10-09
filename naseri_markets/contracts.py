"""Public multi-market contracts. No strategy formulas or broker credentials live here."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{1,79}$")


class Market(StrEnum):
    CRYPTO = "crypto"
    FOREX = "forex"
    INDEX = "index"
    METAL = "metal"


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"


class EvidenceMode(StrEnum):
    HISTORICAL = "historical"
    PAPER = "paper"
    FORWARD = "forward"


@dataclass(frozen=True, slots=True)
class Instrument:
    """Canonical identity. A symbol alone is never globally unique."""

    market: Market
    provider: str
    symbol: str
    timezone: str
    quote_currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market):
            raise ValueError("market must be a registered market class")
        if not self.provider.strip() or not self.symbol.strip():
            raise ValueError("provider and symbol are required")
        if not self.quote_currency.strip():
            raise ValueError("quote currency is required")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError("valid IANA timezone is required") from exc


@dataclass(frozen=True, slots=True)
class EngineDescriptor:
    engine_id: str
    version: str
    supported_markets: frozenset[Market]

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.engine_id):
            raise ValueError("invalid engine_id")
        if not self.version.strip():
            raise ValueError("engine version is required")
        if not self.supported_markets or any(
            not isinstance(market, Market) for market in self.supported_markets
        ):
            raise ValueError("nonempty supported market set is required")


@dataclass(frozen=True, slots=True)
class SignalIntent:
    """Observed proposal; never a filled trade or permission to place an order."""

    signal_id: str
    engine_id: str
    engine_version: str
    instrument: Instrument
    direction: Direction
    observed_at: datetime
    entry: Decimal
    stop: Decimal
    targets: tuple[Decimal, ...]
    evidence_mode: EvidenceMode

    def __post_init__(self) -> None:
        if not self.signal_id.strip():
            raise ValueError("signal identity required")
        if not _ID.fullmatch(self.engine_id) or not self.engine_version.strip():
            raise ValueError("valid engine identity required")
        if not isinstance(self.direction, Direction):
            raise ValueError("invalid signal direction")
        if not isinstance(self.evidence_mode, EvidenceMode):
            raise ValueError("invalid evidence mode")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("timestamp must be timezone aware")
        values = (self.entry, self.stop, *self.targets)
        if not self.targets or any(
            not isinstance(value, Decimal) or not value.is_finite() or value <= 0
            for value in values
        ):
            raise ValueError("positive finite Decimal prices required")
        if self.direction is Direction.LONG and (
            self.stop >= self.entry or any(target <= self.entry for target in self.targets)
        ):
            raise ValueError("invalid long risk/target geometry")
        if self.direction is Direction.SHORT and (
            self.stop <= self.entry or any(target >= self.entry for target in self.targets)
        ):
            raise ValueError("invalid short risk/target geometry")
