# MMT v0.4.0 — Stage 2K: Real source-body checksum review and re-signed Wheel metadata provenance

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate` / Draft PR #352  
**Status:** `226_REAL_SOURCE_BODIES_GITHUB_HASH_MATCH__RE_SIGNED_WHEEL_METADATA_SPOOF_DENIED__ACTUAL_PY312_INSTALL_NOT_RUN`

## 1. Real source, not synthetic source filenames

The approved GitHub connector individually fetched the UTF-8 **content of all 226 actual public Python modules** under the immutable snapshot commit `c709db14408d133478fa74e905e43ef946085f92`. For each received file, the GitHub response's actual source Blob SHA-1 was compared with the previously independently registered `docs/MMT_V0_4_0_PUBLIC_MODULE_SNAPSHOT.json`. All **226/226 hashes matched**. No fetch failed, and no direct textual statement of the form `import private_nyfr_core`, `from private_nyfr_core`, `import r0_engine`, or `from r0_engine` was found in these source bodies.

This is a full **GitHub file-body receipt and checked SHA identity**, not just tree metadata. It is **not** a Python AST scan of every module, cannot catch computed/dynamic imports and is not a locally built real-source Wheel. All files were read via authenticated GitHub connector into the short-lived tool environment; because the isolated runner has no outbound GitHub DNS/clone, a complete 226-module on-disk checkout **was not** materialized.

The checkout's historical source SHA, package subtree and inventory lock remain:
- Original immutable source snapshot commit: `c709db14408d133478fa74e905e43ef946085f92`.
- Package subtree Git SHA-1: `75bfd7de73b184d0da2a83dcf0909d2550d0d8a7`.
- 226 module content sizes total **2,501,524 bytes**.
- Independently pinned complete module inventory SHA256: `c447806f659bb2e99837734feb7ca4620798a799cf4af164399c444d356a2de6`.

## 2. New confirmed signed-artifact source-authenticity weakness

The Stage 2I `mmt_v040_rc_overlay_signed_custody_v1.py` checked **all source module bytes** against a signed stable Wheel and correctly pinned Git/overlay SHA values, but did **not compare Wheel `dist-info/METADATA` Summary or long README body to the original version-controlled packaging inputs**. A holder of an otherwise eligible signing key could repackage and sign an altered Summary/README, leave all 226 modules and RECORD internally correct, and pass the old custody verifier. This matters because publisher trust/policy alone is not evidence that artifact descriptions match the independently pinned Git source.

**Actual narrow fix pushed to GitHub:** in `scripts/mmt_v040_rc_overlay_signed_custody_v1.py` bind signed `dist-info/METADATA` headers `Summary` and `Description-Content-Type: text/markdown` to the exact reviewed `platform_release/pyproject.toml` and enforce **byte-for-byte equality** of the METADATA long-description body to the original `platform_release/README.md`, after independently pinned Git/source validation and stable Wheel signature verification. Reject absent, unexpected or duplicate Summary, wrong content type and changed README with constant denial codes. No import, install, broker/Telegram action or release permission is enabled.

Three **real negative cryptography tests** were added to `tests/unit/test_mmt_v040_rc_overlay_signed_custody_v1.py`: altered Summary, altered README, and duplicate Summary. Test fixtures purposely regenerate valid Wheel RECORD and Ed25519 signature, including a direct `stable.verify()` **positive** on the forged-Summary artifact, showing that the new independent source-provenance gate (not ordinary signature verification) blocks the mismatch.

## 3. Actual execution and exact committed-file attestation

Using the disposable **CPython 3.13.5** runner (no Python 3.12 and no Ruff), reran all existing seven focused suites including actual local Git, synthetic 226-module staged builds and signed Ed25519 tests:

```text
100 passed in 14.99s
```

That is **97 previous tests + 3 new signed-metadata source-spoof tests**. All source and test changes were compared byte-for-byte with the modified GitHub files via independently computed Git Blob SHA-1:

| Changed file | Git blob SHA-1 | SHA256 of exact tested bytes |
| --- | --- | --- |
| `scripts/mmt_v040_rc_overlay_signed_custody_v1.py` | `59ef217cb187375a0d9e088d1edd9fa9649938a7` | `9e29fff4896f5303524bdeb1f4479b35c02d5fc7cfb4275f639939b42f9d080e` |
| `tests/unit/test_mmt_v040_rc_overlay_signed_custody_v1.py` | `fcf02c4e19ba99bfe4e6e3410107c7e592ca7392` | `04005449807c4a2ab4164261dfcf5293c9fee96893090126200dd6901c87f8d2` |

The previous real-`setuptools` 226-*synthetic*-module test includes a genuine `METADATA` Summary, `text/markdown` and README body; it passed again with the new header/description equality checks. File-byte copy integrity and safe false permission flags are preserved.

## 4. Release gate still closed

1. **Actual full-project Wheel**: Not built. The actual 226 module bodies were fetched and hash-verified **inside the GitHub connector**, not mounted as a complete buildable local Git checkout.
2. **Actual CPython3.12, pinned Ruff, full integrated pytest/A6/R35-R38/R42V suites, and fresh nonroot install**: Not run.
3. **Signer authority, hardware/independent build attestation and same-byte real dual Wheel reproducibility**: Not proven. Existing keys were ephemeral test-only keys.
4. **Offline/PAPER startup, restart/rollback, PostgreSQL and frozen legacy migration**: Not run. No LIVE trading/Telegram permission.
5. **No merge into protected `main` or official stable Git tag `v0.4.0`**. Current source still declares `0.4.0rc1`. Older official `v0.3.2`, production DB and user Telmivo server remain unchanged.

**Next acceptance step:** obtain actual full-source checkout and approved disposable **Python 3.12 nonroot** runner; execute clean checkout attestation, two real source builds, new metadata-source proof, installed OFFLINE/PAPER/restart/rollback and final release decision. Do not rely on mock Wheel hashes, GitHub source-body checks alone or previous Python3.13 focused tests as product release authorization.

**Decision: `STAGE_2K_CODE_AND_FOCUSED_TESTS_PASS__OFFICIAL_V040_RELEASE_BLOCKED`.**
