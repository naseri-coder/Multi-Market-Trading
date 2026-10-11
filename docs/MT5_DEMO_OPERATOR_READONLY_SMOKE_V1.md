# Stage 9 — MT5 DEMO Operator Read-Only Smoke Acceptance V1

**State:** nonproduction readiness tooling. Real DEMO connectivity is **NOT VERIFIED** by GitHub CI. Execution, broker login, position alteration, trade dispatch, Telegram publishing, PAPER account unhalt and live account access are forbidden.

## Goal and baseline

Stage 5 introduced active DEMO exposure observation, Stage 6 bounded order/deal history, Stage 7 durable local evidence custody, and Stage 8 independent requery. Stage 9 introduces a standalone **zero-persistence** operator smoke check that does *not* require Stage-7 SQLite evidence, accounts with previous fills, or changes to a production server.

Official Python MT5 documentation confirms `history_orders_total/get`, `history_deals_total/get`, `positions_get`, `orders_get`, `account_info` and `terminal_info`. However these docs **do not establish that our code is compatible with the operator's broker, terminal build or history visibility**.

References:
- https://www.mql5.com/en/docs/python_metatrader5
- https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py

## Strict workflow

Only on an explicitly authorized **local Windows PC / Windows VM** with a previously logged-in MT5 DEMO terminal and the MetaTrader5 Python package installed:

1. Ensure MT5 Terminal itself visibly shows a **DEMO** account. Determine its numeric login and **exact server identifier locally**; do not paste account details or terminal log files into public GitHub.
2. Ensure the historical UTC window is historical, nonempty, **no more than 24 hours**, and the terminal should contain executed DEMO deals in the chosen window if testing history schemas.
3. Perform package contract introspection **without initializing or reading the terminal**:

   ```powershell
   python -m naseri_markets.mt5_demo_operator_smoke_cli --sdk-preflight-only
   ```

4. After the operator approves the fact that MT5 `initialize()` can **start** the terminal and reuse its **last configured account**, run the one-shot read-only demo observation. The only DEMO connection flag is intentionally separate from the initialize acknowledgement:

   ```powershell
   python -m naseri_markets.mt5_demo_operator_smoke_cli `
     --connect-existing-demo-terminal `
     --ack-initialize-may-start-terminal `
     --account-id demo-local `
     --expected-login YOUR_DEMO_LOGIN `
     --expected-server YOUR_EXACT_DEMO_SERVER `
     --start-utc 2026-10-01T00:00:00+00:00 `
     --end-utc 2026-10-01T12:00:00+00:00
   ```

This step performs `initialize()` without credentials, checks official `ACCOUNT_TRADE_MODE_DEMO`, exact pinned login/server, connected terminal and known account margin mode **before history reads** and again afterward. An account switch or REAL/CONTEST/unknown mode blocks the observation. `shutdown()` is invoked in the `finally` path even on failure after the SDK was asked to initialize.

The observer captures `positions_get` and `orders_get` **before and after** a single bounded MT5 history read; any active exposure change during observation is classified `INCONCLUSIVE`, not a proven stable account snapshot. The history reader checks every declared interval count, checks time bounds and rejects duplicate tickets inside a slice or conflicting overlap data.

## Acceptance verdicts

- `PASS_DEMO_READONLY_API_OBSERVATION`: account identity, margin mode, active reads and both historical order/deal reads succeeded with at least one order and deal in the requested window, and before/after active positions/orders were consistent. **Only DEMO API read compatibility on that particular observation**. It does NOT confirm trade execution, broker correctness, complete history or risk authorization.
- `INCONCLUSIVE_NO_MATCHED_HISTORY_ACTIVITY`: calls returned correctly, but the window has no historical orders or executed deals. Empty responses do not prove the historical data schemas or position lifespan.
- `INCONCLUSIVE_ACTIVE_EXPOSURE_CHANGED`: pre/post open position or pending order records changed during the scan; non-atomic snapshot **cannot** establish a stable exposure view.
- `SMOKE_DEMO_READ_REFUSED` / `SMOKE_PROVIDER_READ_EXCEPTION`: invalid identity, unverified account mode, missing API, count mismatch, malformed data or exceptions. **No partial acceptance evidence**.
- `BLOCKED_OPTIONAL_MT5_SDK_NOT_INSTALLED`: MT5 SDK is not installed in the operator's local Python environment.

SDK-only preflight exits 0 when required callable names/constants are present, **without establishing a terminal connection**. DEMO observation exits 0 only for `PASS_DEMO_READONLY_API_OBSERVATION`, exits 3 for an inconclusive observation and exits 2 for unavailable/refused SDK operation.

All stdout observations are **redacted**: never output the expected/observed login, server, symbol, order/deal tickets, position identifiers, balances, prices or order records. The report includes only counts, bounded date window, stable content digest, margin-mode classification and diagnostic-only status. Never upload raw broker data or credentials to public CI.

## Explicit boundaries and remaining blockers

- **No actual MT5 DEMO terminal was available for this GitHub-only implementation.** The authorized connected environments belong to unrelated projects. No attempt to run MT5 or modify those environments was made.
- Even a healthy smoke session is not a guarantee of all-time history completeness, tamper-proof broker evidence, atomically captured positions, complete hedging/netting lifecycle, or permission to execute DEMO/LIVE orders.
- Stage-7 SQLite evidence custody and Stage-3/4 PAPER ledgers are **not opened or modified** by Stage 9; there is no local evidence storage. Stage 6 duplicate-ticket tightening only forbids duplicates **within a single result**, preserving legitimate overlap between contiguous slices.
- User-controlled terminal account/server must be supplied via CLI to test the actual DEMO account. Never substitute REAL accounts or create a new trading login automatically.
- A future separately authorized terminal-side DEMO run is required for `DEMO_TERMINAL_COMPATIBILITY_OBSERVED` to be considered in an external operator acceptance report.

## Offline CI

```bash
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_mt5_demo_operator_smoke_v1.py \
  tests/unit/test_mt5_demo_independent_reverify_v1.py \
  tests/unit/test_mt5_demo_evidence_custody_v1.py \
  tests/unit/test_mt5_demo_history_readonly_v1.py \
  tests/unit/test_mt5_demo_readonly_v1.py \
  tests/unit/test_paper_position_reconciler_v1.py \
  tests/unit/test_execution_position_core_v1.py \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

All GitHub CI tests use an injected fake broker **without the MetaTrader5 package, credentials or DEMO terminal**. The static source guard explicitly prohibits order dispatch/login calls in the Stage-9 modules.
