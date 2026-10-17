# MMT v0.4.0 — Stage 2Q: Runtime / host production admission hardening

**Date:** 2026-10-17
**Branch:** `release/0.4.0-candidate`
**Review:** Draft PR #352
**Status:** `EIGHT_ACTUAL_GUARDS_HARDENED__226_SOURCE_LOCK_MATCH__GLOBAL_AST_GATE_STILL_BLOCKING__OFFICIAL_RELEASE_DENIED`

## 1. Provenance and scope

Continued from verified Stage 2P HEAD `081340b2767291494b316529750f3e1e9adf8521`. No rewrite of 2N–2P. Original entrypoint bodies were fetched from GitHub before patching, and each had exactly one production-value comparison plus an independent `MMT_NONPRODUCTION` predicate. None of these eight sources intentionally inserted `MMT_PRODUCTION=0` into a child environment.

Only the single literal `os.environ.get("MMT_PRODUCTION") == "1"` was replaced by `"MMT_PRODUCTION" in os.environ` in each of the following source files:

| File under `naseri_markets/` | Reviewed gate |
| --- | --- |
| `runtime_a4_security_evidence.py` | runtime security evidence admission |
| `runtime_a5_nonce_custody.py` | nonce custody admission |
| `runtime_a9_offline_intent.py` | offline intent admission |
| `runtime_a10_evidence_anchor.py` | evidence anchoring admission |
| `host_observation_custody_stage24_v1.py` | host observation custody |
| `preinstall_evidence_stage25_v1.py` | preinstall review |
| `disposable_host_preflight_stage32_v1.py` | disposable host preparation |
| `designated_host_readonly_probe_stage34_v1.py` | designated host read-only probe |

Eight targeted changes each remove nine bytes, **72 fewer total source bytes**. The existing explicit nonproduction operator acknowledgements and host/sandbox conditions remain unchanged. No strategy, broker, server, credential, database, Telegram, deployment, LIVE control, or protected `main` change.

## 2. Verification

A new repository-bound AST test file is committed at
`tests/unit/test_mmt_v040_stage2q_runtime_host_production_guards_v1.py` (Git blob SHA-1 `adc578247c807ef95659d1025b9aebfdd0fe3d18`).

An isolated **Python 3.13.5** fixture test run reported **73/73 PASSED** in 0.16 seconds: 48 tests over six expressly defined production values, eight missing-nonproduction refusals, eight guard syntax checks, eight absent-key predicate checks, and one scope check. The fixture modules were reconstructed from the reviewed entry-condition slices; **the actual eight full source modules were not executed** and the full checkout was unavailable in this runner. The exact 3,982-byte committed test file matches the locally tested Git blob; its local SHA256 is `7459b14bfd3ea7fd9d9f5890589a11d9d939024a1dfc4789df61ff8f34d61739`.

After the eight source changes, GitHub's **actual** `naseri_markets` source tree was read and compared to the repinned snapshot:

| Check | Verified |
| --- | --- |
| Source-change commit before lock | `6fcefeab451f65f3f200acbb493a61903efeaba8` |
| Git source subtree SHA-1 | `3e527756bfd362c4bf745651df7a6a2287933b4b` |
| Git public-source entries | 226/226 |
| Blob SHA-1 and size lock match | 226/226 |
| Total source bytes | 2,501,076 |
| Changed module entries | 8 |
| Unchanged module entries | 218 |
| Source lock Git blob SHA-1 | `f68673196639aa60495db0187166c5a0b6374848` |
| Source lock update commit | `929474982f0821bcf9d6c7e4f03761d841beec8d` |
| Tests addition commit | `babff10fceece12430d1e5dc4b5d7f34d3f4b9dd` |

The source snapshot is a cryptographic identity witness, **not** a product runtime certificate.

## 3. Residual release blockers

- Other value-only production checks remain in public modules, including `stage17_official_archive_capture_v1.py`. The Stage 2L **fail-closed global AST staging gate remains enabled and prevents a stable build**.
- A clean full GitHub checkout, nonroot Python 3.12, Ruff, all actual 226-source module tests, installed Wheel, reproducible real dual build, installed PAPER/Brooks R35–R38/R42V, isolated PostgreSQL/recovery, approved signer provenance, independent source and artifact verification, and final PR/main acceptance have NOT been completed.
- The 73 reported tests are **only reduced admission-fixture tests**, not full source-bound acceptance. Do not represent them as verified end-to-end security, exactly-once behavior, or stable-release readiness.

**Next:** Stage 2R — dependency-aware remediation of remaining real data/archive/replay/host checks, with explicit parent→child environment verification; repin full source lock and rerun complete AST staging denial. Then run a genuine nonroot Python 3.12 product matrix before changing PR state. Keep PR #352 Draft; do not tag/merge/deploy.
