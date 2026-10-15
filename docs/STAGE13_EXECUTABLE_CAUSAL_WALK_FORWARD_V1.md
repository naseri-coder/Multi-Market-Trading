# Stage 13 — Executable Causal Forward-Chaining Research Baseline

**NONPRODUCTION ONLY · ACTUAL TRUSTED CORE EVALUATION ON PINNED OFFLINE CSV/PARQUET · SYNTHETIC CORE FIXTURE · UNAUTHENTICATED ARCHIVE · NO LIVE/PUBLIC RELEASE**

## Why this stage exists

Earlier Stage 4 (`research_walk_forward_v1.py`) is a **post-hoc PAPER outcome auditor**, not an executable strategy backtest. Stage 12 introduced a bounded operator-asserted as-of archive *quality* gate, reusing DATA-A1. Neither previously called the strategy core on each historical fold.

Stage 13 introduces exactly one separate, bounded **research-only** runner in `naseri_markets/executable_walk_forward_stage13_v1.py`. It reuses:
- `HistoricalFileSpec` and DATA-A1's full pinned-file OHLC/continuity CSV/Parquet validation. Repeated checks and hash handling are inherited, not reimplemented.
- Stage 12's receipt and archive availability cutoff check. **The declared archive as-of time is later than the final historical candle.** Retrospective observations **cannot** prove market availability at earlier training/validation times. Independent acquisition clock/source custody remains false.
- Stage-5 `OfflineMarketDataEngine` generating bounded, chronological `CoreInput` windows per evaluation. Its `CoreEventType.CLOSED_CANDLE` discipline prevents the strategy seeing future OHLC when deciding.
- Universal Core API `OfflineCoreHarness` to **actually call `evaluate()`** on the explicitly reviewed **`OfflineContractFixture`**, with ABI validation, result provenance checks and quarantine on malformed decisions. This fixture is an internal contract test core, *not* a profitable or selectable public trading strategy.
- The existing research vocabulary of embargo and reserved final holdout without modifying prior Stage-4 or Stage-11 audit behavior.

**Do not infer from this baseline that public Brooks, NY First-Reversal or third-party cores have been backtested.** Arbitrary user-supplied source is not loaded or executed.

## Causal execution assumptions — fixed before processing

`FrozenExecutionPlan` requires explicit UTC training, validation, study-end and **later archive-as-of** timestamps, 2–8 forward validation folds, at least one embargo bar, initial model capital, one bounded notional allocation (0–100%), fixed per-side fee/slippage in basis points and a minimum closed-trade count **for diagnostic blocking only**.

1. The full file is structurally audited before any research evaluation. Data must be one immutable pinned, contiguous, UTC crypto trade-price candle series in the Stage-12 scope, max 5,000 bars. This does **not** establish actual exchange historical provenance.
2. Each expanding-origin validation fold is evaluated from a **fresh** Core harness and data engine. The training cutoff is **before** the test start minus the declared embargo. Every test segment has a fresh, independent position state and historical bars before the segment are available to the core for **lookback only**, not to open paper trades inside the test.
3. The **final holdout** is evaluated once and never included in any validation training cutoff. No parameter fitting or optimizer exists at this stage. Historical validation is replay, **not a prospective independently sealed test**.
4. A decision on a **closed bar** may not create a modeled fill until the **next bar's Open**. An invalid gap/stop geometry is recorded as a blocker, not silently repaired. Exactly one modeled position at a time per segment; conflicting entry intents are counted, not filled.
5. Stop and target evaluate on the actual next/successive OHLC bars. If both prices are inside one candle, **stop wins**. Long stops gap through at min(open,stop), short stops at max(open,stop). Entry and exit each incur adverse price slippage. Quantity is deterministic `initial_capital × notional_fraction / slipped_entry_price`, with no borrowed-margin/leveraged futures assumption. Per-side percentage fees on both fill notionals are subtracted. No funding or exchange-specific contract multiplier is modeled.
6. For every training/test/holdout segment, log counts for actual core evaluations, entry intents, fills, closed trades, busy entries, invalid stop geometry, stop-first ambiguity, pending/unresolved end-of-segment positions, gross PnL, fees, net PnL, mean normalized R and doubled-fee stress. **Pending/open trades are not omitted from evidence**: they become visible blockers. A minimum sample failure likewise produces a descriptive blocked verdict, **never a favorable performance label**.
7. Each segment returns a deterministic trade-evidence digest (not a customer journal) and the complete report has a deterministic SHA-256. This is local content integrity, **not a provider signature, experiment preregistration, source custody or investor performance attestation**.

