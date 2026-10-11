# Multi Market Trading — Stage 10: Offline Signal Lifecycle & Telegram-Shaped Outbox

**Baseline:** `main@a8618cf8846f9fac58f0e1adb7fb2a6c5074c2d1` (Stage 9).

**Scope:** one new isolated SQLite module for **OFFLINE SYNTHETIC / REPLAY** research and Telegram-like *dry-run* send/edit command previews. No Telegram API calls, messages or access tokens; no LIVE signal publication or order execution. The old public Telegram bot, legacy `SignalLedger`, production bot, private NY First-Reversal and existing SQLite databases are **not modified**. Stage 8/9 risk/execution ledgers are entirely independent.

## Dataflow

```text
Stage 7 CoreInput + validated CoreResult + CoreManifest
         |
         v
host-provided offline channel ID + PriceBasis + VolumeSemantics
         |
         v
OfflineSignalLifecycle.register() [NO execution authority]
         |
         +--> append-only revisioned signal event log
         +--> immutable preview SEND command (PENDING)
         |
         v
operator-injected replay/synthetic BidAskTick observations
         |
         +--> WAITING_ENTRY -> ACTIVE -> TARGETS_COMPLETE/STOPPED
         +--> WAITING_ENTRY -> EXPIRED
         +--> independent gross theoretical R observation (never broker P&L)
         +--> new revision, append-only audit, immutable preview EDIT command
         |
         v
claim_dry_run -> operator acknowledgment of LOCAL fake message ID
      (No Telegram calls; no actual delivery occurs)
```

## Contract

- `register(manifest,event,result,decision,channel_id,price_basis,volume_semantics,expires_at,operator_ack=True)` accepts only a *validated* Stage-3 `ENTRY_INTENT` present in a `CoreResult`, exact manifest, binding, source and identity; `DataOrigin` must be `REPLAY/SYNTHETIC`, and the host supplies the negative mock Telegram channel ID. It does not inspect any Stage-8 trade permission. Telegram publication and automatic execution are therefore **separate future activation gates**.
- Symbol/provider/setup text is bounded and refuses embedded control characters/newlines; the preview is **plain text only** and does not use HTML or Markdown parse modes.
- A single entry decision has one immutable identity over the core, version, instance, binding and decision ID. Re-registering identical data after a restart is idempotent; conflicting payload or channel is refused.
- `observe(key, instrument, tick, origin, source_ref, sequence, operator_ack=True)` accepts only exact source/binding, causal timestamps and monotonic per-signal sequence (identical duplicate suppressed, altered duplicate or sequence gap refused). No WebSocket, market-data API, feed trust, exchange session verifier or continuous polling is provided.
- For long observations, theoretical entry is touched on **ASK <= entry**, targets/stop observed on BID. For short observations entry uses BID >= entry, targets/stop on ASK. Entry tick cannot also earn target or stop credit. Stop takes precedence if quote conditions are ambiguous; adverse stop gaps use worse-than-stop quote. Targets fill equal hypothetical fractions at their target prices; final target ends the signal.
- `observed_r` is an **uncosted gross *hypothetical* observed return** divided by initial entry–stop distance, with equal target fractions. It is neither broker account PnL nor a verified realized-R of actual trades; no capital allocation, commission, slippage, funding, spread history, order book or real fills are incorporated.
- `tighten_stop_from_core` only accepts a valid `CoreResult` on `POSITION_UPDATE`, a signal-specific *hypothetical* `PositionSnapshot` whose `position_id == signal_key` and whose revision, setup, binding, initial and current stops exactly match the stored signal state; stops may only tighten and only while ACTIVE. This does **not** control broker stop orders.
- Signal updates persist SQLite state, append-only immutable revision events and SEND/EDIT commands in one `BEGIN IMMEDIATE` transaction. Repeated observations don't rewrite event history. No order or reservation tables exist in this module.
- `claim_dry_run` cannot claim EDIT until SEND has a simulated acknowledgment with a local `fake_message_id`; revisions are claimed in order. A process crash turns CLAIMED into UNKNOWN via `quarantine_inflight`; UNKNOWN is **never silently retried**. `acknowledge_dry_run` can record a *clearly simulated* receipt, and UNKNOWN requires explicit `reconciled_unknown=True`. These simulated acks are **not evidence of Telegram delivery**.

## Important restrictions and acceptance before any real Telegram integration

1. A real Telegram publisher must be an independently authorized module, using actual `getChat` / bot membership/channel permission checks, a verified non-public route and a trusted authenticated source. Operator booleans alone cannot establish these facts.
2. Real Telegram `sendMessage` / `editMessageText` requires distinct identity, callback and API response verification, rate limiting, transient and permanent error handling, and no blind retransmission after uncertain result. This stage **does not implement them**. Telegram does not provide native send idempotency keys; exactly-once cannot be asserted without reconciliation.
3. Before real feed publication, build provenance and market sessions, restart supervision, deterministic cursor/checkpoint, user authorization, multi-tenant isolation, safe secrets management, and a reconciliation protocol against Telegram's actual message ID.
4. Stage-10 uses an isolated on-disk SQLite database in a user-chosen **existing folder**, never opens the active trading database and never migrates the legacy tables.
5. `operator_ack=True` is a local testing gate **not an authentication mechanism**. There is no bridge from this module to `TelegramPrivateChannel` or `PublicSignalBot` and no ability to enable LIVE through this module.
6. No code for private NY First-Reversal is imported, executed or bundled; no strategy specific market, symbol, provider, timeframe or trading quantity appears in Stage-10 module policy.

## Deterministic acceptance

Run:
```sh
python -m pytest -q tests/unit/test_offline_signal_lifecycle_v1.py
```

Also verify Stage 3–7 regression and the complete pre-existing GitHub CI. Cases include two bindings of one core, entry + multitar exits, adverse gap stop, ambiguous spread, short side, pending expiration, forbidden control characters, rejected unverified price basis, durable idempotency after restart, message edit ordering, UNKNOWN quarantine and stopped-signal monotonicity.

**Outcome for this stage:** OFFLINE lifecycle source plus dry-run Telegram-shaped command queue, not actual Telegram publication. Mark `STAGE10_IMPLEMENTED_MERGED_NONPRODUCTION_PASS` only if GitHub PR and CI genuinely pass.

**Next step:** Stage 11 research lab or separately authorized real-message delivery adapter after independent safety prerequisites. The prior 15-stage roadmap places Strategy Research Lab next; production Telegram delivery remains separately gated.
