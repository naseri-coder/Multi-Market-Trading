# Stage 12 — Point-in-Time Historical Dataset Quality & Provenance V1

**Status: OFFLINE RESEARCH CONTRACT / NO AUTHENTICATED REAL DATA / NO BACKTEST / NO BROKER OR TELEGRAM / NO PRODUCTION**

## Audited baseline

Parent SHA: `e6684cd2034435e36c4e5b0241ad40b3b7253dd0`. Existing public modules `historical_data_loader_a1.py`, `data_a1_file_intake.py`, `market_data_engine_v1.py`, `public_forward_capture_stage21c_v1.py` and Stage-21F evidence gate already perform substantial historical-data ingest, CSV/Parquet normalization, stream order/contiguity checks, SHA-256 byte pinning, declared latency and captured forward-replay research. **Do not duplicate or replace those adapters.**

The unresolved reproducibility gap is a **separately pinned, strict archive description** tied to the same source bytes, the first/last bars and an explicit **as-of availability decision**. A historical CSV downloaded *today* cannot magically prove what an exchange exposed at an earlier decision time. It is unsafe to infer acquisition time from bar timestamps.

Stage 12 adds one pure public research gate: `naseri_markets/historical_pit_quality_stage12_v1.py`. It **calls** the existing DATA-A1 `validate_historical_file()` (two-pass file hash, typed OHLC, contiguous chronological bars) and then rereads its validated packets, not a new decoder. It can check local causal *consistency*, never retrospective market-data authenticity.

## Exact bounded scope

For this initial phase, only **operator-provided UTC continuous CRYPTO trade-price CLOSED_CANDLE bars** are supported. One explicitly declared venue + instrument + timeframe per file, with exact bar grid, no missing minutes, sample-count match and window start/end agreement. Supported prices come from existing Stage-5/ DATA-A1 `Decimal` / volume checks. The apparent market provider, `spot` vs `linear_perpetual` contract kind, continuous UTC market calendar and archive acquisition timestamp are **operator assertions**, not externally verified facts. The function never adjusts prices, fills missing data, infers exchange sessions, merges spot and derivatives, converts funding/fees or upgrades confidence because the same provider can be fetched again.

**Inputs:**
- Already-created `HistoricalFileSpec` with typed `FeedDefinition` and prior host-supplied exact dataset SHA256. A valid source reference is `hist_` plus the leading forty hex characters of the dataset digest. The source file path must be absolute; symlinks and invalid formats are rejected by Stage 12 and DATA-A1.
- Separate, exact **JSON receipt** (max 8192 bytes), SHA256 pinned via `trusted_receipt_sha256` from a different operator/host-held reference. The receipt includes exact feed identity, provider claim, contract kind, declared market/price/volume semantics, SHA256 of source file, availability lag, **expected row count**, complete window boundary timestamps and **self-reported `retrieved_at_utc`**.
- A UTC-aware `as_of_utc` cutoff. Every closed candle must have `candle.close_at ≤ packet.received_at ≤ retrieved_at_utc ≤ as_of_utc`; the packet received time is the previously declared `candle.close_at + availability_lag_seconds`, **not** a network receipt timestamp. This is a local causal model, not an exchange-authenticated clock.
- Explicit `MMT_NONPRODUCTION=1`, no `MMT_PRODUCTION=1`, and `operator_ack=True`. Absent acknowledgments, malformed JSON, duplicate keys, float numbers, unknown receipt fields, mismatched hashes/symbols/provider, non-UTC/non-grid timestamps, unproved gaps and insufficient rows all fail closed.

**Strict receipt example:** All values are illustrative synthetic operator declarations; replace SHA values with real independently host-pinned digests. The **receipt checksum itself** is the SHA-256 of these exact UTF-8 bytes, not a checksum of a JSON reformatting.

