# R42-V — pinned Python 3.12 + Ruff offline runtime acceptance gate

**Date:** 2026-10-16. **Scope:** R42-V acceptance tooling ONLY, no strategy, feed, broker, installed PAPER, public signals, marketplace, or release authorization.

**Parent:** R42-VH Draft PR #339, exact reviewed commit `a3686c13699e52a026c06c4e97fdf5ff3304d8d3`.
**Status:** `R42V_PINNED_RUNTIME_GATE_CREATED_PY312_RUFF_ACCEPTANCE_PENDING`.

## Why this exists

Independent Python 3.13.5 synthetic test success is not Python 3.12 runtime compatibility. The isolated assistant host contains Python 3.13.5, pytest and coverage, **but no Python 3.12 binary or Ruff**. `uv python find 3.12 --offline` returned **No interpreter found**. Network access to GitHub is disabled inside this testing container; no operational server or GitHub Actions were used. The product's R42 nonproduction-source security assertions remain deliberately unpromoted.

A small, standard-library-only driver has therefore been added:
`scripts/mmt_r42v_pinned_runtime_acceptance_v1.py`.

It is **not** a broker integration or release switch. It only allows a future independently qualified nonroot Linux Python 3.12 checkout to execute the exact reviewed R42 module, its existing tests, and this gate's negative tests, after independent provenance and tool verification.

## Guard sequence (all must pass)

1. Require an explicit absolute, non-symlink checkout, `--ack-offline-only`, `MMT_NONPRODUCTION=1`, `MMT_PRODUCTION` unset, and a nonroot UID.
2. Require exact SHA-1 Git blob **and SHA-256** of these three files before running Python tests:
   - `scripts/mmt_r42_offline_market_account_evidence_v1.py`: Git blob `070c56bd8774372c40bb61f8316c92988e8c9b35`.
   - `tests/unit/test_mmt_r42_offline_market_account_evidence_v1.py`: Git blob `eab305facdc6ce9406f3a488a602f2b5b62a1b19`.
   - `tests/unit/test_mmt_r42v_pinned_runtime_acceptance_v1.py`: Git blob `ae7ec4f16caf89e9c2dcfc564f9faa9b75874a6a`.
3. Source-only mode returns exit **3**, `R42V_SOURCE_ONLY_NOT_ACCEPTED`, with explicit `python312_accepted=false`; it **never** launches pytest/ruff.
4. Runtime mode requires **actual CPython 3.12** and installed `git` and `ruff`; rejects Python 3.13/3.11 even if compatible syntax.
5. Require real Git HEAD to descend from the frozen reviewed parent, and the checkout to be clean.
6. Run `ruff check --isolated --no-cache --select E4,E7,E9,F` over the reviewed script, both test suites and the new runner. Then run both committed test suites with `sys.executable -X dev -W error -m pytest`, external plugin autoload disabled, exact expected count **59**.
7. Exit 0 only with the narrow result `R42V_BOUNDED_PY312_TEST_LINT_PASS_NOT_RELEASE`. All live/public/real-provider/installed-PAPER approvals remain false. This result **cannot waive Stage15 P0/P1 blockers**.

## Actual independent execution on 2026-10-16

This section documents **real performed actions**, not hypothetical Python 3.12 acceptance.

- Original R42 Git blobs were reverified against the PR #339 versions, unchanged:
  - auditor SHA256 `d4d1aebca64bf81977f5ee5f60cfc1d3833fa2008551378ec8e86916ffdd953d`.
  - original test SHA256 `89eda2c803415e129deaf705cbf5ca60c2053b287b801c0735783568165d420f`.
- New gate source and test blobs byte-matched independent local files tested with **Python 3.13.5 / pytest 9.0.2**:
  - gate source SHA-1 `8b3c2793ef2fe168013c214374d1101625177d39`, SHA256 `a24928725fe5cb53ef93953c7208bd47d0b83a3f0c778dd26ed1dd5b9069a188`;
  - gate tests SHA-1 `ae7ec4f16caf89e9c2dcfc564f9faa9b75874a6a`, SHA256 `dffef2f52bb52794e04d73eedc27cc38f2b7b041531b6ebeb991f589d7e9e5e6`.
- **59/59 executed synthetic pytest cases passed** under strict `-X dev -W error` without third-party plugins. Same result repeated using an independent nonroot UID 1000, 0.16s.
- Python 3.12 syntax-grammar AST parsing of the two newly authored Python files passed on the installed Python 3.13 interpreter. **This is grammar only, NOT a Python 3.12 runtime execution.**
- Source-only CLI checked all three pins and returned **exit 3**, explicit release denial.
- Normal runtime CLI under Python 3.13 returned **exit 2**, `R42V_REAL_PYTHON312_REQUIRED`, explicit release denial.
- An additional one-off adversarial value/type sweep over **792 synthetic single-field mutations** of the existing four evidence documents produced **787 structured refusals**, **5 legitimate accepted variants** (equal schema values or shorter but valid freshness bound), and **0 unhandled exceptions**. This sweep is separately run exploratory evidence, not a committed parameterized test or coverage certification.

## Still OPEN

| Acceptance gate | Outcome |
| --- | --- |
| R42 synthetic core (51 original) + new source-gate negatives (8) on Python 3.13.5 | **59 PASS, actual** |
| Nonroot + fail-closed Python 3.12/Ruff preconditions | **PASS, actual negative checks** |
| Python 3.12 runtime pytest of 59 cases | **PENDING: interpreter unavailable** |
| Actual Ruff process | **PENDING: Ruff unavailable** |
| Full repo/clean Wheel installed-PAPER journey | **PENDING: no full checkout/host acceptance** |
| R41 rootless/gVisor hostile-host acceptance | **PENDING** |
| Authentic feed and remote account or venue eligibility | **NOT VERIFIED** |
| Stage15 nine P0 plus one P1 product blockers | **OPEN** |
| Public release, Telegram delivery, LIVE, Production, main Merge | **HARD DENY / NOT PERFORMED** |

The driver deliberately does not download dependencies, install Python, spend GitHub Actions quota, access Termux, or contact the user's online Telmivo service. Complete independent Python 3.12 execution when a separately approved environment is available. Never label this step `PRODUCT_READY`.
