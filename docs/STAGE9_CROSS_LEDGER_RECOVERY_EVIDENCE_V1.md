# Stage 9 — Cross-Ledger Recovery Evidence Closure V1

**STATUS: OFFLINE / NONPRODUCTION / READ-ONLY RECOVERY DECISION SUPPORT. LIVE AND PUBLIC PRODUCT RELEASE STILL BLOCKED.**

## Evidence baseline and actual gap

Parent baseline: `main@e6f64e8d93ecbc44e784c118e5b0c41f89d2ee12` (Stage-8 architecture audit); do not mutate the historic `crypto-price-action==0.3.2` runtime or its production databases.

Stage 17 already commits an offline job claim; Stage 19 **already commits an effect intent before each target-ledger call** and provides `evaluate_effect_evidence` with exact target-ID checks and an audit chain. Stage 20 already demonstrates two synthetic PAPER bindings using five independent SQLite stores. **No cross-database ACID or global exactly-once exists**. This stage therefore does **not** build another runtime, database, new receipt writer, queue, publisher or authority.

**Added only** a bounded `evaluate_recovery_decisions` function in the existing `naseri_markets/job_effect_reconciliation_v1.py`, preserving the existing Stage-19 API and verdicts. It transforms **verified existing evidence** into an operator-facing decision table, while cross-checking all Stage-17 runtime jobs against the complete *operator-declared* expected effect kinds for each job. Modifications are confined to Stage-19 reconciliation, Stage-19 tests, Stage-20 integration test and this documentation.

## Canonical ownership and boundaries

```text
Stage 12 reviewed operator intent
     → Stage 16 PAPER replay → Stage 17 job (job_id; PENDING/CLAIMED/DONE/QUARANTINED)
                                │
                                ├── Stage 19 PREPARED effect intent (intent_id)
                                │        │
                                │        ├── PAPER_RESERVE → Stage 8 local PAPER target
                                │        ├── PAPER_PLAN → Stage 9 local plan target
                                │        └── DRY_SIGNAL → Stage 10 local NO-SEND signal
                                │
                                └── Stage 19 RECORDED receipt (separate SQLite commit)

STAGE 9 AUDIT ONLY:
owner-stopped private snapshot → existing Stage 19 verify chain/exact IDs
     → Stage 17 job coverage + predeclared expected kind inventory
     → fixed recovery decisions (never replay, alter or send)
```

**No source code in this stage performs a multi-database write, retry, restart, resubmission, Telegram delivery or broker call.** It does not verify modeled PAPER fill/exit effects beyond the existing initial Stage-19 `PAPER_RESERVE`, `PAPER_PLAN` and `DRY_SIGNAL` instrumented boundaries.

## Precondition: independent, consistent, frozen private snapshot

The operator must independently **stop every possible writer**, collect coordinated owner-private SQLite snapshots **including necessary WAL state**, verify the correct roles for effects/runtime/paper/signal, and pass `operator_ack=True` and `all_writers_stopped=True`. Both parameters are operator assertions, **not an independently proven OS lock**. The existing Stage-19 `evaluate_effect_evidence` validates the four existing files, refuses shared-inode roles and symlinks, opens SQLite with `mode=ro` and `query_only=ON`, validates SQLite integrity and recomputes the immutable local effect audit chain. The Stage-9 helper *reuses that validation first*, then obtains the complete bounded runtime job list using a read-only query on the same operator-frozen snapshot.

**Important:** Four separate read-only connections do not provide an atomic cross-database snapshot. If writers were not fully stopped or the snapshot was not obtained consistently, reported decisions must **not** be trusted. This stage never claims to prove a complete uninterrupted crash history, an externally signed receipt or a broker-side truth.

The caller must provide a **complete** operator-declared `expected_effect_kinds_by_job` map, keyed by every Stage-17 `job_id`, including zero-effect jobs. Each value is a sorted tuple containing unique members of `DRY_SIGNAL`, `PAPER_PLAN`, `PAPER_RESERVE`. The model refuses unknown job IDs, omitted runtime jobs, oversized requests, unsorted or duplicate kinds. It **does not invent expected effects by looking at what happened**, because that would silently bless an omitted effect. The map is NOT independently authenticated or automatically deduced from historic panel settings. For a genuine authoritative product, this mapping must eventually be pinned to a separately trusted, pre-execution decision/intent receipt; until then its completeness is operator-asserted.

## Classification decisions (every row defaults to non-executable)

