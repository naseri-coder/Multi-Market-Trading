# Stage 20 — unified operator-driven PAPER pilot (nonproduction)

**Status: scoped installed-wheel integration candidate; full Stage-20 product acceptance NOT complete.** No production deployment, new real market feed, Telegram delivery, broker orders, untrusted plugin loading, or proof of a profitable strategy.

## What is implemented

`naseri_markets.unified_paper_pilot_stage20_v1` is a bounded, explicit, **two-binding** local acceptance journey. It reuses Stage 12 selection/revision/budget, Stage 16 orchestration, Stage 17 durable queue, Stage 19 pre-call effect intents, Stage 8/9 shared-account PAPER orders and modeled stop/target lifecycle, Stage 10 no-send signal journal, and Stage 13/19 read-only audits. It checks exact effect IDs, uniqueness across the two bindings, close-and-reopen position persistence, modeled net PnL and independent local signal toggle.

The selected **symbol and timeframe** are embedded in actual Core API bindings and order plans. This is one source-reviewed built-in *illustrative* `OfflineContractFixture`, **not** a certified Al Brooks strategy. The candle bars and provider metadata are explicitly synthetic. No real performance is established. Stage 19 tracks initial reserve/plan/dry-signal effects, **not** every later simulated fill/exit.

## Clean-wheel usage

Follow the existing Stage 15 instructions to install the separate `multi-market-trading==0.4.0rc1` wheel in an isolated Python 3.12 environment, then call from outside the repository:

```sh
mkdir -m 700 -p "$HOME/mmt-private"
MMT_NONPRODUCTION=1 python -m naseri_markets.unified_paper_pilot_stage20_v1 \
  --state-dir "$HOME/mmt-private/stage20-new" \
  --first-symbol ABCUSD --first-timeframe 5m \
  --second-symbol XYZUSD --second-timeframe 15m \
  --ack-synthetic-offline
```

Optional `--no-dry-run-signals` disables local signal journaling while both PAPER workflows still run. A **fresh** destination is mandatory: resuming a possibly crashed run is explicitly refused. No background poller or network request is started.

Success emits JSON with two CLOSED modeled trades, position net outcomes (including configured modeled costs), source/core and binding identities, Stage 19 exact-effect count (6 with no-send signals, 4 without), Stage 13 integrity, Stage 19 receipt verification and restart evidence. It always reports `telegram_sent=false`, `broker_order_sent=false`, `real_feed_used=false`, `public_release_authorized=false`, `profitability_proven=false`, and `brooks_core_api_integrated=false`.

## Recovery and trust limits

Five distinct SQLite databases are used. There is **no distributed ACID / global exactly-once** guarantee. A process crash may write one target journal before the separate receipt commit. Do not retry, reset, resend, or mark a crashed job safe automatically. Stop all writers, take consistent owner-private snapshots and use Stage 18/19 read-only reconciliation. The runner never automatically retries or authorizes replay. SHA256 chains are local integrity checks, not an external immutable attestation.

## Remaining mandatory acceptance gates

1. **Actual public Brooks Core API port and semantic acceptance:** Al Brooks is historically visible but the current module is *not* a certified `CoreManifest` implementation. Add an independently reviewed adapter and no-lookahead/equivalence tests before any claim of a Brooks trading pilot.
2. **Real end-user panel execution:** This CLI writes verified Stage 12 settings locally; it is *not* a live authenticated Telegram session or remotely managed interactive bot.
3. **Authentic market data PAPER pilot:** Provider quality, timestamps, permission/eligibility and modeled execution versus venue conditions are not established.
4. **Security and operations:** External plugin isolation, secrets, multi-worker recovery, migration and controlled deployment remain blocked.
5. **Economic validation:** Synthetic examples cannot establish edge, historical accuracy or genuine PnL.

Do not upgrade `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE` based on tests of this pilot. Preserve the legacy v0.3.2 runtime, production databases, server, old installation path and all private NY First-Reversal material unchanged.
