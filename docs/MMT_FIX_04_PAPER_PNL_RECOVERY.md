# MMT-FIX-04 — Offline PAPER PnL and recovery integrity

## Problem reproduced

In `naseri_markets/paper_order_lifecycle_v1.py`, the `performance()` view
calculated total net from stored `gross` and `modeled_cost` but returned
stored per-exit `net` values without checking that they matched. The
`reconcile_offline()` restart gate checked only total closed quantity and
risk reservation status; it did not validate realized PnL against immutable
contract economics or the separately journaled closed-bar receipt.

On a disposable SQLite database, modifying an exit's net, gross, cost, price
or quantity was accepted before this fix. This is a data-integrity problem
in the synthetic PAPER ledger, **not** evidence of a live broker loss.

## Remediation

- A **read-only fail-closed check** recomputes gross, modeled transaction
  costs and net from the recorded entry, exit, direction, quantity and the
  immutable account/contract economics.
- Each exit is linked to an exact, previously recorded bar receipt and the
  receipt's original gross/cost/net fields; unexpected, missing or altered
  exit records are rejected.
- Finite and positive lot/price requirements, nonnegative modeled cost and
  total closed quantity are checked.
- The checks run when reporting PnL and when performing an explicit,
  local-only restart reconciliation. They do not execute orders or change
  risk-release semantics.

## Acceptance scenarios

- Normal full-target PAPER exits and historical risk-release tests.
- Five synthetic PnL mutations: net-only, forged gross/net, negative cost,
  NaN quantity, forged exit price with economically matching gross/net.
- Tampered per-bar receipt, missing exit row.
- Multi-target partial close -> process restart -> explicit reconciliation
  -> final close without duplicate PnL, with released risk.
- Existing stop-first, stop-gap, idempotency, kill switch, lifecycle rollback,
  recovery and risk cap unit regressions.
- Real GitHub publication safety, CodeQL and PostgreSQL test corpus must
  pass before merge.

## Explicit boundaries

Only `naseri_markets/` and test/documentation files change. No
`production_source/`, trading engine strategy, live venue/exchange
adapter, actual customer account, or production database is touched.

The stage does **not** provide an independently signed database ledger,
cryptographic external trust anchor, or live exchange reconciliation.
An attacker authorized to rewrite all SQLite ledger tables could fabricate
mutually consistent evidence; these checks protect against accidental or
partial corruption and inconsistent accounting, not full-host compromise.
Realized PnL remains **modeled PAPER PnL**, never broker-attested returns.
