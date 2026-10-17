# Stage 20 — Frozen Brooks V5 Forward-Chaining, Withheld Final Holdout

**Status: NONPRODUCTION PRE-HOLDOUT DECISION-TRACE IMPLEMENTATION; NOT A REAL OOS OR PnL BACKTEST**

**Parent:** Stage19 Draft PR #302 at `1e030793d67a0693ee0286da2a4355a96ce1449f`.
This feature remains stacked on Draft #301 (Stage18) and Draft #300 (Stage17).
No production host, operational database, trading account, Telegram, frozen strategy source, SHA256SUMS, risk thresholds, public release or `main` changes are authorized.

## Why the stage cannot honestly claim independent OOS

Stage17 cannot currently acquire an official Binance Vision archive from this environment and local self-hashes are not cryptographic publisher attestation. Stage18's scheduled funding, historical mark, effective fee tiers, market-depth slippage, contract maintenance margin and liquidation proof are incomplete. Stage19 genuinely executes SHA-pinned original Brooks V5 decisions, but does not export actual filled and closed trade lifecycles or PnL. Also a retrospective full-month archive contains future holdout candles even if the worker receives only earlier candles. A SHA-256 of a newly created study plan is not independently timestamped precommitment.

**Therefore, there is no genuine prospective blind OOS or edge evidence in Stage20.**
The only defensible executable subset is frozen chronological decision replay before opening the holdout.

## Frozen protocol

Module: `naseri_markets/brooks_walk_forward_preholdout_stage20_v1.py`.

The `Stage20FrozenPlan` pins exact SHA-256 of (1) parent full Binance-format ZIP, (2) its canonical full-month CSV, (3) the Stage18 *raw bytes* economic report, and (4) original frozen Brooks V5 source manifest. It also binds a single explicit source window of 60–512 consecutive candles, source-window start, one train-close bar, one validation-close bar, a minimum 1-bar and maximum 48-bar embargo, and the **reserved** final holdout endpoint. At least 60 bars must have closed before first evaluation. Validation must be strictly after train + embargo, and reserved holdout strictly after validation + another embargo.

Example **synthetic** plan, with all bar indices relative to the start of the selected window:

| Phase | Example bar indices | Worker evaluation |
| --- | --- | --- |
| Training context | 1–60 | Brooks V5 decision at close of bar 60 |
| First embargo | 61–62 | No decision used |
| Validation | 63–72 | Brooks V5 decision at close of bar 72 |
| Second embargo | 73–74 | No decision used |
| Final reserved holdout | 75–100 | **NOT EVALUATED** |

The example is illustrative. No parameter fitting occurs in training; the pre-existing Brooks policy is immutable. Two chronological decisions are not a statistically meaningful walk-forward profitability experiment.

`freeze_stage20_plan(plan)` returns deterministic canonical JSON and SHA-256. An externally recorded, independently approved digest is **required** when running `run_stage20_preholdout` to detect post-precommit changes. However, this check alone does not prove the external approval occurred before outcome inspection; the output explicitly reports `independent_plan_precommitment_attested = false`.

## Causal implementation

- Original Stage17 capture and Stage16 full reviewed window must match frozen source hashes, expected start/count, economics byte digest and re-derived data bytes.
- Stage20 derives a fresh **pre-holdout prefix** ending exactly at validation bar 72 (in example). The prefix must have an exact local CSV whose bytes are verified before any worker call.
- Calls existing Stage19/15 genuine, SHA-frozen original Brooks V5 on *only* the train and validation closed-bar cutoffs. Holdout candles are NOT sent to the worker; Stage19 receives only the prefix, not the complete 100-bar research window.
- Records two actual decisions `NO_SIGNAL`, `LONG` or `SHORT`, original evidence hashes, embargo/holdout indices and deterministic report hash.
- Records `holdout_engine_evaluation_performed=false`, `strategy_refit_or_selection_performed=false`, `economic_trade_pnl_calculated=false`, `pristine_prospective_oos_verified=false` and `live_authorized=false`.

This is **pre-holdout forward-chaining decision replay**, NOT full walk-forward refitting or independent blind holdout evaluation. Stage20 deliberately provides no `open_holdout()` API. Do not invent one or use the currently visible retrospective archive as a pristine future sample.

## Minimum conditions for genuine future OOS acceptance

1. Obtain separately reviewed real exchange trade-price history, retention and revision provenance; independently witness timestamps and freeze data/split membership before candidate results.
2. Freeze a genuinely *future* holdout before it becomes observable and capture it prospectively later; ensure no parameter, universe, model or execution rule changes after precommitment.
3. Review an actual Brooks geometry-to-entry/stop/target, next-bar trade entry, fill, stateful position lifecycle and complete exchange fee/funding/mark/margin/liquidation model with conservative adverse execution.
4. Include a sufficiently large set of closed trades and statistically defensible walk-forward folds. Correct for repeated selection and serial dependence. Separate training, validation, embargo and holdout, and account for costs, outages and missing observations.
5. Only then calculate OOS returns or profitability metrics. No claim of edge or future returns without independent evidence.

## Test evidence and constraints

`tests/unit/test_stage20_brooks_walk_forward_preholdout_v1.py` generates a synthetic full-month Binance-format ZIP and a mocked HTTP response, runs the actual Stage17 data quality, Stage18 synthetic economics, Stage16 deterministic window, Stage19/15 frozen Brooks child worker, and checks that only the 72-bar *prefix* reaches it while the 100-bar original final holdout stays unqueried. Additional tests reject plan digest drift, forged future study windows, SHA mismatches, modified local prices, invalid split geometry, missing approval and any Production mode. The entire `tests/unit` public test corpus already covers this test module on PRs.

**Acceptance is limited to CI code integrity, not real-world performance.** Do not bypass CodeQL or the companion publication gate if CodeQL is missing on stacked PRs. Keep PR Draft and unmerged. No Stage21 activation, PAPER mode or real orders.
