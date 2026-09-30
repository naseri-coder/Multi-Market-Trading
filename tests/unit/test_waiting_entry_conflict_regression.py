from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport
from app.modules.signal_automation.conflict_guard import (
    SignalConflictCategory,
    SignalConflictContext,
    check_signal_conflict,
)
from app.modules.signal_automation.service import BrooksSignalIntegrationService


class _Tx:
    def __init__(self, session): self.session = session
    async def __aenter__(self): self.session.begins += 1; return self
    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None: self.session.commits += 1
        else: self.session.rollbacks += 1
        return False


class _Session:
    def __init__(self): self.begins = self.commits = self.rollbacks = 0
    def begin(self): return _Tx(self)


def _command(direction="SHORT"):
    if direction == "LONG":
        entry, stop, targets = Decimal("76000"), Decimal("75000"), (Decimal("77000"), Decimal("78000"))
    else:
        entry, stop, targets = Decimal("76000"), Decimal("77000"), (Decimal("75000"), Decimal("74000"))
    return BrooksSignalImport(
        source_signal_id="btc-20260915-1500", symbol="BTCUSDT", direction=direction,
        entry_price=entry, stop_loss=stop,
        targets=targets, leverage=Decimal("1"),
        exchange="binance", market_type="futures", timeframe="1h",
        setup_type="BREAKOUT_PULLBACK_SHORT", market_snapshot_id="snap-1500",
        market_snapshot_hash="hash-1500", engine_version="core-v5",
        rule_set_version="rules-v6", configuration_version="cfg",
        reasoning=("final gate passed",), rule_ids=("BR",), failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR", "PASS", (1,)),),
        generation_mode="LIVE", publication_scope="VIP",
        counts_toward_performance=True,
    )


@pytest.mark.asyncio
async def test_stale_waiting_entry_is_not_active_opposite_conflict() -> None:
    session = _Session()
    auto = AsyncMock()
    auto.get_by_idempotency_key.return_value = None
    auto.get_signal_conflict_contexts.return_value = (SimpleNamespace(
        signal_id=70, direction="LONG", signal_status="OPEN", lifecycle_state="WAITING_ENTRY",
        entry_activated_at=None, last_market_price=Decimal("76251.06"),
        stop_loss=Decimal("81267.76"),
    ),)
    signal_service = AsyncMock()
    signal_service.create_signal.return_value = SimpleNamespace(id=999)
    service = BrooksSignalIntegrationService(
        session, automation_repository_factory=lambda _: auto,
        signal_service_factory=lambda _: signal_service,
    )
    result = await service.import_signal(_command())

    assert result.created is True
    assert result.signal_id == 999
    assert result.disposition == "STALE_SIGNAL_RECONCILED"
    signal_service.cancel_signal.assert_awaited_once()
    auto.complete_reconciled_pending_lifecycle.assert_awaited_once()
    signal_service.create_signal.assert_awaited_once()
    assert session.commits == 1


def _ctx(
    *, signal_id: int, direction: str = "LONG", state: str | None = "WAITING_ENTRY",
    activated: bool = False, last_price: str = "82000", stop: str = "81267.76",
):
    return SimpleNamespace(
        signal_id=signal_id, direction=direction, signal_status="OPEN",
        lifecycle_state=state,
        entry_activated_at=(datetime(2026, 9, 15, 12, tzinfo=UTC) if activated else None),
        last_market_price=Decimal(last_price), stop_loss=Decimal(stop),
    )


async def _service_result(contexts, *, direction="SHORT"):
    session = _Session()
    auto = AsyncMock()
    auto.get_by_idempotency_key.return_value = None
    auto.get_signal_conflict_contexts.return_value = tuple(contexts)
    signal_service = AsyncMock()
    signal_service.create_signal.return_value = SimpleNamespace(id=999)
    service = BrooksSignalIntegrationService(
        session, automation_repository_factory=lambda _: auto,
        signal_service_factory=lambda _: signal_service,
    )
    return await service.import_signal(_command(direction)), auto, signal_service


@pytest.mark.asyncio
async def test_valid_pending_opposite_blocks_without_reconciliation() -> None:
    result, auto, signal_service = await _service_result((
        _ctx(signal_id=80, last_price="82000"),
    ))
    assert result.created is False
    assert result.signal_id == 80
    assert result.disposition == "SKIPPED_VALID_PENDING_CONFLICT"
    signal_service.cancel_signal.assert_not_awaited()
    signal_service.create_signal.assert_not_awaited()
    auto.complete_reconciled_pending_lifecycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_pending_same_direction_has_own_pending_conflict() -> None:
    result, _, signal_service = await _service_result((
        _ctx(signal_id=81, last_price="82000"),
    ), direction="LONG")
    assert result.created is False
    assert result.disposition == "SKIPPED_VALID_PENDING_CONFLICT"
    signal_service.create_signal.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_opposite_blocks_even_when_newer_pending_is_stale() -> None:
    active = _ctx(signal_id=82, direction="LONG", state="ACTIVE", activated=True)
    newer_stale = _ctx(
        signal_id=83, direction="LONG", state="WAITING_ENTRY",
        activated=False, last_price="76000",
    )
    result, auto, signal_service = await _service_result((newer_stale, active))
    assert result.created is False
    assert result.signal_id == 82
    assert result.disposition == "SKIPPED_ACTIVE_POSITION_CONFLICT"
    signal_service.cancel_signal.assert_not_awaited()
    signal_service.create_signal.assert_not_awaited()
    auto.complete_reconciled_pending_lifecycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_stale_pending_rows_reconcile_before_new_signal() -> None:
    stale = (
        _ctx(signal_id=90, last_price="76000"),
        _ctx(signal_id=91, last_price="75000"),
    )
    result, auto, signal_service = await _service_result(stale)
    assert result.created is True
    assert result.disposition == "STALE_SIGNAL_RECONCILED"
    assert signal_service.cancel_signal.await_count == 2
    assert auto.complete_reconciled_pending_lifecycle.await_count == 2
    signal_service.create_signal.assert_awaited_once()


