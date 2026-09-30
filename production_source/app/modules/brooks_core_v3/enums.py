"""Shared Brooks Core v3 vocabulary for Foundation and crypto adaptation.

The package remains descriptive and does not make publication or execution decisions.
"""

from __future__ import annotations

from enum import StrEnum


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class MarketRegime(StrEnum):
    BULL_TREND = "BULL_TREND"
    BEAR_TREND = "BEAR_TREND"
    TRADING_RANGE = "TRADING_RANGE"
    TRANSITION = "TRANSITION"
    AMBIGUOUS = "AMBIGUOUS"


class AlwaysIn(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    UNRESOLVED = "UNRESOLVED"


class EvidenceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleTaxonomy(StrEnum):
    SOURCE_RULE = "SOURCE_RULE"
    SOURCE_INTERPRETATION = "SOURCE_INTERPRETATION"
    ENGINEERING_POLICY = "ENGINEERING_POLICY"


class SourceBook(StrEnum):
    TRENDS = "Trading Price Action Trends"
    RANGES = "Trading Price Action Trading Ranges"
    REVERSALS = "Trading Price Action Reversals"


class FoundationLayer(StrEnum):
    MARKET_STATE = "MARKET_STATE"
    CONTEXT_MODEL = "CONTEXT_MODEL"
    NARRATIVE_MODEL = "NARRATIVE_MODEL"
    EVIDENCE_REGISTRY = "EVIDENCE_REGISTRY"


class VolatilityState(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class RelativeVolumeState(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    SPIKE = "SPIKE"
    UNKNOWN = "UNKNOWN"


class FakeBreakoutState(StrEnum):
    NONE = "NONE"
    BULL_TRAP = "BULL_TRAP"
    BEAR_TRAP = "BEAR_TRAP"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"


class LiquidityState(StrEnum):
    THIN = "THIN"
    NORMAL = "NORMAL"
    DEEP = "DEEP"
    IMBALANCED = "IMBALANCED"
    UNKNOWN = "UNKNOWN"


class DerivativesBias(StrEnum):
    LONG_CROWDED = "LONG_CROWDED"
    SHORT_CROWDED = "SHORT_CROWDED"
    BALANCED = "BALANCED"
    UNKNOWN = "UNKNOWN"


class MTFAlignment(StrEnum):
    ALIGNED_LONG = "ALIGNED_LONG"
    ALIGNED_SHORT = "ALIGNED_SHORT"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class CryptoEvidenceSource(StrEnum):
    CLOSED_CANDLES = "CLOSED_CANDLES"
    LIQUIDITY_OBSERVATION = "LIQUIDITY_OBSERVATION"
    DERIVATIVES_OBSERVATION = "DERIVATIVES_OBSERVATION"
    MULTI_TIMEFRAME = "MULTI_TIMEFRAME"
