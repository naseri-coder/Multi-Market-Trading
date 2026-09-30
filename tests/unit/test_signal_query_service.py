"""Unit tests for public signal visibility and pagination."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.signals.entities import SignalListMode, SignalRecord, SignalTargetRecord
from app.modules.signals.errors import InvalidSignalError
from app.modules.signals.models import SignalStatus, SignalTargetStatus
from app.modules.signals.query_service import LIVE_WINDOW, SignalQueryService

NOW = datetime(2026, 9, 2, 12, tzinfo=UTC)


def signal_record(signal_id: int = 7) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        leverage=Decimal("5"),
        status=SignalStatus.OPEN.value,
        description=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
    )


def target_record(target_id: int, number: int) -> SignalTargetRecord:
    return SignalTargetRecord(
        id=target_id,
        signal_id=7,
        target_number=number,
        target_price=Decimal(100 + number),
        status=SignalTargetStatus.PENDING.value,
        hit_at=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> SimpleNamespace:
    return SimpleNamespace(
        count_public_signals=AsyncMock(return_value=21),
        list_public_signals=AsyncMock(return_value=(signal_record(),)),
        get_public_signal=AsyncMock(return_value=signal_record()),
        count_targets=AsyncMock(return_value=21),
        list_targets_page=AsyncMock(return_value=(target_record(1, 1),)),
    )


async def test_live_page_uses_one_stable_24_hour_cutoff_and_database_offset() -> None:
    repo = repository()
    service = SignalQueryService(repo, clock=lambda: NOW)

    page = await service.get_page(SignalListMode.LIVE.value, page=2)

    assert page.mode == SignalListMode.LIVE.value
    assert page.page == 2
    assert page.page_size == 10
    assert page.total_items == 21
    assert page.total_pages == 3
    expected_cutoff = NOW - LIVE_WINDOW
    repo.count_public_signals.assert_awaited_once_with(
        mode=SignalListMode.LIVE.value,
        live_since=expected_cutoff,
    )
    repo.list_public_signals.assert_awaited_once_with(
        mode=SignalListMode.LIVE.value,
        live_since=expected_cutoff,
        limit=10,
        offset=10,
    )


async def test_page_above_last_page_is_clamped_before_query() -> None:
    repo = repository()
    repo.count_public_signals.return_value = 11

    page = await SignalQueryService(repo).get_page(SignalListMode.OPEN.value, page=99)

    assert page.page == 2
    repo.list_public_signals.assert_awaited_once_with(
        mode=SignalListMode.OPEN.value,
        live_since=None,
        limit=10,
        offset=10,
    )


async def test_empty_collection_still_returns_safe_first_page() -> None:
    repo = repository()
    repo.count_public_signals.return_value = 0
    repo.list_public_signals.return_value = ()

    page = await SignalQueryService(repo).get_page(SignalListMode.HISTORY.value)

    assert page.signals == ()
    assert page.page == page.total_pages == 1


@pytest.mark.parametrize(
    ("mode", "page", "page_size"),
    [
        ("draft", 1, 10),
        ("open", 0, 10),
        ("history", True, 10),
        ("live", 1, 20),
    ],
)
async def test_invalid_collection_or_pagination_is_rejected(
    mode: str,
    page: int,
    page_size: int,
) -> None:
    repo = repository()

    with pytest.raises(InvalidSignalError):
        await SignalQueryService(repo).get_page(mode, page=page, page_size=page_size)

    repo.count_public_signals.assert_not_awaited()


async def test_detail_clamps_target_page_and_queries_only_ten_targets() -> None:
    repo = repository()

    detail = await SignalQueryService(repo).get_detail(7, target_page=99)

    assert detail.signal.id == 7
    assert detail.target_page == 3
    assert detail.total_target_pages == 3
    repo.get_public_signal.assert_awaited_once_with(7)
    repo.list_targets_page.assert_awaited_once_with(7, limit=10, offset=20)


@pytest.mark.parametrize(("signal_id", "target_page"), [(0, 1), (True, 1), (7, 0)])
async def test_invalid_detail_input_never_queries_public_signal(
    signal_id: int,
    target_page: int,
) -> None:
    repo = repository()

    with pytest.raises(InvalidSignalError):
        await SignalQueryService(repo).get_detail(signal_id, target_page=target_page)

    repo.get_public_signal.assert_not_awaited()


async def test_live_collection_requires_timezone_aware_clock() -> None:
    repo = repository()
    service = SignalQueryService(repo, clock=lambda: datetime(2026, 9, 2))

    with pytest.raises(RuntimeError, match="aware datetime"):
        await service.get_page(SignalListMode.LIVE.value)
