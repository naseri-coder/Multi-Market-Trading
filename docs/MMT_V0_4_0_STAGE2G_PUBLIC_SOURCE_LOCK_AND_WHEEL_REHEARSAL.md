# MMT v0.4.0 — Stage 2G: complete GitHub source lock and 226-module wheel rehearsal

**Date:** 2026-10-17  
**Source:** `naseri-coder/Multi-Market-Trading`, `release/0.4.0-candidate`  
**Verdict:** `REAL_GITHUB_226_BLOB_SNAPSHOT_MATCH__SYNTHETIC_226_WHEEL_REHEARSAL_PASS__ACTUAL_FULL_WHEEL_PY312_BLOCKED`

## 1 — Real 226-module GitHub tree verification, not a fake file listing

Direct GitHub Git tree read at `c709db14408d133478fa74e905e43ef946085f92`, and **reverified after committing this stage's source and tests**, found:

| Property | Real GitHub result |
| --- | --- |
| Flat `naseri_markets/*.py` blobs | **226** |
| Total Python source bytes | **2,501,524** |
| Public package Git subtree SHA-1 | `75bfd7de73b184d0da2a83dcf0909d2550d0d8a7` |
| GitHub snapshot source commit | `c709db14408d133478fa74e905e43ef946085f92` |
| Git tree types and file modes | **226 ordinary blobs, all `100644`** |
| Unexpected nested, non-Python or private-engine module names | **0** |
| Snapshot-path ↔ exact actual blob SHA-1 AND byte-size comparisons | **226/226 matched** |

The source tree SHA is still unchanged after Stage 2G commits; these changes touched only `scripts/`, `tests/` and `docs/`, not any `naseri_markets/` module.

Committed:
- `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json` — all 226 file paths, blob hashes and original size, exact package subtree and historic snapshot commit.
- `scripts/mmt_v040_public_source_snapshot_audit_v1.py` — **read-only**, requires independent trusted Git HEAD, subtree SHA-1 and independently pinned snapshot SHA256; checks a clean, untracked-free checkout, entire 226-file tracked set, every on-disk Git blob hash and length, bytes total and still-clean state after checks. Denies any explicit `MMT_PRODUCTION`. Never builds, imports project modules, installs, or authorizes LIVE.
- `tests/unit/test_mmt_v040_public_source_snapshot_audit_v1.py` — 11 local real-Git synthetic 226-module positive and negative cases.

**Corrected an actual source-lock error:** the initial GitHub inventory used locale-aware filename sorting. Python compares code-point/byte-order lexically, so 40 entries were differently ordered (such as `cert_a10` and `cert_a1_offline`). Rewrote the GitHub lock with deterministic ordinary path sorting; verified the corrected 226 entries against the original tree and tested the auditor's strict-order gate.

### Externally pinnable lock identifiers

- Actual snapshot file SHA256: `c447806f659bb2e99837734feb7ca4620798a799cf4af164399c444d356a2de6`.
- Git blob SHA-1 of snapshot: `7d99bce2d1c8acdc6212b962ac65114bf5ae6e28`.
- Snapshot size: **36,944 UTF-8 bytes**.
- SHA256 computed directly from GitHub-returned ASCII UTF-8 bytes with independently checked SHA256 implementation (known `abc` test vector); path/size/blob checks sourced from GitHub Git tree. This is a source *inventory commitment*, not a trusted signer key and not an actual Wheel digest.

## 2 — Actually executed tests, 2026-10-17

Independent assistant sandbox: CPython **3.13.5**, `pytest`, local Git and test-only `cryptography`, with Python3.12 and Ruff **not available**. User server `telmivo`, production runtime, GitHub Actions, real broker and Telegram were not used.

### A. Real local Git, 226 synthetic modules

```text
11 passed in 1.01s
```

Regressions cover a clean exact Git commit and 226 module blobs; defined production environment (including `0`), wrong independent HEAD, wrong independently pinned public tree, wrong snapshot SHA256, dirty tracked file, untracked new file, forged module count, forged single blob hash, changed Git source tree and manipulated inventory order.

