"""Unit tests for PostgreSQL user upsert behavior."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.modules.users.entities import TelegramUserIdentity
from app.modules.users.errors import UserRepositoryError
from app.modules.users.models import User
from app.modules.users.repository import SQLAlchemyUserRepository


def test_repository_can_be_the_first_import_that_configures_orm_mappers() -> None:
    """Prevent relationship targets from depending on unrelated import order."""
    command = (
        "from app.modules.users.repository import SQLAlchemyUserRepository; "
        "from sqlalchemy.orm import configure_mappers; "
        "configure_mappers(); "
        "print(SQLAlchemyUserRepository.__name__)"
    )

    completed = subprocess.run(
        [sys.executable, "-B", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "SQLAlchemyUserRepository"


class FakeResult:
    def __init__(self, value: User | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> User | None:
        return self.value


class FakeSession:
    def __init__(
        self,
        results: list[FakeResult] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.results = list(results or [])
        self.error = error
        self.statements: list[object] = []

    async def execute(self, statement: object) -> FakeResult:
        self.statements.append(statement)
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


def identity(username: str = "sample_user") -> TelegramUserIdentity:
    return TelegramUserIdentity(
        telegram_user_id=123456789,
        username=username,
        first_name="Sample",
        last_name="User",
        language_code="fa",
        is_bot=False,
    )


def model(at: datetime, *, username: str = "sample_user") -> User:
    return User(
        id=1,
        telegram_user_id=123456789,
        username=username,
        first_name="Sample",
        last_name="User",
        language_code="fa",
        is_bot=False,
        status="ACTIVE",
        last_activity=at,
        created_at=at,
        updated_at=at,
    )


async def test_repository_returns_created_user_after_insert() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    session = FakeSession([FakeResult(model(now))])
    repository = SQLAlchemyUserRepository(session)  # type: ignore[arg-type]

    result = await repository.upsert(identity(), activity_at=now)

    assert result.created is True
    assert result.profile.telegram_user_id == 123456789
    assert len(session.statements) == 1


async def test_repository_updates_existing_user_without_duplicate_insert() -> None:
    now = datetime(2026, 9, 1, 1, tzinfo=UTC)
    session = FakeSession([FakeResult(None), FakeResult(model(now, username="changed"))])
    repository = SQLAlchemyUserRepository(session)  # type: ignore[arg-type]

    result = await repository.upsert(identity(username="changed"), activity_at=now)

    assert result.created is False
    assert result.profile.username == "changed"
    assert len(session.statements) == 2


async def test_repository_maps_sqlalchemy_errors() -> None:
    now = datetime(2026, 9, 1, tzinfo=UTC)
    session = FakeSession(error=SQLAlchemyError("database failed"))
    repository = SQLAlchemyUserRepository(session)  # type: ignore[arg-type]

    with pytest.raises(UserRepositoryError) as exc_info:
        await repository.upsert(identity(), activity_at=now)

    assert isinstance(exc_info.value.__cause__, SQLAlchemyError)
