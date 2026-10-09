# NASERI MARKETS A3 — Durable signal intent, private route and forward-observation ledger

Status: **PUBLIC DEVELOPMENT CODE ONLY**. A3 builds on A2 PR #127, which
builds on A1 PR #126. No merge to main, production deployment, broker or
Telegram connection, private strategy logic, or claim of profitable trading.

## Implemented

- \`SignalLedger\` (SQLite/WAL, FULL sync, user-chosen file, explicit transaction):
  durably records a forward intent with engine ID, instrument identity,
  deterministic payload digest, and *one* private-channel outbox route.
- \`record\`: the same (engine, signal ID, identical payload, identical channel)
  is an idempotent no-op across process restarts. Any collision or cross-channel
  reroute is blocked.
- \`claim\`: atomically moves PENDING → CLAIMED, for a route that still meets
  the configured safety rules and a short signal freshness age; expired
  or future-dated signals become EXPIRED and cannot be claimed. **No send occurs**.
- \`acknowledge_sent\`: CLAiMED or UNKNOWN → SENT **only on externally verified
  Telegram API message-id receipt**; no network use here.
- \`quarantine_inflight\`: on startup, CLAIMED → UNKNOWN. UNKNOWN must be
  reconciled against actual Telegram message evidence, never auto-retried.
  Exactly-once delivery across an external network is NOT guaranteed.
- \`ForwardObserver\`: simulation of a hypothetical entry using observed
  BUY=ASK / SELL=BID, with T1-only exit observations at SELL=BID / BUY=ASK.
  Computes observed R **not actual broker P&L**. Detects non-live provenance,
  mismatched instrument, timestamp gaps and replay; marks UNKNOWN rather than
  manufacturing a win/loss.
- Independent persistent (engine, signal ID) namespaces with separate summary.

## Important limitations

1. PRIVATE channel verification and trusted live-source verification are
   **caller-supplied booleans**, NOT independent network attestations. A live
   connector must call the official Telegram API and authenticated market-feed
   client with explicit evidence before these are permitted to be true.
2. No Telegram API sender/formatter/credential loader is implemented. Outbox
   claims are bookkeeping, not proof that Telegram accepted a message.
3. SQLite durability requires a **persistent writable filesystem with backups**.
   A3 does not provision storage, automatic backups, encryption or cross-host
   high availability. Cross-process SQLite locking is transactional, subject
   to usual deployment and filesystem constraints.
4. The outcome simulator does not claim fills, commissions, slippage, margin,
   realistic stop/limit microstructure, latency or exchange-grade execution.
   It requires one observed live quote at EXACT signal time; if no such
   tick exists, don't infer a fill. If a later quote gap exceeds configured
   duration, outcome is UNKNOWN, not a simulated stop/target.
5. No multi-target/trailing-exit management. Only T1 is observed.
6. A3 does NOT integrate into the legacy Brooks/FM production_source runtime.
   Existing frozen SHA256SUMS remains unchanged; A3 is an isolated module.
7. No trade secrets, private NYFR thresholds, Telegram token, channel IDs,
   live user data or broker credentials belong in the public repository.

## Next stage before private forward test

- Create authenticated market-data provider and independent verification of
  symbol properties, session calendar, market-open/holiday, clock accuracy,
  Bid/Ask freshness and data gaps.
- Verify channel privacy via Telegram getChat and safe send permissions, with
  server-side Telegram message reconciliation after ambiguous outcomes.
- Build a real transport adapter + durable backup, lifecycle worker with
  processing jobs, and immutable evaluation logs in a PRIVATE environment.
- Forward outcomes must distinguish observed hypothetical results from real
  broker fills and report UNKNOWN/gaps alongside resolved outcomes.

## Offline check

\`python -m pytest -q tests/unit/test_naseri_markets_a3.py\`.
