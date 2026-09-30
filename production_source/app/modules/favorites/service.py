"""User favorites business rules independent from Telegram and SQLAlchemy."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.favorites.entities import FavoriteMutation, FavoritePage
from app.modules.favorites.errors import (
    FavoriteSignalNotFoundError,
    InvalidFavoriteError,
)
from app.modules.favorites.repository import FavoriteRepository

FavoriteClock = Callable[[], datetime]
FAVORITES_PAGE_SIZE = 10


def utc_now() -> datetime:
    return datetime.now(UTC)


class FavoriteService:
    """Own idempotent favorite mutation, visibility, and pagination rules."""

    def __init__(
        self,
        repository: FavoriteRepository,
        *,
        clock: FavoriteClock = utc_now,
    ) -> None:
        self.repository = repository
        self.clock = clock

    async def add(self, user_id: int, signal_id: int) -> FavoriteMutation:
        self._validate_id(user_id, "User")
        self._validate_id(signal_id, "Signal")
        if not await self.repository.public_signal_exists(signal_id):
            raise FavoriteSignalNotFoundError(
                "Signal does not exist or is not public"
            )
        created_at = self._now()
        changed = await self.repository.add(
            user_id=user_id,
            signal_id=signal_id,
            created_at=created_at,
        )
        return FavoriteMutation(
            signal_id=signal_id,
            is_favorite=True,
            changed=changed,
        )

    async def remove(self, user_id: int, signal_id: int) -> FavoriteMutation:
        self._validate_id(user_id, "User")
        self._validate_id(signal_id, "Signal")
        changed = await self.repository.remove(
            user_id=user_id,
            signal_id=signal_id,
        )
        return FavoriteMutation(
            signal_id=signal_id,
            is_favorite=False,
            changed=changed,
        )

    async def is_favorite(self, user_id: int, signal_id: int) -> bool:
        self._validate_id(user_id, "User")
        self._validate_id(signal_id, "Signal")
        return await self.repository.is_favorite(
            user_id=user_id,
            signal_id=signal_id,
        )

    async def get_page(
        self,
        user_id: int,
        *,
        page: int = 1,
        page_size: int = FAVORITES_PAGE_SIZE,
    ) -> FavoritePage:
        self._validate_id(user_id, "User")
        self._validate_page(page, page_size)
        total_items = await self.repository.count_for_user(user_id)
        if total_items < 0:
            raise RuntimeError("Favorite repository returned a negative count")
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        signals = await self.repository.list_for_user(
            user_id,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return FavoritePage(
            signals=signals,
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("FavoriteService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_id(value: int, label: str) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise InvalidFavoriteError(f"{label} identifier must be a positive integer")

    @staticmethod
    def _validate_page(page: int, page_size: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidFavoriteError("Favorite page must be a positive integer")
        if page_size != FAVORITES_PAGE_SIZE:
            raise InvalidFavoriteError("Favorite page size must be 10")
