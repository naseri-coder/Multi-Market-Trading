> Historical reference only; not current release proof.
> Original source: `AUDIT_V5.md`; SHA256: `ffc0aafd0e3f6f60ae6293bfbaaf455c56ee8660e862e93065e1b88e06bed450`.

# AUDIT_V5.md — ممیزی و تغییرات هسته Brooks V5

- وضعیت سند: در حال تکمیل؛ قبل از هر تغییر اجرایی ایجاد شد.
- پروژه: `<historical-project-root>`
- زمان شروع آدیت: 2026-09-12 (Asia/Tehran)
- مرجع الزامی: `BOOKS_NOTES_V5.md` با SHA-256 برابر `6e1136f9ca23245ff46149f3dd45b301026449655f5b06fe24d03631049c088c`
- روش ارجاع: هر یافته و تغییر باید دست‌کم یک شناسهٔ قانون از فایل مرجع داشته باشد.

## صفر ایمنی

- پروژه Git ندارد (`NO_GIT`)؛ بنابراین tag/commit پیش از تغییر ممکن نبود.
- بک‌آپ کامل پیش از خواندن/تغییر کد اجرایی ساخته شد:
  `/opt/crypto-signal-backups/brooks_v5_prechange_20260912T070648Z.tar.gz`
- SHA-256 بک‌آپ: `7cf34c05c2480fe596163ec94d2e96be9615a4f4abd966ab1005636c02e9e934`
- تعداد ورودی‌های آرشیو: 568.
- دامنهٔ بک‌آپ: کل `app/modules/` و `app/core/config.py`.
- هیچ تغییر مخرب دیتابیس مجاز نیست؛ کوئری‌های خط مبنا فقط READ ONLY هستند.

## خط مبنای پروداکشن پیش از تغییر

زمان برداشت UTC: `2026-09-12 07:31:10.548088+00`.

| معیار | مقدار |
|---|---:|
| سیگنال بسته‌شده | 281 |
| سیگنال یکتای دارای STOP_HIT | 193 (68.68%) |
| سیگنال یکتای دارای حداقل یک TARGET_HIT | 132 (46.98%) |
| دارای تارگت جزئی و سپس استاپ | 44 |
| رخداد/ردیف تارگتِ HIT | 220 |
| میانگین فاصلهٔ استاپ از ورود | 96.0578499183 واحد قیمت؛ 0.524961% |
| میانگین فاصلهٔ تارگت HIT از ورود | 108.8094835892 واحد قیمت؛ 0.694967% |

| تارگت ۱ | 132 HIT؛ میانگین 80.4506317417 واحد؛ 0.498445% |
| تارگت ۲ | 88 HIT؛ میانگین 151.3477613605 واحد؛ 0.989751% |

تعریف نرخ‌ها: مخرج نرخ‌های سیگنال، فقط 281 ردیف `signals.status='CLOSED'` است. یک سیگنال می‌تواند پس از تارگت جزئی استاپ بخورد؛ بنابراین نرخ STOP_HIT و TARGET_HIT مکمل یکدیگر نیستند. فاصلهٔ استاپ با `abs(entry_price-stop_loss)` از مقدار ذخیره‌شدهٔ سیگنال و فاصلهٔ تارگت با `abs(target_price-entry_price)` از تارگت‌های واقعاً HIT محاسبه شد. این خط مبنا کیفیت علّی نسخهٔ قبلی را اثبات نمی‌کند و فقط معیار مقایسهٔ پس از استقرار است.

## فهرست ساختار و دامنهٔ خوانده‌شده

ساختار کامل ماژول‌های خواسته‌شده با پیمایش بازگشتی ثبت شد. آدیت از `app/modules/brooks_runtime/coordinator.py` آغاز شده و سپس کل فایل‌های Python در `brooks_core/`، `signal_intelligence/`، `risk_engine/`، `market_data/`، `operations/` و `app/core/config.py` خوانده می‌شوند. هر dependency مؤثر خارج از این فهرست نیز از مسیر call graph دنبال خواهد شد.

## یافته‌های مستند پیش از تغییر کد

### A-001 — قرارداد کانتکست fail-open است (بحرانی)

- محل: app/modules/brooks_core/books_full_engine.py:134-138, 181-199, 202-264؛ توابع evaluate، _choose_candidate و _context_contract_status.
- رفتار فعلی: هر candidate که وضعیتش دقیقاً REJECT نباشد eligible است. نیازهای REVERSAL_MATURITY، CLIMAX_AT_EXTREME، LATE_TREND_TWO_SIDED و TREND_EXTREME_OR_RANGE_EXTREME عمداً DEFERRED برمی‌گردند، اما DEFERRED وارد انتخاب و نهایتاً معامله می‌شود.
- پیامد: MTR، کلایمکس، ودج، final flag و double-top/bottom بازگشتی می‌توانند بدون اثبات بلوغ/اکسترمم/ضعف روند غالب صادر شوند.
- نقض: TREND-001، AI-002، MTR-001..003، WDG-001..003، CLX-001..002، FF-001..002 و DTDB-001.
- اصلاح لازم: فقط PASS قابل معامله؛ DEFERRED باید observation یا رد قطعی باشد تا dimension واقعی پیاده شود.

### A-002 — MTR چهارشرطی کامل نیست (بحرانی)

- محل: app/modules/brooks_core/books_full_patterns.py:608-701، تابع detect_major_trend_reversal.
- رفتار فعلی: دو سوی MTR فقط شکست close از یک swing مخالف، برگشت به اکسترمم و یک reversal bar را می‌سنجند.
- کمبودها: وجود روند قبلی قوی صریحاً gate نشده؛ شکست خط روند معتبر با anchorهای کافی و ترجیحاً عبور MA اثبات نشده؛ major_trend_line_anchor_spacing_bars تعریف شده ولی استفاده نشده؛ تست اکسترمم از «بازگشت دومِ کافی» جدا نشده است.
- نقض: MTR-001 و MTR-002.
- تصمیم: تا پیاده‌سازی چهار witness مستقل، MTR نباید tradeable باشد.

### A-003 — قدرت روند و Always-In بیش از حد به پروکسی ثابت وابسته‌اند

- محل: app/modules/brooks_core/context_classifier.py:61-74, 175-221, 253-437 و advanced_context.py:26-123.
- رفتار فعلی: strong bar با body fraction و close-location ثابت، Always-In عمدتاً با streak دو bar، و spike/channel با شمارش سادهٔ رنگ/حرکت تشخیص داده می‌شود.
- نکتهٔ مثبت: ساختار HH/HL یا LH/LL، overlap، displacement، EMA-side و follow-through ترکیب شده‌اند و داده فقط closed-candle است.
- کمبود: فاز SPIKE → CHANNEL → RANGE stateful نیست؛ شکست کل رنج از شکست یک swing کوچک جدا نشده؛ failureهای متوالی و urgency به‌صورت history state نگه‌داری نمی‌شوند.
- نقض: PHASE-001..005، TREND-001..002 و AI-001..003.

### A-004 — تفسیر پترن در بعضی خانواده‌ها کانتکستی است، اما سراسری نیست

