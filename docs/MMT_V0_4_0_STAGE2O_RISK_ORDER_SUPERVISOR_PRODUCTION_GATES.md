# Multi-Market-Trading v0.4.0 — Stage 2O: risk/order/supervisor production gate hardening

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate`  
**Gate:** `EIGHT_REAL_SOURCE_PRODUCTION_CHECKS_HARDENED__OFFLINE_GUARD_TESTS_PASS__STABLE_PUBLICATION_DENIED`

## Scope: actual changes already committed

Stage 2O hardens exactly eight public operational entrypoints. Each replaces the old value-only admission check `os.environ.get("MMT_PRODUCTION") == "1"` with the stricter `"MMT_PRODUCTION" in os.environ`, so a defined variable with value `0`, `false` or an empty string no longer bypasses the nonproduction guard:

| Real public Python module | Function / guard |
| --- | --- |
| `naseri_markets/mmt_r30_offline_risk_order_preflight_v1.py` | R30 offline pre-order risk preflight `_fail(...)` |
| `naseri_markets/brooks_future_shadow_paper_mmt_r29_v1.py` | Shadow PAPER `_gate` |
| `naseri_markets/paper09_snapshot_v1.py` | PAPER snapshot `_consent` (also retains nonroot denial) |
| `naseri_markets/paper_contract_economics_stage21d_v1.py` | Contract economics research acknowledgment |
| `naseri_markets/signed_public_intake_stage27_v1.py` | Signed public candidate intake |
| `naseri_markets/offline_runtime_supervisor_v1.py` | Offline runtime supervisor constructor |
| `naseri_markets/mmt_r28_unified_offline_runtime_v1.py` | R28 unified offline runtime gate |
| `naseri_markets/runtime_supervisor_health_v1.py` | Supervisor health/read-only queue inspection |

These were verified by fetching the **actual GitHub source bodies** (not just filenames) from the release branch, inspecting the gate context and observing exactly one presence predicate and zero old `== "1"` predicates per module. They are **not** an assertion that every function in these modules has been integrated/installed/tested.

Stage 2N, immediately preceding this stage, changed a separate eight genuine intake/PAPER/recovery modules with nine corresponding guards. Both stages preserve the existing opt-in `MMT_NONPRODUCTION=1` policy; no new server, broker integration, live authorization or database migration was introduced.

## Auditable real Git source inventory

- Current package public subtree Git SHA-1: `499e278950abfc67a44ab284d2edb276f33ab6ee`.
- Current source snapshot baseline commit: `3c5b1b2f68638039617cb521d65a379e4276ae1f`.
- The separately committed `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` tracks exactly **226** Python source modules and **2,501,220 source bytes**.
- On 2026-10-17, the latest release branch's Git tree and JSON lock were read back: exactly **226/226** public file paths, Git Blob hashes and byte sizes matched and the `naseri_markets` subtree SHA agreed. The lock is newer than the Stage 2M and Stage 2N locks; older snapshot pins must not be reused as final release evidence.

## Tests actually run in the independent assistant container

The sandbox exposes Python **3.13.5** and `pytest` but **not** Python3.12/Ruff or a cloneable full project GitHub checkout. It contains limited, prior-stage extracted entrypoint fixtures. Re-executed:

```text
tests/unit/test_mmt_v040_stage2n_entrypoint_guard_v1.py:
  81 passed in 0.12s

tests/unit/test_mmt_v040_stage2o_order_supervisor_admission_v1.py:
  74 passed in 0.14s
```

The test-source files in the independent sandbox are byte-identical to the currently committed GitHub files; their exact Git Blob SHA-1s are:

- Stage 2N tests: `82ed4c597603622a194628a19d7433c0b6822d03`
- Stage 2O tests: `1fa24023a15b68ab25b5b3289b3ac5ff79312003`

**155/155** focused **AST-isolated admission** assertions passed across the two suites. Stage 2O checks all six defined production values (empty, 0, 1, false, FALSE, no), positive absent-production + explicit nonproduction, absent acknowledgment denial, retained nonroot refusal for PAPER snapshots and exactly one entrypoint gate for each of the eight module fixtures.

**Crucial limits:** the isolated fixtures contain accurately modeled original guard logic but **not all of the original module source**. The actual eight GitHub file bodies were inspected separately and each was found to have the intended presence policy. This is **not a passing full project test**, genuine source build, PAPER execution, R35–R38/R42V integration, PostgreSQL/rollback verification, or independently attested source→Wheel proof.

## Remaining mandatory release gates

1. **Additional value-only `MMT_PRODUCTION` guards still exist in other 226 public modules.** The Stage 2L AST scanner integrated into the stable staging path must continue to refuse an official stable Wheel until the *entire* real Git checkout passes. Do not disable, bypass, or weaken it.
2. Get a full approved **nonroot Python3.12 source checkout**, run all relevant source + integration tests and Ruff. Full-module imports and runtime behavior, including status/read-only branches, must be tested—not inferred from AST slices.
3. Build two complete real-source 0.4.0 candidate Wheels on the approved host, independently verify the final source and metadata lock, Ed25519 publisher authority, RECORD and reproducibility; then run installed OFFLINE/PAPER crash/restart/PostgreSQL, stop-writer recovery and rollback gates.
4. Leave protected `main`, legacy v0.3.2, server(s), GitHub Actions quota, credentials, Telegram and real brokerage/LIVE accounts untouched. Keep PR #352 **Draft** and the official `v0.4.0` tag **absent** until all release gates are met.

**Decision:** `STAGE_2O_SOURCE_GUARDS_COMMITTED_AND_AST_TESTS_PASS__PRODUCT_RELEASE_NOT_APPROVED`.
