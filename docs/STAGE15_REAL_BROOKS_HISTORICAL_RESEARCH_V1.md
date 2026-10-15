# Stage 15 — Real SHA-pinned Brooks V5 on Historical Research Windows

**Status: REAL CORE EXECUTION — SYNTHETIC TEST CANDLES / UNATTESTED ARCHIVE — RESEARCH ONLY**

## Scope and critical outcome boundary

Stage 13 and 14 research backtest and cost-robustness runners use the internal `OfflineContractFixture`, **not** a tradable strategy. In contrast, the historical public legacy source already contains the actual Al Brooks V5 full-core model. Existing `naseri_markets/brooks_replay.py` verifies its 359-file manifest plus three separately pinned extra modules and runs the actual engine inside a child Python interpreter. Its `replay_once()` writes to a dedicated offline PAPER signal ledger, so it is **not** an appropriate direct callable for research-only read paths.

Stage 15 provides one new bounded **no-ledger research bridge**, `review_real_brooks_history`. It reuses the EXISTING Stage-12 pinned CSV/Parquet archive quality check, DATA-A1 loader, Brooks source SHA verifier, native Brooks replay snapshot normalization, and actual V5 child worker. It never uses Stage-13's fake fixture, changes the legacy Brooks engine, adds a new strategy, rewrites a trade setup, tunes a threshold, calls PAPER order code, or turns on any protected public core.

### What is truly executed?

The exact existing frozen Brooks engine `BrooksTrilogyFullCoreEngine.evaluate(MarketSnapshot)`, with actual `BrooksFullCorePolicy(enable_trade_decisions=True)`, is imported and called **inside the existing child worker**, limited to three operator-declared snapshot close times.

Its actual decision may be `NO_SIGNAL`, `LONG` or `SHORT`. It is **not** simulated or replaced with a forced signal. No market order is submitted, no Telegram message is sent, and the output is not booked as a trade or treated as a live recommendation. The parent verifies full pinned legacy source identity, worker engine version, snapshot ID/hash for exactly the visible data, rule/config evidence, and — if any entry decision exists — valid stop/target geometry. The research output provides decisions, rule evidence digests and deterministic overall SHA-256.

The user-facing output contains no price-based PnL, no funding estimate, no Sharpe/PBO/DSR, no strategy selection, no trading edge, no success-rate forecast and no capital allocation advice.

### Strictly bounded input

- Complete `HistoricalFileSpec`; source file must be a complete contiguous timestamped UTC DATA-A1 archive, with its original byte SHA and operator pinned receipt.
- Original Stage-12 `inspect_historical_pit_archive()` including exact instrument/contract claim, as-of cutoff, candle availability lag, expected sample count and declared acquisition timestamp. The receipt is **operator supplied** and **does not authenticate** a real venue.
- Exact reviewed identity in this narrow first version: `provider=binance_replay`, `symbol=BTCUSDT`, `timeframe=15m`, `quote_currency=USDT`; operator-provided `contract_kind=linear_perpetual`. The real worker constructs `exchange=binance`, `market_type=futures`. This is a strict research fixture identity. **It is not evidence that the file was actually exported from Binance or that Binance Futures historically offered the contract in that exact form.**
- Exact on-disk authoritative `production_source` (SHA256SUMS digest `1a15f9d4b40b07c05186d27f694f9ce71cd007dd5047a35b25b6811f9bc67335`). The original source and SHA256SUMS remain untouched. Never upload this production source tree to a separate third-party server for convenience.
- 60–512 validated historical bars; each evaluated snapshot holds only the last 60–256 bars, and at most three strictly increasing **predeclared UTC bar-close cutoff times**. Every cutoff must coincide exactly with an observed closed bar and occur after at least 60 valid source bars. The worker receives only history ending at that cutoff — never the next bar's prices.
- Explicit local `MMT_NONPRODUCTION=1` and `operator_ack=True`; `MMT_PRODUCTION=1` always refuses. Frozen-source worker timeout bounded to 1–60 seconds per snapshot. No network calls are made by this research wrapper, but its subprocess is **not a proof of OS-enforced network isolation**.

