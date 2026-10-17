# MMT v0.4.0 — Stage 2S: isolated runtime, host and recovery gate hardening

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate` (Draft PR #352)  
**Status:** `SIXTEEN_ACTUAL_SOURCE_GUARDS_HARDENED__226_SOURCE_IDENTITY_MATCH__193_ISOLATED_FIXTURE_TESTS_PASS__FULL_RELEASE_BLOCKED`

## 1. Actual scope and source review

Started from verified Stage 2R HEAD `ef63d41598e71d5a1aadadb47aa5b6fcf70d8d96`. Reviewed actual candidate-branch GitHub contents before changing each source file. Exactly one `os.environ.get("MMT_PRODUCTION") == "1"` occurred in each of these 16 files, with no other local `MMT_PRODUCTION` occurrence. The single value-only predicate was changed to `"MMT_PRODUCTION" in os.environ` while preserving all other bytes, refusals, and separately required `MMT_NONPRODUCTION=1` checks:

| Category | Files under `naseri_markets/` |
| --- | --- |
| Host / isolated worker | `dev_operator.py`, `disposable_gvisor_canary_cli_stage23_v1.py`, `disposable_gvisor_canary_stage23_v1.py`, `durable_isolated_core_gate_stage22_v1.py`, `durable_runtime_a3.py` |
| Historical / exchange | `executable_walk_forward_stage13_v1.py`, `kucoin_futures_replay_stage21_v1.py`, `mt_a1_offline_artifact_preflight.py`, `native_a1_inert_binary_preflight.py` |
| Ledger / recovery | `job_effect_intent_v1.py`, `job_effect_reconciliation_v1.py`, `operational_reconciliation_v1.py` |
| PAPER / administration | `mmt_r31_private_admin_console_v1.py`, `mmt_r33_live_hard_deny_readiness_v1.py`, `mmt_r34_offline_stack_acceptance_v1.py`, `panel_paper_synthetic_demo_v1.py` |

All 16 real GitHub source files were read back after changes: 16/16 new production-key presence predicates, 0/16 old value-only predicates. Exactly 16 × 9 = **144 fewer source bytes**. The local admission predicates retain independently required operator, nonroot/disposable sandbox, host acknowledgements, and other validations. This is **not** a verified full caller/child dependency analysis; no LIVE operation was invoked.

## 2. Test evidence and limits

`tests/unit/test_mmt_v040_stage2s_disposable_runtime_production_guards_v1.py` added on the release branch. Its Git Blob SHA-1 is **`19dcb58206cf8a6777d7686d165bb2a951606dec`** and exact contents match the independently executed local file of **5,043 bytes**, SHA256 `c60bb10b0bb7c631431d714a4ab79091e0a6f301d6f341b5e4df5d60a17168a6`.

**Actual isolated local execution:** CPython **3.13.5** / pytest, **193 passed in 0.39s**.

- 96 tests: sixteen reviewed guards × six explicitly assigned production values (including `0`, `false`, and empty).
- 64 tests: sixteen guards × four missing/invalid `MMT_NONPRODUCTION` values.
- 16 tests: approved environment can clear the **initial extracted guard only** when production key is absent (nonroot identity mocked in the isolated test).
- 16 AST source-shape tests and one inventory scope test.

**Critical limitation:** These 193 tests ran against 16 **synthetic reduced guard fixtures** corresponding to the reviewed entry admission branches. They did **not** import or execute the actual 16 original modules, nor their complete dependencies. On a complete repository checkout, the committed test instead reads real module source and could detect behavioral differences, but that checkout-bound run has **not happened**. No real Python3.12, Ruff, full Wheel, exchange, Telegram, PostgreSQL or PAPER acceptance was performed in this stage. An attempted local Git clone failed to resolve github.com; GitHub read/write instead used the authorized repository connector.

## 3. Git-tree source identity lock

Direct GitHub Git-tree enumeration after the sixteen source changes found exactly **16 changed** module SHA/size entries and **210 unchanged** sources, relative to Stage 2R. The source lock `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` was repinned:

| Property | Confirmed |
| --- | --- |
| Actual source snapshot commit | `3a886348fc14acbfde53455d3491e0827a13c124` |
| Git source subtree SHA-1 | **`951d35d64fdf9ebdc72971e55197fc0a92454230`** |
| Public source modules | **226/226** |
| Total source bytes | **2,500,860** |
| New lock Git Blob SHA-1 | **`b81246823af35b65b34c38a81abddc1e1c7d6d27`** |
| Source lock commit | `76cb2cb1f413805884ea8ed67d0ab37e4cd15181` |

The lock is an exact Git source identity check, **not** proof of Python build/run acceptance, secure signing, or trusted stable release provenance.

## 4. Unresolved AST blockers discovered in the repository

Other **real** legacy value-only admission predicates remain, including:

- `public_candidate_lock_stage26_v1.py`
- `public_forward_capture_stage21c_v1.py`
- `public_futures_contracts.py`
- `publisher_package_registry_stage28_v1.py`
- `read_only_provider_adapters_v1.py` (**two** occurrences)
- `research_robustness_stage14_v1.py`
- `signed_core_candidate_stage23_v1.py`
- `supervisor_synthetic_smoke_v1.py` (single-quoted variant)
- `pine_a1_sma_cross_parity.py`
- additional host/data and job-admission modules require individual verification.

**Global Stage2L release AST fence remains enabled, and stable staging remains blocked.** This stage did not globally eliminate all value-only predicates. It would be incorrect to claim the whole 226-module AST audit passed merely from source inventory pinning or isolated fixtures.

## 5. Next stage and release denial

**Stage 2T:** finish complete source-level production-flag audit and individually patch remaining confirmed predicates, preserving parent→child environment contracts; add real-source-bound tests for multiple guards and quote variants. Recompute and revalidate all 226 real Git blobs, then execute the global Stage2L AST gate on a complete Git checkout. Follow with nonroot CPython3.12, Ruff, real Wheel dual builds, full unit/integration/Postgres/PAPER/Brooks R35–R38/R42V, recovery/rollback and signer approval on the final exact commit.

**Decision:** keep PR #352 Draft/unmerged. Do not change `main`, production environments, signing keys, actual orders, Telegram sends, or release tags `v0.4.0-rc.1`/`v0.4.0`.
