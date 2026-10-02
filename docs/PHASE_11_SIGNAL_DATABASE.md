# Phase 11 — Signal Database Architecture

Phase 11 introduces persistence only. It does not create, publish, calculate, or deliver
real trading signals. Signal business operations belong to Phase 12 and Telegram signal
interfaces belong to later phases.

## Relationships

- `signals` is the aggregate root.
- `signal_targets.signal_id` references `signals.id` with `ON DELETE CASCADE`.
- `signal_events.signal_id` references `signals.id` with `ON DELETE CASCADE`.
- `(signal_id, target_number)` is unique, so target ordering cannot be duplicated.

## Signal lifecycle

- `DRAFT`: persisted but not published.
- `OPEN`: active market signal.
- `CLOSED`: completed signal with `closed_at` populated.
- `CANCELLED`: cancelled signal with `closed_at` populated.

Entry, stop loss, and leverage must be positive. Initial `LONG` signals require
`stop_loss < entry_price`; initial `SHORT` signals require `stop_loss > entry_price`.
As of Phase 12, this directional rule is lifecycle-aware and enforced by
`SignalService`, because a risk-reducing trailing stop may legitimately cross the entry
price after a signal opens. The database continues to enforce positivity and lifecycle
shape constraints.

## Target lifecycle

- `PENDING`: not reached; `hit_at` and `profit_loss` are null.
- `HIT`: reached; `hit_at` and `profit_loss` are required.
- `CANCELLED`: no longer active; hit fields remain null.

Prices use `NUMERIC(38,18)` to retain very small crypto prices without floating-point
rounding. Profit/loss uses signed `NUMERIC(18,8)`.

## Event architecture

`signal_events` is an immutable-history foundation for later service and notification
workflows. Each event stores a constrained `event_type`, JSON object metadata, and a
timezone-aware creation timestamp. Supported foundational events include creation,
publication, updates, targets, stop loss changes, stop hits, closure, and cancellation.

The database column is named `metadata`; the ORM attribute is `event_metadata` because
`metadata` is reserved by SQLAlchemy's declarative API.

## Indexes

- Signal status and creation time for open/history screens and reports.
- Signal symbol and status for symbol-specific lookups.
- Target signal, status, and order for ordered target rendering.
- Event signal and chronology for audit history.
- Event type and creation time for future win-rate and notification queries.
