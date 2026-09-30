from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.paper_runtime.service import PaperRuntimeService
from app.modules.signal_automation.entities import BrooksRuleEvidence


class Tx:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        return False


class Session:
    def begin(self):
        return Tx()


def candidate():
    opened = datetime(2026, 9, 2, tzinfo=UTC)
    snapshot = MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=(Candle(
            open_time=opened,
            close_time=opened.replace(minute=15),
            open=Decimal("100"), high=Decimal("101"),
            low=Decimal("99"), close=Decimal("100.5"), volume=Decimal("10"),
        ),),
        captured_at=opened.replace(minute=15),
        source="UNIT_TEST",
    )
    return PaperSignalCandidate(
        snapshot=snapshot,
        source_signal_id="paper-core-1",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"), Decimal("120")),
        exchange="binance",
        market_type="spot",
        setup_type="H2",
        market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash,
        engine_version="0.10.0",
        rule_set_version="phase2-catalog-v1",
        configuration_version="cfg-paper-1",
        reasoning=("context aligned",),
        rule_ids=("BR-007",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BR-007", "PASS", (11,)),),
        chart_path="/tmp/chart.png",
    )


@pytest.mark.asyncio
async def test_paper_runtime_persists_private_test_and_marks_sent() -> None:
    session = Session()
    integration = AsyncMock()
    integration.import_signal.return_value = SimpleNamespace(signal_id=42, created=True)

    repo = AsyncMock()
    repo.get.return_value = None
    repo.create_pending.return_value = SimpleNamespace(
        id=7, status="PENDING", external_message_id=None
    )
    repo.mark_sending.return_value = SimpleNamespace(id=7, status="SENDING")
    repo.mark_sent.return_value = SimpleNamespace(
        id=7, status="SENT", external_message_id="99"
    )

    publisher = AsyncMock()
    publisher.publish.return_value = "99"

    service = PaperRuntimeService(
        session,
        publisher=publisher,
        private_test_channel_id=-100123,
        default_leverage=Decimal("1"),
        clock=lambda: datetime(2026, 9, 2, tzinfo=UTC),
        integration_service_factory=lambda _: integration,
        delivery_repository_factory=lambda _: repo,
    )

    result = await service.process(candidate())

    command = integration.import_signal.await_args.args[0]
    assert command.generation_mode == "PAPER"
    assert command.publication_scope == "PRIVATE_TEST"
    assert command.counts_toward_performance is False
    assert result.delivery_status == "SENT"
    publisher.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_sent_delivery_is_not_published_twice() -> None:
    session = Session()
    integration = AsyncMock()
    integration.import_signal.return_value = SimpleNamespace(
        signal_id=42, created=False, disposition="SKIPPED_DUPLICATE"
    )

    repo = AsyncMock()
    repo.get.return_value = SimpleNamespace(
        id=7, status="SENT", external_message_id="99"
    )
    publisher = AsyncMock()

    service = PaperRuntimeService(
        session,
        publisher=publisher,
        private_test_channel_id=-100123,
        default_leverage=Decimal("1"),
        integration_service_factory=lambda _: integration,
        delivery_repository_factory=lambda _: repo,
    )
    result = await service.process(candidate())
    assert result.delivery_status == "SENT"
    publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_sending_or_ambiguous_is_fail_closed() -> None:
    for status in ("SENDING", "AMBIGUOUS"):
        session = Session()
        integration = AsyncMock()
        integration.import_signal.return_value = SimpleNamespace(
        signal_id=42, created=False, disposition="SKIPPED_DUPLICATE"
    )
        repo = AsyncMock()
        repo.get.return_value = SimpleNamespace(
            id=7, status=status, external_message_id=None
        )
        publisher = AsyncMock()
        service = PaperRuntimeService(
            session,
            publisher=publisher,
            private_test_channel_id=-100123,
            default_leverage=Decimal("1"),
            integration_service_factory=lambda _: integration,
            delivery_repository_factory=lambda _: repo,
        )
        result = await service.process(candidate())
        assert result.delivery_status == status
        publisher.publish.assert_not_awaited()
