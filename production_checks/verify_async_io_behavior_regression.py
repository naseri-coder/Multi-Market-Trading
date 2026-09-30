"""Regression harness for async publisher and shadow-replay file behavior.

This intentionally tests observable behavior before async-I/O remediation.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from app.modules.live_vip_runtime.entities import LiveVipPublishPayload
from app.modules.live_vip_runtime.publisher import TelegramLiveVipPublisher
from app.modules.paper_runtime.entities import PaperPublishPayload
from app.modules.paper_runtime.publisher import TelegramPaperPublisher
from app.modules.shadow_replay import cli as shadow_cli


class _Bot:
    def __init__(self) -> None:
        self.calls = []

    async def send_photo(self, **kwargs):
        photo = kwargs["photo"]
        assert not photo.closed
        assert photo.read() == b"PNG"
        photo.seek(0)
        self.calls.append(kwargs)
        return SimpleNamespace(message_id=12345)


async def _publishers(root: Path) -> None:
    chart = root / "chart.png"
    chart.write_bytes(b"PNG")
    bot = _Bot()

    paper = TelegramPaperPublisher(bot=bot, private_test_channel_id=-1001)
    paper_payload = PaperPublishPayload(
        signal_id=1, symbol="BTCUSDT", timeframe="15m", direction="LONG",
        setup_type="H2", entry_price=Decimal("100"), stop_loss=Decimal("99"),
        targets=(Decimal("102"),), reasoning=("test",), rule_ids=("R1",),
        market_snapshot_id="snap", market_snapshot_hash="hash", chart_path=str(chart),
    )
    assert await paper.publish(paper_payload) == "12345"
    assert bot.calls[-1]["chat_id"] == -1001
    assert bot.calls[-1]["photo"].closed

    live = TelegramLiveVipPublisher(bot=bot, vip_channel_id=-1002)
    live_payload = LiveVipPublishPayload(
        signal_id=2, symbol="BTCUSDT", timeframe="15m", direction="LONG",
        setup_type="H2_LONG", entry_price=Decimal("100"), stop_loss=Decimal("99"),
        targets=(Decimal("102"),), leverage=Decimal("2"),
        market_snapshot_id="snap", chart_path=str(chart), quality_grade="A",
        final_score=Decimal("90"), confidence=Decimal("0.8"), market_regime="TREND",
    )
    assert await live.publish(live_payload) == "12345"
    assert bot.calls[-1]["chat_id"] == -1002
    assert bot.calls[-1]["photo"].closed

    missing = root / "missing.png"
    bad = PaperPublishPayload(
        signal_id=3, symbol="BTCUSDT", timeframe="15m", direction="LONG",
        setup_type=None, entry_price=Decimal("100"), stop_loss=Decimal("99"),
        targets=(), reasoning=(), rule_ids=(), market_snapshot_id="snap",
        market_snapshot_hash="hash", chart_path=str(missing),
    )
    try:
        await paper.publish(bad)
    except ValueError as exc:
        assert str(exc) == "chart file does not exist"
    else:
        raise AssertionError("missing chart must be rejected")


async def _shadow_output(root: Path) -> None:
    output = root / "shadow.json"

    class _Source:
        exchange = "binance"
        async def get_closed_candles(self, **kwargs):
            return ()
        async def aclose(self):
            return None

    class _Service:
        def __init__(self, **kwargs):
            pass
        async def replay(self, **kwargs):
            return SimpleNamespace(
                metrics=SimpleNamespace(
                    evaluated_snapshots=0, h2_count=0, l2_count=0,
                    ambiguous_count=0, blocked_count=0, no_signal_count=0,
                    detections_per_1000_snapshots=0,
                )
            )

    old_source = shadow_cli.BinanceHistoricalCandleSource
    old_service = shadow_cli.CausalShadowReplayService
    old_report = shadow_cli.report_to_json
    try:
        shadow_cli.BinanceHistoricalCandleSource = _Source
        shadow_cli.CausalShadowReplayService = _Service
        shadow_cli.report_to_json = lambda report: '{"ok":true}'
        args = SimpleNamespace(
            exchange="binance", market_type="spot", symbol="BTCUSDT",
            timeframe="15m", candles=10, window=5, end_at=None, output=str(output),
        )
        assert await shadow_cli._run(args) == 0
        assert output.read_text(encoding="utf-8") == '{"ok":true}\n'
    finally:
        shadow_cli.BinanceHistoricalCandleSource = old_source
        shadow_cli.CausalShadowReplayService = old_service
        shadow_cli.report_to_json = old_report


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        await _publishers(root)
        await _shadow_output(root)
    print("ASYNC_IO_BEHAVIOR_REGRESSION_PASS")


if __name__ == "__main__":
    asyncio.run(main())