- محل صحیح: books_full_patterns.py:420-479 دوقلوها را در bull/bear trend به bull/bear flag ادامه‌دهنده تبدیل می‌کند؛ :535-607 ودج با‌روند را H3/L3 flag می‌گیرد؛ pattern_expansion.py:833-868 micro-wedge خلاف tight Always-In را suppress می‌کند.
- محل ناقص: pattern_expansion.py:349-402, 420-463 و books_full_patterns.py:480-534, 703-823 reversal candidate می‌سازند اما بلوغ/اکسترمم در engine فقط DEFERRED است.
- نقض: HL-004..005، WDG-002..003، EXP-001، DTDB-001 و FF-002.

### A-005 — بریک‌اوت/تست بریک‌اوت در همهٔ مسیرها follow-through یکسان ندارد

- محل خوب: books_full_patterns.py:154-352 برای fresh breakout دو strong bar beyond level می‌خواهد و failed breakout قدرت شکست/بازگشت را مقایسه می‌کند.
- محل ناقص: pattern_expansion.py:231-262, 564-611 شکست ii/iii/ioi و triangle را با یک bar قوی نهایی candidate می‌کند؛ follow-through بعدی هنوز وجود ندارد.
- پول‌بک بریک‌اوت books_full_patterns.py:204-285 حفظ سطح و trigger مجدد را می‌سنجد، ولی کیفیت test و عمق نسبت به volatility/ساختار را نمی‌سنجد.
- نقض: BO-001..003 و TTR-002.

### A-006 — استاپ اولیه بخشی از تصمیم‌درخت را دارد، اما ساختاری کامل نیست

- محل: books_full_engine.py:403-469، books_policy.py:40-96 و risk_engine/calculator.py:13-99.
- نکات صحیح: range کندل با average recent range مقایسه می‌شود؛ کندل بزرگ money-management stop محدودتر و کندل کوچک حداقل استاندارد می‌گیرد؛ RiskCalculator دیگر صرفاً تنگی stop را امتیاز نمی‌دهد.
- کمبود: برای کندل عادی stop فقط آن سوی signal bar است، نه پشت pullback/swing invalidation؛ buffer آن فقط یک tick ثابت symbol است؛ entry buffer درصد قیمت است؛ doji/weak signal و room-to-stop سطحی gate مستقل ندارند.
- نقض: STOP-001..007 و SBAR-001..005.
- اصلاح لازم: stop candidateهای signal، swing/pullback و volatility floor ساخته و بر اساس setup family/context انتخاب شوند؛ large-bar cap فقط با position-sizing caveat.

### A-007 — trailing stop موجود است، ولی breakeven trigger ثابت است

- محل: app/modules/operations/lifecycle.py:280-380, 600-625.
- وضعیت: _structural_trailing_stop بعد از entry با swingهای causal، HH/HL یا LH/LL جدید را می‌سنجد و stop را فقط در جهت کاهش ریسک حرکت می‌دهد؛ این بخش با TRAIL-002..003 هم‌راستاست.
- کمبود: _halfway_to_first_target_reached انتقال breakeven را دقیقاً در نیمهٔ TP1 فعال می‌کند؛ چون TP1 ثابت 1R است عملاً 0.5R و مستقل از price action است.
- نقض/ریسک: TRAIL-001؛ باید favorable excursion همراه با follow-through/ساختار یا threshold volatility-versioned باشد.

### A-008 — تارگت ساختاری محاسبه می‌شود اما مسیر اجرا آن را دور می‌زند (بحرانی)

- محل محاسبهٔ موجود: advanced_context.py:77-123 و market_context.py:208-236، measured-move magnet.
- محل دورزدن: books_full_engine.py:163-180, 451-468 تارگت را فقط entry ± risk × target_r_multiples می‌سازد؛ policy نیز books_policy.py تارگت‌های (1,2) دارد.
- اثر: ساختار چارت در تصمیم نهایی target نقشی ندارد و Trader’s Equation روی target مصنوعی محاسبه می‌شود.
- نقض: TGT-001..003 و به‌تبع TE-001..003.
- اصلاح لازم: اول targetهای swing opposite/range boundary/measured move/magnet؛ R فقط ابزار sanity/fallback مستند، نه منبع اصلی.

### A-009 — veto باربوایر/tight range مجزا نیست

- محل: context_classifier.py:158-174, 344-365 tight range را تشخیص می‌دهد، اما books_full_engine.py:132-180 veto early-return ندارد.
- مسیرهای detect_candle_pattern_breakouts و detect_triangle_breakout می‌توانند یک breakout bar داخل/پس از فشردگی را قبل از follow-through کافی candidate کنند.
- نقض: TTR-001..002 و BO-001.
- اصلاح لازم: absolute veto برای stop-entry breakout از barbwire؛ خروج فقط پس از breakout واضح + follow-through و سپس test/resumption.

### A-010 — معادلهٔ معامله‌گر محاسبه می‌شود ولی hard gate نیست (بحرانی)

- محل محاسبه: signal_intelligence/probability.py:253-292 از Wilson lower bound، risk و reward استفاده می‌کند.
- محل نقض: signal_gate/service.py:19-66 مقدار trader_equation_favorable را می‌خواند اما به failures اضافه نمی‌کند؛ نام policy نیز TE_ADVISORY است. signal_intelligence/service.py:37-55 نیز favorable/minimum probability را شرط approval نمی‌کند.
- نتیجه: معامله‌ای با EV محافظه‌کارانهٔ منفی می‌تواند از gate عبور کند.
- نقض: TE-001..003.
- اصلاح لازم: TRADER_EQUATION_UNFAVORABLE hard failure و حداقل احتمال لازم باید برای هر geometry محاسبه و enforce شود.

### A-011 — scoring نرم جای بعضی vetoهای منبع را گرفته است

- محل: brooks_core/higher_probability.py:24-65 خلاف روند را فقط LOWER می‌کند؛ chooser باز هم LOW‌تر را در نبود گزینهٔ بهتر انتخاب می‌کند. evidence_weighting.py:283-330 conflict بازگشتیِ خلاف trend/Always-In را MODERATE می‌گیرد.
- نقض: AI-002، TREND-002، MTR-003 و TTR-002.
- اصلاح لازم: countertrend فقط با exception package کامل (break + test + second signal + room/TE) مجاز؛ وگرنه early-return.

### A-012 — آستانه‌های ثابت و تصمیم‌های مهندسی

آستانه‌های کتاب‌نیامده و versioned شامل swing L2/R2، windowهای 40/20/10/24/6، strong-body=0.60، close-extreme=0.25، overlapهای 0.50/0.60/0.70، displacement=0.12/0.18، efficiency=0.04، EMA-side=0.55، range zone=0.25، double tolerance=0.12، climax=1.50× median، final-flag span=0.35، micro-double=0.25× median، risk gate=75 و quality gates=60/60/75 است. همچنین signal_intelligence/regime.py:56-91 از volatility ثابت 0.02/0.005 و trend change ثابت 0.01 استفاده می‌کند. این آخری با Brooks context canonical یکسان نیست و فقط لایهٔ ثانویه است.

