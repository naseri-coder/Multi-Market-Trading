# Brooks Trilogy Full Core v3

## Purpose

This is the direct source-grounded core requested from the three primary Al Brooks books:

1. **Trading Price Action Trends**
2. **Trading Price Action Trading Ranges**
3. **Trading Price Action Reversals**

The earlier Books v2 detector was intentionally limited to H2/L2 trend continuation.  v3
changes the architecture: each major Brooks setup family has a separate detector and its
own context instead of being forced through H2/L2.

## Core pipeline

```text
closed candles
  -> causal swing/structure infrastructure
  -> Brooks trend/range/transition + Always-In context
  -> independent setup-family detectors
       trend H2/L2 continuation
       strong breakout
       breakout pullback
       failed breakout
       failed failure / second signal
       trading-range fade
       double top/bottom reversal
       wedge / three-push reversal
       major trend reversal (break + test)
       climactic reversal
       final-flag reversal
  -> two-reason invariant
  -> source-context compatibility
  -> deterministic candidate precedence
  -> setup_type + rule evidence
  -> optional execution geometry (OFF by default)
```

## Source rules represented directly

- Trend strength is multi-factor, not one magic score (Trends, Ch. 19).
- Repeated two-legged pullbacks and H2/L2 with-trend entries matter in trends.
- H1/H2 and L1/L2 are bar-counting events, not arbitrary leg counters (Ranges, Ch. 17).
- A breakout is stronger with strong trend bars, small tails, urgency and follow-through
  (Ranges, Ch. 2).
- A breakout pullback is a small pullback, about one to five bars, after a breakout
  (Ranges glossary / Ch. 5).
- A failed failure is a second signal that resumes the original breakout and is more
  reliable than the first attempt (Ranges glossary / Ch. 5).
- Trading ranges are two-sided: buy low, sell high; do not treat their H2/L2 like trend
  H2/L2 (Ranges, Chs. 21–23).
- A trade should have at least two reasons; countertrend bar-count patterns in a steep
  trend are not reversal patterns by themselves (Ranges, Ch. 26).
- Major trend reversal: break the old trend line/channel, then usually test the old trend
  extreme (Reversals, Ch. 3).
- Wedges are three-push patterns; the pushes need not be geometrically perfect
  (Reversals, Ch. 5; Ranges, Ch. 18).
- A climactic reversal is a climax followed soon by a sharp opposite move; most climaxes
  instead lead to a trading range and trend resumption (Reversals, Ch. 4).
- Final flags are late two-sided flag/range structures whose breakout can reverse the
  trend (Reversals, Ch. 7).
- Always-In is determined from the direction traders would choose if forced to hold a
  position, typically after a spike/breakout and follow-through (Reversals, Ch. 15).

## Deterministic source interpretations

Brooks writes discretionary price action.  The following are explicit coding
interpretations, not claims that the books specify these exact formulas:

- causal swing confirmation uses the existing 2-left / 2-right engineering infrastructure;
- a close through a confirmed swing is used as a deterministic breakout / structure-break
  proxy;
- the upper/lower 25% of a quantified range is an engineering proxy for "near the top" /
  "near the bottom";
- double-top/bottom tolerance is a fraction of recent range;
- a structure break is used as an OHLC proxy for a discretionary trend-line break in MTR;
- climax size uses recent median bar range;
- final-flag compactness uses overlap and recent-range compression.

Every such value is versioned in `BrooksFullCorePolicy.configuration_version`.

## Production safety

Installing this package does **not** change Telegram, DB, PAPER, signal publication or
production wiring.  `enable_trade_decisions=False` by default.  The complete detector
still identifies a best `setup_type` and attaches source evidence inside a NO_SIGNAL
result, so it can be wired deliberately in the next phase without another research loop.
