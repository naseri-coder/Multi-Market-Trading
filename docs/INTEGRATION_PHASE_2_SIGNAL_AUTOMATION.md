# Integration Phase 2 — SQLAlchemy Models, Repository & Atomic Transaction

## Scope

This phase implements the real persistence bridge between Brooks Core output and the
existing signal lifecycle. It does **not** enable the scanner, Telegram publishing, public
queries, or production win-rate counting.

## Added module

`app/modules/signal_automation/`

- `entities.py` — Brooks import command, rule evidence, result/read models
- `models.py` — ORM mapping for `signal_automation_metadata` and `signal_rule_evidence`
- `repository.py` — async PostgreSQL persistence and uniqueness translation
- `service.py` — atomic import transaction
- `errors.py` — integration-specific expected failures

## Existing Signal model change

`signals.publication_scope` from migration 0012 is now mapped in SQLAlchemy using
`SignalPublicationScope`.

## Atomic transaction

One `AsyncSession.begin()` owns:

1. idempotency lookup
2. existing `SignalService.create_signal`
3. `publication_scope` update
4. existing `SignalService.add_target` for all targets
5. automation metadata insert
6. ordered rule evidence insert
7. commit

Any unexpected exception rolls the entire transaction back.

## Race-safe idempotency

Two database uniqueness guards already exist from migration 0012:

- `(producer, source_signal_id)`
- `(producer, idempotency_key)`

A racing duplicate causes the losing transaction to roll back. The service then opens a
fresh transaction and resolves the winning row by idempotency key.

## Important safety state

PAPER remains `PRIVATE_TEST` and cannot count toward performance.
SHADOW remains `INTERNAL` and cannot count toward performance.

Public-query filtering and analytics filtering are **not** changed in this phase. Therefore
PAPER/LIVE runtime activation remains blocked until those filters are implemented in a later phase.

## PostgreSQL validation

A real PostgreSQL integration test is included at:

`tests/integration/test_signal_automation_postgresql.py`

It requires `TEST_DATABASE_URL`. The artifact-generation environment does not have access to
the user's PostgreSQL instance, so this test must be executed on the server before installation
is considered complete.