- تصمیم: thresholdهای هندسی باید همگی در configuration_version و نسبت به ATR/median range/range width باشند. اعداد درصد قیمتِ مطلق در regime analyzer از مسیر تصمیم حذف یا فقط telemetry می‌شوند.
- ارجاع: PHASE-005، STOP-005..007 و بخش «تصمیم‌های مهندسی» مرجع.

### A-013 — پوشش تست سناریویی کامل نیست

- تست‌های واحد hand-crafted برای context، H/L count، stop geometry، trailing و چند detector وجود دارد.
- برای تمام detectorها تست 200–300 سناریوی numpy-random شامل trend/range/noise/volatility-scale وجود ندارد؛ بنابراین نرخ activation، dead logic و over-triggering اندازه‌گیری نشده است.
- نقض الزام آدیت شماره 10 و invariant تست مرجع.
- اصلاح لازم: harness ثابت-seed با حداقل 300 سناریو، گزارش activation family/regime/exception و assertions scale-invariance.

### A-014 — دادهٔ بازار futures نسبت به adapters دیگر fail-closed کامل نیست

- محل: market_data/binance_futures.py:44-101.
- برخلاف Spot/Bybit، خطای HTTP/parse به MarketDataResponseError normalize نمی‌شود و snapshot.assert_fresh فراخوانی نشده است.
- اثر: این موضوع قانون Brooks را نقض نمی‌کند، ولی کیفیت زنجیره و تشخیص closed/fresh context را تهدید می‌کند.
- ارجاع اجرایی: invariant دادهٔ causal/closed در مرجع.

### A-015 — نکات سالم و بدون تغییر لازم

- market_data/entities.py ترتیب، OHLC validity، timezone و بسته‌بودن candle را enforce می‌کند.
- lifecycle.py ambiguity هم‌زمان stop/target را fail-closed ثبت می‌کند و trailing causal دارد.
- operations/telegram_updates.py، payment_settlement.py و vip_entitlements.py منطق تحلیل Brooks ندارند و در این بازسازی تغییر نمی‌کنند.
- context_classifier.py و causal_structure.py از swingهای non-repainting با right confirmation استفاده می‌کنند؛ پارامتر آن تصمیم مهندسی است، نه عدد کتاب.
- دوقلوها و wedge flags در چند مسیر به‌درستی بین continuation و reversal تفکیک شده‌اند؛ مشکل اصلی bypass قرارداد کانتکست است.

## Changelog V5

### C-001 — Trader's Equation hard gate

- فایل‌ها: app/modules/signal_gate/service.py و app/modules/signal_intelligence/service.py.
- تغییر: calibrated probability اکنون باید دست‌کم break-even probability همان geometry باشد و expected value محافظه‌کارانه (Wilson lower bound) مثبت باشد؛ در غیر این صورت approval قبل از publication رد می‌شود.
- شناسه‌ها: TE-001..003.
- compile: python3 -m py_compile روی هر دو فایل؛ exit code 0.
- عدد جدید کتابی اضافه نشد؛ حداقل احتمال پویا و برابر R/(R+Reward) است، نه threshold ثابت.



### C-002 — قرارداد کانتکست، فاز و بلوغ بازگشت

- فایل‌ها: books_full_engine.py، books_full_patterns.py، context_classifier.py،
  advanced_context.py، market_context.py و books_full_policy.py.
- تغییر: فقط وضعیت PASS قابل معامله است؛ DEFERRED دیگر به eligible راه ندارد.
  Always-In هم‌جهت برای continuation اجباری شد و شکست تازه بدون پاک‌کردن ساختار
  قبلی breakout محسوب نمی‌شود.
- MTR اکنون هر چهار شاهد MTR-001..003 را می‌خواهد: روند HH/HL یا LH/LL، شکست
  خط روند و EMA، تست اکسترمم قدیم، و سیگنال دوم با جابه‌جایی کافی.
- breakout pullback باید واقعاً یک تا پنج bar پول‌بک داشته باشد. climax و
  final flag شاهد اکسترمم/late-trend را در metadata حمل می‌کنند.
- شناسه‌ها: PHASE-001..005، AI-001..003، MTR-001..003، CLX-001،
  FF-001..002، BO-001..003.
- تصمیم‌های مهندسی versioned: MTR second reversal = 0.50× median range،
  retest window = 12 bar، final-flag prior span = 6× typical bar.
- compile همهٔ فایل‌ها: exit code 0.


### C-003 — استاپ و تارگت ساختاری

- فایل‌ها: books_full_engine.py و books_policy.py.
- entry یک tick بیرون signal bar است؛ buffer استاپ برابر max(tick،
  0.10× recent average range) و invalidation پشت کل setup/pullback و سطوح
  range/old-extreme قرار می‌گیرد.
- large signal bar از money-management cap و small signal bar از recent-range
  floor استفاده می‌کند؛ تنگی استاپ امتیاز مستقل ندارد.
- target فقط از opposite range boundary، causal swing، active measured move،
  breakout-range projection یا recent-structure measured move می‌آید. fixed-R
  fallback حذف شد؛ نبودن room ساختاری به NO_SIGNAL می‌انجامد.
- شناسه‌ها: STOP-001..007 و TGT-001..003.
- تصمیم‌های مهندسی versioned: buffer=0.10× average range، حداقل room=
  0.50× average range، حداکثر دو target.
- compile: exit code 0.

### C-004 — veto مطلق باربوایر و trailing

- فایل‌ها: books_full_engine.py و operations/lifecycle.py.
- breakout stop-entry در شش bar با overlap بالا و bodyهای کوچک، قبل از scoring
  veto می‌شود. عدد 6 تصمیم مهندسی versioned است.
- breakeven دیگر در نیمهٔ TP1 ثابت فعال نمی‌شود؛ پس از HIT شدن نخستین target
  ساختاری فعال می‌شود و سپس trailing فقط پشت swing causal جدید پیش می‌رود.
- شناسه‌ها: TTR-001..002 و TRAIL-001..003؛ compile exit code 0.


### C-005 — مرز causal دادهٔ Futures

- فایل: market_data/binance_futures.py.
- از یک captured_at واحد و endTime استفاده می‌شود؛ bar باز حذف، خطای transport/
  parse normalize و freshness قبل از تحویل snapshot کنترل می‌شود.
- این تغییر قاعدهٔ معاملاتی جدید نیست؛ invariant دادهٔ بسته و causal است.
- compile: exit code 0.

### C-006 — تست‌های اجراشده تا این مرحله

- subset هسته/کانتکست/استاپ/trailing/Futures: 42 passed، 0 failed.
- تست معادلهٔ معامله‌گر و minimum probability: 2 passed، 0 failed.
- regression اصلاح‌شدهٔ context در crypto MTF: 19 passed، 0 failed.
- کل suite: 867 passed، 21 skipped، 6 failed. دو failure مربوط به regression
  context بود و با base-window قبل از breakout-lookback اصلاح شد؛ چهار failure
  باقیمانده مستقل از V5 هستند: دو subprocess import بدون PYTHONPATH و دو تست
  قدیمی ApplicationLifecycle که آرگومان settings را نمی‌دهند.
