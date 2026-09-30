"""Read-only public signal collections for Telegram and future adapters."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.modules.signals.entities import SignalDetail, SignalListMode, SignalPage
from app.modules.signals.errors import InvalidSignalError
from app.modules.signals.repository import SignalRepository

Clock = Callable[[], datetime]
PUBLIC_PAGE_SIZE = 10
LIVE_WINDOW = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(UTC)


class SignalQueryService:
    """Own public visibility, pagination, and recent-signal semantics."""

    def __init__(self, repository: SignalRepository, *, clock: Clock = utc_now) -> None:
        self.repository = repository
        self.clock = clock

    async def get_page(
        self,
        mode: str,
        *,
        page: int = 1,
        page_size: int = PUBLIC_PAGE_SIZE,
    ) -> SignalPage:
        normalized_mode = self._mode(mode)
        self._validate_page(page, page_size)
        live_since = self._now() - LIVE_WINDOW if normalized_mode == SignalListMode.LIVE else None
        total_items = await self.repository.count_public_signals(
            mode=normalized_mode.value,
            live_since=live_since,
        )
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        signals = await self.repository.list_public_signals(
            mode=normalized_mode.value,
            live_since=live_since,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return SignalPage(
            signals=signals,
            mode=normalized_mode.value,
            page=current_page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        )

    async def get_detail(
        self,
        signal_id: int,
        *,
        target_page: int = 1,
        target_page_size: int = PUBLIC_PAGE_SIZE,
    ) -> SignalDetail:
        self._validate_id(signal_id)
        self._validate_page(target_page, target_page_size)
        signal = await self.repository.get_public_signal(signal_id)
        total_targets = await self.repository.count_targets(signal_id)
        total_target_pages = max(
            1,
            (total_targets + target_page_size - 1) // target_page_size,
        )
        current_page = min(target_page, total_target_pages)
        targets = await self.repository.list_targets_page(
            signal_id,
            limit=target_page_size,
            offset=(current_page - 1) * target_page_size,
        )
        return SignalDetail(
            signal=signal,
            targets=targets,
            target_page=current_page,
            target_page_size=target_page_size,
            total_targets=total_targets,
            total_target_pages=total_target_pages,
        )

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("SignalQueryService clock must return an aware datetime")
        return value.astimezone(UTC)

    @staticmethod
    def _mode(mode: str) -> SignalListMode:
        try:
            return SignalListMode(mode)
        except (TypeError, ValueError):
            raise InvalidSignalError("Unsupported public signal collection") from None

    @staticmethod
    def _validate_id(signal_id: int) -> None:
        if not isinstance(signal_id, int) or isinstance(signal_id, bool) or signal_id <= 0:
            raise InvalidSignalError("Signal identifier must be a positive integer")

    @staticmethod
    def _validate_page(page: int, page_size: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidSignalError("Signal page must be a positive integer")
        if page_size != PUBLIC_PAGE_SIZE:
            raise InvalidSignalError("Public signal page size must be 10")
