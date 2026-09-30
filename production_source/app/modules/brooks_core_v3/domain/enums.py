"""Pure Phase-3 domain enums for Brooks Core v3.

These values are orchestration contracts only. They contain no strategy thresholds.
"""

from enum import StrEnum


class SwingKind(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class StructureState(StrEnum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGE = "RANGE"
    UNDETERMINED = "UNDETERMINED"


class StructureLabel(StrEnum):
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"

class MarketRegimeKind(StrEnum):
    TREND = "TREND"
    TRADING_RANGE = "TRADING_RANGE"
    BREAKOUT_TRANSITION = "BREAKOUT_TRANSITION"
    UNDETERMINED = "UNDETERMINED"


class ZoneRole(StrEnum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"


class ZoneState(StrEnum):
    ACTIVE = "ACTIVE"
    BROKEN = "BROKEN"
    RETESTED = "RETESTED"
    INVALIDATED = "INVALIDATED"
    UNDETERMINED = "UNDETERMINED"


class TrendChannelState(StrEnum):
    ACTIVE = "ACTIVE"
    BROKEN = "BROKEN"
    UNDETERMINED = "UNDETERMINED"

class TradeDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class SignalDecision(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    NO_SIGNAL = "NO_SIGNAL"


class RuleEvaluationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"


class SignalEventType(StrEnum):
    CREATED = "CREATED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    DELIVERY_UPDATED = "DELIVERY_UPDATED"
    INVALIDATED = "INVALIDATED"
