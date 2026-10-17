> **Follow-up evidence on 2026-10-17:** Both independent GitHub PostgreSQL workflows are now **SUCCESS (7,658 passed / 6 skipped each)**, and CERT-A5 separately passed **16** tests. The next Public Test Corpus issue was isolated to the order of its frozen `app` materialization and Ruff step. See [updated independent runner report](docs/MMT_V0_4_0_STAGE2X_INDEPENDENT_PG_GREEN_AND_PUBLIC_CI_ORDER.md).

# MMT v0.4.0 — Stage 2X GitHub runner evidence and Wheel backend repair

**Date:** 2026-10-17. **Base product SHA:** `f8d3883c86b17b707d97fdd07253c645f4eb9886`. **PR #352 remains Draft and unmerged.**

**Verdict:** `INDEPENDENT_POSTGRES_MIGRATIONS_CONFIRMED__OFFLINE_CI_BACKEND_FIX_TESTED__RELEASE_STILL_DENIED`.

## 1. Newly recovered independent execution evidence

An authenticated examination of **already completed GitHub Actions jobs** for the exact product SHA found independent Ubuntu 24.04 CI runners with actual PostgreSQL 16 testing. This corrects the narrower on-host-only observations in the earlier Stage2X partial report. **No new workflow run was manually dispatched here.**

| Genuine GitHub Actions run | Observed result |
| --- | --- |
| [Full Corpus — Disposable PostgreSQL](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39046668509) (job 117436658576) | **2 temporary PostgreSQL databases migrated to Alembic revision `20261013_0023`, PASS**; complete corpus **7,653 passed / 1 failed / 6 skipped** |
| [Native PostgreSQL 16 — no Docker Hub](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39046668538) (job 117436658434) | **2 temporary PostgreSQL databases migrated to revision `20261013_0023`, PASS**, over local Unix sockets; complete corpus **7,653 passed / 1 failed / 6 skipped** |
| [CERT-A5 fixed benign replay](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39046668493) (job 117436657880) | **16 passed**, including real multi-language fixture replay, on an actual GitHub-hosted nonproduction runner |

The two full-corpus executions ran `python -m pytest -q` against migrated PostgreSQL databases and their **only failed case** was the same package-build rehearsal test. The six skips were the four CERT-A5 opt-in test cases (covered in the separately successful CERT-A5 workflow) and the **two public market-data opt-in smoke tests**, which remain unexecuted.

**Important:** the full GitHub CI workflows remain **FAILED**, not accepted. This evidence confirms meaningful coverage for earlier locally skipped PostgreSQL and ephemeral-runner cases, but does **not** establish green CI, rollback or publisher-signature authority.

## 2. Failure root cause verified from both full CI job logs

Both full CI workflows failed at:

`tests/unit/test_mmt_v040_dual_real_setuptools_build_rehearsal_v1.py::test_two_independent_setuptools_invocations_match_signed_rc_overlay`

The test invokes `pip wheel --no-index --no-deps --no-build-isolation` twice. On GitHub's Python 3.12 host it returned `BackendUnavailable: Cannot import 'setuptools.build_meta'`. Disabling build isolation deliberately requires **setuptools and wheel to already be installed in the same invoking Python environment**. The workflows previously installed only `.[dev]`, which did not guarantee a globally importable, exactly pinned build backend.

## 3. Minimal fix confined to two CI workflows and one test

Immediately after editable development installation, both workflows now provision **`setuptools==80.9.0`** and **`wheel==0.45.1`** with `--no-deps`. A mandatory preflight imports `setuptools.build_meta` and verifies those exact installed versions before the full pytest corpus.

New regression file: `tests/unit/test_mmt_v040_ci_noisolation_backend_pins_v1.py`, with four cases confirming both workflows retain exact pins, import checks and fail-closed rejection of deleted/weakened pin lines.

**Actual local execution:** nonroot Python 3.12, network disabled, pinned build dependencies in the venv: **5 passed in 5.78s** (four new workflow contract tests plus the original **real dual setuptools Wheel build rehearsal**). Ruff and AST compilation passed for the new test. Both YAML files parsed successfully with PyYAML 6.0.1. **Zero changes** to the 226 public modules or the locked source tree `511e9346d88280f3be7c80367f8822a8eaa24dd7`.

This local success proves the fix is plausible and exercises the previously failing case. It does **not** yet prove that GitHub CI becomes green on this new commit. Do not manually re-run large GitHub workflows just to spend quota.

## 4. Further mandatory release evidence

- Verify fresh, actual GitHub-hosted full-corpus and PostgreSQL jobs succeed on the reviewed fixed SHA when quota permits; do not count old red jobs as green.
- Keep the two public-data smoke tests separate and opt-in. Never use private exchange credentials without explicit approval.
- Independently prove real schema rollback and installed PAPER recovery/restarts; successful migration upgrades alone do not prove downgrade safety.
- Obtain a verified independent software publisher signature and supply-chain identity. Synthetic signing tests are not sufficient.
- Keep PR #352 **Draft/open/unmerged**. No protected `main` change, `v0.4.0` release tag, deployment, real Telegram broadcast or LIVE trading.

**Phase status:** `STAGE2X_PARTIAL__FULL_CI_GREEN_PENDING__RELEASE_DENIED`.

Machine-readable companion: `docs/evidence/MMT_V0_4_0_STAGE2X_GITHUB_CI_RECONCILIATION.json`.
