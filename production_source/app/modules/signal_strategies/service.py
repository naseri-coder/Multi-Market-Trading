"""Business rules for independent signal-strategy routing."""

from __future__ import annotations

from app.modules.signal_strategies.entities import (
    SUPPORTED_STRATEGY_CODES,
    SignalStrategyRecord,
)
from app.modules.signal_strategies.errors import (
    InvalidSignalStrategyError,
    SignalStrategyChannelRequiredError,
    SignalStrategyEngineNotReadyError,
)
from app.modules.signal_strategies.repository import SignalStrategyRepository


class SignalStrategyService:
    def __init__(self, repository: SignalStrategyRepository) -> None:
        self.repository = repository

    @staticmethod
    def _code(value: str) -> str:
        code = value.strip().upper()
        if code not in SUPPORTED_STRATEGY_CODES:
            raise InvalidSignalStrategyError("Unsupported signal strategy")
        return code

    async def list_all(self) -> tuple[SignalStrategyRecord, ...]:
        return await self.repository.list_all()

    async def get(self, strategy_code: str) -> SignalStrategyRecord:
        return await self.repository.get(self._code(strategy_code))

    async def toggle(
        self, strategy_code: str, *, updated_by_telegram_user_id: int
    ) -> SignalStrategyRecord:
        code = self._code(strategy_code)
        current = await self.repository.get(code)
        if current.enabled:
            return await self.repository.set_enabled(
                code, False, updated_by_telegram_user_id=updated_by_telegram_user_id
            )
        if not current.engine_ready:
            raise SignalStrategyEngineNotReadyError(
                f"{current.display_name} engine is not connected"
            )
        if current.private_channel_id is None:
            raise SignalStrategyChannelRequiredError(
                f"{current.display_name} private channel is not configured"
            )
        return await self.repository.set_enabled(
            code, True, updated_by_telegram_user_id=updated_by_telegram_user_id
        )

    async def set_channel(
        self,
        strategy_code: str,
        *,
        chat_id: int,
        title: str,
        username: str | None,
        updated_by_telegram_user_id: int,
    ) -> SignalStrategyRecord:
        code = self._code(strategy_code)
        if chat_id >= 0:
            raise InvalidSignalStrategyError("Private delivery chat id must be negative")
        normalized_title = title.strip()
        if not normalized_title:
            raise InvalidSignalStrategyError("Channel title is required")
        return await self.repository.set_channel(
            code,
            chat_id=chat_id,
            title=normalized_title,
            username=(username.strip().removeprefix("@") if username else None),
            updated_by_telegram_user_id=updated_by_telegram_user_id,
        )

    async def clear_channel(
        self, strategy_code: str, *, updated_by_telegram_user_id: int
    ) -> SignalStrategyRecord:
        return await self.repository.clear_channel(
            self._code(strategy_code),
            updated_by_telegram_user_id=updated_by_telegram_user_id,
        )

    async def effective_channel_id(self, strategy_code: str) -> int | None:
        item = await self.get(strategy_code)
        return item.private_channel_id if item.effective_enabled else None

    async def set_engine_ready(
        self, strategy_code: str, *, ready: bool
    ) -> SignalStrategyRecord:
        """Synchronize machine-owned engine readiness without changing admin state."""
        return await self.repository.set_engine_ready(
            self._code(strategy_code),
            bool(ready),
        )
