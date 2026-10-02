<div align="center">

# 📈 Crypto Price Action

**Rule-based cryptocurrency signal-system research and development**

[![Publication safety](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml/badge.svg?branch=main)](https://github.com/naseri-coder/crypto-price-action/actions/workflows/publication-safety.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-async-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Release](https://img.shields.io/badge/release-v0.2.0-8A2BE2)](https://github.com/naseri-coder/crypto-price-action)
[![License](https://img.shields.io/badge/license-Apache%202.0-D22128?logo=apache&logoColor=white)](LICENSE)
[![Stars](https://img.shields.io/github/stars/naseri-coder/crypto-price-action?style=flat&logo=github)](https://github.com/naseri-coder/crypto-price-action/stargazers)

**Public source snapshot · Active development · Validation-first · Not approved for live trading**

</div>

> [!IMPORTANT]
> This is an **independent software project**. It is not affiliated with, sponsored by, or endorsed by **Al Brooks** or the publishers of the referenced books. The repository is published for source review, development, testing, and reproducible installation. It does **not** claim profitability and is **not approved for production or live trading**.

---

<details>
<summary>🇮🇷 <strong>فارسی</strong> — معرفی، قابلیت‌ها و نصب</summary>

<br>

## معرفی پروژه

**Crypto Price Action** یک پروژه متن‌باز برای توسعه یک سیستم سیگنال‌دهی ارزهای دیجیتال بر پایه تحلیل قانون‌محور Price Action است. هسته پروژه با تمرکز بر تبدیل مفاهیم ساختاری و زمینه‌ای پرایس‌اکشن به قواعد قابل‌آزمایش، قابل‌ردیابی و قابل‌اعتبارسنجی توسعه داده می‌شود.

این مخزن عمومی شامل یک snapshot انتخاب‌شده و hash-verified از سورس، فایل‌های Docker، تنظیمات PostgreSQL، تست‌های عمومی، کنترل‌های ایمنی انتشار، ابزارهای بررسی یکپارچگی و installer محافظت‌شده برای یک محیط جدید و ایزوله است.

### ✨ نمای سریع

| بخش | وضعیت / توضیح |
| --- | --- |
| 🧠 هسته تحلیل | تحلیل قانون‌محور ساختار، Context و الگوهای Price Action |
| 📊 داده بازار | آداپترهای داده بازار؛ مسیر Binance USD-M Futures در سورس موجود است |
| 🛡️ ریسک | ماژول‌های ارزیابی ریسک و lifecycle سیگنال |
| 🧪 اعتبارسنجی | تست‌های عمومی، بررسی frozen source و کنترل‌های regression |
| 🐘 پایگاه داده | PostgreSQL با SQLAlchemy async |
| 🐳 اجرا | Docker / Docker Compose |
| 📡 یکپارچه‌سازی | Telegram و گزارش‌دهی، با قابلیت‌های حساس خاموش به‌صورت پیش‌فرض |
| 🔐 انتشار | SHA256 allowlist و publication-safety checks |
| 📜 مجوز | Apache License 2.0 |

## 🧩 ساختار کلی

```text
Market Data
    │
    ▼
Price-Action Context & Pattern Analysis
    │
    ▼
Signal / Probability Evaluation
    │
    ▼
Risk & Lifecycle Controls
    │
    ├──► Paper / Shadow paths
    ├──► PostgreSQL
    └──► Telegram / Reporting
```

این نمودار یک نمای سطح‌بالا از معماری است؛ فعال‌بودن هر مسیر عملیاتی به تنظیمات و مرحله اعتبارسنجی آن بستگی دارد.

## ✅ قابلیت‌های موجود در snapshot عمومی

- هسته تحلیل Price Action با ساختار قانون‌محور و خروجی‌های قابل‌بررسی
- تحلیل Context و اجزای ساختاری بازار در ماژول‌های پروژه
- زیرساخت Signal، Probability، Risk و lifecycle
- آداپتر عمومی Binance USD-M Futures در سورس
- مسیرهای paper/shadow برای ارزیابی بدون اتکا به معامله زنده
- PostgreSQL و migrationهای Alembic
- Telegram integration و ماژول‌های گزارش‌دهی
- Docker build و نصب ایزوله
- frozen-source verification با SHA256
- GitHub Actions برای تست و کنترل ایمنی انتشار

> [!NOTE]
> وجود یک ماژول یا مسیر در سورس به معنی فعال یا تأییدشدن آن برای استفاده عملیاتی نیست. قابلیت‌های حساس تا قبل از اعتبارسنجی مستقل باید غیرفعال بمانند.

## 🚀 نصب سریع

### پیش‌نیازها

سرور جدید باید از قبل این موارد را داشته باشد:

- Git
- Docker Engine با Docker daemon فعال
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

فقط روی یک **سرور جدید، جداگانه و ایزوله** اجرا کنید:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

installer ابتدا frozen source را بررسی می‌کند. اگر `.env` وجود نداشته باشد، یک فایل خصوصی با permission برابر `600` ایجاد می‌کند، `ADMIN_IDS` عددی را دریافت می‌کند، رمز URL-safe جدید برای PostgreSQL می‌سازد و پیش‌نیازها را بررسی می‌کند.

برای مجوز نهایی باید دقیقاً عبارت زیر وارد شود:

```text
INSTALL-NEW-HOST
```

فقط بعد از این تأیید، image برنامه ساخته می‌شود، volume اختصاصی PostgreSQL ایجاد می‌شود، migrationهای Alembic اعمال می‌شوند و سرویس‌ها بالا می‌آیند.

### بررسی بدون نصب

برای دریافت و بررسی snapshot بدون راه‌اندازی Docker، migration یا سرویس:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

حالت `--check` آفلاین است و frozen source و فایل‌های انتشار را بررسی می‌کند.

## 🔒 تنظیمات ایمنی پیش‌فرض

تا قبل از اعتبارسنجی جداگانه، این قابلیت‌ها باید خاموش بمانند:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

installer پکیج سیستم‌عامل را مخفیانه نصب نمی‌کند، package manager را تغییر نمی‌دهد، نصب موجود را overwrite نمی‌کند و برای جایگزینی یک deployment عملیاتی طراحی نشده است.

## 📦 بخش‌های مهم مخزن

- `production_source/` — snapshot عمومی انتخاب‌شده و hash-verified
- `production_checks/` — کنترل‌های frozen-source و regression
- `tests/` — مجموعه تست عمومی
- `Dockerfile.production` — build تصویر انتشار
- `compose.yaml` — PostgreSQL و سرویس‌های ایزوله
- `scripts/verify.sh` — بررسی آفلاین hash/source
- `scripts/install.sh` — installer محافظت‌شده
- `scripts/check_publication_safety.py` — کنترل محتوای قابل‌انتشار
- `.github/workflows/` — CI و publication safety

## 🧾 هویت frozen source

نسخه عمومی فعلی شامل **348 فایل بدون تغییر و hash-verified** است که توسط `production_source/SHA256SUMS` انتخاب شده‌اند.

Release manifest SHA256:

```text
769aa1757120c71ddf17579f18f1b63cd5ef3685a25287bd68d7c9bc7c341b49
```

Original immutable 361-entry development manifest SHA256:

```text
aacbb49f28d87cce9135b3d43c568d0c11cfb95cd469f627327cd52a4dc202ef
```

در curation انتشار، ۱۳ ورودی تاریخی کنار گذاشته شده‌اند: یک `.bak`، یک `.tmp` خالی و ۱۱ نسخه آرشیوی migration. ۳۴۸ فایل باقی‌مانده به‌صورت فردی با manifest اصلی تطابق دارند.

## 🛣️ تمرکز توسعه

تمرکز توسعه فعلی روی افزایش پوشش قواعد، اعتبارسنجی Context، regression testing، explainability خروجی‌ها، سخت‌گیری بیشتر در risk/lifecycle و ارزیابی paper/shadow قبل از هر تصمیم درباره مسیرهای عملیاتی است.

## 🤝 مشارکت و امنیت

- [راهنمای مشارکت](CONTRIBUTING.md)
- [گزارش مسائل امنیتی](SECURITY.md)
- [مرز انتشار متن‌باز](docs/OSS_PUBLICATION_REVIEW.md)
- [Apache License 2.0](LICENSE)

هرگز فایل `.env` تکمیل‌شده، token، کلید، dump پایگاه‌داده، log عملیاتی خصوصی، realized trades یا dataset خصوصی بازار را commit یا upload نکنید.

</details>

---

<details open>
<summary>🇬🇧 <strong>English</strong> — overview, capabilities and installation</summary>

<br>

## About the project

**Crypto Price Action** is an open-source cryptocurrency signal-system project built around **rule-based price-action analysis**. The development approach focuses on turning structural and contextual price-action concepts into logic that can be tested, traced, reviewed, and validated.

The public repository packages a curated, hash-verified source snapshot together with Docker deployment files, PostgreSQL configuration, public tests, integrity checks, publication-safety gates, and a guarded installer for a fresh isolated host.

### ✨ At a glance

| Area | Status / description |
| --- | --- |
| 🧠 Analysis core | Rule-based market structure, context, and price-action logic |
| 📊 Market data | Market-data adapters; a Binance USD-M Futures public adapter is present in source |
| 🛡️ Risk | Risk assessment and signal-lifecycle modules |
| 🧪 Validation | Public tests, frozen-source checks, and regression guards |
| 🐘 Database | PostgreSQL with async SQLAlchemy |
| 🐳 Runtime | Docker / Docker Compose |
| 📡 Integrations | Telegram and reporting paths, sensitive runtimes disabled by default |
| 🔐 Publication | SHA256 allowlist and publication-safety checks |
| 📜 License | Apache License 2.0 |

## 🧩 High-level architecture

```text
Market Data
    │
    ▼
Price-Action Context & Pattern Analysis
    │
    ▼
Signal / Probability Evaluation
    │
    ▼
Risk & Lifecycle Controls
    │
    ├──► Paper / Shadow paths
    ├──► PostgreSQL
    └──► Telegram / Reporting
```

This is a high-level conceptual view. The presence of a path in the source does not mean that it is enabled or operationally approved.

## ✅ What is present in the public snapshot

- Rule-based price-action analysis components with inspectable outputs
- Market-context and structural-analysis modules
- Signal, probability, risk, and lifecycle infrastructure
- A public Binance USD-M Futures adapter in source
- Paper/shadow evaluation paths
- PostgreSQL persistence and Alembic migrations
- Telegram integration and reporting modules
- Dockerized isolated deployment
- SHA256 frozen-source verification
- GitHub Actions for public tests and publication-safety checks

> [!NOTE]
> A module being present in source does not mean it is enabled or approved for production use. Sensitive runtime capabilities should remain disabled until they are independently validated.

## 🚀 Quick install

### Prerequisites

The new host must already provide:

- Git
- Docker Engine with a running Docker daemon
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

Run this only on a **new, separate, isolated host**:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

The installer verifies the frozen source first. If `.env` is missing, it creates a private file with mode `600`, asks for numeric `ADMIN_IDS`, generates a fresh URL-safe PostgreSQL password without displaying it, validates the environment, and checks Docker/Compose availability.

Final authorization requires entering exactly:

```text
INSTALL-NEW-HOST
```

Only after that confirmation does the installer build the application image, create a dedicated PostgreSQL volume, apply Alembic migrations, and start the services.

### Verification without installation

To download and verify the public snapshot without starting Docker, running migrations, or modifying services:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

The `--check` mode is offline and verifies the frozen source and publication files.

## 🔒 Safe defaults

Keep these capabilities disabled until each one has been separately validated and intentionally enabled:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

The installer does not silently install operating-system packages, modify the host package manager, overwrite an existing installation, or act as an in-place production upgrade mechanism.

## 📦 Repository map

- `production_source/` — curated, hash-verified public source snapshot
- `production_checks/` — frozen-source and regression guards
- `tests/` — reviewed public test corpus
- `Dockerfile.production` — published-image build
- `compose.yaml` — isolated service and PostgreSQL configuration
- `scripts/verify.sh` — offline source/hash verification
- `scripts/install.sh` — guarded fresh-host installer
- `scripts/check_publication_safety.py` — tracked-file publication checks
- `.github/workflows/` — CI and publication-safety workflows

## 🧾 Frozen source identity

The current public release source consists of **348 unchanged, hash-verified files** selected by the curated `production_source/SHA256SUMS` allowlist.

Release manifest SHA256:

```text
769aa1757120c71ddf17579f18f1b63cd5ef3685a25287bd68d7c9bc7c341b49
```

Original immutable 361-entry development manifest SHA256:

```text
aacbb49f28d87cce9135b3d43c568d0c11cfb95cd469f627327cd52a4dc202ef
```

Publication curation excluded 13 historical entries: one `.bak`, one empty `.tmp`, and 11 archived migration copies. The remaining 348 files match the original manifest individually.

## 🛣️ Development focus

Current development focuses on broader rule coverage, stronger context validation, regression testing, output explainability, tighter risk/lifecycle controls, and paper/shadow evaluation before any operational path is considered.

## 🤝 Contributing & security

- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Open-source publication boundary](docs/OSS_PUBLICATION_REVIEW.md)
- [Apache License 2.0](LICENSE)

Never commit or upload populated `.env` files, credentials, tokens, keys, database dumps, private operational logs, realized trades, or private market datasets.

</details>

---

<div align="center">

**Built for reproducible research, review, testing, and disciplined validation.**

[Repository](https://github.com/naseri-coder/crypto-price-action) · [Issues](https://github.com/naseri-coder/crypto-price-action/issues) · [Actions](https://github.com/naseri-coder/crypto-price-action/actions) · [Security](SECURITY.md)

</div>
