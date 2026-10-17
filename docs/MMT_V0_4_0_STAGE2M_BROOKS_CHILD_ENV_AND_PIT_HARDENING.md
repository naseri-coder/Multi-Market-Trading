# MMT v0.4.0 — Stage 2M: Brooks and PIT production-flag migration

**Date:** 2026-10-17  
**Release branch:** `release/0.4.0-candidate`  
**Status:** `TARGETED_REAL_SOURCE_FIXES_AND_LOCK_PASS__GLOBAL_AST_GATE_STILL_BLOCKED__PY312_NOT_RUN`

## Why this stage mattered

Stage 2L established that the real project has numerous offline/PAPER components that wrongly treat only literal `MMT_PRODUCTION=1` as a production environment. This permits `MMT_PRODUCTION=0`, `false` and empty strings to bypass their local nonproduction admissions. A blindly automated search/replace could itself break the legitimate offline Brooks historical replay because the parent explicitly supplied `MMT_PRODUCTION: "0"` in a child subprocess environment.

This stage therefore migrates the coupled parent, subprocess and operator-facing Brooks surfaces as **one reviewed, constrained unit**, with no strategy, signal, trading, wallet, PostgreSQL, account or deployment changes.

## Changes applied directly to the real GitHub source

1. `naseri_markets/real_brooks_historical_stage15_v1.py`: parent nonproduction guard now rejects **any defined** `MMT_PRODUCTION`. Removed only the spurious `"MMT_PRODUCTION": "0"` from the deliberately whitelisted subprocess environment. The child still receives `MMT_NONPRODUCTION=1`, private temporary HOME, `PYTHONNOUSERSITE=1` and `PYTHONDONTWRITEBYTECODE=1`; neither broker execution nor the frozen Brooks V5 engine logic changed.
2. `naseri_markets/brooks_stage10_cli.py`: PAPER link/replay admission now requires `"MMT_PRODUCTION" not in environment`. Historical read-only `--status` and reconciliation routes deliberately preserve their existing branch/behavior; do not interpret this as an authorization of writes.
3. `naseri_markets/brooks_stage11_cli.py`: input-file PAPER replay admission now rejects any defined production flag in the caller-supplied environment mapping. The read-only diagnostics branch is unchanged.
4. `naseri_markets/brooks_stage12_cli.py`: read-only cohort assessment now requires the supplied environment mapping to **omit** the production flag.
5. `naseri_markets/brooks_termux_readiness_mmt_r23_v1.py`: readiness guard now rejects any defined production flag after the existing `_gate` check.
6. `naseri_markets/historical_pit_quality_stage12_v1.py`: offline Point-in-Time archive preparation refuses any defined production flag before disk/read/data work, retaining the existing operator acknowledgment.

No source files outside these six `naseri_markets/` files were changed during Stage 2M. Across these paths, GitHub Git blob SHA-1 identities were rechecked after upload.

## Bounded functional tests

New committed `tests/unit/test_mmt_v040_brooks_parent_child_production_v1.py` defines **39 parametrized checks**:

- 18 Brooks Stage 10/11/12 entrypoint checks (three real function bodies, six differently formatted defined production values); verify refusal before a PAPER/database or file-dependent branch.
- Six Stage 15 historical-review parent checks (six defined production values); verify refusal before the archive, source validation or subprocess.
- Six R23 Termux-readiness checks and six PIT archive checks (same six values).
- One isolated actual `_worker` function-body test using a mocked subprocess; verifies child environment contains `MMT_NONPRODUCTION=1` and **does not** contain `MMT_PRODUCTION`.
- One Stage 10 read-only `--status` branch preservation case.
- One AST assertion that the worker's literal `subprocess.run(env=...)` dictionary never adds a production flag.

**Actual execution in assistant's independent CPython3.13.5 sandbox:** `39 passed in 0.10s`. The isolated sandbox lacks a cloned full-source repository, so this local run used **faithful reduced copies of the selected function bodies**, not whole GitHub modules and not an installed Wheel. The committed test file is checkout-relative and will extract/execute the *actual* GitHub functions when a complete checkout is available. Its Git blob SHA-1 `7277ba1aa9f4781ab1bd35b96f9f5dead0abc986` matches the tested source bytes exactly. The existing full real-source repository suites and Python3.12 **have NOT run**. Do not claim the 39 fixture cases establish product integration safety.

Also reviewed prior repository tests for Brooks stage10/stage11/stage12/PIT/historical stage15; those had old tests for `MMT_PRODUCTION=1` and did not adequately cover `0` and `false`. This is an additive denial regression; prior positive paths that entirely omit `MMT_PRODUCTION` retain the same control-flow decisions.

## Re-pinned real 226-module Git source

GitHub immutable source commit after the six changes:
`657d9a66e93f749900d748b0444ab2a82c90437d`

Current `naseri_markets` Git subtree SHA-1:
`f21c9db96388765dd5f3829653cef8b5b9a60e19`

Committed `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` updated **exactly six** changed source entries; all **226/226** actual Git tree file hashes, paths and byte sizes again match the lock. Public source size: **2,501,373 bytes** (97 bytes smaller than Stage 2L). Its independently recomputed whole lock SHA256:

`9823877a252e330c125c6417a1d6f554f46efedc20d142354a27f8029f963534`

Snapshot Git blob SHA-1: `9856bff8418bfaf703e25ac60d975ed28b1cd0be`. Stage 2L's older tree and lock pins are superseded by these new exact snapshot values.

## Mandatory blockers, still enforced

- Roughly **70 other actual modules** retain value-only production guards; Stage2L's AST scanner **deliberately refuses any stable staging** until these are assessed and fixed. The Stage2M repairs do not authorize bypassing, disabling or relaxing this gate.
- Full source and tests have not been run locally on **CPython3.12**. The official distribution still declares `0.4.0rc1`, no genuine final complete user-source Wheel or independently trusted publisher signature has been released, and no supported environment has performed complete Ruff/R35-R38/R42V, PostgreSQL, PAPER restart/rollback acceptance.
- No changes were made to `main`, official `v0.3.2`, user production/Telemivo servers, live trading, GitHub Actions or official `v0.4.0` tag.

**Release verdict:** `NOT_READY_FOR_MAIN_MERGE_OR_STABLE_TAG`. Next: continue source-specific migration of remaining old-value guards (prioritize PAPER/intake and check child/test env contracts), audit the full 226-module AST fence, then perform actual complete CPython3.12 install/PAPER/regression acceptance before contemplating protected-main merge and official v0.4.0 tag.
