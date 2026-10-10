#!/usr/bin/env bash
# Disposable GitHub-hosted PG16 only; no real infrastructure.
set -Eeuo pipefail
[[ "$GITHUB_ACTIONS" == "true" && "$RUNNER_ENVIRONMENT" == "github-hosted" ]] || {
  echo "A6_PG_REHEARSAL_REFUSED_OUTSIDE_CI" >&2
  exit 3
}
[[ "$GITHUB_RUN_ID" =~ ^[0-9]+$ ]] || exit 3
stage="$(mktemp -d /tmp/a6-restore-XXXXXXXX)"
cleanup() {
  rm -rf -- "$stage"
  sudo pg_ctlcluster 16 main stop >/dev/null 2>&1 || true
}
trap cleanup EXIT
# Network listening disabled; only local PostgreSQL Unix socket permitted.
sudo python3 - <<'PY'
from pathlib import Path
c = Path("/etc/postgresql/16/main/postgresql.conf")
c.write_text(c.read_text() + "\nlisten_addresses = ''\n")
h = Path("/etc/postgresql/16/main/pg_hba.conf")
h.write_text("local all a6bot scram-sha-256\n" + h.read_text())
PY
sudo pg_ctlcluster 16 main start
sudo -u postgres psql -v ON_ERROR_STOP=1 -c   "CREATE ROLE a6bot LOGIN CREATEDB PASSWORD 'a6_disposable_pg16_only';"
sudo -u postgres createdb -O a6bot a6_legacy
sudo -u postgres createdb -O a6bot a6_restored
export PGPASSWORD="a6_disposable_pg16_only"
export PYTHONPATH="$GITHUB_WORKSPACE"
legacy="postgresql+asyncpg://a6bot:a6_disposable_pg16_only@localhost/a6_legacy?host=/var/run/postgresql"
cp -a production_source/app ./app
cp -a production_source/migrations ./migrations
cp production_source/alembic.ini ./alembic.ini
DATABASE_URL="$legacy" python -m alembic -c alembic.ini upgrade 20261004_0022
[[ "$(psql -h /var/run/postgresql -U a6bot -d a6_legacy -Atqc 'SELECT version_num FROM alembic_version')" == "20261004_0022" ]]
psql -h /var/run/postgresql -U a6bot -d a6_legacy -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE a6_restore_evidence (seq integer PRIMARY KEY, stable_marker text NOT NULL);
INSERT INTO a6_restore_evidence VALUES
 (1, 'A6_FROZEN_SCHEMA_SNAPSHOT'),
 (2, 'SYNTHETIC_EVIDENCE_NO_CUSTOMER_DATA'),
 (3, 'RESTORE_CHECKSUM_IDENTICAL');
SQL
before="$(
  psql -h /var/run/postgresql -U a6bot -d a6_legacy -At     -c 'SELECT seq, stable_marker FROM a6_restore_evidence ORDER BY seq' |
    sha256sum | awk '{print $1}'
)"
sudo -u postgres pg_dump -Fc --no-acl --no-owner -d a6_legacy > "$stage/legacy.pg16.dump"
[[ -s "$stage/legacy.pg16.dump" ]]
pg_restore -h /var/run/postgresql -U a6bot --no-owner --no-acl   -d a6_restored "$stage/legacy.pg16.dump"
after="$(
  psql -h /var/run/postgresql -U a6bot -d a6_restored -At     -c 'SELECT seq, stable_marker FROM a6_restore_evidence ORDER BY seq' |
    sha256sum | awk '{print $1}'
)"
[[ "$before" == "$after" ]] || { echo "A6_RESTORED_DATA_SHA256_MISMATCH" >&2; exit 1; }
[[ "$(psql -h /var/run/postgresql -U a6bot -d a6_restored -Atqc 'SELECT version_num FROM alembic_version')" == "20261004_0022" ]]
[[ "$(psql -h /var/run/postgresql -U a6bot -d a6_legacy -Atqc 'SELECT count(*) FROM a6_restore_evidence')" == "3" ]]
[[ -z "$(sudo ss -lntp | grep -E ':5432\b' || true)" ]] || {
  echo "A6_POSTGRES_NETWORK_LISTENER_REFUSED" >&2; exit 1;
}
echo "A6_LEGACY_PG16_0022_FULL_SCHEMA_BACKUP_RESTORE_PASS"
echo "A6_NO_RUNTIME_DATABASE_CUTOVER_PERFORMED"
