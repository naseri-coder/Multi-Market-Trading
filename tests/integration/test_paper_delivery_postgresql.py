"""Real PostgreSQL delivery state test. Requires migrated 0013 DB."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.paper_runtime.models import SignalDelivery
from app.modules.paper_runtime.repository import SQLAlchemySignalDeliveryRepository
from app.modules.signals.models import Signal, SignalDirection, SignalPublicationScope, SignalStatus

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL required",
)


@pytest.mark.asyncio
async def test_delivery_state_machine(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        _env_file=None,
    )
    db = DatabaseManager.from_settings(settings)
    signal_id = None
    now = datetime(2026, 9, 2, tzinfo=UTC)
    try:
        async with db.session() as session:
            async with session.begin():
                signal = Signal(
                    symbol="P4TEST/USDT",
                    direction=SignalDirection.LONG.value,
                    entry_price=Decimal("100"),
                    stop_loss=Decimal("95"),
                    leverage=Decimal("1"),
                    status=SignalStatus.OPEN.value,
                    publication_scope=SignalPublicationScope.PRIVATE_TEST.value,
                    created_at=now,
                    updated_at=now,
                )
                session.add(signal)
                await session.flush()
                signal_id = signal.id

                repo = SQLAlchemySignalDeliveryRepository(session)
                pending = await repo.create_pending(
                    signal_id=signal_id,
                    channel_kind="TELEGRAM_PRIVATE_TEST",
                    destination_id="-100123",
                    now=now,
                )
                sending = await repo.mark_sending(pending.id, now=now)
                sent = await repo.mark_sent(sending.id, message_id="777", now=now)
                assert sent.status == "SENT"
                assert sent.external_message_id == "777"

        async with db.session() as session:
            count = await session.scalar(
                select(func.count(SignalDelivery.id)).where(
                    SignalDelivery.signal_id == signal_id
                )
            )
            assert count == 1
            await session.execute(delete(Signal).where(Signal.id == signal_id))
            await session.commit()
    finally:
        await db.dispose()
