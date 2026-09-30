"""User repository port and SQLAlchemy implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import case, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# Register all string-based ORM relationship targets before statements compile.
from app.db import models as _models  # noqa: F401
from app.modules.users.entities import TelegramUserIdentity, UserProfile, UserRegistrationResult
from app.modules.users.errors import UserRepositoryError
from app.modules.users.models import User, UserStatus


class UserRepository(Protocol):
    """Persistence contract consumed by UserService."""

    async def upsert(
        self,
        identity: TelegramUserIdentity,
        *,
        activity_at: datetime,
    ) -> UserRegistrationResult:
        """Atomically create or update one Telegram user."""
        ...


def _to_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        telegram_user_id=user.telegram_user_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_bot=user.is_bot,
        status=user.status,
        last_activity=user.last_activity,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


class SQLAlchemyUserRepository:
    """PostgreSQL user repository bound to a caller-owned session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        identity: TelegramUserIdentity,
        *,
        activity_at: datetime,
    ) -> UserRegistrationResult:
        """Use the unique Telegram id to prevent duplicate users under concurrency."""
        values = {
            "telegram_user_id": identity.telegram_user_id,
            "username": identity.username,
            "first_name": identity.first_name,
            "last_name": identity.last_name,
            "language_code": identity.language_code,
            "is_bot": identity.is_bot,
            "last_activity": activity_at,
        }

        try:
            create_statement = (
                insert(User)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_users_telegram_user_id")
                .returning(User)
            )
            created_user = (await self.session.execute(create_statement)).scalar_one_or_none()
            if created_user is not None:
                return UserRegistrationResult(profile=_to_profile(created_user), created=True)

            update_statement = (
                update(User)
                .where(User.telegram_user_id == identity.telegram_user_id)
                .values(
                    **values,
                    updated_at=activity_at,
                    status=case(
                        (
                            User.status == UserStatus.BLOCKED.value,
                            UserStatus.ACTIVE.value,
                        ),
                        else_=User.status,
                    ),
                )
                .returning(User)
            )
            existing_user = (await self.session.execute(update_statement)).scalar_one_or_none()
            if existing_user is None:
                raise UserRepositoryError("User disappeared during conflict resolution")

            return UserRegistrationResult(profile=_to_profile(existing_user), created=False)
        except UserRepositoryError:
            raise
        except SQLAlchemyError as exc:
            raise UserRepositoryError("Unable to persist Telegram user") from exc
