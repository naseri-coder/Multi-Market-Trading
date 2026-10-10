"""A22 public CUSTOM data-only PAPER runtime bridge for Multi Market Trading.

Only precomputed, operator-supplied A7 envelopes enter the fixed in-memory
provider. No strategy code, external network, binary loader, developer
callback, install, live feed, broker, Telegram or private NYFR entry point.
This is NOT an adversarial sandbox or a production adapter.
"""
from __future__ import annotations

import asyncio
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .a21_custom_contract import (
    CustomContractCatalog, CustomContractRefused, CustomEngineContract,
    inspect_custom_paper_fixture, parse_custom_contract,
)
from .contracts import EngineDescriptor, Instrument
from .external_abi import ExternalPaperEngine
from .paper_journal import PaperJournal
from .quotes import QuoteOrigin, QuoteTick, QuoteVerdict
from .registry import EngineRegistry
from .runtime import EngineBinding, MultiEngineRunner
from .sessions import SessionPolicy


class CustomRuntimeRefused(CustomContractRefused):
    """The public PAPER bridge failed a contract or permission fence."""


@dataclass(frozen=True, slots=True)
class CustomRuntimeState:
    engine_id: str
    descriptor_sha256: str
    enabled: bool
    revision: int
    mode: str = "PAPER_ONLY_DATA_BRIDGE"
    executable_installed: bool = False
    private_code_loaded: bool = False
    live_trading_permitted: bool = False
    commercial_entitlement_issued: bool = False


@dataclass(frozen=True, slots=True)
class CustomDispatchResult:
    status: str
    quote_verdict: QuoteVerdict
    submitted_engines: tuple[str, ...] = ()
    stored: int = 0
    duplicate: int = 0
    faulted_engines: tuple[str, ...] = ()
    live_trading_permitted: bool = False


class _FixedEnvelopeSlot:
    """One-shot immutable bytes, not an injected strategy or provider."""
    def __init__(self):
        self._packet: bytes | None = None

    async def produce(self, tick: QuoteTick) -> bytes | None:
        # A cooperative yield permits a toggle/revocation during dispatch;
        # A22 checks the revision again BEFORE any journal commit.
        await asyncio.sleep(0)
        packet, self._packet = self._packet, None
        return packet


