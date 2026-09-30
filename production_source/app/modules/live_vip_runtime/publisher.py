"""Telegram publisher restricted to the configured VIP channel."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from app.modules.live_vip_runtime.entities import LiveVipPublishPayload
from app.modules.paper_runtime.protocols import TelegramBotLike


class TelegramLiveVipPublisher:
    def __init__(self, *, bot: TelegramBotLike, vip_channel_id: int) -> None:
        if vip_channel_id == 0:
            raise ValueError("vip_channel_id must be non-zero")
        self.bot = bot
        self.vip_channel_id = vip_channel_id

    @staticmethod
    def _fmt(value: Decimal | int | float | str) -> str:
        if isinstance(value, Decimal):
            normalized = value.normalize()
            text = format(normalized, "f")
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text
        return str(value)


    @staticmethod
    def _price_fmt(
        value: Decimal | int | float | str | None,
    ) -> str:
        if value is None:
            return "—"

        number = Decimal(str(value))

        if number >= Decimal("100"):
            quant = Decimal("0.01")
        elif number >= Decimal("1"):
            quant = Decimal("0.0001")
        else:
            quant = Decimal("0.00000001")

        return format(
            number.quantize(quant),
            "f",
        ).rstrip("0").rstrip(".")



    @staticmethod
    def _confidence_pct(
        value: Decimal | float | int | None,
    ) -> str:
        if value is None:
            return "—"

        number = Decimal(str(value))

        if number <= Decimal("1"):
            number *= Decimal("100")

        return f"{number.quantize(Decimal('1'))}%"

    @staticmethod
    def _market_label(
        value: str | None,
    ) -> str:
        if not value:
            return "Unknown"

        labels = {
            "TREND": "Trending",
            "RANGE": "Ranging",
            "LOW_VOLATILITY": "Low Volatility",
            "HIGH_VOLATILITY": "High Volatility",
            "REVERSAL": "Reversal",
            "VOLATILE": "Volatile",
        }

        normalized = value.strip().upper()

        return labels.get(
            normalized,
            normalized.replace("_", " ").title(),
        )

    @staticmethod
    def _setup_label(
        value: str | None,
    ) -> str:
        if not value:
            return "—"

        normalized = value.strip().upper()

        for suffix in (
            "_LONG",
            "_SHORT",
        ):
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
                break

        return normalized.replace(
            "_",
            " ",
        ).title()

    @classmethod
    def _risk_reward(cls, payload: LiveVipPublishPayload) -> str | None:
        if not payload.targets:
            return None
        entry = payload.entry_price
        stop = payload.stop_loss
        target = payload.targets[0]

        risk = abs(entry - stop)
        reward = abs(target - entry)

        if risk == 0:
            return None

        rr = reward / risk
        return cls._fmt(rr.quantize(Decimal("0.01")))

    @classmethod
    def _caption(cls, payload: LiveVipPublishPayload) -> str:
        direction = "🟢 LONG" if payload.direction == "LONG" else "🔴 SHORT"
        rr = cls._risk_reward(payload)

        lines = [
            "📡 Signal",
            f"{direction} | {payload.symbol}",
                f"⏱ {payload.timeframe.upper()}",
            
        ]

        if payload.setup_type:
            lines.append(
                f"🎯 Setup: {cls._setup_label(payload.setup_type)}"
            )

        lines.extend(
            [
                f"⭐ Grade: {payload.quality_grade}",
                f"📊 Score: {cls._fmt(payload.final_score)}",
                f"🧠 Confidence: {cls._confidence_pct(payload.confidence)}",
            ]
        )

        if payload.market_regime:
            lines.append(f"📈 Market: {cls._market_label(payload.market_regime)}")

        lines.append("")
        lines.extend(
            [
                f"🔵 Entry: {cls._price_fmt(payload.entry_price)}",
                f"🛑 Stop Loss: {cls._price_fmt(payload.stop_loss)}",
            ]
        )

        for i, target in enumerate(payload.targets, 1):
            lines.append(f"🎯 TP{i}: {cls._price_fmt(target)}")

        lines.append(f"⚙️ Leverage: {cls._fmt(payload.leverage)}x")

        if rr is not None:
            lines.append(f"⚖️ R:R (TP1): 1:{rr}")

        

        lines.append("")
        lines.append("⏳ Status: WAITING FOR ENTRY")

        return "\n".join(lines)

    async def publish(self, payload: LiveVipPublishPayload) -> str:
        chart = Path(payload.chart_path)
        if not await asyncio.to_thread(chart.is_file):
            raise ValueError("chart file does not exist")

        photo = await asyncio.to_thread(chart.open, "rb")
        try:
            message = await self.bot.send_photo(
                chat_id=self.vip_channel_id,
                photo=photo,
                caption=self._caption(payload),
            )
        finally:
            await asyncio.to_thread(photo.close)

        return str(message.message_id)
