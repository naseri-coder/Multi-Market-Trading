<div align="center">

# 📈 Multi Market Trading

**Multi-market architecture · Public strategy SDK · Offline PAPER verification**

**معماری چندبازاره، هسته‌های مستقل و مسیر آزمایشی قابل‌تکرار — بدون ادعای معامله یا سیگنال زنده**

[![Public tests](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/public-test-corpus.yml/badge.svg?branch=main)](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/public-test-corpus.yml)
[![Publication safety](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/publication-safety.yml/badge.svg?branch=main)](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/publication-safety.yml)
[![Legacy v0.3.2](https://img.shields.io/badge/version-v0.3.2-7C3AED)](pyproject.toml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache--2.0-0B7285)](LICENSE)
[![Status](https://img.shields.io/badge/Release-NONPRODUCTION%20ONLY-orange)](docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md)

[شروع سریع](#quickstart) · [وضعیت واقعی](#status) · [معماری](#architecture) · [مستندات](#documents) · [English summary](#english)

[کانال توسعه](https://t.me/naseri_coder) · [GitHub Issues](https://github.com/naseri-coder/Multi-Market-Trading/issues) · [Security](SECURITY.md)

</div>

> [!IMPORTANT]
> **This repository is not an authorized public signal service or live trading product.** The installed PAPER example produces **synthetic demonstration evidence**, never a broker fill or a real trading recommendation. Source verification, isolated tests and CI are not equivalent to real-feed quality, hostile-code isolation, profitability or deployment approval.

<a id="status"></a>
## وضعیت پروژه | Product status

The repository contains **two intentionally distinct software lines**. **Do not run the legacy manager to install the new preview.**

| مسیر | نسخه | وضعیت دقیق | دستور یا نقطه ورود |
| --- | --- | --- | --- |
| Historical crypto runtime | `crypto-price-action 0.3.2` | کد قدیمی محفوظ؛ مدیریت جداگانه | `bash markets.sh` / `crypto-signal-bot` |
| New multi-market distribution | `multi-market-trading 0.4.0rc1` | پیش‌نمایش نصب‌شدنی و غیرتولیدی | `naseri-markets --check` |
| **Installed public toy PAPER MVP** | Same `0.4.0rc1` preview | نمونه عمومی، ثبت SQLite و Replay تکرارپذیر | **`naseri-paper-demo`** |
| Trusted local public Custom | Same preview | فقط کد مستقل بررسی‌شده و مورد اعتماد اپراتور | `naseri-custom` |
| Telegram development panel | Optional `telegram-admin` extra | فقط تنظیمات و پیش‌نمایش؛ اتصال عملیاتی جدید غیرفعال | `naseri-engine-admin` / opt-in Stage 12 |
| Universal Core API / risk / lifecycle / research | Stages 3–15 | قراردادها و اجزای PAPER/آزمایشی، **نه یک سرویس LIVE یکپارچه** | کتابخانه‌ها و آزمون‌های مستقل |

**گیت انتشار:** `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`؛ انتشار کانال تلگرام، معاملات واقعی، اجرای کد ناشناس عمومی و استقرار تجاری هنوز مجاز یا تأیید نشده‌اند. [گزارش آمادگی مرحله ۱۵](docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md).

<a id="quickstart"></a>
## شروع سریع | Installed PAPER demo

این مسیر از یک نمونه **عمومی و بی‌خطر از نظر منطق معاملاتی** استفاده می‌کند تا کاربر بتواند ثبت، فعال‌سازی، Replay، حذف تکرار، ذخیره پایدار و بازبینی پس از ری‌استارت را واقعاً آزمایش کند. خروجی صرفاً شبیه‌سازی و آموزش توسعه است؛ استراتژی سودده یا داده واقعی محسوب نمی‌شود.

**پیش‌نیاز:** Linux/macOS توسعه‌ای، Python 3.12، یک کپی محلی از مخزن، و محیط جدا از سرور تولیدی. از حساب بدون دسترسی ویژه استفاده کنید.

```bash
# Build/install the separate new-product preview in an isolated venv.
python3.12 -m venv /tmp/mmt-paper-venv
/tmp/mmt-paper-venv/bin/python scripts/a6_prepare_package.py --destination /tmp/mmt-paper-package
/tmp/mmt-paper-venv/bin/python -m pip install /tmp/mmt-paper-package

# A NEW private state directory; do not reuse an old or production folder.
export MMT_NONPRODUCTION=1
PAPER=/tmp/mmt-paper-example
/tmp/mmt-paper-venv/bin/naseri-paper-demo --state-dir "$PAPER" init --ack-reviewed-public-toy
```

خروجی `init` شامل `descriptor_sha256` و `revision=1` است. **مقدار هش را از همان خروجی بررسی و جایگزین کنید**؛ سپس مراحل بعدی را اجرا کنید:

```bash
PAPER_CLI=/tmp/mmt-paper-venv/bin/naseri-paper-demo
$PAPER_CLI --state-dir "$PAPER" enable --revision 1 \
  --descriptor-sha256 YOUR_INIT_DESCRIPTOR_SHA256
$PAPER_CLI --state-dir "$PAPER" replay --ack-offline-replay
$PAPER_CLI --state-dir "$PAPER" replay --ack-offline-replay  # DUPLICATE
$PAPER_CLI --state-dir "$PAPER" inspect                       # restart-safe
$PAPER_CLI --state-dir "$PAPER" disable --revision 2
$PAPER_CLI --state-dir "$PAPER" inspect                       # history preserved
```

اولین Replay یک **سیگنال مصنوعی PAPER** را ثبت می‌کند؛ اجرای دوباره همان داده باید `DUPLICATE` باشد. نتیجه بعد از اجرای مجدد دستور (حتی در یک پردازش جدید) باقی می‌ماند. هیچ پیامی به تلگرام و هیچ سفارشی به بروکر ارسال نمی‌شود. ورودی `LIVE` رد می‌شود و اجرای هسته فقط بعد از تأیید صریح ممکن است.

[**راهنمای جامع مسیر نصب و آزمون PAPER**](docs/PAPER_MVP_INSTALLED_USER_JOURNEY_V1.md) · [راهنمای کد محلی مورد اعتماد](docs/TRUSTED_LOCAL_CUSTOM_PAPER_MVP.md)

> [!WARNING]
> `naseri-paper-demo` **فقط نمونه عمومی همراه بسته** را اجرا می‌کند و جایگزین سامانه امن اجرای هسته‌های ناشناس نیست. `python -I -S` sandbox نیست. فایل‌ها و توکن‌های تولیدی را به این محیط وارد نکنید.

<a id="architecture"></a>
## معماری | Architecture

```text
                       Multi Market Trading (public source)
   ┌─────────────────────────────────────────────────────────────┐
   │ Control plane: engine inventory, per-instance configuration │
   │ Provider/symbol/timeframe, requested risk, separate toggles │
   └───────────────────────────┬─────────────────────────────────┘
                               │ preview / policy, not an automatic live grant
   ┌───────────────────────────▼─────────────────────────────────┐
   │ Offline market data → Core API → strategy orchestrator      │
   │            → PAPER risk / position / signal journals        │
   └───────────────────────────┬─────────────────────────────────┘
                               │ audited offline tests / evidence
   ┌───────────────────────────▼─────────────────────────────────┐
   │ Research, reliability, developer SDK and release gates     │
   └─────────────────────────────────────────────────────────────┘

   INSTALLED WORKING TOY PATH (separate, existing authority reused):
   naseri-paper-demo → trusted public toy → TrustedLocalCustomHost
                     → single SQLite PAPER journal → restart/inspect

   NO implicit link to LIVE exchange, broker orders or Telegram publishing.
```

**مرز مسئولیت‌ها:** هسته فقط ستاپ و منطق تصمیم را تعیین می‌کند؛ انتخاب صرافی/بروکر، نماد، تایم‌فریم، سرمایه، مدیریت ریسک و مجوزهای سیگنال/سفارش متعلق به پلتفرم است. «درخواست فعال‌سازی» در پنل به معنای «مجوز واقعی اجرا» نیست. انتخاب نماد در رجیستری پژوهشی نیز دسترسی قانونی یا امکان معامله را اثبات نمی‌کند.

### دستاوردها و وضعیت عملیاتی

| قابلیت | توسعه / آزمون | محدودیت |
| --- | --- | --- |
| Universal Core API v1, multi-binding orchestration | قرارداد و آزمون‌های offline | بدون فعال‌سازی خودکار LIVE |
| Market feed / instrument registry | Replay/Synthetic و پژوهش متادیتا | بدون اصالت‌سنجی کافی قیمت اجرایی واقعی |
| Portfolio/risk + multi-target PAPER lifecycle | پیاده‌سازی و تست مدل‌سازی | بدون سفارش یا پرشدن واقعی بروکر |
| Signal lifecycle + delivery journal | صف خشک و بازبینی داخلی | بدون اثبات ارسال/ویرایش پیام واقعی |
| Strategy Research Lab | تحلیل شواهد PAPER و دوره‌های Train/Validation/Holdout | **بک‌تست واقعی جدید یا Edge سودده تأیید نشده** |
| Trading Control Center | پنل توسعه‌ای چند هسته/نماد/تایم‌فریم | بدون اتصال خودکار به موتور معاملات |
| Reliability, SDK, signatures, release gates | ممیزی و آزمون ساختاری | بدون تأیید خصمانه gVisor یا مجوز Marketplace |
| **Public toy PAPER user journey** | **نصب Wheel → ثبت → Replay → ری‌استارت → inspect** | فقط نمونه عمومی trusted، بدون Telegram/سفارش |

**Brooks Price Action** هسته مرجع عمومی پروژه است؛ فعال‌سازی خودکار آن در محصول جدید از این نمونه نتیجه نمی‌شود. **NY First-Reversal** اختصاصی و *owner-only* است: هیچ سورس، بسته یا مجوز اجرای عمومی آن در مخزن قرار نمی‌گیرد.

<a id="documents"></a>
## راهنما و منابع فنی | Documentation

| موضوع | سند |
| --- | --- |
| **Installed public PAPER journey** | [PAPER MVP guide](docs/PAPER_MVP_INSTALLED_USER_JOURNEY_V1.md) |
| Separate preview distribution / installed demo | [New product release readme](platform_release/README.md) |
| Historically preserved runtime and manager | [Installation](docs/INSTALLATION.md) · [Recovery](docs/REBUILD_RESTORE.md) |
| Universal Core API, market data, secure runtime | [Core API](docs/UNIVERSAL_CORE_API_V1.md) · [Secure runtime](docs/SECURE_PLUGIN_RUNTIME_STAGE4_V1.md) · [Data engine](docs/UNIVERSAL_MARKET_DATA_STAGE5_V1.md) |
| Instrument metadata and bindings | [Provider adapters](docs/PROVIDER_ADAPTERS_AND_INSTRUMENT_CATALOG_STAGE6_V1.md) · [Stage 7](docs/UNIVERSAL_STRATEGY_ORCHESTRATOR_STAGE7_V1.md) |
| PAPER risk, orders, signals | [Risk](docs/UNIVERSAL_PORTFOLIO_RISK_STAGE8_V1.md) · [Lifecycle](docs/UNIVERSAL_ORDER_POSITION_LIFECYCLE_STAGE9_V1.md) · [Signals](docs/SIGNAL_LIFECYCLE_STAGE10_V1.md) |
| Research, UI, acceptance | [Research](docs/STRATEGY_RESEARCH_LAB_STAGE11_V1.md) · [Control center](docs/TRADING_CONTROL_CENTER_STAGE12_V1.md) · [Reliability](docs/RELIABILITY_INTEGRATION_STAGE13_V1.md) |
| Independent developer SDK | [SDK and certification](docs/DEVELOPER_SDK_CERTIFICATION_STAGE14_V1.md) |
| **Product readiness and release blockers** | [Stage 15 readiness](docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md) · [A28 architecture/product audit](docs/MULTI_MARKET_TRADING_A28_FINAL_PRODUCT_AUDIT.md) |
| Security, changes and contributing | [Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Roadmap](ROADMAP.md) |

### Verification / بررسی

```bash
# Existing repository baseline checks (on a compatible development host)
bash scripts/verify.sh

# Focused installed-demo regression (with repository dev dependencies)
python -m pytest -q tests/unit/test_paper_demo_cli_v1.py
```

GitHub CI verifies the **installed preview Wheel**, public toy replay, duplicate protection, reopening durable history and disabled network/order flags in an isolated workspace. These tests do not validate real profitability or production readiness.

<a id="english"></a>
## English summary

Multi Market Trading is a public, strategy-neutral research and PAPER software project. The **legacy crypto runtime (`crypto-price-action 0.3.2`)** and the **new multi-market preview (`multi-market-trading 0.4.0rc1`)** are separate products. This repository now exposes an installable, explicitly authorized **public toy PAPER demo** (`naseri-paper-demo`) using the existing trusted-local host and SQLite journal. The demo proves the registration → explicit enable → synthetic quote replay → idempotent journal → restart/inspect → disable journey; it **does not** run the newer multi-core modules as one automatic service.

Market metadata discovery does not imply trading eligibility. Publisher signatures do not make arbitrary plugin code safe. No automatic real-market feeds, Telegram channel delivery, broker orders, strategy profitability or public launch is certified. Production and third-party executable admission remain **blocked pending independent review and authorization**.

## مشارکت، امنیت و مجوز | Security & contribution

Contributions and reproducible test evidence are welcome under [Apache-2.0](LICENSE). Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). **Never commit secrets, `.env` files, private strategy source, broker credentials, database dumps, user data or operational trading records.**

<div align="center">

[Repository](https://github.com/naseri-coder/Multi-Market-Trading) · [Issues](https://github.com/naseri-coder/Multi-Market-Trading/issues) · [GitHub Actions](https://github.com/naseri-coder/Multi-Market-Trading/actions) · [Telegram development channel](https://t.me/naseri_coder)

**Validation first · Explicit permissions · No invented PnL**

</div>