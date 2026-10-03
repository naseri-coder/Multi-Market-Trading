"""Disposable PostgreSQL contract tests for isolated Chapter-6 ii identity."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import create_async_engine

import app
from app.db.session import DatabaseManager
from app.modules.paper_runtime.models import SignalDelivery
from app.modules.paper_runtime.repository import SQLAlchemySignalDeliveryRepository
from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport
from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signal_automation.service import BrooksSignalIntegrationService
from app.modules.signals.models import Signal

FIRST = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
SECOND = FIRST + timedelta(minutes=15)


def command(
    origin: str, snapshot: str, *, view: str = "PENDING",
    setup: str = "II_PENDING_PAIR", mode: str = "PAPER",
) -> BrooksSignalImport:
    first = {
        "pair-a": FIRST,
        "pair-b": FIRST + timedelta(minutes=30),
        "pair-race": FIRST + timedelta(minutes=60),
    }[origin]
    evidence = BrooksRuleEvidence("BB-TRD-06-II-III", "PASS", (109,))
    return BrooksSignalImport(
        source_signal_id=f"synthetic-{origin}-{snapshot}-{mode}",
        symbol="CH6SYNTHETIC",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"),),
        leverage=Decimal("1"),
        exchange="synthetic",
        market_type="spot",
        timeframe="15m",
        setup_type=setup,
        market_snapshot_id=f"snapshot-{snapshot}",
        market_snapshot_hash=f"hash-{snapshot}",
        engine_version="synthetic",
        rule_set_version="synthetic",
        configuration_version="synthetic",
        reasoning=("synthetic",),
        rule_ids=(evidence.rule_id,),
        failed_rules=(),
        rule_evidence=(evidence,),
        generation_mode=mode,
        publication_scope="PRIVATE_TEST" if mode == "PAPER" else "VIP",
        counts_toward_performance=mode == "LIVE",
        opportunity_variant="CH6_II_PAIR_STOP_V1",
        ii_first_open_time=first,
        ii_second_open_time=first + timedelta(minutes=15),
        opportunity_view=view,
    )


@pytest.fixture
def isolated_database_url() -> str:
    url = os.environ["CH6_DISPOSABLE_DATABASE_URL"]
    source = Path(os.environ["CH6_ISOLATED_SOURCE"]).resolve()
    parsed = urlsplit(url)
    socket_values = parse_qs(parsed.query).get("host", [])
    assert parsed.scheme == "postgresql+asyncpg"
    assert parsed.hostname == "localhost"
    assert parsed.path == "/ch6synthetic"
    assert len(socket_values) == 1 and socket_values[0].startswith("/tmp/ch6-")
    assert Path(app.__file__).resolve().is_relative_to(source)
    return url


@pytest_asyncio.fixture
async def database(isolated_database_url: str):
    manager = DatabaseManager(
        create_async_engine(isolated_database_url, pool_size=2, max_overflow=2)
    )
    try:
        yield manager
    finally:
        async with manager.session() as session, session.begin():
            await session.execute(
                delete(Signal).where(Signal.symbol == "CH6SYNTHETIC")
            )
        await manager.dispose()


async def import_command(database, item: BrooksSignalImport):
    async with database.session() as session:
        return await BrooksSignalIntegrationService(session).import_signal(item)


@pytest.mark.asyncio
async def test_repeated_confirmed_terminal_and_delivery_identity(database) -> None:
    pending = await import_command(database, command("pair-a", "a"))
    repeated = await import_command(database, command("pair-a", "a"))
    confirmed = await import_command(
        database,
        command("pair-a", "b", view="CONFIRMED", setup="II_CONFIRMED_BREAKOUT"),
    )
    assert pending.created is True
    assert repeated.created is False
    assert confirmed.created is False
    assert pending.signal_id == repeated.signal_id == confirmed.signal_id

    async with database.session() as session, session.begin():
        deliveries = SQLAlchemySignalDeliveryRepository(session)
        await deliveries.create_pending(
            signal_id=pending.signal_id,
            channel_kind="TELEGRAM_PRIVATE_TEST",
            destination_id="synthetic-only",
            now=datetime.now(UTC),
        )
        metadata = await session.get(SignalAutomationMetadata, pending.signal_id)
        assert metadata.analysis_metadata["ii_pair_opportunity"]["state"] == "CONFIRMED"
        await session.execute(
            update(Signal).where(Signal.id == pending.signal_id).values(
                status="CANCELLED", closed_at=datetime.now(UTC)
            )
        )
    after_terminal = await import_command(
        database, command("pair-a", "c", view="CONFIRMED")
    )
    assert after_terminal.created is False
    assert after_terminal.signal_id == pending.signal_id
    async with database.session() as session:
        count = await session.scalar(
            select(func.count(SignalAutomationMetadata.signal_id)).where(
                SignalAutomationMetadata.opportunity_key
                == command("pair-a", "a").opportunity_key
            )
        )
        delivery_count = await session.scalar(
            select(func.count(SignalDelivery.id)).where(
                SignalDelivery.signal_id == pending.signal_id
            )
        )
        assert count == 1
        assert delivery_count == 1


@pytest.mark.asyncio
async def test_clean_cross_snapshot_race_and_distinct_origin(database) -> None:
    # New synthetic pair origin, with no pre-existing OPEN signal in this fixture.
    first, second = await asyncio.gather(
        import_command(database, command("pair-race", "race-1")),
        import_command(database, command("pair-race", "race-2")),
    )
    assert sum((first.created, second.created)) == 1
    assert first.signal_id == second.signal_id
    async with database.session() as session, session.begin():
        await session.execute(
            update(Signal).where(Signal.id == first.signal_id).values(
                status="CANCELLED", closed_at=datetime.now(UTC)
            )
        )
    independent = await import_command(database, command("pair-b", "other"))
    assert independent.created is True
    assert independent.signal_id != first.signal_id


@pytest.mark.asyncio
async def test_unrelated_normal_import_keeps_snapshot_key(database) -> None:
    first = command("pair-a", "normal")
    normal = replace(
        first,
        opportunity_variant=None,
        ii_first_open_time=None,
        ii_second_open_time=None,
        opportunity_view=None,
    )
    result = await import_command(database, normal)
    assert result.created is True
    assert result.idempotency_key == normal.idempotency_key
    async with database.session() as session:
        metadata = await session.get(SignalAutomationMetadata, result.signal_id)
        assert metadata.opportunity_variant is None
        assert metadata.opportunity_key is None
