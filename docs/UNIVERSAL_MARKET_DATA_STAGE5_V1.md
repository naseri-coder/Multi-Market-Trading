# Multi Market Trading — Stage 5: Universal Market Data Engine V1

**Verdict scope:** development-only, deterministic REPLAY/SYNTHETIC feed handling; **not authenticated live exchange or broker connectivity**. No Telegram, real account login, broker/exchange orders, database migration, trading permission, or deployment.

**Repository baseline:** `main@2c98f1d6f709e676aaa58635283f713c114311f1` (Stage 4).

## Design principle

Strategies never pick the broker, exchange, symbol or timeframe. A trusted host/operator registers an exact `(market, provider, symbol, timezone, quote currency, timeframe, event kind, origin)` `FeedDefinition`. The host then attaches any compatible `CoreManifest` and `CoreBinding` to that feed. When one valid market sample arrives, the engine builds separate immutable `CoreInput` objects for all subscribed bindings. It never calls the strategy or transmits a market order or Telegram message.

Core API v1 (Stage 3) and Secure Plugin Runtime v1 (Stage 4) are **unchanged**. The stage-5 engine emits **data-only** objects, suitable for future explicitly authorized orchestration. Its normalized samples do **not** authenticate provenance; the caller needs verified source adapters later.

## New source files

- `naseri_markets/market_data_engine_v1.py`: offline feed definitions, subscriptions, shared bounded data buffer, strict ingest, per-feed quarantine, explicit operator-controlled reset, per-binding CoreInput fanout, price/volume provenance metadata.
- `naseri_markets/market_data_normalizers_v1.py`: strict, pure crypto OHLCV fixtures, forex bid-OHLC with **tick_volume**, and quote Bid/Ask fixtures. Only host-supplied maps; no provider REST or MT5 SDK.
- `tests/unit/test_market_data_engine_v1.py`: deterministic offline tests and actual integration with the Stage-3 two-setup example **after** an inert event is emitted.

## Acceptance gates

1. **Market/strategy decoupling:** the same unchanged public two-setup core can consume events for different crypto symbols and forex broker bindings chosen by the host.
2. **One feed, multiple subscribers:** a single validated candle stream fans out to several bindings with distinct instance/binding identity and input digests.
3. **Causal time:** only closed bars are eligible; each must match the declared interval (daily permits 23–25h across DST). Packet receive time cannot precede the observation or exceed the configured maximum lag. No future bars in CoreInput.
4. **Gap/rollback safety:** missing/out-of-order sequence, inconsistent duplicate, changed provenance, overlapping or discontinuous bars, malformed timeframe and stale/future observations quarantine that **feed only**; no further callbacks. Exact duplicate is suppressed.
5. **Explicit reset:** a quarantined feed cannot silently resume. The host must independently establish data continuity and invoke `reset_feed(..., operator_ack=True)`; this boolean is NOT an authentication or remote-admin mechanism.
6. **Evidence honesty:** `DataOrigin` only `REPLAY/SYNTHETIC`, never live; `PriceBasis` identifies trade/bid/ask/mid/mark/index; `VolumeSemantics` distinguishes traded volume from forex broker tick count. These metadata travel alongside `CoreInput` in `MarketDelivery`; the original Core API v1 has no native volume/basis field, so downstream consumers **must carry and enforce metadata** before making any risk or trading claim.
7. **No unauthorized effects:** no secrets, network access, filesystem persistence, broker execution, Telegram delivery, public plugin load, or licensed/proprietary NYFR code.

## Example use (illustrative only)

```python
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, MarketPacket, OfflineMarketDataEngine, PriceBasis, VolumeSemantics,
)
from naseri_markets.core_api_v1 import CoreEventType, DataOrigin, CoreBinding

# `instrument`, `manifest`, `candle` are trusted, already-validated inputs
# provided by a caller; this is not a broker/exchange authorization.
feed = FeedDefinition(
    feed_id="crypto_replay_one", instrument=instrument, timeframe="15m",
    event=CoreEventType.CLOSED_CANDLE, origin=DataOrigin.REPLAY,
    source_ref="immutable_offline_fixture", price_basis=PriceBasis.TRADE,
    volume_semantics=VolumeSemantics.TRADED,
)
engine = OfflineMarketDataEngine(enabled=True)
engine.register_feed(feed)
engine.subscribe(feed.feed_id, manifest, CoreBinding(
    "instance_one", "binding_one", instrument, "15m"))
receipt = engine.ingest(MarketPacket(feed.feed_id, 1,
                                    candle.close_at, feed.source_ref, candle=candle))
# receipt.deliveries contains inert CoreInput events after lookback warm-up.
# NO plugin evaluation, publication or order execution occurs here.
```

## Conservative limitations and next integrations

- **No actual Kraken/Binance/MT5/OANDA/futures/FX authenticated feed is added.** These normalizers are schema examples, not production provider adapters. API authentication, venue KYC/geographic eligibility and live-data proof remain separately gated.
- Pure in-memory buffer; no checkpoint, durable exactly-once guarantee, interprocess sharing, failover, gap reconciliation, backfill or session/holiday verification. An overnight or weekend candle gap currently requires **manual resynchronization**; it must not be silently interpreted as a complete continuous interval.
- A configured price basis or tick-volume marker is only an operator assertion, not external attestation. FX bid candles must not be used to claim executable ask fills or real volume. No dynamic symbol list/selected broker UI here.
- Generic CoreInput from Stage 3 does not encode spread, fee/funding, corporate actions or contract size. Later adapter/orchestration stages must preserve these before PAPER or LIVE valuation.
- The old `trusted_custom.py`, legacy production code, source SHA manifest, PostgreSQL, and Stage-4 OCI host remain untouched. This is intentionally additive and disconnected from deployed services.

**Only after targeted tests, Stage-3/Stage-4 compatibility, and repository CI pass** may the implementation be considered `STAGE5_MARKET_DATA_NONPRODUCTION_PASS`. This is **not** a product-release or live-trading verdict.
