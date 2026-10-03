"""Deterministic V5 robustness run: 300 random OHLCV charts plus scale twins."""

from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
from app.modules.brooks_core.advanced_context import assess_advanced_context
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_patterns import scan_full_brooks_patterns
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import assess_books_context
from app.modules.brooks_core.market_context import build_market_context
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)
REGIMES = ("UP", "DOWN", "RANGE", "NOISE", "MTR_TOP", "MTR_BOTTOM")
SCALE_CHOICES = (Decimal("0.01"), Decimal("1"), Decimal("1000"))


def _path(regime: str, rng: np.random.Generator, bars: int) -> np.ndarray:
    scale = float(rng.lognormal(mean=0.0, sigma=0.65))
    if regime.startswith("MTR_"):
        anchors = (
            (0, 100),
            (10, 106),
            (18, 103),
            (30, 111),
            (42, 107),
            (60, 118),
            (110, 95),
            (119, 116),
            (120, 105),
        )
        values = np.interp(np.arange(bars + 1), *zip(*anchors))
        if regime == "MTR_BOTTOM":
            values = 200 - values
        noise = rng.normal(0, 0.025 * scale, bars + 1)
        noise[[x[0] for x in anchors]] = 0
        return values + noise
    if regime == "UP":
        steps = rng.normal(0.18 * scale, 0.28 * scale, bars)
    elif regime == "DOWN":
        steps = rng.normal(-0.18 * scale, 0.28 * scale, bars)
    elif regime == "RANGE":
        center = 100.0
        values = [center]
        for _ in range(1, bars + 1):
            values.append(values[-1] + 0.24 * (center - values[-1]) + rng.normal(0, 0.34 * scale))
        return np.asarray(values)
    else:
        steps = rng.normal(0, 0.52 * scale, bars)
    return np.r_[100.0, 100.0 + np.cumsum(steps)]


def make_snapshot(regime: str, seed: int, factor: Decimal = Decimal("1")) -> MarketSnapshot:
    rng = np.random.default_rng(seed)
    bars = 120
    path = np.maximum(_path(regime, rng, bars), 10.0)
    candles: list[Candle] = []
    for i in range(bars):
        o = path[i]
        c = path[i + 1]
        recent_steps = np.diff(path[max(0, i - 20) : i + 1])
        observed = float(np.std(recent_steps)) if len(recent_steps) else abs(c - o)
        usual = max(observed, 0.15)
        wick_up = abs(rng.normal(0.20 * usual, 0.12 * usual))
        wick_dn = abs(rng.normal(0.20 * usual, 0.12 * usual))
        if rng.random() < 0.035:
            c += rng.choice((-1, 1)) * rng.uniform(1.5, 3.5) * usual
        vals = [Decimal(str(x)) * factor for x in (o, max(o, c) + wick_up, min(o, c) - wick_dn, c)]
        opened = BASE + timedelta(minutes=15 * i)
        candles.append(
            Candle(
                open_time=opened,
                close_time=opened + timedelta(minutes=15),
                open=vals[0],
                high=vals[1],
                low=vals[2],
                close=vals[3],
                volume=Decimal(str(rng.lognormal(3.0, 0.6))),
            )
        )
    return MarketSnapshot(
        exchange="synthetic",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
        source="V5_SYNTHETIC",
    )


def analyze_snapshot(snapshot: MarketSnapshot, engine: BrooksTrilogyFullCoreEngine) -> dict:
    context = assess_books_context(snapshot, policy=engine.policy.context)
    advanced = assess_advanced_context(snapshot, policy=engine.policy)
    market = build_market_context(snapshot, policy=engine.policy)
    scan = scan_full_brooks_patterns(snapshot, context, engine.policy)
    context_pass = tuple(
        item
        for item in scan.candidates
        if engine._context_contract_status(item, context, market)[0] == "PASS"
    )
    vetoed = tuple(
        item for item in context_pass if engine._barbwire_stop_entry_veto(snapshot, item)
    )
    eligible = tuple(item for item in context_pass if item not in vetoed)
    return {
        "context": context.regime,
        "advanced": advanced.market_phase,
        "raw": tuple(x.setup_type for x in scan.candidates),
        "eligible": tuple(x.setup_type for x in eligible),
        "barbwire_vetoed": tuple(x.setup_type for x in vetoed),
        "rejections": tuple(
            engine._context_contract_status(x, context, market)[1]
            for x in scan.candidates
            if engine._context_contract_status(x, context, market)[0] != "PASS"
        ),
    }


