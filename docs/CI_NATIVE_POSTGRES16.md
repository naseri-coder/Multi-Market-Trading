# PostgreSQL 16 CI without a Docker Hub account

An independent GitHub Actions workflow is introduced for the A2 PR:
`.github/workflows/native-postgres16.yml`.

GitHub's maintained `ubuntu-24.04` hosted runners contain PostgreSQL 16,
initially disabled. This workflow starts the genuine native PostgreSQL
server on **a disposable GitHub-hosted runner**, with local socket-only
connections and two distinct empty databases.

It runs the **unchanged** frozen-source SHA checks, both Alembic upgrades
to revision `20261004_0022`, and the same complete
`python -m pytest -q` suite used by the containerized full-corpus workflow.

The native PostgreSQL test does NOT claim to prove the
`postgres:16-alpine` Docker image, Alpine-specific packaging, the
historic Docker deployment rehearsal, or the production Docker image.
Those existing required tests remain enabled and may fail while Docker
Hub is rate limiting anonymous pulls. Do not merge a protected release
until its required checks are confirmed by the repository's rules.

Neither server, production data, source manifests, package metadata,
private NYFR repository, external Telegram, nor broker credentials
are changed by this step.

Reference: https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md
