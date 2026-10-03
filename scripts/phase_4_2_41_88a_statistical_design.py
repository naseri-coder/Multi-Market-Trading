from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/phase_4_2_41_86_bootstrap_closed_cases_sep11.json"
OUT = ROOT / "artifacts/phase_4_2_41_88a_statistical_design.json"
data = json.loads(FIX.read_text())
cases = data["cases"]
r = np.array([float(x["realized_r"]) for x in cases], dtype=float)
old = np.array([int(x["current_hp_binary_outcome"]) for x in cases], dtype=int)
RNG = np.random.default_rng(42188)
Z95_ONE = 1.6448536269514722
Z975 = 1.959963984540054


def tcrit_one95(df: int) -> float:
    z = Z95_ONE
    v = float(df)
    return (
        z
        + (z**3 + z) / (4 * v)
        + (5 * z**5 + 16 * z**3 + 3 * z) / (96 * v * v)
        + (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / (384 * v**3)
    )


def t_ci90(x):
    x = np.asarray(x, float)
    n = len(x)
    m = float(x.mean())
    if n < 2:
        return [m, m]
    se = float(x.std(ddof=1) / math.sqrt(n))
    c = tcrit_one95(n - 1)
    return [m - c * se, m + c * se]


def bootstrap_ci(x, B=50000, seed=0):
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    n = len(x)
    means = np.empty(B, float)
    chunk = 2000
    for s in range(0, B, chunk):
        b = min(chunk, B - s)
        idx = rng.integers(0, n, size=(b, n))
        means[s : s + b] = x[idx].mean(axis=1)
    return {
        "ci90": [float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))],
        "ci95": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
        "lcb95_one_sided": float(np.quantile(means, 0.05)),
        "bootstrap_sd": float(means.std(ddof=1)),
    }


def winsor10(x):
    x = np.sort(np.asarray(x, float))
    n = len(x)
    k = int(math.floor(0.10 * n))
    if k < 1:
        return x.copy()
    y = x.copy()
    y[:k] = y[k]
    y[n - k :] = y[n - k - 1]
    return y


def wilson(w, total):
    if total <= 0:
        return [0.0, 0.0, 1.0]
    p = w / total
    z = Z975
    z2 = z * z
    den = 1 + z2 / total
    center = (p + z2 / (2 * total)) / den
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total) / den
    return [p, max(0.0, center - margin), min(1.0, center + margin)]


def desc(x, oldx=None, seed=0):
    x = np.asarray(x, float)
    b = bootstrap_ci(x, seed=seed)
    t = t_ci90(x)
    w = winsor10(x)
    wb = bootstrap_ci(w, seed=seed + 991)
    d = {
        "n": len(x),
        "mean_r": float(x.mean()),
        "median_r": float(np.median(x)),
        "std_r": float(x.std(ddof=1)) if len(x) > 1 else 0.0,
        "positive_fraction": float((x > 0).mean()),
        "zero_count": int((x == 0).sum()),
        "bootstrap": b,
        "t_ci90": t,
        "t_lcb95_one_sided": t[0],
        "winsor10_mean_r": float(w.mean()),
        "winsor10_bootstrap_ci90": wb["ci90"],
        "winsor10_lcb95_one_sided": wb["lcb95_one_sided"],
    }
    if oldx is not None:
        oldx = np.asarray(oldx, int)
        d["legacy_wilson95"] = wilson(int(oldx.sum()), len(oldx))
        d["legacy_event_win_fraction"] = float(oldx.mean())
    return d


def family(s):
    v = str(s).upper()
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


# fixed descriptive scopes
scopes = {
    "ALL": list(range(len(cases))),
    "LONG": [i for i, x in enumerate(cases) if x["direction"] == "LONG"],
    "SHORT": [i for i, x in enumerate(cases) if x["direction"] == "SHORT"],
    "15m": [i for i, x in enumerate(cases) if x["timeframe"] == "15m"],
    "1h": [i for i, x in enumerate(cases) if x["timeframe"] == "1h"],
    "LONG_15m": [
        i for i, x in enumerate(cases) if x["direction"] == "LONG" and x["timeframe"] == "15m"
    ],
    "SHORT_15m": [
        i for i, x in enumerate(cases) if x["direction"] == "SHORT" and x["timeframe"] == "15m"
    ],
}
for fam in sorted({family(x["setup_type"]) for x in cases}):
    ix = [i for i, x in enumerate(cases) if family(x["setup_type"]) == fam]
    if len(ix) >= 8:
        scopes["FAMILY_" + fam] = ix
for setup in sorted({x["setup_type"] for x in cases}):
    ix = [i for i, x in enumerate(cases) if x["setup_type"] == setup]
    if len(ix) >= 8:
        scopes["SETUP_" + setup] = ix
