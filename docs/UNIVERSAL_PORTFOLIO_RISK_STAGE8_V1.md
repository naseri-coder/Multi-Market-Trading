# Multi Market Trading — Stage 8: Universal PAPER Core Allocation & Risk V1

**Baseline:** `main@b33daf127dcc7cab571d3c0a2ad8bed5ed45089e` (Stage 7)  
**Mode:** OFFLINE/NONPRODUCTION, operator-controlled. No production deployment, market API, broker/MT5 orders, Telegram channel sending, private NYFR core or live account.

## 1. Objective and reuse

Instead of implementing a competing engine, `naseri_markets/paper_core_risk_bridge_v1.py` reuses the EXISTING tested `PaperExecutionOrchestratorV1` and `PaperRiskPortfolioManager`. Stage 8 adds a durable **per-core-instance / per-account** allocation layer, with multiple bindings (symbol/timeframe) sharing ONE core-instance budget. The preexisting Stage 3 account, portfolio, group and engine caps are always additionally enforced.

```
Stage 7 validated CoreResult + original CoreInput + manifest (OFFLINE only)
                  |
           EXPLICIT operator PAPER request: decision_id, quantity, policy revision
                  |
       Stage 8 persistent allocation + exact binding + provenance checks
                  |
       SQLite BEGIN IMMEDIATE: instance budget + Stage 3 shared budget
                  |
        Stage 3 CREATED order + ACTIVE risk reservation + Stage 8 journal
                  |
       local PAPER receipt only; NEVER submits, fills or sends Telegram
```

### The core NEVER sets account capital

An operator registers the `CoreCapitalAllocation` independent of the strategy code: `instance_id`, immutable `core_id/version`, `account_id`, `portfolio_id`, maximum **instance aggregate modeled risk**, **instance notional**, **per-order risk** and **active orders**. These ceilings are expressed as Decimal fractions of the selected account's current **operator-configured model equity**. Multiple symbol/timeframe bindings can share the same instance. Other instances can use the same account, but Stage 3 computes aggregate reservations atomically.

Leverage, multiplier, quantity step, account equity, estimated friction, account/portfolio and correlation caps come from the independently configured Stage 3 risk policy, not the strategy. `CoreCapitalAllocation` is immutable after registration to avoid silently widening a budget. Disable/enable is a revisioned CAS with explicit local operator acknowledgement. This acknowledgement alone is NOT authorization/authentication for public users; an authenticated administrative interface must precede production exposure.

## 2. Admission and safety invariants

1. The Stage 8 bridge operates exclusively on an explicitly designated disposable **PAPER SQLite file**; NEVER point it at legacy PostgreSQL, existing production SQLite, or a live account.
2. Stage 3 account and portfolio policies and exact instrument correlation groups are configured separately first. Account `external_exposure_cleared` must be explicitly true, but this is an **operator assertion, not provider-side reconciliation**.
3. Both `CoreManifest` and `CoreBinding` are pinned by content digest at registration, not by matching the core name alone. Unknown/modified binding, wrong version, cross-account and cross-market attempts fail before reservation.
4. `CoreInput` and `CoreResult` are revalidated with `validate_core_result`. Only exact `ENTRY_INTENT` is accepted; setup candidates, no-setup, management and exit decisions cannot create Stage 8 orders.
5. Only `DataOrigin.SYNTHETIC` or `REPLAY` is supported. For CRYPTO candle events, the price basis must be `TRADE` and volume semantics `TRADED`. For FOREX, ONLY explicit offline Bid/Ask **tick** event is admitted; bid-only OHLC candles are rejected for executable-entry modeling. INDEX/METAL and mark/index-price decisions remain out of scope. These are metadata assumptions, NOT proof of real executable price or broker permission.
6. The operator supplies an explicit positive fixed-point `Decimal` quantity. No guessed margin, MT5 lot size, contract multiplier, exchange tick size or fills; Stage 3 checks its configured quantity step, currency and portfolio limits.
7. Model per-order risk includes stop distance plus configured roundtrip fee and slippage; both the instance budget and Stage 3 account/portfolio/correlation limits are checked inside ONE serialized SQLite transaction. No changes are written if any check rejects or a later simulated-order operation crashes.
8. Each `(binding_id,decision_id)` has one immutable digest/receipt/order ID. Same request returns the same receipt across restarts even after disable; changed payload or sizing fails. Stage 8 does NOT rely on Stage 7's bounded in-memory dedup. There is NO automatic CoreResult dispatch from Stage 7 to Stage 8.
9. Stage 3's `CREATE` leaves the simulated order CREATED with zero fill. All risk remains ACTIVE until separately verified Stage 3 terminal PAPER lifecycle events release it. No auto stop/target fills or external broker action.
10. Stage 8 never changes existing Stage 3 schema or production source: adds four namespaced tables **inside its separate disposable Stage 3 PAPER database**, and reuses its executor via the same SQLite connection. It cannot make independent calls to trading terminals or Telegram.

