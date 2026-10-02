# Brooks Core V5 - Trilogy Source Notes

Status: SOURCE GATE for V5. This document is the mandatory source of truth for the audit and implementation.

## 0. Source policy and evidence coverage

- Primary sources only: Al Brooks, *Trading Price Action Trends* (TRD), *Trading Price Action Trading Ranges* (RNG), and *Trading Price Action Reversals* (REV).
- `SOURCE_RULE` means a rule stated by Brooks. `SOURCE_INTERPRETATION` means a deterministic OHLCV representation of a qualitative rule. `ENGINEERING_POLICY` means Brooks gives no exact number or algorithm.
- No secondary article may define Brooks behavior. No qualitative statement may silently become a global fixed threshold.
- Full text was extracted page-by-page and indexed by book, PDF page, chapter, and paragraph. Coverage: TRD 477/477 pages and 26 chapters; RNG 236/236 pages and 32 chapters; REV 578/578 pages and 25 chapters.
- PDF SHA-256: TRD `ff3fa3198b11a9087338d39135a638d27b2646f52bf2a6418d9a34be0d334d94`; RNG `78f6e14ed799bc97ca2aa6ff17f2d6280dc51499f7e37fb448365e4d187b6345`; REV `ee7621da29d7d909fd144ddc4b8755ee1b4de729e84bf84e2379a2f97a1108be`.
- The implementation must cite one or more rule IDs below in code comments/tests and in `AUDIT_V5.md`.

## 1. Market phase: trend, spike, channel, and trading range

### BRK-V5-PHASE-001 - Spectrum, not mutually isolated labels (`SOURCE_RULE`)

Price action lies on a spectrum from extreme trend to extreme trading range. Every trend contains smaller ranges and every range contains smaller trends; the same structure can be a trend on one timeframe and a pullback/range on another. Classification must therefore include timeframe and confidence, not only one absolute label. Source: TRD ch.1, PDF pp.85-86.

### BRK-V5-PHASE-002 - Market inertia (`SOURCE_RULE`)

The default expectation is continuation of the current state: most reversal attempts in a trend fail, and most breakout attempts from a trading range fail. The burden of evidence is on a state change. Source: TRD ch.1, PDF p.85; RNG ch.7, PDF pp.71-72.

### BRK-V5-PHASE-003 - Spike (`SOURCE_RULE`)

A spike is one or more trend bars showing urgency and a breakout into a clearer directional state. Multiple consecutive trend bars, small tails, little body overlap, penetration of meaningful levels, and limited pullback increase strength. A single trend bar is simultaneously a breakout/spike/climax candidate; context decides which property dominates. Source: TRD chs.2, 21, PDF pp.89-106, 355-358; RNG ch.2, PDF pp.39-41.

### BRK-V5-PHASE-004 - Channel after spike (`SOURCE_RULE`)

A strong non-exhaustive spike commonly gets follow-through as a channel. The channel has more two-sided trading and weaker directional probability than the spike. As it matures it tends to become a trading range; a channel is functionally a sloped trading range. Source: TRD chs.15, 21, PDF pp.249-278, 355-388; REV ch.4, PDF pp.142-146.

### BRK-V5-PHASE-005 - Trading range (`SOURCE_RULE`)

Repeated overlap, alternating control, tails, reversals, failed breakouts, and uncertainty indicate balance. In the middle, equidistant directional probability is about 50/50; strategy shifts to buy-low/sell-high or waiting for clarity. A directional spike inside the range is not a trend flip unless it breaks the range strongly and has follow-through. Source: TRD chs.1, 3, PDF pp.85, 107-112; REV ch.15, PDF pp.322-325.

## 2. Trend strength and Always-In

### BRK-V5-TREND-001 - Trend strength is a feature bundle (`SOURCE_RULE`)

Strength increases with trending highs/lows/closes/bodies; many with-trend bars; little body overlap; small tails; gaps and micro-gaps; meaningful level penetration; small, infrequent, mostly sideways pullbacks; repeated two-legged with-trend setups; failed countertrend attempts; sustained distance from the moving average; and urgency. No single item or score is sufficient. Source: TRD ch.19, PDF pp.337-339.

### BRK-V5-TREND-002 - Countertrend bars do not automatically weaken a strong trend (`SOURCE_RULE`)

