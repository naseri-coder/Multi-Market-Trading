"""Real PostgreSQL tests for atomic Brooks import and idempotency."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport
from app.modules.signal_automation.models import SignalAutomationMetadata, SignalRuleEvidence
from app.modules.signal_automation.service import BrooksSignalIntegrationService
from app.modules.operations.models import SignalLifecycleState
from app.modules.signals.models import Signal, SignalEvent, SignalTarget

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for Brooks integration PostgreSQL tests",
)


def command(source_signal_id: str = "INTP2-CORE-1") -> BrooksSignalImport:
    return BrooksSignalImport(
        source_signal_id=source_signal_id,
        symbol="INTP2BTC/USDT",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"), Decimal("120")),
        leverage=Decimal("1"),
        exchange="binance",
        market_type="spot",
        timeframe="15m",
        setup_type="H2",
        market_snapshot_id="intp2-snap-1",
        market_snapshot_hash="intp2-hash-1",
        engine_version="0.10.0",
        rule_set_version="phase2-catalog-v1",
        configuration_version="cfg-integration-phase2",
        reasoning=("context aligned", "risk valid"),
        rule_ids=("BR-007",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR-007", "PASS", (11,)),),
        generation_mode="PAPER",
        publication_scope="PRIVATE_TEST",
        counts_toward_performance=False,
    )


async def test_atomic_import_and_idempotency(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    imported_signal_id = None

    try:
        async with database.session() as session:
            service = BrooksSignalIntegrationService(session)
            first = await service.import_signal(command())
            imported_signal_id = first.signal_id
            second = await service.import_signal(command())

            assert first.created is True
            assert second.created is False
            assert second.signal_id == first.signal_id

        async with database.session() as session:
            signal = await session.get(Signal, imported_signal_id)
            assert signal is not None
            assert signal.publication_scope == "PRIVATE_TEST"

            target_count = await session.scalar(
                select(func.count(SignalTarget.id)).where(
                    SignalTarget.signal_id == imported_signal_id
                )
            )
            event_count = await session.scalar(
                select(func.count(SignalEvent.id)).where(
                    SignalEvent.signal_id == imported_signal_id
                )
            )
            evidence_count = await session.scalar(
                select(func.count(SignalRuleEvidence.id)).where(
                    SignalRuleEvidence.signal_id == imported_signal_id
                )
            )
            metadata = await session.get(SignalAutomationMetadata, imported_signal_id)

            assert target_count == 2
            assert event_count == 3  # CREATED + TARGET_ADDED x2
            assert evidence_count == 1
            assert metadata is not None
            assert metadata.counts_toward_performance is False

        # Cleanup only the test signal; CASCADE removes automation/evidence/targets/events.
        async with database.session() as session:
            async with session.begin():
                await session.execute(delete(Signal).where(Signal.id == imported_signal_id))
    finally:
        await database.dispose()


def _conflict_command(*, source_signal_id: str, symbol: str, direction: str) -> BrooksSignalImport:
    base = command(source_signal_id)
    if direction == "SHORT":
        return replace(
            base, symbol=symbol, direction="SHORT", timeframe="1h",
            entry_price=Decimal("100"), stop_loss=Decimal("105"),
            targets=(Decimal("95"), Decimal("90")),
            market_snapshot_id=f"snap-{source_signal_id}",
            market_snapshot_hash=f"hash-{source_signal_id}",
        )
    return replace(
        base, symbol=symbol, direction="LONG", timeframe="1h",
        entry_price=Decimal("100"), stop_loss=Decimal("95"),
        targets=(Decimal("105"), Decimal("110")),
        market_snapshot_id=f"snap-{source_signal_id}",
        market_snapshot_hash=f"hash-{source_signal_id}",
    )


async def _seed_open_brooks(
    session, *, source: str, symbol: str, direction: str,
    lifecycle_state: str, activated_at: datetime | None, last_price: Decimal,
) -> int:
    signal = Signal(
        symbol=symbol, direction=direction, entry_price=Decimal("100"),
        stop_loss=(Decimal("95") if direction == "LONG" else Decimal("105")),
        leverage=Decimal("1"), status="OPEN", publication_scope="PRIVATE_TEST",
        description=f"fixture-{source}",
    )
    session.add(signal)
    await session.flush()
    cmd = _conflict_command(source_signal_id=source, symbol=symbol, direction=direction)
    session.add(SignalAutomationMetadata(
        signal_id=signal.id, producer="BROOKS", generation_mode="PAPER",
        exchange="binance", market_type="futures", timeframe="1h", setup_type="H2",
        source_signal_id=source, idempotency_key=cmd.idempotency_key,
        market_snapshot_id=cmd.market_snapshot_id, market_snapshot_hash=cmd.market_snapshot_hash,
        engine_version=cmd.engine_version, rule_set_version=cmd.rule_set_version,
        configuration_version=cmd.configuration_version, reasoning=[], rule_ids=[], failed_rules=[],
        analysis_metadata={}, counts_toward_performance=False,
    ))
    session.add(SignalLifecycleState(
        signal_id=signal.id, state=lifecycle_state, entry_activated_at=activated_at,
        last_market_price=last_price,
    ))
    await session.flush()
    return signal.id


@pytest.mark.asyncio
async def test_conflict_semantics_multiple_open_rows_postgresql(valid_token: str) -> None:
    settings = Settings(telegram_bot_token=valid_token, database_url=TEST_DATABASE_URL,
                        db_pool_size=2, db_max_overflow=0, _env_file=None)
    database = DatabaseManager.from_settings(settings)
    created_ids: list[int] = []
    try:
        # C: older ACTIVE must not be hidden by newer valid WAITING_ENTRY.
        symbol = "CFCACTIVEUSDT"
        async with database.session() as session, session.begin():
            older_active = await _seed_open_brooks(
                session, source="cf-c-active-old", symbol=symbol, direction="LONG",
                lifecycle_state="ACTIVE", activated_at=datetime(2026, 9, 15, 12, tzinfo=UTC),
                last_price=Decimal("101"),
            )
            newer_pending = await _seed_open_brooks(
                session, source="cf-c-pending-new", symbol=symbol, direction="LONG",
                lifecycle_state="WAITING_ENTRY", activated_at=None, last_price=Decimal("101"),
            )
            created_ids += [older_active, newer_pending]
        async with database.session() as session:
            result = await BrooksSignalIntegrationService(session).import_signal(
                _conflict_command(source_signal_id="cf-candidate-c", symbol=symbol, direction="SHORT")
            )
            assert result.created is False
            assert result.signal_id == older_active
            assert result.disposition == "SKIPPED_ACTIVE_POSITION_CONFLICT"

        # A/E: stale WAITING_ENTRY reconciles once and does not become ACTIVE conflict.
        symbol = "CFCSTALEUSDT"
        async with database.session() as session, session.begin():
            stale_id = await _seed_open_brooks(
                session, source="cf-a-stale", symbol=symbol, direction="LONG",
                lifecycle_state="WAITING_ENTRY", activated_at=None, last_price=Decimal("94"),
            )
            created_ids.append(stale_id)
        cmd = _conflict_command(source_signal_id="cf-a-new-short", symbol=symbol, direction="SHORT")
        async with database.session() as session:
            first = await BrooksSignalIntegrationService(session).import_signal(cmd)
            second = await BrooksSignalIntegrationService(session).import_signal(cmd)
            assert first.created is True
            assert first.disposition == "STALE_SIGNAL_RECONCILED"
            assert second.created is False
            assert second.signal_id == first.signal_id
            assert second.disposition == "SKIPPED_DUPLICATE"
            created_ids.append(first.signal_id)
        async with database.session() as session:
            stale_signal = await session.get(Signal, stale_id)
            stale_lifecycle = await session.get(SignalLifecycleState, stale_id)
            cancelled = await session.scalar(select(func.count(SignalEvent.id)).where(
                SignalEvent.signal_id == stale_id, SignalEvent.event_type == "CANCELLED"
            ))
            assert stale_signal is not None and stale_signal.status == "CANCELLED"
            assert stale_lifecycle is not None and stale_lifecycle.state == "COMPLETE"
            assert cancelled == 1

        # B: genuine ACTIVE opposite remains blocked.
        symbol = "CFCACTONLYUSDT"
        async with database.session() as session, session.begin():
            active_id = await _seed_open_brooks(
                session, source="cf-b-active", symbol=symbol, direction="LONG",
                lifecycle_state="ACTIVE", activated_at=datetime(2026, 9, 15, 12, tzinfo=UTC),
                last_price=Decimal("101"),
            )
            created_ids.append(active_id)
        async with database.session() as session:
            blocked = await BrooksSignalIntegrationService(session).import_signal(
                _conflict_command(source_signal_id="cf-b-new-short", symbol=symbol, direction="SHORT")
            )
            assert blocked.created is False
            assert blocked.signal_id == active_id
            assert blocked.disposition == "SKIPPED_ACTIVE_POSITION_CONFLICT"
    finally:
        async with database.session() as session, session.begin():
            if created_ids:
                await session.execute(delete(Signal).where(Signal.id.in_(created_ids)))
        await database.dispose()