@pytest.mark.asyncio
async def test_older_active_not_hidden_by_newer_valid_waiting_entry() -> None:
    older_active = _ctx(signal_id=100, direction="LONG", state="ACTIVE", activated=True)
    newer_pending = _ctx(
        signal_id=101, direction="LONG", state="WAITING_ENTRY",
        activated=False, last_price="82000",
    )
    result, auto, signal_service = await _service_result((newer_pending, older_active))
    assert result.created is False
    assert result.signal_id == 100
    assert result.disposition == "SKIPPED_ACTIVE_POSITION_CONFLICT"
    signal_service.cancel_signal.assert_not_awaited()
    signal_service.create_signal.assert_not_awaited()
    auto.complete_reconciled_pending_lifecycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_open_rows_use_lifecycle_semantics_not_newest_row_only() -> None:
    older_active = _ctx(signal_id=110, direction="LONG", state="ACTIVE", activated=True)
    newer_pending = _ctx(
        signal_id=111, direction="LONG", state="WAITING_ENTRY",
        activated=False, last_price="82000",
    )
    newest_stale = _ctx(
        signal_id=112, direction="LONG", state="WAITING_ENTRY",
        activated=False, last_price="76000",
    )
    result, auto, signal_service = await _service_result((newest_stale, newer_pending, older_active))
    assert result.created is False
    assert result.signal_id == 110
    assert result.disposition == "SKIPPED_ACTIVE_POSITION_CONFLICT"
    signal_service.cancel_signal.assert_not_awaited()
    signal_service.create_signal.assert_not_awaited()
    auto.complete_reconciled_pending_lifecycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_same_direction_preserves_existing_allow_policy() -> None:
    active = _ctx(signal_id=120, direction="LONG", state="ACTIVE", activated=True)
    result, _, signal_service = await _service_result((active,), direction="LONG")
    assert result.created is True
    assert result.disposition == "CREATED"
    signal_service.create_signal.assert_awaited_once()


def test_waiting_entry_is_never_classified_as_active_position() -> None:
    pending = SignalConflictContext(
        signal_id=121, direction="LONG", signal_status="OPEN",
        lifecycle_state="WAITING_ENTRY", entry_activated_at=None,
        last_market_price=Decimal("82000"), stop_loss=Decimal("81267.76"),
    )
    decision = check_signal_conflict(pending, "SHORT")
    assert decision.allowed is False
    assert decision.category == SignalConflictCategory.VALID_PENDING_ENTRY_CONFLICT
    assert decision.reason == "VALID_PENDING_OPPOSITE_SIGNAL_EXISTS"


def test_active_state_without_activation_timestamp_is_not_active_position() -> None:
    inconsistent = SignalConflictContext(
        signal_id=123, direction="LONG", signal_status="OPEN",
        lifecycle_state="ACTIVE", entry_activated_at=None,
        last_market_price=Decimal("82000"), stop_loss=Decimal("81267.76"),
    )
    decision = check_signal_conflict(inconsistent, "SHORT")
    assert decision.allowed is False
    assert decision.category == SignalConflictCategory.VALID_PENDING_ENTRY_CONFLICT
    assert decision.reason == "UNACTIVATED_OR_INCONSISTENT_LIFECYCLE_CONFLICT"


def test_stale_pending_has_explicit_stale_category() -> None:
    stale = SignalConflictContext(
        signal_id=70, direction="LONG", signal_status="OPEN",
        lifecycle_state="WAITING_ENTRY", entry_activated_at=None,
        last_market_price=Decimal("76251.06"), stop_loss=Decimal("81267.76"),
    )
    decision = check_signal_conflict(stale, "SHORT")
    assert decision.allowed is True
    assert decision.category == SignalConflictCategory.STALE_OR_INVALID_PENDING
    assert decision.reconcile_stale is True
    assert decision.reason == "STALE_PENDING_STRUCTURAL_INVALIDATION"


@pytest.mark.parametrize("status", ["CLOSED", "CANCELLED"])
def test_non_open_signal_rows_do_not_block(status: str) -> None:
    old = SignalConflictContext(
        signal_id=122, direction="LONG", signal_status=status,
        lifecycle_state="COMPLETE", entry_activated_at=None,
        last_market_price=Decimal("76000"), stop_loss=Decimal("81267.76"),
    )
    decision = check_signal_conflict(old, "SHORT")
    assert decision.allowed is True
    assert decision.category == SignalConflictCategory.NO_CONFLICT
