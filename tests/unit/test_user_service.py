"""Unit tests for user application service rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.users.entities import TelegramUserIdentity, UserProfile, UserRegistrationResult
from app.modules.users.errors import InvalidUserIdentityError
from app.modules.users.service import UserService


def identity(**overrides: object) -> TelegramUserIdentity:
    values = {
        "telegram_user_id": 123456789,
        "username": "sample_user",
        "first_name": "Sample",
        "last_name": "User",
        "language_code": "fa",
        "is_bot": False,
    }
    values.update(overrides)
    return TelegramUserIdentity(**values)


def profile(at: datetime) -> UserProfile:
    return UserProfile(
        id=1,
        telegram_user_id=123456789,
        username="sample_user",
        first_name="Sample",
        last_name="User",
        language_code="fa",
        is_bot=False,
        status="ACTIVE",
        last_activity=at,
        created_at=at,
        updated_at=at,
    )


class FakeUserRepository:
    def __init__(self, result: UserRegistrationResult) -> None:
        self.result = result
        self.calls: list[tuple[TelegramUserIdentity, datetime]] = []

    async def upsert(
        self,
        user_identity: TelegramUserIdentity,
        *,
        activity_at: datetime,
    ) -> UserRegistrationResult:
        self.calls.append((user_identity, activity_at))
        return self.result


async def test_service_registers_new_user_with_utc_activity() -> None:
    now = datetime(2026, 9, 1, 8, 30, tzinfo=UTC)
    expected = UserRegistrationResult(profile=profile(now), created=True)
    repository = FakeUserRepository(expected)
    service = UserService(repository, clock=lambda: now)
    user_identity = identity()

    result = await service.register_or_update(user_identity)

    assert result is expected
    assert repository.calls == [(user_identity, now)]


async def test_service_returns_existing_user_result() -> None:
    now = datetime(2026, 9, 1, 8, 31, tzinfo=UTC)
    expected = UserRegistrationResult(profile=profile(now), created=False)
    service = UserService(FakeUserRepository(expected), clock=lambda: now)

    result = await service.register_or_update(identity(username="changed"))

    assert result.created is False


@pytest.mark.parametrize(
    "invalid_identity",
    [
        identity(telegram_user_id=0),
        identity(first_name=" "),
        identity(username="x" * 65),
        identity(language_code="x" * 17),
    ],
)
async def test_service_rejects_invalid_identity(invalid_identity: TelegramUserIdentity) -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    repository = FakeUserRepository(UserRegistrationResult(profile=profile(now), created=True))
    service = UserService(repository, clock=lambda: now)

    with pytest.raises(InvalidUserIdentityError):
        await service.register_or_update(invalid_identity)

    assert repository.calls == []


async def test_service_rejects_naive_clock() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    repository = FakeUserRepository(UserRegistrationResult(profile=profile(now), created=True))
    service = UserService(repository, clock=lambda: datetime(2026, 9, 1))

    with pytest.raises(RuntimeError, match="aware datetime"):
        await service.register_or_update(identity())
