#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ "${GITHUB_ACTIONS:-}" == "true" ]] || { echo "RUNNER_ONLY"; exit 3; }
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ && "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || exit 3
[[ "${TEST_PROJECT:-}" == "stage3b-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" ]] || exit 3
test -f .env && test ! -L .env
compose=(docker compose -p "$TEST_PROJECT" -f compose.yaml --env-file .env)
echo "STAGE3B_BUILD_BEGIN"
"${compose[@]}" build bot
echo "STAGE3B_BUILD_PASS"
echo "STAGE3B_DISPOSABLE_POSTGRES_BEGIN"
"${compose[@]}" up -d --wait postgres
head_output="$("${compose[@]}" run --rm --no-deps bot python -m alembic -c alembic.ini heads 2>&1)"
grep -Fq "20261004_0022" <<<"$head_output"
check_revision() {
  local current
  current="$("${compose[@]}" exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Aqt -c "SELECT version_num FROM alembic_version;"')"
  [[ "$current" == "$1" ]]
}
"${compose[@]}" run --rm --no-deps bot python -m alembic -c alembic.ini upgrade 20261004_0022
check_revision 20261004_0022
echo "STAGE3B_MIGRATION_0022_PASS"
"${compose[@]}" run --rm --no-deps bot python -m alembic -c alembic.ini downgrade 20260914_0020
check_revision 20260914_0020
"${compose[@]}" run --rm --no-deps bot python -m alembic -c alembic.ini upgrade 20261004_0022
check_revision 20261004_0022
echo "STAGE3B_0022_ROLLBACK_REUPGRADE_PASS"
"${compose[@]}" run --rm --no-deps bot python -m app --check-config
"${compose[@]}" run --rm --no-deps bot python -m app --check-db
echo "STAGE3B_APP_CONFIG_DB_CHECKS_PASS"
"${compose[@]}" run --rm --no-deps --volume "${GITHUB_WORKSPACE}/production_checks:/ci_checks:ro" -e PYTHONPATH=/opt/crypto-signal-bot bot python /ci_checks/verify_historical_probability_regression.py
echo "STAGE3B_HP_REGRESSION_PASS"
"${compose[@]}" up -d --no-deps bot
ready=0
for i in {1..30}; do
  container="$("${compose[@]}" ps -q bot)"
  if [[ -n "$container" && "$(docker inspect --format '{{.State.Running}}' "$container")" == "true" ]]; then
    logs="$("${compose[@]}" logs --no-color --tail 120 bot 2>&1)"
    if grep -Fq "TELEGRAM_RUNTIME_DISABLED_OFFLINE_STARTUP_READY" <<<"$logs"; then ready=1; break; fi
  fi
  sleep 2
done
[[ "$ready" == 1 ]] || { echo "STAGE3B_OFFLINE_STARTUP_FAILED (logs suppressed)"; exit 1; }
"${compose[@]}" stop bot
logs="$("${compose[@]}" logs --no-color --tail 120 bot 2>&1)"
grep -Fq "TELEGRAM_RUNTIME_DISABLED_OFFLINE_SHUTDOWN_COMPLETE" <<<"$logs"
echo "STAGE3B_OFFLINE_STARTUP_SHUTDOWN_PASS"
echo "STAGE3B_DISPOSABLE_FUNCTIONAL_TESTS_PASS"
