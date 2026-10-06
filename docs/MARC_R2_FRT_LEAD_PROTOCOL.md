# MARC R2 FRT Lead Reversal v0.3

This stage keeps the complete FRT v0.1 setup and tests one structural
interpretation of a fresh reversal:

**15m must lead 30m.**

The 15m reversal is accepted only while the latest fully closed 30m context has
not yet aligned with the new direction.

## Frozen FRT rules retained

- 15m only;
- frozen R1 SMA 7/25/99 signal;
- two-close MA99 persistence;
- latest directional MA7/25 cross age <= 3 bars;
- 15m MA99 5-bar slope still opposed to the new trade direction;
- structural initial stop distance >= 0.60% of entry;
- frozen R1 exit model;
- 6 bps/side base cost;
- 10 bps/side stress cost.

## Lead condition

The latest **fully closed** 30m candle is evaluated with 30m SMA7/SMA25/SMA99.

30m is BULL when:

- close > MA99; and
- MA7 > MA25.

30m is BEAR when:

- close < MA99; and
- MA7 < MA25.

Everything else is MIXED.

For a 15m LONG:
- BULL = ALIGNED -> reject;
- BEAR = OPPOSED -> allow;
- MIXED -> allow.

For a 15m SHORT:
- BEAR = ALIGNED -> reject;
- BULL = OPPOSED -> allow;
- MIXED -> allow.

No partially formed 30m candle is read.

## Why this is a distinct hypothesis

FRT is intended to capture a transition before the slow regime has completed
its turn. If 30m is already aligned, the move may be mature rather than fresh.

No exit, MA period, ATR band, cross-age, stop rule, cost assumption or gate is
changed in this stage.

## Development and untouched holdout

Development remains BTC/ETH/SOL/BNB/XRP. The unchanged FRT v0.1 development
gate must pass.

Only then may ADA/DOGE/LINK/LTC/BCH be fetched and tested exactly once. The
holdout cannot alter this setup.

Every result remains research-only:

`runtime_approval = DENIED_RESEARCH_ONLY`