- هشدارها: 47 warning؛ عمدتاً deprecationهای matplotlib/telegram.
- حذف تابع legacy _halfway_to_first_target_reached پس از بررسی call-site:
  تنها caller مسیر همان lifecycle بود که به _breakeven_ready تغییر کرد؛
  grep جاری فقط نسخه‌های backup و متن آدیت را نشان می‌دهد.


### C-007 — اعتبارسنجی تصادفی V5

- اسکریپت: scripts/brooks_v5_synthetic_validation.py؛ seed ثابت 912000.
- 360 چارت OHLCV تصادفی/ساختاری: 60 روند صعودی، 60 نزولی، 60 رنج،
  60 نویزی، 60 MTR سقف و 60 MTR کف؛ اندازهٔ bar با lognormal تغییر می‌کند.
- raw detector روی 343/360 = 95.28% حداقل یک observation/candidate داشت؛ این
  نرخ تجمیع همهٔ detectorهاست، نه سیگنال انتشار.
- پس از قرارداد context، Always-In و veto: 251/360 = 69.72% candidate قابل
  ارزیابی داشت. هر 251 مورد geometry و target ساختاری معتبر ساختند؛ گیت‌های
  AI/risk/probability/Trader Equation در این harness دیتابیس‌-آزاد شبیه‌سازی نشدند.
- MTR کامل: 45 SHORT و 45 LONG فعال؛ یعنی 90/120 سناریوی transition هدفمند.
  ناقص‌ها fail-closed ماندند و در سایر رژیم‌ها MTR غالب نشد.
- barbwire veto پنج candidate را پیش از scoring حذف کرد.
- 360 scale-twin با ضریب 0.01/1/1000 بررسی شد: 0 mismatch.
- Exception: 0. assertions dead/universal detector، context gate و scale
  invariance همگی پاس شدند؛ exit code 0.
- نتیجه: منطق MTR مرده نیست، veto واقعی است و thresholdهای نسبی نسبت به مقیاس
  قیمت پایدارند. نرخ 69.72% مربوط به core candidate است؛ publication به
  گیت‌های سخت بعدی وابسته می‌ماند.


### C-008 — اجرای نهایی suite با محیط import صحیح

- فرمان با PYTHONPATH صریح: 871 passed، 21 skipped، 2 failed، 47 warnings،
  2 subtests passed.
- دو failure باقیمانده در tests/unit/test_lifecycle.py هستند و به کد تغییرکرده
  ربط ندارند: ApplicationLifecycle از قبل settings اجباری دارد ولی fixture
  قدیمی فقط database می‌فرستد. برای پنهان‌کردن بدهی قبلی، skip یا تغییر صوری
  اعمال نشد.
- تست جدید target ساختاری/fixed-R prohibition: 7/7 passed.


### C-009 — استقرار نهایی و پایش

- git در پروژه وجود ندارد؛ commit ممکن نبود. بکاپ rollback پیش از تغییر:
  /opt/crypto-signal-backups/brooks_v5_prechange_20260912T070648Z.tar.gz
  با SHA256=7cf34c05c2480fe596163ec94d2e96be9615a4f4abd966ab1005636c02e9e934.
- clean suite با حذف فقط دو تست lifecycle ازپیش‌شکسته: 872 passed، 21 skipped،
  47 warnings و 2 subtests passed؛ exit code 0.
- docker compose build bot موفق؛ image manifest:
  sha256:dc41f703bab80e0968aad2c151be359b62c69e97c74eab0d4855c3f7bb2ebf09.
- فقط bot با --no-deps --force-recreate جایگزین شد؛ PostgreSQL restart/mutation نشد.
- runtime LIVE، poll=60s، پنج symbol و دو timeframe. چرخهٔ نخست هر 10 بازار/
  timeframe از 10:08:16 تا 10:08:27 UTC کامل شد.
- یک XRPUSDT/1h تا probability رسید و با probability=0.101821،
  break-even=0.324507، EV=-0.68623 و trader_equation_favorable=false رد شد؛
  بنابراین گیت V5 در اجرای واقعی شاهد شد.
- سیزده دقیقه لاگ زنده (10:08 تا 10:21 UTC) پایش شد:
  0 ERROR/CRITICAL/Traceback/scan_failed.
- وضعیت نهایی: bot running، RestartCount=0؛ PostgreSQL running/healthy.
- نسخهٔ داخل container: brooks-trilogy-full-core-v5-context-structural و
  BROOKS_HARD_GATE_ENGINEERING_POLICY_V5_TE_REQUIRED.


## فهرست کامل فایل/تابع و قبل → بعد

| فایل/تابع | قبل | بعد V5 |
|---|---|---|
| books_full_engine.evaluate | DEFERRED eligible؛ target ثابت R | فقط PASS؛ veto؛ target ساختاری |
| books_full_engine._choose_candidate | بدون market context | phase/location در انتخاب |
| books_full_engine._context_contract_status | قرارداد عمومی و نرم | Always-In/edge/follow-through/MTR سخت |
| books_full_engine._barbwire_stop_entry_veto | وجود نداشت | early veto مستقل از score |
| books_full_engine._execution_geometry | stop عمدتاً signal؛ 1R/2R | stop tree volatility/setup؛ magnets/MM |
| books_full_patterns._ema20_values | وجود نداشت | EMA causal برای شاهد MTR |
| books_full_patterns.detect_breakout_pullback | zero-bar pullback ممکن | pullback واقعی 1..5 bar |
| books_full_patterns.detect_major_trend_reversal | break/test تقریبی | چهار شاهد کامل + metadata |
| books_full_patterns.detect_climactic_reversal | climax بدون شاهد صریح | extreme/reversal metadata |
| books_full_patterns.detect_final_flag | flag بدون late-trend | late span/push اجباری |
| context_classifier._recent_strong_breakout | strong streak داخل range کافی | پاک‌کردن base structure اجباری |
| advanced_context.assess_advanced_context | channel observations | phase SPIKE/SPIKE_CHANNEL/TIGHT/TRANSITION |
| market_context.build_market_context | MICRO_CHANNEL ID مرده | directional micro-channel IDs |
| books_policy/BrooksBooksPolicy | tick-only buffer؛ fixed targets | volatility buffer/room/target limit versioned |
| books_full_policy/BrooksFullCorePolicy | MTR/final/barbwire constants نبود | thresholdهای نسبی versioned |
| lifecycle._halfway_to_first_target_reached | نیمهٔ TP1 | حذف؛ _breakeven_ready پس از HIT هدف ساختاری |
| BinanceFuturesMarketDataProvider.get_snapshot | clock دوباره؛ freshness نبود | endTime/normalize/closed/fresh fail-closed |
| SignalIntelligenceService.evaluate | TE advisory | probability minimum + TE در approval |
| SignalGateService.evaluate | TE advisory | failureهای سخت probability/TE |


## فایل‌های تست/مستندات تغییرکرده یا افزوده

- تغییر تست‌ها: test_brooks_full_context_contract.py،
  test_brooks_chapter29_stop_geometry.py، test_brooks_trailing_stop_management.py،
  test_binance_futures_market_data.py و test_signal_recovery_policy.py.
- افزوده: scripts/brooks_v5_synthetic_validation.py، BOOKS_NOTES_V5.md و
  AUDIT_V5.md.
