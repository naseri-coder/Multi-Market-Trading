#!/usr/bin/env bash
# Stage 2Y: isolated PostgreSQL migration 0023 downgrade acceptance.
# All URLs MUST refer to scratch-only DBs created by the Stage2Y GitHub runner.
set -Eeuo pipefail

: "${STAGE2Y_ROOT:?missing ephemeral root}"
: "${STAGE2Y_SOCKET:?missing ephemeral socket}"
: "${STAGE2Y_PGPASSWORD:?missing synthetic password}"
: "${STAGE2Y_EMPTY_URL:?missing empty scratch URL}"
: "${STAGE2Y_LEGACY_URL:?missing legacy scratch URL}"

[[ "$STAGE2Y_ROOT" == /tmp/mmt-stage2y-* ]] || exit 90
[[ "$STAGE2Y_SOCKET" == "$STAGE2Y_ROOT/socket" ]] || exit 91
[[ -S "$STAGE2Y_SOCKET/.s.PGSQL.5432" ]] || exit 92
[[ -z "${MMT_PRODUCTION+x}" ]] || { echo "STAGE2Y_PRODUCTION_ENV_DENIED"; exit 93; }
[[ "$APP_ENV" == "test" ]] || exit 94
[[ "$STAGE2Y_EMPTY_URL" == *"/stage2y_empty?host=$STAGE2Y_SOCKET" ]] || exit 95
[[ "$STAGE2Y_LEGACY_URL" == *"/stage2y_legacy?host=$STAGE2Y_SOCKET" ]] || exit 96

sql() {
  local database="$1"
  local statement="$2"
  PGPASSWORD="$STAGE2Y_PGPASSWORD" psql -X -q -h "$STAGE2Y_SOCKET" \
    -U stage2y_scratch -d "$database" -v ON_ERROR_STOP=1 -Atc "$statement"
}

migrate() {
  local url="$1"
  shift
  DATABASE_URL="$url" python -m alembic -c alembic.ini "$@"
}

# 1) Truly empty archive: upgrade -> downgrade -> re-upgrade.
migrate "$STAGE2Y_EMPTY_URL" upgrade 20261013_0023
[[ "$(sql stage2y_empty "SELECT version_num FROM alembic_version")" == "20261013_0023" ]]
[[ "$(sql stage2y_empty "SELECT count(*) FROM retired_strategy_evidence_archive")" == "0" ]]
migrate "$STAGE2Y_EMPTY_URL" downgrade 20261004_0022
[[ "$(sql stage2y_empty "SELECT version_num FROM alembic_version")" == "20261004_0022" ]]
[[ -z "$(sql stage2y_empty "SELECT to_regclass('public.retired_strategy_evidence_archive')")" ]]
migrate "$STAGE2Y_EMPTY_URL" upgrade 20261013_0023
[[ "$(sql stage2y_empty "SELECT version_num FROM alembic_version")" == "20261013_0023" ]]
[[ "$(sql stage2y_empty "SELECT count(*) FROM retired_strategy_evidence_archive")" == "0" ]]
[[ "$(sql stage2y_empty "SELECT count(*) FROM signal_strategy_configs WHERE strategy_code='BROOKS'")" == "1" ]]
echo "STAGE2Y_EMPTY_ARCHIVE_DOWNGRADE_REUPGRADE_PASS"

# 2) Simulate an old, broader allowlist on a completely separate scratch DB.
# Revision 0022 currently permits BROOKS only for new deployments, but earlier
# installed DBs may have accepted other codes. This synthetic case explicitly
# emulates that historical schema; it does NOT claim actual production data.
migrate "$STAGE2Y_LEGACY_URL" upgrade 20261004_0022
[[ "$(sql stage2y_legacy "SELECT version_num FROM alembic_version")" == "20261004_0022" ]]
sql stage2y_legacy "ALTER TABLE signal_strategy_configs DROP CONSTRAINT ck_signal_strategy_configs_strategy_code" >/dev/null
sql stage2y_legacy "ALTER TABLE signal_strategy_configs ADD CONSTRAINT ck_signal_strategy_configs_strategy_code CHECK (strategy_code IN ('BROOKS','LEGACY_TEST'))" >/dev/null
sql stage2y_legacy "INSERT INTO signal_strategy_configs (strategy_code, display_name) VALUES ('LEGACY_TEST','Stage2Y disposable evidence')" >/dev/null
[[ "$(sql stage2y_legacy "SELECT count(*) FROM signal_strategy_configs WHERE strategy_code='LEGACY_TEST'")" == "1" ]]

migrate "$STAGE2Y_LEGACY_URL" upgrade 20261013_0023
[[ "$(sql stage2y_legacy "SELECT version_num FROM alembic_version")" == "20261013_0023" ]]
[[ "$(sql stage2y_legacy "SELECT count(*) FROM signal_strategy_configs WHERE strategy_code='LEGACY_TEST'")" == "0" ]]
[[ "$(sql stage2y_legacy "SELECT count(*) FROM retired_strategy_evidence_archive WHERE source_table='signal_strategy_configs' AND snapshot->>'strategy_code'='LEGACY_TEST'")" == "1" ]]
archive_hash_before="$(sql stage2y_legacy "SELECT md5(snapshot::text) FROM retired_strategy_evidence_archive WHERE source_table='signal_strategy_configs' AND snapshot->>'strategy_code'='LEGACY_TEST'")"
[[ -n "$archive_hash_before" ]]
echo "STAGE2Y_LEGACY_DATA_ARCHIVED_PASS"

# 3) Genuine Alembic downgrade must FAIL closed against nonempty archive.
refusal_log="$STAGE2Y_ROOT/expected-refusal.log"
if migrate "$STAGE2Y_LEGACY_URL" downgrade 20261004_0022 >"$refusal_log" 2>&1; then
  echo "STAGE2Y_DESTRUCTIVE_DOWNGRADE_UNEXPECTED_SUCCESS"
  exit 97
fi
grep -Fq "NONEMPTY_STRATEGY_ARCHIVE_DOWNGRADE_REFUSED" "$refusal_log" || {
  echo "STAGE2Y_DOWNGRADE_FAILED_FOR_WRONG_REASON"
  tail -n 25 "$refusal_log"
  exit 98
}
[[ "$(sql stage2y_legacy "SELECT version_num FROM alembic_version")" == "20261013_0023" ]]
[[ "$(sql stage2y_legacy "SELECT count(*) FROM retired_strategy_evidence_archive")" == "1" ]]
archive_hash_after="$(sql stage2y_legacy "SELECT md5(snapshot::text) FROM retired_strategy_evidence_archive WHERE source_table='signal_strategy_configs' AND snapshot->>'strategy_code'='LEGACY_TEST'")"
[[ "$archive_hash_after" == "$archive_hash_before" ]]
[[ "$(sql stage2y_legacy "SELECT count(*) FROM signal_strategy_configs WHERE strategy_code='BROOKS'")" == "1" ]]
[[ "$(sql stage2y_legacy "SELECT count(*) FROM pg_constraint WHERE conname IN ('ck_signal_strategy_configs_strategy_code','ck_signal_automation_metadata_producer')")" == "2" ]]
echo "STAGE2Y_NONEMPTY_ARCHIVE_DOWNGRADE_REFUSED_AND_EVIDENCE_PRESERVED_PASS"
echo "STAGE2Y_REAL_POSTGRESQL_MIGRATION_ACCEPTANCE_PASS"