### Local operator API

```python
from pathlib import Path
from datetime import UTC, datetime
from naseri_markets.real_brooks_historical_stage15_v1 import (
    review_real_brooks_history,
)

report = review_real_brooks_history(
    archive=Path("/owner-private/research/binance_15m.csv"),
    spec=reviewed_historical_file_spec,
    receipt_bytes=pinned_stage12_receipt_bytes,
    trusted_receipt_sha256=receipt_sha256_from_approved_inventory,
    archive_as_of_utc=reviewed_archive_timestamp_after_final_bar,
    legacy_source=Path("/reviewed-checkout/production_source"),
    evaluation_cutoffs_utc=(
        datetime(2026, 1, 1, 15, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
    ),
    operator_ack=True,
)
assert report["actual_brooks_engine_evaluated"] is True
assert report["actual_exchange_data_authenticated"] is False
assert report["walk_forward_backtest_run"] is False
```

The example absolute paths are placeholders; they must be replaced with actual reviewed local paths. Do not use a production-server directory or secrets.

## Why Stage 15 does NOT yet establish a real trading backtest

Two independent blockers remain:

1. **Market data custody:** No independently timestamped, signed or authenticated historical venue dataset has been supplied as an authoritative research artifact. The CI file is **synthetic flat OHLC candles** intentionally modeled after existing public Brooks integration tests. Stage-12 data quality checks can validate bytes, time grid and local assumptions, but not independently attest provider identity or historical revisions. Official venue archives would need independently reproducible retrieval metadata, instrument-contract history, source signature/witness and a genuinely later blind holdout.
2. **Execution economics:** The reviewed actual Brooks core returns an entry intent/geometry for only a handful of snapshots. This Stage-15 bridge **does not place positions or compute trade PnL**, fee tiers, funding/mark/index, exchange-specific futures multiplier, realized slippage, margin/liquidation, liquidity or brokerage constraints. It does not train candidates or walk-forward fit Brooks. Consequently the Stage-13 single synthetic fixture's PnL must NOT be attributed to Brooks.

The preceding Stage-14 repeated stress runs disclosed their final holdout; it cannot be reused as a fresh, blind OOS test. Source SHA pinning and reproducible V5 invocation prove **code identity and actual local execution**, not that the strategy has a profitable edge.

## Stage 15 acceptance

Dedicated tests must actually run the original frozen Brooks V5 child twice from approved SHA-pinned synthetic CSV with **two distinct increasing candle-close windows**, cross-check each snapshot against the exact parent-calculated hash, prove the two runs are identical, prove original dataset bytes untouched, and check that no PAPER ledger file is created. Negative tests reject wrong future cutoffs, warmup deficiency, duplicate/out-of-order cuts, unapproved venue symbol, spot/futures mismatch, tampered dataset bytes, invalid source tree, production environment, invalid geometry and forged worker output. Existing Brooks real replay and DATA-A1/Stage-12 tests remain unaffected.

CI must include targeted Stage-15 real worker tests, DATA-A1 and Stage-12 regressions plus full original protected GitHub workflow corpus, PostgreSQL and publication fences. Only after **every check on the current PR head** is green may this isolated four-file PR be squash merged.

**Stop after this stage.** No authenticated real-provider data backtest, strategy fitting, license/host provisioning, server access, production change, public Brooks activation or Stage-16 step is authorized here.

**Verdict: `STAGE15_REAL_BROOKS_V5_EXECUTED_ON_SYNTHETIC_HISTORY__AUTHENTIC_DATA_AND_ECONOMICS_PENDING`**, and **LIVE/PUBLIC RELEASE UNAUTHORIZED**.
