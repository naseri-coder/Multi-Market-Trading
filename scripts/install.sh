#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:---check}"
if [[ "$MODE" != "--check" && "$MODE" != "--install" ]]; then
  echo "Usage: bash scripts/install.sh --check | --install" >&2; exit 2
fi
bash scripts/verify.sh
if [[ "$MODE" == "--check" ]]; then
  echo "CHECK_ONLY: no Docker calls, network, migration, or service changes performed"
  exit 0
fi
# This installer is strictly for a fresh separate host.
if [[ -e /opt/crypto-signal-telegram-bot ]]; then
  echo "REFUSED: original Brooks project exists on this host" >&2; exit 3
fi
if [[ ! -t 0 ]]; then
  echo "REFUSED: install requires an interactive operator" >&2; exit 3
fi
python3 scripts/check_env.py .env
# Compose gives inherited shell variables precedence over --env-file interpolation.
# Refuse conflicting database overrides rather than using different bot and DB credentials.
for name in POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB; do
  if [[ -v "$name" ]]; then
    echo "REFUSED: inherited Compose database override for $name (value suppressed)" >&2; exit 3
  fi
done
command -v docker >/dev/null || { echo "Install Docker Engine and Compose v2 first" >&2; exit 3; }
docker compose version >/dev/null
docker info >/dev/null
if docker volume inspect albrooks-installable_postgres_data >/dev/null 2>&1; then
  echo "REFUSED: install volume exists; no overwrite/upgrade through installer" >&2; exit 3
fi
docker compose -p albrooks-installable -f compose.yaml --env-file .env config --quiet
echo "NEW HOST ONLY. Creates dedicated DB, runs migrations, starts bot with runtime disabled."
read -r -p "Type INSTALL-NEW-HOST to continue: " consent
if [[ "$consent" != "INSTALL-NEW-HOST" ]]; then echo "CANCELLED"; exit 3; fi
compose=(docker compose -p albrooks-installable -f compose.yaml --env-file .env)
"${compose[@]}" build bot
"${compose[@]}" up -d --wait postgres
"${compose[@]}" run --rm --no-deps bot python -m alembic -c alembic.ini upgrade head
"${compose[@]}" up -d --no-deps bot
echo "NEW_HOST_INSTALL_FINISHED: review bot status; no live Brooks execution enabled"
