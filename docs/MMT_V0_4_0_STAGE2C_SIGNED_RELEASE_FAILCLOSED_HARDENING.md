# MMT v0.4.0 — Stage 2C R35–R38 fail-closed admission hardening

**Date:** 2026-10-17  
**Branch:** `release/0.4.0-candidate`  
**Status:** `OFFLINE_SECURITY_PATCH_COMMITTED__FULL_INTEGRATION_TESTS_PENDING__V0_4_0_TAG_DENIED`

## 1. Production mode guard inconsistency and fix

Before this stage, **R35** and **R36** denied only `os.environ.get("MMT_PRODUCTION") == "1"`, whereas R37/R38 correctly denied **any explicit presence** of `MMT_PRODUCTION`. The legacy development installer shell guard also rejected only `== 1`. Thus `MMT_PRODUCTION=0`, `false` and empty assignments were not uniformly refused by R35/R36 and the development installer.

Modified:
- `scripts/mmt_r35_offline_preview_install_v1.py`: use `"MMT_PRODUCTION" in os.environ`.
- `scripts/mmt_r36_offline_release_provenance_v1.py`: the same explicit-presence denial.
- `scripts/install_platform_dev.sh`: Bash `[[ -v MMT_PRODUCTION ]]` blocks any defined value, including empty.
- `tests/unit/test_mmt_v040_packaging_transition_v1.py`: update the installer-presence regression.
- New `tests/unit/test_mmt_v040_prod_env_hard_denial_v1.py`: 6 parametrized setting cases on **all four** R35/R36/R37/R38 guards before file I/O; plus explicit-ACK positive/negative and static shell inspection (8 pytest cases total).

This is a *deliberate fail-closed policy change*, not a switch on production features.

## 2. Bounded JSON nesting / error normalization

The R37 signed manifest parser and R38 pinned revocation policy parser previously handled `ValueError`, type and Unicode errors, but could propagate `RecursionError` from JSON decoder/encoder on maliciously deep bounded input. They now normalize parser and canonical encoder recursion into explicit `R37_INVALID_MANIFEST_JSON` / `R38_POLICY_JSON_INVALID` refusals. The underlying SHA256, signature verification, independently pinned public-key fingerprint, revoked-key checks, and nonproduction-only policies **remain unchanged**.

New `tests/unit/test_mmt_v040_signed_json_depth_v1.py` contains **10 cases**: six malformed deep JSON objects (1100/1300/1500 levels per role), two forced decoder recursion errors, and two forced encoder recursion errors. On Python versions whose JSON C parser accepts those deep structures, the expected denial is the existing invalid-schema/invalid-value refusal, not a fake recursion claim. These committed test cases are **not yet executed against the full repository code**.

## 3. Testing actually performed in independent assistant sandbox

The current disposable sandbox only provides **Python 3.13.5** and no local Python 3.12 or Ruff; GitHub public DNS/git clone is unavailable. The user production Telmivo server was intentionally **not** touched.

Actual standalone checks (separate from the committed tests):
- Bash `[[ -v MMT_PRODUCTION ]]` gate evaluated for values `0`, `1`, `false` and empty, and rejected all four; unset key under `MMT_NONPRODUCTION=1` passed. **5/5 standalone shell decisions passed.**
- CPython 3.13 JSON decoder accepted deep 1100/1300/1500-bracket fixtures and re-encoded those structures. This **disproved an assumption** that those fixture inputs must independently trigger RecursionError; test expectations were corrected to accept the appropriate fail-closed structural refusals.
- GitHub branch source re-read confirmed all three environment guards and R37/R38 parser/encoder exception handlers are present; no wholesale source refactoring or signed-wheel installation occurred.

**Not run:** the 18 new pytest cases, full existing R35–R38 tests, actual Python 3.12/Ruff, nonroot wheel installation, Ed25519 positive/negative signed integration on the integrated head, full PostgreSQL corpus, R42V and PAPER recovery/soak. Do not report these as PASS or unlock the release.

## 4. Remaining critical release work

1. Run full source checkout, exact SHA, **real CPython3.12 nonroot** with `pytest`, `ruff`, `cryptography`; execute 18 new pytest cases and every existing A6/R35/R36/R37/R38 test. Confirm changes have not weakened legitimate signed RC acceptance.
2. Build twice; confirm deterministic wheel payload, RECORD consistency, source SHA pin and signature; test R38 valid/corrupted/revoked-signature boundary and owner-private install on independent disposable nonproduction host.
3. Add a **separately domain-separated versioned stable v0.4.0 verifier/manifest**, rather than pretending RC-only `0.4.0rc1` R35/R37/R38 verifier applies to v0.4.0; test downgrade/replay and revocation.
4. Repeat full broker-denied PAPER recovery, installed clean wheel, exact R42V and Python3.12 acceptance, then reviewed PR #352 and protected-main merge.
5. Create official `v0.4.0` tag only **after** the final main commit has passed all release-blocking gates; no production DB migration or live/public order/Telegram permission implied by tag.

**Release verdict: `NOT_READY_FOR_MERGE_OR_STABLE_TAG`.**
