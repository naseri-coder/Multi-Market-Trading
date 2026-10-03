# v0.3.0 Rebuild and Restore Boundary

This document separates a **clean rebuild from public source** from restoration of authorized persistent state.

## Clean rebuild

A clean rebuild starts from the exact official `v0.3.0` tag on a new isolated host.

1. Verify the tag and checkout identity.
2. Run `bash scripts/install.sh --check`.
3. Prepare a new private `.env` from the release template.
4. Use the guarded fresh-host installation flow in `docs/INSTALLATION.md`.
5. Keep all effectful runtime modes disabled until separately reviewed.

The public installer deliberately refuses to overwrite an existing project volume. It is not an upgrade or recovery tool for an operational host.

## Persistent state is separate

Source code and persistent state have different trust boundaries.

The release repository does not contain and must not contain:

- populated `.env` files;
- production PostgreSQL data;
- database dumps;
- Telegram tokens or private channel identifiers;
- private operational logs;
- realized private trades;
- private market datasets.

Restoring any persistent state therefore requires a separately authorized operator procedure.

## Database restoration policy

Do not point an unvalidated release candidate at an existing production database.

Before restoring authorized data:

1. keep the original database unchanged;
2. create a disposable or isolated restoration target;
3. verify the backup independently;
4. restore into that isolated target;
5. confirm the Alembic revision and schema compatibility;
6. run migration and application checks against the isolated copy;
7. review data-specific invariants and access controls;
8. only then decide whether a production migration is separately authorized.

The public release validation uses disposable PostgreSQL resources only and publishes no database host port.

## Configuration restoration policy

Do not copy an old `.env` blindly into v0.3.0.

Start from the v0.3.0 `.env.example`, then transfer only settings that are intentionally authorized and still supported. Validate the resulting file before use:

```bash
python3 scripts/check_env.py .env
```

For the initial safe installation, Telegram and all effectful Brooks/paper/reporting modes remain disabled.

## Reproducibility records

For an auditable rebuild, record at minimum:

- release tag;
- exact commit SHA;
- `production_source/SHA256SUMS` digest;
- migration head;
- dependency-lock verification result;
- container image identity produced from the release source;
- date and operator-approved state restoration inputs.

## Non-goals

This document does not authorize:

- modifying the current production server;
- running migrations against an existing production database;
- restarting or redeploying an existing production service;
- enabling live Brooks execution;
- enabling trading or Telegram publication.

Those operations require separate explicit authorization and validation.
