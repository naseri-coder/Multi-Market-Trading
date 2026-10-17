# MMT v0.4.0 — Stage 2R: archive and Brooks causal-chain production admission hardening

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate` / Draft PR #352  
**Result:** `EIGHT_REAL_SOURCE_GUARDS_HARDENED__SOURCE_LOCK_226_MATCH__104_FIXTURE_TESTS_PASS__GLOBAL_AST_RELEASE_GATE_STILL_BLOCKED`

## 1. Scope and exact production guard edits

Started from verified Stage 2Q HEAD `3deedc719bdb35f96c4f88b4de8f5cc07c755ad9`. The following eight actual public modules were read from the GitHub candidate branch and found to contain exactly one value-only production predicate:

| GitHub source under `naseri_markets/` | Reviewed boundary |
| --- | --- |
| `futures_economic_scenario_stage16_v1.py` | Stage16 explicitly approved research economics |
| `stage17_official_archive_capture_v1.py` | Stage17 official archive capture admission |
| `futures_economics_evidence_stage18_v1.py` | Stage18 funding/economics evidence admission |
| `brooks_causal_backtest_preflight_stage19_v1.py` | Stage19 Brooks causal backtest preflight |
| `brooks_walk_forward_preholdout_stage20_v1.py` | Stage20 research/walk-forward approval |
| `brooks_causal_lifecycle_stage21_preflight_v1.py` | Stage21 causal lifecycle preflight |
| `brooks_primary_source_funding_join_stage21b_v1.py` | Stage21B source/funding evidence join |
| `brooks_prospective_forward_custody_stage21c_v1.py` | Stage21C prospective source custody |

In each file, replaced exactly one
`os.environ.get("MMT_PRODUCTION") == "1"`
with
`"MMT_PRODUCTION" in os.environ`.

**No bulk rewrite**: the existing `MMT_NONPRODUCTION=1` check, seven operator acknowledgement checks, original exact refusal codes, source bytes outside that expression, trading behavior and data/economic validation logic were preserved. Stage17 relies on the separate nonproduction acknowledgement and did not have a per-function `operator_ack`. Each original file had exactly one `MMT_PRODUCTION` mention (its entry guard), so no local child-environment injection of `MMT_PRODUCTION="0"` was changed. Full cross-module runtime dependencies still require genuine integration testing.

Readback from GitHub after updates independently confirmed **8/8** production-key presence checks, **0/8** prior value-only predicates, and **8/8** unchanged `MMT_NONPRODUCTION` checks. Each replacement removes **9 bytes**: **72 bytes** total.

## 2. Test evidence, with limits

Committed `tests/unit/test_mmt_v040_stage2r_archive_brooks_admission_v1.py`, Git blob SHA-1 `a24618e8d3ed0ca06537739addf8d562aa63884e`, **5,354 bytes**; identical to the independently run test file (SHA256 `9b8cce26fab2aa6b3a5e7d839d5b49417e89b997233e00c5ed670ad930ee1adf`).

Isolated local CPython **3.13.5**, pytest **9.0.2**:

```
104 passed in 0.33s
```

- 48 denial cases: eight guards × six explicitly set production values (`""`, `0`, `1`, `false`, `FALSE`, `no`);
- 32 refusal cases: eight guards × four missing/invalid nonproduction acknowledgements;
- 7 missing operator-approval refusals (seven modules have operator_ack; Stage17 does not);
- 8 permitted **initial-guard only** checks when production key absent and nonproduction approval present;
- 8 AST checks for exact immediate error type and refusal reason;
- 1 inventory/scope assertion.

**Critical scope limitation:** The isolated runner could not clone or fetch the full repository because outbound GitHub DNS/network access was unavailable. These **104** tests ran against deliberately reduced, equivalent guard fixtures. The committed test is source-bound and will instead read the original GitHub module files on a complete checkout; that **full-source test has not yet been executed**. This is NOT proof that all eight full modules, imported dependencies, archive captures, broker/PAPER and live-readiness paths execute successfully.

## 3. Source lock and source identity

The exact 226-entry GitHub `naseri_markets` source tree was enumerated and compared against the preceding Stage 2Q snapshot. The eight intended changed paths were the **only** blob SHA/size mismatches; 218 modules were unchanged. After rebaseline, `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` matches GitHub per-file SHA-1/size:

| Property | Verified value |
| --- | --- |
| Source snapshot commit before lock | `6e204cc33208bec42c88d7b41054742b43eb0942` |
| Public subtree SHA-1 | `4bb8186f40d70378741caf1b8a2d878aee3ae748` |
| Public module count | **226/226** |
| Total public-source bytes | **2,501,004** |
| Current lock Git Blob SHA-1 | `25a76954b4ef409040cf434d811e14caf76efdb5` |
| Lock update commit | `d51077b8f93f0f68e8a40b63736c4d137843de55` |

Historical source locks must not be used for publication. This source-identity proof is NOT a full installed Wheel custody certificate or signer approval.

## 4. Remaining release blockers and next stage

The Stage 2L global AST production-value guard audit remains **fail-closed**: other public modules still contain value-only production predicates, so stable staging remains forbidden. Additional guard classes (including any supplied environment mappings and parent→child environment contracts) must be scoped separately and verified by real tests.

**Still unexecuted/required:** full GitHub source checkout; CPython 3.12 nonroot, Ruff and complete unit/integration/Postgres tests; the actual 226-module stable Wheel and dual reproducibility; R35–R38/R42V installed-product acceptance; genuine Brooks→risk→PAPER closure, restart/rollback; release signer trust and supply-chain attestation; final branch protection/review and immutable release-tag checks.

**Stage 2S:** finish a dependency-aware scan and remediation of remaining actual value-only guards, preserving any legitimate child environment policy. Verify the global Stage2L AST gate against all real module bodies, and run actual source-bound regression tests on CPython3.12 before proceeding to packaging and sign-off. Do not call a partial fixture-only pass "release ready".

**Release decision:** PR #352 remains **Draft/unmerged**, `main` unchanged. No v0.4.0 tag, production server, actual trades, Telegram sends, database migrations or new signing authority.
