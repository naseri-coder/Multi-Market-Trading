# Stage 12 — Auditable Brooks PAPER research cohort (nonproduction)

**Objective.** Stop confusing completed PAPER lifecycle programming with a
validated profitable strategy. The tool audits **all Stage-10 linked Brooks
PAPER signals for one local account** and joins source A7 signal/receipt
digests to immutable Stage-10 binding, Stage-3 risk and Stage-11 offline bar
journal. It reports outcome counts, mean/median net realized-R, fees,
slippage, win rate, profit factor and a *predefined* double-cost stress
scenario for **training, validation and untouched-claimed holdout periods**.

**It does NOT obtain independent provider candles**, backtest one year,
optimize trading thresholds, claim the holdout truly untouched, establish
market-feed authenticity, infer missing signals, place DEMO/LIVE orders,
send Telegram messages, reconcile MT5 or deploy. Even an attractive reported
sample cannot authorize core activation or publication.

## Exact immutable-study input

The operator supplies a checked-in or separately timestamped study protocol
JSON (example is a **synthetic study declaration**, not real data):

```json
{
  "schema_version": 1,
  "purpose": "offline_paper_cohort_diagnostic",
  "study_id": "synthetic-brooks-r1",
  "account_id": "paper-account-1",
  "provider": "kraken_futures_trade_public",
  "symbol": "PF_XBTUSD",
  "timeframe": "15m",
  "quote_currency": "USD",
  "window_start_utc": "2026-09-01T00:00:00+00:00",
  "training_end_utc": "2026-09-15T00:00:00+00:00",
  "validation_end_utc": "2026-09-30T00:00:00+00:00",
  "window_end_utc": "2026-10-10T00:00:00+00:00",
  "expected_signal_ids": ["brooks-stage10-fixture"],
  "dataset_origin": "synthetic_fixture",
  "dataset_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "protocol_frozen_before_outcomes": true
}
```

- `expected_signal_ids` MUST cover **every Stage-10 link for the account**,
  including unfilled, open and losers. Missing or extra links refuse the
  study. An account containing mixed symbols/providers/currencies or entries
  outside the declared window refuses the study; a cherry-picked subset is
  not accepted.
- The three partitions have contiguous, strictly ordered UTC boundaries.
  Classification is by *signal candle close*, not exit time, to prevent
  assignment based on outcome. The horizon is at most 400 days.
- The dataset source and SHA256 are **claims, not verified dataset
  provenance**; there is no raw provider-candle attestation or trusted
  publication timestamp. The operator-declared pre-registration flag is
  **not independently verifiable**. A hash doesn't prove historical
  independence or that the dataset wasn't changed after viewing PnL.
- The Stage-3 order, risk reservation, Stage-10 binding, original Brooks
  signal/receipt, Stage-11 bar count/order hash and terminal execution
  chain must agree. Missing, corrupted or contradictory evidence is
  **REFUSED**, not silently skipped.
- Open/unreplayed signals are counted in the denominator, never treated
  as winning or losing closed positions. Reported mean-R and win rate
  explicitly describe **closed PAPER trades only**; they are not
  portfolio return or a probability of success.
- Diagnostic eligibility requires 20 closed PAPER outcomes and zero
  incomplete outcomes. Even then the verdict remains
  `RESEARCH_ONLY_REAL_MARKET_PROVENANCE_UNVERIFIED` with
  `profitability_or_live_edge_proven=false`, because no provider-backed
  historical candles are authenticated. A higher score cannot override it.
- No multi-currency sum; one homogeneous quote currency per manifest
  account. Two-times-cost stress is a **predefined sensitivity scenario**,
  not a post hoc optimized alternative. No annualized compounding, Sharpe
  extrapolation or capital-growth claim is made.
- The Stage-12 tool opens both existing SQLite stores in read-only mode
  with `PRAGMA query_only=ON`. It never creates schemas, reruns strategy,
  sends events, modifies reservations, changes runtime toggles, or produces
  artificial backtest returns. Historical source vs PAPER store is NOT a
  distributed atomic snapshot; recheck on any conflicting custody.

## Run only in a private nonproduction environment

```bash
MMT_NONPRODUCTION=1 python -m naseri_markets.brooks_stage12_cli \
  --state-dir /private/offline-paper-state \
  --manifest /private/frozen-protocol.json \
  --ack-offline-research-only
```

The command prints a machine-readable report to standard output; operators
can independently save/redact the report. `MMT_PRODUCTION=1` or missing
explicit consent fail closed. Never paste private user/account data or raw
historical receipts into Telegram.

## Promotion policy

`STAGE12_OFFLINE_RESEARCH_AUDIT_PASS` means verified *software* provenance
checks and tests, not a real one-year backtest. Future actual research
requires an **independently collected, legally accessible, timestamped
market-data corpus**, full eligible-symbol universe and observed Brooks
signals including NO_SIGNAL decisions, frozen policies *before* holdout,
multiple nonoverlapping time periods and defensible live-DEMO reconciliation.
Another authorization is required; no bypass of exchange residency
restrictions. Existing main source, private NY First-Reversal core,
thresholds, risk limits, bot Telegram commands and servers remain unchanged.
