# Phase 12 — Signal Service

Phase 12 adds framework-independent signal commands, an async repository, and the
business service. No Telegram signal handler, market-data feed, exchange integration,
automatic signal generator, or notification delivery is included in this phase.

## Transaction boundary

`SQLAlchemySignalRepository` uses a caller-owned `AsyncSession`. A composition layer
must execute each service operation inside one database transaction. The service locks
the signal aggregate before state-changing operations so target ordering and lifecycle
transitions remain serialized.

## Supported operations

- Create an `OPEN` signal, or explicitly create a `DRAFT` for a later publishing flow.
- Edit full market fields while a signal is a draft.
- Edit only symbol and description on an open signal; stop changes use the dedicated
  stop-loss operation.
- Add strictly ordered targets above entry for `LONG`, or below entry for `SHORT`.
- Mark targets hit in numeric order and persist caller-supplied profit/loss.
- Tighten stop loss upward for `LONG` or downward for `SHORT`, including crossing entry
  to protect profit.
- Close an open signal with explicit profit/loss and cancel pending targets.
- Cancel a draft or open signal and cancel pending targets.
- Read paginated, newest-first lifecycle history.

## Audit history

Every successful mutation appends an immutable `signal_events` row. Decimal values are
serialized as strings inside JSON metadata so precision is not lost. The service emits
`CREATED`, `UPDATED`, `TARGET_ADDED`, `TARGET_HIT`, `STOP_LOSS_UPDATED`, `CLOSED`, and
`CANCELLED` events.

## Validation and safety

- Float inputs are rejected; exact `Decimal`, string, or integer values are accepted.
- Database numeric precision and scale are validated before persistence.
- Closed and cancelled signals are immutable.
- Open signal direction, entry, and leverage are immutable to avoid rewriting active
  trading history.
- P/L is never guessed by this layer. The caller must supply the result produced by an
  approved market/accounting policy.
- Initial stop geometry is enforced by the service. Migration `20260901_0006` removes
  the entry-relative database check so legitimate trailing stops can cross entry.
