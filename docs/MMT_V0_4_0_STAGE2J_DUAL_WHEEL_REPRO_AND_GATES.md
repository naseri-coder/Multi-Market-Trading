# MMT v0.4.0 — Stage 2J: dual-Wheel byte identity and independently pinned custody

**Date:** 2026-10-17  
**Status:** `SYNTHETIC_WHEEL_DUAL_BUILD_IDENTICAL__FULL_ACTUAL_SOURCE_PY312_BUILD_BLOCKED`  
**Scope:** `release/0.4.0-candidate`; no GitHub Actions, no production device, no main merge, no official stable tag.

## Real release-environment check

The available isolated assistant environment contains CPython **3.13.5**, Git, `pytest` and `setuptools`, but **does not contain CPython 3.12**. Direct DNS access to `github.com` and `codeload.github.com` fails, so the **2,501,524 real source bytes** of 226 GitHub modules could not be cloned into the runner. The connected GitHub tool can read/write individual repository files and verify the actual Git tree but cannot directly mount a complete checkout for Wheel building. An authorized remote production-capable device was **not accessed**, to preserve separation from the live Telmivo server and user services.

The repository is still `multi-market-trading==0.4.0rc1` in `platform_release/pyproject.toml`. No real complete `0.4.0` source Wheel was built or installed.

## Committed code

- `scripts/mmt_v040_dual_wheel_repro_audit_v1.py`: an **offline read-only** two-artifact comparator. It requires explicit nonproduction mode, externally pinned second Wheel SHA256, two different absolute stable Wheel paths in different resolved directories, regular non-symlink/non-hardlink files, and **prior successful R35-independent Stage2I stable signed RC-overlay source custody**. This calls the existing Ed25519 signature, revocation-policy, manifest/RECORD, externally pinned Git commit, pinned 226-module inventory and exact RC→stable metadata-overlay checks. It then re-reads both Wheel files, rechecks the first against its signed hash and the second against its independent external hash, and requires exact byte equality. No build/install, signing, service start, public distribution or LIVE access.
- `tests/unit/test_mmt_v040_dual_wheel_repro_audit_v1.py`: **16 executed test cases** against temporary real Git repositories with 226 synthetic modules and throwaway test signing keys; includes valid byte equality; wrong second digest; distinct nonidentical archives despite a correctly supplied second hash; same Wheel path; symlink; hardlink; wrong Wheel name; explicit production flags (`""`, `0`, `1`, `false`); invalid external SHA256; post-signature primary tampering; invalid signature; wrong approved metadata-overlay hash; and CLI no-install/publication checks.

**Important claim boundary:** separate file paths and matching Wheel hashes **cannot establish independent build machines, independent source checkouts, or real CPython3.12 builds**. The verifier outputs:
`independent_build_proven=false`,
`fresh_build_on_python312_proven=false`,
`source_package_version_promoted=false`,
`install_authorized=false`,
`public_release_authorized=false`,
`live_trading_authorized=false`.

## Actually executed evidence in the disposable sandbox

1. **Two separate real `setuptools` Wheel builds** from **the same 226-module *synthetic* source fixture**, staged twice into different private directories with `SOURCE_DATE_EPOCH=1792100000` and `PYTHONHASHSEED=0`. Both builds completed using the locally installed Python3.13 wheel toolchain. Only this fake-source diagnostic used `pip wheel --ignore-requires-python`; this switch **was not** added to any GitHub packaging script or release installer.
2. Exact independent build results:

| Measurement | Build 1 | Build 2 |
| --- | --- | --- |
| Module contents | **226 synthetic files** | **226 synthetic files** |
| Wheel ZIP members | **231** | **231** |
| Wheel size | **1,412,969 bytes** | **1,412,969 bytes** |
| SHA256 | `3dd8009c57e0c3bd37fb5d9872e60b04c9e0f4cf40668b952db1a2933983eff2` | **identical** |
| ZIP/RECORD verification | **PASS** | **PASS** |

These are **distinct build operations on one disposable environment, not independent builders**, not real repository source and not Python3.12 runtime evidence. They show the package tooling can produce bit-identical Wheels with fixed timestamp and hash seed for this controlled input. This Wheel hash MUST NOT be used as a production release hash or publisher signature pin.

3. The previously tested 80 source/signature/staging/overlay test cases were run again, together with **16 new dual-Wheel cases**, giving **96 passed in 10.82s** on CPython3.13.5.
4. The exact two files committed to GitHub were re-fetched and their Git blob SHA-1 hashes matched the locally executed files, without filename-based assumptions:

| File | Git blob SHA-1 | Local tested SHA256 |
| --- | --- | --- |
| `scripts/mmt_v040_dual_wheel_repro_audit_v1.py` | `ba5857622c97254883b97fbbdce5d75d8831dd17` | `9a83effc073af522a508c705de0da83eb60868237b53147c3966ddbd063827a8` |
| `tests/unit/test_mmt_v040_dual_wheel_repro_audit_v1.py` | `253c8b4c3822d4d454aa7bb618db6f8c8b7ad43e` | `1a605d6590b14cc9f466f24980ed57f3c94605edfad96f0a1414eba029d2a3ee` |

## Mandatory release gates still open

1. Obtain a **full real-source clean Git checkout** pinned to the final reviewed SHA, in a disposable nonproduction **CPython 3.12** nonroot host. Run syntax/Ruff/all repository tests, old A6/R35–R38/R42V and the new signed stable gates.
2. Build the actual full source 226-module `multi_market_trading-0.4.0-py3-none-any.whl` twice using declared pinned `setuptools==80.9.0` / `wheel==0.45.1`, with no `--ignore-requires-python` bypass; compare complete bytes and RECORD and capture independent job/host provenance. Re-run the new Stage2J dual-Wheel gate against those actual artifacts.
3. Verify approved real public-key trust/SPKI pins and revocation policy, the independently attested exact Git source/overlay digest, install Wheel nonroot in a new offline venv, check disabled CLI and perform bounded PAPER/rollback/restart tests.
4. Preserve historic `crypto-price-action==0.3.2`, the frozen source manifest and production server. **Do not merge Draft PR #352 or create the official `v0.4.0` tag** until the above acceptance is actually demonstrated.

**Decision: `NOT_READY_FOR_MAIN_MERGE_OR_STABLE_TAG`.**