The best-looking reversal bars and even the largest bars can be countertrend traps. In the strongest trends, with-trend signal bars can look weak. The stronger the trend, the less important signal-bar appearance is for a with-trend entry and the more demanding it must be for a countertrend entry. Source: TRD chs.4, 19, PDF pp.115-117, 337-344.

### BRK-V5-AI-001 - Always-In definition (`SOURCE_RULE`)

Always-In is the direction a trader would choose if forced to hold either long or short now. It is a swing-direction concept, not permission to trade every minor reversal, and it is dangerous as an entry concept inside a trading range. Source: REV ch.15, PDF pp.321-324.

### BRK-V5-AI-002 - Flip confirmation (`SOURCE_RULE`)

The default confirmation is a breakout/spike plus follow-through, commonly at least two consecutive reasonably strong trend bars. Context can make one strong bar sufficient, but that is an exception requiring evidence. Weak or opposite-close follow-through means the attempted flip is suspect. Source: REV ch.15, PDF pp.323-327, 338-341.

### BRK-V5-AI-003 - Range veto (`SOURCE_RULE`)

Inside a range, a sharp move toward one edge can be a vacuum and should not be called Always-In solely from local momentum. Consensus requires a strong breakout of the whole range plus follow-through. Source: REV ch.15, PDF pp.324-325.

## 3. High/Low 1-2-3-4 counting

### BRK-V5-HL-001 - High count (`SOURCE_RULE`)

During a sideways/down correction in a bull trend or trading range, the first bar whose high exceeds the prior high ends the first leg and is High 1. If no bull swing follows and correction continues, the next such event is High 2. A tiny trend-line break/distinct intervening excursion is needed; otherwise H1/H2 can be only a complex first leg. Equality is not a new count. Source: RNG ch.17, PDF pp.108-109.

### BRK-V5-HL-002 - Low count (`SOURCE_RULE`)

Mirror rule: during a sideways/up correction in a bear trend or trading range, the first bar whose low falls below the prior low is Low 1; later distinct attempts are Low 2, 3, and 4. Source: RNG ch.17, PDF pp.108-110.

### BRK-V5-HL-003 - Context changes meaning (`SOURCE_RULE`)

H2 in a bull trend and L2 in a bear trend are continuation setups, commonly near the moving average. In a trading range, H2 is considered only near the range bottom and L2 only near the range top; the same mechanical pattern at the wrong edge is often a trap to fade. In a clear bear trend, H1/H2 longs are not valid trend setups; in a clear bull trend, L1/L2 shorts are not valid trend setups. Source: RNG ch.17, PDF pp.108-110.

### BRK-V5-HL-004 - High/Low 3 and 4 (`SOURCE_RULE`)

H3/L3 are three-push or wedge/triangle variants. H4/L4 can be a higher-timeframe H2/L2 or a spike-and-channel correction. If H4/L4 fails, assume prior trend control may be lost and wait for structure. A strong breakout through a failed H2/L2 usually implies further legs; do not mechanically fade it. Source: RNG ch.17, PDF pp.109-123.

### BRK-V5-HL-005 - Intrabar ambiguity (`SOURCE_INTERPRETATION`)

An outside bar can cross both sides, but OHLC alone does not reveal the order. It must not be allowed to manufacture two legs or two count events without lower-timeframe ordering data. Source basis: RNG ch.17, PDF pp.119-121.

## 4. Signal bar, entry bar, follow-through, and project “key bar”

### BRK-V5-SBAR-001 - Signal bar is contextual (`SOURCE_RULE`)

A setup bar becomes a signal bar only after the next bar triggers the entry; that current bar is the entry bar and the next is follow-through. A bar shape alone is never a setup. Direction, market phase, location, and preceding structure determine its meaning. Source: TRD ch.4, PDF pp.113-118.

### BRK-V5-SBAR-002 - Reversal bar quality (`SOURCE_RULE`)

A bull reversal bar minimally closes above its open or midpoint; stronger examples open near/below the prior close, close well above it, have a lower tail about one-third to one-half of the bar, little upper tail/overlap, reverse multiple prior closes/highs, and receive strong entry/follow-through. Bear logic mirrors this. Source: TRD ch.5, PDF pp.119-121.

### BRK-V5-SBAR-003 - Context-dependent quality threshold (`SOURCE_RULE`)

Countertrend reversals require much stronger signal bars and surrounding evidence than with-trend pullbacks. A bad-looking with-trend bar in a very strong trend can be valid; a beautiful reversal bar in barbwire or against an unbroken strong trend is not. Source: TRD chs.4-7, PDF pp.115-117, 189-198.

