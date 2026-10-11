"""Universal Core API v1: provider-neutral strategy intents, OFFLINE ONLY.

Data contracts and trusted in-process conformance harness; NOT a sandbox,
market poller, execution engine, or Telegram delivery authorization.
Legacy contracts.py / runtime.py and the production bot remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from .contracts import Direction, EvidenceMode, Instrument, Market, SignalIntent

ABI_MAJOR = 1
ABI_MINOR = 0
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{1,79}$")
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_TIMEFRAME_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30,
                      "1h": 60, "4h": 240, "12h": 720, "1d": 1440}
_TIMEFRAMES = frozenset(_TIMEFRAME_MINUTES)


class CoreContractError(ValueError):
    """Contract refusal; never treat a refused result as a trade signal."""


class CoreEventType(StrEnum):
    CLOSED_CANDLE = "closed_candle"
    QUOTE_TICK = "quote_tick"
    POSITION_UPDATE = "position_update"


class DataOrigin(StrEnum):
    REPLAY = "replay"
    SYNTHETIC = "synthetic"


class DecisionKind(StrEnum):
    NO_SETUP = "no_setup"
    SETUP_CANDIDATE = "setup_candidate"
    ENTRY_INTENT = "entry_intent"
    MANAGEMENT_INTENT = "management_intent"
    EXIT_INTENT = "exit_intent"


class ManagementAction(StrEnum):
    MOVE_STOP = "move_stop"


class ExitAction(StrEnum):
    CLOSE_POSITION = "close_position"
    CANCEL_PENDING_ENTRY = "cancel_pending_entry"


def _identity(value: object, label: str) -> None:
    if type(value) is not str or not _ID.fullmatch(value):
        raise CoreContractError(f"INVALID_{label}")


def _token(value: object, label: str) -> None:
    if type(value) is not str or not _TOKEN.fullmatch(value):
        raise CoreContractError(f"INVALID_{label}")


def _price(value: object, label: str) -> None:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise CoreContractError(f"INVALID_{label}")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CoreContractError("TIMESTAMP_MUST_BE_AWARE")
    return value.astimezone(UTC)


def _reasons(values: tuple[str, ...]) -> None:
    if type(values) is not tuple or len(values) > 12:
        raise CoreContractError("INVALID_REASON_CODES")
    for reason in values:
        _token(reason, "REASON_CODE")


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical(asdict(value))
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical(v) for v in value)
    if isinstance(value, datetime):
        return _utc(value).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if value is None or type(value) in (str, int, bool):
        return value
    raise CoreContractError("NONCANONICAL_INPUT")


def content_digest(value: object) -> str:
    """Stable local integrity digest, NOT proof of genuine provider provenance."""
    packet = json.dumps(_canonical(value), ensure_ascii=True, sort_keys=True,
                        separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(packet).hexdigest()


@dataclass(frozen=True, slots=True)
class SetupSpec:
    setup_id: str
    description: str
    may_manage_stop: bool = False

    def __post_init__(self) -> None:
        _identity(self.setup_id, "SETUP_ID")
        if type(self.description) is not str or not 1 <= len(self.description) <= 240:
            raise CoreContractError("INVALID_SETUP_DESCRIPTION")
        if type(self.may_manage_stop) is not bool:
            raise CoreContractError("INVALID_MANAGEMENT_FLAG")


@dataclass(frozen=True, slots=True)
class CoreManifest:
    core_id: str
    core_version: str
    setups: tuple[SetupSpec, ...]
    supported_markets: frozenset[Market]
    accepted_events: frozenset[CoreEventType]
    minimum_closed_candles: int = 1
    abi_major: int = ABI_MAJOR
    abi_minor: int = ABI_MINOR

    def __post_init__(self) -> None:
        _identity(self.core_id, "CORE_ID")
        _token(self.core_version, "CORE_VERSION")
        if type(self.abi_major) is not int or self.abi_major != ABI_MAJOR or (
            type(self.abi_minor) is not int or self.abi_minor != ABI_MINOR
        ):
            raise CoreContractError("UNSUPPORTED_CORE_ABI")
        if not isinstance(self.setups, tuple) or not 1 <= len(self.setups) <= 32 or any(
            not isinstance(s, SetupSpec) for s in self.setups
        ) or len({s.setup_id for s in self.setups}) != len(self.setups):
            raise CoreContractError("INVALID_SETUP_CATALOG")
        if not isinstance(self.supported_markets, frozenset) or not self.supported_markets or any(
            not isinstance(m, Market) for m in self.supported_markets
        ):
            raise CoreContractError("INVALID_MARKET_CAPABILITIES")
        if not isinstance(self.accepted_events, frozenset) or not self.accepted_events or any(
            not isinstance(e, CoreEventType) for e in self.accepted_events
        ):
            raise CoreContractError("INVALID_EVENT_CAPABILITIES")
        if (type(self.minimum_closed_candles) is not int or
                not 1 <= self.minimum_closed_candles <= 512):
            raise CoreContractError("INVALID_LOOKBACK")


@dataclass(frozen=True, slots=True)
class CoreBinding:
    """Host-selected market binding. No account, leverage, capital, or credentials."""
    instance_id: str
    binding_id: str
    instrument: Instrument
    timeframe: str

    def __post_init__(self) -> None:
        _identity(self.instance_id, "INSTANCE_ID")
        _identity(self.binding_id, "BINDING_ID")
        if not isinstance(self.instrument, Instrument) or self.timeframe not in _TIMEFRAMES:
            raise CoreContractError("INVALID_MARKET_BINDING")


@dataclass(frozen=True, slots=True)
class ClosedCandle:
    open_at: datetime
    close_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        start, end = _utc(self.open_at), _utc(self.close_at)
        object.__setattr__(self, "open_at", start)
        object.__setattr__(self, "close_at", end)
        if start >= end:
            raise CoreContractError("INVALID_CANDLE_TIME")
        for key in ("open", "high", "low", "close"):
            _price(getattr(self, key), key.upper())
        if (type(self.volume) is not Decimal or not self.volume.is_finite()
                or self.volume < 0):
            raise CoreContractError("INVALID_VOLUME")
        if (self.low > min(self.open, self.close) or
                self.high < max(self.open, self.close) or self.high < self.low):
            raise CoreContractError("INVALID_OHLC")


@dataclass(frozen=True, slots=True)
class BidAskTick:
    occurred_at: datetime
    bid: Decimal
    ask: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        _price(self.bid, "BID")
        _price(self.ask, "ASK")
        if self.bid > self.ask:
            raise CoreContractError("CROSSED_QUOTE")


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Read-only exposure geometry; never an authorization to manage it."""
    position_id: str
    setup_id: str
    direction: Direction
    entry: Decimal
    initial_stop: Decimal
    current_stop: Decimal
    revision: int

    def __post_init__(self) -> None:
        _token(self.position_id, "POSITION_ID")
        _identity(self.setup_id, "POSITION_SETUP")
        if not isinstance(self.direction, Direction) or type(self.revision) is not int or self.revision < 0:
            raise CoreContractError("INVALID_POSITION_STATE")
        for label in ("entry", "initial_stop", "current_stop"):
            _price(getattr(self, label), label.upper())
        if self.direction is Direction.LONG and not self.initial_stop < self.entry:
            raise CoreContractError("INVALID_POSITION_GEOMETRY")
        if self.direction is Direction.SHORT and not self.initial_stop > self.entry:
            raise CoreContractError("INVALID_POSITION_GEOMETRY")
        if self.direction is Direction.LONG and self.current_stop < self.initial_stop:
            raise CoreContractError("WIDENED_POSITION_STOP")
        if self.direction is Direction.SHORT and self.current_stop > self.initial_stop:
            raise CoreContractError("WIDENED_POSITION_STOP")


