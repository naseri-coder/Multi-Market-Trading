"""Notification-settings repository port and PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.notifications.entities import NotificationPreference
from app.modules.notifications.errors import NotificationSettingsRepositoryError
from app.modules.notifications.models import UserNotificationSetting


class NotificationSettingsRepository(Protocol):
    """Persistence contract consumed by NotificationSettingsService."""

    async def ensure_defaults(
        self,
        *,
        user_id: int,
        notification_types: tuple[str, ...],
        changed_at: datetime,
    ) -> None: ...

    async def list_for_user(
        self,
        user_id: int,
        *,
        notification_types: tuple[str, ...],
    ) -> tuple[NotificationPreference, ...]: ...

    async def set_enabled(
        self,
        *,
        user_id: int,
        notification_type: str,
        is_enabled: bool,
        changed_at: datetime,
    ) -> bool: ...


def _to_preference(model: UserNotificationSetting) -> NotificationPreference:
    return NotificationPreference(
        notification_type=model.notification_type,
        is_enabled=model.is_enabled,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SQLAlchemyNotificationSettingsRepository:
    """Async PostgreSQL preference persistence in a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_defaults(
        self,
        *,
        user_id: int,
        notification_types: tuple[str, ...],
        changed_at: datetime,
    ) -> None:
        statement = (
            insert(UserNotificationSetting)
            .values(
                [
                    {
                        "user_id": user_id,
                        "notification_type": notification_type,
                        "is_enabled": True,
                        "created_at": changed_at,
                        "updated_at": changed_at,
                    }
                    for notification_type in notification_types
                ]
            )
            .on_conflict_do_nothing(
                constraint="uq_user_notification_settings_user_type"
            )
        )
        try:
            await self.session.execute(statement)
        except SQLAlchemyError as exc:
            raise NotificationSettingsRepositoryError(
                "Unable to initialize notification settings"
            ) from exc

    async def list_for_user(
        self,
        user_id: int,
        *,
        notification_types: tuple[str, ...],
    ) -> tuple[NotificationPreference, ...]:
        ordering = {
            notification_type: index
            for index, notification_type in enumerate(notification_types)
        }
        statement = (
            select(UserNotificationSetting)
            .where(
                UserNotificationSetting.user_id == user_id,
                UserNotificationSetting.notification_type.in_(
                    notification_types
                ),
            )
            .order_by(
                case(
                    ordering,
                    value=UserNotificationSetting.notification_type,
                    else_=len(notification_types),
                )
            )
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise NotificationSettingsRepositoryError(
                "Unable to load notification settings"
            ) from exc
        return tuple(_to_preference(model) for model in models)

    async def set_enabled(
        self,
        *,
        user_id: int,
        notification_type: str,
        is_enabled: bool,
        changed_at: datetime,
    ) -> bool:
        insert_statement = insert(UserNotificationSetting).values(
            user_id=user_id,
            notification_type=notification_type,
            is_enabled=is_enabled,
            created_at=changed_at,
            updated_at=changed_at,
        )
        statement = (
            insert_statement.on_conflict_do_update(
                constraint="uq_user_notification_settings_user_type",
                set_={
                    "is_enabled": insert_statement.excluded.is_enabled,
                    "updated_at": insert_statement.excluded.updated_at,
                },
                where=UserNotificationSetting.is_enabled.is_distinct_from(
                    insert_statement.excluded.is_enabled
                ),
            ).returning(UserNotificationSetting.id)
        )
        try:
            result = await self.session.execute(statement)
            changed_id = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise NotificationSettingsRepositoryError(
                "Unable to update notification setting"
            ) from exc
        return changed_id is not None
