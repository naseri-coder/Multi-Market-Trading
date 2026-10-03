#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:---check}"
if [[ "$MODE" != "--check" && "$MODE" != "--install" ]]; then
  echo "Usage: bash scripts/install.sh --check | --install" >&2
  exit 2
fi
for cmd in bash python3 sha256sum; do
  command -v "$cmd" >/dev/null || { echo "MISSING_PREREQUISITE: $cmd" >&2; exit 3; }
done
bash scripts/verify.sh
if [[ "$MODE" == "--check" ]]; then
  echo "CHECK_ONLY: no Docker calls, network, migration, or service changes performed"
  exit 0
fi

# Fresh-host only: never mutate the protected development/production tree.
if [[ -e /opt/crypto-signal-telegram-bot ]]; then
  echo "REFUSED: original Brooks project exists on this host" >&2
  exit 3
fi
if [[ ! -t 0 ]]; then
  echo "REFUSED: install requires an interactive operator" >&2
  exit 3
fi
if [[ ! -e .env ]]; then
  echo "No .env found; creating a private configuration for this fresh host."
  python3 scripts/bootstrap_env.py .env .env.example
fi
python3 scripts/check_env.py .env

# Compose gives inherited shell variables precedence over --env-file interpolation.
for name in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB DATABASE_URL; do
  if [[ -v "$name" ]]; then
    echo "REFUSED: inherited database override for $name (value suppressed)" >&2
    exit 3
  fi
done

command -v docker >/dev/null || {
  echo "MISSING_PREREQUISITE: Docker Engine. Install Docker Engine + Compose v2, then rerun." >&2
  exit 3
}
docker compose version >/dev/null 2>&1 || {
  echo "MISSING_PREREQUISITE: Docker Compose v2 plugin" >&2
  exit 3
}
docker info >/dev/null || {
  echo "DOCKER_UNAVAILABLE: Docker daemon is not reachable by this user" >&2
  exit 3
}
if docker volume inspect crypto-price-action_postgres_data >/dev/null 2>&1; then
  echo "REFUSED: install volume exists; no overwrite/upgrade through installer" >&2
  exit 3
fi

compose=(docker compose -p crypto-price-action -f compose.yaml --env-file .env)
"${compose[@]}" config --quiet
echo "NEW HOST ONLY. Creates dedicated DB, runs migrations, starts bot with runtime disabled."
read -r -p "Type INSTALL-NEW-HOST to continue: " consent
if [[ "$consent" != "INSTALL-NEW-HOST" ]]; then
  echo "CANCELLED"
  exit 3
fi

"${compose[@]}" build bot
"${compose[@]}" run --rm --no-deps bot   python release_tools/validate_release_config.py --from-environment --mode safe-install
"${compose[@]}" up -d --wait postgres
"${compose[@]}" run --rm --no-deps bot python -m alembic -c alembic.ini upgrade head
"${compose[@]}" run --rm --no-deps bot python -m app --check-config
"${compose[@]}" run --rm --no-deps bot python -m app --check-db
"${compose[@]}" up -d --no-deps bot
echo "NEW_HOST_INSTALL_FINISHED: v0.3.0 source installed with effectful runtime disabled"
