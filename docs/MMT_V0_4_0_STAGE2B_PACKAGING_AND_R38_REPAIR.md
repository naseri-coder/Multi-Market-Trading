# MMT v0.4.0 — Stage 2b packaging transition and signed installer syntax repair

**Date:** 2026-10-17  
**Scope:** `release/0.4.0-candidate`; no `main` merge, no tag, no GitHub Actions, no production access.  
**Verdict:** `RC_STABLE_STAGING_READY_FOR_TESTS__R38_SYNTAX_REPAIRED__SIGNED_STABLE_INSTALL_NOT_YET_IMPLEMENTED`.

## Defect found and fixed (actual code change)

The existing `scripts/mmt_r38_signed_offline_preview_install_v1.py` began its import section with:
```python
import osfrom pathlib import Path
```
This is a Python **SyntaxError**, preventing importing the signed-preview installer and preventing R38 acceptance tests from collecting. Fixed to the two separate statements:
```python
import os
from pathlib import Path
```
The remainder of the installer policy, signature, revocation, read-only preflight and nonroot acknowledgement code was preserved. No signature verifier was bypassed.

The new test `test_r38_signed_preview_installer_is_parseable` in `tests/unit/test_mmt_v040_packaging_transition_v1.py` will detect recurrence with an `ast.parse` check.

## Package/version metadata convergence (actual code changes)

- `scripts/a6_release_preflight.py` now accepts only exact `0.4.0rc1` and `0.4.0` for the separate `multi-market-trading` platform distribution; the root legacy `crypto-price-action==0.3.2` check, exact entrypoint allowlist, empty base dependencies, Docker isolation, and lack of source migration remain.
- `scripts/a6_prepare_package.py` now reads and parses `platform_release/pyproject.toml`, rejects unknown names/versions and nonempty base dependencies **before creating its destination**, and records the exact reviewed metadata version in the staging report.
- `scripts/install_platform_dev.sh` now obtains an exact version from its A6-validated metadata, selects the correspondingly named wheel, and checks the installed distribution's exact version. It **still requires** explicit `MMT_NONPRODUCTION=1`, a nonroot operator, fresh isolated destination and `--ack-isolated-dev-install`; it is a **development** installer and does not certify a stable release. It was not executed here.
- Added `tests/unit/test_mmt_v040_packaging_transition_v1.py` with **11 new parametrized test cases**: two RC/stable staging cases; five invalid version denials; two deferred-dependency refusals; one R38 source parse; one developer-installer guard check.

### Direct GitHub source verification

Fetched the exact branch files after commits and evaluated **14 / 14 static source-consistency assertions**: root old version, preview metadata unpromoted, exact A6 allowed versions, dynamic staging version, safe installer wheel binding, inherited nonroot guard, unchanged R35/R37 RC artifact pins, R38 syntax-repair text and new test source.

This 14/14 result is **source-text validation only**: it does not mean `pytest`, Python parser across all files, Ruff, a Linux-installed wheel, gVisor, PostgreSQL, cryptographic signing or rollback was executed. The new 11 tests have been committed, but not executed in an environment with a full checkout; do not label them PASS.

## Signing policy and important blockers

- **The historical R35, R36, R37 and R38 artifact checks remain `0.4.0rc1`-pinned.** Do not rewrite their constant signature domain, source pins, manifest schema, expected filename, public-key trust policy or test fixtures merely to accept a stable wheel.
- Promoting to **`0.4.0`** requires an independent, explicitly versioned stable artifact trust contract, signed manifest carrying `version=0.4.0` and the **actual final wheel SHA256**, wheel RECORD/package metadata comparison, external trusted key SPKI pin and active/revoked policy. No `v0.4.0` tag before that proof.
- `Dockerfile.platform` / `compose.platform.yaml` still identify `0.4.0rc1`. Do not publish their old RC output as a stable image; a coordinated build review and independent container test must precede their final version change.
- `naseri_markets/release_readiness_v1.py` continues to deny product-level public/LIVE readiness; the compatibility A6 preflight is **not** a product release authorization.
- `platform_release/pyproject.toml` remains `0.4.0rc1`. Frozen 359-line current Brooks historical manifest and root `0.3.2` are untouched.
- Existing `tests/unit/test_mmt_r38_signed_offline_preview_install_v1.py` imports R38 and has extensive signed/negative-policy tests; these must be executed on real Python3.12 with cryptography and a separately approved nonproduction host before relying on the repaired R38.
- No installed-wheel/restart/PAPER/PROD proof was generated in this step.

## Exact next gates

1. Obtain actual disposable nonroot **CPython 3.12**, `ruff`, `pytest`, signing library and a clean checkout pinned to the release-candidate SHA. Run **11 new tests**, existing R35/R36/R37/R38 suites, A6 tests, plus all prior Stage2 focused tests and full suite. Do not trigger Actions solely to bypass user quota.
2. Build `multi-market-trading==0.4.0rc1` twice from source in offline dependency closure. Independently check exact file bytes, wheel ZIP member set, WHEEL/RECORD, signatures and dependency metadata. Execute signed R38 nonroot dry-run only with disposable test keys and no provider credentials.
3. Define and test a distinct **stable `v0.4.0` signing and wheel verification contract**, avoiding downgrade/replay of RC artifacts. Then transition pyproject metadata, installers, optional Docker image, CLI smoke and release notes atomically.
4. Run fresh install → disabled CLI → bounded PAPER synthetic/Brooks replay → duplicate/refusal → restart → rollback, pinned source SHA and private-engine exclusion. GitHub protected-branch approval and final exact-SHA sign-off are still blocking.
5. Leave PR #352 Draft; no `main` change, GitHub tag, live orders, Telegram messages, user accounts or production DB changes.

**Do not confuse a developer-install compatibility patch with an externally signed stable release.**
