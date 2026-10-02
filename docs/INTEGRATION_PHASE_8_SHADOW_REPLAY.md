# Integration Phase 8 — Shadow Evaluation & Signal Quality Validation

## Scope

Phase 8 is a read-only, causal evaluation layer for the Phase 7C fundamentals engine.

It does NOT:
- create database signals
- persist signal automation metadata
- publish to Telegram
- use PAPER runtime
- place orders
- permit tradeable LONG/SHORT engine results

## Historical data

New public-REST historical candle sources:
- Binance spot
- Bybit spot / linear / inverse

Historical data intentionally bypasses freshness checks because historical candles are
expected to be stale. Candle closure, ordering and canonical timeframe alignment remain
validated.

## Causality

For every replay point:
- only candles at or before that point are visible
- the fixed rolling window ends at the evaluated candle
- `captured_at` equals the last candle `close_time`
- the same candle window produces the same snapshot hash

This prevents look-ahead leakage from later candles.

## Classification

Because Phase 7C autonomous decisions remain disabled, source-grounded H2/L2 detections
are represented through `setup_type` while the engine decision stays `NO_SIGNAL`.

Phase 8 classifications:
- H2
- L2
- AMBIGUOUS
- BLOCKED
- NO_SIGNAL

`BLOCKED` is temporarily derived from the existing EH-006 fail-closed reasoning string.
A future core contract may expose a structured blocker field.

## Metrics

The report contains:
- evaluated snapshot count
- H2 count
- L2 count
- ambiguous count
- blocked count
- no-signal count
- H2+L2 detections per 1000 evaluated snapshots

No win-rate or profitability claim is made in Phase 8.

## One-shot CLI

Example:

```bash
python -m app.modules.shadow_replay.cli   --exchange binance   --market-type spot   --symbol BTCUSDT   --timeframe 15m   --candles 500   --window 100   --end-at 2026-09-02T10:00:00Z   --output /tmp/btcusdt-15m-shadow.json
```

For deterministic comparison across runs, always provide an explicit `--end-at`.

## Safety

- No migration.
- No dependency changes.
- No `.env` changes.
- PAPER remains disabled.
- Autonomous Phase 7C trade decisions remain disabled.
- A tradeable engine result raises `ShadowReplaySafetyError`.
