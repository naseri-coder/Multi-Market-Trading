"""Read-only Brooks research pipeline.

This module writes only under research_output/. Production PostgreSQL is opened
inside READ ONLY transactions and production source files are never modified.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from app.modules.brooks_core_v3.knowledge import BrooksKnowledgeEngine
from app.modules.brooks_core_v3.knowledge.coverage import all_concepts
from app.modules.market_data.entities import TIMEFRAME_SECONDS, MarketSnapshot

from research_layer.statistics import (
    bayesian_win_interval,
    binomial_two_sided_p,
    bootstrap_interval,
    correlation_matrix,
    distribution,
    kaplan_meier,
    max_drawdown,
    monte_carlo_paths,
    out_of_sample_split,
    profit_factor,
    rolling_validation,
    sharpe_ratio,
    walk_forward,
    wilson_interval,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_output"
PATTERN_DB_DIR = OUT / "pattern_databases"
CENTRAL_DB = OUT / "brooks_research.sqlite"
SAMPLE_STEP = 40
WINDOW = 80
FORWARD_HORIZON = 10


def json_default(value):
    if isinstance(value, (datetime, Decimal)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise TypeError(type(value).__name__)


def dumps(value) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            pass
    return json.dumps(value, default=json_default, sort_keys=True)


def parse_json(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def fnum(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def load_raw_extract(path: Path) -> dict[str, list[dict]]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("signals", "evidence", "events", "targets", "deliveries")
    if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in required):
        raise ValueError(
            "raw extract must contain signals/evidence/events/targets/deliveries arrays"
        )
    raw = {key: [dict(row) for row in data[key]] for key in required}
    signal_dt_fields = (
        "created_at",
        "updated_at",
        "closed_at",
        "entry_activated_at",
        "last_processed_candle_close",
    )
    for row in raw["signals"]:
        for key in signal_dt_fields:
            if key in row:
                row[key] = _parse_dt(row[key])
    for row in raw["events"]:
        if "created_at" in row:
            row["created_at"] = _parse_dt(row["created_at"])
    return raw


def load_market_extract(path: Path) -> dict[tuple[str, str, str, str], tuple]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("series") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("market extract must contain a series array")
    result = {}
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get("candles"), list):
            raise ValueError("invalid market series row")
        key = (
            str(item["exchange"]),
            str(item["market_type"]),
            str(item["symbol"]),
            str(item["timeframe"]),
        )
        candles = []
        for raw in item["candles"]:
            candles.append(
                Candle(
                    open_time=_parse_dt(raw["open_time"]),
                    close_time=_parse_dt(raw["close_time"]),
                    open=Decimal(str(raw["open"])),
                    high=Decimal(str(raw["high"])),
                    low=Decimal(str(raw["low"])),
                    close=Decimal(str(raw["close"])),
                    volume=Decimal(str(raw["volume"])),
                )
            )
        result[key] = tuple(candles)
    return result


def configure_output_dir(path: Path) -> None:
    global OUT, PATTERN_DB_DIR, CENTRAL_DB
    path = path.expanduser().resolve()
    if path == ROOT or path.name in {"production_source", "app"}:
        raise ValueError("refusing to write research output into runtime source")
    OUT = path
    PATTERN_DB_DIR = OUT / "pattern_databases"
    CENTRAL_DB = OUT / "brooks_research.sqlite"


def open_research_db() -> sqlite3.Connection:
    OUT.mkdir(exist_ok=True)
    PATTERN_DB_DIR.mkdir(exist_ok=True)
    if CENTRAL_DB.exists():
        CENTRAL_DB.unlink()
    db = sqlite3.connect(CENTRAL_DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript("""
    CREATE TABLE raw_signals(signal_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE raw_evidence(signal_id INTEGER, ordinal INTEGER, rule_id TEXT, status TEXT, payload TEXT NOT NULL);
    CREATE TABLE raw_events(signal_id INTEGER, event_type TEXT, created_at TEXT, payload TEXT NOT NULL);
    CREATE TABLE raw_targets(signal_id INTEGER, target_number INTEGER, status TEXT, payload TEXT NOT NULL);
    CREATE TABLE raw_deliveries(signal_id INTEGER, status TEXT, payload TEXT NOT NULL);
    CREATE TABLE market_candles(exchange TEXT, market_type TEXT, symbol TEXT, timeframe TEXT,
      open_time TEXT, close_time TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
      PRIMARY KEY(exchange,market_type,symbol,timeframe,open_time));
    CREATE TABLE signal_candles(signal_id INTEGER, open_time TEXT, close_time TEXT,
      open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY(signal_id,open_time));
    CREATE TABLE knowledge_findings(signal_id INTEGER, category TEXT, concept TEXT, rule_id TEXT,
      state TEXT, bias TEXT, bar_index INTEGER, probability_band TEXT, evidence TEXT);
    """)
    db.executescript("""
    CREATE TABLE signal_metrics(
      signal_id INTEGER PRIMARY KEY, symbol TEXT, timeframe TEXT, market_type TEXT, setup_type TEXT,
      direction TEXT, status TEXT, created_at TEXT, activated_at TEXT, closed_at TEXT, exit_reason TEXT,
      holding_seconds REAL, activation_wait_seconds REAL, execution_record_delay_seconds REAL,
      entry_price REAL, stop_loss REAL, leverage REAL, risk_price REAL, risk_pct REAL,
      realized_r REAL, mfe_r REAL, mae_r REAL, slippage_price REAL, spread_available INTEGER,
      profit_loss REAL, ai_score REAL, risk_score REAL, quality_score REAL, confidence REAL,
      quality_grade TEXT, recorded_regime TEXT, knowledge_regime TEXT, knowledge_trend TEXT,
      knowledge_range TEXT, knowledge_channel TEXT, evidence_pass INTEGER, evidence_ambiguous INTEGER,
      evidence_fail INTEGER, payload TEXT NOT NULL);
    CREATE TABLE historical_observations(
      exchange TEXT, market_type TEXT, symbol TEXT, timeframe TEXT, snapshot_close TEXT,
      category TEXT, concept TEXT, rule_id TEXT, bias TEXT, probability_band TEXT,
      forward_return REAL, directional_return REAL, mfe_pct REAL, mae_pct REAL,
      proxy_success INTEGER, volatility REAL, compression REAL, payload TEXT NOT NULL);
    CREATE TABLE pattern_stats(pattern TEXT, sample_type TEXT, sample_count INTEGER, wins INTEGER,
      losses INTEGER, win_rate REAL, avg_r REAL, median_r REAL, expectancy REAL, profit_factor REAL,
      sharpe REAL, max_drawdown REAL, avg_duration REAL, median_duration REAL,
      wilson_low REAL, wilson_high REAL, bayes_mean REAL, bayes_low REAL, bayes_high REAL,
      bootstrap_low REAL, bootstrap_high REAL, p_value REAL, payload TEXT);
    CREATE TABLE context_stats(pattern TEXT, context TEXT, sample_count INTEGER, wins INTEGER,
      win_rate REAL, expectancy REAL, bayes_mean REAL, ci_low REAL, ci_high REAL, payload TEXT);
    CREATE TABLE rule_interactions(rule_a TEXT, rule_b TEXT, sample_count INTEGER, win_rate REAL,
      expectancy REAL, synergy REAL, p_value REAL, payload TEXT);
    """)
    return db


def persist_raw(db: sqlite3.Connection, raw: dict[str, list[dict]]) -> None:
    db.executemany(
        "INSERT INTO raw_signals VALUES (?,?)", [(r["id"], dumps(r)) for r in raw["signals"]]
    )
    db.executemany(
        "INSERT INTO raw_evidence VALUES (?,?,?,?,?)",
        [
            (r["signal_id"], r["ordinal"], r["rule_id"], r["status"], dumps(r))
            for r in raw["evidence"]
        ],
    )
    db.executemany(
        "INSERT INTO raw_events VALUES (?,?,?,?)",
        [(r["signal_id"], r["event_type"], str(r["created_at"]), dumps(r)) for r in raw["events"]],
    )
    db.executemany(
        "INSERT INTO raw_targets VALUES (?,?,?,?)",
        [(r["signal_id"], r["target_number"], r["status"], dumps(r)) for r in raw["targets"]],
    )
    db.executemany(
        "INSERT INTO raw_deliveries VALUES (?,?,?)",
        [(r["signal_id"], r["status"], dumps(r)) for r in raw["deliveries"]],
    )
    db.commit()


def candle_tuple(exchange, market_type, symbol, timeframe, c):
    return (
        exchange,
        market_type,
        symbol,
        timeframe,
        c.open_time.isoformat(),
        c.close_time.isoformat(),
        float(c.open),
        float(c.high),
        float(c.low),
        float(c.close),
        float(c.volume),
    )


def index_rows(rows: list[dict], key: str = "signal_id") -> dict[int, list[dict]]:
    out = defaultdict(list)
    for row in rows:
        out[int(row[key])].append(row)
    return out


def decisive_exit(events: list[dict]) -> str | None:
    decisive = [
        e for e in events if e["event_type"] in {"STOP_HIT", "TARGET_HIT", "OUTCOME_AMBIGUOUS"}
    ]
    return decisive[-1]["event_type"] if decisive else None


def entry_event(events: list[dict]) -> dict | None:
    for event in events:
        if event["event_type"] == "ENTRY_ACTIVATED":
            return event
    return None


def event_metadata(event: dict | None) -> dict:
    return parse_json(event.get("metadata") if event else None, {})


def in_window(candles, start: datetime, end: datetime):
    return tuple(c for c in candles if c.close_time >= start and c.open_time <= end)


def snapshot_before(candles, at: datetime, count: int = 120):
    eligible = [c for c in candles if c.close_time <= at]
    return tuple(eligible[-count:])


def directional_excursion(candles, direction: str, entry: float, risk: float):
    if not candles or risk <= 0:
        return None, None
    hi = max(float(c.high) for c in candles)
    lo = min(float(c.low) for c in candles)
    if direction == "LONG":
        return (hi - entry) / risk, (entry - lo) / risk
    return (entry - lo) / risk, (hi - entry) / risk


def reconstruct_signal_metrics(db, raw, series):
    events_by = index_rows(raw["events"])
    evidence_by = index_rows(raw["evidence"])
    engine = BrooksKnowledgeEngine()
    metrics = []
    for row in raw["signals"]:
        sid = int(row["id"])
        key = (row["exchange"], row["market_type"], row["symbol"], row["timeframe"])
        candles = series.get(key, ())
        created = row["created_at"]
        activated = row["entry_activated_at"]
        end = row["closed_at"] or row["last_processed_candle_close"] or datetime.now(UTC)
        pre = snapshot_before(candles, created, 120)
        findings = []
        if len(pre) >= 40:
            snap = MarketSnapshot(
                exchange=row["exchange"],
                market_type=row["market_type"],
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                candles=pre,
                captured_at=pre[-1].close_time,
                source="RESEARCH_RECONSTRUCTION",
            )
            ks = engine.evaluate(snap)
            findings = list(ks.all_findings)
            db.executemany(
                "INSERT INTO knowledge_findings VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        sid,
                        f.category.value,
                        f.concept,
                        f.rule_id,
                        f.state.value,
                        f.bias.value,
                        f.bar_index,
                        f.probability_band.value if f.probability_band else None,
                        dumps(f.evidence),
                    )
                    for f in findings
                ],
            )
        start_store = pre[0].open_time if pre else created
        selected = in_window(candles, start_store, end)
        db.executemany(
            "INSERT OR IGNORE INTO signal_candles VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    sid,
                    c.open_time.isoformat(),
                    c.close_time.isoformat(),
                    float(c.open),
                    float(c.high),
                    float(c.low),
                    float(c.close),
                    float(c.volume),
                )
                for c in selected
            ],
        )
        evs = events_by.get(sid, [])
        ent = entry_event(evs)
        em = event_metadata(ent)
        entry = float(row["entry_price"])
        stop = float(row["stop_loss"])
        lev = float(row["leverage"])
        risk = abs(entry - stop)
        risk_pct = (risk / entry * lev * 100.0) if entry and risk else None
        realized = (
            (float(row["profit_loss"]) / risk_pct)
            if row["profit_loss"] is not None and risk_pct
            else None
        )
        active_candles = in_window(candles, activated, end) if activated else ()
        mfe, mae = directional_excursion(active_candles, row["direction"], entry, risk)
        delay = None
        candle_close = em.get("candle_close")
        if ent and candle_close:
            try:
                delay = (ent["created_at"] - datetime.fromisoformat(candle_close)).total_seconds()
            except Exception:
                delay = None
        activated_price = fnum(em.get("entry_price"))
        slippage = (activated_price - entry) if activated_price is not None else None
        holding = (end - activated).total_seconds() if activated else None
        wait = (activated - created).total_seconds() if activated else None
        evrows = evidence_by.get(sid, [])
        pass_n = sum(1 for e in evrows if e["status"] == "PASS")
        amb_n = sum(1 for e in evrows if e["status"] == "AMBIGUOUS")
        fail_n = sum(1 for e in evrows if e["status"] == "FAIL")
        regime = next(
            (
                f.concept
                for f in findings
                if f.rule_id == "BB-RNG-CTX-TREND-VS-RANGE" and f.category.value == "CONTEXT"
            ),
            None,
        )
        trends = sorted({f.concept for f in findings if f.category.value == "TREND"})
        ranges = sorted({f.concept for f in findings if f.category.value == "RANGE"})
        channels = sorted({f.concept for f in findings if f.category.value == "CHANNEL"})
        payload = {
            "production": row,
            "exit_reason": decisive_exit(evs),
            "reconstruction_semantics": "CURRENT_KNOWLEDGE_ENGINE_READ_ONLY_RECONSTRUCTION",
            "knowledge": {"trend": trends, "range": ranges, "channel": channels},
        }
        metric = {
            "signal_id": sid,
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "market_type": row["market_type"],
            "setup_type": row["setup_type"],
            "direction": row["direction"],
            "status": row["status"],
            "created_at": created,
            "activated_at": activated,
            "closed_at": row["closed_at"],
            "exit_reason": decisive_exit(evs),
            "holding_seconds": holding,
            "activation_wait_seconds": wait,
            "execution_record_delay_seconds": delay,
            "entry_price": entry,
            "stop_loss": stop,
            "leverage": lev,
            "risk_price": risk,
            "risk_pct": risk_pct,
            "realized_r": realized,
            "mfe_r": mfe,
            "mae_r": mae,
            "slippage_price": slippage,
            "spread_available": 0,
            "profit_loss": fnum(row["profit_loss"]),
            "ai_score": fnum(row["ai_score"]),
            "risk_score": fnum(row["risk_score"]),
            "quality_score": fnum(row["final_score"]),
            "confidence": fnum(row["confidence"]),
            "quality_grade": row["quality_grade"],
            "recorded_regime": row["market_regime"],
            "knowledge_regime": regime,
            "knowledge_trend": " | ".join(trends),
            "knowledge_range": " | ".join(ranges),
            "knowledge_channel": " | ".join(channels),
            "evidence_pass": pass_n,
            "evidence_ambiguous": amb_n,
            "evidence_fail": fail_n,
            "payload": dumps(payload),
        }
        metrics.append(metric)
    return metrics


def persist_signal_metrics(db, metrics):
    cols = [
        "signal_id",
        "symbol",
        "timeframe",
        "market_type",
        "setup_type",
        "direction",
        "status",
        "created_at",
        "activated_at",
        "closed_at",
        "exit_reason",
        "holding_seconds",
        "activation_wait_seconds",
        "execution_record_delay_seconds",
        "entry_price",
        "stop_loss",
        "leverage",
        "risk_price",
        "risk_pct",
        "realized_r",
        "mfe_r",
        "mae_r",
        "slippage_price",
        "spread_available",
        "profit_loss",
        "ai_score",
        "risk_score",
        "quality_score",
        "confidence",
        "quality_grade",
        "recorded_regime",
        "knowledge_regime",
        "knowledge_trend",
        "knowledge_range",
        "knowledge_channel",
        "evidence_pass",
        "evidence_ambiguous",
        "evidence_fail",
        "payload",
    ]
    sql = "INSERT INTO signal_metrics VALUES (" + ",".join("?" for _ in cols) + ")"
    rows = []
    for m in metrics:
        row = []
        for c in cols:
            v = m[c]
            if isinstance(v, datetime):
                v = v.isoformat()
            row.append(v)
        rows.append(tuple(row))
    db.executemany(sql, rows)
    db.commit()


def window_features(window):
    closes = np.asarray([float(c.close) for c in window], dtype=float)
    rets = np.diff(np.log(closes)) if len(closes) > 1 else np.asarray([])
    volatility = float(np.std(rets, ddof=1)) if rets.size > 1 else 0.0
    ranges = np.asarray(
        [(float(c.high) - float(c.low)) / max(float(c.close), 1e-12) for c in window], dtype=float
    )
    recent = float(np.median(ranges[-10:])) if ranges.size else 0.0
    base = float(np.median(ranges[-40:])) if ranges.size else 0.0
    compression = (recent / base) if base > 0 else 1.0
    return volatility, compression


def future_observation(future, bias, base_price):
    if not future or bias not in {"BULLISH", "BEARISH"}:
        return None, None, None, None, None
    last = float(future[-1].close)
    raw = (last - base_price) / base_price
    hi = max(float(c.high) for c in future)
    lo = min(float(c.low) for c in future)
    if bias == "BULLISH":
        directional = raw
        mfe = (hi - base_price) / base_price
        mae = (base_price - lo) / base_price
    else:
        directional = -raw
        mfe = (base_price - lo) / base_price
        mae = (hi - base_price) / base_price
    return raw, directional, mfe, mae, int(directional > 0)


def sampled_indices(candles, dense_start=None, dense_end=None):
    max_end = len(candles) - FORWARD_HORIZON
    indices = set(range(WINDOW, max_end, SAMPLE_STEP))
    if dense_start and dense_end:
        for end in range(WINDOW, max_end):
            t = candles[end - 1].close_time
            if dense_start <= t <= dense_end:
                indices.add(end)
    return sorted(indices)


def generate_historical_observations(db, series, raw):
    engine = BrooksKnowledgeEngine()
    prod_keys = {
        (r["exchange"], r["market_type"], r["symbol"], r["timeframe"]) for r in raw["signals"]
    }
    dense_start = min(r["created_at"] for r in raw["signals"]) - timedelta(hours=2)
    dense_end = max(r["created_at"] for r in raw["signals"]) + timedelta(hours=2)
    total_snapshots = 0
    total_rows = 0
    sql = "INSERT INTO historical_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for key, candles in sorted(series.items()):
        exchange, market_type, symbol, timeframe = key
        indices = (
            sampled_indices(candles, dense_start, dense_end)
            if key in prod_keys
            else sampled_indices(candles)
        )
        rows = []
        for end in indices:
            window = tuple(candles[end - WINDOW : end])
            future = tuple(candles[end : end + FORWARD_HORIZON])
            if len(window) < WINDOW or len(future) < FORWARD_HORIZON:
                continue
            snap = MarketSnapshot(
                exchange=exchange,
                market_type=market_type,
                symbol=symbol,
                timeframe=timeframe,
                candles=window,
                captured_at=window[-1].close_time,
                source="BROOKS_RESEARCH_OBSERVATION",
            )
            knowledge = engine.evaluate(snap)
            vol, comp = window_features(window)
            base = float(window[-1].close)
            for finding in knowledge.all_findings:
                raw_ret, directional, mfe, mae, success = future_observation(
                    future, finding.bias.value, base
                )
                payload = {
                    "state": finding.state.value,
                    "evidence": finding.evidence,
                    "semantics": "OBSERVATIONAL_10_BAR_FORWARD_NOT_TRADE_OUTCOME",
                }
                rows.append(
                    (
                        exchange,
                        market_type,
                        symbol,
                        timeframe,
                        window[-1].close_time.isoformat(),
                        finding.category.value,
                        finding.concept,
                        finding.rule_id,
                        finding.bias.value,
                        finding.probability_band.value if finding.probability_band else None,
                        raw_ret,
                        directional,
                        mfe,
                        mae,
                        success,
                        vol,
                        comp,
                        dumps(payload),
                    )
                )
            total_snapshots += 1
        db.executemany(sql, rows)
        db.commit()
        total_rows += len(rows)
        print("OBS_SERIES", *key, "snapshots", len(indices), "findings", len(rows), flush=True)
    print("OBS_TOTAL", total_snapshots, total_rows, flush=True)
    return total_snapshots, total_rows


def performance_summary(name, sample_type, rows):
    usable = [r for r in rows if r.get("realized_r") is not None]
    rvals = [float(r["realized_r"]) for r in usable]
    durations = [r.get("holding_seconds") for r in usable if r.get("holding_seconds") is not None]
    n = len(rvals)
    wins = sum(v > 0 for v in rvals)
    losses = n - wins
    if not n:
        return {"pattern": name, "sample_type": sample_type, "sample_count": 0}
    wil = wilson_interval(wins, n)
    bayes, bci = bayesian_win_interval(wins, losses)
    boot = bootstrap_interval(rvals)
    dist = distribution(rvals)
    return {
        "pattern": name,
        "sample_type": sample_type,
        "sample_count": n,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / n,
        "avg_r": float(np.mean(rvals)),
        "median_r": float(np.median(rvals)),
        "expectancy": float(np.mean(rvals)),
        "profit_factor": profit_factor(rvals),
        "sharpe": sharpe_ratio(rvals),
        "max_drawdown": max_drawdown(rvals),
        "avg_duration": float(np.mean(durations)) if durations else None,
        "median_duration": float(np.median(durations)) if durations else None,
        "wilson_low": wil.low,
        "wilson_high": wil.high,
        "bayes_mean": bayes,
        "bayes_low": bci.low,
        "bayes_high": bci.high,
        "bootstrap_low": boot.low,
        "bootstrap_high": boot.high,
        "p_value": binomial_two_sided_p(wins, n),
        "payload": dumps(
            {
                "distribution": dist,
                "monte_carlo": monte_carlo_paths(rvals),
                "out_of_sample": out_of_sample_split(rvals),
                "walk_forward": walk_forward(rvals),
                "rolling_validation": rolling_validation(rvals),
            }
        ),
    }


def insert_pattern_stats(db, stats):
    cols = [
        "pattern",
        "sample_type",
        "sample_count",
        "wins",
        "losses",
        "win_rate",
        "avg_r",
        "median_r",
        "expectancy",
        "profit_factor",
        "sharpe",
        "max_drawdown",
        "avg_duration",
        "median_duration",
        "wilson_low",
        "wilson_high",
        "bayes_mean",
        "bayes_low",
        "bayes_high",
        "bootstrap_low",
        "bootstrap_high",
        "p_value",
        "payload",
    ]
    sql = "INSERT INTO pattern_stats VALUES (" + ",".join("?" for _ in cols) + ")"
    db.executemany(sql, [tuple(s.get(c) for c in cols) for s in stats])
    db.commit()


def actual_analyses(db, metrics, raw):
    closed = [m for m in metrics if m.get("realized_r") is not None]
    by_pattern = defaultdict(list)
    for m in closed:
        by_pattern[m["setup_type"]].append(m)
    stats = [performance_summary("ALL_ACTUAL_SIGNALS", "ACTUAL", closed)]
    stats += [
        performance_summary(name, "ACTUAL", rows) for name, rows in sorted(by_pattern.items())
    ]
    insert_pattern_stats(db, stats)

    contexts = defaultdict(set)
    for m in closed:
        sid = m["signal_id"]
        for label, val in (
            ("RECORDED_REGIME", m.get("recorded_regime")),
            ("KNOWLEDGE_REGIME", m.get("knowledge_regime")),
            ("MARKET", m.get("symbol")),
            ("TIMEFRAME", m.get("timeframe")),
            ("MARKET_TYPE", m.get("market_type")),
        ):
            if val:
                contexts[sid].add(f"{label}:{val}")
    for sid, cat, concept in db.execute(
        "SELECT signal_id,category,concept FROM knowledge_findings WHERE category IN ('CONTEXT','TREND','RANGE','CHANNEL','PRESSURE','TRAP','FAILURE')"
    ):
        contexts[int(sid)].add(f"{cat}:{concept}")
    grouped = defaultdict(list)
    for m in closed:
        for ctx in contexts[m["signal_id"]]:
            grouped[(m["setup_type"], ctx)].append(m)
    context_rows = []
    for (pattern, ctx), rows in grouped.items():
        r = [float(x["realized_r"]) for x in rows]
        n = len(r)
        wins = sum(x > 0 for x in r)
        bayes, ci = bayesian_win_interval(wins, n - wins)
        context_rows.append(
            (
                pattern,
                ctx,
                n,
                wins,
                wins / n,
                float(np.mean(r)),
                bayes,
                ci.low,
                ci.high,
                dumps({"bootstrap_expectancy": bootstrap_interval(r).__dict__}),
            )
        )
    db.executemany("INSERT INTO context_stats VALUES (?,?,?,?,?,?,?,?,?,?)", context_rows)
    db.commit()
    return stats, contexts


def analyse_rule_interactions(db, metrics, raw):
    metric_by = {m["signal_id"]: m for m in metrics if m.get("realized_r") is not None}
    rules_by = defaultdict(set)
    for e in raw["evidence"]:
        sid = int(e["signal_id"])
        if sid in metric_by and e["status"] == "PASS":
            rules_by[sid].add(e["rule_id"])
    individual = defaultdict(list)
    pairs = defaultdict(list)
    for sid, rules in rules_by.items():
        rv = float(metric_by[sid]["realized_r"])
        ordered = sorted(rules)
        for rule in ordered:
            individual[rule].append(rv)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1 :]:
                pairs[(a, b)].append(rv)
    rows = []
    for (a, b), vals in pairs.items():
        n = len(vals)
        wins = sum(v > 0 for v in vals)
        base = (float(np.mean(individual[a])) + float(np.mean(individual[b]))) / 2.0
        exp = float(np.mean(vals))
        synergy = exp - base
        rows.append(
            (
                a,
                b,
                n,
                wins / n,
                exp,
                synergy,
                binomial_two_sided_p(wins, n),
                dumps(
                    {
                        "rule_a_n": len(individual[a]),
                        "rule_b_n": len(individual[b]),
                        "base_expectancy": base,
                    }
                ),
            )
        )
    db.executemany("INSERT INTO rule_interactions VALUES (?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return rows


def ensure_analysis_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS false_signal_categories(signal_id INTEGER, category TEXT, reason TEXT, realized_r REAL);
    CREATE TABLE IF NOT EXISTS missed_opportunities(exchange TEXT, market_type TEXT, symbol TEXT, timeframe TEXT,
      snapshot_close TEXT, concept TEXT, rule_id TEXT, bias TEXT, directional_return REAL, mfe_pct REAL, mae_pct REAL, payload TEXT);
    CREATE TABLE IF NOT EXISTS recommendations(scope TEXT, subject TEXT, recommendation TEXT, confidence TEXT, rationale TEXT, applied INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS market_timeframe_stats(exchange TEXT, market_type TEXT, symbol TEXT, timeframe TEXT,
      candle_count INTEGER, return_mean REAL, return_std REAL, range_median REAL, volume_median REAL,
      total_return REAL, high_low_span REAL, payload TEXT);
    CREATE TABLE IF NOT EXISTS survival_points(time_seconds REAL, at_risk INTEGER, events INTEGER, censored INTEGER, survival REAL);
    CREATE TABLE IF NOT EXISTS correlations(row_name TEXT, column_name TEXT, value REAL);
    """)
    db.commit()


