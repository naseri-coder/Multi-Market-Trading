# Multi Market Trading — Stage 9: Universal Order & Position Lifecycle V1

**Baseline**: `main@a00e020182f1a0eb1699e799add781b919249835` (Stage 8)  
**Scope**: additive, nonproduction, offline simulated PAPER only. No production services, real broker, public Telegram send, server, secret, network feed or LIVE execution.

## 1. What this stage actually does

`naseri_markets/paper_order_lifecycle_v1.py` adds `OfflinePaperPositionLifecycle`, a nonproduction extension of Stage-8 `PaperCoreRiskBridge`. It **reuses** the Stage-3 single-connection `PaperExecutionOrchestratorV1`, `PaperRiskPortfolioManager` and `PositionLifecycleSimulator` rather than creating a competing ledger or redefining risk. It accepts one **already risk-reserved** Stage-8 `PAPER_CREATED` order, checks the immutable core binding/manifest and registers an immutable multi-target plan that must match the core's original `ENTRY_INTENT` exactly. The risk engine remains the authority over account/portfolio reservations, circuit breakers and release.

No downstream execution is triggered by Stage-7 `OrchestratorReceipt` automatically. A host/operator must explicitly approve each step. Current `operator_ack=True` is **not authentication**, regulatory permission, an isolated credential vault, external fill proof or production trading consent.

## 2. Lifecycle and controls

1. `reserve_entry()` in Stage 8: model sizing and create a Stage-3 order with atomically reserved account/portfolio/core risk, **not** a fill.
2. `register_plan(manifest,event,result,decision_id,order_id,targets)` exactly validates that decision, binding, plan prices and target fractions match the signed-off simulator state; each target fraction is positive and all sum exactly to 1.0.
3. `apply_paper_event()` explicitly accepts only `SUBMIT`, `ACK`, `FILL`, `CANCEL`, `REJECT`, `MARK_UNKNOWN`, `RECONCILE_ACK`, `RECONCILE_REJECT`. The operator supplies bounded simulated evidence. `FILL` requires an entry-bar model with a future closed candle, price inside the bar's OHLC range and consistent order quantity. Simulated ACKs/remote IDs are **not genuine broker confirmations**. No `LIVE` or network path exists.
4. `step_closed_bar()` processes the next **contiguous closed crypto trade-price candle**, after the entry bar. It simulates a protective stop or ordered target fractions. If stop **and** targets can both be reached within one candle, the stop takes precedence (pessimistic OHLC tie-break). A gap through a stop uses the adverse opening price. A gap favoring a target **does not** give the strategy free improvement beyond the target price. Partial entry fills have remaining pending quantity canceled before the modeled close. No target/stop fills are credited on the entry bar. **Forex bid-only bars, options, inverse and coin-margined contracts are intentionally excluded.**
5. `apply_core_stop()` accepts the core's independently validated `MANAGEMENT_INTENT / MOVE_STOP` for the same instrument, core, setup, binding, order ID and exact Stage-3 position revision. A previously processed candle must have produced the strategy decision (no retroactive trailing). The underlying Stage-3 stop amendment rejects stop widening. The platform handles the mechanics; the core determines **when and where** to trail.
6. `apply_core_exit()` accepts the core's independent `EXIT_INTENT / CLOSE_POSITION` following an already processed closed candle. The modeled exit is at the **next** supplied candle's opening price, not the candle that generated the decision. It is a research modeling assumption, not guaranteed fill. It atomically records and releases risk.
7. `performance()` reports modeled gross, total assumed friction, net and normalized realized-R against **initial entry-to-stop risk**. It does not claim genuine broker PnL, and the existing Stage-3 daily risk breaker still records **losses**, not a reinvestment of unrealized or unverified profit.

## 3. Transaction and restart requirements

- All Stage-9 action receipts, Stage-3 order transitions, risk release/retention, target flags, cursor position and modeled exit PnL are committed within the **same existing SQLite transaction**. An injected mid-flight exception rolls everything back.
- `paper_stage9_actions` records stable idempotency keys with request digests; identical retries return identical receipts, altered retries refuse. `paper_stage9_bars` deduplicates by order/bar closing time and rejects conflicting OHLC versions.
- On process restart, nonterminal Stage-9 plans are **locked** for further mutations. `reconcile_offline(operator_ack=True)` verifies local order state, risk-reservation status and the sum of booked exit quantity before unlocking. This is **not provider-based reconciliation** and cannot validate real external orders. Unknown/contested broker position requires a future separate integration and must stay blocked from LIVE.
- A paper reservation is retained after a partial fill, an unknown send, or an open position, and is released only when Stage 3 observes its terminal PAPER event. Existing account/portfolio caps and engine correlation constraints are not changed.
- All Stage-9 mutations assume an isolated dedicated nonproduction SQLite file. They must never be pointed at actual production databases.

## 4. Exact scope and non-goals

### Included

- Exact core-to-order identity check and multi-target plan.
- Simulated submit/ACK/partial/full fill, cancellation, rejection, unknown-submission fencing.
- Causal OHLC stop-first gap-aware replay, ordered multi-target partial exits, optional core stop amendments and core-triggered next-bar exit.
- Atomic modeled gross/cost/net realized-R journal, no repeated exits across restart, explicit local reconciliation lock.
- Negative tests for malformed plans, stale position/decision, lookahead, bad time continuity, duplicate receipts, risk-release preservation and rollback.

### Not included (must not be advertised as done)

- Real exchange/broker connectivity, account identity proof or validated real fills; live order routing or true execution latency/funding/swap/FX conversion.
- A trusted real-time price source, market calendars, tradeable Bid/Ask OHLC, queue position, market impact or exchange-side stop orders.
- Permanent platform-level protection against all out-of-process or multi-worker inconsistent writes; Stage 7's orchestrator remains in-memory and does not atomically enqueue Stage 9 actions.
- A fully authorized dynamic Telegram trading panel or public plugin marketplace; Stage 4's real hostile-code containment validation is still outstanding.
- Automated venue selection or any new Iran-resident futures eligibility approval; the allowlist remains unchanged.
- Modification of the protected private NY First-Reversal source, `production_source`, Docker, live DB, manifests or environment.

## 5. Tests and merge criteria

`tests/unit/test_paper_order_lifecycle_v1.py` covers complete offline entries/exits, multi-targets, stop priority and gaps, modeled net PnL, restart locks, action and bar idempotency, authentic core API decision fencing, risk release, fail-closed missing proof, and injected crash rollback. Stage-3, Stage-8 and Stage-7 regression suites, Public Test Corpus, PostgreSQL ephemeral checks, and Publication Safety must remain green on the GitHub PR. No claim of LIVE readiness or profitability follows from these tests.

Expected software-only verdict if all pass: `STAGE9_OFFLINE_PAPER_LIFECYCLE_MERGED_PASS`. Actual broker fill or safe third-party isolated runtime must be validated in later stages.