- app/core/config.py و دیتابیس تغییر نکردند؛ migration اجرا نشد.

## موارد نیازمند تصمیم/اعتبارسنجی انسانی بعدی

- بهبود واقعی win/stop rate فقط پس از cohort کافی از سیگنال‌های V5 قابل سنجش
  است؛ اعداد baseline صرفاً مبنای قبل از cutover هستند، نه ادعای سودآوری.
- phase فعلی از snapshot بسته استنباط می‌شود و state-machine پایدار میان چرخه‌ها
  نیست. افزودن state تاریخی نیازمند schema/retention design جداگانه است.
- دادهٔ higher-timeframe در Signal Intelligence فعلاً UNAVAILABLE ثبت شد؛ تصمیم
  لازم است آیا MTF به hard veto تبدیل شود یا فقط confirmation بماند.
- الگوهای session-anchored مثل opening reversal/gap برای بازار 24/7 بدون تعریف
  session boundary عمداً NOT_APPLICABLE هستند؛ تعریف Asia/London/NY تصمیم محصول است.
- نرخ core-candidate در synthetic برابر 69.72% است؛ انتشار نیست، اما باید طی
  چند هفته نسبت rejection هر لایه و drift پترن‌ها مانیتور شود.
- دو تست قدیمی ApplicationLifecycle باید در تسک نگهداری جدا fixture settings
  دریافت کنند؛ من برای سبزکردن صوری suite رفتار runtime را شل نکردم.


## C-010 — آدیت تکمیلی مدیریت پس از هدف اول (V6)

- یافتهٔ اصلی: operations/lifecycle.py::_breakeven_ready در V5 صرفاً با
  first.status == HIT فعال می‌شد. این رفتار BRK-V6-MGMT-001/002/006 را نقض
  می‌کرد: T1 فعلی اغلب 1R است، در حالی‌که strong trend نباید الزاماً در 1R
  scale-out یا breakeven شود.
- _aggregate_close_pct همهٔ تارگت‌ها را با وزن مساوی فرض می‌کرد؛ هیچ مدل
  صریحی از scalp portion، swing portion یا runner وجود نداشت. بنابراین نتیجهٔ
  تاریخی فقط به‌طور ضمنی 50/50 بود و نمی‌توانست مدیریت context-aware را حساب کند.
- رسیدن همهٔ تارگت‌ها همیشه سیگنال را می‌بست؛ در نتیجه runner تعریف‌شده در
  TRD ch.18 و REV chs.15/19/24 وجود نداشت.
- پیام Telegram فقط HIT شدن TP و جابه‌جایی stop را نشان می‌داد و مشخص نمی‌کرد
  چه سهمی بسته شده یا آیا هدف فقط reference level بوده است.

## C-011 — تغییرات پیاده‌سازی مدیریت V6

- افزوده: app/modules/operations/trade_management.py با policy قفل‌شونده بر
  مبنای initial risk، market regime، target R و channel quality.
- trend: هدف زیر 2R فقط reference level؛ اولین target واجدشرط 50% scale-out؛
  هدف بعدی 25%؛ runner باقی می‌ماند.
- reversal/transition: اولین target حداقل 1R برابر 50%، بعدی 25% و runner 25%.
- range: دو target به‌صورت 50%/50% و بدون runner بیرون range.
- plan در SignalAutomationMetadata.analysis_metadata.trade_management_v6
  ذخیره می‌شود تا trail شدن stop، initial R را تغییر ندهد. initial stop برای
  سیگنال موجود از event immutable نوع CREATED بازیابی می‌شود.
- SignalService.hit_target metadata اختیاری و backward-compatible پذیرفت؛
  eventهای TARGET_HIT اکنون exit_fraction، remaining_fraction، context و
  management action را ثبت می‌کنند.
- P/L پایان معامله وزن‌دار شد: سود بخش‌های واقعاً خارج‌شده + بازده تمام سهم
  باقی‌مانده در terminal stop/exit.
- all-targets-hit فقط وقتی معامله را می‌بندد که remaining fraction صفر باشد؛
  runner روند/برگشت تا structural stop باز می‌ماند.
- breakeven دو مسیر مستقل دارد: بعد از scale-out واقعی در context مجاز، یا
  test-entry سپس extreme جدید. tight channel فقط مسیر ساختاری را می‌پذیرد.
- Telegram اکنون reference-only، درصد secured و درصد runner را نمایش می‌دهد.
- تصمیم‌های عددی fraction در BRK-V6-MGMT-007 صریحاً engineering policy هستند.
- بکاپ پیش از تغییر:
  /opt/crypto-signal-backups/brooks_v5_trade_management_prechange_20260912_154500.tar.gz
  با SHA256=e9d504c133a904ae9275547c5218028c167f1ffdc944170ff573ce0db471ce59.
- baseline پیش از تغییر: 1,912 رویداد کل، 222 TARGET_HIT و 5 STOP_LOSS_UPDATED.
  برای نمونهٔ signal 425، V5 در T1=1R فوراً BE کرد و P/L را با فرض 50/50 برابر
  0.16813944% بست؛ این نمونه شاهد مستقیم مشکل بود.


## C-012 — اعتبارسنجی نهایی مدیریت V6

- python3 -m py_compile روی تمام فایل‌های تغییریافته: exit code 0.
- Ruff روی فایل‌های تغییریافته و تست‌ها: All checks passed.
- گیت واحد/رگرسیون نهایی: 44 passed، 0 failed در 2.56s.
- کل suite با PYTHONPATH صحیح: 886 passed، 21 skipped، 0 failed،
  47 warnings و 2 subtests passed. موارد skipped تست‌های opt-in هستند، نه
  failure پنهان‌شده.
- تمام integrationهای واقعی PostgreSQL روی دیتابیس جداگانهٔ
  crypto_bot_v6_test: 43/43 passed، 0 failed؛ migrationها تا head روی همین
  دیتابیس تست اجرا شدند و production schema تغییر نکرد.
- public-market network smoke عمداً در suite دیتابیس اجرا نشد؛ به‌جای آن
  چرخهٔ زندهٔ production روی Binance بعد از deploy مشاهده شد.
- اسکریپت scripts/brooks_v6_trade_management_validation.py با seed
  20260912 روی 300 سناریوی OHLCV اجرا شد: 75 bull trend، 75 bear trend،
  75 range و 75 noise/transition؛ Exception=0.
- فعال‌سازی policy در synthetic: trend T1 scale-out=0/150، trend T2
  scale-out=150/150، range full-plan=75/75، transition runner=75/75،
  structural trail=65/300 (21.67%) و entry-test/resumption=35/300 (11.67%).
  این نرخ‌ها نشان می‌دهند شاخه‌های جدید نه مرده‌اند و نه همگانی.
- detector مربوط به entry-test/resumption پس از مشاهدهٔ فعال‌سازی بیش‌ازحد
  77.67% سخت‌تر شد: move اولیه حداقل 0.5R، retest بدون نقض original stop و
  سپس close فراتر از extreme قبلی لازم است. مقدار 0.5R تصمیم مهندسی است؛
  Brooks عدد جهانی ارائه نمی‌کند.
