# Rebuild and Restore Runbook

This document defines the v0.3.0 rebuild/restore procedure. It is a **runbook**, not authorization to operate on the current production server.

## Source / secret / persistent-state boundary

- **SOURCE** belongs in GitHub and must come from an immutable reviewed release commit/tag.
- **SECRETS** stay outside GitHub in an access-controlled secret/configuration store.
- **PERSISTENT DATA** includes PostgreSQL application state and any explicitly inventoried non-regenerable assets.
- **REGENERABLE STATE** such as caches, logs, pycache, temporary build output and containers is not a backup target.

## Before any destructive action

1. Establish an authorized maintenance/consistency window.
2. Record the exact currently deployed artifact/image identity.
3. Record PostgreSQL server/version, database names, schemas/extensions, roles required for restore, and actual Alembic revision.
4. Record row counts for critical application tables.
5. Inventory Docker volumes and non-regenerable filesystem assets. Do not assume one named Compose volume is the complete persistent-state inventory.
6. Create a PostgreSQL custom-format logical dump plus required role/extension metadata.
7. Encrypt and store backups off-host; record checksums without publishing credentials or private data.
8. Preserve the prior application artifact and matching state snapshot for rollback.

## Isolated restore rehearsal

Restore only into isolated infrastructure first.

1. Provision a compatible PostgreSQL instance with no connection to the production database.
2. Restore the authorized dump and required roles/extensions.
3. Verify restore exit status, checksums/inventory, row counts and constraints.
4. Determine the restored database's actual Alembic revision; do not guess it from source files.
5. Upgrade the restored copy to the v0.3.0 migration head using the exact release artifact.
6. Run disposable integration/configuration checks and verify critical records remain present.
7. Keep Telegram, Brooks runtime, operations, paper runtime and reporting disabled throughout the rehearsal.

The RC workflow separately proves a synthetic 0020→0021 data-preservation migration against the table directly changed by revision 0021.

## Rebuild

Only after the official v0.3.0 release and a successful restore rehearsal:

1. provision a fresh host;
2. verify the immutable v0.3.0 tag/commit and release artifacts;
3. install using the supported fresh-host path;
4. restore only the authorized persistent state;
5. supply secrets externally;
6. validate configuration and database health;
7. run staged health checks with effectful runtime disabled;
8. enable external effects only in a separately authorized cutover.

## Rollback

Rollback means restoring a **compatible prior application artifact together with its matching database/state snapshot**. Do not assume a destructive Alembic downgrade is safe. In particular, migrations can deliberately refuse downgrade when doing so would discard execution/accounting evidence.

## Explicit prohibitions

- No production database is used by CI.
- No populated `.env`, database dump, private key, Telegram token or operational dataset belongs in GitHub.
- Do not rebuild the current production server from an untagged development branch.
- Do not enable live/effectful modes merely because configuration validation passes.
