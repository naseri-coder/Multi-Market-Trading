"""Typed contracts for Brooks Core v3 Phase 2 Crypto Adaptation Layer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.modules.brooks_core_v3.entities import FoundationSnapshot, MetricValue
from app.modules.brooks_core_v3.enums import (
    CryptoEvidenceSource,
    DerivativesBias,
    EvidenceStatus,
    FakeBreakoutState,
    LiquidityState,
    MTFAlignment,
    RelativeVolumeState,
    VolatilityState,
)
from app.modules.market_data.entities import TIMEFRAME_SECONDS, MarketSnapshot


@dataclass(frozen=True, slots=True)
class CryptoAdaptationEvidence:
    evidence_id: str
    status: EvidenceStatus
    source: CryptoEvidenceSource
    rationale: str
    measurements: tuple[MetricValue, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_id.startswith("CA-"):
            raise ValueError("crypto adaptation evidence ids must start with CA-")
        if not self.rationale.strip():
            raise ValueError("rationale is required")
        for key, value in self.measurements:
            if not key.strip() or not value.strip():
                raise ValueError("measurement key/value cannot be blank")


@dataclass(frozen=True, slots=True)
class LiquidityObservation:
    captured_at: datetime
    source: str
    spread_bps: Decimal | None = None
    bid_ask_depth_ratio: Decimal | None = None
    depth_to_volume_ratio: Decimal | None = None

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None:
            raise ValueError("liquidity observation timestamp must be timezone-aware")
        if not self.source.strip():
            raise ValueError("liquidity observation source is required")
        if all(value is None for value in self.values):
            raise ValueError("liquidity observation needs at least one measurement")
        self.validate_values()

    @property
    def values(self) -> tuple[Decimal | None, ...]:
        return (self.spread_bps, self.bid_ask_depth_ratio, self.depth_to_volume_ratio)

    def validate_values(self) -> None:
        if self.spread_bps is not None and self.spread_bps < 0:
            raise ValueError("spread_bps cannot be negative")
        if self.bid_ask_depth_ratio is not None and self.bid_ask_depth_ratio <= 0:
            raise ValueError("bid_ask_depth_ratio must be positive")
        if self.depth_to_volume_ratio is not None and self.depth_to_volume_ratio < 0:
            raise ValueError("depth_to_volume_ratio cannot be negative")


@dataclass(frozen=True, slots=True)
class DerivativesObservation:
    captured_at: datetime
    source: str
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    open_interest_change_fraction: Decimal | None = None

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None:
            raise ValueError("derivatives observation timestamp must be timezone-aware")
        if not self.source.strip():
            raise ValueError("derivatives observation source is required")
        if all(value is None for value in self.values):
            raise ValueError("derivatives observation needs at least one measurement")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open_interest cannot be negative")

    @property
    def values(self) -> tuple[Decimal | None, ...]:
        return (self.funding_rate, self.open_interest, self.open_interest_change_fraction)


@dataclass(frozen=True, slots=True)
class CryptoAdaptationInput:
    primary_snapshot: MarketSnapshot
    higher_timeframe_snapshots: tuple[MarketSnapshot, ...] = ()
    liquidity: LiquidityObservation | None = None
    derivatives: DerivativesObservation | None = None

    def __post_init__(self) -> None:
        primary = self.primary_snapshot
        seen = {primary.timeframe}
        for snapshot in self.higher_timeframe_snapshots:
            if snapshot.timeframe in seen:
                raise ValueError("multi-timeframe snapshots must use unique timeframes")
            seen.add(snapshot.timeframe)
            identity = (snapshot.exchange, snapshot.market_type, snapshot.symbol)
            primary_identity = (primary.exchange, primary.market_type, primary.symbol)
            if identity != primary_identity:
                raise ValueError("multi-timeframe snapshots must describe the same market")
            if TIMEFRAME_SECONDS[snapshot.timeframe] <= TIMEFRAME_SECONDS[primary.timeframe]:
                raise ValueError("MTF snapshots must be higher than the primary timeframe")
            if snapshot.captured_at > primary.captured_at:
                raise ValueError("higher-timeframe snapshot capture cannot be from the future")
            if snapshot.candles[-1].close_time > primary.captured_at:
                raise ValueError("higher-timeframe snapshot cannot contain future data")
        for observation in (self.liquidity, self.derivatives):
            if observation is not None and observation.captured_at > primary.captured_at:
                raise ValueError("crypto adaptation observation cannot be from the future")


@dataclass(frozen=True, slots=True)
class CryptoAdaptationAssessment:
    foundation: FoundationSnapshot
    volatility_state: VolatilityState
    volatility_ratio: Decimal | None
    relative_volume_state: RelativeVolumeState
    relative_volume_ratio: Decimal | None
    fake_breakout_state: FakeBreakoutState
    fake_breakout_reference_level: Decimal | None
    liquidity_state: LiquidityState
    derivatives_bias: DerivativesBias
    mtf_alignment: MTFAlignment
    evidence: tuple[CryptoAdaptationEvidence, ...]
    blockers: tuple[str, ...]
    configuration_version: str
    input_fingerprint: str

    def __post_init__(self) -> None:
        if not self.configuration_version.strip():
            raise ValueError("configuration_version is required")
        if len(self.input_fingerprint) != 64:
            raise ValueError("input_fingerprint must be a sha256 hex digest")
        if self.volatility_ratio is not None and self.volatility_ratio < 0:
            raise ValueError("volatility_ratio cannot be negative")
        if self.relative_volume_ratio is not None and self.relative_volume_ratio < 0:
            raise ValueError("relative_volume_ratio cannot be negative")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("blockers cannot be blank")
        if not self.evidence:
            raise ValueError("crypto adaptation assessment requires evidence")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("crypto adaptation evidence ids must be unique")
