# Multi Market Trading — Stage 19: Job-to-Effect Intent Ledger V1

**Scope:** opt-in, operator-driven, synthetic/replay only; independent Stage-17 scheduler, Stage-16 offline integrator, Stage-8/9 PAPER and Stage-10 no-send signal journals are preserved. **No production deployment, live provider, broker order, Telegram transmission, unknown plugin loading, or automatic retry is authorized.**

## What is new and what is still missing

Stage 18 only associated a Stage-17 job with potential effects by source/binding. Stage 19 adds a **durable exact-ID pre-call record** before every effect initiated through the *new* `JobEffectIntentExecutor` route. The existing Stage-8 decision idempotency and Stage-10 signal uniqueness remain the sources of truth in their respective target DBs.

A job can now contain three independently auditable intents:

1. `PAPER_RESERVE`: expected `pc8_<deterministic 60-hex>` order ID. The `request_digest` matches the exact Stage-8 `paper_core_decisions.request_digest` contract, including manifest, event, decision, size, market basis and allocation revision.
2. `PAPER_PLAN`: identical expected order ID; the intent's request digest equals SHA256 of the exact Stage-9 `paper_stage9_plans.plan_json` bytes, including targets and fractions.
3. `DRY_SIGNAL`: expected Stage-10 `signal_key` (SHA256 of core, version, instance, binding and decision identity) and the exact `initial_digest` contract including event, result, channel and expiry. **The command remains a local no-send outbox command.**

The effect journal is its own operator-private SQLite file. Each target call is wrapped in `PREPARED` (commit first) → target-specific SQLite operation → validate target receipt → `RECORDED` (second commit). Event rows form an integrity-checkable hash chain, **not an external tamper-proof witness**.

### Crash matrix

| Crash point | What exists | Recovery verdict |
| --- | --- | --- |
| Before `PREPARED` | No known intent | No inference of safety; Stage 17 still gates the Job |
| After `PREPARED`, before target write | Intent, no target evidence | `UNKNOWN_NO_TARGET_NOT_SAFE_TO_RETRY` |
| After target commit, before `RECORDED` | Intent + exact target evidence | `EFFECT_PRESENT_RECEIPT_GAP_MANUAL_REVIEW` |
| After `RECORDED`, while Job still `CLAIMED` | Intent + target | `EXACT_EFFECT_JOB_UNFINISHED_REVIEW` |
| After successful Job `DONE` | Intent, target, verified request identity | `EXACT_OFFLINE_EFFECT_CONFIRMED` |
| Any id/proof conflict | Contradictory evidence | `BLOCKED_INCONSISTENT_EVIDENCE` |
| Signal command `UNKNOWN` or `CLAIMED` | Possible ambiguous send state | `BLOCKED_AMBIGUOUS_DELIVERY` |

**Never infer that missing target evidence means a safe retry.** A crash, stale snapshot, database copy or partially written separate transactions can make absence ambiguous. Stage-17 never requeues `CLAIMED` or `QUARANTINED` jobs. Stage-19 adds no automatic repair, rollback, promotion, supervisor mutation, order fill, exchange gateway or Telegram API call.

## Opt-in construction (trusted operator code, NOT installed automatically)

```python
from naseri_markets.job_effect_intent_v1 import (
    OfflineJobEffectLedger, JobEffectIntentExecutor,
)

# Supply already configured, independently authorized nonproduction objects:
# supervisor: OfflineRuntimeSupervisor; integration: OfflinePanelPaperIntegration
# paper: OfflinePaperPositionLifecycle; signals: OfflineSignalLifecycle
# state directory must be private, 0700, owned by current OS user.
with OfflineJobEffectLedger(private_state / "effects.sqlite", enabled=True) as ledger:
    callback = JobEffectIntentExecutor(
        supervisor=supervisor, ledger=ledger, integration=integration,
        paper=paper, signals=signals, quantity=Decimal("1"),
        dry_run_channel_id=-10019,
    )
    # Stage 17 must have a valid, due, explicitly scheduled job; no background loop.
    receipts = supervisor.run_due(callback, now=clock, limit=1, operator_ack=True)
```

