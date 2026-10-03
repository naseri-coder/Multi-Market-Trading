from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

from app.modules.signal_intelligence.probability import (
    _MIN_BROAD,
    _MIN_EXACT,
    _MIN_FAMILY,
    _setup_family,
    _wilson,
)

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests/fixtures/phase_4_2_41_86_bootstrap_closed_cases_sep11.json").read_text()
)["cases"]
CANDS = json.loads(
    (ROOT / "tests/fixtures/phase_4_2_41_86_bootstrap_candidates_sep11.json").read_text()
)["candidates"]
MATRIX = []
for i, r in enumerate(CASES, 1):
    rr = float(r["realized_r"])
    old = int(r["current_hp_binary_outcome"])
    diag = 1 if rr > 0 else (0 if rr < 0 else None)
    MATRIX.append(
        {
            "case_no": i,
            "candidate_identity": r["candidate_identity"],
            "symbol": r["symbol"],
            "timeframe": r["timeframe"],
            "direction": r["direction"],
            "setup_type": r["setup_type"],
            "terminal_event": r["terminal_event"],
            "terminal_timestamp": r["terminal_timestamp"],
            "realized_r": r["realized_r"],
            "old_repository_outcome": old,
            "diagnostic_sign_outcome": diag,
            "changed": diag != old,
        }
    )


# walk-forward exact pool selection; pool sizes here < 40 so
# nearest-neighbor cap does not alter scope samples materially for
# diagnostics.
def choose_pool(c, prior):
    setup = c["setup_type"]
    tf = c["timeframe"]
    direction = c["direction"]
    family = _setup_family(setup)
    exact_tf = [x for x in prior if x["setup_type"] == setup and x["timeframe"] == tf]
    exact = [x for x in prior if x["setup_type"] == setup]
    fam_tf = [x for x in prior if _setup_family(x["setup_type"]) == family and x["timeframe"] == tf]
    fam = [x for x in prior if _setup_family(x["setup_type"]) == family]
    dt = [x for x in prior if x["direction"] == direction and x["timeframe"] == tf]
    broad = [x for x in prior if x["direction"] == direction]
    if len(exact_tf) >= _MIN_EXACT:
        return exact_tf, "SETUP_TIMEFRAME", _MIN_EXACT
    if len(exact) >= _MIN_EXACT:
        return exact, "SETUP_ALL_TIMEFRAMES", _MIN_EXACT
    if len(fam_tf) >= _MIN_FAMILY:
        return fam_tf, "FAMILY_TIMEFRAME", _MIN_FAMILY
    if len(fam) >= _MIN_FAMILY:
        return fam, "FAMILY_ALL_TIMEFRAMES", _MIN_FAMILY
    if len(dt) >= _MIN_BROAD:
        return dt, "DIRECTION_TIMEFRAME", _MIN_BROAD
    return broad, "DIRECTION_ALL_TIMEFRAMES", _MIN_BROAD


WF = []
for n, c in enumerate(CANDS, 1):
    prior = [x for x in CASES if x["terminal_timestamp"] < c["candidate_timestamp"]]
    pool, scope, minimum = choose_pool(c, prior)
    calibrated = len(pool) >= minimum
    row = {
        "candidate_no": n,
        "identity": c["identity_sha256"],
        "timestamp": c["candidate_timestamp"],
        "symbol": c["symbol"],
        "timeframe": c["timeframe"],
        "direction": c["direction"],
        "setup_type": c["setup_type"],
        "prior_closed_total_old": len(prior),
        "scope": scope,
        "required_sample_size": minimum,
        "compatible_case_count": len(pool),
        "calibrated": calibrated,
    }
    if calibrated:
        oldwins = sum(int(x["current_hp_binary_outcome"]) for x in pool)
        econ = [x for x in pool if float(x["realized_r"]) != 0]
        econwins = sum(float(x["realized_r"]) > 0 for x in econ)
        old = _wilson(oldwins, len(pool))
        new = _wilson(econwins, len(econ)) if econ else (0, 0, 0)
        rr = [float(x["realized_r"]) for x in pool]
        row.update(
            {
                "old_empirical": old[0],
                "old_wilson_lower": old[1],
                "old_wilson_upper": old[2],
                "diagnostic_denominator": len(econ),
                "diagnostic_empirical": new[0],
                "diagnostic_wilson_lower": new[1],
                "diagnostic_wilson_upper": new[2],
                "mean_realized_r": statistics.mean(rr),
                "median_realized_r": statistics.median(rr),
            }
        )
    WF.append(row)
