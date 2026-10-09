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

# The Google cache does not guarantee that postgres:16-alpine is cached.
# Pull the Docker Official Image from Docker's verified ECR Public gallery,
# then use the exact existing postgres:16-alpine reference in all CI scripts.
# No production images or Dockerfile versions are changed.
postgres_mirror="public.ecr.aws/docker/library/postgres:16-alpine"
docker pull "$postgres_mirror"
docker tag "$postgres_mirror" postgres:16-alpine
docker image inspect postgres:16-alpine >/dev/null
postgres_version="$(docker run --rm --entrypoint postgres postgres:16-alpine --version)"
case "$postgres_version" in
  'postgres (PostgreSQL) 16.'*) echo "CI_POSTGRES_16_IMAGE_VERIFIED" ;;
  *) echo "CI_POSTGRES_VERSION_MISMATCH" >&2; exit 1 ;;
esac
