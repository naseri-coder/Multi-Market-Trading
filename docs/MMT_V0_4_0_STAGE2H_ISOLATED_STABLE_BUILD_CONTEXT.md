# MMT v0.4.0 — Stage 2H: isolated stable build-context staging from pinned RC source

**Date:** 2026-10-17  
**Candidate branch:** `release/0.4.0-candidate`  
**Verdict:** `OFFLINE_STABLE_TEST_CONTEXT_IMPLEMENTED_AND_TESTED__REAL_226_SOURCE_PY312_WHEEL_NOT_BUILT__MERGE_TAG_DENIED`.

## Why Stage 2H was necessary

The real repository declares `multi-market-trading==0.4.0rc1` in `platform_release/pyproject.toml`. Previous v0.4.0 stable signature and custody tests used independently generated **synthetic** package metadata and module fixtures. Renaming the real tracked package to stable before Python3.12/full-suite acceptance would prematurely break historical RC-only A6/R35-R38 attestations. An auditable, isolated stable **test** build context is needed instead.

## Actual code and test commits

- `scripts/mmt_v040_offline_stable_staging_v1.py`: stage an exact **226-module source-to-build context** after read-only `mmt_v040_public_source_snapshot_audit_v1.audit` validates independently supplied clean Git HEAD, Git subtree SHA-1 and full source inventory lock SHA256. Parse all module syntax/AST and refuse known prohibited private-core imports. Validate strict project name, RC source version, Python3.12-only declaration, empty base dependencies, exact nine public CLI entrypoints, pinned approved extras, setuptools/wheel versions and `setuptools.build_meta`. Require an **exclusively new** private out-of-checkout destination and explicit `MMT_NONPRODUCTION=1`, without any `MMT_PRODUCTION` variable. Only in the **new copied** `pyproject.toml` change the exact single literal `version = "0.4.0rc1"` to `version = "0.4.0"`. Copy all 226 source modules **byte-for-byte**. Do not build/sign/install/start a Wheel, modify the clean source, or authorize public/LIVE/Telegram access.
- `tests/unit/test_mmt_v040_offline_stable_staging_v1.py`: 10 test cases on temporary real Git repositories containing 226 synthetic modules: successful exact staged copy and preserved RC source; dirty source, wrong subtree pin, wrong source-lock SHA256, any explicit production setting, existing destination, private source tree replacement, already stable source metadata, unapproved build backend and standalone malformed Python syntax refusal.

The test file was first authored with an absolute path to a disposable fixture directory. **This was corrected before final acceptance**: the committed file reads the checkout-relative `platform_release/pyproject.toml`. Tests were rerun after that correction; no hardcoded assistant sandbox paths remain in the checked-in tests.

## Real executable evidence (independent disposable assistant container)

Runtime: **CPython 3.13.5**, pytest and installed setuptools; **Python3.12 and Ruff are absent**, and outbound GitHub DNS/clone is disabled. No Telmivo server, GitHub Actions, production DB, broker or Telegram connection was used.

1. New staging test suite: **10/10 PASS** (final checkout-portable bytes).
2. **Real setuptools-built Wheel rehearsal**: created a source checkout with 226 synthetic `naseri_markets/*.py` modules, committed a clean source tree and private snapshot lock, ran the new stager with external pins and produced an **isolated stable `0.4.0` build context** while leaving the source's `0.4.0rc1` metadata unchanged. Actual `pip wheel --no-build-isolation --ignore-requires-python --no-deps` build (the bypass applies ONLY to this Python3.13 **synthetic** rehearsal) returned status 0; resulting ZIP had **231 entries** (226 Python modules + 5 dist-info). **226/226 Wheel module bytes matched the original synthetic RC source** and the v0.4.0 verifier's ZIP + RECORD validator passed. The isolated Wheel SHA256 varies with build timestamps and is **not** a signed release artifact.
3. Combined four complementary executed suites: **68/68 PASS in 5.40 seconds** — 10 new stage tests, 11 pinned-source inventory tests, 9 signed-source/Wheel custody tests and 38 stable Ed25519 signed-artifact tests, on CPython3.13.5 with isolated test keys and disposable repositories.
4. Actual GitHub files re-fetched and matched locally tested Git blob hashes byte-for-byte:

| File | Verified Git blob SHA-1 | Tested file SHA-256 |
| --- | --- | --- |
| `scripts/mmt_v040_offline_stable_staging_v1.py` | `9aa0a2e1f5e5024dd163854a3697e8853a36f721` | `b7ee73c67e6ba5079784237db600614333674f5301c04d5dfb06bc2103a3fe9b` |
| `tests/unit/test_mmt_v040_offline_stable_staging_v1.py` | `aa42ca65c4b1585818788fb80690512173e40641` | `52a4bfffc8f469e79c38a2a421f773496d614eae846ecdd399a7e337e70c8377` |

## Actual v0.4.0 release blockers — NOT satisfied here

1. **The actual source contents of all 226 GitHub modules have not been materialized into the test runner.** Only their real GitHub paths/blob hashes/byte sizes were checked through the authorized GitHub connector in Stage 2G. The 226 source bodies in this Stage 2H build were deliberately synthetic.
2. No independent **real CPython 3.12** package installation, Ruff, all-project pytest suite, old R35–R38, PostgreSQL, R42V, 32-restart PAPER, Docker nonroot host, real signer identity or rollback proof was executed.
3. The isolated RC→stable overlay creates a **test build context**, **not a publisher-approved stable Git source commit**. The original stable source/Wheel custody checker intentionally requires `version=0.4.0` in the Git checkout; it will **not** attest a stable Wheel against an unmodified RC Git commit without a separately reviewed overlay-provenance adapter. Do not bypass this boundary or claim the test-only overlay grants release provenance.
4. The source package, main branch, legacy `crypto-price-action==0.3.2` and original `production_source/SHA256SUMS` remain unchanged. No stable `v0.4.0` tag, release, merge, production service, public Telegram or LIVE order was created.

**Next acceptance gate:** obtain an exact full-source checkout and an approved nonroot CPython3.12 runner, execute the stager and a truly **full-source stable test Wheel** without Python version bypass, independently attest the reviewed overlay/provenance and all Wheel bytes, then repeat full offline/PAPER/security/recovery tests. Keep PR #352 Draft until this is proven.
