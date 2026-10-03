# v0.3.0 Release Checklist

This checklist governs the first official v0.3.0 release. It does not authorize production deployment or live trading.

## 1. Finish source convergence

- [ ] Complete the remaining reviewed v0.3.0 convergence work.
- [ ] Confirm the final `develop/v0.3.0` HEAD is the intended source baseline.
- [ ] Confirm no unreviewed server-only source remains required for the release.
- [ ] Confirm migration history is coherent and complete.
- [ ] Confirm the curated source manifest matches the intended release source.

## 2. Reconcile public branches

- [ ] Reconcile legitimate documentation changes that landed on `main` after the development branch diverged.
- [ ] Update the OSS-readiness branch onto the final validated `develop/v0.3.0` HEAD.
- [ ] Confirm the OSS-readiness diff remains documentation/community-only.
- [ ] Resolve conflicts without changing validated trading/runtime semantics.

## 3. Version and release metadata

Only after the final source baseline is frozen:

- [ ] Set package version to `0.3.0`.
- [ ] Update README version/status text to match the release.
- [ ] Finalize the v0.3.0 section in `CHANGELOG.md`.
- [ ] Update release-baseline metadata and any exact-SHA guards that intentionally bind to the release.
- [ ] Verify dependency locks are synchronized and reproducible.

## 4. Validation

Run the repository's required release gates against the exact release candidate commit.

At minimum:

- [ ] public test corpus;
- [ ] publication-safety gates;
- [ ] CodeQL / code scanning;
- [ ] source-manifest verification;
- [ ] dependency-lock verification;
- [ ] migration-chain validation;
- [ ] Docker image build;
- [ ] isolated installation verification;
- [ ] package/import discovery;
- [ ] relevant integration tests using disposable resources only;
- [ ] final release-artifact review.

No production database, live trading runtime, or existing production deployment is part of this validation.

## 5. Security review

- [ ] Confirm no unresolved release-blocking Code Scanning findings.
- [ ] Confirm no unresolved published-secret findings.
- [ ] Review Dependabot/security advisories relevant to the exact release candidate.
- [ ] Confirm `.env.example` contains placeholders only.
- [ ] Confirm no private operational data, database dumps, credentials, keys, or private datasets are included.
- [ ] Confirm the public security-reporting path is documented and usable.

## 6. Community and OSS review

- [ ] Confirm LICENSE, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, SUPPORT, ROADMAP, and maintainer documentation are present.
- [ ] Confirm issue and pull-request templates render correctly.
- [ ] Confirm CODEOWNERS points to the current maintainer.
- [ ] Confirm project-impact claims are factual and do not imply profitability.
- [ ] Confirm documentation distinguishes source-derived interpretation from engineering policy where relevant.

## 7. Freeze the release commit

- [ ] Record the exact release commit SHA.
- [ ] Record the final curated manifest SHA256.
- [ ] Record test/security validation results tied to that exact SHA.
- [ ] Ensure no subsequent commit is silently treated as having inherited exact-SHA validation.

## 8. Publish v0.3.0

After all required gates pass:

- [ ] merge the validated release line according to the repository's protected-branch rules;
- [ ] create annotated/tagged version `v0.3.0`;
- [ ] publish a GitHub Release as an official release, not a prerelease;
- [ ] include concise release notes, exact commit identity, validation summary, known limitations, and safety boundaries;
- [ ] verify the public release page and source archives point to the intended commit.

## 9. Post-release

- [ ] Verify the default branch presents the v0.3.0 documentation and version consistently.
- [ ] Re-run any post-release baseline guard required by the repository.
- [ ] Keep the release explicitly separate from production/live-trading approval.
- [ ] Gather only genuine public adoption and contributor metrics for future OSS program applications.
