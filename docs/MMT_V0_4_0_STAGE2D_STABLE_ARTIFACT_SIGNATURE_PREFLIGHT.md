# MMT v0.4.0 — Stage 2D: independently tested stable signed-artifact preflight

**Date:** 2026-10-17  
**Target:** repository release tag `v0.4.0`; Python distribution `multi-market-trading==0.4.0`.  
**Status:** `STABLE_ARTIFACT_READONLY_PREFLIGHT_SYNTHETIC_TESTED__REAL_BUILD_AND_RELEASE_DENIED`.

## Code committed on the release candidate

- `scripts/mmt_v040_signed_artifact_preflight_v1.py`: a **new, read-only verification contract for exact stable `0.4.0` artifacts**, independent from the historical R35–R38 RC-only `0.4.0rc1` installer. Nothing installs, loads the target wheel into Python, starts a worker, sends Telegram, trades, or authorizes public release.
- `tests/unit/test_mmt_v040_signed_artifact_preflight_v1.py`: **32 test cases** using ephemeral, freshly generated Ed25519 keys and synthetic in-memory wheels/RECORD manifests. No production keys and no real accounts.

The new stable signature domain is `MMT-V0.4.0-STABLE-ARTIFACT-MANIFEST-V1\n`, completely distinct from the R37 preview domain. A manifest must be canonical exact-field JSON with immutable distribution, version, purpose, exact external source commit pin, epoch, stable filename, SHA256 of whole wheel and separately pinned wheel RECORD SHA256, and size. The Ed25519 key must independently match an externally supplied DER/SPKI SHA256. A **separately SHA256-pinned, canonical trust-policy file** must list the key as active, not revoked, and reject stale evidence. Forged, incorrectly signed or old RC-domain manifests are rejected.

The stable wheel must have an exact `multi_market_trading-0.4.0-py3-none-any.whl` name, `multi_market_trading-0.4.0.dist-info` paths, all known CLI entrypoint names, `Requires-Python: >=3.12,<3.13`, allowlisted `naseri_markets/*.py` source members, safe ZIP entry types and bounds. The nested source/manifest RECORD rows, hashes and byte sizes must match; optional `telegram-admin` and `brooks-offline` dependencies must exactly match reviewed pinned versions. Explicit private NY-First-Reversal module filenames are refused.

No `MMT_PRODUCTION` assignment of any value is permitted. All successful output flags remain explicitly `false` for install, publication, LIVE, Telegram and filesystem writes.

## Actual executable evidence, without claims about unavailable tooling

**Executed in the assistant's isolated container using Python 3.13.5, pytest and cryptography:** `32 passed in 0.16s` for the exact two files committed to GitHub.

Command used on the isolated staging copy:
```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest -q -c /dev/null -p no:cacheprovider \
tests/test_mmt_v040_signed_artifact_preflight_v1.py
```
Also ran `python -m py_compile` on the validator and test module without error.

**Exact-byte Git Blob identity independently verified after GitHub uploads:**

| File in release branch | Git blob SHA-1 | SHA-256 of tested bytes | Size |
| --- | --- | --- | --- |
| `scripts/mmt_v040_signed_artifact_preflight_v1.py` | `42e6ef97383f25c8c5e49157e73d71c77955019f` | `63d414c8da5c7428ab1af66342c76fd76d715011a3388acee922d9c2402286e6` | 18166 |
| `tests/unit/test_mmt_v040_signed_artifact_preflight_v1.py` | `65cfa264a599da43a26f20d65b70855a39cb19bc` | `81bc33ee861ec92d994f1f685b2f2bce12aaad5d31424d68bb2569e7f64c5dba` | 16217 |

Note the local sandbox test file was under `tests/` for independent pytest discovery; its GitHub location is `tests/unit/` and its **bytes are identical**.

### 32 synthetic cases cover

Positive Ed25519 verification with read-only no-release proof; rejection of all explicit production settings; missing operator opt-in; external manifest/policy pin mismatch; RC-domain signature replay; forged signatures; revoked/untrusted/wrong-signing key; old epoch; wrong release version; duplicate/noncanonical JSON; mismatched source commit; corrupted wheel; wrong wheel filename; RC metadata masquerading as stable; tampered RECORD; unsafe paths/ZIP symlink/private module filename; CLI output not granting installation/LIVE; malicious/unknown optional dependency marker and versions; duplicated wheel version header.

All test keys are synthetic. **None of this proves a real user-controlled signer is provisioned or a production release exists.**

## Explicit unresolved release gates

1. **Real Python3.12 nonroot full-project test matrix** and Ruff were NOT run; independent runner could not resolve GitHub network. The 32 standalone Python3.13.5 test cases are real but **not** a 3.12 or full-project acceptance certificate.
2. `platform_release/pyproject.toml`, `Dockerfile.platform`, `compose.platform.yaml` and R35–R38 historical tools still refer to `0.4.0rc1`. **No new stable wheel was built or installed;** the v0.4.0 verifier was exercised against correctly shaped synthetic test wheels only.
3. A signed manifest's source-commit field is a **signer assertion**, not independent source-to-wheel custody. This verifier checks signed artifact bytes and metadata, but an isolated R36-equivalent proof of a clean exact Git checkout, source→built wheel file identities, deterministic dual builds, artifact upload and independent signer trust is still mandatory.
4. Verified trust roots, real nonroot signed installer, atomic rollback, 32-restart PAPER soak, PostgreSQL, R42V pin checks, and actual provider/region eligibility are outstanding. Rootless/gVisor untrusted execution remains denied.
5. The `v0.4.0` stable tag and official GitHub release are **NOT** created. Draft PR #352 must not be merged until all scoped security, packaging and runtime acceptance gates are satisfied.

**Next stage:** verify stable wheel metadata against an actual independently rebuilt `multi-market-trading==0.4.0` on Python3.12, do strict signer/revocation checks with a separately approved key, then full offline/PAPER integration. Keep `main`, the v0.3.2 public release, historical digest manifest, credentials and Production unchanged.
