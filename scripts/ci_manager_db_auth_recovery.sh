#!/usr/bin/env bash
set -Eeuo pipefail

container="manager-db-auth-$RANDOM-$$"
network="manager-db-auth-net-$RANDOM-$$"
old_password="Old_Manager_DB_Password_2026_A"
new_password="New_Manager_DB_Password_2026_B"
user="crypto_bot"
db="crypto_bot"
stage="bootstrap"

diagnose() {
  rc=$?
  if [[ "$rc" -ne 0 ]]; then
    echo "MANAGER_DB_AUTH_REHEARSAL_FAIL stage=$stage rc=$rc" >&2
    docker ps -a --filter "name=^/${container}$" --format 'container={{.Status}}' >&2 || true
    docker logs "$container" >&2 || true
  fi
  return "$rc"
}

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap diagnose ERR
trap cleanup EXIT

stage="network"
docker network create "$network" >/dev/null

stage="docker_start"
docker run -d --rm   --name "$container"   --network "$network"   --network-alias postgres   --security-opt no-new-privileges:true   -e POSTGRES_USER="$user"   -e POSTGRES_PASSWORD="$old_password"   -e POSTGRES_DB="$db"   postgres:16-alpine >/dev/null

client_psql() {
  local password="$1"
  shift
  docker run --rm     --network "$network"     -e PGPASSWORD="$password"     postgres:16-alpine     psql -X -h postgres -U "$user" -d "$db" "$@"
}

stage="postgres_ready"
ready=0
for _ in {1..90}; do
  if client_psql "$old_password" -Atqc 'SELECT 1' 2>/dev/null | grep -Fxq '1'; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == "1" ]] || {
  echo "MANAGER_DB_AUTH_REHEARSAL_FAIL database_not_ready" >&2
  exit 1
}

stage="precondition_new_password_rejected"
if client_psql "$new_password" -Atqc 'SELECT 1' >/dev/null 2>&1; then
  echo "MANAGER_DB_AUTH_REHEARSAL_FAIL precondition" >&2
  exit 1
fi

stage="alter_role_password"
docker exec -i   -e POSTGRES_PASSWORD="$new_password"   -e POSTGRES_USER="$user"   -e POSTGRES_DB="$db"   "$container"   sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
\getenv nc_role POSTGRES_USER
\getenv nc_password POSTGRES_PASSWORD
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'nc_role', :'nc_password') \gexec
SQL

stage="verify_new_password"
client_psql "$new_password" -Atqc 'SELECT 1' | grep -Fxq '1'

stage="verify_old_password_rejected"
if client_psql "$old_password" -Atqc 'SELECT 1' >/dev/null 2>&1; then
  echo "MANAGER_DB_AUTH_REHEARSAL_FAIL old_password_still_valid" >&2
  exit 1
fi

stage="complete"
echo "MANAGER_DB_AUTH_REHEARSAL_PASS"
