
<div align="center">

# 📈 Multi Market Trading

**Open-source multi-market strategy research · Modular trading cores · Reproducible PAPER workflows**

**پلتفرم متن‌باز پژوهش معاملات چندبازاره؛ هسته‌های مستقل، مدیریت ریسک و آزمون‌های قابل‌بازتولید، با اولویت امنیت و شواهد**

[![Public tests](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/public-test-corpus.yml/badge.svg?branch=main)](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/public-test-corpus.yml)
[![Publication safety](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/publication-safety.yml/badge.svg?branch=main)](https://github.com/naseri-coder/Multi-Market-Trading/actions/workflows/publication-safety.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-0B7285)](LICENSE)
[![Nonproduction only](https://img.shields.io/badge/release-NONPRODUCTION_ONLY-orange)](docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md)

[Overview](#overview) · [Status](#status) · [Recent work](#recent-work) · [Quickstart](#quickstart) · [Architecture](#architecture) · [Roadmap](#roadmap) · [Documentation](#documents) · [English summary](#english)

[Issues](https://github.com/naseri-coder/Multi-Market-Trading/issues) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Development channel](https://t.me/naseri_coder)

</div>

<a id="overview"></a>
## Why Multi Market Trading? | هدف پروژه

Multi Market Trading explores **auditable, strategy-neutral infrastructure** for market research, independent trading cores, explicit operator controls and reproducible PAPER evaluation. It separates strategy decisions from data provenance, market eligibility, risk policy, execution permissions and signal publication. The goal is an open engineering foundation with clear evidence — **not a claim of a profitable trading product**.

این مخزن مسیرهای تحقیق، داده، هسته، انتخاب صرافی/نماد/تایم‌فریم، مدیریت ریسک، چرخه معاملات PAPER و گزارش را به‌صورت تفکیک‌شده توسعه می‌دهد. «وجود کد»، «عبور از تست» و «آمادگی محصول واقعی» سه وضعیت متفاوت هستند.

> [!IMPORTANT]
> **Not authorized for public live trading or real signal delivery.** Installed demonstrations use approved **synthetic/offline PAPER** inputs. Passing CI, signing a package or executing harmless test fixtures does **not** prove profitability, authenticated prices, safe execution of hostile plugins, live exchange eligibility or deployment readiness.

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
| Universal Core API / risk / lifecycle / research | Stages 3–16 | قراردادها و اجزای PAPER/آزمایشی، **نه یک سرویس LIVE یکپارچه** | کتابخانه‌ها و آزمون‌های مستقل |

**Release gate: `PRODUCT_NOT_READY_FOR_PUBLIC_OR_LIVE_RELEASE`.** Autonomous production scanning, real Telegram publication, broker orders, public untrusted-code execution and commercial deployment are not approved. [Readiness report](docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md) · [A28 audit](docs/MULTI_MARKET_TRADING_A28_FINAL_PRODUCT_AUDIT.md).


<a id="recent-work"></a>
## Recent engineering | تازه‌ترین پیشرفت‌ها

**Evidence cutoff: 2026-10-15.** This section describes work **merged into `main`**, independently bounded research fixtures, and remaining blockers. A draft PR is not treated as an available release feature.

| Track | What is implemented or demonstrated | What it does **not** establish |
| --- | --- | --- |
| **Modular core and control plane** | Universal Core API, separate engine/binding settings for provider, symbol, timeframe and budget, risk and signal lifecycle contracts | No general live trading authorization |
| **Brooks Price Action** | Public reference core and operator-facing management/PAPER research paths | No verified positive edge or automatic live activation |
| **Installed PAPER preview** | `0.4.0rc1` synthetic toy-core demo, explicit enable/disable, SQLite replay journal, deduplication and restart-safe inspection | No broker fills, authenticated market feeds or Telegram messages |
| **Panel → PAPER / Stage 17 supervisor** | Opt-in offline panel-to-risk/lifecycle handoff and recoverable queued replay | Not a continuously running multi-market trading service; cross-ledger atomicity remains unresolved |
| **DATA-A1** | Real on-disk **CSV/Parquet** bytes with explicit operator authorization, SHA-256 pin, bounded quality report and causal typed replay | External dataset authenticity and Point-in-Time suitability require separate audits |
| **RUNTIME / CERT** | Inert framed Core API messages and **16 real benign fixture roundtrips** across Python, JavaScript, TypeScript and WebAssembly in disposable CI tests | Not arbitrary uploaded strategies, language feature parity or independently certified hostile-code isolation |
| **MT-A1** | MQ4/MQ5/opaque EX5 hash-pinned static file acceptance and timeframe-claim checks | No terminal connection, MQL compilation, EX5 inspection beyond byte identity or order execution |
| **PINE-A1** | Strict Pine v5/v6 **confirmed-bar SMA-cross indicator subset** with offline trace comparison | Not a universal Pine translator, TradingView integration or trading/PnL equivalence |
| **NATIVE-A1** | Bounded, static PE/ELF header/architecture preflight | No loading/running DLL, EXE or SO files; not malware certification |
| **Security / supply chain** | Immutable input research, bounded Docker fixture tests, real CycloneDX/Grype evidence and candidate byte-level reviews through **CERT-A18** | Not a release-ready image, vulnerability remediation or permission to open Worker dispatch |

References: [DATA-A1](docs/MMT_DATA_A1_CSV_PARQUET_REPLAY.md) · [CERT-A5 real benign workers](docs/MMT_CERT_A5_REAL_BENIGN_WORKER_REPLAY.md) · [MetaTrader static intake](docs/MMT_MT_A1_OFFLINE_ARTIFACT_PREFLIGHT.md) · [Pine subset](docs/MMT_PINE_A1_SMA_CROSS_SEMANTIC_PARITY.md) · [Native static intake](docs/MMT_NATIVE_A1_INERT_PE_ELF_PREFLIGHT.md).

### Security and release boundaries | مرزهای امنیتی

> [!WARNING]
> **RUNTIME-A6 keeps general Python/JS/TS/WASM Worker execution unconditionally DENIED.** CI runs only explicit, reviewed harmless fixtures. Do not treat those tests as permission to execute unknown third-party code, or weaken the production fence.

- On **2026-10-14**, the original experimental Worker image had **18 Critical + 181 High** Grype matches. These **199 baseline findings remain open for review**. Changes in scanner counts for lean images are **not automatically fixed CVEs**. [Baseline triage](docs/MMT_CERT_A14_CRITICAL_HIGH_TRIAGE.md) · [Lean-image evidence](docs/MMT_CERT_A15_LEAN_IMAGE_COMPARISON.md).
- **CERT-A18** checks narrowly scoped absence of specified Debian build-only package paths in a separate benign candidate; it does **not** prove all vulnerable code removed or advisories resolved. [CERT-A18 limitations](docs/MMT_CERT_A18_BUILD_ONLY_ABSENCE_PROOF.md).
- **CERT-A19** remains a [draft PR #275](https://github.com/naseri-coder/Multi-Market-Trading/pull/275) at this cutoff. Research and verified byte custody are **not** a merged upstream patch or CVE closure.
- Independent, designated-host **rootless Docker/gVisor and adversarial isolation acceptance** remain pending. GitHub-hosted rootful Docker probes are useful bounded evidence, **not** equivalent certification.
- Never put production credentials, private strategy code, trading logs, user databases, broker API keys or operational Telegram tokens into public tests or issues.

See [RUNTIME-A6 deny contract](docs/MMT_RUNTIME_A6_DISPATCH_FENCE.md), [independent host requirements](docs/MMT_CERT_A6_DISPOSABLE_HOST_ACCEPTANCE.md) and [security reporting policy](SECURITY.md).

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

<a id="panel-paper"></a>
## مسیر یکپارچه پنل تا PAPER | Stage 16

**New — opt-in offline handoff.** The Stage-12 selected binding now controls a
real **Stage-5 → Stage-7 → Stage-8/9 → Stage-10** demonstration with genuine
PAPER risk/order records and a NO-SEND signal journal, subject to independent
operator acknowledgment. This is not autonomous Telegram trading or a real feed.

The selected **symbol, timeframe and budget** affect the actual offline
evaluation and risk acceptance. Analysis, dry-run signals and PAPER remain
independently requested modes. Stage-8 allocation must agree exactly with
Stage-12 configuration, otherwise execution fails closed.

Run the independent installed-wheel synthetic lifecycle in a **new, private
state directory** on a development machine (Python 3.12). It uses a reviewed
example core, fictitious symbol and price bars; the same command must never
be pointed at an existing production database:

```bash
MMT_NONPRODUCTION=1 python -m naseri_markets.panel_paper_synthetic_demo_v1 \
  --state-dir "$HOME/mmt-stage16-unique-test" \
  --symbol XYZUSD --timeframe 15m --ack-synthetic-offline
```

The test records a modeled PAPER entry/exit, verifies the persisted result
after re-opening SQLite, and audits the NO-SEND signal and order ledgers.
Supported sample periods: `5m`, `15m`, `1h`. All reported PnL is synthetic.

**Still not implemented:** a continuously running authenticated market
scanner, atomic cross-database coordination, actual Telegram delivery,
LIVE broker execution, public third-party plugin sandbox certification,
or a verified profitable strategy. [Stage 16 architecture, test and recovery
limits](docs/OFFLINE_PANEL_TO_PAPER_STAGE16_V1.md).

<a id="offline-supervisor"></a>
## صف اجرای قابل‌بازیابی | Stage 17 Offline Runtime Supervisor

مرحله ۱۷ یک **صف زمان‌بندی‌شده و پایدار SQLite** به مسیر Stage 16 اضافه می‌کند. اپراتور با داده‌های کندلی **SYNTHETIC/REPLAY** از پیش تهیه‌شده، Binding و نسخه تنظیمات را انتخاب می‌کند؛ اجرای محدود و صریح، همان موتور Stage 16 را صدا می‌زند. این **یک سرویس یا Poller دائمی نیست**؛ در نصب، ری‌استارت یا کلیک پنل چیزی به‌صورت خودکار شروع نمی‌شود.

- **Scheduling:** کارهای `PENDING` فقط پس از زمان تعیین‌شده و با تأیید صریح اجرا می‌شوند. کلید محتوایی باعث می‌شود همان Replay دوباره به صف اضافه یا دوباره اجرا نشود.
- **Concurrency:** قفل تراکنشی `BEGIN IMMEDIATE`، رسید claim تصادفی و کنترل نسخه پنل مانع دریافت هم‌زمان همان کار توسط دو اجراکننده می‌شوند.
- **Recovery:** کار نیمه‌تمام `CLAIMED` بعد از Crash **هرگز کورکورانه تکرار نمی‌شود**؛ اپراتور باید سایر اجراکنندگان را متوقف، دفترهای PAPER/سیگنال را جداگانه تطبیق و مورد مبهم را قرنطینه کند.
- **Health:** فرمان `runtime_supervisor_health_v1` وضعیت را **فقط‌خواندنی** نشان می‌دهد. فعال‌سازی LIVE، ارسال واقعی Telegram و معامله بروکر همیشه غیرفعال می‌مانند.

آزمون نصب تمیز با یک هسته نمونه عمومی و خروجی مصنوعی:

```bash
# A unique new destination under an existing owner-private (0700) directory
export MMT_NONPRODUCTION=1
python -m naseri_markets.supervisor_synthetic_smoke_v1 \
  --state-dir "$HOME/mmt-private/stage17-demo" --ack-synthetic-offline
python -m naseri_markets.runtime_supervisor_health_v1 \
  --runtime-db "$HOME/mmt-private/stage17-demo/supervisor.sqlite" \
  --ack-nonproduction-readonly
```

این آزمون Stage 12 → Stage 16 → Stage 10 NO-SEND را بعد از بسته‌شدن و بازکردن مجدد دیتابیس بررسی می‌کند. مسیر PAPER مرحله ۸/۹ جداگانه در تست‌های مخزن کامل ارزیابی می‌شود. **سه دفتر آزمایشی یک تراکنش واحد نیستند و آماده انتشار عمومی یا LIVE نیستند.**

[**قرارداد، محدودیت‌ها و دستورهای Stage 17**](docs/OFFLINE_RUNTIME_SUPERVISOR_STAGE17_V1.md) · [Stage 16](docs/OFFLINE_PANEL_TO_PAPER_STAGE16_V1.md)

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
| Trading Control Center | پنل توسعه‌ای چند هسته/نماد/تایم‌فریم | با اتصال صریح آفلاین Stage 16؛ بدون اجرای خودکار معاملات |
| Reliability, SDK, signatures, release gates | ممیزی و آزمون ساختاری | بدون تأیید خصمانه gVisor یا مجوز Marketplace |
| **Public toy PAPER user journey** | **نصب Wheel → ثبت → Replay → ری‌استارت → inspect** | فقط نمونه عمومی trusted، بدون Telegram/سفارش |

**Brooks Price Action** هسته مرجع عمومی پروژه است؛ فعال‌سازی خودکار آن در محصول جدید از این نمونه نتیجه نمی‌شود. **NY First-Reversal** اختصاصی و *owner-only* است: هیچ سورس، بسته یا مجوز اجرای عمومی آن در مخزن قرار نمی‌گیرد.


<a id="roadmap"></a>
## Roadmap | برنامه آینده

**Evidence-gated priorities — not dates or release promises.** Features below are **planned work**, not deployed or certified capabilities.

| Priority | Engineering direction | Required acceptance evidence |
| --- | --- | --- |
| **P0: security closure** | Triage the 199 original Critical/High matches, verify authenticated upstream fixes or individually justified non-applicability, reconcile package provenance and repeat SBOM/Grype reviews | Reproducible case-by-case decisions; **no silent A6 unlock** |
| **P0: independent isolation** | Test rootless Docker/gVisor and hostile-code boundaries on a separately approved disposable nonproduction host | Independent adversarial evidence and fail-closed review before any future permission proposal |
| **P1: trustworthy data** | Improve source- and time-aware historical feed provenance, candle integrity, latency/funding metadata and market eligibility checks | Source-specific reports, negative tests and no look-ahead assumptions |
| **P1: core interoperability** | Strengthen versioned core contracts, safe language/artifact intake and deterministic replay parity | Narrow independently checked semantic oracles; no unsupported universal conversion claims |
| **P1: integrated PAPER product** | Combine per-core settings, approval workflows, risk controls, observability and restart-safe reconciliation | Isolated, repeatable, nonproduction end-to-end evidence, including cross-database consistency/recovery |
| **P2: open-source ecosystem** | Improve SDK examples, contributor onboarding, issue triage, CI tests, security documentation and public-core integration | Reviewable, maintainable changes with clear threat-model and compatibility boundaries |
| **Conditional future** | Research compliant real-market paper/shadow feeds and, *only if all gates pass*, optional limited broker/Telegram pilots | Verified provider permissions, independent security review, operational readiness, kill switches and **explicit authorization**; no live launch scheduled |

### Contributing and protected scope

Useful public contributions include **reproducible bug reports, deterministic PAPER fixtures, no-look-ahead tests, sandbox and supply-chain audits, documentation, and SDK examples**. Check [CONTRIBUTING.md](CONTRIBUTING.md) and open a narrowly scoped [issue](https://github.com/naseri-coder/Multi-Market-Trading/issues).

**Brooks Price Action** is the public reference core; **`NY First-Reversal` is private and owner-only**. Its source, installation package and execution authorization are deliberately outside this repository. Do not propose adding private strategies or production secrets to public examples.

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
| **Stage 16 — explicit panel-to-PAPER integration** | [Offline handoff and installed synthetic E2E](docs/OFFLINE_PANEL_TO_PAPER_STAGE16_V1.md) |
| **Product readiness and release blockers** | [Stage 15 readiness](docs/PRODUCT_READINESS_AND_RELEASE_GATES_STAGE15_V1.md) · [A28 architecture/product audit](docs/MULTI_MARKET_TRADING_A28_FINAL_PRODUCT_AUDIT.md) |
| Recent data & format contracts | [DATA-A1](docs/MMT_DATA_A1_CSV_PARQUET_REPLAY.md) · [DATA → RUNTIME](docs/MMT_DATA_RUNTIME_PAPER_WIRE_A1.md) · [Cross-format review](docs/MMT_CERT_A1_CROSS_FORMAT_OFFLINE_REVIEW.md) |
| Runtime & security evidence | [Worker deny](docs/MMT_RUNTIME_A6_DISPATCH_FENCE.md) · [Benign multi-language worker](docs/MMT_CERT_A5_REAL_BENIGN_WORKER_REPLAY.md) · [CERT-A14](docs/MMT_CERT_A14_CRITICAL_HIGH_TRIAGE.md) · [CERT-A18](docs/MMT_CERT_A18_BUILD_ONLY_ABSENCE_PROOF.md) |
| Third-party file preflight | [MQ4/MQ5/EX5](docs/MMT_MT_A1_OFFLINE_ARTIFACT_PREFLIGHT.md) · [Pine subset](docs/MMT_PINE_A1_SMA_CROSS_SEMANTIC_PARITY.md) · [PE/ELF](docs/MMT_NATIVE_A1_INERT_PE_ELF_PREFLIGHT.md) |
| Security, changes and contributing | [Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [Earlier roadmap](ROADMAP.md) · [Current roadmap](#roadmap) |

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

Multi Market Trading is an **Apache-2.0 open-source, Python-based** software project for strategy-neutral multi-market research, per-core operator control, testable risk/lifecycle contracts and strictly isolated PAPER experimentation.

**Available for development:** the `0.4.0rc1` nonproduction preview and synthetic installed PAPER demo; local CSV/Parquet intake and causal replay; bounded Stage 16/17 offline handoff; documented Brooks Price Action core; narrow MetaTrader, Pine and PE/ELF artifact research; and reviewed four-language **benign** Worker CI experiments. The legacy `crypto-price-action 0.3.2` runtime remains a separate software line.

**Not production-ready:** real-money trading, unattended exchange scanning, broker fills, Telegram channel delivery, arbitrary public plugin execution, general code translation, verified trading edge and independently certified malicious-code isolation. Experimental container findings remain open. Untrusted-code admission is **fail-closed**.

The [roadmap](#roadmap) prioritizes proven data provenance, independent security evidence, trustworthy PAPER tests and developer-friendly public APIs before any conditional real-world pilot.

## مشارکت، امنیت و مجوز | Security & contribution

Contributions and reproducible test evidence are welcome under [Apache-2.0](LICENSE). Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). **Never commit secrets, `.env` files, private strategy source, broker credentials, database dumps, user data or operational trading records.**

<div align="center">

[Repository](https://github.com/naseri-coder/Multi-Market-Trading) · [Issues](https://github.com/naseri-coder/Multi-Market-Trading/issues) · [GitHub Actions](https://github.com/naseri-coder/Multi-Market-Trading/actions) · [Telegram development channel](https://t.me/naseri_coder)

**Validation first · Explicit permissions · No invented PnL**

</div>