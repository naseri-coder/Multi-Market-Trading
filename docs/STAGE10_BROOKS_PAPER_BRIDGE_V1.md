# Stage 10 — Public Brooks PAPER Signal to Stage-3 simulated risk order

**Nonproduction only.** Stage 10 joins two existing components: the
SHA-frozen public Brooks V5 PAPER replay signal/evidence journal and the
independent Stage-3 risk portfolio + durable PAPER order lifecycle, then
shows the resulting state in the private Telegram administrator panel.

## Exact boundaries

- The source is a locally validated, already-persisted Brooks PAPER signal
  from the original private development state directory (custom_paper.db).
  Its canonical content SHA256, unique scan, risk geometry, receipt SHA256,
  source manifest identity, close time, exact selected timeframe/venue/pair
  and effective no-publisher/no-broker flags are independently rechecked.
  The source is locked against concurrent admin-setting changes through
  the acceptance point. No source rows are changed.
- The destination is a **different** private SQLite file named
  brooks_stage10_paper.sqlite inside the same private development directory.
  It uses existing Stage-3 configured PAPER portfolio, account, instrument
  mapping, limits and halts. Stage 10 does NOT provision risk accounts.
  External exposure must already be explicitly cleared for the offline
  fixture account. Such operator input is not broker attestation.
- This is a deterministic, idempotent one-order link for each account and
  signal; risk reservation, simulated order and link index are created
  atomically in the Stage-3 database. Identical retry reads the previous
  state, modified request conflicts and crash rolls back. It is not an
  atomic distributed transaction across the two separate SQLite stores.
- Explicit fixed-point operator quantity is mandatory. No inferred
  broker lot size, margin or fabricated balance; the existing Stage-3
  engine evaluates quantity step and portfolio, account, group and engine
  caps. The first frozen Brooks target is the Stage-3 target, with the
  rest of the signal preserved in the source receipt.
- Orders start in CREATED state, **never** in FILLED or broker-confirmed
  state. No automatic SUBMIT, ACK, FILL, CLOSE_FILL, stop fill, profit,
  real order, live trading, account login or Telegram channel send occurs.
  Separate explicit Stage-3 offline fixture injection can exercise the
  lifecycle for tests only.
- The Telegram /engines panel shows the distinct count of paper orders
  and risk reservations, and a private-admin-only read-only view button.
  Tapping a button cannot submit any order or create a risk ledger.
  No connection to historical production source and no private
  NY First-Reversal code.

## Operator walkthrough — authorized local development only

Use an already configured separate development PAPER state directory.
Ensure Brooks has a persisted validated V5 PAPER signal from manual replay
and separately configure Stage-3 with a compatible explicitly chosen
PortfolioRiskPolicy, AccountRiskPolicy and exact instrument mapping.

For read-only status:

    python -m naseri_markets.brooks_stage10_cli --status --state-dir /private/dev-state

For an *explicit* simulated risk-reserved order:

    MMT_NONPRODUCTION=1 python -m naseri_markets.brooks_stage10_cli --link \
      --state-dir /private/dev-state --signal-id VERIFIED_SIGNAL_ID \
      --account-id OFFLINE_PAPER_ACCOUNT --quantity 1.00 \
      --ack-nonproduction-stage10-paper

Environment MMT_PRODUCTION=1 always blocks the explicit link. No Telegram
token, exchange key, broker SDK or live service is required. An unconfigured
account correctly refuses.

## Validation and limitations

The test suite covers: valid frozen fixture intent -> Stage-3 order and
risk reservation; duplicate idempotency across restart; corrupted A7
digests, receipts, mismatched venue or timeframe and disabled source;
risk exhaustion, invalid quantity step, unverified exposure and privacy;
offline-only fixture order lifecycle; panel with absent or populated
Stage-3 store; and no real market, broker or Telegram route.

Local SHA digests are corruption checks, not signed provider evidence. The
live data restrictions and lack of validated Iran-resident futures venue
remain unchanged. No profitability claims. The Stage-10 gate can pass
offline without proving actual feed connectivity, operational deployment,
real order handling, or broker-side settlement.

**Verdict if CI passes:** STAGE10_BROOKS_PAPER_BRIDGE_NONPRODUCTION_PASS.
