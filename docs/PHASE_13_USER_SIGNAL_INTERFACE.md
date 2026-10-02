# Phase 13 — User Signal Interface

Phase 13 exposes read-only signal collections to Telegram users. It does not create,
edit, publish, close, or generate signals and does not introduce notification or
win-rate behavior.

## Public collections

- **Live (`live`)**: every non-draft signal created during the latest rolling 24 hours.
- **Open (`open`)**: every signal whose current status is `OPEN`, regardless of age.
- **History (`history`)**: signals whose current status is `CLOSED` or `CANCELLED`.

Draft signals are excluded from every public query and cannot be opened through a
crafted detail callback.

## Pagination

Signal lists are queried directly from PostgreSQL in pages of 10. Target details are
also counted and queried in pages of 10, preventing unbounded database loads and
Telegram messages. Requests above the last page are clamped to the current last page.

## Telegram interface

The persistent user menu includes:

- `📡 سیگنال‌های لحظه‌ای`
- `🟢 سیگنال‌های باز`
- `📜 تاریخچه سیگنال‌ها`

Each list displays symbol, direction, status, entry, and P/L. Signal details display
entry, stop loss, direction, leverage, P/L, description, timestamps, and ordered target
status. Dates use the configured report timezone.

All inline callbacks are versioned, anchored, and restricted to an explicit pattern.
Every signal route reuses the multi-channel membership gate, refreshes user activity,
and clears stale support/admin input state before accepting menu navigation.

## Query architecture

`SignalQueryService` owns public visibility and pagination rules.
`SQLAlchemySignalRepository` performs count and bounded list queries. Telegram handlers
only translate updates into query calls and render the returned immutable records.
