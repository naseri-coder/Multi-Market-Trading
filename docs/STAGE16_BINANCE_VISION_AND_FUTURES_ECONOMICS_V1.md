# Stage 16 — USD-M Historical Archive Intake and Bounded Futures Economics

**Mode: OFFLINE PREPARATION / NOT AUTHENTICATED EXCHANGE HISTORY / NOT A TRADING BACKTEST / NOT LIVE**

Parent: `main@da4cbc636f96223c58653edf79fee12b6e4a0af6`.

## Audited source and operational constraints

The official `binance/binance-public-data` documentation confirms that Binance publishes USD-M futures 12-column klines, archived as ZIP bundles alongside `.CHECKSUM` SHA-256 files, available in monthly and daily batches. The documentation also acknowledges that previously published archives can later be corrected. The operator must independently check the current official repository and applicable data terms before acquisition.

**Official source documentation:** https://github.com/binance/binance-public-data

**Official archive path pattern, this strictly pinned scope only:**

```text
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-YYYY-MM.zip
https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/15m/BTCUSDT-15m-YYYY-MM.zip.CHECKSUM
```

This stage's development environment could **not download the actual ZIP/CHECKSUM bytes directly**. Consequently, Stage-16 tests use generated ZIP fixtures which follow the documented 12-column Binance Vision futures kline format. **No genuine Binance price archive was ingested or authenticated in this implementation.** Do not represent synthetic fixture coverage as real exchange data evidence.

The current original Brokers V5 bridge in Stage 15 already executes the genuine SHA-pinned Brooks engine in an independent worker but accepts at most 512 historical bars per research call. DATA-A1 and Stage 12 already enforce OHLC/candle continuity, dataset SHA256 and self-reported historical archive as-of rules. The earlier Stage 21D KuCoin futures economics contract cannot be reused *as if* it were a Binance instrument contract; its explicit provider and contract geometry fences must not be weakened. Stage 21E KuCoin current Mark/Funding evidence is not Binance historical price custody.

## A. Operator-supplied official-format archive intake

`naseri_markets/binance_vision_archive_stage16_v1.py` provides `prepare_vision_monthly_um_15m()` with **no network or file writes**.

Operator independently supplies: ZIP bytes, sibling CHECKSUM bytes, separately approved SHA-256 pins for **each exact artifact**, year, month, UTC retrieval time and explicit nonproduction consent.

Full-file validation:

1. Exact trusted filename `BTCUSDT-15m-YYYY-MM.zip`; CHECKSUM must name and hash these exact ZIP bytes; both inputs and decompression bounded. Exactly one non-encrypted, non-symlink CSV member with the exact matching basename, no path traversal, no suspicious compression, no other ZIP members.
2. Exactly the complete UTC calendar month's 15-minute rows (including real month length and leap years), in exact chronological alignment. Twelve Binance USD-M kline columns, with optional recognized header only. Open timestamp is in **milliseconds**; Binance close timestamp is usually `open + 900000 - 1` milliseconds. Normalized research close time is the **next 15-minute boundary**, *not* the exchange's inclusive last millisecond.
3. Reject duplicate, missing, overlapping, future or unaligned candles; incorrect OHLC, volume/buy-volume contradictions, malformed fixed-point prices, inconsistent trade counts or mismatched checksums.
4. Produce **canonical DATA-A1 CSV bytes** and an accompanying **Stage-12 exact receipt**, including declared acquisition timestamp and original file SHA; SHA-256 evidence is deterministic. The conversion is pure and never writes a broker or exchange-facing file.
5. The receipt's `provider_claim=binance_replay` and `linear_perpetual` are *operator claims* from a reviewed archive format, not authenticated live instrument terms. The local CHECKSUM protects against accidental tampering but **is not a Binance digital signature**, and two self-approved hashes are not independent custody or trusted acquisition timing.

`select_reviewed_brooks_window()` explicitly derives only 60–512 *predeclared* consecutive bars from the verified full-month CSV. It rehashes the parent and its Stage-12 receipt, creates an independently hashed derived CSV plus a new Stage-12 receipt matching the cut window, and reports parent ZIP and CSV fingerprints. It never silently truncates 2,880 monthly bars to 512; the selection index and length are preserved. Selection was **not independently blinded** to trading outcomes.

