# Brooks Core v3 — Phase 1 Foundation Refactor

## Scope

Phase 1 adds an isolated Foundation package under `app/modules/brooks_core_v3/`.
It does not change the existing Brooks runtime, signal generation, risk engine, score
engine, AI Council, signal quality, Telegram handlers, migrations, or production
publication behavior.

## Added contracts

- `MarketState`: normalized closed-bar market state.
- `ContextModel`: context reasons and explicit phase blockers.
- `NarrativeModel`: human-readable explanation shell.
- `EvidenceRegistry`: source-linked evidence by layer.
- Shared protocol interfaces for future pipeline stages.

## Safety contract

The Foundation pipeline is descriptive only. It produces no entry price, stop loss,
target, chart, delivery, database write, Telegram message, or exchange order. Future
phases must opt in explicitly and preserve the current phase-by-phase approval rule.
