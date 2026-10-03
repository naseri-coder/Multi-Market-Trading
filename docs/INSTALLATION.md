# v0.3.0 Installation

This document describes the supported installation path for the public v0.3.0 source release.

> **Fresh isolated host only.** The installer is not an in-place upgrade mechanism and is not authorized to overwrite an existing deployment or operational database.

## Prerequisites

Install these on the new host before running the installer:

- Git
- Docker Engine with a running daemon
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

The operator account must be able to use Docker.

## 1. Clone the release

After the official tag exists:

```bash
git clone --branch v0.3.0 --depth 1 https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

Before the tag is published, release-candidate validation must use the exact reviewed commit instead of treating a moving branch as a release.

## 2. Run offline verification

```bash
bash scripts/install.sh --check
```

This mode verifies the curated source, Python syntax, package version, release configuration template, required release files, and installer shell syntax. It does not call Docker, run migrations, access a database, or start services.

Do not continue if verification fails.

## 3. Prepare the private environment

The recommended path is to let the installer create a missing `.env` interactively:

```bash
bash scripts/install.sh --install
```

If `.env` does not exist, `scripts/bootstrap_env.py` creates it with private permissions, asks for numeric `ADMIN_IDS`, generates a fresh URL-safe PostgreSQL password, and does not print the password.

For manual preparation:

```bash
cp .env.example .env
chmod 600 .env
```

Replace every placeholder before continuing. The PostgreSQL password in `POSTGRES_PASSWORD` and the password component of `DATABASE_URL` must match.

## 4. Safe-install defaults

The release template intentionally keeps effectful runtime paths disabled:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
BROOKS_SCALE_IN_MODE=disabled
```

The public release includes Binance USD-M Futures support. Presence of runtime code does not authorize paper, Telegram, or live operation.

Validate the template without exposing values:

```bash
python3 scripts/validate_release_config.py --env-file .env.example --mode template
```

A populated safe-install environment is also validated by the installer before any service is created.

## 5. Explicit installation authorization

The installer refuses:

- a host containing the protected original project path;
- non-interactive installation;
- inherited PostgreSQL/Database URL overrides;
- an existing project PostgreSQL volume;
- invalid or unresolved environment configuration.

After preflight, it asks for the exact confirmation:

```text
INSTALL-NEW-HOST
```

Only after that confirmation does it:

1. build the pinned application image;
2. validate the safe-install runtime configuration inside the image;
3. create and start the dedicated PostgreSQL service;
4. apply Alembic migrations through the tracked head;
5. run application configuration and database checks;
6. start the bot container with effectful runtime modes still disabled.

No host PostgreSQL port is published by `compose.yaml`.

## 6. Post-install review

Inspect the service state before enabling anything beyond the safe defaults:

```bash
docker compose -p crypto-price-action -f compose.yaml --env-file .env ps
```

Do not enable Telegram, paper, Brooks runtime/operations, performance reporting, or any live-trading-related mode merely because installation succeeded. Those modes require separate operator review and validation.

## Security boundary

Never commit or upload a populated `.env`, tokens, keys, database dumps, private logs, realized trades, or private market datasets.

v0.3.0 is an official source release. It is not a profitability claim and is not approval for production or live trading.
