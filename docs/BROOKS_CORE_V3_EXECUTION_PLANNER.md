# Brooks Core v3 — Execution Planner Roadmap Stage

## Position

This is the last stage explicitly named in the shared Brooks Core v3 roadmap pipeline.
It follows Trader's Equation and AI Council.

## Design

The planner is review-only. It accepts an existing Phase-3 `SetupCandidate` and
`RiskPlan`, plus Trader's Equation and AI Council results. It does not calculate new
entry, stop, target, leverage, position size, or exchange order parameters.

Readiness states:

- `READY_FOR_REVIEW`
- `BLOCKED`
- `INCOMPLETE`

`READY_FOR_REVIEW` is not execution approval. It only means the supplied risk plan is
complete, Trader's Equation is favorable, and the supplied council is unanimously
supportive under this fail-closed engineering policy.

## Safety

- `execution_allowed` is always false.
- `publication_allowed` is always false.
- No exchange SDK/order call.
- No DB write.
- No Telegram delivery.
- No PAPER/LIVE runtime wiring.
- Existing production `Risk Engine`, `AI Council`, and signal pipeline are unchanged.

## Gate

- compile: PASS
- focused unit tests: 6/6 PASS
- production wiring: NONE
