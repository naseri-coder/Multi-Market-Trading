# Crypto Price Action — frozen-source public snapshot

> PUBLIC SOURCE SNAPSHOT. NOT APPROVED FOR PRODUCTION OR LIVE TRADING.
>
> Independent software project. It is not affiliated with, sponsored by, or endorsed by Al Brooks or the publishers of the referenced books.

## Source selection
Release source: 348 unchanged, hash-verified files from the curated `production_source/SHA256SUMS` allowlist.
Release manifest SHA256: `8bb1e75b35fb333925a4c6ec1595fb9dfc273cc854203e577c4ed19e4bbc21b0`.
The original immutable 361-entry manifest SHA256 is `aacbb49f28d87cce9135b3d43c568d0c11cfb95cd469f627327cd52a4dc202ef`; its unchanged copy remains at `../evidence/FROZEN_SOURCE_SHA256SUMS_361.txt` in the independent staging workspace.
The original manifest contains migration `20260928_0021_ch6_ii_opportunity_identity.py` (SHA256 `7428d542628f32ec1b3df4749a19ec16474f7b24b1b00fc784b600132634bf8f`), following `20260914_0020`. It cannot be identified as solely a September 14 image snapshot.
Publication curation excluded 13 historical entries: one `.bak`, one empty `.tmp`, and 11 archived migration copies. The remaining 348 files match the original manifest individually; the original tree and manifest were not changed.
The original development `app/` tree is excluded. The historical image digest in `production_source/README.md` is a reference, not independently proven provenance for every current file. Development tests are not assumed to match this exact frozen-source subset.

## Contents
`production_source/`: exact hash-verified snapshot; `production_checks/`: frozen HP guard.
`Dockerfile.production`: builds this snapshot and runs the HP guard during build.
`compose.yaml`: distinct project name, PostgreSQL with no host port, runtime flags off by default.
`scripts/verify.sh`: offline hash and AST verification, no Docker daemon use.
`scripts/install.sh`: --check is offline; --install is interactive and fresh-host-only.

## Installation

This repository includes a guarded installer for a **new, separate host only**. It is not an upgrade path for an existing deployment.

### Prerequisites

Install Docker Engine with Compose v2, Git, Bash, Python 3, and `sha256sum`. Then clone this repository and enter its directory:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

### 1. Verify the frozen source

```bash
bash scripts/install.sh --check
```

This check is offline and performs no Docker, network, migration, or service changes.

### 2. Create the environment file

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` locally. Set a private numeric `ADMIN_IDS`, generate a fresh URL-safe password of at least 24 characters, and use the same password in `POSTGRES_PASSWORD` and the matching `DATABASE_URL`. Never commit the populated `.env`.

### 3. Install on a new host

```bash
bash scripts/install.sh --install
```

The installer validates the frozen source and environment, refuses the original project host and an existing install volume, requires interactive confirmation, builds the image, creates a dedicated PostgreSQL volume, applies migrations, and starts the bot with trading and Telegram runtime features disabled.

### Installation safety

Keep Telegram, paper, Brooks runtime, operations, and performance reporting disabled unless they are separately validated and intentionally enabled. Do not use this installer as an upgrade or migration pathway for an existing operational database.

## Open-source publication status
This repository is the public open-source snapshot. The curated source snapshot remains frozen: publication-hardening documentation and CI changes do not alter the 348-file `production_source/SHA256SUMS` identity.

See `docs/OSS_PUBLICATION_REVIEW.md` for the current source-expression and publication review boundary. Security reporting guidance is in `SECURITY.md`; contribution guidance is in `CONTRIBUTING.md`.

The project is licensed under the Apache License 2.0. See `LICENSE`. This license choice does not change the separate source-expression, security, release-integrity, and operational-validation boundaries.

## Operational validation still open
- Original 361-entry source manifest and curated 348-entry release manifest are distinct and documented, including migration 0021; historical image equivalence is not independently established.
- Run Docker build and disposable-db migration/test only on a separately authorized isolated host.
- Reconcile test suite against the selected immutable source; document support and rollback.

Never upload `.env`, backup archives, SQLite data, DB dumps, operational logs, keys,
realized trades or private market datasets. No source, Docker service or database
in the original `/opt/crypto-signal-telegram-bot` tree was modified during staging.
