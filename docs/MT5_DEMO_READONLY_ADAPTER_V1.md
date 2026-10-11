# Stage 5 — Trusted Broker Adapter & MT5 DEMO Read-Only V1

Status: **optional, opt-in, DEMO-only observation and diagnosis**. Source code
in the public `naseri_markets` package; no production deployment, no GitHub
secrets, no credentials, no real-money account access, no Telegram signal
publication, no private engine integration and no order management API.

## Architecture and trust boundary

The purpose is to observe a demonstrably DEMO account and compare open
positions/orders against the preceding isolated Stage-3 PAPER ledger,
without trusting live broker data enough to place trades or automatically
change risk reservations.

Components:

- `mt5_demo_readonly_adapter_v1.py` — provider-injected read adapter.
  Accepts only an **already initialized** MetaTrader5 provider connection;
  calls only `terminal_info`, `account_info`, `positions_get`,
  `orders_get`, never initializes/logs in/places orders or changes any
  terminal settings. Enforces exact user-pinned **numeric login**, **server**
  and `ACCOUNT_TRADE_MODE_DEMO` account mode before AND after the two
  active-exposure enumerations. Rejects disconnected terminals, account
  switches, incomplete/None reads, invalid floats/quantities, duplicate
  tickets, missing identity or malformed order/position structure.
- `mt5_demo_exposure_audit_v1.py` — pure diagnostic report against an
  existing Stage-3/4 SQLite ledger opened as `mode=ro` and
  `PRAGMA query_only=ON`. It cannot call `create`, `apply`,
  `record_loss`, `release`, `reconcile`, `halt` or mutate a portfolio
  database. It surfaces local unmatched positions, unassociated DEMO
  exposure, missing historical order evidence, and optionally manual
  operator-supplied position/pending-order ticket bindings.
- `mt5_demo_readonly_probe.py` — an explicit **one-shot** CLI. With
  `--connect-existing-demo-terminal`, it imports the *optional* MT5 SDK
  and calls `initialize()` with **no login, password, server, or trade
  arguments**. It then reads account identity; even if the existing
  terminal defaults to a real account, no active-order or position reads
  are permitted, and the command refuses the session. It shuts down
  only its own MT5 Python SDK connection.
- Dedicated offline fake-provider tests; full previous Stage-1–4
  regression suites and CI rules still run.

**Critical MT5 behavior:** the official SDK's `initialize()` may start a
local MT5 terminal and attach the last remembered account. This CLI
therefore requires explicit opt-in and refuses all account modes except
the official DEMO constant, verified against pinned login and server
values. The Python package and an already authorized local Windows MT5
terminal must exist for a genuine DEMO read. No attempt has been made
to access such a terminal in CI.

## Explicit local DEMO observation

On a machine with locally authorized MT5 DEMO terminal and optional
`MetaTrader5` Python package already installed, an operator can run:

```bash
python -m naseri_markets.mt5_demo_readonly_probe \
  --connect-existing-demo-terminal \
  --account-id demo-example \
  --expected-login <YOUR_DEMO_LOGIN> \
  --expected-server <YOUR_EXACT_DEMO_SERVER>
```

Optionally add
`--paper-ledger /absolute/path/to/disposable-paper-stage3.sqlite` for
an **additional read-only** comparison. Use only a disposable
nonproduction ledger. This command **never writes** an MT5 order and
never modifies the SQLite ledger. Do not paste credentials into command
arguments, logs, source code, or GitHub CI secrets; the CLI has no
password parameter.

Without explicit opt-in it fails closed. Without MetaTrader5 installed,
it returns an optional-dependency error. With no terminal, disconnected
terminal, mismatched login/server, or any REAL/CONTEST/unknown trade mode,
it stops without publishing a result.

## Why this is NOT Stage-4 authoritative reconciliation

Unlike the deliberately complete offline fixture, real MT5
`positions_get()` and `orders_get()` return **current exposure**.
They do **not** include all historical orders/deals. A currently missing
order might have been filled and closed, canceled, rejected, partially
executed, or replaced; never assume it was rejected.

Accordingly `history_complete=False`, `risk_authority=False`,
`broker_execution_authority=False`, `may_release_paper_risk=False`,
`may_unlock_paper_recovery=False`, `may_execute_trades=False`.
The Stage-4 account recovery fence is **not** cleared by this adapter
and the Stage-4 fixture schema is not populated from MT5 data.

A position ticket is not necessarily the originating order ticket in MT5,
and a Stage-3 linear-paper quantity is not necessarily MT5 lot volume.
This adapter **never** invents that association. The comparison may
accept explicit, operator-verified ticket bindings and a positive
`mt5_lots_per_paper_unit` conversion for *diagnostics only*.
No correlation by symbol/magic/comment/price alone is treated as proof,
and even a clean comparison is not execution permission.

Account equality is an MT5 terminal assertion rather than signed
cryptographic broker evidence. API responses can race with changing
market state; the double identity check only detects account changes,
not a fully atomic provider-side exposure snapshot. No institutional
account authority, history completeness, stop protection, guaranteed
margin, real-time net exposure, slippage or funding truth is claimed.

## Offline acceptance

```bash
python -m pip install pytest==9.1.1 pytest-asyncio==1.4.0 ruff==0.16.9
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_mt5_demo_readonly_v1.py \
  tests/unit/test_paper_position_reconciler_v1.py \
  tests/unit/test_execution_position_core_v1.py \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

Green dedicated checks and all mandatory repository checks constitute
`MT5_DEMO_READONLY_ADAPTER_V1_NONPRODUCTION_PASS` only.

## Next separately authorized phase

A complete historical read-only order/deal ledger must be developed,
with trusted account/session identity, stable broker order/deal IDs,
monotonic journal persistence, UTC history boundaries, broker-specific
symbol/contract/lot mappings, reliable fill/exit accounting and
failure-injection before any integration with Stage-4 recovery. An
MT5 DEMO order dispatcher would require its **own later explicit
authorization** and strong protective-order/restart validation. A live
account remains prohibited.

Official SDK references:

- https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5terminalinfo_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py
- https://www.mql5.com/en/docs/python_metatrader5
