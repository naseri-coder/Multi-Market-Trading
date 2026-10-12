# Stage 21A — KuCoin Futures public candle acquisition and offline REPLAY

**Status: nonproduction, bounded read-only data intake candidate. Not a live feed, LIVE execution, Telegram publication, broker trial, or completed real-data PAPER pilot.**

## Trusted source and boundaries

The official KuCoin Futures [Get Klines](https://www.kucoin.com/docs-new/rest/futures-trading/market-data/get-klines) documents:

- `GET https://api-futures.kucoin.com/api/v1/kline/query` is a public unauthenticated market-data call.
- Required `symbol` and `granularity`, bounded `from` and `to` timestamps in milliseconds.
- The response returns `[timestamp_ms, open, high, low, close, volume, turnover]`. Gaps can occur because KuCoin omits periods with no ticks. Result limits require paging for large windows.
- **Market metadata discovery does not establish trading eligibility or residency permission**. No order routes, API keys or account access are included in this work.

Only a single explicit bounded **2–128 fully closed consecutive candles** range is accepted per invocation. No automatic pagination or missing-bar interpolation; partial, stale/future-window, duplicate, mismatched OHLC, overlapping, invalid JSON, malformed price and truncated responses are refused. The exact raw-body SHA-256 is reported for local evidence. It is not a cryptographic exchange signature.

## Implementation

- `naseri_markets/kucoin_futures_replay_stage21_v1.py`: strict exact instrument and bar interval request; public HTTPS fixed host, no proxy/redirect/credentials, 7-second network timeout, 256 KiB response bound, decimal-safe deterministic parsing. Requires `MMT_NONPRODUCTION=1` and explicit acknowledgment before any GET. Injected test transport is labeled **INJECTED_TEST_TRANSPORT**, never misrepresented as real venue communication.
- `naseri_markets/futures_probe_stage21_v1.py`: explicit manual CLI, never installed as an auto-start service.
- `offline_replay_to_core_inputs` converts already captured candles into a Stage-5 *historically timed* offline `DataOrigin.REPLAY` flow with exact host-selected CoreBinding and CoreManifest. The calculated sample receipt timestamps in this conversion are **simulation time**, not actual market arrival times.
- No signal, order, position, Telegram, account, or Stage-20 PAPER journal writes from this module.

## Example on a separately authorized development workstation

Use a Python 3.12 clean installed project wheel with operator-approved public market data access. Supply real recent complete UTC 15-minute boundaries; these sample dates are illustrative only:

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.futures_probe_stage21_v1 \
  --symbol XBTUSDTM --timeframe 15m \
  --start 2026-10-11T10:00:00Z \
  --end 2026-10-11T10:45:00Z \
  --ack-public-readonly-get
```

The command issues **one GET only when run explicitly**. It prints a provenance-aware, non-authorizing JSON summary; it intentionally does not emit a real trading signal or execute PAPER on its own. Avoid polling, scraping beyond provider terms, or treating unavailable data as valid flat candles.

## Next part of Stage 21 (still OPEN)

A future 21B must implement an operator-reviewed binding to Stage 20's **PAPER risk and lifecycle**, preserving `DataOrigin.REPLAY`, exact dataset digest, historical fill ordering, separate control-plane revisions, no lookahead, explicit entry-bar and exit-bar sequencing and Stage-19 job-to-effect audit. It must not use Stage 16's current **synthetic-only** execution path and mislabel the data. Require multi-symbol installed-wheel acceptance, capture/replay persistence and fault injection before treating Stage 21 as complete.

No NY First-Reversal source, legacy runtime, production database, live Telegram, release settings or deployment is changed. The general verdict remains `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.
