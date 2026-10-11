"""Stage 7: opt-in, OFFLINE strategy orchestration; inert decisions only.

The platform owns subscriptions and activation. A trusted reviewed in-process
core, or the Stage-4 secured isolated host, evaluates the Stage-5 CoreInputs.
This component NEVER sends Telegram messages, accesses broker credentials,
places orders, downloads market data, or grants LIVE/PAPER execution authority.
All state is volatile; there is no exactly-once promise across restarts.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from threading import RLock

from .core_api_v1 import (
    CoreBinding, CoreInput, CoreManifest, CoreResult, DecisionKind,
    OfflineCoreHarness, validate_core_result,
)
from .market_data_engine_v1 import (
    MarketDataRefused, MarketDispatch, MarketPacket, OfflineMarketDataEngine,
    PacketStatus, PriceBasis, VolumeSemantics,
)
from .secure_plugin_runtime_v1 import SecureOfflineCoreHost


class OrchestrationRefused(ValueError):
    """Fail-closed error, no opaque strategy exception details leaked."""


class EvaluationStatus(StrEnum):
    EVALUATED = "evaluated"
    DISABLED = "disabled"
    QUARANTINED = "quarantined"
    DUPLICATE = "duplicate"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class TrustedCoreEvaluator:
    """For reviewed, trusted, operator-approved offline strategy objects only."""

    harness: OfflineCoreHarness
    manifest: CoreManifest

    def __post_init__(self) -> None:
        if (not isinstance(self.harness, OfflineCoreHarness) or
                not isinstance(self.manifest, CoreManifest) or
                not self.harness.enabled or
                self.harness._core.manifest != self.manifest):
            raise OrchestrationRefused("TRUSTED_EVALUATOR_NOT_READY")

    def evaluate(self, event: CoreInput) -> CoreResult:
        return self.harness.evaluate(event)


@dataclass(frozen=True, slots=True)
class IsolatedCoreEvaluator:
    """For owner-approved pinned plugin source; uses Stage-4 OCI isolation."""

    host: SecureOfflineCoreHost
    manifest: CoreManifest
    source: bytes
    source_sha256: str

    def __post_init__(self) -> None:
        import hashlib
        import hmac
        if (not isinstance(self.host, SecureOfflineCoreHost) or
                not self.host.policy.enabled or
                not isinstance(self.manifest, CoreManifest) or
                type(self.source) is not bytes or
                type(self.source_sha256) is not str or
                len(self.source_sha256) != 64 or
                not hmac.compare_digest(hashlib.sha256(self.source).hexdigest(), self.source_sha256)):
            raise OrchestrationRefused("ISOLATED_EVALUATOR_NOT_READY")

    def evaluate(self, event: CoreInput) -> CoreResult:
        return self.host.evaluate(self.manifest, event, source=self.source,
                                  approved_source_sha256=self.source_sha256)


@dataclass(frozen=True, slots=True)
class OrchestratorOutcome:
    binding_id: str
    instance_id: str
    status: EvaluationStatus
    input_digest: str | None = None
    result: CoreResult | None = None
    price_basis: PriceBasis | None = None
    volume_semantics: VolumeSemantics | None = None

    @property
    def actionable_decisions(self) -> tuple[str, ...]:
        if self.result is None:
            return ()
        return tuple(d.decision_id for d in self.result.decisions
                     if d.kind in (DecisionKind.ENTRY_INTENT,
                                   DecisionKind.MANAGEMENT_INTENT,
                                   DecisionKind.EXIT_INTENT))


@dataclass(frozen=True, slots=True)
class OrchestratorReceipt:
    feed_id: str
    sequence: int
    packet_status: PacketStatus
    outcomes: tuple[OrchestratorOutcome, ...]
    waiting_bindings: tuple[str, ...]
    # Read-only decisions, not Telegram publication or trade authorization.
    telegram_sent: bool = False
    broker_order_sent: bool = False


@dataclass(frozen=True, slots=True)
class BindingStatus:
    binding_id: str
    instance_id: str
    feed_id: str
    revision: int
    enabled: bool
    quarantined: bool
    completed_events: int
    refused_events: int
    last_input_digest: str | None
    last_observed_at: datetime | None
    last_error_code: str | None
    telegram_enabled: bool = False
    broker_orders_enabled: bool = False


@dataclass(slots=True)
class _Slot:
    feed_id: str
    manifest: CoreManifest
    binding: CoreBinding
    evaluator: TrustedCoreEvaluator | IsolatedCoreEvaluator
    enabled: bool = False
    revision: int = 1
    quarantined: bool = False
    completed_events: int = 0
    refused_events: int = 0
    last_input_digest: str | None = None
    last_observed_at: datetime | None = None
    last_error_code: str | None = None
    decision_ids: deque[str] = field(default_factory=lambda: deque(maxlen=2048))
    decision_set: set[str] = field(default_factory=set)

    def remember(self, ids: tuple[str, ...]) -> None:
        # Only actionable IDs are deduped; bounded memory is intentional.
        for ident in ids:
            if len(self.decision_ids) == self.decision_ids.maxlen:
                evicted = self.decision_ids.popleft()
                self.decision_set.discard(evicted)
            self.decision_ids.append(ident)
            self.decision_set.add(ident)


class OfflineStrategyOrchestrator:
    """Deterministic in-memory dispatcher with binding-scoped fault quarantine.

    The host supplies a Stage-5 engine; this orchestrator doesn't start feeds.
    Each untrusted evaluator must be explicitly wrapped by Stage-4 isolation.
    Activation uses a revisioned local operator API, not Telegram callbacks.
    """

    def __init__(self, market_data: OfflineMarketDataEngine, *, enabled: bool = False,
                 max_bindings: int = 128) -> None:
        if (not isinstance(market_data, OfflineMarketDataEngine) or
                type(enabled) is not bool or
                type(max_bindings) is not int or not 1 <= max_bindings <= 1024):
            raise OrchestrationRefused("INVALID_ORCHESTRATOR_CONFIG")
        self.market_data = market_data
        self.enabled = enabled
        self.max_bindings = max_bindings
        self._slots: dict[str, _Slot] = {}
        self._lock = RLock()

    def attach(self, feed_id: str, manifest: CoreManifest, binding: CoreBinding,
               evaluator: TrustedCoreEvaluator | IsolatedCoreEvaluator) -> BindingStatus:
        """Registers inert event consumer, default disabled, without loading code."""
        if (type(feed_id) is not str or not isinstance(manifest, CoreManifest) or
                not isinstance(binding, CoreBinding) or
                type(evaluator) not in (TrustedCoreEvaluator, IsolatedCoreEvaluator) or
                evaluator.manifest != manifest):
            raise OrchestrationRefused("INVALID_EVALUATOR_OR_BINDING")
        with self._lock:
            if len(self._slots) >= self.max_bindings:
                raise OrchestrationRefused("BINDING_QUOTA_EXCEEDED")
            if binding.binding_id in self._slots:
                raise OrchestrationRefused("DUPLICATE_BINDING_ID")
            # Subscribe before committing our local state, for atomic registration.
            try:
                self.market_data.subscribe(feed_id, manifest, binding)
            except (MarketDataRefused, ValueError) as exc:
                raise OrchestrationRefused("FEED_BINDING_REJECTED") from exc
            self._slots[binding.binding_id] = _Slot(feed_id, manifest, binding, evaluator)
            return self.state(binding.binding_id)

    def set_enabled(self, binding_id: str, *, enabled: bool,
                    expected_revision: int, operator_ack: bool = False) -> BindingStatus:
        """Administrative analysis-only toggle. NEVER grants order/publication."""
        if (type(enabled) is not bool or type(expected_revision) is not int or
                operator_ack is not True):
            raise OrchestrationRefused("EXPLICIT_OPERATOR_REVISION_REQUIRED")
        with self._lock:
            slot = self._get(binding_id)
            if slot.revision != expected_revision:
                raise OrchestrationRefused("STALE_BINDING_REVISION")
            if enabled and slot.quarantined:
                raise OrchestrationRefused("QUARANTINED_BINDING_REQUIRES_NEW_REVIEW")
            slot.enabled = enabled
            slot.revision += 1
            return self.state(binding_id)

    def state(self, binding_id: str) -> BindingStatus:
        with self._lock:
            s = self._get(binding_id)
            return BindingStatus(
                s.binding.binding_id, s.binding.instance_id, s.feed_id,
                s.revision, s.enabled, s.quarantined, s.completed_events,
                s.refused_events, s.last_input_digest, s.last_observed_at,
                s.last_error_code,
            )

    def _get(self, binding_id: str) -> _Slot:
        try:
            return self._slots[binding_id]
        except (KeyError, TypeError) as exc:
            raise OrchestrationRefused("UNKNOWN_BINDING") from exc

    def ingest(self, packet: MarketPacket) -> OrchestratorReceipt:
        if not self.enabled:
            raise OrchestrationRefused("ORCHESTRATOR_DISABLED")
        # Serializes feed ingestion and result deduplication for one process.
        # Never a claim of parallel, persistent or multi-process orchestration.
        with self._lock:
            try:
                dispatch: MarketDispatch = self.market_data.ingest(packet)
            except MarketDataRefused as exc:
                raise OrchestrationRefused("MARKET_DATA_REFUSED") from exc
            if dispatch.status is PacketStatus.DUPLICATE:
                return OrchestratorReceipt(dispatch.feed_id, dispatch.sequence,
                                           dispatch.status, (), ())
            outcomes: list[OrchestratorOutcome] = []
            for delivery in dispatch.deliveries:
                slot = self._get(delivery.binding_id)
                event = delivery.event
                if slot.feed_id != dispatch.feed_id or event.binding != slot.binding:
                    raise OrchestrationRefused("INTERNAL_ROUTING_INCONSISTENCY")
                status = EvaluationStatus.EVALUATED
                result: CoreResult | None = None
                if slot.quarantined:
                    status = EvaluationStatus.QUARANTINED
                elif not slot.enabled:
                    status = EvaluationStatus.DISABLED
                elif slot.last_input_digest == event.input_digest:
                    status = EvaluationStatus.DUPLICATE
                elif slot.last_observed_at is not None and event.observed_at < slot.last_observed_at:
                    status = EvaluationStatus.STALE
                else:
                    try:
                        result = slot.evaluator.evaluate(event)
                        if not isinstance(result, CoreResult):
                            raise ValueError("NONCONTRACT_RESULT")
                        validate_core_result(slot.manifest, event, result)
                        actionable = tuple(d.decision_id for d in result.decisions
                                           if d.kind in (DecisionKind.ENTRY_INTENT,
                                                         DecisionKind.MANAGEMENT_INTENT,
                                                         DecisionKind.EXIT_INTENT))
                        if any(i in slot.decision_set for i in actionable):
                            raise ValueError("REUSED_ACTIONABLE_ID")
                        slot.remember(actionable)
                        slot.last_input_digest = event.input_digest
                        slot.last_observed_at = event.observed_at
                        slot.completed_events += 1
                    except Exception:
                        # Never leak plugin exceptions, secrets or raw output.
                        slot.refused_events += 1
                        slot.quarantined = True
                        slot.enabled = False
                        slot.revision += 1
                        slot.last_error_code = "EVALUATION_OR_RESULT_REJECTED"
                        status = EvaluationStatus.QUARANTINED
                        result = None
                outcomes.append(OrchestratorOutcome(
                    delivery.binding_id, delivery.instance_id, status,
                    event.input_digest, result, delivery.price_basis,
                    delivery.volume_semantics,
                ))
            return OrchestratorReceipt(dispatch.feed_id, dispatch.sequence,
                                       dispatch.status, tuple(outcomes),
                                       dispatch.waiting_bindings)


__all__ = [
    "BindingStatus", "EvaluationStatus", "IsolatedCoreEvaluator",
    "OfflineStrategyOrchestrator", "OrchestrationRefused", "OrchestratorOutcome",
    "OrchestratorReceipt", "TrustedCoreEvaluator",
]
