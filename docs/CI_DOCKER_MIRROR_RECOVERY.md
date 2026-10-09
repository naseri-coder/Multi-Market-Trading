# GitHub Actions: trustworthy Docker Hub access (A2 release checks)

## Scope

All configuration is on **ephemeral GitHub-hosted Actions runners** only.
The public `Dockerfile.production`, immutable pinned Python SHA-256 image,
`postgres:16-alpine`, full PostgreSQL rehearsal, and all security gates are
unchanged. No server, brokerage API or strategy is touched.

## Verified issue

Public pulls from Docker Hub returned HTTP 429; Google's documented
`mirror.gcr.io` did **not** contain the required PostgreSQL tag; Docker
Official Images ECR Public also returned an anonymous rate-limit error.
We must not disable, skip or declare passing the regression tests.

## Required repo configuration

Create a Docker Hub personal access token restricted to **Read** for image
pulling. Add these *repository* GitHub Actions secrets, never to source files:

- `DOCKERHUB_USERNAME`: your Docker Hub username.
- `DOCKERHUB_TOKEN`: your read-only Docker Hub PAT.

GitHub interface: Settings → Secrets and variables → Actions →
New repository secret.

When both secrets exist, `scripts/ci_configure_docker_mirror.sh` logs in with
`--password-stdin`, configures Google's image cache, pulls and verifies the
same PostgreSQL 16 image, and lets every existing CI check run. It never emits
the token. When either secret is missing, the runner attempts public cache only;
if images remain inaccessible, the pipeline **fails closed** with
`CI_DOCKER_IMAGE_PULL_BLOCKED`.

Provider docs:
https://docs.docker.com/security/access-tokens/
https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images

No GitHub Actions `pull_request_target`, elevated untrusted PR code,
build-time secret injection or bypass of CI requirements is introduced.
