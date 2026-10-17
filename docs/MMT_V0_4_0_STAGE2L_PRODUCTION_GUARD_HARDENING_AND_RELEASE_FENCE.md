# MMT v0.4.0 — Stage 2L: system-wide production-flag guard audit and stable build fence

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate` / Draft PR #352  
**Release verdict:** `PRODUCTION_GUARD_BYPASS_FOUND__SIX_ENTRYPOINTS_FIXED__REMAINING_GATES_FENCED__REAL_STABLE_RELEASE_DENIED`

## 1. Actual source issue

R35–R38 and the stable Ed25519/Git-source auditors already deny the **presence** of `MMT_PRODUCTION`, regardless of its string value. Public package modules had weaker guards:

```python
os.environ.get("MMT_PRODUCTION") == "1"
environment.get("MMT_PRODUCTION") == "1"
```

These conditions fail to identify explicit `MMT_PRODUCTION=0`, `MMT_PRODUCTION=false` or empty assignment. This is a **real inconsistent fail-closed policy** across offline/PAPER runtime and release gates, not a simulated vulnerability.

GitHub connector review of all **226/226 real `naseri_markets/*.py` file bodies** against each committed Git blob identified approximately **73 additional distinct modules** retaining such value-only environment decisions (plus the six primary surfaces initially corrected). The flagged modules include adapter-free PAPER, Binance data intake, historical/live-feed evidence, Brooks backtest lifecycle, operator host/readiness tooling, offline/paper executors, native/certification checks, funding/reconciliation, runtime supervisor and stage-17→34 evidence paths. Some files contain **multiple** value-only decisions.

**Important compatibility dependency:** `naseri_markets/real_brooks_historical_stage15_v1.py` explicitly constructs an environment dictionary containing `"MMT_PRODUCTION": "0"` and also has a value-only guard. Any future mass migration to deny defined production variables **must review and remove such internally supplied false-valued flags** and rerun the actual PAPER/replay suites. Unreviewed mass automated rewriting was deliberately not performed without real Python3.12/full integration tests.

## 2. Six real executable entrypoints fixed

These source modules now use `"MMT_PRODUCTION" in os.environ` rather than a comparison to `"1"`:

1. `naseri_markets/installed_preview_smoke_v1.py`
2. `naseri_markets/installed_paper_pilot_stage10_v1.py`
3. `naseri_markets/unified_paper_pilot_stage20_v1.py`
4. `naseri_markets/paper_demo_cli_v1.py`
5. `naseri_markets/bot_admin_app.py`
6. `naseri_markets/brooks_paper_service.py`

The source changes are strictly **six 9-byte shorter presence predicates** (54 bytes total); no platform build version, strategy logic, default enabled modes, account access, DB, Telegram or broker configuration was altered.

### Mandatory source snapshot lock rebaseline

After those six fixes, fetched the exact **entire 226-file tree** from GitHub and updated `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` with the six new Git Blob SHAs, sizes and an unchanged 220-file remainder.

| Pin / property | New verified value |
| --- | --- |
| Source snapshot commit | `82cf544a2e714bc67afa03ee6fb91b03a99a07cc` |
| Public Python source tree SHA-1 | `46bf28c689a886e02b149dd31e86ad2daa25234e` |
| Public modules | **226** |
| Total source bytes | **2,501,470** |
| Independent snapshot lock SHA256 | `affde088b2639e8b4820ab1a19abbb5797d3243720faf2b7c9e11f5f02991076` |
| Snapshot Git blob SHA-1 | `0faa7564884935c758f5fc49db4e3758888d0e97` |
| Tree-to-snapshot per-file SHA+size consistency | **226/226 PASS** |

The previous Stage 2G snapshot SHA256 `c447806f659bb2e99837734feb7ca4620798a799cf4af164399c444d356a2de6` is historical and **must not be used as the current source lock**. The metadata RC→stable overlay SHA256 is unaffected because `platform_release/pyproject.toml` was not changed.

## 3. Independent AST release blocker added

`scripts/mmt_v040_production_guard_ast_audit_v1.py` is a pure, read-only Python `ast` scanner that detects comparing `MMT_PRODUCTION` to specific literal values through `os.environ.get`, `os.getenv`, a supplied `environment.get` mapping or bracket access, including reversed comparisons and some `!=` forms. It rejects invalid module syntax and returns only constant refusal codes with no credentials or file content.

**Crucially integrated into the existing release staging path** `scripts/mmt_v040_offline_stable_staging_v1.py`: after checking all exact source hashes, clean Git tree, RC metadata and AST syntax—but **before creation of any target build directory**—the stager scans every one of the 226 module byte strings. If **one** unsafe value-only production guard remains, staging refuses with `V040_PRODUCTION_VALUE_ONLY_GUARDS_DENIED:<count>`. The existing CLI catches this refusal and does not promote, sign, install or publish.

The scanner is deliberately a **conservative release blocker**, not a claim to prove the total absence of every possible dynamic unsafe production check. It will block the current source until the remaining value-only checks are repaired and full runtime regression acceptance follows.

## 4. Tests executed vs pending

Actual CPython **3.13.5** independent assistant sandbox, `pytest 9.0.2`:

- **13/13 PASS** AST scanner positive/negative tests for ordinary and reversed value comparisons, supplied environment mappings, `os.getenv`, safe membership checks, comment/string false positives, syntax errors and mixed safe/unsafe module sets.
- **100/100 PASS** existing Stage 2D–2J focused synthetic signing, 226-module fake Git/Wheel, RC→stable overlay, dual setuptools Wheel build and custody tests after integrating the new fail-closed scanner.
- **114/114 PASS in 24.20s** after adding a new strict integration regression: a **clean Git checkout** with a rebaselined **valid 226-module snapshot** but one remaining `MMT_PRODUCTION == "1"` check is refused before any stable staging directory is written.
- The GitHub copies of the final Python scanner, scanner tests, stable stager and stager tests were independently read back and matched the exact locally executed Git Blob SHA-1s:
  - AST scanner: `4f38a64c3486773d54ce3c078139830c874df6ac`
  - AST tests: `6776e0f7858257d35a3690b0f3a4fd67166576ed`
  - Stager: `66fa13502c39346c3a17d5dfd6319aa010251de4`
  - Stager integration tests: `dabf44e9dbead774623b797ced7f25a46307f51a`.
- **56 additional repository-bound entrypoint regression test cases** were committed in `tests/unit/test_mmt_v040_offline_entrypoint_production_flag_v1.py`. Real GitHub source text for all six module guards was re-read, and 6/6 new presence checks and 0/6 old value-only checks were verified. The **full 56-case test file has NOT been run against a complete local real-source checkout**, and must not be included in the 114 passed count.

**Not run:** actual complete 226-module project build/install on nonroot **CPython3.12**; Ruff, all-project pytest, real source reverse-dependency regressions, user PostgreSQL/PAPER restart/rollback, R35–R38/R42V full integration, final approved signer or source-to-real-Wheel attestation.

## 5. Blocking remediation in priority order

1. Fix remaining value-only guards with **module-specific behavioral tests**, not bulk search-and-replace; especially handle `MMT_PRODUCTION="0"` assignments in child environments, and preserve appropriate execution policy for supplied environment mappings.
2. Rebaseline source snapshot only after reviewed code changes, then run the strict AST staging fence and external Git source digest match on the final immutable branch SHA.
3. Obtain a full source checkout on a disposable **CPython3.12** nonroot runner; run all tests, pinned build-tool and Ruff checks, then build a real 226-module stable Wheel twice and prove its signed source/metadata/RECORD custody.
4. Validate OFFLINE/PAPER service shutdown, 32-cycle restart/recovery, PostgreSQL isolation, regression/rollback, signer trust and release notes. Only after approved exit gates may PR #352 become merge-ready.
5. **Do not merge** into protected `main`, create `v0.4.0` tag, touch Telmivo production server, start LIVE/orders or spend limited GitHub Actions quota until accepted.

**Overall:** `STAGE_2L_SECURITY_FINDINGS_AND_RELEASE_FENCE_COMMITTED__V0_4_0_RELEASE_BLOCKED`.
