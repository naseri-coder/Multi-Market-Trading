# MMT v0.4.0 — Stage 2E: real setuptools Wheel metadata interoperability

**Date:** 2026-10-17  
**Target:** a separately installable, offline/PAPER-only `multi-market-trading==0.4.0`.  
**Verdict:** `REAL_WHEEL_METADATA_INTEROP_FIXED__PY312_FULL_SOURCE_ACCEPTANCE_PENDING__TAG_BLOCKED`.

## A. Confirmed bug found only with a real wheel builder

The Stage 2D stable signed-artifact validator `scripts/mmt_v040_signed_artifact_preflight_v1.py` previously compared the exact `Requires-Python` metadata header against one literal:

```
>=3.12,<3.13
```

Real `setuptools` / `pip wheel` metadata generation produced:

```
<3.13,>=3.12
```

These are mathematically equivalent constraints but differ in ordering. **Before the fix, the real builder-produced partial-fixture wheel was rejected with `V040_WHEEL_IDENTITY_INVALID`.** The fixture's package name, version, exact optional dependencies, entrypoints and Python range replicated the project's `platform_release/pyproject.toml`, but it contained only three synthetic `naseri_markets` modules. It is **not** the real full-project wheel, nor a trusted release artifact.

**Fix:** compare precisely the two comma-separated atomic constraints as a sorted two-element list `["<3.13", ">=3.12"]`; reject absent, broadened, extra or otherwise changed ranges. This preserves Python3.12-only runtime policy; it does NOT install or run the product on Python3.13.

## B. Actual test/build evidence

Independent disposable container:
- `Python 3.13.5`, `pytest 9.0.2`, locally available `setuptools 82.0.1` / `wheel 0.46.3` and `cryptography 46.0.4`.
- No Python 3.12 interpreter and no Ruff. Outbound `github.com` DNS/clone not available. User servers, GitHub Actions, production, brokerage and Telegram untouched.
- An initial local `pip wheel` attempt correctly **refused Python3.13**, returning `Package 'multi-market-trading' requires a different Python: 3.13.5 not in '<3.13,>=3.12'`. This is **intended** product compatibility enforcement, not a failure to fix.
- For **metadata-interoperability testing only**, built a *partial synthetic source fixture* with a real `python -m pip wheel --ignore-requires-python --no-build-isolation --no-deps` invocation. The flag was not added to any repository installer or release workflow; it was used solely to examine wheel packaging metadata with the available Python3.13 build interpreter.
- The real-builder fixture produced `multi_market_trading-0.4.0-py3-none-any.whl` (8 entries; SHA256 `580690304c7dfbc96a6651762a0661f751c47f0c686c1a3d7dcffc22fef0ea51`). Before the patch, `_wheel()` rejected it; after the patch, it returned `{"members_verified":8,"record_verified":true}`.
- Generated a throwaway Ed25519 signing key, canonical manifest, exact independent SHA256 policy pins and a detached stable-domain signature for that same builder-produced fixture. New `verify()` accepted it with **all install, public release, live trading, Telegram publication and writes flags `false`**. Replacing the signature with 64 forged bytes produced `V040_SIGNATURE_VERIFICATION_FAILED`.
- Stage 2D test suite originally had 32 tests. Added **6** exact-equivalent-versus-broadened Python-range regression cases. Executed all **38 / 38 passed in 0.20s** on the exact two patched files.
- Independently fetched the two updated GitHub files and verified their blob SHA-1 matches the exact locally tested bytes:

| File | Git blob SHA-1 (updated) | SHA-256 of tested bytes |
| --- | --- | --- |
| `scripts/mmt_v040_signed_artifact_preflight_v1.py` | `5d23421222aa586bbc4c2fc480aaf89f2be6d7ba` | `632750a31167a5b244af5b528431743076218ffea79b2a6087df1cb1bf5d6e42` |
| `tests/unit/test_mmt_v040_signed_artifact_preflight_v1.py` | `7593369d9c53436c57c8ec73d5a2b8c2b467a4c7` | `94ff5612089d4e6cd35299f03e37b2c214a4b9b8ec9b784a944d3525a050f4ec` |

## C. Strict unresolved gates

1. **No complete source checkout, no actual complete v0.4.0 stable Wheel and no Python3.12 nonroot install** was performed. The fixture was missing all strategy/evidence/worker source files. Rebuilt package metadata is not proof of platform packaging completeness, confidentiality or source equivalence.
2. The **actual** project still declares `0.4.0rc1` in `platform_release/pyproject.toml`. The new stable verifier remains independent from RC-only R35–R38. No actual signer trust root, current artifact digest, approval policy, or signed final Git commit exists yet.
3. This stage did **not** run the full repository test corpus, Ruff, existing R35–R38 on Python3.12, R42V, real PostgreSQL, PAPER two-state shutdown/restart/32-cycle soak or rollback. Tests in this report do not count toward those gates.
4. On approved Python3.12 with an exact full GitHub checkout, build the actual candidate twice without bypassing Python compatibility; compare source files to wheel contents/RECORD, pin exact signing source commit and trusted public-key fingerprint, test revocation and replay, perform installed OFFLINE/PAPER and rollback acceptance. Preserve legacy 0.3.2 root and source manifest.
5. Keep draft PR #352 open and `main` untouched. **No official `v0.4.0` tag or release yet**. A stable source/wheel artifact does not authorize public signal delivery, untrusted engines, broker orders or LIVE trading.

**This step fixes a confirmed release-validator interoperability defect using a real packaging tool and test-only fixture, while honestly leaving final package and Python3.12 acceptance outstanding.**
