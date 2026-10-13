# Adapter-free offline integration boundary

Status: **GitHub-only, nonproduction; no installed strategy adapters.**

This connects previously completed software **components**, not any real trading
strategy: Stage-12 `OfflineTradingControlCenter` → Stage-16 operator-driven
`OfflinePanelPaperIntegration` (Stage-5 validated candles + Stage-7 evaluation)
→ Stage-8/9 `OfflinePaperPositionLifecycle` (risk, order plan and journal)
→ Stage-10 `OfflineSignalLifecycle` (dry-run signal outbox)
→ read-only `AdapterFreePaperRuntime.admin_preview`.

All existing per-stage checks are preserved. We do **not** modify the Al Brooks
implementation, the two owner-private NY First-Reversal strategies, or any
adapter code. No strategy source, broker API keys, market account, or Telegram
credentials are loaded. Public Custom remains a generic capability, **not a
trading core**.

## Exact activation semantics

- Constructor requires the real, individually configured Stage-12, Stage-9,
  and Stage-10 objects, a valid admin identity and an explicit operator ack.
- `status(instance_id)` reports `ADAPTER_NOT_INSTALLED` by default. The
  existence of a catalogue entry, a panel toggle or a private-owner reference
  **cannot** activate analysis, orders or Telegram.
- **The only executable allowed today** is the internal
  `OfflineContractFixture`, explicitly accepted by
  `attach_test_fixture(..., operator_ack=True)` with an exact revision and
  matching reviewed manifest. This is a test fixture, **not an added core**.
- Every executable action checks `MMT_NONPRODUCTION=1` and refuses
  `MMT_PRODUCTION=1`. Stale panel revisions revoke the fixture.
- `authorize_paper` and `replay` reuse Stage-16, rather than introducing
  a second execution/risk/decision system.
- After Stage-16 finishes, `admin_preview` reads the resulting Stage-10
  local signal and count of commands. It never calls Telegram.
- Receipt fields `telegram_sent`, `broker_order_sent`,
  `live_runtime_connected`, `feed_authenticated` remain false.

## What this is NOT

This is **not** a live Market Data Adapter, live FX/MT5 or Crypto poller,
always-on strategy scheduler, security approval for arbitrary Python, durable
cross-ledger atomic transaction, deployment, Telegram publication, or an order
execution gateway. There is no authenticated `FORWARD` feed.
Stage-16 presently supports synthetic/replay **crypto closed candles**, not
the NYFR Bid/Ask tick protocol or the NY exchange-session semantics.

The existing three separate SQLite ledgers are durable locally but not
atomically committed together; repeated exact events are reconciled by
existing idempotency contracts. An interrupted multi-ledger operation needs
independent reconciliation and cannot be advertised as all-or-nothing.

## Deferred and explicitly excluded

1. A separately authorized adapter for public Al Brooks, respecting its exact
   original rules and frozen source pin.
2. Separate owner-private NYFR R0 and First Follow-up adapters, with distinct
   IDs, strategy versions, risk scope and ledgers. No private logic in this
   public repository.
3. Authenticated real providers, broker-specific contract economics, and a
   separately certified forward publisher, after independent host/security
   reviews. Until then **all external permissions remain disabled**.

## Validation

`python -m pytest -q tests/unit/test_adapter_free_paper_runtime_v1.py`

The suite checks adapter absence and no writes, operator-only fixture,
integrated synthetic PAPER risk + dry-run signal + local preview, idempotent
retry, panel revision fencing, production denial and no broker/Telegram send.
These tests do not prove signal profitability or real execution readiness.
