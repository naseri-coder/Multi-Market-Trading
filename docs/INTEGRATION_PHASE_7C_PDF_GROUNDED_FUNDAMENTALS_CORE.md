# Integration Phase 7C - PDF-Grounded Fundamentals Core

Primary source: uploaded `اسلاید کامل البروکس ilam98(1).pdf`, 150 slides, reviewed from page 1 through 150.

## What this PDF supports directly

- every market is in trend or trading range (p5; market-cycle discussion p110)
- support/resistance framing (p6; prior highs/lows/channels/MA on p126)
- breakout concept (p7) and successful breakout continuing away from the range (p100, p105)
- bull-trend H2: two legs sideways/down; buy stop above signal-bar high (p11)
- bear-trend L2: two legs sideways/up; sell stop below signal-bar low (p12)
- minor vs major reversal distinction (p13-p15)
- exact inside/outside bar relations (p16)
- default 20-bar EMA (p20)
- context means the bars to the left / big picture (p27; reinforced p123)
- Always-In direction follows resolved trend (p28-p29)
- trading-range breakout attempts often fail; source uses an 80% heuristic (p59, p97, p122)
- trends have inertia; source says most reversals fail (p120-p121)
- candlestick pattern alone is insufficient; context dominates (p116-p124)
- trend structure: HH/HL bull, LH/LL bear (p127)
- context and momentum are the two controlling forces (p128-p130)
- indicators are secondary to the bars (p133-p135)

## What the PDF does NOT specify deterministically

The reviewed fundamentals PDF does not provide exact numerical definitions for:
- causal swing confirmation
- all H1/H2/L1/L2 counting edge cases
- support/resistance zone width and merging
- Always-In flip thresholds
- momentum score
- successful-breakout minimum follow-through
- trade stop placement
- profit-target formula

Those are not silently attributed to Brooks.

## Phase 7C implementation

Source-grounded layer:
- BR-031 market structure from confirmed swings
- EMA(20) metadata
- context-over-pattern guard
- H2/L2 source concepts with page-level evidence

Engineering layer:
- causal swing confirmation from Phase 7B
- conservative inside/outside/equal-boundary counting guard
- causal two-countertrend-leg state machine
- explicit entry buffer
- structural stop plus configurable buffer
- configurable R-multiple targets

Autonomous trade decisions are OFF by default.
With `enable_trade_decisions=False`, the engine may detect `H2_CONFIRMED` or
`L2_CONFIRMED` but still returns `NO_SIGNAL`.

Only an explicit reviewed configuration can enable LONG/SHORT.

## Scope warning

This is a fundamentals-derived core from this 150-slide PDF. It is NOT represented as the
complete Brooks Trading Course strategy engine. Concepts such as a complete MTR or Wedge
algorithm remain outside this source because the slides mention/examples them without enough
deterministic rules for a faithful implementation.

No migration.
No dependency changes.
PAPER remains disabled.
No Telegram auto-publish.
No real orders.
