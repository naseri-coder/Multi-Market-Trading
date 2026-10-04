# Installation — v0.3.2

This guide describes the supported **fresh isolated host** installation path. It is not an in-place production upgrade procedure and does not authorize live trading.

## Safety boundary

Use a new, separate host. Do not point this installer at an existing production database, an existing `crypto-price-action_postgres_data` volume, or the protected `/opt/crypto-signal-telegram-bot` tree.

The default configuration is fail-closed:

- Telegram runtime: disabled
- Brooks runtime: disabled
- Brooks operations: disabled
- Paper runtime: disabled
- Performance reporting: disabled
- Scale-In execution: disabled

## Prerequisites

- Git
- Docker Engine with a running daemon
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

## 1. Clone and open NASERI CODER Bot Manager

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash naseri.sh
```

Running `bash scripts/install.sh` with no arguments opens the same manager. The manager provides guarded install, update, start/stop/restart, status/logs, configuration validation, diagnostics, backup/restore, system information, maintenance, and uninstall workflows.

To run only the offline release verification:

```bash
bash scripts/install.sh --check
```

`--check` is offline. It validates the curated 348-file source manifest, Python syntax, v0.3.2 package identity, template contract, and required release files. It does not start Docker, contact a database, or run migrations.

## 2. Install on a fresh host

Choose **[1] Install Bot** in the manager, or run the compatibility command directly:

```bash
bash scripts/install.sh --install
```

If `.env` is missing, the installer creates it with mode `600`, requests numeric `ADMIN_IDS`, and generates a new URL-safe PostgreSQL password without printing it.

Before resource creation the installer performs:

1. stdlib fail-closed environment preflight;
2. Docker/Compose availability checks;
3. Compose configuration validation;
4. explicit operator authorization using the exact phrase `INSTALL-NEW-HOST`;
5. image build;
6. full typed Settings validation inside the built image.

Only then does it create the dedicated PostgreSQL volume, upgrade the disposable/new database to Alembic head, run application configuration/database checks, and start the bot with effectful runtime disabled.

## Manager safety model

The manager is intentionally fail-closed:

- update accepts only the official `naseri-coder/crypto-price-action` origin on `main`;
- the worktree must be clean and the remote update must be fast-forward only;
- an installed database is backed up before update;
- source rollback is automatic only before database migration starts;
- after migration begins, failures leave the bot stopped and preserve the backup for explicit recovery;
- database restore creates a new safety backup before changing data;
- full runtime removal requires typed confirmation and does not delete source or backups;
- `.env` contents and generated database passwords are never printed by manager workflows.

Manager-created backups are stored under `.naseri-backups/` with restrictive permissions and are ignored by Git.

## Configuration validation modes

`scripts/validate_release_config.py` validates the complete application Settings contract without displaying secret values.

```bash
PYTHONPATH=production_source python scripts/validate_release_config.py \
  --env-file .env --mode safe-install
```

The validator also understands `paper` and `live` configuration shapes for controlled review. Passing either mode only proves configuration consistency; it does **not** approve operational use or live trading.

Conditional fields such as channel IDs and cutover timestamps are documented in `.env.example` and should remain commented until the related mode is intentionally configured.

## Database configuration

The Compose database variables and application URL must describe the same isolated service:

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `DATABASE_URL=postgresql+asyncpg://...@postgres:5432/...`

The installer rejects inherited shell overrides for these values.

## Validation evidence

The release-candidate workflows use only synthetic credentials and disposable resources. PostgreSQL is not published on a host port. The complete tracked corpus runs separately in `Full Corpus - Disposable PostgreSQL`; the v0.3.2 RC workflow also performs package, Stage3B, Docker, offline-startup, and 0020→0021 migration rehearsals.

## Enabling additional runtime modes

Do not edit a running installation casually. Prepare a separate reviewed configuration, validate it with the corresponding mode, and perform an explicitly authorized rollout. The presence of a setting or runtime path in source is not operational approval.


## Paper cold-start bootstrap

On a fresh database, Historical Probability remains fail-closed until enough compatible
realized-R evidence exists. In v0.3.2, Paper mode may persist only otherwise-qualified
stop-trigger candidates as internal `SHADOW` observations and advance them with the same
causal one-minute lifecycle semantics used by the existing lifecycle engine.

These bootstrap observations are not delivered to public/VIP channels, do not count
toward production performance, and do not require
`BROOKS_OPERATIONS_ENABLED=true`.
