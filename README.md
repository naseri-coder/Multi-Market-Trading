<div align="center">

# 📈 Crypto Price Action

### Turning price-action concepts into explicit, testable crypto signal rules

**تبدیل مفاهیم پرایس‌اکشن البروکس به قواعد صریح، قابل‌آزمایش و قابل‌ردیابی برای سیگنال‌های کریپتو**

[![Publication safety](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml/badge.svg?branch=main)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml)
[![Public tests](https://github.com/naseri-coder/crypto-price-action/actions/workflows/public-test-corpus.yml/badge.svg)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/public-test-corpus.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-async-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Version](https://img.shields.io/badge/version-v0.3.2-7C3AED)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache%202.0-D22128?logo=apache&logoColor=white)](LICENSE)

### 📣 Telegram

[![Telegram Channel](https://img.shields.io/badge/Channel-%40naseri__coder-26A5E4?logo=telegram&logoColor=white)](https://t.me/naseri_coder)
[![Developer](https://img.shields.io/badge/Developer-%40nasericoder-26A5E4?logo=telegram&logoColor=white)](https://t.me/nasericoder)

**v0.3.2 · Validation-first · Live Brooks execution disabled**

[Overview](#overview) · [How it works](#how-it-works) · [Current status](#current-status) · [Install & Manager](#install-manager) · [Operations](#operations) · [Verification](#verification) · [Security](#security)

</div>

> [!IMPORTANT]
> **Current main includes the NASERI CODER Bot Manager while the package version remains v0.3.2.** The project does **not** claim profitability and is **not approved for live trading**.
>
> This is an **independent software project** and is not affiliated with, sponsored by, or endorsed by **Al Brooks** or the publishers of the referenced books.

<a id="overview"></a>
## ✨ Overview

**Crypto Price Action** is a rule-based cryptocurrency signal-system project focused on converting documented price-action concepts into inspectable software logic.

Instead of treating a setup as a single pattern match, the project evaluates the setup together with its surrounding **market context, structural evidence, probability assessment, and risk/lifecycle constraints**.

### What the engine evaluates

`Trend direction & relative strength` · `Follow-through` · `Bar overlap` · `Pullbacks & second entries` · `Breakouts & failed breakouts` · `Trading ranges & tight ranges` · `Setup location vs. market context`

<details open>
<summary><strong>🇮🇷 فارسی — پروژه در ۳۰ ثانیه</strong></summary>

<br>

**Crypto Price Action** یک پروژه متن‌باز برای توسعه سیستم سیگنال‌دهی کریپتو با هسته پرایس‌اکشن قانون‌محور است. تمرکز پروژه بر این است که مفاهیم پرایس‌اکشن البروکس به قواعدی تبدیل شوند که بتوان آن‌ها را **تست، ردیابی، توضیح و دوباره اعتبارسنجی** کرد.

سیستم فقط به پیدا کردن یک Pattern اکتفا نمی‌کند؛ بلکه **Context بازار، ساختار، Follow-through، Overlap، Pullback، Breakout / Failed Breakout، Trading Range، Probability و Risk** را در کنار یکدیگر بررسی می‌کند.

در snapshot عمومی فعلی، زیرساخت تحلیل، Signal/Probability، Risk و lifecycle، مسیرهای paper/shadow، PostgreSQL، Docker، Telegram integration، کنترل‌های یکپارچگی سورس و **NASERI CODER Bot Manager** وجود دارد.

**وجود یک قابلیت در سورس به معنی فعال یا تأییدشدن آن برای استفاده عملیاتی نیست.**

</details>

<details>
<summary><strong>🇬🇧 English — understand the project in 30 seconds</strong></summary>

<br>

The project develops a **rule-based crypto signal engine** around explicit, testable interpretations of price-action concepts documented in Al Brooks' published work.

A candidate setup is evaluated in context rather than as an isolated pattern: market structure, follow-through, overlap, pullbacks, breakout behavior, probability evidence, and risk/lifecycle controls all contribute to the decision pipeline.

The public snapshot contains analysis, signal/probability, risk/lifecycle, paper/shadow, PostgreSQL, Docker, Telegram integration, source-integrity infrastructure, and the **NASERI CODER Bot Manager**.

**A capability being present in source does not mean it is enabled or approved for operational use.**

</details>

<a id="how-it-works"></a>
## 🧠 How It Works

```text
Market Data
   ↓
Context & Structure
   ↓
Pattern / Setup Evidence
   ↓
Probability & Decision Evidence
   ↓
Risk & Lifecycle Gates
   ↓
Paper / Shadow / Reporting paths
```

**1. Context first** — identify market regime, direction, structure, range/trend behavior, overlap, and related context.

**2. Setup evidence** — evaluate candidate patterns such as pullbacks, breakouts, failed breakouts, second entries, ranges, and other supported structures.

**3. Probability & evidence** — carry explicit rule evidence and probability-related state instead of reducing the decision to a single opaque score.

**4. Risk & lifecycle** — apply risk checks and lifecycle controls before downstream handling.

**5. Controlled outputs** — paper/shadow, persistence, Telegram, and reporting paths remain subject to configuration and validation gates.

The public source currently uses **Binance USD-M Futures** as the supported market-data path described by this project. Runtime selection and operational approval are separate concerns.

<a id="current-status"></a>
## 🚦 Current Status

| Area | Status |
| --- | --- |
| Brooks rule-based analysis core | 🟡 Active development & validation |
| MARC MA 7/25/99 core | 🟡 Frozen v0.1 baseline; backtest pending |
| Context / pattern coverage | 🟡 Expanding and regression-tested |
| Public source integrity | 🟢 SHA256-verified snapshot |
| Public test corpus | 🟢 GitHub Actions |
| Paper / shadow paths | 🟡 Present; controlled by runtime flags |
| Live Brooks execution | 🔴 Disabled / not production-approved |
| PostgreSQL / Docker installation | 🟢 Reproducible isolated-host path |
| NASERI CODER Bot Manager | 🟢 Install/update/lifecycle/backup tooling present |

> [!NOTE]
> This table describes the public repository state, not trading performance or profitability.

<a id="install-manager"></a>
## 🚀 Installation & NASERI CODER Bot Manager

### Prerequisites

- Git
- Docker Engine with a running daemon
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

### Install

Use this single installation entry point:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash naseri.sh
```

The final command opens the **NASERI CODER Bot Manager**. From there, choose **[1] Install Bot** for a fresh installation.

The Manager uses a color-aware Terminal UI: healthy states are green, warnings/stopped states are yellow, errors and destructive actions are red, and informational sections are cyan. ANSI colors are disabled automatically for non-interactive output and can also be disabled explicitly with `NO_COLOR=1`.

The main menu is:

```text
INSTALLATION
  [1]  Install Bot
  [2]  Update Bot

RUNTIME
  [3]  Start Bot
  [4]  Stop Bot
  [5]  Restart Bot
  [6]  Bot Status
  [7]  View Logs

SYSTEM
  [8]  Configuration
  [9]  Environment Check
  [10] Database Management

DATA
  [11] Backup
  [12] Restore

MAINTENANCE
  [13] Repair / Diagnose
  [14] Verify Installation
  [15] System Information

DANGER ZONE
  [16] Uninstall / Remove Runtime

  [0]  Exit
```

### Fresh installation

For a new isolated host, choose **[1] Install Bot** from the Manager.

The installer will:

1. verify the repository/release tooling;
2. refuse unsafe inherited database overrides;
3. create a private `.env` if one does not exist;
4. validate the fail-closed environment;
5. verify Docker Engine and Docker Compose v2;
6. refuse to overwrite an existing `crypto-price-action_postgres_data` volume;
7. require explicit confirmation;
8. build the bot image;
9. validate application configuration inside the built image;
10. start PostgreSQL;
11. run Alembic migrations to the current repository head;
12. run application configuration/database checks;
13. start the bot container.

Before creating runtime resources, the installer requires the exact confirmation:

```text
INSTALL-NEW-HOST
```

> [!WARNING]
> The fresh-host installer intentionally refuses installation when the protected legacy tree `/opt/crypto-signal-telegram-bot` exists or when the project database volume already exists. It is **not** an overwrite mechanism.

### Safe defaults after installation

A successful install may report:

```text
Bot..................... RUNNING
PostgreSQL.............. RUNNING
Installation state...... RUNNING
```

This means the containers are healthy. It does **not** mean signal delivery or trading-related runtime is enabled.

The default fail-closed configuration keeps effectful runtime disabled:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

So a normal fresh installation can correctly show **Bot = RUNNING** while Telegram, Brooks runtime, Paper runtime, and Brooks operations remain disabled.

### Check installation status

Interactive:

```text
[6] Bot Status
```

Direct command:

```bash
bash naseri.sh status
```

The status screen reports the project version, Git branch/commit, bot and PostgreSQL state, database-volume presence, **database authentication state**, installation state, and a **secret-safe configuration summary**.

Secret values such as database passwords and Telegram tokens are not displayed.

### View logs

Interactive:

```text
[7] View Logs
```

Direct command:

```bash
bash naseri.sh logs
```

Use `Ctrl+C` to stop following logs.

---

<a id="operations"></a>
## 🛠️ Manager Operations

### Command-line shortcuts

The interactive menu is recommended for normal administration, but the same manager can be called directly:

| Operation | Command |
| --- | --- |
| Open menu | `bash naseri.sh` |
| Update | `bash naseri.sh update` |
| Start | `bash naseri.sh start` |
| Stop bot | `bash naseri.sh stop` |
| Restart | `bash naseri.sh restart` |
| Status | `bash naseri.sh status` |
| Logs | `bash naseri.sh logs` |
| Configuration menu | `bash naseri.sh config` |
| Environment check | `bash naseri.sh env-check` |
| Database menu | `bash naseri.sh database` |
| Create full backup | `bash naseri.sh backup` |
| Backup menu | `bash naseri.sh backups` |
| Restore menu | `bash naseri.sh restore` |
| Doctor | `bash naseri.sh doctor` |
| Repair / diagnose menu | `bash naseri.sh repair` |
| Verify installation | `bash naseri.sh verify` |
| System information | `bash naseri.sh system` |
| Guarded uninstall menu | `bash naseri.sh uninstall` |
| Manager help | `bash naseri.sh --help` |

### Update Bot

Choose **[2] Update Bot** or run:

```bash
bash naseri.sh update
```

The updater is intentionally strict. It requires:

- an official Git checkout;
- `origin` to be exactly the official HTTPS or SSH repository;
- branch `main`;
- a completely clean worktree, including untracked files;
- a fast-forward-only update from official `origin/main`;
- explicit typed authorization.

The update confirmation is:

```text
UPDATE
```

When an installed database exists, the manager creates a mandatory backup before updating.

The update workflow then verifies source integrity, builds the current image, validates configuration, starts PostgreSQL, applies Alembic migrations, performs application checks, and restores the previous bot-running state.

> [!IMPORTANT]
> Automatic source rollback is allowed only before database migration begins. Once a migration starts, the manager does not perform an unsafe source-only rollback. A failure leaves the bot stopped and preserves the pre-update backup for explicit recovery.

### Start / Stop / Restart

```bash
bash naseri.sh start
bash naseri.sh stop
bash naseri.sh restart
```

**Start** validates configuration, starts PostgreSQL when required, checks application configuration/database connectivity, and then starts the bot.

**Stop** stops the bot service while retaining PostgreSQL and persistent data.

**Restart** revalidates the installation before restarting the bot.

### Configuration

Choose **[8] Configuration** or run:

```bash
bash naseri.sh config
```

The manager can show a secret-safe summary, validate the current configuration, bootstrap a missing environment file, and open the local `.env` editor through a guarded workflow.

Supported validation shapes are:

- `safe-install`
- `paper`
- `live`

Passing configuration validation proves only that the configuration is internally consistent. It does **not** approve live trading or operational use.

The manager restores `.env` permissions to mode `600` after supported edit/restore workflows.

### Environment Check

Choose **[9] Environment Check** or run:

```bash
bash naseri.sh env-check
```

This checks required commands, Docker/Compose availability, `.env` presence and permissions, and the supported configuration contract.

### Database Management

Choose **[10] Database Management** or run:

```bash
bash naseri.sh database
```

Database Management provides:

- database status;
- current migration / Alembic head inspection;
- guarded upgrade to current Alembic head;
- database backup;
- database restore.

Database upgrades and restores are guarded operations. The manager creates safety backups where required and keeps PostgreSQL isolated behind the Compose network rather than publishing its port to the host.

### Backup

Choose **[11] Backup** or run:

```bash
bash naseri.sh backup
```

Available backup types include:

- full backup;
- PostgreSQL database backup;
- configuration backup;
- backup listing.

Manager backups are stored under:

```text
.naseri-backups/
```

Backup directories/files use restrictive permissions and the directory is ignored by Git.

Database backups use PostgreSQL `pg_dump` in custom format.

### Restore

Choose **[12] Restore** or run:

```bash
bash naseri.sh restore
```

The restore menu supports database and configuration recovery.

Before a database restore, the manager creates a mandatory **pre-restore full backup**. Database restore uses `pg_restore`, then upgrades to the repository Alembic head and runs a database check.

Configuration restore validates the restored `.env`. If the new configuration fails validation, the previous configuration is automatically reinstated.

### Repair / Diagnose

Choose **[13] Repair / Diagnose** or run:

```bash
bash naseri.sh repair
```

Repair tools include:

- Doctor diagnostics;
- repair `.env` permissions;
- rebuild and verify the bot image;
- safe restart;
- guarded PostgreSQL credential recovery when the existing database volume password does not match the private `.env`.

You can run Doctor directly:

```bash
bash naseri.sh doctor
```

### Verify Installation

Choose **[14] Verify Installation** or run:

```bash
bash naseri.sh verify
```

For an offline source/release check without Docker changes:

```bash
bash scripts/install.sh --check
```

`--check` does not start Docker services, run database migrations, or modify a database.

### System Information

Choose **[15] System Information** or run:

```bash
bash naseri.sh system
```

This provides the manager's system/runtime summary for troubleshooting.

### Uninstall / Remove Runtime

Choose **[16] Uninstall / Remove Runtime** or run:

```bash
bash naseri.sh uninstall
```

The uninstall workflow provides separate guarded levels:

1. remove only the bot container while keeping database/config/backups/source;
2. remove project containers/network while retaining database/config/backups/source;
3. full runtime-data removal, including the project database volume.

Full runtime removal requires explicit typed confirmation. Source files and manager-created backups are retained. Removing `.env` requires an additional explicit confirmation.

> [!CAUTION]
> Do not use destructive uninstall or restore options unless you understand exactly which persistent state will be changed. Create and verify a backup first.

## 🔁 Recommended Operator Workflow

For a normal installed instance:

```bash
cd crypto-price-action
bash naseri.sh status
bash naseri.sh
```

Then use the manager rather than manually composing Docker commands.

Before a significant update or configuration/database change:

```bash
bash naseri.sh backup
```

For an official source update:

```bash
bash naseri.sh update
```

After a configuration change:

```bash
bash naseri.sh restart
bash naseri.sh status
```

For troubleshooting:

```bash
bash naseri.sh doctor
bash naseri.sh verify
bash naseri.sh logs
```

## 🗂️ Repository Map

| Path | Purpose |
| --- | --- |
| `production_source/` | Curated, hash-verified public source snapshot |
| `production_checks/` | Frozen-source and regression guards |
| `tests/` | Reviewed public test corpus |
| `naseri.sh` / `scripts/manager.sh` | Interactive NASERI CODER lifecycle manager |
| `scripts/lib/manager_common.sh` | Shared safety, status, config and Compose helpers |
| `scripts/lib/manager_runtime.sh` | Install/update/runtime/database/repair/uninstall workflows |
| `scripts/lib/manager_backup.sh` | Backup and restore implementation |
| `scripts/` | Verification, safety, environment and installer tooling |
| `.github/workflows/` | CI, release baseline, and publication-safety workflows |
| `Dockerfile.production` / `compose.yaml` | Isolated containerized deployment |

<a id="verification"></a>
## 🧪 Verification & Provenance

The current `main` branch source manifest contains **369 tracked entries** in `production_source/SHA256SUMS`.

The historical v0.3.2 release baseline and later validated `main` changes are protected by repository verification and GitHub Actions. Use the repository's release tags when an immutable release identity is required; use `main` when following the current Manager and ongoing development state.

Local verification:

```bash
bash scripts/verify.sh
```

Manager static self-test:

```bash
bash scripts/manager.sh --self-test
```

The verification tooling checks the curated source identity, required release/manager files, shell syntax, package/configuration contracts, and Manager safety invariants.

## 🛣️ Development Direction

**Broader rule coverage → stronger context validation → regression & explainability → paper/shadow evaluation → operational review**

This sequence is a development direction, not a promise of production or live-trading readiness.

<a id="security"></a>
## 🤝 Contributing, Security & License

[Installation](docs/INSTALLATION.md) · [Rebuild/restore](docs/REBUILD_RESTORE.md) · [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Contributing guide](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [Open-source publication boundary](docs/OSS_PUBLICATION_REVIEW.md) · [Apache License 2.0](LICENSE)

> [!CAUTION]
> Never commit or upload populated `.env` files, credentials, tokens, keys, database dumps, private operational logs, realized trades, or private market datasets.

---

<div align="center">

### Built for reproducible research, review, testing, and disciplined validation.

[Repository](https://github.com/naseri-coder/crypto-price-action) · [Issues](https://github.com/naseri-coder/crypto-price-action/issues) · [Actions](https://github.com/naseri-coder/crypto-price-action/actions) · [Security](SECURITY.md)

</div>
