# MMT v0.4.0 — Stage 2X: independent PostgreSQL CI green and public Ruff gate correction

**2026-10-17** · **PR #352 remains Draft/open/unmerged** · Product source `f8d3883c86b17b707d97fdd07253c645f4eb9886`

## Independent runner and genuine database evidence

The previously red dual-PostgreSQL GitHub Actions workflows became **SUCCESS** after the pinned `setuptools==80.9.0` and `wheel==0.45.1` CI installation fix committed in `f909c1e6635bee6558eab727505c456332f2d930`:

- [Full Corpus — Disposable PostgreSQL](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39049609548), job 117445334973: **7,658 passed, 0 failed, 6 skipped**. Real Alembic upgrades of **two** ephemeral PostgreSQL 16 databases through revision `20261013_0023`, cleanup PASS.
- [Native PostgreSQL 16 — no Docker Hub](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39049609341), job 117445333689: **7,658 passed, 0 failed, 6 skipped**. Separate genuine GitHub-hosted, socket-only PostgreSQL 16 runner; **two** ephemeral databases upgraded to revision `20261013_0023`, cleanup PASS.
- [CERT-A5 fixed benign replay](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39049609549), job 117445334716: **16 passed**, using a genuine GitHub-hosted runner. Those harmless replay tests were skipped inside the general corpus because they require explicit opt-in; their independent workflow provides separate real coverage.

Both full-corpus workflows executed the pinned backend preflight and the formerly failing real two-Wheel rehearsal successfully. **Do not add their pass totals together as distinct tests.** The six skips in each full corpus were **four CERT-A5 cases** (covered in its separate workflow) and **two opt-in public-data smoke cases** (not executed). Neither the genuine migration upgrades nor these tests prove safe schema **downgrade/rollback** or a trusted publisher signature.

## Public Test Corpus: remaining 17 Ruff findings were environmental, not product-source changes

The Public Test Corpus workflow for this SHA remained red at [run 39049609401](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39049609401). Its Ruff gate executed **before** the `production_source/app → ./app` materialization, producing **17 `I001` import-group findings**. A clean GitHub checkout reproduced the issue exactly: `RUFF_BASE_FINDINGS=1345`, `RUFF_HEAD_FINDINGS=1362`, `RUFF_NEW_FINDINGS=17`.

Materializing the already-required frozen `app` package **before** the existing Ruff step, without editing any source file, produced `RUFF_HEAD_FINDINGS=1344`, `RUFF_NEW_FINDINGS=0`, `RUFF_NO_NEW_FINDINGS_PASS`. The change is a **reordering of two existing workflow steps**, not disabling Ruff or changing its baseline, permissions or branch protection.

The regression `tests/unit/test_mmt_v040_public_ci_isort_order_v1.py` verifies that the `app` path and the exact main-branch SHA input are present before lint; **5/5 passed** on nonroot Python3.12 with network disabled. PyYAML parsing of the changed workflow succeeded. The **new GitHub run for this second workflow fix has not yet been verified**.

## Outstanding release gates

At the time of this audit eight other GitHub Actions workflows (including Publication safety and some prior Brooks/research workflows) were failing on the first fix SHA; their causes must be resolved or explicitly denied. **True publisher-signature provenance, actual downgrade/rollback, installed PAPER restart evidence and two public market-data opt-in smoke cases remain unverified.**

**Verdict:** `STAGE2X_INDEPENDENT_PG_AND_A5_PASS__PUBLIC_LINT_FIX_LOCALLY_VERIFIED__FULL_RELEASE_DENIED`. Keep PR #352 Draft/open/unmerged. No `main` merge, `v0.4.0` tag, production migration, real Telegram send or LIVE trading.

Structured companion: docs/evidence/MMT_V0_4_0_STAGE2X_INDEPENDENT_GITHUB_CI_GREEN.json
