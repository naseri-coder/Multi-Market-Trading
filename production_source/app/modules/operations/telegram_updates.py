"""Edit VIP signals with V6 scale-out, runner, and stop-management state."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from telegram import Bot

from app.modules.signal_automation.models import SignalAutomationMetadata
from app.modules.signals.models import Signal, SignalTarget


def _fmt(
    value: Decimal | int | float | str | None,
) -> str:
    if value is None:
        return "—"

    if not isinstance(value, Decimal):
        value = Decimal(str(value))

    text = format(value, "f")

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text or "0"


def _price_fmt(
    value: Decimal | int | float | str | None,
) -> str:
    if value is None:
        return "—"

    number = Decimal(str(value))
    magnitude = abs(number)

    if magnitude >= Decimal("100"):
        return format(
            number.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            ),
            "f",
        )

    if magnitude >= Decimal("1"):
        text = format(
            number.quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            ),
            "f",
        )
    else:
        text = format(
            number.quantize(
                Decimal("0.00000001"),
                rounding=ROUND_HALF_UP,
            ),
            "f",
        )

    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text or "0"


def _confidence_pct(
    value: Decimal | int | float | None,
) -> str:
    if value is None:
        return "—"

    number = Decimal(str(value))

    if number <= Decimal("1"):
        number *= Decimal("100")

    number = number.quantize(
        Decimal("1"),
        rounding=ROUND_HALF_UP,
    )

    return f"{number}%"


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
            normalized = normalized[: -len(suffix)]
            break

    return normalized.replace(
        "_",
        " ",
    ).title()


def _display_pct(value: Decimal) -> str:
    value = value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    prefix = "+" if value > 0 else ""

    return f"{prefix}{value}%"


def _live_return_pct(
    *,
    direction: str,
    entry: Decimal,
    price: Decimal,
    leverage: Decimal,
) -> Decimal:
    raw = (price - entry) / entry if direction == "LONG" else (entry - price) / entry

    return (raw * Decimal("100") * leverage).quantize(
        Decimal("0.00000001"),
        rounding=ROUND_HALF_UP,
    )


def render_live_caption(
    *,
    signal: Signal,
    metadata: SignalAutomationMetadata,
    targets: tuple[SignalTarget, ...],
    lifecycle_state: str,
    ambiguous_reason: str | None = None,
    last_market_price: Decimal | None = None,
    entry_activated: bool = False,
    quality_grade: str | None = None,
    final_score: Decimal | None = None,
    confidence: Decimal | None = None,
    market_regime: str | None = None,
    stop_management_note: str | None = None,
    trade_management_note: str | None = None,
    terminal_stop_hit: bool = False,
    runner_reversal: bool = False,
) -> str:
    direction = "🟢 LONG" if signal.direction == "LONG" else "🔴 SHORT"

    hit_targets = tuple(target for target in targets if target.status == "HIT")

    all_targets_hit = bool(targets) and all(target.status == "HIT" for target in targets)

    stop_hit = terminal_stop_hit or (lifecycle_state == "COMPLETE" and not all_targets_hit and not runner_reversal)

    lines = [
        "📡 Signal",
        f"{direction} | {signal.symbol}",
        f"⏱ {metadata.timeframe.upper()}",
    ]

    if metadata.setup_type:
        lines.append(f"🎯 Setup: {_setup_label(metadata.setup_type)}")

    if quality_grade is not None:
        lines.append(f"⭐ Grade: {quality_grade}")

    if final_score is not None:
        lines.append(f"📊 Score: {_fmt(final_score)}")

    if confidence is not None:
        lines.append(f"🧠 Confidence: {_confidence_pct(confidence)}")

    if market_regime:
        lines.append(f"📈 Market: {_market_label(market_regime)}")

    lines.append("")

    entry_suffix = " ✅" if entry_activated else ""

    lines.append(f"🔵 Entry: {_price_fmt(signal.entry_price)}{entry_suffix}")

    stop_suffix = " ❌" if stop_hit else ""

    lines.append(f"🛑 Stop Loss: {_price_fmt(signal.stop_loss)}{stop_suffix}")
    if stop_management_note:
        lines.append(stop_management_note)
    if trade_management_note:
        lines.append(trade_management_note)

    for target in targets:
        target_suffix = " ✅" if target.status == "HIT" else ""

        lines.append(
            f"🎯 TP{target.target_number}: {_price_fmt(target.target_price)}{target_suffix}"
        )

    lines.append(f"⚙️ Leverage: {_fmt(signal.leverage)}x")

    lines.append("")

    if lifecycle_state == "WAITING_ENTRY":
        lines.append("⏳ Status: WAITING FOR ENTRY")

    elif lifecycle_state == "ACTIVE":
        if hit_targets:
            last_hit = hit_targets[-1]

            lines.append(f"🎯 Progress: TP{last_hit.target_number} HIT ✅")

        if last_market_price is None:
            lines.append("📡 Status: LIVE")
        else:
            live_pnl = _live_return_pct(
                direction=signal.direction,
                entry=signal.entry_price,
                price=last_market_price,
                leverage=signal.leverage,
            )

            lines.append(f"💵 Live Price: {_price_fmt(last_market_price)}")

            if live_pnl > 0:
                lines.append("📈 Status: LIVE • IN PROFIT ✅")

            elif live_pnl < 0:
                lines.append("📉 Status: LIVE • IN LOSS ⚠️")

            else:
                lines.append("📡 Status: LIVE • AT ENTRY")

            lines.append(f"💰 Live P/L: {_display_pct(live_pnl)}")

    elif lifecycle_state == "COMPLETE":
        if runner_reversal and not terminal_stop_hit:
            lines.append("🏁 Result: RUNNER CLOSED • ALWAYS-IN REVERSAL")
        elif all_targets_hit and not terminal_stop_hit:
            lines.append("🎯 Result: ALL TARGETS HIT ✅")
        elif all_targets_hit and terminal_stop_hit:
            lines.append("🏁 Result: TARGETS HIT • RUNNER STOPPED")

        final_pnl = signal.profit_loss

        if final_pnl is None:
            lines.append("🏁 Status: CLOSED")

        elif final_pnl > 0:
            lines.append("🏆 Status: CLOSED • PROFIT ✅")
            lines.append(f"💰 Final P/L: {_display_pct(final_pnl)}")

        elif final_pnl < 0:
            lines.append("🏁 Status: CLOSED • LOSS ❌")
            lines.append(f"💰 Final P/L: {_display_pct(final_pnl)}")

        else:
            lines.append("🏁 Status: CLOSED • BREAK EVEN")
            lines.append("💰 Final P/L: 0.00%")

    elif lifecycle_state == "AMBIGUOUS":
        lines.append("⚠️ Status: CLOSED • AMBIGUOUS")

        if ambiguous_reason:
            lines.append("Result not counted in Win Rate due to intrabar ambiguity.")

    else:
        lines.append(f"Status: {lifecycle_state}")

    return "\n".join(lines)


async def edit_live_signal_message(
    bot: Bot,
    *,
    chat_id: int,
    message_id: int,
    caption: str,
) -> None:
    await bot.edit_message_caption(
        chat_id=chat_id,
        message_id=message_id,
        caption=caption,
        connect_timeout=10,
        read_timeout=20,
        write_timeout=20,
        pool_timeout=10,
    )
