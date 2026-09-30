# Crypto Price Action

> **PUBLIC SOURCE SNAPSHOT — NOT APPROVED FOR PRODUCTION OR LIVE TRADING**
>
> Independent software project. It is not affiliated with, sponsored by, or endorsed by Al Brooks or the publishers of the referenced books.

**Installation guides / راهنمای نصب**

[🇮🇷 **فارسی — راهنمای نصب**](#راهنمای-نصب-فارسی) &nbsp;&nbsp; | &nbsp;&nbsp; [🇬🇧 **English — Installation Guide**](#english-installation-guide)

## Project overview

Crypto Price Action is an open-source cryptocurrency signal-system snapshot built around rule-based price-action analysis. The published repository contains a curated, hash-verified source snapshot, Docker packaging, PostgreSQL configuration, offline verification, publication-safety checks, and a guarded fresh-host installer.

The project is under active validation. The public snapshot is intended for review, development, testing, and reproducible installation on an isolated new host. It is **not a claim of profitability** and is **not approved for production or live trading**.

### توضیحات پروژه

**Crypto Price Action** یک پروژه متن‌باز برای سیستم سیگنال‌دهی ارزهای دیجیتال با تحلیل قانون‌محور Price Action است. نسخه عمومی شامل snapshot کنترل‌شده و hash-verified از سورس، بسته‌بندی Docker، PostgreSQL، بررسی آفلاین فایل‌ها، کنترل‌های ایمنی انتشار و installer محافظت‌شده برای نصب روی یک سرور جدید است.

پروژه هنوز در مرحله توسعه و اعتبارسنجی قرار دارد. این نسخه عمومی برای بررسی کد، توسعه، آزمایش و نصب قابل‌تکرار روی یک محیط جدید و ایزوله منتشر شده است و **به معنی تضمین سودآوری یا تأیید برای معامله زنده نیست**.

## Quick install / نصب یک‌فرمانی

### Requirements / پیش‌نیازها

The new host must already have **Git, Docker Engine, Docker Compose v2, Bash, Python 3, and `sha256sum`**.

روی سرور جدید باید **Git، Docker Engine، Docker Compose v2، Bash، Python 3 و `sha256sum`** موجود باشند.

### One command / یک فرمان

Run this only on a **new, separate host**:

این فرمان را فقط روی یک **سرور جدید و جداگانه** اجرا کنید:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

The installer verifies the frozen source first. If `.env` does not exist, it creates a private `.env` with permission `600`, asks for numeric `ADMIN_IDS`, generates a fresh URL-safe PostgreSQL password without displaying it, validates the configuration, checks Docker/Compose, and finally asks you to type:

installer ابتدا frozen source را بررسی می‌کند. اگر `.env` وجود نداشته باشد، فایل خصوصی `.env` را با permission برابر `600` می‌سازد، `ADMIN_IDS` عددی را از شما می‌پرسد، یک رمز جدید و URL-safe برای PostgreSQL بدون نمایش آن تولید می‌کند، تنظیمات و Docker/Compose را بررسی می‌کند و در پایان از شما می‌خواهد دقیقاً این عبارت را وارد کنید:

```text
INSTALL-NEW-HOST
```

Only after that confirmation does it build the image, create the dedicated PostgreSQL volume, start PostgreSQL, apply Alembic migrations, and start the bot. Telegram and trading-related runtime features remain disabled by default.

فقط بعد از این تأیید، image ساخته می‌شود، volume اختصاصی PostgreSQL ایجاد می‌شود، PostgreSQL اجرا می‌شود، migrationهای Alembic اعمال می‌شوند و bot بالا می‌آید. قابلیت‌های Telegram و runtimeهای مرتبط با معامله به‌صورت پیش‌فرض غیرفعال باقی می‌مانند.

> **Important:** the installer does not silently install operating-system packages or modify the host package manager. If a prerequisite is missing, it stops and reports the missing requirement.
>
> **مهم:** installer پکیج‌های سیستم‌عامل را به‌صورت مخفیانه نصب نمی‌کند و package manager سرور را تغییر نمی‌دهد. اگر پیش‌نیازی وجود نداشته باشد، متوقف می‌شود و مورد کمبود را اعلام می‌کند.

## Verification only / فقط بررسی بدون نصب

If you only want to download and verify the snapshot without installing services:

اگر فقط می‌خواهید پروژه را دریافت و بدون نصب سرویس‌ها بررسی کنید:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

`--check` is offline and does **not** call Docker, access the network, run database migrations, or start/modify services.

حالت `--check` آفلاین است و Docker را فراخوانی نمی‌کند، migration اجرا نمی‌کند و هیچ سرویسی را راه‌اندازی یا تغییر نمی‌دهد.

---

## English Installation Guide

### 1. Prepare a new host

This installer is strictly for a **fresh, separate host**. It is not an in-place upgrade or database-migration path for an existing deployment.

Install or make available:

- Git
- Docker Engine
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

Confirm that the Docker daemon is running and accessible by the account that will perform the installation.

### 2. Clone the repository

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

### 3. Verify before installation

```bash
bash scripts/install.sh --check
```

Continue only if the verification succeeds.

### 4. Choose automatic or manual environment setup

**Recommended:** simply run `--install`. If `.env` is absent, the installer securely creates it and asks for the numeric administrator ID.

```bash
bash scripts/install.sh --install
```

For manual configuration instead:

```bash
cp .env.example .env
chmod 600 .env
```

Then edit `.env`. Use a numeric `ADMIN_IDS`, create a fresh URL-safe database password of 24–96 characters, and place the same password in `POSTGRES_PASSWORD` and the password portion of `DATABASE_URL`. Never commit or upload the populated `.env`.

Keep these safety defaults unchanged unless they have been separately validated and intentionally enabled:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

### 5. Complete installation

If you used the manual environment path, run:

```bash
bash scripts/install.sh --install
```

Review the preflight output. When the installer asks for final authorization, type exactly:

```text
INSTALL-NEW-HOST
```

The installer deliberately refuses to overwrite an existing installation volume or install over the original protected project path.

### 6. After installation

Review container/service status before enabling any optional runtime. Do not enable Telegram, paper trading, Brooks runtime, Brooks operations, performance reporting, or live-trading-related behavior until each capability has been separately validated.

---

## راهنمای نصب فارسی

### ۱. آماده‌سازی سرور جدید

این installer فقط برای یک **سرور تازه و جداگانه** است. از آن برای ارتقای نصب موجود یا مهاجرت مستقیم یک پایگاه‌داده عملیاتی استفاده نکنید.

این ابزارها باید موجود باشند:

- Git
- Docker Engine
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

همچنین مطمئن شوید Docker daemon فعال است و کاربری که نصب را انجام می‌دهد اجازه استفاده از Docker را دارد.

### ۲. دریافت پروژه

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

### ۳. بررسی پروژه قبل از نصب

```bash
bash scripts/install.sh --check
```

فقط اگر این مرحله با موفقیت تمام شد، نصب را ادامه دهید.

### ۴. انتخاب تنظیم خودکار یا دستی `.env`

**روش پیشنهادی:** مستقیماً `--install` را اجرا کنید. اگر `.env` وجود نداشته باشد، installer آن را به‌صورت امن می‌سازد و فقط شناسه عددی مدیر را از شما می‌پرسد.

```bash
bash scripts/install.sh --install
```

اگر می‌خواهید `.env` را دستی تنظیم کنید:

```bash
cp .env.example .env
chmod 600 .env
```

سپس `.env` را ویرایش کنید. `ADMIN_IDS` باید عددی باشد. یک رمز جدید و URL-safe با طول ۲۴ تا ۹۶ کاراکتر بسازید و همان رمز را هم در `POSTGRES_PASSWORD` و هم در قسمت password از `DATABASE_URL` قرار دهید. فایل تکمیل‌شده `.env` را هرگز commit یا upload نکنید.

تا زمانی که هر قابلیت جداگانه اعتبارسنجی و عمداً فعال نشده است، این مقادیر را تغییر ندهید:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

### ۵. تکمیل نصب

اگر روش دستی `.env` را انتخاب کرده‌اید، این دستور را اجرا کنید:

```bash
bash scripts/install.sh --install
```

خروجی preflight را بررسی کنید. وقتی installer تأیید نهایی خواست، دقیقاً عبارت زیر را وارد کنید:

```text
INSTALL-NEW-HOST
```

installer عمداً از overwrite کردن volume نصب قبلی یا نصب روی مسیر محافظت‌شده پروژه اصلی جلوگیری می‌کند.

### ۶. بعد از نصب

قبل از فعال‌کردن هر runtime اختیاری، وضعیت containerها و سرویس‌ها را بررسی کنید. Telegram، paper trading، Brooks runtime، Brooks operations، performance reporting و قابلیت‌های مرتبط با معامله زنده را فقط پس از اعتبارسنجی جداگانه فعال کنید.

---

## Repository contents

- `production_source/` — curated frozen source snapshot verified by `production_source/SHA256SUMS`.
- `production_checks/` — frozen-source guard checks.
- `Dockerfile.production` — builds the published snapshot and runs the guard during build.
- `compose.yaml` — isolated PostgreSQL service with no host database port and runtime flags off by default.
- `scripts/verify.sh` — offline source/hash and syntax verification.
- `scripts/install.sh` — guarded fresh-host installer.
- `scripts/bootstrap_env.py` — private fresh-host environment bootstrap used by the installer.
- `scripts/check_publication_safety.py` — tracked-file publication safety checks.

## Frozen source identity

The release source consists of **348 unchanged, hash-verified files** selected by the curated `production_source/SHA256SUMS` allowlist.

Release manifest SHA256:

```text
8bb1e75b35fb333925a4c6ec1595fb9dfc273cc854203e577c4ed19e4bbc21b0
```

The original immutable 361-entry development manifest SHA256 is:

```text
aacbb49f28d87cce9135b3d43c568d0c11cfb95cd469f627327cd52a4dc202ef
```

Publication curation excluded 13 historical entries: one `.bak`, one empty `.tmp`, and 11 archived migration copies. The remaining 348 files match the original manifest individually. Publication-hardening documentation, CI, and installer changes do **not** alter the frozen `production_source` identity.

## Open-source publication status

This repository is the public open-source snapshot. See `docs/OSS_PUBLICATION_REVIEW.md` for the source-expression and publication-review boundary, `SECURITY.md` for security reporting, and `CONTRIBUTING.md` for contribution guidance.

The project is licensed under the Apache License 2.0. See `LICENSE`. The license does not change separate third-party rights, source-expression, security, release-integrity, or operational-validation boundaries.

## Operational validation still open

- Historical image equivalence is not independently established.
- Docker build and disposable-database migration/test validation should be performed only on a separately authorized isolated host.
- The test suite still needs to be reconciled against the selected immutable public-source snapshot and documented with support/rollback procedures.

Never upload `.env`, backup archives, SQLite data, database dumps, operational logs, keys, realized trades, or private market datasets.

No source, Docker service, or database in the original `/opt/crypto-signal-telegram-bot` development tree was modified by these publication changes.
