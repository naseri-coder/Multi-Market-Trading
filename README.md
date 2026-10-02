<div align="center">

# 📈 Crypto Price Action

### Rule-based crypto signal research with traceable price-action logic

**پژوهش و توسعه سیستم سیگنال‌دهی کریپتو با منطق پرایس‌اکشن قانون‌محور**

[![Publication safety](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml/badge.svg?branch=main)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml)
[![Public tests](https://github.com/naseri-coder/crypto-price-action/actions/workflows/public-test-corpus.yml/badge.svg)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/public-test-corpus.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-async-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Release](https://img.shields.io/badge/release-v0.2.0-7C3AED)](https://github.com/naseri-coder/crypto-price-action)
[![License](https://img.shields.io/badge/license-Apache%202.0-D22128?logo=apache&logoColor=white)](LICENSE)

**Public snapshot · Active development · Validation-first · Live trading disabled**

[Overview](#overview) · [Architecture](#architecture) · [Quick Start](#quick-start) · [Verification](#verification) · [Security](#security)

</div>

> [!IMPORTANT]
> **Development snapshot.** This repository is intended for source review, development, testing, and reproducible installation in an isolated environment. It does **not** claim profitability and is **not approved for production or live trading**.
>
> This is an **independent software project** and is not affiliated with, sponsored by, or endorsed by **Al Brooks** or the publishers of the referenced books.

<a id="overview"></a>
## ✨ Overview

**Crypto Price Action** turns price-action concepts into explicit, testable software rules for market context, signal evaluation, probability, risk, and lifecycle handling.

| | |
| --- | --- |
| 🧠 **Analysis** | Rule-based market structure, context, and pattern logic |
| 📊 **Signal intelligence** | Signal, probability, evidence, and decision infrastructure |
| 🛡️ **Risk & lifecycle** | Risk assessment, signal lifecycle, paper/shadow evaluation paths |
| ⚙️ **Reproducible ops** | PostgreSQL, Docker, Alembic, integrity checks, guarded installation |
| 📡 **Integrations** | Telegram and reporting modules, disabled by default where sensitive |
| 🔐 **Publication safety** | SHA256 allowlist, frozen-source verification, CI safety gates |

<details open>
<summary><strong>🇮🇷 فارسی — پروژه در ۳۰ ثانیه</strong></summary>

<br>

این پروژه یک سیستم متن‌باز برای توسعه و ارزیابی **سیگنال‌های کریپتو بر پایه پرایس‌اکشن قانون‌محور** است. هدف، تبدیل مفاهیم تحلیلی به قواعدی است که بتوان آن‌ها را تست، ردیابی، توضیح و دوباره اعتبارسنجی کرد.

در snapshot عمومی فعلی، زیرساخت تحلیل ساختار و Context بازار، Signal/Probability، Risk، lifecycle، مسیرهای paper/shadow، PostgreSQL، Docker، Telegram integration و کنترل‌های یکپارچگی سورس وجود دارد.

**نکته مهم:** وجود یک قابلیت در سورس به معنی فعال یا تأییدشدن آن برای استفاده عملیاتی نیست. مسیرهای حساس به‌صورت پیش‌فرض غیرفعال نگه داشته می‌شوند.

</details>

<details>
<summary><strong>🇬🇧 English — understand the project in 30 seconds</strong></summary>

<br>

This project is an open-source system for developing and evaluating **rule-based cryptocurrency price-action signals**. The goal is to convert analytical concepts into software rules that can be tested, traced, explained, and revalidated.

The current public snapshot includes market-structure and context analysis, signal/probability infrastructure, risk and lifecycle modules, paper/shadow evaluation paths, PostgreSQL, Docker, Telegram integration, and frozen-source integrity controls.

**Important:** a capability being present in source does not mean it is enabled or approved for operational use. Sensitive runtime paths remain disabled by default.

</details>

<a id="architecture"></a>
## 🧩 Architecture

```text
Market Data
    │
    ▼
Context & Structure
    │
    ▼
Pattern / Signal Evaluation
    │
    ▼
Probability & Evidence
    │
    ▼
Risk & Lifecycle Controls
    │
    ├──► Paper / Shadow evaluation
    ├──► PostgreSQL
    └──► Telegram / Reporting
```

The public source contains market-data adapters, including a Binance USD-M Futures adapter. Runtime selection and operational approval are separate concerns.

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

## 🛣️ Development Focus

Current work is centered on broader rule coverage, stronger context validation, regression testing, explainable outputs, tighter risk/lifecycle controls, and paper/shadow evaluation before operational use is considered.

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