### BRK-V5-SBAR-004 - Closed-bar causality (`SOURCE_RULE`)

Do not finalize a signal from an unfinished bar; late changes in close/body/tails materially change strength. Entry, stop tightening, and follow-through evaluation must use closed bars unless an explicitly separate intrabar model supplies ordering. Source: TRD ch.8, PDF pp.199-202.

### BRK-V5-SBAR-005 - “Key bar” is not a Brooks-defined standalone pattern (`SOURCE_BOUNDARY`)

The trilogy does not define a universal `key_bar` detector. In V5, any project key-bar field must be derived evidence (breakout/signal/entry/follow-through/climax role plus context), never an independent Brooks rule.

## 5. Major Trend Reversal (MTR)

### BRK-V5-MTR-001 - Four mandatory conditions (`SOURCE_RULE`)

An MTR requires: (1) an existing visible trend; (2) a sufficiently strong countertrend move that breaks the trend line and usually the moving average; (3) a test of the old trend extreme followed by a second reversal - HH/DT/LH at a bull top or LL/DB/HL at a bear bottom; and (4) that second reversal travels far enough to create consensus that the trend reversed. Source: REV ch.3, PDF pp.112-113.

### BRK-V5-MTR-002 - Trend-line break is necessary evidence, not the reversal (`SOURCE_RULE`)

A trend-line break alone does not reverse a trend. Continue expecting a test of the prior extreme. A weak break that cannot reach the moving average is inadequate; a test that is itself a strong channel can restart the process and requires another breakout/pullback. Source: REV ch.3, PDF pp.116-117, 128-134.

### BRK-V5-MTR-003 - Early versus confirmed entry (`SOURCE_RULE`)

Early MTR entries commonly have probability below 50% but large reward. Waiting for a clear Always-In flip raises probability, often to 60%+, while reducing remaining reward and increasing structural stop distance. Both must still pass the Trader’s Equation. Source: REV ch.3, PDF pp.112-113, 127.

## 6. Climaxes and three-push structures

### BRK-V5-CLX-001 - Climax definition (`SOURCE_RULE`)

A climax is unsustainable behavior: a large trend bar or sequence moving too far/fast. It ends at the first pause/reversal. Most climaxes lead first to a trading range/pullback, not an opposite trend. Reversal needs an opposite spike and follow-through. Source: REV ch.4, PDF pp.139-146.

### BRK-V5-CLX-002 - Continuation versus reversal (`SOURCE_RULE`)

An isolated countertrend spike inside a strong trend commonly becomes a flag and the original extreme is retested. Consecutive climaxes, trend-channel overshoot, mature trend, major support/resistance, opposite spike, and follow-through increase reversal odds. Source: REV ch.4, PDF pp.142-146.

### BRK-V5-WDG-001 - Wedge/three-push definition (`SOURCE_RULE`)

Three pushes in one direction form the common family that includes wedge, micro/parabolic wedge, triple top/bottom, double-top/bottom pullback, head-and-shoulders, final-flag failure, and expanding triangle variants. Shape may be imperfect; behavior and context dominate geometry. Source: REV ch.5, PDF pp.179-184.

### BRK-V5-WDG-002 - Pullback versus reversal (`SOURCE_RULE`)

A wedge pullback is with-trend and can be taken on the first valid signal. A wedge reversal is countertrend and usually needs a second entry or strong breakout plus pullback. In a strong trend, apparent wedge reversals often become sideways two-leg corrections and continuation setups. Source: REV ch.5, PDF pp.180-186.

### BRK-V5-WDG-003 - Wedge targets and failure (`SOURCE_RULE`)

First target after a triggered wedge reversal is the start/bottom of the wedge; next is a measured move based on pattern height. Failure beyond the wedge extreme can run quickly toward a measured move in the original direction; a later fourth-push reversal is a new setup, not proof the first detector was correct. Source: REV ch.5, PDF pp.179-184.

### BRK-V5-EXP-001 - Expanding triangle (`SOURCE_RULE`)

At least five alternating swings, sometimes seven or nine, with progressively higher highs and lower lows. It is a trading range that traps successive breakouts. It may be a reversal or continuation; the first objective is the opposite side, and a successful breakout can project the last-leg/pattern measured move. Failure converts it into continuation or a larger expanding range. Source: REV ch.6, PDF pp.209-215.

