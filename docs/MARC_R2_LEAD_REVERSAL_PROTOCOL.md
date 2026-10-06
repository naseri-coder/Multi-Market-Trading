# MARC R2 Lead Reversal Transition (LRT) v0.3

This stage follows two controlled FRT experiments.

FRT v0.1 produced a positive base-cost edge but only break-even stress
performance. FRT v0.2 improved pooled stress performance through a strict cost
gate, but became too sparse and cross-sectionally inconsistent.

The new hypothesis is structural rather than numerical.

## Lead Reversal idea

A good MARC reversal should be **early**.

The 15m signal is accepted only while the latest fully closed 30m context has
**not yet aligned** with the new 15m direction.

For a LONG signal, the trade is rejected if the latest closed 30m already has:

- close > MA99; and
- MA7 > MA25.

For a SHORT signal, the trade is rejected if the latest closed 30m already has:

- close < MA99; and
- MA7 < MA25.

A MIXED or still-OPPOSED 30m context is allowed. This means 15m is leading the
larger regime rather than chasing a mature move.

## Rules retained unchanged from FRT v0.1

- 15m only;
- frozen R1 MA7/25/99 signal;
- two-close MA99 persistence;
- latest directional MA7/25 cross age <= 3 bars;
- 5-bar MA99 slope still opposed to the new trade direction;
- structural initial stop >= 0.60% of entry;
- frozen R1 exit model;
- 6 bps/side base cost;
- 10 bps/side stress cost.

No cost-budget filter from FRT v0.2 is used.

## Anti-overfit discipline

The FRT v0.1 development gate is reused unchanged:

- >=300 trades;
- base expectancy > +0.05R;
- base PF >= 1.10;
- stress expectancy > 0R;
- stress PF >= 1.03;
- >=4/5 positive base-cost development streams.

Development remains BTC/ETH/SOL/BNB/XRP.

Only if that gate passes are the still-unseen ADA/DOGE/LINK/LTC/BCH archives
fetched. The same holdout thresholds remain unchanged.

Even a passing holdout remains research-only:

`runtime_approval = DENIED_RESEARCH_ONLY`
