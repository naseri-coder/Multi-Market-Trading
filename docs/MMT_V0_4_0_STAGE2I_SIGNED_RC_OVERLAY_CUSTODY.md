# MMT v0.4.0 — Stage 2I: Signed RC→stable overlay custody

**Date:** 2026-10-17  
**Repository:** `naseri-coder/Multi-Market-Trading`  
**Release branch:** `release/0.4.0-candidate`  
**Verdict:** `SIGNED_RC_TO_STABLE_OVERLAY_CUSTODY_TESTED__REAL_SOURCE_PY312_PENDING__RELEASE_DENIED`

## What this fixes

The Stage 2F standalone `mmt_v040_source_wheel_custody_v1.py` deliberately required the Git checkout's `platform_release/pyproject.toml` to be stable `0.4.0`, whereas the project's **real** tracked packaging metadata remains `0.4.0rc1` until release acceptance. The Stage 2H staging tool can apply an exact RC→stable version edit only in a new disposable directory, but could not independently prove that an externally signed stable Wheel came from the **original, clean pinned RC Git commit** plus that one approved metadata edit. This missing custody link is the focus of Stage 2I.

### Actual additions

- `scripts/mmt_v040_rc_overlay_signed_custody_v1.py`: new **read-only** auditor. Validates independently pinned, canonical stable-domain signed manifest, Ed25519 key fingerprint and revocation policy; signed Wheel hash and RECORD; independently pinned exact clean RC Git HEAD, real 226-module subtree hash and complete snapshot lock; the **one and only exact `version = "0.4.0rc1"` → `version = "0.4.0"` metadata transformation**; and byte-for-byte equality of **all 226 Git Python source modules** to the modules in the signed stable Wheel. Each source module undergoes the existing AST/private-import check. The signed Wheel is rehashed on second read and the Git checkout is required to be still clean after verification.
- `tests/unit/test_mmt_v040_rc_overlay_signed_custody_v1.py`: **12** offline tests, including valid signed Wheel custody; wrong independent overlay SHA pin; malformed pin; a **re-signed** tampered module failing Git-to-Wheel byte comparison; re-signed Wheel missing one module; dirty tracked source; wrong public Git tree; forged signature; **historical R37 RC signature-domain** replay even when cryptographically signed; any explicit production variable including `0`; wrong source Git commit; and validation that the CLI has no install/publish operations.

The tool emits `rc_git_commit_is_a_stable_release_commit: false`, `writes_performed: false`, `install_authorized: false`, `public_release_authorized: false`, `live_trading_authorized: false`, and `telegram_publication_authorized: false`. It does not promote, tag, merge, sign, stage, build, install or run the project.

### Exact GitHub packaging-metadata overlay pin (externally reviewed)

Retrieved and byte-matched the actual `platform_release/pyproject.toml` against GitHub blob SHA-1 **`8173a96d589e7d0e7ea9b9ba4a4b7a191b4ec877`** (file size **1650 bytes**). Applying exactly the one permitted version string replacement, and nothing else, produced **stable overlay SHA256**:

`11d87431c863a20514541d8c2eaf70e47555d0ca2e2dbd8d1ded11c994ac01d7`

This digest is an independent **test-stage metadata identity pin**, not a Wheel hash, signer key or live deployment approval. The actual source's descriptive string still calls the package a **preview**, so public-facing stable branding/description remains to be reviewed before a final release.

### Executed evidence

- In an independent disposable container with **CPython 3.13.5**, `pytest`, local Git, `setuptools`, and `cryptography`, executed **80 / 80 tests passing in 6.82 seconds**: 12 new overlay custody cases, 10 existing isolated staging, 11 full-size 226-file snapshot, 9 signed source↔Wheel custody, and 38 Ed25519 stable signed-artifact cases.
- Tests use 226 **synthetic** Python modules in clean temporary local Git repositories, with test-only ephemeral Ed25519 private keys. The **actual GitHub packaging metadata bytes** (not a substitute descriptive fixture) were used in the final rerun after checking the Git blob SHA. The original RC fixture remained byte-identical while the version changed only in an outside-checkout copy.
- Executed a genuine `setuptools` `pip wheel` build from the isolated copy with 226 synthetic Python modules: **231 wheel ZIP entries**. Signed the exact builder-produced Wheel's manifest with a new ephemeral Ed25519 key; verified positive signed RC→stable overlay custody, then tested a wrong overlay SHA and confirmed denial. Resulting test Wheel SHA256 **`7663f0048acb6c322f5f10625316723debd23cd7a695085713c8d79f893b580e`** (disposable and not a reproducibility attestation; Wheel size **56,434 bytes**).
- The Python3.13 fixture-build experiment necessarily used `pip wheel --ignore-requires-python` **only in the disposable test process**. The actual repository build and production installer do not use that flag; this is **not** Python3.12 acceptance.
- Both committed file contents were read back from GitHub and exact Git blob SHA-1 matched the **executed** local bytes:

| File | Git blob SHA-1 | SHA256 of tested content |
|---|---|---|
| `scripts/mmt_v040_rc_overlay_signed_custody_v1.py` | `602f0c32990b4e14825d7b30ac67d479723deb5f` | `6076a3daabe542650e7ca5171a14f2557a643ded7b1b0eb4e2936eae3f938bf4` |
| `tests/unit/test_mmt_v040_rc_overlay_signed_custody_v1.py` | `1e3b5c9986f33bace9b710a5c996a1e117a7522a` | `dc54dcabc52d984523553271d452949235a886006be4267c2b6361c715385b34` |

## Important unresolved release gates — explicit blockers

1. **No complete real 226-file checkout has been cloned in the independent container**; direct GitHub network/DNS is unavailable. Earlier Stage 2G connector-backed real GitHub **paths/hashes/sizes** do match, but **the actual 2,501,524 bytes of source module bodies were not transferred to the test container**. The Wheel in this stage used deliberately synthetic modules; do not conflate module count with actual source verification.
2. **No Python 3.12 installation, Ruff, full real-source package build, Docker image, R35–R38/R42V, live PostgreSQL, PAPER restart/rollback or independent production operator signing-key verification** was performed.
3. The source still declares **`0.4.0rc1`**; the derived `0.4.0` overlay is only a separately pinned preview of the eventual metadata change, **not a separately reviewed immutable stable Git source commit**. Reattest on the exact final commit and real Wheel before public release. Signed manifests alone do not establish publisher authority without externally vetted trust root.
4. A release approver must authorize the stable distribution name, preview-era description, installed CLI behavior, paper/runtime execution, R42V security and release notes. **No protected `main` merge or official `v0.4.0` tag yet.**
5. User server `telmivo`, other servers, GitHub Actions, user credentials, existing `v0.3.2` production state, broker accounts and Telegram have not been accessed.

**Next gate:** obtain a full actual GitHub source checkout and **real CPython 3.12 nonroot** test environment, run these proven source/wheel/signature gate scripts against an actual freshly built `multi-market-trading==0.4.0` candidate, then full package install, offline/PAPER/rollback and independent release signoff.

**Release decision: `NOT_READY_FOR_MERGE_OR_TAG`.**
