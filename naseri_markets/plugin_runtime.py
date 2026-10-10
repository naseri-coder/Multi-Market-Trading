"""A8 unified PUBLIC/PRIVATE plugin controls for offline PAPER simulations.

Disabled by default. No dynamic imports, remote connection, credential reads,
process spawning, Telegram sends, broker orders, or real-private-code loading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .external_abi import ExternalPaperEngine
from .paper_journal import PaperJournal
from .plugin_manager import PluginManager
from .quotes import QuoteOrigin, QuoteTick, QuoteVerdict
from .registry import EngineRegistry
from .runtime import EngineBinding, MultiEngineRunner, QuoteEngine


@dataclass(frozen=True, slots=True)
class ManagedResult:
    status: str
    quote_verdict: QuoteVerdict
    stored: int = 0
    duplicate: int = 0
    faults: tuple[str, ...] = ()


class ManagedPaperPlatform:
    """An A8 operator-driven development facade; NOT a live process sandbox."""

    def __init__(
        self, manager: PluginManager, registry: EngineRegistry,
        runner: MultiEngineRunner, journal: PaperJournal, *,
        enabled: bool = False,
    ) -> None:
        self._manager = manager
        self._registry = registry
        self._runner = runner
        self._journal = journal
        self._enabled = enabled
        self._binding_incarnations: dict[str, int] = {}

    def attach(self, binding: EngineBinding, engine: QuoteEngine) -> None:
        """Bind an operator-provided adapter; never discover or load from disk."""
        identity = binding.descriptor.engine_id
        state = self._manager.get(identity)
        if state is None:
            raise ValueError("A8_PLUGIN_MUST_BE_REGISTERED")
        if (
            state.engine_version != binding.descriptor.version
            or state.markets != frozenset(
                market.value for market in binding.descriptor.supported_markets
            )
        ):
            raise ValueError("A8_DESCRIPTOR_AND_BINDING_MISMATCH")
        # In-process public engines and private mock external-envelope adapters
        # are separate integration contracts, not a code-isolation guarantee.
        if state.visibility == "private" and not isinstance(engine, ExternalPaperEngine):
            raise ValueError("A8_PRIVATE_EXTERNAL_CONTRACT_REQUIRED")
        if state.visibility == "public" and isinstance(engine, ExternalPaperEngine):
            raise ValueError("A8_PUBLIC_IN_PROCESS_CONTRACT_REQUIRED")
        existing = self._registry.get(identity)
        if existing is None:
            self._registry.register(binding.descriptor)
        elif existing != binding.descriptor:
            raise ValueError("A8_REGISTRY_CONFLICT")
        self._runner.attach(binding, engine)
        self._binding_incarnations[identity] = self._manager.incarnation(identity)

    def available_settings(self) -> tuple:
        """Presentation-friendly settings; toggles are applied via PluginManager."""
        return self._manager.list()

    async def process(self, tick: QuoteTick, *, now: datetime) -> ManagedResult:
        if tick.origin not in (QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC):
            raise ValueError("A8_LIVE_QUOTES_FORBIDDEN")
        if not self._enabled:
            return ManagedResult("DISABLED", QuoteVerdict.UNVERIFIED)
        original = self._manager.allowed_paper_engines()
        allowed = frozenset(
            engine_id for engine_id, state in original.items()
            if state.engine_version == (
                self._registry.get(engine_id).version
                if self._registry.get(engine_id) else None
            )
            and tick.instrument.market.value in state.markets
            and self._binding_incarnations.get(engine_id) == (
                self._manager.incarnation(engine_id)
            )
        )
        if not allowed:
            return ManagedResult("NO_ENABLED_BOUND_ENGINES", QuoteVerdict.UNVERIFIED)
        result = await self._runner.process(
            tick, now=now, trusted_live_source=False,
            allowed_engine_ids=allowed,
        )
        # A toggle, replacement or version edit during await invalidates the
        # whole batch, preventing a stale async callback from being persisted.
        current = self._manager.allowed_paper_engines()
        if any(
            current.get(ident) != original[ident]
            or self._manager.incarnation(ident) != self._binding_incarnations.get(ident)
            for ident in allowed
        ):
            return ManagedResult("SETTINGS_CHANGED_IN_FLIGHT", result.quote_verdict)
        if result.quote_verdict is not QuoteVerdict.ACCEPTED:
            return ManagedResult("QUOTE_REJECTED", result.quote_verdict)
        signals = tuple(
            signal for engine_id, batch in result.by_engine.items()
            if engine_id in allowed for signal in batch
        )
        counts = self._journal.record_batch(signals)
        return ManagedResult(
            "ENGINE_FAULTED" if result.faulted_engines else "RECORDED",
            result.quote_verdict, counts.inserted, counts.duplicate,
            result.faulted_engines,
        )
