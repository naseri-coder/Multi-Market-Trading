# MMT-PAPER-09 — Offline PAPER release rehearsal and rollback acceptance

**Boundary:** non-root, stopped-writer, strictly **nonproduction** rehearsal of the existing Brooks V5 → Stage10 PAPER flow using `multi-market-trading==0.4.0rc1[brooks-offline]`. No real exchange, Telegram, server deployment, private NYFR, public signal, LIVE entitlement, DB migration, strategy profitability claim, broker PnL or Stage20 certification.

## Genuine installed-wheel acceptance

The existing Stage10 CI job now independently installs the **actual** public preview wheel in a clean Python 3.12 virtualenv, imports it from installed site-packages, and runs `scripts/accept_paper09_installed.py` in a new, owner-private, disposable directory. A separate SHA-verified original Brooks source mount is required: the frozen 0.3.2 code is never bundled in the 0.4.0rc1 wheel.

The script executes the real frozen Brooks V5 on 72 **synthetic finalized 15m OHLCV bars**, producing an actual decision (not a mocked V5 output); Stage10 may create only one risk-reserved `CREATED` PAPER order and must deduplicate its replay. It then independently verifies both journals with the Stage08 **read-only** inspector. This is functional software acceptance, **not backtesting, genuine price data, profitability, a fill, or verification of external broker state**.

## Two-existing-ledger backup and isolated restore

The library helper `naseri_markets.paper09_snapshot_v1` provides explicit `snapshot_pair()` and `restore_pair()` operations. It is **not** an automatic backup daemon or background updater. Preconditions:

1. Set `MMT_NONPRODUCTION=1`; never run as root or with `MMT_PRODUCTION=1`.
2. Stop **all** writers and operators for these two SQLite databases. The helper also acquires ordered SQLite `BEGIN IMMEDIATE` write fences across both originals; if a writer holds either lock, the attempt must fail without a retained partial archive.
3. The **existing** state folder and both ledger files must be exclusively owned by the caller, with directory mode `0700`, database files with no group/other permissions and link count 1. An older Stage10 ledger might have inherited a permissive shell umask: in that case the helper **refuses to backup**; the operator must separately review and fix permissions. The acceptance script adjusts permission only on **its own disposable newly created test ledger**.
4. Archive and restore parent folders must already be distinct, empty-capable `0700` private directories, not symlinks. Snapshot creates only a new fixed `p09-backup` bundle; restore creates only a new fixed `p09-restored` folder. Nothing is overwritten.
5. The source and restored state must show `MATCHED_PAPER_ORDER` or `CLEAN_NO_SIGNALS`. Orphaned signals, unknown state, mismatched risk and corrupted data require manual review.

The helper uses the official SQLite Backup API, while both sources are fenced against local SQLite writers. Each **detached backup** is checkpointed and sealed from WAL into a standalone database copy; it deliberately does not checkpoint or change the original writer's journal mode. The bundle contains exactly `custom_paper.db`, `brooks_stage10_paper.sqlite` and `manifest.json`. Every copied DB has SHA256 and bounded byte length recorded; SQLite `integrity_check` plus Stage08 cross-ledger verification run before accepting the archive and again after isolated restoration.

**Critical guarantee limitation:** This protects against normal concurrent **SQLite** writers honoring locks and against common copy interruption. It is *not* a distributed ACID transaction between the two live databases, a protection against malicious same-owner filesystem manipulation, an externally authenticated signature, encrypted backup or production-grade disaster recovery. The manifest hashes provide local corruption detection, **not publisher authentication**. Store sensitive backups under separately controlled access; never upload real account data.

## Rollback and soak rehearsal

The CI rehearsal restores to a **new, disposable candidate** directory. A simulated incompatible upgrade is injected by writing a marker *only* in that candidate. Deleting and re-restoring that temporary candidate verifies rollback without touching the original state or backup. No real application schema migration occurs.

A deliberately corrupted copy of the archive is refused **before any restore folder is created**. Finally, 32 separate, fresh Python processes run Stage08 `--reconcile` against the restored state with no sending or mutating operation. Original and restored database SHA256 remain unchanged; `can_automatically_resume`, `live_orders_authorized` and `telegram_publication_authorized` always remain false.

## Acceptance vs unresolved product gaps

Passing this rehearsal supports **`MMT_PAPER09_CLEAN_WHEEL_OFFLINE_RC_ACCEPTED` only** for the bounded, local, synthetic, frozen-Brooks Stage10 path. It does **not** certify Stage20 CoreManifest integration, a unified operator authority, live market feeds, exchange eligibility, real Telegram delivery, third-party hostile-code isolation, broker fills, genuine cross-database exactly-once execution, autonomous crash repair, actual PnL or a strategy's return.

The release verdict `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE` remains in force. No Production, original historical manifest, private NY First-Reversal source, paid service, real exchange or deployment target is modified.

## Tests required for completion

- Negative tests for permissive original files, non-private state, root/live mode, busy SQLite writer, linked files, tampered/partial/missing archive, invalid manifest, no-overwrite, interrupted restore cleanup and an aborted upgrade candidate.
- Source and restored cross-ledger consistency checks, hashes, SQLite integrity, WAL-free bundle validation and a private restore.
- A genuine independent Python 3.12 clean-wheel run and a bounded 32-process restart soak in the **existing** Stage10 workflow.
- Python full public unit suite, Ruff no-new-debt, frozen 359-file Brooks source checksum/AST verification, independent CodeQL, publication safety and both full PostgreSQL suites in the GitHub PR; conditional Merge only once all are truly green.

This is a release candidate **rehearsal**, not an actual release or backup of any customer/server data.