scope_stats = {
    k: desc(r[ix], old[ix], seed=4218800 + j) for j, (k, ix) in enumerate(scopes.items())
}

# sample-size stability: random subsets without replacement from frozen 72.
stability = {}
for n in (8, 12, 20, 30, 40, 72):
    if n == 72:
        subsets = [np.arange(72)]
    else:
        subsets = [RNG.choice(72, n, replace=False) for _ in range(5000)]
    means = np.array([r[ix].mean() for ix in subsets])
    # CI width sensitivity on first deterministic 250 subsets (or full n=72)
    sel = subsets[:250] if n < 72 else subsets
    widths = []
    lcbs = []
    for j, ix in enumerate(sel):
        bb = bootstrap_ci(r[ix], B=3000, seed=880000 + n * 1000 + j)
        widths.append(bb["ci90"][1] - bb["ci90"][0])
        lcbs.append(bb["lcb95_one_sided"])
    stability[str(n)] = {
        "subsample_mean_sd": float(means.std(ddof=1)) if len(means) > 1 else 0.0,
        "subsample_mean_p05": float(np.quantile(means, 0.05)),
        "subsample_mean_p95": float(np.quantile(means, 0.95)),
        "subsample_positive_mean_fraction": float((means > 0).mean()),
        "median_bootstrap_ci90_width": float(np.median(widths)),
        "p90_bootstrap_ci90_width": float(np.quantile(widths, 0.9)),
        "fraction_lcb95_above_zero": float((np.array(lcbs) > 0).mean()),
    }

# pooling distortions via bootstrap difference of means


def diff_boot(ix1, ix2, B=50000, seed=1):
    a = r[ix1]
    b = r[ix2]
    rng = np.random.default_rng(seed)
    vals = np.empty(B)
    chunk = 2000
    for s in range(0, B, chunk):
        q = min(chunk, B - s)
        ia = rng.integers(0, len(a), size=(q, len(a)))
        ib = rng.integers(0, len(b), size=(q, len(b)))
        vals[s : s + q] = a[ia].mean(1) - b[ib].mean(1)
    return {
        "mean_difference": float(a.mean() - b.mean()),
        "ci95": [float(np.quantile(vals, 0.025)), float(np.quantile(vals, 0.975))],
    }


pool_diffs = {
    "LONG_minus_SHORT": diff_boot(scopes["LONG"], scopes["SHORT"], seed=101),
    "15m_minus_1h": diff_boot(scopes["15m"], scopes["1h"], seed=102),
    "LONG15m_minus_SHORT15m": diff_boot(scopes["LONG_15m"], scopes["SHORT_15m"], seed=103),
}

# estimator sensitivity/outlier effect: remove max positive one at a time / winsor diagnostic
all_base = desc(r, old, seed=999)
maxi = int(np.argmax(r))
min_i = int(np.argmin(r))
sensitivity = {
    "full": all_base,
    "without_max_positive": desc(np.delete(r, maxi), np.delete(old, maxi), seed=1001),
    "without_one_max_loss": desc(np.delete(r, min_i), np.delete(old, min_i), seed=1002),
    "max_positive_r": float(r[maxi]),
    "max_loss_r": float(r[min_i]),
}

result = {
    "phase": "4.2.41.88A",
    "input_fixture": str(FIX),
    "input_sha256": hashlib.sha256(FIX.read_bytes()).hexdigest(),
    "case_count": len(cases),
    "statistics_contract_version_proposed": "brooks-v5v6-realized-r-bootstrap-lcb95-v1",
    "primary_candidate_estimator": (
        "mean_realized_r_with_one_sided_95pct_"
        "nonparametric_bootstrap_lower_confidence_bound"
    ),
    "neutral_boundary_r": 0.0,
    "scope_stats": scope_stats,
    "sample_size_stability": stability,
    "pooling_differences": pool_diffs,
    "estimator_sensitivity": sensitivity,
}
OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
print("INPUT_SHA", result["input_sha256"], "N", len(cases))
print("ALL", json.dumps(scope_stats["ALL"], sort_keys=True))
print("---STABILITY---")
for k, v in stability.items():
    print(k, json.dumps(v, sort_keys=True))
print("---SCOPES---")
for k, v in scope_stats.items():
    print(k, json.dumps(v, sort_keys=True))
print("---POOL DIFFS---", json.dumps(pool_diffs, sort_keys=True))
print("---SENSITIVITY---", json.dumps(sensitivity, sort_keys=True))
print("OUT", OUT, "SHA256", hashlib.sha256(OUT.read_bytes()).hexdigest())
