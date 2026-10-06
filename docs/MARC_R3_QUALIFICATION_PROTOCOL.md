# MARC R3 — Regime & Instrument Qualification v0.1

MARC R3 does not invent another moving-average pattern. It keeps the strongest
research family found so far — **FRT v0.1** — and asks a different question:

> When is this instrument and this market regime eligible to trade FRT?

## Why R3 exists

The FRT Lead Reversal variant passed development but failed a genuinely unseen
cross-sectional holdout. Its gross expectancy collapsed on the unseen symbols,
so the rule was not promoted.

This suggests that MARC is not a universal setup that should fire on every
instrument and regime. R3 therefore validates an adaptive **eligibility layer**
instead of adding more entry filters.

## Frozen base setup

The signal generator remains MARC R2 FRT v0.1:

- 15m only;
- SMA 7 / 25 / 99;
- MA7/25 fresh directional cross;
- MA99 reclaim with two-close persistence;
- 5-bar MA99 slope still opposed to the new direction;
- structural initial risk >= 0.60% of entry;
- frozen R1 exit model;
- base execution cost 6 bps/side;
- stress execution cost 10 bps/side.

## Causal regime features

Every FRT shadow trade receives two features computed at the confirmation close.

### Volatility bucket

Current `ATR14 / close` is compared with the **previous 2880 closed 15m bars**
(30 days). No future bar is used.

- LOW: percentile < 33.33%
- MID: 33.33% through 66.67%
- HIGH: > 66.67%

### Structure bucket

A 20-bar price efficiency ratio is computed:

`abs(close[t]-close[t-20]) / sum(abs(close[i]-close[i-1]))`

- TREND: efficiency >= 0.35
- CHOP: efficiency < 0.35

This produces six fixed regime cells such as `HIGH_TREND` and `LOW_CHOP`.

## Expanding walk-forward

Test years are frozen:

- 2023
- 2024
- 2025
- 2026

For each test year, all eligibility decisions are learned strictly from trades
whose entry occurred **before January 1 of that test year**.

There is no random split and no future leakage.

### Regime-cell eligibility

A regime cell is enabled for the next year only when its training history has:

- at least 30 FRT shadow trades;
- base expectancy > +0.05R;
- stress expectancy > 0R;
- stress PF >= 1.03.

### Instrument eligibility

An instrument is enabled for the next year only when its training history has:

- at least 15 FRT shadow trades;
- base expectancy > 0R;
- base PF >= 1.05;
- stress expectancy > 0R.

A real candidate is eligible only when **both** its current regime cell and its
instrument are enabled.

If a historical gap leaves fewer than the full 30 days of causal volatility
history required for the regime feature, that shadow trade is conservatively
**ineligible** for R3. It is not imputed and it does not abort the full study.

## Development universe

These ten symbols are already observed research data and may therefore be used
for R3 development:

- BTCUSDT
- ETHUSDT
- SOLUSDT
- BNBUSDT
- XRPUSDT
- ADAUSDT
- DOGEUSDT
- LINKUSDT
- LTCUSDT
- BCHUSDT

R3 development passes only if the concatenated 2023–2026 eligible trades have:

- at least 150 trades;
- base expectancy > 0R;
- base PF >= 1.10;
- stress expectancy > 0R;
- stress PF >= 1.03;
- at least 3 of 4 test years positive after base costs;
- at least 6 of 10 symbols positive after base costs.

## New untouched cross-sectional holdout

Only if development passes may these archives be fetched:

- AVAXUSDT
- DOTUSDT
- TRXUSDT
- ATOMUSDT
- NEARUSDT

The development-frozen **regime cells for each year** are reused on holdout.
Each holdout instrument may qualify itself only from its own strictly prior FRT
shadow history using the same frozen instrument rule.

The holdout requires:

- at least 75 eligible trades;
- positive base expectancy;
- base PF >= 1.10;
- positive stress expectancy;
- stress PF >= 1.03;
- at least 3 of 4 test years positive;
- at least 3 of 5 symbols positive.

## Conservative shadow behavior

The eligibility layer is evaluated on the frozen FRT shadow stream. If an
ineligible shadow trade would have occupied the FRT engine, R3 does not invent
replacement signals that the base engine never produced. This deliberately
understates opportunities rather than creating optimistic synthetic trades.

Even a full pass remains research-only:

`runtime_approval = DENIED_RESEARCH_ONLY`
