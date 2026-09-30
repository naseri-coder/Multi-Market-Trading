"""Read-only administrator signal collections and details."""

from __future__ import annotations

from app.modules.signals.entities import (
    AdminSignalDetail,
    AdminSignalListMode,
    AdminSignalPage,
)
from app.modules.signals.errors import InvalidSignalError
from app.modules.signals.models import SignalStatus
from app.modules.signals.repository import SignalRepository

ADMIN_SIGNAL_PAGE_SIZE = 10
ADMIN_TARGET_PAGE_SIZE = 10

_MODE_STATUSES = {
    AdminSignalListMode.ACTIVE: (SignalStatus.OPEN.value,),
    AdminSignalListMode.HISTORY: (
        SignalStatus.CLOSED.value,
        SignalStatus.CANCELLED.value,
    ),
    AdminSignalListMode.DRAFTS: (SignalStatus.DRAFT.value,),
}


class AdminSignalQueryService:
    """Own bounded administrator visibility and pagination rules."""

    def __init__(self, repository: SignalRepository) -> None:
        self.repository = repository

    async def get_page(
        self,
        mode: str,
        *,
        page: int = 1,
        page_size: int = ADMIN_SIGNAL_PAGE_SIZE,
    ) -> AdminSignalPage:
        normalized_mode = self._mode(mode)
        self._validate_page(page, page_size, ADMIN_SIGNAL_PAGE_SIZE)
        statuses = _MODE_STATUSES[normalized_mode]
        total_items = await self.repository.count_admin_signals(
            statuses=statuses
        )
        if total_items < 0:
            raise RuntimeError("Signal repository returned a negative count")
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        signals = await self.repository.list_admin_signals(
            statuses=statuses,
            limit=page_size,
            offset=(current_page - 1) * page_size,
        )
        return AdminSignalPage(
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
        target_page_size: int = ADMIN_TARGET_PAGE_SIZE,
    ) -> AdminSignalDetail:
        self._validate_id(signal_id)
        self._validate_page(
            target_page,
            target_page_size,
            ADMIN_TARGET_PAGE_SIZE,
        )
        signal = await self.repository.get_signal(signal_id)
        total_targets = await self.repository.count_targets(signal_id)
        if total_targets < 0:
            raise RuntimeError("Signal repository returned a negative target count")
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
        return AdminSignalDetail(
            signal=signal,
            targets=targets,
            target_page=current_page,
            target_page_size=target_page_size,
            total_targets=total_targets,
            total_target_pages=total_target_pages,
        )

    @staticmethod
    def _mode(mode: str) -> AdminSignalListMode:
        try:
            return AdminSignalListMode(mode)
        except (TypeError, ValueError):
            raise InvalidSignalError(
                "Unsupported administrator signal collection"
            ) from None

    @staticmethod
    def _validate_id(signal_id: int) -> None:
        if (
            not isinstance(signal_id, int)
            or isinstance(signal_id, bool)
            or signal_id <= 0
        ):
            raise InvalidSignalError(
                "Signal identifier must be a positive integer"
            )

    @staticmethod
    def _validate_page(page: int, page_size: int, expected_size: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise InvalidSignalError("Signal page must be a positive integer")
        if page_size != expected_size:
            raise InvalidSignalError("Administrator page size is fixed")
