# Changelog

All notable public changes to this project are recorded here.

This project remains under active development and validation. A tagged release does not imply production or live-trading approval.

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
