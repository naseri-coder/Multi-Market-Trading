"""Framework-independent MARC core entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

MARC_ENGINE_VERSION = "marc-core-v0.1.0"
MARC_RULE_SET_VERSION = "marc-r1-v0.1"
MARC_CONFIGURATION_VERSION = "marc-baseline-v0.1"
MARC_SETUP_TYPE = "MARC_R1_MA99_REGIME_RECLAIM"
MARC_EXIT_MODEL = "TP1_1R_TP2_2R_RUNNER_CHANDELIER_22_3ATR"


class MARCState(StrEnum):
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NEUTRAL = "NEUTRAL"
    BULL_CROSS_DETECTED = "BULL_CROSS_DETECTED"
    BEAR_CROSS_DETECTED = "BEAR_CROSS_DETECTED"
    WAITING_FOR_MA99_RECLAIM = "WAITING_FOR_MA99_RECLAIM"
    WAITING_FOR_MA99_BREAKDOWN = "WAITING_FOR_MA99_BREAKDOWN"
    PERSISTENCE_CONFIRMING = "PERSISTENCE_CONFIRMING"
    LONG_READY = "LONG_READY"
    SHORT_READY = "SHORT_READY"
    INVALIDATED_FALSE_BREAK = "INVALIDATED_FALSE_BREAK"
    NO_TRADE_CHOP = "NO_TRADE_CHOP"
    NO_TRADE_COMPRESSION = "NO_TRADE_COMPRESSION"
    NO_TRADE_OVEREXTENDED = "NO_TRADE_OVEREXTENDED"
    SETUP_EXPIRED = "SETUP_EXPIRED"


@dataclass(frozen=True, slots=True)
class MARCIndicatorFrame:
    index: int
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    ma7: Decimal | None
    ma25: Decimal | None
    ma99: Decimal | None
    atr14: Decimal | None


@dataclass(frozen=True, slots=True)
class MARCDecision:
    symbol: str
    timeframe: str
    state: MARCState
    direction: str | None
    snapshot_id: str
    snapshot_hash: str
    cross_index: int | None
    confirmation_index: int | None
    persistence_count: int
    ma7: Decimal | None
    ma25: Decimal | None
    ma99: Decimal | None
    atr14: Decimal | None
    normalized_spread_atr: Decimal | None
    extension_atr: Decimal | None
    fresh: bool
    reason: str

    @property
    def trade_ready(self) -> bool:
        return self.state in {MARCState.LONG_READY, MARCState.SHORT_READY}


@dataclass(frozen=True, slots=True)
class MARCCandidate:
    """Backtest-ready MARC entry candidate, independent from Brooks contracts."""

    source_signal_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    targets: tuple[Decimal, Decimal]
    exchange: str
    market_type: str
    setup_type: str
    market_snapshot_id: str
    market_snapshot_hash: str
    engine_version: str
    rule_set_version: str
    configuration_version: str
    confirmation_close_time: datetime
    ma99: Decimal
    atr14: Decimal
    initial_risk_atr: Decimal
    risk_fraction: Decimal
    exit_model: str
    reasoning: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.direction not in {"LONG", "SHORT"}:
            raise ValueError("MARC candidate direction must be LONG or SHORT")
        if self.entry_price <= 0 or self.stop_loss <= 0:
            raise ValueError("MARC candidate prices must be positive")
        if any(target <= 0 for target in self.targets):
            raise ValueError("MARC candidate targets must be positive")
        if self.direction == "LONG" and not self.stop_loss < self.entry_price:
            raise ValueError("LONG stop must be below entry")
        if self.direction == "SHORT" and not self.stop_loss > self.entry_price:
            raise ValueError("SHORT stop must be above entry")
        if self.initial_risk_atr <= 0:
            raise ValueError("initial_risk_atr must be positive")


@dataclass(frozen=True, slots=True)
class MARCEntryPlan:
    accepted: bool
    candidate: MARCCandidate | None
    rejection_reason: str | None

    def __post_init__(self) -> None:
        if self.accepted != (self.candidate is not None):
            raise ValueError("accepted must match candidate presence")
        if self.accepted and self.rejection_reason is not None:
            raise ValueError("accepted plan cannot carry a rejection reason")
        if not self.accepted and not self.rejection_reason:
            raise ValueError("rejected plan requires a reason")
