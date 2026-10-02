# Integration Phase 3 — Publication Isolation & Analytics Isolation

## Public signal isolation

Public LIVE / OPEN / HISTORY collections and public detail lookup now require:
`publication_scope IN ('PUBLIC', 'PUBLIC_VIP')`.

Therefore INTERNAL, PRIVATE_TEST and VIP-only signals are hidden from public surfaces.

## Win-rate isolation

The win-rate repository uses a LEFT OUTER JOIN to `signal_automation_metadata`.

Eligible outcome:
- no automation metadata exists (legacy/manual signal), OR
- `counts_toward_performance = true`.

This preserves legacy/manual reporting and excludes PAPER/SHADOW automation by default.

## Scope

No schema change and no Alembic migration are required.
Admin visibility is unchanged.
PAPER/LIVE runtime and Telegram auto-publishing remain disabled.
