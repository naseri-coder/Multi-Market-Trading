"""Immutable Phase-3 domain contracts for Brooks Core v3.

No setup detector, scoring threshold, entry algorithm, exchange SDK, chart renderer,
or Telegram dependency belongs in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .enums import (
    MarketRegimeKind,
    RuleEvaluationStatus,
    SignalDecision,
    SignalEventType,
    StructureLabel,
    StructureState,
    SwingKind,
    TradeDirection,
    TrendChannelState,
    ZoneRole,
    ZoneState,
)

EvidenceValue = tuple[str, str]


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")

def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64:
        raise ValueError(f"{field_name} must be a sha256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be hexadecimal") from exc


def _validate_evidence(items: tuple[EvidenceValue, ...]) -> None:
    for key, value in items:
        _require_text(key, "evidence key")
        _require_text(value, "evidence value")


@dataclass(frozen=True, slots=True)
class Candle:
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool
    source: str

    def __post_init__(self) -> None:
        _require_aware(self.open_time, "open_time")
        _require_aware(self.close_time, "close_time")
        _require_text(self.source, "source")
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be greater than open_time")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")
        if not self.low <= self.open <= self.high:
            raise ValueError("open must be inside candle range")
        if not self.low <= self.close <= self.high:
            raise ValueError("close must be inside candle range")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    market_snapshot_id: str
    market_snapshot_hash: str
    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]
    as_of: datetime
    last_closed_candle_time: datetime
    data_version: str
    higher_timeframe_series: tuple[tuple[str, tuple[Candle, ...]], ...] = ()
    lower_timeframe_series: tuple[tuple[str, tuple[Candle, ...]], ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.symbol, "symbol"),
            (self.timeframe, "timeframe"),
            (self.data_version, "data_version"),
        ):
            _require_text(value, name)
        _require_sha256(self.market_snapshot_hash, "market_snapshot_hash")
        _require_aware(self.as_of, "as_of")
        _require_aware(self.last_closed_candle_time, "last_closed_candle_time")
        if not self.candles:
            raise ValueError("snapshot requires at least one candle")
        previous: Candle | None = None
        for candle in self.candles:
            if not candle.is_closed:
                raise ValueError("snapshot cannot contain unfinished candles")
            if candle.close_time > self.as_of:
                raise ValueError("snapshot cannot contain future candles")
            if previous is not None and candle.open_time <= previous.open_time:
                raise ValueError("candles must be strictly ordered")
            previous = candle
        if self.last_closed_candle_time != self.candles[-1].close_time:
            raise ValueError("last_closed_candle_time must match final candle")
        self._validate_related_series(self.higher_timeframe_series, "higher")
        self._validate_related_series(self.lower_timeframe_series, "lower")

    def _validate_related_series(
        self,
        series: tuple[tuple[str, tuple[Candle, ...]], ...],
        label: str,
    ) -> None:
        seen: set[str] = set()
        for timeframe, candles in series:
            _require_text(timeframe, f"{label} timeframe")
            if timeframe in seen:
                raise ValueError(f"duplicate {label} timeframe")
            seen.add(timeframe)
            previous: Candle | None = None
            for candle in candles:
                if not candle.is_closed or candle.close_time > self.as_of:
                    raise ValueError(f"{label} timeframe contains future/open candle")
                if previous is not None and candle.open_time <= previous.open_time:
                    raise ValueError(f"{label} timeframe candles must be ordered")
                previous = candle


@dataclass(frozen=True, slots=True)
class SwingPoint:
    swing_id: str
    market_snapshot_id: str
    timeframe: str
    kind: SwingKind
    price: Decimal
    pivot_time: datetime
    confirmed_at: datetime
    label: StructureLabel | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.swing_id, "swing_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.timeframe, "timeframe"),
        ):
            _require_text(value, name)
        _require_aware(self.pivot_time, "pivot_time")
        _require_aware(self.confirmed_at, "confirmed_at")
        if self.confirmed_at < self.pivot_time:
            raise ValueError("confirmed_at cannot precede pivot_time")
        if self.price <= 0:
            raise ValueError("swing price must be positive")


@dataclass(frozen=True, slots=True)
class MarketStructure:
    market_snapshot_id: str
    state: StructureState
    confirmed_swings: tuple[SwingPoint, ...]
    labels: tuple[StructureLabel, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.market_snapshot_id, "market_snapshot_id")
        if any(s.market_snapshot_id != self.market_snapshot_id for s in self.confirmed_swings):
            raise ValueError("all swings must belong to the same snapshot")
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("structure reasons cannot be blank")

@dataclass(frozen=True, slots=True)
class MarketRegime:
    market_snapshot_id: str
    kind: MarketRegimeKind
    direction: TradeDirection | None = None
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.market_snapshot_id, "market_snapshot_id")
        if self.kind is MarketRegimeKind.TREND and self.direction is None:
            raise ValueError("TREND regime requires direction")
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("regime reasons cannot be blank")


@dataclass(frozen=True, slots=True)
class SupportResistanceZone:
    zone_id: str
    market_snapshot_id: str
    timeframe: str
    role: ZoneRole
    lower_price: Decimal
    upper_price: Decimal
    provenance: tuple[str, ...]
    evidence: tuple[EvidenceValue, ...]
    state: ZoneState
    created_at: datetime
    last_confirmed_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.zone_id, "zone_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.timeframe, "timeframe"),
        ):
            _require_text(value, name)
        if self.lower_price <= 0 or self.upper_price <= 0:
            raise ValueError("zone prices must be positive")
        if self.lower_price > self.upper_price:
            raise ValueError("zone lower_price cannot exceed upper_price")
        if not self.provenance or any(not item.strip() for item in self.provenance):
            raise ValueError("zone provenance is required")
        _validate_evidence(self.evidence)
        _require_aware(self.created_at, "created_at")
        _require_aware(self.last_confirmed_at, "last_confirmed_at")
        if self.last_confirmed_at < self.created_at:
            raise ValueError("last_confirmed_at cannot precede created_at")


@dataclass(frozen=True, slots=True)
class TrendChannel:
    channel_id: str
    market_snapshot_id: str
    timeframe: str
    direction: TradeDirection
    anchor_swing_ids: tuple[str, ...]
    state: TrendChannelState
    evidence: tuple[EvidenceValue, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.channel_id, "channel_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.timeframe, "timeframe"),
        ):
            _require_text(value, name)
        if not self.anchor_swing_ids or any(not item.strip() for item in self.anchor_swing_ids):
            raise ValueError("trend channel needs anchor_swing_ids")
        _validate_evidence(self.evidence)
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class RuleVersion:
    rule_id: str
    rule_version: str
    source_catalog_version: str
    checksum: str
    created_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.rule_id, "rule_id")
        _require_text(self.rule_version, "rule_version")
        _require_text(self.source_catalog_version, "source_catalog_version")
        _require_sha256(self.checksum, "checksum")
        _require_aware(self.created_at, "created_at")

@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    market_snapshot_id: str
    rule_id: str
    rule_version: str
    status: RuleEvaluationStatus
    source_pages: tuple[int, ...]
    evidence: tuple[EvidenceValue, ...]
    failed_conditions: tuple[str, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.market_snapshot_id, "market_snapshot_id")
        _require_text(self.rule_id, "rule_id")
        _require_text(self.rule_version, "rule_version")
        if not self.source_pages or any(page <= 0 for page in self.source_pages):
            raise ValueError("source_pages must be positive and non-empty")
        _validate_evidence(self.evidence)
        if any(not item.strip() for item in self.failed_conditions):
            raise ValueError("failed_conditions cannot contain blanks")
        _require_aware(self.evaluated_at, "evaluated_at")


@dataclass(frozen=True, slots=True)
class SetupCandidate:
    candidate_id: str
    market_snapshot_id: str
    setup_type: str
    direction: TradeDirection
    rule_ids: tuple[str, ...]
    rule_evaluations: tuple[RuleEvaluation, ...]
    evidence: tuple[EvidenceValue, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.candidate_id, "candidate_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.setup_type, "setup_type"),
        ):
            _require_text(value, name)
        if not self.rule_ids or any(not rule_id.strip() for rule_id in self.rule_ids):
            raise ValueError("setup candidate requires rule_ids")
        if any(item.market_snapshot_id != self.market_snapshot_id for item in self.rule_evaluations):
            raise ValueError("rule evaluations must match candidate snapshot")
        _validate_evidence(self.evidence)
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class RiskPlan:
    market_snapshot_id: str
    setup_candidate_id: str
    entry_price: Decimal | None = None
    structural_invalidation: Decimal | None = None
    stop_price: Decimal | None = None
    targets: tuple[Decimal, ...] = ()
    r_multiples: tuple[Decimal, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.market_snapshot_id, "market_snapshot_id")
        _require_text(self.setup_candidate_id, "setup_candidate_id")
        prices = (
            self.entry_price,
            self.structural_invalidation,
            self.stop_price,
            *self.targets,
        )
        if any(value is not None and value <= 0 for value in prices):
            raise ValueError("risk plan prices must be positive when present")
        if any(value <= 0 for value in self.r_multiples):
            raise ValueError("r_multiples must be positive")
        if self.r_multiples and len(self.r_multiples) != len(self.targets):
            raise ValueError("r_multiples must align with targets")
        if any(not reason.strip() for reason in self.reasons):
            raise ValueError("risk reasons cannot be blank")


@dataclass(frozen=True, slots=True)
class SignalCandidate:
    candidate_id: str
    market_snapshot_id: str
    market_snapshot_hash: str
    setup_candidate_id: str
    direction: TradeDirection
    risk_plan: RiskPlan
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    reasons: tuple[str, ...]
    rule_set_version: str
    engine_version: str
    configuration_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.candidate_id, "candidate_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.setup_candidate_id, "setup_candidate_id"),
            (self.rule_set_version, "rule_set_version"),
            (self.engine_version, "engine_version"),
            (self.configuration_version, "configuration_version"),
        ):
            _require_text(value, name)
        _require_sha256(self.market_snapshot_hash, "market_snapshot_hash")
        if self.risk_plan.market_snapshot_id != self.market_snapshot_id:
            raise ValueError("risk plan must match signal candidate snapshot")
        if self.risk_plan.setup_candidate_id != self.setup_candidate_id:
            raise ValueError("risk plan must match setup candidate")
        if not self.rule_ids or any(not item.strip() for item in self.rule_ids):
            raise ValueError("signal candidate requires rule_ids")
        if any(not item.strip() for item in (*self.failed_rules, *self.reasons)):
            raise ValueError("failed_rules/reasons cannot contain blanks")
        _require_aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class Signal:
    signal_id: str
    decision: SignalDecision
    market_snapshot_id: str
    market_snapshot_hash: str
    rule_set_version: str
    engine_version: str
    configuration_version: str
    reasons: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    approved_at: datetime
    setup_type: str | None = None
    risk_plan: RiskPlan | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.signal_id, "signal_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.rule_set_version, "rule_set_version"),
            (self.engine_version, "engine_version"),
            (self.configuration_version, "configuration_version"),
        ):
            _require_text(value, name)
        _require_sha256(self.market_snapshot_hash, "market_snapshot_hash")
        if any(not item.strip() for item in (*self.reasons, *self.rule_ids, *self.failed_rules)):
            raise ValueError("signal audit fields cannot contain blanks")
        if self.decision is not SignalDecision.NO_SIGNAL and self.risk_plan is None:
            raise ValueError("tradeable signal requires risk_plan")
        if self.risk_plan is not None and self.risk_plan.market_snapshot_id != self.market_snapshot_id:
            raise ValueError("risk plan must match signal snapshot")
        _require_aware(self.approved_at, "approved_at")

@dataclass(frozen=True, slots=True)
class SignalEvent:
    event_id: str
    signal_id: str
    event_type: SignalEventType
    occurred_at: datetime
    payload: tuple[EvidenceValue, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        _require_text(self.signal_id, "signal_id")
        _require_aware(self.occurred_at, "occurred_at")
        _validate_evidence(self.payload)


@dataclass(frozen=True, slots=True)
class ChartSpecification:
    chart_id: str
    signal_id: str
    market_snapshot_id: str
    market_snapshot_hash: str
    timeframe: str
    title: str
    drawing_instructions: tuple[EvidenceValue, ...]
    data_references: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.chart_id, "chart_id"),
            (self.signal_id, "signal_id"),
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.timeframe, "timeframe"),
            (self.title, "title"),
        ):
            _require_text(value, name)
        _require_sha256(self.market_snapshot_hash, "market_snapshot_hash")
        _validate_evidence(self.drawing_instructions)
        if any(not item.strip() for item in self.data_references):
            raise ValueError("data_references cannot contain blanks")
        _require_aware(self.created_at, "created_at")
