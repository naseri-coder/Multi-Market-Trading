"""Stage 6: immutable research-only instrument catalog (never trading approval).

The platform chooses providers/instruments. No strategy code, sockets,
credentials, persistence, Telegram or order APIs occur in this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import Instrument, Market
from .core_api_v1 import content_digest

_PROVIDER = re.compile(r"[a-z][a-z0-9_]{2,47}\Z")
_SYMBOL = re.compile(r"[A-Za-z0-9_.-]{3,64}\Z")
_CURRENCY = re.compile(r"[A-Z0-9]{2,12}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class CatalogRefused(ValueError):
    """Untrusted or stale metadata must not be promoted into market settings."""


class MetadataOrigin(StrEnum):
    PUBLIC_CONTRACT_RESEARCH = "public_contract_research"
    MT5_DEMO_OBSERVATION = "mt5_demo_observation"


class ListingStatus(StrEnum):
    OPEN = "open"
    HALTED = "halted"
    UNKNOWN = "unknown"


def _price(n: Decimal | None, name: str) -> None:
    if n is not None and (type(n) is not Decimal or not n.is_finite() or n <= 0):
        raise CatalogRefused(f"INVALID_{name}")


def _time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CatalogRefused("TIMESTAMP_MUST_BE_AWARE")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class InstrumentMetadata:
    provider: str
    market: Market
    symbol: str
    timezone: str
    quote_currency: str
    price_tick_size: Decimal
    origin: MetadataOrigin
    listing_status: ListingStatus
    observed_at: datetime
    contract_kind: str
    quantity_step: Decimal | None = None
    contract_multiplier: Decimal | None = None

    def __post_init__(self) -> None:
        if (type(self.provider) is not str or not _PROVIDER.fullmatch(self.provider)
                or type(self.symbol) is not str or not _SYMBOL.fullmatch(self.symbol)
                or type(self.quote_currency) is not str
                or not _CURRENCY.fullmatch(self.quote_currency)
                or type(self.contract_kind) is not str
                or not 1 <= len(self.contract_kind) <= 48
                or not isinstance(self.market, Market) or not isinstance(self.origin, MetadataOrigin)
                or not isinstance(self.listing_status, ListingStatus)):
            raise CatalogRefused("INVALID_INSTRUMENT_METADATA")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise CatalogRefused("INVALID_MARKET_TIMEZONE") from exc
        _price(self.price_tick_size, "PRICE_TICK")
        if self.price_tick_size is None:
            raise CatalogRefused("PRICE_TICK_REQUIRED")
        _price(self.quantity_step, "QUANTITY_STEP")
        _price(self.contract_multiplier, "CONTRACT_MULTIPLIER")
        object.__setattr__(self, "observed_at", _time(self.observed_at))

    @property
    def instrument(self) -> Instrument:
        return Instrument(self.market, self.provider, self.symbol,
                          self.timezone, self.quote_currency)

    @property
    def trading_authorized(self) -> bool:
        return False

    @property
    def paper_signal_authorized(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ProviderSnapshot:
    """Atomic observation for precisely one provider."""

    provider: str
    origin: MetadataOrigin
    observed_at: datetime
    instruments: tuple[InstrumentMetadata, ...]
    raw_sha256: str

    def __post_init__(self) -> None:
        if type(self.provider) is not str or not _PROVIDER.fullmatch(self.provider):
            raise CatalogRefused("INVALID_PROVIDER")
        if not isinstance(self.origin, MetadataOrigin):
            raise CatalogRefused("INVALID_ORIGIN")
        object.__setattr__(self, "observed_at", _time(self.observed_at))
        if type(self.instruments) is not tuple or not 0 < len(self.instruments) <= 4000:
            raise CatalogRefused("INVALID_SNAPSHOT_SIZE")
        if type(self.raw_sha256) is not str or not _SHA.fullmatch(self.raw_sha256):
            raise CatalogRefused("INVALID_RAW_HASH")
        keys: set[str] = set()
        for entry in self.instruments:
            if (not isinstance(entry, InstrumentMetadata)
                    or entry.provider != self.provider or entry.origin is not self.origin
                    or entry.observed_at != self.observed_at or entry.symbol in keys):
                raise CatalogRefused("MIXED_OR_DUPLICATE_SNAPSHOT")
            keys.add(entry.symbol)

    @property
    def content_hash(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class CatalogReceipt:
    provider: str
    revision: int
    idempotent: bool
    instrument_count: int
    source_digest: str


class ResearchInstrumentCatalog:
    """Atomic memory-only research snapshot store, not venue authorization."""

    def __init__(self, *, max_age_seconds: int = 3600) -> None:
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 86400:
            raise CatalogRefused("INVALID_MAX_AGE")
        self.max_age_seconds = max_age_seconds
        self._snapshots: dict[str, ProviderSnapshot] = {}
        self._revisions: dict[str, int] = {}

    def replace(self, snapshot: ProviderSnapshot) -> CatalogReceipt:
        if not isinstance(snapshot, ProviderSnapshot):
            raise CatalogRefused("INVALID_SNAPSHOT")
        current = self._snapshots.get(snapshot.provider)
        if current is not None:
            if snapshot.observed_at < current.observed_at:
                raise CatalogRefused("SNAPSHOT_TIME_ROLLBACK")
            if snapshot.observed_at == current.observed_at:
                if current.content_hash != snapshot.content_hash:
                    raise CatalogRefused("CONFLICTING_SAME_TIME_SNAPSHOT")
                return CatalogReceipt(snapshot.provider, self._revisions[snapshot.provider],
                                      True, len(snapshot.instruments), snapshot.raw_sha256)
        revision = self._revisions.get(snapshot.provider, 0) + 1
        self._snapshots[snapshot.provider] = snapshot
        self._revisions[snapshot.provider] = revision
        return CatalogReceipt(snapshot.provider, revision, False,
                              len(snapshot.instruments), snapshot.raw_sha256)

    def lookup(self, provider: str, symbol: str, *, now: datetime) -> InstrumentMetadata:
        if type(provider) is not str or type(symbol) is not str:
            raise CatalogRefused("UNKNOWN_PROVIDER_OR_SYMBOL")
        snapshot = self._snapshots.get(provider)
        if snapshot is None:
            raise CatalogRefused("UNKNOWN_PROVIDER_OR_SYMBOL")
        age = _time(now) - snapshot.observed_at
        if age < timedelta(0) or age > timedelta(seconds=self.max_age_seconds):
            raise CatalogRefused("METADATA_STALE_OR_FUTURE")
        for record in snapshot.instruments:
            if record.symbol == symbol:
                return record
        raise CatalogRefused("UNKNOWN_PROVIDER_OR_SYMBOL")

    def research_instruments(
        self, provider: str, *, now: datetime
    ) -> tuple[InstrumentMetadata, ...]:
        snapshot = self._snapshots.get(provider)
        if snapshot is None:
            raise CatalogRefused("UNKNOWN_PROVIDER")
        self.lookup(provider, snapshot.instruments[0].symbol, now=now)
        return snapshot.instruments

    def refuse_trading_binding(self, *_args: object, **_kwargs: object) -> None:
        raise CatalogRefused("METADATA_NEVER_TRADING_AUTHORIZATION")


__all__ = ["CatalogRefused", "CatalogReceipt", "InstrumentMetadata",
           "ListingStatus", "MetadataOrigin", "ProviderSnapshot",
           "ResearchInstrumentCatalog"]
