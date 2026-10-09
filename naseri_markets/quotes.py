"""Typed, provider-neutral Bid/Ask ticks and a fail-closed quality boundary.

This module has no network access, private strategy logic or trade execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from .contracts import Instrument


class QuoteOrigin(StrEnum):
    LIVE = "live_provider"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"


class QuoteVerdict(StrEnum):
    ACCEPTED = "accepted"
    UNVERIFIED = "unverified_source"
    QUARANTINED = "quarantined"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    STALE = "stale"
    FUTURE = "future"
    SPREAD = "excessive_spread"


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class QuoteTick:
    instrument: Instrument
    occurred_at: datetime
    bid: Decimal
    ask: Decimal
    origin: QuoteOrigin

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument) or not isinstance(self.origin, QuoteOrigin):
            raise ValueError("typed instrument and origin required")
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        if any(
            not isinstance(x, Decimal) or not x.is_finite() or x <= 0
            for x in (self.bid, self.ask)
        ) or self.bid > self.ask:
            raise ValueError("invalid bid/ask quote")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True, slots=True)
class FeedPolicy:
    max_age_seconds: int = 10
    max_future_seconds: int = 1
    max_spread_fraction: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        if (
            not 0 < self.max_age_seconds <= 3600
            or not 0 <= self.max_future_seconds <= 60
            or not isinstance(self.max_spread_fraction, Decimal)
            or not self.max_spread_fraction.is_finite()
            or not Decimal("0") < self.max_spread_fraction <= Decimal("1")
        ):
            raise ValueError("invalid feed policy")


class QuoteQualityGate:
    """One independent watermark per provider/instrument; reset is explicit.

    Trusted means a separately authenticated source; an origin string is NOT
    evidence of that authentication. Replay and synthetic quotes cannot be
    marked as trusted forward ticks.
    """

    def __init__(self, policy: FeedPolicy | None = None) -> None:
        self.policy = policy or FeedPolicy()
        self._previous: dict[Instrument, QuoteTick] = {}
        self._quarantined: set[Instrument] = set()

    def inspect(self, tick: QuoteTick, *, now: datetime, trusted_live_source: bool = False
                ) -> QuoteVerdict:
        now_utc = _utc(now)
        instrument = tick.instrument
        if instrument in self._quarantined:
            return QuoteVerdict.QUARANTINED
        if tick.origin is QuoteOrigin.LIVE and not trusted_live_source:
            return QuoteVerdict.UNVERIFIED
        if tick.origin is not QuoteOrigin.LIVE and trusted_live_source:
            return QuoteVerdict.UNVERIFIED
        age = (now_utc - tick.occurred_at).total_seconds()
        if age > self.policy.max_age_seconds:
            self._quarantined.add(instrument)
            return QuoteVerdict.STALE
        if age < -self.policy.max_future_seconds:
            self._quarantined.add(instrument)
            return QuoteVerdict.FUTURE
        if tick.spread / tick.ask > self.policy.max_spread_fraction:
            self._quarantined.add(instrument)
            return QuoteVerdict.SPREAD
        previous = self._previous.get(instrument)
        if previous:
            if tick.occurred_at < previous.occurred_at:
                self._quarantined.add(instrument)
                return QuoteVerdict.OUT_OF_ORDER
            if tick == previous:
                return QuoteVerdict.DUPLICATE
        self._previous[instrument] = tick
        return QuoteVerdict.ACCEPTED

    def reset(self, instrument: Instrument) -> None:
        """Requires an operator/adapter-verified data resynchronization."""
        self._previous.pop(instrument, None)
        self._quarantined.discard(instrument)
