# MMT-FIX-03 — Research runtime and code-quality ratchet

## Fixed defects

- **B-06:** `research_layer/run_research.py` used `Candle` without importing
  the canonical class; it also rendered raw-market volume using undefined
  `SYMBOLS`, `TIMEFRAMES`, and `RAW_CANDLE_LIMIT` variables.
- The report had invalid integer format specifiers that raised `ValueError`
  when it reached the knowledge snapshot counters.
- The report asserted fixed market instruments and a fixed historical coverage
  even when the offline extracts differed. It now uses `len(series)` and
  `sum(len(candles) ...)` from the supplied input, and describes data-quality
  limitations without claiming non-existent production database access.
- **B-05:** the no-new-debt Ruff CI ratchet now includes `naseri_markets/`
  and `research_layer/` alongside the existing scopes, and still compares
  against the exact PR base revision. Existing lint debt is not auto-fixed.

## Evidence required

1. Test a valid canonical Candle import and fail-closed invalid candle geometry.
2. Test final research report with zero and nonzero synthetic market observations,
   with no invented instruments or dates.
3. Test Ruff discovery of F821 undefined names within both new scopes.
4. Run `python scripts/ci_ruff_no_new_debt.py --base-sha <base-commit>`
   on a **clean checkout before tests materialize** the ignored `app/` and
   `migrations/` layout. Require `RUFF_NEW_FINDINGS=0`.
5. Run full nonproduction regression checks and required publication CI.
   Merge only when the required GitHub statuses report actual success.

## Deliberate exclusions / remaining report findings

- **B-15** (edge-case zero denominator in the *frozen* v0.3.2 regime
  algorithm), **B-07** (score rounding semantics) and trading-engine policy
  changes require a separate, versioned runtime release and policy tests.
  They are **not claimed resolved** by this PR. Do not mutate the historical
  Brooks `production_source/` or its 359-file signed-off manifest.
- **B-08:** network retries are **not** added to order execution without an
  explicit idempotency/reconciliation contract; blindly repeating orders is
  unsafe.
- The offline research path never authorizes live orders or Telegram
  publication. No production data, production server, or live broker is used
  to validate this PR.

## Security and interpretation

The Ruff ratchet prevents **additional findings**, not all existing debt.
The research report is observational; its counts are measurements of the
supplied extracts and do not demonstrate strategy profitability.
