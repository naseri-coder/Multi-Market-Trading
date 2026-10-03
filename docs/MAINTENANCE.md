# Maintenance Model

## Maintainer

The primary maintainer is `@naseri-coder`.

## Development model

Changes are developed on focused branches and reviewed through pull requests. Work that changes source semantics, migrations, persistence, dependencies, publication boundaries, or release identity requires explicit validation appropriate to that scope.

The repository currently maintains a dedicated v0.3.0 development line. The default branch and release tags remain authoritative for published releases.

## Validation

The project uses layered checks rather than a single test command. Depending on the change, validation can include:

- public unit and integration tests;
- publication-safety checks;
- source-manifest and SHA256 verification;
- dependency-lock reproducibility checks;
- Docker build and isolated-install checks;
- migration-chain validation;
- lint/regression debt gates;
- package/import discovery;
- security and release-readiness review.

A passing subset is not automatically equivalent to release approval.

## Source provenance

The curated public source snapshot is tracked with a SHA256 manifest. Changes that alter the frozen source identity require a reviewed manifest update; documentation-only maintenance must not silently change source identity.

## Dependencies

Runtime and development dependencies are pinned. Dependabot is configured for Python, Docker, and GitHub Actions updates. Dependency updates should preserve reproducibility and pass the relevant regression/security gates.

## Security

Sensitive information must never be committed to the repository. See [SECURITY.md](../SECURITY.md) and [OSS Publication Review](OSS_PUBLICATION_REVIEW.md).

## Releases

An official release requires an exact release commit, passing release/publication gates, coherent version metadata, release notes, and an explicit tag/release operation. Development-branch state is not itself a release.

## Contribution review

Pull requests should state:

- what behavior changes;
- what was tested;
- whether trading semantics change;
- whether migrations or persistence change;
- whether source provenance changes;
- whether security or deployment boundaries change.

Small, reviewable changes are preferred.
