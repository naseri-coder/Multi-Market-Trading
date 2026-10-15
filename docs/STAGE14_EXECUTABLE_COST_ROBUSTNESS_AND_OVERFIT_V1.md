# Stage 14 — Cost Robustness + Experiment Inventory + Segregated PBO/DSR

**MODE: NONPRODUCTION OFFLINE RESEARCH ONLY. NOT MARKET PROFITABILITY EVIDENCE. NEVER AUTHORIZE LIVE ORDERS OR PUBLICATION.**

## Baseline and new actual contribution

Authoritative parent: `main@9e47d60aaf110a4bdfdc1dde687995b6dfacca4d`.

Previously implemented and unchanged:

- Stage 13 `executable_walk_forward_stage13_v1.py` **executes** a trusted internal synthetic contract fixture on chronological, DATA-A1-pinned historical candle bars. Each training/test segment is newly evaluated, with a next-open fill model and a reserved final holdout. It is **one fixed strategy candidate**, not a fitted strategy sweep. The dataset provider and archive acquisition clock have not been independently authenticated.
- Stage 5 `research_overfit_diagnostics_v1.py` already implements combinatorially symmetric cross-validation PBO and Deflated Sharpe Ratio. It correctly **requires a complete, synchronized series of portfolio net-period returns for 3–16 independent candidates**, explicit selected candidate, complete trial inventory and no final holdout bins. Per-trade R, a single strategy's profits, or four cost scenarios of the **same** strategy cannot be substituted.
- Stage 4 `research_walk_forward_v1.py` is an offline *post-hoc PAPER outcome audit* and not a separately fitted executable backtest.

Stage 14 adds a narrowly scoped `run_stage14_robustness` method without changing any existing engine, validator, broker adapter, trial-selection logic, database schema or package entrypoint.

## 1. Strict experiment manifest

Input is one complete, bounded `protocol_bytes` JSON, SHA256-pinned separately as `trusted_protocol_sha256`. The top-level keys are fixed:

- `schema_version`: literal 1; `experiment_id`: validated bounded ASCII identifier.
- `core_id` and `core_version` must EXACTLY match the internal trusted `OfflineContractFixture`. No owner-only, private, unknown, reference-only or arbitrary third-party core may be silently substituted.
- `dataset_sha256` must match the already validated `HistoricalFileSpec`.
- `execution_plan_sha256` = the existing `core_api_v1.content_digest(FrozenExecutionPlan)`. It freezes all parameters, including timing, baseline fees, slippage, notional, capital, embargo and minimum count.
- `baseline_execution_evidence_sha256` must match the full **actually re-executed** Stage-13 baseline output. It detects scenario/test or source drift, not preregistration.
- `claimed_preoutcome_freeze` must be literal true. **This is only an operator claim**. The system has no trusted external pre-outcome timestamp or third-party signature. A baseline hash often can only be obtained after a baseline run, so do not interpret this boolean as evidence the trial design was preregistered.
- `stress_case_ids` must exactly equal `["baseline","fee_2x","slippage_2x","joint_2x"]`. Omission, reordering and unreported stress cases fail closed.
- `external_candidate_ids`, `selected_external_candidate_id`, `external_matrix_sha256` and `claimed_complete_external_trial_inventory` must either all describe a coherent, complete multi-candidate *external* matrix or be the explicit empty/`null`/`false` case. A valid external matrix must be provided in full when declared, and vice versa.

The fixed four-case grid is **not hyperparameter optimization** and never selects the scenario giving the highest profit. All stress cases use the identical pinned dataset and Stage-13 core/plan, and only the two execution-cost multipliers change. Per-side base fee/slippage must be at most 50 bps so 2× remains within Stage-13's original strict 100-bps cap.

## 2. What the robustness report measures

| Predeclared case | Fees | Adverse slippage |
| --- | --- | --- |
| `baseline` | 1× | 1× |
| `fee_2x` | 2× | 1× |
| `slippage_2x` | 1× | 2× |
| `joint_2x` | 2× | 2× |

Every case **re-executes the real Stage-13 Core API fixture** and records the full Stage-13 execution digest, validation-fold closed counts, pending/unresolved trades, per-fold net PnL, mean net R and digest of modeled trade receipts. A deterministic Stage-14 hash commits to every case, the complete case inventory, flags and any refusals/blockers.

The runner flags:
- Any Stage-13 execution blocker (insufficient count, invalid next-open geometry, unresolved open/pending trades) **in any case**.
- A different number of validation closed trades between a stress case and baseline. This is reported as scenario path divergence, not manually cherry-picked.
- Higher reported validation PnL with more expensive fills/fees. This is an economics sanity warning, not proof that a monotonic PnL ranking always holds under nonlinear sizing, constraints or changing fills.

