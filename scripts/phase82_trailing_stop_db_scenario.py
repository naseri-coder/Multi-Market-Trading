"""Disposable-PostgreSQL-only trailing-stop integration scenario."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.market_data.entities import Candle
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.signals.entities import CreateSignal
from app.modules.signals.errors import SignalStateError
from app.modules.signals.models import Signal, SignalEvent, SignalTarget
from app.modules.signals.repository import SQLAlchemySignalRepository
from app.modules.signals.service import SignalService
from sqlalchemy import select

BASE = datetime(2026, 1, 2, tzinfo=UTC)
_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db"}
_ALLOWED_DB_MARKERS = ("test", "ci", "tmp", "disposable")


def validate_disposable_database_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("explicit --database-url is required")
    normalized = value.strip().replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    database = parsed.path.lstrip("/").lower()
    if parsed.scheme != "postgresql" or parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError("database URL must target an allowlisted disposable PostgreSQL host")
    if not database or not any(marker in database for marker in _ALLOWED_DB_MARKERS):
        raise ValueError("database name must be explicitly test/ci/tmp/disposable")
    return value.strip()


def bar(i: int, high: str, low: str, close: str | None = None) -> Candle:
    opened = BASE + timedelta(minutes=i)
    h, l = Decimal(high), Decimal(low)
    c = Decimal(close) if close is not None else (h + l) / Decimal("2")
    return Candle(opened, opened + timedelta(minutes=1), c, h, l, c, Decimal("1"))


def structural_bull_candles() -> tuple[Candle, ...]:
    values = [
        ("101", "100"),
        ("103", "101"),
        ("105", "102"),
        ("104", "100"),
        ("103", "99"),
        ("104", "100"),
        ("106", "102"),
        ("108", "104"),
        ("107", "103"),
        ("106", "102"),
        ("107", "103"),
        ("109", "105"),
        ("111", "107"),
        ("110", "106"),
        ("109", "105"),
    ]
    return tuple(bar(i, high, low) for i, (high, low) in enumerate(values))


async def main(database_url: str) -> None:
    settings = Settings(
        database_url=validate_disposable_database_url(database_url),
        telegram_runtime_enabled=False,
        _env_file=None,
    )
    db = DatabaseManager.from_settings(settings)
    created_id = None
    try:
        async with db.session() as session:
            tx = await session.begin()
            try:
                repo = SQLAlchemySignalRepository(session)
                service = SignalService(repo, clock=lambda: BASE)
                created = await service.create_signal(
                    CreateSignal(
                        symbol="BTCUSDT",
                        direction="LONG",
                        entry_price="100",
                        stop_loss="90",
                        leverage="1",
                        description="PHASE82_ROLLBACK_ONLY",
                    )
                )
                created_id = created.id
                await service.add_target(created.id, target_price="110")
                signal = await session.get(Signal, created.id)
                target = await session.scalar(
                    select(SignalTarget).where(SignalTarget.signal_id == created.id)
                )
                lifecycle = LiveSignalLifecycleService(
                    database=db,
                    provider=object(),
                    bot=object(),
                    vip_channel_id=1,
                    cutover_at=BASE - timedelta(days=1),
                    candle_limit=50,
                )

                be_candle = bar(30, "106", "101", "105.5")
                changed = await lifecycle._tighten_active_stop(
                    service=service,
                    signal=signal,
                    targets=(target,),
                    candles=(be_candle,),
                    candle=be_candle,
                    entry_activated_at=BASE,
                )
                assert changed is True
                await session.flush()
                assert signal.stop_loss == Decimal("100.000000000000000000")

                structure = structural_bull_candles()
                changed = await lifecycle._tighten_active_stop(
                    service=service,
                    signal=signal,
                    targets=(target,),
                    candles=structure,
                    candle=structure[-1],
                    entry_activated_at=structure[0].close_time,
                )
                assert changed is True
                await session.flush()
                assert signal.stop_loss == Decimal("101.900000000000000000")

                unchanged = await lifecycle._tighten_active_stop(
                    service=service,
                    signal=signal,
                    targets=(target,),
                    candles=structure,
                    candle=structure[-1],
                    entry_activated_at=structure[0].close_time,
                )
                assert unchanged is False

                try:
                    await service.update_stop_loss(
                        created.id, stop_loss="101.00", reason="TEST_BACKWARD"
                    )
                except SignalStateError:
                    backward_blocked = True
                else:
                    backward_blocked = False
                assert backward_blocked

                events = tuple(
                    (
                        await session.scalars(
                            select(SignalEvent)
                            .where(
                                SignalEvent.signal_id == created.id,
                                SignalEvent.event_type == "STOP_LOSS_UPDATED",
                            )
                            .order_by(SignalEvent.id)
                        )
                    ).all()
                )
                reasons = [event.event_metadata.get("reason") for event in events]
                assert reasons == ["BREAKEVEN", "STRUCTURAL_TRAIL"]
            finally:
                await tx.rollback()

        async with db.session() as verify:
            remaining = await verify.scalar(select(Signal).where(Signal.id == created_id))
            assert remaining is None
        print("ROLLBACK_VERIFIED|synthetic_signal_remaining=0")
    finally:
        await db.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.database_url))
