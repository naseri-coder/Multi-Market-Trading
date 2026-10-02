> Historical reference only; not current release proof.
> Original source: `integration_phase1/docs/integration_contract.md`; SHA256: `4919450735400aa544153c4d779434347c974c629883affbfce35620c1050108`.

# Integration Phase 1 — Contract

## Producer
Brooks Core / signal-engine.

## Consumer
Existing Telegram bot signal domain (`SignalService` + PostgreSQL).

## Hard rules

1. Brooks Core never imports Telegram handlers.
2. Existing SignalService remains lifecycle authority.
3. No parallel `signals` table is introduced.
4. Every automated signal requires snapshot ID + snapshot hash.
5. Every automated signal requires engine, rule-set, and configuration versions.
6. Every automated signal has deterministic idempotency.
7. Rule evidence is stored separately and immutably.
8. Leverage is explicit integration configuration; it is not inferred from Brooks rules.
9. PAPER/SHADOW are excluded from production performance metrics.
10. PAPER/SHADOW must not appear in public user signal surfaces.

## Generation modes

| Mode | publication_scope | counts_toward_performance |
|---|---|---|
| SHADOW | INTERNAL | false |
| PAPER | PRIVATE_TEST | false |
| LIVE | PUBLIC / VIP / PUBLIC_VIP | explicit production decision |

## Transaction boundary

The integration service must own one `AsyncSession.begin()` transaction around both the existing
SignalService calls and automation metadata inserts.

This is required for atomic idempotency.
