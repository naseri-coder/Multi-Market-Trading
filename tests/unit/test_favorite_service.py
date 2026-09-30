"""Favorite service business-rule tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.favorites.errors import (
    FavoriteSignalNotFoundError,
    InvalidFavoriteError,
)
from app.modules.favorites.service import FavoriteService
from app.modules.signals.entities import SignalRecord

NOW = datetime(2026, 9, 1, 20, tzinfo=UTC)


def signal(signal_id: int) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol=f"P15{signal_id}/USDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        leverage=Decimal("5"),
        status="OPEN",
        description=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
    )


class FakeFavoriteRepository:
    def __init__(self, *, public_ids: set[int] | None = None) -> None:
        self.public_ids = {7} if public_ids is None else public_ids
        self.favorites: set[tuple[int, int]] = set()
        self.signals = {item: signal(item) for item in self.public_ids}

    async def public_signal_exists(self, signal_id: int) -> bool:
        return signal_id in self.public_ids

    async def add(self, *, user_id: int, signal_id: int, created_at: datetime) -> bool:
        assert created_at == NOW
        key = (user_id, signal_id)
        changed = key not in self.favorites
        self.favorites.add(key)
        return changed

    async def remove(self, *, user_id: int, signal_id: int) -> bool:
        key = (user_id, signal_id)
        changed = key in self.favorites
        self.favorites.discard(key)
        return changed

    async def is_favorite(self, *, user_id: int, signal_id: int) -> bool:
        return (user_id, signal_id) in self.favorites

    async def count_for_user(self, user_id: int) -> int:
        return len([key for key in self.favorites if key[0] == user_id])

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SignalRecord, ...]:
        ids = sorted(
            (signal_id for owner, signal_id in self.favorites if owner == user_id),
            reverse=True,
        )
        return tuple(self.signals[item] for item in ids[offset : offset + limit])


async def test_add_and_remove_are_idempotent() -> None:
    repository = FakeFavoriteRepository()
    service = FavoriteService(repository, clock=lambda: NOW)

    first_add = await service.add(3, 7)
    duplicate_add = await service.add(3, 7)
    first_remove = await service.remove(3, 7)
    duplicate_remove = await service.remove(3, 7)

    assert (first_add.is_favorite, first_add.changed) == (True, True)
    assert (duplicate_add.is_favorite, duplicate_add.changed) == (True, False)
    assert (first_remove.is_favorite, first_remove.changed) == (False, True)
    assert (duplicate_remove.is_favorite, duplicate_remove.changed) == (False, False)


async def test_draft_or_missing_signal_cannot_be_favorited() -> None:
    service = FavoriteService(FakeFavoriteRepository(public_ids=set()))

    with pytest.raises(FavoriteSignalNotFoundError):
        await service.add(3, 7)


async def test_favorites_are_isolated_and_paginated_ten_per_page() -> None:
    repository = FakeFavoriteRepository(public_ids=set(range(1, 13)))
    service = FavoriteService(repository, clock=lambda: NOW)
    for signal_id in range(1, 13):
        await service.add(3, signal_id)
    await service.add(4, 1)

    first = await service.get_page(3, page=1)
    second = await service.get_page(3, page=2)
    clamped = await service.get_page(3, page=99)
    other_user = await service.get_page(4)

    assert len(first.signals) == 10
    assert len(second.signals) == 2
    assert clamped == second
    assert first.total_items == 12
    assert other_user.total_items == 1


@pytest.mark.parametrize("value", (0, -1, True, "7"))
async def test_identifiers_must_be_positive_integers(value: object) -> None:
    service = FavoriteService(FakeFavoriteRepository())

    with pytest.raises(InvalidFavoriteError):
        await service.is_favorite(value, 7)  # type: ignore[arg-type]


async def test_page_size_is_fixed_and_clock_must_be_timezone_aware() -> None:
    repository = FakeFavoriteRepository()
    service = FavoriteService(repository)
    with pytest.raises(InvalidFavoriteError):
        await service.get_page(3, page=1, page_size=20)

    naive_service = FavoriteService(
        repository,
        clock=lambda: datetime(2026, 9, 1, 20),
    )
    with pytest.raises(RuntimeError, match="aware datetime"):
        await naive_service.add(3, 7)


async def test_negative_repository_count_is_rejected() -> None:
    repository = FakeFavoriteRepository()

    async def negative_count(user_id: int) -> int:
        return -1

    repository.count_for_user = negative_count  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="negative count"):
        await FavoriteService(repository).get_page(3)
