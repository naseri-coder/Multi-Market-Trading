# Stage 5 — Original Offline PBO / Deflated Sharpe Diagnostics V1

**MODE: RESEARCH-ONLY · OFFLINE · NO STRATEGY EXECUTION OR PRODUCTION CHANGES**

This stage complements, but does **not** replace or modify, the existing Stage-11 Strategy Research Lab and Stage-4 time-purged Walk-Forward auditor. The existing Stage-11 outputs, CLI and provenance checks remain untouched. This separate module accepts **complete multi-candidate net portfolio returns** on synchronized equal-length periods. Per-trade R-values for a single core are *not* a valid cross-strategy Sharpe matrix.

## Input evidence and scope contract

An explicitly operator-prepared JSON file with these **exact** root keys:

- `schema_version`: integer 1.
- `study_id`: bounded ASCII research identifier.
- `candidate_ids`: alphabetically sorted, unique IDs of all 3–16 candidates.
- `selected_candidate_id`: one member of that inventory, supplied by operator, not selected by the tool.
- `declared_total_trials`: exact candidate count; `trial_inventory_complete`: literal true. **Every previously tried and rejected strategy/parameter combination is part of the search inventory**. Without a complete inventory and matched return series, this study must not be presented as meaningful. The claim is not independent proof of its completeness.
- `cscv_blocks`: even integer in {4, 6, 8, 10, 12}; contiguous equally-sized blocks, at least 8 periods each and at least 48 observations total.
- `reserved_holdout_start_utc`: separate UTC time boundary; all provided periods **must end no later** than this boundary. No final holdout returns are read.
- `rows`: chronological, gapless and nonoverlapping periods. Every row has exact `period_start_utc`, `period_end_utc` and `net_return_fraction` fields; every candidate has a bounded finite decimal **string** such as `"0.001"` or `"-0.002"`. Candidate returns are **per-period NET portfolio return fractions**, not gross returns or per-trade R. Zero positions must contribute zero-period returns. Use same risk/capital definition, costs and horizon for all candidates.

Missing rows, candidate samples, timestamp provenance, non-UTC timestamps, floating-point JSON values, NaN, infinity, zero variance, uncontrolled input size, mismatched widths, a final holdout crossing or stale/partial trial inventories cause **fail-closed refusal**.

## PBO — combinatorially symmetric CV

Enumerate all combinations of half the time blocks for in-sample and their complements for out-of-sample (`C(12,6)=924` maximum splits). For each split:

1. Calculate each candidate's **unannualized per-period Sharpe** (mean / sample standard deviation) on training blocks only.
2. Identify the unique IS best; ties are refused rather than resolving them in favor of a particular candidate.
3. Rank that candidate on the OOS blocks against the whole candidate inventory. Equal OOS scores use midranks; relative rank divides by `N+1`, protecting against singular logits.
4. `PBO = count(OOS rank logit <= 0) / all splits`. Never silently drop a difficult or losing split.

**This CSCV estimate is not chronological forward testing.** Some IS combinations are later than their OOS complement. This is appropriate for a selection-bias diagnostic, but Stage-4 temporal validation, separate genuine walk-forward backtesting, and blind final holdout remain independently necessary.

## DSR — Bailey and López de Prado

All values use **per-period** Sharpe and sample count, not an annualized Sharpe mixed with raw periodic observations:

- `SR` = mean / sample standard deviation of the operator-selected candidate.
- `sigma_SR` = sample standard deviation across the Sharpe estimates of all declared candidates.
- `SR_star` = `sigma_SR * ((1-gamma) * Phi^-1(1-1/N) + gamma * Phi^-1(1-1/(N*e)))`, where `gamma` is the Euler–Mascheroni constant and `N` is the full declared trial count.
- `g3` = selected candidate return skewness; `g4` = **raw** kurtosis, normal approximately 3.
- `DSR = Phi((SR - SR_star) * sqrt(T-1) / sqrt(1 - g3*SR + ((g4-1)/4)*SR^2))`.

Undefined variance or a nonpositive normalization term **refuses the study**, not silently replaces values with a positive epsilon. The results are statistical **diagnostics** and not calibrated probabilities of investment returns.

## Practical invocation

The JSON must contain 48–960 contiguous equal-width net portfolio-return periods with complete candidate coverage. Example **one row only** (not a complete study):

```json
{
  "period_start_utc": "2026-01-01T00:00:00+00:00",
  "period_end_utc": "2026-01-01T01:00:00+00:00",
  "net_return_fraction": {
    "alpha": "0.001",
    "beta": "-0.002",
    "gamma": "0"
  }
}
```

Run with explicit nonproduction approval; CLI reads a bounded regular local file and prints a JSON report to stdout, with **no files written**:

```bash
PYTHONPATH=. python scripts/mmt_overfit_diagnostics_v1.py \
  --matrix /path/to/synthetic_study_matrix.json \
  --ack-research-only

python -m pytest -q tests/unit/test_research_overfit_diagnostics_v1.py
```

## Limitations and acceptance

The tool cannot prove that the operator listed every past trial, actually preregistered the selected candidate, obtained trustworthy provider data, avoided survivorship biases, included all transaction costs, corrected for serial correlation or preserved a truly blind holdout. Period returns may be statistically dependent; effective independent trial count may differ from declared raw count; Sharpe assumptions can fail under clustered volatility and heavy tails.

The report therefore always declares `readiness=DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF`, `historical_source_authenticated=false`, `selection_pre_registered_verified=false`, `trial_inventory_claim_not_independently_verified=true`, `serial_correlation_adjusted=false`, `holdout_rows_loaded=0`, and `trading_authorized=false`. High DSR or low PBO is **not** approval to publish a trading signal or activate live execution.

Historical formulas:
- Bailey and López de Prado (2014), *The Deflated Sharpe Ratio*: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Bailey et al., *Probability of Backtest Overfitting*: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

**Stage 5 only:** Add a pure module, read-only CLI, strict fixture-based tests, and documentation. No Production, DB, strategy change, security authority, credential handling, trading data download, release manifest mutation or further roadmap stage. All existing protected GitHub CI must pass before merge.
