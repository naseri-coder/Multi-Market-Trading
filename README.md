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

## Installation / نصب

**Choose your guide / راهنمای خود را انتخاب کنید:**

[🇮🇷 **راهنمای نصب فارسی**](#راهنمای-نصب-فارسی) &nbsp;&nbsp; | &nbsp;&nbsp; [🇬🇧 **English Installation Guide**](#english-installation-guide)

### Quick install / نصب یک‌باره

For a **new, separate host only**, after Git, Docker Engine + Compose v2, Bash, Python 3, and `sha256sum` are available:

فقط روی یک **سرور جدید و جداگانه** و پس از موجود بودن Git، Docker Engine + Compose v2، Bash، Python 3 و `sha256sum`:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

This is the actual one-command installation path. If `.env` does not exist, the installer creates it with mode `600`, asks for the numeric `ADMIN_IDS`, generates a fresh database password without displaying it, validates the configuration, and then asks for the final `INSTALL-NEW-HOST` confirmation.

این دستور، مسیر واقعی نصب یک‌باره است. اگر فایل `.env` وجود نداشته باشد، installer آن را با دسترسی `600` می‌سازد، شناسه عددی `ADMIN_IDS` را از شما می‌پرسد، رمز جدید پایگاه‌داده را بدون نمایش آن تولید می‌کند، تنظیمات را بررسی می‌کند و در پایان برای شروع نصب عبارت `INSTALL-NEW-HOST` را جهت تأیید درخواست می‌کند.

> The three-line command ending in `bash scripts/install.sh --check` is a **verification command only**; it does not install the application.
>
> دستور سه‌خطی که به `bash scripts/install.sh --check` ختم می‌شود **فقط برای بررسی است** و برنامه را نصب نمی‌کند.

The installer is not an upgrade or migration path for an existing deployment.

این installer برای ارتقا یا مهاجرت نصب موجود طراحی نشده است.

### English Installation Guide

#### 1. Prerequisites

Install these tools on the new host:

- Git
- Docker Engine
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

Then clone the repository and enter its directory:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

#### 2. Verify the frozen source before installation

Run:

```bash
bash scripts/install.sh --check
```

A successful check verifies the frozen source and installation files. This mode does **not** call Docker, access the network, run database migrations, or start/modify services.

Do not continue to installation if this check fails.

#### 3. Create and protect the environment file

Run:

```bash
cp .env.example .env
chmod 600 .env
```

For the manual path, open `.env` locally and configure it before installation. The quick-install path can create this file automatically:

- Replace `ADMIN_IDS` with the private numeric administrator ID.
- Generate a new URL-safe database password of at least 24 characters.
- Put that same password in `POSTGRES_PASSWORD` and in the password portion of `DATABASE_URL`.
- Keep `TELEGRAM_RUNTIME_ENABLED=false`.
- Keep `BROOKS_RUNTIME_ENABLED=false`.
- Keep `BROOKS_OPERATIONS_ENABLED=false`.
- Keep `PAPER_RUNTIME_ENABLED=false`.
- Keep `PERFORMANCE_REPORTS_ENABLED=false`.
- Never commit or upload the populated `.env` file.

#### 4. Install on the new host

Run:

```bash
bash scripts/install.sh --install
```

The installer performs its safety checks and then asks for interactive confirmation. To continue, type exactly:

```text
INSTALL-NEW-HOST
```

The installer then builds the application image, creates a dedicated PostgreSQL volume, starts PostgreSQL, applies the database migrations, and starts the bot. Trading-related and Telegram runtime features remain disabled by default.

The installer deliberately refuses to proceed if it detects the original project path or an existing installation volume. It is not an in-place upgrade tool.

#### 5. Important safety notes

Do not enable Telegram, paper trading, Brooks runtime, Brooks operations, performance reporting, or live-trading-related behavior until those capabilities have been separately validated and you intentionally choose to enable them.

Do not use real secrets from another deployment. Create fresh credentials for this installation.

---

### راهنمای نصب فارسی

#### ۱. پیش‌نیازها

این ابزارها را روی **سرور جدید و جداگانه** نصب کنید:

- Git
- Docker Engine
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

سپس مخزن را دریافت کنید و وارد پوشه پروژه شوید:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

#### ۲. بررسی فایل‌ها قبل از نصب

ابتدا این دستور را اجرا کنید:

```bash
bash scripts/install.sh --check
```

اگر بررسی موفق باشد، فایل‌های frozen source و فایل‌های لازم برای نصب تأیید شده‌اند. حالت `--check` هیچ سرویس Docker را اجرا یا تغییر نمی‌دهد، به شبکه دسترسی نمی‌زند، migration پایگاه‌داده را اجرا نمی‌کند و هیچ سرویسی را راه‌اندازی نمی‌کند.

**اگر این مرحله خطا داد، نصب را ادامه ندهید.**

#### ۳. ساخت و تنظیم فایل محیطی

این دو دستور را اجرا کنید:

```bash
cp .env.example .env
chmod 600 .env
```

در روش دستی، فایل `.env` را روی همان سرور ویرایش کنید. در روش نصب یک‌باره، installer می‌تواند این فایل را به‌صورت خودکار و امن ایجاد کند:

- مقدار `ADMIN_IDS` را با شناسه عددی خصوصی مدیر جایگزین کنید.
- یک رمز جدید، تصادفی و URL-safe با حداقل ۲۴ کاراکتر برای پایگاه‌داده بسازید.
- همان رمز را در `POSTGRES_PASSWORD` و قسمت رمزِ `DATABASE_URL` قرار دهید.
- `TELEGRAM_RUNTIME_ENABLED=false` باقی بماند.
- `BROOKS_RUNTIME_ENABLED=false` باقی بماند.
- `BROOKS_OPERATIONS_ENABLED=false` باقی بماند.
- `PAPER_RUNTIME_ENABLED=false` باقی بماند.
- `PERFORMANCE_REPORTS_ENABLED=false` باقی بماند.
- فایل تکمیل‌شده `.env` را هرگز commit یا upload نکنید.

#### ۴. اجرای نصب

فقط روی همان **سرور جدید و جداگانه** اجرا کنید:

```bash
bash scripts/install.sh --install
```

اسکریپت ابتدا کنترل‌های ایمنی را انجام می‌دهد و سپس برای ادامه، تأیید تعاملی می‌خواهد. برای تأیید باید دقیقاً عبارت زیر را وارد کنید:

```text
INSTALL-NEW-HOST
```

پس از تأیید، اسکریپت image برنامه را می‌سازد، یک volume اختصاصی PostgreSQL ایجاد می‌کند، PostgreSQL را بالا می‌آورد، migrationهای پایگاه‌داده را اعمال می‌کند و سپس bot را اجرا می‌کند. قابلیت‌های مربوط به معامله و Telegram به‌صورت پیش‌فرض غیرفعال باقی می‌مانند.

اگر مسیر پروژه اصلی یا volume مربوط به یک نصب قبلی تشخیص داده شود، installer عمداً متوقف می‌شود. این اسکریپت برای ارتقای نصب موجود طراحی نشده است.

#### ۵. نکات مهم ایمنی

تا زمانی که هر قابلیت به‌صورت جداگانه بررسی و تأیید نشده است، Telegram، paper trading، Brooks runtime، Brooks operations، performance reporting و قابلیت‌های مرتبط با معامله زنده را فعال نکنید.

برای این نصب credential و رمزهای جدید بسازید و از secretهای یک نصب یا سرور دیگر استفاده نکنید.


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
