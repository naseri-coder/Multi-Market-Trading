# Stage 3 — Brooks closed-candle PAPER evidence, risk receipts and restart

Stage 3 extends the installed development product without changing the
SHA256-frozen Brooks V5 engine or entering production. The original V5
signal geometry, setup thresholds and execution contract remain unchanged.

## Pipeline implemented

1. An authorized **PAPER** request uses validated finalized candles (the
   independent provider feed verifies candle continuity/finality) or an
   explicit offline replay. The actual frozen Brooks V5 worker evaluates
   its original rules and source snapshot.
2. The analyzer result is checked for engine version, snapshot hash/time,
   symbol/provider, configuration, signal geometry and engine revocation.
   A `NO_SIGNAL` result is treated as an auditable scan, not a fake trade.
3. For `LONG` or `SHORT`, the existing `SignalIntent` contract enforces
   strictly positive finite entry/stop/targets and correct direction.
   Stage 3 additionally **calculates**, but does not optimize or threshold,
   the risk per unit `abs(entry-stop)` and each reward multiple
   `abs(target-entry)/risk`. These are diagnostic measurements, not new
   permissions or profitability assertions.
4. Inside the **same SQLite BEGIN IMMEDIATE transaction** as the existing
   Brooks snapshot journal and A7 PAPER signal intent, store exactly one
   signed SHA-256 `brooks_paper_receipts` row for each new scan.
   It includes close time, provider, exchange, symbol, quote, timeframe,
   decision/outcome, source manifest identity, signal ID and risk details.
   All permissions to send Telegram or broker orders are `false`.
5. A duplicate scan keeps the previous journal and receipt untouched.
   A failure writing the receipt rolls back the entire new scan and
   PAPER intent; no partial success. Reopening the development database
   after an unclean exit cannot create another record for the same
   deterministic scan ID. Historic scans from before this stage stay
   readable, but are **not falsely backfilled** with evidence.
6. `/engines` Brooks private details display total new receipts and the
   latest validated scan plus target R where present. `mmt-dev status`
   shows the latest full receipt and counts; `mmt-dev receipts` returns
   a strictly bounded (1–30) local read-only list. SHA-256 integrity
   discrepancies are refused, not silently displayed.

## Explicit scope and compliance limitation

The 2026-10-11 approved Iran-resident futures exchange list remains
**empty**. Therefore the actual online standalone PAPER worker stays IDLE
and no new live market feed or Telegram publishing is activated. The
independent, explicitly fed OFFLINE replay path is used in stage 3 CI
to exercise the real frozen Brooks core end-to-end with synthetic
validated candles. Mock LONG transport-contract tests verify risk R and
transactional signal recording; they **do not** claim that the real
strategy naturally found a profitable setup on those fixtures.

This stage does not add or retune risk thresholds, change trading PnL,
place broker orders, request keys, contact Telegram, run production,
migrate PostgreSQL or bundle private NY First-Reversal.

## Operator commands (isolated development only)

After Stage 1's isolated installer with `MMT_NONPRODUCTION=1`:

```bash
"$HOME/mmt-product-dev/mmt-dev" status
"$HOME/mmt-product-dev/mmt-dev" receipts --limit 8
```

To create an actual new PAPER audit record offline, the existing Brooks
admin state must be expressly enabled for PAPER, and
`naseri-brooks-replay` must be called with a genuinely validated local
closed-candle replay and the SHA-pinned `production_source`.
No background schedule or live feed is started by these commands.

## Gate to stage 4

Before any real end-to-end online signal operation, a provider must
be independently verified as legally available for Iranian-resident
futures trading, provide validated contracts/market data, and pass
fresh-candle source identity, failure recovery and revocation tests.
Real Telegram signal publishing needs **separate explicit authorization**,
durable delivery/reconciliation safeguards and its own nonproduction
acceptance stage.
