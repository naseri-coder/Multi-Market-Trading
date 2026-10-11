# Multi Market Trading — Stage 13 Reliability & Integration Acceptance v1

**Scope:** additive, offline-only acceptance of the Stage 12 control-plane configuration, Stage 5/7 offline strategy path, Stage 8/9 PAPER risk/position journals, and Stage 10 no-send signal journal. **No automatic execution, real Telegram message, broker order, live market feed, deployment, or production migration is authorized.**

## Why this is an acceptance gate, not a new execution engine

The current platform has three independent persistence domains: `t12_*` UI requests; `paper_*` PAPER risk, orders, and performance; and `offline_signal_*` research signal/outbox. There is **no authenticated, persistent transaction coordinator** that turns a requested panel toggle into market data polling, a Stage-7 dispatch, a Stage-8 reservation, or a Telegram send. Building a second version of the existing risk journal would be counterproductive. Stage 13 supplies a **strict read-only verifier** for operator-prepared copies of these journals and explicit test fixtures which exercise the existing components in a nonproduction scenario.

## Files

- `naseri_markets/reliability_acceptance_v1.py`: fail-closed, bounded SQLite evidence inspection and cross-stage consistency checks.
- `scripts/mmt_stage13_reliability_gate.py`: inert CLI, explicit nonproduction fence, machine-readable JSON, exit codes 0 (evidence invariant PASS), 1 (invariants BLOCKED), 2 (invalid scope/evidence).
- `tests/unit/test_reliability_acceptance_v1.py`: deterministic fault-injection tests using disposable synthetic DBs.
- `tests/unit/test_stage13_cross_stage_offline_v1.py`: real Stage 12 → Stage 5 → Stage 7 → Stage 10 result acceptance plus independently authorized Stage 8/9 order lifecycle on the *same* core decision, all synthetic. The standalone local lightweight test tree skips Stage 8/9 when its older dependencies are absent; GitHub's complete test corpus must execute it.

## Trust and data boundaries

- A research catalog entry is NOT provider data authentication, geographic permission, account eligibility, order permission or a LIVE connection. The Iran-resident futures eligibility allowlist remains unchanged.
- The Stage-12 `analysis`, `signals` and `paper` columns are **requests only**, never runtime grants. In particular `telegram_publication_enabled`, `broker_orders_enabled` and `live_trading_enabled` are always false in this phase.
- Stage-7 evaluation uses a trusted reviewed local demonstration core; Stage-4 untrusted gVisor rootless-host containment **has not passed a real adversarial acceptance test**. Never execute unreviewed third-party source as part of this test.
- Stage-10 `PENDING`, `CLAIMED`, `UNKNOWN` and `SIMULATED_ACK` are *not* actual Telegram delivery confirmations. An ambiguous claim requires manual reconciliation; it must not be automatically retried.
- Stage-9 `SUBMIT`, `ACK`, `FILL`, `CLOSE_FILL`, modeled PnL and risk release are local PAPER events, not broker fills.
- The three input DBs must be **existing, distinct, regular, operator-approved nonproduction files**. Symlinks, nonexistent files, shared roles/hardlinks, missing schemas and malformed SQLite are rejected; no auto-bootstrap or copies of real active databases are performed by the tool.
- Each DB is opened with URI `mode=ro`, `PRAGMA query_only=ON` and a stable transaction snapshot. The tool never performs `INSERT`, `UPDATE`, `DELETE`, `ATTACH`, `VACUUM`, or network calls. For high-assurance audits, supply offline snapshot copies from a tested backup procedure rather than files concurrently being changed by another process; read-only WAL connections may still rely on SQLite's OS-level shared-memory handling.

## Invariants checked

