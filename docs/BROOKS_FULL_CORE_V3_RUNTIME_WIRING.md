# Brooks Full Core v3 — Main Runtime Wiring

This overlay connects `BrooksTrilogyFullCoreEngine` to the existing bot runtime through
the already-built safe PAPER boundary:

`closed market data -> full Brooks core -> chart -> PaperSignalCandidate -> existing signal lifecycle -> PRIVATE_TEST Telegram`

Safety remains fail-closed. The runtime is disabled unless `BROOKS_RUNTIME_ENABLED=true`,
and configuration rejects Brooks runtime activation unless `PAPER_RUNTIME_ENABLED=true`.

## Environment switches

```env
BROOKS_RUNTIME_ENABLED=false
BROOKS_EXCHANGE=binance
BROOKS_MARKET_TYPE=spot
BROOKS_SYMBOLS=BTCUSDT,ETHUSDT
BROOKS_TIMEFRAMES=15m,1h
BROOKS_SNAPSHOT_LIMIT=120
```

The existing PAPER variables remain authoritative:

```env
PAPER_RUNTIME_ENABLED=false
PAPER_PRIVATE_TEST_CHANNEL_ID=
PAPER_DEFAULT_LEVERAGE=1
PAPER_POLL_INTERVAL_SECONDS=60
```

No PUBLIC/VIP publishing and no exchange order execution are added by this wiring.

The runtime normalizes `MarketSnapshot.captured_at` to the final closed candle before
analysis. This makes snapshot hashes and deterministic `source_signal_id` stable across
polls/restarts for the same closed-candle set, while the public market-data provider
still performs freshness checks at fetch time.
