# FM — Top-10 Crypto One-Year Research Scan v0.1

This branch is research-only. It does not implement or register the FM runtime
engine and does not change production signal routing.

## Objective

Backtest the previously described FM setup on:

- one complete year: 2025-10-01 through 2026-09-30 UTC;
- 15m;
- 30m rebuilt deterministically from complete aligned 15m pairs;
- ten large non-stable cryptocurrencies with full-year Binance USD-M Futures
  archive coverage.

The candidate universe follows the CoinMarketCap 2026-10-06 market-cap
snapshot with USDT and USDC removed. The script walks down that ranking and
selects the first ten symbols for which every required Binance monthly archive
exists. This prevents a recently listed asset from silently receiving a shorter
test period.

## Frozen FM research interpretation

The original FM discussion was:

Context -> Spike/Impulse -> weak first Pullback -> break -> 3-4 bar
follow-through with a new Gap/FVG -> execution before the Leg-2 destination.

The following unresolved details are frozen for this scan before seeing PnL.

### Spike

A spike is at least five same-direction candles. Closes progress monotonically
and no candle makes an opposite pullback extreme relative to the prior candle.

At least one strict three-candle FVG must exist inside the spike:

- bullish: current low > high two candles earlier;
- bearish: current high < low two candles earlier.

### First pullback

- one or two candles;
- contains at least one opposite-direction body;
- retraces no more than 30% of the spike size.

Spike size uses the directional origin/extreme geometry.

### Break and follow-through

The first bar after the pullback must break the spike extreme in the original
direction.

The break then develops into 3-4 consecutive directional bars.

A **new** FVG must be formed entirely by three post-break follow-through bars.

### Entry

The first post-break candle that completes the new FVG becomes the execution
candle:

- LONG: Buy Limit at that candle's low;
- SHORT: Sell Limit at that candle's high.

The pending order remains valid until one of three events:

1. fill;
2. the Leg-2 destination is reached before fill -> cancel;
3. the first-pullback extreme is invalidated before fill -> cancel.

If fill and cancellation conditions appear in the same OHLC candle, the
research engine resolves conservatively in favor of cancellation.

### Stop

The stop is the exact first-pullback extreme. No extra discretionary buffer is
added in v0.1.

### Destination and TP1

Measured-move destination:

- LONG: pullback low + spike size;
- SHORT: pullback high - spike size.

TP1 is placed 0.10 ATR14 **before** that destination.

This makes the user's "TP1 above the destination" statement deterministic for
SHORT and mirrors it for LONG.

### OHLC ambiguity

When both stop and TP1 are reachable inside the same candle after entry, the
backtest records the stop first.

## Costs

Two cost assumptions are reported:

- base: 6 bps per side;
- stress: 10 bps per side.

No funding-rate model is included in this first scan.

## Interpretation warning

This scan is not presented as an authoritative transcription of Al Brooks or as
a completed FM engine. The original discussion left the exact FVG taxonomy,
selected Buy/Sell candle, stop buffer and TP1 offset unresolved. This protocol
freezes one conservative interpretation so that the one-year crypto test is
reproducible and cannot be tuned after the results are visible.

Any later change to these semantics must be versioned and tested separately.
