# MMT v0.4.0 — Stage 2U: immutable-source partial acceptance and runtime-environment blockade

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate` / Draft PR #352  
**Immutable source under test:** `95ef47f0e1fee454c400770606e27f3c45695eb7`  
**Verdict:** `SOURCE_IDENTITY_226_PASS__TARGETED_GENUINE_AST_AND_RUNTIME_PASS__FULL_226_AST_NOT_EXECUTED__PYTHON312_WHEEL_PRODUCT_NOT_TESTED__OFFICIAL_RELEASE_DENIED`

## 1. Real GitHub source custody on pinned SHA

Using the authorized GitHub repository connection, fetched the **actual UTF-8 content** of all **226 manifest-listed** `naseri_markets/*.py` files from immutable commit `95ef47f0e1fee454c400770606e27f3c45695eb7`, in bounded batches. For every file, confirmed its returned **Git Blob SHA-1** equals the per-file source lock value and that the real UTF-8 byte length equals the manifest. **226/226** source blob/size comparisons passed.

Actual GitHub public-source tree: `3e13f90d5e2f7989b64cd91d15fce786be3c27ca`. Locked aggregate source size: **2,500,734 bytes**. Global **text-pattern** scan of those 226 actual source bodies for value-only `get/getenv("MMT_PRODUCTION") ==/!= literal` decisions found **zero matches**. This textual check is distinct from executing Python's `ast` on 226 original files; **the actual whole-source AST gate has not passed in the available runner**.

The root GitHub repo's published legacy `crypto-price-action` version remains **0.3.2**. The separate `platform_release/pyproject.toml` remains `multi-market-trading==0.4.0rc1`, with `requires-python = ">=3.12,<3.13"` and pinned `setuptools==80.9.0`, `wheel==0.45.1`. Hence Python3.13 smoke tests **cannot** satisfy target Python3.12 package acceptance.

## 2. Genuine, executable source fragment proofs (not a product certificate)

The isolated assistant execution container could not clone GitHub (`Could not resolve host: github.com`). The complete real checkout was **not** present. CPython available was **3.13.5**; `python3.12` and `ruff` executables were **unavailable**. No GitHub Actions quota was used.

Nevertheless, retrieved the **actual original Stage2L AST auditor source** from immutable GitHub commit and reproduced it byte-exactly in the disposable isolated runner. Verified Git Blob SHA-1:

- `scripts/mmt_v040_production_guard_ast_audit_v1.py` — **`4f38a64c3486773d54ce3c078139830c874df6ac`**, actual source matched exactly.
- `naseri_markets/brooks_stage12_cli.py` — **`1f27d2fcf5e2b52d342449913197710c3271f838`**, actual source matched exactly.
- `naseri_markets/runtime_supervisor_health_v1.py` — **`2db6fd9b72dd4c4b1190bf0e8c41f836b8e3c5f3`**, actual source matched exactly.

**Executed under nonroot UID 1000 on Python3.13.5:**

- Six original-scanner direct regression tests from `test_mmt_v040_stage2t_global_ast_source_gate_v1.py`: **6 passed**, **2 full-checkout-dependent cases deselected**. Original scanner syntax/source SHA verified.
- Executed the actual existing Stage2L `require_no_value_only_guards` on the **two original Git-blob-matched source files**: PASS for 2/2; deliberately appended value-only guard correctly produced `V040_PRODUCTION_VALUE_ONLY_GUARDS_DENIED:1`.
- Imported the actual Git-blob-matched `runtime_supervisor_health_v1.py`; performed **11/11 real-module initial-admission cases** successfully: six defined production values refused, four absent/invalid nonproduction acknowledgements refused, and missing offline database refused before database open. No production DB or market network was accessed.
- Re-ran **182/182 Stage2T fixture-based admission regressions** under nonroot Python3.13.5. These remained deliberately reduced guard fixtures, not the 11 full source modules.
- `py_compile` of the five locally held Python files (two original modules, Stage2L scanner, two committed Stage2T tests) succeeded on Python3.13.5. This is not complete-repository compilation.

**Important negative finding:** Running the eight-case Stage2T whole-source AST test file directly in the incomplete fixture workspace led to **8 failed tests** due to the absent 226-source manifest/complete checkout and missing source scanner before mirroring; these failures are **environment prerequisites not met**, NOT legitimate test passes, and NOT evidence of a production regression. After mirroring the authentic scanner, only the six scanner-specific cases were intentionally re-run. The two full-226 test cases have never been executed and remain PENDING.

## 3. Required final product gates — not completed

| Gate | Status |
| --- | --- |
| 226-source exact Git Blob SHA + UTF-8 length vs committed lock | **PASS** |
| 226-source reviewed textual value-only check | **0 observed**; not AST |
| Genuine Stage2L scanner on 2 actual hash-matched source modules + tamper | **PASS** on 2 only |
| Six genuine scanner regression tests | **6/6 PASS** Python3.13.5, nonroot |
| Genuine runtime health admission tests | **11/11 PASS** Python3.13.5, nonroot |
| Full 226 original-source AST gate on real checkout | **NOT RUN** |
| Full Stage2N–2T source-bound / product tests | **NOT RUN** |
| CPython3.12 + Ruff on full checkout | **UNAVAILABLE / NOT RUN** |
| Actual real 226-module Wheel, deterministic two builds, install, RECORD and release signature | **NOT RUN** |
| Installed Brooks→risk→PAPER E2E, 32 restarts, rollback and PostgreSQL | **NOT RUN** |
| Trusted signer, operator/host security accreditation, final protected-branch review | **PENDING** |

## 4. Disposition — keep Stage 2U open

The relevant test code is already committed in the earlier stage:

- `tests/unit/test_mmt_v040_stage2t_global_ast_source_gate_v1.py` (full real-source test, not yet executed end-to-end).
- `tests/unit/test_mmt_v040_stage2t_remaining_production_guards_v1.py` (source-bound guard conditions, only tested with fixtures here).

**Do not promote this partial evidence into a complete Stage2U PASS.** Obtain a clean, disposable, **nonroot CPython3.12** full GitHub checkout pinned to the new final HEAD, execute the 226-source AST gate, all source-bound security tests, Ruff, real installed Wheel and the complete product/recovery/supply-chain matrix. No existing production host, Telmivo server, database, secrets, broker, Telegram or LIVE market order may be used merely to bypass this acceptance environment gap.

**Release denied:** keep PR #352 Draft and unmerged. Do not alter `main`, the immutable `v0.3.2`, or create an official `v0.4.0-rc.1`/`v0.4.0` tag.
