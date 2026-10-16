# MMT-PAPER-07 — genuine frozen Brooks replay to existing Stage10 PAPER risk

**Scope:** explicit, offline, non-root operator workflow for the reviewed historical public Brooks V5 engine. This stage wires **existing** `brooks_replay.replay_once()` directly to **existing** `BrooksStage10PaperBridge.link()` through the pre-existing `brooks_stage10_cli`. It creates **no new core, account authority, database, broker/exchange client or worker daemon**. The 359-entry frozen Brooks manifest and three separately pinned public additions remain unchanged.

## Installation and prerequisites

**Required extra:** install the separate platform wheel with the explicit **brooks-offline optional dependency group**, matching the complete pinned v0.3.2 historical import closure. Frozen V5 imports legacy SQLAlchemy, settings and Telegram modules even when no database server, Telegram transport or provider network is used. The normal platform wheel still declares **zero required dependencies**, and these packages are activated only for the explicit legacy-offline compatibility path.

Install the isolated `multi-market-trading==0.4.0rc1` wheel and use a dedicated, owner-private **non-root** test directory on a disposable machine. The original `production_source/` remains an **external**, SHA-pinned local checkout; it is not bundled in the public wheel.

The operator must separately prepare the existing Brooks OFF/PAPER engine settings, a compatible Stage3 simulated portfolio/account/instrument and an authentic, strictly closed-candle **offline** replay JSON with 60–256 chronological bars. No accounts, risk balances or permissions are created or presumed automatically.

## Explicit offline invocation

```sh
MMT_NONPRODUCTION=1 python -m naseri_markets.brooks_stage10_cli \
  --replay-and-link \
  --state-dir /private/development-state \
  --legacy-source /reviewed/production_source \
  --replay-file /reviewed/closed-bars.json \
  --account-id configured-paper-account --quantity 1.00 \
  --ack-real-brooks-offline \
  --ack-nonproduction-stage10-paper
```

A successful **genuine Brooks NO_SIGNAL** stores its actual scan/receipt and returns `paper_order_created=false`, with no simulated order and no synthesized signal. Only if the SHA-verified historical engine actually emits a properly validated LONG/SHORT signal can the pre-existing Stage10 bridge reserve *modeled* risk and create a `CREATED` PAPER order, using the already configured account. It **never** marks the order SUBMITTED, ACKed, FILLED or CLOSED automatically. A re-evaluated, unchanged signal can reuse the one idempotent risk reservation; changed quantity/account or violated risk/configuration requirements must not silently pass.

Both explicit acknowledgement flags, `MMT_NONPRODUCTION=1`, non-root execution, a normal non-hardlinked bounded replay file, configured engine/PAPER state, genuine frozen source identity, exact selected timeframe and validated source receipt are mandatory. No Telegram send, broker endpoint or live provider is called.

## Evidence required for acceptance

- Actual historical V5 worker executes in its verified child interpreter against finalized offline OHLCV data. Regardless of decision, no synthetic positive setup is substituted.\n- A genuine installed clean-wheel, offline/no-network acceptance using 72 *synthetic* finalized 15m bars produced an actual V5 LONG decision and exactly one created PAPER risk reservation, with the second process recognizing the duplicate. This is **not historical price data, trading performance, live order execution or evidence of edge**; see scripts/accept_paper07_installed.py.
- A separately marked **mock worker transport** test exercises the potential positive decision contract; it is **not** evidence that the actual V5 engine produced a profitable signal.
- NO_SIGNAL never reserves risk or writes an order; positive transport contract links once; repeated invocation does not duplicate risk.
- Missing consent/source, wrong timeframe, revoked engine, hardlinked data, privileged caller and excessive risk quantity fail closed.
- Installed clean-wheel CLI has the new opt-in mode, with proof that imports originate from the installed environment.
- Stage10's AST gate continues to prohibit feeds, publisher calls, live orders, fills and automatic portfolio provisioning. The one narrowly allowed `replay_once` call is bound to explicitly acknowledged offline use.

## Unresolved boundaries — do not claim these are closed

The Brooks replay state journal and Stage10 risk ledger are two **pre-existing separate SQLite databases**. There is **no distributed atomic transaction** between writing a scan and reserving modeled PAPER risk. On error/crash after a recorded scan but before a linked order, the operator must inspect both journals and reconcile manually; **never blindly retry or auto-release**.

The installed Stage20 two-binding synthetic `OfflineContractFixture` remains a **different pilot**, and no Brooks-to-Stage20 CoreManifest certification or unified operator authority is implemented here. Full Stage12→Stage20 integration, a single end-user operator path, durable recovery/UNKNOWN handling, real market-data/account eligibility, actual Telegram delivery, plugin isolation and genuine broker reconciliations remain open P0 gates for subsequent work.

**Release verdict:** `PINNED_BROOKS_OFFLINE_PAPER_RISK_PATH_ACCEPTED` only, if all checks pass; `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE` remains unchanged. The public wheel is an offline PREVIEW. No Production migration, live trading, public signals, private NY First-Reversal source, server deployment or profitability claim is authorized.
