# Brooks Core v3 — Phase 3 Architecture & Domain Model

## Scope

Phase 3 is architecture-only. It defines immutable domain contracts and integration
ports, but does not implement setup detection, scoring, entry/SL/TP algorithms,
exchange adapters, chart rendering, Telegram publication, or production wiring.

## Domain models (15)

1. Candle
2. MarketSnapshot
3. SwingPoint
4. MarketStructure
5. MarketRegime
6. SupportResistanceZone
7. TrendChannel
8. SetupCandidate
9. RuleEvaluation
10. RiskPlan
11. SignalCandidate
12. Signal
13. SignalEvent
14. ChartSpecification
15. RuleVersion

## Domain-owned protocols (2)

- MarketDataProvider
- SignalPublisher

## Hard invariants

- MarketSnapshot is immutable and rejects unfinished/future candles.
- SwingPoint records both pivot_time and confirmed_at.
- Signal is immutable.
- SignalEvent is an immutable append-only event record.
- Signal and ChartSpecification must carry the same snapshot ID and hash.
- Reproduction key is snapshot hash + rule-set + engine + configuration version.
- Domain imports no exchange SDK or Telegram SDK.
- No unresolved numeric strategy thresholds are introduced in Phase 3.
- SetupCandidate is distinct from Signal and cannot publish directly.

## Phase 1/2 preservation

The existing Foundation, source catalog, and Crypto Adaptation implementation are not
modified by Phase 3. Byte-identity checks are part of the Phase-3 unit gate.

## Production safety

Strategy implementation is intentionally absent. Production runtime behavior remains
unchanged in this phase. Runtime integration belongs to the next gated phase and must
start in shadow/fail-closed mode before any publication behavior can change.