`baseline_execution_evidence_sha256` is checked after all four executions; a mismatch refuses rather than post-selecting a more favorable dataset or plan. This evidence is descriptive. There is no PnL-motivated threshold tuning, no selection of best symbol or cost case, and no margin/funding, liquidation or market impact certification.

**IMPORTANT: the Stage-13 runner itself computes the final holdout for every one of the four stress runs.** It therefore is *not blind/prospectively sealed*. Stage 14 reports holdout counts and digests, not stress holdout PnLs, but `holdout_exposed_during_repeated_stress_runs=true` and `blind_final_holdout_preserved=false`. Do not reuse this holdout as an untouched statistical confirmation later.

## 3. Separate external PBO / DSR — no misleading linkage

If the operator supplies a **complete independent multi-candidate** matrix, `run_stage14_robustness` delegates *without reimplementation* to `analyze_overfit_fixture` in the existing Stage-5 module. The matrix must pass original strict checks for synchronized equal-duration periods, all candidate net return fractions each period, 3–16 alphabetically ordered unique IDs, selected ID, exact declared trial count, ≥8 rows per CSCV block, no holdout returns, nonfinite rejection, PBO combinatorial sampling and DSR sample/skew/kurtosis calculations.

The optional external matrix's SHA256, selected ID and candidate inventory must match the separately frozen Stage-14 protocol. The output nests these diagnostics in `external_matrix_overfit_diagnostics`, with `stage13_fixture_attribution_allowed=false`, `source_authenticated=false` and `ready_for_profit_claim=false`. The external matrix is not economically or cryptographically matched to the single Stage-13 fixture and CANNOT certify its Sharpe, PBO, DSR or actual trading results.

If no valid external matrix is present, **PBO and DSR are NOT computed**. Neither mean net R nor the fixed cost cases are mislabeled as independent strategy returns.

## 4. Safety and technical limits

- Requires `operator_ack=True`, `MMT_NONPRODUCTION=1` and not `MMT_PRODUCTION=1`; no production server, data download, private code, trading config, broker, Telegram, strategy optimization, asset filtering or database writes.
- Uses Stage-12 local archive checks: **provider source, continuous-market assertion, contract type and acquisition clock are operator supplied and not independently attested**.
- All prices, returns and fees in Stage-13 are illustrative spot cash-notional modeled values on synthetic research fixtures, not actual bid/ask/depth/market impact or leverage economics.
- An SHA-256 of a self-created manifest is not independent timestamped experiment registration. `trial_inventory_independently_attested=false` and `claimed_protocol_freeze_independently_attested=false` always.
- A positive stress summary does not establish significance, absence of serial correlation, independent out-of-sample results, genuine robustness to all untested scenarios, real strategy profitability or deployability. PBO/DSR source does not currently adjust for time-series serial dependence.

### Reproducibility API

```python
from naseri_markets.core_api_v1 import content_digest
from naseri_markets.research_robustness_stage14_v1 import run_stage14_robustness

# First compute the Stage-13 baseline in a controlled local research
# session, and assemble a COMPLETE, separately host-pinned manifest with
# its resulting full report evidence SHA and content_digest(frozen_plan).
report = run_stage14_robustness(
    pinned_absolute_archive_path,
    reviewed_stage12_historical_spec,
    receipt_bytes=reviewed_stage12_archive_receipt,
    trusted_receipt_sha256=archive_receipt_digest,
    plan=frozen_plan,
    protocol_bytes=reviewed_complete_experiment_manifest,
    trusted_protocol_sha256=experiment_manifest_digest,
    external_matrix_bytes=None,  # stage13 one-candidate → no PBO/DSR
    operator_ack=True,
)
assert report["actual_executable_core_trial_count"] == 1
assert report["stage13_single_core_pbo_dsr_applicable"] is False
assert report["profitability_proven"] is False
```

CI acceptance: four-file scope only: new Stage-14 module, tests, independent GitHub workflow, documentation. Focused tests include Stage 13, Stage 5 PBO/DSR numeric regression and Stage-12 quality; full Public Corpus, Full Corpus/PostgreSQL, publication and legacy build gates must pass on exact final PR head. No modifications to Stage 13 economic fill model or installed release.

**Stop after this stage.** Production, public release, activation of Brooks/NY First-Reversal, real exchange backtest and next-phase data acquisition need separate authorization.
