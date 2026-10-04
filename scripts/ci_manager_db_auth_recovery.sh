#!/usr/bin/env bash
set -Eeuo pipefail

container="manager-db-auth-$RANDOM-$$"
old_password="Old_Manager_DB_Password_2026_A"
new_password="New_Manager_DB_Password_2026_B"
user="crypto_bot"
db="crypto_bot"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --rm   --name "$container"   --security-opt no-new-privileges:true   -e POSTGRES_USER="$user"   -e POSTGRES_PASSWORD="$old_password"   -e POSTGRES_DB="$db"   postgres:16-alpine >/dev/null

for _ in {1..90}; do
  if docker exec "$container" pg_isready -U "$user" -d "$db" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec "$container" pg_isready -U "$user" -d "$db" >/dev/null

# New password must fail before the repair.
if docker exec -e PGPASSWORD="$new_password" "$container"   psql -X -h 127.0.0.1 -U "$user" -d "$db" -Atqc 'SELECT 1' >/dev/null 2>&1; then
  echo "MANAGER_DB_AUTH_REHEARSAL_FAIL precondition" >&2
  exit 1
fi

# This mirrors the Manager recovery path: local socket administration plus
# environment-only password transport. No password is written to logs.
docker exec -i   -e POSTGRES_PASSWORD="$new_password"   -e POSTGRES_USER="$user"   -e POSTGRES_DB="$db"   "$container"   sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
\getenv nc_role POSTGRES_USER
\getenv nc_password POSTGRES_PASSWORD
SELECT format('ALTER ROLE %I WITH PASSWORD %L', :'nc_role', :'nc_password') \gexec
SQL

docker exec -e PGPASSWORD="$new_password" "$container"   psql -X -h 127.0.0.1 -U "$user" -d "$db" -Atqc 'SELECT 1'   | grep -Fxq '1'

if docker exec -e PGPASSWORD="$old_password" "$container"   psql -X -h 127.0.0.1 -U "$user" -d "$db" -Atqc 'SELECT 1' >/dev/null 2>&1; then
  echo "MANAGER_DB_AUTH_REHEARSAL_FAIL old_password_still_valid" >&2
  exit 1
fi

echo "MANAGER_DB_AUTH_REHEARSAL_PASS"