class CustomPaperRuntimeBridge:
    """Separate public extension PAPER runtime; does not alter A8 semantics.

    A21 catalog is required to prove operator-pinned immutable registration.
    Existing A8 rejects public ExternalPaperEngine attachment; A22 uses the
    existing A7 ExternalPaperEngine + A2 MultiEngineRunner in a *distinct*
    operator-owned bridge with separate, default-disabled revisioned toggles.
    """

    def __init__(self, catalog: CustomContractCatalog, journal: PaperJournal, *,
                 paper_enabled: bool = False):
        if (type(catalog) is not CustomContractCatalog
                or type(journal) is not PaperJournal
                or type(paper_enabled) is not bool):
            raise CustomRuntimeRefused("A22_EXACT_PUBLIC_PAPER_DEPENDENCIES")
        self._catalog = catalog
        self._journal = journal
        self._registry = EngineRegistry()
        self._runner = MultiEngineRunner(self._registry, active=True)
        self._providers: dict[str, _FixedEnvelopeSlot] = {}
        self._contracts: dict[str, CustomEngineContract] = {}
        self._states: dict[str, CustomRuntimeState] = {}
        self._paper_enabled = paper_enabled
        self._epoch = 0
        self._gate = asyncio.Lock()

    def attach(self, raw: bytes, *, approved_sha256: str,
               instruments: frozenset[Instrument],
               session_policy: SessionPolicy, timeout_seconds: float = 1.0
               ) -> CustomRuntimeState:
        contract = parse_custom_contract(raw, approved_sha256=approved_sha256)
        if (contract.access_policy != "public_custom"
                or contract.protected_owner_core
                or contract.strategy_family != "generic_custom"):
            raise CustomRuntimeRefused("A22_OWNER_OR_COMMERCIAL_ENGINE_DENIED")
        if (not isinstance(instruments, frozenset) or not instruments
                or any(type(i) is not Instrument or i.market not in contract.markets
                       for i in instruments)
                or not isinstance(session_policy, SessionPolicy)
                or session_policy.verified is not True
                or type(timeout_seconds) not in (float, int)
                or not 0 < timeout_seconds <= 5):
            raise CustomRuntimeRefused("A22_VERIFIED_FIXED_PAPER_BINDING_REQUIRED")
        if contract.engine_id in self._states:
            raise CustomRuntimeRefused("A22_DUPLICATE_RUNTIME_BINDING")
        registered = tuple(x for x in self._catalog.owner_inventory()
                           if x.engine_id == contract.engine_id)
        if (len(registered) != 1
                or registered[0] != contract
                or self._catalog.public_lookup(contract.engine_id) is None):
            raise CustomRuntimeRefused("A22_A21_PUBLIC_PINNED_REGISTRATION_REQUIRED")
        descriptor = EngineDescriptor(
            contract.engine_id, contract.engine_version, contract.markets)
        binding = EngineBinding(descriptor, instruments, session_policy,
                                enabled=True, timeout_seconds=timeout_seconds)
        slot = _FixedEnvelopeSlot()
        self._registry.register(descriptor)
        self._runner.attach(binding, ExternalPaperEngine(
            contract.engine_id, contract.engine_version, slot))
        self._providers[contract.engine_id] = slot
        self._contracts[contract.engine_id] = registered[0]
        status = CustomRuntimeState(contract.engine_id,
                                    contract.approved_descriptor_sha256, False, 1)
        self._states[contract.engine_id] = status
        self._epoch += 1
        return status

    def status(self, engine_id: str) -> CustomRuntimeState:
        if engine_id not in self._states:
            raise CustomRuntimeRefused("A22_UNKNOWN_CUSTOM_ENGINE")
        return self._states[engine_id]

    def enable_paper(self, engine_id: str, *, approved_sha256: str,
                     expected_revision: int) -> CustomRuntimeState:
        """Explicit local operator opt-in: pin is NOT an authentication token."""
        state = self.status(engine_id)
        if (type(expected_revision) is not int
                or expected_revision != state.revision
                or type(approved_sha256) is not str
                or not hmac.compare_digest(approved_sha256, state.descriptor_sha256)):
            raise CustomRuntimeRefused("A22_OPERATOR_PIN_AND_CAS_REQUIRED")
        if state.enabled:
            raise CustomRuntimeRefused("A22_ALREADY_ENABLED")
        if not self._paper_enabled:
            raise CustomRuntimeRefused("A22_PLATFORM_PAPER_SWITCH_OFF")
        faulted, _ = self._runner.state(engine_id)
        if faulted:
            raise CustomRuntimeRefused("A22_FAULTED_NEEDS_SEPARATE_REBUILD")
        updated = CustomRuntimeState(engine_id, state.descriptor_sha256,
                                     True, state.revision + 1)
        self._states[engine_id] = updated
        self._epoch += 1
        return updated

    def disable(self, engine_id: str) -> CustomRuntimeState:
        """Fail-closed revocation always available; no secret or key required."""
        state = self.status(engine_id)
        updated = CustomRuntimeState(engine_id, state.descriptor_sha256,
                                     False, state.revision + 1)
        self._states[engine_id] = updated
        self._epoch += 1
        return updated

    def disable_all(self) -> None:
        for engine_id in tuple(self._states):
            self.disable(engine_id)
        self._paper_enabled = False
        self._epoch += 1

    async def dispatch(self, tick: QuoteTick, *,
                       packets: Mapping[str, bytes | None],
                       expected_revisions: Mapping[str, int],
                       now: datetime) -> CustomDispatchResult:
        """Only inject validated A7 PAPER envelopes for enabled public engines.

        A single tick is dispatched once to multiple engines. An invalid or
        unapproved packet rejects the ENTIRE batch before the runner/journal.
        Changes in permission/identity during await discard all outputs.
        """
        if type(tick) is not QuoteTick or tick.origin not in (
                QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC):
            raise CustomRuntimeRefused("A22_NO_LIVE_QUOTES")
        if (not isinstance(packets, dict) or not packets
                or len(packets) > 16
                or not isinstance(expected_revisions, dict)
                or set(expected_revisions) != set(packets)
                or any(type(k) is not str for k in packets)):
            raise CustomRuntimeRefused("A22_EXACT_BOUNDED_REVISIONED_BATCH")
        async with self._gate:
            if not self._paper_enabled:
                return CustomDispatchResult("PLATFORM_DISABLED", QuoteVerdict.UNVERIFIED)
            epoch = self._epoch
            approved: dict[str, bytes | None] = {}
            for engine_id, packet in packets.items():
                state = self.status(engine_id)
                if (not state.enabled
                        or type(expected_revisions[engine_id]) is not int
                        or expected_revisions[engine_id] != state.revision):
                    raise CustomRuntimeRefused("A22_ENGINE_DISABLED_OR_STALE_REVISION")
                contract = self._contracts[engine_id]
                if (contract.access_policy != "public_custom"
                        or contract.protected_owner_core
                        or self._catalog.public_lookup(engine_id) is None):
                    raise CustomRuntimeRefused("A22_PUBLIC_CONTRACT_REVOKED")
                if tick.instrument.market not in contract.markets:
                    raise CustomRuntimeRefused("A22_MARKET_NOT_ALLOWED")
                if packet is not None:
                    if type(packet) is not bytes or not 0 < len(packet) <= 8192:
                        raise CustomRuntimeRefused("A22_BOUNDED_BYTES_ONLY")
                    inspect_custom_paper_fixture(contract, packet, tick)
                approved[engine_id] = packet
            try:
                for engine_id, packet in approved.items():
                    self._providers[engine_id]._packet = packet
                result = await self._runner.process(
                    tick, now=now, trusted_live_source=False,
                    allowed_engine_ids=frozenset(approved))
            finally:
                for engine_id in approved:
                    self._providers[engine_id]._packet = None
            if (epoch != self._epoch or not self._paper_enabled
                    or any(self._states[ident].revision != expected_revisions[ident]
                           or not self._states[ident].enabled
                           for ident in approved)):
                return CustomDispatchResult("PERMISSION_CHANGED_IN_FLIGHT",
                                             result.quote_verdict)
            if result.quote_verdict is not QuoteVerdict.ACCEPTED:
                return CustomDispatchResult("QUOTE_REJECTED", result.quote_verdict)
            intents = tuple(intent for engine_id, batch in result.by_engine.items()
                            if engine_id in approved for intent in batch)
            counts = self._journal.record_batch(intents)
            return CustomDispatchResult(
                "ENGINE_FAULTED" if result.faulted_engines else "PAPER_RECORDED",
                result.quote_verdict, tuple(sorted(approved)),
                counts.inserted, counts.duplicate, result.faulted_engines)
