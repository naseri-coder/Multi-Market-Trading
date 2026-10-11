# Stage 11 — Causal offline Brooks PAPER position lifecycle & realized-R

**Scope:** Source of entry geometry: frozen PUBLIC Brooks V5 PAPER signal and its Stage-10 verified, risk-reserved local order. Market evidence: an explicitly operator-supplied OFFLINE, consecutive, CLOSED OHLCV fixture **after the signal candle**. No market API, clock lookahead, broker orders, Telegram channel publication, online execution, real feed, production changes, market optimization or new trading strategy.

## Actual implemented lifecycle

An opt-in local replay reads a valid, already linked Stage-10 order and independently verifies its source A7 signal/scan receipt, account ID, immutable signal and receipt digests, matching original entry/stop/first target and PAPER-only flags. It refuses missing risk account, altered original order, other lifecycle events, toggled-off Brooks, altered timeframe, mismatched pair, or unknown broker context.

The input file must be bounded to 512 KiB and 1–1024 strictly contiguous closed OHLCV bars of the **exact signal timeframe**. The very first bar must open at the **signal candle close**. All future bars have one exact timeframe step, positive fixed-decimal prices, valid OHLC range, nonnegative finite volume, UTC-aware timestamps and exact frozen provider/venue/market/pair/currency identity. No reading future bars when making decisions on an earlier bar. Duplicate timestamps, gaps, malformed schemas, out-of-sequence/future-linked candles, after-exit bars and changed historical bars are rejected.

Each bar advances one canonical, deterministic simulated Stage-3 order. A long limit is eligible when the bar low touches entry; a short limit when bar high touches entry. Entry execution uses the **frozen limit price**, never an assumed favorable open. Stage-3 receives synthetic **SUBMIT → ACK → FILL** events in the same transaction — ACK is explicitly a LOCAL OFFLINE FIXTURE, not an actual broker acceptance.

Conservative intrabar path assumptions:

- If entry and STOP occur in the same closed bar, close at the protective stop. If entry and TARGET occur in the same bar but STOP does not, **do not credit** the target until a later bar.
- If STOP and TARGET occur in the same later bar, STOP wins (worst case).
- If a filled position gaps against its stop on a later bar, assume the worse **opening price** rather than an unrealistically good stop price.
- A would-be entry bar that **opens beyond its own stop** is unresolved: reject the entire candidate instead of fabricating risk protection.
- Favorable target gaps never earn better than the frozen target limit.
- No arbitrary stop movement, breakeven intervention, scaling, partial fills, spread claims, or unobserved broker queue prioritization is invented.

A terminal Stage-3 **CLOSE_FILL** releases reserved PAPER risk atomically. Independently calculate:
gross = direction × (exit − entry) × quantity × contract multiplier;
fees = max(entry, exit) × quantity × multiplier × account-policy roundtrip fee rate;
slippage = max(entry, exit) × quantity × multiplier × account-policy worst slippage rate;
net = gross − fees − slippage;
realized R = net / (abs(entry − original stop) × quantity × multiplier).

The modeled costs use the *exact* existing Stage-3 configured **local PAPER policy**, not observed market costs. Net-R is NOT a historical probability estimate and does NOT prove an edge. Still-open trades have **no realized PnL** and retain reserved risk.

### Durable persistence and restart

Destination is only the existing `brooks_stage10_paper.sqlite` Stage-3 PAPER DB. The new `brooks_stage11_bars` and `brooks_stage11_positions` tables are committed **inside one Stage-3 BEGIN IMMEDIATE** with all synthetic order lifecycle transitions, accounting, and risk-release rows. A thrown exception rolls back the full batch, including new tables. Replaying an identical full history after restart is idempotent. Earlier-bar digest changes, rollback to a shorter input, unexpected external lifecycle mutations, a post-terminal extension or a change to the Stage-10 link are refused. Neither source Brooks DB nor any broker account is modified.

The private Telegram Brooks admin panel displays Stage-11 replayed/closed PAPER trades and **modeled net PnL** as read-only diagnostics. It never runs the replay on button press. Panel/CLI status opens the PAPER DB in SQLite true `mode=ro`; an absent DB returns `NOT_CONFIGURED` and is never created.

## Local operator usage

An operator must first create a stage-10 link using the previous stage's explicit authorization and separately configured risk account. Prepare a *private* JSON replay file with schema:

```json
{
  "schema_version": 1,
  "origin": "offline_paper_replay",
  "market": "crypto",
  "provider": "kraken_futures_trade_public",
  "symbol": "PF_XBTUSD",
  "quote_currency": "USD",
  "exchange": "kraken_futures",
  "market_type": "futures",
  "timezone": "UTC",
  "timeframe": "15m",
  "candles": [
    {
      "open_time": "2026-10-01T01:30:00+00:00",
      "close_time": "2026-10-01T01:45:00+00:00",
      "open": "105",
      "high": "110",
      "low": "99",
      "close": "104",
      "volume": "5"
    }
  ]
}
```

These are **illustrative fixture numbers, not actual market quotes**. The candle timestamps must follow the *actual persisted Brooks signal* and timeframe. Run a read-only status anytime:

```bash
python -m naseri_markets.brooks_stage11_cli --status \
  --state-dir /private/nonproduction-state
```

An authorized local fixture lifecycle:

```bash
MMT_NONPRODUCTION=1 python -m naseri_markets.brooks_stage11_cli \
  --replay-file --state-dir /private/nonproduction-state \
  --account-id LOCAL_PAPER_ACCOUNT --signal-id VERIFIED_BROOKS_SIGNAL \
  --candles-file /private/verified-ohlcv-bars.json \
  --ack-offline-paper-only
```

`MMT_PRODUCTION=1`, an absent opt-in or a nonlocal input path without an existing ordinary file fails closed. No key or broker SDK is needed. No connection to actual Binance/Kraken service or MT5 occurs. This operation is never triggered from public/private Telegram callback.

## Limits / acceptance

The OHLC backtest is **not an intrabar tick reconstruction**. Adverse tie-breaking prevents optimistic performance claims but a worst-case assumed path is still an estimate. No slippage from real order-book depth, network latency, maker/taker fees, funding, liquidation, exchange contract specification or short borrow terms are verified. Commission and slippage are configured policy assumptions, not receipts. The operator-provided offline candle data is not authenticated to a provider by local SHA hashing. This stage does not calculate or claim a one-year Brooks win rate or profitability without a representative, independently validated input corpus.

The Stage-11 CI validates deterministic long/stop/target, adverse gap, entry-candle ambiguity, net R, restart idempotency, historical mutation, atomic crash rollback, side-effect-free admin/CLI and prior Stage-1–10 regression tests.

Only if all GitHub CI checks pass: `STAGE11_BROOKS_OFFLINE_CANDLE_LIFECYCLE_NONPRODUCTION_PASS`. This does not authorize live orders, unblocked market connectivity, signal publication, or production deployment.
