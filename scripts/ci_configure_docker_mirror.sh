#!/usr/bin/env bash
# Ephemeral GitHub Actions runner only: use Google Artifact Registry's
# pull-through cache for Docker Official Images. Never change release images.
set -Eeuo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" ]]; then
  echo "CI_DOCKER_MIRROR_REFUSED_NON_GITHUB_HOSTED_RUNNER" >&2
  exit 1
fi

sudo python3 - <<'PY'
import json
from pathlib import Path
path = Path("/etc/docker/daemon.json")
configuration = json.loads(path.read_text()) if path.exists() else {}
if not isinstance(configuration, dict):
    raise SystemExit("CI_DOCKER_MIRROR_INVALID_DAEMON_CONFIG")
mirror = "https://mirror.gcr.io"
existing = configuration.get("registry-mirrors", [])
if not isinstance(existing, list) or any(not isinstance(v, str) for v in existing):
    raise SystemExit("CI_DOCKER_MIRROR_INVALID_CONFIG")
configuration["registry-mirrors"] = [mirror, *(v for v in existing if v != mirror)]
path.write_text(json.dumps(configuration, indent=2) + "\n", encoding="utf-8")
PY

sudo systemctl restart docker
for attempt in $(seq 1 20); do
  if docker info --format '{{json .RegistryConfig.Mirrors}}' 2>/dev/null | grep -Fq "mirror.gcr.io"; then
    echo "CI_DOCKER_MIRROR_CONFIGURED"
    break
  fi
  sleep 2
done
if ! docker info --format '{{json .RegistryConfig.Mirrors}}' | grep -Fq "mirror.gcr.io"; then
  echo "CI_DOCKER_MIRROR_VERIFICATION_FAILED" >&2
  exit 1
fi

# Optional GitHub Actions secrets. Tokens must have read-only Docker Hub scope.
# Never pass tokens on command line or print them to CI logs.
if [[ -n "${DOCKERHUB_USERNAME:-}" && -n "${DOCKERHUB_TOKEN:-}" ]]; then
  printf '%s' "$DOCKERHUB_TOKEN" | docker login --username "$DOCKERHUB_USERNAME" --password-stdin >/dev/null
  echo "CI_DOCKERHUB_AUTHENTICATED"
elif [[ -n "${DOCKERHUB_USERNAME:-}" || -n "${DOCKERHUB_TOKEN:-}" ]]; then
  echo "CI_DOCKERHUB_PARTIAL_SECRET_CONFIG" >&2
  exit 1
else
  echo "CI_DOCKERHUB_SECRETS_MISSING_PUBLIC_CACHE_ONLY"
fi

# Check exactly the same official PostgreSQL major version used by the
# existing release CI. A failed pull is a hard fail: never waive the DB tests.
if ! docker pull postgres:16-alpine; then
  echo "CI_DOCKER_IMAGE_PULL_BLOCKED: add DOCKERHUB_USERNAME and read-only DOCKERHUB_TOKEN as GitHub Actions secrets" >&2
  exit 1
fi
postgres_version="$(docker run --rm --entrypoint postgres postgres:16-alpine --version)"
case "$postgres_version" in
  'postgres (PostgreSQL) 16.'*) echo "CI_POSTGRES_16_IMAGE_VERIFIED" ;;
  *) echo "CI_POSTGRES_VERSION_MISMATCH" >&2; exit 1 ;;
esac
