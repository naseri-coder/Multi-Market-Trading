# Brooks Core v3 — AI Council Roadmap Stage

## Position

This stage follows Trader's Equation in the shared Brooks Core v3 roadmap and precedes
Execution Planner. It is intentionally isolated from the existing production AI Council.

## Design

The v3 council is threshold-free and audit-first. It consumes explicit reviewer opinions
and reports only deliberation state:

- `UNANIMOUS_SUPPORT`
- `UNANIMOUS_OPPOSITION`
- `SPLIT`
- `UNRESOLVED`

It does not expose `approved`, `score`, `final_score`, `confidence`, or a trade decision.
Reviewer IDs must be unique and every opinion must carry a basis and reasons.

The Trader's Equation adapter maps favorable/unfavorable/marginal-or-unresolved math to
SUPPORT/OPPOSE/ABSTAIN without adding new probability or scoring logic.

## Safety

- No production AI Council modification.
- No numeric voting threshold.
- No automated approval/rejection.
- No DB, Telegram, chart, PAPER/LIVE, or exchange wiring.
- `publication_allowed` is always false.

## Gate

- compile: PASS
- focused unit tests: 9/9 PASS
- production wiring: NONE
