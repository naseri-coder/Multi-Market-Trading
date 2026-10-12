# Stage 18 — Operational Reconciliation & Recovery (OFFLINE)

**Status:** Nonproduction, fail-closed evidence inspection and human review. This is **not** a live runtime, delivery engine, replay authorization, atomic transaction coordinator, or proof of real trading.

## Why Stage 18 exists

Stages 12, 16 and 17 have four independent persistence domains: configuration (`t12_*`), PAPER account/order (`paper_*`), local simulated signal/outbox (`offline_signal_*`), and durable queue (`runtime17_jobs`). Stage 17 stores a job payload identity and SHA-256 of its executor's returned receipt, **not the receipt itself or durable exact order/signal IDs**. A job marked `DONE` is therefore **not independently established to have completed end-to-end**, and a job marked `CLAIMED` or `QUARANTINED` might already have written data to another database.

This stage does **not** claim distributed exactly-once semantics. It never turns a crashed job into a new `PENDING` job or edits an existing PAPER order/signal.

## Added components

- `naseri_markets/operational_reconciliation_v1.py`: inspect four existing distinct SQLite files using read-only connections, bounded queries, SQLite quick checks, full pre-existing Stage-13 three-ledger integrity evaluation, Stage-17 job identity verification and conservative per-binding/source candidate counts.
- `naseri_markets/offline_recovery_review_v1.py`: append-only, separate operator review receipts keyed by job ID and exact evidence digest. Requires an explicit human statement that all relevant workers have been stopped. Records **only** `REVIEW_RECORDED_NO_RETRY`.
- `scripts/mmt_stage18_reconcile.py`: command line report and explicitly approved human review; no executor, timer, worker, network, broker or Telegram API.
- `tests/unit/test_operational_reconciliation_v1.py`: staged crash, real child-process termination, data tampering, duplicate and stale review refusal, ambiguous sender state, cross-role collision and explicit environment fences.
- `.github/workflows/stage18-recovery-acceptance.yml`: focused Python 3.12 tests and publication/lint checks on a disposable runner. No secrets or live endpoints.

## Interpretation (no false success)

| Queue state | Stage-18 interpretation | Automatic action |
|---|---|---|
| `PENDING` | `PENDING_NOT_EXECUTED`; no individual side-effect proof | None |
| `CLAIMED` | `BLOCKED_MANUAL_RECONCILIATION`; a worker might have written another journal | **NEVER retry** |
| `QUARANTINED` | `BLOCKED_MANUAL_RECONCILIATION`; reconcile separately | **NEVER retry** |
| `DONE` | `DONE_UNVERIFIED_CROSS_LEDGER`; result hash without an exact list of effects | None |
| Invalid digest, orphan binding, ambiguous local outbox claim | `BLOCKED_EVIDENCE_INVALID` | None |

`candidate_paper_orders` are counted by matching instance and binding; `candidate_signals` by instance, binding and source reference. **These are candidates, not proof that a particular job created them**. The Stage-13 `integrity_verdict=PASS` is a *local invariant check* and does not solve job-to-effect lineage, authenticate market data or certify broker/Telegram activity. `evidence_sha256` is a deterministic hash of the inspected local observations, **not a trusted external timestamp or tamper-proof signature**. When the four independent files cannot be read consistently or evidence is malformed, the tool refuses or reports a blocker; no implicit success.

All release, replay, Telegram and broker permission booleans are **False**. `CLAIMED` and `QUARANTINED` jobs are never reset automatically. The review journal does not modify Stage-17 state or allow resumption.

## Safe offline operator procedure

1. Independently **stop every worker** that can access the test journals. Do not perform review during concurrent mutations.
2. Create consistent operator-approved offline snapshots of the FOUR independent journals, in a nonproduction private directory (files `0600`, distinct inodes). Native SQLite online backup API or a complete stopped-state backup is preferable to an ad hoc copy of a WAL database. Do not point this tool at an active production DB.
3. On a disposable machine with explicit nonproduction environment, run:

```bash
export MMT_NONPRODUCTION=1
python -m scripts.mmt_stage18_reconcile \
  --runtime-db /private/snapshot/runtime.sqlite \
  --control-db /private/snapshot/control.sqlite \
  --paper-db /private/snapshot/paper.sqlite \
  --signal-db /private/snapshot/signal.sqlite \
  --ack-nonproduction-readonly
```

4. Compare all blocked job IDs, source identities, panel revisions, risk reservations and uncertain outbox commands. No automatic resend of `UNKNOWN` or `CLAIMED` commands.
5. If a `CLAIMED` or `QUARANTINED` job has been independently investigated, record a non-authorizing review receipt with the **exact digest emitted by the report** and a short sanitized explanation:

```bash
python -m scripts.mmt_stage18_reconcile \
  --runtime-db /private/snapshot/runtime.sqlite \
  --control-db /private/snapshot/control.sqlite \
  --paper-db /private/snapshot/paper.sqlite \
  --signal-db /private/snapshot/signal.sqlite \
  --ack-nonproduction-readonly \
  --review-db /private/reviews/stage18.sqlite \
  --review-job 'job17_<64 lowercase hex>' \
  --evidence-sha256 '<exact digest from report>' \
  --operator-id 123456 \
  --review-note 'Manually inspected and quarantined; no re-execution' \
  --ack-all-workers-stopped --ack-manual-review
```

The review file is a **separate, local private database** and is not itself a proven immutable audit trail. Never paste confidential job payloads, secrets or private keys into notes or PR logs. This receipt **does not** mean the job is fixed, completed, safe to retry or ready for production.

## Fault boundaries and unfinished prerequisites

- Rootless Docker/gVisor hostile-code isolation remains unverified; do not execute untrusted plugins.
- Stage 17 has no atomic job-to-effect manifest; Stage 18 cannot make three SQLite databases globally atomic. A future, separately authorized execution coordinator needs durable intent and per-effect IDs **before** side effects, plus transactional outbox or independently verified idempotent consumers.
- Real Telegram delivery, actual exchange/provider authentication, KYC/geographic permission, LIVE trading, economic edge, durable off-host recovery and production rollback remain blocked.
- No source modifications to Stages 1–17, existing databases, legacy `production_source`, `SHA256SUMS`, servers, bot tokens or NY First-Reversal.

**Scoped verdict:** `STAGE18_OFFLINE_RECONCILIATION_IMPLEMENTED_NONPRODUCTION`. **Product verdict:** `PRODUCT_NOT_READY_FOR_LIVE`.
