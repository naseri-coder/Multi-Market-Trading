# MMT-PAPER-08 — conservative two-ledger PAPER recovery gate

**Scope:** local read-only reconciliation of the existing Brooks scan / paper-intent SQLite and the existing Stage10 simulated risk / order SQLite. The inspector `naseri_markets.brooks_stage10_recovery_v1` creates **no database, order, queue, journal or background service**. It does not authenticate with an exchange, send to Telegram, inject a fill, calculate unverified PnL, or control Production.

## Operator workflow

Use an existing, private, nonproduction Stage10 state directory:

```sh
python -m naseri_markets.brooks_stage10_cli \
  --state-dir /private/offline-paper-state --reconcile
```

Optionally filter the result with `--signal-id VERIFIED_BROOKS_SIGNAL_ID`. This command **does not need enabling or trading consent**, because it is read-only and intentionally cannot activate any action. The existing `--status`, `--link` and explicitly acknowledged `--replay-and-link` modes remain available under their original restrictions.

The output is bounded to 200 scanned Brooks events and 200 matching Stage10 links; larger or malformed histories fail closed. The tool checks each historical signal's canonical local digest, linked scan/receipt identity, original order-intent provenance, recorded link request hash, simulated order snapshot/contract and risk reservation. It reconciles whether the order is open with ACTIVE modeled reserve or terminal with RELEASED reserve. Local SHA checks detect inconsistent data but are **not** independent external attestations.

## Expected statuses

| Status | Interpretation | Automatic next step |
|---|---|---|
| `NOT_CONFIGURED` | Neither source nor risk store is present | None |
| `CLEAN_NO_SIGNALS` | No pending Brooks positive intent; no mismatched link | None |
| `MATCHED_PAPER_ORDER` | Existing verified evidence, Stage10 order and reservation match in the two read snapshots | Read only; no automatic trading/replay |
| `MANUAL_RECONCILIATION_REQUIRED` | Recorded positive signal without link; missing/corrupt store, wrong digest, missing order, risk mismatch, duplicate/multiple link, excess rows or unknown state | Stop all writers, independently inspect and reconcile |

Every status explicitly returns `can_automatically_resume=false`, `live_orders_authorized=false` and `telegram_publication_authorized=false`.

## The critical crash boundary

In Stage07, genuine Brooks replay commits a verified scan, then a separate transaction may reserve the existing PAPER risk and record its linked order. A crash, power failure or rejected risk between these commits can leave a **recorded signal with no order**. The Stage08 change gates `--replay-and-link`: a subsequent `DUPLICATE_SCAN` is *not permitted* to create a new order unless the read-only reconciliation sees **one matched original order for the exact signal and account**. The Stage10 bridge then independently rechecks source permissions, provenance and idempotency under its own existing writer transactions.

An orphan positive scan therefore stays blocked pending explicit owner review. It must **not** be silently retried, backfilled, force-closed or marked filled. The original explicit `--link` command remains a separately consented manual action, and still enforces all pre-existing risk and source rules. The inspector never performs that action for the operator.

## Accepted nonproduction tests

- New empty state inspection leaves the filesystem empty.
- Forced interruption *after the Brooks scan is persisted but before Stage10 link* yields `MANUAL_RECONCILIATION_REQUIRED`. Automatic duplicate replay refuses without creating orders.
- Two clean sequential invocations, including a separate interpreter restart, preserve exactly one created PAPER order, original link, single risk reservation and unchanged simulated fill state.
- Missing paper database, missing order snapshot, missing risk reservation or link hash drift are quarantined with no repair, unlock or send.
- Engine revocation preserves historical, read-only reporting while preventing further replay.
- The existing Stage10 GitHub gate executes the installed preview wheel's genuine pinned Brooks V5 worker on explicitly *synthetic* closed bars, then reopens and reconciles in a third separate process.

## Deliberate remaining limits

This is **not** an ACID transaction across databases or a signed custody ledger. Snapshot inspection during concurrent writes is observational and must not be treated as authority to resume; a clean result is evidence of a local state at inspection time, **not** permission to do anything later. Operator-driven reconciliation has no automated repair command. The expected owner workflow for an unknown state is stop → owner-private backup of BOTH stores (including WAL if present) → evaluate source receipt, risk order and risk reservation independently → resolve through a separately reviewed and permitted procedure. This stage does not define or execute such a repair.

Stage10's risk/order ledger does not establish actual broker PnL. No modeled `net_pnl` or unrealized profit is claimed by the Stage08 report: PnL will require an independently accepted Stage20/positions/economics mapping in a later scoped stage. Stage20 still uses the synthetic contract fixture and is **not** a certified Brooks CoreManifest. Authentic market-data, Telegram delivery, single operator authority, plugin isolation, long-lived failover, real-account reconciliation and LIVE trading remain blocked.

**Release decision:** `MMT_PAPER08_READONLY_RECONCILIATION_ACCEPTED` only if genuine unit tests, separate clean-wheel acceptance and protected GitHub CI pass. Existing `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE` remains unchanged. No frozen Brooks source, owner-private NYFR, production database or live server changes.
