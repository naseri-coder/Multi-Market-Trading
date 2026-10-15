# Stage 4 — Time-Purged Walk-Forward Audit for Strategy Research Lab

**NONPRODUCTION · OFFLINE / PAPER OUTCOME EVIDENCE ONLY · NO TRADING OR STRATEGY TUNING**

## Baseline and scope

This stage **extends** the existing Stage-11 read-only Strategy Research Lab. No parallel backtesting engine was added. Stage-11 remains authoritative for full population, account/core ownership, modeled cost and exit receipt validation, synthetic/offline provenance and report digests. The new optional `walk_forward` section is computed **only after** Stage-11 verifies its entire scoped evidence.

Files: `naseri_markets/research_walk_forward_v1.py`, an opt-in integration in `naseri_markets/strategy_research_lab_v1.py`, two CLI options in `scripts/mmt_research_lab_v1.py` and isolated/Stage-11 regression tests.

**Without `--wf-folds`**, the original Stage-11 report and SHA-256 must remain **byte-for-byte semantically identical** for the same evidence/protocol; all existing safety and data fences remain in force. No protocol schema change or automatic fold generation occurs unless the operator opts in.

## Frozen time windows and fold construction

Use the already predeclared protocol boundaries (all UTC):

- `[window_start_utc, training_end_utc)` — initial research training observations.
- `[training_end_utc, validation_end_utc)` — divided deterministically into 2–12 expanding-origin forward validation folds.
- `[validation_end_utc, window_end_utc)` — **reserved final holdout**, never included in any fold's training or validation population.

Each validation fold is a half-open chronological interval. Boundaries are computed in **integer microseconds**, eliminating floating time rounding, non-deterministic labels and gaps. For fold `i`, its training cutoff is `fold.test_start - embargo_seconds`; only trades **entered before that cutoff and whose CLOSED_PAPER outcomes exited before that cutoff** enter its training mean. Entries inside the embargo gap are counted separately. The prior validations may enter later fold training only after their outcomes are safely known. The final holdout can never train any fold, even when its R-values change.

A fold's test statistics similarly include only CLOSED_PAPER observations whose **exit** precedes that fold's test end. Records that cross boundaries are not silently dropped from the population: `cross_cutoff_exit` / `excluded_from_closed_metrics` are explicitly counted and yield blockers.

## Fail-closed decisions

- The protocol's original `min_closed_per_segment` is enforced independently for training and validation of **every fold**, plus the final holdout. No lowering the minimum after inspecting performance.
- Noncausal timestamps, duplicate/malformed order IDs, non-UTC dates, nonfinite realized R-values, invalid settings, out-of-window entries and wrong outcome types **refuse the entire Walk-Forward audit**.
- Incomplete and unfilled orders are retained in segment populations; incomplete outcomes are blockers. A validation closed trade exiting after test end is counted as cutoff leakage; a trade entering before the final holdout and exiting in the final holdout triggers `PRE_HOLDOUT_LABEL_CROSSES_BOUNDARY`.
- No confidence claim follows from passing minimums. Report readiness stays `DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF` and `prospective_holdout_verified=false`.
- Report SHA-256 includes the additional complete fold diagnostics when explicitly enabled. A deterministic audit digest covers the new section itself.

### Explicit methodological limitations

**This is a time-purged replayed-outcome audit, NOT a retrained, executable walk-forward backtest.** No strategy is refitted separately on training folds, no parameter search is performed, no daily market-data continuity or Point-in-Time candles are proven, no live broker fills are authenticated and no unseen forward return is certified. This is a safety-focused prerequisite for a separately approved genuine walk-forward research runner.

Stage-11 already reports full holdout metrics in its existing read-only report. Therefore this stage does **not** enforce blind analyst custody or trusted protocol freeze; the operator is explicitly warned not to use holdout metrics to choose parameters. External independently timestamped protocol registration, sealed holdout custody, true causal replay, embargo calibration to setup label horizon, provider-sourced historical data and real-cost sensitivity remain separate future requirements.

## How to invoke

The existing research-only Stage-11 CLI remains unchanged by default:

```bash
PYTHONPATH=. python scripts/mmt_research_lab_v1.py \
  --db /path/to/disposable/paper_stage9.sqlite \
  --protocol /path/to/predeclared_study.json \
  --ack-offline-research
```

To request the optional fold audit:

```bash
PYTHONPATH=. python scripts/mmt_research_lab_v1.py \
  --db /path/to/disposable/paper_stage9.sqlite \
  --protocol /path/to/predeclared_study.json \
  --ack-offline-research \
  --wf-folds 3 \
  --wf-embargo-seconds 86400
```

No file is written by the CLI; results are printed as one JSON object on stdout. A working Stage-9 SQLite research **copy**, with WAL accounted for, is required. No Production DB or server access is authorized.

## Acceptance tests

Tests verify expanding folds, deterministic timestamp boundaries down to microseconds, cutoff purging, embargo population counts, holdout isolation even when holdout R-values change, cross-split outcome blocking, insufficient sample refusal, incomplete/unfilled denominators, duplicate and invalid records, immutable frozen settings, Stage-11 default report parity and CLI negative/opt-in modes.

**Change boundary:** research-only code, tests, documentation, and opt-in CLI. No Production, source SHA manifest, market data download, unrelated strategy, risk gates, databases/migrations, Telegram, broker APIs, Docker, scripts/verify.sh, release manifests or deployment changes.

**Next stage is not authorized by completing this PR.** All protected GitHub CI must pass before merging this stage.
