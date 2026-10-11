# Stage 7 — DEMO Historical Evidence Custody & Hedging/Netting Diagnostics V1

**Status:** Explicitly opted-in MT5 DEMO **read-only** observation and
local nonproduction evidence storage. Nothing here authorizes or executes
trades. No production server, Telegram publisher, user credentials,
broker authentication, real-money account or existing PAPER execution
database is accessed or changed by the implementation or CI.

## Contracts and trust boundaries

New modules:

- `mt5_demo_evidence_custody_v1.py`: dedicated SQLite file (WAL, FULL
  synchronous), account enrollment tied to exact DEMO login, server,
  and broker-reported `margin_mode`. No assumption about numeric
  mode values: compare against the SDK's
  `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING` and
  `ACCOUNT_MARGIN_MODE_RETAIL_NETTING` constants; reject
  `ACCOUNT_MARGIN_MODE_EXCHANGE` and unknown/ambiguous values.
  Every process starts a new volatile read-session token following
  DEMO-only identity checks and **local chain verification**. Old
  tokens never authorize a new process to capture data.
- `mt5_demo_position_accounting_v1.py`: transparent window-only
  reconstruction. Hedging maintains separate positions by broker
  `position_id` even with opposite exposures on the same symbol.
  Netting groups by symbol, applies signed buy/sell entries and exits,
  and models `DEAL_ENTRY_INOUT` reversals conservatively. An
  unproven hedging close-by (`DEAL_ENTRY_OUT_BY`), missing earlier
  entry, direction conflict, overclose or position identity mismatch
  is explicitly flagged — no fabricated broker-confirmed position.
  Nontrade balance/correction deals remain separate from position fills.
- `mt5_demo_custody_probe.py`: optional one-shot local operator
  command; requires explicit opt-in. Uses the optional MetaTrader5 SDK,
  calling `initialize` with no login/password, then only
  `account_info`, `terminal_info`, Stage-6 historical GET/TOTAL
  functions, and `shutdown`. A real/unknown trade mode is rejected
  before any history call. No order send/check, configuration changes,
  or PAPER database writes.

## Crash consistency, anti-rollback, custody restrictions

The first accepted bounded historical window creates a deterministic
SHA-256 receipt from the complete Stage-6 normalized content, attached
to a durable account enrollment epoch. Subsequent new windows:

1. Must extend past the previous `last_end`; gaps or older windows
   are refused. A new window may overlap an older one to prove ticket
   identity and cover the boundary.
2. Repeated historical orders or deals with the same provider ticket
   must have byte-identical normalized payloads (frozen, immutable
   evidence); conflicting revisions are rejected, **not rewritten**.
3. Order/deal tickets, action ID, window digest, chained receipt,
   head and high-watermark are written inside one `BEGIN IMMEDIATE`
   transaction. Any failure rolls the complete write back.
4. Exact repeated action IDs with identical window digest replay the
   prior receipt. A changed action ID payload or reused window with a
   different action key is refused.
5. After restart, all receipt payload digests, previous hashes, chain
   hashes, receipt count, high-watermark and the complete unique ticket
   index are independently rechecked. Any inconsistency refuses new
   ingestion and diagnostic replay.
6. The custody filename must be a regular file or a new nonproduction
   file, never a symlink or directory. Database rows may contain
   sensitive account/trading details, so secure the operator's file
   permissions and backup location. No DB contents are uploaded to
   public GitHub workflows.

The SHA chain is **local integrity checking, not authentication**.
An attacker who can rewrite every row/head can forge an unkeyed
SHA-256 chain. Broker identity, real account truth, cryptographic
provider signatures, external trusted receipts, pin custody and secure
cross-host checkpoints are **not proven**.

## Operator run (only on an authorized DEMO terminal)

```bash
python -m naseri_markets.mt5_demo_custody_probe \
  --connect-existing-demo-terminal \
  --account-id demo-example \
  --expected-login YOUR_DEMO_LOGIN_NUMBER \
  --expected-server YOUR_EXACT_DEMO_SERVER \
  --start-utc 2026-10-01T00:00:00+00:00 \
  --end-utc 2026-10-02T00:00:00+00:00 \
  --custody-db /path/to/nonproduction-mt5-custody.sqlite \
  --action-id demo-capture-001
```

On the next invocation, start a window that overlaps but extends beyond
the previous end. Use the same dedicated custody database. The
operator's local SDK and terminal are required; GitHub CI uses a
provider-injected mock and **does not connect to MT5**.

## Accounting semantics and deliberate limitations

Official MT5 account property descriptions distinguish
`ACCOUNT_MARGIN_MODE_RETAIL_NETTING` and
`ACCOUNT_MARGIN_MODE_RETAIL_HEDGING`; historical deals record
`DEAL_ENTRY_IN`, `DEAL_ENTRY_OUT`, `DEAL_ENTRY_INOUT`
and `DEAL_ENTRY_OUT_BY`. Netting reversals can preserve the original
position identifier. The Stage-7 diagnostic reducer maintains signed
lots for netting, independent position IDs for hedging, cumulative
window-only entry and exit lots, VWAPs and reported
profit/commission/swap/fee. It refuses to infer unseen opening deals
outside the selected window or guarantee that those observations
represent complete current exposure.

The Stage-6 date range and TOTAL/GET checks are **not sufficient proof
of all-time history**. MT5 can return partial broker-visible history.
No live position count, account-wide balance, liquidation, broker stop
protection, close-by counterparty identification, cross-host
authenticated ingestion or authoritative MT5 lot-size normalization
is established by Stage 7.

Every output hard-codes:
`may_send_order=False`,
`may_unlock_recovery=False`,
`may_mutate_paper_risk=False` (accounting),
`may_release_risk=False` (receipt),
and `broker_authenticated=False` (custody verification).

Existing Stage-3/Stage-4 reservations, stop geometry and account
recovery fences remain unchanged. There is **no** integration
that promotes MT5 history data into Stage-4's trusted fixture.

## Validation and release criterion

Python 3.12, strict Ruff, compile and deterministic fake-provider
fault-injection tests:

```bash
python -m pytest -q --confcutdir=tests/unit \
  tests/unit/test_mt5_demo_evidence_custody_v1.py \
  tests/unit/test_mt5_demo_history_readonly_v1.py \
  tests/unit/test_mt5_demo_readonly_v1.py \
  tests/unit/test_paper_position_reconciler_v1.py \
  tests/unit/test_execution_position_core_v1.py \
  tests/unit/test_risk_portfolio_manager_v1.py \
  tests/unit/test_execution_architecture_v1.py
```

The intended verdict, only after all GitHub checks pass, is
`MT5_DEMO_CUSTODY_ACCOUNTING_V1_NONPRODUCTION_PASS`.
It does not indicate safe DEMO or LIVE trading readiness.

**Next separately authorized stage:** independent provider evidence
attestation, bounded historical requery and reliable read-only
position-lifespan provenance, then an operator-approved isolated
MT5 DEMO smoke test. Broker order dispatch remains another later
explicit authorization.

Primary MT5 references:
- https://www.mql5.com/en/docs/constants/environment_state/accountinformation
- https://www.mql5.com/en/docs/python_metatrader5/mt5historydealsget_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5historyordersget_py
