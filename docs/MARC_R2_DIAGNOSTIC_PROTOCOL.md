# MARC R2 Diagnostic Protocol v0.1

This stage explains the frozen MARC R1 backtest. It does **not** optimize
7/25/99, change runtime rules, or authorize publication.

## Questions

For every R1 trade we reconstruct the causal state at the confirmation close:

- MA99 5-bar slope normalized by ATR14;
- exact MA ordering: LONG 7>25>99 / SHORT 7<25<99;
- directional 7-25 and 25-99 separation in ATR units;
- confirmation and next-open distance from MA99;
- age of the latest directional 7/25 cross;
- initial stop distance in ATR and percentage terms;
- higher-timeframe context: 15m -> 30m, 30m -> 1h.

We also record post-entry events strictly as **diagnostics**:

- first MA99 touch;
- first touch/rejection back in the trade direction;
- first close through MA99;
- first close through the opposite 0.10 ATR band;
- whether those events occur within fixed 3/4/5/8-bar horizons.

Post-entry information is never treated as a causal entry filter. Any retest or
early-failure rule suggested by these observations must be implemented and
re-simulated causally in a later R2 experiment.

## Interpretation

The former 2025-01-01 through 2026-09-30 OOS window has already been observed.
It is therefore renamed **diagnostic OOS** for this stage. It may help form R2
hypotheses but cannot be reused as untouched proof of R2 performance.

Any R2 rule derived from this report requires a new holdout, such as a frozen
cross-sectional universe not used to choose the rule and/or future unseen data.

Every diagnostic report contains:

`future_r2_approval = DENIED_DIAGNOSTIC_ONLY`
