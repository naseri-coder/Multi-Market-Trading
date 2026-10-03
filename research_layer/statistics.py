"""Statistical primitives for the read-only Brooks Research Layer."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class Interval:
    low: float
    high: float


def finite(values: Iterable[float | None]) -> np.ndarray:
    return np.asarray([float(v) for v in values if v is not None and math.isfinite(float(v))], dtype=float)


def wilson_interval(wins: int, total: int, z: float = 1.959963984540054) -> Interval:
    if total <= 0:
        return Interval(float("nan"), float("nan"))
    p = wins / total
    den = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / den
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total) / den
    return Interval(max(0.0, center - margin), min(1.0, center + margin))


def bootstrap_interval(values: Iterable[float | None], *, statistic="mean", draws: int = 4000, seed: int = 20260905) -> Interval:
    x = finite(values)
    if x.size == 0:
        return Interval(float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, x.size, size=(draws, x.size))
    samples = x[idx]
    if statistic == "median":
        stats = np.median(samples, axis=1)
    elif statistic == "win_rate":
        stats = np.mean(samples > 0.0, axis=1)
    else:
        stats = np.mean(samples, axis=1)
    lo, hi = np.quantile(stats, [0.025, 0.975])
    return Interval(float(lo), float(hi))


def bayesian_win_interval(wins: int, losses: int, *, draws: int = 20000, seed: int = 20260905) -> tuple[float, Interval]:
    # Weak Jeffreys prior; posterior remains explicitly sample-size dependent.
    rng = np.random.default_rng(seed)
    samples = rng.beta(wins + 0.5, losses + 0.5, size=draws)
    lo, hi = np.quantile(samples, [0.025, 0.975])
    return float(np.mean(samples)), Interval(float(lo), float(hi))


def profit_factor(r_values: Iterable[float | None]) -> float:
    x = finite(r_values)
    gains = float(x[x > 0].sum()) if x.size else 0.0
    losses = float(-x[x < 0].sum()) if x.size else 0.0
    if losses == 0.0:
        return float("inf") if gains > 0.0 else float("nan")
    return gains / losses


def sharpe_ratio(r_values: Iterable[float | None]) -> float:
    x = finite(r_values)
    if x.size < 2:
        return float("nan")
    std = float(np.std(x, ddof=1))
    return float(np.mean(x) / std) if std > 0.0 else float("nan")


def max_drawdown(r_values: Iterable[float | None]) -> float:
    x = finite(r_values)
    if x.size == 0:
        return float("nan")
    equity = np.cumsum(x)
    peaks = np.maximum.accumulate(np.concatenate(([0.0], equity)))
    curve = np.concatenate(([0.0], equity))
    return float(np.max(peaks - curve))


def distribution(values: Iterable[float | None]) -> dict[str, float | int]:
    x = finite(values)
    if x.size == 0:
        return {"n": 0}
    q = np.quantile(x, [0.05, 0.25, 0.5, 0.75, 0.95])
    return {
        "n": int(x.size), "mean": float(np.mean(x)), "median": float(np.median(x)),
        "variance": float(np.var(x, ddof=1)) if x.size > 1 else 0.0,
        "std": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "q05": float(q[0]), "q25": float(q[1]), "q50": float(q[2]),
        "q75": float(q[3]), "q95": float(q[4]),
    }


def monte_carlo_paths(r_values: Iterable[float | None], *, paths: int = 5000, seed: int = 20260905) -> dict[str, float]:
    x = finite(r_values)
    if x.size == 0:
        return {}
    rng = np.random.default_rng(seed)
    samples = rng.choice(x, size=(paths, x.size), replace=True)
    totals = samples.sum(axis=1)
    drawdowns=[]
    for row in samples:
        curve=np.concatenate(([0.0], np.cumsum(row)))
        peaks=np.maximum.accumulate(curve)
        drawdowns.append(float(np.max(peaks-curve)))
    return {
        "total_r_p05": float(np.quantile(totals,0.05)),
        "total_r_median": float(np.median(totals)),
        "total_r_p95": float(np.quantile(totals,0.95)),
        "max_dd_p50": float(np.quantile(drawdowns,0.50)),
        "max_dd_p95": float(np.quantile(drawdowns,0.95)),
        "prob_total_positive": float(np.mean(totals > 0.0)),
    }


def walk_forward(r_values: Iterable[float | None], folds: int = 4) -> list[dict[str, float | int]]:
    x=finite(r_values)
    if x.size < folds + 2:
        return []
    parts=np.array_split(np.arange(x.size), folds + 1)
    rows=[]
    for i in range(1,len(parts)):
        train_idx=np.concatenate(parts[:i]); test_idx=parts[i]
        train=x[train_idx]; test=x[test_idx]
        rows.append({
            "fold": i, "train_n": int(train.size), "test_n": int(test.size),
            "train_expectancy": float(train.mean()), "test_expectancy": float(test.mean()),
            "train_win_rate": float(np.mean(train>0)), "test_win_rate": float(np.mean(test>0)),
        })
    return rows


def rolling_validation(r_values: Iterable[float | None], window: int = 20) -> list[dict[str, float | int]]:
    x=finite(r_values)
    if x.size < window:
        return []
    return [
        {"end_index": i, "n": window, "expectancy": float(np.mean(x[i-window:i])), "win_rate": float(np.mean(x[i-window:i]>0))}
        for i in range(window,x.size+1)
    ]


def kaplan_meier(durations: Iterable[float | None], events: Iterable[bool]) -> list[dict[str, float | int]]:
    pairs=sorted((float(t),bool(e)) for t,e in zip(durations,events) if t is not None and math.isfinite(float(t)))
    if not pairs:
        return []
    at_risk=len(pairs); survival=1.0; rows=[]; i=0
    while i < len(pairs):
        t=pairs[i][0]; same=[]
        while i < len(pairs) and pairs[i][0] == t:
            same.append(pairs[i]); i+=1
        d=sum(1 for _,e in same if e); c=len(same)-d
        if at_risk > 0 and d:
            survival *= (1.0 - d / at_risk)
        rows.append({"time":t,"at_risk":at_risk,"events":d,"censored":c,"survival":survival})
        at_risk -= len(same)
    return rows


def correlation_matrix(rows: list[dict[str, float | None]], columns: list[str]) -> tuple[list[str], np.ndarray]:
    usable=[]
    for row in rows:
        vals=[]; ok=True
        for col in columns:
            value=row.get(col)
            if value is None or not math.isfinite(float(value)):
                ok=False; break
            vals.append(float(value))
        if ok:
            usable.append(vals)
    if len(usable) < 2:
        return columns, np.full((len(columns),len(columns)), np.nan)
    return columns, np.corrcoef(np.asarray(usable,dtype=float),rowvar=False)


def binomial_two_sided_p(wins: int, total: int, p0: float = 0.5) -> float:
    if total <= 0:
        return float("nan")
    def pmf(k: int) -> float:
        return math.comb(total,k) * (p0 ** k) * ((1.0-p0) ** (total-k))
    observed=pmf(wins)
    return min(1.0, sum(pmf(k) for k in range(total+1) if pmf(k) <= observed + 1e-15))


def out_of_sample_split(r_values: Iterable[float | None], fraction: float = 0.30) -> dict[str, float | int]:
    x=finite(r_values)
    if x.size < 4:
        return {}
    cut=max(1,min(x.size-1,int(round(x.size*(1.0-fraction)))))
    train=x[:cut]; test=x[cut:]
    return {
        "train_n":int(train.size),"test_n":int(test.size),
        "train_expectancy":float(train.mean()),"test_expectancy":float(test.mean()),
        "train_win_rate":float(np.mean(train>0)),"test_win_rate":float(np.mean(test>0)),
    }


def blocked_cross_validation(r_values: Iterable[float | None], folds: int = 5) -> list[dict[str, float | int]]:
    x=finite(r_values)
    if x.size < folds:
        return []
    blocks=np.array_split(x,folds)
    rows=[]
    for i,test in enumerate(blocks):
        train=np.concatenate([b for j,b in enumerate(blocks) if j != i])
        rows.append({
            "fold":i+1,"train_n":int(train.size),"test_n":int(test.size),
            "train_expectancy":float(np.mean(train)),"test_expectancy":float(np.mean(test)),
            "train_win_rate":float(np.mean(train>0)),"test_win_rate":float(np.mean(test>0)),
            "note":"BLOCKED_NO_SHUFFLE_TIME_SERIES_CV",
        })
    return rows
