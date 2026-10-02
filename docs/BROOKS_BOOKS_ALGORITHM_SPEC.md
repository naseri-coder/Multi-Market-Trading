# Brooks Books Algorithm Specification — v2 Shadow Core

## Goal

Build a deterministic, causal, auditable approximation of a narrow Brooks setup family:
**with-trend H2/L2 continuation**. The engine must first determine market context and
must not call a range reversal or an immature regime flip a trend H2/L2.

## Pipeline

```text
closed candles only
    -> causal engineering swings
    -> source-style context classifier
         trend strength
         breakout/follow-through
         Always-In evidence
         two-sided/tight-range evidence
         transition/reversal conflict
    -> regime
         BULL_TREND / BEAR_TREND
         TRADING_RANGE / TRANSITION / AMBIGUOUS
    -> if trend only: pullback anchor
    -> H1/H2 or L1/L2 event counting v2
         no global inside/outside/equal guard
         equality = no count event
         inside bar = neutral
         distinct later second excursion required
         H3/H4 are not silently relabeled as H2
    -> source-context check (trend vs range, EMA as contextual evidence)
    -> NO_SIGNAL by default (shadow)
    -> optional source-style stop entry + signal-bar stop
    -> engineering-only targets if explicitly enabled
```

## Causality

Every input is a closed candle at or before `snapshot.captured_at`. Swing points are
confirmed only after the configured right-side confirmation bars have closed. No future
bars are read to classify the current signal. Configuration values are part of the
version string.

## Important behavioral changes from v1

1. **H2/L2 is event-counted rather than "countertrend legs >= 2".** A candidate with
   six arbitrary countertrend leg transitions is no longer automatically called H2.
2. **No full-window EH-006 veto.** Inside bars, equal highs/lows and ordinary overlap
   no longer invalidate an entire pullback. Only actual count events matter.
3. **Context precedes pattern.** A mechanical H2 inside a trading range is not a trend
   H2. A fresh violent opposite breakout is a transition, not automatically a new trend.
4. **Always-In/follow-through is explicit.** Two consecutive strong bars are a key
   source-style piece of evidence, but exact bar-strength thresholds remain engineering.
5. **R40 is not a core source rule.** Previous R40/multi-horizon features can remain
   diagnostics, but v2 does not claim them as Brooks-authored gates.
6. **Signal-bar strength is not a universal hard gate.** Brooks notes that very strong
   trends can produce weak-looking with-trend signal bars.
7. **Execution stays off.** The detector can report `H2_CONFIRMED`/`L2_CONFIRMED` in
   `NO_SIGNAL` shadow results until replay and unseen validation approve it.

## Regime classifier

### Source inputs

- swing structure (HH/HL or LH/LL)
- recent trend-bar direction and quality
- consecutive strong breakout/follow-through bars
- body overlap/two-sided action
- EMA-side persistence as context, not a primary indicator
- recent displacement/path efficiency as engineering measurements of continuity

### Regime semantics

- `BULL_TREND`: source-style bull breakout/follow-through with no conflicting bear
  structure, or confirmed bull structure plus mature multi-factor continuation evidence.
- `BEAR_TREND`: mirror.
- `TRADING_RANGE`: overlapping/two-sided context without a credible breakout.
- `TRANSITION`: a credible new opposite breakout conflicts with prior structure; wait.
- `AMBIGUOUS`: insufficient evidence to decide.

## H2/L2 state machine v2

### H2

1. Start from a causal bull pullback anchor.
2. Observe at least some downward/sideways countertrend progress.
3. First closed bar with `high > prior.high` becomes H1.
4. Do **not** call the next higher-high bar H2 unless a later bar first creates a
   distinct second downward excursion.
5. The next qualifying higher-high event is H2.
6. Only report H2 if that H2 event occurs on the final closed bar of the snapshot.
7. If H2 already occurred earlier, the final bar is not relabeled H2.

L2 is the exact mirror using lows and upward excursions.

## Source gaps that remain engineering problems

Brooks' books are rich but discretionary. The following cannot be converted to exact
code without engineering choices:

- numeric swing confirmation width;
- exact deterministic micro trend-line-break algorithm for every H1/H2 edge case;
- exact boundary between broad channel and trading range;
- quantitative bar-strength cutoffs across crypto symbols/timeframes;
- universal definition of "enough follow-through";
- a universal stop size when signal bars are unusually large;
- a universal H2/L2 profit target;
- position sizing and leverage for crypto.

Every such value must remain versioned and must be validated on unseen data.

## Validation plan

1. Unit tests: count semantics, range/transition veto, closed-bar causality.
2. Replay the **same historical periods already used in Phase 8** to compare v1 vs v2.
3. Re-audit previously labeled KEEP/UNCERTAIN/REJECT candidates without changing their
   locked labels.
4. Run an unseen holdout only after the algorithm is frozen.
5. If visual/context validation is acceptable, freeze detector policy.
6. Only then define outcome execution contract and compute P&L/win rate.
7. Paper runtime remains disabled until outcome validation passes.
