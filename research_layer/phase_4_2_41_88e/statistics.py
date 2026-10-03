from __future__ import annotations

import hashlib
import math
import time

import numpy as np

from .contract import *


def dt(s):
    from datetime import datetime

    return datetime.fromisoformat(s)


def family(s):
    v = str(s or "UNKNOWN").upper()
    for suf in ("_LONG", "_SHORT"):
        if v.endswith(suf):
            v = v[: -len(suf)]
    for p in (
        "BREAKOUT_PULLBACK",
        "FAILED_BREAKOUT",
        "FAILED_FAILURE",
        "BREAKOUT",
        "PARABOLIC_WEDGE",
        "MICRO_WEDGE",
        "WEDGE",
        "DOUBLE_TOP",
        "DOUBLE_BOTTOM",
        "MAJOR_TREND_REVERSAL",
        "FINAL_FLAG",
        "CLIMACTIC_REVERSAL",
        "TRADING_RANGE_FADE",
        "H1",
        "H2",
        "H3",
        "H4",
        "L1",
        "L2",
        "L3",
        "L4",
    ):
        if v.startswith(p):
            return p
    return v


def exact_compatible(c, h):
    return all(c.get(k) == h.get(k) for k in COHORT_FIELDS)


def select_pool(c, prior):
    prior = [x for x in prior if exact_compatible(c, x)]
    s, tf, d, f = c["setup_type"], c["timeframe"], c["direction"], family(c["setup_type"])
    levels = [
        ("SETUP_TIMEFRAME", [x for x in prior if x["setup_type"] == s and x["timeframe"] == tf]),
        ("SETUP_ALL_TIMEFRAMES", [x for x in prior if x["setup_type"] == s]),
        (
            "FAMILY_TIMEFRAME",
            [x for x in prior if family(x["setup_type"]) == f and x["timeframe"] == tf],
        ),
        ("FAMILY_ALL_TIMEFRAMES", [x for x in prior if family(x["setup_type"]) == f]),
        ("DIRECTION_TIMEFRAME", [x for x in prior if x["direction"] == d and x["timeframe"] == tf]),
        ("DIRECTION_ALL_TIMEFRAMES", [x for x in prior if x["direction"] == d]),
    ]
    for scope, pool in levels:
        if len(pool) >= MIN_N:
            return scope, pool
    return levels[-1]


def cohort_serial(c):
    return "|".join(f"{k}={c[k]}" for k in COHORT_FIELDS[:-1])


def seed_for(c, scope, ids):
    material = "|".join([ORIG_STAT, cohort_serial(c), scope, *ids]).encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def bootstrap_t(values, c, scope, ids, B=BOOTSTRAPS):
    x = np.asarray(values, float)
    n = len(x)
    t0 = time.perf_counter()
    if n < 2:
        return None, {"invalid_reason": "N_LT_2", "runtime_ms": (time.perf_counter() - t0) * 1000}
    theta = float(x.mean())
    se = float(x.std(ddof=1) / math.sqrt(n))
    if not math.isfinite(se) or se <= EPS:
        return None, {
            "invalid_reason": "ZERO_OR_INVALID_SE",
            "sample_se": se,
            "runtime_ms": (time.perf_counter() - t0) * 1000,
        }
    rng = np.random.default_rng(seed_for(c, scope, ids))
    chunks = []
    valid = deg = 0
    for s in range(0, B, 2000):
        b = min(2000, B - s)
        y = x[rng.integers(0, n, size=(b, n))]
        m = y.mean(1)
        sy = y.std(1, ddof=1) / math.sqrt(n)
        ok = np.isfinite(sy) & (sy > EPS)
        deg += int((~ok).sum())
        valid += int(ok.sum())
        if ok.any():
            chunks.append((m[ok] - theta) / sy[ok])
    if valid < int(0.95 * B):
        return None, {
            "invalid_reason": "TOO_MANY_DEGENERATE_RESAMPLES",
            "valid_resamples": valid,
            "degenerate_resamples": deg,
            "sample_se": se,
            "runtime_ms": (time.perf_counter() - t0) * 1000,
        }
    ts = np.concatenate(chunks)
    q025, q975 = np.quantile(ts, [0.025, 0.975])
    lo = theta - float(q975) * se
    hi = theta - float(q025) * se
    return {
        "n": n,
        "mean_r": theta,
        "std_r": float(x.std(ddof=1)),
        "median_r": float(np.median(x)),
        "sample_se": se,
        "ci95_lower": lo,
        "ci95_upper": hi,
        "ci95_width": hi - lo,
        "positive_fraction": float((x > 0).mean()),
        "zero_fraction": float((x == 0).mean()),
    }, {
        "seed": seed_for(c, scope, ids),
        "valid_resamples": valid,
        "degenerate_resamples": deg,
        "runtime_ms": (time.perf_counter() - t0) * 1000,
    }


def wilson(values):
    x = np.asarray(values, float)
    n = len(x)
    w = int((x > 0).sum())
    if n == 0:
        return {
            "positive_n": 0,
            "n": 0,
            "positive_fraction": None,
            "wilson_lower": None,
            "wilson_upper": None,
        }
    p = w / n
    z2 = Z95 * Z95
    den = 1 + z2 / n
    center = (p + z2 / (2 * n)) / den
    margin = Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / den
    return {
        "positive_n": w,
        "n": n,
        "positive_fraction": p,
        "wilson_lower": max(0.0, center - margin),
        "wilson_upper": min(1.0, center + margin),
    }


def evaluate(candidate, history, at_time=None):
    t = dt(at_time or candidate["candidate_timestamp"])
    prior = sorted(
        [x for x in history if dt(x["terminal_timestamp"]) < t],
        key=lambda x: (x["terminal_timestamp"], x["candidate_identity"]),
    )
    scope, pool = select_pool(candidate, prior)
    ids = [x["candidate_identity"] for x in pool]
    vals = [float(x["realized_r"]) for x in pool]
    base = {
        "selected_scope": scope,
        "compatible_n": len(pool),
        "history_case_ids": ids,
        "history_realized_r": [str(x["realized_r"]) for x in pool],
        "wilson": wilson(vals),
        "legacy_similarity_used_for_admission": False,
        "max_neighbors_truncation_used": False,
        "trader_equation_controls_admission": False,
    }
    if len(pool) < MIN_N:
        return {
            **base,
            "status": "INSUFFICIENT_HISTORY",
            "sample_mean_r": None,
            "sample_std_r": None,
            "bootstrap_t_lower95": None,
            "bootstrap_t_upper95": None,
            "bootstrap_diagnostics": None,
        }
    st, diag = bootstrap_t(vals, candidate, scope, ids)
    if st is None:
        return {
            **base,
            "status": "INSUFFICIENT_HISTORY",
            "sample_mean_r": None,
            "sample_std_r": None,
            "bootstrap_t_lower95": None,
            "bootstrap_t_upper95": None,
            "bootstrap_diagnostics": diag,
        }
    return {
        **base,
        "status": "FAVORABLE" if st["ci95_lower"] > 0 else "UNFAVORABLE",
        "sample_mean_r": st["mean_r"],
        "sample_std_r": st["std_r"],
        "bootstrap_t_lower95": st["ci95_lower"],
        "bootstrap_t_upper95": st["ci95_upper"],
        "bootstrap_t_width95": st["ci95_width"],
        "bootstrap_diagnostics": diag,
    }
