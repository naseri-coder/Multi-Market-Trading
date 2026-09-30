# Crypto Price Action

> **PUBLIC SOURCE SNAPSHOT — NOT APPROVED FOR PRODUCTION OR LIVE TRADING**
>
> Independent software project. It is not affiliated with, sponsored by, or endorsed by Al Brooks or the publishers of the referenced books.

[🇬🇧 **English documentation**](#english) &nbsp;&nbsp; | &nbsp;&nbsp; [🇮🇷 **راهنمای فارسی**](#فارسی)

---

<a id="english"></a>
# English

## Project overview

**Crypto Price Action** is an open-source cryptocurrency signal-system snapshot built around rule-based price-action analysis. The public repository packages a curated, hash-verified source snapshot together with Docker deployment files, PostgreSQL configuration, offline integrity checks, publication-safety checks, and a guarded installer for a fresh isolated host.

The project is still under development and validation. This public snapshot is intended for source review, development, testing, and reproducible installation in an isolated environment. It does **not** claim profitability and is **not approved for production or live trading**.

## Quick install — one command

### Prerequisites

The new host must already provide:

- Git
- Docker Engine with a running Docker daemon
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

Run the following command on a **new, separate host only**:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

The installer first verifies the frozen source. If `.env` is missing, it creates a private file with mode `600`, asks for numeric `ADMIN_IDS`, generates a fresh URL-safe PostgreSQL password without displaying it, validates the environment, verifies Docker and Compose availability, and asks for final authorization:

```text
INSTALL-NEW-HOST
```

Only after that confirmation does the installer build the application image, create a dedicated PostgreSQL volume, start PostgreSQL, apply Alembic migrations, and start the bot.

The installer does **not** silently install operating-system packages or modify the host package manager. If a prerequisite is missing, it stops and reports the missing requirement.

## Verification without installation

To download and verify the public snapshot without starting Docker services or changing a database:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

The `--check` mode is offline. It verifies the frozen source and installation files without calling Docker, accessing the network, running migrations, or starting/modifying services.

## Step-by-step installation

### 1. Prepare a fresh host

This installer is strictly for a **new, separate host**. It is not an in-place upgrade mechanism and must not be used to overwrite an existing deployment or operational database.

Install the prerequisites listed above and confirm that your account can access the Docker daemon.

### 2. Clone the repository

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

### 3. Run the offline verification

```bash
bash scripts/install.sh --check
```

Do not continue if verification fails.

### 4. Configure the environment

The recommended path is to let `--install` create a missing `.env` securely:

```bash
bash scripts/install.sh --install
```

For manual configuration:

```bash
cp .env.example .env
chmod 600 .env
```

Then edit `.env`. `ADMIN_IDS` must contain numeric administrator IDs. Use a fresh URL-safe database password between 24 and 96 characters, and place the same password in `POSTGRES_PASSWORD` and the password component of `DATABASE_URL`. Never commit or upload a populated `.env`.

Keep these safety defaults disabled unless each capability has been separately validated and intentionally enabled:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

### 5. Authorize and complete installation

When prompted, review the preflight output and type exactly:

```text
INSTALL-NEW-HOST
```

The installer refuses to overwrite its existing installation volume and refuses installation on the protected original-project host path.

### 6. After installation

Review container and service status before enabling optional runtime features. Telegram integration, paper trading, Brooks runtime, Brooks operations, performance reporting, and any live-trading-related behavior should remain disabled until separately validated.

---

<a id="فارسی"></a>
# فارسی

## معرفی پروژه

**Crypto Price Action** یک پروژه متن‌باز برای توسعه یک سیستم سیگنال‌دهی ارزهای دیجیتال بر پایه تحلیل قانون‌محور Price Action است. مخزن عمومی پروژه شامل یک snapshot انتخاب‌شده و hash-verified از سورس، فایل‌های Docker، تنظیمات PostgreSQL، ابزار بررسی آفلاین یکپارچگی فایل‌ها، کنترل‌های ایمنی انتشار و installer محافظت‌شده برای راه‌اندازی روی یک سرور جدید و ایزوله است.

هدف از این نسخه عمومی این است که سورس پروژه قابل بررسی، توسعه، آزمایش و نصب تکرارپذیر باشد. پروژه همچنان در حال توسعه و اعتبارسنجی است؛ بنابراین انتشار این مخزن **به معنی تضمین سودآوری، آماده‌بودن برای محیط عملیاتی یا تأیید برای معامله زنده نیست**.

## نصب سریع با یک فرمان

### پیش‌نیازها

روی سرور جدید باید موارد زیر از قبل موجود و قابل استفاده باشند:

- Git
- Docker Engine و Docker daemon فعال
- Docker Compose v2
- Bash
- Python 3
- `sha256sum`

سپس فقط روی یک **سرور جدید و جداگانه** این فرمان را اجرا کنید:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git && cd crypto-price-action && bash scripts/install.sh --install
```

این فرمان مخزن را دریافت می‌کند، وارد پوشه پروژه می‌شود و installer را اجرا می‌کند. installer ابتدا frozen source را بررسی می‌کند. اگر فایل `.env` وجود نداشته باشد، آن را با permission برابر `600` ایجاد می‌کند، شناسه عددی مدیر یا مدیران را در `ADMIN_IDS` از شما می‌پرسد و یک رمز جدید و URL-safe برای PostgreSQL تولید می‌کند. رمز تولیدشده در خروجی نمایش داده نمی‌شود.

پس از اعتبارسنجی `.env` و بررسی Docker/Compose، installer برای مجوز نهایی از شما می‌خواهد دقیقاً عبارت زیر را وارد کنید:

```text
INSTALL-NEW-HOST
```

فقط پس از این تأیید، image برنامه ساخته می‌شود، volume اختصاصی PostgreSQL ایجاد می‌شود، PostgreSQL بالا می‌آید، migrationهای Alembic اعمال می‌شوند و bot اجرا می‌شود.

installer پکیج‌های سیستم‌عامل را به‌صورت خودکار و مخفیانه نصب نمی‌کند و package manager سرور را تغییر نمی‌دهد. اگر پیش‌نیازی موجود نباشد، نصب متوقف می‌شود و مورد کمبود اعلام می‌شود.

## بررسی پروژه بدون نصب

اگر فقط می‌خواهید سورس عمومی را دریافت و صحت آن را بررسی کنید و نمی‌خواهید هیچ سرویس یا پایگاه‌داده‌ای راه‌اندازی شود:

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
bash scripts/install.sh --check
```

حالت `--check` آفلاین است. این حالت frozen source و فایل‌های نصب را بررسی می‌کند، اما Docker را فراخوانی نمی‌کند، migration پایگاه‌داده را اجرا نمی‌کند و هیچ سرویسی را راه‌اندازی یا تغییر نمی‌دهد.

## راهنمای نصب مرحله‌به‌مرحله

### ۱. آماده‌سازی یک سرور جدید

installer فقط برای یک **سرور تازه، جداگانه و ایزوله** طراحی شده است. از آن برای overwrite کردن نصب موجود، ارتقای مستقیم یک deployment عملیاتی یا مهاجرت یک پایگاه‌داده فعال استفاده نکنید.

پیش‌نیازهای بالا را نصب کنید و مطمئن شوید کاربری که نصب را انجام می‌دهد به Docker daemon دسترسی دارد.

### ۲. دریافت پروژه

```bash
git clone https://github.com/naseri-coder/crypto-price-action.git
cd crypto-price-action
```

### ۳. بررسی آفلاین قبل از نصب

```bash
bash scripts/install.sh --check
```

اگر این مرحله با خطا تمام شد، نصب را ادامه ندهید.

### ۴. تنظیم محیط و فایل `.env`

روش پیشنهادی این است که اجازه دهید installer در صورت نبود `.env` آن را به‌صورت خودکار و امن بسازد:

```bash
bash scripts/install.sh --install
```

در این روش فقط `ADMIN_IDS` عددی از شما خواسته می‌شود و رمز PostgreSQL به‌صورت خودکار تولید می‌شود.

اگر می‌خواهید تنظیمات را دستی انجام دهید:

```bash
cp .env.example .env
chmod 600 .env
```

سپس فایل `.env` را ویرایش کنید. مقدار `ADMIN_IDS` باید شامل شناسه عددی مدیر یا مدیران باشد. برای PostgreSQL یک رمز جدید، تصادفی و URL-safe با طول ۲۴ تا ۹۶ کاراکتر بسازید و دقیقاً همان رمز را در `POSTGRES_PASSWORD` و بخش password از `DATABASE_URL` قرار دهید. فایل تکمیل‌شده `.env` را هرگز commit یا upload نکنید.

تا زمانی که هر قابلیت جداگانه آزمایش و عمداً فعال نشده است، تنظیمات زیر باید غیرفعال باقی بمانند:

```text
TELEGRAM_RUNTIME_ENABLED=false
BROOKS_RUNTIME_ENABLED=false
BROOKS_OPERATIONS_ENABLED=false
PAPER_RUNTIME_ENABLED=false
PERFORMANCE_REPORTS_ENABLED=false
```

### ۵. تأیید نهایی و اجرای نصب

پس از اجرای `--install`، خروجی preflight را بررسی کنید. وقتی installer مجوز نهایی خواست، دقیقاً عبارت زیر را وارد کنید:

```text
INSTALL-NEW-HOST
```

installer عمداً در صورت تشخیص volume نصب قبلی متوقف می‌شود و همچنین اجازه نصب روی مسیر محافظت‌شده پروژه اصلی را نمی‌دهد.

### ۶. بعد از نصب چه کار کنیم؟

بعد از پایان نصب، ابتدا وضعیت containerها و سرویس‌ها را بررسی کنید. قابلیت‌های Telegram، paper trading، Brooks runtime، Brooks operations، performance reporting و هر قابلیت مرتبط با معامله زنده را تا قبل از اعتبارسنجی جداگانه فعال نکنید.

اگر installer به دلیل نبود پیش‌نیاز متوقف شد، ابتدا همان پیش‌نیاز اعلام‌شده را روی سیستم نصب یا فعال کنید و سپس فرمان نصب را دوباره اجرا کنید. اگر `.env` قبلاً ایجاد شده باشد، installer از همان فایل موجود استفاده می‌کند و آن را بدون اجازه بازنویسی نمی‌کند.

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
