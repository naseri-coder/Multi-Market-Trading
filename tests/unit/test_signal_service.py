"""Unit tests for Phase 12 signal lifecycle rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.signals.entities import (
    CreateSignal,
    SignalEventRecord,
    SignalRecord,
    SignalTargetRecord,
    UpdateSignal,
)
from app.modules.signals.errors import InvalidSignalError, SignalStateError
from app.modules.signals.models import (
    SignalDirection,
    SignalEventType,
    SignalStatus,
    SignalTargetStatus,
)
from app.modules.signals.service import SignalService

NOW = datetime(2026, 9, 1, 20, tzinfo=UTC)


def signal_record(
    *,
    signal_id: int = 7,
    direction: str = SignalDirection.LONG.value,
    status: str = SignalStatus.OPEN.value,
    entry_price: Decimal = Decimal("100"),
    stop_loss: Decimal = Decimal("90"),
    description: str | None = "Setup",
) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol="BTC/USDT",
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        leverage=Decimal("5.00"),
        status=status,
        description=description,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
    )


def target_record(
    target_id: int,
    number: int,
    price: str,
    *,
    status: str = SignalTargetStatus.PENDING.value,
) -> SignalTargetRecord:
    return SignalTargetRecord(
        id=target_id,
        signal_id=7,
        target_number=number,
        target_price=Decimal(price),
        status=status,
        hit_at=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
    )


def repository(*, signal: SignalRecord | None = None) -> SimpleNamespace:
    current = signal or signal_record()
    return SimpleNamespace(
        create_signal=AsyncMock(return_value=current),
        get_signal=AsyncMock(return_value=current),
        update_signal=AsyncMock(return_value=current),
        list_targets=AsyncMock(return_value=()),
        get_target=AsyncMock(return_value=target_record(11, 1, "110")),
        create_target=AsyncMock(return_value=target_record(11, 1, "110")),
        mark_target_hit=AsyncMock(
            return_value=replace(
                target_record(11, 1, "110"),
                status=SignalTargetStatus.HIT.value,
                hit_at=NOW,
                profit_loss=Decimal("2.50"),
            )
        ),
        cancel_pending_targets=AsyncMock(return_value=2),
        append_event=AsyncMock(),
        list_events=AsyncMock(return_value=()),
    )


async def test_create_signal_normalizes_values_and_appends_created_event() -> None:
    created = signal_record(description="Momentum")
    repo = repository(signal=created)

    result = await SignalService(repo, clock=lambda: NOW).create_signal(
        CreateSignal(
            symbol=" btc/usdt ",
            direction=" long ",
            entry_price="100.000000000000000001",
            stop_loss="90",
            leverage="5.50",
            description="  Momentum  ",
        )
    )

    assert result is created
    submitted = repo.create_signal.await_args.kwargs
    assert submitted["values"] == {
        "symbol": "BTC/USDT",
        "direction": SignalDirection.LONG.value,
        "entry_price": Decimal("100.000000000000000001"),
        "stop_loss": Decimal("90"),
        "leverage": Decimal("5.50"),
        "status": SignalStatus.OPEN.value,
        "description": "Momentum",
    }
    assert submitted["created_at"] == NOW
    event = repo.append_event.await_args.kwargs
    assert event["event_type"] == SignalEventType.CREATED.value
    assert event["metadata"]["entry_price"] == "100"


async def test_create_draft_uses_draft_status() -> None:
    draft = signal_record(status=SignalStatus.DRAFT.value)
    repo = repository(signal=draft)

    await SignalService(repo, clock=lambda: NOW).create_signal(
        CreateSignal("ETH/USDT", "SHORT", "100", "110", "3", as_draft=True)
    )

    assert repo.create_signal.await_args.kwargs["values"]["status"] == SignalStatus.DRAFT.value


async def test_publish_signal_opens_only_a_draft_and_appends_audit_event() -> None:
    draft = signal_record(status=SignalStatus.DRAFT.value)
    published = replace(draft, status=SignalStatus.OPEN.value, updated_at=NOW)
    repo = repository(signal=draft)
    repo.update_signal.return_value = published

    result = await SignalService(repo, clock=lambda: NOW).publish_signal(7)

    assert result is published
    repo.get_signal.assert_awaited_once_with(7, for_update=True)
    repo.update_signal.assert_awaited_once_with(
        7,
        values={"status": SignalStatus.OPEN.value},
        updated_at=NOW,
    )
    event = repo.append_event.await_args.kwargs
    assert event["event_type"] == SignalEventType.PUBLISHED.value
    assert event["metadata"] == {"previous_status": SignalStatus.DRAFT.value}


async def test_publish_signal_rejects_non_draft_without_mutation() -> None:
    repo = repository(signal=signal_record(status=SignalStatus.OPEN.value))

    with pytest.raises(SignalStateError, match="draft"):
        await SignalService(repo).publish_signal(7)

    repo.update_signal.assert_not_awaited()
    repo.append_event.assert_not_awaited()


@pytest.mark.parametrize(
    "command",
    [
        CreateSignal("", "LONG", "100", "90", "2"),
        CreateSignal("BTC USDT", "LONG", "100", "90", "2"),
        CreateSignal("BTC/USDT", "SIDEWAYS", "100", "90", "2"),
        CreateSignal("BTC/USDT", "LONG", "100", "100", "2"),
        CreateSignal("BTC/USDT", "SHORT", "100", "99", "2"),
        CreateSignal("BTC/USDT", "LONG", 100.0, "90", "2"),
        CreateSignal("BTC/USDT", "LONG", "NaN", "90", "2"),
        CreateSignal("BTC/USDT", "LONG", "100", "90", "1.001"),
        CreateSignal("BTC/USDT", "LONG", "100", "90", "2", description="x" * 4001),
    ],
)
async def test_invalid_create_inputs_never_reach_repository(command: CreateSignal) -> None:
    repo = repository()

    with pytest.raises(InvalidSignalError):
        await SignalService(repo).create_signal(command)

    repo.create_signal.assert_not_awaited()


async def test_open_update_allows_metadata_but_rejects_core_market_changes() -> None:
    current = signal_record()
    updated = replace(current, symbol="BTCUSDT", description="Updated")
    repo = repository(signal=current)
    repo.update_signal.return_value = updated
    service = SignalService(repo, clock=lambda: NOW)

    result = await service.update_signal(
        current.id,
        UpdateSignal(symbol=" btcusdt ", description=" Updated "),
    )

    assert result is updated
    assert repo.update_signal.await_args.kwargs["values"] == {
        "symbol": "BTCUSDT",
        "description": "Updated",
    }
    changes = repo.append_event.await_args.kwargs["metadata"]["changes"]
    assert changes["symbol"] == {"old": "BTC/USDT", "new": "BTCUSDT"}

    with pytest.raises(SignalStateError):
        await service.update_signal(current.id, UpdateSignal(entry_price="101"))


async def test_draft_update_revalidates_stop_and_existing_targets() -> None:
    draft = signal_record(status=SignalStatus.DRAFT.value)
    repo = repository(signal=draft)
    repo.list_targets.return_value = (target_record(11, 1, "110"),)
    service = SignalService(repo)

    with pytest.raises(InvalidSignalError, match="targets conflict"):
        await service.update_signal(draft.id, UpdateSignal(entry_price="115"))

    with pytest.raises(InvalidSignalError, match="stop loss"):
        await service.update_signal(draft.id, UpdateSignal(stop_loss="105"))


async def test_update_rejects_noop_and_closed_signal() -> None:
    repo = repository()
    service = SignalService(repo)

    with pytest.raises(InvalidSignalError, match="does not contain"):
        await service.update_signal(7, UpdateSignal(symbol="BTC/USDT"))

    repo.get_signal.return_value = replace(
        signal_record(),
        status=SignalStatus.CLOSED.value,
        closed_at=NOW,
        profit_loss=Decimal("1"),
    )
    with pytest.raises(SignalStateError):
        await service.update_signal(7, UpdateSignal(description="new"))


async def test_add_target_assigns_order_and_enforces_directional_geometry() -> None:
    repo = repository()
    repo.list_targets.return_value = (
        target_record(11, 1, "110"),
        target_record(12, 2, "120"),
    )
    repo.create_target.return_value = target_record(13, 3, "130")
    service = SignalService(repo, clock=lambda: NOW)

    target = await service.add_target(7, target_price="130")

    assert target.target_number == 3
    assert repo.create_target.await_args.kwargs["target_number"] == 3
    assert repo.append_event.await_args.kwargs["event_type"] == SignalEventType.TARGET_ADDED.value

    with pytest.raises(InvalidSignalError):
        await service.add_target(7, target_price="120")


async def test_short_targets_must_decrease_below_entry() -> None:
    short = signal_record(
        direction=SignalDirection.SHORT.value,
        stop_loss=Decimal("110"),
    )
    repo = repository(signal=short)
    repo.list_targets.return_value = (target_record(11, 1, "90"),)
    service = SignalService(repo)

    with pytest.raises(InvalidSignalError):
        await service.add_target(7, target_price="95")


async def test_hit_target_requires_open_signal_pending_target_and_order() -> None:
    first = target_record(11, 1, "110")
    second = target_record(12, 2, "120")
    repo = repository()
    repo.get_target.return_value = second
    repo.list_targets.return_value = (first, second)
    service = SignalService(repo, clock=lambda: NOW)

    with pytest.raises(SignalStateError, match="Earlier"):
        await service.hit_target(7, 12, profit_loss="4.25")

    repo.list_targets.return_value = (
        replace(
            first,
            status=SignalTargetStatus.HIT.value,
            hit_at=NOW,
            profit_loss=Decimal("2"),
        ),
        second,
    )
    repo.mark_target_hit.return_value = replace(
        second,
        status=SignalTargetStatus.HIT.value,
        hit_at=NOW,
        profit_loss=Decimal("4.25"),
    )

    result = await service.hit_target(7, 12, profit_loss="4.25")

    assert result.status == SignalTargetStatus.HIT.value
    assert repo.mark_target_hit.await_args.kwargs["profit_loss"] == Decimal("4.25")
    assert repo.append_event.await_args.kwargs["event_type"] == SignalEventType.TARGET_HIT.value


async def test_update_stop_loss_only_tightens_risk_and_can_cross_entry() -> None:
    current = signal_record(stop_loss=Decimal("90"))
    repo = repository(signal=current)
    repo.update_signal.return_value = replace(current, stop_loss=Decimal("105"))
    service = SignalService(repo, clock=lambda: NOW)

    updated = await service.update_stop_loss(7, stop_loss="105")

    assert updated.stop_loss == Decimal("105")
    assert repo.append_event.await_args.kwargs["metadata"] == {
        "old_stop_loss": "90",
        "new_stop_loss": "105",
    }

    with pytest.raises(SignalStateError):
        await service.update_stop_loss(7, stop_loss="89")


async def test_update_stop_loss_records_management_reason() -> None:
    current = signal_record(stop_loss=Decimal("90"))
    repo = repository(signal=current)
    repo.update_signal.return_value = replace(current, stop_loss=Decimal("100"))
    service = SignalService(repo, clock=lambda: NOW)

    await service.update_stop_loss(7, stop_loss="100", reason="BREAKEVEN")

    assert repo.append_event.await_args.kwargs["event_type"] == SignalEventType.STOP_LOSS_UPDATED.value
    assert repo.append_event.await_args.kwargs["metadata"] == {
        "old_stop_loss": "90",
        "new_stop_loss": "100",
        "reason": "BREAKEVEN",
    }


async def test_short_stop_loss_only_moves_downward() -> None:
    short = signal_record(
        direction=SignalDirection.SHORT.value,
        stop_loss=Decimal("110"),
    )
    repo = repository(signal=short)
    service = SignalService(repo)

    with pytest.raises(SignalStateError):
        await service.update_stop_loss(7, stop_loss="111")


async def test_close_signal_persists_result_cancels_pending_targets_and_audits() -> None:
    current = signal_record()
    closed = replace(
        current,
        status=SignalStatus.CLOSED.value,
        profit_loss=Decimal("-1.25"),
        closed_at=NOW,
    )
    repo = repository(signal=current)
    repo.update_signal.return_value = closed

    result = await SignalService(repo, clock=lambda: NOW).close_signal(
        7,
        profit_loss="-1.25",
    )

    assert result is closed
    assert repo.update_signal.await_args.kwargs["values"]["status"] == SignalStatus.CLOSED.value
    repo.cancel_pending_targets.assert_awaited_once_with(7, changed_at=NOW)
    event = repo.append_event.await_args.kwargs
    assert event["event_type"] == SignalEventType.CLOSED.value
    assert event["metadata"] == {"profit_loss": "-1.25", "cancelled_targets": 2}


async def test_cancel_signal_supports_draft_and_open_but_not_terminal_states() -> None:
    draft = signal_record(status=SignalStatus.DRAFT.value)
    cancelled = replace(draft, status=SignalStatus.CANCELLED.value, closed_at=NOW)
    repo = repository(signal=draft)
    repo.update_signal.return_value = cancelled
    service = SignalService(repo, clock=lambda: NOW)

    result = await service.cancel_signal(7)

    assert result.status == SignalStatus.CANCELLED.value
    assert repo.append_event.await_args.kwargs["event_type"] == SignalEventType.CANCELLED.value

    repo.get_signal.return_value = cancelled
    with pytest.raises(SignalStateError):
        await service.cancel_signal(7)


async def test_signal_history_verifies_signal_and_forwards_safe_pagination() -> None:
    event = SignalEventRecord(1, 7, SignalEventType.CREATED.value, {}, NOW)
    repo = repository()
    repo.list_events.return_value = (event,)
    service = SignalService(repo)

    result = await service.signal_history(7, limit=25, offset=50)

    assert result == (event,)
    repo.get_signal.assert_awaited_once_with(7)
    repo.list_events.assert_awaited_once_with(7, limit=25, offset=50)

    for limit, offset in ((0, 0), (101, 0), (20, -1)):
        with pytest.raises(InvalidSignalError):
            await service.signal_history(7, limit=limit, offset=offset)


async def test_clock_must_return_timezone_aware_datetime() -> None:
    repo = repository()
    service = SignalService(repo, clock=lambda: datetime(2026, 9, 1))

    with pytest.raises(RuntimeError, match="aware datetime"):
        await service.cancel_signal(7)
