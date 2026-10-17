# MMT v0.4.0 Stage 2F — signed-wheel to clean-Git-source custody

**Date:** 2026-10-17  
**Target:** `multi-market-trading==0.4.0` (future stable source/installation)  
**Verdict:** `SOURCE_WHEEL_CUSTODY_AUDITOR_SYNTHETIC_TESTED__REAL_FULL_PACKAGE_PY312_PENDING__RELEASE_DENIED`

## Implemented and committed

1. `scripts/mmt_v040_source_wheel_custody_v1.py`: a **read-only** source custody extension of the independently signed `scripts/mmt_v040_signed_artifact_preflight_v1.py` validator.
2. `tests/unit/test_mmt_v040_source_wheel_custody_v1.py`: 9 test cases using temporary local real Git repositories, ephemeral Ed25519 keys and signed synthetic Wheel files.

The custody auditor:
- Requires `MMT_NONPRODUCTION=1` and absence of the `MMT_PRODUCTION` variable, with no network, no install, no code execution of packaged modules and no output granting production, public Telegram or LIVE.
- Verifies the independently supplied exact manifest/policy hashes, Ed25519 signer fingerprint, signature, key-revocation status, wheel SHA256, RECORD, version `0.4.0` and exact offline entrypoint/dependency allowlist through the Stage 2D/2E stable validator.
- Requires an **actual Git repository**, exact independently pinned Git HEAD and a completely clean `git status --porcelain=v1 --untracked-files=all` (not just the public folder). No writes to the repository by the auditor.
- Requires stable `platform_release/pyproject.toml`: distribution identity, version, Python3.12-only bounds, zero base dependencies, all exact optional dependency pins and nine exact CLI entrypoints. Pinned setuptools/wheel build dependencies and `setuptools.build_meta` are also mandatory; a different backend is denied even on a clean committed checkout.
- Enumerates all *tracked* flat `naseri_markets/*.py` modules, rejects source symlinks, unreviewed or missing members, and compares the **complete source module set plus exact bytes** to the independently signed Wheel ZIP. Rechecks the original signed Wheel hash after reading it again to reject post-verification substitution.
- Emits explicitly false `writes_performed`, `install_authorized`, `public_release_authorized`, `live_trading_authorized`, and `telegram_publication_authorized`.

This addresses an explicit open item from Stage 2D: an Ed25519-signed manifest alone proves what a signer signed, not that its source files equal an independently pinned clean Git checkout.

## Tests actually run

Assistant independent disposable container: **CPython 3.13.5** (no available Python3.12 or Ruff). Local Git and cryptography present. Actual commands, abbreviated:

```bash
PYTHONPATH=/mnt/data/mmt-v040-stage3f PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -q -c /dev/null -p no:cacheprovider \
  tests/test_mmt_v040_source_wheel_custody_v1.py \
  /mnt/data/mmt-v040-stage2d/tests/test_mmt_v040_signed_artifact_preflight_v1.py
```

**47 passed in 0.59 s = 9 new Git-custody cases plus 38 existing signed-stable-artifact cases** (both byte-identical to the checked GitHub versions). Standalone `python -m py_compile` on the custody module and new test file also passed.

The 9 new cases: valid signed source↔Wheel matching, altered signed Wheel module bytes rejected, omitted signed Wheel source module rejected, untracked module rejected, dirty tracked source rejected, wrong external source commit rejected, clean committed RC metadata rejected for stable version, production variable present even with value 0 rejected, and clean committed unreviewed build backend rejected.

**Additional actual builder-based integration smoke:** re-used Stage 2E's *actual setuptools-built* Wheel fixture `multi_market_trading-0.4.0-py3-none-any.whl` SHA256 `580690304c7dfbc96a6651762a0661f751c47f0c686c1a3d7dcffc22fef0ea51`. Copied its **three public modules** into a new clean local Git repo with the equivalent stable pyproject metadata, freshly signed a canonical stable-domain manifest with a temporary Ed25519 test key and pinned trust policy. `custody.audit()` **passed**, verifying 3/3 module bytes and Wheel RECORD with all privilege flags false. Mutating the checkout's `platform_cli.py` after signing caused `V040_SOURCE_CHECKOUT_NOT_CLEAN` rejection. No host, broker, Telegram, real credentials, user server, git Actions or production DB were accessed.

**Exact-byte GitHub custody module/test match:**

| File | Git blob SHA-1 | Local tested SHA-256 |
|---|---|---|
| `scripts/mmt_v040_source_wheel_custody_v1.py` | `461d6021c7e76be0deb31a3cdb4f28f65f876209` | `RECHECK_ON_FINAL_COMMIT` |
| `tests/unit/test_mmt_v040_source_wheel_custody_v1.py` | `cf777998c4711f0ce342c3bc967438620919ff14` | `RECHECK_ON_FINAL_COMMIT` |

The existing stable validator and its 38 tests in this run matched GitHub blobs `5d23421222aa586bbc4c2fc480aaf89f2be6d7ba` and `7593369d9c53436c57c8ec73d5a2b8c2b467a4c7` respectively. All four byte-identical module/test pairs were verified via Git Blob SHA-1, not by simply trusting filenames.

## Deliberate outstanding gates

1. The GitHub release branch still has `platform_release/pyproject.toml` version `0.4.0rc1`; the new custody auditor **would correctly reject it** as a stable `0.4.0` source. No silent metadata promotion was made. The old root `crypto-price-action==0.3.2` is untouched.
2. The 226 actual tracked source Python modules (approximately 2.5 MB) **were NOT downloaded into the isolated runner as a complete checkout**; repository ZIP/Git networking is restricted. None of the 9 cases used the full 226-module integrated wheel. The real-builder integration smoke had three synthetic files only.
3. Actual **CPython 3.12**, pinned build frontend tools, Ruff, full A6/R35–R38 and R42V corpus, PostgreSQL, full-source rebuild twice, operator-trusted signer, wheel installation and PAPER restart/rollback **have NOT been executed**.
4. The separate stable signer and operator public-key fingerprint still need explicit independent approval, a fresh artifact manifest and final immutable source commit. A verified test-only Ed25519 key is not a production signer.
5. Keep PR #352 Draft and deny any `main` merge/`v0.4.0` official GitHub tag or LIVE/public access until all release acceptance gates are met.

**Next step:** obtain a complete clean checkout of the final candidate on an approved disposable CPython3.12 nonroot host, build the real Wheel, sign the exact final artifact using an independently approved release key, then run the new read-only custody gate plus all existing integration tests. Preserve the RC provenance and legacy production release.
