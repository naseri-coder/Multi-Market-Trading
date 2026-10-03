# Brooks Core v3 — Phase 4 Shadow Runtime Bridge

## Purpose

Phase 4 connects the Phase-3 immutable domain boundary to the existing canonical
market-data snapshots in shadow mode only. It evaluates the existing Phase-1 Foundation
and Phase-2 Crypto Adaptation layers without creating a trade decision.

## Runtime path

```text
canonical closed MarketSnapshot
  -> identity-preserving domain adapter
  -> Phase-1 Foundation
  -> Phase-2 Crypto Adaptation
  -> RuntimeShadowResult
  -> diagnostics only
```

## Hard safety boundary

The Phase-4 result is never publishable. It exposes no LONG/SHORT decision, entry,
stop-loss, targets, leverage, database write, chart render, or Telegram delivery.
The existing PAPER/LIVE Brooks runtime remains untouched by this phase.

## Files

- runtime_bridge/adapter.py
- runtime_bridge/entities.py
- runtime_bridge/core_orchestrator.py
- runtime_bridge/signal_pipeline.py
- runtime_bridge/chart_pipeline.py

## Verification gate

- Phase 4 unit tests: 6/6 PASS.
- Combined Phase 1-4 focused suite: 47/47 PASS.
- Real Binance public BTCUSDT 15m shadow smoke: PASS.
- Real Binance public BTCUSDT 15m + 1h causal MTF shadow smoke: PASS.
- Source snapshot ID/hash are preserved exactly across the adapter.
- `publication_allowed` is always false.
- Four explicit Phase-4 safety blockers prohibit signal generation, DB write,
  chart render, and publication.

## Deployment state

This phase changes source files on the host only. It does not restart or rewire the
currently running LIVE bot container. Production behavior therefore remains unchanged.
