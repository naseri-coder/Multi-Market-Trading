# MARC — MA 7/25/99 Regime & Momentum Core

MARC is the repository's second analytical core. It is deliberately independent
from the Al Brooks core and implements the frozen **MARC R1 v0.1** baseline for
15-minute and 30-minute Binance USD-M Futures candle data.

## Strategy identity

- Core: `MA_REGIME_CORE`
- Short name: `MARC`
- Setup: `MARC_R1_MA99_REGIME_RECLAIM`
- Engine: `marc-core-v0.1.0`
- Rule set: `marc-r1-v0.1`
- Configuration: `marc-baseline-v0.1`

The baseline is intentionally frozen before out-of-sample evaluation. Parameter
changes must become explicit versions rather than silent tuning.

## Frozen baseline

MARC R1 uses:

- SMA 7 / SMA 25 / SMA 99;
- Wilder ATR(14);
- MA7/25 directional crossover as the momentum transition;
- MA99 plus/minus 0.10 ATR as the regime boundary;
- two consecutive qualifying closes for persistence;
- cross validity of 12 bars on 15m and 8 bars on 30m;
- no-trade after more than two MA7/25 crosses in the prior 20 bars;
- no-trade when normalized MA spread is below 0.25 ATR;
- no-trade when confirmation/entry extension from MA99 exceeds 1.50 ATR;
- structure lookback of five closed bars;
- structural stop buffer of 0.20 ATR;
- MA99 stop buffer of 0.50 ATR;
- rejection when initial stop distance exceeds 1.80 ATR;
- nominal strategy risk fraction metadata of 0.50% equity;
- TP1 at 1R, TP2 at 2R, and a future runner contract identified as
  Chandelier 22 / 3 ATR.

The core does not submit exchange orders.

## Long contract

1. MA7 crosses above MA25.
2. The cross remains inside its timeframe-specific validity window.
3. Price closes above `MA99 + 0.10 * ATR14`.
4. A second consecutive close satisfies the same condition.
5. MA compression, crossover chop, and overextension gates must pass.
6. Entry is modeled at the **next bar open**, never at the already-known
   confirmation close.
7. Stop is the lower of:
   - five-bar structure low minus 0.20 ATR;
   - MA99 minus 0.50 ATR.
8. The plan is rejected if entry-to-stop distance exceeds 1.80 ATR.
9. TP1 = 1R and TP2 = 2R.

## Short contract

The short contract is the exact directional mirror of the long contract.

## False MA99 break

After the first qualifying regime close, if the immediately following close
crosses the opposite 0.10 ATR band before persistence completes, the setup is
classified as `INVALIDATED_FALSE_BREAK`. A later setup requires a new MA7/25
cross.

## Causality

`replay_entry_plans()` analyzes only candles that were closed at each
decision point and takes the following candle's open as the modeled entry.
Future candles are never included in indicator or decision calculations.

The replay helper intentionally does **not** assign trade outcomes. Fees,
slippage, funding, Chandelier runner behavior, portfolio sizing, and
out-of-sample performance evaluation belong to the dedicated backtest stage.

## Runtime boundary

The former placeholder FM identity has been migrated to `MARC`. The isolated
runtime package is `app.modules.marc_runtime`.

The default MARC runtime registry remains empty and the strategy row is
fail-closed with `engine_ready=false`. This is intentional: source
implementation does not equal operational approval. A future runtime adapter
must be validated against out-of-sample backtests before it can publish MARC
signals.

MARC must never be persisted or measured as a Brooks producer. The database
identity reserved for a future MARC persistence adapter is `producer='MARC'`.

## Isolation rule

Brooks and MARC must first be evaluated independently. A future fusion mode may
compare or combine their evidence only after standalone performance is known.
