# MMT-DATA-A1 — Historical CSV & Parquet Loader (nonproduction)

**Status: GitHub-only research; strictly REPLAY, not a live market data feed.**

## Contract

`naseri_markets/historical_data_loader_a1.py` adds a bounded-memory reader
for actual historical price rows, accepting explicit `HistoricalFileSpec`
containing an existing Stage-5 `FeedDefinition` and the independently
operator-approved SHA-256 digest. Source_ref must equal
`hist_<first 40 characters of digest>`. Historical origin is always
`DataOrigin.REPLAY`; origin, provider, symbol, timeframe and price basis are
host-selected and **not** authenticated merely by reading the file.

**CSV and Parquet schemas are exact and ordered:**
- OHLCV bars: `open_at,close_at,open,high,low,close,volume` for explicit
  `TRADED` volume; or `tick_volume` for `TICK_COUNT`.
- Bid/Ask ticks: `occurred_at,bid,ask` (no candle OHLC or inferred spread).
- Datetimes: RFC3339/ISO8601 with an explicit timezone. Parquet may instead
  encode a timezone-aware timestamp. Decimal prices: exact decimal strings
  or Parquet decimal logical types, never binary floating-point conversion.
- All fields non-null. No extra provider/symbol/contract columns; identity is
  an explicit immutable `FeedDefinition` supplied by the platform.

## Full-file fail-closed checks

Full-file prevalidation completes **before** `ApprovedHistoricalReplay`
is returned. A streaming SHA-256 of the input must match the supplied pin.
No symlinks or special files; no mutable source assumed. Revalidation checks
file identity and digest before replay. Every row is checked for:
- Valid positive finite prices; nonnegative volume or strict integer tick count;
  valid high/low/open/close geometry, bid ≤ ask.
- UTC-normalized timezone-aware timestamps, strictly increasing source-time
  ordering, no duplicate or overlapping bars.
- Exact timeframe duration. Daily permits 23–25 hours for DST.
- **Strict contiguous bars:** unverified market session gaps, weekends and
  holidays are **rejected**, not filled or inferred as tradable. A later
  exchange-calendar plugin may permit independently verified breaks.
- Explicit pricing and volume basis. Crypto traded volume is not equated to
  FX broker tick count.
- Explicit configurable simulated replay availability delay; a synthetic
  receipt time is **not** proof of historical real-world data availability.

The decoded result uses existing typed `MarketPacket` objects from Stage 5.
`OfflineMarketDataEngine.ingest` can consume these and construct inert
`CoreInput` events after warm-up. **This module does not evaluate a core,
place orders, publish Telegram, or authorize authenticated FORWARD data.**

## Memory and file limits

- Read-only CSV uses `csv.DictReader`, no unbounded `read_bytes()`.
- Parquet uses optional `pyarrow.parquet.ParquetFile.iter_batches`
  (4096 rows/batch); explicit row-group size cap (64 MiB), no nested types.
- CSV maximum 512 MiB, Parquet maximum 1 GiB; at most 5,000,000 rows.
- Parquet decoding requires optional `pyarrow`, installed in a separately
  reviewed **CI/research** environment. No new production dependency.
- This is bounded-memory processing of local files, **not** an online upload
  API and not a server deployment. A correct SHA-256 is byte integrity,
  not a signed source authority or guarantee of Point-in-Time completeness.
- Source must remain **immutable** while replaying. File-system changes
  mid-iteration may yield partial *offline* packet streams; there is no
  transactional snapshot or rollback promise.

## Independent acceptance

`python -m pytest -q tests/unit/test_historical_data_loader_a1.py`

CSV unit cases run with project test dependencies. Real Parquet decode cases
require the explicitly isolated DATA-A1 workflow which installs PyArrow and
verifies that the targeted tests run with `-rs` (no Parquet skips).
The CI tests also verify Stage-5 ingestion and typed CoreInput emission,
malformed schema, gap, duplicate, digest mismatch, and no live flags.

