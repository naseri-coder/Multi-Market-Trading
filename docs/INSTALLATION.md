# Installation — v0.3.1

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

## 1. Clone and verify

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

`--check` is offline. It validates the curated 348-file source manifest, Python syntax, v0.3.1 package identity, template contract, and required release files. It does not start Docker, contact a database, or run migrations.

## 2. Install on a fresh host

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

The release-candidate workflows use only synthetic credentials and disposable resources. PostgreSQL is not published on a host port. The complete tracked corpus runs separately in `Full Corpus - Disposable PostgreSQL`; the v0.3.1 RC workflow also performs package, Stage3B, Docker, offline-startup, and 0020→0021 migration rehearsals.

## Enabling additional runtime modes

Do not edit a running installation casually. Prepare a separate reviewed configuration, validate it with the corresponding mode, and perform an explicitly authorized rollout. The presence of a setting or runtime path in source is not operational approval.
