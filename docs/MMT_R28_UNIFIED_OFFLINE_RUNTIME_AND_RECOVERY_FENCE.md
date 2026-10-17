# MMT R28 — Unified **Offline** Runtime and Restart/Reconciliation Fence

**Scope:** Draft, stacked on MMT R27 PR #320, **NOT** main. No GitHub Actions run, no server access, no live feed, no connected PAPER, no broker/Telegram calls, no autonomous scheduler, no Production change.

## Purpose and actual implementation

The preexisting, reviewed local research path is:

`Stage12 pinned panel and binding -> Stage17 SHA-addressed queue -> Stage16 reviewed offline feed/fixture -> strategy evaluation -> Stage8/9 PAPER risk and simulated order lifecycle (only when separately authorized) -> Stage10 local NO-SEND signal journal`.

R28 adds **one operator API** `R28UnifiedOfflineRuntime`, not another strategy, risk engine, order execution service or SQL owner. The host must pass an existing genuine `OfflineRuntimeSupervisor` and `Stage16ReplayExecutor` connected to the **same authenticated panel and actor**, and the exact internal deterministic `OfflineContractFixture`; unsupported plugins and frozen Brooks production strategy loading remain denied. This R28 path is not equivalent to the R27 frozen Brooks preflight being deployable.

- `inspect()`: native Stage17 durable counts, highlights unresolved `CLAIMED`/`QUARANTINED` work; `DONE` is marked **not independently cross-ledger attested**.
- `run_one(now=..., operator_ack=True)`: one explicit invocation, timezone-aware time, at most one Stage17 atomic claim and Stage16 callback. Block all dispatch when any unresolved job exists. No startup auto-run, retry or external sender; only local synthetic/replay data.
- `inspect_stopped_snapshots(RecoveryPaths(...), all_workers_stopped=True, operator_ack=True)`: calls genuine Stage18 read-only review on **four distinct private offline snapshots**, not on active Production files. It never resumes a quarantined job.
- `verify_frozen_brooks_model(...)`: separately calls genuine R27 frozen worker and independent hypothetical-life-cycle/cost parity audit. Returns a model-only evidence digest and zero execution permissions. **R27 evidence is never silently converted to a Stage16 order.**

## Critical Stage17 defect corrected in R28

Previously the Stage17 `_claim` SQL excluded later jobs on the same binding only when an earlier task was `CLAIMED`. After failure, that earlier job becomes `QUARANTINED` (meaning a Stage8/9/10 side effect may already have committed); a different pending job could be selected and produce duplicate or conflicting risk/orders/signals.

R28 changes the candidate filter to treat `CLAIMED` **or** `QUARANTINED` as binding blockers **inside the same SQLite BEGIN IMMEDIATE transaction**. Neither status is automatically retried, deleted, reset to pending, nor silently marked done. The conservative R28 façade also blocks new dispatch globally if any unresolved queue work is visible.

Regression coverage targets: post-exception distinct event on same binding, restart persistence, Stage16 real synthetic fixture invocation, repeated original SHA ID across restart, missing operator acknowledgements, naive clock, Production environment and stopped-snapshot acknowledgement.

## Four distinct data stores are NOT one atomic database

1. Stage12 control configuration in its own database.
2. Stage17 queue with content-addressed job IDs, claims, statuses and callback **result hash only**.
3. Stage8/9 PAPER simulation order/risk ledger.
4. Stage10 local signal/outbox ledger.

These databases have different owners and transactions. R28 does **not** merge their schemas, guarantee distributed exactly-once effects, prove `DONE` reached both journals, or resolve `UNKNOWN` delivery. Implementing an additional coordinator database would create a fifth authority without solving the underlying distributed transaction ambiguity. The intended remedy here is one facade, conservative fences, and bounded read-only evidence review.

If a process is terminated between a side-effect and Stage17 commit, `CLAIMED` persists. An exception results in `QUARANTINED`. Explicit human stop, consistent four-ledger snapshots and independent Stage18 review are prerequisites for investigation; the audit does not authorize replay. Missing/ambiguous data must remain blocked.

## Frozen Brooks R27 evidence boundary

R27 has reconstructed *hypothetical* entry/exit/cost paths based on frozen worker and operator-supplied parameters, not venue-verified executions or Oct20–Nov3 prospective OOS. R28's `verify_frozen_brooks_model` checks the existing R27 report explicitly has **false** for issuer authentication, real broker fills, real account fees/funding settlements, realized PnL, connected PAPER/LIVE and production mutation. These tests cannot turn R27 into a production strategy adapter.

## Validation and release gate

- On a machine with the **full checked-out R28 tree**, run `python -m pytest -q tests/unit/test_offline_runtime_supervisor_v1.py tests/unit/test_operational_reconciliation_v1.py tests/unit/test_mmt_r27_independent_brooks_lifecycle_economics_v1.py`.
- Run `python -m pytest -q tests/unit` and `ruff check .` in the same complete tree, record exact checkout SHA, dependency hashes and failures.
- Separately require genuine CodeQL, Publication Safety, independent PostgreSQL/integration tests, restart with stopped snapshots, multi-binding concurrency, cross-ledger fault injection and review of the stacked Draft PR chain. Do **not** synthesize successful CI or security evidence.
- No `main` merge or deployment authorized; R29 connected PAPER and R33 controlled LIVE remain **NOT READY**.

**Disposition target:** `MMT_R28_OFFLINE_ROUTE_CODE_REVIEW_ONLY` until real complete-repository tests and independent acceptance. Do not call this Production-Ready or complete end-to-end execution parity.