## Explicitly deferred

No real provider API, source-attestation signature, instrument contract
metadata, arbitrary mapped provider schemas, session calendar, corporate
actions, funding, spreads beyond observed bid/ask, native big-file upload,
continuous/restartable replay checkpoint, isolated Parquet adversarial
sandbox, or strategy adapter is added. Those require separate stages.
Al Brooks, NYFR R0, First Follow-up, Public Custom, production_source,
server, Telegram, database and existing adapter-free runtime are unchanged.

**Verdict can be DATA_A1_OFFLINE_REPLAY_LOADER_PASS only after targeted
real-Parquet and full-repository checks pass.**


## DATA-A1 operator intake: real local files, typed offline PAPER delivery

The original DATA-A1 decoder already existed. A new research-only operator
front-end now accepts an actual on-disk CSV/Parquet file, checks it against a
previously approved SHA-256 and explicit source/symbol/timeframe semantics,
and validates every sample through Stage-5 OfflineMarketDataEngine.
This is file ingestion, not online source retrieval or uploading.

Example on an independent nonproduction machine with Python 3.12,
and PyArrow installed for Parquet:

~~~bash
MMT_NONPRODUCTION=1 python -m naseri_markets.data_a1_intake_cli \
  --file /absolute/path/to/previously-reviewed-history.csv \
  --sha256 YOUR_PREVIOUSLY_APPROVED_LOWERCASE_64_CHARACTER_SHA256 \
  --market crypto --provider declared_history_provider \
  --symbol BTCUSDT --timezone UTC --quote-currency USDT \
  --timeframe 15m --event closed_candle \
  --price-basis trade --volume-semantics traded \
  --availability-lag-seconds 0 --ack-offline-paper-only
~~~

For tick quotes use event quote_tick, price-basis bid_ask and
volume-semantics unknown with the exact occurred_at,bid,ask column set.
Historical bytes MUST be preserved immutable from validation to replay.
SHA-256 checks byte integrity only and does not independently prove
publisher identity, contract, source quality, market session calendar,
Point-in-Time availability or coverage.

The CLI requires MMT_NONPRODUCTION=1, absence of MMT_PRODUCTION=1, a
human acknowledgement and an absolute local file path. It creates no
network request, upload API, trading order, database write, Worker run or
Telegram delivery.

Only after FULL source validation and subsequent full replay does stdout
receive a single JSON report. The report contains operator-declared
provider, market, symbol, timeframe, quote currency and timezone, typed
price and volume bases, SHA-256, source identity, valid row counts, count
of generated paper-ready CoreInput values, observed and availability
timestamps, lowest/highest price, zero-volume count, and tick spreads.

The input is delivered via a read-only inspector CoreManifest bound to
the existing Stage-5 OfflineMarketDataEngine. It never calls strategy
evaluate, paper order placement or an execution adapter. It checks that
each CoreInput has no future candles, is REPLAY origin, and is available
no earlier than the last closed observation. The history ring has at
most 128 candles. All success/authority fields concerning source
attestation, genuine Point-in-Time data, order, Telegram, runtime launch
or executed strategy are explicitly FALSE.

A rejected file prints only DATA_A1_LOCAL_INTAKE_REFUSED on stderr.
A mutated or malformed source cannot produce partial successful stdout
reports. A file replaced during replay can produce partial in-memory
validation before refusal, but cannot trigger a strategy or an order.

The CI workflow exercises the **actual CSV and PyArrow Parquet parsers**
on test-generated files including multiple Parquet row groups, plus
positive and negative PAPER CoreInput tests. These fixtures are not
authenticated market-provider historical data; a separate end-to-end
study with user-supplied real market CSV/Parquet is still required.

No broker, Telegram, server, live database, Al Brooks/NYFR/private core,
or RUNTIME-A6 launch boundary is changed.