### BRK-V5-DTDB-001 - Double/triple structures are contextual (`SOURCE_RULE`)

Exact price equality is not required. After a trend-line break, HH/DT/LH and LL/DB/HL are behaviorally related tests. A double top in a bear trend is usually a bear flag/continuation; a double top after a mature bull trend plus reversal evidence is a reversal. Mirror for bottoms. Triple forms, triangles, H&S, final flags, and double-top/bottom pullbacks may encode the same three-push process. Source: REV chs.3, 8, PDF pp.114-116, 245-252.

## 7. Breakouts, failed breakouts, pullbacks, tests, and final flags

### BRK-V5-BO-001 - Strong breakout checklist (`SOURCE_RULE`)

Require a bundle: large trend body relative to recent bars; small/no tails; several bars and follow-through; urgency and small intrabar pullbacks; meaningful penetration of several levels; micro/body/measuring gaps; reversal of many recent closes/extremes; delayed, shallow first pullback; breakout point and breakeven not breached; compatible higher context. Mirror for bears. Source: RNG ch.2, PDF pp.39-41.

### BRK-V5-BO-002 - Weak/failed breakout checklist (`SOURCE_RULE`)

Failure evidence includes small/average body with large rejection tail; opposite strong follow-through/inside reversal; overlap and repeated pullbacks; only a marginal level break; no scalp distance; deep intrabar retracements; pullback through breakout point/start of spike/breakeven; stalled resumption; and range context/confusion. Source: RNG ch.2, PDF pp.39-41.

### BRK-V5-BO-003 - Breakout pullback and test (`SOURCE_RULE`)

A strong breakout followed by a pullback that tests but respects the breakout area is among the most reliable setups. Tests can be exact, undershoot, overshoot, HH/LH/HL/LL. One-tick stop runs are common; entry and stop logic must preserve the structural premise rather than require exact equality. Source: RNG ch.5, PDF pp.52-58.

### BRK-V5-FF-001 - Final flag (`SOURCE_RULE`)

A potential final flag commonly occurs after a trend of dozens of bars and/or consecutive climaxes, is often horizontal with overlap/tails/reversals/opposite bodies, and can be one bar through many bars. The breakout is often taken only for a scalp and then fails back into the magnetic range. A final-flag reversal generally produces at least a two-legged correction, but not necessarily an opposite trend. Source: REV ch.7, PDF pp.217-220.

### BRK-V5-FF-002 - No hindsight-only label (`SOURCE_RULE` + `SOURCE_INTERPRETATION`)

“Final” is certain only in hindsight. A live detector must output a potential-final-flag hypothesis with maturity/climax/range evidence and later confirm breakout failure; it must not label every last visible flag as a tradable reversal. Source: REV ch.7, PDF pp.217-220.

## 8. Barbwire and tight trading ranges

### BRK-V5-TTR-001 - Definition and absolute stop-entry veto (`SOURCE_RULE`)

Barbwire is a tight range of three or more largely overlapping bars with at least one doji, usually prominent tails. Mechanical stop entries at the top/bottom repeatedly lose because institutions fade them. Unless it is a clearly contextual with-trend flag with breakout confirmation, do not enter a stop-order breakout from barbwire/tight-range balance. Source: RNG ch.22, PDF pp.151-161; especially pp.157-159.

### BRK-V5-TTR-002 - Sloped tight range is still a range (`SOURCE_RULE`)

A slightly sloped tight range remains balanced. Prefer waiting for a failed breakout, strong breakout plus follow-through, or breakout pullback. Do not reinterpret slope alone as trend strength. Source: RNG ch.22, PDF pp.158-160.

## 9. Protective-stop decision tree

### BRK-V5-STOP-001 - A live protective stop is mandatory (`SOURCE_RULE`)

Every trade needs an actual protective stop and a plan for the losing probability. Price-action stops are beyond structural invalidation; money-management stops cap tolerated distance. Source: RNG ch.29, PDF pp.202-208.

### BRK-V5-STOP-002 - Initial structure and recent volatility (`SOURCE_RULE`)

Default initial price-action stop is beyond the signal bar until the entry bar closes. Stop distance must also reflect recent bar size, first-hour required excursion, market volatility, setup type, and structural swing/spike. It is not a fixed percentage and not based only on the signal candle. Source: RNG ch.29, PDF pp.202-208.

### BRK-V5-STOP-003 - Large signal bar (`SOURCE_RULE`)

