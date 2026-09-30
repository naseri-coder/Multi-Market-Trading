"""Brooks Core v3 Phase-3 architecture-only domain package."""

from .contracts import assert_signal_chart_same_snapshot, reproduction_key
from .identity import build_market_snapshot, snapshot_hash
from .models import (
    Candle,
    ChartSpecification,
    MarketRegime,
    MarketSnapshot,
    MarketStructure,
    RiskPlan,
    RuleEvaluation,
    RuleVersion,
    SetupCandidate,
    Signal,
    SignalCandidate,
    SignalEvent,
    SupportResistanceZone,
    SwingPoint,
    TrendChannel,
)
from .protocols import MarketDataProvider, SignalPublisher

DOMAIN_MODELS = (
    Candle,
    MarketSnapshot,
    SwingPoint,
    MarketStructure,
    MarketRegime,
    SupportResistanceZone,
    TrendChannel,
    SetupCandidate,
    RuleEvaluation,
    RiskPlan,
    SignalCandidate,
    Signal,
    SignalEvent,
    ChartSpecification,
    RuleVersion,
)

DOMAIN_PROTOCOLS = (MarketDataProvider, SignalPublisher)

__all__ = [
    "Candle", "MarketSnapshot", "SwingPoint", "MarketStructure", "MarketRegime",
    "SupportResistanceZone", "TrendChannel", "SetupCandidate", "RuleEvaluation",
    "RiskPlan", "SignalCandidate", "Signal", "SignalEvent", "ChartSpecification",
    "RuleVersion", "MarketDataProvider", "SignalPublisher", "DOMAIN_MODELS",
    "DOMAIN_PROTOCOLS", "build_market_snapshot", "snapshot_hash",
    "assert_signal_chart_same_snapshot", "reproduction_key",
]
