# Stage 6 — MT5 DEMO Historical Orders & Deals, Read-Only V1

**Scope:** public `naseri_markets` only; optional local DEMO observation
and nonmutating comparison with an existing disposable PAPER ledger.
No production, terminal provisioning, trading SDK during CI, passwords,
broker orders, real-money accounts, Telegram, DB migration, stop changes,
private strategies, or relaxation of exchange-country restrictions.

## Why separate order and deal histories matter

MetaTrader 5 has two different history endpoints:
`history_orders_get(start_utc, end_utc)` provides **order records**;
`history_deals_get(start_utc, end_utc)` provides individually executed
**deal records** with `ticket`, `order`, `position_id`,
`entry`, `type`, `volume`, `price`, `time_msc` and fee/profit
fields. Position ID is distinct from original order ID; a position can
have multiple opening and closing orders, and orders can have several
partial-fill deals. In a netting account a reversal may involve
`DEAL_ENTRY_INOUT`. These identities **must not** be inferred by
symbol, price or comment.

Official references:
- https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py
- https://www.mql5.com/en/docs/python_metatrader5

## Implemented

`mt5_demo_history_readonly_v1.py`:

- Reuses Stage-5 `DemoAccountExpectation` and its two-factor
  **exact login/server + official DEMO trade-mode** guard.
- Checks connected terminal, exact demo account identity **before and
  after each history slice** and once after the last slice. A mid-query
  account switch cannot yield a "successful" snapshot.
- Requires UTC-aware timestamps (offset-aware ISO 8601 accepted); clamps
  max chunk to 1 day and max chunks to 31 by default, explicitly bounded.
  No symbol or account-level filter is applied to the history endpoints:
  returns *all* symbols in the date window (subject to MT5 terminal
  history visibility). The selected time boundaries may overlap between
  inclusive per-chunk queries; records are deduplicated by globally
  stable order/deal ticket **only when exact payload matches**.
- Uses read-only `history_orders_get`, `history_deals_get` and
  corresponding `history_orders_total`, `history_deals_total`
  count checks. If either endpoint returns None, throws, disagrees with
  count, includes malformed non-finite values, duplicates a ticket with
  different data, exceeds bounded row limits, or changes account, **the
  whole result is refused**. Nothing is partially committed or returned.
- Parses completed/historical order fields and individual trade and
  nontrade deals. Balance/credit account events are not incorrectly
  treated as price-action fills; negative commission, swap, profit and
  fees remain supported.
- Captures deterministic digest of account, bounded history window and
  ordered rows, excluding the local observation time.
- Explicitly marks `window_complete=True` only for successfully checked
  endpoint returns for the selected window, and always
  `all_time_history_complete=False`. Broker-side censorship, terminal
  history settings and truncation undetectable by the SDK count calls
  cannot be ruled out. Count agreement is a local consistency check,
  **not cryptographic proof of completeness**.

`mt5_demo_history_audit_v1.py`:

- Correlates each deal with its independent order and position identity.
  Builds per-position opening/closing lot totals, volume-weighted prices
  and broker-reported net `profit + commission + swap + fee`
  **restricted to the queried window**.
- Flags entry outside window, missing order in history, reversal and
  close-by events, partial/unknown history and impossible cumulative
  consistency.
- An optional existing Stage-3 PAPER SQLite file is opened using
  `mode=ro` and `PRAGMA query_only=ON`; zero local writes.
- **Never** makes implicit lot/unit conversions. `HistoricalTicketBinding`
  takes manually verified PAPER order ID, MT5 opening order ticket,
  MT5 position ID and decimal lots per PAPER unit. The output reports
  mismatching cumulative entries/exits or missing proof; it does not
  mutate or release any PAPER positions.
- Even with zero discrepancies, does **not** assert that full account
  history is proven or unhalt/release risk. `may_execute_trades=False`,
  `may_release_paper_risk=False`,
  `may_unlock_stage4_fence=False`, and
  `may_publish_signal=False` unconditionally.

`mt5_demo_history_probe.py`:

One-shot **explicit opt-in** and optional MT5 SDK import. Only
`initialize()`, read-only historical/identity calls, `shutdown()`
of its own SDK connection. SDK initialize can start the local terminal
using its last account, so the DEMO-only guard prevents reads from
any live/unknown account. The CLI does not accept credentials.

On an operator-owned, pre-authorized Windows MT5 terminal with a
DEMO login and optional `MetaTrader5` Python SDK already installed:

```bash
python -m naseri_markets.mt5_demo_history_probe \
  --connect-existing-demo-terminal \
  --account-id demo-example \
  --expected-login YOUR_DEMO_LOGIN_NUMBER \
  --expected-server YOUR_EXACT_DEMO_SERVER \
  --start-utc 2026-10-01T00:00:00+00:00 \
  --end-utc 2026-10-08T00:00:00+00:00
```

Optionally add `--paper-ledger /absolute/path/to/disposable-stage3.sqlite`
for a **read-only**, unbound diagnostic comparison; manual binding
configuration is supported in the Python API, not accepted via insecure
CLI text. JSON is printed to stdout *only after* the full checked window
completes. This can reveal sensitive broker trade data to the local
console; do not put JSON stdout in public build logs or tickets. Avoid
placing account numbers in screenshots or GitHub issues.

## Important remaining gaps

- Not verified on a real DEMO terminal or broker; GitHub CI uses
  provider-injected deterministic fake MT5 only.
- Broker `history_*_total` matching `history_*_get` is **not**
  absolute all-history assurance. No signed provider snapshot,
  cursor authority, monotonic account revision, persistent outbox,
  durable ingestion, full broker fee normalization or contract mapping.
- Time slices are bounded; rows that entered outside the queried window
  must be fetched in a larger *explicit* range to establish full
  position lifespan.
- Reversals, close-by, hedging/netting aggregation, partial historical
  exit provenance and account-level balance transfers require further
  isolated research before a recovery engine can apply broker history.
- These data are **never** passed to Stage 4's
  `OFFLINE_PAPER_BROKER_FIXTURE_V1` source. No automatic Stage-4
  reconciliation, reserve release or eligibility decision is enabled.

Test suite (offline GitHub CI, no MT5 installed):

```bash
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_mt5_demo_history_readonly_v1.py \
  tests/unit/test_mt5_demo_readonly_v1.py \
  tests/unit/test_paper_position_reconciler_v1.py \
  tests/unit/test_execution_position_core_v1.py \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

A clean CI is `MT5_DEMO_HISTORY_READONLY_V1_NONPRODUCTION_PASS`
**only**. Stage 7 recommendation: broker-history evidence custody,
stable session/account epochs, restart-safe ingestion and independently
verified netting/hedging position accounting, **still DEMO-only**.