When the signal bar/spike is unusually large, either use a proportional money-management/structural stop with smaller position size, or use a capped money-management stop and accept re-entry risk. Never keep normal size merely because the nominal stop is tightened inside a structurally valid bar. Source: RNG ch.29, PDF pp.202-204.

### BRK-V5-STOP-004 - Small signal bar (`SOURCE_RULE`)

A small/doji signal bar does not justify an abnormally tight stop. Quiet pullbacks and tight channels often test beyond that bar; use the normal volatility/structure stop if the premise remains valid. Do not tighten after a doji or minor one-bar range. Source: RNG ch.29, PDF pp.203, 208.

### BRK-V5-STOP-005 - Entry-bar update (`SOURCE_RULE`)

After a strong directional entry bar closes, a stop may tighten beyond that entry bar. If the entry bar is a doji or weak, retain the original stop. Countertrend entries demand faster invalidation than with-trend entries because failure is more likely. Source: RNG ch.29, PDF pp.203, 205, 208.

### BRK-V5-STOP-006 - Premise and timeframe integrity (`SOURCE_RULE`)

Exit immediately when the premise is invalid, even before the stop; otherwise give the trade room specified by its original timeframe and structure. Do not use a lower timeframe merely to manufacture a smaller stop. Source: RNG ch.29, PDF pp.203-208; TRD ch.8, PDF pp.199-202.

### BRK-V5-STOP-007 - Risk scoring must not reward tightness (`SOURCE_INTERPRETATION`)

Smaller stop distance is not intrinsically safer. Risk quality is position-adjusted monetary risk plus structural validity. Any scoring feature that rewards a tighter invalidation distance while ignoring stop-hit probability violates BRK-V5-STOP-002 through 006.

## 10. Breakeven and trailing stops

### BRK-V5-TRAIL-001 - Breakeven is earned, not immediate (`SOURCE_RULE`)

Move toward breakeven after a strong move/first profit objective or when the market has demonstrated the expected follow-through. Do not move to breakeven immediately after entry or after a doji; breakout tests commonly run exact breakeven stops. Source: RNG chs.5, 29, PDF pp.55-56, 203, 208.

### BRK-V5-TRAIL-002 - Swing trailing (`SOURCE_RULE`)

In a bull trend, after a new swing high, trail below the most recent confirmed higher low; mirror above the most recent lower high in a bear trend. Strong trend swings require wider stops and smaller size. Source: RNG ch.29, PDF pp.202, 206-207.

### BRK-V5-TRAIL-003 - Regime transition (`SOURCE_RULE`)

When a trend evolves into a trading range, trailing behind recent swings becomes likely to stop out near the wrong edge. Take partial/full profit on strength and switch management regime rather than blindly continue trend trailing. Source: RNG ch.29, PDF pp.202, 206.

## 11. Structural targets and magnets

### BRK-V5-TGT-001 - Target hierarchy (`SOURCE_RULE`)

Targets come from chart structure: prior swing high/low and trend extreme; range opposite edge/midpoint; breakout point/test; moving average; trend line/channel line; signal/entry bars from prior failed reversals; gaps; major support/resistance; and measured moves. Fixed-R may be a management reference, not the sole source of target price. Source: RNG chs.7-10, 30, PDF pp.71-89, 209-211.

### BRK-V5-TGT-002 - Measured moves (`SOURCE_RULE`)

Candidate projections include leg1=leg2; height of spike; height of trading range; gap/measuring-gap geometry; and pattern height (wedge/triangle). Several plausible anchors must be evaluated; target is an area/magnet, not exact certainty. Source: RNG chs.7-8, PDF pp.71-78; REV chs.5-6, PDF pp.179-184, 209-210.

### BRK-V5-TGT-003 - Context chooses target and management (`SOURCE_RULE`)

Strong trend: allow runner toward measured moves/opposite signals and scale out. Trading range/countertrend: closer structural target and more scalp-like management. A target beyond intervening strong resistance/support is not “reasonable reward” merely because it equals a fixed R multiple. Source: RNG ch.30, PDF pp.209-211.

## 12. Trader’s Equation and probability gate

### BRK-V5-TE-001 - Mandatory equation (`SOURCE_RULE`)

Before entry, require `P(win) * reward > P(loss) * risk`, using realistic structural stop and reachable structural target. Probability, risk, and reward are inseparable and change with every bar. Source: RNG ch.25, PDF pp.171-178.

