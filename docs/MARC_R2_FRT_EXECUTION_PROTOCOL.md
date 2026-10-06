# MARC R2 FRT + Execution Viability v0.2

FRT v0.1 was the first MARC subset to establish a positive base-cost edge:

- 403 development trades;
- +0.09375R base expectancy;
- base PF 1.15386;
- +0.00138R stress expectancy;
- stress PF 1.00207;
- 4/5 positive base-cost symbol streams.

It failed only the pre-registered stress PF threshold (>=1.03), so the untouched
ADA/DOGE/LINK/LTC/BCH holdout was not fetched.

## Single v0.2 change

The FRT v0.1 setup is unchanged except for one pre-entry execution-viability
gate.

Under the already frozen 10 bps/side stress model, the entry-price round-trip
cost estimate may consume at most 0.25R:

`2 * entry * stress_bps / initial_risk <= 0.25R`

This gate is known before entry and does not use future PnL.

## Rules retained from FRT v0.1

- 15m only;
- frozen R1 MA7/25/99 signal and two-close MA99 persistence;
- latest directional MA7/25 cross age <= 3 bars;
- MA99 5-bar slope still opposed to the new trade direction;
- structural stop distance >= 0.60% of entry;
- frozen R1 exit model;
- base cost 6 bps/side;
- stress cost 10 bps/side.

## Development and holdout gates

The FRT v0.1 development gate is reused unchanged. No threshold is relaxed.

Development remains BTC/ETH/SOL/BNB/XRP. If and only if development passes,
the still-unseen ADA/DOGE/LINK/LTC/BCH 15m archives are fetched and tested
exactly once.

The holdout verdict remains research-only even on success:

`runtime_approval = DENIED_RESEARCH_ONLY`
