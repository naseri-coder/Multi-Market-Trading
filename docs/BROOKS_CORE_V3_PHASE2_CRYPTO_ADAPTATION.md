# Brooks Core v3 — Phase 2 Crypto Adaptation Layer

## Purpose

Phase 2 preserves the Brooks Foundation/Pure Core and adds crypto-native context around
it. The adaptation layer is descriptive only: it cannot create a LONG/SHORT decision,
entry, stop, target, score, leverage, database row, chart delivery, or Telegram message.

## Context dimensions

- volatility expansion/contraction from normalized true range on closed candles;
- relative-volume state from final closed-bar volume versus prior median volume;
- crypto fake-breakout / trap context from range probes rejected back inside;
- optional public-market liquidity context from spread/depth observations;
- optional derivatives crowding context from funding and open-interest change;
- multi-timeframe alignment from resolved Brooks Foundation Always-In states.

All numeric thresholds are explicit engineering policy and are included in
`CryptoAdaptationPolicy.configuration_version`; they are not represented as Brooks rules.

## Source-purity boundary

Brooks evidence continues to use `BB-*` rule identifiers and the Phase 1 source catalog.
Crypto adaptation evidence uses separate `CA-*` identifiers and never claims a crypto
threshold came from the Brooks trilogy. The existing `app/modules/brooks_core/` package
is not modified by this phase.

## Fail-closed data rules

- candle-derived context uses only immutable closed candles;
- optional liquidity/OI/funding observations must be timezone-aware and no later than
  the primary snapshot capture time;
- higher-timeframe snapshots must describe the same exchange, market type and symbol;
- a higher-timeframe candle may not close after the primary capture time;
- missing or incomplete optional feeds produce `UNKNOWN` plus an explicit blocker;
- input fingerprints are deterministic SHA-256 values for replay/audit comparison.

No private exchange credentials or order execution are introduced.

## Phase 2 gate

Phase 2 is acceptable only when:

1. Phase 1 Foundation tests remain green.
2. Phase 2 unit tests cover closed-bar context, optional-feed failure modes, MTF
   causality, future-data rejection, evidence separation and deterministic fingerprints.
3. No existing production module imports `CryptoAdaptationEngine`.
4. Application syntax/import checks, configuration validation, PostgreSQL health and
   Alembic head checks remain green.
5. Docker image build succeeds without requiring a production runtime cutover.

Runtime wiring and any use of adaptation context in signal selection belong to a later
phase and require a separate explicit approval.
