# Brooks Core v3 — Trader's Equation Roadmap Stage

## Roadmap position

The shared project roadmap orders the post-Expectation stages as:
`Trader's Equation -> AI Council -> Execution Planner`.
No explicit Phase-5 title was present in the shared roadmap snapshot, so this stage is
intentionally not assigned an invented phase number.

## Source grounding

Primary source: *Trading Price Action Trading Ranges*, Chapter 25.
The source defines favorable trade math using probability, reward, and risk:
probability-weighted reward must exceed probability-weighted risk.

Source PDF evidence used by this implementation: pages 172, 173, and 177.
Probability is explicitly uncertain; therefore the implementation does not infer or
calibrate a crypto probability from Foundation or Crypto Adaptation data.

## Implementation

- `traders_equation/entities.py`
- `traders_equation/evaluator.py`
- `traders_equation/adapter.py`
- `traders_equation/source.py`

## Safety contract

- No setup detector is added.
- No probability estimator is added.
- No entry, stop, target, leverage, Signal, DB write, chart, or Telegram output is created.
- Missing probability/risk/reward yields `UNRESOLVED`.
- A supplied probability requires an explicit `probability_basis`.
- `publication_allowed` is always false.
- The existing Phase-1/2/3/4 code is not modified.

## Mathematical states

- `FAVORABLE`: weighted reward > weighted risk.
- `MARGINAL`: weighted reward == weighted risk.
- `UNFAVORABLE`: weighted reward < weighted risk.
- `UNRESOLVED`: one or more required inputs are absent.

The evaluator also reports the exact break-even probability `risk / (risk + reward)`.
This is arithmetic, not a new Brooks threshold.

## Gate

- compile: PASS
- focused unit tests: 10/10 PASS
- production/runtime wiring: NONE