summary = {
    "phase": "4.2.41.87",
    "decision": "BINARY_MODEL_SEMANTICS_INADEQUATE_FOR_V6",
    "case_count": len(CASES),
    "false_losses_corrected_diagnostic": sum(
        x["old_repository_outcome"] == 0 and x["diagnostic_sign_outcome"] == 1 for x in MATRIX
    ),
    "breakeven_excluded_diagnostic": sum(x["diagnostic_sign_outcome"] is None for x in MATRIX),
    "negative_preserved_loss": sum(
        x["diagnostic_sign_outcome"] == 0 and x["old_repository_outcome"] == 0 for x in MATRIX
    ),
    "old_wins": sum(x["old_repository_outcome"] == 1 for x in MATRIX),
    "old_losses": sum(x["old_repository_outcome"] == 0 for x in MATRIX),
    "diagnostic_positive": sum(x["diagnostic_sign_outcome"] == 1 for x in MATRIX),
    "diagnostic_negative": sum(x["diagnostic_sign_outcome"] == 0 for x in MATRIX),
    "diagnostic_zero": sum(x["diagnostic_sign_outcome"] is None for x in MATRIX),
    "terminal_counts": dict(Counter(x["terminal_event"] for x in MATRIX)),
    "calibrated_candidates": sum(x["calibrated"] for x in WF),
    "insufficient_candidates": sum(not x["calibrated"] for x in WF),
    "scope_counts": dict(Counter(x["scope"] for x in WF if x["calibrated"])),
}
first = next((x for x in WF if x["calibrated"]), None)
summary["first_calibrated"] = first
# material contradiction: event-name win rate <10% but mean R > +0.05, or >50% but mean R < -0.05
contr = [
    x
    for x in WF
    if x["calibrated"]
    and (
        (x["old_empirical"] < 0.10 and x["mean_realized_r"] > 0.05)
        or (x["old_empirical"] > 0.5 and x["mean_realized_r"] < -0.05)
    )
]
summary["material_contradiction_count"] = len(contr)
# realized distribution
pos = [float(x["realized_r"]) for x in CASES if float(x["realized_r"]) > 0]
neg = [float(x["realized_r"]) for x in CASES if float(x["realized_r"]) < 0]
summary["positive_r"] = {
    "n": len(pos),
    "mean": statistics.mean(pos),
    "median": statistics.median(pos),
    "min": min(pos),
    "max": max(pos),
    "stdev": statistics.pstdev(pos),
}
summary["negative_r"] = {
    "n": len(neg),
    "mean": statistics.mean(neg),
    "median": statistics.median(neg),
    "min": min(neg),
    "max": max(neg),
    "stdev": statistics.pstdev(neg),
}
out = {
    "summary": summary,
    "before_after_matrix": MATRIX,
    "walk_forward_scope_diagnostics": WF,
    "material_contradictions": contr,
}
path = ROOT / "artifacts/phase_4_2_41_87_architecture_audit.json"
path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
csvp = ROOT / "artifacts/phase_4_2_41_87_72_case_matrix.csv"
with csvp.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=MATRIX[0].keys())
    w.writeheader()
    w.writerows(MATRIX)
print("SUMMARY", json.dumps(summary, sort_keys=True))
print("AUDIT", path, "SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
print("MATRIX", csvp, "SHA256", hashlib.sha256(csvp.read_bytes()).hexdigest())
print("BREAKEVEN_ROWS", [x for x in MATRIX if x["diagnostic_sign_outcome"] is None])