```json
{
  "schema_version": 1,
  "dataset_sha256": "EXACT_SOURCE_SHA256",
  "feed_id": "stage12_crypto_history",
  "market": "crypto",
  "provider_claim": "fixture_venue",
  "symbol": "BTCUSDT",
  "timezone": "UTC",
  "quote_currency": "USDT",
  "timeframe": "15m",
  "event": "closed_candle",
  "price_basis": "trade",
  "volume_semantics": "traded",
  "contract_kind": "linear_perpetual",
  "session_policy": "continuous_utc_operator_assertion",
  "capture_method": "operator_supplied_archive",
  "availability_lag_seconds": 5,
  "expected_rows": 2,
  "window_start_utc": "2026-10-13T10:00:00Z",
  "window_end_utc": "2026-10-13T10:30:00Z",
  "retrieved_at_utc": "2026-10-13T10:31:00Z"
}
```

### Operator-only API

```python
from datetime import UTC, datetime
from naseri_markets.historical_pit_quality_stage12_v1 import inspect_historical_pit_archive

# The file, immutable HistoricalFileSpec, independent receipt and its SHA256
# must be provided explicitly by the already trusted local research operator.
report = inspect_historical_pit_archive(
    path_to_approved_csv_or_parquet, historical_file_spec,
    receipt_bytes=pinned_utf8_receipt,
    trusted_receipt_sha256=separately_approved_receipt_sha256,
    as_of_utc=datetime(2026, 10, 13, 10, 32, tzinfo=UTC),
    operator_ack=True,
)
assert report.result == "OFFLINE_PIT_LOCAL_CAUSALITY_PASS_SOURCE_UNATTESTED"
assert report.point_in_time_market_truth_certified is False
assert report.backtest_run is False
```

**Not a general data-lake manager.** There are no writes, downloads, retries, agents, scheduler, feeds, exchange requests, Telegram, signals, strategy evaluators, replays or new databases. A positive output is a **descriptive, bounded local historical consistency finding**; there is no public release authority. All authorization/publisher/provider authenticity, contractual eligibility, as-known-at historical revisions, maintenance outages, complete futures fee/funding/mark prices, survivorship and economic adjustment remain **NOT VERIFIED**.

## Critical distinction: retrospective bar tests versus genuine Point-in-Time observation

With a declared `retrieved_at_utc` after the intended decision `as_of_utc`, the archive cannot be admitted as genuine `as-of` evidence, even if all candles fall earlier. If an archive is only downloaded after the research experiment, it can still be evaluated with DATA-A1 as **retrospective replay**, but Stage 12 **must refuse** its stronger local as-of check. Neither mode proves no historical provider revisions or no survivorship bias. A user pinning their own newly created receipt is **not** independent time attestation and cannot qualify the dataset for a verified historical edge claim.

The observation receipts should eventually be anchored by an independent trusted acquisition service with signed time and producer identity, versioned instrument/corporate-action catalog, source API metadata and reproducible exchange-calendar tests. Without that evidence, `acquisition_clock_independently_attested` and `point_in_time_market_truth_certified` must remain false.

## Acceptance and strict Stop Gate

Focused tests exercise synthetic two-bar archive, reproducible SHA256 fingerprints, local quality and zero-volume sample, late-acquired archive refusal, mismatched provider/contract/window, missing/extra rows, gap and invalid OHLC, duplicate JSON fields, future/unavailable source, symlink/relative file, wrong UTC offset, unaligned candle start and subsecond boundary, denied mark/bid-ask/forex, production denial and no strategy/broker/Telegram grant.

- Full existing DATA-A1 tests and this new focused suite must run isolated from legacy `tests/conftest.py` through a disposable test directory; all existing protected CI (full public corpus, PostgreSQL, legacy release and publication safety) remain mandatory.
- No production code, previous source trees, existing historical adapters, manifests/lockfiles, risk thresholds, DB schema or server changes.
- A CI success only means **tested offline contracts pass**, not that the project has acquired an authenticated exchange historical dataset or completed a real-money backtest.
- Do **not** begin the next roadmap phase (causal execution backtest / true walk-forward) until the user explicitly approves it.

**Expected state:** `STAGE12_LOCAL_POINT_IN_TIME_RESEARCH_GATE_PASS__SOURCE_AUTHENTICITY_PENDING`, not product or LIVE readiness.
