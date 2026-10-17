# MMT v0.4.0 — Stage 2X exact SHA GitHub CI acceptance, outstanding release gates

**Recorded:** 2026-10-17  
**Examined PR:** #352 — Draft/open/unmerged  
**Tested immutable candidate:** `d4713b58977cbb0dd47eff55a9447c566ff0d5f5`  
**Public source tree:** `511e9346d88280f3be7c80367f8822a8eaa24dd7` (226 modules unchanged)  
**Verdict:** `INDEPENDENT_CI_76_OF_76_PASS__SCHEMA_DOWNGRADE_AND_PUBLISHER_SIGNER_NOT_VERIFIED__RELEASE_DENIED`

## 1. Genuine GitHub Actions now all green

Direct authenticated GitHub API examination of **76 workflow runs attached to the exact commit above** found **76 SUCCESS, 0 FAILURE**. Unlike previous Stage2X partial reports, this is no longer an inference from local-only test environments. The formerly red Stage10 installed PAPER and Stage15/16 historical jobs are green after the CI environment and `pyarrow` pin conflicts were resolved. Do not sum repeated test cases from different jobs into a single number.

| Evidence | Exact external run | Verified outcome |
| --- | --- | --- |
| Complete corpus, disposable PostgreSQL | [39054048151](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39054048151), job 117458272921 | **7,682 passed, 0 failed, 6 skipped**; 38 warnings, 2 subtests passed; **two ephemeral PostgreSQL migrations through `20261013_0023`** |
| Native PostgreSQL 16 on GitHub-hosted ephemeral runner | [39054048264](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39054048264), job 117458273113 | **7,682 passed, 0 failed, 6 skipped**; 38 warnings, 2 subtests passed; **two real ephemeral databases migrated through `20261013_0023`**, clean network isolation and cleanup |
| Installed-wheel two-binding PAPER restart audit | [39054048044](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39054048044), job 117458272563 | **SUCCESS**; marker `STAGE10_CLEAN_WHEEL_TWO_BINDING_REOPEN_PASS_RELEASE_BLOCKED` |
| Installed Brooks→risk→PAPER plus isolated backup/restore/soak | [39054048164](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39054048164), job 117458272835 | **SUCCESS**; `PINNED_BROOKS_INSTALLED_TWO_PROCESS_PAPER_CI_PASS` and `P09_CLEAN_WHEEL_BACKUP_RESTORE_ROLLBACK_SOAK_PASS` |
| Public Test Corpus and new Ruff order | [39054048388](https://github.com/naseri-coder/Multi-Market-Trading/actions/runs/39054048388), job 117458273575 | **SUCCESS** with lint and corpus gates |

The PAPER rollback above means rollback of **disposable PAPER SQLite ledgers**, **not** Alembic/PostgreSQL schema downgrade. The two are distinct release requirements.

## 2. Precisely delimited acceptance gaps

**PostgreSQL forward migration: PASS. PostgreSQL downgrade: NOT VERIFIED.** The real GitHub-hosted jobs prove all 23 forward revisions can reach `20261013_0023` in freshly created PostgreSQL databases. They do **not** prove a safe `downgrade` or upgrade-again cycle, nor a fail-closed downgrade when `retired_strategy_evidence_archive` has rows. Revision `20261013_0023` includes a source-level guard `NONEMPTY_STRATEGY_ARCHIVE_DOWNGRADE_REFUSED`. That guard still requires real database execution and preserved archive verification on a separate disposable nonproduction runner.

**Trusted software publisher signature: NOT VERIFIED.** Successful synthetic signer unit tests and a reproducible Wheel do not prove the final package was signed by the approved publisher or independently validated. Do not load private signing keys onto a shared CI runner.

**Public market-data smoke: 2 test cases remain explicitly opted out.** The six skipped tests in each full corpus comprise four independently covered CERT-A5 opt-in cases and two public-data smoke cases not exercised as part of this acceptance. A separate actual CERT-A5 workflow has passed.

**Protected-main review and packaging metadata:** still require final operator authorization and independent review. The platform preview declares `0.4.0rc1`; target stable release remains `v0.4.0`. No merge or tag has been authorized.

## 3. Safe disposition of blocked on-host migration

The previous Telmivo-connected host safety control explicitly blocked preparation of a migration/downgrade operation. That control was **not bypassed**. Future PostgreSQL downgrade evaluation must occur in an independently authorized, disposable nonproduction environment such as GitHub-hosted CI, not against any production, Telmivo or user data.

## 4. Next release work

- Independently attest a **scratch-only** PostgreSQL nonempty-archive downgrade refusal, empty-archive downgrade, and re-upgrade with unchanged existing archive evidence.
- Validate publisher signing identity and signed artifact bytes using an approved trust chain; synthetic unit keys are not publication authority.
- Obtain separate permission for the two public market-data smoke tests if they are considered release-critical; do not silently waive them.
- Produce a final release authorization after operator and protected branch review, ensuring exact SHA / source custody / reproducible Wheel match the release candidate.

**This document is an evidence update only. No code change, merge, release tag, deployment, Telegram send or LIVE order is authorized.** PR #352 stays Draft.
