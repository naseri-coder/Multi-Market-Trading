"""Explicit opt-in, isolated, bounded, quote-driven engine execution.

No dynamic imports, credential reads, external API calls, database writes or
Telegram sends. This is an in-process development runner, not a deployed bot.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from .contracts import EngineDescriptor, EvidenceMode, Instrument, SignalIntent
from .quotes import QuoteOrigin, QuoteQualityGate, QuoteTick, QuoteVerdict
from .registry import EngineRegistry
from .sessions import SessionPolicy


class QuoteEngine(Protocol):
    engine_id: str
    engine_version: str

    async def on_quote(self, tick: QuoteTick) -> Sequence[SignalIntent]: ...


@dataclass(frozen=True, slots=True)
class EngineBinding:
    descriptor: EngineDescriptor
    instruments: frozenset[Instrument]
    session_policy: SessionPolicy
    enabled: bool = False
    timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        if (
            not self.instruments
            or any(i.market not in self.descriptor.supported_markets for i in self.instruments)
            or not isinstance(self.session_policy, SessionPolicy)
            or not 0 < self.timeout_seconds <= 30
        ):
            raise ValueError("invalid engine binding")


@dataclass(frozen=True, slots=True)
class DispatchResult:
    quote_verdict: QuoteVerdict
    by_engine: dict[str, tuple[SignalIntent, ...]]
    faulted_engines: tuple[str, ...]


@dataclass(slots=True)
class _Slot:
    binding: EngineBinding
    engine: QuoteEngine
    faulted: bool = False
    error_code: str | None = None


class MultiEngineRunner:
    """Fail-closed and explicitly activated; malformed engines are quarantined."""

    def __init__(self, registry: EngineRegistry, *, active: bool = False,
                 quality_gate: QuoteQualityGate | None = None) -> None:
        self._registry = registry
        self._active = active
        self._gate = quality_gate or QuoteQualityGate()
        self._slots: dict[str, _Slot] = {}
        self._seen: set[tuple[str, str]] = set()  # ephemeral only; A3 adds durable idempotency

    def attach(self, binding: EngineBinding, engine: QuoteEngine) -> None:
        if self._registry.get(binding.descriptor.engine_id) != binding.descriptor:
            raise ValueError("engine not registered with exact version")
        if (engine.engine_id != binding.descriptor.engine_id
                or engine.engine_version != binding.descriptor.version):
            raise ValueError("engine implementation identity mismatch")
        if engine.engine_id in self._slots:
            raise ValueError("duplicate runtime engine")
        self._slots[engine.engine_id] = _Slot(binding, engine)

    def reset_engine(self, engine_id: str) -> None:
        """Explicit operator action; does not bypass feed quality quarantine."""
        slot = self._slots[engine_id]
        slot.faulted = False
        slot.error_code = None

    async def process(self, tick: QuoteTick, *, now, trusted_live_source: bool = False
                      ) -> DispatchResult:
        if not self._active:
            return DispatchResult(QuoteVerdict.UNVERIFIED, {}, ())
        quality = self._gate.inspect(tick, now=now, trusted_live_source=trusted_live_source)
        if quality is not QuoteVerdict.ACCEPTED:
            return DispatchResult(quality, {}, ())
        outputs: dict[str, tuple[SignalIntent, ...]] = {}
        faults: list[str] = []
        for engine_id, slot in self._slots.items():
            bind = slot.binding
            if slot.faulted or not bind.enabled or tick.instrument not in bind.instruments:
                continue
            if not bind.session_policy.is_open(tick.occurred_at):
                continue
            try:
                produced = await asyncio.wait_for(
                    slot.engine.on_quote(tick), timeout=bind.timeout_seconds
                )
                if not isinstance(produced, (tuple, list)):
                    raise ValueError("engine must return a sequence")
                validated: list[SignalIntent] = []
                batch_keys: set[tuple[str, str]] = set()
                for intent in produced:
                    if not isinstance(intent, SignalIntent):
                        raise ValueError("non-contract output")
                    self._registry.validate_intent(intent)
                    if (intent.engine_id != engine_id or intent.instrument != tick.instrument
                            or intent.observed_at != tick.occurred_at):
                        raise ValueError("cross-engine or noncausal output")
                    if (tick.origin is not QuoteOrigin.LIVE
                            and intent.evidence_mode is EvidenceMode.FORWARD):
                        raise ValueError("replay cannot claim forward evidence")
                    key = (engine_id, intent.signal_id)
                    if key in self._seen or key in batch_keys:
                        raise ValueError("duplicate signal identity")
                    validated.append(intent)
                    batch_keys.add(key)
                self._seen.update(batch_keys)
                outputs[engine_id] = tuple(validated)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                slot.faulted = True
                slot.error_code = type(exc).__name__
                faults.append(engine_id)
        return DispatchResult(quality, outputs, tuple(faults))

    def state(self, engine_id: str) -> tuple[bool, str | None]:
        slot = self._slots[engine_id]
        return slot.faulted, slot.error_code