### BRK-V5-TE-002 - Probability bands are context estimates (`SOURCE_RULE`)

When genuinely uncertain, use about 50%; a good contextual setup is commonly treated near 60%; a low-probability high-reward attempt near 40%. These are reasoning bands, not a claim of calibrated historical probability. Source: RNG ch.25, PDF pp.172-173.

### BRK-V5-TE-003 - V5 publication minimum (`SOURCE_INTERPRETATION`)

Autonomous published signals must pass both a calibrated minimum-win-probability gate and positive expected value after fees/slippage. The exact minimum is an engineering/configuration decision and must be validated out-of-sample; Brooks does not prescribe one universal bot threshold. No signal may pass merely because cumulative pattern score is high.

## 13. Apparent contradictions and context activation

1. **Wedge reversal vs continuation:** a wedge at the end of a mature trend with reversal evidence is countertrend and usually needs a second signal; a wedge pullback inside an established trend is a with-trend flag and first signal can be valid. Strong-trend “wedge tops/bottoms” often correct sideways and resume. Rules: BRK-V5-WDG-001/002.
2. **Double top/bottom reversal vs flag:** a double top after a bull trend plus prior bearish strength can reverse; a double top in a bear trend is a bear flag/continuation. Mirror for bottoms. Rule: BRK-V5-DTDB-001.
3. **H2/L2 continuation vs fade:** H2 bull-trend and L2 bear-trend are continuation; at range extremes they are reversal/fade structures; at the wrong range edge they are traps. Rule: BRK-V5-HL-003.
4. **Tight range continuation vs no-trade:** a tight range at an extreme after a strong breakout may be a with-trend flag, but stop-entry inside ordinary barbwire/mid-range is vetoed until strong breakout/failure evidence. Rules: BRK-V5-TTR-001/002.
5. **Large trend bar breakout vs climax:** the same bar is both. Early/context-supported follow-through activates breakout; late maturity, repeated climaxes, channel overshoot, structural magnet, opposite spike, and failed follow-through activate exhaustion. Rules: BRK-V5-PHASE-003, CLX-001/002, BO-001/002.
6. **Bad signal bar valid vs invalid:** bad-looking bar can be acceptable with a very strong trend and structural pullback; countertrend or range-edge breakout requires much stronger confirmation. Rules: BRK-V5-SBAR-002/003.
7. **Signal-bar stop vs wider stop:** signal-bar stop is common, not universal. Large bars can require a capped/proportional stop and smaller size; small bars often require a minimum volatility/structure stop. Rules: BRK-V5-STOP-002/003/004.
8. **Always-In spike inside a range:** local momentum alone may appear Always-In; range context keeps it a vacuum/leg unless the whole range breaks with follow-through. Rule: BRK-V5-AI-003.
9. **Final flag reversal vs ordinary flag:** every reversal has a last flag in hindsight, but live classification requires maturity/climax/two-sided evidence plus breakout failure. Rule: BRK-V5-FF-002.

## 14. Engineering values not supplied by Brooks

The trilogy does not specify universal ATR multipliers, overlap ratios, slope tolerances, pivot lookbacks, wick/body thresholds, crypto stop buffers, fee/slippage assumptions, calibrated publication probability, or exact confidence aggregation. All such values in V5 must be versioned configuration, scale with recent volatility/market structure, be marked `ENGINEERING_POLICY`, and be justified by synthetic tests plus historical out-of-sample evidence. No value may be attributed to Brooks.

## 15. Implementation invariants

- Required order: market phase -> trend-strength/Always-In -> structural pattern near a level -> countertrend veto/qualified exception -> structural stop and target -> Trader’s Equation -> publication gate.
- Absolute vetoes run before soft scoring: causal/closed-bar violation, unresolved intrabar ordering, barbwire stop-entry, structurally invalid stop, unreachable target, invalid MTR sequence, or non-positive Trader’s Equation.
- Pattern names never override context. The engine must retain evidence objects and source rule IDs for every decision.
- V5 must not claim a pattern detector is complete if it implements only geometry without state, location, confirmation, failure, stop, target, and management semantics.


## 16. مدیریت معامله پس از هدف اول — بازخوانی تکمیلی V6

### BRK-V6-MGMT-001 — هدف اول یک فرمان عمومی برای خروج نیست (SOURCE_RULE)

