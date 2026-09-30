"""Unit tests for the SQLAlchemy channel repository."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.modules.channels.entities import CreateChannel, UpdateChannel
from app.modules.channels.errors import (
    ChannelNotFoundError,
    ChannelRepositoryError,
    DuplicateChannelError,
)
from app.modules.channels.models import Channel
from app.modules.channels.repository import SQLAlchemyChannelRepository


def test_repository_can_be_first_import_to_configure_mappers() -> None:
    command = (
        "from app.modules.channels.repository import SQLAlchemyChannelRepository; "
        "from sqlalchemy.orm import configure_mappers; "
        "configure_mappers(); print(SQLAlchemyChannelRepository.__name__)"
    )
    completed = subprocess.run(
        [sys.executable, "-B", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "SQLAlchemyChannelRepository"


def model(channel_id: int = 1, *, is_active: bool = True) -> Channel:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return Channel(
        id=channel_id,
        telegram_chat_id=-1_001_234_567_890 - channel_id,
        username=f"channel{channel_id}",
        title=f"Channel {channel_id}",
        invite_link=None,
        is_active=is_active,
        sort_order=channel_id,
        created_at=timestamp,
        updated_at=timestamp,
    )


class FakeScalarCollection:
    def __init__(self, values: list[Channel]) -> None:
        self.values = values

    def all(self) -> list[Channel]:
        return self.values


class FakeResult:
    def __init__(self, value: object = None, *, values: list[Channel] | None = None) -> None:
        self.value = value
        self.values = values or []

    def scalar_one(self) -> object:
        return self.value

    def scalar_one_or_none(self) -> object:
        return self.value

    def scalars(self) -> FakeScalarCollection:
        return FakeScalarCollection(self.values)


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


async def test_repository_crud_and_toggle_return_records() -> None:
    session = FakeSession(
        [
            FakeResult(model(1)),
            FakeResult(model(1)),
            FakeResult(model(1, is_active=False)),
            FakeResult(model(1)),
            FakeResult(1),
        ]
    )
    repository = SQLAlchemyChannelRepository(session)  # type: ignore[arg-type]

    created = await repository.create(
        CreateChannel(-1_001_234_567_891, "channel1", "Channel 1", None, 1)
    )
    updated = await repository.update(
        1,
        UpdateChannel("Channel 1", "channel1", None, 1),
    )
    toggled = await repository.toggle(1)
    loaded = await repository.get_by_id(1)
    await repository.delete(1)

    assert created.id == updated.id == toggled.id == loaded.id == 1
    assert toggled.is_active is False
    assert len(session.statements) == 5


async def test_repository_lists_channels_in_statement_defined_order() -> None:
    session = FakeSession(
        [
            FakeResult(values=[model(1), model(2)]),
            FakeResult(values=[model(1)]),
        ]
    )
    repository = SQLAlchemyChannelRepository(session)  # type: ignore[arg-type]

    all_channels = await repository.list_all()
    active_channels = await repository.list_active()

    assert [channel.id for channel in all_channels] == [1, 2]
    assert [channel.id for channel in active_channels] == [1]
    active_sql = str(session.statements[1])
    assert "channels.is_active IS true" in active_sql
    assert "ORDER BY channels.sort_order, channels.id" in active_sql


async def test_repository_loads_channel_by_telegram_chat_id() -> None:
    stored = model(3)
    session = FakeSession([FakeResult(stored)])
    repository = SQLAlchemyChannelRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_telegram_chat_id(stored.telegram_chat_id)

    assert result.id == 3
    statement = str(session.statements[0])
    assert "channels.telegram_chat_id" in statement


@pytest.mark.parametrize("operation", ["update", "toggle", "get_by_id", "delete"])
async def test_repository_maps_missing_rows(operation: str) -> None:
    session = FakeSession([FakeResult(None)])
    repository = SQLAlchemyChannelRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ChannelNotFoundError):
        if operation == "update":
            await repository.update(5, UpdateChannel("Title", "channelname", None, 0))
        elif operation == "toggle":
            await repository.toggle(5)
        elif operation == "get_by_id":
            await repository.get_by_id(5)
        else:
            await repository.delete(5)


async def test_repository_maps_unique_constraint_failure() -> None:
    error = IntegrityError("insert", {}, Exception("duplicate"))
    repository = SQLAlchemyChannelRepository(FakeSession(error=error))  # type: ignore[arg-type]

    with pytest.raises(DuplicateChannelError) as exc_info:
        await repository.create(
            CreateChannel(-1_001_234_567_890, "channelname", "Channel", None, 0)
        )

    assert exc_info.value.__cause__ is error


async def test_repository_maps_database_failure() -> None:
    error = SQLAlchemyError("database failed")
    repository = SQLAlchemyChannelRepository(FakeSession(error=error))  # type: ignore[arg-type]

    with pytest.raises(ChannelRepositoryError) as exc_info:
        await repository.list_active()

    assert exc_info.value.__cause__ is error
