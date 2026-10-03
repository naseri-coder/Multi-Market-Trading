"""Deterministic 300-scenario OHLCV validation for Brooks V6 management."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.modules.market_data.entities import Candle
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.trade_management import (
    build_trade_management_plan,
    weighted_close_return,
)

SEED = 20260912
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def make_candles(rng: random.Random, mode: str) -> tuple[Candle, ...]:
    price = Decimal("100")
    result = []
    for index in range(80):
        drift = 0.10 if mode == "BULL" else (-0.10 if mode == "BEAR" else 0.0)
        change = Decimal(str(drift + rng.gauss(0, 0.24)))
        opened = price
        close = max(Decimal("1"), opened + change)
        wick = Decimal(str(abs(rng.gauss(0.16, 0.07))))
        high = max(opened, close) + wick
        low = min(opened, close) - wick
        at = BASE + timedelta(minutes=index)
        result.append(
            Candle(
                at,
                at + timedelta(minutes=1),
                opened,
                high,
                low,
                close,
                Decimal(str(rng.uniform(1, 100))),
            )
        )
        price = close
    return tuple(result)


def run() -> dict[str, object]:
    rng = random.Random(SEED)
    lifecycle = LiveSignalLifecycleService(
        database=object(),
        provider=object(),
        bot=object(),
        vip_channel_id=1,
        cutover_at=BASE,
        candle_limit=100,
    )
    counts = {
        "scenarios": 0,
        "exceptions": 0,
        "trend_t1_scale_out": 0,
        "trend_t2_scale_out": 0,
        "range_full_plan": 0,
        "transition_runner": 0,
        "structural_trail": 0,
        "entry_retest_resumption": 0,
    }

    for scenario in range(300):
        mode = ("BULL", "BEAR", "RANGE", "NOISE")[scenario // 75]
        direction = "SHORT" if mode == "BEAR" else "LONG"
        regime = {
            "BULL": "BULL_TREND",
            "BEAR": "BEAR_TREND",
            "RANGE": "TRADING_RANGE",
            "NOISE": "TRANSITION",
        }[mode]
        entry = Decimal("100")
        stop = Decimal("102") if direction == "SHORT" else Decimal("98")
        sign = Decimal("-1") if direction == "SHORT" else Decimal("1")
        targets = (
            SimpleNamespace(
                target_number=1,
                target_price=entry + sign * Decimal("2"),
                status="HIT",
            ),
            SimpleNamespace(
                target_number=2,
                target_price=entry + sign * Decimal("4"),
                status="HIT",
            ),
        )
        try:
            plan = build_trade_management_plan(
                direction=direction,
                entry_price=entry,
                initial_stop_loss=stop,
                targets=targets,
                market_regime=regime,
                context_metadata={"channel_quality": "TIGHT" if scenario % 4 == 0 else "BROAD"},
            )
            if regime in {"BULL_TREND", "BEAR_TREND"}:
                counts["trend_t1_scale_out"] += int(plan.fraction_for_target(1) > 0)
                counts["trend_t2_scale_out"] += int(plan.fraction_for_target(2) > 0)
            elif regime == "TRADING_RANGE":
                counts["range_full_plan"] += int(plan.runner_fraction == 0)
            else:
                counts["transition_runner"] += int(plan.runner_fraction > 0)

            candles = make_candles(rng, mode)
            signal = SimpleNamespace(
                symbol="BTCUSDT",
                direction=direction,
                entry_price=entry,
                stop_loss=stop,
            )
            structural = lifecycle._structural_trailing_stop(
                signal=signal,
                candles=candles,
                candle=candles[-1],
                entry_activated_at=candles[0].close_time,
            )
            counts["structural_trail"] += int(structural is not None)
            counts["entry_retest_resumption"] += int(
                lifecycle._entry_tested_then_resumed(
                    signal=signal,
                    plan=plan,
                    candles=candles,
                    candle=candles[-1],
                    entry_activated_at=candles[0].close_time,
                )
            )
            value = weighted_close_return(
                plan=plan,
                targets=targets,
                target_returns={1: Decimal("1"), 2: Decimal("2")},
                terminal_return=Decimal("0.25"),
            )
            assert value.is_finite()
            assert Decimal("0") <= plan.realized_fraction(targets) <= Decimal("1")
            assert Decimal("0") <= plan.remaining_fraction(targets) <= Decimal("1")
            counts["scenarios"] += 1
        except Exception:
            counts["exceptions"] += 1

    counts["structural_trail_rate_pct"] = round(
        100 * counts["structural_trail"] / counts["scenarios"], 2
    )
    counts["entry_retest_resumption_rate_pct"] = round(
        100 * counts["entry_retest_resumption"] / counts["scenarios"], 2
    )
    return {"seed": SEED, **counts}


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["exceptions"]:
        raise SystemExit(1)
