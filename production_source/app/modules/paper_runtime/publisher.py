"""Telegram adapter restricted to the configured PRIVATE TEST channel."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.modules.paper_runtime.entities import PaperPublishPayload
from app.modules.paper_runtime.protocols import TelegramBotLike


class TelegramPaperPublisher:
    def __init__(self, *, bot: TelegramBotLike, private_test_channel_id: int) -> None:
        if private_test_channel_id == 0:
            raise ValueError("private_test_channel_id must be non-zero")
        self.bot = bot
        self.private_test_channel_id = private_test_channel_id

    @staticmethod
    def _caption(payload: PaperPublishPayload) -> str:
        direction = "🟢 LONG" if payload.direction == "LONG" else "🔴 SHORT"
        lines = [
            f"{direction} | {payload.symbol}",
            f"Timeframe: {payload.timeframe}",
            "Mode: PAPER",
        ]
        if payload.setup_type:
            lines.append(f"Setup: {payload.setup_type}")
        lines += [
            f"Entry: {payload.entry_price}",
            f"SL: {payload.stop_loss}",
        ]
        for i, target in enumerate(payload.targets, 1):
            lines.append(f"TP{i}: {target}")
        if payload.rule_ids:
            lines.append("Rules: " + ", ".join(payload.rule_ids))
        if payload.reasoning:
            lines.append("Reasons:")
            lines.extend(f"- {reason}" for reason in payload.reasoning)
        lines.append(f"Snapshot: {payload.market_snapshot_id}")
        return "\n".join(lines)

    async def publish(self, payload: PaperPublishPayload) -> str:
        chart = Path(payload.chart_path)
        if not await asyncio.to_thread(chart.is_file):
            raise ValueError("chart file does not exist")
        photo = await asyncio.to_thread(chart.open, "rb")
        try:
            message = await self.bot.send_photo(
                chat_id=self.private_test_channel_id,
                photo=photo,
                caption=self._caption(payload),
            )
        finally:
            await asyncio.to_thread(photo.close)
        return str(message.message_id)
