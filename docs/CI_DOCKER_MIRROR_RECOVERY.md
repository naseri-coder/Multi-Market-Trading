# GitHub Actions Docker Hub rate-limit recovery

This change is **CI-only**, never a production configuration or service
deployment. GitHub-hosted ephemeral Ubuntu runners configure the Google
Artifact Registry mirror `https://mirror.gcr.io` before building the release
image or pulling disposable PostgreSQL test images.

Google's official reference:
https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images

Controls retained:
- All existing workflows, migrations, release checks, CodeQL and unit
  test requirements remain enabled.
- `Dockerfile.production` stays byte-for-byte unchanged, including the pinned
  Python base-image SHA-256 digest.
- Existing `postgres:16-alpine` image reference remains unchanged.
- The daemon pulls a Docker Hub image from the cache if present; otherwise
  it tries Docker Hub. Cache availability is NOT guaranteed.
- Any image pull failure is a **hard CI failure**, never interpreted as a pass.
- Only `GITHUB_ACTIONS=true` on `RUNNER_ENVIRONMENT=github-hosted` can run
  the daemon change; no user server or local Docker daemon is touched.

This does not address unrelated PR content, market-data quality or private
NYFR licensing; those must be audited independently.