```python
from naseri_markets.binance_vision_archive_stage16_v1 import (
    prepare_vision_monthly_um_15m, select_reviewed_brooks_window,
)
prepared = prepare_vision_monthly_um_15m(
    original_zip_bytes, original_checksum_bytes,
    expected_zip_sha256=operator_pinned_zip_sha,
    expected_checksum_sha256=operator_pinned_checksum_sha,
    year=2026, month=9, retrieved_at_utc=trusted_local_utc_clock,
    operator_ack=True,
)
window = select_reviewed_brooks_window(
    prepared, start_bar_index=0, count=72, operator_ack=True,
)
# Operator saves window.canonical_csv_bytes to an isolated, trusted path,
# uses window.csv_sha256 for HistoricalFileSpec, and supplies its
# window.stage12_receipt_bytes and receipt_sha256 to the existing Stage15 API.
assert window.stage15_brooks_evaluated is False
```

Stage-16 synthetic integration tests themselves additionally invoke **the actual frozen Brooks V5 worker** on the derived Stage-12 window. This tests the interface without producing claims about real prices, PnL, or trading edge.

## B. Explicit hypothetical USD-M cash flows

`naseri_markets/futures_economic_scenario_stage16_v1.py` provides one bounded **illustrative** linear USDT-settled futures accounting model, intentionally separate from Stage 21D's KuCoin product contract:

- Full exact JSON operator-supplied and SHA256-pinned *claimed* contract metadata: multiplier/base units per contract, quantity step, price tick, fee fraction, adverse-slippage fraction, margin-maintenance fraction and independently named upstream metadata digest.
- Exact positive Decimal size and tick-grid entry and exit, strictly increasing UTC timestamps and explicit long/short direction.
- Every provided `FundingMarkScenario` item has a strictly increasing settlement instant, a signed bounded funding rate and an explicit reference mark price at that instant; positive funding means long pays and short receives. Missing settlements cannot be inferred and **are not silently filled with zero**.
- Gross quote PnL, two modeled taker fees, adversarial notional-based slippage, signed funding cash flow and net scenario PnL. No maker rebates, account tier discounts or unverified price improvements.
- The output **always** sets `funding_history_completeness_attested=false`, `historical_mark_prices_authenticated=false`, `contract_metadata_authenticated=false`, `liquidation_margin_model_complete=false`, `connected_to_real_brooks_trades=false` and `backtest_profitability_proven=false`. A nonempty funding event list is **not** proof all events have been recorded. The maintenance margin parameter is structurally validated but **not** sufficient to model liquidation.

```python
from naseri_markets.futures_economic_scenario_stage16_v1 import (
    FundingMarkScenario, model_linear_usdm_research_scenario,
)
# Pinned operator hypothesis, NOT any approved Binance fee tier or trade.
scenario = model_linear_usdm_research_scenario(
    reviewed_metadata_bytes, expected_metadata_sha256=metadata_sha,
    side="long", quantity_contracts="1.000",
    entry_price="100.0", exit_price="110.0",
    entry_at=entry_utc, exit_at=exit_utc,
    funding_mark_events=(FundingMarkScenario(
        funding_utc, "0.001", "105.0"),),
    operator_ack=True,
)
assert scenario["backtest_profitability_proven"] is False
```

**No actual authenticated fee snapshot, complete historical Mark/index or funding archive has been collected or demonstrated.** This modeled arithmetic is a stress/plausibility tool only. Do not use it to justify leverage, liquidation, real broker orders or investment recommendations.

## Results and explicit release blockers

| Component | Expected acceptance |
| --- | --- |
| Actual Binance Vision ZIP/CHECKSUM obtained in this task | **BLOCKED — no direct acquisition** |
| Official-format test ZIP parsing, whole-month/UTC grid, SHA-256 and DATA-A1/Stage12 bridge | PASS required by CI |
| 60–512-bar real Brooks worker invocation on derived synthetic archive | PASS required by CI |
| Linear USD-M taker/slippage/funding scenario math | PASS required by CI |
| Independent exchange origin signature and acquisition clock | NOT ATTESTED |
| Historical archive revisions, instrument tick/lot changes | NOT EXCLUDED |
| All historical mark, index, funding, actual fees and liquidity | NOT VERIFIED |
| Margin/liquidation and realistic real futures PnL | NOT MODELED |
| Pre-registered, untouched real-market OOS sample | NOT AVAILABLE |
| Production/PAPER/live activation | NEVER AUTHORIZED |

Target code-acceptance state is `STAGE16_OFFLINE_ARCHIVE_FORMAT_AND_ECONOMICS_PREPARED__REAL_DATA_CUSTODY_PENDING`. **It must never be called `REAL_BROOKS_BACKTEST_PASS`.**

No program downloads from an exchange, deploys, writes to production, changes the old source digest/manifests, swaps the V5 policy, enables a public trading core, reads private API credentials, books position PnL or transmits Telegram. Strict GitHub CI and untouched original publication/legacy release fences are mandatory.

**Stop after Stage 16, even if all CI passes.** Later authenticated acquisition, independent custody, genuine market sample execution and full contract-economics backtest require explicit follow-up approval.
