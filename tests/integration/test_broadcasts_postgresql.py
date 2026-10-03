"""Transactional Phase 8 broadcast workflow against real PostgreSQL."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.broadcasts.entities import CreateBroadcast
from app.modules.broadcasts.errors import BroadcastStateError
from app.modules.broadcasts.models import (
    BroadcastContentType,
    BroadcastRecipient,
    BroadcastRecipientStatus,
    BroadcastStatus,
)
from app.modules.broadcasts.repository import SQLAlchemyBroadcastRepository
from app.modules.broadcasts.service import BroadcastService
from app.modules.users.models import User, UserStatus

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real broadcast integration test",
)


async def test_real_broadcast_snapshot_outcomes_report_and_cancel(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    base_id = 700_000_000_000_000_000 + uuid4().int % 100_000_000_000_000
    owner_id = base_id + 100
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                await session.execute(
                    insert(User),
                    [
                        {
                            "telegram_user_id": base_id + 1,
                            "username": "phase8_active_1",
                            "first_name": "Active 1",
                            "is_bot": False,
                            "status": UserStatus.ACTIVE.value,
                            "last_activity": now,
                        },
                        {
                            "telegram_user_id": base_id + 2,
                            "username": "phase8_active_2",
                            "first_name": "Active 2",
                            "is_bot": False,
                            "status": UserStatus.ACTIVE.value,
                            "last_activity": now,
                        },
                        {
                            "telegram_user_id": base_id + 3,
                            "username": "phase8_active_3",
                            "first_name": "Active 3",
                            "is_bot": False,
                            "status": UserStatus.ACTIVE.value,
                            "last_activity": now,
                        },
                        {
                            "telegram_user_id": base_id + 4,
                            "username": "phase8_blocked",
                            "first_name": "Blocked",
                            "is_bot": False,
                            "status": UserStatus.BLOCKED.value,
                            "last_activity": now,
                        },
                        {
                            "telegram_user_id": base_id + 5,
                            "username": "phase8_bot",
                            "first_name": "Bot",
                            "is_bot": True,
                            "status": UserStatus.ACTIVE.value,
                            "last_activity": now,
                        },
                    ],
                )
                repository = SQLAlchemyBroadcastRepository(session)
                service = BroadcastService(repository)
                draft = await service.create_draft(
                    CreateBroadcast(
                        created_by_telegram_user_id=owner_id,
                        content_type=BroadcastContentType.TEXT.value,
                        text=" Phase 8 integration message ",
                    )
                )
                claimed = await service.confirm(draft.id, owner_id, confirmed_at=now)

                assert claimed.status == BroadcastStatus.PROCESSING.value
                assert claimed.total_recipients == 3
                with pytest.raises(BroadcastStateError):
                    await service.confirm(draft.id, owner_id, confirmed_at=now)

                recipients = await repository.list_pending(draft.id, limit=10)
                assert len(recipients) == 3
                await repository.mark_recipient(
                    recipients[0].id,
                    status=BroadcastRecipientStatus.SENT.value,
                    attempts=1,
                    error_code=None,
                    sent_at=now,
                )
                await repository.mark_recipient(
                    recipients[1].id,
                    status=BroadcastRecipientStatus.FAILED.value,
                    attempts=2,
                    error_code="TELEGRAM_ERROR",
                    sent_at=None,
                )
                await repository.mark_recipient(
                    recipients[2].id,
                    status=BroadcastRecipientStatus.BLOCKED.value,
                    attempts=1,
                    error_code="BOT_BLOCKED",
                    sent_at=None,
                )
                completed = await repository.finalize(draft.id, completed_at=now)
                report = service.report(completed)

                assert report.status == BroadcastStatus.COMPLETED.value
                assert (
                    report.sent_count,
                    report.failed_count,
                    report.blocked_count,
                ) == (1, 1, 1)
                blocked_user_status = await session.scalar(
                    select(User.status).where(User.id == recipients[2].user_id)
                )
                assert blocked_user_status == UserStatus.BLOCKED.value

                second = await service.create_draft(
                    CreateBroadcast(
                        created_by_telegram_user_id=owner_id,
                        content_type=BroadcastContentType.TEXT.value,
                        text="Cancelled",
                    )
                )
                cancelled = await service.cancel(second.id, owner_id)
                assert cancelled.status == BroadcastStatus.CANCELLED.value
                recipient_count = len(
                    (
                        await session.scalars(
                            select(BroadcastRecipient).where(
                                BroadcastRecipient.broadcast_id == second.id
                            )
                        )
                    ).all()
                )
                assert recipient_count == 0

                forward = await service.create_draft(
                    CreateBroadcast(
                        created_by_telegram_user_id=owner_id,
                        content_type=BroadcastContentType.FORWARD.value,
                        source_chat_id=owner_id,
                        source_message_id=55,
                    )
                )
                assert forward.source_chat_id == owner_id
                assert forward.source_message_id == 55
                forward_claimed = await service.confirm(
                    forward.id,
                    owner_id,
                    confirmed_at=now,
                )
                assert forward_claimed.status == BroadcastStatus.PROCESSING.value
                assert forward_claimed.total_recipients == 2
            finally:
                await transaction.rollback()
    finally:
        await database.dispose()
