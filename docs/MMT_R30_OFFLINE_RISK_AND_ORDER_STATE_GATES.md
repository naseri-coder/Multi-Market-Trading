# MMT R30 — Fail-Closed Risk and Order-State Evidence Gate (OFFLINE ONLY)

**Status:** DRAFT, stacked on R29 Draft PR #322, not main, no exchange access, no running orders, no real PAPER, no Telegram, no autonomous trader, no infrastructure provisioning, no GitHub Actions. **R29 prospectively captured Oct20–Nov3 original-source data remain unavailable on Oct16.**

## Goal and architecture

R30 implements an *additional independent read-only risk review*, not a parallel manager or broker adapter. Reuse the already existing product authorities:

- Stage3 `PaperRiskPortfolioManager` owns portfolio/account policy, live SQLite PAPER reservations and the existing **one-way halt** of new risk. Its `risk_snapshot(portfolio_id)` is a local mutable database observation, **not an authenticated exchange balance**.
- Stage3/8/9 `PaperExecutionOrchestratorV1`, `PaperCoreRiskBridge` and `OfflinePaperPositionLifecycle` remain the ONLY owners of any actual local PAPER reservation or modeled order state. This R30 module does not invoke their mutating methods.
- Stage4 `PaperPositionReconcilerV1.fence(account_id)` must say READY, with a revision. That is an existing *local fixture-reconciliation* indication, not real broker/account independent truth.
- Stage17 `OfflineRuntimeSupervisor.health()` must expose *zero* PENDING, CLAIMED, QUARANTINED **and DONE** jobs. In this R28/R29 chain, even DONE is not independently proven cross-ledger; R30 refuses further risk until independent operator review. It does not automatically alter any jobs or issue a retry.
- The operator must provide a complete, consistent active-reservation and order-state inventory corresponding to the Stage3 snapshots. Order status `SENT_UNCONFIRMED` or `SUBMISSION_UNKNOWN`, and an active reservation without a matching known active order, fail closed. This is a local coverage assertion, not a broker-attested state.
- The Stage12 panel and operator explicitly control an `order_switch_enabled` input, and separate account/engine one-way halt declarations; even all-enabled inputs **never authorize broker API execution**.

One public API:
`evaluate_r30_offline_preorder_risk(proposal: OrderSpec, account_policy: AccountRiskPolicy, portfolio_policy: PortfolioRiskPolicy, group_id: str, active_reservations: tuple[R30ActiveReservation, ...], known_order_statuses, portfolio_snapshot, account_recovery_fence, runtime_health, engine_halted, account_halted, order_switch_enabled, operator_ack)`.

The only successful disposition is `LOCAL_MODEL_PASS_NO_RESERVATION_OR_SEND_AUTHORITY`. The result contains modeled candidate notional, stop-based max risk (with operator-declared round-trip fee and adverse slippage), and an optimistic maximum-leverage margin **proxy**, never fills, actual PnL, live authority or a token.

## Safety invariants checked

1. Strict existing PAPER `OrderSpec`, signed/orientation-correct entry, stop and target geometry, canonical Instrument quote currency and exact operator-approved account/portfolio policies; account external exposure must be explicitly marked cleared within the **local** model.
2. Portfolio `halted=false`, account/engine halted=false and `order_switch_enabled=true`; a one-way Stage3 kill switch is NOT reset here.
3. All four Stage17 statuses must be zero (including DONE with no exact Stage18 cross-ledger lineage attestation). Account Stage4 fence must match account ID and be READY with revision.
4. Every reservation belongs to an exact unique order and active state; UNKNOWN, unconfirmed, unmatched, terminal-but-reserved, repeated ID or missing order-state coverage blocks.
5. Existing active notional, modeled risk and margin must sum to the exact Stage3 `risk_snapshot()` totals and match the portfolio's order count. Per-account and portfolio daily loss totals must reconcile. **This does not eliminate TOCTOU/concurrent update risk.**
6. Prevent concurrent orders in the exact same account/market/provider/symbol, whether same or opposite direction; no Hedge-mode exception.
7. Enforce quantity step and independent Stage3 fallback arithmetic for candidate stop risk, friction, notional and modeled margin. Apply per-order, account cumulative, portfolio cumulative, group concentration, engine concentration, leverage, daily loss/worst case, number of orders and margin proxy caps.
8. Never use risk source data to infer real venue instrument contract economics, authenticated equity, liquidation buffers, Mark/funding settlement, or broker-cancel guarantees. Instrument-specific `PaperContractEconomics` may differ from this fallback calculation and must still be enforced by the original Stage3/8/9 implementation. An arithmetic pass is **not** equivalent to order admissibility in the authoritative engine.
9. All failures raise sanitized `R30RiskRefused`; no automatic retry/reconciliation, capital movement, order creation or modification.

## Limitations and release blockers

- This is an **in-memory, caller-supplied** preflight; it does not atomically snapshot independent Stage3/4/17 databases, does not attest the supplier, and does not synchronize with writers. Supplying stale or forged yet internally coherent data can make this check pass. **Never treat it as a live-trading permission gate.**
- Actual connected PAPER and LIVE need independently verified venue account/exposure, exchange-specific leverage/margin/position-mode rules, authenticated `UNKNOWN` resolution, trading permissions, atomic or compensating saga order state, frozen fee/funding/mark snapshots, and durable identity. This stage implements NONE of those.
- R29 only prepares manual frozen Brooks research decisions; no prospective Oct20–Nov3 data has been captured here, no unattended paper orders, and no profitable OOS performance evidence.
- Full repository pytest, Ruff, genuine GitHub-native CodeQL, Publication Safety, exact staged R28/R29 lineage, original real multi-day input, restart failure-injection and broker-account reconciliation require independent testing on the final R30 SHA. No GitHub Actions workflows created or scheduled.

## Manual isolated test commands, after safe checkout

    export MMT_NONPRODUCTION=1
    unset MMT_PRODUCTION
    python -m pytest -q tests/unit/test_mmt_r30_offline_risk_order_preflight_v1.py
    python -m pytest -q tests/unit/test_mmt_r29_real_source_shadow_paper_v1.py
    python -m pytest -q tests/unit/test_offline_runtime_supervisor_v1.py
    python -m pytest -q tests/unit
    ruff check naseri_markets/mmt_r30_offline_risk_order_preflight_v1.py tests/unit/test_mmt_r30_offline_risk_order_preflight_v1.py

Do not merge to main or deploy until **actual** tests and independent security gates are recorded, and prior stacked Draft dependencies are resolved. For now, `MMT_R30_OFFLINE_RISK_GATE_PROPOSED_NOT_RELEASE_READY`.