Brooks یک قانون جهانی از نوع «هر وقت TP1 لمس شد، دقیقاً X درصد ببند» ارائه
نمی‌کند. برنامه باید پیش از ورود مشخص کند معامله scalp است، swing است یا
ترکیب scalp/swing؛ تغییر premise بعد از ورود خطاست. Source: RNG ch.24؛ REV
ch.17, printed pp.337-339.

### BRK-V6-MGMT-002 — روند قوی: سودگیری اولیه را تا حداقل 2R عقب بینداز (SOURCE_RULE)

در strong trend، معامله‌گر نباید به‌خاطر اولین pause یا سطح 1R زود خارج شود.
نمونهٔ اجرایی Trends خروج نصف در 2R، سپس نگه‌داشتن باقی‌مانده تا برگشت واضح یا
پایان جلسه و trail پشت مبدأ spike/آخرین higher-low یا lower-high را نشان می‌دهد.
Source: TRD ch.18, printed pp.301-306.

### BRK-V6-MGMT-003 — روند: scale-out و runner با هم (SOURCE_RULE)

پس از رسیدن reward کافی، بخشی از پوزیشن بسته می‌شود؛ بخشی دیگر runner می‌ماند.
تقسیم نصف/ربع‌ها در کتاب نمونهٔ اجرایی است، نه درصد اجباری جهانی. runner تا
استاپ ساختاری، clear strong opposite signal، Always-In reversal یا پایان جلسه
نگه‌داری می‌شود. Source: TRD ch.18, printed pp.301-306؛ REV ch.15, printed
pp.300-302؛ REV ch.24, printed pp.470-471.

### BRK-V6-MGMT-004 — رنج: در لبهٔ مقابل فعالانه خارج شو (SOURCE_RULE)

در trading range، باقی‌گذاشتن کل معامله برای trailing stop مناسب نیست؛ چون
pullbackها غالباً سوئینگ قبلی را می‌شکنند. در resistance/support، measured-move
magnet یا range extreme باید partial/full profit گرفت و باقی‌مانده را حداکثر
در لبهٔ دور بست، مگر شکست قوی با follow-through رژیم را واقعاً عوض کند.
Source: RNG ch.24؛ RNG ch.29, printed pp.202-208.


### BRK-V6-MGMT-005 — برگشت معتبر: بخشی در 1–2R و runner کوچک (SOURCE_RULE)

در reversal قوی که می‌تواند high/low مهم یا Always-In change باشد، نمونه‌ها
خروج حدود یک‌سوم تا نصف پس از 1–2R، خروج بعدی در pause/هدف بعدی، و نگه‌داشتن
حداقل حدود یک‌ربع تا breakeven/structural stop/opposite signal را نشان می‌دهند.
Source: REV ch.15, printed pp.300-302؛ REV ch.19, printed pp.377-378.

### BRK-V6-MGMT-006 — breakeven پس از سود/تأیید، نه لمس خام TP1 (SOURCE_RULE)

پس از scale-out واقعی می‌توان stop باقی‌مانده را حدود breakeven گذاشت. راه
ساختاری مستقل نیز این است: بازار ابتدا از ورود دور شود، pullback ورود را تست
کند، سپس extreme جدید بسازد؛ تست دوم ورود ضعف premise است. اما در tight/small-
pullback trend انتقال شتاب‌زده به breakeven می‌تواند runner خوب را حذف کند؛ آنجا
ساختار اولویت دارد. Source: RNG ch.29, printed pp.202-208؛ TRD ch.18, printed
p.306؛ TRD small-pullback-trend discussion.

### BRK-V6-MGMT-007 — درصدهای V6 تصمیم مهندسی‌اند (ENGINEERING_POLICY)

چون کتاب درصد واحد و اجباری تعیین نمی‌کند، V6 برای قابلیت حسابرسی این policy
را پیش از تغییر stop در metadata قفل می‌کند: trend: اولین خروج واجدشرط در
حداقل 2R برابر 50%، هدف واجدشرط بعدی 25%، runner حداقل 25%؛ reversal/transition:
50% در اولین هدف حداقل 1R، 25% در هدف بعدی، 25% runner؛ range با دو هدف:
50% در هدف نزدیک و 50% در هدف دور، بدون runner بیرون رنج. این fractions از
نمونه‌های کتاب الهام گرفته‌اند اما «عدد صریح و جهانی Brooks» نیستند و باید با
cohort واقعی out-of-sample بازاعتبارسنجی شوند.
