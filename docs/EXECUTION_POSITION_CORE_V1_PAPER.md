# Execution & Position Management Core V1 — Stage 3 PAPER orchestration

**Scope and safety:** public `naseri_markets` nonproduction, offline
PAPER-only. No authenticated broker, MT4/MT5 `order_send`, real exchange
API, Telegram publication, running server, background task, migration of
existing production DB, live asset eligibility, automatic trading grant,
or change to private strategy engines. This is an **orchestration layer**,
not a trade-execution adapter and not profit/market validation.

## Why Stage 3 introduces a single SQLite transaction

Stage 1 `PositionLifecycleSimulator` and Stage 2
`PaperRiskPortfolioManager` originally each owned a distinct SQLite
transaction. A crash in between could leave a booked risk reservation
without an order, or an order state changed while risk budget still
looked unchanged. Stage 3's new
`naseri_markets/execution_position_core_v1.py` constructs both managers
on the same **dedicated** SQLite connection/file and wraps every
composite write in `BEGIN IMMEDIATE ... COMMIT`. The two existing
managers now support optional `shared_connection` and refuse mutations
outside an owner-managed transaction. Standalone behavior and Stage
1/2 APIs are unchanged.

## Atomic operations

`PaperExecutionOrchestratorV1.create(spec, action_id)`:

1. Starts one SQLite write transaction, checks global idempotency.
2. Calls Stage 2 `reserve`: rejects unknown balances/clearance,
   currency mismatch, risk exposure, correlated overlap, concentration,
   daily loss, margin and leverage model issues.
3. Calls Stage 1 `create`: records PAPER order with state `CREATED`.
4. Commits the reservation, lifecycle record, both journals and
   orchestrator receipt **together**. Any failure rolls all of them back.

`PaperExecutionOrchestratorV1.apply(order_id, action_id, event,...)`:

1. Confirms an `ACTIVE` reservation and equality of complete canonical
   original order specifications in both ledgers.
2. Validates and applies the Stage-1 simulated transition: `SUBMIT`,
   `MARK_UNKNOWN`, `ACK`, `RECONCILE_ACK`,
   `RECONCILE_REJECT`, `REJECT`, `FILL`, `CANCEL`,
   `AMEND_STOP`, `CLOSE_FILL`, `EMERGENCY_CLOSE`.
3. On a simulated close fill, records modeled *net loss magnitude*
   (and never nets profits to erase prior losses) in Stage 2 **inside
   the same transaction**:
   ```
   gross = (exit_price - average_fill_price) * filled_exit_quantity
           * contract_multiplier * (1 for LONG, -1 for SHORT)
   modeled_cost = max(average_fill_price, exit_price)
                  * filled_exit_quantity * contract_multiplier
                  * (roundtrip_fee_fraction + worst_slippage_fraction)
   loss_increment = max(0, modeled_cost - gross)
   ```
   The friction model is intentionally conservative and applies the
   stated round-trip allowance **per closed quantity**. No actual
   broker fills/fees/funding or liquidation model are used.
4. Only when status is terminal **and zero units remain open**,
   atomically releases the risk:
   `REJECTED`/`CANCELED` with 0 fills or `CLOSED` after
   confirmed simulated close quantity. Unknown submission,
   acknowledged-but-unfilled, partially filled, filled-but-open,
   canceled-with-position and failed close always **retain** risk.
5. Persists a global `action_id`+SHA-256 request digest and original
   receipt so an identical retry is harmless and a changed reuse is
   rejected without making changes.

There is **no new automatic worker**. Caller explicitly injects each
offline event. In particular `SUBMIT` records *attempted send* only,
`ACK` and `FILL` reflect test fixture evidence, and
`RECONCILE_ACK`/`RECONCILE_REJECT` require explicit evidence but
do not actually query a broker. `EMERGENCY_CLOSE` is a synthetic
one-step exit for failure tests, **not a broker-guaranteed liquidation**.
Market and limit order types are contracts, not real market/limit routing.
The system has no real order timeout scheduler.

`record_loss`, `halt`, `configure_portfolio`,
`configure_account`, `register_instrument` wrap Stage-2 changes
inside an orchestrator-controlled transaction. Halt affects **new**
risk only; a previously opened PAPER position may still be managed
and closed without relaxing the kill switch.

## Recovery, failure and tests

A restart reopens the same dedicated file and retains incomplete
submission and all reserved account/portfolio risk. A missing transport
reply never causes an automatic replay of `SUBMIT`; remote status
must be reconciled first. The two ledgers, cross-engine caps, global
idempotency keys, closed quantity and cumulative day loss use the same
SQLite durability boundary.

The focused CI suite verifies:
- risk-first order creation; atomic undo when create fails after reserve;
- submitted != acknowledged != partially/fully filled;
- unclear provider reply and forbidden duplicate send;
- protective stop tightening, failed widening and partial-fill handling;
- cancel unfilled remainder and close open quantity in multiple steps;
- modeled losses, daily loss/circuit breaker, profitable close semantics;
- failed release rollback of order status and loss postings;
- persistent unknown submission/restart recovery;
- cross-account and cross-engine correlated risk budget races;
- emergency close only in simulation; halt new risk but continue exits;
- global action-key conflicts, corrupted spec identity and invalid DB path.

Repeat on a disposable Python 3.12 runner:

```bash
python -m pip install pytest==9.1.1 pytest-asyncio==1.4.0 ruff==0.16.9
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_execution_position_core_v1.py \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

## What remains explicitly out of scope

No real authenticated account authority, payment, trading license,
operator role/access enforcement, exchange trading permissions, broker
API, leverage/margin reconciliation, stop order protection guarantee,
multi-instance leader lease, distributed cross-process reconciliation
outside this SQLite file, drawdown mark-to-market or trading edge.
Before MT5 DEMO or other broker wiring, add trusted broker order IDs,
provider-confirmed stop/TP acknowledgments, robust asynchronous
cancel-and-close management, inverse/quanto/MT5 contract normalization,
network timeout and crash fault injection, outbox/inbox persistence,
account identity/permissions and end-to-end security acceptance.

A **green CI** means `EXECUTION_POSITION_CORE_V1_PAPER_PASS` only.
It never means real, DEMO or LIVE execution readiness.
