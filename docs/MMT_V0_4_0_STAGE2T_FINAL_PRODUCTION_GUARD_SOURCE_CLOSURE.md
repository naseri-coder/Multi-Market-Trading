# MMT v0.4.0 — Stage 2T: remaining value-only production-guard source closure

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate` (Draft PR #352)  
**Source outcome:** `ELEVEN_REAL_MODULES__FOURTEEN_REVIEWED_PREDICATES_HARDENED__226_SOURCE_BLOB_LOCK_MATCH`  
**Acceptance outcome:** `FULL_SOURCE_AST_NOT_EXECUTED__PYTHON312_PRODUCT_MATRIX_NOT_RUN__OFFICIAL_RELEASE_BLOCKED`

## 1. Provenance and scope

Started from independently verified Stage 2S HEAD `9397af34191cb8c0da68abdf00d9a73a3ead9537`. Read the candidate GitHub source bodies across the **226** manifest-listed public Python modules for residual literal value-only production checks. A module-specific first pass found nine modules; the subsequent source-wide survey identified two additionally overlooked Brooks R26/R27 parity paths, each containing two value-only controls.

The exact reviewed old expression was `os.environ.get("MMT_PRODUCTION") == "1"` (single-quoted variant in synthetic supervisor). Changed only that expression to the matching `"MMT_PRODUCTION" in os.environ`, keeping quotes appropriate to the module. **No mass replacement of arbitrary environment expressions** and no alteration of existing `MMT_NONPRODUCTION=1`, operator approval or error/return behavior.

| Path under `naseri_markets/` | Production-value checks corrected |
| --- | ---: |
| `brooks_causal_execution_parity_audit_mmt_r26_v1.py` | 2 |
| `brooks_independent_lifecycle_economics_mmt_r27_v1.py` | 2 |
| `pine_a1_sma_cross_parity.py` | 1 |
| `public_candidate_lock_stage26_v1.py` | 1 |
| `public_forward_capture_stage21c_v1.py` | 1 |
| `public_futures_contracts.py` | 1 |
| `publisher_package_registry_stage28_v1.py` | 1 |
| `read_only_provider_adapters_v1.py` | 2 |
| `research_robustness_stage14_v1.py` | 1 |
| `signed_core_candidate_stage23_v1.py` | 1 |
| `supervisor_synthetic_smoke_v1.py` | 1 |

**Total: 11 modules / 14 guards / 126 fewer source bytes.** Each reviewed changed module had no separate local `MMT_PRODUCTION` child-environment assignment. Caller/child compatibility remains unproven without real integration tests.

The source-wide GitHub review found no additional instance of the surveyed `os.environ.get/os.getenv/environment.get("MMT_PRODUCTION") ==/!= "literal"` patterns after these fixes. **This is a text/targeted-pattern inspection, NOT a formally passed full-repository AST audit**: the existing Stage 2L AST gate checks additional forms and must be executed on all original source bytes.

## 2. Source pin and GitHub readback

After the 11 changes, read the actual GitHub Git tree and rebaseline `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json`. Exactly 11 paths differed from the prior lock; **215** source blobs were unchanged.

| Field | Verified value |
| --- | --- |
| Source snapshot commit (before lock update) | `4c00472f193ebdb38c69271ba10e7bdda394e0a8` |
| Public Git source subtree SHA-1 | `3e13f90d5e2f7989b64cd91d15fce786be3c27ca` |
| Source files | **226/226** SHA-1 and size matched |
| Source bytes | **2,500,734** |
| New source-lock Git Blob SHA-1 | `bab211afe8eba88a2bbc32b60525ef7e907ec223` |
| Lock update commit | `6ad2a32885f6bdd2b08fbb417e4a273af3ce80b4` |

After committing tests, independently re-read the GitHub source tree and lock: **226/226 match** remained true. Source identity does NOT imply full Python compatibility, release authority, or signed Wheel custody.

## 3. Focused tests and actual execution limits

**Committed tests:**

- `tests/unit/test_mmt_v040_stage2t_remaining_production_guards_v1.py` — Git Blob SHA-1 `22ce6e2a65007116580f6864e921f8d72c1e75d7` (5,017 bytes), SHA256 `c517013747d62016c386551330c7a9bc835bb9875378cfc7ab56dcb1936d5f7d`. This reads actual module source **when run within the complete repo checkout**, locates 14 reviewed entry-condition AST nodes and evaluates only their boolean predicates. The GitHub file matches the independently executed local test bytes.
- `tests/unit/test_mmt_v040_stage2t_global_ast_source_gate_v1.py` — Git Blob SHA-1 `dd0bb76bea02066b88bd7564b92c0a8412cf405f` (3,149 bytes), SHA256 `a9942115fc3785852e274fe80719934f2c0865594badf673d3f6bb6b899e2df7`. This reads all 226 real source files, verifies each byte-length and Git blob SHA-1 against the manifest, invokes the **actual** Stage2L AST production guard scanner, and exercises a tamper-negative case. Its local Python syntax compilation passed, but **its full-checkout tests were NOT executed**.

**Executed:** in isolated local **CPython 3.13.5** / pytest, **182/182** admission-fixture cases passed in **0.31s**. The locally executed test used **11 deliberately reduced equivalent guard fixtures**, NOT original full module bodies. It is wrong to treat this as real-world runtime, Wheel, or full AST closure. No claim of Python3.12 or full repository pytest success is made.

**Blocked:** the execution container lacked DNS/network access to clone GitHub, as independently confirmed by `git ls-remote`; Python3.12 and Ruff were unavailable in this container. GitHub connector access still permitted source verification and commits. GitHub Actions were not triggered for this stage.

## 4. Hard release gates and next work

**Next Stage 2U: genuine-source acceptance.** Acquire an independent, approved complete real checkout at this exact immutable candidate SHA on **nonroot Python 3.12**, run the two new test files and existing Stage2L global AST scanner against all 226 real module bodies, and repeat prior Stage2N–2S source-bound suites. If the scanner finds another comparison, reject stable staging and fix it with a new scoped proof.

Then run Ruff, full unit/integration/PostgreSQL, R42V pinned 59-case matrix, R35–R38, actual 226-source Wheel dual builds and signature/RECORD/source custody, genuine pinned Brooks→risk→PAPER replay, restart/rollback/32-soak, and signer/host/branch approvals. Record exact SHA and all skip/fail counts. Never substitute partial synthetic fixtures for these acceptance requirements.

**Release verdict:** `SOURCE_FIXES_COMMITTED__GLOBAL_AST_EXECUTION_PENDING__DRAFT_PR_352_UNMERGED__V0_4_0_NOT_AUTHORIZED`.

Do not mark PR #352 ready, merge to protected `main`, create `v0.4.0` or prerelease tag, touch Telmivo or other production servers, use real account secrets, send Telegram messages, or place LIVE orders.
