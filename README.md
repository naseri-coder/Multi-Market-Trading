<div align="center">

# 📈 Crypto Price Action

### Turning price-action concepts into explicit, testable crypto signal rules

**تبدیل مفاهیم پرایس‌اکشن البروکس به قواعد صریح، قابل‌آزمایش و قابل‌ردیابی برای سیگنال‌های کریپتو**

[![Publication safety](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml/badge.svg?branch=main)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml)
[![Public tests](https://github.com/naseri-coder/crypto-price-action/actions/workflows/public-test-corpus.yml/badge.svg)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/public-test-corpus.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-async-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Version](https://img.shields.io/badge/version-v0.2.0-7C3AED)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache%202.0-D22128?logo=apache&logoColor=white)](LICENSE)

**Public source snapshot · Active development · Validation-first · Live Brooks execution disabled**

[Overview](#overview) · [How it works](#how-it-works) · [Current status](#current-status) · [Quick start](#quick-start) · [Verification](#verification) · [Security](#security)

</div>

> [!IMPORTANT]
> **Development snapshot.** This repository is intended for source review, development, testing, and reproducible installation in an isolated environment. It does **not** claim profitability and is **not approved for production or live trading**.
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

در snapshot عمومی فعلی، زیرساخت تحلیل، Signal/Probability، Risk و lifecycle، مسیرهای paper/shadow، PostgreSQL، Docker، Telegram integration و کنترل‌های یکپارچگی سورس وجود دارد.

**وجود یک قابلیت در سورس به معنی فعال یا تأییدشدن آن برای استفاده عملیاتی نیست.**

</details>

<details>
<summary><strong>🇬🇧 English — understand the project in 30 seconds</strong></summary>

<br>

The project develops a **rule-based crypto signal engine** around explicit, testable interpretations of price-action concepts documented in Al Brooks' published work.

A candidate setup is evaluated in context rather than as an isolated pattern: market structure, follow-through, overlap, pullbacks, breakout behavior, probability evidence, and risk/lifecycle controls all contribute to the decision pipeline.

The public snapshot contains analysis, signal/probability, risk/lifecycle, paper/shadow, PostgreSQL, Docker, Telegram integration, and source-integrity infrastructure.

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

The public source includes market-data adapters, including **Binance USD-M Futures**. Runtime selection and operational approval are separate concerns.

<a id="current-status"></a>
## 🚦 Current Status

| Area | Status |
| --- | --- |
| Rule-based analysis core | 🟡 Active development & validation |
| Context / pattern coverage | 🟡 Expanding and regression-tested |
| Public source integrity | 🟢 SHA256-verified snapshot |
| Public test corpus | 🟢 GitHub Actions |
| Paper / shadow paths | 🟡 Present; controlled by runtime flags |
| Live Brooks execution | 🔴 Disabled / not production-approved |
| PostgreSQL / Docker installation | 🟢 Reproducible isolated-host path |

> [!NOTE]
> This table describes the public repository state, not trading performance or profitability.
<a id="quick-start"></a>
## 🚀 Quick Start

### 1) Verify the snapshot — no installation

Recommended first step:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

`--check` runs offline verification of the frozen source and publication files. It does not start Docker services, run migrations, or modify a database.

### 2) Install on a fresh isolated host

Required beforehand: **Git · Docker Engine · Docker Compose v2 · Bash · Python 3 · sha256sum**

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

The installer validates the environment, creates a private `.env` when needed, generates a PostgreSQL password, and waits for explicit final authorization:

```text
INSTALL-NEW-HOST
```

Only after that confirmation does it build the image, create the dedicated PostgreSQL volume, apply Alembic migrations, and start the services.

> [!WARNING]
> Use the installer only on a **new, separate, isolated host**. It is not an in-place production upgrade mechanism.

## 🗂️ Repository Map

| Path | Purpose |
| --- | --- |
| `production_source/` | Curated, hash-verified public source snapshot |
| `production_checks/` | Frozen-source and regression guards |
| `tests/` | Reviewed public test corpus |
| `scripts/` | Verification, safety, environment, and installer tooling |
| `.github/workflows/` | CI, release baseline, and publication-safety workflows |
| `Dockerfile.production` / `compose.yaml` | Isolated containerized deployment |

<details>
<summary><strong>🔒 Safe defaults</strong></summary>

<br>

The following runtime capabilities remain disabled until separately validated and intentionally enabled:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

The installer does not silently install operating-system packages, modify the host package manager, or overwrite an existing deployment.

</details>

<a id="verification"></a>
## 🧪 Verification & Provenance

The current public release source consists of **348 unchanged, hash-verified files** selected by `production_source/SHA256SUMS`.

<details>
<summary><strong>View source identity</strong></summary>

<br>

**Release manifest SHA256**

```text
769aa1757120c71ddf17579f18f1b63cd5ef3685a25287bd68d7c9bc7c341b49
```

**Original immutable 361-entry development manifest SHA256**

```text
aacbb49f28d87cce9135b3d43c568d0c11cfb95cd469f627327cd52a4dc202ef
```

Publication curation excluded 13 historical entries: one `.bak`, one empty `.tmp`, and 11 archived migration copies. The remaining 348 files match the original manifest individually.

</details>

## 🛣️ Development Direction

**Broader rule coverage → stronger context validation → regression & explainability → paper/shadow evaluation → operational review**

This sequence is a development direction, not a promise of production or live-trading readiness.

<a id="security"></a>
## 🤝 Contributing, Security & License

[Contributing guide](CONTRIBUTING.md) · [Security policy](SECURITY.md) · [Open-source publication boundary](docs/OSS_PUBLICATION_REVIEW.md) · [Apache License 2.0](LICENSE)

> [!CAUTION]
> Never commit or upload populated `.env` files, credentials, tokens, keys, database dumps, private operational logs, realized trades, or private market datasets.

---

<div align="center">

### Built for reproducible research, review, testing, and disciplined validation.

[Repository](https://github.com/naseri-coder/crypto-price-action) · [Issues](https://github.com/naseri-coder/crypto-price-action/issues) · [Actions](https://github.com/naseri-coder/crypto-price-action/actions) · [Security](SECURITY.md)

</div>
