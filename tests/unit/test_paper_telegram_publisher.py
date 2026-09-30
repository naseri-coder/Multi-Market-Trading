from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.paper_runtime.entities import PaperPublishPayload
from app.modules.paper_runtime.publisher import TelegramPaperPublisher


@pytest.mark.asyncio
async def test_private_test_publisher_uses_only_configured_channel(tmp_path: Path) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"PNG")
    bot = AsyncMock()
    bot.send_photo.return_value = SimpleNamespace(message_id=123)

    publisher = TelegramPaperPublisher(
        bot=bot,
        private_test_channel_id=-100999,
    )
    payload = PaperPublishPayload(
        signal_id=1,
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        setup_type="H2",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"),),
        reasoning=("ok",),
        rule_ids=("BR-007",),
        market_snapshot_id="snap",
        market_snapshot_hash="hash",
        chart_path=str(chart),
    )
    message_id = await publisher.publish(payload)
    assert message_id == "123"
    assert bot.send_photo.await_args.kwargs["chat_id"] == -100999
    assert "Mode: PAPER" in bot.send_photo.await_args.kwargs["caption"]
