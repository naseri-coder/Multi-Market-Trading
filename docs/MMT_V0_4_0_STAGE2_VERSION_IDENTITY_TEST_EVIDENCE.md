# v0.4.0 Stage 2 — exact offline identity compatibility patch (partial acceptance)

**Date:** 2026-10-17  
**Reviewed head before evidence report:** `release/0.4.0-candidate@a04b100c0bdaaec0c2aacf5ce069b984d7527452`  
**Verdict:** `VERSION_IDENTITY_PATCH_APPLIED__INTEGRATED_PY312_TESTS_PENDING__TAG_DENIED`.

## Changes actually committed

- Added `naseri_markets/platform_version_policy_v1.py` with an exact, type-sensitive installed-distribution allowlist: `0.4.0rc1` and `0.4.0`. All other strings, coercible values and unknown version variants raise fixed `UNEXPECTED_RELEASE_VERSION`. No IO, imports beyond `__future__`, network, secret access or dynamic trust in that helper.
- `naseri_markets/platform_cli.py` uses this same version check. It still only exposes inert `--check` and `--engine-plan`, and asserts network/orders/Telegram false.
- `naseri_markets/installed_preview_smoke_v1.py` uses the same exact version check and preserves its existing simulated fixture/safety refusals.
- `naseri_markets/installed_paper_pilot_stage10_v1.py` uses the same check in its preexisting installed-version gate. Explicit nonproduction ACK and the separate five-ledger read-only recovery, fail-closed production checks and idempotency gates are untouched.
- Added `tests/unit/test_platform_version_v040_v1.py` with 28 cases, testing exact acceptance, negative identities, CLI inert mode and PAPER production-denial behavior. This full repository test file **has NOT been executed yet**.

## Precise test evidence

- Actual isolated container: CPython **3.13.5**, pytest **9.0.2**, no Python 3.12 or Ruff available; external GitHub hostname cannot be resolved from this container. It was **not** possible to clone the full repository, run the existing test corpus, build a wheel, or execute a genuine Python 3.12 test.
- On the exact independently authored helper source, local focused test run: **18/18 passed** (2 accepted exact versions, 16 refused unknown variants).
- A second local-only check on that same helper and two static source/AST assertions: **20/20 passed**. These two static checks were temporary harness checks and were not committed as the new repo test suite.
- Exact local helper's Git blob SHA-1 **`cf7baad5f0b58ff4fc381af9b926d3f69ce9f73e`**, SHA-256 **`1be68a6545990e57d21f4997b2c77a8ce3484cc8fcb1f5d9707af736648d5f92`**. The independently retrieved GitHub blob SHA-1 on the release branch matches the tested local helper byte-for-byte.
- The **three modified runtime modules and 28-case committed test suite have not been executed in the isolated environment**. They were read back through GitHub and checked to reference the shared helper. Report this as source verification only, not an integration PASS.
- No GitHub Actions workflows were scheduled or charged to the restricted quota.

## What remains deliberately unchanged

- `platform_release/pyproject.toml` is **still `0.4.0rc1`**; stable Python package version is **not** published.
- `pyproject.toml` root remains legacy `crypto-price-action==0.3.2`. Current frozen 359-entry `production_source/SHA256SUMS` remains unchanged.
- A6 isolated installer/preflight, R35–R38 checksum/signing and provenance tools, README image/version and many release workflows still explicitly validate the *original* `0.4.0rc1` wheel identity. These tools must not be loosened or search-replaced to make an untested stable artifact pass.
- R42V reviewed source hash pins, LIVE/public signal release-denial policies, rootless host rejection, private NY First-Reversal exclusion, no automatic network startup and the installed PAPER run modes were not promoted.

## Next acceptance gates (REQUIRED before merge/tag)

1. Obtain an approved independent **nonroot Python 3.12 + Ruff** runner / full checkout matching the final candidate SHA. Run **all 28 new tests**, existing A6 + Stage10, R42V pinned 59-case suite, lint and full unit/PostgreSQL tests.
2. Complete a separate narrowly scoped **version-transition installer patch** that reconciles A6, R35–R38 artifact identity, Python wheel metadata, Docker/Compose, public-facing CLI/docs and relevant pinned test/CI contract. Keep old historical RC evidence intact; stable change must not bypass cryptographic checks or silently accept both RC wheels as the same signed artifact.
3. Run fresh nonroot wheel build/install, verify exact wheel metadata and source → RECORD → SHA256/signature; restore/rollback and 32-restart PAPER run; verify original Brooks V5 source and private-module exclusion.
4. Address remaining source, supply-chain, plugin isolation and protected-main merge gates; **do not** create `v0.4.0` or move `main` without all necessary evidence.

**Scope is strictly offline/PAPER. A stable GitHub tag would never itself authorize LIVE trading.**