async def main() -> None:
    policy = replace(BrooksFullCorePolicy(), enable_trade_decisions=True)
    engine = BrooksTrilogyFullCoreEngine(policy=policy)
    total = 360
    counts = defaultdict(Counter)
    raw_types: Counter[str] = Counter()
    eligible_types: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    exceptions: list[str] = []
    scale_mismatches = 0
    family_seen = Counter()
    for i in range(total):
        regime = REGIMES[i % len(REGIMES)]
        base = make_snapshot(regime, 912000 + i)
        factor = SCALE_CHOICES[i % len(SCALE_CHOICES)]
        twin = make_snapshot(regime, 912000 + i, factor)
        try:
            analysis = analyze_snapshot(base, engine)
            twin_analysis = analyze_snapshot(twin, engine)
            result = await engine.evaluate(base)
            counts[regime]["charts"] += 1
            counts[regime]["raw_active"] += bool(analysis["raw"])
            counts[regime]["eligible_active"] += bool(analysis["eligible"])
            counts[regime]["barbwire_veto_charts"] += bool(analysis["barbwire_vetoed"])
            counts[regime]["barbwire_veto_candidates"] += len(analysis["barbwire_vetoed"])
            counts[regime]["trade_active"] += result.decision in {"LONG", "SHORT"}
            raw_types.update(analysis["raw"])
            eligible_types.update(analysis["eligible"])
            rejection_reasons.update(analysis["rejections"])
            family_seen.update(x.split("_", 1)[0] for x in analysis["eligible"])
            if (analysis["context"], analysis["raw"], analysis["eligible"]) != (
                twin_analysis["context"],
                twin_analysis["raw"],
                twin_analysis["eligible"],
            ):
                scale_mismatches += 1
        except Exception as exc:
            exceptions.append(f"{i}:{regime}:{type(exc).__name__}:{exc}")

    raw_active = sum(x["raw_active"] for x in counts.values())
    eligible_active = sum(x["eligible_active"] for x in counts.values())
    trade_active = sum(x["trade_active"] for x in counts.values())
    report = {
        "configuration_version": policy.configuration_version,
        "seed_base": 912000,
        "scenarios": total,
        "regimes": {k: dict(v) for k, v in counts.items()},
        "raw_activation": {"count": raw_active, "pct": round(100 * raw_active / total, 2)},
        "eligible_activation": {
            "count": eligible_active,
            "pct": round(100 * eligible_active / total, 2),
        },
        "trade_activation": {"count": trade_active, "pct": round(100 * trade_active / total, 2)},
        "barbwire_veto_candidates": sum(x["barbwire_veto_candidates"] for x in counts.values()),
        "top_raw_setups": raw_types.most_common(12),
        "top_eligible_setups": eligible_types.most_common(12),
        "top_rejection_reasons": rejection_reasons.most_common(12),
        "eligible_family_prefixes": dict(family_seen),
        "scale_twins_checked": total,
        "scale_mismatches": scale_mismatches,
        "exceptions": exceptions,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if exceptions:
        raise SystemExit("exceptions occurred")
    if raw_active == 0 or raw_active >= total:
        raise SystemExit("raw detector is dead or universal")
    if eligible_active == 0 or eligible_active >= int(total * 0.80):
        raise SystemExit("context gate is dead or ineffective")
    if scale_mismatches:
        raise SystemExit("relative logic is not scale invariant")


if __name__ == "__main__":
    asyncio.run(main())