1. SQLite quick integrity and foreign-key checks plus expected schema for each stage.
2. Unique three-role evidence source, bounded rows and input size.
3. Stage-12 instance/binding and the global Stage-12 versioned hash-chain audit consistency.
4. Cross-stage core identity, instance, account, binding, provider, market, symbol; missing or orphan records rejected.
5. Identical Stage-12 requested risk fractions/order-count and Stage-8 PAPER allocation — **drift is an invariant failure**. This is not permission to copy settings into an execution journal.
6. PAPER risk reservation cannot be `RELEASED` while the position remains open; terminal orders cannot keep ACTIVE risk silently; oversized close/negative quantity refused.
7. Every Stage-9 plan/exit/bar refers to an existing recorded PAPER order; an unplanned Stage-8 order is visibly warned about.
8. Signal states refer to configured bindings; signal event SHA256 text is checked; outbox commands cannot silently reroute across channels or claim simulated delivery without a positive simulated message ID.
9. `CLAIMED` and `UNKNOWN` signal commands block integrity acceptance until manually reconciled.
10. Deterministic evidence digest of bounded observed rows; **not** a cryptographic attestation of market data, a signed research pre-registration, or actual network activity.

This stage **does not recompute full Stage-11 PnL statistics**. For economic evidence, run the existing independent Stage-11 read-only research audit on the same offline PAPER journal and study manifest. Research readiness, financial edge and product-release readiness remain separately gated.

## Reproducible safe command

Run only on a dedicated offline development workstation with explicit nonproduction state and **copies of the three local journals**:

```bash
MMT_NONPRODUCTION=1 python -m scripts.mmt_stage13_reliability_gate \
  --control-db /path/to/disposable/control.sqlite \
  --paper-db /path/to/disposable/paper.sqlite \
  --signal-db /path/to/disposable/signal.sqlite \
  --ack-offline-readonly
```

The CLI is also invocable directly as `python scripts/mmt_stage13_reliability_gate.py` with the repository root in `PYTHONPATH`, consistent with the project's existing CLI wrappers.

**Gate outputs:**

- `integrity_verdict=PASS` means *only* cross-ledger invariants for the supplied offline snapshots passed.
- `release_verdict=BLOCKED_NONPRODUCTION_UNATTESTED` is unconditional, even after perfect offline tests.
- `counts`, `warnings`, `blockers`, `evidence_digest` help operators review differences.
- `telegram_sent=false`, `broker_order_sent=false`, `production_authorized=false` are invariant outputs.

## Fault-injection and recovery acceptance

- Fresh clone/copy with no journal => blocked, not an empty “success”.
- Duplicate signal/result after restart => idempotent: no new command or receipt created.
- Changed command route or same identity with altered meaning => blocked.
- Signal command `UNKNOWN`/`CLAIMED` => no blind resend. Recovery must use separate channel evidence and human review.
- Terminal PAPER trade with active risk or open position with released budget => blocked.
- Missing order, broken cross-stage binding, stale panel revision, changed risk budget, tampered audit and signal event hash => blocked.
- Stage 5 sequence gap/quarantine and Stage 7 per-binding fault isolation remain enforced by their existing tests; Stage 13 does not change those implementations.
- Deliberately corrupted input does not trigger network operations, auto-order creation, account data reads, or writes to the supplied journals.

## Still-blocking requirements for public real deployment

1. Automatic, authenticated and **durably idempotent** integration of Stage-12 intent to actual orchestrator/adapter runtime is absent.
2. API provider authenticity, market-session/calendar, actual fair executable prices, geographic eligibility, account/position reconciliation, and proper rollback fencing have not been verified end-to-end.
3. Real untrusted-code runtime containment (rootless OCI + gVisor adversarial testing), process crash/restart soak, multi-worker concurrency and resource quotas remain unverified.
4. No real Telegram private channel verification, edit acknowledgement, delivery read-back / reconciliation, rate-limit testing or independently evidenced send.
5. Stage-11 genuine provider-data backtesting / true holdout provenance / statistically credible profitability remains unverified.
6. Operator Telegram identity, external account assets/credentials, secrets and any non-PAPER execution or distribution need a separate approved implementation and security release review.

**Expected verdict after merge + successful CI:** `STAGE13_OFFLINE_RELIABILITY_ACCEPTANCE_IMPLEMENTED` with product readiness `PRODUCT_NOT_READY_FOR_LIVE`. Stage 14 (SDK/security certification) requires its own authorization and must not be entered automatically.
