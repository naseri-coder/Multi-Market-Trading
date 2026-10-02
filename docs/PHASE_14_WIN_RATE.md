# Phase 14 — Win Rate System

## Scope

Phase 14 adds read-only rolling win-rate analytics and a public Telegram report
interface. It does not generate signals, mutate signal lifecycle state, or add a
database migration.

## Periods

All boundaries are rolling UTC windows ending at the report generation time:

| Period | Window |
| --- | --- |
| Daily | Previous 24 hours |
| Weekly | Previous 7 days |
| Monthly | Previous 30 days |
| Yearly | Previous 365 days |

The configured `REPORT_TIMEZONE` affects presentation only. Query boundaries
remain aware UTC timestamps.

## Outcome Semantics

The source of truth is `signal_events`. Only `TARGET_HIT` and `STOP_HIT` are
eligible outcomes. A multi-target signal is counted at most once in a report:
the latest eligible event inside the selected window is its outcome. Event ID
breaks ties when two outcome events have the same timestamp.

This prevents several targets from artificially inflating the number of winning
signals and makes target/stop counts mutually exclusive within one report.

## Formula

```text
Win Rate = Target Hit / (Target Hit + Stop Hit) × 100
```

The result is rounded to two decimal places with `ROUND_HALF_UP`. When there are
no evaluated outcomes, target count, stop count, evaluated count, and Win Rate
are all zero.

## Layers

- `app/modules/analytics/repository.py`: one ranked PostgreSQL aggregate query.
- `app/modules/analytics/service.py`: rolling boundaries, validation, formula,
  and rounding.
- `app/bot/handlers/winrate_user.py`: read-only Telegram presentation adapter.
- `app/bot/keyboards/winrate.py`: exact versioned callback allowlist.

The public `📊 نرخ برد ( وین ریت )` entry opens the four report periods. Each
report explains in Persian that a successful signal means its latest outcome is
`TARGET_HIT`, an unsuccessful signal means `STOP_HIT`, and every signal is
counted once. A zero-outcome report also explains why the displayed rate is 0%.

The Telegram handler enforces the existing multi-channel membership gate and
refreshes the user's activity before exposing reports.

## Database

No schema change is required. Phase 11 already created the following indexes:

- `ix_signal_events_type_created_at`
- `ix_signal_events_signal_created_id`

These support the outcome filter, rolling time boundary, deterministic ranking,
and per-signal grouping used by the repository.