### B. Real setuptools wheel with full *module count*, synthetic file contents

Created a disposable checkout containing exactly 226 **synthetic** Python files (2,390,762 test source bytes) using the real package metadata/CLI/optional dependency manifest; performed a real `setuptools` `pip wheel` build in the isolated environment:

- Built `multi_market_trading-0.4.0-py3-none-any.whl` **1,416,280 bytes** in approximately 4.91 seconds.
- Wheel ZIP entries: **231 = 226 modules + 5 dist-info files**.
- Independently signed the synthetic Wheel's complete SHA256 and RECORD with a freshly generated disposable Ed25519 key, its canonical v0.4.0-domain manifest and pinned allow/revocation policy.
- `mmt_v040_signed_artifact_preflight_v1.verify()` **PASS**, all privileged flags false.
- `mmt_v040_source_wheel_custody_v1.audit()` **PASS**, 226/226 source module bytes match the signed Wheel.
- `mmt_v040_public_source_snapshot_audit_v1.audit()` **PASS**, 226/226 Git blob hashes match the complete synthetic snapshot.
- Mutated the checkout after signing: **both custody and snapshot audits explicitly refused the dirty source**, not a false PASS.

Because the builder sandbox only had Python3.13, `--ignore-requires-python` was used **for this synthetic packaging rehearsal only**. The flag was not placed in any actual repository source, release installer or workflow and is prohibited as a Python3.12 acceptance substitute.

### C. Combined executable regressions

```text
58 passed in 1.61s
```

Count: 11 new 226-module snapshot tests + 9 earlier source↔signed-Wheel custody tests + 38 earlier stable Ed25519 validator tests, all run locally with CPython3.13.5. The snapshot validator and 11-test source files were read back from GitHub and their Git blob SHA-1 hashes **exactly match the executed files**:

| Committed file | Exact Git blob SHA-1 | SHA256 of tested source |
| --- | --- | --- |
| `scripts/mmt_v040_public_source_snapshot_audit_v1.py` | `be0ad945564cfe2b600baad89822d2e5b89d070e` | `2afd84465bcb23235367b61079ef34cd53428b6c2b51f56737f06b2eef71d0c2` |
| `tests/unit/test_mmt_v040_public_source_snapshot_audit_v1.py` | `e663b83f017f56064c100668995892e199fb8de6` | `ab474bca73509b6461cc626fb5ef421c7852173331e8f860ccde618415d11298` |

## 3 — Unresolved real release blockers

1. The 226 **actual GitHub Python source file contents** could not be mounted into this sandbox, because the direct GitHub zip/clone path is blocked. Actual names, Git blob SHAs and byte sizes **were independently enumerated and verified** through the GitHub connector; **no full actual-source Wheel** was built, executed or installed.
2. Python **3.12** nonroot runner, Ruff, the complete repo unit/PostgreSQL R42V corpus, physical signature trust and paper state restart/rollback were **not** executed.
3. The current package is **still `0.4.0rc1` in `platform_release/pyproject.toml`**. The stable 0.4.0 signed-wheel auditor is prepared but does not authorize the old RC artifact, and the 226-module snapshot is **not** a release signature.
4. No reviewed real publisher signing key/SPKI trust fingerprint, final built-Wheel SHA256, independently confirmed source-to-wheel chain or signed final release authorization exists.
5. Do not merge Draft PR #352, create the official `v0.4.0` tag, grant LIVE/public Telegram access or mutate `main`, legacy `0.3.2`, production databases or server.

**Next gate:** exact final candidate commit + independently pinned source snapshot SHA256 on an approved disposable **CPython3.12** checkout, full real 226-module wheel build, independent signed stable artifact verification, byte-for-byte custody, then full offline/PAPER/restart/rollback and signoff. Rebaseline the snapshot explicitly if the package source changes; never silently accept drift.
