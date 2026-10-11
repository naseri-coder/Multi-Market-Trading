# Stage 8 — Independent DEMO Requery & Position Lifecycle Provenance V1

**Contract:** Offline CI and an optional, explicitly operator-enabled,
**read-only** MetaTrader 5 DEMO diagnostic. No MT5 order sending, login,
production deployment, private engine, Telegram publication or PAPER risk
mutation. No DEMO/real trade is authorized.

## What is independently reverified

The verifier reads the **existing** Stage-7 custody database with SQLite
`mode=ro` / `PRAGMA query_only=ON`; it does not run schema migrations or
create a new file, enroll a demo account, modify a receipt or release
reserved risk. It rechecks the complete Stage-7 local hash chain and
unique ticket index, locates an **exact UTC bounded window**, and makes a
**new DEMO broker API query** for precisely that window via the Stage-6
reader. The fresh normalized digest must match the stored digest
exactly, including historical order and deal payloads.

Any missing/different order, deal, price, fee, quantity, account identity,
server, DEMO trade mode, or account margin mode fails closed. A complete
requery mismatch is an error, not a replacement opportunity.

**Independence limitation:** both reads still come from the **same**
terminal and provider API. This demonstrates consistency against a
local evidence copy, but cannot authenticate a broker server, obtain a
cryptographic signature or rule out a consistently lying terminal.
SHA-256 is a local corruption indicator, not tamper-proof custody.

## Full position lifecycle inspection

After matching the exact bounded window, for every trade deal's
`DEAL_POSITION_ID`, up to an explicit maximum (20 by default), the
verifier uses the official **read-only** position filters:

- `history_orders_get(position=POSITION_IDENTIFIER)`
- `history_deals_get(position=POSITION_IDENTIFIER)`

It checks that these fresh targeted results do not omit or contradict
orders/deals known to be in the selected window, catches duplicate
tickets/foreign position IDs, notes missing historical opening orders,
and uses Stage-7's Hedging/Netting reducer to assess directional
positions, partial closes, reversals and unsupported Close By events.

Finally it queries `positions_get()` for **all active positions**, using
the stable MT5 `POSITION_IDENTIFIER` rather than `POSITION_TICKET`.
The latter can change on a netting reversal; mixing them risks falsely
considering a position closed. Hedging positions remain separately
identified even with opposite positions on the same symbol. Netting
multiple simultaneous active positions for a symbol is rejected.
Volume, symbol and side of recorded exposure are compared to active
broker observations. Unknown active exposure is flagged, never ignored.

A full matching history/active position read is still **non-atomic**:
trades may occur between those calls. Broker-side truncation may omit
earlier events even from the position-filtered result. The lifecycle
is therefore explicitly **not proven all-time**. Neither the
`content_matches_stored_window` field nor a clean diagnostics list
grants permission for account unhalting or order sending.

## Explicit local operator command

On a pre-authorized Windows machine with a locally installed MT5
terminal already configured for a DEMO account, and an operator-approved
Stage-7 custody file:

```bash
python -m naseri_markets.mt5_demo_reverify_probe \
  --connect-existing-demo-terminal \
  --account-id demo-example \
  --expected-login YOUR_DEMO_LOGIN_NUMBER \
  --expected-server YOUR_EXACT_DEMO_SERVER \
  --custody-db /path/to/existing/nonproduction-custody.sqlite \
  --start-utc 2026-10-01T00:00:00+00:00 \
  --end-utc 2026-10-02T00:00:00+00:00
```

The UTC window must **exactly match** an existing Stage-7 receipt.
The optional `MetaTrader5` Python SDK is imported only by this
opt-in CLI; it can start a local terminal via `initialize()`, so the
operator must deliberately choose this command. No password or broker
token is accepted, and DEMO trade mode, login and server are checked
before and throughout querying. The SDK connection is shut down
after the attempt. No report is emitted for a failed check.

This is *not* a recommendation to connect a live account. Never paste
actual account credentials or account data into public GitHub CI logs.

## Non-authority fields, always false

`broker_cryptographically_authenticated`
`all_time_history_proven`
`all_position_lifespans_proven`
`account_snapshot_atomic`
`may_unlock_stage4`
`may_release_paper_risk`
`may_execute_order`

This stage **does not** convert MT5 history into the Stage-4
`OFFLINE_PAPER_BROKER_FIXTURE_V1` evidence type, alter any Stage-3/4
state, remove hard halts, update position stops or send orders.

## Verification criteria

Dedicated CI runs Python compilation, strict Ruff, explicit broker
write API prohibition and all Stage 1–8 mock-provider tests. Repository
publication, legacy corpus and PostgreSQL checks must also be green
before merge.

```bash
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_mt5_demo_independent_reverify_v1.py \
  tests/unit/test_mt5_demo_evidence_custody_v1.py \
  tests/unit/test_mt5_demo_history_readonly_v1.py \
  tests/unit/test_mt5_demo_readonly_v1.py \
  tests/unit/test_paper_position_reconciler_v1.py \
  tests/unit/test_execution_position_core_v1.py \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

Verdict when green: `STAGE8_MT5_DEMO_INDEPENDENT_REQUERY_NONPRODUCTION_PASS`.
This validates an **offline simulated provider**, not a live DEMO test.

**Next separately authorized action:** isolated read-only smoke test on
an explicitly identified real-world DEMO terminal, compare window
history with local Stage-7 custody under observation, characterize
broker-specific order states, lot step and history coverage. Signed
broker attestation and actual execution risk controls remain future
work. No real/DEMO execution in Stage 8.

## Official semantics

- [MT5 historical orders by position](https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py)
- [MT5 historical deals by position](https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py)
- [MT5 all active positions](https://www.mql5.com/en/docs/python_metatrader5/mt5positionsget_py)
- [POSITION_IDENTIFIER vs position ticket](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties)
