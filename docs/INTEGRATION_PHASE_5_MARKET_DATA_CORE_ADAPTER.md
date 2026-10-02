# Integration Phase 5 — Market Data Foundation + Brooks Core Adapter

## Inventory result

The bot source already contains Brooks persistence metadata and PAPER delivery wiring,
but it does not contain a real exchange market-data module or the actual Brooks strategy
implementation.

This phase therefore does not invent Brooks rules.

## Added

- canonical immutable Candle
- immutable MarketSnapshot
- deterministic snapshot_id
- SHA-256 snapshot_hash
- closed-candle-only validation
- missing/misaligned candle detection
- stale snapshot rejection
- MarketDataProvider protocol
- Binance Spot public REST adapter
- Bybit V5 public REST adapter
- BrooksCoreAnalyzer protocol
- strict snapshot-id/hash bridge into the existing PaperSignalCandidate
- NO_SIGNAL handling

## Safety

No exchange API key is required.
No database migration is required.
No PAPER runtime is enabled.
No background scanner is started.
No Telegram/public/VIP publishing is enabled.
No real order execution is added.

The actual Brooks strategy engine and professional chart renderer remain separate required
components. They must be connected later rather than fabricated here.
