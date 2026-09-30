"""Unit tests for bounded administrator signal queries."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.signals.admin_query_service import AdminSignalQueryService
from app.modules.signals.entities import AdminSignalListMode, SignalRecord, SignalTargetRecord
from app.modules.signals.errors import InvalidSignalError
from app.modules.signals.models import SignalStatus, SignalTargetStatus

NOW = datetime(2026, 9, 2, 8, tzinfo=UTC)


def signal_record(
    signal_id: int = 7,
    *,
    status: str = SignalStatus.OPEN.value,
) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        leverage=Decimal("5"),
        status=status,
        description=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
    )


def target_record(target_id: int = 11) -> SignalTargetRecord:
    return SignalTargetRecord(
        id=target_id,
        signal_id=7,
        target_number=1,
        target_price=Decimal("110"),
        status=SignalTargetStatus.PENDING.value,
        hit_at=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> SimpleNamespace:
    return SimpleNamespace(
        count_admin_signals=AsyncMock(return_value=12),
        list_admin_signals=AsyncMock(return_value=(signal_record(),)),
        get_signal=AsyncMock(return_value=signal_record()),
        count_targets=AsyncMock(return_value=12),
        list_targets_page=AsyncMock(return_value=(target_record(),)),
    )


@pytest.mark.parametrize(
    ("mode", "statuses"),
    [
        (AdminSignalListMode.ACTIVE.value, (SignalStatus.OPEN.value,)),
        (
            AdminSignalListMode.HISTORY.value,
            (SignalStatus.CLOSED.value, SignalStatus.CANCELLED.value),
        ),
        (AdminSignalListMode.DRAFTS.value, (SignalStatus.DRAFT.value,)),
    ],
)
async def test_each_admin_mode_uses_an_allow_listed_status_query(
    mode: str,
    statuses: tuple[str, ...],
) -> None:
    repo = repository()

    page = await AdminSignalQueryService(repo).get_page(mode, page=2)

    assert page.page == page.total_pages == 2
    repo.count_admin_signals.assert_awaited_once_with(statuses=statuses)
    repo.list_admin_signals.assert_awaited_once_with(
        statuses=statuses,
        limit=10,
        offset=10,
    )


async def test_page_is_clamped_and_empty_collection_stays_on_page_one() -> None:
    repo = repository()
    repo.count_admin_signals.return_value = 0
    repo.list_admin_signals.return_value = ()

    page = await AdminSignalQueryService(repo).get_page("drafts", page=99)

    assert page.page == page.total_pages == 1
    assert page.signals == ()
    repo.list_admin_signals.assert_awaited_once_with(
        statuses=(SignalStatus.DRAFT.value,),
        limit=10,
        offset=0,
    )


async def test_admin_detail_clamps_target_page_and_loads_ten_targets() -> None:
    repo = repository()

    detail = await AdminSignalQueryService(repo).get_detail(7, target_page=99)

    assert detail.signal.id == 7
    assert detail.target_page == detail.total_target_pages == 2
    repo.get_signal.assert_awaited_once_with(7)
    repo.list_targets_page.assert_awaited_once_with(7, limit=10, offset=10)


@pytest.mark.parametrize(
    ("mode", "page", "page_size"),
    [
        ("public", 1, 10),
        ("active", 0, 10),
        ("active", True, 10),
        ("history", 1, 25),
    ],
)
async def test_invalid_admin_collection_input_is_rejected_before_database_access(
    mode: str,
    page: int,
    page_size: int,
) -> None:
    repo = repository()

    with pytest.raises(InvalidSignalError):
        await AdminSignalQueryService(repo).get_page(
            mode,
            page=page,
            page_size=page_size,
        )

    repo.count_admin_signals.assert_not_awaited()


@pytest.mark.parametrize(("signal_id", "target_page"), [(0, 1), (True, 1), (7, 0)])
async def test_invalid_admin_detail_is_rejected_before_database_access(
    signal_id: int,
    target_page: int,
) -> None:
    repo = repository()

    with pytest.raises(InvalidSignalError):
        await AdminSignalQueryService(repo).get_detail(
            signal_id,
            target_page=target_page,
        )

    repo.get_signal.assert_not_awaited()
