# Risk & Portfolio Manager V1 — PAPER-only, multi-engine risk budget

**Scope:** isolated, nonproduction development only. This is Stage 2 after
[Execution Architecture V1](EXECUTION_ARCHITECTURE_V1_PAPER_SIMULATOR.md).
The new module is **not connected** to trading, real broker accounts, the
public Telegram bot, any active Brooks signal flow or private NYFR engine.
There are no trading credentials, HTTP calls, database migrations, deployed
services, or automatic-live trading grants.

## Frozen contracts

Files:
- `naseri_markets/risk_portfolio_contract_v1.py` — validated
  `PortfolioRiskPolicy` and `AccountRiskPolicy` with finite Decimal
  amounts, notional, leverage and modeled margin boundaries.
- `naseri_markets/risk_portfolio_manager_v1.py` —
  `PaperRiskPortfolioManager`: local SQLite transaction ledger, aggregate
  risk decisions, cross-engine/account concentrations, intraday loss
  recording and one-way new-risk halts.
- `tests/unit/test_risk_portfolio_manager_v1.py` —
  deterministic safety and concurrency acceptance.
- `.github/workflows/risk-portfolio-v1.yml` —
  code safety, full Stage-1 compatibility and offline checks.

All amounts are in **one explicitly declared quote currency** per portfolio.
No currency conversion, inverse contracts, coin margined futures, dynamic
contract specification, Netting/Hedging broker semantics, risk oracle,
authenticated account balance or guaranteed margin calculation is claimed.
Each instrument must be bound to an **immutable operator-defined correlation
group** before it can consume budget, preventing a strategy from reclassifying
its own group at order-submission time.

## Policy evaluation (every new reserve, atomically)

V1 fails closed on missing account, portfolio, instrument map, non-PAPER
order, currency mismatch, unverified outside exposure, mismatched lot step,
duplicate order identity, active halt, stale/backward trading day or any cap.

The *entire* account/portfolio check and insert executes inside an SQLite
`BEGIN IMMEDIATE` transaction; two separate connections cannot both reserve
against the same pre-reservation balance.

For linear PAPER fixtures:

```text
notional = quantity * reference_entry * contract_multiplier
worst_case_risk = quantity * contract_multiplier *
    (abs(reference_entry - stop)
     + reference_entry * (roundtrip_fee_fraction + worst_slippage_fraction))
modeled_margin = notional / max_leverage
```

Account caps:
- Per-order risk as equity fraction.
- Total risk reserved across all engines' active orders.
- Daily loss + worst-case open reserved risk.
- Total notional and modeled margin as equity fractions.
- Account active-order count.

Portfolio caps:
- Total reserved risk, notional and active order count across accounts.
- Daily realized loss magnitude + modeled worst-case reserved risk.
- Per-correlation-group risk, including across engines and accounts.
- Per-engine concentration across the entire portfolio.

**Exposure truth fence:** `external_exposure_cleared=True` is an
explicit, operator-supplied *PAPER-only assertion*, not an actual reconciled
broker position query. With false/missing value, new reservations fail closed.
There is currently no authenticated source for free margin, maintenance
margin, broker stop execution, fees, realized P&L, funding or correlation
measurement. The rules therefore prove *internal budget correctness only*,
not real-world loss limits.

## Persistent state and release semantics

A successful risk reservation is journaled as `ACTIVE` until a separate
terminal PAPER lifecycle snapshot is presented. `SENT_UNCONFIRMED`,
`SUBMISSION_UNKNOWN`, `ACKNOWLEDGED`, partial fill, filled-but-open, or
cancel-with-partial-position all **retain** the risk reservation. A release
requires the *entire Stage-1 order spec identity* to match plus a terminal:
- `REJECTED` and zero fill;
- `CANCELED` and zero fill;
- `CLOSED` with all executed quantity fully closed.

An evidence string is mandatory. The caller-provided snapshot and string
cannot be cryptographically authenticated in Stage 2, so this is **offline
integration evidence only**. Live release must later be driven from
authenticated provider reconciliation and a unified transactional order /
risk ledger; do not trust arbitrary users or HTTP callers with these
methods. There is no cross-DB commit between Stage-1 simulator SQLite and
this separate risk SQLite.

Each mutation of a reservation, cumulative loss or halt uses a unique
global action ID, request digest and immutable receipt. Identical replay
is harmless; an action reused with a changed payload is denied. Audit
events are persisted for initial configuration, instrument mappings,
reserves, terminal releases, loss updates and killswitch actions.

Losses are nonnegative, *cumulative* magnitudes per account and UTC day
(the system does not net hypothetical gains to erase a breaker). Daily
counters roll over at UTC midnight based on the **injected clock**; a
clock rollback is rejected for new mutations. Operator halts NEVER
automatically reset. Halt scopes: portfolio, account or engine; each
blocks **new** risk but **never** erases existing reservations or changes
close-management rights. V1 intentionally has no unhalt or policy limit
relaxation command.

## Acceptance

Run on a disposable Python 3.12 environment:

```bash
python -m pip install pytest==9.1.1 pytest-asyncio==1.4.0
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

Cases cover both original stage 1 and new policy contracts, correlation
and engine concentration across accounts, per-order and account caps,
instrument mapping immutability, unknown outside exposure, cumulative
loss and UTC rollover, one-way halts, idempotency, forged/replayed
release data, partial-fill risk retention, recovery after restart, and
concurrent SQLite connections racing against a shared risk ceiling.

`RISK_PORTFOLIO_V1_PAPER_PASS` is valid only after the focused GitHub
Action **and** repository publication-safety/full test checks are green.
It must **never** be described as authenticated capital protection,
provider-verified margin, trade execution, profitability or production
readiness.

## Explicitly deferred

1. Atomic coupling to Stage-1 actual simulator order creation, submission,
   and terminal state (Stage 3 lifecycle orchestration).
2. Venue-specific price/quantity tick normalization, minimum notional,
   contract multipliers and account-mode negotiation.
3. A trusted, authenticated authoritative portfolio equity, free-margin,
   liquidation and position reconciliation service; explicit quote
   currency conversion and daily loss sourcing from execution fills.
4. Mark-to-market exposure, correlation estimation, funding, fees, true
   broker-confirmed stops and emergency liquidation; monitoring.
5. Admin authentication/permissions for risk policy and killswitches.
6. Separately authorized DEMO MT5 execution and later crypto adapters,
   and then forward testing; live accounts are NOT permitted by this PR.

Existing Iran-resident futures-eligibility restrictions remain unchanged.