def analyse_false_signals(db, metrics, raw):
    ensure_analysis_tables(db)
    closed = [m for m in metrics if m.get("realized_r") is not None]
    confidences = [m["confidence"] for m in closed if m.get("confidence") is not None]
    conf_med = float(np.median(confidences)) if confidences else None
    ev_by = index_rows(raw["evidence"])
    findings = defaultdict(list)
    for sid, cat, concept in db.execute(
        "SELECT signal_id,category,concept FROM knowledge_findings"
    ):
        findings[int(sid)].append((cat, concept))
    rows = []
    for m in closed:
        if m["realized_r"] >= 0:
            continue
        sid = m["signal_id"]
        f = findings[sid]
        ev = ev_by.get(sid, [])
        categories = []
        if any(
            any(k in concept.upper() for k in ("FINAL FLAG", "CLIMAX", "EXHAUST"))
            for _, concept in f
        ):
            categories.append(("LATE_TREND", "Late-trend/climactic structure detected"))
        if (
            m["evidence_ambiguous"] >= 2
            or str(m.get("knowledge_regime") or "").upper() == "AMBIGUOUS"
        ):
            categories.append(("WEAK_CONTEXT", "Ambiguous context/evidence at signal snapshot"))
        if "BREAKOUT" in str(m["setup_type"]):
            categories.append(("WRONG_BREAKOUT", "Breakout-family signal ended negative"))
        if any(cat == "RANGE" for cat, _ in f):
            categories.append(("POOR_LOCATION", "Trading-range context present"))
        if any("CHANNEL" in e["rule_id"] and e["status"] != "PASS" for e in ev):
            categories.append(("WEAK_CHANNEL", "Channel evidence not confirmed"))
        if any(e["rule_id"] == "BB-REV-15-ALWAYS-IN" and e["status"] != "PASS" for e in ev) or any(
            "ALWAYS-IN" in c.upper() and cat == "FAILURE" for cat, c in f
        ):
            categories.append(("FAKE_ALWAYS_IN", "Always-In unresolved or failed"))
        if conf_med is not None and m.get("confidence") is not None and m["confidence"] < conf_med:
            categories.append(
                ("LOW_RECORDED_CONFIDENCE", "Recorded confidence below closed-signal median")
            )
        if not categories:
            categories = [("UNCLASSIFIED", "No requested failure taxonomy condition detected")]
        for category, reason in categories:
            rows.append((sid, category, reason, float(m["realized_r"])))
    db.executemany("INSERT INTO false_signal_categories VALUES (?,?,?,?)", rows)
    db.commit()
    return rows


