from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.live_vip_runtime.service import LiveVipRuntimeService


def _candidate():
    return SimpleNamespace(
        source_signal_id="src-1", symbol="BTCUSDT", timeframe="1h",
        direction="SHORT", entry_price=Decimal("76000"), stop_loss=Decimal("77000"),
        targets=(Decimal("75000"), Decimal("74000")), exchange="binance",
        market_type="futures", setup_type="BREAKOUT_PULLBACK_SHORT",
        market_snapshot_id="snap-1", market_snapshot_hash="hash-1",
        engine_version="core-v5", rule_set_version="rules-v6",
        configuration_version="cfg", reasoning=("ok",), rule_ids=("BR",),
        failed_rules=(), rule_evidence=(), chart_path="/tmp/chart.png",
    )


@pytest.mark.asyncio
async def test_live_conflict_classification_does_not_publish() -> None:
    integration = AsyncMock()
    integration.import_signal.return_value = SimpleNamespace(
        signal_id=70, created=False, disposition="SKIPPED_VALID_PENDING_CONFLICT"
    )
    publisher = AsyncMock()
    service = LiveVipRuntimeService(
        SimpleNamespace(), publisher=publisher, vip_channel_id=-1001,
        default_leverage=Decimal("1"),
        integration_service_factory=lambda _: integration,
        delivery_repository_factory=lambda _: AsyncMock(),
    )
    result = await service.process(
        _candidate(),
        signal_quality=SimpleNamespace(quality_grade="A", final_score=90, confidence=0.8, metadata={}),
    )
    assert result.signal_id == 70
    assert result.signal_created is False
    assert result.delivery_status == "SKIPPED_VALID_PENDING_CONFLICT"
    publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_active_conflict_is_not_mislabeled_duplicate() -> None:
    integration = AsyncMock()
    integration.import_signal.return_value = SimpleNamespace(
        signal_id=71, created=False, disposition="SKIPPED_ACTIVE_POSITION_CONFLICT"
    )
    publisher = AsyncMock()
    service = LiveVipRuntimeService(
        SimpleNamespace(), publisher=publisher, vip_channel_id=-1001,
        default_leverage=Decimal("1"), integration_service_factory=lambda _: integration,
        delivery_repository_factory=lambda _: AsyncMock(),
    )
    result = await service.process(
        _candidate(),
        signal_quality=SimpleNamespace(quality_grade="A", final_score=90, confidence=0.8, metadata={}),
    )
    assert result.signal_id == 71
    assert result.signal_created is False
    assert result.delivery_status == "SKIPPED_ACTIVE_POSITION_CONFLICT"
    publisher.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_exact_duplicate_remains_skipped_duplicate() -> None:
    integration = AsyncMock()
    integration.import_signal.return_value = SimpleNamespace(
        signal_id=72, created=False, disposition="SKIPPED_DUPLICATE"
    )
    publisher = AsyncMock()
    service = LiveVipRuntimeService(
        SimpleNamespace(), publisher=publisher, vip_channel_id=-1001,
        default_leverage=Decimal("1"), integration_service_factory=lambda _: integration,
        delivery_repository_factory=lambda _: AsyncMock(),
    )
    result = await service.process(
        _candidate(),
        signal_quality=SimpleNamespace(quality_grade="A", final_score=90, confidence=0.8, metadata={}),
    )
    assert result.signal_id == 72
    assert result.signal_created is False
    assert result.delivery_status == "SKIPPED_DUPLICATE"
    publisher.publish.assert_not_awaited()