### Explicitly excluded

The runner is **not** the live/PAPER order or risk ledger, does not mutate Stage 8/9/17/19/20 SQLite databases, and is not a production broker fill simulator. It does not support commissions in fee currency other than modeled quote units, maker/taker tiers, funding, mark/index basis, margin, liquidation, partial fills, stop-limit orders, trailing stops, trading-session gaps, contract size, capacity/impact, hedge offset or external provider fee receipts. Research is therefore restricted to **notional cash PnL for the synthetic long/short fixture**, and short outcomes are counterfactual rather than margin-backed short-sale validation.

Trade results are descriptive **only**. Any claim of realistic futures net profitability, actual exchange past as-of truth or out-of-sample statistically significant edge remains expressly prohibited.

## Trust and reproducibility

No data file is bundled or downloaded. To run, the operator separately prepares:
- a DATA-A1 historical file pinned by `HistoricalFileSpec`;
- the Stage-12 self-reported archive receipt with a separately approved SHA256;
- an explicit frozen `FrozenExecutionPlan`, including `archive_as_of_utc` after all close timestamps;
- `MMT_NONPRODUCTION=1` (and `MMT_PRODUCTION` not 1) plus `operator_ack=True`.

```python
from naseri_markets.executable_walk_forward_stage13_v1 import (
    FrozenExecutionPlan, execute_frozen_walk_forward,
)

# Times are UTC datetimes; values below represent operator-provided,
# precommitted local research inputs, not a live provider feed.
plan = FrozenExecutionPlan(
    training_end, validation_end, study_end, archive_as_of_utc,
    validation_folds=2, embargo_bars=1,
    fee_bps_per_side=Decimal("2"),
    slippage_bps_per_side=Decimal("3"),
    initial_capital=Decimal("1000"),
    notional_fraction=Decimal("0.1"),
    min_closed_per_segment=1,
)
report = execute_frozen_walk_forward(
    approved_absolute_path, approved_historical_file_spec,
    receipt_bytes=operator_receipt,
    trusted_receipt_sha256=separately_approved_receipt_digest,
    plan=plan, operator_ack=True,
)
assert not report["profitability_proven"]
```

**The purported plan freeze is not externally attested.** Altering plan or receipt is visible in the resulting evidence digest, but no trusted pre-outcome signature exists. Future stages may require a signed experiment log, venue-independent data witness, genuinely reviewed core adapter, wider scenario/risk model and prospectively held-out data before any profitability evaluation.

## CI acceptance and stop condition

Tests run deterministic synthetic trending/non-trending CSV archive through the existing validated Stage-12/DATA-A1 route, confirm **real Core.evaluate calls** through the inherited ABI (not slicing prewritten returns), next-bar-entry economics, adverse fee/slippage vs zero-cost, multiple actual expanding folds, embargo, final holdout, zero-trade blockers, no-future archive cutoff, malformed fold boundary, tampered source SHA and nonproduction-only behavior. Existing Stage-12/DATA-A1/research-walk-forward tests remain in scope. The focused suite must pass separately; full protected public/PostgreSQL/legacy-publication tests must pass on the exact PR head.

**No claim of live suitability or proven profit.** Even if green: `STAGE13_EXECUTABLE_SYNTHETIC_CORE_WALK_FORWARD_PASS__REAL_STRATEGY_AND_PIT_PROVENANCE_PENDING`.

**Hard stop after Stage 13.** No activation of a real user core, live broker, API fetch, Telegram, server restart or Stage 14 optimization without separate approval.
