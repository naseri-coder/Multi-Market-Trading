# Multi Market Trading — Stage 11 / Universal Strategy Research Lab V1

**Baseline:** `main@be30188c55544e415d11f3b4d0820c712d497457` (Stage 10).  
**Scope:** additive, research-only/offline, nonproduction. Not a one-year historical market backtest, profitability certification, price downloader, strategy optimization, live broker reconciliation, or Telegram publication.

## 1. Purpose and relationship to the existing code

Stage 3 defines strategy data/decision contracts; Stages 5–7 emit and evaluate offline market events; Stages 8–9 provide a simulated-account risk ledger and a deterministic PAPER lifecycle; Stage 10 tracks signal state separately. Stage 11 now provides a **strategy-neutral, independently read-only analysis** of completed Stage-9 outcomes, preserving Stage-8 account/core/binding ownership and full-population coverage. It **reuses** the existing Stage-9 modeled exits and does not implement another trading or exit engine.

The pre-existing `naseri_markets/brooks_stage12_research_audit.py` remains a separate Brooks-specific verifier. The new module can study any compatible core instance and does not duplicate/change Brooks study policy.

### Files

- `naseri_markets/strategy_research_lab_v1.py` — validated predeclared research scope, read-only Stage-8/9 ledger joins, exact modeled cost/exits checks, descriptive metrics, deterministic evidence/report digests.
- `scripts/mmt_research_lab_v1.py` — explicit opt-in offline CLI: stdout only, never writes its own report or alters research evidence.
- `tests/unit/test_strategy_research_lab_v1.py` — fixtures and negative security/integrity tests. All test market data is fabricated solely as **synthetic examples**, never claimed historical.

## 2. Research contract

The operator supplies a protocol JSON and a **separately prepared, disposable** Stage-9 SQLite database. Protocol keys are exact; no unsupported flags are silently ignored:

```json
{
  "schema_version": 1,
  "study_id": "sample_one",
  "core_id": "examplecore",
  "instance_id": "instance_a",
  "account_id": "account_a",
  "window_start_utc": "2026-01-01T00:00:00+00:00",
  "training_end_utc": "2026-03-01T00:00:00+00:00",
  "validation_end_utc": "2026-05-01T00:00:00+00:00",
  "window_end_utc": "2026-07-01T00:00:00+00:00",
  "expected_order_ids": ["order_1", "order_2"],
  "dataset_origin": "synthetic_fixture",
  "declared_dataset_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "initial_equity": "1000",
  "min_closed_per_segment": 20,
  "claimed_protocol_frozen_before_outcomes": true
}
```

All timestamps must be explicitly UTC-aware, split boundaries strictly ordered, and the window no longer than 400 days. `min_closed_per_segment` is the precommitted *reporting* sample minimum, not a PnL-driven threshold. Each `expected_order_id` must match the exhaustive scoped Stage-9 population — missing, added, modified or duplicate identities are refused. Stage-8 decisions with no Stage-9 plan are separately counted as a **blocker** even when their timestamps cannot be independently assigned to the research window. A zero-sample study produces no performance inference.

The `claimed_protocol_frozen_before_outcomes` flag is **merely an operator assertion**, not proof of registration date or an untouched holdout. Similarly, `declared_dataset_sha256` is an operator claim, not cryptographic attestation of an exchange source. The module creates an additional digest of exact ledger records actually read (`evidence_sha256`) and of the canonical result (`report_sha256`) for reproducibility. A proper independent temporal registry and trusted dataset attestation are future work.

## 3. Full-population evidence and anti-cherry-pick gates

For every included Stage-9 plan, the analyzer matches:

- Stage-8 order ownership (`paper_core_orders`), manifest/binding digests (`paper_core_bindings`), decision identity (`paper_core_decisions`), and core-instance allocation (`paper_core_allocations`).
- Stage-3 order snapshot (`paper_orders`), account policy (`risk_accounts`) and canonical symbol/market/timeframe.
- Stage-9 entry close time, matching exit action records, each bar digest and each bar's serialized exit receipt.
- The Stage-9 modeled gross equation and **exact configured modeled roundtrip fee + slippage fraction**, with `net = gross - cost`.
- Accumulated exit quantity equals the order's closed quantity; open/unfilled/partially closed orders are explicitly counted rather than labeled losers or discarded.

A CLOSED PAPER trade must have positive filled quantity, no remaining open quantity and one or more matched exits. Missing joins, malformed/nonfinite prices, forged receipts or inconsistent quantity/costs **refuse the study**. There is no silent filtering of winning symbols or cherry-picking signal IDs.

## 4. Research partitions, chronology and metrics

- Chronological **training**, **validation** and **holdout** are three adjacent half-open intervals `[start, end)`. Attribution is based on the entry-decision's Stage-9 `input_close`, not on PnL.
- If the last recorded exit falls into another partition, the study reports `CROSS_PARTITION_EXIT_LEAKAGE`, never pretends a holdout was untouched.
- Statistics per partition, for the aggregate, and per setup: total population, CLOSED, unfilled, incomplete, cross-boundary exits, winners, losers, breakeven, win rate, mean/median net R, gross/cost/net modeled PnL, profit factor, and **predeclared double-cost stress**.
- CLOSED-trade equity curve: starts from provided initial equity and adds each *completed* trade's net PnL in exit-time order. The reported maximum drawdown is a **closed-trade-only drawdown**; it explicitly excludes intratrade mark-to-market, overlapping exposures, financing and capital movements.
- Profit factor is `null` if there are no recorded losing trades; this never indicates infinite real profitability.
- Every report has `readiness=DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF`, `independent_provider_data_verified=false`, and `prospective_holdout_verified=false` even if all paper statistics are positive.

## 5. How to run (nonproduction fixture only)

From the project root with appropriate unit test dependencies:

```bash
python -m pytest -q tests/unit/test_strategy_research_lab_v1.py
PYTHONPATH=. python scripts/mmt_research_lab_v1.py \
  --db /path/to/disposable/stage9-paper.sqlite \
  --protocol /path/to/frozen-study.json \
  --ack-offline-research
```

The CLI writes a single JSON report to stdout. Redirect to an independently controlled results file if desired. It has **no** live market API, credentials, broker, network, Telegram send/edit, strategy import, or dataset download. SQLite uses `mode=ro`, `PRAGMA query_only=ON`, and one snapshot transaction. It is not intended for the live production database; prepare a separate consistent backup **with WAL accounted for**. A failed audit returns a refusal code and no partial success JSON.

## 6. Out-of-scope work, required for genuine backtests

1. Acquire and license real historical candles/ticks from each provider. Authenticate source, time range, gaps, data revisions, market sessions, contract multipliers, adjusted price basis and cost schedules; freeze a verifiable dataset digest.
2. Run the same Stage-3 strategy algorithm causally through Stage-5/7 dispatch and Stage-8/9 risk/position simulation, capture **all** candidate setups including no-signal events and bar continuity, and apply predeclared event-trigger and order-fill rules.
3. Independent holdout pre-registration, walk-forward reproducibility, multiple-hypothesis controls, bootstrap uncertainty and model sensitivity, plus reproducible real-data logs.
4. Integrate with the user-facing core passport and research UI only after evidence passes; PAPER/DEMO/LIVE must retain separate PnL ledgers.
5. Confirm Stage-4 hostile plugin isolation before unknown third-party code is executed; CI unit tests are not container security attestations.

**Verdict applies only to implementation, tests and merge:** `STAGE11_RESEARCH_LAB_NONPRODUCTION_PASS` if CI verification and merger are successful. **No actual historical study or profitable strategy is certified by this stage.**
