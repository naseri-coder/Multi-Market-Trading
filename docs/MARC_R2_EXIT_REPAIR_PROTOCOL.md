# MARC R2 Exit Repair v0.1

The first causal R2 search showed that early MA99 exits and delayed three-bar
entries did not improve the frozen R1 baseline. The untouched cross-sectional
holdout was therefore never fetched.

This stage tests a different diagnosis: R1 may be giving away trend expectancy
through its 25% TP1 realization and may be over-trading setups whose stop is so
tight that execution friction consumes too much of one R.

## Development universe

- BTCUSDT
- ETHUSDT
- SOLUSDT
- BNBUSDT
- XRPUSDT

## Pre-registered variants

1. `R1_BASELINE`
2. `PARTIAL25_BE_AFTER_1R`
3. `FULL_BE_AFTER_1R_TP2_50_RUNNER50`
4. `FULL_BE_TP2_50_RUNNER50_COST_BUDGET`

### PARTIAL25_BE_AFTER_1R

The original 25% TP1 is retained. After TP1 becomes known, the remaining
position receives break-even protection beginning on the next candle. This
avoids assuming an intrabar order that OHLC data cannot prove.

### FULL_BE_AFTER_1R_TP2_50_RUNNER50

1R becomes a protection trigger only: no profit is realized there. Break-even
protection starts on the next candle. At 2R, 50% is realized and the remaining
50% continues under the frozen Chandelier runner.

### Cost-budget variant

The same full-position BE model is used, but a setup is rejected before entry
when the stress transaction-cost model would consume more than 0.25R for an
entry-price round trip:

`2 * entry * stress_bps / initial_risk <= 0.25R`

This is an execution-economics rule, not a threshold selected by searching the
historical PnL surface.

## Development selector

A non-baseline variant must have at least 750 trades, positive base and stress
expectancy, base PF > 1.05, and stress PF > 1.00. Highest stress expectancy wins
among passing variants.

## Untouched holdout

Only after a development variant is frozen are these archives allowed to be
fetched:

- ADAUSDT
- DOGEUSDT
- LINKUSDT
- LTCUSDT
- BCHUSDT

The same 15m/30m holdout gate from the prior search is retained. No result can
enable runtime trading:

`runtime_approval = DENIED_RESEARCH_ONLY`