- سازگاری سیگنال‌های carry-over: اگر قبل از commit شدن policy جدید حداقل یک
  target خورده باشد، V5 equal-target accounting حفظ می‌شود و معامله به‌صورت
  retroactive به runner جدید تبدیل نمی‌شود.


## C-013 — استقرار و پایش production مدیریت V6

- build موفق؛ image جدید:
  sha256:f42d678e02e6b8295a56e95c23144166d25b833fb4370d9e0ad54b1db28eb9f8.
  image قبلی برای rollback:
  sha256:dc41f703bab80e0968aad2c151be359b62c69e97c74eab0d4855c3f7bb2ebf09.
- smoke داخل image نسخهٔ brooks-trilogy-trade-management-v6 را بارگذاری کرد.
- فقط سرویس bot با --no-deps --force-recreate تعویض شد؛ PostgreSQL restart
  نشد و هیچ migration یا تغییر schema در production انجام نشد.
- startup کامل بود: اتصال PostgreSQL، Brooks LIVE runtime، operations
  lifecycle، Performance Intelligence و Telegram همگی بالا آمدند.
- چرخهٔ نخست تمام 5 symbol × 2 timeframe را بدون exception کامل کرد. پنجرهٔ
  پایش زندهٔ چهار دقیقه‌ای با exit 124 طبیعیِ timeout تمام شد؛ شمارش سخت
  ERROR/CRITICAL/Traceback/scan_failed/lifecycle failed برابر صفر بود.
- شش سیگنال باز موجود policy را commit کردند: 5 مورد STRONG_TREND و 1 مورد
  REVERSAL_OR_TRANSITION. این planها در JSON metadata ذخیره شدند.
- وضعیت نهایی: bot running, RestartCount=0؛ PostgreSQL running/healthy,
  RestartCount=0.

## محدودیت‌های آگاهانهٔ V6

- این پروژه موتور lifecycle سیگنال است، نه اجرای سفارش صرافی. scale-out در
  event/P&L حسابرسی و پیام Telegram ثبت می‌شود؛ سفارش واقعی partial-close
  در Binance ارسال نمی‌شود.
- خروج runner روی clear strong opposite signal/Always-In reversal هنوز به
  lifecycle یک‌دقیقه‌ای سیم‌کشی نشده است. پیاده‌سازی سطحی با چند if/else
  عمداً انجام نشد؛ این کار باید context کامل timeframe سیگنال را به lifecycle
  منتقل کند و تسک جداگانه می‌خواهد. فعلاً runner با breakeven/structural stop
  مدیریت می‌شود.
- exit پایان جلسه برای بازار 24/7 فعال نیست؛ انتخاب مرز Asia/London/New York
  تصمیم محصول/معامله‌گر است.
- درصدهای 50/25/25 و threshold برابر 0.5R باید پس از cohort کافی به‌صورت
  out-of-sample بازاعتبارسنجی شوند؛ این اعداد قوانین جهانی کتاب نیستند.

## C-014 — مقایسه واقعی STOP/TARGET پس از V5، V6 و خروج runner

زمان snapshot دیتابیس: 2026-09-13T07:14:17.76267+00:00 (UTC). بررسی فقط خواندنی، در تراکنش REPEATABLE READ؛ هیچ پارامتر معاملاتی، کد یا دیتای عملیاتی تغییر نکرد.

### مرزهای زمانی و اعتبار شواهد

- V5: 2026-09-12 10:08:16 UTC، اولین اسکن عملیاتی ثبت‌شده در C-009. این زمان، شاهد فعال‌بودن نسخه است و جایگزین تقریبی مرز استقرار؛ timestamp دقیق StartedAt کانتینر اولیه در شواهد بازیابی‌شده موجود نیست. در بازه 10:00 تا 10:10 هیچ سیگنالی بسته نشده، پس این ابهام روی شمارش حاضر اثر ندارد.
- V6: 2026-09-12T14:45:13.553397952Z، StartedAt ثبت‌شده در بررسی کانتینر نشست قبلی؛ اولین رویداد plan نسخه V6 در 14:45:20.876640 UTC نیز با آن سازگار است. استقرار دوباره ساعت 16:35 نخستین فعال‌سازی V6 نیست.
- خروج runner: 2026-09-12T19:14:01.060324316Z، StartedAt کانتینر مستقر با مسیر شواهد مشترک.
- بک‌آپ‌ها شاهد وجود نسخه فایل‌اند و به‌تنهایی زمان فعال‌شدن کد محسوب نمی‌شوند. تغییرات استاپ/تارگت ساختاری و تریلینگ V5 در همان استقرار V5 بررسی می‌شوند.

### تعریف دقیق و بازتولید خط پایه

متن اصلی SQL تاریخی پیدا نشد؛ SQL زیر بازسازی منطق گزارش است، نه ادعای بازیابی عین متن کوئری قبلی. بازاجرای آن تا زمان ثبت baseline، 2026-09-12T07:31:10.548088Z، تعدادها و میانگین‌های قبلی را بازتولید کرد.

- جامعه: signals.status = CLOSED، تفکیک زمانی با closed_at در بازه‌های نیمه‌باز [شروع، پایان).
- STOP_HIT و حداقل یک TARGET_HIT: تعداد سیگنال متمایز دارای آن رویداد؛ مخرج درصد، کل سیگنال بسته‌شده همان بازه است. این دو دسته هم‌پوشانی دارند.
- ابتدا تارگت سپس استاپ: وجود TARGET_HIT با زمان قبل از STOP_HIT؛ نخستین تارگت قبل از آخرین استاپ.
- میانگین فاصله استاپ: abs(entry_price - stop_loss) / entry_price × 100، فقط برای سیگنال‌های بسته‌شده دارای STOP_HIT. میانگین روی تمام ۲۸۱ سیگنال، خط پایه را بازتولید نمی‌کند.
- stop_loss مقدار ذخیره‌شده فعلی است؛ اگر تریل شده باشد فاصله استاپ اولیه را نشان نمی‌دهد.
- فاصله تارگت برخوردکرده: میانگین abs(target_price - entry_price) / entry_price × 100 بر ردیف‌های signal_targets با status=HIT؛ نه میانگین بر تمام سیگنال‌ها. T1/T2 با target_number تفکیک می‌شوند.
- کنترل baseline: ۲۸۱ بسته؛ ۱۹۳ استاپ؛ ۱۳۲ سیگنال دارای تارگت؛ ۴۴ تارگت سپس استاپ؛ ۲۲۰ ردیف تارگت HIT؛ میانگین استاپ 0.524960776378٪ و تارگت 0.694967118603٪؛ T1 برابر 0.498444776382٪، T2 برابر 0.989750631934٪. کنترل جداگانه فاصله مطلق استاپ نیز 96.057849918290 بازتولید شد.

### جدول مقایسه بر اساس زمان بسته‌شدن

