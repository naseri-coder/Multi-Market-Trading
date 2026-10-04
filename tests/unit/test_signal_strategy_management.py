"""Signal strategy management foundation tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.live_vip_runtime.entities import LiveVipPublishPayload
from app.modules.live_vip_runtime.publisher import TelegramLiveVipPublisher
from app.modules.signal_strategies.entities import SignalStrategyRecord
from app.modules.signal_strategies.errors import (
    SignalStrategyChannelRequiredError,
    SignalStrategyEngineNotReadyError,
)
from app.modules.signal_strategies.publisher import TelegramStrategyVipPublisher
from app.modules.fm_runtime.coordinator import FMRuntimeCoordinator
from app.modules.fm_runtime.registry import FMEngineRegistry
from app.modules.signal_strategies.service import SignalStrategyService

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def _record(
    *,
    code: str = "BROOKS",
    enabled: bool = False,
    engine_ready: bool = True,
    channel_id: int | None = None,
) -> SignalStrategyRecord:
    return SignalStrategyRecord(
        id=1,
        strategy_code=code,
        display_name="Price Action (Al Brooks)" if code == "BROOKS" else "FM",
        enabled=enabled,
        engine_ready=engine_ready,
        private_channel_id=channel_id,
        private_channel_title="VIP" if channel_id is not None else None,
        private_channel_username=None,
        updated_by_telegram_user_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


class _Repo:
    def __init__(self, record: SignalStrategyRecord) -> None:
        self.record = record

    async def list_all(self):
        return (self.record,)

    async def get(self, strategy_code: str):
        assert strategy_code == self.record.strategy_code
        return self.record

    async def set_enabled(self, strategy_code: str, enabled: bool, **kwargs):
        del strategy_code, kwargs
        self.record = replace(self.record, enabled=enabled)
        return self.record

    async def set_channel(self, strategy_code: str, *, chat_id: int, title: str, username, **kwargs):
        del strategy_code, kwargs
        self.record = replace(
            self.record,
            private_channel_id=chat_id,
            private_channel_title=title,
            private_channel_username=username,
        )
        return self.record

    async def clear_channel(self, strategy_code: str, **kwargs):
        del strategy_code, kwargs
        self.record = replace(
            self.record,
            enabled=False,
            private_channel_id=None,
            private_channel_title=None,
            private_channel_username=None,
        )
        return self.record

    async def set_engine_ready(self, strategy_code: str, ready: bool):
        assert strategy_code == self.record.strategy_code
        self.record = replace(self.record, engine_ready=ready)
        return self.record


@pytest.mark.asyncio
async def test_brooks_requires_private_channel_before_enabling() -> None:
    service = SignalStrategyService(_Repo(_record()))

    with pytest.raises(SignalStrategyChannelRequiredError):
        await service.toggle("BROOKS", updated_by_telegram_user_id=123)


@pytest.mark.asyncio
async def test_fm_cannot_enable_before_engine_is_connected() -> None:
    service = SignalStrategyService(
        _Repo(_record(code="FM", engine_ready=False, channel_id=-100222))
    )

    with pytest.raises(SignalStrategyEngineNotReadyError):
        await service.toggle("FM", updated_by_telegram_user_id=123)


@pytest.mark.asyncio
async def test_brooks_can_enable_after_channel_configuration() -> None:
    service = SignalStrategyService(_Repo(_record(channel_id=-100111)))

    result = await service.toggle("BROOKS", updated_by_telegram_user_id=123)

    assert result.enabled is True
    assert result.effective_enabled is True


@pytest.mark.asyncio
async def test_clearing_channel_also_disables_strategy() -> None:
    service = SignalStrategyService(
        _Repo(_record(enabled=True, channel_id=-100111))
    )

    result = await service.clear_channel(
        "BROOKS", updated_by_telegram_user_id=123
    )

    assert result.enabled is False
    assert result.private_channel_id is None
    assert result.effective_enabled is False


def test_strategy_publisher_reuses_exact_existing_vip_caption() -> None:
    payload = LiveVipPublishPayload(
        signal_id=1,
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        setup_type="BREAKOUT_LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"),),
        leverage=Decimal("1"),
        market_snapshot_id="snapshot-1",
        chart_path="/tmp/chart.png",
        quality_grade="A",
        final_score=Decimal("90"),
        confidence=Decimal("0.75"),
        market_regime="TREND",
    )

    assert TelegramStrategyVipPublisher._caption(payload) == (
        TelegramLiveVipPublisher._caption(payload)
    )


class _FakeFMEngine:
    engine_id = "fm-test-engine"
    engine_version = "0.0.test"

    def __init__(self) -> None:
        self.started_contexts = []
        self.shutdown_calls = 0

    async def start(self, context) -> None:
        self.started_contexts.append(context)

    async def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_fm_registry_is_fail_closed_until_engine_is_registered() -> None:
    registry = FMEngineRegistry()
    assert registry.ready is False
    assert registry.get() is None

    engine = _FakeFMEngine()
    registry.register(engine)

    assert registry.ready is True
    assert registry.get() is engine


@pytest.mark.asyncio
async def test_fm_coordinator_starts_only_on_effective_fm_route(monkeypatch) -> None:
    registry = FMEngineRegistry()
    engine = _FakeFMEngine()
    registry.register(engine)
    coordinator = FMRuntimeCoordinator(database=object(), registry=registry)

    route = _record(
        code="FM",
        enabled=True,
        engine_ready=True,
        channel_id=-100222,
    )

    async def _route():
        return route

    async def _sync(ready: bool):
        assert ready is True
        return route

    monkeypatch.setattr(coordinator, "_load_route", _route)
    monkeypatch.setattr(coordinator, "_sync_engine_ready", _sync)

    application = SimpleNamespace(bot=object())
    coordinator._application = application
    await coordinator._reconcile_once()

    assert len(engine.started_contexts) == 1
    assert engine.started_contexts[0].private_channel_id == -100222


@pytest.mark.asyncio
async def test_fm_coordinator_does_not_start_when_route_disabled(monkeypatch) -> None:
    registry = FMEngineRegistry()
    engine = _FakeFMEngine()
    registry.register(engine)
    coordinator = FMRuntimeCoordinator(database=object(), registry=registry)

    route = _record(
        code="FM",
        enabled=False,
        engine_ready=True,
        channel_id=-100222,
    )

    async def _route():
        return route

    monkeypatch.setattr(coordinator, "_load_route", _route)
    coordinator._application = SimpleNamespace(bot=object())
    await coordinator._reconcile_once()

    assert engine.started_contexts == []


def test_fm_runtime_has_no_brooks_imports() -> None:
    from pathlib import Path
    import app.modules.fm_runtime as fm_runtime

    package = Path(fm_runtime.__file__).resolve().parent
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )
    assert "app.modules.brooks_" not in source
    assert "BrooksFullCore" not in source
