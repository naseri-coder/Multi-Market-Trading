# MARC R4 — Setup Morphology & Directional Qualification v0.1

R4 keeps the strongest MARC research family found so far — FRT v0.1 — and
tests whether **the shape of the setup itself** identifies a transferable edge.

It does not change MA periods, stops, targets, or the FRT rules.

## Why R4 exists

R3 showed that a generic volatility/structure regime layer did not stabilize
FRT across time and instruments. R4 therefore moves closer to the actual
price-action event and measures morphology visible at the FRT confirmation
close.

LONG and SHORT are always treated as distinct classes.

## Frozen base setup

The underlying shadow signal remains FRT v0.1:

- 15m only;
- SMA 7 / 25 / 99;
- fresh directional MA7/25 cross;
- MA99 reclaim with two-close persistence;
- 5-bar MA99 slope still opposed to the new direction;
- initial structural risk >= 0.60% of entry;
- frozen R1 exit model;
- 6 bps/side base execution cost;
- 10 bps/side stress execution cost.

## Four morphology points

Every FRT shadow trade receives a score from 0 to 4 using only candles closed
before the entry open.

### 1. Directional impulse

The directional close-to-close displacement over the last 3 bars must be at
least 0.50 ATR14.

### 2. MA7/25 expansion

The directional MA7/25 separation must be at least 0.10 ATR14 and larger than
it was two bars earlier.

### 3. Confirmation-candle quality

Both persistence candles must have bodies in the trade direction and their
average directional close-location value must be at least 0.65.

For LONG, close-location is `(close-low)/(high-low)`.
For SHORT, it is mirrored as `(high-close)/(high-low)`.

### 4. No chase

The confirmation close may be no farther than 0.75 ATR14 beyond MA99 in the
trade direction.

## Fixed morphology classes

The score is not optimized.

- A = score 4
- B = score 3
- C = score 0, 1 or 2

Direction remains part of the class, producing exactly six possible classes:

- LONG_A
- LONG_B
- LONG_C
- SHORT_A
- SHORT_B
- SHORT_C

## Expanding walk-forward

Test years remain:

- 2023
- 2024
- 2025
- 2026

For each test year, morphology eligibility is learned only from FRT shadow
trades before January 1 of that test year.

A direction+morphology class is enabled only when the prior training history
has:

- at least 40 class trades;
- base expectancy > +0.05R;
- stress expectancy > 0R;
- stress PF >= 1.03;
- at least 3 different symbols with 5 or more class trades and positive base
  expectancy.

There is deliberately **no symbol selector** in R4. If a morphology is real,
it must show cross-symbol support before it is allowed into the following year.

## Development universe

The ten already-observed research symbols are:

BTC / ETH / SOL / BNB / XRP / ADA / DOGE / LINK / LTC / BCH.

Development passes only if concatenated eligible test-year trades have:

- at least 150 trades;
- positive base expectancy;
- base PF >= 1.10;
- positive stress expectancy;
- stress PF >= 1.03;
- at least 3 of 4 test years positive after base costs;
- at least 6 of 10 symbols positive after base costs.

## Untouched holdout

AVAX / DOT / TRX / ATOM / NEAR remain untouched after R3.

Only if R4 development passes may their archives be fetched.

The holdout receives the **exact morphology policy frozen by development for
each year**. Holdout results cannot select a direction, class, score threshold,
or symbol.

The holdout requires:

- at least 75 trades;
- positive base expectancy;
- base PF >= 1.10;
- positive stress expectancy;
- stress PF >= 1.03;
- at least 3 of 4 test years positive;
- at least 3 of 5 symbols positive.

## Anti-overfitting constraints

This stage performs no:

- MA period search;
- stop/target search;
- exit modification;
- threshold grid search;
- symbol selection;
- random train/test split;
- holdout-driven repair.

Even a full pass remains research-only:

`runtime_approval = DENIED_RESEARCH_ONLY`

The dedicated GitHub Actions workflow is intentionally added only after source,
tests, CLI, and this protocol pass the repository's existing public checks.
