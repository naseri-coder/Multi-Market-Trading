# MARC R2 Causal Setup Search v0.1

This stage converts the R1 diagnostic into a deliberately small causal
experiment. It is designed to find a cleaner MARC setup without parameter
mining.

## Frozen development universe

The already-observed development universe is:

- BTCUSDT
- ETHUSDT
- SOLUSDT
- BNBUSDT
- XRPUSDT

Date range: 2022-01-01 through 2026-09-30 UTC.

## Pre-registered variants

Only four variants are evaluated:

1. `R1_BASELINE`
2. `EARLY_MA99_LOSS_3`
3. `EARLY_OPPOSITE_BAND_3`
4. `HOLD_MA99_3_THEN_ENTER`

### EARLY_MA99_LOSS_3

The R1 entry is unchanged. During the first three post-entry candles, a close
through MA99 in the wrong direction creates a thesis-failure event. The
remaining position exits at the **next candle open**. No future candle is used
to fill the current candle.

### EARLY_OPPOSITE_BAND_3

The same causal exit is used, but only when the close crosses the opposite
`0.10 * ATR14` band around MA99.

### HOLD_MA99_3_THEN_ENTER

After a valid R1 confirmation, the strategy does not enter immediately. The
next three closed candles must remain on the correct side of their causal MA99.
Only after all three closes are known is a new entry attempted at the following
candle open. Entry distance, structural stop, ATR risk, and targets are
recomputed from information available at that time.

## Frozen development selector

The baseline can never be selected as R2. A non-baseline variant must have:

- at least 750 development trades;
- base-cost expectancy > 0R;
- base-cost profit factor > 1.05;
- stress-cost expectancy > 0R;
- stress-cost profit factor > 1.00.

If several pass, the variant with the highest **stress-cost expectancy** is
selected once.

If none pass, the process stops with `NO_DEVELOPMENT_VARIANT_PASSED`.

## Untouched cross-sectional holdout

The holdout symbols are hard-coded before execution and are not fetched until
after the development selector has produced one fixed variant:

- ADAUSDT
- DOGEUSDT
- LINKUSDT
- LTCUSDT
- BCHUSDT

The selected variant is then run exactly once on both 15m and 30m for those
symbols. No rule is changed after holdout results become visible.

A candidate may receive `MARC_R2_PURE_SETUP_CANDIDATE` only if the untouched
holdout satisfies all of the following:

- at least 500 trades;
- base expectancy > 0R;
- base profit factor >= 1.10;
- stress expectancy > 0R;
- stress profit factor >= 1.03;
- at least 6 of 10 symbol/timeframe streams have positive base expectancy;
- both pooled 15m and pooled 30m have positive base expectancy.

Even that classification is research-only:

`runtime_approval = DENIED_RESEARCH_ONLY`

## Costs and data

Data comes from checksum-verified official Binance Data Vision USD-M Futures
monthly 15m archives. 30m is rebuilt from complete UTC-aligned 15m pairs.

The frozen execution-cost models remain:

- base: 6 bps per side;
- stress: 10 bps per side.

No funding payment model is added in this stage.