| Evidence condition after Stage-19 proof | Stage-9 classification | Operator consequence |
| --- | --- | --- |
| Exact target + recorded receipt + runtime job DONE | `EXACT_TARGET_AND_RECEIPT` | `VERIFIED_ONLY_NO_REDISPATCH`; local evidence only |
| Exact target + PREPARED intent but no recorded receipt | `TARGET_EXISTS_RECEIPT_GAP` | `BLOCKED_OPERATOR_REVIEW` |
| PREPARED intent + no target record | `PREPARED_NO_TARGET_UNKNOWN` | `BLOCKED_OPERATOR_REVIEW`, never automatic retry |
| RECORDED receipt + no target | `RECORDED_TARGET_MISSING_CONFLICT` | `BLOCKED_OPERATOR_REVIEW` |
| Target identity/digest mismatch | `TARGET_CONFLICT` | `BLOCKED_OPERATOR_REVIEW` |
| DRY_SIGNAL outbox UNKNOWN/CLAIMED | `AMBIGUOUS_SIGNAL_OUTBOX` | `BLOCKED_OPERATOR_REVIEW`, never send/resend |
| Missing Stage-17 runtime job referenced by an existing effect | `MISSING_JOB` | `BLOCKED_OPERATOR_REVIEW`; do not discard record |
| Exact target and receipt but job not DONE | `EXACT_TARGET_JOB_UNFINISHED` | `BLOCKED_OPERATOR_REVIEW` |
| Expected effect kind absent from audited journal | `MISSING_EFFECT_INTENT` | `BLOCKED_OPERATOR_REVIEW`, even if job DONE |
| Extra or duplicate effect kind | `UNEXPECTED_OR_DUPLICATE_EFFECT_INTENT` | `BLOCKED_OPERATOR_REVIEW` |
| Runtime PENDING without an expected or observed effect | `PENDING_NO_DISPATCH` | `NO_ACTION_AUTHORIZED` (not completed) |
| DONE, CLAIMED, QUARANTINED job with no effect proof | `JOB_HAS_NO_EFFECT_PROOF` | `BLOCKED_OPERATOR_REVIEW`; legitimate NO_EVALUATION still requires separate independent proof |

Every success and refusal returns or raises **without permission for automatic retry, ledger repair, Telegram publishing, broker execution or LIVE trading**. The table has deterministic `source_evidence_sha256` and `decision_sha256` fingerprints. A same-input and same-snapshot evaluation is stable; altered operator-declared expectations change the decision fingerprint, even if raw data is unchanged. These hashes prove neither independent witness custody nor external authenticity.

## Usage for a forensic operator (example, do NOT point at Production)

```python
from pathlib import Path
from naseri_markets.job_effect_reconciliation_v1 import (
    EffectEvidencePaths,
    evaluate_recovery_decisions,
)

paths = EffectEvidencePaths(
    Path("/private/snapshots/effects.sqlite"),
    Path("/private/snapshots/runtime.sqlite"),
    Path("/private/snapshots/paper.sqlite"),
    Path("/private/snapshots/signals.sqlite"),
)
# Built from a prior, separately approved list of expected effects per job,
# NEVER selected from only the success records found in the audit.
expected = {
    "job17_REPLACE_WITH_REVIEWED_ID": (
        "DRY_SIGNAL", "PAPER_PLAN", "PAPER_RESERVE",
    ),
}
# Environment must be MMT_NONPRODUCTION=1, not MMT_PRODUCTION=1.
report = evaluate_recovery_decisions(
    paths,
    expected_effect_kinds_by_job=expected,
    operator_ack=True,
    all_writers_stopped=True,
)
print(report.as_dict())  # inspect locally; it contains explicit operation IDs
```

Never copy real customer credentials into the evidence workspace. Never automatically clear a quarantine or mark `PREPARED` as safe to replay. A local report is not permission to mutate an original database, and external crash safety must be independently audited before any product promotion.

## Nonproduction acceptance matrix

The repository's Stage-19 test corpus simulates each `PAPER_RESERVE`, `PAPER_PLAN` and `DRY_SIGNAL` cutpoint:

1. Intent PREPARED and target absent → unresolved/blocked.
2. Target exists, receipt not committed → receipt-gap/blocked.
3. Receipt committed but job not DONE → incomplete/blocked.
4. Receipt committed and job DONE → **only** locally verified (no runtime authority).
5. Receipt says committed but target missing → conflict/blocked.
6. Missing job, mismatched target digest, ambiguous signal outbox, missing or duplicate expected effects and tampered audit chain → refused or blocked without data mutation.
7. Stage-20 genuine two-binding **synthetic** PAPER pilot → closed-effect receipt inspection across six effects. An isolated, post-commit copied snapshot changes one job to QUARANTINED; the same stage-9 evaluator must block its effects without changing the original evidence.
8. Hostile input, missing operator approval, incomplete inventory and Production mode → fail-closed.

All existing Stage-17/18/19/20 contracts and tests must remain passing. CI and the Stage-20 synthetic pilot validate only the tested offline scenarios; they cannot guarantee real crash atomicity or external provider correctness.

## Required release decision

Even if all regression tests pass, the system remains `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`. Stage 9 does not close host isolation, account/provider eligibility, true market data/fee accuracy, real Telegram read-back, risk policy certification, authentic Brooks Core API semantics, external sealed holdout or global exactly-once. Operator-provided expected-effect maps and snapshots are expressly not independently trusted evidence.

**Stage 9 stop rule:** Merge only the four scoped files on a green, exact-head PR with the original release fences preserved. Do not start Stage 10, add a new reconciliation ledger, relax sample/risk constraints, deploy, run a real-money trial, or touch production databases.
