from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from app.modules.market_data.entities import MarketSnapshot


class MatplotlibSignalChartRenderer:
    def __init__(
        self,
        *,
        dpi: int = 140,
        max_candles: int = 120,
        ema_period: int = 20,
        swing_window: int = 2,
    ) -> None:
        if dpi < 72:
            raise ValueError("dpi must be at least 72")
        if max_candles < 20:
            raise ValueError("max_candles must be at least 20")
        if ema_period < 2:
            raise ValueError("ema_period must be at least 2")
        if swing_window < 1:
            raise ValueError("swing_window must be at least 1")

        self.dpi = dpi
        self.max_candles = max_candles
        self.ema_period = ema_period
        self.swing_window = swing_window

    @staticmethod
    def _to_float(value: Decimal | int | float) -> float:
        return float(value)

    @staticmethod
    def _format_price(value: Decimal | int | float) -> str:
        numeric = float(value)

        if abs(numeric) >= 1000:
            return f"{numeric:,.2f}"
        if abs(numeric) >= 1:
            return f"{numeric:,.4f}"
        return f"{numeric:,.6f}"

    def _ema(self, values: list[float]) -> list[float]:
        if not values:
            return []

        multiplier = 2 / (self.ema_period + 1)
        result = [values[0]]

        for price in values[1:]:
            result.append(
                ((price - result[-1]) * multiplier) + result[-1]
            )

        return result

    @staticmethod
    def _atr(
        highs: list[float],
        lows: list[float],
        closes: list[float],
        period: int = 14,
    ) -> float:
        if not highs:
            return 0.0

        true_ranges: list[float] = []

        for index in range(len(highs)):
            if index == 0:
                true_range = highs[index] - lows[index]
            else:
                true_range = max(
                    highs[index] - lows[index],
                    abs(highs[index] - closes[index - 1]),
                    abs(lows[index] - closes[index - 1]),
                )

            true_ranges.append(true_range)

        sample = true_ranges[-period:]

        if not sample:
            return 0.0

        return sum(sample) / len(sample)

    def _swing_points(
        self,
        highs: list[float],
        lows: list[float],
    ) -> list[dict[str, object]]:
        points: list[dict[str, object]] = []
        window = self.swing_window

        if len(highs) < (window * 2) + 1:
            return points

        for index in range(window, len(highs) - window):
            local_highs = highs[index - window:index + window + 1]
            local_lows = lows[index - window:index + window + 1]

            if highs[index] == max(local_highs):
                points.append(
                    {
                        "index": index,
                        "kind": "HIGH",
                        "price": highs[index],
                    }
                )

            if lows[index] == min(local_lows):
                points.append(
                    {
                        "index": index,
                        "kind": "LOW",
                        "price": lows[index],
                    }
                )

        points.sort(key=lambda item: int(item["index"]))

        previous_high: float | None = None
        previous_low: float | None = None

        classified: list[dict[str, object]] = []

        for point in points:
            price = float(point["price"])
            kind = str(point["kind"])

            if kind == "HIGH":
                if previous_high is None:
                    label = "SH"
                elif price > previous_high:
                    label = "HH"
                else:
                    label = "LH"

                previous_high = price

            else:
                if previous_low is None:
                    label = "SL"
                elif price > previous_low:
                    label = "HL"
                else:
                    label = "LL"

                previous_low = price

            classified.append(
                {
                    **point,
                    "label": label,
                }
            )

        return classified

    @staticmethod
    def _select_structure_levels(
        swings: list[dict[str, object]],
        current_price: float,
    ) -> tuple[float | None, float | None]:
        highs = [
            float(item["price"])
            for item in swings
            if item["kind"] == "HIGH"
        ]
        lows = [
            float(item["price"])
            for item in swings
            if item["kind"] == "LOW"
        ]

        resistance: float | None = None
        support: float | None = None

        above = [price for price in highs if price >= current_price]
        below = [price for price in lows if price <= current_price]

        if above:
            resistance = min(above, key=lambda value: abs(value - current_price))
        elif highs:
            resistance = highs[-1]

        if below:
            support = min(below, key=lambda value: abs(value - current_price))
        elif lows:
            support = lows[-1]

        return support, resistance

    @staticmethod
    def _price_padding(high: float, low: float) -> float:
        span = high - low

        if span <= 0:
            return max(abs(high) * 0.01, 1.0)

        return max(
            span * 0.08,
            abs(high) * 0.002,
        )

    @staticmethod
    def _breakout_level(
        *,
        highs: list[float],
        lows: list[float],
        direction: str,
    ) -> float | None:
        if len(highs) < 12:
            return None

        # Do not use the latest few candles when calculating the
        # pre-breakout reference structure.
        reference_highs = highs[-35:-4]
        reference_lows = lows[-35:-4]

        if not reference_highs or not reference_lows:
            return None

        if direction == "LONG":
            return max(reference_highs)

        return min(reference_lows)

    @staticmethod
    def _pullback_index(
        *,
        highs: list[float],
        lows: list[float],
        breakout_level: float,
        direction: str,
    ) -> int | None:
        if len(highs) < 3:
            return None

        start = max(0, len(highs) - 10)
        indexes = list(range(start, len(highs)))

        if direction == "LONG":
            return min(
                indexes,
                key=lambda index: abs(lows[index] - breakout_level),
            )

        return min(
            indexes,
            key=lambda index: abs(highs[index] - breakout_level),
        )

    def render(
        self,
        *,
        snapshot: MarketSnapshot,
        direction: str,
        entry_price: Decimal,
        stop_loss: Decimal,
        targets: tuple[Decimal, ...],
        setup_type: str | None,
        output_path: Path,
        chart_evidence=None,
    ) -> Path:
        if direction not in {"LONG", "SHORT"}:
            raise ValueError("direction must be LONG or SHORT")

        if not targets:
            raise ValueError("at least one target is required")

        candles = snapshot.candles[-self.max_candles:]

        if len(candles) < 20:
            raise ValueError(
                "at least twenty candles are required for professional chart rendering"
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ------------------------------------------------------------
        # PROFESSIONAL DARK THEME
        # ------------------------------------------------------------

        background = "#0f172a"
        panel = "#111827"
        grid = "#334155"

        text = "#e2e8f0"
        muted = "#94a3b8"

        bullish = "#22c55e"
        bearish = "#ef4444"

        ema_color = "#facc15"

        entry_color = "#38bdf8"
        stop_color = "#ef4444"
        target_color = "#22c55e"

        support_color = "#22c55e"
        resistance_color = "#f97316"

        structure_high_color = "#fb923c"
        structure_low_color = "#60a5fa"

        breakout_color = "#c084fc"
        pullback_color = "#facc15"

        xs = [
            mdates.date2num(candle.open_time)
            for candle in candles
        ]

        opens = [
            self._to_float(candle.open)
            for candle in candles
        ]

        closes = [
            self._to_float(candle.close)
            for candle in candles
        ]

        highs = [
            self._to_float(candle.high)
            for candle in candles
        ]

        lows = [
            self._to_float(candle.low)
            for candle in candles
        ]

        candle_width = (
            (xs[1] - xs[0]) * 0.65
            if len(xs) > 1
            else 0.004
        )

        fig, ax = plt.subplots(
            figsize=(14, 8),
            dpi=self.dpi,
        )

        fig.patch.set_facecolor(background)
        ax.set_facecolor(background)

        # ------------------------------------------------------------
        # CANDLESTICKS
        # ------------------------------------------------------------

        for x, open_price, close_price, high_price, low_price in zip(
            xs,
            opens,
            closes,
            highs,
            lows,
        ):
            is_bullish = close_price >= open_price
            color = bullish if is_bullish else bearish

            ax.vlines(
                x,
                low_price,
                high_price,
                color=color,
                linewidth=1.1,
                alpha=0.95,
                zorder=4,
            )

            lower = min(
                open_price,
                close_price,
            )

            body_height = abs(
                close_price - open_price
            )

            if body_height == 0:
                body_height = max(
                    (high_price - low_price) * 0.02,
                    1e-9,
                )

            ax.add_patch(
                Rectangle(
                    (
                        x - (candle_width / 2),
                        lower,
                    ),
                    candle_width,
                    body_height,
                    facecolor=color,
                    edgecolor=color,
                    linewidth=0.8,
                    zorder=5,
                )
            )

        # ------------------------------------------------------------
        # EMA20
        # ------------------------------------------------------------

        ema_values = self._ema(closes)

        ax.plot(
            xs,
            ema_values,
            color=ema_color,
            linewidth=1.45,
            alpha=0.95,
            label=f"EMA{self.ema_period}",
            zorder=6,
        )

        # ------------------------------------------------------------
        # PRICE ACTION STRUCTURE
        # ------------------------------------------------------------

        swings = self._swing_points(
            highs,
            lows,
        )

        # Focus structure labels around the authoritative
        # Brooks signal bar instead of annotating every recent swing.
        structure_anchor_index = len(candles) - 1

        if (
            chart_evidence is not None
            and chart_evidence.signal_index is not None
        ):
            evidence_signal_index = (
                chart_evidence.signal_index
                - (
                    len(snapshot.candles)
                    - len(candles)
                )
            )

            if 0 <= evidence_signal_index < len(candles):
                structure_anchor_index = evidence_signal_index

        structure_candidates = [
            swing
            for swing in swings
            if abs(
                int(swing["index"])
                - structure_anchor_index
            ) <= 36
        ]

        if not structure_candidates:
            structure_candidates = swings

        visible_swings = sorted(
            sorted(
                structure_candidates,
                key=lambda swing: abs(
                    int(swing["index"])
                    - structure_anchor_index
                ),
            )[:6],
            key=lambda swing: int(
                swing["index"]
            ),
        )

        for swing in visible_swings:
            index = int(swing["index"])
            price = float(swing["price"])
            label = str(swing["label"])
            kind = str(swing["kind"])

            color = (
                structure_high_color
                if kind == "HIGH"
                else structure_low_color
            )

            marker = (
                "v"
                if kind == "HIGH"
                else "^"
            )

            ax.scatter(
                xs[index],
                price,
                marker=marker,
                s=38,
                color=color,
                zorder=8,
            )

            offset = (
                9
                if kind == "HIGH"
                else -13
            )

            ax.annotate(
                label,
                xy=(
                    xs[index],
                    price,
                ),
                xytext=(
                    0,
                    offset,
                ),
                textcoords="offset points",
                ha="center",
                va=(
                    "bottom"
                    if kind == "HIGH"
                    else "top"
                ),
                fontsize=7.5,
                fontweight="bold",
                color=color,
                zorder=9,
            )

        current_price = closes[-1]

        support, resistance = self._select_structure_levels(
            swings,
            current_price,
        )

        atr = self._atr(
            highs,
            lows,
            closes,
        )

        total_span = max(highs) - min(lows)

        zone_half_width = max(
            atr * 0.22,
            total_span * 0.003,
        )

        # ------------------------------------------------------------
        # SUPPORT ZONE
        # ------------------------------------------------------------

        if support is not None:
            support_low = support - zone_half_width
            support_high = support + zone_half_width

            ax.axhspan(
                support_low,
                support_high,
                color=support_color,
                alpha=0.075,
                zorder=1,
            )

            ax.axhline(
                support,
                color=support_color,
                linewidth=0.9,
                linestyle="--",
                alpha=0.75,
                zorder=2,
            )

            ax.annotate(
                f"S  {self._format_price(support)}",
                xy=(xs[-1], support),
                xytext=(-6, 5),
                textcoords="offset points",
                ha="right",
                fontsize=7.5,
                color=support_color,
                fontweight="bold",
                zorder=10,
            )

        # ------------------------------------------------------------
        # RESISTANCE ZONE
        # ------------------------------------------------------------

        if resistance is not None:
            resistance_low = resistance - zone_half_width
            resistance_high = resistance + zone_half_width

            ax.axhspan(
                resistance_low,
                resistance_high,
                color=resistance_color,
                alpha=0.075,
                zorder=1,
            )

            ax.axhline(
                resistance,
                color=resistance_color,
                linewidth=0.9,
                linestyle="--",
                alpha=0.75,
                zorder=2,
            )

            ax.annotate(
                f"R  {self._format_price(resistance)}",
                xy=(xs[-1], resistance),
                xytext=(-6, 5),
                textcoords="offset points",
                ha="right",
                fontsize=7.5,
                color=resistance_color,
                fontweight="bold",
                zorder=10,
            )

        # ------------------------------------------------------------
        # BROOKS CORE EVIDENCE OVERLAY
        # ------------------------------------------------------------

        snapshot_offset = (
            len(snapshot.candles) - len(candles)
        )

        def visible_index(
            full_index: int | None,
        ) -> int | None:
            if full_index is None:
                return None

            local_index = (
                full_index - snapshot_offset
            )

            if 0 <= local_index < len(candles):
                return local_index

            return None

        breakout_level: float | None = None

        if chart_evidence is not None:
            family = chart_evidence.family

            # --------------------------------------------
            # TRUE SIGNAL BAR
            # --------------------------------------------

            signal_index = visible_index(
                chart_evidence.signal_index
            )

            if signal_index is not None:
                signal_y = (
                    lows[signal_index]
                    if direction == "LONG"
                    else highs[signal_index]
                )

                signal_marker = (
                    "^"
                    if direction == "LONG"
                    else "v"
                )

                direction_badge = (
                    "LONG"
                    if direction == "LONG"
                    else "SHORT"
                )

                setup_badge = None

                if family == "BREAKOUT_PULLBACK":
                    setup_badge = "PULLBACK"
                elif family in {
                    "FAILED_BREAKOUT",
                    "FAILED_FAILURE",
                }:
                    setup_badge = "REVERSAL"
                elif family == "MAJOR_TREND_REVERSAL":
                    setup_badge = "MTR"
                elif family == "WEDGE_REVERSAL":
                    setup_badge = "WEDGE"

                signal_label = (
                    f"{direction_badge} • {setup_badge}"
                    if setup_badge
                    else direction_badge
                )

                # B272 SIGNAL BAR HIGHLIGHT
                ax.axvspan(
                    xs[signal_index]
                    - (candle_width * 0.80),
                    xs[signal_index]
                    + (candle_width * 0.80),
                    color=entry_color,
                    alpha=0.055,
                    zorder=1,
                )

                ax.scatter(
                    xs[signal_index],
                    signal_y,
                    marker=signal_marker,
                    s=120,
                    color=entry_color,
                    edgecolors=background,
                    linewidths=0.8,
                    zorder=15,
                )

                ax.annotate(
                    signal_label,
                    xy=(
                        xs[signal_index],
                        signal_y,
                    ),
                    xytext=(
                        0,
                        -32
                        if direction == "LONG"
                        else 32,
                    ),
                    textcoords="offset points",
                    ha="center",
                    fontsize=8.5,
                    fontweight="bold",
                    color=entry_color,
                    bbox={
                        "boxstyle": "round,pad=0.25",
                        "facecolor": panel,
                        "edgecolor": entry_color,
                        "alpha": 0.92,
                    },
                    zorder=16,
                )

            # --------------------------------------------
            # BREAKOUT / BREAKOUT PULLBACK / FAILURE
            # --------------------------------------------

            if (
                chart_evidence.reference_level
                is not None
            ):
                breakout_level = float(
                    chart_evidence.reference_level
                )

                ax.axhline(
                    breakout_level,
                    color=breakout_color,
                    linestyle=(0, (6, 4)),
                    linewidth=1.25,
                    alpha=0.95,
                    zorder=6,
                )

                ax.annotate(
                    "BROOKS LEVEL  "
                    + self._format_price(
                        breakout_level
                    ),
                    xy=(
                        xs[-1],
                        breakout_level,
                    ),
                    xytext=(-6, -13),
                    textcoords="offset points",
                    ha="right",
                    fontsize=7.5,
                    color=breakout_color,
                    fontweight="bold",
                    zorder=16,
                )

            reference_index = visible_index(
                chart_evidence.reference_swing_index
            )

            if reference_index is not None:
                reference_price = (
                    highs[reference_index]
                    if direction == "LONG"
                    else lows[reference_index]
                )

                ax.scatter(
                    xs[reference_index],
                    reference_price,
                    marker="D",
                    s=44,
                    facecolors="none",
                    edgecolors=breakout_color,
                    linewidths=1.4,
                    zorder=14,
                )

                ax.annotate(
                    "REFERENCE SWING",
                    xy=(
                        xs[reference_index],
                        reference_price,
                    ),
                    xytext=(0, 13),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7,
                    color=breakout_color,
                    fontweight="bold",
                    zorder=15,
                )

            breakout_index = visible_index(
                chart_evidence.breakout_index
            )

            if breakout_index is not None:
                breakout_y = (
                    highs[breakout_index]
                    if direction == "LONG"
                    else lows[breakout_index]
                )

                ax.scatter(
                    xs[breakout_index],
                    breakout_y,
                    marker="*",
                    s=115,
                    color=breakout_color,
                    edgecolors=background,
                    linewidths=0.6,
                    zorder=15,
                )

                ax.annotate(
                    "BREAKOUT",
                    xy=(
                        xs[breakout_index],
                        breakout_y,
                    ),
                    xytext=(0, 16),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7.4,
                    color=breakout_color,
                    fontweight="bold",
                    zorder=16,
                )

            # --------------------------------------------
            # TRADING RANGE
            # --------------------------------------------

            if (
                chart_evidence.range_low
                is not None
                and chart_evidence.range_high
                is not None
            ):
                range_low = float(
                    chart_evidence.range_low
                )

                range_high = float(
                    chart_evidence.range_high
                )

                if range_high > range_low:
                    ax.axhspan(
                        range_low,
                        range_high,
                        color=muted,
                        alpha=0.035,
                        zorder=0,
                    )

                    ax.axhline(
                        range_low,
                        color=support_color,
                        linestyle="--",
                        linewidth=1.1,
                        alpha=0.9,
                        zorder=5,
                    )

                    ax.axhline(
                        range_high,
                        color=resistance_color,
                        linestyle="--",
                        linewidth=1.1,
                        alpha=0.9,
                        zorder=5,
                    )

                    ax.annotate(
                        "RANGE LOW  "
                        + self._format_price(
                            range_low
                        ),
                        xy=(
                            xs[-1],
                            range_low,
                        ),
                        xytext=(-6, 5),
                        textcoords="offset points",
                        ha="right",
                        fontsize=7.3,
                        color=support_color,
                        fontweight="bold",
                        zorder=15,
                    )

                    ax.annotate(
                        "RANGE HIGH  "
                        + self._format_price(
                            range_high
                        ),
                        xy=(
                            xs[-1],
                            range_high,
                        ),
                        xytext=(-6, 5),
                        textcoords="offset points",
                        ha="right",
                        fontsize=7.3,
                        color=resistance_color,
                        fontweight="bold",
                        zorder=15,
                    )

            # --------------------------------------------
            # DOUBLE TOP
            # --------------------------------------------

            if (
                chart_evidence.first_high
                is not None
                and chart_evidence.second_high
                is not None
            ):
                first_high = float(
                    chart_evidence.first_high
                )

                second_high = float(
                    chart_evidence.second_high
                )

                low_zone = min(
                    first_high,
                    second_high,
                )

                high_zone = max(
                    first_high,
                    second_high,
                )

                ax.axhspan(
                    low_zone,
                    high_zone,
                    color=resistance_color,
                    alpha=0.12,
                    zorder=2,
                )

                ax.axhline(
                    (first_high + second_high) / 2,
                    color=resistance_color,
                    linewidth=1.0,
                    linestyle="--",
                    zorder=5,
                )

                ax.annotate(
                    "DOUBLE TOP AREA",
                    xy=(
                        xs[-1],
                        (
                            first_high
                            + second_high
                        ) / 2,
                    ),
                    xytext=(-6, 6),
                    textcoords="offset points",
                    ha="right",
                    fontsize=7.4,
                    color=resistance_color,
                    fontweight="bold",
                    zorder=15,
                )

            # --------------------------------------------
            # DOUBLE BOTTOM
            # --------------------------------------------

            if (
                chart_evidence.first_low
                is not None
                and chart_evidence.second_low
                is not None
            ):
                first_low = float(
                    chart_evidence.first_low
                )

                second_low = float(
                    chart_evidence.second_low
                )

                low_zone = min(
                    first_low,
                    second_low,
                )

                high_zone = max(
                    first_low,
                    second_low,
                )

                ax.axhspan(
                    low_zone,
                    high_zone,
                    color=support_color,
                    alpha=0.12,
                    zorder=2,
                )

                ax.axhline(
                    (first_low + second_low) / 2,
                    color=support_color,
                    linewidth=1.0,
                    linestyle="--",
                    zorder=5,
                )

                ax.annotate(
                    "DOUBLE BOTTOM AREA",
                    xy=(
                        xs[-1],
                        (
                            first_low
                            + second_low
                        ) / 2,
                    ),
                    xytext=(-6, 6),
                    textcoords="offset points",
                    ha="right",
                    fontsize=7.4,
                    color=support_color,
                    fontweight="bold",
                    zorder=15,
                )

            # --------------------------------------------
            # WEDGE — TRUE PUSH INDICES
            # --------------------------------------------

            for push_number, full_index in enumerate(
                chart_evidence.push_indices,
                start=1,
            ):
                push_index = visible_index(
                    full_index
                )

                if push_index is None:
                    continue

                push_y = (
                    lows[push_index]
                    if direction == "LONG"
                    else highs[push_index]
                )

                ax.scatter(
                    xs[push_index],
                    push_y,
                    marker="o",
                    s=58,
                    facecolors="none",
                    edgecolors=pullback_color,
                    linewidths=1.6,
                    zorder=14,
                )

                ax.annotate(
                    f"P{push_number}",
                    xy=(
                        xs[push_index],
                        push_y,
                    ),
                    xytext=(0, 13),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7.5,
                    color=pullback_color,
                    fontweight="bold",
                    zorder=15,
                )

            # --------------------------------------------
            # MAJOR TREND REVERSAL
            # --------------------------------------------

            structure_break_index = visible_index(
                chart_evidence.structure_break_index
            )

            if structure_break_index is not None:
                structure_break_y = closes[
                    structure_break_index
                ]

                ax.scatter(
                    xs[structure_break_index],
                    structure_break_y,
                    marker="X",
                    s=78,
                    color=breakout_color,
                    edgecolors=background,
                    linewidths=0.8,
                    zorder=15,
                )

                ax.annotate(
                    "STRUCTURE BREAK",
                    xy=(
                        xs[structure_break_index],
                        structure_break_y,
                    ),
                    xytext=(0, 16),
                    textcoords="offset points",
                    ha="center",
                    fontsize=7.4,
                    color=breakout_color,
                    fontweight="bold",
                    zorder=16,
                )

            if (
                chart_evidence.old_extreme
                is not None
            ):
                old_extreme = float(
                    chart_evidence.old_extreme
                )

                ax.axhline(
                    old_extreme,
                    color=pullback_color,
                    linestyle=(0, (3, 3)),
                    linewidth=1.1,
                    alpha=0.9,
                    zorder=5,
                )

                ax.annotate(
                    "OLD EXTREME  "
                    + self._format_price(
                        old_extreme
                    ),
                    xy=(
                        xs[-1],
                        old_extreme,
                    ),
                    xytext=(-6, 5),
                    textcoords="offset points",
                    ha="right",
                    fontsize=7.3,
                    color=pullback_color,
                    fontweight="bold",
                    zorder=15,
                )

        # ------------------------------------------------------------
        # ENTRY / STOP / TARGETS
        # ------------------------------------------------------------

        entry_value = self._to_float(
            entry_price
        )

        stop_value = self._to_float(
            stop_loss
        )

        target_values = [
            self._to_float(target)
            for target in targets
        ]

        ax.axhline(
            entry_value,
            color=entry_color,
            linestyle="--",
            linewidth=1.35,
            alpha=0.95,
            label=f"ENTRY {self._format_price(entry_price)}",
            zorder=7,
        )

        ax.axhline(
            stop_value,
            color=stop_color,
            linestyle=":",
            linewidth=1.35,
            alpha=0.95,
            label=f"SL {self._format_price(stop_loss)}",
            zorder=7,
        )

        for target_index, target in enumerate(
            target_values,
            start=1,
        ):
            ax.axhline(
                target,
                color=target_color,
                linestyle="-.",
                linewidth=1.1,
                alpha=0.9,
                label=(
                    f"TP{target_index} "
                    f"{self._format_price(target)}"
                ),
                zorder=7,
            )

        # ------------------------------------------------------------
        # RISK / REWARD AREA
        # ------------------------------------------------------------

        reward_anchor = (
            max(target_values)
            if direction == "LONG"
            else min(target_values)
        )

        risk_low, risk_high = sorted(
            [
                entry_value,
                stop_value,
            ]
        )

        reward_low, reward_high = sorted(
            [
                entry_value,
                reward_anchor,
            ]
        )

        x_fill = [
            xs[0],
            xs[-1],
        ]

        if risk_low != risk_high:
            ax.fill_between(
                x_fill,
                risk_low,
                risk_high,
                color=stop_color,
                alpha=0.055,
                zorder=0,
            )

        if reward_low != reward_high:
            ax.fill_between(
                x_fill,
                reward_low,
                reward_high,
                color=target_color,
                alpha=0.045,
                zorder=0,
            )

        # ------------------------------------------------------------
        # SETUP MARKER
        # ------------------------------------------------------------

        if setup_type and chart_evidence is None:
            ax.annotate(
                setup_type,
                xy=(
                    xs[-1],
                    closes[-1],
                ),
                xytext=(-8, 22),
                textcoords="offset points",
                ha="right",
                fontsize=8,
                fontweight="bold",
                color=text,
                bbox={
                    "boxstyle": "round,pad=0.3",
                    "facecolor": panel,
                    "edgecolor": grid,
                    "alpha": 0.92,
                },
                zorder=12,
            )

        # ------------------------------------------------------------
        # TITLE
        # ------------------------------------------------------------

        direction_icon = (
            "LONG"
            if direction == "LONG"
            else "SHORT"
        )

        title = (
            f"{snapshot.symbol}  ·  "
            f"{snapshot.timeframe}  ·  "
            f"{direction_icon}"
        )

        ax.set_title(
            title,
            color=text,
            fontsize=14,
            fontweight="bold",
            pad=14,
        )

        ax.set_ylabel(
            "Price",
            color=text,
        )

        # ------------------------------------------------------------
        # INFORMATION PANEL
        # ------------------------------------------------------------

        risk_distance = abs(
            entry_value - stop_value
        )

        reward_distance = abs(
            reward_anchor - entry_value
        )

        rr_ratio = (
            reward_distance / risk_distance
            if risk_distance > 0
            else None
        )

        latest_structure = [
            str(item["label"])
            for item in swings[-4:]
        ]

        info_lines = [
            f"Symbol: {snapshot.symbol}",
            f"TF: {snapshot.timeframe}",
            f"Direction: {direction}",
        ]

        if setup_type:
            info_lines.append(
                f"Setup: {setup_type}"
            )

        if chart_evidence is not None:
            if chart_evidence.family:
                info_lines.append(
                    f"Brooks: {chart_evidence.family}"
                )

            if chart_evidence.context:
                info_lines.append(
                    f"Context: {chart_evidence.context}"
                )

        info_lines.extend(
            [
                "",
                f"Entry: {self._format_price(entry_price)}",
                f"SL: {self._format_price(stop_loss)}",
            ]
        )

        for target_index, target in enumerate(
            targets[:3],
            start=1,
        ):
            info_lines.append(
                f"TP{target_index}: "
                f"{self._format_price(target)}"
            )

        info_lines.append("")

        info_lines.append(
            f"EMA{self.ema_period}: "
            f"{self._format_price(ema_values[-1])}"
        )

        if latest_structure:
            info_lines.append(
                "Structure: "
                + " → ".join(latest_structure)
            )

        if rr_ratio is not None:
            info_lines.append(
                f"R:R ≈ 1:{rr_ratio:.2f}"
            )

        ax.text(
            0.014,
            0.985,
            "\n".join(info_lines),
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=8.1,
            color=text,
            bbox={
                "boxstyle": "round,pad=0.5",
                "facecolor": panel,
                "edgecolor": grid,
                "alpha": 0.94,
            },
            zorder=20,
        )

        # ------------------------------------------------------------
        # AXES
        # ------------------------------------------------------------

        ax.tick_params(
            axis="x",
            colors=muted,
        )

        ax.tick_params(
            axis="y",
            colors=muted,
        )

        for spine in ax.spines.values():
            spine.set_color(grid)

        ax.grid(
            True,
            color=grid,
            alpha=0.20,
            linestyle="--",
            linewidth=0.65,
        )

        ax.xaxis.set_major_formatter(
            mdates.DateFormatter(
                "%m-%d\n%H:%M"
            )
        )

        fig.autofmt_xdate()

        all_prices = (
            highs
            + lows
            + [entry_value, stop_value]
            + target_values
        )

        if support is not None:
            all_prices.append(support)

        if resistance is not None:
            all_prices.append(resistance)

        if breakout_level is not None:
            all_prices.append(breakout_level)

        chart_high = max(all_prices)
        chart_low = min(all_prices)

        padding = self._price_padding(
            chart_high,
            chart_low,
        )

        ax.set_ylim(
            chart_low - padding,
            chart_high + padding,
        )

        # Small right-side margin for labels.
        ax.set_xlim(
            xs[0] - candle_width,
            xs[-1] + (candle_width * 7),
        )

        # ------------------------------------------------------------
        # LEGEND
        # ------------------------------------------------------------

        legend = ax.legend(
            loc="upper right",
            fontsize=7.5,
            frameon=True,
        )

        legend.get_frame().set_facecolor(
            panel
        )

        legend.get_frame().set_edgecolor(
            grid
        )

        legend.get_frame().set_alpha(
            0.94
        )

        for legend_text in legend.get_texts():
            legend_text.set_color(text)

        # ------------------------------------------------------------
        # TELEGRAM BOT FOOTER
        # ------------------------------------------------------------
        # B272 TELEGRAM BOT FOOTER
        # Drawn on the figure canvas, outside the chart axes,
        # so it never overlaps candles or Brooks evidence.
        fig.text(
            0.5,
            0.012,
            "✈  @PriceActionfreebot",
            ha="center",
            va="bottom",
            fontsize=8.5,
            fontweight="bold",
            color=muted,
        )

        # Reserve a small footer strip outside the axes.
        fig.tight_layout(
            rect=(0.0, 0.035, 1.0, 1.0)
        )

        fig.savefig(
            output_path,
            facecolor=fig.get_facecolor(),
            edgecolor="none",
        )

        plt.close(fig)

        if (
            not output_path.is_file()
            or output_path.stat().st_size == 0
        ):
            raise RuntimeError(
                "chart renderer did not produce output"
            )

        return output_path
