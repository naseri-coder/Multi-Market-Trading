# Changelog

All notable public changes to this project are recorded here.

This project remains under active development and validation. A tagged release does not imply production or live-trading approval.

## v0.3.2 — 2026-10-03

Paper cold-start bootstrap patch.

### Fixed

- Removed the fresh-database Paper-mode deadlock where Historical Probability remained `UNBOOTSTRAPPED` because Paper candidates could not create the causal evidence needed to mature the cohort.
- Allowed only otherwise-qualified, final-cohort stop-trigger candidates whose sole gate blocker is Historical Probability evidence to persist as `SHADOW/INTERNAL` bootstrap observations in Paper mode.
- Added a shadow-only lifecycle service that reuses the causal one-minute entry/exit and realized-R semantics while excluding LIVE/VIP rows and Telegram message update work.
- Kept `BROOKS_OPERATIONS_ENABLED=false`, LIVE publication, and exchange order execution outside the Paper bootstrap path.
- Added regression coverage for Paper/live bootstrap collection, shadow-only lifecycle selection, no Telegram retry work, and Paper runtime lifecycle wiring.

### Safety boundary

Cold-start observations remain internal, do not count toward production performance, and cannot bypass AI Council, Risk, structure/context, entry-method, cohort-isolation, or final Historical Probability gates.

## v0.3.1 — 2026-10-03

Patch release for the fresh-host installer.

### Fixed

- Fixed the in-container release configuration validator so it can import `app.core.config.Settings` from the packaged image layout.
- Added a regression test that executes the validator from an isolated container-like filesystem layout without relying on the repository checkout or installed site packages.
- Updated the Docker/image, installer, source manifest, verification contract, and release documentation to the `0.3.1` patch identity.

### Scope

This patch does not change Brooks trading semantics, database schema, migration history, or runtime enablement defaults. Effectful runtime modes remain disabled by default.

## v0.3.0 — 2026-10-03

The first official v0.3.0 open-source release.

### Highlights

- Completed the reviewed v0.3.0 source-convergence line and published the approved Batch-B research/test wave.
- Migrated current risk/reward research consumers to the typed current-risk contract and preserved historical 88D/88E/88F runner material as inert archived references.
- Updated the Cold Start fallback to the current HP outcome-policy, statistics-contract, and readiness-state model with fail-closed guards.
- Added isolated PostgreSQL full-corpus validation with separate disposable databases and no published database ports.
- Preserved the Alembic migration chain through revision `20260928_0021`.
- Added open-source maintainer, contribution, support, roadmap, project-impact, CODEOWNERS, issue-template, pull-request-template, and release-readiness documentation.
- Retained publication-safety, source-integrity, dependency-lock, Docker-build, CodeQL, and public-test gates.

### Validation snapshot

Before the release-candidate branch was prepared, the converged development line completed:

- full tracked corpus: **2438 passed, 2 skipped, 2 subtests passed**;
- the two skips were explicit public market-data smoke tests that require separate network opt-in;
- disposable PostgreSQL migrations passed through `20260928_0021` on both isolated databases;
- Public Test Corpus, Publication Safety, and CodeQL passed on the validated convergence heads.

The exact release commit is validated again through protected GitHub checks before the `v0.3.0` tag is created.

### Safety boundary

v0.3.0 is an official source release, not a profitability claim or approval for production/live trading. Live Brooks execution remains disabled/not production-approved unless separately reviewed and intentionally enabled.

## v0.2.0 — 2026-09-30

First public release candidate of the open-source snapshot.

Highlights:

- Apache-2.0 public source snapshot.
- Curated, hash-verified source manifest.
- Reproducible isolated installation path.
- Publication-safety and public-test CI.
- Security and OSS publication review documentation.

v0.2.0 was published as a prerelease and is not approved for production deployment or live trading.