def analyse_missed_opportunities(db, raw):
    start = min(r["created_at"] for r in raw["signals"]) - timedelta(hours=2)
    end = max(r["created_at"] for r in raw["signals"]) + timedelta(hours=2)
    actual = defaultdict(list)
    for r in raw["signals"]:
        actual[(r["exchange"], r["market_type"], r["symbol"], r["timeframe"])].append(r)
    query = """SELECT exchange,market_type,symbol,timeframe,snapshot_close,concept,rule_id,bias,
                    directional_return,mfe_pct,mae_pct,payload
             FROM historical_observations WHERE category='ENTRY' AND directional_return IS NOT NULL"""
    rows = []
    seen = set()
    for r in db.execute(query):
        (
            exchange,
            market_type,
            symbol,
            timeframe,
            close_s,
            concept,
            rule_id,
            bias,
            dr,
            mfe,
            mae,
            payload,
        ) = r
        close = datetime.fromisoformat(close_s)
        if not (start <= close <= end):
            continue
        key = (exchange, market_type, symbol, timeframe)
        tf_seconds = TIMEFRAME_SECONDS[timeframe]
        expected_dir = "LONG" if bias == "BULLISH" else "SHORT" if bias == "BEARISH" else None
        matched = False
        for sig in actual.get(key, []):
            delta = (sig["created_at"] - close).total_seconds()
            if 0 <= delta <= tf_seconds * 1.25 and (
                expected_dir is None or sig["direction"] == expected_dir
            ):
                matched = True
                break
        uniq = (exchange, market_type, symbol, timeframe, close_s, concept, rule_id, bias)
        if not matched and uniq not in seen:
            seen.add(uniq)
            rows.append((*uniq, dr, mfe, mae, payload))
    db.executemany("INSERT INTO missed_opportunities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return rows


def analyse_market_timeframes(db, series):
    ensure_analysis_tables(db)
    rows = []
    for key, candles in sorted(series.items()):
        exchange, market_type, symbol, timeframe = key
        closes = np.asarray([float(c.close) for c in candles], dtype=float)
        volumes = np.asarray([float(c.volume) for c in candles], dtype=float)
        ranges = np.asarray(
            [(float(c.high) - float(c.low)) / max(float(c.close), 1e-12) for c in candles],
            dtype=float,
        )
        rets = np.diff(np.log(closes))
        total = (closes[-1] - closes[0]) / closes[0]
        span = (max(float(c.high) for c in candles) - min(float(c.low) for c in candles)) / closes[
            0
        ]
        payload = {
            "return_distribution": distribution(rets.tolist()),
            "range_distribution": distribution(ranges.tolist()),
            "volume_distribution": distribution(volumes.tolist()),
        }
        rows.append(
            (
                *key,
                len(candles),
                float(np.mean(rets)),
                float(np.std(rets, ddof=1)),
                float(np.median(ranges)),
                float(np.median(volumes)),
                float(total),
                float(span),
                dumps(payload),
            )
        )
    db.executemany("INSERT INTO market_timeframe_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()
    return rows


def analyse_survival_and_correlations(db, metrics):
    ensure_analysis_tables(db)
    durations = [m["holding_seconds"] for m in metrics if m.get("holding_seconds") is not None]
    events = [m["status"] == "CLOSED" for m in metrics if m.get("holding_seconds") is not None]
    surv = kaplan_meier(durations, events)
    db.executemany(
        "INSERT INTO survival_points VALUES (?,?,?,?,?)",
        [(r["time"], r["at_risk"], r["events"], r["censored"], r["survival"]) for r in surv],
    )
    columns = [
        "realized_r",
        "mfe_r",
        "mae_r",
        "ai_score",
        "risk_score",
        "quality_score",
        "confidence",
        "evidence_pass",
        "evidence_ambiguous",
    ]
    names, matrix = correlation_matrix(metrics, columns)
    corr = []
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            value = float(matrix[i, j]) if math.isfinite(float(matrix[i, j])) else None
            corr.append((a, b, value))
    db.executemany("INSERT INTO correlations VALUES (?,?,?)", corr)
    db.commit()
    return surv, names, matrix


def analyse_observational(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS observational_pattern_stats(
      pattern TEXT, sample_count INTEGER, hit_rate REAL, avg_directional_return REAL,
      median_directional_return REAL, avg_mfe_pct REAL, avg_mae_pct REAL,
      bayes_mean REAL, ci_low REAL, ci_high REAL, bootstrap_low REAL, bootstrap_high REAL, payload TEXT);
    CREATE TABLE IF NOT EXISTS observational_context_stats(
      pattern TEXT, context TEXT, sample_count INTEGER, hit_rate REAL,
      avg_directional_return REAL, bayes_mean REAL, ci_low REAL, ci_high REAL, payload TEXT);
    """)
    raw = list(
        db.execute("""SELECT exchange,market_type,symbol,timeframe,snapshot_close,category,concept,rule_id,bias,
        probability_band,directional_return,mfe_pct,mae_pct,volatility,compression
        FROM historical_observations WHERE directional_return IS NOT NULL
        AND category IN ('STRUCTURE','ENTRY','FAILURE','TRAP')""")
    )
    unique = {}
    for row in raw:
        key = (row[0], row[1], row[2], row[3], row[4], row[6], row[8])
        unique.setdefault(key, row)
    records = list(unique.values())
    by = defaultdict(list)
    for r in records:
        by[r[6]].append(r)
    pattern_rows = []
    for pattern, items in sorted(by.items()):
        dr = [float(x[10]) for x in items]
        mfe = [float(x[11]) for x in items if x[11] is not None]
        mae = [float(x[12]) for x in items if x[12] is not None]
        n = len(dr)
        wins = sum(x > 0 for x in dr)
        bayes, ci = bayesian_win_interval(wins, n - wins)
        boot = bootstrap_interval(dr)
        pattern_rows.append(
            (
                pattern,
                n,
                wins / n,
                float(np.mean(dr)),
                float(np.median(dr)),
                float(np.mean(mfe)) if mfe else None,
                float(np.mean(mae)) if mae else None,
                bayes,
                ci.low,
                ci.high,
                boot.low,
                boot.high,
                dumps(
                    {"semantics": "10_BAR_DIRECTIONAL_FORWARD_OBSERVATION_NOT_LIVE_TRADE_WIN_RATE"}
                ),
            )
        )
    db.executemany(
        "INSERT INTO observational_pattern_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", pattern_rows
    )
    series_groups = defaultdict(list)
    for r in records:
        series_groups[(r[0], r[1], r[2], r[3])].append(r)
    thresholds = {}
    for key, items in series_groups.items():
        vols = np.asarray([float(x[13]) for x in items])
        comps = np.asarray([float(x[14]) for x in items])
        thresholds[key] = (np.quantile(vols, [1 / 3, 2 / 3]), np.quantile(comps, [1 / 3, 2 / 3]))
    grouped = defaultdict(list)
    for r in records:
        key = (r[0], r[1], r[2], r[3])
        vq, cq = thresholds[key]
        vol = float(r[13])
        comp = float(r[14])
        vol_label = (
            "LOW_VOLATILITY"
            if vol <= vq[0]
            else "HIGH_VOLATILITY"
            if vol >= vq[1]
            else "MID_VOLATILITY"
        )
        comp_label = (
            "COMPRESSION" if comp <= cq[0] else "EXPANSION" if comp >= cq[1] else "MID_COMPRESSION"
        )
        contexts = [
            f"EXCHANGE:{r[0]}",
            f"MARKET_TYPE:{r[1]}",
            f"SYMBOL:{r[2]}",
            f"TIMEFRAME:{r[3]}",
            f"BIAS:{r[8]}",
            f"VOLATILITY:{vol_label}",
            f"RANGE_STATE:{comp_label}",
        ]
        if r[9]:
            contexts.append(f"PROBABILITY_BAND:{r[9]}")
        for ctx in contexts:
            grouped[(r[6], ctx)].append(float(r[10]))
    context_rows = []
    for (pattern, ctx), vals in grouped.items():
        n = len(vals)
        wins = sum(x > 0 for x in vals)
        bayes, ci = bayesian_win_interval(wins, n - wins)
        boot = bootstrap_interval(vals)
        context_rows.append(
            (
                pattern,
                ctx,
                n,
                wins / n,
                float(np.mean(vals)),
                bayes,
                ci.low,
                ci.high,
                dumps({"bootstrap_directional_return": boot.__dict__}),
            )
        )
    db.executemany(
        "INSERT INTO observational_context_stats VALUES (?,?,?,?,?,?,?,?,?)", context_rows
    )
    db.commit()
    return pattern_rows, context_rows


def generate_recommendations(db):
    recs = []
    for pattern, n, exp, blo, bhi in db.execute(
        "SELECT pattern,sample_count,expectancy,bayes_low,bayes_high FROM pattern_stats WHERE sample_type='ACTUAL' AND pattern!='ALL_ACTUAL_SIGNALS'"
    ):
        if n < 10:
            recs.append(
                (
                    "PATTERN",
                    pattern,
                    "INSUFFICIENT_SAMPLE",
                    "LOW",
                    f"Only {n} actual closed samples; no calibration recommendation is statistically defensible.",
                    0,
                )
            )
        elif exp is not None and exp > 0 and blo is not None and blo > 0.5:
            recs.append(
                (
                    "PATTERN",
                    pattern,
                    "REVIEW_INCREASE_WEIGHT",
                    "HIGH",
                    f"Positive expectancy {exp:.3f}R and Bayesian 95% lower win bound {blo:.3f} > 0.5. Research recommendation only.",
                    0,
                )
            )
        elif exp is not None and exp < 0 and bhi is not None and bhi < 0.5:
            recs.append(
                (
                    "PATTERN",
                    pattern,
                    "REVIEW_DECREASE_WEIGHT",
                    "HIGH",
                    f"Negative expectancy {exp:.3f}R and Bayesian 95% upper win bound {bhi:.3f} < 0.5. Research recommendation only.",
                    0,
                )
            )
        elif exp is not None and exp < 0:
            recs.append(
                (
                    "PATTERN",
                    pattern,
                    "REVIEW_WEAK_PATTERN",
                    "MEDIUM",
                    f"Negative expectancy {exp:.3f}R but uncertainty still crosses neutral; gather more data before calibration.",
                    0,
                )
            )
    for pattern, ctx, n, exp, blo, bhi in db.execute(
        "SELECT pattern,context,sample_count,expectancy,ci_low,ci_high FROM context_stats"
    ):
        if n >= 8 and exp is not None and exp > 0 and blo > 0.5:
            recs.append(
                (
                    "CONTEXT",
                    f"{pattern} | {ctx}",
                    "REVIEW_STRONG_CONTEXT",
                    "MEDIUM",
                    f"n={n}, expectancy={exp:.3f}R, Bayesian lower bound={blo:.3f}.",
                    0,
                )
            )
        elif n >= 8 and exp is not None and exp < 0 and bhi < 0.5:
            recs.append(
                (
                    "CONTEXT",
                    f"{pattern} | {ctx}",
                    "REVIEW_WEAK_CONTEXT",
                    "MEDIUM",
                    f"n={n}, expectancy={exp:.3f}R, Bayesian upper bound={bhi:.3f}.",
                    0,
                )
            )
    for a, b, n, synergy in db.execute(
        "SELECT rule_a,rule_b,sample_count,synergy FROM rule_interactions WHERE sample_count>=8"
    ):
        if abs(synergy or 0) >= 0.20:
            action = "REVIEW_RULE_SYNERGY" if synergy > 0 else "REVIEW_RULE_CONFLICT"
            recs.append(
                (
                    "RULE_INTERACTION",
                    f"{a} + {b}",
                    action,
                    "MEDIUM",
                    f"n={n}, interaction expectancy delta={synergy:.3f}R versus mean individual expectancy.",
                    0,
                )
            )
    db.executemany("INSERT INTO recommendations VALUES (?,?,?,?,?,?)", recs)
    db.commit()
    return recs


def slug(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return value or "pattern"


def create_pattern_databases(db, metrics, raw):
    metric_by = {m["signal_id"]: m for m in metrics}
    evidence_by = index_rows(raw["evidence"])
    outputs = []
    for concept in all_concepts():
        path = PATTERN_DB_DIR / f"{slug(concept.concept)}.sqlite"
        if path.exists():
            path.unlink()
        con = sqlite3.connect(path)
        con.executescript("""
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE actual_samples(signal_id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
        CREATE TABLE observational_samples(exchange TEXT,market_type TEXT,symbol TEXT,timeframe TEXT,snapshot_close TEXT,
          category TEXT,concept TEXT,rule_id TEXT,bias TEXT,directional_return REAL,mfe_pct REAL,mae_pct REAL,payload TEXT);
        CREATE TABLE statistics(kind TEXT PRIMARY KEY,payload TEXT NOT NULL);
        """)
        con.executemany(
            "INSERT INTO metadata VALUES (?,?)",
            [
                ("concept", concept.concept),
                ("status", concept.status),
                ("rule_ids", dumps(list(concept.rule_ids))),
                ("semantics", "INDEPENDENT_RESEARCH_DATABASE_NO_PRODUCTION_EFFECT"),
            ],
        )
        rule_set = set(concept.rule_ids)
        actual = []
        for sid, m in metric_by.items():
            if any(e["rule_id"] in rule_set for e in evidence_by.get(sid, [])):
                actual.append(m)
                con.execute("INSERT OR REPLACE INTO actual_samples VALUES (?,?)", (sid, dumps(m)))
        placeholders = ",".join("?" for _ in rule_set)
        obs = []
        if rule_set:
            query = f"SELECT exchange,market_type,symbol,timeframe,snapshot_close,category,concept,rule_id,bias,directional_return,mfe_pct,mae_pct,payload FROM historical_observations WHERE rule_id IN ({placeholders})"
            obs = list(db.execute(query, tuple(sorted(rule_set))))
        con.executemany("INSERT INTO observational_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", obs)
        actual_closed = [m for m in actual if m.get("realized_r") is not None]
        actual_summary = performance_summary(
            concept.concept, "ACTUAL_RULE_ASSOCIATED", actual_closed
        )
        con.execute("INSERT INTO statistics VALUES (?,?)", ("actual", dumps(actual_summary)))
        obs_dr = [float(r[9]) for r in obs if r[9] is not None]
        if obs_dr:
            wins = sum(v > 0 for v in obs_dr)
            n = len(obs_dr)
            bayes, ci = bayesian_win_interval(wins, n - wins)
            boot = bootstrap_interval(obs_dr)
            obs_summary = {
                "sample_count": n,
                "directional_hit_rate": wins / n,
                "avg_directional_return": float(np.mean(obs_dr)),
                "median_directional_return": float(np.median(obs_dr)),
                "bayes_mean": bayes,
                "bayes_ci": [ci.low, ci.high],
                "bootstrap_mean_ci": [boot.low, boot.high],
                "semantics": "OBSERVATIONAL_FORWARD_NOT_ACTUAL_TRADE_WIN_RATE",
            }
        else:
            obs_summary = {"sample_count": 0, "semantics": "NO_DIRECTIONAL_OBSERVATIONAL_SAMPLE"}
        con.execute("INSERT INTO statistics VALUES (?,?)", ("observational", dumps(obs_summary)))
        con.commit()
        con.close()
        outputs.append((concept.concept, path.name, len(actual), len(obs)))
    return outputs


def export_query_csv(db, filename, query, params=()):
    cur = db.execute(query, params)
    headers = [d[0] for d in cur.description]
    rows = cur.fetchall()
    with (OUT / filename).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    return len(rows)


def export_tables(db):
    exports = {
        "pattern_performance_actual.csv": "SELECT * FROM pattern_stats ORDER BY sample_count DESC,pattern",
        "pattern_performance_observational.csv": "SELECT * FROM observational_pattern_stats ORDER BY sample_count DESC,pattern",
        "context_performance_actual.csv": "SELECT * FROM context_stats ORDER BY sample_count DESC,pattern,context",
        "context_performance_observational.csv": "SELECT * FROM observational_context_stats ORDER BY sample_count DESC,pattern,context",
        "rule_interactions.csv": "SELECT * FROM rule_interactions ORDER BY sample_count DESC,synergy DESC",
        "false_signal_research.csv": "SELECT category,count(*) sample_count,avg(realized_r) avg_r FROM false_signal_categories GROUP BY category ORDER BY sample_count DESC",
        "missed_opportunity_research.csv": "SELECT concept,count(*) sample_count,avg(directional_return) avg_directional_return,avg(mfe_pct) avg_mfe_pct,avg(mae_pct) avg_mae_pct FROM missed_opportunities GROUP BY concept ORDER BY sample_count DESC",
        "market_timeframe_stats.csv": "SELECT * FROM market_timeframe_stats ORDER BY market_type,symbol,timeframe",
        "correlation_matrix_long.csv": "SELECT * FROM correlations",
        "recommendations.csv": "SELECT * FROM recommendations ORDER BY confidence DESC,scope,subject",
        "survival_analysis.csv": "SELECT * FROM survival_points ORDER BY time_seconds",
    }
    return {name: export_query_csv(db, name, q) for name, q in exports.items()}


def save_bar(labels, values, title, ylabel, filename):
    if not labels:
        return
    fig, ax = plt.subplots(figsize=(11, max(5, len(labels) * 0.35)))
    y = np.arange(len(labels))
    ax.barh(y, values)
    ax.set_yticks(y, labels=labels)
    ax.set_xlabel(ylabel)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=160)
    plt.close(fig)


def generate_charts(db, metrics, corr_names, corr_matrix):
    rows = list(
        db.execute(
            "SELECT pattern,win_rate,wilson_low,wilson_high,sample_count FROM pattern_stats WHERE sample_type='ACTUAL' AND pattern!='ALL_ACTUAL_SIGNALS' ORDER BY win_rate"
        )
    )
    if rows:
        labels = [f"{r[0]} (n={r[4]})" for r in rows]
        vals = [r[1] for r in rows]
        lows = [max(0, r[1] - r[2]) for r in rows]
        highs = [max(0, r[3] - r[1]) for r in rows]
        fig, ax = plt.subplots(figsize=(11, max(5, len(rows) * 0.45)))
        y = np.arange(len(rows))
        ax.errorbar(vals, y, xerr=np.asarray([lows, highs]), fmt="o")
        ax.set_yticks(y, labels=labels)
        ax.set_xlim(0, 1)
        ax.set_xlabel("Actual positive-outcome rate with Wilson 95% interval")
        ax.set_title("Actual Pattern Reliability")
        fig.tight_layout()
        fig.savefig(OUT / "pattern_reliability.png", dpi=160)
        plt.close(fig)

    ordered = sorted(
        [m for m in metrics if m.get("realized_r") is not None], key=lambda x: x["created_at"]
    )
    if ordered:
        curve = np.concatenate(([0.0], np.cumsum([m["realized_r"] for m in ordered])))
        peaks = np.maximum.accumulate(curve)
        dd = peaks - curve
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.plot(curve)
        ax.set_title("Cumulative Realized R (Actual Signals)")
        ax.set_xlabel("Trade index")
        ax.set_ylabel("Cumulative R")
        fig.tight_layout()
        fig.savefig(OUT / "actual_equity_r.png", dpi=160)
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.plot(dd)
        ax.set_title("Drawdown Distribution Through Time")
        ax.set_xlabel("Trade index")
        ax.set_ylabel("Drawdown (R)")
        fig.tight_layout()
        fig.savefig(OUT / "actual_drawdown_r.png", dpi=160)
        plt.close(fig)
    if corr_matrix.size and np.isfinite(corr_matrix).any():
        fig, ax = plt.subplots(figsize=(8, 7))
        im = ax.imshow(corr_matrix, vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(corr_names)), labels=corr_names, rotation=45, ha="right")
        ax.set_yticks(range(len(corr_names)), labels=corr_names)
        ax.set_title("Correlation Matrix — Actual Signal Metrics")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        fig.savefig(OUT / "correlation_matrix.png", dpi=160)
        plt.close(fig)

    surv = list(
        db.execute("SELECT time_seconds,survival FROM survival_points ORDER BY time_seconds")
    )
    if surv:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.step([r[0] / 60 for r in surv], [r[1] for r in surv], where="post")
        ax.set_xlabel("Minutes since activation")
        ax.set_ylabel("Survival probability")
        ax.set_title("Holding-Time Survival Curve")
        fig.tight_layout()
        fig.savefig(OUT / "holding_time_survival.png", dpi=160)
        plt.close(fig)

    fail = list(
        db.execute(
            "SELECT category,count(*) n FROM false_signal_categories GROUP BY category ORDER BY n"
        )
    )
    save_bar(
        [r[0] for r in fail],
        [r[1] for r in fail],
        "False-Signal Failure Taxonomy",
        "Count",
        "failure_ranking.png",
    )
    missed = list(
        db.execute(
            "SELECT concept,count(*) n FROM missed_opportunities GROUP BY concept ORDER BY n DESC LIMIT 15"
        )
    )
    save_bar(
        [r[0] for r in reversed(missed)],
        [r[1] for r in reversed(missed)],
        "Missed Observational Opportunities",
        "Count",
        "opportunity_ranking.png",
    )
    market = list(
        db.execute(
            "SELECT market_type||':'||symbol||':'||timeframe,return_std FROM market_timeframe_stats ORDER BY return_std"
        )
    )
    save_bar(
        [r[0] for r in market],
        [r[1] for r in market],
        "Market / Timeframe Realized Volatility",
        "Std(log return)",
        "market_timeframe_volatility.png",
    )


def generate_reliability_matrix(db):
    rows = list(
        db.execute(
            "SELECT pattern,context,win_rate,sample_count FROM context_stats WHERE context LIKE 'RECORDED_REGIME:%'"
        )
    )
    patterns = sorted({r[0] for r in rows})
    contexts = sorted({r[1] for r in rows})
    lookup = {(r[0], r[1]): (r[2], r[3]) for r in rows}
    with (OUT / "reliability_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pattern", *contexts])
        for pattern in patterns:
            w.writerow(
                [
                    pattern,
                    *[
                        (
                            ""
                            if (pattern, c) not in lookup
                            else f"{lookup[(pattern, c)][0]:.4f}|n={lookup[(pattern, c)][1]}"
                        )
                        for c in contexts
                    ],
                ]
            )
    if patterns and contexts:
        matrix = np.full((len(patterns), len(contexts)), np.nan)
        for i, p in enumerate(patterns):
            for j, c in enumerate(contexts):
                if (p, c) in lookup:
                    matrix[i, j] = lookup[(p, c)][0]
        fig, ax = plt.subplots(figsize=(max(8, len(contexts) * 2), max(6, len(patterns) * 0.45)))
        im = ax.imshow(matrix, vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(len(contexts)), labels=contexts, rotation=35, ha="right")
        ax.set_yticks(range(len(patterns)), labels=patterns)
        ax.set_title("Pattern × Recorded Regime Reliability Matrix")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        fig.savefig(OUT / "reliability_matrix.png", dpi=160)
        plt.close(fig)
    return len(rows)


from research_layer.statistics import blocked_cross_validation


def fmt(x, digits=3):
    if x is None:
        return "N/A"
    try:
        if not math.isfinite(float(x)):
            return "N/A"
        return f"{float(x):.{digits}f}"
    except Exception:
        return str(x)


def generate_report(db, metrics, raw, universe_snapshots, universe_findings, pattern_dbs):
    overall = db.execute(
        "SELECT * FROM pattern_stats WHERE pattern='ALL_ACTUAL_SIGNALS' AND sample_type='ACTUAL'"
    ).fetchone()
    cols = [d[0] for d in db.execute("SELECT * FROM pattern_stats LIMIT 0").description]
    overall = dict(zip(cols, overall)) if overall else {}
    closed = [m for m in metrics if m.get("realized_r") is not None]
    rvals = [m["realized_r"] for m in sorted(closed, key=lambda x: x["created_at"])]
    validation = {
        "blocked_cross_validation": blocked_cross_validation(rvals),
        "walk_forward": walk_forward(rvals),
        "out_of_sample": out_of_sample_split(rvals),
        "monte_carlo": monte_carlo_paths(rvals),
    }
    (OUT / "validation_methods.json").write_text(
        json.dumps(validation, indent=2, default=json_default)
    )
    top = list(
        db.execute(
            "SELECT pattern,sample_count,win_rate,expectancy,bayes_low,bayes_high FROM pattern_stats WHERE sample_type='ACTUAL' AND pattern!='ALL_ACTUAL_SIGNALS' ORDER BY expectancy DESC LIMIT 8"
        )
    )
    bottom = list(
        db.execute(
            "SELECT pattern,sample_count,win_rate,expectancy,bayes_low,bayes_high FROM pattern_stats WHERE sample_type='ACTUAL' AND pattern!='ALL_ACTUAL_SIGNALS' ORDER BY expectancy ASC LIMIT 8"
        )
    )
    contexts = list(
        db.execute(
            "SELECT pattern,context,sample_count,win_rate,expectancy,ci_low,ci_high FROM context_stats WHERE sample_count>=5 ORDER BY expectancy DESC LIMIT 12"
        )
    )
    interactions = list(
        db.execute(
            "SELECT rule_a,rule_b,sample_count,win_rate,expectancy,synergy FROM rule_interactions WHERE sample_count>=5 ORDER BY synergy DESC LIMIT 10"
        )
    )
    failures = list(
        db.execute(
            "SELECT category,count(*) n,avg(realized_r) avg_r FROM false_signal_categories GROUP BY category ORDER BY n DESC"
        )
    )
    missed = list(
        db.execute(
            "SELECT concept,count(*) n,avg(directional_return) avg_ret,avg(mfe_pct),avg(mae_pct) FROM missed_opportunities GROUP BY concept ORDER BY n DESC LIMIT 12"
        )
    )
    recs = list(
        db.execute(
            "SELECT scope,subject,recommendation,confidence,rationale FROM recommendations ORDER BY confidence DESC,scope LIMIT 30"
        )
    )
    lines = [
        "# Brooks Research Layer — Final Scientific Report",
        "",
        "## Executive Summary",
        "",
        f"- Production signals observed: **{len(raw['signals'])}**; actual closed signals with reconstructable R: **{len(closed)}**.",
        f"- Raw market universe: **{len(SYMBOLS) * len(TIMEFRAMES) * 2 * RAW_CANDLE_LIMIT:,} candles requested** across BTC/ETH/SOL, Spot/Futures and six timeframes.",
        f"- Knowledge replay snapshots evaluated: **{universe_snapshots:,}**; findings stored: **{universe_findings:,}**.",
        f"- Independent pattern research databases created: **{len(pattern_dbs)}**.",
        f"- Actual aggregate positive-outcome rate: **{fmt(overall.get('win_rate'))}**; expectancy: **{fmt(overall.get('expectancy'))} R**; profit factor: **{fmt(overall.get('profit_factor'))}**.",
        f"- Bayesian 95% win interval: **[{fmt(overall.get('bayes_low'))}, {fmt(overall.get('bayes_high'))}]**; bootstrap expectancy interval: **[{fmt(overall.get('bootstrap_low'))}, {fmt(overall.get('bootstrap_high'))}] R**.",
        "- No production Rule, Weight, Threshold, Probability, AI, Risk, Quality, Telegram or runtime file was intentionally modified by this research pipeline.",
        "",
        "## Scientific Findings",
        "",
        "### Actual pattern performance",
        "",
        "| Pattern | n | Win rate | Expectancy R | Bayesian 95% interval |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in top:
        lines.append(
            f"| {r[0]} | {r[1]} | {fmt(r[2])} | {fmt(r[3])} | [{fmt(r[4])}, {fmt(r[5])}] |"
        )
    lines += [
        "",
        "### Lowest observed actual expectancy",
        "",
        "| Pattern | n | Win rate | Expectancy R | Bayesian 95% interval |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in bottom:
        lines.append(
            f"| {r[0]} | {r[1]} | {fmt(r[2])} | {fmt(r[3])} | [{fmt(r[4])}, {fmt(r[5])}] |"
        )
    lines += [
        "",
        "### Context research",
        "",
        "| Pattern | Context | n | Win rate | Expectancy R | Bayesian 95% interval |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in contexts:
        lines.append(
            f"| {r[0]} | {r[1]} | {r[2]} | {fmt(r[3])} | {fmt(r[4])} | [{fmt(r[5])}, {fmt(r[6])}] |"
        )
    lines += [
        "",
        "### Rule interaction research",
        "",
        "| Rule A | Rule B | n | Win rate | Expectancy R | Synergy ΔR |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in interactions:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {fmt(r[3])} | {fmt(r[4])} | {fmt(r[5])} |")
    lines += [
        "",
        "## False Signal Research",
        "",
        "| Category | Count | Mean R |",
        "|---|---:|---:|",
    ]
    for r in failures:
        lines.append(f"| {r[0]} | {r[1]} | {fmt(r[2])} |")
    lines += [
        "",
        "## Missed Opportunity Research",
        "",
        "Missed opportunities are observational Knowledge-Layer entries with no same-direction production signal within 1.25 bars. They are not hypothetical trades.",
        "",
        "| Concept | Count | Avg 10-bar directional return | Avg MFE | Avg MAE |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in missed:
        lines.append(f"| {r[0]} | {r[1]} | {fmt(r[2], 5)} | {fmt(r[3], 5)} | {fmt(r[4], 5)} |")
    lines += [
        "",
        "## Statistical Confidence",
        "",
        "- Bayesian win intervals use a Jeffreys Beta(0.5,0.5) prior; they are descriptive uncertainty estimates, not production probabilities.",
        "- Bootstrap intervals use 4,000 resamples; Monte Carlo uses 5,000 resampled trade paths.",
        "- Validation is chronological: blocked cross-validation, walk-forward, rolling validation, and a final 30% out-of-sample split. No shuffled time-series CV is used.",
        "- Statistical significance uses a two-sided exact binomial test against 50% positive-outcome frequency; this is a research reference, not a Brooks threshold.",
        "",
        "## Evidence and Data Quality",
        "",
        "- Production PostgreSQL was accessed in READ ONLY transactions.",
        "- MFE/MAE are reconstructed from public closed candles between entry activation and closure and expressed in initial stop-distance R units.",
        "- Realized R is reconstructed from recorded leveraged P/L divided by the recorded initial risk percentage.",
        "- Entry slippage is the difference between recorded activated entry price and configured entry price. Bid/ask spread is unavailable from kline data and is therefore reported as unavailable, never imputed.",
        "- Execution record delay is event-record timestamp minus the candle-close timestamp in ENTRY_ACTIVATED metadata; it is not exchange matching-engine latency.",
        "",
        "## Limitations",
        "",
        "- The live production sample spans only about two days and contains BTC/ETH on 15m/1h; many patterns have small or zero actual-trade samples.",
        "- Any rows outside the supplied signal extract are observational market research, not live trading performance.",
        "- Historical Knowledge findings are generated with the current read-only Knowledge Engine, not necessarily the exact historical engine version used when each old signal was produced.",
        "- Public OHLCV does not provide historical bid/ask spread or true exchange execution latency.",
        "- Multiple correlated signals can share the same market move; statistical independence should not be assumed.",
        "",
        "## Recommended Calibrations — Recommendations Only",
        "",
        "No recommendation below has been applied to Production.",
        "",
    ]
    for scope, subject, rec, confidence, rationale in recs:
        lines.append(f"- **[{confidence}] {rec}** — `{subject}` ({scope}): {rationale}")
    lines += [
        "",
        "## Risk Analysis",
        "",
        "- Research recommendations are subject to selection bias, regime concentration, small-sample uncertainty and correlated observations.",
        "- Negative expectancy in a small sample is not sufficient evidence to remove a Brooks rule; likewise positive expectancy is not sufficient evidence to increase weight.",
        "- Weight/threshold changes should require a separate controlled calibration phase with frozen hypotheses and fresh out-of-sample data.",
        "",
        "## Potential Improvements",
        "",
        "- Persist bid/ask snapshots and exchange acknowledgements in a future data-capture project if true spread/slippage/latency research is required.",
        "- Expand actual outcome history across several months and additional symbols before treating pattern rankings as stable.",
        "- Add version-aware historical reconstruction so each signal can be replayed with its exact engine/rule/configuration versions.",
        "",
        "## Future Research",
        "",
        "- Monthly regime-stratified walk-forward reports.",
        "- Pattern evolution studies: failed H2/L2 → wedge, failed breakout → breakout pullback, final-flag failure → resumption.",
        "- Multi-timeframe conditional reliability with causal HTF snapshots.",
        "- Cross-market divergence and funding/open-interest overlays require a separately supplied, provenance-labelled extract.",
        "- Survival models for time-to-target and time-to-stop with larger samples.",
        "",
        "## Research Layer Safety",
        "",
        "The pipeline is observational only. Recommendations are stored with `applied=0`. Production file hashes are checked before and after the mission.",
        "",
    ]
    (OUT / "FINAL_RESEARCH_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    return lines


def export_covariance(metrics):
    columns = [
        "realized_r",
        "mfe_r",
        "mae_r",
        "ai_score",
        "risk_score",
        "quality_score",
        "confidence",
        "evidence_pass",
        "evidence_ambiguous",
    ]
    usable = []
    for m in metrics:
        vals = []
        ok = True
        for c in columns:
            if m.get(c) is None:
                ok = False
                break
            vals.append(float(m[c]))
        if ok:
            usable.append(vals)
    matrix = (
        np.cov(np.asarray(usable, dtype=float), rowvar=False)
        if len(usable) > 1
        else np.full((len(columns), len(columns)), np.nan)
    )
    with (OUT / "covariance_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", *columns])
        for i, name in enumerate(columns):
            w.writerow([name, *[matrix[i, j] for j in range(len(columns))]])
    return len(usable)


def export_rankings(db):
    return {
        "pattern_ranking.csv": export_query_csv(
            db,
            "pattern_ranking.csv",
            "SELECT pattern,sample_count,win_rate,expectancy,profit_factor,sharpe,bayes_low,bayes_high,p_value FROM pattern_stats WHERE sample_type='ACTUAL' AND pattern!='ALL_ACTUAL_SIGNALS' ORDER BY expectancy DESC",
        ),
        "context_ranking.csv": export_query_csv(
            db,
            "context_ranking.csv",
            "SELECT pattern,context,sample_count,win_rate,expectancy,ci_low,ci_high FROM context_stats ORDER BY expectancy DESC,sample_count DESC",
        ),
        "failure_ranking.csv": export_query_csv(
            db,
            "failure_ranking.csv",
            "SELECT category,count(*) sample_count,avg(realized_r) avg_r FROM false_signal_categories GROUP BY category ORDER BY sample_count DESC,avg_r",
        ),
        "opportunity_ranking.csv": export_query_csv(
            db,
            "opportunity_ranking.csv",
            "SELECT concept,count(*) sample_count,avg(directional_return) avg_directional_return,avg(mfe_pct) avg_mfe_pct,avg(mae_pct) avg_mae_pct FROM missed_opportunities GROUP BY concept ORDER BY avg_directional_return DESC,sample_count DESC",
        ),
    }


async def main(*, raw_extract: Path, market_extract: Path, output_dir: Path):
    started = datetime.now(UTC)
    configure_output_dir(output_dir)
    OUT.mkdir(parents=True, exist_ok=True)
    PATTERN_DB_DIR.mkdir(parents=True, exist_ok=True)
    db = open_research_db()
    ensure_analysis_tables(db)
    raw = load_raw_extract(raw_extract)
    persist_raw(db, raw)
    print("RAW_EXTRACT", {key: len(value) for key, value in raw.items()}, flush=True)
    series = load_market_extract(market_extract)
    for key, candles in series.items():
        db.executemany(
            "INSERT OR REPLACE INTO market_candles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [candle_tuple(*key, candle) for candle in candles],
        )
    db.commit()
    metrics = reconstruct_signal_metrics(db, raw, series)
    persist_signal_metrics(db, metrics)
    print("SIGNAL_METRICS", len(metrics), flush=True)
    snapshots, findings = generate_historical_observations(db, series, raw)
    actual_stats, contexts = actual_analyses(db, metrics, raw)
    interactions = analyse_rule_interactions(db, metrics, raw)
    failures = analyse_false_signals(db, metrics, raw)
    missed = analyse_missed_opportunities(db, raw)
    market_rows = analyse_market_timeframes(db, series)
    surv, corr_names, corr_matrix = analyse_survival_and_correlations(db, metrics)
    obs_stats, obs_ctx = analyse_observational(db)
    recs = generate_recommendations(db)
    pattern_dbs = create_pattern_databases(db, metrics, raw)
    exports = export_tables(db)
    exports.update(export_rankings(db))
    reliability_rows = generate_reliability_matrix(db)
    covariance_n = export_covariance(metrics)
    generate_charts(db, metrics, corr_names, corr_matrix)
    generate_report(db, metrics, raw, snapshots, findings, pattern_dbs)
    db.commit()
    db.close()
    summary = {
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "input_mode": "EXPLICIT_OFFLINE_EXTRACTS",
        "production_database_access": False,
        "network_access": False,
        "production_signals": len(raw["signals"]),
        "production_evidence": len(raw["evidence"]),
        "market_series": len(series),
        "raw_market_candles": sum(len(value) for value in series.values()),
        "knowledge_snapshots": snapshots,
        "historical_findings": findings,
        "pattern_databases": len(pattern_dbs),
        "actual_pattern_stats": len(actual_stats),
        "observational_pattern_stats": len(obs_stats),
        "context_stats": len(obs_ctx),
        "rule_interactions": len(interactions),
        "false_signal_labels": len(failures),
        "missed_observations": len(missed),
        "recommendations": len(recs),
        "survival_points": len(surv),
        "covariance_complete_rows": covariance_n,
        "reliability_rows": reliability_rows,
        "exports": exports,
        "semantics": "RESEARCH_ONLY_NO_PRODUCTION_MUTATION",
    }
    (OUT / "run_summary.json").write_text(
        json.dumps(summary, indent=2, default=json_default), encoding="utf-8"
    )
    print("RESEARCH_COMPLETE", json.dumps(summary, default=json_default), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-extract", type=Path, required=True)
    parser.add_argument("--market-extract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(
        main(
            raw_extract=args.raw_extract,
            market_extract=args.market_extract,
            output_dir=args.output_dir,
        )
    )
