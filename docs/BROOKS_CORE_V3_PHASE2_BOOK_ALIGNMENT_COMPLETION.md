# Brooks Core v3 — Phase 2 Book-Alignment Completion

## Scope

Phase 2 audited the operational Al Brooks pattern inventory and completed/refactored
missing or incomplete semantics without turning every named chart description into an
automatic signal. Session-specific patterns remain fail-closed when crypto snapshots do
not contain a defensible session anchor.

## Coverage

Canonical pattern catalog: 54 concepts.

- Trade candidates: 26
- Observations: 6
- Context-only: 15
- Semantic aliases: 1
- Session-required / fail-closed: 6

Rule-weight profiles changed from 25 in the Phase-1 baseline to 59 in Phase 2.
Added rule profiles: 34. Removed rule profiles: 0.
## Major semantic work

- Candle/signal-bar inventory: inside/outside, ii, iii, ioi, oo/oio, shaved,
  exhaustion, two/three-bar reversals, reversal-bar failure and ledge.
- H1/H2/L1/L2 retained; H3/H4/L3/L4 extended without replacing the old state machine.
- Wedge reversal separated from with-trend H3/L3 wedge-flag semantics.
- Double Top Bear Flag / Double Bottom Bull Flag separated from reversal semantics.
- Double Top/Bottom Pullback added as a distinct breakout-pullback/three-push family.
- Micro Wedge added with Always-In countertrend protection.
- Expanding Triangle implemented as a causal five-swing structure.
- 20-Gap and First MA Gap require trend context and valid trigger behavior.
- Triangle requires trading-range-like overlap, reducing trend false positives.
- Head & Shoulders is represented as a range/flag alias, not a magic reversal detector.
- Measured Move remains context/magnet evidence, not a standalone trade signal.
- Opening/day/gap-session patterns remain non-actionable without a session anchor.
## Test and regression gates

- Full unit suite: 646 passed, 0 failed, 2 subtests passed.
- Brooks/Phase7/Phase8 focused regression: 149 passed, 2 subtests passed.
- Former seven baseline failures were repaired by updating stale test contracts.
- Replay: BTCUSDT 15m, fixed end-time, 120 candles, 60-candle windows.
- Phase-1 and Phase-2 replay identity: same source period and 61 evaluated snapshots.
- Both replay versions remained 61/61 `NO_SIGNAL` under shadow safety policy.
- Live dry run: BTCUSDT / ETHUSDT / SOLUSDT 15m — PASS.
- Live dry run side effects: 0 publication calls, 0 DB writes, 0 exchange orders.

Replay changed setup classification specificity without changing shadow tradeability.
New specialized classifications included Double Bottom Pullback, Double Top Pullback,
Reversal-Bar Failure and L3 Wedge Bear Flag; several generic failed-breakout/failure,
range-fade and wedge-reversal classifications decreased accordingly.
## Production safety

- Docker Compose config: PASS.
- Application configuration: PASS.
- PostgreSQL application health check: PASS.
- Alembic: `20260902_0017 (head)` — PASS.
- PostgreSQL container health: `healthy`.
- Strict bot error scan: PASS.
- Temporary one-shot containers: 0 after cleanup.
- Final Phase-2 image contains 0 manual backup files.
- Risk Engine was not altered for Phase 2.
- Production AI Council was not altered for Phase 2.

Final Phase-2 image:
`sha256:40951f40248a22273a9b7d3fff1753884f5c5f6e414540a58313ebe7ae8dfe69`

The running LIVE bot was deliberately not restarted/cut over and remains on the
previous production image, so validation did not change live behavior.
