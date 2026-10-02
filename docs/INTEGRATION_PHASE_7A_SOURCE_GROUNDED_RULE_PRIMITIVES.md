# Integration Phase 7A — Source-Grounded Rule Primitives

## Source basis

Primary source: `اسلاید کامل البروکس ilam98(1).pdf` (150 slides).

Reviewed catalog contains BR-001..BR-037. This phase implements only deterministic
conditions that the extracted source catalog expresses without inventing numeric thresholds.

## Implemented primitives

- BR-010 Inside Bar — exact high/low relation, source page 16
- BR-011 Outside Bar — exact high/low relation, source page 16
- BR-012 Default EMA length metadata — EMA 20, source page 20
- BR-015 With-trend/countertrend classification — only when trend direction is already resolved
- BR-017 Always-In mapping — only when bull/bear trend state is already resolved
- BR-019 Range-breakout 80% source heuristic — stored as heuristic, never calibrated probability
- BR-020 Volume optional policy
- BR-027 Candlestick pattern requires more information/context
- BR-029 Market inertia 80% source heuristic — not calibrated probability
- BR-030 Trend reversal failure 80% source heuristic — not calibrated probability
- BR-035 Indicators remain secondary to bars

## Explicit blockers

EH-001..EH-007 remain unresolved and are represented in code as blockers, not Brooks rules:
trend-bar thresholds, swing confirmation, S/R zone construction, Always-In flip,
momentum metric, H1/H2/L1/L2 edge counting, and breakout follow-through threshold.

## Decision policy

The Phase 7A engine is fail-closed and returns NO_SIGNAL. It does not emit LONG/SHORT from a
raw MarketSnapshot while the above causal classifiers remain unresolved.

No database migration.
PAPER stays disabled.
No Telegram publishing.
No live orders.
