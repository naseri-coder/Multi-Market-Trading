# Brooks Trilogy Rule Catalog — Engine v2

Status: source-expansion / shadow-only. No production behavior is changed by this document.

## Source hierarchy

Primary sources for the core engine:

1. Al Brooks — *Trading Price Action Trends*
2. Al Brooks — *Trading Price Action Trading Ranges*
3. Al Brooks — *Trading Price Action Reversals*

Secondary uploaded sources:

- *8 Price Action Secrets* (Tradeciety-derived Persian article)
- *Scalp Strategy with Price Action* (multi-timeframe scalp method)

The two secondary files are **not** used to define Brooks core rules. They may later be
used for separate experiments, but their ideas must never be presented as Brooks-authored.

## Classification labels

- `SOURCE_RULE`: directly supported by the Brooks trilogy.
- `SOURCE_INTERPRETATION`: deterministic coding interpretation of a qualitative Brooks rule.
- `ENGINEERING_POLICY`: a value or algorithm Brooks does not specify numerically.

## Core rule catalog

### BB-TRD-19-TREND-STRENGTH — SOURCE_RULE

Source: *Trading Price Action Trends*, Chapter 19, "Signs of Strength in a Trend".

The engine should consider multiple signs together rather than use a single trend score:
trending swing highs/lows, many trend-direction bars, little body overlap, small tails,
urgency, gaps, small/infrequent pullbacks, repeated two-legged pullbacks, failed
countertrend attempts, and persistent movement through important levels.

Implementation consequence: no single R40-style alignment threshold is accepted as a
Brooks rule. `context_classifier.py` uses a bundle of causal features.

### BB-RNG-02-BREAKOUT-FOLLOWTHROUGH — SOURCE_RULE

Source: *Trading Price Action Trading Ranges*, Chapter 2, "Signs of Strength in a Breakout".

A strong breakout is characterized by a strong trend body, small tails, multiple bars,
follow-through, urgency, limited pullback, and penetration of meaningful levels. A
breakout whose follow-through is weak has materially higher failure risk.

Implementation consequence: the v2 context classifier looks for a recent streak of
strong bars and does not treat a single isolated spike as a confirmed new regime.

### BB-REV-15-ALWAYS-IN — SOURCE_RULE

Source: *Trading Price Action Reversals*, Chapter 15, "Always In".

A meaningful Always-In flip generally requires a breakout/spike and follow-through.
Brooks commonly describes at least two consecutive reasonably strong trend bars before
most traders accept the new direction, while also noting that context can make one bar
enough in some cases.

Implementation consequence: v2 uses two strong bars as the default source-style
confirmation, while the exact numerical definition of a "strong bar" is engineering.

### BB-RNG-17-HL-BAR-COUNT — SOURCE_RULE

Source: *Trading Price Action Trading Ranges*, Chapter 17.

For a bull trend (or a trading range correcting sideways/down), the first bar whose high
exceeds the prior bar high is High 1. If the market fails to become a bull swing and
continues sideways/down, the next such occurrence is High 2. The bear-side rule is the
mirror using lows (Low 1 / Low 2).

Implementation consequence: equality does not create a new H/L count; an inside bar is
not itself a count event. The old "block the entire pullback if any inside/outside/equal
bar exists" guard is not retained in v2.

### BB-RNG-17-DISTINCT-SECOND-LEG — SOURCE_INTERPRETATION

Source basis: Chapter 17 states that there needs to be at least a tiny trend-line break
between H1 and H2, otherwise what appears to be H1/H2 can simply be a channel forming a
complex first leg.

Deterministic interpretation for OHLC-only replay: after H1/L1, at least one *later
closed bar* must make a distinct second countertrend excursion before the next H/L event
can be labeled H2/L2. An outside bar cannot complete both the first entry and the second
leg inside the same unknown intrabar sequence.

This is a source interpretation, not a claim that Brooks supplied this exact algorithm.

### BB-RNG-17-TREND-VS-RANGE-CONTEXT — SOURCE_RULE

Source: *Trading Price Action Trading Ranges*, Chapter 17.

H2/L2 in a trend and H2/L2 in a trading range have different meanings and locations.
A trend H2/L2 is a continuation setup. A range H2/L2 is often a reversal/fade setup and
should be judged relative to the range extreme and moving average. Mechanically trading
every H2/L2 is explicitly discouraged.

Implementation consequence: v2 deliberately scopes itself to **trend-continuation
H2/L2 only**. If context is a trading range, it returns `NO_SIGNAL` even if a mechanical
H2/L2 count exists. A separate trading-range engine can be added later.

### BB-RNG-22-TIGHT-RANGE / BARBWIRE — SOURCE_RULE + ENGINEERING_POLICY

Source: *Trading Price Action Trading Ranges*, tight trading range/barbwire discussions.

Overlapping bars, dojis/tails, and two-sided action indicate balance and create whipsaw
risk. Breakouts frequently fail and H2/L2 can fail on both sides before a real breakout.

Implementation consequence: tight-range detection is a context veto for this trend
continuation engine. The numerical overlap/body cutoffs are `ENGINEERING_POLICY`.

### BB-REV-03-REVERSAL-MATURITY — SOURCE_RULE

Source: *Trading Price Action Reversals*, trend-reversal and climactic-reversal sections.

Most reversal attempts fail. A credible reversal should show meaningful momentum,
trend-line/structural break, movement beyond important prior swing points, and often a
test or second entry. A sudden opposite spike without sufficient follow-through should
not instantly be treated as a mature opposite trend.

Implementation consequence: if recent strong breakout direction conflicts with existing
confirmed structure, v2 classifies the state as `TRANSITION`, not as an H2/L2 trend.

### BB-RNG-29-SIGNAL-BAR-STOP — SOURCE_RULE WITH VARIANTS

Source: *Trading Price Action Trading Ranges*, Chapter 29.

A common initial price-action stop is just beyond the signal bar. Brooks also discusses
wider money-management stops, structural/swing stops, scaling approaches, and retaining
a wider stop when the premise remains valid. Therefore there is no single universal
Brooks stop for every H2/L2.

Implementation consequence: when execution is explicitly enabled, v2 defaults to a
signal-bar stop plus a small crypto buffer. That buffer is an engineering policy.

### ENG-BOOKS-V2-TARGETS — ENGINEERING_POLICY

The trilogy discusses scalps, swings, measured moves, risk/reward and the trader's
equation, but does not prescribe one universal fixed R target for every H2/L2.

Implementation consequence: `1R` and `2R` targets remain versioned engineering defaults
and are inactive while autonomous execution is disabled.

## Deliberately not implemented as tradeable v2 setups yet

The source catalog now covers, but the v2 continuation engine intentionally does not
trade, the following families: trading-range fades, Major Trend Reversal, climactic/V
reversal, wedge/three-push reversal, final flag, breakout-pullback as its own setup,
High/Low 3 and 4, limit-order range entries, and scalp-specific management.

They should be separate detectors because Brooks gives them different context and trade
management. Combining them into one H2/L2 state machine would recreate the exact class
of false positives discovered in Phases 8.5–8.20.