| بازه | بسته‌شده | STOP_HIT تعداد / درصد | حداقل یک TARGET_HIT تعداد / درصد | تارگت سپس استاپ | میانگین فاصله استاپ ٪ | میانگین فاصله تارگت HIT ٪ | وضعیت داده |
|---|---:|---:|---:|---:|---:|---:|---|
| خط پایه | 281 | 193 / 68.68٪ | 132 / 46.98٪ | 44 | 0.524961 | 0.694967 | مرجع تاریخی |
| V5 تا پیش از V6 | 4 | 4 / 100٪ | 1 / 25٪ | 1 | 0.515250 | 0.336279 | داده ناکافی؛ همگی سیگنال قدیمی |
| V6 تا پیش از runner | 1 | 1 / 100٪ | 0 / 0٪ | 0 | 0.007927 | — | داده ناکافی؛ سیگنال قدیمی |
| پس از خروج runner | 0 | 0 / — | 0 / — | 0 | — | — | داده ناکافی |
| کل پس از V5 | 5 | 5 / 100٪ | 1 / 20٪ | 1 | 0.413786 | 0.336279 | داده ناکافی؛ همگی سیگنال قدیمی |

علامت — یعنی قابل محاسبه نیست، نه صفر. درصد رخداد با جامعه صفر تعریف ندارد.

| بازه | T1 تعداد / درصد کل بسته‌شده | میانگین فاصله T1 ٪ | T2 تعداد / درصد کل بسته‌شده | میانگین فاصله T2 ٪ |
|---|---:|---:|---:|---:|
| خط پایه | 132 / 46.98٪ | 0.498445 | 88 / 31.32٪ | 0.989751 |
| V5 تا پیش از V6 | 1 / 25٪ | 0.336279 | 0 / 0٪ | — |
| V6 تا پیش از runner | 0 / 0٪ | — | 0 / 0٪ | — |
| پس از خروج runner | 0 / — | — | 0 / — | — |
| کل پس از V5 | 1 / 20٪ | 0.336279 | 0 / 0٪ | — |

### خروج مستقل runner و سودوزیان

RUNNER_CLOSED_ALWAYS_IN_REVERSAL در کل دیتابیس: صفر رویداد، صفر سیگنال. در هر سه بازه نیز صفر. میانگین سودوزیان وزن‌دار سهم runner و میانگین profit_loss سیگنال‌های دارای این خروج، هر دو NULL / فاقد نمونه‌اند؛ نه صفر سود و نه اثبات موفقیت یا شکست.

این رویداد مستقل شمرده می‌شود، اما سیگنالی که قبلاً خروج جزئی تارگت داشته می‌تواند هم TARGET_HIT و هم خروج runner داشته باشد؛ جمع دسته‌های رخداد الزاماً برابر کل سیگنال‌ها نیست. سودوزیان این سامانه، سودوزیان ثبت‌شده سیگنال است؛ این کوئری مدرک اجرای سفارش واقعی در صرافی نیست.

### محدودیت حیاتی انتساب به نسخه و تفسیر

هر پنج سیگنال بسته‌شده بعد از V5 پیش از استقرار V5 ایجاد شده‌اند؛ engine_version هر پنج، brooks-trilogy-full-core-v3-book-aligned-p2 است. آخرین سیگنال ثبت‌شده در بررسی مکمل، 2026-09-12T09:45:12.674658Z بود. شمار کل سیگنال‌های ایجادشده از مرز V5 تا snapshot: صفر، در هر وضعیتی. بنابراین جامعه سیگنال‌های جدید V5/V6/runner برای ارزیابی کیفیت صدور، صفر است.

اعداد جدول، خروج سیگنال‌های منتقل‌شده از نسخه قبلی را توصیف می‌کنند و اثر استاپ/تارگت جدید بر سیگنال تازه را اندازه نمی‌گیرند. نمونه یک‌تایی V6 دارای plan نسخه V6 بود، اما ورود قدیمی داشت؛ فاصله 0.007927٪ مربوط به استاپ ذخیره‌شده پس از مدیریت است، نه عرض استاپ اولیه. برای آن سیگنال، entry=77144.48478، stop_loss=77150.6 و initial_stop_loss در plan برابر 77253.14 بود.

در داده مشاهده‌شده، STOP_HIT از 68.68٪ به 100٪ افزایش و TARGET_HIT از 46.98٪ به 20٪ کاهش یافته؛ این کاهش هم‌زمان هر دو نرخ نیست و نشانه موفقیت هم نیست. با N=5 و همگی ورود قدیمی، نمی‌توان افت تارگت را به دوربودن تارگت ساختاری جدید یا افزایش استاپ را به کیفیت V5 نسبت داد. فاصله میانگین استاپ از 0.524961٪ به 0.413786٪ رسیده، ولی به‌علت نمونه کوچک و تغییر استاپ در طول معامله، دلیلی بر بهبود طراحی اولیه نیست.

هیچ بازه جدید به حد راهنمای ۳۰ سیگنال بسته‌شده نمی‌رسد؛ ۳۰ نیز صرفاً حد اولیه برای گزارش توصیفی است، نه تضمین معناداری آماری یا اثبات علت‌ومعلول.

توصیه: اکنون ضریب بافر 0.10 یا حداقل فاصله تارگت 0.50 تغییر نکند. گزارش طی ۷ تا ۱۴ روز آینده و پس از جمع‌شدن تعداد کافی سیگنال تازه دوباره اجرا شود؛ فقط گذشت زمان کافی نیست. نبود انتشار جدید باید در یک بررسی خواندنی جداگانه از مسیر ردشدن کاندیداها بررسی شود؛ از نبود سیگنال به‌تنهایی نمی‌توان خرابی یا سخت‌گیری بیش‌ازحد را نتیجه گرفت.

### SQL قابل بازاجرای همین گزارش

