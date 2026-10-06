# MARC R2 Fresh Reversal Transition (FRT) v0.1

This stage tests one clean pre-entry hypothesis rather than another exit tweak.

The preceding MARC R2 stages established that:

- broad R1 is too weak after costs;
- early post-entry MA99 failure is descriptive but did not become a profitable
  next-open causal exit;
- delaying entry for a three-bar MA99 hold degraded the setup;
- break-even/TP exit repairs did not rescue broad R1;
- the execution-cost budget reduced losses but did not establish edge.

## Hypothesis

MARC is treated as an **early regime reversal**, not a mature trend-following
entry.

A valid Fresh Reversal Transition candidate must satisfy the frozen R1 signal
and all of the following before entry:

1. timeframe is 15m;
2. the latest directional MA7/MA25 cross is no older than 3 closed bars;
3. the 5-bar MA99 slope is still **opposed** to the new trade direction;
4. the structural initial stop distance is at least 0.60% of entry price.

For LONG, MA99 must still slope down while the new bullish transition is being
confirmed. For SHORT, MA99 must still slope up.

This intentionally captures the moment when fast momentum and price have
reclaimed the slow regime average before MA99 itself has fully turned.

The 0.60% structural-risk floor is an execution-viability rule: extremely tight
stops turn ordinary futures fees/slippage into an excessive fraction of one R.

## What is not changed

- SMA 7 / 25 / 99;
- 0.10 ATR MA99 confirmation band;
- two-close persistence;
- R1 structural/ATR stop construction;
- R1 25% at 1R, 25% at 2R, 50% Chandelier runner;
- base cost 6 bps/side;
- stress cost 10 bps/side.

This isolates setup quality from exit engineering.

## Development gate

Development uses only the already-observed BTC/ETH/SOL/BNB/XRP 15m history
from 2022-01-01 through 2026-09-30.

The single hypothesis must produce:

- at least 300 trades;
- base expectancy > +0.05R;
- base PF >= 1.10;
- stress expectancy > 0R;
- stress PF >= 1.03;
- positive base expectancy on at least 4 of 5 symbol streams.

If it fails, the holdout is not fetched.

## Untouched holdout

If development passes, exactly the same setup is run once on:

- ADAUSDT
- DOGEUSDT
- LINKUSDT
- LTCUSDT
- BCHUSDT

Only 15m is evaluated because FRT is explicitly a 15m setup.

The holdout requires:

- at least 200 trades;
- positive base expectancy;
- base PF >= 1.10;
- positive stress expectancy;
- stress PF >= 1.03;
- at least 4 of 5 symbol streams positive after base costs.

A passing result is still research-only:

`runtime_approval = DENIED_RESEARCH_ONLY`
