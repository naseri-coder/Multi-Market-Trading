# MMT v0.4.0 — Stage 2P: Certification and Worker Dispatch Production-Flag Hardening

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate`  
**Status:** `EIGHT_REAL_ENTRYPOINTS_HARDENED__SOURCE_LOCK_MATCH__REMAINING_AST_STAGING_BLOCKERS__OFFICIAL_RELEASE_DENIED`

## Context and scope

At the start of this stage, GitHub already included finished Stage 2N and Stage 2O changes (Draft PR #352, HEAD `b1582c5b21f0855df3f59f81643743bcdf88dbaf`). We did **not** rewrite or repeat those stages. Stage 2P addresses eight further actual public release-certification and disposable worker admission modules whose nonproduction checks still rejected only `MMT_PRODUCTION == "1"`. The explicitly set values `0`, `false` and empty had bypassed these local admission predicates even though the strict v0.4.0 release preflight rejects any assignment.

## Exact real GitHub code changes

All eight affected files were fetched, their actual predicate and nearby function context reviewed, and verified not to construct an intentional child environment `{"MMT_PRODUCTION": "0"}`. Each contained **exactly one** instance of `os.environ.get("MMT_PRODUCTION") == "1"`. Changed only that single old predicate to `"MMT_PRODUCTION" in os.environ` per file:

| Source module | Guarded operation |
| --- | --- |
| `cert_a1_offline_candidate_review.py` | CERT-A1 explicit operator approval |
| `cert_a1_paper_format_inventory.py` | PAPER file-format inventory |
| `cert_a2_direct_paper_replay.py` | CERT-A2 direct PAPER evidence replay |
| `cert_a3_four_language_wire_replay.py` | Four-language wire replay certification |
| `cert_a4_synthetic_result_contract.py` | Synthetic result contract |
| `cert_a6_disposable_containment.py` | CERT-A6 disposable-only host admission |
| `runtime_a6_dispatch_fence.py` | Reviewed disposable worker dispatch |
| `runtime_a7_disposable_host_preflight.py` | Nonroot disposable host preflight |

Direct post-edit GitHub source reads independently found **8/8 new presence guards**, **0/8 old value-only guards**, and no intentional `MMT_PRODUCTION="0"` child assignment in these scoped source files. The previous independent opt-in `MMT_NONPRODUCTION=1`, CERT-A6's `MMT_CERT_A6_DISPOSABLE_HOST_APPROVED=1`, existing nonroot controls, exact refusal codes, trading logic and network behavior are unchanged.

## Narrow source-bound test fixture and actual execution

Committed `tests/unit/test_mmt_v040_stage2p_cert_worker_admission_v1.py`: its eight source-inventory entries are read from real `naseri_markets/*.py` when a full checkout is available; AST checks require exactly one reviewed production presence predicate and an immediate refusal. The test *executes only that isolated If guard*, never imports or runs workers or opens a dataset, exchange, database or Telegram.

In the assistant's isolated **CPython 3.13.5** container the complete GitHub source checkout was unavailable. The test was instead run with **eight deliberately reduced fixture modules containing the reviewed admission branches**, not full original modules:

```
Stage 2N fixture: 81 passed
Stage 2O fixture: 74 passed
Stage 2P fixture: 74 passed
Combined: 229/229 AST-isolated admissions passed
```

Stage 2P's **74** cases comprise 48 explicit production-value refusals (eight guards times six values: empty, 0, 1, false, FALSE, no), eight successful *initial guard only* checks with explicit nonproduction and no production key, eight missing-nonproduction refusals, one missing disposable-host approval refusal, eight exact AST source-inventory checks and one scope count check. **This is not a full package/unit/integration certificate.** Each full GitHub source file was inspected separately; no Python3.12 installation, full-module imports, broker orders or PAPER replay was executed.

The committed test file Git Blob SHA-1 **`bc017693d604fc9cd0d6b96847e20e2c9755146c`** matches the byte-exact local tested file (`SHA256 f56d65b0b17ec43357fa139e1321a0f0049cc6f90f4572b8cd4fa71f3ab55f3a`). No GitHub Actions quota was used.

## Real 226-module Git identity rebaseline

Only the eight approved source modules changed (nine bytes fewer in each; **72 fewer bytes total**). GitHub's immutable tree was enumerated after the changes; `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` was re-pinned to exactly those eight changed Blob SHAs and source file sizes. Exact current pins:

| Pin | Value |
| --- | --- |
| Source snapshot commit | `1bfa112c7606990c3495a46f78033840788dd459` |
| Public source subtree SHA-1 | `8d3da7c5a376accb147e92e4383c98d7237c4e6b` |
| Public module count and bytes | **226 / 2,501,148** |
| Lock file SHA256, independently computed | `e3ace33fbef4e45f3c4bb8714df8d66494618fc91988b0e2c43f064ff847e220` |
| Lock file Git Blob SHA-1 | `86c9322a7fe8aa8bc1c2da2921b3dddd0bb6b14d` |

Previous Stage 2O lock/tree pins are historical. After the source lock update, re-check all **226/226** exact files against the current GitHub subtree and lock before using this as any reference; a source identity witness still does not constitute approved signing/release authority.

## Hard unresolved release blockers

1. **Other actual `naseri_markets` modules still use value-only `MMT_PRODUCTION` comparisons**. The Stage 2L AST audit integrated into the stable staging path remains a hard fail-closed blocker. The eight scoped fixes must not be interpreted as a complete global AST PASS or a release authorization.
2. **CPython 3.12, Ruff, the real 226-module Wheel, reproducible dual builds, installed R35–R38/R42V, Postgres/PAPER restart/rollback and approved real publisher signing key** remain outstanding. The stage's 229 locally run tests were synthetic **guard-only** smoke tests on Python3.13, not full genuine source package tests.
3. Keep Draft PR #352 unmerged. Do not publish official `v0.4.0`, touch protected `main` or user servers, start LIVE orders, or change public Telegram permissions.

**Next stage:** continue dependency-aware remediation of remaining actual data/host/runtime/security value-only guards while preserving parent/child environment contracts. Then run the whole-source AST release gate and real nonroot Python3.12 product matrix. Do not unlock signing or tagging early.