```sql

BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='30s';
WITH bounds(label,lo,hi) AS (VALUES
 ('baseline_recheck',NULL::timestamptz,'2026-09-12 07:31:10.548088+00'::timestamptz),
 ('post_v5_total','2026-09-12 10:08:16+00'::timestamptz,now()),
 ('v5_before_v6','2026-09-12 10:08:16+00'::timestamptz,'2026-09-12 14:45:13.553397952+00'::timestamptz),
 ('v6_before_runner','2026-09-12 14:45:13.553397952+00'::timestamptz,'2026-09-12 19:14:01.060324316+00'::timestamptz),
 ('runner_period','2026-09-12 19:14:01.060324316+00'::timestamptz,now())
), per_signal AS (
SELECT s.*, abs(s.entry_price-s.stop_loss)/NULLIF(s.entry_price,0)*100 AS stop_pct,
 e.has_stop,e.has_target,e.target_before_stop,e.both_events,e.runner_event,
 t.hits,t.dist_sum,t.t1,t.t1_sum,t.t2,t.t2_sum
FROM signals s
CROSS JOIN LATERAL (
 SELECT count(*) FILTER(WHERE event_type='STOP_HIT')>0 has_stop,
 count(*) FILTER(WHERE event_type='TARGET_HIT')>0 has_target,
 min(created_at) FILTER(WHERE event_type='TARGET_HIT') <
 max(created_at) FILTER(WHERE event_type='STOP_HIT') AS target_before_stop,
 count(*) FILTER(WHERE event_type='STOP_HIT')>0 AND count(*) FILTER(WHERE event_type='TARGET_HIT')>0 both_events,
 count(*) FILTER(WHERE event_type='RUNNER_CLOSED_ALWAYS_IN_REVERSAL')>0 runner_event
 FROM signal_events WHERE signal_id=s.id
) e
CROSS JOIN LATERAL (
 SELECT count(*) hits,sum(abs(target_price-s.entry_price)/NULLIF(s.entry_price,0)*100) dist_sum,
 count(*) FILTER(WHERE target_number=1) t1,
 sum(abs(target_price-s.entry_price)/NULLIF(s.entry_price,0)*100) FILTER(WHERE target_number=1) t1_sum,
 count(*) FILTER(WHERE target_number=2) t2,
 sum(abs(target_price-s.entry_price)/NULLIF(s.entry_price,0)*100) FILTER(WHERE target_number=2) t2_sum
 FROM signal_targets WHERE signal_id=s.id AND status='HIT'
) t
WHERE s.status='CLOSED'
), result AS (
SELECT b.label,b.lo,b.hi,count(s.id) closed,
 count(s.id) FILTER(WHERE has_stop) stop_n,
 count(s.id) FILTER(WHERE has_target) target_n,
 count(s.id) FILTER(WHERE target_before_stop) target_then_stop,
 count(s.id) FILTER(WHERE both_events) both_any_order,
 avg(stop_pct) FILTER(WHERE has_stop) stop_pct, sum(dist_sum)/NULLIF(sum(hits),0) hit_target_pct,
 coalesce(sum(hits),0) hit_rows,coalesce(sum(t1),0) t1_n,
 sum(t1_sum)/NULLIF(sum(t1),0) t1_pct,coalesce(sum(t2),0) t2_n,
 sum(t2_sum)/NULLIF(sum(t2),0) t2_pct,
 count(s.id) FILTER(WHERE runner_event) closed_with_runner_event,
 count(s.id) FILTER(WHERE s.created_at < '2026-09-12 10:08:16+00') pre_v5_created,
 avg(s.profit_loss) FILTER(WHERE runner_event) runner_signal_weighted_pnl
FROM bounds b LEFT JOIN per_signal s ON
(b.lo IS NULL OR s.closed_at>=b.lo) AND s.closed_at<b.hi
GROUP BY b.label,b.lo,b.hi
)
SELECT json_build_object('as_of',now(),'comparison',(SELECT json_agg(result) FROM result),
'runner_events',(SELECT json_build_object('events',count(*),'signals',count(DISTINCT signal_id),
'avg_weighted_runner_pnl',avg((metadata->>'weighted_return_pct')::numeric)) FROM signal_events WHERE event_type='RUNNER_CLOSED_ALWAYS_IN_REVERSAL'),
'created_after_v5',(SELECT json_agg(x) FROM (SELECT status,count(*) n FROM signals WHERE created_at>='2026-09-12 10:08:16+00' GROUP BY status) x),
'closed_after_versions',(SELECT json_agg(x) FROM (SELECT m.engine_version,m.generation_mode,m.market_type,count(*) n FROM signals s LEFT JOIN signal_automation_metadata m ON m.signal_id=s.id WHERE s.status='CLOSED' AND s.closed_at>='2026-09-12 10:08:16+00' GROUP BY 1,2,3) x),
'near_v5_boundary',(SELECT json_agg(x) FROM (SELECT id,created_at,closed_at FROM signals WHERE closed_at BETWEEN '2026-09-12 10:00+00' AND '2026-09-12 10:10+00') x));
ROLLBACK;

```

### خروجی خام snapshot

```json
{
  "as_of": "2026-09-13T07:14:17.76267+00:00",
  "comparison": [
    {
      "label": "baseline_recheck",
      "lo": null,
      "hi": "2026-09-12T07:31:10.548088+00:00",
      "closed": 281,
      "stop_n": 193,
      "target_n": 132,
      "target_then_stop": 44,
      "both_any_order": 44,
      "stop_pct": 0.5249607763777561,
      "hit_target_pct": 0.6949671186028813,
      "hit_rows": 220,
      "t1_n": 132,
      "t1_pct": 0.4984447763824683,
      "t2_n": 88,
      "t2_pct": 0.9897506319335009,
      "closed_with_runner_event": 0,
      "pre_v5_created": 281,
      "runner_signal_weighted_pnl": null
    },
    {
      "label": "post_v5_total",
      "lo": "2026-09-12T10:08:16+00:00",
      "hi": "2026-09-13T07:14:17.76267+00:00",
      "closed": 5,
      "stop_n": 5,
      "target_n": 1,
      "target_then_stop": 1,
      "both_any_order": 1,
      "stop_pct": 0.4137857496774055,
      "hit_target_pct": 0.33627887804576656,
      "hit_rows": 1,
      "t1_n": 1,
      "t1_pct": 0.33627887804576656,
      "t2_n": 0,
      "t2_pct": null,
      "closed_with_runner_event": 0,
      "pre_v5_created": 5,
      "runner_signal_weighted_pnl": null
    },
    {
      "label": "runner_period",
      "lo": "2026-09-12T19:14:01.060324+00:00",
      "hi": "2026-09-13T07:14:17.76267+00:00",
      "closed": 0,
      "stop_n": 0,
      "target_n": 0,
      "target_then_stop": 0,
      "both_any_order": 0,
      "stop_pct": null,
      "hit_target_pct": null,
      "hit_rows": 0,
      "t1_n": 0,
      "t1_pct": null,
      "t2_n": 0,
      "t2_pct": null,
      "closed_with_runner_event": 0,
      "pre_v5_created": 0,
      "runner_signal_weighted_pnl": null
    },
    {
      "label": "v5_before_v6",
      "lo": "2026-09-12T10:08:16+00:00",
      "hi": "2026-09-12T14:45:13.553398+00:00",
      "closed": 4,
      "stop_n": 4,
      "target_n": 1,
      "target_then_stop": 1,
      "both_any_order": 1,
      "stop_pct": 0.5152504446502815,
      "hit_target_pct": 0.33627887804576656,
      "hit_rows": 1,
      "t1_n": 1,
      "t1_pct": 0.33627887804576656,
      "t2_n": 0,
      "t2_pct": null,
      "closed_with_runner_event": 0,
      "pre_v5_created": 4,
      "runner_signal_weighted_pnl": null
    },
    {
      "label": "v6_before_runner",
      "lo": "2026-09-12T14:45:13.553398+00:00",
      "hi": "2026-09-12T19:14:01.060324+00:00",
      "closed": 1,
      "stop_n": 1,
      "target_n": 0,
      "target_then_stop": 0,
      "both_any_order": 0,
      "stop_pct": 0.007926969785901525,
      "hit_target_pct": null,
      "hit_rows": 0,
      "t1_n": 0,
      "t1_pct": null,
      "t2_n": 0,
      "t2_pct": null,
      "closed_with_runner_event": 0,
      "pre_v5_created": 1,
      "runner_signal_weighted_pnl": null
    }
  ],
  "runner_events": {
    "events": 0,
    "signals": 0,
    "avg_weighted_runner_pnl": null
  },
  "created_after_v5": null,
  "closed_after_versions": [
    {
      "engine_version": "brooks-trilogy-full-core-v3-book-aligned-p2",
      "generation_mode": "LIVE",
      "market_type": "futures",
      "n": 5
    }
  ],
  "near_v5_boundary": null
}
```