`MMT_NONPRODUCTION=1` and `MMT_PRODUCTION!=1` are required. The Stage-19 callback verifies a **currently `CLAIMED` Stage-17 job** and refuses a job with any prior effect attempt. The Stage-16 adapter and Stage-8/9/10 policies remain active, including per-instance budgets, modelled market basis and strict provenance. The new Ledger does not create any account, publish any message, or grant authorization; choose a previously reviewed trusted built-in Core.

`JobEffectIntentExecutor` must explicitly replace the old `Stage16ReplayExecutor` in the operator's Stage-17 `run_due` call. **Old execution code remains uninstrumented** and cannot be retroactively certified by Stage-19; Stage-18 remains necessary for old history.

## Strict read-only evidence command

Run this only against four **existing, separately snapshotted** private SQLite files (owner-only, file mode 0600; directory 0700):

```bash
MMT_NONPRODUCTION=1 python -m scripts.mmt_stage19_effects \
  --effects /private/offline/effects.sqlite \
  --runtime /private/offline/runtime.sqlite \
  --paper /private/offline/paper.sqlite \
  --signal /private/offline/signals.sqlite \
  --ack-offline-readonly
```

Exit 0: all inspected Stage-19 intents have exact local target evidence and the corresponding Stage-17 job is DONE. Exit 1: at least one unclear, incomplete or conflicting effect. Exit 2: invalid or insecure evidence. **Exit 0 does NOT authorize production or automatic replay.** Missing Stage-19 intents for older Stage-17 jobs are not certified by this tool; use Stage 18's four-ledger reconciler for full historical coverage.

Input hardening: paths must be absolute, regular, non-symlink, non-hardlinked, current-OS-user owned and private. Roles may not refer to the same inode. SQLite opens in URI `mode=ro`, `query_only=ON`, reads within a snapshot, checks integrity, verifies intent event hash chain, recomputes canonical intent IDs and compares exact reference digests to the Stage-8/9/10 ledger rows. A digest cannot prove market data authenticity, a benign strategy, an independent operator, or true execution at a broker.

## Explicit limitations / operator cautions

- **No distributed ACID transaction.** Separate SQLite target and intent commits have a crash gap by design. Both completion and recovery are always manual for uncertain cases.
- **No cross-machine locking or identity attestation.** Run an approved private local operator workstation. Real HA/worker-fencing requires separate formal design.
- **No durable consumer subscription.** The supervisor remains an opt-in bounded action, not a market poller, daemon, or operator Telegram bot.
- **No retroactive mapping or cryptographic authorization from old receipts.** The new exact mapping applies only to jobs actually executed with the Stage-19 wrapper.
- **No real execution lifecycle coverage.** Stage-9 simulated fills and exits after an initial order plan remain governed by the prior Stage-9 evidence and Stage-18 checks; Stage-19 wraps only the initial reserve, target-plan registration and Stage-10 no-send signal registration.
- **No economic claim.** Synthetic outcomes do not demonstrate historical profitability, backtested edge or authentic venue fills.
- **No automatic recovery based on a receipt**, even if exact hashes match. All verdicts are read-only observations.

## Acceptance and deployment fence

Focused tests include durable pre-call persistence, replay conflict rejection across Job IDs, audit-chain tampering, forged target digests, shared/symlink inputs, crash state and `UNKNOWN` signal commands; repository CI separately exercises the real Stage-16/8/9/10 integrated path with a reviewed synthetic Core and verifies a three-effect receipt.

The historical package/runtime, README, live Telegram, broker adapters, GitHub deployment manifests, frozen production source and private NY First-Reversal stay untouched. **Final stage verdict, after full checks: `STAGE19_OFFLINE_EFFECT_INTENTS_PASS` is not `PRODUCT_READY_FOR_LIVE`.**
