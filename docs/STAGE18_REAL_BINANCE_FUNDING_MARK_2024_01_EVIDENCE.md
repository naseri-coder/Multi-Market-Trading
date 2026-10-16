# Stage18 — Real Binance BTCUSDT 2024-01 Funding and Mark Source Evidence

**Nonproduction research — source-consistent, not exchange-signed historical fact or executed-trade PnL.**

The first exact bounded primary-source probe succeeded on disposable GitHub Actions Runner `38803484348`, using official HTTPS with redirects refused and SHA-256 CHECKSUM companions. Original binary ZIP and CHECKSUM bytes are kept as a short-lived workflow artifact. The actual parsing module and tests then validate the source originals, not hand-written financial observations.

| Source | Observed original ZIP SHA256 | Structure |
| --- | --- | --- |
| USD-M BTCUSDT 2024-01 fundingRate | `3e0d30870672aa8f0f937881056e3cfd55913ae5c780cd50b33f2763aa0ba58e` | 93 records and one header; `calc_time,funding_interval_hours,last_funding_rate` |
| USD-M BTCUSDT 2024-01 markPriceKlines 15m | `aa64b8b765a37c28f11235f2f2ff59f8558b9ff62251315de8b789a22698c926` | 2976 complete mark bars and one header; 12 original columns |

Official URLs:

- https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip
- https://data.binance.vision/data/futures/um/monthly/markPriceKlines/BTCUSDT/15m/BTCUSDT-15m-2024-01.zip

The **exact archived funding timestamps have 15 small delays of 1–3 ms** relative to the 8-hour UTC funding boundary. A strict equality initially refused these genuine rows and CI caught it; the parser now accepts only 0–3 milliseconds, preserves every original offset by ordinal position and explicitly refuses larger shifts, missing events, duplicates, wrong rate magnitude, malformed original files, unusual ZIP members, mismatched checksum and unsafe Mark OHLC.

Funding at **2024-01-01T00:00:00Z** requires a December 2023 prior Mark candle. That candle is outside the month, so the parser deliberately excludes this one event from normalized January Stage18 economics and declares it as an excluded boundary. The 92 remaining events are mapped to the **close of the prior 15-minute Mark candle**. This is a price approximation to a settlement mark, **not verified tick-exact funding settlement**. Never mislabel the prior bar's close as the venue's precise settled mark.

The module emits the existing Stage18 input schemas: `funding_time_utc` schedule CSV and `funding_time_utc,funding_rate,mark_price` rows, plus a SHA-256 evidence report binding original Funding and Mark files, the 15 raw timestamp deltas, exclusions and normalized output digests. This is one provider's archived raw schedule. **Not independently audited by a second source.**

## Still unresolved (no Stage21 authorization)

- Trade-price bars are actual primary-source historical observations already reviewed in Stage17 (parent PR #300); Funding and Mark are from original public files now collected. BUT no independent Binance digital signature, independently witnessed January-2024 publication version or precise historical funding settlement mark.
- Contract exchange filters and tiered maintenance/liquidation requirements are not verified per event. Historical maker/taker fee tiers of an actual account are **private and unspecified**.
- Executable orderbook/depth, queue, adverse fill, latency, position state, fee receipts and actual Brooks entry-stop-target lifecycle are not validated. Model slippage assumptions do not prove fillability.
- Existing Stage20 checks two frozen real-Brooks decisions at predeclared cutoffs in synthetic replay. Neither a statistically powered retrospective OOS nor a pristine **prospective** blind holdout exists.
- Stage21 actual Forward/PAPER must remain **blocked** until these conditions can be demonstrated under separate explicit research approval. No production, Telegram, exchange account or bot source changes. Draft PR, no merge to main.

**Evidence label:** `STAGE18_REAL_FUNDING_MARK_SOURCE_CAPTURED_SOURCE_CONSISTENCY_REVIEW_PENDING` — not `FUTURES_ECONOMICS_CERTIFIED`.
