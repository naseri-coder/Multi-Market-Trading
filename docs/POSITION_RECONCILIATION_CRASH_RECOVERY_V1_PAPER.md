# Stage 4 — Position Reconciliation & Crash Recovery V1 (OFFLINE PAPER)

**Scope:** public `naseri_markets` code and isolated, disposable test databases.
No actual exchange, authenticated MT5, trading terminal, remote network,
Telegram, production state, live order, private strategy, or production deploy
was touched. The offline mock source is NOT authoritative provider truth.

## New components

- `offline_broker_fixture_v1.py`: independent persistent SQLite *fixture*
  simulating external order/account observations. It never shares Stage-3
  SQLite tables or transactions. Its account snapshots contain a mandatory
  account identity, scope-completeness flag, revision, fresh UTC capture time,
  original order-spec digest, remote ID, cumulative entry fills/average price,
  cumulative exits/average price and terminal/working state. This ledger
  intentionally cannot execute orders, query accounts or emit external signals.
- `paper_position_reconciler_v1.py`: compares complete snapshots to all
  local Stage-3 orders for **one account**, applies only safely reconstructable
  events and checkpoint updates as one SQLite transaction, and permanently
  quarantines ambiguous changes.
- `execution_position_core_v1.py`: nested **SAVEPOINT** support for Stage-3
  actions inside one owner-controlled Stage-4 replay transaction; an optional
  Stage-4 account recovery fence in the existing PAPER `create` flow.
- Tests/CI: deterministic independent-broker failure, replay, restart,
  revision consistency, catch-up and rollback acceptance, plus regression
  suites for stages 1–3.

## Explicit opt-in and startup fence

Stage-4 onboarding is explicit. Construct `PaperPositionReconcilerV1(core)`
and call `install(account_id)`. A newly enrolled account becomes **BLOCKED**
for new PAPER orders until a complete fresh broker fixture snapshot is
reconciled. Other accounts not enrolled retain the Stage-3 standalone
behavior. Enrolled account status persists in the same SQLite risk/order
database.

Each orchestrator instance has a unique volatile instance identity; on
**every restart**, the prior successful reconciliation does **not**
authorize new orders from the new process. Fresh reconciliation must succeed
under the new instance identity. A reconciliation success makes the
*recovery fence* ready but **never resets** a Stage-2 hard stop or daily
loss circuit breaker.

This is deliberately an offline model. Do NOT configure this as a real
account gate or plug broker SDK output into it without an independently
reviewed trusted-source and authentication stage.

## What is replayed

- Ambiguous submitted orders may reconcile from explicit external
  `ACKNOWLEDGED` or `REJECTED` evidence without retransmitting `SUBMIT`.
- Cumulative *positive* new fills with provider average fill price
  are decomposed into the missing fill quantity and price. Only legal
  Stage-1 fill transitions occur.
- A provider cancellation after a partial fill cancels the unfilled
  remainder but **retains** the risk reservation while the position is open.
- A provider-reported full PAPER position close may be restored with
  the external average exit price. The Stage-3 closing transaction posts
  conservative modeled loss and releases risk **only after** the simulated
  position is fully closed.
- For partial-size fills with complete exit evidence, Stage 4 first
  simulates the cancel of the remaining quantity before simulated closing.
- Repeating the same account revision and evidence is idempotent. A
  fresh read timestamp does not change the revision/content digest.

The stage does **not** auto-resend, assume an absent provider order means
rejection, invent prices, replay remote stop orders or promise broker-confirmed
protection. Prior partially closed positions with additional external close
deltas are intentionally **not** repaired because Stage 3 does not retain
authoritative historical exit notional. Such gaps are quarantined instead.

## Fail-closed protections

Each offline account snapshot must cover **all** local orders that passed
`SUBMIT`, not merely open orders: the provider fixture represents both
open-order and terminal history. If it is incomplete, stale, forward-dated,
missing a previously submitted order, internally contradictory, from the
wrong account, or contains an untracked order, recovery **refuses** it.

The following also block reconciliation: missing risk reservation, order
spec digest mismatch, changed remote ID, declining provider account
revision, same-revision changed content digest, cumulative fill/close
regression, impossible entry geometry, unsupported late fill after a
cancel, and provider-vs-local terminal-state conflict.

A repair always runs as one transaction:
- Reconciliation applies safe Stage-3 event transitions using deterministic
  idempotency action IDs and records a single successful account revision.
- If any event fails, **all** repairs, loss postings and releases from that
  batch roll back. A separate transaction then sets the account recovery
  fence to BLOCKED, applies a **one-way Stage-2 account halt for new risk**
  and appends an audit record with the error.
- Existing PAPER positions and active risk reservations are not discarded.
  There is deliberately no automatic unhalt even if a later PAPER snapshot
  becomes consistent. Operator-authorized reset and credible provider
  provenance remain future prerequisites.

`scan(account_id, broker)` handles a simulated disconnected fixture by
quarantining the enrolled account instead of treating missing data as
zero exposure. An external record unknown to the local ledger cannot create
a position, bypass portfolio budgets or unreserve capital.

## Test gates

A dedicated GitHub workflow executes the Stage-4 tests **and all previous
Stage-1/Stage-2/Stage-3 focused suites**, isolated from the legacy
project root test configuration. It also checks Python 3.12 compilation,
Ruff, broker/network import isolation and no live `order_send`.

Reproduce in a disposable environment:

```bash
python -m pip install pytest==9.1.1 pytest-asyncio==1.4.0 ruff==0.16.9
python -m pytest -q --confcutdir=tests/unit \
    tests/unit/test_paper_position_reconciler_v1.py \
    tests/unit/test_execution_position_core_v1.py \
    tests/unit/test_risk_portfolio_manager_v1.py \
    tests/unit/test_execution_architecture_v1.py
```

Status code `POSITION_RECONCILIATION_V1_PAPER_PASS` is earned only with
green Stage-4 CI **and** repository-wide test/publication safety checks.

## Limitations before DEMO / LIVE trading

The current independent broker database is a *test double*. It does not
authenticate a provider, verify exchange-canonical trade IDs or fees, prove
whether a broker stop is actually present, reconcile mark-to-market
liquidation/margin/funding, handle partial-exit cumulative price provenance,
or independently authorize new-risk permissions. There is no signed/
timestamped trusted provider receipt, asynchronous outbox/inbox, bounded
retry/timeout strategy against a real provider, correlated crash testing on
real MT5, or operator-authorized unhalt lifecycle. Even a successful Stage
4 does **not** imply readiness for live trading or profitable performance.

Suggested Stage 5: trusted provider-adapter protocol with explicit MT5
**DEMO-only** opt-in and account identity, read-only provider reconciliation
first, followed by separately authorized order dispatch after security
validation. No Iran-resident eligibility policy is relaxed here.
