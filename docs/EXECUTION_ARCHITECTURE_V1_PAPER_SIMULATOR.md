# Execution Architecture V1 — common PAPER order and position lifecycle

**Scope:** independent, standard-library-only prototype in the public
`naseri_markets` package. No production app, private engine, Binance/MT5
trade API, real order, Telegram publication, deployment or runtime activation
is authorized by this change.

## Modules

- `naseri_markets/execution_contract_v1.py`: canonical order identity
  (`order_id`, `signal_id`, `account_id`, `engine_id`, and
  market/provider/symbol), order kind (MARKET or LIMIT), direction, quantity,
  reference entry, stop, target, and PAPER evidence mode.
- `RiskEnvelope` and `size_linear_paper_order`: Decimal-only,
  conservative **linear quote-settled** quantity sizing based on stop
  distance, fee+slippage allowance, account equity and outstanding
  operator-supplied reservations, daily realized-loss limit, leverage and
  notional ceiling. Quantity always rounds **down** to a supplied lot step.
  Errors deny sizing. These calculations are *not* integrated account
  margin verification or a grant for any restricted exchange.
- `naseri_markets/position_lifecycle_simulator.py`: explicitly injected
  outcome events with an atomic SQLite order projection and append-only event
  receipts. Neither module imports any authenticated trading client.

## Order state machine

```text
CREATED --SUBMIT--> SENT_UNCONFIRMED --ACK(remote_id)--> ACKNOWLEDGED
                        |                           |         |
                        +--MARK_UNKNOWN--> SUBMISSION_UNKNOWN |
                        |                     |               |
                        +--REJECT--> REJECTED |               |
                                              |               |
                     RECONCILE_ACK(evidence + remote id) ------+
                     RECONCILE_REJECT(evidence) --> REJECTED

ACKNOWLEDGED --FILL(partial)--> PARTIALLY_FILLED --FILL(rest)--> FILLED
      |                              |
      +--CANCEL--> CANCELED <--------+
                       |                  FILLED
                       +--CLOSE_FILL----------+--> CLOSED (zero open quantity)

FILLED/PARTIALLY_FILLED/CANCELED --EMERGENCY_CLOSE (simulated)--> CLOSED
```

The journal distinguishes *intent creation*, *submission attempted*,
*remote acknowledgement* and *actual executed quantity*. The operator
must reconcile an unknown submission before any further progression:
the simulator **refuses resending** the same order. Only verified
remote-order evidence should ever be injected into reconciliation
events; this first stage does **not** query exchanges.

A partial fill immediately creates an open simulated position with the
original protective stop. A partially filled order cannot receive a
regular CLOSE_FILL until the remaining unfilled quantity has been
canceled. Completed and canceled orders may still contain an open
position, represented separately by `open_position_quantity`.
Stop amendments can only tighten the initial protection. Every
mutation requires an `action_id`. An identical replay returns its
original receipt; a reused ID with different payload is refused.

`EMERGENCY_CLOSE` is a **single synthetic fill** for offline failure
rehearsals. It does NOT prove broker cancellation, protective-order
execution, guaranteed liquidation, slippage, netting or hedging
semantics, or a settled P&L. A real adapter must model asynchronous
cancel acknowledgement and confirmed close fills separately.

## Acceptance and evidence

Run on a clean Python 3.12 development runner:

```bash
python -m pip install pytest==9.1.1
python -m pytest -q --confcutdir=tests/unit tests/unit/test_execution_architecture_v1.py
```

Covered: fail-closed PAPER contract, long/short geometry; stop-aware
risk quantity, fee/slippage, daily loss and account exposure refusal;
send without acknowledgement; unknown transport result and
evidence-gated reconciliation; partial fill/overfill; protected stop,
stop tightening and rejection of widening; cancel/partial close and
simulated emergency flatten; idempotency/replay conflicts;
persisted unknown status after restart; atomic rejected transition;
and separate account identities. The PR also runs the repository's
existing full public test corpus.

## Mandatory later stages — NOT approved or implemented here

1. **Risk & Portfolio Manager:** authoritative account equity, available
   margin, per-venue multipliers, minimum contract amounts, reserved
   exposure across all orders, multi-engine correlations, realized daily
   losses, and atomic risk budget reservation across processes.
2. **Execution & Position Core:** write-capable order state transitions
   anchored in real venue confirmations, stop/TP registration, timeouts,
   partial close, OCO semantics, netting vs hedging, fees and funding.
3. **Account reconciliation:** authenticated order/position/history API
   with stable exchange IDs, stale-evidence protection and deterministic
   recovery from crashes between network send and local commit.
4. **Fault injection and forward testing:** network drop, duplicate
   message, out-of-order provider event, conflicting fills, live-like
   broker rejection, process crash and durable outbox/inbox.
5. **MT5 DEMO adapter:** isolated agent, operator-approved execution,
   broker metadata discovery, demo-only credentials and account-mode
   negotiation. MT4 and crypto-exchange adapters are **separate** phases.

The existing `mt5_readonly_bridge.py` remains strictly read-only.
Iran-resident futures-eligibility restrictions remain unchanged.
There is no Auto Live setting, API-key integration, operator command,
bot-menu action, or background worker enabled by this stage.

**Verdict target:** `EXECUTION_V1_PAPER_SIMULATOR_ACCEPTANCE_PASS` only
if the focused tests and required PR checks pass. It must never be
interpreted as LIVE_EXECUTION_READY or PROFITABILITY_VERIFIED.
