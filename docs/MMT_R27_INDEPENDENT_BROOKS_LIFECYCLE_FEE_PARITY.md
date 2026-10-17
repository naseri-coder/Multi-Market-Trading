# MMT-R27 — Independent Brooks V5 Hypothetical Execution and Futures Cash-Flow Cross-Check

**Status: NONPRODUCTION RESEARCH CODE ONLY — no exchange orders, no connected PAPER, no confirmed OOS edge, no `main` merge.**

## Scope and motivation

Stage21A runs the genuine SHA-frozen historical Brooks V5 strategy on the **earlier** closed 15-minute candle window and produces entry/stop/target geometry. It passes later candles **only** to a hypothetical next-open market/stop/target Stage16 economics model. Stage R26 validates signed-internal/hash-canonical Stage21A reports, but by itself does not recalculate the modeled price path or exchange cash-flow economics from original inputs.

R27 adds an independent **shadow verifier**, not an alternative strategy engine. It tests for agreement of two computations on a fixed, read-only research input. It cannot prove that next-open market fills reproduce Brooks's actual market-order, stop-entry, limit-entry or intrabar fill semantics. It explicitly refuses to certify actual broker fills, exact account-specific rates or historical realized PnL.

## New deliverables

- `naseri_markets/brooks_independent_lifecycle_economics_mmt_r27_v1.py`: `run_r27_brooks_two_pass_model_crosscheck` executes original Stage21A and then **re-runs the original frozen Brooks worker independently** on the same pre-signal closed bars, checking original source manifest, decision evidence, original replay SHA, independent snapshot hashes, decision-cutoff UTC and future candle SHA. Future bars are not shown to the worker for either pass.
- Independently reconstructs entry price using exact contract tick and adverse direction rounding; independently recalculates stop-first ambiguity, adverse stop opening gaps, first target cap and maximum 32 closed-bar horizon. Refuses mismatches in hypothetical trade/no-signal/entry-refused state, modeled entry or exit prices, quantity, event timestamps and exit reason.
- Independently recomputes gross USDT-linear PnL, assumed two taker fees, assumed adverse slippage and declared funding cash-flow from the **same metadata and declared funding/Mark tape**. Independently recomputed net must match Stage21A and the SHA-pinned original Stage16 economic model receipt; otherwise the audit refuses.
- `review_r27_independent_geometry_cost_parity` accepts original Stage21A input+receipt and independently replays source geometry/candles; existing R26 fail-closed report-shape audit runs first. No unauthenticated "trust me" field can set real broker fills or market source verification to true.
- New synthetic adversarial tests cover LONG and SHORT, simultaneous stop/target, TP cap, adverse opening gaps, maximum horizon, declared positive funding paid by longs, fee/slippage decomposition, no-signal, rejected entry, changed funding and metadata, re-signed tampered modeled receipts, causal future input drift and the Production/offline-only fence.
- A genuine frozen Brooks worker smoke calls the original V5 worker **twice** on synthetic closed OHLCV in a disconnected local subprocess. It is evidence of code execution, NOT any signed external dataset or exchange execution.

## Risk and evidence classification

| Question | R27 can establish | Still missing |
|---|---|---|
| Actual frozen Brooks V5 emitted a stable decision from unchanged earlier candles | Second worker run/source and decision SHA parity | Independent validated live trade order or fills |
| Stage21A hypothetical stop, entry, target and price tick match an independent observer | Yes, on admitted synthetic or historical OHLCV | Real order type, spread, queue, partial fills, liquidation, intrabar tick sequence |
| Stage16 modeled assumed fees, funding and slip are arithmetically consistent | Yes, under SHA-pinned **operator-asserted** metadata/tape | Actual account maker/taker tier, executed sizes/fills, exact venue funding settled via authenticated Mark |
| 2024 historical Binance original archives are retrospective source research | Existing Stage17/18/21B research documented | Cannot become genuine 2026 forward OOS merely by replay |
| Oct20–Nov3 2026 future candle sample confirms trading edge | NO; prospective study is **not yet started** as of Oct16 | Original first future-market observations, trusted independent receive-time/venue authenticity and statistical OOS sample |
| Live or connected PAPER account may place orders | NEVER approved | Separate real order-safety, broker authorization and independent evidence |

An independent arithmetic reproduction is not an independently authenticated third-party execution record. Both calculation paths share the same frozen market input and operator-supplied funding/fee metadata; correlated input errors therefore remain possible. Exact entry/exit semantics of the original strategy **are not certified** by selecting a next-open-market fill convention.

## Integration, security and acceptance

Stack this Draft PR on R26 Draft PR #319; no source changes to frozen Brooks V5, existing 2026-10-16 original FreeTSA-signed Oct20 prospective plan, Binance original Jan2024 archives, source timestamps or prior Research receipts. Run full public test corpus, Ruff, protected Publication Safety, real GitHub Advanced Security CodeQL and disposable/native PostgreSQL on the same SHA. Keep PR #309 as **DO NOT MERGE** main-target audit. No GitHub workflow introduced for R27 and no time-based background task enabled.

**Target:** `MMT_R27_INDEPENDENT_MODELED_EXECUTION_ECONOMICS_CODE_PASS — ACTUAL_VENUE_EXECUTION_AND_FORWARD_OOS_NOT_PROVEN`.
