"""PostgreSQL repository for strategy configuration."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.signal_strategies.entities import SignalStrategyRecord
from app.modules.signal_strategies.errors import SignalStrategyNotFoundError
from app.modules.signal_strategies.models import SignalStrategyConfig


class SignalStrategyRepository(Protocol):
    async def list_all(self) -> tuple[SignalStrategyRecord, ...]: ...
    async def get(self, strategy_code: str) -> SignalStrategyRecord: ...
    async def set_enabled(
        self, strategy_code: str, enabled: bool, *, updated_by_telegram_user_id: int
    ) -> SignalStrategyRecord: ...
    async def set_channel(
        self,
        strategy_code: str,
        *,
        chat_id: int,
        title: str,
        username: str | None,
        updated_by_telegram_user_id: int,
    ) -> SignalStrategyRecord: ...
    async def clear_channel(
        self, strategy_code: str, *, updated_by_telegram_user_id: int
    ) -> SignalStrategyRecord: ...


def _record(model: SignalStrategyConfig) -> SignalStrategyRecord:
    return SignalStrategyRecord(
        id=model.id,
        strategy_code=model.strategy_code,
        display_name=model.display_name,
        enabled=model.enabled,
        engine_ready=model.engine_ready,
        private_channel_id=model.private_channel_id,
        private_channel_title=model.private_channel_title,
        private_channel_username=model.private_channel_username,
        updated_by_telegram_user_id=model.updated_by_telegram_user_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SQLAlchemySignalStrategyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> tuple[SignalStrategyRecord, ...]:
        try:
            rows = (
                await self.session.scalars(
                    select(SignalStrategyConfig).order_by(SignalStrategyConfig.id)
                )
            ).all()
        except SQLAlchemyError as exc:
            raise RuntimeError("Unable to list signal strategies") from exc
        return tuple(_record(row) for row in rows)

    async def get(self, strategy_code: str) -> SignalStrategyRecord:
        try:
            row = await self.session.scalar(
                select(SignalStrategyConfig).where(
                    SignalStrategyConfig.strategy_code == strategy_code
                )
            )
        except SQLAlchemyError as exc:
            raise RuntimeError("Unable to load signal strategy") from exc
        if row is None:
            raise SignalStrategyNotFoundError(strategy_code)
        return _record(row)

    async def _update(self, strategy_code: str, **values: object) -> SignalStrategyRecord:
        try:
            row = (
                await self.session.execute(
                    update(SignalStrategyConfig)
                    .where(SignalStrategyConfig.strategy_code == strategy_code)
                    .values(**values)
                    .returning(SignalStrategyConfig)
                )
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise RuntimeError("Unable to update signal strategy") from exc
        if row is None:
            raise SignalStrategyNotFoundError(strategy_code)
        return _record(row)

    async def set_enabled(
        self, strategy_code: str, enabled: bool, *, updated_by_telegram_user_id: int
    ) -> SignalStrategyRecord:
        return await self._update(
            strategy_code,
            enabled=enabled,
            updated_by_telegram_user_id=updated_by_telegram_user_id,
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
        return await self._update(
            strategy_code,
            private_channel_id=chat_id,
            private_channel_title=title,
            private_channel_username=username,
            updated_by_telegram_user_id=updated_by_telegram_user_id,
        )

    async def clear_channel(
        self, strategy_code: str, *, updated_by_telegram_user_id: int
    ) -> SignalStrategyRecord:
        return await self._update(
            strategy_code,
            enabled=False,
            private_channel_id=None,
            private_channel_title=None,
            private_channel_username=None,
            updated_by_telegram_user_id=updated_by_telegram_user_id,
        )
