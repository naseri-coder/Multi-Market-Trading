# Stage 19 — Actual Frozen Brooks V5 Causal Historical Backtest Preflight

**Status: IMPLEMENTED RESEARCH PREFLIGHT ONLY / NO AUTHENTICATED BACKTEST / NOT LIVE**

Parent is the Stage18 DRAFT `feature/stage18-futures-economics-reconciliation-v1` at `1c7903e57d520324e02581a4352393c2110a85c7`. That stage is itself stacked on the Stage17 DRAFT PR #300. This preparation must **not** merge to `main` until underlying authentic-data and economic-evidence gates are accepted.

## Scope actually completed

- Reuse **genuine SHA-frozen Brooks V5** subprocess, without changing any of the original engine, 359-entry manifest, 3 pinned extras or thresholds. The existing Stage15 bounded `review_real_brooks_history` remains the only decision-evaluation path. No synthetic strategy stub substitutes for Brooks in this layer.
- Require actual in-memory Stage17 archive capture object with its full verified month and exact retained original ZIP lineage. **In CI this is synthetic and the transport stubbed**, not a real Binance download.
- Require exact Stage16 derived 60–512-bar historical window, recreate it from the complete parent month and require byte-for-byte matching canonical CSV, receipt and on-disk archive. Unreviewed or changed window is refused.
- Require valid Stage18 modeled-economics report and its hash, matching original month SHA256. All its unsupported exchange-authentication, mark/funding/fees/margin/actual Brooks trade flags must remain false. No operator SHA creates a trusted venue signature.
- Require 1–3 *predeclared*, unique, increasing UTC closed candle cutoffs. The genuine frozen Stage15 source verification, full Stage12 historical PIT/local time quality and chronological worker checks apply to every cutoff. At least 60 historical bars must have closed when the worker runs.
- Record only the actual V5 `NO_SIGNAL` / `LONG` / `SHORT` decision, the exact visible candle count, input and decision evidence hashes, and whether a later candle exists in the recorded archive. The future candle's price is never exposed to the model.
- Return deterministic bounded source/dataset/economics/report SHA evidence and exact blockers. Never report a fill, stop/target execution, trading PnL, win rate or real strategy edge.

## What remains blocked

- **Stage17:** Official market archive unavailable from the current research runtime; even transport consistency does not prove independently authenticated publisher signature, trusted acquisition clock or no later archive revision.
- **Stage18:** Historical funding schedule, mark price observations, effective fee tier, order-book liquidity, slippage and tiered maintenance margin are still operator-asserted/unverified.
- **Brooks geometry → execution:** Stage15 only reports decisions and hashes. It intentionally does not expose validated entry/stop/target geometry in its public research receipt; Stage19 must **not** invent fills or infer a completed trade from a LONG/SHORT intent. A separate reviewed engine-geometry and causal order/position lifecycle adapter is necessary before a real economic backtest.
- **Prospective OOS:** No pristine future holdout, serial-dependence uncertainty or valid profitability claim.

This means the outcome is `STAGE19_REAL_BROOKS_CAUSAL_DECISION_PREFLIGHT_ONLY`, **not Stage19 real historical profitability validation**.

## Exact acceptance contract

PASS of the *code preparation* requires an actual frozen Brooks worker invocation with real original engine source on synthetic 72-bar windows, exact Stage17 → Stage18 → Stage16 → Stage15 SHA lineage, deterministic repeated output, no PAPER / Telegram / DB or production writes, failures for forged checksums, stale economics, changed window data, future/duplicate/unordered cuts and production mode. These tests are in `tests/unit/test_stage19_brooks_causal_backtest_preflight_v1.py`, run by the existing Public Test Corpus on GitHub.

This preparation should remain a Draft PR; require all protected GitHub checks, including CodeQL if configured, on its exact commit. Don't bypass the publication-safety gate for missing CodeQL, merge, start Stage20, deploy, alter strategy parameters or change any operational system.

## Research examples and limitation

Inputs to `review_stage19_brooks_causal_preflight` are a Stage17Capture and Stage16 VisionBrooksWindow, an **absolute local CSV path** holding the exact reviewed derived window bytes, a SHA-consistent Stage18 report JSON, the absolute frozen source checkout path, 1–3 predeclared UTC bar-close cutoffs and an explicit archive `as_of_utc`. Set `MMT_NONPRODUCTION=1` and `operator_ack=True`. The example synthetic archive is BTCUSDT USD-M 15m January 2024; its test prices, funding and scenario costs are entirely generated fixture values.

No actual venue data has been fetched, no actual Brooks trade is booked, and no historical futures PnL exists from this stage. Production remains unchanged.