## 3. Atomicity and limits

`reserve_entry()` wraps the entire Stage 8 operation using Stage 3's `PaperExecutionOrchestratorV1._transaction`, which acquires `BEGIN IMMEDIATE` on the shared SQLite database. Stage 3's `create()` uses a nested SAVEPOINT. The persistent `paper_core_orders` rows are joined to the existing `paper_risk_reservations` ACTIVE rows when computing the per-instance budget. Therefore, a released order no longer consumes instance capacity, while orders from different instances still count towards the Stage 3 shared account/portfolio risk.

A mid-transaction exception rolls back Stage 8 mapping and Stage 3 reservation/order creation together. The request is durable once committed. Cross-process serialization relies on SQLite write locking, not a threading mutex, and is only appropriate for local, nonproduction PAPER experiments. This is not a multi-node distributed reservation protocol.

### Existing risks that are NOT solved

- A fabricated `CoreResult` by a malicious administrator can have a structurally valid digest. Neither content hashes nor `operator_ack=True` establish source/authenticity, broker eligibility or strategy profitability. Durable signed observation receipts and properly authenticated operators remain future work.
- A separately authorized caller could bypass Stage 8 by directly invoking Stage 3 APIs, because Stage 8 is a product composition, **not an OS security perimeter**; do not expose its database or Stage 3 direct commands to untrusted users.
- Stage 3 account equity is a static operator snapshot. No live balance, open-broker-position reconciliation, slippage model attestation, order-book depth, multi-currency conversion or portfolio volatility estimate has been added.
- This stage does not grant market data access or residency-based futures availability. Iran-resident verified futures venue allowlist remains untouched and empty.
- Stage 7 orchestration status is in-memory; Stage 8 only journals submitted decisions, not all analyses. Coupling them automatically requires a durable message/outbox contract and independent safety approval.
- The former Stage 4 hostile-code isolation has not been adversarially verified on a dedicated host.

## 4. Verification and release criteria

- Targeted suite `tests/unit/test_paper_core_risk_bridge_v1.py`: two-instance/account aggregation, binding isolation, exact-once across restart, revision fencing, stopped allocation, per-order/instance/group/account limits, risk rollback on simulated crash, price-basis restrictions and default denial.
- Regression: previous Stage 3 position + risk suites, Stage 3–7 target suites, publication safety, full public corpus where available.
- Verify a clean wheel import and no changes to legacy `production_source/SHA256SUMS`, `trusted_custom.py`, exchange eligibility, broker/Telegram runtime, private NYFR.
- No live balances, no Telegram channels, no API keys, no orders, no deployed service.

**Expected verdict only after review/tests:** `STAGE8_PER_CORE_RISK_NONPRODUCTION_PASS`. It never means the general-purpose live portfolio engine is finished.