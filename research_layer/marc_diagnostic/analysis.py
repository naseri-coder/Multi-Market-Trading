"""Causal-context and post-entry diagnostics for frozen MARC R1 trades."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_backtest.entities import BacktestTrade, BacktestWindowResult
from research_layer.statistics import profit_factor

D = Decimal


@dataclass(frozen=True, slots=True)
class MARCTradeDiagnostic:
    source_signal_id: str
    symbol: str
    timeframe: str
    direction: str
    entry_time: datetime
    gross_r: float
    base_net_r: float
    stress_net_r: float
    tp1_hit: bool
    tp2_hit: bool
    terminal_reason: str
    cross_age_bars: int | None
    confirmation_extension_atr: float | None
    entry_extension_atr: float | None
    initial_risk_atr: float | None
    initial_risk_pct: float
    ma99_slope_5_atr_per_bar: float | None
    ma99_slope_directionally_aligned: bool | None
    full_ma_alignment: bool | None
    ma7_25_directional_gap_atr: float | None
    ma25_99_directional_gap_atr: float | None
    htf_state: str
    htf_directional_alignment: str
    first_ma99_touch_bars: int | None
    first_retest_rejection_bars: int | None
    first_ma99_loss_bars: int | None
    first_opposite_band_failure_bars: int | None
    ma99_touch_within_4: bool
    ma99_touch_within_8: bool
    retest_rejection_within_4: bool
    retest_rejection_within_8: bool
    ma99_loss_within_3: bool
    ma99_loss_within_5: bool
    opposite_band_failure_within_3: bool
    opposite_band_failure_within_5: bool
    cost_drag_r: float



def resample_30m_to_1h(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    """Aggregate only complete UTC-aligned adjacent 30m pairs into 1h candles."""
    source = tuple(candles)
    out: list[Candle] = []
    index = 0
    while index + 1 < len(source):
        first = source[index]
        if first.open_time.minute != 0 or first.open_time.second != 0:
            index += 1
            continue
        second = source[index + 1]
        if second.open_time - first.open_time != timedelta(minutes=30):
            index += 1
            continue
        out.append(
            Candle(
                open_time=first.open_time,
                close_time=second.close_time,
                open=first.open,
                high=max(first.high, second.high),
                low=min(first.low, second.low),
                close=second.close,
                volume=first.volume + second.volume,
            )
        )
        index += 2
    return tuple(out)

def _direction_sign(direction: str) -> D:
    if direction == "LONG":
        return D("1")
    if direction == "SHORT":
        return D("-1")
    raise ValueError("direction must be LONG or SHORT")


def _cross_direction(previous, current) -> str | None:
    if (
        previous.ma7 is None
        or previous.ma25 is None
        or current.ma7 is None
        or current.ma25 is None
    ):
        return None
    if previous.ma7 <= previous.ma25 and current.ma7 > current.ma25:
        return "LONG"
    if previous.ma7 >= previous.ma25 and current.ma7 < current.ma25:
        return "SHORT"
    return None


def _split_contiguous(
    candles: tuple[Candle, ...],
    *,
    timeframe: str,
) -> tuple[tuple[Candle, ...], ...]:
    minutes = {"15m": 15, "30m": 30, "1h": 60}.get(timeframe)
    if minutes is None:
        raise ValueError("unsupported diagnostic timeframe")
    if not candles:
        return ()
    expected = timedelta(minutes=minutes)
    segments: list[list[Candle]] = [[candles[0]]]
    for candle in candles[1:]:
        if candle.open_time - segments[-1][-1].open_time == expected:
            segments[-1].append(candle)
        else:
            segments.append([candle])
    return tuple(tuple(segment) for segment in segments)


def _segment_frames(
    candles: tuple[Candle, ...],
    *,
    timeframe: str,
    policy: MARCPolicy,
) -> tuple[tuple[tuple[Candle, ...], tuple], ...]:
    output = []
    for segment in _split_contiguous(candles, timeframe=timeframe):
        if len(segment) < policy.minimum_indicator_bars:
            continue
        snapshot = MarketSnapshot(
            exchange="binance",
            market_type="futures",
            symbol="DIAGNOSTIC",
            timeframe=timeframe,
            candles=segment,
            captured_at=segment[-1].close_time,
            source="MARC_R2_DIAGNOSTIC",
        )
        output.append((segment, build_indicator_frames(snapshot, policy=policy)))
    return tuple(output)


def _frame_context_for_entry(
    segmented: tuple[tuple[tuple[Candle, ...], tuple], ...],
    *,
    entry_time: datetime,
):
    for candles, frames in segmented:
        opens = [candle.open_time for candle in candles]
        index = bisect_right(opens, entry_time) - 1
        if index < 0 or index >= len(candles):
            continue
        if candles[index].open_time != entry_time:
            continue
        if index == 0:
            return None
        return candles, frames, index
    return None


def _latest_cross_age(frames, confirmation_index: int, direction: str) -> int | None:
    for index in range(confirmation_index, 0, -1):
        if _cross_direction(frames[index - 1], frames[index]) == direction:
            return confirmation_index - index
    return None


def _full_alignment(frame, direction: str) -> bool | None:
    if frame.ma7 is None or frame.ma25 is None or frame.ma99 is None:
        return None
    if direction == "LONG":
        return frame.ma7 > frame.ma25 > frame.ma99
    return frame.ma7 < frame.ma25 < frame.ma99


def _htf_state(
    *,
    frames,
    candles,
    signal_close_time: datetime,
    direction: str,
) -> tuple[str, str]:
    close_times = [candle.close_time for candle in candles]
    index = bisect_right(close_times, signal_close_time) - 1
    if index < 0:
        return "UNAVAILABLE", "UNAVAILABLE"
    frame = frames[index]
    if frame.ma7 is None or frame.ma25 is None or frame.ma99 is None:
        return "UNAVAILABLE", "UNAVAILABLE"
    if frame.close > frame.ma99 and frame.ma7 > frame.ma25:
        state = "BULL"
    elif frame.close < frame.ma99 and frame.ma7 < frame.ma25:
        state = "BEAR"
    else:
        state = "MIXED"
    if state == "MIXED":
        alignment = "MIXED"
    elif (direction == "LONG" and state == "BULL") or (
        direction == "SHORT" and state == "BEAR"
    ):
        alignment = "ALIGNED"
    else:
        alignment = "OPPOSED"
    return state, alignment


def _forward_events(
    *,
    candles,
    frames,
    entry_index: int,
    direction: str,
    policy: MARCPolicy,
    horizon: int = 8,
) -> dict[str, int | None]:
    first_touch = None
    first_rejection = None
    first_loss = None
    first_opposite = None
    end = min(len(candles), entry_index + horizon)
    for index in range(entry_index, end):
        frame = frames[index]
        if frame.ma99 is None or frame.atr14 is None:
            continue
        band = policy.ma99_band_atr * frame.atr14
        if direction == "LONG":
            touch = frame.low <= frame.ma99
            rejection = frame.low <= frame.ma99 + band and frame.close > frame.ma99 + band
            loss = frame.close < frame.ma99
            opposite = frame.close < frame.ma99 - band
        else:
            touch = frame.high >= frame.ma99
            rejection = frame.high >= frame.ma99 - band and frame.close < frame.ma99 - band
            loss = frame.close > frame.ma99
            opposite = frame.close > frame.ma99 + band
        bars = index - entry_index + 1
        if first_touch is None and touch:
            first_touch = bars
        if first_rejection is None and rejection:
            first_rejection = bars
        if first_loss is None and loss:
            first_loss = bars
        if first_opposite is None and opposite:
            first_opposite = bars
    return {
        "touch": first_touch,
        "rejection": first_rejection,
        "loss": first_loss,
        "opposite": first_opposite,
    }


def diagnose_trades(
    *,
    result: BacktestWindowResult,
    candles: tuple[Candle, ...],
    higher_timeframe_candles: tuple[Candle, ...] | None = None,
    policy: MARCPolicy | None = None,
) -> tuple[MARCTradeDiagnostic, ...]:
    selected = policy or MARCPolicy()
    segmented = _segment_frames(candles, timeframe=result.timeframe, policy=selected)
    htf_segmented = ()
    htf_timeframe = None
    if higher_timeframe_candles:
        htf_timeframe = "30m" if result.timeframe == "15m" else "1h"
        htf_segmented = _segment_frames(
            higher_timeframe_candles,
            timeframe=htf_timeframe,
            policy=selected,
        )

    diagnostics = []
    for trade in result.trades:
        found = _frame_context_for_entry(segmented, entry_time=trade.entry_time)
        if found is None:
            raise RuntimeError(f"missing diagnostic candle for {trade.source_signal_id}")
        segment_candles, frames, entry_index = found
        confirmation_index = entry_index - 1
        frame = frames[confirmation_index]
        if frame.ma99 is None or frame.atr14 is None or frame.atr14 <= 0:
            raise RuntimeError(f"missing MARC confirmation indicators for {trade.source_signal_id}")

        sign = _direction_sign(trade.direction)
        cross_age = _latest_cross_age(frames, confirmation_index, trade.direction)
        slope = None
        slope_aligned = None
        if confirmation_index >= 5 and frames[confirmation_index - 5].ma99 is not None:
            slope = (
                (frame.ma99 - frames[confirmation_index - 5].ma99)
                / frame.atr14
                / D("5")
            )
            slope_aligned = sign * slope > 0

        ma7_25_gap = None
        ma25_99_gap = None
        if frame.ma7 is not None and frame.ma25 is not None:
            ma7_25_gap = sign * (frame.ma7 - frame.ma25) / frame.atr14
            ma25_99_gap = sign * (frame.ma25 - frame.ma99) / frame.atr14

        entry = D(str(trade.entry_price))
        stop = D(str(trade.stop_loss))
        confirmation_extension = sign * (frame.close - frame.ma99) / frame.atr14
        entry_extension = sign * (entry - frame.ma99) / frame.atr14
        risk_atr = abs(entry - stop) / frame.atr14
        risk_pct = float(abs(entry - stop) / entry)

        htf_state = "UNAVAILABLE"
        htf_alignment = "UNAVAILABLE"
        if htf_segmented:
            signal_close = segment_candles[confirmation_index].close_time
            candidates = []
            for htf_candles, htf_frames in htf_segmented:
                if htf_candles[0].close_time > signal_close:
                    continue
                candidates.append((htf_candles, htf_frames))
            if candidates:
                htf_candles, htf_frames = candidates[-1]
                htf_state, htf_alignment = _htf_state(
                    frames=htf_frames,
                    candles=htf_candles,
                    signal_close_time=signal_close,
                    direction=trade.direction,
                )

        events = _forward_events(
            candles=segment_candles,
            frames=frames,
            entry_index=entry_index,
            direction=trade.direction,
            policy=selected,
        )

        diagnostics.append(
            MARCTradeDiagnostic(
                source_signal_id=trade.source_signal_id,
                symbol=trade.symbol,
                timeframe=trade.timeframe,
                direction=trade.direction,
                entry_time=trade.entry_time,
                gross_r=trade.gross_r,
                base_net_r=trade.base_net_r,
                stress_net_r=trade.stress_net_r,
                tp1_hit=trade.tp1_hit,
                tp2_hit=trade.tp2_hit,
                terminal_reason=trade.terminal_reason,
                cross_age_bars=cross_age,
                confirmation_extension_atr=float(confirmation_extension),
                entry_extension_atr=float(entry_extension),
                initial_risk_atr=float(risk_atr),
                initial_risk_pct=risk_pct,
                ma99_slope_5_atr_per_bar=None if slope is None else float(slope),
                ma99_slope_directionally_aligned=slope_aligned,
                full_ma_alignment=_full_alignment(frame, trade.direction),
                ma7_25_directional_gap_atr=(
                    None if ma7_25_gap is None else float(ma7_25_gap)
                ),
                ma25_99_directional_gap_atr=(
                    None if ma25_99_gap is None else float(ma25_99_gap)
                ),
                htf_state=htf_state,
                htf_directional_alignment=htf_alignment,
                first_ma99_touch_bars=events["touch"],
                first_retest_rejection_bars=events["rejection"],
                first_ma99_loss_bars=events["loss"],
                first_opposite_band_failure_bars=events["opposite"],
                ma99_touch_within_4=events["touch"] is not None and events["touch"] <= 4,
                ma99_touch_within_8=events["touch"] is not None and events["touch"] <= 8,
                retest_rejection_within_4=(
                    events["rejection"] is not None and events["rejection"] <= 4
                ),
                retest_rejection_within_8=(
                    events["rejection"] is not None and events["rejection"] <= 8
                ),
                ma99_loss_within_3=events["loss"] is not None and events["loss"] <= 3,
                ma99_loss_within_5=events["loss"] is not None and events["loss"] <= 5,
                opposite_band_failure_within_3=(
                    events["opposite"] is not None and events["opposite"] <= 3
                ),
                opposite_band_failure_within_5=(
                    events["opposite"] is not None and events["opposite"] <= 5
                ),
                cost_drag_r=trade.gross_r - trade.base_net_r,
            )
        )
    return tuple(diagnostics)


def _pf(values: list[float]) -> float | None:
    value = profit_factor(values)
    if value == float("inf"):
        return None
    return float(value)


def _summary(records: Iterable[MARCTradeDiagnostic]) -> dict[str, object]:
    items = tuple(records)
    gross = [item.gross_r for item in items]
    base = [item.base_net_r for item in items]
    count = len(items)
    return {
        "trades": count,
        "gross_expectancy_r": None if not count else sum(gross) / count,
        "base_expectancy_r": None if not count else sum(base) / count,
        "base_profit_factor": _pf(base) if count else None,
        "gross_win_rate": (
            None if not count else sum(value > 0 for value in gross) / count
        ),
        "tp1_rate": None if not count else sum(item.tp1_hit for item in items) / count,
        "tp2_rate": None if not count else sum(item.tp2_hit for item in items) / count,
        "average_cost_drag_r": (
            None if not count else sum(item.cost_drag_r for item in items) / count
        ),
    }


def _group(
    records: tuple[MARCTradeDiagnostic, ...],
    key,
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[MARCTradeDiagnostic]] = {}
    for record in records:
        grouped.setdefault(str(key(record)), []).append(record)
    return {name: _summary(items) for name, items in sorted(grouped.items())}


def _extension_bucket(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 0.25:
        return "<=0.25"
    if value <= 0.50:
        return "0.25-0.50"
    if value <= 1.00:
        return "0.50-1.00"
    return ">1.00"


def _risk_bucket(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 0.50:
        return "<=0.50"
    if value <= 1.00:
        return "0.50-1.00"
    if value <= 1.50:
        return "1.00-1.50"
    return ">1.50"


def _cross_age_bucket(value: int | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= 2:
        return "0-2"
    if value <= 5:
        return "3-5"
    return "6+"


def _contrast(
    records: tuple[MARCTradeDiagnostic, ...],
    *,
    attribute: str,
    positive,
    negative,
) -> dict[str, object]:
    yes = tuple(item for item in records if getattr(item, attribute) == positive)
    no = tuple(item for item in records if getattr(item, attribute) == negative)
    yes_summary = _summary(yes)
    no_summary = _summary(no)
    yes_exp = yes_summary["gross_expectancy_r"]
    no_exp = no_summary["gross_expectancy_r"]
    uplift = (
        None
        if yes_exp is None or no_exp is None
        else float(yes_exp) - float(no_exp)
    )
    return {
        "positive": yes_summary,
        "negative": no_summary,
        "gross_expectancy_uplift_r": uplift,
    }


def build_diagnostic_report(
    *,
    validation: tuple[MARCTradeDiagnostic, ...],
    diagnostic_oos: tuple[MARCTradeDiagnostic, ...],
) -> dict[str, object]:
    """Build descriptive evidence only; this report cannot authorize R2 filters."""
    def window(records: tuple[MARCTradeDiagnostic, ...]) -> dict[str, object]:
        return {
            "overall": _summary(records),
            "by_symbol": _group(records, lambda item: item.symbol),
            "by_timeframe": _group(records, lambda item: item.timeframe),
            "by_direction": _group(records, lambda item: item.direction),
            "by_full_ma_alignment": _group(records, lambda item: item.full_ma_alignment),
            "by_ma99_slope_alignment": _group(
                records,
                lambda item: item.ma99_slope_directionally_aligned,
            ),
            "by_htf_alignment": _group(
                records,
                lambda item: item.htf_directional_alignment,
            ),
            "by_cross_age": _group(
                records,
                lambda item: _cross_age_bucket(item.cross_age_bars),
            ),
            "by_confirmation_extension_atr": _group(
                records,
                lambda item: _extension_bucket(item.confirmation_extension_atr),
            ),
            "by_initial_risk_atr": _group(
                records,
                lambda item: _risk_bucket(item.initial_risk_atr),
            ),
            "by_retest_rejection_within_8": _group(
                records,
                lambda item: item.retest_rejection_within_8,
            ),
            "by_ma99_loss_within_3": _group(
                records,
                lambda item: item.ma99_loss_within_3,
            ),
            "by_opposite_band_failure_within_3": _group(
                records,
                lambda item: item.opposite_band_failure_within_3,
            ),
            "contrasts": {
                "full_ma_alignment": _contrast(
                    records,
                    attribute="full_ma_alignment",
                    positive=True,
                    negative=False,
                ),
                "ma99_slope_alignment": _contrast(
                    records,
                    attribute="ma99_slope_directionally_aligned",
                    positive=True,
                    negative=False,
                ),
                "htf_alignment_vs_opposed": _contrast(
                    records,
                    attribute="htf_directional_alignment",
                    positive="ALIGNED",
                    negative="OPPOSED",
                ),
                "retest_rejection_within_8": _contrast(
                    records,
                    attribute="retest_rejection_within_8",
                    positive=True,
                    negative=False,
                ),
                "early_ma99_hold": _contrast(
                    records,
                    attribute="ma99_loss_within_3",
                    positive=False,
                    negative=True,
                ),
                "avoid_early_opposite_band_failure": _contrast(
                    records,
                    attribute="opposite_band_failure_within_3",
                    positive=False,
                    negative=True,
                ),
            },
        }

    return {
        "schema": "MARC_R2_DIAGNOSTIC_V1",
        "baseline": "MARC_R1_V0_1_FROZEN",
        "purpose": "DESCRIPTIVE_ROOT_CAUSE_ANALYSIS_ONLY",
        "validation": window(validation),
        "diagnostic_oos": window(diagnostic_oos),
        "future_r2_approval": "DENIED_DIAGNOSTIC_ONLY",
        "methodology": {
            "ma99_slope": "5-bar SMA99 slope normalized by current ATR14 and by bar",
            "full_ma_alignment": "LONG 7>25>99; SHORT 7<25<99 at confirmation close",
            "htf": "15m->latest closed 30m; 30m->latest closed 1h",
            "retest_rejection": (
                "within 8 post-entry bars, price reaches MA99 band and closes back "
                "outside the 0.10 ATR band in trade direction"
            ),
            "early_failure": "close through MA99 or opposite 0.10 ATR band after entry",
            "warning": (
                "Post-entry event strata are diagnostic and must never be used directly "
                "as causal entry filters without a separately simulated R2 rule."
            ),
        },
    }


def diagnostic_rows(records: Iterable[MARCTradeDiagnostic]) -> list[dict[str, object]]:
    rows = []
    for record in records:
        row = asdict(record)
        row["entry_time"] = record.entry_time.isoformat()
        rows.append(row)
    return rows
