# Release Baseline

## Frozen published baseline

The published pre-release `v0.2.0` is the frozen public baseline for this release line.

- Tag: `v0.2.0`
- Exact commit: `d5abb04917c774b87f366d369da6221002ae35d8`
- Package version: `0.2.0`
- Curated source allowlist: 348 files
- Curated manifest SHA256: `769aa1757120c71ddf17579f18f1b63cd5ef3685a25287bd68d7c9bc7c341b49`

Future development must not redefine the identity of this release.

## Integrity controls

`scripts/ci_release_baseline.py` verifies that the release tag still points to the exact published commit and that the GitHub Release remains published as a pre-release with the expected identity markers.

`.github/workflows/release-baseline-guard.yml` runs hourly and on tag deletion. If the `v0.2.0` tag is missing or moved, the guard restores it to the exact published commit and then re-verifies the release baseline.

The protected publication gate also checks this baseline before allowing itself to pass.

GitHub-native immutable releases apply only to releases published after that repository setting is enabled, so this already-published release is protected by the explicit baseline controls above rather than being represented as retroactively immutable.

## Next development line

The next development line starts from the published baseline on:

`develop/v0.3.0`

Changes for the next version belong on development/topic branches and must pass the repository publication/security gates before reaching `main`. The `v0.2.0` tag remains anchored to the published commit regardless of later `main` development.
