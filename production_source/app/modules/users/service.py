"""User application service and business validation."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.modules.users.entities import TelegramUserIdentity, UserRegistrationResult
from app.modules.users.errors import InvalidUserIdentityError
from app.modules.users.repository import UserRepository

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    """Return an aware UTC time for persistence."""
    return datetime.now(UTC)


class UserService:
    """Coordinate user registration and profile refresh rules."""

    def __init__(self, repository: UserRepository, *, clock: Clock = utc_now) -> None:
        self.repository = repository
        self.clock = clock

    async def register_or_update(
        self,
        identity: TelegramUserIdentity,
    ) -> UserRegistrationResult:
        """Validate identity data and perform an idempotent profile synchronization."""
        self._validate_identity(identity)
        activity_at = self.clock()
        if activity_at.tzinfo is None or activity_at.utcoffset() is None:
            raise RuntimeError("UserService clock must return an aware datetime")

        return await self.repository.upsert(identity, activity_at=activity_at.astimezone(UTC))

    @staticmethod
    def _validate_identity(identity: TelegramUserIdentity) -> None:
        if identity.telegram_user_id <= 0:
            raise InvalidUserIdentityError("Telegram user id must be positive")
        if not identity.first_name.strip():
            raise InvalidUserIdentityError("First name must not be empty")
        if len(identity.first_name) > 255 or (
            identity.last_name is not None and len(identity.last_name) > 255
        ):
            raise InvalidUserIdentityError("Telegram name exceeds storage limits")
        if identity.username is not None and len(identity.username) > 64:
            raise InvalidUserIdentityError("Telegram username exceeds storage limits")
        if identity.language_code is not None and len(identity.language_code) > 16:
            raise InvalidUserIdentityError("Telegram language code exceeds storage limits")