@dataclass(frozen=True, slots=True)
class CoreInput:
    core_id: str
    core_version: str
    binding: CoreBinding
    event: CoreEventType
    observed_at: datetime
    origin: DataOrigin
    source_ref: str
    candles: tuple[ClosedCandle, ...] = ()
    tick: BidAskTick | None = None
    position: PositionSnapshot | None = None

    def __post_init__(self) -> None:
        _identity(self.core_id, "CORE_ID")
        _token(self.core_version, "CORE_VERSION")
        if not isinstance(self.binding, CoreBinding) or not isinstance(self.event, CoreEventType):
            raise CoreContractError("INVALID_CORE_INPUT")
        if not isinstance(self.origin, DataOrigin):
            raise CoreContractError("UNVERIFIED_ORIGIN")
        _token(self.source_ref, "SOURCE_REF")
        at = _utc(self.observed_at)
        object.__setattr__(self, "observed_at", at)
        if (type(self.candles) is not tuple or len(self.candles) > 512 or any(
                not isinstance(c, ClosedCandle) for c in self.candles)):
            raise CoreContractError("INVALID_CANDLE_WINDOW")
        if any(a.close_at > b.open_at for a, b in zip(self.candles, self.candles[1:])):
            raise CoreContractError("OVERLAPPING_CANDLE_WINDOW")
        if any(c.close_at > at for c in self.candles):
            raise CoreContractError("FUTURE_CANDLE")
        interval = timedelta(minutes=_TIMEFRAME_MINUTES[self.binding.timeframe])
        for candle in self.candles:
            duration = candle.close_at - candle.open_at
            # Daily bars across session DST transitions can be 23 or 25 hours.
            if ((self.binding.timeframe != "1d" and duration != interval) or
                    (self.binding.timeframe == "1d" and
                     not timedelta(hours=23) <= duration <= timedelta(hours=25))):
                raise CoreContractError("CANDLE_TIMEFRAME_MISMATCH")
        if self.event is CoreEventType.CLOSED_CANDLE:
            if not self.candles or self.candles[-1].close_at != at or self.tick or self.position:
                raise CoreContractError("INVALID_CLOSED_CANDLE_EVENT")
        elif self.event is CoreEventType.QUOTE_TICK:
            if self.candles or self.position or not isinstance(self.tick, BidAskTick) or self.tick.occurred_at != at:
                raise CoreContractError("INVALID_TICK_EVENT")
        else:
            if not isinstance(self.position, PositionSnapshot) or bool(self.candles) == bool(self.tick):
                raise CoreContractError("INVALID_POSITION_EVENT")
            if self.candles and self.candles[-1].close_at != at:
                raise CoreContractError("POSITION_CANDLE_TIME_MISMATCH")
            if self.tick and (not isinstance(self.tick, BidAskTick) or self.tick.occurred_at != at):
                raise CoreContractError("POSITION_TICK_TIME_MISMATCH")

    @property
    def input_digest(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class CoreDecision:
    decision_id: str
    kind: DecisionKind
    setup_id: str | None = None
    reason_codes: tuple[str, ...] = ()
    direction: Direction | None = None
    entry: Decimal | None = None
    stop: Decimal | None = None
    targets: tuple[Decimal, ...] = ()
    expires_at: datetime | None = None
    action: ManagementAction | ExitAction | None = None
    position_id: str | None = None
    expected_position_revision: int | None = None
    new_stop: Decimal | None = None
    pending_entry_id: str | None = None

    def __post_init__(self) -> None:
        _token(self.decision_id, "DECISION_ID")
        if not isinstance(self.kind, DecisionKind):
            raise CoreContractError("INVALID_DECISION_KIND")
        if self.setup_id is not None:
            _identity(self.setup_id, "SETUP_ID")
        _reasons(self.reason_codes)
        order_fields = (self.direction, self.entry, self.stop, self.targets, self.expires_at)
        management_fields = (self.action, self.position_id, self.expected_position_revision,
                             self.new_stop, self.pending_entry_id)
        if self.kind in (DecisionKind.NO_SETUP, DecisionKind.SETUP_CANDIDATE):
            if (self.kind is DecisionKind.NO_SETUP) != (self.setup_id is None):
                raise CoreContractError("INVALID_NONENTRY_SETUP")
            if any(v is not None and v != () for v in order_fields + management_fields):
                raise CoreContractError("NONENTRY_HAS_TRADE_FIELDS")
        elif self.kind is DecisionKind.ENTRY_INTENT:
            if self.setup_id is None or not isinstance(self.direction, Direction):
                raise CoreContractError("ENTRY_MISSING_SETUP_OR_SIDE")
            _price(self.entry, "ENTRY")
            _price(self.stop, "STOP")
            if (type(self.targets) is not tuple or not 1 <= len(self.targets) <= 5):
                raise CoreContractError("ENTRY_TARGETS_REQUIRED")
            for target in self.targets:
                _price(target, "TARGET")
            if self.direction is Direction.LONG and not (self.stop < self.entry and
                    all(t > self.entry for t in self.targets)):
                raise CoreContractError("INVALID_LONG_GEOMETRY")
            if self.direction is Direction.SHORT and not (self.stop > self.entry and
                    all(t < self.entry for t in self.targets)):
                raise CoreContractError("INVALID_SHORT_GEOMETRY")
            if self.expires_at is not None:
                object.__setattr__(self, "expires_at", _utc(self.expires_at))
            if any(v is not None for v in management_fields):
                raise CoreContractError("ENTRY_HAS_MANAGEMENT_FIELDS")
        else:
            if self.setup_id is None or any(v is not None and v != () for v in order_fields):
                raise CoreContractError("INVALID_MANAGEMENT_OR_EXIT_FIELDS")
            if self.kind is DecisionKind.MANAGEMENT_INTENT:
                if (self.action is not ManagementAction.MOVE_STOP or
                        self.pending_entry_id is not None or self.position_id is None or
                        self.expected_position_revision is None):
                    raise CoreContractError("INVALID_STOP_MANAGEMENT")
                _token(self.position_id, "POSITION_ID")
                _price(self.new_stop, "NEW_STOP")
            else:
                if self.action is ExitAction.CLOSE_POSITION:
                    if self.position_id is None or self.pending_entry_id is not None:
                        raise CoreContractError("EXIT_MISSING_POSITION")
                    _token(self.position_id, "POSITION_ID")
                elif self.action is ExitAction.CANCEL_PENDING_ENTRY:
                    if self.position_id is not None or self.pending_entry_id is None:
                        raise CoreContractError("EXIT_MISSING_ORDER_INTENT")
                    _token(self.pending_entry_id, "PENDING_ENTRY_ID")
                else:
                    raise CoreContractError("INVALID_EXIT_ACTION")
                if self.new_stop is not None:
                    raise CoreContractError("EXIT_HAS_NEW_STOP")
            if (self.expected_position_revision is not None and
                    (type(self.expected_position_revision) is not int or self.expected_position_revision < 0)):
                raise CoreContractError("INVALID_POSITION_REVISION")


@dataclass(frozen=True, slots=True)
class CoreResult:
    core_id: str
    core_version: str
    instance_id: str
    binding_id: str
    observed_at: datetime
    input_digest: str
    decisions: tuple[CoreDecision, ...]

    def __post_init__(self) -> None:
        _identity(self.core_id, "CORE_ID")
        _token(self.core_version, "CORE_VERSION")
        _identity(self.instance_id, "INSTANCE_ID")
        _identity(self.binding_id, "BINDING_ID")
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        if type(self.input_digest) is not str or not _HASH.fullmatch(self.input_digest):
            raise CoreContractError("INVALID_INPUT_DIGEST")
        if (type(self.decisions) is not tuple or not 1 <= len(self.decisions) <= 12 or
                any(not isinstance(d, CoreDecision) for d in self.decisions)):
            raise CoreContractError("INVALID_DECISION_BATCH")


def validate_core_result(manifest: CoreManifest, event: CoreInput, result: CoreResult) -> None:
    """Deterministic contract gate. Does not permit publication or order execution."""
    if (manifest.core_id != event.core_id or manifest.core_version != event.core_version or
            event.binding.instrument.market not in manifest.supported_markets or
            event.event not in manifest.accepted_events):
        raise CoreContractError("INCOMPATIBLE_CORE_BINDING_OR_EVENT")
    if event.candles and len(event.candles) < manifest.minimum_closed_candles:
        raise CoreContractError("INSUFFICIENT_CLOSED_CANDLES")
    if (result.core_id != event.core_id or result.core_version != event.core_version or
            result.instance_id != event.binding.instance_id or
            result.binding_id != event.binding.binding_id or
            result.observed_at != event.observed_at or result.input_digest != event.input_digest):
        raise CoreContractError("RESULT_IDENTITY_OR_PROVENANCE_MISMATCH")
    known = {s.setup_id: s for s in manifest.setups}
    if len({d.decision_id for d in result.decisions}) != len(result.decisions):
        raise CoreContractError("DUPLICATE_DECISION_ID")
    if len(result.decisions) > 1 and any(d.kind is DecisionKind.NO_SETUP for d in result.decisions):
        raise CoreContractError("NO_SETUP_MUST_BE_EXCLUSIVE")
    for decision in result.decisions:
        if decision.setup_id is not None and decision.setup_id not in known:
            raise CoreContractError("UNKNOWN_SETUP_ID")
        if decision.kind is DecisionKind.ENTRY_INTENT:
            if decision.expires_at is not None and decision.expires_at <= event.observed_at:
                raise CoreContractError("EXPIRED_ENTRY_INTENT")
            if event.event not in (CoreEventType.CLOSED_CANDLE, CoreEventType.QUOTE_TICK):
                raise CoreContractError("ENTRY_ON_WRONG_EVENT")
        if decision.kind in (DecisionKind.MANAGEMENT_INTENT, DecisionKind.EXIT_INTENT):
            cancel_pending = (decision.kind is DecisionKind.EXIT_INTENT and
                              decision.action is ExitAction.CANCEL_PENDING_ENTRY)
            if cancel_pending and event.event is CoreEventType.POSITION_UPDATE:
                raise CoreContractError("CANCEL_REQUIRES_MARKET_EVENT")
            if not cancel_pending and event.event is not CoreEventType.POSITION_UPDATE:
                raise CoreContractError("POSITION_ACTION_ON_WRONG_EVENT")
            if decision.kind is DecisionKind.MANAGEMENT_INTENT or decision.action is ExitAction.CLOSE_POSITION:
                p = event.position
                if (p is None or decision.position_id != p.position_id or
                        decision.setup_id != p.setup_id or
                        decision.expected_position_revision != p.revision):
                    raise CoreContractError("STALE_OR_CROSS_POSITION_DECISION")
            if decision.kind is DecisionKind.MANAGEMENT_INTENT:
                p = event.position
                if not known[decision.setup_id].may_manage_stop:
                    raise CoreContractError("UNDECLARED_TRAILING_STOP")
                if p.direction is Direction.LONG and decision.new_stop <= p.current_stop:
                    raise CoreContractError("STOP_NOT_TIGHTENED")
                if p.direction is Direction.SHORT and decision.new_stop >= p.current_stop:
                    raise CoreContractError("STOP_NOT_TIGHTENED")


class OfflineCore(Protocol):
    """A reviewed in-process core; untrusted source MUST NOT be passed here."""

    manifest: CoreManifest

    def evaluate(self, event: CoreInput) -> CoreResult: ...


class OfflineCoreHarness:
    """Explicitly enabled trusted OFFLINE replay. Never sends anything externally."""

    def __init__(self, core: OfflineCore, *, enabled: bool = False) -> None:
        if not isinstance(core.manifest, CoreManifest) or not callable(getattr(core, "evaluate", None)):
            raise CoreContractError("INVALID_CORE_IMPLEMENTATION")
        self._core = core
        self.enabled = enabled
        self.quarantined_bindings: set[str] = set()

    def evaluate(self, event: CoreInput) -> CoreResult:
        if not self.enabled:
            raise CoreContractError("OFFLINE_CORE_DISABLED")
        if event.binding.binding_id in self.quarantined_bindings:
            raise CoreContractError("BINDING_QUARANTINED")
        manifest = self._core.manifest
        if (event.core_id != manifest.core_id or event.core_version != manifest.core_version or
                event.binding.instrument.market not in manifest.supported_markets or
                event.event not in manifest.accepted_events):
            raise CoreContractError("INCOMPATIBLE_CORE_BINDING_OR_EVENT")
        if event.candles and len(event.candles) < manifest.minimum_closed_candles:
            raise CoreContractError("INSUFFICIENT_CLOSED_CANDLES")
        try:
            result = self._core.evaluate(event)
            if not isinstance(result, CoreResult):
                raise CoreContractError("NONCONTRACT_RESULT")
            validate_core_result(manifest, event, result)
            return result
        except Exception as exc:
            self.quarantined_bindings.add(event.binding.binding_id)
            raise CoreContractError("CORE_QUARANTINED_AFTER_INVALID_OUTPUT") from exc


def to_legacy_paper_intent(manifest: CoreManifest, event: CoreInput,
                           result: CoreResult, decision: CoreDecision) -> SignalIntent:
    """One-way data-only adapter to legacy SignalIntent. Never publishes or trades."""
    validate_core_result(manifest, event, result)
    if (event.origin not in (DataOrigin.REPLAY, DataOrigin.SYNTHETIC) or
            decision.kind is not DecisionKind.ENTRY_INTENT or decision not in result.decisions):
        raise CoreContractError("LEGACY_ADAPTER_PAPER_ENTRY_ONLY")
    if (result.core_id != event.core_id or result.core_version != event.core_version or
            result.instance_id != event.binding.instance_id or
            result.binding_id != event.binding.binding_id or
            result.input_digest != event.input_digest or result.observed_at != event.observed_at):
        raise CoreContractError("LEGACY_ADAPTER_CONTEXT_MISMATCH")
    return SignalIntent(
        signal_id=decision.decision_id,
        engine_id=result.core_id,
        engine_version=result.core_version,
        instrument=event.binding.instrument,
        direction=decision.direction,
        observed_at=result.observed_at,
        entry=decision.entry,
        stop=decision.stop,
        targets=decision.targets,
        evidence_mode=EvidenceMode.PAPER,
    )
